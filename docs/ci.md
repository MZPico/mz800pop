# CI: the PR checks

`.github/workflows/pr-checks.yml` runs on every pull request to `main` (and by hand: *Actions → PR checks → Run
workflow*). It builds the port from a clean checkout on GitHub's standard Ubuntu 24.04 runner (2 vCPU) and runs the
**PR tier**, a selection of the tests that keeps each job at or under ~22 minutes. The full gates stay local (below).

## What a run does

Four matrix jobs (`a` to `d`) run in parallel; each one:

1. **Packages**: pasmo 0.5.3 (Ubuntu's package, the version used locally), p7zip-full, Xvfb, SDL2 / SDL2_image
   (SDLPoP), the emulator's build dependencies; Python 3.12 with `requirements.txt` (numpy, Pillow: the versions of
   Ubuntu 24.04's packages used locally).
2. **Tools** (`tools/ci/build_deps.sh`), each from its public source at the commit the local copy is on, kept in the
   actions cache by that version and rebuilt only on a cache miss:
   - SDL3 `release-3.4.14`, SDL3_image `release-3.4.4`, minizip-ng `4.2.2` (mz800emu needs them; not packaged in
     Ubuntu 24.04), into `~/mzdeps`
   - mz800emu (https://github.com/MZPico/mz800emu) at `MZ800EMU_COMMIT`, into `~/mz800emu-bin`;
     `emu/mz800emu-pop.sh` runs the binary named by `MZ800EMU_BIN` (default: the local build
     `/home/matyamar/src/mz800emu/build/build-mz800emu/mz800emu`), with `emu/mz800emu.ini` next to the script
   - SDLPoP (https://github.com/NagyD/SDLPoP) at `SDLPOP_COMMIT` + `tools/sdlpop-pop800.patch`, `make -C src`, into
     `external/SDLPoP` (the oracle `prince`; its `data/` comes with the clone)
   - mzdisk (https://github.com/michalhucik/mzdisk) at `MZDISK_COMMIT`, into `external/mzdisk/build` (upstream's
     CMakeLists.txt at that commit names a missing `sharpmz_utf8.c`; the script drops that line, as the local copy does)

   The commits are in the workflow's `env:` (and as defaults in `build_deps.sh`): bump them together.
3. **The DOS data**: `tools/ci/fetch_dos_data.py` (below).
4. **Build**: `make ci-build` = `make assets`, then everything `make` builds (the game disk `build/pop800.dsk` too:
   below) plus `build/m4test.mzf`.
5. **The PR tier**: `make check-pr PART=a` (`b`, `c`, `d`) under `xvfb-run` (the emulator needs an X display).

Nothing built is passed between the jobs: no artifacts (the build holds converted game art and the repository is
public), each job builds for itself (~1 min).

## The PR tier

`tools/ci/check_pr.py` holds the list (`python3 tools/ci/check_pr.py --list`). Locally: `make ci-build` (or `make` and
`make build/m4test.mzf`), then `make check-pr` runs all four parts, `make check-pr PART=a` one; the emulator needs
`DISPLAY` (e.g. `DISPLAY=127.0.0.1:99`, or `xvfb-run make check-pr`).

| Job | Step | What it checks | On the runner |
|---|---|---|---|
| a | `tools/perfcheck.py` | the frames per tick of 7 fixed stretches against `tests/perf_baseline.json`: fails when one is more than 5 % slower (emulated cycles, so deterministic and machine-independent) | ~2 min |
| a | `tests/m4_game.py --every 10` walk_level1, fight1, level12_shadow_merge | the game program: the kid's state every tick, VRAM every 10th tick | ~2.5 min |
| a | `tests/m4_test.py` on 7 earlier scripts: walk_level1, jumps_climbs, fight1, fight_killpush, level12_shadow_merge, feather_fall, level13_jaffar | the Z80 logic against kidsim, every tick | ~9 min |
| a | `tests/m5_boot.py` | the game disk: the floppy boot through the launcher and PRES's title to the game, main RAM / RAM disk / KV / VRAM against the harness start, byte for byte | ~1.3 min |
| a | `tests/m5_save.py` | Ctrl+G / Ctrl+A, the saved game on a copy of the disk, a write-protected disk | ~0.5 min |
| b | `tests/m4_test.py` on all of `tests/m7_scripts` | the same: the sound-ticks and key scripts | ~9 min |
| b | `tools/oracle_suite.py` on `tests/m7_scripts` + the 7 scripts above | kidsim against SDLPoP | ~9 min |
| b | `tools/cut_suite.py` | cutsim against SDLPoP, all 63 cutscene cases | ~5 s |
| c | `tests/m7_launch.py` | the launcher: boot -> PRES -> game round trips, the level-end handoff through a cutscene, game over and restart | ~13 min |
| c | `tests/m7_cut.py --quick` | PRES's level cutscenes 2 and 8 against cutsim: every frame's state, VRAM, the timing, the music | ~4.5 min |
| d | `tests/m7_title.py --quick` | PRES's title, part 1 (steps a-g): VRAM against tools/titleref.py at every step, fade pass and wipe column, the step timing, the PSG against sndsim (bank A, the looping title theme) | ~8 min |
| d | `make cheats`, `tests/m7_keys.py` | the keys in the game and the launched game (texts, sound off, pause, Shift+L, Ctrl+R / Ctrl+Q through PRES), the release without cheat code | ~6.5 min |

## What stays local

| Gate | Command | Why local |
|---|---|---|
| the logic, all scripts | `python3 tests/m4_test.py` | ~75 min on the runner (~0.25 s a tick, ~18,000 ticks) |
| the game, every script, every tick | `python3 tests/m4_game.py` (`make m4`) | hours |
| the oracle, all scripts | `python3 tools/oracle_suite.py` | ~33 min on the runner (~0.09 s a tick) |
| the sound, full (and `--quick`) | `python3 tests/m7_sound.py` (`make m7sound`) | `--quick` alone ~26 min (measured locally; the runner ran every other test as fast as this machine): over a job's ~25 min budget with the setup; the full run is longer |
| the rest of the disk tests | `python3 tests/m7_title.py` (full), `tests/m7_cut.py` (all cases), `tests/m7_story.py` (`make m7title m7cut m7story`) | the full runs: longer than their quick parts (not timed on the runner) |
| the rest | `make m1 m2 m3 m3anim`, `tests/m8_pace.py` | not in the tier |

### The game disk in CI

`build/pop800.dsk` holds PRES's sound banks (`tools/presbank.py`), made from the Master System soundtrack. Its five
pieces are committed, converted, in `assets/sms/` (MZ-800 PSG streams + `pieces.json`; third-party music, not under the
GPL: `assets/sms/README.md`). Ripping them needs the ROM and MAME (`tools/sms/`, `tools/vgm2psg.py`,
`presbank.py --from-vgm`) and stays a manual, local step: it never runs in CI or in `make`.

The in-game bank `build/assets/sound.bin` is built from the committed OPL level curves `assets/opl/levels.json`
(`assets/opl/README.md`): a curve measured anew depends on the order of the measurement run, so a clean build used to
make a different bank (2378 bytes instead of 2328) and the tests' baselines did not match it.

From a clean checkout and the DOS data the build is byte-identical to the reference build: `sound.bin` md5
`5272e60564b3655e63e04e879c858f1c`, `sound_pres.bin` `85fcc5d863b4...`, `sound_pres_b.bin` `fe4eb77f73fc...`,
`sound_pres_c.bin` `5524da905ca9...`, `pop800.dsk` `097236170b427caa171b651699ad8f75` (the reference: the build of 1ad3ef5 with the logs from the ROM).

## The DOS data and its check

The original DOS Prince of Persia v1.3 data is never committed, uploaded as an artifact or cached: every job downloads
it (5.5 MB, a few seconds) from archive.org, item `prince-of-persia-mr-abandonware`, file `Prince of Persia.7z`
(https://archive.org/download/prince-of-persia-mr-abandonware/Prince%20of%20Persia.7z, 5,482,709 bytes). The archive
holds `Prince of Persia (DOSBox) Installer.exe`, a 7z self-extractor: it is unpacked with `7z x`, never executed. Its
paths are base64 of UTF-16-LE per path component (`QwA=` = `C`); the folder `C/POP/POP13` is v1.3. Its 27 `*.DAT`
files are copied into `external/dos/PRINCE` and each is checked against `tools/ci/dos_data.md5` (made from the local
copy the port was developed with); a missing file or any mismatch fails the job. That copy's PRINCE.EXE, CONFIG.DAT
and SETUP.DAT differ from the local ones and are not used (only `tools/dosbox_scene.py`, a local tool, runs the EXE).

The source may disappear. Then point the script at another copy of the same archive (`fetch_dos_data.py --url URL`,
or `POP800_DOS_URL` in the workflow) or at a folder that holds the files (`--from-dir DIR`): the md5 list decides
whether they are the right ones, so it should change only with a reason.

Locally `python3 tools/ci/fetch_dos_data.py --dest DIR` fetches and checks a copy into DIR (without `--dest` it writes
`external/dos/PRINCE`).

## Caches and minutes

The actions cache holds only the tools above (public sources, no game data), keyed by their versions; it is restored
at the start of each job and saved right after a tool is built. With warm caches a job spends ~1.5 min on setup and
the DOS data and ~20 s on the build, then its part. Measured (wall, the whole job): a 17:42, b 21:29, c 19:43,
d 17:48, so a run takes ~22 min wall and ~77 runner minutes. (The
repository is public: standard runners cost no minutes there; for a private repository on the Free plan that is
~77 of the 2,000 minutes a month per run.) The first run after a cache miss rebuilds the tools (~4 min more: SDL3
~1.2 min, mz800emu ~1.1 min, SDLPoP and mzdisk seconds).
