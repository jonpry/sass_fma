import re
import subprocess

cmd = ["/usr/local/cuda-12.8/bin/nvdisasm", "-hex", "patched_discovery.cubin"]
raw = subprocess.run(cmd, capture_output=True, text=True).stdout
lines = raw.splitlines()
for line in lines:
    if "/*00" in line or "/*01" in line or "nvdisasm" in line:
        print(line)
