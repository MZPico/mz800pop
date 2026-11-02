#!/usr/bin/env python3
"""Build a planar image pack for the MZ-800 from SDLPoP PNGs.

Pack format (lives in the RAM disk):
  per image: [mask plane, inverted (if flagged)] plane0 plane1 plane2 plane3; each plane = h rows x wbytes,
  bit 0 = leftmost pixel, plane p = bit p of the MZ colour index (0 = B, 1 = R, 2 = G, 3 = I).
  Sprites (no mask flag): colour 0 is transparent and the mask is derived at run time.
Directory (lives in RAM, 8 bytes per id):
  page, addr_hi, addr_lo, wbytes, height, flags (bit0 = mask plane present), 0, 0

usage: pack.py <manifest.json> <out.pack> <out.dir> <out.json>
manifest: {"root": "<SDLPoP data dir>", "images": [{"id": n, "set": "KID", "res": 401, "mask": false}, ...]}
"""
import json, os, sys
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from palette_check import nearest

def planar(png, want_mask):
    im = Image.open(png); assert im.mode == 'P'
    tr = 0   # SDLPoP colour-keys index 0 regardless of the PNG's tRNS chunk
    pal = im.getpalette()
    cmap = {}
    px = im.load(); w, h = im.size; wb = (w + 7) // 8
    planes = [bytearray(wb * h) for _ in range(4)]; mask = bytearray(wb * h)
    for y in range(h):
        for x in range(w):
            i = px[x, y]
            if i == tr: continue
            if i not in cmap: cmap[i] = nearest(tuple(pal[i*3:i*3+3]))
            c = cmap[i]
            if not want_mask and c == 0: c = 8   # sprites: keep opaque black visible as dark grey
            bit = 1 << (x & 7); o = y * wb + (x >> 3)
            mask[o] |= bit
            for p in range(4):
                if c & (1 << p): planes[p][o] |= bit
    data = (bytes(b ^ 0xFF for b in mask) if want_mask else b'') + b''.join(bytes(p) for p in planes)   # mask inverted
    return wb, h, data

def main():
    man = json.load(open(sys.argv[1]))
    pack = bytearray(); dirb = bytearray(); info = {}
    for img in man['images']:
        png = os.path.join(man['root'], img['set'], 'res%d.png' % img['res'])
        wb, h, data = planar(png, img.get('mask', False))
        off = len(pack); assert off + len(data) < 0x1000000
        flags = 1 if img.get('mask') else 0
        entry = bytes([off >> 16, (off >> 8) & 255, off & 255, wb, h, flags, 0, 0])
        while len(dirb) < img['id'] * 8: dirb += b'\0' * 8
        dirb += entry; pack += data
        info[img['id']] = {'set': img['set'], 'res': img['res'], 'wbytes': wb, 'h': h, 'offset': off, 'mask': bool(flags)}
    open(sys.argv[2], 'wb').write(pack); open(sys.argv[3], 'wb').write(dirb)
    json.dump(info, open(sys.argv[4], 'w'), indent=1)
    print('pack %d bytes, %d images, dir %d bytes' % (len(pack), len(info), len(dirb)))

if __name__ == '__main__': main()
