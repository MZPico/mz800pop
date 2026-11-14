# Memory map (M4 game + M6 guard logic and drawing, code overlays, M5 level-event logic and drawing, save, M7 launcher, sound model, PSG player and music, waits on sound, PRES title and cutscenes, keys, M8a part 2 gate redraw and pacing, the memory reclaims of 2026-11-01 and M8a part 19)

Baseline: MZ-800 with the 32 KB VRAM extension and a 512 KB paged RAM disk (decided 2026-10-27; swapping
level art per level from floppy, to fit 256 KB, is a late option only). Sources of truth: the `equ`s in
src/m1/gfx.asm, src/m3/room.asm, src/m4/*.asm and `build/m4game.sym`.

## Main RAM

The VRAM window (0x8000-0x9FFF) and CG-ROM (0x1000-0x1FFF) are mapped only inside `blit`; everywhere
else all 64 KB are RAM. Code in the low block must never run inside `blit`.

| Range | Size | Content |
|---|---|---|
| 0x0000-0x00FF | 256 | the guard's sword image buffer (GSWBUF; largest sword image 256 bytes in the kernel's format) |
| 0x0100-0x0123 | 36 | torch cache valid flags (TC_VALID, tcache.asm: FLM_MAX 4 flames x 9 frames; 72 for 8 flames until M8a part 17), runtime only |
| 0x0124-0x012B | 8 | flm_rec (view.asm, M8a part 17: moved from the low code block): the registered torch flames' op records (FLM_MAX words), runtime only |
| 0x012C-0x0135 | 10 | PR_BUF (room.asm, M8a part 19): the wall pattern's seed row, read from PR_TAB in the RAM disk by pr_start (the seed's 10 draws mod 140, then prandom takes them in order), runtime only; 0x0136-0x0147 free |
| 0x0148-0x01B7 | 112 | the guard trace snapshot G_SNAP (30) and the guard records and globals gv_start..gv_end (KID_REC, GUARD_REC, OPP_REC, CHAR_SAVE, guardhp ... roomleave_result; src/m4/guard.asm equs, moved from block 2 in M7 step 5), runtime only (guard_init zeroes gv_start..gv_end) |
| 0x01B8-0x01BC | 5 | M8a part 2 pacing (game.asm): NEXT_TICK (the frame the next tick is due, mode 1), SKIP_TICK, SKIP_RUN, SKIPPED (the last tick's drawing was skipped: the tile snapshot is kept); mode 0 (the release) never writes them; runtime only |
| 0x01C0-0x01C9 | 10 | HP_VARS: the hit point strips' variables (game.asm equs hp_i .. hp_pf; the code is the rare overlay, src/m4/hpstrip.asm; overlay.asm ghp_draw sets hp_n, hp_nf, hp_base, hp_pf before the overlay is loaded), runtime only |
| 0x01CA-0x01FC | 51 | M8a part 7 (people2.asm st_look): ST_KEY, each character slot's look in the last drawn tick (slots 0, 1, 6, 2, 3: SD_DX .. SD_COMPOSE + 1 and PP_XD, 10 bytes each), ST_OK (the last tick had overlay ops, a splash, or a room was drawn after it: sprite_forget); runtime only |
| 0x01BD-0x01BF, 0x01FD-0x01FF | 6 | free (runtime data) |
| 0x0200-0x027F | 128 | run_rect's recorded ops (RR_PTRS, 64 pointers) |
| 0x0280-0x029E | 31 | level-event state EV (objects.asm: next level, time left, bottom text and flash timers, feather fall, upside down, mirror, shadow script, checkpoint, restart / level switch / game over flags, keys (KEYS: bit 0 Ctrl+A, bit 2 Ctrl+G, bits 3-7 a key code, src/m4/keys.asm); for the drawing TEXT_GEN, FLASH_NOW, MI_JUMPED, TXT_GEN_SHOWN, the save overlay's text TEXT_MSG / TEXT_MSG_GEN); set by game_init, runtime only |
| 0x029F | 1 | HO_RDSPD_MAIN (src/boot/launch.inc): the RAM disk's read speed as the boot measured it (src/boot/rdspeed.asm, docs/ramdisk-tiers.md section 1: the game pattern's mean, clocks/byte x 5, 105 = 21.0 = no wait states, 255 = 51.0 or more); set by the launcher at every start after zeroing low RAM; 0 in the harness; read by nothing yet (PLAN item 50) |
| 0x02A0-0x02AF | 16 | HO_MAIN: the launcher's copy of the handoff block (src/boot/launch.inc; magic "P7" = the game was started by the launcher, M7); zeroed by the launcher otherwise, never written by the harness except KEY_OPT 0x02A8 = HO_OPTIONS: bit 0 the sound off (Ctrl+S, M7 step 10; goes through PRES with the block), bit 1 blind (CHEATS only); 0x02AF = HO_RDTOP: the RAM disk's last page as the boot's probe found it (7 = 512 KB, 15 = 1 MB, 31 = 2 MB, 63 = 4 MB, 127 = 8 MB, 255 = 16 MB; set by the launcher at every start; 0 in the harness = the 512 KB layout; read by nothing yet, docs/ramdisk-tiers.md) |
| 0x02B0-0x02B4 | 5 | m4test only: N_SNAP, the 'N' trace snapshot (snd_snap: queued, started, playing, stops) and its counter |
| 0x02C0-0x02DB | 28 | m4test only: S_SNAP, the 'S' trace snapshot (state_snap) and its counter |
| 0x0300-0x03C0 | 193 | M5 drawing (overlay.asm, fx.asm): spr_xor's row SXT 0x0300 (73), the descriptors of slot 5 (the guard's splash when both are hurt) SPR_SP2 0x0350 and slot 6 (the mirror image) SPR_MI 0x0368, the sort keys PP_KEYS 0x0380 (7, slot 6 first), PP_ORD, per slot PP_XD (XOR offset) and PP_CL (left clip), PC_SAVE, and single variables to PP_ANYFX 0x03C0 (FL_SHOWN 0x03B8: the flash shown this tick, read by tests/m4_game.py; UP_SHOWN, TXT_VIS); runtime only |
| 0x03C1-0x03C7 | 7 | SND: the sound model (src/m4/sound.asm: next_sound, current_sound, sound 15's interruptible flag, the stop counter, is_screaming, trigger_button's sound flag, the end-music flag; game_init clears it), runtime only |
| 0x03C8-0x03DC | 21 | SP_VARS: the PSG player (src/m4/psg.asm: SP_WAIT frames until the next group (0 = no stream), SP_PTR the ring's read pointer, MF_SRC / MF_LEFT / MF_W the refill (RAM-disk address, bytes left, the ring's write position), SND_MODE 0 silent / 1 hybrid (the launched game: game_init_h) / 2 ticks / 3 live (tests; sound.asm header), ENV 0x03D1 the four envelopes (attenuation, counter, period)); irq_init stops the player, runtime only |
| 0x03DD-0x03DF | 3 | the ticks sound model (src/m4/sound.asm, M7 step 5): SND_LEFT (ticks the playing sound has left), NEED_L1M (the level 1 music crouch), END_OVER (hybrid: the level end's clock stopped); game_init clears them, runtime only |
| 0x0400-0x04EF | 240 | slice extents (SL_Y0, SL_Y1) |
| 0x0500-0x06FF | 512 | M8a part 25: the low code, part 1 (src/m4/ovl_low.asm, frmlow.asm: the lazy shadow, restore_shadow's and shadow_write's hooks; 485 bytes, 0x06E5-0x06FF free); copied in by game_start from RAM-disk page 4 0xFE00 (see "The low code" below) |
| 0x0700-0x076D | 110 | M8a part 25: FRM_TAB (src/m4/spike.asm, from 0x09DB: 4 objects x 20 bytes: rect, valid pictures and complete pictures, tag + 1, slots, the lazy shadow's state and slot, the complete picture's slot; FRM_NEXT, FRM_CNEXT) and frmlow.asm's variables LC_VARS (to 0x076D); runtime only; 0x076E-0x077F free |
| 0x0780-0x07D5 | 86 | sprite descriptors (overlay.asm): the guard's sword SPR_GS 0x0780, the guard SPR_G 0x0798, the hurt splash SPR_SP 0x07B0; the draw list PP_DL 0x07C8 (count + 13 slots: the 7 people slots and, since the falling-floor order fix, the 6 falling floors drawn this tick; 0x07D6-0x07DF free) |
| 0x07E0-0x07EF | 16 | SEQBUF: the sequence window play_seq reads |
| 0x0800-0x08FF | 256 | VARS: frame counter, VBLN line latch, input, compose rect, falling-floor rects, dirty list |
| 0x0900-0x09A5 | 166 | RV: room renderer state (RR_CB0, RR_NC at RV + 164, 165) |
| 0x09A6-0x09B3 | 14 | M8a part 15: the frames overlay's step variables (src/m4/frames.asm fs_kind .. fs_id), runtime only |
| 0x09B4-0x09DA | 39 | people drawing (overlay.asm): the characters' dirty rects PP_KU/PP_GU, the guard's hit point icon GHP_PAT and strip state GHP_M/GHP_SHOWN, chunk state (0x09A4-0x09B3 free until M8a part 15, the keys moved to 0x0380) |
| 0x09DB-0x09FF | 37 | free (FRM_TAB until M8a part 25: it moved to 0x0700) |
| 0x0A00-0x0AFF | 256 | KV: Char (the character being played: the Kid between ticks), controls, geometry, collisions, PP_SAVE (0x0AB0: Char while the people are placed), kid trace snapshot, pending chunk list, clip_char of the character being placed |
| 0x0B00-0x0BFF | 256 | the kid's sprite descriptor SPR_A, trap state (OV), TROBS (30), MOBS (14) |
| 0x0C00-0x0DFF | 512 | MASKBUF (piece laying: since M8a part 20 a masked piece's inverted mask rows at its compose rows' offsets, MASKBUF + (dst & 0x1FF), anywhere in the 512 bytes; must stay 512-byte aligned (gfx.asm guard); also scratch for pc_col's clip column and the text overlay's bitmap) |
| 0x0E00-0x0FFF | 512 | M8a part 25: the low code, part 2 (src/m4/ovl_low2.asm, frmlow2.asm: a chopper's or spike's step, the complete pictures' direct copy and save; 483 bytes, 0x0FE3-0x0FFF free); copied in by game_start from RAM-disk page 1 0xDE18 (free since M8a part 20: DATABUF) |
| 0x1000-0x119B | 412 | the kid's sword image buffer, its sprite descriptor SPR_S (ROM monitor work area: runtime data only) |
| 0x1200-0x1FFF | 3.5 KB | low code block (kid2.asm, view.asm, sprite.asm, evres.asm, fx.asm; end_of_low 0x1FFA: 6 bytes free (known pixel mismatches, 2026-11-11: +29, view.asm vs_entry's entry 53, the room below-left's column 9, and its run in vs_runs; falling-floor order: +4: obj_chunk's call of mob_lay gone (-3), mobs_visible's top clip +7 (a floor at ybottom -1 no longer kept with no rows; a floor coming in from above gets at least rows 0-2); M8a part 27: +6, obj_chunk clears the lc_sv mark when tc_try takes the chunk (oc_tcx); M8a part 25: +4, obj_chunk asks the low code's lc_chunk first; M8a part 19: -24, sprite_forget into the room and the level-start overlays (src/m4/sprforget.inc); M8a part 18: -16, obj_chunk's falling-floor loop became a call to mob_lay in main (-26), view.asm loose_pic +9, mobs_visible's top clip +1; M8a part 17: +15 used: sprite.asm td_beam +36 (the direct copy's beam wait), obj_chunk asks the torch cache before picking a buffer, flm_rec moved to low RAM 0x0124 -8, three jumps in flames_build relative; M8a part 16: -4, flames_build's exclusivity test became a call to fb_over in main; M8a part 8's run-wise tile snapshot: +81, its 106-byte pointer table moved to 0xF58B; M8a part 9's fs_on jump in char_fetch: +3; part 11's spike case in vrd_one: +5; part 13: -4, vrd_one sends every type but the torches, gates and potions to anim_redraw in main; part 14: +6, vrd_cht sends a button's press or release to btn_redraw)) |
| 0x2000-0x7BFF | 23 KB | main code (people2.asm after objects.asm, then sndobj.asm, fslook.asm, spike.asm; end_of_code 0x7B1B: 229 bytes free below W1 (known pixel mismatches, 2026-11-11: +18, kid.asm xpos_in_drawn_room's room_BL / room_BR as load_room_links makes them (+7) and dead_button, the button after the death taken at the tick's start (+33; the old WANT_RESTART code in kid.asm and game.asm -22); 2026-11-10, the level door's sound: +51, sndobj.asm snd_again; M8a part 28: +17, spike.asm loose_redraw's call of the loose-floor overlay and its stub loose_fast (ovl.asm); falling-floor order: +354: people2.asm mob_place (the floors' tiles and the right tiles' overlay marks), mob_until (the floors' places in the drawing order), mob_pch (a floor laid in its place) and the shorter mob_meet, -48 the old mob_lay; ov_order moved here from overlay.asm (10); part 27: +115: room.asm shift_variant's wall-mark guess +63, load_curr_next +50 (room_ops' sweeps: the left tile is the previous current one), yr_merge's inline clamps +12, add_op in registers with its own 5-byte directory read -10; part 25: +15: the hooks in gfx.asm restore_shadow (call, jp) and shadow_write (call), frm_drop's FE_CMASK, frm_reset split into frm_clr; part 24: +406: buttons.asm trigger_button, do_trigger_list, trigger_gate resident (251; their copies in the gate, door and events overlays and the stub went), src/m4/csres.asm cs_scan and its variables (123; shared by the gate and door overlays), room.asm run_rect split into rr_lays / rr_layc (~30: a gate's contact band laid into its own compose rect); part 23: +130: kid.asm get_row_collision_data as a row walker +114 (its data and variables, 12 bytes, went to the head of block 2: src/m4/collpad.inc), k_get_tile's in-room path +33, check_collisions' bump loop by pointers -7, get_tile_div_mod's page-aligned tables -10; part 21: -17: kid.asm get_row_collision_data's second k_get_tile a column and its push / pop gone (-6), move_coll_to_prev's six clear loops one loop of three rows, two bytes a djnz (-23), room.asm pr_slow's power-of-two path +12; part 20: -1,021: the piece laying's row chains (gfx.asm lmx_ent, lr_ent, lre_ent, lle_ent, the plane loops and the setup in registers, ~330 bytes) replaced the cmx / cm1 / inr chains of kernel_gen.inc (-798), the general copy path lpc_gen / lp_merge (dead), lp_block and the INIR copy rows; part 19: -58: room_checksum (53, objects.asm), its call and store in kid.asm (6) and game.asm's trace_cksum (9) went to the m4test build only (the game's harness computes the checksum: tests/m4_test.py level_cksum), game.asm's calls of room_drawn and sprite_forget (6) into the room overlay, room.asm pr_start +16 (the seed's row from the RAM disk); part 18: +72, people2.asm mob_lay / mob_meet 48 (a falling floor laid only in the chunks it touches; tc_try asks per chunk), spike.asm loose_redraw 19 and its case in anim_redraw 5; part 17: 15 bytes less, room.asm op_patch's fore path no longer bumps fore_gen; part 16: +33, spike.asm fb_over: a flame with a gate's base after it is exclusive; part 15: +97: frm_drop, frm_reset, the frames stub frm_fast and the calls in chomp_redraw / spike_redraw; M8a part 7's st_look: +169; part 8's spr_draw and restore_shadow row loops: +42; part 9's frame store lookup fs_look: +95; part 11's spike_redraw: +60; part 12's guard-frame lookup in fslook.asm: +11; part 13's anim_redraw (choppers, the sword) in spike.asm: +77, op_patch's fore-op path in room.asm: +23; part 14: +76: the stubs gate_fast, door_fast, btn_fast and btn_redraw +45, trigger_button's stub (it picks the copy in W1: the gate, door or events overlay) +10, door_redraw and its case in anim_redraw (spike.asm) +11, the button cache's hook in tile_regen +10; the after-room-draw hook went to block 2 (anires.asm room_drawn), whose 4 bytes in game.asm had moved room.asm's page-aligned op-list table by 29 bytes of padding); PACE_MODE (0x213C) is a byte in game.asm's code: 0 in the release, 1 in `make pace`) |
| 0x7C00-0x7FFF | 1 KB | overlay window W1 (src/m4/ovl.asm): the room overlay (995 bytes, 29 free; M8a part 26: +15, roomfull.asm rf_cell, the cells without run_rect's cover scan; part 25: +5, frm_clr before the draw), the events overlay (737 bytes, 287 free), the guard-leave overlay (342 bytes, 682 free), the guard-enter overlay (943 bytes, 81 free), the keys overlay (469 bytes, 555 free; CHEATS=1 832 bytes, 192 free), the rare overlay (423 bytes, 601 free), the gate overlay (924 bytes, 100 free), the button overlay (821 bytes, 203 free), the door overlay (471 bytes, 553 free) the frames overlay (988 bytes, 36 free; M8a part 25: -32, the hit's slot read and cs_put went to the low code; part 28: its fs_patch moved to src/m4/fspatch.asm, which the loose-floor overlay includes too) or the loose-floor overlay (373 bytes, 651 free; M8a part 28) |
| 0x8000-0x80FF | 256 | bit-reverse table |
| 0x8100-0x81F7 | 248 | room renderer slice tables |
| 0x8200-0x8FFF | 3.5 KB | sprite shift tables (shifts 1-7, lo/hi pages) |
| 0x9000-0x9B87 | 2.9 KB | room op lists (back 192, mid 8, fore 128 records) and tags (M7 step 5 measured the largest rooms of levels 0-14: back 185, fore 126, mid 1 records: no reclaim) |
| 0x9B88-0x9BEB | 100 | the ticks sound model's lengths SND_T12 / SND_T10 (ids 0-49 at 12 and 10 ticks a second; sound.asm, copied by game_init from the level-start overlay; read only by snd_next, never inside blit), runtime only; 0x9BEC-0x9BFF free |
| 0x9C00-0x9F8F | 0.9 KB | temporary op lists (tile regeneration, kid overlays), sprite row buffers |
| 0x9F90-0x9FE7 | 88 | the guards' skill tables and tbl_guard_type (guard.asm GUARD_TABS, moved from block 2 in M7 step 10; copied by game_init from the level-start overlay; never read inside blit), runtime only |
| 0x9FE8-0x9FF7 | 16 | flm_rect (tcache.asm, M8a part 17: moved from block 2): the registered flames' rects (FLM_MAX x 4), runtime only, never read inside blit or tc_direct's copy (VRAM is mapped here then); 0x9FF8-0x9FFF free |
| 0xA000-0xBFFF | 8 KB | COMPOSE_A, COMPOSE_B, SPRBUF_A (kid image), SPRBUF_B (third compose chunk; in a tick with the mirror image (slot 6, at 0xB800) or two hurt splashes (slot 5, at 0xBC80) it holds those images and stays out of the chunk rotation); 0xA000-0xAFFF (COMPOSE_A/B) is also overlay window W2 while a level starts, a bottom text is drawn or the game is saved (the level-start overlay, 2,273 bytes, to 0xA8E0; above it, 0xAA00-0xAFFF = window WF, the fill overlay, 1,453 bytes, loaded by the level-start overlay for the frame store's fills; the text overlay, 1,021 bytes, 3,075 free; the save overlay, 697 bytes, its sector buffer at 0xA700 and the directory buffer 0xA800-0xAFFF) |
| 0xC000-0xEBFF | 11 KB | tables block (tables.inc; the kid width and guard size tables moved to logic.bin) + overlay.asm (the people on screen: objects, overlays, order, guard hit points), tcache.asm, rcache.asm, guard.asm (code ~5.1 KB, then its harness option blocks guard_opts, ev_opts; G_SNAP and the records/globals are in low RAM 0x0148 since M7 step 5; addresses in build/m4game.sym; the room-change parts are W1 overlays: src/m4/gleave.asm, genter.asm), sound.asm (M7: the sound model and the waits on sound, ~640 bytes), psg.asm (M7: the PSG player, its ISR part with the envelopes, the ring refill; 321 bytes), keyres.asm (M7 step 10: key_scan), gate.asm (M8a part 2: gate_redraw, 76 bytes; part 14: +4, the animation overlay first), anires.asm (M8a part 14: cs_get, cs_put, dirty_hook, room_drawn, the button cache's validity, 199 bytes); block2_end 0xEBF3: 13 bytes free, 0 in the cheat build (falling-floor order: +1: overlay.asm's calls of mob_place and mob_until and people_chunk's jump to mob_pch +11, ov_order moved to people2.asm -10; M8a part 23: +12, src/m4/collpad.inc at its head: get_row_collision_data's data and variables, exactly the bytes that put tables.inc's tile_div_tbl on 0xC400 (page-aligned for get_tile_div_mod; the tables' order and distances unchanged); M8a part 19: -7, anires.asm room_drawn into the room overlay's rf_game; M8a part 17: 5 bytes less: tcache.asm tc_direct, the RAM disk straight into VRAM, replaced tc_hit's compose-buffer read (+50 net); flm_rect moved to 0x9FE8 -16, FLM_MAX 4; jumps in tc_try and tc_save relative; M8a part 7: +19; part 15: +3, dirty_hook calls frm_drop) |
| 0xEC00-0xF500 | 2305 | the current level's blueprint |
| 0xF510-0xF5F8 | 233 | the tile-change snapshot (view.asm, runtime only): VIEW_SNAP 0xF510 (54 x tile byte, modifier; entry 53 since 2026-11-11: the room below-left's column 9), VS_BTN 0xF57C (up to 8 x (entry, pressed) of the buttons on screen, then 0xff), vs_ptrs 0xF58D (54 x the entry's tile byte address, 0 = no room; rebuilt when the room on screen changes) |
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
disk when it is needed (~300 T, ~12 lookups per tick); add_op reads the 5 bytes it needs (offset, w, h) into registers
itself (M8a part 27). Its table `dir_tab` can also point into main RAM
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

The duel (docs/duel-design.md section 12, src/duel/duel.asm): nothing resident. While a duel runs, its pieces lie over
game.asm's main loop (level_ready .. flip_now), kid.asm kid_tick, guard.asm tick_pre .. check_skel and the guard AI
(autocontrol_opponent .. check_chomped_guard), the free main RAM below W1 (end_of_code .. OVL_W1; phase 3's HUD),
kid.asm leave_room .. kid_tick and evres.asm death_text .. draw_game_frame (the network, phase 4), plus six patched
operands (kid.asm duel_d14 / duel_d15, overlay.asm duel_sd1 / duel_sd2, duel_pp1 / duel_pp2). objects.asm
make_loose_fall .. foh2 carries no duel code since section 18 (reserved); check_spiked .. start_chompers neither: the
duel runs the game's spike code there since section 20. The pieces d_boot lays into the holes wait in RAM-disk page 6 0x16C0- (the complete chopper pictures' pool,
runtime scratch) from the launcher to the game's level_ready; the pieces read again during the duel (section 18: the
arenas' P_w2, the texts' P_txt, the lobby's P_lob, the blade pixels P_bld) are a second record in page 1 0xE918-0xFC5B
(the button pictures' slots: runtime scratch, and an arena has no button). P_w2 is copied into W2's top (OVL_WF
0xAA00-0xAFFF, the fill overlay's window: no level start's fill runs in a duel) at the duel's entry and each match's and
round's start (the level-start overlay is loaded below it, 0xA000-, for its alter_mods); P_txt right after the text
overlay (up to 0xA5FF) with it at each text change; P_lob into 0xA600-0xA9FF after the lobby's arena draw. Player 2's block lies over
d_boot / d_ptab once they ran. The next game start restores the clean GAME image.

## Code overlays (src/m4/ovl.asm, 2026-10-29)

Code that does not run every tick is assembled separately (src/m4/ovl_*.asm, against the main program's symbols:
tools/ovltool.py equ) and lives in the RAM disk (page 7 from 0xD900 since 2026-11-01, page 6 0xE300 before: a 12-entry table
(OVL_MAX), then the images; tools/ovltool.py pack -> build/m4ovl.bin, written by tests/m4_game.py setup and later by the
floppy loader). Resident code calls it
through stubs in ovl.asm that copy the overlay into its window first:

| Window | Range | Overlays | Loaded |
|---|---|---|---|
| W1 | 0x7C00-0x7FFF (1 KB, top of the main code) | 0 room (995 B since M8a part 26; 975 B at part 19): draw_room_full = room_ops, tile_tag, slices_build, bkt_build, rr_bkt, run_ops (src/m3/roomfull.asm), and the game's entry rf_game (M8a part 19: after the draw sprite_forget (src/m4/sprforget.inc), the cached button pictures dropped (bc_v) and a jump to frm_reset, which ends in flames_rebuild: what game.asm called after draw_room_full before); set_flip (the upside-down screen's code patches, src/m4/ovl_room.asm: a full room draw follows it) | when not the current W1 overlay (ovl_cur1): today once, at the first room draw |
| W1 | | 2 events (737 B; 1,009 until M8a part 24): proc_get_object + add_life (the potions and the sword: hit points, flashes, feather fall, upside down, open), autocontrol_shadow (the scripted shadows of levels 4, 5, 6, 12, do_auto_moves, the level 12 union), jump_through_mirror, died_on_button (src/m4/events.asm), and from 2026-11-01 to M8a part 24 the buttons (src/m4/buttons.asm, resident since part 24) | when not the current W1 overlay: a shadow level reloads it at its first shadow tick after a room draw (~13 K T), the next room draw reloads the room overlay (~19 K T) |
| W2 | 0xA000-0xAFFF (COMPOSE_A/B, 4 KB) | 1 level (2,299 B since M8a part 19 (its own copy of sprite_forget, pr_build writing to the RAM disk); it must end below WF 0xAA00: 261 bytes left): game_start (the program's start, src/m4/gstart.asm: video_init, tables_init (src/m1/tables.asm), the frame store's fill through fs_ovl (the fill overlay below: 1 MB and more; at boot with the game's ACT_FILL, gs_fill), irq_init, sprite_init, sword_init, pr_build (src/m3/prbuild.asm), then game_init and load_level; 2026-11-01), M7's handoff (M7 step 3: game_init_h sets the sound mode SND_MODE, ho_swap mutes the PSG) (load_level_h: the swap to PRES before a level with a cutscene; game_init_h: the level, time and hit points from HO_MAIN; game_over_h: the swap at GAME_OVER, or level 1 without the launcher), load_level, game_init, guard_type_tbl, alter_mods + tile_type_in (src/m3/altmods.asm), play_level (do_startpos, set_start_pos, checkpoint, the level 1/7/13 entries, a seamless start, draw_level_first, show_level), find_start_level_door, guard_init, pos_guards, kid_start_g, guard_x (src/m4/levelstart.asm); load_level calls the fill overlay's fs_guard with the level's guard set | at every call (the compose buffers overwrite it) |
| WF | 0xAA00-0xAFFF (W2's top, 1.5 KB) | 9 fill (1,453 B, M8a part 12; image in RAM-disk page 6 0xEC00, not in page 7's area): fs_fill (the kid's and the sword's store, M8a parts 9-10), fs_guard (the level's guard set, part 12), ff_prog and the generator src/m4/fsgen.asm (src/m4/ovl_fill.asm, fstore.asm, fsvars.inc); scratch SPRBUF_A = the cell buffer, SPRBUF_B 0xB800 the masks, 0xBC20 the generator's variables, 0xBC60 the fill's, 0xBC80-0xBE4D the row code | 1 MB and more only, by the level-start overlay (gstart.asm fs_ovl): at the boot's ACT_FILL, every game start, every level start |
| W2 | | 3 text (940 B): text_draw, the bottom text line with its glyphs (src/m4/text.asm, build/assets/font_text.inc), GAME SAVED / UNABLE TO SAVE GAME (TEXT_MSG); composes in SPRBUF_B | at every call (game.asm text_chk: a text set or erased, the death text's blink) |
| W1 | | 4 guard-leave (342 B): guard_leaves (exit_room after the kid left a room with a guard: leave_guard / follow_guard), guard_fallout (check_guard_fallout for a guard other than the shadow: the level 3 skeleton, death), guard_tile_ptr (src/m4/gleave.asm) | when the kid leaves a room with a guard in it (then the room draw reloads the room overlay) |
| W1 | | 5 guard-enter (943 B): room_entered (check_the_end's new-room part: anim_tile_modif, start_chompers, check_fall_flo, check_shadow, enter_guard, get_guard_hp, do_init_shad; src/m4/genter.asm, shadinit.asm); lrs_body (leave_room's level specials, guard.asm lr_special's resident tail calls it before goto_other_room; 2026-11-01) | at every room change and level start: lrs_body in the kid's tick, room_entered in the same tick's tick_post (one load; then the room draw reloads the room overlay) |
| W2 | | 6 save (697 B; M7 step 3: both entries stop the sound first, snd_halt): save_game (Ctrl+G, levels 3-13) and load_saved (M7's Ctrl+L), the WD2793 code (src/m4/save.asm, src/boot/fdc.asm) | at every call: save_key at a tick start after pend_flush (game.asm), load_saved |
| W1 | | 7 keys (469 B; CHEATS=1 832 B): key_read, key_logic (src/m4/keys.asm, docs/m7-design.md section 18) | when a key of key_tab is down at a tick start |
| W1 | | 10 gate (924 B, M8a part 14; part 24: pillar gates and the contact band in place, trigger_button's copy out): gate_step, a gate's one-row step as a moving part (src/m4/colshift.asm with CS_GATE) | at a visible gate step when not the current W1 overlay (~19 K T) |
| W1 | | 11 button (821 B, M8a part 14; image in RAM-disk page 6 0xF200, its own place like the fill overlay's): btn_step, a button's press or release from the cached pictures (src/m4/btnstep.asm, cschg.asm) | at a press or release of a button seen in its own room (~17 K T; a moving gate's next step loads the gate overlay again) |
| W1 | | 12 door (471 B, M8a part 14; image in page 6 0xF600): door_step, the level door's opening step (colshift.asm with CS_DOOR; trigger_button resident since part 24) | at a visible door step when not the current W1 overlay (~18 K T; a gate moving in the same tick: both, ~0.55 frames a tick) |
| W1 | | 13 frames (1,020 B, M8a part 15; image in RAM-disk page 0 0xA400-0xA7FF, its own place): frm_step, a chopper's or a spike's picture step from pre-drawn pictures (src/m4/frames.asm) | at a picture step of a chopper or spike of the room on screen when not the current W1 overlay (~21 K T; alternates with the gate overlay while a gate moves) |
| W1 | | 8 rare (423 B, 2026-11-01): hp_redraw + hp_strip (the kid's and the guard's hit point strips, src/m4/hpstrip.asm; game.asm hp_draw falls into hp_redraw's stub, overlay.asm ghp_draw calls hp_strip's; their variables HP_VARS 0x01C0), get_item + do_pickup (an item taken, objects.asm check_get_item), chomped (kid2.asm's stub; src/m4/rare.asm) | when the hit points shown change (a level start, a hit, a potion, a guard hit), an item is taken, a chomper kills |

Moving them freed 1,527 bytes of main code (net 503 after W1) (end_of_code 0x7E5B -> 0x7864, of which W1 now takes the top 1 KB) and
191 bytes of block 2 (block2_end 0xEA71 -> 0xE9B2). The M3 test programs and m4test have no loader and include
roomfull.asm, altmods.asm and levelstart.asm directly. How to add an overlay: the comment at the top of src/m4/ovl.asm.

The fill overlay (M8a part 12, 2026-11-03): fs_fill, fs_guard and the generator left the level-start overlay (3,438 ->
2,273 bytes) for overlay 9 (1,453 bytes), loaded into WF (W2's top, 0xAA00) by the level-start overlay itself
(gstart.asm fs_ovl, on 1 MB and more only); its image is in page 6 0xEC00 (tools/ovltool.py pack: an overlay with
ovl_rd_page / ovl_rd_addr / ovl_rd_last keeps its own place), so page 7's area went from 608 to 1,773 bytes free (the
cheat build 194 -> 1,359). The guards' lookup cost main 11 bytes (fslook.asm fsl_g): free resident code after #26 and
part 12: main 602 (end_of_code 0x79A6), low 22 (end_of_low 0x1FEA), block 2 unchanged.

## The low code (M8a part 25)

The free low RAM of parts 19 and 20 now holds code: src/m4/ovl_low.asm at 0x0500-0x06FF and ovl_low2.asm at
0x0E00-0x0FFF (the lazy shadow and the direct copies of choppers' and spikes' pictures, docs/perf.md "M8a part 25"), with
their data at 0x0700-0x076D. They are overlays 14 and 15 of the table (OVL_MAX 16; 17 since M8a part 28's loose-floor overlay), windows WL and WL2. Neither comes and
goes: game_start (gstart.asm, the level-start overlay) loads both with ovl_load at every start, after the launcher's
zero_low. Their images have their own places in the RAM disk, written by tests/m4_game.py and tools/mkgamedisk.py:
page 4 0xFE00-0xFFE4 (after part 15's slots) and page 1 0xDE18-0xDFFA (between part 15's slot 0xDA58 and the sound
bank). The rules below still hold (code here may run with VRAM mapped: lc_direct does). gfx.asm calls into it only when
LCODE is defined (game.asm): m4test and the M3 programs assemble gfx.asm without the hooks. Free: 0x06E5-0x06FF,
0x076E-0x077F, 0x0FE3-0x0FFF.

### What the free low RAM 0x0500-0x077F allowed (M8a part 19)

640 contiguous bytes (and 16 more at 0x04F0-0x04FF, between the slice extents and PR_TAB's old place), freed when
PR_TAB went to the RAM disk. What can go there and what it must respect:

- **Code is possible, also code that runs inside `blit`.** The game maps 0x0000-0x0FFF as RAM at its start (game.asm
  `out (0xe0)`, `out (0xe1)`) and nothing maps it away: `in a, (0xe0)` (blit, blit_flip, tc_direct, the fill's VRAM
  use) puts the CG-ROM over 0x1000-0x1FFF and VRAM over 0x8000-0x9FFF only. So unlike the low code block 0x1200-0x1FFF,
  code here may run with VRAM mapped (e.g. a POP / PUSH copy into VRAM, roadmap step 3), and it may read 0x8000-0x9FFF
  only as VRAM then (as main code).
- **It is zeroed at every program start, and no loader can put it there.** The launcher (src/boot/boot.asm zero_low)
  clears 0x0000-0x11FF before it starts the game (every boot, every swap back from PRES), and m4game.mzf loads at
  0x1200 (the ROM's tape loader: the monitor ROM is at 0x0000-0x0FFF while it runs; the harness's run_mzf the same).
  Code here must be copied in by game_start (src/m4/gstart.asm, the level-start overlay, which runs after every
  launcher start and in the harness): from the level-start overlay itself (261 bytes left below WF) or from its own
  RAM-disk image (tools/ovltool.py pack's own-place overlays, as the fill / button / door images: page 6 0xE280-0xE3FF
  384 B, page 7 0xFD99-0xFFFF 615 B (the cheat build 201 B; M8a part 28), page 0 0xA22B-0xA3FF 469 B) with one far_copy; that
  copy is ~14 K T for 640 bytes, once a start. Data here must be runtime-initialised (as all of low RAM).
- **No vectors, no stack near it.** The interrupt is IM2 through VECTAB 0xFE00 (I = 0xFE); the stack is below 0xFE00;
  RST and NMI vectors (0x0000-0x0066) are inside GSWBUF and unused. The neighbours are data: SL_Y0 / SL_Y1 below
  (0x0400-0x04EF) and the sprite descriptors SPR_GS .. PP_DL from 0x0780.
- **The other programs:** m4test and the M3 test programs do not use 0x0500-0x077F (m4test's snapshots are at
  0x02B0-0x02DB); code shared with m4test that moves here needs m4test to place it the same way. PRES is a separate
  program (the launcher zeroes it all between).
- tests/m5_boot.py and m7_launch.py compare main RAM between the floppy-booted game and the harness: what game_start
  writes here is the same on both paths.

## RAM disk (64 KB pages)

| Page | Content | Free |
|---|---|---|
| 0 | dungeon environment pack (41.5 KB), the frames overlay's image (0xA400-0xA7FF, M8a part 15), shadow guard set (0xA800, 16.1 KB), the launcher's area (0xF000-0xFBFF, M7: src/boot/boot.asm's image, 2.3 KB used, up to 0xFAFF; 0xFB00-0xFBFF the POP800.PRS table, launch.inc PRS_TAB_RD_ADDR, 2026-11-14); M8a part 15's picture slots (512 KB, 1 MB; runtime only, tests/m5_boot.py RUNTIME_SCRATCH): 0xE868-0xEFE7 (2 x 960), 0xFC00-0xFFBF (960) | 469 B (0xA22B-0xA3FF) + 24 B + 64 B |
| 1 | shadow room (0x0000, 32,000 B), dungeon wall pack (0x8000), objects (0xC000), sword (0xD000), the PSG sound bank (0xE000-0xE8FF, M7: build/assets/sound.bin, tools/sndconv.py + tools/midi2psg.py; 2,304 bytes, and its second part 0xFEE4-0xFF18 (53 bytes, build/assets/sound_hi.bin, since 2026-11-11: the streams that no longer fit before the button pictures, docs/m7-design.md 12.2): index 57 x 4, effects 954 (since 2026-11-10: the looping level door 15, docs/m7-design.md 12.1; 2026-11-11: the ring-outs, 12.2), the 11 in-game music pieces 1,175), the button pictures (0xE918-0xFC5B, M8a part 14, runtime only: 4 slots of 1,233 bytes, src/m4/btnstep.asm: the 8 x 17-byte rect of a button in both states, 4 planes, and its differing records; runtime scratch: tests/m5_boot.py RUNTIME_SCRATCH leaves it out of the RAM-disk comparisons), the low code's part 2 image (0xDE18-0xDFFA, M8a part 25: build/ovl_low2.bin) | (part 15's slots: 0x7D00-0x7F87 (648), 0xDA58-0xDE17 (960), 0xFC5C-0xFEE3 (648)) 0x7F88-0x7FFF, 0xDFFB-0xDFFF, 0xE900-0xE917, 0xFF19-0xFFFF |
| 2-3 | kid pack (106.3 KB); page 3 0xA000-0xFF2B: the game's compressed image (M7, 24,364 bytes: the program's main-RAM records as a record stream; when it grows past 0xFFFF it continues in page 4 at 0xD400, tools/mkgamedisk.py GAME_SEGS) | 0.2 KB (0xFF2C-0xFFFF) + 0x9F28-0x9FFF |
| 4 | palace environment pack (54.2 KB); 0xD400-: the game image's second piece (0xD400-0xDD2F at M8a part 15; tools/mkgamedisk.py asserts it ends below FRM_P4); 0xE000-0xFDFF: part 15's picture slots (512 KB, 1 MB: 8 x 960, runtime only); 0xFE00-0xFFE4: the low code's part 1 image (M8a part 25: build/ovl_low.bin) | 0xDD30-0xDFFF + 0xFFE5-0xFFFF |
| 5 | palace wall pack (0x0000), 16 level blueprints (0x4000), guard set directories (0x3400, 6 x 0x120, game.asm guard_type_tbl order), directories (0xD100 dungeon env, 0xD800 dungeon wall, 0xDB00 palace env, 0xE200 palace wall, 0xE500 objects, 0xE700 kid, 0xEE00 sword), harness control script (0xF000), the handoff block (0x3AC0-0x3ACF, M7: src/boot/launch.inc) | ~1 KB (0x3AD0-0x3FDF: part 15's slots, 2 x 648) |
| 6 | torch picture cache (0x0000-0x143F: FLM_MAX 4 flames x 9 slots of 144 bytes, runtime only; 0x1440-0x287F (5,184 bytes) was free after M8a part 17 cut FLM_MAX from 8 to 4; of it 0x16C0-0x25BF (3,840 bytes) is M8a part 25's complete-picture pool on 512 KB and 1 MB (4 x 960, the first chopper's pictures 0-3, runtime only) and 0x25C0-0x287F (704 bytes) free), PR_TAB (0x1440-0x16BF, M8a part 19: the wall pattern's draws mod 140, 64 seeds x 10; written by pr_build at every start of the game program (gstart.asm, after the launcher's zero_low, so after every PRES swap too: PRES's sound bank overwrites 0x0000-0x287F), read by pr_start, 10 bytes a wall pattern; the same place on every size: the frame store starts at page 8), dungeon guard set (0x3000), palace guard set (0x8000), logic.bin (0xD000-0xE27F: sequence table, kid and guard frame tables, kid image widths 0xE000, guard image sizes 0xE100), the frame store's masks and build id (0xE400-0xE7FF, build/assets/fstore_masks.bin, M8a part 9: the fill's input, written on every size), the guard sets' masks (0xE800-0xEBBF, build/assets/fstore_gmasks.bin, part 12: 12 records of 80 bytes), the fill overlay's image (0xEC00-0xF1AC, build/ovl_fill.bin, part 12; both written on every size), the button overlay's image (0xF200-0xF527, build/ovl_btn.bin, M8a part 14, written with the fill's), the door overlay's (0xF600-0xF963, build/ovl_door.bin); the code overlays were at 0xE300-0xFFFF until 2026-11-01 (full: now page 7) | 704 B (0x25C0-0x287F, runtime only; PRES's scratch) + 0.4 KB (0xE280-0xE3FF) + 64 B (0xEBC0-0xEBFF) + 83 B (0xF1AD-0xF1FF) + 203 B (0xF535-0xF5FF) (part 15's slots: 0x2880-0x2FFF 2 x 960, 0xF964-0xFD23 960, 0xFD24-0xFFAB 648) |
| 7 | fat (0x0000), skeleton (0x4C40), vizier (0x8D80-0xD8F3) guard sets, code overlays (0xD900-0xFD98, build/m4ovl.bin, 9,369 bytes (M8a part 28; tools/ovltool.py pack prints the layout): the 17-entry table 0xD900-0xD987 (8 bytes an entry, OVL_MAX 17 since M8a part 28), room 0xD988 (995 bytes since part 26), level start 0xDD6B (2,309 bytes; 2,273 since part 12: the fill moved to its own overlay in page 6), then events 0xE670, text 0xE951, guard-leave 0xED4E, guard-enter 0xEEA4, save 0xF253, keys 0xF50C, rare 0xF6E1, gate 0xF888 (M8a part 14), loose floors 0xFC24 (373 bytes, M8a part 28); the button, door, frames, low and fill overlays have their own places in pages 6, 0, 4 and 1; the cheat build to 0xFF36 (9,783 bytes)) | 615 B (0xFD99-0xFFFF; the cheat build 201 B) |

Title and cutscene art (title 215 KB, story/cutscene 115 KB) is for the presentation program PRES (M7): per the
decision of 2026-10-30 (docs/m7-design.md section 9) it is read from the floppy (POP800.PRS) per scene into PRES's own
main RAM; the RAM disk only gets what the swap needs (the launcher 2.2 KB, the game image 24 KB, the handoff block).
The scratch areas (the shadow room page 1 0x0000-0x7CFF, the torch cache page 6 0x0000-0x287F) are free for PRES.

Pages 8 and up (a RAM disk of 1 MB or more; the tiers by HO_RDTOP: 15-61 (1 MB up to 3.9 MB, 2 MB among them) the 1 MB
layout, pages 8-15 only; 62 and more (FS_TOP2: 4, 8 and 16 MB) the full layout, pages 8-62, nothing above: docs/ramdisk-tiers.md
section 15; M8a part 9, docs/ramdisk-tiers.md "As built: step 1"): the frame store, written
only by the fill overlay (src/m4/fstore.asm: at boot the kid's and the sword's keys, at a level start the level's guard set; M8a part 12, docs/ramdisk-tiers.md section 13) on a RAM disk of 1 MB and more (HO_RDTOP >= 15); on 512 KB
they are not written (page 8 would alias page 0):

| Page | Content |
|---|---|
| 8 0x0000-0x75BF | the key table: 471 ids x 16 variants x 4 bytes (id = the kid's frame 0-219, the sword's 220 + frame, 255 + 36 x set + frame the six guard sets, M8a part 12: their slots 0x3FC0-0x75BF), slot id * 64 + (mirror * 8 + shift) * 4 = the entry's page (0 = not stored), address hi, lo, 0 |
| 8 0x7700-0x7704 | the marker: the build id (tools/fstore.py: a CRC of the masks, the kid and sword packs and directories, the kernel's sources and the fill), the class filled (1, 2); written last; cleared by the boot (src/boot/boot.asm), so every boot fills |
| 8 0x7705-0x770A | the guard sets' flags (part 12): set s's entries and slots are filled; cleared with the key table by the boot's fill; on 1 MB all are cleared (with all guard slots) before a set is filled |
| 8 0x7800- and 9-14 | class 1 (every card from 1 MB): 891 entries, 409,512 bytes, to page 14 0xC2F4; an entry = ow, h, the byte count (2), the cell buffer as spr_fetch leaves it ((w + 1) * 4 * h bytes); none crosses a page; the order and addresses are tools/fstore.py's (build/assets/fstore_keys.txt) |
| 14 0xC2F4-15 | 1 MB to 3.9 MB (g 1): the level's guard set, refilled when the set changes (81.2 KB: 106-150 entries, 81.1 KB a set; part 12; no room cache on 1 MB, the user's decision of 2026-11-03) |
| 14 0xC2F4-27 0x6130 | class 2 (from rd_top FS_TOP2 = 62 since 2026-11-13, 61 before: 4 MB and more): 1,262 more entries, 823,312 bytes |
| 27 0x6130-61 0x390C | 4 MB and more (g 2): the six guard sets whole (every variant), each in its own region (27:6130, 33:814C, 39:6374, 44:5E24, 50:2FAC, 55:1A04), filled at the first level with that set and kept |
| 61 0x390C-61 | free (4 MB and more) |
| 62 0x0000-0x5FFF | 4 MB and more: M8a part 15's chopper and spike pictures (src/m4/frames.asm FRM_P16: 4 objects x 6 slots of 1 KB; runtime only) |
| 62 0x6000-0xBFFF | 4 MB and more: M8a part 25's complete pictures (the rect as the screen shows it with nobody in it, row-major), one per slot at the slot's address + 0x6000; runtime only |
| 62 0xC000-63 (4 MB), -127 (8 MB), -255 (16 MB) | free |

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
| 0xB000-0xB965 | the loader / launcher (2,406 bytes of code, font and messages (2026-11-14); the WD2793 code src/boot/fdc.asm; at most LN_MAX = 3 KB) and its variables |
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

PRES's free main RAM (2026-11-14, PLAN item 99): PRES's code (0x2000-end_of_pres) shares main RAM with two things that
move when it grows: the title art's PZ bands (tools/mkgamedisk.py title_entries: first fit into 0x1200-0x1FFF,
end_of_pres-0x7FFF and ART2_START-ART2_END) and the cutscene art (tools/cutart.py: the engine to end_of_cut, then the
room's bands and each scene's sprites from end_of_cut, a 62-byte sprite of cutscene_2_6 the tightest). The cutscene art
is the limit: PRES may grow by **2 bytes** (end_of_pres 0x2F08), the title art alone would allow 444. mkgamedisk checks
both with PRES PRES_RESERVE (2) bytes longer and prints the figure ("PRES may grow by ..."); one more byte of PRES stops
the build ("PRES has grown into its reserve"). The duel's Ctrl+D code (pres.asm DUEL_PRES_USED, 34 B) is part of PRES;
its old 64-byte reserve (DUEL_PRES_BYTES) was checked against the title art only and is gone.

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
