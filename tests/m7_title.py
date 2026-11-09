#!/usr/bin/env python3
"""M7 step 6: the title in PRES (src/pres/pres.asm) against the Python reference render of TITLE.DAT (tools/titleref.py,
checked against DOSBox's EGA original, docs/m7-design.md §15). Every run boots a copy of build/pop800.dsk (mz800emu
writes a mounted image back on eject) with the RAM disk filled with a pattern (tests/m5_boot.py).
  1. the title's first steps (a-f, g and its fade-out; h-m: tests/m7_story.py): at the start of every step
     (ts_step) VRAM equals the reference screen of the step before, pixel for pixel, and the frame (FRAMES) is exactly
     the start frame + floor(5 T / 6), T = the step's SDLPoP tick (docs/m7-design.md §1.2; the exception, step f: SDLPoP's
     lasts until music 54 ends (the ticks model, kidsim SOUND_SECONDS), PRES's ends 60 ticks earlier, tools/titleref.py
     STEPS; after the fade-in the step's code runs once its last pass is drawn,
     up to 3 frames later, the clock exact); the fade-in's 5 passes (tf_pass: rows y mod 5 < k + 1 from the new screen),
     the fade-out's (tfo_pass) and the wipes' columns (tw_col: j and k, the columns COLS) against the reference too,
     at their ticks (t_target); the PSG state at every interrupt that plays a group equals tools/sndsim.py's player
     for the same events (the tracker of tests/m7_sound.py; the presentation's bank A build/assets/sound_pres.bin), music
     54 (the Master System title theme, looped: M7 step 11) starts with the fade-in's last pass and plays exactly twice:
     f stops it (snd_halt) between the interrupt that played its 2nd pass's last frame and the one that would start a
     3rd (titleref.music_stop_tick), silence until step g; music 55 of g fades out (psg.asm's fade, MFADE_FRAMES) to
     silence at the last pass of g's fade-out;
     build/sound/pres/title_a-g.wav is what the emulator played.
  2. keys: SPACE at step a starts level 1 (the handoff ACT_PLAY level 1, 60:719, 3 hit points; the launched game at
     level_ready and TICKS ticks later equals a direct level 1 start (tests/m4_game.py setup, the real game's options:
     main RAM, the RAM disk without PRES's scratch, KV, EV, VRAM; NEED_L1M set: the level 1 crouch music); SHIFT (the
     button) starts it too; CTRL alone does nothing.
  3. Ctrl+L with a saved game (made as tests/m5_save.py does: Ctrl+G on level 3, the disk written back): the game
     starts at the saved level with the saved time and hit points, as a direct start of that level with that time.
  4. Ctrl+L without a valid save (POP800.SAV empty): the title goes on (the next step comes, its screen right, no
     handover), and a key then still starts the game.
Prints the steps' frames (expected / measured) and the loading times.
usage: m7_title.py [--quick | --rest]   (--quick: part 1 only; --rest: parts 2-4 only)"""
import os, shutil, sys, tempfile, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools')); sys.path.insert(0, os.path.join(ROOT, 'tests'))
QUICK = '--quick' in sys.argv
REST = '--rest' in sys.argv
sys.argv = sys.argv[:1]
from emu import Emu
from m3_test import syms
from m4_game import setup
import m5_boot as M5
import m7_sound
import sndsim
import titleref as T
BUILD = os.path.join(ROOT, 'build')
G = syms(os.path.join(BUILD, 'm4game.sym')); BS = syms(os.path.join(BUILD, 'boot.sym')); PS = syms(os.path.join(BUILD, 'pres.sym'))
EV = 0x0280; KV = 0x0A00
REAL_GAME = M5.REAL_GAME
TICKS = 100
COLS = (0, 1, 2, 7, 19, 20, 33, 38, 39)
FAILS = []

def check(what, ok, detail=''):
    print('  %-86s %s%s' % (what, 'ok' if ok else 'FAILED', '' if ok else '  ' + str(detail)))
    if not ok: FAILS.append(what)

def frames(e):
    b = e.mem(0x0800, 2); return b[0] | (b[1] << 8)
def word(e, a):
    b = e.mem(a, 2); return b[0] | (b[1] << 8)
def screen(e): return T.from_planes(e.vram_planes())

def boot(e, dsk):
    M5.fill_ramdisk(e)
    e.call('media_insert', slot='fdc0_fd0', path=dsk, ro=True)
    e.call('reset')
    t = {'boot -> PRES (1 MB+: the frame store\'s fill included)': M5.to_pres(e)}
    t['PRES -> the title\'s clock (2 floppy loads, step a\'s screen decoded)'] = M5.run_to(e, PS['ts_sync'], 1000)
    return t

def timeline():
    """[(event, tick)] of the title from its clock's start: ('pass', k) fade-in passes, ('step', s), ('col', (s, c)),
    ('opass', k) fade-out passes"""
    out = []; t = 0
    loop = 0
    for k in range(5): out.append((('pass', loop, k), t + 4 * k))
    t += 16
    for s, names, ticks in T.STEPS:
        out.append((('step', loop, s), t))
        if s in T.WIPES:
            for c in range(40): out.append((('col', loop, s, c), t + 2 * c))
        t += ticks
    for k in range(5): out.append((('opass', loop, k), t + 4 * k))
    t += 20
    out.append((('step', loop, 'h'), t))
    return out

def title_run(dsk):
    print('1. the title: screens, timing, music (a-g)')
    bank = sndsim.load_bank(os.path.join(BUILD, 'assets', 'sound_pres.bin'), 0)
    TL = dict(timeline())
    names = dict((s, n) for s, n, _ in T.STEPS)
    prev_of = {'b': 'a', 'c': 'b', 'd': 'c', 'e': 'd', 'f': 'e', 'g': 'f'}
    black = T.blank()
    rows = []; bad_scr = []; bad_t = []; n_scr = 0
    with Emu() as e:
        times = boot(e, dsk)
        F0 = frames(e)
        tr = m7_sound.Tracker(e, PS, 'silent', bank)
        tr.addr = {PS['spi_done']: 'act', PS['snh_di']: 'halt', PS['snd_arm']: 'arm', PS['snd_start']: 'start', PS['sf_x']: 'fill', PS['mf_go']: 'fade'}
        mine = {PS['ts_step']: 'step', PS['tf_pass']: 'pass', PS['tw_col']: 'col', PS['tfo_pass']: 'opass'}
        e.call('bp_clear')
        tr.bps()                        # (tracepoints, or breakpoints without tracing: tests/m7_sound.py Tracker)
        for a in mine: e.call('bp_add', addr=a)
        loop = 0; seen = set(); arms = []; t0 = time.time()
        tr.hooks['arm'] = lambda f: arms.append((tr.cur[0], tr.cur[1] - F0))
        halts = []; tr.hooks['halt'] = lambda f: halts.append(f - F0)
        while True:
            r = e.run(1000)
            if r['stopped_by'] != 'breakpoint': tr.poll(); continue
            pc = e.call('get_registers')['PC']
            tr.event(pc)
            kind = mine.get(pc)
            if kind is None: continue
            f = frames(e) - F0; tgt = word(e, PS['t_target']) - F0
            if kind == 'step':
                s = chr(e.mem(PS['t_step'], 1)[0])
                key = ('step', loop, s)
                want_f = TL[key] * 5 // 6
                rows.append((loop, s, TL[key], want_f, tgt, f))
                # (the clock's target exactly; the step's code runs at that frame, except after the fade-in, whose
                # last pass (started at the target with the music) is drawn first: ~2 frames)
                if tgt != want_f or not (f == want_f or (s == 'a' and 0 < f - want_f <= 3) or (s == 'h' and -4 <= f - want_f <= 0)): bad_t.append((key, want_f, tgt, f))
                if s in prev_of:
                    ref = T.screen(names[prev_of[s]]); n_scr += 1
                    d = T.diff(screen(e), ref)
                    if d: bad_scr.append((key, 'end of ' + prev_of[s], len(d), d[:3]))
                seen.add(key)
                if s == 'h': break
                continue
            k = e.mem(PS['t_col'], 1)[0]
            if kind == 'pass':
                key = ('pass', loop, k); ref = T.fade_in(black, T.screen(['MAIN']), k + 1)
            elif kind == 'opass':
                key = ('opass', loop, k); ref = T.fade_in(T.screen(names['g']), black, k + 1)
            else:
                s = 'g'
                key = ('col', loop, s, k)
                if k not in COLS: continue
                ref = T.wipe(T.screen(names['f']), T.screen(names[s]), k + 1)
            want_t = TL[key] * 5 // 6
            if tgt != want_t or not 0 <= f - tgt <= 3: bad_t.append((key, want_t, tgt, f))
            d = T.diff(screen(e), ref); n_scr += 1
            if d: bad_scr.append((key, len(d), d[:3]))
        f1 = tr.finish()
    print('   %s' % ', '.join('%s %d frames' % kv for kv in times.items()))
    print('   step  tick   frame expected  clock  code at   (frames from the title\'s clock start; 5/6 frame a tick)')
    for loop, s, t, wf, tg, f in rows:
        print('   %s%-3s %6d %10d %6d %8d %s' % (s, "'" if loop else ' ', t, wf, tg, f, '' if wf == tg else '  DIFFERS'))
    durs = {}
    for (l0, s0, t0_, _, f0_, _), (l1, s1, t1_, _, f1_, _) in zip(rows, rows[1:]):
        if l0 == 0: durs[s0] = (t1_ - t0_, f1_ - f0_)
    print('   durations (ticks -> frames): %s' % ', '.join('%s %d -> %d' % (s, t, f) for s, (t, f) in durs.items()))
    check('every step starts at its frame: start + floor(5 T / 6) (%d steps; f: %d ticks, SDLPoP\'s - %d)' % (
          len(rows), dict((s, t) for s, _, t in T.STEPS)['f'], T.F_EARLIER),
          not bad_t, bad_t[:5])
    check('VRAM pixel-exact against tools/titleref.py at every step, fade pass and wipe column checked (%d screens)' % n_scr,
          not bad_scr, bad_scr[:4])
    want_arm = [(54, 16 * 5 // 6), (55, TL[('step', 0, 'g')] * 5 // 6)]
    check('music 54 starts with the fade-in\'s last pass, music 55 with step g (frames %s)' % [a for _, a in want_arm], arms == want_arm, arms)
    j0 = TL[('step', 0, 'g')] * 5 // 6
    n = T.title_frames(); stop = T.music_stop_tick() * 5 // 6     # (the title theme, looped whole)
    want_stop = arms[0][1] + T.TITLE_PASSES * n if arms else None
    check('music 54 (the title theme, %d frames) plays %d times: f stops it at frame %s = its start + %d (the pass '
          'boundary), %d frames before g' % (n, T.TITLE_PASSES, want_stop, T.TITLE_PASSES * n, j0 - stop),
          want_stop == stop and stop in halts and not [h for h in halts if want_stop < h < j0]
          and tr.wraps.get(54) == T.TITLE_PASSES and 54 not in dict(tr.lengths), (halts, tr.wraps, tr.lengths))
    fo = TL[('opass', 0, 4)]                         # (g's fade-out's last pass: the text gone)
    want = [(55, (fo - sndsim.MFADE_TICKS) * 5 // 6, fo * 5 // 6)]
    got = [(sid, a - F0, b - F0) for a, (sid, b) in zip(tr.fades, tr.faded)]
    check('music 55 fades out over %d frames from frame %d: silent (stopped) at g\'s fade-out\'s last pass, frame %d (got %s)' % (
          sndsim.MFADE_FRAMES, want[0][1], want[0][2], got), got == want and len(tr.fades) == 1, (got, tr.fades))
    check('the PSG state at every interrupt that played a group equals sndsim\'s (%d samples, %.0f s)' % (tr.samples, time.time() - t0),
          tr.bad == 0 and tr.samples > 1000, tr.first)
    w = os.path.join(BUILD, 'sound', 'pres', 'title_a-g.wav')
    sndsim.write_wav(w, sndsim.render(tr.per_frame(f1))); print('   wrote %s (the title a-g as the emulator played it)' % w)

def snap_game(e, scratch_screen=True):
    return M5.snapshot(e, M5.RESERVED + (M5.PRES_SCRATCH if scratch_screen else M5.PRES_LEFT))

def direct(level, time_left):
    """a direct start of the level (the harness), the real game's options and the time left: snapshots at
    level_ready and TICKS ticks later"""
    with Emu() as e:
        M5.fill_ramdisk(e)
        setup(e, level, opts=dict(REAL_GAME, time=time_left))
        M5.run_to(e, G['level_ready'])
        h1 = snap_game(e); h1['need_l1m'] = e.mem(G['NEED_L1M'], 1)[0]
        M5.ticks(e, TICKS)
        h2 = snap_game(e, False); h2['kv'] = e.mem(KV, 256); h2['ev'] = e.mem(EV, 31); h2['vram'] = e.vram_planes()
    return h1, h2

def launched(e):
    """the launched game from its start: level_ready (silent from there, as the harness) and TICKS ticks"""
    M5.run_to(e, G['level_ready'])
    mode = e.mem(G['SND_MODE'], 1)[0]
    e.call('mem_write', addr=G['SND_MODE'], data_hex='00')
    f1 = snap_game(e); f1['need_l1m'] = e.mem(G['NEED_L1M'], 1)[0]; f1['mode'] = mode
    M5.ticks(e, TICKS)
    f2 = snap_game(e, False); f2['kv'] = e.mem(KV, 256); f2['ev'] = e.mem(EV, 31); f2['vram'] = e.vram_planes()
    return f1, f2

def masked(s, ranges):
    """the snapshot with main-RAM ranges [(address, length)] zeroed (the harness option block's time)"""
    main = [bytearray(m) for m in s['main']]
    for a, n in ranges:
        for (lo, hi), m in zip(M5.MAIN, main):
            if lo <= a < hi: m[a - lo:a - lo + n] = bytes(n)
    return dict(s, main=[bytes(m) for m in main])

def compare_game(what, h, f):
    mm = [(G['ev_opts'] + 3, 3)]
    h1, h2 = h; f1, f2 = f
    check('%s: at level_ready main RAM and the RAM disk as a direct start' % what,
          M5.compare('   %s at level_ready' % what, masked(h1, mm), masked(f1, mm)) == 0)
    check('%s: %d ticks later main RAM, the RAM disk, KV, EV, VRAM' % (what, TICKS),
          M5.compare('   %s after %d ticks' % (what, TICKS), masked(h2, mm), masked(f2, mm)) == 0 and
          h2['kv'] == f2['kv'] and h2['ev'] == f2['ev'] and h2['vram'] == f2['vram'],
          (h2['kv'] == f2['kv'], h2['ev'] == f2['ev'], h2['vram'] == f2['vram']))

def to_step(e, s):
    """run to the start of step s (ts_step with t_step = s)"""
    while True:
        M5.run_to(e, PS['ts_step'], 3000)
        if chr(e.mem(PS['t_step'], 1)[0]) == s: return

def keys_run(dsk):
    print('2. keys: SPACE starts level 1 as a direct start; SHIFT starts it; CTRL alone does nothing')
    with Emu() as e:
        boot(e, dsk)
        M5.title_start(e, 'SPACE')
        ho = e.mem(PS['ho'], 16)
        check('SPACE at step a: the handoff ACT_PLAY level 1, 60:719, 3 hit points, the rest 0',
              ho[2:8] == bytes([0, 1, 60, 719 & 255, 719 >> 8, 3]) and ho[9:] == bytes(7), ho.hex())
        f = launched(e)
    h = direct(1, (60, 719))
    check('the launched game: sound live (SND_MODE 1), NEED_L1M 1 (the level 1 crouch music) as the direct start',
          f[0]['mode'] == 1 and f[0]['need_l1m'] == 1 == h[0]['need_l1m'], (f[0]['mode'], f[0]['need_l1m'], h[0]['need_l1m']))
    compare_game('level 1 from the title', h, f)
    with Emu() as e:
        boot(e, dsk)
        to_step(e, 'b')
        e.call('input_press_key', key='CTRL')
        e.call('bp_clear'); e.call('bp_add', addr=PS['p_go']); e.call('bp_add', addr=PS['ts_step'])
        r = e.run(1000); pc = e.call('get_registers')['PC']; s = chr(e.mem(PS['t_step'], 1)[0])
        e.call('input_release_key', key='CTRL')
        check('CTRL held through step b: no handover, step c comes', pc == PS['ts_step'] and s == 'c', ('%04X' % pc, s))
        to_step(e, 'd')
        M5.title_start(e, 'SHIFT')
        ho = e.mem(PS['ho'], 16)
        check('SHIFT (the button) at step e: the handoff ACT_PLAY level 1', ho[2:4] == bytes([0, 1]), ho.hex())

def make_save(tmp):
    """a disk with a saved game: level 3, Ctrl+G, as tests/m5_save.py does; returns (disk, the saved state)"""
    import m5_save
    dsk = os.path.join(tmp, 'save.dsk'); shutil.copy(M5.DSK, dsk)
    with Emu() as e:
        S = m5_save.boot_level(e, 3, dsk, ro=False)
        e.call('mem_write', addr=EV + 1, data_hex='29')              # (some time left other than a fresh level's)
        e.call('mem_write', addr=EV + 2, data_hex='2301')
        m5_save.ticks(e, S, 1)
        st = m5_save.state(e, S)
        m5_save.key(e, 'CTRL', 'G'); m5_save.ticks(e, S, 1); m5_save.key(e, 'CTRL', 'G', down=False)
        m5_save.ticks(e, S, 2)
        e.call('media_eject', slot='fdc0_fd0')
    rec = m5_save.sav_file(dsk)[:14]
    check('the saved game on the disk: %s (level %d, %d:%d, %d hit points)' % (rec.hex(), st['level'], st['rem_min'],
          st['rem_tick'], st['hitp']), rec == m5_save.record(st), rec.hex())
    return dsk, st

def ctrl_l(e, upto=('p_go', 'ts_step')):
    """Ctrl+L held until PRES hands over or the next step starts; returns (PC, whether load_saved ran)"""
    e.call('input_press_key', key='CTRL'); e.call('input_press_key', key='L')
    e.call('bp_clear'); e.call('bp_add', addr=PS['tk_load'])
    r = e.run(100); loaded = r['stopped_by'] == 'breakpoint'
    e.call('bp_clear')
    for u in upto: e.call('bp_add', addr=PS[u])
    r = e.run(1000); pc = e.call('get_registers')['PC']
    e.call('input_release_key', key='L'); e.call('input_release_key', key='CTRL'); e.call('bp_clear')
    return pc, loaded

def ctrl_l_run(tmp):
    print('3. Ctrl+L with a saved game: the game at the saved level, as a direct start with the saved time')
    dsk, st = make_save(tmp)
    with Emu() as e:
        boot(e, dsk)
        to_step(e, 'b')
        pc, loaded = ctrl_l(e)
        ho = e.mem(PS['ho'], 16)
        check('Ctrl+L at step b: load_saved, the handoff ACT_PLAY level %d, %d:%d, %d hit points' % (
              st['level'], st['rem_min'], st['rem_tick'], st['hitp']), loaded and pc == PS['p_go'] and
              ho[2:8] == bytes([0, st['level'], st['rem_min'], st['rem_tick'] & 255, st['rem_tick'] >> 8, st['hitp']]) and
              ho[9:] == bytes(7), ('%04X' % pc, loaded, ho.hex()))
        M5.run_to(e, G['start'], 1000)
        f = launched(e)
        lv = e.mem(G['level_number'], 1)[0]
    h = direct(st['level'], (st['rem_min'], st['rem_tick']))
    check('the launched game is on level %d' % st['level'], lv == st['level'], lv)
    compare_game('the saved level from the title', h, f)
    print('4. Ctrl+L without a valid save: the title goes on')
    dsk0 = os.path.join(tmp, 'nosave.dsk'); shutil.copy(M5.DSK, dsk0)
    with Emu() as e:
        boot(e, dsk0)
        to_step(e, 'b')
        F0 = frames(e)
        pc, loaded = ctrl_l(e)
        s = chr(e.mem(PS['t_step'], 1)[0])
        check('Ctrl+L at step b, POP800.SAV empty: load_saved ran, no handover, step c comes', loaded and pc == PS['ts_step'] and s == 'c',
              ('%04X' % pc, loaded, s))
        d = T.diff(screen(e), T.screen(['MAIN', 'PRESENTS']))
        playing = e.mem(PS['SP_WAIT'], 1)[0]
        check('   VRAM at step c = the end of step b; the music goes on (the player\'s stream runs)', not d and playing, (len(d), playing))
        M5.title_start(e, 'SPACE')
        ho = e.mem(PS['ho'], 16)
        check('   then SPACE starts level 1', ho[2:4] == bytes([0, 1]), ho.hex())

def main():
    tmp = tempfile.mkdtemp(prefix='m7title')
    try:
        dsk = os.path.join(tmp, 'pop800.dsk'); shutil.copy(M5.DSK, dsk)
        if not REST: title_run(dsk)
        if not QUICK:
            keys_run(dsk)
            ctrl_l_run(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print('M7 title test %s' % ('OK' if not FAILS else 'FAILED (%d)' % len(FAILS)))
    sys.exit(1 if FAILS else 0)

if __name__ == '__main__':
    main()
