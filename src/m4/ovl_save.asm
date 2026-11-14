; Save overlay (window W2, src/m4/ovl.asm): Ctrl+G saves the game to the disk file POP800.SAV, load_saved reads it back
; (src/m4/save.asm, the WD2793 code src/boot/fdc.asm). Assembled after the main program against its symbols
; (build/ovl_save.inc, tools/ovltool.py). Called at a tick start after pend_flush: nothing composed waits in W2.
                include "../../build/ovl_save.inc"
                org     OVL_W2
ovl_id          equ     OVL_SAVE
ovl_entry:      jr      sv_mute_s               ; entry 0 (stub save_key)
                nop
                jr      sv_mute_l               ; entry 1 (stub load_saved)
                nop
; the floppy code runs with interrupts off: the sound stops first (psg.asm snd_halt: no hanging tone)
sv_mute_s:      call    snd_halt
                jp      save_game
sv_mute_l:      call    snd_halt
                jp      load_saved

SV_PRES         equ     0               ; (save.asm sv_off: the motor off after the save)
                include "../m4/save.asm"
ovl_end:
                if ovl_end > SV_SEC
                .error the save overlay runs into its sector buffer
                endif
