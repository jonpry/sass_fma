#include <iostream>
#include <cuda_runtime.h>

__global__ void discovery_kernel(float* a, float* b, float* c, float* d) {
    float x = a[0];
    float y = b[0];
    float z = c[0];

    // Force separate FMUL and FADD using intrinsics to prevent FMA merging
    float res_mul = __fmul_rn(x, y);
    float res_add = __fadd_rn(res_mul, z);
    
    d[0] = res_add;
}

int main() {
    float *d_a, *d_b, *d_c, *d_d;
    cudaMalloc(&d_a, 4); cudaMalloc(&d_b, 4); cudaMalloc(&d_c, 4); cudaMalloc(&d_d, 4);
    discovery_kernel<<<1, 1>>>(d_a, d_b, d_c, d_d);
    cudaDeviceSynchronize();
    return 0;
}
