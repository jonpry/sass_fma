# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SASS FMA Bypass Tool — a SASS-level binary translator for NVIDIA GPUs (Volta sm_70 / Ampere sm_80) that intercepts CUDA module loading via `LD_PRELOAD` and rewrites defective `FFMA` instructions into `FMUL` + `FADD` sequences. Targets hardware where the fused multiply-add unit is physically defective.

## Build and Test

```bash
# Build everything (interceptor.so + all test executables + cubin/sass artifacts)
./build.sh

# Run all test suites (basic, comprehensive, stress, runtime JIT)
./run_test.sh

# Use with any CUDA application
CUDA_FORCE_PTX_JIT=1 LD_PRELOAD=./interceptor.so ./your_cuda_app
```

Requires: CUDA Toolkit (`nvcc`, `nvdisasm`), Python 3, g++. The Makefile only builds `interceptor.so`; `build.sh` also compiles all CUDA test binaries with `nvcc -arch=sm_70`.

## Architecture

Two-layer design:

1. **`interceptor.cpp`** — C++ shared library loaded via `LD_PRELOAD`. Hooks `cuModuleLoadDataEx`, `cuModuleLoadData`, `cuModuleLoad`, and `__cudaRegisterFatBinary`. On each cubin load, writes the binary to a temp file, spawns `python3 rewriter.py`, and loads the patched result. Thread-safe via mutex.

2. **`rewriter.py`** — Python engine that performs the actual transformation:
   - Disassembles cubin via `nvdisasm -hex`, auto-detects sm_70 vs sm_80
   - Parses SASS into per-kernel sections (`.text.<kernel_name>`)
   - Builds CFG and runs iterative backward liveness analysis to find dead registers for use as temporaries
   - Splits each `FFMA` into `FMUL` + `FADD`, preserving predicates and scoreboard barriers
   - Manually expands the ELF `.text` sections and shifts all section/program headers
   - Patches `.nv.info` metadata (REGCOUNT) and jump table offsets in `.nv.constant*` sections
   - Updates branch targets (BRA/SSY/PBK) using a `pc_map` of old-to-new PC values

## Key Invariants

- Instructions are 128-bit (16 bytes each). All PC values are multiples of 16.
- FFMA splitting doubles instruction count for each FMA — the ELF must physically grow.
- When `r_dest == r_srcC` in an FFMA, a spare register is required (found via liveness or by incrementing `max_reg`).
- Jump table entries in `.nv.constant*` are only patched if they match known PC values (verified via BRX/LDC tracing to avoid corrupting float literals).
- The symtab (SHT_SYMTAB, type 11) function symbol sizes are updated to reflect expanded `.text` sections.

## Test Suites

- `test_kernel.cu` — Basic FMA test
- `comprehensive.cu` / `comprehensive_test.cu` — Accumulator aliasing, predicated FMAs, loops with backward branches, switch/jump tables
- `stress_test.cu` — 1024-FMA unrolled expansion, register saturation (250+ regs)
- `runtime_test.cu` — Runtime JIT path via `CUDA_FORCE_PTX_JIT=1`
