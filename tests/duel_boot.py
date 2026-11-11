#!/usr/bin/env python3
"""Duel phase 2 (docs/duel-design.md section 12): the duel from the floppy, as a player reaches it. A copy of
build/pop800.dsk boots to PRES's title; Ctrl+D hands over with ACT_DUEL (src/pres/pres.asm p_duel); the launcher loads
POP800.PR3's entries PRS_DUEL1 (the staged pieces, RAM-disk page 6) and PRS_DUEL (the piece over the game's main loop)
around the GAME image (src/boot/boot.asm); the game starts level 1 as always and runs into the patch (duel.asm d_boot),
which lays the staged pieces into their holes and starts the duel (d_entry): the arena, the menu (1 LOCAL). Checked: the handoff's action, every piece
in main RAM at d_entry byte for byte (build/duel_patch.json), the silent sound model, the arena (room 3 drawn, the two
players at their start tiles), the local input bytes (duel.asm d_input: the cursor keys / SHIFT for player 1, W A S D /
Q for player 2, BREAK quit, ENTER rematch), the HUD's first text and a sound on the PSG, then BREAK: back to PRES's title (ACT_TITLE) and a new game from there.
Saves screenshots with --shots DIR.
usage: duel_boot.py [--shots DIR]"""
import json, os, shutil, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools')); sys.path.insert(0, os.path.join(ROOT, 'tests'))
sys.argv, ARGS = sys.argv[:1], sys.argv[1:]                 # (m5_boot reads its own argument)
from emu import Emu
from m3_test import syms
import m5_boot as M5
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


def main():
    shots = None
    if '--shots' in ARGS: shots = ARGS[ARGS.index('--shots') + 1]; os.makedirs(shots, exist_ok=True)
    j = json.load(open(os.path.join(B, 'duel_patch.json')))
    tmp = tempfile.mkdtemp(prefix='duelboot')
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
            ok = all(e.mem(a, n - a) == binb[a - base:n - base] for a, n, k in pieces)
            check('every piece in its hole (PRS_DUEL1 staged, laid in by d_boot)', ok)
            check('the game\'s level 1 started first (level_number 1)', e.mem(G['level_number'], 1)[0] == 1)
            M5.run_to(e, D['d_ready'], 100)
            check('the silent sound model (SND_MODE 0)', e.mem(G['SND_MODE'], 1)[0] == 0)
            kid, gd = e.mem(G['KID_REC'], 16), e.mem(G['GUARD_REC'], 16)
            check('the players at their start tiles (room 3, columns 2 and 7)', (kid[9], kid[4], gd[9], gd[4], gd[11]) == (3, 2, 3, 7, 1),
                  (kid.hex(), gd.hex()))
            M5.run_to(e, D['dlb_mk'], 1000)
            check('the menu over the arena drawn first (room 3 on the screen, duel.asm d_lobby)',
                  e.mem(G['SHOWN_ROOM'], 1)[0] == 3 and e.mem(D['d_netm'], 1)[0] == 0)
            if shots: e.run(2); e.screenshot(os.path.join(shots, 'duel_boot_menu.png'))
            keys(e, ('1',)); M5.run_to(e, D['dlb_go'], 50); keys(e, ('1',), down=False)
            check('1: LOCAL, the match', e.mem(D['d_netm'], 1)[0] == 0)
            M5.run_to(e, D['ds_go'], 400); e.run(2)
            check('the sound: the swords drawn (19) play on the PSG (duel.asm d_snd)',
                  e.mem(D['d_acur'], 1)[0] == 19 and e.mem(G['SP_WAIT'], 1)[0] != 0, (e.mem(D['d_acur'], 1), e.mem(G['SP_WAIT'], 1)))
            print('2. the local input')
            ticks(e, 2)
            check('room 3 on the screen', e.mem(G['SHOWN_ROOM'], 1)[0] == 3)
            check('the bottom text: ROUND 1 (duel.asm d_key)', tuple(e.mem(D['d_key'], 4)) == (0, 1, 0, 0), e.mem(D['d_key'], 4))
            check('no key: 0, 0', ticks(e, 1) == (0, 0))
            for k1, k2, want in ((('RIGHT', 'SHIFT'), ('A', 'Q'), (0x12, 0x11)), (('LEFT', 'UP'), ('D', 'W'), (0x05, 0x06)),
                                 (('DOWN',), ('S',), (0x08, 0x08))):
                keys(e, k1 + k2); got = ticks(e, 2); keys(e, k1 + k2, down=False)
                check('player 1 %s, player 2 %s: %02X %02X' % ('+'.join(k1), '+'.join(k2), want[0], want[1]), got == want, got)
            ticks(e, 30)
            if shots: e.screenshot(os.path.join(shots, 'duel_boot_play.png'))
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
    print('FAILED: %s' % ', '.join(FAILS) if FAILS else 'all ok')
    sys.exit(1 if FAILS else 0)


if __name__ == '__main__':
    main()
