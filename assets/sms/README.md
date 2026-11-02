# assets/sms: the presentation music (Master System Prince of Persia, converted)

**Not covered by the GPL.** These files are derived from the music of the Sega Master System *Prince of Persia*
(Domark, 1992): third-party music, not part of this project's GPL-3 code. They are kept here, converted, so that the
port builds without the cartridge ROM; their copyright stays with its holders.

## What they are

The five pieces the presentation program PRES plays (`tools/presbank.py`, docs/m7-design.md §19), each as an MZ-800
PSG stream (the format of `tools/sndconv.py`, played by `src/m4/psg.asm`): the SN76489 register writes of the
Master System game's own sound driver, logged per frame, with the tone dividers rescaled to the MZ-800's clock
(ratio 1.0000006, worst error 0.001 cents) and every attenuation change kept (the "exact" variant). No samples, no
code of the game.

| File | SMS song | Frames (50 Hz) | Loop | Bytes | PRES |
|---|---|---|---|---|---|
| `01_title.psg` | 1 | 570 (11.40 s) | whole | 3,436 | the title, the main picture, the ending |
| `03_story_credits.psg` | 3 | 501 (10.02 s) | one-shot | 3,039 | the credits |
| `05_story_jaffar.psg` | 5 | 1,220 (24.40 s) | whole | 5,331 | Jaffar's scene, "Marry Jaffar" |
| `07_cutscene.psg` | 7 | 432 (8.64 s) | one-shot | 2,046 | the level cutscenes |
| `11_hourglass.psg` | 11 | 985 (19.70 s) | from frame 25 (byte 56) | 3,480 | the story text, the time-out |

`pieces.json` gives per piece its frame count, the loop frame and the loop group's byte offset in the stream
(`null` for a one-shot), the size and the md5; `tools/presbank.py` checks them and builds
`build/assets/sound_pres.bin`, `sound_pres_b.bin`, `sound_pres_c.bin` from these streams and the game's effects.
A one-shot stream ends with the end byte 0; a looping one ends with its last wait (the bank appends the loop command
`0xE8 lo hi`), and its loop group writes the whole chip state so the loop is seamless.

No other piece, log, VGM, disassembly or screenshot of the Master System game is in the repository.

## How they were made

1. The ROM: *Prince of Persia (Europe)* for the Sega Master System, md5 `70e9b330dd6a91e7310f3c8d9a934ecc` (the
   user's own copy, kept outside the project and never copied into it).
2. `tools/sms/run_song.py` runs it headless in MAME 0.264 (driver `smspal`, PAL 50 Hz, with a stub BIOS of our own)
   with the Lua autoboot script `tools/sms/songlog.lua`, which starts one piece directly through the game's sound
   driver and logs the writes to the PSG port per frame (`logs/music_<n>.log`).
3. `tools/vgm2psg.py --logs DIR` turns the logs into VGM files with their loop points (`build/sound/sms/<nn>_<name>.vgm`,
   plus the analysis in `build/sound/sms/index.txt` and WAVs to listen to).
4. `tools/presbank.py --from-vgm build/sound/sms` encodes the five pieces PRES uses for the MZ-800 (the loop group where
   the piece loops), verifies each stream against the logged states through the player model `tools/sndsim.py`, and
   writes this folder.

## Regenerating them (local only)

Ripping is a manual, local process: it needs the ROM and MAME and never runs in CI or in the normal build (`make`
reads only this folder).

```
for n in 1 3 5 7 11; do python3 tools/sms/run_song.py --rom /path/to/pop_e.sms --work /tmp/sms music $n 6000; done
python3 tools/vgm2psg.py --logs /tmp/sms/logs --only 1,3,5,7,11
python3 tools/presbank.py --from-vgm build/sound/sms
git diff --stat assets/sms     # nothing, if the ROM, MAME and the tools are the same
make build/assets/sound_pres.bin   # the banks (they need the in-game bank, so the DOS data: tools/ci/fetch_dos_data.py)
```

The banks made from the committed streams are byte-identical to those of the original build from the VGMs
(`sound_pres.bin` md5 `85fcc5d863b406471a9d01fe02ffd837`, `sound_pres_b.bin` `fe4eb77f73fcb3838bd29b74b2160299`,
`sound_pres_c.bin` `5524da905ca9d1c6f7aa53a76ba4180c`).
