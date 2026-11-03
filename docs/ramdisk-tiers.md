# RAM-disk tiers: design and measurements (2026-11-03)

Status: **step 1 built** (section 11: the frame store, the kid and sword keys; PR perf/frame-store); the rest is the design. Sections 7-8 (prefetching; prebuilt layouts and
the hybrid) answer the user's follow-up questions; the recommendation (section 9) rests on them. The enabling changes
in the same PR change no behaviour: the boot's probe now counts the RAM disk's pages and the launcher hands the size
to the program it starts (the frame store reads it: section 11), the emulator launcher takes a size (`POP800_RD_SIZE`),
`tests/m5_boot.py` tests the probe with 512 KB, 1 MB and 16 MB, `tools/fetchstat.py` measures the sprite fetch and
tools/fetchmodel/ holds the models and measurements behind the tables (run_all.sh / idle_all.sh feed them).

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
  writes pages 0-7 only, so nothing breaks; a test that inspects the caches above page 51 needs the limit raised.
  Done: MZPico/mz800emu#2 lists every region (up to 1024; 332 with 16 MB, all 256 pages), and `tests/m5_boot.py`
  checks all 256 pages.
- `mr1r18_type = SRAM` (the INI's until PR #18) saves the whole RAM disk to its file on every exit (16 MB with the 16M
  size) and is why instances started in one directory share and corrupt one file. The INI now has `STANDARD` (the
  keyword; no file, filled with 0xFF at every start), which removes both.
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

### The read speed (src/boot/rdspeed.asm rd_speed, PLAN item 50)

Why: a RAM disk may hold the CPU's WAIT on its I/O cycles, and the game reads it byte by byte through the data port.
Chip-based RAM disks (the original MZ-1R18 and similar boards) have no wait states: 21.0 clocks a byte for INIR (+0).
The MZPico (Deluxe: a file-backed RAM disk behind a 128-byte SD window) always asserts WAIT on its RAM-disk I/O:
at least +1 on every access, the address and page OUTs too, so 22 or more, and possibly much more on some accesses
(a window miss). The boot measures what the machine does and shows it; it does not name devices or assume a minimum.

**Method.** Right after the probe, under DI. The clock is the 8253's counter 0: CLK0 = 17.734475 MHz / 16 = 1.108 MHz
(mz800emu `GDGCLK_CTC0_DIVIDER 16`), the CPU = the same crystal / 5, so one count is exactly 3.2 CPU clock periods of
real time; a wait state stretches the CPU's I/O cycle but not the counter (the CPU's own instructions are never
counted). Counter 0 in mode 2 from 65536 (59 ms a turn; a 16-bit difference of two latched values is right across a
turn), GATE0 = 1 through 0xE008 bit 0 (the ROM's I/O area at 0xE000: `OUT (E3h)`, the write, `OUT (E1h)`), its audio
muted meanwhile (8255 PC0 = 0, put back after), GATE0 = 0 again after (counter 1, which the game uses, is not touched).
A timing = latch, read, call the timed routine, latch, read; the fixed part around the routine is measured (16 runs
with an empty routine: 30 counts = 96 clocks each in mz800emu, exactly the instructions' sum) and the routine's own
nominal cost besides the bytes (42 clocks) is subtracted, so **clocks/byte = 21 + (the measured clocks - the nominal
clocks) / n**: no wait states = 21.0, and each wait clock on a data IN or on the address OUT adds 1 / n. The unit is
"clocks/byte": CPU clock periods of elapsed time, waits included, not instruction T-states. The excess over 21 is
shown as "+x.x WAIT".

What is timed, in each area of the RAM disk (page 0 from 0x0000; the last 8 KB of page 7, of the middle page
rd_top / 2 + 1 and of the last page; 3 areas on 512 KB, 4 on more), every routine = the address OUT on EBh then INIR
(the game's way: set the address, read a row):

- 32 chunks of 128 bytes, each at an address no other chunk touched: 16 aligned to 128 (base + k * 512), 16 misaligned
  by 64 (base + k * 512 + 320). A RAM disk with a 128-byte window misses once in an aligned chunk and twice in a
  misaligned one. Shown: MIN and MAX chunk, ALIGN and MISAL (the averages), AVG (all 32, in the last line as CHUNK).
- GAME: 32 runs of the game's pattern, the address OUT and an INIR of 32 bytes, at scattered addresses all over the
  page (0x0123 + k * 0x0753); the average. This is what the game's speed depends on.

Precision: a count is 3.2 clocks, so one 128-byte chunk is good to +-0.03 clocks/byte, one 32-byte run to +-0.1,
the averages of 16-32 to better than +-0.02; the calibration's 16 runs fix the fixed part to +-0.2 clocks. Reads only
(into TRKBUF): nothing in the RAM disk or main RAM changes (m5_boot compares both with the harness setup). Time: the
loader takes 719 frames instead of 708 (+0.22 s with the table's drawing; 5 KB read an area).

**Screen** (the loading screen; "LOADING..." and the bar moved up 12 lines to make room, the floppy errors to line 84):

    RAM DISK 1024K, CLOCKS/BYTE
     PAGE   MIN   MAX ALIGN MISAL  GAME
     P0    21.0  21.0  21.0  21.0  21.0
     P7    21.0  21.0  21.0  21.0  21.0
     P8    21.0  21.0  21.0  21.0  21.0
     P15   21.0  21.0  21.0  21.0  21.0
     GAME 21.0 +0.0 WAIT  CHUNK 21.0 +0.0

How to read it: GAME (last line: the mean over the areas) is the number to compare between machines; +x.x WAIT is the
wait clocks a byte. MAX far above MIN, or MISAL above ALIGN, means non-uniform waits (window misses). The loader's font
got the glyphs it lacked (3 4 6 7 9 J Q V X + /).

**The stop.** The GAME mean above `RD_SPEED_MAX` = 36.0 clocks/byte (x 10 = 360, the one constant in rdspeed.asm;
user, 2026-11-03) stops the boot with "RAM DISK TOO SLOW: 37.5 CLOCKS/BYTE" / "GAME PATTERN, MAX 36.0, WORST P7 37.5"
(the worst area's GAME): no launch, nothing more loaded (rs_stop, the motor off). Why 36.0: where RAM-disk waits slow
the kid's walk by about 10 %. Measured with the frame store (#19, tools/rdreads.py and mz800emu's mr1r18_wait): the game
makes ~2,700 RAM-disk port accesses a tick walking (~2,400 data reads, the seeks, the page selects, the writes), and 1 T
of wait on each costs +0.035 frames a tick, so 10 % of a ~5.2-frame tick is ~15 waits; the GAME pattern reads
21 + w + w/32 clocks/byte, 15 waits -> 36.5. (A first estimate, 50.0, counted only the kid's frame bytes, ~500 a tick.)
A room change costs +1.28 frames a wait (~19 frames at the limit). A uniform +1 (22.0) passes with a wide margin. Below `RD_SPEED_MIN` = 15.0 (faster than an INIR can be: the timer is wrong, e.g. GATE0 or CLK0 not as
expected, or a counter that does not count) it stops too: "RAM DISK TIMER FAULT: ..." with the fastest area. Both
limits are words in the boot's image (rd_max, rd_min).

**The handoff.** rd_spd = the GAME mean x 5 (rounded; 105 = 21.0, 0.2 a step, 255 = 51.0 or more) is a byte of the
launcher's image like rd_top; the launcher writes it to HO_RDSPD_MAIN = 0x029F (the byte before HO_MAIN; the 16-byte
block has no spare byte) at every start. 0 = the harness (not measured). Nothing reads it yet.

**Tested** (m5_boot): 512 KB, 1 MB and 16 MB give 21.0 everywhere (every value 21.0 +-0.1; mz800emu models no wait
states), the boot goes on and the game gets 105; with rd_max patched to 15.0 in the loaded image the boot halts at
rs_stop with the message and never launches (build/m5_rdslow.png), the same with rd_min patched to 25.0 (the timer
fault, build/m5_rdfault.png). With an emulator that has `mr1r18_wait` (MZPico/mz800emu#2; `POP800_RD_WAIT`, PR #18)
it also boots with +1 T a RAM-disk port access (22.0 in every column, "+1.0 WAIT", the boot goes on;
build/m5_rdwait1.png), +14 (GAME 35.4 = 21 + 14 + 14/32 for the address OUT: just under the limit, the boot goes on;
build/m5_rdwait14.png) and +16 (GAME 37.5, the stop without patching; build/m5_rdwait16.png); with an older emulator
these are reported as not tested. (Found on the way: mz800emu#2's first builds read mr1r18_wait as hexadecimal, so
10 and up gave 16+ waits; fixed in 94b7967, the pin since #18.)

To check on real hardware: the values on a chip-based card (21.0 expected) and on an MZPico Deluxe (22 or more, the
spread of MIN / MAX), and that GATE0 through 0xE008 works in the MZ-800 mode on the real machine as in mz800emu.

### How the tests select the size

`POP800_RD_SIZE=512K|1M|16M|256K|64K` (emu/mz800emu-pop.sh, built in this PR): the launcher writes a copy of the INI
with that size to build/emu/ and starts the emulator with it (the RAM disk is in memory, no file); unset = the INI as it
is (1 MB). `POP800_RD_WAIT=<T>` likewise sets mz800emu's `mr1r18_wait` (MZPico/mz800emu#2): that many wait states on
every RAM-disk port access, default 0; the MZPico asserts WAIT for at least 1 T, so INIR takes 22 T a byte instead of
21. tools/testrun.py includes both variables in its cache key. Proposed CI use: section 4.

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

## 3. The frame cache: option A, filled at run time

(Sections 7 and 8 compare it with prefetching and with prebuilt or pre-generated fixed layouts; the recommendation in
section 9 is the fixed-layout hybrid of section 8, which reuses this section's entry format and lookup.)

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
- **Data**: 1 MB = page 8 0x7800-0xFFFF and pages 9-15 (~490 KB) as one ring; 16 MB = pages 9-80 (72 pages, 4,608 KiB: the whole key
  space's 4,382 KiB with the 4-byte headers, plus slack for the entries that do not cross a page boundary: never full) or, with the room cache (section 5), whatever pages it leaves.
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

RAM disk: 1 MB card pages 8-15 (directory 30 KB + ~480 KB ring); 16 MB pages 8-80 for frames (the directory on page 8, the data on pages 9-80). Resident ~300 bytes of
main code. Floppy: nothing.

**Pixel identity across sizes**: the cache only replaces how the cell buffer is filled, so every pixel test that passes
on both sizes proves it. CI: the full regression gets a RAM-disk dimension (`POP800_RD_SIZE` set per job: 512K = the
reference without caches, 1M = the cache with eviction, 16M = no eviction), i.e. the 11 parts x 2 (x 3 on demand), or a
second workflow run with the variable; the PR tier stays one size (1M once the cache exists: the common case, with
evictions exercised by the long traps scripts only if the ring is small; a test build with a 64 KB ring would exercise
eviction in every script). tests/m4_game.py's every-tick VRAM hash comparison against the Python reference is the
check; perfcheck gets warm and cold stretches (the cold one: a fresh RAM disk; warm: the stretch run twice).

**Today's game on other sizes, verified in this PR**: the full regression on the runners with the INI at 512K
(regress/rd512) and at 16M (regress/rd16m) (section 6).

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
  256 KB (0.549 instead of 0.447 in the session table). Which split is the user's call (section 10).
- **Resident**: the slot choice and the snapshot compare at a room draw go into the room overlay (W1, 86 bytes free:
  likely a second room overlay); resident only the patched shadow page (~20-40 bytes).

## 6. Results of the regression runs on other sizes

The full regression on the runners (all 11 parts, every test on its full set) with the INI's `mr1r18_size` changed on a
probe branch, this PR's first commit: **512K: passed** (regress/rd512, run 41628768083) and **16M: passed**
(regress/rd16m, run 41628772168); the PR checks passed too. Today's game (and the new probe) therefore behaves the same
with 512 KB, 1 MB and 16 MB, which the tiers' verification (section 4) builds on.

## 7. Prefetching: can the cache be (almost) always warm?

### The working set

| | keys | bytes as stored entries |
|---|---:|---:|
| the kid, every frame x 2 mirrors x 8 shifts | 3,504 | 2,154 KB |
| the sword | 544 | 59 KB |
| one guard set (guard, guard_palace, fat, vizier / skel, shadow) | 544 / 448, 512 | 368-388 KB / 314, 311 KB |
| the whole game | 7,184 | 4,354 KB |
| observed in the scripts, per level (kid / that level's guard set): level 1 | 1,256 / - | 793 KB / - |
| level 2 / 4 (the plain guard) | 402, 928 / 142, 171 | 273, 590 / 122, 138 KB |
| level 13 (vizier) / 12 (shadow) | 244, 247 / 90, 32 | 154, 166 / 68, 26 KB |
| observed over all 71 scripts | 2,553 | 1,515 KB |

(Per level the observed sets are what the scripts happen to cover: level 1 has 30 scripts, other levels 1-6.) 1 MB
(~480 KB free above the base layout and the 30 KB directory): about a fifth of the kid's full set, or the most used
~400 KB of kid + sword keys and ~80 KB of the level's guard set. 16 MB: everything (4.35 MB in pages 9-80, section 3) with room for
the room cache.

### Fill times at today's shift speed

Generating a key with today's code = a fetch (measured: ~1,800 T + per image byte 25.5 read, 79 / 99 shift unmirrored /
mirrored, 17 loop) + writing it (21.1 T a byte): tools/fetchmodel/prebuild.py.

| | today's fetch code | a dedicated generator (estimate) |
|---|---:|---:|
| the kid's full set (2,154 KB) | 78.4 s | ~31 s |
| one guard set (~388 KB) | 12-15 s | ~5.6 s |
| the sword | 2.3 s | ~0.9 s |
| everything (4,354 KB) | 163 s | ~61 s |
| the most used kid + sword 400 KB | 14.6 s | ~5.8 s |
| the most used 80 KB of a guard set | 3.0 s | ~1.2 s |

The dedicated generator (estimate, not built): one read of each image row, the 8 shifts made by shifting the row one
more bit each time (RL through the 4 planes, ~20 T a byte), the mirror by the bit-reverse table, each variant's row
written with OTIR to its entry (21 T a byte + a seek a row): ~50 T an output byte instead of ~125. Its output must be
byte-identical to the kernel's (checked as tools/fetchmodel/prebuild_check.py checks the Python generator).

### When the MZ has time without the player noticing

- **Do the pages survive?** Yes: pages 8 and up are written by nothing but the caches: not by the boot's stream
  (pages 0-7), the launcher (page 0 0xF000, page 5's handoff block, the game image in pages 3-4), PRES (its scratch is
  page 1 0x0000-0x7CFF and page 6 0x0000-0x287F) or a level change. A cache filled at boot lasts the whole session,
  across levels, restarts and cutscenes.
- **At boot**: the loader runs 14.2 s today (emulator, 708 frames; a real drive longer); the title waits for a key.
  Filling there adds its time to the first start (or runs while PRES shows the title: PRES owns main RAM then, so the
  filler would be PRES's own code; not designed).
- **At a level start**: today the level load is ~0.9 s (m5_boot: 44 frames from the game's start to level_ready on
  level 1); the "LEVEL n" text, the fade and the level 1 crouch music are timed in ticks, which keep running (filling
  there would delay them: visible). A per-level fill makes the level start longer by its time.
- **The idle part of ticks** (the 4-frame pacing floor halts when a tick took less than 4 frames), measured with
  tracepoints at tick_done and ml_go over all 71 scripts (tools/fetchmodel/idle.py): **0.05-2.3 frames idle a second
  of play** (walk_level1 1.50, traps_b1 0.87, random1 1.32, the level starts ~2.2, fights 0.10-0.22, death_text 0.19,
  time_expire 0.06): the game runs 5-8 frames a tick, so it almost never waits. At ~1.1 frames a key (today's code)
  that is about one key a second walking, none in fights: negligible.
- **Death and level-end waits** are tick-driven too (the death text, the end music in the hybrid sound mode): the
  ticks are drawn as always, so no idle time; working there would change how many ticks a wait takes in real time,
  i.e. behaviour: no.

So prefetching means a fixed amount of work at boot and / or level start, not background filling.

### Misses that remain, the cold pass

With a store filled ahead (keys chosen by use, cross-validated: chosen from half of the scripts, measured on the other
half; tools/fetchmodel/static_set.py), fetch frames a tick, today 0.866 on these runs:

| store | fetch | stored keys hit |
|---|---:|---:|
| 16 MB: every key (all keys these runs use hit) | 0.186 | 100 % |
| 1 MB: kid + sword 400 KB + the level's guard set 80 KB | 0.397 | 74 % |
| kid + sword 448 KB + guard set 32 KB | 0.392 | 74 % |
| kid + sword 256 KB + guard set 64 KB | 0.474 | 64 % |
| kid + sword 400 KB only | 0.448 | 68 % |

Held-out scripts with the 1 MB store (keys chosen from the other 70): walk_level1 0.936 -> 0.485, fight1 1.222 -> 0.639,
traps_b1 0.906 -> 0.361. A key not in the store costs exactly today's fetch: **no cold penalty** (option A's first
pass is up to +0.1-0.25 slower than today).

### Resident bytes

A background filler (in the halt loop, resumable per row so the next tick is never late) would need its generator
resident (~250-350 bytes: the overlays' windows are busy during play) for ~1 key a second: not worth it. Boot and
level-start filling run from overlays (W2 / the launcher: no resident cost).

## 8. Prebuilt or pre-generated fixed layouts against the run-time cache

The per-tick saving is the same in every variant: a hit = the lookup + reading the entry (~800 T + 21.1 T a byte)
instead of ~63 K T. What differs is how the entries get into the RAM disk and whether the per-tick code also fills.

**The fixed layout**: the entries of the chosen keys at build-time-known (B, D) or boot-computed (C) places, a key table
in page 8 (4 bytes a key, 471 ids x 16 = 30 KB, 0 = not stored: the normal fetch), no headers needed beyond ow / h, no
eviction, no fill: the per-tick code is section 3's lookup alone, **~110 bytes of main code** (768 free; it does not fit
the low block's 30 or block 2's 220 together with its callers' changes). With all 16 variants of every image stored
(16 MB) the table could even be per image (base address; variant v at base + v * size) but the per-key table costs
the same lookup and serves both sizes.

| | A: run-time cache | B: prebuilt on the floppy | C: generated at boot / level start | D: MZPico RAM-disk image |
|---|---|---|---|---|
| how the data get there | the first use of a key | tools/build_assets.py -> disk -> the loader unpacks into pages 8+ | an overlay from the packs | the image file on the SD card, already there at power-up |
| per-tick code (resident) | lookup + fill + FIFO, ~300 B | lookup ~110 B | lookup ~110 B | lookup ~110 B |
| 1 MB: what is stored | any key, FIFO | the most used kid + sword 400 KB (+ guard sets?) | kid + sword 400 KB at boot, the level's guard 80 KB at level start | as B/C |
| 16 MB | everything as used | kid 2,154 KB does not fit the disk (below) | everything: 61-163 s: too long; the 1 MB core + A's fill for the rest | everything |
| disk | none | 400 KB raw -> **~88 KB PZ (22 %)**; the kid's full set 475 KB, everything 960 KB | none | none (the image is built locally from the user's data) |
| boot cost | none | read ~4.4 s (real drive ~20 KB/s) + PZ decode ~11.5 s (~100 T a byte) = **~16 s** | **~5.8 s** (dedicated generator) / 14.6 s (today's code) | none |
| level start | none | none (if guard sets are on the disk: 82-86 KB PZ each) | +1.2 s (dedicated) / +3.0 s (today's code) for 80 KB of the guard set | none |
| cold pass | first uses +0.1-0.25 a tick | none: an unstored key = today's fetch | none | none |
| session fetch (1 MB / 16 MB) | 0.447 / 0.301 | 0.397 / - | 0.397 / ~0.19-0.30 | 0.397 / 0.186 |
| pixel safety | the kernel's own buffer | a PC generator: must match the kernel bit for bit | the kernel's own routines (or a verified generator) | as B |

B's numbers come from tools/fetchmodel/prebuild.py, which generates every variant as the kernel does; its output equals
the kernel's buffer for all 852 distinct kid fetches of walk_level1 and traps_b1 (tools/fetchmodel/prebuild_check.py,
tracepoints after char_fetch: 0 differ), so B is pixel-safe given such a test in the build.

**The disk** (for B): today's disk (40 tracks x 2 sides, 1,280 blocks of 256 B) has 241 blocks (60 KB) free after
POP800.PR2: B's 88 KB does not fit. An 80-track FSMZ image (mzdisk `mzdsk-create --format-basic 80 --sides 2`: 2,560
blocks = 640 KB, the DSK file 696,576 bytes; a "720 KB" PC-style 9 x 512 format is not FSMZ) leaves ~1,520 blocks
(~380 KB): B's 88 KB fits, the kid's full set (475 KB PZ) does not. What it needs: tools/mkgamedisk.py the track count
(its `mzdsk-create ... 40` and the block budget), the loader's block -> track / side / sector arithmetic and seek range
(tracks 40-79; to check), tests mounting the bigger image (mz800emu reads DSK track tables of any length; to check), and
the FSMZ free map beyond block 1,280 (the MZ-800 Disk BASIC's own 80-track support: to check). Hardware: the MZ-800's
standard drive (MZ-1F19, 5.25" 2D) has 40 tracks: an 80-track image works on MZPico's FDC (its DSK track table takes
up to 204 track-sides) and on an 80-track drive, not on a stock drive, so it would be a second disk image, not the
only one.

**D on MZPico** (MZPico-firmware src/mz_devices/ramdisk.cpp): `[ramdisk]` has `image=` (a backing file on the SD card,
flat: byte page * 65,536 + address, the same as mz800emu's rd-mz800.dat) and `size=`; writes go back to the file, so
the contents persist across power cycles (even option A would stay warm). It is Deluxe-board only (pico_rd elsewhere,
same `image=`). Without an image it is RAM-backed, bounded by the Pico's RAM (an RP2040 has 264 KB: less than today's
512 KB layout); with an image every access goes through a 128-byte cached window of the file (each seek outside the
window is an SD read). Whether that keeps up with the game's access pattern (a seek a row in the shadow restore and the
fetch) is a hardware question that already applies to today's 512 KB game; to measure on a Deluxe board before relying
on D. The image would be written by a build tool from the user's own assets (like build/pop800.dsk).

### The hybrid (the user's candidate)

1. the kid's (and sword's) variants prebuilt by tools/build_assets.py in the fixed layout, on the disk, loaded at boot;
2. the level's guard set generated before the level by an overlay, into the fixed layout;
3. keys not stored: today's fetch.

Measured / estimated for it:

| | 1 MB | 16 MB |
|---|---|---|
| RAM disk | key table 30 KB + kid / sword 400 KB + one guard set's 80 KB (pages 8-15) | everything: 4.35 MB (directory page 8, data pages 9-80) |
| disk for (1) | 88 KB PZ (does not fit today's disk; fits 80 tracks) | the kid's full set 475 KB PZ: does not fit even 80 tracks |
| boot (1) | ~16 s from the disk (B) or ~5.8 s generated (C) | the full kid set: ~31 s generated, ~78 s with today's code |
| level start (2) | 80 KB of the guard set: +1.2 s / +3.0 s; the whole set +5.6 s / +12-15 s | every set once: as the 1 MB column, then never again |
| per-tick lookup | ~110 bytes main | the same |
| cold pass | none: the kid's stored keys are warm from the first tick, the guard's after the level start; the rest = today | none |
| gain (fetch frames a tick) | session 0.866 -> 0.397; walk 0.94 -> 0.49, fight 1.22 -> 0.64, traps 0.91 -> 0.36 | -> 0.186 when all stored |
| whole tick | walk ~5.72 -> ~5.3, fight ~7.73 -> ~7.2 (first pass = every pass) | walk -> ~5.0, fight -> ~6.5 |

Against option A on 1 MB: the hybrid is better over a session (0.397 against 0.447), has no cold penalty, ~190 fewer
resident bytes and no fill / eviction code; A adapts to keys the scripts never showed (on 16 MB A ends warmer than a
partial store). The kid's part as B (disk) costs a bigger disk and ~16 s of boot; as C (generated at boot from the
packs already in the RAM disk) ~6 s and no disk change, with the same layout and lookup. 16 MB: the full set takes
~31 s to generate: generate the 1 MB core at boot, and let the rest fill on first use (A's fill without eviction, +~190
bytes) or not at all.

## 9. Recommendation

1. **PR A: the fixed-layout store and its lookup** (char_fetch: the key table in page 8, ~110 bytes main), the tier
   decision from rd_top, `POP800_RD_SIZE` in tests/m4_game.setup (0x02AF), and the **kid + sword core generated at boot
   by an overlay from the packs** with today's shift routines (exact by construction; ~14.6 s for 400 KB: measure it on
   the MZ in this PR) and the key list chosen at build time from the scripts' use (tools/fetchmodel/static_set.py into
   build/assets). Gain on 1 MB: fetch -0.45 to -0.58 a tick from the first tick, no cold pass. ~3-4 days.
2. **PR B: a dedicated generator** (all 16 variants of an image from one read), verified byte for byte against the
   kernel: boot ~14.6 -> ~6 s; then the level's guard set at the level start (80 KB ~1.2 s; whole set ~5.6 s on 16 MB,
   once). ~2-3 days.
3. **PR C: CI**: the full regression with a RAM-disk dimension (512K reference, 1M, 16M; this PR's probe runs show both
   pass today), the PR tier at 1M. ~0.5-1 day.
4. **16 MB extras** (optional): the rest of the key space by fill on first use without eviction (A's fill, ~190 bytes),
   or generated once and kept on MZPico's file-backed RAM disk (D, persists). Then **PR D: the visited-room cache**
   (section 5, ~4-6 days; revisit ~106 -> ~15-20 frames).
5. Not recommended: B for the kid on the floppy (needs an 80-track second disk image, ~16 s of boot, and still not the
   full set); background filling in idle tick time (0.05-2.3 frames a second); the run-time cache alone on 1 MB (cold
   passes slower than today). A faster shift routine (the shift is 77-103 T a byte) still helps
   every size and the generator: measure after PR B.

## 10. Open questions for the user

1. Boot time: is ~6 s (dedicated generator; ~15 s with today's code in the first PR) added to the first start acceptable,
   or should it run while PRES shows the title (PRES's own code, more work)?
2. Level start: +1.2 s for 80 KB of the guard set (or +5.6 s for the whole set, once per set on 16 MB) acceptable?
3. The 1 MB split between the frame store and the room cache (8 room slots = 256 KB would halve the kid core:
   0.397 -> ~0.48 a tick of fetch)?
4. The key list from the test scripts' use (cross-validated 74 % hits): good enough, or record a few real play sessions
   (the GUI) to choose it?
5. MZPico: is the 512 KB+ `[ramdisk]` on a Deluxe board file-backed (RP2040 RAM), and is its speed known? A test on the
   board would tell whether D (and today's game) run at the emulator's speed there.
6. Resident space: the lookup (~110 bytes) fits next to the parked beam wait (PR #8, ~478) in the 768 free bytes; A's
   fill would not: keep the fill out (16 MB extras later)?
7. The emulator: raise MCP_REGIONS_MAX (or a bank-addressed RAM-disk command) and consider `mr1r18_type = STD` for the
   tests? Done (MZPico/mz800emu#2, PR #18: `mr1r18_type = STANDARD`).

## 11. As built: step 1, the frame store (2026-11-03, PLAN.md item 49)

**The user's decisions (2026-11-03)**: the hybrid with a fixed layout (section 8), no run-time fill (option A dropped);
building the kid's set at boot is acceptable, and +~1.2 s at a level start for the guard set (step 2, not built
here); the stored keys are chosen from the test scripts; **on 1 MB the RAM disk above the base layout goes to the
frame store only: no room cache on 1 MB** (the room cache is a later step, from 2 MB up); the game behaves and looks
the same on every size (512 KB: no store, today's fetch).

**The layout** (tools/fstore.py, at build time into build/assets; nothing generated is committed):

- The keys: assets/fstore_uses.txt (committed: numbers only) lists every kid and sword key (chtab, frame, mirror,
  shift) the 71 scripts fetched and how often (2,153 keys; `tools/fstore.py --uses build/meas/k` remakes it from
  tools/fetchmodel/run_all.sh's output). **Class 1** = the most used per byte up to 400 KB (headers included): 891 keys,
  409,512 bytes, 80.2 % of the scripts' kid and sword fetches; every card from 1 MB. **Class 2** = the other 1,262 keys
  (823,312 bytes) from rd_top 29 (2 MB and more; on 16 MB). The guards' keys are step 2.
- RAM-disk page 8: the key table (471 ids x 16 variants x 4 bytes = 0x75C0 bytes: id = the kid's frame 0-219, the
  sword's 220 + frame, 255-470 for the guard sets of step 2; slot = id * 64 + (mirror * 8 + shift) * 4 = the entry's
  page (0 = not stored), address hi, lo), the marker at 0x7700 (the build id: a CRC of the masks, the kid and sword
  packs and directories, the kernel's and the fill's sources; then the class), the entries from 0x7800 on and in
  pages 9+: ow, h, the byte count (2 bytes), then the cell buffer exactly as spr_fetch leaves it; an entry that would
  cross a page starts the next page. Class 1 ends at page 14 0xC2F4 (81.6 KB of 1 MB left: step 2's guard set), class
  2 at page 27 0x6130.
- The fill's input: the masks (255 ids x 2 classes, a 16-bit word each: bit v = variant v stored) and the build id,
  1,024 bytes (build/assets/fstore_masks.bin) at page 6 0xE400, written on every size by the boot's stream
  (tools/mkgamedisk.py) and by the harness (tests/m4_game.py setup). The fill allocates in mask order (class 1 by id
  and variant, then class 2); tools/fstore.py computes the same layout (build/assets/fstore_keys.txt,
  fstore_tab1.bin / fstore_tab2.bin = page 8 0x0000-0x77FF as the fill must leave it).

**The lookup** (src/m4/fslook.asm, main code, 95 bytes; char_fetch in the low block +3 bytes): on a miss of the slot's
one-entry cache char_fetch jumps through fs_on, which is `jp cf_fetch` (today's fetch) until the fill patches it to
fs_look. fs_look: the chtab (kid or sword; anything else: today's fetch), the slot address from the id and key2's low
nibble, one seek to page 8 and 3 INs; page 0: today's fetch; else a seek to the entry, INI x 2 into SD_OW / SD_H, the
count, INIR into the slot's buffer, then the byte column as on a cache hit. ~300 T + 21 T a byte instead of ~63 K T.
Resident total: **98 bytes** (main 768 -> 673 free, low block 30 -> 27, block 2 unchanged).

**The fill, at boot** (the user's decisions of 2026-11-03, second round: the fill runs in the loading, before the
title, with a progress bar; every boot from the floppy fills; 16 MB keeps classes 1 and 2; the faster generator is
step 2, the next PR). After the floppy load, on 1 MB and more (rd_top >= 15), the loader (src/boot/boot.asm) clears the
store's marker (page 8 0x7700: five zero bytes), writes "PREPARING SPRITES" in the place of "LOADING..." (msg_load's
position, read at run time), draws the bar empty again (BAR_ROW, BAR_COL: the loader's own layout) and starts the game
with the new action ACT_FILL (src/boot/launch.inc; the block carries the bar's first VRAM byte, its width 32 and its
colour, so the game knows nothing of the loader's layout). game_start (src/m4/gstart.asm gs_fill) keeps the loader's
screen, runs tables_init and fs_fill (src/m4/fstore.asm: the masks to SPRBUF_B, the marker compared with the build id
and the class; it differs, so page 8 0x0000-0x77FF is cleared, then for every stored key dir_entry and **spr_fetch,
today's routine**, into SPRBUF_A, the table slot and the entry written with OTIR, the bar advanced (ff_prog: 32 cells
over the keys, VRAM mapped only while a cell is drawn: the shift tables are behind it), the marker last) and hands
over to the title (ho_swap, ACT_TITLE). Every later game start in the session (after the title, PRES's swaps, game
over) runs fs_fill again from game_start: the marker matches, so it only patches fs_on. A store left in the RAM disk
by an earlier session, possibly overwritten by another program, is never trusted (tests/m5_boot.py boots with a
valid-looking marker planted and checks that the fill ran: the key table and the bar). The fill puts spr_fetch's
patched operands and dir_buf back, so main RAM is as after a start without the fill (tests/m7_launch.py compares a
round trip with a direct start). The level-start overlay grew 2,201 -> 2,746 bytes (W2: 1,350 free); the overlay area
in page 7 has 1.3 KB left (the cheat build ~0.9 KB); the launcher's image +~70 bytes.

The interface step 2 replaces: fs_fill checks the marker and calls `ff_pass` with HL = a key list (a mask table) per
class; ff_pass / ff_key make one key at a time with spr_fetch (~1,800 T + ~125 T an image byte, + the write). Step 2's
dedicated generator (all 16 variants of an image from one read of its rows, ~50 T an output byte) replaces ff_pass /
ff_key behind the same call; the layout (tools/fstore.py), the marker, the bar and the lookup stay. **Built: section 12** (the 1 MB fill 15.5 -> 7.0 s, 16 MB 45.0 -> 18.7 s).

**The boot timeline** (tests/m5_boot.py, emulator frames, 50 a second; the loader's time as before, the PRES and title
steps unchanged):

| | the loader (floppy) | the fill ("PREPARING SPRITES", incl. the game image's start ~1.3 s) | PRES starts | the title's step a |
|---|---:|---:|---:|---:|
| 512 KB | 712 = 14.2 s | - | 815 = 16.3 s | 1,035 = 20.7 s |
| 1 MB | 712 = 14.2 s | 851 = 17.0 s (the fill itself 774 = 15.5 s) | 1,666 = 33.3 s | 1,886 = 37.7 s |
| 16 MB | 713 = 14.3 s | 2,334 = 46.7 s (the fill itself 2,250 = 45.0 s) | 3,150 = 63.0 s | 3,370 = 67.4 s |

The game's start after the title's key is as on 512 KB (game start -> level_ready 45 frames). On a real drive the
loader takes longer; the fill does not depend on the drive. On MZPico with w wait states a port access the fill takes
w x 10.7 frames (1 MB) / w x 31.5 (16 MB) more (docs/perf.md "M8a part 9").

**With PR #20 (boot/rd-speed)**: #20 moves "LOADING..." and the bar 12 lines up and puts its measurement table below
them; the fill reuses msg_load's position and BAR_ROW at run time, so nothing collides in either order. A trial merge
of the two branches has one conflict, PLAN.md (both append an item); the code merges cleanly and the merged loader
builds (the launcher's image 2,428 of 3,072 bytes). Either order works; #20 first is the simpler one (its PLAN item
is earlier and #19's follows it).

**The harness**: tests/m4_game.py setup writes the masks, puts the size at 0x02AF (the emulator's own, from the
number of its RAM-disk regions: 512 KB = 7, 1 MB = 15, 16 MB = 255; not from the INI: the cheat tree build/cheat has no
emu/, so emu/mz800emu-pop.sh cannot cd to its directory there and the emulator runs with its built-in defaults, a 1 MB
RAM disk, whatever `POP800_RD_SIZE` says), clears the marker (every run fills anew: 0.6 s of host time on 1
MB, 1.6 s on 16 MB; no store left in a RAM-disk file is trusted) and runs to the fill's end (fs_done), so every test's
frame counts start after it (`fs_run=False`: the fill then runs inside game_start: m5_boot's harness run).
tests/m8_fstore.py (PR part a, full part sound): on 1 MB+ the key table and the marker equal tools/fstore.py's, every
entry equals tools/fetchmodel/prebuild.py's generator (byte-identical to the kernel: prebuild_check.py) with its
header, fs_on points at the lookup, a second start does not fill; on 512 KB fs_on is untouched.

**Results**: docs/perf.md "M8a part 9: the frame store" (perfcheck per size, the RAM-disk accesses per tick and the
cost of wait states on MZPico).

## 12. As built: step 2, the dedicated generator (2026-11-03, PLAN.md item 51)

**What it does** (src/m4/fsgen.asm, in the level-start overlay W2 with fs_fill): fs_fill keeps its marker check, the
table clear and the marker, and now makes both classes in **one pass over the ids** (`fg_run`: HL = class 1's mask
table, DE = class 2's or 0, BC = the number of ids, fg_id = the first id; class 1 allocates from page 8 FS_DATA, class 2
from class 1's end FS_E1P:FS_E1A, which tools/fstore.py now exports: the same addresses as filling class 1 first, then
class 2). Per id and mirror with any variant stored (in either class):

1. the image is read once (its directory entry: dir_entry, as before) into SPRBUF_A, directly at the **lowest stored
   shift**: at shift 0 a plain copy (mirrored: the columns from the right, each byte through the bit-reverse table),
   otherwise through the kernel's own lo / hi shift tables (the same lookups spr_fetch's routines do; mirrored, the
   carry runs from the right: hi | the carry, lo the next carry), the extra column written last;
2. each stored variant is written to its entry (ow, h, the count, then the buffer with OUTI, 64 at a time; the slot in
   the key table as before), the bar advanced per entry as before;
3. the next shift is the buffer shifted **one more bit**: per plane and row `sla (ix+p)`, then `rl (ix+p+4c)` up to the
   extra column (a row of a plane is a little-endian number of ow bytes; nothing reaches past the extra column up to
   shift 7), until no higher shift of this mirror is stored.

The row code (the four read kinds and the step) is made at run time for the image's width (`fg_mk`, a template per
kind, kept while the width is the same) into SPRBUF_B 0xBC80-0xBE4D; the generator's variables at 0xBC20; the masks at
0xB800 as before. Interrupts stay off; VRAM is mapped only for the bar's cells (the bit-reverse table is behind it).
The table clear uses the same OUTI block (480 x 64 zero bytes: 10.8 -> 7.1 frames). The layout, the marker, the bar
and the lookup are unchanged; tools/fstore.py's build id now also covers src/m4/fsgen.asm.

**For the guard sets** (the follow-up): fg_run fills any key list given as a mask table and a pointer; fg_dir maps an
id to its directory entry (today: the kid's and the sword's ids) and is the place for the guards' ids 255-470.

**Measured first** (a prototype of the generator assembled at 0xA000 and called on single images after the harness
start, 1 MB; build/proto, not committed): with all 16 variants of an image stored, **46 T an output byte** (images of
384-816 bytes: 45.1-47.1), against the estimate of ~50 (section 7): the estimate holds per byte. With the real masks it
is more, because a mirror's stored shifts are spread out (on average 3.8 of 8 stored, the steps between them still
cost): the first build (shift 0, then one step a shift) filled 1 MB in 381 frames (66 T an output byte); reading
straight at the lowest stored shift saved 26 frames (the model said ~37), the table clear 4 more: 351 (61 T).

**Profile of the 1 MB fill** (the emulator's call profiler, before the table-clear change, frames of 71,136 T): the
steps 131 (37 %; 23 T a byte), the OUTI writes 93 (16.2 T a byte), the reads 87 (shift 0 10, mirrored 28, shifted 32,
mirrored and shifted 17), fg_put's seeks and the slots 12, the table clear 11, making the row code 7, the rest 4.

**The fill's time** (tests/m8_fstore.py, the harness start with the fill minus the start without it, frames):

| | step 1 (spr_fetch per key) | step 2 (the generator) |
|---|---:|---:|
| 1 MB (class 1: 891 keys, 409,512 bytes) | 774 = 15.5 s | **351 = 7.0 s** (2.2x) |
| 16 MB (classes 1 + 2: 2,153 keys, 1,232,824 bytes) | 2,250 = 45.0 s | **933 = 18.7 s** (2.4x) |

**The boot timeline** (tests/m5_boot.py, frames from the reset; the loader now includes #20's read-speed measurement,
+13 frames against the table in section 11):

| | the loader (floppy) | the fill ("PREPARING SPRITES", incl. the game image's start) | PRES starts | the title's step a | level_ready (a key at step a) |
|---|---:|---:|---:|---:|---:|
| 512 KB | 723 = 14.5 s | - | 830 = 16.6 s | 1,053 = 21.1 s | 1,161 = 23.2 s |
| 1 MB | 725 = 14.5 s | 426 = 8.5 s (was 851) | 1,259 = 25.2 s (was 1,666) | 1,482 = 29.6 s (was 1,886) | 1,590 = 31.8 s |
| 16 MB | 725 = 14.5 s | 1,012 = 20.2 s (was 2,334) | 1,845 = 36.9 s (was 3,150) | 2,068 = 41.4 s (was 3,370) | 2,176 = 43.5 s |

**Wait states** (MZPico): every port access 1 T longer (mr1r18_wait = 1, tests/m8_fstore.py with POP800_RD_WAIT=1) costs the fill **+7.1 frames on 1 MB, +20.7 on 16 MB** (step 1: +10.7 / +31.5): the generator reads each image once per mirror instead of once per key, so w wait states add w x 0.14 s (1 MB) / w x 0.41 s (16 MB).

**Memory**: the level-start overlay 2,746 -> 3,438 bytes (W2: 658 free); the overlay area in page 7 to 0xFD9F (608
bytes free; the cheat build to 0xFF3D, 194 bytes free: the next W2 growth needs another place, e.g. a fill-only overlay); main RAM, the low block and block 2 unchanged (nothing resident). The fill's scratch is
SPRBUF_A/SPRBUF_B as before (both free between ticks and overwritten by the compose; the swap to PRES replaces them),
dir_buf put back: main RAM after the fill is as after a start without it (tests/m7_launch.py).
