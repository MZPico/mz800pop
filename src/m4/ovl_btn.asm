; Button overlay (window W1, src/m4/ovl.asm): a button's press or release from a cached picture (M8a part 14,
; src/m4/btnstep.asm). Assembled after the main program against its symbols (build/ovl_btn.inc, tools/ovltool.py). Loaded
; at a press or release (~0.2 frames; the gate overlay, which a moving gate needs, comes back at its next step).
; Nothing here may call another W1 overlay.
                include "../../build/ovl_btn.inc"
                org     OVL_W1
ovl_id          equ     OVL_BTN
ovl_rd_page     equ     OVL_BTN_PAGE            ; (tools/ovltool.py pack: the image's own place in the RAM disk, page 6
ovl_rd_addr     equ     OVL_BTN_RD              ; after the fill overlay; tests/m4_game.py and tools/mkgamedisk.py write it)
ovl_rd_last     equ     OVL_DOOR_RD - 1
ovl_entry:      jp      btn_step                ; entry 0 (stub btn_fast: view.asm vrd_cht)

                include "../m4/btnstep.asm"
                include "../m4/cschg.asm"
ovl_end:
                if ovl_end > OVL_W1_END
                .error the button overlay is larger than its window W1
                endif
