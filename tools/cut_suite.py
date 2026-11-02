#!/usr/bin/env python3
"""M7 steps 7-8: tools/cutsim.py against SDLPoP for every cutscene. Each case runs SDLPoP ('prince megahit N' with
the oracle hook POP800_CUT=<rem_min>, external/SDLPoP/src/pop800_trace.c: the cutscene play_level runs before level
N, or with POP800_CUT_SCENE pv_scene / time_expired / end_sequence_anim; deterministic: seed 12345, the ticks sound model
at 60 a second with cutsim's lengths, one frame in each EGA fade) and cutsim's scene, and compares the 'C' lines (one per
cutscene frame) and the 'W' line exactly.
Cases: levels 2, 4, 6, 8, 9, 12 at rem_min 60, 30, 10, 3 (hourglass states 3, 4, 5, 6; level 12's short-time scene
below 6 minutes) and the boundaries 65, 33, 17, 6, 5, 1; the three named scenes.
With --shots DIR the SDLPoP screens of every frame are saved too (DIR/<level>_<rem_min>/cut_<n>.bmp, VGA colours).
usage: cut_suite.py [--shots DIR] [level[:rem_min] | pv | expired | ending ...]"""
import os, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import cutsim

LEVELS = (2, 4, 6, 8, 9, 12)
TIMES = (60, 30, 10, 3)
BOUNDS = (65, 33, 17, 6, 5, 1)

SCENES = {'pv': 'pv_scene', 'expired': 'time_expired', 'ending': 'end_sequence_anim'}

def sdlpop(level, rem_min, shots=None):
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, 'cut.txt')
        env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', POP800_CUT=str(rem_min),
                   POP800_TRACE=out, POP800_CUT_TICKS=','.join(str(cutsim.sound_ticks60(i))
                                                            for i in range(len(cutsim.SOUND_SECONDS))))
        if shots: os.makedirs(shots, exist_ok=True); env['POP800_CUT_SHOTS'] = os.path.abspath(shots)
        if level in SCENES: env['POP800_CUT_SCENE'] = level; level = 1
        subprocess.run([os.path.join(ROOT, 'external', 'SDLPoP', 'prince'), 'megahit', str(level)],
                       cwd=os.path.join(ROOT, 'external', 'SDLPoP'), env=env, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=300)
        return open(out).read().split('\n')[:-1] if os.path.exists(out) else []

def sim(level, rem_min):
    return cutsim.named_scene(SCENES[level], rem_min) if level in SCENES else cutsim.level_scene(level, rem_min)

def check(level, rem_min, shots=None):
    a = sdlpop(level, rem_min, shots)
    b = sim(level, rem_min).lines
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y: return len(b), (i, x, y)
    if len(a) != len(b): return len(b), (min(len(a), len(b)), 'length %d' % len(a), 'length %d' % len(b))
    return len(b), None

def main():
    args = sys.argv[1:]; shots = None
    if '--shots' in args: i = args.index('--shots'); shots = args[i + 1]; del args[i:i + 2]
    cases = []
    for a in args:
        if a in SCENES: cases.append((a, 60)); continue
        lv, _, rm = a.partition(':')
        cases += [(int(lv), int(rm))] if rm else [(int(lv), t) for t in TIMES]
    if not cases: cases = [(lv, t) for lv in LEVELS for t in TIMES + BOUNDS] + [(n, 60) for n in SCENES]
    bad = 0
    for lv, rm in cases:
        n, d = check(lv, rm, os.path.join(shots, '%s_%d' % (lv, rm)) if shots else None)
        w = sim(lv, rm).lines[-1]
        print('level %2s rem_min %2d (%s): %3d lines (%s), %s' % (lv, rm, sim(lv, rm).scene, n, w,
              'cutsim matches SDLPoP' if not d else 'DIFF at line %d:\n  sdlpop %s\n  cutsim %s' % d))
        bad += d is not None
    print('%d of %d cases match' % (len(cases) - bad, len(cases)))
    sys.exit(1 if bad else 0)

if __name__ == '__main__':
    main()
