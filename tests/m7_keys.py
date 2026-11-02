#!/usr/bin/env python3
"""M7 step 10: the keys in the game (docs/m7-design.md §6, §18), through the keyboard matrix (emulator key presses,
get_controls' keyboard path; the logic against SDLPoP and the script path: tools/oracle_suite.py and tests/m4_test.py on
tests/m7_scripts/key_*.txt).
  1. SPACE: the time text (pixels against tests/m4_game.py draw_text), once per press, not the button; SHIFT and the fire
     bit are the button; keys that do nothing leave the logic alone.
  2. Ctrl+S, Ctrl+V: the texts (pixels), 24 ticks; Ctrl+S: the PSG silent while a stream runs and every wait on it the
     same; the sound model's bytes per tick equal to a run without it (ticks mode); on again: the stream is heard.
  3. The pause (BREAK): GAME PAUSED (pixels), all else on the screen as it was, the logic state unchanged, TICKS and the
     clock stand, FRAMES counts, the PSG muted, any key but CTRL / SHIFT resumes, the stream goes on where it was: the PSG
     states of a run with the pause equal those of a run without it.
  4. Shift+L: levels 1-3, the 15-minute cap; level 4: nothing. Enter and SHIFT while dead: the level restarts; Enter
     before alive 7 nothing.
  5. The launched game (a copy of build/pop800.dsk): Ctrl+R and Ctrl+Q through PRES to the title, then a new game equal
     to a direct level 1 start; Shift+L through the level 2 cutscene; the sound off goes through PRES and the swap, the
     ending turns it on.
  6. The release has no cheat code. Run from the cheat build (build/cheat/tests/m7_keys.py, `make cheats`): the cheats
     on the keyboard and the resident cost.
usage: m7_keys.py [part ...]   (parts: texts sound pause levels launched release; in build/cheat: cheats)"""
import os, shutil, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools')); sys.path.insert(0, os.path.join(ROOT, 'tests'))
from emu import Emu
from m3_test import syms, write_pack
from m4_game import setup, Font, draw_text, SCRIPT, SCRIPT_PTR
from m4_test import encode
import kidsim, sndsim
BUILD = os.path.join(ROOT, 'build')
REAL_GAME = dict(guards=True, place=[], sword=False)
GUARDS_OFF = dict(guards=False, place=[], sword=False)
EV = 0x0280; KV = 0x0A00; FRAMES = 0x0800; TICKS = 0x0872; INPUT = 0x086B
FAILS = []

def check(what, ok, detail=''):
    print('  %-84s %s%s' % (what, 'ok' if ok else 'FAILED', '' if ok else '  ' + str(detail)), flush=True)
    if not ok: FAILS.append(what)
def word(e, a):
    b = e.mem(a, 2); return b[0] | (b[1] << 8)
def ticks(e, S, n=1):
    e.call('bp_clear'); e.call('bp_add', addr=S['tick_done'])
    for _ in range(n):
        r = e.run(1000); assert r['stopped_by'] == 'breakpoint', r
    e.call('bp_clear')
def key(e, *names, down=True):
    for n in names: e.call('input_press_key' if down else 'input_release_key', key=n)
def press(e, S, *names, n=1):
    """the keys down for n ticks, then up (one more tick)"""
    key(e, *names); ticks(e, S, n); key(e, *names, down=False); ticks(e, S, 1)
def hits(e, S, addr, n=1):
    """n ticks; how many times PC passed addr"""
    c = 0
    e.call('bp_clear'); e.call('bp_add', addr=addr); e.call('bp_add', addr=S['tick_done'])
    for _ in range(n):
        while True:
            r = e.run(1000); assert r['stopped_by'] == 'breakpoint', r
            if e.call('get_registers')['PC'] == addr:
                c += 1
                e.call('bp_clear'); e.call('bp_add', addr=S['tick_done'])
                r = e.run(1000); assert r['stopped_by'] == 'breakpoint', r
                e.call('bp_clear'); e.call('bp_add', addr=addr); e.call('bp_add', addr=S['tick_done'])
            break
    e.call('bp_clear')
    return c
FONT = Font()
def text_ok(e, text):
    """the bottom line (x 70..249, rows 192..199) as SDLPoP's display_text_bottom draws text ('' = black)"""
    from PIL import Image
    ref = Image.new('P', (320, 200)); px = ref.load()
    if text: draw_text(px, text, FONT)
    pm = e.vram_image().load()
    bad = [(x, y) for y in range(192, 200) for x in range(70, 250) if (pm[x, y] != 0) != (px[x, y] != 0) or (px[x, y] and pm[x, y] != 15)]
    return not bad, bad[:4]
def logic(e, S):
    """the logic state: KV, EV (bottom-text generation counters normalised), OV, the guards' records, the level"""
    k = bytearray(e.mem(KV, 256)); k[0xD0:0xE2] = bytes(18)
    ev = bytearray(e.mem(EV, 31)); ev[25] = int(ev[28] == ev[25] ^ 255); ev[28] = 0; ev[24] = 0; ev[29] = 0; ev[30] = 0
    return {'KV': bytes(k), 'EV': bytes(ev), 'OV': e.mem(0x0B00, 256), 'guard': e.mem(S['gv_start'], S['gv_end'] - S['gv_start']),
            'level': e.mem(S['LEVEL'], 2305), 'snd': e.mem(S['SND'], 7) + e.mem(S['SND_LEFT'], 3)}
def diff(a, b): return [k for k in a if a[k] != b[k]]
def start(e, lv, opts=GUARDS_OFF, n=60):
    S = setup(e, lv, opts=opts)
    e.call('mem_write', addr=0x02A8, data_hex='00')
    e.call('bp_clear'); e.call('bp_add', addr=S['level_ready'])
    r = e.run(1000); assert r['stopped_by'] == 'breakpoint', r
    ticks(e, S, n)
    return S
def run_script_game(e, S, moves, keys=None):
    write_pack(e, encode(moves, keys or [0] * len(moves)), 5, SCRIPT)
    e.call('mem_write', addr=SCRIPT_PTR, data_hex='%02x%02x' % (SCRIPT & 255, SCRIPT >> 8))
def psg(e): return sndsim.emu_state(e.call('get_periph_sn76489'))
def muted(st): return st[0] == st[2] == st[4] == st[6] == 15        # (sndsim.emu_state: attenuation, tone per channel)
def call_at_tick_done(e, S, addr, a):
    """from the tick_done breakpoint: call addr with A = a, back to tick_done"""
    reg = e.call('get_registers'); sp = (reg['SP'] - 2) & 0xFFFF
    e.call('mem_write', addr=sp, data_hex='%02x%02x' % (S['tick_done'] & 255, S['tick_done'] >> 8))
    e.call('set_register', reg='SP', value=sp); e.call('set_register', reg='PC', value=addr)
    e.call('set_register', reg='AF', value=(a << 8) | (reg['AF'] & 255))
    e.call('bp_clear'); e.call('bp_add', addr=S['tick_done'])
    r = e.run(100); assert r['stopped_by'] == 'breakpoint', r
    e.call('bp_clear')

def part_texts():
    print('1. SPACE, the button, Ctrl+V: level 1 from the keyboard')
    with Emu() as e:
        S = start(e, 1)
        ok, bad = text_ok(e, ''); check('the LEVEL text has gone', ok, bad)
        a = logic(e, S); press(e, S, 'A'); press(e, S, 'L'); press(e, S, 'R'); press(e, S, 'CTRL'); press(e, S, 'RETURN')
        b = logic(e, S)
        ev = lambda s: s['EV'][4:]                                    # (the clock runs)
        check('A, L, R, CTRL, Enter alone: no text, no restart', ev(a) == ev(b) and text_ok(e, '')[0], (ev(a).hex(), ev(b).hex()))
        key(e, 'SPACE'); ticks(e, S, 1)
        check('SPACE: is the time text, 24 ticks', word(e, S['TEXT_REM']) in (23, 24) and text_ok(e, '60 MINUTES LEFT')[0], (word(e, S['TEXT_REM']), text_ok(e, '60 MINUTES LEFT')[1]))
        check('SPACE is not the button (INPUT bit 4, control_shift)', e.mem(INPUT, 1)[0] & 0x10 == 0 and e.mem(S['C_SHIFT'], 1)[0] == 0)
        ticks(e, S, 30); key(e, 'SPACE', down=False); ticks(e, S, 1)
        check('SPACE held: once; the text erased after 24 ticks', text_ok(e, '')[0] and word(e, S['TEXT_REM']) == 0, word(e, S['TEXT_REM']))
        key(e, 'SHIFT'); ticks(e, S, 1)
        check('SHIFT is the button; the time text does not come (SPACE with SHIFT: not SPACE in process_key)', e.mem(INPUT, 1)[0] & 0x10 != 0)
        key(e, 'SPACE'); ticks(e, S, 2); key(e, 'SPACE', 'SHIFT', down=False); ticks(e, S, 1)
        check('   SHIFT+SPACE: no text', text_ok(e, '')[0] and word(e, S['TEXT_REM']) == 0)
        ticks(e, S, 5)
        key(e, 'CTRL', 'V'); ticks(e, S, 1)
        check('Ctrl+V: the version on the bottom line', text_ok(e, kidsim.VERSION_TEXT)[0], text_ok(e, kidsim.VERSION_TEXT)[1])
        key(e, 'CTRL', 'V', down=False); ticks(e, S, 24)
        check('   erased after 24 ticks', text_ok(e, '')[0])

def part_sound():
    print('2. Ctrl+S: the PSG silent, the stream and the waits on it as before')
    with Emu() as e:
        S = start(e, 1)
        e.call('mem_write', addr=S['SND_MODE'], data_hex='01')
        key(e, 'CTRL', 'S'); ticks(e, S, 1); key(e, 'CTRL', 'S', down=False)
        check('first press: SOUND OFF on the bottom line, the option byte 1', text_ok(e, 'SOUND OFF')[0] and e.mem(0x02A8, 1)[0] == 1, text_ok(e, 'SOUND OFF')[1])
        ticks(e, S, 24)
        check('   erased after 24 ticks', text_ok(e, '')[0])
        call_at_tick_done(e, S, S['snd_start'], 41)                   # the end music (levels' 41: 12.75 s)
        n = 0; quiet = True; e.call('bp_clear'); e.call('bp_add', addr=S['tick_done'])
        f0 = word(e, FRAMES)
        while e.mem(S['SP_WAIT'], 1)[0] and word(e, FRAMES) - f0 < 1000:
            r = e.run(1000); assert r['stopped_by'] == 'breakpoint'
            quiet = quiet and muted(psg(e)); n += 1
        off_frames = word(e, FRAMES) - f0
        check('music 41 runs its %d frames (12.75 s), the PSG muted all the way (%d samples)' % (off_frames, n), quiet and abs(off_frames - 637) < 12, (quiet, off_frames))
        call_at_tick_done(e, S, S['snd_start'], 41)
        key(e, 'CTRL', 'S'); ticks(e, S, 1); key(e, 'CTRL', 'S', down=False)
        check('Ctrl+S again: SOUND ON', text_ok(e, 'SOUND ON')[0], text_ok(e, 'SOUND ON')[1])
        heard = False
        for i in range(100):
            ticks(e, S, 1)
            heard = heard or not muted(psg(e))
        check('   the running stream is heard again', heard)
        call_at_tick_done(e, S, S['snd_halt'], 0)
    moves = [(0, 0, 0)] * 10 + [(1, 0, 0)] * 40 + [(0, 0, 0)] * 40
    tr = []
    for off in (False, True):
        with Emu() as e:
            S = setup(e, 1, opts=GUARDS_OFF)
            e.call('mem_write', addr=S['SND_MODE'], data_hex='02')
            keys = [0] * len(moves)
            if off: keys[5] = kidsim.KEY_CTRL_S << 3
            run_script_game(e, S, moves + [(0, 0, 0)] * 10, keys + [0] * 10)
            e.call('bp_clear'); e.call('bp_add', addr=S['level_ready']); e.run(1000)
            t = []
            for i in range(len(moves)):
                ticks(e, S, 1)
                t.append((e.mem(S['SND'], 2) + e.mem(S['SND_LEFT'], 2), e.mem(KV, 16)))
            tr.append(t)
    check('the script\'s ticks mode with Ctrl+S: queued, current, SND_LEFT, NEED_L1M and the kid equal every tick', tr[0] == tr[1])

def part_pause():
    print('3. the pause: BREAK')
    def stream(pause):
        with Emu() as e:
            S = start(e, 1)
            e.call('mem_write', addr=S['SND_MODE'], data_hex='03')
            call_at_tick_done(e, S, S['snd_start'], 41)
            states = []
            def until(addr=None, frames=None):
                """run, a PSG state at every frame the player plays, until PC = addr or that many states"""
                e.call('bp_clear'); e.call('bp_add', addr=S['spi_done'])
                if addr: e.call('bp_add', addr=addr)
                while True:
                    r = e.run(50); assert r['stopped_by'] == 'breakpoint', r
                    if addr and e.call('get_registers')['PC'] == addr: break
                    states.append(psg(e))
                    if frames and len(states) >= frames: break
                e.call('bp_clear')
            until(frames=120)
            if pause:
                until(S['tick_done'])
                v0 = e.vram_image().load(); clock = word(e, S['REM_TICK']); ring0 = e.mem(S['SP_PTR'], 2)
                key(e, 'BREAK')
                until(syms(os.path.join(BUILD, 'ovl_keys.sym'))['dp_rel'])
                tk = word(e, TICKS)
                key(e, 'BREAK', down=False)
                e.run(20)
                f0 = word(e, FRAMES); e.run(100); f1 = word(e, FRAMES)
                st = psg(e); pix = e.vram_image().load()
                check('paused: FRAMES counts (%d in 100 frames), the PSG muted, no stream for the ISR' % (f1 - f0),
                      f1 - f0 == 100 and muted(st) and e.mem(S['SP_WAIT'], 1)[0] == 0, (f1 - f0, st))
                ok, bad = text_ok(e, 'GAME PAUSED'); check('GAME PAUSED on the bottom line', ok, bad)
                other = [(x, y) for y in range(200) for x in range(320) if not (y >= 192 and 70 <= x < 250) and pix[x, y] != v0[x, y]]
                check('the rest of the screen as it was', not other, other[:4])
                key(e, 'CTRL'); e.run(20); key(e, 'CTRL', down=False)
                check('CTRL alone does not resume', word(e, TICKS) == tk)
                key(e, 'SHIFT'); e.run(20); key(e, 'SHIFT', down=False)
                check('SHIFT alone does not resume', word(e, TICKS) == tk)
                e.run(10)
                check('the clock and TICKS stand', word(e, S['REM_TICK']) == clock and word(e, TICKS) == tk)
                check('the stream\'s read pointer has not moved', e.mem(S['SP_PTR'], 2) == ring0)
                key(e, 'Z')
                n0 = len(states); until(S['tick_done'])
                key(e, 'Z', down=False)
                check('a key resumes: the tick ends (TICKS as it was: the tick that paused)', word(e, TICKS) == tk, (tk, word(e, TICKS)))
                check('   SP_WAIT back: the stream runs', e.mem(S['SP_WAIT'], 1)[0] != 0)
                ok, bad = text_ok(e, ''); check('   the text erased at the resume\'s tick end', ok, bad)
            until(frames=320)
            return states
    ref = stream(False); got = stream(True)
    # (one group may be sampled at the resume itself: the whole sequence from the same stream position must agree)
    bad = [i for i, (x, y) in enumerate(zip(ref, got)) if x != y]
    check('the PSG state at the player\'s every frame: a run with the pause equals one without (%d frames)' % len(ref), not bad, bad[:5])
    with Emu() as e:
        S = start(e, 1)
        a = logic(e, S); tk = word(e, TICKS)
        key(e, 'BREAK')
        e.run(60); key(e, 'BREAK', down=False); e.run(60)
        check('no sound: logic unchanged during the pause (KV, EV, OV, guards, level, the sound state)', not diff(a, logic(e, S)), diff(a, logic(e, S)))
        key(e, 'SPACE'); e.call('bp_clear'); e.call('bp_add', addr=S['tick_done']); r = e.run(20); assert r['stopped_by'] == 'breakpoint'; e.call('bp_clear')
        key(e, 'SPACE', down=False); ticks(e, S, 1)
        check('the resuming key (SPACE) has no effect of its own', e.mem(S['IS_SHOW_TIME'], 1)[0] == 0 and text_ok(e, '')[0])
        key(e, 'BREAK')
        e.run(60); key(e, 'BREAK', down=False); e.run(30); key(e, 'BREAK'); e.call('bp_clear'); e.call('bp_add', addr=S['tick_done']); r = e.run(20); assert r['stopped_by'] == 'breakpoint'; e.call('bp_clear'); ticks(e, S, 3); key(e, 'BREAK', down=False); ticks(e, S, 2)
        check('BREAK resumes too, held: it does not pause again', word(e, TICKS) > tk + 2 and text_ok(e, '')[0])
        # the blink's dark phase and a text under the pause
        e.call('mem_write', addr=S['TEXT_REM'], data_hex='2500'); e.call('mem_write', addr=S['TEXT_TOTAL'], data_hex='2001')   # 37 of 288: 37 % 12 = 1 ...
        ticks(e, S, 1)
        for i in range(12):
            if e.mem(S['TEXT_REM'], 1)[0] % 12 > 3 and text_ok(e, '')[0]: break
            ticks(e, S, 1)
        check('   (the death text in its dark phase)', text_ok(e, '')[0])
        key(e, 'BREAK'); e.run(40); key(e, 'BREAK', down=False); e.run(20)
        check('the pause shows through the blink\'s dark phase', text_ok(e, 'GAME PAUSED')[0], text_ok(e, 'GAME PAUSED')[1])
        key(e, 'Z'); e.call('bp_clear'); e.call('bp_add', addr=S['tick_done']); r = e.run(20); assert r['stopped_by'] == 'breakpoint'; e.call('bp_clear'); key(e, 'Z', down=False)
        check('   the resume erases the death text as do_paused does (its timer 0: no title)', word(e, S['TEXT_REM']) == 0 and word(e, S['TEXT_TOTAL']) == 0 and text_ok(e, '')[0])

def part_levels():
    print('4. Shift+L; Enter and SHIFT while dead')
    with Emu() as e:
        S = start(e, 1)
        key(e, 'SHIFT', 'L'); h = hits(e, S, S['load_level'], 1); key(e, 'L', 'SHIFT', down=False)
        check('Shift+L on level 1: level 2, 15:719 minus the tick', h == 1 and e.mem(S['level_number'], 1)[0] == 2 and e.mem(S['REM_MIN'], 1)[0] == 15, (h, e.mem(S['level_number'], 1)[0], e.mem(S['REM_MIN'], 1)[0]))
        ticks(e, S, 10); key(e, 'SHIFT', 'L'); ticks(e, S, 2); key(e, 'L', 'SHIFT', down=False); ticks(e, S, 10)
        key(e, 'SHIFT', 'L'); ticks(e, S, 2); key(e, 'L', 'SHIFT', down=False); ticks(e, S, 3)
        check('level 2 -> 3 -> 4', e.mem(S['level_number'], 1)[0] == 4, e.mem(S['level_number'], 1)[0])
        key(e, 'SHIFT', 'L'); ticks(e, S, 2); key(e, 'L', 'SHIFT', down=False); ticks(e, S, 2)
        check('level 4: Shift+L does nothing', e.mem(S['level_number'], 1)[0] == 4)
    sp = os.path.join(ROOT, 'tests', 'm7_scripts', 'death_music.txt')
    moves, patches = kidsim.read_script(sp)
    for name, keyname in (('Enter', 'RETURN'), ('SHIFT', 'SHIFT')):
        with Emu() as e:
            S = setup(e, kidsim.script_level(sp), opts=REAL_GAME)
            run_script_game(e, S, moves + [(0, 0, 0)] * 2)
            e.call('bp_clear'); e.call('bp_add', addr=S['level_ready']); e.run(1000); e.call('bp_clear')
            for (rm, p, t, m) in patches:
                e.call('mem_write', addr=S['LEVEL'] + (rm - 1) * 30 + p, data_hex='%02x' % t)
                e.call('mem_write', addr=S['LEVEL'] + 720 + (rm - 1) * 30 + p, data_hex='%02x' % m)
            n = 0
            while not (0 <= e.mem(S['K_ALIVE'], 1)[0] < 100) and n < 200: ticks(e, S, 1); n += 1
            e.call('mem_write', addr=SCRIPT_PTR, data_hex='0000')          # (from here the keyboard)
            if keyname == 'RETURN':
                key(e, keyname); h0 = hits(e, S, S['load_level'], 1); key(e, keyname, down=False)
                check('Enter at alive %d (< 7): nothing' % e.mem(S['K_ALIVE'], 1)[0], h0 == 0)
            while e.mem(S['K_ALIVE'], 1)[0] < 8: ticks(e, S, 1)
            key(e, keyname); h = hits(e, S, S['load_level'], 2); key(e, keyname, down=False)
            check('%s while dead (alive 8): the level restarts, once' % name, h == 1 and e.mem(S['K_ALIVE'], 1)[0] >= 128 and e.mem(S['HITP_CURR'], 1)[0] > 0, (h, e.mem(S['K_ALIVE'], 1)[0]))

def part_launched():
    sys.argv = sys.argv[:1]
    import m5_boot as M5, m7_title as MT
    G, PS = M5.G, M5.PS
    print('5. the launched game (the disk)')
    tmp = tempfile.mkdtemp(prefix='m7keys')
    try:
        dsk = os.path.join(tmp, 'pop800.dsk'); shutil.copy(M5.DSK, dsk)
        h = MT.direct(1, (60, 719))
        for keyname, name in (('R', 'Ctrl+R'), ('Q', 'Ctrl+Q')):
            with Emu() as e:
                MT.boot(e, dsk); M5.title_start(e, 'SPACE')
                M5.run_to(e, G['level_ready'], 2000); ticks(e, G, 60)
                key(e, 'CTRL', keyname)
                M5.run_to(e, PS['pres'], 2000); key(e, 'CTRL', keyname, down=False)
                ho = e.mem(M5.BS['HO_MAIN'], 16)
                check('%s: PRES with ACT_TITLE' % name, ho[2] == M5.BS['ACT_TITLE'], ho.hex())
                M5.run_to(e, PS['ts_step'], 2000)
                check('   the title\'s step a', chr(e.mem(PS['t_step'], 1)[0]) == 'a')
                M5.title_start(e, 'SPACE')
                f = MT.launched(e)
            MT.compare_game('a new game after %s' % name, h, f)
        with Emu() as e:
            MT.boot(e, dsk); M5.title_start(e, 'SPACE')
            M5.run_to(e, G['level_ready'], 2000); ticks(e, G, 60)
            key(e, 'CTRL', 'S'); ticks(e, G, 1); key(e, 'CTRL', 'S', down=False)
            key(e, 'SHIFT', 'L')
            M5.run_to(e, PS['pres'], 2000); key(e, 'SHIFT', 'L', down=False)
            ho = e.mem(M5.BS['HO_MAIN'], 16)
            check('Shift+L: PRES with the cutscene before level 2, 15 minutes, the option sound off', ho[2:5] == bytes([M5.BS['ACT_CUTSCENE'], 2, 15]) and ho[8] == 1, ho.hex())
            n = 0; quiet = True; arm = 0
            e.call('bp_clear'); e.call('bp_add', addr=G['start'])
            while True:
                r = e.run(50); n += r['actual_frames']
                if r['stopped_by'] == 'breakpoint' or n > 6000: break
                quiet = quiet and muted(psg(e)); arm += e.mem(PS['SP_WAIT'], 1)[0] != 0
            e.call('bp_clear')
            check('   the cutscene plays its music silently (%d of %d samples with a stream), then the game' % (arm, n // 50), quiet and arm > 0 and n <= 6000, (quiet, arm, n))
            M5.run_to(e, G['level_ready'], 500)
            sp1 = e.mem(G['spo_1'], 2)
            check('   level 2: the sound still off (the PSG writes patched), option 1', sp1 == b'\0\0' and e.mem(0x02A8, 1)[0] == 1, sp1.hex())
            key(e, 'CTRL', 'S'); ticks(e, G, 1); key(e, 'CTRL', 'S', down=False)
            check('   Ctrl+S: on again', e.mem(G['spo_1'], 2) == bytes([0xD3, 0xF2]) and e.mem(0x02A8, 1)[0] == 0)
        with Emu() as e:                                        # the ending turns the sound on
            MT.boot(e, dsk); M5.title_start(e, 'SPACE')
            M5.run_to(e, G['level_ready'], 2000); ticks(e, G, 5)
            key(e, 'CTRL', 'S'); ticks(e, G, 1); key(e, 'CTRL', 'S', down=False)
            e.call('mem_write', addr=G['GAME_OVER'], data_hex='02')
            M5.run_to(e, PS['pres'], 2000); e.run(100)
            check('the ending turns the sound on (SDLPoP end_sequence_anim): PRES\'s option 0, its writes in place',
                  e.mem(PS['ho'] + 8, 1)[0] == 0 and e.mem(PS['spo_1'], 2) == bytes([0xD3, 0xF2]), e.mem(PS['spo_1'], 2).hex())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def part_release():
    print('6. the release: no cheat code')
    S = syms(os.path.join(BUILD, 'm4game.sym')); K = syms(os.path.join(BUILD, 'ovl_keys.sym'))
    check('no cheat symbols in the game or the keys overlay', not [k for k in list(S) + list(K) if k.startswith(('ck_', 'kl_cheat', 'blind_set', 'td_timer'))])
    rel = open(os.path.join(BUILD, 'ovl_keys.bin'), 'rb').read()
    ovl = open(os.path.join(BUILD, 'm4ovl.bin'), 'rb').read() + open(os.path.join(BUILD, 'm4game.bin'), 'rb').read()
    check('the keys overlay in the release pack', rel in ovl, len(rel))
    cb = os.path.join(BUILD, 'cheat', 'build', 'ovl_keys.bin')
    if os.path.exists(cb):
        C = syms(os.path.join(BUILD, 'cheat', 'build', 'ovl_keys.sym')); cg = syms(os.path.join(BUILD, 'cheat', 'build', 'm4game.sym'))
        cheat = open(cb, 'rb').read()
        table = cheat[C['ck_tab'] - C['ovl_entry']:C['ck_tab'] - C['ovl_entry'] + 16]
        code = cheat[C['ck_kill'] - C['ovl_entry']:C['ck_revive'] - C['ovl_entry']]
        check('the cheat build\'s code is not in the release binaries (the table, K\'s routine)', table not in ovl and code not in ovl)
        print('  resident: release main end %04X (%d free), block 2 end %04X (%d free); CHEATS=1 main %04X (%d free), block 2 %04X (%d free)' % (
            S['end_of_code'], 0x7C00 - S['end_of_code'], S['block2_end'], 0xEC00 - S['block2_end'],
            cg['end_of_code'], 0x7C00 - cg['end_of_code'], cg['block2_end'], 0xEC00 - cg['block2_end']))
        print('  the keys overlay: release %d bytes, CHEATS=1 %d bytes (W1: 1024)' % (len(rel), len(cheat)))
    else: check('(the cheat build exists: make cheats)', False)

def part_cheats():
    print('the cheats on the keyboard (CHEATS=1)')
    with Emu() as e:
        S = start(e, 1)
        m0 = e.mem(S['REM_MIN'], 1)[0]
        press(e, S, 'F1'); check('F1 (+): a minute more, the time shown', e.mem(S['REM_MIN'], 1)[0] == m0 + 1 and text_ok(e, '61 MINUTES LEFT')[0], text_ok(e, '61 MINUTES LEFT')[1])
        ticks(e, S, 25); press(e, S, 'F2'); check('F2 (-): a minute less', e.mem(S['REM_MIN'], 1)[0] == m0)
        ticks(e, S, 25)
        hm = e.mem(S['HITP_MAX'], 1)[0]; press(e, S, 'SHIFT', 'T'); check('Shift+T: a hit point more', e.mem(S['HITP_MAX'], 1)[0] == hm + 1 and e.mem(S['HITP_CURR'], 1)[0] == hm + 1)
        press(e, S, 'SHIFT', 'I'); ticks(e, S, 2); check('Shift+I: upside down', e.mem(S['UPSIDE'], 1)[0] == 0xFF); press(e, S, 'SHIFT', 'I'); ticks(e, S, 2)
        press(e, S, 'SHIFT', 'W'); check('Shift+W: the feather fall', e.mem(S['FEATHER'], 1)[0] != 0)
        room = e.mem(S['SHOWN_ROOM'], 1)[0]; links = e.mem(S['LEVEL'] + 1952 + (room - 1) * 4, 4)
        i = [j for j in range(4) if links[j]][0]; kname = 'HJUN'[i]
        press(e, S, kname); ticks(e, S, 2); r0 = e.mem(S['SHOWN_ROOM'], 1)[0]; press(e, S, 'CTRL', 'B'); ticks(e, S, 2)
        check('%s: that room on screen (%d), Ctrl+B back (%d)' % (kname, r0, e.mem(S['SHOWN_ROOM'], 1)[0]), r0 == links[i] != room == e.mem(S['SHOWN_ROOM'], 1)[0], (room, links.hex()))
        press(e, S, 'T'); check('T: the time as a text', word(e, S['TEXT_REM']) > 0)
        ticks(e, S, 25)
        press(e, S, 'SHIFT', 'B'); pm = e.vram_image().load()
        lit = sum(1 for y in range(192) for x in range(0, 320, 3) if pm[x, y])
        check('Shift+B: the playfield black', lit == 0, lit)
        ticks(e, S, 3); pm = e.vram_image().load()
        check('   and it stays', not sum(1 for y in range(192) for x in range(0, 320, 3) if pm[x, y]))
        press(e, S, 'SHIFT', 'B'); ticks(e, S, 3); pm = e.vram_image().load()
        check('   Shift+B again: the room', sum(1 for y in range(192) for x in range(0, 320, 3) if pm[x, y]) > 100)
    sp = os.path.join(ROOT, 'tests', 'm7_scripts', 'death_music.txt')
    moves, patches = kidsim.read_script(sp)
    with Emu() as e:
        S = setup(e, 7, opts=GUARDS_OFF)
        run_script_game(e, S, moves + [(0, 0, 0)] * 2)
        e.call('bp_clear'); e.call('bp_add', addr=S['level_ready']); e.run(1000); e.call('bp_clear')
        for (rm, p, t, m) in patches:
            e.call('mem_write', addr=S['LEVEL'] + (rm - 1) * 30 + p, data_hex='%02x' % t)
            e.call('mem_write', addr=S['LEVEL'] + 720 + (rm - 1) * 30 + p, data_hex='%02x' % m)
        n = 0
        while e.mem(S['K_ALIVE'], 1)[0] > 100 or e.mem(S['K_ALIVE'], 1)[0] < 3: ticks(e, S, 1); n += 1; assert n < 300
        e.call('mem_write', addr=SCRIPT_PTR, data_hex='0000')
        press(e, S, 'R'); ticks(e, S, 2)
        check('R: the dead kid lives, hit points full (no resurrect_time: docs/m7-design.md §18)', e.mem(S['K_ALIVE'], 1)[0] == 0xFF and e.mem(S['HITP_CURR'], 1)[0] == e.mem(S['HITP_MAX'], 1)[0] > 0, (e.mem(S['K_ALIVE'], 1)[0], e.mem(S['HITP_CURR'], 1)[0]))

def main():
    cheat_tree = 'kl_cheat' in syms(os.path.join(BUILD, 'ovl_keys.sym'))
    parts = sys.argv[1:] or (['cheats'] if cheat_tree else ['texts', 'sound', 'pause', 'levels', 'launched', 'release'])
    for p in parts: globals()['part_' + p]()
    print('m7_keys: %s' % ('all ok' if not FAILS else '%d FAILED: %s' % (len(FAILS), FAILS)))
    sys.exit(1 if FAILS else 0)

if __name__ == '__main__': main()
