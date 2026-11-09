; The low code, part 1 (M8a part 25, window WL = low RAM 0x0500-0x06FF, src/m4/ovl.asm OVL_LOW): the lazy shadow of
; choppers' and spikes' pictures (src/m4/frmlow.asm; part 2: src/m4/ovl_low2.asm). Assembled after the main program against its symbols
; (build/ovl_low.inc, tools/ovltool.py). Not an overlay that comes and goes: game_start (src/m4/gstart.asm) copies it in
; once at every start of the program (the launcher zeroes low RAM), and nothing replaces it. Its image has its own place
; in the RAM disk (page OVL_LOW_PAGE; tests/m4_game.py and tools/mkgamedisk.py write it). docs/memory.md "The free low
; RAM 0x0500-0x077F".
                include "../../build/ovl_low.inc"
                include "../boot/launch.inc"
                org     OVL_WL
ovl_id          equ     OVL_LOW
ovl_rd_page     equ     OVL_LOW_PAGE
ovl_rd_addr     equ     OVL_LOW_RD
ovl_rd_last     equ     0xffff          ; (page 4 0xFE00-0xFFFF)
ovl_entry:      jp      rs_pre                  ; LC_RSPRE (gfx.asm restore_shadow's head)
                jp      rs_post                 ; LC_RSPOST (its tail)
                jp      sw_pre                  ; LC_SWPRE (gfx.asm shadow_write's head)
                jp      lc_cr                   ; LC_CR (frmlow2.asm)
                jp      cmp4                    ; LC_CMP4 (frmlow2.asm)

                include "../m4/frmlow.asm"
ovl_end:
                if ovl_end > OVL_WL_END
                .error the low code is larger than its window WL
                endif
