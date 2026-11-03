; ---------------------------------------------------------------- the frame store's lookup (main code)
; char_fetch (src/m4/sprite.asm, the low block) jumps here on a miss of the slot's one-entry cache once the level-start
; overlay's fill (src/m4/fstore.asm) has patched fs_on: IY = the descriptor, A = the frame, C = chtab << 4 | mirror << 3 |
; shift. A stored key: the cell buffer from the RAM disk, then cf_xb (the byte column); else today's fetch (cf_fetch).
; docs/ramdisk-tiers.md "As built: step 1". Key table: page FS_PAGE, id * 64 + (mirror * 8 + shift) * 4 = the entry's page (0: not stored), address hi, lo;
; the entry: ow, h, the byte count (2), then the cell buffer exactly as spr_fetch leaves it.
                include "../../build/assets/fstore_equ.inc"
fs_look:        ld      b, a                    ; B = frame
                ld      a, c
                and     0xf0                    ; the chtab
                jr      z, fsl_sw               ; (CH_SWORD = 0: ids FS_SWORD + frame)
                cp      CH_KID << 4
                jr      nz, fsl_no              ; (the guards: not stored)
                ld      a, b
                jr      fsl_id
fsl_sw:         ld      a, b
                add     a, FS_SWORD
fsl_id:         rrca
                rrca                            ; A = id >> 2 | (id & 3) << 6
                ld      h, a
                and     0xc0
                ld      l, a
                ld      a, c
                and     15
                add     a, a
                add     a, a
                or      l
                ld      l, a
                ld      a, h
                and     0x3f
                ld      h, a                    ; HL = the key's slot
                ld      a, FS_PAGE
                out     (RD_PAGE), a
                ld      b, h
                ld      c, RD_ADDR
                out     (c), l
                dec     c                       ; (RD_DATA)
                in      a, (c)
                or      a
                jr      z, fsl_no               ; not stored
                in      d, (c)
                in      e, (c)
                out     (RD_PAGE), a
                ld      b, d
                inc     c
                out     (c), e
                dec     c
                push    iy
                pop     hl
                inc     hl
                inc     hl
                ini                             ; SD_OW
                ini                             ; SD_H
                in      e, (c)
                in      d, (c)                  ; DE = ow * 4 * h
                ld      l, (iy+SD_BUF)
                ld      h, (iy+SD_BUF+1)
                ld      b, e
                dec     de
                inc     d
fsl_rd:         inir
                dec     d
                jr      nz, fsl_rd
                jp      cf_xb
                if      RD_ADDR - RD_DATA - 1
                .error  the store's lookup switches the ports with dec c / inc c
                endif
fsl_no:         ld      a, (iy+SD_FRAME)
                jp      cf_fetch
