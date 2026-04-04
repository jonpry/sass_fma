#include <cuda_runtime.h>

// 1. Accumulator: Force R_dest == R_srcC
__global__ void test_accumulator(float* a, float* b, float* c, float* d) {
    float x = a[0];
    float y = b[0];
    float z = c[0];
    // This often compiles to FFMA R1, R2, R3, R1
    z = x * y + z;
    d[0] = z;
}

// 2. Predication
__global__ void test_predicated(float* a, float* b, float* c, float* d) {
    float x = a[0];
    float y = b[0];
    float z = c[0];
    float res = 0;
    // Condition that results in predicated FFMA
    if (x > 1.0f) {
        res = x * y + z;
    }
    d[0] = res;
}

// 3. Loop (Backward Branches)
__global__ void test_loop(float* a, float* b, float* c, float* d) {
    float val = 0;
    for(int i = 0; i < 5; i++) {
        val = a[0] * b[0] + val;
    }
    d[0] = val;
}

// 4. Switch (Jump Tables)
__global__ void test_switch(float* a, float* b, float* c, float* d) {
    int choice = (int)c[0];
    float res = 0;
    switch(choice) {
        case 1: res = a[0] * b[0] + 4.0f; break;
        case 2: res = a[0] * b[0] + 5.0f; break;
        default: res = 0; break;
    }
    d[0] = res;
}
