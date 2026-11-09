#!/usr/bin/env python3
"""M7 step 3: the Python model of the PSG player (src/m4/psg.asm) and of the SN76489 as mz800emu emulates it, the
sound model's request rules (src/m4/sound.asm, tools/kidsim.py) on top of it, and WAV rendering for listening.

  Psg        the chip's registers: per channel the attenuation, the tone divider (10 bits; a latch byte sets the low
             4 bits, which take effect with the data byte, as in mz800emu psg.c), the noise rate and type
  Player     psg.asm: halt (stop + mute), start(id) (= halt, copy the stream from the bank, arm), isr() (one frame),
             fade() (PRES's music fade-out: mf_start; MFADE_PER frames per attenuation step, silent and stopped after
             MFADE_FRAMES)
  Sim        play(id) / next() / stop() (SDLPoP play_sound / play_next_sound / stop_sounds, the priorities and
             interruptible flags of kidsim) in the 'silent' (nothing ever plays) or 'live' (the player's stream)
             mode, frame by frame: run(script) gives the PSG state after every frame
  render     PSG states per frame -> samples (the emulator's step algorithm at CPU/16, box-filtered to 44.1 kHz)

Script lines (run_script, the CLI): `<frame> play <id>`, `<frame> next`, `<frame> stop`, `<frame> start <id>` (the
player directly); the events of frame f happen after the f-th interrupt, before the next one.
usage: sndsim.py [--wav] [--script FILE [--live] [--frames N]] [--sdlpop SCRIPT.txt]
  --wav       build/sound/: every effect and music placeholder as the PSG plays it (*_psg.wav), the DOS originals
              (*_pcspk.wav: the speaker notes; *_digi.wav: the digitized effects SDLPoP plays by default) and the
              A/B reels ab_effects.wav (per effect: digitized original, speaker original, PSG) and all_effects_psg.wav
  --script    print the PSG state per frame for a script of events
  --sdlpop    record the original: SDLPoP (external/SDLPoP/prince with the pop800 hooks, as tools/oracle.py runs it)
              plays the control script with SDL_AUDIODRIVER=disk (real time, digitized effects + MIDI music) ->
              build/sound/scene_<script>_sdlpop.wav, to compare with tests/m7_sound.py's scene_<script>_*.wav"""
import os, struct, sys, wave
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import sndconv as SC
BANK = os.path.join(HERE, '..', 'build', 'assets', 'sound.bin')
OUTDIR = os.path.join(HERE, '..', 'build', 'sound')
PSG_CLK = SC.CPU / 16.0
RATE = 44100
MFADE_PER = 3                       # psg.asm (PRES): the fade's frames per attenuation step
MFADE_FRAMES = 15 * MFADE_PER       # 45 frames = 0.9 s = 54 SDLPoP ticks
MFADE_TICKS = MFADE_FRAMES * 6 // 5

# the sound model's tables (tools/kidsim.py: SDLPoP sound_prio_table, sound_interruptible, PoP 1.3 values)
import kidsim
PRIO, INTERRUPTIBLE, MISSING = kidsim.SOUND_PRIO, kidsim.SOUND_INTERRUPTIBLE, kidsim.SOUND_MISSING


class Psg:
    def __init__(self):
        self.att = [15] * 4; self.tone = [0] * 3; self.lo = [0] * 3
        self.ndiv = 0; self.ntype = 0; self.latch = 3; self.latch_att = True
    def write(self, v):
        if v & 0x80:
            self.latch = (v >> 5) & 3; self.latch_att = bool(v & 0x10)
            if self.latch_att: self.att[self.latch] = v & 15
            elif self.latch < 3: self.lo[self.latch] = v & 15
            else: self.ndiv = v & 3; self.ntype = (v >> 2) & 1
        else:
            c = self.latch
            if self.latch_att: self.att[c] = v & 15
            elif c < 3: self.tone[c] = ((v << 4) | self.lo[c]) & 0x3FF
            else: self.ndiv = v & 3; self.ntype = (v >> 2) & 1
    def state(self):
        """(att0, tone0, att1, tone1, att2, tone2, att3, noise rate, noise type) as get_periph_sn76489 reports them"""
        return (self.att[0], self.tone[0], self.att[1], self.tone[1], self.att[2], self.tone[2], self.att[3], self.ndiv,
                self.ntype)
    def load(self, st):
        self.att = [st[0], st[2], st[4], st[6]]; self.tone = [st[1], st[3], st[5]]; self.ndiv, self.ntype = st[7], st[8]

NOISE_DIV = {'div_16': 0, 'div_32': 1, 'div_64': 2, 'tone2_controlled': 3}
def emu_state(d):
    """Psg.state()'s tuple from mz800emu's get_periph_sn76489 answer"""
    ch = d['psg0']['channels']
    return (ch[0]['attenuation'], ch[0]['tone_divider'], ch[1]['attenuation'], ch[1]['tone_divider'],
            ch[2]['attenuation'], ch[2]['tone_divider'], ch[3]['attenuation'], NOISE_DIV[ch[3]['noise_div_type']],
            1 if ch[3]['noise_type'] == 'white' else 0)


class Bank(dict):
    """{id: stream bytes}; loops: {id: the loop point as a byte offset into the stream} for the streams that end
    with the loop command (M7 step 11: psg.asm snd_fill; tools/presbank.py writes them)"""
    def __init__(self, streams=(), loops=None):
        super().__init__(streams); self.loops = dict(loops or {})

def load_bank(path=BANK, base=SC.SB_ADDR):
    """Bank of a bank file (sndconv's layout; the presentation's banks have base 0): a stream whose last byte is not
    the end 0x00 is followed by 0xE8 lo hi, the loop command (its loop point hi:lo as a bank address)"""
    b = open(path, 'rb').read() if isinstance(path, str) else path; ent = Bank()
    for sid in range(SC.NIDS):
        src, n = struct.unpack_from('<HH', b, sid * 4)
        if not n: continue
        s = b[src - base:src - base + n]; ent[sid] = s
        if s[-1] != 0:
            t = src - base + n
            assert b[t] == 0xE8, ('a stream without an end needs the loop command', sid)
            lp = struct.unpack_from('<H', b, t + 1)[0] - src
            assert 0 <= lp < n, (sid, lp)
            ent.loops[sid] = lp
    return ent


class Underrun(Exception): pass

class Player:
    """src/m4/psg.asm: SP_WAIT (frames until the next group, 0 = no stream), the read position SP_PTR in the ring
    0xFE02-0xFEFF, the refill state (MF_LEFT bytes of the stream not yet copied, MF_W the write position), the four
    envelopes (attenuation, counter, period). fill() is snd_fill (main code: as many bytes as the ring has room for);
    reading a byte the fill has not written yet raises Underrun."""
    LO, HI = SC.MUS_BUF & 0xFF, 0x100
    def __init__(self, bank=None, psg=None):
        self.bank = bank if bank is not None else load_bank(); self.psg = psg or Psg()
        self.wait = 0; self.r = self.LO; self.w = self.LO; self.left = 0; self.src = b''; self.pos = 0
        self.ring = {}; self.avail = 0; self.env = [[15, 0, 0] for _ in range(4)]
        self.writes = 0; self.last = None; self.fills = []; self.loop = None; self.loops = 0
        self.mf_cnt = 0; self.mf_off = 0
    def fade(self, delay=0):
        """mf_start / mf_delay: the fade-out starts after `delay` interrupts (PRES): every MFADE_PER interrupts the
        offset added to every attenuation written goes up by one (the four channels written again); at 15 the stream
        stops as at its end"""
        self.mf_off = 0; self.mf_cnt = MFADE_PER + delay
    def adj(self, v):
        """mf_att: an attenuation latch byte with the fade's offset (at most 15)"""
        return (v & 0xF0) | min(15, (v & 15) + self.mf_off)
    def mute(self):
        for v in (0x9F, 0xBF, 0xDF, 0xFF): self.psg.write(v)
    def halt(self):
        self.wait = 0; self.left = 0; self.mf_cnt = self.mf_off = 0; self.mute()
    def free(self):
        """room in the ring as snd_fill computes it (253 at most)"""
        return (self.r - self.w - 1) % 256 - (2 if self.r <= self.w else 0)
    def fill(self, n=None):
        """snd_fill: copy min(room, left) bytes (or n: the Z80's count, checked against the room); a looping stream
        goes on at its loop point when its end is reached (snd_fill's loop command: the copying continues in the same
        call, so `left` never stays 0); returns the count"""
        if not self.left: return 0
        m = self.free() if self.loop is not None else min(self.free(), self.left)
        if n is None: n = m
        assert n <= m, ('fill', n, m)
        for i in range(n):
            self.ring[self.w] = self.src[self.pos]; self.pos += 1
            self.w += 1
            if self.w == self.HI: self.w = self.LO
            self.left -= 1
            if not self.left and self.loop is not None:
                self.pos = self.loop; self.left = len(self.src) - self.loop; self.loops += 1
        self.avail += n; self.fills.append(n)
        return n
    def load(self, sid, fill=True):
        """snd_start's part after the halt: the index entry, the envelopes off, the ring empty, the first fill"""
        if sid not in self.bank: return False
        self.src = self.bank[sid]; self.pos = 0; self.left = len(self.src)
        self.loop = getattr(self.bank, 'loops', {}).get(sid); self.loops = 0
        self.env = [[15, 0, 0] for _ in range(4)]
        self.r = self.w = self.LO; self.avail = 0; self.ring = {}
        if fill: self.fill()
        return True
    def arm(self): self.wait = 1
    def start(self, sid):
        self.halt()
        if self.load(sid): self.arm()
    def playing(self): return self.wait != 0
    def rd(self):
        if self.avail <= 0: raise Underrun()
        v = self.ring[self.r]; self.avail -= 1
        self.r += 1
        if self.r == self.HI: self.r = self.LO
        return v
    def out(self, v): self.psg.write(v); self.writes += 1
    def isr(self):
        """one interrupt; returns the number of PSG bytes written"""
        self.writes = 0; self.last = None
        if not self.wait: return 0
        if self.mf_cnt:                                 # the fade (PRES)
            self.mf_cnt -= 1
            if not self.mf_cnt:
                if self.mf_off + 1 == 15:               # silent: the stream stops as at its end
                    self.mf_off = 0; self.wait = 0; self.mute(); self.writes += 4; self.last = 'fade'
                    return self.writes
                self.mf_off += 1; self.mf_cnt = MFADE_PER
                for c, e in enumerate(self.env): self.out(self.adj(0x90 | (c << 5) | e[0]))
        for c, e in enumerate(self.env):                # the envelopes
            if e[0] < 15:
                e[1] = (e[1] - 1) & 255
                if e[1] == 0:
                    e[0] += 1; e[1] = e[2]; self.out(self.adj(0x90 | (c << 5) | e[0]))
        self.last = 'step'
        self.wait -= 1
        if self.wait: return self.writes
        while True:
            b = self.rd()
            if b == 0:
                self.wait = 0; self.mute(); self.writes += 4; self.last = 'end'; return self.writes
            if b < 0x80:
                self.wait = b; return self.writes
            self.out(self.adj(b) if b & 0x10 else b)
            if not b & 0x10:
                if b < 0xE0: self.out(self.rd())        # a tone latch's data byte
            else:
                c = (b >> 5) & 3; self.env[c][0] = b & 15
                if b & 15 != 15:
                    p = self.rd(); self.env[c][1] = p; self.env[c][2] = p


class Sim:
    """the request side + the player: mode 'silent' (snd_playing 0) or 'live' (the player's stream)"""
    def __init__(self, mode='silent', bank=None):
        self.mode = mode; self.p = Player(bank); self.next_sound = -1; self.current = -1; self.int15 = 0
        self.frame = 0; self.lines = []
    def playing(self): return 1 if self.mode == 'live' and self.p.playing() else 0
    def play(self, sid):
        if self.next_sound < 0 or PRIO[sid] <= PRIO[self.next_sound]:
            if sid in MISSING: return
            self.next_sound = sid
    def decide(self, q, playing, current, int15):
        """play_next_sound's rule: the id started (-1 none)"""
        if q < 0: return -1
        if not playing: return q
        intr = INTERRUPTIBLE[current] or (current == 15 and int15)
        return q if intr and PRIO[q] <= PRIO[current] else -1
    def next(self):
        q = self.next_sound; p = self.playing(); st = self.decide(q, p, self.current, self.int15)
        if st >= 0: self.current = st; self.p.start(st)
        self.next_sound = -1
        self.lines.append((self.frame, q, st, p))
        return st
    def stop(self): self.p.halt()
    def fill(self, n=None): return self.p.fill(n)
    def isr(self): self.frame += 1; return self.p.isr()


def run_script(events, nframes, mode='silent', start_state=None):
    """events [(frame, op, arg)] -> [PSG state after the events of frame f, f = 0..nframes-1] (and the Sim)"""
    s = Sim(mode)
    if start_state: s.p.psg.load(start_state)
    ev = sorted(events, key=lambda e: e[0]); i = 0; out = []
    for f in range(nframes):
        while i < len(ev) and ev[i][0] == f:
            _, op, arg = ev[i]; i += 1
            if op == 'play': s.play(arg)
            elif op == 'next': s.next()
            elif op == 'stop': s.stop()
            elif op == 'start': s.p.start(arg)
        out.append(s.p.psg.state())
        s.isr(); s.fill()                                # (a refill after every frame)
    return out, s


# ---------------------------------------------------------------- rendering
_LFSR = {}
def lfsr(white):
    """the noise output bit after each shift (mz800emu: 16-bit register from 1 << 15; white: feedback bits 0 ^ 3)"""
    if white in _LFSR: return _LFSR[white]
    sr = 1 << 15; out = []
    n = 65535 if white else 16
    for _ in range(n):
        b0 = sr & 1
        if white: sr = (sr >> 1) | ((b0 ^ ((sr >> 3) & 1)) << 15)
        else: sr = (sr >> 1) | (b0 << 15)
        out.append(sr & 1)
    _LFSR[white] = np.array(out, np.float32)
    return _LFSR[white]

def amp(att): return 0.0 if att >= 15 else 10 ** (-2.0 * att / 20.0)

def render(states, rate=RATE):
    """PSG states (Psg.state() tuples), one per frame of 1/50 s -> float samples in [-1, 1]"""
    steps_per_frame = PSG_CLK / 50.0
    out = []; step0 = 0.0; nshift = 0.0; noise_phase = 0.0
    tphase = [0.0, 0.0, 0.0]
    for st in states:
        s0 = step0; s1 = step0 + steps_per_frame
        n = int(round(s1 * rate / PSG_CLK)) - int(round(s0 * rate / PSG_CLK))
        if n <= 0: step0 = s1; continue
        k = 8                                       # sub-samples per output sample (box filter)
        t = (np.arange(n * k, dtype=np.float64) + 0.5) / (n * k) * steps_per_frame        # PSG steps into the frame
        mix = np.zeros(n * k, np.float32)
        att = [st[0], st[2], st[4], st[6]]; tone = [st[1], st[3], st[5]]
        for c in range(3):
            N = tone[c]
            ph = tphase[c] + t
            if att[c] < 15 and N >= 2:
                mix += amp(att[c]) * (1.0 - 2.0 * (np.floor(ph / N) % 2))
            tphase[c] = (tphase[c] + steps_per_frame) % (2 * max(N, 1))
        ndiv, white = st[7], st[8]
        timer = (tone[2] if ndiv == 3 else (16 << ndiv))
        if att[3] < 15 and timer >= 2:
            seq = lfsr(white)
            idx = (nshift + np.floor((noise_phase + t) / timer)).astype(np.int64) % len(seq)
            mix += amp(att[3]) * (2.0 * seq[idx] - 1.0)
        if timer >= 1:
            total = noise_phase + steps_per_frame
            nshift += np.floor(total / max(timer, 1)); noise_phase = total % max(timer, 1)
        out.append(mix.reshape(n, k).mean(axis=1) / 4.0)
        step0 = s1
    return np.concatenate(out) if out else np.zeros(0, np.float32)

def speaker(sid, rate=RATE):
    """the DOS original on the PC speaker (SDLPoP speaker_callback: square waves, rests silent)"""
    r = SC.pcspk(sid)
    if r is None: return None
    tempo, notes = r; out = []; ph = 0.0
    for f, l in notes:
        n = int(round(l / float(tempo) * rate))
        if f <= 1 or f > SC.INAUDIBLE: out.append(np.zeros(n, np.float32)); continue
        t = ph + np.arange(n) * f / rate
        out.append(np.where((t % 1.0) < 0.5, 0.25, -0.25).astype(np.float32)); ph = (ph + n * f / rate) % 1.0
    return np.concatenate(out) if out else np.zeros(0, np.float32)

def digitized(sid, rate=RATE):
    r = SC.digi(sid)
    if r is None: return None
    sr, s = r
    t = np.arange(int(len(s) * rate / sr)) * sr / float(rate)
    return (np.interp(t, np.arange(len(s)), s) / 128.0 * 0.5).astype(np.float32)

def write_wav(path, x, rate=RATE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    x = np.clip(x, -1, 1); d = (x * 32000).astype('<i2').tobytes()
    with wave.open(path, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(d)

def sound_states(sid, bank=None, frames=None):
    """the PSG state per frame while sound sid plays from a muted PSG (until the player stops, or frames of a
    looping stream)"""
    s = Sim('live', bank); s.p.start(sid); out = []
    while frames is None or len(out) < frames:
        s.isr(); s.fill()
        if not s.p.playing(): break
        out.append(s.p.psg.state())
    return out

def consumed(stream, loop=None, frames=None):
    """bytes of the stream read through each interrupt (the player alone, refilled after every frame; a looping
    stream for `frames` frames)"""
    p = Player(Bank({0: stream}, {0: loop} if loop is not None else None)); p.start(0); out = []; n = 0
    while p.playing() and (frames is None or len(out) < frames):
        a = p.avail; p.isr(); n += a - p.avail; p.fill(); out.append(n)
    return out

def max_gap(stream, loop=None, frames=None):
    """the longest time in frames between two refills the stream survives in any phase (a fill tops the ring up to
    RING - 1 unread bytes; the bytes read before the next fill must not exceed them); None = any (it fits whole)"""
    if len(stream) < SC.RING and loop is None: return None
    b = [0] + consumed(stream, loop, frames); g = 1
    while g < len(b) and max(b[t + g] - b[t] for t in range(len(b) - g)) <= SC.RING - 1: g += 1
    return g - 1

def render_all():
    bank = load_bank(); gap = np.zeros(int(0.3 * RATE), np.float32)
    ab, allp = [], []
    for sid in sorted(bank):
        name = '%02d_%s' % (sid, SC.NAMES[sid])
        kind = 'music' if sid in SC.MUSIC else 'effects'
        psg = render(sound_states(sid, bank))
        write_wav(os.path.join(OUTDIR, kind, name + '_psg.wav'), psg)
        sp = speaker(sid)
        if sp is not None: write_wav(os.path.join(OUTDIR, kind, name + '_pcspk.wav'), sp)
        dg = digitized(sid) if kind == 'effects' else None
        if dg is not None: write_wav(os.path.join(OUTDIR, kind, name + '_digi.wav'), dg)
        if kind == 'effects':
            for x in (dg, sp, psg):
                if x is not None and len(x): ab += [x, gap]
            ab.append(gap); allp += [psg, gap]
    write_wav(os.path.join(OUTDIR, 'ab_effects.wav'), np.concatenate(ab))
    write_wav(os.path.join(OUTDIR, 'all_effects_psg.wav'), np.concatenate(allp))
    print('wrote', OUTDIR, '(effects/, music/, ab_effects.wav, all_effects_psg.wav)')

def record_sdlpop(script):
    """SDLPoP's own audio for a control script (see --sdlpop); returns the WAV path"""
    import subprocess, tempfile
    root = os.path.join(HERE, '..')
    moves, patches = kidsim.read_script(script); keys = kidsim.read_keys(script)
    d = tempfile.mkdtemp(); plain = os.path.join(d, 'script.txt'); raw = os.path.join(d, 'audio.raw')
    open(plain, 'w').write('\n'.join('%d %d %d' % m + (' %d' % k if k else '') for m, k in zip(moves, keys)) + '\n')
    env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='disk', SDL_DISKAUDIOFILE=raw, POP800_SEED='12345',
               POP800_SCRIPT=plain, POP800_TRACE=os.path.join(d, 'trace.txt'))
    o = kidsim.script_opts(script)
    if o['guards']:
        if o['place']: env['POP800_GUARD'] = ','.join('%d:%d:%d:%d:%d' % g for g in o['place'])
    else: env['POP800_NOGUARDS'] = '1'
    if o['sword']: env['POP800_SWORD'] = '1'
    if o['time']: env['POP800_TIME'] = '%d:%d' % o['time']
    if o['start']: env['POP800_START'] = '%d:%d:%d' % o['start']
    if patches: env['POP800_PATCH'] = kidsim.patch_env(script)
    subprocess.run([os.path.join(root, 'external', 'SDLPoP', 'prince'), 'megahit', str(kidsim.script_level(script))],
                   cwd=os.path.join(root, 'external', 'SDLPoP'), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=600)
    x = np.frombuffer(open(raw, 'rb').read(), '<i2').astype(np.float32).reshape(-1, 2).mean(axis=1) / 32768.0
    out = os.path.join(OUTDIR, 'scene_%s_sdlpop.wav' % os.path.basename(script)[:-4])
    write_wav(out, x); return out

if __name__ == '__main__':
    a = sys.argv[1:]
    if '--wav' in a: render_all()
    if '--sdlpop' in a: print('wrote', record_sdlpop(a[a.index('--sdlpop') + 1]))
    if '--script' in a:
        ev = []
        for line in open(a[a.index('--script') + 1]):
            p = line.split()
            if not p or p[0].startswith('#'): continue
            ev.append((int(p[0]), p[1], int(p[2]) if len(p) > 2 else None))
        nf = int(a[a.index('--frames') + 1]) if '--frames' in a else max(e[0] for e in ev) + 100
        states, s = run_script(ev, nf, 'live' if '--live' in a else 'silent')
        for f, st in enumerate(states): print(f, ' '.join(str(v) for v in st))
