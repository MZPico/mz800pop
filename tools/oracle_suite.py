#!/usr/bin/env python3
"""kidsim against SDLPoP for every control script: runs each script through the oracle (tools/oracle.py) and through
tools/kidsim.py and compares the traces tick by tick: kid lines, (scripts with guards) the 'G' guard lines, (scripts with
'# state') the 'S' level-event state lines, the 'N' sound lines (every script; kidsim in its silent sound mode, see
norm_sound) and the 'EXPIRED' / 'END' markers. Scripts with '# sound ticks' (tests/m7_scripts: SDLPoP's waits on sound
through the same ticks model, POP800_SOUND_TICKS, so they are deterministic) are compared exactly (compare_lines exact):
every N line field, the S lines and the whole script after a death too; alive up to 8 (SDLPoP's death timer stops
there, kidsim counts on: nothing reads it above 7).
usage: oracle_suite.py [script.txt ...]   (default: tests/m4_scripts, tests/m6_scripts, tests/m5_scripts, tests/m7_scripts)"""
import glob, os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import kidsim, oracle

def norm(l, dead=False):
    """kid lines: only the sign of alive is compared (SDLPoP's death timer waits on sounds). 'G' lines without a guard
    (direction 56): the Guard record's fields are dead state then (overwritten before anything reads them again; their
    values are what the level's intro cutscene or an earlier guard left), so only the globals are compared. 'S' lines
    after the kid's death (dead): is_show_time and the bottom text wait on the death sound in SDLPoP: not compared."""
    p = l.split()
    if p[0] == 'S' and dead: p[5:8] = ['-'] * 3
    if p[0] == 'G':
        if p[4] == '86': p[1:15] = ['-'] * 3 + [p[4]] + ['-'] * 10
    elif p[0] != 'S' and len(p) > 12: p[12] = str(min(int(p[12]), 0))
    return ' '.join(p)

DEATH_MUSIC = ('24', '28', '32')

def norm_sound(x, y, dead=False):
    """'N queued started playing stops' lines (x SDLPoP's, y kidsim's). The request side (queued: the tick's request
    after play_sound's priority rule; stops: stop_sounds calls) is deterministic and always compared. Whether
    play_next_sound starts it depends on check_sound_playing, which is real time in SDLPoP (SDL audio) and always 0 in
    kidsim's silent mode: started and playing are compared only where SDLPoP had no sound playing (then the start rule is
    the same in both). After the kid's death SDLPoP's death timer freezes while a sound plays, which moves the death
    music request (24, 28, 32) by real time: a line where either side queued it is not compared then."""
    a, b = x.split(), y.split()
    if len(a) != 5 or len(b) != 5: return x, y
    if dead and (a[1] in DEATH_MUSIC or b[1] in DEATH_MUSIC): return 'N -', 'N -'
    if a[3] != '0': a[2:4] = b[2:4] = ['-', '-']
    return ' '.join(a), ' '.join(b)

def check(script):
    lv = kidsim.script_level(script)
    with tempfile.TemporaryDirectory() as d:
        a = oracle.run(lv, script, os.path.join(d, 'trace.txt'))
    return compare_lines(a, kidsim.run_script(lv, script), exact=kidsim.script_opts(script)['sound'] == 'ticks')

def norm_exact(l):
    """the ticks model (exact): kid lines' alive capped at 8 (SDLPoP's death timer stops counting there)"""
    p = l.split()
    if p[0][0].isdigit() and len(p) > 12: p[12] = str(min(int(p[12]), 8))
    return ' '.join(p)

def compare_lines(a, b, exact=False):
    """a: the oracle's lines, b: kidsim's; returns (len(b), None or (line, sdlpop, kidsim) of the first difference)"""
    if exact:
        for i, (x, y) in enumerate(zip(a, b)):
            if norm_exact(x) != norm_exact(y): return len(b), (i, x, y)
        if len(a) != len(b): return len(b), (min(len(a), len(b)), 'length %d' % len(a), 'length %d' % len(b))
        return len(b), None
    cut = len(b); death = len(b)       # stop 8 kid ticks after a death
    for i, y in enumerate(b):
        if not y[0].isdigit(): continue
        if int(y.split()[12]) >= 0:
            death = i
            kids = [j for j in range(i, len(b)) if b[j][0].isdigit()]
            cut = kids[8] if len(kids) > 8 else len(b)
            break
    for i, (x, y) in enumerate(zip(a[:cut], b[:cut])):
        if x[0] == 'N' and y[0] == 'N':
            u, v = norm_sound(x, y, i >= death)
            if u != v: return len(b), (i, x, y)
        elif norm(x, i >= death) != norm(y, i >= death): return len(b), (i, x, y)
    if len(a[:cut]) != len(b[:cut]): return len(b), (min(len(a), len(b)), 'length %d' % len(a), 'length %d' % len(b))
    return len(b), None

if __name__ == '__main__':
    scripts = sys.argv[1:] or sorted(glob.glob(os.path.join(ROOT, 'tests', 'm4_scripts', '*.txt'))) + \
        sorted(glob.glob(os.path.join(ROOT, 'tests', 'm6_scripts', '*.txt'))) + \
        sorted(glob.glob(os.path.join(ROOT, 'tests', 'm5_scripts', '*.txt'))) + \
        sorted(glob.glob(os.path.join(ROOT, 'tests', 'm7_scripts', '*.txt')))
    bad = 0
    for s in scripts:
        n, d = check(s)
        if d: bad += 1
        print('%-26s %5d lines: %s' % (os.path.basename(s), n, 'matches SDLPoP' if not d else
              'first diff at line %d\n    sdlpop %s\n    kidsim %s' % d), flush=True)
    print('scripts differing: %d' % bad)
    sys.exit(1 if bad else 0)
