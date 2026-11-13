#!/usr/bin/env python3
"""The duel patch (src/duel/duel.asm, docs/duel-design.md section 12): its pieces, the holes, the call-graph check.

  duelpatch.py build      build/duel.bin + duel.sym -> build/duel_main.bin (the piece over the game's main loop:
                          2-byte address, then its bytes: POP800.PRS entry PRS_DUEL, main RAM), build/duel_stage.bin
                          (entry PRS_DUEL1's two RAM-disk records: the pieces d_boot copies into the holes, in d_ptab's
                          order, at DUEL_STAGE_PAGE: DUEL_STAGE_ADDR; then the W2 pieces and the blade pixels, STAGE2, at
                          DUEL_STAGE2_PAGE: DUEL_STAGE2_ADDR, read during the duel), build/duel_patch.json (both, the hole map
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
# The overlay the duel's pieces call into in window W2 (duel.asm d_text's body P_txt: the text overlay, loaded by
# `call ovl_w2` with OVL_TEXT first; its td_render, td_put, td_num called in place, build/duel_text.inc)
PIECE_W2 = 'text'
# The pieces in W2 (docs/duel-design.md 15, 18): not in holes of the game's code but in W2 (their H_W2*), copied there
# from the RAM disk when needed: P_w2 the arenas (WF; d_arena), P_txt the texts (above the text overlay; d_text), P_lob
# the lobby (d_lobby). A jump from a piece into W2 goes to one of them, or to an overlay: P_w2's call of the level-start
# overlay's alter_mods (w_load loads it below P_w2), the others' to the text overlay
W2_PIECES = {'P_w2': 'H_W2A', 'P_txt': 'H_W2T', 'P_lob': 'H_W2L'}
PIECE_ARENA, ARENA_W2 = 'P_w2', 'level'
# The blade pixels (duel.asm P_bld): read from the RAM disk only (d_blade), never laid in main RAM (a dummy hole)
STAGED_ONLY = {'P_bld': 'H_BLD'}
# The second staging record (RAM-disk page DUEL_STAGE2_PAGE: the button pictures' slots, which a duel never uses): the
# pieces read again during the duel, in this order (duel.asm DSTAGE_*). The first record (page 6) holds d_ptab's
# pieces, read once by d_boot: on 512 KB and 1 MB it is the complete chopper pictures' pool (stage C's spikes)
STAGE2 = (('P_w2', 'DSTAGE_W2'), ('P_txt', 'DSTAGE_TXT'), ('P_lob', 'DSTAGE_LOB'), ('P_bld', 'DSTAGE_BLD'))
# Holes kept free of duel code for stage C (docs/duel-design.md 18: the spikes run the game's own code there); still
# checked as dropped code (nothing reaches them while the duel has no traps)
RESERVED = ('H_OBJ', 'H_SPK')
# The lobby (P_lob) is lost when W2 is drawn into or another overlay is loaded over it: it calls only these (d_text
# loads W2 below it), and leaves only by a jump to these
LOBBY_CALLS = {'d_text', 'd_key1', 'd_kget', 'dlj_at', 'd_nleave', 'd_smsg', 'n_do', 'n_cmd', 'n_out', 'n_in', 'n_wait',
               'n_stat', 'read_inputs'}
LOBBY_EXITS = {'dlb_go', 'd_quit'}
LIVE_HOLES = ('H_D1', 'H_SD', 'H_PP', 'H_W2', 'H_BLD')     # (the patch sites, the W2 places, the dummy: not dropped code)
TEXT_W = 160                # the bottom line's bitmap (text.asm TXB: 20 bytes, x 80..239)


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
    for k, h in list(W2_PIECES.items()) + list(STAGED_ONLY.items()):
        if where.get(k) != h: errs.append('%s is not in %s' % (k, h))
    for k, h in where.items():
        if h in RESERVED: errs.append('%s lies in %s, reserved for the spikes (stage C)' % (k, h))
    # d_ptab: the staged pieces' order (the first record)
    main = data['P_main']; t = D['d_ptab'] - D['P_main']; order = []
    while True:
        adr, n = struct.unpack_from('<HH', main, t); t += 4
        if adr == 0: break
        order.append((adr, n))
    later = [k for k, at in STAGE2]
    staged = [(a, e - a, k) for a, e, k in pieces if k != 'P_main' and k not in later]
    by_addr = {a: (n, k) for a, n, k in staged}
    if sorted(o[0] for o in order) != sorted(by_addr) or any(by_addr[a][0] != n for a, n in order):
        errs.append('d_ptab %s does not list the staged pieces %s' % (order, [(hex(a), n, k) for a, n, k in staged]))
    stage = b''.join(data[by_addr[a][1]] for a, n in order if a in by_addr)
    room = D['DUEL_STAGE_END'] - D['DUEL_STAGE_ADDR']
    if len(stage) > room: errs.append('the staged pieces: %d bytes, the RAM-disk scratch %d' % (len(stage), room))
    # the second record: STAGE2's order, at DSTAGE_*, within the button pictures' slots (src/m4/btnstep.asm)
    stage2 = b''
    for k, at in STAGE2:
        if D[at] != D['DUEL_STAGE2_ADDR'] + len(stage2): errs.append('%s %04X, %s is staged at %04X' % (at, D[at], k, D['DUEL_STAGE2_ADDR'] + len(stage2)))
        stage2 += data[k]
    B_ = syms(os.path.join(B, 'ovl_btn.sym'))
    if (D['DUEL_STAGE2_PAGE'], D['DUEL_STAGE2_ADDR'], D['DUEL_STAGE2_END']) != (B_['BC_PAGE'], B_['BC_BASE'], B_['BC_BASE'] + 4 * B_['BC_SLOT']):
        errs.append('DUEL_STAGE2 is not the button pictures\' slots (btnstep.asm BC_PAGE, BC_BASE, 4 x BC_SLOT)')
    room2 = D['DUEL_STAGE2_END'] - D['DUEL_STAGE2_ADDR']
    if len(stage2) > room2: errs.append('the second staging record: %d bytes, its scratch %d' % (len(stage2), room2))
    return errs, where, order, (stage, stage2)


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
    dropped = [h for h in holes if not h[2].startswith(LIVE_HOLES)]      # (the patch sites, the arenas' window: live)
    w2 = {k: (D[k], D[k + '_end']) for k in W2_PIECES}
    in_w2 = lambda a: next((k for k, (lo, hi) in w2.items() if lo <= a < hi), None)
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
        if sp == 'main' and in_piece(ins.a) and S['OVL_W2'] <= t < S['OVL_W2_END']:
            if in_w2(t): return ('main', t)                                     # (into a W2 piece, copied there first)
            ovl = ARENA_W2 if in_w2(ins.a) == PIECE_ARENA else PIECE_W2
            assert t in I.ovl_sym[ovl].values(), 'a duel piece jumps to %04X in W2: not a label of the %s overlay' % (t, ovl)
            return (ovl, t)
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
    names = {v: k for k, v in S.items()}
    names.update({v: k for k, v in D.items() if not k.startswith(('H_', 'P_')) and any(lo <= v < hi for lo, hi, n in pieces)})
    lob = w2['P_lob']
    for f, (sp, t), k in edges:                 # the lobby: only calls that keep W2 above the text overlay, exits to resident code
        if f[0] != 'main' or not lob[0] <= f[1] < lob[1] or (sp == 'main' and lob[0] <= t < lob[1]): continue
        n = names.get(t, '%04X' % t)
        if k in ('call', 'callc', 'rst') and n not in LOBBY_CALLS:
            errs.append('the lobby (P_lob) calls %s: not in LOBBY_CALLS (it may load W2 over the lobby)' % n)
        if k in ('jp', 'jr', 'jpc', 'jrc', 'djnz') and n not in LOBBY_EXITS:
            errs.append('the lobby (P_lob) jumps to %s: not in LOBBY_EXITS' % n)
    txt = w2['P_txt']
    for f, (sp, t), k in edges:                 # the texts: into the text overlay or themselves only
        if f[0] == 'main' and txt[0] <= f[1] < txt[1] and sp == 'main' and in_w2(t) and in_w2(t) != 'P_txt':
            errs.append('the texts (P_txt) jump into %s' % in_w2(t))
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


def font(path, label):
    """{character: (width, rows)} of a generated font include (tools/build_assets.py build_font_text / _duel)"""
    out = {}; on = False; consts = {}
    for line in open(path):
        m = re.match(r'(\w+)\s+equ\s+(\d+)', line)
        if m: consts[m.group(1)] = int(m.group(2))
        if line.startswith(label + ':'): on = True; continue
        m = re.match(r'\s+db\s+(.*)', line)
        if on and m:
            v = [int(x) for x in m.group(1).split(',')]
            if v == [0]: break
            out[chr(v[0])] = (v[1], v[2:])
    return out, consts


def check_texts(D, pieces, data):
    """every string of duel.asm d_strs and every dst_ label: its glyphs in the font the duel draws with (the text overlay's txt_font with
    d_font laid over its lowercase records, d_hud) and its width (SDLPoP draw_text: each glyph + 1, the space 3 + 1;
    the numbers 1-3 as the widest two digits) within the line's TEXT_W pixels. -> (errors, {label: width})"""
    game, gc = font(os.path.join(B, 'assets', 'font_text.inc'), 'txt_font')
    duel, dc = font(os.path.join(B, 'assets', 'font_duel.inc'), 'd_font')
    order = sorted(game)                         # (txt_font's order: build_font_text sorts the characters)
    gone = order[dc['DFONT_OFS'] // 9:dc['DFONT_OFS'] // 9 + dc['DFONT_N']]
    f = {c: v for c, v in game.items() if c not in gone}; f.update(duel)
    num = 2 * max(f[c][0] + 1 for c in '0123456789')
    def mem(a):
        p = [(lo, k) for lo, e, k in pieces if lo <= a < e][0]
        return data[p[1]][a - p[0]]
    errs = []; widths = {}
    t = D['d_strs']; strs = []                   # d_strs (the HUD's), then every dst_ label (the lobby's, the network's)
    while mem(t) | (mem(t + 1) << 8): strs.append(mem(t) | (mem(t + 1) << 8)); t += 2
    strs += sorted(set(v for k, v in D.items() if k.startswith('dst_')) - set(strs))
    for a in strs:
        w = 0; txt = ''
        while mem(a):
            c = mem(a); a += 1
            if c < 4: w += num; txt += '<%d>' % c
            elif chr(c) == ' ': w += gc['TXT_SPACE_W'] + 1; txt += ' '
            elif chr(c) in f: w += f[chr(c)][0] + 1; txt += chr(c)
            else: errs.append('the duel text %r: no glyph for %r' % (txt, chr(c))); txt += chr(c)
        widths[txt] = w - 1
        if w - 1 > TEXT_W: errs.append('the duel text %r: %d pixels, the line has %d' % (txt, w - 1, TEXT_W))
    return errs, widths


def crc16(b, crc=0xFFFF):
    """CRC-16/CCITT-FALSE"""
    for x in b:
        crc ^= x << 8
        for _ in range(8): crc = ((crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1) & 0xFFFF
    return crc


def build_id(D, pieces, data):
    """the network's build id (duel.asm d_build, NETCREATE / NETJOIN: the relay refuses a joiner with another): a CRC-16
    of the game (build/m4game.bin), its overlays (build/m4ovl.bin) and every piece of the patch (d_build 0), laid into
    its piece; -> the id"""
    crc = crc16(open(os.path.join(B, 'm4game.bin'), 'rb').read())
    crc = crc16(open(os.path.join(B, 'm4ovl.bin'), 'rb').read(), crc)
    for a, e, k in pieces: crc = crc16(data[k], crc)
    crc = crc or 1
    a, e, k = [p for p in pieces if p[0] <= D['d_build'] < p[1]][0]
    b = bytearray(data[k]); b[D['d_build'] - a:D['d_build'] - a + 2] = struct.pack('<H', crc); data[k] = bytes(b)
    return crc


def build():
    D, pieces, holes, data = load()
    bid = build_id(D, pieces, data)
    errs, where, order, stage = check_pieces(D, pieces, holes, data)
    terrs, widths = check_texts(D, pieces, data)
    errs += terrs
    if errs: sys.exit('duelpatch: ' + '\n  '.join(errs))
    cg_errs, notes = call_graph(D, pieces, holes, data)
    if cg_errs: sys.exit('duelpatch: the call graph reaches the holes:\n  ' + '\n  '.join(cg_errs))
    main = data['P_main']
    open(os.path.join(B, 'duel_main.bin'), 'wb').write(struct.pack('<H', D['P_main']) + main)
    open(os.path.join(B, 'duel_stage.bin'), 'wb').write(stage[0] + stage[1])
    rep = report(D, pieces, holes, where)
    js = {'build_id': bid, 'build_at': D['d_build'], 'main': [[D['P_main'], main.hex()]], 'stage': {'page': D['DUEL_STAGE_PAGE'], 'addr': D['DUEL_STAGE_ADDR'],
          'data': stage[0].hex()}, 'stage2': {'page': D['DUEL_STAGE2_PAGE'], 'addr': D['DUEL_STAGE2_ADDR'], 'data': stage[1].hex()}, 'holes': rep['holes'], 'figures': rep['figures'], 'call_graph': notes}
    json.dump(js, open(os.path.join(B, 'duel_patch.json'), 'w'), indent=1)
    print_report(rep)
    print("the network's build id %04X" % bid)
    print('texts (pixels of %d): %s' % (TEXT_W, ', '.join('%s %d' % kv for kv in widths.items())))
    print('call graph: %d instructions reached (overlays %s), no hole; cut by hand: %s; indirect jumps: %s' % (
        notes['reached'], ', '.join(notes['overlays']), '; '.join(notes['cut']) or 'none', ', '.join(notes['indirect']) or 'none'))


def report(D, pieces, holes, where=None):
    used = {}
    for a, e, k in pieces:
        h = [x for x in holes if x[0] <= a and e <= x[1]]
        if h: used[h[0][2]] = used.get(h[0][2], 0) + e - a
    rows = [{'hole': k, 'from': a, 'to': e, 'size': e - a, 'used': used.get(k, 0)} for a, e, k in holes]
    code = [r for r in rows if not r['hole'].startswith(LIVE_HOLES) and r['hole'] not in RESERVED]
    fig = {'holes': sum(r['size'] for r in code), 'used': sum(r['used'] for r in code), 'main': len(dict(
        (k, 1) for k in ['P_main'])) and D['P_main_end'] - D['P_main'],
           'staged': sum(e - a for a, e, k in pieces if k != 'P_main' and k not in dict(STAGE2)),
           'staged2': sum(D[k + '_end'] - D[k] for k, at in STAGE2), 'stage2_room': D['DUEL_STAGE2_END'] - D['DUEL_STAGE2_ADDR'],
           'w2': {k: [D[k + '_end'] - D[k], D[h + '_END'] - D[h]] for k, h in W2_PIECES.items()},
           'reserved': sum(r['size'] for r in rows if r['hole'] in RESERVED),
           'stage_room': D['DUEL_STAGE_END'] - D['DUEL_STAGE_ADDR']}
    return {'holes': rows, 'figures': fig}


def print_report(rep):
    print('%-8s %-11s %5s %5s %5s' % ('hole', 'range', 'size', 'used', 'free'))
    for r in rep['holes']:
        print('%-8s %04X-%04X %5d %5d %5d' % (r['hole'], r['from'], r['to'] - 1, r['size'], r['used'], r['size'] - r['used']))
    f = rep['figures']
    print('code holes %d bytes, the duel %d, free %d (and %d reserved for the spikes: %s); P_main %d bytes (main RAM)' % (
        f['holes'], f['used'], f['holes'] - f['used'], f['reserved'], ', '.join(RESERVED), f['main']))
    print('staged: %d of %d (page 6, laid in by d_boot), %d of %d (page 1: %s)' % (f['staged'], f['stage_room'], f['staged2'],
          f['stage2_room'], ', '.join(k for k, at in STAGE2)))
    print('in W2 when needed: %s' % ', '.join('%s %d of %d' % (k, u, r) for k, (u, r) in f['w2'].items()))


if __name__ == '__main__':
    a = sys.argv[1:]
    if a == ['build']: build()
    elif a == ['report']:
        D, pieces, holes, data = load(); print_report(report(D, pieces, holes))
    else: sys.exit(__doc__)
