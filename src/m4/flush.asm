; ---------------------------------------------------------------- the screen copy of the composed chunks (M4)
; pend_flush: copy the composed chunks to the screen, untorn and together. The copy writes a row's four planes
; together, top to bottom, at k = 1.31 + 0.28 * w lines a row (slower than the beam), so a chunk is clean when
; d, the lines until the beam next reaches its top row, is at least (k - 1) * h + k (a beam already inside the
; chunk or below it gives a large d). The chunks are copied back to back from a moment when that holds for each
; of them at its predicted start, and the chunks that show a character all change in the same frame (a kid split
; over two chunks never shows half old). The order of the copies is free (docs/perf.md "M8a part 3: the beam
; wait") as long as two chunks that overlap keep theirs (by top row, the earlier entry first on a tie: the order
; pf_sort gives them), so the screen after the flush is the same whatever order is taken: pf_try tries that order
; first, then the others, each against a fresh beam read. If none fits within one to two frames, each goes on its
; own when clear (sprite.asm pf_next).
; (Main block; the one-at-a-time copy and the helpers pf_blit1, pf_sort are in sprite.asm, low block.)
BEAM_Y0         equ     113                     ; lines from the VBLN interrupt (scanline 245) to canvas row 0 (46)
BEAM_MARGIN     equ     16                      ; k (<= 4) plus the error: an interrupt between the beam read and the
                                                ; copy or inside it (<= 5 lines), rounding, a few lines to spare
BEAM_GUARD      equ     8                       ; lines of prediction error tolerated around a chunk's top (the copy
                                                ; starts within -3.5 / +6 lines of PF_LAT0 + PF_LATN * n after the read)
PF_LAT0         equ     3                       ; lines from the beam read to the first copy: PF_LAT0 + PF_LATN * n
PF_LATN         equ     2                       ; (measured: 5.2, 7.0, 9.1 lines for n = 1, 2, 3)
pend_flush:     ld      a, (PEND_N)
                or      a
                ret     z
                call    pf_prep
                ld      hl, (FRAMES)
                ld      (pf_f0), hl
pf_try:         ld      hl, (pf_ord)            ; the orders: (pair mask, n pf_tab offsets) each
                ld      a, (pf_nord)
                ld      b, a
pt_o:           push    bc
                inc     hl
                push    hl
                call    pf_seq
                pop     hl
                jp      nc, pf_go
                ld      a, (PEND_N)
                add     a, l
                ld      l, a
                jp      nc, pt_n
                inc     h
pt_n:           pop     bc
                djnz    pt_o
                ld      hl, (FRAMES)            ; none fits now: again, for one to two frames
                ld      de, (pf_f0)
                or      a
                sbc     hl, de
                ld      a, l
                cp      2
                jp      c, pf_try
pf_fall:        call    pf_sort                 ; none came: one at a time, as it always was
                jp      pf_next
pf_go:          pop     bc                      ; copy them in this order (HL: the offsets)
                ld      a, (PEND_N)
                ld      b, a
pg_l:           push    bc
                ld      e, (hl)
                inc     hl
                push    hl
                ld      d, 0
                ld      hl, pf_tab + 5
                add     hl, de
                ld      e, (hl)                 ; its PEND_LIST entry
                ld      ix, PEND_LIST
                add     ix, de
                call    pf_blit1
                pop     hl
                pop     bc
                djnz    pg_l
                xor     a
                ld      (PEND_N), a
                ret
; pf_seq: HL = an order (n pf_tab offsets): carry clear when every chunk, copied in that order
; from now, is clear at its start and the chunks with a character all show in the same frame
pf_seq:         push    hl
                call    beam_lines
                ld      de, 312
psq_m:          or      a
                sbc     hl, de
                jp      nc, psq_m
                add     hl, de                  ; s = the beam's line (0 = the VBLN interrupt)
                ld      de, (pf_t0)
                add     hl, de
                ld      (pf_st), hl             ; s + t: the next copy's start (lines from the VBLN)
                ld      a, 0xff
                ld      (pf_e), a
                pop     hl
                ld      a, (PEND_N)
                ld      b, a
ps_l:           ld      e, (hl)
                inc     hl
                push    hl
                ld      d, 0
                ld      ix, pf_tab
                add     ix, de
                ld      l, (ix+0)
                ld      h, (ix+1)               ; Y = the line of its top row
                ld      de, (pf_st)
                or      a
                sbc     hl, de
                ld      de, 312
                ld      c, 0
ps_m:           bit     7, h                    ; d = (Y - s - t) mod 312, C = the 312s added
                jp      z, ps_d
                add     hl, de
                inc     c
                jp      ps_m
ps_d:           ld      a, h                    ; d >= need
                or      a
                jp      nz, ps_g
                ld      a, l
                cp      (ix+2)
                jp      c, ps_no
ps_g:           ld      de, BEAM_GUARD - 312    ; and not just behind the beam either: a few lines of error
                add     hl, de                  ; would turn "shows next frame" into "this frame, torn"
                jp      c, ps_no
                bit     0, (ix+4)               ; only chunks with a character must show in the same frame: the
                jp      z, ps_ok                ; beam first shows the chunk whole at start + d = Y + 312 C - s,
                ld      a, (pf_e)               ; so all of them need the same C
                inc     a
                jp      z, ps_e1
                dec     a
                cp      c
                jp      nz, ps_no
ps_e1:          ld      a, c
                ld      (pf_e), a
ps_ok:          ld      hl, (pf_st)
                ld      e, (ix+3)               ; + its copy's duration
                ld      d, 0
                add     hl, de
                ld      (pf_st), hl
                pop     hl
                djnz    ps_l
                or      a
                ret
ps_no:          pop     hl
                scf
                ret
; pf_prep: pf_idx = the PEND_LIST offsets in the order pf_sort would give; pf_tab = per chunk in that order: the line
; of its top row (2 bytes), need = h (k - 1) + BEAM_MARGIN, the copy's duration h k + 4, the character flag (bit 0),
; its PEND_LIST offset; pf_ovl = the pairs of them that overlap (bit 0: 0-1, 1: 0-2, 2: 1-2); pf_ord / pf_nord = the
; orders that keep those pairs in order; pf_t0 = the lines from a beam read to the first copy
pf_prep:        ld      hl, pf_idx
                ld      (hl), 0
                inc     hl
                ld      (hl), 6
                inc     hl
                ld      (hl), 12
                ld      a, (PEND_N)
                cp      2
                jp      c, pp_tab
                ld      hl, pf_idx              ; (0, 1), (1, 2), (0, 1): pf_sort's two bubble passes
                call    pp_cmp
                ld      a, (PEND_N)
                cp      3
                jp      c, pp_tab
                call    pp_cmp
                ld      hl, pf_idx
                call    pp_cmp
pp_tab:         ld      hl, pf_idx
                ld      de, pf_tab
                ld      a, (PEND_N)
                ld      b, a
pp_l:           ld      c, (hl)
                inc     hl
                push    hl
                push    bc
                push    de
                ld      b, 0
                ld      ix, PEND_LIST
                add     ix, bc
                ld      e, (ix+2)
                ld      d, b
                ld      hl, beam_kq
                add     hl, de
                ld      a, (hl)
                ld      e, (ix+3)
                call    mul8                    ; HL = 16 h (k - 1) (< 4096; keeps C)
                add     hl, hl
                add     hl, hl
                add     hl, hl
                add     hl, hl                  ; H = h (k - 1)
                pop     de
                ld      a, (ix+1)
                add     a, BEAM_Y0
                ld      (de), a
                inc     de
                ld      a, 0
                adc     a, 0
                ld      (de), a
                inc     de
                ld      a, h
                add     a, BEAM_MARGIN
                ld      (de), a
                inc     de
                ld      a, h
                add     a, (ix+3)
                add     a, 4
                ld      (de), a
                inc     de
                ld      a, (ix+4)
                ld      (de), a
                inc     de
                ld      a, c
                ld      (de), a
                inc     de
                pop     bc
                pop     hl
                djnz    pp_l
                ld      e, 0
                ld      a, (PEND_N)
                cp      2
                jp      c, pp_1
                cp      3
                jp      c, pp_01
                ld      bc, (pf_idx + 1)
                call    pp_meet                 ; (1, 2)
                ld      a, (pf_idx)
                ld      c, a
                ld      a, (pf_idx + 2)
                ld      b, a
                call    pp_meet                 ; (0, 2)
pp_01:          ld      bc, (pf_idx)
                call    pp_meet                 ; (0, 1)
pp_1:           ld      a, e
                ld      (pf_ovl), a
                ld      a, (PEND_N)
                ld      hl, pf_ords1
                ld      b, 1
                dec     a
                jp      z, pp_o
                ld      hl, pf_ords2
                ld      b, 2
                dec     a
                jp      z, pp_o
                ld      hl, pf_ords3
                ld      b, 6
pp_o:           ld      a, (pf_ovl)
                or      a
                jp      nz, pp_cp
                ld      (pf_ord), hl            ; nothing overlaps: every order, from the table
                ld      a, b
                jp      pp_on
pp_cp:          ld      de, pf_olist            ; else the ones that keep the overlapping pairs in order
                ld      (pf_ord), de
                ld      c, 0
ppo_l:          push    bc
                ld      a, (PEND_N)
                inc     a
                ld      c, a
                ld      b, 0
                ld      a, (pf_ovl)
                and     (hl)
                jp      nz, ppo_skip
                ldir
                pop     bc
                inc     c
                jp      ppo_n
ppo_skip:       add     hl, bc
                pop     bc
ppo_n:          djnz    ppo_l
                ld      a, c
pp_on:          ld      (pf_nord), a
                ld      a, (PEND_N)
                ld      b, a
                ld      a, PF_LAT0
pp_t:           add     a, PF_LATN
                djnz    pp_t
                ld      l, a
                ld      h, 0
                ld      (pf_t0), hl
                ret
; pp_cmp: HL = pf_idx + i: entries idx[i], idx[i + 1] by top row (swapped only when the second is higher: stable);
; HL = pf_idx + i + 1
pp_cmp:         ld      e, (hl)
                inc     hl
                ld      d, (hl)
                push    hl
                ld      bc, PEND_LIST + 1
                ld      l, e
                ld      h, 0
                add     hl, bc
                ld      a, (hl)
                ld      l, d
                ld      h, 0
                add     hl, bc
                cp      (hl)
                pop     hl
                ret     c
                ret     z
                ld      (hl), e
                dec     hl
                ld      (hl), d
                inc     hl
                ret
; pp_meet: C, B = two PEND_LIST offsets: E = 2 E + 1 when their rects overlap, else 2 E
pp_meet:        push    de
                ld      ix, PEND_LIST
                ld      e, c
                ld      d, 0
                add     ix, de
                ld      hl, PEND_LIST
                ld      e, b
                add     hl, de
                call    pf_meet
                pop     de
                rl      e
                ret
; pf_meet: IX, HL = two pending entries (x, y, w, h): carry when their rects overlap (keeps DE)
pf_meet:        call    pm_1
                ret     nc
                inc     ix
                inc     hl
                call    pm_1
                dec     ix
                dec     hl
                ret
pm_1:           ld      a, (hl)                 ; carry when [a, a + aw) at (IX+0), (IX+2) meets [b, b + bw) at
                inc     hl                      ; (HL), (HL+2)
                inc     hl
                add     a, (hl)
                dec     hl
                dec     hl
                ld      c, a
                ld      a, (ix+0)
                cp      c
                ret     nc
                add     a, (ix+2)
                ld      c, a
                ld      a, (hl)
                cp      c
                ret
; the orders: the pairs of chunks they swap (pf_ovl's bits), then the chunks' pf_tab offsets; the sorted order first
pf_ords1:       db      0, 0
pf_ords2:       db      0, 0, 6,  1, 6, 0
pf_ords3:       db      0, 0, 6, 12,  4, 0, 12, 6,  1, 6, 0, 12,  3, 6, 12, 0,  6, 12, 0, 6,  7, 12, 6, 0
                if PEND_MAX > 3
                .error pf_ords: PEND_MAX > 3
                endif
; pf_e and pf_st (= pf_t) are in sprite.asm: pend_flush's raster scratch pf_f0..pf_s stays one block of 12 bytes
; (tests/m5_boot.py leaves it out of its RAM comparison)
pf_st           equ     pf_t
pf_t0:          dw      0
pf_ord:         dw      0
pf_nord:        db      0
pf_ovl:         db      0
pf_idx:         ds      PEND_MAX
pf_tab:         ds      6 * PEND_MAX
pf_olist:       ds      24              ; (the orders kept when two chunks overlap)
