#include <cuda_runtime.h>

__global__ void spill_kernel(float* d_out, float a, float b, int idx) {
    // Making it volatile and using a dynamic index prevents optimization
    volatile float large_stack[128];
    for(int i=0; i<128; i++) large_stack[i] = a + (float)i;
    
    // Force a spill/restore pattern by using many registers then accessing stack
    float v1 = a * b;
    float v2 = v1 + a;
    float v3 = v2 * b;
    
    float val = large_stack[idx % 128];
    d_out[0] = val + v3;
}

int main() {
    float *d_out;
    cudaMalloc(&d_out, 4);
    spill_kernel<<<1, 1>>>(d_out, 1.0f, 2.0f, 10);
    cudaDeviceSynchronize();
    return 0;
}
