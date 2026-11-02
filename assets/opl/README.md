# assets/opl: the OPL level curves of the in-game music

`levels.json` holds the loudness curves `tools/midi2psg.py` arranges the DOS MIDI music for the PSG with: per
(OPL program, velocity, MIDI key) used by the music, the level in dB of that note per 20 ms frame while it is held,
and for 3 s (150 frames) after its note-off. They are **measurements, not music data**: each note was rendered by
SDLPoP's OPL3 emulation (`external/SDLPoP/src/opl3.c`, Nuked OPL3, with the DOS game's instrument bank) and its RMS
taken per frame (`midi2psg.level_curves`). 700 curves, every one the current pieces use.

## Why they are committed

A curve depends on the order it was measured in: `level_curves` renders all the missing notes in one run on one
emulated chip, one after another, so a note's curve depends on what was played before it on that chip (the voice it
gets, what the other voices still hold): measured alone, 24 of 25 sampled curves differ from the cached ones, by up to
~13-20 dB in some frames. The local cache
(`build/sound/opl/levels.json`) grew over the development, so a clean build measured the notes in a different order
and produced a different bank (2378 bytes instead of 2328). Measuring each note on a fresh chip is order-independent
but does not give the reference values either, and every test baseline (`tests/perf_baseline.json`, the m4/m7
recordings) was made with the reference bank. So the reference curves are kept here and the build reads them.

With them `make` builds `build/assets/sound.bin` byte-identical to the reference: 2,328 bytes, md5
`5272e60564b3655e63e04e879c858f1c`; no OPL rendering runs at all.

## Changing the music

A curve missing here (a new piece, another velocity or key, a longer note) is measured as before into
`build/sound/opl/levels.json` and `midi2psg.py` says so on stderr. To make it part of the build, add those entries
(from that file) to `levels.json` here, one line per curve, sorted by key; keep the existing ones unless the bank is
meant to change (then the baselines change with it).
