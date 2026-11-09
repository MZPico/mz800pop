; Full room draw: the op list of a whole room (room_ops), the slice tables from scratch (slices_build), the per-cell
; buckets (bkt_build, rr_bkt) and the 15-cell draw (run_ops, draw_room_full). Split out of room.asm: the M3 test
; programs and m4test include it next to room.asm; the M4 game runs it from the room overlay (src/m4/ovl_room.asm).
; room.asm's rr_table jumps to rr_bkt_ent while bkt_on is set (only inside run_ops): each program defines it, as
; rr_bkt here or as the overlay's jump table entry.

; build the op list for room A
room_ops:       ld      (R_ROOM), a
                ld      hl, ops_gen
                inc     (hl)
                xor     a
                ld      (OPCOUNT), a
                ld      (OPCOUNT+1), a
                ld      (OPCOUNT+2), a
                ld      (PTR_TABLE), a
                call    load_room_links
                call    load_leftroom
                ld      a, 2
ro_row:         ld      (DRAWN_ROW), a
                call    load_rowbelow
                ld      a, (DRAWN_ROW)
                call    row_ys
                xor     a
ro_col:         ld      (DRAWN_COL), a
                call    tile_tag
                call    load_curr_next
                call    draw_tile
                ld      a, (DRAWN_COL)
                inc     a
                cp      10
                jp      nz, ro_col
                ld      a, (DRAWN_ROW)
                dec     a
                jp      p, ro_row
                ; the room above: its bottom row
                ld      a, (R_ROOM)
                ld      (R_SAVED), a    ; saved room
                ld      a, (R_A)
                ld      (R_ROOM), a
                call    load_room_links
                call    load_leftroom
                ld      a, 2
                ld      (DRAWN_ROW), a
                call    load_rowbelow
                xor     a
ro_acol:        ld      (DRAWN_COL), a
                add     a, 30
                ld      (CUR_TAG), a
                call    load_curr_next
                ld      hl, -1
                ld      (DRAW_MAIN_Y), hl
                ld      hl, 2
                ld      (DRAW_BOTTOM_Y), hl
                call    draw_tile_above
                ld      a, (DRAWN_COL)
                inc     a
                cp      10
                jp      nz, ro_acol
                ld      a, (R_SAVED)
                ld      (R_ROOM), a
                call    load_room_links
                ld      a, 1
                ld      (sb_full), a
                jp      slices_build

; tile_tag: CUR_TAG = DRAWN_ROW*10 + DRAWN_COL
tile_tag:       ld      a, (DRAWN_ROW)
                ld      hl, tbl_line
                call    tab_get
                ld      hl, DRAWN_COL
                add     a, (hl)
                ld      (CUR_TAG), a
                ret

; slices_build: rebuild SL_START/SL_CNT of the three lists from the tag arrays
slices_build:   ld      hl, SL_CNT
                ld      de, SL_CNT + 1
                ld      bc, 119
                ld      (hl), 0
                ldir
                ld      a, (sb_full)            ; vertical extent of each slice (rows, clamped to 0..200): all
                or      a                       ; of them after a room build, else only TR_TAG's three
                jp      z, sb_one
                ld      hl, SL_Y0
                ld      de, SL_Y0 + 1
                ld      bc, 119
                ld      (hl), 0xff
                ldir
                ld      hl, SL_Y1
                ld      de, SL_Y1 + 1
                ld      bc, 119
                ld      (hl), 0
                ldir
                jp      sb_go
sb_one:         ld      a, (TR_TAG)
                ld      e, a
                ld      d, 0
                ld      b, 3
sb_o1:          ld      hl, SL_Y0
                add     hl, de
                ld      (hl), 0xff
                ld      hl, SL_Y1
                add     hl, de
                ld      (hl), 0
                ld      a, e
                add     a, 40
                ld      e, a
                djnz    sb_o1
sb_go:          xor     a
sb_tbl:         ld      (sb_t), a
                ld      c, a
                add     a, a
                add     a, a
                add     a, c
                add     a, a
                add     a, a
                add     a, a            ; tbl*40
                ld      (sb_off), a
                ld      a, (sb_t)
                add     a, a
                ld      hl, opt_base
                add     a, l
                ld      l, a
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a            ; HL = tags
                push    hl
                ld      a, (sb_t)
                add     a, a
                ld      hl, opl_base
                add     a, l
                ld      l, a
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a
                ld      (sb_rec), hl    ; the list's first record
                pop     hl
                ld      a, (sb_t)
                ld      de, OPCOUNT
                add     a, e
                ld      e, a
                ld      a, (de)
                or      a
                jp      z, sb_next
                ld      b, a
                ld      c, 0            ; index
sb_op:          ld      a, (hl)         ; tag
                ld      (sb_tag), a
                ld      e, a
                ld      a, (sb_off)
                add     a, e
                ld      e, a
                ld      d, 0
                push    hl
                ld      hl, SL_CNT
                add     hl, de
                ld      a, (hl)
                or      a
                jp      nz, sb_cnt
                push    hl
                ld      hl, SL_START
                add     hl, de
                ld      (hl), c
                pop     hl
sb_cnt:         inc     (hl)
                push    bc
                ld      a, (sb_full)
                or      a
                jp      nz, sb_c1
                ld      a, (TR_TAG)
                ld      hl, sb_tag
                cp      (hl)
                jp      z, sb_c1
                ld      hl, (sb_rec)            ; not this slice: only step to the next record
                ld      bc, 8
                add     hl, bc
                ld      (sb_rec), hl
                jp      sb_c2
sb_c1:          call    sb_yr                   ; the record's rows into the slice's extent (DE = slot)
sb_c2:          pop     bc
                pop     hl
                inc     hl
                inc     c
                djnz    sb_op
sb_next:        ld      a, (sb_t)
                inc     a
                cp      3
                jp      nz, sb_tbl
                ret
sb_tag:         db      0
sb_full:        db      1
; ---------------------------------------------------------------- per-cell op buckets (full draws)
; bucket (cell * 3 + list) at BKT + 41 * that: count (0xff = overflowed: scan the list instead), then up to
; 40 record indices in list order. COMPOSE_B is free while the room is drawn.
BKT             equ     COMPOSE_B
BKT_MAX         equ     40
bkt_build:      ld      hl, BKT
                ld      de, 41
                ld      b, 45
bb_clr:         ld      (hl), 0
                add     hl, de
                djnz    bb_clr
                xor     a
bb_tbl:         ld      (bb_t), a
                add     a, a
                ld      e, a
                ld      d, 0
                ld      hl, opl_base
                add     hl, de
                ld      e, (hl)
                inc     hl
                ld      d, (hl)
                ld      (bb_rec), de
                ld      a, (bb_t)
                ld      e, a
                ld      d, 0
                ld      hl, OPCOUNT
                add     hl, de
                ld      a, (hl)
                or      a
                jp      z, bb_next
                ld      (bb_n), a
                xor     a
                ld      (bb_i), a
bb_rec_l:       ld      ix, (bb_rec)
                ld      a, (ix+3)               ; columns: max(xb, 0) / 8 .. min(xb + w - 1, 39) / 8
                ld      b, a
                add     a, (ix+6)
                dec     a                       ; xb + w - 1 (signed)
                jp      m, bb_skip
                cp      40
                jp      c, bb_x1
                ld      a, 39
bb_x1:          rrca
                rrca
                rrca
                and     31
                ld      (bb_cx1), a
                ld      a, b
                bit     7, a
                jp      z, bb_x0
                xor     a
bb_x0:          cp      40
                jp      nc, bb_skip
                rrca
                rrca
                rrca
                and     31
                ld      (bb_cx0), a
                ld      l, (ix+4)               ; rows: max(ytop, 0) / 64 .. min(ytop + h - 1, 191) / 64
                ld      h, (ix+5)
                ld      e, (ix+7)
                ld      d, 0
                add     hl, de
                dec     hl                      ; last row
                bit     7, h
                jp      nz, bb_skip
                ld      a, h
                or      a
                jp      nz, bb_y1c
                ld      a, l
                cp      192
                jp      c, bb_y1
bb_y1c:         ld      a, 191
bb_y1:          rlca
                rlca
                and     3
                ld      (bb_cy1), a
                ld      l, (ix+4)
                ld      h, (ix+5)
                bit     7, h
                jp      nz, bb_y0z
                ld      a, h
                or      a
                jp      nz, bb_skip
                ld      a, l
                cp      192
                jp      nc, bb_skip
                jp      bb_y0
bb_y0z:         xor     a
bb_y0:          rlca
                rlca
                and     3
bb_cyl:         ld      (bb_cy), a              ; for each band and column: append the index
                ld      a, (bb_cx0)
bb_cx:          ld      (bb_c), a
                ld      a, (bb_cy)              ; cell = band * 5 + column; bucket = cell * 3 + list
                ld      c, a
                add     a, a
                add     a, a
                add     a, c
                ld      hl, bb_c
                add     a, (hl)
                ld      c, a
                add     a, a
                add     a, c
                ld      hl, bb_t
                add     a, (hl)
                ld      l, a
                ld      h, 0
                ld      e, l
                ld      d, h
                add     hl, hl
                add     hl, hl
                add     hl, de                  ; 5x
                add     hl, hl
                add     hl, hl
                add     hl, hl                  ; 40x
                add     hl, de                  ; 41x
                ld      de, BKT
                add     hl, de
                ld      a, (hl)
                cp      BKT_MAX
                jp      nc, bb_full
                inc     (hl)
                inc     a
                ld      e, a
                ld      d, 0
                add     hl, de
                ld      a, (bb_i)
                ld      (hl), a
                jp      bb_cn
bb_full:        ld      (hl), 0xff
bb_cn:          ld      a, (bb_c)
                ld      hl, bb_cx1
                cp      (hl)
                jp      z, bb_cyn
                inc     a
                jp      bb_cx
bb_cyn:         ld      a, (bb_cy)
                ld      hl, bb_cy1
                cp      (hl)
                jp      z, bb_skip
                inc     a
                jp      bb_cyl
bb_skip:        ld      hl, (bb_rec)
                ld      de, 8
                add     hl, de
                ld      (bb_rec), hl
                ld      hl, bb_i
                inc     (hl)
                ld      a, (bb_n)
                cp      (hl)
                jp      nz, bb_rec_l
bb_next:        ld      a, (bb_t)
                inc     a
                cp      3
                jp      nz, bb_tbl
                ret
; rr_bkt: rr_table from the cell's bucket (falls back to the scan when it overflowed)
rr_bkt:         ld      a, (CELL)
                ld      c, a
                add     a, a
                add     a, c
                ld      hl, RUN_TBL
                add     a, (hl)
                ld      l, a
                ld      h, 0
                ld      e, l
                ld      d, h
                add     hl, hl
                add     hl, hl
                add     hl, de                  ; 5x
                add     hl, hl
                add     hl, hl
                add     hl, hl                  ; 40x
                add     hl, de                  ; 41x
                ld      de, BKT
                add     hl, de
                ld      a, (hl)
                cp      0xff
                jp      z, rr_tbl
                or      a
                ret     z
                ld      b, a
                inc     hl
                ld      (bkt_p), hl
                ld      a, (RUN_TBL)
                add     a, a
                ld      e, a
                ld      d, 0
                ld      hl, opl_base
                add     hl, de
                ld      e, (hl)
                inc     hl
                ld      d, (hl)
                ld      (bkt_base), de
rb_l:           push    bc
                ld      hl, (bkt_p)
                ld      a, (hl)
                inc     hl
                ld      (bkt_p), hl
                inc     a                       ; the record's end: base + (index + 1) * 8
                ld      l, a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      de, (bkt_base)
                add     hl, de
                ld      (OPL_PTR), hl
                call    rl_lay                  ; (M8a part 26: not rec_lay. A bucket's ops touch its cell, and the
                pop     bc                      ; piece is clipped to the rect anyway; only rf_cell's lay pass
                djnz    rb_l                    ; comes here, in RR_MODE 0)
                ret
bkt_p:          dw      0
bkt_base:       dw      0
bb_t:           db      0
bb_n:           db      0
bb_i:           db      0
bb_rec:         dw      0
bb_c:           db      0
bb_cy:          db      0
bb_cx0:         db      0
bb_cx1:         db      0
bb_cy1:         db      0

; draw the whole screen from the op lists: 5 columns of 8 bytes x 3 bands of 64 rows
run_ops:        call    bkt_build               ; each cell's ops, in list order (a full draw scans no lists)
                ld      a, 1
                ld      (bkt_on), a
                xor     a
                ld      (CELL), a
                ld      (RR_C0), a
                ld      a, 9
                ld      (RR_C1), a
ro_cell:        ld      a, (CELL)
                ld      b, 0
ro_band:        cp      5
                jp      c, ro_b2
                sub     5
                inc     b
                jp      ro_band
ro_b2:          add     a, a
                add     a, a
                add     a, a
                ld      (CRX), a
                ld      a, b
                rrca
                rrca                    ; b*64 (b = 0..2)
                ld      (CRY), a
                ld      a, CW
                ld      (CRW), a
                ld      a, CH
                ld      (CRH), a
                call    rf_cell
                ld      hl, CELL
                inc     (hl)
                ld      a, (hl)
                cp      15
                jp      nz, ro_cell
                xor     a
                ld      (bkt_on), a
                ret

; rf_cell: run_rect without its cover scan (M8a part 26). No back or mid op covers a whole 8 x 64 cell (none of the
; 4,740 cells of levels 1-14, docs/perf.md "M8a part 26"), so the scan never skipped the fill here; every op laid over
; black is what run_rect does when it finds no cover, so the pixels are the same whatever the room. RR_SHONLY is 0 in a
; full draw (the compose buffer is COMPOSE_A).
rf_cell:        ld      hl, COMPOSE_A
                ld      (V_COMPOSE), hl
                call    rect_bounds
                call    rr_fill
                jp      rr_sw

; draw room A completely
draw_room_full: call    room_ops
                jp      run_ops

