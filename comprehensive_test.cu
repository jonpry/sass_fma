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

void run_test(CUmodule module, const char* name, float a_val, float b_val, float c_val, float expected) {
    CUfunction func;
    CHECK_CUDA(cuModuleGetFunction(&func, module, name));

    float h_a = a_val, h_b = b_val, h_c = c_val, h_d = 0;
    CUdeviceptr d_a, d_b, d_c, d_d;

    CHECK_CUDA(cuMemAlloc(&d_a, 4));
    CHECK_CUDA(cuMemAlloc(&d_b, 4));
    CHECK_CUDA(cuMemAlloc(&d_c, 4));
    CHECK_CUDA(cuMemAlloc(&d_d, 4));

    CHECK_CUDA(cuMemcpyHtoD(d_a, &h_a, 4));
    CHECK_CUDA(cuMemcpyHtoD(d_b, &h_b, 4));
    CHECK_CUDA(cuMemcpyHtoD(d_c, &h_c, 4));

    void* args[] = { &d_a, &d_b, &d_c, &d_d };
    CHECK_CUDA(cuLaunchKernel(func, 1, 1, 1, 1, 1, 1, 0, NULL, args, NULL));
    CHECK_CUDA(cuCtxSynchronize());

    CHECK_CUDA(cuMemcpyDtoH(&h_d, d_d, 4));

    bool pass = (h_d == expected);
    std::cout << "[Test] " << name << ": " << (pass ? "PASS" : "FAILURE") 
              << " (Got " << h_d << ", Expected " << expected << ")" << std::endl;

    cuMemFree(d_a); cuMemFree(d_b); cuMemFree(d_c); cuMemFree(d_d);
}

int main() {
    CHECK_CUDA(cuInit(0));
    CUdevice dev;
    CHECK_CUDA(cuDeviceGet(&dev, 0));
    CUcontext ctx;
    CHECK_CUDA(cuCtxCreate(&ctx, 0, dev));

    // Load the cubin (Interceptor will hook this)
    std::ifstream ifs("comprehensive.cubin", std::ios::binary | std::ios::ate);
    std::streamsize size = ifs.tellg();
    ifs.seekg(0, std::ios::beg);
    std::vector<char> buffer(size);
    ifs.read(buffer.data(), size);

    CUmodule module;
    CHECK_CUDA(cuModuleLoadDataEx(&module, buffer.data(), 0, NULL, NULL));

    // 1. Test Accumulator (R_dest == R_srcC)
    run_test(module, "_Z16test_accumulatorPfS_S_S_", 2.0f, 3.0f, 4.0f, 10.0f);

    // 2. Test Predication
    run_test(module, "_Z15test_predicatedPfS_S_S_", 2.0f, 3.0f, 4.0f, 10.0f); // if(true)
    run_test(module, "_Z15test_predicatedPfS_S_S_", 0.5f, 3.0f, 4.0f, 0.0f);  // if(false)

    // 3. Test Loop (Relative Branches)
    run_test(module, "_Z9test_loopPfS_S_S_", 2.0f, 1.0f, 0.0f, 10.0f);

    // 4. Test Switch (Jump Tables)
    run_test(module, "_Z11test_switchPfS_S_S_", 2.0f, 3.0f, 1.0f, 10.0f); // Case 1: a*b+4
    run_test(module, "_Z11test_switchPfS_S_S_", 2.0f, 3.0f, 2.0f, 11.0f); // Case 2: a*b+5

    return 0;
}
