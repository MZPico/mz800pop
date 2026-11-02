#!/usr/bin/env python3
"""Check the EGA room renderer against a DOSBox capture of the real game (machine=ega).
Capture: build/dosbox/capture/prince_003.png = level 1, room 1, prince standing at the start.
Pixels under the prince and the two torch flames are ignored (animated / sprite)."""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from popdata import Level, RoomRenderer, EGA_RGB, EGA2MZ
from PIL import Image

def ega_idx(rgb): return min(range(16), key=lambda i: sum((a-b)**2 for a,b in zip(rgb, EGA_RGB[i])))

def main():
    cap_path = os.path.join(ROOT, 'build', 'dosbox', 'capture', 'prince_003.png')
    if not os.path.exists(cap_path): print('no DOSBox capture, skipping'); return
    cap = Image.open(cap_path).convert('RGB'); pc = cap.load()
    rr = RoomRenderer(Level(1), ega=True); im = rr.draw_room(1); pm = im.load()
    ignore = set((x, y) for x in range(28, 50) for y in range(70, 120))            # prince
    ignore |= set((x, y) for x in range(0, 24) for y in range(0, 64))              # the gate the prince fell through, still closing
    for tbl in ('back', 'fore', 'mid'):
        for (ch, id1, xo, yo, blit) in rr.ops[tbl]:
            if ch == 1 and 1 <= id1 <= 9:                                           # flames
                w, h, _ = rr.sets[ch].get(id1)
                ignore.update((x, y) for x in range(xo, xo + w) for y in range(yo, yo + h))
    bad = [(x, y) for y in range(192) for x in range(320) if (x, y) not in ignore and pm[x, y] != EGA2MZ[ega_idx(pc[x, y])]]
    print('EGA room 1 vs DOSBox capture: %d differing pixels (outside prince/flames)' % len(bad), bad[:5])
    assert len(bad) == 0, bad[:10]
    print('EGA capture test OK')

if __name__ == '__main__': main()
