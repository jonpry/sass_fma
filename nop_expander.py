#!/usr/bin/env python3
import sys
import struct
import re
import subprocess

# SM70 NOP Encoding
NOP_H1 = 0x0000000000007918
NOP_H2 = 0x000fc00000000000

class NopExpander:
    def __init__(self, input_path, output_path):
        self.input_path = input_path
        self.output_path = output_path
        self.sections_to_expand = []

    def get_sections(self):
        """Finds all .text sections in the ELF."""
        with open(self.input_path, 'rb') as f: data = f.read()
        e_shoff = struct.unpack_from('<Q', data, 40)[0]
        e_shnum = struct.unpack_from('<H', data, 60)[0]
        sh_idx = struct.unpack_from('<H', data, 62)[0]
        
        sh_table = [struct.unpack_from('<IIQQQQIIQQ', data, e_shoff + (i*64)) for i in range(e_shnum)]
        str_tab_off = sh_table[sh_idx][4]

        def get_name(idx):
            end = data.find(b'\x00', str_tab_off + idx)
            return data[str_tab_off + idx : end].decode('utf-8')

        for i in range(e_shnum):
            name = get_name(sh_table[i][0])
            if ".text." in name:
                self.sections_to_expand.append(name)

    def patch_and_expand(self, num_nops=1024):
        with open(self.input_path, 'rb') as f: data = bytearray(f.read())
        
        e_phoff, e_shoff = struct.unpack_from('<QQ', data, 32)[0:2]
        e_phnum = struct.unpack_from('<H', data, 56)[0]
        e_shnum = struct.unpack_from('<H', data, 60)[0]
        sh_idx = struct.unpack_from('<H', data, 62)[0]
        
        sh_table = [list(struct.unpack_from('<IIQQQQIIQQ', data, e_shoff + (i*64))) for i in range(e_shnum)]
        ph_table = [list(struct.unpack_from('<IIQQQQQQ', data, e_phoff + (i*56))) for i in range(e_phnum)]
        str_tab_off = sh_table[sh_idx][4]

        def get_name(idx):
            end = data.find(b'\x00', str_tab_off + idx)
            return data[str_tab_off + idx : end].decode('utf-8')

        cur_data, cum_growth = data, 0
        nop_block = bytearray()
        for _ in range(num_nops):
            nop_block.extend(struct.pack('<QQ', NOP_H1, NOP_H2))
        
        growth_per_sec = len(nop_block)

        for i in range(e_shnum):
            name = get_name(sh_table[i][0])
            if ".text." in name:
                old_off, old_size = sh_table[i][4], sh_table[i][5]
                actual_off = old_off + cum_growth + old_size
                
                # Insert NOPs at the end of the section
                cur_data = cur_data[:actual_off] + nop_block + cur_data[actual_off:]
                
                sh_table[i][5] += growth_per_sec
                for j in range(e_shnum):
                    if sh_table[j][4] > old_off: sh_table[j][4] += growth_per_sec
                
                for j in range(e_phnum):
                    if ph_table[j][2] <= old_off and (ph_table[j][2] + ph_table[j][5]) > old_off:
                        ph_table[j][5] += growth_per_sec
                        ph_table[j][6] += growth_per_sec
                    elif ph_table[j][2] > old_off:
                        ph_table[j][2] += growth_per_sec

                if e_phoff > old_off: e_phoff += growth_per_sec
                if e_shoff > old_off: e_shoff += growth_per_sec
                cum_growth += growth_per_sec

        # Update symbol sizes
        for i in range(e_shnum):
            if sh_table[i][1] in [2, 11]: # SHT_SYMTAB, SHT_DYNSYM
                o, s, entsize = sh_table[i][4], sh_table[i][5], sh_table[i][9]
                content = bytearray(cur_data[o:o+s])
                for j in range(0, len(content), entsize):
                    st_shndx = struct.unpack_from('<H', content, j+6)[0]
                    if st_shndx < e_shnum and ".text." in get_name(sh_table[st_shndx][0]):
                        struct.pack_into('<Q', content, j+16, sh_table[st_shndx][5])
                cur_data[o:o+s] = content

        struct.pack_into('<QQ', cur_data, 32, e_phoff, e_shoff)
        for i in range(e_shnum): struct.pack_into('<IIQQQQIIQQ', cur_data, e_shoff + (i*64), *sh_table[i])
        for i in range(e_phnum): struct.pack_into('<IIQQQQQQ', cur_data, e_phoff + (i*56), *ph_table[i])
        
        with open(self.output_path, 'wb') as f: f.write(cur_data)
        print(f"[NopExpander] Expanded {len(self.sections_to_expand)} sections by {num_nops} NOPs each.")

if __name__ == "__main__":
    if len(sys.argv) < 3: sys.exit(1)
    exp = NopExpander(sys.argv[1], sys.argv[2])
    exp.get_sections()
    exp.patch_and_expand()
