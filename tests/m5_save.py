#!/usr/bin/env python3
"""M5: the keys Ctrl+A / Ctrl+G and the saved game (src/m4/save.asm, the save overlay) on the game disk.
The game (tests/m4_game.py setup(), the real game's options) runs with a copy of build/pop800.dsk in drive 0:
  1. level 3, the keyboard (emulator key presses, the MZ-800 matrix: CTRL column 8 bit 6, A column 4 bit 7, G
     column 4 bit 1): Ctrl+G saves (the record = rem_min, rem_tick, level, hitp_beg_lev as at the tick start, SDLPoP's
     process_key point), the bottom line shows GAME SAVED (pixels against tests/m4_game.py draw_text) and is erased
     24 ticks later; Ctrl+G held down saves once; G alone and A alone do nothing; Ctrl+A restarts the level once (the
     level-start overlay runs in the next tick, not again while the keys stay down);
  2. the read side: load_saved (the M7 title's Ctrl+L) after the variables were changed puts the saved values back
     (A = 0); the disk image, after the emulator wrote it back (media_eject), holds the record in POP800.SAV
     (mzdsk-fsmz get): magic POP8, version 1, the words, the checksum;
  3. a write-protected disk (a read-only file: mz800emu ignores media_insert's ro flag), the harness script's Ctrl+G
     bit (control byte bit 7): UNABLE TO SAVE GAME on the bottom line, the image unchanged; load_saved on the fresh
     disk (POP800.SAV all 0): A = 1 (no valid save), the variables untouched;
  4. level 2 (saving is allowed on levels 3-13 only): Ctrl+G does nothing (no text, the disk untouched).
usage: m5_save.py"""
import os, shutil, struct, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools')); sys.path.insert(0, os.path.join(ROOT, 'tests'))
from emu import Emu
from m3_test import write_pack
from m4_game import setup, Font, draw_text, SCRIPT, SCRIPT_PTR
BUILD = os.path.join(ROOT, 'build')
DSK = os.path.join(BUILD, 'pop800.dsk')
MZD = os.path.join(ROOT, 'external', 'mzdisk', 'build', 'mzdsk-fsmz')
REAL_GAME = dict(guards=True, place=[], sword=False)
EV = dict(REM_MIN=1, REM_TICK=2, HITP_BEG_LEV=17)      # objects.asm EV offsets (EV = 0x0280)
FAILS = []

def check(what, ok, detail=''):
    print('  %-62s %s%s' % (what, 'ok' if ok else 'FAILED', '' if ok else '  ' + str(detail)))
    if not ok: FAILS.append(what)

def ticks(e, S, n=1):
    e.call('bp_clear'); e.call('bp_add', addr=S['tick_done'])
    for _ in range(n):
        r = e.run(1000); assert r['stopped_by'] == 'breakpoint', r
    e.call('bp_clear')

def tick_hits(e, S, addr):
    """one tick; True if PC passed addr in it"""
    e.call('bp_clear'); e.call('bp_add', addr=addr); e.call('bp_add', addr=S['tick_done'])
    r = e.run(1000); assert r['stopped_by'] == 'breakpoint', r
    hit = e.call('get_registers')['PC'] == addr
    if hit:
        e.call('bp_clear'); e.call('bp_add', addr=S['tick_done'])
        r = e.run(1000); assert r['stopped_by'] == 'breakpoint', r
    e.call('bp_clear')
    return hit

def state(e, S):
    m = e.mem(0x0280, 32)
    return dict(rem_min=m[EV['REM_MIN']], rem_tick=m[EV['REM_TICK']] | (m[EV['REM_TICK'] + 1] << 8),
                level=e.mem(S['level_number'], 1)[0], hitp=m[EV['HITP_BEG_LEV']])

def record(st):
    r = b'POP8\x01' + struct.pack('<HHHH', st['rem_min'], st['rem_tick'], st['level'], st['hitp'])
    return r + bytes([-sum(r) & 255])

def call(e, S, addr):
    """call a routine from the tick_done breakpoint (return address tick_done); returns the registers after it"""
    reg = e.call('get_registers'); sp = (reg['SP'] - 2) & 0xFFFF
    e.call('mem_write', addr=sp, data_hex='%02x%02x' % (S['tick_done'] & 255, S['tick_done'] >> 8))
    e.call('set_register', reg='SP', value=sp); e.call('set_register', reg='PC', value=addr)
    e.call('bp_clear'); e.call('bp_add', addr=S['tick_done'])
    r = e.run(1000); assert r['stopped_by'] == 'breakpoint', r
    e.call('bp_clear')
    return e.call('get_registers')

def text_ok(e, text):
    """the bottom line (x 70..249, rows 192..199) as SDLPoP's display_text_bottom draws text ('' = black)"""
    from PIL import Image
    ref = Image.new('P', (320, 200)); px = ref.load()
    if text: draw_text(px, text, Font())
    im = e.vram_image(); pm = im.load()
    bad = [(x, y) for y in range(192, 200) for x in range(70, 250) if (pm[x, y] != 0) != (px[x, y] != 0) or (px[x, y] and pm[x, y] != 15)]
    return not bad, bad[:4]

def key(e, *names, down=True):
    for n in names: e.call('input_press_key' if down else 'input_release_key', key=n)

def sav_file(dsk):
    """POP800.SAV's 256 bytes from the disk image (mzdsk-fsmz get: an MZF, 128-byte header)"""
    out = dsk + '.sav.mzf'
    if os.path.exists(out): os.remove(out)
    subprocess.run([MZD, dsk, 'get', 'POP800.SAV', out], check=True, capture_output=True)
    return open(out, 'rb').read()[128:]

def boot_level(e, lv, dsk, ro):
    S = setup(e, lv, opts=REAL_GAME)
    e.call('media_insert', slot='fdc0_fd0', path=dsk, ro=ro)
    e.call('bp_clear'); e.call('bp_add', addr=S['level_ready'])
    r = e.run(1000); assert r['stopped_by'] == 'breakpoint', r
    ticks(e, S, 30)                                 # (the LEVEL text has gone)
    return S

def main():
    tmp = tempfile.mkdtemp(prefix='m5save')
    try:
        dsk = os.path.join(tmp, 'save.dsk'); shutil.copy(DSK, dsk)
        check('fresh disk: POP800.SAV is 256 zero bytes', sav_file(dsk) == bytes(256))
        print('1. level 3, the keyboard')
        with Emu() as e:
            S = boot_level(e, 3, dsk, ro=False)
            key(e, 'G'); ticks(e, S, 2); key(e, 'G', down=False)
            check('G alone: no save, no text', e.mem(S['TEXT_MSG'], 1)[0] == 0)
            before = state(e, S)
            key(e, 'CTRL', 'G'); ticks(e, S, 1)
            msg, gen, tgen = e.mem(S['TEXT_MSG'], 1)[0], e.mem(S['TEXT_MSG_GEN'], 1)[0], e.mem(S['TEXT_GEN'], 1)[0]
            check('Ctrl+G: TEXT_MSG = 1 (GAME SAVED), current', msg == 1 and gen == tgen, (msg, gen, tgen))
            ok, bad = text_ok(e, 'GAME SAVED'); check('Ctrl+G: GAME SAVED on the bottom line', ok, bad)
            ticks(e, S, 1); gen2 = e.mem(S['TEXT_GEN'], 1)[0]
            check('Ctrl+G held: saved once', gen2 == tgen, (tgen, gen2))
            key(e, 'CTRL', 'G', down=False)
            ticks(e, S, 24)
            ok, bad = text_ok(e, ''); check('the text erased after 24 ticks', ok and e.mem(S['TEXT_MSG'], 1)[0] == 0, bad)
            key(e, 'A'); hit = tick_hits(e, S, S['load_level']); key(e, 'A', down=False)
            check('A alone: no restart', not hit)
            key(e, 'CTRL', 'A'); hit1 = tick_hits(e, S, S['load_level']); hit2 = tick_hits(e, S, S['load_level'])
            key(e, 'CTRL', 'A', down=False); ticks(e, S, 2)
            check('Ctrl+A: the level restarts once', hit1 and not hit2, (hit1, hit2))
            print('2. load_saved')
            saved = dict(before)
            e.call('mem_write', addr=0x0280 + EV['REM_MIN'], data_hex='05')
            e.call('mem_write', addr=0x0280 + EV['REM_TICK'], data_hex='0700')
            e.call('mem_write', addr=0x0280 + EV['HITP_BEG_LEV'], data_hex='07')
            e.call('mem_write', addr=S['level_number'], data_hex='09')
            reg = call(e, S, S['load_saved'])
            a = reg['AF'] >> 8 if 'AF' in reg else reg['A']
            got = state(e, S)
            check('load_saved: A = 0, the saved values back', a == 0 and got == saved, (a, got, saved))
            e.call('media_eject', slot='fdc0_fd0')
        rec = sav_file(dsk)
        check('the disk image: POP800.SAV = the record %s' % record(before).hex(), rec[:14] == record(before) and rec[14:] == bytes(242),
              rec[:16].hex())
        print('   saved: %s' % before)
        print('3. a write-protected disk (a read-only file), the script bit')
        dsk3 = os.path.join(tmp, 'save3.dsk'); shutil.copy(DSK, dsk3)
        os.chmod(dsk3, 0o444)       # (mz800emu ignores media_insert's ro; a file it cannot write is a protected disk)
        with Emu() as e:
            S = boot_level(e, 5, dsk3, ro=True)
            write_pack(e, bytes([0x05, 0x85, 0x05, 0xff]), 5, SCRIPT)      # still, still + Ctrl+G, still
            e.call('mem_write', addr=SCRIPT_PTR, data_hex='%02x%02x' % (SCRIPT & 255, SCRIPT >> 8))
            ticks(e, S, 2)
            msg = e.mem(S['TEXT_MSG'], 1)[0]
            check('script Ctrl+G, write-protected: TEXT_MSG = 2', msg == 2, msg)
            ok, bad = text_ok(e, 'UNABLE TO SAVE GAME'); check('UNABLE TO SAVE GAME on the bottom line', ok, bad)
            before = state(e, S)
            reg = call(e, S, S['load_saved'])
            a = reg['AF'] >> 8 if 'AF' in reg else reg['A']
            check('load_saved, no save on the disk: A = 1, nothing changed', a == 1 and state(e, S) == before, (a, state(e, S), before))
            e.call('media_eject', slot='fdc0_fd0')
        check('write-protected: the disk image untouched', open(dsk3, 'rb').read() == open(DSK, 'rb').read())
        os.chmod(dsk3, 0o644)
        print('4. level 2')
        dsk2 = os.path.join(tmp, 'save2.dsk'); shutil.copy(DSK, dsk2)
        with Emu() as e:
            S = boot_level(e, 2, dsk2, ro=False)
            key(e, 'CTRL', 'G'); ticks(e, S, 2); key(e, 'CTRL', 'G', down=False)
            check('level 2, Ctrl+G: no text', e.mem(S['TEXT_MSG'], 1)[0] == 0)
            e.call('media_eject', slot='fdc0_fd0')
        check('level 2, Ctrl+G: the disk untouched', open(dsk2, 'rb').read() == open(DSK, 'rb').read())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print('M5 save test %s' % ('OK' if not FAILS else 'FAILED (%d)' % len(FAILS)))
    sys.exit(1 if FAILS else 0)

if __name__ == '__main__':
    main()
