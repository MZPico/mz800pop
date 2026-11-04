#!/usr/bin/env python3
"""What a moving-part-only redraw of an animated tile needs to stay pixel-exact (docs/perf.md "Busy rooms: per-room and
per-object costs"). For one tile of a room, renders the room with tools/popdata.py's RoomRenderer (the Python reference
the pixel tests compare with) at every visible state of the tile, and for each step from one state to the next:
  D        the changed pixels: their count and the bounding box (byte columns x rows)
  moving   the ops that differ between the two states (the moving part), and whether they are all opaque (blit copy)
  under    the static ops painted before the first moving op, inside D: what a restore has to put back. 'flat c'
           when the new picture's pixels in D that no new moving op covers are all colour c (then a fill restores them,
           the Apple II way); else the number of distinct colours there (a cached background is needed)
  over     the static ops painted after the first moving op that overlap D (they must be re-laid on top)
  cover    the new moving ops (opaque) cover D completely: drawing them alone gives the new picture
  shift    (gates and the level door) the pixels of D that are NOT the old picture moved up by the step's k rows
           (a gate: k = the change of min(mod, 188) / 4; the door: the change of its modifier), and their rows: where
           this is 0, moving the column by k rows gives the new picture exactly
usage: animexact.py LEVEL ROOM POS [--states a,b,c,...]  (default states per tile type: gate 0..188 by 4, chopper 1..6
       and the blood bit, level door 0..43, torch 0..8, potion bubble 1..7, spikes 0..9, loose floor 0x80..0x8a, sword 0/1)
       animexact.py --all   a summary for a tile of each type in a busy room and in another level"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from popdata import Level, RoomRenderer, T, B_NOTRANSP, B_OR, B_TRANSP, B_BLACK, B_MONO

def states_for(t, m0):
    if t == T.gate: return list(range(0, 189, 4)) + [188]
    if t == T.chomper: return [1, 2, 3, 4, 5, 6, 0x81, 0x82, 0x83, 0x84, 0x85, 0x86]
    if t == T.level_door_left: return list(range(0, 44))
    if t in (T.torch, T.torch_with_debris): return list(range(9))
    if t == T.potion: return [(m0 & 0xF8) | i for i in range(1, 8)]
    if t == T.spike: return list(range(10))
    if t == T.loose: return [0x80 + i for i in range(11)]
    if t == T.sword: return [0, 1]
    return [m0]

class Painter:
    """the ops of a draw_room call as a flat paint-order list, and a painter of any subset"""
    def __init__(self, rr):
        self.rr = rr
    def oplist(self):
        o = self.rr.ops; out = []
        for w in o['wipe0']: out.append(('wipe',) + tuple(w))
        for k in ('back', 'mid'):
            for op in o[k]: out.append(('img',) + tuple(op))
        for w in o['wipe1']: out.append(('wipe',) + tuple(w))
        for op in o['fore']: out.append(('img',) + tuple(op))
        return out
    def pixels(self, op):
        """{(x, y): colour or None (transparent: unchanged)} of one op (None for a black-blitter's untouched pixels)"""
        rr = self.rr; out = {}
        if op[0] == 'wipe':
            left, top, width, height, color = op[1:]
            col = rr.wallcol.get(color, color) if color >= 0x60 else color
            for y in range(top, top + height):
                for x in range(left, left + width):
                    if 0 <= x < 320 and 0 <= y < 200: out[(x, y)] = col
            return out
        ch, id1, x0, y0, blit = op[1:]
        w, h, rows = rr.sets[ch].get(id1)
        mono = rr.sets[ch].mono_colour(blit & 0x0F) if blit >= B_MONO else 0
        for y in range(h):
            for x in range(w):
                sx, sy = x0 + x, y0 + y
                if not (0 <= sx < 320 and 0 <= sy < 200): continue
                c = rows[y][x]
                if blit == B_NOTRANSP: out[(sx, sy)] = max(c, 0)
                elif c >= 0: out[(sx, sy)] = 0 if blit == B_BLACK else (mono if blit >= B_MONO else c)
        return out
    def opaque(self, op):
        return op[0] == 'wipe' or op[5] == B_NOTRANSP

def render(L, room, i, m):
    L.bg[i] = m
    rr = RoomRenderer(L); im = rr.draw_room(room)
    return rr, im.load(), Painter(rr).oplist()

def analyse(lv, room, pos, states=None, quiet=False):
    L = Level(lv); i = (room - 1) * 30 + pos
    t = L.fg[i] & 0x1F; m0 = L.bg[i]
    states = states or states_for(t, m0)
    name = {v: k for k, v in T.__dict__.items() if not k.startswith('_')}.get(t, t)
    prev = None; res = []
    for m in states:
        rr, px, ops = render(L, room, i, m)
        img = {(x, y): px[x, y] for x in range(320) for y in range(200)}
        if prev:
            pimg, pops = prev[1], prev[2]
            D = [p for p in img if img[p] != pimg[p]]
            if not D:
                prev = (m, img, ops, rr); continue
            P = Painter(rr)
            pset = list(pops); moving_new = []; static = []
            for k, op in enumerate(ops):
                if op in pset: pset.remove(op); static.append((k, op))
                else: moving_new.append((k, op))
            moving_old = pset
            first = min(k for k, op in moving_new) if moving_new else len(ops)
            Dset = set(D)
            xs = [p[0] for p in D]; ys = [p[1] for p in D]
            bx0, bx1, by0, by1 = min(xs) // 8, max(xs) // 8, min(ys), max(ys)
            cov = {}
            for k, op in moving_new:
                for p, c in P.pixels(op).items():
                    if p in Dset: cov[p] = c
            rest = [img[p] for p in D if p not in cov]
            cols = set(rest)
            under = 'none' if not rest else ('flat %d' % rest[0] if len(cols) == 1 else '%d colours' % len(cols))
            over = []
            for k, op in static:
                if k > first and any(p in Dset for p in P.pixels(op)): over.append(op[:3] if op[0] == 'img' else ('wipe',))
            allopq = all(P.opaque(op) for k, op in moving_new)
            covers = not rest and allopq and not over
            shift = None
            if t in (T.gate, T.level_door_left):
                k = (min(m, 188) // 4 - min(prev[0], 188) // 4) if t == T.gate else m - prev[0]
                bad = [p for p in D if not (0 <= p[1] + k < 200 and img[p] == pimg[(p[0], p[1] + k)])]
                shift = (k, len(bad), sorted({p[1] for p in bad}))
            r = dict(m0=prev[0], m1=m, n=len(D), box=(bx0, bx1, by0, by1), moving=len(moving_new) + len(moving_old),
                     moving_new=[op[:4] for k, op in moving_new], opaque=allopq, under=under, over=over, covers=covers,
                     shift=shift)
            res.append(r)
            if not quiet:
                print('%s l%d r%d p%d  %3d -> %3d  D %5d px, bytes %d-%d rows %d-%d (%d x %d)  moving %d (%s)  under %-10s  over %d %s%s' % (
                    name, lv, room, pos, prev[0], m, len(D), bx0, bx1, by0, by1, bx1 - bx0 + 1, by1 - by0 + 1, r['moving'],
                    'opaque' if allopq else 'masked', under, len(over), ' '.join('%s:%s' % (o[1], o[2]) for o in over if o[0] == 'img'),
                    '  COVERS' if covers else '') + ('  shift %d: %d px not a shift%s' % (shift[0], shift[1],
                    ' (rows %d-%d)' % (shift[2][0], shift[2][-1]) if shift[1] else '') if shift else ''), flush=True)
        prev = (m, img, ops, rr)
    return res

ALL = [   # one tile of each type in the busy rooms (level, room, pos)
    ('chomper', 5, 24, None), ('gate', 5, 24, None), ('level_door_left', 10, 1, None), ('torch', 5, 24, None),
    ('potion', 5, 24, None), ('spike', 7, 19, None), ('loose', 2, 18, None), ('sword', None, None, None)]

def find_tile(t, lv=None, room=None):
    for n in ([lv] if lv else range(1, 15)):
        L = Level(n)
        for r in ([room] if room else range(1, 25)):
            for p in range(30):
                if L.fg[(r - 1) * 30 + p] & 0x1F == t and p % 10 != 9: return n, r, p
    return None

def summary(res):
    """one line per tile: steps, the largest D, the under kinds, the over op ids"""
    unders = {}; overs = set()
    for r in res:
        k = r['under'] if r['under'].startswith('flat') else r['under'].split()[-1] if r['under'] != 'none' else 'none'
        unders[k] = unders.get(k, 0) + 1
        overs |= {o[2] for o in r['over'] if o[0] == 'img'}
    if not res: return 'no visible step'
    big = max(res, key=lambda r: (r['box'][1] - r['box'][0] + 1) * (r['box'][3] - r['box'][2] + 1))
    sh = [r for r in res if r['shift']]
    shs = ('; a pure shift in %d of %d steps' % (sum(1 for r in sh if r['shift'][1] == 0), len(sh))) if sh else ''
    return '%d steps, largest D %d x %d (bytes x rows), moving ops %d-%d (%s), under: %s; over ids %s%s' % (
        len(res), big['box'][1] - big['box'][0] + 1, big['box'][3] - big['box'][2] + 1, min(r['moving'] for r in res),
        max(r['moving'] for r in res), 'all opaque' if all(r['opaque'] for r in res) else 'masked',
        ', '.join('%s x%d' % kv for kv in sorted(unders.items())), sorted(overs) or '-', shs)

def main():
    a = sys.argv[1:]
    if '--all' in a:
        for nm, lv, room, pos in ALL:
            for f in [find_tile(getattr(T, nm), lv, room), find_tile(getattr(T, nm), 1 if (lv or 5) != 1 else 2)]:
                if f: print('%-16s level %2d room %2d pos %2d (%s): %s' % (nm, f[0], f[1], f[2], 'palace' if Level(f[0]).type else
                            'dungeon', summary(analyse(*f, quiet=True))), flush=True)
        return
    lv, room, pos = int(a[0]), int(a[1]), int(a[2])
    st = [int(v, 0) for v in a[a.index('--states') + 1].split(',')] if '--states' in a else None
    analyse(lv, room, pos, st)

if __name__ == '__main__':
    main()
