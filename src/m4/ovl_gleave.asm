; Guard-leave overlay (window W1, src/m4/ovl.asm): the guard stays behind or follows the kid out of the room, a guard
; falls out of the room (src/m4/gleave.asm). Assembled after the main program against its symbols
; (build/ovl_gleave.inc, tools/ovltool.py). Runs in the tick the kid leaves a room with a guard (the room draw then
; reloads the room overlay) or when a guard falls below the room.
                include "../../build/ovl_gleave.inc"
                org     OVL_W1
ovl_id          equ     OVL_GLEAVE
ovl_entry:      jp      guard_leaves            ; entry 0 (stub guard_leaves: exit_room)
                jp      guard_fallout           ; entry 1 (stub guard_fallout: check_guard_fallout)

                include "../m4/gleave.asm"
ovl_end:
                if ovl_end > OVL_W1_END
                .error the guard-leave overlay is larger than its window W1
                endif
