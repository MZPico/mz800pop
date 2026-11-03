#!/usr/bin/env python3
"""Sizes and times of a prebuilt (fixed-layout) frame store (docs/ramdisk-tiers.md section 10): every image of a set
in all 16 variants (mirror x shift) in the cell-buffer format char_fetch leaves (row stride (w+1)*4, the 4 planes of
a byte column together), generated here the way the kernel does it (the mirror = the row's bytes reversed and each
byte bit-reversed; a shift s moves the row s pixels right: bit 0 = the leftmost pixel). Sizes exact; the compression
(tools/pzpack.py, the boot's 16 KB RAM-disk records) measured on a sample of the records. Times: the floppy read and
PZ decode rates measured on today's boot (tests/m5_boot.py: the loader), the MZ-side generation at today's measured
fetch speed (tools/fetchstat.py: per image byte read 25.5 + shift 77-103 + loop 17 T, ~1,800 T a fetch) plus the
write (21.1 T a byte). usage: prebuild.py [--sample N]"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import pzpack
A = os.path.join(HERE, '..', '..', 'build', 'assets')
F = 71136; HZ = 50
REV = bytes(int('{:08b}'.format(b)[::-1], 2) for b in range(256))

def variants(pack, d, i):
    """the 16 cell buffers (mirror 0/1 x shift 0-7) of image i of a set"""
    e = d[i * 8:i * 8 + 8]; off = (e[0] << 16) | (e[1] << 8) | e[2]; w, h = e[3], e[4]
    n = w * h; planes = [pack[off + n * p:off + n * (p + 1)] for p in range(4)]
    out = []
    for m in (0, 1):
        for s in range(8):
            buf = bytearray((w + 1) * 4 * h)
            for p in range(4):
                for y in range(h):
                    row = planes[p][y * w:(y + 1) * w]
                    if m: row = bytes(REV[b] for b in reversed(row))
                    v = int.from_bytes(row, 'little') << s
                    for x in range(w + 1):
                        buf[(y * (w + 1) + x) * 4 + p] = (v >> (8 * x)) & 255
            out.append(bytes(buf))
    return w, h, out

def main():
    sample = int(sys.argv[sys.argv.index('--sample') + 1]) if '--sample' in sys.argv else 6
    tot = {}; allraw = bytearray()
    for s in ('kid', 'sword', 'guard', 'guard_palace', 'fat', 'skel', 'vizier', 'shadow'):
        pack = open(os.path.join(A, s + '.pack'), 'rb').read(); d = open(os.path.join(A, s + '.dir'), 'rb').read()
        raw = bytearray(); imgb = 0; n = 0; gen = 0
        for i in range(len(d) // 8):
            if not (d[i * 8 + 3] and d[i * 8 + 4]): continue
            w, h, vs = variants(pack, d, i)
            for m in range(16):
                raw += vs[m]; n += 1
                ib = w * h * 4; imgb += ib
                gen += 1800 + ib * (25.5 + (79 if m < 8 else 99) + 17) + 800 + 21.1 * len(vs[m])
        tot[s] = (n, len(raw), gen); allraw += raw
    # compression on a sample of 16 KB records (every `sample`-th)
    blk = 16384; zs = 0; rs = 0
    for k, o in enumerate(range(0, len(allraw), blk)):
        if k % sample: continue
        b = bytes(allraw[o:o + blk]); rs += len(b); zs += len(pzpack.compress(b))
    ratio = zs / rs
    print('PZ on %d KB of sample records: %.1f %% of the raw size' % (rs // 1024, 100 * ratio))
    # the boot's rates (tests/m5_boot.py on main: the loader 708 frames for its 3 data files); measured below
    print('%-13s %6s %9s %9s %12s' % ('set', 'keys', 'raw KB', 'PZ KB', 'MZ gen s'))
    for s, (n, b, g) in tot.items():
        print('%-13s %6d %9.1f %9.1f %12.1f' % (s, n, b / 1024, b * ratio / 1024, g / F / HZ))
    n = sum(v[0] for v in tot.values()); b = sum(v[1] for v in tot.values()); g = sum(v[2] for v in tot.values())
    print('%-13s %6d %9.1f %9.1f %12.1f' % ('all', n, b / 1024, b * ratio / 1024, g / F / HZ))

if __name__ == '__main__':
    main()
