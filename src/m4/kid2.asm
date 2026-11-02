; M4: kid logic added after the main code filled up (SDLPoP check_gate_push, check_chomped_kid, chomped).
; The game assembles it at 0x1C00 (below the program, above the sword buffers): it never runs inside blit,
; where CG-ROM covers 0x1000-0x1FFF.

; check_gate_push: a closing gate pushes a standing, turning or crouching kid 5 px out of its tile
check_gate_push:
                ld      a, (K_ACTION)
                cp      AC_TURN
                jr      z, cgp1
                ld      a, (K_FRAME)
                cp      15
                jr      z, cgp1
                cp      108
                ret     c
                cp      111
                ret     nc
cgp1:           call    get_tile_at_char
                ld      a, (TILE_COL)
                ld      (cgp_col), a
                ld      a, (CURR_TILE2)
                cp      T_GATE
                jr      z, cgp2
                ld      a, (TILE_COL)           ; or the tile to its left
                dec     a
                ld      c, a
                ld      a, (TILE_ROW)
                ld      b, a
                ld      a, (CURR_ROOM)
                call    k_get_tile
                cp      T_GATE
                ret     nz
cgp2:           ld      a, (TILE_COL)
                ld      e, a
                ld      d, 0
                ld      hl, CURR_FLAGS
                add     hl, de
                ld      a, (hl)
                ld      hl, PREV_FLAGS
                add     hl, de
                and     (hl)
                inc     a
                ret     nz
                call    can_bump_into_gate
                or      a
                ret     z
                ld      a, (cgp_col)            ; gate at the kid's tile: push left, else right
                ld      b, a
                ld      a, (TILE_COL)
                cp      b
                ld      a, (K_X)
                jr      c, cgp_r
                sub     5
                jr      cgp_s
cgp_r:          add     a, 5
cgp_s:          ld      (K_X), a
                jp      bumped_sound
cgp_col:        db      0
;  check_chomped_kid: a closed chomper (modifier 2) in a tile the kid's row fully covers (collision flags 0xFF)
check_chomped_kid:
                xor     a
ckc_l:          ld      (ckc_col), a
                ld      e, a
                ld      d, 0
                ld      hl, CURR_FLAGS
                add     hl, de
                ld      a, (hl)
                inc     a
                jr      nz, ckc_n
                ld      hl, CURR_ROOMS
                add     hl, de
                ld      a, (K_ROW)
                ld      b, a
                ld      c, e
                ld      a, (hl)
                call    k_get_tile
                cp      T_CHOMPER
                jr      nz, ckc_n
                call    k_modif
                and     0x7f
                cp      2
                call    z, chomped
ckc_n:          ld      a, (ckc_col)
                inc     a
                cp      10
                jr      c, ckc_l
                ret
ckc_col:        db      0
; chomped: src/m4/rare.asm (the game: the rare overlay, W1, through this stub; m4test includes rare.asm)
                if defined GAME_OVL
chomped:        push    af
                ld      a, OVL_RARE
                call    ovl_w1
                pop     af
                jp      OVL_W1 + 9
                endif
