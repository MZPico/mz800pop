#!/usr/bin/env python3
"""M7 step 4: the DOS MIDI music arranged for the MZ-800 PSG (3 square tone channels + noise), as streams for the
player in src/m4/psg.asm (format: tools/sndconv.py).

Source: MIDISND1/2.DAT (external/dos/PRINCE, never redistributed): one standard MIDI file per piece (type 0, 480
ticks a beat, 7 channels with one OPL instrument each, many octave doublings). SDLPoP plays them on an OPL3 with
PRINCE.DAT resource 1 as the instrument bank (src/midi.c); its rules are kept here:
  - pitch: note 69 - 12 + semitones = 440 Hz; the SysEx 00 00 34 01 00 nn sets semitones (12 in most pieces, 24 in 26,
    none = an octave lower in 25, 29, 35, 37, 43, 53);
  - timing: the first event's delta is never waited for; tempo meta events; pieces 53 and 54 run 3% faster / slower
    (midi_tempo_modifiers); the piece ends at its end-of-track event (its length = SDLPoP's, the game's waits);
  - loudness: per note the OPL carrier level from the instrument and the velocity.
The loudness of every note over time (attack, decay, sustain, release) is measured, not modelled: SDLPoP's own OPL
code (external/SDLPoP/src/opl3.c, Nuked OPL3) renders each (instrument, velocity, key) once, held as long as its
longest note, and the RMS per 20 ms frame gives its level curve in dB (committed: assets/opl/levels.json, see its
README; new ones are cached in build/sound/opl/levels.json); the same helper renders whole pieces for listening
(build/sound/music/<id>_<name>_midi.wav).

Arrangement (per piece; PIECES below has the per-piece choices and notes):
  1. the notes, pitches folded up by octaves into the PSG's range (>= 108.3 Hz: D5, notes below an octave up, again
     if needed), each with its level curve (on: measured; after the note-off: the measured release);
  2. per 20 ms frame up to 3 notes sound, chosen by importance: level, the top note (melody) and the bottom note (bass)
     get a bonus, a note already playing keeps its channel (hysteresis), a pitch class already chosen counts less
     (octave doublings give way to chord tones); a note that lost its channel does not come back; a note repeating the
     pitch of the note before it on the same channel is re-struck after a 1-frame gap;
  3. levels -> attenuation: att = (piece peak - level) / 2 dB + the piece's offset; below 28 dB = off;
  4. the stream: per channel the attenuation the ISR's envelope produces (an attenuation byte starts a linear decay:
     one step every p frames, p = 0 holds) is fitted to the wanted one (within ATT_TOL steps), so a note costs its
     tone (2 bytes, only if it changes), one attenuation command (2 bytes) and a command per envelope corner.
The length of every stream equals the MIDI length rounded to 20 ms (checked: within 1 frame).
usage: midi2psg.py [--wav] [--list] [ids]   (--wav: build/sound/music/<id>_<name>_{midi,psg,pcspk}.wav + ab_music.wav)"""
import json, os, struct, subprocess, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from datfile import DatFile
ROOT = os.path.join(HERE, '..')
DOS = os.path.join(ROOT, 'external', 'dos', 'PRINCE')
SDLPOP_SRC = os.path.join(ROOT, 'external', 'SDLPoP', 'src')
OPLDIR = os.path.join(ROOT, 'build', 'sound', 'opl')
# the reference level curves the in-game bank is built from (committed: assets/opl/README.md); curves missing there are
# measured into OPLDIR's levels.json (a measurement depends on the run's order, so it is kept out of the normal build)
LEVELS = os.path.join(ROOT, 'assets', 'opl', 'levels.json')
DUMP_USED = None                                # a dict: level_curves records every curve it hands out (--prune-levels)
CPU = 3546895
FRAME = 0.02
TONE_MIN = CPU / (32 * 1023)
TEMPO_MOD = {53: -0.03, 54: 0.03}            # SDLPoP midi_tempo_modifiers
OPL_RATE = 22050                              # the level measurement's sample rate


# ---------------------------------------------------------------- the MIDI data
def _vl(b, p):
    v = 0
    while True:
        c = b[p]; p += 1; v = (v << 7) | (c & 127)
        if not c & 128: return v, p

def midi(sid):
    """the piece's events: dict(tpq, ev=[(tick, kind, ch, p1, p2)]) with kind 0x80/0x90/0xC0 channel events,
    0xF0 SysEx semitones (p1), 0x51 tempo (p1 = us a beat, as written), 0x2F the end, 0x00 the file's first event
    (whatever it is); other events dropped"""
    d = DatFile(os.path.join(DOS, 'MIDISND1.DAT' if sid < 50 else 'MIDISND2.DAT'))
    r = d.resource(10000 + sid)[1:]
    assert r[:4] == b'MThd'
    fmt, nt, tpq = struct.unpack('>HHH', r[8:14]); assert fmt == 0 and nt == 1
    p = 14; assert r[p:p + 4] == b'MTrk'
    end = p + 8 + struct.unpack('>I', r[p + 4:p + 8])[0]; p += 8
    t = 0; last = 0; ev = []; first = None
    while p < end:
        dt, p = _vl(r, p); t += dt
        if first is None: first = t; ev.append((t, 0x00, 0, 0, 0))       # (the file's first event: SDLPoP never
                                                                            # waits for its delta; kept as a no-op)
        s = r[p]
        if s & 0x80: p += 1
        else: s = last
        if s < 0xF0: last = s
        hi = s & 0xF0
        if hi in (0x80, 0x90, 0xA0, 0xB0, 0xE0):
            if hi == 0x90 and r[p + 1] == 0: ev.append((t, 0x80, s & 15, r[p], 0))
            elif hi in (0x80, 0x90): ev.append((t, hi, s & 15, r[p], r[p + 1]))
            p += 2
        elif hi in (0xC0, 0xD0):
            if hi == 0xC0: ev.append((t, 0xC0, s & 15, r[p], 0))
            p += 1
        elif s in (0xF0, 0xF7):
            l, p = _vl(r, p); x = r[p:p + l]; p += l
            if l == 7 and x[2] == 0x34 and x[3] in (0, 1) and x[4] == 0: ev.append((t, 0xF0, 0, x[5], 0))
        elif s == 0xFF:
            ty = r[p]; p += 1; l, p = _vl(r, p); x = r[p:p + l]; p += l
            if ty == 0x51: ev.append((t, 0x51, 0, int.from_bytes(x, 'big'), 0))
            if ty == 0x2F: ev.append((t, 0x2F, 0, 0, 0)); break
    return dict(tpq=tpq, ev=ev)

def seconds(sid, m=None):
    """tick -> seconds as SDLPoP plays it (tempo map with the tempo modifier; the first event at 0)"""
    m = m or midi(sid); mod = TEMPO_MOD.get(sid, 0.0)
    pts = [(0, 0.0, 500000)]
    for t, k, c, p1, p2 in m['ev']:
        if k == 0x51:
            t0, s0, us = pts[-1]; pts.append((t, s0 + (t - t0) * us / m['tpq'] / 1e6, int(p1 * (1.0 + mod))))
    def f(t):
        i = max(j for j in range(len(pts)) if pts[j][0] <= t)
        t0, s0, us = pts[i]; return s0 + (t - t0) * us / m['tpq'] / 1e6
    return f

def length(sid):
    """the piece's length in seconds (its end-of-track event)"""
    m = midi(sid); return seconds(sid, m)(m['ev'][-1][0])

def instruments():
    r = DatFile(os.path.join(DOS, 'PRINCE.DAT')).resource(1)
    return r[0], r[1:1 + 16 * r[0]]

def notes(sid):
    """[dict(t0, t1 (s), ch, key, vel, prog, pk (the key as played: 69 = 440 Hz), f (Hz))] in start order"""
    m = midi(sid); sec = seconds(sid, m)
    prog = {c: c for c in range(16)}; semis = 0; on = {}; out = []
    for t, k, c, p1, p2 in m['ev']:
        if k == 0xC0: prog[c] = p1
        elif k == 0xF0: semis = p1
        elif k == 0x90:
            if (c, p1) in on: out.append(dict(on.pop((c, p1)), t1=sec(t)))   # (a retrigger ends the note)
            on[(c, p1)] = dict(t0=sec(t), ch=c, key=p1, vel=p2, prog=prog[c], pk=p1 - 12 + semis,
                               f=440.0 * 2 ** ((p1 - 69 - 12 + semis) / 12.0))
        elif k == 0x80 and (c, p1) in on: out.append(dict(on.pop((c, p1)), t1=sec(t)))
    end = sec(m['ev'][-1][0])
    for n in on.values(): out.append(dict(n, t1=end))
    return sorted(out, key=lambda n: (n['t0'], n['ch']))


# ---------------------------------------------------------------- SDLPoP's OPL playback (a helper program)
POPMIDI_C = r'''
/* SDLPoP's MIDI playback (src/midi.c: play_midi_sound, midi_callback, midi_note_on/off, process_midi_event) with its
   Nuked OPL3 (src/opl3.c), outside the game: written by tools/midi2psg.py. stdin: "rate tpq modifier chanmask", the
   instrument count and 16 hex bytes each, then events "delta kind ch p1 p2" (kind hex: 80, 90, C0, F0 = semitones,
   51 = tempo, 2F = end). stdout: raw 16-bit stereo samples. */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
#include "opl3.h"
typedef uint8_t byte; typedef uint16_t word; typedef uint32_t dword;
#define NV 9
typedef struct { byte mul, ksl_tl, a_d, s_r, waveform; } op_t;
typedef struct { byte bl, bh, FB_conn; op_t ops[2]; byte perc, unk[2]; } ins_t;
static opl3_chip chip; static ins_t ins[256]; static int nins;
static byte vnote[NV]; static int vins[NV], vch[NV], chins[16], lastv, semis; static dword uspb; static float tmod;
static unsigned chmask; static byte cache[512];
static word rpo[] = {0x000,0x001,0x002,0x003,0x004,0x005,0x008,0x009,0x00A,0x00B,0x00C,0x00D,0x010,0x011,0x012,0x013,
  0x014,0x015,0x100,0x101,0x102,0x103,0x104,0x105,0x108,0x109,0x10A,0x10B,0x10C,0x10D,0x110,0x111,0x112,0x113,0x114,0x115};
static word rso[] = {0,1,2,3,4,5,6,7,8,0x100,0x101,0x102,0x103,0x104,0x105,0x106,0x107,0x108};
static byte sbop[] = {0,1,2,6,7,8,12,13,14,18,19,20,24,25,26,30,31,32};
static void wr(word r, byte v) { OPL3_WriteReg(&chip, r, v); cache[r] = v; }
static void wrm(word r, byte v, byte m) { wr(r, (cache[r] & ~m) | (v & m)); }
static word rpair(int v, int op) { word o = rpo[sbop[v]]; if (op) o += 3; return o; }
static void wins(ins_t *i, int v) {
  wr(0xC0 + rso[v], i->FB_conn | 0x30);
  for (int o = 0; o < 2; o++) { op_t *p = &i->ops[o]; word r = rpair(v, o);
    wr(0x20 + r, p->mul); wr(0x40 + r, p->ksl_tl); wr(0x60 + r, p->a_d); wr(0x80 + r, p->s_r); wr(0xE0 + r, p->waveform); }
}
static ins_t *gins(int id) { return (id >= 0 && id < nins) ? &ins[id] : &ins[0]; }
static void noff(int ch, int note) {
  for (int v = 0; v < NV; v++) if (vch[v] == ch && vnote[v] == note) { wrm(0xB0 + rso[v], 0, 0x20); vnote[v] = 0; break; }
}
static void non(int ch, int note, int vel) {
  if (!((chmask >> ch) & 1)) return;
  if (vel == 0) { noff(ch, note); return; }
  int id = chins[ch]; ins_t *in = gins(id); int voice = -1, t = lastv;
  for (int i = 0; i < NV; i++) { ++t; t %= NV; if (vnote[t] == 0) { voice = t; break; } }
  lastv = voice;
  if (voice < 0) return;
  if (vins[voice] != id) { wins(in, voice); vins[voice] = id; }
  vnote[voice] = note; vch[voice] = ch;
  float oct = ((int)note - 69 - 12 + semis) / 12.0f; float fr = powf(2.0f, oct) * 440.0f;
  float fn = fr * (float)(1 << 20) / 49716.0f; int block = (int)(log2f(fn) - 9) & 7; int f = ((int)fn >> block) & 1023;
  word ro = rso[voice];
  wr(0xA0 + ro, f & 0xFF); wr(0xB0 + ro, 0x20 | (block << 2) | (f >> 8));
  wrm(0x40 + rpair(voice, 0), in->ops[0].ksl_tl, 0x3F);
  int iv = in->ops[1].ksl_tl & 0x3F; int cv = ((iv + 64) * 225) / (vel + 161);
  if (cv < 64) cv = 64; if (cv > 127) cv = 127; cv -= 64;
  wrm(0x40 + rpair(voice, 1), cv, 0x3F);
}
typedef struct { dword dt; int kind, ch, p1, p2; } ev_t;
static ev_t ev[200000];
int main(void) {
  int rate, tpq, n = 0;
  if (scanf("%d %d %f %x %d", &rate, &tpq, &tmod, &chmask, &nins) != 5) return 1;
  for (int i = 0; i < nins; i++) for (int k = 0; k < 16; k++) { unsigned x; if (scanf("%2x", &x) != 1) return 1; ((byte *)&ins[i])[k] = x; }
  while (n < 200000 && scanf("%u %x %d %d %d", &ev[n].dt, &ev[n].kind, &ev[n].ch, &ev[n].p1, &ev[n].p2) == 5) n++;
  OPL3_Reset(&chip, rate); memset(cache, 0, sizeof cache); wr(0x105, 1);
  for (int v = 0; v < NV; v++) { wins(&ins[0], v); vins[v] = 0; vnote[v] = 0; }
  for (int c = 0; c < 16; c++) chins[c] = c;
  semis = 0; uspb = 500000; lastv = 0;
  int64_t pos = 0, nextp = 0; float fract = 0; int ttnp = 0, idx = 0;
  static int16_t buf[2 * 4096];
  for (;;) {
    if (ttnp > 0) {
      int64_t us_np = (int64_t)ttnp * uspb / tpq, us_need = 4096LL * 1000000 / rate, adv = us_np < us_need ? us_np : us_need;
      int avail = (int)((adv * rate + 999999) / 1000000), af = avail < 4096 ? avail : 4096;
      adv = (int64_t)af * 1000000 / rate;
      OPL3_GenerateStream(&chip, buf, af); fwrite(buf, 4, af, stdout);
      float tef = (float)adv * tpq / uspb; int64_t te = (int64_t)tef; fract += tef - te;
      if (fract > 1.0f) { fract -= 1.0f; te += 1; }
      pos += te; ttnp -= te;
    } else {
      int done = 0;
      while (pos >= nextp) {
        if (idx >= n) { done = 1; break; }
        ev_t *e = &ev[idx++];
        switch (e->kind) {
          case 0x80: noff(e->ch, e->p1); break;
          case 0x90: non(e->ch, e->p1, e->p2); break;
          case 0xC0: chins[e->ch] = e->p1; break;
          case 0xF0: semis = e->p1; break;
          case 0x51: uspb = (dword)(e->p1 * (1.0f + tmod)); break;
        }
        if (idx < n && ev[idx].dt) nextp += ev[idx].dt;
      }
      if (done) break;
      ttnp = (int)(nextp - pos);
    }
  }
  return 0;
}
'''

def popmidi():
    """the helper's binary (compiled into build/sound/opl/ when missing or older than this file)"""
    os.makedirs(OPLDIR, exist_ok=True)
    exe = os.path.join(OPLDIR, 'popmidi'); src = os.path.join(OPLDIR, 'popmidi.c')
    if not os.path.exists(exe) or os.path.getmtime(exe) < os.path.getmtime(__file__):
        open(src, 'w').write(POPMIDI_C)
        subprocess.run(['gcc', '-O2', '-o', exe, src, os.path.join(SDLPOP_SRC, 'opl3.c'), '-I', SDLPOP_SRC, '-lm'],
                       check=True)
    return exe

def opl_run(tpq, ev, rate, mod=0.0, chmask=0xFFFF):
    """ev [(tick, kind, ch, p1, p2)] -> mono float samples (SDLPoP's OPL playback)"""
    n, bank = instruments()
    lines = ['%d %d %f %x %d' % (rate, tpq, mod, chmask, n), ' '.join('%02x' % b for b in bank)]
    prev = 0
    for t, k, c, p1, p2 in ev:
        lines.append('%d %x %d %d %d' % (t - prev, k, c, p1, p2)); prev = t
    r = subprocess.run([popmidi()], input=('\n'.join(lines) + '\n').encode(), stdout=subprocess.PIPE, check=True)
    x = np.frombuffer(r.stdout, '<i2').astype(np.float32).reshape(-1, 2).mean(axis=1) / 32768.0
    return x

def opl_render(sid, rate=44100, chmask=0xFFFF):
    m = midi(sid); return opl_run(m['tpq'], m['ev'], rate, TEMPO_MOD.get(sid, 0.0), chmask)


# ---------------------------------------------------------------- the level curves
REL_FRAMES = 150                 # the release measured for 3 s after the note-off
FLOOR_DB = -90.0

def _frames_db(x, rate):
    n = int(round(rate * FRAME)); k = len(x) // n
    r = np.sqrt((x[:k * n].reshape(k, n).astype(np.float64) ** 2).mean(axis=1)) + 1e-9
    return np.maximum(20 * np.log10(r), FLOOR_DB)

def level_curves(combos):
    """{(prog, vel, key): (on dB per frame for `hold` frames, release dB per frame from the note-off)} for combos
    {(prog, vel, key): hold frames}; each measured alone (one note at a time on channel 0), cached"""
    key = lambda c: '%d,%d,%d' % c
    fixed = json.load(open(LEVELS)) if os.path.exists(LEVELS) else {}
    path = os.path.join(OPLDIR, 'levels.json')
    cache = json.load(open(path)) if os.path.exists(path) else {}
    from_ref = set()
    for c in combos:
        k = key(c)
        if k in fixed and len(fixed[k][0]) >= combos[c]: cache[k] = fixed[k]; from_ref.add(c)
    stale = [c for c in combos if c not in from_ref and key(c) in cache and len(cache[key(c)][0]) >= combos[c]]
    if stale:
        print('midi2psg: %d level curves come from %s, not from %s (measured in an earlier run: the bank differs from '
              'the reference build: docs/ci.md)' % (len(stale), os.path.relpath(path, ROOT), os.path.relpath(LEVELS, ROOT)),
              file=sys.stderr)
    if DUMP_USED is not None: DUMP_USED.update({key(c): cache[key(c)] for c in combos if key(c) in cache})
    todo = [c for c in combos if key(c) not in cache or len(cache[key(c)][0]) < combos[c]]
    if todo:
        print('midi2psg: %d level curves not in %s, measured into %s (the bank then differs from the reference '
              'build: docs/ci.md)' % (len(todo), os.path.relpath(LEVELS, ROOT), os.path.relpath(path, ROOT)), file=sys.stderr)
    if todo:
        # one run: per combo a program change, the note held `hold` frames, the release, 0.2 s of silence
        tpq = 500; ev = []; t = 0                   # 120 bpm (the default tempo): 1000 ticks a second, 20 a frame
        spans = []
        for c in todo:
            prog, vel, k = c; hold = combos[c] + 10
            ev.append((t, 0xC0, 0, prog, 0)); ev.append((t, 0xF0, 0, 12, 0))
            ev.append((t, 0x90, 0, k, vel)); ev.append((t + 20 * hold, 0x80, 0, k, 0))
            spans.append((c, t, hold)); t += 20 * (hold + REL_FRAMES + 10)
        ev.append((t, 0x2F, 0, 0, 0))
        x = opl_run(tpq, ev, OPL_RATE)
        db = _frames_db(x, OPL_RATE)
        for c, t0, hold in spans:
            f0 = t0 // 20
            cache[key(c)] = [[round(v, 2) for v in db[f0:f0 + hold]], [round(v, 2) for v in db[f0 + hold:f0 + hold + REL_FRAMES]]]
        json.dump(cache, open(path, 'w'))
    return {c: (np.array(cache[key(c)][0]), np.array(cache[key(c)][1])) for c in combos}


# ---------------------------------------------------------------- the arrangement
# per program: the octave the OPL instrument sounds in, relative to the written note (its strongest low partial,
# measured: carrier/modulator multipliers 2 and 2 sound an octave up, 0.5 an octave down)
PROG_SHIFT = {2: 12, 7: 12, 3: -12, 11: -12, 15: -12}
ATT_RANGE = 14                   # attenuation 0..14 (2 dB steps, 28 dB); quieter = off
DEFAULTS = dict(
    voices=3,                    # tone channels used
    offset=0,                    # attenuation added to every note (after the piece's peak = 0)
    top=12.0, bass=5.0,           # dB bonus of the highest / lowest sounding note (melody, bass)
    keep=8.0,                    # dB bonus of a note that has a channel
    onset=8.0, onset_frames=3,   # dB bonus of a note's first frames
    dup=20.0,                    # dB penalty of a pitch class already chosen
    aweight=0.5,                 # loudness of a folded note: this share of the A-weighting difference
    refill=True,                 # a note that lost its channel may take a free one again (a held chord stays full)
    tol=1,                       # attenuation tolerance of the envelope fit (steps)
    drop=(),                     # MIDI channels left out
    shift={},                    # per MIDI channel: semitones added (after PROG_SHIFT)
)

def tone_n(f): return max(1, min(1023, int(round(CPU / (32.0 * f)))))

def fold(f):
    while f < TONE_MIN: f *= 2.0
    return f

def a_weight(f):
    """the A-weighting in dB (IEC 61672) at f Hz"""
    f2 = f * f
    ra = 12194.0 ** 2 * f2 * f2 / ((f2 + 20.6 ** 2) * np.sqrt((f2 + 107.7 ** 2) * (f2 + 737.9 ** 2)) * (f2 + 12194.0 ** 2))
    return 20 * np.log10(ra) + 2.0

def note_levels(ns, curves):
    """per note: (first frame, level dB per frame from it) until it is 60 dB under its peak"""
    out = []
    for n in ns:
        on, rel = curves[(n['prog'], n['vel'], n['pk'])]
        f0 = int(round(n['t0'] / FRAME)); f1 = max(f0 + 1, int(round(n['t1'] / FRAME)))
        d = f1 - f0
        lv = list(on[:d]) + [on[min(d, len(on)) - 1] + (r - on[-1]) for r in rel]
        lv = np.array(lv)
        out.append((f0, lv))
    return out

def arrange(sid, spec=None):
    """the piece as PSG states per frame (sndconv.State) and the arrangement's notes"""
    import sndconv as SC
    sp = dict(DEFAULTS); sp.update(spec or PIECES.get(sid, {}))
    ns = [n for n in notes(sid) if n['ch'] not in sp['drop']]
    nfr = int(round(length(sid) / FRAME))
    combos = {}
    for n in ns:
        c = (n['prog'], n['vel'], n['pk']); combos[c] = max(combos.get(c, 0), int(round((n['t1'] - n['t0']) / FRAME)) + 1)
    curves = level_curves(combos)
    lv = note_levels(ns, curves)
    # the sounding pitch of each note: the instrument's octave, the channel's shift, folded into the PSG's range
    snd = [n['f'] * 2 ** ((PROG_SHIFT.get(n['prog'], 0) + sp['shift'].get(n['ch'], 0)) / 12.0) for n in ns]
    # a note moved up keeps its loudness: the level corrected by the ear's sensitivity at the two pitches (half the
    # A-weighting difference: a 50 Hz bass folded to 100-200 Hz sounds much louder at the same level)
    lv = [(f0, l + sp['aweight'] * (a_weight(f) - a_weight(fold(f)))) for (f0, l), f in zip(lv, snd)]
    peak = max(l.max() for f0, l in lv)
    floor = peak - 2.0 * (ATT_RANGE - sp['offset']) - 1.0
    tn = [tone_n(fold(f)) for f in snd]
    pc = [int(round(12 * np.log2(fold(f) / 440.0))) % 12 for f in snd]
    # per frame: the pitch groups (one per tone divider: unisons after the fold merge) and their level
    chans = [None] * sp['voices']                # the group (divider) on each channel
    banned = set()                                # groups that lost their channel (until a new onset)
    frames = [SC.State() for _ in range(nfr)]
    choice = []
    for f in range(nfr):
        groups = {}
        for i, (f0, l) in enumerate(lv):
            k = f - f0
            if k < 0 or k >= len(l) or l[k] < floor: continue
            g = groups.setdefault(tn[i], dict(level=-999.0, onset=False, lo=1e9, hi=0.0, pc=pc[i], age=999))
            g['level'] = max(g['level'], l[k]); g['lo'] = min(g['lo'], snd[i]); g['hi'] = max(g['hi'], snd[i])
            if k < sp['onset_frames']: g['age'] = min(g['age'], k)
            if k == 0: g['onset'] = True
        for n_ in list(banned):
            if n_ not in groups or groups[n_]['onset']: banned.discard(n_)
        cand = {n_: g for n_, g in groups.items() if n_ not in banned}
        back = {n_: g for n_, g in groups.items() if n_ in banned} if sp['refill'] else {}
        top_g = bass_g = None
        if cand:                                  # the melody / bass: the loudest note of the top / bottom pitch class
            hi = max(cand, key=lambda k: cand[k]['hi']); lo = min(cand, key=lambda k: cand[k]['lo'])
            top_g = max((k for k in cand if cand[k]['pc'] == cand[hi]['pc']), key=lambda k: (cand[k]['level'], k))
            if len(cand) > 1:
                bass_g = max((k for k in cand if cand[k]['pc'] == cand[lo]['pc'] and k != top_g),
                             key=lambda k: (cand[k]['level'], -k), default=None)
        def score(n_, g, chosen_pc):
            s = g['level']
            if n_ == top_g: s += sp['top']
            if n_ == bass_g: s += sp['bass']
            if n_ in chans: s += sp['keep']
            if g['age'] < sp['onset_frames']: s += sp['onset']
            if g['pc'] in chosen_pc: s -= sp['dup']
            return s
        chosen = []; cpc = set()
        left = dict(cand)
        while left and len(chosen) < sp['voices']:
            best = max(left, key=lambda n_: score(n_, left[n_], cpc))
            chosen.append(best); cpc.add(left[best]['pc']); del left[best]
        for c in range(sp['voices']):                    # channels keep their group; the dropped ones are banned
            if chans[c] is not None and chans[c] not in chosen:
                if chans[c] in groups: banned.add(chans[c])
                chans[c] = None
        for n_ in chosen:
            if n_ in chans: continue
            c = chans.index(None); chans[c] = n_
        while back and None in chans:                    # free channels: the loudest dropped notes come back
            n_ = max(back, key=lambda k: back[k]['level'] - (sp['dup'] if back[k]['pc'] in cpc else 0))
            if back[n_]['pc'] in cpc and len(back) == 1 and False: break
            chans[chans.index(None)] = n_; cpc.add(back[n_]['pc']); banned.discard(n_); del back[n_]
        st = frames[f]
        for c, n_ in enumerate(chans):
            if n_ is None: continue
            g = groups[n_]
            a = int(round((peak - g['level']) / 2.0)) + sp['offset']
            if a > ATT_RANGE: continue
            st.tone[c] = n_; st.att[c] = max(0, a)
            st.onset = getattr(st, 'onset', set()); 
            if g['onset']: st.onset.add(c)
            choice.append(list(chans))
    # a re-struck note on a channel whose level does not rise: the frame before it silent
    for f in range(1, nfr):
        for c in getattr(frames[f], 'onset', ()):
            p = frames[f - 1]
            if p.tone[c] == frames[f].tone[c] and p.att[c] < 15 and frames[f].att[c] >= p.att[c] - 1:
                p.att[c] = 15
    # the reference for the listening aids: per frame the pitch-class amplitudes of all notes and the top note's class
    ref = np.zeros((nfr, 12)); top = [None] * nfr
    for i, (f0, l) in enumerate(lv):
        for k in range(len(l)):
            f = f0 + k
            if f >= nfr: break
            if l[k] < floor: continue
            ref[f, pc[i]] += 10 ** ((l[k] - peak) / 20.0)
            if top[f] is None or snd[i] > top[f][0]: top[f] = (snd[i], pc[i])
    return frames, dict(peak=peak, notes=len(ns), ref=ref, top=top)

def score(frames, info):
    """(harmony, melody): the mean cosine of the pitch-class amplitudes (PSG vs all MIDI notes, weighted by the MIDI's
    energy) and the share of frames whose top MIDI note's pitch class sounds on the PSG"""
    ref, top = info['ref'], info['top']; h = w = m = mn = 0.0
    for f, st in enumerate(frames):
        e = np.linalg.norm(ref[f])
        if e <= 0: continue
        v = np.zeros(12)
        for c in range(3):
            if st.att[c] < 15 and st.tone[c]:
                v[int(round(12 * np.log2(CPU / 32.0 / st.tone[c] / 440.0))) % 12] += 10 ** (-st.att[c] / 10.0)
        h += e * (v @ ref[f]) / (np.linalg.norm(v) * e + 1e-12); w += e
        mn += 1; m += 1 if v[top[f][1]] > 0 else 0
    return h / max(w, 1e-12), m / max(mn, 1)

PIECES = {
    56: dict(top=30.0, why='the ending (124.7 s): melody on channels 0/4/5 in three octaves, a busy bass and broken '
             'chords on 2/3 (400 notes each); the melody bonus raised (30 dB) so the tune always keeps a voice'),
}

def stream(sid, spec=None):
    """(stream bytes, the note for sound.txt, frames) of a piece"""
    import sndconv as SC
    sp = dict(DEFAULTS); sp.update(spec or PIECES.get(sid, {}))
    fr, info = arrange(sid, sp)
    data = SC.encode(fr, sp['tol'], fit=True)
    nfr = len(fr); L = length(sid)
    assert abs(nfr * FRAME - L) <= FRAME / 2 + 1e-9, (sid, nfr, L)
    h, m = score(fr, info)
    nch = len(set(n['ch'] for n in notes(sid)))
    folded = sum(1 for n in notes(sid) if n['f'] * 2 ** (PROG_SHIFT.get(n['prog'], 0) / 12.0) < TONE_MIN)
    why = (sp.get('why', 'MIDI') + ': %d notes on %d MIDI channels -> %d voices, %d notes folded up; harmony %.2f, '
           'melody %.2f; %.2f s (MIDI %.3f s)' % (info['notes'], nch, sp['voices'], folded, h, m, nfr * FRAME, L))
    return data, why, nfr


# ---------------------------------------------------------------- listening aids
def chroma(x, rate=44100, hop=0.05, lo=100.0, hi=4000.0):
    """pitch-class energy per hop (12 x n), each column normalised"""
    n = int(rate * 0.1); h = int(rate * hop); win = np.hanning(n)
    fr = np.fft.rfftfreq(n, 1.0 / rate); sel = (fr >= lo) & (fr <= hi)
    pcs = (np.round(12 * np.log2(fr[sel] / 440.0)) % 12).astype(int)
    cols = []
    for i in range(0, max(1, len(x) - n), h):
        X = np.abs(np.fft.rfft(x[i:i + n] * win))[sel] ** 2
        c = np.bincount(pcs, X, 12); cols.append(c / (np.linalg.norm(c) + 1e-12))
    return np.array(cols).T

def similarity(a, b, rate=44100):
    """mean cosine similarity of the two signals' chroma (where the reference sounds)"""
    ca, cb = chroma(a, rate), chroma(b, rate); n = min(ca.shape[1], cb.shape[1])
    ea = np.array([np.sqrt((a[int(i * 0.05 * rate):int(i * 0.05 * rate) + 4410] ** 2).mean()) for i in range(n)])
    m = ea > ea.max() * 0.05
    return float((ca[:, :n] * cb[:, :n]).sum(axis=0)[m].mean())

def psg_states(sid, data=None):
    import sndsim
    if data is None: data = stream(sid)[0]
    return sndsim.sound_states(0, {0: data})

def write_wavs(ids):
    """build/sound/music/<id>_<name>_{midi,psg,pcspk}.wav and build/sound/ab_music.wav (per piece: SDLPoP's OPL
    playback of the MIDI, the PC-speaker tune, the PSG arrangement, 0.7 s apart)"""
    import sndconv as SC, sndsim
    out = os.path.join(ROOT, 'build', 'sound'); gap = np.zeros(int(0.7 * 44100), np.float32); ab = []
    for sid in ids:
        name = '%02d_%s' % (sid, SC.NAMES[sid]); d = os.path.join(out, 'music')
        opl = opl_render(sid); opl = opl / max(1e-6, np.abs(opl).max()) * 0.7
        psg = sndsim.render(psg_states(sid)); sp = sndsim.speaker(sid)
        sndsim.write_wav(os.path.join(d, name + '_midi.wav'), opl)
        sndsim.write_wav(os.path.join(d, name + '_psg.wav'), psg)
        if sp is not None: sndsim.write_wav(os.path.join(d, name + '_pcspk.wav'), sp)
        ab += [opl, gap] + ([sp, gap] if sp is not None else []) + [psg, gap, gap]
        print('  %s: midi %.2f s, psg %.2f s, chroma similarity to the MIDI: psg %.2f%s' % (
            name, len(opl) / 44100.0, len(psg) / 44100.0, similarity(opl, psg),
            '' if sp is None else ', speaker %.2f s' % (len(sp) / 44100.0)))
    sndsim.write_wav(os.path.join(out, 'ab_music.wav'), np.concatenate(ab))
    print('wrote build/sound/music/*_{midi,psg,pcspk}.wav, build/sound/ab_music.wav')

if __name__ == '__main__':
    import sndconv as SC
    a = sys.argv[1:]
    ids = [int(x) for x in a if x.isdigit()] or sorted(SC.MUSIC)
    if '--list' in a or not a or '--wav' not in a:
        for sid in ids:
            d, why, n = stream(sid); print('%2d %-22s %5d frames %5d bytes: %s' % (sid, SC.NAMES[sid], n, len(d), why))
    if '--wav' in a: write_wavs(ids)
