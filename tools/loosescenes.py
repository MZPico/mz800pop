#!/usr/bin/env python3
"""Loose (falling) floors: the per-tick cost of a floor shaking, falling and landing (docs/perf.md "Speed roadmap").
  find OUTDIR [LEVELS...]     scenes found with kidsim only (as tools/trapscenes.py), per kind the best one of levels
                              1-14 (or LEVELS), written as <kind>_a.txt (everything as in the level) and <kind>_b.txt
                              (the same moves, the screen's loose floors patched to floor: walking alone):
                                shake    the kid walks or runs over loose floors (the most visible shake steps
                                         before a room change or death)
                                fall     the kid sets a floor off and stops; it falls and lands in the room while he
                                         stands
                                fallrun  the same with the kid moving all the time
                                multi    the most ticks with two or more floors falling on the screen
                                ride     the kid stands on a loose floor and falls with it into the room below
  label SCRIPT                every tick's phases (kidsim): K/. the kid moved / stood, R the room changed (a room
                              draw), rel a floor came loose (its tile became empty), land a floor landed (a tile became
                              rubble), sh / sh- a loose floor's picture / modifier only changed, mobN N falling floors
                              drawn (sprite.asm mobs_visible's rule: the drawn room, the room below near its top, the
                              room above near its bottom)
  measure OUTDIR [--jobs N] [--csv OUT]   run every scene (a and b) in the emulator: per scene and phase the frames a
                              tick (tick_done to tick_done; median / p90 / worst), the work (ml_go to tick_done) and
                              a - b on the ticks where the kid is in the same state in a and b
The phase of a tick for the tables: R (a room draw) > land > rel > mob2+ > mob1 > sh > sh- > none; one tick counts in
one phase. The scenes are not committed: `find` regenerates them in ~2 minutes."""
import os, sys, csv
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path[:0] = [os.path.join(ROOT, 'tests'), HERE]
import kidsim
from popdata import Level, T

N = 100
RUN = [(1, 0, 0)] * 24 + [(-1, 0, 0)] * 24
WALK = [(1, 0, 1)] * 30 + [(-1, 0, 1)] * 30
JUMP = [(1, -1, 0)] * 14 + [(-1, -1, 0)] * 14

def pats():
    """name -> one period of moves (repeated to N); xstop: x moves, then the kid stands"""
    p = {'run': RUN, 'walk': WALK, 'jump': JUMP, 'stand': [(0, 0, 0)]}
    for k in (3, 5, 7, 9, 12, 16, 20): p['runstop%d' % k] = [(1, 0, 0)] * k + [(0, 0, 0)] * (N - k)
    for k in (1, 2, 3, 4, 6): p['walkstop%d' % k] = ([(1, 0, 1)] * 6 + [(0, 0, 0)] * 2) * k + [(0, 0, 0)] * N
    return p
PAT = pats()

def moves_for(pat, d):
    p = PAT[pat]; m = (p * (N // len(p) + 1))[:N]
    return [(x * d, y, s) for (x, y, s) in m]

def s8(v): return v - 256 if v >= 128 else v

def loose_frame(m):
    if m & 0x80:
        m &= 0x7F
        if m > 10: return 1
    return m

def screen_tiles(sim, room):
    """(room, pos) of the tiles the shown room's renderer looks at (view.asm vs_runs)"""
    L, R, U, D = sim.links(room)
    out = [(room, p) for p in range(30)]
    if L: out += [(L, p) for p in (9, 19, 29)]
    if U: out += [(U, p) for p in range(20, 30)]
    if D: out += [(D, p) for p in range(10)]
    return out

def mobs_drawn(sim, room):
    """sprite.asm mobs_visible: the falling floors drawn on room's screen"""
    if not room: return 0
    L, R, U, D = sim.links(room); n = 0
    for m in sim.mobs:
        if m['room'] == room:
            if m['y'] < 210: n += 1
        elif m['room'] == D and D:
            if (m['y'] + 17) & 0xFF < 35: n += 1
        elif m['room'] == U and U:
            if m['y'] >= 174: n += 1
    return min(n, 6)

def sim_run(sim, moves, stop_dead=True):
    """per move: (kid state, phases {name: count}, alive)"""
    out = []
    for (x, y, sh) in moves:
        lv = sim.level; K = sim.Kid
        kb = (sim.drawn_room, K.x, K.y, K.frame)
        fg, bg = bytes(lv.fg), bytes(lv.bg); rm0 = sim.drawn_room
        sim.step(x, y, sh)
        if sim.game_over: break
        lv = sim.level; K = sim.Kid; rm = sim.drawn_room
        ka = (rm, K.x, K.y, K.frame)
        c = {}
        if rm != rm0 or not rm: c['R'] = 1
        else:
            for r, p in screen_tiles(sim, rm):
                i = (r - 1) * 30 + p
                t0, t1 = fg[i] & 0x1F, lv.fg[i] & 0x1F
                if t0 != t1:
                    if t0 == T.loose and t1 == T.empty: c['rel'] = c.get('rel', 0) + 1
                    elif t1 in (T.debris, T.torch_with_debris): c['land'] = c.get('land', 0) + 1
                    else: c['tile'] = c.get('tile', 0) + 1
                elif t1 == T.loose and bg[i] != lv.bg[i]:
                    k = 'sh' if loose_frame(bg[i]) != loose_frame(lv.bg[i]) else 'sh-'
                    c[k] = c.get(k, 0) + 1
            n = mobs_drawn(sim, rm)
            if n: c['mob'] = n
        alive = K.alive < 0
        out.append((ka, c, alive, ka != kb))
        if stop_dead and not alive: break
    return out

def labels(sp):
    moves, patches = kidsim.read_script(sp)
    o = kidsim.script_opts(sp)
    sim = kidsim.KidSim(Level(kidsim.script_level(sp)), patches=patches, guards=o['guards'], place=o['place'],
                        sword=o['sword'], time=o['time'], start=o['start'], multi_level=True)
    return sim_run(sim, moves, stop_dead=False)

def phase(c):
    if 'R' in c: return 'R'
    if 'land' in c: return 'land'
    if 'rel' in c: return 'rel'
    if c.get('mob', 0) >= 2: return 'mob2+'
    if c.get('mob', 0) == 1: return 'mob1'
    if 'sh' in c: return 'sh'
    if 'sh-' in c: return 'sh-'
    return 'none'

def write(path, lv, start, moves, patches, note):
    with open(path, 'w') as f:
        f.write('# level %d\n# start %d:%d:%d\n' % (lv, start[0], start[1], start[2]))
        if patches: f.write('# patch %s\n' % ','.join('%d:%d:%d:%d' % p for p in patches))
        f.write('# %s\n' % note)
        for (x, y, s) in moves: f.write('%d %d %d\n' % (x, y, s))

def score(kind, out, room0, below):
    """the scene's score for a kind (0: not that kind)"""
    s = 0
    for i, (ka, c, alive, moved) in enumerate(out):
        rm = ka[0]
        if kind == 'ride':
            if 'R' in c:
                # the kid fell into the room below with a floor drawn there after the room change
                if rm == below and alive and any(o[1].get('mob', 0) for o in out[i + 1:i + 8]): return 100 + i
                return 0
            continue
        if 'R' in c or not alive: break
        if kind == 'shake': s += (c.get('sh', 0) * 3 + c.get('sh-', 0)) if moved else 0
        elif kind == 'fall':
            if c.get('mob') and not moved: s += 2
            if 'land' in c and not moved: s += 10
        elif kind == 'fallrun':
            if c.get('mob') and moved: s += 2
            if 'land' in c and moved: s += 10
        elif kind == 'multi':
            if c.get('mob', 0) >= 2: s += c['mob']
    return s

def loose_patches(sim, room):
    return [(r, p, T.floor, 0) for r, p in screen_tiles(sim, room)
            if sim.level.fg[(r - 1) * 30 + p] & 0x1F == T.loose]

def find(outdir, levels):
    os.makedirs(outdir, exist_ok=True)
    best = {}
    kinds = ('shake', 'fall', 'fallrun', 'multi', 'ride')
    for lv in levels:
        L = Level(lv); sim0 = kidsim.KidSim(Level(lv))
        for i in range(720):
            if L.fg[i] & 0x1F != T.loose: continue
            room, pos = i // 30 + 1, i % 30; row, col = pos // 10, pos % 10
            below = sim0.links(room)[3]
            starts = []
            for dc in range(-4, 5):
                c = col + dc
                if not 0 <= c <= 9: continue
                t = L.fg[(room - 1) * 30 + row * 10 + c] & 0x1F
                if t in (T.floor, T.loose, T.torch, T.debris, T.potion) or dc == 0:
                    for d in ((0,) if dc < 0 else (-1,) if dc > 0 else (0, -1)): starts.append((room, row * 10 + c, d))
            for st in starts:
                d = 1 if st[2] == 0 else -1
                for pat in PAT:
                    if pat == 'stand' and st[1] != pos: continue
                    mv = moves_for(pat, d)
                    sim = kidsim.KidSim(Level(lv), start=st, multi_level=True)
                    out = sim_run(sim, mv)
                    for k in kinds:
                        sc = score(k, out, room, below)
                        if k == 'ride' and sc and pat == 'stand': sc += 1000     # the kid stands on the floor
                        if sc and (sc > best.get(k, (0,))[0]):
                            best[k] = (sc, lv, st, pat, mv, len(out), (room, pos))
        print('level %d done: %s' % (lv, ' '.join('%s %s' % (k, v[0]) for k, v in sorted(best.items()))), flush=True)
    for k, (sc, lv, st, pat, mv, n, at) in sorted(best.items()):
        sim0 = kidsim.KidSim(Level(lv))
        mv = mv[:min(N, n + 12)]
        note = '%s: loose floor %d:%d, level %d, start %d:%d:%d, pattern %s, score %d (tools/loosescenes.py)' % (
            k, at[0], at[1], lv, st[0], st[1], st[2], pat, sc)
        write(os.path.join(outdir, k + '_a.txt'), lv, st, mv, [], note)
        write(os.path.join(outdir, k + '_b.txt'), lv, st, mv, loose_patches(sim0, st[0]), note + '; the loose floors patched to floor')
        print('%-8s level %2d floor %s start %s pattern %-10s %3d ticks score %d' % (k, lv, at, st, pat, n, sc))

def frames(sp):
    import busyrooms as BR
    return BR.frames(sp)

def pct(v, q):
    v = sorted(v); return v[min(len(v) - 1, int(q * (len(v) - 1) + 0.5))] if v else float('nan')

def measure(outdir, jobs=4, csv_out=None):
    from concurrent.futures import ProcessPoolExecutor
    scripts = sorted(os.path.join(outdir, f) for f in os.listdir(outdir) if f.endswith('.txt') and f[-6:-4] in ('_a', '_b'))
    with ProcessPoolExecutor(jobs) as ex: F = dict(zip(scripts, ex.map(frames, scripts)))
    rows = []
    mean = lambda v: sum(v) / len(v) if v else float('nan')
    for sa in scripts:
        if not sa.endswith('_a.txt'): continue
        sb = sa[:-6] + '_b.txt'
        La, Lb = labels(sa), labels(sb)
        n = min(len(F[sa]), len(La))
        print('%s (%d ticks)' % (os.path.basename(sa)[:-6], n))
        ph = {}
        for t in range(2, n):
            p = phase(La[t][1]) + ('' if La[t][3] else ' (kid still)')
            ph.setdefault(p, []).append(t)
        for p, ts in sorted(ph.items()):
            fa = [F[sa][t][0] for t in ts]; wa = [F[sa][t][1] for t in ts]
            same = [t for t in ts if t < len(F[sb]) and t < len(Lb) and Lb[t][0] == La[t][0]]
            d = [F[sa][t][1] - F[sb][t][1] for t in same]
            print('  %-18s %3d ticks  frames %5.2f / %5.2f / %5.2f  work median %5.2f  a-b (%d ticks) median %5.2f mean %5.2f' % (
                p, len(ts), pct(fa, .5), pct(fa, .9), max(fa), pct(wa, .5), len(same), pct(d, .5), mean(d)))
        for t in range(n):
            rows.append([os.path.basename(sa)[:-6], t, phase(La[t][1]), int(La[t][3]), '%.3f' % F[sa][t][0], '%.3f' % F[sa][t][1],
                         '%.3f' % F[sb][t][1] if t < len(F[sb]) and t < len(Lb) and Lb[t][0] == La[t][0] else '',
                         ' '.join('%s%d' % kv for kv in sorted(La[t][1].items()))])
    if csv_out:
        with open(csv_out, 'w', newline='') as f:
            w = csv.writer(f); w.writerow(['scene', 'tick', 'phase', 'moved', 'a_frames', 'a_work', 'b_work', 'labels'])
            w.writerows(rows)

def main():
    a = sys.argv[1:]
    if not a: sys.exit(__doc__)
    if a[0] == 'find':
        find(a[1], [int(v) for v in a[2:]] or range(1, 15))
    elif a[0] == 'label':
        for t, (ka, c, alive, moved) in enumerate(labels(a[1])):
            print('%3d %s %-6s %s %s' % (t, 'K' if moved else '.', phase(c), ka, ' '.join('%s%d' % kv for kv in sorted(c.items()))))
    elif a[0] == 'measure':
        jobs = int(a[a.index('--jobs') + 1]) if '--jobs' in a else 4
        co = a[a.index('--csv') + 1] if '--csv' in a else None
        measure(a[1], jobs, co)

if __name__ == '__main__':
    main()
