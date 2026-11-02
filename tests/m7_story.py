#!/usr/bin/env python3
"""M7 step 8: the intro story, time_expired and the ending in PRES (src/pres/pres.asm, cut.asm) against tools/cutsim.py and
tools/titleref.py (both checked against SDLPoP and DOSBox: tools/cut_suite.py, docs/m7-design.md §17). Every run boots a
copy of build/pop800.dsk, so POP800.PR2 is really read from the disk (the entries behind POP800.PRS's 255 blocks).
  1. the title's h-m (tests/m7_title.py: a-g): pv_scene (C lines, VRAM after every drawn frame, the fades, the clock
     floor(5 T / 6), flash palette writes, the PZ sprites), i's fade-in and screen, the wait for music 52, j's and k's
     wipes, the fade-out, the title again; the PSG against sndsim all the way;
  2. ACT_EXPIRED: time_expired (102 + 2 fade frames; the same checks), keys ignored, then the title;
  3. ACT_ENDING: end_sequence_anim (keys ignored), the hail screen, TITLE_MAIN until the ticks model's music 56 ends (a key
     ends the hail wait and the wait on TITLE_MAIN: do_wait; not the wait for the music), then the title; the Master
     System title theme loops under it all (M7 step 11: 3 plays = 2052 ticks from the embrace's start);
  WAVs of what the emulator played: build/sound/pres/title_h-i.wav, title_j-m.wav, time_expired.wav, ending.wav.
  4. keys: a key during g, in pv_scene, at i and j, k: level 1 as a direct start; Ctrl+L in pv_scene with an empty save:
     the title starts again;
  5. forced lateness: some frames' starts pushed late: frames are skipped, the C lines stay exact, every drawn frame VRAM-exact;
  6. the flow in the real game: a time-out (the clock poked near its end) -> time_expired -> the title; level 14's end
     (the kid walks there) -> the ending -> the title; a new game from that title equals a direct level 1 start.
usage: m7_story.py [title] [expired] [ending] [endkeys] [keys] [late] [flow]   (default: all)"""
import os, shutil, sys, tempfile, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools')); sys.path.insert(0, os.path.join(ROOT, 'tests'))
ARGS = sys.argv[1:]
sys.argv = sys.argv[:1]
from emu import Emu
import m5_boot as M5
import m7_cut as C
import m7_title as MT
from m4_game import encode, write_pack, SCRIPT, SCRIPT_PTR
import cutsim
import titleref as T
PS = C.PS; BS = C.BS; G = C.G; HO = C.HO; EV = C.EV
check = C.check
FAILS = C.FAILS
BLACK = [bytes(8000)] * 4
WIPE = 80

def word(e, a): return C.word(e, a)
def go(e, limit=30000):
    """run until a breakpoint (at most limit frames)"""
    while limit > 0:
        if e.run(min(limit, 1000))['stopped_by'] == 'breakpoint': return True
        limit -= 1000
    return False
def scr(e): return T.from_planes(e.vram_planes())

def title_ticks():
    """the title's tick of g's start (f ends with music 54), of h (g's wipe + wait + fade-out)"""
    tg = 16 + T.music_end_ticks()
    return tg, tg + 80 + 600 + 20

def run_step(e, tr, want, limit=30000):
    """run with the tracker until ts_step with t_step = want"""
    e.call('bp_clear')
    tr.bps()
    e.call('bp_add', addr=PS['ts_step'])
    while True:
        if not go(e, limit): raise RuntimeError('no step %s' % want)
        pc = e.call('get_registers')['PC']
        tr.event(pc)
        if pc == PS['ts_step'] and chr(e.mem(PS['t_step'], 1)[0]) == want: return

def run_to_sync(e, dsk):
    M5.fill_ramdisk(e)
    e.call('media_insert', slot='fdc0_fd0', path=dsk, ro=True)
    e.call('reset')
    M5.run_to(e, PS['pres'], 3000)
    tr = C.tracker(e)
    e.call('bp_clear')
    tr.bps()
    e.call('bp_add', addr=PS['ts_sync'])
    while True:
        go(e, 4000)
        pc = e.call('get_registers')['PC']
        tr.event(pc)
        if pc == PS['ts_sync']: break
    return tr, C.frames(e)

def part_title(dsk):
    print('1. the title h-m: pv_scene, i, j, k, the fade-out, the title again (POP800.PR2 read from the disk)')
    tg, th = title_ticks()
    cs = cutsim.named_scene('pv_scene')
    with Emu() as e:
        tr, F0 = run_to_sync(e, dsk)
        t0 = time.time()
        run_step(e, tr, 'h')
        check('step h at tick %d: frame %d, the screen black (g\'s fade-out)' % (th, th * 5 // 6),
              word(e, PS['t_target']) - F0 == th * 5 // 6 and e.vram_planes() == BLACK, word(e, PS['t_target']) - F0)
        # pv_scene: starts when music 55 ends: tick tg + its length
        T0 = tg + cutsim.sound_ticks60(55)
        m = C.scene_run(e, cs, tr, F0=F0, T0=T0, stop=('op_cret',))
        C.report(cs, 'pv_scene', m, T0=T0)
        check('   no scene frame skipped' if not m['skipped'] else '   skipped frames: %s (reported, the next drawn frame exact)' % m['skips'], True)
        flash = [f['n'] for f in cs.frames if f['flash']]
        got = m['flashes']
        check('   the flash: %d frames show PLT0 = 15 for their first 2 ticks, group 1; back to black at the next frame (checked there); frames %s' % (len(got), flash),
              [f[0] for f in got] == [n for n in flash if n not in m['skips']] and all(f[1:] == (15, 1) for f in got) and len(flash) == 5, (got, flash))
        check('   the PZ sprites were unpacked when their image changed (%d)' % m['unpz'], m['unpz'] > 50, m['unpz'])
        check('   the end of pv_scene: the screen black, tick %d' % (T0 + cs.t), m.get('end_black') and m['end_tick'] == T0 + cs.t, (m.get('end_black'), m.get('end_tick')))
        mus_end = word(e, PS['mus_end'])
        Tpv = T0 + cs.t
        Ti = Tpv + PS['TITLE_I_LOAD'] + 16
        # i's fade-in
        e.call('bp_clear'); tr.bps(); e.call('bp_add', addr=PS['tf_pass']); e.call('bp_add', addr=PS['ts_step'])
        black = T.blank(); marry = T.screen(['FRAME', 'MARRY']); ok = True; lastfr = None
        while True:
            go(e); pc = e.call('get_registers')['PC']; tr.event(pc)
            if pc == PS['tf_pass']:
                k = e.mem(PS['t_col'], 1)[0]; d = T.diff(scr(e), T.fade_in(black, marry, k + 1))
                if d: ok = False; print('      pass', k, len(d), d[:3])
            if pc == PS['ts_step']: break
        check('i: the fade-in\'s 5 passes of frame + "Marry Jaffar" pixel-exact, step i at frame floor(5 T / 6), T = %d' % Ti,
              ok and chr(e.mem(PS['t_step'], 1)[0]) == 'i' and word(e, PS['t_target']) - F0 == Ti * 5 // 6, word(e, PS['t_target']) - F0)
        # j: music 52 ended (the ticks model), MAIN + logo decoded meanwhile
        Tj = mus_end + PS['TITLE_J_LOAD']
        run_step(e, tr, 'j')
        fr = word(e, PS['t_target']) - F0; late = C.frames(e) - F0 - fr
        check('j at tick %d (music 52\'s end + %d): frame %d; VRAM still frame + "Marry Jaffar"; lag %d frames' % (Tj, PS['TITLE_J_LOAD'], Tj * 5 // 6, late),
              fr == Tj * 5 // 6 and not T.diff(scr(e), marry) and late <= 2, (fr, late))
        print('   music 52 length model: mus_end %d, its stream: %s' % (mus_end, [x for x in tr.lengths if x[0] == 52]))
        fj = C.frames(e)
        run_step(e, tr, 'k')
        Tk = Tj + WIPE + 120
        main = T.screen(['MAIN', 'POP', 'MECHNER']); cred = T.screen(['FRAME', 'CREDITS'])
        check('k at tick %d: VRAM = main + logo + copyright (the wipe)' % Tk, not T.diff(scr(e), main) and word(e, PS['t_target']) - F0 == Tk * 5 // 6, word(e, PS['t_target']) - F0)
        run_step(e, tr, 'm')
        Tm = Tk + WIPE + 360
        check('m at tick %d: VRAM = frame + credits' % Tm, not T.diff(scr(e), cred) and word(e, PS['t_target']) - F0 == Tm * 5 // 6, word(e, PS['t_target']) - F0)
        e.call('bp_clear'); tr.bps(); e.call('bp_add', addr=PS['title'])
        while True:
            go(e); pc = e.call('get_registers')['PC']; tr.event(pc)
            if pc == PS['title']: break
        check('after m\'s fade-out (screen black) the title again (step 9 puts the demo here)', e.vram_planes() == BLACK)
        C.psg_report(tr, 'the title from h to m (music 55 on, 50, 54, 42)')
        check('   the music: g\'s piece (55) on through h\'s black and fade-in, Jaffar\'s piece (50) from pv_scene\'s first cue, the title theme (54) at j, '
              'the credits (42) at k; the cues 4, 51, 53, 52 start nothing; banks A at the title\'s start, B at h, C before j: %s' % tr.banks,
              all(s in tr.starts for s in (50, 54, 42)) and not any(s in tr.starts for s in (4, 51, 53, 52)) and tr.starts.get(55) == 1 and
              [b for _, b in tr.banks] == ['PRS_SOUND', 'PRS_SND_B', 'PRS_SND_C'], (tr.starts, tr.banks))
        check('   Jaffar\'s piece looped %s times through pv_scene and i (24.4 s a loop)' % tr.wraps.get(50), tr.wraps.get(50, 0) >= 1, tr.wraps)
        C.write_wav(tr, 'title_h-i', f1=fj); C.write_wav(tr, 'title_j-m', f0=fj)
        print('   the whole run took %.0f s of host time' % (time.time() - t0))
    print('   title ticks: g %d, h %d, pv_scene %d-%d, i %d, j %d, k %d, m %d (%.1f s at 60 a second)' % (tg, th, T0, Tpv, Ti, Tj, Tk, Tm, (Tm + 20) / 60))
    return m

def press_at(a, b):
    def f(e, n):
        if n == a: e.call('input_press_key', key='SPACE')
        if n == b: e.call('input_release_key', key='SPACE')
    return f

def boot_action(e, dsk, action, level=1, rem_min=0):
    M5.fill_ramdisk(e)
    e.call('media_insert', slot='fdc0_fd0', path=dsk, ro=True)
    e.call('reset')
    M5.run_to(e, PS['pres'], 3000)
    ho = bytearray(e.mem(HO, 16)); ho[2] = action; ho[3] = level; ho[4] = rem_min; ho[5:7] = (0).to_bytes(2, 'little'); ho[7] = 3
    e.call('mem_write', addr=HO, data_hex=bytes(ho).hex())

def part_expired(dsk):
    print('2. time_expired (action 0x11), keys ignored, then the title')
    cs = cutsim.named_scene('time_expired')
    with Emu() as e:
        boot_action(e, dsk, BS['ACT_EXPIRED'])
        tr = C.tracker(e)
        m = C.scene_run(e, cs, tr, stop=('tc_exptitle',), at_start=press_at(20, 30))
        C.report(cs, 'time_expired', m, mus=36)
        check('   the 200-row room: rows 192-199 not black', any(any(v for v in r) for r in m['screens'][0][192:]))
        check('   the end (music 36 over, tick %d = its length): the screen black, SPACE pressed at frames 20-30 ignored' % cs.t,
              m.get('end_black') and m['end_tick'] == cs.t, (m.get('end_black'), m['end_tick']))
        C.psg_report(tr, 'time_expired')
        C.write_wav(tr, 'time_expired')
        M5.run_to(e, PS['ts_step'], 2000)
        check('   then the title, step a', chr(e.mem(PS['t_step'], 1)[0]) == 'a')

def part_ending(dsk):
    print('3. the ending (action 0x12): end_sequence_anim, the hail screen, TITLE_MAIN until music 56 ends, then the title')
    cs = cutsim.named_scene('end_sequence_anim')
    with Emu() as e:
        boot_action(e, dsk, BS['ACT_ENDING'], 14, 42)
        tr = C.tracker(e)
        bg = cutsim.Render(cs).background()
        m = C.scene_run(e, cs, tr, stop=('op_cret',), last=bg, at_start=press_at(20, 30))
        C.report(cs, 'end_sequence_anim', m, mus=26)
        check('   rows 192-199 black (the game\'s offscreen surface)', all(all(v == 0 for v in r) for r in m['screens'][0][192:]))
        check('   the end (music 26 over, tick %d): the screen black, SPACE pressed at frames 20-30 ignored' % cs.t, m.get('end_black') and m['end_tick'] == cs.t, (m.get('end_black'), m['end_tick']))
        run_step(e, tr, 'q')
        F0 = m['F0']; T0 = cs.t
        Tq = word(e, PS['ct_tick'])
        Tp = Tq - 16
        hail = T.screen(['FRAME_RED', 'HAIL']); main = T.screen(['MAIN'])
        check('the hail screen at step q (the fade-in done; the title theme of the embrace (26) loops on, no music 56 start)',
              not T.diff(scr(e), hail) and 26 in tr.starts and 56 not in tr.starts, (len(T.diff(scr(e), hail)), tr.starts))
        run_step(e, tr, 'r')
        check('step r 900 ticks later: the frame floor(5 T / 6)', word(e, PS['t_target']) - F0 == (Tq + 900) * 5 // 6, word(e, PS['t_target']) - F0)
        run_step(e, tr, 's')
        check('TITLE_MAIN (the wipe\'s result) at step s (240 ticks after r)', not T.diff(scr(e), main) and word(e, PS['ct_tick']) == Tq + 900 + 240, word(e, PS['ct_tick']))
        run_step(e, tr, 't')
        check('step t when the model\'s 56 ends: tick %d = the embrace\'s start + %d + %d (3 loops of the title theme = 2052 ticks), TITLE_MAIN' % (
              Tp + cutsim.sound_ticks60(56), Tp, cutsim.sound_ticks60(56)),
              word(e, PS['ct_tick']) == Tp + cutsim.sound_ticks60(56) == 2052 and not T.diff(scr(e), main), word(e, PS['ct_tick']))
        e.call('bp_clear'); tr.bps(); e.call('bp_add', addr=PS['title'])
        while True:
            go(e); pc = e.call('get_registers')['PC']; tr.event(pc)
            if pc == PS['title']: break
        check('then the fade-out and the title', e.vram_planes() == BLACK)
        C.psg_report(tr, 'the ending')
        check('   the title theme looped %s times from the embrace to step t (2 loop commands + the third play; the halt at t may fall on the third)' % tr.wraps.get(26), tr.wraps.get(26) in (2, 3), tr.wraps)
        C.write_wav(tr, 'ending')

def step_to(e, s):
    e.call('bp_clear'); e.call('bp_add', addr=PS['ts_step'])
    while True:
        assert go(e), 'no step ' + s
        if chr(e.mem(PS['t_step'], 1)[0]) == s: return

def part_ending_keys(dsk):
    print('3b. a key at the hail screen (do_wait: it ends the wait) and on TITLE_MAIN; music 56 still decides the end')
    with Emu() as e:
        boot_action(e, dsk, BS['ACT_ENDING'], 14, 42)
        MT.to_step(e, 'q')
        t0 = C.frames(e); Tq = word(e, PS['ct_tick'])
        M5.run_to(e, PS['t_wait'], 200)                  # (TITLE_MAIN decoded into page 1: the wait starts)
        e.run(3)
        e.call('input_press_key', key='SPACE')
        step_to(e, 'r'); n = C.frames(e) - t0
        e.call('input_release_key', key='SPACE')
        check('SPACE at q\'s wait: step r after %d frames (not 750)' % n, n < 150, n)
        tick = word(e, PS['ct_tick'])
        print('   the clock counted %d ticks to r (the frames left x 6/5)' % (tick - Tq))
        step_to(e, 's')
        d = T.diff(scr(e), T.screen(['MAIN']))
        check('TITLE_MAIN at s (without a key: 160 ticks after the wipe)', not d, len(d))
        e.call('input_press_key', key='SPACE')             # (a key on s: no effect: the music decides)
        fs = C.frames(e); ts = word(e, PS['ct_tick']); me = word(e, PS['mus_end'])
        step_to(e, 't'); e.call('input_release_key', key='SPACE')
        check('a key during s ignored: step t when the model\'s music ends (tick %d, %d frames later)' % (me, C.frames(e) - fs),
              word(e, PS['ct_tick']) == me and C.frames(e) - fs >= (me - ts) * 5 // 6 - 2 > 100, (word(e, PS['ct_tick']), me, ts, C.frames(e) - fs))

def key_case(dsk, step, what, h=None):
    with Emu() as e:
        MT.boot(e, dsk)
        MT.to_step(e, step)
        if what: M5.run_to(e, PS[what], 3000)
        e.call('input_press_key', key='SPACE')
        n = M5.run_to(e, PS['p_go'], 200)
        e.call('input_release_key', key='SPACE')
        ho = e.mem(PS['ho'], 16)
        check('SPACE at step %s%s: the handoff ACT_PLAY level 1, 60:719, 3 hit points after %d frames' % (step, ' (' + what + ')' if what else '', n),
              ho[2:8] == bytes([0, 1, 60, 719 & 255, 719 >> 8, 3]) and ho[9:] == bytes(7), ho.hex())
        return MT.launched(e) if h else None

def part_keys(dsk, tmp):
    print('4. keys as show_title: any key starts a new game, in the story screens and in pv_scene too')
    for step, what in (('g', None), ('h', 'tc_drawn'), ('i', None), ('j', None), ('k', None)):
        key_case(dsk, step, what)
    h = MT.direct(1, (60, 719))
    f = key_case(dsk, 'h', 'tc_drawn', h)
    MT.compare_game('level 1 after a key in pv_scene', h, f)
    with Emu() as e:
        MT.boot(e, dsk)
        MT.to_step(e, 'h')
        M5.run_to(e, PS['tc_drawn'], 3000)
        pc, loaded = MT.ctrl_l(e, upto=('title', 'p_go'))
        check('Ctrl+L in pv_scene, POP800.SAV empty: load_saved ran, the title starts again (its sprites were in the buffers)',
              loaded and pc == PS['title'], ('%04X' % pc, loaded))
        M5.run_to(e, PS['ts_step'], 3000)
        check('   its step a comes', chr(e.mem(PS['t_step'], 1)[0]) == 'a')

def part_late(dsk):
    print('5. forced lateness: a frame\'s start pushed late (FRAMES + 12 at chosen frames, as an overrun would): logic exact, drawing skipped')
    for lv, rm, late in ((8, 60, (5, 18, 33, 47)), (9, 3, (3, 7, 30, 60))):
        cs = cutsim.level_scene(lv, rm)
        with Emu() as e:
            C.boot_pres(e, dsk, lv, rm)
            M5.run_to(e, PS['ts_sync'], 2000)
            F0 = C.frames(e)
            class NoTr:
                addr = {}
                def event(self, pc): return None
            def push(e, n):
                if n in late:
                    f = C.frames(e) + 12
                    e.call('mem_write', addr=0x0800, data_hex='%02x%02x' % (f & 255, f >> 8))
            m = C.scene_run(e, cs, NoTr(), F0=F0, at_start=push)
            print('   %s: %d frames, %d drawn, %d skipped: %s' % (cs.scene, m['n'], m['drawn'], m['skipped'], m['skips']))
            check('level %d: the frames after each pushed frame are skipped until the clock is caught up' % lv,
                  all(n in m['skips'] for n in late) and m['drawn'] >= m['n'] - 2 - 4 * len(late), m['skips'])
            check('   the C lines stay exact through the skips', not m['bad_c'] and m['n'] == m['want_n'], m['bad_c'])
            check('   VRAM pixel-exact after every drawn frame (the dirty rectangles repair the skipped ones)', not m['bad_v'], m['bad_v'])
            check('   the frames\' clock unchanged', not m['bad_t'], m['bad_t'][:3])

def launched_game(e, dsk):
    """boot -> title -> a key -> the game at level_ready"""
    MT.boot(e, dsk)
    M5.title_start(e, 'SPACE')
    M5.run_to(e, G['level_ready'], 2000)

def part_flow(dsk):
    print('6. the flow in the real game: a time-out and level 14\'s end through PRES back to the title')
    with Emu() as e:
        launched_game(e, dsk)
        e.call('mem_write', addr=EV + 1, data_hex='01')              # rem_min 1, rem_tick 3 ticks
        e.call('mem_write', addr=EV + 2, data_hex='0300')
        e.call('bp_clear'); e.call('bp_add', addr=PS['pres'])
        go(e); pc = e.call('get_registers')['PC']
        ho = e.mem(HO, 16)
        check('the clock runs out in the launched game: PRES starts with ACT_EXPIRED', pc == PS['pres'] and ho[2] == BS['ACT_EXPIRED'], ('%04X' % pc, ho.hex()))
        tr = C.tracker(e)
        cs = cutsim.named_scene('time_expired')
        m = C.scene_run(e, cs, tr, stop=('tc_exptitle',))
        check('   time_expired plays exactly (the C lines, VRAM)', not m['bad_c'] and not m['bad_v'] and m['n'] == m['want_n'], (m['bad_c'], m['bad_v']))
        M5.run_to(e, PS['ts_step'], 2000)
        check('   then the title', chr(e.mem(PS['t_step'], 1)[0]) == 'a')
        e.call('input_press_key', key='SPACE')
        M5.run_to(e, PS['p_go'], 200)
        e.call('input_release_key', key='SPACE')
        f = MT.launched(e)
        g = e.call('get_periph_gdg')
        check('   the game\'s palette: group 0, PLT0-3 = 0, 1, 2, 3', g['regPALGRP'] == 0 and g['palette'][:4] == [0, 1, 2, 3], g)
    h = MT.direct(1, (60, 719))
    MT.compare_game('a new game after the time-out', h, f)
    with Emu() as e:
        # level 14 from the title (the handoff's level), the kid walks: right over the button, then left through the
        # gates into room 5 (found with kidsim; tests/m5_scripts/level14_end.txt is the oracle's scene of the last part)
        MT.boot(e, dsk)
        M5.title_start(e, 'SPACE')
        e.call('mem_write', addr=PS['ho'] + 3, data_hex='0e')
        M5.run_to(e, G['level_ready'], 2000)
        moves = [(0, 0, 0)] * 5 + [(1, 0, 0)] * 20 + [(0, 0, 0)] * 5
        for i in range(40): moves += [(-1, 0, 0)] * 40 + [(0, 0, 0)] * 10
        scr0 = e.region(M5.RAMDISK[5], SCRIPT, 4096)                 # (the harness script's place: put back for the comparison below)
        write_pack(e, encode(moves, [0] * len(moves)), 5, SCRIPT)
        e.call('mem_write', addr=SCRIPT_PTR, data_hex='%02x%02x' % (SCRIPT & 255, SCRIPT >> 8))
        e.call('bp_clear'); e.call('bp_add', addr=PS['pres'])
        go(e, 20000); pc = e.call('get_registers')['PC']
        ho = e.mem(HO, 16)
        check('the kid enters room 5 of level 14 (check_the_end): PRES starts with ACT_ENDING', pc == PS['pres'] and ho[2] == BS['ACT_ENDING'], ('%04X' % pc, ho.hex()))
        tr = C.tracker(e)
        cs = cutsim.named_scene('end_sequence_anim')
        bg = cutsim.Render(cs).background()
        m = C.scene_run(e, cs, tr, stop=('op_cret',), last=bg)
        check('   the embrace plays exactly', not m['bad_c'] and not m['bad_v'] and m['n'] == m['want_n'], (m['bad_c'], m['bad_v']))
        e.call('bp_clear'); e.call('bp_add', addr=PS['title']); go(e)
        check('   the hail screen and TITLE_MAIN, then the title', e.call('get_registers')['PC'] == PS['title'])
        M5.run_to(e, PS['ts_step'], 2000)
        write_pack(e, scr0, 5, SCRIPT)
        e.call('input_press_key', key='SPACE')
        M5.run_to(e, PS['p_go'], 200)
        e.call('input_release_key', key='SPACE')
        f = MT.launched(e)
    MT.compare_game('a new game after the ending', h, f)

def main():
    parts = [a for a in ARGS if not a.startswith('-')] or ['title', 'expired', 'ending', 'keys', 'late', 'flow']
    tmp = tempfile.mkdtemp(prefix='m7story')
    try:
        dsk = os.path.join(tmp, 'pop800.dsk'); shutil.copy(M5.DSK, dsk)
        for p in parts:
            if p == 'title': part_title(dsk)
            if p == 'expired': part_expired(dsk)
            if p == 'ending': part_ending(dsk); part_ending_keys(dsk)
            if p == 'endkeys': part_ending_keys(dsk)
            if p == 'keys': part_keys(dsk, tmp)
            if p == 'late': part_late(dsk)
            if p == 'flow': part_flow(dsk)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    allf = FAILS + MT.FAILS
    print('M7 story test %s' % ('OK' if not allf else 'FAILED (%d)' % len(allf)))
    sys.exit(1 if allf else 0)

if __name__ == '__main__':
    main()
