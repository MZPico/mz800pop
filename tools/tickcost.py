#!/usr/bin/env python3
"""Per-tick cost of the M4 game against what the tick shows (docs/perf.md "Gates and spikes: per-tick measurements").
Runs a control script in the emulator (the setup of tools/perfcheck.py: a tracepoint at tick_done, no stops) and the
same script in tools/kidsim.py, and labels every tick by what changed on the shown screen:
  K  the kid moved (room, x, y or frame changed)            .  the kid stood
  G  a gate's visible bar position min(mod, 188) / 4 changed (a gate of the shown room in columns 0-8, or of the
     left room's column 9: the gates view.asm vrd_gate redraws); g = a gate's modifier changed, nothing visible
  S  a spike's picture changed (get_spike_frame: modifier & 0x80 -> 5, else the modifier; a shown-room spike);
     s = a spike's modifier changed, the picture did not (the 15 ticks it stays out, 0x8F..0x81)
  R  the room changed (left out of the class summary)
usage: tickcost.py SCRIPT [T0 T1] [--series] [--profile t,t,...] [--top N] [--csv OUT]
       tickcost.py --scene PREFIX [T0 T1] [--series]   (the four scripts PREFIX_[abcd].txt of tools/trapscenes.py)
  SCRIPT: a path, or a name in tests/m4_scripts, m5_scripts, m6_scripts, m7_scripts, perf_scripts
  --series        print every tick of T0..T1 (frames, label, kid, the trap modifiers that changed)
  --profile LIST  profile each listed tick alone (mz800emu's call profiler, one tick) and print its routines
  --rects LIST    the redraw events of each listed tick (tile regenerations, dirty rects, rect runs, object chunks)
The tick numbering is the script's move index: tick t's cost is from the end of tick t-1 (tick_done) to its own end."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path[:0] = [os.path.join(ROOT, 'tests'), HERE]
import m4_game as G, kidsim
from popdata import Level, T
from emu import Emu
FRAME = 312 * 228

def script_path(s):
    if os.path.exists(s): return s
    for d in ('m4_scripts', 'm5_scripts', 'm6_scripts', 'm7_scripts', 'perf_scripts'):
        p = os.path.join(ROOT, 'tests', d, s if s.endswith('.txt') else s + '.txt')
        if os.path.exists(p): return p
    sys.exit('no script ' + s)

def spike_frame(m): return 5 if m & 0x80 else m

def sim_labels(sp):
    """per move: (label, kid tuple, notes) from kidsim"""
    moves, patches = kidsim.read_script(sp); keys = kidsim.read_keys(sp)
    o = kidsim.script_opts(sp)
    sim = kidsim.KidSim(Level(kidsim.script_level(sp)), patches=patches, guards=o['guards'], place=o['place'],
                        sword=o['sword'], time=o['time'], start=o['start'], multi_level=True)
    out = []
    for (x, y, sh), k in zip(moves, keys):
        K = sim.Kid
        kb = (sim.drawn_room, K.x, K.y, K.frame)
        lv = sim.level; lvn = lv.number
        snap = (bytes(lv.fg), bytes(lv.bg))
        sim.step(x, y, sh, k)
        if sim.game_over: break
        lv = sim.level; K = sim.Kid
        ka = (sim.drawn_room, K.x, K.y, K.frame)
        rm = sim.drawn_room
        lab = ''; notes = []
        if kb[0] != ka[0] or not rm or lv.number != lvn:
            out.append(('R', ka, '')); continue
        kid = 'K' if kb != ka else '.'
        tiles = [(rm, p, 'own') for p in range(30)]
        left = sim.links(rm)[0]
        if left: tiles += [(left, p, 'left') for p in (9, 19, 29)]
        g = s = ''
        for r, p, kind in tiles:
            i = (r - 1) * 30 + p
            t = lv.fg[i] & 0x1F; m0, m1 = snap[1][i], lv.bg[i]
            if m0 == m1 or (snap[0][i] & 0x1F) != t: continue
            if t == T.gate:
                if kind == 'own' and p % 10 == 9: continue
                vis = min(m0, 188) // 4 != min(m1, 188) // 4
                g = 'G' if vis or g == 'G' else 'g'
                notes.append('gate%s%d:%d->%d' % ('L' if kind == 'left' else '', p, m0, m1))
            elif t == T.spike and kind == 'own':
                vis = spike_frame(m0) != spike_frame(m1)
                s = 'S' if vis or s == 'S' else 's'
                notes.append('spike%d:%02x->%02x' % (p, m0, m1))
        col = K.curr_col if K.curr_col is not None else -1
        out.append((kid + (g or '-') + (s or '-'), ka, ' '.join(notes) + ' kidcol=%d row=%d' % (col, K.curr_row) +
                    (' dead' if K.alive >= 0 else '')))
    return out

def emu_setup(e, sp):
    moves, patches = kidsim.read_script(sp)
    S = G.setup(e, kidsim.script_level(sp), opts=kidsim.script_opts(sp))
    enc = bytes([((x + 1) & 3) | (((y + 1) & 3) << 2) | (0x10 if sh else 0) for (x, y, sh) in moves]) + b'\xff'
    G.write_pack(e, enc, 5, G.SCRIPT)
    e.call('mem_write', addr=G.SCRIPT_PTR, data_hex='%02x%02x' % (G.SCRIPT & 255, G.SCRIPT >> 8))
    e.call('bp_clear'); e.call('bp_add', addr=S['level_ready']); e.run(400)
    for (rm, p, t, m) in patches:
        e.call('mem_write', addr=G.LEVEL_ADDR + (rm - 1) * 30 + p, data_hex='%02x' % t)
        e.call('mem_write', addr=G.LEVEL_ADDR + 720 + (rm - 1) * 30 + p, data_hex='%02x' % m)
    e.call('bp_clear')
    return S, len(moves)

def emu_frames(sp, last):
    """frames of each tick 0..last-1 (as tools/perfcheck.py: a tracepoint at tick_done)"""
    with Emu() as e:
        S, n = emu_setup(e, sp); last = min(last, n)
        size = G.rd_size(e)
        cyc = lambda: e.call('get_raster_pos')['total_cycles']
        marks = [cyc()]
        e.trace_add(S['tick_done'])
        for r in e.collect(200, stop=lambda r: len(marks) > last):
            marks.append(r['cycles'])
        e.trace_clear()
    return size, [((marks[i + 1] - marks[i]) & 0xFFFFFFFF) / FRAME for i in range(len(marks) - 1)]

def emu_profile(sp, ticks, top):
    """the call profile of each tick in ticks, alone"""
    res = {}
    with Emu() as e:
        S, n = emu_setup(e, sp)
        names = {}
        for k, v in S.items(): names.setdefault(v, k)
        e.call('bp_add', addr=S['tick_done'])
        t = 0
        for want in sorted(ticks):
            while t < want: e.run(400); t += 1
            e.call('profiler_reset'); e.call('profiler_start')
            c0 = e.call('get_raster_pos')['total_cycles']
            e.run(400); t += 1
            c1 = e.call('get_raster_pos')['total_cycles']
            e.call('profiler_stop')
            r = e.call('profiler_get', limit=1000)
            rows = [(it['incl_cycles'] / FRAME, it['excl_cycles'] / FRAME, it['calls'], names.get(it['addr'], '%04X' % it['addr']))
                    for it in r['entries']]
            res[want] = (((c1 - c0) & 0xFFFFFFFF) / FRAME, rows)
    return res

def emu_rects(sp, ticks):
    """per listed tick the redraw events in order: tile_regen (A = the tile tag), gate_redraw, dr_run (the dirty rect
    DR_X0, X1, Y0, Y1: byte columns, rows), run_rect (CRX, CRY, CRW, CRH, RR_SHONLY), obj_chunk (CRX, CRY, CRW, CRH)"""
    with Emu() as e:
        S, n = emu_setup(e, sp)
        last = max(ticks) + 1
        tp = {}
        tp[e.trace_add(S['tick_done'])] = 'tick'
        tp[e.trace_add(S['tile_regen'], regs=('AF',))] = 'regen'
        tp[e.trace_add(S['gate_redraw'])] = 'gate_redraw'
        tp[e.trace_add(S['tile_redraw'], regs=('AF',))] = 'tile_redraw'
        tp[e.trace_add(S['dr_run'], mem=((S['DR_X0'], 4),))] = 'dr_run'
        tp[e.trace_add(S['run_rect'], mem=((S['CRX'], 4), (S['RR_SHONLY'], 1)))] = 'run_rect'
        tp[e.trace_add(S['obj_chunk'], mem=((S['CRX'], 4),))] = 'obj_chunk'
        ev = {}; t = 0; c0 = None
        for r in e.collect(200, stop=lambda r: t >= last):
            kind = tp.get(r.get('id'), None)
            if kind is None:      # (records may carry the address only)
                kind = {S['tick_done']: 'tick', S['tile_regen']: 'regen', S['gate_redraw']: 'gate_redraw', S['tile_redraw']: 'tile_redraw',
                        S['dr_run']: 'dr_run', S['run_rect']: 'run_rect', S['obj_chunk']: 'obj_chunk'}[r['addr']]
            if kind == 'tick':
                t += 1; continue
            if t in ticks:
                m = r.get('mem', [])
                if kind in ('regen', 'tile_redraw'): d = 'tag %d' % (r['regs']['AF'] >> 8)
                elif kind == 'dr_run': x0, x1, y0, y1 = m[0]; d = 'x %d-%d y %d-%d (%d x %d bytes)' % (x0, x1, y0, y1, x1 - x0, y1 - y0)
                elif kind == 'run_rect': x, y, w, h = m[0]; d = 'x %d y %d w %d h %d%s' % (x, y, w, h, ' shadow only' if m[1][0] else '')
                elif kind == 'obj_chunk': x, y, w, h = m[0]; d = 'x %d y %d w %d h %d' % (x, y, w, h)
                else: d = ''
                ev.setdefault(t, []).append('%-12s %s' % (kind, d))
        e.trace_clear()
    return ev

def pct(v, q):
    v = sorted(v); return v[min(len(v) - 1, int(q * (len(v) - 1) + 0.5))]

def scene(prefix, t0, t1, series):
    """the four scripts of a tools/trapscenes.py scene: a = kid moves + trap, b = kid moves, c = kid stands + trap,
    d = kid stands; per class of a's ticks: a, b, c, d and the combination's excess a - b - (c - d), on the ticks where
    a's and b's kid (and c's and d's) are the same"""
    L = {}; F = {}
    for k in 'abcd':
        sp = prefix + '_%s.txt' % k
        L[k] = sim_labels(sp); size, F[k] = emu_frames(sp, t1)
    n = min(len(F[k]) for k in 'abcd'); n = min(n, t1)
    print('%s ticks %d-%d, RAM disk %s' % (os.path.basename(prefix), t0, n, size))
    cls = {}; rows = []
    for t in range(t0, n):
        la = L['a'][t]
        if la[0] == 'R' or la[1] != L['b'][t][1] or L['c'][t][1] != L['d'][t][1] or 'dead' in la[2]: continue
        v = [F[k][t] for k in 'abcd']
        lab = la[0] + '/' + L['c'][t][0][1:]
        cls.setdefault(lab, []).append(v); rows.append((t, lab, v, la[2]))
    if series:
        for t, lab, v, nt in rows:
            print('%4d %-7s a %6.2f b %6.2f c %6.2f d %6.2f  excess %+6.2f  %s' % (t, lab, v[0], v[1], v[2], v[3], v[0] - v[1] - v[2] + v[3], nt))
    print('%-8s %5s | %-17s | %-17s | %-17s | %-17s | %6s' % ('a/c', 'ticks', 'a med p90 worst', 'b med p90 worst',
          'c med p90 worst', 'd med p90 worst', 'excess'))
    for lab in sorted(cls):
        v = cls[lab]; col = lambda i: [x[i] for x in v]
        f = lambda i: '%5.2f %5.2f %5.2f' % (pct(col(i), .5), pct(col(i), .9), max(col(i)))
        ex = [x[0] - x[1] - x[2] + x[3] for x in v]
        print('%-8s %5d | %s | %s | %s | %s | %+6.2f' % (lab, len(v), f(0), f(1), f(2), f(3), sum(ex) / len(ex)))

def main():
    a = sys.argv[1:]
    opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d
    pos = [x for i, x in enumerate(a) if not x.startswith('--') and (i == 0 or not a[i - 1] in ('--profile', '--top', '--csv', '--rects'))]
    if '--scene' in a:
        scene(pos[0], int(pos[1]) if len(pos) > 1 else 1, int(pos[2]) if len(pos) > 2 else 120, '--series' in a); return
    sp = script_path(pos[0])
    labels = sim_labels(sp)
    t0 = int(pos[1]) if len(pos) > 1 else 0
    t1 = int(pos[2]) if len(pos) > 2 else len(labels)
    t1 = min(t1, len(labels))
    if '--rects' in a:
        ticks = [int(v) for v in opt('--rects').split(',')]
        ev = emu_rects(sp, set(ticks))
        for t in ticks:
            print('tick %d %s %s' % (t, labels[t][0], labels[t][2]))
            for x in ev.get(t, []): print('   ' + x)
        return
    if '--profile' in a:
        ticks = [int(v) for v in opt('--profile').split(',')]
        top = int(opt('--top', 25))
        for t, (fr, rows) in sorted(emu_profile(sp, ticks, top).items()):
            print('tick %d: %.2f frames  %s  %s' % (t, fr, labels[t][0] if t < len(labels) else '?', labels[t][2] if t < len(labels) else ''))
            rows.sort(key=lambda x: -x[0])
            print('  %-24s %6s %7s %7s' % ('routine', 'calls', 'incl', 'excl'))
            for incl, excl, calls, nm in rows[:top]: print('  %-24s %6d %7.2f %7.2f' % (nm, calls, incl, excl))
        return
    size, fr = emu_frames(sp, t1)
    print('%s ticks %d-%d, RAM disk %s' % (os.path.basename(sp), t0, t1, size))
    rows = [(t, fr[t], labels[t]) for t in range(t0, min(t1, len(fr)))]
    if '--csv' in a:
        with open(opt('--csv'), 'w') as f:
            f.write('tick,frames,label,room,x,y,frame,notes\n')
            for t, v, (lab, k, nt) in rows: f.write('%d,%.3f,%s,%d,%d,%d,%d,%s\n' % (t, v, lab, k[0], k[1], k[2], k[3], nt))
    if '--series' in a:
        for t, v, (lab, k, nt) in rows: print('%4d %6.2f %s  room %2d x %3d y %3d fr %3d  %s' % (t, v, lab, k[0], k[1], k[2], k[3], nt))
    cls = {}
    for t, v, (lab, k, nt) in rows:
        if lab == 'R': continue
        cls.setdefault(lab, []).append(v)
    print('%-6s %5s %7s %7s %7s %7s' % ('class', 'ticks', 'median', 'p90', 'worst', 'mean'))
    for lab in sorted(cls):
        v = cls[lab]
        print('%-6s %5d %7.2f %7.2f %7.2f %7.2f' % (lab, len(v), pct(v, .5), pct(v, .9), max(v), sum(v) / len(v)))

if __name__ == '__main__':
    main()
