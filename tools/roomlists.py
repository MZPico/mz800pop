#!/usr/bin/env python3
"""M8a part 22: every room's op lists precomputed at build time (docs/perf.md "M8a part 22: precomputed room lists").

The Z80 room renderer (src/m3/room.asm, roomfull.asm room_ops) builds a room's op lists from the level's tiles at every
room change. They depend only on the tiles (and the door-link timers of buttons), so this tool builds them here with
the Python reference (tools/popdata.py, whose lists tests/m3_test.py checks against room_ops for every room) for the
level's canonical state: the tiles as the game's load_level leaves them (the blueprint, then alter_mods), with one
change: a potion's bubble frame is 1, not 0 (frame 0 draws no bubble, so the stored list holds the bubble record that
the room draw patches to the frame on screen). At a room change the game (src/m3/rlists.asm) reads the room's lists
back from the RAM disk and regenerates only the tiles whose inputs differ from the canonical state.

The data, one blob a level (build/assets/rlists.bin: the 14 blobs, each padded to 256 bytes, behind a 256-byte index;
tools/mkgamedisk.py puts them on the floppy as POP800.RLS, PZ-packed; the game loads the level's blob into the RAM disk at
the first room draw of a level):
  0  'R', level, number of records in the dictionary, number of groups
  4  the dictionary's size (records 8 N + group table 2 G + groups), 16-bit
  6  the rooms' stream offsets from the blob start (24 x 16-bit; 0 = no room)
  54 the record dictionary: N x 8 bytes, a record relative to its tile: flags, chtab, id, xbyte - 4 col, ytop - 63 row
     (lo, hi; the row above: row -1), w, h
     the group table: G x 16-bit, a group's offset from the dictionary's start
     the groups: count, then count record indices (group 0 is empty)
  then per room: the back list's group per position key 0..39 (room.asm tag_key order: row 2, 1, 0, the row above),
     the fore list's 40, then the mid list: count, count x (key, record index)
usage: roomlists.py [--check DUMP.pkl]   (writes build/assets/rlists.bin; --check compares with a Z80 dump)"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from popdata import Level, RoomRenderer, room_oplist, T, CH_ENV, CH_WALL, CH_OBJ
ROOT = os.path.join(HERE, '..')
A = os.path.join(ROOT, 'build', 'assets')
OUT = os.path.join(A, 'rlists.bin')
DISK = os.path.join(A, 'rlists_rls.bin')
INC = os.path.join(A, 'rlists.inc')
CHUNK = 0x800              # a PZ chunk unpacks to at most this (save.asm RL_UNBUF 0x9000-0x97FF)
LOW_BLOCKS = 3             # POP800.RLS's first blocks: the compare's low code (game.asm RL_LOWBLK, src/m4/rllow.asm)
PZ_BLOCKS = 11             # a level's packed blocks (save.asm RL_PZBUF: OVL_W2 + 0x500 to the window's end)
MAGIC = ord('R')
HDR = 54
OPMAX = (192, 8, 128)
BLOB_MAX = 0x11C0          # the RAM-disk area (src/m3/rlists.asm RL_BASE .. RL_END: page 6 0x16C0-0x287F)
DICT_MAX = 0x1000          # the dictionary is read into COMPOSE_A/B (4 KB) at a room change
KEY_ROW = [2] * 10 + [1] * 10 + [0] * 10 + [-1] * 10

def key_of_tag(t):
    return t if t >= 30 else (2 - t // 10) * 10 + t % 10

def tag_of_key(k):
    return k if k >= 30 else (2 - k // 10) * 10 + k % 10

class TagRR(RoomRenderer):
    """popdata's renderer, noting each op's tile tag (room.asm CUR_TAG: row * 10 + col, 30 + col for the row above)"""
    def add(self, table, ch, id1, xh, xl, ybottom, blit):
        n = len(self.ops[table]); r = super().add(table, ch, id1, xh, xl, ybottom, blit)
        if len(self.ops[table]) > n and hasattr(self, 'tagl'):
            self.tagl[table].append(30 + self.drawn_col if self.draw_bottom_y == 2 else self.drawn_row * 10 + self.drawn_col)
        return r
    def paint(self): return None
    def room_lists(self, room, variants, dirs):
        """[(record bytes, tag)] per list (back, mid, fore), as room_ops leaves them"""
        self.tagl = {'back': [], 'mid': [], 'fore': []}
        self.draw_room(room)
        ops = room_oplist(self, variants)
        out = ([], [], [])
        tags = self.tagl['back'] + self.tagl['mid'] + self.tagl['fore']
        assert len(tags) == len(ops)
        for (ti, ch, vid, xb, yt, code, mono), tag in zip(ops, tags):
            d = dirs[ch][vid * 8: vid * 8 + 8]
            rec = struct.pack('<BBBbhBB', ti | code << 2 | mono << 4, ch, vid, xb, yt, d[3], d[4])
            out[ti].append((rec, tag))
        for ti in range(3): assert len(out[ti]) <= OPMAX[ti], (room, ti, len(out[ti]))
        return out

def assets(ltype):
    env = 'palace' if ltype else 'dungeon'
    variants = {}
    for name, ch in ((env, CH_ENV), (env + '_wall', CH_WALL), ('objects', CH_OBJ)):
        for (i, sft, vid) in json.load(open(os.path.join(A, name + '.json')))['variants']: variants[(ch, i, sft)] = vid
    dirs = {CH_ENV: open(os.path.join(A, env + '.dir'), 'rb').read(), CH_WALL: open(os.path.join(A, env + '_wall.dir'), 'rb').read(),
            CH_OBJ: open(os.path.join(A, 'objects.dir'), 'rb').read()}
    return variants, dirs

def canonical(lv):
    """the level's canonical state: load_level's (popdata.Level applies alter_mods) with potions at bubble frame 1"""
    level = Level(lv)
    for i in range(720):
        if level.fg[i] & 0x1F == T.potion: level.bg[i] |= 1
    for i in range(720):        # (rlists.asm takes a button's canonical state as not pressed)
        if level.fg[i] & 0x1F in (T.opener, T.closer): assert level.raw[1696 + level.bg[i]] & 0x1F <= 1, (lv, i)
    return level

def level_lists(lv, level=None):
    level = level or canonical(lv)
    rr = TagRR(level, ega=True); variants, dirs = assets(level.type)
    return {room: rr.room_lists(room, variants, dirs) for room in range(1, level.used_rooms + 1)}

def rel(rec, tag):
    row, col = KEY_ROW[key_of_tag(tag)], (tag % 10 if tag < 30 else tag - 30)
    f, ch, i, xb, yt, w, h = struct.unpack('<BBBbhBB', rec)
    return struct.pack('<BBBbhBB', f, ch, i, xb - 4 * col, yt - 63 * row, w, h)

def encode(lv, lists):
    dic = {}; groups = {(): 0}
    def gid(seq):
        return groups.setdefault(tuple(seq), len(groups))
    streams = {}
    for room, ls in lists.items():
        s = bytearray()
        for ti in (0, 2):
            per = [[] for _ in range(40)]
            last = -1
            for rec, tag in ls[ti]:
                k = key_of_tag(tag); assert k >= last; last = k
                per[k].append(dic.setdefault(rel(rec, tag), len(dic)))
            s += bytes(gid(p) for p in per)
        mid = ls[1]; s.append(len(mid)); last = -1
        for rec, tag in mid:
            k = key_of_tag(tag); assert k >= last; last = k
            s += bytes((k, dic.setdefault(rel(rec, tag), len(dic))))
        streams[room] = bytes(s)
    assert len(dic) <= 255 and len(groups) <= 255 and all(len(g) <= 255 for g in groups), lv
    recs = b''.join(sorted(dic, key=dic.get))
    gl = sorted(groups, key=groups.get)
    gtab = bytearray(); gdata = bytearray(); base = len(recs) + 2 * len(gl)
    for g in gl:
        gtab += struct.pack('<H', base + len(gdata)); gdata += bytes((len(g),) + g)
    dict_ = recs + bytes(gtab) + bytes(gdata)
    assert len(dict_) <= DICT_MAX, (lv, len(dict_))
    idx = [0] * 24; body = bytearray(); pos = HDR + len(dict_)
    for room in sorted(streams):
        idx[room - 1] = pos + len(body); body += streams[room]
    blob = bytes((MAGIC, lv, len(dic) & 255, len(gl))) + struct.pack('<H', len(dict_)) + struct.pack('<24H', *idx) + dict_ + bytes(body)
    return blob

def decode(blob):
    """blob -> {room: ([(rec, tag)] x 3)} (the Z80 decoder's result, without patches)"""
    nrec = blob[2] or 256; dsz = struct.unpack_from('<H', blob, 4)[0]; idx = struct.unpack_from('<24H', blob, 6)
    d = blob[HDR:HDR + dsz]
    def group(g):
        o = struct.unpack_from('<H', d, 8 * nrec + 2 * g)[0]; return d[o + 1:o + 1 + d[o]]
    def absrec(i, k):
        f, ch, id_, xr, yr, w, h = struct.unpack_from('<BBBbhBB', d, 8 * i)
        t = tag_of_key(k); col = t % 10 if t < 30 else t - 30
        return struct.pack('<BBBbhBB', f, ch, id_, (xr + 4 * col + 128) % 256 - 128, (yr + 63 * KEY_ROW[k] + 32768) % 65536 - 32768, w, h), t
    out = {}
    for room in range(1, 25):
        if not idx[room - 1]: continue
        p = idx[room - 1]; ls = ([], [], [])
        for ti in (0, 2):
            for k in range(40):
                for i in group(blob[p + k]): ls[ti].append(absrec(i, k))
            p += 40
        n = blob[p]; p += 1
        for j in range(n): ls[1].append(absrec(blob[p + 2 * j + 1], blob[p + 2 * j]))
        out[room] = ls
    return out

def build():
    blobs = []
    for lv in range(1, 15):
        lists = level_lists(lv); b = encode(lv, lists)
        assert decode(b) == lists, lv
        assert len(b) <= BLOB_MAX, (lv, len(b), BLOB_MAX)
        blobs.append(b)
        print('level %2d: %d rooms, %d records in %d groups, dictionary %d bytes, blob %d bytes (of %d)' % (
            lv, len(lists), b[2], b[3], struct.unpack_from('<H', b, 4)[0], len(b), BLOB_MAX))
    index = bytearray(256); data = bytearray()
    for i, b in enumerate(blobs):        # index: per level 1-14 the blob's block (from the file's first) and length
        struct.pack_into('<HH', index, 4 * (i + 1), 1 + len(data) // 256, len(b))
        data += b + bytes(-len(b) % 256)
    open(OUT, 'wb').write(bytes(index) + bytes(data))
    # the floppy file POP800.RLS (tools/mkgamedisk.py): per level its blob as PZ chunks of at most CHUNK bytes each
    # (src/m4/save.asm rl_fetch_h unpacks a chunk at 0x9000, then writes it to the RAM disk), from a whole block;
    # the table (rlists.inc, the save overlay's): per level the first block (from the file's), blocks, chunks
    import pzpack
    disk = bytearray(); inc = ['; generated by tools/roomlists.py: POP800.RLS, per level 1-14 the first block (from the file\'s',
                               '; first), the blocks and the PZ chunks of its room-list blob (src/m4/save.asm rl_fetch_h)',
                               'RL_DISK_LOW     equ     %d               ; the low code\'s blocks first (game.asm RL_LOWBLK)' % LOW_BLOCKS, 'rl_disk:']
    for lv, b in enumerate(blobs, 1):
        z = b''.join(pzpack.compress(b[o:o + CHUNK]) for o in range(0, len(b), CHUNK))
        nb = (len(z) + 255) // 256; assert nb <= PZ_BLOCKS, (lv, nb)
        inc.append('                db      %d, %d, %d, %d      ; level %d: %d bytes PZ, %d raw' % (
            (LOW_BLOCKS + len(disk) // 256) & 255, (LOW_BLOCKS + len(disk) // 256) >> 8, nb, (len(b) + CHUNK - 1) // CHUNK, lv, len(z), len(b)))
        disk += z + bytes(-len(z) % 256)
    open(DISK, 'wb').write(bytes(disk))
    open(INC, 'w').write('\n'.join(inc) + '\n')
    print('wrote %s: %d bytes (%d blocks), %s' % (DISK, len(disk), len(disk) // 256, INC))

def check(dump):
    """the lists of the plain load state (no potion change) against a Z80 dump of room_ops (scratch tool)"""
    import pickle
    D = pickle.load(open(dump, 'rb')); bad = 0
    for lv in range(1, 15):
        lists = level_lists(lv, Level(lv))
        for room, ls in lists.items():
            c, recs, tags = D[(lv, room)]
            for ti in range(3):
                got = b''.join(r for r, t in ls[ti]); gt = bytes(t for r, t in ls[ti])
                if got != recs[ti] or gt != tags[ti] or len(ls[ti]) != c[ti]:
                    bad += 1; print('level %d room %d list %d differs' % (lv, room, ti))
    print('rooms differing:', bad)
    return bad

if __name__ == '__main__':
    if len(sys.argv) > 2 and sys.argv[1] == '--check':
        sys.exit(1 if check(sys.argv[2]) else 0)
    build()
