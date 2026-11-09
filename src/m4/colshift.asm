; ---------------------------------------------------------------- moving parts (M8a part 14; the gate and door overlays, W1)
; A gate's bars and the level door are rigid opaque stacks: every step of their movement is the previous picture moved
; by one row (docs/perf.md "M8a part 14"). A step here moves the column's rows in the shadow instead of laying the stack
; piece by piece, lays the few pieces that do change, patches the op records in place (the op lists stay what a
; regeneration would give: later redraws, room re-entry and overlaps lay them) and puts the rect on the dirty list with
; its picture kept in SPRBUF_B (the object pass composes the people and the fore pieces over it, no restore).
; Entries: gate_step (gate.asm gate_redraw; the gate overlay, src/m4/ovl_anim.asm, CS_GATE), door_step (spike.asm
; door_redraw; the door overlay, src/m4/ovl_door.asm, CS_DOOR); carry set: not this way, the caller redraws the tile(s)
; as before. (trigger_button, once copied into both overlays, is resident since M8a part 24.)
; C, E = the new and the old modifier; VS_KIND, VS_TAG, VS_POS (view.asm vs_entry).
;
; The shared part (also for pre-drawn pictures from the RAM disk, fix A): a rect is composed in SPRBUF_B from a source
; (cs_get: the shadow, at a row offset), pieces laid over it (cs_lay: an op record), then cs_put writes it to the shadow,
; puts it on the dirty list and marks SPRBUF_B as its kept background (room.asm rr_kr / rr_kv, tcache.asm oc_kept).

; (cs_get, cs_put: src/m4/anires.asm, block 2)
; (cs_scan and its variables: src/m4/csres.asm, main)
; cs_lay: HL = an op record: lay it into the compose rect (clipped to it)
cs_lay:         ld      de, 8
                add     hl, de
                ld      (OPL_PTR), hl
                jp      rl_lay
; cs_find: DE = an id range: cs_scan of the drawing tile's (cs_bt) slice without moving (HL = the last record, Z: none)
cs_find:        ld      c, 0
                ld      a, (cs_bt)
                jp      cs_scan
; cs_rc: A = tag < 30 -> A = its column, C = 63 x its row
cs_rc:          ld      b, 0
csr1:           cp      10
                jr      c, csr2
                sub     10
                inc     b
                jr      csr1
csr2:           ld      c, a
                ld      a, b
                add     a, a
                add     a, a
                add     a, a
                add     a, a
                add     a, a
                add     a, a
                sub     b
                ld      b, a
                ld      a, c
                ld      c, b
                ret
; cs_draw: VS_KIND 0 (our room, not column 9) or 1 (the left room's column 9): A = the tag of the tile that draws the
; tile's right part (draw_tile_anim_right: the gate's bars, the level door), kept in cs_bt; carry: another kind
cs_draw:        ld      a, (VS_KIND)
                cp      2
                ccf
                ret     c
                or      a
                ld      a, (VS_TAG)
                jr      nz, csd1                ; kind 1: our column 0
                ld      a, (VS_POS)
                call    mod10
                cp      9
                scf
                ret     z                       ; column 9: drawn in the room on the right
                ld      a, (VS_TAG)
                inc     a
csd1:           ld      (cs_bt), a
                or      a
                ret
; cs_whole: the compose rect CRY = cs_t0, CRH = cs_s1 + A - cs_t0 in SPRBUF_B, its bounds set (for cs_lay)
cs_whole:       ld      hl, cs_s1
                add     a, (hl)
                ld      hl, cs_t0
                sub     (hl)
                ld      (CRH), a
                ld      a, (hl)
                ld      (CRY), a
                ld      hl, SPRBUF_B
                ld      (V_COMPOSE), hl
                jp      rect_bounds
; cs_8: HL = SPRBUF_B + 8 A (a row of the compose rect)
cs_8:           ld      l, a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      de, SPRBUF_B
                add     hl, de
                ret

                include "../m4/cschg.asm"

                if defined CS_GATE
; ---------------------------------------------------------------- a gate's step
; The bars (room.asm draw_gate_back, drawn by the gate's right neighbour, the bars tile, in its column's 3 bytes): the
; bottom piece and the slices hang from the gate's bottom, cut at its top GT = 63 row + 3 by the frame slice; above
; GT the tile above draws the top piece (68 mono black, then the frame DOOR_FRAM_TOP[p & 7], p = min(mod, 188) / 4).
; A step p -> p + k (|k| = 1, both <= 46) is the picture moved by k rows up from GT down to S1 (the bottom's last row +
; 1, or the floor's top MY - 13 while the bottom is within 13 rows of it, MY = GT + 59), with:
;   rows max(GT - 9, 0)..GT - 1: 68 and the new frame laid over the old picture (68 covers every frame);
;   k < 0 (closing): row GT from the new frame slice over the old row GT (the picture moves down: row GT would
;   come from above the gate; the slice copies 20 of its 24 pixels in the dungeon, its extent);
;   min(p) <= 12: rows MY - 13..MY - min(p) - 1 (where the floor meets the bars, down to the lower bottom) laid by
;   run_rect (dr_run): there the floor drawn before the bars shows below them.
; Exact for every gate of levels 1-14 whose bars tile is empty, a floor, a button (pressed: a floor or a stuck floor),
; a loose floor, a torch, a gate or a pillar: its base 92, laid after the bars, is kept where it covers them (cs_pil,
; M8a part 24: the dungeon's bytes 1-2 read again, the palace's head laid again and pixels 16-19 kept;
; tools/movecheck.py).
; The records: the bars' (CH_ENV 50..59) move by k rows, the frame slice gets its new id, height and top; the top
; frame its new id. Where the record count or the branch changes ((46 - min(p)) & 7 = 0: a slice more or less; min(p)
; = 11: the open / closed branch of draw_gate_back) the bars tile is regenerated instead (tile_regen).
gate_step:      ld      a, c
                call    cs_pos
                ld      (cs_pn), a
                ld      b, a                    ; B = the new position
                ld      a, e
                call    cs_pos
                ld      c, a                    ; C = the old one
                ld      a, b
                sub     c
                ld      (cs_k), a               ; k = new - old (up)
                inc     a
                and     0xfd
                scf
                ret     nz                      ; |k| > 1 (a dropping gate)
                ld      a, b
                cp      c
                jr      c, gs1
                ld      a, c
gs1:            ld      (cs_min), a
                cp      46
                ccf
                ret     c                       ; 47 involved: the bottom piece reaches above GT
                call    cs_draw
                ret     c
                add     a, a                    ; the bars tile's type: one of cs_okmap
                ld      l, a
                ld      h, 0
                ld      de, vs_ptrs
                add     hl, de
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a
                ld      a, (hl)
                and     0x1f
                ld      c, a
                and     7
                inc     a
                ld      b, a
                ld      a, c
                rrca
                rrca
                rrca
                and     3
                ld      hl, cs_okmap
                call    tab_get
gs2:            rrca
                djnz    gs2
                ccf
                ret     c
                ld      a, c
                ld      (cs_ty), a
                ld      a, (cs_bt)
                call    cs_chg
                scf
                ret     nz                      ; the bars tile changed this tick too: the old way (its own redraw
                                                ; would find its records regenerated)
                ld      a, (cs_bt)
                call    cs_rc
                add     a, a
                add     a, a
                ld      (cs_x), a               ; the bars' byte column
                ld      a, c
                add     a, 3
                ld      (cs_gt), a              ; GT = 63 row + 3
                ld      c, a
                sub     9
                jr      nc, gs3
                xor     a
gs3:            ld      (cs_t0), a              ; T0 = max(GT - 9, 0)
                ld      a, c
                add     a, 59 - 13
                ld      c, a                    ; MY - 13
                ld      a, (cs_min)
                sub     13
                ld      b, 1
                jr      c, gs4                  ; the bottom within 13 rows of the floor: S1 = MY - 13, the contact band
                dec     b
                neg
                add     a, c                    ; else S1 = MY - min
                ld      c, a
gs4:            ld      a, c
                ld      (cs_s1), a
                ld      a, b
                ld      (cs_cl), a
                ; the records
                ld      a, (cs_min)
                cp      11
                jr      z, gs_rg
                cpl
                add     a, 47                   ; 46 - min
                and     7
                jr      z, gs_rg
                ld      de, 50 * 256 + 59
                call    cs_find                 ; HL = the frame slice (the last of the bars)
                jr      z, gs_rg
                push    hl
                ld      de, 7
                add     hl, de
                ld      a, (cs_k)               ; its height still the old frame ((46 - old) & 7) + 1? (a redraw
                ld      b, a                    ; before this one in the tick may have regenerated the tile)
                ld      a, (cs_pn)
                sub     b
                cpl
                add     a, 47
                and     7
                inc     a
                cp      (hl)
                ld      c, b
                ld      a, (cs_bt)
                ld      de, 50 * 256 + 59
                call    z, cs_scan              ; then the bars move by k
                pop     hl
                push    hl
                ld      a, (cs_pn)              ; its new frame f = ((46 - p) & 7) + 1: image DOOR_FRAM_SLICE[f],
                cpl                             ; f rows from GT
                add     a, 47
                and     7
                inc     a
                ld      c, a
                ld      hl, door_fram_slice
                call    tab_get
                pop     hl
                push    hl
                inc     hl
                inc     hl
                ld      (hl), a
                inc     hl
                inc     hl
                ld      a, (cs_gt)
                ld      (hl), a
                inc     hl
                ld      (hl), 0
                inc     hl
                inc     hl
                ld      (hl), c
                pop     hl
                jr      gs_tf
gs_rg:          call    lrl_lr
                ld      a, (cs_bt)
                call    tile_regen
                ld      de, 52 * 256 + 59
                call    cs_find                 ; HL = the frame slice
gs_tf:          ld      (cs_rfr), hl
                ld      a, (cs_bt)              ; the top frame: the tile above the bars tile (row - 1, or the above
                sub     10                      ; room's row 2 = tag 30 + column), if it draws one
                jr      nc, gs6
                add     a, 40
gs6:            ld      c, 0
                ld      de, 60 * 256 + 67
                call    cs_scan
                jr      z, gs7
                ld      a, (cs_pn)
                and     7
                add     a, 60
                inc     hl
                inc     hl
                ld      (hl), a
                dec     hl
                dec     hl
gs7:            ld      (cs_rtop), hl
                ; compose: rows T0..E - 1 as they are, E..S1 - 1 from k rows lower; E = GT, closing GT + 1 (the
                ; frame slice laid over row GT copies only its extent, 20 of the 24 pixels in the dungeon: the rest
                ; must stay the old row's, what is under the bars)
                ld      a, (cs_k)
                rlca
                and     1
                ld      hl, cs_gt
                add     a, (hl)
                ld      (cs_tag), a             ; E
                ld      hl, (cs_x)              ; CRX, CRY = cs_x, cs_t0
                ld      (CRX), hl
                sub     h
                ld      h, a
                ld      l, 3
                ld      (CRW), hl               ; CRW = 3, CRH = E - T0
                push    af
                ld      hl, SPRBUF_B
                call    cs_get
                pop     af
                call    cs_8
                push    hl
                ld      a, (cs_tag)
                ld      b, a
                ld      a, (cs_k)
                add     a, b
                ld      (CRY), a
                ld      a, (cs_s1)
                sub     b
                ld      (CRH), a
                pop     hl
                call    cs_get
                xor     a
                call    cs_whole                ; rows T0..S1 - 1
                ld      hl, (cs_rtop)
                ld      a, h
                or      l
                jr      z, gs9
                push    hl
                ld      de, -8                  ; 68, the record before the frame (draw_tile_anim_topright)
                add     hl, de
                call    cs_lay
                pop     hl
                call    cs_lay
gs9:            ld      a, (cs_k)
                or      a
                ld      hl, (cs_rfr)
                call    m, cs_lay               ; closing: row GT from the frame slice
                ld      a, (cs_ty)
                cp      T_PILLAR
                call    z, cs_pil               ; a pillar's base (92, laid after the bars) over them
gs10:           ld      a, (cs_cl)              ; the contact band (M8a part 24): laid into the compose rect below
                or      a                       ; S1 (one rect, kept: no restore in the object pass), while the
                jr      z, gs11                 ; rect stays within SPRBUF_B's 64 rows (min >= 4)
                ld      a, (cs_min)
                cp      4
                jr      c, gs11
                ld      a, (cs_gt)
                add     a, 46                   ; MY - 13
                ld      (CRY), a
                call    cpp_row
                ld      (V_COMPOSE), hl
                ld      a, (cs_min)
                cpl
                add     a, 14                   ; 13 - min rows
                ld      (CRH), a
                push    af
                call    rr_layc
                pop     af
                call    cs_whole
                xor     a
                ld      (cs_cl), a
gs11:           call    cs_put
                ld      a, (cs_cl)
                or      a
                ret     z                       ; (carry clear)
                call    dr_reset                ; the contact band: rows S1 = MY - 13 to the lower bottom (MY - min - 1)
                ld      a, (cs_x)
                ld      l, a
                add     a, 3
                ld      h, a
                ld      (DR_X0), hl
                ld      a, (cs_min)
                cpl
                add     a, 14                   ; 13 - min rows
                ld      b, a
                ld      a, (cs_s1)
                ld      l, a
                add     a, b
                ld      h, a
                ld      (DR_Y0), hl
                call    dr_run
                or      a
                ret
; cs_pil (M8a part 24): the bars tile is a pillar, whose base 92 is laid after the bars over rows GT..GT + 59. The
; dungeon's covers bytes 1-2 of the column whole in rows GT..S1 - 1: there the old picture (read again). The
; palace's covers pixels 16-19 (byte 2, bits 0-3) in rows GT + 9..GT + 46, more in rows GT..GT + 8: rows GT..GT + 9
; get the bars' records (CH_ENV 50..59) and 92 laid again, rows GT + 10..S1 - 1 bits 0-3 of byte 2 from the old
; picture (tools/movecheck.py gates: exact for every pillar gate of levels 1-14).
cs_pil:         ld      a, (LEVEL_TYPE)
                or      a
                jr      nz, cpp_p
                ld      a, (cs_gt)              ; the dungeon: bytes 1-2 of rows GT..S1 - 1 from the shadow
                ld      c, a
                ld      b, a
                ld      a, (cs_s1)
                sub     c
                ld      h, a
                ld      l, 2
                ld      a, (cs_x)
                inc     a
                call    cpp_get
                jp      cpp_end
cpp_p:          ld      a, (cs_gt)              ; the palace: rows GT..GT + 9, the bars' records and 92 laid again
                ld      (CRY), a
                ld      a, 10
                ld      (CRH), a
                call    cpp_row
                ld      (V_COMPOSE), hl
                call    rect_bounds
                ld      de, 50 * 256 + 59
                call    cs_layr
                ld      de, 92 * 256 + 92
                call    cs_layr
                ld      a, (cs_gt)              ; rows GT + 10..S1 - 1: bits 0-3 of byte 2 from the old picture
                add     a, 10
                ld      c, a
                ld      b, a
                ld      a, (cs_s1)
                sub     c
                ld      (cs_kk), a
                ld      h, a
                ld      l, 1
                ld      a, (cs_x)
                add     a, 2
                push    bc
                ld      de, COMPOSE_A           ; (free while the tiles are redrawn: no chunk is pending)
                call    cpp_gt
                pop     bc
                ld      a, b
                call    cpp_row0
                inc     hl
                inc     hl
                ex      de, hl
                ld      hl, COMPOSE_A
                ld      b, 4
cpp_pl:         push    bc
                push    hl
                push    de
                ld      a, (cs_kk)
                ld      b, a
cpp_r:          ld      a, (de)
                xor     (hl)
                and     0xf0
                xor     (hl)
                ld      (de), a
                ld      a, l
                add     a, CW
                ld      l, a
                jr      nc, cpp_r1
                inc     h
cpp_r1:         ld      a, e
                add     a, CW
                ld      e, a
                jr      nc, cpp_r2
                inc     d
cpp_r2:         djnz    cpp_r
                pop     de
                pop     hl
                inc     d
                inc     d
                inc     h
                inc     h
                pop     bc
                djnz    cpp_pl
cpp_end:        ld      a, (cs_x)               ; the whole rect again (for cs_put)
                ld      (CRX), a
                ld      a, 3
                ld      (CRW), a
                xor     a
                jp      cs_whole
; cpp_get: A = CRX, L = CRW, H = CRH, C = CRY: the shadow's rect into the compose's row B on (the same bytes);
; cpp_gt: into DE instead
cpp_get:        push    hl
                push    af
                ld      a, b
                call    cpp_row0
                pop     af
                push    af
                ld      e, a
                ld      a, (cs_x)
                cpl
                inc     a
                add     a, e
                ld      e, a
                ld      d, 0
                add     hl, de                  ; (the byte: CRX - x)
                ex      de, hl
                pop     af
                pop     hl
cpp_gt:         ld      (CRX), a
                ld      (CRW), hl
                ld      a, c
                ld      (CRY), a
                ex      de, hl
                jp      cs_get
; cpp_row: HL = row CRY of the compose rect in SPRBUF_B (cpp_row0: row A)
cpp_row:        ld      a, (CRY)
cpp_row0:       ld      hl, cs_t0
                sub     (hl)
                jp      cs_8
; cs_layr: DE = an id range: lay every CH_ENV record of the bars tile's (cs_bt) back slice with an id in it, in list
; order, into the compose rect (rect_bounds set; rec_lay rejects the ones that miss it)
cs_layr:        ld      a, (cs_bt)
                ld      l, a
                ld      h, 0
                ld      (cs_lo), de
                ld      de, SL_CNT
                add     hl, de
                ld      b, (hl)
                ld      de, SL_START - SL_CNT
                add     hl, de
                ld      l, (hl)
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      de, (opl_base)
                add     hl, de
                inc     b
                jr      clr_n1
clr_l:          push    bc
                push    hl
                inc     hl
                ld      a, (hl)
                cp      CH_ENV
                jr      nz, clr_n
                inc     hl
                ld      a, (hl)
                ld      hl, cs_lo + 1
                cp      (hl)
                jr      c, clr_n
                dec     hl
                cp      (hl)
                jr      z, clr_y
                jr      nc, clr_n
clr_y:          pop     hl
                push    hl
                ld      de, 8
                add     hl, de
                ld      (OPL_PTR), hl
                call    rec_lay
clr_n:          pop     hl
                ld      de, 8
                add     hl, de
                pop     bc
clr_n1:         djnz    clr_l
                ret
cs_pos:         cp      189                     ; A = modifier -> min(A, 188) / 4
                jr      c, csp1
                ld      a, 188
csp1:           rrca
                rrca
                and     0x3f
                ret
; the bars tile's types: empty, floor, a pillar (both kinds: cs_pil), stuck (a pressed closer), closer, loose floor, opener,
; torch, gate
CS_OK0          equ     (1 << T_EMPTY) | (1 << T_FLOOR) | (1 << T_PILLAR) | (1 << T_GATE) | (1 << T_STUCK)
cs_okmap:       db      CS_OK0 | (1 << T_CLOSER_R)
                db      (1 << (T_LOOSE - 8)) | (1 << (T_OPENER - 8))
                db      (1 << (T_TORCH - 16))
                db      0

                endif

                if defined CS_DOOR
; ---------------------------------------------------------------- the level door's step
; The door (room.asm draw_leveldoor, drawn by the right neighbour of its tile at xh + 1, 6 bytes; yb = MY - 13): 99 at
; yb, 144 (the dark opening) at yb - 4, the slices (33) from the door's bottom yb - ml up every 4 rows, 34 at yb - 51
; over their top. Opening ml -> ml + 1 (ml <= 43, not in the start room, where a wipe replaces 144) moves rows
; max(yb - 50, 0)..yb - ml - 1 one row up (the old picture one row lower) and reveals row yb - ml: the old picture
; there with 99 and 144 laid over it (clipped to the row). In the dungeon the door is 42 pixels wide: of its sixth
; byte only the two left pixels move (bits 0, 1), the rest is the old picture. The records: the slices move one row
; up; when ml & 3 = 3 a slice goes, at ml = 0 144 comes (the count changes): the tile is regenerated instead. Exact for
; every level door of levels 1-14 and every opening step (tools/movecheck.py).
door_step:      ld      a, e
                inc     a
                cp      c
                scf
                ret     nz                      ; (not one up: closing, the start)
                ld      a, e
                ld      (cs_min), a             ; ml (old)
                cp      44
                ccf
                ret     c                       ; (above 43: not seen)
                ld      a, (LV_START_ROOM)
                ld      hl, SHOWN_ROOM
                cp      (hl)
                scf
                ret     z
                call    cs_draw
                ret     c
                call    cs_rc
                add     a, a
                add     a, a
                inc     a
                ld      (cs_x), a               ; the door's byte column
                ld      a, c                    ; 63 row
                or      a
                jr      z, ds1                  ; (row 0: yb - 50 = -1 -> 0)
                dec     a
ds1:            ld      (cs_t0), a              ; the rect's top row
                ld      a, c
                add     a, 49                   ; yb = 63 row + 49
                ld      hl, cs_min
                sub     (hl)
                ld      (cs_s1), a              ; R = yb - ml: the revealed row
                ; the records
                ld      a, (cs_bt)
                call    cs_chg
                scf
                ret     nz                      ; the tile changed this tick too: the old way
                ld      a, (cs_min)
                or      a
                jr      z, ds_rg                ; (0 -> 1: 144 comes)
                and     3
                cp      3
                jr      z, ds_rg
                ld      de, 33 * 256 + 33
                call    cs_find                 ; the bottom slice: still at the old place (yb - ml - 5)?
                ld      de, 4
                add     hl, de
                ld      a, (cs_s1)
                sub     5
                cp      (hl)
                ld      c, 1
                ld      a, (cs_bt)
                ld      de, 33 * 256 + 33
                call    z, cs_scan              ; then the slices one row up
                jr      ds2
ds_rg:          call    lrl_lr
                ld      a, (cs_bt)
                call    tile_regen
ds2:            ld      de, 99 * 256 + 99
                call    cs_find
                ld      (cs_rtop), hl           ; 99
                ld      de, 144 * 256 + 144
                call    cs_find
                ld      (cs_rfr), hl            ; 144
                ; compose: rows T0..R - 1 from one row lower, row R as it is
                ld      hl, (cs_x)
                inc     h
                ld      (CRX), hl               ; CRX = x, CRY = T0 + 1
                ld      a, (cs_s1)
                ld      hl, cs_t0
                sub     (hl)
                ld      (cs_tag), a             ; (the moved rows' count)
                ld      h, a
                ld      l, 6
                ld      (CRW), hl
                ld      hl, SPRBUF_B
                call    cs_get
                ld      a, (cs_s1)
                ld      (CRY), a
                ld      a, 1
                ld      (CRH), a
                ld      a, (cs_tag)
                call    cs_8
                ld      (cs_last), hl           ; (the revealed row's place)
                call    cs_get
                ld      a, (LEVEL_TYPE)
                or      a
                jr      nz, ds4
                ld      hl, (cs_x)              ; the dungeon: the sixth byte's right six pixels from the old picture
                ld      a, l
                add     a, 5
                ld      l, a
                ld      (CRX), hl               ; CRX = x + 5, CRY = T0
                ld      a, (cs_tag)
                ld      h, a
                ld      l, 1
                ld      (CRW), hl
                ld      hl, COMPOSE_A           ; (free while the tiles are redrawn: no chunk is pending)
                call    cs_get
                ld      hl, COMPOSE_A
                ld      de, SPRBUF_B + 5
                ld      b, 4
ds_p:           push    bc
                push    hl
                push    de
                ld      a, (cs_tag)
                ld      b, a
ds_r:           ld      a, (de)
                xor     (hl)
                and     3
                xor     (hl)
                ld      (de), a
                ld      a, l                    ; (both rows 8 bytes on: DE = HL + 5, from 256-aligned buffers)
                add     a, 8
                ld      l, a
                jr      nc, ds_r1
                inc     h
                inc     d
ds_r1:          add     a, 5
                ld      e, a
                djnz    ds_r
                pop     de
                pop     hl
                inc     d
                inc     d
                inc     h
                inc     h
                pop     bc
                djnz    ds_p
                ld      hl, (cs_x)
                ld      (CRX), hl
                ld      a, 6
                ld      (CRW), a
ds4:            ld      a, (cs_s1)              ; the revealed row: 99 and 144 clipped to it
                ld      (CRY), a
                ld      a, 1
                ld      (CRH), a
                ld      hl, (cs_last)
                ld      (V_COMPOSE), hl
                call    rect_bounds
                ld      hl, (cs_rtop)
                ld      a, h
                or      l
                call    nz, cs_lay
                ld      hl, (cs_rfr)
                ld      a, h
                or      l
                call    nz, cs_lay
                ld      a, 1
                call    cs_whole                ; rows T0..R
                call    cs_put
                or      a
                ret

                endif
cs_x:           db      0                       ; (cs_x, cs_t0: CRX, CRY of the rect)
cs_t0:          db      0
cs_k:           db      0
cs_pn:          db      0
cs_min:         db      0
cs_bt:          db      0
cs_gt:          db      0
cs_s1:          db      0
cs_cl:          db      0
cs_ty:          db      0
cs_rtop:        dw      0
cs_rfr:         dw      0
