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

typedef CUresult (*cuModuleLoadDataEx_t)(CUmodule*, const void*, unsigned int, CUjit_option*, void**);
typedef CUresult (*cuModuleLoadData_t)(CUmodule*, const void*);

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

std::string patch_ptx(const char* input) {
    std::string ptx(input);
    
    // 1. Inject temp register declaration into each entry
    // A more robust way would be per-function, but global-ish within the entry works.
    size_t pos = 0;
    while ((pos = ptx.find(".entry", pos)) != std::string::npos) {
        size_t brace = ptx.find("{", pos);
        if (brace != std::string::npos) {
            ptx.insert(brace + 1, "\n\t.reg .f32 %f_tmp;\n");
            pos = brace + 20; // Skip ahead
        } else break;
    }

    // 2. Replace fma.rn.f32 with mul + add
    // Pattern: fma.rn.f32 dest, src1, src2, src3;
    std::regex fma_regex("fma\\.rn\\.f32\\s+([^,]+),\\s+([^,]+),\\s+([^,]+),\\s+([^;]+);");
    ptx = std::regex_replace(ptx, fma_regex, "mul.rn.f32 %f_tmp, $2, $3; add.rn.f32 $1, %f_tmp, $4;");

    return ptx;
}

CUresult patch_and_load(cuModuleLoadDataEx_t original_func, CUmodule* module, const void* image, unsigned int numOptions, CUjit_option* options, void** optionValues) {
    if (!image) return original_func(module, image, numOptions, options, optionValues);

    const uint32_t* magic = (const uint32_t*)image;
    if (magic[0] == 0x46624110) {
        // --- Fatbinary Path ---
        // The driver will eventually extract SASS or PTX from this and call LoadDataEx again.
        // We let this pass so we can catch the specific cubin/ptx in the next recursive call.
        return original_func(module, image, numOptions, options, optionValues);
    }

    if (!is_elf(image)) {
        // --- PTX Path ---
        const char* ptx_str = (const char*)image;
        if (strncmp(ptx_str, ".version", 8) != 0 && strncmp(ptx_str, "\n.version", 9) != 0) {
            // Not PTX either, just load normally
            return original_func(module, image, numOptions, options, optionValues);
        }

        std::cerr << "[Hook] PTX string detected. Splitting FMAs..." << std::endl;
        std::string patched = patch_ptx(ptx_str);

        // Add CU_JIT_FMA_MODE = CU_JIT_FMA_NONE to options
        std::vector<CUjit_option> new_opts;
        std::vector<void*> new_vals;
        bool mode_set = false;

        for (unsigned int i = 0; i < numOptions; ++i) {
            new_opts.push_back(options[i]);
            if (options[i] == CU_JIT_FMA) {
                new_vals.push_back((void*)0); // 0 = CU_JIT_FMA_NONE
                mode_set = true;
            } else {
                new_vals.push_back(optionValues[i]);
            }
        }

        if (!mode_set) {
            new_opts.push_back(CU_JIT_FMA);
            new_vals.push_back((void*)0);
        }

        return original_func(module, patched.c_str(), new_opts.size(), new_opts.data(), new_vals.data());
    }

    // --- SASS (ELF) Path ---
    std::lock_guard<std::mutex> lock(g_rewriter_mutex);
    size_t size = get_elf_size(image);
    char tmp_in[] = "/tmp/orig_XXXXXX.cubin";
    char tmp_out[] = "/tmp/patched_XXXXXX.cubin";
    int fd_in = mkstemps(tmp_in, 6);
    int fd_out = mkstemps(tmp_out, 6);
    if (fd_in == -1 || fd_out == -1) {
        if (fd_in != -1) close(fd_in);
        if (fd_out != -1) close(fd_out);
        return original_func(module, image, numOptions, options, optionValues);
    }
    close(fd_out);
    if (write(fd_in, image, size) != (ssize_t)size) {
        close(fd_in); unlink(tmp_in); unlink(tmp_out);
        return original_func(module, image, numOptions, options, optionValues);
    }
    close(fd_in);

    std::string cmd = "python3 rewriter.py " + std::string(tmp_in) + " " + std::string(tmp_out) + " > /dev/null 2>&1";
    int status = system(cmd.c_str());
    
    CUresult result = CUDA_ERROR_UNKNOWN;
    if (status == 0) {
        std::ifstream ifs(tmp_out, std::ios::binary | std::ios::ate);
        if (ifs.is_open()) {
            std::streamsize p_size = ifs.tellg();
            ifs.seekg(0, std::ios::beg);
            std::vector<char> buffer(p_size);
            ifs.read(buffer.data(), p_size);
            result = original_func(module, buffer.data(), numOptions, options, optionValues);
        } else {
            result = original_func(module, image, numOptions, options, optionValues);
        }
    } else {
        result = original_func(module, image, numOptions, options, optionValues);
    }

    unlink(tmp_in);
    unlink(tmp_out);
    return result;
}

extern "C" CUresult cuModuleLoadDataEx(CUmodule* module, const void* image, unsigned int numOptions, CUjit_option* options, void** optionValues) {
    static auto orig = (cuModuleLoadDataEx_t)dlsym(RTLD_NEXT, "cuModuleLoadDataEx");
    return patch_and_load(orig, module, image, numOptions, options, optionValues);
}

extern "C" CUresult cuModuleLoadData(CUmodule* module, const void* image) {
    static auto orig_ex = (cuModuleLoadDataEx_t)dlsym(RTLD_NEXT, "cuModuleLoadDataEx");
    return patch_and_load(orig_ex, module, image, 0, NULL, NULL);
}
