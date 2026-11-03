#!/usr/bin/env python3
"""The frame store (docs/ramdisk-tiers.md "As built: step 1"; src/m4/fstore.asm, src/m4/fslook.asm, tools/fstore.py)
on the emulated RAM disk's size (the emulator's: POP800_RD_SIZE, else emu/mz800emu.ini's):
  - 1 MB and more: the fill (game_start) leaves page 8's key table and marker exactly as tools/fstore.py computes
    them (build/assets/fstore_tab<class>.bin) and every stored entry equal to the kernel's buffer as
    tools/fetchmodel/prebuild.py generates it (its output equals the kernel's: prebuild_check.py), with its header;
    char_fetch's fs_on points at the lookup; a second start finds the marker and does not fill again; then a level
    start of each guard set (section 13): the lookup's guard base, the sets' flags, every guard slot of the key table
    and every stored entry of the level's set as tools/fstore.py (build/assets/fstore_gkeys.txt) and prebuild.py
    compute them, the shared region refilled on 1 MB, the sets kept on 16 MB, and the level start's time;
  - below 1 MB: no fill, fs_on unchanged (today's fetch), pages 8+ not written (they alias pages 0-7).
Prints the fill's time (frames of 71,136 T). The pixels with the store: every VRAM test (tests/m4_game.py and the
others) on that size. usage: m8_fstore.py"""
import os, sys, struct, collections
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [HERE, os.path.join(ROOT, 'tools'), os.path.join(ROOT, 'tools', 'fetchmodel')]
import m4_game as G
from m3_test import syms
RAMDISK = {p: 76 + p for p in range(52)}     # (page -> region id; the MCP lists pages 0-51 of a 16 MB RAM disk)
from emu import Emu
import prebuild
A = os.path.join(ROOT, 'build', 'assets')
F = 71136

def page_read(e, page, addr, n):
    out = b''
    while n:
        k = min(n, 8192); out += e.region(RAMDISK[page], addr, k); addr += k; n -= k
    return out

ZR = 0xA000                 # z80_read's code and buffer (the compose buffers: the program is reloaded afterwards)
def z80_read(e, page, addr, n):
    """n (<= 3584) bytes of a RAM-disk page that the MCP does not list (16 MB: pages 52+), read by the Z80 itself:
    a routine in the compose buffers run from PC to its stop (the game's state is lost: call it last, setup reloads)"""
    code = bytes((0xF3, 0x3E, page, 0xD3, 0xE9, 0x01, 0xEB, addr >> 8, 0x3E, addr & 255, 0xED, 0x79,
                  0x21, 0x00, (ZR >> 8) + 1, 0x01, 0xEA, 0x00, 0x16, 14, 0xED, 0xB2, 0x15, 0x20, 0xFB, 0x18, 0xFE))
    e.call('mem_write', addr=ZR, data_hex=code.hex())
    e.call('bp_clear'); e.call('bp_add', addr=ZR + len(code) - 2)
    e.call('set_register', reg='PC', value=ZR)
    r = e.run(10); assert r['stopped_by'] == 'breakpoint', r
    e.call('bp_clear')
    return e.mem(ZR + 0x100, n)

# a level of each guard set (game.asm guard_type_tbl, the palace guard by level type), in an order that refills the
# shared region on 1 MB and comes back to a set already filled (16 MB: kept; 1 MB: filled again)
GLEVELS = ((1, 0), (6, 1), (3, 2), (13, 3), (12, 4), (4, 5), (1, 0))
GSETS = ('guard', 'fat', 'skel', 'vizier', 'shadow', 'guard_palace')

def to_ready(e, S):
    """frames from here (the harness after the kid's store: fs_done) to level_ready (load_level done)"""
    c0 = e.call('get_raster_pos')['total_cycles']
    e.call('bp_clear'); e.call('bp_add', addr=S['level_ready'])
    for _ in range(10):
        r = e.run(1000)
        if r['stopped_by'] == 'breakpoint': break
    assert r['stopped_by'] == 'breakpoint', r
    e.call('bp_clear')
    return (e.call('get_raster_pos')['total_cycles'] - c0) / F

def guards(e, S, top):
    """the guard sets (docs/ramdisk-tiers.md section 13): at a level start of each set, the lookup's base, the flags,
    every guard slot of the key table and every stored entry of the level's set as tools/fstore.py and
    tools/fetchmodel/prebuild.py compute them; a restart of the same level does not fill again"""
    g = 2 if top >= S['FS_TOP2'] else 1
    gk = collections.defaultdict(list)
    for l in open(os.path.join(A, 'fstore_gkeys.txt')):
        if l.startswith('#'): continue
        v = l.split(); k = tuple(map(int, v[:7])) + (int(v[7], 16), int(v[8]))
        if k[0] == g: gk[k[1]].append(k[2:])
    fails = 0; filled = set(); vcache = {}
    lo, hi = S['FS_GID'] * 64, (S['FS_GID'] + 6 * S['FS_GN']) * 64
    for lv, st in GLEVELS:
        G.setup(e, lv, fs_fresh=False)
        fr = to_ready(e, S)
        G.setup(e, lv, fs_fresh=False)
        fr2 = to_ready(e, S)
        filled = filled | {st} if g == 2 else {st}
        base = struct.unpack('<H', e.mem(S['fsl_g'] + 1, 2))[0]
        flags = page_read(e, S['FS_PAGE'], S['FS_GFLAG'], 6)
        tab = page_read(e, S['FS_PAGE'], lo, hi - lo)
        want = bytearray(hi - lo)
        for s_ in filled:
            for (i, f, m, sh, p, a, n) in gk[s_]:
                o = i * 64 + (m * 8 + sh) * 4 - lo; want[o:o + 3] = bytes((p, a >> 8, a & 255))
        wflags = bytes(1 if s_ in filled else 0 for s_ in range(6))
        pk = (open(os.path.join(A, GSETS[st] + '.pack'), 'rb').read(), open(os.path.join(A, GSETS[st] + '.dir'), 'rb').read())
        pages = {}; bad = 0; byts = 0; zr = 0
        for (i, f, m, sh, p, a, n) in gk[st]:
            if (st, f) not in vcache: vcache[(st, f)] = prebuild.variants(pk[0], pk[1], f)
            w, h, vs = vcache[(st, f)]
            exp = bytes((w + 1, h)) + struct.pack('<H', n) + vs[m * 8 + sh]
            byts += len(exp)
            if p in RAMDISK:
                if p not in pages: pages[p] = page_read(e, p, 0, 0x10000)
                got = pages[p][a:a + len(exp)]
            else: got = z80_read(e, p, a, len(exp)); zr += 1      # (the game is reloaded by the next setup)
            if got != exp:
                bad += 1
                if bad <= 3: print('FAIL guard set %d frame %d mirror %d shift %d at %d:%04x' % (st, f, m, sh, p, a))
        ok = base == (S['FS_GID'] + S['FS_GN'] * st) * 64 and flags == wflags and tab == want and not bad
        print('level %2d, guard set %d (%s, g %d): %d entries (%d bytes%s) %s; level start %.1f frames (%.2f s), a restart %.1f (%.2f s)%s' % (
            lv, st, GSETS[st], g, len(gk[st]), byts, ', %d read by the Z80' % zr if zr else '', 'equal' if not bad else '%d differ' % bad, fr, fr / 50, fr2, fr2 / 50,
            '' if ok else ' FAIL (base %04x, flags %s, slots %s)' % (base, flags.hex(), 'equal' if tab == want else 'differ')))
        fails += not ok
    return fails

def main():
    S = syms(os.path.join(ROOT, 'build', 'm4game.sym'))
    fails = 0
    with Emu() as e:
        top = G.rd_top(e)
        c0 = e.call('get_raster_pos')['total_cycles']
        G.setup(e, 1)
        c1 = e.call('get_raster_pos')['total_cycles']
        on = struct.unpack('<H', e.mem(S['fs_on'] + 1, 2))[0]
        if top < S['FS_TOP1']:
            ok = on == S['cf_fetch']
            print('RAM disk %s (rd_top %d): no store, fs_on -> cf_fetch: %s' % (G.rd_size(e), top, 'ok' if ok else 'FAIL %04x' % on))
            return 0 if ok else 1
        cls = 2 if top >= S['FS_TOP2'] else 1
        print('RAM disk %s (rd_top %d): class %d; setup with the fill %.1f frames (%.2f s)' % (G.rd_size(e), top, cls, (c1 - c0) / F, (c1 - c0) / F / 50))
        if on != S['fs_look']: print('FAIL fs_on -> %04x, not fs_look' % on); fails += 1
        tab = page_read(e, S['FS_PAGE'], 0, S['FS_DATA'])
        want = open(os.path.join(A, 'fstore_tab%d.bin' % cls), 'rb').read()
        if tab != want:
            bad = [i for i in range(len(want)) if tab[i] != want[i]]
            print('FAIL key table: %d bytes differ, first at 0x%04x' % (len(bad), bad[0])); fails += 1
        else: print('key table and marker: as tools/fstore.py computes them')
        packs = {c: (open(os.path.join(A, n + '.pack'), 'rb').read(), open(os.path.join(A, n + '.dir'), 'rb').read()) for c, n in ((2, 'kid'), (0, 'sword'))}
        pages = {}; n = 0; bad = 0; byts = 0; vcache = {}
        for l in open(os.path.join(A, 'fstore_keys.txt')):
            if l.startswith('#'): continue
            c_, i, c, f, m, s, p, a, sz = l.split(); c_, c, f, m, s, p, sz = map(int, (c_, c, f, m, s, p, sz)); a = int(a, 16)
            if c_ > cls: continue
            if p not in pages: pages[p] = page_read(e, p, 0, 0x10000)
            if (c, f) not in vcache: vcache[(c, f)] = prebuild.variants(packs[c][0], packs[c][1], f)
            w, h, vs = vcache[(c, f)]
            want = bytes((w + 1, h)) + struct.pack('<H', sz) + vs[m * 8 + s]
            got = pages[p][a:a + len(want)]
            n += 1; byts += len(want)
            if got != want:
                bad += 1
                if bad <= 5: print('FAIL entry chtab %d frame %d mirror %d shift %d at %d:%04x' % (c, f, m, s, p, a))
        print('%d entries (%d bytes) checked, %d differ' % (n, byts, bad)); fails += bad > 0
        # a second start: the marker is found, no fill
        c0 = e.call('get_raster_pos')['total_cycles']
        G.setup(e, 1, fs_fresh=False)
        c1 = e.call('get_raster_pos')['total_cycles']
        print('a second start (the marker found): setup %.1f frames' % ((c1 - c0) / F))
        if (c1 - c0) / F > 60: print('FAIL the store was filled again'); fails += 1
        fails += guards(e, S, top)
    print('FAIL' if fails else 'PASS')
    return 1 if fails else 0

if __name__ == '__main__':
    sys.exit(main())
