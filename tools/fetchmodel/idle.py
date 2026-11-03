#!/usr/bin/env python3
"""The idle time of the 4-frame pacing floor (game.asm mainloop, PACE_MODE 0: a tick that took less than 4 frames
halts until its 4th frame), measured with tracepoints: per tick the cycles from tick_done to ml_go (the next tick's
start: the mainloop's halts and overhead). Also the frames from the program's start to level_ready (the level start)
and the level-start's first tick. usage: idle.py SCRIPT ... (writes idle.json lines per tick to --out FILE)"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path[:0] = [os.path.join(ROOT, 'tests'), os.path.join(ROOT, 'tools')]
import m4_game as G, kidsim
from emu import Emu
from fetchstat import script_path
FRAME = 312 * 228

def run(sp):
    moves, patches = kidsim.read_script(sp); keys = kidsim.read_keys(sp)
    o = kidsim.script_opts(sp)
    with Emu() as e:
        S = G.setup(e, kidsim.script_level(sp), opts=o)
        G.write_pack(e, G.encode(moves, keys), 5, G.SCRIPT)
        e.call('mem_write', addr=G.SCRIPT_PTR, data_hex='%02x%02x' % (G.SCRIPT & 255, G.SCRIPT >> 8))
        e.call('bp_clear'); e.call('bp_add', addr=S['guards_off_chk'])
        r = e.run(400); assert r['stopped_by'] == 'breakpoint', r
        for (rm, p, t, m) in patches:
            e.call('mem_write', addr=G.LEVEL_ADDR + (rm - 1) * 30 + p, data_hex='%02x' % t)
            e.call('mem_write', addr=G.LEVEL_ADDR + 720 + (rm - 1) * 30 + p, data_hex='%02x' % m)
        e.call('bp_clear')
        e.trace_add(S['tick_done']); e.trace_add(S['ml_go']); e.trace_add(S['level_ready'])
        out = []; td = None; tick = 0; t0 = None
        for rec in e.collect(200, stop=lambda r: tick >= len(moves)):
            a = rec['addr']; cy = rec['cycles']
            if a == S['tick_done']: td = cy; tick += 1
            elif a == S['ml_go']:
                if td is not None: out.append((((cy - td) & 0xFFFFFFFF) / FRAME, cy))
            elif a == S['level_ready']: t0 = cy; td = None
        e.trace_clear()
    return out

if __name__ == '__main__':
    args = sys.argv[1:]
    outf = args[args.index('--out') + 1] if '--out' in args else None
    names = [a for i, a in enumerate(args) if not a.startswith('--') and (i == 0 or args[i - 1] != '--out')]
    res = {}
    for nm in names:
        sp = script_path(nm); r = run(sp)
        idle = [x for x, _ in r]; n = len(idle); tot = sum(idle)
        span = ((r[-1][1] - r[0][1]) & 0xFFFFFFFF) / FRAME if n > 1 else 1
        res[nm] = dict(idle=idle, frames=span)
        print('%s: %d ticks in %.0f frames, idle %.3f frames a tick (%.0f%% of the ticks idle > 1 frame), %.2f frames idle a second of play' % (
            nm, n, span, tot / max(n, 1), 100 * sum(1 for x in idle if x > 1) / max(n, 1), sum(idle[1:]) / span * 50))
    if outf: json.dump(res, open(outf, 'w'))
