#!/usr/bin/env python3
import sys
import subprocess
import re
import struct

# Unified Constants for sm_70/sm_80
FMUL_BASE_H1 = 0x7220
FADD_BASE_H1 = 0x7221
BRA_BASE_H1 = 0x7947
BRA_BASE_H2 = 0x000fc0000383ffff

class SassRewriter:
    def __init__(self, input_path, output_path):
        self.input_path = input_path
        self.output_path = output_path
        self.arch = "sm_70"
        self.sections = {} 
        self.pc_map = {}   # (sec_name, old_pc) -> new_pc
        self.verified_jump_tables = set() 
        self.used_registers = set()
        self.max_reg = 0

    def disassemble(self):
        """Runs nvdisasm and detects architecture."""
        cmd = ["/usr/local/cuda/bin/nvdisasm", "-hex", self.input_path]
        try:
            raw = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
            if "SM80" in raw:
                self.arch = "sm_80"
                print("[Rewriter] Detected SM80 (Ampere) architecture.")
            else:
                self.arch = "sm_70"
                print("[Rewriter] Detected SM70 (Volta) architecture.")
            return raw
        except: return ""

    def get_regs(self, op, args):
        regs = [int(r) for r in re.findall(r"R(\d+)", args)]
        if not regs: return set(), set()
        if any(x in op for x in ["ST", "BRA", "EXIT", "RET", "JMP", "CAL", "BAR", "MEMBAR"]):
            return set(), set(regs)
        return {regs[0]}, set(regs[1:])

    def solve_liveness(self, instrs):
        pc_to_idx = {ins['pc']: i for i, ins in enumerate(instrs)}
        for i, ins in enumerate(instrs):
            succs = []
            if "EXIT" not in ins['op'] and "RET" not in ins['op'] and i+1 < len(instrs):
                succs.append(i+1)
            if "BRA" in ins['op']:
                off = struct.unpack('<i', struct.pack('<I', (ins['h1'] >> 32) & 0xFFFFFFFF))[0]
                target = ins['pc'] + 16 + off
                if target in pc_to_idx: succs.append(pc_to_idx[target])
            ins['succs'] = succs
            ins['live_in'], ins['live_out'] = set(), set()

        changed = True
        while changed:
            changed = False
            for i in reversed(range(len(instrs))):
                ins = instrs[i]
                new_out = set()
                for s_idx in ins['succs']: new_out.update(instrs[s_idx]['live_in'])
                new_in = ins['uses'].union(new_out - ins['defs'])
                if new_in != ins['live_in'] or new_out != ins['live_out']:
                    ins['live_in'], ins['live_out'] = new_in, new_out
                    changed = True

    def parse_sass(self, raw_text):
        for r in re.findall(r"R(\d+)", raw_text): self.max_reg = max(self.max_reg, int(r))
        sec_re = re.compile(r"//-+\s+(?P<name>\.text\.\S+)\s+-+")
        ins_re = re.compile(r"/\*(?P<pc>[0-9a-f]+)\*/\s+(?P<op>[\w\.]+)(?P<args>[^;]*);\s+/\*\s+(?P<h1>0x[0-9a-f]+)\s+\*/")
        const_re = re.compile(r"c\s*\[\s*(?P<bank>0x[0-9a-f]+)\s*\]\s*\[\s*(?P<off>0x[0-9a-f]+)\s*\]")
        reg_sources = {} 

        lines = raw_text.splitlines()
        cur_sec, i = ".text", 0
        while i < len(lines):
            line = lines[i]
            s_m = sec_re.search(line)
            if s_m:
                cur_sec = s_m.group('name')
                self.sections[cur_sec] = []
                i += 1; continue
            m = ins_re.search(line)
            if m:
                if cur_sec not in self.sections: self.sections[cur_sec] = []
                pc, op, args, h1 = int(m.group('pc'), 16), m.group('op'), m.group('args'), int(m.group('h1'), 16)
                i += 1
                h2 = 0
                if i < len(lines):
                    h2_m = re.search(r"/\*\s+(?P<h2>0x[0-9a-f]+)\s+\*/", lines[i])
                    if h2_m: h2 = int(h2_m.group('h2'), 16)
                
                c_m = const_re.search(args)
                if c_m:
                    bank, off = int(c_m.group('bank'), 16), int(c_m.group('off'), 16)
                    sec_name = f".nv.constant{bank}"
                    if "BRX" in op: self.verified_jump_tables.add((sec_name, off))
                    elif "LDC" in op:
                        r_m = re.search(r"(?P<reg>R\d+)", args)
                        if r_m: reg_sources[r_m.group('reg')] = (sec_name, off)
                if any(x in op for x in ["JMP", "CAL"]):
                    r_m = re.search(r"(?P<reg>R\d+)", args)
                    if r_m and r_m.group('reg') in reg_sources: self.verified_jump_tables.add(reg_sources[r_m.group('reg')])

                defs, uses = self.get_regs(op, args)
                self.sections[cur_sec].append({'pc':pc, 'h1':h1, 'h2':h2, 'op':op, 'defs':defs, 'uses':uses})
            else: i += 1

        for sn, instrs in self.sections.items():
            self.solve_liveness(instrs)
            new_instrs = []
            for ins in instrs:
                self.pc_map[(sn, ins['pc'])] = len(new_instrs) * 16
                if "FMA" in ins['op']:
                    r_dest, r_srcA, r_srcB, r_srcC = (ins['h1']>>16)&0xFF, (ins['h1']>>24)&0xFF, (ins['h1']>>32)&0xFF, ins['h2']&0xFF
                    pred, temp_reg = ins['h2']&0xF, r_dest
                    if r_dest == r_srcC:
                        spare = next((r for r in range(255) if r not in ins['live_out']), None)
                        if spare is None: self.max_reg += 1; spare = self.max_reg
                        temp_reg = spare
                    
                    # 1. FMUL (Common for 70/80)
                    fmul_h1 = FMUL_BASE_H1 | (temp_reg << 16) | (r_srcA << 24) | (r_srcB << 32)
                    fmul_h2 = (ins['h2'] & ~((0x7<<46)|(0xF<<41)|0xFF|0xF)) | (0x0<<46) | (0x1<<41) | 0xFF | pred
                    new_instrs.append({'h1':fmul_h1, 'h2':fmul_h2, 'op':'FMUL', 'old_pc':ins['pc']})
                    # 2. FADD (Common for 70/80)
                    fadd_h1 = FADD_BASE_H1 | (r_dest << 16) | (r_srcC << 24) | (temp_reg << 32)
                    orig_wb = (ins['h2'] >> 46) & 0x7
                    fadd_h2 = (ins['h2'] & ~((0x3F<<52)|(0x7<<46)|0xF)) | (0x1<<52) | (orig_wb<<46) | pred
                    new_instrs.append({'h1':fadd_h1, 'h2':fadd_h2, 'op':'FADD', 'old_pc':None})
                else:
                    new_instrs.append({'h1':ins['h1'], 'h2':ins['h2'], 'op':ins['op'], 'old_pc':ins['pc']})
            self.sections[sn] = new_instrs

    def patch_and_rebuild(self):
        with open(self.input_path, 'rb') as f: data = bytearray(f.read())
        e_phoff, e_shoff, e_phnum, e_shnum = struct.unpack_from('<QQHH', data, 32)[0:4]
        sh_idx = struct.unpack_from('<H', data, 62)[0]
        
        for sn, instrs in self.sections.items():
            for i, ins in enumerate(instrs):
                if any(br in ins['op'] for br in ['BRA', 'SSY', 'PBK']):
                    off = struct.unpack('<i', struct.pack('<I', (ins['h1'] >> 32) & 0xFFFFFFFF))[0]
                    if ins['old_pc'] is not None:
                        target = ins['old_pc'] + 16 + off
                        if (sn, target) in self.pc_map:
                            ins['h1'] = (ins['h1'] & 0x00000000FFFFFFFF) | (((self.pc_map[(sn, target)] - (i*16+16)) & 0xFFFFFFFF) << 32)

        cur_data, cum_growth = data, 0
        sh_table = [list(struct.unpack_from('<IIQQQQIIQQ', data, e_shoff + (i*64))) for i in range(e_shnum)]
        str_tab_off = sh_table[sh_idx][4]

        for i in range(e_shnum):
            name = "".join(chr(data[str_tab_off + sh_table[i][0] + k]) for k in range(64) if data[str_tab_off + sh_table[i][0] + k] != 0)
            if name in self.sections:
                old_off, old_size = sh_table[i][4], sh_table[i][5]
                new_sec = bytearray()
                for ins in self.sections[name]: new_sec.extend(struct.pack('<QQ', ins['h1'], ins['h2']))
                growth = len(new_sec) - old_size
                actual_off = old_off + cum_growth
                cur_data = cur_data[:actual_off] + new_sec + cur_data[actual_off + old_size:]
                sh_table[i][5] = len(new_sec)
                for j in range(e_shnum):
                    if sh_table[j][4] > old_off: sh_table[j][4] += growth
                if e_phoff > old_off: e_phoff += growth
                if e_shoff > old_off: e_shoff += growth
                cum_growth += growth

        for i in range(e_shnum):
            name = "".join(chr(data[str_tab_off + sh_table[i][0] + k]) for k in range(64) if data[str_tab_off + sh_table[i][0] + k] != 0)
            o, s = sh_table[i][4], sh_table[i][5]
            target_k = name.replace(".nv.info.", ".text.") if ".nv.info." in name else None
            if ".nv.info" in name or ".nv.constant" in name:
                content = bytearray(cur_data[o:o+s])
                for j in range(0, len(content) - 3, 4):
                    v = struct.unpack('<I', content[j:j+4])[0]
                    if v != 0 and v % 16 == 0:
                        if target_k and (target_k, v) in self.pc_map: struct.pack_into('<I', content, j, self.pc_map[(target_k, v)])
                        elif not target_k and (".nv.constant" in name):
                            suffix = name.split('.')[-1]
                            for (sn, opc), npc in self.pc_map.items():
                                if v == opc and suffix in sn: struct.pack_into('<I', content, j, npc); break
                    if ".nv.info" in name and j <= len(content)-12 and content[j]==0x04 and content[j+1]==0x2f:
                        struct.pack_into('<I', content, j+8, self.max_reg + 1)
                cur_data[o:o+s] = content

        for i in range(e_shnum):
            if sh_table[i][1] == 11:
                o, s, entsize = sh_table[i][4], sh_table[i][5], sh_table[i][9]
                content = bytearray(cur_data[o:o+s])
                for j in range(0, len(content), entsize):
                    if (content[j+4] & 0xf) == 2:
                        tx_idx = struct.unpack_from('<H', content, j+6)[0]
                        if tx_idx < e_shnum: struct.pack_into('<Q', content, j+16, sh_table[tx_idx][5])
                cur_data[o:o+s] = content

        struct.pack_into('<QQ', cur_data, 32, e_phoff, e_shoff)
        for i in range(e_shnum): struct.pack_into('<IIQQQQIIQQ', cur_data, e_shoff + (i*64), *sh_table[i])
        with open(self.output_path, 'wb') as f: f.write(cur_data)
        print(f"[Rewriter] Unified sm_70/80 Patch Complete. Arch: {self.arch}")

if __name__ == "__main__":
    if len(sys.argv) < 3: sys.exit(1)
    r = SassRewriter(sys.argv[1], sys.argv[2])
    r.parse_sass(r.disassemble())
    r.patch_and_rebuild()
