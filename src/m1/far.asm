; ---------------------------------------------------------------- far storage driver
; Backend: STD / MZ-1R18 paged RAM disk (E9 page, EB address, EA data auto-increment).
; (pico_rd and memext backends come later through the same entry points.)
RD_PAGE         equ     0xe9
RD_DATA         equ     0xea
RD_ADDR         equ     0xeb
                if RD_ADDR - RD_DATA - 1
                .error shadow_write switches the ports with dec c / inc c
                endif

; far_seek: A = page, DE = address within the page
far_seek:       out     (RD_PAGE), a
                ld      b, d
                ld      c, RD_ADDR
                ld      a, e
                out     (c), a
                ret

; far_seek_entry: IX = directory entry, HL = 16-bit offset from the entry's start
far_seek_entry: ld      e, (ix+2)
                ld      d, (ix+1)
                add     hl, de
                ld      a, (ix+0)
                adc     a, 0
                ex      de, hl
                jr      far_seek

; far_read: HL = destination, B = byte count (1..255)
far_read:       ld      c, RD_DATA
                inir
                ret

; far_copy: A = page, DE = address in the page, HL = destination, BC = byte count (any size)
far_copy:       push    bc
                push    hl
                call    far_seek
                pop     hl
                pop     de              ; DE = count
                ld      c, RD_DATA
fc_full:        ld      a, d
                or      a
                jr      z, fc_rest
                ld      b, 0
                inir                    ; 256 bytes
                dec     d
                jr      fc_full
fc_rest:        ld      a, e
                or      a
                ret     z
                ld      b, a
                inir
                ret
