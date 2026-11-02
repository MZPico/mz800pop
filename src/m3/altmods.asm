; Level load: the alter-mods pass (SDLPoP load_alter_mod for every room) and its tile lookup. Split out of
; room.asm: the M3 test programs and m4test include it next to room.asm; the M4 game runs it from the
; level-start overlay (src/m4/ovl_level.asm).

; ---------------------------------------------------------------- level: alter mods (load_alter_mod for all rooms)
alter_mods:     xor     a               ; (the renderer starts in its normal mode: draw to the screen)
                ld      (RR_SHONLY), a
                ld      a, (LV_USED)
                cp      25
                jp      c, am0
                ld      a, 24
am0:            ld      (A_TMP2), a     ; used rooms
                ld      b, 1            ; room
amroom:         ld      a, b
                ld      (R_ROOM), a
                call    room_links_raw  ; R_L, R_R of this room
                ld      c, 0            ; pos
ampos:          push    bc
                ld      a, (R_ROOM)
                call    tile_base       ; HL = &fg[(room-1)*30], DE = &bg[...]
                ld      b, 0
                add     hl, bc
                ex      de, hl
                add     hl, bc          ; HL = &bg, DE = &fg
                ld      a, (de)
                and     0x1f
                ld      b, a            ; tile type
                ld      a, (hl)         ; modifier
                ld      c, a
                ld      a, b
                cp      T_GATE
                jp      nz, am1
                ld      a, c
                cp      1
                ld      a, 0
                jp      nz, amset
                ld      a, 188
                jp      amset
am1:            cp      T_LOOSE
                jp      nz, am2
                xor     a
                jp      amset
am2:            cp      T_POTION
                jp      nz, am3
                ld      a, c
                add     a, a
                add     a, a
                add     a, a
                jp      amset
am3:            cp      T_TORCH
                jp      z, amzero
                cp      T_TORCH_DEBRIS
                jp      nz, am4
amzero:         xor     a
                jp      amset
am4:            cp      T_WALL
                jp      nz, amnext
                ld      a, c
                cp      1
                jp      nz, am5
                ld      a, 0x80
                jp      am6
am5:            add     a, a
                add     a, a
                add     a, a
                add     a, a
am6:            ld      (A_TMP), a
                pop     bc              ; C = pos, B = room
                push    bc
                ; wall to left
                ld      e, 1
                ld      a, c
                call    mod10           ; A = pos % 10
                or      a
                jp      nz, amwl1
                ld      a, (R_L)
                or      a
                jp      z, amwl_done    ; no left room: wall_to_left = 1
                ld      d, a            ; left room
                ld      a, c
                add     a, 9
                call    tile_type_in    ; A = type of tile (room D, pos A)
                jp      amwl2
amwl1:          ld      a, (R_ROOM)
                ld      d, a
                ld      a, c
                dec     a
                call    tile_type_in
amwl2:          cp      T_WALL
                ld      e, 1
                jp      z, amwl_done
                ld      e, 0
amwl_done:      ld      a, e
                ld      (A_TMP2+1), a   ; wall_to_left (scratch at RV+30)
                ; wall to right
                ld      e, 1
                ld      a, c
                call    mod10
                cp      9
                jp      nz, amwr1
                ld      a, (R_R)
                or      a
                jp      z, amwr_done
                ld      d, a
                ld      a, c
                sub     9
                call    tile_type_in
                jp      amwr2
amwr1:          ld      a, (R_ROOM)
                ld      d, a
                ld      a, c
                inc     a
                call    tile_type_in
amwr2:          cp      T_WALL
                ld      e, 1
                jp      z, amwr_done
                ld      e, 0
amwr_done:      ld      a, (A_TMP2+1)
                ld      d, a            ; D = left, E = right
                ld      a, (A_TMP)
                bit     0, d
                jp      z, amwr3
                or      2
amwr3:          bit     0, e
                jp      z, amwr4
                or      1
amwr4:          ; store into bg
                ld      (A_TMP), a
                pop     bc
                push    bc
                ld      a, (R_ROOM)
                call    tile_base
                ld      b, 0
                ex      de, hl
                add     hl, bc
                ld      a, (A_TMP)
                ld      (hl), a
                jp      amnext
amset:          ld      (hl), a
amnext:         pop     bc
                inc     c
                ld      a, c
                cp      30
                jp      nz, ampos
                inc     b
                ld      a, (A_TMP2)
                cp      b
                jp      nc, amroom
                ret

; In: D = room, A = pos. Out: A = tile type
tile_type_in:   push    bc
                push    de
                ld      c, a
                ld      a, d
                call    tile_base
                ld      b, 0
                add     hl, bc
                ld      a, (hl)
                and     0x1f
                pop     de
                pop     bc
                ret

