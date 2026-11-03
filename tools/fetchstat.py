#!/usr/bin/env python3
"""The sprite fetch (sprite.asm char_fetch -> gfx.asm spr_fetch) measured with tracepoints, for the RAM-disk tier
design (docs/ramdisk-tiers.md). No code change: tracepoints only (tools/emu.py trace_add / collect).

Per char_fetch call it records the slot (the descriptor IY), the key (chtab, frame, mirror, shift), the level's guard
set (gset: dir_tab's CH_GUARD directory, game.asm guard_type_tbl order; for chtab 5), whether the
one-entry cache of the slot (SD_LKEY / SD_LKEY2) hit, the image's width and height (V_W, V_H) and the CPU cycles of:
  setup  char_fetch's entry to the first row (key compare, dir_entry = an 8-byte RAM-disk read, spr_fetch's patching,
         the seek);
  read   the rows' INIR from the RAM disk (sfrow -> sf_de);
  shift  the shift routine (sf_de -> sf_stride: shift and, for a mirrored frame, the bit reverse);
  loop   the rest (row and plane loop, until the return to pp_put).
usage: fetchstat.py [--rows] [--out FILE.json] SCRIPT[:T0-T1] ...
  SCRIPT is a name in tests/m4_scripts, m5_scripts, m6_scripts or m7_scripts; T0-T1 limits the ticks summed (all
  ticks are run up to T1). --rows adds the row tracepoints (read / shift split; slower); without it only the calls and
  the keys are recorded (the working set). --out writes every call as JSON lines for later analysis."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path[:0] = [os.path.join(ROOT, 'tests'), HERE]
import m4_game as G, kidsim
from emu import Emu
FRAME = 312 * 228
SLOTS = {0x0B00: 'kid', 0x1180: 'kid sword', 0x0798: 'guard', 0x0780: 'guard sword', 0x07B0: 'splash',
         0x0350: 'splash 2', 0x0368: 'mirror image'}

def script_path(name):
    for d in ('m4_scripts', 'm5_scripts', 'm6_scripts', 'm7_scripts'):
        p = os.path.join(ROOT, 'tests', d, name if name.endswith('.txt') else name + '.txt')
        if os.path.exists(p): return p
    raise SystemExit('no script ' + name)

def run(sp, t1=None, rows=False):
    """the calls of one script run: a list of dicts (tick, slot, key, hit, w, h, setup, read, shift, loop, total)"""
    moves, patches = kidsim.read_script(sp); keys = kidsim.read_keys(sp)
    o = kidsim.script_opts(sp)
    with Emu() as e:
        S = G.setup(e, kidsim.script_level(sp), opts=o)
        G.write_pack(e, G.encode(moves, keys), 5, G.SCRIPT)
        e.call('mem_write', addr=G.SCRIPT_PTR, data_hex='%02x%02x' % (G.SCRIPT & 255, G.SCRIPT >> 8))
        e.call('bp_clear'); e.call('bp_add', addr=S['guards_off_chk'])
        r = e.run(400); assert r['stopped_by'] == 'breakpoint', r
        for (rm, p, t, m) in patches:
            e.call('mem_write', addr=G.LEVEL_ADDR + (rm - 1) * 30 + p, data_hex='%02x' % t)
            e.call('mem_write', addr=G.LEVEL_ADDR + 720 + (rm - 1) * 30 + p, data_hex='%02x' % m)
        e.call('bp_clear')
        by_addr = {S['tick_done']: 'tick', S['char_fetch']: 'entry', S['cfdo']: 'miss', S['cf_ch']: 'frame',
                   S['pu2a'] + 5: 'ret'}                # (pu2a + 5: after pp_put's `push iy : call char_fetch`)
        e.trace_add(S['tick_done'])
        e.trace_add(S['char_fetch'], regs=['IY'], mem=[(S['cf_ch'] + 1, 1), (S['dir_tab'] + 3 * 5 + 1, 2)])
        e.trace_add(S['cfdo'], regs=['BC'])
        e.trace_add(S['cf_ch'], regs=['BC'])
        e.trace_add(S['pu2a'] + 5)
        if rows:
            by_addr.update({S['sfrow']: 'row', S['sf_de']: 'read', S['sf_stride']: 'shift'})
            e.trace_add(S['sfrow'], mem=[(0x0814, 5)])  # V_W, V_H, V_OW, V_SHPAGE, V_MIRROR
            e.trace_add(S['sf_de'])
            e.trace_add(S['sf_stride'])
        tick = 0; calls = []; c = None; last = len(moves) if t1 is None else min(t1, len(moves))
        for rec in e.collect(200, stop=lambda r: tick >= last):
            k = by_addr[rec['addr']]
            cy = rec['cycles']
            if k == 'tick':
                tick += 1; continue
            if k == 'entry':
                iy = rec['regs']['IY']
                gd = rec['mem'][1]
                c = dict(tick=tick, slot=SLOTS.get(iy, hex(iy)), chtab=rec['mem'][0][0], hit=True, t0=cy, t_row0=None,
                         read=0, shift=0, w=None, h=None, rows=0,
                         gset=((gd[0] | gd[1] << 8) - S['RD_DIR_GUARD']) // 0x120)   # (the level's guard set: dir_tab's CH_GUARD)
            elif c is None: continue
            elif k == 'miss':
                c['hit'] = False; k2 = rec['regs']['BC'] & 0xFF
                c['mirror'] = (k2 >> 3) & 1; c['sh'] = k2 & 7
            elif k == 'frame':
                c['frame'] = rec['regs']['BC'] & 0xFF
            elif k == 'row':
                if c['t_row0'] is None:
                    m = rec['mem'][0]; c['t_row0'] = cy; c['w'], c['h'] = m[0], m[1]
                c['tr'] = cy; c['rows'] += 1
            elif 'tr' not in c and k in ('read', 'shift'):
                c['odd'] = c.get('odd', 0) + 1                  # (a row tracepoint out of order: counted, not timed)
            elif k == 'read':
                c['read'] += (cy - c['tr']) & 0xFFFFFFFF; c['tr'] = cy
            elif k == 'shift':
                c['shift_t'] = c.get('shift_t', 0) + ((cy - c['tr']) & 0xFFFFFFFF)
            elif k == 'ret':
                c['total'] = (cy - c['t0']) & 0xFFFFFFFF
                if c['t_row0'] is not None: c['setup'] = (c['t_row0'] - c['t0']) & 0xFFFFFFFF
                c['shift'] = c.pop('shift_t', 0)
                for x in ('t0', 't_row0', 'tr'): c.pop(x, None)
                calls.append(c); c = None
        e.trace_clear()
    return calls

def main():
    args = sys.argv[1:]
    rows = '--rows' in args
    out = args[args.index('--out') + 1] if '--out' in args else None
    names = [a for i, a in enumerate(args) if not a.startswith('--') and (i == 0 or args[i - 1] != '--out')]
    allc = []
    for nm in names:
        span = None
        if ':' in nm: nm, s = nm.split(':'); span = tuple(int(v) for v in s.split('-'))
        sp = script_path(nm)
        calls = run(sp, span[1] if span else None, rows)
        for c in calls: c['script'] = os.path.basename(sp)[:-4]
        allc += calls
        sel = [c for c in calls if span is None or span[0] <= c['tick'] < span[1]]
        end = min(span[1], len(kidsim.read_script(sp)[0])) if span else max([c['tick'] for c in calls] + [0]) + 1
        nt = max(end - span[0], 1) if span else end        # (a span past the script's end: only the ticks run)
        miss = [c for c in sel if not c['hit']]
        tot = sum(c['total'] for c in sel)
        print('%s%s: %d ticks, %d calls, %d fetches (misses of the one-entry cache), %.3f frames a tick in char_fetch' %
              (nm, ' %d-%d' % span if span else '', nt, len(sel), len(miss), tot / nt / FRAME))
        if rows and miss:
            for part in ('setup', 'read', 'shift'):
                v = sum(c.get(part, 0) for c in miss)
                print('   %-6s %.3f frames a tick' % (part, v / nt / FRAME))
            loop = sum(c['total'] - c.get('setup', 0) - c['read'] - c['shift'] for c in miss)
            print('   %-6s %.3f frames a tick; hits %.4f' % ('loop', loop / nt / FRAME, sum(c['total'] for c in sel if c['hit']) / nt / FRAME))
        keys = set((c['chtab'], c.get('frame'), c.get('mirror'), c.get('sh')) for c in miss)
        print('   distinct (chtab, frame, mirror, shift) keys fetched: %d' % len(keys))
    if out:
        with open(out, 'w') as f:
            for c in allc: f.write(json.dumps(c) + '\n')

if __name__ == '__main__':
    main()
