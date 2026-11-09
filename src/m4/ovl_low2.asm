; The low code, part 2 (M8a part 25, window WL2 = low RAM 0x0E00-0x0FFF, src/m4/ovl.asm OVL_LOW2): choppers' and
; spikes' steps, the complete pictures' direct copy and save (src/m4/frmlow2.asm; part 1: src/m4/ovl_low.asm).
; Assembled after the main program against its symbols (build/ovl_low2.inc, tools/ovltool.py). Not an overlay that
; comes and goes: game_start (src/m4/gstart.asm) copies it in once at every start of the program (the launcher zeroes
; low RAM), and nothing replaces it. Its image has its own place in the RAM disk (page OVL_LOW2_PAGE; tests/m4_game.py
; and tools/mkgamedisk.py write it). docs/memory.md "The low code".
                include "../../build/ovl_low2.inc"
                include "../boot/launch.inc"
                org     OVL_WL2
ovl_id          equ     OVL_LOW2
ovl_rd_page     equ     OVL_LOW2_PAGE
ovl_rd_addr     equ     OVL_LOW2_RD
ovl_rd_last     equ     0xdfff                  ; (page 1 0xDE18-0xDFFF; the sound bank from 0xE000)
ovl_entry:      jp      lc_step                 ; LC_STEP (src/m4/frames.asm fs_step)
                jp      lc_direct               ; LC_DIRECT (frmlow.asm lc_chunk)
                jp      lc_save                 ; LC_SAVE (sprite.asm obj_chunk, after the composition)
                jp      lc_chunk                ; LC_CHUNK (sprite.asm obj_chunk's head)

                include "../m4/frmlow2.asm"
ovl_end:
                if ovl_end > OVL_WL2_END
                .error the low code (part 2) is larger than its window WL2
                endif
