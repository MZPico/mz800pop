# Memory map (M4 game + M6 guard logic and drawing, code overlays, M5 level-event logic and drawing, save, M7 launcher, sound model, PSG player and music, waits on sound, PRES title and cutscenes, keys, M8a part 2 gate redraw and pacing, the memory reclaim of 2026-11-01)

Baseline: MZ-800 with the 32 KB VRAM extension and a 512 KB paged RAM disk (decided 2026-10-27; swapping
level art per level from floppy, to fit 256 KB, is a late option only). Sources of truth: the `equ`s in
src/m1/gfx.asm, src/m3/room.asm, src/m4/*.asm and `build/m4game.sym`.

## Main RAM

The VRAM window (0x8000-0x9FFF) and CG-ROM (0x1000-0x1FFF) are mapped only inside `blit`; everywhere
else all 64 KB are RAM. Code in the low block must never run inside `blit`.

| Range | Size | Content |
|---|---|---|
| 0x0000-0x00FF | 256 | the guard's sword image buffer (GSWBUF; largest sword image 256 bytes in the kernel's format) |
| 0x0100-0x0147 | 72 | torch cache valid flags (TC_VALID) |
| 0x0148-0x01B7 | 112 | the guard trace snapshot G_SNAP (30) and the guard records and globals gv_start..gv_end (KID_REC, GUARD_REC, OPP_REC, CHAR_SAVE, guardhp ... roomleave_result; src/m4/guard.asm equs, moved from block 2 in M7 step 5), runtime only (guard_init zeroes gv_start..gv_end) |
| 0x01B8-0x01BC | 5 | M8a part 2 pacing (game.asm): NEXT_TICK (the frame the next tick is due, mode 1), SKIP_TICK, SKIP_RUN, SKIPPED (the last tick's drawing was skipped: the tile snapshot is kept); mode 0 (the release) never writes them; runtime only |
| 0x01C0-0x01C9 | 10 | HP_VARS: the hit point strips' variables (game.asm equs hp_i .. hp_pf; the code is the rare overlay, src/m4/hpstrip.asm; overlay.asm ghp_draw sets hp_n, hp_nf, hp_base, hp_pf before the overlay is loaded), runtime only |
| 0x01CA-0x01FC | 51 | M8a part 7 (people2.asm st_look): ST_KEY, each character slot's look in the last drawn tick (slots 0, 1, 6, 2, 3: SD_DX .. SD_COMPOSE + 1 and PP_XD, 10 bytes each), ST_OK (the last tick had overlay ops, a splash, or a room was drawn after it: sprite_forget); runtime only |
| 0x01BD-0x01BF, 0x01FD-0x01FF | 6 | free (runtime data) |
| 0x0200-0x027F | 128 | run_rect's recorded ops (RR_PTRS, 64 pointers) |
| 0x0280-0x029E | 31 | level-event state EV (objects.asm: next level, time left, bottom text and flash timers, feather fall, upside down, mirror, shadow script, checkpoint, restart / level switch / game over flags, keys (KEYS: bit 0 Ctrl+A, bit 2 Ctrl+G, bits 3-7 a key code, src/m4/keys.asm); for the drawing TEXT_GEN, FLASH_NOW, MI_JUMPED, TXT_GEN_SHOWN, the save overlay's text TEXT_MSG / TEXT_MSG_GEN); set by game_init, runtime only |
| 0x029F | 1 | HO_RDSPD_MAIN (src/boot/launch.inc): the RAM disk's read speed as the boot measured it (src/boot/rdspeed.asm, docs/ramdisk-tiers.md section 1: the game pattern's mean, clocks/byte x 5, 105 = 21.0 = no wait states, 255 = 51.0 or more); set by the launcher at every start after zeroing low RAM; 0 in the harness; read by nothing yet (PLAN item 50) |
| 0x02A0-0x02AF | 16 | HO_MAIN: the launcher's copy of the handoff block (src/boot/launch.inc; magic "P7" = the game was started by the launcher, M7); zeroed by the launcher otherwise, never written by the harness except KEY_OPT 0x02A8 = HO_OPTIONS: bit 0 the sound off (Ctrl+S, M7 step 10; goes through PRES with the block), bit 1 blind (CHEATS only); 0x02AF = HO_RDTOP: the RAM disk's last page as the boot's probe found it (7 = 512 KB, 15 = 1 MB, 255 = 16 MB; set by the launcher at every start; 0 in the harness = the 512 KB layout; read by nothing yet, docs/ramdisk-tiers.md) |
| 0x02B0-0x02B4 | 5 | m4test only: N_SNAP, the 'N' trace snapshot (snd_snap: queued, started, playing, stops) and its counter |
| 0x02C0-0x02DB | 28 | m4test only: S_SNAP, the 'S' trace snapshot (state_snap) and its counter |
| 0x0300-0x03C0 | 193 | M5 drawing (overlay.asm, fx.asm): spr_xor's row SXT 0x0300 (73), the descriptors of slot 5 (the guard's splash when both are hurt) SPR_SP2 0x0350 and slot 6 (the mirror image) SPR_MI 0x0368, the sort keys PP_KEYS 0x0380 (7, slot 6 first), PP_ORD, per slot PP_XD (XOR offset) and PP_CL (left clip), PC_SAVE, and single variables to PP_ANYFX 0x03C0 (FL_SHOWN 0x03B8: the flash shown this tick, read by tests/m4_game.py; UP_SHOWN, TXT_VIS); runtime only |
| 0x03C1-0x03C7 | 7 | SND: the sound model (src/m4/sound.asm: next_sound, current_sound, sound 15's interruptible flag, the stop counter, is_screaming, trigger_button's sound flag, the end-music flag; game_init clears it), runtime only |
| 0x03C8-0x03DC | 21 | SP_VARS: the PSG player (src/m4/psg.asm: SP_WAIT frames until the next group (0 = no stream), SP_PTR the ring's read pointer, MF_SRC / MF_LEFT / MF_W the refill (RAM-disk address, bytes left, the ring's write position), SND_MODE 0 silent / 1 hybrid (the launched game: game_init_h) / 2 ticks / 3 live (tests; sound.asm header), ENV 0x03D1 the four envelopes (attenuation, counter, period)); irq_init stops the player, runtime only |
| 0x03DD-0x03DF | 3 | the ticks sound model (src/m4/sound.asm, M7 step 5): SND_LEFT (ticks the playing sound has left), NEED_L1M (the level 1 music crouch), END_OVER (hybrid: the level end's clock stopped); game_init clears them, runtime only |
| 0x0400-0x04EF | 240 | slice extents (SL_Y0, SL_Y1) |
| 0x0500-0x077F | 640 | wall-pattern random draws mod 140 (PR_TAB: 64 seeds x 10, built at the first room) |
| 0x0780-0x07CF | 80 | sprite descriptors (overlay.asm): the guard's sword SPR_GS 0x0780, the guard SPR_G 0x0798, the hurt splash SPR_SP 0x07B0; the draw list PP_DL 0x07C8 (count + 7 slots) |
| 0x07E0-0x07EF | 16 | SEQBUF: the sequence window play_seq reads |
| 0x0800-0x08FF | 256 | VARS: frame counter, VBLN line latch, input, compose rect, falling-floor rects, dirty list |
| 0x0900-0x09A3 | 164 | RV: room renderer state |
| 0x09B4-0x09DA | 39 | people drawing (overlay.asm): the characters' dirty rects PP_KU/PP_GU, the guard's hit point icon GHP_PAT and strip state GHP_M/GHP_SHOWN, chunk state (0x09A4-0x09B3 and 0x09DB-0x09FF free: the keys moved to 0x0380) |
| 0x0A00-0x0AFF | 256 | KV: Char (the character being played: the Kid between ticks), controls, geometry, collisions, PP_SAVE (0x0AB0: Char while the people are placed), kid trace snapshot, pending chunk list, clip_char of the character being placed |
| 0x0B00-0x0BFF | 256 | the kid's sprite descriptor SPR_A, trap state (OV), TROBS (30), MOBS (14) |
| 0x0C00-0x0FFF | 1 KB | MASKBUF, DATABUF (piece laying; MASKBUF is also scratch for pc_col's clip column and the text overlay's bitmap) |
| 0x1000-0x119B | 412 | the kid's sword image buffer, its sprite descriptor SPR_S (ROM monitor work area: runtime data only) |
| 0x1200-0x1FFF | 3.5 KB | low code block (kid2.asm, view.asm, sprite.asm, evres.asm, fx.asm; end_of_low 0x1FE5: 27 bytes free (M8a part 8's run-wise tile snapshot: +81, its 106-byte pointer table moved to 0xF58B; M8a part 9's fs_on jump in char_fetch: +3)) |
| 0x2000-0x7BFF | 23 KB | main code (people2.asm after objects.asm, then sndobj.asm, fslook.asm; end_of_code 0x795F: 673 bytes free below W1 (M8a part 7's st_look: +169; part 8's spr_draw and restore_shadow row loops: +42; part 9's frame store lookup fs_look: +95); PACE_MODE (0x213C) is a byte in game.asm's code: 0 in the release, 1 in `make pace`) |
| 0x7C00-0x7FFF | 1 KB | overlay window W1 (src/m4/ovl.asm): the room overlay (938 bytes, 86 free), the events overlay (1,009 bytes, 15 free), the guard-leave overlay (342 bytes, 682 free), the guard-enter overlay (943 bytes, 81 free), the keys overlay (469 bytes, 555 free; CHEATS=1 832 bytes, 192 free) or the rare overlay (423 bytes, 601 free) |
| 0x8000-0x80FF | 256 | bit-reverse table |
| 0x8100-0x81F7 | 248 | room renderer slice tables |
| 0x8200-0x8FFF | 3.5 KB | sprite shift tables (shifts 1-7, lo/hi pages) |
| 0x9000-0x9B87 | 2.9 KB | room op lists (back 192, mid 8, fore 128 records) and tags (M7 step 5 measured the largest rooms of levels 0-14: back 185, fore 126, mid 1 records: no reclaim) |
| 0x9B88-0x9BEB | 100 | the ticks sound model's lengths SND_T12 / SND_T10 (ids 0-49 at 12 and 10 ticks a second; sound.asm, copied by game_init from the level-start overlay; read only by snd_next, never inside blit), runtime only; 0x9BEC-0x9BFF free |
| 0x9C00-0x9F8F | 0.9 KB | temporary op lists (tile regeneration, kid overlays), sprite row buffers |
| 0x9F90-0x9FE7 | 88 | the guards' skill tables and tbl_guard_type (guard.asm GUARD_TABS, moved from block 2 in M7 step 10; copied by game_init from the level-start overlay; never read inside blit), runtime only; 0x9FE8-0x9FFF free |
| 0xA000-0xBFFF | 8 KB | COMPOSE_A, COMPOSE_B, SPRBUF_A (kid image), SPRBUF_B (third compose chunk; in a tick with the mirror image (slot 6, at 0xB800) or two hurt splashes (slot 5, at 0xBC80) it holds those images and stays out of the chunk rotation); 0xA000-0xAFFF (COMPOSE_A/B) is also overlay window W2 while a level starts, a bottom text is drawn or the game is saved (the level-start overlay, 2,201 bytes, 1,895 free; the text overlay, 1,021 bytes, 3,075 free; the save overlay, 697 bytes, its sector buffer at 0xA700 and the directory buffer 0xA800-0xAFFF) |
| 0xC000-0xEBFF | 11 KB | tables block (tables.inc; the kid width and guard size tables moved to logic.bin) + overlay.asm (the people on screen: objects, overlays, order, guard hit points), tcache.asm, rcache.asm, guard.asm (code ~5.1 KB, then its harness option blocks guard_opts, ev_opts; G_SNAP and the records/globals are in low RAM 0x0148 since M7 step 5; addresses in build/m4game.sym; the room-change parts are W1 overlays: src/m4/gleave.asm, genter.asm), sound.asm (M7: the sound model and the waits on sound, ~640 bytes), psg.asm (M7: the PSG player, its ISR part with the envelopes, the ring refill; 321 bytes), keyres.asm (M7 step 10: key_scan), gate.asm (M8a part 2: gate_redraw, 76 bytes); block2_end 0xEB24: 220 bytes free (M8a part 7: +19) |
| 0xEC00-0xF500 | 2305 | the current level's blueprint |
| 0xF510-0xF5F4 | 229 | the tile-change snapshot (view.asm, runtime only): VIEW_SNAP 0xF510 (53 x tile byte, modifier), VS_BTN 0xF57A (up to 8 x (entry, pressed) of the buttons on screen, then 0xff), vs_ptrs 0xF58B (53 x the entry's tile byte address, 0 = no room; rebuilt when the room on screen changes) |
| 0xF600-0xFA7B | 1,148 | the guard's image buffer SPRBUF_G (largest guard image 1,092 bytes in the kernel's format, kid images for the shadow 1,148) |
| 0xFA80-0xFC87 | 520 | the hurt splash's image buffer SPLBUF (slot 4; a second splash in the same tick: SPRBUF_B + 0x480) |
| 0xFCE0-0xFDFF | 288 | stack |
| 0xFE00-0xFE01 | 2 | IM2 vector (the PIO's vector 0; the 8253's interrupt is masked) |
| 0xFE02-0xFEFF | 254 | MUS_BUF: the PSG player's ring buffer (M7 step 4: every stream, refilled from the RAM disk by snd_fill in main code; at most 253 bytes unread) |
| 0xFF00 | 1 | free |

The guard logic (src/m4/guard.asm) keeps its records and globals in low RAM (0x0148, equs; block 2 until M7 step 5): the Kid,
Guard and Opp records (16 bytes each, SDLPoP char_type order), Char as the tick left it (CHAR_SAVE), guardhp,
can_guard_see_kid, the sword fighting timers and flags; `guard_opts` (flags, count, placed guards) is the harness
option block (see the guard.asm header); `G_SNAP` (30 bytes) is the guard trace snapshot tests/m4_test.py reads.
The level's guard arrays are in the blueprint at LEVEL + 2119 (tile, dir, x, seq_lo, skill, seq_hi, colour: 24
bytes each). `ev_opts` (6 bytes: start room, tile, direction; minutes and ticks left) is the harness option block of the
level events ('# start', '# time'). The logic test program (m4test.asm) has its own layout: tables + guard.asm from
0xC000 (block2_end 0xDC17), main code to 0x778D, the overlays' code (roomfull.asm, altmods.asm, levelstart.asm,
evres.asm, events.asm) at 0xA000-0xAA91 (no compose buffers there), harness script at 0xE400-0xEBFF, the level
blueprints in the RAM disk as in the game (it loads levels itself: restarts, level switches).

The program file loads at 0x1200 (low block, then the main code from 0x2000; entry 0x2000). Everything from
0xC000 up is a second block (`.b2`) that the harness pokes and the floppy loader (below) loads: the ROM tape
loader cannot write 0xD000 and above, nor use 0x1000-0x11FF.

Image directories are no longer in main RAM: `dir_entry` (room.asm) copies one 8-byte entry from the RAM
disk when it is needed (~300 T, ~12 lookups per tick). Its table `dir_tab` can also point into main RAM
(page 0xFF), which the M3 test programs use.

M5 drawing (2026-10-30): the new resident code went into the low block (fx.asm: the shadow's XOR copy, the
upside-down chunk tops), the main block (people2.asm: the mirror image, the left clip's column, the blink, the text and
flash checks; gfx.asm: blit_flip, sd_bounds) and block 2 (overlay.asm: seven object slots); the rarely run parts are
overlays (the text line in W2, set_flip in the room overlay). No reclaim was needed. Still free in low RAM (runtime
data only): 0x0148-0x01FF, 0x029F (taken 2026-11-03: HO_RDSPD_MAIN), 0x02B0-0x02BF, 0x03C1-0x03FF, 0x09A4-0x09B3, 0x09DB-0x09FF (M7 took 0x0148-0x01FF and
0x03C1-0x03D0, step 4 gave 0x0148-0x01FF back and took 0x03D1-0x03DC: still free 0x0148-0x01FF, 0x029F, 0x02B0-0x02BF in
the game, 0x03DD-0x03FF, 0x09A4-0x09B3, 0x09DB-0x09FF).

Reclaim and save (2026-10-30): the guard's room-change code went from block 2 (and anim_tile_modif from the main
block) into two W1 overlays: guard-leave (src/m4/gleave.asm: exit_room's guard part = leave_guard, follow_guard;
check_guard_fallout's action part; guard_tile_ptr) and guard-enter (src/m4/genter.asm: check_the_end's room part =
anim_tile_modif, check_fall_flo, check_shadow, enter_guard, get_guard_hp; do_init_shad from src/m4/shadinit.asm, which
the events overlay also includes: one W1 overlay cannot call another). Freed: block 2 873 bytes (block2_end 0xEBC8 ->
0xE85F), main 162 bytes net of the three stubs (end_of_code 0x7BD5 -> 0x7B33). Then the keys (get_controls: Ctrl+A /
Ctrl+G from the keyboard matrix, edge-triggered) and the save stubs took 32 bytes of main (end_of_code 0x7B53). The
IM2 table and the op-list sizes were not needed as reclaims.

## Code overlays (src/m4/ovl.asm, 2026-10-29)

Code that does not run every tick is assembled separately (src/m4/ovl_*.asm, against the main program's symbols:
tools/ovltool.py equ) and lives in the RAM disk (page 7 from 0xD900 since 2026-11-01, page 6 0xE300 before: a 12-entry table
(OVL_MAX), then the images; tools/ovltool.py pack -> build/m4ovl.bin, written by tests/m4_game.py setup and later by the
floppy loader). Resident code calls it
through stubs in ovl.asm that copy the overlay into its window first:

| Window | Range | Overlays | Loaded |
|---|---|---|---|
| W1 | 0x7C00-0x7FFF (1 KB, top of the main code) | 0 room (938 B): draw_room_full = room_ops, tile_tag, slices_build, bkt_build, rr_bkt, run_ops (src/m3/roomfull.asm); set_flip (the upside-down screen's code patches, src/m4/ovl_room.asm: a full room draw follows it) | when not the current W1 overlay (ovl_cur1): today once, at the first room draw |
| W1 | | 2 events (1,009 B): proc_get_object + add_life (the potions and the sword: hit points, flashes, feather fall, upside down, open), autocontrol_shadow (the scripted shadows of levels 4, 5, 6, 12, do_auto_moves, the level 12 union), jump_through_mirror, and since 2026-11-01 the buttons: trigger_button (do_trigger_list, trigger_gate) and died_on_button (src/m4/events.asm) | when not the current W1 overlay: a shadow level reloads it at its first shadow tick after a room draw (~13 K T), a plate pressed (the kid, a guard, a loose floor; every tick while the kid stands on it, loaded once), the next room draw reloads the room overlay (~19 K T) |
| W2 | 0xA000-0xAFFF (COMPOSE_A/B, 4 KB) | 1 level (2,746 B): game_start (the program's start, src/m4/gstart.asm: video_init, tables_init (src/m1/tables.asm), fs_fill (the frame store's fill, src/m4/fstore.asm, M8a part 9: 1 MB and more; at boot with the game's ACT_FILL, gs_fill), irq_init, sprite_init, sword_init, pr_build (src/m3/prbuild.asm), then game_init and load_level; 2026-11-01), M7's handoff (M7 step 3: game_init_h sets the sound mode SND_MODE, ho_swap mutes the PSG) (load_level_h: the swap to PRES before a level with a cutscene; game_init_h: the level, time and hit points from HO_MAIN; game_over_h: the swap at GAME_OVER, or level 1 without the launcher), load_level, game_init, guard_type_tbl, alter_mods + tile_type_in (src/m3/altmods.asm), play_level (do_startpos, set_start_pos, checkpoint, the level 1/7/13 entries, a seamless start, draw_level_first, show_level), find_start_level_door, guard_init, pos_guards, kid_start_g, guard_x (src/m4/levelstart.asm) | at every call (the compose buffers overwrite it) |
| W2 | | 3 text (940 B): text_draw, the bottom text line with its glyphs (src/m4/text.asm, build/assets/font_text.inc), GAME SAVED / UNABLE TO SAVE GAME (TEXT_MSG); composes in SPRBUF_B | at every call (game.asm text_chk: a text set or erased, the death text's blink) |
| W1 | | 4 guard-leave (342 B): guard_leaves (exit_room after the kid left a room with a guard: leave_guard / follow_guard), guard_fallout (check_guard_fallout for a guard other than the shadow: the level 3 skeleton, death), guard_tile_ptr (src/m4/gleave.asm) | when the kid leaves a room with a guard in it (then the room draw reloads the room overlay) |
| W1 | | 5 guard-enter (943 B): room_entered (check_the_end's new-room part: anim_tile_modif, start_chompers, check_fall_flo, check_shadow, enter_guard, get_guard_hp, do_init_shad; src/m4/genter.asm, shadinit.asm); lrs_body (leave_room's level specials, guard.asm lr_special's resident tail calls it before goto_other_room; 2026-11-01) | at every room change and level start: lrs_body in the kid's tick, room_entered in the same tick's tick_post (one load; then the room draw reloads the room overlay) |
| W2 | | 6 save (697 B; M7 step 3: both entries stop the sound first, snd_halt): save_game (Ctrl+G, levels 3-13) and load_saved (M7's Ctrl+L), the WD2793 code (src/m4/save.asm, src/boot/fdc.asm) | at every call: save_key at a tick start after pend_flush (game.asm), load_saved |
| W1 | | 7 keys (469 B; CHEATS=1 832 B): key_read, key_logic (src/m4/keys.asm, docs/m7-design.md section 18) | when a key of key_tab is down at a tick start |
| W1 | | 8 rare (423 B, 2026-11-01): hp_redraw + hp_strip (the kid's and the guard's hit point strips, src/m4/hpstrip.asm; game.asm hp_draw falls into hp_redraw's stub, overlay.asm ghp_draw calls hp_strip's; their variables HP_VARS 0x01C0), get_item + do_pickup (an item taken, objects.asm check_get_item), chomped (kid2.asm's stub; src/m4/rare.asm) | when the hit points shown change (a level start, a hit, a potion, a guard hit), an item is taken, a chomper kills |

Moving them freed 1,527 bytes of main code (net 503 after W1) (end_of_code 0x7E5B -> 0x7864, of which W1 now takes the top 1 KB) and
191 bytes of block 2 (block2_end 0xEA71 -> 0xE9B2). The M3 test programs and m4test have no loader and include
roomfull.asm, altmods.asm and levelstart.asm directly. How to add an overlay: the comment at the top of src/m4/ovl.asm.

## RAM disk (64 KB pages)

| Page | Content | Free |
|---|---|---|
| 0 | dungeon environment pack (41.5 KB), shadow guard set (0xA800, 16.1 KB), the launcher's copy (0xF000-0xFBFF, M7: src/boot/boot.asm's image, 2.2 KB used) | 1.5 KB (0xA22B-0xA7FF) + 2 KB (0xE868-0xEFFF) + 1 KB (0xFC00-0xFFFF) |
| 1 | shadow room (0x0000, 32,000 B), dungeon wall pack (0x8000), objects (0xC000), sword (0xD000), the PSG sound bank (0xE000-0xE917, M7: build/assets/sound.bin, tools/sndconv.py + tools/midi2psg.py; 2,328 bytes: index 57 x 4, effects 925, the 11 in-game music pieces 1,175) | 1.4 KB (0xDA58-0xDFFF) + 5.8 KB (0xE918-0xFFFF) |
| 2-3 | kid pack (106.3 KB); page 3 0xA000-0xFF2B: the game's compressed image (M7, 24,364 bytes: the program's main-RAM records as a record stream; when it grows past 0xFFFF it continues in page 4 at 0xD400, tools/mkgamedisk.py GAME_SEGS) | 0.2 KB (0xFF2C-0xFFFF) + 0x9F28-0x9FFF |
| 4 | palace environment pack (54.2 KB); 0xD400-0xFFFF: reserved for the game image's second piece | 11.1 KB |
| 5 | palace wall pack (0x0000), 16 level blueprints (0x4000), guard set directories (0x3400, 6 x 0x120, game.asm guard_type_tbl order), directories (0xD100 dungeon env, 0xD800 dungeon wall, 0xDB00 palace env, 0xE200 palace wall, 0xE500 objects, 0xE700 kid, 0xEE00 sword), harness control script (0xF000), the handoff block (0x3AC0-0x3ACF, M7: src/boot/launch.inc) | ~1 KB + 0x3AD0-0x3FFF |
| 6 | torch picture cache (0x0000-0x287F), dungeon guard set (0x3000), palace guard set (0x8000), logic.bin (0xD000-0xE27F: sequence table, kid and guard frame tables, kid image widths 0xE000, guard image sizes 0xE100), the frame store's masks and build id (0xE400-0xE7FF, build/assets/fstore_masks.bin, M8a part 9: the fill's input, written on every size); the code overlays were at 0xE300-0xFFFF until 2026-11-01 (full: now page 7) | 1.9 KB (0x2880-0x2FFF) + 0.4 KB (0xE280-0xE3FF) + 6 KB (0xE800-0xFFFF) |
| 7 | fat (0x0000), skeleton (0x4C40), vizier (0x8D80-0xD8F3) guard sets, code overlays (0xD900-0xFAEB, build/m4ovl.bin: the 12-entry table 0xD900, room 0xD960, level start 0xDD0A, then events, text, guard-leave, guard-enter, save, keys, rare (each 545 bytes later than before M8a part 9); the cheat build to 0xFC89) | 1.3 KB (0xFAEC-0xFFFF; the cheat build 0.9 KB) |

Title and cutscene art (title 215 KB, story/cutscene 115 KB) is for the presentation program PRES (M7): per the
decision of 2026-10-30 (docs/m7-design.md section 9) it is read from the floppy (POP800.PRS) per scene into PRES's own
main RAM; the RAM disk only gets what the swap needs (the launcher 2.2 KB, the game image 24 KB, the handoff block).
The scratch areas (the shadow room page 1 0x0000-0x7CFF, the torch cache page 6 0x0000-0x287F) are free for PRES.

Pages 8 and up (a 1 MB or 16 MB RAM disk; M8a part 9, docs/ramdisk-tiers.md "As built: step 1"): the frame store, written
only by the level-start overlay's fill (src/m4/fstore.asm) on a RAM disk of 1 MB and more (HO_RDTOP >= 15); on 512 KB
they are not written (page 8 would alias page 0):

| Page | Content |
|---|---|
| 8 0x0000-0x75BF | the key table: 471 ids x 16 variants x 4 bytes (id = the kid's frame 0-219, the sword's 220 + frame, 255-470 reserved for the six guard sets of step 2), slot id * 64 + (mirror * 8 + shift) * 4 = the entry's page (0 = not stored), address hi, lo, 0 |
| 8 0x7700-0x7704 | the marker: the build id (tools/fstore.py: a CRC of the masks, the kid and sword packs and directories, the kernel's sources and the fill), the class filled (1, 2); written last; cleared by the boot (src/boot/boot.asm), so every boot fills |
| 8 0x7800- and 9-14 | class 1 (every card from 1 MB): 891 entries, 409,512 bytes, to page 14 0xC2F4; an entry = ow, h, the byte count (2), the cell buffer as spr_fetch leaves it ((w + 1) * 4 * h bytes); none crosses a page; the order and addresses are tools/fstore.py's (build/assets/fstore_keys.txt) |
| 14 0xC2F4-15 | free on 1 MB (81.6 KB: the level's guard set, step 2; no room cache on 1 MB, the user's decision of 2026-11-03) |
| 14 0xC2F4-27 0x6130 | class 2 (from rd_top 29, i.e. 2 MB and more; on 16 MB): 1,262 more entries, 823,312 bytes |
| 28-255 | free (16 MB) |

All six guard sets are resident (tests/m4_game.py GUARD_SETS; the floppy loader loads them all too); loading only the
level's set (at most 20.4 KB) would need a per-level load from floppy and would free ~90 KB of pages 6-7 for the
visited-room cache.

## Floppy boot (M5, 2026-10-30; M7 launcher)

build/pop800.dsk (`make`; tools/mkgamedisk.py) is an FSMZ disk: the IPLPRO bootstrap is the loader src/boot/boot.asm
(block 48, 10 blocks), the data stream is in the files POP800.D1 (block 58), POP800.D2 (block 292) and POP800.D3 (block
528), 495 blocks (2026-11-01: the overlays grew); the saved game is POP800.SAV (block 553, 1 block, below); the presentation
program is POP800.PRS (block 554, 255 blocks, full) with POP800.PR2 (block 809, 202 blocks, the next blocks on the disk): 457
blocks: the index block and the entries of M7 step 8 (docs/m7-design.md §17). 269 of the 1280 blocks are free.
The ROM IPL loads the loader to 0x1200, moves it to 0xB000 and starts it. While it runs (the game is not there yet):

| Range | Use |
|---|---|
| 0x0000-0x11FF | zeroed at the start (the game's variables: SCRIPT_PTR 0x0876 = 0 means no harness script) |
| 0x2000-0x5FFF | OUTBUF: a decompressed RAM-disk record (16 KB at most), copied to the RAM disk with OTIR |
| 0x6000-0x9FFF | INBUF1: a RAM-disk record's compressed payload |
| 0x8000-0x9FFF | INBUF2: a main-RAM record's payload (8 KB at most; these records decompress in place, last) |
| 0xA000-0xAFFF | TRKBUF: the sectors of one track (multi-sector reads) |
| 0xB000-0xB93B | the loader / launcher (2,278 bytes of code, font and messages; the WD2793 code src/boot/fdc.asm; at most LN_MAX = 3 KB) and its variables |
| 0xBF00-0xBFFF | its stack (SP 0xC000) |

VRAM and the CG ROM are mapped only while it draws (title, progress bar). After the RAM-disk probe it copies its own
image to the RAM disk (page 0 0xF000: the launcher). Then it loads the RAM-disk records: everything tests/m4_game.py
setup() writes (pages 0-7 as in the table above, the gaps untouched) and the game's compressed image (page 3 0xA000:
the program's main-RAM records, 0x1200-0x7FFF and 0xC000-block2_end of build/m4game.bin, PZ, as a record stream).
It writes the handoff block "title" (page 5 0x3AC0) and continues as the launcher.

### The launcher and the swaps (M7 step 1, src/boot/launch.inc)

Two programs take turns in main RAM: the GAME and PRES (src/pres/pres.asm, the presentation program).
A program hands over by writing the 16-byte handoff block (format in launch.inc: magic "P7", action, level, rem_min,
rem_tick, hitp_beg_lev, options, K_TICK, last_loose, result, is_guard_notice, roomleave_result) to page 5 0x3AC0 and jumping to the launcher's entry
LN_LAUNCH (0xB003); the game first copies the launcher (3 KB from page 0 0xF000) to 0xB000, from the level-start
overlay (W2). The launcher zeroes 0x0000-0x11FF, puts the block at HO_MAIN (0x02A0) and starts:
- the GAME (action 0x00 play level n): its image is decompressed from the RAM disk (no floppy), ~62 frames (1.2 s:
  the PZ decoder needs ~100 T a byte on this code), then `start`; game_init (the W2 overlay) takes the level, the
  time and the hit points from HO_MAIN when its magic is there (the harness never writes it: the harness path is
  unchanged);
- PRES (actions 0x10 title, 0x11 time expired, 0x12 ending, 0x13 cutscene before level n): entry 0 of POP800.PRS from
  the floppy (12 frames in the emulator; a real drive ~0.5 s more), started at 0x2000. PRES calls the resident
  launcher (LN_PRS_LOAD, 0xB006) to load its scenes (POP800.PRS entries: main-RAM records only).
While PRES runs, 0x8000-0xBFFF belong to the launcher (its buffers INBUF2 0x8000, TRKBUF 0xA000, its image and stack).
The game hands over at a level change to a level with a cutscene (2, 4, 6, 8, 9, 12; not at a restart or the level's
first start: SDLPoP play_level) and at GAME_OVER (time expired, the end, the death text ran out). The launcher leaves
the RAM disk at page 0, address 0 before the game starts (nothing in the game depends on it: every access seeks).
Stream and record format: tools/mkgamedisk.py; compression (PZ, ~27% of the raw size): tools/pzpack.py.
Each track run is read starting at the sector under the head (fd_read_rot: READ ADDRESS, then the run's sectors from
the next one on and the skipped ones last, without the 15 ms settle delay): ~1 turn per track instead of ~1.5 on a real
drive (estimated ~3 s of the boot; the emulator has no rotation).

## The saved game (M5, 2026-10-30)

POP800.SAV: one FSMZ block preallocated by tools/mkgamedisk.py (256 zero bytes = no save; DIR lists it, the free map
counts it). Ctrl+G during play on levels 3-13 (SDLPoP's original rule) runs the save overlay at the tick start (SDLPoP's
process_key point, before the tick's logic): it finds the file in the directory (blocks 16-23), writes the block with
WD2793 WRITE SECTOR (A4h, inverted bus as for reads), reads it back and compares, stops the motor and sets the 24-tick
bottom text GAME SAVED or UNABLE TO SAVE GAME (any error: no drive, no file, write protect, a mismatch). The game is
paused (interrupts off) while the drive works. The record (bytes 14-255 zero):

| Offset | Size | Content |
|---|---|---|
| 0 | 4 | "POP8" |
| 4 | 1 | version 1 |
| 5 | 2 | rem_min (SDLPoP's PRINCE.SAV fields as 16-bit words from here) |
| 7 | 2 | rem_tick |
| 9 | 2 | current level |
| 11 | 2 | hitp_beg_lev |
| 13 | 1 | checksum: bytes 0-13 sum to 0 (mod 256) |

load_saved (the stub in src/m4/ovl.asm, for M7's Ctrl+L on the title) reads it back: A = 0 and level_number, REM_MIN,
REM_TICK, HITP_BEG_LEV set; A = 1 no valid save (magic, version, checksum or a value out of range: nothing changed);
A = 2 disk error. tests/m5_save.py checks both directions and the image file.

Sound model (M7 step 2, 2026-10-30): src/m4/sound.asm (block 2: snd_play / snd_next / snd_stop, the priority table,
the kid and guard call sites' sound parts) and src/m4/sndobj.asm (main code: the traps' sound parts), state SND at
0x03C1. The IM2 table shrank to its one vector (0xFE00-0xFE01): 0xFE02-0xFF00 free for the player's buffers. Free
resident code now: main 12, low 53, block 2 416 bytes (481); the player (M7 step 3, ~300 bytes) goes into block 2. The
op-list reclaim is still available. Details: docs/m7-design.md section 11.

PSG player (M7 step 3, 2026-10-30): src/m4/psg.asm in block 2 (167 bytes: snd_isr, the tail of game.asm's VBLN isr
(`jp snd_isr`), psg_mute, snd_halt, snd_start, snd_playing); its state SP_VARS at 0x03C8, the effect buffer 0x0148-0x01FF,
the music buffer 0xFE02-0xFF00; the sound bank in RAM-disk page 1 at 0xE000 (written by the boot and by
tests/m4_game.py setup). All of it is outside 0x1000-0x1FFF and 0x8000-0x9FFF (mapped while blit runs, when the ISR may
come). Main code: isr's tail became a jump (-2 bytes), irq_init calls snd_halt (+3; room.asm's page padding took the
difference: end_of_code stays 0x7BF4, 12 bytes free). Free resident code now: main 12, low 53, block 2 249 bytes; the
op-list reclaim was not needed. Details: docs/m7-design.md section 12.

Music (M7 step 4, 2026-10-31): the MIDI arranged for the PSG (tools/midi2psg.py) in a new stream format with per-channel
envelopes in the ISR; every stream (effects too) plays through the ring 0xFE02-0xFEFF, which snd_fill (psg.asm, main
code: from snd_start and once a tick from snd_playing) refills from the bank. The RAM-disk bank shrank from 3,703 to
2,328 bytes with all in-game music complete; the presentation's music (8,202 bytes, the ending 5,106) is in
build/assets/sound_pres.bin for PRES (POP800.PRS), not in the RAM disk. The effect buffer 0x0148-0x01FF is free again.
psg.asm 167 -> 321 bytes: block 2 has 91 bytes free (block2_end 0xEBA5); main 12, low 53 unchanged; the op-list
reclaim was not needed. Details: docs/m7-design.md section 13.

Waits on sound (M7 step 5, 2026-10-31): sound.asm's waits and the ticks model needed ~200 bytes of block 2 (91 free):
the guard snapshot G_SNAP and the guard records and globals (113 bytes of runtime-only data, same layout) moved from
block 2 to low RAM 0x0148-0x01B7. The ticks model's lengths (100 bytes) live at 0x9B88 (behind the VRAM window, read
only outside blit), copied by game_init from the level-start overlay; its state SND_LEFT, NEED_L1M, END_OVER at
0x03DD-0x03DF. The op-list sizing gives nothing: the largest rooms need back 185 / 192, fore 126 / 128, mid 1 / 8
records (tools/popdata.py over levels 0-14). Main code +3 bytes (kid.asm: the crouch check; the death timer's call and
game.asm's level change got shorter). Free resident code now: main 9, low 53, block 2 9 bytes; free runtime data:
0x01B8-0x01FF, 0x9BEC-0x9BFF, 0x9F90-0x9FFF. Details: docs/m7-design.md section 14.

Title in PRES (M7 step 6, 2026-10-31): PRES (3,638 bytes at 0x2000) loads POP800.PRS entry 2 (the presentation's
sound bank, copied to the torch cache, page 6 0x0000-0x287F) and entry 3 (the title art: 14 PZ bands stored at
0x1200-0x1FFF, 0x2E36-0x7FFF, 0xDF40-0xEBF6, 0xEC00-0xFBFF, unpacked one at a time into DBUF 0xC000-0xDF3F) and composes
its screens in the shadow room's place (page 1 0x0000-0x7CFF, row-interleaved planes). Both RAM-disk areas are scratch
the game rebuilds (the shadow rows 192-199 keep PRES's bytes). POP800.PRS is 144 blocks (index, PRES, the placeholder
scene, the sound bank, the title art). No game memory changed. Details: docs/m7-design.md section 15.

Presentation music (M7 step 11, 2026-11-01): PRES plays the Master System soundtrack's pieces from three banks (tools/presbank.py:
build/assets/sound_pres.bin A 10,121 bytes, _b 9,938, _c 7,631; POP800.PRS entries PRS_SOUND, PRS_SND_B 21, PRS_SND_C 22), each
copied whole to the torch cache (page 6 0x0000-0x287F, as before) when a scene needs it: A at the title's start and for the
cutscenes / time-out / ending, B at title step h, C before step j. The pieces loop through psg.asm's loop command (0xE8 lo hi
after a stream, read by snd_fill: +36 bytes of block 2, block2_end 0xEAED -> 0xEB11, 239 free; the ISR unchanged). The in-game
bank build/assets/sound.bin is unchanged (byte-identical; note that it is reproducible only with midi2psg's level
curves: a copy without them gives a different arrangement; since 2026-11-02 they are committed, assets/opl/levels.json). Details: docs/m7-design.md section 19.

Level cutscenes in PRES (M7 step 7, 2026-10-31): the engine src/pres/cut.asm is assembled after PRES's own image
(end_of_pres 0x2E61) but travels in POP800.PRS's room entry (PRS_CROOM: the engine 0x2E61-0x3ED9, the room's PZ bands, the
common sprites at 0x1200-0x1FFF and 0xDF40-0xF36F); a scene's entry puts its pre-shifted sprites at 0x3EDA-0x7FFF; the
composed row RB is 0xA000-0xA3FF (the launcher's track buffer, free once the loads are done). The room is in the shadow
room's place (page 1, as the title's screens); play_seq reads logic.bin in page 6 in place (read only). POP800.PRS is 255
blocks (full); POP800.PR2 (step 8) must be the next blocks on the disk. No game memory changed. Details: docs/m7-design.md
section 16.

Intro story, time-out and ending in PRES (M7 step 8, 2026-10-31): the placeholder stubs and the font are gone: PRES 3,465
bytes (end_of_pres 0x2D89), the engine 4,935 bytes (to end_of_cut 0x40D0, in the room entry). New in main RAM during a
scene: cut_spr at 0xF400-0xFBFF (8 bytes a sprite); pv_scene's 115 sprites as PZ blocks (28.5 KB) in end_of_cut-0x7FFF,
DBUF and 0x8000-0x9F3F (read only while VRAM is not mapped; the launcher's INBUF2 there: its part is loaded at DBUF and
copied up, and every record of that entry after the copy is stored), each unpacked when drawn into its slot's buffer
0xA400 / 0xA940 (RB stays 0xA000-0xA3FF). The title's art entries are per image group at fixed places, the four story texts
share one. Nothing of it in the RAM disk beyond the old scratch (page 1 0x0000-0x7CFF, page 6 0x0000-0x287F). The cutscene palette:
group 1, PLT0 black: MZ 4 = EGA attribute 0 (the flash), MZ 0 = EGA 13; PRES restores group 0 identity before the title
and the game. No game memory changed. Details: docs/m7-design.md §17.

Keys (M7 step 10, 2026-10-31): room made by moving guard.asm's constant tables (88 bytes) to 0x9F90 (game_init copies them) and
the key handling out of resident code. Resident now: key_scan (block 2, 33 bytes), two stubs (main), the script's key prefix in
get_controls, one call in kid.asm. Free resident code: main 6, low 53, block 2 61 bytes. New overlay OVL_KEYS (id 7, the last of
OVL_MAX 8: the next overlay needs OVL_MAX raised and the table's images moved; the area has 0x2AA bytes free). With CHEATS=1
(`make cheats`: build/cheat): key_scan + 13 bytes (block 2 48 free), the main loop's blind check + 8 bytes that disappear in
room.asm's page alignment at 0x4100 (main end unchanged). Details: docs/m7-design.md section 18.

M8a part 2 (2026-10-31, docs/perf.md): the gate change detection went into the low block (view.asm vrd_gate, 49 bytes) and the gate's
one-pass redraw into block 2 (src/m4/gate.asm gate_redraw, 65 bytes, 76 after the 2026-11-01 fix of the own-room gate case, docs/perf.md;
room.asm only got the label lrl_lr); the time-exact pacing prototype into the main block (game.asm: mode check, clock, skip decision,
~100 bytes; PACE_MODE byte 0x2161). Room was made
without moving anything: `jp` -> `jr` where the target is in range, in code that runs at most a few times a tick (block 2: 17 jumps in
guard.asm, overlay.asm, tcache.asm, and 24 more on 2026-11-01 for the gate fix: guard.asm's sword-fight and autocontrol dispatch 7,
overlay.asm's overlay tile classification ob_* 17; main: 100 jumps in kid.asm and objects.asm, none in the tile-lookup, play_seq or
piece-laying loops; a taken jr costs 2 T more than a jp, ~200 T a tick at most). Free resident code now: main 16, low 4, block 2 26
bytes; the cheat build (CHEATS=1: key_scan + 13 bytes in block 2) fits with 13 to spare. Runtime data: the pacing variables 0x01B8-0x01BC.
`make pace` builds the mode-1 game and disk in build/pace (as `make cheats` does for the cheats): the image differs from the release
in the PACE_MODE byte only.

Memory reclaim (2026-11-01, before the M8a drawing work): 896 bytes of main code, 111 of the low block and 249 of block 2 were
freed with no change in behaviour (the pixel sets, the logic traces and tools/perfcheck.py are the gates; the table below is
the resident code moved, net of the stubs that replaced it). Free resident code now: main 912 (end_of_code 0x7870), low 115
(end_of_low 0x1F8D), block 2 275 bytes (block2_end 0xEAED; the cheat build 904 / 115 / 262). The overlay table grew to 12
entries (OVL_MAX) and the whole overlay area moved from page 6 (0xE300-0xFFFF, which would have been full) to page 7 at
0xD900-0xF8C9 (1.8 KB free; the cheat build 1.4 KB): page 6 0xE280-0xFFFF is free again. tools/mkgamedisk.py and the harness
take the place from the symbols. Because PRES's cutscene and title art kept clear of the game's block 2 end .. 0xEBFF only for
tests/m5_boot.py's main-RAM comparison, that comparison now ends at block2_end and the art may use 0xDF40-0xFBFF whole
(tools/cutart.py, mkgamedisk.py title_entries): the PRS entries' addresses changed, PRES's code did not.

| Moved | Bytes freed | Where it went | Why it is cold (tools/profile.py over all 46 m4/m6/m5 scripts) |
|---|---:|---|---|
| the start-up: start's prologue, video_init, irq_init (game.asm), tables_init (gfx.asm -> src/m1/tables.asm), pr_build + pr_start's check (room.asm -> src/m3/prbuild.asm), sprite_init (sprite.asm), sword_init (overlay.asm) | main 194 + 92, low 42, block 2 82 | the level-start overlay (W2): game_start in src/m4/gstart.asm, one stub in ovl.asm; `start` is 16 bytes (di, sp, the bank ports, call game_start) | runs once per program start (0 calls in any tick); PR_TAB is built at the start instead of at the first room draw (the same ~10 frames, before level_ready: the test programs keep pr_start's check, GAME_OVL) |
| trigger_button, do_trigger_list, trigger_gate, died_on_button (objects.asm) | main 305 | the events overlay (W1), two stubs | a plate pressed: 5 call sites in 46 scripts plus check_press's jump every tick while the kid stands on a plate (the overlay stays loaded then); lr_special's level-door case goes through the resident tail (below) |
| hpd_go .. hp_or and the strips' variables (game.asm) | main 222 | the rare overlay (W1, new: src/m4/hpstrip.asm), the variables HP_VARS 0x01C0, stubs hp_redraw (game.asm, hp_draw falls into it) and hp_strip (ovl.asm, for ghp_draw) | hp_strip 124 calls in 46 scripts (a level start, a hit, a potion, a guard's hit) |
| get_item, do_pickup (objects.asm) | main 94 | the rare overlay (src/m4/rare.asm), one stub | 16 calls in 8 scripts (an item taken) |
| chomped (kid2.asm) | low 71 | the rare overlay (rare.asm), the stub in kid2.asm (GAME_OVL; m4test includes rare.asm) | 8 calls in 2 scripts (a chomper death) |
| lr_special's level specials (guard.asm) | block 2 167 | the guard-enter overlay (genter.asm lrs_body, stub in ovl.asm); guard.asm keeps a 24-byte tail that calls trigger_button when lrs_body returns CY (a W1 overlay cannot call another: the events overlay) and goto_other_room | once per room change, in the tick whose room_entered loads the same overlay (no extra load) |

Not moved, measured and judged too warm for a W1 overlay (a load is ~0.3 frames): start_chompers (every fall, landing and
row change), hurt_by_sword (every sword hit), the kid's jump and grab helpers (every jump), flames_build (after every room
draw: W1 holds the room overlay then, 86 bytes free), the loose floor code (every shaking floor). goto_other_room stays
resident because the guard-leave (W1) and level-start (W2) overlays call it.
