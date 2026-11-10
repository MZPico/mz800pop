# Graphics source sets and the MZ-800 palette

## Best donor: DOS EGA/Tandy art (EDUNGEON.DAT, EPALACE.DAT + ega[] mappings of KID/GUARD/PRINCE DATs)
- 320x200, 16 fixed EGA colours, same 32x63 tile grid and sprite metrics as VGA/SDLPoP data; gameplay area 320x192 + 8-px status line.
- EGA palette is the same RGBI family as the MZ-800 (black, blue, red, magenta, green, cyan, yellow, white + bright variants); only EGA index 6 (brown #AA5500) differs from the MZ-800 dark yellow (olive-ish). Pixel-for-pixel reuse with at most one colour remap. Needs a DOS v1.0-1.3 install (v1.4 is VGA only) and PR to extract.
- Fallback: quantise the VGA PNGs shipped in SDLPoP/data (dungeon = blue-grey ramp maps well; palace warm tones need dithering).
- VGA image counts: KID 219 (12-21 px wide, 37-51 high), VDUNGEON 132, VPALACE 149, PRINCE 57, GUARD/SKEL/SHADOW/VIZIER/FAT ~34/28/32/34/34, PV 98, TITLE 10. Per-set 16-colour palettes (env, kid, guard, objects).
- Amiga = same art as VGA; Atari ST = same art, brighter palette. X68000/PC-98/FM Towns = redrawn Japanese art at higher resolution, >16 colours — not a good 16-colour donor. SNES = different game.

## MZ-800 palette (confirmed: Sharp MZ-800 Technical Reference pp.27-28; mz800emu)
- Colour code = I*8 + G*4 + R*2 + B: 0 black,1 blue,2 red,3 magenta,4 green,5 cyan,6 yellow,7 white,8 grey,9 lt blue,10 lt red,11 lt magenta,12 lt green,13 lt cyan,14 lt yellow,15 bright white.
- Port 0xF0: bits 5-4 = palette register PLT0-3, bits 3-0 = colour; bit 6 = palette group select. In 320x200/16 only ONE group of four pixel values (upper two bits = group) is remapped by PLT0-3; the other 12 are output as their IGRB code. Border (port 0xCF) not paletted.
- So: effectively fixed 16 colours with 4 remappable entries (useful for flash/fade effects and for one palette tweak per level, e.g. mapping a group to the palace browns).

## Palette mapping experiments (2026-10-25, tools/palette_check.py, tools/ega_check.py)
- Sheets: docs/research/palette-check.png (nearest-colour mapping), docs/research/ega-check.png.
- Nearest-colour mapping of the VGA art: dungeon set converts well (blue/grey/white ramp); the
  palace tan/cream ramp turns yellow-dominant and the kid's skin tones collapse to grey. Per-set
  hand-tuned colour tables are needed for KID/VPALACE (or the real EGA DAT art).
- The ega[] block in SDLPoP's .pal files does NOT behave as "two EGA indices per VGA entry":
  rendering with that interpretation gives wrong colours (cyan/green kid). Treat those bytes as
  unknown; do not build the pipeline on them.
- KID/PRINCE VGA palettes hold only 8 distinct colours each (entries 8-15 repeat 0-7 with
  small variations), so a sprite set needs <= 8 colours: good for planar packing and for
  colour-remap tricks per enemy type.

## SDLPoP rendering facts needed to reproduce rooms (verified pixel-exact, 2026-10-25)
- Transparency: SDLPoP colour-keys palette index 0 of every image regardless of the PNG's tRNS chunk;
  other palette entries with RGB black (e.g. PRINCE.DAT index 11) are opaque black.
- "mono" blits (0x40 | colour) take the colour from the global 16-entry VGA palette, which SDLPoP
  modifies at start: entry 6 = (0x30,0x26,0x14) tan (wall decals), entry 12 = (0x38,0x00,0x0C).
- Palace wall bricks: solid rectangles in colours 0x61-0x64 / 0x66-0x69 = wall palette (res 360)
  entries 1-4 / 6-9, chosen by the PRNG seeded with the room number (gen_palace_wall_colors).
- Dungeon wall decoration (wall_pattern): PRNG seeded with room + row*10 + col, LCG
  seed*214013+2531011, (seed>>16) % (max+1).
- SDLPoP's "coloured torches" extension recolours flames from the torch modifier; the original
  zeroes nothing but uses the modifier as the first animation frame. We zero it (SDLPoP).
- Level colour variations (v1.3, PRINCE.DAT res 20) retint env/wall palettes on levels 3, 7, 8, 9,
  12, 13, 14; irrelevant for a fixed palette, could drive the MZ-800's 4 remappable entries later.
- Oracle: `external/SDLPoP/prince megahit <level> --screenshot-level` (SDL dummy video driver) writes
  screenshots/screenshot_000.png with rooms placed by BFS from the start room, 320 x 189 apart;
  tests/m2_oracle.py reproduces the placement and compares rooms pixel by pixel.

## Palette tuning (2026-10-25)
- tools/palettes.json maps each set's .pal entry index to an MZ colour; ImageSet applies it by RGB
  (the SDLPoP PNGs of one set do not share one palette order, some carry a dummy entry 0).
- Dungeon tuned to the EGA look: bricks light/dark grey (7/8), mortar black, floor tops cyan (5),
  flames red/white, prince with orange skin (2) and white clothes. Mock-ups:
  docs/research/screen_dungeon_mz800.png, screen_palace_mz800.png (2x).
- The oracle test (tests/m2_oracle.py) runs with overrides disabled so it checks geometry/logic only.

## EGA art pipeline (2026-10-26) — the chosen art source
- Source: the user's DOS v1.3 installation in external/dos/PRINCE (git-ignored, not redistributable).
  EDUNGEON.DAT / EPALACE.DAT hold the EGA environment art; sprites (KID, GUARD, FAT, SKEL, VIZIER,
  SHADOW, PRINCE, PV, TITLE) are the same 4-bpp images as VGA, recoloured through a table.
- tools/datfile.py reads DAT containers (checksum byte + resource; RLE/LZG, both orientations),
  verified identical to SDLPoP's PNG extraction on KID.DAT (219 images) and GUARD.DAT (34).
- Colour rules, verified pixel-exact against DOSBox (machine=ega) captures of level 1 room 1:
  * environment art: pixel value = EGA colour number (the palette resource's nibble table at bytes
    68..75 is the identity); value 13 is displayed as black (opaque black, distinct from 0 = transparent);
  * sprites: pixel index -> EGA colour through the 16-nibble table of the set's palette resource
    (KID: 1->red, 2->13 (black), 3->white, 5/6->brown, 7->light grey, 15->white ...); guards take
    the table from GUARD1.DAT (palace) / GUARD2.DAT (dungeon);
  * EGA colour -> MZ-800 colour: [0,1,4,5,2,3,6,7,8,9,12,13,10,11,14,15] (IRGB -> IGRB bit order);
  * "mono" blit colours are EGA colour numbers directly;
  * empty image resources (2 bytes) in E*.DAT are replaced by the "optional graphics" at 1000+id
    (SDLPoP load_more_opt_graf), e.g. palace arches 1201-1213;
  * palace walls in EGA are drawn like dungeon walls (wall images 361+, dividers), the VGA-only
    coloured-brick rectangles and dungeon marks are skipped.
- DOSBox oracle: build/dosbox/pop.conf (machine=ega, captures to build/dosbox/capture); SETUP must be
  run once to select EGA (writes CONFIG.DAT: first word 4); xdotool drives keys, Ctrl+F5 captures.
- Mock-ups: docs/research/screen_dungeon_mz800.png, screen_palace_mz800.png (EGA art on the MZ palette).

## MZ-specific recolours (2026-11-10, PLAN status 74) — deviations from the EGA look
Chosen by the user from mock-ups (kept out of the repo: they are renders of the original art). All three are asset-side
only (no code, no resident memory); the references (tools/popdata.py, tools/titleref.py through build_assets.title_image,
the kid pack that tests/m4_game.py and tools/cutsim.py decode) carry the same rules, so the exactness tests check the new
look.
- Kid's feet (popdata.KID_FEET): KID.DAT values 13 / 14 are the feet's own entries (bare skin in VGA; EGA white 15 /
  light grey 7 = white shoes). Now skin yellow 6 for both ("K1a flat skin"); the shade colour is still open (6/8;
  6/0 is the same on the MZ, a sprite's black being drawn as 8).
- Palace floor tops (popdata.palace_env_post, "F3"): EGA red 4 (MZ red 2, only floor pieces carry it) -> a red 2 /
  black 0 1-pixel checker, a dark maroon. Phase from each image's bottom row, odd for the pieces drawn at an odd
  offset from the row (PALACE_FLOOR_ODD: 35, 36, 99, 144). Over all 6 palace levels' rooms the only joints left are
  the 10 rows where a raised plate meets its own right piece (42, drawn one row up beside an unpressed opener: 43
  joints, 430 pixel pairs); ordinary tile joints have none. The walls are unchanged.
- Title sky ("T2w", build_assets.title_sky): EGA brown 6 -> MZ yellow 6 made the sky the palace's colour. Inside the
  arch window only (flood fill from (160, 40) over rows < 100, bounded by the arch's light yellow 14) yellow 6 becomes a
  red 2 / dark green 4 checker (= brown); ornaments and road keep yellow. +480 bytes PZ of title art (PRES: 759 free).
- Composite video (not checked on hardware yet): a 1-pixel column pattern in 320-pixel mode is a ~3.5 MHz signal,
  close to the PAL colour subcarrier, so through composite the checkers can show cross-colour (a shimmer of false
  colour) and dot crawl instead of a clean mix; on RGB and in the emulator they mix as intended. The palace walls' and
  the arch lattice's checkers (2026-10-26) are the same kind of pattern, so how they look on the user's set predicts
  these. The floor's red/black is a strong luminance step (likely the most visible artefact, over large areas); the
  sky's red/green has two hues of different brightness. Fallbacks if it is bad: solid red 2 floors (as before) and a
  solid red 2 sky ("T1w").
