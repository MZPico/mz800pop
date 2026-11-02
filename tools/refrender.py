#!/usr/bin/env python3
"""Reference renderer for the M1 test scene: decodes the pack with the directory and draws the
room (same rules as room_init in m1test.asm) plus sprites into a 320x200 index image.
Used by tests/m1_compare.py to check the Z80 kernel pixel-exact."""
from PIL import Image

MZPAL = [0,0,0,0x40,0x40,0xAC,0xD0,0x34,0,0xB4,0x0C,0x8C,0x40,0x6C,0,0x24,0xCC,0xFF,0xE8,0xD4,0x30,0xD0,0xD0,0xD0,
         0x84,0x84,0x84,0,0x8C,0xE8,0xFF,0,0,0xF0,0x54,0xCC,0x54,0xFF,0x54,0x80,0xFF,0xFF,0xFF,0xFF,0x28,0xFF,0xFF,0xFF]

class Pack:
    def __init__(self, pack, dirb):
        self.pack = pack; self.dir = dirb
    def entry(self, i):
        e = self.dir[i*8:i*8+8]
        off = (e[0] << 16) | (e[1] << 8) | e[2]
        return off, e[3], e[4], e[5] & 1
    def image(self, i):
        """-> (wbytes, h, mask[h][w*8] or None, colour[h][w*8])"""
        off, wb, h, hasmask = self.entry(i)
        n = wb * h; p = self.pack
        mask = p[off:off+n] if hasmask else None
        planes = [p[off + (k + hasmask) * n: off + (k + 1 + hasmask) * n] for k in range(4)]
        col = [[0]*(wb*8) for _ in range(h)]; msk = [[0]*(wb*8) for _ in range(h)]
        for y in range(h):
            for x in range(wb*8):
                o = y*wb + (x >> 3); b = 1 << (x & 7)
                c = sum(((planes[k][o] >> (x & 7)) & 1) << k for k in range(4))
                col[y][x] = c
                msk[y][x] = ((mask[o] & b) == 0) if hasmask else (c != 0)      # (the mask plane is stored inverted)
        return wb, h, msk, col

def room_cells():
    cells = []
    for c in range(30):
        bg = (c & 3) + 1
        if bg == 4: bg = 2
        fore = 4 if c in (3, 7, 16, 25) else None
        cells.append((bg, fore))
    return cells

def render(pk, sprites, with_room=True, cells=None):
    scr = [[0]*320 for _ in range(200)]
    def lay(i, px, py, masked, mirror=False):
        wb, h, msk, col = pk.image(i)
        for y in range(h):
            sy = py + y
            if not 0 <= sy < 200: continue
            for x in range(wb*8):
                sxx = px + ((wb*8 - 1 - x) if mirror else x)
                if not 0 <= sxx < 320: continue
                if masked and not msk[y][x]: continue
                scr[sy][sxx] = col[y][x]
    cells = cells or room_cells()
    if with_room:
        for c, (bg, fore) in enumerate(cells):
            px, py = (c % 10) * 32, (c // 10) * 63
            wb, h, _, _ = pk.image(bg); lay(bg, px, py + 63 - h, True)
    for (i, x, y, mirror) in sprites:
        wb, h, _, _ = pk.image(i)
        # mirrored frames: the Z80 mirrors within the padded (wb*8) pixel row, then shifts by x&7
        lay(i, x, y, True, mirror)
    if with_room:
        for c, (bg, fore) in enumerate(cells):
            if fore is None: continue
            px, py = (c % 10) * 32 + 8, (c // 10) * 63
            wb, h, _, _ = pk.image(fore); lay(fore, px, py + 63 - h, True)
    im = Image.new('P', (320, 200)); px_ = im.load()
    for y in range(200):
        for x in range(320): px_[x, y] = scr[y][x]
    im.putpalette(MZPAL + [0]*(768-48))
    return im
