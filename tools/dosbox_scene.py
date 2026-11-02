#!/usr/bin/env python3
"""M7 step 8: record a scene of the DOS original's EGA version in DOSBox (as tools/dosbox_title.py: Xvfb + ffmpeg at 50
frames a second; output only under build/dosbox/scene/, derived from the DOS game: never into the repository).
Keys are sent with xdotool at given times.
The game runs from a copy (build/dosbox/scene/game) with a prepared PRINCE.SAV (--save level:rem_min:rem_tick:hitp): Ctrl+L
at the title (as "--keys 3:ctrl+l") then starts that level through its cutscene: no cheats needed.
usage: dosbox_scene.py NAME SECONDS [--cycles N] [--args ""] [--save L:M:T:H] [--keys "T:key[,T:key...]"]
       key: a keysym, or key@SECS to hold it
       dosbox_scene.py compare NAME <level|scene> REM_MIN FROM TO: the recording's frames FROM..TO against cutsim's render:
       per change of the screen the best cutsim frame and the pixels that differ, the torches, the stars and the mouse
       cursor left out"""
import os, shutil, struct, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, 'build', 'dosbox', 'scene')
COPYPROT = 0x1b89b       # the copy protection level in PRINCE.EXE v1.3 (SDLPoP options.c)

def record(name, seconds, cycles=3000, args='', keys=(), disp=':78', save=None):
    os.makedirs(OUT, exist_ok=True)
    game = os.path.join(OUT, 'game')
    if not os.path.isdir(game):
        shutil.copytree(os.path.join(ROOT, 'external', 'dos', 'PRINCE'), game)
        for root, ds, fs in os.walk(game):
            for f in fs: os.chmod(os.path.join(root, f), 0o644)
        ex = bytearray(open(os.path.join(game, 'PRINCE.EXE'), 'rb').read())
        assert ex[COPYPROT:COPYPROT + 2] == b'\x02\0', 'not the v1.3 EXE (SDLPoP options.c copyprot_level offsets)'
        ex[COPYPROT:COPYPROT + 2] = b'\0\0'             # (in this private copy: a save's level starts without the potion test)
        open(os.path.join(game, 'PRINCE.EXE'), 'wb').write(ex)
    if save:
        lv, m, t, h = save        # (SDLPoP process_save: rem_min, rem_tick, current_level, hitp_beg_lev: words)
        open(os.path.join(game, 'PRINCE.SAV'), 'wb').write(struct.pack('<HHHH', m, t, lv, h))
    conf = os.path.join(OUT, name + '.conf')
    src = open(os.path.join(ROOT, 'build', 'dosbox', 'pop.conf')).read().splitlines()
    L = []
    for l in src:
        if l.startswith('captures='): l = 'captures=' + OUT
        if l.startswith('cycles='): l = 'cycles=%d' % cycles
        if l.strip() == 'prince' and args: l = 'prince ' + args
        if l.startswith('mount c'): l = 'mount c ' + game
        L.append(l)
    open(conf, 'w').write('\n'.join(L) + '\n')
    x = subprocess.Popen(['Xvfb', disp, '-screen', '0', '800x600x24'], stderr=subprocess.DEVNULL)
    time.sleep(1)
    env = dict(os.environ, DISPLAY=disp)
    d = subprocess.Popen(['dosbox', '-conf', conf], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.5)
    ff = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'x11grab', '-framerate', '50', '-video_size', '640x400',
                           '-i', disp + '+80,100', '-t', str(seconds), '-c:v', 'ffv1', os.path.join(OUT, name + '.mkv')], env=env)
    t0 = time.time()
    for t, k in sorted(keys):
        dt = t - (time.time() - t0)
        if dt > 0: time.sleep(dt)
        k, _, hold = k.partition('@')
        if hold:
            subprocess.run(['xdotool', 'keydown', k], env=env); time.sleep(float(hold)); subprocess.run(['xdotool', 'keyup', k], env=env)
        else:
            subprocess.run(['xdotool', 'key', k], env=env)
    ff.wait(); d.kill(); x.kill()

def compare(name, scene, rem, a, b):
    import numpy as np
    sys.path.insert(0, HERE)
    import cutsim
    from popdata import EGA_RGB
    cs = cutsim.named_scene(scene, rem) if scene in cutsim.SCENE_IMGS else cutsim.level_scene(int(scene), rem)
    rgb = np.array(EGA_RGB)
    ega = [cutsim.EGA2MZ.index(i) for i in range(16)]
    lut = np.array([EGA_RGB[ega[i]] for i in range(16)]); lut[cutsim.BLACK0] = (0, 0, 0)    # (MZ 4 shows black)
    scr = np.array(list(cutsim.Render(cs).screens()))
    mz = lut[scr]
    mask = np.ones((200, 320), bool)
    mask[99:117, 88:112] = 0; mask[99:117, 205:230] = 0; mask[94:106, 150:167] = 0
    for x, y, _ in cutsim.STARS: mask[y, x] = 0
    path = os.path.join(OUT, name + '.mkv')
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', path, '-vf', 'scale=320:200:flags=neighbor', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE)
    n = 0; prev = None; res = []
    while n <= b:
        d = p.stdout.read(192000)
        if len(d) < 192000: break
        if n >= a:
            f = np.frombuffer(d, np.uint8).reshape(200, 320, 3).astype(int)
            if prev is None or (f != prev).any():
                ds = ((mz != f[None]).any(3) & mask[None]).sum((1, 2))
                m = int(ds.argmin()); res.append((n, m, int(ds[m])))
            prev = f
        n += 1
    p.kill()
    return res, len(cs.frames)

if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'compare':
        res, nf = compare(a[1], a[2], int(a[3]), int(a[4]), int(a[5]))
        for n, m, d in res: print('video frame %5d: best cutsim frame %3d, %5d pixels differ' % (n, m, d))
        import collections
        print('of %d frames: the changes\' differences %s' % (nf, sorted(collections.Counter(d for _, _, d in res).items())[:8]))
        sys.exit(0)
    def opt(n, dflt):
        if n in a:
            i = a.index(n); v = a[i + 1]; del a[i:i + 2]; return v
        return dflt
    cyc = int(opt('--cycles', 3000)); args = opt('--args', ''); sv = opt('--save', ''); keys = opt('--keys', '')
    keys = [(float(p.split(':')[0]), p.split(':', 1)[1]) for p in keys.split(',') if p]
    record(a[0], int(a[1]), cyc, args, keys, save=tuple(int(v) for v in sv.split(':')) if sv else None)
