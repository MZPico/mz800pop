#!/usr/bin/env python3
"""PZ: the floppy loader's compression format (src/boot/unpz.asm is the Z80 decoder), an LZ77 with interlaced
Elias-gamma numbers and a repeat-offset, in the style of Einar Saukas' ZX0 but with its own, simpler bit layout.

Bit stream: bits are read MSB first from "bit bytes" that sit inline in the byte stream; the decoder fetches the next
bit byte at the moment it needs a bit and has none left (its bit buffer A starts as 0x80, a sentinel), so the
encoder reserves a bit byte in its output at that same moment.
Elias(v), v >= 1: v = 1 b(k-1) .. b0 in binary is sent as k pairs (control 0, data bit b) and a final control 1.
Tokens (a block always starts with a literal run, without a selector bit):
  literal run:     Elias(n), n bytes
  after a literal run:  bit 0 = repeat match: Elias(len), copy len bytes from the last offset
                        bit 1 = new match
  after a match:        bit 0 = literal run, bit 1 = new match
  new match:  Elias(hi + 1) with hi = (offset - 1) >> 8, then the byte (-offset) & 255, then Elias(len - 1)
              (len >= 2); Elias(256) in place of hi + 1 ends the block.
Back-references never leave the block (offset <= bytes produced so far), so blocks are independent.
usage: pzpack.py test <file> [block]   (round-trip and ratio check)"""
import sys

def elias_bits(v):
    return 2 * (v.bit_length() - 1) + 1

class BitWriter:
    def __init__(self):
        self.out = bytearray(); self.bpos = -1; self.nbits = 8
    def bit(self, b):
        if self.nbits == 8:
            self.bpos = len(self.out); self.out.append(0); self.nbits = 0
        if b: self.out[self.bpos] |= 0x80 >> self.nbits
        self.nbits += 1
    def byte(self, v): self.out.append(v & 255)
    def elias(self, v):
        assert v >= 1
        k = v.bit_length() - 1
        for i in range(k - 1, -1, -1):
            self.bit(0); self.bit((v >> i) & 1)
        self.bit(1)

def match_len(data, i, j, limit):
    """common prefix length of data[i:] and data[j:] (j < i), at most limit"""
    if data[i] != data[j]: return 0
    lo, hi = 1, 1
    while hi < limit and data[i:i + hi * 2] == data[j:j + hi * 2] and hi * 2 <= limit:
        lo = hi * 2; hi *= 2
    hi = min(hi * 2, limit)
    while lo < hi:                       # data[i:i+lo] equal; find the largest
        mid = (lo + hi + 1) // 2
        if data[i:i + mid] == data[j:j + mid]: lo = mid
        else: hi = mid - 1
    return lo

def find_matches(data, depth=40):
    """for each position: list of (len, offset), lengths increasing, the smallest offset for each length"""
    n = len(data); heads = {}; res = [None] * n
    for i in range(n):
        cands = []
        if i + 2 <= n:
            key = data[i:i + 2]
            chain = heads.get(key)
            if chain:
                best = 1; lim = n - i
                for j in reversed(chain[-depth:]):
                    if data[j + best:j + best + 1] != data[i + best:i + best + 1] and best < lim: continue
                    l = match_len(data, i, j, lim)
                    if l > best:
                        cands.append((l, i - j)); best = l
                        if l == lim: break
            heads.setdefault(key, []).append(i)
        res[i] = cands
    return res

INF = float('inf')
LONG = 96   # matches at least this long are only taken whole (and their shorter lengths not tried)

def compress(data):
    """optimal-ish parse (dynamic programming over two states: after a literal run / after a match)"""
    n = len(data)
    if n == 0: raise ValueError('empty block')
    ms = find_matches(data)
    # L[i]: cost to have produced i bytes, last token a literal run; (cost, run length, back pointer, last offset)
    # M[i]: last token a match: (cost, prev state 'L'/'M', from position, kind 'r'/'n', offset, last offset)
    Lc = [INF] * (n + 1); Lrun = [0] * (n + 1); Loff = [0] * (n + 1)
    Mc = [INF] * (n + 1); Mfrom = [None] * (n + 1); Moff = [0] * (n + 1)
    # the first literal run has no selector bit
    for i in range(0, n):
        # extend / start literal runs ending at i + 1
        if i == 0:
            c, run, off = 0 + 8 + elias_bits(1), 1, 0
            Lc[1], Lrun[1], Loff[1] = c, 1, 0
        else:
            best = INF
            if Lc[i] < INF:
                r = Lrun[i]; c = Lc[i] + 8 + elias_bits(r + 1) - elias_bits(r)
                best = c; brun = r + 1; boff = Loff[i]
            if Mc[i] < INF:
                c = Mc[i] + 1 + 8 + elias_bits(1)
                if c < best: best = c; brun = 1; boff = Moff[i]
            if best < Lc[i + 1]:
                Lc[i + 1], Lrun[i + 1], Loff[i + 1] = best, brun, boff
        if i == 0: continue
        # matches starting at i
        for state, cost, lastoff in (('L', Lc[i], Loff[i]), ('M', Mc[i], Moff[i])):
            if cost == INF: continue
            if state == 'L' and lastoff:
                # repeat match
                rl = match_len(data, i, i - lastoff, n - i) if lastoff <= i else 0
                if rl:
                    lens = (rl,) if rl >= LONG else range(1, rl + 1)
                    for l in lens:
                        c = cost + 1 + elias_bits(l)
                        if c < Mc[i + l]:
                            Mc[i + l] = c; Mfrom[i + l] = ('L', i, lastoff, 'r'); Moff[i + l] = lastoff
            prev = 1
            for (ml, off) in ms[i]:
                base = cost + 1 + elias_bits(((off - 1) >> 8) + 1) + 8
                lens = (ml,) if ml >= LONG else range(max(prev + 1, 2), ml + 1)
                for l in lens:
                    c = base + elias_bits(l - 1)
                    if c < Mc[i + l]:
                        Mc[i + l] = c; Mfrom[i + l] = (state, i, off, 'n'); Moff[i + l] = off
                prev = ml
    # backtrack
    toks = []; pos = n; state = 'L' if Lc[n] <= Mc[n] else 'M'
    while pos > 0:
        if state == 'L':
            r = Lrun[pos]; toks.append(('lit', pos - r, r)); p = pos - r
            state = 'M'; pos = p
            if pos == 0: break
            # a literal run is always preceded by a match (except at the start)
        else:
            st, p, off, kind = Mfrom[pos]
            toks.append((kind, off, pos - p)); pos = p; state = st
    toks.reverse()
    w = BitWriter(); first = True; after = None
    for t in toks:
        if t[0] == 'lit':
            if not first: w.bit(0)
            w.elias(t[2])
            for b in data[t[1]:t[1] + t[2]]: w.byte(b)
            after = 'L'
        elif t[0] == 'r':
            assert after == 'L'
            w.bit(0); w.elias(t[2]); after = 'M'
        else:
            off, l = t[1], t[2]
            w.bit(1); w.elias(((off - 1) >> 8) + 1); w.byte(-off); w.elias(l - 1); after = 'M'
        first = False
    w.bit(1); w.elias(256)
    return bytes(w.out)

def decompress(src):
    """reference decoder (mirrors src/boot/unpz.asm)"""
    out = bytearray(); p = 0; a = [0x80]; pos = [0]
    def bit():
        nonlocal p
        a[0] = (a[0] << 1) & 0x1FF
        if a[0] & 0xFF == 0:
            v = src[p]; p += 1
            c = v >> 7; a[0] = ((v << 1) | 1) & 0xFF
            return c
        c = a[0] >> 8; a[0] &= 0xFF
        return c
    def elias():
        v = 1
        while not bit(): v = v * 2 + bit()
        return v
    neg = None
    n = elias(); out += src[p:p + n]; p += n
    sel_after_lit = True
    while True:
        if not bit():
            if sel_after_lit:           # repeat match
                l = elias()
                for _ in range(l): out.append(out[len(out) - neg])
                sel_after_lit = False; continue
            n = elias(); out += src[p:p + n]; p += n; sel_after_lit = True; continue
        h = elias()
        if h == 256: break
        lo = src[p]; p += 1
        neg = ((h - 1) << 8) + ((~lo) & 255) + 1
        l = elias() + 1
        for _ in range(l): out.append(out[len(out) - neg])
        sel_after_lit = False
    return bytes(out), p

def pack_block(data):
    """(kind, payload): kind 1 = PZ, 0 = stored (when PZ does not save anything)"""
    z = compress(data)
    if len(z) >= len(data): return 0, bytes(data)
    return 1, z

if __name__ == '__main__':
    if sys.argv[1] == 'test':
        import time, zlib
        d = open(sys.argv[2], 'rb').read(); bs = int(sys.argv[3]) if len(sys.argv) > 3 else 8192
        t = time.time(); tot = 0; ztot = 0
        for o in range(0, len(d), bs):
            blk = d[o:o + bs]; z = compress(blk); r, used = decompress(z)
            assert r == blk and used == len(z), ('mismatch at block', o)
            tot += len(z); ztot += len(zlib.compress(blk, 9))
        print('%s: %d -> %d (%.1f%%), zlib per block %d (%.1f%%), %.1f s' % (sys.argv[2], len(d), tot, 100.0 * tot / len(d), ztot, 100.0 * ztot / len(d), time.time() - t))
