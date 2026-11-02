; ---------------------------------------------------------------- the bottom text line (M5, SDLPoP display_text_bottom)
; text_draw (from game.asm text_chk through the text overlay's stub, src/m4/ovl.asm): the text line as the logic state
; says: the text set last (TEXT_TOTAL 288: 'Press Button to Continue', blinking in its last 72 ticks (text_vis);
; 24 or 12 while IS_SHOW_TIME is still set: show_level's LEVEL n; else show_time's message from the time left; 0 or
; 36: none; the save overlay's GAME SAVED / UNABLE TO SAVE GAME (TEXT_MSG) before all of these), drawn like SDLPoP's display_text_bottom: rect_bottom_text (x 70..249, rows 193..201) black, the text in
; hc_font (1 px between characters) centred at x 160, glyph tops at row 193, colour 15. Every text fits x 80..239
; (byte columns 10..29): those columns are composed (all four planes the same bitmap) and copied; x 70..79 and
; 240..249 stay black. The glyphs: build/assets/font_text.inc (tools/build_assets.py).
TXB             equ     MASKBUF                 ; the line's bitmap: 7 rows x TXB_W bytes from x 80, bit 0 = leftmost
TXB_W           equ     20
TXC             equ     SPRBUF_B                ; the compose chunk (the overlay itself is in COMPOSE_A, window W2)
text_draw:      ld      a, (TEXT_GEN)
                cpl
                ld      (TXT_GEN_SHOWN), a
                call    text_vis
                ld      (TXT_VIS), a
                ld      hl, TXB                 ; blank
                ld      de, TXB + 1
                ld      bc, 7 * TXB_W - 1
                ld      (hl), 0
                ldir
                ld      b, a
                ld      de, td_str
                ld      a, (TEXT_MSG)           ; the save overlay's and the keys' texts while no text came after them
                or      a
                jr      z, td_nmsg
                ld      c, a
                ld      a, (TEXT_GEN)
                ld      hl, TEXT_MSG_GEN
                cp      (hl)
                jr      nz, td_msg0
                if defined CHEATS
                ld      a, c
                cp      7
                jp      z, td_timer
                endif
                ld      a, c                    ; (the pause shows through the blink's dark phase)
                add     a, a
                add     a, td_msgs % 256 - 2
                ld      l, a
                ld      a, td_msgs / 256
                adc     a, 0
                ld      h, a
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a
                jr      td_cp
td_msg0:        xor     a                       ; (replaced: forget it)
                ld      (TEXT_MSG), a
td_nmsg:        ld      a, b
                or      a
                jp      z, td_put               ; (the blink's dark phase)
                ld      a, (TEXT_TOTAL + 1)
                or      a
                ld      hl, str_press
                jr      nz, td_cp               ; (288)
                ld      a, (TEXT_TOTAL)
                or      a
                jr      z, td_put
                cp      36
                jr      z, td_put
                ld      a, (IS_SHOW_TIME)
                or      a
                jr      z, td_time
                ld      hl, str_level
                call    td_copy
                ld      a, (level_number)
                cp      13
                jr      nz, td_lv
                ld      a, 12
td_lv:          call    td_num
                jr      td_end
td_time:        ld      a, (REM_MIN)
                ld      hl, str_expired
                or      a
                jr      z, td_cp
                dec     a
                jr      z, td_sec
                inc     a
                call    td_num
                ld      hl, str_min
                jr      td_cp
td_sec:         ld      hl, (REM_TICK)          ; seconds: (rem_tick + 1) / 12
                inc     hl
                ld      bc, -12
                ld      a, -1
td_d12:         inc     a
                add     hl, bc
                jr      c, td_d12
                push    af
                call    td_num
                pop     af
                dec     a
                ld      hl, str_secs
                jr      nz, td_cp
                ld      hl, str_sec
td_cp:          call    td_copy
td_end:         xor     a
                ld      (de), a
                call    td_render
td_put:         ld      bc, 0x080a              ; the chunks: B = width, C = byte column
                call    td_chunk
                ld      bc, 0x0812
                call    td_chunk
                ld      bc, 0x041a
; td_chunk: the bitmap's byte columns C - 10 .. C - 10 + B - 1 into TXC (four planes), copied to the screen
td_chunk:       ld      a, c
                ld      (CRX), a
                ld      a, b
                ld      (CRW), a
                ld      a, 193
                ld      (CRY), a
                ld      a, 7
                ld      (CRH), a
                ld      hl, TXC
                ld      (V_COMPOSE), hl
                ld      a, c
                sub     10
                ld      e, a
                ld      d, 0
                ld      hl, TXB
                add     hl, de
                ld      de, TXC
                ld      c, 7
tdc_r:          push    bc
                push    hl
                push    de
                ld      c, b
                ld      b, 0
                ldir
                pop     hl
                ld      de, CW
                add     hl, de
                ex      de, hl
                pop     hl
                ld      bc, TXB_W
                add     hl, bc
                pop     bc
                dec     c
                jr      nz, tdc_r
                ld      de, TXC + COMPOSE_PLANE
                ld      a, 3
tdc_p:          ld      hl, TXC
                ld      bc, 7 * CW
                ldir
                ld      hl, COMPOSE_PLANE - 7 * CW
                add     hl, de
                ex      de, hl
                dec     a
                jr      nz, tdc_p
                jp      blit
; td_copy: the string at HL (0 ends it) to DE
td_copy:        ld      a, (hl)
                or      a
                ret     z
                ld      (de), a
                inc     hl
                inc     de
                jr      td_copy
; td_num: A = 0..99 in decimal to DE
td_num:         ld      b, '0' - 1
tdn1:           inc     b
                sub     10
                jr      nc, tdn1
                add     a, '0' + 10
                ld      c, a
                ld      a, b
                cp      '0'
                jr      z, tdn2
                ld      (de), a
                inc     de
tdn2:           ld      a, c
                ld      (de), a
                inc     de
                ret
; td_render: td_str into the bitmap, centred (SDLPoP draw_text: x = 70 + 180 / 2 - width / 2)
td_render:      ld      hl, td_str
                ld      c, 0                    ; the width: each character's + 1
tdr_w:          ld      a, (hl)
                or      a
                jr      z, tdr_x
                inc     hl
                push    hl
                push    bc
                call    td_glyph
                pop     bc
                pop     hl
                inc     a
                add     a, c
                ld      c, a
                jr      tdr_w
tdr_x:          ld      a, c
                srl     a
                neg
                add     a, 160 - 80
                ld      (td_x), a
                ld      hl, td_str
tdr_c:          ld      a, (hl)
                or      a
                ret     z
                inc     hl
                push    hl
                call    td_glyph
                push    af
                ld      a, h
                or      l
                call    nz, td_blit
                pop     af
                inc     a
                ld      hl, td_x
                add     a, (hl)
                ld      (hl), a
                pop     hl
                jr      tdr_c
; td_glyph: A = character -> A = its width, HL = its 7 rows (0 for the space)
td_glyph:       ld      c, a
                ld      hl, 0
                cp      ' '
                ld      a, TXT_SPACE_W
                ret     z
                ld      hl, txt_font
                ld      de, 9
tdg1:           ld      a, (hl)
                cp      c
                jr      z, tdg2
                add     hl, de
                jr      tdg1
tdg2:           inc     hl
                ld      a, (hl)
                inc     hl
                ret
; td_blit: HL = the 7 rows of a glyph: OR them into the bitmap at x td_x
td_blit:        ld      a, (td_x)
                rrca
                rrca
                rrca
                and     31
                ex      de, hl
                ld      l, a
                ld      h, 0
                ld      bc, TXB
                add     hl, bc
                ex      de, hl                  ; DE = the bitmap byte
                ld      a, (td_x)
                and     7
                ld      b, a                    ; the bit offset
                ld      c, 7
tdb_r:          push    bc
                ld      a, (hl)
                inc     hl
                push    hl
                ld      l, a
                ld      h, 0
                inc     b
                jr      tdb_s2
tdb_s:          add     hl, hl
tdb_s2:         djnz    tdb_s
                ld      a, (de)
                or      l
                ld      (de), a
                inc     de
                ld      a, (de)
                or      h
                ld      (de), a
                ld      hl, TXB_W - 1
                add     hl, de
                ex      de, hl
                pop     hl
                pop     bc
                dec     c
                jr      nz, tdb_r
                ret
td_x:           db      0
str_press:      db      'Press Button to Continue', 0
str_expired:    db      'TIME HAS EXPIRED!', 0
str_level:      db      'LEVEL ', 0
str_min:        db      ' MINUTES LEFT', 0
str_secs:       db      ' SECONDS LEFT', 0
str_sec:        db      ' SECOND LEFT', 0
str_saved:      db      'GAME SAVED', 0
str_unable:     db      'UNABLE TO SAVE GAME', 0
str_s_off:      db      'SOUND OFF', 0
str_s_on:       db      'SOUND ON', 0
str_version:    db      'PRINCE OF PERSIA V1.0', 0      ; (tools/kidsim.py VERSION_TEXT)
str_paused:     db      'GAME PAUSED', 0
td_msgs:        dw      str_saved, str_unable, str_s_off, str_s_on, str_version, str_paused
                if defined CHEATS
; TEXT_MSG 7 (the cheat T): minutes and seconds
td_timer:       ld      a, (REM_MIN)
                call    td_num
                ld      hl, str_t1
                call    td_copy
                ld      hl, (REM_TICK)
                inc     hl
                ld      bc, -12
                ld      a, -1
tdt1:           inc     a
                add     hl, bc
                jr      c, tdt1
                call    td_num
                ld      hl, str_t2
                jp      td_cp
str_t1:         db      ' MIN ', 0
str_t2:         db      ' SEC', 0
                endif
                include "../../build/assets/font_text.inc"
td_str:         ds      26
