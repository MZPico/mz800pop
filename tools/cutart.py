#!/usr/bin/env python3
"""M7 steps 7-8: the cutscenes' art and tables for PRES (src/pres/pres.asm, the cutscene engine), from the same
sources as tools/cutsim.py's reference render (PV.DAT, PRINCE.DAT's flames, the kid pack's mouse; EGA colours,
DOSBox-checked, docs/m7-design.md §16).

  write_inc()        build/assets/cut.inc: frame_tbl_cuts (SDLPoP seg006.c), the sequence offsets the scene scripts use
                     (CSEQ_<id>), the sound tables (priority, interruptible, the ticks model's length at 60 a second)
  prs_entries(P)     POP800.PRS's cutscene entries (tools/mkgamedisk.py; P = build/pres.sym): the room entry (the
                     engine's code, the background as PZ bands with its art_idx slot, the common sprites and their table
                     cut_com) and one entry per scene (its character sprites and the table cut_spr), as main-RAM
                     records [(address, raw bytes, stored)] (stored: the PZ bands, unpacked by PRES itself)

Sprites (the engine draws byte-aligned only): every image a scene draws, at every pixel shift (x & 7) it is drawn at
(cutsim over the scenes and every hourglass state), pre-shifted and pre-flipped. Format: wb, h, then h rows of 5 x wb
bytes, column by column: the inverted mask (1 = keep the background), planes 0-3 (MZ colour bits, only where the mask
is 0); bit 0 = the leftmost pixel. cut_spr entries (6 bytes, 0xFF ends): chtab | 0x80 (flipped), image, the image's pixel width w, the
shift, the address, wb, h (8 bytes: pv_scene's addresses are PZ blocks of the whole sprite, unpacked when drawn). cut_com (fixed places, cutsim draw_list): the flames of torch 0 (x 93) and torch 1 (x 211), frames
0-8; the hourglass, states 1-7 (index 0 unused); the sand 0-2; the pillar.
The background: res 951 with the bed res 981 ORed (EGA colour numbers) and the six stars in their first colours
(cutsim.Render.background), 4 planes in 4 bands of 50 rows (PRES's draw_img 'copy')."""
import os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cutsim, kidsim
OUT = os.path.join(HERE, '..', 'build', 'assets')

# the scenes and their PRS entries (pres.asm PRS_C*): (name, [(level, rem_min) cases whose frames it must cover])
# (the characters do not depend on the hourglass state; level 12's scene is cutscene_2_6 from 6 minutes up)
SCENES = (('PRS_C26', [(2, 60), (6, 60)]), ('PRS_C4', [(4, 60)]), ('PRS_C8', [(8, 60)]), ('PRS_C9', [(9, 60)]),
          ('PRS_C12', [(12, 60), (12, 3)]), ('PRS_CEXP', [('time_expired', 60)]), ('PRS_CEND', [('end_sequence_anim', 60)]))
PV_BUF2 = 8000              # pv_scene's second part (PRS_CPV2): loaded at DBUF, copied to 0x8000 by the engine
TORCH_X = (cutsim.TORCH_XH[0] * 8 + cutsim.TORCH_XL[0], cutsim.TORCH_XH[1] * 8 + cutsim.TORCH_XL[1])
TORCH_YB = 116
GLASS_X, GLASS_YB, SAND_X, SAND_YB, PILLAR_X, PILLAR_YB = 152, 168, 160, 164, 240, 167
SEQ_IDS = sorted(set(cutsim.SEQ.values()))

def encode(w, h, rows, shift):
    """the engine's sprite: (wb, h, data) of rows (MZ colours, -1 = background) drawn at a pixel shift"""
    wb = (w + shift + 7) // 8
    out = bytearray([wb, h])
    for y in range(h):
        blk = [bytearray(wb) for _ in range(5)]
        for x in range(w):
            c = rows[y][x]
            if c < 0: continue
            px = x + shift; b = 1 << (px & 7); o = px >> 3
            blk[0][o] |= b
            for p in range(4):
                if c >> p & 1: blk[p + 1][o] |= b
        blk[0] = bytearray(v ^ 0xFF for v in blk[0])
        for j in range(wb): out += bytes(k[j] for k in blk)
    return bytes(out)

def opaque(w, h, rows):
    """blitters_0_no_transp: index 0 drawn black (EGA attribute 0)"""
    return [[cutsim.BLACK0 if c < 0 else c for c in r] for r in rows]

def scene_sprites(cases):
    """{(chtab | flip << 7, image, shift): (w, encoded)} the characters of the scene's frames"""
    out = {}
    for lv, rm in cases:
            cs = cutsim.named_scene(lv, rm) if isinstance(lv, str) else cutsim.level_scene(lv, rm)
            for f in cs.frames:
                for (tab, ch, idx, x, yb, blit, flip, peel, slot) in f['objs']:
                    if ch not in (2, 3, 4): continue
                    w, h, rows = cutsim.sprite(ch, idx, cs.which_imgs, 0, 0, flip)
                    xx = x - w if flip else x
                    if xx >= 320 or xx + w <= 0: continue           # (off the screen: the engine skips it too)
                    assert xx >= 0 and yb - h + 1 >= 0 and yb < 192, ('the engine clips at the right edge only', lv, f['n'])
                    key = (ch | (0x80 if flip else 0), idx, xx & 7)
                    assert not any(c == cutsim.BLACK0 for r in rows for c in r), 'a character uses the flash\'s pixel value'
                    if key not in out: out[key] = (w, encode(w, h, rows, xx & 7))
    return out

def common_sprites():
    """[(name, encoded)] in cut_com's order"""
    out = []
    for t in (0, 1):
        for f in range(9):
            w, h, rows = cutsim.sprite(1, f, 1, TORCH_X[t], TORCH_YB)
            out.append(('torch%d_%d' % (t, f), encode(w, h, opaque(w, h, rows), TORCH_X[t] & 7)))
    out.append(('glass_0', b''))
    for st in range(1, 8):
        w, h, rows = cutsim.sprite(8, st + 1, 1, GLASS_X, GLASS_YB - 27)
        assert h == 28
        out.append(('glass_%d' % st, encode(w, h, rows, GLASS_X & 7)))
    for s in range(3):
        w, h, rows = cutsim.sprite(8, s + 9, 1, SAND_X, SAND_YB - 7)
        assert h == 8
        out.append(('sand_%d' % s, encode(w, h, rows, SAND_X & 7)))
    w, h, rows = cutsim.sprite(8, 1, 1, PILLAR_X, PILLAR_YB - 47)
    assert h == 48
    bg = cutsim.Render(cutsim.named_scene('pv_scene')).background()  # (cut.asm: the pillar counts as drawn from the start)
    assert all(rows[y][x] < 0 or rows[y][x] == bg[PILLAR_YB - 47 + y][PILLAR_X + x] for y in range(h) for x in range(w))
    out.append(('pillar', encode(w, h, rows, PILLAR_X & 7)))
    return out

def background():
    """the room's screen as 4 planes (plane-major, 8000 bytes each), its 200 rows (cut.asm p1_black: 192 in the game)"""
    scr = cutsim.Render(cutsim.named_scene('pv_scene')).background()
    P = [bytearray(8000) for _ in range(4)]
    for y in range(200):
        for x in range(320):
            c = scr[y][x]
            for p in range(4):
                if c >> p & 1: P[p][y * 40 + (x >> 3)] |= 1 << (x & 7)
    return P

def write_inc():
    import build_assets as BA
    ft = BA.frame_tables()['cuts']
    seq_off = [int(l.split()[1]) for l in open(os.path.join(OUT, 'seqtbl_offsets.txt'))]
    L = ['; generated by tools/cutart.py - do not edit (M7 step 7: the cutscene engine in src/pres/pres.asm)',
         '; frame_tbl_cuts (SDLPoP seg006.c): image, sword (0xC0: chtab - 2), dx, dy, flags (0x80 odd)',
         'CUT_FRAMES      equ     %d' % len(ft), 'frame_tbl_cuts:']
    for f in ft: L.append('                db      %s' % ', '.join(str(v & 255) for v in f))
    L.append('; the sequence table offsets of the scripts\' sequences (seqtbl_offset_char; logic.bin page 6 0xD000)')
    for i in SEQ_IDS: L.append('CSEQ_%-10d equ     %d' % (i, seq_off[i]))
    L.append('; the sounds (SDLPoP seg000.c sound_prio_table, data.h sound_interruptible; kidsim: the ids without a resource')
    L.append('; have priority 0xFF here: play_sound ignores them) and the ticks model\'s lengths at 60 a second (words)')
    n = len(kidsim.SOUND_PRIO)
    L.append('CUT_NSND        equ     %d' % n)
    L.append('cut_prio:       db      %s' % ', '.join(str(0xFF if i in kidsim.SOUND_MISSING else kidsim.SOUND_PRIO[i]) for i in range(n)))
    L.append('cut_intr:       db      %s' % ', '.join(str(kidsim.SOUND_INTERRUPTIBLE[i]) for i in range(n)))
    L.append('cut_len60:      dw      %s' % ', '.join(str(cutsim.sound_ticks60(i)) for i in range(n)))
    L.append('CUT_L55         equ     %d' % cutsim.sound_ticks60(55))
    L.append('CUT_L56         equ     %d' % cutsim.sound_ticks60(56))
    st0 = cutsim.level_scene(2, 60).stars0
    L.append('; the stars\' colour indices after load_intro (cutsim stars0; the background has them)')
    L.append('cut_star0:      db      %s' % ', '.join(str(v) for v in st0))
    open(os.path.join(OUT, 'cut.inc'), 'w').write('\n'.join(L) + '\n')

def first_fit(items, free):
    """items [(key, bytes)] placed largest first into free [[lo, hi]] -> {key: address}"""
    addr = {}
    for key, data in sorted(items, key=lambda t: -len(t[1])):
        place = next((f for f in free if f[1] - f[0] >= len(data)), None)
        assert place is not None, ('no room for', key, len(data), [(hex(a), hex(b)) for a, b in free])
        addr[key] = place[0]; place[0] += len(data)
    return addr

def prs_entries(P, pres_bin, pack):
    """[(name, records)]: records [(address, bytes, stored)] (stored = written as it is; else PZ by the launcher);
    pack(raw) -> PZ payload (mkgamedisk.pack_cached)"""
    E = P['end_of_pres']; C1 = P['end_of_cut']
    code = pres_bin[E - 0x2000:C1 - 0x2000]
    # the room entry: the engine, the background bands, the common sprites, cut_com, art_idx slot 0
    planes = background()
    bands = []
    rows = 50
    for b in range(4):
        raw = b''.join(planes[p][b * rows * 40:(b + 1) * rows * 40] for p in range(4))
        kind, pz = pack(raw); assert kind
        bands.append((b, pz))
    free = [[C1, 0x8000]]
    baddr = first_fit([(b, pz) for b, pz in bands], free)
    idx = bytearray(P['ART_ENT'])
    idx[:8] = bytes([0, 0, 40, 200, 0, 255, 255, 4])
    for b, pz in bands: idx[8 + 3 * b:11 + 3 * b] = bytes([rows]) + struct.pack('<H', baddr[b])
    com = common_sprites()
    cfree = [[0x1200, 0x2000], [P['ART2_START'], P['CUT_SPR']]]        # (above the game's block 2 too: tests/m5_boot.py, 2026-11-01)
    caddr = first_fit([(n, d) for n, d in com if d], cfree)
    ctab = b''.join(struct.pack('<H', caddr[n] + 2 if d else 0) for n, d in com)
    assert len(ctab) == P['CUT_COM_N'] * 2
    hdr = {n: d[:2] for n, d in com if d}
    room = [(E, code, False)] + [(baddr[b], pz, True) for b, pz in bands] + \
           [(P['art_idx'] + P['SLOT_ROOM'] * P['ART_ENT'], bytes(idx), True), (P['cut_com'], ctab, False)] + \
           [(caddr[n], d, False) for n, d in com if d]
    out = [('PRS_CROOM', room)]
    stats = {'room bands PZ': sum(len(pz) for _, pz in bands), 'common sprites': sum(len(d) for _, d in com),
             'free after the common sprites': sum(f[1] - f[0] for f in cfree)}
    def table(spr, addr):
        tab = b''
        for k in sorted(spr):
            w, d = spr[k]
            tab += bytes([k[0], k[1], w, k[2]]) + struct.pack('<H', addr[k]) + d[:2]
        tab += b'\xff'
        assert len(tab) <= P['CUT_SPR_MAX'] * 8 + 1, len(tab)
        return tab
    for name, cases in SCENES:
        spr = scene_sprites(cases)
        sfree = [[C1, 0x8000], [P['DBUF'], P['DBUF'] + P['DBUF_SIZE']]]
        sa = first_fit([(k, d) for k, (w, d) in spr.items()], sfree)
        recs = [(sa[k], d, False) for k, (w, d) in spr.items()] + [(P['CUT_SPR'], table(spr, {k: sa[k] + 2 for k in spr}), False)]
        out.append((name, recs))
        stats[name] = '%d sprites, %d bytes' % (len(spr), sum(len(d) for w, d in spr.values()))
    # pv_scene: every sprite its own PZ block (too many to keep unpacked): the first part in the places, the rest at 0x8000
    spr = scene_sprites([('pv_scene', 60)])
    pz = {}
    for k, (w, d) in spr.items():
        kind, b = pack(d); assert kind, ('a sprite PZ cannot store', k)
        assert len(d) <= P['SLOTBUF_MAX'], ('a slot buffer is too small', k, len(d))
        pz[k] = b
    place1 = [[C1, 0x8000], [P['DBUF'], P['DBUF'] + P['DBUF_SIZE']]]; place2 = [[0x8000, 0x8000 + PV_BUF2]]
    sa = {}
    for k, b in sorted(pz.items(), key=lambda t: -len(t[1])):
        f = next((f for f in place2 + place1 if f[1] - f[0] >= len(b)), None)
        assert f is not None, ('pv_scene: no room for', k, len(b), place1, place2)
        sa[k] = f[0]; f[0] += len(b)
    recs1 = [(sa[k], pz[k], True) for k in pz if sa[k] < 0x8000 or sa[k] >= 0xA000] + [(P['CUT_SPR'], table(spr, sa), True)]     # (stored: a packed record would pass through INBUF2 0x8000)
    delta = P['DBUF'] - 0x8000
    recs2 = [(sa[k] + delta, pz[k], True) for k in pz if 0x8000 <= sa[k] < 0xA000]
    out.append(('PRS_CPV', recs1)); out.append(('PRS_CPV2', recs2))
    stats['PRS_CPV'] = '%d sprites, %d bytes raw, %d PZ, free %d' % (len(spr), sum(len(d) for w, d in spr.values()),
                                                                    sum(len(b) for b in pz.values()), sum(f[1] - f[0] for f in place1 + place2))
    return out, stats

if __name__ == '__main__':
    write_inc()
    print('build/assets/cut.inc written')
