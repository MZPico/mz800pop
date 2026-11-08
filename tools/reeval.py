#!/usr/bin/env python3
"""Re-evaluation of the speed candidates after M8a part 18 (docs/perf.md "Speed roadmap: re-evaluation"). Measuring
only; nothing here changes the game.
  fixed SCRIPT T0 T1          the per-tick fixed costs (S1) over ticks T0..T1-1, frames a tick (mz800emu's call
                              profiler, inclusive): the snapshot, the dirty list, the controls, hp_draw, text_chk,
                              flash_tick, trace_cksum, the interrupt; then the same stretch with SND_MODE 1 (the
                              release's hybrid mode: the PSG player plays the tick's sounds) and a stretch with
                              SCRIPT_PTR 0 (the keyboard and joystick scan instead of the script)
  profile SCRIPT T0 T1 NAME,...   the mean inclusive frames a tick and calls a tick of the named routines
The scenes are those of tools/loosescenes.py, busyrooms.py and roadmap.py (not committed: their `find` writes them)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path[:0] = [os.path.join(ROOT, 'tests'), HERE]
import kidsim
import tickcost as TC
from emu import Emu
import m4_game as G
from m3_test import syms

FIXED = ['view_snapshot', 'dirty_reset', 'get_controls', 'read_inputs', 'key_scan', 'kid_tick', 'trace_cksum',
         'room_checksum', 'hp_draw', 'ghp_draw', 'text_chk', 'flash_tick', 'isr', 'snd_next', 'snd_playing', 'snd_fill',
         'snd_frame', 'draw_objects', 'view_redraw']

def prof(sp, t0, t1, pokes=(), after=None):
    """mean inclusive frames and calls a tick over ticks t0..t1-1; pokes: (addr, bytes) written at level_ready;
    after: a function (e, S) run after tick t0 is reached (before the profiled stretch)"""
    with Emu() as e:
        S, n = TC.emu_setup(e, sp)
        for a, d in pokes: e.call('mem_write', addr=a, data_hex=d.hex())
        names = {}
        for k, v in S.items(): names.setdefault(v, k)
        e.call('bp_add', addr=S['tick_done'])
        for t in range(t0): e.run(400)
        if after: after(e, S)
        e.call('profiler_reset'); e.call('profiler_start')
        c0 = e.call('get_raster_pos')['total_cycles']
        for t in range(t0, t1): e.run(400)
        c1 = e.call('get_raster_pos')['total_cycles']
        e.call('profiler_stop')
        r = e.call('profiler_get', limit=1000)
    k = t1 - t0
    inc = {}; calls = {}
    for it in r['entries']:
        nm = names.get(it['addr'], '%04X' % it['addr'])
        inc[nm] = inc.get(nm, 0) + it['incl_cycles'] / k / TC.FRAME
        calls[nm] = calls.get(nm, 0) + it['calls'] / k
    return ((c1 - c0) & 0xFFFFFFFF) / k / TC.FRAME, inc, calls, S

def show(title, tot, inc, calls, names):
    print('%s: %.3f frames a tick' % (title, tot))
    for nm in names:
        print('  %-16s %7.3f frames  %6.2f calls  %8.0f T a call' % (nm, inc.get(nm, 0), calls.get(nm, 0),
              inc.get(nm, 0) * TC.FRAME / calls[nm] if calls.get(nm) else 0))

def fixed(sp, t0, t1):
    tot, inc, calls, S = prof(sp, t0, t1)
    show('%s %d-%d, harness (silent, script)' % (os.path.basename(sp), t0, t1), tot, inc, calls, FIXED)
    sm = S['SND_MODE']
    tot, inc, calls, S = prof(sp, t0, t1, pokes=((sm, b'\x01'),))
    show('the same, SND_MODE 1 (hybrid: the PSG player plays)', tot, inc, calls, FIXED)
    def nokeys(e, S): e.call('mem_write', addr=G.SCRIPT_PTR, data_hex='0000')
    tot, inc, calls, S = prof(sp, t0, t1, after=nokeys)
    show('the same ticks with SCRIPT_PTR 0 (the kid stands: the keyboard / joystick scan)', tot, inc, calls, FIXED)

# the room change's laying by phase: a tracepoint at the head of every phase of run_rect / rec_lay / lay_piece16; the
# cycles from a phase's tracepoint to the next tracepoint are that phase's (calls inside a phase, e.g. cmx_n inside a
# masked row or far_seek_entry inside a plane's setup, count in it)
LAY_MARKS = [
    ('run_rect', 'cell: run_rect head, rect bounds, the cover scan setup'),
    ('rr_fill', 'cell: the black fill'), ('rr_lay', 'cell: lay pass start'), ('rr_sw', 'cell: the shadow write'),
    ('rr_fore', 'cell: the fore pass'), ('blit', 'cell: the copy to VRAM'),
    ('rr_bkt', 'scan: the cell bucket loop (record to record)'), ('rec_lay', 'scan: rec_lay reject / accept test'),
    ('rl_scan', 'scan: the cover scan (mode 1)'), ('rl_lay', 'piece: record fields + dir_entry'),
    ('lay_piece16', 'piece: lay_piece16 setup (clip, offsets, chains)'),
    ('lpc_planes', 'copy: setup of the plane loop'), ('lpf_p', 'copy: per-plane seek'),
    ('lpf_row', 'copy: rows, full bytes (INIR)'), ('lpf_rrow', 'copy: rows, right edge merged'),
    ('lpf_lrow', 'copy: rows, both edges merged'), ('lpf_pe', 'copy: plane end'), ('lpc_gen', 'copy: general path'),
    ('lpmasked', 'masked: setup'), ('lp_block', 'masked: the mask block read (INIR)'),
    ('lpm_plane', 'masked: per-plane setup + seek'), ('lpx_row', 'masked: rows (cmx_n + row step)'),
    ('lpm_rows', 'masked: mono / black rows setup'), ('lpm_row', 'masked: mono / black rows (cm2 / cm3)'),
    ('lpm_pnext', 'masked: plane end'),
]

def lay(sp, tick):
    with Emu() as e:
        S, n = TC.emu_setup(e, sp)
        R = syms(os.path.join(ROOT, 'build', 'ovl_room.sym'))
        addr = {}
        for nm, _ in LAY_MARKS:
            a = S.get(nm, R.get(nm))
            if a is None: print('no symbol', nm); continue
            addr[a] = nm
        e.call('bp_add', addr=S['tick_done'])
        for t in range(tick): e.run(400)
        e.call('bp_clear')
        start = e.trace_add(S['draw_room_full']); end = e.trace_add(S['room_drawn'])
        for a in addr: e.trace_add(a)
        recs = []; done = [False]
        for r in e.collect(50, stop=lambda r: r['addr'] == S['room_drawn']):
            recs.append(r)
        e.trace_clear()
    i0 = next(i for i, r in enumerate(recs) if r['addr'] == S['draw_room_full'])
    i1 = next(i for i, r in enumerate(recs) if r['addr'] == S['room_drawn'])
    recs = recs[i0:i1 + 1]
    cyc = {}; hits = {}
    for a, b in zip(recs, recs[1:]):
        nm = addr.get(a['addr'], 'room_ops + buckets (draw_room_full to the first cell)')
        cyc[nm] = cyc.get(nm, 0) + ((b['cycles'] - a['cycles']) & 0xFFFFFFFF); hits[nm] = hits.get(nm, 0) + 1
    tot = sum(cyc.values())
    print('%s tick %d: draw_room_full %.2f frames (%d T), by phase (frames, %% of the draw, hits, T a hit):' % (
        os.path.basename(sp), tick, tot / TC.FRAME, tot))
    lab = dict(LAY_MARKS)
    for nm in sorted(cyc, key=lambda k: -cyc[k]):
        print('  %-58s %7.2f %5.1f%% %6d %8.0f' % (lab.get(nm, nm) + ' [' + nm + ']', cyc[nm] / TC.FRAME, 100 * cyc[nm] / tot,
              hits[nm], cyc[nm] / hits[nm]))

def loose_pics(sp):
    """per tick of a loosescenes.py script: the number of loose floors on the screen whose picture
    (LOOSE_FRAM_BOTTOM[loose_frame]) changed, and of those whose loose_frame changed with the same picture"""
    import loosescenes as LS
    from popdata import Level, T, LOOSE_FRAM_BOTTOM
    moves, patches = kidsim.read_script(sp)
    o = kidsim.script_opts(sp)
    sim = kidsim.KidSim(Level(kidsim.script_level(sp)), patches=patches, guards=o['guards'], place=o['place'],
                        sword=o['sword'], time=o['time'], start=o['start'], multi_level=True)
    out = []
    for (x, y, sh) in moves:
        lv = sim.level; fg, bg = bytes(lv.fg), bytes(lv.bg); rm0 = sim.drawn_room
        sim.step(x, y, sh)
        if sim.game_over: break
        lv = sim.level; rm = sim.drawn_room; p = f = 0
        if rm == rm0 and rm:
            for r, q in LS.screen_tiles(sim, rm):
                i = (r - 1) * 30 + q
                if fg[i] & 0x1F == T.loose == lv.fg[i] & 0x1F and bg[i] != lv.bg[i]:
                    a, b = LS.loose_frame(bg[i]), LS.loose_frame(lv.bg[i])
                    if LOOSE_FRAM_BOTTOM[a] != LOOSE_FRAM_BOTTOM[b]: p += 1
                    elif a != b: f += 1
        out.append((p, f))
    return out

def loose(pairs):
    """pairs: (CSV of loosescenes.py measure, its scene directory): every scene's ticks by phase, with the shake split
    into shp (a picture changes) and shf (loose_frame only); frames median / p90, a - b median / mean"""
    import csv
    pct = lambda v, q: sorted(v)[min(len(v) - 1, int(q * (len(v) - 1) + 0.5))] if v else float('nan')
    mean = lambda v: sum(v) / len(v) if v else float('nan')
    ph = {}
    for path, d in pairs:
        pics = {}
        for r in csv.DictReader(open(path)):
            sc = r['scene']
            if sc not in pics: pics[sc] = loose_pics(os.path.join(d, sc + '_a.txt'))
            t = int(r['tick'])
            if t < 2: continue
            p = r['phase']
            if p == 'sh':
                pp, ff = pics[sc][t] if t < len(pics[sc]) else (0, 0)
                p = 'shp%d' % min(pp, 2) if pp else 'shf'
            k = (p, 'moving' if r['moved'] == '1' else 'still')
            v = ph.setdefault(k, ([], []))
            v[0].append(float(r['a_frames']))
            if r['b_work']: v[1].append(float(r['a_work']) - float(r['b_work']))
    print('%-8s %-6s %5s | frames median / p90 / worst | a-b ticks, median / mean' % ('phase', 'kid', 'ticks'))
    for k in sorted(ph):
        fa, d = ph[k]
        print('%-8s %-6s %5d | %6.2f / %6.2f / %6.2f | %4d %6.2f / %6.2f' % (k[0], k[1], len(fa), pct(fa, .5), pct(fa, .9), max(fa), len(d), pct(d, .5), mean(d)))

def gate_kind(lv, room, gr, gp, m0, m1):
    """the path of a visible gate step (colshift.asm gate_step's rules, docs/perf.md "M8a part 14"): G1 a palace
    pillar as the bars tile (the old path), G2 a drop (|k| > 1, the old path), G4 to or from position 47 (the old
    path), G3 closed (min(p) <= 12: the contact band's run_rect), regen (a slice comes or goes, or p = 11: the bars
    tile regenerated), open (the plain shift); '+dp' a dungeon pillar's base laid again"""
    from popdata import T
    p0, p1 = min(m0, 188) // 4, min(m1, 188) // 4
    if gp % 10 == 9: br, bp = room, gp - 9
    else: br, bp = gr, gp + 1
    bt = lv.fg[(br - 1) * 30 + bp] & 0x1F
    dp = '+dp' if bt == T.pillar and lv.type == 0 else ''
    if bt == T.pillar and lv.type == 1: return 'G1 palace pillar'
    if abs(p1 - p0) > 1: return 'G2 drop'
    if 47 in (p0, p1): return 'G4 to/from 47'
    mp = min(p0, p1)
    if (46 - mp) & 7 == 0 or mp == 11: return 'regen' + dp
    if mp <= 12: return 'G3 closed band' + dp
    return 'open' + dp

def gate_steps(sp):
    """per tick of a script (kidsim, the shown room unchanged, the kid alive): the visible gate steps' kinds"""
    from popdata import Level, T
    moves, patches = kidsim.read_script(sp)
    o = kidsim.script_opts(sp)
    sim = kidsim.KidSim(Level(kidsim.script_level(sp)), patches=patches, guards=o['guards'], place=o['place'],
                        sword=o['sword'], time=o['time'], start=o['start'], multi_level=True)
    out = []; seen = set(); alive0 = True
    for (x, y, sh) in moves:
        lv = sim.level; bg = bytes(lv.bg); rm0 = sim.drawn_room; dl0 = bytes(sim.dl2)
        sim.step(x, y, sh)
        if sim.game_over: break
        lv = sim.level; rm = sim.drawn_room; ks = []
        alive = sim.Kid.alive < 0
        if rm != rm0 or (alive and not alive0): seen.clear()
        alive0 = alive
        if rm == rm0 and rm and alive:
            for p in range(30):
                i = (rm - 1) * 30 + p; m = lv.bg[i]
                if lv.fg[i] & 0x1F in (T.opener, T.closer) and ((dl0[m] & 0x1F) > 1) != ((sim.dl2[m] & 0x1F) > 1):
                    ks.append('button: B1 miss' if p not in seen else 'button: hit'); seen.add(p)
            left = sim.links(rm)[0]
            tiles = [(rm, p) for p in range(30) if p % 10 != 9] + ([(left, p) for p in (9, 19, 29)] if left else [])
            for r, p in tiles:
                i = (r - 1) * 30 + p
                if lv.fg[i] & 0x1F != T.gate or bg[i] == lv.bg[i]: continue
                if min(bg[i], 188) // 4 == min(lv.bg[i], 188) // 4: continue
                ks.append(gate_kind(lv, rm, r, p, bg[i], lv.bg[i]))
        out.append(ks)
    return out

def gates(csvp, d):
    """the only-gate variants (walk_gate) of tools/busyrooms.py measure's CSV: per gate-step kind the work above
    walking (a_work - b_work) on the ticks with exactly one visible gate step; and the census of every kind in the
    walk_a / stand_a scenes"""
    import csv
    pct = lambda v, q: sorted(v)[min(len(v) - 1, int(q * (len(v) - 1) + 0.5))] if v else float('nan')
    cost = {}; census = {}; cache = {}
    for r in csv.DictReader(open(csvp)):
        v = r['variant']
        if v not in ('walk_gate', 'walk', 'stand'): continue
        sp = os.path.join(d, '%s_%s.txt' % (r['scene'], v if v != 'walk' and v != 'stand' else v + '_a'))
        if sp not in cache: cache[sp] = gate_steps(sp)
        t = int(r['tick']); ks = cache[sp][t] if t < len(cache[sp]) else []
        if v in ('walk', 'stand'):
            for k in ks: census[k] = census.get(k, 0) + 1
        elif len(ks) == 1:
            cost.setdefault(ks[0], []).append(float(r['a_work']) - float(r['b_work']))
    gate = lambda k: not k.startswith('button')
    ng = sum(v for k, v in census.items() if gate(k)); nb = sum(v for k, v in census.items() if not gate(k))
    print('in the walk_a / stand_a scenes: %d visible gate steps (the shares: of these), %d button changes (the shares: '
          'of these)' % (ng, nb))
    for k in sorted(census, key=lambda k: (not gate(k), -census[k])):
        c = cost.get(k, [])
        print('  %-22s %5d (%4.1f%%)  one-step ticks of walk_gate %3d: a-b median %5.2f mean %5.2f' % (
            k, census[k], 100 * census[k] / (ng if gate(k) else nb), len(c), pct(c, .5), sum(c) / len(c) if c else float('nan')))
    for k in cost:
        if k not in census: print('  %-22s (walk_gate only) %3d ticks: a-b median %5.2f' % (k, len(cost[k]), pct(cost[k], .5)))

def events(paths):
    """kidsim over whole scripts: how often each candidate's situation comes up. Per script and in total: ticks, room
    draws (room changes, level starts and restarts), deaths, visible gate steps by kind (gate_kind), chopper picture
    changes (with blood: C1; in the above room's row 2 or the left room's column 9: C2), spike picture changes (own /
    C2), visible button changes (the first of a button since the last room draw: B1, a miss; later ones: hits; and how
    many buttons changed only once in a visit), loose-floor picture changes (shp), frame-only shakes (shf), releases and
    landings (T1)"""
    from popdata import Level, T, CHOMPER_FRAM1, LOOSE_FRAM_BOTTOM
    import loosescenes as LS
    tot = {}
    def add(c, k, v=1): c[k] = c.get(k, 0) + v
    for sp in paths:
        moves, patches = kidsim.read_script(sp); keys = kidsim.read_keys(sp)
        o = kidsim.script_opts(sp)
        sim = kidsim.KidSim(Level(kidsim.script_level(sp)), patches=patches, guards=o['guards'], place=o['place'],
                            sword=o['sword'], time=o['time'], start=o['start'], multi_level=True)
        c = {}; seen = {}; visit = {}; alive0 = True
        def close_visit():
            for b, n in visit.items(): add(c, 'buttons changed in a visit: once' if n == 1 else 'buttons changed in a visit: twice+')
            visit.clear(); seen.clear()
        for (x, y, sh), k in zip(moves, keys):
            lv = sim.level; fg, bg = bytes(lv.fg), bytes(lv.bg); rm0 = sim.drawn_room; lvn = lv.number
            dl0 = bytes(sim.dl2)
            sim.step(x, y, sh, k)
            if sim.game_over: break
            add(c, 'ticks')
            lv = sim.level; rm = sim.drawn_room; K = sim.Kid
            alive = K.alive < 0
            if alive0 and not alive: add(c, 'deaths')
            restart = alive and not alive0
            alive0 = alive
            if rm != rm0 or lv.number != lvn or restart or not rm:
                add(c, 'room draws (level start / change / restart)'); close_visit(); continue
            L, R, U, D = sim.links(rm)
            def tiles():
                for p in range(30): yield rm, p, 'own'
                if L:
                    for p in (9, 19, 29): yield L, p, 'left'
                if U:
                    for p in range(20, 30): yield U, p, 'above'
            for r, p, w in tiles():
                i = (r - 1) * 30 + p
                t0, t1 = fg[i] & 0x1F, lv.fg[i] & 0x1F; m0, m1 = bg[i], lv.bg[i]
                if t0 != t1:
                    if t0 == T.loose and t1 == T.empty: add(c, 'T1 loose release')
                    elif t1 in (T.debris, T.torch_with_debris): add(c, 'T1 loose landing')
                    elif t0 in (T.potion, T.sword): add(c, 'potion / sword taken')
                    else: add(c, 'tile changed: %d->%d' % (t0, t1))
                    continue
                if t1 in (T.opener, T.closer) and w == 'own':
                    pr = lambda d: (d[m1] & 0x1F) > 1
                    if pr(dl0) != pr(sim.dl2):
                        b = (r, p)
                        add(c, 'button change: B1 miss (first since the room draw)' if b not in seen else 'button change: hit')
                        seen[b] = 1; visit[b] = visit.get(b, 0) + 1
                    continue
                if m0 == m1: continue
                if t1 == T.gate and ((w == 'own' and p % 10 != 9) or w == 'left'):
                    if min(m0, 188) // 4 != min(m1, 188) // 4: add(c, 'gate step: ' + gate_kind(lv, rm, r, p, m0, m1))
                elif t1 == T.chomper:
                    a0 = (CHOMPER_FRAM1[min(m0 & 0x7F, 6)], m0 & 0x80); a1 = (CHOMPER_FRAM1[min(m1 & 0x7F, 6)], m1 & 0x80)
                    if a0 != a1:
                        add(c, 'chopper step: ' + ('C2 neighbour room' if w != 'own' else 'C1 with blood' if m1 & 0x80 else 'own'))
                elif t1 == T.spike:
                    f = lambda m: 5 if m & 0x80 else m
                    if f(m0) != f(m1): add(c, 'spike step: ' + ('C2 neighbour room' if w != 'own' else 'own'))
                elif t1 == T.loose:
                    a, b = LS.loose_frame(m0), LS.loose_frame(m1)
                    if LOOSE_FRAM_BOTTOM[a] != LOOSE_FRAM_BOTTOM[b]: add(c, 'loose shake: picture (shp)')
                    elif a != b: add(c, 'loose shake: frame only (shf)')
        close_visit()
        print('%s: %s' % (os.path.basename(sp), ', '.join('%s %d' % kv for kv in sorted(c.items()))))
        for k, v in c.items(): add(tot, k, v)
    print('total:')
    for k in sorted(tot): print('  %-55s %6d' % (k, tot[k]))

def census():
    """per level (the Python reference's level data): rooms, gates (palace pillar as the bars tile: G1), buttons
    (openers / closers: a closer drops its gates, G2), choppers, spikes, loose floors, and the screens with a chopper
    or spike in the room above's row 2 or the left room's column 9 (C2)"""
    from popdata import Level, T
    tot = {}
    print('lv  rooms gates G1 openers closers choppers spikes loose  C2-screens(chopper/spike)  torches potions')
    for n in range(1, 15):
        lv = Level(n); c = {}
        def add(k, v=1): c[k] = c.get(k, 0) + v
        for room in range(1, lv.used_rooms + 1):
            L, R, U, D = lv.links(room)
            for p in range(30):
                t = lv.fg[(room - 1) * 30 + p] & 0x1F
                if t == T.gate:
                    add('gates')
                    br, bp = (R, p - 9) if p % 10 == 9 else (room, p + 1)
                    if br and lv.type == 1 and lv.fg[(br - 1) * 30 + bp] & 0x1F == T.pillar: add('G1')
                for k, tt in (('openers', T.opener), ('closers', T.closer), ('choppers', T.chomper), ('spikes', T.spike),
                              ('loose', T.loose), ('torches', T.torch), ('potions', T.potion)):
                    if t == tt: add(k)
                if t == T.torch_with_debris: add('torches')
            nb = [(U, q) for q in range(20, 30)] if U else []
            nb += [(L, q) for q in (9, 19, 29)] if L else []
            if any(lv.fg[(r - 1) * 30 + q] & 0x1F in (T.chomper, T.spike) for r, q in nb): add('C2')
        add('rooms', lv.used_rooms)
        print('%2d %6d %5d %2d %7d %7d %8d %6d %5d %10d %24d %7d' % (n, c.get('rooms', 0), c.get('gates', 0), c.get('G1', 0),
              c.get('openers', 0), c.get('closers', 0), c.get('choppers', 0), c.get('spikes', 0), c.get('loose', 0),
              c.get('C2', 0), c.get('torches', 0), c.get('potions', 0)))
        for k, v in c.items(): tot[k] = tot.get(k, 0) + v
    print('all', ', '.join('%s %d' % kv for kv in sorted(tot.items())))

# ---------------------------------------------------------------- the op lists (the Python reference: tools/popdata.py
# RoomRenderer, whose lists tests/m3_test.py proves equal to room.asm's, record for record)
def _rr(n):
    import popdata as P
    P.RoomRenderer.paint = lambda self: None          # the lists only
    lv = P.Level(n)
    return lv, P.RoomRenderer(lv, ega=True)

def _ops(rr, room):
    rr.draw_room(room)
    return [('b',) + o for o in rr.ops['back']] + [('m',) + o for o in rr.ops['mid']] + [('f',) + o for o in rr.ops['fore']]

def _dims(rr, o):
    w, h, rows = rr.sets[o[1]].get(o[2]); return w, h

def _blocks(rr, ops, bw, bh, y0, nx, ny, fore):
    """per block (bw bytes x bh rows from row y0) the ops touching it, relative to the block: two blocks with equal
    lists have equal pixels"""
    import collections
    c = collections.defaultdict(list)
    for o in ops:
        tb, ch, id1, x, y, blit = o
        if tb == 'f' and not fore: continue
        w, h = _dims(rr, o)
        xb0 = x >> 3; xb1 = (x + w - 1) >> 3
        for cx in range(nx):
            if xb1 < cx * bw or xb0 > cx * bw + bw - 1: continue
            for cy in range(ny):
                yt = y0 + cy * bh
                if y + h - 1 < yt or y > yt + bh - 1: continue
                c[(cx, cy)].append((tb, ch, id1, x - cx * bw * 8, y - yt, blit))
    return c

def oplists():
    """R1: per level the op records of every room (back / mid / fore), the bytes the Z80 keeps (8-byte record + tag
    byte; the slice tables, 480 bytes, are rebuilt from the lists), the cell buckets (15 counts + one index per op and
    cell), how well a level's lists compress (zlib -9, a stand-in for tools/pzpack.py), and the dynamic part: the
    records that change or go when an animated tile of the screen goes through its states, plus per tile the most
    records one of its states adds (gates, loose floors, choppers,
    spikes, torches, potions, the sword, the level door, buttons pressed)"""
    import difflib, struct, zlib
    from popdata import T, B_NOTRANSP, B_OR, B_TRANSP, B_BLACK
    VARY = {T.gate: list(range(0, 189, 4)), T.loose: list(range(0, 11)) + [0x81, 0x84], T.chomper: list(range(16)) + [0x81, 0x83],
            T.spike: [0, 1, 2, 3, 4, 5, 0x8F], T.torch: list(range(10)), T.torch_with_debris: list(range(10)),
            T.sword: [0, 1, 2], T.level_door_left: list(range(44))}
    ANIM = set(VARY) | {T.opener, T.closer, T.potion}
    print('lv | records a room back / fore mean (max) | lists + tags a room mean / max | + buckets | level total, zlib | '
          'animated tiles a screen mean / max | dynamic records a room mean / max')
    tot = [0, 0]
    for n in range(1, 15):
        lv, rr = _rr(n); rows = []; blob = bytearray()
        for room in range(1, lv.used_rooms + 1):
            base = _ops(rr, room)
            for o in base:
                tb, ch, id1, x, y, blit = o
                w, h = _dims(rr, o)
                code = {B_NOTRANSP: 0, B_OR: 1, B_TRANSP: 1, B_BLACK: 2}.get(blit, 3)
                blob += struct.pack('<BBBbhBBB', 'bmf'.index(tb) | code << 2, ch, (id1 + 37 * (x & 7)) & 255, x >> 3, y,
                                    ((x & 7) + w + 7) // 8, h, 0)
            inst = sum(len(v) for v in _blocks(rr, base, 8, 64, 0, 5, 3, True).values())
            L, R, U, D = lv.links(room)
            scr = [(room, p) for p in range(30)] + ([(L, p) for p in (9, 19, 29)] if L else []) + \
                  ([(U, p) for p in range(20, 30)] if U else []) + ([(D, p) for p in range(10)] if D else [])
            scr = [(r, p) for r, p in scr if lv.fg[(r - 1) * 30 + p] & 0x1F in ANIM]
            dyn = set(); grow = {}      # base records a state changes or removes; per tile the most records a state adds
            for r, p in scr:
                i = (r - 1) * 30 + p; t = lv.fg[i] & 0x1F; m0, f0 = lv.bg[i], lv.fg[i]
                if t in (T.opener, T.closer): var = [('fg', (f0 & 0xE0) | (T.floor if t == T.opener else T.stuck))]
                elif t == T.potion: var = [('bg', (m0 & 0xF8) | k) for k in range(8)]
                else: var = [('bg', v) for v in VARY[t]]
                for kind, v in var:
                    if kind == 'bg': lv.bg[i] = v
                    else: lv.fg[i] = v
                    ops = _ops(rr, room); lv.bg[i] = m0; lv.fg[i] = f0
                    if ops == base: continue
                    added = 0
                    for tag, a0, a1, b0, b1 in difflib.SequenceMatcher(None, base, ops, autojunk=False).get_opcodes():
                        if tag != 'equal':
                            dyn.update(range(a0, a1)); added += max(0, (b1 - b0) - (a1 - a0))   # inserts, growing replaces
                    grow[(r, p)] = max(grow.get((r, p), 0), added)
            nb = sum(1 for o in base if o[0] != 'f')
            rows.append((nb, len(base) - nb, 9 * len(base), 15 + inst, len(scr), len(dyn) + sum(grow.values())))
        k = len(rows); mean = lambda i: sum(r[i] for r in rows) / k; mx = lambda i: max(r[i] for r in rows)
        lt = sum(r[2] for r in rows); z = len(zlib.compress(bytes(blob), 9)); tot[0] += lt; tot[1] += z
        print('%2d | %5.1f (%3d) / %5.1f (%3d) | %5.0f / %4d | %4.0f | %6d, %5d | %4.1f / %2d | %4.1f / %2d' % (
            n, mean(0), mx(0), mean(1), mx(1), mean(2), mx(2), mean(3), lt, z, mean(4), mx(4), mean(5), mx(5)), flush=True)
    print('all levels: lists + tags %d bytes, zlib %d' % tuple(tot))

def blocks():
    """R2: per level how many of the full draw's blocks have a list of ops (relative to the block) that an earlier
    block of the level already had (a cache keyed by the block's ops would hit), for three grains: the renderer's
    cells (8 bytes x 64 rows), tile blocks (4 bytes x 63 rows from row 3: one tile's place) and half cells (4 x 64);
    back + mid (the shadow's picture) and with the fore pieces (the screen's)"""
    import collections
    G = [('cell 8x64', (8, 64, 0, 5, 3)), ('tile 4x63', (4, 63, 3, 10, 3)), ('half 4x64', (4, 64, 0, 10, 3))]
    tot = collections.Counter()
    for n in range(1, 15):
        lv, rr = _rr(n)
        seen = collections.defaultdict(collections.Counter); inst = collections.Counter()
        for room in range(1, lv.used_rooms + 1):
            base = _ops(rr, room)
            for g, (bw, bh, y0, nx, ny) in G:
                for fore in (False, True):
                    c = _blocks(rr, base, bw, bh, y0, nx, ny, fore)
                    for cx in range(nx):
                        for cy in range(ny): seen[(g, fore)][tuple(c.get((cx, cy), []))] += 1; inst[(g, fore)] += 1
        line = '%2d' % n
        for g, _ in G:
            for fore in (False, True):
                d = len(seen[(g, fore)]); i = inst[(g, fore)]
                line += ' | %s%s %3d of %3d distinct (%2.0f%% hits)' % (g, '+fore' if fore else '', d, i, 100 * (i - d) / i)
                tot[(g, fore, 'd')] += d; tot[(g, fore, 'i')] += i
        print(line, flush=True)
    for g, _ in G:
        for fore in (False, True):
            d, i = tot[(g, fore, 'd')], tot[(g, fore, 'i')]
            print('all %s%s: %d distinct of %d (%.0f%% hits)' % (g, '+fore' if fore else '', d, i, 100 * (i - d) / i))

def masks():
    """the masked pieces (blit code 1) of every room's full draw: their bytes (per plane, by the shifted byte grid) by
    mask class: fully opaque (could be copied, 21 T), fully transparent (could be skipped), partial (AND / OR)"""
    import collections
    from popdata import B_OR, B_TRANSP
    tot = collections.Counter(); cache = {}
    for n in range(1, 15):
        lv, rr = _rr(n); lc = collections.Counter()
        for room in range(1, lv.used_rooms + 1):
            for tb, ch, id1, x, y, blit in _ops(rr, room):
                if blit not in (B_OR, B_TRANSP): continue
                key = (n > 0 and lv.type, ch, id1, x & 7)
                if key not in cache:
                    w, h, rows = rr.sets[ch].get(id1); s = x & 7; nb = (s + w + 7) // 8; c = collections.Counter()
                    for row in rows:
                        bits = [False] * (nb * 8)
                        for xx, v in enumerate(row):
                            if v != -1: bits[s + xx] = True
                        for b in range(nb):
                            k = sum(bits[b * 8:b * 8 + 8]); c['opaque' if k == 8 else 'transparent' if k == 0 else 'partial'] += 1
                    cache[key] = c
                lc.update(cache[key])
        s = sum(lc.values())
        print('%2d: %6d masked plane bytes: opaque %4.1f%%, transparent %4.1f%%, partial %4.1f%%' % (
            n, s, 100 * lc['opaque'] / s, 100 * lc['transparent'] / s, 100 * lc['partial'] / s), flush=True)
        tot.update(lc)
    s = sum(tot.values())
    print('all: opaque %.1f%%, transparent %.1f%%, partial %.1f%%' % tuple(100 * tot[k] / s for k in ('opaque', 'transparent', 'partial')))

def main():
    a = sys.argv[1:]
    if not a: sys.exit(__doc__)
    if a[0] in ('oplists', 'blocks', 'masks'):
        globals()[a[0]]()
    elif a[0] == 'events':
        events([TC.script_path(x) for x in a[1:]])
    elif a[0] == 'census':
        census()
    elif a[0] == 'gates':
        gates(a[1], a[2])
    elif a[0] == 'loose':
        loose([(a[i], a[i + 1]) for i in range(1, len(a), 2)])
    elif a[0] == 'lay':
        lay(TC.script_path(a[1]), int(a[2]))
    elif a[0] == 'fixed':
        fixed(TC.script_path(a[1]), int(a[2]), int(a[3]))
    elif a[0] == 'profile':
        tot, inc, calls, S = prof(TC.script_path(a[1]), int(a[2]), int(a[3]))
        show('%s %s-%s' % (a[1], a[2], a[3]), tot, inc, calls, a[4].split(','))

if __name__ == '__main__':
    main()
