#!/usr/bin/env python3
"""Duel phase 1 (docs/duel-design.md section 11): the scripted duels of tests/duel_scripts through tools/duelsim.py, the
duel's oracle (kidsim in duel mode; no emulator, no SDLPoP). Per script: two runs give the same trace (determinism),
and the script's expectations hold: '# expect rounds 1,2,3' (the round results in order: 1 P1, 2 P2, 3 draw),
'# expect score a:b' (at the end), '# expect match m' (the match state at the end), '# expect matches 1,0,3' (the match state's changes: 1 P1 won, 2 P2 won, 3 quit,
0 a rematch), '# expect mirror other.txt' (every tick is the other script's tick with the players swapped and the room
mirrored around the start tiles' middle: x -> 270 - x in the fixed arena), '# expect hurt none' (both keep their full hit points every tick), '# expect sheathe a,b' (the
ticks at which the kid and the shadow first put their drawn swords away), '# expect arenas 12:1,12:16' (a '# seed'
script's random arenas, docs/duel-design.md 15: the rounds' level:room in order), '# expect potions 8:4:1:8:2' (the
potion pairs placed, docs/duel-design.md 19: level:room:column:column:type in order), '# expect spikes 11:14:0:9' (the placed spikes, docs/duel-design.md 21: level:room:column:column in order), '# expect
d18 18:1,58:2' (D18's hits: tick:player in order), '# expect hps 3/3:3/3,3/3:2/3' (the
hit points' states in order, each kept at least a tick: player 1's current/maximum:player 2's), '# expect symmetric
N' (every tick player 2 is player 1 mirrored around their start tiles' middle, x within N pixels: the same frame,
action, alive and hit points, the opposite direction; N 2 when a potion is drunk: SDLPoP get_item moves a drinker
facing right 1-2 pixels further than one facing left; 10 for a spike death: SDLPoP spiked puts the body 8 pixels
from the tile's left; '# expect mirror other.txt N' the same tolerance), '# expect
digest <hex>' (the whole trace's sha256, 16 digits: any change of the duel's
logic or of kidsim's shows here; --update rewrites it after an intended change). Any other expectation key fails.
usage: duel_test.py [--update] [script.txt ...]   (default: tests/duel_scripts/*.txt)"""
import glob, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import duelsim as D

EXPECT_KEYS = {'rounds', 'score', 'match', 'matches', 'mirror', 'digest', 'hurt', 'sheathe', 'arenas', 'potions', 'hps',
               'symmetric', 'spikes', 'd18'}


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
    sim = D.DuelSim(kid_frames=opts['p2_frames'] != 'shadow', seed=opts['seed']); out = []
    for in1, in2 in inputs:
        sim.step(in1, in2); K, G = sim.Kid, sim.Guard
        out.append(((K.frame, K.x, K.direction, K.action, K.alive, sim.hitp_curr, sim.hitp_max),
                    (G.frame, G.x, G.direction, G.action, G.alive, sim.guardhp_curr, sim.guardhp_max)))
    return out


def mirror_x(path):
    """the x the players' start tiles mirror around (their x summed: 270 in the fixed arena)"""
    _, opts = D.read_duel_script(path)
    sim = D.DuelSim(seed=opts['seed'])
    return sim.Kid.x + sim.Guard.x


def symmetric(path, tol=0):
    """every tick player 2 is player 1 mirrored (x within tol): None, or the first tick that is not"""
    X = mirror_x(path)
    for t, (k, g) in enumerate(records(path)):
        if (k[0], k[3], k[4], k[5], k[6]) != (g[0], g[3], g[4], g[5], g[6]) or abs(k[1] - (X - g[1])) > tol or k[2] == g[2]:
            return 'tick %d: %s vs %s' % (t + 1, k, g)
    return None


def sheathed(path):
    """[the kid's, the shadow's first tick after the start with the sword sheathed again (0: never)]"""
    inputs, opts = D.read_duel_script(path)
    sim = D.DuelSim(kid_frames=opts['p2_frames'] != 'shadow', seed=opts['seed']); drawn = [False, False]; out = [0, 0]
    for t, (in1, in2) in enumerate(inputs):
        sim.step(in1, in2)
        for p, c in enumerate((sim.Kid, sim.Guard)):
            if c.sword: drawn[p] = True
            elif drawn[p] and not out[p]: out[p] = t + 1
    return out


def mirrored(a, b, tol=0):
    """script a's ticks are script b's with the players swapped: the same frames, actions, alive, hit points, opposite directions,
    x mirrored"""
    ra, rb = records(a), records(b); X = mirror_x(a)
    if len(ra) != len(rb): return 'lengths %d != %d' % (len(ra), len(rb))
    for t, ((ka, ga), (kb, gb)) in enumerate(zip(ra, rb)):
        for p, q in ((ka, gb), (ga, kb)):
            if (p[0], p[3], p[4], p[5], p[6]) != (q[0], q[3], q[4], q[5], q[6]) or abs(p[1] - (X - q[1])) > tol or p[2] == q[2]:
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
    if 'arenas' in ex:
        got = ','.join('%d:%d' % la for la in sim.arena_log)
        if got != ex['arenas']: errs.append('arenas %s, expected %s' % (got, ex['arenas']))
    if 'potions' in ex:
        got = ','.join('%d:%d:%d:%d:%d' % pl for pl in sim.potion_log)
        if got != ex['potions']: errs.append('potions %s, expected %s' % (got, ex['potions']))
    if 'spikes' in ex:
        got = ','.join('%d:%d:%d:%d' % sl for sl in sim.spike_log)
        if got != ex['spikes']: errs.append('placed spikes %s, expected %s' % (got, ex['spikes']))
    if 'd18' in ex:
        got = ','.join('%d:%d' % (t, p + 1) for t, p in sim.d18_log)
        if got != ex['d18']: errs.append('D18 hits %s, expected %s' % (got, ex['d18']))
    if 'hps' in ex:
        seq = []
        for k, g in records(path):
            h = '%d/%d:%d/%d' % (k[5], k[6], g[5], g[6])
            if not seq or seq[-1] != h: seq.append(h)
        if ','.join(seq) != ex['hps']: errs.append('hit points %s, expected %s' % (','.join(seq), ex['hps']))
    if 'symmetric' in ex:
        m = symmetric(path, int(ex['symmetric']))
        if m: errs.append('not symmetric: %s' % m)
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
        f, *tol = ex['mirror'].split()
        m = mirrored(path, os.path.join(os.path.dirname(path), f), int(tol[0]) if tol else 0)
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
