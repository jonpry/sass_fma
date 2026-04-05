import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'CuAssembler'))

from CuAsm.CuControlCode import CuControlCode

def decode_ctrl(h2):
    ctrl_int = (h2 >> 41) & 0x1FFFF
    return CuControlCode.decode(ctrl_int)

# Original FFMA from test_switch branch 1
# 0110 | FFMA R7, R2, R5, 5 | h1:40a0000002077423 | h2:004fe20000000005
h2_orig = 0x004fe20000000005
print(f"Original FFMA Control: {decode_ctrl(h2_orig)}")

# My FMUL
# 00e0 | FMUL R3, R2, R5 | h1:0000000502037220 | h2:004fe20000400000
h2_fmul = 0x004fe20000400000
print(f"My FMUL Control:       {decode_ctrl(h2_fmul)}")

# My FADD
# 00f0 | FADD R7, R3, 5 | h1:40a0000003077421 | h2:004fe20000000000
h2_fadd = 0x004fe20000000000
print(f"My FADD Control:       {decode_ctrl(h2_fadd)}")

# LDG instructions from test_switch
print(f"LDG R2 Control:        {decode_ctrl(0x000ea800001ee900)}")
print(f"LDG R5 Control:        {decode_ctrl(0x000ea400001ee900)}")
