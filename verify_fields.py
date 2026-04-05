#!/usr/bin/env python3
import sys
import re

def decode_sm70(h1, h2):
    """Internal logic to extract fields from SM70 128-bit instruction."""
    opcode = h1 & 0xFFF
    pred = (h1 >> 9) & 0x7
    pred_inv = (h1 >> 12) & 0x1
    rd = (h1 >> 16) & 0xFF
    ra = (h1 >> 24) & 0xFF
    
    # Register-Register FFMA (0x223) vs Immediate FFMA (0x423)
    if opcode == 0x223:
        rb = (h1 >> 32) & 0xFF
        rc = h2 & 0xFF
        return f"FFMA R{rd}, R{ra}, R{rb}, R{rc}", pred, pred_inv
    elif opcode == 0x423:
        rb = h2 & 0xFF
        imm = (h1 >> 32) & 0xFFFFFFFF
        return f"FFMA R{rd}, R{ra}, R{rb}, 0x{imm:08x}", pred, pred_inv
    elif opcode == 0x220:
        rb = (h1 >> 32) & 0xFF
        return f"FMUL R{rd}, R{ra}, R{rb}", pred, pred_inv
    elif opcode == 0x221:
        ra_fadd = (h1 >> 24) & 0xFF
        rb_fadd = (h1 >> 32) & 0xFF
        return f"FADD R{rd}, R{ra_fadd}, R{rb_fadd}", pred, pred_inv
    
    return f"UNKNOWN(0x{opcode:03x})", pred, pred_inv

def run_test(cubin_path):
    import subprocess
    cmd = ["/usr/local/cuda-12.8/bin/nvdisasm", "-hex", cubin_path]
    raw = subprocess.run(cmd, capture_output=True, text=True).stdout
    
    lines = raw.splitlines()
    i = 0
    print(f"{'EXPECTED (ASM)':<40} | {'DECODED FROM HEX':<40} | RESULT")
    print("-" * 100)
    
    while i < len(lines):
        # nvdisasm prints H2 (control) then H1 (op)
        # /*0000*/  OP ARGS ; /* 0xH1 */
        #                      /* 0xH2 */
        m = re.search(r"/\*([0-9a-f]+)\*/\s+(?P<asm>[^;]+);\s+/\*\s+(?P<h1>0x[0-9a-f]+)\s+\*/", lines[i])
        if m:
            asm_expected = m.group('asm').strip()
            h1 = int(m.group('h1'), 16)
            i += 1
            h2_m = re.search(r"/\*\s+(?P<h2>0x[0-9a-f]+)\s+\*/", lines[i])
            if h2_m:
                h2 = int(h2_m.group('h2'), 16)
                
                # Only test instructions we care about
                if any(x in asm_expected for x in ["FFMA", "FMUL", "FADD"]):
                    decoded_asm, p, p_inv = decode_sm70(h1, h2)
                    p_str = f"@!P{p} " if p_inv else (f"@P{p} " if p != 7 else "")
                    full_decoded = p_str + decoded_asm
                    
                    # Fuzzy match (ignore .reuse, .reuse, spaces)
                    clean_exp = re.sub(r"\.\w+", "", asm_expected).replace(" ", "")
                    clean_dec = full_decoded.replace(" ", "")
                    
                    status = "OK" if clean_dec in clean_exp or clean_exp in clean_dec else "FAIL"
                    print(f"{asm_expected:<40} | {full_decoded:<40} | {status}")
        i += 1

if __name__ == "__main__":
    run_test("discovery.cubin")
