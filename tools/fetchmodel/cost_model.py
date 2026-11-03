"""cache cost model per script / stretch from build/meas/k/*/calls.jsonl (fetchstat --rows)"""
import json, os, glob, sys
F = 71136
K = os.path.join(os.path.dirname(__file__), '..', '..', 'build', 'meas', 'k')   # tools/fetchmodel/run_all.sh's output
HIT = 800           # a warm hit: char_fetch's key test, the directory lookup (seek + 5 bytes), the seek, the loop
FILL = 800          # a first use, on top of today's fetch: allocation, FIFO invalidation, the seek, the directory write
TPB = 21.1          # INIR / OTIR T per byte (+ the 256-byte chunk loop)
def model(cs, t0=0, t1=None, prior=None):
    """frames a tick in char_fetch over ticks t0..t1: today, the first pass (empty cache at tick 0 or `prior` keys
    seen), all warm"""
    t1 = t1 or max(c['tick'] for c in cs) + 1
    seen = set(prior or ()); last = {}
    today = first = warm = 0; fills = 0; nf = 0
    for c in cs:
        if not c['hit']:
            last[c['slot']] = c
            key = (c['chtab'], c['frame'], c['mirror'], c['sh'])
            n = (c['w'] + 1) * c['h'] * 4
            hitc = HIT + TPB * n
            cold = c['total'] + FILL + TPB * n
            isnew = key not in seen; seen.add(key)
            if t0 <= c['tick'] < t1:
                nf += 1
                today += c['total']; warm += hitc
                first += cold if isnew else hitc; fills += isnew
        elif t0 <= c['tick'] < t1:
            today += c['total']; first += c['total']; warm += c['total']
    nt = t1 - t0
    return today / nt / F, first / nt / F, warm / nt / F, fills / nt, nf / nt
if __name__ == '__main__':
    spans = {'walk_level1': [(30, 60), (190, 260), (0, None)], 'fight1': [(60, 160), (0, None)], 'traps_b1': [(0, 300), (0, None)],
             'gate_push': [(200, 260)]}
    print('%-14s %9s %7s %7s %7s %7s %8s' % ('script', 'ticks', 'today', 'first', 'warm', 'gain', 'fills/t'))
    for nm, sp in spans.items():
        if not os.path.exists(os.path.join(K, nm, 'calls.jsonl')): print('%-14s (no calls.jsonl: its run failed)' % nm); continue
        cs = [json.loads(l) for l in open(os.path.join(K, nm, 'calls.jsonl'))]
        for t0, t1 in sp:
            a, b, c, f, n = model(cs, t0, t1)
            print('%-14s %4d-%-4s %7.3f %7.3f %7.3f %7.3f %8.2f  (fetches/t %.2f)' % (nm, t0, t1 or 'end', a, b, c, a - c, f, n))
    print()
    print('all scripts, the whole run, first pass from an empty cache: frames a tick today / first pass / warm')
    rows = []
    for d in sorted(glob.glob(os.path.join(K, '*'))):
        if not os.path.exists(os.path.join(d, 'calls.jsonl')): continue    # (a failed fetchstat run: no calls.jsonl)
        cs = [json.loads(l) for l in open(os.path.join(d, 'calls.jsonl'))]
        if not cs: continue
        a, b, c, f, n = model(cs)
        rows.append((os.path.basename(d), a, b, c))
    worse = [r for r in rows if r[2] > r[1] + 0.005]
    print('  scripts slower on the first pass than today: %d of %d; the worst: %s' % (len(worse), len(rows),
          ', '.join('%s %.3f -> %.3f' % (r[0], r[1], r[2]) for r in sorted(worse, key=lambda r: r[1] - r[2])[:6])))
    fights = [r for r in rows if r[0].startswith('fight') or 'fight' in r[0] or r[0].startswith('level1') is False and r[1] > 1.2]
    for r in rows:
        if r[0] in ('fight1', 'fight2', 'fight_skill5', 'level2_fight', 'level13_jaffar', 'traps_b1', 'random1', 'walk_level1', 'run_rooms', 'level12_shadow_hit'):
            print('  %-20s %.3f %.3f %.3f' % r)
