"""one long session (all scripts one after the other, as tools/fetchmodel/working_set.py): the frame cache's policies and sizes"""
import json, os, glob, collections, sys
F = 71136
K = os.path.join(os.path.dirname(__file__), '..', '..', 'build', 'meas', 'k')   # tools/fetchmodel/run_all.sh's output
HIT, FILL, MARK, TPB = 800, 800, 150, 21.1
GSET = {1: 'guard', 2: 'guard', 3: 'skel', 4: 'guard', 5: 'guard', 6: 'fat', 7: 'guard', 8: 'guard', 9: 'guard', 10: 'guard_palace',
        11: 'guard_palace', 12: 'shadow', 13: 'vizier', 14: 'vizier', 0: 'guard'}
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import kidsim
ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
def lvl(name):
    for d in ('m4_scripts', 'm5_scripts', 'm6_scripts', 'm7_scripts'):
        p = os.path.join(ROOT, 'tests', d, name + '.txt')
        if os.path.exists(p): return kidsim.script_level(p)
seq = []; ticks = 0
order = sys.argv[1:] or [os.path.basename(d) for d in sorted(glob.glob(os.path.join(K, '*')))
                         if os.path.exists(os.path.join(d, 'calls.jsonl'))]      # (a failed fetchstat run: no calls.jsonl)
for nm in order:
    cs = [json.loads(l) for l in open(os.path.join(K, nm, 'calls.jsonl'))]
    if not cs: continue
    lv = lvl(nm); ticks += max(c['tick'] for c in cs) + 1
    for c in cs:
        if c['hit']: seq.append((None, 0, c['total'])); continue
        s = 'kid' if c['chtab'] == 2 else 'sword' if c['chtab'] == 0 else GSET.get(lv, '?') if c['chtab'] == 5 else c['chtab']
        seq.append(((s, c['frame'], c['mirror'], c['sh']), (c['w'] + 1) * c['h'] * 4, c['total']))
def sim(cap, second=False, evict='fifo'):
    cache = collections.OrderedDict(); used = 0; seen = set(); cost = 0; hits = 0; n = 0
    for key, size, today in seq:
        if key is None: cost += today; continue
        n += 1
        if key in cache:
            cost += HIT + TPB * size; hits += 1; continue
        if second and key not in seen:
            seen.add(key); cost += today + MARK; continue
        cost += today
        if cap is not None and used + size > cap:
            if evict == 'none': continue
            if evict == 'flush': cache.clear(); used = 0; seen.clear()
            else:
                while used + size > cap: _, sz = cache.popitem(last=False); used -= sz
        cache[key] = size; used += size; cost += FILL + TPB * size
    return cost / ticks / F, hits / n
base = sum(t for _, _, t in seq) / ticks / F
print('%d ticks, %d fetches; today %.3f frames a tick in char_fetch' % (ticks, sum(1 for k, _, _ in seq if k), base))
for cap in (None, 960 * 1024, 448 * 1024, 256 * 1024, 128 * 1024):
    for second in (False, True):
        out = []
        for ev in ('fifo', 'flush', 'none'):
            if cap is None and ev != 'fifo': continue
            c, h = sim(cap, second, ev); out.append('%s %.3f (hits %.0f%%)' % (ev, c, 100 * h))
        print('  cache %-9s fill on %-6s use: %s' % ('unlimited' if cap is None else '%d KB' % (cap // 1024), 'second' if second else 'first', ', '.join(out)))
