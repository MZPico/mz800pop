# Performance budget and measurements

Budget: one game tick = 4 video frames at 50 Hz = 283,544 T-states (12.5 fps, the original's
design rate; the DOS version runs 12 fps and 10 fps in fights).

## M1 kernel measurements (2026-10-25, tests/m1_test.py, two moving kid sprites, frames 401-408)

Per tick, both characters moving, averaged over 8 ticks:

| Phase | T-states | Notes |
|---|---:|---|
| fetch A / B (RAM disk read + shift + mirror) | 75,879 / 86,996 | ~83 T per source byte (21 INIR + 62 table shift) + ~130 T per plane-row |
| restore (shadow room -> compose, both) | 95,180 | ~280 T per plane-row: seek 52 + INI chain 16/byte + overhead |
| draw (masked sprite into compose, both) | 84,258 | ~260 T per cell of 4 planes, empty cells skipped |
| fore pieces (masked, from pack) | 22,105 | only where a pillar overlaps a rect |
| blit (compose -> VRAM, both) | 69,433 | 16 T/byte + ~110 T per plane-row |
| total work | ~433,000 | 6.1 frames |

One moving character: ~215,000 T = 3.0 frames -> fits the 4-frame tick with the game logic.
A character whose frame, facing and sub-byte shift did not change costs no fetch (cache);
a character that did not move needs no compose at all.

Conclusion: nominal 12.5 fps (tick = 4 frames) when one character moves, ticks stretch to
5-6 frames (8-10 fps) when both move. 16.7 fps is out of reach with planar 16-colour sprites.

## Things measured and rejected
- PUSH-based VRAM writes: no gain because the source bytes must still be loaded (LDI's 16 T/byte
  is the floor; LDIR 21 T/byte is equal to an LDI chain at 5 bytes per row because of call overhead).
- Pre-shifted sprite variants (4 shifts, 2-px grid): would cut fetch from ~80 to ~21 T/byte, but the
  kid set alone would need ~485 KB; mirrored variants would double it. Not feasible with <= 512 KB.
- Pairs (maskinv,data) layout: the pairing pass cost more than it saved; the interleaved-cell
  layout with the mask computed once per cell in the draw loop is cheaper.

## Known remaining fat (each ~10-20 K per tick)
- restore: compose row advance and shadow row advance could use patched strides (-20%).
- blit: LDIR with patched BC is equal to the LDI chain; the per-row overhead (~110 T) is the cost.
- fetch: inline the shift routine per plane to drop call/ret and counter overhead (~130 T/row).

## Hardware facts used
- VRAM writes >= 8 T apart are free; LDI/LDIR/INI to VRAM pay no wait states.
- Shadow room = clean background in RAM disk page 1 (plane p at p*8000 + y*40 + x), read at
  16-21 T/byte; rewritten only when a room is drawn or a background block changes.

## M3 room renderer measurements (2026-10-26, level 1, emulator cycle counter)

| Operation | T-states | Frames | Notes |
|---|---:|---:|---|
| room_ops (op list of a room, ~100 ops) | 620-740 K | 9-10 | prandom now ~1.5 K per call (register LCG), add_op ~1.4 K, wall_pattern ~14 K per wall tile |
| run_ops (full room, 15 cells of 8x64) | 6.2-7.9 M | 90-112 | fixed cost ~150 K per cell (shadow write ~85 K, blit ~55 K, PUSH fill 13 K) + pieces |
| lay_piece copy, 4-byte rows | ~240 T per plane-row | | ~470 with the general edge merge, ~300 right-edge fast path |
| lay_piece masked, 4-byte rows | ~400 T per plane-row | | block read + cm1 chain |
| torch flame (op_patch + 2x18 rect) | ~80 K | 1.1 | fill 10 K, candidate scan 10 K, lay 19 K, shadow 13 K, blit 11 K: per-row overheads dominate |
| generic tile_redraw (3 regenerations + splice + rect) | 170-500 K | 2.4-7 | per tile: state loads ~9 K, draw_tile 8-11 K, splice 1-16 K, slices_build ~25 K |

Where the time goes: per-row overhead of ~150-180 T in fill/shadow/blit/lay for narrow rects, the
STD RAM-disk seek per row of the shadow room (stride 40), and the op-list bookkeeping. Planned for the
M8 pass: leaner row loops (patched immediates, no memory variables in loops), incremental slice-table
updates instead of slices_build, cached per-row state in tile_regen, and a cheaper shadow layout.

## M4 prototype tick cost (2026-10-26, level 1, 200 ticks of a random script, emulator cycle counter)

| Phase | T-states (avg / max) | Frames |
|---|---:|---:|
| kid logic + room change check + torch/bubble animation | 210 K / 223 K | 3.0 |
| kid_place + kid_draw (fetch, restore shadow, draw, fore pieces, VBLN wait, blit) | 208 K / 380 K | 2.9 |
| whole tick | 417 K / 601 K | 5.9 / 8.5 |

Measured 6.5 video frames per tick over the run (nominal 4): the prototype plays at ~7.7 fps.
The kid logic itself is small (~10-20 K); the animation part is the two torch flames (~80 K each,
see the M3 table). Sprite drawing is dominated by the per-row overheads of restore/blit and the
8-byte-wide compose rect of the widest frames. Both are M8 material: leaner row loops, torch flames
every other tick or a cheaper flame path, and a sprite rect that only covers the changed bytes.

## M4 game tick cost (2026-10-26, level 1 walkthrough, first 200 ticks, emulator cycle counter)

| Phase | Frames per tick (avg) | Notes |
|---|---:|---|
| tile redraws (view_redraw) | 4.7 | two torch flames per room at ~1.1 each, gates and the level door through the generic per-tile redraw (2-7 each) |
| kid + falling floors (draw_objects) | 3.5 | dirty rects through restore/draw/fore/blit |
| room changes (draw_room_full) | 1.9 | ~130 frames each, three in these 200 ticks |
| kid logic + traps (kid_tick) | 0.9 | |
| tile snapshot | 0.5 -> ~0.1 | room links looked up once per tick now |
| total work | ~11.6 | max 140 on a room change; measured 21 frames per tick over the whole walkthrough |

So the game plays at about 2-4 ticks per second instead of 12.5. The M8 pass has to bring the torch
flames, the gate redraw and the sprite path down by an order of magnitude (see the M3 notes: per-row
overheads dominate), and hide room changes.

### Update after the first playtest (2026-10-26)

- Flicker (prince vs torch flames, shaking floors): tile redraws now write the shadow room only and
  report their rect; the object pass composes background + falling floors + prince + fore pieces and
  blits once. Verified: no screen writes between the end of a tick and the object pass (711 ticks).
- Door/gate slowness was mostly a bug: the tile snapshot lived in DATABUF, which the tile redraw itself
  overwrites, so ~30 tiles were redrawn per tick while a door moved (~100 frames per step). Fixed
  (snapshot at 0xF510): one tile per step, ~20 frames per door tick, ~10 frames per normal tick.
- What remains in a door step: re-laying ~27 pieces of the door area, ~18 K T per opaque piece and
  ~55 K T per transparent one (12 of the ~20 frames). That is the M8 work: pre-inverted masks, opaque
  bytes copied without combining, fewer per-row RAM-disk seeks.

### Update after the second playtest (2026-10-27)

- The screen copy writes the four planes of a row back to back (`blq_n`, generated): 1.31 + 0.28 * w
  lines per row (w = bytes, 1.59 to 3.56 lines). Measured in the emulator, which shows no VRAM wait
  states on these writes. It is cheaper than the plane-by-plane loop (4 x (16w + 102) T a row).
- The beam position comes from the 8253 counter 1 (clocked by HSYNC, set to mode 2 with a 65536 period,
  and the counter 2 interrupt is masked through 8255 PC2). The VBLN interrupt latches it at scanline
  245. Canvas row 0 is 113 lines later.
- pend_flush copies a chunk when d >= h * (k - 1) + 20, where d is the lines until the beam reaches
  the chunk's top. The margin of 20 covers k and the ~13 lines between the beam read and the first
  write (the scan of the pending list).
- Walkthrough ticks 20-200: object-pass copies 573 clean, 0 torn (before: 428 clean, 148 torn). Room
  redraw copies are not timed (28 of 45 torn: a wipe while the new room appears). Frames per tick
  11.27 (before 11.76, when it waited for VBLN).

### Third playtest (2026-10-27)

- Level-door tick (walkthrough ticks 203-206), by main-loop phase: kid logic 1.5 frames, view_redraw 14-17
  (run_rect of the door area ~8, tile_regen of three tiles ~2.5, shadow writes ~1.5), draw_objects 5-8 (the
  door's fore pieces ~3.5). Per piece: 6x6 opaque door slice 13.3 K T (most of it the per-row edge merge),
  masked 4x60 jamb clipped to 3x46 92 K T (was 149 K before the single-run block read).
- Copy latency from the beam read to the first copy: 4 + 5.5 lines per pending chunk (measured), used in the
  same-frame schedule; BEAM_GUARD 12 lines around a chunk's top absorbs the prediction error.

## M8a speed work (2026-10-28; tools/profile.py = mz800emu's call profiler per routine)

| Situation | Before M8a | Now |
|---|---|---|
| Normal tick (walkthrough ticks 30-60, two torches) | 9.5 frames | 6.1 frames |
| Loose floor shaking (one tile redraw) | ~14 | ~10 |
| Level door step (walkthrough ticks 203-207) | ~23 | 17.8 |
| Room change (walkthrough tick 89) | ~134 | 105.9 |

What did it:
- Change detection: the 53 view tiles' addresses are built once per room (view.asm); a tick reads bytes.
- Torch flames as objects: an exclusive flame (the last back/mid op in its rect) is not kept current in
  the shadow; object chunks lay its current frame after the restore, a chunk inside a flame skips the
  restore, a torch tick only patches the op and marks the rect dirty. Torch chunks with nothing else in
  them come from a picture cache (RAM-disk page 6, per flame and frame).
- Piece laying: tight copy loops (INIR per row, right/left edge merges, clipped rows read and dropped);
  masks stored inverted in the packs; masked pieces combined straight from the RAM-disk port.
- Op lists: occlusion pass in run_rect (skip what an opaque op covers), per-slice vertical extents,
  incremental slice tables after a tile regeneration, per-cell buckets for full room draws.
- Main loop: a late tick does not wait for the next frame.
- Door step (20.2 -> 18.3): the background-only redraw of a rect composes into SPRBUF_B and keeps it; an
  object chunk of exactly that rect starts from it instead of restoring from the shadow (oc_kept). The flame
  registry is re-found by place after a tile redraw instead of rebuilt, unless the redraw touched a flame
  (flm_hook, flames_sync). slices_fast skips the slice starts when a slice count is unchanged.
- Door step (18.3 -> 17.8; walkthrough ticks 190-260 11.04 -> 10.75): run_rect's scan records the ops it
  finds (RR_PTRS) and the lay pass runs from that list (src/m4/rcache.asm) instead of walking the slice
  tables again; a copy-mode op that the next op repeats lower down (same flags, image, column) is laid only
  down to the next one's top row, which is exact because the edge bits are per piece, not per row.
- Room change (116.9 -> 105.9): the wall pattern's random draws come from a table (its seed is
  row*10 + col + room < 64, at most 10 draws, all reduced mod 2, 4, 5 or 7, which divide 140: the table
  holds the draws mod 140; prandom 6.2 -> 1.1 frames; the game's own draws still use the generator).
  shadow_write keeps the RAM-disk port in C (address/data ports switched by dec c / inc c, out (c),e) and
  writes full 8-byte rows with inline OUTIs (15.6 -> 11.7); restore_shadow got the same row loop. mul8
  loops over the bits of the smaller factor and stops early (3.2 -> 1.3).
- Visited-room cache: deferred until M6 shows the guard sprites' RAM-disk needs (user, 2026-10-28); each
  cached room needs ~33 KB (shadow + op lists), only pages 6-7 are free.
- Tried and dropped: a per-rect cache of the composed prefix (the ops before the moving ones, keyed by the
  record contents, picture in RAM-disk page 6). A level door repeats only 3 ops (black fill, jamb, stairs)
  before its 14 moving slices; loading the 7x64 picture (~0.6 frames) cost about what it saved, and growing
  the dirty rect to make the key stable made gates slower (gate_push 6.57 -> 6.93). What is left in a door
  step is per-piece cost: ~25 pieces at ~10 K T each in lay_piece16 itself.

Where a normal tick goes now (~6.1 frames): object pass ~4.1 (kid frame fetch 0.9, fore pieces 0.7,
restore 0.6, kid draw 0.4, copies 0.8), kid logic ~1.0, tile redraws/snapshot ~0.4. The kid's own area
has a data-movement floor of ~1.8 frames (restore, fetch+shift, draw, copy of ~1 KB each).
Room change (~117): piece laying ~55, shadow write ~15 (32 KB to the RAM disk), op lists ~17, copy ~11.
Frame skipping (draw fewer ticks, keep the logic at 12.5/s) was tried and deferred (user, 2026-10-28):
with drawing at ~5.5 frames the measured gain was small (6.2-7.9 ticks/s); revisit after the speed work.

## M6 drawing: the guard on screen (2026-10-28)

The guard, both swords, the hurt splashes and the guard's hit point strip go through the kid's object pass
(src/m4/overlay.asm people_place / people_chunk): five object slots (kid, kid's sword, guard, guard's sword, one
hurt splash), each with its own sprite descriptor and buffer; per character one dirty rect (this tick's objects U
last tick's), the two merged into one when they meet; the chunks of both characters carry the same-frame flag
(oc_kidtouch checks both rects), so they show in the same frame as long as they fit the three chunk buffers.
Objects are drawn in SDLPoP's order (per tile in redraw order with the tile overlays between them, y order within
a tile), clipped by their character's clip_char.

| Stretch (tools/perfcheck.py, tools/profile.py) | Frames per tick |
|---|---:|
| fight1 ticks 60-160 (kid and guard fighting, palace) | 8.99 |
| level2_fight ticks 90-190 (dungeon) | 9.4 |
| fight_killpush ticks 150-250 (push-off, the guard falls) | 12.5 |
| no guard (walkthrough 30-60) | 6.11 (was 5.98: +0.13 for the general object list, sort and clips) |

Where a fight tick goes (fight1 60-160, 8.99 frames): object pass 6.8 = placing 2.0 (image fetches 1.5: the kid,
the guard and the swords change frame almost every tick) + compose chunks 3.7 (sprite draws 1.1, fore pieces 1.1,
shadow restore 0.9, torch flames 0.2) + copies 0.8 + scheduling 0.3; kid and guard logic 1.2; tile redraws
(torches) 0.8. About three compose chunks per tick (the two characters' merged rect is 9-14 bytes wide).
Not done: a character whose objects did not change is still composed every tick (skipping it would make a
standing guard almost free).

## Code overlays (2026-10-29, src/m4/ovl.asm)

The full room draw and the level start run from RAM-disk overlays (docs/memory.md). Load cost, measured in the
emulator (cycle counter from the stub's entry to the window entry, walkthrough of level 1):

| Load | Bytes | T-states | Frames | When |
|---|---:|---:|---:|---|
| level-start overlay into W2 | 945 | 20,653 | 0.29 | every level start / restart (load_level: 10.6 frames in all) |
| room overlay into W1, first room draw | 868 | 19,092 | 0.27 | once: W1 keeps it (draw_room_full + flames_rebuild 113 frames) |
| room overlay already in W1 | - | 104 | 0.001 | every later room change (the stub's check) |

About 21 T per byte (INIR from the RAM-disk port) plus ~300 T for the table entry. tools/perfcheck.py after the
change: all stretches within +0.3% of the baseline (room change 105.91 vs 105.92); the baseline was not updated.

## M5 level-event logic (2026-10-29; scratchpad ovlmeas: the game playing the M5 scenes, mz800emu's call profiler)

New resident per-tick hooks, measured per call (T-states):

| Hook | T per tick | Notes |
|---|---:|---|
| show_time (evres.asm) | 160-212 | the clock, every tick; ~1.5 K more per tick only in the last minute (rem_tick mod 12) |
| draw_game_frame (evres.asm) | 120-240 | text and flash timers, the mirror flag |
| timers: feather fall counter | ~20 of 124-163 | |
| fall_accel / play_seq / jump_up / is_obstacle / check_on_floor feather, mirror and level 12 tests | ~20-40 | only on the paths that fall, jump or hit a tile |
| state_snap | 17 | a `ret` in the game (the harness's trace point in m4test) |
| autocontrol_shadow stub (ovl_w1 check) | ~100-200 | only while a scripted shadow is in the level |

Together about 500 T = 0.007 frames per tick. Overlay loads (W1): the events overlay (583 bytes) ~13 K T = 0.19
frames, the room overlay (868 bytes) ~19 K T = 0.27 frames; the level-start overlay (1,216 bytes, W2) ~26.5 K T
inside load_level (710 K T = 10 frames with alter_mods and play_level). Loads per scene: level 4 mirror (127 ticks)
2 (room at the start, events at the mirror jump); level 12 shadow merge (224 ticks, 4 room draws) 3; level 5 shadow
(178 ticks) 3; level 6 shadow + exit (88 ticks) 5 (incl. the level 7 start); feather fall (320 ticks) 3. So at most
one events load after a room draw and one room-overlay reload at the next room draw: < 0.5 frames per room change
(on ~100-frame room draws). tools/perfcheck.py after the change: all stretches within +0.3% (baseline not updated).

## M5 drawing (2026-10-30: the shadow, the mirror image, both splashes, texts, flashes, the upside-down screen)

tools/perfcheck.py, the build before the change measured the same way (its numbers in brackets; the baseline file was
not updated):

| Stretch | Frames per tick |
|---|---:|
| normal tick (walkthrough 30-60) | 6.15 (6.11) |
| level door step (walkthrough 203-207) | 17.53 (17.54) |
| room change (walkthrough 89) | 105.91 (105.92) |
| walkthrough 190-260 | 10.82 (10.79) |
| gate (gate_push 200-260) | 6.78 (6.73) |
| traps (traps_b1 0-300, one hurt flash) | 6.07 (6.03) |
| fight (fight1 60-160) | 9.08 (9.04) |
| level 5 shadow (level5_shadow_potion 10-110) | 19.64 (17.46, the shadow drawn plain) |
| level 12 shadow fight (level12_shadow_hit 120-170) | 12.32 (9.69, the shadow drawn plain) |
| level 4 mirror image (level4_mirror_image 100-175) | 7.95 |

Without the effects the cost is the bookkeeping of seven object slots, the per-tick text and flash checks and the
text draws themselves (a text appears or is erased: the W2 text overlay, ~19 K T to load, ~20 K T to draw):
0.0-0.05 frames per tick. The upside-down screen costs nothing while the screen is upright (set_flip patches blit and
the copy scheduler only when it turns). A flash holds the tick for about two frames (SDLPoP shows it 2/60 s).
The shadow's XOR copy (spr_xor) is the expensive part, ~2.3-2.6 frames per tick for a full kid-size shadow: per row the
needed source cells are shifted 1 or 2 px through four rla chains (unrolled, ~34 T a byte), the first copy's black
pixels found, then each visible cell XORed into the four planes (~315 T a cell). Ideas if it matters: a cached
pre-shifted XOR image per (frame, shift) in SPRBUF_B (pays when the shadow stands), the XOR value for plane 3
precomputed per cell (a plain four-plane XOR loop, ~-0.2 frames).

## Guard room-change overlays, keys, save (2026-10-30)

The guard's room-change code moved into two W1 overlays (docs/memory.md): a room change now loads the guard-enter
overlay (739 bytes, ~16 K T = 0.23 frames) in tick_post's check_the_end and then the room overlay again in
draw_room_full (938 bytes, ~20 K T = 0.28 frames); with a guard in the room the kid leaves, also the guard-leave
overlay (342 bytes, ~7.5 K T). The keyboard's Ctrl keys (get_controls) and the Ctrl+G check at the tick start cost
~150 T per tick. tools/perfcheck.py (baseline not updated):

| Stretch | Frames per tick (baseline) |
|---|---:|
| normal tick (walkthrough 30-60) | 6.15 (6.11) |
| level door step (walkthrough 203-207) | 17.53 (17.54) |
| room change (walkthrough 89) | 106.41 (105.92: +0.5 frames, the two overlay loads) |
| walkthrough 190-260 | 10.82 (10.76) |
| gate (gate_push 200-260) | 6.78 (6.72) |
| traps (traps_b1 0-300) | 6.07 (6.01) |
| fight (fight1 60-160, guard on) | 9.08 (8.99) |

All but the room change are as after the M5 drawing (previous section). Saving (Ctrl+G) pauses the game while the drive
works (interrupts off: FRAMES misses those VBLNs): in the emulator (no rotation, no step time) mostly the two seeks'
60 ms delay loops, ~0.15 s; on a real drive estimated ~1 s (motor start, seeks to the directory and back, ~3 turns).

## Sound model (M7 step 2, 2026-10-30)

The request side of the sound model (src/m4/sound.asm, sndobj.asm: snd_play at every call site, snd_next once per tick,
no audio yet) costs 0.3-1.2% (`make perf`, baseline not updated): normal 6.11 -> 6.13, level door 17.54 -> 17.74, room
change 105.92 -> 106.42, walkthrough 190-260 10.76 -> 10.81, gate 6.72 -> 6.78, traps 6.01 -> 6.08, fight 8.99 -> 9.07
frames per tick. The IM2 table now has one entry (no change to the ISR).

## PSG player (M7 step 3, 2026-10-30)

The VBLN ISR now ends in the player (src/m4/psg.asm snd_isr). Measured in tests/m7_sound.py (breakpoints at `isr` and
the player's `reti`, 400 interrupts while a driver plays the effects back to back): **idle 211 T** from isr to reti (was
172 T: +39 T a frame, 0.06% of a frame); **playing 235-798 T, average 371-417 T** in effect-dense stretches (+63..+626 T;
at most 9 PSG bytes in one frame, 1.9-2.7 bytes on average in the frames that play a record, 41-56 T each: OTIR's 21 T
plus the PSG's READY wait, which mz800emu models as 16 + 4..19 T synced to the chip's clock). The
main code pays at each start: snd_start ~0.5 K T + 21 T per stream byte (the RAM-disk copy; 6-96 bytes for an effect,
up to 255 for a music placeholder), and the silent mode (every harness run) starts every request.
tools/perfcheck.py (baseline not updated; step 2's numbers in brackets):

| Stretch | Baseline | Step 2 | Now |
|---|---:|---:|---:|
| normal tick (walkthrough 30-60) | 6.11 | 6.13 | 6.18 (+1.1%) |
| level door step (walkthrough 203-207) | 17.54 | 17.74 | 17.73 (+1.1%) |
| room change (walkthrough 89) | 105.92 | 106.42 | 106.91 (+0.9%) |
| walkthrough 190-260 | 10.76 | 10.81 | 10.86 (+0.9%) |
| gate (gate_push 200-260) | 6.72 | 6.78 | 6.79 (+1.0%) |
| traps (traps_b1 0-300) | 6.01 | 6.08 | 6.09 (+1.3%) |
| fight (fight1 60-160, guard on) | 8.99 | 9.07 | 9.10 (+1.2%) |

## M7 step 4: the music player (2026-10-31)

The player now steps four software envelopes in the ISR while a stream plays (~350 T a frame), reads its stream
through the 254-byte ring and the main code refills the ring (snd_fill: from snd_start, and from snd_playing once a
tick: ~60 T when nothing is to copy, ~47 T a byte copied; music needs at most ~4 bytes a tick, the in-game pieces ~2:
under 300 T a tick). tests/m7_sound.py: the ISR from isr to reti 211 T idle (unchanged), 577-2,204 T while playing,
878-931 T on average (driver runs; step 3: 235-798, avg 417): ~1.3% of the CPU while a sound plays, nothing
otherwise. A full room draw (tick 89 of the walkthrough, 107 frames between two refills) is covered by the ring: the
densest piece (the ending) needs a refill only every 229 frames. tools/perfcheck.py (baseline not updated):

| Stretch | Baseline | Step 3 | Now |
|---|---:|---:|---:|
| normal tick (walkthrough 30-60) | 6.11 | 6.18 | 6.20 (+1.5%) |
| level door step (walkthrough 203-207) | 17.54 | 17.73 | 17.77 (+1.3%) |
| room change (walkthrough 89) | 105.92 | 106.91 | 106.91 (+0.9%) |
| walkthrough 190-260 | 10.76 | 10.86 | 10.97 (+2.0%) |
| gate (gate_push 200-260) | 6.72 | 6.79 | 6.79 (+1.0%) |
| traps (traps_b1 0-300) | 6.01 | 6.09 | 6.10 (+1.5%) |
| fight (fight1 60-160, guard on) | 8.99 | 9.10 | 9.12 (+1.4%) |

## M7 step 5: the waits on sound (2026-10-31)

The ticks model adds a countdown at each tick start (guard.asm timers, ~30 T), a table lookup when a sound starts
(snd_next, ~60 T) and the mode checks at the waits (the death timer only while the kid is dead, the crouch check only
on frame 109); the end-of-level clock charge (show_time once per tick still owed, at most 153 calls, ~10 K T) runs
once, in the level-start overlay. tools/perfcheck.py (baseline not updated):

| Stretch | Baseline | Step 4 | Now |
|---|---:|---:|---:|
| normal tick (walkthrough 30-60) | 6.11 | 6.20 | 6.20 (+1.5%) |
| level door step (walkthrough 203-207) | 17.54 | 17.77 | 17.76 (+1.3%) |
| room change (walkthrough 89) | 105.92 | 106.91 | 106.48 (+0.5%) |
| walkthrough 190-260 | 10.76 | 10.97 | 10.99 (+2.1%) |
| gate (gate_push 200-260) | 6.72 | 6.79 | 6.79 (+1.0%) |
| traps (traps_b1 0-300) | 6.01 | 6.10 | 6.10 (+1.5%) |
| fight (fight1 60-160, guard on) | 8.99 | 9.12 | 9.11 (+1.3%) |

(The room change is 0.4 frames faster than in step 4; not investigated: the step's only change on that path is the
guard records and globals' new address in low RAM, docs/memory.md, and the end of the level-start overlay's layout.)

## M8a part 2 (2026-10-31 / 11-01): gate redraws, a pixel regression, the time-exact pacing prototype

### A. Gate redraws (in the release)

Before: every change of a gate's modifier went through the generic tile_redraw of the gate's tile (three regenerations
and a rect), and a gate in the left room's column 9 through two of them (the drawing tile and the tile above it: six
regenerations, two rects); a closing gate changes its modifier every tick but moves one row only every fourth one, and
not at all above 188, so most of those redraws changed nothing on screen. Now (src/m4/view.asm vrd_gate, 49 bytes in
the low block; src/m4/gate.asm gate_redraw, 76 bytes in block 2):
- a gate tick redraws only when the visible bar position min(modifier, 188) / 4 changes, and nothing at all for a gate
  that draws nothing on this screen (our own column 9, the above room's row 2);
- the redraw regenerates only the tiles that draw from the gate: the right neighbour (the bars, draw_gate_back) and the
  tile above that one (the top, draw_tile_anim_topright), the latter only when it is empty, a big pillar top or a door
  top (can_see_bl), and lays one dirty rect; for a gate in the below room's row 0 only our row-2 tile above-right.

gate_push (level 4; scratchpad gateticks2.py, frames per tick, tick_done to tick_done), before -> after:

| Ticks | What | Before | After |
|---|---|---:|---:|
| 18-60 | the gate opening while the kid stands in room 1 (the gate is in column 9: not visible from there) | 6.79 | 5.55 |
| 65-115 | the gate closing from 238 down, seen from room 2 (no visible change above 188) | 7.06 | 4.06 |
| 115-303, the visible steps (every 4th tick) | one row of bars moves | 10.81 (9.7-9.9 typical) | 10.22 (8.1 typical) |
| 115-303, the other ticks | the modifier changes, the bars do not | 5.81 (6.69 typical) | 3.43 (3.7 typical) |
| 200-260 (tools/perfcheck.py's gate stretch) | | 6.81 | 5.13 |
| 8-9 | no gate change (reference) | 4.92 | 4.91 |

perfcheck's gate stretch: 6.72 (baseline) -> 5.13 (-23.7%); the other stretches unchanged (the sound work's +1-2%
of M7 stays; tools/perfcheck.py on the final build of 2026-11-01 against the original baseline: normal 6.20 (6.11, +1.5%), door
17.76 (17.54, +1.3%), room change 106.92 (105.92, +0.9%), walkthrough 190-260 10.97 (10.76, +2.0%), gate 5.13 (5.13), traps 6.10
(6.01, +1.5%), fight 9.12 (8.99, +1.4%); tests/perf_baseline.json keeps the original values for all but the gate stretch).

### The regression (found 2026-10-31 by the m5 scene set, fixed 2026-11-01)

tests/m4_game.py --every 1 on tests/m5_scripts: level6_shadow_exit 4,876 differing pixels from tick 21,
level5_shadow_potion 66,166 from tick 17, the logic exact; the m4 and m6 sets, which have one moving gate (gate_push's,
in room 1's column 9), passed. Both scenes have a gate of the shown room in a column below 9 that opens (level 6 room 1
tile 12, level 5 room 24 tile 1 after the button): for that case (VS_KIND 0) gate_redraw regenerated the gate's own tile
(VS_TAG = its position) instead of the right neighbour that draws the bars and the tile above that one, so the bars
stayed where they were while the reference moved them (the diff: the bar column, 376-470 pixels a tick, the lattice one
row off). Found by tracing which redraw routine each tick called (scratchpad diag_gate.py: breakpoints on gate_redraw,
tile_redraw, torch_fast, the gate modifiers and the pixel diff per tick). The same review found that a gate in the below
room's column 9 (VS_KIND 3, VS_TAG 0xff: nothing of it on screen) would have regenerated tag 0xff; it is skipped now.
Fix: gate.asm computes the bars tile per kind (kind 0: VS_TAG + 1; kind 1: VS_TAG; kind 3: the top tile only, nothing
for 0xff) and the top tile from it (one row up, or the above row's column c for row 0: tag 30 + c, snapshot entry 33 + c):
65 -> 76 bytes. Block 2 had 13 bytes free, and the cheat build needs 13 more than the release: 24 more `jp` -> `jr` in
block 2 code that runs at most a few times a tick (guard.asm's sword-fight and autocontrol dispatch, 7; overlay.asm's
overlay tile classification ob_*, 17). After the fix all pixel sets pass (the test results below); gate_push's numbers
are unchanged (its gate is kind 1 from room 2).
Gates on the final binaries (build/m4game.bin md5 2f705171..., 2026-11-01): tests/m4_game.py --every 1 on the m4 (18 scripts),
m6 (16) and m5 (18) scene sets 0 state diffs and 0 differing pixels; tests/m4_test.py 63 scripts 0 differing ticks; tests/m7_launch.py
and tests/m7_keys.py ok; tests/m8_pace.py ok on walk_level1, gate_push and fight1; tools/perfcheck.py ok (the table below).

### Where a visible gate step goes (tools/profile.py, gate_push, the fixed build)

The closing step seen from room 2 (tick 123: 180 -> 179, the bars move one row; the gate is in the left room's column 9,
so our column 0 draws the bars and our (0, 0) the top): 8.15 frames against 3.78 for the neighbouring ticks whose
modifier change is not visible (tick 124-127), so the step costs 4.4 frames:

| Part | Frames | Notes |
|---|---:|---|
| tile_regen x 2 | 1.07 | tile_gen 0.52 (the op lists of the two tiles), splice_tbl 0.40, slices_fast ~0.15 |
| run_rect: laying | 1.89 | rc_hook / rc_ahead: 8 pieces through lay_piece16 1.71 (the edge-merge loops cmx_4 0.41) |
| run_rect: fill_black | 0.23 | |
| run_rect: shadow_write | 0.29 | the rect goes to the shadow room only (RR_SHONLY) |
| the object pass | ~0.5 | the rect becomes a third compose chunk (obj_chunk +0.28, from the kept SPRBUF_B) and a VRAM copy (blq_4 0.19) |
| view_redraw's own scan, dir_entry etc. | ~0.4 | |

Before A the same step cost 9.73 (view_redraw 5.65: two tile_redraws = six tile_regens 2.88 + two run_rects 2.32) and
the ticks between them 6.69 (the six regenerations with nothing visible: 2.90). What is left is the lay pass: ~1.9
frames for 8 pieces (two bar slices, the top slice, the bottom piece, the frame, the floor pieces behind), and the fixed
costs of a rect (fill, shadow write, chunk, copy, ~1.2).

The opening step in room 1 (tick 40: 88 -> 92): the gate is in room 1's own column 9, nothing of its bars is on this
screen, and view_redraw costs 0.35 frames, the same as a tick without any gate change (tick 8); the tick's 5.97 frames
against 4.91 at tick 8 are the kid standing at the right edge (fore pieces 0.75 vs 0.22, lay_piece16 0.98 vs 0.48, the
same-frame copy scheduling pf_seq 0.54): nothing is left there for the gate. Before A it was 6.29 with view_redraw 1.14.

The bar slice image (CH_ENV image 52, 20 x 8 in the dungeon set, 24 x 8 in the palace set; stacked every 8 rows from the
bottom piece, image 50, upward, the top one cut by door_fram_slice) is not vertically uniform: it has 8 distinct rows
(two vertical bars and a diagonal lattice with an 8-row period), so a one-row move changes every row of the bar column,
not just its top and bottom rows. But the stack moves rigidly: after a one-row step every interior row equals the row
above (or below) it from the previous screen; only the row under the frame top and the bottom piece's rows are new. A
one-row shift of the column in the shadow room and in VRAM (4 planes x ~60 rows x 3 bytes) plus two short pieces would
replace the 8-piece lay pass (~1.9 frames); it needs the previous screen to be current there (no object over the gate:
the kid or a guard in the gate's column would have to fall back to the full redraw). Not done.

### B. Time-exact pacing (built and measured, not adopted)

src/m4/game.asm, PACE_MODE (a byte in the code; 0 in the release, the harness pokes it, `make pace` builds a mode-1
game and disk in build/pace; tests/m8_pace.py compares the two modes). Mode 0 is the pacing as before: a tick starts
when 4 frames have passed since the last one, a late tick starts at once, every tick is drawn. Mode 1:
- a fixed clock: the next tick is due at NEXT_TICK, which advances by 4 frames per tick whatever the tick cost;
- a tick that starts a whole tick late (4 or more frames after it was due) runs its logic without drawing, at most
  SKIP_MAX = 2 in a row; the tile snapshot is kept over an undrawn tick, so the next drawn tick redraws everything that
  changed since the last drawn one (tiles, flames, the people, the falling floors: tests/m8_pace.py checks that its VRAM
  and the shadow room equal mode 0's at every drawn tick);
- never skipped: a tick that changes the room or turns the screen upside down, a flash, a guard hit (his strip and
  splash); the kid's hit shows as the flash;
- old rects: an undrawn tick leaves the people's last drawn rects alone (they are the last drawn position's), so the
  next drawn tick restores what was last on screen;
- later than DEBT_MAX = 8 frames (a room change, a level load, a pause, a save) the clock restarts from now: no
  catching up after a stall.
The variables NEXT_TICK, SKIP_TICK, SKIP_RUN, SKIPPED are low RAM 0x01B8-0x01BC (zeroed by the launcher's low-RAM clear;
the harness runs in zeroed RAM); mode 0 reads SKIPPED and SKIP_TICK (both 0) and writes nothing of the clock.

tests/m8_pace.py (the release binary with the mode poked; ticks a second over the stretch, frames = frames per tick):

| Stretch | Mode 0 (every tick drawn) | Mode 1 | Undrawn ticks | Cost of a tick (frames of work): undrawn / drawn after a skip / drawn after a drawn |
|---|---|---|---|---|
| walk 30-60 | 8.07 ticks/s, 6.20 frames | 12.32 ticks/s, 7.4 screens/s | 12 of 30 | 1.18 / 6.74 / 5.07 |
| walk 190-260 | 4.55, 10.99 | 5.93, 4.1 screens/s | 22 of 70 | 1.13 / 12.39 / 11.71 |
| gate opening 18-60 | 9.01, 5.55 | 11.04, 7.6 | 13 of 42 | 1.33 / 6.07 / 5.41 |
| gate 200-260 | 9.75, 5.13 | 12.42, 9.3 | 15 of 60 | 1.12 / 2.07 / 5.32 |
| fight 60-160 | 5.48, 9.12 | 8.24, 4.5 | 45 of 100 | 1.40 / 9.30 / 10.77 |

(Numbers of 2026-10-31; the rerun on the fixed build of 2026-11-01 gave the same within the run-to-run variation of the skip pattern:
walk 30-60 11.48 ticks/s, 7.3 screens/s, 11 undrawn; walk 190-260 5.67, 4.1, 20 undrawn; the gate and fight stretches identical.)
The logic is identical in both modes at every tick (kid and guard lines, the guard records, the level events, the sound
model, the traps, the blueprint) and every drawn screen equals mode 0's. Decision (user, 2026-10-31): built and
measured, kept as a switch (build/pace, PACE_MODE), not adopted: the game should keep drawing every tick, and the speed is
to come from the drawing work first (the next items: the beam wait, the fore-layer precompose, the kid rect split, the
standing guard, the kid logic trims).

## Memory reclaim (2026-11-01; docs/memory.md)

Cold code went into overlays (the start-up, the buttons, the hit point strips, an item taken, chomped, leave_room's level
specials: 896 bytes of main, 111 low, 249 block 2 freed) with no change in what a tick does; the new W1 loads happen once
per plate episode, per hit point change, per item or per chomper death (~0.3 frames each: the overlay, then the room overlay
again at the next room draw). tools/perfcheck.py on the final build (baseline not updated):

| Stretch | Baseline | Before (2026-11-01 gate fix) | Now |
|---|---:|---:|---:|
| normal tick (walkthrough 30-60) | 6.11 | 6.20 | 6.20 |
| level door step (walkthrough 203-207) | 17.54 | 17.76 | 18.09 (+1.9%) |
| room change (walkthrough 89) | 105.92 | 106.92 | 106.91 |
| walkthrough 190-260 | 10.76 | 10.97 | 10.99 |
| gate (gate_push 200-260) | 5.13 | 5.13 | 5.13 |
| traps (traps_b1 0-300) | 6.01 | 6.10 | 6.03 (-1.1%) |
| fight (fight1 60-160, guard on) | 8.99 | 9.12 | 9.12 |

The door step's +0.33 frames a tick is not work: tools/profile.py over ticks 203-207 of both builds shows every routine
equal (view_redraw 10.92, run_rect 8.10, kid_tick 1.10, the same chunks) except the same-frame copy scheduler's beam waits
(pf_seq 22.8 calls, pf_calc 28, mul8 90 a tick appear in the top 45: obj_chunk 2.86 -> 3.21 inclusive, pend_flush 0.95 ->
1.01). The ticks start at another raster phase than before (the start-up's cycles changed: PR_TAB is built at the start,
the overlay loads differ), so the chunks wait for the beam differently; the traps stretch gained the same way. This phase
sensitivity is what the M8a beam-wait item is about.
