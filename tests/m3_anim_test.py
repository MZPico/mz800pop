#!/usr/bin/env python3
"""M3: per-tile redraw (tile_redraw) versus the Python reference. Draws a room, then changes the modifier of
every animated tile a few times; after each change the Z80 regenerates that tile's ops and re-lays the dirty
rect. Checks the op lists and the full VRAM against a fresh Python render of the modified room, and reports
the cycle cost per redraw. usage: m3_anim_test.py [level] [rooms...]"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m3_test import *
from popdata import T
TILE_REQ = 0x080A; TILE_FRAME = 0x080B
FRAMES = {T.torch: [3, 7, 0], T.torch_with_debris: [3, 7, 0], T.gate: [60, 120, 188, 0], T.spike: [1, 3, 5, 0x85, 0],
          T.chomper: [2, 5, 8, 0x83, 1], T.loose: [0x81, 0x8c, 1, 0], T.level_door_left: [10, 30, 43, 0], T.sword: [5, 0],
          T.potion: None}

def main():
    lv = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    level = Level(lv); rr = RoomRenderer(level, ega=True)
    rooms = [int(r) for r in sys.argv[2:]] or list(range(1, level.used_rooms + 1))
    S = syms(os.path.join(ROOT, 'build', 'm3test.sym'))
    total_bad = 0; costs = []; ops_bad = 0
    with Emu() as e:
        e.run_mzf(os.path.join(ROOT, 'build', 'm3test.mzf'))
        variants = load_assets(e, level.type)
        e.call('mem_write', addr=LEVEL_ADDR, data_hex=level.raw.hex())
        e.call('mem_write', addr=LEVEL_TYPE, data_hex='%02x' % level.type)
        e.call('bp_add', addr=S['draw_done'])
        first = True
        for room in rooms:
            # full draw first
            e.call('mem_write', addr=OPS_ONLY, data_hex='00')
            e.call('mem_write', addr=ROOM_REQ, data_hex='%02x' % room)
            if not first: e.call('set_register', reg='PC', value=S['again'])
            first = False
            r = e.run(1000); assert r['stopped_by'] == 'breakpoint', r
            base = (room - 1) * 30
            for pos in range(30):
                t = level.fg[base + pos] & 0x1F
                if t not in FRAMES: continue
                orig = level.bg[base + pos]
                frames = FRAMES[t] if FRAMES[t] is not None else [(orig & 0xF8) | f for f in (2, 5, 7)]
                if t == T.potion and (orig >> 3) == 0: continue
                for m in frames:
                    level.bg[base + pos] = m
                    e.call('mem_write', addr=LEVEL_ADDR + 720 + base + pos, data_hex='%02x' % m)
                    if t in (T.torch, T.torch_with_debris) and pos % 10 < 9 and m < 9:
                        # torch fast path: patch the flame op in the slice of the tile to the right
                        e.call('mem_write', addr=OPS_ONLY, data_hex='03')
                        e.call('mem_write', addr=TILE_REQ, data_hex='%02x' % (pos + 1)); e.call('mem_write', addr=TILE_FRAME, data_hex='%02x' % m)
                    else:
                        e.call('mem_write', addr=OPS_ONLY, data_hex='02')
                        e.call('mem_write', addr=TILE_REQ, data_hex='%02x' % pos)
                    e.call('set_register', reg='PC', value=S['again'])
                    t0 = e.call('get_raster_pos')['total_cycles']
                    r = e.run(1000); assert r['stopped_by'] == 'breakpoint', r
                    cost = e.call('get_raster_pos')['total_cycles'] - t0; costs.append((cost, (t if not (t in (T.torch, T.torch_with_debris) and pos % 10 < 9 and m < 9) else 'torch-fast'), pos, m))
                    ref = rr.draw_room(room); ref_ops = room_oplist(rr, variants); got_ops = z80_ops(e)
                    im = e.vram_image(); pm, pr = im.load(), ref.load()
                    bad = [(x, y, pm[x, y], pr[x, y]) for y in range(192) for x in range(320) if pm[x, y] != pr[x, y]]
                    total_bad += len(bad)
                    ops_bad += ref_ops != got_ops
                    if ref_ops != got_ops or bad:
                        print('room %d tile %d (type %d) mod %d: ops %s, pixels differing %d %s, %d T' % (room, pos, t, m, 'ok' if ref_ops == got_ops else 'DIFF', len(bad), bad[:3], cost))
                        if ref_ops != got_ops:
                            for i, (a, b) in enumerate(zip(ref_ops, got_ops)):
                                if a != b: print('   first op diff at %d: python %s z80 %s' % (i, a, b)); break
                            if len(ref_ops) != len(got_ops): print('   lengths python %d z80 %d' % (len(ref_ops), len(got_ops)))
                        if bad:
                            im.save(os.path.join(ROOT, 'build', 'm3a_r%d_t%d_m%d_z80.png' % (room, pos, m))); ref.save(os.path.join(ROOT, 'build', 'm3a_r%d_t%d_m%d_ref.png' % (room, pos, m)))
                level.bg[base + pos] = orig
                e.call('mem_write', addr=LEVEL_ADDR + 720 + base + pos, data_hex='%02x' % orig)
                # restore the Z80 state too so later tiles start from the reference room
                e.call('mem_write', addr=OPS_ONLY, data_hex='02'); e.call('mem_write', addr=TILE_REQ, data_hex='%02x' % pos)
                e.call('set_register', reg='PC', value=S['again']); r = e.run(1000); assert r['stopped_by'] == 'breakpoint', r
            print('room %2d: %d redraws, total differing pixels so far %d' % (room, len(costs), total_bad))
    if costs:
        by_type = {}
        for c, t, pos, m in costs: by_type.setdefault(t, []).append(c)
        for t, cs in sorted(by_type.items(), key=lambda kv: str(kv[0])): print('type %s: %d redraws, avg %6d T (%.2f frames), max %d' % (t, len(cs), sum(cs) // len(cs), sum(cs) / len(cs) / 70886, max(cs)))
    print('total differing pixels:', total_bad)
    if ops_bad: print('redraws whose op lists differ:', ops_bad)
    sys.exit(1 if total_bad or ops_bad else 0)

if __name__ == '__main__': main()
