; ---------------------------------------------------------------- M6: the guard and sword fighting
; Z80 port of the guard logic of tools/kidsim.py (SDLPoP seg000/002/003/004/005/006): two characters, Kid and
; Guard, as SDLPoP keeps them. KV (kid.asm K_*) is Char, the character being played; KID_REC and GUARD_REC are
; the two records (16 bytes in char_type order: frame x y direction curr_col curr_row action fall_x fall_y room
; repeat charid sword alive curr_seq), OPP_REC is Opp, the copy of the other one. The kid routines of kid.asm and
; objects.asm work on Char for both. Between ticks KV holds the Kid (the drawing code reads it); Char as SDLPoP
; left it at the end of the tick is kept in CHAR_SAVE for the few places that read it at the next tick start
; (timers on level 8, check_skel on level 3).
;
; Tick order (kidsim step / SDLPoP play_frame): tick_pre (deltas, timers, do_mobs, process_trobs, check_skel,
; check_can_guard_see_kid, loadkid_and_opp), the kid's frame (kid.asm kid_tick: control, sequence, collisions;
; savekid; the kid trace snapshot), tick_post (play_guard_frame, check_sword_hurting, check_sword_hurt,
; do_delta_hp, exit_room, check_the_end, check_guard_fallout, the guard trace snapshot G_SNAP, tick_end).
;
; Harness options (guard_opts, set before the program runs; 0 = the real game): bit 0 = no guards (all guards are
; removed at the first control tick of a level, SDLPoP's POP800_NOGUARDS hook), bit 1 = the kid has the sword;
; then a count and up to GOPT_MAX placed guards (room, tile, direction, skill, colour) written into the level's
; guard arrays at the level start (SDLPoP's pop800_level_start hook).
;
; The shadow's scripted moves (autocontrol_shadow) and the mirror are in the events overlay (src/m4/events.asm).
; Jaffar plays as a normal guard (kidsim autocontrol_Jaffar). No sounds (the sound model: the feather fall music).

DIR_NONE        equ     0x56
CHARID_SHADOW   equ     1
CHARID_GUARD    equ     2
CHARID_SKELETON equ     4
CHARID_MOUSE    equ     24
AC_HURT         equ     99
SEQ_BASE        equ     0x196e          ; level guards_seq_lo/hi hold SDLPoP's seq address (offset + SEQ_BASE)
T_SKELETON      equ     21
; record offsets
OF_FRAME        equ     0
OF_X            equ     1
OF_Y            equ     2
OF_DIR          equ     3
OF_COL          equ     4
OF_ROW          equ     5
OF_ACTION       equ     6
OF_FALLX        equ     7
OF_FALLY        equ     8
OF_ROOM         equ     9
OF_CHARID       equ     11
OF_SWORD        equ     12
OF_ALIVE        equ     13
OF_SEQ          equ     14
; the level's guard arrays (24 rooms each)
LV_GTILE        equ     LEVEL + 2119
LV_GDIR         equ     LEVEL + 2143
LV_GX           equ     LEVEL + 2167
LV_GSEQLO       equ     LEVEL + 2191
LV_GSKILL       equ     LEVEL + 2215
LV_GSEQHI       equ     LEVEL + 2239
LV_GCOLOR       equ     LEVEL + 2263
; sequences
SQ_STAND        equ     2
SQ_DRAW_SWORD   equ     55
SQ_GUARD_FWD_SWORD equ  56
SQ_BACK_WITH_SWORD equ  57
SQ_GUARD_STRIKE equ     58
SQ_TURN_WITH_SWORD equ  60
SQ_PARRY_AFTER_STRIKE equ 61
SQ_PARRY        equ     62
SQ_GUARD_ACTIVE_FALL equ 63
SQ_PUSHED_BACK_SWORD equ 64
SQ_BUMP_FWD_SWORD equ   65
SQ_STRIKE_AFTER_PARRY equ 66
SQ_ATTACK_PARRIED equ   69
SQ_HIT_BY_SWORD equ     74
SQ_STRIKE       equ     75
SQ_GUARD_STAND_INACTIVE equ 77
SQ_STAND_FLIPPED equ    80
SQ_KID_PUSHED_OFF equ   81
SQ_GUARD_PUSHED_OFF equ 82
SQ_GUARD_FALL   equ     83
SQ_STABBED      equ     85
SQ_FORWARD_WITH_SWORD equ 86
SQ_GUARD_INACTIVE equ   87
SQ_SKEL_WAKE    equ     88
SQ_TURN_DRAW_SWORD equ  89
SQ_EN_GARDE     equ     90
SQ_PUT_SWORD_AWAY equ   92
SQ_PUT_SWORD_FAST equ   93
SQ_MOUSE_FORWARD equ    105
SQ_MOUSE_STAND  equ     107
GOPT_MAX        equ     4

; ================================================================ records (seg006 loadkid ... saveshad_and_opp)
loadkid:        ld      hl, KID_REC
                jr      gld
loadshad:       ld      hl, GUARD_REC
gld:            ld      de, KV
                jr      gcp16
savekid:        ld      de, KID_REC
                jr      gsv
saveshad:       ld      de, GUARD_REC
gsv:            ld      hl, KV
                jr      gcp16
loadkid_and_opp:
                call    loadkid
                ld      hl, GUARD_REC
                ld      de, OPP_REC
                jr      gcp16
loadshad_and_opp:
                call    loadshad
                ld      hl, KID_REC
                ld      de, OPP_REC
                jr      gcp16
savekid_and_opp:
                call    savekid
                ld      hl, OPP_REC
                ld      de, GUARD_REC
                jr      gcp16
saveshad_and_opp:
                call    saveshad
                ld      hl, OPP_REC
                ld      de, KID_REC
gcp16:          ldi                     ; (16 x ldi: a quarter faster than ldir)
                ldi
                ldi
                ldi
                ldi
                ldi
                ldi
                ldi
                ldi
                ldi
                ldi
                ldi
                ldi
                ldi
                ldi
                ldi
                ret

; ================================================================ helpers
; scmp: HL vs DE, signed (small values): S flag set (jp m) if HL < DE; HL kept
scmp:           push    hl
                or      a
                sbc     hl, de
                pop     hl
                ret
; char_opp_dist: HL = distance to Opp (> 0 in front of Char, < 0 behind, 999 another room)
char_opp_dist:  ld      a, (OPP_REC + OF_ROOM)
                ld      hl, K_ROOM
                cp      (hl)
                jr      z, cod1
                ld      hl, 999
                ret
cod1:           ld      a, (OPP_REC + OF_X)
                ld      l, a
                ld      h, 0
                ld      a, (K_X)
                ld      e, a
                ld      d, 0
                or      a
                sbc     hl, de
                ld      a, (K_DIR)
                bit     7, a
                jr      z, cod2
                ex      de, hl          ; facing left: -distance
                ld      hl, 0
                or      a
                sbc     hl, de
cod2:           bit     7, h
                ret     nz
                ld      a, (OPP_REC + OF_DIR)
                ld      e, a
                ld      a, (K_DIR)
                cp      e
                ret     z
                ld      de, 13
                add     hl, de
                ret
; xbump16: A = column + 5 -> HL = x_bump[A] (x_bump[0] = -12)
xbump16:        or      a
                jr      z, xb0
                ld      hl, x_bump
                call    k_tbl
                ld      l, a
                ld      h, 0
                ret
xb0:            ld      hl, -12
                ret
set_y_land:     ld      a, (K_ROW)
                inc     a
                ld      hl, y_land
                call    k_tbl
                ld      (K_Y), a
                ret
; guard_type: A = SDLPoP tbl_guard_type of the level (0 guard, 1 fat, 2 skeleton, 3 vizier, 4 shadow, 0xff none)
guard_type:     ld      a, (level_number)
                and     15
                ld      hl, tbl_guard_type
                jp      k_tbl
get_tile_infrontof2_char:
                call    dir_front
                add     a, a
                ld      hl, K_COL
                add     a, (hl)
                ld      (INFRONTX), a
                ld      c, a
                ld      a, (K_ROW)
                ld      b, a
                ld      a, (K_ROOM)
                jp      k_get_tile
bumped_sound:   ld      a, 1
                ld      (IS_GUARD_NOTICE), a
                ld      a, 8
                jp      snd_play
clear_char:     ld      a, DIR_NONE
                ld      (K_DIR), a
                xor     a
                ld      (K_ALIVE), a
                ld      (K_ACTION), a
                ld      (GUARDHP_CURR), a
                ret
on_guard_killed:
                ld      a, (level_number)
                or      a
                jr      nz, ogk1
                ld      (DEMO_INDEX), a         ; demo level
                ld      (DEMO_TIME), a
                inc     a
                ld      (CHECKPOINT), a
                ret
ogk1:           cp      13
                jr      nz, ogk2
                ld      a, 1                    ; Jaffar killed: flash, show the time, the exit door opens
                ld      (IS_SHOW_TIME), a
                inc     a
                ld      (LEVELDOOR_OPEN), a
                ld      a, 43
                call    snd_play
                ld      bc, 18 * 256 + COLOR_WHITE
; set_flash: C = colour, B = ticks
set_flash:      ld      (FLASH_COLOR), bc       ; (FLASH_TIME follows FLASH_COLOR)
                ret
ogk2:           ld      a, (K_CHARID)           ; a guard's death (not the shadow's): the victory music
                cp      CHARID_SHADOW
                ret     z
                ld      a, 37
                jp      snd_play
; ================================================================ hooks called from kid.asm / objects.asm
; load_frame for charid != kid: the guard's frame table (kid table for the mouse, the shadow's kid frames)
load_frame_ch:  cp      CHARID_MOUSE
                jp      z, lf_kid
                cp      CHARID_SHADOW
                ld      a, (K_FRAME)
                jr      nz, lfc_g
                cp      150
                jp      c, lf_kid
                cp      190
                jp      nc, lf_kid
                jr      lfc_i
lfc_g:          cp      102                     ; guard falling frames
                jr      c, lfc_i
                cp      107
                jr      nc, lfc_i
                add     a, 70
lfc_i:          sub     149
                jr      c, lfc_none
                cp      41
                jr      nc, lfc_none
                ld      l, a
                ld      h, 0
                ld      d, h
                ld      e, l
                add     hl, hl
                add     hl, hl
                add     hl, de
                ld      de, RD_FRAMES_GUARD
                add     hl, de
                ex      de, hl
                ld      a, RD_LOGIC_PAGE
                call    far_seek
                ld      hl, CF_IMG
                ld      bc, 0x0500 | RD_DATA
                inir
                ret
lfc_none:       ld      hl, CF_IMG
                ld      (hl), 255
                inc     hl
                xor     a
                ld      (hl), a
                inc     hl
                ld      (hl), a
                inc     hl
                ld      (hl), a
                inc     hl
                ld      (hl), a
                ret
; set_char_collision for an image of chtab 5 (frame sword byte 0xC0): the level's guard set sizes
scc_guard:      cp      0xc0
                jp      nz, scc_noimg
                call    guard_type
                cp      5
                jp      nc, scc_noimg
                ld      b, a
                ld      a, (OBJ_ID)
                cp      GUARD_WH_N
                jp      nc, scc_noimg
                ld      l, a
                ld      h, 0
                ld      de, GUARD_WH_N
                inc     b
sccg1:          dec     b
                jr      z, sccg2
                add     hl, de
                jr      sccg1
sccg2:          add     hl, hl
                ld      de, RD_GUARD_WH         ; (logic.bin guard_wh)
                add     hl, de
                ex      de, hl
                call    rd_logic
                ld      (CHAR_WH), a
                in      a, (RD_DATA)
                ld      (CHAR_H), a
                jp      scc1
; take_hp for the guard: B = count -> A = 1 if that kills
take_hp_g:      ld      a, (GUARDHP_CURR)
                cp      b
                jr      z, thg_dead
                jr      c, thg_dead
                ld      a, b
                neg
                ld      (GUARDHP_DELTA), a
                xor     a
                ret
thg_dead:       neg
                ld      (GUARDHP_DELTA), a
                ld      a, 1
                ret
; do_delta_hp: the kid's and the guard's hit points (level 12: hurting the shadow hurts the kid)
do_delta_hp_g:  ld      a, (OPP_REC + OF_CHARID)
                cp      CHARID_SHADOW
                jr      nz, ddg1
                ld      a, (level_number)
                cp      12
                jr      nz, ddg1
                ld      a, (GUARDHP_DELTA)
                or      a
                jr      z, ddg1
                ld      (HITP_DELTA), a
ddg1:           call    do_delta_hp
                ld      a, (GUARDHP_DELTA)
                ld      hl, GUARDHP_CURR
                add     a, (hl)
                bit     7, a
                jr      z, ddg2
                xor     a
ddg2:           ld      hl, GUARDHP_MAX
                cp      (hl)
                jr      c, ddg3
                ld      a, (hl)
ddg3:           ld      (GUARDHP_CURR), a
                ret
; control_standing (after the item check): the guard draws, the kid draws or backs off when the guard sees him
cs_guard:       ld      a, (K_CHARID)
                or      a
                jr      z, csg1
                ld      a, (C_DOWN)
                cp      C_HELD
                jr      nz, csg1
                ld      a, (C_FWD)
                cp      C_HELD
                jp      z, draw_sword
csg1:           ld      a, (HAVE_SWORD)
                or      a
                jp      z, cs_shift
                ld      a, (OFFGUARD)
                or      a
                jr      z, csg2
                ld      a, (C_SHIFT)
                bit     7, a
                jp      z, cs_noshift           ; offguard, button not held: past the shift branch
csg2:           ld      a, (CAN_SEE)
                cp      2
                jr      nc, csg3
                xor     a
                ld      (OFFGUARD), a
                jp      cs_shift
csg3:           call    char_opp_dist
                ld      de, -10
                call    scmp
                jp      m, cs_shift
                ld      de, 90
                call    scmp
                jp      p, cs_shift
                ld      a, 1
                ld      (HOLDING_SWORD), a
                ld      de, -6
                call    scmp
                jp      m, csg4                 ; -10..-7
                bit     7, h
                jp      nz, back_pressed        ; -6..-1
csg4:           ld      a, (OPP_REC + OF_CHARID)
                cp      CHARID_SHADOW
                jp      nz, draw_sword
                ld      a, (OPP_REC + OF_ACTION)
                cp      AC_MIDAIR
                jr      z, csg5
                ld      a, (OPP_REC + OF_FRAME)
                cp      107
                jp      c, draw_sword
                cp      118
                jp      nc, draw_sword
csg5:           xor     a
                ld      (OFFGUARD), a
                jp      cs_shift
; back_pressed (after release_arrows): turn, or turn and draw when the guard is behind him
back_pressed_g: ld      a, (HAVE_SWORD)
                or      a
                jr      z, bpg_turn
                ld      a, (CAN_SEE)
                cp      2
                jr      c, bpg_turn
                call    char_opp_dist
                ld      de, 1
                call    scmp
                jp      p, bpg_turn
                call    distance_to_edge_weight
                cp      2
                jr      c, bpg_turn
                ld      a, 2
                ld      (K_SWORD), a
                xor     a
                ld      (OFFGUARD), a
                ld      a, SQ_TURN_DRAW_SWORD
                jp      seqtbl_offset_char
bpg_turn:       ld      a, SQ_TURN
                jp      seqtbl_offset_char
; bumped_floor with the sword drawn: K_TMP3 = push direction
bfl_sword:      ld      a, (K_DIR)
                ld      b, a
                ld      a, (K_TMP3)
                cp      b
                jr      nz, bfs_back
                ld      a, SQ_BUMP_FWD_SWORD
                call    seqtbl_offset_char
                call    play_seq
                ld      a, 1
                call    char_dx_forward
                ld      (K_X), a
                ret
bfs_back:       ld      a, SQ_PUSHED_BACK_SWORD
                call    seqtbl_offset_char
                call    play_seq
                jp      bumped_sound
; start_fall, frames >= 86 (A = frame): with the sword (150..179) the guard or the kid is pushed off the ledge
sf_more:        cp      150
                jp      c, sf_fall
                cp      180
                jp      nc, sf_fall
                ld      a, (K_CHARID)
                cp      CHARID_GUARD
                jr      nz, sfm_kid
                ld      a, (K_ROW)
                cp      3
                jr      nz, sfm1
                ld      a, (K_COL)
                cp      10
                jp      z, clear_char
sfm1:           ld      a, (K_FALLX)
                bit     7, a
                jr      z, sfm_gf
                call    sfm_edge
                ld      a, SQ_GUARD_PUSHED_OFF
                jp      sf_go
sfm_gf:         xor     a
                ld      (DROPPEDOUT), a
                ld      a, SQ_GUARD_FALL
                jp      sf_go
sfm_kid:        ld      a, 1
                ld      (DROPPEDOUT), a
                call    sfm_edge
                ld      a, SQ_KID_PUSHED_OFF
                jp      sf_go
sfm_edge:       ld      a, (K_DIR)              ; facing left near the edge: 5 back
                bit     7, a
                ret     z
                call    distance_to_edge_weight
                cp      8
                ret     nc
                ld      a, -5
                call    char_dx_forward
                ld      (K_X), a
                ret
; land, alive (and not spiked): soft (1 row), medium (2 rows; a guard dies), else dead
land_alive:     ld      a, (K_FALLY)
                cp      22
                jr      c, la_soft
                cp      33
                jp      nc, ld_dead
                ld      a, (K_CHARID)
                cp      CHARID_SHADOW
                jr      z, la_soft
                cp      CHARID_GUARD
                jp      z, ld_dead
                ld      a, 1
                call    take_hp
                or      a
                jr      nz, la_crush
                ld      a, 16                   ; medium land
                call    snd_play
                ld      a, 1
                ld      (IS_GUARD_NOTICE), a
                ld      a, SQ_MEDIUM_LAND
                jp      ld_go
la_crush:       call    snd_play                ; (A = 0: crushed)
                ld      a, SQ_CRUSHED
                jp      ld_go
la_soft:        ld      a, (K_CHARID)
                cp      CHARID_GUARD
                jr      nc, la_g
                ld      a, (K_SWORD)
                cp      2
                jr      z, la_g
                ld      b, SQ_SOFT_LAND
                jr      la_n
la_g:           ld      a, 2
                ld      (K_SWORD), a
                ld      b, SQ_GUARD_ACTIVE_FALL
la_n:           ld      a, (K_CHARID)
                or      a
                jr      nz, la_go
                ld      a, 17                   ; the kid's soft land
                call    snd_play
                ld      a, 1
                ld      (IS_GUARD_NOTICE), a
la_go:          ld      a, b
                jp      ld_go
; leave_room's level specials before the room change (A = leave direction 0 left, 1 right, 2 up, 3 down): lrs_body (the
; guard-enter overlay, src/m4/genter.asm, through its stub in ovl.asm) does the specials and returns A = the direction with
; CY = the exit button must be triggered first (the level door open: trigger_button is the events overlay, which a W1
; overlay cannot call), or A = 0xfe (the level 6 falling exit: leave_room's result)
lr_special:     call    lrs_body
                jr      c, lrs_trig
                cp      0xfe
                ret     z
                jp      goto_other_room
lrs_trig:       push    af
                ld      b, 0
                ld      c, 0xff
                xor     a
                call    trigger_button
                pop     af
                jp      goto_other_room
; tick 0 of a level with the guards off (harness): the guard and all the level's guards go
guards_off_chk: ld      a, (guard_opts)
                and     1
                ret     z
                ld      hl, (K_TICK)
                ld      a, h
                or      l
                ret     nz
                ld      a, DIR_NONE
                ld      (GUARD_REC + OF_DIR), a
                xor     a
                ld      (GUARD_REC + OF_ROOM), a
                ld      hl, LV_GTILE
                ld      b, 24
goc1:           ld      (hl), 30
                inc     hl
                djnz    goc1
                ret

; ================================================================ the tick
; tick_pre: from the tick start to the kid's frame (Char = Kid on return, Opp = Guard)
tick_pre:       xor     a
                ld      (HITP_DELTA), a
                ld      (GUARDHP_DELTA), a
                call    timers
                ld      a, (MOBS_N)
                ld      (tp_mobs), a
                call    do_mobs
                call    savekid                 ; (a falling floor may have hit the kid)
                ld      a, (tp_mobs)
                or      a
                jr      z, tp1
                ld      hl, KID_REC             ; (kidsim: Char = Kid after the mobs)
                ld      de, CHAR_SAVE
                call    gcp16
tp1:            call    process_trobs
                call    check_skel
                call    check_can_guard_see_kid
                jp      loadkid_and_opp
tp_mobs:        db      0
; tick_post: after the kid's frame (kid.asm kid_tick)
tick_post:      call    play_guard_frame
                call    check_sword_hurting
                call    check_sword_hurt
                call    sword_vs_sword          ; (sound.asm)
                call    do_delta_hp_g
                call    exit_room
                call    check_the_end
                ld      a, (GAME_OVER)          ; (the end, or the time ran out at the kid's death: nothing more)
                or      a
                jp      nz, tick_end
                call    check_guard_fallout
                ld      hl, GUARD_REC           ; the guard trace snapshot (SDLPoP pop800_trace_guard)
                ld      de, G_SNAP
                ld      bc, 16
                ldir
                ld      hl, g_glob
                ld      bc, 14
                ldir
                ld      a, (HITP_CURR)
                ld      (G_SNAP + 18), a
                ld      a, (KID_REC + OF_SWORD)
                ld      (G_SNAP + 19), a
                ld      a, (level_number)
                cp      6
                jr      nz, tpo_12
                ld      a, (ROOMLEAVE)          ; level 6: falling out of room 1 is the exit
                cp      0xfe
                jr      nz, tpo_t
                ld      a, 0xff
                ld      (KID_REC + OF_Y), a
                jr      tpo_next
tpo_12:         cp      12                      ; level 12: running into room 23 is the exit (seamless)
                jr      nz, tpo_t
                ld      a, (KID_REC + OF_ROOM)
                cp      23
                jr      nz, tpo_t
                ld      a, 1
                ld      (SEAMLESS), a
tpo_next:       ld      hl, NEXT_LEVEL
                inc     (hl)
                call    snd_stop
                inc     a
                ld      (LEVEL_SWITCH), a
tpo_t:          ld      a, (END_OVER)           ; (hybrid: the clock stops after the ticks model's level end wait)
                or      a
                call    z, show_time
                call    state_snap              ; (the harness's 'S' trace point; the game: ret)
                ld      a, (level_number)       ; the time is up (not on levels 13 and 14)
                cp      13
                jr      nc, tpo_x
                ld      a, (REM_MIN)
                or      a
                jr      nz, tpo_x
                ld      a, GO_EXPIRED
                ld      (GAME_OVER), a
                jr      tick_end
tpo_x:          call    end_wait                ; (sound.asm: the level done without end music changes now)
                ld      a, (LEVEL_SWITCH)
                or      a
                call    z, draw_game_frame      ; (not when the next level starts)
tpo1:           ld      hl, (K_TICK)
                inc     hl
                ld      (K_TICK), hl
; tick_end: keep Char, leave the Kid in KV for the drawing code
tick_end:       ld      hl, KV
                ld      de, CHAR_SAVE
                call    gcp16
                jp      loadkid
; timers (seg000): the ticks sound model's clock (kidsim sound_tick: at the tick start), the shadow union, the guard
; notice timer, the feather fall, the level 8 mouse
timers:         ld      hl, SND_LEFT
                ld      a, (hl)
                or      a
                jr      z, tm00
                dec     (hl)
tm00:           ld      a, (UNITED)
                or      a
                jr      z, tm1
                bit     7, a
                jr      nz, tm1
                dec     a
                jr      nz, tm0
                dec     a
tm0:            ld      (UNITED), a
tm1:            ld      a, (GUARD_NOTICE_TIMER)
                or      a
                jr      z, tm2
                bit     7, a
                jr      nz, tm2
                dec     a
                ld      (GUARD_NOTICE_TIMER), a
tm2:            ld      a, (FEATHER)            ; feather fall: ends when no sound plays (silent: its music until a
                or      a                       ; stop_sounds) or after 225 ticks
                jr      z, tm3
                inc     a
                ld      (FEATHER), a
                cp      226
                jr      nc, tm2b
                call    feather_snd             ; (sound.asm)
                jr      nz, tm3
tm2b:           xor     a
                ld      (FEATHER), a
                ld      (FEATHER_MUSIC), a
tm3:            ld      a, (level_number)
                cp      8
                ret     nz
                ld      a, (CHAR_SAVE + OF_ROOM)
                cp      16
                ret     nz
                ld      a, (LEVELDOOR_OPEN)
                or      a
                ret     z
                cp      255                     ; (a word in SDLPoP: stop at 255 so it never wraps to 0)
                ret     z
                inc     a
                ld      (LEVELDOOR_OPEN), a
                cp      150
                ret     nz
do_mouse:       call    loadkid
                ld      a, CHARID_MOUSE
                ld      (K_CHARID), a
                ld      a, 200
                ld      (K_X), a
                xor     a
                ld      (K_ROW), a
                call    set_y_land
                ld      a, 0xff
                ld      (K_ALIVE), a
                ld      (K_DIR), a
                ld      a, 1
                ld      (GUARDHP_CURR), a
                ld      a, SQ_MOUSE_FORWARD
                call    seqtbl_offset_char
                call    play_seq
                call    saveshad
                ld      hl, KV
                ld      de, CHAR_SAVE
                call    gcp16
                jp      loadkid
; check_skel: level 3, the skeleton wakes up when the kid comes near it with the exit door open
check_skel:     ld      a, (level_number)
                cp      3
                ret     nz
                ld      a, (GUARD_REC + OF_DIR)
                cp      DIR_NONE
                ret     nz
                ld      a, (DRAWN_ROOM)
                cp      1
                ret     nz
                ld      a, (LEVELDOOR_OPEN)
                or      a
                ret     z
                ld      a, (KID_REC + OF_COL)
                cp      2
                jr      z, cks1
                cp      3
                ret     nz
cks1:           ld      a, (DRAWN_ROOM)
                ld      c, 5
                ld      b, 1
                call    k_get_tile
                cp      T_SKELETON
                ret     nz
                ld      a, T_FLOOR
                call    set_tile_cur
                ld      hl, CHAR_SAVE           ; Char as it was
                ld      de, KV
                call    gcp16
                ld      a, (DRAWN_ROOM)
                ld      (K_ROOM), a
                ld      a, 1
                ld      (K_ROW), a
                call    set_y_land
                ld      a, 5
                ld      (K_COL), a
                ld      a, (x_bump + 10)
                add     a, TILE_SIZEX
                ld      (K_X), a
                ld      a, 0xff
                ld      (K_DIR), a
                ld      a, SQ_SKEL_WAKE
                call    seqtbl_offset_char
                call    play_seq
                ld      a, 44
                call    snd_play
                ld      a, 2
                ld      (GUARD_SKILL), a
                ld      (K_SWORD), a
                ld      a, 0xff
                ld      (K_ALIVE), a
                ld      a, 3
                ld      (GUARDHP_MAX), a
                ld      (GUARDHP_CURR), a
                xor     a
                ld      (K_FALLX), a
                ld      (K_FALLY), a
                ld      (IS_GUARD_NOTICE), a
                ld      (GUARD_REFRAC), a
                ld      a, CHARID_SKELETON
                ld      (K_CHARID), a
                call    saveshad
                jp      loadkid

; ================================================================ seeing and bumping (seg003)
; check_can_guard_see_kid: CAN_SEE = 0 no, 1 sees him but won't come, 2 sees him and comes
check_can_guard_see_kid:
                ld      a, (GUARD_REC + OF_CHARID)
                cp      CHARID_MOUSE
                jp      z, cgs_0
                cp      CHARID_SHADOW
                jr      nz, cgs1
                ld      a, (level_number)
                cp      12
                jp      nz, cgs_0
cgs1:           ld      a, (KID_REC + OF_FRAME)
                or      a
                jp      z, cgs_0
                cp      219
                jr      c, cgs2
                cp      229
                jp      c, cgs_0
cgs2:           ld      a, (GUARD_REC + OF_DIR)
                cp      DIR_NONE
                jp      z, cgs_0
                ld      a, (KID_REC + OF_ALIVE)
                bit     7, a
                jp      z, cgs_0
                ld      a, (GUARD_REC + OF_ALIVE)
                bit     7, a
                jp      z, cgs_0
                ld      a, (KID_REC + OF_ROOM)
                ld      hl, GUARD_REC + OF_ROOM
                cp      (hl)
                jp      nz, cgs_0
                ld      a, (KID_REC + OF_ROW)
                ld      hl, GUARD_REC + OF_ROW
                cp      (hl)
                jp      nz, cgs_0
                ld      a, 2
                ld      (CAN_SEE), a
                ld      a, (KID_REC + OF_COL)
                add     a, FIRST_COL
                call    xbump16
                ld      de, TILE_MIDX
                add     hl, de
                ld      (cgs_left), hl
                ld      a, (GUARD_REC + OF_COL)
                add     a, FIRST_COL
                call    xbump16
                ld      de, TILE_MIDX
                add     hl, de
                ld      (cgs_right), hl
                ld      de, (cgs_left)
                call    scmp
                jp      p, cgs3
                ld      (cgs_left), hl          ; swap
                ld      (cgs_right), de
cgs3:           ld      hl, (cgs_left)
                call    get_tile_at_kid
                cp      T_CHOMPER               ; (a chomper is on a tile's left)
                jr      nz, cgs4
                ld      hl, (cgs_left)
                ld      de, TILE_SIZEX
                add     hl, de
                ld      (cgs_left), hl
cgs4:           ld      hl, (cgs_right)
                call    get_tile_at_kid
                cp      T_GATE                  ; (a gate is on a tile's right)
                jr      nz, cgs_loop
                ld      hl, (cgs_right)
                ld      de, -TILE_SIZEX
                add     hl, de
                ld      (cgs_right), hl
cgs_loop:       ld      hl, (cgs_right)
                ld      de, (cgs_left)
                call    scmp
                ret     m
                ex      de, hl
                call    get_tile_at_kid
                cp      T_WALL
                jr      z, cgs_0
                cp      T_DOORTOP_FLOOR
                jr      z, cgs_0
                cp      T_DOORTOP
                jr      z, cgs_0
                cp      T_LOOSE
                jr      z, cgs_1
                cp      T_CHOMPER
                jr      z, cgs_1
                cp      T_GATE
                jr      nz, cgs5
                call    k_modif
                cp      112
                jr      c, cgs_1
                jr      cgs_n
cgs5:           call    k_is_floor
                jr      nz, cgs_n
cgs_1:          ld      a, 1
                ld      (CAN_SEE), a
cgs_n:          ld      hl, (cgs_left)
                ld      de, TILE_SIZEX
                add     hl, de
                ld      (cgs_left), hl
                jr      cgs_loop
cgs_0:          xor     a
                ld      (CAN_SEE), a
                ret
cgs_left:       dw      0
cgs_right:      dw      0
; get_tile_at_kid: HL = xpos -> the tile of the kid's row at that x
get_tile_at_kid:
                ld      de, -7
                add     hl, de
                call    get_tile_div_mod
                ld      c, a
                ld      a, (KID_REC + OF_ROW)
                ld      b, a
                ld      a, (KID_REC + OF_ROOM)
                jp      k_get_tile
; bump_into_opponent: (Char = Kid) an unarmed kid bumps into an armed guard he faces
bump_into_opponent:
                ld      a, (CAN_SEE)
                cp      2
                ret     c
                ld      a, (K_SWORD)
                or      a
                ret     nz
                ld      a, (OPP_REC + OF_SWORD)
                or      a
                ret     z
                ld      a, (OPP_REC + OF_ACTION)
                cp      2
                ret     nc
                ld      a, (OPP_REC + OF_DIR)
                ld      hl, K_DIR
                cp      (hl)
                ret     z
                call    char_opp_dist
                ld      de, -15
                call    scmp
                ret     m
                ld      de, 16
                call    scmp
                ret     p
                call    set_y_land
                xor     a
                ld      (K_FALLY), a
                ld      a, SQ_BUMP
                call    seqtbl_offset_char
                jp      play_seq
; check_killed_shadow: level 12, killing the shadow kills the kid
check_killed_shadow:
                ld      a, (level_number)
                cp      12
                ret     nz
                ld      a, (OPP_REC + OF_CHARID)
                ld      hl, K_CHARID
                or      (hl)
                cp      CHARID_SHADOW
                ret     nz
                ld      a, (K_ALIVE)
                bit     7, a
                ret     z
                ld      a, (OPP_REC + OF_ALIVE)
                bit     7, a
                ret     nz
                ld      bc, 5 * 256 + COLOR_WHITE
                call    set_flash
                ld      a, 100
                jp      take_hp

; ================================================================ sword control (seg005)
draw_sword:     call    release_arrows
                ld      (C_FWD), a
                ld      (C_SHIFT2), a
                ld      b, SQ_DRAW_SWORD
                ld      a, (K_CHARID)
                or      a
                jr      nz, dsw1
                ld      (OFFGUARD), a
                ld      a, 19
                call    snd_play
                jr      dsw2
dsw1:           cp      CHARID_SHADOW
                jr      z, dsw2
                ld      b, SQ_EN_GARDE
dsw2:           ld      a, 2
                ld      (K_SWORD), a
                ld      a, b
                jp      seqtbl_offset_char
control_with_sword:
                ld      a, (K_ACTION)
                cp      AC_HANG_CLIMB
                ret     nc
                call    get_tile_at_char
                cp      T_LOOSE
                jr      z, cws1
                ld      a, (CAN_SEE)
                cp      2
                jr      c, cws3
cws1:           call    char_opp_dist
                ld      a, h
                or      a
                jr      nz, cws2
                ld      a, l
                cp      90
                jr      c, swordfight
                jr      cws3
cws2:           bit     7, h
                jr      z, cws3
                ld      de, -4
                call    scmp
                jp      p, swordfight
                ld      a, SQ_TURN_WITH_SWORD
                jp      seqtbl_offset_char
cws3:           ld      a, (K_CHARID)
                or      a
                jr      nz, cws4
                ld      a, (K_ALIVE)
                bit     7, a
                jr      z, cws4
                xor     a
                ld      (HOLDING_SWORD), a
cws4:           ld      a, (K_CHARID)
                cp      CHARID_GUARD
                jr      nc, swordfight
                ld      a, (K_FRAME)
                cp      171
                ret     nz
                xor     a
                ld      (K_SWORD), a
                ld      a, SQ_PUT_SWORD_AWAY
                jp      seqtbl_offset_char
swordfight:     ld      a, (K_FRAME)
                ld      (sfg_frame), a
                cp      161
                jr      nz, sfg1
                ld      a, (C_SHIFT2)
                bit     7, a
                jr      nz, sfg1
                ld      a, SQ_BACK_WITH_SWORD   ; (back with the sword when parrying)
                jp      seqtbl_offset_char
sfg1:           ld      a, (C_SHIFT2)
                cp      C_HELD
                jr      nz, sfg2
                ld      a, (K_CHARID)
                or      a
                jr      nz, sfg1a
                ld      a, 15
                ld      (KID_SWORD_STRIKE), a
sfg1a:          call    sword_strike
                ld      a, (C_SHIFT2)
                cp      C_IGNORE
                ret     z
sfg2:           ld      a, (C_DOWN)
                cp      C_HELD
                jr      nz, sfg3
                ld      a, (sfg_frame)
                call    is_158_170_171
                ret     nz
                ld      a, C_IGNORE
                ld      (C_DOWN), a
                xor     a
                ld      (K_SWORD), a
                ld      a, (K_CHARID)
                or      a
                jr      nz, sfg2b
                inc     a
                ld      (OFFGUARD), a
                ld      a, 9
                ld      (GUARD_REFRAC), a
                xor     a
                ld      (HOLDING_SWORD), a
                ld      a, SQ_PUT_SWORD_FAST
                jp      seqtbl_offset_char
sfg2b:          cp      CHARID_SHADOW
                ld      a, SQ_PUT_SWORD_AWAY
                jp      z, seqtbl_offset_char
                ld      a, SQ_GUARD_INACTIVE
                jp      seqtbl_offset_char
sfg3:           ld      a, (C_UP)
                cp      C_HELD
                jr      z, parry
                ld      a, (C_FWD)
                cp      C_HELD
                jp      z, forward_with_sword
                ld      a, (C_BACK)
                cp      C_HELD
                jp      z, back_with_sword
                ret
sfg_frame:      db      0
; is_158_170_171: A = frame -> Z if one of the en garde frames
is_158_170_171: cp      158
                ret     z
                cp      170
                ret     z
                cp      171
                ret
sword_strike:   ld      a, (K_FRAME)
                cp      157
                jr      z, sst_s
                cp      165
                jr      z, sst_s
                call    is_158_170_171
                jr      z, sst_s
                cp      150
                jr      z, sst_p
                cp      161
                ret     nz
sst_p:          ld      b, SQ_STRIKE_AFTER_PARRY
                jr      sst_go
sst_s:          ld      b, SQ_STRIKE
                ld      a, (K_CHARID)
                or      a
                jr      z, sst_go
                ld      b, SQ_GUARD_STRIKE
sst_go:         ld      a, C_IGNORE
                ld      (C_SHIFT2), a
                ld      a, b
                jp      seqtbl_offset_char
parry:          xor     a
                ld      (par_play), a
                ld      a, (K_FRAME)
                cp      168
                jr      z, par_a
                cp      165
                jr      z, par_a
                call    is_158_170_171
                jr      z, par_a
                cp      167
                ret     nz
                ld      b, SQ_PARRY_AFTER_STRIKE
                jr      par_go
par_a:          ld      a, (K_CHARID)
                or      a
                jr      z, par_kid
                call    char_opp_dist
                ld      de, 32
                call    scmp
                jp      p, back_with_sword
                ld      a, (OPP_REC + OF_FRAME)
                cp      152
                ret     nz
                jr      par_par
par_kid:        ld      a, (OPP_REC + OF_FRAME)
                cp      168
                ret     z
                cp      151
                jr      z, par_par
                cp      152
                jr      z, par_par
                cp      162
                jr      z, par_par
                cp      153
                jr      nz, par_par
                ld      a, 1
                ld      (par_play), a
par_par:        ld      b, SQ_PARRY
par_go:         ld      a, C_IGNORE
                ld      (C_UP), a
                ld      a, b
                call    seqtbl_offset_char
                ld      a, (par_play)
                or      a
                ret     z
                jp      play_seq
par_play:       db      0
back_with_sword:
                ld      a, (K_FRAME)
                call    is_158_170_171
                ret     nz
                ld      a, C_IGNORE
                ld      (C_BACK), a
                ld      a, SQ_BACK_WITH_SWORD
                jp      seqtbl_offset_char
forward_with_sword:
                ld      a, (K_FRAME)
                call    is_158_170_171
                ret     nz
                ld      a, C_IGNORE
                ld      (C_FWD), a
                ld      a, (K_CHARID)
                or      a
                ld      a, SQ_FORWARD_WITH_SWORD
                jp      z, seqtbl_offset_char
                ld      a, SQ_GUARD_FWD_SWORD
                jp      seqtbl_offset_char
control_guard_inactive:
                ld      a, (K_FRAME)
                cp      166
                ret     nz
                ld      a, (C_DOWN)
                cp      C_HELD
                ret     nz
                ld      a, (C_FWD)
                cp      C_HELD
                jp      z, draw_sword
                ld      a, C_IGNORE
                ld      (C_DOWN), a
                ld      a, SQ_STAND_FLIPPED
                jp      seqtbl_offset_char

; ================================================================ guard AI (seg002)
move_0_nothing: xor     a
                ld      (C_SHIFT), a
                ld      (C_Y), a
                ld      (C_X), a
                ld      (C_SHIFT2), a
                ld      (C_DOWN), a
                ld      (C_UP), a
                ld      (C_BACK), a
                ld      (C_FWD), a
                ret
move_1_forward: ld      a, X_FORWARD
                ld      (C_X), a
                ld      a, C_HELD
                ld      (C_FWD), a
                ret
move_2_backward:
                ld      a, C_HELD
                ld      (C_BACK), a
                ld      a, X_BACKWARD
                ld      (C_X), a
                ret
move_3_up:      ld      a, Y_UP
                ld      (C_Y), a
                ld      a, C_HELD
                ld      (C_UP), a
                ret
move_4_down:    ld      a, C_HELD
                ld      (C_DOWN), a
                ld      a, Y_DOWN
                ld      (C_Y), a
                ret
move_down_back: ld      a, C_HELD
                ld      (C_DOWN), a
                jr      move_2_backward         ; (jr: M8a part 2 needed block 2 bytes)
move_down_forw: ld      a, C_HELD
                ld      (C_DOWN), a
                jr      move_1_forward
move_6_shift:   ld      a, C_HELD
                ld      (C_SHIFT), a
                ld      (C_SHIFT2), a
                ret
autocontrol_opponent:
                call    move_0_nothing
                ld      a, (K_CHARID)
                or      a
                jr      z, autocontrol_guard    ; (autocontrol_kid)
                ld      hl, JUSTBLOCKED
                call    dec_nz
                ld      hl, KID_SWORD_STRIKE
                call    dec_nz
                ld      hl, GUARD_REFRAC
                call    dec_nz
                ld      a, (K_CHARID)
                cp      CHARID_MOUSE
                jr      z, autocontrol_mouse
                cp      CHARID_SKELETON
                jr      nz, aco1
                ld      a, 2
                ld      (K_SWORD), a
                jr      autocontrol_guard
aco1:           cp      CHARID_SHADOW
                jp      z, autocontrol_shadow   ; (the events overlay: the scripted shadows of levels 4, 5, 6, 12)
                jr      autocontrol_guard       ; (Jaffar too)
dec_nz:         ld      a, (hl)
                or      a
                ret     z
                dec     (hl)
                ret
autocontrol_mouse:
                ld      a, (K_DIR)
                cp      DIR_NONE
                ret     z
                ld      a, (K_ACTION)
                or      a
                jr      nz, acm1
                ld      a, (K_X)
                cp      200
                ret     c
                jp      clear_char
acm1:           ld      a, (K_X)
                cp      166
                ret     nc
                ld      a, SQ_MOUSE_STAND
                call    seqtbl_offset_char
                jp      play_seq
autocontrol_guard:
                ld      a, (K_SWORD)
                cp      2
                jr      nc, autocontrol_guard_active
autocontrol_guard_inactive:
                ld      a, (KID_REC + OF_ALIVE)
                bit     7, a
                ret     z
                call    char_opp_dist
                ld      (g_dist), hl
                ld      a, (OPP_REC + OF_ROW)
                ld      b, a
                ld      a, (K_ROW)
                cp      b
                jr      nz, agi1
                ld      de, -8
                call    scmp
                jp      m, agi1
                bit     7, h
                jr      z, agi1
                jr      agi_see                 ; just behind him (-8..-1)
agi1:           ld      a, (IS_GUARD_NOTICE)
                or      a
                jr      z, agi2
                xor     a                       ; the kid made a sound ...
                ld      (IS_GUARD_NOTICE), a
                ld      hl, (g_dist)
                bit     7, h
                jr      z, agi_see
                ld      de, -4                  ; ... behind the guard: he turns around
                call    scmp
                ret     p
                jp      move_4_down
agi2:           ld      hl, (g_dist)
                bit     7, h
                ret     nz
agi_see:        ld      a, (CAN_SEE)
                or      a
                ret     z
                ld      a, (level_number)
                cp      13
                jp      nz, move_down_forw
                ld      a, (GUARD_NOTICE_TIMER)
                or      a
                ret     nz
                jp      move_down_forw
autocontrol_guard_active:
                ld      a, (K_FRAME)
                cp      166
                ret     z
                cp      150
                ret     c
                ld      a, (CAN_SEE)
                cp      1
                ret     z
                or      a
                jr      nz, aga_see
                ld      a, (DROPPEDOUT)
                or      a
                jp      nz, guard_follows_kid_down
                ld      a, (K_CHARID)
                cp      CHARID_SKELETON
                ret     z
                jp      move_down_back
aga_see:        call    char_opp_dist
                ld      (g_dist), hl
                ld      de, 12
                call    scmp
                jp      m, aga1
                ld      a, (OPP_REC + OF_FRAME)
                cp      102
                jr      c, aga1
                cp      118
                jr      nc, aga1
                ld      a, (OPP_REC + OF_ACTION)
                cp      AC_BUMPED
                ret     z
aga1:           ld      hl, (g_dist)
                ld      de, 35
                call    scmp
                jp      p, aga_far
                ld      de, 12
                call    scmp
                jp      m, aga_close
                ld      a, (K_SWORD)
                cp      2
                jp      nc, autocontrol_guard_kid_in_sight
                ld      de, 8
                call    scmp
                jp      p, autocontrol_guard_kid_in_sight
aga_close:      ld      a, (OPP_REC + OF_DIR)
                ld      hl, K_DIR
                cp      (hl)
                jp      z, move_2_backward      ; turn around
                jp      move_1_forward
aga_far:        ld      a, (GUARD_REFRAC)
                or      a
                ret     nz
                ld      a, (OPP_REC + OF_DIR)
                ld      hl, K_DIR
                cp      (hl)
                jr      z, autocontrol_guard_kid_far
                ld      a, (OPP_REC + OF_FRAME)
                cp      7
                jr      c, aga_f2
                cp      15
                jr      nc, aga_f2
                ld      hl, (g_dist)            ; the kid runs at him
                ld      de, 40
                call    scmp
                ret     p
                jp      move_6_shift
aga_f2:         cp      34
                jr      c, autocontrol_guard_kid_far
                cp      44
                jr      nc, autocontrol_guard_kid_far
                ld      hl, (g_dist)            ; run-jump
                ld      de, 50
                call    scmp
                ret     p
                jp      move_6_shift
autocontrol_guard_kid_far:
                call    get_tile_infrontof_char
                call    k_is_floor
                jp      nz, move_1_forward
                call    get_tile_infrontof2_char
                call    k_is_floor
                jp      nz, move_1_forward
                jp      move_2_backward
guard_follows_kid_down:
                ld      a, (OPP_REC + OF_ACTION)
                cp      AC_HANG_CLIMB
                ret     z
                cp      AC_HANG_STRAIGHT
                ret     z
                call    get_tile_infrontof_char
                call    wall_type
                jr      nz, gfk_no
                ld      a, (CURR_TILE2)
                call    k_is_floor
                jp      nz, move_1_forward
                ld      a, (TILE_ROW)
                inc     a
                ld      b, a
                ld      a, (TILE_COL)
                ld      c, a
                ld      a, (CURR_ROOM)
                call    k_get_tile
                cp      T_SPIKE
                jr      z, gfk_no
                cp      T_LOOSE                 ; would fall on a loose floor
                jr      z, gfk_no
                call    wall_type
                jr      nz, gfk_no
                ld      a, (CURR_TILE2)         ; ... or into a chasm
                call    k_is_floor
                jr      z, gfk_no
                ld      a, (K_ROW)              ; ... or the kid is not below
                inc     a
                ld      hl, OPP_REC + OF_ROW
                cp      (hl)
                jp      z, move_1_forward
gfk_no:         xor     a
                ld      (DROPPEDOUT), a
                jp      move_2_backward
autocontrol_guard_kid_in_sight:
                ld      a, (OPP_REC + OF_SWORD)
                cp      2
                jr      z, akis_armed
                ld      a, (GUARD_REFRAC)
                or      a
                ret     nz
                ld      hl, (g_dist)
                ld      de, 29
                call    scmp
                jp      m, move_6_shift
                jp      move_1_forward
akis_armed:     ld      hl, (g_dist)
                ld      de, 10
                call    scmp
                jp      m, guard_advance
                ld      de, 29
                call    scmp
                jp      p, guard_advance
                call    guard_block
                ld      a, (GUARD_REFRAC)
                or      a
                ret     nz
                ld      hl, (g_dist)
                ld      de, 12
                call    scmp
                jp      m, guard_advance
                ld      de, 29
                call    scmp
                jp      p, guard_advance
                jr      guard_strike
guard_advance:  ld      a, (GUARD_SKILL)
                or      a
                jr      z, gadv1
                ld      a, (KID_SWORD_STRIKE)
                or      a
                ret     nz
gadv1:          ld      hl, advprob
                call    g_prob
                ret     c
                jp      move_1_forward
guard_block:    ld      a, (OPP_REC + OF_FRAME)
                cp      152
                jr      z, gbl1
                cp      153
                jr      z, gbl1
                cp      162
                ret     nz
gbl1:           ld      hl, blockprob
                ld      a, (JUSTBLOCKED)
                or      a
                jr      z, gbl2
                ld      hl, impblockprob
gbl2:           call    g_prob
                ret     c
                jp      move_3_up
guard_strike:   ld      a, (OPP_REC + OF_FRAME)
                cp      169
                ret     z
                cp      151
                ret     z
                ld      hl, strikeprob
                ld      a, (K_FRAME)
                cp      161
                jr      z, gst1
                cp      150
                jr      nz, gst2
gst1:           ld      hl, restrikeprob
gst2:           call    g_prob
                ret     c
                jp      move_6_shift
; g_prob: HL = probability table -> carry clear if table[guard_skill] > prandom(255)
g_prob:         ld      a, (GUARD_SKILL)
                call    k_tbl
                ld      (g_t1), a
                ld      a, 255
                call    prandom
                ld      b, a
                ld      a, (g_t1)
                cp      b
                ret     c               ; p < r: no
                ret     nz              ; p > r: yes (carry clear)
                scf                     ; p = r: no
                ret

; ================================================================ the guard's frame (seg000 play_guard_frame)
play_guard_frame:
                ld      a, (GUARD_REC + OF_DIR)
                cp      DIR_NONE
                ret     z
                call    loadshad_and_opp
                call    load_fram_det_col
                call    check_killed_shadow
                call    play_guard
                ld      a, (K_ROOM)
                ld      hl, DRAWN_ROOM
                cp      (hl)
                jp      nz, saveshad
                call    play_seq
                ld      a, (K_X)
                cp      44
                jp      c, saveshad
                cp      211
                jp      nc, saveshad
                call    fall_accel
                call    fall_speed
                call    load_frame_to_obj
                call    load_fram_det_col
                call    set_char_collision
                call    check_guard_bumped
                call    check_action
                call    check_press
                call    check_spike_below
                call    check_spiked
                call    check_chomped_guard
                jp      saveshad
play_guard:     ld      a, (K_CHARID)
                cp      CHARID_MOUSE
                jp      z, autocontrol_opponent
                ld      a, (K_ALIVE)
                bit     7, a
                jr      z, plg1
                ld      a, (GUARDHP_CURR)
                or      a
                jr      nz, plg2
                ld      (K_ALIVE), a
                call    on_guard_killed
plg1:           ld      a, (K_CHARID)
                cp      CHARID_SHADOW
                call    z, clear_char
plg2:           call    autocontrol_opponent
                jp      control
; check_guard_bumped (seg004): a guard advancing with the sword into a wall is pushed back
check_guard_bumped:
                ld      a, (K_ACTION)
                cp      AC_RUN_JUMP
                ret     nz
                ld      a, (K_ALIVE)
                bit     7, a
                ret     z
                ld      a, (K_SWORD)
                cp      2
                ret     c
                call    get_tile_at_char
                cp      T_WALL
                jr      z, cgb_y
                cp      T_DOORTOP_FLOOR
                jr      z, cgb_y
                cp      T_GATE
                jr      nz, cgb1
                call    can_bump_into_gate
                or      a
                jr      nz, cgb_y
cgb1:           ld      a, (K_DIR)
                bit     7, a
                ret     nz
                ld      a, (TILE_COL)
                dec     a
                ld      c, a
                ld      a, (TILE_ROW)
                ld      b, a
                ld      a, (CURR_ROOM)
                call    k_get_tile
                cp      T_DOORTOP_FLOOR
                jr      z, cgb_y
                ld      a, (CURR_TILE2)
                cp      T_GATE
                ret     nz
                call    can_bump_into_gate
                or      a
                ret     z
cgb_y:          call    load_frame_to_obj
                call    set_char_collision
                call    is_obstacle
                or      a
                ret     z
                ld      a, (CURR_TILE2)
                call    dist_from_wall_behind
                bit     7, h
                ret     z
                ld      de, -12
                call    scmp
                ret     m
                ld      a, l
                neg
                call    char_dx_forward
                ld      (K_X), a
                ld      a, SQ_BUMP_FWD_SWORD
                call    seqtbl_offset_char
                call    play_seq
                jp      load_fram_det_col
; dist_from_wall_behind: A = tile -> HL (99: not a wall)
dist_from_wall_behind:
                call    wall_type
                jr      nz, dwb1
                ld      hl, 99
                ret
dwb1:           ld      (g_t1), a
                ld      a, (K_DIR)
                bit     7, a
                jr      nz, dwb_l
                ld      a, (g_t1)
                ld      hl, wall_dist_from_right
                call    k_tbl
                ld      b, a
                ld      a, TILE_RIGHTX
                sub     b
                call    k_sext
                ld      de, (COLL_TLX)
                add     hl, de
                ex      de, hl
                ld      hl, (CX_LCOLL)
                or      a
                sbc     hl, de
                ret
dwb_l:          ld      a, (g_t1)
                ld      hl, wall_dist_from_left
                call    k_tbl
                call    k_sext
                ld      de, (COLL_TLX)
                add     hl, de
                ld      de, (CX_RCOLL)
                or      a
                sbc     hl, de
                ret
check_chomped_guard:
                call    get_tile_at_char
                call    check_chomped_here
                or      a
                ret     nz
                ld      a, (TILE_COL)
                inc     a
                ld      c, a
                ld      a, (TILE_ROW)
                ld      b, a
                ld      a, (CURR_ROOM)
                call    k_get_tile
check_chomped_here:
                ld      a, (CURR_TILE2)
                cp      T_CHOMPER
                jr      nz, cch0
                call    k_modif
                and     0x7f
                cp      2
                jr      nz, cch0
                ld      a, (TILE_COL)
                add     a, FIRST_COL
                ld      hl, x_bump
                call    k_tbl
                add     a, TILE_MIDX
                ld      l, a
                ld      h, 0
                jr      nc, cch1
                inc     h
cch1:           ld      (COLL_TLX), hl
                ld      a, (CURR_TILE2)
                call    get_left_wall_xpos
                ld      de, (CX_RCOLL)
                call    scmp
                jp      p, cch0
                ld      a, (CURR_TILE2)
                call    get_right_wall_xpos
                ex      de, hl
                ld      hl, (CX_LCOLL)
                call    scmp
                jp      p, cch0
                call    chomped
                ld      a, 1
                ret
cch0:           xor     a
                ret

; ================================================================ sword hits (seg002)
check_sword_hurting:
                ld      a, (GUARD_REC + OF_DIR) ; no guard and no sword drawn: check_hurting does nothing and
                cp      DIR_NONE                ; Char = Kid, Opp = Guard already (the guard's frame did not run)
                jr      nz, csw00
                ld      a, (GUARD_REC + OF_SWORD)
                cp      2
                jr      z, csw00
                ld      a, (KID_REC + OF_SWORD)
                cp      2
                ret     nz
csw00:          ld      a, (KID_REC + OF_FRAME)
                or      a
                ret     z
                cp      219                     ; (not on the stairs)
                jr      c, csw0
                cp      229
                ret     c
csw0:           call    loadshad_and_opp
                call    check_hurting
                call    saveshad_and_opp
                call    loadkid_and_opp
                call    check_hurting
                jp      savekid_and_opp
check_hurting:  ld      a, (K_SWORD)
                cp      2
                ret     nz
                ld      a, (OPP_REC + OF_ROW)
                ld      hl, K_ROW
                cp      (hl)
                ret     nz
                ld      a, (K_FRAME)
                cp      153
                jr      z, chu1
                cp      154
                ret     nz
chu1:           call    char_opp_dist
                bit     7, h
                jr      nz, chu_hit
                ld      de, 29
                call    scmp
                jp      p, chu_hit
                ld      a, (OPP_REC + OF_FRAME)
                cp      161
                jr      z, chu_parried
                cp      150
                jr      z, chu_parried
chu_hit:        ld      a, (K_FRAME)            ; poking with the sword and Opp is not parrying
                cp      154
                ret     nz
                ld      b, 8
                ld      a, (OPP_REC + OF_SWORD)
                cp      2
                jr      c, chu2
                ld      b, 12
chu2:           push    bc
                call    char_opp_dist
                pop     bc
                ld      e, b
                ld      d, 0
                call    scmp
                jp      m, chu_snd              ; (sound.asm: out of range: the sword swishes)
                ld      de, 29
                call    scmp
                jp      p, chu_snd
                ld      a, AC_HURT
                ld      (OPP_REC + OF_ACTION), a
                ret
chu_parried:    ld      a, 161
                ld      (OPP_REC + OF_FRAME), a
                ld      a, (K_CHARID)
                or      a
                jr      z, chu3
                ld      a, 4
                ld      (JUSTBLOCKED), a
chu3:           ld      a, SQ_ATTACK_PARRIED
                call    seqtbl_offset_char
                jp      play_seq
check_sword_hurt:
                ld      a, (GUARD_REC + OF_ACTION)
                cp      AC_HURT
                jr      nz, cswh2
                ld      a, (KID_REC + OF_ACTION)
                cp      AC_HURT
                jr      nz, cswh1
                ld      a, AC_RUN_JUMP
                ld      (KID_REC + OF_ACTION), a
cswh1:          call    loadshad
                call    hurt_by_sword
                call    saveshad
                ld      a, (GUARD_SKILL)
                ld      hl, refractimer
                call    k_tbl
                ld      (GUARD_REFRAC), a
                ret
cswh2:          ld      a, (KID_REC + OF_ACTION)
                cp      AC_HURT
                ret     nz
                call    loadkid
                call    hurt_by_sword
                jp      savekid
hurt_by_sword:  ld      a, (K_ALIVE)
                bit     7, a
                ret     z
                ld      a, (K_SWORD)
                cp      2
                jr      z, hbs1
                ld      a, 100                  ; hurt when not in fighting pose: death
                call    take_hp
                ld      a, SQ_STABBED
                call    seqtbl_offset_char
                jr      hbs_killed
hbs1:           ld      a, (K_CHARID)
                cp      CHARID_SKELETON         ; (skeletons can't be hurt)
                jr      z, hbs_hit
                ld      a, 1
                call    take_hp
                or      a
                jr      nz, hbs_killed
hbs_hit:        ld      a, SQ_HIT_BY_SWORD
                call    seqtbl_offset_char
                call    set_y_land
                xor     a
                ld      (K_FALLY), a
                jp      hbs_snd                 ; (sound.asm: the hurt sound, play_seq)
hbs_killed:     call    get_tile_behind_char
                or      a
                jr      nz, hbs_st
                call    distance_to_edge_weight
                ld      (g_t1), a
                cp      4
                jr      c, hbs_st
                ld      a, (g_t1)               ; killed and pushed off the ledge
                sub     20
                call    char_dx_forward
                ld      (K_X), a
                call    load_fram_det_col
                ld      hl, K_ROW
                inc     (hl)
                ld      a, SQ_KID_PUSHED_OFF
                call    seqtbl_offset_char
                jp      hbs_snd
hbs_st:         ld      a, SQ_STABBED
                call    seqtbl_offset_char
                ld      a, (K_CHARID)
                or      a
                jr      z, hbs_y
                ld      a, (K_DIR)
                bit     7, a
                jr      z, hbs_y
                ld      a, (CURR_TILE2)
                cp      T_GATE
                jr      z, hbs_g
                call    get_tile_at_char
                cp      T_GATE
                jr      nz, hbs_y
hbs_g:          ld      a, (TILE_COL)
                add     a, FIRST_COL
                ld      hl, x_bump
                call    k_tbl
                add     a, TILE_MIDX
                ld      (K_X), a
                ld      a, 10
                call    char_dx_forward
                ld      (K_X), a
hbs_y:          call    set_y_land
                xor     a
                ld      (K_FALLY), a
                jp      hbs_snd

; ================================================================ rooms (seg002 / seg003)
; exit_room: the kid leaves the room; the guard stays behind (leave_guard) or follows him (follow_guard)
exit_room:      ld      a, (EXIT_TIMER)
                or      a
                jr      z, exr1
                dec     a
                ld      (EXIT_TIMER), a
                ret
exr1:           call    loadkid
                call    load_frame_to_obj
                call    set_char_collision
                call    leave_room
                ld      (ROOMLEAVE), a
                bit     7, a
                ret     nz
                call    savekid
                ld      a, (K_ROOM)
                ld      (NEXT_ROOM), a
                ld      a, (GUARD_REC + OF_DIR)
                cp      DIR_NONE
                ret     z
                jp      guard_leaves            ; (stub: the guard-leave overlay, src/m4/gleave.asm)
; check_the_end: a room change takes effect (SDLPoP check_the_end + redraw_screen's exit timer)
check_the_end:  ld      a, (NEXT_ROOM)
                or      a
                ret     z
                ld      hl, DRAWN_ROOM
                cp      (hl)
                ret     z
                ld      (hl), a
                cp      5                       ; level 14, the princess's room: the end
                jr      nz, cte1
                ld      a, (level_number)
                cp      14
                jr      nz, cte1
                ld      a, GO_END
                ld      (GAME_OVER), a
                ret
cte1:           jp      room_entered            ; (stub: the guard-enter overlay, src/m4/genter.asm)
; check_guard_fallout: a guard that fell out of the room dies (the skeleton of level 3 lands in room 3)
check_guard_fallout:
                ld      a, (GUARD_REC + OF_DIR)
                cp      DIR_NONE
                ret     z
                ld      a, (GUARD_REC + OF_Y)
                cp      211
                ret     c
                ld      a, (GUARD_REC + OF_CHARID)
                cp      CHARID_SHADOW
                jp      nz, guard_fallout       ; (stub: the guard-leave overlay)
                ld      a, (GUARD_REC + OF_ACTION)
                cp      AC_FREEFALL
                ret     nz
                call    loadshad
                call    clear_char
                jp      saveshad

; ================================================================ tables (SDLPoP data.h custom defaults)
; (constant, moved out of block 2 in M7 step 10: runtime RAM behind the VRAM window, never read inside blit; copied by
; game_init from levelstart.asm guard_tabs_img)
GUARD_TABS      equ     0x9f90
strikeprob      equ     GUARD_TABS
restrikeprob    equ     GUARD_TABS + 12
blockprob       equ     GUARD_TABS + 24
impblockprob    equ     GUARD_TABS + 36
advprob         equ     GUARD_TABS + 48
refractimer     equ     GUARD_TABS + 60
tbl_guard_type  equ     GUARD_TABS + 72
GUARD_TABS_N    equ     88

; ================================================================ variables
g_dist:         dw      0
g_t1:           db      0
; harness options (see the header): flags, count, GOPT_MAX x (room, tile, direction, skill, colour)
guard_opts:     db      0, 0
                ds      GOPT_MAX * 5
; harness options of the level events (0 room = none; the real game: as assembled): the kid's start (room, tile,
; direction) on the first level, the time left at the start (minutes, ticks)
ev_opts:        db      0, 0, 0, 60
                dw      719
; the guard trace snapshot: Guard (16), guardhp_curr, guardhp_max, hitp_curr, Kid.sword, can_guard_see_kid,
; holding_sword, justblocked, guard_refrac, kid_sword_strike, guard_notice_timer, is_guard_notice, offguard,
; droppedout, guard_skill; then the records and globals guard_init zeroes at each level start (gv_start..gv_end).
; Runtime only: in low RAM since M7 step 5 (0x0148-0x01B7; they were 113 bytes of block 2), the layout as before.
GV_LOW          equ     0x0148
G_SNAP          equ     GV_LOW                  ; 30 bytes
gv_start        equ     GV_LOW + 30
KID_REC         equ     gv_start                ; 16 bytes each
GUARD_REC       equ     gv_start + 16
OPP_REC         equ     gv_start + 32
CHAR_SAVE       equ     gv_start + 48
g_glob          equ     gv_start + 64           ; (in the snapshot's order)
GUARDHP_CURR    equ     g_glob + 0
GUARDHP_MAX     equ     g_glob + 1
                                                ; (+2, +3: hitp_curr, Kid.sword in the snapshot)
CAN_SEE         equ     g_glob + 4
HOLDING_SWORD   equ     g_glob + 5
JUSTBLOCKED     equ     g_glob + 6
GUARD_REFRAC    equ     g_glob + 7
KID_SWORD_STRIKE equ    g_glob + 8
GUARD_NOTICE_TIMER equ  g_glob + 9
IS_GUARD_NOTICE equ     g_glob + 10
OFFGUARD        equ     g_glob + 11
DROPPEDOUT      equ     g_glob + 12
GUARD_SKILL     equ     g_glob + 13
GUARDHP_DELTA   equ     g_glob + 14
CURR_GUARD_COLOR equ    g_glob + 15
UNITED          equ     g_glob + 16             ; united_with_shadow
ROOMLEAVE       equ     g_glob + 17             ; roomleave_result
gv_end          equ     g_glob + 18
                if gv_end > 0x0200
                .error the guard variables overlap RR_PTRS
                endif
