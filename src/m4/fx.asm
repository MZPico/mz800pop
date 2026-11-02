; ---------------------------------------------------------------- M5 drawing: the resident per-tick part
; The shadow's XOR copy (spr_xor), the upside-down screen's chunk tops (fl_top, fl_untop: patched into the copy
; scheduler by set_flip in the room overlay; blit_flip in gfx.asm). Low block: nothing here runs inside blit. The
; bottom text check and the flash: people2.asm.

; ---------------------------------------------------------------- the shadow's XOR copy (SDLPoP blitters_3_xor)
; spr_xor: IY = descriptor (spr_draw has just drawn it into the compose chunk), A = d (1 or 2): the image again d px
; further right, XORed per plane: SDLPoP's blit_xor XORs the RGB values, which for these RGBI colours is the XOR of
; the colour numbers. The kid's black (stored as colour 8: sprite images have no mask) XORs nothing, and where the
; first copy left a black pixel the result is the XOR colour (black ^ c = c). Per row: the row shifted d px into SXT
; (plane p cell j at SXT + 16 p + j, j = 0 .. ow), the first copy's black pixels at SXT + 64 + j, then the visible
; cells applied: c0..2 ^= v0..2, c3 = (c3 & ~(black & vm)) ^ (v3 & vm) with vm = v0 | v1 | v2.
spr_xor:        ld      (SX_D), a
                ld      a, 1
                call    sd_bounds               ; (one column more; returns from here when nothing shows)
                ld      (SX_DST), de            ; (V_ROWOFF: the first visible cell's source)
                ld      a, (V_C0)               ; j0 = c0 - xb: the first visible cell
                sub     (iy+SD_XB)
                ld      (SX_J0), a
                ld      c, a                    ; the source cells shifted: ja = max(j0 - 1, 0) ..
                or      a
                jr      z, sx_a0
                dec     a
sx_a0:          ld      (sx_ja), a
                ld      b, a
                ld      a, (V_PX)               ; .. jb = min(j0 + cells, ow) (exclusive)
                add     a, c
                cp      (iy+SD_OW)
                jr      c, sx_b0
                ld      a, (iy+SD_OW)
sx_b0:          ld      e, a
                sub     c
                ld      (sx_nm), a              ; the visible cells with a source cell (the first copy's black)
                ld      a, e
                sub     b                       ; n = jb - ja (0 .. 8)
                ld      (sx_n), a
                ld      e, a
                add     a, b
                sub     c
                sub     8
                ld      l, a                    ; IX offset from the visible source: 4 (ja + n - 8 - j0)
                ld      h, 0
                bit     7, a
                jr      z, sx_k0
                dec     h
sx_k0:          add     hl, hl
                add     hl, hl
                ld      (sx_ko), hl
                ld      a, 8                    ; the unrolled shift's entry: sx_unr + 6 (8 - n)
                sub     e
                ld      e, a
                add     a, a
                add     a, e
                add     a, a
                ld      e, a
                ld      d, 0
                ld      hl, sx_unr
                add     hl, de
                ld      (sx_call + 1), hl
sx_row:         ld      hl, (V_ROWOFF)          ; 1. cells ja .. jb - 1 shifted d px into SXT + 16 p + j, and
                ld      de, (sx_ko)             ; SXT + 16 p + jb what moves out of cell jb - 1
                add     hl, de
                push    hl
                pop     ix
                ld      a, (sx_ja)
                ld      e, a
                ld      d, high SXT
                ld      c, 4
sx_p:           push    de
                or      a                       ; (nothing left of cell ja that matters)
sx_call:        call    0                       ; patched: sx_unr + 6 (8 - n)
                ld      a, (SX_D)
                dec     a
                jr      z, sx_s3
                pop     hl                      ; d = 2: once more
                push    hl
                ld      a, (sx_n)
                ld      b, a
                inc     b
                or      a
sx_s2:          rl      (hl)
                inc     l
                djnz    sx_s2
sx_s3:          pop     de
                inc     ix                      ; the next plane
                ld      a, e
                add     a, 16
                ld      e, a
                dec     c
                jr      nz, sx_p
                ld      a, (SX_J0)              ; 2. the first copy's black pixels in the visible cells:
                add     a, 64                   ; s3 & ~(s0 | s1 | s2) at SXT + 64 + j (0 where no source)
                ld      e, a
                ld      hl, (V_ROWOFF)
                ld      a, (sx_nm)
                or      a
                jr      z, sx_m1
                ld      b, a
sx_m:           ld      a, (hl)
                inc     hl
                or      (hl)
                inc     hl
                or      (hl)
                inc     hl
                cpl
                and     (hl)
                inc     hl
                ld      (de), a
                inc     e
                djnz    sx_m
sx_m1:          xor     a
                ld      (de), a
                ld      a, (SX_J0)              ; 3. the visible cells
                ld      l, a
                ld      h, high SXT
                ld      de, (SX_DST)
                ld      a, (V_PX)
sx_c:           ex      af, af'                 ; (A' = cells left)
                ld      a, (hl)                 ; plane 0
                ld      c, a                    ; (C = vm)
                ex      de, hl
                xor     (hl)
                ld      (hl), a
                inc     h
                inc     h
                ex      de, hl
                set     4, l                    ; plane 1
                ld      a, (hl)
                ld      b, a
                or      c
                ld      c, a
                ld      a, b
                ex      de, hl
                xor     (hl)
                ld      (hl), a
                inc     h
                inc     h
                ex      de, hl
                res     4, l                    ; plane 2
                set     5, l
                ld      a, (hl)
                ld      b, a
                or      c
                ld      c, a
                ld      a, b
                ex      de, hl
                xor     (hl)
                ld      (hl), a
                inc     h
                inc     h
                ex      de, hl
                set     4, l                    ; plane 3
                ld      a, (hl)
                and     c
                ld      b, a                    ; v3 & vm
                ld      a, l
                xor     0x70                    ; (SXT + 64 + j)
                ld      l, a
                ld      a, (hl)
                and     c
                cpl
                ex      de, hl
                and     (hl)
                xor     b
                ld      (hl), a
                ld      a, h
                sub     6
                ld      h, a
                inc     l                       ; the next compose column
                ex      de, hl
                res     6, l
                inc     l                       ; the next cell
                ex      af, af'
                dec     a
                jr      nz, sx_c
                ld      hl, (SX_DST)            ; the next row
                ld      de, CW
                add     hl, de
                ld      (SX_DST), hl
                ld      hl, (V_ROWOFF)
                ld      e, (iy+SD_OW)
                ld      d, 0
                add     hl, de
                add     hl, de
                add     hl, de
                add     hl, de
                ld      (V_ROWOFF), hl
                ld      hl, V_N
                dec     (hl)
                jp      nz, sx_row
                ret

; sx_unr: one plane of a row shifted 1 px (rla through the cells, carry = the bits moving on), IX = the source of the
; entry's first cell, DE = the destination; entered at sx_unr + 6 (8 - n) for n cells; the bits out of the last cell
; go to the next destination byte
sx_unr:         ld      a, (ix+0)
                rla
                ld      (de), a
                inc     e
                ld      a, (ix+4)
                rla
                ld      (de), a
                inc     e
                ld      a, (ix+8)
                rla
                ld      (de), a
                inc     e
                ld      a, (ix+12)
                rla
                ld      (de), a
                inc     e
                ld      a, (ix+16)
                rla
                ld      (de), a
                inc     e
                ld      a, (ix+20)
                rla
                ld      (de), a
                inc     e
                ld      a, (ix+24)
                rla
                ld      (de), a
                inc     e
                ld      a, (ix+28)
                rla
                ld      (de), a
                inc     e
                ld      a, 0
                rla
                ld      (de), a
                ret
sx_ja:          db      0
sx_n:           db      0
sx_nm:          db      0
sx_ko:          dw      0

; ---------------------------------------------------------------- the upside-down screen (SDLPoP flip_screen)
; While upside_down, blit (gfx.asm blit_flip) writes a playfield chunk's rows at 191 - row, its compose rows bottom up;
; the copy scheduler then keeps the chunk's top screen row in the pending list: set_flip patches oc_rec (fl_top) and
; pf_blit1 (fl_untop) to convert.
; fl_top: A = the screen top of the compose chunk (CRY, CRH) upside down: 192 - CRY - CRH (keeps HL)
fl_top:         push    hl
                ld      hl, CRY
                ld      a, 192
                sub     (hl)
                inc     hl
                inc     hl                      ; (CRH)
                sub     (hl)
                pop     hl
                ret
; fl_untop: IX = a pending chunk with its screen top: A = its CRY
fl_untop:       ld      a, 192
                sub     (ix+1)
                sub     (ix+3)
                ret

