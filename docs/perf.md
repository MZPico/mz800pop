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
