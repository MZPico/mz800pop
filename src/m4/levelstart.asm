; Level start: the kid's start position (kid.asm's state, SDLPoP do_startpos + set_start_pos), the start room's level
; door (objects.asm), the guards' start state (guard.asm; guard_opts and the guard variables gv_start..gv_end stay
; in guard.asm). Run once per level start, from load_level: the M4 game runs it from the level-start overlay
; (src/m4/ovl_level.asm), m4test includes it directly.

; Level start: SDLPoP play_level / do_startpos / set_start_pos / draw_level_first as tools/kidsim.py has them (the
; kid's start position, a level 3 checkpoint, the level 1, 7 and 13 entries, a seamless start after the level 12
; exit, the start room's level door, the guards' start state, the LEVEL text), and game_init (a new game). Run from
; load_level: the M4 game runs this from the level-start overlay (src/m4/ovl_level.asm), m4test includes it directly.

SQ_RUN          equ     84
; game_init: kidsim's initial state (a new game): the level events (EV), the time left (ev_opts: the harness's
; '# time' option, else 60 minutes), the characters and the guard globals, kidsim's tick counter
game_init:      ld      hl, EV
                ld      de, EV + 1
                ld      bc, EV_SIZE - 1
                ld      (hl), 0
                ldir
                ld      hl, gv_start
                ld      de, gv_start + 1
                ld      bc, gv_end - gv_start - 1
                ld      (hl), 0
                ldir
                ld      hl, 0
                ld      (K_TICK), hl
                xor     a
                ld      (LAST_LOOSE), a
                ld      a, (ev_opts + 3)
                ld      (REM_MIN), a
                ld      hl, (ev_opts + 4)
                ld      (REM_TICK), hl
                ld      a, 3
                ld      (HITP_BEG_LEV), a
                ld      a, (level_number)
                ld      (NEXT_LEVEL), a
                ld      hl, SND                 ; the sound model (sound.asm): nothing asked for or played
                ld      b, SND_SIZE
gi_snd:         ld      (hl), 0
                inc     hl
                djnz    gi_snd
                ld      a, 0xff
                ld      (SND_NEXT), a
                xor     a                       ; the ticks model (M7 step 5): nothing plays, the level end's clock
                ld      (SND_LEFT), a           ; runs; the level 1 start crouches until its music ends (SDLPoP
                ld      (END_OVER), a           ; init_game: need_level1_music; sound.asm crouch_music: not when
                ld      a, (level_number)       ; silent)
                cp      1
                ld      a, 0
                jr      nz, gi_l1
                inc     a
gi_l1:          ld      (NEED_L1M), a
                ld      hl, snd_ticks_tab       ; the lengths (sound.asm SND_T12, SND_T10)
                ld      de, SND_T12
                ld      bc, 100
                ldir
                ld      hl, guard_tabs_img      ; the guards' skill tables (guard.asm GUARD_TABS)
                ld      de, GUARD_TABS
                ld      bc, GUARD_TABS_N
                ldir
                ret
; strikeprob, restrikeprob, blockprob, impblockprob, advprob, refractimer (12 skills each), tbl_guard_type (16 levels):
; SDLPoP data.h custom defaults
guard_tabs_img:
                db           61, 100, 61, 61, 61, 40, 100, 220, 0, 48, 32, 48
                db           0, 0, 0, 5, 5, 175, 16, 8, 0, 255, 255, 150
                db           0, 150, 150, 200, 200, 255, 200, 250, 0, 255, 255, 255
                db           0, 61, 61, 100, 100, 145, 100, 250, 0, 145, 255, 175
                db           255, 200, 200, 200, 255, 255, 200, 0, 0, 255, 100, 100
                db           16, 16, 16, 16, 8, 8, 8, 8, 0, 8, 0, 0
                db           0, 0, 0, 2, 0, 0, 1, 0, 0, 0, 0, 0, 4, 3, 0xff, 0xff
; the ticks sound model's lengths (tools/kidsim.py sound_ticks_tables: ceil(seconds x rate), the feather music at least
; the 225-tick cap) for the ids 0-49, at 12 ticks a second, then at 10; tests/m4_test.py checks them against kidsim
snd_ticks_tab:
                db      2, 14, 7, 2, 2, 2, 7, 1, 2, 3, 4, 2, 2, 5, 9, 20
                db      6, 5, 8, 4, 2, 2, 2, 2, 44, 30, 168, 144, 87, 64, 43, 0
                db      87, 29, 0, 124, 175, 50, 0, 225, 83, 153, 0, 46, 3, 5, 6, 6
                db      2, 5
                db      2, 11, 6, 2, 1, 2, 6, 1, 2, 3, 4, 2, 2, 4, 7, 17
                db      5, 4, 7, 3, 2, 1, 2, 2, 36, 25, 140, 120, 72, 53, 36, 0
                db      73, 24, 0, 103, 146, 42, 0, 187, 69, 128, 0, 39, 3, 4, 5, 5
                db      2, 4

; play_level: the level in LEVEL is fresh: start it. Kept from before: kidsim's tick (K_TICK), the hit points (a
; seamless start), LAST_LOOSE, the four character records and the guard globals guard_init does not clear; Char
; starts as the last tick left it (CHAR_SAVE: do_startpos sets nearly all of it).
play_level:     ld      hl, (K_TICK)
                push    hl
                ld      hl, (HITP_CURR)         ; (curr, max)
                push    hl
                ld      a, (LAST_LOOSE)
                push    af
                ld      hl, KV
                ld      de, KV + 1
                ld      bc, 176 - 1
                ld      (hl), 0
                ldir
                ld      hl, OV                  ; objects, hit points, counters
                ld      de, OV + 1
                ld      bc, 32 - 1
                ld      (hl), 0
                ldir
                pop     af
                ld      (LAST_LOOSE), a
                pop     hl
                ld      (HITP_CURR), hl
                pop     hl
                ld      (K_TICK), hl
                ld      hl, CHAR_SAVE
                ld      de, KV
                ld      bc, 16
                ldir
                call    guard_init
                xor     a
                ld      (FLASH_TIME), a
                ld      (DEMO_INDEX), a
                ld      (DEMO_TIME), a
                ld      (IS_RESTART), a
                ld      (LEVEL_SWITCH), a
                ld      (END_OVER), a           ; (the level end's clock: running)
                call    pos_guards
                ld      a, -1                   ; collision rooms: none (prev, curr, below, above)
                ld      (PREV_COLL_ROW), a
                ld      (SND_NEXT), a           ; (next_sound = -1)
                ld      hl, PREV_ROOMS
                call    ks_none
                ld      hl, CURR_ROOMS
                call    ks_none
                ld      hl, BELOW_ROOMS
                call    ks_none
                ld      hl, ABOVE_ROOMS
                call    ks_none
; do_startpos
                ld      hl, ev_opts             ; the harness's start position ('# start', the first level only)
                ld      a, (hl)
                or      a
                jr      z, ks_cp
                ld      de, LV_START_ROOM
                ld      bc, 3
                ldir
                xor     a
                ld      (ev_opts), a
ks_cp:          ld      a, (level_number)       ; level 3 after the checkpoint: start there, the loose floor of
                cp      3                       ; room 7 is gone
                jr      nz, ks_pos
                ld      a, (CHECKPOINT)
                or      a
                jr      z, ks_pos
                ld      hl, LV_START_ROOM
                ld      (hl), 2
                inc     hl
                ld      (hl), 6
                inc     hl
                ld      (hl), 0xff
                ld      a, 7
                ld      bc, 0x0004
                call    k_get_tile
                ld      a, T_EMPTY
                call    set_tile_cur
ks_pos:         ld      a, (LV_START_ROOM)
                ld      (K_ROOM), a
                ld      a, (LV_START_ROOM + 1)  ; start_pos
                ld      b, 0
ks_row:         cp      10
                jr      c, ks_r2
                sub     10
                inc     b
                jr      ks_row
ks_r2:          ld      (K_COL), a
                ld      a, b
                ld      (K_ROW), a
                ld      a, (K_COL)
                add     a, FIRST_COL
                ld      hl, x_bump
                call    k_tbl
                add     a, TILE_SIZEX
                ld      (K_X), a
                ld      a, (LV_START_ROOM + 2)  ; start_dir: he turns into it
                cpl
                ld      (K_DIR), a
                ld      a, (SEAMLESS)           ; hit points (kept after the level 12 exit)
                or      a
                jr      nz, ks_seq0
                ld      a, (level_number)
                or      a
                ld      a, 4
                jr      z, ks_hp
                ld      a, (HITP_BEG_LEV)
ks_hp:          ld      (HITP_CURR), a
                ld      (HITP_MAX), a
ks_seq0:        ld      a, (level_number)
                cp      13
                ld      a, SQ_RUN               ; level 13: running entry
                jr      z, ks_seq
                ld      a, (level_number)
                cp      1
                ld      a, SQ_TURN
                jr      nz, ks_seq
                ld      a, 5                    ; level 1: the button in room 5 is pressed, he drops in
                ld      c, 2
                ld      b, 0
                call    k_get_tile
                ld      b, 0
                ld      c, 0xff
                xor     a
                call    trigger_button
                ld      a, SQ_FALL
ks_seq:         call    seqtbl_offset_char
; set_start_pos
                ld      a, (K_ROW)
                inc     a
                ld      hl, y_land
                call    k_tbl
                ld      (K_Y), a
                xor     a
                ld      (K_CHARID), a
                ld      (K_FALLX), a
                ld      (K_FALLY), a
                ld      (K_SWORD), a
                ld      (UPSIDE), a
                ld      (FEATHER), a
                ld      (SND_SCREAM), a
                dec     a
                ld      (K_ALIVE), a
                call    play_seq
                ld      a, (level_number)       ; level 7: from room 17 he falls into the room below
                cp      7
                jr      nz, ks_save
                ld      a, (K_ROOM)
                cp      17
                jr      nz, ks_save
                ld      a, 3
                call    goto_other_room
ks_save:        call    savekid
                ld      a, (level_number)       ; have_sword from level 2 on (and the demo level)
                cp      1
                ld      a, 0
                jr      z, ks_sw
                inc     a
ks_sw:          ld      (HAVE_SWORD), a
                call    find_start_level_door
                call    snd_stop
; draw_level_first
                ld      hl, 12345               ; the random seed of a level start (SDLPoP oracle runs use the same)
                ld      (SEED), hl
                ld      hl, 0
                ld      (SEED+2), hl
                ld      a, (K_ROOM)
                ld      (NEXT_ROOM), a
                call    kid_start_g             ; (the harness's guard options, the start room)
; show_level: the LEVEL text (not after a seamless start, not on levels 0 and 14, 15)
                call    erase_text
                ld      a, (SEAMLESS)
                or      a
                jr      nz, ks_sl
                ld      a, (level_number)
                or      a
                jr      z, ks_sl
                cp      14
                jr      nc, ks_sl
                ld      hl, 24
                call    set_text
                ld      a, 1
                ld      (IS_SHOW_TIME), a
ks_sl:          xor     a
                ld      (SEAMLESS), a
                jp      tick_end
ks_none:        ld      b, 10
ks_c1:          ld      (hl), 0xff
                inc     hl
                djnz    ks_c1
                ret

; ---------------------------------------------------------------- (objects.asm) the start room's level door
find_start_level_door:
                ld      a, (K_ROOM)
                ld      (CURR_ROOM), a
                xor     a
                ld      (sc_pos), a
fsl_loop:       ld      a, (sc_pos)
                call    get_curr_tile
                cp      T_LEVELDOOR_L
                jr      nz, fsl_next
                ld      a, (sc_pos)
                ld      c, a
                ld      a, (CURR_ROOM)
                call    o_ptrs
                ld      a, 43
                ld      (de), a
                ld      a, (CURR_ROOM)
                ld      b, a
                ld      a, (sc_pos)
                ld      c, a
                ld      a, 3
                call    add_trob
fsl_next:       ld      hl, sc_pos
                inc     (hl)
                ld      a, (hl)
                cp      30
                jr      nz, fsl_loop
                ret

; ---------------------------------------------------------------- (guard.asm) the guards at a level start
; guard_init: what play_level clears of the guard state (the rest stays as the last level left it, as in kidsim)
guard_init:     xor     a
                ld      (GUARDHP_CURR), a
                ld      (CAN_SEE), a
                ld      (HOLDING_SWORD), a
                ld      (OFFGUARD), a
                ld      (DROPPEDOUT), a
                ld      (UNITED), a
                ld      a, CHARID_GUARD
                ld      (GUARD_REC + OF_CHARID), a
                ld      a, DIR_NONE
                ld      (GUARD_REC + OF_DIR), a
                ret
; pos_guards: the guards' x from their tiles
pos_guards:     ld      hl, LV_GTILE
                ld      b, 24
ksg1:           ld      a, (hl)
                cp      30
                jr      nc, ksg2
                call    guard_x
                push    hl
                ld      de, LV_GX - LV_GTILE
                add     hl, de
                ld      (hl), a
                ld      de, LV_GSEQHI - LV_GX
                add     hl, de
                ld      (hl), 0
                pop     hl
ksg2:           inc     hl
                djnz    ksg1
                ret
; kid_start_g: draw_level_first's harness options (sword, placed guards), then the start room (check_the_end)
kid_start_g:    ld      a, (guard_opts)
                and     2
                jr      z, ksg4
                ld      a, 1
                ld      (HAVE_SWORD), a
ksg4:           ld      a, (guard_opts + 1)     ; placed guards
                or      a
                jr      z, ksg6
                cp      GOPT_MAX + 1
                jr      c, ksg4b
                ld      a, GOPT_MAX
ksg4b:          ld      b, a
                ld      ix, guard_opts + 2
ksg5:           ld      a, (ix + 0)
                dec     a
                ld      e, a
                ld      d, 0
                ld      hl, LV_GTILE
                add     hl, de
                ld      a, (ix + 1)
                ld      (hl), a
                call    guard_x
                ld      hl, LV_GX
                add     hl, de
                ld      (hl), a
                ld      hl, LV_GDIR
                add     hl, de
                ld      a, (ix + 2)
                ld      (hl), a
                ld      hl, LV_GSKILL
                add     hl, de
                ld      a, (ix + 3)
                ld      (hl), a
                ld      hl, LV_GCOLOR
                add     hl, de
                ld      a, (ix + 4)
                ld      (hl), a
                ld      hl, LV_GSEQLO
                add     hl, de
                ld      (hl), 0
                ld      hl, LV_GSEQHI
                add     hl, de
                ld      (hl), 0
                ld      de, 5
                add     ix, de
                djnz    ksg5
ksg6:           jp      check_the_end
; guard_x: A = guard tile (0..29) -> A = x_bump[tile % 10 + 5] + 14 (keeps BC, DE, HL)
guard_x:        push    hl
gx1:            cp      10
                jr      c, gx2
                sub     10
                jr      gx1
gx2:            add     a, FIRST_COL
                ld      hl, x_bump
                call    k_tbl
                add     a, TILE_SIZEX
                pop     hl
                ret
