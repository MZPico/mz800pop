; ---------------------------------------------------------------- level events: the events overlay (M5)
; Z80 port of tools/kidsim.py's rarer level events, run from the RAM disk in window W1 (src/m4/ovl_event.asm; m4test
; includes this file directly): the potions (proc_get_object: hit points, flashes, feather fall, upside down,
; opening), the scripted shadows of levels 4, 5, 6 and 12 (autocontrol_shadow: called every tick while a shadow
; is in the level; the overlay stays in W1 until a room draw replaces it) and the kid's jump through the level 4
; mirror. All entries are called from resident code through the stubs in src/m4/ovl.asm; the code here calls only
; resident routines (and its own), never another W1 overlay.

; ================================================================ potions and the sword (seg006 proc_get_object)
; proc_get_object: the kid drinks (PICKUP_TYPE 1 health, 2 life, 3 feather, 4 upside down, 5 hurt, 6 open) or
; takes the sword (0xff); their sounds (sound.asm snd_stop, snd_play).
proc_get_object:
                ld      a, (K_CHARID)
                or      a
                ret     nz
                ld      a, (PICKUP_TYPE)
                or      a
                ret     z
                cp      0xff
                jr      nz, pgo1
                ld      (HAVE_SWORD), a         ; the sword: have_sword = -1, the victory music, yellow flash
                ld      a, 37
                call    snd_play
                ld      bc, 8 * 256 + COLOR_YELLOW
                jp      set_flash
pgo1:           cp      1                       ; health
                jr      nz, pgo2
                ld      a, (HITP_MAX)
                ld      hl, HITP_CURR
                cp      (hl)
                ret     z
                call    snd_stop
                ld      a, 33
                call    snd_play
                ld      a, 1
                ld      (HITP_DELTA), a
                ld      bc, 2 * 256 + COLOR_RED
                jp      set_flash
pgo2:           cp      2                       ; life
                jr      nz, pgo3
                call    snd_stop
                ld      a, 30
                call    snd_play
                ld      bc, 4 * 256 + COLOR_RED
                call    set_flash
                jp      add_life
pgo3:           cp      3                       ; feather fall: the music starts
                jr      nz, pgo4
                call    snd_stop
                ld      a, 39
                call    snd_play
                ld      a, 1
                ld      (FEATHER), a
                ld      (FEATHER_MUSIC), a
                ld      bc, 3 * 256 + COLOR_GREEN
                jp      set_flash
pgo4:           cp      4                       ; upside down (drawing only)
                jr      nz, pgo5
                ld      a, (UPSIDE)
                cpl
                ld      (UPSIDE), a
                ret
pgo5:           cp      5                       ; hurt (the potions level 15: half the hit points)
                jr      nz, pgo6
                call    snd_stop
                ld      a, 13
                call    snd_play
                ld      a, (level_number)
                cp      15
                ld      a, -1
                jr      nz, pgo5b
                ld      a, (HITP_MAX)
                inc     a
                srl     a
                neg
pgo5b:          ld      (HITP_DELTA), a
                ret
pgo6:           cp      6                       ; open: the button of room 8 tile 0
                ret     nz
                ld      a, 8
                ld      bc, 0
                call    k_get_tile
                ld      b, 0
                ld      c, 0xff
                xor     a
                jp      trigger_button
; add_life: one more hit point (at most 10), all filled up
add_life:       ld      a, (HITP_MAX)
                inc     a
                cp      11
                jr      c, adl1
                ld      a, 10
adl1:           ld      (HITP_MAX), a
                ld      hl, HITP_CURR
                sub     (hl)
                ld      (HITP_DELTA), a
                ret

; ================================================================ the mirror (level 4, seg003 jump_through_mirror)
; jump_through_mirror (draw_game_frame): the kid's mirror image becomes the shadow, the kid keeps 1 hit point.
; (check_mirror_image's distance_mirror only places the image on screen: overlay.asm pp_mirror.)
jump_through_mirror:
                call    loadkid
                ld      a, (K_COL)              ; check_mirror_image: x = 2 (x_bump[col + 5] + 10) - x, turned
                add     a, FIRST_COL
                ld      hl, x_bump
                call    k_tbl
                add     a, 10
                add     a, a
                ld      hl, K_X
                sub     (hl)
                ld      (hl), a
                ld      a, (K_DIR)
                cpl
                ld      (K_DIR), a
                xor     a
                ld      (JUMPED_MIRROR), a
                inc     a
                ld      (MI_JUMPED), a          ; (drawing: no mirror image this tick)
                ld      a, CHARID_SHADOW
                ld      (K_CHARID), a
                ld      a, 45
                call    snd_play
                call    saveshad
                ld      a, (HITP_MAX)
                ld      (GUARDHP_MAX), a
                ld      (GUARDHP_CURR), a
                ld      a, 1
                ld      (HITP_CURR), a
                ret

; ================================================================ the scripted shadows (seg002 autocontrol_shadow)
; autocontrol_shadow: Char = the shadow (controls cleared by autocontrol_opponent), Opp = the kid
autocontrol_shadow:
                ld      a, (level_number)
                cp      4
                jr      z, acs4
                cp      5
                jr      z, acs5
                cp      6
                jr      z, acs6
                cp      12
                jp      z, acs12
                ret
; level 4: the shadow out of the mirror runs left and vanishes
acs4:           ld      a, (K_ROOM)
                cp      4
                ret     nz
                ld      a, (K_X)
                cp      80
                jp      c, clear_char
                jp      move_1_forward
; level 6: the shadow steps forward when the kid run-jumps
acs6:           ld      a, (K_ROOM)
                dec     a
                ret     nz
                ld      a, (KID_REC + OF_FRAME)
                cp      43
                ret     nz
                ld      a, (KID_REC + OF_X)
                cp      128
                ret     nc
                call    move_6_shift
                jp      move_1_forward
; level 5: once the gate is open the shadow drinks the potion and runs away
acs5:           ld      a, (K_ROOM)
                cp      24
                ret     nz
                ld      a, (DEMO_TIME)
                or      a
                jr      nz, acs5b
                ld      a, 24                   ; the gate (room 24, tile 1)
                ld      bc, 0x0001
                call    k_get_tile
                call    k_modif
                cp      80
                ret     c
                xor     a
                ld      (DEMO_INDEX), a
acs5b:          call    do_auto_moves
                ld      a, (K_X)
                cp      15
                ret     nc
                jp      clear_char
; do_auto_moves: the shadow's moves from shad_drink_move (demo_time, move) by DEMO_TIME / DEMO_INDEX
do_auto_moves:  ld      a, (DEMO_TIME)
                cp      0xfe
                ret     nc
                inc     a
                ld      (DEMO_TIME), a
                ld      b, a
                ld      a, (DEMO_INDEX)
                ld      c, a
                add     a, a
                ld      e, a
                ld      d, 0
                ld      hl, shad_drink_move
                add     hl, de
                ld      a, b
                cp      (hl)                    ; moves[index].time <= demo_time: the next index, this move
                jr      c, dam_prev
                inc     c
                ld      a, c
                ld      (DEMO_INDEX), a
                jr      dam_go
dam_prev:       dec     hl                      ; else the previous move
                dec     hl
dam_go:         inc     hl
                ld      a, (hl)
                or      a
                jp      z, move_0_nothing
                dec     a
                jp      z, move_1_forward
                dec     a
                jp      z, move_2_backward
                dec     a
                jp      z, move_3_up
                dec     a
                jp      z, move_4_down
                dec     a
                jr      nz, dam6
                call    move_3_up
                jp      move_1_forward
dam6:           dec     a
                jp      z, move_6_shift
                dec     a
                ret     nz                      ; (-1, -2: the controls stay)
                ld      (C_SHIFT), a            ; move_7: shift released
                ret
shad_drink_move: db     0x00, 0, 0x01, 1, 0x0e, 0, 0x12, 6, 0x1d, 7, 0x2d, 2, 0x31, 1, 0xff, 0xfe
; level 12: the shadow fights the kid; when the kid sheathes his sword and walks into it, they unite
acs12:          ld      a, (K_ROOM)
                cp      15
                jr      nz, a12a
                ld      a, (SHADOW_INIT)
                or      a
                jr      nz, a12a
                ld      a, (OPP_REC + OF_X)
                cp      150
                jr      c, a12i
                ld      hl, init_shad_12
                ld      a, SQ_FALL
                jp      do_init_shad
a12i:           ld      a, 1
                ld      (SHADOW_INIT), a
a12a:           ld      a, (K_SWORD)
                cp      2
                jr      c, a12b
                ld      a, (OFFGUARD)
                or      a
                jp      z, autocontrol_guard_active
                ld      a, (GUARD_REFRAC)
                or      a
                jp      z, autocontrol_guard_active
                jp      move_4_down
a12b:           ld      a, (OPP_REC + OF_SWORD)
                cp      2
                jr      nc, a12c
                ld      a, (OFFGUARD)
                or      a
                jr      nz, a12d
a12c:           ld      a, (CAN_SEE)
                cp      2
                ret     c
                call    char_opp_dist
                ld      de, 90
                call    scmp
                ret     p
                ld      a, (K_FRAME)            ; the shadow draws his sword
                cp      15
                ret     nz
                jp      move_down_forw
a12d:           call    char_opp_dist
                ld      de, 10
                call    scmp
                jp      m, a12_unite
                ld      a, (CAN_SEE)            ; the kid runs to the shadow: the shadow runs to him
                cp      2
                ret     nz
                ld      a, (OPP_REC + OF_FRAME)
                cp      3
                ret     c
                cp      15
                jp      c, move_1_forward
                cp      127
                ret     c
                cp      133
                ret     nc
                jp      move_1_forward
a12_unite:      ld      bc, 18 * 256 + COLOR_WHITE
                call    set_flash
                call    add_life
                ld      a, 42
                ld      (UNITED), a
                xor     a                       ; the kid stands where the shadow was
                ld      (K_CHARID), a
                call    savekid
                jp      clear_char


; died_on_button: the kid died on the button at CURR_ROOM/CURR_TILEPOS
died_on_button: ld      a, (CURR_TILEPOS)
                call    get_curr_tile
                ld      a, (O_CMOD)
                ld      (O_T4), a
                ld      a, (O_CTILE)
                cp      T_OPENER
                jr      nz, dob1
                ld      a, T_FLOOR
                call    set_tile_cur
                xor     a
                call    set_mod_cur
                ld      b, T_DEBRIS
                jr      dob2
dob1:           ld      b, a            ; closer: becomes stuck
                ld      a, T_STUCK
                call    set_tile_cur
                ld      a, (O_CTILE)
                ld      b, a
dob2:           ld      a, (O_T4)
                ld      c, a
                ld      a, 1
                jp      trigger_button
