#!/usr/bin/env python3
"""Kid logic measurements (docs/perf.md "Kid logic: measured (2026-11-08)"): the game logic of a tick (kid.asm
kid_tick and everything under it: tick_pre's timers, mobs, trobs, the guard, the kid's sequence, the collisions,
tick_post) profiled alone, and what a saving in it would change after the 4-frame pacing.
  profile SCRIPT T0 T1 [--top N] [--csv OUT]
        ticks T0..T1-1 of a script. Per tick the emulator stops at kid_tick's entry, starts mz800emu's call profiler,
        and stops it at kid_tick's return (its return address read from the stack), so only the logic is profiled.
        Prints the logic's frames a tick (exact, entry to return), the routines by exclusive and by inclusive frames a
        tick, and the groups (collision, tile lookups, sequence table, ...). Then the frames a tick (tick_done to
        tick_done) and the work (ml_go to tick_done) of the same stretch, with the pacing replayed from the work
        (floor() below: game.asm mainloop's mode 0), and what-ifs: the logic cut by X frames every tick, and by each
        group's share. --csv: every tick's work, frames, logic and group frames.
  pace CSV X [X ...]   the replay alone from a --csv file: mean / median frames a tick with the work cut by X
The pacing rule (game.asm mainloop, PACE_MODE 0): a tick starts at ml_go when FRAMES - LAST_TICK >= 4 (LAST_TICK = FRAMES
at the last ml_go), else it halts to the next interrupt. FRAMES counts the vertical blanks, so a tick that ends early
waits to the 4th frame boundary after its own start; a late one starts at once."""
import os, sys, bisect, math
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path[:0] = [os.path.join(ROOT, 'tests'), HERE]
import tickcost as TC
from emu import Emu
from m3_test import syms
FRAME = TC.FRAME

# groups by routine name (the profiler's call targets; a routine reached by jp counts in its caller)
GROUPS = [
    ('collision', ('check_collisions', 'get_row_collision_data', 'set_char_collision', 'move_coll_to_prev',
                   'get_left_wall_xpos', 'get_right_wall_xpos', 'wall_type', 'check_bumped', 'bump_into_opponent',
                   'check_bumped_look_left', 'check_bumped_look_right', 'is_obstacle', 'xpos_in_drawn_room',
                   'bumped', 'bumped_fall', 'clear_coll_rooms', 'get_room_address', 'gcp16', 'okt_meet')),
    ('tile lookup', ('k_get_tile', 'get_tile', 'get_tile_div_mod', 'get_tile_div_mod_m7', 'tile_base', 'k_tbl',
                     'tab_get', 'links_of', 'y_to_row_mod4', 'get_tile_at_char', 'get_tile_behind_char',
                     'get_tile_infrontof_char', 'get_tile_above_char', 'get_tile_front_above_char',
                     'get_tile_behind_above_char', 'get_tilepos', 'k_is_floor', 'k_modif', 'find_room_of_tile')),
    ('sequence', ('play_seq', 'seq_sound', 'seqtbl_offset_char', 'far_seek', 'far_seek_entry')),
    ('frame load', ('load_frame', 'load_fram_det_col', 'load_frame_to_obj', 'determine_col', 'dx_weight',
                    'char_dx_forward', 'dir_front', 'get_edge_distance', 'distance_to_edge_weight')),
    ('mul / div', ('mul8', 'mul16', 'div8', 'div16', 'mul_a_e', 'mul10')),
    ('random', ('prandom',)),
]

# The trims' cost model: a tick's rows {routine: (incl frames, excl frames, calls)} -> the T-states the trim saves.
# The new code's costs are hand counts of the sketched code (docs/perf.md), the old ones are the measured ones.
def _c(r, k): return r[k][2] if k in r else 0
def _i(r, k): return r[k][0] * FRAME if k in r else 0
def _kgt(r): return _i(r, 'k_get_tile') / _c(r, 'k_get_tile') if _c(r, 'k_get_tile') else 0
def _cols(r): return _c(r, 'get_left_wall_xpos')     # columns walked by get_row_collision_data (and check_chomped_guard)
GRC_ROW, GRC_COL = 600, 280         # the row walker: a row's setup with one tile lookup, a column
KGT_FAST = 130                      # k_get_tile: saved by the in-room path, a call (the measured in-room call ~340 T)
TRIMS = [
    ('A', 'row walker for get_row_collision_data',
     lambda r: max(0, _i(r, 'get_row_collision_data') - _c(r, 'get_row_collision_data') * GRC_ROW - _cols(r) * GRC_COL)),
    ("A'", '(alone: the second k_get_tile a column dropped)', lambda r: _cols(r) * (_kgt(r) + 15)),
    ('B', 'check_collisions: the bump loop by pointers', lambda r: 1600 * _c(r, 'get_row_collision_data') / 3),
    ('C', 'move_coll_to_prev: the clears unrolled x2', lambda r: 628 * _c(r, 'move_coll_to_prev')),   # (measured in part 21: 2,292 -> 1,664 T)
    ('D', 'k_get_tile: the in-room path (calls left after A)',
     lambda r: KGT_FAST * max(0, _c(r, 'k_get_tile') - 2 * _cols(r) + _c(r, 'get_row_collision_data'))),
    ('E', 'prandom: max + 1 a power of two (255) without the division', lambda r: 700 * _c(r, 'prandom')),
    ('F', 'trigger_button resident (no events-overlay load; logic side)', lambda r: _i(r, 'ovl_w1')),     # (the scenes' logic loads are all the events overlay's, for trigger_button: tracepoints)
    ('G', 'get_tile_div_mod: page-aligned tables, k_tbl inlined', lambda r: 90 * _c(r, 'get_tile_div_mod')),
]
TRIMS_ALL = ('A', 'B', 'C', 'D', 'E', 'F', 'G')

def name_map():
    S = syms(os.path.join(ROOT, 'build', 'm4game.sym'))
    by = {}
    for k, v in S.items():
        if k.isupper() or k.startswith('_'): continue
        if v not in by or len(k) < len(by[v]): by[v] = k
    for ov in ('ovl_event', 'ovl_rare', 'ovl_keys', 'ovl_anim', 'ovl_btn'):
        p = os.path.join(ROOT, 'build', ov + '.sym')
        if os.path.exists(p):
            for k, v in syms(p).items():
                if 0x7C00 <= v < 0x8000 and not k.isupper(): by.setdefault(v, '%s:%s' % (ov, k))
    return S, by

def profile(sp, t0, t1):
    """per tick: (logic frames, {routine: (incl, excl, calls)}, unmatched returns)"""
    S, by = name_map()
    out = []
    with Emu() as e:
        S2, n = TC.emu_setup(e, sp)
        t1 = min(t1, n)
        e.call('bp_add', addr=S2['tick_done'])
        for t in range(t0): e.run(400)
        e.call('bp_clear')
        cyc = lambda: e.call('get_raster_pos')['total_cycles']
        for t in range(t0, t1):
            e.call('bp_add', addr=S2['kid_tick'])
            e.run(400)
            sp_ = e.call('get_registers')['SP']
            m = e.mem(sp_, 2); ret = m[0] | m[1] << 8
            e.call('bp_clear'); e.call('bp_add', addr=ret)
            e.call('profiler_reset'); e.call('profiler_start')
            c0 = cyc(); e.run(400); c1 = cyc()
            e.call('profiler_stop')
            r = e.call('profiler_get', limit=1000)
            rows = {}
            for it in r['entries']:
                nm = by.get(it['addr'], '%04X' % it['addr'])
                a = rows.get(nm, (0, 0, 0))
                rows[nm] = (a[0] + it['incl_cycles'] / FRAME, a[1] + it['excl_cycles'] / FRAME, a[2] + it['calls'])
            tot = ((c1 - c0) & 0xFFFFFFFF) / FRAME
            rows['kid_tick (own)'] = (tot, tot - sum(v[1] for v in rows.values()), 1)
            out.append((tot, rows, r.get('unmatched_returns', 0)))
            e.call('bp_clear'); e.call('bp_add', addr=S2['tick_done']); e.run(400); e.call('bp_clear')
    return out

def pace(work, cut=None):
    """replay mode-0 pacing: work[i] in frames (ml_go to tick_done) -> frames a tick (tick_done to tick_done).
    The tick's start s; FRAMES = floor(t); next start = end if floor(end) - floor(s) >= 4 else floor(s) + 4.
    (The ISR's time inside a halt and the main loop's few T are left out.)"""
    s = 0.0; ends = []
    for i, w in enumerate(work):
        w = max(0.05, w - (cut[i] if cut else 0))
        e = s + w; ends.append(e)
        s = e if math.floor(e) - math.floor(s) >= 4 else math.floor(s) + 4
    return [ends[i + 1] - ends[i] for i in range(len(ends) - 1)]

def stats(v):
    v2 = sorted(v); return sum(v) / len(v), v2[len(v2) // 2], v2[min(len(v2) - 1, int(.9 * (len(v2) - 1) + .5))]

def grouped(rows):
    g = {}
    for lab, names in GROUPS:
        g[lab] = sum(rows[n][1] for n in names if n in rows)
    return g

def main():
    a = sys.argv[1:]
    if not a: sys.exit(__doc__)
    opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d
    if a[0] == 'pace':
        import csv
        rows = list(csv.DictReader(open(a[1])))
        work = [float(r['work']) for r in rows]
        for x in a[2:]:
            m, md, p9 = stats(pace(work, [float(x)] * len(work)))
            print('cut %.2f: mean %.3f median %.2f p90 %.2f' % (float(x), m, md, p9))
        return
    if a[0] != 'profile': sys.exit(__doc__)
    sp = TC.script_path(a[1]); t0, t1 = int(a[2]), int(a[3]); top = int(opt('--top', 30))
    t0 = max(t0, 1)     # (tick 0 holds the level start: its frames are not a tick's)
    P = profile(sp, t0, t1); n = len(P)
    import busyrooms as BR
    fw = BR.frames(sp)
    acc = {}
    for tot, rows, um in P:
        for k, v in rows.items():
            x = acc.get(k, (0, 0, 0)); acc[k] = (x[0] + v[0] / n, x[1] + v[1] / n, x[2] + v[2] / n)
    lt = [p[0] for p in P]
    print('%s ticks %d-%d: logic (kid_tick, entry to return) mean %.3f median %.3f p90 %.3f max %.3f frames a tick; '
          'unmatched returns %d' % (os.path.basename(sp), t0, t0 + n, *stats(lt), max(lt), sum(p[2] for p in P)))
    print('  by exclusive frames a tick:')
    print('    %-34s %7s %7s %7s %8s' % ('routine', 'calls', 'excl', 'incl', 'T/call'))
    for k, (i, x, c) in sorted(acc.items(), key=lambda kv: -kv[1][1])[:top]:
        print('    %-34s %7.1f %7.3f %7.3f %8.0f' % (k, c, x, i, x * FRAME / c if c else 0))
    print('  by inclusive frames a tick:')
    for k, (i, x, c) in sorted(acc.items(), key=lambda kv: -kv[1][0])[:top]:
        print('    %-34s %7.1f %7.3f %7.3f' % (k, c, x, i))
    G = [grouped(r) for _, r, _ in P]
    print('  groups (exclusive, frames a tick): ' + ', '.join('%s %.3f' % (lab, sum(g[lab] for g in G) / n) for lab, _ in GROUPS))
    # pacing
    fr = [f for f, w in fw]; wk = [w for f, w in fw]
    # replay over the whole script (the pacing carries over), the stretch's ticks reported
    rp = pace(wk)
    sl = slice(t0, t0 + n)
    print('  measured: frames mean %.3f median %.2f p90 %.2f; work mean %.3f; ticks at the floor (< 4.05) %d of %d' % (
        *stats(fr[sl]), sum(wk[sl]) / n, sum(1 for f in fr[sl] if f < 4.05), n))
    print('  replayed from the work: frames mean %.3f median %.2f p90 %.2f (the check of the rule)' % stats(rp[t0 - 1:t0 - 1 + n] if t0 else rp[:n]))
    # (rp[i] is the time from tick i's end to tick i+1's end, i.e. tick i+1's frames)
    def whatif(cut):
        full = [0.0] * len(wk)
        for i in range(n): full[t0 + i] = cut[i]
        r = pace(wk, full)
        return stats(r[t0 - 1:t0 - 1 + n] if t0 else r[:n])
    base = whatif([0] * n)[0]
    above = sum(1 for i in range(n) if wk[t0 + i] > 4.0)
    print('  ticks with work above 4 frames: %d of %d' % (above, n))
    for x in (0.05, 0.1, 0.2, 0.3, 0.5):
        m, md, p9 = whatif([min(x, lt[i]) for i in range(n)])
        print('  what-if logic -%.2f every tick: frames mean %.3f (%+.3f) median %.2f p90 %.2f' % (x, m, m - base, md, p9))
    for lab, _ in GROUPS:
        for f in (0.25, 0.5):
            m, md, p9 = whatif([G[i][lab] * f for i in range(n)])
            print('  what-if %-12s cut by %d %%: logic -%.3f, frames mean %.3f (%+.3f)' % (lab, f * 100, sum(G[i][lab] * f for i in range(n)) / n, m, m - base))
    # the trims (docs/perf.md "Kid logic: measured"): each one's saving per tick from that tick's own profile, by the
    # cost model in TRIMS (T-states of the new code counted by hand), then the pacing replayed
    sav = {k: [fn(r) / FRAME for _, r, _ in P] for k, _, fn in TRIMS}
    print('  trims (modelled saving: logic frames a tick; frames a tick after the pacing; median; p90):')
    allc = [0.0] * n
    for k, lab, fn in TRIMS:
        s = sav[k]
        if k in TRIMS_ALL:
            for i in range(n): allc[i] += s[i]
        m, md, p9 = whatif(s)
        print('    %-3s %-52s logic -%.3f  frames %+.3f  median %.2f  p90 %.2f' % (k, lab, sum(s) / n, m - base, md, p9))
    m, md, p9 = whatif(allc)
    print('    %-3s %-52s logic -%.3f  frames %+.3f  median %.2f  p90 %.2f' % ('all', 'A + B + C + D + E + F + G', sum(allc) / n, m - base, md, p9))
    if '--csv' in a:
        with open(opt('--csv'), 'w') as f:
            f.write('tick,work,frames,logic,' + ','.join(l.replace(' ', '_').replace('/', '') for l, _ in GROUPS) + '\n')
            for i in range(n):
                f.write('%d,%.4f,%.4f,%.4f,%s\n' % (t0 + i, wk[t0 + i], fr[t0 + i], lt[i], ','.join('%.4f' % G[i][l] for l, _ in GROUPS)))

if __name__ == '__main__':
    main()
