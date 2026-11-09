#!/usr/bin/env python3
"""Option E of the busy rooms (docs/perf.md "Option E: measured"): where a visible object step's time goes, by stage.
  profile A B TICK[,TICK...]   profile each tick alone in script A and in script B (e.g. a scene's walk_<kind> and its
                               walk_b, from tools/busyrooms.py find): per stage the inclusive frames in A, in B and
                               A - B (what the object's change costs on that tick)
  diff A B TICK[,TICK...]      the routines whose inclusive frames differ most between A and B on each tick
  chunks A TICK[,TICK...]      the object pass's chunks of each tick (CRX, CRY, CRW, CRH) and how many were kept
                               (cs_put's picture, no restore), restored or inside a flame
  census [LEVELS] [--list]     every animated object of levels 1-14 in its own room (the Python reference): E's
                               layer (the back / mid ops that change over its states), whether a static back / mid op
                               drawn after the layer touches its pixels (over: E must lay that op again in every chunk,
                               or the object is not exclusive) or only its rect (rect-only: exclusive by pixels, not by
                               the Z80's record rects), the layer's pieces and whether they are opaque
  touch A LEVEL ROOM           the object pass's chunks that touch a chopper's, spike's, gate column's or torch
                               flame's rect without being its own step chunk: the chunks E would have to lay that
                               object's picture in (count a tick, overlap bytes a plane)
  direct SCRIPT ...            (M8a part 17) every direct copy of a cached torch flame into VRAM against the beam:
                               torn copies (must be 0), the copy's length and the beam's closest approach
  direct2 SCRIPT ...           (M8a part 25) every direct copy of a chopper's or spike's complete picture (frmlow2.asm
                               lc_direct, row-major) against the beam, row by row: torn passes (must be 0), the copy's
                               length and the beam's closest approach to the row being written
  model CSV [--e K=V,...]      the busy-rooms cost model (tools/busyrooms.py fit) with E's per-step costs:
                               frames a tick, median / p90, now and after E, per scene
The stages (inclusive frames of mz800emu's call profiler, one tick):
  tick          the whole tick, tick_done to tick_done (with the pacing wait: never under 4)
  redraw        view_redraw: the snapshot compare and every object step (torch_fast, the overlays' steps through
                their resident stubs, tile_redraw), of it
    regen         tile_regen (op-list regenerations)
    run_rect      run_rect (laying pieces into a dirty rect: dr_run's, the overlays')
    shadow_write  shadow_write (the rect into the shadow: run_rect's and cs_put's)
    ovl_load      ovl_load (a W1 overlay read from the RAM disk)
  place         people_place (the people's objects and rects)
  chunks        obj_chunk: the object pass's compose chunks (with a flush inside one when the buffers are full), of it
    restore       restore_shadow (the chunks' background read from the shadow; cs_get's too, which jumps into it,
                  is counted in redraw)
    flames        flames_lay (the exclusive torch flames laid after the restore)
    tcache        tc_try + tc_save (the torch picture cache)
    people        people_chunk (the kid, the guard, their swords, the overlays between them)
    fore          lay_fore_rect (the fore pieces over the chunk)
  copy          pf_blit1 (the chunks to VRAM)
  wait          pf_seq (the beam wait: pend_flush's look for a moment when every chunk is clear of the beam; the
                one-at-a-time fallback is not counted)
(draw_objects and pend_flush are left out: pend_flush is entered by a jump, and the profiler loses draw_objects'
return on some ticks.)
The scenes are not committed: tools/busyrooms.py find regenerates them."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path[:0] = [os.path.join(ROOT, 'tests'), HERE]
import tickcost as TC
from emu import Emu

STAGES = [('tick', None), ('redraw', 'view_redraw'), ('  regen', 'tile_regen'), ('  run_rect', 'run_rect'),
          ('  shadow_write', 'shadow_write'), ('  ovl_load', 'ovl_load'), ('place', 'people_place'),
          ('chunks', 'obj_chunk'), ('  restore', 'restore_shadow'), ('  flames', 'flames_lay'),
          ('  tcache', ('tc_try', 'tc_save')), ('  people', 'people_chunk'), ('  fore', 'lay_fore_rect'),
          ('copy', 'pf_blit1'), ('wait', 'pf_seq'), ('chunks (calls)', 'obj_chunk')]

def stages(tot, rows):
    inc = {}; calls = {}
    for i, e, c, n in rows: inc[n] = inc.get(n, 0) + i; calls[n] = calls.get(n, 0) + c
    out = {}
    for lab, s in STAGES:
        if lab == 'tick': v = tot
        elif lab == 'chunks (calls)': v = calls.get('obj_chunk', 0)
        elif isinstance(s, tuple): v = sum(inc.get(x, 0) for x in s)
        else: v = inc.get(s, 0)
        out[lab] = v
    return out

def profile(sa, sb, ticks):
    pa = TC.emu_profile(TC.script_path(sa), ticks, 0)
    pb = TC.emu_profile(TC.script_path(sb), ticks, 0) if sb != '-' else {}
    for t in ticks:
        A = stages(*pa[t]); B = stages(*pb[t]) if t in pb else None
        print('tick %d: %s%s' % (t, os.path.basename(sa), (' against ' + os.path.basename(sb)) if B else ''))
        for lab, _ in STAGES:
            if B: print('  %-16s %6.2f %6.2f %+6.2f' % (lab, A[lab], B[lab], A[lab] - B[lab]))
            else: print('  %-16s %6.2f' % (lab, A[lab]))

def diff(sa, sb, ticks, top=30):
    """the routines whose inclusive frames differ most between A and B on each tick (calls A / B)"""
    pa = TC.emu_profile(TC.script_path(sa), ticks, 0)
    pb = TC.emu_profile(TC.script_path(sb), ticks, 0)
    for t in ticks:
        A = {}; B = {}
        for i, e, c, n in pa[t][1]: A[n] = (A.get(n, (0, 0))[0] + i, A.get(n, (0, 0))[1] + c)
        for i, e, c, n in pb[t][1]: B[n] = (B.get(n, (0, 0))[0] + i, B.get(n, (0, 0))[1] + c)
        print('tick %d: %.2f against %.2f frames' % (t, pa[t][0], pb[t][0]))
        d = sorted(set(A) | set(B), key=lambda n: -abs(A.get(n, (0, 0))[0] - B.get(n, (0, 0))[0]))
        for n in d[:top]:
            a = A.get(n, (0, 0)); b = B.get(n, (0, 0))
            print('  %-20s %6.2f %6.2f %+6.2f  calls %d / %d' % (n, a[0], b[0], a[0] - b[0], a[1], b[1]))

def chunks(sa, ticks):
    """the chunks of each tick: rect and how its background came (kept SPRBUF_B, the torch cache, a flame, restore)"""
    sp = TC.script_path(sa)
    with Emu() as e:
        S, n = TC.emu_setup(e, sp)
        last = max(ticks) + 1
        tp = {e.trace_add(S['tick_done']): 'tick', e.trace_add(S['obj_chunk'], mem=((S['CRX'], 4),)): 'chunk',
              e.trace_add(S['restore_shadow'], mem=((S['CRX'], 4),)): 'restore', e.trace_add(S['blit'], mem=((S['CRX'], 4),)): 'blit'}
        byaddr = {S['tick_done']: 'tick', S['obj_chunk']: 'chunk', S['restore_shadow']: 'restore', S['blit']: 'blit'}
        t = 0; ev = {}
        for r in e.collect(200, stop=lambda r: t >= last):
            k = tp.get(r.get('id')) or byaddr[r['addr']]
            if k == 'tick': t += 1; continue
            if t in ticks:
                x, y, w, h = r.get('mem', [[0, 0, 0, 0]])[0]
                ev.setdefault(t, []).append('%-8s x %2d y %3d w %d h %3d (%4d bytes a plane)' % (k, x, y, w, h, w * h))
        e.trace_clear()
    for t in ticks:
        print('tick %d' % t)
        for l in ev.get(t, []): print('  ' + l)

KIND_OF = None
def _kinds():
    from popdata import T
    return {T.torch: 'torch', T.torch_with_debris: 'torch', T.chomper: 'chopper', T.gate: 'gate', T.spike: 'spike',
            T.potion: 'potion', T.sword: 'sword', T.level_door_left: 'door', T.loose: 'loose'}

def census_level(n):
    """per animated object of level n in its own room: E's layer (the moving back / mid ops over all its states), the
    moving fore ops, the static back / mid ops after the layer that touch its pixels (pixel over) or only its records'
    rects (rect over), whether the layer is opaque, its union rect (bytes x rows), its pieces at most"""
    from collections import Counter
    from popdata import Level, RoomRenderer, T
    import animexact as AX
    K = _kinds(); out = []
    L = Level(n); pix = {}
    def P(rr, op):
        if op not in pix: pix[op] = frozenset(AX.Painter(rr).pixels(op))
        return pix[op]
    for room in range(1, 25):
        for pos in range(30):
            i = (room - 1) * 30 + pos; t = L.fg[i] & 0x1F
            if t not in K: continue
            m0 = L.bg[i]
            states = AX.states_for(t, m0)
            if t == T.chomper: states = [1, 2, 3, 4, 5, 6]
            if t == T.gate: states = list(range(0, 189, 4))
            lists = []
            for m in states:
                L.bg[i] = m
                rr = RoomRenderer(L); rr.paint = lambda: None; rr.draw_room(room)
                o = rr.ops; ol = []
                for k in ('wipe0', 'back', 'mid', 'wipe1', 'fore'):
                    for op in o[k]: ol.append((k, ('wipe',) + tuple(op) if k.startswith('wipe') else ('img',) + tuple(op)))
                lists.append(ol)
            L.bg[i] = m0
            common = Counter(lists[0])
            for ol in lists[1:]: common &= Counter(ol)
            layer = set(); mfore = set(); over_px = set(); over_rect = set(); pieces = 0
            lpix = set()
            for ol in lists:
                c = Counter(common); first = None; lay = []
                for k, (lst, op) in enumerate(ol):
                    if c[(lst, op)] > 0: c[(lst, op)] -= 1; continue
                    if lst == 'fore': mfore.add(op)
                    else:
                        layer.add(op); lay.append(op)
                        if first is None: first = k
                pieces = max(pieces, len(lay))
                for op in lay: lpix |= P(rr, op)
            if not layer and not mfore: continue
            xs = [p[0] for p in lpix]; ys = [p[1] for p in lpix]
            box = (min(xs) // 8, max(xs) // 8 + 1, min(ys), max(ys) + 1) if lpix else None
            for ol in lists:
                c = Counter(common); seen = False
                for k, (lst, op) in enumerate(ol):
                    mv = True
                    if c[(lst, op)] > 0: c[(lst, op)] -= 1; mv = False
                    if mv and lst != 'fore': seen = True; continue
                    if not seen or mv or lst == 'fore': continue
                    q = P(rr, op)
                    if q & lpix: over_px.add(op[:3] if op[0] == 'img' else ('wipe',))
                    elif q and box:
                        qx = [p[0] // 8 for p in q]; qy = [p[1] for p in q]
                        if min(qx) < box[1] and max(qx) + 1 > box[0] and min(qy) < box[3] and max(qy) + 1 > box[2]:
                            over_rect.add(op[:3] if op[0] == 'img' else ('wipe',))
            opq = all(op[0] == 'wipe' or op[5] == 0 for op in layer) if layer else None
            out.append(dict(level=n, room=room, pos=pos, kind=K[t], layer=len(layer), pieces=pieces, fore=len(mfore),
                            opaque=opq, box=box, over_px=sorted(over_px), over_rect=sorted(over_rect)))
    return out

def census(levels):
    from multiprocessing import Pool
    with Pool(7) as p: R = [r for rs in p.map(census_level, levels) for r in rs]
    by = {}
    for r in R: by.setdefault(r['kind'], []).append(r)
    print('%-8s %4s | %-9s %-9s %-9s | %-12s | %-11s | pixel-over ids (objects)' % (
        'kind', 'n', 'exclusive', 'rect-only', 'over', 'layer pieces', 'opaque'))
    for k, L in sorted(by.items()):
        ex = [r for r in L if not r['over_px'] and not r['over_rect']]
        ro = [r for r in L if not r['over_px'] and r['over_rect']]
        ov = [r for r in L if r['over_px']]
        ids = Counter_ids(ov)
        pc = [r['pieces'] for r in L]
        print('%-8s %4d | %-9d %-9d %-9d | %2d-%-2d (med %d) | %-11s | %s' % (
            k, len(L), len(ex), len(ro), len(ov), min(pc), max(pc), sorted(pc)[len(pc) // 2],
            '%d of %d' % (sum(1 for r in L if r['opaque']), len(L)), ', '.join('%s %d' % kv for kv in ids)))
    return R

def Counter_ids(rs):
    c = {}
    for r in rs:
        for o in r['over_px']:
            key = '%s:%s' % (o[1], o[2]) if o[0] == 'img' else 'wipe'
            c[key] = c.get(key, 0) + 1
    return sorted(c.items(), key=lambda kv: -kv[1])[:8]

def obj_rects(lv, room):
    """the rects (x0, x1, y0, y1: byte columns, rows; exclusive) of the shown room's choppers (fix A's rect), spikes,
    gates (the bars' column, rows 0 .. the gate's bottom) and torch flames (registered or not)"""
    from popdata import Level, T
    L = Level(lv); out = []
    for p in range(30):
        t = L.fg[(room - 1) * 30 + p] & 0x1F; c, r = p % 10, p // 10
        if t == T.chomper: out.append(('chopper', p, (4 * c, 4 * c + 4, 63 * r + 3, 63 * r + 63)))
        elif t == T.spike: out.append(('spike', p, (4 * c, min(4 * c + 6, 40), 63 * r + 34, 63 * r + 61)))
        elif t == T.gate and c < 9: out.append(('gate', p, (4 * c + 4, 4 * c + 7, max(63 * r - 6, 0), 63 * r + 63)))
        elif t in (T.torch, T.torch_with_debris) and c < 9: out.append(('torch', p, (4 * c + 5, 4 * c + 7, 63 * r + 5, 63 * r + 23)))
    return out

def touch(sa, lv, room, last=None):
    """E's extra work: the object pass's chunks that touch an object's rect without being that object's own step
    chunk (exactly its rect); under E each must lay the object's current picture over its restore"""
    sp = TC.script_path(sa)
    R = obj_rects(lv, room)
    with Emu() as e:
        S, n = TC.emu_setup(e, sp)
        last = min(last or n, n)
        i_t = e.trace_add(S['tick_done']); i_c = e.trace_add(S['obj_chunk'], mem=((S['CRX'], 4),))
        t = 0; ch = {}
        for r in e.collect(200, stop=lambda r: t >= last):
            if r.get('id') == i_t or r['addr'] == S['tick_done']: t += 1; continue
            ch.setdefault(t, []).append(tuple(r['mem'][0]))
        e.trace_clear()
    per = {}; ticks = range(2, last)
    for t in ticks:
        for (x, y, w, h) in ch.get(t, []):
            for kind, p, (x0, x1, y0, y1) in R:
                ox = min(x + w, x1) - max(x, x0); oy = min(y + h, y1) - max(y, y0)
                if ox <= 0 or oy <= 0: continue
                own = (x, x + w, y, y + h) == (x0, x1, y0, y1) or (kind == 'gate' and x == x0 and w <= 3) or \
                      (kind == 'torch' and (x, y, w, h) == (x0, y0, 2, 18))
                d = per.setdefault(kind, [0, 0, 0, 0])
                if own: d[0] += 1
                else: d[1] += 1; d[2] += ox * oy; d[3] += 1 if t else 0
    print('%s: %d ticks, objects %s' % (os.path.basename(sa), len(ticks), ' '.join('%s%d' % (k, p) for k, p, _ in R)))
    for k, (own, other, area, _) in sorted(per.items()):
        print('  %-8s own step chunks %4d (%.2f a tick) | other chunks touching %4d (%.2f a tick), %6.1f bytes a plane each' % (
            k, own, own / len(ticks), other, other / len(ticks), area / other if other else 0))

def model(csv_path, e_costs):
    """frames a tick (median / p90) per scene: now (measured a), the model now, the model with E's costs"""
    import csv as C
    import busyrooms as BR
    rows = list(C.DictReader(open(csv_path)))
    import numpy as np
    K = BR.KINDS
    X = np.array([[float(r[k]) for k in K] for r in rows]); y = np.array([float(r['a_work']) - float(r['b_work']) for r in rows])
    c, *_ = np.linalg.lstsq(X, y, rcond=None)
    bad = sorted(set(e_costs) - set(K))
    if bad: sys.exit('optione.py model: unknown kind(s) %s in --e (known: %s)' % (', '.join(bad), ' '.join(K)))
    cost = dict(zip(K, c)); new = dict(cost); new.update(e_costs)
    sc = {}
    for r, x in zip(rows, X):
        if r['variant'] not in ('walk', 'stand'): continue
        bw = float(r['b_work']); fa = float(r['a_frames'])
        m0 = max(4.0, bw + sum(cost[k] * v for k, v in zip(K, x)))
        m1 = max(4.0, bw + sum(new[k] * v for k, v in zip(K, x)))
        sc.setdefault((r['scene'], r['variant']), []).append((fa, m0, m1))
    pct = BR.pct
    print('costs now: ' + ' '.join('%s %.2f' % (k, cost[k]) for k in K if abs(cost[k]) > .005))
    print('costs E:   ' + ' '.join('%s %.2f' % (k, new[k]) for k in K if abs(new[k]) > .005))
    print('%-14s %5s | %-13s | %-13s | %-13s' % ('scene', 'ticks', 'measured', 'model now', 'model E'))
    for (s, v), L in sc.items():
        f = lambda i: '%5.2f / %5.2f' % (pct([l[i] for l in L], .5), pct([l[i] for l in L], .9))
        print('%-14s %5d | %s | %s | %s' % (s + ' ' + v, len(L), f(0), f(1), f(2)))

def direct(scripts):
    """M8a part 17: every direct copy (tcache.asm tc_direct, td_go to td_end) of each script against the beam. The beam's
    line is the time since the VBLN interrupt's entry (game.asm isr; a frame is 312 x 228 T), canvas row = line - 113
    (sprite.asm BEAM_Y0). A copy tears when the beam is on one of the rect's rows CRY..CRY + CRH - 1 at any time from its
    first VRAM write to its last. Prints per script the copies, the torn ones (0 is the claim), the copy's length in
    lines (max) and the closest the beam came: the lines from the copy's end to the beam's next arrival at the top row,
    and from the beam leaving the bottom row to the copy's start (min)."""
    F = TC.FRAME; bad_all = 0
    for sp in scripts:
        with Emu() as e:
            S, n = TC.emu_setup(e, TC.script_path(sp))
            i_isr = e.trace_add(S['isr']); i_go = e.trace_add(S['td_go'], mem=((S['CRX'], 4),))
            i_in = e.trace_add(S['tc_direct']); t_in = None; waits = []
            i_end = e.trace_add(S['td_end']); i_done = e.trace_add(S['tick_done'])
            t = 0; isr = None; go = None; cps = []
            for r in e.collect(200, stop=lambda r: t >= n):
                k = r.get('id')
                if k == i_isr or (k is None and r['addr'] == S['isr']): isr = r['cycles']
                elif k == i_in or (k is None and r['addr'] == S['tc_direct']): t_in = r['cycles']
                elif k == i_go or (k is None and r['addr'] == S['td_go']):
                    go = (r['cycles'], r['mem'][0])
                    if t_in is not None: waits.append((r['cycles'] - t_in) / 228.0)
                elif k == i_end or (k is None and r['addr'] == S['td_end']):
                    if go and isr is not None: cps.append((go[0] - isr, r['cycles'] - isr, go[1]))
                    go = None
                else: t += 1
            e.trace_clear()
        torn = 0; ln = 0; pre = post = 10 ** 9
        if go:                                       # a copy still open when the trace ended: counted as torn
            torn += 1; print('%s: warning: a copy was still open at the end of the trace (counted as torn)' % os.path.basename(sp))
        for a, b, (x, y, w, h) in cps:
            la, lb = a / 228.0, b / 228.0          # lines since the interrupt before the copy
            ln = max(ln, lb - la)
            top = 113 + y                            # the beam is on the rect in lines [top + 312 k, top + h + 312 k)
            k = int((la - top) // 312)
            for kk in (k - 1, k, k + 1, k + 2):
                s0, s1 = top + 312 * kk, top + h + 312 * kk
                if s0 < lb and la < s1: torn += 1; break
            nxt = min(s for s in (top + 312 * kk for kk in range(k - 1, k + 3)) if s >= lb)
            prv = max(s for s in (top + h + 312 * kk for kk in range(k - 2, k + 2)) if s <= la)
            pre = min(pre, nxt - lb); post = min(post, la - prv)
        bad_all += torn
        print('%s: %d direct copies (%.2f a tick), %d torn; longest %.1f lines; the beam at least %.1f lines after the end, '
              '%.1f lines before the start; the wait for the beam %.1f lines a copy (mean), %.1f at most' % (
              os.path.basename(sp), len(cps), len(cps) / max(n, 1), torn, ln, pre if cps else 0, post if cps else 0,
              sum(waits) / len(waits) if waits else 0, max(waits) if waits else 0))
    return bad_all

def direct2(scripts):
    """M8a part 25: every direct copy of a complete picture (frmlow2.asm lc_direct: ld_go to ld_end, a row's four planes at
    a time, top row first) against the beam. Row r is written from its start (the trace at ld_r) to the next row's start;
    the beam is on canvas row y + r during [isr + (113 + y + r + 312 k) x 228, + 228) T. A pass k of the beam over the rect
    shows row r new when the row was written before the beam came, old when it was written after the beam left, torn
    when the two overlap; the pass is torn when a row is torn or the rows are mixed (some new, some old). Prints per
    script the copies, the torn passes (0 is the claim), the longest copy (lines), lines a row (max), the closest the
    beam came to the row being written (lines, min: behind it, ahead of it) and the wait for the beam (lines)."""
    from m3_test import syms
    L2 = syms(os.path.join(ROOT, 'build', 'ovl_low2.sym'))
    bad_all = 0
    for sp in scripts:
        with Emu() as e:
            S, n = TC.emu_setup(e, TC.script_path(sp))
            pts = {'isr': S['isr'], 'in': L2['lc_direct'], 'go': L2['ld_go'], 'row': L2['ld_r'], 'end': L2['ld_end'],
                   'done': S['tick_done']}
            ids = {}
            for k, a in pts.items():
                ids[e.trace_add(a, mem=((S['CRX'], 4),) if k == 'go' else ())] = k
            by = {a: k for k, a in pts.items()}
            t = 0; isr = None; cur = None; cps = []; t_in = None; waits = []
            for r in e.collect(200, stop=lambda r: t >= n):
                k = ids.get(r.get('id')) or by.get(r['addr'])
                c = r['cycles']
                if k == 'isr': isr = c
                elif k == 'in': t_in = c
                elif k == 'go':
                    cur = {'isr': isr, 'rect': r['mem'][0], 'rows': []}
                    if t_in is not None: waits.append((c - t_in) / 228.0)
                elif k == 'row' and cur is not None: cur['rows'].append(c)
                elif k == 'end' and cur is not None: cur['end'] = c; cps.append(cur); cur = None
                elif k == 'done': t += 1
            e.trace_clear()
        torn = 0; ln = 0; lpr = 0; behind = ahead = 10 ** 9
        for cp in cps:
            x, y, w, h = cp['rect']; rows = cp['rows'] + [cp['end']]
            assert len(rows) == h + 1, (sp, 'rows traced', len(rows) - 1, h)
            base = cp['isr']
            ln = max(ln, (rows[-1] - rows[0]) / 228.0)
            lpr = max(lpr, max((rows[i + 1] - rows[i]) / 228.0 for i in range(h)))
            l0 = (rows[0] - base) / 228.0
            k0 = int((l0 - 113 - y) // 312)
            for kk in range(k0 - 1, k0 + 3):
                st = set()
                for i in range(h):
                    T0 = base + (113 + y + i + 312 * kk) * 228
                    if rows[i + 1] <= T0: st.add('new'); behind = min(behind, (T0 - rows[i + 1]) / 228.0)
                    elif rows[i] >= T0 + 228: st.add('old'); ahead = min(ahead, (rows[i] - T0 - 228) / 228.0)
                    else: st.add('torn')
                if 'torn' in st or len(st) > 1: torn += 1
        bad_all += torn
        print('%s: %d direct copies (%.2f a tick), %d torn passes; longest %.1f lines, %.2f lines a row at most; the beam at '
              'least %.1f lines after a row was written, %.1f lines before; the wait %.1f lines a copy (mean), %.1f at most' % (
              os.path.basename(sp), len(cps), len(cps) / max(n, 1), torn, ln, lpr, behind if cps else 0, ahead if cps else 0,
              sum(waits) / len(waits) if waits else 0, max(waits) if waits else 0))
    return bad_all

def main():
    a = sys.argv[1:]
    if not a: sys.exit(__doc__)
    if a[0] == 'direct': sys.exit(1 if direct(a[1:]) else 0)
    if a[0] == 'direct2': sys.exit(1 if direct2(a[1:]) else 0)
    if a[0] == 'profile': profile(a[1], a[2], [int(x) for x in a[3].split(',')])
    elif a[0] == 'diff': diff(a[1], a[2], [int(x) for x in a[3].split(',')])
    elif a[0] == 'chunks': chunks(a[1], [int(x) for x in a[2].split(',')])
    elif a[0] == 'census':
        R = census([int(x) for x in a[1].split(',')] if len(a) > 1 and not a[1].startswith('-') else list(range(1, 15)))
        if '--list' in a:
            for r in R:
                if r['over_px'] or r['over_rect']: print(r)
    elif a[0] == 'touch': touch(a[1], int(a[2]), int(a[3]))
    elif a[0] == 'model':
        e = {}
        if '--e' in a:
            i = a.index('--e')
            if i + 1 >= len(a): sys.exit('optione.py model: --e needs K=V,... (kinds: tools/busyrooms.py KINDS)')
            for kv in a[i + 1].split(','):
                if '=' not in kv: sys.exit('optione.py model: --e %r is not K=V' % kv)
                k, v = kv.split('=', 1); e[k] = float(v)
        model(a[1], e)
    else: sys.exit(__doc__)

if __name__ == '__main__': main()
