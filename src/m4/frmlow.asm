; ---------------------------------------------------------------- choppers and spikes: the lazy shadow (M8a part 25)
; The low code, part 1 (window WL = low RAM 0x0500-0x06FF, src/m4/ovl_low.asm; part 2: src/m4/frmlow2.asm, window WL2 =
; 0x0E00-0x0FFF). Resident (game_start copies both in at every start), called with any overlay in W1.
; The lazy shadow. A chopper's or a spike's picture step that finds its picture in its slot (src/m4/frames.asm) no
; longer writes the shadow: the shadow's rect goes stale (FE_ST) and the slot (FE_SP, FE_SA) holds what it should hold
; (the slot's bytes are the ones dr_run wrote into the shadow when the picture was drawn). So:
;   restore_shadow (gfx.asm, rs_pre / rs_post): a compose rect wholly inside a stale rect comes from the slot alone,
;     the part of one that meets a stale rect from the slot after the shadow's read;
;   shadow_write (gfx.asm, sw_pre): a stale rect the write touches goes back into the shadow first (lc_wb), or, when the
;     write covers it, is no longer stale;
;   a step (frmlow2.asm lc_step) runs sw_pre over its rect before its own rect goes stale, so stale rects never overlap
;     (a spike's rect reaches into its right neighbour's column, a chopper's there);
;   a room draw clears them (spike.asm frm_clr, before the room overlay's draw).
; The complete pictures (lc_chunk here, the copy and the save in frmlow2.asm): a chunk that is exactly an object's rect
; with nothing else in it.

; lc_cr: the compose rect as x0, x1, y0, y1 -> lc_c
lc_cr:          ld      hl, (CRX)
                ld      de, (CRW)
                ld      a, l
                ld      (lc_c), a
                add     a, e
                ld      (lc_c + 1), a
                ld      a, h
                ld      (lc_c + 2), a
                add     a, d
                ld      (lc_c + 3), a
                ret
; cmp4: Z when the 4 bytes at HL and DE are equal (keeps C)
cmp4:           ld      b, 4
c4_l:           ld      a, (de)
                cp      (hl)
                ret     nz
                inc     hl
                inc     de
                djnz    c4_l
                ret
; lc_isect: IX = an object: its rect met with lc_c -> lc_x0, lc_x1, lc_y0, lc_y1; carry: they do not meet
lc_isect:       ld      hl, lc_c
                ld      de, lc_x0
                ld      a, (ix + FE_X0)
                call    li_max
                ld      a, (ix + FE_X1)
                call    li_min
                ld      a, (ix + FE_Y0)
                call    li_max
                ld      a, (ix + FE_Y1)
                call    li_min
                ld      a, (lc_x0)
                ld      hl, lc_x1
                cp      (hl)
                ccf
                ret     c
                ld      a, (lc_y0)
                ld      hl, lc_y1
                cp      (hl)
                ccf
                ret
li_max:         cp      (hl)
                jr      nc, li_s
                ld      a, (hl)
                jr      li_s
li_min:         cp      (hl)
                jr      c, li_s
                ld      a, (hl)
li_s:           ld      (de), a
                inc     hl
                inc     de
                ret

; rs_pre: restore_shadow's head: the compose rect wholly inside a stale rect: its rows from that object's slot, and back
; to restore_shadow's caller (no shadow read). rs_post: its tail: the parts in stale rects from their slots.
rs_pre:         xor     a
                db      0x21                    ; (ld hl, nn: skips the ld a, 1)
rs_post:        ld      a, 1
                ld      (rs_mode + 1), a
                ld      a, (FRM_TAB + FE_TAG)   ; (no object yet: the entries are taken in order)
                or      a
                ret     z
                call    lc_cr
                push    ix
                ld      ix, FRM_TAB
                ld      b, FRM_N
rs_l:           ld      a, (ix + FE_ST)
                or      a
                jr      z, rs_n
                push    bc
                call    lc_isect
                jr      c, rs_n0
                ld      hl, lc_x0
                ld      de, lc_c
                call    cmp4                    ; Z: inside
rs_mode:        ld      a, 0                    ; (patched: 0 the head, 1 the tail)
                jr      nz, rs_part
                or      a
                jr      z, rs_in
rs_part:        or      a
                call    nz, lc_rd
rs_n0:          pop     bc
rs_n:           ld      de, FE_SIZE
                add     ix, de
                djnz    rs_l
                pop     ix
                ret
rs_in:          call    lc_rd
                pop     bc
                pop     ix
                pop     hl                      ; (restore_shadow's own return: back to its caller)
                ret
; lc_rd: IX = a stale object: the meet lc_x0 .. lc_y1 from its slot (plane-major, its rect's rows) into V_COMPOSE
lc_rd:          ld      a, (ix + FE_X1)
                sub     (ix + FE_X0)
                ld      (lr_w + 1), a
                ld      c, a
                ld      a, (ix + FE_Y1)
                sub     (ix + FE_Y0)
                ld      e, a
                ld      a, c
                call    mul8                    ; HL = w h: a plane
                ld      (lr_ps + 1), hl
                ld      a, (lc_y0)
                sub     (ix + FE_Y0)
                ld      e, a
                ld      a, (lr_w + 1)
                call    mul8                    ; HL = (y0 - Y0) w
                ld      a, (lc_x0)
                sub     (ix + FE_X0)
                ld      e, a
                ld      d, 0
                add     hl, de
                ld      e, (ix + FE_SA)
                ld      d, (ix + FE_SA + 1)
                add     hl, de
                push    hl                      ; the slot's first byte
                ld      hl, lc_x0
                ld      a, (lc_x1)
                sub     (hl)
                ld      (lr_n + 1), a
                neg
                add     a, CW
                ld      (lr_cw + 1), a
                ld      a, (lc_y1)
                inc     hl
                inc     hl
                sub     (hl)
                ld      (lr_rows + 1), a
                ld      a, (lc_c + 2)
                ld      e, a
                ld      a, (hl)
                sub     e
                ld      l, a                    ; the compose's first byte: V_COMPOSE + CW (y0 - CRY) + x0 - CRX
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      a, (lc_c)
                ld      e, a
                ld      a, (lc_x0)
                sub     e
                ld      e, a
                ld      d, 0
                add     hl, de
                ld      de, (V_COMPOSE)
                add     hl, de
                pop     de
                ld      a, (ix + FE_SP)
                out     (RD_PAGE), a
                ld      a, 4
lr_p:           push    af
                push    de
                push    hl
lr_rows:        ld      a, 0                    ; (patched: the rows)
lr_r:           ld      c, RD_ADDR
                ld      b, d
                out     (c), e
                dec     c
lr_n:           ld      b, 0                    ; (patched: the bytes a row)
                inir
lr_cw:          ld      bc, 0                   ; (patched: CW - the bytes)
                add     hl, bc
lr_w:           ld      bc, 0                   ; (patched: w)
                ex      de, hl
                add     hl, bc
                ex      de, hl
                dec     a
                jr      nz, lr_r
                pop     hl
                ld      bc, COMPOSE_PLANE
                add     hl, bc
                pop     de
lr_ps:          ld      bc, 0                   ; (patched: w h)
                ex      de, hl
                add     hl, bc
                ex      de, hl
                pop     af
                dec     a
                jr      nz, lr_p
                ret

; sw_pre: shadow_write's head (and lc_step's): every stale rect the compose rect touches is stale no longer; the ones
; it does not cover go back into the shadow first (lc_wb)
sw_pre:         ld      a, (FRM_TAB + FE_TAG)
                or      a
                ret     z
                call    lc_cr
                push    ix
                ld      ix, FRM_TAB
                ld      b, FRM_N
sp_l:           ld      a, (ix + FE_ST)
                or      a
                jr      z, sp_n
                push    bc
                call    lc_isect
                jr      c, sp_n0
                ld      (ix + FE_ST), 0
                push    ix                      ; covered: the meet is the object's rect
                pop     hl
                ld      de, lc_x0
                call    cmp4
                call    nz, lc_wb
sp_n0:          pop     bc
sp_n:           ld      de, FE_SIZE
                add     ix, de
                djnz    sp_l
                pop     ix
                ret
; lc_wb: IX = an object: its slot back into the shadow's rect: read into COMPOSE_A (free while the tiles are redrawn,
; the only time the shadow is written in play: colshift.asm uses it the same way), then written by shadow_write's body;
; the compose rect, V_COMPOSE and lc_c as before
lc_wb:          ld      hl, (CRX)
                push    hl
                ld      hl, (CRW)
                push    hl
                ld      hl, (V_COMPOSE)
                push    hl
                ld      hl, COMPOSE_A
                ld      (V_COMPOSE), hl
                ld      a, (ix + FE_X0)         ; the compose rect and the meet = the object's rect
                ld      (CRX), a
                ld      (lc_x0), a
                ld      b, a
                ld      a, (ix + FE_X1)
                ld      (lc_x1), a
                sub     b
                ld      (CRW), a
                ld      a, (ix + FE_Y0)
                ld      (CRY), a
                ld      (lc_y0), a
                ld      b, a
                ld      a, (ix + FE_Y1)
                ld      (lc_y1), a
                sub     b
                ld      (CRH), a
                call    lc_cr
                call    lc_rd
                call    sw_body
                pop     hl
                ld      (V_COMPOSE), hl
                pop     hl
                ld      (CRW), hl
                pop     hl
                ld      (CRX), hl
                jp      lc_cr

