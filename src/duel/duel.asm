; ---------------------------------------------------------------- the duel patch (docs/duel-design.md, phase 2)
; The duel easter egg: the kid (player 1) against the shadow (player 2) in one room, both with the kid's moves, as
; tools/duelsim.py plays it (the oracle; docs/duel-design.md section 11 the rules, section 12 this patch as built).
; Not a program of its own: pieces of code laid over the GAME image (build/m4game.bin, restored by the launcher as for
; every game start) where the duel never runs the game's code: the holes (H_* below; tools/duelpatch.py checks every
; piece against them and the call graph against the holes). Assembled against the game's symbols (build/duel.inc,
; tools/ovltool.py equ), so a change of the game moves the pieces with it or fails the build here.
;
; How it gets there (src/boot/boot.asm, ACT_DUEL; Ctrl+D on PRES's title): the launcher loads POP800.PRS entry
; PRS_DUEL1 (the staged pieces, one RAM-disk record: page DUEL_STAGE_PAGE at DUEL_STAGE_ADDR, runtime scratch), restores
; the GAME image, loads entry PRS_DUEL (the piece P_main: main RAM over the game's main loop, level_ready on) and starts
; the game at its `start`. The game starts as always (game_start: the video, the tables, the interrupts, level 1's
; start: the game's code untouched until then), returns to level_ready = d_boot here, which copies the staged pieces
; into their holes and runs the duel (d_entry). Nothing of the patch is in the RAM disk's GAME image: the next game
; start restores a clean one.
;
; The rules (duelsim's DuelSim.step): the duel's own tick (d_tick) runs both players' frames with the game's routines;
; player 2's frame runs with Char.charid = the kid's and Opp.charid = the shadow's, so every charid test of the game's
; sword code takes the kid's rules (D1-D9: the kid's frame table, draw rule, sword sequences, parry rule) and the
; "opponent is the shadow" rule (D3) holds both ways; kid_sword_strike (set only by the real kid's strike) is kept
; around it. D10 (the kid's hurt sound) and D12 / D13 (each player's own hit points, both hurt in one tick) are the
; duel's own hurt (d_hurt); D11 (the shadow sees the kid) is check_can_guard_see_kid run with the record's charid a
; guard's; D14 / D15 are the only patches inside the game's kid code (kid.asm duel_d14, duel_d15). Player 2's block
; (duelsim BLOCK + COLL: 90 bytes) is swapped with the globals around its frame (d_swap).
;
; The drawing: the game's (the full room draw once, draw_objects, the hit point strips); player 2 is drawn as the
; kid (its record's charid is the kid's while drawing: the kid's images, no XOR look, its strip at the right) with
; a blue suit and grey hair (a plane operation per cell: d_sdraw, DUEL_LOOK; overlay.asm duel_sd1 / duel_sd2). Pacing: mode 0, every tick drawn, at least 4 frames (game.asm's).
; The torches flicker as in the game (d_torches, process_trobs, view_redraw: prandom, never hashed).
; Sound: the silent model (SND_MODE 0: nothing waits on a sound; the effects play).
;
; Input (d_input; the byte of duel-design 11.6: bit 0 left, 1 right, 2 up, 3 down, 4 the button, 5 quit, 6 rematch):
; player 1 the game's (the cursor keys, SHIFT, joystick 1: read_inputs' INPUT), BREAK = quit, ENTER = rematch;
; player 2 W A S D + Q and joystick 2 (IN F1h). The harness (tests/duel_z80.py) sets d_script: two bytes a tick from
; RAM-disk page RD_LV_PAGE instead.

                include "../../build/duel.inc"

; ---- the arena and the rules (tools/duelsim.py)
ARENA_ROOM      equ     3
ARENA_ROW       equ     1
P1_COL          equ     2
P2_COL          equ     7
ROUND_HP        equ     3
WINS            equ     3
ROUND_END_TICKS equ     36
IN_QUIT         equ     5               ; (bits)
IN_REMATCH      equ     6
MATCH_QUIT      equ     3
DUEL_STAGE_PAGE equ     6               ; the staged pieces: RAM-disk scratch (duel-design 1.5 rule 1: page 6
DUEL_STAGE_ADDR equ     0x16c0          ; 0x16C0-0x287F; the chopper pictures' pool at runtime, none in the arena)
DUEL_STAGE_END  equ     0x2880
PORT_JOY2       equ     0xf1

; ---- the holes: code of the game the duel never runs (tools/duelpatch.py: a piece lies inside one hole; the stubs and
; the patch sites are holes of their own). H_x .. H_x_END (exclusive).
H_MAIN          equ     level_ready             ; game.asm's main loop (the duel has its own): PRS_DUEL, main RAM
H_MAIN_END      equ     flip_now
H_KT            equ     kid_tick                ; kid.asm kid_tick (the duel has its own frame, d_frame)
H_KT_END        equ     level_number
H_TICK          equ     tick_pre                ; guard.asm tick_pre, tick_post, tick_end, timers, do_mouse, check_skel
H_TICK_END      equ     check_can_guard_see_kid
H_AI            equ     autocontrol_opponent    ; guard.asm the guard AI, play_guard_frame, play_guard, the guard's
H_AI_END        equ     check_sword_hurting     ; bumps and chompers
H_FREE          equ     end_of_code             ; main RAM free below W1
H_FREE_END      equ     OVL_W1
; the patch sites (kid.asm, overlay.asm: labels only in the game's source)
H_D14           equ     duel_d14
H_D14_END       equ     duel_d14 + 3
H_D15           equ     duel_d15 + 1
H_D15_END       equ     duel_d15 + 3
H_SD1           equ     duel_sd1 + 1
H_SD1_END       equ     duel_sd1 + 3
H_SD2           equ     duel_sd2 + 1
H_SD2_END       equ     duel_sd2 + 3
H_PP1           equ     duel_pp1 + 1
H_PP1_END       equ     duel_pp1 + 3
H_PP2           equ     duel_pp2 + 1
H_PP2_END       equ     duel_pp2 + 3

; ================================================================ P_main: over the game's main loop (main RAM)
                org     H_MAIN
P_main:
; d_boot: game_start returned here (level 1 started, the interrupts on): the staged pieces into their holes
d_boot:         ld      a, DUEL_STAGE_PAGE
                ld      de, DUEL_STAGE_ADDR
                call    far_seek
                ld      ix, d_ptab
db_p:           ld      l, (ix+0)
                ld      h, (ix+1)
                ld      a, h
                or      l
                jp      z, d_entry
                ld      e, (ix+2)
                ld      d, (ix+3)
                ld      bc, 4
                add     ix, bc
                ld      c, RD_DATA
db_f:           ld      a, d
                or      a
                jr      z, db_r
                ld      b, 0
                inir
                dec     d
                jr      db_f
db_r:           ld      a, e
                or      a
                jr      z, db_p
                ld      b, a
                inir
                jr      db_p
; the staged pieces in their order in the RAM disk (tools/duelpatch.py stages them so): address, length; 0 ends
d_ptab:         dw      P_ai, P_ai_end - P_ai
                dw      P_kt, P_kt_end - P_kt
                dw      P_tick, P_tick_end - P_tick
                dw      P_d14, 3
                dw      P_d15, 2
                dw      P_sd1, 2
                dw      P_sd2, 2
                dw      P_pp1, 2
                dw      P_pp2, 2
                dw      0
d_script:       dw      0               ; (the harness: the next input pair's RAM-disk address in page RD_LV_PAGE; 0: live)

; d_loop: the match loop (game.asm mainloop's mode 0: a tick every 4 frames at most, every tick drawn)
d_loop:         ld      hl, (FRAMES)
                ld      de, (LAST_TICK)
                or      a
                sbc     hl, de
                ld      a, h
                or      a
                jr      nz, dl_go
                ld      a, l
                cp      4
                jr      nc, dl_go
                halt
                jr      d_loop
dl_go:          ld      hl, (FRAMES)
                ld      (LAST_TICK), hl
                ld      hl, (TICKS)
                inc     hl
                ld      (TICKS), hl
                call    view_snapshot   ; (the tiles before the tick: the torches' frames, game.asm's way)
                call    dirty_reset
                call    d_input
                call    d_tick
d_tend:         ld      a, (d_match)    ; (harness: the tick's end, the D line)
                cp      MATCH_QUIT
                jr      z, d_quit
                ld      a, (DRAWN_ROOM) ; the arena, once
                ld      hl, SHOWN_ROOM
                cp      (hl)
                jr      z, dl_t
                ld      (hl), a
                call    draw_room_full
                jr      dl_d
dl_t:           ld      a, 1            ; the torches' changed frames: into the shadow room, on the dirty list
                ld      (RR_SHONLY), a  ; (game.asm gmt3: drawn with the people over them)
                ld      hl, dirty_hook
                ld      (RR_HOOK), hl
                call    view_redraw
                xor     a
                ld      (RR_SHONLY), a
dl_d:           ld      hl, GUARD_REC + OF_CHARID      ; player 2 drawn as the kid (d_sdraw: its colours)
                ld      (hl), 0
                call    draw_objects
                call    hp_draw
                ld      hl, GUARD_REC + OF_CHARID
                ld      (hl), CHARID_SHADOW
d_done:         jr      d_loop          ; (harness: the tick drawn)
; d_quit: back to PRES's title (the level-start overlay's handoff; without the launcher, the harness: it stops here)
d_quit:         ld      a, GO_TITLE
                ld      (GAME_OVER), a
                call    game_over
dq_stop:        halt
                jr      dq_stop

P_main_end:
                if P_main_end > H_MAIN_END
                .error the duel's main piece is larger than the game's main loop
                endif

; ================================================================ P_ai: over the guard AI (block 2)
                org     H_AI
P_ai:
; d_entry: the arena (level 1 is started), the first round, the match loop
d_entry:        ld      sp, STACK
                xor     a
                ld      (SND_MODE), a   ; the silent sound model (duel-design 11.4)
                ld      (NEED_L1M), a   ; (no level 1 music crouch)
                ld      (TROBS_N), a    ; no tile animations but the torches (d_torches), no falling floors
                ld      (MOBS_N), a
                ld      (IS_SHOW_TIME), a
                ld      (EXIT_TIMER), a
                ld      (d_rounds), a
                ld      (d_score1), a
                ld      (d_score2), a
                ld      (d_result), a
                ld      (d_match), a
                call    erase_text
                ld      hl, LV_LINKS + (ARENA_ROOM - 1) * 4    ; the room's links: room 0, a wall on every side
                ld      b, 4
de_l:           ld      (hl), 0
                inc     hl
                djnz    de_l
                ld      hl, LV_GTILE    ; no guards
                ld      b, 24
de_g:           ld      (hl), 30
                inc     hl
                djnz    de_g
                ld      a, ARENA_ROOM
                ld      (DRAWN_ROOM), a
                ld      (NEXT_ROOM), a
                call    d_torches
                call    d_reset
                call    d_hash
                ld      hl, (FRAMES)
                ld      (LAST_TICK), hl
d_ready:        jp      d_loop          ; (harness: the state before the first tick)

; d_tick: one tick (duelsim DuelSim.step) with the input bytes d_in1, d_in2
d_tick:         xor     a
                ld      (HITP_DELTA), a
                ld      (GUARDHP_DELTA), a
                call    process_trobs   ; (the torches' flicker: prandom, which no logic reads; not hashed)
                ld      hl, GUARD_REC + OF_CHARID      ; (D11: the shadow sees the kid on every level)
                ld      (hl), CHARID_GUARD
                call    check_can_guard_see_kid
                ld      hl, GUARD_REC + OF_CHARID
                ld      (hl), CHARID_SHADOW
                call    loadkid_and_opp ; player 1
                ld      a, (d_in1)
                ld      hl, HITP_CURR
                call    d_frame
                call    savekid
d_mid:          ld      hl, (K_TICK)    ; (harness: the kid line)
                inc     hl
                ld      (K_TICK), hl
                call    d_swap          ; player 2: its block in, the kid's rules
                call    loadshad_and_opp
                xor     a
                ld      (K_CHARID), a
                inc     a
                ld      (OPP_REC + OF_CHARID), a
                ld      a, (KID_SWORD_STRIKE)
                push    af
                ld      a, (d_in2)
                ld      hl, GUARDHP_CURR
                call    d_frame
                pop     af
                ld      (KID_SWORD_STRIKE), a
                ld      a, CHARID_SHADOW
                ld      (K_CHARID), a
                call    saveshad
                call    d_swap
                call    check_sword_hurting
                call    d_hurt
                call    sword_vs_sword
                call    do_delta_hp_g
d_gline:        call    d_round         ; (harness: the G line)
                call    snd_next        ; (play_next_sound: the N line at snd_snap)
                call    loadkid         ; (KV = the kid for the drawing)
                jp      d_hash

; d_frame: SDLPoP play_kid_frame for Char (KV), Opp set: A = the input byte, HL = the character's hit points (D12)
d_frame:        ld      (df_in), a
                ld      (df_hp), hl
                call    load_fram_det_col
                ld      a, (K_ALIVE)    ; out of hit points: dead (duelsim duel_control)
                rla
                jr      nc, df1
                ld      hl, (df_hp)
                ld      a, (hl)
                or      a
                jr      nz, df1
                ld      (K_ALIVE), a
df1:            ld      hl, GRAB_TIMER
                ld      a, (hl)
                or      a
                jr      z, df2
                dec     (hl)
df2:            ld      hl, CTRL1       ; rest_ctrl_1
                ld      de, C_FWD
                ld      bc, 5
                ldir
                ld      a, (df_in)      ; the input byte: right over left, down over up
                ld      b, a
                ld      c, 0
                rrca
                jr      nc, df3
                dec     c
df3:            rrca
                jr      nc, df4
                ld      c, 1
df4:            ld      e, 0
                rrca
                jr      nc, df5
                dec     e
df5:            rrca
                jr      nc, df6
                ld      e, 1
df6:            ld      a, c
                ld      (C_X), a
                ld      a, e
                ld      (C_Y), a
                ld      a, b
                and     0x10
                jr      z, df7
                ld      a, C_HELD
df7:            ld      (C_SHIFT), a
                call    read_user_control
                call    user_control
                ld      hl, C_FWD       ; save_ctrl_1
                ld      de, CTRL1
                ld      bc, 5
                ldir
                ld      a, (K_ALIVE)    ; the death counter: no wait on a sound, no music, no text (duel-design 11.4)
                rla
                jr      c, df_body
                ld      a, (K_FRAME)
                cp      177
                jr      z, df8
                cp      178
                jr      z, df8
                cp      185
                jr      nz, df_body
df8:            ld      a, (K_ALIVE)
                cp      100
                jr      nc, df_body
                inc     a
                ld      (K_ALIVE), a
df_body:        ld      a, (K_ROOM)
                or      a
                ret     z
                call    play_seq
                call    fall_accel
                call    fall_speed
                call    load_frame_to_obj
                call    load_fram_det_col
                call    set_char_collision
                call    bump_into_opponent
                call    check_collisions
                call    check_bumped
                call    check_gate_push
                jp      check_action    ; (no check_press, spikes, chompers, knocks: the arena has none)
df_in:          db      0
df_hp:          dw      0

; d_hurt: check_sword_hurt the duel's way (D13, the user's change 2026-11-11: both hurt in one tick is a clash, nobody
; is hurt, both play attack_was_parried, the kid first; D10: the shadow hurt by the kid's rules and sound; D12: take_hp
; on its own hit points: the kid's path with the two exchanged)
d_hurt:         ld      a, (KID_REC + OF_ACTION)
                cp      AC_HURT
                jr      nz, dh1
                ld      a, (GUARD_REC + OF_ACTION)
                cp      AC_HURT
                jr      z, dh_clash
                call    loadkid
                call    hurt_by_sword
                jp      savekid
dh_clash:       call    loadkid
                call    dh_par
                call    savekid
                call    loadshad
                call    dh_par
                jp      saveshad
dh_par:         ld      a, SQ_ATTACK_PARRIED
                call    seqtbl_offset_char
                jp      play_seq
dh1:            ld      a, (GUARD_REC + OF_ACTION)
                cp      AC_HURT
                ret     nz
                call    loadshad
                call    dh_x
                xor     a
                ld      (K_CHARID), a
                call    hurt_by_sword
                ld      a, CHARID_SHADOW
                ld      (K_CHARID), a
                call    dh_x
                jp      saveshad
dh_x:           ld      hl, (HITP_CURR) ; HITP_CURR <-> GUARDHP_CURR, HITP_DELTA <-> GUARDHP_DELTA
                ld      a, (GUARDHP_CURR)
                ld      (HITP_CURR), a
                ld      a, l
                ld      (GUARDHP_CURR), a
                ld      a, (HITP_DELTA)
                ld      l, a
                ld      a, (GUARDHP_DELTA)
                ld      (HITP_DELTA), a
                ld      a, l
                ld      (GUARDHP_DELTA), a
                ret

; d_reset: a round's start (duelsim round_reset): both at their start tiles, standing, swords sheathed, full hit
; points, fresh blocks
d_reset:        ld      bc, P1_COL * 256 + 0           ; player 1: column, direction right; charid the kid
                ld      e, 0
                call    dr_char
                call    savekid
                ld      bc, P2_COL * 256 + 0xff        ; player 2: left, the shadow
                ld      e, CHARID_SHADOW
                call    dr_char
                call    saveshad
                call    loadkid_and_opp
                call    d_fresh         ; the blocks: player 1's (the globals), then player 2's
                call    d_swap
                call    d_fresh
                ld      a, ROUND_HP
                ld      hl, HITP_CURR
                ld      (hl), a
                inc     hl
                ld      (hl), a         ; HITP_MAX
                ld      (GUARDHP_CURR), a
                ld      (GUARDHP_MAX), a
                ld      (GHP_M), a      ; (the drawing: player 2's strip shows its hit points from the start)
                xor     a
                ld      (HITP_DELTA), a
                ld      (GUARDHP_DELTA), a
                ld      (SND_SCREAM), a
                ld      (KNOCK), a
                ld      (d_timer), a
                ld      hl, CAN_SEE     ; can_guard_see_kid .. droppedout (holding_sword, offguard: the block's)
                ld      b, DROPPEDOUT + 1 - CAN_SEE
drs_z:          ld      (hl), a
                inc     hl
                djnz    drs_z
                ret
; dr_char: Char (KV) = a fresh record: B = column, C = direction, E = charid; then the stand sequence played
dr_char:        ld      hl, KV
                push    bc
                ld      b, 16
drc_z:          ld      (hl), 0
                inc     hl
                djnz    drc_z
                pop     bc
                ld      a, e
                ld      (K_CHARID), a
                ld      a, c
                ld      (K_DIR), a
                ld      a, b
                ld      (K_COL), a
                add     a, FIRST_COL
                ld      hl, x_bump
                call    k_tbl
                add     a, TILE_SIZEX
                ld      (K_X), a
                ld      a, ARENA_ROW
                ld      (K_ROW), a
                inc     a
                ld      hl, y_land
                call    k_tbl
                ld      (K_Y), a
                ld      a, ARENA_ROOM
                ld      (K_ROOM), a
                ld      a, 0xff
                ld      (K_ALIVE), a
                ld      a, SQ_STAND
                call    seqtbl_offset_char
                jp      play_seq
; d_fresh: player 2's block fresh: ctrl1 released, grab_timer 0, have_sword 1, offguard 0, holding_sword 0, no collision
; rows (prev_collision_row -1, rooms -1, flags 0)
d_fresh:        ld      hl, d_blk2
                xor     a
                ld      b, 6
dfr1:           ld      (hl), a
                inc     hl
                djnz    dfr1
                inc     a
                ld      (hl), a         ; have_sword
                inc     hl
                dec     a
                ld      (hl), a         ; offguard
                inc     hl
                ld      (hl), a         ; holding_sword
                inc     hl
                dec     a
                ld      (hl), a         ; prev_collision_row
                inc     hl
                ld      c, 4
dfr2:           ld      b, 10
dfr3:           ld      (hl), 0xff      ; rooms
                inc     hl
                djnz    dfr3
                ld      b, 10
dfr4:           ld      (hl), 0         ; flags
                inc     hl
                djnz    dfr4
                dec     c
                jr      nz, dfr2
                ret
; d_swap: player 2's block (d_blk2) <-> the globals (duelsim swap_block)
d_swap:         ld      de, d_blk2
                ld      hl, d_blkmap
dsw_r:          ld      c, (hl)
                inc     hl
                ld      b, (hl)
                inc     hl
                ld      a, b
                or      c
                ret     z
                push    hl
                ld      a, (hl)
                ld      h, b
                ld      l, c
                ld      b, a
dsw_b:          ld      a, (de)
                ld      c, (hl)
                ld      (hl), a
                ld      a, c
                ld      (de), a
                inc     hl
                inc     de
                djnz    dsw_b
                pop     hl
                inc     hl
                jr      dsw_r
d_blkmap:       dw      CTRL1           ; ctrl1, grab_timer (KV + 24 .. 29)
                db      6
                dw      HAVE_SWORD
                db      1
                dw      OFFGUARD
                db      1
                dw      HOLDING_SWORD
                db      1
                dw      PREV_COLL_ROW
                db      1
                dw      PREV_ROOMS      ; the collision rows (KV + 96 .. 175)
                db      80
                dw      0
; d_hash: the state hash (duelsim state_bytes / hash16: 68 bytes, h = rotl16(h, 1) + byte) -> d_hashv
d_hash:         ld      hl, 0
                ld      ix, d_hashmap
dhs_r:          ld      e, (ix+0)
                ld      d, (ix+1)
                ld      a, d
                or      e
                jr      z, dhs_x
                ld      b, (ix+2)
                inc     ix
                inc     ix
                inc     ix
dhs_b:          add     hl, hl          ; rotate left by one
                jr      nc, dhs_1
                inc     l
dhs_1:          ld      a, (de)
                add     a, l
                ld      l, a
                jr      nc, dhs_2
                inc     h
dhs_2:          inc     de
                djnz    dhs_b
                jr      dhs_r
dhs_x:          ld      (d_hashv), hl
                ret
d_hashmap:      dw      KID_REC         ; the kid's and the shadow's records
                db      32
                dw      HITP_CURR       ; hitp_curr, hitp_max
                db      2
                dw      GUARDHP_CURR    ; guardhp_curr, guardhp_max
                db      2
                dw      CAN_SEE
                db      1
                dw      JUSTBLOCKED     ; justblocked, guard_refrac, kid_sword_strike, guard_notice_timer, is_guard_notice
                db      5
                dw      DROPPEDOUT      ; droppedout, guard_skill
                db      2
                dw      CTRL1           ; player 1's block: ctrl1, grab_timer
                db      6
                dw      HAVE_SWORD
                db      1
                dw      OFFGUARD
                db      1
                dw      HOLDING_SWORD
                db      1
                dw      d_blk2          ; player 2's block (its first 9 bytes)
                db      9
                dw      d_rounds        ; the round state
                db      6
                dw      0
; the duel's state (the round state in the hash's order)
d_rounds:       db      0
d_score1:       db      0
d_score2:       db      0
d_timer:        db      0
d_result:       db      0
d_match:        db      0
d_in1:          db      0
d_in2:          db      0
d_hashv:        dw      0
d_blk2:         ds      90              ; player 2's block: ctrl1 (5), grab_timer, have_sword, offguard, holding_sword,
                                        ; prev_collision_row, the collision rows (80, kid.asm PREV_ROOMS .. ABOVE_FLAGS)
P_ai_end:
                if P_ai_end > H_AI_END
                .error the duel's piece P_ai is larger than its hole (the guard AI)
                endif

; ================================================================ P_kt: over kid.asm kid_tick
                org     H_KT
P_kt:
; d14 (kid.asm bumped, pushed left into a wall, duel_d14): D14, a wall of room 0 left of column 0 is the room's own
; column 9 (as SDLPoP does for the right edge)
d14:            ld      a, (TILE_COL)
                dec     a
                cp      0xff
                jr      nz, d14x
                ld      a, (CURR_ROOM)
                or      a
                ld      a, 0xff
                jr      nz, d14x
                ld      a, (K_ROOM)
                ld      (CURR_ROOM), a
                ld      a, 9
d14x:           ld      (TILE_COL), a
                ld      c, a
                jp      duel_d14r
; d15 (kid.asm is_obstacle's xpos_in_drawn_room, duel_d15): D15, room 0's column 0 is the right neighbour's
d15:            ld      a, (CURR_ROOM)
                or      a
                jp      nz, xpos_in_drawn_room
                ld      a, (TILE_COL)
                or      a
                jp      nz, xpos_in_drawn_room
                ld      de, TILE_SIZEX * 10
                add     hl, de
                ret
; d_sdraw (overlay.asm's spr_draw calls, duel_sd1 / duel_sd2): HL = the descriptor; the guard's slot (player 2) is
; drawn with its colours changed by one plane operation on the drawn pixels (DUEL_LOOK, below), else spr_draw. The same
; kernel as gfx.asm spr_draw (its own patched operands). The black outline (colour 8: plane IV alone) stays as it is in
; every variant. The planes: I = bit 0 (B), II = bit 1 (R), III = bit 2 (G), IV = bit 3 (the intensity). Extra T a
; drawn cell against spr_draw's cell (~110 T): 0 +117, 1 +32, 2 +16, 3 +16, 4 -7, 5 +20 (a kid image has ~100-290 cells,
; ~150 drawn: 0 costs ~0.25 frames a tick, the others at most ~0.1).
;   0 (default, the user's choice 2026-11-11) a blue suit, grey hair: where plane I (B) is set, planes II and III (R,
;     G) cleared (the kid's white 15 -> light blue 9, light grey 7 -> blue 1); where R alone of B, R, G is set (the hair,
;     colours 2 and 10) R cleared and plane IV (I) set: grey 8. The skin 6 and the outline 8 (the only other colours
;     of the kid's images) unchanged. Per cell: R' = R & G & ~B, G' = G & ~B, I' = I | (R & ~G & ~B), with ~B in IXL
;     and G | ~(drawn) in IXH, then the hair in IXH
;   1 a blue suit only (the hair as it is): R' = R & ~B, G' = G & ~B (~B kept in IXL)
;   2 R <-> B: planes I and II swapped (white stays white, the skin cyan, the hair blue)
;   3 R <-> G: planes II and III swapped (the hair green)
;   4 no B: plane I cleared (a golden outfit, the skin as it is)
;   5 I inverted: plane IV XOR (planes I | II | III), i.e. XOR 8 on every drawn pixel but the outline (light grey
;     clothes, light yellow skin, light red hair)
; Colour 8 (plane IV alone) is drawn as any other colour (the kernel's transparency is "no plane set", colour 0): the
; images' black is stored as 8 and shows dark grey, the grey hair is that grey.
                if not defined DUEL_LOOK
DUEL_LOOK       equ     0
                endif
d_sdraw:        push    hl
                ld      de, SPR_G
                or      a
                sbc     hl, de
                pop     hl
                jp      nz, spr_draw
                push    hl
                pop     iy
                xor     a
                call    sd_bounds       ; (returns from here when nothing is visible)
                push    ix              ; (IXL, IXH: DUEL_LOOK's masks; the caller keeps IX)
                ld      a, (V_PX)
                ld      (dsd_px + 1), a
                ld      (dsd_dst + 1), a
                add     a, a
                add     a, a
                ld      c, a
                ld      a, (sd_stride + 1)      ; (sd_bounds patched the kernel's: ow * 4)
                sub     c
                ld      (dsd_stride + 1), a
                ld      a, (V_N)
                exx
                ld      b, a
                exx
                ld      hl, (V_ROWOFF)
dsdrow:
dsd_px:         ld      c, 0
dsdcell:        ld      a, (hl)
                if DUEL_LOOK = 1
                cpl
                ld      ixl, a          ; ~(plane I): the suit's mask
                cpl
                endif
                inc     l
                or      (hl)
                inc     l
                or      (hl)
                if DUEL_LOOK = 5
                ld      (dsd_q + 1), a  ; planes I | II | III: the XOR on plane IV
                endif
                inc     l
                or      (hl)
                jr      z, dsdempty
                cpl
                ld      b, a
                dec     l
                dec     l
                dec     l
                if DUEL_LOOK = 0
                ld      a, (hl)
                cpl
                ld      ixl, a          ; ~(plane I)
                inc     l
                inc     l
                ld      a, (hl)
                or      b
                ld      ixh, a          ; plane III | the undrawn bits
                dec     l
                dec     l
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                and     ixl
                and     ixh             ; plane II: R & G & ~B
                ld      (de), a
                ld      a, ixh
                cpl
                and     ixl
                and     (hl)
                ld      ixh, a          ; the hair: R & ~G & ~B
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                and     ixl             ; plane III: G & ~B
                ld      (de), a
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                or      ixh             ; plane IV: I | the hair
                ld      (de), a
                endif
                if DUEL_LOOK = 1
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                and     ixl             ; plane II: not where plane I is
                ld      (de), a
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                and     ixl             ; plane III: not where plane I is
                ld      (de), a
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                endif
                if DUEL_LOOK = 2
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a               ; plane I into II
                inc     l
                dec     d
                dec     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a               ; plane II into I
                inc     l
                inc     d
                inc     d
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                endif
                if DUEL_LOOK = 3
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                inc     l
                inc     d
                inc     d
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a               ; plane II into III
                inc     l
                dec     d
                dec     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a               ; plane III into II
                inc     l
                inc     d
                inc     d
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                endif
                if DUEL_LOOK = 4
                ld      a, (de)
                and     b
                ld      (de), a               ; plane I cleared
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                endif
                if DUEL_LOOK = 5
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
dsd_q:          xor     0               ; (patched: planes I | II | III; within the drawn bits: or = xor)
                ld      (de), a
                endif
                if DUEL_LOOK > 5
                .error DUEL_LOOK: 0 to 5
                endif
                inc     hl
                ld      a, d
                sub     6
                ld      d, a
                inc     e
                dec     c
                jp      nz, dsdcell
                jr      dsdrowend
dsdempty:       inc     hl
                inc     e
                dec     c
                jp      nz, dsdcell
dsdrowend:
dsd_stride:     ld      bc, 0
                add     hl, bc
                ld      a, e
dsd_dst:        sub     0
                add     a, CW
                ld      e, a
                jr      nc, dsd_nc
                inc     d
dsd_nc:         exx
                dec     b
                exx
                jp      nz, dsdrow
                pop     ix              ; (the caller's descriptor pointer)
                ret
P_kt_end:
                if P_kt_end > H_KT_END
                .error the duel's piece P_kt is larger than its hole (kid_tick)
                endif

; ================================================================ P_tick: over guard.asm tick_pre .. check_skel
                org     H_TICK
P_tick:
; d_input: d_in1, d_in2 (the input bytes) from the keys and the joysticks, or the harness's script
d_input:        ld      hl, (d_script)
                ld      a, h
                or      l
                jr      z, di_live
                ex      de, hl
                ld      a, RD_LV_PAGE
                call    far_seek
                in      a, (RD_DATA)
                ld      (d_in1), a
                in      a, (RD_DATA)
                ld      (d_in2), a
                ld      hl, (d_script)
                inc     hl
                inc     hl
                ld      (d_script), hl
                ret
di_live:        call    read_inputs     ; (game.asm: KEYMAT, player 1's INPUT: cursor keys, SHIFT, joystick 1)
                ld      a, (KEYMAT + 8) ; BREAK (8/7): quit
                and     0x80
                rrca
                rrca
                ld      b, a
                ld      a, (KEYMAT + 0) ; ENTER (0/0): rematch
                and     1
                rrca
                rrca
                or      b
                ld      hl, INPUT
                or      (hl)
                ld      (d_in1), a
                in      a, (PORT_JOY2)  ; player 2: joystick 2 (up, down, left, right, fire in bits 0-4, low active)
                cpl
                ld      c, a
                and     0x0c            ; left, right -> bits 0, 1
                rrca
                rrca
                ld      b, a
                ld      a, c
                and     0x03            ; up, down -> bits 2, 3
                add     a, a
                add     a, a
                or      b
                ld      b, a
                ld      a, c
                and     0x10            ; fire
                or      b
                ld      b, a
                ld      hl, di_keys     ; W A S D Q
                ld      c, 1
di_k:           ld      a, (hl)
                inc     hl
                add     a, KEYMAT % 256
                ld      e, a
                ld      d, KEYMAT / 256
                ld      a, (de)
                and     (hl)
                inc     hl
                jr      z, di_k1
                ld      a, b
                or      c
                ld      b, a
di_k1:          sla     c
                bit     5, c
                jr      z, di_k
                ld      a, b
                ld      (d_in2), a
                ret
di_keys:        db      4, 0x80, 4, 0x10, 2, 0x02, 2, 0x20, 2, 0x80     ; A left, D right, W up, S down, Q fire

; d_torches: the arena's torches start flickering as at a room entry (genter.asm anim_tile_modif's torch part: a
; random first frame, a trob each; the room on the left is room 0 here: none there)
d_torches:      xor     a
                ld      (dt_pos), a
dt_l:           ld      a, ARENA_ROOM
                ld      (CURR_ROOM), a
                ld      a, (dt_pos)
                call    get_curr_tile
                cp      T_TORCH
                jr      z, dt_t
                cp      T_TORCH_DEBRIS
                jr      nz, dt_n
dt_t:           ld      a, 8
                call    prandom
                ld      b, a
                ld      a, (dt_pos)
                ld      c, a
                ld      a, ARENA_ROOM
                call    o_ptrs
                ld      a, b
                ld      (de), a
                ld      b, ARENA_ROOM
                ld      a, (dt_pos)
                ld      c, a
                ld      a, 1
                call    add_trob
dt_n:           ld      hl, dt_pos
                inc     (hl)
                ld      a, (hl)
                cp      30
                jr      nz, dt_l
                ret
dt_pos:         db      0

; d_round: the rounds (duelsim round_step), after the tick's hit points are final
d_round:        ld      a, (d_in1)
                ld      hl, d_in2
                or      (hl)
                ld      b, a
                ld      a, (d_match)
                bit     IN_QUIT, b
                jr      z, dr1
                cp      MATCH_QUIT
                jr      z, dr1
                ld      a, MATCH_QUIT
                ld      (d_match), a
                ret
dr1:            or      a
                jr      z, dr_on
                cp      MATCH_QUIT
                ret     z
                bit     IN_REMATCH, b
                ret     z
                xor     a               ; rematch
                ld      (d_rounds), a
                ld      (d_score1), a
                ld      (d_score2), a
                ld      (d_result), a
                ld      (d_match), a
                jp      d_reset
dr_on:          ld      a, (d_timer)
                or      a
                jr      nz, dr_tm
                ld      c, a            ; C: bit 0 player 1 at 0, bit 1 player 2
                ld      a, (HITP_CURR)
                or      a
                jr      nz, dr2
                inc     c
dr2:            ld      a, (GUARDHP_CURR)
                or      a
                jr      nz, dr3
                set     1, c
dr3:            ld      a, c
                or      a
                ret     z
                cp      3               ; the result: 3 a draw, 1 player 1 (C = 2), 2 player 2 (C = 1)
                jr      z, dr4
                xor     3
dr4:            ld      (d_result), a
                ld      hl, d_rounds
                inc     (hl)
                cp      3
                jr      z, dr5
                ld      hl, d_rounds    ; (d_score1 = d_rounds + 1, d_score2 + 2)
                ld      e, a
                ld      d, 0
                add     hl, de
                inc     (hl)
dr5:            ld      a, ROUND_END_TICKS
                ld      (d_timer), a
                ret
dr_tm:          dec     a
                ld      (d_timer), a
                ret     nz
                ld      a, (d_score1)
                cp      WINS
                ld      a, 1
                jr      nc, dr_end
                ld      a, (d_score2)
                cp      WINS
                ld      a, 2
                jr      nc, dr_end
                jp      d_reset
dr_end:         ld      (d_match), a
                ret

; d_ppchar (overlay.asm people_place's calls of pp_char, duel_pp1 / duel_pp2): the blades (the user's choice
; 2026-11-11, docs/duel-design.md 12.8): a character is drawn with another kid frame, body and sword together (the hilt
; stays in the hand), so that a parry's blades meet and the en-garde blades sit at two heights. Drawing only: KV is the
; drawing's copy of the record here (people_place restores it from PP_SAVE), the logic never sees it. B = the slot (0
; player 1, 2 player 2), A = the hit point delta (kept)
d_ppchar:       push    af
                ld      hl, dpp_p1
                ld      a, b
                or      a
                jr      z, dpp_l
                ld      hl, dpp_p2
dpp_l:          ld      a, (hl)
                or      a
                jr      z, dpp_x
                inc     hl
                ld      c, a
                ld      a, (K_FRAME)
                cp      c
                ld      a, (hl)
                inc     hl
                jr      nz, dpp_l
                ld      (K_FRAME), a
dpp_x:          pop     af
                jp      pp_char
dpp_p1:         db      161, 158, 0                             ; player 1: the parry (161) as en garde (158)
dpp_p2:         db      161, 157, 158, 157, 170, 157, 171, 157, 0   ; player 2: the parry and en garde as 157

P_tick_end:
                if P_tick_end > H_TICK_END
                .error the duel's piece P_tick is larger than its hole (tick_pre .. check_skel)
                endif

; ================================================================ the patch sites
                org     H_D14
P_d14:          jp      d14
P_d14_end:
                org     H_D15
P_d15:          dw      d15
P_d15_end:
                org     H_SD1
P_sd1:          dw      d_sdraw
P_sd1_end:
                org     H_SD2
P_sd2:          dw      d_sdraw
P_sd2_end:
                org     H_PP1
P_pp1:          dw      d_ppchar
P_pp1_end:
                org     H_PP2
P_pp2:          dw      d_ppchar
P_pp2_end:
