import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'CuAssembler'))

from CuAsm.CuInsAssemblerRepos import CuInsAssemblerRepos
from CuAsm.CuSMVersion import CuSMVersion

def check_code(h1, h2):
    code = (h2 << 64) | h1
    repo_path = os.path.join(os.getcwd(), 'CuAssembler/CuAsm/InsAsmRepos/DefaultInsAsmRepos.sm_70.txt')
    repo = CuInsAssemblerRepos(repo_path, arch='sm_70')
    
    # We can't easily disassemble a raw code without a feeder, 
    # but we can check if it matches any known InsKey.
    for key, assembler in repo.items():
        # buildInsValVec would be needed, but we can just check buildCode 
        # if we knew the vals.
        pass
    
    # Let's try to see if CuAsm can handle the code
    from CuAsm.CuControlCode import CuControlCode
    ctrl = (h2 >> 41) & 0x1FFFF
    print(f"Control: {CuControlCode.decode(ctrl)}")

# My "broken" FADD from Turn 45
h1_fadd = 0x40000000030d7421
h2_fadd = 0x0c8fe40000000000
check_code(h1_fadd, h2_fadd)

# Let's see if there are any bits in h2 (0-40) that are non-zero
print(f"h2 bits 0-40: {h2_fadd & 0x1FFFFFFFFFF:x}")
