# CI: the PR checks

`.github/workflows/pr-checks.yml` runs on every pull request to `main` (and by hand: *Actions → PR checks → Run
workflow*). It builds the port from a clean checkout on GitHub's standard Ubuntu 24.04 runner (2 vCPU) and runs the
**PR tier**, a selection of the tests that keeps each job at or under ~22 minutes. The **full regression**, every test
on its full set, runs on the same runners on demand (`.github/workflows/full-regression.yml`, below). Locally
`tools/testrun.py` runs what a change affects, cached and in parallel (below). All three take their tests from one
list, `tools/ci/suite.py`.

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

`tools/ci/suite.py` holds the lists: `PARTS` (this tier), `FULL` (the full regression), `SMOKE` (the local smoke
tier) and, per program, what the local runner needs (`PROGRAMS`, below). `tools/ci/check_pr.py` runs the steps of a
tier one after the other (`python3 tools/ci/check_pr.py --list`). Locally: `make ci-build` (or `make` and `make
build/m4test.mzf`), then `make check-pr` runs all four parts, `make check-pr PART=a` one (the emulator runs headless
in its pipe mode, SDLPoP with SDL's dummy drivers: CI's `xvfb-run` is a precaution). `python3 tools/testrun.py --tier
pr [--part a] [-j 4]` runs the same commands through the local runner: in parallel and cached.

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

## The full regression (on the runners)

`.github/workflows/full-regression.yml` runs every test on its full set: the parts of `FULL` in `tools/ci/suite.py`,
one matrix job each (`python3 tools/ci/check_pr.py --full PART`; the same setup and build as the PR jobs, a 75-minute
job limit). With the tracepoints of MZPico/mz800emu#1 the emulator no longer stops at every tick or interrupt, so the
whole set fits the runners (m7_sound ~1.5 h -> ~5.4 min, m4_test on every script ~45 -> ~4.3 min, measured locally).

| Part | Steps |
|---|---|
| logic | `tests/m4_test.py` on every script (m4, m6, m5, m7), `tools/perfcheck.py`, `tools/cut_suite.py` |
| oracle-m4m6, oracle-m5m7 | `tools/oracle_suite.py` on those sets (kidsim against SDLPoP) |
| pixels-m4, pixels-m6, pixels-m5 | `tests/m4_game.py --every 1` on that set (the state and VRAM every tick) |
| sound | `tests/m7_sound.py` (full), `tests/m5_boot.py`, `tests/m5_save.py`, `tests/m8_pace.py` |
| pres | `tests/m7_title.py`, `tests/m7_cut.py` (full: every case, the keys, Ctrl+L) |
| story | `tests/m7_story.py` |
| launch-keys | `tests/m7_launch.py`, `make cheats`, `tests/m7_keys.py`, and in the CHEATS=1 tree `build/cheat/tests/m7_keys.py` (the cheat keys) and `build/cheat/tests/m4_test.py` on the key scripts (the cheats, Z80 against kidsim) |
| early | `smoke_test`, `m0_test`, `m1_compare`, `m1_test`, `make build/m3test.mzf build/m3demo.mzf`, `m3_test` and `m3_anim_test` on each of the 14 levels, `m3_demo` (records only); measured locally ~9 min wall with 4 jobs (`m3_anim_test` 1,729 s serial) |

How to run it:

- **By hand**: *Actions → Full regression → Run workflow*, choose the branch; or `gh workflow run full-regression.yml
  --ref BRANCH` (`gh run watch` follows it). All parts run.
- **By a push to a `regress/**` branch**: `git push origin HEAD:regress/<name>` runs it on that commit.
- **Some parts only**: commit a file `tools/ci/regress_only` on the branch with the part names, one per line (`#`
  comments allowed), e.g. `pres` and `story` after a PRES change. The other jobs still start, print `skipped
  (tools/ci/regress_only)` and pass within the setup time. Do not merge the file into `main` (a run on demand would
  then skip those parts too).
- Unknown part names, on the command line or in `tools/ci/regress_only`, fail the job (a typo cannot give a green run
  with no steps).

Not in the full regression: the M2 measurements `tests/m2_oracle.py` (the renderer against SDLPoP's level-map
screenshots, with known differences: 1,518 pixels on level 1, 4,298 on level 4) and `tests/m2_ega_capture.py` (needs a
DOSBox capture of the real game in `build/dosbox/`). They are measurements, not gates: run them locally (`make m2`).

Locally `python3 tools/ci/check_pr.py --full PART` runs a part one step after the other, and `make check-full` runs the
whole set through the local runner without the cache; the full regression is normally the runners' job.

## Local testing

`tools/testrun.py` runs the tests of `tools/ci/suite.py` in parallel and skips each test that passed before with the
same inputs. It builds first (`make ci-build`, then what the selected tests need: `make cheats`, the M3 programs).

| Target | What | Use |
|---|---|---|
| `make check` | the full regression's tests that the changes since `BASE` can affect, plus those that failed last time; each cached | after a change |
| `make check-smoke` | `SMOKE`: the build, `smoke_test`, `m5_boot` (the disk boot), `m4_test` on three short scripts, `m4_game --every 1` on one scene, `m7_title --quick`, `m7_cut 2:60` (one cutscene), `perfcheck`, `cut_suite` | ~1.6 min cold (below), seconds cached |
| `make check ALL=1` | every test of the full regression, cached | after changing the emulator, SDLPoP, pasmo or the Makefile's build rules |
| `make check-full` | every test, no cache | normally on the runners (above) |

Options: `J=N` jobs (default: half the cores), `K="text ..."` only the tests whose id contains one of the words (e.g.
`make check K="m4_test oracle_suite"`), `BASE=ref` (`make check`: count the changes from that commit; default: the
merge base with `origin/main`; `BASE=HEAD`: the uncommitted changes only). Directly: `python3 tools/testrun.py --list`
(the selection, with the file that selected each test and the expected times), `--explain ID` (one test: its
command, tiers, the sources of its artefacts, its inputs and cache key), `--tier pr --part a`, `--no-cache`,
`--no-build`, `--idle S`, `--display D`.

**The tests.** Every step of the tier is a test, except: a program given control scripts that runs them one by one
(`m4_test`, `oracle_suite`, `m4_game`) is one subtest per script, and a program run without arguments whose run splits
into parts (`PROGRAMS[...]['split']`) runs as those parts: `m7_launch` (`M7_ONLY=round_trip | level_end | game_over`),
`m7_title` (`--quick`, `--rest`), `m7_cut` (each of the 7 cases, `--rest`: the key and Ctrl+L parts), `m7_story` (title,
expired, ending, keys, late, flow), `m7_keys` (texts, sound, pause, levels, launched, release), `m8_pace` (its three
scripts). Together the parts run what the whole run does. A test's id is its command (`m4_game --every 1 m4/walk_level1`,
`m7_cut 2:60`, `m7_launch M7_ONLY=round_trip`; `cheat/...` in the CHEATS=1 tree), so the same command in two tiers is
one test with one cache entry: the smoke tier's tests are tests of the full regression, the PR tier's `m4_test m7/...`
are the full regression's. The full regression has 276 tests (`--tier all --list`).

**Affected** (`make check`): the files that differ from `BASE` (committed or not) and the untracked files, `*.md`
excepted. A test is selected when one of them is among its repository inputs (below) or matches the sources of its
build artefacts (`suite.Build`: e.g. the game's binaries come from `src/m4`, `src/m3`, `src/m1`, `src/boot`; the disk
from all of `src/`; the assets from `assets/` and `tools/`, coarsely). A test that failed, hung or timed out in an
earlier run (`build/testrun/failed.json`) is selected until it passes. The base is assumed checked: `origin/main` has
passed the runners. The emulator, SDLPoP, pasmo, mzdisk and the Makefile are not in the selection (`make check
ALL=1` after changing one; their hashes are in the cache key, so only what they changed reruns).

**The cache** (`build/testrun/cache.json`): a pass is stored against a sha256 of everything the result depends on:
the command line and environment; the test's file and every repo module it imports (static analysis of the imports,
transitively, within `tests/` and `tools/`); the control scripts it is given or names; the build artefacts it uses
(the logic tests `build/m4test.*`, the game tests `build/m4game.*`, `m4ovl.bin`, the overlays, the disk tests
`build/pop800.dsk`, `boot.*`, `pres.*` and these, each with `build/assets/`; the logic and game tests without the
presentation's art and banks); `tools/ci/dos_data.md5` (for the DOS data), `assets/` (not `*.md`),
`tools/palettes.json`; and as used the emulator binary and `emu/`, SDLPoP (`prince`, its commit, `SDLPoP.ini`,
`tools/sdlpop-pop800.patch`), pasmo, mzdisk. Content hashes, not times: an edit that builds the same bytes (a comment)
selects the tests, and they come back `cached`. Failures, hangs and timeouts are never cached.

**Isolation.** Each test runs in its own working directory `build/testrun/work/<id>` (the emulator writes its RAM-disk
image, breakpoint file and other state into its current directory). The disk tests boot their own copies of
`build/pop800.dsk` (tempfile); `m0_test` mounts a copy of `build/m0.dsk`. `m3_test`/`m3_anim_test` (diff images with
the same names for every level) and `m0_test` run in a scratch tree `build/testrun/scratch/<id>`: the project's
directories as symlinks, `build/` a directory of symlinks to the artefacts, so what the test writes stays there.
The work and scratch
trees are removed after a pass and kept after a failure (removed with their symlinks unlinked first, never followed).

**The display.** The runner checks that the emulator starts on `DISPLAY`; if not, it starts a private Xvfb (under WSL
`-listen tcp -nolisten unix`, `DISPLAY=127.0.0.1:<n>`) for the run and stops it at the end. The current emulator runs
headless in its pipe mode and the oracles use SDL's dummy drivers, so any `DISPLAY` passes the check today.

**The watchdog.** A test whose log has not grown and whose processes have used under 5 % of a CPU for 2 minutes (an
emulator hanging at its start) is killed and run once more; a second hang is reported as `hung`. A test running longer
than 3 x its measured time (at least 5 minutes; 30 minutes before it has one) is killed: `timeout`. The measured times
are in `build/testrun/times.json`.

**Output.** One line per finished test (`pass`, `fail`, `cached`, `hung`, `timeout`, the seconds), then a table per
program, the failures with their logs; `build/testrun/last.json` holds every result, `build/testrun/logs/<id>.log` each
test's output. The exit status is 1 if any test failed, hung or timed out.

**Measured** (8 cores, `-j 4`, the trace emulator of MZPico/mz800emu#1, the build up to date; `BASE=HEAD` and the
change uncommitted):

| Run | Selected | Ran | Wall |
|---|---|---|---|
| `make check-smoke`, no cache | 10 | 10 | 98 s (+10 s `make ci-build`; `m5_boot` 84 s is the longest) |
| a PRES change (`src/pres/pres.asm`), first `make check` | 27: the disk tests (`m5_*`, `m7_launch`, `m7_title`, `m7_cut`, `m7_story`, `m7_keys`) | 24 (3 cached from the smoke run) | 750 s (`m7_launch M7_ONLY=level_end` 620 s; `m7_story late` failed there at once, fixed since: 109 s) |
| the same again | 27 | 0, all cached | 20 s |
| a game-code change (`src/m4/kid.asm`), first `make check` | 171: `m4_test` (71 + 15 cheat), `m4_game` (52), `perfcheck`, `m8_pace`, `m7_sound`, `cheat/m7_keys` and the disk tests | 139 (32 cached: the edit built the same disk) | 1124 s (`m8_pace` ~5 min each, `m4_game` traps scenes ~4 min each) |
| the same again | 171 | 0, all cached | 21 s |
| a doc change (`*.md`) | 0 | 0 | 5 s (no build) |

The oracle tests (kidsim against SDLPoP) are selected by changes to the tools and scripts, not by `src/`: a game-code
change leaves them alone.

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
