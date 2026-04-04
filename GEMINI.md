# Project: sass_fma
A high-performance, SASS-level binary translator for NVIDIA GPUs (sm_70/sm_80) designed to bypass hardware defects by rewriting Streaming Multiprocessor Assembly on-the-fly.

## Technical Stack
- **Languages:** C++ (Interceptor), Python 3.10 (Rewriter)
- **APIs:** CUDA Driver API, ELF Binary Manipulation
- **Architectures:** Volta (sm_70), Ampere (sm_80)

## Final Architecture
The tool uses a **Direct Insertion (Manual ELF Shifting)** strategy to achieve zero execution overhead:

1. **`interceptor.so`**: A thread-safe C++ shared library that hooks `cuModuleLoadDataEx`. It creates unique temporary files for concurrent kernel loads and manages clean-up.
2. **`rewriter.py`**: A Python 3.10 engine that:
   - **In-place Splitting**: Replaces `FFMA` with a `FMUL` + `FADD` sequence directly in the `.text` section.
   - **Manual ELF Shifting**: Physically expands the ELF file and manually updates the Section Header and Program Header tables to account for code growth.
   - **Kernel-Aware Patching**: Links kernels to their specific metadata (`.nv.info`) and constant sections to resolve branch and jump-table offsets without collisions.
   - **Local Liveness Analysis**: Builds a Control Flow Graph (CFG) and performs backward data-flow analysis to identify **dead registers** at each instruction. This allows the tool to repurpose registers for FMUL+FADD splits even in kernels with high register pressure.
   - **Dynamic Metadata Update**: Automatically updates the hardware `REGCOUNT` if a new physical register is required.
   - **Synchronization**: Injects hardware scoreboard barriers to ensure data dependency integrity between the new FMUL and FADD ops.

## Build and Execute
### 1. Build
```bash
./build.sh
```

### 2. Run Tests
```bash
./run_test.sh
```
This runs the basic test, the comprehensive suite (Accumulator, Predication, Loops, and Switch), and the **Mega-Stress Suite** (Massive Expansion and Register Saturation).

### 3. Usage in Applications
```bash
LD_PRELOAD=./interceptor.so ./your_cuda_application
```

## Development Status
- **Verified on sm_70:** All tests (Basic, Comprehensive, and Stress) pass.
- **Performance:** Native speed (zero-overhead direct insertion).
- **Safety:** Instruction-aware tracing and liveness analysis prevent corruption of mathematical constants and register states.
