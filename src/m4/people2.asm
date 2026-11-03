; ---------------------------------------------------------------- the people on screen: M5 parts (main block)
; Parts of overlay.asm's people drawing that live in the main code block (block 2 is full): the shadow's XOR offset,
; the level 12 blink, the kid's mirror image (pp_mirror), the left clip's column (pc_col), the standing characters
; (st_look); and the per-tick checks of the bottom text (text_chk) and the flash (flash_tick).

; pp_xd: the XOR copy's offset: A = calc_screen_x_coord(OBJ_X + 1) - PP_SX (1 or 2)
pp_xd:          ld      hl, (OBJ_X)
                inc     hl
                call    scr_x
                ld      a, (PP_SX)
                ld      b, a
                ld      a, l
                sub     b
                ret
; pp_blink: NZ while the kid is drawn as the shadow (united_with_shadow even, not 0: the level 12 union)
pp_blink:       ld      a, (UNITED)
                or      a
                ret     z
                cpl
                and     1
                ret
; pp_mirror: SDLPoP check_mirror (draw_people, KV = the kid): Char as the tick left it stands on a mirror tile and the
; kid did not jump through it this tick: his mirror image (check_mirror_image: x mirrored at the mirror, turned) in
; slot 6 when it is in front of the mirror (distance_mirror >= 0) and below its row's top (clip y_clip[row + 1], left
; col * 32 + 9; no clip_char); its tile is obj_tilepos as the last character placed left it (OBJT_LAST)
pp_mirror:      ld      hl, MI_JUMPED
                ld      a, (hl)
                ld      (hl), 0
                or      a
                ret     nz
                ld      a, (level_number)       ; (a mirror tile exists only on level 4: SDLPoP's mirror event)
                cp      4
                ret     nz
                ld      a, (CHAR_SAVE + OF_COL)
                ld      c, a
                ld      a, (CHAR_SAVE + OF_ROW)
                ld      b, a
                ld      a, (CHAR_SAVE + OF_ROOM)
                call    k_get_tile
                cp      T_MIRROR
                ret     nz
                call    pm_go
                ld      hl, PP_SAVE             ; KV: the kid again
                ld      de, KV
                jp      gcp16
pm_go:          call    load_frame
                call    distance_to_edge_weight
                ld      b, a
                ld      a, (K_DIR)
                or      a
                ld      a, b
                jr      nz, pm1
                cpl
                add     a, TILE_SIZEX
pm1:            sub     2
                ret     m
                ld      a, (K_COL)              ; x = 2 (x_bump[col + 5] + 10) - x, turned
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
                ld      a, (K_ROOM)
                ld      hl, DRAWN_ROOM
                cp      (hl)
                ret     nz
                call    load_frame_to_obj
                ld      a, (K_ROW)              ; clip_top = y_clip[row + 1] < obj_y (row -1: -60 as a word, never)
                inc     a
                ret     z
                add     a, a
                ld      e, a
                ld      d, 0
                ld      hl, y_clip_tbl
                add     hl, de
                ld      e, (hl)
                ld      a, e
                ld      (CLIP_TOP), a
                ld      hl, (OBJ_Y)
                or      a
                sbc     hl, de
                ret     z
                ret     m
                ld      a, (CF_IMG)
                cp      255
                ret     z
                inc     a
                ld      (pp_id), a
                ld      a, (CF_SWORD)
                and     0xc0
                ld      a, CH_KID
                jr      z, pm2
                ld      a, CH_GUARD
pm2:            ld      (pp_ch), a
                ld      hl, (OBJ_X)
                call    scr_x
                ld      (PP_SX), hl
                ld      (pp_x), hl
                ld      hl, (OBJ_Y)
                ld      (pp_y), hl
                ld      a, 40
                ld      (CLIP_RIGHT), a
                ld      a, (K_COL)              ; left clip: col * 32 + 9
                ld      l, a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      de, 9
                add     hl, de
                ld      (CLIP_LEFT), hl
                ld      a, 1
                ld      (PP_T1), a
                call    pp_blink                ; (the kid's case: the blink draws it as the shadow too)
                call    nz, pp_xd
                ld      (PP_XDV), a
                ld      a, (OBJT_LAST)
                ld      (PP_ORD + 6), a
                ld      a, 6
                ld      (pp_slot), a
                jp      pp_put
; pc_col: the compose column at V_COMPOSE (CRH rows, 4 planes) to MASKBUF (A = 0), or its pixels left of the clip
; (bits 0 .. PC_K - 1) back from MASKBUF (A = PC_K)
pc_col:         or      a
                jr      z, pcc0
                ld      b, a                    ; the mask (1 << k) - 1
                xor     a
pcc_m:          scf
                rla
                djnz    pcc_m
pcc0:           ld      (pcc_x + 1), a
                ld      de, MASKBUF
                ld      hl, (V_COMPOSE)
                ld      c, 4
pcc_p:          push    hl
                ld      a, (CRH)
                ld      b, a
pcc_r:          ld      a, (de)
                xor     (hl)
pcc_x:          and     0                       ; patched: the mask (0: keep the compose byte)
                xor     (hl)
                ld      (de), a
                ld      (hl), a
                inc     de
                ld      a, l
                add     a, 8
                ld      l, a
                jr      nc, pcc_n
                inc     h
pcc_n:          djnz    pcc_r
                pop     hl
                inc     h
                inc     h
                dec     c
                jr      nz, pcc_p
                ret


; ---------------------------------------------------------------- the bottom text (SDLPoP display_text_bottom)
; text_chk (after the tick's drawing): a text was set or erased (TEXT_GEN), or the death text's blink changes: the text
; overlay draws the text line
text_chk:       ld      a, (TEXT_GEN)
                cpl
                ld      hl, TXT_GEN_SHOWN
                cp      (hl)
                jp      nz, text_draw
                call    text_vis
                ld      hl, TXT_VIS
                cp      (hl)
                ret     z
                jp      text_draw
; text_vis: A = 0 while 'Press Button to Continue' (288 ticks) is in the dark phase of its blink (draw_game_frame:
; the last 72 ticks, erased while text_time_remaining % 12 > 3), else 1
text_vis:       ld      hl, (TEXT_TOTAL)
                ld      de, -288
                add     hl, de
                ld      a, h
                or      l
                ld      a, 1
                ret     nz
                ld      hl, (TEXT_REM)
                ld      a, h
                or      a
                ld      a, 1
                ret     nz
                ld      a, l
                cp      72
                ld      a, 1
                ret     nc
                ld      a, l
tv1:            sub     12
                jr      nc, tv1
                add     a, 12 - 4               ; (A = rem % 12 - 12: carry when rem % 12 >= 4)
                sbc     a, a
                inc     a
                ret

; ---------------------------------------------------------------- the flash (SDLPoP flash_if_hurt, do_flash)
; flash_tick (after the tick's drawing): the tick's flash (FLASH_NOW, EGA colour; draw_game_frame) shows the playfield's
; black in that colour for two frames, as SDLPoP's set_bg_attr does for 2/60 s: palette register 0 (colour 0) set while
; the beam is below the playfield, kept for two passes over its 192 rows, reset below it. FL_SHOWN = the MZ colour.
flash_tick:     ld      hl, FLASH_NOW
                ld      a, (hl)
                ld      (hl), 0
                ld      (FL_SHOWN), a
                or      a
                ret     z
                ld      b, a                    ; EGA IRGB -> MZ IGRB: bits 1 and 2 swapped
                and     9
                bit     1, b
                jr      z, flt1
                or      4
flt1:           bit     2, b
                jr      z, flt2
                or      2
flt2:           ld      (FL_SHOWN), a
                ld      c, a
                call    fl_out
                ld      a, c
                out     (PORT_PAL), a           ; PAL0 = the colour
                ld      b, 2
flt3:           call    fl_in
                call    fl_out
                djnz    flt3
                xor     a
                out     (PORT_PAL), a           ; PAL0 = black
                ret
; fl_in: wait until the beam is in the playfield (lines BEAM_Y0 .. BEAM_Y0 + 191 after the VBLN interrupt); fl_out:
; until it is not (keep BC)
fl_in:          call    fl_beam
                jr      nc, fl_in
                ret
fl_out:         call    fl_beam
                jr      c, fl_out
                ret
fl_beam:        push    bc                      ; carry: in the playfield
                call    beam_lines
                pop     bc
                ld      de, -BEAM_Y0
                add     hl, de
                ret     nc
                ld      de, -192
                add     hl, de
                ccf
                ret

; st_look: which character looks as in the last drawn tick (M8a part 7): st_res bit 0 the kid, bit 1 the guard. Each of
; his slots (the kid 0, 1, 6, the guard 2, 3) has the same visible flag, image (SD_LKEY, SD_LKEY2: frame, chtab, mirror,
; shift), screen rect, clip and XOR offset; this tick and the last have no overlay ops and no hurt splash, and no room
; was drawn since (sprite_forget sets ST_OK). Then his pixels, and everything under them, are as on screen, and his
; rect needs no redraw: what changed there (the other character, a tile, a falling floor) brings a rect of its own.
; PP_KU, PP_GU stay (oc_kidtouch: no torch chunk from the cache over a character).
ST_KEY          equ     0x01ca                  ; 50: per slot SD_DX .. SD_COMPOSE + 1 (9) and PP_XD, as last tick
ST_OK           equ     0x01fc                  ; 0: the last tick had no overlay op, no splash, no room drawn after it
st_look:        ld      a, (OV_NM)
                ld      hl, OV_NF
                or      (hl)
                ld      hl, SPR_SP + SD_DX
                or      (hl)
                ld      hl, SPR_SP2 + SD_DX
                or      (hl)
                ld      hl, ST_OK
                ld      c, (hl)
                ld      (hl), a
                or      c                       ; (not 0: neither of them)
                push    af
                ld      (st_chg), a
                ld      hl, st_tab
                ld      de, ST_KEY
                call    st_grp                  ; the kid
                pop     bc
                ld      a, (st_chg)
                push    af
                ld      a, b
                ld      (st_chg), a
                call    st_grp                  ; the guard
                pop     bc
                ld      c, 0
                ld      a, (st_chg)
                or      a
                jr      nz, stl1
                ld      c, 2
stl1:           ld      a, b
                or      a
                jr      nz, stl2
                inc     c
stl2:           ld      a, c
                ld      (st_res), a
                ret
; st_grp: HL = a group's slots (descriptor, slot; a descriptor 0x00xx ends it), DE = their keys: the keys replaced by
; this tick's, st_chg not 0 when one differed (a slot invisible then and now: not compared)
st_grp:         ld      a, (hl)
                inc     hl
                ld      b, (hl)
                inc     hl
                inc     b
                dec     b
                ret     z
                push    hl
                add     a, SD_DX
                ld      l, a
                ld      h, b
                ld      a, (de)
                or      (hl)
                jr      z, stg_n
                ld      b, SD_COMPOSE + 2 - SD_DX
                call    st_cmp
                pop     hl
                ld      a, (hl)                 ; its XOR offset
                inc     hl
                push    hl
                add     a, low PP_XD
                ld      l, a
                ld      h, high PP_XD
                ld      b, 1
                call    st_cmp
                pop     hl
                jr      st_grp
stg_n:          ld      hl, SD_COMPOSE + 3 - SD_DX
                add     hl, de
                ex      de, hl
                pop     hl
                inc     hl
                jr      st_grp
; st_cmp: B bytes at HL against the keys at DE; from the first that differs on they are copied and st_chg is set
st_cmp:         ld      a, (de)
                cp      (hl)
                jr      nz, stc1
                inc     hl
                inc     de
                djnz    st_cmp
                ret
stc1:           ld      c, b
                ld      b, 0
                ldir
                ld      a, 1
                ld      (st_chg), a
                ret
st_tab:         dw      SPR_A
                db      0
                dw      SPR_S
                db      1
                dw      SPR_MI
                db      6
                dw      0
                dw      SPR_G
                db      2
                dw      SPR_GS
                db      3
                dw      0
st_chg:         db      0
st_res:         db      0
