CC=g++
CFLAGS=-fPIC -shared
LDFLAGS=-ldl
CUDA_PATH=/usr/local/cuda

all: interceptor.so

interceptor.so: interceptor.cpp
	$(CC) $(CFLAGS) -I$(CUDA_PATH)/include interceptor.cpp -o interceptor.so $(LDFLAGS)

clean:
	rm -f interceptor.so
