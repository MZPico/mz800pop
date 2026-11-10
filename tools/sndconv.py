#!/usr/bin/env python3
"""M7 step 3: the sound bank for the MZ-800 PSG player (src/m4/psg.asm), made from the DOS sound data.

Sources (external/dos/PRINCE, never redistributed; only the converted bank goes to build/):
  IBM_SND1/2.DAT  the PC-speaker resources (res 10000 + id): u8 type 0, u16 tempo (length units per second), then
                  {u16 freq_Hz, u8 length}*, ended by u16 0x0012; freq 0/1 = a rest (SDLPoP speaker_callback)
  DIGISND1-3.DAT  the digitized effects (PoP 1.3 wave: u8 type 1, u16 rate, u8 size 8, u16 count, 4 bytes, u8 samples):
                  the source for the five effects that have no speaker data (falling, sword_moving, draw_sword,
                  loose_shake 1-3)

Effects are re-made for 50 Hz, not played back: the speaker notes last 2-3.5 ms. Each 20 ms frame of the speaker
timeline becomes one PSG state (tone, noise and attenuation per channel), keeping the pitch contour and the length
(see SPEC below and docs/m7-design.md "As built: step 3"). Music is the MIDI arranged for the PSG by tools/midi2psg.py
(M7 step 4; docs/m7-design.md "As built: step 4").

Stream format (one stream per sound id; the player, src/m4/psg.asm, reads it through its 254-byte ring buffer
0xFE02-0xFEFF, which the main code refills from the RAM disk; tools/sndsim.py Player is the model):
  per 20 ms frame step a group of commands, ended by a wait byte:
    0x00         the end: all four channels muted, the player stops
    0x01-0x7F w  the group ends; the next group is read w frames later
    1cc0dddd     tone latch of channel c (c < 3), written to port F2h, then its data byte 00dddddd (also written)
    11100xxx     noise control (c = 3), written
    1cc1aaaa     attenuation aaaa of channel c (0-3), written; unless aaaa = 15 (off) a period byte p follows: c's
                 envelope then makes it one step (2 dB) quieter every p frames until off (p = 0: every 256 frames,
                 i.e. held)
  Every interrupt while a stream plays: first the envelopes step (per channel with attenuation < 15: its counter
  counts down from p; at 0 the attenuation goes up by one and is written, the counter restarts at p), then, when the
  wait has run out, the next group. A stream of n frames has its end byte n frames after its first group.
  Effects use the envelopes as holds (p = 0: every attenuation change is a command) and for their ring-outs (ring_out:
  one command with a period per channel); music (tools/midi2psg.py)
  uses them for the notes' decays.
Bank (build/assets/sound.bin, written to RAM-disk page SB_PAGE at SB_ADDR by the boot and the harness, and the streams
that no longer fit before BANK_END in build/assets/sound_hi.bin at SB_HI, the same page):
  index: NIDS entries of 4 bytes (u16 RAM-disk address of the stream, u16 length; length 0 = no stream), then the
  streams: the effects and the in-game music. The presentation's banks (the same layout with addresses from 0, the
  effects and the Master System pieces, M7 step 11) are tools/presbank.py's: build/assets/sound_pres*.bin.
  A stream whose last byte is not the end 0x00 loops: the loop command 0xE8 lo hi follows it in the bank (not counted
  in its length): psg.asm snd_fill goes on copying from bank address hi:lo (tools/sndsim.py Player models it).
Also writes build/assets/sound.txt (one line per id: what was made and how).
usage: sndconv.py [--list]"""
import json, os, struct, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from datfile import DatFile
DOS = os.path.join(HERE, '..', 'external', 'dos', 'PRINCE')
OUT = os.path.join(HERE, '..', 'build', 'assets')

CPU = 3546895                   # Hz; the PSG is clocked at CPU / 16 (mz800emu), tone f = CPU / (32 N)
FRAME = 0.02                    # the player's step: one VBLN interrupt (50 Hz)
SB_PAGE, SB_ADDR = 1, 0xE000    # the bank in the RAM disk (src/m4/psg.asm SB_PAGE, SB_ADDR)
BANK_END = 0xE918               # the button pictures follow it (src/m4/btnstep.asm BC_BASE, docs/memory.md)
SB_HI, SB_HI_END = 0xFEE4, 0x10000  # the bank's second part (2026-11-11, the effects' ring-outs): page 1's free tail after
                                # M8a part 15's chopper / spike slot 0xFC5C-0xFEE3 (src/m4/frames.asm fs_sdir); every
                                # RAM-disk size has pages 0-7 alike, PRES's scratch is page 1 0x0000-0x7CFF only
                                # (docs/memory.md); build/assets/sound_hi.bin, written as sound.bin is
MUS_BUF, RING = 0xFE02, 254     # the player's ring buffer (0xFE02-0xFEFF; it holds at most RING - 1 bytes)
NIDS = 57
TONE_MIN = CPU / (32 * 1023)    # 108.3 Hz: the lowest tone
NOISE_FIXED = [CPU / 16 / (16 << d) for d in range(3)]   # LFSR shift rates of noise rates 0-2: 13.9, 6.9, 3.5 kHz

NAMES = ['fell_to_death', 'falling', 'tile_crashing', 'button_pressed', 'gate_closing', 'gate_opening',
         'gate_closing_fast', 'gate_stop', 'bumped', 'grab', 'sword_vs_sword', 'sword_moving', 'guard_hurt', 'kid_hurt',
         'leveldoor_closing', 'leveldoor_sliding', 'medium_land', 'soft_land', 'drink', 'draw_sword', 'loose_shake_1',
         'loose_shake_2', 'loose_shake_3', 'footstep', 'death_regular', 'presentation', 'embrace', 'cutscene_2_4_6_12',
         'death_in_fight', 'meet_Jaffar', 'big_potion', '(31)', 'shadow_music', 'small_potion', '(34)', 'cutscene_8_9',
         'out_of_time', 'victory', 'blink', 'low_weight', 'cutscene_12_short_time', 'end_level_music', '(42)',
         'victory_Jaffar', 'skel_alive', 'jump_through_mirror', 'chomped', 'chomper', 'spiked', 'spikes',
         'story_2_princess', 'princess_door_opening', 'story_4_Jaffar_leaves', 'story_3_Jaffar_comes', 'intro_music',
         'story_1_absence', 'ending_music']
MUSIC_GAME = {24, 25, 28, 29, 30, 32, 33, 37, 39, 41, 43}                 # the in-game music (the RAM-disk bank)
MUSIC_PRES = {26, 27, 35, 36, 40, 50, 52, 53, 54, 55, 56}                 # the presentation's (PRES)
MUSIC = MUSIC_GAME | MUSIC_PRES
UNUSED = {31, 34, 42}

# Per-effect conversion (speaker data unless src='digi'). Keys:
#   voices k   the speaker notes are k interleaved lines (note i -> line i mod k), played on separate channels
#   chmap      line -> tone channel (default line i -> channel i); lines not in it are dropped
#   noise      lines played as noise (LFSR) instead of tone
#   att        attenuation (2 dB steps, 0 loudest) of every line; env: per-frame added attenuation (last entry repeats)
#   src='digi' made from the digitized sample: mode 'tone' (pitch from the autocorrelation in prange Hz), 'noise'
#              (rate from the zero crossings) or 'mix' (tone at tonef Hz + noise 3 steps quieter); level from the RMS
#   tail       the ring-out (ring_out, 2026-11-11): True every sounding channel, 'noise' the noise channel only (the
#              tones stop with the stream: a thump's hum would hold), absent none. Given where the sample rings or
#              crashes on; never for the taps and clicks (footstep, the gates' ticks, bumps, the low pulses), whose
#              held pulse or tone turned a click into a buzz (the user's report of the first ring-outs)
#   loop       the stream loops (its end byte dropped, the loop command to its start follows it in the bank) until a
#              stop or another sound: the level door's sliding (15), which animate_leveldoor asks for every tick of the
#              opening and stops when the door is open; the ticks model holds it for its digitized length (20 ticks),
#              longer than the speaker pattern (13 frames) and, on the MZ-800's slower ticks, than the digitized
#              sample itself, so a one-shot stream left a silence of most of every 20 ticks (docs/m7-design.md 12.1);
#              a last frame equal to the first is dropped (the seam), which also keeps the bank's size: it ends where
#              the button pictures start (page 1 0xE918, src/m4/btnstep.asm)
#   why        the note for sound.txt / the docs
SPEC = {
    0: dict(why='random notes 24-1068 Hz (72 ms) -> white noise, rate following the notes'),
    1: dict(src='digi', mode='tone', prange=(250, 500), why='no speaker data: the digitized scream (1.09 s): its pitch '
            '(~367 Hz) and loudness per frame'),
    2: dict(tail=True, env=[0] * 11 + [1, 2, 3, 4], why='random notes 51-1139 Hz (302 ms) -> noise following the notes, faded '
            'over the last 4 frames'),
    3: dict(tail=True, why='random notes (42 ms) -> 2 frames of noise'),
    4: dict(why='one 101 Hz note (14 ms) -> 1 frame of a 101 Hz pulse (periodic noise clocked by channel 2)'),
    5: dict(att=4, why='one 101 Hz note (7 ms) -> 1 frame, 4 dB quieter than 4 (the speaker note is half as long)'),
    6: dict(tail=True, why='random notes 252-1861 Hz (128 ms) -> 6 frames of noise'),
    7: dict(why='one 4999 Hz note (14 ms) -> 1 frame tone'),
    8: dict(why='one 49 Hz note (42 ms) -> 2 frames of a 49 Hz pulse'),
    9: dict(why='one 61 Hz note (14 ms) -> 1 frame of a 61 Hz pulse'),
    10: dict(tail=True, env=[0, 2, 5], frames=3, why='one 2999 Hz note (42 ms) -> 3 frames tone with a decay (the clang)'),
    11: dict(src='digi', mode='noise', why='no speaker data: the digitized swish (106 ms) -> noise, rate and level '
             'per frame'),
    12: dict(voices=2, att=3, why='two interleaved falling lines 230->70 / 730->570 Hz (62 ms) -> two tones (the low '
             'line as a pulse below 108 Hz)'),
    13: dict(voices=2, att=3, why='two interleaved falling lines 980->820 / 480->320 Hz (51 ms) -> two tones'),
    14: dict(tail=True, voices=2, att=3, why='rising octave pairs 208/416 -> 400/800 Hz, then a 97 ms rest (184 ms) -> two '
             'tones, then silence (the stream keeps the length)'),
    15: dict(loop=True, why='18 notes 39->31->39 Hz (250 ms) -> a 31-39 Hz pulse following the notes, looping until '
             'stopped (the door\'s opening ends with stop_sounds; DOS restarts it every tick it has ended)'),
    16: dict(tail='noise', voices=3, noise=[1], att=3, why='three interleaved lines: 121->201 and 101->181 Hz rising, one random '
             '(60 ms) -> two tones + noise'),
    17: dict(att=3, why='one 49 Hz note (42 ms) -> 2 frames of a 49 Hz pulse, 2 dB quieter than the bump'),
    18: dict(why='six rising sweeps (10 notes each, 138->256 Hz) with rests (1.46 s) -> tone sweeps and rests'),
    19: dict(tail=True, src='digi', mode='noise', why='no speaker data: the digitized blade (254 ms) -> bright noise, level per '
             'frame'),
    20: dict(src='digi', mode='noise', why='no speaker data: the digitized rattle (121 ms) -> noise'),
    21: dict(tail='noise', src='digi', mode='mix', tonef=733, why='no speaker data: the digitized rattle (95 ms, a clink at 733 Hz) -> '
             'tone + noise'),
    22: dict(src='digi', mode='mix', tonef=524, why='no speaker data: the digitized rattle (106 ms, 524 Hz) -> tone + '
             'noise'),
    23: dict(src='digi', mode='noise', why='the digitized step (121 ms) -> a noise tap, rate and level per frame (the '
             'speaker\'s one 61 Hz note, a 1-frame pulse, until 2026-11-11: with a ring-out it buzzed)'),
    38: dict(why='2500, 2000, 1500, 1000 Hz (56 ms) -> 3 frames of falling tone'),
    44: dict(why='19 notes of 20 ms each, 33-3132 Hz -> one tone per frame (pulses below 108 Hz)'),
    45: dict(tail=True, voices=2, att=3, why='two interleaved lines: 1758-2536 Hz jittering, 1002->2152 Hz rising (167 ms) -> '
             'two tones'),
    46: dict(tail='noise', voices=3, noise=[1], att=3, why='three interleaved lines: 501->581 Hz, random, 999->919 Hz (68 ms) -> two '
             'tones + noise'),
    47: dict(voices=2, att=3, why='4000 / 750 Hz alternating (107 ms) -> two tones'),
    48: dict(tail='noise', voices=3, noise=[1], att=3, why='three interleaved lines: 499 Hz falling to 0, random, 999->... falling '
             '(151 ms) -> two falling tones + noise (inaudible >15 kHz notes = silence)'),
    49: dict(voices=4, chmap={0: 0, 1: 1, 3: 2}, att=3, why='four interleaved lines 4300->5200, 2700->1800, '
             '2800->3700, 1200->300 Hz (56 ms) -> three tones (the third line, which crosses the first, dropped)'),
    51: dict(why='9 notes 39->31 Hz (538 ms) -> a 31-39 Hz pulse'),
}
DEFAULT_ATT = 2
INAUDIBLE = 15000               # speaker notes above this are silence (the PIT divisor wraps; nothing audible)


def tone_n(f):
    return max(1, min(1023, int(round(CPU / (32.0 * f)))))

def pulse_n(f):
    """channel 2 divider for periodic noise at f Hz (1 pulse per 16 LFSR shifts, one shift per channel-2 period)"""
    return max(1, min(1023, int(round(CPU / (256.0 * f)))))

def noise_n(rate):
    """channel 2 divider for white noise with LFSR shift rate `rate`"""
    return max(1, min(1023, int(round(CPU / (16.0 * rate)))))


def pcspk(sid):
    """(tempo, [(freq, length)]) of the speaker resource, or None"""
    dat = 'IBM_SND1.DAT' if sid < 44 else 'IBM_SND2.DAT'
    d = DatFile(os.path.join(DOS, dat))
    if 10000 + sid not in d.ids(): return None
    r = d.resource(10000 + sid)
    if len(r) < 3: return None
    tempo = struct.unpack_from('<H', r, 1)[0]; notes = []; p = 3
    while p + 3 <= len(r):
        f = struct.unpack_from('<H', r, p)[0]
        if f == 0x12: break
        notes.append((f, r[p + 2])); p += 3
    return tempo, notes

def digi(sid):
    """(rate, samples as floats centred on 0) of the digitized effect, or None"""
    for f in ('DIGISND1.DAT', 'DIGISND2.DAT', 'DIGISND3.DAT'):
        d = DatFile(os.path.join(DOS, f))
        if 10000 + sid in d.ids():
            b = d.resource(10000 + sid)
            rate, size, cnt = struct.unpack_from('<HBH', b, 1)
            return rate, np.frombuffer(b[10:10 + cnt], np.uint8).astype(float) - 128
    return None

def timeline(tempo, notes):
    out, t = [], 0.0
    for f, l in notes:
        d = l / float(tempo); out.append((t, t + d, f)); t += d
    return out, t


class State:
    """the PSG state a frame wants: att[4], tone[3] (divider or None = don't care), noise (control byte or None)"""
    def __init__(self):
        self.att = [15] * 4; self.tone = [None] * 3; self.noise = None
    def key(self): return (tuple(self.att), tuple(self.tone), self.noise)


def place(st, reqs):
    """put the requests [(line, kind, value, att)] of one frame on the channels. kind: 'tone' f Hz, 'noise' shift rate,
    'low' f Hz (below the tone range). Tones go to their channel; noise and low pulses to channel 3, clocked by
    channel 2 when no tone uses it (a fixed rate otherwise); a low pulse without a free channel 2 / 3 goes an octave up."""
    ch2_tone = any(k == 'tone' and c == 2 for c, k, v, a in reqs) or \
        sum(1 for c, k, v, a in reqs if k == 'low') > 1
    used3 = False
    for c, k, v, a in sorted(reqs, key=lambda r: r[1] == 'low'):     # (noise before a low pulse)
        if k == 'low' and (used3 or ch2_tone):
            while v < TONE_MIN: v *= 2
            k = 'tone'
        if k == 'tone':
            st.tone[c] = tone_n(v); st.att[c] = a
        elif k == 'noise':
            if not ch2_tone:
                st.tone[2] = noise_n(v); st.noise = 0xE7; ch2_tone = True
            else:
                d = min(range(3), key=lambda i: abs(np.log(NOISE_FIXED[i] / v)))
                st.noise = 0xE4 | d
            st.att[3] = a; used3 = True
        else:   # low pulse: periodic noise clocked by channel 2
            st.tone[2] = pulse_n(v); st.noise = 0xE3; st.att[3] = a; used3 = True; ch2_tone = True
    return st


def frames_from_speaker(sid, spec):
    tempo, notes = pcspk(sid)
    tl, total = timeline(tempo, notes)
    nf = spec.get('frames', max(1, int(round(total / FRAME))))
    k = spec.get('voices', 1); chmap = spec.get('chmap', {i: i for i in range(k)}); noisy = spec.get('noise', [])
    att0 = spec.get('att', DEFAULT_ATT); env = spec.get('env', [0])
    out = []
    for fi in range(nf):
        w0, w1 = fi * FRAME, (fi + 1) * FRAME
        if fi == nf - 1 and spec.get('frames'): w1 = max(w1, total)
        rest = sum(max(0.0, min(w1, t1) - max(w0, t0)) for t0, t1, f in tl if f <= 1)
        sound = sum(max(0.0, min(w1, t1) - max(w0, t0)) for t0, t1, f in tl if f > 1)
        if not any(t0 < w1 and t1 > w0 for t0, t1, f in tl):          # past the end (a frames override): the last note
            sound, rest = 1.0, 0.0
            win = [(n, t1 - t0, f) for n, (t0, t1, f) in enumerate(tl)][-k:]
        else:
            win = [(n, max(0.0, min(w1, t1) - max(w0, t0)), f) for n, (t0, t1, f) in enumerate(tl) if t0 < w1 and t1 > w0]
        a = min(15, att0 + env[min(fi, len(env) - 1)])
        st = State(); reqs = []
        if sound > rest and a < 15:
            for line, c in chmap.items():
                ns = [(ov, f) for n, ov, f in win if n % k == line and 1 < f <= INAUDIBLE and ov > 0]
                if not ns: continue
                fs = sorted(f for ov, f in ns)
                if line in noisy or (len(ns) >= 3 and fs[-1] / fs[0] > 2.5):
                    reqs.append((c, 'noise', min(14000.0, max(500.0, 4.0 * float(np.median(fs)))), a))
                else:
                    f = max(ns)[1]
                    reqs.append((c, 'low' if f < TONE_MIN else 'tone', f, a))
        out.append(place(st, reqs))
    return out


def frames_from_digi(sid, spec):
    rate, s = digi(sid)
    n = int(round(rate * FRAME)); nf = int(np.ceil(len(s) / float(n)))
    out, lastn = [], None
    for fi in range(nf):
        w = s[fi * n:(fi + 1) * n]; w = w - w.mean()
        rms = float(np.sqrt((w * w).mean())) + 1e-9
        a = int(round(20 * np.log10(60.0 / rms) / 2.0)) + 1
        st = State()
        if a < 15 and len(w) > n // 2:
            a = max(0, a)
            zc = ((w[:-1] < 0) != (w[1:] < 0)).sum() * rate / float(len(w)) / 2.0
            mode = spec['mode']
            if mode == 'tone':
                lo, hi = spec['prange']
                ac = np.correlate(w, w, 'full')[len(w) - 1:]
                l0, l1 = int(rate / hi), int(rate / lo) + 1
                lag = l0 + int(np.argmax(ac[l0:l1]))
                f = rate / float(lag)
                if lastn is not None and abs(tone_n(f) - lastn) <= 0.03 * lastn: f = CPU / (32.0 * lastn)
                lastn = tone_n(f)
                place(st, [(0, 'tone', f, a)])
            elif mode == 'noise':
                place(st, [(0, 'noise', min(14000.0, max(500.0, 4.0 * zc)), a)])
            else:
                place(st, [(0, 'tone', spec['tonef'], min(15, a + 2)), (1, 'noise', min(14000.0, max(500.0, 4.0 * zc)), min(15, a + 3))])
        out.append(st)
    while len(out) > 1 and out[-1].att == [15] * 4: out.pop()        # (the silent tail)
    return out


TAIL_MIN, TAIL_MAX = 3, 40      # the ring-out's frames: the digitized sample's rest after the stream, within these

def ring_out(sid, frames, noise_only=False):
    """the effect's ring-out (2026-11-11): after its last audible frame the sound decays to silence over the rest of the
    digitized sample's length (at most TAIL_MAX frames; none when the stream reaches it already; TAIL_MIN frames for the
    one effect without a sample, the blink 38), each sounding channel from its own
    attenuation one 2 dB step every p frames (p = tail / steps, at least 1): exactly the player's envelope (an
    attenuation command with period p), so a tail costs one command per channel. Tones and noise hold; noise_only: the
    tones stop at the stream's last frame, the noise channel alone decays. The stream keeps at least its old length (a
    rest at its end stays). Only for the effects whose SPEC asks for it (tail). -> (frames, tail frames)"""
    n0 = len(frames); fr = list(frames)
    while len(fr) > 1 and fr[-1].att == [15] * 4: fr.pop()
    if fr[-1].att == [15] * 4: return frames, 0
    d = digi(sid)
    dlen = int(round(len(d[1]) / float(d[0]) / FRAME)) if d else len(fr)
    tail = min(TAIL_MAX, dlen - len(fr)) if d else TAIL_MIN
    if tail <= 0: return frames, 0      # (the stream reaches the sample's end already: the digitized ones, 18, 44, 51)
    last = fr[-1]; n1 = len(fr)
    if noise_only:
        if last.att[3] >= 15: return frames, 0
        last = State(); last.tone = list(fr[-1].tone); last.noise = fr[-1].noise; last.att = [15, 15, 15, fr[-1].att[3]]
    per = [max(1, int(round(tail / float(15 - a)))) if a < 15 else 0 for a in last.att]
    for k in range(1, tail + 1):
        st = State(); st.tone = list(last.tone); st.noise = last.noise
        st.att = [15 if a >= 15 else min(15, a + k // per[c]) for c, a in enumerate(last.att)]
        fr.append(st)
        if st.att == [15] * 4: break
    while len(fr) > 1 and fr[-1].att == [15] * 4: fr.pop()
    used = len(fr) - n1
    while len(fr) < n0: fr.append(State())
    return fr, used

def encode(frames, tol=0, fit=False):
    """the stream of a list of frame States (the format above): only the registers that change are written; the
    attenuation follows the envelope model of the player. Effects (fit False): every attenuation change is a command
    with p = 0, so the PSG state per frame is exactly the frames'. Music (fit True): a command is made where the
    envelope's attenuation would differ from the wanted one by more than tol steps (or one is off and the other not),
    with the period that follows the wanted attenuations longest."""
    env = [[15, 0, 0] for _ in range(4)]          # attenuation, counter, period (the ISR's)
    tone = [None] * 3; noise = None; groups = []
    def step(e):
        if e[0] < 15:
            e[1] = (e[1] - 1) & 255
            if e[1] == 0: e[1] = e[2]; e[0] += 1
    def ok(sim, want): return (sim >= 15) == (want >= 15) and abs(sim - want) <= tol
    def run(f, c, a, p):
        """frames from f an envelope (a, p) follows channel c's wanted attenuation"""
        e = [a, p, p]; k = 1
        while f + k < len(frames):
            step(e)
            if not ok(e[0], frames[f + k].att[c]): break
            k += 1
        return k
    for f, st in enumerate(frames):
        for e in env: step(e)
        b = []
        for c in range(3):
            n = st.tone[c]
            if n is not None and n != tone[c]:
                b += [0x80 | (c << 5) | (n & 15), (n >> 4) & 0x3F]; tone[c] = n
        if st.noise is not None and st.noise != noise:
            b.append(st.noise); noise = st.noise
        for c in range(4):
            want = st.att[c]; cur = env[c][0]
            new_note = c in getattr(st, 'onset', ()) and want < 15
            if (want == cur and not new_note) or (fit and not new_note and ok(cur, want)): continue
            if want >= 15:
                b.append(0x9F | (c << 5)); env[c] = [15, 0, 0]; continue
            p = 0
            if fit:
                p = max([0] + list(range(1, 64)), key=lambda q: (run(f, c, want, q), -q))
            b += [0x90 | (c << 5) | want, p]; env[c] = [want, p, p]
        groups.append(b)
    out = bytearray(); f = 0
    while f < len(groups):
        g = groups[f]; nxt = f + 1
        while nxt < len(groups) and not groups[nxt]: nxt += 1
        w = nxt - f
        while w > 127:                                 # (a long hold: groups of only a wait)
            out += bytes(g) + bytes([127]); g = []; w -= 127
        out += bytes(g) + bytes([w]); f = nxt
    out.append(0)
    return bytes(out)

def decode(stream):
    """the PSG state per frame a stream gives (sndsim's Player on it alone), and the number of frames"""
    import sndsim
    p = sndsim.Player({0: stream}); p.start(0); out = []
    while True:
        p.isr()
        if not p.playing(): break
        out.append(p.psg.state())
    return out


def make_bank(streams, loops=None):
    """a bank at SB_ADDR of {id: stream} (tests/m7_sound.py plays the presentation's pieces through the game's player
    with it); loops {id: loop point byte offset}: the loop command follows those streams"""
    bank = bytearray(NIDS * 4)
    for sid in sorted(streams):
        struct.pack_into('<HH', bank, sid * 4, SB_ADDR + len(bank), len(streams[sid]))
        lp = (loops or {}).get(sid)
        if lp is not None: bank += streams[sid] + bytes([0xE8]) + struct.pack('<H', SB_ADDR + len(bank) + lp)
        else: bank += streams[sid]
    assert SB_ADDR + len(bank) <= 0x10000
    return bytes(bank)

def build(verbose=True):
    import midi2psg
    streams, notes, info, loops = {}, {}, {}, {}
    for sid in range(NIDS):
        name = NAMES[sid]
        if sid in UNUSED: notes[sid] = 'unused id: no stream'; continue
        if sid in MUSIC:
            data, why, nfr = midi2psg.stream(sid)
            streams[sid] = data; notes[sid] = why
            info[sid] = dict(kind='music', frames=nfr, bytes=len(data))
            continue
        spec = SPEC[sid]
        fr = frames_from_digi(sid, spec) if spec.get('src') == 'digi' else frames_from_speaker(sid, spec)
        if spec.get('loop') and len(fr) > 1 and fr[-1].key() == fr[0].key():
            fr = fr[:-1]                # (the loop's seam: the last frame is the first one again)
        tail = 0
        if spec.get('tail') and not spec.get('loop'):
            fr, tail = ring_out(sid, fr, noise_only=spec['tail'] == 'noise')
        data = encode(fr, fit=bool(tail))
        assert len(data) < RING, (sid, len(data))
        if spec.get('loop'):
            assert data[-1] == 0 and 0 < data[-2] < 0x80, sid       # (the end byte after the last wait)
            data = data[:-1]; loops[sid] = 0
        streams[sid] = data
        notes[sid] = spec['why'] + (', ring-out %d frames' % tail if tail else '')
        info[sid] = dict(kind='effect', frames=len(fr), bytes=len(data) + (3 if sid in loops else 0))
    assert SB_ADDR & 0xFF == 0 and 4 * (NIDS - 1) < 256          # (psg.asm: the index entry at SB_ADDR + 4 id)
    banks = {}
    for fn, music, base in (('sound.bin', MUSIC_GAME, SB_ADDR),):
        # the streams in id order from the index on, up to BANK_END; the ones that no longer fit go to the second part
        # at SB_HI (in id order); an index entry is a page-1 address, so the player reads either part alike
        bank = bytearray(NIDS * 4); addr = base + len(bank); hi = bytearray(); full = False
        for sid in range(NIDS):
            if sid not in streams or (sid in MUSIC and sid not in music): continue
            data = streams[sid]
            n = len(data) + (3 if sid in loops else 0)
            if full or addr + n > BANK_END:
                full = True; at = SB_HI + len(hi)
            else: at = addr
            struct.pack_into('<HH', bank, sid * 4, at, len(data))
            if sid in loops: data = data + bytes([0xE8]) + struct.pack('<H', at + loops[sid])
            if at == addr: bank += data; addr += len(data)
            else: hi += data
        assert base + len(bank) <= BANK_END, ('the bank overlaps the button pictures', base + len(bank))
        assert SB_HI + len(hi) <= SB_HI_END, ('the bank\'s second part does not fit page 1', SB_HI + len(hi))
        os.makedirs(OUT, exist_ok=True)
        open(os.path.join(OUT, fn), 'wb').write(bytes(bank)); banks[fn] = bank
        open(os.path.join(OUT, 'sound_hi.bin'), 'wb').write(bytes(hi)); banks['sound_hi.bin'] = hi
    eff = sum(i['bytes'] for i in info.values() if i['kind'] == 'effect')
    mg = sum(info[s]['bytes'] for s in MUSIC_GAME); mp = sum(info[s]['bytes'] for s in MUSIC_PRES)
    lines = ['# generated by tools/sndconv.py: the PSG sound bank (RAM-disk page %d 0x%04X, %d bytes, and 0x%04X, %d bytes; '
             'the presentation\'s banks: tools/presbank.py)' % (SB_PAGE, SB_ADDR, len(banks['sound.bin']), SB_HI, len(banks['sound_hi.bin'])),
             '# id name kind frames bytes: how it was made']
    for sid in range(NIDS):
        i = info.get(sid)
        if i: lines.append('%2d %-22s %-6s %4d %4d: %s' % (sid, NAMES[sid], i['kind'], i['frames'], i['bytes'], notes[sid]))
        else: lines.append('%2d %-22s -: %s' % (sid, NAMES[sid], notes.get(sid, 'no speaker data')))
    lines.append('# effects %d bytes, in-game music %d bytes, index %d bytes: sound.bin %d; the MIDI presentation music '
                 '(%d bytes) is not in a bank: PRES plays the Master System pieces (tools/presbank.py)' % (eff, mg, NIDS * 4, len(banks['sound.bin']), mp))
    open(os.path.join(OUT, 'sound.txt'), 'w').write('\n'.join(lines) + '\n')
    if verbose: print('sound bank: %d + %d bytes (effects %d, in-game music %d, index %d) -> build/assets/sound.bin, '
                      'sound_hi.bin (the presentation\'s banks: tools/presbank.py)' % (
                          len(banks['sound.bin']), len(banks['sound_hi.bin']), eff, mg, NIDS * 4))
    return bytes(banks['sound.bin'])


if __name__ == '__main__':
    build()
    if '--list' in sys.argv: print(open(os.path.join(OUT, 'sound.txt')).read())
