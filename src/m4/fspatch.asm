; ---------------------------------------------------------------- an animated tile's records patched in place
; Included by the frames overlay (src/m4/frames.asm: choppers, spikes) and the loose-floor overlay
; (src/m4/loosestep.asm, M8a part 28): each overlay has its own copy.
; fs_patch0: A = the list (0 back, 2 fore; 1: the back of the tile right of VS_TAG), B..C = the ids to look for, E =
; the new id: the first such CH_ENV record of the tile gets it, its bottom row kept; HL = that row; carry: none found.
; fs_patch: the same with the bottom row fs_yb
fs_patch0:      ld      hl, 0xffff
                ld      (fs_yb), hl
fs_patch:       ld      d, a
                ld      a, (VS_TAG)
                bit     0, d
                jr      z, fp_1
                inc     a
                res     0, d
fp_1:           ld      (OP_TAG), a
                ld      a, d
                ld      (OP_LIST), a
                ld      a, b
                ld      (OP_LO), a
                ld      a, c
                ld      (OP_HI), a
                ld      a, e
                ld      (fs_id), a
                ld      a, CH_ENV
                ld      (OP_CH), a
                ld      a, 1
                ld      (OP_ONLY), a
                call    op_patch                ; (find only: HL = the record, A != 0)
                push    af
                xor     a
                ld      (OP_ONLY), a
                pop     af
                or      a
                scf
                ret     z
                push    hl
                pop     ix                      ; IX = the record
                ld      a, (fs_id)
                ld      (ix + 2), a
                ld      c, a
                ld      a, CH_ENV
                call    dir_entry
                inc     hl
                inc     hl
                inc     hl
                ld      b, (hl)                 ; w
                inc     hl
                ld      c, (hl)                 ; h
                ld      hl, (fs_yb)             ; the bottom row: given, or the record's
                ld      a, h
                and     l
                inc     a
                jr      nz, fp_2
                ld      l, (ix + 4)
                ld      h, (ix + 5)
                ld      e, (ix + 7)
                ld      d, 0
                add     hl, de
                dec     hl
                ld      (fs_yb), hl
fp_2:           ld      (ix + 6), b
                ld      (ix + 7), c
                ld      b, 0                    ; top = bottom - h + 1
                or      a
                sbc     hl, bc
                inc     hl
                ld      (ix + 4), l
                ld      (ix + 5), h
                ld      b, h                    ; the slice's extent grows with the new image (room.asm yr_merge:
                ld      c, l                    ; BC = top, HL = bottom + 1, DE = the slice)
                ld      hl, (fs_yb)
                inc     hl
                ld      a, (OP_LIST)
                ld      e, a
                add     a, a
                add     a, a
                add     a, e
                add     a, a
                add     a, a
                add     a, a                    ; list * 40
                ld      e, a
                ld      a, (OP_TAG)
                add     a, e
                ld      e, a
                ld      d, 0
                call    yr_merge
                ld      hl, (fs_yb)
                or      a
                ret
fs_yb:          dw      0                       ; a piece's bottom row
