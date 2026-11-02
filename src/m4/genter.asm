; ---------------------------------------------------------------- M6: the new room's guard (W1 overlay)
; Split out of guard.asm and objects.asm (2026-10-30): check_the_end's part for a new room (SDLPoP check_the_end: the
; room's animated tiles, the level 13 floors, its guard or shadow enters). In the game: the guard-enter overlay
; (window W1, src/m4/ovl_genter.asm; entry room_entered through its stub in src/m4/ovl.asm); m4test includes this file
; directly. Nothing here may call another W1 overlay: play_seq (enter_guard) reaches the events overlay's
; proc_get_object only for the kid (ps_getitem), never for a guard. do_init_shad: src/m4/shadinit.asm.
; room_entered (check_the_end, a new room is drawn): the room's tiles, the level 13 floors, the room's guard or shadow
room_entered:
                call    loadkid
                call    anim_tile_modif
                call    start_chompers
                call    check_fall_flo
                call    check_shadow
                ld      a, 2
                ld      (EXIT_TIMER), a
                ret
; check_fall_flo: level 13, the loose floors above rooms 23 and 16 start falling
check_fall_flo: ld      a, (level_number)
                cp      13
                ret     nz
                ld      a, (DRAWN_ROOM)
                cp      23
                jr      z, cff1
                cp      16
                ret     nz
cff1:           call    links_of
                ld      a, d
                ld      (CURR_ROOM), a
                ld      a, 22
cff2:           ld      (cff_pos), a
                ld      (CURR_TILEPOS), a
                ld      a, 0xff
                call    prandom
                and     0x0f
                neg
                call    make_loose_fall
                ld      a, (cff_pos)
                inc     a
                cp      28
                jr      c, cff2
                ret
cff_pos:        db      0
; check_shadow: the room's guard (or the shadow on levels 5, 6 and 12) enters the drawn room
check_shadow:   xor     a
                ld      (OFFGUARD), a
                ld      a, (level_number)
                cp      12
                jr      nz, chs6
                ld      a, (UNITED)
                or      a
                jr      nz, chs6
                ld      a, (DRAWN_ROOM)
                cp      15
                jr      nz, chs6
                ld      (K_ROOM), a
                ld      c, 1
                ld      b, 0
                call    k_get_tile
                cp      T_SWORD
                ret     z
                xor     a
                ld      (SHADOW_INIT), a
                ld      hl, init_shad_12
                ld      a, SQ_FALL
                jp      do_init_shad
chs6:           ld      a, (level_number)
                cp      6
                jr      nz, chs5
                ld      a, (DRAWN_ROOM)
                ld      (K_ROOM), a
                cp      1
                jr      nz, chs5
                ld      a, (LEVELDOOR_OPEN)     ; the presentation music, once
                cp      0x4d
                ld      a, 25
                call    nz, snd_play
                ld      a, 0x4d
                ld      (LEVELDOOR_OPEN), a
                ld      hl, init_shad_6
                ld      a, SQ_STAND
                jp      do_init_shad
chs5:           ld      a, (level_number)
                cp      5
                jr      nz, enter_guard
                ld      a, (DRAWN_ROOM)
                ld      (K_ROOM), a
                cp      24
                jr      nz, enter_guard
                ld      c, 3
                ld      b, 0
                call    k_get_tile
                cp      T_POTION
                ret     nz
                ld      hl, init_shad_5
                ld      a, SQ_STAND
                jp      do_init_shad            ; (src/m4/shadinit.asm)
enter_guard:    ld      a, (DRAWN_ROOM)
                dec     a
                ld      (g_rm1), a
                ld      e, a
                ld      d, 0
                ld      hl, LV_GTILE
                add     hl, de
                ld      a, (hl)
                cp      30
                ret     nc
                push    af
                ld      a, (DRAWN_ROOM)
                ld      (K_ROOM), a
                pop     af
                call    div10
                ld      (K_ROW), a
                call    set_y_land
                call    g_rm1_de
                ld      hl, LV_GX
                add     hl, de
                ld      a, (hl)
                ld      (K_X), a
                call    get_tile_div_mod_m7
                ld      (K_COL), a
                call    g_rm1_de
                ld      hl, LV_GDIR
                add     hl, de
                ld      a, (hl)
                ld      (K_DIR), a
                call    guard_type
                ld      (g_t1), a
                ld      b, 0
                or      a
                jr      nz, eg1
                call    g_rm1_de
                ld      hl, LV_GCOLOR
                add     hl, de
                ld      b, (hl)
eg1:            ld      a, b
                and     0x0f
                ld      (CURR_GUARD_COLOR), a
                ld      a, (g_t1)
                cp      2
                ld      a, CHARID_GUARD
                jr      nz, eg2
                ld      a, CHARID_SKELETON
eg2:            ld      (K_CHARID), a
                call    g_rm1_de
                ld      hl, LV_GSEQHI
                add     hl, de
                ld      a, (hl)
                or      a
                jr      nz, eg_seq
                ld      a, (K_CHARID)
                cp      CHARID_SKELETON
                jr      nz, eg3
                ld      a, 2
                ld      (K_SWORD), a
                ld      a, SQ_GUARD_ACTIVE_FALL
                jr      eg4
eg3:            xor     a
                ld      (K_SWORD), a
                ld      a, SQ_GUARD_STAND_INACTIVE
eg4:            call    seqtbl_offset_char
                jr      eg5
eg_seq:         ld      b, a
                ld      hl, LV_GSEQLO
                add     hl, de
                ld      c, (hl)
                ld      hl, -SEQ_BASE
                add     hl, bc
                ld      (K_SEQ), hl
eg5:            call    play_seq
                call    g_rm1_de
                ld      hl, LV_GSKILL
                add     hl, de
                ld      a, (hl)
                cp      12
                jr      c, eg6
                ld      a, 3
eg6:            ld      (GUARD_SKILL), a
                ld      a, (K_FRAME)
                cp      185
                jr      z, eg_dead
                cp      177
                jr      z, eg_dead
                cp      178
                jr      z, eg_dead
                ld      a, 0xff
                ld      (K_ALIVE), a
                xor     a
                ld      (JUSTBLOCKED), a
                ld      (GUARD_REFRAC), a
                ld      (IS_GUARD_NOTICE), a
                call    get_guard_hp
                jr      eg7
eg_dead:        ld      a, 1
                ld      (K_ALIVE), a
                xor     a
                ld      (GUARDHP_CURR), a
eg7:            xor     a
                ld      (K_FALLY), a
                ld      (K_FALLX), a
                ld      a, AC_RUN_JUMP
                ld      (K_ACTION), a
                jp      saveshad
g_rm1_de:       ld      a, (g_rm1)
                ld      e, a
                ld      d, 0
                ret
get_guard_hp:   ld      a, (GUARD_SKILL)
                ld      hl, extrastrength
                call    k_tbl
                ld      b, a
                ld      a, (level_number)
                and     15
                ld      hl, tbl_guard_hp
                call    k_tbl
                add     a, b
                ld      (GUARDHP_DELTA), a
                ld      (GUARDHP_CURR), a
                ld      (GUARDHP_MAX), a
                ret
extrastrength:  db      0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0
tbl_guard_hp:   db      4, 3, 3, 3, 3, 4, 5, 4, 4, 5, 5, 5, 4, 6, 0, 0
g_rm1:          db      0               ; (enter_guard only)
; anim_tile_modif: torches, potions and swords of the drawn room (and the torches in column 9 of the room on
; its left) get random first frames and start animating
anim_tile_modif:
                ld      a, (DRAWN_ROOM)
                ld      (CURR_ROOM), a
                xor     a
                ld      (sc_pos), a
atm_loop:       ld      a, (sc_pos)
                call    get_curr_tile
                cp      T_POTION
                jr      z, atm_potion
                cp      T_TORCH
                jr      z, atm_torch
                cp      T_TORCH_DEBRIS
                jr      z, atm_torch
                cp      T_SWORD
                jr      nz, atm_next
                ld      a, 255
                call    prandom
                and     0x1f
                jr      atm_set
atm_potion:     ld      a, 6
                call    prandom
                inc     a
                ld      b, a
                ld      a, (O_CMOD)
                and     0xf8
                or      b
                jr      atm_set
atm_torch:      ld      a, 8
                call    prandom
atm_set:        ld      b, a
                ld      a, (sc_pos)
                ld      c, a
                ld      a, (DRAWN_ROOM)
                call    o_ptrs
                ld      a, b
                ld      (de), a
                ld      a, (DRAWN_ROOM)
                ld      b, a
                ld      a, (sc_pos)
                ld      c, a
                ld      a, 1
                call    add_trob
atm_next:       ld      hl, sc_pos
                inc     (hl)
                ld      a, (hl)
                cp      30
                jr      nz, atm_loop
                ; torches in column 9 of the room on the left
                ld      a, (DRAWN_ROOM)
                call    links_of
                ld      a, c
                ld      (atm_left), a
                xor     a
                ld      (atm_row), a
atm_l:          ld      a, (atm_row)
                ld      b, a
                ld      c, 9
                ld      a, (atm_left)
                call    k_get_tile
                cp      T_TORCH
                jr      z, atm_lt
                cp      T_TORCH_DEBRIS
                jr      nz, atm_ln
atm_lt:         ld      a, 8
                call    prandom
                ld      b, a
                ld      a, (atm_row)
                ld      hl, tbl_line
                call    k_tbl
                add     a, 9
                ld      c, a
                ld      (sc_pos), a
                ld      a, (atm_left)
                push    bc
                call    o_ptrs
                pop     bc
                ld      a, b
                ld      (de), a
                ld      a, (atm_left)
                ld      b, a
                ld      a, (sc_pos)
                ld      c, a
                ld      a, 1
                call    add_trob
atm_ln:         ld      hl, atm_row
                inc     (hl)
                ld      a, (hl)
                cp      3
                jr      nz, atm_l
                ret
atm_left:       db      0
atm_row:        db      0

; lrs_body: leave_room's level specials before the room change (A = leave direction 0 left, 1 right, 2 up, 3 down; guard.asm
; lr_special calls it through the stub): returns A = the direction, CY = the resident tail must trigger the exit button first
; (the tile k_get_tile set; trigger_button is in the events overlay), or A = 0xfe NC (the level 6 falling exit). Moved from
; guard.asm 2026-11-01: it runs once per room change, in the tick whose room_entered loads this overlay anyway.
lrs_body:       ld      (lrs_dir), a
                ld      a, (level_number)
                ld      c, a
                ld      a, (lrs_dir)
                or      a
                jr      nz, lrs1
                ld      a, c                    ; left: level 4 mirror music marks the door, level 3 checkpoint,
                cp      4                       ; Jaffar dead: the exit door opens
                jr      nz, lrs0b
                ld      a, (LEVELDOOR_OPEN)
                or      a
                jr      z, lrs0b
                cp      0x4d
                jr      z, lrs0b
                ld      a, (K_ROW)
                or      a
                jr      nz, lrs0b
                ld      a, (K_ROOM)
                cp      11
                jr      nz, lrs0b
                ld      a, 25                   ; (play_mirr_mus)
                call    snd_play
                ld      a, 0x4d
                ld      (LEVELDOOR_OPEN), a
lrs0b:          ld      a, c
                cp      3
                jr      nz, lrs0c
                ld      a, (K_ROOM)
                cp      7
                jr      nz, lrs0c
                ld      a, 1
                ld      (CHECKPOINT), a
                ld      a, (HITP_MAX)
                ld      (HITP_BEG_LEV), a
lrs0c:          ld      a, (LEVELDOOR_OPEN)
                cp      2
                jr      nz, lrs_go
                ld      a, 24
                ld      bc, 0
                call    k_get_tile
                ld      b, 0
                ld      c, 0xff
                xor     a
                ld      a, (lrs_dir)    ; CY: guard.asm lr_special triggers the button of the tile k_get_tile set (the
                scf                     ; events overlay), then the room change
                ret
lrs1:           cp      1
                jr      nz, lrs3
                ld      a, c                    ; right: level 12 the sword disappears, level 13 meet Jaffar
                cp      12
                jr      nz, lrs1b
                ld      a, (K_ROOM)
                cp      18
                jr      nz, lrs1b
                ld      a, 15
                ld      c, 1
                ld      b, 0
                call    k_get_tile
                ld      a, T_FLOOR
                call    set_tile_cur
                xor     a
                call    set_mod_cur
lrs1b:          ld      a, (level_number)
                cp      13
                jr      nz, lrs_go
                ld      a, (LEVELDOOR_OPEN)
                or      a
                jr      nz, lrs_go
                ld      a, (K_ROOM)
                cp      3
                jr      nz, lrs_go
                ld      a, 29                   ; (meet_Jaffar)
                call    snd_play
                ld      a, 28
                ld      (GUARD_NOTICE_TIMER), a
                jr      lrs_go
lrs3:           cp      3
                jr      nz, lrs_go
                ld      a, c                    ; down: the level 6 falling exit
                cp      6
                jr      nz, lrs_go
                ld      a, (K_ROOM)
                cp      1
                jr      nz, lrs_go
                ld      a, 0xfe
                or      a               ; (NC: leave_room returns 0xfe)
                ret
lrs_go:         ld      a, (lrs_dir)
                or      a               ; (NC)
                ret
lrs_dir:        db      0
