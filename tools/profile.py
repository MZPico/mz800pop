#!/usr/bin/env python3
"""Profile the M4 game in the emulator: run a control script to tick T0, record mz800emu's call profiler over
ticks T0..T1, print per-tick averages per routine (calls, inclusive and exclusive frames; 1 frame = 71136 T).
usage: profile.py script.txt T0 T1 [--root DIR] [--top N] [--sort incl|excl]
(script: a path, or a name in tests/m4_scripts or tests/m6_scripts; its '# guard' / '# sword' options apply)"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
root = args[args.index('--root') + 1] if '--root' in args else os.path.join(HERE, '..')
top = int(args[args.index('--top') + 1]) if '--top' in args else 30
key = args[args.index('--sort') + 1] if '--sort' in args else 'incl'
script, t0, t1 = args[0], int(args[1]), int(args[2])
sys.path[:0] = [os.path.join(root, 'tests'), os.path.join(root, 'tools')]
import m4_game as G, kidsim
from emu import Emu
FRAME = 312 * 228

sp = script if os.path.exists(script) else os.path.join(root, 'tests', 'm4_scripts', script)
if not os.path.exists(sp): sp = os.path.join(root, 'tests', 'm6_scripts', script)
moves, patches = kidsim.read_script(sp)
lv = kidsim.script_level(sp)
with Emu() as e:
    S = G.setup(e, lv, opts=kidsim.script_opts(sp))      # (the script's guard options, as tests/m4_game.py runs it)
    names = {}
    for k, v in S.items(): names.setdefault(v, k)
    enc = bytes([((x + 1) & 3) | (((y + 1) & 3) << 2) | (0x10 if sh else 0) for (x, y, sh) in moves]) + b'\xff'
    G.write_pack(e, enc, 5, G.SCRIPT)
    e.call('mem_write', addr=G.SCRIPT_PTR, data_hex='%02x%02x' % (G.SCRIPT & 255, G.SCRIPT >> 8))
    e.call('bp_clear'); e.call('bp_add', addr=S['level_ready']); e.run(400)
    for (rm, p, t, m) in patches:
        e.call('mem_write', addr=G.LEVEL_ADDR + (rm - 1) * 30 + p, data_hex='%02x' % t)
        e.call('mem_write', addr=G.LEVEL_ADDR + 720 + (rm - 1) * 30 + p, data_hex='%02x' % m)
    e.call('bp_clear'); e.call('bp_add', addr=S['tick_done'])
    for t in range(t0): e.run(400)
    c0 = e.call('get_raster_pos')['total_cycles']
    e.call('profiler_reset'); e.call('profiler_start')
    for t in range(t0, t1): e.run(400)
    e.call('profiler_stop')
    c1 = e.call('get_raster_pos')['total_cycles']
    r = e.call('profiler_get', limit=1000)
n = t1 - t0
rows = []
for it in r['entries']:
    nm = names.get(it['addr'], '%04X' % it['addr'])
    rows.append((it['incl_cycles'] / n / FRAME, it['excl_cycles'] / n / FRAME, it['calls'] / n, nm))
rows.sort(key=lambda x: -(x[0] if key == 'incl' else x[1]))
print('%s ticks %d-%d: %.2f frames per tick' % (os.path.basename(sp), t0, t1, (c1 - c0) / n / FRAME))
print('%-24s %8s %8s %8s' % ('routine', 'calls', 'incl', 'excl'))
for incl, excl, calls, nm in rows[:top]:
    print('%-24s %8.1f %8.2f %8.2f' % (nm, calls, incl, excl))
