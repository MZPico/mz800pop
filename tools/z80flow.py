#!/usr/bin/env python3
"""A static control-flow walk over Z80 code (the duel patch's call-graph check, docs/duel-design.md section 12).

decode(mem, a) -> Ins: the instruction at a in mem (a callable byte reader): its length, its kind ('seq' falls
through, 'jp' / 'jr' unconditional, 'jpc' / 'jrc' / 'djnz' conditional, 'call' / 'callc' / 'rst', 'ret' (also retn,
reti), 'retc' conditional, 'ind' an indirect jump: jp (hl) / (ix) / (iy), 'halt'), its branch target and the 16-bit
addresses it names (an immediate ld rp, nn, a memory operand (nn): 'addr' with how: 'imm' / 'mem').

walk(roots, mem_of, ...) follows every path from the roots (calls, both arms of a conditional, fall-through) and
returns the instructions reached; mem_of(space, a) gives a byte of an address space (the main image or an overlay's
window, see tools/duelpatch.py), and a resolver hook maps a jump target into a space (a jump into an overlay window
after its stub's `ld a, id / call ovl_w1`)."""

ALU_HL = {0x86, 0x8E, 0x96, 0x9E, 0xA6, 0xAE, 0xB6, 0xBE}
IDX_HL = {0x34, 0x35, 0x36, 0x46, 0x4E, 0x56, 0x5E, 0x66, 0x6E, 0x7E, 0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x77} | ALU_HL


class Ins:
    __slots__ = ('a', 'n', 'kind', 'target', 'addrs', 'imm8')
    def __init__(self, a, n, kind='seq', target=None, addrs=(), imm8=None):
        self.a, self.n, self.kind, self.target, self.addrs, self.imm8 = a, n, kind, target, list(addrs), imm8
    def __repr__(self): return 'Ins(%04X,%d,%s,%s)' % (self.a, self.n, self.kind, None if self.target is None else '%04X' % self.target)


def w16(mem, a): return mem(a) | (mem(a + 1) << 8)


def decode(mem, a):
    op = mem(a)
    if op == 0xCB: return Ins(a, 2)
    if op == 0xED:
        o2 = mem(a + 1)
        if 0x40 <= o2 < 0x80:
            z = o2 & 7
            if z == 3:
                nn = w16(mem, a + 2)
                return Ins(a, 4, addrs=[(nn, 'mem')])
            if z == 5: return Ins(a, 2, 'ret')            # retn / reti
        return Ins(a, 2)
    if op in (0xDD, 0xFD):
        o2 = mem(a + 1)
        if o2 == 0xCB: return Ins(a, 4)
        if o2 == 0xE9: return Ins(a, 2, 'ind')
        if o2 == 0x21: return Ins(a, 4, addrs=[(w16(mem, a + 2), 'imm')])
        if o2 in (0x22, 0x2A): return Ins(a, 4, addrs=[(w16(mem, a + 2), 'mem')])
        if o2 == 0x36: return Ins(a, 4)
        if o2 in IDX_HL: return Ins(a, 3)
        if o2 in (0xDD, 0xFD, 0xED): return Ins(a, 1)    # (a prefix ignored: the next byte decodes on its own)
        i = decode(mem, a + 1)
        return Ins(a, i.n + 1, i.kind, i.target, i.addrs, i.imm8)
    x, y, z, p, q = op >> 6, (op >> 3) & 7, op & 7, (op >> 4) & 3, (op >> 3) & 1
    if x == 0:
        if z == 0:
            if y == 0 or y == 1: return Ins(a, 1)
            d = mem(a + 1); d = d - 256 if d > 127 else d
            t = (a + 2 + d) & 0xFFFF
            if y == 2: return Ins(a, 2, 'djnz', t)
            if y == 3: return Ins(a, 2, 'jr', t)
            return Ins(a, 2, 'jrc', t)
        if z == 1:
            if q == 0: return Ins(a, 3, addrs=[(w16(mem, a + 1), 'imm')])
            return Ins(a, 1)
        if z == 2:
            if y >= 4: return Ins(a, 3, addrs=[(w16(mem, a + 1), 'mem')])
            return Ins(a, 1)
        if z == 6: return Ins(a, 2, imm8=mem(a + 1)) if y == 7 else Ins(a, 2, imm8=mem(a + 1))
        return Ins(a, 1)
    if x == 1: return Ins(a, 1)                         # (halt: on after the interrupt)
    if x == 2: return Ins(a, 1)
    # x == 3
    if z == 0: return Ins(a, 1, 'retc')
    if z == 1:
        if q == 0: return Ins(a, 1)
        if p == 0: return Ins(a, 1, 'ret')
        if p == 2: return Ins(a, 1, 'ind')
        return Ins(a, 1)
    if z == 2: return Ins(a, 3, 'jpc', w16(mem, a + 1))
    if z == 3:
        if y == 0: return Ins(a, 3, 'jp', w16(mem, a + 1))
        if y in (2, 3): return Ins(a, 2)
        return Ins(a, 1)
    if z == 4: return Ins(a, 3, 'callc', w16(mem, a + 1))
    if z == 5:
        if q == 0: return Ins(a, 1)
        if p == 0: return Ins(a, 3, 'call', w16(mem, a + 1))
        return Ins(a, 1)
    if z == 6: return Ins(a, 2)
    return Ins(a, 1, 'rst', y * 8)


def walk(roots, mem_of, resolve, stop=lambda sp, a: False):
    """roots: [(space, addr)]. mem_of(space) -> byte reader. resolve(space, ins, target, ctx) -> (space, addr) of a jump
    or call target (ctx: the last `ld a, n` value of the straight line before it, for the overlay stubs). stop(space, a):
    do not walk on from there (a duel stub, a routine handled by hand). Returns {(space, addr): Ins} and the edges
    [(from (space, addr), to (space, addr), kind)]."""
    seen = {}; edges = []; todo = list(roots)
    while todo:
        sp, a = todo.pop()
        ctx = None
        while (sp, a) not in seen:
            if stop(sp, a): break
            mem = mem_of(sp)
            i = decode(mem, a)
            seen[(sp, a)] = i
            if mem(a) == 0x3E: ctx = mem(a + 1)
            k = i.kind
            if i.target is not None and k in ('jp', 'jr', 'jpc', 'jrc', 'djnz', 'call', 'callc', 'rst'):
                tgt = resolve(sp, i, i.target, ctx)
                for t in (tgt if isinstance(tgt, list) else [] if tgt is None else [tgt]):
                    edges.append(((sp, a), t, k))
                    todo.append(t)
            if k in ('jp', 'jr', 'ret', 'ind'): break
            a = (a + i.n) & 0xFFFF
    return seen, edges
