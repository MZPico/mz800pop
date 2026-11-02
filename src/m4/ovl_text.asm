; Text overlay (window W2, src/m4/ovl.asm): the bottom text line (src/m4/text.asm), drawn when a text is set or erased
; and while the death text blinks (game.asm text_chk, after the tick's drawing: the compose buffers are free). Assembled
; after the main program against its symbols (build/ovl_text.inc, tools/ovltool.py). In W2 it leaves the room and
; events overlays in W1 alone; it composes in SPRBUF_B.
                include "../../build/ovl_text.inc"
                org     OVL_W2
ovl_id          equ     OVL_TEXT
ovl_entry:      jp      text_draw               ; entry 0 (stub text_draw)

                include "../m4/text.asm"
ovl_end:
                if ovl_end > OVL_W2_END
                .error the text overlay is larger than its window W2
                endif
