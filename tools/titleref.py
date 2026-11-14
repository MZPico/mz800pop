#!/usr/bin/env python3
"""M7 step 6: the Python reference render of the title (SDLPoP show_title, seg000.c, with the EGA art of TITLE.DAT)
for tests/m7_title.py. Independent of PRES's packs: the images come straight from the DAT (tools/datfile.py through
popdata.DatImageSet, the EGA colours of the chtab's palette resource: 40 for the story frame and texts, 50 for the
title images) and are drawn as SDLPoP's draw_full_image does with data.h's full_image table (build_assets.TITLE_IMAGES):
  copy    blitters_0_no_transp: every pixel of the image's w x h, index 0 black
  transp  blitters_10h_transp: index 0 transparent (the logo)
  mono    blitters_white (method_3_blit_mono): the 1-bpp text's set pixels in colour 15, the others untouched
Screens are 200 rows of 320 MZ colours (lists).
  screen(names)      the images drawn in order on a black screen, e.g. screen(['MAIN', 'POP', 'MECHNER'])
  STEPS              the title's steps (docs/m7-design.md §1.2) as PRES plays them in M7 step 6: (name, images on the
                     screen, SDLPoP ticks); step f's ticks: the ticks model of music 54 less F_EARLIER, the title
                     theme stopped F_MUSIC ticks into f (music_stop_tick: after TITLE_PASSES passes)
  wipe(old, new, n)  transition_ltr after n of PRES's 40 8-px columns (SDLPoP: 160 2-px columns, 4 per PRES column)
  fade_in(new, k)    the EGA fade-in after pass k (rows y mod 5 < k from the new screen; DOSBox, §15)
  loading()          the screen PRES starts from: black with the launcher's "LOADING..." (src/boot/boot.asm LN_LOADING:
                     msg_load, the loader's 5x7 font src/boot/font.inc at row 100, x 32, colour 7)
usage: titleref.py [out_dir]   (PNGs of the steps' screens)"""
import math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from build_assets import TITLE_IMAGES, title_image
from popdata import EGA_RGB, EGA2MZ
import kidsim

NAMES = {'MAIN': 51, 'PRESENTS': 52, 'GAME': 53, 'POP': 54, 'MECHNER': 55, 'FRAME': 41, 'ABSENCE': 42, 'MARRY': 43,
         'HAIL': 44, 'CREDITS': 45, 'FRAME_RED': 46}
LAYOUT = {r: (x, y, mode) for r, _, x, y, mode in TITLE_IMAGES}
WIPE_TICKS = 80             # transition_ltr: 160 steps at 120 a second
FADE_TICKS = 16             # fade_in_2: 5 passes 4 ticks apart; the music of step a starts with the last (tick 16)
MUSIC = 54
TITLE_PASSES = 2            # the title theme's passes in a-f (the user's decision, 2026-11-09)
F_EARLIER = 60              # ... and f ends 1 s before SDLPoP's (DOS) end of music 54

def music_end_ticks():
    """SDLPoP's step f lasts until music 54 ends: SDLPoP polls check_sound_playing once a tick, so the title's clock at
    f's end is the first whole tick after the music's length (the ticks model: kidsim SOUND_SECONDS)"""
    return math.ceil(kidsim.SOUND_SECONDS[MUSIC] * 60 - 1e-9)

def title_frames():
    """one pass of PRES's title theme (the Master System's song 1, looped whole) in 50 Hz frames"""
    import presbank
    return presbank.piece('title')['frames']

def music_stop_tick():
    """the title's tick at which PRES stops the title theme (step f's OP_MSTOP): the clock's frame floor(5 T / 6) is the
    one of the music's start (the fade-in's last pass, its first group at the next interrupt) + TITLE_PASSES passes, so
    the stop comes after the interrupt that played the last pass's last frame and before the one that would start the
    next pass: the smallest such tick"""
    f = FADE_TICKS * 5 // 6 + TITLE_PASSES * title_frames()
    t = -(-6 * f // 5)
    assert t * 5 // 6 == f
    return t

# (step, images on the screen at its end, its length in SDLPoP ticks; 'wipe' = transition_ltr first)
# A deviation from SDLPoP: its f waits until the DOS music 54 ends (music_end_ticks: 1502 ticks from a, 25.02 s); PRES
# plays the Master System's title theme (11.40 s) instead, which would loop to 22.80 s and be cut 2.2 s into a third
# pass by g's music. PRES plays it exactly TITLE_PASSES times (f stops it at music_stop_tick: F_MUSIC ticks into f) and
# ends f F_EARLIER ticks before SDLPoP: a-f AF_TICKS = 1442 ticks, ~1.2 s of silence on the logo before g.
_AE = (('a', ['MAIN'], 130), ('b', ['MAIN', 'PRESENTS'], 205), ('c', ['MAIN'], 65), ('d', ['MAIN', 'GAME'], 270),
       ('e', ['MAIN'], 235))
AE_TICKS = sum(t for *_, t in _AE)
AF_TICKS = music_end_ticks() - F_EARLIER
F_MUSIC = music_stop_tick() - FADE_TICKS - AE_TICKS
assert 0 < F_MUSIC < AF_TICKS - AE_TICKS
STEPS = list(_AE) + [('f', ['MAIN', 'POP', 'MECHNER'], AF_TICKS - AE_TICKS),
                     ('g', ['FRAME', 'ABSENCE'], WIPE_TICKS + 600)]
WIPES = ('g',)

def blank(): return [[0] * 320 for _ in range(200)]

def loading(text='LOADING...', x0=32, y0=100, col=7):
    import re
    font = [[int(v, 16) for v in re.findall(r'0x([0-9a-f]{2})', l)]
            for l in open(os.path.join(HERE, '..', 'src', 'boot', 'font.inc')) if l.strip().startswith('db')]
    s = blank()
    for i, ch in enumerate(text):
        g = font[ord(ch) - 0x20]
        for r in range(7):
            for b in range(8):
                if g[r] >> b & 1: s[y0 + r][x0 + 8 * i + b] = col
    return s

def draw(scr, name):
    res = NAMES[name]; x0, y0, mode = LAYOUT[res]
    w, h, rows = title_image(res)
    for y in range(h):
        row = rows[y]; out = scr[y0 + y]
        for x in range(w):
            c = row[x]
            if c < 0:
                if mode != 'copy': continue
                c = 0
            out[x0 + x] = c
    return scr

_CACHE = {}
def screen(names):
    key = tuple(names)
    if key not in _CACHE:
        s = blank()
        for n in names: draw(s, n)
        _CACHE[key] = s
    return [r[:] for r in _CACHE[key]]

def wipe(old, new, n):
    """the screen after n of the 40 wipe steps (columns of 8 pixels from the left)"""
    return [new[y][:8 * n] + old[y][8 * n:] for y in range(200)]

def fade_in(old, new, k):
    return [new[y][:] if y % 5 < k else old[y][:] for y in range(200)]

def from_planes(planes):
    """a screen from the four VRAM planes (8000 bytes each, bit 0 = leftmost pixel)"""
    out = []
    for y in range(200):
        row = []
        for xb in range(40):
            b = [p[y * 40 + xb] for p in planes]
            for bit in range(8):
                row.append(sum(((b[q] >> bit) & 1) << q for q in range(4)))
        out.append(row)
    return out

def diff(a, b):
    """[(x, y)] where two screens differ"""
    return [(x, y) for y in range(200) for x in range(320) if a[y][x] != b[y][x]]

MZ2EGA = [EGA2MZ.index(i) for i in range(16)]
def png(scr, path):
    from PIL import Image
    im = Image.new('RGB', (320, 200)); px = im.load()
    for y in range(200):
        for x in range(320): px[x, y] = EGA_RGB[MZ2EGA[scr[y][x]]]
    im.save(path)

if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', 'build', 'title_ref')
    os.makedirs(out, exist_ok=True)
    t = 0
    for step, names, ticks in STEPS:
        t += ticks
        png(screen(names), os.path.join(out, 'step_%s.png' % step))
        print('%s: %-28s %4d ticks (%.2f s), ends at tick %d' % (step, '+'.join(names), ticks, ticks / 60, t))
