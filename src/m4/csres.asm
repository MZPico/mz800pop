; ---------------------------------------------------------------- moving parts: cs_scan in main (M8a part 24)
; cs_scan of src/m4/colshift.asm (both the gate and the door overlay use it), moved out of them in M8a part 24 to make
; room in the gate overlay, and its variables.
; cs_scan: A = tag, D..E = an id range, C = k: in the tag's back slice every CH_ENV record with an id in D..E moves by
; k rows up (ytop -= k; its slice's extent widened: room.asm sb_yr). Out: HL = the last such record, Z: none. (k = 0:
; only finds it.)
cs_scan:        ld      (cs_tag), a
                ld      (cs_lo), de
                ld      e, a
                ld      a, c
                ld      (cs_kk), a
                ld      hl, 0
                ld      (cs_last), hl
                ld      d, h
                ld      hl, SL_CNT
                add     hl, de
                ld      b, (hl)
                ld      hl, SL_START
                add     hl, de
                ld      l, (hl)
                ld      h, d
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      de, (opl_base)
                add     hl, de                  ; the slice's first record
                inc     b
                jr      css_n1
css_l:          push    bc
                push    hl
                inc     hl
                ld      a, (hl)                 ; chtab
                cp      CH_ENV
                jr      nz, css_n
                inc     hl
                ld      a, (hl)                 ; id: D <= id <= E (kept in cs_lo as E, D)
                ld      hl, cs_lo + 1
                cp      (hl)
                jr      c, css_n
                dec     hl
                cp      (hl)
                jr      z, css_y
                jr      nc, css_n
css_y:          pop     hl
                push    hl
                ld      (cs_last), hl
                ld      (sb_rec), hl
                ld      de, 4
                add     hl, de
                ld      a, (cs_kk)
                ld      c, a
                rla
                sbc     a, a
                ld      b, a                    ; BC = k
                ld      e, (hl)
                inc     hl
                ld      d, (hl)
                ex      de, hl
                or      a
                sbc     hl, bc
                ex      de, hl
                ld      (hl), d
                dec     hl
                ld      (hl), e
                ld      a, (cs_tag)
                ld      e, a
                ld      d, 0
                call    sb_yr
css_n:          pop     hl
                ld      de, 8
                add     hl, de
                pop     bc
css_n1:         djnz    css_l
                ld      hl, (cs_last)
                ld      a, h
                or      l
                ret
cs_kk:          db      0
cs_tag:         db      0
cs_lo:          dw      0
cs_last:        dw      0
