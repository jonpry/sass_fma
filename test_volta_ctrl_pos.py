import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'CuAssembler'))

from CuAsm.CuInsAssemblerRepos import CuInsAssemblerRepos

def get_code(asm_str):
    arch = 'sm_70'
    repo_path = os.path.join(os.getcwd(), 'CuAssembler/CuAsm/InsAsmRepos/DefaultInsAsmRepos.sm_70.txt')
    repo = CuInsAssemblerRepos(repo_path, arch=arch)
    return repo.assemble(0, asm_str + " ;")

code1 = get_code("FMUL R0, R1, R2")
code2 = get_code("{B0:W0:S01} FMUL R0, R1, R2")

print(f"Code 1: 0x{code1:032x}")
print(f"Code 2: 0x{code2:032x}")
diff = code1 ^ code2
print(f"Diff:   0x{diff:032x}")
