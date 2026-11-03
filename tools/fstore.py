#!/usr/bin/env python3
"""The frame store's fixed layout (docs/ramdisk-tiers.md "As built: step 1"): which (character, frame, mirror, shift)
keys get a pre-shifted, pre-mirrored cell buffer in RAM-disk pages 8+, and where.

The keys are chosen from the test scripts' use (assets/fstore_uses.txt: every kid and sword key the 71 scripts of
tests/m4-m7_scripts fetched, with its count; remade by `fstore.py --uses build/meas/k`, the output of
tools/fetchmodel/run_all.sh): class 1 = the most used per byte up to CLASS1_BUDGET (every card from 1 MB), class 2 =
the rest of them (cards with at least FS_TOP2 + 1 pages, i.e. 16 MB). The sizes come from the image directories, so
the layout is computed at build time from the user's game data and never committed.

The MZ's fill (src/m4/fstore.asm with the generator src/m4/fsgen.asm, the level-start overlay) walks the same masks in the same order and allocates the
same way; this tool computes the result it must produce:
  build/assets/fstore_equ.inc   the FS_* constants (the lookup's and the fill's)
  build/assets/fstore_masks.bin the two mask tables (255 ids x 16 variant bits, words) and the build id: the fill's
                                input, written to the RAM disk at FS_MPAGE:FS_MADDR by the boot and the harness
  build/assets/fstore_tab.bin   page 8 0x0000-0x77FF as the fill leaves it (the key table and the marker)
  build/assets/fstore_keys.txt  every stored key: class id chtab frame mirror shift page address size

The guard sets (docs/ramdisk-tiers.md section 13): ids FS_GID + 36 * set + frame (set = game.asm guard_type_tbl's
index, the order of tests/m4_game.py GUARD_SETS). Two layouts, filled at a level start for the level's set by the fill
overlay (src/m4/fstore.asm fs_guard):
  g 1 (class 1, rd_top FS_TOP1 up to below FS_TOP2: 1 MB): one region from class 1's end to page FS_TOP1's end, shared
      by the six sets and refilled when the set changes; per set the most used keys that fit (assets/fstore_guses.txt:
      the guards' keys the scripts fetched, with the level's set; a set's own use first, then the use pooled over all
      sets, then the other variants of the frames used), allocated in id and variant order like the kid's;
  g 2 (class 2, from FS_TOP2: 16 MB): every variant of every image of every set, each set in its own region after
      class 2 (filled at the first level with that set, then kept for the session).
  build/assets/fstore_gmasks.bin  the fill's input per layout and set (FS_GREC bytes each, g 1's six, then g 2's): the
                                36 mask words, the region's page and address (the entries' first), then padding
  build/assets/fstore_gkeys.txt   every stored guard key: g set id frame mirror shift page address size
usage: fstore.py [--uses DIR] [--guses DIR]"""
import json, os, sys, glob, collections, zlib
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
A = os.path.join(ROOT, 'build', 'assets')
USES = os.path.join(ROOT, 'assets', 'fstore_uses.txt')

FS_PAGE = 8                 # the key table's page
FS_SWORD = 220              # id = frame (kid, chtab 2) or FS_SWORD + frame (sword, chtab 0)
FS_IDS = 255
FS_GID = 255                # the guard sets' first id: FS_GID + FS_GN * set + frame
FS_GN = 36
FS_GSETS = ('guard', 'fat', 'skel', 'vizier', 'shadow', 'guard_palace')  # (game.asm guard_type_tbl's indices)
FS_GIDS = 471               # ids reserved in the table: kid 220, sword 35, six guard sets x 36
FS_TABEND = FS_GIDS * 64    # 0x75C0
FS_MARK = 0x7700            # the marker: the build id (4 bytes), the class filled (1 byte)
FS_GFLAG = 0x7705           # 6 bytes: guard set s's entries and slots are filled (cleared with the table)
FS_DATA = 0x7800            # the entries start here (page 8), then pages 9 and up
CLASS1_BUDGET = 400 * 1024  # bytes of entries (headers included) on every card from 1 MB
FS_TOP1 = 15                # rd_top from which the store is on (1 MB)
CH_SWORD, CH_KID, CH_GUARD = 0, 2, 5
FS_MPAGE, FS_MADDR = 6, 0xE400  # the masks and the build id (fstore_masks.bin) in the RAM disk (pages 0-7: every size)
FS_GMADDR = 0xE800          # the guard sets' masks (fstore_gmasks.bin), page FS_MPAGE
FS_GREC = 80                # bytes a record: 36 words, page, address (2), padding
GUSES = os.path.join(ROOT, 'assets', 'fstore_guses.txt')

def uses_from_meas(d):
    use = collections.Counter()
    for f in sorted(glob.glob(os.path.join(d, '*', 'calls.jsonl'))):
        for l in open(f):
            c = json.loads(l)
            if c['hit'] or c['chtab'] not in (CH_SWORD, CH_KID): continue
            use[(c['chtab'], c['frame'], c['mirror'], c['sh'])] += 1
    print('# the frame store\'s key use (tools/fstore.py --uses build/meas/k: tools/fetchmodel/run_all.sh over the 71 scripts')
    print('# of tests/m4-m7_scripts); chtab (2 kid, 0 sword) frame mirror shift fetches')
    for k in sorted(use): print('%d %d %d %d %d' % (k + (use[k],)))

def guses_from_meas(d):
    use = collections.Counter()
    for f in sorted(glob.glob(os.path.join(d, '*', 'calls.jsonl'))):
        for l in open(f):
            c = json.loads(l)
            if c['hit'] or c['chtab'] != CH_GUARD: continue
            use[(c['gset'], c['frame'], c['mirror'], c['sh'])] += 1
    print('# the frame store\'s guard key use (tools/fstore.py --guses build/meas/k: tools/fetchmodel/run_all.sh over the 71')
    print('# scripts of tests/m4-m7_scripts); set (game.asm guard_type_tbl order) frame mirror shift fetches')
    for k in sorted(use): print('%d %d %d %d %d' % (k + (use[k],)))

def read_guses():
    u = collections.Counter()
    for l in open(GUSES):
        if l.startswith('#') or not l.strip(): continue
        g, f, m, s, n = map(int, l.split()); u[(g, f, m, s)] = n
    return u

def alloc(start, items, last_page=None):
    """the fill's allocation (src/m4/fsgen.asm fg_put): items = (key, bytes) in fill order -> [(key, page, address)],
    the end (page, address); an entry that would cross a page starts the next one"""
    page, addr = start; out = []
    for k, n in items:
        if addr + n + 4 > 0xFFFF: page += 1; addr = 0
        out.append((k, page, addr)); addr += n + 4
    if last_page is not None and page > last_page: return None, None
    return out, (page, addr)

def guard_layout(e1, e2):
    """the guard sets' layouts g 1 (from class 1's end e1, to the end of page FS_TOP1) and g 2 (from class 2's end e2):
    {g: [(mask words, (page, address), [(id, frame, mirror, shift, page, address, bytes)])] per set}, g 2's end"""
    dirs = [open(os.path.join(A, n + '.dir'), 'rb').read() for n in FS_GSETS]
    def wh(s, f): e = dirs[s][f * 8:f * 8 + 8]; return (e[3], e[4]) if len(e) == 8 else (0, 0)
    def size(s, f): w, h = wh(s, f); return (w + 1) * 4 * h
    use = read_guses(); pool = collections.Counter(); fuse = collections.Counter()
    for (s, f, m, sh), n in use.items(): pool[(f, m, sh)] += n; fuse[(f, m)] += n; fuse[f] += n
    def order(keys):    # fill order: by id (frame) and variant
        return sorted(keys, key=lambda k: (k[0], k[1] * 8 + k[2]))
    out = {1: [], 2: []}; pos = e2
    for s in range(len(FS_GSETS)):
        imgs = [f for f in range(FS_GN) if all(wh(s, f))]
        cand = [(f, m, sh) for f in imgs for m in (0, 1) for sh in range(8)]
        assert all(k[1] in imgs for k in use if k[0] == s), 'a used guard image is empty'
        score = lambda k: (use[(s,) + k] * 1000 + pool[k] * 10 + fuse[(k[0], k[1])] / 10 + fuse[k[0]] / 1000) / (size(s, k[0]) + 4)
        chosen = []
        for k in sorted(cand, key=lambda k: (-score(k), k)):
            trial = order(chosen + [k])
            a, _ = alloc(e1, [(t, size(s, t[0])) for t in trial], FS_TOP1)
            if a is not None: chosen.append(k)
        for g, keys, start in ((1, order(chosen), e1), (2, order(cand), pos)):
            a, end = alloc(start, [(t, size(s, t[0])) for t in keys])
            m = [0] * FS_GN
            for f, mi, sh in keys: m[f] |= 1 << (mi * 8 + sh)
            gid = FS_GID + FS_GN * s
            out[g].append((m, start, [(gid + f, f, mi, sh, p, ad, size(s, f)) for ((f, mi, sh), p, ad) in a]))
            if g == 2: pos = end
    return out, pos, use

def read_uses():
    u = {}
    for l in open(USES):
        if l.startswith('#') or not l.strip(): continue
        c, f, m, s, n = map(int, l.split()); u[(c, f, m, s)] = n
    return u

def kid_id(chtab, frame): return frame if chtab == CH_KID else FS_SWORD + frame

def layout():
    dirs = {CH_KID: open(os.path.join(A, 'kid.dir'), 'rb').read(), CH_SWORD: open(os.path.join(A, 'sword.dir'), 'rb').read()}
    def wh(c, f): e = dirs[c][f * 8:f * 8 + 8]; return e[3], e[4]
    def size(k): w, h = wh(k[0], k[1]); return (w + 1) * 4 * h
    use = read_uses()
    for k in use: assert all(wh(k[0], k[1])), k
    order = sorted(use, key=lambda k: (-use[k] / (size(k) + 4), k))
    c1 = set(); spent = 0
    for k in order:
        if spent + size(k) + 4 <= CLASS1_BUDGET: c1.add(k); spent += size(k) + 4
    c2 = set(use) - c1
    masks = []
    for cls in (c1, c2):
        m = [0] * FS_IDS
        for (c, f, mi, s) in cls: m[kid_id(c, f)] |= 1 << (mi * 8 + s)
        masks.append(m)
    # the fill's allocation (src/m4/fsgen.asm fg_put): class 1 by id and variant, then class 2 from class 1's end
    # (the generator makes both classes in one pass over the ids, with class 2's pointer starting at FS_E1P:FS_E1A)
    page, addr = FS_PAGE, FS_DATA; keys = []; ends = []
    for cls, m in ((1, masks[0]), (2, masks[1])):
        for i in range(FS_IDS):
            for v in range(16):
                if not m[i] >> v & 1: continue
                c, f = (CH_KID, i) if i < FS_SWORD else (CH_SWORD, i - FS_SWORD)
                n = size((c, f, v >> 3, v & 7))
                if addr + n + 4 > 0xFFFF: page += 1; addr = 0
                keys.append((cls, i, c, f, v >> 3, v & 7, page, addr, n)); addr += n + 4
        ends.append((page, addr))
    return masks, keys, ends, use

def build_id(masks, gl):
    h = 0
    for m in masks: h = zlib.crc32(b''.join(x.to_bytes(2, 'little') for x in m), h)
    for g in (1, 2):
        for m, st, _ in gl[g]: h = zlib.crc32(b''.join(x.to_bytes(2, 'little') for x in m) + bytes(st[:1]) + st[1].to_bytes(2, 'little'), h)
    for n in ('kid.dir', 'sword.dir', 'kid.pack', 'sword.pack') + tuple(x + y for x in FS_GSETS for y in ('.dir', '.pack')):
        h = zlib.crc32(open(os.path.join(A, n), 'rb').read(), h)
    for n in ('src/m1/kernel_gen.inc', 'src/m1/gfx.asm', 'src/m1/tables.asm', 'src/m4/fstore.asm', 'src/m4/fsgen.asm'):
        h = zlib.crc32(open(os.path.join(ROOT, n), 'rb').read(), h)
    return h

def main():
    if '--uses' in sys.argv: return uses_from_meas(sys.argv[sys.argv.index('--uses') + 1])
    if '--guses' in sys.argv: return guses_from_meas(sys.argv[sys.argv.index('--guses') + 1])
    masks, keys, ends, use = layout()
    assert ends[0][0] < FS_TOP1, 'class 1 does not fit 1 MB'
    gl, gend, guse = guard_layout(ends[0], ends[1])
    fid = build_id(masks, gl)
    top2 = gend[0]              # class 2 and the whole guard sets (g 2) need pages up to gend's
    tab = bytearray(FS_DATA)
    for cls in (1, 2):
        t = tab if cls == 1 else bytearray(tab)
        for (c_, i, c, f, m, s, p, a, n) in keys:
            if c_ > cls: continue
            o = i * 64 + (m * 8 + s) * 4; t[o:o + 3] = bytes((p, a >> 8, a & 255))
        t[FS_MARK:FS_MARK + 5] = fid.to_bytes(4, 'little') + bytes((cls,))
        open(os.path.join(A, 'fstore_tab%d.bin' % cls), 'wb').write(t)
    with open(os.path.join(A, 'fstore_gmasks.bin'), 'wb') as f:  # (the guard fill's input, FS_MPAGE:FS_GMADDR)
        for g in (1, 2):
            for m, (p, a), _ in gl[g]:
                f.write((b''.join(x.to_bytes(2, 'little') for x in m) + bytes((p, a & 255, a >> 8))).ljust(FS_GREC, b'\0'))
    gsum = []
    with open(os.path.join(A, 'fstore_gkeys.txt'), 'w') as f:
        f.write('# g set id frame mirror shift page address bytes (tools/fstore.py)\n')
        for g in (1, 2):
            for s_, (m, st, ks) in enumerate(gl[g]):
                for k in ks: f.write('%d %d %d %d %d %d %d 0x%04X %d\n' % ((g, s_) + k))
                hit = sum(guse[(s_, k[1], k[2], k[3])] for k in ks); tot = sum(n for k, n in guse.items() if k[0] == s_)
                gsum.append((g, s_, len(ks), sum(k[6] + 4 for k in ks), hit, tot))
    with open(os.path.join(A, 'fstore_keys.txt'), 'w') as f:
        f.write('# class id chtab frame mirror shift page address bytes (tools/fstore.py)\n')
        for k in keys: f.write('%d %d %d %d %d %d %d 0x%04X %d\n' % k)
    n1 = [k for k in keys if k[0] == 1]; n2 = [k for k in keys if k[0] == 2]
    b1 = sum(k[8] + 4 for k in n1); b2 = sum(k[8] + 4 for k in n2)
    tot = sum(use.values())
    with open(os.path.join(A, 'fstore_equ.inc'), 'w') as f:      # (the main program's; the overlay gets them as symbols)
        f.write('; generated by tools/fstore.py: the frame store\'s constants (docs/ramdisk-tiers.md)\n')
        f.write('; class 1: %d keys, %d bytes, to page %d 0x%04X (%.1f %% of the scripts\' kid and sword fetches)\n' % (
            len(n1), b1, ends[0][0], ends[0][1], 100 * sum(use[(k[2], k[3], k[4], k[5])] for k in n1) / tot))
        f.write('; class 2: %d keys, %d bytes, to page %d 0x%04X; build id %08x\n' % (len(n2), b2, ends[1][0], ends[1][1], fid))
        for g, s_, n, b, hit, tot in gsum:
            f.write('; guards g %d set %d %-12s: %d keys, %d bytes (%d of the scripts\' %d fetches)\n' % (g, s_, FS_GSETS[s_], n, b, hit, tot))
        f.write('; g 2 ends at page %d 0x%04X\n' % gend)
        for nm, v in (('FS_PAGE', FS_PAGE), ('FS_SWORD', FS_SWORD), ('FS_IDS', FS_IDS), ('FS_MARK', FS_MARK),
                      ('FS_DATA', FS_DATA), ('FS_TOP1', FS_TOP1), ('FS_TOP2', top2), ('FS_MPAGE', FS_MPAGE), ('FS_MADDR', FS_MADDR),
                      ('FS_N1', len(n1)), ('FS_N2', len(n2)),
                      ('FS_E1P', ends[0][0]), ('FS_E1A', ends[0][1]),
                      ('FS_GID', FS_GID), ('FS_GN', FS_GN), ('FS_GFLAG', FS_GFLAG), ('FS_GMADDR', FS_GMADDR), ('FS_GREC', FS_GREC)):
            f.write('%-15s equ     0x%04x\n' % (nm, v))
    with open(os.path.join(A, 'fstore_masks.bin'), 'wb') as f:   # (the fill's input in the RAM disk, FS_MPAGE:FS_MADDR)
        f.write(b''.join(x.to_bytes(2, 'little') for m in masks for x in m) + fid.to_bytes(4, 'little'))
    print('frame store: class 1 %d keys %d bytes (to page %d 0x%04X), class 2 %d keys %d bytes (to page %d 0x%04X; with the whole guard sets to page %d 0x%04X: on from rd_top %d); id %08x'
          % (len(n1), b1, ends[0][0], ends[0][1], len(n2), b2, ends[1][0], ends[1][1], gend[0], gend[1], top2, fid))
    for g, s_, n, b, hit, tot in gsum:
        print('  guards g %d %-12s %4d keys %7d bytes, %d of %d script fetches' % (g, FS_GSETS[s_], n, b, hit, tot))

if __name__ == '__main__':
    main()
