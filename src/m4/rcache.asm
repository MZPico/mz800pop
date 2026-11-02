; M4: run_rect's lay pass from the ops its scan recorded (RR_PTRS, in lay order) instead of a second walk over
; the slice tables; a copy-mode op that the next op repeats lower down is laid only down to the next one's top
; row (a door's slices overlap by two rows). (A cache of the composed prefix per redrawn rect was tried: a door
; step repeats only 3 ops before its moving slices, and the picture load cost as much as it saved.)
rc_m:           db      0                       ; ops to lay (from the cover on)
rc_e:           dw      0                       ; their pointers
rc_i:           db      0

; rc_run: run_rect after its scan (rr_cnt ops recorded, rr_last = the cover's index + 1 or 0): compose the rect
; and set carry; no carry when the list does not apply (room draws through the buckets, too many ops)
rc_run:         ld      a, (bkt_on)
                or      a
                ret     nz
                ld      a, (rr_cnt)
                cp      RC_MAX + 1
                ret     nc
                ld      c, a
                ld      a, (rr_last)            ; from the cover on, or all of them over black
                or      a
                jp      nz, rc_k
                push    bc
                ld      a, (CRX)
                ld      b, a
                ld      a, (CRY)
                ld      c, a
                ld      a, (CRW)
                ld      d, a
                ld      a, (CRH)
                ld      e, a
                call    fill_black
                pop     bc
                ld      a, 1
rc_k:           dec     a
                ld      b, a
                ld      a, c
                sub     b
                ld      (rc_m), a
                ld      a, b
                add     a, a
                ld      l, a
                ld      h, RR_PTRS >> 8
                ld      (rc_e), hl
                xor     a
rc_lay:         ld      (rc_i), a
                ld      hl, rc_m
                cp      (hl)
                jp      nc, rc_done
                add     a, a
                ld      hl, (rc_e)
                add     a, l
                ld      l, a
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a
                ld      (OPL_PTR), hl
                call    rc_ahead
                ld      a, (rc_i)
                inc     a
                jp      rc_lay
rc_done:        scf
                ret
; rc_ahead: lay the op at OPL_PTR (pointer rc_i of rc_e); a copy-mode op that the next op repeats lower down
; (same flags, image and column: the same columns and edge bits, laid over it) is laid only down to the next
; one's top row (a door's slices overlap by two rows)
rc_ahead:       ld      a, (rc_i)
                inc     a
                ld      hl, rc_m
                cp      (hl)
                jp      nc, rl_lay
                add     a, a
                ld      hl, (rc_e)
                add     a, l
                ld      l, a
                ld      e, (hl)
                inc     hl
                ld      d, (hl)
                ex      de, hl
                ld      de, -8
                add     hl, de                  ; HL = the next record
                ex      de, hl
                ld      hl, (OPL_PTR)
                ld      bc, -8
                add     hl, bc                  ; HL = this record
                ld      a, (hl)
                and     0x0c
                jp      nz, rl_lay
                ld      b, 4
ra_c:           ld      a, (de)
                cp      (hl)
                jp      nz, rl_lay
                inc     hl
                inc     de
                djnz    ra_c
                ld      a, (de)                 ; d = next ytop - ytop: 0 <= d < h
                sub     (hl)
                ld      c, a
                inc     hl
                inc     de
                ld      a, (de)
                sbc     a, (hl)
                jp      nz, rl_lay
                inc     hl
                inc     hl
                ld      a, c
                or      a
                ret     z                       ; the same place: wholly laid over
                cp      (hl)
                jp      nc, rl_lay
                ex      de, hl                  ; the next ytop - CRY: rows of the rect left above it
                ld      d, (hl)
                dec     hl
                ld      e, (hl)
                ld      a, (CRY)
                ld      l, a
                ld      h, 0
                ex      de, hl
                or      a
                sbc     hl, de
                ret     c                       ; (at or above the rect's top: nothing of it shows)
                ret     z
                ld      a, h
                or      a
                jp      nz, rl_lay
                ld      a, (CRH)
                cp      l
                jp      c, rl_lay
                jp      z, rl_lay
                push    af
                ld      a, l
                ld      (CRH), a
                call    rl_lay
                pop     af
                ld      (CRH), a
                ret
