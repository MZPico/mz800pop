#!/usr/bin/env python3
"""M4: the playable program (build/m4game.mzf) against the references. For each control script the Z80 runs
the game tick by tick; after every tick the kid's state must equal tools/kidsim.py's, and every few ticks the
VRAM must equal the Python room render with the kid composited the way the Z80 places him. Records
build/m4_<script>.gif of the run. With --gui the emulator window is opened instead and left running on the
joystick / cursor keys (joystick 1 = NUM_KEYPAD).
A script with a '# draw after death' line is followed after the kid's death until it ends (the others stop 8 ticks
after it, as the logic tests do). Every tick also checks the flash the Z80 showed (FL_SHOWN) against SDLPoP's
flash_if_hurt.
usage: m4_game.py [--gui] [--level N] [--every N] [script.txt ...]"""
import base64, os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools')); sys.path.insert(0, os.path.join(ROOT, 'tests'))
from m3_test import syms, load_assets, LEVEL_ADDR, RV, rebase_dir, write_pack
from m4_test import z80_state, KV, norm, guard_opts_bytes, ev_opts_bytes, encode
from emu import Emu
from popdata import Level, RoomRenderer, B_TRANSP, B_NOTRANSP, B_OR, B_BLACK, B_MONO, MZ, EGA2MZ, T
import build_assets as BA
import kidsim
A = os.path.join(ROOT, 'build', 'assets')
LEVEL_TYPE = RV + 20
SCRIPT = 0xF000; SCRIPT_PTR = 0x0876; TICKS = 0x0872; SPR = 0x0b20   # SCRIPT: RAM-disk page 5 (game.asm RD_SCRIPT)
KID_PAGE = 2
LEVEL_ADDR = 0xEC00
# guard sets in the RAM disk (page, address): whole sets in the gaps, no image across a page; until the M5 loader
# loads only the level's set, all six are resident
GUARD_SETS = (('guard', 6, 0x3000), ('fat', 7, 0x0000), ('skel', 7, 0x4C40), ('vizier', 7, 0x8D80), ('shadow', 0, 0xA800),
              ('guard_palace', 6, 0x8000))

class KidPack:
    """Decodes build/assets/<name>.pack images the way the Z80 sprite kernel sees them (mask = drawn pixels)."""
    def __init__(self, name='kid'):
        self.pack = open(os.path.join(A, name + '.pack'), 'rb').read(); self.dir = open(os.path.join(A, name + '.dir'), 'rb').read()
        import json
        self.info = json.load(open(os.path.join(A, name + '.json')))['images']
        self.cache = {}
    def get(self, pid, mirror=False):
        key = (pid, mirror)
        if pid == 0: return None
        if key in self.cache: return self.cache[key]
        d = self.dir[pid * 8:pid * 8 + 8]; off = (d[0] << 16) | (d[1] << 8) | d[2]; wb, h, flags = d[3], d[4], d[5]
        n = wb * h
        if flags & 1:   # mask plane first
            mask = self.pack[off:off + n]; planes = [self.pack[off + n * (p + 1):off + n * (p + 2)] for p in range(4)]
        else:           # sprite sets: planes only, drawn where any plane bit is set (black pixels were remapped to 8)
            planes = [self.pack[off + n * p:off + n * (p + 1)] for p in range(4)]
            mask = bytes(planes[0][i] | planes[1][i] | planes[2][i] | planes[3][i] for i in range(n))
        rows = []
        for y in range(h):
            row = []
            for x in range(wb * 8):
                o = y * wb + (x >> 3); bit = 1 << (x & 7)
                if mask[o] & bit: row.append(sum(1 << p for p in range(4) if planes[p][o] & bit))
                else: row.append(-1)
            rows.append(row)
        w = self.info[str(pid)]['w']
        if mirror: rows = [list(reversed(r[:w])) for r in rows]
        else: rows = [r[:w] for r in rows]
        self.cache[key] = (w, h, rows)
        return self.cache[key]

class KidSet:
    """ImageSet stand-in for the compositor: id = (pack id, mirror) tuple, or 'extra' (a clipped image)."""
    def __init__(self, kp): self.kp = kp; self.extra = None
    def get(self, key): return self.extra if key == 'extra' else self.kp.get(*key)
    def mono_colour(self, c): return 0

def kid_sprite(sim, frames):
    """Where the Z80 puts the kid: (pack id, mirror, x, ytop) or None, from the simulator's state."""
    K = sim.Kid; sim.Char = K.copy(); sim.load_frame_to_obj()
    img = sim.cur_frame[0]
    if img == 255: return None
    mirror = K.direction >= 0
    ox = sim.obj_x; x = int(ox * 8 / 7) if ox >= 0 else -int((-ox) * 8 / 7)
    w, h, _ = frames.get(img + 1, mirror)
    if mirror: x -= w
    return (img + 1, mirror, x, sim.obj_y - h + 1, w, h)

SWORD_TBL = BA.frame_tables()['sword']
def sword_sprite(sim, swords):
    """SDLPoP add_sword_to_objtable for the kid: (pack id, mirror, x, ytop, before_kid) or None. The sword shows
    on the found-sword frames 229..237 (and later whenever it is drawn)."""
    K = sim.Kid; sim.Char = K.copy(); sim.load_frame_to_obj()
    if not (229 <= K.frame < 238 or K.sword != 0): return None
    sf = sim.cur_frame[1] & 0x3F
    if sf == 0: return None
    sid, sx, sy = SWORD_TBL[sf]
    if sid == 0xFF: return None
    ox = sim.obj_x; x = int(ox * 8 / 7) if ox >= 0 else -int((-ox) * 8 / 7)
    x += -sx if K.direction < 0 else sx
    y = sim.obj_y + sy
    mirror = K.direction >= 0
    w, h, _ = swords.get(sid + 1, mirror)
    if mirror: x -= w
    return (sid + 1, mirror, x, y - h + 1, y < sim.obj_y)

def composite(rr, room, spr, kidset):
    rr.draw_room(room)
    if spr:
        pid, mirror, x, y, w, h = spr
        rr.sets[2] = kidset
        if 0 <= x and x + w <= 320 and 0 <= y and y + h <= 192:
            rr.ops['mid'].append((2, (pid, mirror), x, y, B_TRANSP))
    return rr.paint()

GUARDS_OFF = dict(guards=False, place=[], sword=False)
def setup(e, lv, start=True, opts=GUARDS_OFF):
    """RAM disk in game.asm's layout, the RAM directories, the level number, the guard options (guard.asm guard_opts;
    default: guards off, as the m4 scripts and tools/perfcheck.py are recorded) and the level-event options (guard.asm
    ev_opts: '# start', '# time'). Returns the symbols."""
    e.run_mzf(os.path.join(ROOT, 'build', 'm4game.mzf'))
    rd = lambda n: open(os.path.join(A, n), 'rb').read()
    write_pack(e, rd('dungeon.pack'), 0, 0)
    write_pack(e, rd('dungeon_wall.pack'), 1, 0x8000)
    write_pack(e, rd('objects.pack'), 1, 0xC000)
    write_pack(e, rd('sword.pack'), 1, 0xD000)
    write_pack(e, rd('kid.pack'), 2, 0)
    write_pack(e, rd('palace.pack'), 4, 0)
    write_pack(e, rd('palace_wall.pack'), 5, 0)
    lvf = lambda n: os.path.join(A, 'level%02d.bin' % n)
    levels = b''.join((open(lvf(n), 'rb').read()[:2305] if os.path.exists(lvf(n)) else b'').ljust(2305, b'\0') for n in range(16))
    write_pack(e, levels, 5, 0x4000)
    write_pack(e, rd('logic.bin'), 6, 0xD000)        # sequence and frame tables (kid.asm RD_SEQ, RD_FRAMES_*)
    gdirs = bytearray(6 * 0x120)                      # the guard sets (game.asm guard_type_tbl order), all resident
    for i, (name, page, base) in enumerate(GUARD_SETS):
        write_pack(e, rd(name + '.pack'), page, base)
        d = rebase_dir(rd(name + '.dir'), page, base); assert len(d) <= 0x120, name
        gdirs[i * 0x120:i * 0x120 + len(d)] = d
    write_pack(e, bytes(gdirs), 5, 0x3400)
    dirs = bytearray(0xEF18 - 0xD100)                 # all image directories, page 5 (game.asm: dir_entry reads them)
    for name, page, base, at, size in (('dungeon.dir', 0, 0, 0xD100, 0x700), ('dungeon_wall.dir', 1, 0x8000, 0xD800, 0x300),
                                       ('palace.dir', 4, 0, 0xDB00, 0x700), ('palace_wall.dir', 5, 0, 0xE200, 0x300),
                                       ('objects.dir', 1, 0xC000, 0xE500, 0x200), ('kid.dir', KID_PAGE, 0, 0xE700, 0x6E0),
                                       ('sword.dir', 1, 0xD000, 0xEE00, 0x118)):
        d = rebase_dir(rd(name), page, base); assert len(d) <= size, name
        dirs[at - 0xD100:at - 0xD100 + len(d)] = d
    write_pack(e, bytes(dirs), 5, 0xD100)
    S = syms(os.path.join(ROOT, 'build', 'm4game.sym'))
    ovl = open(os.path.join(ROOT, 'build', 'm4ovl.bin'), 'rb').read()   # code overlays (src/m4/ovl.asm): table + images
    write_pack(e, ovl, S['OVL_RD_PAGE'], S['OVL_RD_TAB'])
    write_pack(e, rd('sound.bin'), S['SB_PAGE'], S['SB_ADDR'])     # the PSG sound bank (tools/sndconv.py, src/m4/psg.asm)
    e.call('mem_write', addr=S['level_number'], data_hex='%02x' % lv)
    e.call('mem_write', addr=S['guard_opts'], data_hex=guard_opts_bytes(opts).hex())
    e.call('mem_write', addr=S['ev_opts'], data_hex=ev_opts_bytes(opts).hex())
    return S

def env_h(level_type, img):
    d = open(os.path.join(A, ('palace' if level_type else 'dungeon') + '.dir'), 'rb').read()
    return d[img * 8 + 4]

def mob_ops(sim):
    """Falling floors as game.asm draws them (SDLPoP draw_mob + the loose floor object): mid-table ops."""
    ops = []; room = sim.drawn_room; L, R, U, D = sim.links(room)
    for m in sim.mobs[:6]:
        y = m['y']
        if m['room'] == room:
            if y >= 210: continue
            yb = y
        elif m['room'] == D and D:
            sy = y - 256 if y > 127 else y
            if abs(sy) >= 18: continue
            yb = sy + 192
        elif m['room'] == U and U:
            if y < 174: continue
            yb = y - 189
        else: continue
        top = yb - 16
        if top < -16 or top >= 192: continue
        x = m['xh'] * 8; t = sim.level.type
        ops.append((6, 70, x, yb - 3 - env_h(t, 70) + 1, B_TRANSP))
        ops.append((6, 74, x, yb - env_h(t, 74) + 1, 0))
        ops.append((6, 72, x + 32, yb - 1 - env_h(t, 72) + 1, B_TRANSP))
    return ops

def kid_clip(sim):
    """(top row, right x in pixels) of the exit stairs clip (game.asm kid_clip), or None"""
    K = sim.Kid
    if not 224 <= K.frame < 229: return None
    room = sim.drawn_room
    for col in range(10):
        pos = K.curr_row * 10 + col
        if sim.tile_at(room, pos) == T.level_door_left:
            right = ((col + 1) * 4 + 6 + (1 if sim.level.type else 0)) * 8
            yb = (63 * K.curr_row + 49) & 0xFF; m = sim.mod_at(room, pos)
            lb = (yb - (m & 3) - 48) & 0xFF; y = (yb - m) & 0xFF
            while lb < y: lb = (lb + 4) & 0xFF
            return (lb + 1, right)
    return None

def tile_order(t):
    """Where SDLPoP's redraw_needed_tiles reaches a tilepos: rows 2, 1, 0, then the row above; 30 (no tile) first."""
    if t == 30: return -1
    if t < 0: return 30 + (-t - 1)
    return (2 - t // 10) * 10 + t % 10

class ObjImg:
    """A one-image set for the compositor (an object image after clipping)."""
    def __init__(self, img): self.img = img
    def get(self, key): return self.img
    def mono_colour(self, c): return 0
SwordSet = ObjImg
SWORDS = KidPack('sword')
PACKS = {}
def pack(name):
    if name not in PACKS: PACKS[name] = KidPack(name)
    return PACKS[name]
GUARD_TYPE_TBL = (0, 0, 0, 2, 0, 0, 1, 0, 0, 0, 0, 0, 4, 3, 0, 0)    # game.asm guard_type_tbl (index into GUARD_SETS)
def guard_pack(sim):
    """The level's guard set (chtab 5) as game.asm load_level picks it: a plain guard uses the palace set in palaces."""
    g = GUARD_TYPE_TBL[sim.level.number & 15]
    if g == 0 and sim.level.type: g = 5
    return pack(GUARD_SETS[g][0])

def screen_x(ox):
    """SDLPoP calc_screen_x_coord: logical x * 320 / 280, toward zero."""
    return int(ox * 8 / 7) if ox >= 0 else -int((-ox) * 8 / 7)

def char_present(sim, kid):
    """SDLPoP draw_kid / draw_guard: is the character drawn in the drawn room at all?"""
    if kid: return sim.Kid.room != 0 and sim.Kid.room == sim.drawn_room
    return sim.Guard.direction != kidsim.DIR_NONE and sim.Guard.room == sim.drawn_room

def obj_tile(sim, C):
    """SDLPoP set_objtile_at_char for C (before redraw_at_char widens the columns)."""
    sim.Char = C.copy(); sim.load_fram_det_col(); sim.load_frame_to_obj(); sim.set_char_collision()
    f, a = C.frame, C.action
    if a == kidsim.A_RUN_JUMP: row, col = sim.char_bottom_row, sim.char_col_left
    else: row, col = sim.Char.curr_row, sim.Char.curr_col
    if (135 <= f < 149) or a in (kidsim.A_HANG_CLIMB, kidsim.A_MIDAIR, kidsim.A_FREEFALL, kidsim.A_HANG_STRAIGHT): col -= 1
    if row < 0 or row >= 3 or col >= 10 or col < 0: return 30
    return row * 10 + col

MIRROR_LEVEL, MIRROR_ROOM, MIRROR_COLUMN = 4, 4, 4      # SDLPoP custom->mirror_level, mirror_room, mirror_column
def blink_shadow(sim):
    """SDLPoP draw_objtable_item: after the level 12 union the kid (and a mirror image) is drawn as the shadow while
    united_with_shadow is even and not 0"""
    u = sim.united_with_shadow
    return u != 0 and u % 2 == 0

def add_obj(objs, typ, tile, y, pk, pid, x, yb, clip, mirror, xor=0):
    """an objtable entry with its image clipped (clip = top row, right x, left x); xor = d: drawn as the shadow, a
    second copy XORed d pixels right (SDLPoP draw_objtable_item case 1: blitters_2_or at xl, blitters_3_xor at xl + 1;
    d = calc_screen_x_coord(x + 1) - calc_screen_x_coord(x))"""
    w, h, rows = pk.get(pid, mirror)
    if mirror: x -= w
    ytop = yb - h + 1
    top, right, left = clip
    vis = lambda xx, yy: ytop + yy >= top and left <= x + xx < right and ytop + yy < 192
    clipped = lambda dx: [[(c if vis(xx + dx, yy) else -1) for xx, c in enumerate(row)] for yy, row in enumerate(rows)]
    objs.append(dict(type=typ, tile=tile, y=y, img=(w, h, clipped(0)), x=x, ytop=ytop, xor=xor,
                     img2=(w, h, clipped(xor)) if xor else None))

def people_objs(sim, kp, mirror_tile=30):
    """SDLPoP draw_people: the objtable entries of the mirror image, the kid and the guard in insertion order (mirror
    image; character, hurt splash, sword): dicts with type (0 kid, 1 shadow, 2 guard, 3 sword, 4 mirror image,
    5 splash), tile, y (objtable y = bottom row), the clipped image to draw (img = (w, h, rows), x, ytop) and xor (the
    shadow's second copy). mirror_tile: SDLPoP's obj_tilepos when check_mirror adds the image (objtile_frame)."""
    objs = []
    gp = guard_pack(sim)
    mi = getattr(sim, 'mirror_img', None)                # check_mirror (draw_people): the kid's mirror image
    if mi is not None:
        C, dist = mi
        if dist >= 0 and C.room == sim.drawn_room:
            saved = sim.Char; sim.Char = C.copy(); sim.load_frame_to_obj(); sim.Char = saved
            clip_top = kidsim.KidSim.Y_CLIP[C.curr_row + 1] & 0xFFFF      # (a word in SDLPoP: -60 is never < obj_y)
            if clip_top < sim.obj_y and sim.obj_id != 255:
                ox = sim.obj_x
                add_obj(objs, 4, mirror_tile, sim.obj_y, kp if sim.obj_chtab == 2 else gp, sim.obj_id + 1, screen_x(ox),
                        sim.obj_y, (clip_top, 320, C.curr_col * 32 + 9), C.direction == kidsim.RIGHT,
                        screen_x(ox + 1) - screen_x(ox) if blink_shadow(sim) else 0)
    for kid in (True, False):
        if not char_present(sim, kid): continue
        C = sim.Kid if kid else sim.Guard
        tile = obj_tile(sim, C)
        ct, cr = sim.clip_char(C)                       # (loads C again: load_fram_det_col, load_frame_to_obj, ...)
        ox, oy, chtab, oid, mirror = sim.obj_x, sim.obj_y, sim.obj_chtab, sim.obj_id, C.direction == kidsim.RIGHT
        sword_frame = sim.cur_frame[1] & 0x3F
        fwd = (lambda d: d) if C.direction >= kidsim.RIGHT else (lambda d: -d)      # obj_dx_forward
        shadow = not kid and C.charid == kidsim.CHARID_SHADOW
        cl = 0                                          # add_guard_to_objtable: the shadow only right of the mirror
        if shadow and sim.level.number == MIRROR_LEVEL and C.room == MIRROR_ROOM: cl = 137 + (MIRROR_COLUMN - 4) * 32
        def add(typ, tile, y, pk, pid, x, yb, clip, xor=0):
            add_obj(objs, typ, tile, y, pk, pid, x, yb, clip, mirror, xor)
        if oid != 255:
            sx = screen_x(ox)
            add(0 if kid else (1 if shadow else 2), tile, oy, kp if chtab == 2 else gp, oid + 1, sx, oy, (ct, cr, cl),
                screen_x(ox + 1) - sx if (shadow or (kid and blink_shadow(sim))) else 0)
        if (sim.hitp_delta if kid else sim.guardhp_delta) < 0 and C.frame != 178:      # draw_hurt_splash
            f = C.frame; sx, sy = ox, oy
            if f == 185 or 106 <= f < 111: sy += 4; sx += fwd(5)
            elif f == 177: sx += fwd(-5)
            else: sy -= (4 if C.charid == kidsim.CHARID_KID else 0) + 11; sx += fwd(5)
            if C.charid == kidsim.CHARID_KID: add(5, 255, sy, kp, 219, screen_x(sx), sy, (0, 320, 0))
            else: add(5, 255, sy, gp, 2, screen_x(sx), sy, (0, 320, 0))
        if ((229 <= C.frame < 238) or C.sword != kidsim.SWORD_SHEATHED or        # add_sword_to_objtable
                (C.charid == kidsim.CHARID_GUARD and C.alive < 0)) and sword_frame:
            sid, dx, dy = SWORD_TBL[sword_frame]
            if sid != 0xFF: add(3, tile, oy + dy, SWORDS, sid + 1, screen_x(ox) + fwd(dx), oy + dy, (ct, cr, cl))
    return objs

def mid_sequence(sim, rr, objs):
    """SDLPoP redraw_needed_tiles for the objects and the overlays (redraw_at_char2 of both characters): the midtable
    ops in drawing order, and the fore-table ops of the row above. Objects of a tile come after the tile's overlay, in
    y order (objtable scanned last to first, bubble-sorted; the shadow last); draw_other_overlay's second case draws
    the objects of the tile to the left again. Overlays at or before the first character's tile are left out (they
    only re-lay the room under nothing)."""
    room = sim.drawn_room
    marks = {}; first = None
    for kid in (True, False):
        if not char_present(sim, kid): continue
        C = sim.Kid if kid else sim.Guard
        ov = sim.overlay_tiles(C)
        o = tile_order(obj_tile(sim, C))
        first = o if first is None else min(first, o)
        if ov is None: continue
        kind, tiles, _ = ov
        for t in tiles:
            if t == 30: continue
            if marks.get(t) != 'other': marks[t] = kind      # (redraw_frames2 wins over the floor overlay)
    def at(t):
        sel = [o for o in reversed(objs) if o['tile'] == t]
        sel.sort(key=lambda o: (o['type'] == 1, o['y']))
        out = []
        for o in sel:
            k = 100 + objs.index(o); rr.sets[k] = ObjImg(o['img'])
            out.append((k, None, o['x'], o['ytop'], B_TRANSP))
            if o['xor']:
                rr.sets[k + 50] = ObjImg(o['img2'])
                out.append((k + 50, None, o['x'] + o['xor'], o['ytop'], ('XOR', o['x'], o['img'][2])))
        return out
    mid = at(30); fore = []
    for row in (2, 1, 0):
        for col in range(10):
            t = row * 10 + col
            if t in marks and first is not None and tile_order(t) > first:
                ops, left = rr.overlay(room, t, marks[t], sim.Kid.frame)
                mid.extend(ops)
                if left: mid.extend(at((t - 1) & 0xFF))
            mid.extend(at(t))
    for t in sorted((t for t in marks if t < 0), key=tile_order):
        fore.extend(rr.overlay(room, t, marks[t], sim.Kid.frame)[0])
    mid.extend(at(255))
    return mid, fore

HP_IMG = {}
def hp_icons(kp):
    if not HP_IMG: HP_IMG['full'] = kp.get(217); HP_IMG['empty'] = kp.get(218)
    return HP_IMG

def ghp_instrument(sim):
    """The guard's hit point strip as SDLPoP leaves it on the screen: draw_guard_hp(0, guardhp_curr) erases it where
    the logic drops a guard (clear_char, leave_guard, enter_guard of a dead guard, check_guard_fallout); draw_hp
    redraws it when guardhp_delta != 0. sim.ghp_shown = the slots showing a full icon (slot i at x = 314 - 7 i)."""
    sim.ghp_shown = set(); sim.ghp_erase = 0
    for name in ('clear_char', 'leave_guard', 'enter_guard', 'check_guard_fallout'):
        orig = getattr(sim, name)
        def wrap(*a, _o=orig, **k):
            before = sim.guardhp_curr
            r = _o(*a, **k)
            if before and sim.guardhp_curr == 0: sim.ghp_erase = max(sim.ghp_erase, before)
            return r
        setattr(sim, name, wrap)
def ghp_shows(sim):
    c = sim.Guard.charid
    return c not in (kidsim.CHARID_SKELETON, kidsim.CHARID_MOUSE) and (c != kidsim.CHARID_SHADOW or sim.level.number == 12)
def ghp_step(sim, x, y, sh, k=0):
    """sim.step with the guard strip's model (seg000 draw_hp after the tick, without the one-hit-point blink)."""
    sim.ghp_erase = 0
    r = sim.step(x, y, sh, k)
    if ghp_shows(sim):
        if sim.ghp_erase: sim.ghp_shown -= set(range(sim.ghp_erase))
        if sim.guardhp_delta:
            sim.ghp_shown = set(range(sim.guardhp_curr)) | {i for i in sim.ghp_shown if i >= sim.guardhp_max}
    return r

def paint(rr):
    """popdata.RoomRenderer.paint plus the shadow's XOR copy: an op with blit ('XOR', x of the first copy) XORs its
    image per plane (SDLPoP blit_xor XORs RGB, which for these RGBI colours is the XOR of the colour numbers); the
    kid's black (stored as 8: sprites have no mask) XORs nothing, and where the first copy left such a black pixel the
    result is the XOR colour (black ^ c = c)."""
    scr = [[0] * 320 for _ in range(200)]
    def blit_img(ch, id1, x0, y0, blit):
        w, h, rows = rr.sets[ch].get(id1)
        if isinstance(blit, tuple):
            _, xf, first = blit
            for y in range(h):
                sy = y0 + y
                if not 0 <= sy < 200: continue
                srow = rows[y]; frow = first[y]; drow = scr[sy]
                for x in range(w):
                    sx = x0 + x; c = srow[x]
                    if not 0 <= sx < 320 or c < 0 or c == 8: continue
                    f = sx - xf
                    drow[sx] = c if 0 <= f < w and frow[f] == 8 else drow[sx] ^ c
            return
        mono = rr.sets[ch].mono_colour(blit & 0x0F) if blit >= B_MONO else 0
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
        col = rr.wallcol.get(color, color) if color >= 0x60 else color
        for y in range(top, top + height):
            if not 0 <= y < 200: continue
            for x in range(left, left + width):
                if 0 <= x < 320: scr[y][x] = col
    for op in rr.ops['wipe0']: wipe(op)
    for op in rr.ops['back']: blit_img(*op)
    for op in rr.ops['mid']: blit_img(*op)
    for op in rr.ops['wipe1']: wipe(op)
    for op in rr.ops['fore']: blit_img(*op)
    from PIL import Image
    im = Image.new('P', (320, 200)); px = im.load()
    for y in range(200):
        for x in range(320): px[x, y] = scr[y][x]
    pal = []
    for c in MZ: pal += list(c)
    im.putpalette(pal + [0] * (768 - 48))
    return im

# ---- the bottom text (SDLPoP display_text_bottom: rect_bottom_text = rows 193..201, x 70..249, black, then the text
# centred, glyph tops at row 193 (valign bottom), font hc_font: 1 px between characters, colour 15 mono blits)
class Font:
    """SDLPoP's hc_font: character c = data/font/res(1000 + c).png, drawn where the pixel is not 0"""
    def __init__(self): self.cache = {}
    def get(self, ch):
        if ch not in self.cache:
            from PIL import Image
            from popdata import DATA
            im = Image.open(os.path.join(DATA, 'font', 'res%d.png' % (1000 + ord(ch)))); w, h = im.size; px = im.load()
            self.cache[ch] = (w, h, [[(15 if px[x, y] else -1) for x in range(w)] for y in range(h)])
        return self.cache[ch]
def text_width(text, font):
    return sum(font.get(ch)[0] + 1 for ch in text)
def text_shown(sim):
    """the bottom text on screen after the tick: texts are displayed when set (show_level, show_time, the death text)
    and erased when they run out; 'Press Button to Continue' (288 ticks) blinks in its last 72 ticks (draw_game_frame:
    erased while text_time_remaining % 12 > 3, shown again at 3); the 36-tick death text has no text"""
    tot, rem = sim.text_time_total, sim.text_time_remaining
    if tot in (0, 36) or (tot == 288 and rem < 72 and rem % 12 > 3): return ''
    return sim.bottom_text
def draw_text(px, text, font):
    x = 70 + 180 // 2 - text_width(text, font) // 2
    for ch in text:
        w, h, rows = font.get(ch)
        for yy in range(h):
            for xx in range(w):
                if rows[yy][xx] >= 0 and 70 <= x + xx < 250 and 193 + yy < 200: px[x + xx, 193 + yy] = 15
        x += w + 1

# ---- what the drawing needs from inside the tick
def fx_instrument(sim):
    """SDLPoP check_mirror (draw_people): the kid's mirror image is the kid as check_mirror_image mirrors him, taken
    before the next tick reloads Char (sim.mirror_img = (Char, distance_mirror) or None); flash_if_hurt after
    draw_game_frame: the flash colour of the tick (sim.flash_shown, EGA colour number, 0 = none)."""
    o_cm, o_cmi, o_dgf = sim.check_mirror, sim.check_mirror_image, sim.draw_game_frame
    def cmi():
        r = o_cmi(); sim._cmi = (sim.Char.copy(), sim.distance_mirror); return r
    def cm():
        sim._cmi = None; jump = sim.jumped_through_mirror == -1
        r = o_cm()
        sim.mirror_img = None if jump else sim._cmi
        return r
    def dgf():
        before = sim.flash_time
        r = o_dgf()
        sim.flash_shown = sim.flash_color if before else (12 if sim.hitp_delta < 0 else 0)
        return r
    sim.check_mirror_image, sim.check_mirror, sim.draw_game_frame = cmi, cm, dgf
    sim.mirror_img = None; sim.flash_shown = 0; sim.objt = 0
def fx_step(sim, x, y, sh, k=0):
    """ghp_step with the per-tick drawing state (flash, obj_tilepos)"""
    sim.flash_shown = 0
    r = ghp_step(sim, x, y, sh, k)
    sim.mirror_tile = objtile_frame(sim)
    return r
def objtile_frame(sim):
    """SDLPoP's obj_tilepos through one drawn frame: draw_mobs sets it for each falling floor it draws, check_mirror's
    image takes it as it is, draw_kid and draw_guard set it (set_objtile_at_char). Returns the mirror image's tile."""
    saved = sim.Char
    room = sim.drawn_room; L, R, U, D = sim.links(room)
    for m in sim.mobs:
        y = m['y']
        if m['room'] == room:
            if y >= 210: continue
            yb = y
        elif m['room'] == D:
            sy = y - 256 if y > 127 else y
            if abs(sy) >= 18: continue
            yb = sy + 192
        elif m['room'] == U:
            if y < 174: continue
            yb = y - 189
        else: continue
        col, row = m['xh'] >> 2, sim.y_to_row_mod4(yb)
        sim.objt = 30 if row < 0 or row >= 3 or col >= 10 or col < 0 else row * 10 + col
    mt = sim.objt
    for kid in (True, False):
        if char_present(sim, kid): sim.objt = obj_tile(sim, sim.Kid if kid else sim.Guard)
    sim.Char = saved
    return mt

FONT = None
def reference(sim, rr, kp, kidset):
    global FONT
    room = sim.drawn_room
    rr.draw_room(room)
    rr.sets[2] = kidset
    rr.ops['mid'].extend(mob_ops(sim))
    mid, fore = mid_sequence(sim, rr, people_objs(sim, kp, getattr(sim, 'mirror_tile', 30)))
    rr.ops['mid'].extend(mid); rr.ops['fore'].extend(fore)
    im = paint(rr)
    px = im.load()
    if sim.upside_down:                            # SDLPoP flip_screen: the 192 playfield rows upside down
        rows = [[px[xx, yy] for xx in range(320)] for yy in range(192)]
        for yy in range(192):
            for xx in range(320): px[xx, yy] = rows[191 - yy][xx]
    icons = hp_icons(kp)
    for yy in range(192, 200):                     # the playfield is 192 rows; below it the hit point strips and the text
        for xx in range(320): px[xx, yy] = 0
    for i in range(sim.hitp_max):                  # the kid's (left)
        w, h, rows = icons['full' if i < sim.hitp_curr else 'empty']
        for yy in range(h):
            for xx in range(w):
                px[i * 7 + xx, 194 + yy] = max(rows[yy][xx], 0)
    w, h, rows = guard_pack(sim).get(1)            # the guard's (right): chtab 5 image 0, opaque
    for i in getattr(sim, 'ghp_shown', ()):
        for yy in range(h):
            for xx in range(w):
                if 0 <= 314 - i * 7 + xx < 320: px[314 - i * 7 + xx, 194 + yy] = max(rows[yy][xx], 0)
    text = text_shown(sim)
    if text:
        if FONT is None: FONT = Font()
        draw_text(px, text, FONT)
    return im

def main():
    args = sys.argv[1:]
    gui = '--gui' in args
    lv = int(args[args.index('--level') + 1]) if '--level' in args else 1
    every = int(args[args.index('--every') + 1]) if '--every' in args else 5
    import glob
    scripts = [a for a in args if a.endswith('.txt')] or sorted(glob.glob(os.path.join(ROOT, 'tests', 'm4_scripts', '*.txt')))
    if gui:
        from m3_demo import TcpEmu, EXE_GUI
        import subprocess
        p = subprocess.Popen([EXE_GUI, '--mcp-tcp-port', '5656', '--no-first-run-windows'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        e = TcpEmu(5656); e.call('run', frames=3)
        setup(e, lv, opts=dict(guards=True, place=[], sword=False)); e.call('set_speed', mode='normal'); e.call('run')
        print('the prince is running in the emulator window (level %d). Cursor keys / joystick 1 move, SHIFT / fire = the button (careful step, grab, pick up), SPACE = the time, BREAK = pause.' % lv)
        e.close(); return
    kp = KidPack(); kidset = KidSet(kp); total_bad = 0
    with Emu() as e:
        for sp in scripts:
            moves, patches = kidsim.read_script(sp); keys = kidsim.read_keys(sp)
            lv = int(args[args.index('--level') + 1]) if '--level' in args else kidsim.script_level(sp)
            o = kidsim.script_opts(sp)
            after_death = any(l.startswith('# draw after death') for l in open(sp))   # (no SDLPoP comparison there: its
            sim = kidsim.KidSim(Level(lv), patches=patches, guards=o['guards'], place=o['place'], sword=o['sword'],   # death
                                time=o['time'], start=o['start'], multi_level=True)                  # timer waits on sounds)
            ghp_instrument(sim); fx_instrument(sim)
            sim.objt = 0; objtile_frame(sim)               # (the level start's first draw: draw_level_first)
            rr = RoomRenderer(sim.level, ega=True)
            S = setup(e, lv, opts=o)
            write_pack(e, encode(moves, keys), 5, SCRIPT)
            e.call('mem_write', addr=SCRIPT_PTR, data_hex='%02x%02x' % (SCRIPT & 255, SCRIPT >> 8))
            e.call('bp_clear'); e.call('bp_add', addr=S['guards_off_chk'])
            r = e.run(400); assert r['stopped_by'] == 'breakpoint', r
            for (rm, p, t, m) in patches:                  # patches go in where SDLPoP's hook applies them: at the first
                e.call('mem_write', addr=LEVEL_ADDR + (rm - 1) * 30 + p, data_hex='%02x' % t)      # tick's control step
                e.call('mem_write', addr=LEVEL_ADDR + 720 + (rm - 1) * 30 + p, data_hex='%02x' % m)
            e.call('bp_clear'); e.call('bp_add', addr=S['tick_done'])
            frames_out = []; bad_state = 0; bad_px = 0; first = None; t0 = time.time(); stop = None
            for t, ((x, y, sh), k) in enumerate(zip(moves, keys)):
                r = e.run(400); assert r['stopped_by'] == 'breakpoint', (sp, t, r)
                ref = fx_step(sim, x, y, sh, k)
                if ref is None or sim.game_over:        # (M5 scenes: a restart tick has no state; game over: the end)
                    if sim.game_over: break
                    continue
                got = z80_state(e, int(ref.split()[0]))
                fl = e.mem(S['FL_SHOWN'], 1)[0]         # the flash the tick showed (flash_if_hurt), MZ colour
                want = EGA2MZ[sim.flash_shown & 15] if sim.flash_shown else 0
                if fl != want:
                    bad_state += 1
                    if first is None: first = ('flash', t, want, fl)
                if sim.level_done:          # the exit: the Z80 is on the level kidsim is on now, then stop (M7 step 5: the
                    lvl = e.mem(S['level_number'], 1)[0]        # stairs of levels 1-12 wait for the end music, which
                    print('   exit reached at tick %d; the program is on level %d now (kidsim %d)' % (t, lvl, sim.level.number))
                    if lvl != sim.level.number: bad_state += 1  # never ends in the silent mode: the level stays)
                    break
                if norm(ref) != norm(got):
                    bad_state += 1
                    if first is None: first = ('state', t, ref, got)
                if t % every == 0 or t == len(moves) - 1:
                    if rr.level is not sim.level: rr = RoomRenderer(sim.level, ega=True)     # (M5: a new level)
                    im = e.vram_image(); refim = reference(sim, rr, kp, kidset)
                    pm, pr = im.load(), refim.load()
                    bad = [(xx, yy, pm[xx, yy], pr[xx, yy]) for yy in range(200) for xx in range(320) if pm[xx, yy] != pr[xx, yy]]
                    if bad:
                        bad_px += len(bad)
                        if first is None: first = ('screen', t, bad[:4])
                        tag = os.path.basename(sp)[:-4]
                        im.save(os.path.join(ROOT, 'build', 'm4_%s_t%d_z80.png' % (tag, t))); refim.save(os.path.join(ROOT, 'build', 'm4_%s_t%d_ref.png' % (tag, t)))
                    frames_out.append(im.convert('RGB'))
                if stop is None and ((sim.Kid.alive >= 0 and not after_death) or sim.level_done): stop = t + (1 if sim.level_done else 8)
                if stop is not None and t >= stop: break          # after a death (restart) or the exit (next level) the simulator stops
            total_bad += bad_state + bad_px
            gif = os.path.join(ROOT, 'build', 'm4_%s.gif' % os.path.basename(sp)[:-4])
            if frames_out: frames_out[0].save(gif, save_all=True, append_images=frames_out[1:], duration=80 * every, loop=0)
            print('%-20s %4d ticks: %d state diffs, %d differing pixels%s  (%.0fs)' % (os.path.basename(sp), t + 1, bad_state, bad_px, '' if first is None else '; first: %s' % (first,), time.time() - t0))
    print('total:', total_bad)

if __name__ == '__main__': main()
