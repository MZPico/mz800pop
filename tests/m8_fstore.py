#!/usr/bin/env python3
"""The frame store (docs/ramdisk-tiers.md "As built: step 1"; src/m4/fstore.asm, src/m4/fslook.asm, tools/fstore.py)
on the emulated RAM disk's size (the emulator's: POP800_RD_SIZE, else emu/mz800emu.ini's):
  - 1 MB and more: the fill (game_start) leaves page 8's key table and marker exactly as tools/fstore.py computes
    them (build/assets/fstore_tab<class>.bin) and every stored entry equal to the kernel's buffer as
    tools/fetchmodel/prebuild.py generates it (its output equals the kernel's: prebuild_check.py), with its header;
    char_fetch's fs_on points at the lookup; a second start finds the marker and does not fill again;
  - below 1 MB: no fill, fs_on unchanged (today's fetch), pages 8+ not written (they alias pages 0-7).
Prints the fill's time (frames of 71,136 T). The pixels with the store: every VRAM test (tests/m4_game.py and the
others) on that size. usage: m8_fstore.py"""
import os, sys, struct
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
    print('FAIL' if fails else 'PASS')
    return 1 if fails else 0

if __name__ == '__main__':
    sys.exit(main())
