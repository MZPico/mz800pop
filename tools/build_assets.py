#!/usr/bin/env python3
"""Build every asset pack for the MZ-800 port from the SDLPoP data folder.

Output (build/assets/):
  <set>.pack / <set>.dir / <set>.json   planar image packs (see tools/pack.py for the format);
                                        directory index = SDLPoP 1-based image id of that chtab
  levelNN.bin                           raw 2305-byte level blueprints (alter_mods applied by the game)
  tables.inc                            Z80 assembler tables ported from SDLPoP seg008/seg006
Sets:
  dungeon/palace: env images (res 201..), dungeon_wall/palace_wall (res 361..), objects (PRINCE 151..173),
  sword (PRINCE 701..), kid (401..), guard/fat/skel/vizier/shadow (751..), pv (801..), font (1033..)
  title (TITLE.DAT res 41-45, 51-55): build_title(), its own format for PRES (M7 step 6): maskless 4-plane full
  screens, 1-bpp story texts, a mask only for the transparent logo (res 54)
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from popdata import kid_post, POTION_FRAM_BUBB, CHOMPER_FRAM1, ImageSet, DatImageSet, DATA, DOSDIR, TILE_TABLE, EGA2MZ, PALACE_EGA_MAP, palace_env_post, palace_wall_post
from datfile import DatFile
OUT = os.path.join(HERE, '..', 'build', 'assets')
EGA = os.path.isdir(DOSDIR) and not os.environ.get('POP_VGA_ASSETS')   # EGA DAT art when the DOS files are present

SETS = [  # name, folder, first res, id range, mask plane?, sprite colour rule
    ('dungeon', 'VDUNGEON', 200, range(1, 160), True, False),
    ('palace', 'VPALACE', 200, range(1, 160), True, False),
    ('dungeon_wall', 'VDUNGEON', 360, range(1, 18), True, False),
    ('palace_wall', 'VPALACE', 360, range(1, 18), True, False),
    ('objects', 'PRINCE', 150, range(1, 24), True, False),
    ('sword', 'PRINCE', 700, range(1, 35), False, True),
    ('kid', 'KID', 400, range(1, 220), False, True),
    ('guard', 'GUARD', 750, range(1, 35), False, True),
    ('fat', 'FAT', 750, range(1, 35), False, True),
    ('skel', 'SKEL', 750, range(1, 35), False, True),
    ('vizier', 'VIZIER', 750, range(1, 35), False, True),
    ('shadow', 'SHADOW', 750, range(1, 35), False, True),
    ('guard_palace', 'GUARD', 750, range(1, 35), False, True),
    ('pv', 'PV', 800, range(1, 200), True, False),
    ('font', 'font', 1032, range(1, 100), True, False),
]

def planar_from_rows(w, h, rows, want_mask, sprite):
    wb = (w + 7) // 8
    planes = [bytearray(wb * h) for _ in range(4)]; mask = bytearray(wb * h)
    for y in range(h):
        for x in range(w):
            c = rows[y][x]
            if c < 0: continue
            if sprite and c == 0: c = 8        # the Z80 derives sprite masks from colour != 0
            bit = 1 << (x & 7); o = y * wb + (x >> 3)
            mask[o] |= bit
            for p in range(4):
                if c & (1 << p): planes[p][o] |= bit
    # the mask plane is stored inverted (1 = keep the background): the Z80 ANDs it in directly
    return wb, (bytes(b ^ 0xFF for b in mask) if want_mask else b'') + b''.join(bytes(p) for p in planes)

EGA_SETS = {  # name -> (DAT, first res, palette DAT for the colour table or None)
    'dungeon': ('EDUNGEON', 200, None), 'palace': ('EPALACE', 200, None),
    'dungeon_wall': ('EDUNGEON', 360, None), 'palace_wall': ('EPALACE', 360, None),
    'objects': ('PRINCE', 150, None), 'sword': ('PRINCE', 700, None), 'kid': ('KID', 400, None),
    'guard': ('GUARD', 750, 'GUARD2'), 'guard_palace': ('GUARD', 750, 'GUARD1'),
    'fat': ('FAT', 750, None), 'skel': ('SKEL', 750, None), 'vizier': ('VIZIER', 750, None),
    'shadow': ('SHADOW', 750, None), 'pv': ('PV', 800, None), 'title': ('TITLE', 40, None),
}

def ega_set(name, sprite):
    dat, first, paldat = EGA_SETS[name]
    if name == 'palace': iset = DatImageSet(dat, first, ega_map=PALACE_EGA_MAP, post=palace_env_post)
    elif name == 'palace_wall': iset = DatImageSet(dat, first, ega_map=PALACE_EGA_MAP, post=palace_wall_post)
    elif name == 'kid': iset = DatImageSet(dat, first, sprite=sprite, post=kid_post)
    else: iset = DatImageSet(dat, first, sprite=sprite)
    if paldat:
        r = DatFile(os.path.join(DOSDIR, paldat + '.DAT')).resource(750)
        tab = [v for b in r[68:76] for v in (b >> 4, b & 15)]
        iset.ega_tab = tab
        iset.lut = [-1] + [EGA2MZ[0 if tab[i] == 13 else tab[i]] for i in range(1, 16)]
        if sprite: iset.lut = [-1] + [(c or 8) for c in iset.lut[1:]]
        iset.cache = {}
    return iset

CHTAB_OF_SET = {'dungeon': 6, 'palace': 6, 'dungeon_wall': 7, 'palace_wall': 7, 'objects': 1}
# Pre-shifted variants needed by the room renderer: every (chtab, id) drawn at a sub-byte x offset, for every
# shift it can take (wall marks land on random offsets; the others are fixed xl values in popdata.py, over all
# animation frames). Keyed (chtab, id) -> list of shifts; build/assets/shift_variants.json may add more.
SHIFT_VARIANTS = {}
def _sv_add(ch, i, shifts):
    if i: SHIFT_VARIANTS.setdefault((ch, i), []).extend(x for x in shifts if x and x not in SHIFT_VARIANTS.get((ch, i), []))
for _i in range(11, 18): _sv_add(7, _i, range(1, 8))                     # wall marks (left_mark/right_mark)
_sv_add(1, 23, [1])                                                     # potion back
for _i in POTION_FRAM_BUBB: _sv_add(1, _i, [1])                          # potion bubble frames
for _n in CHOMPER_FRAM1: _sv_add(6, _n + 114, [4]); _sv_add(6, _n + 119, [4])   # chomper blood (back, fore)
for _i in (12, 13, 14, 15): _sv_add(1, _i, [6])                          # potion fore (dungeon, +2 palace)
_sv = os.path.join(OUT, 'shift_variants.json')
if os.path.exists(_sv):
    for k, v in json.load(open(_sv)).items():
        ch, i = (int(t) for t in k.split(',')); _sv_add(ch, i, v)

def build_set(name, folder, first, ids, want_mask, sprite):
    iset = ega_set(name, sprite) if (EGA and name in EGA_SETS) else ImageSet(folder, first, sprite=sprite)
    pack = bytearray(); dirb = bytearray(); info = {}; variants = []
    def add_entry(i, w, h, rows, tag, x0=0):
        # x0..x0+w is the image's pixel extent inside the wb*8 box (shift variants are padded on the left);
        # copy-mode drawing must leave the pixels outside the extent alone: byte 6/7 = extent mask of the
        # first/last byte column, dir flag bit 1 = some column is partial.
        wb, data = planar_from_rows(w + x0, h, rows, want_mask, sprite)
        def colmask(c): return sum(1 << b for b in range(8) if x0 <= c * 8 + b < x0 + w)
        lm, rm = colmask(0), colmask(wb - 1)
        flags = (1 if want_mask else 0) | (2 if (lm & rm) != 255 else 0)
        if (len(pack) & 0xFFFF) + len(data) > 0x10000:       # never let an image straddle a 64 KB RAM-disk page
            pack.extend(b'\0' * (0x10000 - (len(pack) & 0xFFFF)))
        off = len(pack)
        while len(dirb) < i * 8: dirb.extend(b'\0' * 8)
        dirb.extend(bytes([off >> 16, (off >> 8) & 255, off & 255, wb, h, flags, lm, rm]))
        pack.extend(data); info[i] = {'res': tag, 'w': w + x0, 'h': h, 'wbytes': wb, 'offset': off}
    for i in ids:
        img = iset.get(i)
        if img is None: continue
        w, h, rows = img
        add_entry(i, w, h, rows, first + i)
    # pre-shifted variants (the Z80 room renderer only draws byte-aligned): image shifted right by s pixels
    ch = CHTAB_OF_SET.get(name)
    nextid = max(ids) + 1
    for i in ids:                       # ids are assigned in a fixed order so every set agrees with shift_tab
        for sft in SHIFT_VARIANTS.get((ch, i), []):
            vid = nextid; nextid += 1
            variants.append((i, sft, vid))
            img = iset.get(i)
            if img is None: continue    # image empty in this set: the directory entry stays empty
            w, h, rows = img
            srows = [[-1] * sft + row for row in rows]
            add_entry(vid, w, h, srows, 'shift %d of %d' % (sft, i), x0=sft)
    for ext, blob in (('pack', pack), ('dir', dirb)):
        open(os.path.join(OUT, '%s.%s' % (name, ext)), 'wb').write(blob)
    json.dump({'set': folder, 'first': first, 'source': 'ega-dat' if isinstance(iset, DatImageSet) else 'sdlpop-png',
               'images': info, 'variants': variants,
               'colours': {('%d,%d,%d' % k if isinstance(k, tuple) else str(k)): v for k, v in iset.cmap.items()}},
              open(os.path.join(OUT, name + '.json'), 'w'), indent=1)
    ALL_VARIANTS[name] = variants; ALL_INFO[name] = info
    return len(pack), len(info)
ALL_VARIANTS = {}; ALL_INFO = {}

def build_levels():
    if EGA:
        d = DatFile(os.path.join(DOSDIR, 'LEVELS.DAT'))
        for n in range(0, 15):
            if 2000 + n in d.table: open(os.path.join(OUT, 'level%02d.bin' % n), 'wb').write(d.resource(2000 + n))
        return
    for n in range(0, 15):
        src = os.path.join(DATA, 'LEVELS', 'res%d.bin' % (2000 + n))
        if os.path.exists(src):
            open(os.path.join(OUT, 'level%02d.bin' % n), 'wb').write(open(src, 'rb').read())

def frame_tables():
    """frame_table_kid / frame_tbl_guard / frame_tbl_cuts / sword_tbl parsed from SDLPoP seg006.c."""
    import re
    src = open(os.path.join(DATA, '..', 'src', 'seg006.c')).read()
    def table(name):
        m = re.search(r'const frame_type %s\[\] = \{(.*?)\n\};' % name, src, re.S)
        rows = re.findall(r'\{\s*(\d+),\s*(0x[0-9A-Fa-f]+)\|\s*(\d+),\s*(-?\d+),\s*(-?\d+),\s*(0x[0-9A-Fa-f]+)\|\s*(\d+)\}', m.group(1))
        return [(int(a), int(b, 16) | int(c), int(d), int(e), int(f, 16) | int(g)) for a, b, c, d, e, f, g in rows]
    m = re.search(r'const sword_table_type sword_tbl\[\] = \{(.*?)\n\};', src, re.S)
    sword = [tuple(int(v) for v in r) for r in re.findall(r'\{\s*(\d+),\s*(-?\d+),\s*(-?\d+)\}', m.group(1))]
    return {'kid': table('frame_table_kid'), 'guard': table('frame_tbl_guard'), 'cuts': table('frame_tbl_cuts'), 'sword': sword}

# logic.bin (RAM-disk page 6 at 0xD000, game.asm RD_LOGIC_*): name -> (offset, room)
LOGIC_LAYOUT = {'seqtbl': (0x000, 0xA00), 'kid': (0xA00, 0x500), 'guard': (0xF00, 0x100), 'kid_width': (0x1000, 0x100),
                'guard_wh': (0x1100, 0x180)}
LOGIC_SIZE = 0x1280

def build_tables():
    ft = frame_tables()
    json.dump(ft, open(os.path.join(OUT, 'frames.json'), 'w'))
    lines = ['; generated by tools/build_assets.py from SDLPoP seg008.c / seg006.c - do not edit',
             '; tile_table: base_id, floor_left, base_y, right_id, floor_right, right_y, stripe_id, topright_id, bottom_id, fore_id, fore_x, fore_y',
             'tile_table:']
    for i, t in enumerate(TILE_TABLE):
        lines.append('                db      ' + ', '.join(str(v & 255) for v in t) + '   ; %d' % i)
    # the logic tables live in the RAM disk (logic.bin, LOGIC_LAYOUT): the sequence table, the kid's and the guard's
    # frame tables (image, sword (0xC0 chtab | 0x3F sword image), dx, dy, flags (0x1F weight x, 0x20 thin, 0x40 needs
    # floor, 0x80 odd pixel)); the cutscene frame table is not used by the game
    logic = bytearray(LOGIC_SIZE)
    for name in ('kid', 'guard'):
        b = bytes(v & 255 for f in ft[name] for v in f)
        assert len(b) <= LOGIC_LAYOUT[name][1], name
        logic[LOGIC_LAYOUT[name][0]:LOGIC_LAYOUT[name][0] + len(b)] = b
    lines.append('; sword_tbl: image, dx, dy'); lines.append('sword_tbl:')
    for i, f in enumerate(ft['sword']):
        lines.append('                db      ' + ', '.join(str(v & 255) for v in f) + '   ; %d' % i)
    # small per-tile frame tables from seg008.c
    import popdata as P
    for nm in ('DOORTOP_FRAM_TOP', 'DOOR_FRAM_TOP', 'BLUELINE_FRAM1', 'BLUELINE_FRAM_Y', 'BLUELINE_FRAM3', 'DOORTOP_FRAM_BOT',
               'SPIKES_FRAM_RIGHT', 'LOOSE_FRAM_RIGHT', 'WALL_FRAM_BOTTOM', 'LOOSE_FRAM_BOTTOM', 'LOOSE_FRAM_LEFT',
               'SPIKES_FRAM_LEFT', 'POTION_FRAM_BUBB', 'CHOMPER_FRAM1', 'CHOMPER_FRAM_BOT', 'CHOMPER_FRAM_TOP',
               'CHOMPER_FRAM_Y', 'SPIKES_FRAM_FORE', 'CHOMPER_FRAM_FOR', 'WALL_FRAM_MAIN', 'DOOR_FRAM_SLICE'):
        lines.append(nm.lower() + ':')
        lines.append('                db      ' + ', '.join(str(v & 255) for v in getattr(P, nm)))
    # shifted image variants: chtab, image id, shift -> variant id (terminated by 0xff)
    # mono blit colours: EGA colour number -> MZ colour, per art set (palace env/wall sets are recoloured)
    lines.append('mono_map_dungeon:')
    lines.append('                db      ' + ', '.join(str(v) for v in EGA2MZ))
    lines.append('mono_map_palace:')
    lines.append('                db      ' + ', '.join(str(v) for v in PALACE_EGA_MAP))
    # potion bubble frames: POTION_FRAM_BUBB[f] drawn at xl = 1 -> shift variant ids (0 for frame 0)
    ov = {(i, sft): vid for (i, sft, vid) in ALL_VARIANTS['objects']}
    lines.append('; bubble_var: variant id (shift 1) of the potion bubble image for frames 0..7')
    lines.append('bubble_var:')
    lines.append('                db      ' + ', '.join(str(ov.get((i, 1), 0)) for i in POTION_FRAM_BUBB))
    lines.append('; col_of_tag: tile tag (row*10+col, 30+col for the above row) -> column')
    lines.append('col_of_tag:')
    lines.append('                db      ' + ', '.join(str(t % 10) for t in range(40)))
    # sequence table (SDLPoP seqtbl.c, dumped by build/seqdump/dump): JMP targets rebased from the DOS base
    # 0x196E to offsets into the table, so the Z80 keeps curr_seq as a plain offset
    sq = os.path.join(OUT, 'seqtbl.bin')
    if os.path.exists(sq):
        data = bytearray(open(sq, 'rb').read()); BASE = 0x196E
        LEN = {0xFB: 1, 0xFA: 1, 0xFE: 0, 0xF7: 2, 0xFF: 2, 0xFD: 0, 0xFC: 0, 0xF9: 1, 0xF8: 2, 0xF5: 0, 0xF4: 0, 0xF2: 1, 0xF1: 0, 0xF3: 1, 0xF6: 0}
        i = 0
        while i < len(data):
            op = data[i]; i += 1
            n = LEN.get(op, 0)
            if op in (0xFF, 0xF7):
                tgt = data[i] | (data[i+1] << 8); tgt -= BASE
                assert 0 <= tgt < len(data), (i, tgt)
                data[i] = tgt & 255; data[i+1] = tgt >> 8
            i += n
        open(os.path.join(OUT, 'seqtbl_z80.bin'), 'wb').write(data)
        offs = [int(l.split()[1]) for l in open(os.path.join(OUT, 'seqtbl_offsets.txt'))]
        offs[0] = 0
        assert len(data) <= LOGIC_LAYOUT['seqtbl'][1]
        logic[:len(data)] = data
        open(os.path.join(OUT, 'logic.bin'), 'wb').write(logic)
        lines.append('; seq_offsets: sequence id -> offset into seqtbl (word)')
        lines.append('seq_offsets:')
        for k in range(0, len(offs), 8):
            lines.append('                dw      ' + ', '.join(str(v & 0xffff) for v in offs[k:k+8]))
    # kid logic tables (SDLPoP data.h / seg004.c / seg006.c)
    lines.append('; x_bump: tile column + 5 -> logical x of the column (14 units per tile, screen left = 58)')
    lines.append('x_bump:')
    lines.append('                db      ' + ', '.join(str(v & 255) for v in [-12, 2, 16, 30, 44, 58, 72, 86, 100, 114, 128, 142, 156, 170, 184, 198, 212, 226, 240, 254]))
    lines.append('; y_land: row + 1 -> y of the feet standing on that row (bytes: -8, 55, 118, 181, 244)')
    lines.append('y_land:')
    lines.append('                db      ' + ', '.join(str(v & 255) for v in [-8, 55, 118, 181, 244]))
    lines.append('; tile_div_tbl / tile_mod_tbl: xpos (0..255) -> tile column (signed) and position in the tile, floor semantics')
    lines.append('tile_div_tbl:')
    for k in range(0, 256, 32): lines.append('                db      ' + ', '.join(str(((x - 58) // 14) & 255) for x in range(k, k + 32)))
    lines.append('tile_mod_tbl:')
    for k in range(0, 256, 32): lines.append('                db      ' + ', '.join(str((x - 58) % 14) for x in range(k, k + 32)))
    lines.append('; wall_dist_from_left / wall_dist_from_right: wall type (0..5) -> distance')
    lines.append('wall_dist_from_left:'); lines.append('                db      ' + ', '.join(str(v & 255) for v in [0, 10, 0, -1, 0, 0]))
    lines.append('wall_dist_from_right:'); lines.append('                db      ' + ', '.join(str(v & 255) for v in [0, 0, 10, 13, 0, 0]))
    lines.append('; tile_floor_tbl: tile type -> 1 if it is a floor; wall_type_tbl: tile type -> wall type (0 none, 1 right, 2 left, 3 chomper, 4 both)')
    nofloor = {0, 9, 12, 20, 26, 27, 28, 29}
    lines.append('tile_floor_tbl:'); lines.append('                db      ' + ', '.join('0' if t in nofloor else '1' for t in range(32)))
    wt = {4: 1, 7: 1, 12: 1, 13: 2, 18: 3, 20: 4}
    lines.append('wall_type_tbl:'); lines.append('                db      ' + ', '.join(str(wt.get(t, 0)) for t in range(32)))
    # kid width table (logic.bin 'kid_width'): frame image index (0..) -> pixel width of the kid image (for set_char_collision)
    kinfo = ALL_INFO.get('kid', {})
    maxi = max(int(k) for k in kinfo) if kinfo else 0   # info keys are image ids (int)
    ws = [kinfo.get(i + 1, kinfo.get(str(i + 1), {})).get('w', 0) for i in range(maxi)]
    assert len(ws) <= LOGIC_LAYOUT['kid_width'][1]
    logic[LOGIC_LAYOUT['kid_width'][0]:LOGIC_LAYOUT['kid_width'][0] + len(ws)] = bytes(ws)
    # guard size table (logic.bin 'guard_wh'): per guard image set (0 guard, 1 fat, 2 skel, 3 vizier, 4 shadow; kidsim
    # GUARD_IMAGES order), image index 0..GUARD_WH_N-1 -> (char_width_half = (w + 1) / 2, height) for set_char_collision of
    # chtab 5 (0, 0 = none)
    GUARD_WH_N = 34
    lines.append('GUARD_WH_N      equ     %d' % GUARD_WH_N)
    vals = []
    for gname in ('guard', 'fat', 'skel', 'vizier', 'shadow'):
        ginfo = json.load(open(os.path.join(OUT, gname + '.json')))['images']     # (as kidsim reads them)
        assert max(int(k) for k in ginfo) <= GUARD_WH_N, gname
        for i in range(GUARD_WH_N):
            e = ginfo.get(str(i + 1))
            vals += [(e['w'] + 1) // 2, e['h']] if e else [0, 0]
    assert len(vals) <= LOGIC_LAYOUT['guard_wh'][1]
    logic[LOGIC_LAYOUT['guard_wh'][0]:LOGIC_LAYOUT['guard_wh'][0] + len(vals)] = bytes(vals)
    open(os.path.join(OUT, 'logic.bin'), 'wb').write(logic)
    # level types (0 dungeon, 1 palace) for levels 0..15, and the hit point icons (kid images 217 full / 218 empty:
    # 6x5 pixels, opaque) as 4 planes x 5 row bytes (plane-major, as in the pack), bit 0 = leftmost pixel
    from popdata import LEVEL_TYPE
    lines.append('level_type_tbl:'); lines.append('                db      ' + ', '.join(str(v) for v in LEVEL_TYPE))
    kp = open(os.path.join(OUT, 'kid.pack'), 'rb').read(); kd = open(os.path.join(OUT, 'kid.dir'), 'rb').read()
    for nm, pid in (('hp_full', 217), ('hp_empty', 218)):
        e = kd[pid * 8:pid * 8 + 8]; off = (e[0] << 16) | (e[1] << 8) | e[2]; wb, h = e[3], e[4]; n = wb * h
        assert wb == 1 and h == 5, (nm, wb, h)
        vals = [kp[off + n * pl + r] for pl in range(4) for r in range(5)]
        lines.append(nm + ':'); lines.append('                db      ' + ', '.join(str(v) for v in vals))
    lines.append('; shift_tab: chtab, id, shift, variant id; end 0xff')
    lines.append('shift_tab:')
    for name, vs in ALL_VARIANTS.items():
        if name not in CHTAB_OF_SET or name.startswith('palace'): continue   # dungeon and palace sets share ids/variants
        for (i, sft, vid) in vs:
            lines.append('                db      %d, %d, %d, %d' % (CHTAB_OF_SET[name], i, sft, vid))
    lines.append('                db      0xff')
    open(os.path.join(OUT, 'tables.inc'), 'w').write('\n'.join(lines) + '\n')

# the bottom texts the game draws (game.asm text_chk, the text overlay src/m4/text.asm): their characters
TEXT_STRINGS = ('Press Button to Continue', 'TIME HAS EXPIRED!', 'MINUTES LEFT', 'SECONDS LEFT', 'LEVEL', '0123456789',
                'GAME SAVED', 'UNABLE TO SAVE GAME', 'SOUND OFF', 'SOUND ON', 'PRINCE OF PERSIA V1.0', 'GAME PAUSED')
def build_font_text():
    """font_text.inc: the glyphs of SDLPoP's font (data/font res 1000 + character, hc_font) for the characters of the
    bottom texts: per character its code, width and 7 rows (bit 0 = leftmost pixel), 0 at the end; the space is 3 px
    wide (res 1032 is an empty 3 x 1 image)."""
    from PIL import Image
    chars = sorted(set(''.join(TEXT_STRINGS)) - {' '})
    lines = ['; generated by tools/build_assets.py (build_font_text): glyphs of the bottom texts (do not edit)',
             'TXT_SPACE_W     equ     %d' % Image.open(os.path.join(DATA, 'font', 'res1032.png')).size[0], 'txt_font:']
    for ch in chars:
        im = Image.open(os.path.join(DATA, 'font', 'res%d.png' % (1000 + ord(ch))))
        w, h = im.size; px = im.load()
        assert w <= 8 and h <= 7, (ch, w, h)
        rows = [sum(1 << x for x in range(w) if px[x, y]) if y < h else 0 for y in range(7)]
        lines.append('                db      %d, %d, %s' % (ord(ch), w, ', '.join(str(r) for r in rows)))
    lines.append('                db      0')
    open(os.path.join(OUT, 'font_text.inc'), 'w').write('\n'.join(lines) + '\n')

# M7 step 6: the title art for PRES (src/pres/pres.asm), drawn as SDLPoP's full_image table (data.h) says: image (res),
# its chtab's palette resource (res 40: the story frame and texts, res 50: the title; they differ in entry 14), the
# position (x, y), the blitter: 'copy' (blitters_0_no_transp: every pixel of the w x h box, index 0 black), 'transp'
# (blitters_10h_transp: index 0 transparent) or 'mono' (a 1-bpp text drawn white: blitters_white, colour 15 PSET).
# Checked against DOSBox's EGA title (docs/m7-design.md §15): the EGA credits (res 45, 143 rows) are drawn at y 23.
TITLE_IMAGES = ((51, 50, 0, 0, 'copy'), (52, 50, 96, 106, 'copy'), (53, 50, 96, 122, 'copy'), (54, 50, 24, 107, 'transp'),
                (55, 50, 48, 184, 'copy'), (41, 40, 0, 0, 'copy'), (42, 40, 24, 25, 'mono'), (43, 40, 24, 25, 'mono'),
                (44, 40, 24, 25, 'mono'), (45, 40, 24, 23, 'mono'), (46, 40, 0, 0, 'copy'))     # (res 45: SDLPoP's y 26 is VGA's; DOSBox EGA 23)

FRAME_RED = 46

def title_image(res):
    """(w, h, rows of MZ colours (-1 = transparent: index 0 of a 4-bpp image, a 0 bit of a 1-bpp one)) of a TITLE.DAT
    image at its place on the screen. EGA colours from the chtab's palette resource: its four 16-entry EGA tables
    (bytes 68-99, a nibble each) are a 2 x 2 dither, table (y & 1) * 2 + (x & 1) at screen pixel (x, y) (found against
    DOSBox's EGA title, docs/m7-design.md §15: indices 3, 6, 8 and 10 alternate two colours in a checkerboard; the
    other DATs' tables are equal but for PV.DAT's room and bed); EGA 13 shows as black (popdata.DatImageSet)."""
    from datfile import DatFile
    first = next(p for r, p, *_ in TITLE_IMAGES if r == res)
    x0, y0 = next((x, y) for r, _, x, y, _ in TITLE_IMAGES if r == res)
    d = DatFile(os.path.join(DOSDIR, 'TITLE.DAT'))
    pal = d.resource(first)
    tabs = [[v for b in pal[68 + 8 * t:76 + 8 * t] for v in (b >> 4, b & 15)] for t in range(4)]
    if res == FRAME_RED:       # STORY_FRAME for the hail screen: load_title_images(0): its background (index 14) red, not blue
        for t in tabs: t[14] = 4
    w, h, rows, depth = d.image(41 if res == FRAME_RED else res)
    out = []
    for y in range(h):
        if depth == 1: out.append([15 if v else -1 for v in rows[y]]); continue
        r = []
        for x, v in enumerate(rows[y]):
            e = tabs[((y0 + y) & 1) * 2 + ((x0 + x) & 1)][v]
            r.append(-1 if v == 0 else EGA2MZ[0 if e == 13 else e])
        out.append(r)
    return w, h, out

def build_title():
    """title.pack / title.dir / title.json (PRES's title art; mkgamedisk.py cuts it into PZ bands for POP800.PRS).
    Image data: 'copy' 4 planes (wb x h each, plane p = bit p of the MZ colour), 'transp' the inverted mask (1 = keep
    the background) then the 4 planes, 'mono' one plane (1 = colour 15); bit 0 = the leftmost pixel. Directory: per
    id = res - 40 8 bytes as the other packs (offset 24-bit, wbytes, h, flags: bit 0 mask, bit 1 partial edge column,
    bit 2 mono; the extent masks of the first and last byte column: a box wider than the image leaves those pixels)."""
    pack = bytearray(); dirb = bytearray(8 * 16); info = {}
    for res, palres, x, y, mode in TITLE_IMAGES:
        w, h, rows = title_image(res)
        assert x % 8 == 0 and x + w <= 320 and y + h <= 200, res
        wb = (w + 7) // 8
        P = [bytearray(wb * h) for _ in range(4)]; M = bytearray(wb * h)
        for yy in range(h):
            for xx in range(w):
                c = rows[yy][xx]
                if c < 0:
                    if mode != 'copy': continue
                    c = 0
                bit = 1 << (xx & 7); o = yy * wb + (xx >> 3)
                M[o] |= bit
                for pl in range(4):
                    if c & (1 << pl): P[pl][o] |= bit
        if mode == 'mono': data = bytes(M)
        elif mode == 'transp': data = bytes(b ^ 0xFF for b in M) + b''.join(bytes(q) for q in P)
        else: data = b''.join(bytes(q) for q in P)
        rm = (1 << (w - (wb - 1) * 8)) - 1
        flags = (1 if mode == 'transp' else 0) | (2 if rm != 255 else 0) | (4 if mode == 'mono' else 0)
        off = len(pack); i = res - 40
        dirb[i * 8:i * 8 + 8] = bytes([off >> 16, (off >> 8) & 255, off & 255, wb, h, flags, 255, rm])
        pack += data
        info[res] = {'w': w, 'h': h, 'wbytes': wb, 'offset': off, 'x': x, 'y': y, 'mode': mode, 'palette': palres,
                     'flags': flags, 'lm': 255, 'rm': rm, 'size': len(data)}
    for ext, blob in (('pack', pack), ('dir', dirb)):
        open(os.path.join(OUT, 'title.%s' % ext), 'wb').write(blob)
    json.dump({'set': 'TITLE', 'source': 'ega-dat', 'images': info}, open(os.path.join(OUT, 'title.json'), 'w'), indent=1)
    # step f's two waits (PRES's step table; tools/titleref.py): SDLPoP's f waits until the DOS music 54 ends (the ticks
    # model); PRES's title theme (the Master System's, 11.40 s) plays exactly TITLE_PASSES times instead: f's first wait
    # ends with its last pass (then OP_MSTOP), the second F_EARLIER ticks before SDLPoP's f ends (a deviation)
    import titleref as T
    f = dict((st, t) for st, _, t in T.STEPS)['f']
    open(os.path.join(OUT, 'title.inc'), 'w').write(
        '; generated by tools/build_assets.py (build_title) - do not edit\n'
        '; step f: SDLPoP waits until music 54 (kidsim SOUND_SECONDS %.3f s) ends at tick %d from a; PRES plays its title\n'
        '; theme (%d frames a pass) %d times from a (tick %d): stopped at tick %d, f ends %d ticks before SDLPoP\'s (%d from a)\n'
        'TITLE_F_MUSIC   equ     %-15d ; f: until the title theme\'s pass %d ends (then OP_MSTOP)\n'
        'TITLE_F_REST    equ     %-15d ; f: the rest, silent\n' % (
            T.kidsim.SOUND_SECONDS[T.MUSIC], T.music_end_ticks(), T.title_frames(), T.TITLE_PASSES, T.FADE_TICKS,
            T.music_stop_tick(), T.F_EARLIER, T.AF_TICKS, T.F_MUSIC, T.TITLE_PASSES, f - T.F_MUSIC))
    return len(pack), len(info)

def main():
    os.makedirs(OUT, exist_ok=True)
    if sys.argv[1:] == ['--font-text']: build_font_text(); return
    if sys.argv[1:] == ['--title']: print('title %d bytes, %d images' % build_title()); return
    print('art source:', 'EGA DAT files in external/dos' if EGA else 'SDLPoP VGA PNGs')
    total = 0
    for s in SETS:
        size, n = build_set(*s); total += size
        print('%-14s %4d images %7d bytes' % (s[0], n, size))
    if EGA:
        size, n = build_title(); total += size
        print('%-14s %4d images %7d bytes' % ('title', n, size))
    build_levels(); build_tables(); build_font_text()
    import sndconv; sndconv.build()                 # the PSG sound bank (M7)
    print('total pack bytes', total)

if __name__ == '__main__': main()
