# RAM-disk tiers: design and measurements (2026-11-03)

Status: **design for review**; measured, nothing of the caches built. The enabling changes in the same PR change no
behaviour: the boot's probe now counts the RAM disk's pages and the launcher hands the size to the program it starts
(nothing reads it yet), the emulator launcher takes a size (`POP800_RD_SIZE`), `tests/m5_boot.py` tests the probe with
512 KB, 1 MB and 16 MB, and `tools/fetchstat.py` measures the sprite fetch.

The decisions this builds on (PLAN.md item 33 and its 16 MB addendum, item 41): the RAM-disk size is probed at boot and
used when it is there, never required; 256 KB = per-level loading (late M8), 512 KB = today's layout, 1 MB and more =
caches the MZ derives from the data it already has (the floppy stays 320 KB): pre-shifted and pre-mirrored sprite
frames on demand (the kid first, then the guards), the visited-room cache; 16 MB = the caches never evict. The game
must behave and look the same on every size: the caches change only the speed.

Numbers are frames (71,136 T) per tick unless noted; the reference build is main cc72e14 (perfcheck medians: walk 30-60
5.72, fight 7.73, traps 5.63; docs/perf.md "M8a part 8").

## 1. The probe and how the size reaches the game

### The hardware and the emulator

The MZ-1R18-style RAM disk (STD protocol): `OUT (E9h)` = the 64 KB page, `OUT (C),A` on EBh with B = the high byte =
the 16-bit address, EAh = data with auto-increment, `IN (F8h)` = page and address 0. mz800emu
(src/emulator/hw-generic/ramdisk/ramdisk.c) emulates 64 KB, 256 KB, 512 KB, 1 MB and 16 MB (`mr1r18_size` = 64K,
256K, 512K, 1M, 16M; the page register is ANDed with the size mask 0x00 / 0x03 / 0x07 / 0x0F / 0xFF, so a smaller
card aliases page p to p & mask; the address is a uint16_t that wraps inside the page without carrying into the page
register). The project INI (emu/mz800emu.ini) has had `mr1r18_size = 1M` all along: every test so far ran with 1 MB,
and the game used pages 0-7 only. Nothing in mz800emu needs changing for the tiers themselves; for the tests:

- its MCP lists at most 128 memory regions (src/emulator/mcp/dispatch.c `MCP_REGIONS_MAX 128`): with 16 MB only RAM-disk
  pages 0-51 can be read or written by `region_read` / `region_write` (the game itself reaches all 256). The harness
  writes pages 0-7 only, so nothing breaks; a test that inspects the caches above page 51 needs the limit raised (512)
  or a bank-addressed RAM-disk command: a later PR to MZPico/mz800emu (branch from `wasm`).
- `mr1r18_type = SRAM` (the INI's) saves the whole RAM disk to its file on every exit (16 MB with the 16M size) and is
  why instances started in one directory share and corrupt one file; `STD` (no file, filled with 0xFF at start) would
  remove both. Not changed here (the tests write everything they need; worth considering when CI runs two sizes).
- pico_rd (port 45h, PLAN item 35a) is not emulated at all.

### The probe (src/boot/boot.asm rd_probe, built in this PR)

A 2-byte marker (p, p xor 0x5A) at offset 0 of each page p, written from page 255 down to 0, then read back from page 0
up; the RAM disk is the pages up to the first wrong marker. On a card that ignores the high page bits, page p aliases a
lower page whose later write replaces the marker; a page without memory behind it does not keep one (an open bus reading
the same value twice fails the second byte). `rd_top` = the last good page: 7 = 512 KB, 15 = 1 MB, 255 = 16 MB (any
count of pages works, not only powers of two). Below 8 pages it still refuses (the 256 KB tier changes that later).
The original bytes of all 256 pages are saved in TRKBUF (free until the directory is read) and put back, aliased pages
last-written-lowest, so a page gets its own bytes. ~0.1 M T (30 ms); the launcher's image grew 35 bytes (2,331 of 3,072).

`tests/m5_boot.py` boots with 512 KB, 1 MB and 16 MB (temporary INIs) to the end of the probe (`rd_probed`): rd_top
7 / 15 / 255, accepted, and the pattern it put at offsets 0-1 of each reachable page beforehand is back. The 256 KB
refusal is tested as before.

To check on real hardware: a 1 MB / 16 MB card's behaviour for the page bits it does not decode (the probe assumes
aliasing or no memory, both handled) and whether a write to a missing page can disturb another one (none known).

### How the size reaches the game

The handoff block's byte 15 (src/boot/launch.inc `HO_RDTOP`, until now always 0): `rd_top` is a byte of the
launcher's image, set by the probe before the image is copied to the RAM disk, so every later launch (the game
restored from its RAM-disk image, PRES from the floppy) has it; the launcher writes it into HO_MAIN + 15 (0x02AF)
after copying the block. The game reads 0x02AF directly (it stays valid during play like the rest of HO_MAIN; no new
resident byte). 0 there (the harness, which does not boot) = the 512 KB layout, i.e. today's behaviour. The harness
will poke 0x02AF to select a tier (tests/m4_game.py setup, from `POP800_RD_SIZE`, in the cache's PR). Verified: the
launched game finds 15 with the 1 MB INI (m5_boot).

The tier decision belongs in the level-start overlay (W2, once per game start: `rd_top >= 15` = the caches on; a
16 MB card = never evict); the per-tick code only sees the cache's own variables.

### How the tests select the size

`POP800_RD_SIZE=512K|1M|16M|256K|64K` (emu/mz800emu-pop.sh, built in this PR): the launcher writes a copy of the INI
with that size and its own RAM-disk file (`rd-mz800-<size>.dat` in the current directory) to build/emu/ and starts the
emulator with it; unset = the INI as it is (1 MB). tools/testrun.py includes the variable in its cache key. Proposed CI
use: section 4.

### pico_rd (PLAN item 35a, later)

pico_rd has a 24-bit position and wraps at its size; its "page" is the position's byte 2, so the tiers' page
arithmetic is the same and `rd_top` = size / 64 KB - 1 (from the same marker probe on base+2, or the device's size if
the firmware exposes it). The cache code goes through far_seek's page/address interface (and the per-row patched ports
of 35a), so nothing tier-specific is needed for pico_rd. Rule for all new code: the page is a full byte (never a page
mask, never 0xFF as a flag: dir_tab's 0xFF = main RAM is only used by the M3 test programs and must stay out of the
cache's directory).

## 2. The fetch today (measured)

char_fetch (src/m4/sprite.asm, called from pp_put for every object slot) keeps a one-entry cache per slot (SD_LKEY /
SD_LKEY2: chtab, frame, mirror, shift = x & 7); on a miss spr_fetch (src/m1/gfx.asm) reads the frame plane by plane,
row by row (INIR of w bytes into ROWTMP) and calls the generated shift routine (src/m1/kernel_gen.inc shr_w*_m*_s*),
which shifts through the shift tables and writes the interleaved cell buffer (row stride (w+1)*4: 4 planes a byte
column, one column more than the image). **The mirror is done at the fetch**, in the same routine (the m1 variants read
the row backwards and bit-reverse each byte through the 0x8000 table); the draw (spr_draw) only masks (mask = OR of the
4 planes) and needs nothing else.

Measured with tools/fetchstat.py (tools/fetchmodel/run_all.sh runs it on every script; working_set.py, cost_model.py,
session.py and key_space.py there compute the tables below from its output; tracepoints at char_fetch, cfdo, cf_ch, each row's sfrow / sf_de / sf_stride, the
return to pp_put, tick_done; CPU cycles):

| Stretch | fetch | setup (key, dir_entry, patching, seek) | RAM-disk reads (INIR) | shift + mirror | row / plane loop | hits |
|---|---:|---:|---:|---:|---:|---:|
| walk_level1 30-60 (30 fetches) | 0.899 | 0.026 | 0.153 | 0.610 | 0.110 | 0 |
| fight1 60-160 (201 fetches, 81 hits) | 1.547 | 0.050 | 0.287 | 1.029 | 0.178 | 0.003 |
| traps_b1 0-300 (242 fetches) | 0.730 | 0.020 | 0.134 | 0.476 | 0.098 | 0.001 |

Per byte of image (w x h x 4 planes): the read is 25-26 T (INIR 21 + the row's setup), the shift 77-81 T unmirrored
and 96-103 T mirrored (so **the mirror costs ~20 T a byte**, ~0.12 frames a tick walking right), the loop 14-19 T.
An average fetch is 407-455 image bytes (a 553-603-byte cell buffer) and ~63 K T. The RAM-disk read is a sixth of the
fetch; the shift is two thirds.

Fetches a tick: 1.0 walking, 2.0 in fight1 60-160 (kid 95, kid's sword 39, guard 38, guard's sword 26, splash 3 of
201), 0.8 in the traps.

### The working set (all 71 scripts of tests/m4-m7_scripts, 19,858 ticks, 19,740 fetches)

| | keys (chtab, frame, mirror, shift) | cell buffers |
|---|---:|---:|
| one script, first pass: walk_level1 (287 ticks) | 250 of 284 fetches distinct (12 % repeat) | 147 KB |
| fight1 (346 ticks) / fight_skill5 / level2_fight | 375 of 503 (25 %) / 303 of 902 (66 %) / 400 of 747 (46 %) | 219 / 166 / 231 KB |
| traps_b1 (1,500 ticks) | 603 of 1,334 (55 %) | 386 KB |
| all scripts together | 2,553 keys (kid 1,822, sword 331, guards 400) | 1,515 KB |
| the whole key space (every image x 2 mirrors x 8 shifts, + a 4-byte header) | 7,184 keys | 4,382 KB (kid 2,168) |

The most used keys first: 128 KB of entries cover 40 % of all fetches, 256 KB 59 %, 512 KB 79 %, 1 MB 95 %. The kid
rarely shows the same frame at the same shift twice in a short stretch (a walk cycles frames while x moves 1-4 pixels
a tick): **a first pass gains little, a long session a lot**. That decides the fill and eviction policy (section 3).

## 3. The frame cache

### Format of an entry

Exactly the cell buffer char_fetch leaves (the kernel's format: shifted, mirrored, the extra column, ow * 4 * h bytes),
behind a 4-byte header: the directory slot it belongs to (2 bytes, for eviction) and ow, h. A hit is one seek and one
read stream: the header's ow / h into the descriptor (SD_OW, SD_H; SD_XB from x as today), then INIR of ow*4*h bytes
straight into SD_BUF. Pre-shift and pre-mirror are the same entry: one key per (set, frame, mirror, shift). The draw is
unchanged and the bytes are the ones the shift routine writes (it writes every byte of the buffer, the empty extra
column included), so **the pixels are identical by construction**. Largest entry 1,152 bytes (a 4-byte header + the
1,148-byte kid image of the shadow); no entry crosses a page boundary (the address does not carry into the page).

(Not chosen: storing only the non-empty cells of each row. The buffer must be zero elsewhere, and clearing costs the
same 21 T a byte as reading; it would need a draw that knows the row extents.)

### Where it lives, the directory, the lookup

- **Directory**: page 8 from 0x0000, 4 bytes a key (page, address hi, address lo, 0), indexed directly:
  `(set_base + frame) * 64 + mirror * 32 + shift * 4`. Sets: kid 0 (220 ids), sword 220 (35), the six guard sets
  255 + 36 * set (set = the level start's guard set index 0-5, game.asm guard_type_tbl order, kept in a resident byte
  by the level-start overlay; the shadow on the guard slot uses the kid's images through chtab 2 = the kid set). 471
  ids x 64 = 30,144 bytes. Page 0 = empty (page 0 never holds an entry). The guard set is part of the key, so a level
  change needs no flush.
- **Data**: 1 MB = page 8 0x7800-0xFFFF and pages 9-15 (~490 KB) as one ring; 16 MB = pages 9-75 (4.3 MB, the whole key
  space: never full) or, with the room cache (section 5), whatever pages it leaves.
- **Lookup** per char_fetch miss of the slot's one-entry cache (the existing SD_LKEY test stays in front): index
  arithmetic ~80 T, seek page 8 ~40 T, 3 INs ~50 T, test, seek the entry ~40 T, the header 4 INs ~50 T, the descriptor
  ~60 T: **~350 T, then 21.1 T a byte** (INIR in 256-byte chunks). The existing dir_entry call (~300 T) is not needed
  on a hit (ow and h come from the header).
- **Fill on first use**: today's fetch, then allocate at the ring's write pointer, invalidate the old entries the new one
  overwrites (each: read its header's slot, write 0 to that slot's page byte: ~250 T; ~1-2 a fill), OTIR the header and
  the buffer (21.1 T a byte), write the directory slot (~150 T): **today's fetch + ~800 T + 21.1 T a byte** (+0.16
  frames for an average entry, +20 % on that fetch).
- **Eviction**: 16 MB none (the key space fits). 1 MB a FIFO ring (the oldest entries are overwritten; a page's unused
  tail gets a "skip to the next page" header). Simulated over the 71 scripts as one session
  (tools/fetchmodel/session.py), fetch frames a tick, today 0.866:

| cache | FIFO | flush when full | stop when full |
|---|---:|---:|---:|
| unlimited (16 MB) | 0.301 (hits 87 %) | | |
| 960 KB | 0.344 (82 %) | 0.388 | 0.367 |
| 448 KB (1 MB card, frames only) | 0.447 (71 %) | 0.525 | 0.582 |
| 256 KB (1 MB card shared with 4 room pages) | 0.549 (60 %) | 0.625 | 0.653 |
| 128 KB | 0.691 (45 %) | 0.782 | 0.730 |

  FIFO wins at every size; filling only on a key's second use (a "seen" mark in the directory slot) was simulated too:
  it saves the write for single-use keys but delays every reuse, and is within +-0.03 of first-use filling (better only
  at 128-256 KB). LRU proper would need a list update on every hit and variable-size free space: not worth it over FIFO.
- **Persistence**: the ring pointers live in page 8's header (not in main RAM), so the cache survives the PRES swaps
  (the game's image is restored from the RAM disk, PRES never touches pages 8+); the directory is cleared once, by the
  launcher before it starts the first game (30 KB, ~0.2 s), not at every level start. Across restarts and levels the
  entries stay valid (the packs never change during a run).

### Today's pack addressing (docs/memory.md "RAM disk")

The kid pack is pages 2-3 (106.3 KB, far_seek_entry carries into page 3), its directory page 5 0xE700; the sword page 1
0xD000 (directory 0xEE00); the six guard sets in pages 6, 7 and 0 with their directories at page 5 0x3400 (6 x 0x120,
dir_tab's CH_GUARD entry points at the level's); dir_entry copies an 8-byte entry per lookup. Pages 8+ are untouched
by everything today (the boot, the launcher, PRES, the game), so the cache needs no move.

### Resident bytes

The hit and the fill both run in the tick (first uses happen while playing: 0.7-0.9 fills a tick on a first walk), so
both are resident: lookup + hit ~110 bytes, fill + ring + invalidation ~190 bytes, ~300 bytes of main code (768 free;
block 2 220, low 30); variables (the ring pointers) in page 8, the guard set index and the "on" flag as immediates
patched by the level-start overlay. The set-up (the tier decision, the directory clear) goes into W2 / the launcher.
Conflict: PR #8's beam-wait scheduler (parked for its ~478 bytes) and the cache do not both fit the 768 bytes; the
cache gains ~8x more.

### Interactions

- **The shadow's XOR copy** (fx.asm spr_xor, PP_XDV): applied at the draw to the fetched buffer: unchanged; the shadow's
  images are the kid's (chtab 2) and share his entries.
- **The mirror image** (level 4, slot 6, SPRBUF_B): a mirrored kid frame like any other: shares the kid's entries.
- **The upside-down screen**: done at the copy (blit_flip, the chunk tops patched by set_flip): the buffers are not
  flipped: unchanged.
- **Palettes**: the guard colours are baked per set (guard / guard_palace packs); the flash is PAL0: nothing at the
  fetch.
- **The sword and the splash**: own chtabs (sword set; the splash's images are keyed by their chtab like the rest).
- **Clipping**: whole frames are fetched, clipping is at the draw: unchanged. Slots 5 / 6 taking SPRBUF_B
  (PP_BBUSY) are unchanged.

## 4. Expected gains, costs, verification

Cost model: a hit 800 T + 21.1 T a byte of the entry, a fill today's fetch + 800 T + 21.1 T a byte
(tools/fetchmodel/cost_model.py); measured per-fetch costs and sizes as input. Fetch frames a tick:

| Stretch | today | warm (every key cached) | first pass (empty cache at the script's start) |
|---|---:|---:|---:|
| walk_level1 30-60 | 0.900 | 0.175 (-0.72) | 0.756 (-0.14) |
| walk_level1 190-260 | 0.909 | 0.186 (-0.72) | 1.025 (+0.12) |
| walk_level1 whole (287 ticks) | 0.936 | 0.186 | 1.017 (+0.08) |
| fight1 60-160 | 1.547 | 0.331 (-1.22) | 1.326 (-0.22) |
| traps_b1 0-300 | 0.730 | 0.154 (-0.58) | 0.747 (+0.02) |
| one session of all 71 scripts, 16 MB / 1 MB (448 KB) / 1 MB (256 KB) | 0.866 | 0.301 / 0.447 / 0.549 | |

Whole tick, warm: walk 5.72 -> ~5.0 (-13 %), fight 7.73 -> ~6.5 (-16 %), traps 5.63 -> ~5.05. A first pass through a
new stretch is up to ~0.1-0.25 frames a tick slower (42 of the 71 scripts run from an empty cache are slower over their
whole length, the worst fight_bump 1.21 -> 1.46): the fill's write. Over a session the cache wins (the FIFO table
above); a 16 MB card plays every revisited stretch warm.

RAM disk: 1 MB card pages 8-15 (directory 30 KB + ~480 KB ring); 16 MB pages 8-75 for frames. Resident ~300 bytes of
main code. Floppy: nothing.

**Pixel identity across sizes**: the cache only replaces how the cell buffer is filled, so every pixel test that passes
on both sizes proves it. CI: the full regression gets a RAM-disk dimension (`POP800_RD_SIZE` set per job: 512K = the
reference without caches, 1M = the cache with eviction, 16M = no eviction), i.e. the 11 parts x 2 (x 3 on demand), or a
second workflow run with the variable; the PR tier stays one size (1M once the cache exists: the common case, with
evictions exercised by the long traps scripts only if the ring is small; a test build with a 64 KB ring would exercise
eviction in every script). tests/m4_game.py's every-tick VRAM hash comparison against the Python reference is the
check; perfcheck gets warm and cold stretches (the cold one: a fresh RAM disk; warm: the stretch run twice).

**Today's game on other sizes, verified in this PR**: the full regression on the runners with the INI at 512K
(regress/rd512) and at 16M (regress/rd16m) (section 7).

## 5. The visited-room cache (second step)

- **Slots**: the shadow room (page 1 0x0000, 32,000 bytes: plane p at p*8000 + y*40 + x) becomes a slot chosen per room:
  two slots a page (0x0000, 0x8000), the shadow's page an immediate patched at a room draw (gfx.asm restore_shadow and
  shadow_write are the two SHADOW_PAGE sites; the base 0x8000 ORs into the row addresses). The renderer draws straight
  into the room's slot, so a first visit costs nothing extra.
- **A revisit**: no piece laying (~55 frames of a room change) and no shadow write (~15): the VRAM copy from the slot
  (32,000 bytes, ~9.5 frames at 21 T a byte) plus the op lists. Rebuilding the op lists is ~17 frames (room change
  ~45 frames); keeping them too (back/mid/fore lists and tags, ~2.9 KB per room, in a separate area: 32,000 + 2,952 does
  not fit a half page) makes it ~15-20 frames instead of ~106.
- **Invalidation**: each slot keeps the tile snapshot of its room as view.asm's tile-change snapshot does for the room
  on screen (53 tile bytes + modifiers: the room and its neighbours' edge tiles, the buttons' pressed state). At a
  revisit the current blueprint is compared with it and every changed tile is redrawn with tile_redraw (~1 frame a tile;
  gates that moved, floors that fell, buttons, potions taken) before the copy; no hook in the off-screen tile code is
  needed. The torch flames and the falling floors are drawn per tick over the background as today.
- **Sizes**: levels 1-14 have 316 rooms (24 each, level 10 21, level 14 7): 158 pages for all of them, 15 more for the
  op lists. 16 MB: 8 + 158 + 15 + the frame cache's observed ~24 pages (67 for the whole key space) = 205-248 of 256
  pages: everything fits, never evicting, across levels and restarts (a restart's blueprint reload is caught by the
  snapshot compare). 1 MB: a few room slots against frame-cache space: 4 pages = 8 rooms (LRU per level), the frames
  256 KB (0.549 instead of 0.447 in the session table). Which split is the user's call (section 8).
- **Resident**: the slot choice and the snapshot compare at a room draw go into the room overlay (W1, 86 bytes free:
  likely a second room overlay); resident only the patched shadow page (~20-40 bytes).

## 6. Recommendation

1. **PR A: the frame cache for the kid, sword and guards** (1 MB and 16 MB at once: the eviction is the only difference;
   FIFO ring, 16 MB = a ring that never wraps): directory + lookup + fill in char_fetch, set-up in W2 / the launcher,
   `POP800_RD_SIZE` in m4_game.setup (poke 0x02AF), perfcheck warm/cold stretches, the full regression at 512K / 1M /
   16M. ~3-4 days. Gain warm walk -0.72, fight -1.2 frames a tick; cold first passes up to +0.1-0.25.
2. **PR B: CI**: the RAM-disk dimension in the full-regression workflow (or a second run), PR tier at 1M; optionally the
   emulator's region limit raised (MZPico/mz800emu PR from `wasm`) to inspect the cache above page 51 in tests. ~0.5-1
   day.
3. **PR C: the visited-room cache** (16 MB first: no eviction; then 1 MB's split): ~4-6 days. Revisit ~106 -> ~15-20
   frames.
4. Independent of the tiers (every size, also the fill path): a faster shift routine (the shift is 77-103 T a byte;
   registers instead of IY-indexed stores, no ROWTMP pass for shift 0) could gain ~0.15-0.25 frames a tick walking on
   512 KB; worth a measurement after PR A since it also lowers the cold penalty.
5. Not recommended as separate steps: a pre-mirrored pack alone (-0.12 walking right, superseded by the cache's
   entries) and pre-generating entries at level start (the whole kid set is ~2.1 MB: ~60 s of shifting).

## 7. Results of the regression runs on other sizes

(filled in below when the runner jobs finish)

## 8. Open questions for the user

1. The 1 MB split between frames and rooms: frames only (448 KB, the frame cache's best), or 256 KB frames + 8 room
   slots? (the session numbers: 0.447 vs 0.549 frames a tick of fetch; a revisit ~15-20 frames instead of ~106).
2. The cold penalty: a first pass is up to ~0.1-0.25 frames a tick slower than today (fight_bump the worst). Acceptable,
   or fill only when the tick has time left (a fill skipped when the tick is already late; it changes only speed)?
3. Resident space: the cache (~300 bytes) and the parked beam wait (PR #8, ~478) do not both fit the 768 free bytes.
   Cache first, beam wait after a reclaim?
4. Pre-generating during PRES's title (it waits for a key; the kid's most used ~128-256 KB of entries in ~10-20 s) to
   start warm: worth the complexity?
5. The emulator: raise MCP_REGIONS_MAX (or add a bank-addressed RAM-disk read/write) and consider `mr1r18_type = STD`
   for the tests (no shared file, no 16 MB file writes)?
