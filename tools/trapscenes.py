#!/usr/bin/env python3
"""Find short scenes where the kid moves while a gate or spikes animate on the shown screen (docs/perf.md "Gates and
spikes: per-tick measurements"), with tools/kidsim.py only. For every button (opener: the gate opens, then closes
slowly; closer: an open gate drops) whose gate is drawn on the button's screen, and for every spike tile, it tries
the kid starting on that tile (or next to the spikes) with a few control patterns and keeps, per level and kind, the
start and pattern with the most ticks of kid motion + visible trap change before the first room change or death.
Each scene is written as four scripts (the combination and its parts, the same start, tick-aligned):
  <name>_a.txt  the kid moves, the trap animates          <name>_b.txt  the same moves, the trap patched away
  <name>_c.txt  the kid stands, the trap animates         <name>_d.txt  the kid stands, the trap patched away
(b: the button or spike tile becomes floor; for a closer scene the gate starts open in all four; c, d for a button: the
kid's first moves until he has stepped off the button, then he stands; for spikes he stands on the spike tile).
usage: trapscenes.py OUTDIR [levels...]"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kidsim
from popdata import Level, T
import tickcost as TC
N = 120
PAT = {   # name: one period of moves, repeated to N
    'run':      [(1, 0, 0)] * 24 + [(-1, 0, 0)] * 24,
    'runlong':  [(1, 0, 0)] * 40 + [(-1, 0, 0)] * 40,
    'walk':     [(1, 0, 1)] * 30 + [(-1, 0, 1)] * 30,
    'jump':     [(1, -1, 0)] * 14 + [(-1, -1, 0)] * 14,
}

def moves_for(pat, d):
    p = PAT[pat]; m = (p * (N // len(p) + 1))[:N]
    return [(x * d, y, s) for (x, y, s) in m]

def run_sim(lv, start, moves, patches):
    sim = kidsim.KidSim(Level(lv), patches=patches, start=start, multi_level=True)
    out = []
    for (x, y, s) in moves:
        K = sim.Kid; kb = (sim.drawn_room, K.x, K.y, K.frame); fg = bytes(sim.level.fg); bg = bytes(sim.level.bg)
        sim.step(x, y, s)
        if sim.game_over or sim.Kid.alive >= 0: break
        K = sim.Kid; ka = (sim.drawn_room, K.x, K.y, K.frame)
        if ka[0] != kb[0]: break
        out.append((ka, fg, bytes(sim.level.bg)))
    return sim, out

def write(path, lv, start, moves, patches, note):
    with open(path, 'w') as f:
        f.write('# level %d\n# start %d:%d:%d\n' % (lv, start[0], start[1], start[2]))
        if patches: f.write('# patch %s\n' % ','.join('%d:%d:%d:%d' % p for p in patches))
        f.write('# %s\n' % note)
        for (x, y, s) in moves: f.write('%d %d %d\n' % (x, y, s))

def score(path):
    L = TC.sim_labels(path); n = 0
    for lab, k, nt in L:
        if lab == 'R' or nt.endswith('dead'): break
        if lab[0] == 'K' and (lab[1] == 'G' or lab[2] == 'S'): n += 1
    return n, len(L)

def gate_of(L, room, pos):
    """the gates a button at room:pos triggers that are drawn on room's screen (own columns 0-8, the left room's 9)"""
    m = L.bg[(room - 1) * 30 + pos]; out = []
    left = L.links(room)[0] if hasattr(L, 'links') else None
    while m < 256:
        d1 = L.doorlinks1[m]; d2 = L.doorlinks2[m]
        r = ((d1 & 0x60) >> 5) + ((d2 & 0xE0) >> 3); p = d1 & 0x1F
        if r and L.fg[(r - 1) * 30 + p] & 0x1F == T.gate: out.append((r, p))
        if d1 & 0x80: break
        m += 1
    return out

def main():
    outdir = sys.argv[1]; levels = [int(v) for v in sys.argv[2:]] or range(1, 15)
    os.makedirs(outdir, exist_ok=True); tmp = os.path.join(outdir, '_try.txt')
    for lv in levels:
        L = Level(lv); best = {}
        sim0 = kidsim.KidSim(Level(lv))
        for i in range(720):
            t = L.fg[i] & 0x1F; room, pos = i // 30 + 1, i % 30
            if t in (T.opener, T.closer):
                left = sim0.links(room)[0]
                gs = [(r, p) for (r, p) in gate_of(L, room, pos) if (r == room and p % 10 != 9) or (r == left and p % 10 == 9)]
                if not gs: continue
                kind = 'open' if t == T.opener else 'drop'
                base = [(r, p, T.gate, 188) for (r, p) in gs] if kind == 'drop' else []
                off = [(room, pos, T.floor, 0)]
                starts = [(room, pos, d) for d in (0, -1)]
            elif t == T.spike:
                kind = 'spike'; base = []; off = [(room, pos, T.floor, 0)]
                starts = [(room, pos + dc, d) for dc in (-2, -1, 1, 2) for d in (0, -1)
                          if 0 <= (pos % 10) + dc <= 9 and L.fg[(room - 1) * 30 + pos + dc] & 0x1F in (T.floor, T.torch, T.dpressplate if hasattr(T, 'dpressplate') else T.floor)]
            else: continue
            for st in starts:
                d = 1 if st[2] == 0 else -1
                for pat in PAT:
                    mv = moves_for(pat, d)
                    write(tmp, lv, st, mv, base, '')
                    sc, n = score(tmp)
                    if sc > best.get(kind, (0,))[0]: best[kind] = (sc, st, pat, mv, base, off, (room, pos))
        for kind, (sc, st, pat, mv, base, off, at) in best.items():
            name = os.path.join(outdir, 'l%02d_%s' % (lv, kind))
            note = '%s at %d:%d, kid pattern %s; %d ticks of kid motion with a visible change (tools/trapscenes.py)' % (kind, at[0], at[1], pat, sc)
            stand = [(0, 0, 0)] * N
            if kind == 'spike':      # standing: the kid stands on the spike tile (they rise under him and stay out)
                stc = (at[0], at[1], st[2])
            else:                    # a button: the kid's first moves until he is off the button, then he stands (on the
                stc = st             # button the gate's timer restarts every tick and an opened gate never closes)
                sim = kidsim.KidSim(Level(lv), patches=base, start=st, multi_level=True)
                for k, m in enumerate(mv):
                    sim.step(*m)
                    if sim.Kid.room != at[0] or sim.Kid.curr_row * 10 + sim.Kid.curr_col != at[1]: break
                stand = mv[:k + 1] + [(0, 0, 0)] * (N - k - 1)
            write(name + '_a.txt', lv, st, mv, base, note)
            write(name + '_b.txt', lv, st, mv, base + off, note + '; the trap patched away')
            write(name + '_c.txt', lv, stc, stand, base, note + '; the kid stands')
            write(name + '_d.txt', lv, stc, stand, base + off, note + '; the kid stands, the trap patched away')
            print('level %2d %-5s %3d ticks  start %s pattern %s  at %s' % (lv, kind, sc, st, pat, at), flush=True)
    if os.path.exists(tmp): os.remove(tmp)

if __name__ == '__main__':
    main()
