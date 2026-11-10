; Loose-floor overlay (window W1, src/m4/ovl.asm, OVL_LOOSE): a loose floor's picture step in its own room, its records
; patched in place and one small rect laid (M8a part 28, src/m4/loosestep.asm). Assembled after the main program
; against its symbols (build/ovl_loose.inc, tools/ovltool.py). Nothing here may call another W1 overlay.
                include "../../build/ovl_loose.inc"
                org     OVL_W1
ovl_id          equ     OVL_LOOSE
ovl_entry:      jp      loose_step              ; entry 0 (stub loose_fast: spike.asm loose_redraw)

                include "../m4/loosestep.asm"
ovl_end:
                if ovl_end > OVL_W1_END
                .error the loose-floor overlay is larger than its window W1
                endif
