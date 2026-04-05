import os

with open('rewriter.py', 'r') as f:
    content = f.read()

# Define the NEW expansion logic for SM70 based on CuAsm
new_logic = """                if "FMA" in ins['op']:
                    # Common extraction
                    rd = (ins['h1'] >> 16) & 0xFF
                    ra = (ins['h1'] >> 24) & 0xFF
                    
                    # Preserve predication/scheduling (bits 9-15 of h1)
                    h1_meta = ins['h1'] & 0xFE00 
                    
                    # FFMA (Imm) opcode is 0x423 (bits 0-11)
                    is_imm = (ins['h1'] & 0xFFF) == 0x423
                    
                    if is_imm:
                        # FFMA (Imm) Rd, Ra, Rb, Imm
                        rb = ins['h2'] & 0xFF
                        imm_val = (ins['h1'] >> 32) & 0xFFFFFFFF
                        
                        temp_reg = rd
                        spare = next((r for r in range(2, 255) if r not in ins['live_out'] and r != rd and r != ra and r != rb), None)
                        if spare is not None: temp_reg = spare
                        else: self.max_reg += 1; temp_reg = self.max_reg

                        # 1. FMUL (Reg-Reg) R_temp, Ra, Rb
                        # h1: (rb<<32 | ra<<24 | rd<<16 | 0x7220)
                        fmul_h1 = (rb << 32) | (ra << 24) | (temp_reg << 16) | 0x7220 | h1_meta
                        # h2: Preserve control bits (41-63), set bit 22 (0x400000), clear others. Overwrite stall.
                        fmul_h2 = (ins['h2'] & 0xFFFFFE0000000000) | 0x00400000 | (0x08 << 41)
                        new_instrs.append({'h1':fmul_h1, 'h2':fmul_h2, 'op':'FMUL', 'old_pc':ins['pc']})

                        # 2. FADD (Reg-Imm) Rd, R_temp, Imm
                        # h1: (imm<<32 | ra<<24 | rd<<16 | 0x7421)
                        fadd_h1 = (imm_val << 32) | (temp_reg << 24) | (rd << 16) | 0x7421 | h1_meta
                        fadd_h2 = (ins['h2'] & 0xFFFFFE0000000000)
                        new_instrs.append({'h1':fadd_h1, 'h2':fadd_h2, 'op':'FADD', 'old_pc':None})
                    else:
                        # FFMA (Reg) Rd, Ra, Rb, Rc
                        rb = (ins['h1'] >> 32) & 0xFF
                        rc = ins['h2'] & 0xFF
                        
                        temp_reg = rd
                        if rd == rc:
                            spare = next((r for r in range(2, 255) if r not in ins['live_out'] and r != rd and r != ra and r != rb), None)
                            if spare is not None: temp_reg = spare
                            else: self.max_reg += 1; temp_reg = self.max_reg

                        # 1. FMUL (Reg-Reg) R_temp, Ra, Rb
                        fmul_h1 = (rb << 32) | (ra << 24) | (temp_reg << 16) | 0x7220 | h1_meta
                        fmul_h2 = (ins['h2'] & 0xFFFFFE0000000000) | 0x00400000 | (0x08 << 41)
                        new_instrs.append({'h1':fmul_h1, 'h2':fmul_h2, 'op':'FMUL', 'old_pc':ins['pc']})

                        # 2. FADD (Reg-Reg) Rd, Rc, R_temp
                        # h1: (rb<<32 | ra<<24 | rd<<16 | 0x7221)
                        fadd_h1 = (temp_reg << 32) | (rc << 24) | (rd << 16) | 0x7221 | h1_meta
                        fadd_h2 = (ins['h2'] & 0xFFFFFE0000000000)
                        new_instrs.append({'h1':fadd_h1, 'h2':fadd_h2, 'op':'FADD', 'old_pc':None})"""

# Find the loop and replace the body
start_marker = 'if "FMA" in ins[\'op\']:'
end_marker = 'self.sections[sn] = new_instrs'

# This is a bit brittle but we can use the indentation to find the end of the block
lines = content.splitlines()
new_lines = []
skip = False
for line in lines:
    if start_marker in line:
        new_lines.append(new_logic)
        skip = True
    elif end_marker in line:
        new_lines.append(line)
        skip = False
    elif not skip:
        new_lines.append(line)

with open('rewriter.py', 'w') as f:
    f.write('\\n'.join(new_lines))
