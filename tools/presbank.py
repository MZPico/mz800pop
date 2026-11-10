#!/usr/bin/env python3
"""M7 step 11: the presentation's sound banks (PRES, src/pres/pres.asm) from the Master System Prince of Persia
soundtrack (assets/sms/: the five pieces as MZ-800 PSG streams, converted from the driver's register logs; see
assets/sms/README.md) and our effects (build/assets/sound.bin, tools/sndconv.py). docs/m7-design.md 19 (the mapping
decided 2026-11-01).
The streams are a stored artifact: the build reads them, it never needs the ROM. --from-vgm DIR remakes them (locally,
from the logs tools/sms/run_song.py + tools/vgm2psg.py made from the ROM: DIR = build/sound/sms): each piece's VGM ->
the states per frame -> the tones rescaled to the MZ-800's clock -> the exact stream (with the loop group for a looping
piece), checked against the states through tools/sndsim.py; writes assets/sms/<piece>.psg and assets/sms/pieces.json.

The pieces (exact streams: every attenuation change a command, the tones rescaled to the MZ-800's clock) and where
they loop (the loop command 0xE8 lo hi after the stream: psg.asm snd_fill, tools/sndsim.py):
  title      SMS 1  11.40 s  loops whole               title steps a-f and j, the ending (embrace, hail, TITLE_MAIN)
  hourglass  SMS 11 19.70 s  loops from 0.50 s (SMS)   the story text g (into h until Jaffar's piece starts), time_expired
  jaffar     SMS 5  24.40 s  loops whole               pv_scene (h) from its first cue, "Marry Jaffar" (i)
  credits    SMS 3  10.02 s  one-shot (k cuts it)      the credits k
  cutscene   SMS 7   8.64 s  one-shot                  the level cutscenes (the level starts when it ends)
Three banks (each <= SBANK_MAX = 10 KB, the torch cache page 6 0x0000-0x287F; sndconv's layout, addresses from 0:
57 index entries of (address, length) then the streams; an id's entry aliases the piece its DOS cue plays; a cue
whose entry is empty starts nothing in PRES: cut.asm play_next_sound):
  A sound_pres.bin    hourglass (55 g, 36 time_expired), title (54, 26 the embrace), cutscene (27, 35, 40), effects
                      the title a-g, the level cutscenes, time_expired, the ending (POP800.PRS entry PRS_SOUND)
  B sound_pres_b.bin  hourglass (55: the same address as in A, so g's stream goes on through h's black and fade-in
                      after the reload), jaffar (50: pv_scene's first cue), effects but 4 and 51 (pv_scene's cues
                      4, 51, 53, 52 start nothing: the loop goes on)   (PRS_SND_B, loaded at h)
  C sound_pres_c.bin  title (54: j), credits (PM_CREDITS 42: k), effects   (PRS_SND_C, loaded between i and j)
Writes build/assets/sound_pres.txt (the layout) and with --wav build/sound/pres/model_<piece>.wav (the model: the
piece and one loop more, tools/sndsim.py render).
usage: presbank.py [--wav]
       presbank.py --from-vgm DIR      (remakes assets/sms/ from DIR/<piece>.vgm only: the banks are `make
                                       build/assets/sound_pres.bin`, which needs build/assets/sound.bin)"""
import hashlib, json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import sndconv as SC
import sndsim
import vgm2psg as V
ASSETS = os.path.join(HERE, '..', 'assets', 'sms')    # the stored streams (assets/sms/README.md)
OUT = os.path.join(HERE, '..', 'build', 'assets')
WAV = os.path.join(HERE, '..', 'build', 'sound', 'pres')
SBANK_MAX = 0x2880                  # pres.asm SBANK_MAX (the torch cache)
PM_CREDITS = 42                     # pres.asm: k's music (an id without a DOS sound)

# name: (VGM, loop: None one-shot, 'vgm' the VGM's loop point, 0 the whole piece)
PIECES = {'title': ('01_title', 0), 'hourglass': ('11_hourglass', 'vgm'), 'jaffar': ('05_story_jaffar', 0),
          'credits': ('03_story_credits', None), 'cutscene': ('07_cutscene', None)}
FRAMES = {'title': 570, 'hourglass': 985, 'jaffar': 1220, 'credits': 501, 'cutscene': 432}   # (index.txt; asserted)
# the banks: (file, PRS entry name, [pieces in bank order], {id: piece}, effects left out)
BANKS = [('sound_pres.bin', 'PRS_SOUND', ['hourglass', 'title', 'cutscene'],
          {55: 'hourglass', 36: 'hourglass', 54: 'title', 26: 'title', 27: 'cutscene', 35: 'cutscene', 40: 'cutscene'}, set()),
         ('sound_pres_b.bin', 'PRS_SND_B', ['hourglass', 'jaffar'], {55: 'hourglass', 50: 'jaffar'}, {4, 51}),
         ('sound_pres_c.bin', 'PRS_SND_C', ['title', 'credits'], {54: 'title', PM_CREDITS: 'credits'}, set())]
SHARED = ('hourglass',)             # at the same address in every bank that has it (A -> B: the stream goes on)


def convert(name, vgmdir):
    """the piece from its VGM (--from-vgm): -> (stream, loop frame or None, the loop group's byte offset or None, frames)"""
    fn, lp = PIECES[name]
    frames, vloop, clk = V.read_vgm(os.path.join(vgmdir, fn + '.vgm'))
    assert len(frames) == FRAMES[name], (name, len(frames))
    states = V.states_of(frames)
    mz, cents, _ = V.rescale(states, clk)
    assert abs(cents) < 0.01
    loop = vloop if lp == 'vgm' else lp
    if loop is None:
        stream = V.encode(mz); V.verify(stream, mz); off = None
    else:
        stream, off = V.encode(mz, loop=loop); V.verify(stream, mz, loop=loop, loop_off=off)
    return stream, loop, off, len(frames)


def from_vgm(vgmdir):
    """remakes assets/sms/<piece>.psg and pieces.json from the VGMs in vgmdir"""
    os.makedirs(ASSETS, exist_ok=True)
    man = {}
    for n in PIECES:
        stream, loop, off, nfr = convert(n, vgmdir)
        fn = PIECES[n][0]
        open(os.path.join(ASSETS, fn + '.psg'), 'wb').write(stream)
        man[n] = dict(file=fn + '.psg', sms_song=int(fn[:2]), frames=nfr, loop_frame=loop, loop_offset=off,
                      bytes=len(stream), md5=hashlib.md5(stream).hexdigest())
    with open(os.path.join(ASSETS, 'pieces.json'), 'w') as f:
        json.dump(man, f, indent=1); f.write('\n')
    print('wrote', os.path.normpath(ASSETS), '(%s)' % ', '.join('%s %d B' % (m['file'], m['bytes']) for m in man.values()))


def piece(name):
    """the stored piece (assets/sms/pieces.json) -> dict(stream, loop_off, frames, loop, gap)"""
    m = json.load(open(os.path.join(ASSETS, 'pieces.json')))[name]
    stream = open(os.path.join(ASSETS, m['file']), 'rb').read()
    assert len(stream) == m['bytes'] and hashlib.md5(stream).hexdigest() == m['md5'], (name, 'assets/sms changed?')
    assert m['frames'] == FRAMES[name] and m['file'] == PIECES[name][0] + '.psg', name
    loop, off = m['loop_frame'], m['loop_offset']
    assert (loop is None) == (off is None) and (loop is None) == (PIECES[name][1] is None), name
    if loop is None: assert stream[-1] == 0, name                  # a one-shot ends with the end byte
    else: assert 0 <= off < len(stream), name                      # a looping one with its last wait (the bank adds 0xE8)
    gap = sndsim.max_gap(stream, off, m['frames'] * 3)
    return dict(stream=stream, loop_off=off, frames=m['frames'], loop=loop, gap=gap)


def build(verbose=True, wav=False):
    P = {n: piece(n) for n in PIECES}
    gb = sndsim.load_bank(os.path.join(OUT, 'sound.bin'))
    # (a looping effect, the level door's sliding 15, is one pass here: PRES never plays it; its end byte back)
    eff = {i: s + bytes(1) if i in gb.loops else s for i, s in gb.items() if i not in SC.MUSIC}
    assert all(s[-1] == 0 for s in eff.values())
    lines = ['# generated by tools/presbank.py: the presentation\'s sound banks (Master System pieces + our effects)',
             '# piece: SMS frames, loop (frame, stream byte offset), bytes, the longest refill gap survived (frames)']
    for n, p in P.items():
        lines.append('%-9s %4d frames %6.2f s, %s, %4d bytes, gap %s' % (
            n, p['frames'], p['frames'] / 50.0, 'one-shot' if p['loop'] is None else 'loops at frame %d (byte %d)' % (p['loop'], p['loop_off']),
            len(p['stream']), p['gap'] if p['gap'] is not None else 'fits the ring'))
    shared_at = {}
    banks = {}
    for fn, ent, order, ids, no_eff in BANKS:
        bank = bytearray(SC.NIDS * 4); addr = {}
        for n in order:
            p = P[n]
            if n in SHARED and n in shared_at: assert shared_at[n] == len(bank), (fn, n)
            addr[n] = len(bank); bank += p['stream']
            if p['loop'] is not None: bank += bytes([0xE8]) + struct.pack('<H', addr[n] + p['loop_off'])
            if n in SHARED: shared_at[n] = addr[n]
        for sid in sorted(eff):
            if sid in no_eff: continue
            struct.pack_into('<HH', bank, sid * 4, len(bank), len(eff[sid])); bank += eff[sid]
        for sid, n in ids.items():
            assert not struct.unpack_from('<H', bank, sid * 4 + 2)[0]
            struct.pack_into('<HH', bank, sid * 4, addr[n], len(P[n]['stream']))
        assert len(bank) <= SBANK_MAX, (fn, len(bank))
        os.makedirs(OUT, exist_ok=True)
        open(os.path.join(OUT, fn), 'wb').write(bytes(bank)); banks[fn] = bytes(bank)
        chk = sndsim.load_bank(bytes(bank), 0)
        for sid, n in ids.items():
            assert chk[sid] == P[n]['stream'] and chk.loops.get(sid) == P[n]['loop_off'], (fn, sid)
        lines.append('%s (%s): %d bytes (%d free): %s; effects %s' % (
            fn, ent, len(bank), SBANK_MAX - len(bank), ', '.join('%d -> %s @%d' % (s, n, addr[n]) for s, n in sorted(ids.items())),
            'all' if not no_eff else 'all but %s' % sorted(no_eff)))
    open(os.path.join(OUT, 'sound_pres.txt'), 'w').write('\n'.join(lines) + '\n')
    if verbose: print('\n'.join(lines))
    if wav:
        os.makedirs(WAV, exist_ok=True)
        for n, p in P.items():
            fr = p['frames'] if p['loop'] is None else p['frames'] + (p['frames'] - p['loop'])
            st = sndsim.sound_states(0, sndsim.Bank({0: p['stream']}, {0: p['loop_off']} if p['loop'] is not None else None), fr)
            sndsim.write_wav(os.path.join(WAV, 'model_%s.wav' % n), sndsim.render(st))
        print('wrote', WAV, '(model_<piece>.wav: the piece and one loop)')
    return banks, P


if __name__ == '__main__':
    if '--from-vgm' in sys.argv:
        from_vgm(sys.argv[sys.argv.index('--from-vgm') + 1])
        print('assets/sms remade; build the banks with: make build/assets/sound_pres.bin')
    else:
        build(wav='--wav' in sys.argv)
