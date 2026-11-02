# CI: the PR checks

`.github/workflows/pr-checks.yml` runs on every pull request to `main` (and by hand: *Actions → PR checks → Run
workflow*). It builds the port from a clean checkout on GitHub's standard Ubuntu 24.04 runner (2 vCPU) and runs the
**PR tier**, a selection of the tests that keeps each job under ~20 minutes. The full gates stay local (below).

## What a run does

Two matrix jobs (`a`, `b`) run in parallel; each one:

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
4. **Build**: `make ci-build` = `make assets`, then everything `make` builds plus `build/m4test.mzf`, except the game
   disk (below).
5. **The PR tier**: `make check-pr PART=a` or `PART=b` under `xvfb-run` (the emulator needs an X display).

Nothing built is passed between the jobs: no artifacts (the build holds converted game art and the repository is
public), each job builds for itself (~1.5 min).

## The PR tier

`tools/ci/check_pr.py` holds the list (`python3 tools/ci/check_pr.py --list`). Locally: `make ci-build` (or `make` and
`make build/m4test.mzf`), then `make check-pr` runs both parts, `make check-pr PART=a` one; the emulator needs
`DISPLAY` (e.g. `DISPLAY=127.0.0.1:99`, or `xvfb-run make check-pr`).

| Job | Step | What it checks | On the runner |
|---|---|---|---|
| a | `tools/perfcheck.py` | the frames per tick of 7 fixed stretches against `tests/perf_baseline.json`: fails when one is more than 5 % slower (emulated cycles, so deterministic and machine-independent) | ~2 min |
| a | `tests/m4_game.py --every 10` walk_level1, fight1, level12_shadow_merge | the game program: the kid's state every tick, VRAM every 10th tick | ~2.5 min |
| a | `tests/m4_test.py` on 7 earlier scripts: walk_level1, jumps_climbs, fight1, fight_killpush, level12_shadow_merge, feather_fall, level13_jaffar | the Z80 logic against kidsim, every tick | ~9 min |
| b | `tests/m4_test.py` on all of `tests/m7_scripts` | the same: the sound-ticks and key scripts | ~9 min |
| b | `tools/oracle_suite.py` on `tests/m7_scripts` + the 7 scripts above | kidsim against SDLPoP | ~7 min |
| b | `tools/cut_suite.py` | cutsim against SDLPoP, all 63 cutscene cases | ~10 s |

## What stays local

| Gate | Command | Why local |
|---|---|---|
| the logic, all scripts | `python3 tests/m4_test.py` | ~75 min on the runner (~0.25 s a tick, ~18,000 ticks) |
| the game, every script, every tick | `python3 tests/m4_game.py` (`make m4`) | hours |
| the oracle, all scripts | `python3 tools/oracle_suite.py` | ~33 min on the runner (~0.09 s a tick) |
| the sound, full (and `--quick`) | `python3 tests/m7_sound.py` (`make m7sound`) | needs PRES's sound banks (below); `--quick` alone ~9 min |
| the disk tests | `make m5boot m5save m7launch m7title m7cut m7story m7keys` | need `build/pop800.dsk` (below) |
| the rest | `make m1 m2 m3 m3anim`, `tests/m8_pace.py` | not in the tier |

### The game disk is not built in CI

`build/pop800.dsk` holds PRES's sound banks (`tools/presbank.py`), made from the Master System soundtrack's register
logs `build/sound/sms/*.vgm`, which are logged from the ROM in MAME (`tools/sms/run_song.py`; the ROM is the user's
and is never copied). They are derived from the ROM, so they are not committed and CI has no source for them.
`make ci-build` builds everything but the disk when `build/sound/sms/` is empty (locally, with the logs there, it
builds the disk too). So the tests that boot the disk, and `tests/m7_sound.py` (it plays the banks' pieces, even with
`--quick`), stay local.

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
at the start of each job and saved right after a tool is built. With warm caches a job spends ~2.5 min on setup and
the build, then its part: job a ~16 min, job b ~19 min wall, so a run takes ~20 min wall and ~35 runner minutes. (The
repository is public: standard runners cost no minutes there; for a private repository on the Free plan that is
~35 of the 2,000 minutes a month per run.) The first run after a cache miss rebuilds the tools (~4 min more: SDL3
~1.2 min, mz800emu ~1.1 min, SDLPoP and mzdisk seconds).
