#!/usr/bin/env python3
"""M7 steps 7-8: the level cutscenes in PRES (src/pres/cut.asm) against tools/cutsim.py (checked against SDLPoP by
tools/cut_suite.py). tests/m7_story.py tests pv_scene, time_expired and the ending with this file's scene_run. Every run boots a copy of build/pop800.dsk (mz800emu writes a mounted image back on eject); at
PRES's start the handoff is turned into ACT_CUTSCENE for the case's level and time.
  1. per case (level, rem_min): the 'C' line of every cutscene frame (tc_frame: both characters, the hourglass, its sand,
     the star, the torches, the flash, the frame time, the sound model) equals cutsim's; VRAM after every drawn frame
     (tc_drawn) equals cutsim's render pixel for pixel (frames whose drawing was skipped are counted, and the next drawn
     frame must be exact); the fades' passes; the frames' clock: every frame starts at the clock's frame
     floor(5 T / 6), T = cutsim's tick of the frame (a fade: one frame at its start, then 5 passes 4 ticks apart and 4
     more ticks); the music (27, 35, 40: the Master System cutscene piece, M7 step 11) starts with frame 0 (psg.asm
     snd_start: the fade-in's frame), the PSG state at every interrupt that plays equals tools/sndsim.py's; the scene
     ends (tc_end) when the ticks model's music ends (8.64 s: the piece's end; build/sound/pres/cutscene_*.wav),
     at the tick cutsim's W line gives, the screen black (the fade-out); then the launcher starts the level with the
     handoff's time.
     The frame cost: the cycles from the frame's start to tc_drawn (logic + drawing), against the 5-frame budget.
  2. the handoff path: tests/m7_launch.py (level 1's end -> PRES level 2 cutscene -> level 2 against a direct start).
  3. a key during the scene: the level starts at once (the sound stopped, the screen black).
  4. Ctrl+L at the title with a save (as tests/m5_save.py makes it) on cutscene levels 4 and 9: the scene before the level
     plays (frames exact), then the level starts with the saved time; a save on level 5 (no cutscene): the level at once.
usage: m7_cut.py [--quick] [level:rem_min ...]   (--quick: part 1 for levels 2 and 8 only)"""
import os, shutil, sys, tempfile, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools')); sys.path.insert(0, os.path.join(ROOT, 'tests'))
ARGS = sys.argv[1:]
sys.argv = sys.argv[:1]
from emu import Emu
from m3_test import syms
import m5_boot as M5
import m7_sound
import sndsim
import cutsim
BUILD = os.path.join(ROOT, 'build')
G = syms(os.path.join(BUILD, 'm4game.sym')); BS = syms(os.path.join(BUILD, 'boot.sym')); PS = syms(os.path.join(BUILD, 'pres.sym'))
HO = BS['HO_MAIN']; EV = 0x0280
FRAME_T = 312 * 228
CASES = [(2, 60), (4, 30), (6, 10), (8, 60), (9, 3), (12, 60), (12, 3)]
FAILS = []

def check(what, ok, detail=''):
    print('  %-96s %s%s' % (what, 'ok' if ok else 'FAILED', '' if ok else '  ' + str(detail)))
    if not ok: FAILS.append(what)

def word(e, a):
    b = e.mem(a, 2); return b[0] | (b[1] << 8)
def frames(e): return word(e, 0x0800)
def cyc(e): return e.call('get_raster_pos')['total_cycles']
def s8(v): return v - 256 if v > 127 else v

def planes(scr):
    """a screen (200 rows of 320 MZ colours) as the four VRAM planes"""
    P = [bytearray(8000) for _ in range(4)]
    for y in range(200):
        row = scr[y]
        for xb in range(40):
            v = [0, 0, 0, 0]
            for bit in range(8):
                c = row[xb * 8 + bit]
                for p in range(4):
                    if c >> p & 1: v[p] |= 1 << bit
            for p in range(4): P[p][y * 40 + xb] = v[p]
    return [bytes(p) for p in P]

def diff_px(a, b):
    """the number of differing pixels between two plane sets, and the first (x, y)"""
    n = 0; first = None
    for p in range(4):
        for i in range(8000):
            d = a[p][i] ^ b[p][i]
            if d:
                n += bin(d).count('1')
                if first is None: first = ((i % 40) * 8 + (d & -d).bit_length() - 1, i // 40)
    return n, first

def c_line(e, n):
    """the Z80's 'C' line at tc_frame (cutsim's format)"""
    k = e.mem(PS['cut_kid'], 7); s = e.mem(PS['cut_shad'], 7)
    v = e.mem(PS['cut_vars'], PS['cut_vars_end'] - PS['cut_vars'])
    o = lambda name: PS[name] - PS['cut_vars']
    star = e.mem(PS['cut_star'], 1)[0]
    stcol = v[o('cut_stcol') + star] if star != 0xFF else 0xFF
    fl = e.mem(PS['cut_flshow'], 1)[0]
    left = v[o('cut_left')] | v[o('cut_left') + 1] << 8
    return 'C %d  %d %d %d %d  %d %d %d %d  %d %d  %d %d  %d %d  %d %d  %d %d %d' % (
        n, k[0], k[1], k[2], s8(k[3]), s[0], s[1], s[2], s8(s[3]), v[o('cut_hg')], s8(v[o('cut_sand')]), s8(star), s8(stcol),
        v[o('cut_torch')], v[o('cut_torch') + 1], fl, v[o('cut_ft')], s8(v[o('cut_next')]), v[o('cut_cur')], int(left > 0))

def boot_pres(e, dsk, level, rem_min):
    """boot; at PRES's start the handoff becomes ACT_CUTSCENE level, rem_min"""
    M5.fill_ramdisk(e)
    e.call('media_insert', slot='fdc0_fd0', path=dsk, ro=True)
    e.call('reset')
    M5.run_to(e, PS['pres'], 3000)
    ho = bytearray(e.mem(HO, 16))
    ho[2] = BS['ACT_CUTSCENE']; ho[3] = level; ho[4] = rem_min; ho[5:7] = (431).to_bytes(2, 'little'); ho[7] = 4
    e.call('mem_write', addr=HO, data_hex=bytes(ho).hex())
    return bytes(ho)

BANKS = {'PRS_SOUND': 'sound_pres.bin', 'PRS_SND_B': 'sound_pres_b.bin', 'PRS_SND_C': 'sound_pres_c.bin'}   # (tools/presbank.py)
def bank(name='PRS_SOUND'):
    return sndsim.load_bank(os.path.join(BUILD, 'assets', BANKS[name]), 0)

def tracker(e):
    """the PSG against tools/sndsim.py (tests/m7_sound.py's tracker, as tests/m7_title.py uses it): created while the
    player is stopped (PRES's start); its breakpoints are added by scene_run. The model's bank follows PRES's bank
    loads (tc_bank: bank_cur; M7 step 11: the stream playing goes on, at the same address in the new bank)"""
    tr = m7_sound.Tracker(e, PS, 'silent', bank())
    tr.addr = {PS['spi_done']: 'act', PS['snh_di']: 'halt', PS['snd_arm']: 'arm', PS['snd_start']: 'start', PS['sf_x']: 'fill',
               PS['tc_mute']: 'mute', PS['tc_bank']: 'bank'}
    tr.banks = []
    ev = tr.event
    def event(pc):
        if tr.addr.get(pc) == 'mute':                 # (do_load: psg_mute, the stream pauses: sndsim's chip muted too)
            tr.sync(frames(e)); st = m7_sound.psg(e); tr.sim.p.psg.load(st); tr.states.append((frames(e), st)); return 'mute'
        if tr.addr.get(pc) == 'bank':
            cur = e.mem(PS['bank_cur'], 1)[0]; name = {PS[k]: k for k in BANKS}[cur]
            nb = bank(name); tr.banks.append((frames(e), name))
            if tr.cur is not None:                    # (the stream playing must be the same bytes at the same place)
                sid = tr.cur[0]
                assert nb.get(sid) == tr.sim.p.bank.get(sid) and nb.loops.get(sid) == tr.sim.p.loop, ('the playing stream differs in the new bank', sid, name)
            tr.sim.p.bank = nb; return 'bank'
        return ev(pc)
    tr.event = event
    return tr

def write_wav(tr, name, f0=None, f1=None):
    """build/sound/pres/<name>.wav: the PSG as the emulator played it, from frame f0 to f1 (the tracker's whole run)"""
    st = tr.per_frame(f1 if f1 is not None else frames(tr.e))
    if f0 is not None: st = st[f0 - tr.f0:]
    w = os.path.join(BUILD, 'sound', 'pres', name + '.wav')
    sndsim.write_wav(w, sndsim.render(st)); print('   wrote %s' % w)

def scene_run(e, cs, tr, F0=None, T0=0, stop=('tc_end', ), last=None, at_start=None):
    """run the scene to a stop label against cutsim's scene cs; F0, T0: the clock's start frame and the scene's first
    tick on it (None: the scene's own OP_SYNC). Checks at every frame the C line, the frame's clock, VRAM after a drawn
    frame, the fade-in's and fade-out's passes; last: the screen the fade-out clears when nothing was drawn"""
    screens = list(cutsim.Render(cs).screens())
    want = [l for l in cs.lines if l.startswith('C')]
    c0 = cyc(e)
    e.call('bp_clear')
    mine = ['tcf_pass', 'tfo_pass', 'tc_fstart', 'tc_frame', 'tc_drawn', 'tc_abort', 'tc_flash', 'tc_unpz'] + list(stop)
    if F0 is None: mine.append('ts_sync')
    for a in mine: e.call('bp_add', addr=PS[a])
    for a in tr.addr: e.call('bp_add', addr=a)
    m = dict(bad_c=[], bad_v=[], bad_t=[], bad_p=[], bad_o=[], skipped=0, drawn=0, costs=[], lags=[], music=[], load=None, flashes=[], unpz=0, skips=[])
    n = 0; c_start = None; shown = None; addr = {PS[a]: a for a in mine}
    while True:
        r = e.run(1000)
        if r['stopped_by'] != 'breakpoint': continue
        pc = e.call('get_registers')['PC']
        what = tr.event(pc)
        if what == 'start' or pc == PS['snd_start']:
            m['music'].append((e.call('get_registers')['AF'] >> 8, n, frames(e) - (F0 if F0 is not None else 0)))
        a = addr.get(pc)
        if a is None: continue
        if a == 'tc_fstart':
            c_start = cyc(e)
            g = e.call('get_periph_gdg')
            if g['palette'][:4] != [0, 5, 6, 7] or g['regPALGRP'] != 1: m.setdefault('bad_pal', []).append((n, g['palette'][:4], g['regPALGRP']))
            if at_start: at_start(e, n)
        elif a == 'ts_sync':
            F0 = frames(e); m['load'] = (cyc(e) - c0) / FRAME_T
        elif a == 'tc_unpz': m['unpz'] += 1
        elif a == 'tcf_pass':
            k = e.mem(PS['t_col'], 1)[0]
            f = cs.frames[n - 1]
            ref = [bytes(bytearray(fp[i] if (i // 40) % 5 <= k else 0 for i in range(8000))) for fp in planes(screens[n - 1])]
            d = diff_px(e.vram_planes(), ref)
            tgt = word(e, PS['t_target']) - F0; wt = (T0 + f['tick'] + 4 * k) * 5 // 6
            if d[0] or tgt != wt: m['bad_p'].append((k, d, tgt, wt))
            if k == 4: shown = screens[n - 1]
        elif a == 'tfo_pass':
            k = e.mem(PS['t_col'], 1)[0]
            f = cs.frames[n - 1]
            src = planes(shown if shown is not None else last)
            ref = [bytes(bytearray(fp[i] if (i // 40) % 5 > k else 0 for i in range(8000))) for fp in src]
            d = diff_px(e.vram_planes(), ref)
            tgt = word(e, PS['t_target']) - F0; wt = (T0 + f['tick'] + 4 * k) * 5 // 6
            if d[0] or tgt != wt: m['bad_o'].append((k, d, tgt, wt))
        elif a == 'tc_frame':
            got = c_line(e, n)
            if got != want[n] and len(m['bad_c']) < 3: m['bad_c'].append((n, want[n], got))
            tgt = word(e, PS['t_target']) - F0
            wt = (T0 + cs.frames[n]['tick']) * 5 // 6
            if tgt != wt: m['bad_t'].append((n, wt, tgt))
            if cs.frames[n]['fade'] is None: m['lags'].append(frames(e) - F0 - tgt)
            if e.mem(PS['cut_late'], 1)[0]: m['skipped'] += 1; m['skips'].append(n)
            n += 1
        elif a == 'tc_drawn':
            m['drawn'] += 1
            if not os.environ.get('CUT_NOCOST'): m['costs'].append((cyc(e) - c_start) / FRAME_T)
            shown = screens[n - 1]
            d = diff_px(e.vram_planes(), planes(shown))
            if d[0] and len(m['bad_v']) < 3: m['bad_v'].append((n - 1, d))
        elif a == 'tc_flash':
            g = e.call('get_periph_gdg')
            m['flashes'].append((n - 1, g['palette'][0], g['regPALGRP']))
        elif a == 'tc_abort':
            m['aborted'] = n; m['stop'] = a; break
        else:
            m['stop'] = a
            m['end_tick'] = word(e, PS['ct_tick']); m['end_frame'] = frames(e) - F0; m['F0'] = F0
            m['end_black'] = e.vram_planes() == [bytes(8000)] * 4
            break
    m['n'] = n; m['want_n'] = len(want); m['W'] = cs.lines[-1].split(); m['screens'] = screens; m['shown'] = shown
    return m

def report(cs, label, m, T0=0, mus=None):
    w = [int(x) for x in m['W'][1:]]
    left = w[-1]
    print('   %s, %s: %d frames (%d drawn, %d skipped %s), loading %.0f frames; music %s' % (
        cs.scene, label, m['n'], m['drawn'], m['skipped'], m['skips'][:12], m['load'] or -1, m['music']))
    if os.environ.get('CUT_VERBOSE'): print('   costs %s' % ' '.join('%.1f' % c for c in m['costs']))
    costs = sorted(m['costs'])
    if costs:
        print('   frame cost (the frame\'s logic + drawing, MZ frames): min %.2f, median %.2f, max %.2f; lag at the frame start: '
              'max %d frames' % (costs[0], costs[len(costs) // 2], costs[-1], max(m['lags'])))
    check('%s: the C lines equal cutsim\'s (%d frames)' % (label, m['want_n']), not m['bad_c'] and m['n'] == m['want_n'], (m['bad_c'], m['n']))
    check('   VRAM pixel-exact against cutsim\'s render after every drawn frame (%d)' % m['drawn'], not m['bad_v'], m['bad_v'])
    check('   the fade-in\'s and fade-out\'s passes: VRAM and clock', not m['bad_p'] and not m['bad_o'], (m['bad_p'][:3], m['bad_o'][:3]))
    check('   every frame starts at the clock\'s frame floor(5 T / 6)', not m['bad_t'], m['bad_t'][:3])
    check('   the palette at every frame start: group 1, PLT0-3 = 0, 5, 6, 7 (MZ 4 shows black)', 'bad_pal' not in m, m.get('bad_pal', [])[:3])
    if mus is not None:
        check('   music %d starts with frame 0 (the fade-in\'s frame)' % mus, m['music'][:1] and m['music'][0][:2] == (mus, 0), m['music'])
    end = T0 + cs.t
    if 'end_tick' in m:
        check('   the scene ends with its music: tick %d (W line: %d left at its end), screen black' % (end, left),
              m['end_tick'] == end + 0 if cs.scene in ('time_expired', 'end_sequence_anim', 'pv_scene') or not left else m['end_tick'] == end + left,
              (m.get('end_tick'), m.get('end_black')))

def psg_report(tr, what):
    tr.finish()
    check('%s: the PSG at every interrupt that played a group equals sndsim\'s (%d samples; starts %s)' % (what, tr.samples, tr.starts),
          tr.bad == 0 and tr.samples > 0, tr.first)

def launched_level(e, ho):
    """after tc_end: the launcher starts the game: its level and time"""
    M5.run_to(e, G['level_ready'], 2000)
    lv = e.mem(G['level_number'], 1)[0]; ev = e.mem(EV, 31)
    return lv, ev[1], ev[2] | ev[3] << 8, ev[17]

def part1(dsk, cases):
    print('1. the level cutscenes against tools/cutsim.py')
    allc = []
    for lv, rm in cases:
        with Emu() as e:
            ho = boot_pres(e, dsk, lv, rm)
            tr = tracker(e)
            cs = cutsim.level_scene(lv, rm)
            m = scene_run(e, cs, tr)
            mus = {2: 27, 4: 27, 6: 27, 8: 35, 9: 35, 12: 40 if rm < 6 else 27}[lv]
            report(cs, 'level %d rem_min %d' % (lv, rm), m, mus=mus)
            check('   the rows 192-199 stay black (the game\'s 192-row offscreen surface)', all(all(v == 0 for v in r) for r in m['screens'][0][192:]))
            allc += m['costs']
            psg_report(tr, 'level %d' % lv)
            # (the piece is 432 frames = 518.4 ticks; the level starts at tick 519 (ceil), the clock rounds down: the stream's
            # last 1-2 frames fall after tc_end, where the level start halts it: all of it must have been copied and read)
            L = [x - 1 for s_, x in tr.lengths if s_ == mus]; p = tr.sim.p
            whole = L == [432] or (tr.cur is not None and tr.cur[0] == mus and p.left == 0 and p.avail <= 4)
            check('   music %d: the cutscene piece (SMS 7) played whole to the level start (%s)' % (
                  mus, 'ended, %s frames' % L if L else 'all %d bytes read but %d, %d frames before its end' % (len(p.src), p.avail, frames(e) - tr.cur[1] if tr.cur else -1)), whole, (L, p.left, p.avail))
            write_wav(tr, 'cutscene_%d_%d' % (lv, rm))
            got = launched_level(e, ho)
            check('   then the level starts: level %d, %d:431, 4 hit points (the handoff\'s)' % (lv, rm), got == (lv, rm, 431, 4), got)
    return allc

def tracker_at(e):
    """the tracker while PRES is at p_cutscene: the title's music is stopped there (p_play: snd_halt)"""
    return tracker(e)

def part3(dsk):
    print('3. a key during the scene: the level at once')
    with Emu() as e:
        boot_pres(e, dsk, 8, 60)
        M5.run_to(e, PS['ts_sync'], 2000)
        for _ in range(20): M5.run_to(e, PS['tc_frame'], 100)
        e.call('input_press_key', key='SPACE')
        e.call('bp_clear'); e.call('bp_add', addr=PS['tc_abort']); e.call('bp_add', addr=PS['tc_end'])
        r = e.run(100); pc = e.call('get_registers')['PC']
        e.call('input_release_key', key='SPACE')
        n = e.mem(PS['cut_n'], 1)[0]
        black = e.vram_planes() == [bytes(8000)] * 4
        check('SPACE at frame 20 of the level 8 scene: aborted (tc_abort) after frame %d, the screen black' % n,
              pc == PS['tc_abort'] and black and 20 <= n <= 23, ('%04X' % pc, n, black))
        f0 = frames(e)
        got = launched_level(e, None)
        check('   then level 8 starts with the handoff\'s time', got == (8, 60, 431, 4), got)

def part4(tmp, level=4):
    print('4. Ctrl+L at the title with a save on level %d' % level)
    import m5_save, m7_title
    dsk = os.path.join(tmp, 'save%d.dsk' % level); shutil.copy(M5.DSK, dsk)
    with Emu() as e:
        S = m5_save.boot_level(e, level, dsk, ro=False)
        e.call('mem_write', addr=EV + 1, data_hex='29')
        e.call('mem_write', addr=EV + 2, data_hex='2301')
        m5_save.ticks(e, S, 1)
        st = m5_save.state(e, S)
        m5_save.key(e, 'CTRL', 'G'); m5_save.ticks(e, S, 1); m5_save.key(e, 'CTRL', 'G', down=False)
        m5_save.ticks(e, S, 2)
        e.call('media_eject', slot='fdc0_fd0')
    rec = m5_save.sav_file(dsk)[:14]
    check('the save: level %d, %d:%d, %d hit points' % (st['level'], st['rem_min'], st['rem_tick'], st['hitp']),
          rec == m5_save.record(st), rec.hex())
    with Emu() as e:
        m7_title.boot(e, dsk)
        m7_title.to_step(e, 'b')
        e.call('input_press_key', key='CTRL'); e.call('input_press_key', key='L')
        scene = level in cutsim.LEVEL_SCENES
        stop = PS['p_cutscene'] if scene else PS['p_go']
        e.call('bp_clear'); e.call('bp_add', addr=PS['p_cutscene']); e.call('bp_add', addr=PS['p_go'])
        e.run(300); pc = e.call('get_registers')['PC']
        e.call('input_release_key', key='L'); e.call('input_release_key', key='CTRL'); e.call('bp_clear')
        ho = e.mem(PS['ho'], 16)
        check('Ctrl+L at step b: load_saved, then %s' % ('the cutscene before level %d (p_cutscene)' % level if scene else 'level %d at once (p_go)' % level),
              pc == stop and ho[3] == level and ho[4] == st['rem_min'], ('%04X' % pc, ho.hex()))
        if scene:
            tr = tracker_at(e)
            cs = cutsim.level_scene(level, st['rem_min'])
            m = scene_run(e, cs, tr)
            report(cs, 'level %d' % level, m)
            psg_report(tr, 'level %d after Ctrl+L' % level)
        got = launched_level(e, ho)
        check('   then level %d with the saved time and hit points' % level, got == (level, st['rem_min'], st['rem_tick'], st['hitp']), got)

def main():
    quick = '--quick' in ARGS
    cases = [tuple(int(v) for v in a.split(':')) for a in ARGS if ':' in a] or ([(2, 60), (8, 60)] if quick else CASES)
    tmp = tempfile.mkdtemp(prefix='m7cut')
    try:
        dsk = os.path.join(tmp, 'pop800.dsk'); shutil.copy(M5.DSK, dsk)
        costs = part1(dsk, cases)
        if costs:
            c = sorted(costs)
            print('   all frames: cost min %.2f, median %.2f, max %.2f MZ frames (budget 5)' % (c[0], c[len(c) // 2], c[-1]))
        if not quick and not any(':' in a for a in ARGS):
            part3(dsk)
            part4(tmp, 4)
            part4(tmp, 9)
            part4(tmp, 5)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print('M7 cutscene test %s' % ('OK' if not FAILS else 'FAILED (%d)' % len(FAILS)))
    sys.exit(1 if FAILS else 0)

if __name__ == '__main__':
    main()
