; ---------------------------------------------------------------- a loose floor's picture step (M8a part 28)
; The loose-floor overlay (W1, src/m4/ovl_loose.asm). A loose floor's picture (spike.asm loose_redraw: the bottom piece
; LOOSE_FRAM_BOTTOM[loose_frame(modifier)], 43 / 73 / 74; the left piece 41 / 69 / 70 and the right one 42 / 71 / 72
; follow it) changes, in its own room (VS_KIND 0), only these records and pixels (tools/movecheck.py loosepics: every
; loose floor of levels 1-14, every pair of pictures):
;   records: in its own tile's slice every back record of the old left piece, every back and fore record of the old
;   bottom piece (a tile drawn twice has two of each), and in its right neighbour's (columns 0-8) every back record of
;   the old right piece: each gets the new image, its bottom row kept (fspatch.asm). The other records stay;
;   pixels (the shadow and the fore pieces): x 4c .. 4c + 7 (to byte column 39), rows 63r + 49 .. 63r + 65.
; So the step patches the records and lays only that rect (dr_run: one chunk, at most 8 x 17), where tile_redraw
; regenerated the two tiles and laid the rect of all their old and new ops. A record not found (never, by the check)
; or a picture outside the three: carry, and the caller regenerates as before (spike.asm sr_1: the tiles from the
; level, whatever was patched here). Records keep their places, so nothing that keeps record addresses (ops_gen) or
; the torch registry has to follow; a fore record patched where the redraw touched a torch flame drops the torch
; pictures with fore pieces in them (fore_gen, as frames.asm fs_fg).
; (Keeping the rect's pictures in RAM-disk slots, as the choppers' and spikes', was built and measured: on the 168
; loose-floor scenes of levels 1-14 it saved 0.01 frames a shake tick over this; docs/perf.md "M8a part 28".)
; Entry loose_step (stub loose_fast): B = the new picture (its bottom piece), D = the old one; VS_TAG = the tile (0..29).
LS_W            equ     8                       ; the rect: up to 8 bytes x 17 rows
LS_Y0           equ     49
LS_H            equ     17

loose_step:     ld      a, b
                call    ls_idx
                ret     c
                ld      (ls_new), a
                ld      a, d
                call    ls_idx
                ret     c
                ld      (ls_old), a
                xor     a
                ld      (fs_fore), a
                ld      hl, ls_left             ; its own tile: the left piece (back), the bottom piece (back, fore)
                call    ls_all                  ; (A = 0: the back list)
                ret     c
                ld      hl, ls_bot
                xor     a
                call    ls_all
                ret     c
                ld      hl, ls_bot
                ld      a, 2
                call    ls_all
                ret     c
                ld      a, 1
                ld      (fs_fore), a
                ld      a, (VS_TAG)             ; the row and the column
                ld      b, 0
ls_r:           cp      10
                jr      c, ls_r2
                sub     10
                inc     b
                jr      ls_r
ls_r2:          ld      c, a
                cp      9
                jr      z, ls_rect              ; (column 9: its right part is the next room's)
                push    bc
                ld      hl, ls_right            ; the right neighbour's back
                ld      a, 1
                call    ls_all
                pop     bc
                ret     c
ls_rect:        ld      a, c                    ; DR: x 4c .. min(4c + 8, 40), rows 63r + 49 .. 63r + 65
                add     a, a
                add     a, a
                ld      (DR_X0), a
                add     a, LS_W
                cp      41
                jr      c, ls_x1
                ld      a, 40
ls_x1:          ld      (DR_X1), a
                ld      a, b                    ; 63 r
                add     a, a
                add     a, a
                add     a, a
                add     a, a
                add     a, a
                add     a, a
                sub     b
                add     a, LS_Y0
                ld      (DR_Y0), a
                add     a, LS_H
                ld      (DR_Y1), a
                call    dr_run
                ld      a, (fs_fore)            ; a fore record patched where the redraw touched a torch flame
                ld      hl, flm_touch           ; (dirty_from_dr's flm_hook): the torch pictures with fore pieces in
                and     (hl)                    ; them go (tcache.asm tc_try)
                ret     z                       ; (no carry)
                ld      hl, fore_gen
                inc     (hl)
                or      a
                ret
; ls_idx: A = a bottom piece -> A = its picture 0..2; carry: none of them
ls_idx:         ld      hl, ls_bot
                ld      bc, 3
                cpir
                scf
                ret     nz
                ld      a, 2                    ; (found at k: BC = 2 - k)
                sub     c
                ret
; ls_all: HL = a piece's three ids, A = the list (0 back, 2 fore, 1 the right neighbour's back): every record of the
; old picture's id in the tile's slice gets the new one; carry: not one found
ls_all:         ld      (ls_list), a
                push    hl
                ld      a, (ls_new)
                call    ls_tab
                ld      (ls_nid), a
                pop     hl
                ld      a, (ls_old)
                call    ls_tab
                ld      (ls_oid), a
                call    ls_one
                ret     c
la_l:           call    ls_one
                jr      nc, la_l
                or      a
                ret
ls_one:         ld      a, (ls_oid)
                ld      b, a
                ld      c, a
                ld      a, (ls_nid)
                ld      e, a
                ld      a, (ls_list)
                jp      fs_patch0
ls_tab:         add     a, l
                ld      l, a
                jr      nc, lt_1
                inc     h
lt_1:           ld      a, (hl)
                ret

                include "../m4/fspatch.asm"

ls_left:        db      41, 69, 70
ls_bot:         db      43, 73, 74
ls_right:       db      42, 71, 72
ls_new:         db      0
ls_old:         db      0
ls_list:        db      0
ls_oid:         db      0
ls_nid:         db      0
