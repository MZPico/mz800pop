; Animation overlay (window W1, src/m4/ovl.asm): the steps of animated tiles drawn as their moving part (M8a part 14,
; src/m4/colshift.asm): a gate's bars and the level door moved by one row, a button's picture. Assembled after the main
; program against its symbols (build/ovl_anim.inc, tools/ovltool.py). Shares W1 with the room, events, guard, keys and
; rare overlays: while a gate or the door moves nothing else loads W1, so a step costs no load; after a room draw, a
; button press (the events overlay) or a key the first step loads it again (~0.1 frames).
; Nothing here may call another W1 overlay.
                include "../../build/ovl_anim.inc"
                org     OVL_W1
ovl_id          equ     OVL_ANIM
ovl_entry:      jp      gate_step               ; entry 0 (stub gate_fast: gate.asm gate_redraw)
                jp      door_step               ; entry 1 (stub door_fast: spike.asm door_redraw)

                include "../m4/colshift.asm"
ovl_end:
                if ovl_end > OVL_W1_END
                .error the animation overlay is larger than its window W1
                endif
