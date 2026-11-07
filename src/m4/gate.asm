; ---------------------------------------------------------------- gates: the redraw of a modifier-only change (M8a part 2, block 2)
; gate_redraw (view.asm vrd_gate): the visible bar position of a gate changed. The bars are drawn by the gate's right
; neighbour (draw_tile_anim_right -> draw_gate_back) and their top by the tile above that one (draw_tile_anim_topright, in
; draw_tile and draw_tile_above), but only when that tile can see its bottom-left (empty, big pillar top, door top:
; can_see_bl without the lattice); any other tile there draws nothing from the gate. Regenerates only those tiles (one
; or two) and lays one dirty rect. (tile_redraw would regenerate the tile's right neighbour and the tile above-right too,
; which do not draw from the gate, and a second tile_redraw for the tile above would regenerate three more and lay a
; second rect.) By VS_KIND (view.asm vs_entry):
;   0 a gate of our room at column c < 9: the bars tile is VS_TAG + 1 (our (row, c + 1)), the top tile the one above it
;     (our (row - 1, c + 1), or the above row's column c + 1 = tag 31 + c for row 0);
;   1 a gate in the left room's column 9: the bars tile is VS_TAG (our column 0), the top tile the one above it;
;   3 a gate in the below room's row 0: only its top shows, drawn by our (2, c + 1) = VS_TAG (0xff for c = 9: nothing).
gate_redraw:    call    gate_fast               ; (the gate overlay: a one-row step as a moving part)
                ret     nc
                call    dr_reset
                call    lrl_lr                  ; (room.asm: load_room_links, load_leftroom)
                ld      a, (VS_KIND)
                ld      c, a
                ld      a, (VS_TAG)
                bit     1, c
                jr      nz, gr_one              ; kind 3: the top tile only
                dec     c
                jr      z, gr_b                 ; kind 1: VS_TAG draws the bars
                inc     a                       ; kind 0: its right neighbour does
gr_b:           call    tile_regen              ; (the bars tile)
                ld      a, (TR_TAG)             ; (tile_regen's tag, kept)
                sub     10
                ld      b, a                    ; the tag of the tile above
                jr      nc, gr1
                add     a, 40                   ; row 0: the above row's column c (tag 30 + c, snapshot entry 33 + c)
                ld      b, a
                add     a, 3
gr1:            add     a, a                    ; its tile address from the snapshot's pointers (0: no room there)
                ld      l, a
                ld      h, 0
                ld      de, vs_ptrs
                add     hl, de
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a
                or      h
                jr      z, gr_do                ; (no room: regenerate it, to be safe)
                ld      a, (hl)
                and     0x1f                    ; T_EMPTY
                jr      z, gr_do
                cp      T_BIGPILLAR_T
                jr      z, gr_do
                cp      T_DOORTOP
                jr      nz, gr_run
gr_do:          ld      a, b
gr_one:         inc     a                       ; (tag 0xff: no tile on screen draws it; an empty rect lays nothing)
                jr      z, gr_run
                dec     a
                call    tile_regen
gr_run:         jp      dr_run
