#!/usr/bin/env python3
"""M7 steps 3-4: the PSG player (src/m4/psg.asm) against tools/sndsim.py, frame by frame, in mz800emu.

At every interrupt where the player is active (a breakpoint at spi_done: the envelopes stepped and the frame's group
read) the emulator's SN76489 state (get_periph_sn76489: attenuation and tone divider of channels 0-2, attenuation, rate
and type of the noise channel) must equal sndsim's state after the same events. Events are taken where they happen in
the Z80 (breakpoints, with the frame counter FRAMES): snd_start (the id), snd_halt (the stream stops, the PSG is
muted), snd_fill's copy (sf_x: sndsim copies as many bytes as the Z80 did, which must fit sndsim's ring; a byte read
before it was copied is an underrun), snd_arm (the stream starts), and in the game the sound model's decision: at
snd_playing sndsim's player state is the expected `playing`, and play_next_sound's rule (sndsim Sim.decide, kidsim's
tables) on the queued id, the last started id and sound 15's flag gives the expected `started`; both are checked at
snd_next's end (snn_x: B started, C queued, E playing).
  A. direct: a small driver program (assembled here against build/m4game.sym, run in the compose buffers after the
     level start; it refills the ring after every frame) plays every stream of the bank to its end, then starts sounds
     over playing ones and stops one (snd_halt) midway; then the presentation's pieces (build/assets/sound_pres*.bin,
     the Master System pieces, the looping ones through the loop command (psg.asm snd_fill, M7 step 11),
     written to the bank's place for the test). The length of each music piece (frames from its arm to its end) must
     equal the MIDI length within 1 frame. Also the ISR's cost per frame (cycles from `isr` to the player's reti).
  B. game scenes: control scripts in the game (the harness, guards and patches as tests/m4_game.py runs them), in the
     silent mode (as every harness test: snd_playing 0, every request starts) and in the live mode (SND_MODE poked to 3
     at level_ready: every check_sound_playing, play_next_sound's too, asks the player's stream, the queue and priorities
     audible end to end; M7 step 5: the release's hybrid mode 1 decides play_next_sound by the ticks model instead,
     which tests/m4_test.py checks against kidsim, mode 2); the streaming
     scene starts a long piece (the ending, 124.7 s, as id 41 in a test bank) at a tick of a script with room changes,
     so the ring is refilled once a tick (play_next_sound) and must survive the full room draws (the largest gap
     between two refills is printed).
Renders build/sound/scene_<script>_<mode>.wav from the emulator's PSG states (tools/sndsim.py render).
usage: m7_sound.py [--quick] [script.txt ...]"""
import os, subprocess, sys, tempfile, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools')); sys.path.insert(0, os.path.join(ROOT, 'tests'))
from emu import Emu
from m3_test import syms, write_pack
from m4_game import setup, SCRIPT, SCRIPT_PTR, LEVEL_ADDR
from m4_test import encode
import kidsim, sndsim, sndconv
BUILD = os.path.join(ROOT, 'build')
FRAMES = 0x0800; TICKS = 0x0872
SCENES = ['m6_scripts/fight_killpush.txt', 'm6_scripts/level2_drop.txt', 'm5_scripts/level13_jaffar.txt',
          'm4_scripts/walk_level1.txt']
FAILS = []
COST_FRAMES = 400

def check(what, ok, detail=''):
    print('  %-78s %s%s' % (what, 'ok' if ok else 'FAILED', '' if ok else '  ' + str(detail)))
    if not ok: FAILS.append(what)

def regs(e): return e.call('get_registers')
def frames(e):
    b = e.mem(FRAMES, 2); return b[0] | (b[1] << 8)
def psg(e): return sndsim.emu_state(e.call('get_periph_sn76489'))
def cyc(e): return e.call('get_raster_pos')['total_cycles']

class Tracker:
    """drives a sndsim.Sim from the Z80's events and compares the PSG state where the Z80 writes it.
    The PSG's registers change only through writes, and the game writes it only in the player (snd_isr: the envelope
    steps and the group; psg_mute in snd_halt and at a stream's end), so the state is sampled at the end of every
    active interrupt (spi_done), and sndsim, stepped to the same interrupt (FRAMES), must have been active there too;
    snd_halt, the fills and the decisions are checked where they happen. Between those points the state is constant."""
    def __init__(self, e, S, mode, bank):
        self.e, self.S, self.mode = e, S, mode
        self.sim = sndsim.Sim(mode, bank)
        self.samples = 0; self.bad = 0; self.first = []; self.states = []
        self.decisions = 0; self.bad_dec = 0; self.expect = None; self.starts = {}; self.writes = []
        self.pending = None; self.loaded = False; self.armed_at = {}; self.lengths = []; self.cur = None
        self.underruns = 0; self.fill_frames = []; self.gap = 0; self.last_fill = None; self.wraps = {}
        f = frames(e); st = psg(e)
        assert e.mem(S['SP_WAIT'], 1)[0] == 0
        self.sim.frame = f; self.sim.p.psg.load(st); self.states.append((f, st)); self.f0 = f
    def bps(self):
        S = self.S
        self.addr = {S['spi_done']: 'act', S['snh_di']: 'halt', S['snd_arm']: 'arm', S['snd_start']: 'start',
                     S['sf_x']: 'fill', S['snd_playing']: 'playing', S['snn_x']: 'decided'}
        if self.mode == 'live': self.addr[S['snp_rd']] = 'playing'; del self.addr[S['snd_playing']]
        for a in self.addr: self.e.call('bp_add', addr=a)
    def sync(self, f):
        while self.sim.frame < f:
            was = self.sim.p.playing()
            try:
                self.writes.append(self.sim.isr())
            except sndsim.Underrun:
                self.underruns += 1; self.bad_one(self.sim.frame, 'underrun'); self.sim.p.wait = 0
            if was and not self.sim.p.playing() and self.cur is not None:
                self.lengths.append((self.cur[0], self.sim.frame - self.cur[1])); self.cur = None
    def bad_one(self, *what):
        self.bad += 1
        if len(self.first) < 5: self.first.append(what)
    def event(self, pc):
        e, S, sim = self.e, self.S, self.sim
        what = self.addr.get(pc)
        if what is None: return None
        f = frames(e); self.sync(f)
        if what == 'act':
            st = psg(e); self.samples += 1; self.states.append((f, st))
            if sim.p.last not in ('step', 'end'): self.bad_one(f, 'z80 player active, sndsim', sim.p.last)
            if st != sim.p.psg.state():
                self.bad_one(f, 'emu', st, 'sndsim', sim.p.psg.state())
                sim.p.psg.load(st)                       # (resynchronise: count each difference once)
        elif what == 'start': self.pending = regs(e)['AF'] >> 8; self.loaded = False
        elif what == 'halt':
            if self.cur is not None and sim.p.loops: self.wraps[self.cur[0]] = self.wraps.get(self.cur[0], 0) + sim.p.loops
            sim.p.halt(); self.cur = None; self.states.append((f, sim.p.psg.state()))
        elif what == 'fill':
            if self.pending is not None and not self.loaded:
                sim.p.load(self.pending, fill=False); self.loaded = True
            # the bytes copied: the ring's write position moved (254 places); MF_LEFT after a loop command (sf_x comes
            # before snd_fill wraps to the loop point, then again for the loop point's bytes) is 0 while the model wrapped
            n = (e.mem(S['MF_W'], 1)[0] - sim.p.w) % 254
            m = e.mem(S['MF_LEFT'], 2); left = m[0] | (m[1] << 8)
            try:
                sim.fill(n)
                if not (left == sim.p.left or (left == 0 and sim.p.loop is not None)): self.bad_one(f, 'fill left', left, sim.p.left)
            except AssertionError as x:
                self.bad_one(f, 'fill', x.args)
        elif what == 'arm':
            sid = self.pending; self.pending = None
            if not self.loaded: sim.p.load(sid, fill=False)
            sim.p.arm(); self.starts[sid] = self.starts.get(sid, 0) + 1; self.cur = (sid, f)
        elif what == 'playing':
            if self.last_fill is not None and sim.p.playing() and sim.p.left: self.gap = max(self.gap, f - self.last_fill)
            self.last_fill = f
            if self.inject and frames_tick(e) == self.inject[0] and not self.injected:
                e.call('mem_write', addr=S['SND_NEXT'], data_hex='%02x' % self.inject[1]); self.injected = True
            m = e.mem(S['SND'], 3)                     # SND_NEXT, SND_CUR, SND_INT15
            q = -1 if m[0] == 0xFF else m[0]; cur = m[1]; p = sim.playing()
            self.expect = (q, p, sim.decide(q, p, cur, m[2]))
        elif what == 'decided':
            r = regs(e); b, c, ee = (r['BC'] >> 8) & 255, r['BC'] & 255, r['DE'] & 255
            got = (-1 if c == 0xFF else c, ee, -1 if b == 0xFF else b)
            self.decisions += 1
            if got != self.expect:
                self.bad_dec += 1
                if len(self.first) < 5: self.first.append((f, 'decision z80', got, 'sndsim', self.expect))
        return what
    inject = None; injected = False
    def finish(self):
        """the end of the run: sndsim stepped to the emulator's frame, the states compared once more"""
        f = frames(self.e); self.sync(f); st = psg(self.e)
        if st != self.sim.p.psg.state(): self.bad_one(f, 'end: emu', st, 'sndsim', self.sim.p.psg.state())
        self.states.append((f, st)); return f
    def per_frame(self, f1):
        """the PSG state per frame from f0 to f1 (constant between the samples)"""
        out, i, cur = [], 0, self.states[0][1]
        for f in range(self.f0, f1):
            while i < len(self.states) and self.states[i][0] <= f: cur = self.states[i][1]; i += 1
            out.append(cur)
        return out

def frames_tick(e):
    b = e.mem(TICKS, 2); return b[0] | (b[1] << 8)

def run_until(e, tr, stop):
    """run, handling the breakpoints, until stop() is true (asked after each sound decision: one per tick)"""
    while True:
        r = e.run(1000)
        if r['stopped_by'] != 'breakpoint': continue
        if tr.event(regs(e)['PC']) == 'decided' and stop(): return

DRIVER = """
                org     0xa000
drv:            ld      sp, 0xfe00
                ei
                ld      hl, list
d1:             ld      a, (hl)
                inc     hl
                ld      b, (hl)
                inc     hl
                cp      0xff
                jr      z, done
                push    hl
                push    bc
                cp      0xfd
                jr      z, d_go
                cp      0xfe
                jr      z, d_halt
                call    snd_start
                jr      d_go
d_halt:         call    snd_halt
d_go:           pop     bc
                ld      a, b
                or      a
                jr      z, d_end
d_w:            halt
                push    bc
                call    snd_fill
                pop     bc
                djnz    d_w
                jr      d_next
d_end:          halt
                call    snd_fill
                ld      a, (SP_WAIT)
                or      a
                jr      nz, d_end
                halt
d_next:         pop     hl
                jr      d1
done:           halt
                jr      done
list:
"""

def driver_bin(S, items):
    """the driver assembled against the game's symbols; items [(id or 0xFE = snd_halt, frames to wait (0: until the
    stream ends))]; a wait above 255 frames continues in 0xFD items (wait only). Returns (bytes, its symbols)."""
    d = tempfile.mkdtemp()
    out = []
    for a, n in items:
        out.append((a, min(n, 255))); n -= min(n, 255)
        while n > 0: out.append((0xFD, min(n, 255))); n -= min(n, 255)
    src = ''.join('%-15s equ 0x%04x\n' % (k, S[k]) for k in ('snd_start', 'snd_halt', 'snd_fill', 'SP_WAIT'))
    src += DRIVER + ''.join('                db      %d, %d\n' % it for it in out) + '                db      0xff, 0xff\n'
    open(os.path.join(d, 'drv.asm'), 'w').write(src)
    subprocess.run(['pasmo', '--bin', os.path.join(d, 'drv.asm'), os.path.join(d, 'drv.bin'), os.path.join(d, 'drv.sym')],
                   check=True, stdout=subprocess.DEVNULL)
    return open(os.path.join(d, 'drv.bin'), 'rb').read(), syms(os.path.join(d, 'drv.sym'))

def drive(e, bank, items, test_bank=None):
    """the driver program over the items with the tracker (test_bank: written to the bank's place first)"""
    S = setup(e, 1)
    if test_bank is not None: write_pack(e, test_bank, S['SB_PAGE'], S['SB_ADDR'])
    e.call('bp_clear'); e.call('bp_add', addr=S['level_ready']); e.run(400)
    drv, D = driver_bin(S, items)
    e.call('mem_write', addr=0xA000, data_hex=drv.hex())
    e.call('set_register', reg='PC', value=0xA000)
    e.call('bp_clear')
    tr = Tracker(e, S, 'silent', bank); tr.bps(); e.call('bp_add', addr=D['done'])
    while True:
        r = e.run(1000)
        if r['stopped_by'] != 'breakpoint': continue
        pc = regs(e)['PC']
        if pc == D['done']: break
        tr.event(pc)
    return tr, tr.finish()

def check_lengths(tr, what):
    """every music piece played from its start to its end: the frames from its first to its end group = the MIDI
    length (s x 50) within 1 frame"""
    import midi2psg
    bad = []; n = 0
    for sid, L in tr.lengths:
        if sid not in sndconv.MUSIC: continue
        n += 1; want = midi2psg.length(sid) / 0.02
        if abs((L - 1) - want) > 1: bad.append((sid, L - 1, round(want, 2)))
    check('A: %s: the %d music pieces last their MIDI length within 1 frame' % (what, n), not bad and n, bad)

def part_a(e, bank, quick):
    print('A. direct: every stream of the bank, overlaps, a stop')
    ids = sorted(bank)
    if quick: ids = [i for i in ids if i not in sndconv.MUSIC] + [24, 41]
    items = [(i, 0) for i in ids]
    items += [(2, 5), (18, 3), (0xFE, 4), (41, 30), (47, 2), (0xFE, 2), (31, 3), (12, 0), (39, 40), (0xFE, 3)]
    S = setup(e, 1)
    e.call('bp_clear'); e.call('bp_add', addr=S['level_ready']); e.run(400)
    drv, D = driver_bin(S, items)
    e.call('mem_write', addr=0xA000, data_hex=drv.hex())
    e.call('set_register', reg='PC', value=0xA000)
    e.call('bp_clear')
    # the ISR's cost: COST_FRAMES interrupts with breakpoints at isr and the player's reti (the first effects, then
    # music 24 from frame ~300)
    cost = {'idle': [], 'playing': []}; t0 = time.time()
    e.call('bp_add', addr=S['isr']); e.call('bp_add', addr=S['spi_reti'])
    t_isr = None; was = None; n = 0
    while n < COST_FRAMES:
        r = e.run(1000)
        if r['stopped_by'] != 'breakpoint': continue
        pc = regs(e)['PC']
        if pc == S['isr']:
            t_isr = cyc(e); was = e.mem(S['SP_WAIT'], 1)[0]
        elif pc == S['spi_reti'] and t_isr is not None:
            cost['playing' if was else 'idle'].append(cyc(e) - t_isr); n += 1
    print('  ISR cost (cycles from isr to the player\'s reti, %d interrupts): idle %d-%d T (%d), playing %d-%d T, avg %.0f (%d)' % (
        n, min(cost['idle']), max(cost['idle']), len(cost['idle']), min(cost['playing']), max(cost['playing']),
        sum(cost['playing']) / len(cost['playing']), len(cost['playing'])))
    # the comparison: the driver again from the start
    e.call('bp_clear')
    tr, f1 = drive(e, bank, items)
    wr = [w for w in tr.writes if w]
    print('  PSG bytes written per interrupt: max %d, %d interrupts with writes, avg %.1f there (sndsim)' % (max(wr), len(wr), sum(wr) / len(wr)))
    sndsim.write_wav(os.path.join(BUILD, 'sound', 'driver_all_streams.wav'), sndsim.render(tr.per_frame(f1)))
    print('  %d samples (active interrupts) over %d frames, %d streams started, %d fills, %.0f s' % (
        tr.samples, f1 - tr.f0, sum(tr.starts.values()), len(tr.sim.p.fills), time.time() - t0))
    check('A: the PSG state and the player\'s steps equal sndsim\'s, no underrun (%d frames)' % (f1 - tr.f0), tr.bad == 0, tr.first)
    want = set(ids)
    check('A: every stream of the bank was started (%d ids)' % len(want), want <= set(tr.starts), sorted(want - set(tr.starts)))
    check_lengths(tr, 'the game\'s bank')
    if not quick:                       # the presentation's pieces (M7 step 11: the Master System pieces, tools/presbank.py,
        import presbank                 # the looping ones through the loop command) through the same player, one at a time
        banks = {fn: sndsim.load_bank(os.path.join(BUILD, 'assets', fn), 0) for fn, *_ in presbank.BANKS}
        done = set()
        for fn, ent, order, ids, no_eff in presbank.BANKS:
            for sid, name in sorted(ids.items()):
                if name in done: continue
                done.add(name); pres = banks[fn]; n = presbank.FRAMES[name]; loop = pres.loops.get(sid)
                tb = sndconv.make_bank({sid: pres[sid]}, {sid: loop} if loop is not None else None); t0 = time.time()
                items = [(sid, n + (n - loop) // 2 + 20 if loop is not None else 0), (0xFE, 4)]   # (a looping piece: 1.5 loops, then halted)
                tr, f1 = drive(e, sndsim.load_bank(tb), items, tb)
                print('  presentation %s (id %d, %s): %d samples over %d frames, %d fills, %d loops, %.0f s' % (
                    name, sid, 'loops at frame %d' % loop if loop is not None else 'one-shot', tr.samples, f1 - tr.f0, len(tr.sim.p.fills), tr.wraps.get(sid, 0), time.time() - t0))
                check('A: presentation %s: PSG state per frame equals sndsim\'s, no underrun' % name, tr.bad == 0, tr.first)
                if loop is not None: check('A: %s looped once through the loop command (the model wrapped %s)' % (name, tr.wraps.get(sid)), tr.wraps.get(sid) == 1, tr.wraps)
                else:
                    L = [x for s_, x in tr.lengths if s_ == sid]
                    check('A: %s lasts its SMS length %d frames' % (name, n), L and L[0] - 1 == n, L)
    return tr, cost

def part_b(e, bank, sp, mode, max_ticks=None, inject=None, test_bank=None, tag=''):
    """inject (tick, id): the id is queued (SND_NEXT) at that tick's play_next_sound; test_bank: written to the
    bank's place (bank = its streams)"""
    moves, patches = kidsim.read_script(sp); keys = kidsim.read_keys(sp)
    lv = kidsim.script_level(sp); o = kidsim.script_opts(sp)
    S = setup(e, lv, opts=o)
    if test_bank is not None: write_pack(e, test_bank, S['SB_PAGE'], S['SB_ADDR'])
    write_pack(e, encode(moves, keys), 5, SCRIPT)
    e.call('mem_write', addr=SCRIPT_PTR, data_hex='%02x%02x' % (SCRIPT & 255, SCRIPT >> 8))
    e.call('bp_clear'); e.call('bp_add', addr=S['level_ready']); r = e.run(400); assert r['stopped_by'] == 'breakpoint'
    if mode == 'live': e.call('mem_write', addr=S['SND_MODE'], data_hex='03')     # (sound.asm: live = the player)
    e.call('bp_clear'); e.call('bp_add', addr=S['guards_off_chk']); r = e.run(400); assert r['stopped_by'] == 'breakpoint'
    for (rm, p, t, m) in patches:
        e.call('mem_write', addr=LEVEL_ADDR + (rm - 1) * 30 + p, data_hex='%02x' % t)
        e.call('mem_write', addr=LEVEL_ADDR + 720 + (rm - 1) * 30 + p, data_hex='%02x' % m)
    e.call('bp_clear')
    tr = Tracker(e, S, mode, bank); tr.bps(); tr.inject = inject
    n = min(len(moves), max_ticks or len(moves))
    def stop():
        b = e.mem(TICKS, 2); return (b[0] | (b[1] << 8)) >= n
    t0 = time.time()
    run_until(e, tr, stop)
    f1 = tr.finish()
    # (the next setup reloads the program after 3 more frames: a long player frame could leave the CPU inside the ISR
    # without its RETI, and the PIO would never interrupt again; the player stopped, the ISR is short)
    e.call('mem_write', addr=S['SP_WAIT'], data_hex='00')
    name = os.path.basename(sp)[:-4] + tag
    sndsim.write_wav(os.path.join(BUILD, 'sound', 'scene_%s_%s.wav' % (name, mode)), sndsim.render(tr.per_frame(f1)))
    started = ' '.join('%d:%d' % kv for kv in sorted(tr.starts.items()))
    print('  %-20s %-6s %4d ticks %5d frames, %4d samples, %3d decisions, started %s  (%.0f s)' % (name, mode, n, f1 - tr.f0, tr.samples, tr.decisions,
                                                                                    started, time.time() - t0))
    if inject:
        print('  %-20s streaming: %d fills, the longest time between two refills %d frames, %d underruns' % (
            name, len(tr.sim.p.fills), tr.gap, tr.underruns))
    check('B: %s %s: PSG state per frame and the decisions equal sndsim\'s%s' % (name, mode, ', no underrun' if inject else ''),
          tr.bad == 0 and tr.bad_dec == 0 and (not inject or tr.injected), tr.first)
    return tr

def main():
    args = sys.argv[1:]; quick = '--quick' in args
    scenes = [a for a in args if a.endswith('.txt')] or [os.path.join(ROOT, 'tests', s) for s in SCENES]
    bank = sndsim.load_bank()
    S = syms(os.path.join(BUILD, 'm4game.sym'))
    check('the bank\'s place in the RAM disk: psg.asm SB_PAGE/SB_ADDR/MUS_BUF = sndconv\'s',
          (S['SB_PAGE'], S['SB_ADDR'], S['MUS_BUF']) == (sndconv.SB_PAGE, sndconv.SB_ADDR, sndconv.MUS_BUF))
    for a in [S[k] for k in ('snd_isr', 'psg_mute', 'sp_rd', 'spi_reti', 'SP_WAIT', 'ENV', 'MUS_BUF')] + [S['MUS_BUF'] + 253, S['ENV'] + 11]:
        assert not (0x1000 <= a < 0x2000 or 0x8000 <= a < 0xA000), hex(a)
    check('the ISR player\'s code and data are outside 0x1000-0x1FFF and 0x8000-0x9FFF', True)
    with Emu() as e:
        part_a(e, bank, quick)
        print('B. game scenes')
        for sp in scenes:
            for mode in ('silent', 'live'):
                part_b(e, bank, sp, mode, 150 if quick else None)
        if not args or quick:
            # streaming through room changes: the level end music (41, 306 bytes) and the ending (5,106 bytes, as id 41
            # in a test bank: 124.7 s at 41 bytes/s) started at tick 80 of the walkthrough, before its full room draws
            # (tick 89: the longest tick, ~106 frames, tools/perfcheck.py; live mode: music is never interrupted)
            rr = os.path.join(ROOT, 'tests', 'm4_scripts', 'walk_level1.txt')
            part_b(e, bank, rr, 'live', None, inject=(80, 41), tag='_41')
            # (the long streaming piece: Jaffar's piece of the presentation (5,331 bytes, bank B's id 50), looping)
            pres = sndsim.load_bank(os.path.join(BUILD, 'assets', 'sound_pres_b.bin'), 0)
            tb = dict(bank); tb[41] = pres[50]; tbb = sndconv.make_bank(tb, {41: pres.loops[50]})
            tr = part_b(e, sndsim.load_bank(tbb), rr, 'live', 400, inject=(80, 41), test_bank=tbb, tag='_loop')
            check('B: the looping piece wrapped through the room draws (%d loops)' % tr.sim.p.loops, tr.sim.p.loops >= 1, tr.sim.p.loops)
    print('FAILED: %s' % FAILS if FAILS else 'all ok')
    sys.exit(1 if FAILS else 0)

if __name__ == '__main__': main()
