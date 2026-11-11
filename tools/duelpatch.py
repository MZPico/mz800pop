#!/usr/bin/env python3
"""The duel patch (src/duel/duel.asm, docs/duel-design.md section 12): its pieces, the holes, the call-graph check.

  duelpatch.py build      build/duel.bin + duel.sym -> build/duel_main.bin (the piece over the game's main loop:
                          2-byte address, then its bytes: POP800.PRS entry PRS_DUEL, main RAM), build/duel_stage.bin
                          (the other pieces in d_ptab's order: entry PRS_DUEL1, a RAM-disk record at DUEL_STAGE_PAGE:
                          DUEL_STAGE_ADDR that d_boot copies into the holes), build/duel_patch.json (both, the hole map
                          and the figures, for tools/mkgamedisk.py and tests/duel_z80.py); then the checks below
  duelpatch.py report     the hole map and the free bytes

The pieces: every P_x .. P_x_end of duel.sym. The holes: every H_x .. H_x_END (src/duel/duel.asm: the game's code the
duel never runs, by the game's own labels; the patch sites H_D14 .. are holes of the instructions they replace). Checked:
  1. every piece lies inside one hole, no two pieces overlap, the staged pieces fit the RAM-disk scratch, d_ptab names
     every piece but P_main exactly once;
  2. the call graph (tools/z80flow.py) over the game with the patch laid in (m4game.bin, the overlays at their
     windows: an overlay stub's `ld a, id / call ovl_w1` names the overlay its jump enters), from the duel's entry
     (d_boot) and the interrupt (isr): no path reaches a hole's byte outside a piece (a dropped routine's code), and no
     reached instruction of the game names an address inside a hole as memory (a dropped routine's variable). Paths
     the arena cannot take are cut by hand (COLD: why, per routine), and so are the self-modified jumps (INDIRECT); every
     cut routine must show no execution in the emulator's code log over the scripted duels (tests/duel_z80.py --cdl)."""
import json, os, re, struct, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from z80flow import walk
B = os.path.join(ROOT, 'build')

# Calls into code the arena never runs: (the caller's routine (a label of m4game.sym), the callee) -> why. The static walk
# does not follow them; tests/duel_z80.py's code log checks that the callee is never executed in a duel. (None needed
# while the duel uses only the holes of src/duel/duel.asm; the dropped trap code would need e.g. ('ld0', 'start_chompers'):
# land, the arena has no fall.)
COLD = {}
# The kernel's self-modified jumps and calls (src/m1/gfx.asm, src/m4/fx.asm; the operand is 0 in the image): the site's
# label -> where its patched operand points: ('table', t) every entry of a dw table of src/m1/kernel_gen.inc, ('chain',
# label) an unrolled chain entered somewhere inside (walked from its start).
INDIRECT = {
    'shr_call': [('table', 'shr_table')], 'fb_call': [('table', 'fill_table')], 'bl_call': [('table', 'blq_table')],
    'lpm_call': [('table', 'cm2_table'), ('table', 'cm3_table')], 'fbp_entry': [('chain', 'pushrows')],
    'lr_ent': [('chain', 'lr_8')], 'lr_dj': [('chain', 'lr_k')], 'lr_lp': [('chain', 'lr_8')],
    'lr_lp2': [('chain', 'lr_8')], 'lmx_ent': [('chain', 'lmx_8')], 'lmx_dj': [('chain', 'lmx_k')],
    'sx_call': [('chain', 'sx_unr')], 'rs_jp': [('chain', 'rs_ini')], 'sw_n': [('chain', 'otr_8')],
    'frm:fs_oj': [('chain', 'frm:fs_och')],    # (an overlay's site: 'overlay:label', the frames overlay's row chain)
}
LN_LAUNCH = 0xb003          # src/boot/launch.inc: the launcher (the duel's end: the level-start overlay's ho_swap)


def kernel_tables():
    """{table: [labels]} of src/m1/kernel_gen.inc's dw tables"""
    out = {}; cur = None
    for line in open(os.path.join(ROOT, 'src', 'm1', 'kernel_gen.inc')):
        m = re.match(r'(\w+_table):', line)
        if m: cur = out.setdefault(m.group(1), []); continue
        m = re.match(r'\s+dw\s+(\w+)', line)
        if m and cur is not None:
            if m.group(1) != '0': cur.append(m.group(1))
            continue
        cur = None
    return out


def syms(path):
    d = {}
    for line in open(path):
        m = re.match(r'(\S+)\s+EQU\s+([0-9A-Fa-f]+)H', line.strip())
        if m: d[m.group(1)] = int(m.group(2), 16)
    return d


def load():
    D = syms(os.path.join(B, 'duel.sym'))
    pieces = sorted((D[k], D[k + '_end'], k) for k in D if k.startswith('P_') and not k.endswith('_end'))
    holes = sorted((D[k], D[k + '_END'], k) for k in D if k.startswith('H_') and not k.endswith('_END'))
    binb = open(os.path.join(B, 'duel.bin'), 'rb').read()
    base = min(p[0] for p in pieces)
    assert base + len(binb) == max(p[1] for p in pieces), 'duel.bin does not span its pieces (%04X + %d)' % (base, len(binb))
    data = {k: binb[a - base:e - base] for a, e, k in pieces}
    return D, pieces, holes, data


def check_pieces(D, pieces, holes, data):
    errs = []
    where = {}
    for a, e, k in pieces:
        hs = [h for h in holes if h[0] <= a and e <= h[1]]
        if len(hs) != 1: errs.append('%s %04X-%04X: not inside one hole' % (k, a, e - 1)); continue
        where[k] = hs[0][2]
    for (a, e, k), (a2, e2, k2) in zip(pieces, pieces[1:]):
        if a2 < e: errs.append('%s and %s overlap' % (k, k2))
    # d_ptab: the staged pieces' order
    main = data['P_main']; t = D['d_ptab'] - D['P_main']; order = []
    while True:
        adr, n = struct.unpack_from('<HH', main, t); t += 4
        if adr == 0: break
        order.append((adr, n))
    staged = [(a, e - a, k) for a, e, k in pieces if k != 'P_main']
    by_addr = {a: (n, k) for a, n, k in staged}
    if sorted(o[0] for o in order) != sorted(by_addr) or any(by_addr[a][0] != n for a, n in order):
        errs.append('d_ptab %s does not list the staged pieces %s' % (order, [(hex(a), n, k) for a, n, k in staged]))
    stage = b''.join(data[by_addr[a][1]] for a, n in order if a in by_addr)
    room = D['DUEL_STAGE_END'] - D['DUEL_STAGE_ADDR']
    if len(stage) > room: errs.append('the staged pieces: %d bytes, the RAM-disk scratch %d' % (len(stage), room))
    return errs, where, order, stage


class Image:
    """the game's main RAM with the patch laid in, the overlays at their windows"""
    def __init__(self, data, pieces):
        self.S = syms(os.path.join(B, 'm4game.sym'))
        img = bytearray(0x10000); b = open(os.path.join(B, 'm4game.bin'), 'rb').read(); img[0x1200:0x1200 + len(b)] = b
        for a, e, k in pieces: img[a:e] = data[k]
        self.main = img
        self.ovl = {}; self.ovl_id = {}; self.ovl_sym = {}
        for f in sorted(os.listdir(B)):
            if not (f.startswith('ovl_') and f.endswith('.bin')): continue
            n = f[4:-4]; s = syms(os.path.join(B, 'ovl_%s.sym' % n)); m = bytearray(0x10000)
            d = open(os.path.join(B, f), 'rb').read(); m[s['ovl_entry']:s['ovl_entry'] + len(d)] = d
            self.ovl[n] = m; self.ovl_id[s['ovl_id']] = n; self.ovl_sym[n] = s
        S = self.S
        self.windows = [(S['OVL_W1'], S['OVL_W1_END']), (S['OVL_W2'], S['OVL_W2_END'])]
        self.low = [(S['OVL_WL'], S['OVL_WL_END'], 'low'), (S['OVL_WL2'], S['OVL_WL2_END'], 'low2')]
        inv = sorted((v, k) for k, v in S.items() if 0x0400 <= v < 0x10000)
        self.inv_a = [v for v, k in inv]; self.inv_k = [k for v, k in inv]
        self.unresolved = []
    def mem(self, sp):
        m = self.main if sp == 'main' else self.ovl[sp]
        return lambda a: m[a & 0xFFFF]
    def resolve(self, sp, ins, t, ctx):
        for lo, hi, n in self.low:
            if lo <= t < hi: return (n, t)
        for lo, hi in self.windows:
            if lo <= t < hi:
                if sp != 'main' and lo <= self.ovl_sym[sp]['ovl_entry'] < hi: return (sp, t)
                if ctx in self.ovl_id and lo <= self.ovl_sym[self.ovl_id[ctx]]['ovl_entry'] < hi:
                    return (self.ovl_id[ctx], t)
                self.unresolved.append((sp, ins.a, t)); return None
        return ('main', t)
    def name(self, sp, a):
        if sp != 'main':
            s = self.ovl_sym.get(sp)
            if s:
                best = max(((v, k) for k, v in s.items() if v <= a and k not in self.S), default=None)
                if best: return '%s:%s+%d' % (sp, best[1], a - best[0])
            return '%s:%04X' % (sp, a)
        import bisect
        i = bisect.bisect_right(self.inv_a, a) - 1
        return '%s+%d' % (self.inv_k[i], a - self.inv_a[i]) if i >= 0 else '%04X' % a
    def routine(self, a):
        import bisect
        i = bisect.bisect_right(self.inv_a, a) - 1
        return self.inv_k[i] if i >= 0 else None


def call_graph(D, pieces, holes, data):
    """-> (errors, notes): the static check (module docstring, 2)"""
    I = Image(data, pieces)
    S = I.S
    in_piece = lambda a: any(p[0] <= a < p[1] for p in pieces)
    dropped = [h for h in holes if not h[2].startswith(('H_D1', 'H_SD', 'H_PP'))]      # (the patch sites are live code)
    in_hole = lambda a: any(h[0] <= a < h[1] for h in dropped)
    cold = {}
    for (caller, callee), why in COLD.items(): cold.setdefault(S[callee], []).append((caller, why))
    cut = []
    tabs = kernel_tables(); ind_at = {}
    for site, specs in INDIRECT.items():
        sp_ = site.split(':')[0] if ':' in site else 'main'
        at = lambda lab: (sp_, I.ovl_sym[sp_][lab.split(':')[1]]) if ':' in lab else ('main', S[lab])
        ind_at[at(site)] = [at(lab) for kind, name in specs for lab in (tabs[name] if kind == 'table' else [name])]
    def resolve(sp, ins, t, ctx):
        if (sp, ins.a) in ind_at: return ind_at[(sp, ins.a)]
        if t == LN_LAUNCH: return None          # (the level-start overlay's ho_swap: the duel's end, the launcher)
        if sp == 'main' and t == S['rr_bkt_ent']: return ('room', t)   # (room.asm rr_table: only while the room overlay draws)
        r = I.resolve(sp, ins, t, ctx)
        if r and r[0] == 'main' and r[1] in cold and sp == 'main' and not in_piece(ins.a):
            if I.routine(ins.a) in [c for c, w in cold[r[1]]]:
                cut.append((ins.a, r[1])); return None
        return r
    seen, edges = walk([('main', D['d_boot']), ('main', S['isr'])], I.mem, resolve)
    errs = []
    for (sp, a), ins in sorted(seen.items(), key=lambda x: (x[0][0] != 'main', x[0])):
        if sp != 'main': continue
        if in_hole(a) and not in_piece(a):
            src = [I.name(*f) for f, t, k in edges if t == ('main', a)]
            errs.append('reaches the dropped code at %s (from %s)' % (I.name(sp, a), ', '.join(src) or 'falling through'))
    for f, (sp, t), k in edges:                 # the game's code into a hole: a dropped routine's entry (a piece there now)
        made = f[0] == 'main' and any(in_piece(x) for x in range(f[1], f[1] + seen[f].n))   # (a patched instruction)
        if sp == 'main' and in_hole(t) and not made:
            errs.append('%s %s %s: into a hole' % (I.name(*f), k, I.name(sp, t)))
    for (sp, a), ins in seen.items():
        if sp == 'main' and in_piece(a): continue
        if sp == 'main' and ins.kind not in ('jp', 'jr', 'ret', 'ind') and in_hole(a + ins.n):
            errs.append('%s falls through into a hole' % I.name(sp, a))
        for nn, how in ins.addrs:
            if in_hole(nn) and not in_piece(nn) and how == 'mem':
                errs.append('%s names %s inside a hole' % (I.name(sp, a), I.name('main', nn)))
    for sp, a, t in I.unresolved:
        errs.append('%s: a jump into an overlay window (%04X) whose overlay the walk cannot tell' % (I.name(sp, a), t))
    ind = sorted(I.name(sp, a) for (sp, a), ins in seen.items() if ins.kind == 'ind' and not (sp == 'main' and in_piece(a)))
    notes = {'reached': len(seen), 'overlays': sorted(set(sp for sp, a in seen) - {'main'}),
             'cut': sorted(set('%s -> %s' % (I.name('main', a), I.name('main', t)) for a, t in cut)), 'indirect': ind}
    for f, (sp, t), k in edges:
        if sp == 'main' and t < 0x1200 and not any(lo <= t < hi for lo, hi, n in I.low):
            errs.append('%s jumps to %04X (a self-modified operand? list it in INDIRECT)' % (I.name(*f), t))
    into = {}
    for f, (sp, t), k in edges:
        if sp != 'main' and f[0] != sp: into.setdefault(sp, set()).add(I.name(*f))
    notes['overlay_entries'] = {k: sorted(v) for k, v in into.items()}
    return errs, notes


def build():
    D, pieces, holes, data = load()
    errs, where, order, stage = check_pieces(D, pieces, holes, data)
    if errs: sys.exit('duelpatch: ' + '\n  '.join(errs))
    cg_errs, notes = call_graph(D, pieces, holes, data)
    if cg_errs: sys.exit('duelpatch: the call graph reaches the holes:\n  ' + '\n  '.join(cg_errs))
    main = data['P_main']
    open(os.path.join(B, 'duel_main.bin'), 'wb').write(struct.pack('<H', D['P_main']) + main)
    open(os.path.join(B, 'duel_stage.bin'), 'wb').write(stage)
    rep = report(D, pieces, holes, where)
    js = {'main': [[D['P_main'], main.hex()]], 'stage': {'page': D['DUEL_STAGE_PAGE'], 'addr': D['DUEL_STAGE_ADDR'],
          'data': stage.hex()}, 'holes': rep['holes'], 'figures': rep['figures'], 'call_graph': notes}
    json.dump(js, open(os.path.join(B, 'duel_patch.json'), 'w'), indent=1)
    print_report(rep)
    print('call graph: %d instructions reached (overlays %s), no hole; cut by hand: %s; indirect jumps: %s' % (
        notes['reached'], ', '.join(notes['overlays']), '; '.join(notes['cut']) or 'none', ', '.join(notes['indirect']) or 'none'))


def report(D, pieces, holes, where=None):
    used = {}
    for a, e, k in pieces:
        h = [x for x in holes if x[0] <= a and e <= x[1]]
        if h: used[h[0][2]] = used.get(h[0][2], 0) + e - a
    rows = [{'hole': k, 'from': a, 'to': e, 'size': e - a, 'used': used.get(k, 0)} for a, e, k in holes]
    code = [r for r in rows if not r['hole'].startswith(('H_D1', 'H_SD', 'H_PP'))]
    fig = {'holes': sum(r['size'] for r in code), 'used': sum(r['used'] for r in code), 'main': len(dict(
        (k, 1) for k in ['P_main'])) and D['P_main_end'] - D['P_main'],
           'staged': sum(e - a for a, e, k in pieces if k != 'P_main'),
           'stage_room': D['DUEL_STAGE_END'] - D['DUEL_STAGE_ADDR']}
    return {'holes': rows, 'figures': fig}


def print_report(rep):
    print('%-8s %-11s %5s %5s %5s' % ('hole', 'range', 'size', 'used', 'free'))
    for r in rep['holes']:
        print('%-8s %04X-%04X %5d %5d %5d' % (r['hole'], r['from'], r['to'] - 1, r['size'], r['used'], r['size'] - r['used']))
    f = rep['figures']
    print('code holes %d bytes, the duel %d, free %d; P_main %d bytes (main RAM), staged %d of %d (RAM-disk scratch)' % (
        f['holes'], f['used'], f['holes'] - f['used'], f['main'], f['staged'], f['stage_room']))


if __name__ == '__main__':
    a = sys.argv[1:]
    if a == ['build']: build()
    elif a == ['report']:
        D, pieces, holes, data = load(); print_report(report(D, pieces, holes))
    else: sys.exit(__doc__)
