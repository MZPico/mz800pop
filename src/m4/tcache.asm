; M4: torch chunks from a cache. A chunk that is exactly a registered flame's rect, with no kid, falling floor
; or overlay in it, is the flame frame plus the room's fore pieces: its picture depends on the frame only. The
; pictures are kept in RAM-disk page TC_PAGE (one 144-byte slot per registered flame and frame: 0x0000-0x143F for
; FLM_MAX 4) and reused until the flame registry or a fore op in a flame's rect changes. Since M8a part 17 a cached
; picture goes from the RAM disk straight into VRAM (tc_direct: no compose buffer, no pending chunk).
TC_PAGE         equ     6
TC_VALID        equ     0x0100                  ; FLM_MAX * 9 flags (low RAM, runtime only), then view.asm flm_rec
                if TC_VALID + FLM_MAX * 9 > flm_rec
                .error tcache.asm: TC_VALID runs into flm_rec
                endif
tc_try:         xor     a
                ld      (tc_slot), a
                ld      a, (flm_gen)            ; registry or fore ops changed: forget everything
                ld      hl, tc_gen
                cp      (hl)
                jp      nz, tc_flush
                ld      a, (fore_gen)
                inc     hl
                cp      (hl)
                jp      nz, tc_flush
tc_t1:          ld      a, (OV_NM)              ; nothing else in the chunk
                ld      hl, OV_NF
                or      (hl)
                ld      hl, MOBR_N
                or      (hl)
                ret     nz
                call    oc_kidtouch
                or      a
                ret     nz
                ld      a, (flm_n)              ; the flame whose rect this is
                or      a
                ret     z
                ld      b, a
                ld      c, 0
                ld      hl, flm_rec
tc_f:           push    hl
                ld      e, (hl)
                inc     hl
                ld      d, (hl)
                ex      de, hl
                inc     hl
                inc     hl
                ld      a, (hl)                 ; frame id 1..9
                ld      (tc_id), a
                inc     hl
                ld      a, (CRX)
                cp      (hl)
                jr      nz, tc_fn
                inc     hl
                ld      a, (CRY)
                cp      (hl)
                jr      nz, tc_fn
                inc     hl
                inc     hl
                ld      a, (CRW)
                cp      (hl)
                jr      nz, tc_fn
                inc     hl
                ld      a, (CRH)
                cp      (hl)
                jr      z, tc_hit
tc_fn:          pop     hl
                inc     hl
                inc     hl
                inc     c
                djnz    tc_f
                or      a
                ret
tc_hit:         pop     hl
                ld      a, c                    ; slot = flame * 9 + id - 1
                add     a, a
                add     a, a
                add     a, a
                add     a, c
                ld      hl, tc_id
                add     a, (hl)
                ld      (tc_slot), a            ; (slot + 1)
                ld      e, a
                ld      d, 0
                ld      hl, TC_VALID - 1
                add     hl, de
                ld      a, (hl)
                or      a
                ret     z                       ; not cached yet: compose it (tc_save keeps it)
                ld      a, (blit)               ; the screen upside down (set_flip patched blit into a jump): compose
                xor     0xdb                    ; it (and keep it again)
                ret     nz
                call    tc_seek
                xor     a                       ; (no tc_save: a later kept chunk skips tc_try)
                ld      (tc_slot), a
; tc_direct: the RAM disk at the slot: its picture (4 planes x CRH rows x 2 bytes) straight into VRAM at CRX, CRY,
; plane after plane. The copy changes the rect's planes one after the other, so it must lie wholly between two passes
; of the beam over the rect's rows: sprite.asm td_beam waits for that (docs/perf.md "M8a part 17"). The code and the
; stack stay clear of 0x8000-0x9FFF (VRAM while it is mapped) and of 0x1000-0x1FFF (the CG-ROM's place). Out: carry.
tc_direct:      ld      a, (CRY)                ; HL = VRAM + 40 CRY + CRX
                ld      l, a
                ld      h, 0
                ld      d, h
                ld      e, l
                add     hl, hl
                add     hl, hl
                add     hl, de
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      a, (CRX)
                ld      e, a
                add     hl, de
                ld      de, VRAM
                add     hl, de
                push    hl
                call    td_beam                 ; (sprite.asm: until the copy cannot meet the beam)
td_go:          pop     hl
                ld      de, 38
                ld      c, RD_DATA
                in      a, (0xe0)               ; VRAM at 0x8000
                ld      a, 1
td_p:           out     (PORT_WF), a
                push    hl
                push    af
                ld      a, (CRH)
td_r:           ld      b, 2
                inir
                add     hl, de
                dec     a
                jr      nz, td_r
                pop     af
                pop     hl
                add     a, a
                cp      16
                jr      nz, td_p
td_end:         in      a, (0xe1)
                scf
                ret
tc_flush:       ld      a, (flm_gen)
                ld      (tc_gen), a
                ld      a, (fore_gen)
                ld      (tc_gen + 1), a
                ld      hl, TC_VALID
                ld      de, TC_VALID + 1
                ld      bc, FLM_MAX * 9 - 1
                ld      (hl), 0
                ldir
                jp      tc_t1
; tc_save: after a chunk tc_try marked was composed: keep its picture
tc_save:        ld      a, (tc_slot)
                or      a
                ret     z
                ld      e, a
                ld      d, 0
                ld      hl, TC_VALID - 1
                add     hl, de
                ld      (hl), 1
                call    tc_seek
                ld      c, RD_DATA
                ld      hl, (V_COMPOSE)
                ld      a, 4
tc_wp:          push    hl
                push    af
                ld      a, (CRH)
tc_wr:          ld      b, 2
                otir
                ld      de, CW - 2
                add     hl, de
                dec     a
                jr      nz, tc_wr
                pop     af
                pop     hl
                ld      de, COMPOSE_PLANE
                add     hl, de
                dec     a
                jr      nz, tc_wp
                xor     a
                ld      (tc_slot), a
                ret
; tc_seek: the RAM disk at slot (tc_slot - 1) * 144
tc_seek:        ld      a, (tc_slot)
                dec     a
                ld      l, a
                ld      h, 0
                ld      e, l
                ld      d, h
                add     hl, hl
                add     hl, hl
                add     hl, hl
                add     hl, de                  ; * 9
                add     hl, hl
                add     hl, hl
                add     hl, hl
                add     hl, hl                  ; * 144
                ex      de, hl
                ld      a, TC_PAGE
                jp      far_seek
tc_slot:        db      0
tc_id:          db      0
tc_gen:         db      0xfe, 0

; ---------------------------------------------------------------- chunk buffers and the kept background
; oc_kept: carry set when the chunk is exactly the rect the last background-only redraw composed into SPRBUF_B
; (its background is already there: no restore); that buffer is then this chunk's
oc_kept:        ld      a, (rr_kv)
                or      a
                ret     z
                ld      hl, rr_kr
                ld      de, CRX
                ld      b, 4
ok_l:           ld      a, (de)
                cp      (hl)
                jp      nz, ok_no
                inc     hl
                inc     de
                djnz    ok_l
                xor     a
                ld      (rr_kv), a
                ld      de, SPRBUF_B
                ld      (V_COMPOSE), de
                ld      (oc_comp), de
                scf
                ret
ok_no:          or      a
                ret
; buf_pick: DE = a chunk buffer no pending chunk uses (SPRBUF_B only while it holds no kept picture or image); carry
; set when there is none
buf_pick:       ld      de, COMPOSE_A
                call    bp_used
                ret     nc
                ld      de, COMPOSE_B
                call    bp_used
                ret     nc
                ld      a, (rr_kv)
                ld      hl, PP_BBUSY            ; (or it holds an image this tick: overlay.asm slots 5, 6)
                or      (hl)
                scf
                ret     nz
                ld      de, SPRBUF_B
bp_used:        ld      a, (PEND_N)             ; carry when a pending chunk is in buffer DE
                or      a
                ret     z
                ld      b, a
                ld      hl, PEND_LIST + 5
bpu_l:          ld      a, (hl)
                cp      d
                scf
                ret     z
                push    de
                ld      de, 6
                add     hl, de
                pop     de
                djnz    bpu_l
                or      a
                ret
; ---------------------------------------------------------------- the flame registry across tile redraws
; flm_hook: a background redraw's rect (DR_X0..DR_X1, DR_Y0..DR_Y1) touching a registered flame means the
; flames must be checked again (an op in front of one may have changed); else their records only moved
flm_hook:       ld      a, (flm_n)
                or      a
                ret     z
                ld      b, a
                ld      hl, flm_rect
fh_l:           ld      a, (DR_X1)              ; x0 <= DR_X1 and DR_X0 < x0 + w (inclusive ends: err to touching)
                cp      (hl)
                jp      c, fh_n
                ld      a, (hl)
                inc     hl
                inc     hl
                add     a, (hl)
                dec     hl
                dec     hl
                ld      c, a
                ld      a, (DR_X0)
                cp      c
                jp      nc, fh_n
                inc     hl                      ; y0 <= DR_Y1 and DR_Y0 < y0 + h
                ld      a, (DR_Y1)
                cp      (hl)
                dec     hl
                jp      c, fh_n
                inc     hl
                ld      a, (hl)
                inc     hl
                inc     hl
                add     a, (hl)
                dec     hl
                dec     hl
                dec     hl
                ld      c, a
                ld      a, (DR_Y0)
                cp      c
                jp      nc, fh_n
                ld      a, 1
                ld      (flm_touch), a
                ret
fh_n:           inc     hl
                inc     hl
                inc     hl
                inc     hl
                djnz    fh_l
                ret
; flames_sync: after ops moved: rebuild the registry if a redraw touched a flame, else find each flame's
; record again by its place
flames_sync:    ld      a, (ops_gen)
                ld      hl, flm_gen
                cp      (hl)
                ret     z
                ld      a, (flm_touch)
                or      a
                jp      nz, flames_rebuild
                ld      a, (flm_n)
                or      a
                jp      z, flames_rebuild
                ld      b, a
                ld      ix, flm_rect
                ld      iy, flm_rec
fs_f:           push    bc
                ld      hl, (opl_base)          ; the back list
                ld      a, (OPCOUNT)
                ld      b, a
fs_s:           push    hl
                inc     hl
                ld      a, (hl)
                cp      CH_OBJ
                jp      nz, fs_sn
                inc     hl
                ld      a, (hl)                 ; id: flames 1..9
                dec     a
                cp      9
                jp      nc, fs_sn
                inc     hl
                ld      a, (hl)
                cp      (ix+0)
                jp      nz, fs_sn
                inc     hl
                ld      a, (hl)
                cp      (ix+1)
                jp      nz, fs_sn
                inc     hl
                ld      a, (hl)
                or      a
                jp      nz, fs_sn
                pop     hl                      ; found: the record start
                ld      (iy+0), l
                ld      (iy+1), h
                jr      fs_next
fs_sn:          pop     hl
                ld      de, 8
                add     hl, de
                djnz    fs_s
                pop     bc                      ; not found: rebuild
                jr      flames_rebuild
fs_next:        pop     bc
                ld      de, 4
                add     ix, de
                inc     iy
                inc     iy
                djnz    fs_f
                ld      a, (ops_gen)
                ld      (flm_gen), a
                ret
flames_rebuild: call    flames_build
                xor     a
                ld      (flm_touch), a
                ld      a, (flm_n)              ; the registered flames' rects
                or      a
                ret     z
                ld      b, a
                ld      hl, flm_rec
                ld      de, flm_rect
fr_l:           push    bc
                push    hl
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a
                inc     hl
                inc     hl
                inc     hl
                ld      a, (hl)                 ; x
                ld      (de), a
                inc     de
                inc     hl
                ld      a, (hl)                 ; y (rows 0..191)
                ld      (de), a
                inc     de
                inc     hl
                inc     hl
                ld      a, (hl)                 ; w
                ld      (de), a
                inc     de
                inc     hl
                ld      a, (hl)                 ; h
                ld      (de), a
                inc     de
                pop     hl
                inc     hl
                inc     hl
                pop     bc
                djnz    fr_l
                ret
flm_rect        equ     0x9fe8                  ; 4 * FLM_MAX (runtime only; above guard.asm GUARD_TABS, never read inside
                if flm_rect + 4 * FLM_MAX > 0xa000      ; blit or tc_direct's copy, while VRAM is mapped there)
                .error tcache.asm: flm_rect
                endif
flm_touch:      db      0
