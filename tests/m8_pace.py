#!/usr/bin/env python3
"""M8a part 2: the time-exact pacing prototype (src/m4/game.asm PACE_MODE 1) against today's pacing (mode 0).
Each script runs twice in the game (build/m4game.mzf, the harness setup of tests/m4_game.py, the script's guard options),
mode 0 and mode 1 (PACE_MODE poked before the start), stopping at tick_done after every tick. Checked:
  1. the logic is identical every tick: the kid line (tests/m4_test.py z80_state), the guard line (G_SNAP) and the guard
     records and globals, the level-event state EV (the time, texts, flashes, flags; without TXT_GEN_SHOWN, the text on
     screen: drawing state), the sound model's state (SND, the ticks model), the trap state and the trobs / mobs, the level
     blueprint (tiles and modifiers);
  2. after every tick mode 1 drew (SKIPPED = 0 at tick_done), VRAM equals mode 0's VRAM at the same tick: the skipped
     ticks' changes (tiles, the people, the falling floors, torch flames) must all be in the next drawn screen;
  3. at the end, after the last drawn tick, the shadow room (RAM-disk page 1) equals mode 0's: no stale background.
Measured (mode 1 vs mode 0, over the moving stretches): ticks a second, drawn screens a second, the skipped ticks and
their runs, the cost of an undrawn tick, of a drawn tick after a skip and of a normal drawn tick (cycles from ml_go to
tick_done: the work without the wait for the clock).
usage: m8_pace.py [--ticks N] [script.txt ...]   (default: walk_level1, gate_push, fight1 with their stretches)"""
import hashlib, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, 'tests'), os.path.join(ROOT, 'tools')]
import m4_game as G, kidsim
from m4_test import z80_state, z80_guard
from m3_test import RAMDISK
from emu import Emu
FRAME = 312 * 228
STRETCHES = {'walk_level1.txt': [(30, 60), (190, 260)], 'gate_push.txt': [(18, 60), (200, 260)], 'fight1.txt': [(60, 160)]}
LOGIC = [(0x0148, 30, 'G_SNAP'), (0x0166, 0x52, 'guard records'), (0x0280, 0x1C, 'EV'), (0x029D, 3, 'EV: TEXT_MSG'), (0x03C1, 7, 'SND'), (0x03DD, 3, 'ticks model'),
         (0x0B30, 0x1A, 'trap state'), (0x0B3B, 2, 'TROBS_N/MOBS_N'), (0x0B50, 0xB0, 'TROBS/MOBS'), (0xEC00, 1440, 'level tiles')]

def script_path(script):
    for d in ('m4_scripts', 'm6_scripts', 'm5_scripts', 'm7_scripts'):
        sp = os.path.join(ROOT, 'tests', d, script)
        if os.path.exists(sp): return sp
    return script

def run(sp, mode, nticks):
    """one run: per tick (cost cycles, cycles at tick_done, skipped, kid line, logic md5, vram md5); the shadow room at the end"""
    moves, patches = kidsim.read_script(sp)
    nticks = min(nticks, len(moves) - 1)
    with Emu() as e:
        S = G.setup(e, kidsim.script_level(sp), opts=kidsim.script_opts(sp))
        e.call('mem_write', addr=S['PACE_MODE'], data_hex='%02x' % mode)
        enc = bytes([((x + 1) & 3) | (((y + 1) & 3) << 2) | (0x10 if sh else 0) for (x, y, sh) in moves]) + b'\xff'
        G.write_pack(e, enc, 5, G.SCRIPT)
        e.call('mem_write', addr=G.SCRIPT_PTR, data_hex='%02x%02x' % (G.SCRIPT & 255, G.SCRIPT >> 8))
        e.call('bp_clear'); e.call('bp_add', addr=S['level_ready']); e.run(400)
        for (rm, p, t, m) in patches:
            e.call('mem_write', addr=G.LEVEL_ADDR + (rm - 1) * 30 + p, data_hex='%02x' % t)
            e.call('mem_write', addr=G.LEVEL_ADDR + 720 + (rm - 1) * 30 + p, data_hex='%02x' % m)
        e.call('bp_clear'); e.call('bp_add', addr=S['ml_go']); e.call('bp_add', addr=S['tick_done'])
        cyc = lambda: e.call('get_raster_pos')['total_cycles']
        rows = []
        for t in range(nticks):
            r = e.run(400); assert r['stopped_by'] == 'breakpoint', (sp, t, r)       # ml_go
            c0 = cyc()
            r = e.run(400); assert r['stopped_by'] == 'breakpoint', (sp, t, r)       # tick_done
            c1 = cyc()
            skipped = e.mem(S['SKIPPED'], 1)[0]
            kid = z80_state(e, t) + ' ' + z80_guard(e, S['G_SNAP'])
            h = hashlib.md5()
            for a, n, _ in LOGIC: h.update(e.mem(a, n))
            vram = hashlib.md5(b''.join(e.vram_planes())).hexdigest()
            rows.append((c1 - c0, c1, skipped, kid, h.hexdigest(), vram))
        shadow = hashlib.md5(b''.join(e.region(RAMDISK[1], off, 4096) for off in range(0, 32000, 4096))[:32000]).hexdigest()
    return rows, shadow

def stats(rows, t0, t1):
    """ticks a second, drawn screens a second, skips, costs over ticks t0..t1 (rows: one per tick, tick_done cycles)"""
    seg = rows[t0:t1]
    secs = (rows[t1 - 1][1] - rows[t0 - 1][1]) / FRAME / 50 if t0 > 0 else (rows[t1 - 1][1] - rows[0][1]) / FRAME / 50
    n = len(seg); drawn = sum(1 for r in seg if not r[2])
    runs = []; k = 0
    for r in seg:
        if r[2]: k += 1
        elif k: runs.append(k); k = 0
    if k: runs.append(k)
    cost = lambda sel: (sum(r[0] for r in sel) / len(sel) / FRAME) if sel else float('nan')
    undrawn = [r for r in seg if r[2]]
    after = [seg[i] for i in range(1, n) if not seg[i][2] and seg[i - 1][2]]
    normal = [seg[i] for i in range(1, n) if not seg[i][2] and not seg[i - 1][2]]
    return dict(ticks_s=n / secs, drawn_s=drawn / secs, frames_tick=secs * 50 / n, skipped=n - drawn,
                runs={k: runs.count(k) for k in sorted(set(runs))}, c_undrawn=cost(undrawn), c_after=cost(after), c_normal=cost(normal))

def main():
    args = sys.argv[1:]
    nticks = int(args[args.index('--ticks') + 1]) if '--ticks' in args else 10000
    scripts = [a for a in args if a.endswith('.txt')] or list(STRETCHES)
    bad = 0
    for script in scripts:
        sp = script_path(script); name = os.path.basename(sp)
        r0, sh0 = run(sp, 0, nticks); r1, sh1 = run(sp, 1, nticks)
        n = len(r0); diffs = [t for t in range(n) if r0[t][3:5] != r1[t][3:5]]
        drawn1 = [t for t in range(n) if not r1[t][2]]
        vbad = [t for t in drawn1 if r0[t][5] != r1[t][5]]
        last = drawn1[-1] if drawn1 else None
        print('%s: %d ticks; mode 1 skipped %d, drew %d' % (name, n, n - len(drawn1), len(drawn1)))
        print('  logic identical every tick: %s' % ('yes' if not diffs else 'NO, first at tick %d:\n   0 %s\n   1 %s' % (diffs[0], r0[diffs[0]][3], r1[diffs[0]][3])))
        print('  VRAM equal to mode 0 at every tick mode 1 drew: %s' % ('yes (%d ticks)' % len(drawn1) if not vbad else 'NO at %d ticks, first %d' % (len(vbad), vbad[0])))
        same_sh = sh0 == sh1
        print('  shadow room equal at the end (last drawn tick %s, last tick %s): %s' % (last, 'drawn' if last == n - 1 else 'skipped', 'yes' if same_sh else 'NO'))
        bad += len(diffs) + len(vbad) + (0 if same_sh or last != n - 1 else 1)
        for t0, t1 in STRETCHES.get(name, [(0, n)]):
            t1 = min(t1, n)
            if t1 <= t0: continue
            s0, s1 = stats(r0, t0, t1), stats(r1, t0, t1)
            print('  ticks %d-%d: mode 0 %.2f ticks/s (%.2f frames a tick, all drawn); mode 1 %.2f ticks/s, %.2f screens/s, %d of %d ticks undrawn, runs %s' % (
                t0, t1, s0['ticks_s'], s0['frames_tick'], s1['ticks_s'], s1['drawn_s'], s1['skipped'], t1 - t0, s1['runs']))
            print('    cost (frames, work only): mode 0 drawn tick %.2f; mode 1 undrawn %.2f, drawn after a skip %.2f, drawn after a drawn %.2f' % (
                s0['c_normal'], s1['c_undrawn'], s1['c_after'], s1['c_normal']))
    print('m8_pace: %s' % ('ok' if not bad else '%d problems' % bad))
    sys.exit(1 if bad else 0)

if __name__ == '__main__': main()
