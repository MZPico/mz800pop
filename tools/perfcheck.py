#!/usr/bin/env python3
"""Speed regression check for the M4 game: run fixed stretches of the test scripts in the emulator, measure
frames per tick (1 frame = 71136 T) and compare with tests/perf_baseline.json. A stretch more than the
tolerance slower than its baseline fails the check.
usage: perfcheck.py [--root DIR] [--update] [--tol PCT]
  --update  write the measured values as the new baseline (after an intended change)"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
root = args[args.index('--root') + 1] if '--root' in args else os.path.join(HERE, '..')
tol = float(args[args.index('--tol') + 1]) if '--tol' in args else 5.0
sys.path[:0] = [os.path.join(root, 'tests'), os.path.join(root, 'tools')]
import m4_game as G, kidsim
from emu import Emu
FRAME = 312 * 228
BASE = os.path.join(root, 'tests', 'perf_baseline.json')
# name: (script, first tick, end tick)
STRETCHES = {
    'normal tick (walkthrough 30-60)': ('walk_level1.txt', 30, 60),
    'level door step (walkthrough 203-207)': ('walk_level1.txt', 203, 207),
    'room change (walkthrough 89)': ('walk_level1.txt', 89, 90),
    'walkthrough 190-260': ('walk_level1.txt', 190, 260),
    'gate (gate_push 200-260)': ('gate_push.txt', 200, 260),
    'traps (traps_b1 0-300)': ('traps_b1.txt', 0, 300),
    'fight (fight1 60-160, guard on)': ('fight1.txt', 60, 160),
}

def script_path(script):
    """tests/m4_scripts/<script>, else tests/m6_scripts/<script> (fight scenes)"""
    sp = os.path.join(root, 'tests', 'm4_scripts', script)
    return sp if os.path.exists(sp) else os.path.join(root, 'tests', 'm6_scripts', script)

def measure(script, spans):
    """frames per tick for each (t0, t1) of one script, in one emulator run"""
    sp = script_path(script)
    moves, patches = kidsim.read_script(sp)
    out = {}
    with Emu() as e:
        S = G.setup(e, kidsim.script_level(sp), opts=kidsim.script_opts(sp))     # (guard options as the tests run it)
        enc = bytes([((x + 1) & 3) | (((y + 1) & 3) << 2) | (0x10 if sh else 0) for (x, y, sh) in moves]) + b'\xff'
        G.write_pack(e, enc, 5, G.SCRIPT)
        e.call('mem_write', addr=G.SCRIPT_PTR, data_hex='%02x%02x' % (G.SCRIPT & 255, G.SCRIPT >> 8))
        e.call('bp_clear'); e.call('bp_add', addr=S['level_ready']); e.run(400)
        for (rm, p, t, m) in patches:
            e.call('mem_write', addr=G.LEVEL_ADDR + (rm - 1) * 30 + p, data_hex='%02x' % t)
            e.call('mem_write', addr=G.LEVEL_ADDR + 720 + (rm - 1) * 30 + p, data_hex='%02x' % m)
        e.call('bp_clear'); e.call('bp_add', addr=S['tick_done'])
        marks = {}
        last = max(t1 for _, t1 in spans)
        cyc = lambda: e.call('get_raster_pos')['total_cycles']
        for t in range(last + 1):
            marks[t] = cyc()
            if t < last: e.run(400)
        for t0, t1 in spans: out[(t0, t1)] = (marks[t1] - marks[t0]) / (t1 - t0) / FRAME
    return out

by_script = {}
for name, (script, t0, t1) in STRETCHES.items(): by_script.setdefault(script, []).append((t0, t1))
got = {}
for script, spans in by_script.items():
    m = measure(script, spans)
    for name, (s, t0, t1) in STRETCHES.items():
        if s == script: got[name] = round(m[(t0, t1)], 2)
if '--update' in args:
    json.dump(got, open(BASE, 'w'), indent=1)
    print('baseline written:', BASE)
base = json.load(open(BASE)) if os.path.exists(BASE) else {}
bad = 0
print('%-40s %9s %9s %7s' % ('stretch (frames per tick)', 'baseline', 'now', 'change'))
for name, v in got.items():
    b = base.get(name)
    if b is None: print('%-40s %9s %9.2f' % (name, '-', v)); continue
    ch = (v - b) / b * 100
    flag = '  SLOWER' if ch > tol else ''
    bad += ch > tol
    print('%-40s %9.2f %9.2f %+6.1f%%%s' % (name, b, v, ch, flag))
print('perf check: %s' % ('%d stretch(es) more than %.0f%% slower' % (bad, tol) if bad else 'ok'))
sys.exit(1 if bad else 0)
