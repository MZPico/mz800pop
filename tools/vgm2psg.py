#!/usr/bin/env python3
"""SN76489 register logs (the Sega Master System Prince of Persia soundtrack, logged by tools/sms/songlog.lua in
MAME) or VGM files -> VGM files, the MZ-800 PSG stream format (tools/sndconv.py) and WAVs rendered through the
player model (tools/sndsim.py). Nothing here touches the game, its banks or the tests: everything goes to
build/sound/sms/ (the ROM-derived logs stay outside the project, see tools/sms/run_song.py).

Pipeline per piece:
  1. the log: lines "w <frame> <hex>" (one PSG byte, the 50 Hz frame it was written in), "p <frame> c9 c8 cb cc d2"
     (the SMS driver's position: song-table index, row, tick, music flag, sfx flag) -> the bytes per frame
  2. the register state after every frame (sndsim.Psg: latch/data semantics as mz800emu) -> the piece's end: a
     music piece ends when the driver reaches its end position 0 (what follows in the log is the game's own
     attract-mode music), an sfx when its flag clears; without that, the loop (the shortest period after which the
     audible state sequence repeats to the end of the log, checked against the position trace) or the trailing
     silence
  3. a VGM (v1.50, SN76489 at the source clock, 50 Hz frames, loop offset/length set) for ordinary players
  4. the MZ-800 streams: the dividers rescaled to the MZ-800's clock (N' = round(N x MZ / SRC); noise rate bits as
     they are), then per frame a group of the changed registers (tone latch + data, noise control, attenuation
     + period byte) and a wait byte. Two variants:
       <name>.psg      exact: p = 0 (held) and every attenuation change is a command (the SMS driver does its own
                       envelopes per frame, so this is 1 attenuation byte pair per sounding channel per frame)
       <name>_env.psg  approximate: an attenuation command only where the wanted value leaves the player's envelope
                       by more than 1 step (2 dB) or gets louder, with the period that follows the wanted curve
                       longest (tools/midi2psg.py's rule); tones exact
     The player's envelope (p = 0 steps the attenuation up every 256 frames) is simulated in both. Every stream is
     replayed through sndsim.Player and must reproduce the wanted states (within 1 step for _env).
  5. WAVs: the exact stream as the player plays it, through sndsim.render (mz800emu's chip: 16-bit LFSR, periodic
     noise f/16) -> <n>_<name>.wav; the _env stream -> <n>_<name>_env.wav; and through midi2psg_exp.render_exact
     (the real SN76489AN: 15-bit LFSR, f/15) -> <n>_<name>_exact.wav when the piece uses periodic noise
  6. the numbers: frames, seconds, loop, bytes, bytes/s, the densest 1 s, the longest refill gap the 253-byte ring
     survives (docs/m7-design.md 13: the game needs ~120 frames), the worst pitch error of the rescaling

usage: vgm2psg.py --logs DIR [--out build/sound/sms] [--only n,m] [--no-wav]   every music_<n>.log / sfx_<n>.log
       vgm2psg.py --vgm FILE --name NAME [--out DIR]                            one VGM (clock from its header)
       vgm2psg.py --vgm FILE --info                                             only the analysis"""
import argparse, math, os, struct, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import sndconv as SC
import sndsim
OUT = os.path.join(HERE, '..', 'build', 'sound', 'sms')

SMS_CLK_PAL = 3546893           # Hz: the PAL Master System's Z80 / PSG clock (53.203424 MHz / 15)
SMS_CLK_NTSC = 3579545          # the NTSC one (the same ROM runs on both; this is the (E) release on a PAL console)
MZ_CLK = SC.CPU                 # 3546895: the MZ-800's PSG clock (tools/sndconv.py, src/m4/psg.asm)
FPS = 50                        # the MZ-800's frame (the PAL SMS runs its driver at 49.70 Hz: 0.6% slower)
SAMPLES = 882                   # VGM samples (44.1 kHz) per 50 Hz frame
RING_FRAMES = 120               # the in-game refill gap the ring must survive (docs/m7-design.md 13)
PERIODS = [0] + list(range(1, 64)) + [64, 80, 96, 128, 160, 192, 255]   # the envelope periods the _env encoder tries

# The pieces: SMS driver song number -> (file name, what it is). The DOS mapping is in build/sound/sms/index.txt.
PIECES = {
    1: ('title', 'title screen music (also the attract mode\'s first piece)'),
    3: ('story_credits', 'intro story, first part: the palace with the princess and the credits'),
    5: ('story_jaffar', 'intro story, second part: Jaffar in the palace (chained after 3 by the game)'),
    7: ('cutscene', 'the between-level cutscene piece (called from five cutscene character scripts; SMS Power\'s "Mirror '
        'Prince", the one track of their SMS pack the Game Gear pack lacks)'),
    8: ('grand_vizier', 'SMS Power\'s "Grand Vizier" (the Game Gear pack\'s track of that name is the same piece); called by '
        'the ending script interpreter (not reached in the emulator; by code only); PRES plays it for Jaffar\'s screens'),
    10: ('potion', 'the potion jingle (the potion-drinking code, one piece for all potions)'),
    11: ('hourglass', 'the looping piece of the "minutes left" hourglass screen and the demo play'),
    14: ('level_start', 'played when a level starts (after the hourglass screen); the game is silent after it'),
    15: ('death', 'the death music (fall, spikes, chomper, sword)'),
    16: ('level_end', 'played when the kid walks into the exit door (SMS Power\'s "Get Sword", as the Game Gear pack\'s)'),
}
SFX = list(range(17, 35))


# ---------------------------------------------------------------- input
def read_log(path):
    """-> (frames: list of lists of bytes, one per frame from the start marker; pos: {frame: (c9, c8, cb, cc, d2)})"""
    frames, pos = [], {}
    for line in open(path):
        p = line.split()
        if not p: continue
        if p[0] == 'w':
            f = int(p[1])
            while len(frames) <= f: frames.append([])
            frames[f].append(int(p[2], 16))
        elif p[0] == 'p':
            pos[int(p[1])] = tuple(int(x) for x in p[2:7])
    n = max(len(frames), (max(pos) + 1) if pos else 0)
    while len(frames) < n: frames.append([])
    return frames, pos

def read_vgm(path):
    """-> (frames of bytes at 50 Hz, loop frame or None, SN76489 clock)"""
    d = open(path, 'rb').read()
    assert d[:4] == b'Vgm ', 'not a VGM'
    version = struct.unpack_from('<I', d, 8)[0]
    clock = struct.unpack_from('<I', d, 0x0C)[0] & 0x3FFFFFFF
    loop_off = struct.unpack_from('<I', d, 0x1C)[0]
    loop_abs = loop_off + 0x1C if loop_off else None
    data = struct.unpack_from('<I', d, 0x34)[0] + 0x34 if version >= 0x150 else 0x40
    frames, cur, samples, loop_frame = [], [], 0, None
    p = data
    while p < len(d):
        if loop_abs is not None and p == loop_abs: loop_frame = len(frames)
        c = d[p]
        if c == 0x50: cur.append(d[p + 1]); p += 2
        elif c == 0x61: samples += struct.unpack_from('<H', d, p + 1)[0]; p += 3
        elif c == 0x62: samples += 735; p += 1
        elif c == 0x63: samples += 882; p += 1
        elif 0x70 <= c <= 0x7F: samples += (c & 15) + 1; p += 1
        elif c == 0x66: break
        elif c == 0x4F: p += 2
        elif 0x51 <= c <= 0x5F: p += 3
        else: raise ValueError('VGM command %02X not supported' % c)
        while samples >= SAMPLES:
            frames.append(cur); cur = []; samples -= SAMPLES
    if cur: frames.append(cur)
    return frames, loop_frame, clock

def write_vgm(path, frames, loop_frame, clock):
    body = bytearray(); loop_abs = None
    for i, fr in enumerate(frames):
        if loop_frame is not None and i == loop_frame: loop_abs = 0x40 + len(body)
        for b in fr: body += bytes((0x50, b))
        body.append(0x63)
    body.append(0x66)
    h = bytearray(0x40)
    h[0:4] = b'Vgm '
    struct.pack_into('<I', h, 4, 0x40 + len(body) - 4)
    struct.pack_into('<I', h, 8, 0x150)
    struct.pack_into('<I', h, 0x0C, clock)
    struct.pack_into('<I', h, 0x18, len(frames) * SAMPLES)
    if loop_abs is not None:
        struct.pack_into('<I', h, 0x1C, loop_abs - 0x1C)
        struct.pack_into('<I', h, 0x20, (len(frames) - loop_frame) * SAMPLES)
    struct.pack_into('<I', h, 0x24, FPS)
    struct.pack_into('<H', h, 0x28, 0x0009); h[0x2A] = 16        # SN76489: feedback 0x0009, 16-bit shift register
    struct.pack_into('<I', h, 0x34, 0x40 - 0x34)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, 'wb').write(bytes(h) + bytes(body))


# ---------------------------------------------------------------- analysis
def states_of(frames):
    """the Psg.state() tuple after every frame's writes"""
    psg = sndsim.Psg(); out = []
    for fr in frames:
        for b in fr: psg.write(b)
        out.append(psg.state())
    return out

MUTE = (15, 15, 15, 15)

def audible_key(st):
    """the state reduced to what sounds (muted channels' tones do not matter; tone 2 matters for noise rate 3)"""
    att = (st[0], st[2], st[4], st[6])
    t = (st[1] if att[0] < 15 else None, st[3] if att[1] < 15 else None,
         st[5] if (att[2] < 15 or (att[3] < 15 and st[7] == 3)) else None)
    return (att, t, (st[7], st[8]) if att[3] < 15 else None)

def trim(keys, n):
    """n without the trailing silence"""
    while n > 0 and keys[n - 1][0] == MUTE: n -= 1
    return n

def analyse(frames, pos=None, kind='music', min_period=25):
    """-> dict(end=frames of a one-shot piece or None, loop=(start, period[, note]) or None, nframes, how)"""
    keys = [audible_key(s) for s in states_of(frames)]
    n = len(keys)
    if pos:                                               # the driver's own end
        for f in sorted(pos):
            if f < 2: continue
            if (kind == 'music' and pos[f][0] == 0) or (kind == 'sfx' and pos[f][4] == 0):
                return dict(end=trim(keys, f), loop=None, nframes=n, how='driver end at frame %d' % f)
    e = trim(keys, n)
    if n - e >= FPS: return dict(end=e, loop=None, nframes=n, how='silent to the end')
    for P in range(min_period, n // 2 + 1):
        L = 0
        for i in range(n - P - 1, -1, -1):
            if keys[i] != keys[i + P]: L = i + 1; break
        if n - L >= int(1.5 * P) + 1:
            loop = [L, P]
            if pos and not all(pos.get(i)[:3] == pos.get(i + P)[:3] for i in range(L, n - P) if i in pos and i + P in pos):
                loop.append('position trace differs')
            return dict(end=None, loop=tuple(loop), nframes=n, how='loop found')
    return dict(end=e, loop=None, nframes=n, how='no end and no loop in the log')


# ---------------------------------------------------------------- conversion
def rescale(states, src_clk, dst_clk=MZ_CLK):
    """the tone dividers for the destination clock; -> (states, worst error in cents, the divider that has it)"""
    r = dst_clk / float(src_clk); out = []; worst = (0.0, None)
    for s in states:
        s = list(s)
        for i in (1, 3, 5):
            N = s[i]
            if N == 0: continue
            M = max(1, min(1023, int(round(N * r))))
            cents = 1200 * math.log2(dst_clk * N / (src_clk * M))
            if abs(cents) > abs(worst[0]): worst = (cents, N)
            s[i] = M
        out.append(tuple(s))
    return out, worst[0], worst[1]

def encode(states, approx=False, loop=None):
    """the MZ-800 stream (tools/sndconv.py's format) that makes the player produce `states`, one per frame;
    approx: the attenuations through the player's envelopes within 1 step (see the module doc).
    loop (M7 step 11, tools/presbank.py): the stream repeats from frame `loop` forever: its group writes every
    channel's attenuation (resetting the envelopes), the tones and the noise it needs, so the state is the same
    whether the group is reached from the intro or from the end; the stream then ends with its last wait, no end
    byte (the bank adds the loop command 0xE8 lo hi), and (stream, the loop group's byte offset) is returned"""
    want = [(s[0], s[2], s[4], s[6]) for s in states]
    att = [15] * 4; tone = [None] * 3; noise = None      # the chip as the player left it (start: muted, unknown tones)
    env = [[15, 0, 0] for _ in range(4)]                  # the player's envelopes (attenuation, counter, period)
    out = bytearray(); pending_wait = 0; groups = 0; loop_off = None; force = False

    def run_len(c, i, a, p):
        """frames after i during which the envelope started with (a, p) stays within a step of the wanted curve"""
        v, cnt, k = a, p, 0
        for j in range(i + 1, len(want)):
            if v < 15:
                cnt = (cnt - 1) & 255
                if cnt == 0: v += 1; cnt = p
            w = want[j][c]
            if w < v or w > v + 1 or (w == 15) != (v == 15): break
            k += 1
        return k

    def flush_wait():
        nonlocal pending_wait
        while pending_wait > 127: out.append(127); pending_wait -= 127
        if pending_wait: out.append(pending_wait); pending_wait = 0

    for i, st in enumerate(states):
        for c, e in enumerate(env):                       # the ISR's envelope step before the group
            if e[0] < 15:
                e[1] = (e[1] - 1) & 255
                if e[1] == 0: e[0] += 1; e[1] = e[2]; att[c] = e[0]
        wa = want[i]; grp = bytearray()
        if i == loop: tone = [None] * 3; noise = None; force = True      # (the chip's state at the loop's end is unknown here)
        for c in range(3):
            need = wa[c] < 15 or (c == 2 and wa[3] < 15 and st[7] == 3)
            N = st[1 + 2 * c]
            if need and tone[c] != N:
                grp += bytes((0x80 | (c << 5) | (N & 15), (N >> 4) & 0x3F)); tone[c] = N
        if wa[3] < 15 and noise != (st[7], st[8]):
            grp.append(0xE0 | (st[8] << 2) | st[7]); noise = (st[7], st[8])
        for c in range(4):
            a, v = wa[c], att[c]
            need = force or ((a < v or a > v + 1 or (a == 15) != (v == 15)) if approx else a != v)
            if need:
                p = 0
                if approx and a < 15: p = max(PERIODS, key=lambda q: run_len(c, i, a, q))
                grp.append(0x90 | (c << 5) | a); att[c] = a; env[c] = [a, p, p]
                if a != 15: grp.append(p)
        force = False
        if grp or groups == 0:
            if groups: flush_wait()
            if i == loop: loop_off = len(out)
            out += grp; groups += 1
        pending_wait += 1
    flush_wait()
    if loop is None: out.append(0); return bytes(out)
    assert loop_off is not None
    return bytes(out), loop_off

def loop_states(states, loop, frames):
    """the wanted state per frame of a looping piece played for `frames` frames"""
    n = len(states)
    return [states[i if i < n else loop + (i - n) % (n - loop)] for i in range(frames)]

def verify(stream, states, approx=False, loop=None, loop_off=None):
    """the player's states for the stream, checked against the wanted ones (a looping stream: through the model's
    loop command, for the piece and two and a half more loops)"""
    if loop is None: got = sndsim.sound_states(0, {0: stream})
    else:
        n = len(states); frames = n + (n - loop) * 5 // 2 + 3
        got = sndsim.sound_states(0, sndsim.Bank({0: stream}, {0: loop_off}), frames)
        states = loop_states(states, loop, frames)
    assert len(got) == len(states), ('length', len(got), len(states))
    for i, (g, w) in enumerate(zip(got, states)):
        kg, kw = audible_key(g), audible_key(w)
        if approx:
            assert all(abs(x - y) <= 1 and (x == 15) == (y == 15) for x, y in zip(kg[0], kw[0])), ('att', i, g, w)
            assert kg[1:] == kw[1:], ('frame', i, g, w)
        else:
            assert kg == kw, ('frame', i, g, w)
    return got

def budget(stream):
    """(bytes, max bytes the player reads in any 1 s, max in any RING_FRAMES frames, the longest refill gap in frames
    the ring survives (None: the stream fits whole))"""
    c = np.array([0] + sndsim.consumed(stream))
    def win(w): return int((c[w:] - c[:-w]).max()) if len(c) > w else int(c[-1])
    dens1 = win(FPS); densr = win(RING_FRAMES)
    if len(stream) < SC.RING: gap = None
    else:
        lo, hi = 1, len(c) - 1                            # the largest g with win(g) <= RING - 1 (monotone)
        while lo < hi:
            m = (lo + hi + 1) // 2
            if win(m) <= SC.RING - 1: lo = m
            else: hi = m - 1
        gap = lo
    return len(stream), dens1, densr, gap

def uses_periodic(states): return any(s[6] < 15 and s[8] == 0 for s in states)
def uses_noise(states): return any(s[6] < 15 for s in states)


# ---------------------------------------------------------------- one piece
def convert(frames, name, out, src_clk, pos=None, kind='music', info=None, wav=True):
    info = info or analyse(frames, pos, kind)
    if info['end'] is not None: n = info['end']
    elif info['loop']: n = info['loop'][0] + info['loop'][1]
    else: n = info['nframes']
    loop = info['loop'][0] if info['loop'] else None
    frames = frames[:n]
    states = states_of(frames)
    res = dict(name=name, frames=n, seconds=n / float(FPS), loop=loop, how=info['how'],
               loop_len=(info['loop'][1] if info['loop'] else None),
               loop_note=(info['loop'][2] if info['loop'] and len(info['loop']) > 2 else ''),
               periodic=uses_periodic(states), noise=uses_noise(states), files=[], var={})
    os.makedirs(out, exist_ok=True)
    vgm = os.path.join(out, name + '.vgm'); write_vgm(vgm, frames, loop, src_clk); res['files'].append(vgm)
    mz, res['cents'], res['worstN'] = rescale(states, src_clk)
    for approx, suffix in ((False, ''), (True, '_env')):
        stream = encode(mz, approx); got = verify(stream, mz, approx)
        psg = os.path.join(out, name + suffix + '.psg'); open(psg, 'wb').write(stream); res['files'].append(psg)
        nbytes, dens1, densr, gap = budget(stream)
        res['var'][suffix] = dict(bytes=nbytes, dens1=dens1, densr=densr, gap=gap,
                                  bps=nbytes / res['seconds'] if n else 0.0)
        if wav:
            w = os.path.join(out, name + suffix + '.wav'); sndsim.write_wav(w, sndsim.render(got)); res['files'].append(w)
            if res['periodic'] and not approx:
                import midi2psg_exp
                w2 = os.path.join(out, name + '_exact.wav'); sndsim.write_wav(w2, midi2psg_exp.render_exact(got))
                res['files'].append(w2)
    return res

def describe(r):
    lp = ('loops: %.2f s intro + %.2f s loop' % (r['loop'] / float(FPS), r['loop_len'] / float(FPS)) if r['loop'] is not None
          else 'one-shot')
    if r.get('loop_note'): lp += ' (%s)' % r['loop_note']
    s = '%-14s %6.2f s (%4d frames) %s [%s]; noise: %s; worst pitch error %.3f cents\n' % (
        r['name'], r['seconds'], r['frames'], lp, r['how'],
        'periodic + white' if r['periodic'] and r['noise'] else 'periodic' if r['periodic'] else 'white' if r['noise'] else 'none',
        r['cents'])
    for suffix, v in r['var'].items():
        gap = 'fits the ring whole' if v['gap'] is None else 'survives a %d-frame refill gap' % v['gap']
        s += '    %-5s %5d bytes, %5.1f B/s, densest 1 s %3d B, densest %d frames %3d B, %s%s\n' % (
            suffix or 'exact', v['bytes'], v['bps'], v['dens1'], RING_FRAMES, v['densr'], gap,
            '' if v['gap'] is None or v['gap'] >= RING_FRAMES else ' (NOT ENOUGH for the game: needs %d)' % RING_FRAMES)
    return s.rstrip()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--logs'); ap.add_argument('--vgm'); ap.add_argument('--name'); ap.add_argument('--out', default=OUT)
    ap.add_argument('--only'); ap.add_argument('--info', action='store_true'); ap.add_argument('--no-wav', action='store_true')
    ap.add_argument('--clock', type=int, default=SMS_CLK_PAL, help='the source PSG clock of a log (default PAL)')
    a = ap.parse_args()
    if a.vgm:
        frames, loop, clk = read_vgm(a.vgm)
        info = analyse(frames)
        if loop is not None and not info['loop']: info = dict(end=None, loop=(loop, len(frames) - loop), nframes=len(frames), how='VGM loop')
        if a.info: print(info); return
        r = convert(frames, a.name or os.path.splitext(os.path.basename(a.vgm))[0], a.out, clk, info=info, wav=not a.no_wav)
        print(describe(r)); return
    only = set(int(x) for x in a.only.split(',')) if a.only else None
    results = []
    for kind, nums in (('music', sorted(PIECES)), ('sfx', SFX)):
        for n in nums:
            if only and n not in only: continue
            path = os.path.join(a.logs, '%s_%d.log' % (kind, n))
            if not os.path.exists(path): print('missing', path); continue
            frames, pos = read_log(path)
            nm = PIECES[n][0] if kind == 'music' else 'sfx%d' % n
            r = convert(frames, '%02d_%s' % (n, nm), a.out, a.clock, pos=pos, kind=kind, wav=not a.no_wav)
            r['n'] = n; r['kind'] = kind; print(describe(r)); results.append(r)
    if not only: write_index(results, a.out, a.clock)
    return results


# The DOS cue -> SMS piece mapping (from the game's call sites of the driver's play-music routine, see the module
# doc of tools/sms/run_song.py and the report in the index): DOS id -> (SMS song or None, note)
DOS_MAP = {
    24: (15, 'the death music: the SMS plays song 15 at every death (fall, spikes, chomper, sword)'),
    25: (14, 'the level 1 start: song 14 is played by the level-start code'),
    26: (None, 'no embrace piece found (the SMS ending, song 8, is one piece)'),
    27: (7, 'the cutscene pieces: song 7 is called from five cutscene character scripts'),
    28: (15, 'as 24: the SMS has one death music'),
    29: (None, 'no Jaffar-meeting piece found'),
    30: (10, 'the potions: song 10 is played by the potion-drinking code (one jingle for all potions)'),
    32: (None, 'no shadow piece found'),
    33: (10, 'as 30'),
    35: (7, 'as 27'),
    36: (None, 'no out-of-time piece found (not reached; song 8 could also be this: its caller is a script interpreter)'),
    37: (None, 'no victory piece found'),
    39: (None, 'no feather-fall piece'),
    40: (7, 'as 27'),
    41: (16, 'the level end: song 16 is played when the kid walks into the exit door'),
    43: (None, 'no Jaffar-victory piece found'),
    50: (3, 'the intro story: the SMS plays song 3 (first part) then song 5 (the palace scene, chained)'),
    52: (5, 'as 50'),
    53: (5, 'as 50'),
    54: (1, 'the title music: song 1 (11.4 s; the DOS title is 25.0 s)'),
    55: (3, 'as 50'),
    56: (8, 'the ending: song 8 is played by a script interpreter (12.4 s; the DOS ending is 124.7 s); identified by code only'),
}

def write_index(results, out, clock):
    import kidsim
    by = {r['n']: r for r in results if r['kind'] == 'music'}
    L = ['SMS Prince of Persia (E) soundtrack -> MZ-800 PSG streams (tools/vgm2psg.py, tools/sms/run_song.py)', '',
         'Source: the SN76489 register writes of the game\'s sound driver, logged in MAME (smspal, PAL 50 Hz) while',
         'each piece was started directly through the driver\'s play routine (no gameplay). Clocks: SMS PAL %d Hz,' % clock,
         'MZ-800 %d Hz: ratio %.7f, the dividers are rescaled (worst error below). One SMS frame = one MZ-800 frame' % (MZ_CLK, MZ_CLK / float(clock)),
         '(the PAL SMS frame is 49.70 Hz, the MZ-800 50 Hz: 0.6%% faster here). Ring budget: %d bytes, %d frames (docs/m7-design.md 13).' % (SC.RING - 1, RING_FRAMES),
         'Files per piece: .vgm (standard, loop set), .psg (exact stream), _env.psg (envelope-approximated stream),',
         '.wav (the exact stream through sndsim), _env.wav, _exact.wav (real-chip noise model, where periodic noise is used).', '']
    L.append('== pieces'); L.append('')
    for r in results:
        L.append(describe(r))
        if r['kind'] == 'music': L.append('    %s' % PIECES[r['n']][1])
        L.append('    files: ' + ', '.join(os.path.basename(f) for f in r['files']))
        L.append('')
    L.append('== DOS cues (tools/kidsim.py SOUND_SECONDS) -> SMS'); L.append('')
    for sid, (sms, note) in sorted(DOS_MAP.items()):
        dos_len = kidsim.SOUND_SECONDS[sid]
        if sms is not None and sms in by:
            r = by[sms]
            s = 'SMS song %d (%s): %.2f s, %s' % (sms, PIECES[sms][0], r['seconds'], 'loops' if r['loop'] is not None else 'one-shot')
        elif sms is not None: s = 'SMS song %d (not converted)' % sms
        else: s = 'no SMS counterpart'
        L.append('%2d %-24s DOS %7.3f s -> %s' % (sid, SC.NAMES[sid], dos_len, s))
        L.append('   %s' % note)
    open(os.path.join(out, 'index.txt'), 'w').write('\n'.join(L) + '\n')

if __name__ == '__main__':
    main()
