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
  (Measured anew in M8a part 3: 8.5 / 14.3 / 19.2 lines for 1 / 2 / 3 chunks, the model 3-4 lines too pessimistic.)

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

## M8a part 3: the beam wait (measured, change parked) (2026-11-02)

Status: measured; the scheduler variant below is built and verified but **parked** in PR #8 (MZPico/mz800pop#8,
branch perf/beam-wait) because it costs ~476 resident bytes (end_of_code 0x7870 -> 0x7B02, the low block -181) for
~1-1.5 %, and the next drawing work (kid rect split, fore-layer precompose, standing guard) needs that room. It is
to be rebased and merged when there is resident room; the measuring tool (tools/beamwait.py) comes with it.

A tick ends with pend_flush (sprite.asm): the chunks the object pass composed (at most 3, the
compose buffers) go to VRAM back to back, each started only when the beam cannot overtake it (d, the lines until the
beam next reaches the chunk's top, at least h (k - 1) + BEAM_MARGIN) nor has just passed it (d < 312 - BEAM_GUARD), and
the chunks that show a character change in the same frame. A flush with more chunks than buffers flushes mid-pass too.

### Measured (tools/beamwait.py in PR #8: tracepoints at pend_flush, each beam read, pf_blit1, the copy kernel's start and end, the
VBLN interrupt; raster lines from the GDG tick counter, 1136 a line)

pend_flush's time outside the copies, frames per tick (perfcheck's stretches; the copies themselves are unchanged:
walk 0.58, door 1.29, fight 0.80 frames a tick):

| Stretch | Now (main): setup / waiting / latency / one at a time = total | Parked variant: setup / waiting / latency / one at a time = total |
|---|---|---|
| walk_level1 30-60 | 0.028 / 0.125 / 0.058 / - = 0.216 | 0.065 / 0.056 / 0.024 / - = 0.150 |
| level door 203-207 | 0.025 / 0.470 / 0.083 / - = 0.584 | 0.091 / 0.082 / 0.036 / - = 0.215 |
| room change 89 | 0.016 / 0.402 / 0.040 / - = 0.461 | 0.047 / 0.361 / 0.017 / - = 0.428 |
| walk_level1 190-260 | 0.022 / 0.244 / 0.071 / - = 0.342 | 0.078 / 0.055 / 0.030 / - = 0.168 |
| gate_push 200-260 | 0.005 / 0.034 / 0.025 / - = 0.065 | 0.025 / 0.016 / 0.012 / - = 0.053 |
| traps_b1 0-300 | 0.027 / 0.121 / 0.056 / 0.007 = 0.215 | 0.065 / 0.054 / 0.023 / 0.004 = 0.151 |
| fight1 60-160 | 0.029 / 0.249 / 0.056 / 0.141 = 0.478 | 0.067 / 0.256 / 0.024 / 0.066 = 0.418 |

(setup: entry to the first beam read; waiting: to the read the copy started from; latency: from that read to the first
copy; one at a time: the whole of the flushes that gave up on the same-frame copy. After a frame boundary is crossed
the rest of the stretch starts at another raster phase, so single numbers move by a few per cent; the per-flush causes
below are what the change addresses.)

What makes a tick wait (each failing try classified with the old pf_seq's rules):
- **The sorted order.** Chunks were copied top first. In a walk tick the two torch chunks (2x18 at row 68) come first and
  the kid's chunk just below them (3-6 x 26-41 at rows 78-93) would start ~75 lines after the read, too late: the beam
  reaches its top first and overtakes the copy ("need" fails on the third chunk). Copying the kid's chunk first, then the
  torches, fits at once in most of those cases. Failing tries by reason over walk 190-260: need 590 (471 on the top
  chunk, the beam about to reach it; 119 on a later one), guard 117 (the beam just past a chunk's top).
- **The tries were slow.** A try recomputed every chunk's need and duration (mul8) after its beam read: ~4,000 T for 3
  chunks, so the first copy started 19.2 lines after the read (14.3 for 2 chunks, 8.5 for 1) and a wait was spent in
  steps of 6-11 lines. The latency model 6 n + 5 lines was 3-4 lines too pessimistic: the real start came earlier than
  predicted (by -7.3 to +2.5 lines), which the guard had to absorb and the margin did not need.
- **Fights.** The kid's and the guard's chunks are wide (8x40, 7x40 side by side, plus a 2x18): their copies take
  250-360 lines, so they can only all show in the same frame when the copy starts right after the beam has passed their
  tops (~200 lines of waiting a flush), and 9 of 116 flushes found no such moment in 1-2 frames and fell back to one at a
  time (0.14 frames a tick).
- No copy was torn in any stretch (measured from each copy's start and end), and the margins were larger than needed:
  the beam passed a chunk's top at least 11.3 lines before its first row was written, and its next pass came at least
  19.4 lines after the copy's catch-up point.

### The parked variant (PR #8)

- The chunk values (the line of the top row, need, duration, the character flag) are computed once per flush (pf_prep);
  a try is one beam read and a few compares per chunk: the first copy starts 5.2 / 7.0 / 9.1 lines after the read for
  1 / 2 / 3 chunks, modelled as PF_LAT0 + PF_LATN n = 3 + 2 n (error now -2.9 to +5.7 lines, median +0.9).
- pf_try tries the sorted order first, then the other orders (all 6 of 3 chunks), each against its own beam read.
  **Why the screen stays the same:** two chunks that overlap keep the order the old code copied them in (by top row, the
  earlier entry on a tie: pf_sort's stable order; pf_ovl marks the overlapping pairs, an order that swaps one is never
  tried), and chunks that do not overlap write disjoint VRAM, so after the flush every byte holds what the old order left
  there. Only when the copies happen changes. The sort became an index sort (pf_idx); PEND_LIST is sorted in place only
  before the one-at-a-time fallback, which is unchanged.
- BEAM_GUARD 12 -> 8, BEAM_MARGIN 20 -> 16: with the accurate latency the guard keeps the old worst case (the beam passes
  a chunk's top >= 9.8 lines before its first row is written), and the need side keeps >= 8.1 lines beyond the measured
  worst case (an interrupt between the read and the copy, or inside the copy, adds up to ~5 lines). Both constants are
  for the real-hardware check of M8: the copy speed is the emulator's VRAM wait-state model.
- Code: src/m4/flush.asm (main block, 658 bytes: pend_flush, pf_prep, pf_seq, the order tables); the old pend_flush,
  pf_all and pf_seq left the low block (181 bytes net). Free resident would be main 912 -> 254, low 115 -> 296: the reason it is parked.

Checks with tools/beamwait.py over the whole of walk_level1 0-261, gate_push 0-261, traps_b1 0-299, fight1 0-161: no torn
copy, no together-flush whose character chunks first show in different frames, no overlapping pair out of its order.

### The variant's gains (tools/perfcheck.py, 3 runs each; its runs were identical, main's door step varied 17.88-18.09)

| Stretch | Main (median) | Parked variant | Change |
|---|---:|---:|---:|
| normal tick (walkthrough 30-60) | 6.20 | 6.13 | -1.1% |
| level door step (walkthrough 203-207) | 17.88 | 17.72 | -0.9% |
| room change (walkthrough 89) | 106.92 | 106.89 | 0 |
| walkthrough 190-260 | 11.00 | 10.83 | -1.5% |
| gate (gate_push 200-260) | 5.13 | 5.06 | -1.4% |
| traps (traps_b1 0-300) | 6.03 | 5.97 | -1.0% |
| fight (fight1 60-160, guard on) | 9.13 | 9.07 | -0.7% |

### Tried and measured, not kept

- **A feasibility test per order** (pf_fits: the character chunks of an order can show in the same frame at some beam
  position exactly when max a_i - min (a_i - need_i) <= 311 - BEAM_GUARD, a_i = the top line minus the chunk's start
  offset), to give up on hopeless fight flushes after one frame instead of two: fight 9.06 -> 9.04 (0.2 %) for ~150
  bytes; run at every flush it cost more than it saved (walk +0.04 frames). Dropped.
- **Copying a chunk without a character on its own** while the others wait (simulated on the recorded flushes): worse
  than the order search (walk 190-260 0.10 instead of 0.18 frames a tick saved), the greedy copy commits too early.
- **No beam wait at all** (copy at once in the sorted order, the setup kept; a test build, never committed): normal 6.05,
  door 17.60, room change 106.51, walk 190-260 10.74, gate 5.04, traps 5.90, fight 8.73, i.e. -0.4 to -1.3 % against the variant
  and -3.7 % in the fight, and ~0.07 frames a tick more without pf_prep. Too small for a tearing switch like
  PACE_MODE; not built.

### What is left

- Fights: the same-frame rule over all character chunks (the kid's and the guard's chunks are tied together) is most of
  the remaining wait (0.26 frames a tick + 0.07 one at a time). Tying only the chunks of one character together would
  cut it (simulated: -0.075 frames a tick without the rule at all), but it changes what the screen shows between two
  frames; the kid rect split (smaller, better placed chunks) would help the same flushes.
- The setup (0.07 frames a tick) is now the largest part in walks: the index sort, the overlap tests and pf_prep's
  multiply could be trimmed by ~0.02-0.03.
- Using the wait for other work: after pend_flush the tick only draws the hit points and the texts, and the next tick's
  logic must not start before tick_done (the harness reads VRAM there), so there is nothing to overlap with it today.

## M8a part 4: the kid area (measured) (2026-11-02)

Status: **measured, not built.** The M8a list item 7 "old/new rects kept apart" would save under 0.01 frames a tick:
a character's old and new rects (the bounding boxes of his objects last tick and this tick) nearly coincide, so their
union box is within ~2 % of the exact union area, and a split adds chunks.

How the kid's area is drawn today: people_place (overlay.asm, block 2) builds per character U = old rect U new rect
(pp_group), joins the kid's and the guard's U into one box when they meet, and puts them on the dirty list;
obj_rect_run (sprite.asm) cuts each dirty rect into compose chunks of at most 8 bytes x 64 rows starting at its left
edge; obj_chunk composes a chunk (the shadow background or the background-only picture, the flames and falling
floors, people_chunk = the overlay ops and the sprites, lay_fore_rect = the fore pieces), and pend_flush copies them.

### Measured (tracepoints, a scratch tool in the worktree's build/, not committed)

Tracepoints at draw_objects and its return, people_place's end, char_fetch and its return, pp_rects (the old rects,
SD_OXB of the kid and the guard) and after the two pp_group calls (U and the new rects), do_m1 (the dirty list),
obj_chunk (CRX..CRH), oc_free, oc_base, oc_kid, oc_fore, oc_rec, the return from obj_chunk, pf_blit1 and its returns.
CPU cycles, frames per tick over perfcheck's spans (the copies inside a mid-pass flush are counted as copy, not setup):

| Stretch | place (of it fetch) | chunk setup | background | flames, mobs | people (overlays + sprites) | fore | copy | flush waiting etc. | object pass |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| walk_level1 30-60 | 1.225 (0.899) | 0.075 | 0.627 | 0.161 | 0.447 | 0.697 | 0.584 | 0.208 | 4.024 |
| fight1 60-160 | 2.064 (1.547) | 0.143 | 0.964 | 0.177 | 1.202 | 1.094 | 0.797 | 0.403 | 6.844 |
| traps_b1 0-300 | 1.031 (0.730) | 0.061 | 0.612 | 0.189 | 0.479 | 0.321 | 0.558 | 0.219 | 3.470 |
| gate_push 200-260 | 0.250 (0.004) | 0.013 | 0.060 | 0.182 | 0.002 | 0.173 | 0.225 | 0.078 | 0.983 |

(chunk setup includes recording the chunk; background = the shadow restore, a torch chunk's cached picture or nothing
inside a flame; the gate stretch has the kid outside the drawn room, its object pass is the torches and the gate.)

The dirty rects (x in bytes, y in rows; area = bytes x rows):

| Stretch | chunks a tick | dirty area a tick | kid U area | kid exact old U new | ticks with old/new disjoint / overlapping < half |
|---|---:|---:|---:|---:|---:|
| walk_level1 30-60 | 3.17 | 264 | 174 | 170 | 1 / 2 of 30 |
| walk_level1 0-261 | | | 177 | 174 | 2 / 5 of 257 |
| fight1 60-160 | 3.15 | 450 | 222 (guard 164) | 219 (guard 163) | 0 / 0 of 100 (guard 0 / 0) |
| traps_b1 0-300 | 3.06 | 245 | 161 | 159 | 0 / 6 of 298 |

The kid moves a few pixels a tick and his frames have similar boxes: old and new overlap almost entirely, and the
union box is the exact union but for a few corner bytes. The disjoint cases are the few ticks where the image jumps
(a turn, a frame with a different box).

### Per-chunk cost (least squares over the chunks without the 2 x 18 torch chunks)

The background costs ~640-1,010 T a row plus ~37 T a byte, fore ~16 K a chunk plus ~60-95 T a byte in fights, the copy
~300 T a row plus ~64 T a byte (k = 1.31 + 0.28 w lines a row): a chunk costs roughly 31 K + 1,140 h + 160 w h T
including its share of the sprite drawing. The per-row part dominates: a 1-byte-wide chunk of 35 rows still costs
~25 K in the background and up to ~55 K in lay_fore_rect.

With that model, the cheapest cover of each character's old U new (the box; old and new apart; one of them plus the
other's bands outside it) against the box (frames per tick):

| Stretch | kid: box -> best cover | guard: box -> best cover | ticks where a split wins |
|---|---:|---:|---:|
| walk_level1 30-60 | 1.446 -> 1.445 | | 1 of 30 |
| walk_level1 0-261 | 1.475 -> 1.472 | | 10 of 257 |
| fight1 60-160 | 1.720 -> 1.713 | 1.222 -> 1.222 | 12 of 200 |
| traps_b1 0-300 | 1.380 -> 1.380 | | 0 of 298 |

Joining the kid's and the guard's boxes when they meet (fight1 60-160, 43 ticks): 1.436 frames a tick against 1.401 for
the best separate cover (the kid's box and the guard's bands outside it), ~0.035 a tick; the join usually makes two
8-wide chunks where separate boxes make three (8 + 1 + 8), so it is mostly right.

### Estimate and decision

- Gain: <= 0.007 frames a tick keeping old and new apart (walking, traps, fights), ~0.035 more in fights from not
  joining the two characters: far under the ~0.2 frames a tick the change would need.
- Cost (a sketch): in pp_group, the old and new rects onto the dirty list separately when they are disjoint (or
  overlap little) instead of U, with oc_kidtouch's and the join's use of PP_KU kept: ~40-60 bytes in block 2 (238 B free);
  the band cover ~120-150 bytes.
- Decision: not built (gain / cost far below the rule of thumb: >= 0.2 frames a tick on walks or fights at < 250 bytes).

### What the numbers point to instead

- **The fetch** (char_fetch: the image from the RAM disk, shifted and mirrored) is the largest single part of the
  object pass: 0.90 frames a tick walking, 1.55 fighting (two characters and swords), more than any compose step. The
  pre-mirrored kid pack (M8a item 7's second half, RAM-disk budget) and a shift-free path for byte-aligned x are
  the levers.
- **Narrow tail chunks**: a box 9-11 bytes wide becomes an 8-wide chunk plus a 1-3-wide one, which pays the full per-row
  and per-chunk cost (~70-90 K T) for a few bytes: ~0.12 such chunks a tick in fight1 60-160 (~0.13 frames a tick),
  ~0.03 walking. Removing them needs chunks wider than 8 bytes when they are low (the buffers hold 512 bytes a plane:
  e.g. 12 x 42), i.e. a compose row stride other than 8 in restore_shadow, the piece layers, spr_draw and the copy
  kernel: a large change, not sized here.
- **Fore** (lay_fore_rect) costs ~16 K a chunk before it lays anything in fights and is the largest compose step walking
  (0.70 frames a tick): the fore pieces hidden behind the kid (item 7) and the per-room pre-composed fore layer (M8a
  list item 2) address it.
- The background's per-row cost (~640-1,010 T a row a chunk: RAM-disk seeks per row) is M8a item 3 (the shadow stored
  chunk-major).

## M8a part 5: the fore layer (measured) (2026-11-02)

Status: **measured, not built.** The M8a list item 2 (compose each room's fore layer once at room entry into the RAM
disk as mask + data and apply it in one masked pass per chunk instead of laying the fore ops every tick) fails all three
budgets: it gains under 0.1 frames a tick walking, needs up to ~31-38 KB of RAM disk for the largest room (the largest
free piece is 11.1 KB) and would add ~10-30 frames to a room change. Its only sizeable gain, in fights and in chunks
without fore pieces, is the op scan, which a faster scan gets without a precomposed layer (below).

What lay_fore_rect does today (room.asm, called by obj_chunk after the people): the candidate tile columns C0..C1 from
the chunk (CRX - 6 .. CRX + CRW - 1, in tiles), then rr_table's walk over 4 tile rows (rows 2, 1, 0 and the row above) x
those columns: per cell the tag, its slice count in SL_CNT, the slice's row range against the chunk, then rec_lay on
each op of the slice (reject by box, else lay_piece16: mode 0 copy, mode 1 masked).

### Measured (tracepoints at oc_fore, lay_fore_rect's return, the end of the OV_FORE list, rec_lay, rl_lay,
lay_piece16 and its return in rl_lay, tick_done with the fore op list; a scratch tool in the worktree's build/)

Frames per tick over the chunks that run lay_fore_rect (the torch chunks from the cache do not):

| Stretch | chunks a tick | lay_fore_rect | of it the scan | of it laying (rl_lay .. ret) | ops tested / laid a chunk | chunks laying 0 / 1 / 2 / 3 ops |
|---|---:|---:|---:|---:|---:|---|
| walk_level1 30-60 | 1.93 | 0.658 | 0.147 | 0.511 | 2.0 / 0.91 | 23 / 22 / 8 / 5 |
| fight1 60-160 | 2.79 | 1.073 | 0.246 | 0.827 | 1.6 / 0.62 | 105 / 174 / 0 / 0 |
| traps_b1 0-300 | 1.81 | 0.282 | 0.116 | 0.166 | 1.1 / 0.35 | 405 / 85 / 51 / 1 |
| walk_level1 190-260 | 3.47 | 0.228 | 0.215 | 0.013 | 0.1 / 0.02 | 239 / 4 / 0 / 0 |

(the kid's own fore overlays, OV_FORE, cost 0.002-0.006 frames a tick.)

- **The scan** costs ~4.4-6.3 K T a chunk: ~450-1,000 T of setup + ~280-340 T per cell visited (10.7-14.0 cells a chunk:
  all 4 tile rows x 3-4 columns, whatever the chunk's rows) + ~360-760 T per op tested. A chunk that lays nothing still
  pays ~3.7-5.4 K.
- **The laying** is per op, and per row: copy mode (pillar fronts 95, dungeon walls, floor fronts) ~4.0 K + 470 T a row
  + 55-90 T a byte (an op ~22-24 K T); masked (the fight room's pillar 2 x 60, palace pieces, 100) ~6.0 K + 660-690 T a
  row + 150-195 T a byte (~11-34 K T). The pieces laid: the pillar front 95 (73 % of the ops), the wall face (wall 10),
  floor fronts 43 / 73 / 74, the potion's 100.
- Fore ops of one chunk barely overlap: in the chunks with 2-3 ops the ops' clipped areas add up to 995 bytes x rows for
  a union of 900 (walk 30-60) and 4,256 for 3,940 (traps). A precomposed layer would lay the same bytes once more or less.

Per room (tools/popdata.py's renderer over the 340 rooms of levels 0-14, the fore ops and the palace's fore wipes, the
covered screen bytes = bytes x rows with any fore pixel): largest level 6 room 8 with 7,680 of the screen's 8,000 (the
palace walls), level 10 room 13 7,560; per level the largest 5,289-7,680; 94 % of the covered bytes are fully opaque.
Stored as 4 plane bytes (+ a mask byte where not opaque): 30.7-38 KB for the largest room; 105 (with masks) to 145 (opaque
without) of the 340 rooms would fit the largest free RAM-disk piece (page 4, 11.1 KB).

In a room change the room draw lays the room's fore ops in its own pass: 17.3-30.1 frames of the 91-107 (walk_level1:
46-86 fore ops laid, some twice across cells).

### Estimate and decision

- **Gain** (the cost model above; a lookup of the chunk's part of the layer at 1-2 K T in place of the scan, then one
  masked pass over the union of the chunk's fore bytes): walk 30-60 -0.02 to +0.01 frames a tick all masked, +0.07 to
  +0.10 if the format kept opaque bytes on the copy path; fight1 60-160 +0.18 to +0.22; traps_b1 0-300 +0.02 to +0.08;
  walk_level1 190-260 +0.12 to +0.17. Merging the ops is worth ~0.02-0.03; the rest is the scan replaced by the lookup.
  A masked pass over today's copy-mode pieces (pillars, walls: 150-195 instead of 55-90 T a byte) loses what merging
  wins, so the layer would need an opaque/masked run format per row.
- **Resident**: the lookup (per-room index by chunk position) and the run-format apply: ~180-250 bytes in main.
  **Overlay**: the compose at room entry (lay every fore op into a mask + data buffer, write it out): ~250-350 bytes in
  W1 (the room overlay has 86 free, i.e. a W1 overlay of its own).
- **RAM disk**: up to ~31-38 KB for one room (one room's layer, overwritten at the next room): does not fit the free
  pieces (~38 KB in total, 11.1 KB the largest); "not precomposed" would be the case for 195-235 of 340 rooms.
- **Room change**: the compose is the fore pass of the room draw once more into separate buffers (17-30 frames) plus
  writing ~3,000-7,700 bytes x 4-5 out (~4-11 frames); capturing the fore pieces during the room draw instead (laying
  into the separate buffers, then applying them to the compose chunk) still adds the apply and the write (~10-25 frames).
  Far over 5 frames.
- And the fore layer changes inside a room: spikes, chompers, loose floors, potions (their bubbles every tick) have fore
  ops that tile_regen replaces; each change would recompose that part.
- Decision: not built (rule: >= 0.2 frames a tick walking or fighting for < 250 resident bytes, fits the RAM disk, < 5
  frames per room change: fails all of the walking gain, the RAM disk and the room change).

### What the numbers point to instead

- **A faster fore scan** (the 0.12-0.25 frames a tick that are not laying): restrict the tile rows to those the chunk's
  rows can reach (a chunk of <= 64 rows meets at most 2-3 of the 4 rows' slices: about half the cells), and walk SL_CNT
  by pointer in the column loop (the tag and the count without the two tab_get calls) so an empty cell costs ~50 T
  instead of ~300. Estimated scan 4.4-6.3 K -> ~1.5-2 K T a chunk: walk 30-60 -0.08, fight -0.15, traps -0.06, walk
  190-260 -0.13 frames a tick, for ~40-80 bytes in main; rr_table also serves run_rect (tile redraws: door, gate,
  loose floor steps), which would gain the same per cell. Under the 0.2 rule on walks alone, but cheap; a candidate
  together with item 3 below.
- **The laying's per-row cost** (470 T a row copying, 660-690 masked: a chunk with the fight room's pillar pays ~21 K of
  its 34 K in per-row work): M8a list item 3 (per-row overheads of the piece layers).

## M8a part 6: the fore scan (2026-11-03)

Part 5 measured the fore pass (lay_fore_rect) and found its fixed part, the scan, at 4.4-6.3 K T a chunk: 450-1,000 T
of setup, ~300 T for each of the 11-14 tile cells it visited (all 4 tile rows) and 360-760 T for each op tested, so a
chunk that lays nothing still paid 3.7-5.4 K T. The scan is rr_table, which run_rect's tile redraws use too.

**The change** (src/m3/room.asm): rr_table walks the slice count table SL_CNT by pointer along each tile row instead
of two tab_get calls and a row x 10 lookup per cell: an empty cell costs ~35 T. A non-empty cell's slice rows are
tested in registers before the walk state is saved (a slice that misses the rect ~90 T). The slice tables share their
low byte (SL_START / SL_CNT on page 0x81, SL_Y0 / SL_Y1 on page 0x04); an assembly-time check guards that layout.
lay_fore_rect takes its bounds from rect_bounds and limits the columns to the rect's. The rows, columns and the order
of the ops laid are the same, so the pixels are: the full regression on the runners passed (all parts).

**Result:** the scan of a chunk 4.4-6.3 K T -> 1.7-3.0 K T; the main code 67 bytes smaller (end_of_code 0x7870 ->
0x782D). tools/perfcheck.py, medians of 3 runs each, main (f3c16d5) -> this:

| Stretch | main | fore scan | change |
|---|---:|---:|---:|
| normal tick (walkthrough 30-60) | 6.20 | 6.10 | -0.10 |
| fight (fight1 60-160) | 9.13 | 9.00 | -0.13 |
| traps (traps_b1 0-300) | 6.03 | 5.96 | -0.07 |
| walkthrough 190-260 | 11.00 | 10.70 | -0.30 |
| level door step (walkthrough 203-207) | 17.88 | 17.45 | -0.43 |
| room change (walkthrough 89) | 106.92 | 106.58 | -0.34 |
| gate (gate_push 200-260) | 5.13 | 5.11 | -0.02 |

Part 5's estimate was walk -0.08, fight -0.15: met. The tile redraws (doors, gates, loose floors) share the scan, so
the walkthrough and the door step gain more than the fore pass alone would. The baseline (tests/perf_baseline.json)
is lowered where the new median beats it; the room change and the fight keep their older, lower values.

## M8a part 7: standing characters (2026-11-03)

Status: **built.** A character who looks exactly as in the last drawn tick gets no dirty rect of his own: in fights the
guard stands still (en garde, waiting, lying dead) in 50-75 % of the ticks he is shown, and his chunks were composed and
copied again every tick for the same pixels. fight1 60-160 gains ~0.77 frames a tick (9.00 -> 8.23); walking is unchanged
(no comparison while no guard is shown).

### Measured (tracepoints at people_place, pp_rects (every slot's descriptor, PP_XD, PP_CL, PP_ORD, the overlay op
lists), do_m1 (the dirty list, PP_KU, PP_GU), obj_chunk, oc_kid, oc_fore, oc_rec and the return, pf_blit1 (the pending
entry) and its returns, char_fetch / cfdo / its return, VRAM read at every tick_done; a scratch tool in the worktree's
build/, not committed)

A character is "unchanged" when all his slots (the kid 0, 1, 6, the guard 2, 3, the splash 4 with its owner) have the same
visible flag, frame, chtab / mirror / shift, x, y, rect, clip, XOR offset and left clip as in the last drawn tick, in the
same room. Checked against VRAM: in every such tick of every script his rect's bytes outside the other dirty rects (the
other character's U, tile redraws, falling floors, torches) were the same as after the last drawn tick (0 exceptions in
5,300 ticks), so leaving his rect off the dirty list keeps the screen.

| Script (all ticks) | ticks | kid unchanged / shown | guard unchanged / shown | of them joined | compose + copy saved | chunks + copy, before -> after (built) |
|---|---:|---:|---:|---:|---:|---:|
| fight1 60-160 (perfcheck) | 100 | 5 / 100 | 62 / 100 | 9 | 0.79 | 4.38 -> 3.55 |
| fight1 | 344 | 11 / 343 | 197 / 263 | 40 | 0.70 | 3.82 -> 3.11 |
| fight2 | 344 | 13 / 340 | 125 / 184 | 43 | 0.78 | 4.16 -> 3.40 |
| fight3 | 344 | 13 / 324 | 177 / 244 | 40 | 1.18 | 4.46 -> 3.32 |
| fight_bump | 99 | 32 / 98 | 36 / 71 | 26 | 1.44 | 4.55 -> 3.06 |
| fight_chomper | 138 | 11 / 137 | 74 / 110 | 23 | 1.02 | 5.22 -> 4.19 |
| fight_drop | 339 | 20 / 338 | 71 / 276 | 49 | 0.49 | 5.57 -> 5.04 |
| fight_follow | 307 | 19 / 306 | 134 / 228 | 6 | 0.39 | 4.09 -> 3.69 |
| fight_killpush | 403 | 15 / 402 | 205 / 284 | 81 | 1.22 | 4.77 -> 3.60 |
| fight_leave | 166 | 24 / 165 | 22 / 98 | 8 | 0.54 | 4.46 -> 3.91 |
| fight_skill11 | 341 | 14 / 340 | 213 / 313 | 125 | 1.21 | 5.49 -> 4.16 |
| fight_skill5 | 340 | 39 / 339 | 112 / 303 | 90 | 0.64 | 5.32 -> 4.63 |
| fight_skill7 | 341 | 9 / 340 | 196 / 313 | 112 | 1.07 | 5.52 -> 4.45 |
| fight_spikes | 133 | 9 / 132 | 61 / 105 | 12 | 1.22 | 4.93 -> 3.78 |
| fight_unarmed | 157 | 97 / 156 | 89 / 129 | 6 | 2.24 | 4.23 -> 2.00 |
| level2_drop | 343 | 30 / 342 | 120 / 281 | 55 | 0.79 | 5.12 -> 4.21 |
| level2_fight | 354 | 16 / 353 | 201 / 313 | 117 | 0.85 | 4.69 -> 3.63 |
| walk_level1 (also 30-60, 190-260) | 316 | 0 / 286 | | | 0 | 2.45 -> 2.45 |
| traps_b1 0-300 (perfcheck) | 300 | 53 / 299 | | | 0.17 | 2.22 -> 2.05 |
| traps_b1 | 1498 | 161 / 1497 | | | 0.12 | 2.26 -> 2.14 |

(frames per tick over all ticks of the script; "saved" = the measured compose (background, people, fore, record) and copy
of the chunks inside an unchanged character's own rect; when the two characters' rects were joined, the joined box's
chunks less the other character's own U, from a per-chunk fit of the same run, ~22 K + 480 T a byte x row.)

- The fetch is no lever: char_fetch already keeps a slot's image while frame, chtab, mirror and shift stay (fight1 60-160:
  81 cached fetches cost 0.003 frames a tick; the 201 real ones 1.54). What a standing character still costs is the chunk
  work: in fight1 60-160 the guard's unchanged ticks spend 0.48 frames a tick composing (background 0.13, people 0.17,
  fore 0.18) and 0.08 copying; all of it can go, since nothing in the rect changed.
- The kid rarely stands in a fight (5-39 of ~340 ticks; fight_unarmed 97), never in the walkthrough, in 11-18 % of
  the traps ticks (standing between moves: traps_b1 0-300 -0.17 frames a tick).
- Unchanged-but-joined ticks: the other character's U alone covers the overlap, so the join is dropped.

### What was built (src/m4/people2.asm st_look, main block; overlay.asm pp_rects, block 2; sprite.asm sprite_forget)

- st_look (called from pp_rects) keeps, per slot of the kid (0, 1, 6) and the guard (2, 3), the descriptor bytes SD_DX
  .. SD_COMPOSE + 1 (visible flag, SD_LKEY / SD_LKEY2 = the image's frame, chtab, mirror, shift; the screen rect; the
  clip) and PP_XD (the shadow's XOR copy, the level 12 blink) from the last drawn tick (ST_KEY, low RAM 0x01CA, 50
  bytes), compares and replaces them. The rect and the image key fix x and y (the rect's clipped sides give them back).
  A slot invisible then and now is not compared; from the first byte that differs the rest is copied with LDIR (a
  walking tick pays ~1 K T for it by count: no change in perfcheck; the first byte-by-byte version cost 0.03-0.05
  frames a tick walking).
- A character is skipped only when, this tick and the last, there are no overlay ops (OV_NM, OV_NF: the tiles drawn
  again over a character depend on both characters' frames) and no hurt splash (slots 4, 5: their owner and draw
  order), and no room was drawn since (sprite_forget sets ST_OK: room changes, a new level, the upside-down flip, the
  cheat build's blind screen). The left clip (the shadow right of the level 4 mirror, the mirror image's clip) is fixed
  within a room.
- Then his U is not put on the dirty list and not joined with the other character's. PP_KU / PP_GU stay as they were:
  oc_kidtouch reads them, and tc_try must not take a torch chunk from its cache (the flame without people) where a
  standing guard is.
- What does not change the screen or comes with its own rect: the flash (palette register only), the other character
  (his U covers his old and new pixels, and the chunk draws everybody in it), tile redraws (dirty_from_dr), falling
  floors, torch flames, the bottom texts and hit point strips (outside the playfield).
- Cost: main +169 bytes (end_of_code 0x782D -> 0x78D6, 810 free), block 2 +19 (block2_end 0xEB11 -> 0xEB24, 220 free),
  low block +4 (end_of_low 0x1F8D -> 0x1F91, 111 free): 192 bytes; 51 bytes of runtime-only low RAM (0x01CA-0x01FC).
- VRAM after every tick is the same as before in all 18 measured scripts (the scratch tool's VRAM per tick, main's build
  against this one, 6,800 ticks), and the test suite's pixel checks pass.

perfcheck (tools/perfcheck.py, medians of 3 runs each, rebased; main = 11e43a4, with part 6's fore scan) main -> this:

| Stretch | main | this | change |
|---|---:|---:|---:|
| normal tick (walkthrough 30-60) | 6.10 | 6.10 | 0 |
| level door step (walkthrough 203-207) | 17.45 | 17.54 | +0.09 |
| room change (walkthrough 89) | 106.58 | 106.32 | -0.26 |
| walkthrough 190-260 | 10.71 | 10.73 | +0.02 |
| gate (gate_push 200-260) | 5.11 | 5.11 | 0 |
| traps (traps_b1 0-300) | 5.96 | 5.96 | 0 |
| fight (fight1 60-160, guard on) | 9.00 | 8.23 | **-0.77** |

Fights gain ~8.5 %. The first version compared every tick and cost a walking tick ~0.05 frames (6.10 -> 6.15) with no
guard on screen; st_look now returns at once while the guard's slot is not visible (the kid alone gains nothing, see
the traps below) and marks its snapshot stale (ST_OK), 14 bytes. The door step's +0.09 is within the raster-phase
spread of that stretch. The
traps stretch saves 0.17 frames a tick of chunk work but no tick time: most likely its ticks end waiting for the beam
over the traps' own chunks, which takes the saving back (not traced further). The fight baseline is lowered
8.99 -> 8.23; the others stay.

## M8a part 8: small items (2026-11-03)

Status: **three built, two measured and not built.** A pass over the candidates parts 4-7 left (narrow tail chunks, the
background restore's per-row cost) and over the per-routine profile after parts 6-7 for whatever is cheap per byte.
Each built item is its own commit. Walking 6.10 -> 5.72 frames a tick, fights 8.23 -> 7.73, for 123
resident bytes (main +42, low block +81).

### The profile after parts 6 and 7 (tools/profile.py, main 80c4945, frames per tick, the routine's own cycles)

| Routine | walk_level1 30-60 | fight1 60-160 | What it is |
|---|---:|---:|---|
| lay_piece16 | 0.66 | 0.39 | the piece layers (fore pieces, tile redraws, overlays; per piece ~4 K T of setup: M8a list item 3) |
| spr_draw | 0.39 | 0.77 | the sprites into the compose chunk (per cell ~260 T drawn, ~82 T empty, ~190 T a row) |
| char_fetch (+ shr_* kernels) | 0.34 (+0.55) | 0.60 (+0.80) | the image from the RAM disk, shifted and mirrored (~180 T a plane-row outside the kernels) |
| restore_shadow (+ inr_* chains) | 0.26 (+0.21) | 0.37 (+0.35) | the background from the shadow room (124 T a plane-row outside the INIs) |
| view_redraw + view_snapshot + vs_get | 0.20 + 0.09 + 0.16 | 0.18 + 0.09 + 0.17 | which tiles changed: 2 x 53 entries a tick, ~270-400 T each |
| blq_* (the copy kernels) | 0.43 | 0.53 | the chunk copies (pf_blit1) |
| k_get_tile, k_tbl, get_row_collision_data | 0.28, 0.10, 0.12 | 0.36, 0.14, 0.12 | kid / guard logic (M8a list item 6) |
| cmx_* | 0.11 | 0.36 | masked pieces combined from the RAM-disk port |
| lay_fore_rect | 0.05 | 0.20 | the fore scan (part 6) |
| tc_try | 0.13 | 0.04 | the torch cache lookup |

### 1. Narrow tail chunks (measured, not built)

Tracepoints at obj_chunk (the chunk and its dirty rect), its return, the mid-pass flushes, restore_shadow and oc_base,
pf_blit1 and its returns (a scratch tool in the worktree's build/, not committed), main 80c4945:

| Stretch | chunks a tick | dirty rects 9-11 wide: tail chunks a tick | their compose + copy | per tail chunk |
|---|---:|---:|---:|---:|
| walk_level1 30-60 | 3.17 | 0.033 | 0.037 + 0.006 frames a tick | 92 K T |
| fight1 60-160 | 2.49 | 0.06 | 0.044 + 0.012 frames a tick | 67 K T |

Part 4 counted ~0.12 tails a tick in fights (~0.13 frames); part 7 halved them (a standing guard's box is no longer
joined with the kid's). Merging a tail into a wider chunk still pays its bytes (~160 T a byte-row), so the gain is at
most ~0.03-0.05 frames a tick. Shifting the split does not help: the cost is per chunk and per row, and a 9-11 byte box
needs two 8-wide chunks however it is split. Wider chunks need a compose row stride other than 8 everywhere a chunk is
addressed (restore_shadow, the four piece-laying modes, spr_draw, spr_xor, the torch cache, the text overlay) and new
copy and INI kernels for widths 9-16: several hundred bytes. **Not built** (gain < 0.1 frames a tick).

### 2. The background restore's per-row cost (chunk-major shadow measured, not built; the row loop built)

Same tracepoints: the restore costs 0.469 frames a tick walking (37.7 rows a tick, 886 T a row of 4 planes) and 0.719
fighting (53.1 rows, 963 T a row). Per plane-row the loop spent 134 T besides the INIs (16 T a byte): the seek (ld b,d /
out (c),e / dec c / inc c) 24 T, the next shadow row (+40) 27 T, the call into the INI chain and its ret 27 T, the
compose row advance 27 T (also for full 8-byte rows, where it adds 0), the row counter in A' 29 T.

- **A chunk-major shadow** (one seek per chunk) removes at most the seek and the +40: 51 T a plane-row, 0.11 frames a
  tick walking, 0.15 fighting. But object chunks start at the dirty rect's left edge, any byte column: in a layout of
  8-byte strips an unaligned chunk crosses two strips (two runs a row, two seeks), and aligning the chunks to the strips
  gives every box that crosses a strip boundary one more chunk (~31 K T + 1,140 T a row, the cost of a narrow tail).
  shadow_write (room change, tile redraws) would write strips at about today's cost. **Not built.**
- **The row loop** (built, commit "restore_shadow: ..."): a jump into restore_shadow's own INI chain (10 T instead of
  27), the compose advance skipped for full rows (a patched jr, 12 T instead of 27), the row count in B' (exx / dec b /
  exx, 22 T instead of 29), the plane count in C', and the next plane's shadow address from the last one + 8000 instead
  of shadow_addr for each plane. 110 T a plane-row besides the INIs (95 for full rows). restore_shadow 0.47 -> 0.41
  frames a tick walking, 0.72 -> 0.62 fighting (tools/profile.py). Main +23 bytes.

### 3. The tile-change snapshot (built)

view_snapshot (before the tick logic) stored, and view_redraw (after it) compared, the 53 entries that can change the
room on screen (its 30 tiles, the left room's column 9, the row above, the row below) one by one, each through a
pointer table and vs_get (the tile byte, its modifier, a button's pressed state): ~0.45 frames a tick in every tick,
walking or fighting, for ~2 entries that change (the torch flames).

**The change** (src/m4/view.asm): both walk the entries as 6 runs of consecutive tile bytes (vs_runs: the room's 30,
the left room's 3 rows of column 9, the row above, the row below; a run without a room is skipped by both), copying or
comparing the tile byte and the modifier inline (~75-90 T an entry). The pressed state is kept only for the buttons on
screen, listed when the pointer table is built at a room change (VS_BTN, up to 8; levels 0-14 show at most 5; tiles
never become buttons, a button can only become debris, which the tile byte shows): a button pressed or released gets its
snapshot tile byte changed, so the compare takes it in its turn. An entry that changed goes through the old per-entry
code (vrd_one: the torch, gate, potion and tile cases, unchanged), in the same order as before. view_snapshot 0.18 ->
0.07 frames a tick, view_redraw's own part with vs_get 0.36 -> 0.12 (walk_level1 30-60; fight1 the same). Low block
+187 bytes of code; the 106-byte pointer table moves from the low block to runtime RAM after the snapshot (0xF58B), so
the low block grows by 81 bytes (end_of_low 0x1F91 -> 0x1FE2, 30 free).

### 4. spr_draw's row loop (built)

spr_draw kept the row's source and compose pointers in memory and reloaded them every row (~190 T a row: 33 rows a tick
walking, 62 fighting, with 126 / 281 cells). Now they stay in HL and DE (patched advances: the source (ow - px) * 4, the
compose from the row start + 8, since the last cell's inc e can wrap E), the row count in B', and inc l inside a cell
(the image buffers are 4-aligned): ~75 T a row, 18 T less a drawn cell. spr_draw 0.41 -> 0.35 frames a tick walking,
1.33 -> 1.21 fighting (inclusive). Main +19 bytes.

### Measured, not built

- char_fetch's row loop (~180 T a plane-row outside the shift kernels): the row counter in B' would save ~7 T, < 0.02
  frames a tick. The mirrored shift kernels (84 T a byte: the bit-reverse lookup, then the shift tables) would need a
  combined reverse-and-shift table per shift (4 KB).
- shadow_write's row loop (the room change): the same B' counter saves ~0.4 frames a room change.
- lay_piece16's per-piece setup (~4 K T) and per-row costs: M8a list item 3, not a small item.

### Result

Same pixels: VRAM after every tick identical to main's (80c4945) in 32 scripts (the 16 fight scripts of
tests/m6_scripts and 16 of tests/m4_scripts, walk_level1, traps_b1/9/39/40, gate_push, random1 among them; 12,882
ticks; a scratch tool), and the full regression on the runners (regress/small) passed.
Resident: main +42 (end_of_code 0x78D6 -> 0x7900, 768 free), low block +81 (end_of_low 0x1F91 -> 0x1FE2, 30 free),
block 2 unchanged (0xEB24); runtime RAM 0xF5AF-0xF5F4 (70 bytes, unused before) now holds the end of the pointer table.
VRAM is unchanged because every change is a faster loop over the same bytes in the same order: the same chunks, the same
pixels composed into them, the same tiles redrawn in the same order.

tools/perfcheck.py, medians of 3 runs each, main (80c4945) -> spr_draw -> + restore_shadow -> + the snapshot (this):

| Stretch | main | spr_draw | + restore_shadow | + snapshot (this) | change |
|---|---:|---:|---:|---:|---:|
| normal tick (walkthrough 30-60) | 6.10 | 6.04 | 5.95 | 5.72 | **-0.38** |
| fight (fight1 60-160, guard on) | 8.23 | 8.07 | 7.95 | 7.73 | **-0.50** |
| traps (traps_b1 0-300) | 5.96 | 5.90 | 5.85 | 5.63 | -0.33 |
| walkthrough 190-260 | 10.73 | 10.63 | 10.55 | 10.26 | -0.47 |
| level door step (walkthrough 203-207) | 17.54 | 17.47 | 17.24 | 17.06 | -0.48 |
| room change (walkthrough 89) | 106.56 | 106.25 | 106.16 | 106.05 | -0.51 |
| gate (gate_push 200-260) | 5.11 | 5.11 | 5.09 | 4.99 | -0.12 |

Per item (walking / fighting, frames a tick): spr_draw -0.06 / -0.16 for 19 bytes, restore_shadow -0.09 / -0.12 for
23 bytes, the snapshot -0.23 / -0.22 for 81 (the rule: >= ~0.1 on walks or fights for < ~100 bytes). The room change
gets no slower (-0.5). Walking is now 6.2 % faster, fights 6.1 %. The baseline (tests/perf_baseline.json) is lowered to
the new medians except the room change, whose baseline (105.92) is below this run's median.

## M8a part 9: the frame store (2026-11-03)

Status: **built** (RAM-disk tiers step 1, docs/ramdisk-tiers.md section 11; PLAN.md item 49). On a RAM disk of 1 MB and
more the kid's and the sword's most used (frame, mirror, shift) keys are generated once at the first game start with
today's spr_fetch into RAM-disk pages 8+ (a fixed layout computed at build time by tools/fstore.py); a stored key is
then a copy of the finished cell buffer (~300 T + 21 T a byte) instead of today's fetch (~63 K T on average). 512 KB:
no store, today's fetch. Resident 98 bytes (main +95, low +3).

### perfcheck, medians of 3 runs per size (frames a tick)

The base is design/ramdisk-tiers 1388c51 (= main cc72e14's game; it uses pages 0-7 only, so its speed is the same on
every size). The emulator gave the same value in all 3 runs of each case here.

| Stretch | base 512 KB | new 512 KB | base 1 MB | new 1 MB | base 16 MB | new 16 MB |
|---|---:|---:|---:|---:|---:|---:|
| normal tick (walkthrough 30-60) | 5.72 | 5.72 | 5.72 | **5.20** | 5.72 | **5.03** |
| fight (fight1 60-160, guard on) | 7.73 | 7.72 | 7.73 | **7.20** | 7.73 | **6.86** |
| traps (traps_b1 0-300) | 5.63 | 5.63 | 5.63 | 5.30 | 5.63 | 5.23 |
| walkthrough 190-260 | 10.26 | 10.26 | 10.26 | 10.06 | 10.26 | 9.69 |
| level door step (walkthrough 203-207) | 17.05 | 17.16 | 17.05 | 16.23 | 17.05 | 16.23 |
| room change (walkthrough 89) | 106.05 | 106.05 | 106.05 | 106.05 | 106.05 | 105.22 |
| gate (gate_push 200-260) | 4.99 | 4.99 | 4.99 | 4.99 | 4.99 | 4.99 |

512 KB is unchanged but for the level door step's +0.11 and the fight's -0.01, which are the measurement: with a
breakpoint stop at every tick_done instead of perfcheck's tracepoint (tools/emu.py collect, which runs the emulation
in 200-frame steps) the door step's ticks 204-207 are 19.40 / 15.21 / 14.93 / 19.08 frames in both builds; with the
tracepoint, base's tick 205 takes 14.74 (one frame-phase wait fewer), the new build's 15.21 as with breakpoints.
1 MB is 9 %
faster walking (5.72 -> 5.20) and 7 % in the fight (7.72 -> 7.20), 16 MB 12 % / 11 % (5.03, 6.86). The room change
does not get faster on 1 MB (it fetches the kid once; the room draw is the cost) and 0.8 frames faster on 16 MB. The
gate stretch has no fetches. tests/perf_baseline.json is measured at the tests' default size, **1 MB** (the INI's
`mr1r18_size`): it is lowered to the new 1 MB medians where they beat it (walk, door step, 190-260, traps, fight; not
the room change, 106.05 against 105.92, nor the gate, equal), in its own commit. tools/perfcheck.py now takes the
RAM disk's size from the emulator and compares with tests/perf_baseline_<size>.json when there is one:
perf_baseline_512K.json = the baseline before the store (today's game), perf_baseline_16M.json = the 16 MB medians
above (regress/fs2-512's perfcheck had failed against the 1 MB baseline: 4 stretches more than 5 % slower, i.e. the
store's gain).

### The fill (boot time)

tests/m8_fstore.py and an I/O count around fs_fill (frames of 71,136 T): **1 MB (class 1, 891 keys, 409,512 bytes) 774
frames = 15.5 s** (318,505 data-port reads, 442,910 writes); **16 MB (classes 1 + 2, 2,153 keys, 1,232,824 bytes)
2,250 frames = 45.0 s** (968,945 reads, 1,270,008 writes). At every boot from the floppy, on the loading screen
before the title ("PREPARING SPRITES" and the loader's bar; the boot clears the marker, so a store left in the RAM disk
is never trusted; later starts in the session find the marker): boot -> PRES 1 MB 1,666 frames = 33.3 s, 16 MB 3,150
= 63.0 s, 512 KB 815 = 16.3 s (tests/m5_boot.py; docs/ramdisk-tiers.md section 11 has the timeline). On MZPico with w wait
states on every port access the fill takes w x (data-port reads + writes) more: +10.7 / +31.5 frames a T of wait (1 MB / 16 MB).

### RAM-disk accesses per tick (tools/rdreads.py)

Counted by the emulator's I/O breakpoints (IORQ_R / IORQ_W on the ports, a `continue` action: they count every byte of
an INIR / OTIR and never stop), read at tick_done; the same stretches and setup as perfcheck. Reads = the data port
(0xEA); writes = the data port; addr = the address port (0xEB, one per seek); page = 0xE9. Per tick:

| Stretch | size | frames | reads | writes | addr | page | +1 / +2 / +3 T a read (frames a tick) |
|---|---|---:|---:|---:|---:|---:|---|
| walk_level1 30-60 | 512 KB (today) | 5.718 | 2,312 | 130 | 200 | 41 | 0.032 / 0.065 / 0.097 |
| | 1 MB | 5.199 | 2,416 | 130 | 200 | 42 | 0.034 / 0.068 / 0.102 |
| | 16 MB | 5.032 | 2,444 | 130 | 200 | 41 | 0.034 / 0.069 / 0.103 |
| room change (walk_level1 89) | 512 KB | 106.05 | 53,499 | 30,720 | 5,253 | 1,270 | 0.752 / 1.504 / 2.256 |
| | 1 MB | 106.06 | 53,500 | 30,720 | 5,254 | 1,271 | 0.752 / 1.504 / 2.256 |
| | 16 MB | 105.22 | 53,650 | 30,720 | 5,253 | 1,270 | 0.754 / 1.508 / 2.263 |
| fight1 60-160 | 512 KB | 7.719 | 3,086 | 144 | 275 | 50 | 0.043 / 0.087 / 0.130 |
| | 1 MB | 7.200 | 3,176 | 144 | 276 | 50 | 0.045 / 0.089 / 0.134 |
| | 16 MB | 6.863 | 3,237 | 144 | 275 | 50 | 0.045 / 0.091 / 0.136 |
| traps_b1 0-300 | 512 KB | 5.632 | 2,051 | 301 | 219 | 40 | 0.029 / 0.058 / 0.086 |
| | 1 MB | 5.301 | 2,142 | 301 | 219 | 40 | 0.030 / 0.060 / 0.090 |
| | 16 MB | 5.226 | 2,170 | 301 | 219 | 40 | 0.030 / 0.061 / 0.091 |

The store reads slightly more than today's fetch (+3-5 %: a stored entry has the empty extra byte column and a 7-byte
table slot + header that the image does not), so it does not make the game more sensitive to a slow RAM disk:
the per-tick cost of wait states is ~0.03-0.05 frames a T of wait in play (< 1 % of a 5-7 frame tick at 1 T, ~2 % at 3
T) and ~0.75 frames a T on a room change (0.7 %). Counting every port access (reads, writes, seeks), as the MZPico's
WAIT would stretch each one, adds 15 % in play and 70 % on a room change (the shadow write's 30,720 OUTs).

**Measured with wait states** (MZPico/mz800emu#2's `mr1r18_wait`, the emulator of PR #18 test/memdisk, 9ccd087;
POP800_RD_WAIT=N there, here a temporary INI with `mr1r18_wait` and the in-memory RAM disk): the counts are the same
at wait 0 and 1, and 1 T of wait on every port access costs, frames a tick:

| Stretch | 512 KB w0 -> w1 | 1 MB w0 -> w1 | 16 MB w0 -> w1 |
|---|---|---|---|
| walk_level1 30-60 | 5.718 -> 5.757 (+0.039) | 5.199 -> 5.233 (+0.034) | 5.032 -> 5.067 (+0.035) |
| room change | 106.05 -> 107.33 (+1.28) | 106.06 -> 107.33 (+1.28) | 105.22 -> 106.50 (+1.28) |
| fight1 60-160 | 7.719 -> 7.768 (+0.049) | 7.200 -> 7.240 (+0.040) | 6.863 -> 6.915 (+0.052) |
| traps_b1 0-300 | 5.632 -> 5.662 (+0.030) | 5.301 -> 5.331 (+0.030) | 5.226 -> 5.250 (+0.024) |

(= the access counts x 1 T, within the rounding of the per-tick mean; 2 and 3 T scale linearly.) The store's gain
(-0.5 / -0.7 frames a tick) is ten times the cost of a wait state.

### Same pixels

VRAM after every tick equal to the Python reference (tests/m4_game.py, the pixel sets) on 512 KB, 1 MB and 16 MB: the
full regression on the runners for each size, with the fill at boot and main merged (764c9ac; all 11 parts passed:
regress/fs5-512 run 41662255045, regress/fs5-1m run 41662249445, regress/fs5-16m run 41662260287; earlier runs had
found the cheat tree's size mismatch, m7_sound's loop margin and perfcheck's single baseline, all fixed); m5_boot (the floppy boot with the fill on the loading screen, against the harness),
m7_launch (a round trip against a direct start: the fill leaves main RAM as a start without it) and m8_fstore pass
locally on 1 MB (m8_fstore also on 512 KB and 16 MB).

## Gates and spikes: per-tick measurements (2026-11-03)

Status: **measured, nothing built.** The playtest of main 60e7a83 (1 MB, no waits): walking is fine, but the game slows
down visibly whenever the kid walks or runs while a gate opens or closes or spikes rise, anywhere. Measured on that
build at 1 MB (the INI's), and the main scenes again at 512 KB.

**Tools** (committed): tools/tickcost.py runs a script in the emulator (perfcheck's setup, a tracepoint at tick_done)
and in kidsim side by side, and labels every tick by what changed on the shown screen: `K`/`.` the kid moved / stood,
`G` a gate's visible bar position min(mod, 188) / 4 changed (`g`: only its modifier), `S` a spike's picture changed
(`s`: only its modifier: the 15 ticks the spikes stay out, 0x8F..0x81). `--scene` runs the four scripts of a scene and
compares them tick by tick; `--profile t,...` profiles single ticks; `--rects t,...` traces the tile regenerations,
dirty rects, rect runs and object chunks of single ticks. tools/trapscenes.py finds the scenes with kidsim only. It
tries every button whose gate is drawn on its screen and every spike tile, with the kid starting on or next to it and
a few run, walk and jump patterns, and keeps the one with the most ticks of kid motion plus a visible trap change before
a room change or death. It writes each scene as four tick-aligned scripts: **a** the kid moves + the trap animates,
**b** the same moves with the button or spike patched to floor, **c** the kid stands (after stepping off the button; on
the spike tile) + the trap, **d** c without the trap. So a - b is the trap's cost while the kid moves, c - d its cost
while he stands, and a - b - c + d what the combination costs above the sum of its parts. 11 scenes are in
tests/perf_scripts (levels 4, 7, 9, 10, 14, 2, 6, 8; the finder found 31 on levels 1-14). tests/m4_game.py --every 1
on six of the a scripts: 0 state diffs, 0 differing pixels.

### Per scene (1 MB, frames a tick, the ticks where the kid moves)

| scene | ticks | n | a: median / p90 / worst | b (walking alone) median | a - b median | c - d median | excess (n) |
|---|---|---:|---|---:|---:|---:|---|
| l02 open (the gate opens 4 rows a tick, then closes 1 a tick) | visible | 53 | 8.84 / 10.94 / 15.16 | 4.62 | 3.86 | 3.46 | +0.33 (53) |
| | not visible | 66 | 4.94 / 5.26 / 5.68 | 4.56 | 0.14 | 0.00 | +0.27 |
| l04 open (gate_push's gate, the left room's column 9) | visible | 53 | 11.01 / 13.94 / 26.91 | 4.95 | 6.18 | 6.34 | +0.11 (53) |
| | not visible | 66 | 5.01 / 5.89 / 6.11 | 4.93 | 0.16 | 0.00 | +0.10 |
| l04 through (the kid runs into the gate's column, col 0-1) | visible | 53 | 11.13 / 14.77 / 26.91 | 4.97 | | | +0.08; standing +0.28 |
| l07 open | visible | 47 | 10.42 / 13.54 / 25.94 | 5.01 | 5.35 | 5.29 | +0.16 |
| l09 open | visible | 46 | 13.68 / 19.18 / 21.93 | 6.03 | 5.00 | 5.00 | +0.04 |
| l04 drop (an open gate drops, then reopens) | visible | 51 | 12.94 / 15.46 / 20.49 | 5.96 | 6.71 | 9.29 (the drop) | +0.00 |
| l10 drop | visible | 50 | 11.48 / 18.54 / 29.35 | 5.05 | 5.95 | 9.88 (the drop) | +0.00 |
| l07 drop (room 19: a gate cycling on its own + spikes) | gate visible | 71 | 12.21 / 16.62 / 22.15 | 5.78 | 6.28 | 5.36 | +0.19 (44) |
| | gate + spike step | 5 | 18.66 / 22.15 / 22.15 | 12.21 | | | |
| l14 spike | spike step | 9 | 10.90 / 11.96 / 12.42 | 4.57 | 5.87 | (kid on the tile) | |
| | spikes held | 14 | 5.98 / 6.23 / 6.62 | 4.07 | 1.89 | | |
| l08 spike | spike step | 18 | 12.57 / 13.57 / 18.16 | 8.71 | 5.26 | | |
| | spikes held | 31 | 6.02 / 7.10 / 7.97 | 4.59 | 1.96 | | |
| l06 spike | spike step | 18 | 11.00 / 13.75 / 16.12 | 8.97 | 5.77 | 7.61 | +0.09 (5) |
| | spikes held | 28 | 6.26 / 6.94 / 8.05 | 5.22 | 1.29 | | |
| l02 / l04 / l09 spike (not committed) | spike step | 9-21 | 11.3-13.9 (medians) | | 2.4-7.1 | 5.0-7.0 | -0.06 .. +0.66 |
| | spikes held | 7-14 | 6.0-11.5 | | 1.7-2.0 | | |

Walking alone (b) is 4.0-6.0 in these rooms (perfcheck's walk: 5.20). An opening gate changes its picture **every
tick** (+4 rows) for ~47 ticks, a closing one every 4th tick, a dropping one every tick for 4-5 ticks (20-60 rows a
tick, +9-10 frames each). A spike cycle is 5 visible rising ticks, then 15 held ticks with no visible change (or for
as long as the kid stays on the spikes), then 4 visible retracting ticks. At 512 KB the increments are the same (l04
open a - b 6.33, l14 spike step 6.31 / held 2.03, l07 drop 6.0); only the kid's own part is 0.4-0.7 slower, as walking
is there. The frame store plays no part in the traps.

**The combination costs the sum of its parts.** On ticks where a's and c's trap are in the same state, a - b - c + d
is -0.06 .. +0.33 frames (+0.66 in one spike scene with the kid on the spike's own chunk). There is no super-additive
work. The kid's rect and the gate's bar column (bytes 0-4 of the screen for a left-room gate) do not overlap: even with
the kid at the gate his chunk starts at byte 5. The dirty rect does not grow into a whole column either. The game gets
slow because the trap's redraw costs 5-7 frames by itself, as much again as a whole walking tick. A kid running next
to an opening gate runs at 11 frames a tick, 4.5 ticks a second, for the ~47 ticks of the opening.

Tick by tick, l04 open (a | b | c), the opening (ticks 1-2 belong to the level start and cost the same in all four):
```
tick   3     4     5     6     7     8     9    10    11    12    13    14    15    16    23    31    39    40    46    47
a  12.97 12.51 12.74 12.62 15.42 12.49 12.02 19.33 12.13 13.94 11.37 11.57 13.94 10.97 14.39 13.75 13.17  9.42  8.88 13.69
b   4.74  4.99  4.98  4.99  4.97  4.99  4.99  5.10  4.63  5.02  4.31  4.61  5.02  4.25  5.60  4.72  4.07  4.64  4.32  5.45
c  12.97 12.51 12.74 12.62 15.42 12.49 12.29 19.06 11.83 15.18 11.42 10.97 13.42 11.40 13.77 12.63 12.69  8.55  8.69 13.16
```
The cost falls as the bars get shorter: 12.5 at modifier 12, 9 at 160. Every 8th tick costs +3 more (a beam / torch
phase). The closing, a: 98 13.23, 99 4.88, 100 5.89, 101 5.90, 102 10.49, 103 5.60, 104 5.84, 105 6.03, 106 9.52, ...,
110 9.09, 114 9.30, 118 9.29 (b is 4.0-5.7 throughout). l14 spike, a | b: rising (ticks 13-17) 11.66 11.33 12.42
11.96 10.90 | 5.99 5.59 5.35 4.89 3.95; held (19-32) 5.1-6.6 | 3.1-4.8; retracting (33-36) 10.44 9.97 8.94 9.38 |
4.17 4.10 4.57 4.38. l10 drop, a | b: 21.52 21.34 29.35 27.48 | 12.58 11.95 17.37 17.62 (the drop's 4 ticks, +9-12
each).

### Where a visible step goes (tools/tickcost.py --profile / --rects, inclusive frames)

| | gate opening at 48 (l04 c 13) | gate opening at 156 (c 40) | gate closing 184->183 (c 102) | spike step 2->3 (l14 a 15) | spikes held (l14 a 20) |
|---|---:|---:|---:|---:|---:|
| the tick / the same tick without the change | 11.42 / 4.53 | 8.55 / 4.53 | 8.43 / 4.53 | 12.42 / 5.35 (b) | 6.13 / 4.12 (b) |
| dirty rect (bytes x rows) | 4 x 56 | 4 x 29 | 4 x 23 | 6 x 27 | empty |
| tile_regen (2 for a gate, 3 for a spike) | 1.36 | 1.12 | 1.11 | 1.61 | **1.58** |
| run_rect (shadow only): pieces laid | 4.14: 14 | 2.54: 10 | 2.25: 10 | 3.17: 13 | - |
| of it lay_piece16 (the masked pieces' cmx_4) | 3.12 (0.82) | 2.18 (0.48) | 2.01 (0.40) | ~2.4 (1.19) | |
| of it fill_black + shadow_write | 0.50 + 0.65 | 0.25 + 0.35 | 0.20 + 0.28 | 0.28 + 0.38 | |
| the object pass: the rect's own chunk + copy (+ the beam wait in pend_flush) | ~1.3 | ~0.3 | ~0.4 | +1.75 (+1.13 of it the spikes' fore pieces, laid in the kid's chunk and again in the rect's) | +0.4 (the spikes' fore pieces over the kid) |

The RAM-disk reads are inside the lay pass (the masked pieces, cmx_4) and the shadow write. The beam wait is small
(pend_flush +0.5 at most). The kid's and the guard's own redraw do not change with the trap (people_place and
char_fetch cost the same).

### Repeated work found

1. **Spikes held: 15 ticks a cycle of regenerating three tiles for nothing.** Every modifier change of a spike goes
   through tile_redraw (view.asm vrd_one has no spike case), which regenerates the tile, its right neighbour and the
   tile above-right (1.58 frames). The regenerated ops are identical and the dirty rect is empty: the picture depends
   on spike_frame(modifier) only (room.asm dta_spike, dtar_spike, dtf_spike; 0x81-0x8F all give 5). While the kid
   stands on spikes they stay out and this repeats every tick. a - b on these ticks: 1.3-2.0 frames.
2. **A spike step regenerates the above-right tile too**, which draws nothing from a spike (draw_tile_anim_topright
   reads only a gate below-left): one of the 3 tile_regens (~0.5 frames) on every visible spike tick.
3. **A gate step re-lays the whole bar column**, top to bottom (4 x 23-72 bytes, 10-14 pieces), for a 1-row (closing)
   or 4-row (opening) move. It also regenerates both tiles' op lists (1.1-1.4 frames) although only the bar records' y
   and the frame slice change. The ticks without a visible change cost nothing any more (M8a part 2).
4. **A spike step under the kid composes the overlap twice.** The kid's chunk and the dirty rect's chunk overlap (l14
   tick 15: 16,85 8 x 34 and 16,97 6 x 27); both lay the spikes' fore pieces and both are copied. For gates this does
   not happen (no overlap, even with the kid at the gate).

Not found: a gate redrawn without a visible change, a whole-column or full-screen redraw, the kid redrawn twice.

### The speed to aim at

SDLPoP runs gates and spikes on its ordinary ~12 ticks a second. Our tick is at least 4 frames (12.5 a second) and
walking takes 5.2 (9.6 a second). For a gate or spike tick to look like walking, its extra cost has to be about 0.5
frames or less (within 10 % of walking). Today it is 5-7 (a gate or spike step), 9-12 (a dropping gate) and 1.3-2
(spikes held).

### Candidate fixes (not built; pixels must stay identical, the logic tick-exact)

| # | fix | gain (frames a tick) | cost | effort / risk |
|---|---|---|---|---|
| 1 | vrd_one: a spike whose spike_frame is unchanged draws nothing (as vrd_gate does for gates) | held ticks -1.6 (6.0 -> ~4.4: walking plus the inherent ~0.3 of the fore spikes); 15 of a cycle's 24 ticks, and every tick while the kid stands on spikes | ~14 B, low block (27 free) | hours / low |
| 2 | spike redraw without the above-right regeneration | visible spike ticks -0.5 (9 of 24) | ~10 B | hours / low |
| 3 | spike records patched in place (3 records: own back spikes_fram_left, own fore spikes_fram_fore, the neighbour's spikes_fram_right; op_patch with one dr_run at the end), regenerating only for frames 0 <-> 1 and 9 -> 0 (no record there) | visible spike ticks -1.0 more on 7 of 9 (a step ~11.5 -> ~10 together with 2) | ~60-90 B (main has 673 free, or block 2) | 1-2 days / medium (record extents, slice tables) |
| 4 | one chunk for the kid's box and an overlapping tile-redraw rect | spike steps under the kid -0.5..-0.9 (estimate: the overlap's restore, fore pieces and copy) | ~50-100 B | days / medium (chunk order, beam scheduling) |
| 5 | gate: the bar records' y / count and the frame slice patched in place instead of 2 x tile_regen (PLAN M8a list item 1, "records patched in place"); regenerate only when the slice count changes | -1.1..-1.4 on a step without a count change: closing ~-1.2 a visible step, opening ~-0.6 a tick (every 2nd tick changes the count) | ~100-150 B | days / medium-high |
| 6 | gate column shift: scroll the bar stack by the step in the shadow and in the kept compose buffer (the slices are blit_copy, opaque), then lay only the frame slice, the bottom piece and the revealed rows; the full redraw when a person overlaps the column | -2..-3 a visible step (the lay pass 1.9-3.1 plus the fill, against ~0.5 for the scroll) | ~200-300 B (an overlay: 21 T a byte to load, ~0.07 frames) | a week / high |
| 7 | lay_piece16's per-piece setup (~4 K T a piece; M8a list item 3) | -0.6..-0.8 a gate step (10-14 pieces); also spike steps, door steps and room changes | main | days / medium |

Ranked by gain per effort: **1** (by far the cheapest; held spikes are the most common spike ticks), **2**, then **5**
and **3** (the regenerations, ~1 frame each on every visible step), **7** (general), **6** (the largest single gain
for gates, and the most work) and **4**. With 1-3 a spike cycle would cost ~+4.5 on 9 ticks and ~+0.3 on 15 (from +6
and +1.8). With 5 + 6 a gate step would cost ~+1.5-2 instead of +5-7: a kid running past an opening gate would take ~7
frames a tick instead of 11. (Not proposed: drawing fewer ticks, PACE_MODE 1 of M8a part 2, which the user decided
against.)
