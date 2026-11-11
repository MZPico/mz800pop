#!/usr/bin/env python3
"""Duel phase 1 (docs/duel-design.md section 11): the scripted duels of tests/duel_scripts through tools/duelsim.py, the
duel's oracle (kidsim in duel mode; no emulator, no SDLPoP). Per script: two runs give the same trace (determinism),
and the script's expectations hold: '# expect rounds 1,2,3' (the round results in order: 1 P1, 2 P2, 3 draw),
'# expect score a:b' (at the end), '# expect match m' (the match state at the end), '# expect matches 1,0,3' (the match state's changes: 1 P1 won, 2 P2 won, 3 quit,
0 a rematch), '# expect mirror other.txt' (every tick is the other script's tick with the players swapped and the room
mirrored: x -> 270 - x), '# expect hurt none' (both keep their full hit points every tick), '# expect sheathe a,b' (the
ticks at which the kid and the shadow first put their drawn swords away), '# expect digest <hex>' (the whole trace's sha256, 16 digits: any change of the duel's
logic or of kidsim's shows here; --update rewrites it after an intended change). Any other expectation key fails.
usage: duel_test.py [--update] [script.txt ...]   (default: tests/duel_scripts/*.txt)"""
import glob, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import duelsim as D

EXPECT_KEYS = {'rounds', 'score', 'match', 'matches', 'mirror', 'digest', 'hurt', 'sheathe'}
MIRROR_X = 270           # the arena's start columns 2 and 7 face each other around x = 135


def match_changes(lines):
    seq = []; prev = 0
    for l in lines:
        if l.startswith('D ') and len(l.split()) > 9:
            m = int(l.split()[9])
            if m != prev: seq.append(m)
            prev = m
    return seq


def records(path):
    """per tick, the end of the tick's (kid, shadow): frame x direction action alive hit points"""
    inputs, opts = D.read_duel_script(path)
    sim = D.DuelSim(kid_frames=opts['p2_frames'] != 'shadow'); out = []
    for in1, in2 in inputs:
        sim.step(in1, in2); K, G = sim.Kid, sim.Guard
        out.append(((K.frame, K.x, K.direction, K.action, K.alive, sim.hitp_curr),
                    (G.frame, G.x, G.direction, G.action, G.alive, sim.guardhp_curr)))
    return out


def sheathed(path):
    """[the kid's, the shadow's first tick after the start with the sword sheathed again (0: never)]"""
    inputs, opts = D.read_duel_script(path)
    sim = D.DuelSim(kid_frames=opts['p2_frames'] != 'shadow'); drawn = [False, False]; out = [0, 0]
    for t, (in1, in2) in enumerate(inputs):
        sim.step(in1, in2)
        for p, c in enumerate((sim.Kid, sim.Guard)):
            if c.sword: drawn[p] = True
            elif drawn[p] and not out[p]: out[p] = t + 1
    return out


def mirrored(a, b):
    """script a's ticks are script b's with the players swapped: the same frames, actions, alive, hit points, opposite directions,
    x mirrored"""
    ra, rb = records(a), records(b)
    if len(ra) != len(rb): return 'lengths %d != %d' % (len(ra), len(rb))
    for t, ((ka, ga), (kb, gb)) in enumerate(zip(ra, rb)):
        for p, q in ((ka, gb), (ga, kb)):
            if (p[0], p[3], p[4], p[5]) != (q[0], q[3], q[4], q[5]) or p[1] != MIRROR_X - q[1] or p[2] == q[2]:
                return 'tick %d: %s vs %s' % (t + 1, p, q)
    return None


def check(path, update):
    errs = []
    lines, sim = D.run_duel(path)
    again, _ = D.run_duel(path)
    if lines != again: errs.append('not deterministic')
    _, opts = D.read_duel_script(path)
    ex = opts['expect']; dg = D.digest(lines)
    if 'rounds' in ex and D.round_results(lines) != [int(v) for v in ex['rounds'].split(',')]:
        errs.append('rounds %s, expected %s' % (D.round_results(lines), ex['rounds']))
    if 'score' in ex and '%d:%d' % tuple(sim.score) != ex['score']:
        errs.append('score %d:%d, expected %s' % (sim.score[0], sim.score[1], ex['score']))
    unknown = sorted(set(ex) - EXPECT_KEYS)
    if unknown: errs.append('unknown expectation(s): %s' % ', '.join(unknown))
    if 'match' in ex and sim.match != int(ex['match']):
        errs.append('match %d, expected %s' % (sim.match, ex['match']))
    if 'matches' in ex and match_changes(lines) != [int(v) for v in ex['matches'].split(',')]:
        errs.append('matches %s, expected %s' % (match_changes(lines), ex['matches']))
    if 'hurt' in ex and ex['hurt'] == 'none':
        hp = [(k[5], g[5]) for k, g in records(path)]
        if any(h != (D.ROUND_HP, D.ROUND_HP) for h in hp):
            t = next(i for i, h in enumerate(hp) if h != (D.ROUND_HP, D.ROUND_HP))
            errs.append('hurt at tick %d: hit points %d:%d' % (t + 1, hp[t][0], hp[t][1]))
    if 'sheathe' in ex:
        sw = sheathed(path); want = [int(v) for v in ex['sheathe'].split(',')]
        if sw != want: errs.append('sheathed at ticks %s, expected %s' % (sw, want))
    if 'mirror' in ex:
        m = mirrored(path, os.path.join(os.path.dirname(path), ex['mirror']))
        if m: errs.append('not the mirror of %s: %s' % (ex['mirror'], m))
    if update and ex.get('digest') != dg:
        src = open(path).read().split('\n')
        src = [l for l in src if not l.startswith('# expect digest')]
        src.insert(1, '# expect digest ' + dg)
        open(path, 'w').write('\n'.join(src))
        print('  %s: digest set to %s' % (os.path.basename(path), dg))
    elif ex.get('digest') != dg:
        errs.append('digest %s, expected %s' % (dg, ex.get('digest')))
    return errs, sim, lines


def main():
    args = sys.argv[1:]; update = '--update' in args
    scripts = [a for a in args if a.endswith('.txt')] or sorted(glob.glob(os.path.join(ROOT, 'tests', 'duel_scripts', '*.txt')))
    bad = 0
    for sp in scripts:
        errs, sim, lines = check(sp, update)
        print('%-14s %4d ticks  rounds %-16s score %d:%d  match %d  final hash %04x  %s' % (
            os.path.basename(sp), sim.tick, ','.join(map(str, D.round_results(lines))) or '-', sim.score[0],
            sim.score[1], sim.match, sim.state_hash(), 'ok' if not errs else 'FAIL: ' + '; '.join(errs)))
        bad += bool(errs)
    print('%d of %d scripts pass' % (len(scripts) - bad, len(scripts)))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
