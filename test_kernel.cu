#include <iostream>
#include <vector>
#include <fstream>
#include <cuda.h>
#include <cuda_runtime.h>

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

int main() {
    int n = 1024;

    // 1. Initialize Driver API
    CHECK_CUDA(cuInit(0));
    CUdevice device;
    CHECK_CUDA(cuDeviceGet(&device, 0));
    CUcontext context;
    CHECK_CUDA(cuCtxCreate(&context, 0, device));

    // 2. Load the CUBIN (The interceptor will hook this)
    // We expect discovery.cubin to exist after ./build.sh
    std::ifstream ifs("discovery.cubin", std::ios::binary | std::ios::ate);
    if (!ifs.is_open()) {
        std::cerr << "Error: discovery.cubin not found. Run ./build.sh first." << std::endl;
        return 1;
    }
    std::streamsize cubin_size = ifs.tellg();
    ifs.seekg(0, std::ios::beg);
    std::vector<char> cubin_data(cubin_size);
    ifs.read(cubin_data.data(), cubin_size);

    CUmodule module;
    // THIS IS THE HOOK POINT
    CHECK_CUDA(cuModuleLoadDataEx(&module, cubin_data.data(), 0, NULL, NULL));

    CUfunction function;
    CHECK_CUDA(cuModuleGetFunction(&function, module, "_Z16discovery_kernelPfS_S_S_"));

    // 3. Setup Data
    std::vector<float> h_a(1, 2.0f), h_b(1, 3.0f), h_c(1, 4.0f), h_d(9, 0.0f);
    CUdeviceptr d_a, d_b, d_c, d_d;

    CHECK_CUDA(cuMemAlloc(&d_a, sizeof(float)));
    CHECK_CUDA(cuMemAlloc(&d_b, sizeof(float)));
    CHECK_CUDA(cuMemAlloc(&d_c, sizeof(float)));
    CHECK_CUDA(cuMemAlloc(&d_d, 9 * sizeof(float)));

    CHECK_CUDA(cuMemcpyHtoD(d_a, h_a.data(), sizeof(float)));
    CHECK_CUDA(cuMemcpyHtoD(d_b, h_b.data(), sizeof(float)));
    CHECK_CUDA(cuMemcpyHtoD(d_c, h_c.data(), sizeof(float)));

    // 4. Launch
    void* args[] = { &d_a, &d_b, &d_c, &d_d };
    CHECK_CUDA(cuLaunchKernel(function, 1, 1, 1, 1, 1, 1, 0, NULL, args, NULL));
    CHECK_CUDA(cuCtxSynchronize());

    // 5. Verify
    CHECK_CUDA(cuMemcpyDtoH(h_d.data(), d_d, 9 * sizeof(float)));
    std::cout << "Result: " << (h_d[6] == 10.0f ? "SUCCESS" : "FAILURE") << " (Got " << h_d[6] << ")" << std::endl;

    return 0;
}
