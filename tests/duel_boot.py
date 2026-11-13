#!/usr/bin/env python3
"""Duel phase 2 (docs/duel-design.md section 12): the duel from the floppy, as a player reaches it. A copy of
build/pop800.dsk boots to PRES's title; Ctrl+D hands over with ACT_DUEL (src/pres/pres.asm p_duel); the launcher loads
POP800.PR3's entries PRS_DUEL1 (the staged pieces, RAM-disk page 6) and PRS_DUEL (the piece over the game's main loop)
around the GAME image (src/boot/boot.asm); the game starts level 1 as always and runs into the patch (duel.asm d_boot),
which lays the staged pieces into their holes and starts the duel (d_entry). Run twice: a machine without the Unicard /
MZPico (POP800_UNICARD=0: no NET card) goes straight into the local match, no menu, the fixed arena not drawn; a machine
with it (the INI's default: the NET device) shows the menu over the fixed arena (room 3 drawn, the two players at their
start tiles) and 1 LOCAL starts the match. Checked: the handoff's action, every piece
in main RAM at d_entry byte for byte (build/duel_patch.json; the arenas' piece P_w2 is copied into W2 at each use), the
silent sound model, then the match:
the random arenas (docs/duel-design.md 15) from the seed the duel took from the frame counter: the match's level loaded
(its type, the level number 1 for the logic), the round's room drawn, the players at its start tiles, as
tools/duelsim.py chooses them for that seed; the local input bytes (duel.asm d_input: the cursor keys / SHIFT, / or ? for player 1, W A S D /
Q for player 2, BREAK quit, ENTER rematch), the HUD's first text and a sound on the PSG, player 2's hit point strip
blue (duel.asm d_bswap: the empty icons too; the game's icons red again after), then BREAK: back to PRES's title
(ACT_TITLE) and a new game from there. Saves screenshots with --shots DIR.
usage: duel_boot.py [--shots DIR]"""
import json, os, shutil, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools')); sys.path.insert(0, os.path.join(ROOT, 'tests'))
sys.argv, ARGS = sys.argv[:1], sys.argv[1:]                 # (m5_boot reads its own argument)
from emu import Emu
from m3_test import syms
import m5_boot as M5
import duelsim as DS, popdata as PD
B = os.path.join(ROOT, 'build')
D = syms(os.path.join(B, 'duel.sym')); G, BS, PS = M5.G, M5.BS, M5.PS
FAILS = []


def check(what, ok, detail=''):
    print('  %-70s %s%s' % (what, 'ok' if ok else 'FAILED', '' if ok else '  ' + str(detail)), flush=True)
    if not ok: FAILS.append(what)


def ticks(e, n):
    """n duel ticks (to d_tend); returns the input bytes of the last"""
    for _ in range(n): M5.run_to(e, D['d_tend'], 400)
    return tuple(e.mem(D['d_in1'], 2))


def keys(e, names, down=True):
    for n in names: e.call('input_press_key' if down else 'input_release_key', key=n)


def first_of(e, addrs, limit):
    """run until PC is one of addrs: returns it"""
    e.call('bp_clear')
    for a in addrs: e.call('bp_add', addr=a)
    n = 0
    while n < limit:
        r = e.run(min(1000, limit - n)); n += r['actual_frames']
        if r['stopped_by'] == 'breakpoint':
            e.call('bp_clear'); return e.call('get_registers')['PC']
    raise AssertionError('PC reached none of %s in %d frames' % (['%04X' % a for a in addrs], limit))


def strip(planes, x0, x1):
    """the colours of the hit point strip's pixels x0 <= x < x1 (rows 194-198) that are not black: {colour: count}"""
    out = {}
    for y in range(194, 199):
        for x in range(x0, x1):
            c = sum(((planes[q][y * 40 + x // 8] >> (x & 7)) & 1) << q for q in range(4))
            if c: out[c] = out.get(c, 0) + 1
    return out


def rb(c): return (c & 0xC) | ((c & 1) << 1) | ((c >> 1) & 1)     # (planes I and II, B and R, exchanged)


def run(card, shots, j):
    """the floppy's duel on a machine with (card) or without the Unicard / MZPico (POP800_UNICARD)"""
    tag = 'card' if card else 'nocard'
    print('== %s ==' % ('with the Unicard / MZPico (the NET device): the menu' if card else
                        'without the Unicard (no NET card): the local duel at once'))
    tmp = tempfile.mkdtemp(prefix='duelboot')
    env = os.environ.get('POP800_UNICARD')
    os.environ['POP800_UNICARD'] = '1' if card else '0'
    try:
        dsk = os.path.join(tmp, 'pop800.dsk'); shutil.copy(M5.DSK, dsk)
        with Emu() as e:
            M5.fill_ramdisk(e)
            e.call('media_insert', slot='fdc0_fd0', path=dsk, ro=True)
            e.call('reset')
            M5.to_pres(e)
            print('1. Ctrl+D on the title')
            M5.run_to(e, PS['ts_step'], 3000)
            keys(e, ('CTRL', 'D'))
            M5.run_to(e, PS['p_go'], 100)
            keys(e, ('CTRL', 'D'), down=False)
            ho = e.mem(PS['ho'], 16)
            check('PRES hands over with ACT_DUEL, level 1', ho[2] == BS['ACT_DUEL'] and ho[3] == 1, ho.hex())
            f = M5.run_to(e, G['start'], 3000)
            f += M5.run_to(e, D['d_entry'], 3000)
            print('   PRES -> the duel\'s entry: %d frames' % f)
            for a, hx in j['main']:
                check('the main piece at %04X (PRS_DUEL)' % a, e.mem(a, len(hx) // 2).hex() == hx)
            pieces = sorted((D[k], D[k + '_end'], k) for k in D if k.startswith('P_') and not k.endswith('_end'))
            binb = bytearray(open(os.path.join(B, 'duel.bin'), 'rb').read()); base = min(p[0] for p in pieces)
            binb[j['build_at'] - base:j['build_at'] - base + 2] = j['build_id'].to_bytes(2, 'little')   # (duelpatch.py's)
            ok = all(e.mem(a, n - a) == binb[a - base:n - base] for a, n, k in pieces if k != 'P_w2')
            check('every piece in its hole (PRS_DUEL1 staged, laid in by d_boot)', ok)
            check('the game\'s level 1 started first (level_number 1)', e.mem(G['level_number'], 1)[0] == 1)
            if card:
                M5.run_to(e, D['dlb_mk'], 1000)
                check('the silent sound model (SND_MODE 0)', e.mem(G['SND_MODE'], 1)[0] == 0)
                kid, gd = e.mem(G['KID_REC'], 16), e.mem(G['GUARD_REC'], 16)
                check('the players at the fixed arena\'s start tiles (room 3, columns 2 and 7)', (kid[9], kid[4], gd[9], gd[4], gd[11]) == (3, 2, 3, 7, 1),
                      (kid.hex(), gd.hex()))
                check('the menu over the arena drawn first (room 3 on the screen, duel.asm d_lobby)',
                      e.mem(G['SHOWN_ROOM'], 1)[0] == 3 and e.mem(D['d_netm'], 1)[0] == 0)
                if shots: e.run(2); e.screenshot(os.path.join(shots, 'duel_boot_menu.png'))
                keys(e, ('1',)); M5.run_to(e, D['dlb_go'], 50); keys(e, ('1',), down=False)
                check('1: LOCAL, the match', e.mem(D['d_netm'], 1)[0] == 0)
                M5.run_to(e, D['d_ready'], 100)
            else:
                pc = first_of(e, (D['dlb_mk'], D['d_draw'], D['d_ready']), 1000)
                check('no NET card: straight into the local match (no menu, no arena drawn before it)',
                      pc == D['d_ready'] and e.mem(D['d_netm'], 1)[0] == 0, '%04X' % pc)
                check('the silent sound model (SND_MODE 0)', e.mem(G['SND_MODE'], 1)[0] == 0)
            seed = int.from_bytes(e.mem(D['d_seed'], 2), 'little')
            lv = DS.match_level(seed, 0); ai = DS.round_arena(seed, 0, lv, 0, None); _, room, row, c1 = DS.arenas()[ai]
            check('the seed %04X: level %d (%s) loaded, the level number 1 for the logic' % (seed, lv, 'palace' if PD.LEVEL_TYPE[lv] else 'dungeon'),
                  (e.mem(D['d_lvl'], 1)[0], e.mem(G['LEVEL_TYPE'], 1)[0], e.mem(G['level_number'], 1)[0]) == (lv, PD.LEVEL_TYPE[lv], 1))
            kid, gd = e.mem(G['KID_REC'], 16), e.mem(G['GUARD_REC'], 16)
            check('its arena %d: room %d, the players on row %d, columns %d and %d' % (ai, room, row, c1, c1 + DS.START_GAP),
                  (e.mem(D['d_aidx'], 1)[0], kid[9], kid[5], kid[4], gd[9], gd[5], gd[4]) == (ai, room, row, c1, room, row, c1 + DS.START_GAP),
                  (kid.hex(), gd.hex()))
            M5.run_to(e, D['ds_go'], 400); e.run(2)
            check('the sound: the swords drawn (19) play on the PSG (duel.asm d_snd)',
                  e.mem(D['d_acur'], 1)[0] == 19 and e.mem(G['SP_WAIT'], 1)[0] != 0, (e.mem(D['d_acur'], 1), e.mem(G['SP_WAIT'], 1)))
            print('2. the local input')
            ticks(e, 2)
            check('the arena\'s room %d on the screen' % room, e.mem(G['SHOWN_ROOM'], 1)[0] == room)
            check('the bottom text: ROUND 1 (duel.asm d_key)', tuple(e.mem(D['d_key'], 4)) == (0, 1, 0, 0), e.mem(D['d_key'], 4))
            check('no key: 0, 0', ticks(e, 1) == (0, 0))
            for k1, k2, want in ((('RIGHT', 'SHIFT'), ('A', 'Q'), (0x12, 0x11)), (('LEFT', 'UP'), ('D', 'W'), (0x05, 0x06)),
                                 (('DOWN',), ('S',), (0x08, 0x08))):
                keys(e, k1 + k2); got = ticks(e, 2); keys(e, k1 + k2, down=False)
                check('player 1 %s, player 2 %s: %02X %02X' % ('+'.join(k1), '+'.join(k2), want[0], want[1]), got == want, got)
            # player 1's button also on / and ? (the user's key option A, docs/duel-design.md 16.3), SHIFT not pressed
            for k, bit in (('/', 0x01), ('?', 0x02)):
                keys(e, ('RIGHT', k)); got = ticks(e, 2); km = e.mem(G['KEYMAT'] + 7, 2); keys(e, ('RIGHT', k), down=False)
                check('player 1 RIGHT+%s (the matrix 7/%d, no SHIFT): the button, 12 00' % (k, bit >> 1),
                      got == (0x12, 0) and km[0] & 3 == bit and not km[1] & 1, (got, km.hex()))
            ticks(e, 30)
            if shots: e.screenshot(os.path.join(shots, 'duel_boot_play_%s.png' % tag))
            # player 2's strip blue, the empty icons too (duel.asm d_bswap): both players at 1 of 3 hit points (a poke:
            # the strips are drawn when the hit points change), then the right strip = the left one's colours, B <-> R
            icons = e.mem(G['hp_full'], 40)
            e.call('mem_write', addr=G['HITP_CURR'], data_hex='01'); e.call('mem_write', addr=G['GUARDHP_CURR'], data_hex='01')
            ticks(e, 2); pl = e.vram_planes()
            left, right = strip(pl, 0, 21), strip(pl, 299, 320)
            check('player 2\'s strip: 1 full and 2 empty icons, blue where player 1\'s are red',
                  right and right == {rb(c): n for c, n in left.items()} and not any(c & 3 == 2 for c in right), (left, right))
            check('the game\'s icons (hp_full, hp_empty) red again after the drawing', e.mem(G['hp_full'], 40) == icons)
            if shots: e.screenshot(os.path.join(shots, 'duel_boot_hp_%s.png' % tag))
            keys(e, ('ENTER',)); got = ticks(e, 1); keys(e, ('ENTER',), down=False)
            check('ENTER: the rematch bit', got == (0x40, 0), got)
            print('3. BREAK: back to the title')
            keys(e, ('BREAK',)); got = ticks(e, 1)
            check('BREAK: the quit bit, the match quit (3)', got[0] == 0x20 and e.mem(D['d_match'], 1)[0] == 3, got)
            f = M5.run_to(e, PS['pres'], 3000); keys(e, ('BREAK',), down=False)
            ho = e.mem(BS['HO_MAIN'], 16)
            check('PRES with ACT_TITLE (%d frames)' % f, ho[2] == BS['ACT_TITLE'], ho.hex())
            M5.title_start(e, 'SPACE')
            M5.run_to(e, G['level_ready'], 3000)
            check('then a new game: the game\'s own main loop at level_ready (no patch)',
                  e.mem(G['level_ready'], 8) == open(os.path.join(B, 'm4game.bin'), 'rb').read()[G['level_ready'] - 0x1200:][:8])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if env is None: os.environ.pop('POP800_UNICARD', None)
        else: os.environ['POP800_UNICARD'] = env


def main():
    shots = None
    if '--shots' in ARGS: shots = ARGS[ARGS.index('--shots') + 1]; os.makedirs(shots, exist_ok=True)
    j = json.load(open(os.path.join(B, 'duel_patch.json')))
    for card in (False, True): run(card, shots, j)
    print('FAILED: %s' % ', '.join(FAILS) if FAILS else 'all ok')
    sys.exit(1 if FAILS else 0)


if __name__ == '__main__':
    main()
