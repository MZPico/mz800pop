# Prince of Persia for the Sharp MZ-800 — port plan

Target: Sharp MZ-800 (Z80A 3.55 MHz, 64 KB RAM) with the MZ-1R25 32 KB VRAM extension
(320x200, 16 colours), a floppy drive (MZ-1E05/WD2793 or MZPico FDC) and a RAM disk
(MZ-1R18 protocol or MZPico `[ramdisk]`). Goal: the full 14-level game with 16-bit-class
graphics (the DOS/Amiga art at 320x200 in 16 colours) and the smoothest animation the
machine allows, developed and tested on mz800emu with its MCP server.

Research notes backing this plan are in `docs/research/` (Apple II source and SDLPoP,
existing ports, graphics sources, MZ-800 hardware).

---

## 1. Decisions

### 1.1 Code base: the 2026 ZX Spectrum 128K port, not a new translation and not C
> **Changed 2026-10-26:** the game logic is ported from **SDLPoP** instead (its frame and sequence tables pair
> with the DOS art, and it is the test oracle): SDLPoP (hooked) -> tools/kidsim.py (Python port) -> Z80, each
> step checked tick by tick. The Spectrum port remains a reference for Z80 techniques only. The text below is
> the original decision.
- **Primary source: Sergey Potapov's ZX Spectrum 128K port**
  (https://github.com/PotapovSergey77/POP_Spectrum_128K, branch `zx-spectrum-port`,
  disk loader in `zx-spectrum-disk`). 22,000 lines of Z80 assembly for pasmo, ported
  "routine by routine" from Mechner's 6502 source, complete (14 levels, all enemies,
  traps, cutscenes, music), same CPU speed as ours, plus ~50 Python tools for Apple II
  assets and for cross-checking Z80 traces against the 6502 original. Its game logic
  (pop.asm control/sequence/collision/falling/grabbing/clock sections, fight.asm,
  lvcode.asm, roomblk.asm) is directly reusable; its 1-bpp Spectrum rendering, bank
  paging and tape/TR-DOS loaders are what we replace.
- **Reference oracles:** Mechner's Apple II source (semantics, data tables) and
  SDLPoP (DOS behaviour, and `seg008.c` for which DOS image is drawn where for every tile,
  which we need because we use DOS tiles instead of Apple ones).
- **Rejected: compiling SDLPoP's logic with SDCC/z88dk.** The logic segments are
  compilable, but SDCC code is ~2x slower, SDLPoP's data layer (SDL surfaces, DAT
  decompressor, ~340 KB working set on its smallest port) is unusable, and a finished
  Z80 assembly port of the same logic already exists.
- **Rejected: fresh 6502-to-Z80 translation.** No usable transpiler exists; the BBC and
  Spectrum authors both did it by hand over a year or more.

### 1.2 Art: the DOS EGA set, 320x200, 16 fixed RGBI colours (decided; source files in external/dos)
- The DOS EGA art (EDUNGEON.DAT, EPALACE.DAT, the `ega[]` mappings in KID/GUARD/PRINCE/PV
  DATs, v1.0-1.3 installs only) is already 320x200 in a 16-colour RGBI palette that
  matches the MZ-800's fixed IGRB set almost one-to-one (only EGA brown vs MZ dark yellow
  differs). Same tile grid (32x63) and sprite metrics as the VGA/Amiga/ST art.
- Fallback / enhancement: quantise the VGA PNGs that SDLPoP ships in `data/` to the 16 MZ
  colours with per-set dithering; use the 4 remappable palette entries per level to tune
  the palace browns.
- Extraction: PR (Princed Resources) or SDLPoP's PNG + .pal files; conversion with our own
  Python pipeline (see §4).
- Resolution choice: 320x192 playfield + 8-line status bar exactly as DOS. Logic keeps
  Mechner's 140-unit room coordinates (block = 14 units, 10 blocks); screen x = unit *
  32/14 via a 141-entry table, the same mapping the DOS version used.

### 1.3 Rendering model (no double buffer exists in 16-colour mode)
32 KB of VRAM is exactly one 16-colour frame, so no page flip. The design follows the
Apple II / Spectrum approach adapted to planar VRAM:
- Room is drawn once into VRAM when entered (SURE pass), piece by piece from the tile set.
- Characters and moving objects use **save-under** buffers in RAM (as HIRES.S
  `layrsave/peel`), so the clean background is never read back from VRAM (VRAM reads cost
  2-5 wait states; writes spaced >= 8 T are free).
- Per game tick, for each character: compose the union rectangle of old and new sprite in a
  RAM buffer (restore from save-under, lay the new masked sprite, re-lay foreground pieces
  from the tile cache), take the new save-under from it, then LDIR the rectangle to VRAM,
  plane by plane via the WF plane-select, synchronised to VBLN. This is the "only moment
  the screen changes", as in the Spectrum port, and keeps flicker-free output without a
  second frame.
- Sprites are stored facing left, 4-bpp planar, colour 0 = transparent; the mask is the OR
  of the four planes (no stored mask); mirroring is a per-byte bit-reverse table plus
  byte-order swap, so one stored frame serves both facings. Shifting to arbitrary x uses
  16-bit shift tables per plane byte (Spectrum/BBC technique).
- Tiles use WF REPLACE/PSET where a piece has one colour per byte run, otherwise plane-wise
  SINGLE writes. Apple's AND/OR/STA/XOR piece semantics map to mask-and / or / copy / xor
  on each plane.
- Game tick = every 4th 50 Hz frame (12.5 fps, the original design rate; the DOS version
  runs 12). Stretch goal: every 3rd frame (16.7 fps, what the Spectrum port achieves with
  1-bpp sprites). Budget per tick: 283k T at 12.5 fps. Rough cost estimate for two
  characters: fetch frames from RAM disk ~20k T, compose + mask + shift ~80k T, fore
  pieces ~20k T, VRAM copy ~35k T, logic ~30k T. Fits with margin; measure with the
  emulator profiler before committing to 16.7 fps.

### 1.4 Memory model
> **Current map: docs/memory.md** (512 KB RAM disk baseline, decided 2026-10-27; per-level swapping for
> 256 KB is a late option). The table below is the original estimate.
Main RAM (64 KB, ROMs switched out, VRAM window kept at 8000h-9FFFh):

| Range | Use |
|---|---|
| 0000h-00FFh | IM2 vector table / RST stubs |
| 0100h-7FFFh | game code + fixed tables (~32 KB; Spectrum fixed half is ~24 KB code + tables) |
| 8000h-9FFFh | VRAM window (8 KB; `IN (E1h)` can expose the DRAM underneath as an 8 KB reserve) |
| A000h-FFFFh | level blueprint 2.3 KB, room state, current-room tile cache (~12 KB), two character frame buffers (~1 KB each), save-under buffers (~2 KB), compose buffer (~2 KB), object list, sound, stack |

RAM disk (sequential port access, ~21 T/byte, 16-bit random positioning):

| Content | Raw size (est.) |
|---|---|
| Kid set, 219 frames planar 4-bpp, left-facing only | ~80 KB |
| Current enemy set (guard/skel/fat/shadow/vizier), per level | ~15 KB |
| Current environment set (dungeon or palace pieces), per level type | ~60 KB |
| Objects (PRINCE.DAT: sword, potions, flames, meters, font) | ~10 KB |

That is ~165 KB raw, ~100 KB with a cheap RLE/ZX0 pack decoded on fetch.
**Decided (2026-10-25): baseline is a 256 or 512 KB paged RAM disk (MZ-1R18 protocol:
E9h page, EAh data, EBh address; MZPico `[ramdisk]`). The game must also run on MZPico's
`pico_rd` (port 45h protocol, available on every board). A memory-mapped bank extension
(memext, as modelled by mz800emu) is an optional third backend used only for speed when
present.** The storage layer is a small driver interface (`far_seek page:addr`,
`far_read n`, `far_write n`, `far_size`) with backends selected at boot by probing:
MZ-1R18/MZPico ramdisk, pico_rd, memext. 256 KB leaves room to pre-compose neighbouring
rooms (4 x 30 KB) for instant room changes.

Floppy (320 KB per side-pair, 80-track images allowed on MZPico): whole game as one
bootable DSK: boot loader (IPLPRO sector), core program, kid pack (loaded once into the
RAM disk), per-level packs (blueprint + level code + enemy set + env set when it changes).
Level change = a few seconds of loading, as on the Apple II. Save game to floppy or the
RAM disk.

### 1.5 Timing and input
- VBLN interrupt via Z80 PIO port A bit 5 (IM2), fallback 8253 counter 1/2 locked to HSYNC;
  tick counter drives the 4-frame game tick exactly as the Spectrum port's FRAME_WAIT.
- Keyboard via 8255 (D0h/D1h) matrix scan, joystick via IN F0h; map to the five game inputs.
- Sound: SN76489 PSG at F2h (3 tones + noise). Convert the Spectrum port's AY sound/music
  data (itself taken from the CPC version) to SN76489 commands offline; 8253 beeper as a
  fallback channel.

---

## 2. Toolchain

- Assembler: **pasmo** (installed; the Spectrum sources assemble with it) during the port;
  optional move to sjasmplus later for macros/modules.
- Python 3 pipeline for assets and disk building (reuse Potapov's `zx/tools/*.py` for
  Apple II level/sequence/frame tables; new converters for DOS DAT/PNG -> planar packs;
  mzdisk CLI or our own DSK writer for the bootable image).
- **mz800emu** (built at `~/src/mz800emu/build/build-mz800emu/mz800emu`) with the VRAM
  extension, FDC and RAM disk enabled; **MCP server** (`mcp-server/mcpinit.sh` -> project
  `.claude/.mcp.json`, not yet set up) for scripted runs: `emu_media_insert`, `emu_run`
  (frame-exact, reproducible), `emu_input_send_joystick`, `emu_mem_read`,
  `emu_region_read` (VRAM planes for screenshots/pixel diffs), `emu_profiler_*`,
  `emu_snapshot_*` for regression states, breakpoints and watch expressions.
- Real hardware: MZ-800 + MZ-1R25 + MZPico Deluxe (floppy + `[ramdisk]`) and the
  MZPico floppy board for a real drive.
- Reference renders: SDLPoP (built with the same EGA/VGA data) for pixel-level room
  comparisons, and Potapov's `crosscheck.py`/`trace.py` approach for logic parity.

---

## 3. Work breakdown

### M0 — Harness (foundation)
1. Repo layout: `src/` (asm), `tools/` (python), `assets/` (extracted art, git-ignored
   originals), `build/`, `tests/`.
2. Build: `make` -> pasmo binaries -> MZF wrappers -> bootable `pop800.dsk`.
3. mz800emu MCP set up for this project; headless config with VRAM extension, FDC image
   mounted, RAM disk 128/256 KB. Smoke test script: boot the DSK, run N frames, dump VRAM
   planes to PNG, compare to a golden image.
4. Boot path: IPLPRO loader -> core program -> hardware probe (VRAM extension present?
   RAM disk present and size? joystick?) with a clear error screen.
5. 16-colour mode init (DMD=02h, WF/RF, palette group, SOF=0, border), VBLN IM2 handler,
   keyboard/joystick reader, PSG silence.
Exit: a test pattern in 16 colours boots from floppy in the emulator, keys/joystick echo on
screen, frame counter increments at 50 Hz.

### M1 — Planar graphics kernel
1. Storage driver (`far_*`) for the RAM disk; benchmark bytes/tick.
2. Tile blitter: lay a piece at (block x, y, section A/B/C/D) with copy / or / and-mask /
   xor semantics, using REPLACE/PSET where profitable.
3. Sprite blitter: shifted, mirrored, masked 4-bpp draw into a RAM compose buffer; clip
   left/right/top/bottom as HIRES.S does (CROP).
4. Rectangle copy RAM -> VRAM, top-to-bottom, the four planes of a row together; timed against
   the beam via the 8253 line counter (status 11).
5. Save-under buffers for two characters + one object.
6. Microbenchmarks through `emu_profiler_*`; record T-states per operation in
   `docs/perf.md`. Decide 12.5 vs 16.7 fps here.
Exit: a test program animates two kid frames across a static room at the target rate
without tearing.

### M2 — Asset pipeline
1. Extract DOS EGA sets with PR (EDUNGEON/EPALACE + sprite DATs); fallback converter from
   SDLPoP's VGA PNGs with palette quantisation to the MZ IGRB set.
2. Convert to planar packs: kid, 5 enemy sets, 2 environment sets, objects, cutscene art
   (PV.DAT), title screens, font. Pack with RLE/ZX0; emit a manifest (offsets, sizes,
   width/height/hotspots) as assembler includes.
3. Build the frame tables: Mechner's FRAMEDEF (Fimage, Fsword, dx, dy, Fcheck) remapped to
   DOS image ids (SDLPoP `frame_table_kid/guard`, `sword_tbl`) and DOS pixel offsets.
4. Tile drawing tables: for each of the 30 tile types, the DOS piece ids and positions per
   section, derived from SDLPoP `seg008.c` (`draw_tile_*`, `get_tile_to_draw`), plus the
   dungeon/palace variants and the "wall" pattern tables.
5. Levels: 14 blueprints (2304 bytes, identical in Apple and DOS data), level code
   (`lvcode.asm` per level from the Spectrum port), per-level pack layout on the DSK.
Exit: an offline Python renderer draws any room from our packed data and matches SDLPoP's
render of the same room after palette mapping (allowing documented differences).

### M3 — Room renderer on the machine
1. ~~Full room draw~~ (done: op list + cell execution, pixel-exact for every room of every level).
2. Animated tiles first (reordered 2026-10-26 to get motion on screen early): a per-tile redraw
   that rebuilds the op list for one tile column and re-lays only the compose cells it touches,
   driven by the FRAMEADV.S-style countdowns the Spectrum port keeps — torches, gates,
   spikes, chompers, loose floors, pressure plates, potion bubbles. Exit: a camera demo in the
   emulator (joystick steps through rooms, tiles animate at the 12.5 fps tick).
3. Room transitions (view change) with full redraw are deferred into M4: they are added when
   the prince first reaches a room edge.
Exit: `make m3` pixel-exact for every static room; animated tiles verified frame by frame
against popdata.py with the modifier advanced the same way.

### M4 — The prince (done, guards and the items below excepted)
Done (statuses 9-13): all kid movement, room changes, traps (spikes, chompers, loose and falling floors,
gates with buttons and door links, gate push), potions (heal, life, hurt, open), hit points, death and
restart, the sword pickup (sword in hand), the level door and the exit to the next level, SDLPoP's clip
and redraw overlays, pixel-exact against a Python reference and tick-exact against SDLPoP on 18 scripts.
Missing (moved to M5): feather-fall potion (slow fall, flash), upside-down potion (screen flip), screen
flashes, the level-1 start (crouch until the music ends).

### M8a — Speed (brought forward 2026-10-27: the game is not playable at the current rate)
Now ~10-11 frames per tick (12.5 fps needs 4), door/gate ticks ~21, room change ~130 frames (2.6 s).
1. Cache the static background behind animated tiles (torch flames ~1.1 frames each every tick; gates,
   level doors, chompers, spikes, loose floors): per step copy the cached background and lay only the
   moving pieces.
2. Object pass (~3.5 frames): pre-compose each room's fore layer (mask + data) into the RAM disk at room
   entry and apply it in one masked pass instead of re-laying fore pieces every tick. (Measured 2026-11-02, status 44:
   not built; the fore ops barely overlap, the gain is the op scan, the layer needs up to ~38 KB of RAM disk and
   ~10-30 frames a room change.)
3. Piece laying: per-row overheads (copy-mode edge merge ~450 T a row-plane, masked chains), fewer
   RAM-disk seeks; faster op-list regeneration (tile_regen ~0.8 frames a tile).
4. Room change: the same, then pre-compose the next room while the kid approaches an edge (RAM-disk
   pages 6-7 are free for it).
Exit: a normal tick within 4 frames, door ticks within 6, room change under 1 s; pixel tests unchanged.
Status (2026-10-28, docs/perf.md; part 1 done, paused for M6 and M5): normal tick 9.5 -> 5.98 frames
(8.4 ticks/s, ~70% of SDLPoP's 12/s), level door step 23 -> 17.6, room change 134 -> 105.9 (2.1 s), gate
stretch (gate_push 200-260) 6.6. Tried and dropped: INI/OTIR chains entered by a call (rows too short),
per-row/column/box occlusion, a door prefix picture cache; frame skipping deferred.
Remaining, with expected gains (frames per tick unless noted), resumed after M6/M5:
1. Door/gate renderer: one pre-composed door image laid as one piece, the background behind the door
   composed once per opening, the door's op records patched in place instead of tile_regen: door step
   17.6 -> ~10-12, gate stretch -> ~5.5-6.
2. Visited-room cache (shadow + op lists, ~33 KB a room) in what pages 6-7 keep free after the guard set
   (~100 KB: ~3 rooms): a revisit ~25-30 frames instead of ~106. Decision deferred to after M6 (user).
3. Shadow stored chunk-major (one RAM-disk seek per chunk instead of per row): room change -4 to -6,
   door -0.2, normal -0.1. (Measured 2026-11-03, status 47: not built, object chunks are not strip-aligned; the
   restore's row loop got 24-39 T a plane-row faster instead.)
4. Room-change screen copy with POP/PUSH and the VRAM write modes: room change -2 to -4.
5. Copy paths: an inline INI chain entered by a jump (no call) instead of INIR per row: room change
   -1.5 to -3, door -0.2. The rest of lay_piece16's per-piece setup (~2 K T): room change -2, door -0.3.
6. Kid logic (collision rows, tile lookups): -0.2 to -0.3.
7. Kid area, measured with a guard on screen: old/new rects kept apart, fore pieces hidden behind the kid
   skipped, less spinning in the copy scheduler: -0.4 to -0.6 (the old/new split measured 2026-11-02: < 0.01, dropped,
   status 43; the copy scheduler: status 42). Pre-mirrored kid pack (~106 KB of RAM disk,
   same budget question as 2): -0.25.
8. memext backend (memory-mapped RAM disk, no seeks) where the hardware has it.
9. Standing characters: a character who looks as in the last drawn tick gets no dirty rect (built 2026-11-03, status
   46: fight -0.8 frames a tick).
Expected after 1-7: normal ~5.0-5.3 (~80% of SDLPoP), fights ~6-7, door ~10-12, room change ~95 first
visit / ~0.5 s revisited. The last ~20% needs frame skipping or memext.
Regression guard: `make perf` (tools/perfcheck.py, part of `make m4`) measures six fixed stretches and fails
when one is more than 5% slower than tests/perf_baseline.json; `tools/perfcheck.py --update` after an
intended change. New features must keep it green (the guard is drawn through the kid's object pass,
chunk buffers and copy scheduler).

### M5 — Level events, all levels, loading
1. Missing kid features: feather fall, upside-down potion, flashes, time limit (60 min) with the
   remaining-time messages, level-name and "press button" texts (font pack exists).
2. Per-level events (SDLPoP seg000/seg004 specials): level 1 start, 3 skeleton and checkpoint,
   4 mirror and the shadow running through it, 5 shadow drinking the potion, 6 shadow and checkpoint,
   8 the mouse opening the gate, 12 merging with the shadow and the invisible bridge, 13 falling ceiling
   floors and Jaffar's room, 14 the princess / end. Each needs an oracle script (SDLPoP hooks exist).
3. Exercise every level in the test harness (scripts may name their level; walkfind finds paths).
4. Floppy boot and loader for the game itself (so far the harness fills RAM and the RAM disk): load the
   program blocks (0x1200-0x7FFF, 0xC000-0xEBFF), fill the RAM disk from floppy, probe its size.
5. Save/restore.
Exit: all 14 levels playable from floppy in the emulator; replay scripts per level.

### M6 — Fights
1. Guard logic from SDLPoP (seg002 autocontrol AI, seg005 sword control, seg006 guard parts): strike,
   parry, stab, guard hit points, falling, skeleton, fat guard, vizier, shadow; oracle scripts with
   guards on (the POP800_NOGUARDS hook turned off).
2. Second character drawing (guard sprite buffer at 0xF600, docs/memory.md), guard hit points strip,
   hurt splash (draw_hurt_splash), sword drawn in fights (the sword drawing exists).
3. Enemy sets paged per level from the RAM disk (guard 20 KB, fat 19.5, skel 16.7, vizier 19.3,
   shadow 16.5 KB; pages 6-7).
Exit: fights match SDLPoP tick by tick in replay scripts.

### M7 — Presentation and sound
1. A separate program loaded from floppy between levels: title, story screens, princess cutscenes
   (PV art 115 KB, title 215 KB), game over, ending; the hour-glass.
2. Sound: no sound exists yet. PSG driver (SN76489), effects from SDLPoP's sound list, music re-arranged.
3. Options (controls), pause, cheat keys behind a build flag.
Exit: full game flow from boot to ending.

### M8 — Hardware, release
1. Real hardware: MZPico Deluxe (floppy + `[ramdisk]`) and a real drive; verify the beam timing
   (VBLN at scanline 245, copy rate per row) and VRAM wait states; pico_rd backend speed.
2. Per-level palette tuning, fades; try the 16.7 fps tick if M8a leaves time.
3. Release DSK + README (rights note: non-commercial fan port, no PoP rights).

Suggested order and effort (one developer, part time): M0 2 weeks, M1 3, M2 3, M3 3, M4 4,
M5 4, M6 3, M7 3, M8 3. The logic milestones (M4-M6) are mostly mechanical because the
Z80 logic exists; the graphics milestones (M1-M3) are the new work.

---

## 4. Asset pipeline detail

```
DOS EGA/VGA DATs ──PR / SDLPoP data──> PNG+pal ──tools/convert.py──> planar 4-bpp frames
Apple II LEVELS, SEQTABLE, FRAMEDEF ──Potapov tools──> levels.bin, seqtbl.inc, framedef.inc
SDLPoP seg008.c tables ──tools/tiletables.py──> tiles.inc (piece ids per section, per env)
all packs ──tools/pack.py──> kid.pak, env_dun.pak, env_pal.pak, guard*.pak, obj.pak, lvl01..14.pak
packs + binaries ──tools/mkdsk.py (or mzdisk)──> pop800.dsk (IPLPRO boot)
```

Frame record in a pack: width in bytes, height, x/y hotspot, 4 planes of w*h bytes
(RLE/ZX0 packed), no mask. Tile pieces: same record plus a mask plane where the Apple
piece used AND/XOR semantics.

---

## 5. Testing strategy
- **Golden images:** every room of every level rendered offline (Python) and on the
  emulator (VRAM plane dump via `emu_region_read`), compared pixel-exact.
- **Replays:** scripted joystick input per level through MCP, frame-exact (`emu_run` is
  deterministic), end state compared to stored snapshots; the Spectrum port's
  `makedemo.py`/`runtap.py` approach ported to mz800emu.
- **Logic parity:** trace the kid's state (x, y, frame, action, sequence) per tick on the
  Spectrum build under Potapov's `z80.py` and on ours via MCP watches; diff.
- **Performance:** `tools/profile.py` (mz800emu's call profiler per routine) per milestone, the budget
  table in `docs/perf.md`, and `make perf` (tools/perfcheck.py) as the regression check against
  `tests/perf_baseline.json`.
- **Hardware:** boot stability on MZPico; VRAM timing sanity test (a known-cycle blit
  measured against the 8253).

---

## 6. Risks and open questions
1. **RAM disk speed.** ~21 T/byte sequential on MZ-1R18; the pico_rd protocol's per-byte
   cost must be measured (M1) and may force a smaller per-tick fetch budget on that backend.
2. **EGA art availability.** Requires a DOS 1.0-1.3 install; otherwise quantise VGA.
3. **Flicker/tearing** with a single frame: mitigated by compose-then-copy timed against the beam
   (8253 counter 1 = line counter, status 11); verify on hardware, not only in the emulator: the
   VBLN interrupt line (245) and the copy rate (1.31 + 0.28 * w lines a row) are emulator measurements.
4. **VRAM wait states** are modelled from HDL, "not verified on real HW" per the GDG docs.
5. ~~Potapov's code coupling~~ (moot: the logic comes from SDLPoP). New: **speed** (status 14, M8a) and
   **main RAM** for M5/M6 code (docs/memory.md: ~8 KB of code room, then overlays from the RAM disk).
6. **Rights.** Mechner permits study/modification of the source; the franchise and the DOS
   art are Ubisoft's. Non-commercial fan release only; do not ship the original DATs, ship
   converted packs as the other ports do.
7. **Sound fidelity.** SN76489 has no envelopes; AY music needs re-arrangement.

## 7. Immediate next steps
1. ~~Confirm the RAM disk assumption~~ (done: 256/512 KB + pico_rd, memext optional).
2. ~~Clone Potapov's repo, SDLPoP and mzdisk into `external/`; set up the mz800emu MCP
   server (`.mcp.json`, restart Claude Code to activate); M0 smoke test~~ (done: `make test`
   boots a 16-colour test program in the headless emulator and checks VRAM planes and the
   VBLNK counter; `tools/emu.py` drives the emulator over its JSONL pipe).
3. Palette validation done on SDLPoP's VGA art (docs/research/palette-check.png): dungeon maps
   well, kid and palace need hand-tuned tables or the EGA DATs. Next: obtain EDUNGEON/EPALACE
   + v1.3 KID/GUARD DATs if available, else write per-set colour tables.
4. ~~M0 remaining: bootable DSK, RAM-disk probe, VBLN IM2 interrupt, keyboard/joystick~~ (done:
   `make` builds `build/pop800.dsk`, `make test` boots it through the ROM IPL in the emulator and
   checks the 50 Hz PIO interrupt, inputs, the RAM-disk probe and read speed; see
   docs/research/mz800-hardware.md "M0 results"). pico_rd and memext backends are written/
   deferred respectively and need real hardware.
5. ~~M1 planar graphics kernel~~ (done: src/m1/gfx.asm + far.asm; pixel-exact against
   tools/refrender.py via tests/m1_compare.py; timings in docs/perf.md). Decision: tick = 4
   frames (12.5 fps) nominal, stretching to 5-6 frames when two characters move. Design
   changes versus §1.3: background restore comes from a clean "shadow room" kept in RAM-disk
   page 1 instead of re-laying pieces; two compose buffers, both characters composed first and
   blitted together right after the VBLN interrupt (top rect first).
6. ~~M2 asset pipeline~~ (done: tools/build_assets.py writes build/assets/*.pack/.dir/.json for
   15 image sets (623 KB raw), the 15 level blueprints and tables.inc with the tile table, frame
   tables and sword table; tools/popdata.py is a Python port of SDLPoP's seg008 room renderer,
   pixel-exact against SDLPoP's own level maps for every static room of levels 1 and 4
   (tests/m2_oracle.py); per-set colour overrides live in tools/palettes.json).
   **Art source changed to the DOS EGA data** (2026-10-26, user-supplied v1.3 install in
   external/dos): tools/datfile.py decodes the DATs, popdata.DatImageSet applies the EGA colour
   rules (docs/research/graphics-sources.md), verified against DOSBox captures; the EGA art is
   drawn for 16 fixed colours and maps onto the MZ-800 palette almost one to one.
   Next: M3 room renderer on the machine (port of tools/popdata.py's draw_room to Z80).
7. M3 step 1 done (2026-10-26): src/m3/room.asm builds a room's operation list (back/mid/fore
   tables, 8-byte records) with a full port of popdata.py's seg008 logic (wall pattern PRNG,
   gates, level door, chompers, potions, above-room row) and executes it through the M1 kernel
   in 40 compose cells (10 columns x 4 bands of 48 rows): fill black, lay pieces, shadow write,
   blit. tests/m3_test.py compares op lists and VRAM with the Python reference; `make m3`
   is pixel-exact for every room of all 14 levels. Directory entries gained extent masks
   (bytes 6/7, flag bit 1) so copy-mode pieces with a partial last byte column leave the
   neighbouring pixels alone.
8. M3 step 2 done (2026-10-26): animated tiles. Op records carry a tile tag and the lists keep
   per-tile slice tables; `tile_redraw(tag)` regenerates the ops of a tile (plus its right and
   above-right neighbours, which draw from its state), splices them in place, and re-lays only
   the rect of the ops that changed through `run_rect`; `op_patch` (torch_redraw, bubble_redraw)
   patches a single-op animation in place. tests/m3_anim_test.py changes every animated tile's
   modifier through all its frames in every room of all 14 levels: pixel-exact (`make m3anim`).
   src/m3/demo.asm + tests/m3_demo.py is the camera demo (joystick/cursor keys walk the rooms,
   torches and potion bubbles animate at the tick; `make m3demo` records build/m3_demo.gif,
   `tests/m3_demo.py --gui` runs it in the emulator window). Costs (docs/perf.md): full room
   ~110 frames (needs the M8 pass), torch flame ~1.1 frames, generic tile ~4-7 frames.
   Room transitions are drawn with a full redraw (deferred polish: blank + redraw in M4).
9. M4 first cut done (2026-10-26): the prince walks, runs, turns, jumps (standing and running),
   climbs up and down, hangs, falls, bumps into walls and gates, and changes rooms in level 1.
   **Logic source changed from the Spectrum port to SDLPoP** (seg002/004/005/006): its frame table
   and sequence table pair with the DOS art we use, and SDLPoP doubles as a tick-exact oracle.
   Pipeline: external/SDLPoP gained two hooks (src/pop800_trace.c: POP800_SCRIPT feeds controls per
   tick, POP800_TRACE dumps the kid state, POP800_NOTRAPS freezes traps for comparisons);
   tools/kidsim.py is a Python port verified tick-exact against those traces (2178 ticks over six
   scripts); src/m4/kid.asm is the Z80 port verified tick-exact against kidsim (tests/m4_test.py);
   src/m4/game.asm + sprite.asm run it with the room renderer and the sprite kernel, and
   tests/m4_game.py checks every tick's state and the whole screen every 5th tick against the
   Python render with the kid composited (pixel-exact over the same six scripts, incl. room
   changes). `python3 tests/m4_game.py --gui` plays it in the emulator window (cursor keys or
   joystick 1, SPACE/fire = shift). `make m4` runs both tests.
   Not yet: traps, buttons, loose floors, potions, hit points, sprite clipping at floors when
   climbing (clip_char), guards, sound. Memory: code 0x2000-0x6FFF, tables block at 0xC000 (the
   ROM tape loader cannot fill 0xD000+, so mkmzf splits it off into a .b2 file the harness pokes;
   the floppy loader will load both), renderer lists behind the VRAM window at 0x8000-0x9FFF
   (mapped only inside blit), kid pack in RAM-disk pages 2-3, shadow + wall + objects in page 1.
   Speed: a tick costs ~5.9 frames on average (max 8.5): ~3 frames torch animation + kid logic,
   ~3 frames sprite restore/draw/blit; the game therefore runs at ~7.7 fps instead of 12.5 until
   the M8 performance pass (docs/perf.md).
10. M4 proper done (2026-10-26), guards excepted. The kid logic gained SDLPoP's seg007 and the
   related kid code: animated tiles ("trobs": torches, potions, swords, spikes, gates, level door,
   buttons, loose floors, chompers), falling loose floors ("mobs"), door links and buttons, spikes,
   pressing, items and potions (heal, life, hurt, open), hit points, death (the button restarts the
   level), the level door and the exit stairs. Chain as before: SDLPoP (hooks: now also
   POP800_NOGUARDS, POP800_SEED, POP800_PATCH, kept in tools/sdlpop-pop800.patch; tools/oracle.py runs
   a script) -> tools/kidsim.py -> src/m4/kid.asm + objects.asm. 14 control scripts (8,579 ticks: a
   level 1 walkthrough found by tools/walkfind.py, three potion scripts, trap-heavy random scripts)
   are tick-exact at each step, including hit points, the animated-tile and falling-floor counts and a
   checksum of the kid's room. The game program (src/m4/game.asm) now redraws the tiles that changed
   each tick (torch and bubble fast paths, the per-tile redraw otherwise), draws the kid and the
   falling floors together in dirty rectangles (src/m4/sprite.asm, with the exit-stairs clip), the hit
   point strip, restarts after death, and loads the next level from the RAM disk (all blueprints and
   both art sets are there; the floppy loader of M5 will fill it). tests/m4_game.py checks the state
   every tick and the whole 320x200 screen every 5th tick against the simulator's render: pixel-exact
   on six scripts, and the walkthrough ends on level 2. Memory: variables and two buffers moved to
   0x0800-0x0FFF (free RAM in this mode), code may use 0x2000-0x7FFF.
   Not yet: guards, the sword, sound, the general clip_char (sprite clipping by walls and floors
   when climbing), sprites partially off the screen edge (hidden), the level 13 special floors and
   other per-level events, feather fall and the upside-down potion.
11. Second playtest fixes (2026-10-27). Climbing: the general clip_char (kidsim.clip_char and
   kid_clip in sprite.asm) hides the prince behind the floor he climbs onto, and spr_draw takes a
   signed byte column and a 16-bit row, so sprites half off the screen edge or hanging into the room
   above are drawn instead of dropped. Pressure plates are drawn pressed (lowered) while their
   door-link timer runs, as SDLPoP's get_tile_to_draw does (popdata, room.asm get_tile, the tile
   snapshot). Remaining flicker: the object pass composes up to three chunks, then copies them
   timed against the beam. The 8253 counter 1 counts HSYNCs; the VBLN interrupt latches it, so the
   code knows the beam's line. The copy now writes all four planes of a row together (blq_n in
   kernel_gen.inc), at 1.31 + 0.28 * width lines a row. A chunk is copied only once the beam cannot
   catch it. Over walkthrough ticks 20-200: 573 of 573 object copies clean (148 of 576 torn before),
   and the tick got slightly cheaper (11.3 frames against 11.8). Room changes still copy as they
   draw, which shows as a top-to-bottom wipe.
12. Third playtest fixes (2026-10-27).
   - Climbing up facing right: SDLPoP's redraw_at_char2 overlays are ported. The floor tiles at a hanging,
     climbing or falling kid's columns are drawn again over him (draw_other_overlay / draw_floor_overlay;
     only those SDLPoP reaches after the kid's own tile). popdata.RoomRenderer.overlay and
     kidsim.overlay_tiles are the reference; src/m4/overlay.asm (in the 0xC000 block) is the Z80 side.
   - Red limbs: the kid art uses the hair's palette entry (EGA red) for a few shadowed limb pixels.
     popdata.kid_post recolours red clusters away from the hair with the skin colour.
   - SHIFT works as the button too.
   - The sword in the kid's hand (found-sword frames 229-237; SDLPoP add_sword_to_objtable): the sword pack
     is in RAM-disk page 1 at 0xD000, its directory at 0x1800, its buffer at 0x1A00. New script
     tests/m4_scripts/sword.txt (a patched sword tile), oracle-exact and pixel-exact.
   - The slice tables (SL_START/SL_CNT) sat on the shift-7 hi table at 0x8F00. They moved to the free page
     0x8100. The kid never uses shift 7 (x = obj_x * 8 / 7 is never 7 mod 8); the sword does.
   - Chunks of one tick are copied back to back from a moment when every chunk is clear of the beam and
     all of them show in the same frame (a kid split over two chunks showed half old for a frame: the
     "artifact at the screen edge"). The dirty rects are composed last-first, so the kid's chunks share the
     first buffer batch. Walkthrough ticks 20-200: no torn copies, no fallbacks.
   - Masked pieces clipped sideways are read in one RAM-disk run (rows w apart): 149 K -> 92 K T for a 4x60
     piece. A level-door tick still costs ~21 frames (normal ~10): ~8 for the door's back pieces, ~2.5
     regenerating three tiles' ops, ~3.5 for its fore pieces in the object pass. That is M8 work (cache the
     door's static background, faster piece laying).
   - The program's SCRIPT (harness control bytes) moved to 0x1000 (ROM monitor work area; CG-ROM is
     mapped there only inside blit). The tables block may now reach 0xE000. The size guards use .error
     (pasmo's `ds -1` only warned).
13. Fourth playtest (2026-10-27): the guillotine never cut the prince. SDLPoP's check_chomped_kid/chomped
   (a closed chomper in a tile the kid's row fully covers: blood on the blade, the kid set into it, seq 54)
   and check_gate_push (a closing gate pushes a standing kid 5 px) were never ported. Both are now in kidsim
   and src/m4/kid2.asm, which the game assembles at 0x1C00 (the program now loads from 0x1C00; nothing there
   runs inside blit).
   - Found on the way: can_bump_into_gate answered "yes" when the kid's height equalled the gate's.
   - Found on the way: a moving gate in the left room's column 9 did not redraw our column 0 one row up (the
     gate top, draw_tile_anim_topright).
   - Found on the way: room.asm's op-list config tables are indexed without a page carry, and the code growth
     moved them across 0x4000. They are now kept within one page by a conditional pad.
   - New scripts: chomper.txt (level 1 with a patched chomper, cut at tick 36) and gate_push.txt (level 4,
     a patched opener link; scripts may say '# level N'). tools/walkfind.py takes 'at<room>:<pos>' goals and
     a prefix script.
14. Memory restructure (2026-10-27, docs/memory.md): 512 KB RAM disk baseline. Image directories moved
   from main RAM to the RAM disk (dir_entry: ~12 lookups a tick, ~0.05 frames); the harness script moved
   to the RAM disk; freed: low code block 0x1200-0x1FFF (3.5 KB), the tables/code block may grow to
   0xEBFF (~3 KB free), 0xF600-0xFCDF reserved for the M6 guard buffer, 0x0000-0x07FF for M8a caches.
   Plan reordered: M8a (speed) next, then M5, M6, M7, M8.
15. M8a part 1 done (2026-10-28, docs/perf.md): normal tick 9.5 -> 5.98 frames, door step 23 -> 17.6, room
   change 134 -> 105.9. Kept: change detection by tile addresses, torch flames as objects with a picture
   cache, fast piece-laying loops (inverted masks, streamed masked pieces), incremental slice tables,
   single-cover occlusion, per-cell buckets for room draws, the background-only redraw reused by the object
   pass, flame registry re-found by place, run_rect laying from its recorded op list with overlapping
   repeats clipped (src/m4/rcache.asm), wall-pattern draws from a table (PR_TAB), shadow_write/restore_shadow
   row loops, a faster mul8. `make perf` guards these numbers. Low RAM is now used up to 0x077F
   (docs/memory.md). Decided (user): continue with the game now, M6 (fights) first since a second
   character is the largest speed unknown, then M5, then the rest of M8a (list in the M8a section), M7,
   M8. The visited-room cache waits until M6 shows the guard set's RAM-disk needs.
16. M6 first part done (2026-10-29): guards and sword fights.
   - Oracle: SDLPoP hooks for the guard (`G` trace lines after each frame, POP800_GUARD placement, POP800_SWORD;
     tools/sdlpop-pop800.patch), tools/oracle.py script options `# guards`, `# guard room:tile:dir:skill:color`,
     `# sword`; tools/oracle_suite.py compares kidsim with SDLPoP for all scripts (kid and guard lines).
   - tools/kidsim.py: SDLPoP's guard logic (AI, sword control, hurting, falling, enter/leave/follow, skeleton,
     mouse, shadow start positions); 16 fight scenes in tests/m6_scripts, tick-exact against SDLPoP.
   - Z80: src/m4/guard.asm (block 2, ~5 KB): two characters through SDLPoP's Kid/Guard record swaps; logic
     tick-exact against kidsim on all 34 scripts (tests/m4_test.py, guard lines included). The game has guards
     on; the harness turns them off for the kid-only scripts (guard_opts).
   - Drawing (src/m4/overlay.asm people_place/people_chunk): the guard, his sword, both hurt splashes, the
     guard hit point strip, in SDLPoP's object order, through the kid's object pass and copy scheduler;
     pixel-exact against the reference on every tick of the 16 scenes; the reference checked against SDLPoP
     screenshots (silhouettes). Guard sets all resident in the RAM disk (docs/memory.md).
   - Memory: the sequence, frame and image-size tables moved to the RAM disk (logic.bin, page 6 0xD000).
     Free: block 2 ~0.4 KB, main ~0.4 KB, low block ~0.7 KB: M5 needs code overlays from the RAM disk.
   - Speed (`make perf`): fight 8.99 frames per tick (SDLPoP fights at 10 ticks/s = 5 frames), normal 6.11.
   - Left: the shadow's scripted moves and its OR/XOR drawing and mirror clip (with the M5 level events), a
     tick where both characters are hurt shows only the guard's splash, the 1-hit-point blink of both strips,
     a standing guard is composed every tick (skipping it is an M8a item; done: status 46), Jaffar fights as a normal guard.
17. Code overlays (2026-10-29, M5 step 0; src/m4/ovl.asm has the recipe, docs/memory.md the layout): W1 = 1 KB at
   0x7C00 for event code during play (now: the full room draw, 868 B), W2 = 0xA000-0xAFFF (compose buffers,
   unused between levels) for level-start code (now: load_level, kid/guard start, alter_mods, 945 B). Overlays are
   separate pasmo assemblies against build/ovl_*.inc (tools/ovltool.py from the main sym), stored in RAM-disk
   page 6 from 0xE300 (5.4 KB free there). Loads: ~0.3 frames at a level start and at the first room draw.
   Free main RAM now: main 924 B (below W1), block 2 590 B, low block 694 B; W1 156 B, W2 3.1 KB.
18. M5 level events, logic (2026-10-30): kidsim ported SDLPoP's level start (checkpoint, level 7/13 entries,
   seamless 12->13), play_level_2/draw_game_frame order, time limit and messages, potions (feather fall incl.
   guards, upside-down state, flashes, life), the mirror, the shadow scripts of levels 4/5/6/12, level 12
   hidden floors, level 13 Jaffar/floors, level 14 END; SDLPoP hooks: 'S' state line, POP800_TIME,
   POP800_START, Ctrl+A key field; 15 scenes in tests/m5_scripts; all 49 scripts match SDLPoP
   (tools/oracle_suite.py). Z80: events in a W1 overlay (src/m4/events.asm, 583 B), level start/restart in the W2
   overlay (levelstart.asm play_level, 1.2 KB), resident hooks ~650 B (evres.asm show_time/draw_game_frame);
   tests/m4_test.py compares kid, G and S lines on all 49 scripts: 0 differing. Free: main 676 B, low 444 B,
   block 2 437 B, W1 441 B beside the events overlay, W2 2.9 KB. Not drawn yet: texts, flashes, the flipped
   screen, the shadow's OR/XOR blending and the mirror image; Ctrl+A only from scripts; game over restarts at
   level 1 (no title yet).
19. M5 effects drawn (2026-10-30): the shadow (masked copy + per-plane XOR copy 1-2 px right, kid images, the
   level 4 mirror clip and the kid's mirror image, the level 12 blink), both hurt splashes, the bottom texts
   (SDLPoP font, W2 text overlay), flashes (palette register 0 while the beam is in the playfield), the
   upside-down screen (blit_flip, 192 playfield rows). Pixel-exact against the reference on every tick of the 18
   m5 scenes; checked against SDLPoP screenshots. Costs: the shadow's XOR copy ~2.5 frames per tick while on
   screen (level 5 shadow 19.6, level 12 fight 12.3: M8a item). Resident RAM is exhausted (main 44 B, low 56 B,
   block 2 56 B); W2 3.2 KB free: further resident additions need the reclaims first (guard enter/leave to W1,
   IM2 table, op-list sizing).
   Disk: the game needs ~421 KB raw but compresses to ~22% (zlib): one 320 KB disk (40 tracks, 2 sides) with a
   compressed RAM-disk image and the M7 art is the plan.
20. Floppy boot (2026-10-30): `make` builds build/pop800.dsk, a standard FSMZ 320 KB disk: the ROM IPL boots
   src/boot/boot.asm (1.8 KB at 0xB000), which probes the RAM disk (refuses under 512 KB), reads two FSMZ data
   files with its own WD2793 code (the ROM IPL's sequence) and decompresses them ("PZ", ZX0-style, independent
   blocks; tools/pzpack.py, tools/mkgamedisk.py: 444 KB -> 122 KB, 27%) into the RAM disk and main RAM, then
   starts the game (guards on). tests/m5_boot.py (`make m5boot`): RAM disk and main RAM byte-identical to the
   harness setup, the game identical after 300 ticks. Boot 16.7 s in the emulator (its FDC has no rotation
   timing; ~22-25 s estimated on a real drive: start each track at the sector under the head to save ~3 s).
   M0's disk is now build/m0.dsk. Untested: MZPico, real drive timing, booting from a drive other than 0.
   Decided (user, 2026-10-30): full per-level playthrough scripts are skipped for now (the 52 scripts and
   scenes cover the logic); revisit before release (M8). Save = the original's Ctrl+G (levels 3-13: level,
   time, start hit points to a POP800.SAV file on the game disk); restore (Ctrl+L) comes with M7's title.
21. M5 done (2026-10-30). Ctrl+A restarts the level (keyboard; CTRL col 8 bit 6, A col 4 bit 7), Ctrl+G saves on
   levels 3-13 to POP800.SAV (block 536; magic, version, checksum; WRITE SECTOR with read-back; "GAME SAVED" /
   "UNABLE TO SAVE GAME"), the read side is a W2 entry ready for M7's Ctrl+L (tests/m5_save.py). Reclaim: the
   guard room-transition code moved to two W1 overlays (genter, gleave: +873 B block 2, +162 B main); free
   now: main 173 B, low 56 B, block 2 929 B; W1 holds 4 overlays in turn (room change +0.5%). The loader reads
   each track from the sector under the head first (READ ADDRESS; real-drive gain untested). Emulator notes:
   media_insert's read-only flag is ignored (tests mount copies), its READ ADDRESS byte order differs from the
   WD chip. Not done: the IM2-table and op-list reclaims (still available).
22. M7 design (2026-10-30): docs/m7-design.md (inventory of SDLPoP's title/cutscenes/ending/sound, the MZ-800 PSG,
   proposal, 11-step plan, ~5-6 part-time weeks). Decided (§9 there): separate presentation program swapped by a
   launcher; all presentation art loaded per scene from the floppy (RAM disk kept free for the room cache); hybrid
   sound timing (tests silent); MIDI arranged for 3 PSG voices; SPACE shows the time as in the original (button =
   SHIFT/fire); no Hall of Fame; EGA fades checked in DOSBox first; the level-0 attract demo is ported.
23. M7 step 1 (2026-10-30): launcher + handoff (docs/m7-design.md §10): boot -> PRES (stub) -> game; the game hands
   over before levels 2, 4, 6, 8, 9, 12 and on game over (expired, end, death timeout); a 16-byte handoff block
   (RAM-disk page 5 0x3AC0) carries level, time (SDLPoP does not count cutscene time), hit points and four logic
   globals that survive a level change. The compressed game image (24 KB) sits in RAM-disk page 3's tail; PRES and
   its scenes come from the floppy file POP800.PRS. Swap costs: game -> PRES ~13 frames (+ floppy), PRES -> game
   62 frames (1.2 s; decompression ~100 T/byte). tests/m7_launch.py: launched paths byte-identical to direct ones.
24. M7 step 2 (2026-10-31): the sound model in the logic (docs/m7-design.md §11): SDLPoP's priorities and
   interruptible flags (PoP 1.3 values), the per-tick queue, ~45 call sites, stop_sounds; modes silent (tests),
   ticks, hybrid in kidsim; the Z80 has the silent model (src/m4/sound.asm, sndobj.asm). SDLPoP hook: 'N' line per
   drawn frame (queued, started, playing, stops; started/playing compared only where SDLPoP had nothing playing).
   All 52 scripts match SDLPoP and the Z80 matches kidsim. IM2 reclaim done (0xFE02-0xFF00 free for the music
   buffer). Silent-mode change: a level end without end music changes level at once (as SDLPoP). Free: main 12 B,
   low 53 B, block 2 416 B (the PSG player ~300 B fits).
25. M7 step 3 (2026-10-31): the PSG player (src/m4/psg.asm, 167 B, in the VBLN ISR; idle +39 T a frame) and all
   in-game effects converted from the DOS PC-speaker data (tools/sndconv.py; 3.7 KB sound bank in RAM-disk page 1
   0xE000; per-effect notes in docs/m7-design.md §12); music ids play one-voice speaker placeholders. The launched
   game plays live, every harness test stays silent. tests/m7_sound.py: the emulator's PSG state equals the Python
   player/SN76489 model (tools/sndsim.py) per frame. WAVs in build/sound/ (ab_effects.wav: digitized / speaker / PSG).
26. M7 step 4 (2026-10-31): music. tools/midi2psg.py arranges all 22 MIDI pieces for 3 PSG voices (note loudness
   measured from SDLPoP's own OPL3 rendering, melody/bass bonuses, octave folding below 108 Hz, MIDI length kept
   within half a frame; docs/m7-design.md §13). A new stream format with per-channel decay envelopes, a 254-byte ring
   at 0xFE02 refilled once a tick (no underrun through a 107-frame room draw). In-game bank 2.3 KB (RAM-disk page 1);
   presentation music 9.4 KB in build/assets/sound_pres.bin for PRES. psg.asm 321 B; block 2 91 B free. ISR while
   playing ~900 T avg. Listening: build/sound/ab_music.wav (MIDI / PC speaker / PSG per piece). Found: kidsim's
   SOUND_SECONDS are wrong for presentation pieces 35, 36, 53, 54 (fix in step 5).
27. M7 step 5 (2026-10-31): the waits on sound (docs/m7-design.md §14). A ticks model (a sound lasts ceil(length x
   12/s, 10/s with the sword drawn) ticks; SND_LEFT) next to the PSG player, SND_MODE 0 silent / 1 hybrid (the release)
   / 2 ticks / 3 live. The release: the level 1 crouch and the feather fall wait on the ticks model (feather: the
   225-tick cap and music 39 end together); the death timer and the level end wait on the live music, the level end's
   clock charged exactly as the original's frame count (END_OVER stops it when the live music runs longer, end_charge
   adds the rest when it is shorter; walk_level1 -> level 2 at 60:283 as SDLPoP). SDLPoP hooks POP800_SOUND_TICKS and
   POP800_LEVEL1_MUSIC; 4 new exact scripts in tests/m7_scripts (level1_crouch, level1_end_music, death_music,
   feather_ticks): 56 scripts match SDLPoP and the Z80 matches kidsim; the 52 old ones are unchanged and silent.
   SOUND_SECONDS 35, 36, 53, 54 fixed from the MIDI. Memory: guard snapshot/records moved to low RAM 0x0148; the
   op-list sizing is no reclaim (the largest rooms need 185/192 and 126/128 records). Free: main 9 B, block 2 9 B,
   W2 level overlay 1,665 B: resident code is used up (next reclaims: block 2 constant tables to runtime RAM, or overlays).
   tests/m7_sound.py: all ok; its full run takes ~1.5 h (every music piece played at ~4.5 emulated frames a second), --quick ~12 min.
28. M7 step 6 (2026-10-31): the title in PRES (docs/m7-design.md §15). Steps a-f, j, k of show_title (g-i = step 8,
   the demo = step 9 slot into the step table; for now the title loops), every step on frame floor(5T/6); step f
   waits for music 54 by the ticks model (1502 ticks from a). DOSBox (EGA) check, D8: no palette fade: fade_in_2 /
   fade_out_2 draw / clear in 5 interlaced row passes (y mod 5), j and k are left-to-right wipes, b-f cuts; TITLE.DAT
   colours are a 2x2 dither of four EGA tables (the old title.pack had only the first; PV.DAT res 950/980 dither too:
   step 7); res 45 at y 23. PRES 3,638 B (psg.asm, save.asm and the PZ decoder src/boot/unpz.asm included, not
   forked); POP800.PRS 144 blocks (PRES, the PRES sound bank, the title art 27 KB PZ); 4.8 KB of PRES art space left
   (the intro art needs a second PRS file or per-scene loads). Keys: any key / SHIFT starts level 1, Ctrl+L starts the
   saved level (its cutscene: step 7). No game-side change (m4game/m4ovl/boot binaries identical). tests/m7_title.py:
   42 screens pixel-exact against tools/titleref.py, step frames, PSG = sndsim, the keys; m5_boot, m7_launch, m5_save,
   m7_sound --quick, perfcheck ok.
29. M7 step 7 (2026-10-31): the level cutscenes in PRES (docs/m7-design.md §16). tools/cutsim.py (seg001 port, EGA
   render with the PV.DAT dither), SDLPoP hook POP800_CUT (C/W lines; tools/cut_suite.py 60/60 exact), src/pres/cut.asm
   (engine 4,217 B, loaded with the room entry; pre-shifted sprites from tools/cutart.py), scenes 2/6, 4, 8, 9, 12 from
   floppy, nothing in the RAM disk. tests/m7_cut.py: 7 cases, C lines exact, VRAM pixel-exact on every frame, a key
   aborts, Ctrl+L to level 4. Frame cost median 2.45, max 5.72 MZ frames (budget 5), no drawing skipped. No game-side
   change. POP800.PRS is full (255 blocks): step 8 continues in POP800.PR2 (next disk blocks; built once, never booted).
   Open: (a) that the EGA fade_in_1 / fade_out_1 run no cutscene frames is an assumption shared by hook and cutsim:
   needs a DOSBox recording; (b) untested code: OP_CFT, OP_CUNTIL, OP_CFLASH, OP_CHGN, OP_CSAND, the flash palette,
   play_seq's SEQ_SOUND; SKIP_LATE not triggered in the final build; (c) cutscene music: only id and start frame
   compared, no per-frame sndsim check; (d) perfcheck +0.5..+2.1% with an unchanged game (cause not found; run
   conditions?); (e) DOSBox colours checked on a sample, the PV2 princess and the mouse only as VGA silhouettes.
30. M7 step 8 (2026-10-31): the intro story, time_expired and the ending in PRES (docs/m7-design.md §17). DOSBox
   (tools/dosbox_scene.py) corrected step 7: each EGA fade runs one cutscene frame, not zero (fade-out's inferred);
   EGA flashes (5 flashes, attribute 0 white); level scenes and the ending have 192 room rows; the hail frame is red;
   a key ends only the do_wait waits. A SEQ_SOUND bug found and fixed. No Hall of Fame, no game-side change.
   POP800.PR2 (202 blocks, booted for real); 271 of 1280 disk blocks free. PRES 3,465 B, engine 4,935 B. cut_suite 63/63;
   tests/m7_cut.py now has PSG = sndsim and Ctrl+L on levels 4, 9, 5; tests/m7_story.py new (run whole). Skipped
   drawing: pv_scene 5 of 366 frames (max cost 9.28 MZ frames), embrace 2 of 103 (6.89), logic stays exact.
   Open: a failed Ctrl+L in pv_scene restarts the title (SDLPoP continues); the title reloads its art at every
   start (225 frames); i and j start later than SDLPoP (decoding allowance; j's art read after music 52); the music-start
   model comes from the fade code, not audio (DOSBox gave none); scenes 2 and 6 not recorded separately; floppy and
   music-gap times unmeasured on hardware; perfcheck +0.5..+2.1% unexplained. Remaining in M7: step 10 (keys and cheats); step 9 (the demo) dropped by the user 2026-10-31 (D9 reversed): the title loops.
31. M7 step 10 (2026-10-31): keys and cheats (docs/m7-design.md §18). Room: guard.asm's skill tables (88 B) to runtime
   RAM 0x9F90 (game_init copies them), key handling out of resident code into a W1 overlay OVL_KEYS (469 B; OVL_MAX 8 is
   now full); resident: key_scan 33 B (block 2) + 2 stubs + the script key prefix. Free: main 6, low 53, block 2 61 B.
   Keys: BREAK pause (PSG muted, GAME PAUSED text, the stream resumes: §14's early-ended wait is gone), SPACE = show
   time (button = SHIFT / fire only), Shift+L (levels 1-3, time cap 15:719), Enter/SHIFT while dead = Ctrl+A, Ctrl+R /
   Ctrl+Q title, Ctrl+S sound off (patches the player's OUTs; requests and waits unchanged: intentional difference,
   SDLPoP shortens the death / level-end / crouch waits with sound off), Ctrl+V version text. SDLPoP hook runs the
   real process_key from script key fields; 15 new key_* scripts (71 scripts total: oracle 71/71, m4_test 0 differing,
   release and cheat builds). Cheats only with `make cheats` (build/cheat, pasmo --equ CHEATS=1): release has 0 B of
   cheat code (checked by bytes and symbols); the cheat overlay 832 B. Differences in the cheat build: R revives at
   once, T a 24-tick text, Shift+B blanks once. tests/m7_keys.py (`make m7keys`); all gates green on the final binaries
   (m4_game 52 scenes, m5_boot/save, m7_launch/title/cut/story/sound --quick). perfcheck +0.5..+2.5% (same drift as
   steps 7-8). Not oracle-compared: the pause and Ctrl+S keyboard paths (logic parts are), cheats R / Shift+B / T.
   M7 game work complete (steps 1-8, 10; 9 dropped). Remaining: step 11 (real hardware, part of M8), M8a speed, M8.
32. M8a part 2 (2026-10-31 / 11-01, docs/perf.md "M8a part 2"): A. gate fixes: a gate's modifier change redraws only
   when min(mod,188)/4 changed and only the tiles that draw the bars (src/m4/gate.asm 76 B in block 2, view.asm
   vrd_gate): gate stretch 6.72 -> 5.13 frames/tick, closing ticks without visible movement 6.69 -> 3.7 (the floor),
   visible step 9.8 -> 8.1, opening with the kid 6.79 -> 5.55. A first version regenerated the wrong tile for a gate in
   columns 0-8 of the shown room (the m4/m6 scene sets never cover that; m5's level5_shadow_potion / level6_shadow_exit
   caught it): fixed; from now on every pixel gate run includes the m5 set. Step profile of a visible step (+4.4 frames):
   tile_regen x2 1.07, lay pass 1.89 (8 pieces), fill 0.23, shadow write 0.29, object pass ~0.5, scan ~0.4. The bar
   slice (image 52, 8-row lattice period) is not vertically uniform, but the stack moves rigidly: a one-row shift of
   shadow+VRAM plus two short pieces could replace the lay pass (not done). B. time-exact pacing (PACE_MODE at 0x2161,
   default 0 = draw every tick; mode 1: fixed 4-frame tick clock, undrawn ticks when a whole tick behind, at most 2 in a
   row, old rects from the last drawn position; `build/pace/` disk; tests/m8_pace.py: logic and drawn screens identical
   to mode 0). Measured mode 0 -> 1: walk 30-60 8.07 -> 11.5-12.3 ticks/s (7.4 screens/s), walk 190-260 4.55 -> 5.93,
   gate opening 9.01 -> 11.04, gate 200-260 9.75 -> 12.42, fight 5.48 -> 8.24 (4.5 screens/s). Decision (user,
   2026-10-31): not adopted, kept as a backup switch; speed comes from drawing work first. perf baseline: original
   values kept, gate updated to 5.13. Room: 24 jp->jr in cold block-2 code. Free resident: main 16, low 4, block 2 26 B.
   All gates green on the final binaries (m4_game m4/m6/m5 every tick, m4_test 63 scripts, launch, keys, pace, perf).
   Music: a listening experiment (tools/midi2psg_exp.py, build/sound/exp, copied to the user's Downloads): periodic-noise
   bass + fixed roles + arpeggio; found mz800emu's periodic noise at f2/8 with a 16-bit register vs the datasheet's f2/15
   15-bit: needs a hardware check before adoption (also affects effect 4); an arpeggio needs a player command (streams
   3-5x otherwise, the in-game ring would underrun). Pending the user's listening verdict.
33. Decision (user, 2026-11-01): the RAM-disk size is probed at boot and used when available (not required):
   256 KB = per-level loading from floppy (one environment, one guard set, one blueprint; no torch cache; game image
   reloaded from floppy; +4-5 s per level start; late M8 option, two builds not needed), 512 KB = today's layout, 1 MB+ =
   derived caches generated on the MZ (the floppy stays 320 KB): on-demand pre-shifted sprite frames (kid first, then
   guards; fetch 0.9 -> ~0.3 frame/tick), pre-mirrored frames (-0.25), pre-composed fore layer per room (-0.5, also on
   512 KB), visited-room cache (~33 KB a room, revisit 106 -> ~25-30 frames). This replaces the M8a items "pre-mirrored
   kid pack" and "visited-room cache"; it comes after the port-independent drawing work (beam wait, kid rect split,
   kid logic trims, standing guard, gate column shift). memext is not a speed source (INIR = LDIR per byte; seeks ~0.1
   frame/tick); a Pico-side compositor would be a separate project (docs: this conversation's analysis to be written up
   in docs/perf.md when the work starts).
   Addendum (user, 2026-11-01): some users have 16 MB RAM disks. The caches never evict there: all pre-shifted and
   mirrored kid and guard frames (~1.8 MB) and every room of the game (~13.4 MB, cached on first draw, across levels and
   restarts); the room cache = per-room shadow slots (the renderer draws straight into the room's slot: a visited room
   costs nothing extra; revisit ~15-20 frames: VRAM copy + op lists; invalidated by off-screen tile changes through the
   animated-object list). No pre-rendering pass at level entry (~87 frames a room: 35-40 s a level). far_* must treat
   the page number as a full byte (MZ-1R18 8-bit page register, pico_rd 24-bit); test once with a 16 MB emulator config.
34. Resident-memory reclaim (2026-11-01, docs/memory.md "Memory reclaim", docs/perf.md): free resident code main 912 B
   (was 16), low 115 (was 4), block 2 275 (was 26), no behaviour / pixel / trace / speed change. Moved by profiler
   evidence over all 46 scene scripts: the start-up (src/m4/gstart.asm in the level-start overlay; tables_init ->
   src/m1/tables.asm, pr_build -> src/m3/prbuild.asm, built at start now), trigger_button & co -> events overlay, a new
   rare overlay (id 8: hit-point strips, item pickup, chomper death), lr_special -> guard-enter overlay. Left resident
   as too warm: start_chompers, hurt_by_sword, jump/grab helpers, flames_build, loose floors. OVL_MAX 8 -> 12; the
   overlay area moved to RAM-disk page 7 0xD900 (1.8 KB free), page 6 0xE280-0xFFFF free again. PRES art may use
   0xDF40-0xFBFF (m5_boot compares to block2_end now; PRS entry addresses changed, PRES code not). Gates all green on the
   final binaries (m4_test 71 scripts twice, m4_game m4/m6/m5 every tick, launch (one load-related emulator flake under 9
   parallel runs, idle rerun ok), keys, pace, boot, save, sound quick, title, cut, perf: door step +1.9% explained as the
   beam-wait raster phase, identical routine costs). Next: the drawing work (beam wait, kid rect split, kid logic trims,
   standing guard, gate column shift), then the RAM-disk tiers (item 33).
35. Scope additions (user, 2026-11-01), ordered after the speed work (items 33-34's drawing list and tiers):
   a. pico_rd backend (M8, 3-5 days): far_seek per backend; the ~80 data-port immediates patched at boot from a
      build-generated patch table (EAh -> 46h); pico_rd variants of the two paths that rely on EBh = EAh + 1
      (shadow_write, the restore; pico_rd's add-delta register fits row strides); size from the device (wraps at size);
      add the pico_rd device to mz800emu (we build it; the firmware's pico_rd.cpp is the reference) and run the gate
      suite once in pico_rd mode. Matters: every MZPico board has pico_rd, not every setup a 512 KB RAM disk.
   b. 256 KB RAM disk (M8, ~1 week, after the layout settles): per-level loading per item 33.
   c. 16 KB VRAM (no extension: 320x200 in 4 colours): declined for this port (all art to 4 colours, 2-plane kernel and
      renderer, doubled pixel tests, PRES: 3-5 weeks for a worse-looking game). New code keeps the plane count a
      constant so a "lite edition" stays possible.
   d. Easter egg, two-player sword fights (after M8): local first (1-1.5 weeks): player 2 on joystick 2 (port F1h) or a
      second key set replaces autocontrol_opponent's control bytes; activation by a key combination on the title (handoff
      action "fight": arena, opponent type incl. fat / skeleton / Jaffar / the shadow = kid sprites); fixed arenas, hit
      points to zero -> text, rematch; kidsim gets the mode (no SDLPoP oracle: new behaviour; Z80 vs kidsim exact);
      ~100 B resident + the level-start overlay. Then network (+2-3 weeks): lockstep over the MZPico NET device API as
      BomberNet uses it (~/src/bomberman docs/net-protocol.md, net-timing.md: rooms with a 4-letter code, host/join,
      ready -> seed + start frame, per-frame keys, adaptive input delay, desync detection, relay): the netdev client calls
      in Z80, a room screen in PRES, the m4test state snapshot as the desync hash, tests with two emulator instances
      against the relay; both sides MZ-800 + MZPico with NET.
36. Repository on GitHub (2026-11-02): MZPico/mz800pop, public, GPL-3 (LICENSE; the README's licence note; the converted
   SMS music in assets/sms is third-party and not under the GPL, assets/sms/README.md). Work goes through branches and
   pull requests to main only (never a direct push), each PR reviewed by CodeRabbit and its review addressed in the PR.
37. PR checks on GitHub Actions (2026-11-02, .github/workflows/pr-checks.yml, docs/ci.md): every PR to main builds the port
   from a clean checkout on the standard Ubuntu 24.04 runner (pasmo, mz800emu, SDLPoP, mzdisk, SDL3 from pinned commits,
   cached) and runs the PR tier in four jobs (~22 min wall). The DOS v1.3 data is never committed, uploaded or cached: each
   job fetches it from archive.org at run time (tools/ci/fetch_dos_data.py; unpacked with 7z, never executed), checks
   every DAT against tools/ci/dos_data.md5 and retries the download. The SMS presentation music (assets/sms, the PSG
   streams) and the OPL level measurements (assets/opl/levels.json) are committed, so a clean clone builds the exact disk
   (pop800.dsk md5 09723617..., byte-identical to the local reference build).
38. mz800emu tracepoints, PSG write log and VRAM hash (2026-11-02, MZPico/mz800emu#1, merged into wasm as 0e37a91; CI pins
   that commit): a tracepoint records registers / memory / the VRAM planes' CRC-32s without stopping the emulator
   (tools/emu.py trace_add / collect). The tests that stopped at every tick or interrupt use them now (POP800_EMU_TRACE=0
   keeps the old path): m7_sound full ~1.5 h -> 5.4 min, m4_test on all scripts ~45 -> 4.2 min.
39. Full regression on the runners (2026-11-02, .github/workflows/full-regression.yml): every test on its full set in 11
   parts (~30 min wall), by hand or by a push to a regress/** branch (tools/ci/regress_only for some parts). The early
   milestones' tests (M0-M3: smoke, m0, m1, m3 on all 14 levels) got an exit status and are gates now (part "early").
40. Local runner (2026-11-02, tools/testrun.py, docs/ci.md "Local testing"): `make check` runs the tests the changes since
   the merge base can affect (plus the last failures), in parallel, each cached by a hash of its inputs; `make
   check-smoke` (~1.6 min cold), `make check-full` (everything, no cache). The PR tier, the full regression, the smoke
   tier and the runner take their tests from one list, tools/ci/suite.py.
41. Decisions and known issues (2026-11-02): the heavy runs belong on the runners (locally `make check` only, never a cold
   full suite); M7 step 9 stays dropped (item 31); the RAM-disk tiers of item 33 (512 KB baseline, 1 MB+ derived caches,
   16 MB never-evict caches, 256 KB per-level loading as a late M8 option) stand; the pacing switch PACE_MODE (item 32 B)
   is kept as a backup, not adopted. Known issue: mz800emu is not run-to-run deterministic: the same build varies by up
   to ~1-2 % in some perfcheck stretches (door step 17.88 vs 18.09 frames), so speed changes are judged on the median
   of several runs.
42. M8a part 3, the beam wait (2026-11-02, docs/perf.md "M8a part 3: the beam wait (measured, change parked)"): measured
   with tracepoints where a tick waits for the beam before its chunk copies: scheduling + waiting 0.215 frames a tick
   walking (walk_level1 30-60), 0.477 fighting (fight1 60-160), 0.065 at the gate (gate_push 200-260), 0.214 in the traps
   (traps_b1 0-300), 0.58 in a door step. Causes: the fixed top-first copy order, tries that recomputed every chunk
   (first copy 19.2 lines after the beam read for 3 chunks, the model 3-4 lines pessimistic), and in fights the
   same-frame rule over wide side-by-side character chunks (9 of 116 flushes fell back to one at a time). A scheduler
   variant (values once per flush, every order tried with overlapping chunks kept in order so the screen is the same,
   BEAM_GUARD 12 -> 8, BEAM_MARGIN 20 -> 16; no torn copy or split same-frame flush in the tracepoint checks) gains
   0.07-0.09 frames a tick (perfcheck: normal 6.20 -> 6.13, walk 190-260 11.00 -> 10.83, gate 5.13 -> 5.06, traps
   6.03 -> 5.97, fight 9.13 -> 9.07). Decision (user, 2026-11-02): parked in PR #8 (perf/beam-wait, a draft) for its
   resident cost (~478 bytes, end_of_code 0x7870 -> 0x7B05, the low block -183); rebased and merged when there is resident
   room. A no-wait test build would add only -0.4 to -1.3 % (fight -3.7 %): no tearing switch.
43. M8a part 4, the kid area (2026-11-02, docs/perf.md "M8a part 4: the kid area (measured)"): measured with tracepoints
   before building (no code change). The object pass per tick, frames: walk_level1 30-60 place 1.23 (of it the fetch
   0.90), background 0.63, flames 0.16, people 0.45, fore 0.70, copy 0.58, chunk setup 0.08, flush waiting 0.21 = 4.02;
   fight1 60-160 place 2.06 (fetch 1.55), background 0.96, people 1.20, fore 1.09, copy 0.80 = 6.84; traps_b1 0-300 3.47;
   gate_push 200-260 0.98. A character's old and new rects nearly coincide (kid box 174 against an exact union of 170
   bytes x rows walking, 222 / 219 fighting; old and new disjoint or overlapping less than half in 3 of 30, 7 of 257,
   0 of 100, 6 of 298 ticks), so keeping them apart would save <= 0.007 frames a tick (chunk cost model 31 K + 1,140 h
   + 160 w h T), not joining the kid's and the guard's boxes ~0.035 in fights, against ~40-60 bytes in block 2.
   Decision: not built (rule: >= 0.2 frames a tick at < 250 bytes). M8a list item 7's old/new split is dropped; what
   the numbers point to: the fetch (0.9-1.55 frames a tick; pre-mirrored pack, a shift-free path), narrow tail chunks of
   9-11-wide boxes (~0.13 frames a tick in fights; needs chunks wider than 8 bytes), the fore pass (item 7's hidden fore
   pieces, M8a list item 2) and the background's per-row cost (M8a list item 3).
44. M8a part 5, the fore layer (2026-11-02, docs/perf.md "M8a part 5: the fore layer (measured)"; numbered after item 43
   of PR #10, the kid area): measured with tracepoints before building (no code change). lay_fore_rect per tick, frames:
   walk_level1 30-60 0.658 (scan 0.147, laying 0.511), fight1 60-160 1.073 (0.246 / 0.827), traps_b1 0-300 0.282 (0.116 /
   0.166), walk_level1 190-260 0.228 (0.215 / 0.013). The scan ~4.4-6.3 K T a chunk (~300 T for each of 11-14 tile cells,
   all 4 tile rows); a chunk lays 0-3 ops (0.02-0.91 on average), an op ~22-24 K T copying (pillar front, wall face) or
   ~11-34 K masked, most of it per row (470 / 660-690 T a row). The ops of a chunk barely overlap (union 90-93 % of
   their sum). Per room (levels 0-14, 340 rooms) the fore layer covers up to 7,680 screen bytes (level 6 room 8): ~31-38
   KB, 105-145 rooms fit the largest free RAM-disk piece (11.1 KB); the room draw's fore pass is 17-30 frames of a room
   change. Estimate: gain walk -0.02 to +0.10, fight +0.18 to +0.22 (mostly the scan replaced by a lookup), ~180-250
   resident bytes, a room change +10-30 frames. Decision: not built (rule: >= 0.2 frames a tick, < 250 bytes, fits the
   RAM disk, < 5 frames a room change). Pointer: a faster fore scan (tile rows from the chunk's rows, SL_CNT walked by
   pointer: ~1.5-2 K T a chunk, walk -0.08, fight -0.15 frames a tick, ~40-80 bytes, run_rect gains too).
45. M8a part 6, the fore scan (2026-11-03, docs/perf.md "M8a part 6: the fore scan"): rr_table (lay_fore_rect's fore
   scan and run_rect's tables) walks SL_CNT by pointer along each tile row (an empty cell ~35 T instead of ~300) and
   tests a non-empty cell's slice rows in registers; lay_fore_rect takes its bounds from rect_bounds. Same rows,
   columns and op order: the same pixels. The scan of a chunk 4.4-6.3 K T -> 1.7-3.0 K T; main code 67 bytes smaller
   (end_of_code 0x7870 -> 0x782D; low block and block 2 unchanged). perfcheck medians of 3 runs, main -> this: walk
   30-60 6.20 -> 6.10, fight 9.13 -> 9.00, traps 6.03 -> 5.96, walkthrough 190-260 11.00 -> 10.70, level door 17.88 ->
   17.45, room change 106.92 -> 106.58, gate 5.13 -> 5.11 (the tile redraws share the scan: the walkthrough and the
   door gain more than the estimate). The full regression on the runners passed (regress/fore-scan).
46. M8a part 7, standing characters (2026-11-03, docs/perf.md "M8a part 7: standing characters"; numbered after item 45
   of PR #13, the fore scan): measured first with tracepoints over the 16 fight scripts and the walkthrough (per tick and
   character: unchanged slots, the chunks and copies of his rect, VRAM after each tick). The guard is unchanged (same
   frame, chtab, mirror, shift, rect, clip, XOR offset) in 50-75 % of the ticks he is shown (fight1 60-160: 62 of 100;
   en garde, waiting, lying dead), the kid in 1-12 % of fight ticks, never in the walkthrough; his fetch is already a
   cache hit (0.003 frames a tick), his chunks are not: 0.39-2.24 frames a tick of compose + copy in the fight scripts
   (fight1 60-160 0.79), with his pixels the same outside the other dirty rects in every such tick (VRAM checked).
   Built: st_look (people2.asm, main) keeps the slots' visible flag, image key, rect, clip and XOR offset from the last
   drawn tick (low RAM 0x01CA-0x01FC) and pp_rects (block 2) leaves an unchanged character's rect off the dirty list (and
   unjoined) unless this tick or the last has overlay ops or a hurt splash or a room was drawn since (sprite_forget).
   Cost 192 bytes: main +169 (end_of_code 0x782D -> 0x78D6), block 2 +19 (block2_end 0xEB11 -> 0xEB24), low +4
   (end_of_low 0x1F8D -> 0x1F91). VRAM after every tick identical in all 18 measured scripts. perfcheck medians of 3
   runs, main (11e43a4) -> this: fight 9.00 -> 8.23 (baseline 8.99 -> 8.23), walk 30-60 6.10 -> 6.10 (no comparison
   while no guard is shown), door 17.45 -> 17.54 (within its spread), walkthrough 190-260 10.71 -> 10.73, traps 5.96 ->
   5.96, room change 106.58 -> 106.32, gate 5.11 -> 5.11.
47. M8a part 8, small items (2026-11-03, docs/perf.md "M8a part 8: small items"): measured first (tracepoints, the
   per-routine profile after parts 6-7, documented there). Not built: narrow tail chunks (9-11-wide boxes; after part 7
   0.03-0.06 tails a tick, 0.04-0.06 frames, wider chunks need a variable compose stride and new kernels) and the
   chunk-major shadow (the seeks and the +40 are 51 T of 134 a plane-row: <= 0.11 / 0.15 frames a tick, and unaligned
   object chunks cross two strips). Built, each its own commit, VRAM after every tick identical to main's: restore_shadow's
   row loop (a jump into its own INI chain, no compose advance for full rows, the counts in B' / C'; main +23 bytes),
   spr_draw's row loop (pointers kept in registers; main +19) and the tile-change snapshot walked as 6 runs of tile bytes
   with the buttons' pressed state from a list built per room (view.asm; low block +81, end_of_low 0x1FE2, 30 free; its
   pointer table moved to 0xF58B). perfcheck medians of 3 runs, main (80c4945) -> this: walk 30-60 6.10 -> 5.72, fight
   8.23 -> 7.73, traps 5.96 -> 5.63, walkthrough 190-260 10.73 -> 10.26, level door 17.54 -> 17.06, room change 106.56 ->
   106.05, gate 5.11 -> 4.99 (baseline lowered except the room change). Main end_of_code 0x78D6 -> 0x7900 (768 free).
48. RAM-disk tiers, design (2026-11-03, docs/ramdisk-tiers.md; for review, the caches not built): measured with
   tracepoints (tools/fetchstat.py) that the fetch is a sixth RAM-disk reads and two thirds the shift (walk 30-60: 0.899 =
   setup 0.026, reads 0.153, shift + mirror 0.610, loop 0.110; fight 60-160 1.547 = 0.050 / 0.287 / 1.029 / 0.178); the
   mirror is done at the fetch (~20 T a byte of the shift's 96-103). Working set over all 71 scripts: 2,553 (chtab, frame,
   mirror, shift) keys, 1.5 MB of cell buffers (the whole key space 7,184 keys, 4.4 MB); a first pass repeats few keys
   (walkthrough 12 %, fights 25-66 %). Design: an entry = the cell buffer as char_fetch leaves it plus a 4-byte header,
   a direct-indexed directory in page 8 (471 ids x 16 keys x 4 bytes = 30 KB; ~350 T a lookup + 21 T a byte), filled on
   first use (+~800 T + 21 T a byte on that fetch), a FIFO ring on 1 MB (pages 8-15), never full on 16 MB; ~300
   resident bytes; pixels identical by construction. Estimate: warm walk -0.72, fight -1.22 frames a tick (tick 5.72 ->
   ~5.0, 7.73 -> ~6.5), first passes up to +0.1-0.25; over one session of all scripts the fetch 0.866 -> 0.301 (16 MB) /
   0.447 (1 MB, frames only). Room cache (second step): per-room shadow slots (2 a page), revisit ~15-20 frames,
   invalidated by a per-slot tile snapshot compared at the revisit; 316 rooms fit 16 MB with the frames. Built here, no
   behaviour change: the boot's probe counts the pages (rd_top 7 / 15 / 255) and the launcher puts it at HO_MAIN + 15
   (0 = the harness = 512 KB layout; nothing reads it yet), `POP800_RD_SIZE` selects the emulator's size, m5_boot tests
   the probe at 512 KB / 1 MB / 16 MB. Found: every test so far ran with 1 MB (the INI); mz800emu's MCP reaches only RAM-disk
   pages 0-51 with 16 MB (128-region limit). The full regression passed with the INI at 512K and at 16M. Follow-ups
   (user): prefetching (sections 7: the ticks idle only 0.05-2.3 frames a second, so prefetch = work at boot / level
   start; pages 8+ survive levels and PRES) and prebuilt / boot-generated fixed layouts and the hybrid (section 8: a key
   table, lookup ~110 resident bytes, no fill or eviction; 1 MB store kid + sword 400 KB + the level's guard set 80 KB
   chosen from the scripts' use: fetch 0.871 -> 0.399 a tick with no cold pass, against the run-time cache's 0.447 with
   +0.1-0.25 first passes; the kid's set on the floppy needs an 80-track image (88 KB PZ for 400 KB; the full set 475
   KB) and ~16 s of boot, generated at boot from the packs ~6 s (a dedicated generator) / ~15 s (today's code); the
   guard's 80 KB at a level start +1.2 / +3.0 s; MZPico's [ramdisk] takes a flat image file, persistent). Recommended
   (section 9): the fixed-layout store with the kid core generated at boot (~3-4 days), a dedicated generator and the
   level's guard set (~2-3 days), CI with a RAM-disk dimension, 16 MB extras, then the room cache (~4-6 days); open
   questions in section 10.
