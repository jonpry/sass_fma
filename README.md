# SASS FMA Bypass Tool

Created by Jon Pry.

A high-performance, SASS-level binary translator for NVIDIA GPUs designed to bypass hardware defects by rewriting Streaming Multiprocessor Assembly (SASS) on-the-fly.

## Overview

This tool was developed to rescue GPU hardware (specifically NVIDIA Volta/Ampere) where the fused multiply-add (`FFMA`) instruction is defective. It intercepts CUDA module loading at the Driver API level and surgically replaces every `FFMA` with a functionally equivalent `FMUL` followed by an `FADD`.

### Key Features

*   **Zero Performance Overhead**: Uses direct instruction insertion (manual ELF shifting) to maintain native execution speed.
*   **Production-Grade Analysis**: Implements full **Control Flow Graph (CFG)** construction and **Iterative Liveness Analysis** to safely find spare registers.
*   **Multi-Kernel Support**: Correctly handles cubins containing multiple kernels through kernel-aware metadata patching.
*   **Safe Jump Table Tracing**: Uses symbolic tracing to patch `switch` statements in constant memory without corrupting mathematical literals.
*   **Architecture Aware**: Automatically detects and supports **sm_70 (Volta)** and **sm_80 (Ampere)**.
*   **Thread Safe**: Supports concurrent kernel loading in multi-threaded applications.

## Architecture

1.  **`interceptor.so`**: A C++ shared library designed for `LD_PRELOAD`. It hooks `cuModuleLoadDataEx` and related functions to capture `.cubin` files before they are loaded.
2.  **`rewriter.py`**: A Python 3 engine that disassembles the binary, maps out the entire PC space, performs the instruction split, and manually shifts the ELF headers and sections.

## Prerequisites

*   CUDA Toolkit (nvcc, nvdisasm)
*   Python 3.x
*   C++ Compiler (g++)

## Installation

1.  Clone the repository.
2.  Install Python dependencies:
    ```bash
    pip install -r requirements.txt
    ```
3.  Build the interceptor:
    ```bash
    ./build.sh
    ```

## Usage

To apply the bypass to any CUDA application, simply prefix the command with the interceptor and force PTX JIT to ensure all kernels are captured:

```bash
export CUDA_FORCE_PTX_JIT=1
LD_PRELOAD=./interceptor.so ./your_cuda_application
```

## Running Tests

The project includes a comprehensive test suite covering accumulators, predication, loops, and large-scale expansion:

```bash
./run_test.sh
```

## License
MIT
