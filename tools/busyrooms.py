#!/usr/bin/env python3
"""Busy rooms: the per-tick cost of a room's animated objects (docs/perf.md "Busy rooms: per-room and per-object costs").
  census [--top N]            rooms of levels 1-14 by the animated objects drawn on their screen (own room; the left
                              room's column 9 for torches and gates), with the buttons whose gate is drawn there
  find OUTDIR LV:ROOM ... | --worst   write the scenes of each room, found with kidsim only (as tools/trapscenes.py):
                                l<LV>r<ROOM>_walk_a   the kid moves in the room (the start and pattern with the most
                                                      weighted visible object changes before a room change or death;
                                                      starts on buttons press them), everything animates
                                l<LV>r<ROOM>_walk_b   the same moves, every animated tile of the screen patched to
                                                      floor (torches, potions, the sword, choppers, spikes, loose
                                                      floors, buttons; gates stay as they are): walking alone
                                l<LV>r<ROOM>_walk_<k> the same moves, only the objects of kind k kept
                                l<LV>r<ROOM>_stand_a/b the kid stands (where most changes happen), all / none
  measure PREFIX ... | OUTDIR --worst  [--csv OUT] [--jobs N]  run each scene's scripts in the emulator (N at a
                              time, default 4): per scene the frames a tick (tick_done to tick_done, paced to 4 at
                              least) of a and b and their work (ml_go, after the pacing wait, to tick_done), and per
                              kind the work of the only-k variant minus b's, on the ticks where the kid is in the start
                              room, alive and in the same state; --csv writes every tick with its change counts
  fit CSV ... [--whatif k=v,...]  least squares over the ticks: (a - b) = sum over kinds of n_kind(tick) x c_kind;
                              per scene the model against the measurement, and the frames a tick with the costs
                              of some kinds replaced (a planned fix)
The kinds a tick is labelled with (kidsim; the changes the renderer reacts to, by its path in view.asm vrd_one):
  torch    a flame frame (torch_fast: op patch, the flame laid in the object pass)
  potion   a bubble frame (bubble_redraw: fore op patch)
  sword / sword-   the glint appears or goes (modifier 1) / the modifier only (both tile_redraw: 3 regenerations)
  chomp / chomp-   the chopper's picture changes / its modifier only (both tile_redraw)
  gate / gate-     the visible bar position min(mod, 188) / 4 (gate_redraw) / the modifier only (nothing drawn)
  spike / spike-   spike_frame changes (spike_redraw) / the modifier only (nothing drawn)
  loose / loose-   loose_frame changes / the modifier only (tile_redraw)
  door     the level door's modifier (tile_redraw)       button   a button drawn pressed / released (tile_redraw)
  tile     a tile byte changed (a loose floor falls away: tile_redraw)"""
import os, sys, csv
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path[:0] = [os.path.join(ROOT, 'tests'), HERE]
import kidsim
from popdata import Level, T, CHOMPER_FRAM1
import trapscenes as TS

N = 100
KINDS = ['torch', 'potion', 'sword', 'sword-', 'chomp', 'chomp-', 'gate', 'gate-', 'spike', 'spike-', 'loose', 'loose-',
         'door', 'button', 'tile']
W = {'torch': .3, 'potion': .6, 'sword': 1.5, 'sword-': 1.5, 'chomp': 4, 'chomp-': 1.5, 'gate': 5, 'gate-': 0, 'spike': 5,
     'spike-': 0, 'loose': 3, 'loose-': 1.5, 'door': 5, 'button': 2, 'tile': 3}   # the search's prior weights (frames)
# the rooms measured in docs/perf.md "Busy rooms" (census order, the sword room last); `--worst` stands for them
WORST = ['5:24', '3:16', '8:23', '10:10', '8:4', '9:1', '10:1', '7:19', '5:8', '2:18', '7:7', '9:22', '1:5', '5:7',
         '10:14', '9:9', '11:2', '4:18', '8:5', '1:15']
PAT = dict(TS.PAT); PAT['stand'] = [(0, 0, 0)]
ANIM = (T.torch, T.torch_with_debris, T.potion, T.sword, T.chomper, T.spike, T.loose, T.opener, T.closer)
KIND_TILES = {'torch': (T.torch, T.torch_with_debris), 'potion': (T.potion,), 'sword': (T.sword,), 'chomper': (T.chomper,),
              'spike': (T.spike,), 'loose': (T.loose,), 'gate': (T.opener, T.closer)}

def spike_frame(m): return 5 if m & 0x80 else m
def chomp_pic(m): return (CHOMPER_FRAM1[min(m & 0x7F, 6)], m & 0x80)
def loose_frame(m):
    if m & 0x80:
        m &= 0x7F
        if m > 10: return 1
    return m

def screen_tiles(lv, room):
    """(room, pos, where) of the tiles whose change the shown room's renderer looks at (view.asm vs_runs)"""
    L, R, U, D = lv.links(room)
    out = [(room, p, 'own') for p in range(30)]
    if L: out += [(L, p, 'left') for p in (9, 19, 29)]
    if U: out += [(U, p, 'above') for p in range(20, 30)]
    if D: out += [(D, p, 'below') for p in range(10)]
    return out

def census():
    rows = []
    for n in range(1, 15):
        L = Level(n)
        for room in range(1, 25):
            c = {}
            left = L.links(room)[0]
            for r, p, w in screen_tiles(L, room):
                if w in ('above', 'below'): continue
                t = L.fg[(r - 1) * 30 + p] & 0x1F
                k = None
                if t in (T.torch, T.torch_with_debris): k = 'torch' if (w == 'own') == (p % 10 != 9) else None
                elif t == T.gate: k = 'gate' if (w == 'own') == (p % 10 != 9) else None
                elif w != 'own': k = None
                elif t == T.potion: k = 'potion'
                elif t == T.sword: k = 'sword'
                elif t == T.chomper: k = 'chomper'
                elif t == T.spike: k = 'spike'
                elif t == T.loose: k = 'loose'
                elif t == T.level_door_left: k = 'door'
                elif t in (T.opener, T.closer):
                    if any((rr == room and q % 10 != 9) or (rr == left and q % 10 == 9) for rr, q in TS.gate_of(L, room, p)):
                        k = 'button'
                if k: c[k] = c.get(k, 0) + 1
            if c: rows.append((n, room, c))
    return rows

def busy_score(c):
    """a ranking of the census: every-tick objects 1, triggered objects 2"""
    return sum(c.get(k, 0) for k in ('torch', 'potion', 'sword')) + 2 * sum(c.get(k, 0) for k in ('chomper', 'button', 'spike', 'gate'))

def labels(sp):
    """per move: (kid state, {kind: count}, alive in the start room) from kidsim"""
    moves, patches = kidsim.read_script(sp)
    o = kidsim.script_opts(sp)
    sim = kidsim.KidSim(Level(kidsim.script_level(sp)), patches=patches, guards=o['guards'], place=o['place'],
                        sword=o['sword'], time=o['time'], start=o['start'], multi_level=True)
    return sim_run(sim, moves)

def sim_run(sim, moves, stop=False):
    out = []; room0 = None
    for (x, y, sh) in moves:
        lv = sim.level; K = sim.Kid
        kb = (sim.drawn_room, K.x, K.y, K.frame)
        fg, bg, dl2 = bytes(lv.fg), bytes(lv.bg), bytes(sim.dl2)
        rm0 = sim.drawn_room
        sim.step(x, y, sh)
        if sim.game_over: break
        lv = sim.level; K = sim.Kid; rm = sim.drawn_room
        ka = (rm, K.x, K.y, K.frame)
        if room0 is None: room0 = rm
        ok = rm == rm0 == room0 and K.alive < 0 and rm
        if not ok and stop: break
        c = {}
        if ok:
            for r, p, w in screen_tiles(lv, rm):
                i = (r - 1) * 30 + p
                t = lv.fg[i] & 0x1F; m0, m1 = bg[i], lv.bg[i]
                if (fg[i] & 0x1F) != t: c['tile'] = c.get('tile', 0) + 1; continue
                if t in (T.opener, T.closer):
                    def pressed(d): return (d[m1] & 0x1F) > 1
                    if pressed(dl2) != pressed(sim.dl2): c['button'] = c.get('button', 0) + 1
                    continue
                if m0 == m1: continue
                k = None
                if t in (T.torch, T.torch_with_debris):
                    if (w == 'own' and p % 10 != 9) or w == 'left': k = 'torch'
                elif t == T.gate:
                    if (w == 'own' and p % 10 != 9) or w == 'left':
                        k = 'gate' if min(m0, 188) // 4 != min(m1, 188) // 4 else 'gate-'
                elif t == T.spike:
                    if w != 'below': k = 'spike' if spike_frame(m0) != spike_frame(m1) else 'spike-'
                elif t == T.potion: k = 'potion' if w == 'own' and (m0 ^ m1) & 0xF8 == 0 else 'loose-'
                elif t == T.sword: k = 'sword' if (m0 == 1) != (m1 == 1) else 'sword-'
                elif t == T.chomper: k = 'chomp' if chomp_pic(m0) != chomp_pic(m1) else 'chomp-'
                elif t == T.loose: k = 'loose' if loose_frame(m0) != loose_frame(m1) else 'loose-'
                elif t == T.level_door_left: k = 'door'
                if k: c[k] = c.get(k, 0) + 1
        out.append((ka, c, bool(ok), ka != kb))
    return out

def write(path, lv, start, moves, patches, note):
    with open(path, 'w') as f:
        f.write('# level %d\n# start %d:%d:%d\n' % (lv, start[0], start[1], start[2]))
        if patches: f.write('# patch %s\n' % ','.join('%d:%d:%d:%d' % p for p in patches))
        f.write('# %s\n' % note)
        for (x, y, s) in moves: f.write('%d %d %d\n' % (x, y, s))

def patch_away(L, room, keep=()):
    """patches that turn the screen's animated tiles to floor, except the kinds in keep"""
    out = []
    for r, p, w in screen_tiles(L, room):
        t = L.fg[(r - 1) * 30 + p] & 0x1F
        if t not in ANIM: continue
        if any(t in KIND_TILES[k] for k in keep): continue
        out.append((r, p, T.floor, 0))
    return out

def opened_gates(L, room):
    """a closer drops only an open gate: the gates of the room's closers start open (as tools/trapscenes.py)"""
    out = []
    left = L.links(room)[0]
    for p in range(30):
        if L.fg[(room - 1) * 30 + p] & 0x1F == T.closer:
            out += [(r, q, T.gate, 188) for (r, q) in TS.gate_of(L, room, p)]
    return out

def score(sim_out, walk):
    s = 0
    for ka, c, ok, moved in sim_out:
        if not ok: break
        if walk and not moved: continue
        s += sum(W[k] * v for k, v in c.items())
    return s

def find(outdir, lv, room):
    L = Level(lv)
    base = opened_gates(L, room)
    starts = []
    for p in range(30):
        t = L.fg[(room - 1) * 30 + p] & 0x1F
        if t in (T.floor, T.torch, T.torch_with_debris, T.opener, T.closer, T.potion, T.sword, T.stuck, T.dpress if hasattr(T, 'dpress') else T.floor,
                 T.debris, T.doortop_with_floor, T.bigpillar_bottom, T.level_door_left):
            starts += [(room, p, d) for d in (0, -1)]
    best = {}
    for st in starts:
        d = 1 if st[2] == 0 else -1
        for pat in PAT:
            mv = TS.moves_for(pat, d) if pat != 'stand' else [(0, 0, 0)] * N
            sim = kidsim.KidSim(Level(lv), patches=base, start=st, multi_level=True)
            out = sim_run(sim, mv, stop=True)
            kind = 'stand' if pat == 'stand' else 'walk'
            if kind == 'walk' and len(out) < 40: continue
            sc = score(out, kind == 'walk')
            if sc > best.get(kind, (-1,))[0]: best[kind] = (sc, st, pat, mv, len(out))
    name = os.path.join(outdir, 'l%02dr%02d' % (lv, room))
    present = set()
    for r, p, w in screen_tiles(L, room):
        t = L.fg[(r - 1) * 30 + p] & 0x1F
        for k, ts in KIND_TILES.items():
            if t in ts: present.add(k)
    res = []
    for kind, (sc, st, pat, mv, n) in sorted(best.items()):
        mv = mv[:n]
        note = '%s in level %d room %d, start %d:%d:%d, pattern %s, %d ticks in the room, score %.1f (tools/busyrooms.py)' % (
            kind, lv, room, st[0], st[1], st[2], pat, n, sc)
        write(name + '_%s_a.txt' % kind, lv, st, mv, base, note)
        write(name + '_%s_b.txt' % kind, lv, st, mv, base + patch_away(L, room), note + '; every animated tile patched to floor')
        if kind == 'walk' and len(present) > 1:
            for k in sorted(present):
                write(name + '_%s_%s.txt' % (kind, k), lv, st, mv, base + patch_away(L, room, keep=(k,)), note + '; only %s kept' % k)
        res.append((kind, st, pat, n, sc))
    return res

# ---------------------------------------------------------------- the emulator side
def frames(sp):
    """per tick: (frames from tick_done to tick_done, the work: frames from ml_go, the tick's start after the pacing
    wait, to tick_done)"""
    import tickcost as TC
    from emu import Emu
    n = len(kidsim.read_script(sp)[0])
    with Emu() as e:
        S, n = TC.emu_setup(e, sp)
        cyc = lambda: e.call('get_raster_pos')['total_cycles']
        done = [cyc()]; go = []
        i_go = e.trace_add(S['ml_go']); i_done = e.trace_add(S['tick_done'])
        for r in e.collect(200, stop=lambda r: len(done) > n):
            if r.get('id') == i_go or (r.get('id') is None and r['addr'] == S['ml_go']): go.append(r['cycles'])
            else: done.append(r['cycles'])
        e.trace_clear()
    F = TC.FRAME
    return [(((done[i + 1] - done[i]) & 0xFFFFFFFF) / F, ((done[i + 1] - go[i]) & 0xFFFFFFFF) / F) for i in range(min(len(done) - 1, len(go)))]

def pct(v, q):
    v = sorted(v); return v[min(len(v) - 1, int(q * (len(v) - 1) + 0.5))] if v else float('nan')

def measure(prefixes, csv_out=None, jobs=4):
    """per scene and kind (walk, stand): the frames a tick (paced: tick_done to tick_done; median / p90 / worst) and
    the work (ml_go to tick_done: the tick without the pacing wait) of a and b, on the ticks after the level start
    where the kid is in the start room, alive, and in the same state in a and b; for every only-kind variant k its
    work minus b's on its own matching ticks"""
    from concurrent.futures import ProcessPoolExecutor
    scripts = []
    for pre in prefixes:
        d = os.path.dirname(pre) or '.'; b = os.path.basename(pre)
        scripts += sorted(os.path.join(d, f) for f in os.listdir(d) if f.startswith(b + '_') and f.endswith('.txt'))
    with ProcessPoolExecutor(jobs) as ex: F = dict(zip(scripts, ex.map(frames, scripts)))
    rows = []
    mean = lambda v: sum(v) / len(v) if v else float('nan')
    for pre in prefixes:
        d = os.path.dirname(pre) or '.'; b = os.path.basename(pre)
        for kind in ('walk', 'stand'):
            sa = os.path.join(d, '%s_%s_a.txt' % (b, kind)); sb = os.path.join(d, '%s_%s_b.txt' % (b, kind))
            if sa not in F: continue
            La, Lb = labels(sa), labels(sb)
            n = min(len(F[sa]), len(F[sb]), len(La), len(Lb))
            ticks = [t for t in range(2, n) if La[t][2] and La[t][0] == Lb[t][0]]
            pa = [F[sa][t][0] for t in ticks]; pb = [F[sb][t][0] for t in ticks]
            wa = [F[sa][t][1] for t in ticks]; wb = [F[sb][t][1] for t in ticks]
            tot = {}
            for t in ticks:
                for k, v in La[t][1].items(): tot[k] = tot.get(k, 0) + v
            print('%s %-5s %3d ticks | frames a %5.2f / %5.2f / %5.2f  b %5.2f | work a %5.2f (mean %5.2f)  b %5.2f (mean %5.2f)'
                  '  a-b mean %5.2f | changes a tick: %s' % (
                b, kind, len(ticks), pct(pa, .5), pct(pa, .9), max(pa) if pa else 0, pct(pb, .5), pct(wa, .5), mean(wa),
                pct(wb, .5), mean(wb), mean(wa) - mean(wb), ' '.join('%s %.2f' % (k, v / len(ticks)) for k, v in sorted(tot.items()))))
            rows.append((b, kind, ticks, F[sa], F[sb], La))
            for s in sorted(F):
                if os.path.basename(s).startswith('%s_%s_' % (b, kind)) and s not in (sa, sb):
                    k = os.path.basename(s)[len(b) + len(kind) + 2:-4]
                    Lk = labels(s)
                    tk = [t for t in ticks if t < len(F[s]) and t < len(Lk) and Lk[t][0] == La[t][0]]
                    dw = [F[s][t][1] - F[sb][t][1] for t in tk]
                    print('    only %-8s %3d ticks  work - b: median %5.2f mean %5.2f' % (k, len(tk), pct(dw, .5), mean(dw)))
                    rows.append((b, kind + '_' + k, tk, F[s], F[sb], Lk))
    if csv_out:
        with open(csv_out, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['scene', 'variant', 'tick', 'a_frames', 'a_work', 'b_frames', 'b_work', 'moved'] + KINDS)
            for b, kind, ticks, fa, fb, La in rows:
                for t in ticks:
                    w.writerow([b, kind, t, '%.3f' % fa[t][0], '%.3f' % fa[t][1], '%.3f' % fb[t][0], '%.3f' % fb[t][1],
                                int(La[t][3])] + [La[t][1].get(k, 0) for k in KINDS])

def fit(paths, whatifs=()):
    """the cost model: per kind the frames of work one change costs, by least squares over every tick of the CSVs
    (a_work - b_work = sum n_kind x c_kind); then per scene (the a scripts) the measured and the modelled mean of
    a - b, and the modelled frames a tick (max(4, b's work + the objects), the 4-frame pacing) for each what-if:
    a set of kind=frames overrides, e.g. chomp=1.9,chomp-=0"""
    import numpy as np
    X = []; y = []; R = []
    for p in paths:
        for r in csv.DictReader(open(p)):
            X.append([float(r[k]) for k in KINDS]); y.append(float(r['a_work']) - float(r['b_work'])); R.append(r)
    X = np.array(X); y = np.array(y)
    used = [i for i in range(len(KINDS)) if X[:, i].any()]
    c, res, *_ = np.linalg.lstsq(X[:, used], y, rcond=None)
    pred = X[:, used] @ c
    print('%d ticks; residual median %.2f, mean |res| %.2f' % (len(y), float(np.median(y - pred)), float(np.mean(abs(y - pred)))))
    print('%-8s %8s %8s' % ('kind', 'ticks', 'frames'))
    for i, v in zip(used, c): print('%-8s %8d %8.2f' % (KINDS[i], int((X[:, i] > 0).sum()), v))
    coef = dict.fromkeys(KINDS, 0.0); coef.update({KINDS[i]: float(v) for i, v in zip(used, c)})
    cases = [('model', {})] + [(w, dict((kv.split('=')[0], float(kv.split('=')[1])) for kv in w.split(','))) for w in whatifs]
    print('\n%-14s %5s %7s %7s | %s' % ('scene', 'ticks', 'a-b', 'model', ' | '.join('%s: median mean' % nm[:40] for nm, _ in cases)))
    scenes = []
    for k, r in enumerate(R):
        if r['variant'] in ('walk', 'stand'): scenes.append((r['scene'] + ' ' + r['variant'], k))
    order = []
    for s, k in scenes:
        if s not in order: order.append(s)
    for s in order:
        ks = [k for s2, k in scenes if s2 == s]
        bw = np.array([float(R[k]['b_work']) for k in ks])
        cols = []
        for nm, ov in cases:
            cc = dict(coef); cc.update(ov)
            obj = np.array([sum(X[k, i] * cc[KINDS[i]] for i in range(len(KINDS))) for k in ks])
            fr = np.maximum(4.0, bw + obj)
            cols.append('%5.2f %5.2f' % (float(np.median(fr)), float(fr.mean())))
        print('%-14s %5d %7.2f %7.2f | %s' % (s, len(ks), float(y[ks].mean()), float(pred[ks].mean()), ' | '.join(cols)))

def main():
    a = sys.argv[1:]
    if not a: sys.exit(__doc__)
    if a[0] == 'census':
        top = int(a[a.index('--top') + 1]) if '--top' in a else 40
        rows = sorted(census(), key=lambda r: -busy_score(r[2]))
        for n, room, c in rows[:top]:
            print('level %2d room %2d  score %2d  %s' % (n, room, busy_score(c), ' '.join('%s %d' % kv for kv in sorted(c.items()))))
    elif a[0] == 'find':
        os.makedirs(a[1], exist_ok=True)
        for x in (WORST if '--worst' in a else a[2:]):
            lv, room = (int(v) for v in x.split(':'))
            for kind, st, pat, n, sc in find(a[1], lv, room):
                print('level %2d room %2d %-5s start %s pattern %-8s %3d ticks score %.1f' % (lv, room, kind, st, pat, n, sc), flush=True)
    elif a[0] == 'measure':
        co = a[a.index('--csv') + 1] if '--csv' in a else None
        jobs = int(a[a.index('--jobs') + 1]) if '--jobs' in a else 4
        pre = [x for i, x in enumerate(a[1:], 1) if not x.startswith('--') and a[i - 1] not in ('--csv', '--jobs')]
        if '--worst' in a:
            pre = [os.path.join(pre[0], 'l%02dr%02d' % tuple(int(v) for v in r.split(':'))) for r in WORST]
        measure(pre, co, jobs)
    elif a[0] == 'fit':
        wi = [a[i + 1] for i in range(len(a) - 1) if a[i] == '--whatif']
        fit([x for i, x in enumerate(a[1:], 1) if not x.startswith('--') and a[i - 1] != '--whatif'], wi)

if __name__ == '__main__':
    main()
