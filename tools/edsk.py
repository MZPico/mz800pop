#!/usr/bin/env python3
"""Extended DSK sector lengths: fix and check (docs/research/mz800-hardware.md "Real drive findings").

mzdisk (DSKLib) writes every sector-info entry of an Extended DSK image with bytes 6-7, the "actual data length", set to
0. mz800emu ignores the field; tools that write real floppies trust it: Greaseweazle (gw write) wrote such sectors
without data and the MZ-800's ROM found no IPLPRO ("no master"). The length must be 128 << N (N = byte 3).

  python3 tools/edsk.py fix FILE...     set every sector's length to 128 << N (in place)
  python3 tools/edsk.py check FILE...   exit 1 if any sector's length is 0 or differs from 128 << N
"""
import sys


def sectors(d):
    """yield (track index, sector index, offset of its sector-info entry) for every sector of an Extended DSK image"""
    if d[:8] != b'EXTENDED':
        raise ValueError('not an Extended DSK image')
    off = 0x100
    for t in range(d[0x30] * d[0x31]):
        size = d[0x34 + t] * 256
        if not size:
            continue
        if d[off:off + 10] != b'Track-Info':
            raise ValueError('track %d: no Track-Info block at 0x%x' % (t, off))
        for i in range(d[off + 0x15]):
            yield t, i, off + 0x18 + 8 * i
        off += size


def fsmz_block(d, b):
    """FSMZ block b (256 bytes, the true values) of an Extended DSK image: logical track b / 16 is DSK track
    (b / 16) XOR 1 (the MZ-800 writes the side inverted), sector b % 16 + 1, the data stored inverted"""
    t = (b // 16) ^ 1
    for tt, i, e in sectors(d):
        if tt == t and d[e + 2] == b % 16 + 1:
            o = e - 0x18 - 8 * i                        # (the track's Track-Info block)
            return bytes(255 - x for x in d[o + 0x100 + 256 * i:o + 0x100 + 256 * (i + 1)])
    raise ValueError('block %d not in the image' % b)


def dir_names(d, block=16):
    """the file names in one FSMZ directory block (8 entries of 32 bytes: +0 type, +1 the name, CR-terminated)"""
    data = fsmz_block(d, block); out = []
    for k in range(8):
        ent = data[32 * k:32 * k + 32]
        if ent[0] and ent[0] != 0x80:                   # (0: free; 0x80: the directory's header)
            out.append(ent[1:18].split(b'\r')[0].decode('ascii', 'replace'))
    return out


def problems(d):
    out = []
    for t, i, e in sectors(d):
        want, have = 128 << d[e + 3], d[e + 6] | d[e + 7] << 8
        if have != want:
            out.append('track %d sector %d (id %d): length %d, 128 << N = %d' % (t, i, d[e + 2], have, want))
    return out


def fix(path):
    d = bytearray(open(path, 'rb').read())
    n = 0
    for _t, _i, e in sectors(d):
        want = 128 << d[e + 3]
        if d[e + 6] | d[e + 7] << 8 != want:
            d[e + 6], d[e + 7] = want & 0xff, want >> 8
            n += 1
    if n:
        open(path, 'wb').write(d)
    return n


def check(path):
    return problems(open(path, 'rb').read())


def main(argv):
    if len(argv) < 2 or argv[0] not in ('fix', 'check'):
        sys.exit(__doc__)
    bad = 0
    for p in argv[1:]:
        if argv[0] == 'fix':
            print('%s: %d sector lengths set' % (p, fix(p)))
        else:
            pr = check(p)
            if pr:
                bad = 1
                print('%s: %d sectors with a wrong length, e.g. %s' % (p, len(pr), pr[0]))
            else:
                print('%s: every sector length is 128 << N' % p)
    sys.exit(bad)


if __name__ == '__main__':
    main(sys.argv[1:])
