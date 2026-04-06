#define _GNU_SOURCE
#include <iostream>
#include <fstream>
#include <vector>
#include <dlfcn.h>
#include <cuda.h>
#include <unistd.h>
#include <sys/wait.h>
#include <elf.h>
#include <cstring>
#include <mutex>
#include <regex>
#include <fcntl.h>
#include <stdarg.h>

void log_msg(const char* format, ...) {
    int fd = open("/tmp/sass_fma.log", O_WRONLY | O_CREAT | O_APPEND, 0666);
    if (fd != -1) {
        va_list args;
        va_start(args, format);
        vdprintf(fd, format, args);
        va_end(args);
        close(fd);
    }
}

__attribute__((constructor))
void interceptor_init() {
    log_msg(">>> [Interceptor] Library Loaded into PID %d <<<\n", getpid());
}

typedef CUresult (*cuModuleLoadDataEx_t)(CUmodule*, const void*, unsigned int, CUjit_option*, void**);

static std::mutex g_rewriter_mutex;

bool is_elf(const void* data) {
    if (!data) return false;
    const unsigned char* magic = (const unsigned char*)data;
    return (magic[0] == 0x7f && magic[1] == 'E' && magic[2] == 'L' && magic[3] == 'F');
}

size_t get_elf_size(const void* data) {
    const Elf64_Ehdr* ehdr = (const Elf64_Ehdr*)data;
    size_t sh_end = ehdr->e_shoff + (ehdr->e_shentsize * ehdr->e_shnum);
    size_t ph_end = ehdr->e_phoff + (ehdr->e_phentsize * ehdr->e_phnum);
    return ((sh_end > ph_end) ? sh_end : ph_end) + 8192;
}

const void* find_elf(const void* data, size_t total_size, size_t* out_size) {
    const unsigned char* p = (const unsigned char*)data;
    for (size_t i = 0; i < total_size - 64; ++i) {
        if (p[i] == 0x7f && p[i+1] == 'E' && p[i+2] == 'L' && p[i+3] == 'F') {
            const Elf64_Ehdr* ehdr = (const Elf64_Ehdr*)(p + i);
            if (ehdr->e_machine == 190 || ehdr->e_machine == 0) { // EM_CUDA or Generic
                 *out_size = get_elf_size(ehdr);
                 if (i + *out_size <= total_size) return ehdr;
            }
        }
    }
    return NULL;
}

std::string patch_ptx(const char* input) {
    std::string ptx(input);
    size_t pos = 0;
    while ((pos = ptx.find(".entry", pos)) != std::string::npos) {
        size_t brace = ptx.find("{", pos);
        if (brace != std::string::npos) {
            ptx.insert(brace + 1, "\n\t.reg .f32 %f_tmp;\n");
            pos = brace + 20;
        } else break;
    }
    std::regex fma_regex("fma\\.rn\\.f32\\s+([^,]+),\\s+([^,]+),\\s+([^,]+),\\s+([^;]+);");
    ptx = std::regex_replace(ptx, fma_regex, "mul.rn.f32 %f_tmp, $2, $3; add.rn.f32 $1, %f_tmp, $4;");
    return ptx;
}

CUresult patch_and_load(cuModuleLoadDataEx_t original_func, CUmodule* module, const void* image, unsigned int numOptions, CUjit_option* options, void** optionValues) {
    if (!image) return original_func(module, image, numOptions, options, optionValues);

    const void* target_image = image;
    size_t target_size = 0;

    const uint32_t* magic = (const uint32_t*)image;
    if (magic[0] == 0x46624110) {
        log_msg("[Hook] Fatbinary detected. Searching for cubin...\n");
        struct fatBinaryHeader {
            unsigned int magic;
            unsigned short version;
            unsigned short headerSize;
            unsigned long long fatSize;
        };
        const fatBinaryHeader* h = (const fatBinaryHeader*)image;
        target_image = find_elf(image, h->fatSize, &target_size);
        if (!target_image) {
            log_msg("[Hook] No cubin found in fatbinary. Passing original to driver.\n");
            return original_func(module, image, numOptions, options, optionValues);
        }
        log_msg("[Hook] Extracted cubin from fatbinary (size %zu).\n", target_size);
    }

    if (!is_elf(target_image)) {
        const char* ptx_str = (const char*)target_image;
        if (strncmp(ptx_str, ".version", 8) == 0 || strncmp(ptx_str, "\n.version", 9) == 0) {
            log_msg("[Hook] PTX detected. Patching...\n");
            std::string patched = patch_ptx(ptx_str);
            std::vector<CUjit_option> new_opts;
            std::vector<void*> new_vals;
            bool mode_set = false;
            for (unsigned int i = 0; i < numOptions; ++i) {
                new_opts.push_back(options[i]);
                if (options[i] == CU_JIT_FMA) {
                    new_vals.push_back((void*)0); 
                    mode_set = true;
                } else new_vals.push_back(optionValues[i]);
            }
            if (!mode_set) {
                new_opts.push_back(CU_JIT_FMA);
                new_vals.push_back((void*)0);
            }
            return original_func(module, patched.c_str(), new_opts.size(), new_opts.data(), new_vals.data());
        }
        return original_func(module, image, numOptions, options, optionValues);
    }

    log_msg("[Hook] ELF binary detected. Running rewriter...\n");
    std::lock_guard<std::mutex> lock(g_rewriter_mutex);
    if (target_size == 0) target_size = get_elf_size(target_image);
    
    char tmp_in[] = "/tmp/orig_XXXXXX.cubin";
    char tmp_out[] = "/tmp/patched_XXXXXX.cubin";
    int fd_in = mkstemps(tmp_in, 6);
    int fd_out = mkstemps(tmp_out, 6);
    close(fd_out);
    write(fd_in, target_image, target_size);
    close(fd_in);

    std::string cmd = "python3 rewriter.py " + std::string(tmp_in) + " " + std::string(tmp_out) + " > /dev/null 2>&1";
    int status = system(cmd.c_str());
    
    CUresult result;
    if (status == 0) {
        std::ifstream ifs(tmp_out, std::ios::binary | std::ios::ate);
        if (ifs.is_open()) {
            std::streamsize p_size = ifs.tellg();
            ifs.seekg(0, std::ios::beg);
            std::vector<char> buffer(p_size);
            ifs.read(buffer.data(), p_size);
            result = original_func(module, buffer.data(), numOptions, options, optionValues);
        } else {
            result = original_func(module, target_image, numOptions, options, optionValues);
        }
    } else {
        result = original_func(module, target_image, numOptions, options, optionValues);
    }
    unlink(tmp_in); unlink(tmp_out);
    return result;
}

extern "C" {
    __attribute__((visibility("default"))) CUresult cuModuleLoadData(CUmodule* module, const void* image) {
        static auto orig = (cuModuleLoadDataEx_t)dlsym(RTLD_NEXT, "cuModuleLoadDataEx");
        return patch_and_load(orig, module, image, 0, NULL, NULL);
    }
    __attribute__((visibility("default"))) CUresult cuModuleLoadData_v2(CUmodule* module, const void* image) {
        return cuModuleLoadData(module, image);
    }
    __attribute__((visibility("default"))) CUresult cuModuleLoadDataEx(CUmodule* module, const void* image, unsigned int n, CUjit_option* o, void** v) {
        static auto orig = (cuModuleLoadDataEx_t)dlsym(RTLD_NEXT, "cuModuleLoadDataEx");
        return patch_and_load(orig, module, image, n, o, v);
    }
    __attribute__((visibility("default"))) CUresult cuModuleLoadDataEx_v2(CUmodule* module, const void* image, unsigned int n, CUjit_option* o, void** v) {
        return cuModuleLoadDataEx(module, image, n, o, v);
    }
    __attribute__((visibility("default"))) CUresult cuModuleLoad(CUmodule* module, const char* fname) {
        std::ifstream ifs(fname, std::ios::binary | std::ios::ate);
        if (!ifs.is_open()) {
             typedef CUresult (*cuModuleLoad_t)(CUmodule*, const char*);
            static auto orig = (cuModuleLoad_t)dlsym(RTLD_NEXT, "cuModuleLoad");
            return orig(module, fname);
        }
        std::streamsize size = ifs.tellg();
        ifs.seekg(0, std::ios::beg);
        std::vector<char> buffer(size);
        ifs.read(buffer.data(), size);
        return cuModuleLoadData(module, buffer.data());
    }
    __attribute__((visibility("default"))) void** __cudaRegisterFatBinary(void* fatb) {
        log_msg(">>> [Hook] __cudaRegisterFatBinary called <<<\n");
        typedef void** (*reg_t)(void*);
        static reg_t orig = (reg_t)dlsym(RTLD_NEXT, "__cudaRegisterFatBinary");
        return orig(fatb);
    }
     __attribute__((visibility("default"))) void __cudaUnregisterFatBinary(void** handle) {
        log_msg(">>> [Hook] __cudaUnregisterFatBinary called <<<\n");
        typedef void (*unreg_t)(void**);
        static unreg_t orig = (unreg_t)dlsym(RTLD_NEXT, "__cudaUnregisterFatBinary");
        orig(handle);
    }
}
