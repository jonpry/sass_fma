#include <iostream>
#include <vector>
#include <fstream>
#include <cuda.h>

#define CHECK_CUDA(call) \
    do { \
        CUresult res = call; \
        if (res != CUDA_SUCCESS) { \
            const char* err_str; \
            cuGetErrorString(res, &err_str); \
            std::cerr << "CUDA Error: " << err_str << " at line " << __LINE__ << std::endl; \
            exit(1); \
        } \
    } while (0)

typedef void (*device_func_ptr)(float*, float*, float*, float*);

__device__ void func_a(float* a, float* b, float* c, float* d) { d[0] = a[0] * b[0] + 1.0f; }
__device__ void func_b(float* a, float* b, float* c, float* d) { d[0] = a[0] * b[0] + 2.0f; }

// 1. Indirect Calls (Function Pointers)
__global__ void test_indirect_call(float* a, float* b, float* c, float* d, int selector) {
    device_func_ptr funcs[] = { func_a, func_b };
    funcs[selector % 2](a, b, c, d);
}

// 2. Massive Expansion (1024 FMAs)
__global__ void test_massive_expansion(float* a, float* b, float* c, float* d) {
    float val = c[0];
    float x = a[0];
    float y = b[0];
    
    #pragma unroll
    for(int i=0; i<1024; i++) {
        val = x * y + val;
    }
    d[0] = val;
}

// 3. Register Saturation (Forces R250+)
__global__ void test_register_saturation(float* a, float* b, float* c, float* d) {
    float regs[250];
    #pragma unroll
    for(int i=0; i<250; i++) regs[i] = a[0] + (float)i;
    
    // Force many FMAs using these registers
    float sum = 0;
    #pragma unroll
    for(int i=0; i<250; i++) sum = regs[i] * b[0] + sum;
    
    d[0] = sum;
}

int main() {
    CHECK_CUDA(cuInit(0));
    CUdevice dev;
    CHECK_CUDA(cuDeviceGet(&dev, 0));
    CUcontext ctx;
    CHECK_CUDA(cuCtxCreate(&ctx, 0, dev));

    std::ifstream ifs("stress.cubin", std::ios::binary | std::ios::ate);
    if (!ifs.is_open()) {
        std::cerr << "Error: stress.cubin not found. Run ./build.sh first." << std::endl;
        return 1;
    }
    std::streamsize size = ifs.tellg();
    ifs.seekg(0, std::ios::beg);
    std::vector<char> buffer(size);
    ifs.read(buffer.data(), size);

    CUmodule module;
    CHECK_CUDA(cuModuleLoadDataEx(&module, buffer.data(), 0, NULL, NULL));

    // Run Massive Expansion
    float h_a=1.0001f, h_b=1.0001f, h_c=0.0f, h_d=0.0f;
    CUdeviceptr d_a, d_b, d_c, d_d;
    cuMemAlloc(&d_a, 4); cuMemAlloc(&d_b, 4); cuMemAlloc(&d_c, 4); cuMemAlloc(&d_d, 4);
    cuMemcpyHtoD(d_a, &h_a, 4); cuMemcpyHtoD(d_b, &h_b, 4); cuMemcpyHtoD(d_c, &h_c, 4);

    CUfunction f_mass;
    cuModuleGetFunction(&f_mass, module, "_Z22test_massive_expansionPfS_S_S_");
    void* args[] = { &d_a, &d_b, &d_c, &d_d };
    CHECK_CUDA(cuLaunchKernel(f_mass, 1, 1, 1, 1, 1, 1, 0, NULL, args, NULL));
    cuCtxSynchronize();
    cuMemcpyDtoH(&h_d, d_d, 4);
    std::cout << "[Stress] Massive Expansion: DONE (Result: " << h_d << ")" << std::endl;

    // Run Indirect Call
    CUfunction f_ind;
    int selector = 1;
    cuModuleGetFunction(&f_ind, module, "_Z18test_indirect_callPfS_S_S_i");
    void* args2[] = { &d_a, &d_b, &d_c, &d_d, &selector };
    CHECK_CUDA(cuLaunchKernel(f_ind, 1, 1, 1, 1, 1, 1, 0, NULL, args2, NULL));
    cuCtxSynchronize();
    cuMemcpyDtoH(&h_d, d_d, 4);
    std::cout << "[Stress] Indirect Call (Case 1): " << (h_d > 2.0f ? "PASS" : "FAIL") << " (Result: " << h_d << ")" << std::endl;

    return 0;
}
