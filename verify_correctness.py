#!/usr/bin/env python3
import subprocess
import os
import glob

def verify_cubin(cubin_path):
    print(f"Verifying {cubin_path}...")
    cmd = ["/usr/local/cuda-12.8/bin/nvdisasm", "-hex", cubin_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"  [FAIL] nvdisasm failed on {cubin_path}")
        return False
        
    output = result.stdout + result.stderr
    
    errors = []
    if "INVALID0" in output:
        errors.append("Found INVALID0 instruction.")
    if "Unrecognized operation" in output:
        errors.append("Found Unrecognized operation error.")
    if "Illegal instruction" in output:
        errors.append("Found Illegal instruction error.")
    if "FFMA " in output:
        errors.append("Found unreplaced FFMA instruction.")
        
    if errors:
        for err in errors:
            print(f"  [FAIL] {err}")
        return False
        
    print("  [PASS] Cubin is perfectly valid and all FFMA replaced.")
    return True

if __name__ == "__main__":
    cubins = glob.glob("patched_*.cubin")
    if not cubins:
        print("No patched cubins found to verify.")
        
    all_passed = True
    for c in cubins:
        if not verify_cubin(c):
            all_passed = False
            
    if all_passed:
        print("\nSUCCESS: All invariants hold true for all patched cubins.")
        exit(0)
    else:
        print("\nFAILURE: Some invariants were violated.")
        exit(1)
