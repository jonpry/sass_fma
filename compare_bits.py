import re
import subprocess

cmd = ["/usr/local/cuda-12.8/bin/nvdisasm", "-hex", "patched_discovery.cubin"]
raw = subprocess.run(cmd, capture_output=True, text=True).stdout
lines = raw.splitlines()
i = 0
while i < len(lines):
    if "/*00e0" in lines[i] or "/*00f0" in lines[i]:
        print(lines[i-1])
        print(lines[i])
    i += 1
