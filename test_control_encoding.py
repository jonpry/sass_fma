import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'CuAssembler'))

from CuAsm.CuControlCode import CuControlCode

def test_ctrl(s):
    try:
        code = CuControlCode.encode(s)
        print(f"{s:<20} | 0x{code:06x}")
    except Exception as e:
        print(f"{s:<20} | ERROR: {e}")

print(f"{'Control String':<20} | {'Encoded (24-bit)':<16}")
print("-" * 40)
test_ctrl("B------:R-:W-:Y:S01")
test_ctrl("B------:R-:W0:-:S01")
test_ctrl("B------:R0:W-:-:S01")
test_ctrl("B0-----:R-:W-:-:S01")
test_ctrl("B-1----:R-:W-:-:S01")
test_ctrl("B----5-:R-:W-:-:S01")
