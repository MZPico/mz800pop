#!/usr/bin/env python3
"""The shipped disk images' Extended DSK sector lengths (tools/edsk.py) and the game disk's directory: every sector-info entry of build/pop800.dsk,
build/m0.dsk and, when built, the cheats and pacing disks has bytes 6-7 ("actual data length") = 128 << N. mzdisk
writes 0 there; a floppy written from such an image (Greaseweazle) has no sector data and does not boot. Also checks
that the check itself sees a zero length (a copy of the image with one entry cleared). The directory: every file the
boot or the save looks up by name (POP800.D1.., POP800.SAV) is in the directory's first block (block 16, the only one
they read: tools/mkgamedisk.py check_lookups), and the check fails when one is not (a copy with POP800.SAV's entry in
block 16 freed). No emulator.
usage: edsk_check.py [FILE...]"""
import os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import edsk, mkgamedisk

DISKS = ['build/pop800.dsk', 'build/m0.dsk']
OPTIONAL = ['build/cheat/build/pop800.dsk', 'build/pace/build/pop800.dsk']


def main(args):
    paths = args or [os.path.join(ROOT, p) for p in DISKS] + [os.path.join(ROOT, p) for p in OPTIONAL
                                                               if os.path.exists(os.path.join(ROOT, p))]
    fails = 0
    for p in paths:
        pr = edsk.check(p)
        n = sum(1 for _ in edsk.sectors(open(p, 'rb').read()))
        print('%s %s: %d sectors%s' % ('FAIL' if pr else 'ok  ', os.path.relpath(p, ROOT), n,
                                      ', %d wrong, e.g. %s' % (len(pr), pr[0]) if pr else ', every length 128 << N'))
        fails += bool(pr)
    e = next(edsk.sectors(open(paths[0], 'rb').read()))[2]     # the check must see a zero length
    with tempfile.NamedTemporaryFile(suffix='.dsk', delete=False) as f:
        f.write(open(paths[0], 'rb').read())
    try:
        edsk.fix(f.name)                            # (a correct image with one entry cleared)
        d = bytearray(open(f.name, 'rb').read())
        d[e + 6] = d[e + 7] = 0
        open(f.name, 'wb').write(d)
        seen = len(edsk.check(f.name)) == 1
        edsk.fix(f.name)
        seen = seen and not edsk.check(f.name)
    finally:
        os.remove(f.name)
    print('%s the check sees a cleared length and fix sets it' % ('ok  ' if seen else 'FAIL'))
    fails += not seen
    for p in paths:                                     # the game disks: the directory's first block
        if os.path.basename(p) != 'pop800.dsk': continue
        d = open(p, 'rb').read()
        names = [n for n in edsk.dir_names(d, 16) if n.startswith('POP800.D')] + [mkgamedisk.SAVE_NAME]
        try: mkgamedisk.check_lookups(d, names); ok = len(names) > 1
        except AssertionError: ok = False
        print('%s %s: %s in directory block 16' % ('ok  ' if ok else 'FAIL', os.path.relpath(p, ROOT), ', '.join(names)))
        fails += not ok
    d = bytearray(open(paths[0], 'rb').read())          # the check fails when POP800.SAV is not in block 16
    t = 16 // 16 ^ 1; free = False
    for tt, i, e in edsk.sectors(d):
        if tt == t and d[e + 2] == 1:
            o = e - 0x18 - 8 * i + 0x100 + 256 * i
            for k in range(8):
                ent = bytes(255 - x for x in d[o + 32 * k:o + 32 * k + 18])
                if ent[1:11] == mkgamedisk.SAVE_NAME.encode():
                    d[o + 32 * k] = 0xFF; free = True                     # (type 0: a free entry)
    try: mkgamedisk.check_lookups(bytes(d), [mkgamedisk.SAVE_NAME]); caught = False
    except AssertionError: caught = True
    print('%s the directory check fails when POP800.SAV is not in block 16' % ('ok  ' if free and caught else 'FAIL'))
    fails += not (free and caught)
    print('edsk_check: %s' % ('PASS' if not fails else 'FAIL'))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main(sys.argv[1:])
