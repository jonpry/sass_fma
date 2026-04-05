import re
ins_re = re.compile(r"/\*(?P<pc>[0-9a-f]+)\*/\s+(?:@!?[A-Z0-9]+\s+)?(?P<op>[\w\.]+)(?P<args>[^;]*);\s+/\*\s+(?P<h1>0x[0-9a-f]+)\s+\*/")
line1 = "        /*0160*/                   BRA `(.L_x_0);                            /* 0xfffffff000007947 */"
line2 = "        /*0170*/                   NOP;                                      /* 0x0000000000007918 */"
for l in [line1, line2]:
    m = ins_re.search(l)
    if m:
        print(f"MATCH: {m.groups()}")
    else:
        print(f"FAIL: {l}")
