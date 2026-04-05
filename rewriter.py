#!/usr/bin/env python3
import sys
import subprocess
import re
import struct
import os
sys.path.append(os.path.join(os.getcwd(), 'CuAssembler'))
try:
    from CuAsm.CuControlCode import CuControlCode
except ImportError:
    print("Could not import CuAsm.CuControlCode. Make sure it is accessible.")
    sys.exit(1)

class SassRewriter:
    def __init__(self, input_path, output_path):
        self.input_path = input_path
        self.output_path = output_path
        self.arch = "sm_70"
        self.sections = {} 
        self.pc_map = {}   # (sec_name, old_pc) -> new_pc
        self.max_reg = 0
        self.num_replaced = 0

    def disassemble(self):
        cmd = ["/usr/local/cuda-12.8/bin/nvdisasm", "-hex", self.input_path]
        try:
            raw = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
            if "SM80" in raw: self.arch = "sm_80"
            else: self.arch = "sm_70"
            print(f"[Rewriter] Detected {self.arch.upper()} architecture.")
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
            if any(x in ins['op'] for x in ["BRA", "JMP"]):
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
        ins_re = re.compile(r"/\*(?P<pc>[0-9a-f]+)\*/\s+(?:(?P<pred>@!?[A-Z0-9]+)\s+)?(?P<op>[\w\.]+)(?P<args>[^;]*);\s+/\*\s+(?P<h1>0x[0-9a-f]+)\s+\*/")
        
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
                defs, uses = self.get_regs(op, args)
                self.sections[cur_sec].append({'pc':pc, 'h1':h1, 'h2':h2, 'op':op, 'defs':defs, 'uses':uses, 'old_pc':pc})
            else: i += 1

        for sn, instrs in self.sections.items():
            self.solve_liveness(instrs)
            new_instrs = []
            for ins in instrs:
                self.pc_map[(sn, ins['pc'])] = len(new_instrs) * 16
                if "FMA" in ins['op'] and self.arch == "sm_70":
                    self.num_replaced += 1
                    rd, ra = (ins['h1'] >> 16) & 0xFF, (ins['h1'] >> 24) & 0xFF
                    h1_pred = ins['h1'] & 0xF000
                    op_base = ins['h1'] & 0xFFF
                    
                    # Dynamic register allocation
                    candidates = set(range(self.max_reg + 1)) - ins['live_out'] - ins['defs'] - ins['uses']
                    if candidates: temp_reg = min(candidates)
                    else:
                        temp_reg = self.max_reg + 1
                        self.max_reg = temp_reg

                    # Extract original control components (h2 bits 41-63)
                    orig_ctrl = ins['h2'] >> 41
                    c_wait, c_read, c_write, c_yield, c_stall = CuControlCode.splitCode(orig_ctrl)

                    # FMUL: Wait for original deps, Read original deps, No Write (7), No Yield (1), Stall 4
                    fmul_ctrl_code = CuControlCode.mergeCode(c_wait, c_read, 7, 1, 4)
                    fmul_h2 = (fmul_ctrl_code << 41) | 0x00400000

                    # FADD: No Wait (0), No Read (7), Write original deps, Original Yield, Original Stall
                    fadd_ctrl_code = CuControlCode.mergeCode(0, 7, c_write, c_yield, c_stall)
                    fadd_h2 = (fadd_ctrl_code << 41)

                    if op_base == 0x423:
                        rb, imm_val = ins['h2'] & 0xFF, (ins['h1'] >> 32) & 0xFFFFFFFF
                        fmul_h1 = (rb << 32) | (ra << 24) | (temp_reg << 16) | 0x220 | h1_pred
                        new_instrs.append({'h1':fmul_h1, 'h2':fmul_h2, 'op':'FMUL', 'old_pc':ins['pc']})
                        fadd_h1 = (imm_val << 32) | (temp_reg << 24) | (rd << 16) | 0x421 | h1_pred
                        new_instrs.append({'h1':fadd_h1, 'h2':fadd_h2, 'op':'FADD', 'old_pc':None})
                    elif op_base == 0x823:
                        rc, imm_val = ins['h2'] & 0xFF, (ins['h1'] >> 32) & 0xFFFFFFFF
                        fmul_h1 = (imm_val << 32) | (ra << 24) | (temp_reg << 16) | 0x820 | h1_pred
                        new_instrs.append({'h1':fmul_h1, 'h2':fmul_h2, 'op':'FMUL', 'old_pc':ins['pc']})
                        fadd_h1 = (temp_reg << 32) | (rc << 24) | (rd << 16) | 0x221 | h1_pred
                        new_instrs.append({'h1':fadd_h1, 'h2':fadd_h2, 'op':'FADD', 'old_pc':None})
                    else: # 0x223
                        rb, rc = (ins['h1'] >> 32) & 0xFF, ins['h2'] & 0xFF
                        fmul_h1 = (rb << 32) | (ra << 24) | (temp_reg << 16) | 0x220 | h1_pred
                        new_instrs.append({'h1':fmul_h1, 'h2':fmul_h2, 'op':'FMUL', 'old_pc':ins['pc']})
                        fadd_h1 = (temp_reg << 32) | (rc << 24) | (rd << 16) | 0x221 | h1_pred
                        new_instrs.append({'h1':fadd_h1, 'h2':fadd_h2, 'op':'FADD', 'old_pc':None})
                else:
                    new_instrs.append({'h1':ins['h1'], 'h2':ins['h2'], 'op':ins['op'], 'old_pc':ins['pc']})
            self.sections[sn] = new_instrs

    def patch_and_rebuild(self):
        with open(self.input_path, 'rb') as f: data = bytearray(f.read())
        e_phoff, e_shoff = struct.unpack_from('<QQ', data, 32)[0:2]
        e_phnum = struct.unpack_from('<H', data, 56)[0]
        e_shnum = struct.unpack_from('<H', data, 60)[0]
        sh_idx = struct.unpack_from('<H', data, 62)[0]
        
        for sn, instrs in self.sections.items():
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
            end = data.find(b'\x00', str_tab_off + idx)
            return data[str_tab_off + idx : end].decode('utf-8')

        for i in range(e_shnum):
            name = get_name(sh_table_orig[i][0])
            if name in self.sections:
                old_off, old_size = sh_table[i][4], sh_table[i][5]
                new_sec = bytearray()
                for ins in self.sections[name]: new_sec.extend(struct.pack('<QQ', ins['h1'], ins['h2']))
                growth = len(new_sec) - old_size
                cur_data = cur_data[:old_off] + new_sec + cur_data[old_off + old_size:]
                sh_table[i][5] = len(new_sec)
                if ".text." in name: sh_table[i][7] = (sh_table[i][7] & 0x00FFFFFF) | ((self.max_reg + 1) << 24)

                accum_shift = growth
                for j in range(e_shnum):
                    if sh_table[j][4] > old_off:
                        new_off = sh_table[j][4] + accum_shift
                        align = sh_table[j][8]
                        if align > 1:
                            aligned_off = (new_off + align - 1) & ~(align - 1)
                            padding = aligned_off - new_off
                            if padding > 0:
                                cur_data = cur_data[:new_off] + b'\x00'*padding + cur_data[new_off:]
                                accum_shift += padding; new_off = aligned_off
                        sh_table[j][4] = new_off
                for j in range(e_phnum):
                    if ph_table[j][2] <= old_off and (ph_table[j][2] + ph_table[j][5]) > old_off:
                        ph_table[j][5] += accum_shift; ph_table[j][6] += accum_shift 
                    elif ph_table[j][2] > old_off: ph_table[j][2] += accum_shift 
                if e_phoff > old_off: e_phoff += accum_shift
                if e_shoff > old_off: e_shoff += accum_shift

        struct.pack_into('<QQ', cur_data, 32, e_phoff, e_shoff)
        for i in range(e_shnum): struct.pack_into('<IIQQQQIIQQ', cur_data, e_shoff + (i*64), *sh_table[i])
        for i in range(e_phnum): struct.pack_into('<IIQQQQQQ', cur_data, e_phoff + (i*56), *ph_table[i])
        with open(self.output_path, 'wb') as f: f.write(cur_data)
        print(f"[Rewriter] Success. Replaced {self.num_replaced} FMAs.")

if __name__ == "__main__":
    if len(sys.argv) < 3: sys.exit(1)
    r = SassRewriter(sys.argv[1], sys.argv[2])
    r.parse_sass(r.disassemble())
    r.patch_and_rebuild()
