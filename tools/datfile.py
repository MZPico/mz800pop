#!/usr/bin/env python3
"""Reader for Prince of Persia 1 DAT files (DOS v1.0-1.4), ported from SDLPoP seg009.c.

    DatFile(path).ids()                 -> resource ids
    DatFile(path).resource(id)          -> raw bytes (without the checksum byte)
    DatFile(path).image(id)             -> (width, height, rows of palette indices 0..15 / 0..1)
    DatFile(path).palette(id)           -> dict(row_bits, vga=[(r,g,b) 8-bit]*16, cga=[..], ega=[..32 bytes])
    datfile.py <file.dat> [outdir]      -> lists resources, writes every image as PNG into outdir

Header: u32 table_offset, u16 table_size. Table: u16 count, then {u16 id, u32 offset, u16 size}.
Each resource starts with a checksum byte, then `size` bytes. Image resource: u16 height, u16 width,
u16 flags (bits 12-14 = bpp-1, bits 8-11 = compression: 0 raw, 1 RLE l-r, 2 RLE u-d, 3 LZG l-r,
4 LZG u-d), then data; pixels are packed MSB first, `stride = (bpp*width+7)//8` bytes per row.
"""
import struct, sys, os

class DatFile:
    def __init__(self, path):
        self.path = path; self.data = open(path, 'rb').read()
        toff, tsize = struct.unpack_from('<IH', self.data, 0)
        count = struct.unpack_from('<H', self.data, toff)[0]
        self.table = {}
        for i in range(count):
            rid, off, size = struct.unpack_from('<HIH', self.data, toff + 2 + i * 8)
            self.table[rid] = (off, size)
    def ids(self): return sorted(self.table)
    def resource(self, rid):
        off, size = self.table[rid]
        return self.data[off + 1: off + 1 + size]      # skip the checksum byte
    def checksum_ok(self, rid):
        off, size = self.table[rid]
        return sum(self.data[off: off + 1 + size]) & 0xFF == 0
    # ---- images
    def image(self, rid):
        r = self.resource(rid)
        h, w, flags = struct.unpack_from('<HHH', r, 0)
        if h == 0: return None
        depth = ((flags >> 12) & 7) + 1; cmeth = (flags >> 8) & 0x0F
        stride = (depth * w + 7) // 8; n = stride * h
        src = r[6:]
        if cmeth == 0: dest = bytes(src[:n]).ljust(n, b'\0')
        elif cmeth == 1: dest = rle_lr(src, n)
        elif cmeth == 2: dest = rle_ud(src, n, stride, h)
        elif cmeth == 3: dest = lzg_lr(src, n)
        elif cmeth == 4: dest = lzg_ud(src, n, stride, h)
        else: raise ValueError('compression %d' % cmeth)
        ppb = 8 // depth; mask = (1 << depth) - 1
        rows = []
        for y in range(h):
            row = []; base = y * stride
            for xb in range(stride):
                v = dest[base + xb]; shift = 8
                for k in range(ppb):
                    if len(row) >= w: break
                    shift -= depth; row.append((v >> shift) & mask)
            rows.append(row)
        return w, h, rows, depth
    def palette(self, rid):
        r = self.resource(rid)
        row_bits, n = struct.unpack_from('<HB', r, 0)
        vga = [(r[3+i*3]*4, r[4+i*3]*4, r[5+i*3]*4) for i in range(16)]
        return {'row_bits': row_bits, 'n_colors': n, 'vga': vga, 'cga': list(r[51:67]), 'ega': list(r[67:99])}

def rle_lr(src, n):
    out = bytearray(); i = 0
    while len(out) < n:
        c = src[i]; i += 1
        if c < 128:
            c += 1
            while c and len(out) < n: out.append(src[i]); i += 1; c -= 1
        else:
            c = 256 - c; v = src[i]; i += 1
            while c and len(out) < n: out.append(v); c -= 1
    return bytes(out)

def rle_ud(src, n, stride, h):
    out = bytearray(n); i = 0; pos = 0; remh = h; written = 0
    def put(v):
        nonlocal pos, remh, written
        out[pos] = v; written += 1; pos += stride; remh -= 1
        if remh == 0: pos -= (n - 1); remh = h
    while written < n:
        c = src[i]; i += 1
        if c < 128:
            c += 1
            while c and written < n: put(src[i]); i += 1; c -= 1
        else:
            c = 256 - c; v = src[i]; i += 1
            while c and written < n: put(v); c -= 1
    return bytes(out)

def lzg(src, n, stride=1, h=None):
    """LZG with a 1 KB ring window; stride/h handle the up-down ('column-major') variant."""
    window = bytearray(0x400); wpos = 0x400 - 0x42
    out = bytearray(n); i = 0; mask = 0; written = 0
    pos = 0; remh = h
    def put(v):
        nonlocal pos, remh, written, wpos
        window[wpos] = v; wpos = (wpos + 1) & 0x3FF
        out[pos] = v; written += 1
        if h is None: pos += 1
        else:
            pos += stride; remh -= 1
            if remh == 0: pos -= (n - 1); remh = h
    while written < n:
        mask >>= 1
        if (mask & 0xFF00) == 0: mask = src[i] | 0xFF00; i += 1
        if mask & 1:
            put(src[i]); i += 1
        else:
            info = (src[i] << 8) | src[i+1]; i += 2
            cs = info & 0x3FF; length = (info >> 10) + 3
            while length and written < n:
                put(window[cs]); cs = (cs + 1) & 0x3FF; length -= 1
    return bytes(out)
def lzg_lr(src, n): return lzg(src, n)
def lzg_ud(src, n, stride, h): return lzg(src, n, stride, h)

if __name__ == '__main__':
    d = DatFile(sys.argv[1]); out = sys.argv[2] if len(sys.argv) > 2 else None
    if out: os.makedirs(out, exist_ok=True)
    for rid in d.ids():
        r = d.resource(rid); kind = '?'
        if len(r) == 100 and rid % 50 == 0: kind = 'palette'
        try:
            img = d.image(rid)
            if img and 0 < img[0] <= 320 and 0 < img[1] <= 200 and (len(r) - 6) <= img[0]*img[1]: kind = 'image %dx%d %dbpp' % (img[0], img[1], img[3])
        except Exception: pass
        print(rid, len(r), kind, 'cksum ok' if d.checksum_ok(rid) else 'CKSUM BAD')
        if out and kind.startswith('image'):
            from PIL import Image
            w, h, rows, depth = img
            im = Image.new('P', (w, h)); px = im.load()
            for y in range(h):
                for x in range(w): px[x, y] = rows[y][x]
            im.save(os.path.join(out, 'res%d.png' % rid))
