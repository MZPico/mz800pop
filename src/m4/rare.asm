; ---------------------------------------------------------------- rare kid logic: the rare overlay (W1, src/m4/ovl_rare.asm)
; Split out of src/m4/objects.asm and kid2.asm (2026-11-01, the memory reclaim): code that runs once per item taken or
; per death. Called through the stubs in src/m4/ovl.asm (kid2.asm: chomped); m4test includes this file directly. Nothing
; here may call another W1 overlay (crouch, seqtbl_offset_char, play_seq, set_tile_cur are resident).
; get_item (check_get_item: the kid takes a potion or the sword), do_pickup: A = pickup type
get_item:       ld      a, (K_FRAME)
                cp      109
                jr      z, gi_crouched
                call    get_edge_distance
                ld      b, a
                ld      a, (EDGE_TYPE)
                cp      EDGE_FLOOR
                jr      z, gi1
                ld      a, b
                call    char_dx_forward
                ld      (K_X), a
gi1:            ld      a, (K_DIR)
                or      a
                jp      nz, crouch      ; facing left
                ld      a, (CURR_TILE2)
                cp      T_POTION
                ld      a, -2
                jr      nz, gi2
                ld      a, -1
gi2:            call    char_dx_forward
                ld      (K_X), a
                jp      crouch
gi_crouched:    ld      a, (CURR_TILE2)
                cp      T_SWORD
                jr      nz, gi_potion
                ld      a, -1
                call    do_pickup
                ld      a, SQ_GET_SWORD
                jp      seqtbl_offset_char
gi_potion:      call    k_modif
                rrca
                rrca
                rrca
                and     0x1f
                call    do_pickup
                ld      a, SQ_DRINK
                jp      seqtbl_offset_char
do_pickup:      ld      (PICKUP_TYPE), a
                ld      a, C_IGNORE
                ld      (C_SHIFT2), a
                ld      a, T_FLOOR
                call    set_tile_cur
                xor     a
                jp      set_mod_cur

; chomped: blood on the blade; the kid (once) is put in the chomper and cut
chomped:        call    k_modif
                or      0x80
                call    set_mod_cur
                ld      a, (K_FRAME)
                cp      178
                ret     z
                ld      a, (K_ROOM)
                ld      hl, CURR_ROOM
                cp      (hl)
                ret     nz
                ld      a, (TILE_COL)
                add     a, FIRST_COL
                ld      hl, x_bump
                call    k_tbl
                add     a, 7
                ld      (K_X), a
                ld      a, (K_DIR)              ; 7 - !direction
                or      a
                ld      a, 6
                jr      z, chd1
                inc     a
chd1:           call    char_dx_forward
                ld      (K_X), a
                ld      a, (K_ROW)
                inc     a
                ld      hl, y_land
                call    k_tbl
                ld      (K_Y), a
                ld      a, 46
                call    kill_snd        ; (sound.asm: take_hp(100), the sound)
                ld      a, SQ_CHOMPED
                call    seqtbl_offset_char
                jp      play_seq
