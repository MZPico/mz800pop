; Frames overlay (window W1, src/m4/ovl.asm, OVL_FRM): choppers' and spikes' picture steps from pre-drawn pictures in
; the RAM disk (M8a part 15, src/m4/frames.asm). Assembled after the main program against its symbols
; (build/ovl_frm.inc, tools/ovltool.py). Its image is in RAM-disk page OVL_FRM_PAGE (its own place, like the button
; overlay's). Nothing here may call another W1 overlay.
                include "../../build/ovl_frm.inc"
                include "../boot/launch.inc"
                org     OVL_W1
ovl_id          equ     OVL_FRM
ovl_rd_page     equ     OVL_FRM_PAGE            ; (tools/ovltool.py pack: the image's own place; tests/m4_game.py and
ovl_rd_addr     equ     OVL_FRM_RD              ; tools/mkgamedisk.py write it)
ovl_rd_last     equ     0xa7ff
ovl_entry:      jp      frm_step                ; entry 0 (stub frm_fast: spike.asm chomp_redraw, spike_redraw)

                include "../m4/frames.asm"
ovl_end:
                if ovl_end > OVL_W1_END
                .error the frames overlay is larger than its window W1
                endif
