#!/usr/bin/env python3
"""Build the bootable game disk (build/pop800.dsk): an FSMZ (MZ-800 Disk BASIC) disk, 40 cylinders x 2 sides x 16 x 256 B,
whose IPLPRO bootstrap is the floppy loader (src/boot/boot.asm) and whose files POP800.D1, POP800.D2, ... hold the
compressed data stream the loader decompresses into the RAM disk and main RAM.

The data is exactly what tests/m4_game.py setup() writes (the RAM-disk packs, the six guard sets, the directories,
the level blueprints, logic.bin, the code overlays build/m4ovl.bin) plus the program image build/m4game.bin
(0x1200-0x7FFF and block 2 0xC000-block2_end); tests/m5_boot.py checks the result against setup() byte by byte.

Stream: a sequence of records. Record = kind (1 byte), dest address (2), raw length (2), payload length (2),
progress bar width after this record (1, in bytes of the 32-byte bar), payload.
  kind bit 7: payload stored (else PZ-compressed, tools/pzpack.py), bit 6: main RAM destination (else the RAM disk,
  page = bits 3-0); 0xFE: the rest of this file is padding, continue with the next file; 0xFF: end of the stream.
RAM-disk records come first: the loader decompresses them into a buffer at 0x2000 (16 KB at most, never across a
64 KB page) and copies the buffer to the RAM disk; main-RAM records (8 KB blocks) are decompressed in place, last.
Every block is independent (back-references stay inside it).
The disk also holds POP800.SAV, one block (256 bytes, all 0 = no saved game) that the game's save overlay
(src/m4/save.asm: Ctrl+G) overwrites in place with the saved position (magic "POP8", version, SDLPoP's PRINCE.SAV
fields as 16-bit words, checksum); it is preallocated here so the directory and the free-block map stay right.
M7 (the launcher, src/boot/launch.inc): the program is no longer loaded into main RAM by the boot. Its records (the
same main-RAM records, PZ) form a second record stream, the GAME image, that the D files put into the RAM disk as
data (stored RAM-disk records): from GAME_RD_PAGE:GAME_RD_ADDR (page 3 0xA000) on, continued by a record 0xFD page,
address (3 bytes) at page 4 0xD400 when the first piece is full; the launcher decompresses it into main RAM at every
swap back to the game. The boot copies itself (the launcher) to the RAM disk (LN_RD_PAGE:LN_RD_ADDR) and writes the
handoff block (HO_RD_PAGE:HO_RD_ADDR); both areas are reserved here, not written by the stream.
POP800.PRS: the presentation program's file. Block 0 = the index: entry count (word), then per entry its first block
(word, counted from the file's start) and its block count (word); each entry is a record stream (main-RAM records only,
ended by 0xFF, padded to whole blocks) the launcher loads (LN_PRS_LOAD), numbered as pres.asm's PRS_* say: entry 0 =
PRES (build/pres.bin, 0x2000), the presentation's sound bank (build/assets/sound_pres.bin at SBANK_TMP; PRES copies it
to the torch cache), the title art (title_entries: stored PZ bands and PRES's art index, one entry per image group), the
cutscenes (tools/cutart.py: the room entry with the engine, then one entry per scene).
The file outgrew one FSMZ file (0xFF00 bytes): its tail is the file POP800.PR2, which must be the next blocks on the disk
(asserted from the directory): the launcher reads an entry as blocks counted from POP800.PRS's first block, so an entry
may lie in either file or across both, and the launcher needs no change.
usage: mkgamedisk.py <out.dsk> <boot.mzf> [--mzdisk DIR]"""
import hashlib, json, multiprocessing, os, re, struct, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import pzpack, cutart
B = os.path.join(ROOT, 'build'); A = os.path.join(B, 'assets')
CACHE = os.path.join(B, 'pzcache')
RD_BLOCK = 16384            # RAM-disk records: output buffer 0x2000-0x5FFF, input 0x6000-0x9FFF
MAIN_BLOCK = 8192           # main-RAM records: input buffer 0x8000-0x9FFF
FILE_MAX = 0xFF00           # MZF size field is 16 bits; files are padded to whole 256-byte blocks
BAR = 32                    # progress bar width in bytes
NPAGES = 8
SAVE_NAME = 'POP800.SAV'  # the saved game (src/m4/save.asm)
PRS_NAME = 'POP800.PRS'   # the presentation program and its scenes (M7)
PR2_NAME = 'POP800.PR2'   # (M7 step 7) POP800.PRS's continuation: the next blocks on the disk (see prs_file)
# the GAME image's pieces in the RAM disk: (page, start, end); the first must be launch.inc's GAME_RD_PAGE:GAME_RD_ADDR.
# Pages 3 and 4 hold only fixed art packs (the kid, the palace environment) whatever M8a does with the guard sets.
GAME_SEGS = ((3, 0xA000, 0x10000), (4, 0xD400, 0x10000))
if os.environ.get('MKGAMEDISK_SPLIT'):      # (test hook: end the first piece early, so the image continues in page 4)
    GAME_SEGS = ((3, 0xA000, int(os.environ['MKGAMEDISK_SPLIT'], 16)),) + GAME_SEGS[1:]

# the guard sets and directories as tests/m4_game.py setup() places them (GUARD_SETS there is the source of truth;
# tests/m5_boot.py compares the result with setup()'s)
GUARD_SETS = (('guard', 6, 0x3000), ('fat', 7, 0x0000), ('skel', 7, 0x4C40), ('vizier', 7, 0x8D80), ('shadow', 0, 0xA800),
              ('guard_palace', 6, 0x8000))
DIRS = (('dungeon.dir', 0, 0, 0xD100, 0x700), ('dungeon_wall.dir', 1, 0x8000, 0xD800, 0x300),
        ('palace.dir', 4, 0, 0xDB00, 0x700), ('palace_wall.dir', 5, 0, 0xE200, 0x300),
        ('objects.dir', 1, 0xC000, 0xE500, 0x200), ('kid.dir', 2, 0, 0xE700, 0x6E0),
        ('sword.dir', 1, 0xD000, 0xEE00, 0x118))

def syms(path):
    d = {}
    for line in open(path):
        m = re.match(r'(\S+)\s+EQU\s+([0-9A-Fa-f]+)H', line.strip())
        if m: d[m.group(1)] = int(m.group(2), 16)
    return d

def rebase_dir(dirb, page, base):
    out = bytearray(dirb)
    for i in range(0, len(out), 8):
        if any(out[i:i+5]):
            off = ((out[i] << 16) | (out[i+1] << 8) | out[i+2]) + base
            out[i] = page + (off >> 16); out[i+1] = (off >> 8) & 255; out[i+2] = off & 255
    return bytes(out)

def ramdisk_writes():
    """[(page, address, bytes)] in setup()'s order"""
    rd = lambda n: open(os.path.join(A, n), 'rb').read()
    w = [(0, 0, rd('dungeon.pack')), (1, 0x8000, rd('dungeon_wall.pack')), (1, 0xC000, rd('objects.pack')),
         (1, 0xD000, rd('sword.pack')), (2, 0, rd('kid.pack')), (4, 0, rd('palace.pack')), (5, 0, rd('palace_wall.pack'))]
    lvf = lambda n: os.path.join(A, 'level%02d.bin' % n)
    levels = b''.join((open(lvf(n), 'rb').read()[:2305] if os.path.exists(lvf(n)) else b'').ljust(2305, b'\0') for n in range(16))
    w.append((5, 0x4000, levels))
    w.append((6, 0xD000, rd('logic.bin')))
    gdirs = bytearray(6 * 0x120)
    for i, (name, page, base) in enumerate(GUARD_SETS):
        w.append((page, base, rd(name + '.pack')))
        d = rebase_dir(rd(name + '.dir'), page, base); assert len(d) <= 0x120, name
        gdirs[i * 0x120:i * 0x120 + len(d)] = d
    w.append((5, 0x3400, bytes(gdirs)))
    dirs = bytearray(0xEF18 - 0xD100)
    for name, page, base, at, size in DIRS:
        d = rebase_dir(rd(name), page, base); assert len(d) <= size, name
        dirs[at - 0xD100:at - 0xD100 + len(d)] = d
    w.append((5, 0xD100, bytes(dirs)))
    S = syms(os.path.join(B, 'm4game.sym'))
    w.append((S['OVL_RD_PAGE'], S['OVL_RD_TAB'], open(os.path.join(B, 'm4ovl.bin'), 'rb').read()))
    w.append((S['SB_PAGE'], S['SB_ADDR'], rd('sound.bin')))          # the PSG sound bank (M7, tools/sndconv.py)
    w.append((S['FS_MPAGE'], S['FS_MADDR'], rd('fstore_masks.bin')))  # the frame store's keys (tools/fstore.py)
    return w

def launcher_syms():
    return syms(os.path.join(B, 'boot.sym'))

def reserved():
    """[(page, address, length, what)]: the RAM-disk areas the boot / launcher / game write besides the stream's
    setup() data: the launcher's copy, the handoff block, the GAME image's pieces (as used)"""
    L = launcher_syms()
    out = [(L['LN_RD_PAGE'], L['LN_RD_ADDR'], L['LN_MAX'], 'launcher'), (L['HO_RD_PAGE'], L['HO_RD_ADDR'], L['HO_SIZE'], 'handoff')]
    for page, addr, data in game_image_writes():
        out.append((page, addr, len(data), 'game image'))
    return out

def records(blks, bar=None):
    """the record bytes of [(kind, address, raw)] (kind 0x40 = main RAM, else the RAM-disk page); bar(i) = the progress
    bar after record i"""
    with multiprocessing.Pool() as pool: packed = pool.map(pack_cached, [b[2] for b in blks])
    out = []
    for i, ((kind, addr, raw), (pz, payload)) in enumerate(zip(blks, packed)):
        if kind & 0x40: assert len(payload) <= MAIN_BLOCK
        else: assert len(payload) <= RD_BLOCK
        out.append(bytes([kind | (0 if pz else 0x80)]) + struct.pack('<HHH', addr, len(raw), len(payload)) +
                   bytes([bar(i) if bar else 0]) + payload)
    return out

def main_blocks(parts):
    """[(0x40, address, raw)]: main-RAM records of 8 KB at most"""
    return [(0x40, addr + o, data[o:o + MAIN_BLOCK]) for addr, data in parts for o in range(0, len(data), MAIN_BLOCK)]

_GAME = None
def game_image_writes():
    """[(page, address, bytes)]: the GAME image stream (the program's main-RAM records) in its RAM-disk pieces"""
    global _GAME
    if _GAME is not None: return _GAME
    L = launcher_syms(); assert (GAME_SEGS[0][0], GAME_SEGS[0][1]) == (L['GAME_RD_PAGE'], L['GAME_RD_ADDR']), 'launch.inc'
    os.makedirs(CACHE, exist_ok=True)
    recs = records(main_blocks(program_parts()))
    segs = list(GAME_SEGS); page, at, end = segs.pop(0); cur = bytearray(); out = []
    for r in recs:
        if at + len(cur) + len(r) + 4 > end:          # (room for the 0xFD record after it)
            page2, at2, end2 = segs.pop(0)
            cur += bytes([0xFD, page2, at2 & 255, at2 >> 8])
            out.append((page, at, bytes(cur))); page, at, end, cur = page2, at2, end2, bytearray()
        cur += r
    cur.append(0xFF); assert at + len(cur) <= end
    out.append((page, at, bytes(cur)))
    _GAME = out
    return out

def ramdisk_image(game=True):
    """(image of pages 0..NPAGES-1, mask of written bytes): setup()'s data and (game) the GAME image"""
    img = bytearray(NPAGES * 65536); mask = bytearray(NPAGES * 65536)
    for page, addr, data in ramdisk_writes() + (game_image_writes() if game else []):
        a = page * 65536 + addr; assert a + len(data) <= len(img)   # (the kid pack spans pages 2-3)
        assert not any(mask[a:a + len(data)]), ('RAM-disk writes overlap', page, hex(addr))
        img[a:a + len(data)] = data; mask[a:a + len(data)] = b'\1' * len(data)
    L = launcher_syms()
    for page, addr, n, what in reserved()[:2]:
        a = page * 65536 + addr; assert not any(mask[a:a + n]), (what, 'overlaps the data')
    return img, mask

def program_parts():
    """[(address, bytes)]: main RAM 0x1200-0x7FFF and block 2 0xC000-block2_end from build/m4game.bin (loaded at 0x1200)"""
    body = open(os.path.join(B, 'm4game.bin'), 'rb').read()
    at = lambda a, b: body[a - 0x1200:b - 0x1200]
    end2 = 0x1200 + len(body); assert end2 <= 0xEC00, hex(end2)
    return [(0x1200, at(0x1200, 0x8000).ljust(0x8000 - 0x1200, b'\0')), (0xC000, at(0xC000, end2))]

def blocks():
    """[(kind, address, raw bytes)]"""
    img, mask = ramdisk_image(); out = []
    i = 0; n = len(img)
    while i < n:
        if not mask[i]: i += 1; continue
        j = i
        while j < n and mask[j] and j - i < RD_BLOCK and (j == i or j % 65536): j += 1
        out.append((i >> 16, i & 0xFFFF, bytes(img[i:j]))); i = j
    return out

def pack_cached(data):
    key = hashlib.sha1(data).hexdigest(); path = os.path.join(CACHE, key)
    if os.path.exists(path):
        b = open(path, 'rb').read(); return b[0], b[1:]
    kind, payload = pzpack.pack_block(data)
    if kind:
        r, used = pzpack.decompress(payload); assert r == data and used == len(payload), 'PZ round trip failed'
    with open(path + '.tmp', 'wb') as f: f.write(bytes([kind]) + payload)
    os.replace(path + '.tmp', path)
    return kind, payload

def build_stream():
    os.makedirs(CACHE, exist_ok=True)
    blks = blocks()
    total_raw = sum(len(b[2]) for b in blks); done = [0]
    def bar(i):
        done[0] += len(blks[i][2]); return done[0] * BAR // total_raw
    recs = records(blks, bar)
    files = [bytearray()]; stats = {'raw': total_raw, 'packed': 0, 'records': len(blks), 'stored': 0}
    for rec in recs:
        if rec[0] & 0x80: stats['stored'] += 1
        stats['packed'] += len(rec) - 8
        if len(files[-1]) + len(rec) + 1 > FILE_MAX:
            files[-1].append(0xFE); files.append(bytearray())
        files[-1] += rec
    files[-1].append(0xFF)
    files = [bytes(f).ljust((len(f) + 255) & ~255, b'\0') for f in files]
    stats['stream'] = sum(len(f) for f in files)
    return files, stats

# the title art: PRES's art slots (pres.asm SLOT_*) -> TITLE.DAT res, and the POP800.PRS entries holding them (M7 steps 6, 8)
TITLE_SLOTS = (('SLOT_MAIN', 51), ('SLOT_PRESENTS', 52), ('SLOT_GAME', 53), ('SLOT_POP', 54), ('SLOT_MECHNER', 55),
               ('SLOT_FRAME', 41), ('SLOT_CREDITS', 45), ('SLOT_ABSENCE', 42), ('SLOT_MARRY', 43), ('SLOT_HAIL', 44), ('SLOT_FRAMER', 46))
TITLE_ENTRIES = (('PRS_T_MAIN', ('SLOT_MAIN',)), ('PRS_T_PG', ('SLOT_PRESENTS', 'SLOT_GAME')),
                 ('PRS_T_LOGO', ('SLOT_POP', 'SLOT_MECHNER')), ('PRS_T_FRAME', ('SLOT_FRAME',)), ('PRS_T_ABS', ('SLOT_ABSENCE',)),
                 ('PRS_T_MARRY', ('SLOT_MARRY',)), ('PRS_T_CRED', ('SLOT_CREDITS',)), ('PRS_T_HAIL', ('SLOT_HAIL',)), ('PRS_T_FRED', ('SLOT_FRAMER',)))
TITLE_TEXTS = ('SLOT_ABSENCE', 'SLOT_MARRY', 'SLOT_CREDITS', 'SLOT_HAIL')    # one place: PRES has only one of them at a time
TITLE_BAND = 8000           # a band (unpacked into PRES's DBUF) holds at most this many bytes

def title_entries(P):
    """{entry name: [(address, payload)]} and statistics. Every image of build/assets/title.pack (tools/build_assets.py
    build_title) is cut into bands of whole rows (each band: the image's blocks (mask, planes) for those rows, at most
    TITLE_BAND bytes), PZ-packed (tools/pzpack.py) and stored as it is (PRES unpacks a band when it draws it) at a fixed
    free place of PRES's main RAM, so any images PRES loads together fit; the story texts share one place. An image's
    art_idx slot (pres.asm ART_ENT bytes: byte column, row, wbytes, height, flags, lm, rm, bands, then per band its rows
    and its address) comes with its entry."""
    info = json.load(open(os.path.join(A, 'title.json')))['images']
    pack = open(os.path.join(A, 'title.pack'), 'rb').read()
    bands = []                                              # (slot name, band, rows, pz)
    ents = {}
    assert len(TITLE_SLOTS) == P['ART_SLOTS']
    for name, res in TITLE_SLOTS:
        e = info[str(res)]
        wb, h, fl = e['wbytes'], e['h'], e['flags']
        nblk = 1 if fl & 4 else 5 if fl & 1 else 4
        blk = [pack[e['offset'] + k * wb * h:e['offset'] + (k + 1) * wb * h] for k in range(nblk)]
        nb = -(-(wb * h * nblk) // TITLE_BAND); rows = -(-h // nb)
        assert nb <= P['ART_BANDS'], res
        ents[name] = bytearray([e['x'] // 8, e['y'], wb, h, fl, e['lm'], e['rm'], nb]).ljust(P['ART_ENT'], b'\0')
        for b in range(nb):
            r0, r1 = b * rows, min(h, (b + 1) * rows)
            raw = b''.join(k[r0 * wb:r1 * wb] for k in blk); assert len(raw) <= TITLE_BAND
            kind, pz = pack_cached(raw); assert kind, 'a band PZ cannot store'
            bands.append((name, b, r1 - r0, pz))
    # the free places (first fit, largest bands first; tests/m5_boot.py compares the game's main RAM only to block2_end since
    # 2026-11-01: PRES's art may stay between it and 0xEC00)
    free = [[0x1200, 0x2000], [P['end_of_pres'], 0x8000], [P['ART2_START'], P['ART2_END']]]
    addr = {}
    fixed = [t for t in bands if t[0] not in TITLE_TEXTS]; texts = [t for t in bands if t[0] in TITLE_TEXTS]
    assert all(t[1] == 0 for t in texts), 'a story text in more than one band'
    tmax = max(len(t[3]) for t in texts)
    for t in sorted(fixed + [('TEXT', 0, 0, bytes(tmax))], key=lambda t: -len(t[3])):
        place = next(f for f in free if f[1] - f[0] >= len(t[3]))
        addr[t[0], t[1]] = place[0]; place[0] += len(t[3])
    out = {}
    for ent, slots in TITLE_ENTRIES:
        recs = []
        for name in slots:
            for s, b, n, pz in bands:
                if s != name: continue
                a = addr['TEXT', 0] if s in TITLE_TEXTS else addr[s, b]
                ents[s][8 + 3 * b:11 + 3 * b] = bytes([n]) + struct.pack('<H', a)
                recs.append((a, pz))
            recs.append((P['art_idx'] + P[name] * P['ART_ENT'], bytes(ents[name])))
        out[ent] = recs
    stats = {'bands': len(bands), 'pz': sum(len(t[3]) for t in bands), 'raw': len(pack),
             'free': sum(f[1] - f[0] for f in free)}            # (left after the bands)
    return out, stats

def stored_records(recs):
    """the record bytes of [(address, payload)] as stored main-RAM records (the launcher copies them as they are)"""
    out = b''
    for a, data in recs:
        assert len(data) <= MAIN_BLOCK
        out += bytes([0xC0]) + struct.pack('<HHH', a, len(data), len(data)) + b'\0' + data
    return out

def prs_file():
    """POP800.PRS: the index block and the entries' record streams (see the docstring)"""
    pres_bin = open(os.path.join(B, 'pres.bin'), 'rb').read()
    P = syms(os.path.join(B, 'pres.sym')); start = P['PRES_START']
    pres = pres_bin[:P['end_of_pres'] - start]          # (pres.bin goes on with the cutscene engine: PRS_CROOM)
    assert start + len(pres) <= 0x8000 and start + len(pres_bin) == P['end_of_cut']
    title, tstats = title_entries(P)
    named = {'PRES': b''.join(records(main_blocks([(start, pres)])))}
    for ent, fn in (('PRS_SOUND', 'sound_pres.bin'), ('PRS_SND_B', 'sound_pres_b.bin'), ('PRS_SND_C', 'sound_pres_c.bin')):
        sbank = open(os.path.join(A, fn), 'rb').read()          # (the sound banks: tools/presbank.py, M7 step 11)
        assert len(sbank) <= P['SBANK_MAX'], 'the presentation sound bank %s outgrows the torch cache' % fn
        named[ent] = b''.join(records(main_blocks([(P['SBANK_TMP'], sbank)])))
    for name, recs in title.items(): named[name] = stored_records(recs)
    # the cutscenes (tools/cutart.py): the room entry (the engine, the room, the common sprites), the scenes
    cut, cstats = cutart.prs_entries(P, pres_bin, pack_cached)
    for name, recs in cut:
        st = b''
        for addr, data, stored in recs:
            st += stored_records([(addr, data)]) if stored else b''.join(records(main_blocks([(addr, data)])))
        named[name] = st
    tstats['cut'] = cstats
    order = sorted((k for k in named if k != 'PRES'), key=lambda k: P[k])
    assert [P[k] for k in order] == list(range(1, len(order) + 1)), 'pres.asm PRS_* and the entries differ'
    streams = [named['PRES']] + [named[k] for k in order]
    tstats['names'] = ['PRES'] + order
    streams = [st + b'\xff' for st in streams]
    streams = [st.ljust((len(st) + 255) & ~255, b'\0') for st in streams]
    index = struct.pack('<H', len(streams)); blk = 1
    for st in streams:
        index += struct.pack('<HH', blk, len(st) // 256); blk += len(st) // 256
    data = index.ljust(256, b'\0') + b''.join(streams)
    assert len(data) <= 2 * FILE_MAX, 'POP800.PRS and POP800.PR2 are full'
    return data, [len(st) for st in streams], tstats

def mzf(name, data, ftype=0x01, load=0, exec_=0):
    nm = name.encode('ascii')
    hdr = bytes([ftype]) + nm + b'\r' * (17 - len(nm)) + struct.pack('<HHH', len(data), load, exec_)
    return hdr.ljust(128, b'\0') + data

def main():
    args = sys.argv[1:]
    mzd = os.path.join(ROOT, 'external', 'mzdisk', 'build')
    if '--mzdisk' in args: i = args.index('--mzdisk'); mzd = args[i + 1]; del args[i:i + 2]
    out, boot = args
    files, st = build_stream()
    print('data stream: %d records (%d stored), %d bytes raw -> %d bytes packed (%.1f%%), %d bytes in %d files' % (
        st['records'], st['stored'], st['raw'], st['packed'], 100.0 * st['packed'] / st['raw'], st['stream'], len(files)))
    gw = game_image_writes()
    print('GAME image in the RAM disk: %d bytes (%s)' % (sum(len(d) for _, _, d in gw),
          ', '.join('page %d %04X-%04X' % (p, a, a + len(d) - 1) for p, a, d in gw)))
    prs, lens, ts = prs_file()
    print('POP800.PRS + PR2: %d bytes (index 256, entries: %s); title art: %d bands, %d bytes PZ (title.pack %d raw), %d bytes free for it in PRES' % (
          len(prs), ', '.join('%s %d' % (a, b // 256) for a, b in zip(ts['names'], lens)), ts['bands'], ts['pz'], ts['raw'], ts['free']))
    print('  cutscenes: %s' % ', '.join('%s %s' % kv for kv in ts['cut'].items()))
    if os.path.exists(out): os.remove(out)
    run = lambda *a: subprocess.run([os.path.join(mzd, a[0])] + list(a[1:]), check=True, capture_output=True, text=True).stdout
    run('mzdsk-create', out, '--format-basic', '40', '--sides', '2')
    run('mzdsk-fsmz', out, 'boot', 'put', boot)
    names = []
    for i, f in enumerate(files):
        name = 'POP800.D%d' % (i + 1); names.append(name)
        p = os.path.join(B, 'pop800_d%d.mzf' % (i + 1))
        # ftype 0x04 (BASIC data): not a machine-code file, so the monitor / BASIC will not try to run it
        open(p, 'wb').write(mzf(name, f, ftype=0x04))
        run('mzdsk-fsmz', out, 'put', p)
    names.append(SAVE_NAME)
    p = os.path.join(B, 'pop800_sav.mzf')
    open(p, 'wb').write(mzf(SAVE_NAME, bytes(256), ftype=0x04))
    run('mzdsk-fsmz', out, 'put', p)
    for name, part in ((PRS_NAME, prs[:FILE_MAX]), (PR2_NAME, prs[FILE_MAX:])):
        if not part: continue
        names.append(name)
        p = os.path.join(B, 'pop800_%s.mzf' % name[-3:].lower())
        open(p, 'wb').write(mzf(name, part, ftype=0x04))
        run('mzdsk-fsmz', out, 'put', p)
    d = json.loads(run('mzdsk-fsmz', '-o', 'json', out, 'dir'))
    fb = {f['name']: f for f in d['files']}
    if PR2_NAME in fb:                  # the launcher reads POP800.PRS's entries as blocks counted from its first one
        assert fb[PR2_NAME]['block'] == fb[PRS_NAME]['block'] + fb[PRS_NAME]['block_count'], 'POP800.PR2 must follow POP800.PRS'
    print(run('mzdsk-fsmz', out, 'boot').split('Reading bootstrap header ...')[-1].strip().replace('\n\n', '\n'))
    for f in d['files']:
        print('  %-10s block %4d, %4d blocks (%d bytes)' % (f['name'], f['block'], f['block_count'], f['size']))
    assert [f['name'] for f in d['files']] == names, d

if __name__ == '__main__':
    main()
