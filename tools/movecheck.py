#!/usr/bin/env python3
"""M8a part 14: the moving-part redraws (src/m4/colshift.asm, src/m4/btnstep.asm) simulated on the Python reference
(tools/popdata.py RoomRenderer, the renderer the pixel tests compare with) for every gate, level door and button of
levels 1-14, whole screen, every step (docs/perf.md "M8a part 14"). The shadow room holds the back and mid ops (and the
wipes before them), not the fore pieces: the steps are checked on that picture.
  gates    every gate drawn on a screen (our room's columns 0-8, the left room's column 9) whose bars tile is one of
           colshift.asm's types, every one-row step p -> p +- 1 (p = min(mod, 188) / 4, both <= 46): the old picture
           with rows GT..S1 - 1 moved by k, 68 and the new top frame laid over rows max(GT - 9, 0)..GT - 1, closing:
           the new frame slice laid, min(p) <= 12: rows MY - 13..MY - 1 from the new picture (run_rect)
  doors    every level door (not in the start room), every opening step ml -> ml + 1 (ml <= 43): rows
           max(yb - 50, 0)..yb - ml - 1 moved one row up (in the dungeon only the left two pixels of the sixth byte),
           row yb - ml: the old row with 99 and 144 laid over it; the ops that change are the slices (33) only (and
           144 at 0 -> 1)
  buttons  every button seen in its own room, pressed and released: the changed pixels within x 4c..4c + 7 (to 40),
           rows 63r + 49..63r + 65, only back ops change, as many in both states
usage: movecheck.py [gates|doors|buttons ...]   (default all; ~10 minutes)"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from collections import Counter
from popdata import Level, RoomRenderer, T, COL_XH, CH_ENV, B_NOTRANSP, B_OR, B_TRANSP, B_BLACK, B_MONO

def shadow(rr):
    """the room's back and mid ops (and the wipes before them) painted: what the shadow room holds"""
    scr = [[0] * 320 for _ in range(200)]
    for left, top, width, height, color in rr.ops['wipe0']:
        col = rr.wallcol.get(color, color) if color >= 0x60 else color
        for y in range(max(top, 0), min(top + height, 200)):
            for x in range(max(left, 0), min(left + width, 320)): scr[y][x] = col
    for op in rr.ops['back'] + rr.ops['mid']: paint(scr, rr, op)
    return scr

def paint(scr, rr, op, clip=(0, 320, 0, 200)):
    ch, id1, x0, y0, blit = op
    w, h, rows = rr.sets[ch].get(id1)
    mono = rr.sets[ch].mono_colour(blit & 0x0F) if blit >= B_MONO else 0
    for y in range(h):
        sy = y0 + y
        if not clip[2] <= sy < clip[3]: continue
        for x in range(w):
            sx = x0 + x
            if not clip[0] <= sx < clip[1]: continue
            c = rows[y][x]
            if blit == B_NOTRANSP: scr[sy][sx] = max(c, 0)
            elif blit in (B_OR, B_TRANSP):
                if c >= 0: scr[sy][sx] = c
            elif blit == B_BLACK:
                if c >= 0: scr[sy][sx] = 0
            elif c >= 0: scr[sy][sx] = mono

def render(L, room):
    rr = RoomRenderer(L); rr.draw_room(room)
    return rr, shadow(rr)

def diff(a, b):
    return sum(1 for y in range(192) for x in range(320) if a[y][x] != b[y][x])

def tiles(t):
    """(level, shown room, tile index, row, column of the tile that draws its right part) for every tile of type t
    drawn by a tile of the shown room: our room's columns 0-8, the left room's column 9 (drawn by our column 0)"""
    for lv in range(1, 15):
        L = Level(lv)
        for room in range(1, 25):
            for p in range(30):
                i = (room - 1) * 30 + p
                if L.fg[i] & 0x1F == t and p % 10 != 9: yield lv, room, i, p // 10, p % 10 + 1
            left = L.links(room)[0]
            if left:
                for r in range(3):
                    i = (left - 1) * 30 + r * 10 + 9
                    if L.fg[i] & 0x1F == t: yield lv, room, i, r, 0

GATE_BARS_OK = {T.empty, T.floor, T.stuck, T.closer, T.loose, T.opener, T.torch, T.gate}   # colshift.asm cs_okmap

def gates():
    n = bad = other = 0
    st = list(range(0, 189, 4))
    for lv, room, i, r, bc in tiles(T.gate):
        L = Level(lv)
        if L.fg[(room - 1) * 30 + r * 10 + bc] & 0x1F not in GATE_BARS_OK: other += 1; continue
        GT = 63 * r + 3; MY = GT + 59; X0 = COL_XH[bc] * 8; T0 = max(GT - 9, 0)
        R = {}
        for m in st:
            L.bg[i] = m; rr, sh = render(L, room); R[m] = (sh, rr, rr.ops['back'] + rr.ops['mid'])
        for a, b in list(zip(st, st[1:])) + list(zip(st[1:], st)):
            po, pn = a // 4, b // 4; k = pn - po; mn = min(po, pn)
            if max(po, pn) > 46: continue
            n += 1
            old = R[a][0]; new, rr, ops = R[b]
            S1 = MY - 13 if mn <= 12 else MY - mn
            pred = [row[:] for row in old]
            clip = (X0, X0 + 24, T0, S1)
            top = [op for op in ops if op[0] == CH_ENV and 60 <= op[1] <= 67 and op[2] == X0 and op[3] == GT - 9]
            if top:
                paint(pred, rr, (CH_ENV, 68, X0, GT - 9, B_MONO), clip)
                paint(pred, rr, top[0], clip)
            for y in range(GT, S1):
                for x in range(X0, X0 + 24): pred[y][x] = old[y + k][x]
            if k < 0:
                fr = [op for op in ops if op[0] == CH_ENV and 52 <= op[1] <= 59 and op[2] == X0 and op[3] == GT]
                paint(pred, rr, fr[0], clip)
            if mn <= 12:
                for y in range(MY - 13, MY):
                    for x in range(X0, X0 + 24): pred[y][x] = new[y][x]
            d = diff(pred, new)
            if d: bad += 1; print('gate: level %d room %d tile %d step %d -> %d: %d pixels differ' % (lv, room, i, a, b, d))
    print('gates: %d steps, %d differ (%d gates with another bars tile: the old way)' % (n, bad, other), flush=True)
    return bad

def doors():
    n = bad = 0
    for lv, room, i, r, dc in tiles(T.level_door_left):
        L = Level(lv)
        if L.start_room == room: continue
        MY = 63 * r + 62; yb = MY - 13; X0 = (COL_XH[dc] + 1) * 8; WD = 48 if L.type else 42
        R = {}
        for ml in range(0, 45):
            L.bg[i] = ml; rr, sh = render(L, room); R[ml] = (sh, rr, Counter(rr.ops['back'] + rr.ops['mid']))
        for ml in range(0, 44):
            n += 1
            old, _, oo = R[ml]; new, rr, no = R[ml + 1]
            T0 = max(yb - 50, 0); Rw = yb - ml
            pred = [row[:] for row in old]
            for y in range(T0, Rw):
                for x in range(X0, X0 + WD): pred[y][x] = old[y + 1][x]
            for idd, ybot in ((99, yb), (144, yb - 4)):
                h = rr.sets[CH_ENV].get(idd)[1]
                paint(pred, rr, (CH_ENV, idd, X0, ybot - h + 1, B_NOTRANSP), (X0, X0 + 48, Rw, Rw + 1))
            d = diff(pred, new)
            ch = [op[1] for op in ((oo - no) + (no - oo)).elements()]
            ops_ok = all(v == 33 for v in ch) or (ml == 0 and set(ch) <= {33, 144})
            if d or not ops_ok:
                bad += 1; print('door: level %d room %d tile %d step %d: %d pixels differ, changed ops %s' % (lv, room, i, ml, d, ch))
    print('doors: %d steps, %d differ' % (n, bad), flush=True)
    return bad

def buttons():
    n = bad = 0
    for lv in range(1, 15):
        L = Level(lv)
        L.dl2 = list(L.raw[1696:1696 + 256])
        for room in range(1, 25):
            for p in range(30):
                i = (room - 1) * 30 + p
                if L.fg[i] & 0x1F not in (T.opener, T.closer): continue
                m = L.bg[i]; res = []
                for timer in (0, 5):
                    L.dl2[m] = (L.dl2[m] & 0xE0) | timer
                    rr = RoomRenderer(L); im = rr.draw_room(room).load()
                    res.append((shadow(rr), [[im[x, y] for x in range(320)] for y in range(192)], rr.ops))
                L.dl2[m] = L.raw[1696 + m]
                n += 1
                r, c = divmod(p, 10)
                x0, x1, y0, y1 = 32 * c, min(32 * c + 64, 320), 63 * r + 49, 63 * r + 66
                errs = []
                for k in (0, 1):
                    A, B = res[0][k], res[1][k]
                    out = [(x, y) for y in range(192) for x in range(320) if A[y][x] != B[y][x] and not (x0 <= x < x1 and y0 <= y < y1)]
                    if out: errs.append('%d pixels outside' % len(out))
                o0, o1 = res[0][2], res[1][2]
                for t in ('mid', 'fore', 'wipe0', 'wipe1'):
                    if Counter(o0[t]) != Counter(o1[t]): errs.append(t + ' ops change')
                if len(o0['back']) != len(o1['back']): errs.append('back op count changes')
                if errs: bad += 1; print('button: level %d room %d pos %d: %s' % (lv, room, p, ', '.join(errs)))
    print('buttons: %d, %d differ' % (n, bad), flush=True)
    return bad

if __name__ == '__main__':
    what = sys.argv[1:] or ['gates', 'doors', 'buttons']
    sys.exit(1 if sum(globals()[w]() for w in what) else 0)
