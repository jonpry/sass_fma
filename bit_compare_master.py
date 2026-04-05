import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'CuAssembler'))

from CuAsm.CuInsParser import CuInsParser
from CuAsm.CuInsAssemblerRepos import CuInsAssemblerRepos

def get_code(asm_str):
    repo_path = os.path.join(os.getcwd(), 'CuAssembler/CuAsm/InsAsmRepos/DefaultInsAsmRepos.sm_70.txt')
    repo = CuInsAssemblerRepos(repo_path, arch='sm_70')
    code = repo.assemble(0, asm_str + " ;")
    return code

def print_bits(name, code):
    h1 = code & 0xFFFFFFFFFFFFFFFF
    h2 = code >> 64
    print(f"--- {name} ---")
    print(f"h1: {h1:016x} | {h1:064b}")
    print(f"h2: {h2:016x} | {h2:064b}")

# FFMA R13, R2, R5, 2
# CuAsm: h1: 40000000020d7423 | h2: 000fe40000000005
print_bits("FFMA IMM (GOOD)", get_code("FFMA R13, R2, R5, 2.0"))

# FMUL R63, R2, R5
print_bits("FMUL REG (GOOD)", get_code("FMUL R63, R2, R5"))

# FADD R13, R63, 2.0
print_bits("FADD IMM (GOOD)", get_code("FADD R13, R63, 2.0"))
