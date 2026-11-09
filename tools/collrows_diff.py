#!/usr/bin/env python3
"""Differential check of the collision rows (docs/perf.md "M8a part 23: collision rows"): the old and the new
check_collisions (move_coll_to_prev, get_row_collision_data three times, the bump loop) and k_get_tile, run on the same
inputs in two emulators, one with each build of m4test, and every byte they leave compared.

  collrows_diff.py OLD_BUILD_DIR NEW_BUILD_DIR [--cases N] [--seed S] [--levels 1-14]

Each build dir holds an m4test.mzf / .b2 / .sym (e.g. a copy of build/ made at main, and build/). Per level, both
emulators boot m4test, load the level (tests/m4_test.py setup) and run to the first tick's end; then for each case
the cases go in batches of 30 (a KV image and the registers each, at 0xA000: m4test does not draw) to a driver loop at
0x0E00 (assembled by pasmo for the routine's address): per case it copies the image into KV, loads AF, BC, DE, HL,
calls the routine with interrupts off, and copies KV and the registers back over the case:
- check_collisions: Char's room, row, action and collision x (CX_LCOLL, CX_RCOLL) random (rooms 1-24, rows -1..3,
  x -300..600 with widths 0..48, or each at a wall's x +-1), the collision rows (prev, current, below, above), PREV_COLL_ROW and the tile
  variables random; compared: all of KV (0x0A00-0x0AFF) but the scratch bytes K_TMP, K_TMPW, K_TMPW2 (KV + 80,
  84..87: written by the old code, read by nobody after it).
- k_get_tile: room 0-24, column -15..24, row -5..7 random; compared: KV and the registers AF, BC, DE, HL.
Prints the cases and the differences (0 = equal; exit status 1 if any). Needs the trace-capable emulator
(MZ800EMU_BIN, as the tests) and pasmo."""
import os, random, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, 'tools'), os.path.join(ROOT, 'tests')]
from emu import Emu
from m3_test import syms
import m4_test as M
import kidsim

KV = 0x0A00
STUB = 0x0E00
SKIP = {80, 84, 85, 86, 87}

def boot(build, level):
    e = Emu()
    S = syms(os.path.join(build, 'm4test.sym'))
    e.run_mzf(os.path.join(build, 'm4test.mzf'))
    M.write_pack(e, open(os.path.join(M.A, 'logic.bin'), 'rb').read(), 6, 0xD000)
    M.write_pack(e, M.levels_blob(), 5, 0x4000)
    e.call('mem_write', addr=M.DIR_KID, data_hex=open(os.path.join(M.A, 'kid.dir'), 'rb').read().hex())
    e.call('mem_write', addr=S['level_number'], data_hex='%02x' % level)
    o = kidsim.script_opts(os.path.join(ROOT, 'tests', 'm4_scripts', 'walk_level1.txt'))
    e.call('mem_write', addr=S['guard_opts'], data_hex=M.guard_opts_bytes(o).hex())
    e.call('mem_write', addr=S['ev_opts'], data_hex=M.ev_opts_bytes(o).hex())
    e.call('mem_write', addr=M.SCRIPT, data_hex='ff')
    e.call('bp_clear'); e.call('bp_add', addr=S['tick_done']); e.run(400); e.call('bp_clear')
    return e, S

DRIVER = """
                org     0x0E00
                di
                ld      sp, 0xFD00
dl_loop:        ld      hl, (rec)
                ld      de, 0x0A00
                ld      bc, 256
                ldir
                ld      sp, hl
                pop     af
                pop     bc
                pop     de
                pop     hl
                ld      sp, 0xFD00
                call    TARGET
                ld      (o_hl), hl
                ld      (o_de), de
                ld      (o_bc), bc
                push    af
                pop     hl
                ld      (o_af), hl
                ld      hl, 0x0A00
                ld      de, (rec)
                ld      bc, 256
                ldir
                ld      hl, 8
                add     hl, de
                ex      de, hl
                ld      hl, o_af
                ld      bc, 8
                ldir
                ld      (rec), de
                ld      hl, cnt
                dec     (hl)
                jr      nz, dl_loop
dl_done:        jr      dl_done
rec:            dw      BUF
cnt:            db      0
o_af:           dw      0
o_bc:           dw      0
o_de:           dw      0
o_hl:           dw      0
"""
BUF, REC, NREC = 0xA000, 272, 30

def driver(target, tmp):
    """the driver loop assembled by pasmo for a target address -> (code bytes, the done address, cnt's address)"""
    src = os.path.join(tmp, 'drv%04x.asm' % target)
    open(src, 'w').write('TARGET equ 0x%04x\nBUF equ 0x%04x\n' % (target, BUF) + DRIVER)
    out = src[:-4] + '.bin'; sym = src[:-4] + '.sym'
    subprocess.check_call(['pasmo', '--bin', src, out, sym], stdout=subprocess.DEVNULL)
    S = syms(sym)
    return open(out, 'rb').read(), S['dl_done'], S['cnt']

def run_batch(e, drv, recs):
    """recs: (KV image 256, regs in AF BC DE HL) -> [(KV after, regs out)]"""
    code, done, cnt = drv
    data = b''.join(kv + b''.join(w16(r) for r in regs) + bytes(8) for kv, regs in recs)
    e.call('mem_write', addr=STUB, data_hex=code.hex())
    e.call('mem_write', addr=cnt, data_hex='%02x' % len(recs))
    e.call('mem_write', addr=BUF, data_hex=data.hex())
    e.call('bp_clear'); e.call('bp_add', addr=done)
    e.call('set_register', reg='PC', value=STUB)
    e.run(40)
    if e.call('get_registers')['PC'] != done or e.mem(cnt, 1) != b'\0':
        raise RuntimeError('the driver did not finish')
    m = e.mem(BUF, REC * len(recs))
    return [(m[i * REC:i * REC + 256], m[i * REC + 264:i * REC + 272]) for i in range(len(recs))]

def w16(v): return bytes([v & 255, (v >> 8) & 255])

def cc_case(rnd):
    kv = {}
    kv[9] = bytes([rnd.randint(1, 24)])                   # K_ROOM
    kv[5] = bytes([rnd.randint(-1, 3) & 255])             # K_ROW
    kv[6] = bytes([rnd.choice([0, 1, 2, 3, 4, 5, 6, 7])]) # K_ACTION (7 = AC_TURN?)
    if rnd.random() < 0.5:                                # anywhere
        l = rnd.randint(-300, 600); r = l + rnd.randint(0, 48)
    else:                                                 # at a wall's x (or one off): tlx = 14 c + 65, the walls at
        tlx = lambda: 14 * rnd.randint(-6, 15) + 65       # tlx + (-1, 0, 10) (left) and tlx + (0, 3, 13) (right)
        r = tlx() + rnd.choice([-1, 0, 10]) + rnd.randint(-1, 1)
        l = tlx() + rnd.choice([0, 3, 13]) + rnd.randint(-1, 1)
        if rnd.random() < 0.7: l = r - rnd.randint(0, 40)
        elif rnd.random() < 0.5: r = l + rnd.randint(0, 40)
    if rnd.random() < 0.1: l, r = r, l                    # also crossed
    kv[50] = w16(l); kv[52] = w16(r)                      # CX_LCOLL, CX_RCOLL
    kv[60] = bytes(rnd.randrange(256) for _ in range(10)) # tile variables, COLL_TLX
    kv[71] = bytes([rnd.randint(-2, 4) & 255])            # PREV_COLL_ROW
    rows = bytearray()
    for _ in range(4):
        rows += bytes(rnd.choice([0xff, rnd.randint(0, 24)]) for _ in range(10))
        rows += bytes(rnd.randrange(256) for _ in range(10))
    kv[96] = bytes(rows)
    return kv

def main():
    a = sys.argv[1:]
    old, new = a[0], a[1]
    n = int(a[a.index('--cases') + 1]) if '--cases' in a else 2000
    seed = int(a[a.index('--seed') + 1]) if '--seed' in a else 1
    lv = a[a.index('--levels') + 1] if '--levels' in a else '1-14'
    l0, l1 = (int(x) for x in lv.split('-'))
    total = bad = 0; cases = [0, 0]
    tmp = tempfile.mkdtemp()
    for level in range(l0, l1 + 1):
        (eo, So), (en, Sn) = boot(old, level), boot(new, level)
        assert eo.mem(M.LEVEL_ADDR, 2305) == en.mem(M.LEVEL_ADDR, 2305)
        base_o, base_n = eo.mem(KV, 256), en.mem(KV, 256)
        rnd = random.Random(seed * 100 + level)
        drvs = {}
        for e, S, tag in ((eo, So, 'o'), (en, Sn, 'n')):
            drvs[tag] = (driver(S['check_collisions'], tmp), driver(S['k_get_tile'], tmp))
        done = 0
        while done < n:
            k = min(NREC, n - done)
            kind = (done // NREC) % 2                    # batches of check_collisions and of k_get_tile in turn
            recs = []
            for i in range(k):
                kv = bytearray(base_o)
                if kind == 0:
                    for off, b in cc_case(rnd).items(): kv[off:off + len(b)] = b
                    regs = (0, 0, 0, 0)
                else:
                    room, col, row = rnd.randint(0, 24), rnd.randint(-15, 24), rnd.randint(-5, 7)
                    regs = (room << 8 | rnd.randrange(256), ((row & 255) << 8) | (col & 255), rnd.randrange(65536), rnd.randrange(65536))
                recs.append((bytes(kv), regs))
            ro = run_batch(eo, drvs['o'][kind], recs)
            rn = run_batch(en, drvs['n'][kind], recs)
            for (kv, regs), a_, b_ in zip(recs, ro, rn):
                mo = bytes(0 if j in SKIP else v for j, v in enumerate(a_[0]))
                mn = bytes(0 if j in SKIP else v for j, v in enumerate(b_[0]))
                ok = mo == mn and (kind == 0 or a_[1] == b_[1])
                total += 1; cases[kind] += 1
                if not ok:
                    bad += 1
                    if bad <= 10:
                        d = [j for j in range(256) if mo[j] != mn[j]]
                        print('DIFF level %d %s: in %s regs %s; KV bytes %s, regs %s / %s' % (level, ('check_collisions', 'k_get_tile')[kind],
                              kv[:176].hex(), regs, d, a_[1].hex(), b_[1].hex()))
            done += k
        eo.p.kill(); en.p.kill()
        print('level %2d: %d cases, %d differing so far' % (level, n, bad), flush=True)
    print('total: %d cases (check_collisions %d, k_get_tile %d), %d differing' % (total, cases[0], cases[1], bad))
    sys.exit(1 if bad else 0)

if __name__ == '__main__':
    main()
