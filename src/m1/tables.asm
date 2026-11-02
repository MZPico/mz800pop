; ---------------------------------------------------------------- tables (the bit-reverse and shift tables at TABBASE)
; Included by src/m1/gfx.asm, or by the game's level-start overlay (src/m4/gstart.asm: it runs once, at the start).
tables_init:    ld      hl, TABBASE     ; bit reverse
tirev:          ld      c, l
                xor     a
                ld      e, 8
tirbit:         rr      c
                rla
                dec     e
                jr      nz, tirbit
                ld      (hl), a
                inc     l
                jr      nz, tirev
                ld      d, 1            ; s = 1..7
tis:            ld      a, d
                add     a, a
                add     a, high TABBASE
                ld      h, a            ; lo page
                ld      l, 0
tilo:           ld      a, l
                ld      e, d
tishl:          add     a, a
                dec     e
                jr      nz, tishl
                ld      (hl), a         ; lo[s][b] = b << s
                inc     h               ; hi page
                ld      a, 8
                sub     d
                ld      e, a            ; 8-s
                ld      a, l
tishr:          srl     a
                dec     e
                jr      nz, tishr
                ld      (hl), a
                dec     h
                inc     l
                jr      nz, tilo
                inc     d
                ld      a, d
                cp      8
                jr      nz, tis
                ret
