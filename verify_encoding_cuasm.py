import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'CuAssembler'))

from CuAsm.CuInsParser import CuInsParser
from CuAsm.CuSMVersion import CuSMVersion
from CuAsm.CuInsAssemblerRepos import CuInsAssemblerRepos

def get_encoding(asm_str, arch='sm_70'):
    cip = CuInsParser(arch)
    # res is (InsKey, InsVals, InsModifier)
    res = cip.parse(asm_str)
    
    repo_path = os.path.join(os.getcwd(), 'CuAssembler/CuAsm/InsAsmRepos/DefaultInsAsmRepos.sm_70.txt')
    repo = CuInsAssemblerRepos(repo_path, arch=arch)
    
    code = repo.assemble(0, asm_str)
    return code

# Test cases for FFMA split
tests = [
    "FMUL R11, R2, R5",
    "FADD R11, R6, R11",
    "FADD R7, R3, 5.0",
    "FMUL R0, R2, R5",
]

print(f"{'Instruction':<30} | {'128-bit Hex Encoding'}")
print("-" * 80)
for t in tests:
    try:
        code = get_encoding(t + " ;")
        if code:
            print(f"{t:<30} | {code:032x}")
    except Exception as e:
        print(f"{t:<30} | ERROR: {str(e)}")

