; M4/M6: the people on screen: the kid and the guard with their swords and hurt splashes, in SDLPoP's drawing
; order, the tiles drawn again over them (SDLPoP redraw_at_char2), their clip (clip_char), the guard's hit point
; strip. Assembled into the second block (0xC000+, after the tables): none of it runs inside blit.

; ---------------------------------------------------------------- tiles drawn again over the characters
; SDLPoP redraw_at_char2: while a character hangs, climbs, jumps up or falls, the tiles at his columns are drawn
; again over him (draw_other_overlay: the tile's base, bottom and spike/sword parts when the tile to its left is
; empty; draw_floor_overlay on climb frames 137..144: a floor-edge piece and the bottom). SDLPoP reaches the
; tiles in row 2, 1, 0, then the row above order and draws the objects of a tile after its overlay, so only the
; overlays after an object's tile cover it. ov_mark_char marks the tiles of each character, ov_gen_all generates
; their ops once per tick into OV_MID (and, for the row above, the bottom piece's fore copy into OV_FORE);
; people_chunk lays them between the objects.
OV_MID          equ     0x9dc0                  ; 32 records (the temp fore list's room: free outside tile_regen)
OV_FORE         equ     0x9ec0                  ; 8 records
ov_cfg:         dw      TMP_BACK, OV_MID, OV_FORE
                db      TMPMAX_BACK, 32, 8
                db      0, 0, 0
                dw      TMP_TAGS, TMP_TAGS, TMP_TAGS
floor_left_ovl: db      32, 151, 151, 150, 150, 151, 32, 32

; ov_mark_char: KV = a character in the drawn room: mark the tiles SDLPoP's redraw_at_char2 draws again over him
; (ov_mark: 2 = draw_other_overlay, 1 = draw_floor_overlay; the other overlay wins where both mark a tile)
ov_mark_char:   ld      a, (K_FRAME)            ; which overlay, if any (geometry loaded, columns widened: pp_char)
                cp      78
                jr      c, ob_k1
                cp      80
                jr      c, ob_other
ob_k1:          cp      137
                jr      c, ob_k2
                cp      145
                jr      c, ob_floor
ob_k2:          ld      a, (K_ACTION)
                cp      2
                jr      z, ob_other
                cp      3
                jr      z, ob_other
                cp      4
                jr      z, ob_other
                cp      6
                jr      z, ob_other
                cp      5
                ret     nz
                ld      a, (K_FRAME)
                cp      102
                ret     c
                cp      107
                ret     nc
ob_other:       ld      a, 2
                jr      ob_kind
ob_floor:       ld      a, 1
ob_kind:        ld      (ov_kind), a
                ld      (ov_any), a
                ld      a, (CHAR_COL_L)         ; mark the tiles: columns right .. left, bottom row (not when
                ld      b, a                    ; hanging/climbing) and top row
                ld      a, (CHAR_COL_R)
                sub     b
                ret     m
ob_col:         ld      (ov_c), a               ; (offset from the left column)
                ld      a, (K_ACTION)
                cp      2
                jr      z, ob_c1
                ld      a, (CHAR_BOT_ROW)
                call    ov_mark_tile
ob_c1:          ld      a, (CHAR_TOP_ROW)
                ld      hl, CHAR_BOT_ROW
                cp      (hl)
                call    nz, ov_mark_tile
                ld      a, (ov_c)
                sub     1
                jr      nc, ob_col
                ret
; obj_order: KV = a character (geometry loaded, columns not widened): A = his tile (SDLPoP set_objtile_at_char) in
; redraw order, 0xff = tile 30 (none)
obj_order:      ld      a, (K_ACTION)
                cp      1
                jr      nz, ob_o1
                ld      a, (CHAR_BOT_ROW)
                ld      b, a
                ld      a, (CHAR_COL_L)
                jr      ob_o2
ob_o1:          ld      a, (K_ROW)
                ld      b, a
                ld      a, (K_COL)
ob_o2:          ld      c, a
                ld      a, (K_FRAME)
                cp      135
                jr      c, ob_o3
                cp      149
                jr      c, ob_o4
ob_o3:          ld      a, (K_ACTION)
                cp      2
                jr      z, ob_o4
                cp      3
                jr      z, ob_o4
                cp      4
                jr      z, ob_o4
                cp      6
                jr      nz, ob_o5
ob_o4:          dec     c
ob_o5:          ld      a, 0xff                 ; order -1: no tile (drawn before all)
                bit     7, b
                ret     nz
                ld      a, b
                cp      3
                ld      a, 0xff
                ret     nc
                ld      a, c
                cp      10                      ; (also catches c < 0)
                ld      a, 0xff
                ret     nc
                jp      ov_order
; ov_gen_all: KV = the kid: the overlay ops of the marked tiles after the first character's, in redraw order, into
; OV_MID / OV_FORE; ov_mark[k] becomes the number of OV_MID ops drawn before the objects of the tile at order k
; (draw_other_overlay's second case moves the objects of the tile to its left after its ops)
ov_gen_all:     ld      a, (ov_any)             ; (no tile marked: no ops, ov_mark all 0)
                or      a
                ret     z
                ld      a, (ov_first)           ; (order + 1 of the first character's tile)
                or      a
                jp      z, og_a0
                ld      b, a                    ; the tiles up to his: nothing before the objects there
                ld      hl, ov_mark
og_a1:          ld      (hl), 0
                inc     hl
                djnz    og_a1
og_a0:          ld      hl, opl_base            ; generate into the overlay lists
                ld      de, TR_SAVE
                ld      bc, 6
                ldir
                ld      hl, opl_max
                ld      bc, 3
                ldir
                ld      hl, OPCOUNT
                ld      bc, 3
                ldir
                ld      hl, opt_base
                ld      bc, 6
                ldir
                ld      hl, ov_cfg
                ld      de, opl_base
                ld      bc, 6
                ldir
                ld      de, opl_max
                ld      bc, 3
                ldir
                ld      de, OPCOUNT
                ld      bc, 3
                ldir
                ld      de, opt_base
                ld      bc, 6
                ldir
                ld      a, (DRAWN_ROOM)
                ld      (R_ROOM), a
                call    load_room_links
                call    load_leftroom
                ld      a, (ov_first)
ob_k:           cp      40
                jp      nc, ob_done
                ld      (ov_k), a
                ld      e, a
                ld      d, 0
                ld      hl, ov_mark
                add     hl, de
                ld      a, (hl)
                or      a
                call    nz, ov_gen
                ld      a, (ov_k)
                ld      e, a
                ld      d, 0
                ld      hl, ov_mark
                add     hl, de
                ld      a, (OPCOUNT+1)
                ld      (hl), a
                ld      a, (ov_k)
                inc     a
                jp      ob_k
ob_done:        ld      a, (OPCOUNT+1)
                ld      (OV_NM), a
                ld      a, (OPCOUNT+2)
                ld      (OV_NF), a
                ld      hl, TR_SAVE             ; restore the room lists
                ld      de, opl_base
                ld      bc, 6
                ldir
                ld      de, opl_max
                ld      bc, 3
                ldir
                ld      de, OPCOUNT
                ld      bc, 3
                ldir
                ld      de, opt_base
                ld      bc, 6
                ldir
                ret

; ov_mark_tile: A = row (signed), column CHAR_COL_L + ov_c: mark the tile's place in the drawing order
ov_mark_tile:   ld      b, a
                ld      a, (CHAR_COL_L)
                ld      hl, ov_c
                add     a, (hl)
                ld      c, a
                bit     7, b
                jp      nz, omt_above
                ld      a, b
                cp      3
                ret     nc
                call    ov_order
                jr      omt_set
omt_above:      ld      a, c                    ; the row above the room: after rows 2, 1, 0
                add     a, 30
omt_set:        ld      e, a
                ld      d, 0
                ld      hl, ov_mark
                add     hl, de
                ld      a, (ov_kind)
                cp      (hl)
                ret     c
                ld      (hl), a
                ret
; ov_order: B = row 0..2, C = col 0..9 -> A = (2 - row) * 10 + col
ov_order:       ld      a, 2
                sub     b
                ld      e, a
                add     a, a
                add     a, a
                add     a, e
                add     a, a
                add     a, c
                ret

; ov_gen: (ov_k) = place in the order: add that tile's overlay ops
ov_gen:         and     1                       ; A = the mark: 2 other (ov_kind 0), 1 floor (ov_kind 1)
                ld      (ov_kind), a
                ld      a, (OPCOUNT+2)
                ld      (ov_f0), a
                ld      a, (ov_k)
                cp      30
                jp      nc, og_above
                ld      b, 2                    ; row = 2 - k / 10, col = k % 10
og_r:           cp      10
                jp      c, og_r2
                sub     10
                dec     b
                jp      og_r
og_r2:          ld      (DRAWN_COL), a
                ld      a, b
                ld      (DRAWN_ROW), a
                call    load_rowbelow
                ld      a, (DRAWN_ROW)
                call    row_ys
                call    load_curr_left
                xor     a
                ld      (ov_left), a
                ld      a, 1
                ld      (PTR_TABLE), a
                ld      a, (ov_kind)
                or      a
                jp      z, og_other
                ld      a, (TILE_LEFT)          ; draw_floor_overlay
                cp      T_EMPTY
                jp      nz, og_end
                ld      a, (CURR_TILE)
                cp      T_FLOOR
                jp      z, og_fl
                cp      T_PILLAR
                jp      z, og_fl
                cp      T_STUCK
                jp      z, og_fl
                cp      T_TORCH
                jp      nz, og_other
og_fl:          ld      a, (K_FRAME)
                sub     137
                ld      e, a
                ld      d, 0
                ld      hl, floor_left_ovl
                add     hl, de
                ld      c, (hl)
                xor     a
                call    xh_plus
                call    blit_or
                ld      hl, (DRAW_MAIN_Y)
                ld      a, (CURR_TILE)
                cp      T_STUCK
                jp      nz, og_fl2
                inc     hl
og_fl2:         ld      a, CH_ENV
                ld      b, 0
                call    add_mid
                xor     a
                call    draw_tile_bottom
                jr      og_end
og_other:       ld      a, (TILE_LEFT)          ; draw_other_overlay
                cp      T_EMPTY
                jp      z, og_t2
                ld      a, (CURR_TILE)
                cp      T_EMPTY
                jp      z, og_end
                ld      a, (DRAWN_COL)
                or      a
                jp      z, og_end
                sub     2
                ld      c, a
                ld      a, (DRAWN_ROW)
                ld      b, a
                ld      a, (R_ROOM)
                ld      e, T_EMPTY
                call    get_tile
                ld      a, d
                cp      T_EMPTY
                jp      nz, og_end
                ld      a, 1
                ld      (ov_left), a
og_t2:          call    draw_tile_right         ; draw_tile2 (only its mid-table parts stay)
                call    draw_tile_anim_right
                call    draw_tile_base
                call    draw_tile_anim
                xor     a
                call    draw_tile_bottom
                call    draw_loose
og_end:         xor     a
                ld      (PTR_TABLE), a
                ld      (OPCOUNT), a            ; back-table ops change nothing: dropped
                ld      a, (ov_f0)
                ld      (OPCOUNT+2), a          ; and so do the fore copies of fore pieces already in the room
                ld      a, (ov_left)            ; the second case redraws the objects of the tile to its left:
                or      a                       ; they move after this tile's ops
                ret     z
                ld      a, (ov_k)
                dec     a
                ld      e, a
                ld      d, 0
                ld      hl, ov_mark
                add     hl, de
                ld      a, (OPCOUNT+1)
                ld      (hl), a
                ret
og_above:       sub     30                      ; redraw_needed_above: the bottom piece goes to the fore table too
                ld      (DRAWN_COL), a
                ld      a, (R_ROOM)
                ld      (R_SAVED), a
                ld      a, (R_A)
                ld      (R_ROOM), a
                call    load_room_links
                call    load_leftroom
                ld      a, 2
                ld      (DRAWN_ROW), a
                call    load_rowbelow
                call    load_curr_left
                ld      hl, -1
                ld      (DRAW_MAIN_Y), hl
                ld      hl, 2
                ld      (DRAW_BOTTOM_Y), hl
                ld      a, 1
                call    draw_tile_bottom
                xor     a
                ld      (OPCOUNT), a
                ld      a, (R_SAVED)
                ld      (R_ROOM), a
                call    load_room_links
                jp      load_leftroom
ov_kind:        db      0
ov_c:           db      0
ov_first:       db      0
ov_any:         db      0
ov_k:           db      0
ov_f0:          db      0
ov_left:        db      0
ov_mark:        ds      40
OV_NM:          db      0               ; overlay ops this tick: mid, fore
OV_NF:          db      0

; kid_clip: KV = a character, geometry loaded (pp_char): CLIP_TOP (row) / CLIP_RIGHT (byte column), SDLPoP clip_char (the kid
; behind a floor edge or a wall while climbing, behind the door jamb on the exit stairs)
kid_clip:       xor     a
                ld      (CLIP_TOP), a
                ld      a, 40
                ld      (CLIP_RIGHT), a
                ld      a, (K_FRAME)
                cp      224
                jp      c, kc_general
                cp      229
                jp      c, kc_stairs
kc_general:     ; (pp_char: geometry loaded, columns widened)
                ; top: the tile at the top left (and top right) of the kid is a wall or a floor
                ld      a, (CHAR_COL_L)
                ld      c, a
                ld      a, (CHAR_TOP_ROW)
                ld      b, a
                ld      a, (K_ROOM)
                call    k_get_tile
                cp      T_WALL
                jp      z, kc_t1
                call    k_is_floor
                jp      z, kc_right
kc_t1:          ld      a, (K_ACTION)
                or      a
                jp      nz, kc_t2
                ld      a, (K_FRAME)
                cp      79
                jp      z, kc_t3
                cp      81
                jp      z, kc_t3
kc_t2:          ld      a, (CHAR_COL_R)
                ld      c, a
                ld      a, (CHAR_TOP_ROW)
                ld      b, a
                ld      a, (K_ROOM)
                call    k_get_tile
                cp      T_WALL
                jp      z, kc_t3
                call    k_is_floor
                jp      z, kc_right
kc_t3:          ld      a, (K_ROW)              ; clip_y = y_clip[row + 1]
                inc     a
                ld      (kc_crow), a
                add     a, a
                ld      l, a
                ld      h, 0
                ld      de, y_clip_tbl
                add     hl, de
                ld      e, (hl)
                inc     hl
                ld      d, (hl)                 ; DE = clip_y
                ld      a, (kc_crow)
                cp      1
                jp      z, kc_t4
                ld      hl, (OBJ_Y)             ; clip_y < obj_y
                or      a
                sbc     hl, de
                jp      z, kc_right
                jp      m, kc_right
                ld      hl, (CHAR_TOP_Y)        ; clip_y - 15 < char_top_y
                push    de
                ld      bc, 15
                add     hl, bc
                or      a
                sbc     hl, de
                pop     de
                jp      z, kc_right
                jp      m, kc_right
kc_t4:          bit     7, d                    ; (a clip above the screen clips nothing)
                jp      nz, kc_right
                ld      a, d
                or      a
                ld      a, 192
                jp      nz, kc_t5
                ld      a, e
                cp      193
                jp      c, kc_t5
                ld      a, 192
kc_t5:          ld      (CLIP_TOP), a
kc_right:       ld      hl, (CX_LCOLL)          ; col = column of char_x_left_coll - 4
                ld      de, -4
                add     hl, de
                call    get_tile_div_mod
                ld      (kc_col), a
                inc     a
                ld      c, a
                ld      a, (K_ROW)
                ld      b, a
                ld      a, (K_ROOM)
                call    k_get_tile
                cp      T_DOORTOP_FLOOR
                jp      z, kc_plus
                cp      T_DOORTOP
                jp      z, kc_plus
                ld      a, (kc_col)
                ld      c, a
                ld      a, (K_ROW)
                ld      b, a
                ld      a, (K_ROOM)
                call    k_get_tile
                cp      T_DOORTOP_FLOOR
                jp      z, kc_c2
                cp      T_DOORTOP
                jp      nz, kc_check
kc_c2:          ld      a, (K_ACTION)           ; ... unless he is in the air or hanging / climbing facing left
                cp      AC_MIDAIR
                jp      z, kc_check
                ld      b, a
                ld      a, (K_FRAME)
                ld      c, a
                ld      a, b
                cp      AC_FREEFALL
                jp      nz, kc_c3
                ld      a, c
                cp      106
                jp      z, kc_check
kc_c3:          ld      a, b
                cp      AC_BUMPED
                jp      nz, kc_c4
                ld      a, c
                cp      107
                jp      z, kc_check
kc_c4:          ld      a, (K_DIR)
                or      a
                jp      z, kc_plus
                ld      a, b
                cp      AC_HANG_CLIMB
                jp      z, kc_check
                cp      AC_HANG_STRAIGHT
                jp      z, kc_check
                cp      AC_RUN_JUMP
                jp      nz, kc_plus
                ld      a, c
                cp      137
                jp      c, kc_plus
                cp      140
                jp      c, kc_check
kc_plus:        ld      a, (TILE_COL)           ; right = tile_col * 32 + 32
                add     a, a
                add     a, a
                add     a, 4
                ld      (CLIP_RIGHT), a
                ret
kc_check:       ld      hl, (CX_RCOLL)          ; a wall (or a mirror) right of the kid in his row and his top row
                call    get_tile_div_mod
                ld      (kc_col), a
                ld      c, a
                ld      a, (K_ROW)
                ld      b, a
                ld      a, (K_ROOM)
                call    k_get_tile
                cp      T_WALL
                jp      z, kc_k1
                cp      T_MIRROR
                ret     nz
                ld      a, (K_DIR)
                or      a
                ret     nz
kc_k1:          ld      a, (kc_col)
                ld      c, a
                ld      a, (CHAR_TOP_ROW)
                ld      b, a
                ld      a, (K_ROOM)
                call    k_get_tile
                cp      T_WALL
                jp      z, kc_k2
                cp      T_MIRROR
                ret     nz
kc_k2:          ld      a, (CURR_ROOM)
                ld      hl, K_ROOM
                cp      (hl)
                ret     nz
                ld      a, (TILE_COL)           ; right = tile_col * 32
                add     a, a
                add     a, a
                ld      (CLIP_RIGHT), a
                ret
kc_crow:        db      0
kc_col:         db      0
y_clip_tbl:     dw      -60, 3, 66, 129, 192
kc_stairs:      ; the level door in the kid's row: its right edge and the top of its opening (door fully open)
                ld      a, (DRAWN_ROOM)
                ld      (CURR_ROOM), a
                ld      a, (K_ROW)
                ld      hl, tbl_line
                call    k_tbl
                ld      (kc_pos), a
                ld      b, 10
kc_find:        push    bc
                ld      a, (kc_pos)
                call    get_curr_tile
                pop     bc
                cp      T_LEVELDOOR_L
                jp      z, kc_found
                ld      hl, kc_pos
                inc     (hl)
                djnz    kc_find
                ret
kc_found:       ld      a, (kc_pos)
                call    mod10
                inc     a                       ; leveldoor_right = ((col + 1) * 4 bytes * 8) + 48 [+ 8 palace]
                add     a, a
                add     a, a                    ; bytes
                add     a, 6                    ; + 48 px
                ld      b, a
                ld      a, (LEVEL_TYPE)
                or      a
                jp      z, kc_r
                inc     b
kc_r:           ld      a, b
                ld      (CLIP_RIGHT), a
                ; leveldoor_ybottom = ybottom - (m & 3) - 48, then up in steps of 4 while above y = ybottom - m
                ; (ybottom = draw_main_y - 13 = 63 * row + 49); clip_top = leveldoor_ybottom + 1
                ld      a, (K_ROW)
                ld      b, a
                add     a, a
                add     a, a
                add     a, a
                add     a, a
                add     a, a
                add     a, a                    ; *64
                sub     b                       ; *63
                add     a, 49
                ld      (kc_yb), a
                ld      a, (O_CMOD)             ; the door's modifier (from get_curr_tile)
                ld      (kc_m), a
                and     3
                ld      b, a
                ld      a, (kc_yb)
                sub     b
                sub     48
                ld      c, a                    ; lb
                ld      a, (kc_yb)
                ld      hl, kc_m
                sub     (hl)
                ld      b, a                    ; y
kc_lb:          ld      a, c
                cp      b
                jp      nc, kc_set              ; lb >= y: done
                add     a, 4
                ld      c, a
                jp      kc_lb
kc_set:         ld      a, c
                inc     a
                ld      (CLIP_TOP), a
                ret
kc_pos:         db      0
kc_yb:          db      0
kc_m:           db      0

; ---------------------------------------------------------------- the people on screen (M6, M5)
; SDLPoP draw_people: the kid and the guard are objects (objtable) of seven slots: 0 the kid, 1 his sword, 2 the guard,
; 3 his sword, 4 the hurt splash (the kid's or the guard's), 5 the guard's hurt splash when both lose hit points in the
; same tick, 6 the kid's mirror image (level 4, check_mirror). Each slot has a sprite descriptor and buffer (slots 5
; and 6 in SPRBUF_B, the third chunk buffer, which then stays out of the chunk rotation for the tick); per tick a slot
; keeps: SD_DX = visible, SD_CR = its screen rect (xb, y, w, h), SD_COMPOSE = its clip (top row, right byte column:
; the character's clip_char; none for the splash), PP_CL its left clip (pixel x: the shadow right of the level 4
; mirror, the mirror image), PP_XD: drawn as the shadow (SDLPoP draw_objtable_item case 1: the image, then the image
; XORed d px further right; the shadow, and the kid in the blink after the level 12 union). Drawing order: the
; objects of a tile come after the tile's overlay (ov_gen_all), in redraw order of their tiles (tile 30 first, the
; splashes last), within a tile by y, the shadow last (objtable scanned last to first, then a stable sort: among
; equal keys slot order 5, 4, 3, 2, 1, 0, 6). PP_DL lists the visible slots in that order; people_chunk draws them
; into a compose chunk with the overlay ops between them.
SWORDBUF        equ     0x1000                  ; the kid's sword image (<= 5 x 19 x 4 bytes; the ROM monitor's
SPR_S           equ     0x1180                  ; work area, free once the game runs) and its sprite descriptor
SPR_GS          equ     0x0780                  ; the guard's sword: descriptor (image at GSWBUF, <= 256 bytes)
SPR_G           equ     0x0798                  ; the guard: descriptor (image at SPRBUF_G)
SPR_SP          equ     0x07b0                  ; the hurt splash: descriptor (image at SPLBUF)
PP_DL           equ     0x07c8                  ; draw list: count, then up to 7 slots in drawing order
GSWBUF          equ     0x0000
SPRBUF_G        equ     0xf600                  ; <= 1,148 bytes (guard images 1,092; the shadow's kid images 1,148)
SPLBUF          equ     0xfa80                  ; 520 bytes
SPRBUF_MI       equ     SPRBUF_B                ; the mirror image (kid images <= 1,148 bytes)
SPLBUF2         equ     SPRBUF_B + 0x480        ; the second splash (520 bytes)
PP_KU           equ     0x09b4                  ; 4: the kid's objects, this tick's U last tick's (bounding box; 0 = none)
PP_GU           equ     0x09b8                  ; 4: the guard's
PP_R            equ     0x09bc                  ; 4: scratch rect
GHP_PAT         equ     0x09c0                  ; 20: the guard's hit point icon (plane-major, as in the pack)
GHP_M           equ     0x09d4                  ; full icons on the guard's strip (as SDLPoP leaves it)
GHP_SHOWN       equ     0x09d5                  ; as drawn (0xff = draw again)
PP_SPOWN        equ     0x09d6                  ; the owner of the splash in slot 4 (0 kid, 2 guard, 0xff none)
PP_SX           equ     0x09d7                  ; 2: the character's screen x (unflipped)
PP_CUR          equ     0x09d9                  ; the character being placed (slot 0 or 2)
PC_DONE         equ     0x09da                  ; overlay ops laid so far in this chunk
PP_SAVE         equ     0x0ab0                  ; 16: Char (KV) as before people_place (drawing does not change it)
; M5 drawing state (low RAM 0x0300-0x03BF, runtime only)
SXT             equ     0x0300                  ; 73: spr_xor's row: plane p cell j at SXT + 16 p + j, black pixels + 64
SPR_SP2         equ     0x0350                  ; slot 5: descriptor (image at SPLBUF2)
SPR_MI          equ     0x0368                  ; slot 6: descriptor (image at SPRBUF_MI)
PP_KEYS         equ     0x0380                  ; 7 x 16-bit sort keys ((order + 1) << 10 | (y + 256) & 0x3ff; 0xffff
                                                ; none): slot 6 first, then slots 0..5
PP_ORD          equ     0x038e                  ; 7: the slot's tile in redraw order (0xff = tile 30; 40 = a splash)
PP_XD           equ     0x0395                  ; 7: the XOR copy's offset in px (0: a plain object)
PP_CL           equ     0x039c                  ; 14: the left clip in px (0: none)
PC_SAVE         equ     0x03aa                  ; 6: CRX, CRY, CRW, CRH, V_COMPOSE while a clipped sprite is drawn
CLIP_LEFT       equ     0x03b0                  ; 2: the left clip of the object being placed
PP_XDV          equ     0x03b2                  ; its XOR offset
PP_T1           equ     0x03b3                  ; it is the shadow (objtable type 1: last among its tile's objects)
PP_BBUSY        equ     0x03b4                  ; SPRBUF_B holds an image this tick
OBJT_LAST       equ     0x03b5                  ; SDLPoP obj_tilepos as the last character placed left it (order)
PC_SLOT         equ     0x03b6                  ; the slot pc_draw draws
PC_K            equ     0x03b7                  ; its left clip's pixels in the clip column (0: none)
FL_SHOWN        equ     0x03b8                  ; game.asm: the flash shown this tick (MZ colour, 0 none; harness)
UP_SHOWN        equ     0x03b9                  ; game.asm: the screen as drawn (0xff: upside down)
TXT_VIS         equ     0x03bb                  ; game.asm: the blinking death text is shown
SX_D            equ     0x03bc                  ; spr_xor: the offset, the first cell, the compose row, cells left
SX_J0           equ     0x03bd
SX_DST          equ     0x03be                  ; 2
PP_ANYFX        equ     0x03c0                  ; this tick an object has a left clip or an XOR copy (pc_draw)
pp_slots:       dw      SPR_A, SPR_S, SPR_G, SPR_GS, SPR_SP, SPR_SP2, SPR_MI
; sword_init: src/m4/gstart.asm (the level-start overlay, once at the start): the other descriptors' buffers

; people_place: after the tick: the objects of the kid and the guard, their overlays, the drawing order, and the
; dirty rects (per character this tick's objects U last tick's; one rect when the two meet)
people_place:   ld      hl, KV
                ld      de, PP_SAVE
                call    gcp16
                ld      hl, PP_KEYS             ; no objects yet
                ld      b, 14
pp0:            ld      (hl), 0xff
                inc     hl
                djnz    pp0
                ld      a, 40                   ; (the splashes: after all tiles)
                ld      (PP_ORD + 4), a
                ld      (PP_ORD + 5), a
                ld      a, 0xff
                ld      (PP_SPOWN), a
                ld      (SPR_SP2 + SD_LKEY), a  ; (SPRBUF_B: fetched again every tick)
                ld      (SPR_MI + SD_LKEY), a
                xor     a
                ld      (PP_BBUSY), a
                ld      (SPR_A + SD_DX), a
                ld      (SPR_S + SD_DX), a
                ld      (SPR_G + SD_DX), a
                ld      (SPR_GS + SD_DX), a
                ld      (SPR_SP + SD_DX), a
                ld      (SPR_SP2 + SD_DX), a
                ld      (SPR_MI + SD_DX), a
                ld      (OV_NM), a
                ld      (OV_NF), a
                ld      (PP_ANYFX), a
                ld      hl, ov_any              ; (ov_mark is all 0 unless the last tick marked tiles)
                or      (hl)
                jr      z, pp1x
                xor     a
                ld      (hl), a
                ld      hl, ov_mark
                ld      b, 40
pp1:            ld      (hl), a
                inc     hl
                djnz    pp1
pp1x:
                ld      a, 0x80
                ld      (ov_first), a
                ld      hl, 0x0601              ; the keys the sort looks at: PP_KEYS index 1 .. 5 (slots 0 .. 4);
                ld      (pq_rng), hl            ; pp_put widens it for slots 5 and 6
                call    pp_mirror               ; (SDLPoP check_mirror: before the kid; KV back to the kid after it)
                ld      a, (K_ROOM)             ; the kid (SDLPoP draw_kid)
                or      a
                jr      z, pp_g
                ld      hl, DRAWN_ROOM
                cp      (hl)
                jr      nz, pp_g
                ld      a, (HITP_DELTA)
                ld      b, 0
                call    pp_char
pp_g:           ld      a, (GUARD_REC + OF_DIR) ; the guard (draw_guard)
                cp      DIR_NONE
                jr      z, pp_order
                ld      a, (GUARD_REC + OF_ROOM)
                ld      hl, DRAWN_ROOM
                cp      (hl)
                jr      nz, pp_order
                call    loadshad
                ld      a, (GUARDHP_DELTA)
                ld      b, 2
                call    pp_char
pp_order:       ld      hl, PP_SAVE             ; the kid again
                ld      de, KV
                call    gcp16
                call    ov_gen_all              ; (draw_floor_overlay reads the kid's frame)
                ; ---- the drawing order: selection of the smallest key, among equal keys the last one in PP_KEYS
                ; (slot 6, the mirror image, is first there: objtable entry 0, drawn after the others of its key)
                ld      hl, PP_DL
                ld      (hl), 0
pq_o:          ld      de, 0xffff
                ld      a, (pq_rng)
                ld      c, a
                add     a, a
                ld      l, a
                ld      h, 0
                ld      ix, PP_KEYS
                ex      de, hl
                add     ix, de
                ex      de, hl
pq_i:          ld      l, (ix+0)
                ld      h, (ix+1)
                or      a
                sbc     hl, de
                jr      z, pq_t
                jr      nc, pq_n
pq_t:          add     hl, de
                ex      de, hl
                ld      b, c
pq_n:           inc     ix
                inc     ix
                inc     c
                ld      a, (pq_rng + 1)
                cp      c
                jr      nz, pq_i
                ld      a, d
                and     e
                inc     a
                jr      z, pp_rects             ; (0xffff: no more)
                ld      l, b                    ; (taken)
                ld      h, 0
                add     hl, hl
                ld      de, PP_KEYS
                add     hl, de
                ld      (hl), 0xff
                inc     hl
                ld      (hl), 0xff
                ld      a, b                    ; its slot: key k is slot k - 1, key 0 slot 6
                dec     a
                jp      p, pq_s
                ld      a, 6
pq_s:           ld      hl, PP_DL
                inc     (hl)
                ld      e, (hl)
                ld      d, 0
                add     hl, de
                ld      (hl), a
                jr      pq_o
pp_rects:       call    st_look                 ; ---- the dirty rects (a character as last tick: none of his own)
                ld      hl, SPR_A + SD_OXB
                ld      de, PP_KU
                ld      c, 0
                call    pp_group
                ld      hl, SPR_G + SD_OXB
                ld      de, PP_GU
                ld      c, 2
                call    pp_group
                ld      a, (st_res)             ; (one of them as last tick: no join)
                or      a
                jr      nz, pp_d1
                ld      a, (PP_KU + 2)          ; the two meet: one rect
                or      a
                jr      z, pp_d1
                ld      hl, PP_KU
                ld      de, CRX
                ld      bc, 4
                ldir
                ld      hl, PP_GU
                call    okt_meet
                jr      z, pp_d1
                ld      hl, PP_GU
                ld      de, PP_KU
                call    ru
                ld      hl, 0
                ld      (PP_GU), hl
                ld      (PP_GU + 2), hl
pp_d1:          ld      a, (st_res)
                rra
                ld      hl, PP_KU
                call    nc, dr_add_rect
                ld      a, (st_res)
                and     2
                ret     nz
                ld      hl, PP_GU
                jp      dr_add_rect
; pp_group: C = a character's slot (0 kid, 2 guard), HL = his old rect (descriptor SD_OXB), DE = his U rect:
; U = old U this tick's objects; the old rect becomes this tick's
pp_group:       push    hl
                push    de
                ld      hl, 0
                ld      (PP_R), hl
                ld      (PP_R + 2), hl
                ld      a, c                    ; his slots: his image and sword, the mirror image (kid) or the
                call    pp_rgrow                ; second splash (guard), the splash in slot 4 when it is his
                ld      a, c
                inc     a
                call    pp_rgrow
                ld      a, c
                or      a
                ld      a, 6
                jr      z, pg_1
                dec     a
pg_1:           call    pp_rgrow
                ld      a, (PP_SPOWN)
                cp      c
                ld      a, 4
                call    z, pp_rgrow
                pop     de
                pop     hl
                push    hl
                push    de
                ld      bc, 4
                ldir                            ; U = old
                pop     de
                ld      hl, PP_R
                call    ru
                pop     de                      ; old = this tick's
                ld      hl, PP_R
                ld      bc, 4
                ldir
                ret
; pp_rgrow: A = slot: PP_R grows by its rect when it is visible (keeps BC)
pp_rgrow:       push    bc
                call    pp_desc
                ld      de, SD_DX
                add     hl, de
                ld      a, (hl)
                or      a
                jr      z, prg1
                inc     hl
                inc     hl
                inc     hl                      ; SD_CR
                ld      de, PP_R
                call    ru
prg1:           pop     bc
                ret
; pp_desc: A = slot -> HL = its descriptor
pp_desc:        add     a, a
                ld      l, a
                ld      h, 0
                ld      de, pp_slots
                add     hl, de
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a
                ret
; ru: DE = rect, HL = rect (xb, y, w, h; w = 0: none): (DE) = (DE) U (HL)
ru:             inc     hl
                inc     hl
                ld      a, (hl)
                dec     hl
                dec     hl
                or      a
                ret     z
                inc     de
                inc     de
                ld      a, (de)
                dec     de
                dec     de
                or      a
                jr      nz, ru_go
                ld      bc, 4
                ldir
                ret
ru_go:          push    de
                ld      b, (hl)                 ; B, C, D, E = x0, y0, x1, y1 of (HL)
                inc     hl
                ld      c, (hl)
                inc     hl
                ld      a, (hl)
                add     a, b
                ld      d, a
                inc     hl
                ld      a, (hl)
                add     a, c
                ld      e, a
                pop     hl
                push    hl
                ld      a, (hl)
                cp      b
                jr      nc, ru1
                ld      b, a
ru1:            inc     hl
                inc     hl
                add     a, (hl)
                cp      d
                jr      c, ru2
                ld      d, a
ru2:            dec     hl
                ld      a, (hl)
                cp      c
                jr      nc, ru3
                ld      c, a
ru3:            inc     hl
                inc     hl
                add     a, (hl)
                cp      e
                jr      c, ru4
                ld      e, a
ru4:            pop     hl
                ld      (hl), b
                inc     hl
                ld      (hl), c
                inc     hl
                ld      a, d
                sub     b
                ld      (hl), a
                inc     hl
                ld      a, e
                sub     c
                ld      (hl), a
                ret

; pp_char: KV = a character in the drawn room, B = his slot (0 kid, 2 guard), A = his hit point delta this tick:
; SDLPoP add_kid_to_objtable / add_guard_to_objtable (his image, clip, overlays), draw_hurt_splash,
; add_sword_to_objtable
pp_char:        ld      (pp_dlt), a
                ld      a, b
                ld      (PP_CUR), a
                ld      (pp_slot), a
                call    load_fram_det_col
                call    load_frame_to_obj
                call    set_char_collision
                call    obj_order               ; his tile (also his sword's)
                ld      hl, PP_CUR
                ld      e, (hl)
                ld      d, 0
                ld      hl, PP_ORD
                add     hl, de
                ld      (hl), a
                inc     hl
                ld      (hl), a
                ld      (OBJT_LAST), a          ; (SDLPoP set_objtile_at_char: obj_tilepos)
                inc     a                       ; the first character's tile (order + 1)
                ld      hl, ov_first
                cp      (hl)
                jr      nc, pc1
                ld      (hl), a
pc1:            call    draw_cols               ; redraw_at_char: the sword's wider columns
                call    ov_mark_char            ; redraw_at_char2
                call    kid_clip                ; clip_char
                ld      hl, (OBJ_X)
                call    scr_x
                ld      (PP_SX), hl
                ld      hl, 0                   ; add_guard_to_objtable: the shadow shows only right of the level 4
                ld      a, (K_CHARID)           ; mirror (obj_clip_left 137; his sword too)
                cp      CHARID_SHADOW
                ld      (PP_T1), a              ; (Z flag: the shadow)
                jr      nz, pc_cl
                ld      a, (level_number)
                cp      4
                jr      nz, pc_cl
                ld      a, (K_ROOM)
                cp      4
                jr      nz, pc_cl
                ld      l, 137
pc_cl:          ld      (CLIP_LEFT), hl
                ld      a, (CF_IMG)             ; ---- his image (chtab 2 + (sword >> 6))
                cp      255
                jr      z, pc_sw
                inc     a
                ld      (pp_id), a
                ld      a, (CF_SWORD)
                and     0xc0
                ld      a, CH_KID
                jr      z, pc2
                ld      a, CH_GUARD
pc2:            ld      (pp_ch), a
                ld      hl, (PP_SX)
                ld      (pp_x), hl
                ld      hl, (OBJ_Y)
                ld      (pp_y), hl
                ld      a, (PP_T1)              ; drawn as the shadow: the shadow, the kid in the level 12 blink
                sub     CHARID_SHADOW
                ld      (PP_T1), a              ; (0: the shadow)
                jr      z, pc_xs
                ld      a, (PP_CUR)
                or      a
                jr      nz, pc_x0
                call    pp_blink
                jr      z, pc_x0
pc_xs:          call    pp_xd
                jr      pc3
pc_x0:          xor     a
pc3:            ld      (PP_XDV), a
                call    pp_put
pc_sw:          xor     a                       ; (the sword and the splash: plain objects)
                ld      (PP_XDV), a
                inc     a
                ld      (PP_T1), a
                ld      a, (K_FRAME)            ; ---- his sword (add_sword_to_objtable)
                cp      229
                jr      c, pc_s1
                cp      238
                jr      c, pc_s2
pc_s1:          ld      a, (K_SWORD)
                or      a
                jr      nz, pc_s2
                ld      a, (K_CHARID)           ; (a live guard always)
                cp      CHARID_GUARD
                jr      nz, pc_spl
                ld      a, (K_ALIVE)
                rla
                jr      nc, pc_spl
pc_s2:          ld      a, (CF_SWORD)
                and     0x3f
                jr      z, pc_spl
                ld      l, a
                ld      h, 0
                ld      e, l
                ld      d, h
                add     hl, hl
                add     hl, de
                ld      de, sword_tbl
                add     hl, de
                ld      a, (hl)                 ; image, dx, dy
                cp      0xff
                jr      z, pc_spl
                inc     a
                ld      (pp_id), a
                inc     hl
                ld      a, (hl)
                inc     hl
                push    hl
                call    fwd_dx                  ; x = his screen x + dx forward
                ld      de, (PP_SX)
                add     hl, de
                ld      (pp_x), hl
                pop     hl
                ld      a, (hl)
                call    k_sext                  ; y = obj_y + dy
                ld      de, (OBJ_Y)
                add     hl, de
                ld      (pp_y), hl
                ld      a, CH_SWORD
                ld      (pp_ch), a
                ld      hl, pp_slot
                inc     (hl)
                call    pp_put
pc_spl:         ld      a, (pp_dlt)             ; ---- the hurt splash (draw_hurt_splash)
                rla
                ret     nc
                ld      a, (K_FRAME)
                cp      178                     ; (chomped: none)
                ret     z
                ld      hl, (OBJ_Y)
                ld      c, 5
                cp      185                     ; dead, falling, landing: lower
                jr      z, psp_low
                cp      106
                jr      c, psp_2
                cp      111
                jr      c, psp_low
psp_2:          cp      177                     ; spiked
                jr      nz, psp_3
                ld      c, -5
                jr      psp_x
psp_3:          ld      de, -11                 ; else higher (the kid's 4 more)
                ld      a, (K_CHARID)
                or      a
                jr      nz, psp_4
                ld      de, -15
psp_4:          add     hl, de
                jr      psp_x
psp_low:        inc     hl
                inc     hl
                inc     hl
                inc     hl
psp_x:          ld      (pp_y), hl
                ld      a, c
                call    fwd_dx
                ld      de, (OBJ_X)
                add     hl, de
                call    scr_x
                ld      (pp_x), hl
                ld      a, (K_CHARID)           ; the kid's (chtab 2 image 218) or the guard's (chtab 5 image 1)
                or      a
                ld      a, CH_KID
                ld      c, 219
                jr      z, psp_5
                ld      a, CH_GUARD
                ld      c, 2
psp_5:          ld      (pp_ch), a
                ld      a, c
                ld      (pp_id), a
                xor     a                       ; no clip
                ld      (CLIP_TOP), a
                ld      h, a
                ld      l, a
                ld      (CLIP_LEFT), hl
                ld      a, 40
                ld      (CLIP_RIGHT), a
                ld      hl, PP_SPOWN            ; slot 4, or 5 for the guard's when the kid's is in 4
                ld      a, (hl)
                inc     a
                ld      a, 5
                jr      nz, psp_6
                ld      a, (PP_CUR)
                ld      (hl), a
                ld      a, 4
psp_6:          ld      (pp_slot), a
; pp_put: slot pp_slot = image pp_id of chtab pp_ch, unflipped screen x pp_x, bottom row pp_y, facing K_DIR, clip
; CLIP_TOP / CLIP_RIGHT: fetch it (unless off the screen), its rect, visible flag and sort key
pp_put:         ld      a, (pp_slot)
                call    pp_desc
                push    hl
                pop     iy
                ld      a, (pp_id)
                ld      (iy+SD_FRAME), a
                ld      c, a
                ld      a, (K_DIR)              ; facing right = mirrored (the images face left)
                inc     a
                ld      (iy+SD_MIRROR), a
                ld      a, (pp_ch)
                ld      (cf_ch + 1), a          ; (char_fetch's chtab)
                call    dir_entry
                inc     hl
                inc     hl
                inc     hl
                ld      b, (hl)                 ; wb
                inc     hl
                ld      a, (hl)                 ; h
                ld      (pp_h), a
                ld      hl, (pp_x)
                ld      a, (iy+SD_MIRROR)
                or      a
                jr      z, pu1
                ld      a, b                    ; flipped: SDLPoP puts the image's right edge at x; the kernel mirrors the
                add     a, a                    ; whole byte box, which starts wb * 8 left of x
                add     a, a
                add     a, a
                ld      e, a
                ld      d, 0
                sbc     hl, de
pu1:            ld      (iy+SD_X), l
                ld      (iy+SD_X+1), h
                ld      de, 64                  ; on the screen: -64 < x < 320
                add     hl, de
                ld      de, 384
                or      a
                sbc     hl, de
                ret     nc
                ld      a, (pp_y + 1)           ; bottom >= 0
                rla
                ret     c
                ld      hl, (pp_y)              ; top = bottom - h + 1 < 192
                ld      a, (pp_h)
                ld      e, a
                ld      d, 0
                or      a
                sbc     hl, de
                inc     hl
                ld      (iy+SD_Y), l
                ld      (iy+SD_YH), h
                ld      a, h
                inc     a
                jr      z, pu2
                dec     a
                ret     nz
                ld      a, l
                cp      192
                ret     nc
pu2:            ld      a, (pp_slot)            ; slots 5, 6: into SPRBUF_B (its kept picture is lost)
                cp      5
                jr      c, pu2a
                ld      a, 1
                ld      (PP_BBUSY), a
                xor     a
                ld      (rr_kv), a
pu2a:           push    iy
                call    char_fetch
                pop     iy
                ld      a, (PP_XDV)             ; the rect: columns max(xb, 0) .. min(xb + ow (+ 1: the shadow's XOR
                or      a                       ; copy), 40)
                jr      z, pu2b
                ld      a, 1
pu2b:           ld      b, (iy+SD_XB)
                add     a, b
                add     a, (iy+SD_OW)
                ret     m
                ld      c, a
                bit     7, b
                jr      z, pu3
                ld      b, 0
pu3:            cp      41
                jr      c, pu4
                ld      c, 40
pu4:            ld      a, c
                sub     b
                ret     z
                ret     c
                ld      (iy+SD_CR + 2), a
                ld      (iy+SD_CR), b
                ld      l, (iy+SD_Y)            ; rows max(y, 0) .. min(y + h, 192)
                ld      h, (iy+SD_YH)
                ld      e, (iy+SD_H)
                ld      d, 0
                add     hl, de
                ld      a, l
                cp      193
                jr      c, pu5
                ld      a, 192
pu5:            ld      c, a
                ld      b, (iy+SD_Y)
                bit     7, (iy+SD_YH)
                jr      z, pu6
                ld      b, 0
pu6:            sub     b
                ret     z
                ret     c
                ld      (iy+SD_CR + 3), a
                ld      (iy+SD_CR + 1), b
                ld      (iy+SD_DX), 1
                ld      a, (CLIP_TOP)
                ld      (iy+SD_COMPOSE), a
                ld      a, (CLIP_RIGHT)
                ld      (iy+SD_COMPOSE + 1), a
                ld      a, (pp_slot)
                ld      e, a
                ld      d, 0
                ld      hl, PP_XD
                add     hl, de
                ld      a, (PP_XDV)
                ld      (hl), a
                ld      hl, PP_CL
                add     hl, de
                add     hl, de
                ld      bc, (CLIP_LEFT)
                ld      (hl), c
                inc     hl
                ld      (hl), b
                or      b                       ; (PP_ANYFX: an object with a left clip or an XOR copy)
                or      c
                ld      hl, PP_ANYFX
                or      (hl)
                ld      (hl), a
                ld      hl, PP_ORD              ; its key: (order + 1) << 10 | (y + 256) & 0x3ff (the shadow: 0x3ff)
                add     hl, de
                ld      a, (hl)
                inc     a
                add     a, a
                add     a, a
                ld      b, a
                ld      hl, (pp_y)
                ld      a, (PP_T1)
                or      a
                jr      nz, pk1
                ld      hl, 0x2ff
pk1:            inc     h
                ld      a, h
                and     3
                or      b
                ld      h, a
                ex      de, hl
                ld      a, (pp_slot)            ; (PP_KEYS: slot 6 first)
                inc     a
                cp      7
                jr      c, pk2
                xor     a
pk2:            ld      hl, pq_rng              ; (the sort's range covers it)
                cp      (hl)
                jr      nc, pk3
                ld      (hl), a
pk3:            inc     hl
                cp      (hl)
                jr      c, pk4
                inc     a
                ld      (hl), a
                dec     a
pk4:            add     a, a
                ld      l, a
                ld      h, 0
                ld      bc, PP_KEYS
                add     hl, bc
                ld      (hl), e
                inc     hl
                ld      (hl), d
                ret
; fwd_dx: A = delta (signed) -> HL = the delta forward (K_DIR: right +, left -)
fwd_dx:         ld      b, a
                ld      a, (K_DIR)
                rla
                ld      a, b
                jr      nc, fd1
                neg
fd1:            jp      k_sext
; scr_x: HL = logical x (signed) -> HL = screen x (SDLPoP calc_screen_x_coord: x * 320 / 280 toward zero)
scr_x:          bit     7, h
                jr      z, scx1
                call    neg_hl
                call    scx1
neg_hl:         ld      a, l
                cpl
                ld      l, a
                ld      a, h
                cpl
                ld      h, a
                inc     hl
                ret
scx1:           add     hl, hl
                add     hl, hl
                add     hl, hl
                jp      div_hl_7
; draw_cols: SDLPoP redraw_at_char: a character holding the sword has one more column in his facing direction
; (clip_char and redraw_at_char2 see it)
draw_cols:      ld      a, (K_SWORD)
                cp      2
                ret     c
                ld      a, (K_DIR)
                or      a
                jr      nz, dc_l
                ld      a, (CHAR_COL_R)
                cp      9
                ret     nc
                inc     a
                ld      (CHAR_COL_R), a
                ret
dc_l:           ld      a, (CHAR_COL_L)
                or      a
                ret     z
                dec     a
                ld      (CHAR_COL_L), a
                ret
pp_dlt:         db      0
pq_rng:         db      1, 6                    ; the sort's PP_KEYS index range (first, end)
pp_slot:        db      0
pp_id:          db      0
pp_ch:          db      0
pp_h:           db      0
pp_x:           dw      0
pp_y:           dw      0

; people_chunk: the people and the overlay ops into the compose chunk, in their drawing order
people_chunk:   xor     a
                ld      (PC_DONE), a
                ld      hl, PP_DL
                ld      b, (hl)
                inc     b
                jr      pch_n
pch_l:          inc     hl
                push    hl
                push    bc
                ld      a, (hl)                 ; a slot: the overlay ops before it, then its image
                push    af
                call    slot_p
                call    pc_ops
                pop     af
                ld      (PC_SLOT), a
                call    pp_desc
                call    pc_draw
                pop     bc
                pop     hl
pch_n:          djnz    pch_l
                ld      a, (OV_NM)              ; the ops after all
; pc_ops: lay the overlay ops PC_DONE .. A - 1
pc_ops:         ld      hl, PC_DONE
                ld      c, (hl)
                sub     c
                ret     z
                ret     c
                ld      b, a
                add     a, c
                ld      (hl), a
                ld      l, c
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      de, OV_MID
                add     hl, de
                jp      lay_list
; slot_p: A = slot -> A = the overlay ops drawn before its objects
slot_p:         ld      e, a
                ld      d, 0
                ld      hl, PP_ORD
                add     hl, de
                ld      a, (hl)
                inc     a
                ret     z                       ; (tile 30: before all)
                dec     a
                cp      40
                ld      a, (OV_NM)              ; (the splash: after all)
                ret     nc
                ld      a, (hl)
                ld      e, a
                ld      hl, ov_mark
                add     hl, de
                ld      a, (hl)
                ret
; pc_draw: HL = descriptor of slot PC_SLOT: its image into the compose chunk, clipped (SD_COMPOSE: top row, right byte
; column; PP_CL: left pixel), and its XOR copy when it is drawn as the shadow (PP_XD)
pc_draw:        push    hl
                pop     ix
                ld      hl, (CRX)               ; (CRX, CRY)
                ld      (PC_SAVE), hl
                ld      hl, (CRW)               ; (CRW, CRH)
                ld      (PC_SAVE + 2), hl
                ld      hl, (V_COMPOSE)
                ld      (PC_SAVE + 4), hl
                xor     a
                ld      (PC_K), a
                ld      a, (ix+SD_COMPOSE)      ; top: narrow the compose rect
                ld      hl, CRY
                sub     (hl)
                jr      c, pcd1
                jr      z, pcd1
                ld      b, a
                ld      a, (CRH)
                cp      b
                jp      c, pcd_r                ; the whole chunk is above the clip
                jp      z, pcd_r
                sub     b
                ld      (CRH), a
                ld      a, (ix+SD_COMPOSE)
                ld      (CRY), a
                ld      l, b                    ; the compose rows start b rows further down
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      de, (V_COMPOSE)
                add     hl, de
                ld      (V_COMPOSE), hl
pcd1:           ld      a, (ix+SD_COMPOSE + 1)  ; right
                ld      hl, CRX
                sub     (hl)
                jp      c, pcd_r
                jp      z, pcd_r
                ld      hl, CRW
                cp      (hl)
                jr      nc, pcd2
                ld      (hl), a
pcd2:           ld      a, (PP_ANYFX)           ; (no object has a left clip or an XOR copy: plain)
                or      a
                jr      nz, pcd3
                push    ix
                pop     hl
                call    spr_draw
                jr      pcd_r
pcd3:           ld      a, (PC_SLOT)            ; left (pixel x; 0: none)
                add     a, a
                ld      e, a
                ld      d, 0
                ld      hl, PP_CL
                add     hl, de
                ld      e, (hl)
                inc     hl
                ld      d, (hl)
                ld      a, d
                or      e
                jr      z, pcd_dr
                ld      a, e
                and     7
                ld      c, a                    ; the clip column's pixels left of the clip
                srl     d
                rr      e
                srl     d
                rr      e
                srl     d
                rr      e                       ; E = the clip column
                ld      a, (CRX)
                ld      b, a
                ld      a, e
                sub     b
                jr      c, pcd_dr               ; the chunk is right of the clip column
                jr      z, pcd_k
                ld      b, a                    ; narrow the chunk to start at the clip column
                ld      a, (CRW)
                sub     b
                jr      c, pcd_r
                jr      z, pcd_r
                ld      (CRW), a
                ld      a, e
                ld      (CRX), a
                ld      e, b
                ld      d, 0
                ld      hl, (V_COMPOSE)
                add     hl, de
                ld      (V_COMPOSE), hl
pcd_k:          ld      a, c
                ld      (PC_K), a
                or      a
                jr      z, pcd_dr
                xor     a
                call    pc_col                  ; (keep the clip column)
pcd_dr:         push    ix
                pop     hl
                call    spr_draw
                ld      a, (PC_SLOT)
                ld      e, a
                ld      d, 0
                ld      hl, PP_XD
                add     hl, de
                ld      a, (hl)
                or      a
                call    nz, spr_xor             ; (IY = the descriptor, from spr_draw)
                ld      a, (PC_K)
                or      a
                call    nz, pc_col              ; (its pixels left of the clip back)
pcd_r:          ld      hl, (PC_SAVE)
                ld      (CRX), hl
                ld      hl, (PC_SAVE + 2)
                ld      (CRW), hl
                ld      hl, (PC_SAVE + 4)
                ld      (V_COMPOSE), hl
                ret
; ghp_draw: the guard's hit point strip (bottom right, SDLPoP draw_guard_hp: icon i at x = 314 - 7 i, y = 194; not for
; the skeleton, the mouse, nor the shadow but on level 12). SDLPoP's screen keeps what draw_hp drew when
; guardhp_delta != 0 and loses it where the logic drops the guard (draw_guard_hp(0, curr), then guardhp_curr = 0)
ghp_draw:       ld      a, (GUARD_REC + OF_CHARID)
                cp      CHARID_SKELETON
                ret     z
                cp      CHARID_MOUSE
                ret     z
                cp      CHARID_SHADOW
                jr      nz, gd1
                ld      a, (level_number)
                cp      12
                ret     nz
gd1:            ld      a, (GUARDHP_CURR)
                ld      b, a
                ld      a, (GUARDHP_DELTA)
                or      a
                jr      nz, gd2
                or      b
                jr      nz, gd3
gd2:            ld      a, b
                ld      (GHP_M), a
gd3:            ld      a, (GHP_M)
                ld      hl, GHP_SHOWN
                cp      (hl)
                ret     z
                ld      (hl), a
                ld      (hp_n), a
                ld      (hp_nf), a
                ld      a, CH_GUARD             ; the icon: chtab 5 image 0
                ld      c, 1
                call    dir_entry
                push    hl
                pop     ix
                ld      hl, 0
                call    far_seek_entry
                ld      hl, GHP_PAT
                ld      bc, 20 << 8 | RD_DATA
                inir
                ld      hl, GHP_PAT
                ld      (hp_pf), hl
                ld      a, 32
                ld      (hp_base), a
                ld      bc, 0x0820              ; bytes 32..39, then 31
                call    hp_strip
                ld      bc, 0x011f
                jp      hp_strip
