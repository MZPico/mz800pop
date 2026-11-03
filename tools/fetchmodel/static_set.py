#!/usr/bin/env python3
"""A fixed (prebuilt or pre-generated) frame store holding a chosen set of keys, the normal fetch as the fallback
(no fill, no eviction): fetch frames a tick over the scripts (build/meas/k/*/calls.jsonl), the keys chosen by how often
the OTHER half of the scripts used them (2-fold cross-validation: even / odd scripts), within a byte budget per set
group. A hit costs HIT + 21.1 T a byte (cost_model.py), a key not in the store today's measured fetch.
usage: static_set.py"""
import json, os, glob, collections, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import kidsim
ROOT = os.path.join(HERE, '..', '..')
K = os.path.join(ROOT, 'build', 'meas', 'k')
GSET = {1: 'guard', 2: 'guard', 3: 'skel', 4: 'guard', 5: 'guard', 6: 'fat', 7: 'guard', 8: 'guard', 9: 'guard', 10: 'guard_palace',
        11: 'guard_palace', 12: 'shadow', 13: 'vizier', 14: 'vizier', 0: 'guard'}   # (as session.py: for grouping)
def lvl(name):
    for d in ('m4_scripts', 'm5_scripts', 'm6_scripts', 'm7_scripts'):
        p = os.path.join(ROOT, 'tests', d, name + '.txt')
        if os.path.exists(p): return kidsim.script_level(p)
F = 71136; HIT = 800; TPB = 21.1
scripts = []
for d in sorted(glob.glob(os.path.join(K, '*'))):
    nm = os.path.basename(d); f = os.path.join(d, 'calls.jsonl')
    if not os.path.exists(f): print('(skipped %s: no calls.jsonl, its run failed)' % nm); continue
    cs = [json.loads(l) for l in open(f)]
    if not cs: continue
    lv = lvl(nm); seq = []
    for c in cs:
        if c['hit']: seq.append((None, 0, c['total'], None)); continue
        s = 'kid' if c['chtab'] == 2 else 'sword' if c['chtab'] == 0 else GSET.get(lv, '?') if c['chtab'] == 5 else str(c['chtab'])
        seq.append(((s, c['frame'], c['mirror'], c['sh']), (c['w'] + 1) * c['h'] * 4 + 4, c['total'], s))
    scripts.append((nm, max(c['tick'] for c in cs) + 1, seq))

def choose(train, budget):
    """keys by use in `train`, greedily by uses per byte, per group budget {group: bytes}; group = 'kid' (kid + sword)
    or 'guard' (any one guard set: the budget is per set)"""
    use = collections.Counter(); size = {}
    for _, _, seq in train:
        for k, sz, _, s in seq:
            if k: use[k] += 1; size[k] = sz
    chosen = set(); spent = collections.Counter()
    for k in sorted(use, key=lambda k: -use[k] / size[k]):
        g = 'kid' if k[0] in ('kid', 'sword') else 'g:' + k[0]
        b = budget['kid' if g == 'kid' else 'guard']
        if b is None or spent[g] + size[k] <= b: chosen.add(k); spent[g] += size[k]
    return chosen, spent

def cost(test, chosen):
    t = 0; today = 0; ticks = 0; n = 0; h = 0
    for _, nt, seq in test:
        ticks += nt
        for k, sz, tot, _ in seq:
            today += tot
            if k and k in chosen: t += HIT + TPB * sz; h += 1
            else: t += tot
            n += k is not None
    return today / ticks / F, t / ticks / F, h / max(n, 1), ticks, n

if __name__ == '__main__':
    halves = (scripts[0::2], scripts[1::2])
    for label, budget in (('16 MB: every key', dict(kid=None, guard=None)),
                          ('1 MB: kid+sword 400 KB, the level\'s guard set 80 KB', dict(kid=400 * 1024, guard=80 * 1024)),
                          ('1 MB: kid+sword 448 KB, guard set 32 KB', dict(kid=448 * 1024, guard=32 * 1024)),
                          ('kid+sword 256 KB, guard set 64 KB', dict(kid=256 * 1024, guard=64 * 1024)),
                          ('kid+sword 128 KB, guard set 32 KB', dict(kid=128 * 1024, guard=32 * 1024)),
                          ('kid+sword only, 400 KB (no guard keys)', dict(kid=400 * 1024, guard=0))):
        res = []
        for i in (0, 1):
            ch, sp = choose(halves[1 - i], budget); res.append(cost(halves[i], ch) + (sp,))
        nt = sum(r[3] for r in res); nf = sum(r[4] for r in res)        # both folds pooled: weighted by ticks / fetches
        a = sum(r[0] * r[3] for r in res) / nt; b = sum(r[1] * r[3] for r in res) / nt; h = sum(r[2] * r[4] for r in res) / max(nf, 1)
        sp = res[0][5]
        print('%-55s fetch %.3f -> %.3f frames a tick (store hits %.0f%% of the fetches); kid+sword %d KB, a guard set up to %d KB' % (
            label, a, b, 100 * h, sp['kid'] // 1024, max([v for g, v in sp.items() if g != 'kid'] + [0]) // 1024))
    every = set(k for _, _, seq in scripts for k, _, _, _ in seq if k)
    a, b, h, _, _ = cost(scripts, every)
    print('%-55s fetch %.3f -> %.3f frames a tick (hits 100%%: the whole key space stored, so all %d keys used here hit)' % (
        '16 MB: every key', a, b, len(every)))
    for nm in ('walk_level1', 'fight1', 'traps_b1'):
        test = [s for s in scripts if s[0] == nm]; rest = [s for s in scripts if s[0] != nm]
        ch, _ = choose(rest, dict(kid=400 * 1024, guard=80 * 1024))
        a, b, h, _, _ = cost(test, ch)
        print('  %-12s (keys chosen from the other 70 scripts, 1 MB budget): %.3f -> %.3f (hits %.0f%%)' % (nm, a, b, 100 * h))
