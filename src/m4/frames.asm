; ---------------------------------------------------------------- pre-drawn pictures: choppers and spikes (M8a part 15)
; The frames overlay (W1, src/m4/ovl_frm.asm). A chopper's or a spike's picture step (spike.asm chomp_redraw and
; spike_redraw, our room's own tiles: VS_KIND 0) changes pixels only in a fixed rect of its tile (checked against the
; reference for every chopper and spike of levels 1-14 and every pair of pictures: tools/movecheck.py chompers,
; spikes):
;   a chopper: x 4c .. 4c + 3, rows 63r + 3 .. 63r + 62 (60 rows; the fore pieces' rects reach row 62);
;   a spike:   x 4c .. 4c + 5 (to 40), rows 63r + 34 .. 63r + 60 (27 rows; its right part is drawn by the right
;              neighbour).
; The rect's picture as the shadow holds it (the background without the fore pieces) depends only on the object's
; picture while nothing else in the rect changes, so each picture is kept in a RAM-disk slot the first time it is drawn
; and copied back later:
;   records: the pieces that change (a chopper: its bottom 101-105, top 111-113 and fore 106-110; a spike: its left
;   part 128-132 and fore 139-143, the right neighbour's 134-138) get their new image in place (id, size, top row; the
;   bottom row stays, a chopper's top piece is CHOMPER_FRAM_Y[n] above its bottom piece's), unless a piece comes or
;   goes (a chopper's top piece at n 0, 1; a spike's picture 0): then the tile(s) are regenerated as before;
;   pixels: the picture valid: the slot read into SPRBUF_B and put (anires.asm cs_put: the shadow, the dirty list, the
;   object pass's kept background); else the rect laid by dr_run (one chunk: its picture stays in SPRBUF_B), then
;   saved in the slot.
; Chopper pictures: n = CHOMPER_FRAM1[min(mod & 0x7F, 6)] (0..4); with blood (bit 7) not this way. Spike pictures:
; spike_frame 0..9; frames with the same images share one (fs_canon: 0 = 9, 1 = 8, 2 = 7, 4 = 6: 6 pictures).
; The objects (FRM_N, the first ones stepping after a room draw) and their pictures' validity are in FRM_TAB (low RAM;
; spike.asm frm_drop, frm_reset): a redraw of the shadow that touches an object's rect (anires.asm dirty_hook: every
; dr_run and cs_put) drops its pictures, a room draw every object and slot. The object's own redraw here keeps its
; other pictures (they are pictures of the same background).
; The slots (fs_seek): 16 MB: page FRM_P16, 1 KB each, six per object; else the pieces of pages 0-7 listed in
; fs_bdir (FRM_BIG bytes: a chopper's or a spike's picture) and fs_sdir (FRM_SMALL: a spike's), taken by each object
; at its first step until they run out (pictures without a slot are drawn as before, every time).
; Entry frm_step (stub frm_fast): B = the new picture's key, D = the old one's (a chopper: n | the blood bit; a spike:
; its spike_frame), C = 0 a chopper, 1 a spike; VS_TAG = the tile (0..29). Carry: not this way, nothing done (the
; caller redraws as before).
FRM_BIG         equ     960                     ; a chopper's slot: 4 planes x 60 rows x 4 bytes
FRM_SMALL       equ     648                     ; a spike's: 4 planes x 27 rows x 6 bytes

frm_step:       push    ix
                call    fs_step
                pop     ix
                ret
fs_step:        ld      a, c
                ld      (fs_kind), a
                or      a
                jr      nz, fs_sp
                ld      a, b                    ; a chopper: n | blood
                or      d
                rla
                ret     c                       ; (blood: as before)
                ld      a, d
                ld      (fs_ko), a
                ld      a, b
                jr      fs_k1
fs_sp:          ld      a, b                    ; a spike: the frames' pictures
                cp      10
                ccf
                ret     c
                ld      a, d
                cp      10
                ccf
                ret     c
                ld      hl, fs_canon
                call    fs_tab
                ld      (fs_ko), a
                ld      hl, fs_canon
                ld      a, b
                call    fs_tab
fs_k1:          ld      (fs_k), a
                ; the rect: x0, x1, y0, y1
                ld      a, (VS_TAG)
                ld      b, 0
fs_r1:          cp      10
                jr      c, fs_r2
                sub     10
                inc     b
                jr      fs_r1
fs_r2:          ld      (fs_col), a
                add     a, a
                add     a, a
                ld      (fs_rect), a
                ld      e, a
                ld      a, (fs_kind)
                or      a
                ld      a, 4
                jr      z, fs_r3
                ld      a, 6
fs_r3:          add     a, e
                cp      41
                jr      c, fs_r4
                ld      a, 40
fs_r4:          ld      (fs_rect + 1), a
                ld      a, b                    ; 63 r
                add     a, a
                add     a, a
                add     a, a
                add     a, a
                add     a, a
                add     a, a
                sub     b
                ld      b, a
                ld      a, (fs_kind)
                or      a
                ld      de, 3 * 256 + 60        ; (a chopper: + 3, 60 rows)
                jr      z, fs_r5
                ld      de, 34 * 256 + 27       ; (a spike: + 34, 27 rows)
fs_r5:          ld      a, d
                add     a, b
                ld      (fs_rect + 2), a
                add     a, e
                ld      (fs_rect + 3), a
                ; the object's entry: its tag, else a free one
                ld      a, (VS_TAG)
                inc     a
                ld      c, a
                ld      ix, FRM_TAB
                ld      de, FE_SIZE
                ld      b, FRM_N
fs_e1:          ld      a, (ix + FE_TAG)
                cp      c
                jr      z, fs_e3
                add     ix, de
                djnz    fs_e1
                ld      ix, FRM_TAB
                ld      b, FRM_N
fs_e2:          ld      a, (ix + FE_TAG)
                or      a
                jr      z, fs_new
                add     ix, de
                djnz    fs_e2
                scf                             ; (no entry left: as before)
                ret
fs_new:         ld      (ix + FE_TAG), c
                push    ix
                pop     de
                ld      hl, fs_rect             ; (FE_X0 .. FE_Y1)
                ld      bc, 4
                ldir
                xor     a
                ld      (ix + FE_MASK), a
                call    fs_alloc
fs_e3:          ; the records: patched in place, else the tile(s) regenerated
                push    ix
                call    fs_recs
                pop     ix
                ; DR and the compose rect = the rect
                ld      hl, fs_rect             ; x0, x1, y0, y1 -> DR_X0, DR_X1, DR_Y0, DR_Y1; CRX, CRW, CRY, CRH
                ld      de, DR_X0
                ld      bc, 4
                ldir
                ld      a, (fs_rect)
                ld      (CRX), a
                ld      b, a
                ld      a, (fs_rect + 1)
                sub     b
                ld      (CRW), a
                ld      (fs_w), a
                ld      a, (fs_rect + 2)
                ld      (CRY), a
                ld      b, a
                ld      a, (fs_rect + 3)
                sub     b
                ld      (CRH), a
                ld      (fs_h), a
                ld      a, (fs_w)               ; the row loops: W of the six INI / OUTI, then the compose row's rest
                neg
                add     a, 6
                add     a, a
                ld      e, a
                ld      d, 0
                ld      hl, fs_ich
                add     hl, de
                ld      (fs_ij + 1), hl
                ld      hl, fs_och
                add     hl, de
                ld      (fs_oj + 1), hl
                ld      a, (fs_w)
                neg
                add     a, CW
                ld      (fs_ia + 1), a
                ld      (fs_oa + 1), a
                ; the picture's bit
                ld      a, (fs_k)
                ld      b, a
                inc     b
                ld      a, 0x80
fs_b1:          rlca
                djnz    fs_b1
                ld      (fs_bit), a
                ld      a, (ix + FE_MASK)
                ld      (fs_mask), a
                ld      hl, fs_bit
                and     (hl)
                jr      z, fs_miss
                ; the picture valid: from its slot into SPRBUF_B, then put
                call    fs_seek
                ld      hl, SPRBUF_B
                ld      a, 4
fs_i1:          push    hl
                ex      af, af'
                ld      a, (fs_h)
fs_i2:          ex      af, af'
fs_ij:          jp      0                       ; (patched: fs_ich + 2 (6 - W))
fs_ich:         ini
                ini
                ini
                ini
                ini
                ini
fs_ia:          ld      de, 0                   ; (patched: CW - W)
                add     hl, de
                ex      af, af'
                dec     a
                jr      nz, fs_i2
                ex      af, af'
                pop     hl
                inc     h
                inc     h                       ; (+ COMPOSE_PLANE)
                dec     a
                jr      nz, fs_i1
                push    ix
                call    cs_put                  ; (dirty_hook: frm_drop drops this object's pictures too: kept below)
                pop     ix
                jr      fs_keep
fs_miss:        push    ix
                call    dr_run                  ; (one chunk: x1 - x0 <= CW, y1 - y0 <= CH; its picture stays in SPRBUF_B)
                pop     ix
                call    fs_seek
                jr      c, fs_keep0             ; (no slot for this picture)
                ld      hl, SPRBUF_B
                ld      a, 4
fs_o1:          push    hl
                ex      af, af'
                ld      a, (fs_h)
fs_o2:          ex      af, af'
fs_oj:          jp      0
fs_och:         outi
                outi
                outi
                outi
                outi
                outi
fs_oa:          ld      de, 0
                add     hl, de
                ex      af, af'
                dec     a
                jr      nz, fs_o2
                ex      af, af'
                pop     hl
                inc     h
                inc     h
                dec     a
                jr      nz, fs_o1
fs_keep:        ld      a, (fs_mask)            ; the object's pictures as before this redraw, and this one
                ld      hl, fs_bit
                or      (hl)
                ld      (ix + FE_MASK), a
fs_fg:          ld      a, (fs_fore)            ; a fore record patched where a redraw touched a torch flame
                ld      hl, flm_touch           ; (dirty_from_dr's flm_hook): the torch pictures with fore pieces in
                and     (hl)                    ; them go (tcache.asm tc_try; after a regeneration the registry
                ret     z                       ; follows instead)
                ld      hl, fore_gen
                inc     (hl)
                or      a
                ret
fs_keep0:       ld      a, (fs_mask)
                ld      (ix + FE_MASK), a
                jr      fs_fg

; fs_recs: the object's records from the old picture fs_ko to the new one fs_k
fs_recs:        xor     a
                ld      (fs_fore), a
                ld      a, (fs_kind)
                or      a
                jr      nz, fr_sp
                ld      a, (fs_ko)              ; a chopper: its top piece is there for n >= 2 only
                cp      2
                sbc     a, a
                ld      b, a
                ld      a, (fs_k)
                cp      2
                sbc     a, a
                xor     b
                jr      nz, fr_regen
                ld      a, (fs_k)               ; the bottom piece (its bottom row: the tile's main row)
                add     a, 101
                ld      e, a
                ld      bc, 101 * 256 + 105
                xor     a
                call    fs_patch0
                jr      c, fr_regen
                ld      (fs_my), hl
                ld      a, (fs_k)               ; the fore piece
                add     a, 106
                ld      e, a
                ld      bc, 106 * 256 + 110
                ld      a, 2
                call    fs_patch0
                jr      c, fr_regen
                ld      a, 1
                ld      (fs_fore), a
                ld      a, (fs_k)               ; the top piece: CHOMPER_FRAM_Y[n] above the main row
                cp      2
                ret     c
                ld      hl, chomper_fram_y
                call    fs_tab
                ld      e, a
                ld      d, 0
                ld      hl, (fs_my)
                or      a
                sbc     hl, de
                ld      (fs_yb), hl
                ld      a, (fs_k)
                add     a, 111 - 2
                ld      e, a
                ld      bc, 111 * 256 + 113
                xor     a
                call    fs_patch
                ret     nc
fr_regen:       call    own_regen               ; (a fresh dirty rect, the room links, the tile)
                ld      a, (fs_kind)
                or      a
                ret     z
                ld      a, (fs_col)
                cp      9
                ret     z
                ld      a, (tr_t)
                inc     a
                jp      tile_regen              ; (a spike: its right neighbour draws its right part)
fr_sp:          ld      a, (fs_ko)              ; a spike: picture 0 has no pieces
                or      a
                ld      a, (fs_k)
                jr      nz, fr_s1
                or      a
                ret     z                       ; (0 -> 0: nothing changes)
                jr      fr_regen
fr_s1:          or      a
                jr      z, fr_regen
                add     a, 127                  ; its left part (back)
                ld      e, a
                ld      bc, 128 * 256 + 132
                xor     a
                call    fs_patch0
                jr      c, fr_regen
                ld      a, (fs_k)               ; the fore part
                add     a, 138
                ld      e, a
                ld      bc, 139 * 256 + 143
                ld      a, 2
                call    fs_patch0
                jr      c, fr_regen
                ld      a, 1
                ld      (fs_fore), a
                ld      a, (fs_col)             ; the right part: the right neighbour's back
                cp      9
                ret     z
                ld      a, (fs_k)
                add     a, 133
                ld      e, a
                ld      bc, 134 * 256 + 138
                ld      a, 1
                call    fs_patch0
                jr      c, fr_regen
                ret

; fs_patch0: A = the list (0 back, 2 fore; 1: the back of the tile right of VS_TAG), B..C = the ids to look for, E =
; the new id: the first such CH_ENV record of the tile gets it, its bottom row kept; HL = that row; carry: none found.
; fs_patch: the same with the bottom row fs_yb
fs_patch0:      ld      hl, 0xffff
                ld      (fs_yb), hl
fs_patch:       ld      d, a
                ld      a, (VS_TAG)
                bit     0, d
                jr      z, fp_1
                inc     a
                res     0, d
fp_1:           ld      (OP_TAG), a
                ld      a, d
                ld      (OP_LIST), a
                ld      a, b
                ld      (OP_LO), a
                ld      a, c
                ld      (OP_HI), a
                ld      a, e
                ld      (fs_id), a
                ld      a, CH_ENV
                ld      (OP_CH), a
                ld      a, 1
                ld      (OP_ONLY), a
                call    op_patch                ; (find only: HL = the record, A != 0)
                push    af
                xor     a
                ld      (OP_ONLY), a
                pop     af
                or      a
                scf
                ret     z
                push    hl
                pop     ix                      ; IX = the record
                ld      a, (fs_id)
                ld      (ix + 2), a
                ld      c, a
                ld      a, CH_ENV
                call    dir_entry
                inc     hl
                inc     hl
                inc     hl
                ld      b, (hl)                 ; w
                inc     hl
                ld      c, (hl)                 ; h
                ld      hl, (fs_yb)             ; the bottom row: given, or the record's
                ld      a, h
                and     l
                inc     a
                jr      nz, fp_2
                ld      l, (ix + 4)
                ld      h, (ix + 5)
                ld      e, (ix + 7)
                ld      d, 0
                add     hl, de
                dec     hl
                ld      (fs_yb), hl
fp_2:           ld      (ix + 6), b
                ld      (ix + 7), c
                ld      b, 0                    ; top = bottom - h + 1
                or      a
                sbc     hl, bc
                inc     hl
                ld      (ix + 4), l
                ld      (ix + 5), h
                ld      b, h                    ; the slice's extent grows with the new image (room.asm yr_merge:
                ld      c, l                    ; BC = top, HL = bottom + 1, DE = the slice)
                ld      hl, (fs_yb)
                inc     hl
                ld      a, (OP_LIST)
                ld      e, a
                add     a, a
                add     a, a
                add     a, e
                add     a, a
                add     a, a
                add     a, a                    ; list * 40
                ld      e, a
                ld      a, (OP_TAG)
                add     a, e
                ld      e, a
                ld      d, 0
                call    yr_merge
                ld      hl, (fs_yb)
                or      a
                ret

; fs_alloc: IX = a new entry: its slots (FE_FIRST: the first, bit 7 the small pool; FE_CNT: how many: the pictures
; 0 .. FE_CNT - 1 have one). A spike takes six small ones, else six big ones, else what is left of the pool with more.
fs_alloc:       ld      a, (HO_MAIN + HO_RDTOP)
                cp      FS_TOP2
                ld      hl, FRM_N * 6           ; (16 MB: six for each)
                jr      nc, fa_0
                ld      hl, FRM_NS * 256 + FRM_NB
fa_0:           ld      a, (FRM_NEXT)           ; L, H = the big and the small pool's free slots
                ld      b, a
                ld      a, l
                sub     b
                ld      l, a
                ld      a, (FRM_NEXT + 1)
                ld      c, a
                ld      a, h
                sub     c
                ld      h, a                    ; (B, C = their next ones)
                ld      a, (fs_kind)
                or      a
                ld      e, 5
                jr      z, fa_big
                ld      e, 6
                ld      a, h
                cp      e
                jr      nc, fa_sm
                ld      a, l
                cp      e
                jr      nc, fa_big
                cp      h
                jr      nc, fa_big
fa_sm:          ld      a, h                    ; the small pool: E or what is left
                cp      e
                jr      c, fa_1
                ld      a, e
fa_1:           ld      (ix + FE_CNT), a
                add     a, c
                ld      (FRM_NEXT + 1), a
                ld      a, c
                or      0x80
                ld      (ix + FE_FIRST), a
                ret
fa_big:         ld      a, l
                cp      e
                jr      c, fa_2
                ld      a, e
fa_2:           ld      (ix + FE_CNT), a
                ld      (ix + FE_FIRST), b
                add     a, b
                ld      (FRM_NEXT), a
                ret

; fs_seek: the RAM disk at the slot of picture fs_k of entry IX, C = RD_DATA; carry: it has none
fs_seek:        ld      a, (fs_k)
                cp      (ix + FE_CNT)
                ccf
                ret     c
                add     a, (ix + FE_FIRST)      ; (bit 7: the small pool)
                ld      b, a
                ld      a, (HO_MAIN + HO_RDTOP)
                cp      FS_TOP2
                jr      c, fk_dir
                ld      a, b                    ; 16 MB: page FRM_P16, id x 1024
                add     a, a
                add     a, a
                ld      d, a
                ld      e, 0
                ld      a, FRM_P16
                jr      fk_go
fk_dir:         ld      hl, fs_bdir
                bit     7, b
                jr      z, fk_1
                res     7, b
                ld      hl, fs_sdir
fk_1:           ld      a, b
                add     a, a
                add     a, b
                ld      e, a
                ld      d, 0
                add     hl, de
                ld      a, (hl)                 ; page, address
                inc     hl
                ld      e, (hl)
                inc     hl
                ld      d, (hl)
fk_go:          call    far_seek
                ld      c, RD_DATA
                or      a
                ret

; fs_tab: HL = a table, A = an index: A = its entry (keeps BC, DE)
fs_tab:         add     a, l
                ld      l, a
                jr      nc, ft_1
                inc     h
ft_1:           ld      a, (hl)
                ret

fs_canon:       db      0, 1, 2, 3, 4, 5, 4, 2, 1, 0
; the slots of pages 0-7 (512 KB, 1 MB): page, address (docs/memory.md "RAM disk"; tests/m5_boot.py RUNTIME_SCRATCH)
fs_bdir:
                db      4
                dw      0xe000
                db      4
                dw      0xe3c0
                db      4
                dw      0xe780
                db      4
                dw      0xeb40
                db      4
                dw      0xef00
                db      4
                dw      0xf2c0
                db      4
                dw      0xf680
                db      4
                dw      0xfa40
                db      0
                dw      0xe868
                db      0
                dw      0xec28
                db      6
                dw      0x2880
                db      6
                dw      0x2c40
                db      0
                dw      0xfc00
                db      1
                dw      0xda58
                db      6
                dw      0xf964
FRM_NB          equ     ($ - fs_bdir) / 3
fs_sdir:
                db      6
                dw      0xfd24
                db      1
                dw      0xfc5c
                db      5
                dw      0x3ad0
                db      5
                dw      0x3d58
                db      1
                dw      0x7d00
FRM_NS          equ     ($ - fs_sdir) / 3
fs_yb:          dw      0                       ; a piece's bottom row
fs_my:          dw      0                       ; the chopper's main row
; the step's variables: low RAM 0x09A6-0x09B3 (runtime only, docs/memory.md; RV ends at 0x09A5)
fs_kind         equ     0x09a6                  ; 0 chopper, 1 spike
fs_k            equ     0x09a7                  ; the new picture
fs_ko           equ     0x09a8                  ; the old one
fs_col          equ     0x09a9
fs_rect         equ     0x09aa                  ; x0, x1, y0, y1
fs_w            equ     0x09ae
fs_h            equ     0x09af
fs_bit          equ     0x09b0
fs_mask         equ     0x09b1
fs_fore         equ     0x09b2                  ; a fore record was patched
fs_id           equ     0x09b3
