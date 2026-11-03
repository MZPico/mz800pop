; M8a part 11: the redraw of a spike's modifier-only change (main block; called from view.asm vrd_one).
; spike_redraw (M8a part 11; view.asm vrd_one, entry VS_IDX): a spike's modifier changed from E to C. Its picture
; depends on spike_frame(modifier) only (dta_spike and dtf_spike of its own tile, dtar_spike of its right neighbour),
; so a change within one frame (the 15 ticks it stays out, 0x8F..0x81, and every tick the kid stands on it) draws
; nothing. A frame change regenerates the tiles that draw it, not the tile above-right (draw_tile_anim_topright reads
; only a gate below-left, draw_tile_topright no spike modifier) that tile_redraw adds. By VS_KIND (vs_entry):
;   0 our room's column c: the tile and, for c < 9, its right neighbour;
;   1 the left room's column 9: our column 0 (VS_TAG) draws its right part;
;   2 the above room's row 2: its tile (VS_TAG) only, as tile_redraw does for the above row;
;   3 the below room's row 0: nothing on screen draws from it.
spike_redraw:   ld      a, c
                call    spike_frame
                ld      b, a
                ld      a, e
                call    spike_frame
                cp      b
                ret     z
                ld      a, (VS_KIND)
                cp      3
                ret     z
                ld      a, (VS_TAG)
                ld      (tr_t), a
                call    dr_reset
                call    lrl_lr
                ld      a, (tr_t)
                call    tile_regen
                ld      a, (VS_KIND)
                or      a
                jp      nz, dr_run
                call    tag_col
                cp      9
                jp      z, dr_run
                ld      a, (tr_t)
                inc     a
                call    tile_regen      ; right neighbour
                jp      dr_run
