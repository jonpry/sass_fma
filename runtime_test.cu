#include <iostream>
#include <cuda_runtime.h>

__global__ void runtime_kernel(float* d_out, float a, float b, float c) {
    // This will compile to FFMA. We want to see it intercepted.
    d_out[0] = a * b + c;
}

int main() {
    float *d_out;
    cudaMalloc(&d_out, 4);
    
    std::cout << "[Runtime Test] Launching kernel using <<< >>> syntax..." << std::endl;
    runtime_kernel<<<1, 1>>>(d_out, 2.0f, 3.0f, 4.0f);
    
    float h_out = 0;
    cudaMemcpy(&h_out, d_out, 4, cudaMemcpyDeviceToHost);
    
    if (h_out == 10.0f) {
        std::cout << "Result: SUCCESS (Got " << h_out << ")" << std::endl;
    } else {
        std::cout << "Result: FAILURE (Got " << h_out << ")" << std::endl;
    }
    
    cudaFree(d_out);
    return 0;
}
