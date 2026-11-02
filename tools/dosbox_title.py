#!/usr/bin/env python3
"""M7 step 6 (decision D8): record the DOS original's EGA title in DOSBox and analyse it (docs/m7-design.md §15).
DOSBox (build/dosbox/pop.conf: machine=ega, the game in external/dos/PRINCE) runs in a virtual X server (Xvfb); ffmpeg
grabs its window at 50 frames a second (DOSBox's own capture keys do not reach it there). The recording and the
frames stay in build/dosbox/title/ (derived from the DOS game: never into the repository). The analysis:
  - every frame that changes more than CHANGE pixels: the rows it touched (a fade pass touches the rows y mod 5 = k),
    the columns (a wipe moves left to right) and whether colours changed in place (a palette fade would);
  - the stable screens against tools/titleref.py (the reference the MZ title is tested against), the mouse cursor's
    square excluded.
The window must sit where Xvfb puts it (0, 0 .. 640 x 400 at 2x: DOSBox centres it in an 800 x 600 screen at 80, 100).
usage: dosbox_title.py [--record SECONDS] [--analyse]"""
import os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
OUT = os.path.join(ROOT, 'build', 'dosbox', 'title')
CHANGE = 1500
CURSOR = (150, 94, 166, 105)          # the DOSBox mouse cursor at the window's centre (x0, y0, x1, y1)

def record(seconds):
    os.makedirs(OUT, exist_ok=True)
    conf = os.path.join(OUT, 'pop.conf')
    src = open(os.path.join(ROOT, 'build', 'dosbox', 'pop.conf')).read()
    open(conf, 'w').write('\n'.join(l if not l.startswith('captures=') else 'captures=' + OUT for l in src.splitlines()) + '\n')
    disp = ':77'
    x = subprocess.Popen(['Xvfb', disp, '-screen', '0', '800x600x24'], stderr=subprocess.DEVNULL)
    time.sleep(1)
    env = dict(os.environ, DISPLAY=disp)
    d = subprocess.Popen(['dosbox', '-conf', conf], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.5)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'x11grab', '-framerate', '50', '-video_size', '640x400',
                    '-i', disp + '+80,100', '-t', str(seconds), '-c:v', 'ffv1', os.path.join(OUT, 'title.mkv')], env=env)
    d.kill(); x.kill()

def frames():
    import numpy as np
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', os.path.join(OUT, 'title.mkv'), '-vf', 'scale=320:200:flags=neighbor',
                          '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE)
    while True:
        b = p.stdout.read(320 * 200 * 3)
        if len(b) < 320 * 200 * 3: return
        yield np.frombuffer(b, np.uint8).reshape(200, 320, 3).astype(int)

def analyse():
    import numpy as np
    import titleref as T
    from popdata import EGA_RGB, EGA2MZ
    rgb = np.array(EGA_RGB)
    def mz(f):
        idx = ((f[:, :, None, :] - rgb[None, None]) ** 2).sum(3).argmin(2)
        return [[EGA2MZ[v] for v in row] for row in idx.tolist()]
    refs = {'+'.join(n): T.screen(n) for n in (['MAIN'], ['MAIN', 'PRESENTS'], ['MAIN', 'GAME'], ['MAIN', 'POP', 'MECHNER'],
                                               ['FRAME', 'ABSENCE'], ['FRAME', 'MARRY'], ['FRAME', 'CREDITS'])}
    x0, y0, x1, y1 = CURSOR
    prev = None; still = 0; matched = {}
    for n, f in enumerate(frames()):
        if prev is not None:
            ch = np.abs(f - prev).sum(2) > 0; c = int(ch.sum())
            if c > CHANGE:
                rows = np.where(ch.any(1))[0]; cols = np.where(ch.any(0))[0]
                recol = int((ch & (f.sum(2) > 0) & (prev.sum(2) > 0)).sum())
                print('%5d %6.2f s: %5d pixels, rows %3d-%3d (mod 5: %s), columns %3d-%3d, recoloured in place %d' % (
                    n, n / 50, c, rows.min(), rows.max(), ''.join(str(v) for v in sorted(set(rows % 5))), cols.min(),
                    cols.max(), recol))
            if c > 200: still = 0             # (the torches and stars of pv_scene flicker below this)
            else: still += 1
            if still == 25:                     # half a second without a change: a stable screen
                s = mz(f)
                for name, ref in refs.items():
                    d = [(x, y) for x, y in T.diff(s, ref) if not (x0 <= x <= x1 and y0 <= y <= y1)]
                    if not d:
                        matched.setdefault(name, []).append(round(n / 50, 1)); print('       stable screen = %s' % name)
        prev = f
    print('screens matching tools/titleref.py pixel for pixel (outside the cursor): %s' % matched)

if __name__ == '__main__':
    a = sys.argv[1:]
    if '--record' in a: record(int(a[a.index('--record') + 1]))
    if '--analyse' in a or not a: analyse()
