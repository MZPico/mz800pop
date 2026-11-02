; Guard-enter overlay (window W1, src/m4/ovl.asm): a new room (check_the_end): its animated tiles start, the level 13
; floors fall, its guard or shadow enters (src/m4/genter.asm). Assembled after the main program against its symbols
; (build/ovl_genter.inc, tools/ovltool.py). Runs in the tick of a room change (the room draw then reloads the room
; overlay: ~0.3 frames of a ~100-frame room draw).
                include "../../build/ovl_genter.inc"
                org     OVL_W1
ovl_id          equ     OVL_GENTER
ovl_entry:      jp      room_entered            ; entry 0 (stub room_entered: check_the_end)
                jp      lrs_body                ; entry 1 (stub lrs_body: leave_room's level specials, guard.asm lr_special)

                include "../m4/genter.asm"
                include "../m4/shadinit.asm"
ovl_end:
                if ovl_end > OVL_W1_END
                .error the guard-enter overlay is larger than its window W1
                endif
