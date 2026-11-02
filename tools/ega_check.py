#!/usr/bin/env python3
"""Render SDLPoP VGA art through the ega[] colour pairs in its .pal files (official EGA
look, 2-colour checker dither per palette entry), remapped to MZ-800 IGRB.
usage: ega_check.py <SDLPoP/data> <out.png>"""
import sys, os
from PIL import Image
sys.path.insert(0, os.path.dirname(__file__))
from palette_check import MZ
# EGA colour number -> MZ-800 IGRB colour number (EGA order is IRGB, MZ order is IGRB)
EGA2MZ = [0, 1, 4, 5, 2, 3, 6, 7, 8, 9, 12, 13, 10, 11, 14, 15]

def ega_pairs(palfile):
    if not os.path.exists(palfile): return None
    b = open(palfile, 'rb').read()
    ega = b[68:100]
    if not any(ega): return None
    return [(ega[i] >> 4, ega[i] & 15, 0) for i in range(16)]  # one byte per colour: two EGA indices to dither

def convert(png, pairs):
    im = Image.open(png); assert im.mode == 'P'
    if pairs is None:  # no EGA table in this .pal: nearest-colour fallback
        from palette_check import convert as conv
        return conv(im)
    out = Image.new('RGBA', im.size); px = im.load(); po = out.load()
    tr = im.info.get('transparency', 0)
    for y in range(im.size[1]):
        for x in range(im.size[0]):
            i = px[x, y]
            if i == tr: po[x, y] = (0, 0, 0, 0); continue
            a, b, _ = pairs[i]
            c = a if (x + y) & 1 == 0 else b
            po[x, y] = MZ[EGA2MZ[c]] + (255,)
    return out

def main():
    root, out = sys.argv[1], sys.argv[2]
    sets = [('KID', 400, [401,402,403,404,405,406,410,415,420,430,440,450,460,470,480,500]),
            ('PRINCE', 150, [151,152,153,154,155,156,157,158,161,162,163,164]),
            ('PRINCE', 700, [701,702,703,704,705,706])]
    scale = 4; rows = []
    for name, pal, ids in sets:
        pairs = ega_pairs(os.path.join(root, name, 'res%d.pal' % pal))
        print(name, 'ega pairs:', pairs and [(a, b) for a, b, _ in pairs])
        tiles = []
        for i in ids:
            p = os.path.join(root, name, 'res%d.png' % i)
            if os.path.exists(p): tiles.append((Image.open(p).convert('RGBA'), convert(p, pairs)))
        h = max(t[0].size[1] for t in tiles); w = sum(t[0].size[0] + 4 for t in tiles)
        row = Image.new('RGBA', (w * scale, (2 * h + 8) * scale), (40, 40, 40, 255)); x = 0
        for a, b in tiles:
            row.paste(a.resize((a.size[0]*scale, a.size[1]*scale), Image.NEAREST), (x*scale, 0))
            row.paste(b.resize((b.size[0]*scale, b.size[1]*scale), Image.NEAREST), (x*scale, (h+8)*scale))
            x += a.size[0] + 4
        rows.append(row)
    W = max(r.size[0] for r in rows); H = sum(r.size[1] + 8 for r in rows)
    sheet = Image.new('RGBA', (W, H), (40, 40, 40, 255)); y = 0
    for r in rows: sheet.paste(r, (0, y)); y += r.size[1] + 8
    sheet.save(out); print('wrote', out)
main()
