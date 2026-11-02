#!/usr/bin/env python3
"""Compare tools/popdata.py's room renderer against SDLPoP's own level map screenshot
(external/SDLPoP/prince megahit N --screenshot-level), pixel by pixel after mapping both to
the MZ-800 palette. Rows 0..188 of each room (the map packs rooms 189 px apart)."""
import os, sys, subprocess
os.environ['POP_NO_PALETTE_OVERRIDES'] = '1'   # geometry/logic check: both sides use nearest-colour mapping
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from popdata import Level, RoomRenderer
from palette_check import nearest, MZ
from PIL import Image
SDLPOP = os.path.join(ROOT, 'external', 'SDLPoP')

def oracle_map(level_no):
    shots = os.path.join(SDLPOP, 'screenshots')
    for f in os.listdir(shots) if os.path.isdir(shots) else []: os.remove(os.path.join(shots, f))
    os.makedirs(shots, exist_ok=True)
    env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    subprocess.run(['./prince', 'megahit', str(level_no), '--screenshot-level'], cwd=SDLPOP, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    return Image.open(os.path.join(shots, 'screenshot_000.png')).convert('RGB')

def layout(level):
    """BFS placement exactly as SDLPoP save_level_screenshot (start room at 0,0)."""
    dx = [-1, 1, 0, 0]; dy = [0, 0, -1, 1]
    xpos = {level.start_room: 0}; ypos = {level.start_room: 0}
    queue = [level.start_room]; qi = 0
    while qi < len(queue):
        r = queue[qi]; qi += 1
        for d in range(4):
            o = level.roomlinks[r-1][d]
            if 1 <= o <= 24 and o not in xpos:
                xpos[o] = xpos[r] + dx[d]; ypos[o] = ypos[r] + dy[d]; queue.append(o)
    minx = min(xpos.values()); miny = min(ypos.values())
    return {r: (xpos[r]-minx, ypos[r]-miny) for r in xpos}

def main():
    lv = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    level = Level(lv); rr = RoomRenderer(level)
    omap = oracle_map(lv); pos = layout(level)
    # map oracle RGB through the same per-set colour tables the renderer uses (tools/palettes.json),
    # so tuned palettes still compare exactly; unknown RGBs fall back to nearest-colour
    table = {}
    for iset in (rr.obj, rr.wall, rr.env):      # env last: it wins on shared RGBs
        for rgb in iset.pal_rgb()[1:]: table[rgb] = iset.colour(rgb)
    cache = {}
    def mz(rgb):
        if rgb not in cache: cache[rgb] = table.get(rgb, nearest(rgb))
        return cache[rgb]
    total = 0; report = []
    cols = 6; rows = (len(pos) + cols - 1) // cols
    sheet = Image.new('RGB', (cols*322, rows*2*192), (40, 40, 40))
    for i, room in enumerate(sorted(pos)):
        x, y = pos[room]
        crop = omap.crop((x*320, y*189, x*320+320, y*189+189))
        mine = rr.draw_room(room)
        # ignore dynamic items SDLPoP draws differently (animated flames recoloured by its coloured-torch
        # extension, potion bubbles, torch flames mid-animation): everything drawn from chtab 1 ids 1..9, 16..23
        ignore = set()
        for tbl in ('back', 'fore', 'mid'):
            for (ch, id1, xo, yo, blit) in rr.ops[tbl]:
                if ch == 1 and (1 <= id1 <= 9 or 16 <= id1 <= 23):
                    w, h, _ = rr.sets[ch].get(id1)
                    for yy in range(max(0, yo), min(189, yo + h)):
                        for xx in range(max(0, xo), min(320, xo + w)): ignore.add((xx, yy))
        pm, po = mine.load(), crop.load(); bad = 0
        diff = Image.new('RGB', (320, 189)); pd = diff.load()
        for yy in range(189):
            for xx in range(320):
                a = pm[xx, yy]; b = mz(po[xx, yy])
                if a != b and (xx, yy) not in ignore: bad += 1; pd[xx, yy] = (255, 0, 0)
                else: pd[xx, yy] = MZ[a]
        total += bad; report.append((room, bad))
        sheet.paste(mine.convert('RGB').crop((0, 0, 320, 189)), ((i % cols)*322, (i // cols)*2*192))
        sheet.paste(diff, ((i % cols)*322, (i // cols)*2*192 + 192))
    sheet.save(os.path.join(ROOT, 'build', 'm2_oracle_level%d.png' % lv))
    print('level %d: %d rooms, %d differing pixels total' % (lv, len(pos), total))
    print(' per room:', ' '.join('%d:%d' % rb for rb in report))

if __name__ == '__main__': main()
