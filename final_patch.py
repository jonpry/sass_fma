import re

with open('rewriter.py', 'r') as f:
    content = f.read()

replacement = """        for sn, instrs in self.sections.items():
            self.solve_liveness(instrs)
            new_instrs = []
            for ins in instrs:
                self.pc_map[(sn, ins['pc'])] = len(new_instrs) * 16
                if "FMA" in ins['op']:
                    rd = (ins['h1'] >> 16) & 0xFF
                    ra = (ins['h1'] >> 24) & 0xFF
                    h1_meta = ins['h1'] & 0xF000 
                    is_imm = (ins['h1'] & 0xFFF) == 0x423
                    
                    if is_imm:
                        rb = ins['h2'] & 0xFF
                        imm_val = (ins['h1'] >> 32) & 0xFFFFFFFF
                        temp_reg = rd
                        spare = next((r for r in range(2, 255) if r not in ins['live_out'] and r != rd and r != ra and r != rb), None)
                        if spare is not None: temp_reg = spare
                        else: self.max_reg += 1; temp_reg = self.max_reg

                        # 1. FMUL (Reg-Reg) R_temp, Ra, Rb
                        fmul_h1 = (rb << 32) | (ra << 24) | (temp_reg << 16) | 0x220 | h1_meta
                        fmul_h2 = (ins['h2'] & 0xFFFFFE0000000000) | 0x00400000 | (0x08 << 41)
                        new_instrs.append({'h1':fmul_h1, 'h2':fmul_h2, 'op':'FMUL', 'old_pc':ins['pc']})

                        # 2. FADD (Reg-Imm) Rd, R_temp, Imm
                        fadd_h1 = (imm_val << 32) | (temp_reg << 24) | (rd << 16) | 0x221 | h1_meta
                        fadd_h2 = (ins['h2'] & 0xFFFFFE0000000000)
                        new_instrs.append({'h1':fadd_h1, 'h2':fadd_h2, 'op':'FADD', 'old_pc':None})
                    else:
                        rb = (ins['h1'] >> 32) & 0xFF
                        rc = ins['h2'] & 0xFF
                        temp_reg = rd
                        if rd == rc:
                            spare = next((r for r in range(2, 255) if r not in ins['live_out'] and r != rd and r != ra and r != rb), None)
                            if spare is not None: temp_reg = spare
                            else: self.max_reg += 1; temp_reg = self.max_reg

                        # 1. FMUL (Reg-Reg) R_temp, Ra, Rb
                        fmul_h1 = (rb << 32) | (ra << 24) | (temp_reg << 16) | 0x220 | h1_meta
                        fmul_h2 = (ins['h2'] & 0xFFFFFE0000000000) | 0x00400000 | (0x08 << 41)
                        new_instrs.append({'h1':fmul_h1, 'h2':fmul_h2, 'op':'FMUL', 'old_pc':ins['pc']})

                        # 2. FADD (Reg-Reg) Rd, Rc, R_temp
                        fadd_h1 = (temp_reg << 32) | (rc << 24) | (rd << 16) | 0x221 | h1_meta
                        fadd_h2 = (ins['h2'] & 0xFFFFFE0000000000)
                        new_instrs.append({'h1':fadd_h1, 'h2':fadd_h2, 'op':'FADD', 'old_pc':None})
                else:
                    new_instrs.append({'h1':ins['h1'], 'h2':ins['h2'], 'op':ins['op'], 'old_pc':ins['pc']})
            self.sections[sn] = new_instrs"""

pattern_loop = r'        for sn, instrs in self\.sections\.items\(\):.*?            self\.sections\[sn\] = new_instrs'
content = re.sub(pattern_loop, replacement, content, flags=re.DOTALL)

# Fix regex for predicated instructions
content = content.replace('ins_re = re.compile(r"/*(?P<pc>[0-9a-f]+)*/\\\\s+(?P<op>[\\\\w\\\\.]+)(?P<args>[^;]*);\\\\s+/*\\\\s+(?P<h1>0x[0-9a-f]+)\\\\s+*/")', 
                          'ins_re = re.compile(r"/*(?P<pc>[0-9a-f]+)*/\\\\s+(?:@!?[A-Z0-9]+\\\\s+)?(?P<op>[\\\\w\\\\.]+)(?P<args>[^;]*);\\\\s+/*\\\\s+(?P<h1>0x[0-9a-f]+)\\\\s+*/")')

# Final ELF rebuild logic with alignment and REGCOUNT
rebuild_replacement = """        for sn, instrs in self.sections.items():
            for i, ins in enumerate(instrs):
                if any(br in ins['op'] for br in ['BRA', 'SSY', 'PBK', 'JMP']):
                    off = struct.unpack('<i', struct.pack('<I', (ins['h1'] >> 32) & 0xFFFFFFFF))[0]
                    if ins['old_pc'] is not None:
                        target = ins['old_pc'] + 16 + off
                        if (sn, target) in self.pc_map:
                            ins['h1'] = (ins['h1'] & 0x00000000FFFFFFFF) | (((self.pc_map[(sn, target)] - (i*16+16)) & 0xFFFFFFFF) << 32)

        cur_data = data
        sh_table = [list(struct.unpack_from('<IIQQQQIIQQ', data, e_shoff + (i*64))) for i in range(e_shnum)]
        sh_table_orig = [list(struct.unpack_from('<IIQQQQIIQQ', data, e_shoff + (i*64))) for i in range(e_shnum)]
        ph_table = [list(struct.unpack_from('<IIQQQQQQ', data, e_phoff + (i*56))) for i in range(e_phnum)]
        str_tab_off = sh_table[sh_idx][4]

        def get_name(idx):
            end = data.find(b'\\\\x00', str_tab_off + idx)
            return data[str_tab_off + idx : end].decode('utf-8')

        for i in range(e_shnum):
            name = get_name(sh_table_orig[i][0])
            if name in self.sections:
                old_off, old_size = sh_table[i][4], sh_table[i][5]
                new_sec = bytearray()
                for ins in self.sections[name]: new_sec.extend(struct.pack('<QQ', ins['h1'], ins['h2']))
                growth = len(new_sec) - old_size
                actual_off = old_off 
                cur_data = cur_data[:actual_off] + new_sec + cur_data[actual_off + old_size:]
                sh_table[i][5] = len(new_sec)
                
                if ".text." in name:
                    sh_table[i][7] = (sh_table[i][7] & 0x00FFFFFF) | ((self.max_reg + 1) << 24) | 0x10000000

                accum_shift = growth
                for j in range(e_shnum):
                    if sh_table[j][4] > old_off:
                        orig_off = sh_table[j][4]
                        new_off = orig_off + accum_shift
                        align = sh_table[j][8]
                        if align > 1:
                            aligned_off = (new_off + align - 1) & ~(align - 1)
                            padding = aligned_off - new_off
                            if padding > 0:
                                cur_data = cur_data[:new_off] + b'\\\\x00'*padding + cur_data[new_off:]
                                accum_shift += padding
                                new_off = aligned_off
                        sh_table[j][4] = new_off
                
                for j in range(e_phnum):
                    if ph_table[j][2] <= old_off and (ph_table[j][2] + ph_table[j][5]) > old_off:
                        ph_table[j][5] += accum_shift 
                        ph_table[j][6] += accum_shift 
                    elif ph_table[j][2] > old_off:
                        ph_table[j][2] += accum_shift 

                if e_phoff > old_off: e_phoff += accum_shift
                if e_shoff > old_off: e_shoff += accum_shift"""

pattern_rebuild = r'        for sn, instrs in self\.sections\.items\(\):.*?if e_shoff > old_off: e_shoff \+= growth'
content = re.sub(pattern_rebuild, rebuild_replacement, content, flags=re.DOTALL)

with open('rewriter.py', 'w') as f:
    f.write(content)
