; Door overlay (window W1, src/m4/ovl.asm, OVL_DOOR): the level door's opening step as a moving part (M8a part 14,
; src/m4/colshift.asm with CS_DOOR), and a copy of trigger_button (src/m4/buttons.asm: the kid stands on the exit's plate
; while the door opens). Its image is in RAM-disk page OVL_DOOR_PAGE (its own place, like the button overlay's: page 7's
; area is full with the cheat build). Nothing here may call another W1 overlay.
                include "../../build/ovl_door.inc"
                org     OVL_W1
ovl_id          equ     OVL_DOOR
ovl_rd_page     equ     OVL_DOOR_PAGE           ; (tools/ovltool.py pack: the image's own place; tests/m4_game.py and
ovl_rd_addr     equ     OVL_DOOR_RD             ; tools/mkgamedisk.py write it)
ovl_rd_last     equ     0xffff
CS_DOOR         equ     1
ovl_entry:      jp      door_step               ; entry 0 (stub door_fast: spike.asm door_redraw)
                jp      door_step               ; (entries 1, 2 unused)
                jp      door_step
                jp      trigger_button          ; entry 3 (stub trigger_button)

                include "../m4/colshift.asm"
                include "../m4/buttons.asm"
ovl_end:
                if ovl_end > OVL_W1_END
                .error the door overlay is larger than its window W1
                endif
