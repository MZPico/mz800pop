#!/usr/bin/env python3
"""Pixel-exact comparison of the Z80 kernel output against tools/refrender.py."""
import base64, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from emu import Emu
from refrender import Pack, render
from PIL import Image

def syms(path):
    d = {}
    for line in open(path):
        m = re.match(r'(\S+)\s+EQU\s+([0-9A-Fa-f]+)H', line.strip())
        if m: d[m.group(1)] = int(m.group(2), 16)
    return d

def diff(a, b, out):
    pa, pb = a.load(), b.load(); n = 0; first = None
    im = Image.new('RGB', (320, 200)); po = im.load()
    for y in range(200):
        for x in range(320):
            if pa[x, y] != pb[x, y]:
                n += 1; po[x, y] = (255, 0, 0); first = first or (x, y, pa[x, y], pb[x, y])
            else: po[x, y] = (0, 0, 0) if pa[x, y] == 0 else (60, 60, 60)
    im.resize((640, 400)).save(out); return n, first

def sprite_state(e, base):
    d = e.mem(base, 16)
    return {'x': d[6] | (d[7] << 8), 'y': d[5], 'frame': d[8], 'mirror': d[9], 'xb': d[4], 'ow': d[2], 'h': d[3]}

def main():
    S = syms(os.path.join(ROOT, 'build', 'm1test.sym'))
    pack = open(os.path.join(ROOT, 'build', 'm1.pack'), 'rb').read()
    dirb = open(os.path.join(ROOT, 'build', 'm1.dir'), 'rb').read()
    pk = Pack(pack, dirb)
    total = 0
    with Emu() as e:
        e.run_mzf(os.path.join(ROOT, 'build', 'm1test.mzf'))
        for off in range(0, len(pack), 4096):
            e.call('region_write', region_id=76, offset=off, data_b64=base64.b64encode(pack[off:off+4096]).decode())
        e.call('mem_write', addr=0x7800, data_hex=dirb.hex())
        e.call('bp_add', addr=S['ph_tick']); e.run(1000)
        got = e.vram_image(); ref = render(pk, [])
        n, first = diff(got, ref, os.path.join(ROOT, 'build', 'cmp_room.png')); total += n
        print('room: %d differing pixels' % n, first or '')
        for t in range(3):
            e.run(100)   # to the next ph_tick breakpoint: one full tick has been composed and blitted
            a, b = sprite_state(e, 0x0840), sprite_state(e, 0x0860)
            got = e.vram_image()
            ref = render(pk, [(a['frame'], a['x'], a['y'], a['mirror']), (b['frame'], b['x'], b['y'], b['mirror'])])
            n, first = diff(got, ref, os.path.join(ROOT, 'build', 'cmp_tick%d.png' % t)); total += n
            print('tick %d: A=%s B=%s -> %d differing pixels %s' % (t, a, b, n, first or ''))
        ref.save(os.path.join(ROOT, 'build', 'cmp_ref.png')); got.save(os.path.join(ROOT, 'build', 'cmp_got.png'))
    print('total differing pixels:', total)
    sys.exit(1 if total else 0)

if __name__ == '__main__': main()
