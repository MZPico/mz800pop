#!/usr/bin/env python3
"""M7 step 7: the level cutscenes' silhouettes against SDLPoP's own screens (VGA colours: only the shapes and places can
be compared with the EGA reference render), as M6's guard drawing was checked. tools/cut_suite.py --shots DIR saves
SDLPoP's screen of every cutscene frame and the room before the first frame (cut_bg.bmp: fade_in_1's screen, no
objects). Per frame, cutsim's objects cover a set of pixels (the opaque pixels of the sprites it draws, a torch's whole
box); SDLPoP's silhouette = its pixels that differ from its room. (The pillar is left out of the cover: it is drawn on the room's own pillar.) Then:
  outside  SDLPoP's silhouette pixels where cutsim draws nothing (a misplaced, missing or extra object): 0 expected;
  inside   cutsim's covered pixels that SDLPoP's silhouette lacks: VGA sprite pixels the colour of the VGA background
           (coincidences, reported only).
The stars are left out (SDLPoP continues their colours from earlier scenes, the reference starts fresh).
usage: cut_shots.py DIR level:rem_min ...   (DIR as given to cut_suite.py --shots; writes DIR/<case>_sil.png, the worst
frame: cutsim's cover green, SDLPoP's silhouette blue, outside pixels white)"""
import os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cutsim

def cover(cs, f):
    m = np.zeros((200, 320), bool)
    for (tab, ch, idx, ox, yb, blit, flip, peel, slot) in f['objs']:
        if (ch, idx) == (8, 1): continue                      # (the pillar: drawn on the room's own pillar)
        fl = flip and ch in (2, 3, 4)
        w, h, rows = cutsim.sprite(ch, idx, cs.which_imgs if cs.which_imgs is not None else 1, 0, 0, fl)
        if fl: ox -= w
        clip = 192 if ch in (2, 3, 4) else 200
        for yy in range(h):
            y = yb - h + 1 + yy
            if not 0 <= y < clip: continue
            for xx in range(w):
                if (rows[yy][xx] >= 0 or blit == 'copy') and 0 <= ox + xx < 320: m[y, ox + xx] = True
    return m

def compare(d, lv, rm):
    from PIL import Image
    import cut_suite
    cs = cut_suite.sim(lv, rm)
    shots = []
    for k in range(len(cs.frames)):
        im = np.array(Image.open(os.path.join(d, '%s_%d' % (lv, rm), 'cut_%d.bmp' % k)).convert('RGB')).astype(np.int64)
        shots.append(im[:, :, 0] * 65536 + im[:, :, 1] * 256 + im[:, :, 2])
    shots = np.stack(shots)
    cov = np.stack([cover(cs, f) for f in cs.frames])
    im = np.array(Image.open(os.path.join(d, '%s_%d' % (lv, rm), 'cut_bg.bmp')).convert('RGB')).astype(np.int64)
    bg = im[:, :, 0] * 65536 + im[:, :, 1] * 256 + im[:, :, 2]
    known = np.ones((200, 320), bool)
    stars = np.zeros((200, 320), bool)
    for x, y, _ in cutsim.STARS: stars[y, x] = True
    use = known & ~stars
    out = []
    for k in range(len(cs.frames)):
        sil = (shots[k] != bg) & use
        out.append((int((sil & ~cov[k]).sum()), int((cov[k] & use & ~sil).sum()), int((cov[k] & use).sum())))
    worst = max(range(len(out)), key=lambda k: (out[k][0], out[k][1]))
    sil = (shots[worst] != bg) & use
    img = np.zeros((200, 320, 3), np.uint8); img[cov[worst]] = (0, 120, 0); img[sil] = (0, 0, 200); img[sil & ~cov[worst]] = (255, 255, 255)
    Image.fromarray(img).resize((640, 400), 0).save(os.path.join(d, '%s_%d_sil.png' % (lv, rm)))
    return out, worst, int((~known).sum())

if __name__ == '__main__':
    d = sys.argv[1]; bad = 0
    for a in sys.argv[2:]:
        lv, rm = a.split(':'); lv = int(lv) if lv.isdigit() else lv; rm = int(rm)
        out, worst, unknown = compare(d, lv, rm)
        o = sum(x[0] for x in out); i = sum(x[1] for x in out); c = sum(x[2] for x in out)
        print('level %2s rem_min %2d: %3d frames, %6d covered pixels; SDLPoP silhouette outside cutsim\'s objects: %d; covered '
              'but not in SDLPoP\'s silhouette (colour coincidences): %d (%.1f%%)' % (
              lv, rm, len(out), c, o, i, 100.0 * i / max(c, 1)))
        bad += o
    sys.exit(1 if bad else 0)
