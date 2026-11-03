; ---------------------------------------------------------------- the frame store's fill (the level-start overlay, W2)
; docs/ramdisk-tiers.md "As built: step 1". On a RAM disk of 1 MB and more (HO_RDTOP, the boot's probe; the harness
; pokes it) the chosen kid and sword keys (tools/fstore.py: class 1 on every such card, class 2 too from FS_TOP2) are
; generated with today's fetch (dir_entry + spr_fetch: the kernel's own shift routines, so the pixels are the same by
; construction) into RAM-disk pages 8+, once: the marker (the build id and the class) at page 8 FS_MARK says the
; store is there (the game is restarted from its image at every launch; pages 8+ are written by nothing else).
; Then fs_on (char_fetch, src/m4/sprite.asm) is patched to the lookup (src/m4/fslook.asm). Interrupts are off; uses
; SPRBUF_A (outside W2) as the cell buffer, SPRBUF_B for the masks (copied from the RAM disk: FS_MPAGE:FS_MADDR, written
; by the boot and the harness) and its own variables, the shift tables (tables_init first). It leaves main RAM as a
; start without the fill does (spr_fetch's patched operands and dir_buf put back: tests/m7_launch.py compares them).
FF_MBUF         equ     SPRBUF_B                ; the masks (2 x FS_IDS words), fs_id (4), ff_class (1)
fs_mask1        equ     FF_MBUF
fs_mask2        equ     FF_MBUF + 2 * FS_IDS
fs_id           equ     FF_MBUF + 4 * FS_IDS
ff_class        equ     fs_id + 4               ; (right after fs_id: the marker's fifth byte)
FF_SAVE_A       equ     sf_rows + 1             ; spr_fetch's patched operands
FF_SAVE_N       equ     sf_stride + 3 - FF_SAVE_A
ff_save         equ     FF_MBUF + 0x410         ; their copy, then dir_buf's
ff_desc         equ     ff_save + 0x40          ; a sprite descriptor (SD_BUF = SPRBUF_A, the rest spr_fetch's)
ff_page         equ     ff_desc + SD_SIZE
ff_addr         equ     ff_page + 1
ff_n            equ     ff_page + 3
ff_id           equ     ff_page + 5
ff_v            equ     ff_page + 6
ff_bw           equ     ff_page + 7             ; the progress bar (ACT_FILL: the loading screen's): width in bytes
ff_bcol         equ     ff_page + 8             ; (0: no bar), colour (right after ff_bw), its next byte in VRAM,
ff_bptr         equ     ff_page + 9             ; the error term (keys x width)
ff_acc          equ     ff_page + 11
ff_keys         equ     ff_page + 13            ; the keys to fill
fs_fill:        ld      a, (HO_MAIN + HO_RDTOP)
                cp      FS_TOP1
                ret     c                       ; 512 KB: today's fetch
                ld      a, FS_MPAGE             ; the masks and the build id
                ld      de, FS_MADDR
                ld      hl, FF_MBUF
                ld      bc, 4 * FS_IDS + 4
                call    far_copy
                ld      a, (HO_MAIN + HO_RDTOP)
                ld      b, 1
                cp      FS_TOP2
                jr      c, ff_cls
                inc     b
ff_cls:         ld      a, b
                ld      (ff_class), a
                ld      hl, FS_N1
                dec     a
                jr      z, ff_k1
                ld      hl, FS_N1 + FS_N2
ff_k1:          ld      (ff_keys), hl
                ld      hl, 0
                ld      (ff_acc), hl
                ld      a, FS_PAGE              ; the marker
                ld      de, FS_MARK
                call    far_seek
                dec     c
                ld      hl, fs_id
                ld      b, 5                    ; (fs_id, then ff_class)
ffm_cmp:        in      a, (c)
                cp      (hl)
                jr      nz, ff_build
                inc     hl
                djnz    ffm_cmp
                jp      ff_on
ff_build:       ld      hl, FF_SAVE_A
                ld      de, ff_save
                ld      bc, FF_SAVE_N
                ldir
                ld      hl, dir_buf
                ld      c, 8
                ldir
                ld      hl, SPRBUF_A
                ld      (ff_desc + SD_BUF), hl
                ld      a, FS_PAGE              ; the table and the marker cleared
                ld      de, 0
                call    far_seek
                dec     c
                ld      d, high FS_DATA
                xor     a
                ld      b, a
ffz:            out     (c), a
                djnz    ffz
                dec     d
                jr      nz, ffz
                ld      a, RD_LV_PAGE           ; the kid's and the sword's directories (as load_level sets them)
                ld      (dir_tab + 3 * CH_KID), a
                ld      (dir_tab + 3 * CH_SWORD), a
                ld      hl, RD_DIR_KID
                ld      (dir_tab + 3 * CH_KID + 1), hl
                ld      hl, RD_DIR_SWORD
                ld      (dir_tab + 3 * CH_SWORD + 1), hl
                ld      a, FS_PAGE
                ld      (ff_page), a
                ld      hl, FS_DATA
                ld      (ff_addr), hl
                ld      hl, fs_mask1
                call    ff_pass
                ld      a, (ff_class)
                cp      2
                jr      c, ff_mark
                ld      hl, fs_mask2
                call    ff_pass
ff_mark:        ld      hl, ff_save
                ld      de, FF_SAVE_A
                ld      bc, FF_SAVE_N
                ldir
                ld      de, dir_buf
                ld      c, 8
                ldir
                ld      a, FS_PAGE              ; the marker last: an interrupted fill is redone
                ld      de, FS_MARK
                call    far_seek
                dec     c
                ld      hl, fs_id
                ld      b, 5
                otir
ff_on:          ld      hl, fs_look
                ld      (fs_on + 1), hl
fs_done:        ret

; ff_pass: HL = the mask table (FS_IDS words: bit v = variant v = mirror * 8 + shift stored)
ff_pass:        xor     a
                ld      (ff_id), a
ffp_id:         ld      e, (hl)
                inc     hl
                ld      d, (hl)
                inc     hl
                push    hl
                xor     a
                ld      (ff_v), a
ffp_v:          srl     d
                rr      e
                push    de
                call    c, ff_key
                pop     de
                ld      hl, ff_v
                inc     (hl)
                ld      a, d
                or      e
                jr      nz, ffp_v
                pop     hl
                ld      a, (ff_id)
                inc     a
                ld      (ff_id), a
                cp      FS_IDS
                jr      c, ffp_id
                ret

; ff_key: the entry of (ff_id, ff_v) at (ff_page, ff_addr) (the next page when it does not fit: tools/fstore.py the same)
ff_key:         ld      a, (ff_id)
                cp      FS_SWORD
                ld      c, a
                ld      a, CH_KID
                jr      c, ffk_d
                ld      a, c
                sub     FS_SWORD
                ld      c, a
                ld      a, CH_SWORD
ffk_d:          call    dir_entry               ; HL = the 8-byte entry
                push    hl
                pop     ix
                ld      a, (ix+3)               ; bytes = (w + 1) * 4 * h
                inc     a
                add     a, a
                add     a, a
                ld      e, a
                ld      d, 0
                ld      b, (ix+4)
                ld      hl, 0
ffk_m:          add     hl, de
                djnz    ffk_m
                ld      (ff_n), hl
                ld      de, 4
                add     hl, de
                ld      de, (ff_addr)
                add     hl, de
                jr      nc, ffk_fit             ; (addr + bytes + 4 > 0xFFFF: the next page)
                ld      hl, ff_page
                inc     (hl)
                ld      hl, 0
                ld      (ff_addr), hl
ffk_fit:        ld      a, (ff_v)               ; today's fetch into SPRBUF_A
                and     7
                ld      e, a
                ld      d, 0
                ld      a, (ff_v)
                rrca
                rrca
                rrca
                and     1
                ld      hl, ff_desc
                call    spr_fetch
                ld      a, (ff_id)              ; the key's slot: id * 64 + v * 4
                ld      l, a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      a, (ff_v)
                add     a, a
                add     a, a
                or      l
                ld      e, a
                ld      d, h
                ld      a, FS_PAGE
                call    far_seek
                dec     c
                ld      a, (ff_page)
                out     (c), a
                ld      a, (ff_addr + 1)
                out     (c), a
                ld      a, (ff_addr)
                out     (c), a
                ld      a, (ff_page)            ; the entry: ow, h, the byte count, the cell buffer
                ld      de, (ff_addr)
                call    far_seek
                dec     c
                ld      a, (ff_desc + SD_OW)
                out     (c), a
                ld      a, (ff_desc + SD_H)
                out     (c), a
                ld      de, (ff_n)
                out     (c), e
                out     (c), d
                ld      hl, SPRBUF_A
                ld      b, e
                dec     de
                inc     d
ffk_o:          otir
                dec     d
                jr      nz, ffk_o
                ld      hl, (ff_n)
                ld      de, 4
                add     hl, de
                ld      de, (ff_addr)
                add     hl, de
                ld      (ff_addr), hl
; ff_prog: the progress bar after a key (ff_bw bytes over ff_keys keys)
ff_prog:        ld      a, (ff_bw)
                or      a
                ret     z
                ld      e, a
                ld      d, 0
                ld      hl, (ff_acc)
                add     hl, de
ffp_l:          ld      de, (ff_keys)
                or      a
                sbc     hl, de
                jr      c, ffp_x
                ld      (ff_acc), hl
                in      a, (0xe0)               ; VRAM on (the shift tables are behind it: no fetch meanwhile)
                ld      a, (ff_bcol)
                or      0x80                    ; REPLACE
                out     (PORT_WF), a
                ld      hl, (ff_bptr)
                push    hl
                ld      de, 40
                ld      b, 8
ffp_row:        ld      (hl), 0xff
                add     hl, de
                djnz    ffp_row
                in      a, (0xe1)               ; VRAM off
                pop     hl
                inc     hl
                ld      (ff_bptr), hl
                ld      hl, (ff_acc)
                jr      ffp_l
ffp_x:          add     hl, de
                ld      (ff_acc), hl
                ret

                if      FF_SAVE_N + 8 > ff_desc - ff_save
                .error  ff_save is too small
                endif
                if      ff_class >= ff_save
                .error  the masks run into ff_save
                endif
                if      FS_PAGE - LN_FS_PAGE + FS_MARK - LN_FS_MARK + FS_TOP1 - LN_FS_TOP
                .error  the boot's view of the frame store (src/boot/launch.inc) differs
                endif
                if      ff_keys + 2 >= SPRBUF_B + 0x800
                .error  the fill's variables run out of SPRBUF_B
                endif
