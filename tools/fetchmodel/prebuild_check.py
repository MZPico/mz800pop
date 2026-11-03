#!/usr/bin/env python3
"""Checks prebuild.py's variant generator against the kernel: every kid fetch of a script (a tracepoint after
char_fetch with the kid's descriptor SPR_A and his cell buffer SPRBUF_A) compared byte for byte with
prebuild.variants(). usage: prebuild_check.py [SCRIPT]"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path[:0] = [os.path.join(ROOT, 'tests'), os.path.join(ROOT, 'tools'), HERE]
import m4_game as G, kidsim
from emu import Emu
from fetchstat import script_path
import prebuild
SPR_A, SPRBUF_A = 0x0B00, 0xB000

def main():
    sp = script_path(sys.argv[1] if len(sys.argv) > 1 else 'walk_level1')
    pack = open(os.path.join(prebuild.A, 'kid.pack'), 'rb').read(); d = open(os.path.join(prebuild.A, 'kid.dir'), 'rb').read()
    moves, patches = kidsim.read_script(sp); keys = kidsim.read_keys(sp)
    o = kidsim.script_opts(sp); n = 0; bad = 0; seen = set()
    with Emu() as e:
        S = G.setup(e, kidsim.script_level(sp), opts=o)
        G.write_pack(e, G.encode(moves, keys), 5, G.SCRIPT)
        e.call('mem_write', addr=G.SCRIPT_PTR, data_hex='%02x%02x' % (G.SCRIPT & 255, G.SCRIPT >> 8))
        e.call('bp_clear'); e.call('bp_add', addr=S['guards_off_chk'])
        r = e.run(400); assert r['stopped_by'] == 'breakpoint', r
        e.call('bp_clear')
        e.trace_add(S['tick_done']); e.trace_add(S['pu2a'] + 5, mem=[(SPR_A, 24), (SPRBUF_A, 2048)])
        tick = 0
        for rec in e.collect(200, stop=lambda r: tick >= len(moves)):
            if rec['addr'] == S['tick_done']: tick += 1; continue
            sd, buf = rec['mem']
            fr, mi = sd[8], sd[9]; x = sd[6] | sd[7] << 8; key = (fr, mi, x & 7)
            if sd[0] | sd[1] << 8 != SPRBUF_A or key in seen: continue      # (another slot, or already checked)
            seen.add(key)
            w, h, vs = prebuild.variants(pack, d, fr)
            want = vs[mi * 8 + (x & 7)]; n += 1
            if buf[:len(want)] != want: bad += 1
        e.trace_clear()
    print('%s: %d distinct kid fetches compared, %d differ' % (os.path.basename(sp), n, bad))
    sys.exit(1 if bad or not n else 0)

if __name__ == '__main__':
    main()
