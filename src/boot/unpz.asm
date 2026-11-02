; ---------------------------------------------------------------- PZ decoder (tools/pzpack.py)
; In: HL = compressed block, DE = destination. Out: DE = end of the output, HL = after the block. A' is used.
; Shared by the floppy loader / launcher (src/boot/boot.asm) and PRES (src/pres/pres.asm); the includer defines
; up_neg (2 bytes of RAM).
unpz:           ld      a, 0x80         ; bit buffer: empty (the sentinel bit only)
up_lit:         call    up_elias        ; literal run
                ldir
                add     a, a            ; after a literal run: 0 = repeat match, 1 = new match
                jr      nz, ul_1
                ld      a, (hl)
                inc     hl
                rla
ul_1:           jr      c, up_new
                call    up_elias        ; repeat match: length
up_copy:        push    hl
                ld      hl, (up_neg)
                add     hl, de
                ldir
                pop     hl
                add     a, a            ; after a match: 0 = literal run, 1 = new match
                jr      nz, ul_2
                ld      a, (hl)
                inc     hl
                rla
ul_2:           jr      nc, up_lit
up_new:         call    up_elias        ; (offset - 1) >> 8, plus 1; 256 = end of the block
                dec     b
                ret     z
                ex      af, af'
                ld      a, c
                neg
                ld      (up_neg + 1), a
                ld      a, (hl)         ; (-offset) & 255
                inc     hl
                ld      (up_neg), a
                ex      af, af'
                call    up_elias        ; length - 1
                inc     bc
                jr      up_copy
; interlaced Elias gamma: BC = 1, then (control 0, data bit) pairs until a control 1
up_elias:       ld      bc, 1
ue_loop:        add     a, a
                jr      nz, ue_1
                ld      a, (hl)
                inc     hl
                rla
ue_1:           ret     c
                add     a, a
                jr      nz, ue_2
                ld      a, (hl)
                inc     hl
                rla
ue_2:           rl      c
                rl      b
                jr      ue_loop

