#!/usr/bin/env python3
"""Prince of Persia data access (SDLPoP data folder) and a Python port of SDLPoP's room
renderer (seg008.c) that produces MZ-800 16-colour index images.

The renderer is the reference for the Z80 room code (M3) and the source of the tile/frame
tables packed for the game. Static rendering only: gates closed, buttons unpressed, no kid.
"""
import os, struct, json
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
import sys; sys.path.insert(0, HERE)
from palette_check import MZ, nearest

DATA = os.path.join(HERE, '..', 'external', 'SDLPoP', 'data')
VGA16 = [(0,0,0),(0,0,170),(0,170,0),(0,170,170),(170,0,0),(170,0,170),(192,152,80),(170,170,170),   # entry 6 is overridden by set_pal(6,0x30,0x26,0x14)
         (85,85,85),(85,85,255),(85,255,85),(85,255,255),(255,85,85),(255,85,255),(255,255,85),(255,255,255)]
VGA16_MZ = [nearest(c) for c in VGA16]
LEVEL_TYPE = [0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 1, 1, 0, 0, 1, 0]      # 0 dungeon, 1 palace (index = level)
GUARD_TYPE = [0, 0, 0, 2, 0, 0, 1, 0, 0, 0, 0, 0, 4, 3, -1, -1]      # GUARD FAT SKEL VIZIER SHADOW
GUARD_SETS = ['GUARD', 'FAT', 'SKEL', 'VIZIER', 'SHADOW']
GUARD_SETS_LEVEL0 = {0: 'GUARD2', 1: 'GUARD1'}   # dungeon / palace guard graphics
TILES = dict(empty=0, floor=1, spike=2, pillar=3, gate=4, stuck=5, closer=6, doortop_with_floor=7,
             bigpillar_bottom=8, bigpillar_top=9, potion=10, loose=11, doortop=12, mirror=13, debris=14,
             opener=15, level_door_left=16, level_door_right=17, chomper=18, torch=19, wall=20, skeleton=21,
             sword=22, balcony_left=23, balcony_right=24, lattice_pillar=25, lattice_down=26,
             lattice_small=27, lattice_left=28, lattice_right=29, torch_with_debris=30)
T = type('T', (), TILES)
# blitters
B_NOTRANSP, B_OR, B_XOR, B_BLACK, B_TRANSP, B_MONO = 0, 2, 3, 9, 0x10, 0x40
# chtabs
CH_SWORD, CH_OBJ, CH_KID, CH_GUARD, CH_ENV, CH_WALL = 0, 1, 2, 5, 6, 7
# tile_table: base_id, floor_left, base_y, right_id, floor_right, right_y, stripe_id, topright_id, bottom_id, fore_id, fore_x, fore_y
TILE_TABLE = [
 (0,0,0,0,0,0,0,0,0,0,0,0), (41,1,0,42,1,2,145,0,43,0,0,0), (127,1,0,133,1,2,145,0,43,0,0,0),
 (92,1,0,93,1,2,0,94,43,95,1,0), (46,1,0,47,1,2,0,48,43,49,3,0), (41,1,1,35,1,3,145,0,36,0,0,0),
 (41,1,0,42,1,2,145,0,96,0,0,0), (46,1,0,0,0,2,0,0,43,49,3,0), (86,1,0,87,1,2,0,0,43,88,1,0),
 (0,0,0,89,0,3,0,90,0,91,1,3), (41,1,0,42,1,2,145,0,43,12,2,-3), (0,1,0,0,0,0,145,0,0,0,0,0),
 (0,0,0,0,0,2,0,0,85,49,3,0), (75,1,0,42,1,2,0,0,43,77,0,0), (97,1,0,98,1,2,145,0,43,100,0,0),
 (147,1,0,42,1,1,145,0,149,0,0,0), (41,1,0,37,0,0,0,38,43,0,0,0), (0,0,0,39,1,2,0,40,43,0,0,0),
 (0,0,0,42,1,2,145,0,43,0,0,0), (41,1,0,42,1,2,0,0,43,0,0,0), (0,0,0,1,1,2,0,2,0,0,0,0),
 (30,1,0,31,1,2,0,0,43,0,0,0), (41,1,0,42,1,2,145,0,43,0,0,0), (41,1,0,10,0,0,0,11,43,0,0,0),
 (0,0,0,12,1,2,0,13,43,0,0,0), (92,1,0,42,1,2,145,0,43,95,1,0), (1,0,0,0,0,0,0,0,2,9,0,-53),
 (3,0,-10,0,0,0,0,0,0,9,0,-53), (4,0,-10,0,0,0,0,0,0,9,0,-53), (5,0,-10,0,0,0,0,0,0,9,0,-53),
 (97,1,0,98,1,2,0,0,43,100,0,0)]
TT_BASE_ID, TT_FLOOR_LEFT, TT_BASE_Y, TT_RIGHT_ID, TT_FLOOR_RIGHT, TT_RIGHT_Y, TT_STRIPE_ID, TT_TOPRIGHT_ID, TT_BOTTOM_ID, TT_FORE_ID, TT_FORE_X, TT_FORE_Y = range(12)
COL_XH = [0, 4, 8, 12, 16, 20, 24, 28, 32, 36]
TBL_LINE = [0, 10, 20]
DOORTOP_FRAM_TOP = [0, 81, 83, 0]; DOOR_FRAM_TOP = [60, 61, 62, 63, 64, 65, 66, 67]
BLUELINE_FRAM1 = [0, 124, 125, 126]; BLUELINE_FRAM_Y = [0, -20, -20, 0]; BLUELINE_FRAM3 = [44, 44, 45, 45]
DOORTOP_FRAM_BOT = [78, 80, 82, 0]
SPIKES_FRAM_RIGHT = [0, 134, 135, 136, 137, 138, 137, 135, 134, 0]; LOOSE_FRAM_RIGHT = [42, 71, 42, 72, 72, 42, 42, 42, 72, 72, 72, 0]
WALL_FRAM_BOTTOM = [7, 9, 5, 3]; LOOSE_FRAM_BOTTOM = [43, 73, 43, 74, 74, 43, 43, 43, 74, 74, 74, 0]
LOOSE_FRAM_LEFT = [41, 69, 41, 70, 70, 41, 41, 41, 70, 70, 70, 0]
SPIKES_FRAM_LEFT = [0, 128, 129, 130, 131, 132, 131, 129, 128, 0]; POTION_FRAM_BUBB = [0, 16, 17, 18, 19, 20, 21, 22]
CHOMPER_FRAM1 = [3, 2, 0, 1, 4, 3, 3, 0]; CHOMPER_FRAM_BOT = [101, 102, 103, 104, 105, 0]
CHOMPER_FRAM_TOP = [0, 0, 111, 112, 113, 0]; CHOMPER_FRAM_Y = [0, 0, 0x25, 0x2F, 0x32]
SPIKES_FRAM_FORE = [0, 139, 140, 141, 142, 143, 142, 140, 139, 0]; CHOMPER_FRAM_FOR = [106, 107, 108, 109, 110, 0]
WALL_FRAM_MAIN = [8, 10, 6, 4]; DOOR_FRAM_SLICE = [67, 59, 58, 57, 56, 55, 54, 53, 52]
# wall decoration resources (chtab 7)
RW_DIVIDER1, RW_RNDBLOCK, RW_MARK_TL, RW_MARK_BL, RW_MARK_TR, RW_MARK_BR = 11, 13, 14, 15, 16, 17

def tile_is_floor(t):
    return t in (1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 13, 14, 15, 16, 17, 18, 19, 20, 22, 23, 24, 25, 30, 21)

class Level:
    def __init__(self, number, data=None):
        self.number = number
        if data is None:
            data = open(os.path.join(DATA, 'LEVELS', 'res%d.bin' % (2000 + number)), 'rb').read()
        assert len(data) == 2305, len(data)
        self.raw = data
        self.fg = bytearray(data[0:720]); self.bg = bytearray(data[720:1440])
        self.doorlinks1 = data[1440:1696]; self.doorlinks2 = data[1696:1952]
        rl = data[1952:2048]
        self.roomlinks = [(rl[i*4], rl[i*4+1], rl[i*4+2], rl[i*4+3]) for i in range(24)]  # left,right,up,down
        self.used_rooms = min(data[2048], 24)
        self.start_room = data[2048 + 24 + 24 + 15 + 1 - 1]  # offset 2111? computed below
        off = 2048 + 1 + 24 + 24 + 15
        self.start_room, self.start_pos, self.start_dir = data[off], data[off+1], data[off+2]
        g = off + 3 + 4
        self.guards_tile = data[g:g+24]; self.guards_dir = data[g+24:g+48]; self.guards_x = data[g+48:g+72]
        self.guards_seq_lo = data[g+72:g+96]; self.guards_skill = data[g+96:g+120]; self.guards_seq_hi = data[g+120:g+144]
        self.guards_color = data[g+144:g+168]
        self.type = LEVEL_TYPE[number]
        self.alter_mods_allrm()
    def links(self, room):   # 1-based room, returns (L,R,U,D)
        return self.roomlinks[room-1] if room else (0, 0, 0, 0)
    def tile(self, room, pos):
        """The tile as drawn (SDLPoP get_tile_to_draw): a button whose door-link timer runs is drawn pressed."""
        t, m = self.fg[(room-1)*30 + pos] & 0x1F, self.bg[(room-1)*30 + pos]
        if t in (T.closer, T.opener):
            dl2 = getattr(self, 'dl2', None)
            timer = (dl2[m] if dl2 is not None else self.raw[1696 + m]) & 0x1F
            if timer > 1:
                if t == T.closer: t = T.stuck
                else: t, m = T.floor, 0
        return t, m
    def alter_mods_allrm(self):
        """seg008 load_alter_mod for every tile (what the game does right after loading a level)."""
        for room in range(1, self.used_rooms + 1):
            L, R, U, D = self.links(room)
            base = (room-1)*30
            for pos in range(30):
                t = self.fg[base+pos] & 0x1F; m = self.bg[base+pos]
                if t == T.gate: self.bg[base+pos] = 188 if m == 1 else 0
                elif t == T.loose: self.bg[base+pos] = 0
                elif t == T.potion: self.bg[base+pos] = (m << 3) & 0xFF
                elif t in (T.torch, T.torch_with_debris): self.bg[base+pos] = 0   # flame animation starts at frame 0
                elif t == T.wall:
                    nm = 0x80 if m == 1 else (m << 4) & 0xFF
                    wl = wr = 1
                    if pos % 10 == 0:
                        if L: wl = (self.fg[(L-1)*30 + pos + 9] & 0x1F) == T.wall
                    else: wl = (self.fg[base+pos-1] & 0x1F) == T.wall
                    if pos % 10 == 9:
                        if R: wr = (self.fg[(R-1)*30 + pos - 9] & 0x1F) == T.wall
                    else: wr = (self.fg[base+pos+1] & 0x1F) == T.wall
                    nm |= 3 if (wl and wr) else (2 if wl else (1 if wr else 0))
                    self.bg[base+pos] = nm

PALETTE_OVERRIDES = {}
_pf = os.path.join(HERE, 'palettes.json')
if os.path.exists(_pf) and not os.environ.get('POP_NO_PALETTE_OVERRIDES'): PALETTE_OVERRIDES = json.load(open(_pf))

class ImageSet:
    """A chtab: images loaded from SDLPoP PNGs, converted to MZ colour indices (-1 = transparent).
    Colours are mapped by RGB (the PNGs of one set do not share one palette order); tools/palettes.json
    overrides are keyed by the set's .pal entry index and translated to RGB here."""
    def __init__(self, setname, first_res, cmap=None, sprite=False):
        self.setname, self.first = setname, first_res
        self.cache = {}; self.sprite = sprite   # sprite: opaque black becomes dark grey (mask = colour != 0)
        self.cmap = dict(cmap or {})            # RGB -> MZ colour
        ov = PALETTE_OVERRIDES.get('%s.%d' % (setname, first_res), {})
        if ov:
            pal = self.pal_rgb()
            for k, v in ov.items(): self.cmap[pal[int(k)]] = int(v)
    def colour(self, rgb):
        if rgb not in self.cmap:
            c = nearest(rgb)
            self.cmap[rgb] = (c or 8) if self.sprite else c
        return self.cmap[rgb]
    def get(self, id1):
        """id1 = 1-based image id as used by seg008 (resource = first + id1)."""
        if id1 in self.cache: return self.cache[id1]
        p = os.path.join(DATA, self.setname, 'res%d.png' % (self.first + id1))
        if not os.path.exists(p): self.cache[id1] = None; return None
        im = Image.open(p); assert im.mode == 'P', p
        pal = im.getpalette(); px = im.load(); w, h = im.size
        lut = [-1] + [self.colour(tuple(pal[i*3:i*3+3])) for i in range(1, 256) if i*3 + 2 < len(pal)]
        rows = [[lut[px[x, y]] for x in range(w)] for y in range(h)]   # index 0 = colour key (transparent)
        self.cache[id1] = (w, h, rows); return self.cache[id1]
    def png_palette(self):
        """The 16-entry palette as the SDLPoP PNGs index it (entry 0 is the colour-key dummy)."""
        for i in range(1, 400):
            p = os.path.join(DATA, self.setname, 'res%d.png' % (self.first + i))
            if os.path.exists(p):
                pp = Image.open(p).getpalette(); return [tuple(pp[k*3:k*3+3]) for k in range(16)]
        return [(0, 0, 0)] * 16
    def pal_rgb(self, res=None):
        b = open(os.path.join(DATA, self.setname, 'res%d.pal' % (res or self.first)), 'rb').read()
        return [(b[4+i*3]*4, b[5+i*3]*4, b[6+i*3]*4) for i in range(16)]
    def mono_colour(self, c):
        """MZ colour for a 'mono' blit colour c: SDLPoP uses the standard 16-colour VGA palette."""
        return VGA16_MZ[c & 15]

EGA_RGB = [(0,0,0),(0,0,170),(0,170,0),(0,170,170),(170,0,0),(170,0,170),(170,85,0),(170,170,170),
           (85,85,85),(85,85,255),(85,255,85),(85,255,255),(255,85,85),(255,85,255),(255,255,85),(255,255,255)]
# EGA colour number -> MZ-800 colour number (EGA bit order IRGB, MZ order IGRB)
EGA2MZ = [0, 1, 4, 5, 2, 3, 6, 7, 8, 9, 12, 13, 10, 11, 14, 15]
# Palace colour treatment (chosen 2026-10-26, see docs/research/palace_variants_*.png):
#  P1: EGA brown -> orange-red 2, light grey -> yellow 6 (brick dither becomes orange/yellow), white -> light grey 7
#  F2 (wall image set): solid light grey not touching brown -> yellow/dark-grey checker; white -> yellow/light-grey checker
#  A5 (environment image 1 = arch lattice, the pier block above a column) -> orange/yellow checker
PALACE_EGA_MAP = list(EGA2MZ); PALACE_EGA_MAP[6] = 2; PALACE_EGA_MAP[7] = 6; PALACE_EGA_MAP[15] = 7
def _chk(a, b): return lambda x, y: a if (x + y) & 1 else b
def palace_wall_post(id1, w, h, rows, eg):
    out = [row[:] for row in rows]
    for y in range(h):
        for x in range(w):
            e = eg[y][x]
            if e == 7:
                adj = any(0 <= x+dx < w and 0 <= y+dy < h and eg[y+dy][x+dx] == 6 for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)))
                if not adj: out[y][x] = _chk(6, 8)(x, y)
            elif e == 15: out[y][x] = _chk(6, 7)(x, y)
    return out
def palace_env_post(id1, w, h, rows, eg):
    if id1 != 1: return rows
    out = [row[:] for row in rows]
    for y in range(2, min(45, h)):
        for x in range(9, min(20, w)):
            if eg[y][x] == 7: out[y][x] = _chk(2, 6)(x, y)
    return out
def kid_post(id1, w, h, rows, eg):
    """The kid's art uses the hair's palette entry (EGA red) for a few shadowed limb pixels (the far hand when he
    starts to run, an arm or leg in some poses): red patches there look wrong on the MZ-800. Red clusters away
    from the hair (the largest red cluster) take the skin colour instead (chosen 2026-10-27 after a playtest)."""
    red = lambda x, y: eg[y][x] in (4, 12)
    seen = set(); comps = []
    for y in range(h):
        for x in range(w):
            if red(x, y) and (x, y) not in seen:
                st = [(x, y)]; seen.add((x, y)); c = []
                while st:
                    a, b = st.pop(); c.append((a, b))
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            q = (a + dx, b + dy)
                            if 0 <= q[0] < w and 0 <= q[1] < h and q not in seen and red(*q): seen.add(q); st.append(q)
                comps.append(c)
    if len(comps) < 2: return rows
    comps.sort(key=len, reverse=True); hair = comps[0]
    out = [row[:] for row in rows]
    for c in comps[1:]:
        if min(max(abs(a - p), abs(b - q)) for a, b in c for p, q in hair) > 3:
            for a, b in c: out[b][a] = EGA2MZ[6]
    return out
DOSDIR = os.path.join(HERE, '..', 'external', 'dos', 'PRINCE')

class DatImageSet(ImageSet):
    """Images straight from a DOS DAT file, coloured as the EGA version shows them: pixel index ->
    EGA colour through the palette resource's 16-nibble table (identity for the E*.DAT art) -> MZ."""
    post = None                                       # optional per-image post-process (id1, w, h, rows, ega_rows) -> rows
    def __init__(self, datname, first_res, sprite=False, pal_res=None, ega_map=None, post=None):
        from datfile import DatFile
        self.setname, self.first, self.sprite = datname, first_res, sprite
        self.ega_map = ega_map or EGA2MZ              # EGA colour -> MZ colour, overridable per set
        self.post = post
        self.dat = DatFile(os.path.join(DOSDIR, datname + '.DAT'))
        self.cache = {}; self.cmap = {}
        pr = pal_res or first_res
        if pr in self.dat.table:
            r = self.dat.resource(pr); e = r[68:76]
            self.ega_tab = [v for b in e for v in (b >> 4, b & 15)]
        else:
            self.ega_tab = list(range(16))
        # EGA art value 13 is displayed as black by the game (verified against DOSBox: opaque black)
        self.lut = [-1] + [self.ega_map[0 if self.ega_tab[i] == 13 else self.ega_tab[i]] for i in range(1, 16)]
        if sprite: self.lut = [-1] + [(c or 8) for c in self.lut[1:]]
    def get(self, id1):
        if id1 in self.cache: return self.cache[id1]
        rid = self.first + id1
        if rid not in self.dat.table or len(self.dat.resource(rid)) <= 2:
            rid = 1000 + self.first + id1      # "optional graphics": EGA/CGA variants live at 1200+ (load_more_opt_graf)
            if rid not in self.dat.table or len(self.dat.resource(rid)) <= 2: self.cache[id1] = None; return None
        img = self.dat.image(rid)
        if img is None or img[0] > 320 or img[1] > 200: self.cache[id1] = None; return None   # not an image (palette etc.)
        w, h, rows, depth = img
        if depth == 1: out = [[(-1 if v == 0 else 15) for v in row] for row in rows]   # mono masks
        else: out = [[self.lut[v] for v in row] for row in rows]
        if self.post is not None and depth != 1:
            eg = [[(0 if v == 0 else self.ega_tab[v]) for v in row] for row in rows]
            out = self.post(id1, w, h, out, eg)
        self.cache[id1] = (w, h, out); return self.cache[id1]
    def pal_rgb(self, res=None):
        return [EGA_RGB[self.ega_tab[i]] for i in range(16)]
    def mono_colour(self, c): return self.ega_map[c & 15]

class Prng:
    def __init__(self): self.seed = 0
    def rand(self, mx):
        self.seed = (self.seed * 214013 + 2531011) & 0xFFFFFFFF
        return (self.seed >> 16) % (mx + 1)

class RoomRenderer:
    """Port of SDLPoP draw_room(): collects back/mid/fore/wipe operations, then paints them."""
    def __init__(self, level, ega=False):
        self.level = level; self.ltype = level.type; self.ega = ega
        if ega:
            env = 'EPALACE' if self.ltype else 'EDUNGEON'
            emap = PALACE_EGA_MAP if self.ltype else None
            self.env = DatImageSet(env, 200, ega_map=emap, post=palace_env_post if self.ltype else None)
            self.wall = DatImageSet(env, 360, ega_map=emap, post=palace_wall_post if self.ltype else None)
            self.obj = DatImageSet('PRINCE', 150)
        else:
            env = 'VPALACE' if self.ltype else 'VDUNGEON'
            self.env = ImageSet(env, 200); self.wall = ImageSet(env, 360); self.obj = ImageSet('PRINCE', 150)
        self.sets = {CH_ENV: self.env, CH_WALL: self.wall, CH_OBJ: self.obj}
        self.prng = Prng()
        # palace wall colours: VGA indices 0x61-0x64 / 0x66-0x69 = wall palette entries 1-4 / 6-9
        wp = self.wall.pal_rgb(360)
        self.wallcol = {0x60 + i: self.wall.colour(wp[i]) for i in range(16)}
    # --- tile access (get_tile_to_draw) ---
    def get_tile(self, room, col, row, default):
        if col == -1: return self.leftroom[row]
        if room: return self.level.tile(room, TBL_LINE[row] + col)
        return (default, 0)
    def load_room_links(self, room):
        lv = self.level
        L, R, A, Bm = lv.links(room)
        self.room_L, self.room_R, self.room_A, self.room_B = L, R, A, Bm
        self.room_AL = self.room_AR = self.room_BL = self.room_BR = 0
        if room:
            if A: self.room_AL, self.room_AR = lv.links(A)[0], lv.links(A)[1]
            else:
                if L: self.room_AL = lv.links(L)[2]
                if R: self.room_AR = lv.links(R)[2]
            if Bm: self.room_BL, self.room_BR = lv.links(Bm)[0], lv.links(Bm)[1]
            else:
                if L: self.room_BL = lv.links(L)[3]
                if R: self.room_BR = lv.links(R)[3]
    def load_leftroom(self):
        self.leftroom = [self.get_tile(self.room_L, 9, r, T.wall) for r in range(3)]
    def load_rowbelow(self):
        if self.drawn_row == 2: room, room_left, rb = self.room_B, self.room_BL, 0
        else: room, room_left, rb = self.drawn_room, self.room_L, self.drawn_row + 1
        self.row_below_left = [None]*10
        for c in range(1, 10): self.row_below_left[c] = self.get_tile(room, c-1, rb, T.empty)
        self.row_below_left[0] = self.get_tile(room_left, 9, rb, T.wall)
    def load_curr_and_left(self):
        default = T.floor if self.drawn_row == 2 else T.wall
        self.curr_tile, self.curr_mod = self.get_tile(self.drawn_room, self.drawn_col, self.drawn_row, default)
        self.tile_left, self.mod_left = self.get_tile(self.drawn_room, self.drawn_col - 1, self.drawn_row, default)
        self.draw_xh = COL_XH[self.drawn_col]
    # --- op lists ---
    def add(self, table, ch, id1, xh, xl, ybottom, blit):
        if id1 == 0: return 0
        img = self.sets[ch].get(id1)
        if img is None: return 0
        w, h, rows = img
        self.ops[table].append((ch, id1, xh*8 + xl, ybottom - h + 1, blit))
        return 1
    def add_back(self, *a): return self.add('back', *a)
    def add_fore(self, *a): return self.add('fore', *a)
    def add_mid(self, *a): return self.add('mid', *a)
    def add_wipe(self, layer, left, bottom, height, width, color):
        self.ops['wipe%d' % layer].append((left, bottom + 1 - height, width, height, color))
    # --- draw_tile parts ---
    def can_see_bottomleft(self):
        return self.curr_tile in (T.empty, T.bigpillar_top, T.doortop, T.lattice_down)
    def draw_tile_floorright(self):
        if not self.can_see_bottomleft(): return
        self.draw_tile_topright()
        if TILE_TABLE[self.tile_left][TT_FLOOR_RIGHT] == 0: return
        self.add_back(CH_ENV, 42, self.draw_xh, 0, TILE_TABLE[T.floor][TT_RIGHT_Y] + self.draw_main_y, B_BLACK)
    def draw_tile_topright(self):
        tt, tm = self.row_below_left[self.drawn_col]
        if tt in (T.doortop_with_floor, T.doortop):
            if self.ltype == 0: return
            self.add_back(CH_ENV, DOORTOP_FRAM_TOP[tm], self.draw_xh, 0, self.draw_bottom_y, B_OR)
        elif tt == T.wall:
            self.add_back(CH_WALL, 2, self.draw_xh, 0, self.draw_bottom_y, B_OR)
        else:
            self.add_back(CH_ENV, TILE_TABLE[tt][TT_TOPRIGHT_ID], self.draw_xh, 0, self.draw_bottom_y, B_OR)
    def draw_tile_anim_topright(self):
        if self.curr_tile in (T.empty, T.bigpillar_top, T.doortop) and self.row_below_left[self.drawn_col][0] == T.gate:
            self.add_back(CH_ENV, 68, self.draw_xh, 0, self.draw_bottom_y, B_MONO)
            m = min(self.row_below_left[self.drawn_col][1], 188)
            self.add_back(CH_ENV, DOOR_FRAM_TOP[(m >> 2) % 8], self.draw_xh, 0, self.draw_bottom_y, B_OR)
    def draw_tile_right(self):
        if self.curr_tile == T.wall: return
        tl, ml = self.tile_left, self.mod_left
        if tl == T.empty:
            if ml > 3: return
            self.add_back(CH_ENV, BLUELINE_FRAM1[ml], self.draw_xh, 0, BLUELINE_FRAM_Y[ml] + self.draw_main_y, B_OR)
        elif tl == T.floor:
            self.add_back(CH_ENV, 42, self.draw_xh, 0, TILE_TABLE[tl][TT_RIGHT_Y] + self.draw_main_y, B_TRANSP)
            num = ml if ml <= 3 else 0
            if num == (1 if self.ltype else 0): return
            self.add_back(CH_ENV, BLUELINE_FRAM3[num], self.draw_xh, 0, self.draw_main_y - 20, B_NOTRANSP)
        elif tl in (T.doortop_with_floor, T.doortop):
            if self.ltype == 0: return
            self.add_back(CH_ENV, DOORTOP_FRAM_BOT[ml], self.draw_xh, 0, TILE_TABLE[tl][TT_RIGHT_Y] + self.draw_main_y, B_OR)
        elif tl == T.wall:
            if self.ltype and (ml & 0x80) == 0:
                self.add_back(CH_ENV, 84, self.draw_xh + 3, 0, self.draw_main_y - 27, B_NOTRANSP)
            self.add_back(CH_WALL, 1, self.draw_xh, 0, TILE_TABLE[tl][TT_RIGHT_Y] + self.draw_main_y, B_OR)
        else:
            id1 = TILE_TABLE[tl][TT_RIGHT_ID]
            if id1:
                if tl == T.stuck:
                    blit = B_TRANSP
                    if self.curr_tile in (T.empty, T.stuck) or not tile_is_floor(self.curr_tile): id1 = 42
                else: blit = B_OR
                self.add_back(CH_ENV, id1, self.draw_xh, 0, TILE_TABLE[tl][TT_RIGHT_Y] + self.draw_main_y, blit)
            if self.ltype:
                self.add_back(CH_ENV, TILE_TABLE[tl][TT_STRIPE_ID], self.draw_xh, 0, self.draw_main_y - 27, B_OR)
            if tl in (T.torch, T.torch_with_debris):
                self.add_back(CH_ENV, 146, self.draw_xh, 0, self.draw_bottom_y - 28, B_NOTRANSP)
    def spike_frame(self, m): return 5 if m & 0x80 else m
    def loose_frame(self, m):
        if m & 0x80:
            m &= 0x7F
            if m > 10: return 1
        return m
    def draw_tile_anim_right(self):
        tl, ml = self.tile_left, self.mod_left
        if tl == T.spike:
            self.add_back(CH_ENV, SPIKES_FRAM_RIGHT[self.spike_frame(ml)], self.draw_xh, 0, self.draw_main_y - 7, B_TRANSP)
        elif tl == T.gate: self.draw_gate_back()
        elif tl == T.loose:
            self.add_back(CH_ENV, LOOSE_FRAM_RIGHT[self.loose_frame(ml)], self.draw_xh, 0, self.draw_bottom_y - 1, B_OR)
        elif tl == T.level_door_left: self.draw_leveldoor()
        elif tl in (T.torch, T.torch_with_debris):
            if ml < 9: self.add_back(CH_OBJ, ml + 1, self.draw_xh + 1, 0, self.draw_main_y - 40, B_NOTRANSP)
    def draw_tile_bottom(self, arg):
        id1 = 0; blit = B_NOTRANSP; ch = CH_ENV
        if self.curr_tile == T.wall:
            if self.ltype == 0 or self.ega: id1 = WALL_FRAM_BOTTOM[self.curr_mod & 0x7F]
            ch = CH_WALL
        else:
            if self.curr_tile == T.doortop: blit = B_OR
            id1 = TILE_TABLE[self.curr_tile][TT_BOTTOM_ID]
        if self.add(self.ptr_table, ch, id1, self.draw_xh, 0, self.draw_bottom_y, blit) and arg:
            self.add_fore(ch, id1, self.draw_xh, 0, self.draw_bottom_y, blit)
        if ch == CH_WALL: self.wall_pattern(0, 'back')
    def draw_loose(self, arg):
        if self.curr_tile == T.loose:
            id1 = LOOSE_FRAM_BOTTOM[self.loose_frame(self.curr_mod)]
            self.add_back(CH_ENV, id1, self.draw_xh, 0, self.draw_bottom_y, B_NOTRANSP)
            self.add_fore(CH_ENV, id1, self.draw_xh, 0, self.draw_bottom_y, B_NOTRANSP)
    def draw_tile_base(self):
        yb = self.draw_main_y
        if self.tile_left == T.lattice_down and self.curr_tile == T.doortop: id1 = 6; yb += 3
        elif self.curr_tile == T.loose: id1 = LOOSE_FRAM_LEFT[self.loose_frame(self.curr_mod)]
        elif self.curr_tile == T.opener and self.tile_left == T.empty and self.ltype == 0: id1 = 148
        else: id1 = TILE_TABLE[self.curr_tile][TT_BASE_ID]
        self.add(self.ptr_table, CH_ENV, id1, self.draw_xh, 0, TILE_TABLE[self.curr_tile][TT_BASE_Y] + yb, B_TRANSP)
    def draw_tile_anim(self):
        ct, cm = self.curr_tile, self.curr_mod
        if ct == T.spike:
            self.add(self.ptr_table, CH_ENV, SPIKES_FRAM_LEFT[self.spike_frame(cm)], self.draw_xh, 0, self.draw_main_y - 2, B_TRANSP)
        elif ct == T.potion:
            pt = (cm & 0xF8) >> 3; color = 12; pot = 0
            if pt == 0: return
            if pt in (5, 6): color = 9
            if pt in (3, 4): color = 10; pot = 1
            if pt == 2: pot = 1
            self.add_back(CH_OBJ, 23, self.draw_xh + 3, 1, self.draw_main_y - (pot << 2) - 14, B_MONO)
            self.add_fore(CH_OBJ, POTION_FRAM_BUBB[cm & 7], self.draw_xh + 3, 1, self.draw_main_y - (pot << 2) - 14, B_MONO + color)
        elif ct == T.sword:
            self.add_mid(CH_OBJ, (1 if cm == 1 else 0) + 10, self.draw_xh, 0, self.draw_main_y - 3, B_TRANSP)
        elif ct == T.chomper:
            n = CHOMPER_FRAM1[min(cm & 0x7F, 6)]
            self.add_back(CH_ENV, CHOMPER_FRAM_BOT[n], self.draw_xh, 0, self.draw_main_y, B_TRANSP)
            if cm & 0x80: self.add_back(CH_ENV, n + 114, self.draw_xh + 1, 4, self.draw_main_y - 6, B_MONO + 12)
            self.add_back(CH_ENV, CHOMPER_FRAM_TOP[n], self.draw_xh, 0, self.draw_main_y - CHOMPER_FRAM_Y[n], B_TRANSP)
    def draw_tile_fore(self):
        ct, cm = self.curr_tile, self.curr_mod
        if ct == T.spike:
            self.add_fore(CH_ENV, SPIKES_FRAM_FORE[self.spike_frame(cm)], self.draw_xh, 0, self.draw_main_y - 2, B_TRANSP)
        elif ct == T.chomper:
            n = CHOMPER_FRAM1[min(cm & 0x7F, 6)]
            self.add_fore(CH_ENV, CHOMPER_FRAM_FOR[n], self.draw_xh, 0, self.draw_main_y, B_TRANSP)
            if cm & 0x80: self.add_fore(CH_ENV, n + 119, self.draw_xh + 1, 4, self.draw_main_y - 6, B_MONO + 12)
        elif ct == T.wall:
            if self.ltype == 0 or self.ega: self.add_fore(CH_WALL, WALL_FRAM_MAIN[cm & 0x7F], self.draw_xh, 0, self.draw_main_y, B_NOTRANSP)
            self.wall_pattern(1, 'fore')
        else:
            id1 = TILE_TABLE[ct][TT_FORE_ID]
            if id1 == 0: return
            if ct == T.potion:
                pt = (cm & 0xF8) >> 3
                if 2 <= pt < 5: id1 = 13
            xh = TILE_TABLE[ct][TT_FORE_X] + self.draw_xh; yb = TILE_TABLE[ct][TT_FORE_Y] + self.draw_main_y
            if ct == T.potion:
                if self.ltype: id1 += 2
                self.add_fore(CH_OBJ, id1, xh, 6, yb, B_TRANSP)
            elif (ct == T.pillar and self.ltype == 0) or (T.lattice_small <= ct < T.torch_with_debris):
                self.add_fore(CH_ENV, id1, xh, 0, yb, B_NOTRANSP)
            else:
                self.add_fore(CH_ENV, id1, xh, 0, yb, B_TRANSP)
    def draw_gate_back(self):
        gate_top_y = self.draw_bottom_y - 62
        openness = (min(self.mod_left, 188) >> 2) + 1
        gate_bottom_y = self.draw_main_y - openness
        if gate_bottom_y + 12 < self.draw_main_y:
            self.add_back(CH_ENV, 50, self.draw_xh, 0, gate_bottom_y, B_NOTRANSP)
        else:
            self.add_back(CH_ENV, TILE_TABLE[T.gate][TT_RIGHT_ID], self.draw_xh, 0, TILE_TABLE[T.gate][TT_RIGHT_Y] + self.draw_main_y, B_NOTRANSP)
            if self.can_see_bottomleft(): self.draw_tile_topright()
            self.draw_tile_bottom(0); self.draw_loose(0); self.draw_tile_base()
            self.add_back(CH_ENV, 51, self.draw_xh, 0, gate_bottom_y - 2, B_TRANSP)
        yb = gate_bottom_y - 12
        if yb < 192:
            while yb >= 0 and yb > 7 and yb - 7 > gate_top_y:
                self.add_back(CH_ENV, 52, self.draw_xh, 0, yb, B_NOTRANSP); yb -= 8
        frame = yb - gate_top_y + 1
        if 0 < frame < 9: self.add_back(CH_ENV, DOOR_FRAM_SLICE[frame], self.draw_xh, 0, yb, B_NOTRANSP)
    def draw_leveldoor(self):
        yb = self.draw_main_y - 13
        self.add_back(CH_ENV, 99, self.draw_xh + 1, 0, yb, B_NOTRANSP)
        ml = self.mod_left
        if ml:
            if self.level.start_room != self.drawn_room:
                self.add_back(CH_ENV, 144, self.draw_xh + 1, 0, yb - 4, B_NOTRANSP)
            else:
                width = 39 if self.ltype == 0 else 48; xlow = 2 if self.ltype == 0 else 0
                self.add_wipe(0, 8*(self.draw_xh + 1) + xlow, yb - 4, 45, width, 0)
        ld_yb = yb - (ml & 3) - 48; y = yb - ml
        while True:
            self.add_back(CH_ENV, 33, self.draw_xh + 1, 0, ld_yb, B_NOTRANSP)
            if y > ld_yb: ld_yb += 4
            else: break
        self.add_back(CH_ENV, 34, self.draw_xh + 1, 0, self.draw_main_y - 64, B_NOTRANSP)
    def wall_pattern(self, part, table):
        saved = self.prng.seed
        self.prng.seed = self.drawn_room + TBL_LINE[self.drawn_row] + self.drawn_col
        self.prng.rand(1)
        xh, dmy, dby = self.draw_xh, self.draw_main_y, self.draw_bottom_y
        addt = self.add_back if table == 'back' else self.add_fore
        layer = 0 if table == 'back' else 1
        is_dungeon = (self.ltype == 0)
        if self.ltype and not self.ega:   # palace, VGA only
            pwc = self.palace_wall_colors; r, c = self.drawn_row, self.drawn_col
            if part:
                self.add_wipe(layer, 8*xh, dmy - 40, 20, 32, pwc[44*r + c])
                self.add_wipe(layer, 8*xh, dmy - 19, 21, 16, pwc[44*r + 11 + c])
                self.add_wipe(layer, 8*(xh+2), dmy - 19, 21, 16, pwc[44*r + 12 + c])
                self.add_wipe(layer, 8*xh, dmy, 19, 8, pwc[44*r + 22 + c])
                self.add_wipe(layer, 8*(xh+1), dmy, 19, 24, pwc[44*r + 23 + c])
                addt(CH_WALL, self.prng.rand(2) + 3, xh + 3, 0, dmy - 53, B_MONO + 6)
                addt(CH_WALL, self.prng.rand(2) + 6, xh, 0, dmy - 34, B_MONO + 6)
                addt(CH_WALL, self.prng.rand(2) + 9, xh, 0, dmy - 13, B_MONO + 6)
                addt(CH_WALL, self.prng.rand(2) + 12, xh, 0, dmy, B_MONO + 6)
            self.add_wipe(layer, 8*xh, dby, 3, 32, pwc[44*r + 33 + c])
            addt(CH_WALL, self.prng.rand(2) + 15, xh, 0, dby, B_MONO + 6)
        else:
            md = self.prng.rand(1); mdo = self.prng.rand(4); bd = self.prng.rand(1); bdo = self.prng.rand(4)
            bm = self.curr_mod & 0x7F
            def left_mark(v, a2, a1):
                LPOS = [58, 41, 37, 20, 16]; img = RW_MARK_BL if v % 2 else RW_MARK_TL
                lv2 = (a1 + 6) if v > 3 else ((a2 + 6) if v > 1 else 0)
                addt(CH_WALL, img, xh + (1 if v in (2, 3) else 0), lv2, dby - LPOS[v], B_TRANSP)
            def right_mark(v, a1):
                RPOS = [52, 42, 31, 21]; img = RW_MARK_BR if v % 2 else RW_MARK_TR
                a1 = 24 if v < 2 else a1 - 3
                addt(CH_WALL, img, xh + (1 if v > 1 else 0), a1, dby - RPOS[v], B_TRANSP)
            if bm == 3:      # WWW
                if part:
                    if self.prng.rand(4) == 0: addt(CH_WALL, RW_RNDBLOCK, xh, 0, dby - 42, B_NOTRANSP)
                    addt(CH_WALL, RW_DIVIDER1 + md, xh + 1, mdo, dby - 21, B_TRANSP)
                addt(CH_WALL, RW_DIVIDER1 + bd, xh, bdo, dby, B_TRANSP)
                if part and is_dungeon:
                    if self.prng.rand(4) == 0: right_mark(self.prng.rand(3), mdo)
                    if self.prng.rand(4) == 0: left_mark(self.prng.rand(4), mdo - md, bdo - bd)
            elif bm == 0:    # SWS
                if is_dungeon and part and self.prng.rand(6) == 0: left_mark(self.prng.rand(1), mdo - md, bdo - bd)
            elif bm == 1:    # SWW
                if part:
                    if self.prng.rand(4) == 0: addt(CH_WALL, RW_RNDBLOCK, xh, 0, dby - 42, B_NOTRANSP)
                    addt(CH_WALL, RW_DIVIDER1 + md, xh + 1, mdo, dby - 21, B_TRANSP)
                    if is_dungeon:
                        if self.prng.rand(4) == 0: right_mark(self.prng.rand(3), mdo)
                        if self.prng.rand(4) == 0: left_mark(self.prng.rand(3), mdo - md, bdo - bd)
            elif bm == 2:    # WWS
                if part: addt(CH_WALL, RW_DIVIDER1 + md, xh + 1, mdo, dby - 21, B_TRANSP)
                addt(CH_WALL, RW_DIVIDER1 + bd, xh, bdo, dby, B_TRANSP)
                if part and is_dungeon:
                    if self.prng.rand(4) == 0: right_mark(self.prng.rand(1) + 2, mdo)
                    if self.prng.rand(4) == 0: left_mark(self.prng.rand(4), mdo - md, bdo - bd)
        self.prng.seed = saved
    def gen_palace_wall_colors(self):
        saved = self.prng.seed; self.prng.seed = self.drawn_room; self.prng.rand(1)
        pwc = [0]*(44*3)
        for row in range(3):
            for sub in range(4):
                base = 0x61 if sub % 2 else 0x66
                prev = -1
                for col in range(11):
                    while True:
                        c = base + self.prng.rand(3)
                        if c != prev: break
                    pwc[44*row + 11*sub + col] = c; prev = c
        self.prng.seed = saved; self.palace_wall_colors = pwc
    def draw_tile(self):
        self.draw_tile_floorright(); self.draw_tile_anim_topright(); self.draw_tile_right(); self.draw_tile_anim_right()
        self.draw_tile_bottom(0); self.draw_loose(0); self.draw_tile_base(); self.draw_tile_anim(); self.draw_tile_fore()
    def draw_tile_aboveroom(self):
        self.draw_tile_floorright(); self.draw_tile_anim_topright(); self.draw_tile_right()
        self.draw_tile_bottom(0); self.draw_loose(0); self.draw_tile_fore()
    # --- overlays over a hanging/climbing/falling kid (SDLPoP draw_other_overlay, draw_floor_overlay, redraw_needed_above)
    FLOOR_LEFT_OVERLAY = (32, 151, 151, 150, 150, 151, 32, 32)
    def overlay(self, room, tilepos, kind, kid_frame):
        """Ops one overlay tile adds over the kid: (ops in drawing order, objects_left) where objects_left means
        SDLPoP redraws the objects of tilepos - 1 right after (draw_other_overlay's second case). The ops are
        mid-table ops; for the row above the room the bottom piece's fore copy."""
        saved = self.ops, self.ptr_table, self.drawn_room
        self.ops = {'back': [], 'mid': [], 'fore': [], 'wipe0': [], 'wipe1': []}
        self.drawn_room = room; self.load_room_links(room); self.load_leftroom()
        left_objs = False
        if tilepos < 0:
            self.drawn_room = self.room_A; self.load_room_links(self.room_A); self.load_leftroom()
            self.drawn_row = 2; self.load_rowbelow(); self.drawn_col = -tilepos - 1
            self.load_curr_and_left(); self.draw_main_y = -1; self.draw_bottom_y = 2
            self.ptr_table = 'back'; self.draw_tile_bottom(1)
            out = self.ops['fore']
        else:
            self.drawn_row, self.drawn_col = divmod(tilepos, 10)
            self.load_rowbelow(); self.draw_bottom_y = 63 * self.drawn_row + 65; self.draw_main_y = self.draw_bottom_y - 3
            self.load_curr_and_left()
            self.ptr_table = 'mid'
            def other():
                if self.tile_left == T.empty: self.draw_tile2(); return False
                if (self.curr_tile != T.empty and self.drawn_col > 0 and
                        self.get_tile(self.drawn_room, self.drawn_col - 2, self.drawn_row, T.empty)[0] == T.empty):
                    self.draw_tile2(); return True
                return False
            if kind == 'floor':
                if self.tile_left == T.empty:
                    if self.curr_tile in (T.floor, T.pillar, T.stuck, T.torch):
                        if 137 <= kid_frame <= 144:
                            self.add_mid(CH_ENV, self.FLOOR_LEFT_OVERLAY[kid_frame - 137], self.draw_xh, 0,
                                         (1 if self.curr_tile == T.stuck else 0) + self.draw_main_y, B_TRANSP)
                        self.draw_tile_bottom(0)
                    else: left_objs = other()
            else: left_objs = other()
            out = self.ops['mid']
        self.ops, self.ptr_table, self.drawn_room = saved
        self.load_room_links(self.drawn_room)
        return out, left_objs
    def draw_tile2(self):
        self.draw_tile_right(); self.draw_tile_anim_right(); self.draw_tile_base(); self.draw_tile_anim()
        self.draw_tile_bottom(0); self.draw_loose(0)
    # --- room ---
    def draw_room(self, room):
        self.ops = {'back': [], 'mid': [], 'fore': [], 'wipe0': [], 'wipe1': []}
        self.ptr_table = 'back'
        self.drawn_room = room; self.load_room_links(room)
        if self.ltype: self.gen_palace_wall_colors()
        self.load_leftroom()
        for self.drawn_row in (2, 1, 0):
            self.load_rowbelow()
            self.draw_bottom_y = 63 * self.drawn_row + 65; self.draw_main_y = self.draw_bottom_y - 3
            for self.drawn_col in range(10):
                self.load_curr_and_left(); self.draw_tile()
        saved = room
        self.drawn_room = self.room_A; self.load_room_links(self.room_A); self.load_leftroom()
        self.drawn_row = 2; self.load_rowbelow()
        for self.drawn_col in range(10):
            self.load_curr_and_left(); self.draw_main_y = -1; self.draw_bottom_y = 2; self.draw_tile_aboveroom()
        self.drawn_room = saved; self.load_room_links(saved)
        return self.paint()
    def paint(self):
        scr = [[0]*320 for _ in range(200)]
        def blit_img(ch, id1, x0, y0, blit):
            w, h, rows = self.sets[ch].get(id1)
            mono = self.sets[ch].mono_colour(blit & 0x0F) if blit >= B_MONO else 0
            for y in range(h):
                sy = y0 + y
                if not 0 <= sy < 200: continue
                srow = rows[y]; drow = scr[sy]
                for x in range(w):
                    sx = x0 + x
                    if not 0 <= sx < 320: continue
                    c = srow[x]
                    if blit == B_NOTRANSP: drow[sx] = max(c, 0)
                    elif blit in (B_OR, B_TRANSP):
                        if c >= 0: drow[sx] = c
                    elif blit == B_BLACK:
                        if c >= 0: drow[sx] = 0
                    elif blit >= B_MONO:
                        if c >= 0: drow[sx] = mono
        def wipe(op):
            left, top, width, height, color = op
            col = self.wallcol.get(color, color) if color >= 0x60 else color
            for y in range(top, top + height):
                if not 0 <= y < 200: continue
                for x in range(left, left + width):
                    if 0 <= x < 320: scr[y][x] = col
        for op in self.ops['wipe0']: wipe(op)
        for op in self.ops['back']: blit_img(*op)
        for op in self.ops['mid']: blit_img(*op)
        for op in self.ops['wipe1']: wipe(op)
        for op in self.ops['fore']: blit_img(*op)
        im = Image.new('P', (320, 200)); px = im.load()
        for y in range(200):
            for x in range(320): px[x, y] = scr[y][x]
        pal = []
        for c in MZ: pal += list(c)
        im.putpalette(pal + [0]*(768-48))
        return im

def room_oplist(rr, variants):
    """Canonical operation list of the last draw_room() call, as the Z80 renderer builds it:
    (table 0 back/1 mid/2 fore, chtab, image id (shift variant resolved), xbyte, ytop, blit, mono colour).
    `variants` maps (chtab, id, shift) -> variant id."""
    out = []
    for ti, tbl in enumerate(('back', 'mid', 'fore')):
        for (ch, id1, x, y, blit) in rr.ops[tbl]:
            sft = x & 7; vid = id1
            if sft: vid = variants[(ch, id1, sft)]
            mono = rr.sets[ch].mono_colour(blit & 15) if blit >= B_MONO else 0   # MZ colour, as the Z80 stores it
            code = {B_NOTRANSP: 0, B_OR: 1, B_TRANSP: 1, B_BLACK: 2}.get(blit, 3)
            out.append((ti, ch, vid, x >> 3, y, code, mono))
    return out

if __name__ == '__main__':
    import sys
    lvl = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    out = sys.argv[2] if len(sys.argv) > 2 else 'build/level%d_rooms.png' % lvl
    level = Level(lvl); rr = RoomRenderer(level)
    cols = 6; rows = (level.used_rooms + cols - 1) // cols
    sheet = Image.new('RGB', (cols * 322, rows * 202), (40, 40, 40))
    for r in range(1, level.used_rooms + 1):
        im = rr.draw_room(r).convert('RGB')
        sheet.paste(im, (((r-1) % cols) * 322, ((r-1) // cols) * 202))
    sheet.save(out); print('wrote', out, 'rooms', level.used_rooms, 'type', 'palace' if level.type else 'dungeon')
