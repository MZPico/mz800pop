; The room lists' compare in low RAM (M8a part 22, src/m3/rlcmp.asm): assembled after the main program against its
; symbols (build/rllow.inc, tools/ovltool.py), at RL_LOWCODE (0x0500-0x077F: free since M8a part 19, code allowed,
; zeroed at every program start). Its image is the first RL_LOWBLK blocks of the floppy file POP800.RLS
; (tools/mkgamedisk.py); the room-list fetch (src/m4/save.asm rl_fetch_h) copies it here with every level's blob, so it
; is there whenever rl_lv says a blob is (rlists.asm rl_load calls it only then).
                include "../../build/rllow.inc"
                org     RL_LOWCODE
rl_low:
                include "../m3/rlcmp.asm"
rl_low_end:
                if rl_low_end > RL_LOWCODE + RL_LOWN
                .error the room lists' low code is larger than its place (RL_LOWN)
                endif
                if rl_cmp - rl_low
                .error rl_cmp must be the low code's first byte (rlists.asm: rl_cmp equ RL_LOWCODE)
                endif
