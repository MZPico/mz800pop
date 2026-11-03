; ---------------------------------------------------------------- the frame store's generator (step 2)
; docs/ramdisk-tiers.md section 11 "As built: step 2". Makes the stored variants (mirror, shift) of an image from one
; read of it per mirror: the image is read into the cell buffer at the lowest shift stored (the kernel's lo / hi
; tables; at shift 0 a plain copy; mirrored: the columns in reverse order, each byte through the bit-reverse table),
; every further shift is the buffer shifted one more bit (each plane's row a little-endian number of ow bytes, one
; SLA / RL each: the same bytes as the kernel's shift by its tables), and each stored variant is written to its entry
; with OUTI. Byte for byte the kernel's spr_fetch buffer (tests/m8_fstore.py). The row code is made for the image's
; width (fg_mk) into FG_CODE.
;
; fg_run: HL = mask table A, DE = mask table B (0: none), BC = the number of ids, fg_id = the first id. A mask is a
;   word per id, bit v = variant v = mirror * 8 + shift stored. A variant set in table A gets the next entry at fg_pa,
;   one set in table B the next at fg_pb (page, address: each table allocates in id and variant order, an entry that
;   would cross a page starts the next page: tools/fstore.py the same), its key table slot (FS_PAGE id * 64 + v * 4)
;   the entry's page and address; ff_prog after each entry. Interrupts off, VRAM unmapped (the bit-reverse table),
;   uses SPRBUF_A and the includer's FG_VARS (FG_VARS_N bytes) and FG_CODE (FG_CODE_N bytes); fg_dir (here: kid and
;   sword ids) reads dir_buf through dir_entry.
fg_ma           equ     FG_VARS                 ; the mask tables' next words
fg_mb           equ     FG_VARS + 2
fg_cnt          equ     FG_VARS + 4             ; ids left
fg_id           equ     FG_VARS + 6             ; the id (16 bits)
fg_va           equ     FG_VARS + 8             ; its masks (A, B)
fg_vb           equ     FG_VARS + 10
fg_ca           equ     FG_VARS + 12            ; the variants of this mirror left (A, B), from the current shift
fg_cb           equ     FG_VARS + 13
fg_v            equ     FG_VARS + 14            ; the variant in the buffer
fg_ent          equ     FG_VARS + 16            ; the directory entry's page, address (hi, lo), width, height
fg_st           equ     FG_VARS + 21            ; the row stride (w + 1) * 4
fg_n            equ     FG_VARS + 22            ; the entry's bytes
fg_pa           equ     FG_VARS + 24            ; table A's next entry: page, address
fg_pb           equ     FG_VARS + 27            ; table B's
fp_ps           equ     FG_VARS + 30            ; fg_put: the table's pointer, the entry's page and address,
fp_pg           equ     FG_VARS + 32            ; the bytes past the last 64
fp_ad           equ     FG_VARS + 33
fp_r            equ     FG_VARS + 35
fgk_t           equ     FG_VARS + 36            ; fg_mk: the template
FG_VARS_N       equ     38
fg_c0           equ     FG_CODE                 ; the kinds' code (a tag, then 14 + w x the template's length;
fg_c1           equ     fg_c0 + 1 + 14 + 7 * 5  ; the step 7 + (w + 1) x 16)
fg_c2           equ     fg_c1 + 1 + 14 + 7 * 8
fg_c3           equ     fg_c2 + 1 + 14 + 7 * 11
fg_c4           equ     fg_c3 + 1 + 14 + 7 * 14
FG_CODE_N       equ     fg_c4 + 1 + 7 + 8 * 16 - FG_CODE


fg_run:         ld      (fg_ma), hl
                ld      (fg_mb), de
                ld      (fg_cnt), bc
                ld      a, 0xff                 ; (no row code made yet)
                ld      (fg_c0), a
                ld      (fg_c1), a
                ld      (fg_c2), a
                ld      (fg_c3), a
                ld      (fg_c4), a
fgr_id:         ld      hl, (fg_ma)
                ld      e, (hl)
                inc     hl
                ld      d, (hl)
                inc     hl
                ld      (fg_ma), hl
                ld      (fg_va), de
                ld      hl, (fg_mb)
                ld      a, h
                or      l
                ld      d, a
                ld      e, a
                jr      z, fgr_b
                ld      e, (hl)
                inc     hl
                ld      d, (hl)
                inc     hl
                ld      (fg_mb), hl
fgr_b:          ld      (fg_vb), de
                ld      hl, (fg_va)
                ld      a, h
                or      l
                or      d
                or      e
                call    nz, fg_img
                ld      hl, (fg_id)
                inc     hl
                ld      (fg_id), hl
                ld      hl, (fg_cnt)
                dec     hl
                ld      (fg_cnt), hl
                ld      a, h
                or      l
                jr      nz, fgr_id
                ret

; fg_img: the stored variants of image fg_id (masks fg_va, fg_vb)
fg_img:         call    fg_dir                  ; HL = the 8-byte directory entry
                ld      de, fg_ent
                ld      bc, 5
                ldir
                ld      a, (fg_ent + 3)         ; the stride and the bytes (w + 1) * 4 * h
                inc     a
                add     a, a
                add     a, a
                ld      (fg_st), a
                ld      e, a
                ld      d, 0
                ld      a, (fg_ent + 4)
                ld      b, a
                ld      hl, 0
fgi_m:          add     hl, de
                djnz    fgi_m
                ld      (fg_n), hl
                xor     a                       ; mirror 0: variants 0-7
                ld      (fg_v), a
                ld      a, (fg_va)
                ld      (fg_ca), a
                ld      a, (fg_vb)
                ld      (fg_cb), a
                call    fg_mir
                ld      a, 8                    ; mirror 1: variants 8-15
                ld      (fg_v), a
                ld      a, (fg_va + 1)
                ld      (fg_ca), a
                ld      a, (fg_vb + 1)
                ld      (fg_cb), a
fg_mir:         ld      a, (fg_ca)
                ld      hl, fg_cb
                or      (hl)
                ret     z
fgm_lo:         rra                             ; up to the lowest shift stored: the image is read at that shift
                jr      c, fgm_ld
                ld      hl, fg_ca
                srl     (hl)
                ld      hl, fg_cb
                srl     (hl)
                ld      hl, fg_v
                inc     (hl)
                jr      fgm_lo
fgm_ld:         call    fg_load
fgm_s:          ld      hl, fg_ca               ; the buffer holds variant fg_v: stored in A, in B?
                srl     (hl)
                ld      hl, fg_pa
                call    c, fg_put
                ld      hl, fg_cb
                srl     (hl)
                ld      hl, fg_pb
                call    c, fg_put
                ld      a, (fg_ca)
                ld      hl, fg_cb
                or      (hl)
                ret     z                       ; (no higher shift stored)
                ld      a, 4                    ; one more bit: the step's code (kind 4)
                call    fg_mk
                ld      (fgm_c + 1), hl
                ld      ix, SPRBUF_A
                call    fg_rows
fgm_c:          call    0                       ; (patched: the step's code)
                ld      hl, fg_v
                inc     (hl)
                jr      fgm_s

; fg_rows: B' = the rows, DE' = the stride (the row code's loop)
fg_rows:        exx
                ld      a, (fg_st)
                ld      e, a
                ld      d, 0
                ld      a, (fg_ent + 4)
                ld      b, a
                exx
                ret

; fg_dir: fg_id -> HL = its directory entry (dir_entry: dir_buf)
fg_dir:         ld      a, (fg_id)
                cp      FS_SWORD
                ld      c, a
                ld      a, CH_KID
                jp      c, dir_entry
                ld      a, c
                sub     FS_SWORD
                ld      c, a
                ld      a, CH_SWORD
                jp      dir_entry

; fg_load: the image into SPRBUF_A as variant fg_v (the image: plane 0's rows, then planes 1-3): kind = the mirror,
; + 2 when shifted (s = fg_v & 7: D = its lo table's page, B its hi table's; E = the bit-reverse table's)
fg_load:        ld      a, (fg_v)
                ld      c, a
                and     7
                add     a, a
                ld      b, a
                add     a, high TABBASE
                ld      (fgl_d + 1), a
                ld      a, c
                rrca
                rrca
                rrca
                and     1                       ; the mirror
                inc     b
                dec     b
                jr      z, fgl_k
                or      2                       ; shifted
fgl_k:          call    fg_mk
                ld      (fgl_c + 1), hl
                ld      a, (fg_ent + 1)
                ld      d, a
                ld      a, (fg_ent + 2)
                ld      e, a
                ld      a, (fg_ent)
                call    far_seek
                ld      ix, SPRBUF_A
fgl_d:          ld      d, 0                    ; (patched)
                ld      b, d                    ; (the hi table's page)
                inc     b
                ld      e, high TABBASE
                ld      a, 4
fgl_p:          push    af
                push    ix
                call    fg_rows
fgl_c:          call    0                       ; (patched: the kind's code)
                pop     ix
                inc     ix
                pop     af
                dec     a
                jr      nz, fgl_p
                ret

; fg_mk: A = kind (0-3 the reads: a plane's rows, one template per byte column; 4 the step: a row's 4 planes shifted
; one bit, sla / rl (ix + p + 4c)) -> HL = its code for width fg_ent+3, made unless the tag (the buffer's first byte)
; says it is. The code loops over B' rows (add ix, DE'); the reads keep C = 0, or the shift's carry (lo | the
; previous byte's hi, hi the next carry), the last column gets C.
fg_mk:          add     a, a
                add     a, a
                ld      e, a
                ld      d, 0
                ld      hl, fg_kt
                add     hl, de
                ld      e, (hl)
                inc     hl
                ld      d, (hl)                 ; DE = the buffer: tag, code
                inc     hl
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a                    ; HL = the template (0: the step)
                ld      (fgk_t), hl
                ld      a, (fg_ent + 3)
                ex      de, hl
                cp      (hl)
                inc     hl
                ret     z
                dec     hl
                ld      (hl), a
                inc     hl
                push    hl                      ; (the result, and the loop's start)
                ex      de, hl                  ; DE = the code
                ld      b, a                    ; w
                ld      hl, (fgk_t)
                ld      a, h
                or      l
                jr      z, fgk_st
                push    hl
                pop     iy                      ; IY = the template: step, displacement index, length, first,
                ld      a, 0x0e                 ; ld c, 0
                ld      (de), a
                inc     de
                xor     a
                ld      (de), a
                inc     de
                bit     7, (iy+0)
                jr      z, fgk_d
                ld      a, b                    ; (descending: the mirror's columns)
                dec     a
                add     a, a
                add     a, a
fgk_d:          add     a, (iy+3)
                ld      c, a                    ; C = the displacement
fgk_c:          push    bc
                push    iy
                pop     hl
                ld      bc, 5
                add     hl, bc
                ld      c, (iy+2)
                ld      b, 0
                push    de
                ldir
                pop     hl
                ld      c, (iy+1)
                add     hl, bc
                pop     bc
                ld      (hl), c
                ld      a, c
                add     a, (iy+0)
                ld      c, a
                djnz    fgk_c
                ld      a, (fg_ent + 3)         ; ld (ix + last), c
                add     a, a
                add     a, a
                and     (iy+4)
                ld      c, a
                ld      a, 0xdd
                ld      (de), a
                inc     de
                ld      a, 0x71
                ld      (de), a
                inc     de
                ld      a, c
                jr      fgk_x
fgk_st:         ld      c, 0                    ; the step: per plane sla (ix + p), then rl (ix + p + 4c) up to c = w
fgk_p:          ld      a, (fg_ent + 3)
                inc     a
                ld      b, a
                ld      l, c
                ld      h, 0x26
fgk_b:          ld      a, 0xdd
                ld      (de), a
                inc     de
                ld      a, 0xcb
                ld      (de), a
                inc     de
                ld      a, l
                ld      (de), a
                inc     de
                ld      a, h
                ld      (de), a
                inc     de
                ld      h, 0x16
                ld      a, l
                add     a, 4
                ld      l, a
                djnz    fgk_b
                inc     c
                ld      a, c
                cp      4
                jr      c, fgk_p
                jr      fgk_y                   ; (the step: the tail only)
fgk_x:          ld      (de), a
                inc     de
fgk_y:          ld      hl, fgk_tl              ; exx / add ix, de / dec b / exx / jp nz, start / ret
                ld      bc, 6
                ldir
                pop     hl
                ex      de, hl
                ld      (hl), e
                inc     hl
                ld      (hl), d
                inc     hl
                ld      (hl), 0xc9
                ex      de, hl
                ret
fgk_tl:         db      0xd9, 0xdd, 0x19, 0x05, 0xd9, 0xc2
; the kinds: the buffer, the template: the displacement's step, its index in the bytes, their length, its first
; value (+ 4 (w - 1) when descending), a mask for the last write's (ld (ix + 4w AND mask), c), the bytes for one column
fg_kt:          dw      fg_c0, fgt_0, fg_c1, fgt_1, fg_c2, fgt_2, fg_c3, fgt_3, fg_c4, 0
fgt_0:          db      4, 4, 5, 0, 0xff                ; in a, (RD_DATA) / ld (ix + d), a
                db      0xdb, RD_DATA, 0xdd, 0x77, 0
fgt_1:          db      -4, 7, 8, 0, 0xff               ; in a, (RD_DATA) / ld l, a / ld h, e / ld a, (hl) (reversed) /
                db      0xdb, RD_DATA, 0x6f, 0x63, 0x7e, 0xdd, 0x77, 0  ; ld (ix + d), a
fgt_2:          db      4, 8, 11, 0, 0xff               ; in a, (RD_DATA) / ld l, a / ld h, d / ld a, (hl) / or c /
                db      0xdb, RD_DATA, 0x6f, 0x62, 0x7e, 0xb1, 0xdd, 0x77, 0, 0x24, 0x4e   ; ld (ix + d), a / inc h /
                                                ; ld c, (hl): lo | the carry, hi the next carry
fgt_3:          db      -4, 11, 14, 4, 0                ; the columns from the right: the carry is the lo part of the
                db      0xdb, RD_DATA, 0x6f, 0x63, 0x7e, 0x6f, 0x60, 0x7e, 0xb1, 0xdd, 0x77, 0, 0x62, 0x4e
                                                ; column right of it: in a, (RD_DATA) / ld l, a / ld h, e /
                                                ; ld a, (hl) / ld l, a / ld h, b / ld a, (hl) / or c /
                                                ; ld (ix + d + 4), a / ld h, d / ld c, (hl): hi | the carry, lo
                                                ; the next carry; the last write column 0

; fg_put: HL = fg_pa or fg_pb: the buffer (variant fg_v of fg_id) as that table's next entry, its slot, the bar
fg_put:         ld      (fp_ps), hl
                ld      a, (hl)
                ld      (fp_pg), a
                inc     hl
                ld      e, (hl)
                inc     hl
                ld      d, (hl)
                ld      hl, (fg_n)
                ld      bc, 4
                add     hl, bc
                add     hl, de
                jr      nc, fp_fit              ; (address + bytes + 4 > 0xFFFF: the next page)
                ld      hl, fp_pg
                inc     (hl)
                ld      de, 0
                ld      hl, (fg_n)
                add     hl, bc
fp_fit:         ld      (fp_ad), de
                ex      de, hl                  ; DE = the next entry
                ld      hl, (fp_ps)
                ld      a, (fp_pg)
                ld      (hl), a
                inc     hl
                ld      (hl), e
                inc     hl
                ld      (hl), d
                ld      hl, (fg_id)             ; the slot: id * 64 + v * 4
                add     hl, hl
                add     hl, hl
                add     hl, hl
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      a, (fg_v)
                add     a, a
                add     a, a
                or      l
                ld      e, a
                ld      d, h
                ld      a, FS_PAGE
                call    far_seek
                dec     c
                ld      a, (fp_pg)
                out     (c), a
                ld      a, (fp_ad + 1)
                out     (c), a
                ld      a, (fp_ad)
                out     (c), a
                ld      a, (fp_pg)              ; the entry: ow, h, the byte count, the cell buffer
                ld      de, (fp_ad)
                call    far_seek
                dec     c
                ld      a, (fg_st)
                rrca
                rrca
                out     (c), a
                ld      a, (fg_ent + 4)
                out     (c), a
                ld      hl, (fg_n)
                out     (c), l
                out     (c), h
                ld      a, l                    ; 64 q + r bytes
                and     0x3f
                ld      (fp_r), a
                add     hl, hl
                add     hl, hl
                ld      a, h
                ld      hl, SPRBUF_A
                or      a
                jr      z, fp_rest
fp_q:           call    fg_o64
                dec     a
                jr      nz, fp_q
fp_rest:        ld      a, (fp_r)
                add     a, a
                ld      e, a
                ld      d, 0
                push    hl
                ld      hl, fg_o64e
                sbc     hl, de                  ; (carry clear: add a, a of r < 64)
                ld      (fp_j + 1), hl
                pop     hl
fp_j:           call    0                       ; (patched: the last r OUTIs)
                jp      ff_prog
fg_o64:         rept    64
                outi
                endm
fg_o64e:        ret
