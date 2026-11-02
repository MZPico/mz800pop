#!/usr/bin/env python3
"""Where the M4 game waits for the raster beam before copying composed chunks to VRAM (src/m4/flush.asm pend_flush),
measured with mz800emu's non-stopping tracepoints (docs/perf.md "M8a part 3: the beam wait").
usage: beamwait.py script.txt T0 T1 [--root DIR] [-v]
  per tick over ticks T0..T1 (perfcheck's span: tick_done #T0 to #T1): pend_flush's time outside the copies, split into
  setup (entry -> the first beam read), waiting (-> the read the copy starts from), latency (-> the first copy) and the
  one-at-a-time flushes; and the checks over the whole run 0..T1: torn copies (from each copy's measured start and end),
  flushes whose character chunks show in different frames, overlapping chunks copied out of their sorted order.
Raster lines come from the GDG tick counter (1136 ticks a line, 312 lines a frame; line 0 = the VBLN interrupt's phase).
-v: every flush (its chunks, the beam line at entry, the waits, where each copy started)."""
import collections, itertools, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
root = args[args.index('--root') + 1] if '--root' in args else os.path.join(HERE, '..')
V = '-v' in args
script, t0, t1 = args[0], int(args[1]), int(args[2])
sys.path[:0] = [os.path.join(root, 'tests'), os.path.join(root, 'tools')]
import m4_game as G, kidsim
from emu import Emu
LT, FR = 1136, 1136 * 312
sp = script if os.path.exists(script) else os.path.join(root, 'tests', 'm4_scripts', script)
if not os.path.exists(sp): sp = os.path.join(root, 'tests', 'm6_scripts', script)
moves, patches = kidsim.read_script(sp)
with Emu() as e:
    if not e.tracing: sys.exit('beamwait.py needs an emulator with tracepoints (MZPico/mz800emu#1)')
    S = G.setup(e, kidsim.script_level(sp), opts=kidsim.script_opts(sp))
    enc = bytes([((x + 1) & 3) | (((y + 1) & 3) << 2) | (0x10 if sh else 0) for (x, y, sh) in moves]) + b'\xff'
    G.write_pack(e, enc, 5, G.SCRIPT)
    e.call('mem_write', addr=G.SCRIPT_PTR, data_hex='%02x%02x' % (G.SCRIPT & 255, G.SCRIPT >> 8))
    e.call('bp_clear'); e.call('bp_add', addr=S['level_ready']); e.run(400)
    for (rm, p, t, m) in patches:
        e.call('mem_write', addr=G.LEVEL_ADDR + (rm - 1) * 30 + p, data_hex='%02x' % t)
        e.call('mem_write', addr=G.LEVEL_ADDR + 720 + (rm - 1) * 30 + p, data_hex='%02x' % m)
    e.call('bp_clear')
    # the instructions traced (offsets checked against the opcodes below)
    pg_call, pg_ret = S['pg_l'] + 17, S['pg_l'] + 28                # pf_go: `call pf_blit1`, its `ret`
    for a, op in ((S['pend_flush'] + 4, 0xC8), (S['pf_next'] + 4, 0xC8), (S['pf_take'] + 2, 0xCD), (S['pf_beam'] + 3, 0x11),
                  (S['pf_seq'] + 4, 0x11), (pg_call, 0xCD), (pg_ret, 0xC9)):
        assert e.mem(a, 1)[0] == op, 'flush.asm / sprite.asm changed: update the traced offsets (%04X)' % a
    P = {}
    def tp(name, addr, **kw): P[e.trace_add(addr, **kw)] = name
    tp('tick', S['tick_done']); tp('isr', S['isr'])
    tp('pf', S['pend_flush'], mem=[(S['PEND_N'], 1), (S['PEND_LIST'], 18)])
    tp('ret', S['pend_flush'] + 4, regs=['AF']); tp('ret', S['pf_next'] + 4, regs=['AF']); tp('ret_go', pg_ret)
    tp('go', S['pf_go']); tp('next', S['pf_next'])
    tp('read', S['pf_seq'] + 4); tp('read', S['pf_beam'] + 3)       # just after a beam_lines call
    tp('blit1', S['pf_blit1']); tp('blit1_ret', pg_call + 3); tp('blit1_ret', S['pf_take'] + 5)
    tp('kern', S['bl_call'], mem=[(S['CRX'], 4)]); tp('kern_end', S['bl_done'])
    recs = []; n = [0]
    def stop(r):
        if P[r['id']] == 'tick': n[0] += 1
        return n[0] >= t1
    for r in e.collect(10, stop=stop): recs.append((P[r['id']], r['ticks'], r.get('regs', {}), r['mem']))
    e.trace_clear()
phase = collections.Counter(t % FR for nm, t, rg, m in recs if nm == 'isr').most_common(1)[0][0]
A = lambda t: (t - phase) / LT
tick = 0; fl = collections.defaultdict(list); cur = None
for nm, t, regs, mem in recs:
    if nm == 'tick': tick += 1; continue
    if nm == 'pf':
        n_ = mem[0][0]; L = mem[1]
        cur = {'t0': t, 'n': n_, 'ch': [tuple(L[i*6:i*6+4]) + (L[i*6+4] & 1,) for i in range(n_)], 'reads': [], 'kern': [],
               'b': 0, 'mode': None, 'first': None}
        fl[tick].append(cur); continue
    if cur is None: continue
    if nm == 'read': cur['reads'].append(t)
    elif nm == 'go': cur['mode'] = 'together'
    elif nm == 'next' and cur['mode'] is None: cur['mode'] = 'one'
    elif nm == 'blit1':
        cur['b0'] = t
        if cur['first'] is None: cur['first'] = t; cur['nr'] = len(cur['reads'])
    elif nm == 'blit1_ret': cur['b'] += t - cur['b0']
    elif nm == 'kern': cur['kern'].append([t, None, tuple(mem[0])])
    elif nm == 'kern_end': cur['kern'][-1][1] = t
    elif nm in ('ret', 'ret_go'):
        if nm == 'ret' and not regs['AF'] & 0x40: continue      # (a `ret z` not taken)
        cur['t1'] = t; cur = None
def overlap(a, b): return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]
torn = split = swapped = 0
for tk, xs in fl.items():
    for x in xs:
        if 't1' not in x or not x['n']: continue
        frames = set(); ch = sorted(x['ch'], key=lambda c: c[1])        # (pf_sort's order: stable by top row)
        korder = [k[2] for k in x['kern']]
        for k0, k1, cr in x['kern']:
            y, h = cr[1], cr[3]
            if not h: continue
            s0, s1 = A(k0), A(k1); L = 113 + y
            w0 = s0 + (s1 - s0) / h                          # the first row written (rows at an even pace)
            Pn = L + 312 * -(-(w0 - L) // 312)               # the beam's first pass over the top row after that
            if Pn < s1 - (h - 1) - 1e-9: torn += 1           # it would overtake the copy
            if any(c[:4] == cr and c[4] for c in ch): frames.add(Pn // 312)
        if x['mode'] == 'together' and len(frames) > 1: split += 1
        for a, b in itertools.combinations(ch, 2):
            if overlap(a, b) and x['mode'] == 'together' and korder.index(a[:4]) > korder.index(b[:4]): swapped += 1
S_ = collections.Counter()
for tk in range(t0, t1):
    for x in fl[tk]:
        if 't1' not in x or not x['n']: continue
        rest = x['t1'] - x['t0'] - x['b']
        if x['mode'] == 'one': S_['one at a time'] += rest
        else:
            r0, rl = x['reads'][0], x['reads'][x['nr'] - 1]
            S_['setup'] += r0 - x['t0']; S_['waiting'] += rl - r0; S_['latency'] += x['first'] - rl
            S_['after the copies'] += rest - (x['first'] - x['t0'])
        if V:
            print('tick %d: n=%d %s %s, beam line %.0f at entry, %d beam reads, %.1f lines before the first copy; copies at %s' % (
                tk, x['n'], ' '.join('(%d,%d %dx%d%s)' % (c[0], c[1], c[2], c[3], ' char' if c[4] else '') for c in x['ch']),
                x['mode'], A(x['t0']) % 312, len(x['reads']), (x['first'] - x['t0']) / LT,
                ', '.join('%.0f' % (A(k[0]) % 312) for k in x['kern'])))
k = t1 - t0
print('%s ticks %d-%d: pend_flush outside the copies %.3f frames per tick (%s)' % (
    os.path.basename(sp), t0, t1, sum(S_.values()) / k / FR, ', '.join('%s %.3f' % (a, b / k / FR) for a, b in S_.items())))
print('ticks 0-%d: torn copies %d, together-flushes with character chunks in different frames %d, overlapping chunks out of order %d' % (
    t1, torn, split, swapped))
