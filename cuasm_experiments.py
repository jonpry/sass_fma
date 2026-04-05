import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'CuAssembler'))

from CuAsm.CuInsParser import CuInsParser
from CuAsm.CuInsAssemblerRepos import CuInsAssemblerRepos

def get_info(asm_str):
    arch = 'sm_70'
    repo_path = os.path.join(os.getcwd(), 'CuAssembler/CuAsm/InsAsmRepos/DefaultInsAsmRepos.sm_70.txt')
    repo = CuInsAssemblerRepos(repo_path, arch=arch)
    code = repo.assemble(0, asm_str + " ;")
    h1 = code & 0xFFFFFFFFFFFFFFFF
    h2 = code >> 64
    return h1, h2

instrs = [
    "FMUL R0, R1, R2",
    "FMUL R0, R1.reuse, R2",
    "FMUL R0, R1, R2.reuse",
    "[W0] FMUL R0, R1, R2",
    "[B0] FMUL R0, R1, R2",
]

print(f"{'Instruction':<30} | {'h1':<16} | {'h2':<16}")
print("-" * 70)
for ins in instrs:
    try:
        h1, h2 = get_info(ins)
        print(f"{ins:<30} | {h1:016x} | {h2:016x}")
    except Exception as e:
        print(f"{ins:<30} | ERROR: {str(e)}")
