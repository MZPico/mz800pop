#!/usr/bin/env python3
"""Listening experiment (not part of the build): the DOS MIDI music arranged for the PSG with chiptune techniques,
rendered to WAV in build/sound/exp/. Imports tools/midi2psg.py (the MIDI reading, the OPL level measurement),
tools/sndconv.py (the stream encoder) and tools/sndsim.py (the player model); changes nothing they do.

Differences to midi2psg.py's arrangement (docs/m7-design.md section 13):
  1. Real bass through periodic noise: the SN76489's noise channel in periodic mode clocked from tone channel 2
     outputs one pulse per 15 shifts (15-bit shift register, SN76489AN; the datasheet's shift rate for the fixed
     rate 0 is N/512 = the frequency of a tone with divider 16, i.e. one shift per tone-2 PERIOD): the pitch is
     f2 / 15. Channel 2's divider is set to 15 x the bass note (attenuation off), the noise channel's attenuation
     carries the bass: the bass line sounds at its real pitch (36.7 Hz in piece 54) instead of folded up.
     NB mz800emu (hw-generic/psg/psg.c) shifts a 16-bit register once per tone-2 HALF period (every `divider` steps
     of CPU/16), which gives f2 / 8 - 10.9 semitones above the real chip; tools/sndsim.py models the emulator.
     render_exact() below is the real-chip model (15-bit register, taps 0 and 1 for white noise, one shift per
     period); the emulator's rendering of the same stream is written too (*_exp_emu.wav) so the difference can be
     heard. The game tests' reference (sndsim.render) is untouched.
  2. Fixed roles instead of per-frame loudness picking: channel 0 = the melody (the top pitch class; the loudest of
     its octaves, kept while it sounds), with its instrument's measured envelope; channel 1 = the harmony as a fast
     arpeggio of the chord's other pitch classes (1 note per ARP frames); channel 2 + noise = the bass (the lowest
     note at or below BASS_MAX Hz). A melody or bass note repeating its pitch is re-struck after a 1-frame gap.
  3. Dynamics: the measured level curves map to attenuation as in midi2psg.py (peak = 0, 2 dB a step, > 28 dB = off);
     the arpeggio has one attenuation per chord (its loudest note's) so it does not flicker; the bass gets a boost
     (the 1/15-duty pulse has ~6 dB less RMS and ~14 dB less fundamental than a square wave at the same attenuation).
Outputs (build/sound/exp/): <id>_<name>_exp.wav (the arrangement, real-chip model), _exp_arp1.wav / _exp_arp2.wav
(arpeggio at 1 / 2 frames a note), _exp_vib.wav (with a frame-rate vibrato on the melody), _exp_bass5.wav (bass
10 dB instead of 6 dB above its measured level), _exp_emu.wav (the exp
stream as mz800emu would play it), _ab.wav (OPL original / current PSG / new PSG, 1 s apart), <id>_<name>_exp.txt
and summary.txt.
usage: midi2psg_exp.py [ids]   (default 54 41 24 25)"""
import os, sys, wave
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import midi2psg as M
import sndconv as SC
import sndsim
ROOT = os.path.join(HERE, '..')
EXP = os.path.join(ROOT, 'build', 'sound', 'exp')
MUSIC = os.path.join(ROOT, 'build', 'sound', 'music')
CPU, FRAME = M.CPU, M.FRAME
PERIODIC_LEN = 15                 # the SN76489AN's shift register (16 on the Sega VDP and in mz800emu)
NOISE_TONE2 = 0xE3                # noise control: periodic, clocked by channel 2

DEFAULTS = dict(
    arp=1,                        # frames per arpeggio note
    bass_max=130.0,               # the lowest sounding note at or below this is the bass
    bass_min=0.0,                 # bass notes below this are raised by octaves (0: never)
    bass_boost=3,                 # attenuation steps the bass is louder than its measured level says
    harm_att=1,                   # steps the arpeggio is quieter than its loudest note says
    bass_double=True,             # channel 1 doubles the bass (folded up) when the chord has no other note
    double_att=3,                 # ... that many steps quieter than the bass
    vibrato=0,                    # melody vibrato depth in divider steps (0 off), a triangle of VIB_PERIOD frames
    vib_delay=6,                  # frames of a note before the vibrato starts
    melody_att=0,                 # offset of the melody's attenuation
    tol=1,                        # the encoder's attenuation tolerance (steps)
)
VIB_PERIOD = 8                    # frames: 6.25 Hz
VIB_SHAPE = [0, 1, 1, 1, 0, -1, -1, -1]


def bass_n(f):
    """channel 2 divider for a periodic-noise bass at f Hz (f2 = 15 f)"""
    return max(1, min(1023, int(round(CPU / (32.0 * PERIODIC_LEN * f)))))

def bass_f(n): return CPU / (32.0 * n) / PERIODIC_LEN

def fold(f):
    while f < M.TONE_MIN: f *= 2.0
    return f


def arrange(sid, spec=None):
    """the piece as sndconv.State per frame + info (roles per frame, counts)"""
    sp = dict(DEFAULTS); sp.update(spec or {})
    ns = M.notes(sid)
    nfr = int(round(M.length(sid) / FRAME))
    combos = {}
    for n in ns:
        c = (n['prog'], n['vel'], n['pk']); combos[c] = max(combos.get(c, 0), int(round((n['t1'] - n['t0']) / FRAME)) + 1)
    curves = M.level_curves(combos)
    lv = M.note_levels(ns, curves)
    snd = [n['f'] * 2 ** (M.PROG_SHIFT.get(n['prog'], 0) / 12.0) for n in ns]       # the sounding pitch, unfolded
    pc = [int(round(12 * np.log2(f / 440.0))) % 12 for f in snd]
    peak = max(l.max() for f0, l in lv)
    floor = peak - 2.0 * M.ATT_RANGE - 1.0
    att_of = lambda level: int(round((peak - level) / 2.0))
    frames = [SC.State() for _ in range(nfr)]
    roles = []                                        # per frame: dict(mel=i, bass=i, harm=[i...])
    mel_prev = bass_prev = None; arp_ctr = 0; arp_pool_prev = []
    used_as_bass = set(); folded_harm = set(); mel_notes = set()
    for f in range(nfr):
        act = {}
        for i, (f0, l) in enumerate(lv):
            k = f - f0
            if k < 0 or k >= len(l) or l[k] < floor: continue
            act[i] = (l[k], k)
        st = frames[f]; st.onset = set(); role = dict(mel=None, bass=None, harm=[])
        if not act: roles.append(role); continue
        # the bass: the lowest sounding note at or below bass_max
        low = [i for i in act if snd[i] <= sp['bass_max']]
        bass = min(low, key=lambda i: (snd[i], -act[i][0])) if low else None
        if bass is not None and bass_prev in act and pc[bass_prev] == pc[bass] and snd[bass_prev] <= snd[bass] * 1.01:
            bass = bass_prev                          # (keep the note while it sounds)
        # the melody: the top pitch class among the notes above the bass; the loudest of its octaves, kept
        up = [i for i in act if i != bass] or list(act)
        top = max(up, key=lambda i: snd[i])
        cands = [i for i in up if pc[i] == pc[top]]
        mel = mel_prev if mel_prev in cands else max(cands, key=lambda i: (act[i][0], snd[i]))
        # the harmony: the other pitch classes (the loudest note of each), the bass's class last
        pool = {}
        for i in act:
            if i in (bass, mel) or pc[i] == pc[mel]: continue
            if bass is not None and pc[i] == pc[bass] and snd[i] < sp['bass_max']: continue   # (an octave of the bass)
            j = pool.get(pc[i])
            if j is None or act[i][0] > act[j][0]: pool[pc[i]] = i
        harm = sorted(pool.values(), key=lambda i: snd[i])
        if bass is not None and len(harm) > 3: harm = [i for i in harm if pc[i] != pc[bass]]
        harm = harm[-3:]
        role.update(mel=mel, bass=bass, harm=harm); roles.append(role)
        # channel 0: the melody
        lvl, age = act[mel]
        a = att_of(lvl) + sp['melody_att']
        if a <= M.ATT_RANGE:
            n = M.tone_n(fold(snd[mel])); mel_notes.add(mel)
            if sp['vibrato'] and age >= sp['vib_delay']:
                n = max(1, min(1023, n + sp['vibrato'] * VIB_SHAPE[(age - sp['vib_delay']) % VIB_PERIOD]))
            st.tone[0] = n; st.att[0] = max(0, a)
            if age == 0: st.onset.add(0)
        # channel 2 + noise: the bass
        if bass is not None:
            lvl, age = act[bass]
            a = att_of(lvl) - sp['bass_boost']
            if a <= M.ATT_RANGE:
                fb = snd[bass]
                while sp['bass_min'] and fb < sp['bass_min']: fb *= 2.0
                st.tone[2] = bass_n(fb); st.att[2] = 15; st.noise = NOISE_TONE2; st.att[3] = max(0, a)
                used_as_bass.add(bass)
                if age == 0: st.onset.add(3)
        # channel 1: the arpeggio (or the bass doubled)
        if harm:
            keyp = [pc[i] for i in harm]
            if keyp != [pc[i] for i in arp_pool_prev]: arp_ctr = 0           # (a new chord starts at its lowest note)
            i = harm[(arp_ctr // sp['arp']) % len(harm)]; arp_ctr += 1
            lvl = max(act[j][0] for j in harm)
            a = att_of(lvl) + sp['harm_att']
            if a <= M.ATT_RANGE:
                f_ = fold(snd[i])
                if snd[i] < M.TONE_MIN: folded_harm.add(i)
                st.tone[1] = M.tone_n(f_); st.att[1] = max(0, a)
                if any(act[j][1] == 0 for j in harm) and len(harm) == 1: st.onset.add(1)
        elif sp['bass_double'] and bass is not None and st.att[3] < 15:
            a = st.att[3] + sp['bass_boost'] + sp['double_att']
            if a <= M.ATT_RANGE:
                st.tone[1] = M.tone_n(fold(snd[bass])); st.att[1] = a
                if act[bass][1] == 0: st.onset.add(1)
            arp_ctr = 0
        else: arp_ctr = 0
        arp_pool_prev = harm
        mel_prev, bass_prev = mel, bass
    # a re-struck pitch on a channel whose level does not rise: the frame before it silent
    for f in range(1, nfr):
        for c in frames[f].onset:
            p, s = frames[f - 1], frames[f]
            tc = 2 if c == 3 else c
            if p.tone[tc] == s.tone[tc] and p.att[c] < 15 and s.att[c] >= p.att[c] - 1: p.att[c] = 15
    low_notes = [i for i in range(len(ns)) if snd[i] < M.TONE_MIN]
    info = dict(peak=peak, roles=roles, notes=ns, snd=snd, low=low_notes, used_as_bass=used_as_bass,
                folded_harm=folded_harm, mel_notes=mel_notes, spec=sp)
    return frames, info


# ---------------------------------------------------------------- the real-chip renderer
_LFSR = {}
def lfsr_exact(white):
    """the SN76489AN's noise output per shift: 15-bit register from 1 << 14; white: feedback bit 0 ^ bit 1"""
    if white in _LFSR: return _LFSR[white]
    sr = 1 << 14; out = []
    for _ in range(32767 if white else PERIODIC_LEN):
        b0 = sr & 1
        sr = (sr >> 1) | (((b0 ^ ((sr >> 1) & 1)) if white else b0) << 14)
        out.append(sr & 1)
    _LFSR[white] = np.array(out, np.float32)
    return _LFSR[white]

def render_exact(states, rate=sndsim.RATE):
    """sndsim.render with the real chip's noise: the shift register is 15 bits long and shifts once per tone-2
    period (2 N steps of CPU/16; fixed rates: 2 x 16 << r steps). The tones are sndsim's."""
    steps_per_frame = sndsim.PSG_CLK / 50.0
    out = []; step0 = 0.0; nshift = 0.0; noise_phase = 0.0
    tphase = [0.0, 0.0, 0.0]
    for st in states:
        s0 = step0; s1 = step0 + steps_per_frame
        n = int(round(s1 * rate / sndsim.PSG_CLK)) - int(round(s0 * rate / sndsim.PSG_CLK))
        if n <= 0: step0 = s1; continue
        k = 8
        t = (np.arange(n * k, dtype=np.float64) + 0.5) / (n * k) * steps_per_frame
        mix = np.zeros(n * k, np.float32)
        att = [st[0], st[2], st[4], st[6]]; tone = [st[1], st[3], st[5]]
        for c in range(3):
            N = tone[c]; ph = tphase[c] + t
            if att[c] < 15 and N >= 2: mix += sndsim.amp(att[c]) * (1.0 - 2.0 * (np.floor(ph / N) % 2))
            tphase[c] = (tphase[c] + steps_per_frame) % (2 * max(N, 1))
        ndiv, white = st[7], st[8]
        timer = 2 * (tone[2] if ndiv == 3 else (16 << ndiv))                    # one shift per tone period
        if att[3] < 15 and timer >= 4:
            seq = lfsr_exact(white)
            idx = (nshift + np.floor((noise_phase + t) / timer)).astype(np.int64) % len(seq)
            mix += sndsim.amp(att[3]) * (2.0 * seq[idx] - 1.0)
        total = noise_phase + steps_per_frame
        nshift += np.floor(total / max(timer, 1)); noise_phase = total % max(timer, 1)
        out.append(mix.reshape(n, k).mean(axis=1) / 4.0)
        step0 = s1
    return highpass(np.concatenate(out)) if out else np.zeros(0, np.float32)


# ---------------------------------------------------------------- measurements
def read_wav(path):
    with wave.open(path, 'rb') as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() == sndsim.RATE
        return np.frombuffer(w.readframes(w.getnframes()), '<i2').astype(np.float32) / 32000.0

def low_share(x, rate=sndsim.RATE, cut=130.0):
    """share of the signal's energy in 20 Hz .. `cut` Hz (dB; DC left out)"""
    X = np.abs(np.fft.rfft(x)) ** 2; fr = np.fft.rfftfreq(len(x), 1.0 / rate)
    return 10 * np.log10((X[(fr >= 20) & (fr < cut)].sum() + 1e-12) / (X[fr >= 20].sum() + 1e-12))

def highpass(x, rate=sndsim.RATE, fc=20.0):
    """first-order high-pass (the output coupling; the periodic pulse's DC level moves with every attenuation step)"""
    a = np.exp(-2 * np.pi * fc / rate)
    import scipy.signal as ss
    return ss.lfilter([ (1 + a) / 2, -(1 + a) / 2], [1, -a], x).astype(np.float32)

def bytes_per_second(stream, nfr):
    """mean and the densest 1 s window (bytes read by the player)"""
    c = sndsim.consumed(stream); c = np.array([0] + c)
    w = 50; dens = max(c[t + w] - c[t] for t in range(len(c) - w)) if len(c) > w else c[-1]
    return len(stream) / (nfr * FRAME), dens


def run(sid, spec):
    fr, info = arrange(sid, spec)
    data = SC.encode(fr, info['spec']['tol'], fit=True)
    nfr = len(fr); L = M.length(sid)
    assert abs(nfr * FRAME - L) <= FRAME / 2 + 1e-9, (sid, nfr, L)
    states = sndsim.sound_states(0, {0: data})
    assert len(states) == nfr, (len(states), nfr)
    return data, fr, info, states


def main(ids):
    os.makedirs(EXP, exist_ok=True)
    gap = np.zeros(sndsim.RATE, np.float32)
    summary = []
    for sid in ids:
        name = '%02d_%s' % (sid, SC.NAMES[sid])
        opl_path, psg_path = os.path.join(MUSIC, name + '_midi.wav'), os.path.join(MUSIC, name + '_psg.wav')
        opl = read_wav(opl_path) if os.path.exists(opl_path) else M.opl_render(sid) / max(1e-6, np.abs(M.opl_render(sid)).max()) * 0.7
        cur = read_wav(psg_path) if os.path.exists(psg_path) else sndsim.render(M.psg_states(sid))
        cur_stream = M.stream(sid)[0]
        lines = ['piece %d %s: MIDI %.3f s' % (sid, SC.NAMES[sid], M.length(sid))]
        # the bass boost: 3 steps (the pulse's 6 dB RMS deficit against a square wave); the low-band shares of the
        # alternatives are listed (they hardly move: the 1/15 pulse's energy sits in its harmonics above 130 Hz)
        res = {}
        for b in (1, 3, 5):
            data, fr, info, states = run(sid, dict(arp=1, bass_boost=b)); res[b] = low_share(render_exact(states))
        boost = 3
        lines.append('energy share 20-130 Hz: OPL %.1f dB, current PSG %.1f dB, new PSG with bass boost 1/3/5 steps %s dB '
                     '(boost 3 used; _exp_bass5.wav has 5)' % (opl_low_ := low_share(opl), low_share(cur),
                                                              ' / '.join('%.1f' % res[b] for b in (1, 3, 5))))
        variants = {}
        for tag, sp in (('arp1', dict(arp=1)), ('arp2', dict(arp=2)), ('vib', dict(arp=1, vibrato=1)),
                        ('bass5', dict(arp=1, bass_boost=5))):
            sp = dict(dict(bass_boost=boost), **sp)
            data, fr, info, states = run(sid, sp)
            x = render_exact(states)
            sndsim.write_wav(os.path.join(EXP, '%s_exp_%s.wav' % (name, tag)), x)
            bps, dens = bytes_per_second(data, len(fr))
            mg = sndsim.max_gap(data)
            sim = M.similarity(opl, x)
            variants[tag] = dict(data=data, fr=fr, info=info, states=states, x=x, bps=bps, dens=dens, gap=mg, sim=sim)
            lines.append('  %-5s %5d bytes, %5.1f B/s mean, densest second %3d B, ring survives a refill gap of %s frames, '
                         'chroma similarity to the OPL %.2f' % (tag, len(data), bps, dens, 'any' if mg is None else '%d' % mg, sim))
        cbps, cdens = bytes_per_second(cur_stream, len(variants['arp1']['fr']))
        lines.append('  current: %d bytes, %.1f B/s mean, densest second %d B, gap %s, similarity %.2f' % (
            len(cur_stream), cbps, cdens, sndsim.max_gap(cur_stream), M.similarity(opl, cur)))
        best = 'arp1'
        v = variants[best]
        sndsim.write_wav(os.path.join(EXP, name + '_exp.wav'), v['x'])
        sndsim.write_wav(os.path.join(EXP, name + '_exp_emu.wav'), sndsim.render(v['states']))
        sndsim.write_wav(os.path.join(EXP, name + '_ab.wav'), np.concatenate([opl, gap, cur, gap, v['x']]))
        info = v['info']; ns = info['notes']; snd = info['snd']
        low = info['low']; real = [i for i in low if i in info['used_as_bass']]
        still = [i for i in low if i in info['folded_harm']]
        unused = [i for i in low if i not in info['used_as_bass'] and i not in info['folded_harm']]
        def pitches(ix):
            return ', '.join('%.1f' % f for f in sorted(set(round(snd[i], 1) for i in ix)))
        lines.append('notes below 108.3 Hz (folded up by midi2psg.py): %d of %d; now real bass (periodic noise): %d '
                     '(pitches %s Hz); still folded, in the arpeggio: %d (%s); not sounding (an octave doubling of the bass '
                     'or masked): %d' % (len(low), len(ns), len(real), pitches(real), len(still), pitches(still), len(unused)))
        bass_set = sorted(set(round(snd[i], 1) for i in info['used_as_bass']))
        lines.append('bass pitches used: %s Hz -> channel 2 dividers %s (f2 = 15 x bass: %s Hz)' % (
            ', '.join('%.1f' % f for f in bass_set), ', '.join(str(bass_n(f)) for f in bass_set),
            ', '.join('%.0f' % (15 * f) for f in bass_set)))
        err = max(abs(1200 * np.log2(bass_f(bass_n(f)) / f)) for f in bass_set) if bass_set else 0
        lines.append('bass tuning error of the divider rounding: at most %.0f cents' % err)
        rl = info['roles']; nfr = len(rl)
        fm = sum(1 for r in rl if r['mel'] is not None); fb = sum(1 for r in rl if r['bass'] is not None)
        fh = [len(r['harm']) for r in rl]
        lines.append('roles per frame (%d frames): melody %d, bass %d, arpeggio of 1/2/3 notes: %d/%d/%d, no harmony '
                     '(channel 1 doubles the bass) %d' % (nfr, fm, fb, fh.count(1), fh.count(2), fh.count(3),
                                                           sum(1 for r in rl if not r['harm'] and r['bass'] is not None)))
        mch = sorted(set(ns[i]['ch'] for i in info['mel_notes'])); bch = sorted(set(ns[i]['ch'] for i in info['used_as_bass']))
        lines.append('melody drawn from MIDI channels %s, bass from channels %s' % (mch, bch))
        lines.append('arpeggio rate for _exp.wav: 1 note a frame (50 notes/s; _exp_arp2.wav: 1 per 2 frames); vibrato: '
                     'off in _exp.wav (_exp_vib.wav: +-1 divider step, 6.25 Hz triangle, from the 6th frame of a note)')
        txt = '\n'.join(lines) + '\n'
        open(os.path.join(EXP, name + '_exp.txt'), 'w').write(txt)
        print(txt); summary.append(txt)
    open(os.path.join(EXP, 'summary.txt'), 'w').write('\n'.join(summary))


if __name__ == '__main__':
    ids = [int(x) for x in sys.argv[1:] if x.isdigit()] or [54, 41, 24, 25]
    main(ids)
