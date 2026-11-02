#!/usr/bin/env python3
"""Map SDLPoP VGA art to the MZ-800 fixed IGRB palette and build a comparison sheet.

usage: palette_check.py <SDLPoP/data> <out.png>
"""
import sys, os
from PIL import Image

MZ = [  # index: measured RGB (mz800emu / Brazda)
    (0x00,0x00,0x00),(0x40,0x40,0xAC),(0xD0,0x34,0x00),(0xB4,0x0C,0x8C),
    (0x40,0x6C,0x00),(0x24,0xCC,0xFF),(0xE8,0xD4,0x30),(0xD0,0xD0,0xD0),
    (0x84,0x84,0x84),(0x00,0x8C,0xE8),(0xFF,0x00,0x00),(0xF0,0x54,0xCC),
    (0x54,0xFF,0x54),(0x80,0xFF,0xFF),(0xFF,0xFF,0x28),(0xFF,0xFF,0xFF)]

def lum(c): return 0.299*c[0]+0.587*c[1]+0.114*c[2]

def nearest(rgb):
    # weighted RGB distance with a luminance term so greys stay greys
    best=None
    for i,m in enumerate(MZ):
        d=(2*(rgb[0]-m[0])**2+4*(rgb[1]-m[1])**2+3*(rgb[2]-m[2])**2)/9.0 + 2*(lum(rgb)-lum(m))**2
        if best is None or d<best[0]: best=(d,i)
    return best[1]

def convert(im):
    im=im.convert('RGBA')
    out=Image.new('RGBA',im.size)
    px=im.load(); po=out.load()
    for y in range(im.size[1]):
        for x in range(im.size[0]):
            r,g,b,a=px[x,y]
            if a==0: po[x,y]=(0,0,0,0)
            else: po[x,y]=MZ[nearest((r,g,b))]+(255,)
    return out

def pal_map(png):
    im=Image.open(png)
    if im.mode!='P': return []
    pal=im.getpalette()[:48]
    return [(tuple(pal[i*3:i*3+3]), nearest(tuple(pal[i*3:i*3+3]))) for i in range(16)]

def main():
    root,out=sys.argv[1],sys.argv[2]
    sets=[('VDUNGEON',[214,215,216,217,230,231,232,233,250,251,260,261,270,280,290,300]),
          ('VPALACE',[201,202,203,204,214,215,216,217,230,231,240,250,260,270,280,290]),
          ('KID',[401,402,403,404,405,406,410,415,420,430,440,450,460,470,480,500]),
          ('GUARD',[751,752,753,754,755,756,760,765]),
          ('PRINCE',[151,152,153,154,155,156,157,158])]
    scale=2; rows=[]
    for name,ids in sets:
        tiles=[]
        for i in ids:
            p=os.path.join(root,name,'res%d.png'%i)
            if not os.path.exists(p): continue
            im=Image.open(p); tiles.append((im.convert('RGBA'),convert(im)))
        if not tiles: continue
        h=max(t[0].size[1] for t in tiles)
        w=sum(t[0].size[0]+4 for t in tiles)
        row=Image.new('RGBA',(w*scale,(2*h+8)*scale),(40,40,40,255))
        x=0
        for a,b in tiles:
            row.paste(a.resize((a.size[0]*scale,a.size[1]*scale),Image.NEAREST),(x*scale,0))
            row.paste(b.resize((b.size[0]*scale,b.size[1]*scale),Image.NEAREST),(x*scale,(h+8)*scale))
            x+=a.size[0]+4
        rows.append(row)
        print(name,'palette ->',[m for _,m in pal_map(os.path.join(root,name,'res%d.png'%ids[0]))])
    W=max(r.size[0] for r in rows); H=sum(r.size[1]+8 for r in rows)
    sheet=Image.new('RGBA',(W,H),(40,40,40,255)); y=0
    for r in rows: sheet.paste(r,(0,y)); y+=r.size[1]+8
    sheet.save(out); print('wrote',out,sheet.size)

if __name__=='__main__': main()
