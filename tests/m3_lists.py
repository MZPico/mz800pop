#!/usr/bin/env python3
"""M8a part 22: the precomputed room lists (tools/roomlists.py, src/m3/rlists.asm) against room_ops, in the Z80.

For every room of the levels given (default 1-14), in the M3 test program (build/m3test.mzf):
  1. the canonical state (load_level's tiles, potions at bubble frame 1): the room's lists read back from the blob
     (OPS_ONLY 4: rl_load, slices_build, rl_regen) must be byte-identical to room_ops' (OPS_ONLY 1): the counts, every
     8-byte record, every tag, the slice tables; and nothing may need a regeneration (the blob is that state);
  2. TRIALS random states (default 6) of the tiles the room's lists read (its own, the neighbours' edges): torches,
     potions, gates, loose floors, choppers, spikes, buttons (door-link timers), the level door, the sword, tiles
     that become empty, floor or rubble, any non-wall tile type: the read-back lists, patched, against room_ops of
     that state, the same comparison.
The load state's potions at bubble frame 0 differ from the canonical state too (every potion room exercises the patch).
usage: m3_lists.py [--trials N] [--seed S] [level ...]"""
import base64, os, random, struct, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools')); sys.path.insert(0, os.path.join(ROOT, 'tests'))
from emu import Emu
from popdata import Level, T
import m3_test as M3

RL_BIN = os.path.join(ROOT, 'build', 'assets', 'rlists.bin')
LEVEL = 0xEC00
OPL = (0x9000, 0x9600, 0x9640); OPT = (0x9A40, 0x9B00, 0x9B08)
SL = ((0x8100, 120, 'SL_START'), (0x8180, 120, 'SL_CNT'), (0x0400, 120, 'SL_Y0'), (0x0478, 120, 'SL_Y1'))

def blob(lv):
    d = open(RL_BIN, 'rb').read(); blk, n = struct.unpack_from('<HH', d, 4 * lv)
    return d[blk * 256: blk * 256 + n]

def links(lv, room):
    return lv.links(room) if room else (0, 0, 0, 0)

def room_links(lv, room):
    """room.asm load_room_links: L, R, A, B, AL, AR, BL, BR"""
    L, R, A, B = links(lv, room); AL = AR = BL = BR = 0
    if room:
        if A: AL, AR = links(lv, A)[0], links(lv, A)[1]
        else:
            if L: AL = links(lv, L)[2]
            if R: AR = links(lv, R)[2]
        if B: BL, BR = links(lv, B)[0], links(lv, B)[1]
        else:
            if L: BL = links(lv, L)[3]
            if R: BR = links(lv, R)[3]
    return L, R, A, B, AL, AR, BL, BR

def slot_tiles(lv, room):
    """the (room, pos) of the 64 slots (rlists.asm rl_runs)"""
    L, R, A, B, AL, AR, BL, BR = room_links(lv, room)
    aL, aR, aA, aB, aAL, aAR, aBL, aBR = room_links(lv, A)
    sel = [room, L, B, BL, A, aL, aB, aBL]
    runs = [(0, 0, 3, 0, 10), (1, 0, 3, 9, 1), (2, 0, 1, 0, 9), (3, 0, 1, 9, 1), (4, 2, 1, 0, 10), (5, 2, 1, 9, 1),
            (6, 0, 1, 0, 9), (7, 0, 1, 9, 1)]
    out = set()
    for s, r0, nr, c0, nc in runs:
        if not sel[s]: continue
        for r in range(r0, r0 + nr):
            for c in range(c0, c0 + nc): out.add((sel[s], r * 10 + c))
    return sorted(out)

MODS = {T.gate: lambda r: r.choice([0, 1, 4, 47, 100, 188, 189, 200, 255] + [r.randrange(256)]),
        T.loose: lambda r: r.choice(list(range(11)) + [0x81, 0x82, 0x83, 0x84]),
        T.chomper: lambda r: r.randrange(16) | r.choice([0, 0x80]),
        T.spike: lambda r: r.choice(list(range(10)) + [0x8F, 0x80]),
        T.torch: lambda r: r.randrange(13), T.torch_with_debris: lambda r: r.randrange(13),
        T.level_door_left: lambda r: r.randrange(44), T.sword: lambda r: r.randrange(3)}
NOWALL = [t for t in range(31) if t != T.wall]

def mutate(rng, lv, mem, tiles, n):
    """change n of the tiles in the level image mem (fg 0, bg 720, door-link timers 1696)"""
    for room, pos in rng.sample(tiles, min(n, len(tiles))):
        i = (room - 1) * 30 + pos; t = mem[i] & 0x1F
        if t == T.wall: continue
        k = rng.random()
        if t in MODS and k < 0.6: mem[720 + i] = MODS[t](rng)
        elif t == T.potion and k < 0.6:
            mem[720 + i] = (mem[720 + i] & 0xF8) | rng.randrange(8) if rng.random() < 0.8 else rng.randrange(256)
        elif t in (T.opener, T.closer) and k < 0.6:
            j = 1696 + mem[720 + i]; mem[j] = (mem[j] & 0xE0) | rng.randrange(6)
        elif k < 0.75:
            mem[i] = (mem[i] & 0xE0) | rng.choice([T.empty, T.floor, T.debris])
        else:
            nt = rng.choice(NOWALL); mem[i] = (mem[i] & 0xE0) | nt
            mem[720 + i] = MODS[nt](rng) if nt in MODS else rng.choice([0, 0, 1, 2, 3, rng.randrange(256)])

def lists(e):
    c = e.mem(0x0900 + 22, 3)
    recs = [e.mem(OPL[t], c[t] * 8) if c[t] else b'' for t in range(3)]
    tags = [e.mem(OPT[t], c[t]) if c[t] else b'' for t in range(3)]
    sl = {name: e.mem(a, n) for a, n, name in SL}
    return c, recs, tags, sl

def same(a, b):
    """'' or the first difference"""
    (ca, ra, ta, sa), (cb, rb, tb, sb) = a, b
    if ca != cb: return 'counts %s / %s' % (list(ca), list(cb))
    for t in range(3):
        if ra[t] != rb[t]:
            i = next(i for i in range(0, len(ra[t]), 8) if ra[t][i:i + 8] != rb[t][i:i + 8])
            return 'list %d record %d: %s / %s (tag %d)' % (t, i // 8, ra[t][i:i + 8].hex(), rb[t][i:i + 8].hex(), ta[t][i // 8])
        if ta[t] != tb[t]: return 'list %d tags' % t
    cnt = sa['SL_CNT']
    if cnt != sb['SL_CNT']: return 'SL_CNT'
    for name in ('SL_Y0', 'SL_Y1'):
        if sa[name] != sb[name]:
            i = next(i for i in range(120) if sa[name][i] != sb[name][i])
            return '%s[%d] (count %d): %d / %d' % (name, i, cnt[i], sa[name][i], sb[name][i])
    for i in range(120):
        if cnt[i] and sa['SL_START'][i] != sb['SL_START'][i]: return 'SL_START[%d]' % i
    return ''

def main():
    a = sys.argv[1:]; trials = 6; seed = 22
    if '--trials' in a: i = a.index('--trials'); trials = int(a[i + 1]); del a[i:i + 2]
    if '--seed' in a: i = a.index('--seed'); seed = int(a[i + 1]); del a[i:i + 2]
    levels = [int(x) for x in a] or list(range(1, 15))
    S = M3.syms(os.path.join(ROOT, 'build', 'm3test.sym'))
    rng = random.Random(seed); bad = 0; nroom = 0; nstate = 0; regen = []
    for n in levels:
        lv = Level(n)
        with Emu() as e:
            e.run_mzf(os.path.join(ROOT, 'build', 'm3test.mzf'))
            M3.load_assets(e, lv.type)
            e.call('mem_write', addr=LEVEL, data_hex=lv.raw.hex())
            e.call('mem_write', addr=M3.LEVEL_TYPE, data_hex='%02x' % lv.type)
            M3.write_pack(e, lv.raw, 5, 0x4000 + 2305 * n)          # the blueprint, as the game has it
            M3.write_pack(e, blob(n), 6, S['RL_BASE'])               # the level's blob, as the fetch leaves it
            e.call('mem_write', addr=S['rl_lv'], data_hex='%02x' % n)
            e.call('mem_write', addr=S['RL_TLEVEL'], data_hex='%02x' % n)
            e.call('bp_add', addr=S['draw_done'])
            def run(mode, room, mem):
                e.call('mem_write', addr=LEVEL, data_hex=bytes(mem).hex())
                e.call('mem_write', addr=M3.OPS_ONLY, data_hex='%02x' % mode)
                e.call('mem_write', addr=M3.ROOM_REQ, data_hex='%02x' % room)
                e.call('set_register', reg='PC', value=S['again'])
                r = e.run(1000); assert r['stopped_by'] == 'breakpoint', r
                if mode == 4: assert e.mem(S['RL_FAIL'], 1)[0] == 0, ('no lists', n, room)
                return lists(e)
            e.call('mem_write', addr=M3.OPS_ONLY, data_hex='01')
            e.call('mem_write', addr=M3.ROOM_REQ, data_hex='01')
            r = e.run(1000); assert r['stopped_by'] == 'breakpoint', r
            base = bytearray(e.mem(LEVEL, 2305))                        # after alter_mods
            canon = bytearray(base)
            for i in range(720):
                if canon[i] & 0x1F == T.potion: canon[720 + i] |= 1
            for room in range(1, lv.used_rooms + 1):
                nroom += 1; tiles = slot_tiles(lv, room)
                states = [('canonical', canon), ('load', base)]
                for k in range(trials):
                    m = bytearray(base); mutate(rng, lv, m, tiles, rng.choice([1, 2, 4, 8, 16])); states.append(('random %d' % k, m))
                for name, mem in states:
                    got = run(4, room, mem); nreg = sum(e.mem(0x0E00, 40)); want = run(1, room, mem)
                    nstate += 1; d = same(got, want)
                    if name == 'canonical' and nreg: d = d or 'canonical state, %d tiles regenerated' % nreg
                    if name == 'load': regen.append(nreg)
                    if d:
                        bad += 1; print('level %d room %d, %s state: DIFFERS: %s' % (n, room, name, d))
            print('level %2d: %d rooms, %d states each, differing so far %d' % (n, lv.used_rooms, 2 + trials, bad), flush=True)
    print('rooms %d, states %d, differing %d; the load state regenerated %s tiles a room (mean %.2f, max %d)' % (
        nroom, nstate, bad, sum(regen), sum(regen) / max(1, len(regen)), max(regen or [0])))
    sys.exit(1 if bad else 0)

if __name__ == '__main__': main()
