#!/bin/bash

# Define paths
NVCC=/usr/local/cuda-12.8/bin/nvcc
NVDISASM=/usr/local/cuda-12.8/bin/nvdisasm

# Ensure we have the library
if [ ! -f "interceptor.so" ]; then
    echo "Error: interceptor.so not found. Run ./build.sh first."
    exit 1
fi

echo "================================================"
echo "   STAGE 1: SM70 Dynamic Verification (HW)      "
echo "================================================"

echo "Running basic test_kernel with interceptor..."
LD_PRELOAD=./interceptor.so ./test_kernel

echo "------------------------------------------------"
echo "Running comprehensive_test with interceptor..."
LD_PRELOAD=./interceptor.so ./comprehensive_test

echo "------------------------------------------------"
echo "Running stress_test with interceptor..."
LD_PRELOAD=./interceptor.so ./stress_test

echo "------------------------------------------------"
echo "Running runtime_test (forced JIT) with interceptor..."
CUDA_FORCE_PTX_JIT=1 LD_PRELOAD=./interceptor.so ./runtime_test

echo ""
echo "================================================"
echo "   STAGE 2: SM80 Static Verification            "
echo "================================================"

verify_sm80() {
    local src=$1
    local name=$2
    local cubin="${name}_sm80.cubin"
    local patched="patched_${cubin}"
    
    echo "Testing $name for SM80..."
    $NVCC -arch=sm_80 -cubin "$src" -o "$cubin" 2>/dev/null
    if [ $? -ne 0 ]; then echo "  Compilation FAILED"; return 1; fi
    
    python3 rewriter.py "$cubin" "$patched" > /dev/null
    if [ $? -ne 0 ]; then echo "  Rewriting FAILED"; return 1; fi
    
    $NVDISASM -hex "$patched" > /dev/null 2>&1
    if [ $? -ne 0 ]; then
        echo "  Disassembly VERIFICATION FAILED"
        return 1
    fi
    
    echo "  SUCCESS: Structural and Disassembler Integrity Verified."
    rm "$cubin" "$patched"
}

verify_sm80 "discovery.cu" "basic"
verify_sm80 "comprehensive.cu" "comprehensive"
verify_sm80 "stress_test.cu" "stress"

echo "------------------------------------------------"
echo "All SM70 and SM80 tests completed."
