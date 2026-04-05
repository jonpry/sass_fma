import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'CuAssembler'))
from CuAsm.CuInsAssemblerRepos import CuInsAssemblerRepos

def get_code(asm_str):
    repo_path = os.path.join(os.getcwd(), 'CuAssembler/CuAsm/InsAsmRepos/DefaultInsAsmRepos.sm_70.txt')
    repo = CuInsAssemblerRepos(repo_path, arch='sm_70')
    code = repo.assemble(0, asm_str + " ;")
    return code

# Base instruction: B------:R-:W-:Y:S01
c1 = get_code("MOV R1, R1")
# With Write Scoreboard 0: B------:R-:W0:Y:S01
c2 = get_code("[W0] MOV R1, R1")
# With Wait on Scoreboard 0: B0-----:R-:W-:Y:S01
c3 = get_code("B0 MOV R1, R1")

h2_1 = c1 >> 64
h2_2 = c2 >> 64
h2_3 = c3 >> 64

print(f"Base h2: {h2_1:016x}")
print(f"W0   h2: {h2_2:016x} (diff: {h2_2^h2_1:016x})")
print(f"B0   h2: {h2_3:016x} (diff: {h2_3^h2_1:016x})")
