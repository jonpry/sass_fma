#!/bin/bash

# Ensure we have the library
if [ ! -f "interceptor.so" ]; then
    echo "Error: interceptor.so not found. Run ./build.sh first."
    exit 1
fi

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
