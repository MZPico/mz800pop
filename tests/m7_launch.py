#!/usr/bin/env python3
"""M7 step 1: the launcher and the swaps between the game and PRES (src/boot/launch.inc, src/boot/boot.asm,
src/pres/pres.asm, the level-start overlay src/m4/ovl_level.asm). Every run boots a copy of build/pop800.dsk
(mz800emu writes a mounted image back on eject); RAM-disk pages 0-7 are filled with a pattern first.
  1. round trip: floppy boot -> PRES (title) -> game level 1, TICKS1 ticks; then the game hands over as at a level
     change (the stub load_level with A = 4, a level with a cutscene) -> launcher -> PRES (cutscene before 4) ->
     launcher -> game level 4 (M7 step 7: PRES plays the level 4 cutscene, src/pres/cut.asm, and starts the level when its
     music ends). Against a direct level-4 start (tests/m4_game.py setup, the real game's options, the
     time left the handoff carried): main RAM and the RAM disk at level_ready, then TICKS ticks: the kid (KV, without
     K_TICK: the harness starts it at 0), the level events (EV), main RAM, VRAM. The direct start gets the two guard
     globals the handoff carries (is_guard_notice, roomleave_result) poked at its level_ready. Not compared: the harness option
     ev_opts' time (the launched game takes the time from the handoff), the RAM-disk areas only the boot writes, the
     scratch the game ran level 1 in (the shadow room page 1 0x0000-0x7CFF at level_ready, the torch cache page 6
     0x0000-0x287F).
  2. level end: tests/m4_scripts/walk_level1.txt (guards off at the level start, as the m4 scripts) in the floppy-booted
     game and in the harness (the direct path, no launcher: load_level inside the exit tick T). M7 step 5: the level
     waits on its end music (41, 12.75 s): the floppy game in its release mode (hybrid, SND_MODE 1: the PSG player's
     live music decides when the level changes, the clock is charged what the ticks model still had), the direct path
     in the ticks mode (SND_MODE 2: 153 ticks after the music starts, the original's length); both without the level 1
     music crouch (NEED_L1M 0: the script assumes none). Checked: the launched game hands over in the first tick after
     the player's stream ended, and with exactly the time left of the direct path's level 2 (the charge); the floppy
     game goes through PRES (cutscene before level 2); its tick k after the swap is compared with the direct run's tick
     T + k (the script continues where the direct path was; both silent from then on): KV (without kidsim's tick
     counter K_TICK: the live wait has its own length), EV, 0x0B00-0x0BFF (the kid's sprite, the traps, TROBS, MOBS),
     the guard records and globals, G_SNAP and the level blueprint every tick, VRAM every 10 ticks. The time left (EV)
     must be equal: PRES does not count time (SDLPoP's rem_tick only runs in play_frame's show_time).
     2b. the same with the ticks model's end music 60 ticks longer in both runs (SND_LEFT poked where it starts): the
     live music now ends first and the level change charges the rest (ovl_level.asm end_charge); the time left must
     equal the direct path's again. (The real piece: the Z80 runs ~12.6 ticks a second while the kid is off the screen,
     faster than the original's 12, so the ticks model ends first and END_OVER stops the clock: case 2.)
  3. game over in the launched game: GAME_OVER 1 (time expired), 2 (the end), 3 (the death text ran out) reach PRES
     with ACT_EXPIRED / ACT_ENDING / ACT_TITLE and come back as a new game (level 1, 60:719, 3 hit points: a key on
     PRES's title, M7 step 6); a restart
     (IS_RESTART) does not swap; without the launcher (the harness) GAME_OVER 3 still starts level 1 again.
M7 step 3: every game run is set to the silent sound mode at level_ready (psg.asm SND_MODE 0, as the harness): the
launched game is live (checked), and live decisions change only which sounds start, i.e. the timing.
Prints the transitions' times in frames (50 per second; the emulator's floppy has no rotation: a real drive is slower).
usage: m7_launch.py [ticks]"""
import os, shutil, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools')); sys.path.insert(0, os.path.join(ROOT, 'tests'))
TICKS = int(sys.argv[1]) if len(sys.argv) > 1 else 300
sys.argv = sys.argv[:1]                                     # (m5_boot reads its own argument)
from emu import Emu
from m3_test import syms, write_pack
from m4_game import setup, SCRIPT, SCRIPT_PTR, GUARDS_OFF
from m4_test import encode
import kidsim
import m5_boot as M5
BUILD = os.path.join(ROOT, 'build')
G = syms(os.path.join(BUILD, 'm4game.sym')); BS = syms(os.path.join(BUILD, 'boot.sym')); PS = syms(os.path.join(BUILD, 'pres.sym'))
REAL_GAME = M5.REAL_GAME
HO = BS['HO_MAIN']; KV = 0x0A00; EV = 0x0280; K_TICK = KV + 90; TICKS_VAR = 0x0872
FRAME = 312 * 228
SCRATCH = [(1, 0x0000, 32000, 'shadow room'), (6, 0x0000, 0x2880, 'torch cache')]
TORCH = SCRATCH[1:] + M5.PRES_LEFT[:4]  # (+ PRES's title screen in the shadow rows 192-199 the game never writes)
FAILS = []
LIVE = []          # SND_MODE at each level_ready reached (1 = the launched game's live sound; the harness: 0)

def check(what, ok, detail=''):
    print('  %-74s %s%s' % (what, 'ok' if ok else 'FAILED', '' if ok else '  ' + str(detail)))
    if not ok: FAILS.append(what)

def cyc(e): return e.call('get_raster_pos')['total_cycles']

def run_to(e, addrs, limit=6000):
    """run until PC is one of addrs; returns (PC, frames)"""
    addrs = [addrs] if isinstance(addrs, int) else addrs
    e.call('bp_clear')
    for a in addrs: e.call('bp_add', addr=a)
    c0 = cyc(e); n = 0
    while True:
        r = e.run(1000); n += r['actual_frames']
        if r['stopped_by'] == 'breakpoint': break
        assert n < limit, 'PC %04X never reached %s' % (e.call('get_registers')['PC'], ['%04X' % a for a in addrs])
    e.call('bp_clear')
    pc = e.call('get_registers')['PC']
    if pc == G['level_ready']:                  # M7 step 3: the game silent, as the harness (see the module doc)
        LIVE.append(e.mem(G['SND_MODE'], 1)[0]); e.call('mem_write', addr=G['SND_MODE'], data_hex='00')
    return pc, (cyc(e) - c0) / FRAME

def tick(e):
    pc, _ = run_to(e, G['tick_done'], 1000)

def call_at_tick_done(e, addr, a=None):
    """from the tick_done breakpoint: call addr (A = a), returning to tick_done"""
    reg = e.call('get_registers'); sp = (reg['SP'] - 2) & 0xFFFF
    e.call('mem_write', addr=sp, data_hex='%02x%02x' % (G['tick_done'] & 255, G['tick_done'] >> 8))
    e.call('set_register', reg='SP', value=sp); e.call('set_register', reg='PC', value=addr)
    if a is not None: e.call('set_register', reg='AF', value=(a << 8) | (reg['AF'] & 255))

def boot_to_game(e, dsk, times=None):
    """reset with the disk: boot -> launcher -> PRES (title) -> game start; returns the frames of each part"""
    M5.fill_ramdisk(e)
    e.call('media_insert', slot='fdc0_fd0', path=dsk, ro=True)
    e.call('reset')
    t = {}
    _, t['boot'] = run_to(e, BS['launch_main'])
    _, t['launcher -> PRES'] = run_to(e, PS['pres'])
    t['PRES title (to its step a, a key)'] = M5.title_start(e)
    _, t['PRES -> game start'] = run_to(e, G['start'])
    if times is not None: times.update(t)
    return t

def snap(e, masks_rd=(), masks_main=()):
    s = M5.snapshot(e)
    s['rd'] = M5.ramdisk(e, list(M5.RESERVED) + list(masks_rd))
    main = [bytearray(m) for m in s['main']]
    for a, n in masks_main:
        for (lo, hi), m in zip(M5.MAIN, main):
            if lo <= a < hi: m[a - lo:a - lo + n] = bytes(n)
    s['main'] = [bytes(m) for m in main]
    return s

def kv(e):
    b = bytearray(e.mem(KV, 256)); b[90:92] = b'\0\0'           # (K_TICK)
    return bytes(b)

def round_trip(dsk, times):
    print('1. round trip: game level 1 -> PRES (cutscene before level 4) -> game level 4, against a direct level-4 start')
    TICKS1 = 50
    with Emu() as e:
        boot_to_game(e, dsk)
        run_to(e, G['level_ready'])
        for _ in range(TICKS1): tick(e)
        rem = e.mem(EV + 1, 3); rem_min, rem_tick = rem[0], rem[1] | rem[2] << 8
        call_at_tick_done(e, G['load_level'], 4)
        _, f_swap = run_to(e, BS['launch_main'])
        _, f_pres = run_to(e, PS['pres'])
        ho = e.mem(HO, 16)
        check('PRES gets ACT_CUTSCENE, level 4, the time %d:%d, 3 hit points' % (rem_min, rem_tick),
              ho[2] == BS['ACT_CUTSCENE'] and ho[3] == 4 and ho[4] == rem_min and ho[5] | ho[6] << 8 == rem_tick and ho[7] == 3,
              ho.hex())
        _, f_stub = run_to(e, PS['p_go'])
        _, f_back = run_to(e, G['start'])
        _, f_ready = run_to(e, G['level_ready'])
        times.update({'game -> launcher (overlay: handoff, launcher copy)': f_swap, 'launcher -> PRES (floppy: PRES + scene)': f_pres,
                      'PRES: the cutscene before level 4 (loading, scene, music)': f_stub, 'launcher -> game start (image from the RAM disk)': f_back,
                      'game start -> level_ready': f_ready})
        mm = [(G['ev_opts'] + 3, 3)]
        f1 = snap(e, SCRATCH, mm); lv = e.mem(G['level_number'], 1)[0]
        check('the game is on level 4', lv == 4, lv)
        M5.ticks(e, TICKS)
        f2 = snap(e, TORCH, mm); f2['kv'] = kv(e); f2['ev'] = e.mem(EV, 31); f2['vram'] = e.vram_planes()
    with Emu() as e:
        M5.fill_ramdisk(e)
        setup(e, 4, opts=dict(REAL_GAME, time=(rem_min, rem_tick)))
        run_to(e, G['level_ready'])
        for k, sym in ((BS['HO_NOTICE'], 'IS_GUARD_NOTICE'), (BS['HO_ROOMLEAVE'], 'ROOMLEAVE')):   # (the globals a level
            e.call('mem_write', addr=G[sym], data_hex='%02x' % ho[k])                             # change keeps)
        h1 = snap(e, SCRATCH, mm)
        M5.ticks(e, TICKS)
        h2 = snap(e, TORCH, mm); h2['kv'] = kv(e); h2['ev'] = e.mem(EV, 31); h2['vram'] = e.vram_planes()
    check('at level_ready: main RAM and the RAM disk as a direct start', M5.compare('   level 4 at level_ready', h1, f1) == 0)
    check('after %d ticks: main RAM and the RAM disk' % TICKS, M5.compare('   level 4 after %d ticks' % TICKS, h2, f2) == 0)
    check('after %d ticks: KV, EV, VRAM' % TICKS, h2['kv'] == f2['kv'] and h2['ev'] == f2['ev'] and h2['vram'] == f2['vram'],
          (h2['kv'] == f2['kv'], h2['ev'] == f2['ev'], h2['vram'] == f2['vram']))

GV = None
def logic_state(e):
    """the logic state; drawing-only bytes normalised: the pending chunk list (KV 0xD0-0xE1, empty between ticks but
    stale), the bottom-text generation counters (EV 25 TEXT_GEN, 28 TXT_GEN_SHOWN: only whether the text on screen is
    the current one, TXT_GEN_SHOWN == ~TEXT_GEN, matters), TROBS / MOBS entries beyond their counts"""
    gv0, gv1 = G['gv_start'], G['gv_end']
    k = bytearray(e.mem(KV, 256)); k[0xD0:0xE2] = bytes(18); k[90:92] = b'\0\0'      # (K_TICK)
    ev = bytearray(e.mem(EV, 31)); ev[25] = int(ev[28] == ev[25] ^ 255); ev[28] = 0
    ov = bytearray(e.mem(0x0B00, 256)); tn, mn = ov[0x30 + 11], ov[0x30 + 12]
    ov[0x50 + 3 * tn:0x50 + 90] = bytes(90 - 3 * tn); ov[0xAA + 6 * mn:0xAA + 84] = bytes(84 - 6 * mn)
    return {'KV': bytes(k), 'EV': bytes(ev), 'OV 0B00': bytes(ov), 'guard': e.mem(gv0, gv1 - gv0),
            'G_SNAP': e.mem(G['G_SNAP'], 30), 'level': e.mem(G['LEVEL'], 2305), 'level_number': e.mem(G['level_number'], 1)}

def level_end(dsk, times, n_after=100, extra=0):
    """extra: ticks added to the ticks model's length of the end music in both runs (poked into SND_LEFT where it
    starts), so that the live music ends first and the level change charges the rest (end_charge)"""
    print('2%s. level end: walk_level1 (live end music in the launched game, ticks in the direct path) through PRES '
          '(cutscene before level 2) against the direct path%s' % ('b' if extra else '', '; the ticks model %d ticks longer' % extra if extra else ''))
    sp = os.path.join(ROOT, 'tests', 'm4_scripts', 'walk_level1.txt')
    moves, patches = kidsim.read_script(sp); keys = kidsim.read_keys(sp)
    assert not patches
    # (padded with idle ticks: the wait for the end music outlasts the script, and game.asm's get_controls decodes the
    # script's end byte 0xff as a control byte, Ctrl+A included: a restart)
    moves = moves + [(0, 0, 0)] * 400; keys = keys + [0] * 400
    script = encode(moves, keys)
    ref = {}
    with Emu() as e:                                    # the direct path (ticks mode)
        M5.fill_ramdisk(e)
        S = setup(e, 1, opts=GUARDS_OFF)
        write_pack(e, script, 5, SCRIPT)
        e.call('mem_write', addr=SCRIPT_PTR, data_hex='%02x%02x' % (SCRIPT & 255, SCRIPT >> 8))
        run_to(e, G['level_ready'])
        e.call('mem_write', addr=G['SND_MODE'], data_hex='02'); e.call('mem_write', addr=G['NEED_L1M'], data_hex='00')
        T = None; t = 0; t_music = None
        while True:
            tick(e); t += 1
            if t_music is None and e.mem(G['SND_CUR'], 1)[0] == 41 and e.mem(G['SND_LEFT'], 1)[0]:
                t_music = t
                if extra: e.call('mem_write', addr=G['SND_LEFT'], data_hex='%02x' % (e.mem(G['SND_LEFT'], 1)[0] + extra))
            if T is None and e.mem(G['level_number'], 1)[0] == 2:
                T = t; sptr_d = e.mem(SCRIPT_PTR, 2)
                e.call('mem_write', addr=G['SND_MODE'], data_hex='00')     # (level 2: silent, as the launched game)
            if T is not None:
                k = t - T
                ref[k] = logic_state(e)
                if k % 10 == 0 or k == n_after: ref[k]['vram'] = e.vram_planes()
                if k == n_after: break
            assert t < 700, 'the direct path never reached level 2'
    ev_d = ref[0]['EV']
    print('   direct path (ticks): music 41 started in tick %d, level 2 loaded in tick %d (%d ticks later), time left %d:%d' % (
        t_music, T, T - t_music, ev_d[1], ev_d[2] | ev_d[3] << 8))
    check('the direct path waits the end music\'s %d ticks (12.75 s x 12/s%s)' % (153 + extra, ' + %d' % extra if extra else ''),
          T - t_music == 153 + extra, T - t_music)
    with Emu() as e:                                    # through PRES (hybrid: the live music)
        boot_to_game(e, dsk)
        e.call('mem_write', addr=G['guard_opts'], data_hex='01')       # (guards off at the level start, as setup)
        write_pack(e, script, 5, SCRIPT)
        e.call('mem_write', addr=SCRIPT_PTR, data_hex='%02x%02x' % (SCRIPT & 255, SCRIPT >> 8))
        run_to(e, G['level_ready'])
        e.call('mem_write', addr=G['SND_MODE'], data_hex='01'); e.call('mem_write', addr=G['NEED_L1M'], data_hex='00')
        t = 0; t_music = None; f_music = None; last = None; over = None; c0 = cyc(e)
        while True:
            pc, _ = run_to(e, [G['tick_done'], BS['LN_LAUNCH']], 1000)
            if pc == BS['LN_LAUNCH']: break
            t += 1
            m = e.mem(G['SND_CUR'], 1)[0]; left = e.mem(G['SND_LEFT'], 1)[0]; wait = e.mem(G['SP_WAIT'], 1)[0]
            if t_music is None and m == 41 and left:
                t_music = t; f_music = (cyc(e) - c0) / FRAME
                if extra: left += extra; e.call('mem_write', addr=G['SND_LEFT'], data_hex='%02x' % left)
            if t_music is not None: last = (left, wait, (cyc(e) - c0) / FRAME)
            if over is None and e.mem(G['END_OVER'], 1)[0]: over = t
            assert t < 700, 'the launched game never left level 1'
        f_end = (cyc(e) - c0) / FRAME
        charge = max(last[0] - 1, 0); wait_end = e.mem(G['SP_WAIT'], 1)[0]
        print('   launched (hybrid): music 41 started in tick %d, the handover in tick %d (%d ticks, %.0f frames = %.2f s later); '
              'charged at the change: %d ticks%s' % (t_music, t + 1, t + 1 - t_music, f_end - f_music, (f_end - f_music) / 50,
              charge, '' if over is None else '; END_OVER (the clock stopped) from tick %d' % over))
        check('the launched game waits for the live music: it hands over in the first tick after the player\'s stream ended',
              last[1] != 0 and wait_end == 0, (last, wait_end))
        sptr = e.mem(SCRIPT_PTR, 2); lvl_ev = e.mem(EV, 31)
        check('   the live wait lasts the music (12.75 s, within a tick of ~0.15 s)', abs((f_end - f_music) / 50 - 12.75) < 0.4,
              (f_end - f_music) / 50)
        check('   the clock charge: the time left at the handover equals the direct (ticks) path\'s at level 2 (%d:%d)' % (
            ev_d[1], ev_d[2] | ev_d[3] << 8), lvl_ev[1:4] == ev_d[1:4], (lvl_ev[1], lvl_ev[2] | lvl_ev[3] << 8))
        _, f_pres = run_to(e, PS['pres'])
        ho = e.mem(HO, 16)
        check('PRES gets ACT_CUTSCENE, level 2, the time and hit points of the game',
              ho[2] == BS['ACT_CUTSCENE'] and ho[3] == 2 and ho[4] == lvl_ev[1] and ho[5:7] == lvl_ev[2:4] and ho[7] == lvl_ev[17], ho.hex())
        r = e.run(30); e.screenshot(os.path.join(BUILD, 'm7_pres_cut2.png'))
        _, f_back = run_to(e, G['start']); f_back += r['actual_frames']
        e.call('mem_write', addr=SCRIPT_PTR, data_hex=sptr_d.hex())   # (the script goes on where the direct path is)
        _, f_ready = run_to(e, G['level_ready'])
        if extra:
            check('   the live music ended first: the level change charged the ticks model\'s rest', charge > 0 and over is None, (charge, over))
            times['level end (ticks model +%d): the live music wait' % extra] = f_end - f_music
            return
        times.update({'level end: the live music wait (music start -> PRES)': f_end - f_music, 'level end -> PRES': f_pres,
                      'PRES -> level 2 start (the cutscene included)': f_back, 'level 2 start -> level_ready': f_ready})
        bad = {}; first = None; firsts = {}
        for k in range(1, n_after + 1):
            tick(e)
            got = logic_state(e)
            for key, v in ref[k].items():
                if key == 'vram': continue
                if got[key] != v:
                    bad[key] = bad.get(key, 0) + 1
                    d = [i for i in range(len(v)) if v[i] != got[key][i]]
                    if key not in firsts: firsts[key] = (k, ['%d: %02X/%02X' % (i, v[i], got[key][i]) for i in d[:8]])
                    if first is None: first = (k, key)
            if 'vram' in ref[k]:
                if e.vram_planes() != ref[k]['vram']:
                    bad['vram'] = bad.get('vram', 0) + 1
                    if first is None: first = (k, 'vram')
        e.screenshot(os.path.join(BUILD, 'm7_level2.png'))
    check('level 2, %d ticks: the logic state every tick, VRAM every 10 ticks as the direct path' % n_after, not bad, (bad, first))
    for key, (k, d) in firsts.items(): print('     %s first differs at tick %d (offset: direct/launched): %s' % (key, k, ', '.join(d)))

def game_over(dsk, times):
    print('3. game over and restart in the launched game; game over without the launcher')
    with Emu() as e:
        boot_to_game(e, dsk)
        run_to(e, G['level_ready'])
        for _ in range(20): tick(e)
        for go, act, name in ((1, BS['ACT_EXPIRED'], 'time expired'), (2, BS['ACT_ENDING'], 'the end'), (3, BS['ACT_TITLE'], 'the death text ran out')):
            e.call('mem_write', addr=EV + 1, data_hex='05')              # (some other time, to see the new game's)
            e.call('mem_write', addr=EV + 23, data_hex='%02x' % go)       # GAME_OVER
            _, f0 = run_to(e, PS['pres'])
            ho = e.mem(HO, 16)
            check('GAME_OVER %d (%s): PRES gets action %02X' % (go, name, act), ho[2] == act, ho.hex())
            if go < 3: run_to(e, PS['title'], 16000)                      # (time_expired, the ending: no key ends them; tests/m7_story.py)
            f1 = M5.title_start(e)                                        # (the title: a key)
            _, f1b = run_to(e, G['start']); f1 += f1b
            _, f2 = run_to(e, G['level_ready'])
            ev = e.mem(EV, 31); lv = e.mem(G['level_number'], 1)[0]
            check('   then a new game: level 1, 60:719, 3 hit points', lv == 1 and ev[1] == 60 and ev[2] | ev[3] << 8 == 719 and ev[17] == 3,
                  (lv, ev[1], ev[2] | ev[3] << 8, ev[17]))
            times['game over %d: -> PRES / PRES (%s) -> game start' % (go, 'the title after the scene' if go < 3 else 'title')] = '%.1f / %.1f' % (f0, f1)
            for _ in range(5): tick(e)
        e.call('mem_write', addr=EV + 21, data_hex='01')                 # IS_RESTART (Ctrl+A)
        e.call('bp_clear'); e.call('bp_add', addr=G['tick_done']); e.call('bp_add', addr=BS['LN_LAUNCH'])
        r = e.run(1000); pc = e.call('get_registers')['PC']; e.call('bp_clear')
        check('a restart in the launched game does not swap', r['stopped_by'] == 'breakpoint' and pc == G['tick_done'], '%04X' % pc)
    with Emu() as e:
        M5.fill_ramdisk(e)
        setup(e, 2, opts=REAL_GAME)
        run_to(e, G['level_ready'])
        for _ in range(5): tick(e)
        e.call('mem_write', addr=EV + 23, data_hex='03')
        e.call('bp_clear'); e.call('bp_add', addr=G['tick_done']); e.call('bp_add', addr=BS['LN_LAUNCH'])
        r = e.run(1000); pc = e.call('get_registers')['PC']; e.call('bp_clear')
        lv = e.mem(G['level_number'], 1)[0]
        check('the harness (no launcher): GAME_OVER 3 starts level 1 again', pc == G['tick_done'] and lv == 1, ('%04X' % pc, lv))

def main():
    tmp = tempfile.mkdtemp(prefix='m7launch')
    times = {}
    try:
        dsk = os.path.join(tmp, 'pop800.dsk'); shutil.copy(M5.DSK, dsk)
        with Emu() as e:
            print('0. boot -> PRES -> game (tests/m5_boot.py compares this path with the harness)')
            boot_to_game(e, dsk, times)
            ho = e.mem(HO, 16); lv = e.mem(G['level_number'], 1)[0]
            check('the game starts from the launcher: handoff ACT_PLAY level 1 at HO_MAIN', ho[:4] == bytes([0x50, 0x37, 0, 1]), ho.hex())
            _, times['game start -> level_ready (level 1)'] = run_to(e, G['level_ready'])
            check('the launched game\'s sound is live (psg.asm SND_MODE 1; then silent for the comparisons)', LIVE[-1:] == [1], LIVE)
        if os.environ.get('M7_ONLY') != 'level_end': round_trip(dsk, times)
        level_end(dsk, times)
        level_end(dsk, times, n_after=1, extra=60)
        if os.environ.get('M7_ONLY') == 'level_end': return
        game_over(dsk, times)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print('times (frames, 50 per second):')
    for k, v in times.items():
        print('  %-58s %s' % (k, ('%.1f' % v) if isinstance(v, float) else v))
    print('M7 launch test %s' % ('OK' if not FAILS else 'FAILED (%d)' % len(FAILS)))
    sys.exit(1 if FAILS else 0)

if __name__ == '__main__':
    main()
