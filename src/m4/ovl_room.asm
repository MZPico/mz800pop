; Room overlay (window W1, src/m4/ovl.asm): the full room draw (room_ops, slices_build, the per-cell buckets,
; run_ops), src/m3/roomfull.asm. Assembled after the main program against its symbols (build/ovl_room.inc,
; tools/ovltool.py). Stays loaded until another W1 overlay is called.
                include "../../build/ovl_room.inc"
                org     OVL_W1
ovl_id          equ     OVL_ROOM
ovl_entry:      jp      rf_game                 ; entry 0 (stub draw_room_full)
                jp      rr_bkt                  ; entry 1 (rr_bkt_ent: room.asm rr_table while bkt_on)
                jp      set_flip                ; entry 2 (stub set_flip: a full room draw follows)

; rf_game: the full room draw (A = room), then what follows every room draw in the game (game.asm called room_drawn and
; sprite_forget after it until M8a part 19): the characters' old rects forgotten, every cached button picture dropped
; (anires.asm bc_v), the pre-drawn pictures reset and the torch registry rebuilt (spike.asm frm_reset, which ends in
; flames_rebuild: a tail jump, nothing returns into this overlay after it)
rf_game:        push    af                      ; (no stale shadow rect of the room before: M8a part 25)
                call    frm_clr
                pop     af
                call    draw_room_full
                call    rf_forget
                xor     a
                ld      (bc_v), a
                jp      frm_reset
rf_forget:
                include "../m4/sprforget.inc"
                include "../m3/roomfull.asm"

; set_flip: A = UPSIDE (0xff: upside down): patch blit's first instruction (in a, (0xe0) / jp blit_flip) and the chunk
; scheduler's tops (oc_rec: ld a, (CRY) / call fl_top; pf_blit1: ld a, (ix+1) / call fl_untop); the caller draws the
; room again. Not flipped, the patched places are the plain code: no cost.
set_flip:       or      a
                jr      z, sf_off
                ld      a, 0xc3                 ; jp
                ld      (blit), a
                ld      hl, blit_flip
                ld      (blit + 1), hl
                ld      a, 0xcd                 ; call
                ld      (oc_ry), a
                ld      (pf_ry), a
                ld      hl, fl_top
                ld      (oc_ry + 1), hl
                ld      hl, fl_untop
                ld      (pf_ry + 1), hl
                ret
sf_off:         ld      hl, 0xe0db              ; in a, (0xe0)
                ld      (blit), hl
                ld      a, 0x3a                 ; ld a, (nn)
                ld      (blit + 2), a
                ld      (oc_ry), a
                ld      hl, CRY
                ld      (oc_ry + 1), hl
                ld      hl, 0x7edd              ; ld a, (ix+1)
                ld      (pf_ry), hl
                ld      a, 1
                ld      (pf_ry + 2), a
                ret
ovl_end:
                if ovl_end > OVL_W1_END
                .error the room overlay is larger than its window W1
                endif
