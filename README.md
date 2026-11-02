# pop-800 — Prince of Persia for the Sharp MZ-800

Fan port of Prince of Persia (Apple II, 1989) to the Sharp MZ-800 with the 32 KB VRAM
extension (320x200, 16 colours), floppy disk and RAM disk. See `PLAN.md` for the plan and
`docs/research/` for the research notes behind it.

## Layout

- `PLAN.md` — the port plan (decisions, memory model, milestones, risks)
- `docs/research/` — notes on the Apple II source, SDLPoP, existing ports, art sets, MZ-800 hardware
- `src/test/` — test programs (`colorbars.asm`); `src/m0/` — the M0 boot program (floppy boot, VBLN IRQ, input, RAM-disk probe); `src/m1/` — planar graphics kernel (`gfx.asm`, `far.asm`, generated `kernel_gen.inc`) and its test scene; `src/m3/` — the Z80 room renderer (`room.asm`, port of SDLPoP's seg008 as reproduced by `tools/popdata.py`) and its test program; `src/m4/` — the prince: `kid.asm` (control, sequences, falling, collisions, room changes, a port of SDLPoP's kid logic as reproduced by `tools/kidsim.py`), `sprite.asm` (the kid through the sprite kernel), `objects.asm` (traps, buttons, loose floors, potions, hit points), `game.asm` (the playable program), `m4test.asm` (logic harness)
- `tools/` — `mkmzf.py` (MZF wrapper), `emu.py` (headless mz800emu driver over the JSONL pipe), `pack.py` (PNG -> planar pack + directory), `gen_kernel.py` (unrolled kernel routines), `refrender.py` (reference renderer for the M1 scene), `popdata.py` (level loader + Python port of SDLPoP's room renderer), `build_assets.py` (all packs, levels and tables into build/assets/), `palettes.json` (per-set colour overrides),
  `palette_check.py` / `ega_check.py` (art-to-MZ-palette experiments)
- `tests/` — automated checks run against the emulator (`make test`); `tests/m4_scripts/` are control scripts (one `x y shift` line per tick) shared by SDLPoP's trace hooks, the Python simulator and the Z80
- `tools/sdlpop-pop800.patch` — our hooks in the local SDLPoP build (applied by `tools/fetch-external.sh`): `POP800_SCRIPT` feeds a control script, `POP800_TRACE` writes the kid state per tick, `POP800_NOGUARDS`, `POP800_SEED`, `POP800_PATCH`, `POP800_NOTRAPS`; `tools/oracle.py` runs them to validate `tools/kidsim.py`
- `emu/` — project emulator configuration (`mz800emu.ini`, launcher used by `.mcp.json`)
- `external/dos/PRINCE/` — the user's own DOS v1.3 game files (EGA DAT art source; git-ignored, never redistribute)
- `external/` — cloned references, not part of the build: `pop-spectrum` (Potapov's Spectrum
  128K port), `SDLPoP`, `mzdisk`. Re-clone with `tools/fetch-external.sh`.

## Requirements

pasmo, Python 3 with Pillow, mz800emu built at `~/src/mz800emu/build/build-mz800emu/mz800emu`
(its `mcp-server/mcpinit.sh` must have been run once to create the venv used by `.mcp.json`).

```sh
make        # assemble programs and build the bootable build/pop800.dsk
make test   # smoke test + M0 acceptance test in the headless emulator
make assets # packs, level blueprints and tables from the EGA DATs into build/assets/
make m3     # Z80 room renderer versus the Python reference, every room of every level (M3LEVELS=... to narrow)
make m3anim # per-tile redraw of every animated tile through all its frames, every room of every level
make m3demo # camera demo: records build/m3_demo.gif; tests/m3_demo.py --gui runs it in the emulator window
make m4     # the prince: Z80 logic versus tools/kidsim.py, then the playable program versus the Python render (state every tick, screen every 5th)
python3 tools/oracle.py 1 tests/m4_scripts/walk_level1.txt /tmp/t.txt   # check kidsim against SDLPoP on a script
python3 tools/walkfind.py 1 out.txt   # search a control script that finishes a level (kidsim)
python3 tests/m4_game.py --gui   # play the prototype in the emulator window: cursor keys / joystick 1, SHIFT, SPACE or fire = the button
```
