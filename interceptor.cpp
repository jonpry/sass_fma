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

typedef CUresult (*cuModuleLoadDataEx_t)(CUmodule*, const void*, unsigned int, CUjit_option*, void**);
typedef CUresult (*cuModuleLoadData_t)(CUmodule*, const void*);
typedef CUresult (*cuModuleLoad_t)(CUmodule*, const char*);
typedef void** (*cudaRegisterFatBinary_t)(void*);

static std::mutex g_mutex;

// --- FatBinary Structures (Simplified) ---
struct __fatBinC_Header {
    uint32_t magic;
    uint16_t version;
    uint16_t header_size;
    uint64_t fat_size;
};

extern "C" void** __cudaRegisterFatBinary(void* fatb) {
    static auto orig = (cudaRegisterFatBinary_t)dlsym(RTLD_NEXT, "__cudaRegisterFatBinary");
    
    struct __fatBinC_Header* header = (struct __fatBinC_Header*)fatb;
    if (header->magic == 0x46624110) { // FATBIN_MAGIC
        std::cout << "[Hook] FatBinary registration detected (size: " << header->fat_size << ")." << std::endl;
        char* env = getenv("CUDA_FORCE_PTX_JIT");
        if (!env || std::string(env) != "1") {
            std::cout << "[Hook] WARNING: CUDA_FORCE_PTX_JIT is not set to 1. Kernels in this fatbinary might bypass the rewriter!" << std::endl;
        }
    }

    return orig(fatb);
}

size_t get_elf_size(const void* data) {
    const Elf64_Ehdr* ehdr = (const Elf64_Ehdr*)data;
    if (memcmp(ehdr->e_ident, ELFMAG, SELFMAG) != 0) return 0;
    const uint8_t* base = (const uint8_t*)data;
    size_t max_end = ehdr->e_shoff + (size_t)ehdr->e_shentsize * ehdr->e_shnum;
    size_t ph_end = ehdr->e_phoff + (size_t)ehdr->e_phentsize * ehdr->e_phnum;
    if (ph_end > max_end) max_end = ph_end;
    for (int i = 0; i < ehdr->e_shnum; i++) {
        const Elf64_Shdr* shdr = (const Elf64_Shdr*)(base + ehdr->e_shoff + (size_t)i * ehdr->e_shentsize);
        if (shdr->sh_type != SHT_NOBITS) {
            size_t sec_end = shdr->sh_offset + shdr->sh_size;
            if (sec_end > max_end) max_end = sec_end;
        }
    }
    return max_end;
}

// Internal helper to run the rewriter on a memory buffer
CUresult patch_and_load(cuModuleLoadDataEx_t original_func, CUmodule* module, const void* image, unsigned int numOptions, CUjit_option* options, void** optionValues) {
    std::lock_guard<std::mutex> lock(g_mutex);
    size_t size = get_elf_size(image);
    if (size == 0) return original_func(module, image, numOptions, options, optionValues);

    char tmp_in[] = "/tmp/orig_XXXXXX.cubin";
    char tmp_out[] = "/tmp/patched_XXXXXX.cubin";
    int fd_in = mkstemps(tmp_in, 6);
    int fd_out = mkstemps(tmp_out, 6);
    close(fd_out);

    ssize_t written = write(fd_in, image, size);
    close(fd_in);
    if (written < 0 || (size_t)written != size) {
        unlink(tmp_in);
        unlink(tmp_out);
        return original_func(module, image, numOptions, options, optionValues);
    }

    std::string cmd = "python3 rewriter.py " + std::string(tmp_in) + " " + std::string(tmp_out);
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

extern "C" CUresult cuModuleLoad(CUmodule* module, const char* fname) {
    std::ifstream ifs(fname, std::ios::binary | std::ios::ate);
    if (!ifs.is_open()) {
        static auto orig = (cuModuleLoad_t)dlsym(RTLD_NEXT, "cuModuleLoad");
        return orig(module, fname);
    }
    std::streamsize size = ifs.tellg();
    ifs.seekg(0, std::ios::beg);
    std::vector<char> buffer(size);
    ifs.read(buffer.data(), size);
    
    static auto orig_ex = (cuModuleLoadDataEx_t)dlsym(RTLD_NEXT, "cuModuleLoadDataEx");
    return patch_and_load(orig_ex, module, buffer.data(), 0, NULL, NULL);
}
