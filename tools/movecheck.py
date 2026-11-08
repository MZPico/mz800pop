#!/usr/bin/env python3
"""M8a part 14: the moving-part redraws (src/m4/colshift.asm, src/m4/btnstep.asm) simulated on the Python reference
(tools/popdata.py RoomRenderer, the renderer the pixel tests compare with) for every gate, level door and button of
levels 1-14, whole screen, every step (docs/perf.md "M8a part 14"). The shadow room holds the back and mid ops (and the
wipes before them), not the fore pieces: the steps are checked on that picture. A piece laid over the moved picture is
painted as the Z80 lays it: a copy-mode piece only inside its extent (build/assets/*.dir; the dungeon's gate slices
copy 20 of their 24 pixels, the reference paints all 24 over what is under them, which shows the same there). Where an
extent reaches past the reference's image (a door piece's last pixel), the emulator's pixel tests are the check.
  gates    every gate drawn on a screen (our room's columns 0-8, the left room's column 9) whose bars tile is one of
           colshift.asm's types, every one-row step p -> p +- 1 (p = min(mod, 188) / 4, both <= 46): the old picture
           with rows GT..S1 - 1 moved by k (closing: GT + 1..), 68 and the new top frame laid over rows
           max(GT - 9, 0)..GT - 1, closing: the new frame slice laid, a dungeon pillar's base (92) laid again, min(p) <= 12: rows MY - 13..MY - min - 1
           from the new picture (run_rect)
  doors    every level door (not in the start room), every opening step ml -> ml + 1 (ml <= 43): rows
           max(yb - 50, 0)..yb - ml - 1 moved one row up (in the dungeon only the left two pixels of the sixth byte),
           row yb - ml: the old row with 99 and 144 laid over it; the ops that change are the slices (33) only (and
           144 at 0 -> 1)
  buttons  every button seen in its own room, pressed and released: the changed pixels within x 4c..4c + 7 (to 40),
           rows 63r + 49..63r + 65, only back ops change, as many in both states
  chompers every chopper seen in its own room, every pair of pictures n -> m (n, m = 0..4, no blood: frames.asm): the
           old picture with the rect x 4c..4c + 3, rows 63r + 3..63r + 62 taken from the new one is the new one; the
           fore ops that change lie in the rect; the ops that change are the bottom (101-105), top (111-113) and fore
           (106-110) pieces, in place (same list, same index), bottoms kept (the top's CHOMPER_FRAM_Y[m] above the
           bottom's), unless the top piece comes or goes (then frames.asm regenerates the tile)
  spikes   every spike seen in its own room, every pair of pictures (frames.asm fs_canon: 0..5): the rect x 4c..4c + 5
           (to 40), rows 63r + 34..63r + 60 the same way; the pieces 128-132, 139-143 (own tile) and 134-138 (the right
           neighbour) in place with their bottoms kept, unless one side is picture 0
  torches  (M8a part 16) every torch flame drawn on a screen (our room's columns 0-8, the left room's column 9), at
           every position of a gate right of the torch: the ops after the flame that touch its rect (the Z80's record
           rects: whole byte columns). view.asm flames_build registers a flame when there are none, or when the one
           op after it is CH_ENV 46 (spike.asm fb_over: the base of the gate the flame's tile draws); then 46 must
           have no pixel inside the flame's rect (laying the flame alone gives the picture)
  caches   (M8a part 17, tcache.asm) every screen of levels 1-14 (our room), every potion at each bubble frame 1..7: at
           most 4 torch flames (view.asm FLM_MAX) on a screen, and no potion bubble's rect touches a flame's (room.asm
           op_patch bumps no fore_gen for a bubble: the flames' cached pictures never hold a bubble)
  loose    (M8a part 18) every loose floor of levels 1-14 on every screen that shows it, every pair of modifiers 0..11,
           0x80..0x8B: which tiles' ops change (spike.asm loose_redraw regenerates those only)
usage: movecheck.py [gates|doors|buttons|chompers|spikes|torches|caches|loose ...]   (default all; ~15 minutes)"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from collections import Counter
from popdata import Level, RoomRenderer, T, CHOMPER_FRAM_Y, COL_XH, CH_ENV, CH_WALL, B_NOTRANSP, B_OR, B_TRANSP, B_BLACK, B_MONO

def shadow(rr):
    """the room's back and mid ops (and the wipes before them) painted: what the shadow room holds"""
    scr = [[0] * 320 for _ in range(200)]
    for left, top, width, height, color in rr.ops['wipe0']:
        col = rr.wallcol.get(color, color) if color >= 0x60 else color
        for y in range(max(top, 0), min(top + height, 200)):
            for x in range(max(left, 0), min(left + width, 320)): scr[y][x] = col
    for op in rr.ops['back'] + rr.ops['mid']: paint0(scr, rr, op)
    return scr

def paint0(scr, rr, op):
    """one op as the reference paints it (the whole image)"""
    ch, id1, x0, y0, blit = op
    w, h, rows = rr.sets[ch].get(id1)
    mono = rr.sets[ch].mono_colour(blit & 0x0F) if blit >= B_MONO else 0
    for y in range(h):
        sy = y0 + y
        if not 0 <= sy < 200: continue
        for x in range(w):
            sx = x0 + x
            if not 0 <= sx < 320: continue
            c = rows[y][x]
            if blit == B_NOTRANSP: scr[sy][sx] = max(c, 0)
            elif blit in (B_OR, B_TRANSP):
                if c >= 0: scr[sy][sx] = c
            elif blit == B_BLACK:
                if c >= 0: scr[sy][sx] = 0
            elif c >= 0: scr[sy][sx] = mono

DIRS = {}
def extent(rr, ch, id1):
    """the Z80's copy-mode extent of an image (build/assets/<set>.dir: flags bit 1 = a partial edge column, then the
    masks of the first and the last byte column; bit n = pixel n of the byte): its pixels outside are not copied"""
    name = {CH_ENV: 'env', CH_WALL: 'wall'}.get(ch)
    if not name: return None
    f = ('palace' if rr.ltype else 'dungeon') + ('_wall' if name == 'wall' else '')
    if f not in DIRS: DIRS[f] = open(os.path.join(HERE, '..', 'build', 'assets', f + '.dir'), 'rb').read()
    e = DIRS[f][8 * id1:8 * id1 + 8]
    return (e[3], e[6], e[7]) if e[5] & 2 else None

def paint(scr, rr, op, clip=(0, 320, 0, 200)):
    """one op over scr; a copy-mode op only inside its Z80 extent (what the Z80 lays over a picture)"""
    ch, id1, x0, y0, blit = op
    w, h, rows = rr.sets[ch].get(id1)
    mono = rr.sets[ch].mono_colour(blit & 0x0F) if blit >= B_MONO else 0
    ext = extent(rr, ch, id1) if blit == B_NOTRANSP else None
    for y in range(h):
        sy = y0 + y
        if not clip[2] <= sy < clip[3]: continue
        for x in range(w):
            sx = x0 + x
            if not clip[0] <= sx < clip[1]: continue
            if ext and ((x < 8 and not ext[1] >> (x & 7) & 1) or (x >= 8 * (ext[0] - 1) and not ext[2] >> (x & 7) & 1)):
                continue
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

GATE_BARS_OK = {T.empty, T.floor, T.stuck, T.closer, T.loose, T.opener, T.torch, T.gate}   # colshift.asm cs_okmap (and
                                                                                          # the dungeon's pillar)

def gates():
    n = bad = other = 0
    st = list(range(0, 189, 4))
    for lv, room, i, r, bc in tiles(T.gate):
        L = Level(lv)
        bt = L.fg[(room - 1) * 30 + r * 10 + bc] & 0x1F
        pillar = bt == T.pillar and L.type == 0
        if bt not in GATE_BARS_OK and not pillar: other += 1; continue
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
            for y in range(GT + (k < 0), S1):
                for x in range(X0, X0 + 24): pred[y][x] = old[y + k][x]
            if k < 0:
                fr = [op for op in ops if op[0] == CH_ENV and 52 <= op[1] <= 59 and op[2] == X0 and op[3] == GT]
                paint(pred, rr, fr[0], clip)
            if pillar:
                for op in ops:
                    if op[0] == CH_ENV and op[1] == 92 and op[2] == X0: paint(pred, rr, op, clip)
            if mn <= 12:
                for y in range(MY - 13, MY - mn):
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

def own_tiles(t):
    """(level, room, tile index, row, column) for every tile of type t in its own room"""
    for lv in range(1, 15):
        L = Level(lv)
        for room in range(1, 25):
            for p in range(30):
                if L.fg[(room - 1) * 30 + p] & 0x1F == t: yield lv, room, (room - 1) * 30 + p, p // 10, p % 10

def frames_check(name, t, mods, W, Y0, H, ranges, top):
    """the frames overlay's two claims for every object of type t: the rect and the records patched in place"""
    n = bad = 0
    for lv, room, i, r, c in own_tiles(t):
        L = Level(lv); m0 = L.bg[i]
        x0, x1, y0, y1 = 32 * c, min(32 * c + 8 * W, 320), 63 * r + Y0, 63 * r + Y0 + H
        R = {}
        for k, m in mods.items():
            L.bg[i] = m; rr, sh = render(L, room); R[k] = (sh, rr.ops)
        L.bg[i] = m0
        for a in R:
            for b in R:
                if a == b: continue
                n += 1; errs = []
                old, oo = R[a]; new, no = R[b]
                pred = [row[:] for row in old]
                for y in range(y0, y1):
                    for x in range(x0, x1): pred[y][x] = new[y][x]
                d = diff(pred, new)
                if d: errs.append('%d pixels outside the rect' % d)
                for op in (Counter(oo['fore']) - Counter(no['fore'])) + (Counter(no['fore']) - Counter(oo['fore'])):
                    rr = RoomRenderer(L); w, h, _ = rr.sets[op[0]].get(op[1])
                    if not (op[2] >= x0 and op[2] + w <= x1 and op[3] >= y0 and op[3] + h <= y1): errs.append('fore op %s outside' % (op,))
                for lst in ('wipe0', 'wipe1', 'mid'):
                    if oo[lst] != no[lst]: errs.append(lst + ' ops change')
                if top(a) == top(b):        # patched in place: same lists but the pieces, each at its index
                    for lst in ('back', 'fore'):
                        if len(oo[lst]) != len(no[lst]): errs.append(lst + ' count changes'); continue
                        for po, pn in zip(oo[lst], no[lst]):
                            if po == pn: continue
                            rg = [g for g in ranges if g[0] <= po[1] <= g[1]]
                            ho = RoomRenderer(L).sets[po[0]].get(po[1])[1]; hn = RoomRenderer(L).sets[pn[0]].get(pn[1])[1]
                            ok = rg and rg[0][0] <= pn[1] <= rg[0][1] and po[0] == pn[0] and po[2] == pn[2] and po[4] == pn[4]
                            if ok and rg[0][2] == 'top':
                                bot = lambda ops: [q for q in ops if 101 <= q[1] <= 105 and q[0] == po[0]][0]
                                bo, bn = bot(oo['back']), bot(no['back'])
                                hb = lambda q: RoomRenderer(L).sets[q[0]].get(q[1])[1]
                                ok = pn[3] + hn - 1 == bn[3] + hb(bn) - 1 - CHOMPER_FRAM_Y[b]
                            elif ok:
                                ok = po[3] + ho - 1 == pn[3] + hn - 1
                            if not ok: errs.append('%s op %s -> %s' % (lst, po, pn))
                if errs:
                    bad += 1; print('%s: level %d room %d tile %d %d -> %d: %s' % (name, lv, room, i, a, b, ', '.join(errs[:4])))
    print('%s: %d steps, %d differ' % (name, n, bad), flush=True)
    return bad

def chompers():
    return frames_check('chompers', T.chomper, {3: 0, 2: 1, 0: 2, 1: 3, 4: 4}, 4, 3, 60,
                        [(101, 105, 'bottom'), (106, 110, 'fore'), (111, 113, 'top')], lambda n: n >= 2)

def spikes():
    return frames_check('spikes', T.spike, {k: k for k in range(6)}, 6, 34, 27,
                        [(128, 132, 'left'), (134, 138, 'right'), (139, 143, 'fore')], lambda p: p > 0)

def torches():
    n = bad = alone = by46 = other = 0
    for t in (T.torch, T.torch_with_debris):
        for lv, room, i, r, c in tiles(t):
            L = Level(lv)
            gi = None
            if c < 10:
                gi = (room - 1) * 30 + r * 10 + c            # the tile right of the torch draws the flame
                if L.fg[gi] & 0x1F != T.gate: gi = None
            m0 = L.bg[gi] if gi is not None else None
            for m in range(0, 189, 4) if gi is not None else [None]:
                if gi is not None: L.bg[gi] = m
                rr = RoomRenderer(L); rr.draw_room(room)
                ol = [('img',) + tuple(o) for o in rr.ops['back'] + rr.ops['mid']] + [('wipe',) + tuple(o) for o in rr.ops['wipe1']]
                xf = 32 * c + 8                                # the flame: draw_xh + 1 of the drawing tile
                fl = [k for k, o in enumerate(ol) if o[0] == 'img' and o[1] == 1 and 1 <= o[2] <= 9 and o[3] == xf
                      and 63 * r <= o[4] + 40 <= 63 * r + 63]
                for k in fl:
                    n += 1
                    f = ol[k]; fw, fh, _ = rr.sets[1].get(f[2])
                    fx0, fx1, fy0, fy1 = f[3] // 8, (f[3] + fw - 1) // 8, f[4], f[4] + fh - 1
                    ov = []
                    for o in ol[k + 1:]:
                        if o[0] == 'wipe': x0, x1, y0, y1 = o[1] // 8, (o[1] + o[3] - 1) // 8, o[2], o[2] + o[4] - 1
                        else:
                            w, h, _ = rr.sets[o[1]].get(o[2]); x0, x1, y0, y1 = o[3] // 8, (o[3] + w - 1) // 8, o[4], o[4] + h - 1
                        if x1 >= fx0 and x0 <= fx1 and y1 >= fy0 and y0 <= fy1: ov.append(o)
                    if not ov: alone += 1; continue
                    if len(ov) != 1 or ov[0][:3] != ('img', CH_ENV, 46): other += 1; continue
                    by46 += 1
                    scr = [[None] * 320 for _ in range(200)]
                    paint(scr, rr, ov[0][1:], clip=(8 * fx0, 8 * fx1 + 8, fy0, fy1 + 1))
                    px = sum(1 for y in range(200) for x in range(320) if scr[y][x] is not None)
                    if px:
                        bad += 1; print('torches: level %d room %d tile %d gate %s: 46 has %d pixels in the flame' % (lv, room, i, m, px))
            if gi is not None: L.bg[gi] = m0
    print('torches: %d flames (states), %d alone, %d with the gate base 46 after them, %d with other ops, %d differ' % (
        n, alone, by46, other, bad), flush=True)
    return bad

def caches():
    from popdata import POTION_FRAM_BUBB
    B = set(POTION_FRAM_BUBB[1:8]); n = bad = mf = 0
    for lv in range(1, 15):
        L = Level(lv)
        pots = [i for i in range(len(L.fg)) if L.fg[i] & 0x1F == T.potion]
        m0 = {i: L.bg[i] for i in pots}
        for room in range(1, 25):
            for f in range(1, 8):
                for i in pots: L.bg[i] = (m0[i] & 0xF8) | f
                rr = RoomRenderer(L); rr.draw_room(room); n += 1
                fl = [o for o in rr.ops['back'] if o[0] == 1 and 1 <= o[1] <= 9 and o[3] >= 0]
                bb = [o for o in rr.ops['fore'] if o[0] == 1 and o[1] in B]
                mf = max(mf, len(fl)); errs = []
                if len(fl) > 4: errs.append('%d flames' % len(fl))
                for b in bb:
                    w, h, _ = rr.sets[1].get(b[1]); bx0, bx1 = b[2] // 8, (b[2] + w - 1) // 8
                    for o in fl:
                        fw, fh, _ = rr.sets[1].get(o[1])
                        if bx0 <= (o[2] + fw - 1) // 8 and bx1 >= o[2] // 8 and b[3] < o[3] + fh and o[3] < b[3] + h:
                            errs.append('bubble %s touches flame %s' % (b, o))
                if errs: bad += 1; print('caches: level %d room %d frame %d: %s' % (lv, room, f, ', '.join(errs)))
        for i in pots: L.bg[i] = m0[i]
    print('caches: %d screens x bubble frames, at most %d flames a screen, %d differ' % (n, mf, bad), flush=True)
    return bad

class TaggedRenderer(RoomRenderer):
    """RoomRenderer whose ops are kept per tile: {(above, row, col): (back, mid, fore, wipe0, wipe1) of its draw}"""
    def _tagged(self, f, key):
        n0 = {k: len(v) for k, v in self.ops.items()}
        f()
        self.by_tile[key] = tuple(tuple(self.ops[k][n0[k]:]) for k in ('back', 'mid', 'fore', 'wipe0', 'wipe1'))
    def draw_tile(self):
        self._tagged(super().draw_tile, (0, self.drawn_row, self.drawn_col))
    def draw_tile_aboveroom(self):
        self._tagged(super().draw_tile_aboveroom, (1, self.drawn_row, self.drawn_col))
    def draw_room(self, room):
        self.by_tile = {}
        return super().draw_room(room)

def loose():
    """M8a part 18 (spike.asm loose_redraw): a loose floor's picture is LOOSE_FRAM_BOTTOM[loose_frame(modifier)] (the
    left and right pieces follow it); for every loose floor of levels 1-14, every screen that shows it and every
    modifier 0..11, 0x80..0x8B: the same picture gives identical op lists; a different one changes only the ops of its
    own tile and its right neighbour (our room), our column 0 (the left room's column 9), its own tile (the above room's
    row 2), nothing (the below room's row 0)"""
    from popdata import LOOSE_FRAM_BOTTOM
    mods = list(range(12)) + list(range(0x80, 0x8C))
    rr0 = RoomRenderer(Level(1))
    pic = lambda m: LOOSE_FRAM_BOTTOM[rr0.loose_frame(m)]
    n = bad = 0; seen = Counter()
    for lv in range(1, 15):
        L = Level(lv)
        for i in range(len(L.fg)):
            if L.fg[i] & 0x1F != T.loose: continue
            room, p = i // 30 + 1, i % 30; r, c = p // 10, p % 10
            screens = [(room, 'own', {(0, r, c)} | ({(0, r, c + 1)} if c < 9 else set()))]
            for s in range(1, 25):
                lk = L.links(s)
                if c == 9 and lk[0] == room: screens.append((s, 'left', {(0, r, 0)}))
                if r == 2 and lk[2] == room: screens.append((s, 'above', {(1, 2, c)}))
                if r == 0 and lk[3] == room: screens.append((s, 'below', set()))
            m0 = L.bg[i]
            for s, kind, expect in screens:
                ops = {}
                for m in mods:
                    L.bg[i] = m; rr = TaggedRenderer(L); rr.draw_room(s); ops[m] = rr.by_tile
                L.bg[i] = m0
                seen[kind] += 1
                for a in mods:
                    for b in mods:
                        if a >= b: continue
                        n += 1
                        diff_t = {k for k in ops[a] if ops[a][k] != ops[b].get(k)}
                        ok = not diff_t if pic(a) == pic(b) else diff_t <= expect
                        if not ok:
                            bad += 1
                            print('loose: level %d tile %d on screen %d (%s) %#x -> %#x: tiles %s differ' % (
                                lv, i, s, kind, a, b, sorted(diff_t)))
    print('loose: %s screens, %d modifier pairs, %d differ' % (dict(seen), n, bad), flush=True)
    return bad

if __name__ == '__main__':
    what = sys.argv[1:] or ['gates', 'doors', 'buttons', 'chompers', 'spikes', 'torches', 'caches', 'loose']
    sys.exit(1 if sum(globals()[w]() for w in what) else 0)
