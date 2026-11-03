; ---------------------------------------------------------------- the frame store's fill (the level-start overlay, W2)
; docs/ramdisk-tiers.md section 11. On a RAM disk of 1 MB and more (HO_RDTOP, the boot's probe; the harness pokes it)
; the chosen kid and sword keys (tools/fstore.py: class 1 on every such card, class 2 too from FS_TOP2) are generated
; into RAM-disk pages 8+ by the dedicated generator (src/m4/fsgen.asm, step 2: every stored variant of an image from
; one read of it per mirror, byte for byte the kernel's spr_fetch buffer). The boot clears the marker (page 8 FS_MARK:
; the build id and the class) and starts the game with ACT_FILL (src/m4/gstart.asm gs_fill: the fill on the loading
; screen, ff_bw > 0: its progress bar, then the title); every later start in the same session (PRES swaps, restarts)
; finds the marker and only patches fs_on (char_fetch, src/m4/sprite.asm) to the lookup (src/m4/fslook.asm). The
; harness, which does not boot, fills at game_start (no bar).
; fs_fill = the marker check, then one fg_run over both classes' mask tables (FS_IDS words: bit v = variant v =
; mirror * 8 + shift stored): class 1 allocates from FS_DATA in page 8, class 2 from class 1's end (FS_E1P:FS_E1A,
; tools/fstore.py), so the layout is the one of filling class 1 first, then class 2; the marker last.
; Interrupts are off; uses SPRBUF_A as the cell buffer, SPRBUF_B for the masks (copied from the RAM disk:
; FS_MPAGE:FS_MADDR, written by the boot and the harness), the generator's variables and row code and its own
; variables, the bit-reverse table (tables_init first). It leaves main RAM as a start without the fill does (dir_buf
; put back: tests/m7_launch.py compares it).
FF_MBUF         equ     SPRBUF_B                ; the masks (2 x FS_IDS words), fs_id (4), ff_class (1)
fs_mask1        equ     FF_MBUF
fs_mask2        equ     FF_MBUF + 2 * FS_IDS
fs_id           equ     FF_MBUF + 4 * FS_IDS
ff_class        equ     fs_id + 4               ; (right after fs_id: the marker's fifth byte)
ff_save         equ     FF_MBUF + 0x410         ; dir_buf's copy
FG_VARS         equ     FF_MBUF + 0x420         ; the generator's (src/m4/fsgen.asm)
ff_bw           equ     FF_MBUF + 0x460         ; the progress bar (ACT_FILL: the loading screen's): width in bytes
ff_bcol         equ     ff_bw + 1               ; (0: no bar), colour (right after ff_bw), its next byte in VRAM,
ff_bptr         equ     ff_bw + 2               ; the error term (keys x width)
ff_acc          equ     ff_bw + 4
ff_keys         equ     ff_bw + 6               ; the keys to fill
FG_CODE         equ     FF_MBUF + 0x480         ; the generator's row code
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
ff_build:       ld      hl, dir_buf
                ld      de, ff_save
                ld      bc, 8
                ldir
                ld      hl, SPRBUF_A            ; the table and the marker cleared (64 zero bytes at a time)
                ld      de, SPRBUF_A + 1
                ld      bc, 63
                ld      (hl), b
                ldir
                ld      a, FS_PAGE
                ld      de, 0
                call    far_seek
                dec     c
                ld      de, FS_DATA / 64
ffz:            ld      hl, SPRBUF_A
                call    fg_o64
                dec     de
                ld      a, d
                or      e
                jr      nz, ffz
                ld      a, RD_LV_PAGE           ; the kid's and the sword's directories (as load_level sets them)
                ld      (dir_tab + 3 * CH_KID), a
                ld      (dir_tab + 3 * CH_SWORD), a
                ld      hl, RD_DIR_KID
                ld      (dir_tab + 3 * CH_KID + 1), hl
                ld      hl, RD_DIR_SWORD
                ld      (dir_tab + 3 * CH_SWORD + 1), hl
                ld      a, FS_PAGE              ; class 1 from FS_DATA, class 2 from class 1's end
                ld      (fg_pa), a
                ld      hl, FS_DATA
                ld      (fg_pa + 1), hl
                ld      a, FS_E1P
                ld      (fg_pb), a
                ld      hl, FS_E1A
                ld      (fg_pb + 1), hl
                ld      hl, 0
                ld      (fg_id), hl
                ld      de, 0
                ld      a, (ff_class)
                cp      2
                jr      c, ff_gen
                ld      de, fs_mask2
ff_gen:         ld      hl, fs_mask1
                ld      bc, FS_IDS
                call    fg_run
ff_mark:        ld      hl, ff_save
                ld      de, dir_buf
                ld      bc, 8
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
                in      a, (0xe0)               ; VRAM on (the bit-reverse table is behind it: no image read meanwhile)
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

                include "../m4/fsgen.asm"

                if      FS_DATA % 64
                .error  ffz clears FS_DATA bytes in blocks of 64
                endif
                if      ff_class >= ff_save
                .error  the masks run into ff_save
                endif
                if      FG_VARS + FG_VARS_N > ff_bw
                .error  the generator's variables run into ff_bw
                endif
                if      ff_keys + 2 > FG_CODE
                .error  the fill's variables run into the row code
                endif
                if      FS_PAGE - LN_FS_PAGE + FS_MARK - LN_FS_MARK + FS_TOP1 - LN_FS_TOP
                .error  the boot's view of the frame store (src/boot/launch.inc) differs
                endif
                if      FG_CODE + FG_CODE_N > SPRBUF_B + 0x800
                .error  the generator's row code runs out of SPRBUF_B
                endif
