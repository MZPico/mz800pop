; Events overlay (window W1, src/m4/ovl.asm): the potions, the scripted shadows (levels 4, 5, 6, 12), the jump
; through the mirror, died_on_button (src/m4/events.asm); trigger_button (src/m4/buttons.asm) was here until M8a part 24
; (now resident). Assembled after the main program against its symbols (build/ovl_event.inc,
; tools/ovltool.py). Shares W1 with the room overlay: stays loaded until a room draw replaces it (a shadow level
; reloads it at its first shadow tick after each room draw).
                include "../../build/ovl_event.inc"
                org     OVL_W1
ovl_id          equ     OVL_EVENT
ovl_entry:      jp      proc_get_object         ; entry 0 (stub proc_get_object)
                jp      autocontrol_shadow      ; entry 1 (stub autocontrol_shadow)
                jp      jump_through_mirror     ; entry 2 (stub jump_through_mirror)
                jp      died_on_button          ; (entry 3 unused: trigger_button is resident since M8a part 24)
                jp      died_on_button          ; entry 4 (stub died_on_button)

                include "../m4/events.asm"
                include "../m4/shadinit.asm"         ; (do_init_shad: also in the guard-enter overlay)
ovl_end:
                if ovl_end > OVL_W1_END
                .error the events overlay is larger than its window W1
                endif
