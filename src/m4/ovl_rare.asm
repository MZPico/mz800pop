; Rare overlay (window W1, src/m4/ovl.asm): code that runs once per hit point change (the kid's and the guard's strips,
; src/m4/hpstrip.asm), per item taken (get_item, do_pickup) and per chomper death (chomped; src/m4/rare.asm). Assembled
; after the main program against its symbols (build/ovl_rare.inc, tools/ovltool.py). Shares W1 with the room, events,
; guard and keys overlays: a load costs ~0.3 frames, once per such event (the next room draw reloads the room overlay).
; Nothing here may call another W1 overlay.
                include "../../build/ovl_rare.inc"
                org     OVL_W1
ovl_id          equ     OVL_RARE
ovl_entry:      jp      hp_redraw               ; entry 0 (game.asm hp_draw: the kid's strip)
                jp      hp_strip                ; entry 1 (stub hp_strip: B = width, C = column; overlay.asm ghp_draw)
                jp      get_item                ; entry 2 (stub get_item: objects.asm check_get_item)
                jp      chomped                 ; entry 3 (stub chomped in kid2.asm)

                include "../m4/hpstrip.asm"
                include "../m4/rare.asm"
ovl_end:
                if ovl_end > OVL_W1_END
                .error the rare overlay is larger than its window W1
                endif
