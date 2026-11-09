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

## M8a part 10: the frame store's generator (2026-11-03)

Status: **built** (RAM-disk tiers step 2, docs/ramdisk-tiers.md section 12; PLAN.md item 51). The frame store's fill
(1 MB and more, at every floppy boot on the loading screen) no longer makes each key with spr_fetch: src/m4/fsgen.asm
reads each image once per mirror, straight at its lowest stored shift, makes every further shift by shifting the
buffer one more bit (SLA / RL, 23 T a byte) and writes each stored variant with OUTI (16 T a byte). Same layout,
marker, bar and lookup; the play-time speed is unchanged (no resident code changed, perfcheck as part 9).

Measured before building it (a prototype on single images): **46 T an output byte with all 16 variants of an image
stored** (estimate ~50, ramdisk-tiers section 7); with the real masks (3.8 of a mirror's 8 shifts stored on average,
spread out) the fill steps ~0.95 buffer bytes per stored byte: 66 T an output byte at first (shift 0, then a step a
shift), 61 after reading at the lowest stored shift and the faster table clear.

| | step 1 | step 2 | |
|---|---:|---:|---|
| 1 MB fill (class 1, 409,512 bytes) | 774 frames = 15.5 s | **351 frames = 7.0 s** | 2.2x |
| 16 MB fill (classes 1 + 2, 1,232,824 bytes) | 2,250 frames = 45.0 s | **933 frames = 18.7 s** | 2.4x |
| boot -> the title's step a, 1 MB (tests/m5_boot.py) | 1,886 = 37.7 s | 1,482 = 29.6 s | |
| boot -> the title's step a, 16 MB | 3,370 = 67.4 s | 2,068 = 41.4 s | |
| boot -> the title's step a, 512 KB (no fill) | 1,035 = 20.7 s | 1,053 = 21.1 s (#20's read-speed check) | |

Profile of the 1 MB fill (frames): the steps 131, the OUTI writes 93, the image reads 87, the entries' seeks and slots
12, the table clear 11 (now 7), making the row code 7. Not built: a plan per mirror that reloads at a later stored
shift instead of stepping over a gap (the model: -6 frames on 1 MB, -10 on 16 MB, for ~100 more bytes of an overlay
area that has 194 bytes left in the cheat build).

Wait states (MZPico): every port access 1 T longer (mr1r18_wait = 1, tests/m8_fstore.py with POP800_RD_WAIT=1) costs the fill **+7.1 frames on 1 MB, +20.7 on 16 MB** (step 1: +10.7 / +31.5): the generator reads each image once per mirror instead of once per key, so w wait states add w x 0.14 s (1 MB) / w x 0.41 s (16 MB).

Same pixels: tests/m8_fstore.py checks every entry against tools/fetchmodel/prebuild.py's generator (byte-identical to
the kernel) on 1 MB and 16 MB: all 891 / 2,153 entries equal, the key table and marker as tools/fstore.py computes
them. The full regression on the runners at 512 KB, 1 MB and 16 MB at 40332ec passed, all 11 parts each (regress/fsgen-512 run 41712562421, regress/fsgen-1m run 41712557377, regress/fsgen-16m run 41712567946); locally m5_boot (512 KB, 1 MB, 16 MB), m7_launch (1 MB) and the smoke tier.

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

## M8a part 11: spikes (2026-11-03)

Status: **built.** The first two fixes of the gates-and-spikes measurement ("Gates and spikes: per-tick
measurements", candidate fixes 1 and 2; its tools tools/tickcost.py, tools/trapscenes.py and tests/perf_scripts, on main
since #24, measured before and after). view.asm vrd_one sends a spike's modifier-only change to spike_redraw
(src/m4/spike.asm, main block), the way vrd_gate handles gates (M8a part 2 A):

1. **Held spikes draw nothing.** The spike's picture depends on spike_frame(modifier) only (room.asm dta_spike,
   dtf_spike of its own tile, dtar_spike of its right neighbour); when the old and the new modifier give the same frame
   (the 15 ticks 0x8F..0x81 that the spikes stay out, and every tick the kid stands on them, 0x8F again) nothing is
   regenerated or laid.
2. **A spike step regenerates only the tiles that draw it**: its own tile and its right neighbour (column < 9); for a
   spike in the left room's column 9 our column 0 only; for the above room's row 2 its tile only (as tile_redraw did);
   for the below room's row 0 nothing (draw_tile_anim_topright reads only a gate, draw_tile_topright no spike
   modifier). tile_redraw's third regeneration, the tile above-right, and for a left-room spike the second
   tile_redraw of the row above, are gone.

Resident: low block +5 bytes (the dispatch in vrd_one: end_of_low 0x1FE5 -> 0x1FEA, 22 free), main +60 (spike.asm:
end_of_code 0x795F -> 0x799B, 613 free). The Python reference renders the room from the level state, so it has no
redraw decision to keep in step (as for gate fix A).

### Per scene (1 MB, frames a tick, the ticks where the kid moves; tools/tickcost.py --scene, median / p90 / worst)

| scene | ticks | n | before | after | b (walking, after) |
|---|---|---:|---|---|---:|
| l14 spike | spikes held | 14 | 5.98 / 6.23 / 6.62 | **4.16** / 4.85 / 4.91 | 4.07 |
| | spike step | 9 | 10.90 / 11.96 / 12.42 | 10.44 / 11.46 / 11.70 | 4.57 |
| l08 spike | spikes held | 31 | 6.02 / 7.10 / 7.97 | **4.13** / 5.06 / 6.01 | 4.02 |
| | spike step | 18 | 12.57 / 13.57 / 18.16 | 10.91 / 12.55 / 17.16 | 7.65 |
| l06 spike | spikes held | 28 | 6.26 / 6.94 / 8.05 | **4.24** / 5.01 / 6.25 | 4.21 |
| | spike step | 13 | 10.87 / 13.75 / 16.12 | 10.62 / 13.54 / 16.13 | 10.03 |
| | spike step, the kid standing on the spikes (c) | 5 | 11.75 / 16.18 / 16.18 | 10.99 / 16.18 / 16.18 | |
| l07 drop (room 19) | spikes held | 11 | 7.51 / 11.72 / 11.90 | **5.98** / 10.37 / 10.74 | 5.49 |
| | spikes held + gate step | 8 | 15.11 / 15.84 / 18.95 | 13.94 / 14.82 / 17.57 | |
| | spike step | 4 | 13.88 / 16.42 / 16.42 | 13.29 / 16.65 / 16.65 | 12.94 |
| | spike step + gate step | 5 | 18.68 / 22.15 / 22.15 | 18.18 / 22.16 / 22.16 | |

Held ticks cost what walking costs now (l14 4.16 against b's 4.07, l08 4.13 / 4.02, l06 4.24 / 4.21): -1.7..-2.0
frames a tick, the expected 6.0 -> ~4.4. (b's own numbers fell in l08, l06 and l07 too: b patches only one spike
tile to floor, other spikes of the room still cycle.) Tick by tick, the mean change of a's spike steps is -0.34
(l14), -1.26 (l08, with held spikes elsewhere in the room), -0.32 (l06), -0.28 (l07); per step between -0.9 and
+0.25. Every step regenerates 2 tiles instead of 3 (--rects), -0.41 frames of tile_regen, but on some ticks the
saving turns into waiting for the beam before the copy: l14 tick 33 (0x81 -> 6) is 10.44 frames in both builds,
with tile_regen 1.61 -> 1.20 and pend_flush 0.89 -> 1.30 (--profile). The worst ticks that grew (l07 16.42 -> 16.65)
are such beam phases.

### perfcheck (3 runs per size, identical within each size; main = 60e7a83, one run)

| Stretch | 512 KB main / new | 1 MB main / new | 16 MB main / new |
|---|---|---|---|
| normal tick (walkthrough 30-60) | 5.72 / 5.72 | 5.20 / 5.20 | 5.03 / 5.03 |
| level door step (walkthrough 203-207) | 17.16 / 17.16 | 16.23 / 16.23 | 16.23 / 16.23 |
| room change (walkthrough 89) | 106.05 / 106.05 | 106.05 / 106.05 | 105.22 / 105.22 |
| walkthrough 190-260 | 10.26 / 10.26 | 10.06 / 10.07 | 9.69 / 9.68 |
| gate (gate_push 200-260) | 4.99 / 4.99 | 4.99 / 4.99 | 4.99 / 4.99 |
| traps (traps_b1 0-300) | 5.63 / 5.63 | 5.30 / 5.30 | 5.22 / 5.22 |
| fight (fight1 60-160, guard on) | 7.73 / 7.72 | 7.19 / 7.20 | 6.86 / 6.86 |

Nothing changes by more than 0.01. The 1 MB walkthrough 190-260 +0.01 is beam phase: its ticks differ only in the
level door's animation (215 -0.51, 222 +0.57, 226 +0.61, ...), each a whole wait more or less, from the 17 T the
spike compare adds to every other modifier change that reaches vrd_one's type checks. The baselines were lowered where
the new medians beat them: 512 KB fight 7.73 -> 7.72, 16 MB walkthrough 190-260 9.69 -> 9.68 and traps 5.23 -> 5.22
(1 MB: none).

### Same pixels, same logic

tests/m4_game.py --every 1 (state and VRAM every tick) on the l14, l08, l06 spike and l07 drop scenes' a and c
scripts, traps_b1, b9, b39, b40 and fight_spikes: 0 state diffs, 0 differing pixels; tests/m4_test.py on the same
scripts: 0 differing (the logic program does not include view.asm). The full regression on the runners: see the PR.

## M8a part 12: guard frames (2026-11-03)

Status: **built** (RAM-disk tiers step 3, docs/ramdisk-tiers.md section 13; PLAN.md item 54). On 1 MB and more the
level's guard set's frames go into the frame store at the level start (1 MB: the most used ~81 KB of the set in a
region shared by the sets; 16 MB: every variant of every set, each set once per session), and the lookup serves the
guard (chtab 5) like the kid. Resident +11 bytes of main; the fills moved to their own overlay (page 6).

**Measured first** (tools/fetchstat.py, frames a tick in char_fetch, all / the guard's chtab 5 part; before = main):

| script (ticks) | 1 MB before | 1 MB after | 16 MB before | 16 MB after |
|---|---|---|---|---|
| fight1 60-160 | 1.008 / 0.428 | 0.711 / 0.130 | 0.656 / 0.428 | 0.331 / 0.102 |
| fight2 (346) | 0.645 / 0.209 | 0.489 / 0.052 | 0.434 / 0.209 | 0.275 / 0.050 |
| fight_skill5 (342) | 1.042 / 0.658 | 0.593 / 0.208 | 0.925 / 0.658 | 0.425 / 0.158 |
| level2_fight (356) | 1.249 / 0.429 | 0.967 / 0.146 | 0.693 / 0.428 | 0.353 / 0.088 |
| level13_jaffar (294) | 0.767 / 0.434 | 0.436 / 0.102 | 0.645 / 0.434 | 0.314 / 0.102 |

The guard was 0.21-0.66 frames a tick of a fight (every guard fetch went through spr_fetch, ~75-95 K T); stored it is
0.05-0.21 on 1 MB (the keys left out: 11 % of the scripts' guard fetches in sample, 24 % with each script's own keys
left out of the choice) and 0.05-0.16 on 16 MB (every key stored: the lookup plus the read, ~300 T + 21 T a byte, and
the splash). The keys are chosen from these scripts, so the 1 MB rows are in-sample.

### perfcheck (frames a tick; before = main ef78865, both measured here; the emulator gives the same value every run)

| Stretch | 512 KB before | after | 1 MB before | after | 16 MB before | after |
|---|---:|---:|---:|---:|---:|---:|
| normal tick (walkthrough 30-60) | 5.72 | 5.72 | 5.20 | 5.20 | 5.03 | 5.03 |
| level door step (walkthrough 203-207) | 17.16 | 17.05 | 16.23 | 16.23 | 16.23 | 16.23 |
| room change (walkthrough 89) | 106.05 | 106.05 | 106.05 | 106.05 | 105.22 | 105.22 |
| walkthrough 190-260 | 10.26 | 10.28 | 10.07 | 10.07 | 9.66 | 9.66 |
| gate (gate_push 200-260) | 4.99 | 4.99 | 4.99 | 4.99 | 4.99 | 4.99 |
| traps (traps_b1 0-300) | 5.63 | 5.63 | 5.30 | 5.30 | 5.22 | 5.23 |
| fight (fight1 60-160, guard on) | 7.72 | 7.73 | 7.20 | **6.88** | 6.87 | **6.52** |

The fight is 4.4 % faster on 1 MB and 5.1 % on 16 MB; nothing else changes beyond ±0.1 (512 KB runs none of the new
code: its ±0.01-0.11 come from the main code's 11 bytes moving what follows fs_look). The fight's baselines are
lowered (tests/perf_baseline.json 7.20 -> 6.88, perf_baseline_16M.json 6.86 -> 6.52); 512 KB keeps its baseline.

### The level start

+64-75 frames (1.3-1.5 s) on 1 MB when the set changes, +210-260 (4.2-5.2 s) on 16 MB at the first level of each set;
a restart or the same set again +0.5 frames (the fill overlay's load and the flag); 512 KB 0.3-0.4 frames sooner (the
smaller level-start overlay). No progress indicator exists at that point, so none was added. Per level:
docs/ramdisk-tiers.md section 13. Wait states (MZPico): the guard fill reads each image once per mirror and writes
~81 KB / ~400 KB, so as the boot fill's ~+7 frames per 400 KB and wait state: ~+1.4 / +7 frames a set.

### Same pixels

tests/m8_fstore.py at a level start of each set (levels 1, 6, 3, 13, 12, 4, then 1 again): the lookup's base, the
flags, every guard slot and every stored guard entry against tools/fetchmodel/prebuild.py's generator: all equal on
1 MB (106-150 entries a set; the region refilled at each change, set 0 filled again at the end) and 16 MB (448-544 a
set, all six kept; the pages beyond the MCP's 52 read by a Z80 routine in the test); a restart does not fill. 512 KB:
no store. tests/m4_game.py --every 1 on fight1, fight2, fight_skill5, level2_fight and level13_jaffar at 1 MB and
16 MB: 0 state diffs, 0 differing pixels; m5_boot (512 KB, 1 MB, 16 MB), m7_launch (1 MB) pass. The full regression on
the runners: see the PR.

## Busy rooms: per-room and per-object costs (2026-11-04)

Status: **measured, nothing built.** The playtest: "when one gets to more complex rooms with 2 guillotines and multiple
opening/closing gates, and some bottles, it becomes unplayably slow". Measured on main ef78865 at 1 MB (the INI's), no
waits. The room of the report is level 5 room 24 (2 choppers, 2 gates with 3 buttons, a potion, 2 torches): **13.2
frames a tick with the kid running, 13.5 standing, against 4.0 with its animated tiles patched away** (3.8 ticks a
second instead of 12.5). Choppers are the worst objects, then gates and the level door.

**Tools** (committed): tools/busyrooms.py `census` lists the 270 rooms of levels 1-14 with animated objects on their
screen; `find OUTDIR --worst` writes the scenes of the 20 rooms below with kidsim only (as tools/trapscenes.py: the
start and the run / walk / jump pattern with the most weighted visible object changes before a room change or death;
starting on a button presses it; closers' gates start open): per room `walk_a` (everything animates), `walk_b` (the
same moves, every animated tile of the screen patched to floor: torches, potions, the sword, choppers, spikes, loose
floors, buttons), `walk_<kind>` (only that kind kept) and `stand_a` / `stand_b`. `measure OUTDIR --worst --csv OUT`
runs them (tracepoints at ml_go, where a tick starts after the pacing wait, and at tick_done): **frames** = tick_done
to tick_done (what the player gets; never under 4, the pacing), **work** = ml_go to tick_done (without the wait).
Every tick is labelled by kidsim with the object changes the renderer reacts to (the kinds in the tool's header).
`fit CSV --whatif kind=frames,...` fits the cost model and evaluates fixes. tools/animexact.py renders a tile's
animation steps with the Python reference (tools/popdata.py RoomRenderer) and reports what a moving-part-only redraw
needs to stay exact: the changed pixels, the moving ops, whether what lies under them is flat, which ops lie over
them. The scenes (144 files, 588 KB) are not committed: `find` regenerates them in ~1 minute; measuring all takes ~6
minutes with 7 emulators.

### The worst rooms (1 MB, ticks 2+ with the kid in the start room, alive, in the same state as in b)

Frames a tick: a median / p90 / worst, b median ("walking alone" in that room: 4.0 everywhere, the pacing floor; its
work is 2.5-3.9 frames); a - b and the model = the mean work above b (the model: next section).

| level / room | objects on screen | kid | ticks | a: median / p90 / worst | b | a - b | model |
|---|---|---|---:|---|---:|---:|---:|
| 5 / 24 | 2 choppers, 2 gates (3 buttons), potion, 2 torches | runs | 107 | **13.18** / 17.86 / 25.46 | 3.99 | 9.13 | 9.05 |
| | | stands | 98 | **13.54** / 17.20 / 17.93 | 3.99 | 9.22 | 9.41 |
| 3 / 16 | 3 choppers, potion, 2 torches | jumps | 118 | **16.03** / 20.92 / 24.10 | 3.99 | 12.64 | 12.72 |
| | | stands | 98 | **15.90** / 20.26 / 20.58 | 3.99 | 12.30 | 12.92 |
| 8 / 23 | 2 choppers, gate, potion, spike, torch | jumps | 118 | 13.17 / 19.46 / 20.95 | 4.00 | 8.94 | 8.65 |
| 10 / 10 | 2 choppers, gate (3 buttons), 2 torches | jumps | 43 | 12.96 / 21.93 / 29.93 | 4.02 | 10.14 | 8.93 |
| 8 / 4 | 2 choppers, 2 spikes, 2 torches | runs | 118 | 12.22 / 15.09 / 16.33 | 4.04 | 7.70 | 8.06 |
| 9 / 1 | chopper, 2 gates (2 buttons), torch | jumps | 45 | 13.60 / 18.95 / 21.93 | 4.02 | 9.84 | 9.97 |
| 10 / 1 | 4 gates (2 buttons), level door, loose floor, 2 torches | runs | 98 | 11.75 / 20.45 / 32.58 | 3.99 | 7.58 | 7.53 |
| 7 / 19 | 4 gates (4 buttons), spike, 3 torches | runs | 118 | 10.62 / 14.82 / 22.14 | 4.00 | 7.46 | 6.50 |
| 5 / 8 | 2 gates (3 buttons), 3 torches | jumps | 93 | 10.97 / 13.89 / 22.42 | 4.00 | 7.75 | 7.12 |
| 2 / 18 | gate (2 buttons), loose floor, potion, 2 torches | runs | 48 | 11.98 / 18.92 / 22.25 | 4.11 | 8.99 | 7.39 |
| 7 / 7 | 2 gates (2 buttons), loose floor, 3 torches | jumps | 54 | 10.97 / 14.44 / 21.05 | 3.99 | 7.68 | 6.87 |
| 9 / 22 | 2 gates (2 buttons), 2 spikes, torch | jumps | 41 | 10.76 / 14.62 / 17.72 | 3.98 | 7.61 | 7.70 |
| 1 / 5 | gate, loose floor, potion, 3 torches | runs | 74 | 9.97 / 13.01 / 17.16 | 4.00 | 6.62 | 7.41 |
| 5 / 7 | 4 gates (2 buttons), level door, potion, 2 torches | runs | 118 | 7.55 / 14.48 / 28.61 | 3.99 | 5.82 | 5.11 |
| 10 / 14 | chopper, 3 spikes, 2 torches | runs | 118 | 7.03 / 12.50 / 13.59 | 4.01 | 4.93 | 4.59 |
| 9 / 9 | chopper, gate (2 buttons), 2 torches | runs | 30 | 7.77 / 11.96 / 19.85 | 3.97 | 5.75 | 5.01 |
| 11 / 2 | gate (5 buttons) | jumps | 97 | 7.49 / 11.02 / 19.12 | 4.01 | 3.39 | 3.26 |
| 4 / 18 | 2 gates (2 buttons), 2 spikes, 2 torches | runs | 118 | 6.56 / 12.53 / 20.36 | 3.98 | 3.96 | 4.59 |
| 8 / 5 | gate, 3 spikes, 2 torches | runs | 118 | 6.97 / 11.97 / 19.86 | 3.97 | 4.02 | 4.59 |
| 1 / 15 | the sword, 2 torches | runs | 118 | 6.24 / 7.01 / 7.78 | 4.03 | 2.75 | |

Standing (stand_a) in the chopper rooms costs the same as moving: the choppers keep cycling while the kid is in their
row. In the gate rooms standing is cheaper (the gates open once and stay: l07r19 5.56, l05r08 5.12 medians). The
"walking ~5.2" of perfcheck is level 1's walkthrough rooms with their torches. The kid alone in these rooms works
2.5-3.9 frames, so an object's cost first fills the slack up to 4 frames and then adds one for one.

### The cost model: cost(tick) = the kid's work + the sum of the object changes

Least squares over 8,994 ticks (all variants of all scenes; `fit build/busy/all.csv`), work frames per change. The
mean |residual| is 0.63 frames a tick; the per-scene means are within ~1 frame of the measurement (the table above):

| change (kidsim label) | frames | how often (per object) | renderer path today |
|---|---:|---|---|
| chopper, its picture changes (chomp) | **6.70** | 5 of every 15 ticks while the kid is in its row (it finishes its cycle when he leaves) | tile_redraw: 3 regenerations + rect |
| chopper, the modifier only (chomp-) | **1.82** | the other 10 of the 15 ticks | tile_redraw: 3 regenerations, empty rect |
| gate, the bars move (gate) | **5.82** | opening: every tick, 1 row (modifier +4), ~47 ticks; closing: every 4th tick, ~190 ticks; dropping: every tick, 4-5 ticks | gate_redraw: 2 regenerations + rect |
| gate, the modifier only (gate-) | 0.19 | closing: 3 of 4 ticks | nothing (M8a part 2) |
| spikes, the picture changes (spike) | 4.88 | 9 of a 24-tick cycle | spike_redraw: 2 regenerations + rect |
| button pressed / released (button) | 5.07 | per press | tile_redraw |
| potion bubble (potion) | 1.19 | every tick | bubble_redraw: fore op patch, then a run_rect of the bubble |
| torch flame (torch) | 0.60 | ~every tick | torch_fast: op patch, the flame laid in the object pass |
| loose floor shakes (loose) | 3.07 | 5 steps per shake (rare) | tile_redraw |
| sword, the modifier only (sword-; l01r15's only-sword variant) | **1.50** | 97 % of the ticks (the modifier counts down; the glint shows only at 1) | tile_redraw: 3 regenerations, empty rect |
| level door step (walk_level1 204-206, profile) | **~9-11** | every tick for 43 ticks (opening, 1 row a tick) | tile_redraw: 3 regenerations + a 6 x 51 rect |

So an active chopper costs (5 x 6.7 + 10 x 1.8) / 15 = 3.4 frames a tick, an opening gate 5.8 a tick for ~4
seconds of play, each potion 1.2 and each torch 0.6 every tick. The combination is additive, as found for gates and
spikes: in l05r24 the only-kind variants sum to 93 % of a - b (8.5 of 9.1).

### Where a step goes (tools/tickcost.py --profile, inclusive frames)

| | 2 choppers, modifier only (l08r04_walk_chomper 10) | 2 choppers, picture (same, 19) | potion (l05r24_walk_potion 10) | 2 torches (l05r24_walk_torch 10) | level door step (walk_level1 204) |
|---|---|---|---|---|---|
| the tick / the same tick in b | 7.03 / 4.10 | 14.98 / 4.03 | 4.16 / 4.10 (paced) | 4.14 / 4.10 (paced) | 14.21 |
| regenerations | tile_regen x 6: 3.46 | x 6: 3.65 | - | - | x 3: 2.24 |
| laying the rect | (empty) | run_rect 3.89 (lay_piece16 x 8: 5.08 with the chunks') | run_rect 0.57 (3 pieces) | - | run_rect 6.82 (lay_piece16 x 22: 5.08) |
| fill, shadow write | - | shadow_write 0.73 | 0.10 | - | 0.55 + 0.74 |
| object pass above b | 0.02 | +2.65 (the rects' chunks; people_chunk 2.46 against 0.54: the choppers' rects overlap the kid in their row) | +0.76 (a chunk for the bubble) | +0.84 (two 2 x 18 chunks) | +1.7 |

Findings:
1. **A chopper redraws three tiles on every tick of its cycle, 10 of 15 times for nothing.** Its picture is
   CHOMPER_FRAM1[min(modifier & 0x7F, 6)] and the blood bit (room.asm dta_chomper / dtf_chomper): modifiers 5-15 and
   0 all give the same picture. It draws nothing in its right neighbour or the tile above-right
   (draw_tile_anim_right / draw_tile_anim_topright have no chopper case), yet tile_redraw regenerates both: 1.2 of
   the 1.8 frames.
2. **The sword redraws three tiles every tick** (its modifier counts down from 0x28-0x67 to 1): 1.5 frames a tick
   for a glint that shows on 3 % of the ticks.
3. **A potion bubble runs a rect through the shadow** although the bubble is a fore op and the shadow holds the
   background without the fore pieces (room.asm rr_sw): marking the old and the new bubble rect dirty is enough, as
   torch_fast does for flames (~0.6 of its 1.2).
4. **A gate or door step lays the whole stack of pieces again** (10-14 for a gate, 22 for the door) after 2-3 op-list
   regenerations, for a picture that is the previous one moved by one row (next section).

### What stays exact (tools/animexact.py: the changed pixels, the moving ops and the shift check of each step against the reference)

| object | the changed area of a step | moving ops | under them | exact moving-part path |
|---|---|---|---|---|
| gate | 3 x 56 bytes x rows max | the bar stack: bottom 50, slices 52 and the top slice (53-59 are exactly the bottom 1-7 rows of 52), all opaque (blit copy); the top piece 60-67 (masked) | the open branch (the bottom more than 12 rows above the floor, modifier >= 48): covered or black; the closed branch: the floor (2 colours) | **yes**: every step of l05r24's and l01r05's gates is the previous picture shifted by the step (1 row), 0 differing pixels below the gate top; only a ~10-row band at the top (the top piece cycles: 0-21 pixels; opening l05r24 p21 0 everywhere) and, in the closed branch, 1-3 pixels of one row where the bottom meets the floor differ |
| level door | 6 x 51 | 6-27 opaque slices | black or one flat colour, which varies by row (5, 7, 8: the dungeon's wall behind is in bands) | **yes**: every step is the previous picture shifted by one row except the newly revealed bottom row: 0 pixels in 38 of 43 steps (palace l10r1) and 38 of 43 (dungeon l1r9); in the others 1-40 pixels of that one row differ (a 6 x 1 band to lay as today) |
| chopper | 4 x 58 | 3-5 masked pieces (bottom, top, fore, blood) | 4-7 colours (the wall, the floor) | **yes** with the background under it kept or cached; no shift structure (5 pictures) |
| spikes | 6 x 26 | 3-6 masked | several colours | yes, with a cached background or cached frames |
| potion bubble | 1 x 9 | the bubble (masked, fore list) | black | yes (dirty rect only: the fore pass lays it) |
| torch flame | 2 x 17 | the flame (opaque) | covered | yes (already so: torch_fast) |
| sword glint | 2 x 7 | masked | covered | yes (redraw only on the glint's change) |

The Apple II's movebuf (redgate / drawgateb: the bars drawn opaque, the bottom piece's blank lines erase the trail,
no restore) maps onto the DOS art like this: the bars and the door are opaque and rigid, so drawing only the moving
part, or moving the column by one row, is pixel-exact. Under the bars the art is black only in the open branch, and
the door's revealed rows are not black in the dungeon, so a black fill alone (Apple's blank lines) is not exact; taking
the revealed rows from the shifted picture is. Choppers and spikes are masked over a textured background: for them a
moving-part-only redraw needs the background under them (a cached under-layer or cached frames).

### The options (frames of work a visible step unless noted; gains on the worst rooms from the model's what-ifs)

**C. Draw only what changes (cheap fixes)**: (1) a chopper's modifier change draws nothing unless its picture changes
(as spike fix 1); (2) a chopper's picture change regenerates its own tile only; (3) the sword likewise, on the glint's
change only; (4) a potion bubble marks its rects dirty without a run_rect. Gains: chopper modifier-only 1.8 -> 0,
picture 6.7 -> ~5.5, the sword 1.5 -> ~0 a tick, a potion 1.2 -> ~0.6 a tick. Memory: ~80-120 bytes of main (613
free) and the chopper / sword cases in vrd_one (the low block has 22 free; or the dispatch moves to main). Exact: yes
(the reference renders from the level state). Effort ~1 day, risk low.

**D. Moving part only: the column shift (gates, the level door)**: a step moves the column's rows (a gate: the rows
below its top band; the door: its 6 x 51) by the step in the shadow (the shifted rows read into SPRBUF_B and written
back: ~0.3 + ~0.6 for a 3 x 57 gate column, from restore_shadow's ~190 T a plane row of 8 bytes and shadow_write's
~0.012 frames a row of a narrow rect), lays the gate's ~10-row top band as today (an op patch of the top piece's
record, a 3 x 10 run_rect, ~0.4) and puts the column on the dirty list (the object pass copies it, ~0.3-0.5). The bar
and door tiles' op lists are regenerated once when the movement stops, or before any other redraw of those tiles,
instead of at every step. Gate step 5.8 -> **~1.9**, door step ~10 -> **~1.8**; the closed branch's floor-contact
row and the door's newly revealed bottom row are laid as small bands like the top band (or, simpler, take today's
path on the ~10 closed-branch steps of a gate and the 5 such door steps). No RAM-disk space; ~200-300 bytes (a W1 overlay for the step
code, ~30 bytes resident). Exact: yes (the shift check above; the shadow is the source, so it is right whatever lies
under the column). Guard: a registered torch flame over the column (its pixels need not be in the shadow) falls back
to today's path. Effort 3-5 days, risk medium.

**A. Pre-drawn frames (choppers, spikes)**: each distinct picture of the object's rect (the background-only result of
today's run_rect, i.e. what the shadow holds there) is written to a RAM-disk slot the first time it is drawn (lazy: no
room-entry cost, ~0.35 frames once per picture); a later step reads the picture into SPRBUF_B (~0.36 for 4 x 58),
writes the shadow (~0.7), and the object pass composes the people and the fore pieces over it and copies it (~0.6-1.0
with the kid in the row). Chopper picture step 5.5 -> **~2.0-2.5**, spike step 4.9 -> **~1.5**. Space: a chopper
5 pictures x 928 bytes = 4.6 KB (the blood pictures not cached: today's path), a spike 5 x 624 = 3.1 KB; the worst
rooms need 13.9 KB (l03r16), 15.5 KB (l08r04), 14.0 KB (l10r14). 512 KB: ~23 KB free but in pieces (page 1
0xE918-0xFFFF 5.8 KB, page 6 0xE800-0xFFFF 6 KB, page 4 11.1 KB if the game image's reserved second piece stays
unused), i.e. 4 chopper-sized slots; 1 MB: from the 81.6 KB tail of pages 14-15, which is earmarked for the guards'
frame store (the two need agreeing); 16 MB: free. A slot is valid while the tiles drawing into its rect are unchanged
(any other redraw touching the rect drops it). The kid or a guard over the tile: the cached picture is background
only, the object pass draws them on top as today. Exact: yes (the bytes are today's run_rect output). Effort ~1 week
(slot table, capture, invalidation), ~250 bytes in an overlay, risk medium.

A for gates (not proposed): a gate has 47 positions, whole-column pictures would take 47 x 3 x 62 x 4 = 35 KB a gate;
the rigid shift (D) gives the same with no space.

**E. An exclusive animated layer (the torch mechanism generalized)**: the shadow keeps the background without the
moving parts, and every chunk that touches an animated object lays its current picture (a shifted strip, a cached
picture, the masked pieces) after the restore, as flames_lay does. A step then needs no shadow write (-0.5..-0.7 a
step for gates, the door, choppers, spikes), and small opaque rects with nothing over them (flames, bubbles) can go
straight to VRAM (a torch 0.6 -> ~0.15 a tick, estimate). Brings the steps to ~1.0-1.5. It costs every chunk that
touches an object that object's picture (+0.2-0.4 when the kid is at a chopper or in a gate). Effort 1-2 weeks, risk
high (chunk order, exclusivity rules, the beam scheduling); to be measured after C, D and A.

**B. Pacing (PACE_MODE 1, skipped draws)**: no gain in these rooms as it is. ml_pace (src/m4/game.asm) restarts the
tick clock when it is more than DEBT_MAX = 8 frames late, and a drawn tick in l05r24 costs ~13.5 frames (9.5 late
after it): so after a typical drawn tick the clock restarts and the next tick is drawn too. A skip needs a tick that
ends 4-8 frames late, i.e. a drawn tick of ~8-12 frames; ticks vary (p90 ~17.9, some ~9), so B skips some ticks, but
far fewer than its design assumes (an estimate from the median, not measured: most ticks drawn, near today's ~3.7
ticks a second). Only with the debt limit raised or removed would it settle into 1 drawn tick and 2
skipped ones (~13.5 + 2 x ~1.3 frames for 3 ticks: ~9 ticks a second, ~3 screens a second), and then the debt grows by
~4 frames every 3 ticks until a stall resets it; in that case two of every three screens are never shown (choppers
and gates jump 2-3 steps from screen to screen): not exact over time. The user decided against it (2026-10-31).

What the model predicts (frames a tick, median / mean; `fit ... --whatif`; C = chomp-=0, chomp=5.5, potion=0.6;
D = gate=1.9, door=1.8; A = chomp=1.9, spike=1.9; E = every step 1.0 (buttons too), torch=0.15. A button press keeps
its 5.07 in C, D and A: none of them changes the button's redraw):

| room (kid) | today | C | C + D | C + D + A | + E |
|---|---|---|---|---|---|
| 5 / 24 (runs) | 13.84 / 12.62 | 10.23 / 9.18 | 10.23 / 9.18 | 6.66 / 6.99 | 5.01 / 5.20 |
| 5 / 24 (stands) | 14.09 / 12.62 | 10.48 / 8.82 | 10.48 / 8.82 | 6.88 / 6.33 | 5.09 / 4.81 |
| 3 / 16 | 15.97 / 16.08 | 10.54 / 10.65 | 10.54 / 10.65 | 6.98 / 7.05 | 5.20 / 5.31 |
| 8 / 23 | 12.57 / 11.85 | 8.96 / 8.10 | 8.96 / 8.10 | 5.83 / 5.72 | 4.56 / 4.79 |
| 10 / 10 | 12.35 / 12.29 | 9.33 / 9.09 | 9.33 / 8.64 | 6.07 / 6.29 | 4.37 / 4.66 |
| 8 / 4 | 12.68 / 11.85 | 9.66 / 8.62 | 9.66 / 8.62 | 6.10 / 6.24 | 4.61 / 4.83 |
| 9 / 1 | 11.90 / 13.37 | 10.08 / 11.75 | 6.16 / 7.84 | 6.16 / 6.64 | 4.67 / 4.94 |
| 10 / 1 | 15.56 / 11.22 | 15.56 / 11.22 | 7.85 / 7.15 | 7.85 / 7.15 | 5.16 / 5.28 |
| 7 / 19 | 10.47 / 9.82 | 10.47 / 9.82 | 6.69 / 7.50 | 6.69 / 7.14 | 4.56 / 4.70 |
| 5 / 8 | 10.79 / 10.42 | 10.79 / 10.42 | 6.88 / 7.01 | 6.88 / 7.01 | 4.64 / 4.78 |
| 2 / 18 | 11.38 / 10.94 | 10.80 / 10.36 | 7.83 / 7.99 | 7.83 / 7.99 | 6.16 / 6.15 |
| 7 / 7 | 10.77 / 10.14 | 10.77 / 10.14 | 6.85 / 6.80 | 6.85 / 6.80 | 4.61 / 4.71 |
| 1 / 5 | 11.55 / 10.71 | 10.97 / 10.13 | 7.09 / 7.64 | 7.09 / 7.64 | 5.06 / 5.18 |

(The model's "today" medians differ a little from the measured ones above: it sums mean costs per change on b's
work, max 4.) Plus the sword room (l01r15) 6.2 -> ~4.7 with C, and the level door step (walk_level1 203-207) ~16 ->
~7 with D. After C + D + A the worst rooms run at ~6-8 frames a tick (6-8 ticks a second; a room without objects
runs at 4-5). Reaching ~1 frame a step or less, i.e. ~4.5-5 frames a tick in these rooms, needs E as well; what is
left after E is the torches (2-3 a room) and the kid.

### Build order (sequential PRs: they touch view.asm, room.asm, gate.asm and the object pass)

1. **C: draw only on a picture change** (choppers, the sword, potions): ~1 day; chopper rooms -2.5..-5.5 frames a
   tick (median), the sword room -1.5, potion rooms -0.6.
2. **D: the column shift for gates and the level door** (one routine: shift a shadow rect by k rows, then put it on
   the dirty list): 3-5 days; gate rooms -3..-8 a tick while a gate moves (l10r01 15.6 -> 7.9, l07r19 10.5 -> 6.7),
   the exit door's 43 ticks ~16 -> ~7. Not l05r24 (10.2 -> 10.2 after C): its 3 buttons are pressed often and a press
   still costs 5.1 (a tile_redraw); a cheaper button redraw (its few changed rows) would be a separate item.
3. **A: the frame cache for choppers and spikes** (the same SPRBUF_B -> shadow -> dirty-list path as D, the source a
   RAM-disk slot): ~1 week; chopper rooms another -3..-3.5 (l03r16 10.5 -> 7.0).
4. **E: the exclusive animated layer and the direct copy of small rects** (to be measured first, after 1-3): 1-2
   weeks; another -1.5..-2.5 in the worst rooms, and each torch -0.45 in every room.

The shared mechanism of 2 and 3 (later also the gate's top band and E's strip copies): put a rect into SPRBUF_B from a
source (the shadow at a row offset, or a RAM-disk slot), write it to the shadow, put it on the dirty list; the object
pass after it is unchanged. ~150-250 bytes: the per-step code in a W1 overlay (loaded when an animated step needs it
and another overlay held W1: 21 T a byte, ~0.1 frames a load), ~30 bytes resident in main, nothing more in the low
block.

## M8a part 13: animated objects on change (2026-11-07)

Status: **built.** Option C of the busy-rooms measurement ("Busy rooms: per-room and per-object costs", PR #28; its
tools tools/busyrooms.py and tools/animexact.py): choppers, the sword and potion bubbles draw only when their picture
changes, and then only the tile that draws it. view.asm vrd_one sends a modifier-only change of every type but the
torches, gates and potions to anim_redraw (src/m4/spike.asm, main block), which handles spikes (part 11), choppers
and the sword, and passes the rest on to vrd_tile:

1. **Choppers.** The picture is n = CHOMPER_FRAM1[min(modifier & 0x7F, 6)] plus the blood bit (dta_chomper,
   dtf_chomper: back and fore ops of its own tile). When the old and the new modifier give the same picture (10 of
   the 15 ticks of a cycle: modifiers 5..15 and 0 all give n = 3) nothing is regenerated or laid; before, tile_redraw
   regenerated 3 tiles for an empty rect. A picture change regenerates the chopper's own tile only (our room, or the
   above room's row 2, whose fore op shows); a chopper in the left room's column 9 or the below room's row 0 draws
   nothing on screen.
2. **The sword.** The picture is image 10, or 11 at modifier 1 (dta_sword, a mid op of its own tile); the modifier
   counts down every tick, the glint shows on 3 % of them. Only a change into or out of 1 regenerates the tile, and
   only in its own room (draw_tile_above has no draw_tile_anim).
3. **Potion bubbles.** op_patch (room.asm) of a fore op in a background-only redraw (RR_SHONLY, the game) hands the
   old and the new rect to the dirty list (RR_HOOK) without dr_run: the shadow holds no fore pieces (rr_sw), so the
   shadow write of the bubble's rect was redundant; the object pass lays the fore pieces over the restored shadow.
   fore_gen and the slice extent are updated as before.

Which tiles draw which picture was checked against the Python reference for every chopper, sword and potion of levels
1-14 and every screen that shows one (its own room, the right room for column 9, the room below for row 2, the room
above for row 0): RoomRenderer's op lists, each op tagged with the tile whose draw emitted it, for every modifier
(choppers 0x00-0x0F and 0x80-0x8F, swords 0-3 / 0x28 / 0x67, potions the 8 bubbles). Modifiers with the same picture
give identical lists; otherwise only the object's own tile's ops differ; from the left room and the below room
nothing differs (choppers own 39 / above 4 / below 10 screens, swords 3 / 1 / 2, potions 57 / 23 / 7; 0 exceptions).
The reference renders the room from the level state, so it has no redraw decision to follow.

Resident: low block -4 bytes (vrd_one's spike case and potion test fold into one jump: end_of_low 0x1FEA -> 0x1FE6,
26 free), main +100 (spike.asm +77, op_patch +23: end_of_code 0x79A6 -> 0x7A0A, 502 free).

### The busy rooms (1 MB, frames a tick: median / p90 / worst; tools/busyrooms.py measure, main 64b93ed against this)

| room | objects | kid | ticks | before | after | b (walking alone) |
|---|---|---|---:|---|---|---:|
| 5 / 24 | 2 choppers, 2 gates, potion, 2 torches | runs | 107 | 13.16 / 17.84 / 25.46 | **9.97** / 17.34 / 26.06 | 3.99 |
| | | stands | 98 | 13.54 / 17.20 / 17.93 | **10.27** / 17.36 / 17.48 | 3.99 |
| 3 / 16 | 3 choppers, potion, 2 torches | jumps | 118 | 15.94 / 20.93 / 24.10 | **10.96** / 16.97 / 20.06 | 3.99 |
| | | stands | 98 | 15.85 / 20.09 / 20.60 | **10.78** / 16.80 / 16.95 | 3.99 |
| 8 / 23 | 2 choppers, gate, potion, spike, torch | jumps | 118 | 13.17 / 19.46 / 20.93 | **9.61** / 16.35 / 17.95 | 4.00 |
| | | stands | 98 | 13.10 / 19.40 / 19.93 | **9.53** / 16.41 / 16.94 | 3.99 |
| 10 / 10 | 2 choppers, gate, 2 torches | jumps | 43 | 12.96 / 21.93 / 29.89 | **10.18** / 19.38 / 27.92 | 4.02 |
| | | stands | 98 | 11.96 / 17.65 / 28.34 | **9.06** / 15.53 / 26.77 | 3.99 |
| 8 / 4 | 2 choppers, 2 spikes, 2 torches | runs | 118 | 12.22 / 15.17 / 16.33 | **9.35** / 15.41 / 16.96 | 4.04 |
| | | stands | 98 | 11.73 / 14.32 / 14.65 | **8.84** / 14.76 / 14.97 | 3.99 |
| 1 / 15 | the sword, 2 torches | runs | 118 | 6.24 / 7.02 / 7.78 | **4.57** / 5.02 / 6.98 | 4.03 |
| | | stands | 98 | 5.04 / 5.87 / 7.96 | **3.99** / 4.48 / 7.63 | 3.99 |
| 1 / 5 | gate, loose floor, potion, 3 torches | runs | 74 | 9.97 / 12.97 / 17.16 | **9.23** / 12.09 / 16.53 | 4.00 |
| | | stands | 98 | 6.50 / 12.45 / 16.35 | **6.35** / 11.60 / 16.31 | 3.99 |

The cost model refitted over the 3,812 ticks of these scenes (`fit`, frames of work a change; before / after):

| change | before | after | expected (option C) |
|---|---:|---:|---:|
| chomp- (a chopper's modifier only) | 1.92 | **0.11** | 0 |
| chomp (its picture) | 6.68 | **6.05** | ~5.5 |
| sword- (the sword's modifier only) | 1.61 | **-0.05** | 0 |
| sword (the glint appears or goes; 9 ticks) | 3.07 | 2.30 | |
| potion (a bubble frame) | 1.10 | **0.66** | ~0.6 |
| torch / gate / button (unchanged paths) | 0.49 / 5.49 / 4.74 | 0.46 / 5.34 / 4.88 | |

The chopper rooms lose 2.9-5.0 frames a tick at the median (l03r16 15.9 -> 11.0), the sword room reaches the walking
floor, the potion rooms lose ~0.45 per potion. The worst ticks change little: they are the ticks where all choppers
change their picture at once, and a picture step still costs ~6 frames (two tile_regens fewer, -0.6, but the tile's
run_rect of 4 x 63 rows and the object pass over the kid in the chopper's row are the rest: option A's pre-drawn frames
are for those). The gate's l01r05 and l05r24 differences are beam phase. Buttons keep their full tile_redraw (4.7-5.1 frames a press):
a cheaper button redraw is a candidate of its own, not part of C.

### perfcheck (one run per size, the emulator is cycle-exact; main = 64b93ed)

| Stretch | 512 KB main / new | 1 MB main / new | 16 MB main / new |
|---|---|---|---|
| normal tick (walkthrough 30-60) | 5.72 / 5.72 | 5.20 / 5.20 | 5.03 / 5.03 |
| level door step (walkthrough 203-207) | 17.16 / 17.16 | 16.23 / 16.23 | 16.23 / 16.23 |
| room change (walkthrough 89) | 106.05 / 106.05 | 106.05 / 106.05 | 105.22 / 105.22 |
| walkthrough 190-260 | 10.26 / 10.26 | 10.07 / 10.07 | 9.66 / 9.68 |
| gate (gate_push 200-260) | 4.99 / 4.99 | 4.99 / 4.99 | 4.99 / 4.99 |
| traps (traps_b1 0-300) | 5.63 / 5.63 | 5.30 / 5.30 | 5.23 / 5.23 |
| fight (fight1 60-160, guard on) | 7.72 / 7.72 | 6.88 / 6.88 | 6.51 / 6.51 |

The stretches have no chopper, sword or potion (level 1's walkthrough room 15 is not in them), so nothing moves but
the 16 MB walkthrough 190-260 (+0.02: the level door's beam phase, as in part 11). The 16 MB fight baseline is
lowered 6.52 -> 6.51 (main's median too).

### Same pixels, same logic

tests/m4_game.py --every 1 (state and VRAM every tick) on chomper, sword, potion_heal / hurt / life, fight_chomper,
level5_shadow_potion, potion_upside_down, death_text, the a scripts (walk and stand) of the seven busy rooms above,
the l14 spike a and l06 spike c scenes, fight_spikes and traps_b1: 0 state diffs, 0 differing pixels.
tests/m4_test.py on chomper, sword, the three potion scripts, fight_chomper and traps_b1: 0 differing. The full
regression on the runners: see the PR.

## M8a part 14: column shift (gates, level door) and buttons (2026-11-07)

Status: **built.** Option D of the busy-rooms measurement ("Busy rooms: per-room and per-object costs") and the cheaper
button redraw that section left open: a gate's or the level door's step moves the column's rows in the shadow instead
of laying the stack piece by piece, and a button's press or release puts a cached picture. The code is in three new
W1 overlays and a small resident part:

- src/m4/colshift.asm: gate_step (CS_GATE: the gate overlay, 10, src/m4/ovl_anim.asm, 1,014 bytes; from gate.asm
  gate_redraw through the stub gate_fast) and door_step (CS_DOOR: the door overlay, 12, src/m4/ovl_door.asm, 868
  bytes, image in RAM-disk page 6 0xF600; from spike.asm door_redraw); carry: not this step, the caller redraws as
  before.
- src/m4/btnstep.asm (the button overlay, 11; 808 bytes; its image in RAM-disk page 6 0xF200, its own place like the
  fill overlay's: page 7's area has no room left for the cheat build's keys overlay): btn_step, from view.asm vrd_cht.
- src/m4/anires.asm (block 2, 192 bytes): the shared tail, which fix A will use too: **cs_get** (a rect of the shadow,
  at any row offset, into SPRBUF_B), **cs_put** (SPRBUF_B's rect into the shadow, onto the dirty list, and marked as the
  object pass's kept background: room.asm rr_kr / rr_kv, tcache.asm oc_kept, so the object pass composes the people and
  the fore pieces over it without a restore), **dirty_hook** (RR_HOOK's target now: drops the cached button pictures a
  redraw touches) and the button cache's validity (bc_v, bc_rect, btn_rgi).
- src/m4/buttons.asm (trigger_button, do_trigger_list, trigger_gate, 272 bytes) is copied into the gate and the door
  overlays besides the events overlay, at the same entry; ovl.asm's trigger_button stub runs the copy in W1 when the
  gate or the door overlay is there, else loads the events overlay. The kid's check_press calls trigger_button every
  tick he stands on a plate, and the plate is what opens the gate (and the exit door): with the buttons in the events
  overlay only, both overlays were loaded every tick, 0.6 frames a tick (measured on walk_level1 204 with the first
  build of this part, which had them resident instead: 272 bytes of main, given back by the copies).

### The gate (colshift.asm gate_step)

The bars (draw_gate_back, drawn by the gate's right neighbour, the bars tile, in its column's 3 bytes) hang from the
gate's bottom and are cut at its top GT = 63 row + 3 by the frame slice; above GT the tile above draws the top piece:
68 (mono black) and the frame DOOR_FRAM_TOP[p & 7], p = min(mod, 188) / 4. A step p -> p + k with |k| = 1 and both
<= 46 is drawn as:

1. rows GT..S1 - 1 of the column (closing: GT + 1..): the shadow k rows lower (cs_get into SPRBUF_B). S1 = MY - min(p)
   (the lower bottom's row + 1, MY = GT + 59) in the open branch, MY - 13 (the floor's top) while min(p) <= 12;
2. rows max(GT - 9, 0)..GT - 1: the shadow, with 68 and the new top frame laid over it (68 covers every frame; their
   two records are the top tile's, found and the frame's id patched);
3. closing (k = -1): row GT stays the old row and the new frame slice is laid over it (moved, it would come from above
   the gate; the slice copies only its extent, 20 of its 24 pixels in the dungeon, the rest is what is under the bars);
4. a dungeon pillar as the bars tile: its base (92, mono black, drawn after the bars) laid again over the moved rows;
5. cs_put; and while min(p) <= 12 the contact band, rows MY - 13..MY - min(p) - 1 (the floor drawn before the bars
   shows below them there), laid by dr_run.

The op records stay what a regeneration would make (later redraws, overlaps and room re-entry lay them): the bars'
records (CH_ENV 50..59 in the bars tile's back slice) move by k rows and the frame slice gets its new id, height and
top; the top frame its new id. Where the record count or the branch changes ((46 - min(p)) & 7 = 0: a slice comes or
goes; min(p) = 11: draw_gate_back's open / closed branch) the bars tile is regenerated instead. Not this way
(gate_redraw as before): a dropping gate (|k| > 1), a step to or from 47 (the bottom piece reaches above GT), the
below room's row 0 (only the top shows), a bars tile that changed in the same tick (its own redraw would find its
records regenerated), a bars tile other than empty, floor, stuck, closer, loose floor, opener, torch, gate or the
dungeon's pillar (in levels 1-14 only the palace pillar: 9 gates in levels 4, 5, 6, 10, 11 and 14, whose base does not
cover what the shift moved). A regeneration of the bars tile earlier in the same tick (tile_redraw's above-right tile,
for a left-room gate) leaves the records already moved: the frame slice's height tells, and then they are not moved
again.

### The level door (colshift.asm door_step)

The door (draw_leveldoor, drawn by its tile's right neighbour at xh + 1, 6 bytes; yb = MY - 13): 99 at yb, 144 (the
dark opening) at yb - 4, the slices (33) every 4 rows from the door's bottom yb - ml up, 34 over their top. An opening
step ml -> ml + 1 (ml <= 43, not in the start room, where a wipe replaces 144) is the picture moved one row up in rows
max(yb - 50, 0)..yb - ml - 1, and the revealed row yb - ml: the old row with 99 and 144 laid over it, clipped to the
row. In the dungeon the door is 42 pixels wide: of its sixth byte only bits 0-1 (the two left pixels) are taken from
the moved rows, the rest from the old picture (a 1 x n restore into COMPOSE_A and a merge). Records: the slices move
one row up; at ml & 3 = 3 (a slice goes) and ml = 0 (144 comes) the tile is regenerated. Not this way: closing (the
start room's door at the level start), the start room, a tile changed in the same tick.

### Buttons (btnstep.asm btn_step)

A press or release (view_redraw makes the snapshot's tile byte differ in bit 0; vrd_cht sends exactly that to
btn_redraw) changes only the back ops of the button's tile and its right neighbour (a pressed opener is drawn as a
floor, a pressed closer as a stuck floor: get_tile), as many of them in both states, and pixels only in the rect
x 4c..4c + 7 (to 40), rows 63r + 49..63r + 65 (8 x 17 bytes). tile_redraw regenerated three tiles and laid the rect
piece by piece (~4.9 frames). The first four buttons of a screen (VS_BTN order) have a slot in RAM-disk page 1
0xE918-0xFC5B (1,233 bytes each): the rect's picture in both states (4 planes x 17 rows of 8 bytes) and the records
that differ between the states (tag, place in the slice, both versions; not CH_OBJ, the flames torch_fast patches).

- **The slot valid** (anires.asm bc_v): the new state's records written into the two slices (their extents widened),
  the picture read into SPRBUF_B and put (cs_put). Nothing is regenerated or laid.
- **Else**: the old picture saved from the shadow, the two tiles' back slices kept (COMPOSE_B), the tiles regenerated,
  the rect (with the regenerated records' rects) laid by dr_run, the new picture (SPRBUF_B after the dr_run) and the
  differing records saved, the slot valid. When the regenerated records' rects reach out of the rect (the palace's
  stripe and blue line pieces, whose pixels do not change) the new picture is read from the shadow instead. Not kept
  when the right tile changed in the same tick (its own redraw follows), when the own tile shows no differing record
  (it was regenerated earlier in the tick), or when more than 8 records differ.
- A slot goes when a redraw of the shadow touches its rect (dirty_hook: every dr_run of the room renderer and every
  cs_put), when one of its tiles is regenerated (room.asm tile_regen calls btn_rgi while a slot is valid), and at every
  room draw (game.asm).

The other rooms' buttons (the left room's column 9, the rows above and below) and the fifth button on: tile_redraw as
before. The first press after a room draw is a miss: ~4.0-4.5 frames (two regenerations instead of three, plus the
two pictures saved); every later press or release in the room until something redraws the rect: **0.52** frames
(l07r19_walk_a ticks 71, 72), 0.77 with the button overlay's load (ticks 18, 39, 46, 47, 78: a gate moved the tick
before), and a moving gate's next step loads the gate overlay again (+0.28). The model's per-change cost (below)
mixes both: in these scenes the kid dies and restarts the room often.

### Memory

Against main 8e5aad2: main +76 bytes (end_of_code 0x7A0A -> 0x7A56, 426 free): the stubs gate_fast, door_fast,
btn_fast and btn_redraw +45, trigger_button's stub +10, door_redraw and its case in spike.asm's anim_redraw +11, the
button cache's hook in room.asm tile_regen +10. The low block +6 (vrd_cht sends a button's press to btn_redraw; 20
free). Block 2 +203 (anires.asm 199: cs_get, cs_put, dirty_hook, room_drawn, the button cache's validity; gate.asm +4;
17 free). The overlays: the gate overlay 1,014 bytes (10 free), the door overlay 868, the button overlay 808 (cs_chg,
27 bytes, is in each of the three), the events overlay unchanged (1,009). RAM disk: the button pictures page 1
0xE918-0xFC5B, the button and door overlays' images page 6 0xF200 and 0xF600; page 7's overlay area 751 bytes free
(the cheat build 337). An earlier build had the button code, cs_chg and the after-room-draw hook resident (main +387,
115 free); moved out as above, costing: a gate and the door moving in the same tick load both overlays every tick
(~0.55 frames; only while the exit door opens next to moving gates, l10r01 and l05r07); a button press after a gate
step loads the button overlay and then the gate overlay again (~0.25 + 0.3 frames, as before the move); the kid on a
plate with neither overlay in W1 loads the events overlay once (as on main).

### Exact (tools/movecheck.py: each step simulated on the Python reference's shadow, whole screen)

tools/movecheck.py paints the steps above on RoomRenderer's shadow picture (the wipes, back and mid ops: what the
shadow room holds) and compares the result with the reference's picture of the new state, every pixel: gates 7,452
steps of every gate of levels 1-14 drawn on a screen (our room's columns 0-8, the left room's column 9) with a bars
tile of the list (the 9 palace-pillar gates left out), every one-row step both ways with both positions <= 46: 0
differ; level doors 748 opening steps (ml 0..43, every door not in its start room): 0 differ; buttons: all 134 seen
in their own room, the changed pixels in the rect and only back ops changing, as many: 0 exceptions. How it was found
(scratch scripts on the same reference): every gate step is a one-row shift below GT in the open branch; the closed
branch differs in 1-3 pixels where the bottom meets the floor (hence the contact band, which needs to reach only the
lower bottom); 68 covers every top frame; for 19 gates the bars tile is a pillar, whose base is drawn over the bars:
the dungeon's (10 gates) is exact with it laid again, the palace's is not.

### The prototype (measure first)

The first build moved the rows (steps 1 and 5) and laid the rest as tile_redraw would: the two tiles regenerated, and
the top band (rows GT - 9..GT) by run_rect. gate_push tick 183 (the left room's gate closing 120 -> 119): **9.05 ->
8.16 frames**; gate_redraw 4.42 -> 3.34 frames: the two regenerations 1.19, the top band's run_rect 1.48 (7 pieces),
the move itself 0.55 (restore 0.27 into SPRBUF_B, the shadow write 0.24). The estimate (~1.9 for the whole step with
the object pass) assumed neither: so the records are patched in place (no regeneration) and the band's changes are
laid as their two pieces (68 and the frame) over the shadow. The same tick now: **6.04**; view_redraw 4.61 -> 1.65,
the gate step 1.52 (the three pieces 0.54, the restores 0.38, the shadow write 0.44, the scans and patches ~0.1); the
object pass copies the column from the kept SPRBUF_B (no restore).

Where a gate step still costs more (l07r07_walk_gate, a dungeon-pillar gate opening, frames a tick with the kid
running): the open steps 5.9-6.4, of it the gate ~2.1 (the pillar's base laid again, 32 pixels x up to 46 rows, masked:
~0.9); the closed steps (min(p) <= 12: the first 12 of an opening, the last 12 visible ones of a closing) 8.3-9.2 (the
contact band's run_rect, ~5 pieces: ~1.5; it was 1.7-2.0 while the band reached the floor's bottom, MY - 1); the steps
that regenerate the bars tile +0.6 (1 of 8, and 11 <-> 12).

### The busy rooms (1 MB, frames a tick: median / p90 / worst; tools/busyrooms.py measure, main 8e5aad2 against this)

| room | objects | kid | ticks | main 8e5aad2 | now | mean work: main / now | b (walking alone) |
|---|---|---|---:|---|---|---|---:|
| 5 / 24 | 2 choppers, 2 gates (3 buttons), potion, 2 torches | moves | 107 | 9.98 / 17.34 / 26.07 | **7.72** / 17.31 / 23.04 | 9.81 / 9.59 | 3.99 |
| 5 / 24 |  | stands | 98 | 10.27 / 17.36 / 17.48 | **10.27** / 17.36 / 17.50 | 9.29 / 9.30 | 3.99 |
| 10 / 1 | 4 gates (one at a palace pillar: the old way), level door, loose floor, 2 torches | moves | 98 | 11.75 / 20.45 / 32.58 | **9.90** / 16.87 / 23.29 | 11.28 / 9.62 | 3.99 |
| 10 / 1 |  | stands | 98 | 3.99 / 18.95 / 33.86 | **3.99** / 15.32 / 29.90 | 9.57 / 8.04 | 3.99 |
| 7 / 19 | 4 gates (4 buttons), spike, 3 torches | moves | 118 | 10.64 / 14.84 / 22.16 | **7.99** / 13.29 / 22.17 | 10.77 / 9.28 | 4.00 |
| 7 / 19 |  | stands | 98 | 5.17 / 11.25 / 13.24 | **5.17** / 9.29 / 11.37 | 7.23 / 6.50 | 3.99 |
| 5 / 8 | 2 gates (3 buttons), 3 torches | moves | 93 | 10.98 / 13.89 / 22.44 | **9.59** / 13.33 / 19.77 | 11.05 / 9.35 | 4.00 |
| 5 / 8 |  | stands | 98 | 5.12 / 12.57 / 15.67 | **5.12** / 8.97 / 13.94 | 7.78 / 6.17 | 3.99 |
| 7 / 7 | 2 gates (dungeon pillars), loose floor, 3 torches | moves | 54 | 10.97 / 14.44 / 21.20 | **8.91** / 11.96 / 17.77 | 10.96 / 9.16 | 3.99 |
| 7 / 7 |  | stands | 98 | 5.18 / 13.37 / 15.95 | **5.45** / 10.90 / 13.35 | 7.89 / 6.97 | 3.99 |
| 9 / 1 | chopper, 2 gates (one at a pillar), torch | moves | 45 | 12.03 / 17.88 / 20.83 | **9.75** / 14.97 / 16.80 | 11.97 / 10.02 | 4.02 |
| 9 / 1 |  | stands | 98 | 6.95 / 13.12 / 16.24 | **4.99** / 11.29 / 16.16 | 7.34 / 6.47 | 3.99 |
| 9 / 22 | 2 gates (one at a pillar), 2 spikes, torch | moves | 41 | 10.76 / 14.63 / 17.70 | **8.32** / 13.53 / 16.60 | 10.71 / 8.91 | 3.98 |
| 9 / 22 |  | stands | 98 | 3.99 / 10.94 / 13.55 | **3.99** / 8.55 / 10.82 | 5.69 / 4.90 | 3.99 |
| 2 / 18 | gate (a pillar), loose floor, potion, 2 torches | moves | 48 | 11.50 / 17.94 / 21.59 | **9.49** / 14.94 / 18.43 | 11.89 / 10.20 | 4.11 |
| 2 / 18 |  | stands | 98 | 4.64 / 4.66 / 15.30 | **4.64** / 4.66 / 14.96 | 4.79 / 4.78 | 3.99 |
| 1 / 5 | gate, loose floor, potion, 3 torches | moves | 74 | 9.23 / 12.09 / 16.53 | **7.04** / 9.90 / 17.11 | 9.38 / 7.81 | 4.00 |
| 1 / 5 |  | stands | 98 | 6.35 / 11.60 / 16.31 | **5.91** / 9.12 / 16.63 | 7.40 / 6.29 | 3.99 |
| 5 / 7 | 4 gates, level door, potion, 2 torches | moves | 118 | 6.95 / 14.00 / 27.21 | **6.96** / 10.40 / 23.90 | 9.15 / 7.82 | 3.99 |
| 5 / 7 |  | stands | 98 | 5.99 / 13.30 / 27.21 | **5.99** / 9.96 / 23.90 | 8.96 / 7.45 | 3.99 |

The cost model refitted (`fit` over the 4,300 ticks of these scenes, frames of work a change; main 8e5aad2 / now):

| change | ticks | main | now |
|---|---:|---:|---:|
| torch | 2572 | 0.63 | 0.64 |
| potion | 1086 | 0.68 | 0.54 |
| chomp | 221 | 6.15 | 6.21 |
| chomp- | 373 | -0.06 | -0.03 |
| gate | 1296 | 5.98 | **3.87** |
| gate- | 368 | 0.16 | 0.21 |
| spike | 42 | 5.38 | 5.62 |
| spike- | 44 | 0.43 | 0.22 |
| loose | 20 | 2.94 | 3.08 |
| door | 10 | 1.43 | **0.96** |
| button | 101 | 5.13 | **3.56** |
| tile | 4 | 7.79 | 7.59 |

Where the gate's 3.87 goes (the plan expected ~1.9): the 1,043 visible gate steps of these scenes (walk_a and
stand_a, the kid in the room; kidsim's states) are 37 % open steps (~1.9 frames each with the object pass: gate_push
tick 183's step 1.52 + ~0.4), 5 % open steps that regenerate the bars tile (~2.5), 22 % at a dungeon pillar (~2.8,
the base laid again ~0.9), 17 % closed steps (min(p) <= 12: ~3.4, the contact band's run_rect ~1.5) and 8 % closed at
a pillar (~4.3), and the old way: 9 % at a palace pillar (l10r01: ~6), 3 % drops (|k| > 1, the l07r19 and l02r18
scenes: ~10) and 2 % steps to or from 47 (~6). Weighted, ~3.3 a step; the fit adds what overlaps the kid's own work.
Overlay loads: l07r19_walk_a 42 in 118 ticks (94 ticks none, 13 two), l01r05 40, l07r07 10, l10r01 12 (counted at
ovl_load): room draws after a death, the button overlay and the gate overlay after it; ~0.1 frames a tick on
average. What would take the rest: the closed steps without run_rect (the floor drawn before the bars shows below
their bottom: the revealed rows from cached floor pictures, fix A's mechanism, or the band's few pieces laid directly),
the palace pillar (its base does not cover what the shift moves: a masked shift), and drops (a k-row shift: the top k
rows from the slice texture). The door is 10 ticks here (the level door below is the measurement). button mixes the
first press after a room draw (a miss, ~4-4.5) with the cached ones (~0.5-0.8; +0.3 when the gate overlay comes back
the tick after); these scenes die and draw the room again often (l07r19: 3 misses, 7 hits in the profiled ticks).

### gate_push and the level door (tools/tickcost.py, 1 MB)

| | main: median / p90 / worst | now | mean: main / now |
|---|---|---|---|
| gate_push 200-260, the 15 visible gate steps (a closing gate) | 9.79 / 12.89 / 14.30 | **6.31** / 7.82 / 9.00 | 10.48 / 6.79 |
| gate_push 200-260, all 60 ticks | | | 4.99 / 4.10 |
| walk_level1 203-207, the level door opening | 15.51 / 18.17 / 18.17 | **9.26** / 9.45 / 9.45 | 16.09 / 8.60 |

walk_level1 tick 204 (a door step): 14.21 -> 7.43 frames, the door step 2.51 (the three restores 0.99, the shadow
write 0.70, the merge of the sixth byte, the two clipped pieces); 206 (a slice goes: the tile regenerated, 1.54)
18.17 -> 9.45; 203 (0 -> 1, regenerated) 18.08 -> 9.35. The kid stands on the exit's plate meanwhile: with
trigger_button only in the events overlay these ticks cost 0.6 frames more (both overlays loaded every tick).

### perfcheck (one run per size; main = 8e5aad2)

| Stretch | 512 KB main / new | 1 MB main / new | 16 MB main / new |
|---|---|---|---|
| normal tick (walkthrough 30-60) | 5.72 / 5.72 | 5.20 / 5.20 | 5.03 / 5.03 |
| level door step (walkthrough 203-207) | 17.16 / **9.23** | 16.23 / **8.54** | 16.23 / **8.54** |
| room change (walkthrough 89) | 106.05 / 106.05 | 106.05 / 106.05 | 105.22 / 105.22 |
| walkthrough 190-260 | 10.26 / **6.44** | 10.07 / **6.19** | 9.68 / **5.85** |
| gate (gate_push 200-260) | 4.99 / **4.10** | 4.99 / **4.10** | 4.99 / **4.10** |
| traps (traps_b1 0-300) | 5.63 / 5.64 | 5.30 / 5.31 | 5.23 / 5.23 |
| fight (fight1 60-160, guard on) | 7.72 / **7.17** | 6.88 / **6.36** | 6.51 / **5.98** |

The bold baselines are lowered (fight1: a guard stands on a closer, its presses and releases come from the cache). The
+0.01 are the beam phase (the same ticks summed by tools/tickcost.py are equal; the 512 KB normal tick measured 5.75 on
one build of this part, 5.72 on the others). With the button code resident in main the level door measured 8.43 /
8.51 / 9.14; in its own overlay its first step loads it.

### Same pixels, same logic

tests/m4_game.py --every 1 (state and VRAM every tick): gate_push, walk_level1, l02_open_a / c, l04_open_a / c,
l04_thr_a, l07_open_a, l09_open_a, l04_drop_a, l07_drop_a, l10_drop_a, btn_bars, fight1, the walk_a scripts of all ten busy rooms above
and the stand_a of l07r07, l07r19, l09r22, l10r01, l05r07, l05r08, l01r05, traps_b1, traps_b9, level12_exit_level13 and
level13_exit (two more dungeon exit doors): 0 state diffs, 0 differing pixels. tests/m4_test.py (the logic, Z80 against
kidsim, tick-exact) on gate_push, traps_b1 / b9 / b39 / b40, walk_level1, random1-3, level4_mirror,
level5_shadow_potion, level6_shadow_exit, level12_shadow_merge / hit: 0 differing. tools/movecheck.py: 0 differences.
`make ci-build`, `make cheats`. The full regression on the runners: see the PR.

Faults found on the way, fixed: (1) a button regenerated its right neighbour, a spike that changed in the same tick,
whose own redraw then found no difference to lay (l07r19 tick 53): the button's dirty rect now includes the
regenerated records' rects, and nothing is cached then; (2) perfcheck's fight1 (level 4, a guard on a closer: a press
or release every 3-4 ticks) got 0.05 frames a tick slower: no palace button was ever cached, as their stripe records
reach out of the rect; now kept (the picture read back from the shadow); (3) a closing step laid the frame slice over the
moved row GT, but the Z80 copies only the slice's extent (20 of its 24 pixels in the dungeon) and the rest showed the
row above the gate (l02_open_a tick 102): row GT now keeps the old row under the slice, and tools/movecheck.py paints
laid pieces with the Z80's extents (it had painted all 24 pixels, as the reference does, and missed it).

(4, found in review on PR #30) a slot's entry was filled from the wrong 6 bytes (its rect and two scratch bytes instead
of the rect and the tiles' tags), so a regeneration of the button's tile did not drop it (btnstep.asm: bs_r and bs_t
are now one 6-byte block, an assembly check keeps them so). The pixel tests had not hit it: it needs a gate whose bars
tile is the button, a cached press, then a gate step that regenerates the tile without touching the button's rect
(a slice-count change while the gate is open), then the next press or release. tests/m4_scripts/btn_bars.txt (level 8
room 15: the opener right of the gate; found with kidsim and a model of the cache) runs the button through presses,
releases and regenerating gate steps, pixel-exact every tick; with the fix the entry holds the tags (16, 17).

## M8a part 15: chopper and spike frames (2026-11-07)

Status: **built.** Option A of the busy-rooms measurement ("Busy rooms: per-room and per-object costs"): a chopper's or
a spike's picture step copies a pre-drawn picture of its rect from the RAM disk instead of laying the pieces again,
and patches the pieces' records in place instead of regenerating the tile. The code is a new W1 overlay (the frames
overlay, 13: src/m4/frames.asm through src/m4/ovl_frm.asm, 1,020 bytes, image in RAM-disk page 0 0xA400) entered from
spike.asm chomp_redraw / spike_redraw (our room's own choppers and spikes, VS_KIND 0; the other rooms' and a chopper
with blood go the old way), on top of part 14's resident cs_put / dirty_hook / room_drawn.

### What stays exact (tools/movecheck.py chompers, spikes)

- **The rect.** Between any two pictures of a chopper only the rect x 4c..4c + 3, rows 63r + 3..63r + 62 changes (the
  shadow's pixels to row 60, the fore pieces' rects to row 62); of a spike x 4c..4c + 5 (to 40), rows 63r + 34..63r +
  60 (its right part is drawn by the right neighbour). Checked on the reference for all 39 choppers and 120 spikes of
  levels 1-14 seen in their own room, every ordered pair of pictures (780 + 3,600 steps): the old picture with the
  rect taken from the new one is the new one, whole screen, and the fore ops that change lie in the rect: 0 differ.
  All four planes change, so a picture is the whole rect: 960 bytes (4 x 60 x 4), a spike's 648 (6 x 27 x 4).
- **The pictures.** A chopper's picture n = CHOMPER_FRAM1[min(mod & 0x7F, 6)] (5 pictures), a spike's spike_frame
  0..9 with equal images merged (0 = 9, 1 = 8, 2 = 7, 4 = 6: 6 pictures).
- **The records.** What changes between two pictures is the object's pieces only, at the same place in the same list:
  a chopper's bottom (101-105), top (111-113) and fore (106-110), a spike's left part (128-132), fore (139-143) and the
  right neighbour's 134-138; their bottom rows stay (a chopper's top is CHOMPER_FRAM_Y[n] above its bottom piece's
  bottom). The exceptions are a piece that comes or goes: a chopper's top at n 0, 1 (2 of its 5 steps), a spike's
  picture 0 (2 of 9). Then the tile is regenerated as before (and the spike's right neighbour). Checked with the rect.

### The step (frames.asm frm_step)

1. The object's entry in FRM_TAB (low RAM 0x09DB: 4 objects, the first ones stepping after a room draw; its rect, its
   valid pictures, its slots), else a free one: it takes its slots (below).
2. Records: patched in place (op_patch's find, the id, size and top row written, the slice's extent widened), or the
   tile(s) regenerated. A patched fore record over a torch flame (flm_touch) bumps fore_gen (the torch pictures with
   fore pieces in them go); a patch leaves ops_gen alone, so the torch registry is not rescanned and the torch picture
   cache (tcache.asm) is not flushed: before, every chopper step flushed it.
3. Pixels: the picture valid: its slot read into SPRBUF_B (an INI chain per row, ~0.3 frames for 960 bytes) and put
   (cs_put: the shadow, the dirty list, the object pass's kept background); else the dirty rect is the rect, dr_run lays
   it (one chunk: its picture stays in SPRBUF_B) and the picture is written to its slot.
4. Validity: frm_drop (main, called by anires.asm dirty_hook: every dr_run of the room renderer and every cs_put)
   drops every picture of an object whose rect the redrawn rect touches; the object's own redraw keeps its others
   (pictures of the same background); a room draw clears everything (room_drawn -> frm_reset). Two committed scripts
   exercise it: tests/m4_scripts/frm_button.txt (level 10 room 10: a closer pressed next to the chopper; without the
   drop tick 21 differs) and frm_spike_btn.txt (level 7 room 19: a closer and moving gates next to a spike; without it
   tick 82 differs).

### The slots (memory)

- **16 MB:** page FRM_P16 = 62 (free after the frame store), 1 KB a slot, six per object: every picture of 4 objects.
- **512 KB and 1 MB:** nothing in pages 8-15 (the frame store's, as decided for 1 MB). The free pieces of pages 0-7
  that exist on every size: 15 chopper-sized slots (960 bytes: page 4 0xE000-0xFDFF x 8, page 0 0xE868 x 2 and 0xFC00,
  page 6 0x2880 x 2 and 0xF964, page 1 0xDA58) and 5 spike-sized ones (648: page 6 0xFD24, page 1 0xFC5C and 0x7D00,
  page 5 0x3AD0 x 2), 17,640 bytes in 13 pieces (frames.asm fs_bdir / fs_sdir; tests/m5_boot.py RUNTIME_SCRATCH reads
  them from the overlay's image). A chopper takes five big slots, a spike six small ones, else six big ones, else what
  is left; pictures without a slot are drawn the old way every time. What the rooms need (pictures, 960 / 648 bytes):
  l03r16 (3 choppers) 15 big: all; l05r24, l08r23, l10r10 (2 choppers, + a spike in l08r23): all; l08r04 (2 choppers,
  2 spikes) 22 pictures: 20 (the second spike 4 of 6); l10r14 (1 chopper, 3 spikes) 23: 20; the six 4-spike rooms
  24: 20. Page 4's slots start at FRM_P4 = 0xE000, after the game image's second piece (0xD400-0xDD2F today;
  tools/mkgamedisk.py asserts it ends below FRM_P4). Page 1 0xE918-0xFC5B stays the button cache's.
- **Resident:** main +97 (end_of_code 0x7A56 -> 0x7AB7, 329 free: frm_drop with its early exit, frm_reset, the stub,
  the calls in chomp_redraw / spike_redraw), block 2 +3 (dirty_hook calls frm_drop; 14 free), the low block unchanged.
  Data: FRM_TAB 0x09DB-0x09FC (34 bytes) and the step's variables 0x09A6-0x09B3 (low RAM, runtime only; RV, the room
  renderer's variables, ends at 0x09A5, not 0x09A3 as docs/memory.md had it: a first build put variables at 0x09A4,
  which rr_table overwrites). The overlay table +8 bytes (page 7: 743 free).

### The prototype (measure first)

The first build regenerated the tile on every step and laid nothing on a hit (cs_put of the cached picture). 16 MB,
l03r16_stand_a tick 45 (one chopper step, the kid next to it): 4.97 -> 8.48 frames against 4.97 for the same tick
without a step; the step 1.87 (own_regen 0.60, the slot read 0.55, cs_put's shadow write 0.69), the object pass over
the kid +1.6 (the chunk's fore pieces, the kid composed into it, the copy). The estimate (~2.0-2.5 for the step and the
object pass) had no regeneration. So the records are patched where no piece comes or goes, and the slot read is an
unrolled INI chain: the same tick now **7.97** (1 MB), the step **1.25** (read 0.42 with the scans, cs_put 0.72); a
step that regenerates (2 of 5) 2.03 (tick 46: 8.96). What is left over the kid is the object pass (~1.7), which every
redraw of that rect pays (option E's subject).

### The busy rooms (1 MB, frames a tick: median / p90 / worst; tools/busyrooms.py measure, main 1ba17ed against this)

| scene | ticks | main | now | mean work: main / now | b |
|---|---:|---|---|---|---:|
| 3 / 16 (3 choppers) moves | 118 | 10.96 / 16.99 / 20.06 | **8.79** / 14.00 / 17.62 | 11.31 / 9.33 | 3.99 |
| 3 / 16 (3 choppers) stands | 98 | 10.78 / 16.81 / 16.95 | **7.99** / 12.29 / 16.94 | 10.80 / 8.79 | 3.99 |
| 5 / 24 (2 choppers, gates) moves | 107 | 7.72 / 17.31 / 23.04 | **7.50** / 12.94 / 23.78 | 9.59 / 8.35 | 3.99 |
| 5 / 24 (2 choppers, gates) stands | 98 | 10.27 / 17.36 / 17.50 | **8.42** / 12.96 / 18.38 | 9.30 / 8.04 | 3.99 |
| 8 / 23 (2 choppers, spike) moves | 118 | 9.59 / 16.31 / 17.94 | **6.79** / 10.95 / 16.86 | 8.59 / 6.94 | 4.00 |
| 8 / 23 (2 choppers, spike) stands | 98 | 9.54 / 16.41 / 16.94 | **6.64** / 10.97 / 16.60 | 8.27 / 6.48 | 3.99 |
| 10 / 10 (2 choppers, gate) moves | 43 | 10.18 / 19.87 / 28.36 | **7.95** / 17.87 / 26.91 | 10.52 / 9.99 | 4.02 |
| 10 / 10 (2 choppers, gate) stands | 98 | 9.06 / 15.56 / 26.26 | **7.32** / 12.07 / 27.32 | 8.22 / 7.18 | 3.99 |
| 8 / 4 (2 choppers, 2 spikes) moves | 118 | 9.39 / 15.40 / 16.94 | **7.59** / 12.48 / 15.48 | 8.64 / 7.46 | 4.04 |
| 8 / 4 (2 choppers, 2 spikes) stands | 98 | 8.84 / 14.77 / 14.95 | **6.69** / 11.01 / 14.97 | 7.66 / 6.52 | 3.99 |
| 9 / 22 (gates, 2 spikes) moves | 41 | 8.32 / 13.52 / 16.60 | **8.33** / 13.11 / 18.30 | 8.91 / 9.06 | 3.98 |
| 9 / 22 (gates, 2 spikes) stands | 98 | 3.99 / 8.55 / 10.82 | **3.99** / 8.57 / 10.76 | 4.90 / 4.90 | 3.99 |
| 10 / 14 (chopper, 3 spikes) moves | 118 | 5.15 / 11.46 / 12.27 | **5.16** / 8.74 / 10.92 | 6.96 / 6.08 | 4.01 |
| 10 / 14 (chopper, 3 spikes) stands | 98 | 3.99 / 10.17 / 10.95 | **3.99** / 7.66 / 10.03 | 6.05 / 5.16 | 3.99 |
| 9 / 1 (chopper, gates) moves | 45 | 9.75 / 14.97 / 16.80 | **9.55** / 15.56 / 16.78 | 10.02 / 9.51 | 4.02 |
| 9 / 1 (chopper, gates) stands | 98 | 4.99 / 11.29 / 16.16 | **4.98** / 9.16 / 14.48 | 6.47 / 5.85 | 3.99 |

The 16 MB run of the same scenes (the prototype build, which regenerated every step): l03r16 8.96 / 8.60, l05r24 7.36
/ 9.15, l08r23 7.23 / 7.41, l10r10 8.18 / 8.02, l08r04 7.86 / 7.96 (moving / standing medians). The busy scenes have
few spike steps (the kid rarely sets them off): the l09r22 / l10r14 differences are the chopper and the torch cache
(no flush at a patched chopper step).

The cost model refitted over the same 4,120 ticks (`fit`, frames of work a change; main / now): **chomp 6.09 -> 4.12**,
chomp- 0.08 -> 0.06, torch 0.49 -> 0.52, potion 0.63 -> 0.54, gate 3.96 -> 4.10 (277 ticks, the alternation with the
frames overlay in W1: below), button 3.40 -> 3.28, spike 4.51 -> 4.94 (14 ticks: noise). The chomp mixes the misses
(the first cycle after each room draw: the scenes die and restart often) with the hits.

### Spikes (tools/tickcost.py --scene, 1 MB, frames a tick with a spike picture change and the kid moving, median /
p90 / worst; before = this build with the frames overlay off, i.e. main's path)

| scene | ticks | before | now | excess before / now |
|---|---:|---|---|---|
| l14_spike (a) | 9 | 10.42 / 11.58 / 11.68 | **9.57** / 10.57 / 12.55 | 5.76 / 4.22 |
| l06_spike (a) | 13 | 10.70 / 13.54 / 16.14 | **9.16** / 11.00 / 11.61 | 2.05 / 0.94 |
| l08_spike (a) | 18 | 10.89 / 12.56 / 17.16 | **9.43** / 11.56 / 13.27 | 3.65 / 2.54 |

A spike's cycle is 9 picture changes, of which the first 5 after a room draw are misses (0 -> 1 .. 4 -> 5: laid, then
saved) and the 4 back down hits (5 -> 4 -> 2 -> 1 -> 0, the pictures it rose through); 0 -> 1 and 1 -> 0 regenerate (the
pieces come and go). These scenes set a spike off once or twice, so most of their steps are misses; a spike that keeps
cycling (the kid standing next to it) is all hits from its second cycle.

### Overlay loads

The frames overlay is a W1 overlay: in a room where a gate moves while a chopper cycles, the gate and the frames
overlays alternate (~0.3 frames a load, 1,020 bytes). The W1 window has no room for both (the gate overlay has 10
bytes free, the frames overlay 4), and main has 329 bytes free. In the chopper rooms with a gate (l05r24, l08r23,
l10r10, l09r01) that costs ~0.6 per chopper step while the gate moves; the gate's model cost went 3.96 -> 4.10.

### perfcheck (one run per size; main = 1ba17ed, the baselines)

| Stretch | 512 KB main / new | 1 MB main / new | 16 MB main / new |
|---|---|---|---|
| normal tick (walkthrough 30-60) | 5.72 / 5.75 | 5.20 / 5.20 | 5.03 / 5.03 |
| level door step (walkthrough 203-207) | 9.23 / 9.23 | 8.54 / 8.54 | 8.54 / 8.54 |
| room change (walkthrough 89) | 105.92 / 106.06 | 105.92 / 106.06 | 105.22 / 105.57 |
| walkthrough 190-260 | 6.44 / 6.45 | 6.19 / 6.17 | 5.85 / 5.83 |
| gate (gate_push 200-260) | 4.10 / 4.10 | 4.10 / 4.10 | 4.10 / 4.10 |
| traps (traps_b1 0-300) | 5.63 / 5.64 | 5.30 / 5.31 | 5.22 / 5.23 |
| fight (fight1 60-160, guard on) | 7.17 / 7.19 | 6.36 / 6.33 | 5.98 / 6.00 |

No chopper or spike in the stretches; the differences are the beam phase (the 512 KB normal tick measured 5.75 on a
build of part 14 too; the room change is one tick, its 16 MB value was 105.23 on an earlier build of this part).
frm_drop exits at once while the room has no chopper or spike stepping (the first entry free). No baseline lowered.

### Same pixels, same logic

tests/m4_game.py --every 1 (state and VRAM every tick) at 512 KB, 1 MB and 16 MB: chomper, fight_chomper,
fight_spikes, the l14_spike_a, l06_spike_c and l08_spike_a scenes, frm_button, frm_spike_btn, traps_b1, and the walk_a
and stand_a scripts of l03r16, l05r24, l08r23, l08r04, l10r14, l09r22, l09r01, the stand_a of l10r10 and the walk_a of
l01r15 (25 scripts a size): 0 state diffs, 0 differing pixels. tests/m4_test.py on chomper, fight_chomper, frm_button,
frm_spike_btn: 0 differing. tools/movecheck.py chompers, spikes: 0 differ. `make ci-build`, `make cheats`. The full
regression on the runners: see the PR.

## Option E: measured (2026-11-07)

Status: **measured, nothing merged.** Option E of "Busy rooms: per-room and per-object costs" (the exclusive animated
layer: the shadow keeps the room without the moving parts, every chunk that touches an animated object lays its current
picture after the restore, as flames_lay does for torches), measured on main 4d375f2 (C #29, D #30, A #31), 1 MB, no
waits, in the six busy rooms l03r16, l05r24, l08r23, l10r10, l10r01 and l07r19 (tools/busyrooms.py find / measure).

**Tools** (committed): tools/optione.py `profile A B TICKS` (per stage, the inclusive frames of one tick in script A,
in B and A - B: the redraw with its regenerations, run_rect, shadow writes and overlay loads; people_place; the object
pass's chunks with their restore, flames, torch cache, people and fore pieces; the copy to VRAM; the beam wait),
`diff` (the routines that differ most), `chunks` (the object pass's chunks of a tick), `touch A LEVEL ROOM` (the chunks
that touch an object's rect without being its own step: E's extra work), `census` (every animated object of levels
1-14 on the Python reference: which static ops lie over its moving part) and `model`. The prototype is on the branch
**proto/option-e** (pushed, not a PR, not exact). It has three build switches, `make -B m4game E1=1 E2=1 E3=1`:

- **E1**: anires.asm cs_put writes no shadow. Every cs_put step (a chopper or spike hit, a gate or door step, a cached
  button) only puts the picture on the dirty list as the kept background.
- **E2**: sprite.asm obj_chunk takes a kept chopper chunk (4 x 60) or spike chunk (6 x 27) as complete when there is
  no kid and no falling floor in it. No people and no fore pieces are laid, as if the slot held the picture with its
  fore pieces.
- **E3**: tcache.asm tc_hit (a torch chunk from the torch cache: no kid, nothing else in it) reads the slot from the RAM
  disk straight into VRAM. There is no compose buffer, no pending chunk and no beam wait (68 bytes, spike.asm
  e_tdirect).

The pixels are wrong (the shadow goes stale, the fore pieces are missing), so these builds measure cost only. The logic
is unchanged, so the scenes run the same ticks.

### 1. Where the time goes now (tools/optione.py profile; frames of the tick in the scene's only-kind variant minus walk_b; 1 MB)

| step (scene, tick) | redraw: of it shadow write / run_rect / regen | chunks: restore / people / fore | copy | wait | work |
|---|---|---|---:|---:|---:|
| chopper hit, nobody in its rect (l08r23_stand_a 30) | 1.38: 0.70 / - / - (the slot read and patches 0.68) | ~1.0 people, ~1.0 its fore pieces | ~0.4 | 0 | **2.68** |
| chopper hit, the kid beside it (l03r16_walk_chomper 20) | 1.25: 0.70 / - / - | +1.87: 0 / 0.27 / 1.58 | 0.48 | 0.32 | 3.25 |
| two chopper hits, the kid at them (l03r16 18) | 3.48: 1.39 / - / - | +7.25: 0.61 / 1.30 / 2.93 | 0.95 | 1.88 | 9.8 |
| spike hit (l07r19_walk_spike 82) | 0.77: 0.38 | +1.59: - / 0.42 / 0.39 | 0.27 | 0.37 | 1.9 |
| gate open step (l07r19_walk_gate 30, 36) | 1.0-1.1: 0.42-0.48 / - / - | +0.8 (the kept column, no restore) | 0.3 | 0 | ~2.1 |
| gate step that regenerates the bars tile (26) | 2.23: 0.52 / - / 0.88 | +0.9 | 0.34 | 0.05 | ~3.5 |
| gate closed step: the contact band (13) | 3.04: 0.68 / 1.71 / - | +1.9: 0.45 / 0.13 / 0.06 | 0.44 | 0.47 | ~5.9 |
| gate the old way: palace pillar (l10r01_walk_gate 20, 30) | 7.4-9.2: 1.2 / 4.3-4.8 / 0.9-2.5 | +3-4: 0.6-1.0 / 0.9-1.1 / 0.8-1.0 | 0.8 | 0.3-0.9 | 10-13 |
| level door step (walk_level1 204, the whole tick) | 2.66: 0.69 | 2.73 (with the torches' chunks) | 1.11 | 0.24 | 7.48 a tick |
| button press, cached (part 14: 0.52) | of it the shadow write 0.42 | | | | 0.52 |
| potion bubble (l03r16_walk_potion 25, 30) | 0.06 | +0.34: 0.08 / - / 0.20 (the bubble) | 0.05 | 0.04 | 0.45-0.5 |
| two exclusive torches, cached (l03r16_walk_torch 25, 30) | 0.06 (torch_fast) | +0.26 (tc_try's read 0.20) | 0.23 | 0 | 0.36-0.57 |
| torch behind a gate's bars (l07r19_walk_torch 30: p26, next to the gate p27) | 1.04: torch_redraw, run_rect 0.88 (the room cache's replay 0.57) | | | | **~1.2-1.4** a tick |

What E can remove:

- the shadow write of every cs_put step: 0.4-0.7 a step (choppers, spikes, gates, the door, cached buttons);
- for a chopper or spike with nobody in its rect, the people and fore passes over the picture: 1.0-2.5 (the chopper's
  own fore pieces are 60-row masked pieces, ~0.75 each);
- for small cached rects (flames, bubbles), the chunk and the copy through a compose buffer: ~0.2 a torch.

What it cannot remove:

- the people and the fore pieces when the kid is in the rect (he must go between the layers);
- a miss (the first cycle after a room draw, which takes today's dr_run);
- the gates' top band, contact band, regenerating steps and the old-way gates (these are run_rect and regenerations,
  not shadow writes);
- the beam wait (it follows the chunks' sizes and the kid's chunk).

### 2. The mechanism in this codebase

- **The shadow without the moving parts.** The op lists do not separate the moving parts. An object's pieces are
  ordinary back, mid or fore records (flags, chtab, id, x, y, w, h) of the tile that draws them, found by tag and id
  range: choppers 101-113, spikes 128-143, gates 50-68 and the frame slice, the door 33 / 34 / 99 / 144, flames CH_OBJ
  1-9, bubbles in the fore list. A full E marks them (a free flag bit, set by room_ops and tile_gen). run_rect's
  shadow write (rr_sw) and run_ops (the room draw) skip the marked back and mid records. flames_build's registry
  (flm_rec, 8 entries) becomes an object registry: the object, its rect, its records and its picture's source.
- **Which objects are exclusive** (`optione.py census`, the Python reference, each object over all its states). A
  layer is exclusive when no static back or mid op drawn after it touches its pixels (then nothing has to be laid
  again over it):

  | kind | exclusive | what lies over the others |
  |---|---:|---|
  | torches | 371 of 383 | 3 have chopper pieces 104 / 112 over them; 9 touch only by rect |
  | choppers | 39 of 39 | |
  | potions | 56 of 56 | |
  | the sword | 3 of 3 | |
  | spikes | **14 of 120** | 106 have the right neighbour's 133 or a wipe over them |
  | gates | **3 of 38** | the floor pieces 41 / 43 where the bars meet the floor, the pillar bases 92 / 147 / 149, the top 68 / 48 |
  | level doors | **0 of 28** | the frame 34, 37-40 and 99 |
  | loose floors | 17 of 172 | |

  Exclusivity also changes with another object's state. 9 torches stand left of a gate (l01r07, l04r07, l04r08,
  l04r24, l05r07, l05r10, l07r03, l07r07, l07r19), and the bars, drawn after the flame, cover it while the gate is
  down. The census (one object varied at a time) calls them exclusive; the Z80's registry (record rects, the current
  state) does not. l07r19's torch p26 costs 1.2-1.4 frames a tick for that.
- **How each chunk lays them.** After restore_shadow (or instead of it), for each registered object whose rect the
  chunk touches, the chunk lays:
  - a flame: its record (rec_lay, as today);
  - a chopper or spike: its slot (fix A's picture: the background with the object, i.e. what the shadow would hold);
  - a gate: a strip (the bars are rigid and opaque: one picture of the column, read at the gate's offset), then its
    over pieces laid again.

  `touch` measured how many such chunks there are. While the kid walks: chopper rects 0.3-0.6 chunks a tick (68-106
  bytes a plane of overlap each), gate columns 0.3-0.4 (57-107 bytes), spikes 0.5 (l07r19), flames 0.1-0.3 (7-16
  bytes; l08r23_stand 1.0). While he stands there are none, except l08r23's flame. What each costs:
  - from a slot, a second read of the overlap rows instead of the shadow's: ~0.05-0.2 a chunk (a seek per plane row);
  - from pieces, two masked 60-row pieces: ~0.5 a chunk;
  - for a gate, the strip plus its over pieces: the contact band and the pillar base again in every chunk, ~1-2.
- **A step becomes "mark the rect dirty"** (E1, what the prototype measures). The step patches its records (as C, D
  and A do) and puts its rect on the dirty list; the chunk takes the picture from the slot (or the strip) in place of
  the restore. Without a full E, the same saving is exact for every object whose picture is cached: the shadow is
  allowed to go stale under a registered rect (a **lazy shadow**). restore_shadow then takes that rect's rows from the
  current slot, and a dr_run into the rect first writes the slot back; the slot's bytes are the shadow's by
  construction. The gates and the door do not fit this: their next step shifts the shadow itself (D's cs_get), so
  skipping their write needs the strip.
- **The direct VRAM path** (E3). A chunk that is exactly a cached small rect with nothing in it (today tc_try's
  condition) goes from the RAM disk into VRAM by INI, plane by plane (e_tdirect: 4 planes x 18 rows of 2 bytes). In a
  real build it must be a pending entry, so that pend_flush times it against the beam (+~30 bytes). The same holds for:
  - a potion bubble (1 x 9 over black: a 7-frame cache like the torch's);
  - a chopper or spike picture with its fore pieces (E2) when nobody is in its rect (960 bytes: ~0.42 frames by INI,
    against today's slot read 0.42 + copy 0.48).
- **The changes by file:**
  - **room.asm**: a marked-record bit and its skip in rr_sw and run_ops; the dr_run write-back hook (lazy shadow).
  - **view.asm**: the flame registry generalized (objects, sources, exclusivity by the current state: a flame under a
    gate's bars is registered with the bars as its over records).
  - **overlay.asm / sprite.asm**: obj_chunk's per-object lay after the restore (flames_lay generalized), the
    complete-picture path (E2), and the direct path (E3) in pend_flush.
- **What C, D and A become:**
  - **C** stays: it decides that a picture changed.
  - **D** stays for gates and the door: their shadow write stays unless the strip is built.
  - **A** stays and becomes the restore's source. Its slots are still needed, and the complete pictures need more of
    them.

### 3. The prototype (proto/option-e; tools/busyrooms.py measure on the same scenes)

Frames of work a step: the tick in the scene minus walk_b, the same ticks in every build. Misses and steps that
regenerate are left out. The ticks: l08r23_stand_a 30, 35, 45, 60 and the like, l07r19_walk_spike 81-83, walk_level1
204 and the walk_torch scenes.

| step | now | E1 (no shadow write) | + E2 (nobody in the rect: complete picture) | + E3 | estimate |
|---|---:|---:|---:|---:|---:|
| chopper hit, nobody in its rect | **2.68** | 1.96 | **0.97** | 0.97 (direct copy: ~0.5, not built) | 1.0-1.5 |
| chopper hit that regenerates (a piece comes or goes) | 3.6 | 2.8 | 1.85 | | |
| two chopper hits in one tick (l08r23 18, 33) | 7.1 | 5.4 | 4.4 | | |
| spike hit (l07r19 81-83) | 1.25-1.89 | 1.14-1.24 | 0.50-1.14 | | |
| gate step (l07r19_walk_gate, all visible steps, median) | 3.20 | 2.91 | | | 1.0-1.5 |
| level door step (walk_level1 204, the whole tick) | 7.48 | 6.95 | | | |
| button press (l05r24 walk, median of its ticks) | 7.35 | 6.77 | | | |
| two exclusive torches (walk_torch scenes, median a tick) | 0.71-0.78 | | | **0.38** | 0.3 |
| three torches, one behind bars (l07r19_walk_torch) | 2.02 | | | 1.78 | |

The fitted costs (`busyrooms.py fit`, all ticks including misses; main / E1 / E1+E2 / E1+E2+E3):

| change | main | E1 | E1+E2 | E1+E2+E3 |
|---|---:|---:|---:|---:|
| chomp | 4.23 | 3.65 | 3.12 | 3.15 |
| gate | 4.44 | 4.18 | 4.19 | 4.27 |
| button | 3.05 | 2.93 | 3.03 | 3.09 |
| torch | 0.61 | 0.61 | 0.60 | **0.52** |
| spike (28 ticks, mostly misses) | 5.33 | 5.26 | 5.22 | 5.31 |

So E reaches its estimate in two cases: a chopper with nobody near it (2.68 -> 0.97, ~0.5 with the direct copy) and
exclusive torches (0.39 -> 0.19 a torch). It does not for gates (3.20 -> 2.91: what is left is the top band, the
contact band, the regenerating steps and the old way), nor with the kid in the chopper's rect (he is composed between
the layers either way).

E's extra cost on other chunks (section 2): from a slot, +0.05-0.2 per touching chunk; with 0.3-0.6 such chunks a tick
in the chopper rooms while the kid walks, that is +0.02-0.1 a tick. From pieces (no slot: the 512 KB / 1 MB spike
rooms, misses), +0.15-0.3 a tick.

### 4. Memory

The prototype: E1 -3 bytes (block 2), E2 36 bytes (main), E3 68 bytes (main). A real build must be resident, since the
object pass runs after view_redraw with any overlay in W1:

| part | resident bytes | where |
|---|---:|---|
| lazy shadow: restore_shadow's redirect to the slot (overlap rows, per plane), the write-back before a dr_run into a stale rect, the stale flags | ~160 | main (every chunk calls restore_shadow); FRM_TAB has no spare bit per object: +4 bytes of low RAM (0x09FD-0x09FF has 3) |
| complete pictures (E2): the capture after a chunk composed one (a tc_save for the chopper rect), the chunk's test (e_kept) | ~80 | main; the frames overlay has 4 bytes free (the slot choice would move out of it: ~0.3 a load) |
| the direct copy (E3) as a pending entry, the potion bubble cache | ~130 | main (e_tdirect 68 + pend_flush's branch ~30 + the bubble's cache entry ~30) |
| the torch under bars (flames_build registers a flame with the bars' records over it; the torch cache flushed at a gate step) | ~40 | the low block (view.asm, 20 free), or flames_build moved into main |
| full E for gates (the strip built, the over pieces laid in every chunk) | ~250 | the gate overlay has 10 free: a second overlay, and more W1 loads |

That is ~400 bytes without the gates, against main 329, block 2 14 and low 20, so a reclaim of ~100-150 bytes is
needed. Candidates: tc_flush / tc_save into the room overlay, which runs after every room draw; spike.asm's
anim_redraw dispatch into the frames overlay.

The W1 overlays do not help the object pass: any step overlay can be in W1 when the chunks run. The gate overlay and
the frames overlay (1,014 + 1,020 bytes) cannot share the 1 KB window, so the alternation that fix A reported (~0.3 a
load, ~0.6 per chopper step while a gate moves) stays. Moving trigger_button's 272-byte copies out of the gate and door
overlays into main would not make room for both either.

RAM disk:

- A's slots stay: they are the restore's source.
- Complete pictures double them (a chopper +5 x 960 bytes, a spike +6 x 648). On 16 MB, page 62 has room for them. On
  512 KB and 1 MB, part 15's 15 large (960-byte) + 5 small (648-byte) slots are already in use by A's pictures:
  a chopper takes 5 large slots, so l03r16 (3 choppers) uses all 15, and a 2-chopper room (l05r24, l08r23, l10r10)
  leaves 5, enough for one chopper's complete pictures. The small slots cannot hold a chopper's 960 bytes, and the
  spike rooms are already short (20 of 22-24 pictures). Without more slots, step 4 on 512 KB and 1 MB therefore
  covers no chopper in l03r16 and one of the two in the 2-chopper rooms; on 16 MB (page 62) it covers all.
- The torch's direct path needs nothing new (TC_PAGE 6). The bubble cache needs 56 x 36 = 2,016 bytes. It does not
  fit at page 6 0x2880: the two A slots there are 1,920 bytes and 0x3000 starts the dungeon guard set. It needs three
  of A's 960-byte slots (or a free piece of 2,016 bytes elsewhere: to be found in step 1's PR), which costs A one
  chopper's or several spikes' pictures on 512 KB and 1 MB.

### 5. Exactness

- **The lazy shadow and the complete pictures are exact by construction.** A slot holds the bytes dr_run wrote into
  the shadow (fix A; tools/movecheck.py chompers / spikes: 0 differ). A complete picture is the chunk's own composition
  when no person, falling floor or overlay op (OV_MID / OV_FORE) is in it, which is tc_try's rule for torches. The
  risks are in the order, not in the pixels:
  - a dr_run, cs_put or regeneration that touches a stale rect must write the slot back first (today dirty_hook runs
    after the shadow write: E needs a hook before it);
  - a complete picture must go with every frm_drop and every fore_gen change.
- **The full exclusive layer is not exact for most gates, spikes and doors unless their over ops are laid again** (the
  census above). The hard cases:
  - **a fore piece over a chopper** (its own fore pieces 106-110 and the floor's fore pieces): no problem. They are
    fore, laid by every chunk after the people, as today.
  - **the kid between layers**: SDLPoP's redraw_at_char2 overlays lay a tile's base and its spike or chopper parts
    over him. They come from the op records, which C, D and A keep current, so the overlay pass is unchanged.
  - **a gate with the kid in it**: the bars are behind him, but the floor pieces 41 / 43 and the pillar base 92 are
    drawn after the bars and over them. Every chunk with the kid in the gate column must lay them again (~1-2 frames),
    which D pays once per step.
  - **a torch behind a gate's bars**: two layers in one rect (the flame, then the bars' rows, then the fore).
- The Python reference renders from the level state. The layer order back, objects, sprites, fore is SDLPoP's as long
  as every chunk lays the layer's records in their list order and the over ops after them. The tests that would cover
  it: the busy rooms' a and stand scripts at --every 1 (25 a size in part 15), plus the 9 torch-by-gate rooms.

### 6. Projected (1 MB, frames a tick, median / p90; "E1+E2+E3" is the prototype measured, cost only)

| scene | now | E1+E2+E3 measured | reduced E projected (below) | mean work now / E1+E2+E3 |
|---|---|---|---|---|
| 3 / 16 walk | 8.81 / 14.00 | **7.40** / 12.95 | ~6.6 / ~12 (16 MB); ~7.6 (512 KB, 1 MB: no step 4) | 9.33 / 8.13 |
| 3 / 16 stand | 7.98 / 12.29 | **6.00** / 10.01 | ~5.3 / ~9.5 (16 MB); ~6.3 (512 KB, 1 MB) | 8.80 / 7.43 |
| 5 / 24 walk | 7.50 / 12.94 | **6.67** / 10.95 | ~6.1 / ~10.5 (16 MB); ~6.4 (1 MB) | 8.36 / 7.64 |
| 5 / 24 stand | 8.43 / 12.96 | **6.76** / 10.50 | ~6.2 / ~10 (16 MB); ~6.6 (1 MB) | 8.04 / 7.09 |
| 8 / 23 walk | 6.80 / 10.96 | **5.52** / 8.97 | ~4.9 / ~8.5 (16 MB); ~5.2 (1 MB) | 6.95 / 6.07 |
| 8 / 23 stand | 6.64 / 10.97 | **4.96** / 8.57 | ~4.4 / ~8 (16 MB); ~4.8 (1 MB) | 6.48 / 5.51 |
| 10 / 10 walk | 7.99 / 17.87 | **7.34** / 16.98 | ~7.0 / ~16.5 (16 MB); ~7.3 (1 MB) | 9.99 / 9.55 |
| 10 / 10 stand | 7.32 / 12.07 | **5.57** / 9.67 | ~5.3 / ~9.3 (16 MB); ~5.7 (1 MB) | 7.17 / 6.20 |
| 10 / 1 walk | 9.90 / 16.89 | 9.93 / 16.06 | ~9.9 / ~16.5 | 9.63 / 9.32 |
| 10 / 1 stand | 3.99 / 15.23 | 3.99 / 14.87 | 3.99 / ~15 | 8.04 / 7.71 |
| 7 / 19 walk | 8.25 / 13.03 | 7.81 / 13.03 | ~6.8 / ~12 | 9.23 / 8.96 |
| 7 / 19 stand | 5.17 / 9.66 | 5.56 / 8.95 | ~4.4 / ~8.5 | 6.51 / 6.07 |
| walking (perfcheck normal tick, level 1's torches) | 5.20 | | ~4.8-5.0 | |

How the reduced-E column is derived from the measured E1+E2+E3 (the 512 KB / 1 MB figures in the chopper rooms add
back step 4's ~1.0 a chopper hit for the choppers without complete-picture slots, above: l03r16 all of its ~1.0 hits
a tick, the 2-chopper rooms half of their ~0.7: estimates, not measured):

- without E1's gate, door and button savings (they need the strip, which the reduced E does not build: +0.1-0.3 in
  l07r19 and l10r01);
- with the chopper and spike complete pictures copied directly (-~0.45 a step);
- with the potion bubble cached and copied directly (-~0.3 a tick a potion);
- with the torch under bars cached (l07r19: -~1.2 a tick).

The p90s are the measured ones less about half of that. The pacing floor is 4 frames. The busy rooms go from ~7-10 to
~4.5-7 frames a tick at the median. What is left: the old-way gates (l10r01's palace pillar gate, 10-13 frames a step)
and the kid at a chopper (4.4 for two steps).

### 7. Effort, risk, order (separate PRs)

1. **The direct copy of cached small rects**: torch flames now, potion bubbles with their own 7-frame cache, as a
   pending entry timed by pend_flush. 2-3 days, risk low-medium (the copy must stay untorn and in order with the
   kid's chunks). Every room with torches gains -0.2 a torch a tick (walking 5.2 -> ~4.8-5.0); potions -0.3. **The
   first gain, and it reaches every room.**
2. **The torch under a gate's bars**: register such a flame with the bars' records over it, and key its cached picture
   by the gate's position (flushed at the gate's step). 1-2 days, risk low; l07r19 -1.2 a tick, and the other 8 rooms.
3. **A lazy shadow for cached pictures** (choppers, spikes, cached buttons: no shadow write, the restore from the slot,
   a write-back before a dr_run). 4-5 days, risk medium (the invalidation order; it needs the ~100-150-byte reclaim);
   -0.7 a chopper or spike step, -0.4 a cached button press. With step 4, **the largest gain in the chopper rooms**.
4. **Complete pictures for choppers and spikes with nobody in the rect**, copied directly. 3-4 days, risk medium (more
   slots: all of them on 16 MB, choppers only on 1 MB); -1.0..-1.5 a step on top of step 3 (l08r23_stand 6.64 ->
   ~4.4).
5. **Full E for gates and the door** (the strip, the over pieces in every chunk). 1-2 weeks, risk high, -0.3..-0.5 a
   step (35 of 38 gates have static pieces over their bars): **not recommended**. If gates still matter after the
   hardware milestone, the old-way gates (palace pillar, drops) are the better target.

Recommendation: a **reduced E** (steps 1-4, ~2-2.5 weeks with the reclaim), in that order. Step 1 alone is the
cheapest gain for every room; steps 3-4 are for the chopper rooms. No full exclusive layer, and no E for gates. Then
M8, the hardware.

## M8a part 16: torches by a gate (2026-11-08)

Status: **built.** Step 2 of "Option E: measured" section 7, done first (smaller). In 9 rooms a torch stands left of a
gate (l01r07, l04r07, l04r08, l04r24, l05r07, l05r10, l07r03, l07r07, l07r19). view.asm flames_build did not register
their flames, so every flame frame took torch_fast's slow path (torch_redraw: op_patch, dr_run into the shadow, the
room cache's replay), ~0.8-0.9 frames a tick more than a registered flame.

### What lies over the flame (tools/movecheck.py torches)

Option E's census put it down to the gate's bars. On the reference it is not the bars: the bars are drawn by the gate's
right neighbour, a byte column right of the flame, and never touch its rect at any gate position. What lies over the
flame's rect is CH_ENV 46, the **gate's base** (TILE_TABLE[gate]'s base piece, a transparent 4 x 60 piece). The gate's
own tile draws it right after the flame (draw_tile_anim_right, then draw_tile_base), and its records' rect covers the
flame's, so flames_build saw an op after the cover and called the flame not exclusive. The base has no pixel inside the
flame's rect, and it does not change with the gate's position. So the flame alone is the picture there, and nothing
has to be keyed by the gate's position.

tools/movecheck.py torches checks this for every torch flame drawn on a screen of levels 1-14 (our room's columns 0-8,
the left room's column 9), at every position of a gate right of the torch (0..188 by 4): 806 flame states. 371 have no
op after them in their rect, 432 (the 9 torches x 48 gate positions) have exactly the gate's base 46 there, with no
pixel in the flame's rect. 3 have other ops (choppers' 104 / 112, as the census found): still the slow path. 0 differ.

### The change

spike.asm fb_over (main, 33 bytes), called by flames_build in place of its `rr_cnt == rr_last` test: Z when the flame's
cover is the last op in the rect, or when the one op after it is CH_ENV 46 (rr_table's scan records every op in the
rect in RR_PTRS, so the op after the cover is at RR_PTRS[rr_cnt - 1]). The rest of the registry works unchanged:
- flames_lay lays the flame after the restore, and flames_cover skips the restore of a chunk inside it. Both are exact,
  since 46 adds no pixel there.
- The torch cache (tcache.asm) keeps the chunk as composed. A gate step that regenerates the tile moves the records
  (ops_gen), and flames_sync finds the flame again by its place; part 14's one-row step does not touch the flame's rect.

Resident: main +33 (end_of_code 0x7AD8, 296 free), low block -4 (the 10-byte test became a call and a jump; end_of_low
0x1FE8, 24 free), block 2 unchanged (14 free).

### Before / after (1 MB, frames a tick, median / p90; tools/busyrooms.py find + measure, main 8c5ca08 against this)

| room (torches) | walk main | walk new | stand main | stand new | only torch (work - b, median) main / new |
|---|---|---|---|---|---|
| l07r19 (3) | 8.25 / 13.03 | **7.01** / 12.07 | 5.17 / 9.63 | **4.99** / 8.56 | 2.02 / **1.15** |
| l01r07 (2) | 7.14 / 12.67 | **6.56** / 11.96 | 4.14 / 5.32 | **3.99** / 4.65 | 1.67 / **0.82** |
| l04r07 (3) | 6.21 / 11.88 | **5.97** / 10.91 | 5.71 / 5.91 | **5.02** / 5.19 | 2.45 / **1.73** |
| l04r08 (2) | 5.99 / 8.42 | **5.13** / 7.48 | 5.14 / 8.31 | **4.53** / 7.61 | 1.59 / **0.69** |
| l04r24 (3) | 5.99 / 10.66 | **5.04** / 10.09 | 4.99 / 5.04 | **3.99** / 4.81 | 2.03 / **1.32** |
| l05r07 (2) | 6.97 / 10.47 | **6.02** / 9.96 | 5.98 / 9.96 | **5.55** / 8.98 | 1.75 / **0.86** |
| l05r10 (2) | 4.96 / 6.09 | **4.02** / 5.83 | 4.50 / 4.52 | **3.98** / 4.00 | 1.86 / **0.98** |
| l07r03 (2) | 7.70 / 10.96 | **6.80** / 10.00 | 4.99 / 9.93 | **3.99** / 9.05 | 1.73 / **0.98** |
| l07r07 (3) | 8.79 / 11.96 | **7.98** / 10.98 | 5.47 / 10.92 | **4.99** / 9.95 | 2.12 / **1.24** |

The only-torch work falls by 0.7-0.9 frames a tick in every one of them (the torch by the gate now costs what the
others do, ~0.4). The medians fall by 0.2-1.0 (the pacing floor is 4). The other busy rooms and the perfcheck stretches
have no torch by a gate: unchanged.

### perfcheck (one run per size; main = 8c5ca08, the baselines)

| Stretch | 512 KB base / new | 1 MB base / new | 16 MB base / new |
|---|---|---|---|
| normal tick (walkthrough 30-60) | 5.72 / 5.75 | 5.20 / 5.20 | 5.03 / 5.03 |
| level door step (walkthrough 203-207) | 9.23 / 9.23 | 8.54 / 8.54 | 8.54 / 8.54 |
| room change (walkthrough 89) | 105.92 / 106.06 | 105.92 / 106.07 | 105.22 / 105.57 |
| walkthrough 190-260 | 6.44 / 6.45 | 6.19 / 6.17 | 5.85 / 5.82 |
| gate (gate_push 200-260) | 4.10 / 4.10 | 4.10 / 4.10 | 4.10 / 4.10 |
| traps (traps_b1 0-300) | 5.63 / 5.64 | 5.30 / 5.31 | 5.22 / 5.23 |
| fight (fight1 60-160, guard on) | 7.17 / 7.19 | 6.36 / 6.36 | 5.98 / 5.99 |

No torch by a gate in the stretches: unchanged within the beam phase. No baseline lowered.

### Same pixels, same logic

tests/m4_game.py --every 1 (state and VRAM every tick) at 512 KB, 1 MB and 16 MB: the walk_a, stand_a, walk_torch,
walk_gate and walk_potion scenes of the 9 rooms and of the busy rooms l03r16, l05r24, l08r23, l10r10, l10r01, l08r04,
plus walk_level1, gate_push, btn_bars, potion_heal, potion_hurt, potion_life (71 scripts a size): 0 state diffs, 0
differing pixels. tools/movecheck.py torches: 0 differ. `make ci-build`, `make cheats`. The full regression on the
runners: see the PR.

## M8a part 17: direct copy of cached torch flames (2026-11-08)

Status: **built.** Step 1 of "Option E: measured" section 7, reduced to what pays for its bytes. A torch flame whose
chunk is a cached picture with nothing over it goes from its RAM-disk slot straight into VRAM, timed against the beam:
no compose buffer, no pending chunk, no screen copy. And a potion bubble's frame no longer throws the flames' cached
pictures away.

### What changed

- **The direct copy** (tcache.asm tc_direct, block 2). obj_chunk now asks tc_try before it picks a chunk buffer. On a
  hit the RAM disk, at the slot, is read by INIR into VRAM, plane after plane (4 planes x CRH rows x 2 bytes; the
  flame's rect is 2 bytes wide). Under the upside-down flip (set_flip patches blit into a jump) the chunk is composed as
  before. A direct hit clears tc_slot: else a later chunk that takes the kept-picture path (oc_kept skips tc_try) would
  reach tc_save with the stale slot and overwrite the flame's picture with its own.
- **The beam wait** (sprite.asm td_beam, low block; it reuses pend_flush's pf_beam and pf_d). See "Why it cannot tear".
- **fore_gen** (room.asm op_patch). The fore path bumped fore_gen at every potion bubble frame, and tc_try flushes
  the whole torch cache when fore_gen moves: in a room with a potion the flames missed the cache at every bubble frame.
  No bubble's rect touches a flame's on any screen of levels 1-14 (tools/movecheck.py caches: 2,352 screens x bubble
  frames, 0 differ), so a flame's picture never holds a bubble and the bump is gone. frames.asm still bumps fore_gen
  when a fore record in a flame's rect is patched.
- **Memory found in what this touches:**
  - FLM_MAX 8 -> 4: no screen of levels 1-14 shows more than 4 flames (movecheck caches). That frees page 6
    0x1440-0x287F (the slots of flames 4-7, 5,184 bytes, runtime only) and 36 bytes of TC_VALID.
  - flm_rec (8 bytes) moved from the low code block to low RAM 0x0124 (after TC_VALID), flm_rect (16) from block 2 to
    0x9FE8 (the free bytes above GUARD_TABS; neither is read while VRAM is mapped).
  - tc_hit's read into the compose buffer is gone; a few jumps in tc_try, tc_save and flames_build became relative.

Resident: main 15 bytes smaller (311 free), low 15 larger (9 free), block 2 5 smaller (19 free). Nothing on the RAM
disk is added.

### Why it cannot tear

The copy changes the rect's four planes one after the other, so all of it must fall between two passes of the beam
over the rect's rows. Let d be the lines until the beam next reaches the rect's top row, (BEAM_Y0 + CRY - s) mod 312,
where s is beam_lines: the 8253's HSYNC count since the VBLN interrupt, the same source and BEAM_Y0 as pend_flush's
chunk copies. td_beam reads the beam until both hold:

- d >= 2h + TD_PRE (8): the copy's length with room to spare. A row's four planes take 4 x (36 x 2 + 29) T of code
  with the 15 wait states a RAM-disk byte the boot accepts at most (rdspeed.asm RD_SPEED_MAX), 1.77 lines, plus the
  VRAM's own wait states: measured at 15 waits, a flame's copy (h = 18) is 34.6 lines at most, under the 44 it is given.
  The copy starts a few dozen T after the last beam read.
- d + h <= 312 - TD_POST (6): the beam left the rect's bottom row at least 6 lines before the copy starts.

The window is shut for 3h + 14 = 68 of the 312 lines. The only interrupt is the VBLN one at line 0 (with the PSG player
at most 2,204 T, under 10 lines). It cannot fall inside a copy that ends near the beam, nor between a passed check and
the copy's start when the start is near the beam: canvas rows begin 113 lines after it, so a copy around line 0 has
over 80 lines to spare.

tools/optione.py direct traces every copy (td_go to td_end) and the VBLN interrupt's entry in the emulator; a copy
tears when the beam is on one of the rect's rows at any time from its first write to its last:

| scene (1 MB) | RAM-disk waits | copies (a tick) | torn | longest copy (lines) | beam after the end, before the start (lines, min) | wait a copy (lines, mean / max) |
|---|---:|---:|---:|---:|---|---|
| walk_level1 | 0 | 349 (1.10) | 0 | 28.4 | 17.3, 7.8 | 11.6 / 72.0 |
| l04r07_stand_a | 0 | 180 (1.80) | 0 | 25.1 | 19.8, 7.9 | 10.8 / 59.1 |
| l07r19_walk_a | 0 | 27 (0.23) | 0 | 25.1 | 26.7, 8.6 | 6.0 / 67.7 |
| l05r07_walk_a | 0 | 106 (0.88) | 0 | 25.1 | 22.9, 8.0 | 9.2 / 65.6 |
| walk_level1 | 15 | 349 (1.10) | 0 | 37.9 | 8.6, 7.7 | 12.5 / 69.9 |
| l04r07_stand_a | 15 | 180 (1.80) | 0 | 34.6 | 15.3, 8.2 | 15.8 / 69.9 |
| l07r19_walk_a | 15 | 27 (0.23) | 0 | 34.6 | 8.8, 9.3 | 12.8 / 67.7 |
| l05r07_walk_a | 15 | 106 (0.88) | 0 | 34.6 | 10.2, 8.0 | 13.7 / 69.9 |

(POP800_RD_WAIT=15.) The 37.9 is a copy far from the beam with the VBLN interrupt inside it. The closest the beam came
to a copy's end is 8.6 lines, inside the allowance; to its start 7.7 (TD_POST 6 plus the read-to-copy delay). On the
real machine the beam position comes from the same 8253 HSYNC count that pend_flush's chunk copies rely on (PLAN status
11); a check on the hardware belongs to M8 with the rest of the beam timing.

### Speed

What each part costs and buys (1 MB; the busy-room scenes are tools/busyrooms.py find's, mean work a tick of the a
scene, the median frames in brackets; only-torch / only-potion: that kind's variant minus walk_b, mean a tick). The
variants were built and measured; A, B and C are main 3f95f09 plus:

| | main / low / block 2 free | normal tick 512 KB / 1 MB | l04r07 stand | l05r07 walk | l07r07 stand | l01r05 stand | only-torch l07r19 | only-potion l05r07 |
|---|---|---|---|---|---|---|---|---|
| main | 296 / 24 / 14 | 5.72 / 5.20 | 5.07 (5.02) | 7.15 (6.02) | 6.12 (4.99) | 6.29 (5.91) | 1.22 | 0.50 |
| A: fore_gen only | 311 / 24 / 14 | 5.72 / 5.20 | 4.58 (4.49) | 6.91 (5.98) | 6.12 (4.99) | 6.07 (5.96) | 1.22 | 0.47 |
| **B: A + direct flames (this)** | **311 / 9 / 19** | **5.47 / 5.12** | **4.40 (4.34)** | **6.72 (5.95)** | **5.89 (4.98)** | **5.97 (5.95)** | **0.92** | 0.47 |
| B': B, td_beam in main | 275 / 45 / 19 | as B | | | | | | |
| C: the first draft (B + bubbles) | 137 / 34 / 18 | 5.47 / 5.09 | 4.08 (3.99) | 6.54 (5.82) | 5.82 (4.52) | 5.85 (5.49) | 0.92 | 0.13 |
| D: B + slim bubbles (estimate) | ~255 / 9 / ? | as C | | | | | | |

The draft (C) also cached the potion bubbles (spike.asm bub_build, a slot per bubble and frame in the page 6 space
FLM_MAX 4 frees) and copied them directly: a bubble alone fell from 0.5 to 0.13 frames a tick. In whole scenes that
came to -0.08 a tick on average (l04r07 -0.17 / -0.32, l05r07 -0.18 / -0.24, but l03r16 +0.06 / +0.13, l05r24 and
l01r05 within 0.1 either way), for +58 bytes of main, and the room change was +0.1 (bub_build at every flush). B leaves
the bubbles out. Its direct copy was also slimmed from the draft's 106 bytes in main (with blit's VRAM address moved
into a shared vram_at) to tc_direct in block 2 plus the 36-byte td_beam.

All rooms (1 MB, mean work a tick of the a scenes, main -> B; only-torch work in brackets):

| room | walk | stand |
|---|---|---|
| l01r07 (2 torches) | 7.68 -> 7.61 (0.91 -> 0.72) | 3.84 -> 3.56 |
| l04r07 (3, potion) | 7.38 -> 7.12 (1.55 -> 1.28) | 5.07 -> 4.40 |
| l05r07 (2, potion) | 7.15 -> 6.72 (0.85 -> 0.49) | 6.65 -> 6.30 |
| l07r07 (3) | 8.41 -> 8.39 (1.28 -> 0.86) | 6.12 -> 5.89 |
| l07r19 (3) | 8.39 -> 8.37 (1.22 -> 0.92) | 5.66 -> 5.46 |
| l03r16 (2, potion, chopper) | 9.32 -> 9.31 (0.83 -> 0.55) | 8.79 -> 8.77 |
| l05r24 (2, potion, chopper) | 8.36 -> 8.26 (0.77 -> 0.48) | 8.04 -> 7.93 |
| l01r05 (3, potion) | 7.79 -> 7.78 (1.37 -> 1.05) | 6.29 -> 5.97 |

A cached flame costs ~0.1 frames a tick less (the copy ~25 lines and the wait ~10 instead of the compose read, the
pending copy and its share of pend_flush). The rooms with a potion gain the most standing: their flames now hit.

### perfcheck (one run per size; main = 3f95f09, the baselines; lowered where beaten, in this commit)

| Stretch | 512 KB base / new | 1 MB base / new | 16 MB base / new |
|---|---|---|---|
| normal tick (walkthrough 30-60) | 5.72 / **5.47** | 5.20 / **5.12** | 5.03 / **5.00** |
| level door step (walkthrough 203-207) | 9.23 / 9.23 | 8.54 / 8.56 | 8.54 / 8.56 |
| room change (walkthrough 89) | 105.92 / 106.05 | 105.92 / 106.05 | 105.22 / 105.22 |
| walkthrough 190-260 | 6.44 / **6.35** | 6.19 / **6.14** | 5.85 / **5.78** |
| gate (gate_push 200-260) | 4.10 / **4.09** | 4.10 / **4.09** | 4.10 / **4.09** |
| traps (traps_b1 0-300) | 5.63 / **5.55** | 5.30 / **5.24** | 5.22 / **5.18** |
| fight (fight1 60-160, guard on) | 7.17 / **7.09** | 6.36 / **6.28** | 5.98 / **5.96** |

The normal tick (level 1's torches) gains 0.03 (16 MB) to 0.25 (512 KB): a tick saved shows only where it moves the
tick's end over a frame's beam phase, which differs by size. The room change and the door step are as on main (main's
own runs: 106.07 and 8.54 at 1 MB), within the tolerance; their baselines stay.

### Same pixels, same logic

tests/m4_game.py --every 1 (state and VRAM every tick) at 512 KB, 1 MB and 16 MB: the walk_a and stand_a scenes of
the torch rooms l01r07, l04r07, l05r07, l07r07, l07r19, the potion rooms l03r16, l05r24, l01r05 and the busy rooms
l08r23, l10r10, l10r01, plus walk_level1, potion_heal, potion_hurt, potion_life, level5_shadow_potion and
potion_upside_down (the flip: composed as before), 28 scripts a size: 0 state diffs, 0 differing pixels.
tests/m4_test.py: 0 differing. tools/movecheck.py caches: 0 differ. `make ci-build`, `make cheats`. The full
regression on the runners: see the PR.

## Speed roadmap (2026-11-08)

Status: **measured; candidates 1 and 2 (L1, M1 + M2) since built** (see "M8a part 18: loose floors"); **section 7's
reclaims PR_TAB, room_checksum, sprite_forget and room_drawn since built** (see "M8a part 19: reclaim"). After the playtest remark "falling floors look quite slow": the loose floors, the
room change, fights and walking measured by stage on main f004916 (M8a part 17), 1 MB unless noted, no waits; then one
ranked list of what is left, with the busy-room steps of "Option E: measured" in it.

**Tools** (committed): tools/loosescenes.py `find OUTDIR` (kidsim only, ~2 minutes for levels 1-14: per kind the best
scene, `<kind>_a` as in the level and `<kind>_b` with the screen's loose floors patched to floor; kinds `shake`, `fall`
(the kid sets a floor off and stops), `fallrun`, `multi` (two or more floors falling), `ride` (the kid stands on a floor
and falls with it into the room below)), `label SCRIPT` (every tick's phase) and `measure OUTDIR [--csv]` (frames,
work, a - b per phase). tools/roadmap.py `enter OUTDIR LV:ROOM ...` (a script that runs into a room), `stages SCRIPT
TICK` (a room change by stage, with the tick's RAM-disk accesses) and `range SCRIPT T0 T1` (a stretch by stage). The
phase of a tick: R (a room draw) > land (a floor landed: its tile became rubble) > rel (a floor came loose) > mob2+ /
mob1 (falling floors drawn: sprite.asm mobs_visible's rule) > sh / sh- (a loose floor's loose_frame / only its
modifier changed). Scenes measured: the best of levels 1-14 (levels 13, 10, 11) and the best of level 1 alone (rooms
7, 8, 12): 10 scenes, ~1,050 ticks. The scenes are not committed (`find` regenerates them).

### 1. Falling floors

**Per phase** (frames a tick, median / p90 / worst over the 10 scenes; a - b = the work above the same tick with the
floors patched away, on the ticks where the kid is in the same state in both; 512 KB: the level-1 scenes, within 0.3 of
1 MB, the frame store plays no part):

| phase | kid | ticks | frames | a - b median / mean | 512 KB (level 1) |
|---|---|---:|---|---|---|
| shake, the picture changes (sh) | moving | 138 | 8.32 / 14.66 / 33.95 | 4.24 / 6.51 | 9.21 / 12.97 |
| | still | 25 | 4.76 / 7.12 / 7.54 | 1.47 (1 tick) | |
| release (rel: the tile becomes empty, the floor starts falling) | moving | 27 | 13.96 / 19.89 / 23.17 | 10.42 / 10.08 | 14.97 / 18.50 |
| | still | 8 | 7.84 / 16.48 / 18.64 | | |
| one floor falling (mob1) | moving | 98 | 8.05 / 12.92 / 17.65 | 3.56 / 4.61 | 8.07 / 12.63 |
| | still | 9 | 5.82 / 7.16 / 8.79 | (b diverges) | |
| two to five falling (mob2+) | moving | 35 | 12.05 / 17.36 / 19.63 | 7.02 / 6.82 | |
| | still | 24 | 10.37 / 14.93 / 15.54 | | |
| landing (land: rubble; the knock shakes the row) | moving | 21 | 15.47 / 21.54 / 28.50 | 9.55 / 9.03 | 15.86 / 21.14 |
| | still | 6 | 15.14 / 21.71 / 21.71 | | |
| the kid falls with a floor into the room below (R) | | 7 | 97.9 / 105.1 / 106.1 | +1.67 (the floor in the room draw) | |
| nothing (none) | moving | 305 | 4.05 / 4.99 / 9.55 | 0.00 / 0.09 | 4.57 / 5.53 |

A floor that is stepped on shakes for 10 ticks (its modifier counts 1..10, loose_frame = the modifier), comes loose at
11 and falls ~4-8 ticks (speed +3 a tick, up to 29 rows) before it lands: ~20 ticks at 8-14 frames instead of 4-5,
i.e. the game runs at ~4-6 ticks a second while a floor goes, and at 10-15 frames a tick with several floors (level
13). **The perfcheck normal tick holds it too**: walk_level1 30-60 has a landing knock at tick 54 that shakes a floor
for 4 ticks (ticks 55-58: 8.5-9.0 frames; the rest of the stretch 3.3-6.7): those 4 ticks are 0.6 of its 5.12 frames
a tick.

**Where a step goes** (tools/optione.py diff, ride_a against ride_b of level 1 room 8, inclusive frames, a - b; the
call profiler loses draw_objects' return on these ticks, so the routines are listed, not the stage totals):

| | shake, picture change (tick 74: 8.27 / 4.65) | release (82: 11.20 / 4.30) | one floor falling (84: 7.97 / 4.30) | landing (95: 9.65 / 4.09) | five floors falling, kid still (level 13 fall_a 24: 10.21, absolute) |
|---|---|---|---|---|---|
| tile_redraw: regenerations | 1.19 (3 tiles) | 1.51 (3) | - | 1.71 (3) | - |
| tile_redraw: run_rect (of it the room cache's replay rc_hook) + shadow write | 1.73 (1.35) + 0.25 | 1.49 (1.14) + 0.23 | - | 2.16 (1.80) + 0.21 | - |
| lay_mob (the floor's pieces 70 / 74 / 72 from the RAM disk) | - | 2.11 (5 calls) | **1.67 (5 calls)** | - | **3.90 (10 calls)** |
| the chunks' restore / people / fore | +0.00 / +0.42 / +0.18 | +0.23 / +0.26 / +0.11 | +0.45 / +0.26 / +0.16 | +0.24 / +0.67 / +0.64 | 1.12 / 0.77 / 0.44 |
| the torch cache lost (flames_lay +, tc_try -) | +0.38 / -0.17 | +0.40 / -0.20 | +0.39 / -0.20 | 0 | (no torch) |
| copy (pf_blit1) / beam wait (pf_seq) | +0.44 / -0.26 | +0.64 / +0.07 | +0.63 / +0.18 | +0.39 / -0.13 | 0.96 / 0.09 |

**Work that repeats for nothing:**
1. **lay_mob runs for every falling floor in every chunk of the tick**, whether the floor touches the chunk or not
   (sprite.asm obj_chunk oc_mob has no overlap test; lay_piece16 clips the pieces away only after the directory lookup
   and its setup): ~0.33-0.39 frames a floor and chunk. One floor in a 3-chunk tick: 5 calls where 1-2 draw; five
   floors in 2 chunks: 10 calls, 3.9 frames.
2. **Any falling floor on screen switches the torch cache off for the whole tick** (tcache.asm tc_try tests `MOBR_N`,
   not the chunk): every torch chunk is composed again, ~+0.2 a torch a tick.
3. **A shake redraws although the picture did not change.** A loose floor has three pictures (popdata
   LOOSE_FRAM_LEFT / BOTTOM / RIGHT: frames 0, 2, 5-7 = 41 / 43 / 42; 1 = 69 / 73 / 71; 3, 4, 8-10 = 70 / 74 / 72), but
   view.asm vrd_one sends every modifier change of a loose floor to tile_redraw. Of the 10 countdown ticks of a
   stepped-on floor the picture changes on 5 (frames 1, 2, 3, 5, 8); the other 5 cost a full tile_redraw (~3.5
   frames) for nothing. (A knock shake, 0x81..0x84, changes the picture every tick.)
4. **A shake regenerates three tiles**: the floor's own (draw_loose, the base piece), its right neighbour's
   (draw_tile_anim_right: piece 42 / 71 / 72) and the tile above-right, which draws nothing from a loose floor
   (draw_tile_topright reads only the tile type): ~0.4 frames a visible step, as the spikes' fix 2 found.
5. Every chunk of a floor looks up and reads its three pieces again (directory entry, seek, lay_piece16's setup): the
   same three pieces in every tick of every floor.
6. The release and the landing are a full tile_redraw each (3 regenerations, run_rect with 5-8 pieces): +5.5..+7
   frames, twice a floor; the landing's knock also shakes every loose floor of its row (level 13: up to 8 at once, a
   33-frame tick).

The kid's own drawing does not change with the floors (people_place equal in a and b). A floor in the room below or
above is drawn by the same path near the screen's edge (mobs_visible); crossing the boundary costs nothing extra
besides the room change when the kid falls with it.

### 2. The room change (tools/roadmap.py stages; one tick, inclusive frames)

| room | tick | op lists (room_ops) + buckets | fill | laying (rec_lay) | of it masked rows | shadow write | copy to VRAM | kid, objects, hooks | RAM disk reads / writes / seeks |
|---|---:|---|---:|---:|---:|---:|---:|---:|---|
| l01r01 (walkthrough 89, dungeon, 2 floors falling) | 106.05 | 11.79 + 2.44 | 2.75 | 57.63 | 17.28 | 11.67 | 11.36 | 7.4 | 53,500 / 30,720 / 5,254 |
| l01r02 (dungeon, simple) | 103.12 | 11.78 + 2.44 | 2.75 | 57.35 | 16.66 | 11.66 | 11.23 | 3.4 | 51,594 / 30,720 / 5,217 |
| l01r07 (dungeon, torches, a gate) | 98.08 | 9.79 + 2.15 | 2.75 | 54.44 | 18.67 | 11.67 | 11.20 | 4.1 | 48,225 / 30,720 / 5,081 |
| l03r16 (dungeon, busy: 3 choppers) | 104.36 | 9.91 + 2.36 | 2.75 | 59.49 | 18.12 | 11.66 | 11.20 | 4.2 | 51,297 / 30,720 / 5,242 |
| l04r04 (palace, simple) | 86.02 | 9.00 + 2.08 | 2.75 | 43.43 | 12.25 | 11.66 | 11.44 | 3.7 | 39,510 / 30,720 / 5,031 |
| l06r03 (palace, simple) | 81.50 | 9.82 + 1.89 | 2.75 | 39.28 | 7.51 | 11.66 | 11.12 | 3.8 | 35,378 / 30,720 / 4,907 |
| l05r24 (palace, busy) | 109.43 | 10.52 + 2.66 | 2.75 | 62.91 | 20.63 | 11.66 | 11.28 | ~1.7 | 53,550 / 30,720 / 5,332 |
| l10r01 (palace, busy: pillars, 4 gates) | 116.01 | 10.15 + 2.88 | 2.75 | 70.76 | 26.47 | 11.66 | 11.27 | 3.8 | 59,946 / 30,720 / 5,419 |

(Overlay loads 0-0.3, the hooks after the draw (room_drawn, flames_build) 0.1-0.6; the copy column holds the object
pass's copies too, 0.14-0.39.) **82-116 frames, 1.6-2.3 seconds, the same on every RAM-disk size** (perfcheck: 512 KB
and 16 MB within 1 frame). The fixed part is ~26 frames (fill 2.75, shadow write 11.66, copy 11.2), the op lists
11-14, the piece laying 39-71. The laying follows the bytes read (35-60 K: ~1.1 frames a 1,000 bytes, ~80 T a byte of
which 21 T is the INIR; the rest is the masked and copy-mode row work), not the piece count; a piece is laid once per
cell it touches (rec_lay 238-467 calls for 151-221 lay_piece16 calls). In the walkthrough's first 318 ticks the 3 room
changes are ~16 % of the time (318 of ~1,950 frames).

What could cut it:

| | gain a room change | sizes | notes |
|---|---|---|---|
| the visited-room cache (docs/ramdisk-tiers.md section 5: the renderer draws into the room's slot; a revisit copies the slot to VRAM, keeps the op lists, redraws the changed tiles) | revisit 106 -> **~15-20**; first visit 0 | 16 MB (158 + 15 pages); 1 MB: no (the user's decision of 2026-11-03); 512 KB: no | 1-2 weeks; resident ~20-40 (the shadow page patched), a second room overlay; exact (the snapshot compare redraws what changed) |
| the op lists kept per visited room (2.9 KB of lists and tags + ~0.5 KB of slice tables, read back by INIR in ~1 frame) | revisit **-12..-13** | 16 MB (part of the room cache); 512 KB / 1 MB only after a RAM-disk reclaim (e.g. only the level's guard set: ~90 KB of pages 6-7) | 3-4 days alone; the room cache's invalidation |
| a faster op-list build (room_ops / tile_gen; in the walkthrough's change draw_tile 7.2, draw_tile_bottom 2.8, wall patterns 1.9-3.1, prandom 1.1, mul8 1.2, get_tile 0.7) | **-3..-4** every change (estimate: a third of 9-12), and -0.1..-0.2 a tile regeneration in play | all | 3-5 days, medium (resident room.asm; tests/m3_test.py covers every room of every level) |
| band cells (40 bytes x 48 rows instead of 8 x 64: shadow and VRAM rows contiguous, one seek a 40-byte plane row, a block copy) | **-6..-8** (estimate: shadow 11.7 -> ~7.5 at ~17 T a byte, copy 11.2 -> ~9, against more piece setups at the band edges) | all | needs the whole 8 KB compose area during the draw (the kid's image is fetched again) and its own lay / write / copy path (~300 bytes of overlay): 1-1.5 weeks, high; a prototype first |
| the VRAM copy by POP / PUSH or the write modes (PLAN M8a list item 4) | -2..-4 (and ~-0.1 a tick in play) | all | 2-3 days, medium (pend_flush's copy-speed model changes) |
| the black fill skipped where a back op covers the whole cell (run_rect's cover rule, checked per cell of the full draw) (**measured: no cell is ever covered; built instead: the full draw without the cover scan, -2.3..-3.5: M8a part 26**) | -1..-1.5 | all | 1 day, low |

Not levers: the RAM-disk reads as such (INIR and LDIR are both 21 T a byte: a main-RAM piece cache would save only the
seeks, ~1.8 frames), the overlay loads (0-0.3), the hooks (0.4).

### 3. Fights (tools/roadmap.py range fight1 60 160; frames a tick)

| | 512 KB | 1 MB | 16 MB |
|---|---:|---:|---:|
| frames median / p90 / mean (ticks at the floor) | 5.48 / 11.80 / 7.08 (10 of 100) | 5.37 / 9.84 / 6.29 (21) | 4.52 / 9.84 / 5.96 (31) |
| logic (kid_tick 1.25, the guard's tick_pre / tick_post 0.12, trobs 0.07) | 1.44 | 1.44 | 1.44 |
| people_place (of it char_fetch: the frames) | 2.09 (1.54) | 1.26 (0.71) | 0.88 (0.33) |
| object pass: restore / flames + torch cache / fore | 0.62 / 0.21 / 0.59 | 0.62 / 0.21 / 0.59 | 0.62 / 0.21 / 0.59 |
| composing the people (spr_draw: kid, guard, swords) | ~1.1 | ~1.2 | ~1.2 |
| copy (pf_blit1) / beam wait (pf_seq) | 0.59 / 0.29 | 0.59 / 0.29 | 0.59 / 0.29 |

(The profiler loses some returns in fights: people_chunk's inclusive total comes out below spr_draw's; spr_draw's own
figure is used.) The fight is ~2.3 frames a tick above the floor on 1 MB. What differs by size is the frames' fetch
(char_fetch 1.54 / 0.71 / 0.33). The rest is spread: logic 1.4, composing two characters 1.2, restore + fore 1.2, copy
+ wait 0.9. No single item is worth more than ~0.3: the same-frame rule over both characters' chunks (pf_seq 0.29;
tying only one character's chunks together ~-0.08, "M8a part 3", but it changes what shows between two frames), kid
logic trims (collision rows, tile lookups: -0.2..-0.3, PLAN M8a list item 6), #8's scheduler (-0.06).

### 4. Walking (tools/roadmap.py range walk_level1 30 60)

1 MB: frames median 4.57, p90 8.47, mean 5.12; work mean 4.93; 12 of 30 ticks at the floor. 512 KB: 4.56 / 8.94 /
5.47 (char_fetch 0.90 against 0.35: no frame store). Per tick on 1 MB: logic 1.20 (kid_tick 1.00: check_collisions
0.48, get_row_collision_data 0.41), view_redraw 0.76 (of it **tile_redraw 0.60: the knock-shaken loose floor of ticks
55-58**), people_place 0.67 (char_fetch 0.35), object pass 2.21 (restore 0.41, flames 0.16, torch cache 0.19, people
0.42, fore 0.58), copy 0.44, beam wait 0.12. Of the ~1.1 frames a tick above the 4-frame pacing 0.6 is the loose floor
(section 1); the rest is the kid's own drawing and logic. Harness note: trace_cksum (room_checksum, 0.08 frames a tick)
runs only under script control (SCRIPT_PTR != 0), i.e. in every measurement but never in the played game, which is
that much faster than measured.

### 5. The parked beam-wait scheduler (#8)

From "M8a part 3" and PR #8: -0.07..-0.09 frames a tick (normal 6.20 -> 6.13, fight 9.13 -> 9.07, walk 190-260 11.00 ->
10.83) for ~476 resident bytes (main +658, low -181). Today the beam wait is pf_seq 0.10-0.12 a tick walking and 0.29
fighting (0.22 / 0.48 then), so the variant would save ~0.05-0.06. Below the rule (>= 0.2 frames a tick at < 250
bytes) and more than main's 311 free bytes: **not worth it now**; it stays parked.

### 6. The ranked candidates

Gain in frames where the situation hits (1 MB unless noted). Resident free today: main 311, low 9, block 2 19; overlays:
the room overlay 86 free, the frames overlay 4. "Exact": the pixels stay identical by construction (and the per-tick
pixel tests check it).

| # | candidate | gain | how often the player sees it | resident (main / low / block 2), overlays | RAM disk | effort, risk, exact |
|---|---|---|---|---|---|---|
| 1 | **L1: loose floors draw only on a picture change, regenerating their own tile and the right neighbour only** (a loose case in spike.asm anim_redraw: the picture group of the old and the new modifier, as chomp_redraw) | the 5 countdown ticks without a change ~-3.5 each (8.5 -> ~5); a visible step -0.4; ~-18 frames over a floor's countdown | every floor stepped on (172 loose floors in levels 1-14; walk_level1: 15 of its 318 ticks shake) | main ~35 | none | 1 day, low, exact |
| 2 | **M1 + M2: a falling floor is laid only in the chunks it touches, and the torch cache tests the chunk, not the tick** (one test of the floor's OMOBR rect against the chunk, used by oc_mob and tc_try) | one floor falling -1.0..-1.5 (a - b 3.6 -> ~2.2); five floors -2.5 (lay_mob 3.9 -> ~1.4); -0.2 a torch more | every falling-floor tick (~5-8 a floor; level 13's run constantly) | ~40: main (obj_chunk is in the low block, 9 free: a call into main) | none | 1-2 days, low, exact |
| 3 | **L2: cached loose-floor pictures** (part 15's frame slots: the floor's rect, own tile + the right piece, its three background-only pictures through cs_put; knock shakes too) | a visible shake step 4.2 -> **~1**; the normal tick -0.4 (5.12 -> ~4.7); level 13's 8-floor knock ~33 -> ~12 | every visible shake step (5 of a countdown, 4 of a knock) | ~150-250 of overlay (the frames overlay has 4 free: a second overlay or a reclaim) + ~20 main | 3 small slots (648 B) a floor: 512 KB / 1 MB share part 15's 20 slots with choppers and spikes (a miss takes today's path); 16 MB: page 62 | 3-5 days, medium (invalidation as part 15), exact |
| 4 | Option E step 3: the lazy shadow (choppers, spikes, cached buttons: no shadow write, the restore from the slot; **built for choppers and spikes: M8a part 25**) | -0.7 a chopper / spike step, -0.4 a cached button press | the busy rooms | ~160 main + 4 low: **needs a reclaim** | none | 4-5 days, medium, exact |
| 5 | Option E step 4: complete pictures with nobody in the rect, copied directly (**built for choppers: M8a part 25**) | -1.0..-1.5 a step on top of 4 (l08r23 stand 6.64 -> ~4.4) | the chopper rooms | ~80 main: **needs the reclaim** | 16 MB all; 512 KB / 1 MB choppers only (slots) | 3-4 days, medium, exact |
| 6 | the visited-room cache (with the op lists) | revisit 106 -> ~15-20 (2 s -> 0.3-0.4 s) | most room changes after a room's first visit | ~20-40, a second room overlay | **16 MB only** | 1-2 weeks, medium, exact |
| 7 | a faster op-list build | -3..-4 a room change; -0.1..-0.2 a tile regeneration in play (helps 1's remaining steps, gates' regenerating steps, chopper misses) | every room change | room.asm in main: likely +50..+100 | none | 3-5 days, medium, exact (m3 tests) |
| 8 | band cells for the full room draw | -6..-8 a room change (estimate) | every room change | ~300 overlay (a second room overlay) | none | 1-1.5 weeks, high; a prototype first |
| 9 | the VRAM copy by POP / PUSH or the write modes (**measured and dropped**: "Step 3 (the VRAM copy): measured and dropped"; PUSH waits on the GDG, banded LDI -2.5 a room change for ~680 bytes) | -2..-4 a room change, ~-0.1 a tick | everywhere | ~50-100 main | none | 2-3 days, medium |
| 10 | the fill skipped under a covering back op in the full draw (**measured: 0 of 4,740 cells covered; built instead: the full draw without the cover scan and the bucket ops' touch test, -2.3..-3.5: M8a part 26**) | -1..-1.5 a room change | every room change | room overlay (86 free) | none | 1 day, low, exact |
| 11 | M3: a falling floor's three pieces looked up once a tick (directory entries and seeks kept for its chunks) | ~-0.1 a floor and chunk after 2 | falling floors | ~30 main | none | 1 day, low, exact |
| 12 | kid logic trims (collision rows, tile lookups; **A', C, E built: M8a part 21**, the logic -0.10..-0.17 a tick) | -0.2..-0.3 a tick | every tick | main | none | 3-5 days, medium (tick-exact against kidsim) |
| 13 | #8, the beam-wait scheduler | -0.05..-0.06 a tick | everywhere | +476 net: no | none | parked |

Order by what the player gets: **1 and 2 first** (2-3 days, ~75 resident bytes, no reclaim: a falling floor's ticks go
from ~8-14 to ~5-7 frames, the countdown's unchanged ticks to walking speed), then **3** (the visible shakes and the
normal tick's 0.4), then the busy-room steps 4-5 after a reclaim, then the room change: 7 and 10 on every size, 6 on 16
MB, 8 if a prototype confirms it. 9 and 12 are the small general ones; 13 stays parked.

### 7. Memory: what needs a reclaim, and the reclaims found

Need a reclaim first: 4 and 5 (~240 bytes of main together, against 311 free shared with everything else), 3 unless it
gets its own overlay, 2 if it were put in the low block (9 free). 1, 2 (in main), 10 and 11 fit today.

| reclaim | frees | cost | notes |
|---|---|---|---|
| **PR_TAB to the RAM disk** (the wall-pattern draws, 64 seeds x 10, low RAM 0x0500-0x077F): pr_start reads its 10-byte row by INIR into a 10-byte buffer | **640 bytes of low RAM**, outside 0x1000-0x1FFF (CG-ROM inside blit), so usable for code | ~+400 T a wall pattern: ~+0.3 frames a room change (~57 patterns), ~0 in play; ~+15 bytes of code | the largest reclaim found; built at the start (gstart.asm), written to a free spot (page 6 0x1440- is free since part 17) |
| room_checksum out of the game: the harness computes the 'K' trace's checksum from memory at tick_done; trace_cksum and its call go | 53 + 6 + 3 bytes of main | none in play; the measurements lose the 0.08 frames a tick the player never pays | tests/m4_test.py and m4_game.py read RAM there anyway; m4test.asm keeps its own |
| sprite_forget (24, low) and room_drawn's hooks (block 2) into the room overlay | 24 low + ~30 block 2 | none (once per room draw) | the room overlay has 86 free |
| flames_build (175 bytes, low) into a second room overlay | 175 low | a W1 load (~0.3) whenever a regeneration near a flame re-checks the flames in play | measure that rate first |
| tc_flush (28, block 2) into the room overlay; anim_redraw's dispatch into the frames overlay ("Option E: measured" section 4) | 28 block 2; ~35 main | a frames-overlay load for a non-cached object's step | |
| only the level's guard set in the RAM disk (docs/memory.md "RAM disk") | ~90 KB of RAM disk (pages 6-7), every size | a per-level floppy load | room for the op lists of visited rooms on 512 KB / 1 MB |

The op-list buffers stay (back 185 / 192, fore 126 / 128 used: M7 step 5), and no other table was found that shrinks
without a speed cost.

### 8. More candidates, not yet measured (added 2026-11-08; to rank with section 6 after part 18, the loose floors)

The user asked for every remaining option in one list, to re-rank after candidates 1 and 2 are built. These are the
gaps left in what parts 11-17 built, and new ideas; the figures are from parts 14-15's per-kind tables and the cost
model where they exist, else marked "to measure".

| candidate | today | possible | where the player sees it | approach, cost |
|---|---|---|---|---|
| G1: palace-pillar gates (9 % of gate steps, part 14) | ~6 a step (the old path) | ~2-3 | palace gate rooms (l10r01: 9.9 a tick) | a shift that keeps the pillar's mask (its base 147/149 laid over the bars); an overlay |
| G2: dropping gates (3 %) | ~10 a step | ~2-3 | a gate dropping (4-5 ticks) | a k-row shift (the gate falls 4-5 rows a tick) |
| G3: closed gate's contact band (17 % of gate steps) | ~3.4 a step (run_rect ~1.5) | ~2 | every closing gate | the floor strip in front of the bars from a cached picture (part 15's slots, cs_put) |
| G4: steps to or from position 47 (2 %) | ~6 | ~2 | gates opening fully / starting to close | the record-count change handled in place |
| B1: a button's first press in a room (a cache miss) | ~4.3 | ~0.6 | the first press of each button after a room draw (often the only one) | fill the button's slot at the room draw (+ a little a room change), or keep slots across room draws |
| C1: a chopper with blood (bit 7: the old path) | ~6 a step | ~1.3 | after the kid dies on it, until the room is redrawn | the blood pictures as more slots |
| C2: choppers and spikes of the neighbouring rooms (the above room's row 2, the left room's column 9) | the old path | as their own room's | some screens | part 15's rect rules for those cases |
| T1: the unidentified "tile" kind of the cost model (other tile_redraw changes) | ~7.6 a change | to measure | rare in the busy scenes | identify first (pressure plates in other rooms? debris? the skeleton?) |
| P1: potion bubbles cached (part 17's option C/D) | 0.45 a tick | ~0.15 | potion rooms | measured: -0.08 a tick on average for ~45-58 bytes: not worth it |
| R1: op lists precomputed at build time per room (the static part) and read at the room draw | the build 11-14 a room change | to measure (the read cost against the build) | every room change, every size | size to measure: ~270 rooms of op lists; per level at the level start into free RAM-disk space? |
| R2: a cache of drawn cells across rooms, keyed by the tile and its neighbours | piece laying 39-71 a room change | to measure | every room change | rooms share many identical cells; RAM-disk space (16 MB; 512 KB / 1 MB after the reclaims) |
| R3: a level restart / death redraw | a full room draw | to measure | every death and Ctrl+A | whether the room in the shadow can be reused |
| S1: per-tick fixed costs: the PSG player, the keyboard scan, the VBLN interrupt, the HP strip and the bottom text | to measure | ? | every tick | the stages tools/roadmap.py does not separate yet |
| H1: real hardware | the emulator's numbers | to measure | everything | the MZPico's wait states (+1 per access: +0.035 a walking tick, +1.28 a room change) and the real machine's timing |

Re-rank sections 6 and 8 together once part 18 is built, by the visible gain per byte (resident free then: main ~236
if part 18 takes ~75).
## M8a part 18: loose floors (2026-11-08)

Status: **built.** Candidates 1 and 2 of the speed roadmap ("Speed roadmap (2026-11-08)", PR #35, part 1 "Falling
floors"; its tools tools/loosescenes.py and tools/roadmap.py), measured before and after on main f004916.

### What changed

1. **A loose floor redraws only when its picture changes, and regenerates only the tiles that draw it** (spike.asm
   loose_redraw, a case of anim_redraw; view.asm loose_pic). Its picture is LOOSE_FRAM_BOTTOM[loose_frame(modifier)]:
   three pictures (43 / 73 / 74; the left piece 41 / 69 / 70 and the right one 42 / 71 / 72 follow the bottom), so of
   the 10 countdown ticks of a floor stepped on (frames 1..10) those into 4, 6, 7, 9 and 10 draw nothing; before,
   every modifier change was a full tile_redraw (3 regenerations, ~3.5 frames). A picture change regenerates what
   spike_redraw regenerates (sr_1: no pre-drawn pictures): our room's floor its own tile and, for columns 0-8, its
   right neighbour (draw_tile_anim_right, dtar_loose); the left room's column 9 our column 0; the above room's row 2
   its own tile (draw_tile_above: draw_loose, no anim_right); the below room's row 0 nothing. The tile above-right
   (draw_tile_topright reads only the type) and, for a left-room floor, the row above our column 0 are no longer
   regenerated. A knock shake (0x81..0x84) changes the picture every tick: it keeps its redraws, one regeneration
   fewer each.
2. **A falling floor is laid only in the compose chunks it touches, and the torch cache tests the chunk** (people2.asm
   mob_lay / mob_meet, main block). obj_chunk's loop over MOBR (low block) is now a call to mob_lay, which lays a floor
   only when its rect (OMOBR, same index: its three pieces 70, 74, 72 lie inside x .. x + 8, ybottom - 16 .. ybottom)
   meets the chunk. tc_try asked MOBR_N, so any falling floor on screen switched the torch cache off for the whole
   tick; it now asks mob_meet (the same loop, A = 1 on the first floor that meets the chunk).
3. **A pixel bug found on the way: a falling floor whose top is above the screen was never drawn** (sprite.asm
   mobs_visible). Clipping the rect's top at row 0 cleared E but left D = 0xFF, and the next test took the floor for
   one below the screen: a floor falling in from the room above (and its first rows on our screen, ybottom < 16) was
   left out of MOBR, so for its first ~2-4 ticks the top rows showed black where the reference draws it (ld de, 0: +1
   byte of low). main showed it in four of loosescenes.py's ten scenes (level 13's falling ceilings: fall_a 1,880
   pixels, ride_a 1,192, shake_a 295, multi_a), with the same VRAM and state as this change's first draft every tick;
   the committed tests have no such floor on screen. These ticks now draw the floor (a little more work than before).

**Which tiles draw it** was checked against the Python reference for every loose floor of levels 1-14 on every screen
that shows it (tools/movecheck.py loose: RoomRenderer's op lists tagged with the tile whose draw emitted them, every
pair of modifiers 0..11, 0x80..0x8B): the same picture gives identical lists, a different one changes only the tiles
above (own 172, above 76, below 45, left 13 screens, 84,456 pairs, 0 differ).

Resident: **main +72** (end_of_code 0x7AC9 -> 0x7B11, 239 free: mob_meet / mob_lay 48, loose_redraw 19, its case in
anim_redraw 5), **low -16** (end_of_low 0x1FF7 -> 0x1FE7, 25 free: obj_chunk's loop -26, loose_pic +9, the top
clip +1), block 2 0
(tc_try's test is as long as before). Nothing on the RAM disk.

### Per phase (loosescenes.py measure, 1 MB, frames a tick: median / p90 / worst over the 10 scenes, levels 1-14's
best (levels 13, 10, 11) and level 1's; the phases as the roadmap's, but "sh" split: sh the picture changes, shf only
loose_frame changes (the countdown ticks this skips), sh- the modifier only; mean is the mean change a tick)

| phase | kid | ticks | before | after | mean |
|---|---|---:|---|---|---:|
| shake, the picture changes (sh) | moving | 91 | 10.14 / 17.05 / 33.95 | **8.78** / 14.93 / 30.89 | -1.52 |
| | still | 15 | 4.75 / 7.12 / 7.41 | 4.98 / 7.10 / 7.21 | -0.23 |
| shake, frame only (shf: 4, 6, 7, 9, 10) | moving | 43 | 5.33 / 7.71 / 8.11 | **3.94** / 5.15 / 6.13 | -1.59 |
| | still | 10 | 5.17 / 7.08 / 7.54 | **3.93** / 5.52 / 5.76 | -1.22 |
| release (rel) | moving | 27 | 13.96 / 19.89 / 23.17 | 13.38 / 18.09 / 22.09 | -0.51 |
| | still | 8 | 7.84 / 16.48 / 18.64 | 9.61 / 17.31 / 17.42 | +0.83 |
| one floor falling (mob1) | moving | 98 | 8.03 / 12.92 / 17.65 | 7.97 / 11.11 / 17.87 | -0.44 |
| | still | 9 | 5.82 / 7.16 / 8.79 | 5.99 / 6.54 / 7.01 | -0.33 |
| two to five falling (mob2+) | moving | 35 | 12.05 / 17.36 / 19.61 | 12.01 / 17.48 / 18.73 | -0.30 |
| | still | 24 | 10.37 / 14.93 / 15.54 | 10.06 / 13.84 / 16.28 | +0.04 |
| landing (land) | moving | 21 | 15.47 / 21.54 / 28.50 | 13.58 / 20.56 / 27.50 | -1.60 |
| | still | 6 | 15.14 / 21.71 / 21.71 | 15.15 / 22.61 / 22.61 | -0.16 |
| nothing (none) | moving / still | 241 / 231 | 4.03 / 3.99 | 4.04 / 3.99 | 0.00 / -0.05 |
| a room draw (R) | moving | 7 | 97.87 / 105.10 / 106.07 | 98.03 / 105.95 / 106.09 | +0.39 |

**The 8-floor knock** (shake_a, level 11 room 8, ticks 16-20): the landing tick 17.05 -> **4.35** (it sets the
modifiers of the row's 8 floors without a picture change: sh-), the four knock ticks 33.9 -> 30.9 each (8 floors
change the picture every tick; one regeneration fewer each, -0.37 a floor).

The countdown ticks without a picture change now cost what walking costs (3.94 against none's 4.04). Falling floors
gain less than the roadmap's estimate (one floor -1.0..-1.5): the clipped lay_mob calls were cheap. In level 1's ride
(room 8, ticks 14-20, one floor, tools/roadmap.py range) lay_mob runs 2 times a tick instead of 5, but its frames go
only 1.52 -> 1.32: a floor's rect, old and new, is in 2 chunks anyway, and the 3 calls that clipped everything away
cost ~0.07 each (the roadmap's ~0.35 a floor and chunk was the mean over all calls, the drawing ones included). In level 13's multi stretch
(ticks 10-34, 2-5 floors) lay_mob 2.86 -> 2.76 and the mean tick 14.21 -> 13.80 (the draft without fix 3: lay_mob 2.28,
12.89; the ceilings falling in from above are drawn now). The torch cache now runs while a floor falls, but right after a
release it is cold (the release's tile_redraw moves the op records: flames_sync renews the registry and tc_try flushes
the cache), so in the ride the 6 falling ticks save 4 pictures a tick (tc_save +0.18) and hit none before the kid falls
into the next room; the cache pays when a floor falls in a room the kid stays in. The level-1 release still
(1 tick) is +1.77: beam phase on +0.38 of work (those saves). The several-floors and room-draw rows hold fix 3: level
13's ceilings falling in from above are now drawn in their first ticks (multi's room draw +0.85, shake's tick 71
+1.96: work the reference always did); with the draft that left them out, mob2+ was 11.42 / 15.80 / 18.55 (-0.82).

### perfcheck (one run per size; main f004916's own runs; baselines lowered where beaten, in this commit)

| Stretch | 512 KB main / new | 1 MB main / new | 16 MB main / new |
|---|---|---|---|
| normal tick (walkthrough 30-60) | 5.47 / **5.27** | 5.12 / **4.89** | 5.00 / **4.81** |
| level door step (walkthrough 203-207) | 9.23 / 9.23 | 8.56 / **8.51** | 8.56 / **8.51** |
| room change (walkthrough 89) | 106.05 / 106.06 | 106.05 / 106.07 | 105.22 / 105.57 |
| walkthrough 190-260 | 6.35 / 6.35 | 6.14 / **6.11** | 5.78 / 5.78 |
| gate (gate_push 200-260) | 4.09 / 4.09 | 4.09 / 4.09 | 4.09 / 4.09 |
| traps (traps_b1 0-300) | 5.55 / **5.46** | 5.24 / **5.15** | 5.18 / **5.10** |
| fight (fight1 60-160, guard on) | 7.09 / 7.09 | 6.28 / 6.30 | 5.96 / **5.94** |

The normal tick's knock-shaken floor (ticks 55-58) was 0.6 of it: -0.19..-0.23. The 16 MB room change +0.35 is the
beam: the tick's stages are equal within 0.01 (tools/roadmap.py stages) but the object pass's last copy waits 0.36
instead of 0.04 frames (pf_seq). The other increases (+0.01, +0.02) are beam phase too (fight1: the stages within 0.03,
which way differs by size).

### Same pixels, same logic

tests/m4_game.py --every 1 (state and VRAM every tick) at 512 KB, 1 MB and 16 MB on 57 scripts a size: the ten
loose-floor scenes of loosescenes.py find (levels 1-14 and level 1 alone, the a scripts), the walk_a and stand_a scenes
of busyrooms.py find --worst (20 rooms), traps_b1, b9, b39, b40, walk_level1, level13_exit and level12_exit_level13:
0 state diffs, 0 differing pixels, except multi_a (level 13): from tick 47 on (3 state diffs, the screen). There the
kid dies at tick 40 (a floor lands on him) and the game program restarts the level at tick 47 (its state cleared, a
full redraw), which kidsim's death does not follow; the scene has no '# draw after death' line, and adding one does
not help (the restart is not the death text). It is the scene, not this change: main gives the same VRAM and state
every tick (a per-tick CRC comparison of the two builds), and m4_test (logic only) passes it. Before fix 3, fall_a,
ride_a and shake_a differed too, on main as well (the floor falling in from above, see "What changed" 3).
tests/m4_test.py on the ten scenes, traps_b1, b9, b39, b40 and walk_level1: 0 differing. tools/movecheck.py loose: 0
differ. `make ci-build`, `make cheats`. The full regression on the runners: see the PR.

## Speed roadmap: re-evaluation measurements (2026-11-08)

Status: **measured, nothing built.** These are the numbers for re-ranking sections 6 and 8 of "Speed roadmap
(2026-11-08)" after M8a part 18. Measured on main 5c0596e, 1 MB, no waits. The tool is tools/reeval.py (`fixed`, `lay`,
`loose`, `gates`, `events`, `census`, `oplists`, `blocks`, `masks`). The scenes are those of loosescenes.py and of
busyrooms.py `find --worst` (not committed). "a - b" is the work above the same ticks with the objects patched away.

### Per situation (frames a tick; a - b where measured)

| situation | frames median / p90 | a - b median / mean | source |
|---|---|---|---|
| walking (walk_level1 30-60) | 4.30 / 7.71 (mean 4.89) | | roadmap.py range |
| fight (fight1 60-160) | 5.37 / 10.08 (mean 6.30) | | roadmap.py range |
| loose floor, one picture change (shp, kid moving, 57 ticks) | 7.97 / 9.30 | **4.01 / 3.36** | reeval.py loose, the 10 scenes |
| loose floors, two or more pictures (shp2: knocks) | 11.59 / 30.87 | 7.39 / 12.89 | |
| loose floor, frame only (shf) | 3.94 / 5.15 | 0.06 / 0.18 | |
| release (rel) / landing (land) | 13.38 / 18.09; 13.58 / 20.56 | 9.37 / 9.07; 7.61 / 5.91 | |
| one floor falling (mob1) / 2-5 (mob2+) | 7.97 / 11.11; 12.01 / 17.48 | 3.93 / 4.17; 7.53 / 7.31 | |
| chopper picture change / modifier only | | 4.22 / 0.14 a change (fit) | busyrooms.py fit, 9,446 ticks |
| C1: a chopper with blood (the kid dead next to it) | 11.52 work | ~+7.0 a step (against 4.49 dead with no change) | chomper.txt, 19 steps |
| spike picture change | | 4.12 a change (fit) | |
| torch / potion (each, every tick) | | 0.39 / 0.46 | fit |
| gate, a plain shift (open, 39 % of the 1,182 visible gate steps) / at a dungeon pillar (13 %) | | 1.72 / 2.74 | reeval.py gates (walk_gate, ticks with one step) |
| gate, a regenerating step (8 %) / at a dungeon pillar (3 %) | | 3.21 / 4.32 | |
| **G3** closed band (15 %) / at a dungeon pillar (5 %) | | **4.10** / 5.55 | |
| **G1** palace pillar (13 % in these scenes; 8 of the 90 gates) | | **6.06** | |
| **G2** drop (2.4 %) | | **8.15** | |
| **G4** to or from 47 (1.6 %) | | **8.25** (6 ticks) | |
| button: a hit (79 % of the 77 button changes) / **B1** the first change since the room draw (21 %) | | 1.41 / **5.55** (with the overlay loads) | |
| room change, l01r01 dungeon (walkthrough 89) | 106.07 | op lists 11.79 + buckets 2.44, fill 2.75, laying 57.61, shadow write 11.67, copy 11.36 | roadmap.py stages |
| room change, l04r04 palace | 86.02 | 9.00 + 2.08, 2.75, 43.44, 11.66, 11.44 | |
| R3: the restart after a death (traps_b9 1446) | 107.43 | load_level 12.10 + the room draw 89.03; then 4 ticks of 8-13 | |

T1 (the cost model's "tile" kind, 7.59 a change over 4 ticks) is **the loose floor's release and landing**. Those 4
ticks are l02r18's ticks 20 and 29, the only "tile" ticks in the scenes. Their costs are the rel and land rows above.

### S1: the fixed costs (walk_level1 30-60, frames a tick)

| part | frames a tick |
|---|---:|
| view_snapshot | 0.071 |
| trace_cksum (the harness only) | 0.081 |
| text_chk | 0.030 |
| the interrupt (with the PSG player at SND_MODE 1: ~0.02) | 0.013-0.030 |
| the controls: the script / the keyboard and joystick scan (read_inputs 0.014, key_scan 0.002) | 0.005 / 0.019 |
| hp_draw + ghp_draw | 0.006 |
| the sound model | 0.005-0.013 |
| flash_tick + dirty_reset | 0.002 |

The game pays **~0.17 a tick** for these, and nothing is above 0.07. Not a lever.

### How often (levels 1-14)

There is no playthrough of levels 2-14. walkfind.py runs at ~37 expansions a second and found no route on level 2 in
3,000. The counts below come from kidsim (reeval.py events) and the level data (reeval.py census):

- **walk_level1 (318 ticks):** 3 room draws, 9 shp, 5 shf, 1 release, 1 landing, 4 G2 steps, 1 B1, 3 button hits.
- **The test scripts (m4, m5, m6: 18,119 ticks):** a room draw every 181 ticks, 12 deaths. Of 53 button visits, 18
  changed the button once (the press is the only change, so B1 is all there is) and 35 changed it twice or more.
- **The census:** 316 rooms, 90 gates (8 at a palace pillar: G1), 99 openers, 29 closers (drops), 39 choppers, 116
  spikes, 169 loose floors, 354 torches, 50 potions. 16 screens have a chopper or spike in the room above's row 2 or
  the left room's column 9 (C2).
- **A gate's open-and-close cycle** has 94 visible steps: 56 plain, 14 regenerating, 22 in the closed band (G3), 2 at
  47 (G4). A closer's drop is 4-5 G2 steps instead of the closing. The per-game gate mix below comes from this
  cycle and the census (G3 = 22/94 of the steps of the 82 non-G1 gates, G1 = 8 of the 90 gates' steps, G4 2 a cycle,
  G2 = 29 closers x ~1.5 x 4.5), not from the busy scenes' shares in the table above (busy rooms over-represent G1).

The table estimates one completion. It assumes ~40,000 ticks, each gate ~1.5 cycles with ~70 steps seen, each button
pressed 1-1.5 times, ~60 % of the loose floors set off and 5-15 deaths on choppers:

| event | a game (estimate) | gain a hit (candidate) | frames a game |
|---|---:|---:|---:|
| room changes | 300-500 | R1 -8.4..-13.2; laying loops -18..-20; R2 -25..-30; copy + shadow floor -9 | R1 -2,500..-6,600; loops ~-7,600 |
| deaths (R3) | 20-100 | each is a full room draw + 12 (load_level) | |
| gate steps | ~8,000 | | |
| of them G3 / G1 / G4 / G2 | ~1,700 / ~700 / ~250 / ~200 | -2.1 / -3.5 / -6 / -5.6 | -3,600 / -2,450 / -1,500 / -1,100 |
| loose picture changes (shp) | ~800-1,000 | L2: -3 | ~-2,700 |
| releases + landings (T1) | ~200 | | |
| chopper steps / C1 | ~2,000 / 100-300 | C1 -5.7 (the kid is dead: little is seen) | C1 ~-1,100 |
| C2 steps | < 100 | ~-2 | < -200 |
| button misses (B1) | ~130-200 | -4 | ~-700 |
| every tick (the copy by POP / PUSH or LDI, plane-major) | ~40,000 | ~-0.14 walking (pf_blit1 0.43) | ~-5,600 |

### R1: op lists precomputed per room (reeval.py oplists; the Python reference's lists, equal to room.asm's)

**Size.** A room has 56-103 back records and 35-68 fore records (max 185 / 126). The lists and their tags (9 bytes a
record) take **820-1,448 bytes a room** (max 1,872). The cell buckets add ~124-202 bytes. The slice tables (480 bytes)
are rebuilt by slices_build in under 0.7 frames. **Per level that is 8.4-34.7 KB**, 397 KB for all 14 levels. zlib -9
packs a level into 1.7-7.8 KB (89 KB for all).

**Read cost.** At the room draw, ~1.6-2.1 KB by INIR (21 T a byte) plus ~10 seeks is **~0.5-0.7 frames**, and the
slices ~0.5 more. room_ops + bkt_build cost **11.1-14.2** today (l04r04 9.00 + 2.08, l01r01 11.79 + 2.44).

**What is not static.** These are the records of the screen's animated tiles: its own, the left room's column 9, the
above room's row 2 and the below room's row 0. A screen has 2.7-6.5 such tiles (max 15). Per room 5.7-17.5 records (level means; max 69, level 10's gates) are
changed or removed by a state, or added by one (counted per tile as its state with the most added):

- gates: the bar records and slices move with the position;
- loose floors: the picture, and empty or rubble after a fall;
- choppers and spikes: the frame, and the blood;
- buttons: pressed is drawn as floor or stuck;
- torches: the flame (op patch);
- potions: the bubble (op patch), and floor once taken;
- the sword and the level door.

**The patch at the draw.** Every animated tile whose (type, modifier) differs from the stored state is regenerated by
tile_regen (~0.5 frames each); op_patch handles the flames and bubbles. That is typically 0-3 tiles. The new cost is the
read 0.5-0.7 + the slices ~0.5 + the patches 0-1.5 = 1.0-2.7 frames, against 11.1-14.2: **-8.4..-13.2 a room change
on every size**.

**Where the lists come from:**

- precomputed on the PC: ~7 KB a level, packed on the floppy;
- built at the level start: 24 x ~13 frames, ~6 s;
- built at each room's first visit: then only revisits gain.

They need ~35-47 KB of RAM disk a level: free on 16 MB, after a reclaim on 512 KB / 1 MB.

### The room change's laying (reeval.py lay: a tracepoint at the head of every phase, cycles to the next)

l01r01 reads 53,500 bytes (rec_lay 57.61 frames: ~77 T a byte); l04r04 reads 39,510 (43.44):

| phase | l01r01 | l04r04 | per unit |
|---|---:|---:|---|
| masked rows (7,228 / 5,460 plane rows: cmx_n and the row step) | 28.46 | 21.23 | 280 T a row: 53 T a byte (20,720 bytes) + ~128 T a row (call 17, ret 10, three strides, the drop test, the loop) |
| copy rows (5,432 / 3,752 rows) | 11.63 | 7.73 | 147 T a row: INIR 21 T a byte + ~65 T a row |
| the mask block (INIR), the per-plane setup and seek, the plane ends, the masked setup | 6.76 | 5.21 | ~400 T a plane |
| copy plane setup, seek, end | 2.33 | 2.26 | ~700 T a piece |
| piece setup (lay_piece16 1,640 T; the record and dir_entry 750 T) | 6.21 | 5.34 | ~2,400 T a piece (185 / 158 pieces) |
| the scan (rec_lay's tests 342 T, the cover scan, the buckets) | 2.54 | 2.47 | |
| mono / black rows | 0.51 | 0.13 | |

**Best per byte with today's data format:** a specialised loop per width (rows unrolled, page-aligned buffers, inc l /
inc e, no drop test):

- the masked row step 128 -> ~30 T: -10 frames;
- the masked bytes 53 -> ~45 T: -2;
- the copy row step 65 -> ~30 T: -2.5;
- precomputed plane offsets and one seek a plane: -2..-3;
- a lighter piece setup: -3.

Together **~-18..-20 of 57.6**, to ~50 T a byte. **Built in M8a part 20** ("M8a part 20: faster piece laying"): rec_lay 57.6 -> 40.3
(-17.3), the room change 106.6 -> 88.3 at 1 MB.

**With a new mask format.** Of the masked pieces' bytes, 29.9 % are fully opaque, 27.7 % fully transparent and 42.4 %
partial (reeval.py masks). Copying the opaque runs and skipping the transparent ones would cut the masked arithmetic
from 53 to ~31 T a byte on average, another ~-6.

**Not a lever:** the fore pieces are ~55 % of the bytes laid in a full draw, but a fore piece that lays its back twin
again with nothing over it is only 0.2 % of them.

**R2** (reeval.py blocks) is a cache keyed by a block's op list (equal lists give equal pixels):

- **Repeats.** The renderer's 8 x 64 cells repeat little: 21 % of the instances are repeats, 18 % with the fore
  pieces. **Tile blocks (4 bytes x 63 rows, one tile's place) repeat 87 %** for back + mid and 78 % with the fore. A
  level has 49-113 distinct back blocks (1,216 for all levels), 129-169 with the fore (2,070).
- **Cost.** A hit reads ~1 KB a version by INIR (~0.3 frames) instead of ~1.9 frames of laying. With both versions,
  that is ~-25..-30 a room change once a level's blocks are cached.
- **Memory.** ~230 KB of RAM disk a level: 16 MB only, 1 MB has no room.
- **Design.** The block ids are static per room (R1's data, 30 bytes a room), and the animated tiles' blocks are drawn
  as today. The full draw needs tile-aligned 8 x 63 cells and a 3-row strip.

### The copy and the shadow write (bounds for candidate 9)

**Today, per room change:**

- The copy (blq_8) costs 196 T a plane row of 8 bytes (8 LDI 128, the plane select 18, the pointers 50): 24.5 T a
  byte, 11.1-11.4 frames. The emulator shows no VRAM waits.
- The shadow write costs OUTI 16 T a byte plus a seek every 8-byte row: 27 T a byte, 11.67 frames.

**Floors for the 30,720 bytes (4 planes x 40 x 192):**

- **The copy, plane-major by POP / PUSH: ~15.6 T a byte, 6.7 frames.** 8 LDI plane-major take ~18.4-20.5 T (7.9-8.8
  frames). The write modes do not help 4-plane data: they write one byte to every selected plane, or one colour.
- **The shadow write, OUTI with one seek a contiguous run: 16.1 T a byte, 6.9 frames** (a cell-major shadow; band
  cells 17.2 T, 7.4 frames).

Together **22.8 -> ~13.6 (-9)**. The copy alone gains -4.4. In play, the same rule takes ~0.14 of walking's 0.43 frames
a tick of pf_blit1.

### Memory (main 5c0596e)

| area | free |
|---|---|
| main (end_of_code 0x7B11, W1 at 0x7C00) | **239** |
| low (end_of_low 0x1FE7) | **25** |
| block 2 (block2_end 0xEBED, LEVEL 0xEC00) | **19** |
| W1 overlays | room 86, events 15, gleave 682, genter 81, keys 555, rare 601, gate (anim) 10, buttons 203, door 156, frames 4 |
| W2 overlays | level 1,823, text 3,075, save 3,399 |
| the fill overlay (WF) | 83 |
| RAM disk page 7's overlay area | 743 |

## M8a part 19: reclaim (2026-11-08)

Status: **built.** Step 0 of the speed roadmap's order: resident memory for the next steps (faster piece laying in the
room draw, the POP / PUSH copy into VRAM), from section 7 of "Speed roadmap (2026-11-08)". No visible change: the
pixels and the logic are exact by construction and by the tests.

### What changed

1. **PR_TAB to the RAM disk** (room.asm, prbuild.asm). The wall pattern's draws mod 140 (64 seeds x 10, the table the
   generator builds once) moved from low RAM 0x0500-0x077F to RAM-disk page 6 0x1440-0x16BF (the torch cache's part
   freed by M8a part 17; the same place on 512 KB, 1 MB and 16 MB: the frame store and the 16 MB slots are in pages 8
   and up). pr_build writes it in order through the data port (pr_slow does not touch the RAM disk); pr_start seeks the
   seed's row and reads its 10 bytes by INIR into PR_BUF (low RAM 0x012C, free since part 17), from which prandom takes
   them as before. The game builds it at every start of the program (gstart.asm game_start: every boot and every swap
   back from PRES, whose sound bank overwrites page 6 0x0000-0x287F; the launcher zeroes low RAM then too); the test
   programs (m3test, m3demo, m4test) at their first wall pattern, as before.
2. **The kid trace's room checksum out of the game** (objects.asm room_checksum 53 bytes, its call and store in kid.asm
   6, game.asm trace_cksum 9). It is assembled into m4test only (`if not defined GAME_OVL`), which keeps its own
   checksum at the trace point (tests/m4_test.py against kidsim, unchanged). The game's harness computes it from the
   level in memory at tick_done (tests/m4_test.py level_cksum, z80_state(level=...)): tests/m4_game.py captures the
   level (1,440 bytes) in its tracepoint and compares it with kidsim's level after the step (tick_end_line), tests/m8_pace.py
   reads it at tick_done in both runs. The value at tick_done is not always the trace point's: the guard's frame
   (check_press, spikes), exit_room and a level load come after it; over the 74 scripts of tests/m*_scripts kidsim's two
   values differ on 22 of 20,377 ticks (fight_killpush 10, fight_spikes 2, the shadow and exit scenes, Shift+L),
   so both sides take the tick's end.
3. **sprite_forget and room_drawn into the room overlay** (section 7's cheap overlay moves). The room overlay's entry
   0 is now rf_game: draw_room_full, then sprite_forget's body (src/m4/sprforget.inc), the button cache's bc_v = 0 and
   a jump to frm_reset (which ends in flames_rebuild); game.asm's two calls after draw_room_full and anires.asm's
   room_drawn are gone. sprite_forget now runs before frm_reset, not after it: nothing in frm_reset, flames_rebuild,
   flames_build or op_patch reads what it clears (the characters' old rects, OMOBR_N, ST_OK). The level-start overlay
   has its own copy (its jp sprite_forget). tc_flush stays resident: tc_try calls it in play.
4. tools/roadmap.py stages: the wall pattern rows (pr_start) as a stage; the room draw counted once (the overlay now
   calls its draw_room_full); "after the draw" is measured by tracepoints from the draw's return (room_drawn, since
   rf_forget) to game.asm gmt4, the same interval in both revisions (the button cache's reset, frm_reset with
   flames_rebuild, sprite_forget): walk_level1 tick 89 at 1 MB 0.40 before, 0.41 after. tools/reeval.py lay (#37)
   ends at rf_forget where room_drawn is gone.

Resident (main 5c0596e -> this):

| area | before | after | freed |
|---|---|---|---:|
| main code (end_of_code) | 0x7B11, 239 free | 0x7AD7, 297 free | **58** (checksum 68, the two calls 6; pr_start +16) |
| low RAM data 0x0000-0x0FFF | PR_TAB 0x0500-0x077F | 0x0500-0x077F free; PR_BUF 10 bytes at 0x012C | **640** contiguous (630 net) |
| low code block (end_of_low) | 0x1FE7, 25 free | 0x1FCF, 49 free | **24** (sprite_forget) |
| block 2 (block2_end) | 0xEBED, 19 free | 0xEBE6, 26 free | **7** (room_drawn) |
| room overlay (W1) | 938 B, 86 free | 975 B, 49 free | -37 |
| level-start overlay (W2) | 2,273 B, 287 below WF | 2,299 B, 261 below WF | -26 |
| page 7's overlay area | 743 free (the cheat build ~329) | 680 free (the cheat build 266) | -63 |
| RAM disk page 6 | 0x1440-0x287F free | PR_TAB 0x1440-0x16BF; 0x16C0-0x287F free | -640 |

What the freed low RAM can hold: docs/memory.md "The free low RAM 0x0500-0x077F" (code too, also code that runs
with VRAM mapped, but copied in by game_start at every start: the launcher zeroes 0x0000-0x11FF and no loader can put
it there).

### Cost (tools/roadmap.py stages walk_level1 89, the perfcheck room change: 42 wall patterns with a table row)

pr_start: 0.09 -> 0.27 frames, +0.18 (+305 T a wall pattern: the seek 65, INIR 205, the rest 35; 42 more seeks and
pages, 420 more data reads; the room overlay's load +37 bytes, +0.01). The kid's tick -0.08 in the harness runs only
(trace_cksum ran room_checksum under script control; the release returned at once). The work of a room change: +0.11.

| tick 89 (frames) | 512 KB main / new | 1 MB main / new | 16 MB main / new |
|---|---|---|---|
| the tick | 106.06 / 106.17 | 106.07 / 106.58 | 105.57 / 105.56 |
| op-list build (room_ops, with pr_start) | 11.79 / 11.97 | 11.79 / 11.97 | 11.79 / 11.97 |
| kid logic (kid_tick) | 1.59 / 1.51 | 1.59 / 1.51 | 1.59 / 1.51 |
| object pass (draw_objects) | 5.35 / 5.35 | 5.36 / 5.75 | 4.86 / 4.73 |

The rest is the beam: the object pass's last copy waits for it (1 MB +0.39, 16 MB -0.13), as in part 18's 16 MB room
change.

### perfcheck (one run per size; main = 5c0596e, the part 18 runs (512 KB and 1 MB measured again here, within 0.02);
lowered where beaten, in this commit)

| Stretch | 512 KB main / new | 1 MB main / new | 16 MB main / new |
|---|---|---|---|
| normal tick (walkthrough 30-60) | 5.27 / **5.22** | 4.89 / 4.89 | 4.81 / 4.81 |
| level door step (walkthrough 203-207) | 9.23 / 9.23 | 8.51 / 8.51 | 8.51 / 8.51 |
| room change (walkthrough 89) | 106.06 / 106.17 | 106.07 / 106.58 | 105.57 / 105.57 |
| walkthrough 190-260 | 6.35 / **6.27** | 6.11 / **6.08** | 5.78 / **5.71** |
| gate (gate_push 200-260) | 4.09 / 4.09 | 4.09 / 4.09 | 4.09 / 4.09 |
| traps (traps_b1 0-300) | 5.46 / **5.41** | 5.15 / **5.11** | 5.10 / **5.07** |
| fight (fight1 60-160, guard on) | 7.09 / **7.00** | 6.30 / **6.21** | 5.94 / **5.86** |

The faster stretches are the harness's trace_cksum gone (room_checksum ran every tick under script control: ~0.08 a
tick of work; the release never paid it), so the baselines follow the measurement, not a gain for the player. The room
change is the cost above plus the beam (1 MB +0.51 of which +0.39 is the object pass's wait). The 16 MB column is the
build before change 3 (the overlay moves: +37 bytes of room overlay load, +0.01 a room change); a 16 MB perfcheck run
of the final build hung in the emulator when run beside the others (as one of main's did) and was not repeated.

### Same pixels, same logic

tests/m4_game.py --every 1 (state, with the checksum from the level, and VRAM every tick) at 512 KB, 1 MB and 16 MB on
20 scripts a size (walk_level1, run_rooms, traps_b1, gate_push, frm_button, frm_spike_btn, btn_bars, chomper, fight1,
fight_killpush, fight_spikes, fight_chomper, level4_mirror, level6_shadow_exit, level12_exit_level13, level13_exit,
level3_checkpoint, feather_fall_guard, level5_shadow_potion, potion_upside_down): 0 state diffs, 0 differing pixels.
tests/m3_test.py levels 1 and 4 (every room, the wall patterns): 0 differing pixels. tests/m4_test.py on walk_level1,
fight_killpush, fight_spikes, level12_exit_level13, level3_checkpoint: 0 differing. tests/m7_launch.py (the PRES swaps:
PR_TAB rebuilt after PRES's sound bank) and tests/m8_pace.py: ok. `make ci-build`, `make cheats`. tests/m5_boot.py
needs a newer emulator than the local trace build (its 16 MB probe: "lists 52 RAM-disk pages of 256"): on the runners.
The full regression on the runners: see the PR.

## M8a part 20: faster piece laying (2026-11-08)

Status: **built.** Step 1 of the speed roadmap's order: the room draw's piece laying ("Speed roadmap: re-evaluation
measurements", "The room change's laying": 57.6 of the 106-frame room change, ~77 T a byte read). The piece data
format is unchanged (an RLE / opaque-run mask format stays a later candidate). The pixels are exact by construction and
by the tests; the same code lays every piece in play (tile regenerations, falling floors, the fore pieces of the object
pass), so play gets faster too.

### What changed (src/m1/gfx.asm lay_piece16 and below; tools/gen_kernel.py)

1. **Masked rows (mode 1): one unrolled chain for every width** (lmx_ent). The mask rows are read once a piece into
   MASKBUF **at the compose rows' own offsets** (MASKBUF + (dst & 0x1FF): the mask byte of a compose byte has its low
   address byte, so one `inc l` / `inc e` pair steps both and the row step sets E = L). A row is n bodies of
   `ld a, (de); and (hl); ld c, a; in a, (RD_DATA); or c; ld (hl), a; inc l; inc e` (48 T; the last byte without the
   increments, 40 T), then a patched `jp` into a 7-deep chain of `in a, (RD_DATA)` (the k = w - n bytes of a piece
   clipped at the sides: the rest of the row and the next row's start), the row step (`ld a, l; add a, 9 - n; ld l, a;
   ld e, a; jr c`, a page crossing every 32 rows) and `djnz` with a patched displacement back to the n-byte entry. A
   row costs 48 n + 41 + 11 k T (the patched `jp` into the drop chain 10, the row step 26, `djnz` 13; a page
   crossing, every 32 rows, +13), against 53 n + 128 + 25 k before (cmx_n by `call`, three strides, the drop loop's
   test). `IN A,(n)` (11 T, no C) frees B for the row count; the port's high address byte is A, which the RAM disk
   does not decode (boot.asm and kid.asm already read it so).
2. **Copy rows and the mask rows: an INI chain** (lr_ent): n `ini` (16 T a byte instead of INIR's 21), the same drop
   chain and row step (`dec d; jp nz` to the n-byte entry): 16 n + 46 + 11 k T a row (the `jp` 10, the step 36; a
   page crossing +9) against 21 n + 65 (+ the drop loop). The mask read uses it into MASKBUF (one INIR of the whole block before; the strided block and its 513-byte
   limit are gone). A piece whose last column is partial (the right edge, the extent mask V_RM) has its own chain
   (lre_ent: n - 1 `ini`, the last byte merged); a partial first column (both edges, rare) a small loop (lle_ent).
3. **The plane loops in registers** (lpx_plane, lcf_p): the plane's RAM-disk page and address in A:HL, one `out` pair a
   plane (no far_seek_entry), the plane size, the compose row, the mask and the row count patched into the loop, the
   plane counter in A'. ~450 -> ~250 T a plane.
4. **The piece setup in registers** (lay_piece16 to the mode dispatch): the clip with the rect in registers, the two
   products (the row offset, the plane size w x h) by repeated addition (w <= 8). 1,540 -> 1,110 T a piece. The chains'
   patches (lr_patch: the n part and the k part each kept while unchanged) 490 T a piece.
5. **Dead code removed:** the cmx_n chains (mode 1's row combine before), the cm1_n chains (unused since mode 1
   streams), the inr_n INI chains and lp_ini, the general copy path lpc_gen / lp_merge (no jump led there), lp_block
   (the mask block read), the INIR copy rows lpf_* and the variables V_EDGE, V_OLDL, V_OLDR, V_ROWS, DATABUF.

Pieces stay at most 8 bytes wide (the drop chains hold 7: every directory the renderer lays from has w <= 7; the people
are drawn by spr_draw, not here). MASKBUF must be 512-byte aligned (an `.error` guard).

**Where the code lives: main**, in place of the old laying code (gfx.asm and kernel_gen.inc are main code). The room
overlay (49 free), a second room overlay or the free low RAM 0x0500-0x077F were not needed: the new code is smaller than
what it replaces, and it must stay resident because play lays pieces every tick (an overlay load costs ~0.3 frames).

Resident (main b617782 -> this):

| area | before | after | |
|---|---|---|---:|
| main code (end_of_code) | 0x7AD7, 297 free | 0x76DA, **1,318 free** | **-1,021** (gfx.asm lay_piece16 .. fill_black -223 incl. the new chains ~330; kernel_gen.inc -798: the cmx, cm1 and inr chains and their tables) |
| low RAM data | MASKBUF 0x0C00-0x0DFF, DATABUF 0x0E00-0x0FFF | MASKBUF 0x0C00-0x0DFF (all of it: the rows at the compose offsets) | 0x0E00-0x0FFF **free** (512 B; DATABUF had no reader since mode 1 streams) |
| low code block, block 2, overlays, RAM disk | | unchanged | 0 |

### The room change (tools/roadmap.py stages, one tick, inclusive frames; main b617782 / this)

| room | 512 KB tick | 1 MB tick | 16 MB tick | rec_lay (every size) | of it masked rows / copy and mask rows (this) |
|---|---|---|---|---|---|
| l01r01 (walk_level1 89, the perfcheck room change) | 106.17 / **88.31** (-17.9) | 106.58 / **88.31** (-18.3) | 105.56 / **87.48** (-18.1) | 57.61 / **40.29** (-17.3) | 18.55 / 11.32 (17.29 cmx rows before) |
| l01r07 (dungeon, torches, a gate) | 98.15 / **82.20** (-16.0) | 98.15 / **82.20** (-16.0) | 98.23 / **82.36** (-15.9) | 54.43 / **38.56** (-15.9) | |
| l03r16 (dungeon, 3 choppers) | 103.76 / **86.07** (-17.7) | 104.47 / **86.77** (-17.7) | 103.75 / **86.17** (-17.6) | 59.49 / **41.79** (-17.7) | |
| l04r04 (palace, simple) | 87.24 / **73.95** (-13.3) | 86.05 / **72.89** (-13.2) | 86.05 / **72.89** (-13.2) | 43.43 / **30.28** (-13.2) | |
| l05r24 (palace, busy) | 109.78 / **90.93** (-18.9) | 109.47 / **90.61** (-18.9) | 109.47 / **90.61** (-18.9) | 62.91 / **44.07** (-18.8) | |
| l10r01 (palace, pillars, 4 gates) | 115.61 / **94.98** (-20.6) | 115.95 / **95.84** (-20.1) | 115.95 / **95.84** (-20.1) | 70.76 / **50.10** (-20.7) | |

(The rooms of tools/roadmap.py `enter`: l01r07 tick 22, l03r16 19, l04r04 23, l05r24 3, l10r01 3.) The RAM-disk
reads, writes and seeks of the tick are the same (the seeks: one `out` pair a plane as before, now without
far_seek_entry). The rest of the tick is unchanged but for the object pass (its fore pieces: walk_level1 89 5.75 ->
4.77 at 1 MB); the op lists (11.97), the shadow write (11.66) and the copy (11.36) are now the larger part.

**The prototype** (change 1 alone, the masked rows, measured before building the rest; 1 MB): walk_level1 89 106.58 ->
94.60 (-12.0; rec_lay 57.61 -> 46.25), l04r04 86.05 -> 77.42 (-8.6; rec_lay 43.43 -> 34.82). Then change 2's plain copy
rows -3.0, change 3 -1.5, change 4 -0.9, the edge chains -0.5 (walk_level1 89 at 1 MB).

**Where the laying goes now** (tools/reeval.py lay walk_level1 89, 1 MB; its marks extended to the new phases):
masked rows (lmx) 17.9 frames (3,054 T a plane), copy and mask rows (lr) 9.6, the right-edge rows 1.6, the piece setup
2.9 + the record and directory entry 2.0 + the chain patches 1.2, the plane loops 2.5, the scan 2.5, mono / black rows
0.5. The rows are now ~73 % of the laying: what is left is per byte (the masked byte's 48 T, INI's 16), i.e. the data
format (the opaque / transparent runs of the masks: "Speed roadmap: re-evaluation measurements", ~-6).

### perfcheck (one run per size; main = b617782's own runs; baselines lowered where beaten, in this commit)

| Stretch | 512 KB main / new | 1 MB main / new | 16 MB main / new |
|---|---|---|---|
| normal tick (walkthrough 30-60) | 5.19 / **4.93** | 4.89 / **4.69** | 4.81 / **4.61** |
| level door step (walkthrough 203-207) | 9.23 / **9.15** | 8.51 / **8.47** | 8.51 / **8.47** |
| room change (walkthrough 89) | 106.17 / **88.31** | 106.58 / **88.31** | 105.56 / **87.48** |
| walkthrough 190-260 | 6.27 / **6.21** | 6.08 / **6.00** | 5.71 / **5.66** |
| gate (gate_push 200-260) | 4.09 / 4.10 | 4.09 / 4.10 | 4.09 / 4.10 |
| traps (traps_b1 0-300) | 5.41 / **5.18** | 5.11 / **4.90** | 5.07 / **4.86** |
| fight (fight1 60-160, guard on) | 7.00 / **6.75** | 6.21 / **5.92** | 5.86 / **5.66** |

In play every tick that lays pieces gains: the object pass's fore pieces (the normal tick -0.20..-0.26, the fight
-0.20..-0.29), the loose floors' regenerations and falling floors (traps -0.21..-0.23). The gate stretch is +0.01 (its
ticks sit at the 4-frame floor; the chain patch costs a little on its small pieces).

### In play: the busy rooms (tools/roadmap.py range over busyrooms.py `find --worst` scenes, ticks 1-99, 1 MB; main / this)

| scene | frames median | p90 | mean | object pass (obj_chunk, mean) |
|---|---|---|---|---|
| l03r16 walk (3 choppers) | 8.96 / **7.97** | 14.55 / **12.99** | 9.48 / **8.75** | 6.52 / 5.81 |
| l03r16 stand | 7.64 / **7.19** | 12.01 / **11.60** | 8.65 / **8.07** | 6.20 / 5.80 |
| l05r24 walk (palace, busy) | 7.35 / **6.63** | 12.91 / **11.94** | 8.13 / **7.61** | |
| l08r23 walk | 6.70 / **6.34** | 10.94 / **9.98** | 6.94 / **6.53** | 5.91 / 5.24 |
| l08r23 stand | 6.54 / **6.09** | 10.96 / **9.89** | 6.47 / **6.06** | 4.82 / 4.46 |
| l10r01 walk (pillars, 4 gates) | 9.59 / **8.87** | 16.33 / **14.67** | 9.20 / **8.49** | 4.06 / 3.75 |
| l10r10 walk | 7.30 / **6.46** | 14.48 / **13.38** | 8.58 / **7.89** | 4.76 / 4.24 |
| l02r18 walk (loose floors, a gate) | 7.16 / **6.64** | 13.82 / **12.36** | 7.63 / **7.17** | 3.64 / 3.32 |

-0.4..-0.8 frames a tick on average in the busy rooms, -1..-1.7 at p90: the object pass's fore pieces and falling
floors, the regenerations (tile_redraw, run_rect) and the moving parts' pieces (gates, chopper and spike misses) all
lay through the same code. (The profiler lost l05r24's object-pass return before.)

### Same pixels, same logic

tests/m3_test.py every room of levels 1-14 (the full room draw against the Python reference): 0 differing pixels,
also after each step above. tests/m3_anim_test.py level 1 (every animated tile's redraw): 0 differing. tests/m4_game.py
--every 1 (the state and VRAM every tick) on seven busy-room scenes of busyrooms.py `find --worst` (l03r16, l05r24,
l10r01, l10r10, l08r23, l02r18, l04r18 walk_a) at 512 KB, 1 MB and 16 MB: 2,490 ticks, 0 state diffs, 0 differing
pixels; walk_level1 at 1 MB: 0. `make ci-build`, `make cheats`, `make pace`. Also m3_anim_test levels 4, 7, 10 and 13: 0. The full
regression on the runners (regress/laying at 550a205, run 42506358462: the m4 / m5 / m6 pixel sets at --every 1, the
story, PRES, launch / keys and sound parts at 512 KB, 1 MB and 16 MB, launch / keys at 1 MB + 1 wait; m3_test and
m3_anim_test of every level, the logic oracles at 1 MB): all 28 jobs passed. The commit after it changes only the
docs.

## Kid logic: measured (2026-11-08)

Status: **measured; A', C and E built in "M8a part 21: kid logic trims", A, B, D and G in "M8a part 23: collision rows"** (F not built). Candidate 12 of "Speed roadmap (2026-11-08)" section 6 ("kid logic trims"), on
main e334925 (M8a part 20), 1 MB, no waits. The tool is tools/kidlogic.py `profile SCRIPT T0 T1 [--csv OUT]`. For each
tick it stops at kid_tick's entry and runs mz800emu's call profiler from there to kid_tick's return. The return
address is read from the stack, so only the logic is profiled, and the logic's time is exact by cycles. It then
replays the pacing (game.asm mainloop, mode 0) from the measured work (ml_go to tick_done) and applies each trim's
modelled saving per tick. The busy-room scenes are busyrooms.py `find --worst` (not committed).

**The logic is less than the roadmap said.** kid_tick contains everything: tick_pre (the timers, mobs and trobs, the
guard's sight) and tick_post (jumped to: the guard's frame, the sword hits). Sections 3 and 4 added tick_pre and the
trobs to kid_tick's inclusive time a second time. The 1.00 of section 4 also held trace_cksum (0.08), which part 19
removed. Walking costs **0.92** a tick, not 1.20; a fight costs **1.20**, not 1.44.

### Per stretch (frames a tick)

| stretch | logic mean / median / p90 / max | frames mean / median (measured; replayed) | ticks with work > 4 |
|---|---|---|---:|
| walk_level1 30-60 | 0.918 / 0.905 / 1.091 / 1.126 | 4.694 / 4.36; 4.672 / 4.26 | 16 of 30 |
| fight1 60-160 | 1.204 / 1.162 / 1.378 / 1.643 | 5.916 / 5.02; 5.921 / 5.02 | 75 of 100 |
| traps_b1 1-300 | 0.886 / 0.916 / 1.084 / 1.497 | 4.635 / 3.99; 4.649 / 4.01 | 91 of 299 |
| l03r16 walk_a 1-100 (3 choppers) | 0.865 / 0.951 / 1.131 / 1.230 | 8.754 / 7.97; 8.749 / 7.97 | 95 of 99 |
| l05r24 walk_a 1-100 (palace, busy) | 1.028 / 1.000 / 1.342 / 1.602 | 7.612 / 6.63; 7.610 / 6.63 | 98 of 99 |
| l08r23 walk_a 1-100 | 0.755 / 0.878 / 1.071 / 1.204 | 6.526 / 6.34; 6.515 / 6.34 | 77 of 99 |
| l10r01 walk_a 1-100 (pillars, 4 gates) | 0.988 / 1.019 / 1.088 / 1.388 | 8.491 / 8.87; 8.503 / 8.87 | 76 of 99 |

The replay matches the measured mean within 0.02 (it leaves out the interrupt inside the halt).

### Top routines (exclusive frames a tick; calls a tick, T a call)

| routine | walk | fight | traps_b1 | l10r01 | what it is |
|---|---|---|---|---|---|
| k_get_tile | 0.155 (32.4, 340) | 0.168 (36.4, 329) | 0.148 | 0.177 (31.7, 398) | SDLPoP get_tile: room / column / row normalised through the links by a loop on memory variables, then tbl_line, tile_base, k_tbl. Inclusive 0.24-0.29 |
| get_row_collision_data | 0.121 (3.0, 2,860) | 0.124 | 0.110 | 0.119 | one collision row, 3 a tick. **Inclusive 0.41**: ~9,600 T a row, ~2,000 T a column |
| k_tbl | 0.090 (145) | 0.112 (181) | 0.085 | 0.085 | A = (HL + A): 44 T + the call, 61 T a lookup; ~65 a tick from k_get_tile, 40 from check_collisions' loop, 28 from wall_type |
| tile_base | 0.054 (39, 98) | 0.068 (50) | 0.048 | 0.058 | the room's fg / bg address from a table |
| prandom | 0.050 (2.2, 1,634) | 0.028 (1.2) | 0.047 | 0.046 | the LCG (~850 T) and a 16-step division (~780 T). Called with 255 by the torches, potions and the guard |
| kid_tick (own) | 0.038 (2,723) | 0.038 | 0.038 | 0.038 | the controls' copies, the harness snapshot (KV_SNAP), the dispatch |
| move_coll_to_prev | 0.032 (2,292) | 0.032 | 0.029 | 0.030 | copies 20 bytes, then clears 60 by djnz loops |
| check_collisions | 0.025 (1,805) | 0.026 | 0.023 | 0.025 | the bump loop: 10 columns x 4 k_tbl calls |
| set_char_collision | 0.024 (2.0, 855) | 0.036 (3.0) | 0.025 | 0.024 | of it dir_entry 452 T (the image's height from the RAM disk) |
| wall_type + get_left / right_wall_xpos | 0.044 | 0.046 | 0.044 | 0.045 | wall_type twice a column, k_tbl, k_sext, 16-bit adds |
| get_tile_div_mod | 0.018 (8, 155) | 0.030 (14) | 0.017 | 0.017 | two k_tbl lookups |
| play_seq / far_seek | 0.015 / 0.008 | 0.031 / 0.012 | | | the sequence table (RAM disk): **0.02-0.04, not a lever** |
| check_chomped_kid | 0.015 (1,060) | 0.015 | 0.015 | 0.015 | 10 columns of flags |
| far_copy (overlay loads) | 0 | 0.021 | 0 | 0 | l05r24: **0.085** (28 events-overlay loads in 100 ticks) |

**Groups** (exclusive): tile lookups (k_get_tile, k_tbl, tile_base, get_tile_*, links_of ...) 0.35 walking / 0.44
fighting; collision (check_collisions, get_row_collision_data, the wall routines, move_coll_to_prev,
set_char_collision ...) 0.25 / 0.27; sequence 0.02 / 0.04; frame loading 0.03 / 0.06; prandom 0.05 / 0.03; **mul /
div helpers 0** (none runs in the logic). The guard (fight1): play_guard_frame 0.21 inclusive, tick_pre 0.12, the
trobs 0.07-0.09. Inclusive: check_collisions is **0.48 of the 0.92** walking, and 0.49 of the 1.20 in a fight.

**The overlay thrash (new):** a kid on a plate calls trigger_button every tick. Its stub loads the events overlay into
W1 unless W1 holds the gate or the door overlay. In a room whose draw uses W1 itself (ovl_frm for choppers and
spikes, ovl_btn for the button pictures), each such tick loads two overlays of ~1 KB (~21,400 T, 0.3 frames each):
the events overlay in the logic and the draw's overlay back. l05r24 walk_a: 43 trigger_button calls, 28 logic loads
and 30 ovl_frm loads in 100 ticks. fight1 60-160: 7 + 7 (ovl_btn).

### Why it is slow, and the trims (modelled per tick from each tick's profile, then the pacing replayed)

The new code's costs are hand counts of sketched code. They live in kidlogic.py TRIMS: a row walker costs 600 T a row
plus 280 T a column; the in-room k_get_tile saves 130 T a call.

| # | trim | why today is slow | logic saved: walk / fight / traps / busy (4 rooms) | **mean frames a tick after the floor**: walk / fight / traps / busy | resident bytes (main) | risk to tick-exactness | effort |
|---|---|---|---|---|---|---|---|
| A | **get_row_collision_data as a row walker**: resolve (room, row) once with k_get_tile, again only where the columns cross into the left or right room (as k_get_tile resolves them: row first when negative, columns, row 3 last); walk a pointer through fg; one 32-byte table a side by tile (the wall offset, the none case); the compares against CX_RCOLL / CX_LCOLL as running 16-bit differences (-14 a column); the last column's CURR_ROOM / TILE_COL / TILE_ROW / CURR_TILEPOS / CURR_TILE2 stored at the end | per column: k_get_tile twice (the second is the same call), wall_type twice, k_tbl, k_sext, 16-bit loads and stores through memory variables: ~2,000 T | -0.33 / -0.33 / -0.32 / -0.23..-0.36 | **-0.14 / -0.23 / -0.08 / -0.21..-0.31** | ~200 code + 64 table, against the old 170: **+~95** | medium: room 0 (wall), the room crossings, the state left behind. Exact by construction if those are kept; m4_test, the oracles and tests/m4_game.py check it | 2-3 days |
| A' | (A's first step alone: the second k_get_tile of each column dropped, the tile kept in a register) | the same call with the same inputs; get_left_wall_xpos changes no tile variable | -0.11 / -0.11 / -0.11 / -0.08..-0.13 | -0.05 / -0.08 / -0.03 / -0.07..-0.10 | ~0 | **none** (a pure function, unchanged state) | 1 hour |
| B | check_collisions' bump loop by pointers (HL / DE over CURR / PREV rooms and flags, no k_tbl) | 40 k_tbl calls and their setups a tick | -0.022 / -0.022 / -0.020 / -0.014..-0.021 | -0.010 / -0.022 / -0.007 / -0.011..-0.020 | ~0 (181 rewritten) | low | half a day |
| C | move_coll_to_prev: the 60-byte clear unrolled x2 (`ld (hl),a; inc l` twice a djnz; KV + 0x60..0xAF stays in one page) | 60 djnz iterations | -0.009 / -0.009 / -0.008 / -0.005..-0.008 (628 T a call, as built in part 21: 2,292 -> 1,664; first modelled as 1,000) | -0.004 / -0.007 / 0 / -0.005..-0.008 | +~10 (built: -23) | none | 1 hour |
| D | k_get_tile: an in-room path (0 <= column < 10, 0 <= row < 3, room != 0: row x 10 + column, the room's base, one read; the same variables stored) | the general loop of memory loads and tests for the common case | -0.013 / -0.019 / -0.012 / -0.010..-0.012 (after A; ~-0.07 without A) | -0.006 / -0.022 / 0 / -0.009..-0.013 | +~30 | low | half a day |
| E | prandom: when max + 1 is a power of two (255: the torches, potions, the guard), the result is SEED+2's byte AND max; no division | a 16-step restoring division for a mask | -0.021 / -0.012 / -0.020 / -0.010..-0.020 | -0.010 / -0.021 / -0.003 / -0.010..-0.020 | +~10 | none (the seed's update unchanged) | 1 hour |
| F | trigger_button resident (buttons.asm, 272 bytes, in main; the copies in the events, gate and door overlays go) | the W1 thrash above | 0 / -0.022 / 0 / **-0.088** (l05r24; 0 in the other three) | 0 / -0.020 / 0 / -0.088 in l05r24, **plus about as much in the draw** (ovl_frm / ovl_btn not reloaded; not modelled) | **+~255** (frees ~272 in three overlays) | low | 1 day |
| G | get_tile_div_mod: tile_mod_tbl / tile_div_tbl page-aligned, k_tbl inlined | two calls a lookup | -0.010 / -0.018 / -0.010 / -0.009..-0.010 | -0.004 / -0.021 / 0 / -0.008..-0.013 | ~0 (the tables placed) | none | half a day |
| | **A + B + C + D + E + F + G** | | -0.41 / -0.44 / -0.40 / -0.29..-0.48 | **-0.19 / -0.33 / -0.09 / -0.27..-0.48** (l05r24 with F) | **~+400** (~+145 without F) | | ~1.5 weeks |

Also looked at and not worth it: caching the collision rows across ticks (CX_LCOLL / RCOLL change every tick, and
after A a column's tile part is ~60 T: invalidating on every tile change would cost more); set_char_collision's image
lookup cached by OBJ_ID (~0.007); check_chomped_kid (~0.008); inlining the remaining k_tbl calls (~0.02 for 3 bytes a
site); the sequence table (0.02-0.04 in all); the harness snapshot in kid_tick (~0.005).

### The effective gain (the pacing replayed)

What a cut of X frames of logic every tick gives, as mean frames a tick:

| X | walk_level1 30-60 | fight1 60-160 | traps_b1 1-300 | l10r01 walk | l03r16 walk |
|---:|---:|---:|---:|---:|---:|
| 0.1 | -0.043 | -0.068 | -0.026 | | |
| 0.2 | -0.087 | -0.144 | -0.046 | -0.145 | -0.196 |
| 0.3 | -0.130 | -0.218 | -0.062 | -0.218 | -0.287 |
| 0.5 | -0.217 | -0.345 | -0.095 | | |

On a walking stretch the floor absorbs about half of a logic saving: 16 of 30 ticks do more than 4 frames of work. In
traps_b1 it absorbs three quarters (182 of 299 ticks sit at the floor). In fights and in the busy rooms (75-98 % of
ticks above the floor) nearly all of the saving shows. The medians barely move while walking (4.26 -> 4.15 with
everything); the p90 moves by -0.1..-0.5.

### Recommendation

1. **A' + C + E first** (an afternoon, ~20 bytes, exact by construction): walking -0.07, fight -0.11, the busy rooms
   -0.09..-0.13 frames a tick.
2. **A, the row walker** (2-3 days, ~+95 bytes, with D folded in, since A resolves its rooms through k_get_tile):
   the only large item. Walking -0.14 more than today in all (A replaces A'), fight -0.23, busy rooms -0.21..-0.31.
   Below the roadmap's rule of thumb (>= 0.2 a tick for < 250 bytes) while walking, above it in fights and the busy
   rooms.
3. **F** if the plate rooms matter: ~255 bytes of main for -0.1..-0.2 frames on the ticks the kid stands on a plate in
   a chopper, spike or button-picture room (l05r24: -0.088 in the logic alone). Measure the draw side when building.
4. B and G only as fill-ins in the same PR as A (-0.02 / -0.01).

The whole set is at most ~-0.2 walking and ~-0.3 in fights, so it does not change the ranking of section 6. It is
general (every tick, every size, no RAM-disk space), but smaller than one frame's worth of any drawing step. The
check for every step: tests/m4_test.py and tests/m4_game.py --every 1 against kidsim, plus the logic oracles on the
runners.

## Step 3 (the VRAM copy): measured and dropped (2026-11-08)

Status: **dropped by the user; nothing built.** Candidate 9 of "Speed roadmap (2026-11-08)" section 6, the copy of the
compose buffer into VRAM (blq_8 and the narrower widths), after part 20. The unfinished patch is kept locally, not in
the repo.

**POP / PUSH does not help on the MZ-800.** The GDG makes a VRAM write that comes within ~6.4 T of the previous one
wait 3-6 T (mz800emu models it from the GDG's HDL; docs/research/mz800-hardware.md already said that PUSH-to-VRAM tricks
lose). PUSH writes its two bytes 3 T apart, so the second always waits: ~18 T a byte with the POP, no better than LDI.
The ~15.6 T a byte of "The copy and the shadow write (bounds for candidate 9)" assumed no waits.

**The best found: a plane-major LDI copy in bands of 16 rows, for width 8 only** (one plane select per band and plane
instead of per row):

| room change (1 MB, one tick) | before | after |
|---|---:|---:|
| l01r01 (walk_level1 89) | 88.31 | 85.79 (-2.5) |
| l04r04 (palace, simple) | 72.89 | 70.38 (-2.5) |
| l10r01 (palace, pillars, 4 gates) | 95.84 | 93.14 (-2.7) |

-2.2..-2.7 frames a room change at all three sizes, ~-0.02 a walking tick, for **~680 bytes of main**. It also showed a
16-row strip of mixed planes for one frame during the room draw (before: one row): the band is copied plane by plane
while the beam passes. Widths 1-7 banded as well: ~-0.02 a tick more for ~420 bytes. Neither is worth its memory and the
visible strip, so the copy stays row-major (blq_8 and the narrow paths unchanged).

## M8a part 21: kid logic trims (2026-11-08)

Status: **built.** Trims A', C and E of "Kid logic: measured (2026-11-08)" (recommendation 1): three small changes to
the logic's code with the same results, tick-exact against kidsim (and so SDLPoP) by construction and by the tests.

### What changed

1. **A': get_row_collision_data reads each column's tile once** (kid.asm). SDLPoP calls get_tile twice a column (for
   the left and the right wall); the port did too, with the same inputs (K_ROOM, the column, the row: pushed and
   popped around get_left_wall_xpos). The tile is now kept in C across get_left_wall_xpos and handed to
   get_right_wall_xpos. ~-1,250 T a row (three rows a tick).
2. **C: move_coll_to_prev's 60-byte clear in one loop** (kid.asm): the three rows (CURR, BELOW, ABOVE: rooms 0xff,
   flags 0) are contiguous, so one loop of three rows, two bytes a `djnz` by `ld (hl), a; inc l` (the 60 bytes stay
   in one 256-byte page: KV + 116..175; two `.error` guards keep the layout). 2,290 -> 1,662 T a call.
3. **E: prandom without the division when max + 1 is a power of two** (room.asm pr_slow): the result is the seed's
   third byte AND max (max 255: the torches, the potions' bubbles, the guard; also 0, 1, 3, ..., 127). The seed's update
   is unchanged. ~1,636 -> ~925 T a call for those maxes; the others keep the division.

Resident (main e334925 -> this):

| area | before | after | |
|---|---|---|---:|
| main code (end_of_code) | 0x76DA, 1,318 free | 0x76C9, **1,335 free** | **-17** (A' -6, C -23, E +12) |
| low code, block 2, low RAM, overlays, RAM disk | | unchanged | 0 |

### Why it is exact

- **A'.** k_get_tile is a function of its inputs (A = room, C = column, B = row) and of the level in memory (fg and the
  links): it writes CURR_ROOM, TILE_COL, TILE_ROW, CURR_TILEPOS and CURR_TILE2 and returns CURR_TILE2 in A; links_of
  and tile_base only read. Between the two calls only get_left_wall_xpos runs: wall_type, k_tbl, k_sext and an add
  with COLL_TLX. It writes no memory (so neither the inputs, K_ROOM and the level, nor the five variables change) and
  leaves BC alone, so the second call would rewrite the same five variables with the same values and return the same
  A. The registers the old second call left behind differ only in C at the routine's end, and its one caller
  (check_collisions) loads C before it reads it.
- **C.** The same 60 bytes get the same values (CURR_ROOMS .. ABOVE_FLAGS + 9, contiguous by the equates); the caller
  uses none of the registers or flags afterwards (it reloads A).
- **E.** For every max with (max + 1) & max = 0 (mod 256), the old 16-step division (`add hl, hl; rla; cp c; sub c`,
  c = max + 1, so 0 for 255) leaves exactly the low bits of the seed's high word. Checked exhaustively by an
  instruction-level model of that loop over all 65,536 high words and the nine maxes 0, 1, 3, 7, 15, 31, 63, 127, 255
  (589,824 cases: the division equals both `hw & max` and SDLPoP's `hw % (max + 1)`). The test that picks the path,
  (max + 1) & max, is the one the table path already used. The seed's sequence is untouched (the update runs before),
  and no caller of a power-of-two max reads the flags after the call (they all store or test A first).

### The logic (tools/kidlogic.py profile; 1 MB, no waits; main e334925 + the tool / this)

| stretch | logic mean (frames a tick) | frames a tick, mean (measured) | median | p90 | ticks with work > 4 |
|---|---|---|---|---|---|
| walk_level1 30-60 | 0.918 / **0.776** (-0.142) | 4.694 / **4.590** (-0.10) | 4.36 / 4.26 | 6.96 / 6.75 | 16 / 14 of 30 |
| fight1 60-160 | 1.203 / **1.070** (-0.133) | 5.926 / **5.876** (-0.05) | 5.02 / 4.98 | 9.27 / 9.18 | 75 / 72 of 100 |
| traps_b1 1-300 | 0.886 / **0.746** (-0.140) | 4.635 / **4.598** (-0.04) | 3.99 / 3.99 | 5.00 / 4.99 | 91 / 80 of 299 |
| l03r16 walk_a 1-100 (3 choppers) | 0.865 / **0.756** (-0.109) | 8.754 / **8.663** (-0.09) | 7.97 / 7.97 | 12.99 / 12.99 | 95 / 95 of 99 |
| l05r24 walk_a 1-100 (palace, busy) | 1.028 / **0.897** (-0.131) | 7.612 / **7.436** (-0.18) | 6.63 / 6.59 | 11.94 / 11.61 | 98 / 98 of 99 |
| l08r23 walk_a 1-100 | 0.755 / **0.655** (-0.100) | 6.526 / **6.395** (-0.13) | 6.34 / 6.11 | 9.98 / 9.95 | 77 / 75 of 99 |
| l10r01 walk_a 1-100 (pillars, 4 gates) | 0.988 / **0.822** (-0.166) | 8.491 / **8.359** (-0.13) | 8.87 / 8.87 | 14.67 / 14.64 | 76 / 69 of 99 |

The logic gains what the model said (A' + C + E: -0.140 modelled walking with C at its measured 628 T a call, -0.142 measured). Per routine (walking):
k_get_tile 32.4 -> 18.4 calls a tick (0.243 -> 0.138 inclusive), get_row_collision_data 0.406 -> 0.293 inclusive,
move_coll_to_prev 2,292 -> 1,664 T, prandom 1,634 -> 978 T a call (the torches' 255 calls ~925 T). The frames a tick
move by less where ticks sit at the 4-frame floor (walking, traps) and by about the logic's saving where the work is
above it (l05r24, l08r23, l10r01). The fight's -0.05 is below the replay's estimate (-0.09): its time also depends on
where the copies meet the beam.

### perfcheck (one run per size; main e334925's own runs (equal to the baselines but gate 4.10); baselines lowered where beaten, in this commit)

| Stretch | 512 KB main / new | 1 MB main / new | 16 MB main / new |
|---|---|---|---|
| normal tick (walkthrough 30-60) | 4.93 / **4.91** | 4.69 / **4.59** | 4.61 / **4.52** |
| level door step (walkthrough 203-207) | 9.14 / **8.98** | 8.47 / **8.23** | 8.47 / **8.23** |
| room change (walkthrough 89) | 88.31 / **88.27** | 88.31 / **88.25** | 87.48 / **87.32** |
| walkthrough 190-260 | 6.21 / **6.12** | 6.00 / **5.90** | 5.63 / **5.56** |
| gate (gate_push 200-260) | 4.10 / **4.08** | 4.10 / **4.08** | 4.10 / **4.08** |
| traps (traps_b1 0-300) | 5.18 / **5.12** | 4.90 / **4.87** | 4.86 / **4.83** |
| fight (fight1 60-160, guard on) | 6.75 / **6.64** | 5.92 / **5.87** | 5.66 / **5.62** |

Every stretch gains on every size: -0.02..-0.24 frames a tick (the level door step most: its ticks sit just above the
floor).

### Same pixels, same logic

tests/m4_test.py (the Z80 logic against kidsim: kid, guard, state and sound lines every tick) on all 74 scripts of
tests/m4_scripts, m6_scripts, m5_scripts and m7_scripts: 0 differing ticks. tests/m4_game.py --every 1 (the state with
the level checksum, and VRAM every tick) at 1 MB on 31 scripts (walk_level1, gate_push, run_rooms, traps_b1, btn_bars,
chomper, frm_button, frm_spike_btn, fight1, fight_killpush, fight_spikes, fight_chomper, fight_follow, fight_leave,
level2_fight, level4_mirror, level6_shadow_exit, level12_exit_level13, level13_exit, level3_checkpoint,
feather_fall_guard, level5_shadow_potion, potion_upside_down and seven busy-room scenes of busyrooms.py `find
--worst`: l03r16, l05r24, l08r23, l04r18, l10r01, l10r10, l02r18 walk_a): 0 state diffs, 0 differing pixels; at 512
KB and 16 MB on walk_level1, fight1, fight_killpush, traps_b1, level6_shadow_exit, level12_exit_level13 and the l03r16,
l05r24, l10r01 scenes: 0. tests/m3_test.py levels 1 and 4: 0 differing pixels (the wall patterns' seeds are all below
64, so they take PR_TAB, not the generator). E's exhaustive check: 589,824 cases equal. `make ci-build`, `make
cheats`, `make pace`. The full regression on the runners: see the PR.

## M8a part 23: collision rows (2026-11-09)

Status: **built.** Trim A of "Kid logic: measured (2026-11-08)" (recommendation 2: get_row_collision_data as a row
walker) with D folded in, and B and G as fill-ins: the same results byte for byte, tick-exact against kidsim (and so
SDLPoP) by construction, by a differential harness of the old and the new code, and by the tests.

### What changed

1. **A: get_row_collision_data walks the row** (kid.asm). SDLPoP calls get_tile for each column of the row
   (LEFT_CHK..RIGHT_CHK, 4-7 columns, three rows a tick), and the port did, through k_get_tile's normalising loop.
   Now k_get_tile resolves the row's first column, and again only where TILE_COL would reach 10. Between those, the
   next column's k_get_tile (Char.room, column + 1, row) would only add one to TILE_COL and CURR_TILEPOS and read the
   next fg byte (see "Why it is exact"), so a pointer walks fg (room 0: a 10-byte run of T_WALL, CURR_TILEPOS 0). The
   two compares are running 16-bit differences in the alternate registers: HL' = coll_tile_left_xpos - CX_RCOLL - 1
   and DE' = coll_tile_left_xpos - CX_LCOLL - 1, both + 14 a column; a column's tile gives its wall type
   (wall_type_tbl, page-safe) and the type two offsets (grc_wd: wall_dist_from_left + 1 and 13 -
   wall_dist_from_right, both 0..13, so the adds are zero-extended): the left flag is the sign of HL' + the first,
   the right flag the inverted sign of DE' + the second. A column without a wall takes the row's constant flags
   (0x00FF < CX_RCOLL, 0 > CX_LCOLL). The flags are stored as the walk goes; the rooms array is filled per room
   segment (grc_fill). At the end TILE_COL, CURR_TILEPOS, CURR_TILE2 (the last column's; CURR_ROOM and TILE_ROW are
   the last k_get_tile's) and COLL_TLX (= HL' + CX_RCOLL + 1) are stored, as the old code left them. ~2,500 T a row
   inclusive (walking, ~5 columns), was ~6,950 after part 21's A' (~9,600 before).
2. **D: k_get_tile's in-room path** (kid.asm): a column 0..9 and a row 0..2 skip the normalising loop and tbl_line
   (row * 10 + column by adds), then the same tile_base / k_tbl tail, so the same stores, registers and flags. ~340 ->
   ~250 T an in-room call.
3. **B: check_collisions' bump loop by pointers** (kid.asm): HL / DE over the current and the previous row (the flags
   ten bytes on, all in KV's page: an `.error` guard), instead of four k_tbl calls a column. The same columns in the
   same order (9 down to 0), so BUMP_L / BUMP_R get the same values.
4. **G: get_tile_div_mod reads its tables by page** (kid.asm): tile_div_tbl / tile_mod_tbl page-aligned (0xC400 /
   0xC500), `ld h, page; ld a, (hl)` instead of two k_tbl calls. The tables are aligned without moving them relative
   to each other: get_row_collision_data's data and variables (grc_wd and four bytes, exactly 12) moved to the head
   of block 2 (src/m4/collpad.inc, game.asm and m4test.asm), which shifts tables.inc by the 12 bytes it needed.
   (The first try put the two tables first in tables.inc. The differential harness below caught it: x_bump[LEFT_CHK
   + 5] reads past x_bump's 20 bytes when LEFT_CHK is below -5 or above 14, e.g. CX_LCOLL 0, and those bytes changed.
   With the padding, x_bump's 256-byte window holds the same bytes as before: y_land, then tile_div_tbl.)

Resident (main d7dd935 -> this):

| area | before | after | |
|---|---|---|---:|
| main code (end_of_code) | 0x76C9, 1,335 free | 0x774B, **1,205 free** | **+130** (A +114, D +33, B -7, G -10) |
| block 2 (block2_end) | 0xEBE6, 26 free | 0xEBF2, **14 free** | **+12** (A's data, the padding for G) |
| low code, low RAM, overlays, RAM disk | | unchanged | 0 |

A came out larger than the ~+95 of the model (the room segments' fill, the crossing path and room 0's wall run).

### Why it is exact

- **A, the tile part.** k_get_tile (Char.room, c, r) normalises in a fixed order: while the row is negative, + 3 and
  the room above; then a negative column + 10 and the room on the left, a column >= 10 - 10 and the room on the
  right (back to the row test after each); last a row >= 3 - 3 and the room below. Room 0 stays room 0 (the values
  are still normalised). For columns c and c + 1 with the same floor(c / 10), the moves are the same in the same
  order, so the result is the same room and row with TILE_COL one more, CURR_TILEPOS one more (room 0: 0) and the
  next fg byte (room 0: T_WALL). When TILE_COL would be 10 the walker calls k_get_tile with (Char.room, the column,
  the row) itself: a room to the right of the room below need not be the room below the room to the right. The
  level does not change during a row. So every column reads the tile the old code read, and the variables left
  after the last column are the same.
- **A, the flags.** The old code computed left = COLL_TLX + sext(wall_dist_from_left) (or 0x00FF) and tested the
  sign of left - CX_RCOLL by `sbc hl, de`, and right = COLL_TLX + 13 - wall_dist_from_right (or 0) and the sign of
  CX_LCOLL - right. Modulo 2^16, left - CX_RCOLL = (COLL_TLX - CX_RCOLL - 1) + (dl + 1), and dl + 1 is 0..11 (dl = -1
  for the chomper), so the walker's zero-extended add gives the same 16 bits; (COLL_TLX - CX_LCOLL - 1) + r = -(CX_LCOLL
  - right) - 1 = NOT (CX_LCOLL - right), so its sign is the old sign inverted. Equal for every input, overflow
  included. The no-wall flags use the old constants (the high byte of 0x00FF - CX_RCOLL is -H). The flags and the
  rooms go to [TILE_COL] as before; with more than ten columns a later segment overwrites an earlier one's entries
  in the same order as before (the fill runs at each segment's end).
- **A, what is not written any more.** The old code's scratch K_TMP (the last column's flags), K_TMPW and K_TMPW2 (its
  wall x): K_TMPW / K_TMPW2 have no other reader anywhere; every other routine that reads K_TMP writes it first
  (checked at each reader). grc_row, grc_col, grc_rooms, grc_flags were the routine's own. The alternate registers
  and AF' are changed now (nothing keeps a value in them across a call: the ISR saves only AF and HL, gfx.asm and
  frames.asm use them inside a routine).
- **D.** In range the old loop changed nothing (no links_of, so BC is kept) and kgt_done computed tbl_line[row] +
  column = row * 10 + column; then the same tile_base and k_tbl, so HL, DE, A and the flags are the same; room 0
  leaves HL and DE as they came, as before.
- **B.** Previous room = current room and not 0xff is the old test (current not 0xff, then equal) in the other order;
  the flag tests are unchanged. No caller reads the registers check_collisions leaves (check_bumped loads its own).
- **G.** HL leaves pointing at the tile_div_tbl entry as before; DE is kept. The flags differ (no k_tbl `add`); every
  caller (kid.asm, guard.asm, objects.asm, overlay.asm, genter.asm) stores, adds or tests A first.

**The differential harness** (tools/collrows_diff.py): main's m4test and this one in two emulators, the same level
loaded, a driver loop at 0x0E00 that copies a KV image in, sets the registers, calls the routine and copies KV and
the registers out, 30 cases a batch. check_collisions with random inputs (Char's room 1-24, row -1..3, action, CX_LCOLL
/ CX_RCOLL anywhere in -300..600 or at a wall's x +-1, the previous rows, PREV_COLL_ROW and the tile variables
random): all 256 bytes of KV compared but K_TMP, K_TMPW, K_TMPW2. k_get_tile with room 0-24, column -15..24, row
-5..7: KV and AF, BC, DE, HL compared. Its sensitivity: a build with one grc_wd offset off by one differs in 12 of
300 cases of level 1.

### The logic (tools/kidlogic.py profile; 1 MB, no waits; main d7dd935 / this)

| stretch | logic mean (frames a tick) | frames a tick, mean (measured) | median | p90 | ticks at the floor |
|---|---|---|---|---|---|
| walk_level1 30-60 | 0.776 / **0.543** (-0.233) | 4.590 / **4.515** (-0.08) | 4.26 / 4.14 | 6.75 / 6.49 | 13 / 14 of 30 |
| fight1 60-160 | 1.070 / **0.804** (-0.266) | 5.876 / **5.696** (-0.18) | 4.98 / 4.76 | 9.18 / 8.94 | 25 / 26 of 100 |
| traps_b1 1-300 | 0.747 / **0.542** (-0.205) | 4.598 / **4.539** (-0.06) | 3.99 / 3.99 | 4.99 / 4.97 | 193 / 197 of 299 |
| l03r16 walk_a 1-100 (3 choppers) | 0.756 / **0.582** (-0.174) | 8.663 / **8.458** (-0.21) | 7.97 / 7.92 | 12.99 / 12.96 | 2 / 4 of 99 |
| l05r24 walk_a 1-100 (palace, busy) | 0.897 / **0.688** (-0.209) | 7.441 / **7.221** (-0.22) | 6.59 / 6.55 | 11.94 / 11.50 | 2 / 6 of 99 |
| l08r23 walk_a 1-100 | 0.655 / **0.505** (-0.150) | 6.395 / **6.253** (-0.14) | 6.11 / 5.98 | 9.95 / 9.95 | 22 / 23 of 99 |
| l10r01 walk_a 1-100 (pillars, 4 gates) | 0.822 / **0.601** (-0.221) | 8.359 / **8.170** (-0.19) | 8.48 / 8.02 | 14.61 / 14.38 | 25 / 26 of 99 |

The logic gains -0.15..-0.27 frames a tick, a little more than the model's A + B + D + G after part 21 (walking -0.25
modelled with A at 600 T a row + 280 a column; measured -0.233). After the 4-frame floor: walking -0.08, traps -0.06
(most of their ticks sit at the floor), the fight and the busy rooms -0.14..-0.22 (nearly all of the saving). Per
routine (walking): get_row_collision_data 0.293 -> 0.105 inclusive (1,708 T a row exclusive), check_collisions
0.362 -> 0.155 inclusive, k_get_tile 18.4 -> 7.4 calls a tick (339 -> 251 T a call), k_tbl 117 -> 26 calls,
get_tile_div_mod 155 -> 85 T a call. A alone (first build, walking): 0.776 -> 0.594; A + B + D 0.560; with G 0.543.

### perfcheck (one run per size; main d7dd935 = the baselines; baselines lowered where beaten, in this commit)

| Stretch | 512 KB main / new | 1 MB main / new | 16 MB main / new |
|---|---|---|---|
| normal tick (walkthrough 30-60) | 4.91 / **4.73** | 4.59 / **4.51** | 4.52 / **4.44** |
| level door step (walkthrough 203-207) | 8.98 / **8.73** | 8.23 / **8.00** | 8.23 / **8.00** |
| room change (walkthrough 89) | 88.27 / **87.93** | 88.25 / 88.25 | 87.32 / **87.27** |
| walkthrough 190-260 | 6.12 / **5.95** | 5.90 / **5.79** | 5.56 / **5.45** |
| gate (gate_push 200-260) | 4.08 / **4.07** | 4.08 / **4.07** | 4.08 / **4.07** |
| traps (traps_b1 0-300) | 5.12 / **5.00** | 4.87 / **4.81** | 4.83 / **4.78** |
| fight (fight1 60-160, guard on) | 6.64 / **6.41** | 5.87 / **5.70** | 5.62 / **5.48** |

(Two runs of the final build; the second differed by at most 0.01.)

### Same pixels, same logic

The differential harness (tools/collrows_diff.py, main's m4test against this one): 84,000 cases, 6,000 a level for
levels 1-14 (42,000 of check_collisions, 42,000 of k_get_tile): 0 differing. tests/m4_test.py (the Z80 logic against
kidsim: kid, guard, state and sound lines every tick) on all 74 scripts of tests/m4_scripts, m6_scripts, m5_scripts
and m7_scripts: 0 differing ticks. tests/m4_game.py --every 1 (the state with the level checksum, and VRAM every
tick) at 1 MB on 30 scripts (walk_level1, run_rooms, jumps_climbs, random1, traps_b1, traps_b9, gate_push, run_fall,
fight1, fight_killpush, fight_chomper, fight_follow, fight_spikes, level2_drop, level2_fight, level3_skeleton,
level4_mirror, level6_shadow_exit, level12_shadow_merge, level12_exit_level13, level13_exit, level14_end,
feather_fall_guard and the busy-room scenes l03r16, l05r24, l08r23, l10r01, l04r18, l10r10, l02r18 walk_a): 0 state
diffs, 0 differing pixels; at 512 KB on walk_level1, fight_killpush, traps_b1, l05r24 and at 16 MB on fight1,
level12_shadow_merge, level6_shadow_exit, l10r01: 0. tables.inc and the room renderer are unchanged (m3test's
binary does not include kid.asm). `make ci-build`, `make cheats`, `make pace`. The full regression on the runners:
see the PR.

## M8a part 24: gates at pillars and the closed band (2026-11-09)

Status: **built.** Candidates G1 and G3 of "Speed roadmap (2026-11-08)" section 8. A gate whose bars tile is a pillar
now takes part 14's column shift too: the palace pillar (G1) was on the old path, and the dungeon pillar's base is no
longer laid again. A closed gate's contact band (G3) is laid into the step's own compose rect. trigger_button became
resident; that made the room in the gate overlay. G2 and G4 (drops, steps to or from 47) are unchanged.

### Where a step's time went (measure first; tools/optione.py profile / diff, walk_gate against walk_b, 1 MB)

- **G3** (l01r05 ticks 5, 6, 12, 13), against an open step (ticks 20, 21):
  - the step itself costs 2.6 frames against 1.2;
  - the band's run_rect 1.24-1.31 (5 pieces: lay_piece16 0.80, scans and the fill ~0.3);
  - the object pass restores the merged chunk, +0.45 (the band's rect is not the kept SPRBUF_B rect);
  - a second shadow write, +0.19, and the copy, +0.1.
- **G1** (l11r02, a-b work 4.2-5.5 a step):
  - the bars tile regenerated, 1.1;
  - run_rect 3.1-3.4 (12 pieces);
  - the shadow write, 0.6;
  - the object pass, +1.3 (the kid, the pillar's fore piece).
- **A cache of the band's pictures** (a picture per position, kept per room visit) was simulated with kidsim over the
  m4 / m5 / m6 scripts and the busy scenes: 5-7 % hits. Gates do not close and open again within one visit, so the
  cache was not built.

### What changed

1. **G1, the palace pillar** (colshift.asm cs_pil). Its base 92, laid after the bars, covers pixels 16-19 of the bars'
   column (byte 2, bits 0-3) in rows GT + 9..GT + 46, and more of rows GT..GT + 8. So the step is the plain shift, then:
   - rows GT..GT + 9 get the bars' records (CH_ENV 50..59 of the bars tile's slice) and 92 laid again (cs_layr);
   - rows GT + 10..S1 - 1 take bits 0-3 of byte 2 from the old picture.

   The palace pillar left cs_okmap's exceptions.
2. **The dungeon pillar.** Its base covers bytes 1-2 of the column whole in rows GT..S1 - 1. Those bytes are now read
   again from the shadow, instead of 92 being laid again over the moved rows.
3. **G3, the band in place.** room.asm run_rect is split:
   - rr_lays: the fill and the back and mid ops;
   - rr_layc: the same, with the tile columns set from the rect, as dr_run's.

   gate_step lays the band (rows MY - 13..MY - min - 1) into SPRBUF_B below S1. One cs_put then writes, dirties and
   keeps the whole rect, so the object pass composes over it without a restore. While min(p) < 4 the rect would pass
   SPRBUF_B's 64 rows (T0 = GT - 9 to MY - min), so those steps keep the second rect (dr_run).
4. **trigger_button resident** (buttons.asm in main; its copies in the gate, door and events overlays and the stub
   are gone). This is the planned plate-thrash item: a plate pressed while the frames or button overlay held W1
   loaded the events overlay every tick.
5. **cs_scan in main** (src/m4/csres.asm, with its 7 bytes of variables): both the gate and the door overlay use it.

Tried and dropped:

- **A faster palace head**: the head copied from the compose 8 rows lower (the bars are slices there while min(p) <=
  28), with a mask table and in-place merges. It was exact by tools/movecheck.py and ~0.25 a step faster on those
  steps, but it needed ~120 bytes more of main for the helpers it pushed out of the overlay.
- **A palace band cut to 3 rows** (rows MY - 13..MY - 11 for a floor or torch bars tile). It is exact on the Python
  reference's pictures, but on the Z80 the shifted row MY - 10 differed (l05r08, l10r01, gate_push): the shadow
  differs from the reference under a fore piece there. Not built.

### Memory (main 0312bd3 / this)

| area | before | after |
|---|---|---|
| main (end_of_code) | 0x774B, 1,205 free | 0x78E1, **799 free** (+406: trigger_button 251, cs_scan + variables 123, rr_layc and the run_rect split ~30) |
| low code, block 2, low RAM, RAM disk | | unchanged (the door overlay's image in page 6 shrank) |
| gate overlay (W1) | 1,014 (10 free) | **924** (100 free): the trigger_button copy out (-272), cs_pil + cs_layr in (~+160), the band's lay (+46) |
| door overlay | 868 | 471 |
| events overlay | 1,009 | 737 |

### Per gate-step kind (tools/reeval.py gates; 1 MB; a - b on walk_gate's ticks with one step; main 0312bd3 / this)

| kind (share of the 1,182 visible steps) | ticks | a-b median | a-b mean |
|---|---:|---|---|
| open (39 %) | 190 | 1.68 / 1.68 | 1.64 / 1.64 |
| **G3** closed band (15 %) | 79 | 3.69 / **3.18** | 3.72 / **3.29** |
| open at a dungeon pillar (13 %) | 91 | 2.47 / **2.25** | 2.40 / **2.22** |
| **G1** palace pillar (13 %) | 49 | 5.28 / **3.38** | 5.01 / **3.70** |
| regen (8 %) | 39 | 3.08 / 3.20 | 3.46 / **3.17** |
| **G3** at a dungeon pillar (5 %) | 41 | 4.87 / **3.81** | 4.93 / **4.04** |
| regen at a dungeon pillar (3 %) | 19 | 3.88 / **3.62** | 4.30 / **3.90** |
| G2 drop (2.4 %) / G4 to or from 47 (1.6 %) | 19 / 6 | 6.81 / 6.71; 7.07 / 7.07 | 6.97 / 6.89; 5.31 / 5.31 |
| button hit / B1 miss | 32 / 12 | 1.39 / **1.19**; 5.13 / **4.56** | 1.69 / **1.39**; 5.64 / **5.28** |

- G1 gains -1.3 a step, not the estimated -3.5. The old path's own work was smaller than its 6.06 a-b suggested;
  the object pass is unchanged.
- G3 gains -0.43 a step, -0.89 at a dungeon pillar; -0.55 over both kinds. The steps with min(p) < 4 (4 of the 11
  kinds) gain nothing.
- Over a game (the re-evaluation's ~1,700 G3 and ~700 G1 steps): ~-930 and ~-910 frames, plus the pillar steps.
- The buttons gain from trigger_button: no events overlay loaded in a tick that already loads the button overlay.

### The busy rooms (tools/busyrooms.py measure; 1 MB; frames a tick median / p90, and the mean work; main / this)

| scene | median | p90 | mean work |
|---|---|---|---|
| l10r01 walk (4 gates, one at a palace pillar) | 8.92 / **7.93** | 14.38 / **12.67** | 8.29 / **7.43** |
| l10r01 stand | 3.99 / 3.99 | 13.33 / **11.57** | 6.81 / **6.04** |
| l11r02 walk (palace pillar gates) | 6.30 / **5.01** | 9.26 / **8.16** | 5.81 / **5.11** |
| l05r08 walk | 8.93 / **7.98** | 11.96 / 11.84 | 8.22 / 8.13 |
| l09r01 walk (a dungeon pillar) | 8.07 / **7.44** | 13.51 / **12.98** | 8.39 / **8.02** |
| l09r22 walk | 7.28 / **6.54** | 11.43 / 11.63 | 7.88 / **7.49** |
| l07r07 walk (dungeon pillars) | 6.96 / 6.91 | 9.97 / **8.99** | 7.38 / **7.05** |
| l02r18 walk | 8.29 / **7.90** | 12.97 / **12.23** | 8.68 / **8.38** |
| l10r10 stand | 6.46 / **5.98** | 10.55 / **9.92** | 6.21 / **5.92** |
| l08r23 walk (choppers, a spike: no gate) | unchanged | | |

**trigger_button alone, l05r24** (choppers, a potion, plates; no visible gate step in the scene):

- walk: 6.59 / 6.50 median, 11.50 / 10.92 p90, mean work 7.26 / 7.09;
- stand (the kid on a plate): 7.32 / 6.58 median, 11.42 / 10.84 p90, mean work 6.88 / **6.53** (-0.35 a tick).

### perfcheck (one run per size; main 0312bd3 = the baselines; lowered where beaten, in this commit)

| Stretch | 512 KB main / new | 1 MB main / new | 16 MB main / new |
|---|---|---|---|
| normal tick (walkthrough 30-60) | 4.73 / 4.73 | 4.51 / 4.51 | 4.44 / 4.44 |
| level door step (walkthrough 203-207) | 8.73 / 8.74 | 8.00 / **7.90** | 8.00 / **7.90** |
| room change (walkthrough 89) | 87.93 / 87.94 | 88.25 / 88.26 | 87.27 / **87.26** |
| walkthrough 190-260 | 5.95 / 5.93-5.95 | 5.79 / **5.77** | 5.45 / **5.42** |
| gate (gate_push 200-260) | 4.07 / **4.04** | 4.07 / **4.04** | 4.07 / **4.04** |
| traps (traps_b1 0-300) | 5.00 / 5.00 | 4.81 / **4.80** | 4.78 / 4.78 |
| fight (fight1 60-160, guard on) | 6.41 / **6.35** | 5.70 / **5.63** | 5.48 / **5.42** |

The level door step loads no events overlay any more (the kid stands on the exit's plate). The fight's guard stands
on a closer.

### Same pixels, same logic

- **tools/movecheck.py gates** models the new rules: every pillar gate (both kinds) and the band. 8,280 steps of
  every gate of levels 1-14 on every screen that shows it, every one-row step both ways with both positions <= 46:
  0 differ. It was 7,452 before; the palace pillar gates are now in. Doors, buttons, chompers and the other checks:
  0 differ.
- **tests/m4_game.py --every 1** at 512 KB, 1 MB and 16 MB, 0 state diffs and 0 differing pixels on each of:
  - gate_push, btn_bars, frm_button, frm_spike_btn, walk_level1, fight1;
  - l04_open_a, l04_drop_a, l02_open_a, l07_drop_a;
  - the busy scenes l10r01, l11r02, l07r07, l05r08, l02r18, l10r10 (walk_a) and l05r24 (stand_a).
  At 1 MB also l04r18, l05r07, l01r05, l07r19, l09r01, l09r09, l09r22 walk_a and l10r01, l11r02, l05r08, l07r07
  stand_a.
- **tests/m4_test.py** (gate_push, walk_level1, traps_b1, btn_bars, fight1): 0 differing.
- `make ci-build`, `make cheats`, `make pace`, `make m3`. The full regression on the runners: see the PR.

A fault found on the way: the palace head's lay ran with the compose rect of the closing step's one-row shadow read
(CRX / CRW of byte 2), and laid nothing (l10r01 walk_a tick 109). tools/movecheck.py cannot see this, since it models
the pixels, not the registers; the emulator test did. The rect is now set before the lay.

## M8a part 25: choppers and spikes, lazy shadow and direct copy (2026-11-09)

Status: **built.** Steps 3 and 4 of "Option E: measured" section 7 (the speed roadmap's candidates 4 and 5).
- **The lazy shadow:** a chopper's or spike's step whose picture is in its slot writes nothing into the shadow.
- **The complete pictures:** a chopper's rect with nobody in it is copied from a RAM-disk slot straight into VRAM.

Cached buttons keep their shadow write (below).

### Where a step's time went (measure first; tools/optione.py profile / diff, 1 MB, main 132af94)

- **A chopper hit with nobody in its rect** (l08r23 walk_chomper tick 30, l03r16 ticks 30 / 32) costs ~3.2 frames of
  work:
  - the redraw 1.28: the slot read ~0.42, cs_put's shadow write 0.70, the patches and the stub ~0.15;
  - the chunk +1.5: the fore pieces 0.62-1.05, and people_chunk +0.65 although the kid is not in the chunk (pc_draw
    runs spr_draw clipped to nothing, lmx_ent x 4);
  - the copy 0.47, the wait ~0.
- **Two hits in one tick** cost 6.6-7.7: the second one's chunk restores and waits.
- **A spike hit** (l07r19 walk_spike ticks 82, 83) costs ~1.9-2.4: the redraw 0.77 (read 0.28, shadow write 0.38), the
  chunk +1.25-1.33, the copy 0.27. A miss's redraw is 2.7-2.8 (dr_run).
- **In the busy scenes** (busyrooms.py measure, a - b on the walk_chomper ticks with one picture change), a chopper step
  costs a median 2.7-3.0, a mean 3.0-3.4 (the misses after each restart included). The steps that regenerate (2 of 5)
  cost +0.7.

### What changed

1. **The lazy shadow** (src/m4/frmlow.asm, frmlow2.asm lc_step). A hit (the picture's slot valid) no longer reads the
   slot into SPRBUF_B and no longer calls cs_put. Instead:
   - the shadow's rect is marked stale (FE_ST), and the slot's place is kept in the object's entry;
   - the rect goes on the dirty list (dirty_hook, without the kept picture);
   - the slot holds the bytes the shadow should hold (fix A: dr_run wrote them).

   Every reader and writer of the shadow follows it:
   - **restore_shadow** (gfx.asm):
     - a compose rect wholly inside a stale rect is read from the slot alone (rs_pre: no shadow read);
     - a compose rect that meets one gets those rows from the slot after the shadow's read (rs_post).
     - cs_get, which jumps into restore_shadow, follows too.
   - **shadow_write** (gfx.asm sw_pre):
     - a write that covers a stale rect clears its mark;
     - a write that only touches one first writes the slot back (lc_wb: the slot into COMPOSE_A by lc_rd, then
       shadow_write's body).
   - **a hit** first runs sw_pre over its own rect, so stale rects never overlap. A spike's rect reaches into its
     right neighbour's column, and a chopper may stand there.
   - **a room draw**: the room overlay clears FRM_TAB before it (frm_clr), and frm_reset clears it again after.
2. **The complete pictures** (frmlow2.asm lc_chunk, lc_save, lc_direct). obj_chunk asks lc_chunk first.
   - A chunk that is exactly a chopper's rect, with nothing else in it, is the picture plus the fore pieces. "Nothing
     else" is tc_try's rule: no overlay op, no falling floor, no character's rect (this tick's or the last), and here
     also no registered torch flame (it animates on its own).
   - Such a chunk depends on the picture only. Its first composition is written to the picture's complete slot,
     row-major (a row's four planes one after the other).
   - Later such chunks go from that slot straight into VRAM (lc_direct, timed against the beam: below). There is no
     restore, no people pass, no fore pieces, no compose buffer and no pending chunk.
   - frm_drop drops a complete picture with its background (FE_CMASK with FE_MASK). The object's own step keeps both.
   - The slots:
     - 16 MB: every chopper picture, at its slot + 0x6000 in page 62.
     - 512 KB and 1 MB: a pool of 4 x 960 bytes in page 6 0x16C0-0x25BF (free since part 17), for the first chopper
       to step after a room draw (its pictures 0-3).
   - **Spikes get no complete pictures.** On the trap scenes (tools/trapscenes.py) a spike's chunk had the kid in it
     on all but 1 of ~100 steps, so keeping the pictures (648 bytes each) only cost time: +0.08 a step at 16 MB in a
     first build. A spike step has the lazy shadow only.
3. **Cached buttons** keep their shadow write. A button's picture is composed in SPRBUF_B by btnstep.asm with its
   records, and its 1,233-byte slot holds both states. Making it lazy needs the slot's place per state in the
   restore's form and a third resident part. That would be ~0.4 a cached press, which happens a few times a room
   visit: not built.

### Memory (main 7baaac2 / this)

| area | change |
|---|---|
| main (end_of_code 0x78E1 -> 0x78F0) | +15: the hooks in restore_shadow (head, tail) and shadow_write (head), frm_drop's FE_CMASK, frm_clr; **784 free** |
| low code block (end_of_low 0x1FCF -> 0x1FD3) | +4 (obj_chunk's call): 45 free; block 2 unchanged (14 free) |
| low RAM 0x0500-0x06FF | the low code, part 1 (src/m4/ovl_low.asm, frmlow.asm): 485 bytes |
| low RAM 0x0700-0x076D | FRM_TAB (moved from 0x09DB, 8 -> 20 bytes an object) and the low code's variables: 110 bytes |
| low RAM 0x0E00-0x0FFF | the low code, part 2 (ovl_low2.asm, frmlow2.asm): 483 bytes |
| overlays | frames 1,020 -> 988 (36 free); room 975 -> 980 (44 free); the table 14 -> 16 entries |
| RAM disk, every size | the low code's images: page 4 0xFE00-0xFFE4, page 1 0xDE18-0xDFFA (both copied in by game_start at every start) |
| RAM disk, runtime only | 512 KB / 1 MB: the complete-picture pool, page 6 0x16C0-0x25BF (4 x 960; 704 bytes of the part 17 gap left); 16 MB: page 62 0x6000-0xBFFF |

The free low RAM of parts 19 and 20 is used, and main stays nearly as it was. The two parts are separate W-type
overlays because their images need own places of at most 512 / 488 bytes (docs/memory.md "The low code"). The
write-back reuses shadow_write's body through COMPOSE_A, which is free while the tiles are redrawn (colshift.asm uses it
the same way). A row-by-row RAM-disk copy would have needed ~70 bytes more.

### Why it cannot tear (tools/optione.py direct2)

The copy writes a row's four planes, then the next row, top first. That is slower than the beam (as pend_flush's chunk
copies), so the beam must not overtake it:
- **Its speed, measured on a chopper's 4-byte rows:**
  - 2.5 lines a row (151 lines a copy) without RAM-disk waits;
  - 3.6 (216 lines) with the 15 wait states the boot accepts at most.

  Up to 8 lines a row when the VBLN interrupt falls inside.
- **When it starts:** when d, the lines until the beam next reaches the rect's top row, is at least
  (3w - 2) / 4 x CRH + 20 (2.5 CRH + 20 for a chopper), and at most 312 - 12 (not just behind the beam: pend_flush's
  guard).

`direct2` traces every copy row by row (lc_direct's ld_r) and the interrupt's entry. A pass of the beam over the rect
is torn when a row is being written while the beam is on it, or when the rows are mixed (some new, some old):

| scenes (l08r23_stand_a, l03r16_walk_a, l05r24_stand_a, l10r10_walk_a, fight_chomper, the spike scenes) | copies | torn passes | longest copy | closest beam (lines) | wait a copy (lines, mean) |
|---|---:|---:|---|---|---|
| 16 MB, no waits (trace build) | 255 | 0 | 152.6 | 78 behind a row, 12.5 ahead | 22-114 |
| 16 MB, 15 waits (mz800emu-regions) | 255 | 0 | 215.8 | 16 behind, 12.4 ahead | 38-94 |
| 1 MB, no waits | 100 | 0 | 152.6 | 78 behind, 12.6 ahead | 10-106 |
| 1 MB, 15 waits | 100 | 0 | 215.8 | 18 behind, 12.8 ahead | 34-77 |

The start condition is fixed for the worst RAM disk. Without waits a copy waits ~20-60 lines more than it needs to (the
boot's measured speed, HO_RDSPD_MAIN, is not read: 0 in the harness). That is the next small gain here (~0.1 a copy).

### Per chopper step (tools/busyrooms.py measure, walk_chomper a - b on ticks with one picture change, misses included; median / mean, main -> this)

| room (ticks) | 512 KB | 1 MB | 16 MB |
|---|---|---|---|
| l03r16 (54) | 3.04 / 3.30 -> **2.47** / 2.76 | 3.07 / 3.29 -> **2.36** / 2.83 | 3.04 / 3.25 -> **1.85** / 2.36 |
| l05r24 (39) | 2.99 / 3.41 -> **2.29** / 2.79 | 2.99 / 3.40 -> **2.30** / 2.76 | 2.98 / 3.36 -> **1.90** / 2.40 |
| l08r04 (46) | 2.70 / 2.99 -> **2.13** / 2.14 | 2.69 / 2.96 -> **2.10** / 2.15 | 2.74 / 2.97 -> **1.16** / 1.65 |
| l08r23 (46) | 2.97 / 3.24 -> **2.43** / 2.68 | 2.84 / 3.22 -> **2.42** / 2.61 | 2.80 / 3.19 -> **1.55** / 2.08 |
| l10r10 (16) | 3.78 / 3.93 -> **3.56** / 3.74 | 3.78 / 3.88 -> **3.55** / 3.71 | 3.96 / 4.07 -> **3.95** / 3.95 |
| l10r14 (38) | 2.96 / 3.19 -> **1.79** / 2.26 | 2.96 / 3.12 -> **1.74** / 2.19 | 2.91 / 3.04 -> **1.52** / 1.96 |

- **16 MB:** -1.1..-1.6 a step at the median (l08r04 2.74 -> 1.16). This is every chopper's complete picture plus the
  lazy shadow.
- **512 KB and 1 MB:** -0.4..-1.2. That is the lazy shadow plus the pool, which covers 4 of the first chopper's 5
  pictures.
- **l10r10** gains little: its kid is in a chopper's rect on most of these ticks.
- **The means** hold the misses after each death and restart (dr_run, unchanged).

**Spikes** (tools/trapscenes.py's 9 spike scenes, 107 steps; a - b median / mean): 1 MB 3.10 / 2.84 -> 3.09 / 2.87,
16 MB 3.13 / 2.84 -> 3.06 / 2.84. Nearly all of these steps are misses (the first cycle after the room draw) with the kid
in the rect: the lazy shadow saves only on hits, and the complete pictures are not kept for spikes.

### The busy rooms (tools/busyrooms.py measure; frames a tick median / p90 / mean work, main -> this)

| scene | 512 KB | 1 MB | 16 MB |
|---|---|---|---|
| l03r16 walk | 7.96 / 12.30 / 8.56 -> **7.46** / 10.96 / 8.11 | 7.89 / 11.99 / 8.25 -> **7.13** / 10.32 / 7.76 | 7.41 / 11.78 / 7.97 -> **6.44** / 9.75 / 6.93 |
| l03r16 stand | 7.01 / 11.00 / 7.76 -> **6.56** / 9.60 / 7.01 | 7.01 / 11.00 / 7.71 -> **6.56** / 9.60 / 6.96 | 7.01 / 11.00 / 7.72 -> **5.40** / 7.73 / 6.15 |
| l08r23 walk | 6.55 / 10.41 / 6.56 -> **5.99** / 9.15 / 6.25 | 5.97 / 9.93 / 6.09 -> **5.48** / 8.64 / 5.78 | 5.71 / 9.86 / 5.83 -> **4.82** / 7.00 / 5.16 |
| l08r23 stand | 5.67 / 9.60 / 5.60 -> **4.69** / 8.48 / 5.13 | 5.67 / 9.60 / 5.56 -> **4.69** / 8.20 / 5.07 | 5.67 / 9.60 / 5.56 -> **4.07** / 5.98 / 4.60 |
| l05r24 walk | 7.06 / 11.51 / 7.59 -> **6.20** / 10.40 / 7.32 | 6.50 / 10.92 / 7.09 -> **5.99** / 9.73 / 6.83 | 6.09 / 10.92 / 6.80 -> **5.32** / 9.25 / 6.26 |
| l05r24 stand | 6.58 / 10.84 / 6.58 -> **4.98** / 9.42 / 6.08 | 6.58 / 10.84 / 6.53 -> **4.98** / 9.39 / 6.02 | 6.58 / 10.84 / 6.54 -> **4.98** / 6.99 / 5.56 |
| l10r10 walk | 7.03 / 15.95 / 8.79 -> **6.33** / 15.98 / 8.65 | 7.03 / 15.84 / 8.60 -> **6.31** / 14.99 / 8.50 | 6.36 / 14.97 / 8.13 -> **5.56** / 15.43 / 8.02 |
| l10r10 stand | 5.97 / 9.92 / 5.97 -> **4.58** / 8.84 / 5.44 | 5.98 / 9.92 / 5.92 -> **4.58** / 8.56 / 5.39 | 5.93 / 9.98 / 5.92 -> **4.03** / 5.99 / 4.88 |
| l08r04 walk | 6.87 / 11.44 / 7.03 -> **5.93** / 9.37 / 6.53 | 6.45 / 10.51 / 6.50 -> **5.16** / 8.51 / 5.99 | 5.96 / 10.44 / 6.10 -> **4.94** / 7.01 / 5.25 |
| l08r04 stand | 5.96 / 9.97 / 5.66 -> **4.99** / 8.55 / 5.20 | 5.96 / 9.97 / 5.61 -> **4.99** / 7.98 / 5.15 | 5.97 / 9.97 / 5.61 -> **4.98** / 6.98 / 4.89 |
| l10r14 walk | 5.01 / 8.00 / 5.78 -> **5.02** / 7.31 / 5.63 | 4.74 / 7.49 / 5.24 -> **4.92** / 7.01 / 5.06 | 4.03 / 7.09 / 4.94 -> **4.05** / 6.07 / 4.66 |
| l10r14 stand | 3.99 / 6.92 / 4.37 -> **3.99** / 5.55 / 4.06 | 3.99 / 6.92 / 4.32 -> **3.99** / 5.55 / 4.01 | 3.99 / 6.92 / 4.32 -> **3.99** / 5.42 / 3.95 |
| l07r19 walk | 7.23 / 11.07 / 7.90 -> **7.28** / 10.76 / 7.93 | 6.29 / 10.95 / 7.28 -> **6.36** / 10.96 / 7.32 | 6.29 / 10.10 / 7.05 -> **6.36** / 10.11 / 7.09 |
| l07r19 stand | 3.99 / 7.49 / 4.67 -> **3.99** / 7.46 / 4.65 | 3.99 / 7.08 / 4.62 -> **3.99** / 7.09 / 4.63 | 3.99 / 7.08 / 4.62 -> **3.99** / 7.09 / 4.63 |

- **The standing scenes:** the median falls by 0.5-1.6 frames, the p90 by 1-4 (16 MB). l08r23 stands at 4.07 / 5.98 on
  16 MB, 4.69 / 8.2 on 1 MB.
- **The walking scenes** gain less: the kid passes through the choppers' rects.
- **l07r19** (gates, a spike) and **l10r14 stand** are as before.

### perfcheck (one run per size; main 7baaac2's runs = the baselines; lowered where beaten, in this commit)

| Stretch | 512 KB base / new | 1 MB base / new | 16 MB base / new |
|---|---|---|---|
| normal tick (walkthrough 30-60) | 4.73 / 4.73 | 4.51 / 4.51 | 4.44 / 4.44 |
| level door step (walkthrough 203-207) | 8.73 / **8.56** | 7.90 / 7.90 | 7.90 / 7.90 |
| room change (walkthrough 89) | 87.93 / 88.03 | 88.25 / 88.26 | 87.26 / 87.27 |
| walkthrough 190-260 | 5.95 / **5.92** | 5.77 / 5.77 | 5.42 / 5.42 |
| gate (gate_push 200-260) | 4.04 / 4.04 | 4.04 / 4.04 | 4.04 / 4.04 |
| traps (traps_b1 0-300) | 5.00 / 5.01 | 4.80 / 4.81 | 4.78 / 4.78 |
| fight (fight1 60-160, guard on) | 6.35 / 6.35 | 5.63 / 5.67 | 5.42 / 5.43 |
| **choppers (frm_button 20-120)**, new | 6.86 / **6.43** | 6.63 / **6.18** | 6.29 / **5.55** |

- **The new stretch:** l10r10's two choppers and a closer (tests/m4_scripts/frm_button.txt). Its baselines are this
  commit's.
- **The fight +0.04 at 1 MB:** the hooks' early exits (a few calls a chunk). It is within the tolerance, and the
  baseline stays.
- **The room change +0.1 at 512 KB:** frm_clr before the draw, and the beam phase.
- **The 512 KB level door step:** the beam phase.

### Same pixels, same logic

- **tests/m4_game.py --every 1** at 512 KB, 1 MB and 16 MB, 0 state diffs and 0 differing pixels on each of 33
  scripts:
  - chomper (the blood), fight_chomper, frm_button, frm_spike_btn, btn_bars, traps_b1, traps_b9, walk_level1, fight1,
    fight_spikes;
  - the trap scenes l07_spike_a, l08_spike_a, l14_spike_a, l06_spike_c, l07_spike_c;
  - the walk_a and stand_a of the busy rooms l03r16, l08r23, l05r24, l10r10, l08r04, l10r14, l07r19, l09r22, l09r01.
- **tests/m4_test.py** (chomper, fight_chomper, frm_button, frm_spike_btn, traps_b1): 0 differing.
- **tools/movecheck.py** chompers (780 steps), spikes (3,600), caches (2,352 screens): 0 differ.
- **tests/m5_boot.py:** RUNTIME_SCRATCH now leaves out the complete-picture pool.
- `make ci-build`, `make cheats`, `make pace`, `make m3`. The full regression on the runners: see the PR.

Faults found on the way (the emulator tests found them; the pixels stayed exact):
- The hit test read the complete pictures' mask instead of the pictures' (an instruction inserted between the load and
  the test), so most hits went the miss path.
- lc_save tested lc_sv's full address after clearing only its high byte. A later chunk could then write a complete
  picture through a stale entry pointer: one 16 MB run of frm_button stalled.
- lc_sv was also not cleared at a room draw (frm_clr now clears the low code's variables with FRM_TAB).

After those, two runs stalled once each: a 1 MB l10r14_stand_a at tick 0, and one busy-rooms measurement. Both ran
with 9-12 emulators on 8 cores, and neither repeated alone. A capped run of all 54 busy-room scripts at 1 MB (a scratch
script: every tick within 400 frames) and the 99 final pixel runs did not stall.

## M8a part 26: the full room draw without the cover scan (2026-11-09)

Status: **built.** Candidate 10 of the speed roadmap ("the black fill skipped where a back op covers the whole cell")
was measured first, gave nothing, and turned into a different cut of the same code: the full draw's cells skip
run_rect's cover scan, and the bucket ops skip rec_lay's touch test.

### Measure first: no cell is ever covered

The full draw lays 15 cells of 8 bytes x 64 rows (run_ops). run_rect already applies its cover rule there: a first
pass over the cell's back and mid ops (RR_MODE 1, rl_scan) looks for the last copy-mode op without a partial edge that
covers the whole rect, and skips the fill and every op before it. Counted over every room of levels 1-14 (316 rooms,
4,740 cells; popdata.room_oplist with the build/assets directories, a scratch script):

| cover | cells | rows of cells |
|---|---:|---|
| one copy-mode op over the whole cell (run_rect's rule) | **0** | |
| the union of the copy-mode ops (exact edges) | 0 | 5.0 % of the cell rows fully covered: ~0.75 cells' worth a room, ~0.14 frames of the 2.75-frame fill |
| upper bound: any opaque pixel of any back or mid op (masked ops too) | 0 | 10.5 %: ~1.6 cells' worth (l10r01 3.5), ~0.3 frames, and only with per-pixel mask knowledge at run time |

The pieces are at most a tile (4 bytes) wide and a cell straddles the tile rows (63 rows at y = 2 + 63 k against
bands of 64), so no single piece covers one. A fill of only the uncovered row ranges would save ~0.14 frames a room
change: below the 0.5 the roadmap asks for. **The fill stays.** What the measurement showed instead: **the scan runs
for every op of every cell and never finds a cover.** M8a part 20's breakdown already had "the scan 2.5" frames a room
change.

### What changed (src/m3/roomfull.asm; the room overlay, so the M3 test programs run the same code)

1. **rf_cell** replaces run_ops' `call run_rect`: COMPOSE_A, rect_bounds, then room.asm's rr_fill (the black fill,
   the back and mid lists) and rr_sw (the shadow write, the fore list, the blit). This is run_rect without its scan pass
   and without rc_hook. rc_run returns at once while bkt_on is set anyway. RR_SHONLY is 0 in a full draw. Laying
   every op over black is exactly what run_rect does when the scan finds no cover. **The pixels cannot differ, whatever
   the room**: the rule never fired, and skipping it is the run_rect path for "no cover".
2. **rr_bkt calls rl_lay, not rec_lay.** A bucket holds the ops whose clipped rect meets the cell (bkt_build's column
   and band ranges are rec_lay's touch test), and lay_piece16 clips every piece to the rect anyway. Only rf_cell's lay
   pass reaches rr_bkt now, in RR_MODE 0. An overflowed bucket (0xff) still scans through rr_tbl and rec_lay.

Nothing after the draw reads the scan's results (rr_cnt, rr_last, rr_lastrec, RR_PTRS): flames_build runs its own
scan. tools/roadmap.py stages now counts rf_cell under "15 cells" and rl_lay under "laying the ops".

### Memory (main 71f7da3 / this)

| area | change |
|---|---|
| room overlay (W1) | 980 -> **995 bytes (29 free)**: rf_cell 15 bytes (its call replaces run_ops' call of run_rect) |
| RAM disk page 7 | the overlays after the room overlay 15 bytes later (the release's and the cheat build's packs fit as before) |
| main, low, block 2 | unchanged (784 / 45 / 14 free) |

### The room change (tools/roadmap.py stages, one tick, inclusive frames; main 71f7da3 / this)

| room (tick) | 512 KB | 1 MB | 16 MB | 15 cells (1 MB) | laying (rec_lay + rl_lay, 1 MB) |
|---|---|---|---|---|---|
| l01r01 (25) | 80.90 / **78.38** (-2.52) | 80.03 / **77.34** (-2.69) | 80.03 / **77.34** (-2.69) | 64.06 / 61.54 | 37.38 / 35.38 |
| l01r07 (22) | 82.01 / **79.75** (-2.26) | 82.01 / **79.75** (-2.26) | 82.17 / **79.90** (-2.27) | 65.17 / 62.90 | 38.57 / 36.80 |
| l03r16 (19) | 86.00 / **83.67** (-2.33) | 86.85 / **84.51** (-2.34) | 86.13 / **83.63** (-2.50) | 68.49 / 65.99 | 41.80 / 39.80 |
| l04r04 (23) | 73.70 / **71.40** (-2.30) | 72.64 / **70.36** (-2.28) | 72.64 / **70.36** (-2.28) | 56.83 / 54.55 | 30.27 / 28.52 |
| l05r24 (3) | 90.68 / **87.76** (-2.92) | 90.53 / **87.54** (-2.99) | 90.53 / **87.54** (-2.99) | 70.91 / 67.89 | 44.06 / 41.66 |
| l10r01 (3) | 94.75 / **91.49** (-3.26) | 95.43 / **91.93** (-3.50) | 95.43 / **91.93** (-3.50) | 77.04 / 73.54 | 50.08 / 47.30 |

(The rooms of tools/roadmap.py `enter`, as in part 20.) The gain grows with the op count: the scan visited every
bucket op once more. On l01r07, change 1 alone was -1.49 and change 2 -0.77. The fill (2.75), the shadow write and the
copy are unchanged. The RAM-disk reads of the tick are 15 bytes more (the larger overlay's load).

### perfcheck (one run per size; main 71f7da3 = the baselines; lowered where beaten, in this commit)

| Stretch | 512 KB base / new | 1 MB base / new | 16 MB base / new |
|---|---|---|---|
| normal tick (walkthrough 30-60) | 4.73 / 4.73 | 4.51 / 4.51 | 4.44 / 4.44 |
| level door step (walkthrough 203-207) | 8.56 / 8.56 | 7.90 / 7.90 | 7.90 / 7.90 |
| room change (walkthrough 89) | 87.93 / **85.70** | 88.25 / **85.71** | 87.26 / **85.27** |
| walkthrough 190-260 | 5.92 / **5.91** | 5.77 / 5.77 | 5.42 / 5.42 |
| gate (gate_push 200-260) | 4.04 / 4.04 | 4.04 / 4.04 | 4.04 / 4.04 |
| traps (traps_b1 0-300) | 5.00 / **4.99** | 4.80 / **4.79** | 4.78 / **4.77** |
| fight (fight1 60-160, guard on) | 6.35 / 6.35 | 5.63 / 5.67 | 5.42 / 5.42 |
| choppers (frm_button 20-120) | 6.43 / 6.43 | 6.18 / 6.18 | 5.55 / 5.55 |

Only the full room draw changed: the play stretches are equal. The 1 MB fight's +0.04 is the same beam-phase noise as
in part 25 (no code it runs changed), and its baseline stays.

### Same pixels, same logic

- **tests/m3_test.py**, every room of levels 1-14 (the full room draw against the Python reference, the op lists
  too): 0 differing pixels.
- **tests/m3_anim_test.py**, levels 1, 4, 10 and 13: 0 differing.
- **tests/m4_game.py --every 1** at 512 KB, 1 MB and 16 MB on walk_level1, run_rooms, level12_exit_level13,
  level13_exit and level6_shadow_exit: 0 state diffs and 0 differing pixels on each of the 15 runs.
- `make ci-build`, `make cheats`, `make pace`. The full regression on the runners: see the PR.
