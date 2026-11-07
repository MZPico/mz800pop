; M8a parts 11 and 13: the redraw of an animated tile's modifier-only change (main block; called from view.asm vrd_one,
; entry VS_IDX, C, E = the new and the old modifier, A = the tile type): spikes, choppers and the sword draw only when
; their picture changes, and then regenerate only the tiles that draw it (tile_redraw regenerates three); any other
; type goes on to vrd_tile. Which tiles draw a picture: room.asm draw_tile_anim / draw_tile_fore read the tile's own
; modifier, draw_tile_anim_right its left neighbour's (spikes, gates, loose floors, the level door, torches),
; draw_tile_anim_topright and draw_tile_topright the tile below-left's (a gate, a door top), draw_tile_right the left
; neighbour's only for an empty tile, a floor, a door top or a wall; draw_tile_above has no draw_tile_anim (checked
; against tools/popdata.py RoomRenderer for every chopper, sword and potion of levels 1-14, docs/perf.md part 13).
anim_redraw:    cp      T_SPIKE
                jr      z, spike_redraw
                cp      T_CHOMPER
                jr      z, chomp_redraw
                cp      T_SWORD
                jp      nz, vrd_tile
; the sword: its picture is image 10, or 11 (the glint) at modifier 1 (dta_sword, a mid op of its own tile); seen only
; in its own room (VS_KIND 0)
                ld      a, (VS_KIND)
                or      a
                ret     nz
                ld      a, c
                dec     a
                ld      a, e
                jr      nz, swr_1
                dec     a               ; new 1: a change unless the old is 1 too
                ret     z
                jr      own_redraw
swr_1:          dec     a               ; new not 1: a change if the old was 1
                ret     nz
                jr      own_redraw
; a chopper: its picture is n = CHOMPER_FRAM1[min(modifier & 0x7F, 6)] and the blood bit 7 (dta_chomper, dtf_chomper:
; its own tile's back and fore ops), so 10 of the 15 ticks of its cycle (modifiers 5..15 and 0 all give n = 3) draw
; nothing. VS_KIND 0 our room and 2 the above room's row 2 (its fore op): its own tile only; 1 the left room's column
; 9 and 3 the below room's row 0: nothing on screen draws from it.
chomp_redraw:   ld      a, (VS_KIND)
                rrca
                ret     c               ; (1, 3)
                ld      a, c
                call    chomp_pic
                ld      b, a
                ld      a, e
                call    chomp_pic
                cp      b
                ret     z
own_redraw:     call    own_regen
                jp      dr_run
chomp_pic:      ld      d, a            ; A = modifier -> A = n | blood bit
                and     0x7f
                cp      7
                jr      c, cpc1
                ld      a, 6
cpc1:           ld      hl, chomper_fram1
                call    tab_get
                ld      l, a
                ld      a, d
                and     0x80
                or      l
                ret
; own_regen: a fresh dirty rect and the ops of the tile VS_TAG (tr_t) regenerated
own_regen:      ld      a, (VS_TAG)
                ld      (tr_t), a
                call    dr_reset
                call    lrl_lr
                ld      a, (tr_t)
                jp      tile_regen

; spike_redraw (M8a part 11): a spike's picture depends on spike_frame(modifier) only (dta_spike and dtf_spike of its
; own tile, dtar_spike of its right neighbour), so a change within one frame (the 15 ticks it stays out, 0x8F..0x81,
; and every tick the kid stands on it) draws nothing. A frame change regenerates the tiles that draw it, not the tile
; above-right (draw_tile_anim_topright reads only a gate below-left, draw_tile_topright no spike modifier) that
; tile_redraw adds. By VS_KIND (vs_entry):
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
                call    own_regen
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
