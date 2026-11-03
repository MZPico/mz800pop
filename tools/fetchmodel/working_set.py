"""working set of the frame cache over all scripts (build/meas/k/*/calls.jsonl, fetchstat --rows)"""
import json, os, glob, collections, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import kidsim
F = 71136
K = os.path.join(os.path.dirname(__file__), '..', '..', 'build', 'meas', 'k')   # tools/fetchmodel/run_all.sh's output
ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
def lvl(name):
    for d in ('m4_scripts', 'm5_scripts', 'm6_scripts', 'm7_scripts'):
        p = os.path.join(ROOT, 'tests', d, name + '.txt')
        if os.path.exists(p): return kidsim.script_level(p), d
CH = {0: 'sword', 2: 'kid', 5: 'guard'}
GSET = {1: 'guard', 2: 'guard', 3: 'skel', 4: 'guard', 5: 'guard', 6: 'fat', 7: 'guard', 8: 'guard', 9: 'guard', 10: 'guard_palace',
        11: 'guard_palace', 12: 'shadow', 13: 'vizier', 14: 'vizier', 0: 'guard'}  # (approximate; only for grouping)
rows = []; per = []
for d in sorted(glob.glob(os.path.join(K, '*'))):
    nm = os.path.basename(d); f = os.path.join(d, 'calls.jsonl')
    if not os.path.exists(f): continue
    cs = [json.loads(l) for l in open(f)]
    lv, kind = lvl(nm)
    ticks = max([c['tick'] for c in cs] + [0]) + 1
    last = {}
    m = []
    for c in cs:
        if not c['hit']: last[c['slot']] = c
        else:
            p = last.get(c['slot'])
            if p: c = dict(c, frame=p['frame'], mirror=p['mirror'], sh=p['sh'], w=p['w'], h=p['h'])
        c['set'] = ('kid' if c['chtab'] == 2 else 'sword' if c['chtab'] == 0 else 'g:' + GSET.get(lv, '?') if c['chtab'] == 5 else 'ch%d' % c['chtab'])
        c['key'] = (c['set'], c.get('frame'), c.get('mirror'), c.get('sh'))
        c['size'] = ((c['w'] or 0) + 1) * (c['h'] or 0) * 4
        c['nm'] = nm; c['lv'] = lv
        if not c['hit']: m.append(c)
    seen = set(); first = 0
    for c in m:
        if c['key'] not in seen: seen.add(c['key']); first += 1
    nb = sum(c['size'] for c in {c['key']: c for c in m}.values())
    per.append((nm, kind, ticks, len(m), first, nb, sum(c['total'] for c in cs) / ticks / F))
    rows += m
print('%-24s %5s %7s %7s %7s %8s %7s' % ('script', 'ticks', 'fetches', 'keys', 'reuse%', 'KB', 'fetch f/t'))
for nm, kind, t, n, k, nb, ft in per:
    print('%-24s %5d %7d %7d %6.0f%% %8.1f %7.3f' % (nm, t, n, k, 100 * (n - k) / max(n, 1), nb / 1024, ft))
tot = len(rows); keys = collections.Counter(c['key'] for c in rows); size = {c['key']: c['size'] for c in rows}
print('all scripts: %d fetches, %d distinct keys, %.0f KB of cell buffers' % (tot, len(keys), sum(size.values()) / 1024))
for s in sorted(set(k[0] for k in keys)):
    ks = [k for k in keys if k[0] == s]
    print('  %-16s %5d keys %8.1f KB, %6d fetches' % (s, len(ks), sum(size[k] for k in ks) / 1024, sum(keys[k] for k in ks)))
# frequency: the most used keys and the share of the fetches (and of the shift work ~ size) they cover
order = sorted(keys, key=lambda k: -keys[k])
acc = 0; accb = 0; cov = []
for i, k in enumerate(order):
    acc += keys[k]; accb += size[k]
    for kb in (128, 256, 512, 768, 1024, 1536):
        if accb > kb * 1024 and not any(c[0] == kb for c in cov): cov.append((kb, i, acc_prev / tot))
    acc_prev = acc
print('the most used keys first: KB -> share of all fetches covered:', ', '.join('%d KB: %.0f%%' % (kb, 100 * s) for kb, i, s in cov))
# one long session: all scripts one after the other (the order of the list), the cache never evicting / LRU of N KB
def sim(cap_kb, lru=True, groups=None):
    import collections as C
    cache = C.OrderedDict(); used = 0; hits = 0; n = 0
    for c in rows:
        k = c['key']; n += 1
        if k in cache:
            hits += 1
            if lru: cache.move_to_end(k)
            continue
        if cap_kb is None or used + c['size'] <= cap_kb * 1024:
            cache[k] = c['size']; used += c['size']
        elif lru:
            while cache and used + c['size'] > cap_kb * 1024:
                _, sz = cache.popitem(last=False); used -= sz
            cache[k] = c['size']; used += c['size']
    return hits / n
for cap in (None, 1536, 1024, 512, 448, 256):
    print('one session over all scripts, cache %s: hit rate %.0f%% LRU, %.0f%% fill until full' % ('unlimited' if cap is None else '%d KB' % cap, 100 * sim(cap), 100 * sim(cap, lru=False)))
json.dump([dict(nm=c['nm'], key=list(c['key']), size=c['size'], tick=c['tick'], total=c['total'], read=c['read'], shift=c['shift'], setup=c.get('setup', 0)) for c in rows], open(os.path.join(K, '..', 'allmiss.json'), 'w'))
