; ---------------------------------------------------------------- moving parts: the resident part (M8a part 14, block 2)
; The overlays' shared tail (src/m4/colshift.asm: gates and the level door; src/m4/btnstep.asm: buttons; later the
; pre-drawn pictures of fix A): a rect composed in SPRBUF_B goes into the shadow, onto the dirty list, and stays there as
; the object pass's kept background (room.asm rr_kr / rr_kv, tcache.asm oc_kept). And the button picture cache's
; validity: every redraw of the shadow (the room renderer's dirty rects through RR_HOOK, cs_put) drops the cached
; pictures it touches, every regeneration the ones of the tiles it regenerates, a room draw all (game.asm).

; cs_get: HL = a place in SPRBUF_B (the rect's row there): the shadow's rect CRX, CRY, CRW, CRH copied into it
cs_get:         ld      (V_COMPOSE), hl
                jp      restore_shadow
; cs_put: the rect CRX, CRY, CRW, CRH composed in SPRBUF_B: into the shadow, onto the dirty list, kept
cs_put:         ld      hl, SPRBUF_B
                ld      (V_COMPOSE), hl
                call    shadow_write
                ld      hl, (CRX)
                ld      (rr_kr), hl
                ld      de, (CRW)
                ld      (rr_kr + 2), de
                ld      a, 1
                ld      (rr_kv), a
                ld      a, l                    ; DR_X0, DR_X1, DR_Y0, DR_Y1 = CRX, + CRW, CRY, + CRH
                add     a, e
                ld      e, a
                ld      a, h
                add     a, d
                ld      d, h
                ld      h, e
                ld      (DR_X0), hl
                ld      e, d
                ld      d, a
                ld      (DR_Y0), de
; dirty_hook: RR_HOOK's target (game.asm) and cs_put's: the shadow's rect DR_* was redrawn: the cached button pictures
; it touches go, then it goes on the dirty list (sprite.asm dirty_from_dr)
dirty_hook:     ld      a, (bc_v)
                or      a
                jp      z, dirty_from_dr
                push    ix
                ld      ix, bc_rect
                ld      bc, 0x0401              ; B = the slots, C = the slot's bit in bc_v
bi_l:           ld      a, (bc_v)
                and     c
                jr      z, bi_n
                ld      a, (DR_X0)              ; touches: DR_X0 < x1, x0 < DR_X1, DR_Y0 < y1, y0 < DR_Y1
                cp      (ix + 1)
                jr      nc, bi_n
                ld      a, (DR_X1)
                cp      (ix + 0)
                jr      c, bi_n
                jr      z, bi_n
                ld      a, (DR_Y0)
                cp      (ix + 3)
                jr      nc, bi_n
                ld      a, (DR_Y1)
                cp      (ix + 2)
                jr      c, bi_n
                jr      z, bi_n
                call    bc_drop
bi_n:           ld      de, 6
                add     ix, de
                sla     c
                djnz    bi_l
                pop     ix
                jp      dirty_from_dr
; bc_drop: C = a slot's bit: its pictures are no longer valid
bc_drop:        ld      a, c
                cpl
                ld      hl, bc_v
                and     (hl)
                ld      (hl), a
                ret
; btn_rgi: room.asm tile_regen regenerates the tile TR_TAG: the slots of the buttons drawn by it go (their record
; lists name its records by place)
btn_rgi:        ld      a, (TR_TAG)
                ld      e, a
                ld      hl, bc_rect + 4
                ld      bc, 0x0401
br_l:           ld      a, (hl)
                cp      e
                inc     hl
                jr      z, br_d
                ld      a, (hl)
                cp      e
br_d:           push    hl
                call    z, bc_drop
                pop     hl
                ld      a, l
                add     a, 5
                ld      l, a
                jr      nc, br_n
                inc     h
br_n:           sla     c
                djnz    br_l
                ret
bc_v:           db      0                       ; the valid slots (bit e: slot e; game.asm clears it at a room draw)
bc_rect:        ds      4 * 6                   ; per slot: x0, x1, y0, y1 (bytes, rows; x1, y1 exclusive), own tag, right tag
