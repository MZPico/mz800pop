; ---------------------------------------------------------------- choppers and spikes: the step, the direct copy (M8a part 25)
; The low code, part 2 (window WL2 = low RAM 0x0E00-0x0FFF, src/m4/ovl_low2.asm; part 1 and the rules: frmlow.asm).
; The complete pictures. A chunk that is exactly an object's rect with nothing else in it (frmlow.asm lc_chunk) is the
; picture plus the fore pieces: it depends on the picture only, like the background (frm_drop drops both, FE_CMASK with
; FE_MASK). Its first composition is kept in the complete picture's slot (lc_save; row-major: a row's four planes one
; after the other), and later such chunks copy it from there straight into VRAM (lc_direct): no restore, no people, no
; fore pieces, no compose buffer, no pending chunk. The slots: 16 MB page FRM_P16 + 0x6000 (every picture); 512 KB and
; 1 MB the pool FRM_CPOOL in page FRM_CPAGE (FRM_NC pictures: the first chopper's first FRM_NC; lc_step).
; lc_direct runs with VRAM mapped: this code and its data stay clear of 0x1000-0x1FFF and 0x8000-0x9FFF.
LD_MARGIN       equ     20                      ; lines (sprite.asm BEAM_MARGIN: the scan, the call, the interrupt)
LD_GUARD        equ     12                      ; (sprite.asm BEAM_GUARD)

; lc_step: frames.asm fs_step, IX = the object, A = 1 a step from its slot (a hit), 0 a picture just drawn and saved
; (a miss: dr_run wrote the shadow); lc_sp, lc_sa = the picture's slot, fs_k / fs_bit / fs_kind the picture; CR* and
; DR_* = the object's rect. The slot's place and the complete picture's are kept in the object's entry; a hit makes the
; shadow's rect stale and puts the rect on the dirty list (anires.asm dirty_hook, as cs_put did without its shadow
; write and kept picture); its complete pictures stay (lc_cm: what frm_drop dropped of them by the object's own redraw).
lc_step:        push    af
                or      a
                call    nz, LC_SWPRE            ; (a hit: the stale rects its rect touches, its own one too)
                ld      a, (lc_sp)
                ld      (ix + FE_SP), a
                ld      hl, (lc_sa)
                ld      (ix + FE_SA), l
                ld      (ix + FE_SA + 1), h
                ld      a, (fs_bit)
                ld      (ix + FE_KB), a
                ld      a, (fs_kind)            ; the complete picture's slot: a chopper's only (a spike's chunk has
                or      a                       ; the kid in it nearly always: its pictures were kept, not copied)
                ld      a, 0
                jr      nz, ls_cp
                ld      a, (HO_MAIN + HO_RDTOP) ; 16 MB: its slot + 0x6000
                cp      FS_TOP2
                jr      c, ls_pool
                ld      a, h
                add     a, FRM_C16
                ld      h, a
                ld      a, FRM_P16
                jr      ls_ca
ls_pool:        ld      a, (ix + FE_CCNT)       ; 512 KB, 1 MB: the pool for the first chopper (FE_CCNT 2: it has it,
                or      a                       ; 1: not)
                jr      nz, ls_p1
                ld      hl, FRM_CNEXT
                or      (hl)
                ld      a, 1
                jr      nz, ls_p0
                ld      (hl), a
                inc     a
ls_p0:          ld      (ix + FE_CCNT), a
ls_p1:          dec     a
                jr      z, ls_cp                ; (A = 0: none)
                ld      a, (fs_k)
                ld      e, a
                cp      FRM_NC
                ld      a, 0
                jr      nc, ls_cp
                ld      a, 960 / 4
                call    mul8
                add     hl, hl
                add     hl, hl                  ; x 960
                ld      de, FRM_CPOOL
                add     hl, de
                ld      a, FRM_CPAGE
ls_ca:          ld      (ix + FE_CA), l
                ld      (ix + FE_CA + 1), h
ls_cp:          ld      (ix + FE_CP), a
                pop     af
                ld      (ix + FE_ST), a
                or      a
                jr      z, ls_d
                push    ix
                call    dirty_hook
                pop     ix
ls_d:           ld      a, (lc_cm)
                ld      (ix + FE_CMASK), a
                ret

; lc_chunk: sprite.asm obj_chunk's head: a chunk that is exactly an object's rect with nothing else in it (tcache.asm
; tc_try's rule: no overlay op, no falling floor, no character's rect; and no registered torch flame, which animates on
; its own): its complete picture valid: straight into VRAM (lc_direct; carry: done); else it is kept after
; the chunk is composed (lc_sv: lc_save)
lc_chunk:       ld      a, (FRM_TAB + FE_TAG)   ; (no object: lc_sv's high byte is 0, lc_save clears it)
                or      a
                ret     z
                call    LC_CR
                push    ix
                ld      ix, FRM_TAB
                ld      b, FRM_N
lk_l:           ld      a, (ix + FE_CP)
                or      a
                jr      z, lk_n
                push    bc
                push    ix
                pop     hl
                ld      de, lc_c
                call    LC_CMP4
                pop     bc
                jr      z, lk_hit
lk_n:           ld      de, FE_SIZE
                add     ix, de
                djnz    lk_l
lk_no:          pop     ix
                or      a
                ret
lk_hit:         ld      a, (OV_NM)
                ld      hl, OV_NF
                or      (hl)
                jr      nz, lk_no
                call    mob_meet
                jr      nz, lk_no
                call    oc_kidtouch
                or      a
                jr      nz, lk_no
                ld      a, (flm_n)
                or      a
                jr      z, lk_f0
                ld      b, a
                ld      hl, flm_rect
lk_f:           push    hl
                push    bc
                call    okt_meet
                pop     bc
                pop     hl
                jr      nz, lk_no
                inc     hl
                inc     hl
                inc     hl
                inc     hl
                djnz    lk_f
lk_f0:          ld      a, (ix + FE_CMASK)
                and     (ix + FE_KB)
                jr      nz, lk_dir
                ld      (lc_sv), ix             ; (not kept yet: lc_save after the composition)
                jr      lk_no
lk_dir:         ld      a, (blit)               ; the screen upside down (set_flip patched blit into a jump): compose
                xor     0xdb
                jr      nz, lk_no
                call    lc_direct
                pop     ix
                scf
                ret
; lc_direct: IX = the object (its rect = the compose rect): its complete picture (row-major) straight into VRAM. A row's
; four planes are written one after the other, top row first, slower than the beam (LD_K lines a row at most with the
; boot's worst RAM disk, 15 wait states: 3.6 for a chopper's 4 bytes, ~5.1 for a spike's 6, measured), like pend_flush's chunk copies: the copy starts when d, the lines until the beam next
; reaches the top row, is at least (LD_K - 1) CRH + LD_MARGIN (the beam cannot overtake it) and not just behind the beam
; (d <= 312 - LD_GUARD). docs/perf.md "M8a part 25".
lc_direct:      ld      a, (ix + FE_X1)
                sub     (ix + FE_X0)
                ld      (ld_n + 1), a
                ld      a, (ix + FE_CP)
                ld      e, (ix + FE_CA)
                ld      d, (ix + FE_CA + 1)
                call    far_seek
                ld      a, (ld_n + 1)           ; the need: (3 w - 2) / 4 CRH + LD_MARGIN (LD_K - 1 lines a row:
                ld      e, a                    ; 2.5 for a chopper's 4 bytes, 4 for a spike's 6)
                add     a, a
                add     a, e
                sub     2
                ld      e, a
                ld      a, (CRH)
                call    mul8
                srl     h
                rr      l
                srl     h
                rr      l
                ld      de, LD_MARGIN
                add     hl, de
                ld      (lc_need), hl
                ld      a, (CRY)                ; HL = VRAM + 40 CRY + CRX
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
ld_b:           call    pf_beam
                ld      ix, CRX
                call    pf_d                    ; HL = d
                ld      de, (lc_need)
                or      a
                sbc     hl, de
                jr      c, ld_b
                add     hl, de
                ld      de, 312 - LD_GUARD + 1
                or      a
                sbc     hl, de
                jr      nc, ld_b
ld_go:          pop     de                      ; DE = the row
                ld      c, RD_DATA
                in      a, (0xe0)               ; VRAM at 0x8000
                ld      a, (CRH)
ld_r:           ex      af, af'
                ld      a, 1
ld_p:           ld      h, d
                ld      l, e
                out     (PORT_WF), a
ld_n:           ld      b, 0                    ; (patched: the width)
                inir
                add     a, a
                cp      16
                jr      nz, ld_p
                ld      hl, 40
                add     hl, de
                ex      de, hl
                ex      af, af'
                dec     a
                jr      nz, ld_r
ld_end:         in      a, (0xe1)
                ret

; lc_save: sprite.asm obj_chunk after the chunk is composed (in place of tcache.asm tc_save): the chunk lc_chunk marked
; becomes its object's complete picture (row-major), then tc_save
lc_save:        ld      hl, (lc_sv)
                ld      a, h                    ; (its high byte only: FRM_TAB is at 0x0700)
                or      a
                jp      z, tc_save
                xor     a
                ld      (lc_sv + 1), a
                push    ix
                push    hl
                pop     ix
                ld      a, (ix + FE_CMASK)
                or      (ix + FE_KB)
                ld      (ix + FE_CMASK), a
                ld      a, (ix + FE_X1)
                sub     (ix + FE_X0)
                ld      (sv_n + 1), a
                ld      a, (ix + FE_CP)
                ld      e, (ix + FE_CA)
                ld      d, (ix + FE_CA + 1)
                pop     ix
                call    far_seek
                ld      c, RD_DATA
                ld      hl, (V_COMPOSE)
                ld      de, COMPOSE_PLANE
                ld      a, (CRH)
sv_r:           push    af
                push    hl
                ld      a, 4
sv_p:           push    hl
sv_n:           ld      b, 0                    ; (patched: the width)
                otir
                pop     hl
                add     hl, de
                dec     a
                jr      nz, sv_p
                pop     hl
                ld      a, l
                add     a, CW
                ld      l, a
                jr      nc, sv_1
                inc     h
sv_1:           pop     af
                dec     a
                jr      nz, sv_r
                jp      tc_save
