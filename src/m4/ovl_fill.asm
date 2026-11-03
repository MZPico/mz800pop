; Fill overlay (window WF = the top of W2, OVL_WF .. OVL_W2_END, src/m4/ovl.asm): the frame store's fills, on a RAM disk
; of 1 MB and more only (docs/ramdisk-tiers.md sections 11-13): fs_fill (the kid's and the sword's keys: at boot with
; ACT_FILL, the marker check at every game start) and fs_guard (the level's guard set at its start). Called only from
; the level-start overlay (src/m4/gstart.asm fs_ovl: loaded under it, at the top of the compose buffers, while nothing
; is composed). Its image lives in RAM-disk page OVL_FILL_PAGE at OVL_FILL_RD (not in page 7's overlay area: it is
; written by the boot's stream and the harness on every size; tools/ovltool.py pack puts only its table entry there).
                include "../../build/ovl_fill.inc"
                include "../boot/launch.inc"
                org     OVL_WF
ovl_id          equ     OVL_FILL
ovl_rd_page     equ     OVL_FILL_PAGE           ; (tools/ovltool.py pack: the image's own place in the RAM disk)
ovl_rd_addr     equ     OVL_FILL_RD
ovl_rd_last     equ     0xffff
ovl_entry:      jp      fs_fill                 ; entry 0: the kid's and the sword's store (ff_bw: the bar, 0 none)
                jp      fs_guard                ; entry 1: A = the level's guard set

                include "../m4/fstore.asm"
ovl_end:
                if ovl_end > OVL_W2_END
                .error the fill overlay is larger than its window
                endif
