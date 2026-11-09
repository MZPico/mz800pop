; ---------------------------------------------------------------- the kid on screen (M4)
; One character sprite through the M1 kernel: fetch the frame image (shifted/mirrored) into the sprite buffer,
; compose = restore the shadow background of old U new rect, draw the sprite, lay the fore pieces of the room
; that touch the rect, then blit after VBLN. Adapted from src/m1/m1test.asm.
SPR_A           equ     0x0b00          ; the kid's sprite descriptor (SD_SIZE bytes; overlay.asm: the other objects')

; sprite_init: src/m4/gstart.asm (the level-start overlay, once at the start)

; div_hl_7: HL = HL / 7 (unsigned)
div_hl_7:       ld      b, 16
                xor     a
                ld      c, 7
                ld      de, 0
dh7:            add     hl, hl
                rla
                cp      c
                jp      c, dh7b
                sub     c
                inc     l
dh7b:           djnz    dh7
                ret

; ---------------------------------------------------------------- objects on screen
; draw_objects: the kid and the falling floors for this tick. Every dirty rectangle (the kid's old and new
; rect together, each falling floor's old and new rect) is redrawn in compose chunks of at most CW x CH:
; shadow background, falling floors, the kid, the fore pieces of the room, blit.
MOBR_N          equ     0x0880          ; visible falling floors this tick: count, then 6 x (xb, ybottom lo, ybottom hi, 0)
MOBR            equ     0x0881
OMOBR_N         equ     0x0899          ; their rects (xb, y, w, h): this tick's, kept as next tick's old ones
OMOBR           equ     0x089a
DR_LIST_N       equ     0x08c0          ; dirty rects: count + 15 x (x0, y0, x1, y1)
DR_LIST         equ     0x08c1
DR_LIST_MAX     equ     15
MOB_DRAW_MAX    equ     6
PEND_N          equ     0x08fe          ; composed chunks waiting for the screen copy (count; list below)
PEND_MAX        equ     3
PEND_LIST       equ     0x0ad0          ; 3 x (CRX, CRY, CRW, CRH, buffer)
CLIP_TOP        equ     0x0afc          ; clip_char of a character: top row, right byte column (40 = none)
CLIP_RIGHT      equ     0x0afe

; dirty_reset: an empty dirty list (at the start of a tick: tile redraws add to it before draw_objects)
dirty_reset:    xor     a
                ld      (DR_LIST_N), a
                ld      (rr_kv), a
                ret
; dirty_from_dr: RR_HOOK target: the room renderer's rect DR_X0..DR_X1 x DR_Y0..DR_Y1 becomes dirty
dirty_from_dr:  call    flm_hook                ; (a redraw touching a torch flame: re-check the flames)
                ld      a, (DR_X0)
                ld      b, a
                ld      a, (DR_Y0)
                ld      c, a
                ld      a, (DR_X1)
                ld      d, a
                ld      a, (DR_Y1)
                ld      e, a
                jp      dr_add_xy
draw_objects:   call    people_place            ; the kid and the guard (overlay.asm): their objects, rects, order
do_kid_done:    ; ---- the falling floors
                ld      a, (OMOBR_N)            ; last tick's rects
                or      a
                jp      z, do_m0
                ld      b, a
                ld      hl, OMOBR
do_om:          push    bc
                push    hl
                call    dr_add_rect
                pop     hl
                ld      de, 4
                add     hl, de
                pop     bc
                djnz    do_om
do_m0:          call    mobs_visible            ; MOBR (draw list) and OMOBR (their rects, for next tick and now)
                ld      a, (OMOBR_N)
                or      a
                jp      z, do_m1
                ld      b, a
                ld      hl, OMOBR
do_nm:          push    bc
                push    hl
                call    dr_add_rect
                pop     hl
                ld      de, 4
                add     hl, de
                pop     bc
                djnz    do_nm
do_m1:          ; ---- redraw the dirty rects: compose into the chunk buffers, copy them timed against the beam
                xor     a
                ld      (PEND_N), a
                ld      a, (DR_LIST_N)          ; last first: the kid's and the falling floors' rects come
                or      a                       ; after the tile redraws', and their chunks should share the
                jp      z, do_end               ; first batch of buffers (they show in the same frame)
                ld      b, a
                dec     a
                add     a, a
                add     a, a
                ld      e, a
                ld      d, 0
                ld      hl, DR_LIST
                add     hl, de
do_rect:        push    bc
                push    hl
                ld      a, (hl)
                ld      (DR_X0), a
                inc     hl
                ld      a, (hl)
                ld      (DR_Y0), a
                inc     hl
                ld      a, (hl)
                ld      (DR_X1), a
                inc     hl
                ld      a, (hl)
                ld      (DR_Y1), a
                call    obj_rect_run
                pop     hl
                ld      de, -4
                add     hl, de
                pop     bc
                djnz    do_rect
do_end:         jp      pend_flush

; dr_add_rect: HL = rect (xb, y, w, h): clamp to the playfield and append (x0, y0, x1, y1)
dr_add_rect:    ld      b, (hl)                 ; x0
                inc     hl
                ld      c, (hl)                 ; y0
                inc     hl
                ld      a, (hl)
                add     a, b
                ld      d, a                    ; x1
                inc     hl
                ld      a, (hl)
                add     a, c
                jp      nc, dar1
                ld      a, 192
dar1:           ld      e, a                    ; y1
dr_add_xy:      ld      a, d                    ; clamp x1 <= 40, y1 <= 192
                cp      41
                jp      c, dar2
                ld      d, 40
dar2:           ld      a, e
                cp      193
                jp      c, dar3
                ld      e, 192
dar3:           ld      a, b
                cp      d
                ret     nc                      ; empty
                ld      a, c
                cp      e
                ret     nc
                ld      a, (DR_LIST_N)
                cp      DR_LIST_MAX
                jp      nc, dax_merge           ; full: grow the last rect instead
                ld      l, a
                inc     a
                ld      (DR_LIST_N), a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                push    de
                ld      de, DR_LIST
                add     hl, de
                pop     de
                ld      (hl), b
                inc     hl
                ld      (hl), c
                inc     hl
                ld      (hl), d
                inc     hl
                ld      (hl), e
                ret
dax_merge:      ld      hl, DR_LIST + (DR_LIST_MAX - 1) * 4
                ld      a, (hl)
                cp      b
                jp      c, dxm1
                ld      (hl), b
dxm1:           inc     hl
                ld      a, (hl)
                cp      c
                jp      c, dxm2
                ld      (hl), c
dxm2:           inc     hl
                ld      a, (hl)
                cp      d
                jp      nc, dxm3
                ld      (hl), d
dxm3:           inc     hl
                ld      a, (hl)
                cp      e
                ret     nc
                ld      (hl), e
                ret
; dr_add_union: HL, DE = two rects (xb, y, w, h): append their bounding box
dr_add_union:   push    de
                ld      de, du_r1
                ld      bc, 4
                ldir
                pop     hl
                ld      de, du_r2
                ld      bc, 4
                ldir
                ld      a, (du_r1)              ; x0 = min
                ld      b, a
                ld      a, (du_r2)
                cp      b
                jp      nc, dau1
                ld      b, a
dau1:           ld      a, (du_r1+1)            ; y0 = min
                ld      c, a
                ld      a, (du_r2+1)
                cp      c
                jp      nc, dau2
                ld      c, a
dau2:           ld      a, (du_r1)              ; x1 = max(x + w)
                ld      hl, du_r1+2
                add     a, (hl)
                ld      d, a
                ld      a, (du_r2)
                ld      hl, du_r2+2
                add     a, (hl)
                cp      d
                jp      c, dau3
                ld      d, a
dau3:           ld      a, (du_r1+1)            ; y1 = max(y + h)
                ld      hl, du_r1+3
                add     a, (hl)
                jp      nc, dau4
                ld      a, 192
dau4:           ld      e, a
                ld      a, (du_r2+1)
                ld      hl, du_r2+3
                add     a, (hl)
                jp      nc, dau5
                ld      a, 192
dau5:           cp      e
                jp      c, dau6
                ld      e, a
dau6:           jp      dr_add_xy
du_r1:          ds      4
du_r2:          ds      4

; mobs_visible: the falling floors visible in the drawn room (SDLPoP draw_mob): MOBR = (xb, ybottom 16-bit),
; OMOBR = their screen rects (xb, top, 8, height) for this tick's and next tick's dirty lists
mobs_visible:   xor     a
                ld      (MOBR_N), a
                ld      (OMOBR_N), a
                ld      a, (MOBS_N)
                or      a
                ret     z
                ld      b, a
                ld      ix, MOBS
mv_loop:        push    bc
                ld      a, (ix+2)               ; room
                ld      hl, DRAWN_ROOM
                cp      (hl)
                jp      nz, mv_b
                ld      a, (ix+1)
                cp      210
                jp      nc, mv_next
                ld      l, a
                ld      h, 0
                jp      mv_add
mv_b:           ld      c, a
                ld      a, (DRAWN_ROOM)
                push    bc
                call    links_of                ; D = above, E = below
                pop     bc
                ld      a, c
                cp      e
                jp      nz, mv_a
                ld      a, (ix+1)               ; room below: |(sbyte)y| < 18 -> y + 192
                add     a, 17
                cp      35
                jp      nc, mv_next
                ld      a, (ix+1)
                ld      l, a
                ld      h, 0
                bit     7, a
                jp      z, mv_b2
                dec     h
mv_b2:          ld      de, 192
                add     hl, de
                jp      mv_add
mv_a:           cp      d
                jp      nz, mv_next
                ld      a, (ix+1)               ; room above: y >= 174 -> y - 189
                cp      174
                jp      c, mv_next
                ld      l, a
                ld      h, 0
                ld      de, -189
                add     hl, de
mv_add:         ld      a, (MOBR_N)
                cp      MOB_DRAW_MAX
                jp      nc, mv_next
                push    hl
                ld      l, a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                ld      de, MOBR
                add     hl, de
                pop     de                      ; DE = ybottom
                ld      a, (ix+0)
                ld      (hl), a
                inc     hl
                ld      (hl), e
                inc     hl
                ld      (hl), d
                ; its rect: x = xh .. xh + 8, rows ybottom - 15 .. ybottom (pieces 70 at y-3 h13, 74 at y h3, 72 at y-1 h16)
                ld      a, (OMOBR_N)
                ld      l, a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                push    de
                ld      de, OMOBR
                add     hl, de
                pop     de
                ld      a, (ix+0)
                ld      (hl), a                 ; xb
                inc     hl
                push    hl
                ex      de, hl
                ld      de, -16
                add     hl, de                  ; top = ybottom - 16 (covers all three pieces)
                ex      de, hl
                pop     hl
                ld      b, 17
                bit     7, d                    ; clip the top at 0
                jp      z, mv_t1
                ld      a, e
                add     a, 17
                jp      m, mv_next_pop          ; entirely above
                ld      b, a
                ld      de, 0                   ; (M8a part 18: D too; a floor coming in from the room above was
                                                ; taken for one below the screen and never drawn)
mv_t1:          ld      a, d
                or      a
                jp      nz, mv_next_pop         ; below the screen
                ld      a, e
                cp      192
                jp      nc, mv_next_pop
                ld      (hl), e                 ; y
                inc     hl
                ld      (hl), 8                 ; w
                inc     hl
                ld      (hl), b                 ; h
                ld      hl, MOBR_N
                inc     (hl)
                ld      hl, OMOBR_N
                inc     (hl)
                jp      mv_next
mv_next_pop:
mv_next:        ld      de, 6
                add     ix, de
                pop     bc
                dec     b
                jp      nz, mv_loop
                ret

; obj_rect_run: redraw the rect DR_X0..DR_X1 x DR_Y0..DR_Y1 in chunks of CW x CH
obj_rect_run:   ld      a, (DR_Y0)
orr_y:          ld      hl, DR_Y1
                cp      (hl)
                ret     nc
                ld      (CRY), a
                ld      c, a
                ld      a, (hl)
                sub     c
                cp      CH
                jp      c, orr_h
                ld      a, CH
orr_h:          ld      (CRH), a
                ld      a, (DR_X0)
orr_x:          ld      hl, DR_X1
                cp      (hl)
                jp      nc, orr_ynext
                ld      (CRX), a
                ld      c, a
                ld      a, (hl)
                sub     c
                cp      CW
                jp      c, orr_w
                ld      a, CW
orr_w:          ld      (CRW), a
                call    obj_chunk
                ld      a, (CRX)
                add     a, CW
                jp      orr_x
orr_ynext:      ld      a, (CRY)
                add     a, CH
                jp      orr_y
; obj_chunk: one compose chunk (CRX, CRY, CRW, CRH): background, falling floors, kid, fore pieces, blit
obj_chunk:      call    LC_CHUNK                ; a chopper's or spike's complete picture straight into VRAM (M8a part 25)
                ret     c
                call    oc_kept                 ; the background-only redraw of this rect: its picture as base
                jp      c, oc_base
                call    tc_try                  ; a torch chunk seen before: from its cache straight into VRAM
                ret     c
                call    buf_pick                ; a free chunk buffer (flush when all are in use)
                jr      nc, oc_free
                ld      hl, (CRX)               ; (the flush uses the compose rect: keep this chunk's)
                ld      (oc_cr), hl
                ld      hl, (CRW)
                ld      (oc_cr+2), hl
                call    pend_flush
                ld      hl, (oc_cr)
                ld      (CRX), hl
                ld      hl, (oc_cr+2)
                ld      (CRW), hl
                call    buf_pick
oc_free:        ld      (V_COMPOSE), de
                ld      (oc_comp), de
                call    flames_cover            ; a chunk inside a torch flame needs no background
                call    nc, restore_shadow
oc_base:        call    flames_lay              ; the flames' current frames (the shadow may hold old ones)
                call    mob_lay                 ; the falling floors in this chunk (people2.asm)
oc_kid:         call    people_chunk            ; the people and the overlays in their drawing order
oc_fore:        call    lay_fore_rect
                ld      hl, OV_FORE
                ld      a, (OV_NF)
                ld      b, a
                call    lay_list
                call    LC_SAVE                 ; (a chopper's or spike's complete picture, a torch chunk to remember)
oc_rec:         ; record the chunk: CRX, CRY, CRW, CRH, buffer
                ld      a, (PEND_N)
                ld      l, a
                ld      h, 0
                ld      e, l
                ld      d, h
                add     hl, hl
                add     hl, de
                add     hl, hl                  ; *6
                ld      de, PEND_LIST
                add     hl, de
                ld      a, (CRX)
                ld      (hl), a
                inc     hl
oc_ry:          ld      a, (CRY)                ; (upside down: call fl_top, the screen top)
                ld      (hl), a
                inc     hl
                ld      a, (CRW)
                ld      (hl), a
                inc     hl
                ld      a, (CRH)
                ld      (hl), a
                inc     hl
                push    hl
                call    oc_kidtouch             ; bit 0 of the buffer address: the chunk shows (part of) the kid
                pop     hl
                ld      de, (oc_comp)
                or      e
                ld      (hl), a
                inc     hl
                ld      (hl), d
                ld      hl, PEND_N
                inc     (hl)
                ret
; pend_flush: copy the composed chunks to the screen, untorn and together. The copy writes a row's four planes
; together, top to bottom, at k = 1.31 + 0.28 * w lines a row (slower than the beam), so a chunk is clean when
; d, the lines until the beam next reaches its top row, is at least (k - 1) * h + k (a beam already inside the
; chunk or below it gives a large d). The chunks are copied back to back (top first) from a moment when that
; holds for each of them at its predicted start, so they all change in the same frame (a kid split over two
; chunks never shows half old). If no such moment comes within two frames, each goes on its own when clear.
BEAM_Y0         equ     113                     ; lines from the VBLN interrupt (scanline 245) to canvas row 0 (46)
BEAM_MARGIN     equ     20                      ; k (<= 4) plus the lines the scan and the call take after the beam read
BEAM_GUARD      equ     12                      ; lines of prediction error tolerated around a chunk's top
pend_flush:     ld      a, (PEND_N)
                or      a
                ret     z
                call    pf_sort
                ld      hl, (FRAMES)
                ld      (pf_f0), hl
pf_try:         call    pf_seq
                jp      nc, pf_all
                ld      hl, (FRAMES)
                ld      de, (pf_f0)
                or      a
                sbc     hl, de
                ld      a, l
                cp      2
                jp      c, pf_try
pf_next:        ld      a, (PEND_N)             ; one at a time
                or      a
                ret     z
                call    pf_beam
                ld      ix, PEND_LIST
                ld      a, (PEND_N)
                ld      b, a
                ld      c, 0
pf_scan:        call    pf_calc
                call    pf_d
                ld      de, (pf_need)
                or      a
                sbc     hl, de
                jp      nc, pf_take
                ld      de, 6
                add     ix, de
                inc     c
                djnz    pf_scan
                jp      pf_next                 ; none is clear yet: look again
pf_take:        push    ix
                call    pf_blit1
                pop     de                      ; remove it: the last entry moves into its place
                ld      hl, PEND_N
                dec     (hl)
                ld      a, (hl)
                ld      l, a
                ld      h, 0
                ld      b, h
                ld      c, l
                add     hl, hl
                add     hl, bc
                add     hl, hl
                ld      bc, PEND_LIST
                add     hl, bc
                ld      bc, 6
                ldir
                jp      pf_next
pf_all:         ld      ix, PEND_LIST           ; all clear: copy them in order
                ld      a, (PEND_N)
                ld      b, a
pa_l:           push    bc
                push    ix
                call    pf_blit1
                pop     ix
                ld      de, 6
                add     ix, de
                pop     bc
                djnz    pa_l
                xor     a
                ld      (PEND_N), a
                ret
; pf_seq: carry clear when every chunk, copied in list order from now, is clear at its start and all of them
; show in the same frame
pf_seq:         call    pf_beam
                ld      a, (PEND_N)             ; the first copy starts after this check: 4 + 5.5 lines a chunk
                ld      b, a                    ; (measured), 5 + 6 per chunk taken
                add     a, a
                ld      c, a
                add     a, a
                add     a, c
                add     a, 5
                ld      l, a
                ld      h, 0
                ld      (pf_t), hl
                ld      hl, 0x8000
                ld      (pf_e), hl
                ld      ix, PEND_LIST
ps_l:           call    pf_calc
                call    pf_d
                push    hl
                ld      de, (pf_need)
                or      a
                sbc     hl, de
                pop     hl
                ret     c
                push    hl                      ; and not just behind the beam either: a few lines of error
                ld      de, 312 - BEAM_GUARD    ; would turn "shows next frame" into "this frame, torn"
                or      a
                sbc     hl, de
                pop     hl
                ccf
                ret     c
                bit     0, (ix+4)               ; only chunks with the kid must show in the same frame
                jp      z, ps_ok
                ld      de, (pf_t)              ; the beam first shows the chunk whole at start + d: that frame
                add     hl, de                  ; is E = t + d - top; all chunks must show in the same one
                ld      e, (ix+1)
                ld      d, 0
                or      a
                sbc     hl, de
                ex      de, hl
                ld      hl, (pf_e)
                bit     7, h
                jp      z, ps_cmp
                ld      (pf_e), de              ; (the first chunk sets it)
                jp      ps_ok
ps_cmp:         or      a
                sbc     hl, de
                scf
                ret     nz
ps_ok:          ld      hl, (pf_t)
                ld      de, (pf_dur)
                add     hl, de
                ld      (pf_t), hl
                ld      de, 6
                add     ix, de
                djnz    ps_l
                or      a
                ret
; pf_beam: pf_s = the beam's line (0 = the VBLN interrupt), pf_t = 0
pf_beam:        call    beam_lines
                ld      de, 312
pf_mod:         or      a
                sbc     hl, de
                jp      nc, pf_mod
                add     hl, de
                ld      (pf_s), hl
                ld      hl, 0
                ld      (pf_t), hl
                ret
; pf_calc: chunk at IX: pf_need = h * (k - 1) + BEAM_MARGIN, pf_dur = h * k + 4 (lines). Keeps BC.
pf_calc:        push    bc
                ld      e, (ix+2)
                ld      d, 0
                ld      hl, beam_kq
                add     hl, de
                ld      a, (hl)
                ld      e, (ix+3)
                call    mul8                    ; HL = h * 16 (k - 1)
                ld      b, 4
pc_sh:          srl     h
                rr      l
                djnz    pc_sh
                push    hl
                ld      de, BEAM_MARGIN
                add     hl, de
                ld      (pf_need), hl
                pop     hl
                ld      e, (ix+3)
                ld      d, 0
                add     hl, de
                ld      de, 4
                add     hl, de
                ld      (pf_dur), hl
                pop     bc
                ret
; pf_d: HL = (BEAM_Y0 + y - pf_s - pf_t) mod 312: the lines from the chunk's start until the beam reaches its top
pf_d:           ld      l, (ix+1)
                ld      h, 0
                ld      de, BEAM_Y0
                add     hl, de
                ld      de, (pf_s)
                or      a
                sbc     hl, de
                ld      de, (pf_t)
                or      a
                sbc     hl, de
                ld      de, 312
pd_n:           bit     7, h
                ret     z
                add     hl, de
                jp      pd_n
; td_beam: wait until a direct copy of the compose rect (tcache.asm tc_direct: 4 planes x CRH rows of 2 bytes) can
; lie wholly between two passes of the beam over the rect's rows. d (pf_d) = the lines until the beam next reaches the
; rect's top row; the copy starts when d >= 2 CRH + TD_PRE (a row's 4 planes take at most 1.77 lines with the 15 wait
; states a byte the boot accepts at most: at most 1.77 CRH < 2 CRH lines for the copy) and when the beam left the
; bottom row at least TD_POST lines ago (d + CRH <= 312 - TD_POST). Keeps nothing (IX = CRX).
TD_PRE          equ     8
TD_POST         equ     6
td_beam:        call    pf_beam
                ld      ix, CRX
                call    pf_d                    ; HL = d
                ld      a, (CRH)
                ld      c, a
                add     a, a
                add     a, TD_PRE
                ld      e, a
                ld      d, 0
                or      a
                sbc     hl, de
                jr      c, td_beam
                ld      b, d
                add     hl, bc
                add     hl, bc
                add     hl, bc
                ld      de, -(313 - TD_POST - TD_PRE)
                add     hl, de
                jr      c, td_beam
                ret
; pf_blit1: copy the chunk at IX
pf_blit1:       ld      a, (ix+0)
                ld      (CRX), a
pf_ry:          ld      a, (ix+1)               ; (upside down: call fl_untop)
                ld      (CRY), a
                ld      a, (ix+2)
                ld      (CRW), a
                ld      a, (ix+3)
                ld      (CRH), a
                ld      a, (ix+4)
                and     0xfe                    ; (bit 0: the kid flag)
                ld      e, a
                ld      d, (ix+5)
                ld      (V_COMPOSE), de
                jp      blit
; pf_sort: the pending list by top row (at most 3 entries: two bubble passes)
pf_sort:        ld      c, 2
pso_p:          ld      a, (PEND_N)
                dec     a
                ret     z
                ld      b, a
                ld      ix, PEND_LIST
pso_l:          ld      a, (ix+7)
                cp      (ix+1)
                jp      nc, pso_n
                ld      e, 6                    ; swap the two entries
                push    ix
pso_x:          ld      a, (ix+0)
                ld      d, (ix+6)
                ld      (ix+6), a
                ld      (ix+0), d
                inc     ix
                dec     e
                jp      nz, pso_x
                pop     ix
pso_n:          ld      de, 6
                add     ix, de
                djnz    pso_l
                dec     c
                jp      nz, pso_p
                ret
pf_f0:          dw      0
pf_e:           dw      0
pf_t:           dw      0
pf_need:        dw      0
pf_dur:         dw      0
pf_s:           dw      0
beam_kq:        db      0, 10, 14, 19, 23, 28, 32, 37, 42  ; 16 * (k - 1) by width
oc_cr:          ds      4
pend_bufs:      dw      COMPOSE_A, COMPOSE_B, SPRBUF_B
; oc_kidtouch: A = 1 (NZ) when the compose rect meets a character's rects (this tick's or the last one's), else 0
oc_kidtouch:    ld      hl, PP_KU               ; the kid's rects (this tick's U the last one's)
                call    okt_meet
                ret     nz
                ld      hl, PP_GU               ; the guard's
okt_meet:       ld      a, (CRX)                ; HL = rect (x, y, w, h): A = 1 (NZ) when it meets CR*
                ld      b, a
                ld      a, (hl)
                ld      c, a                    ; x
                inc     hl
                inc     hl
                add     a, (hl)                 ; x + w
                cp      b
                jp      c, okt_no
                jp      z, okt_no               ; x + w <= CRX
                ld      a, (CRW)
                add     a, b
                cp      c
                jp      c, okt_no
                jp      z, okt_no               ; CRX + CRW <= x
                dec     hl
                ld      a, (CRY)
                ld      b, a
                ld      a, (hl)
                ld      c, a                    ; y
                inc     hl
                inc     hl
                add     a, (hl)                 ; y + h
                cp      b
                jp      c, okt_no
                jp      z, okt_no
                ld      a, (CRH)
                add     a, b
                cp      c
                jp      c, okt_no
                jp      z, okt_no
                ld      a, 1
                or      a
                ret
okt_no:         xor     a
                ret
oc_comp:        dw      0
; lay_mob: B = xb, DE = ybottom: the three loose floor pieces (SDLPoP draw_objtable_item, loose floor)
lay_mob:        ld      a, b
                ld      (lm_xb), a
                ld      (lm_y), de
                ld      a, 70                   ; left part: transparent, ybottom - 3
                ld      c, -3
                ld      b, 0
                ld      e, 1
                call    lm_piece
                ld      a, 74                   ; bottom: opaque, ybottom
                ld      c, 0
                ld      b, 0
                ld      e, 0
                call    lm_piece
                ld      a, 72                   ; right part: transparent, ybottom - 1, one tile right
                ld      c, -1
                ld      b, 4
                ld      e, 1
; lm_piece: A = env image, C = dy (signed), B = dx (bytes), E = mode (0 opaque, 1 transparent)
lm_piece:       ld      (lm_img), a
                ld      a, e
                ld      (lm_mode), a
                ld      a, b
                ld      (lm_dx), a
                ld      a, c
                call    k_sext                  ; HL = dy
                ld      de, (lm_y)
                add     hl, de                  ; ybottom of the piece
                push    hl
                ld      a, (lm_img)
                ld      c, a
                ld      a, CH_ENV
                call    dir_entry
                push    hl
                pop     ix
                pop     hl
                ld      e, (ix+4)               ; top = ybottom - h + 1
                ld      d, 0
                or      a
                sbc     hl, de
                inc     hl
                ex      de, hl
                ld      a, (lm_xb)
                ld      hl, lm_dx
                add     a, (hl)
                ld      b, a
                ld      a, (lm_mode)
                jp      lay_piece16
lm_xb:          db      0
lm_dx:          db      0
lm_y:           dw      0
lm_img:         db      0
lm_mode:        db      0

; sprite_forget: src/m4/sprforget.inc (M8a part 19: in the room and the level-start overlays)

; fetch the frame of the character at IY (shifted/mirrored) into its buffer, unless cached
char_fetch:     ld      a, (iy+SD_X)
                and     7
                ld      c, a
                ld      a, (cf_ch + 1)          ; key2: chtab << 4 | mirror << 3 | shift (the guard slot shows the
                add     a, a                    ; shadow's kid images too)
                add     a, (iy+SD_MIRROR)
                add     a, a
                add     a, a
                add     a, a
                or      c
                ld      c, a
                ld      a, (iy+SD_FRAME)
                cp      (iy+SD_LKEY)
                jp      nz, cfdo
                ld      a, c
                cp      (iy+SD_LKEY2)
                jp      nz, cfdo
cf_xb:          ld      a, (iy+SD_X)            ; cached: only the byte column changes
                ld      e, a
                ld      d, (iy+SD_X+1)
                srl     d
                rr      e
                srl     d
                rr      e
                srl     d
                rr      e
                ld      (iy+SD_XB), e
                ret
cfdo:           ld      (iy+SD_LKEY2), c
                ld      a, (iy+SD_FRAME)
                ld      (iy+SD_LKEY), a
fs_on:          jp      cf_fetch                ; (patched: fs_look, the frame store's lookup, src/m4/fslook.asm)
cf_fetch:       ld      c, a
cf_ch:          ld      a, CH_KID               ; (patched: the sword's chtab)
                call    dir_entry
                push    hl
                pop     ix
                ld      e, (iy+SD_X)
                ld      d, (iy+SD_X+1)
                ld      a, (iy+SD_MIRROR)
                push    iy
                pop     hl
                jp      spr_fetch

