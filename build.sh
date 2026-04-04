#!/bin/bash
set -e

NVCC=/usr/local/cuda/bin/nvcc
ARCH=sm_70

echo "Compiling interceptor.so..."
make all

echo "Compiling test_kernel..."
$NVCC -arch=$ARCH test_kernel.cu -o test_kernel -lcuda

echo "Compiling discovery_kernel..."
$NVCC -arch=$ARCH discovery.cu -o discovery_kernel -lcuda

echo "Extracting discovery cubin..."
# Compile to cubin for easier disassembly
$NVCC -arch=$ARCH -cubin discovery.cu -o discovery.cubin

echo "Dumping discovery SASS..."
/usr/local/cuda/bin/nvdisasm -hex discovery.cubin > discovery.sass

echo "Compiling comprehensive test suite..."
$NVCC -arch=$ARCH comprehensive_test.cu -o comprehensive_test -lcuda
$NVCC -arch=$ARCH -cubin comprehensive.cu -o comprehensive.cubin

echo "Compiling stress test suite..."
$NVCC -arch=$ARCH stress_test.cu -o stress_test -lcuda
$NVCC -arch=$ARCH -cubin stress_test.cu -o stress.cubin # Note: Compiling the kernels in stress_test.cu

echo "Compiling runtime_test suite..."
$NVCC -arch=$ARCH runtime_test.cu -o runtime_test

echo "Build complete."
