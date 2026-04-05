#include <cuda_runtime.h>

__global__ void discovery_kernel(float* a, float* b, float* c, float* d) {
    float x = a[0];
    float y = b[0];
    float z = c[0];
    float out;
    int pred_val = (x > 0);

    // 1. FMUL variants
    asm ("mul.rn.f32 %0, %1, %2;" : "=f"(out) : "f"(x), "f"(y)); d[0] = out;
    asm ("mul.rn.f32 %0, %1, 2.0;" : "=f"(out) : "f"(x)); d[1] = out;
    asm ("{ .reg .pred %%p1; setp.ne.s32 %%p1, %1, 0; @%%p1 mul.rn.f32 %0, %2, %3; }" : "=f"(out) : "r"(pred_val), "f"(x), "f"(y)); d[2] = out;

    // 2. FADD variants
    asm ("add.rn.f32 %0, %1, %2;" : "=f"(out) : "f"(x), "f"(z)); d[3] = out;
    asm ("add.rn.f32 %0, %1, 4.0;" : "=f"(out) : "f"(x)); d[4] = out;
    asm ("{ .reg .pred %%p1; setp.ne.s32 %%p1, %1, 0; @%%p1 add.rn.f32 %0, %2, %3; }" : "=f"(out) : "r"(pred_val), "f"(x), "f"(z)); d[5] = out;

    // 3. FFMA variants (to compare)
    asm ("fma.rn.f32 %0, %1, %2, %3;" : "=f"(out) : "f"(x), "f"(y), "f"(z)); d[6] = out;
    asm ("fma.rn.f32 %0, %1, %2, 5.0;" : "=f"(out) : "f"(x), "f"(y)); d[7] = out;
    asm ("{ .reg .pred %%p1; setp.ne.s32 %%p1, %1, 0; @%%p1 fma.rn.f32 %0, %2, %3, %4; }" : "=f"(out) : "r"(pred_val), "f"(x), "f"(y), "f"(z)); d[8] = out;
}

int main() { return 0; }
