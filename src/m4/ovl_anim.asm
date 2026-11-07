; Gate overlay (window W1, src/m4/ovl.asm, OVL_ANIM): a gate's one-row step as a moving part (M8a part 14,
; src/m4/colshift.asm with CS_GATE), and a copy of trigger_button (src/m4/buttons.asm): the kid on a plate calls it every
; tick, and with it here a gate moving at the same time needs no other overlay (ovl.asm's trigger_button stub calls the
; copy in W1 when this, the door or the events overlay is there). Assembled after the main program against its symbols
; (build/ovl_anim.inc, tools/ovltool.py). Shares W1 with the room, events, guard, keys, rare, button and door overlays:
; while a gate moves nothing else loads W1 (a button press: the button overlay, then this again, ~0.1 + 0.3 frames).
; Nothing here may call another W1 overlay.
                include "../../build/ovl_anim.inc"
                org     OVL_W1
ovl_id          equ     OVL_ANIM
CS_GATE         equ     1
ovl_entry:      jp      gate_step               ; entry 0 (stub gate_fast: gate.asm gate_redraw)
                jp      gate_step               ; (entries 1, 2 unused: trigger_button is entry 3 in every overlay
                jp      gate_step               ; that has it, as in the events overlay)
                jp      trigger_button          ; entry 3 (stub trigger_button)

                include "../m4/colshift.asm"
                include "../m4/buttons.asm"
ovl_end:
                if ovl_end > OVL_W1_END
                .error the gate overlay is larger than its window W1
                endif
