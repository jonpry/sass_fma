def print_diff(name, h1, h2):
    print(f"--- {name} ---")
    print(f"h1: {h1:064b}")
    print(f"h2: {h2:064b}")

# Good FMUL from expanded_discovery.cubin
# FMUL R11, R2, R5 | h1:00000005020b7220 | h2:004fc80000400000
print_diff("GOOD FMUL", 0x00000005020b7220, 0x004fc80000400000)

# Patched FMUL from patched_comprehensive.cubin (as seen in opcodes_dump.txt)
# /*00e0*/ FMUL.INVALID0 R7, R2, R0 ; /* 0x0000000002077220 */ /* 0x004e2200000000ff */
print_diff("PATCHED FMUL", 0x0000000002077220, 0x004e2200000000ff)
