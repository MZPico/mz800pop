#!/usr/bin/env python3
"""M3: Z80 room renderer versus the Python reference. For each room: compare the operation list
built by the Z80 with popdata.room_oplist(), then the VRAM with the Python render.
usage: m3_test.py [level] [rooms...]"""
import base64, json, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from emu import Emu
from popdata import Level, RoomRenderer, room_oplist
A = os.path.join(ROOT, 'build', 'assets')
DIR_ENV, DIR_WALL, DIR_OBJ, LEVEL_ADDR = 0xE000, 0xE700, 0xEA00, 0xEC00
OPLISTS = (0x9000, 0x9600, 0x9640)   # back, mid, fore record lists (RAM behind the VRAM window)
RV = 0x0900; LEVEL_TYPE = RV + 20; OPCOUNT = RV + 22
ROOM_REQ, OPS_ONLY = 0x0808, 0x0809
RAMDISK = {p: 76 + p for p in range(16)}   # page -> emulator region id (STD RAM disk 64 KB pages)

def syms(path):
    d = {}
    for line in open(path):
        m = re.match(r'(\S+)\s+EQU\s+([0-9A-Fa-f]+)H', line.strip())
        if m: d[m.group(1)] = int(m.group(2), 16)
    return d

def rebase_dir(dirb, page, base):
    """Directory entries hold a 24-bit pack offset; make them RAM-disk (page, address) with the pack loaded at
    `base` of `page` (a pack longer than 64 KB continues in the next page; images never straddle pages)."""
    out = bytearray(dirb)
    for i in range(0, len(out), 8):
        if any(out[i:i+5]):
            off = ((out[i] << 16) | (out[i+1] << 8) | out[i+2]) + base
            out[i] = page + (off >> 16); out[i+1] = (off >> 8) & 255; out[i+2] = off & 255
    return bytes(out)

def write_pack(e, data, page, base):
    """Write a pack into the RAM disk at (page, base), continuing into the following pages."""
    for off in range(0, len(data), 4096):
        a = base + off
        e.call('region_write', region_id=RAMDISK[page + (a >> 16)], offset=a & 0xFFFF, data_b64=base64.b64encode(data[off:off+4096]).decode())

def load_assets(e, ltype):
    env = 'palace' if ltype else 'dungeon'
    packs = {'env': open(os.path.join(A, env + '.pack'), 'rb').read(), 'wall': open(os.path.join(A, env + '_wall.pack'), 'rb').read(),
             'obj': open(os.path.join(A, 'objects.pack'), 'rb').read()}
    dirs = {k: open(os.path.join(A, f), 'rb').read() for k, f in (('env', env + '.dir'), ('wall', env + '_wall.dir'), ('obj', 'objects.dir'))}
    # RAM disk: page 0 env set, page 1 shadow room (32 KB) + wall set at 0x8000 + objects at 0xC000, pages 2-3 kid
    layout = {'env': (0, 0), 'wall': (1, 0x8000), 'obj': (1, 0xC000)}
    for k, (page, base) in layout.items(): write_pack(e, packs[k], page, base)
    for k, addr in (('env', DIR_ENV), ('wall', DIR_WALL), ('obj', DIR_OBJ)):
        page, base = layout[k]
        e.call('mem_write', addr=addr, data_hex=rebase_dir(dirs[k], page, base).hex())
    variants = {}
    for name, ch in ((env, 6), (env + '_wall', 7), ('objects', 1)):
        for (i, sft, vid) in json.load(open(os.path.join(A, name + '.json')))['variants']: variants[(ch, i, sft)] = vid
    return variants

def z80_ops(e):
    counts = e.mem(OPCOUNT, 3); out = []
    for t, base in enumerate(OPLISTS):
        n = counts[t]; raw = e.mem(base, n * 8) if n else b''
        for i in range(n):
            r = raw[i*8:i*8+8]
            xb = r[3] - 256 if r[3] > 127 else r[3]; yt = r[4] | (r[5] << 8); yt = yt - 65536 if yt > 32767 else yt
            out.append((r[0] & 3, r[1], r[2], xb, yt, (r[0] >> 2) & 3, (r[0] >> 4) & 15))
    return out

def main():
    lv = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    level = Level(lv); rr = RoomRenderer(level, ega=True)
    rooms = [int(r) for r in sys.argv[2:]] or list(range(1, level.used_rooms + 1))
    S = syms(os.path.join(ROOT, 'build', 'm3test.sym'))
    with Emu() as e:
        e.run_mzf(os.path.join(ROOT, 'build', 'm3test.mzf'))
        variants = load_assets(e, level.type)
        e.call('mem_write', addr=LEVEL_ADDR, data_hex=level.raw.hex())
        e.call('mem_write', addr=LEVEL_TYPE, data_hex='%02x' % level.type)
        e.call('mem_write', addr=ROOM_REQ, data_hex='%02x' % rooms[0])
        e.call('bp_add', addr=S['draw_done'])
        first = True; total_bad = 0; ops_bad = 0
        for room in rooms:
            if not first:
                e.call('mem_write', addr=ROOM_REQ, data_hex='%02x' % room)
                e.call('set_register', reg='PC', value=S['again'])
            first = False
            r = e.run(1000); assert r['stopped_by'] == 'breakpoint', r
            rr.draw_room(room); ref_ops = room_oplist(rr, variants); got_ops = z80_ops(e)
            same = sum(1 for a, b in zip(ref_ops, got_ops) if a == b)
            if ref_ops != got_ops:
                ops_bad += 1
                print('room %d: OPS DIFFER: z80 %d ops, python %d ops, %d equal in sequence' % (room, len(got_ops), len(ref_ops), same))
                for i, (a, b) in enumerate(zip(ref_ops, got_ops)):
                    if a != b: print('   first diff at %d: python %s  z80 %s' % (i, a, b)); break
                if len(ref_ops) != len(got_ops):
                    extra = got_ops[len(ref_ops):] if len(got_ops) > len(ref_ops) else ref_ops[len(got_ops):]
                    print('   extra:', extra[:3])
            im = e.vram_image(); ref = rr.draw_room(room); pm, pr = im.load(), ref.load()
            bad = [(x, y, pm[x, y], pr[x, y]) for y in range(192) for x in range(320) if pm[x, y] != pr[x, y]]
            total_bad += len(bad)
            print('room %2d: ops %s, pixels differing %d %s' % (room, 'ok' if ref_ops == got_ops else 'DIFF', len(bad), bad[:3]))
            if bad:
                im.save(os.path.join(ROOT, 'build', 'm3_room%d_z80.png' % room)); ref.save(os.path.join(ROOT, 'build', 'm3_room%d_ref.png' % room))
    print('total differing pixels:', total_bad)
    if ops_bad: print('rooms whose op lists differ:', ops_bad)
    sys.exit(1 if total_bad or ops_bad else 0)

if __name__ == '__main__': main()
