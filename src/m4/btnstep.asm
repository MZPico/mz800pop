; ---------------------------------------------------------------- a button pressed or released (M8a part 14; the button overlay, W1)
; A press changes the button's tile and its right neighbour (draw_tile_right reads the left tile): their back ops only
; (a pressed opener is drawn as a floor, a pressed closer as a stuck floor: room.asm get_tile), the same number of them,
; and pixels only in the rect x 4c..4c + 7 (to the screen's edge), rows 63r + 49..63r + 65 (checked against the
; reference for all 134 buttons of levels 1-14 seen in their own room, docs/perf.md part 14). tile_redraw regenerated
; three tiles and laid that rect piece by piece (~5 frames). Here the first four buttons of the screen (VS_BTN order)
; have a slot in the RAM disk (page BC_PAGE): the rect's picture in both states and the records that differ between
; them (own and right tile, by their place in the slice; not the flames, CH_OBJ, which torch_fast patches). A change:
;   the slot valid (anires.asm bc_v): the new state's records written into the slices, its picture read into SPRBUF_B
;   and put (cs_put): nothing regenerated, nothing laid;
;   else: the old picture saved from the shadow, the two tiles regenerated (their old back slices kept in COMPOSE_B),
;   the rect laid by dr_run (exact: the ops are current), its picture (SPRBUF_B) and the differing records saved, the
;   slot valid (if the counts stayed and at most BC_DMAX records differ).
; A slot goes when a redraw touches its rect or regenerates one of its tiles, and at a room draw (anires.asm).
; Entry btn_step (stub btn_fast, view.asm vrd_cht): B = the new tile byte; VS_IDX, VS_KIND, VS_TAG. Carry: not this
; way (another room's button: tile_redraw as before).
BC_PAGE         equ     1                       ; page 1 0xE918-0xFC5B (docs/memory.md; tests/m5_boot.py RUNTIME_SCRATCH)
BC_BASE         equ     0xe918
BC_PIC          equ     4 * 8 * 17              ; one picture: 4 planes x 17 rows of 8 bytes (the compose buffer's rows)
BC_DIFF         equ     2 * BC_PIC              ; the records: count, then count x (tag, place, unpressed, pressed)
BC_DMAX         equ     8
BC_SLOT         equ     BC_DIFF + 1 + BC_DMAX * 18
BS_SNAP         equ     COMPOSE_B               ; the old back slices (own, right: 0x200 each; free during view_redraw)
BS_LIST         equ     COMPOSE_B + 0x400       ; the record list being built / read

btn_step:       ld      a, b
                and     0x1f
                cp      T_OPENER
                jr      z, bs0
                cp      T_CLOSER_R
                scf
                ret     nz
bs0:            ld      a, (VS_KIND)
                or      a
                scf
                ret     nz                      ; (the other rooms' buttons: tile_redraw)
                ld      a, (VS_IDX)             ; the slot: the place in VS_BTN (0..3; 4: none)
                ld      c, a
                ld      hl, VS_BTN
                ld      b, 0
bs1:            ld      a, (hl)
                cp      c
                jr      z, bs2
                inc     hl
                inc     hl
                inc     b
                ld      a, b
                cp      4
                jr      c, bs1
bs2:            ld      a, b
                ld      (bs_e), a
                ld      a, (VS_TAG)             ; the rect and the tiles
                ld      (bs_t), a
                ld      b, 0
bs3:            cp      10
                jr      c, bs4
                sub     10
                inc     b
                jr      bs3
bs4:            ld      c, a                    ; column
                add     a, a
                add     a, a
                ld      (bs_r), a               ; x0 = 4 c
                add     a, 8
                cp      41
                jr      c, bs5
                ld      a, 40
bs5:            ld      (bs_r + 1), a           ; x1
                ld      a, b                    ; y0 = 63 r + 49
                add     a, a
                add     a, a
                add     a, a
                add     a, a
                add     a, a
                add     a, a
                sub     b
                add     a, 49
                ld      (bs_r + 2), a
                add     a, 17
                ld      (bs_r + 3), a           ; y1
                ld      a, c
                cp      9
                ld      a, 0xff
                jr      z, bs6
                ld      a, (bs_t)
                inc     a
bs6:            ld      (bs_t + 1), a           ; the right tile (0xff: column 9)
                ld      a, (VS_IDX)
                call    vs_press
                ld      (bs_s), a               ; the new state: 1 pressed
                call    bs_bit
                jr      z, bs_miss
                ld      hl, bc_v
                and     (hl)
                jr      z, bs_miss
                ; a valid slot: the records, then the picture
                ld      de, BC_DIFF
                call    bs_seek
                ld      hl, BS_LIST
                ld      b, 1 + BC_DMAX * 18
                inir
                ld      hl, BS_LIST
                ld      b, (hl)
                inc     hl
                inc     b
                jr      bh_n
bh_l:           push    bc
                ld      a, (hl)                 ; tag
                ld      (bs_dt), a
                inc     hl
                ld      c, (hl)                 ; place
                inc     hl
                push    hl
                call    bs_rec                  ; DE = the record
                pop     hl
                push    hl
                ld      a, (bs_s)
                or      a
                jr      z, bh1
                ld      bc, 8
                add     hl, bc                  ; (the pressed one)
bh1:            ld      (sb_rec), de
                ld      bc, 8
                ldir
                ld      a, (bs_dt)
                ld      e, a
                ld      d, 0
                call    sb_yr                   ; (its slice's extent: room.asm)
                pop     hl
                ld      de, 16
                add     hl, de
                pop     bc
bh_n:           djnz    bh_l
                ld      a, (bs_s)
                call    bs_pic
bh2:            push    bc
                ld      bc, 0x88 * 256 + RD_DATA
                inir
                ld      bc, 512 - 0x88
                add     hl, bc
                pop     bc
                djnz    bh2
                call    bs_cr
                call    cs_put                  ; (which drops the slots it touches: this one too)
                jp      bs_valid
bs_miss:        ld      a, (bs_e)               ; no valid slot
                cp      4
                jr      nc, bm1
                call    bs_cr                   ; the old picture from the shadow
                ld      hl, SPRBUF_B
                call    cs_get
                ld      a, (bs_s)
                xor     1
                call    bs_put
                ld      a, (bs_t)               ; the old back slices
                ld      de, BS_SNAP
                call    bs_copy
                ld      a, (bs_t + 1)
                ld      de, BS_SNAP + 0x200
                call    bs_copy
bm1:            call    dr_reset
                call    lrl_lr
                ld      a, (bs_t)
                call    tile_regen
                ld      a, (bs_t + 1)
                cp      0xff
                call    nz, tile_regen
                ld      hl, bs_r                ; the dirty rect: the regenerated records' rects and the button's
                ld      de, DR_X0               ; (C: they reach out of it; a change of the right tile in the same
                ld      bc, 0x0200              ; tick is told by cs_chg below)
bu_l:           ld      a, (de)                 ; x0 / y0: the smaller
                cp      (hl)
                jr      nc, bu1
                inc     c
                jr      bu2
bu1:            ld      a, (hl)
                ld      (de), a
bu2:            inc     hl
                inc     de
                ld      a, (de)                 ; x1 / y1: the larger
                cp      (hl)
                jr      c, bu3
                jr      z, bu3
                inc     c
                jr      bu4
bu3:            ld      a, (hl)
                ld      (de), a
bu4:            inc     hl
                inc     de
                djnz    bu_l
                push    bc
                call    dr_run                  ; (the button's rect alone: one chunk, its picture stays in SPRBUF_B)
                pop     bc
                ld      a, c
                or      a
                jr      z, bm3
                call    bs_cr                   ; (more than the rect, e.g. the palace's stripe records: the rect's
                ld      hl, SPRBUF_B            ; new picture from the shadow; SPRBUF_B no longer the kept chunk)
                call    cs_get
                xor     a
                ld      (rr_kv), a
bm3:
                ld      a, (bs_t + 1)           ; the right tile changed this tick too (its redraw follows and finds
                cp      0xff                    ; it regenerated): nothing kept
                jr      z, bm2
                call    cs_chg
                jr      nz, bs_end
bm2:            ld      a, (bs_e)
                cp      4
                jr      nc, bs_end
                ld      a, (bs_s)               ; the new picture
                call    bs_put
                ld      hl, BS_LIST + 1         ; the differing records
                ld      (bs_p), hl
                xor     a
                ld      (BS_LIST), a
                ld      a, (bs_t)
                ld      hl, BS_SNAP
                call    bs_diff
                jr      c, bs_end
                ld      a, (BS_LIST)            ; none of the own tile's: it was regenerated before in this tick
                or      a
                jr      z, bs_end
                ld      a, (bs_t + 1)
                ld      hl, BS_SNAP + 0x200
                call    bs_diff
                jr      c, bs_end
                ld      de, BC_DIFF
                call    bs_seek
                ld      hl, BS_LIST
                ld      b, 1 + BC_DMAX * 18
                otir
                ld      a, (bs_e)               ; the slot's rect and tiles
                ld      l, a
                add     a, a
                add     a, l
                add     a, a
                ld      e, a
                ld      d, 0
                ld      hl, bc_rect
                add     hl, de
                ex      de, hl
                ld      hl, bs_r
                ld      bc, 6
                ldir
bs_valid:       call    bs_bit
                ld      hl, bc_v
                or      (hl)
                ld      (hl), a
bs_end:         or      a
                ret

; bs_bit: A = the slot's bit in bc_v (Z: no slot)
bs_bit:         ld      a, (bs_e)
                cp      4
                ld      b, a
                ld      a, 0
                ret     nc
                inc     b
                inc     a
                jr      bsb2
bsb1:           add     a, a
bsb2:           djnz    bsb1
                or      a
                ret
; bs_seek: DE = an offset in the slot: the RAM disk set there, C = RD_DATA
bs_seek:        ld      a, (bs_e)
                ld      hl, BC_BASE
                ld      bc, BC_SLOT
                inc     a
                jr      bss2
bss1:           add     hl, bc
bss2:           dec     a
                jr      nz, bss1
                add     hl, de
                ex      de, hl
                ld      a, BC_PAGE
                call    far_seek
                ld      c, RD_DATA
                ret
; bs_pic: A = a state: the RAM disk set at its picture, HL = SPRBUF_B, B = 4 (the planes)
bs_pic:         ld      de, 0
                or      a
                jr      z, bsp1
                ld      de, BC_PIC
bsp1:           call    bs_seek
                ld      hl, SPRBUF_B
                ld      b, 4
                ret
; bs_put: A = a state: SPRBUF_B's 17 rows (4 planes x 136 bytes) into its picture
bs_put:         call    bs_pic
bsu1:           push    bc
                ld      bc, 0x88 * 256 + RD_DATA
                otir
                ld      bc, 512 - 0x88
                add     hl, bc
                pop     bc
                djnz    bsu1
                ret
; bs_cr: the compose rect = the button's rect
bs_cr:          ld      hl, bs_r                ; x0, x1, y0, y1 -> CRX, CRW, CRY, CRH
                ld      a, (hl)
                ld      (CRX), a
                inc     hl
                ld      a, (hl)
                dec     hl
                sub     (hl)
                ld      (CRW), a
                inc     hl
                inc     hl
                ld      a, (hl)
                ld      (CRY), a
                ld      a, 17
                ld      (CRH), a
                ret
; bs_rec: A = tag, C = a place in its back slice -> DE = the record's address
bs_rec:         ld      e, a
                ld      d, 0
                ld      hl, SL_START
                add     hl, de
                ld      a, (hl)
                add     a, c
                ld      l, a
                ld      h, d
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      de, (opl_base)
                add     hl, de
                ex      de, hl
                ret
; bs_copy: A = tag (0xff: none), DE = a buffer: the tag's back record count there, then its records
bs_copy:        cp      0xff
                ret     z
                push    de
                ld      e, a
                ld      d, 0
                ld      hl, SL_CNT
                add     hl, de
                ld      b, (hl)
                ld      c, 0
                call    bs_rec                  ; DE = the slice
                pop     hl
                ld      (hl), b
                inc     hl
                ex      de, hl
                ld      a, b
                or      a
                ret     z
                push    hl
                ld      l, a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      b, h
                ld      c, l
                pop     hl
                ldir
                ret
; bs_diff: A = tag (0xff: none), HL = its old slice (bs_copy's): every record that differs now (but a flame, CH_OBJ)
; appended to BS_LIST (count, at bs_p: tag, place, unpressed, pressed); carry: the count changed, or too many
bs_diff:        cp      0xff
                ret     z
                ld      (bs_dt), a
                ld      (bd_old), hl
                push    af
                ld      c, 0
                call    bs_rec
                ld      (bd_new), de
                pop     af
                ld      e, a
                ld      d, 0
                ld      hl, SL_CNT
                add     hl, de
                ld      a, (hl)
                ld      hl, (bd_old)
                cp      (hl)
                scf
                ret     nz                      ; the count changed
                inc     hl
                ld      (bd_old), hl
                ld      b, a
                ld      c, 0
                inc     b
                jr      bd_n
bd_l:           push    bc
                ld      hl, (bd_old)
                ld      de, (bd_new)
                inc     de
                ld      a, (de)
                dec     de
                cp      CH_OBJ
                jr      z, bd_s                 ; (a flame: torch_fast's own)
                ld      b, 8
bd_c:           ld      a, (de)
                cp      (hl)
                jr      nz, bd_d
                inc     hl
                inc     de
                djnz    bd_c
                jr      bd_s
bd_d:           ld      hl, BS_LIST
                ld      a, (hl)
                cp      BC_DMAX
                jr      nc, bd_x                ; too many
                inc     (hl)
                ld      de, (bs_p)
                ld      a, (bs_dt)
                ld      (de), a
                inc     de
                pop     bc
                push    bc
                ld      a, c
                ld      (de), a                 ; place
                inc     de
                ld      a, (bs_s)               ; unpressed first: the old record if it is pressed now, else the new one
                or      a
                ld      hl, (bd_old)
                jr      nz, bd_1
                ld      hl, (bd_new)
bd_1:           ld      bc, 8
                ldir
                ld      a, (bs_s)
                or      a
                ld      hl, (bd_new)
                jr      nz, bd_2
                ld      hl, (bd_old)
bd_2:           ld      bc, 8
                ldir
                ld      (bs_p), de
bd_s:           ld      hl, (bd_old)
                ld      de, 8
                add     hl, de
                ld      (bd_old), hl
                ld      hl, (bd_new)
                add     hl, de
                ld      (bd_new), hl
                pop     bc
                inc     c
bd_n:           djnz    bd_l
                or      a
                ret
bd_x:           pop     bc
                scf
                ret

bs_e:           db      0                       ; the slot (4: none)
bs_s:           db      0                       ; the new state (1 pressed)
bs_r:           ds      4                       ; x0, x1, y0, y1 (then bs_t: the 6 bytes of a bc_rect entry, copied
bs_t:           dw      0                       ; own, right tag     together at bs_valid's ldir)
bs_dt:          db      0
bs_p:           dw      0
bd_old:         dw      0
bd_new:         dw      0
                if bs_t != bs_r + 4
                .error bs_r, bs_t: the 6 bytes of a bc_rect entry
                endif
