; ---------------------------------------------------------------- planar graphics kernel (M1)
; Screen: 320x200, 4 planes, 40 bytes per line, bit 0 = leftmost pixel.
; Compose buffer: 4 planes x CW(8) bytes x CH(64) rows at COMPOSE; plane stride 512, row stride 8.
; Sprite buffer: interleaved cells [p0 p1 p2 p3] per byte column, row stride ow*4.

CW              equ     8
CH              equ     64
COMPOSE_A       equ     0xa000          ; 2048 bytes each, 512-byte aligned
COMPOSE_B       equ     0xa800
COMPOSE_PLANE   equ     512
SPRBUF_A        equ     0xb000          ; 2048 bytes each (8 cells x 64 rows x 4): images up to 7 bytes wide + shift
SPRBUF_B        equ     0xb800
TABBASE         equ     0x8000          ; page 0 = bit reverse, pages 2s/2s+1 = lo/hi shift tables (behind the VRAM window)
ROWTMP          equ     0x9f70          ; sprite fetch row temp (16 bytes), behind the VRAM window
ROWTMP2         equ     0x9f80
MASKBUF         equ     0x0c00          ; lay_piece masked modes: the inverted mask rows at the compose rows' offsets
                                        ; (MASKBUF + (dst & 0x1FF), 512 bytes; 512-byte aligned)
                if MASKBUF and 0x1ff
                .error MASKBUF must be 512-byte aligned (lmx_ent: the mask's low address byte is the compose row's)
                endif
V_COMPOSE       equ     0x0832          ; 16-bit: current compose buffer
VRAM            equ     0x8000          ; the VRAM window is mapped (IN E0) only inside blit and the test programs'
                                        ; video_init; otherwise 0x8000-0x9FFF is RAM holding the renderer's tables and lists
PORT_WF         equ     0xcc

; variables
CRX             equ     0x0810          ; compose rect: byte column, row, width (bytes), height
CRY             equ     0x0811
CRW             equ     0x0812
CRH             equ     0x0813
V_W             equ     0x0814
V_H             equ     0x0815
V_OW            equ     0x0816
V_SHPAGE        equ     0x0817
V_MIRROR        equ     0x0818
V_XB            equ     0x0819
V_R0            equ     0x0820
V_R1            equ     0x0821
V_C0            equ     0x0822
V_C1            equ     0x0823
V_N             equ     0x0824
V_PX            equ     0x0825
V_PY            equ     0x0826
V_MODE          equ     0x0827
V_PLANE         equ     0x0828
V_PSIZE         equ     0x082a          ; 16-bit w*h of the piece being laid
V_SPRP          equ     0x082c          ; 16-bit pointer to the sprite descriptor in use
V_IYSAVE        equ     0x082e
V_ROWOFF        equ     0x0830          ; 16-bit
V_MONO          equ     0x0834          ; mono blit colour (lay_piece mode 3)
V_SKIP          equ     0x0835          ; lay_piece16: piece rows hidden above the screen
V_CSKIP         equ     0x0836          ; lay_piece: piece byte columns hidden left of the screen
V_LM            equ     0x0838          ; bits of the first visible column taken from the piece
V_RM            equ     0x0839          ; same for the last visible column
V_DST           equ     0x083c          ; 16-bit: compose dst of the current plane's first row
V_POFF          equ     0x083e          ; 16-bit: far offset of the current plane's first (visible) row
V_NB            equ     0x0840          ; bytes per row laid
V_PART          equ     0x0841          ; 0 = rows contiguous in far memory (n == w), else re-seek every row
V_FBSP          equ     0x0844          ; fill_black: saved SP
DIR             equ     0x7800          ; directory, 8 bytes per image id: page, addr hi, addr lo, width bytes,
                                        ; height, flags (bit0 mask plane first, bit1 partial edge column),
                                        ; extent mask of the first column, extent mask of the last column

; sprite descriptor layout
SD_BUF          equ     0               ; 2: cell buffer
SD_OW           equ     2               ; row width in bytes (w+1)
SD_H            equ     3
SD_XB           equ     4               ; screen byte column
SD_Y            equ     5               ; screen row
SD_X            equ     6               ; 2: pixel x
SD_FRAME        equ     8
SD_MIRROR       equ     9
SD_OXB          equ     10              ; previous rect
SD_OY           equ     11
SD_OW2          equ     12
SD_OH           equ     13
SD_DX           equ     14
SD_LKEY         equ     15              ; last fetched frame
SD_LKEY2        equ     16              ; last fetched mirror<<3 | shift
SD_CR           equ     17              ; 4: compose rect (xb, y, w, h) of the last compose
SD_COMPOSE      equ     21              ; 2: this character's compose buffer
SD_YH           equ     23              ; high byte of the row (0, or 0xFF for a sprite starting above the screen)
SD_SIZE         equ     24

; ---------------------------------------------------------------- tables
; tables_init (src/m1/tables.asm) builds the bit-reverse and shift tables at TABBASE. The game (GAME_OVL) runs it
; from the level-start overlay (src/m4/gstart.asm); the test programs include it here.
                if not defined GAME_OVL
                include "../m1/tables.asm"
                endif

; ---------------------------------------------------------------- sprite fetch
; In: IX = directory entry, HL = sprite descriptor, DE = pixel x (0..319), A = mirror (0/1)
spr_fetch:      ld      (V_SPRP), hl
                ld      (V_MIRROR), a
                push    hl
                pop     iy
                ld      (iy+SD_X), e
                ld      (iy+SD_X+1), d
                ld      (iy+SD_MIRROR), a
                ld      a, (ix+3)
                ld      (V_W), a
                inc     a
                ld      (V_OW), a
                ld      (iy+SD_OW), a
                ld      a, (ix+4)
                ld      (V_H), a
                ld      (iy+SD_H), a
                ld      a, e
                and     7
                ld      c, a            ; shift
                ld      a, e
                srl     d
                rra
                srl     d
                rra
                srl     d
                rra
                ld      (iy+SD_XB), a
                ; shift table page and routine
                ld      a, c
                add     a, a
                add     a, high TABBASE
                ld      (V_SHPAGE), a
                ld      a, (V_W)
                dec     a
                add     a, a
                ld      hl, V_MIRROR
                add     a, (hl)
                add     a, a
                ld      b, a
                ld      a, c
                or      a
                jr      nz, sfnz
                inc     b               ; s == 0 variant
sfnz:           ld      l, b
                ld      h, 0
                add     hl, hl
                ld      bc, shr_table
                add     hl, bc
                ld      a, (hl)
                ld      (shr_call+1), a
                inc     hl
                ld      a, (hl)
                ld      (shr_call+2), a
                ; seek to the frame data (planes 0..3, no mask)
                ld      hl, 0
                call    far_seek_entry
                ; patch the row-read and shift parameters into the inner loop
                ld      a, (V_W)
                ld      (sf_bc+2), a            ; B of `ld bc,(w<<8)|RD_DATA`
                ld      hl, ROWTMP
                ld      a, (V_MIRROR)
                or      a
                jr      z, sfpd
                ld      a, (V_W)
                dec     a
                add     a, l
                ld      l, a                    ; mirror: source pointer at the last byte
sfpd:           ld      (sf_de+1), hl
                ld      a, (V_SHPAGE)
                ld      (sf_h+1), a
                ld      (sf_b+1), a
                ld      a, (V_OW)
                add     a, a
                add     a, a
                ld      (sf_stride+1), a
                ld      l, (iy+SD_BUF)
                ld      h, (iy+SD_BUF+1)
                push    hl
                pop     iy                      ; IY = buffer (plane 0)
                ld      a, (V_H)
                ld      (sf_rows+1), a
                ld      a, 4
                ld      (V_PLANE), a            ; planes left
sfplane:
sf_rows:        ld      a, 0                    ; patched: h
                ex      af, af'                 ; A' = row counter
sfrow:          ld      hl, ROWTMP
sf_bc:          ld      bc, RD_DATA             ; patched: B = w
                inir
sf_de:          ld      de, 0                   ; patched: ROWTMP (or its last byte)
sf_h:           ld      h, 0                    ; patched: lo-table page
sf_b:           ld      b, 0                    ; patched: lo-table page (mirror variants)
shr_call:       call    0                       ; patched: shift routine
sf_stride:      ld      bc, 0                   ; patched: ow*4
                add     iy, bc
                ex      af, af'
                dec     a
                jr      z, sfrow_x
                ex      af, af'
                jp      sfrow
sfrow_x:         ex      af, af'
                ; next plane: IY = buffer + plane index
                ld      hl, V_PLANE
                dec     (hl)
                ret     z
                ld      a, 4
                sub     (hl)                    ; plane index 1..3
                ld      c, a
                ld      b, 0
                push    ix
                ld      ix, (V_SPRP)
                ld      l, (ix+SD_BUF)
                ld      h, (ix+SD_BUF+1)
                pop     ix
                add     hl, bc
                push    hl
                pop     iy
                jp      sfplane

; ---------------------------------------------------------------- sprite draw into compose
; In: HL = sprite descriptor. Clips to the compose rect.
spr_draw:       push    hl
                pop     iy
                xor     a
                call    sd_bounds               ; (returns from spr_draw when nothing is visible)
                ld      a, (V_PX)               ; the row loop keeps its pointers in registers: patch the
                ld      (sd_px+1), a            ; cells per row and both row advances
                ld      (sd_dst+1), a           ; compose: back to the row start, then CW on
                ld      c, a
                add     a, a
                add     a, a
                ld      c, a
                ld      a, (sd_stride+1)
                sub     c
                ld      (sd_stride+1), a        ; source: (ow - px) * 4
                ld      a, (V_N)
                exx
                ld      b, a                    ; B' = rows left
                exx
                ld      hl, (V_ROWOFF)
sdrow:
sd_px:          ld      c, 0                    ; patched: cells per row
sdcell:         ld      a, (hl)                 ; (the cell buffers are 4-aligned: inc l inside a cell)
                inc     l
                or      (hl)
                inc     l
                or      (hl)
                inc     l
                or      (hl)
                jr      z, sdempty      ; nothing to draw in this cell
                cpl
                ld      b, a            ; B = inverted mask
                dec     l
                dec     l
                dec     l
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                inc     hl
                ld      a, d
                sub     6
                ld      d, a
                inc     e
                dec     c
                jp      nz, sdcell
                jr      sdrowend
sdempty:        inc     hl
                inc     e
                dec     c
                jp      nz, sdcell
sdrowend:
sd_stride:      ld      bc, 0           ; patched: sd_bounds ow*4, then (ow - px) * 4
                add     hl, bc
                ld      a, e            ; (the last cell's inc e may have wrapped E: the carry comes from
sd_dst:         sub     0               ; the row start + CW; patched: px)
                add     a, CW
                ld      e, a
                jr      nc, sd_nc
                inc     d
sd_nc:          exx
                dec     b
                exx
                jp      nz, sdrow
                ret

; sd_bounds: IY = sprite descriptor, A = extra byte columns right of the image (the shadow's XOR copy: 1): its visible
; part in the compose rect: V_R0, V_N (rows), V_C0, V_PX (cells per row), V_ROWOFF (source of the first cell), DE = its
; compose address, sd_stride patched. Nothing visible: returns from the caller.
sd_bounds:      ld      (sdb_x+1), a
                ; rows: r0 = max(y, CRY); r1 = min(y + h, CRY + CRH), y signed 16-bit (SD_YH:SD_Y)
                ld      a, (CRY)
                ld      e, a
                ld      a, (iy+SD_YH)
                or      a
                jr      z, sdr0a
                bit     7, a
                jp      z, sdb_none     ; y >= 256: below the screen
                jr      sdr0b           ; y < 0 -> r0 = CRY
sdr0a:          ld      a, (iy+SD_Y)
                cp      e               ; 0 <= y < CRY -> r0 = CRY
                jr      nc, sdr0c
sdr0b:          ld      a, e
sdr0c:          ld      (V_R0), a
                ld      l, (iy+SD_Y)
                ld      h, (iy+SD_YH)
                ld      e, (iy+SD_H)
                ld      d, 0
                add     hl, de          ; y + h (signed)
                bit     7, h
                jp      nz, sdb_none    ; entirely above the screen
                ld      a, (CRY)
                ld      e, a
                ld      a, (CRH)
                add     a, e            ; CRY + CRH (<= 200)
                ld      e, a
                ld      d, 0
                or      a
                sbc     hl, de          ; y + h - (CRY + CRH)
                jr      c, sdr1a        ; y + h smaller
                ld      a, e
                jr      sdr1
sdr1a:          add     hl, de
                ld      a, l
sdr1:           ld      (V_R1), a
                ld      hl, V_R0
                sub     (hl)
                jp      z, sdb_none
                jp      c, sdb_none
                ld      (V_N), a        ; row count (reuse V_N temporarily)
                ; cols: c0 = max(xb, CRX); c1 = min(xb + ow, CRX + CRW), xb a signed byte column
                ld      a, (iy+SD_XB)
                bit     7, a
                jr      nz, sdc0a       ; left of the screen
                ld      hl, CRX
                cp      (hl)
                jr      nc, sdc0
sdc0a:          ld      a, (CRX)
sdc0:           ld      (V_C0), a
                ld      a, (iy+SD_XB)
                add     a, (iy+SD_OW)
sdb_x:          add     a, 0            ; patched: extra columns
                bit     7, a
                jp      nz, sdb_none    ; ends left of the screen
                or      a
                jp      z, sdb_none
                ld      c, a
                ld      a, (CRX)
                ld      hl, CRW
                add     a, (hl)
                cp      c
                jr      c, sdc1
                ld      a, c
sdc1:           ld      (V_C1), a
                ld      hl, V_C0
                sub     (hl)
                jp      z, sdb_none
                jp      c, sdb_none
                ld      (V_PX), a       ; cell count per row
                ; src = buf + ((r0-y)*ow + (c0-xb))*4 ; dst = COMPOSE + (r0-CRY)*8 + (c0-CRX)
                ld      a, (V_R0)
                sub     (iy+SD_Y)
                ld      e, (iy+SD_OW)
                call    mul8            ; HL = (r0-y)*ow
                ld      a, (V_C0)
                sub     (iy+SD_XB)
                ld      e, a
                ld      d, 0
                add     hl, de
                add     hl, hl
                add     hl, hl          ; *4
                ld      e, (iy+SD_BUF)
                ld      d, (iy+SD_BUF+1)
                add     hl, de
                ld      (V_ROWOFF), hl  ; src row pointer
                ld      a, (iy+SD_OW)
                add     a, a
                add     a, a
                ld      (sd_stride+1), a
                ld      a, (V_R0)
                ld      hl, CRY
                sub     (hl)
                ld      l, a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl          ; (r0-CRY)*8, 16-bit
                ld      a, (V_C0)
                push    hl
                ld      hl, CRX
                sub     (hl)
                pop     hl
                ld      e, a
                ld      d, 0
                add     hl, de
                ld      de, (V_COMPOSE)
                add     hl, de
                ex      de, hl          ; DE = dst
                ret
sdb_none:       pop     hl              ; (the caller's return)
                ret
; HL = A * E (8x8 -> 16), over the bits of E (put the smaller factor in E: a width); B, D, E destroyed
mul8:           ld      d, 0
                ld      b, e
                ld      e, a            ; DE = A
                ld      hl, 0
mul8l:          srl     b
                jr      nc, mul8n
                add     hl, de          ; (keeps Z from the shift)
mul8n:          ret     z
                sla     e
                rl      d
                jp      mul8l

; ---------------------------------------------------------------- tile piece into compose
; In: IX = directory entry, A = mode (0 copy, 1 masked, 2 black, 3 mono), B = px (byte column), C = py (top row)
; Clips to the compose rect. Copy mode streams rows straight from the RAM disk into the buffer.
; lay_piece16: same but DE = signed 16-bit top row (pieces may start above the screen); rows above 0 are skipped.
; (M8a part 20: the clip in registers, the products by repeated addition: w <= 8)
lay_piece16:    ld      (V_MODE), a
                bit     7, d
                jr      z, lp16pos
                xor     a               ; negative top: the first -DE rows clipped away, the piece starts at row 0
                sub     e
                ld      (V_SKIP), a
                ld      c, 0
                jr      lp_common
lp16pos:        ld      c, e
lay_piece:      ld      (V_MODE), a
                xor     a
                ld      (V_SKIP), a
lp_common:      xor     a               ; a negative byte column: the left columns clipped away
                bit     7, b
                jr      z, lp_cs0
                sub     b
                ld      b, 0
lp_cs0:         ld      (V_CSKIP), a
                ld      a, b
                ld      (V_PX), a
                ld      a, c
                ld      (V_PY), a
                ; rows: R0 = max(py, CRY), R1 = min(py + h - skip, CRY + CRH)
                ld      a, (V_SKIP)
                ld      d, a
                ld      a, (ix+4)
                sub     d
                ret     c               ; entirely above the screen
                ret     z
                ld      e, a            ; the visible height
                ld      hl, (CRY)       ; L = CRY
                ld      a, (CRH)
                add     a, l
                ld      h, a            ; H = CRY + CRH
                ld      a, c
                add     a, e
                jr      c, lpr1a        ; (past row 255: below the rect)
                cp      h
                jr      c, lpr1
lpr1a:          ld      a, h
lpr1:           ld      h, a            ; H = R1
                ld      a, c
                cp      l
                jr      nc, lpr0
                ld      a, l
lpr0:           ld      (V_R0), a
                ld      l, a            ; L = R0
                ld      a, h
                sub     l
                ret     z
                ret     c
                ld      (V_N), a        ; rows to do
                ; columns: C0 = max(px, CRX), C1 = min(px + w - cskip, CRX + CRW)
                ld      a, (V_CSKIP)
                ld      d, a
                ld      a, (ix+3)
                sub     d
                ret     c
                ret     z
                add     a, b
                ld      e, a            ; px + the visible width
                ld      a, (CRX)
                ld      h, a
                ld      a, (CRW)
                add     a, h
                cp      e
                jr      c, lpc1
                ld      a, e
lpc1:           ld      (V_C1), a
                ld      e, a
                ld      a, b
                cp      h
                jr      nc, lpc0
                ld      a, h
lpc0:           ld      (V_C0), a
                ld      d, a            ; D = C0
                ld      a, e
                sub     d
                ret     z
                ret     c
                ld      c, a            ; n bytes per row
                ld      (V_NB), a
                ; dst = V_COMPOSE + (R0 - CRY) * 8 + (C0 - CRX)
                ld      a, d
                sub     h
                ld      e, a            ; C0 - CRX
                ld      a, (CRY)
                ld      h, a
                ld      a, l
                sub     h               ; R0 - CRY (0..63)
                ld      l, a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      a, e
                or      l               ; (the low 3 bits are free)
                ld      l, a
                ld      de, (V_COMPOSE)
                add     hl, de
                ld      (V_DST), hl
                ; the far offset of the first visible row's first byte (of the mask, or of plane 0):
                ; (R0 - py + skip) * w + (C0 - px + cskip); the plane size w * h
                ld      a, (V_C0)
                sub     b
                ld      hl, V_CSKIP
                add     a, (hl)
                ld      (lp_col+1), a
                ld      a, (V_R0)
                ld      hl, V_PY
                sub     (hl)
                ld      hl, V_SKIP
                add     a, (hl)
                ld      e, a
                ld      d, 0
                ld      b, (ix+3)
                ld      a, b
                sub     c
                ld      (V_PART), a     ; w - n: bytes dropped after each row
                ld      a, CW
                sub     c
                ld      (lpm_stride+1), a
                ld      a, b            ; w
lp_col:         ld      hl, 0           ; patched: the column offset (H = 0)
lp_mr:          add     hl, de
                djnz    lp_mr
                ld      (V_ROWOFF), hl
                ld      e, (ix+4)       ; d = 0
                ld      b, a
                ld      hl, 0
lp_mh:          add     hl, de
                djnz    lp_mh
                ld      (V_PSIZE), hl
                ld      a, (V_MODE)
                or      a
                jp      nz, lpmasked
                ; copy mode: pixels outside the image extent (partial first/last byte column) keep the
                ; compose contents. V_LM/V_RM = bits taken from the piece in the first/last visible column.
                ld      a, (ix+5)
                and     2
                jr      z, lpc_fast
                ld      a, 0xff
                ld      (V_LM), a
                ld      (V_RM), a
                ld      a, (V_CSKIP)
                or      a
                jr      nz, lpe1        ; first piece column clipped away
                ld      a, (V_C0)
                ld      hl, V_PX
                cp      (hl)
                jr      nz, lpe1
                ld      a, (ix+6)
                ld      (V_LM), a
lpe1:           ld      a, (V_PX)
                add     a, (ix+3)
                ld      hl, V_CSKIP
                sub     (hl)            ; screen column after the piece's last column
                ld      hl, V_C1
                cp      (hl)
                jr      nz, lpe2
                ld      a, (ix+7)
                ld      (V_RM), a
lpe2:           ld      a, (V_LM)
                ld      hl, V_RM
                and     (hl)
                inc     a
                jr      z, lpc_fast   ; both 0xff: plain copy
                ld      a, (V_LM)
                inc     a
                jr      nz, lpc_ledge   ; left edge partial too: the lle loop
                call    lre_patch       ; right edge only: the lre chain (the last byte through V_RM)
                ld      hl, lre_ent
                jr      lpc_go
; plain copy (M8a part 20): each plane's rows by the INI row chain (lr_ent), V_PART bytes dropped after each row
lpc_fast:       call    lr_patch
                ld      hl, lr_ent
lpc_go:         ld      (lcf_call+1), hl
                ld      hl, (V_DST)
                ld      (lcf_dst+1), hl
                ld      hl, (V_PSIZE)
                ld      (lcf_ps+1), hl
                ld      a, (V_N)
                ld      (lcf_n+1), a
                ld      a, 4
                ex      af, af'
                ld      hl, (V_ROWOFF)
                ld      a, (ix+5)       ; flags bit0: skip the mask plane
                and     1
                jr      z, lcf_0
                ld      de, (V_PSIZE)
                add     hl, de
lcf_0:          ld      e, (ix+2)
                ld      d, (ix+1)
                add     hl, de
                ld      a, (ix+0)
                adc     a, 0            ; A:HL = the plane's first row in the RAM disk
lcf_p:          out     (RD_PAGE), a
                ld      b, h
                ld      c, RD_ADDR
                out     (c), l
                push    af
                push    hl
lcf_dst:        ld      hl, 0           ; patched: the plane's first compose row
lcf_n:          ld      d, 0            ; patched: rows
                dec     c               ; RD_DATA
lcf_call:       call    lr_ent          ; patched: lr_ent, or lre_ent (a right edge)
lcf_pe:         ld      hl, lcf_dst+2
                inc     (hl)
                inc     (hl)            ; the next plane (+ COMPOSE_PLANE)
                pop     hl
                pop     af
lcf_ps:         ld      de, 0           ; patched: the plane size
                add     hl, de
                adc     a, 0
                ex      af, af'
                dec     a
                ret     z
                ex      af, af'
                jp      lcf_p
; a left edge (rare): the lle loop, through the same plane loop
lpc_ledge:      ld      a, (V_RM)
                ld      (lle_lrm+1), a
                cpl
                ld      (lle_lnrm+1), a
                ld      a, (V_NB)
                ld      b, a
                ld      a, CW
                sub     b
                ld      (lle_st+1), a   ; 8 - n
                ld      a, (V_PART)
                ld      (lle_k+1), a
                dec     b               ; the first byte through LM, or LM & RM when the row is one byte
                ld      a, (V_LM)
                jr      nz, lle_p1
                ld      hl, V_RM
                and     (hl)
lle_p1:         ld      (lle_llm+1), a
                cpl
                ld      (lle_lnlm+1), a
                ld      a, b
                ld      (lle_n1+1), a   ; n - 1
                ld      hl, lle_ent
                jp      lpc_go
; lle_ent: D rows into HL (8-byte rows), C = RD_DATA: the first byte through LM, the middle ones as read, the last
; through RM; k = V_PART bytes dropped after each row
lle_ent:        in      a, (c)
lle_llm:        and     0               ; patched: LM (or LM & RM)
                ld      b, a
                ld      a, (hl)
lle_lnlm:       and     0               ; patched: ~that
                or      b
                ld      (hl), a
                inc     hl
lle_n1:         ld      a, 0            ; patched: n - 1
                or      a
                jr      z, lle_l3
                dec     a
                jr      z, lle_l2
                ld      b, a
                inir
lle_l2:         in      a, (c)          ; the last byte
lle_lrm:        and     0               ; patched: RM
                ld      b, a
                ld      a, (hl)
lle_lnrm:       and     0               ; patched: ~RM
                or      b
                ld      (hl), a
                inc     hl
lle_l3:
lle_k:          ld      a, 0            ; patched: k
                or      a
                jr      z, lle_l5
                ld      b, a
lle_l4:         in      a, (c)
                djnz    lle_l4
lle_l5:
lle_st:         ld      a, 0            ; patched: 8 - n
                add     a, l
                ld      l, a
                jr      nc, lle_l6
                inc     h
lle_l6:         dec     d
                jr      nz, lle_ent
                ret

; masked modes (M8a part 20): the mask rows are read once into MASKBUF at the compose rows' own offsets (MASKBUF +
; (dst & 0x1FF): an 8-byte row stride, a compose byte's mask byte has the same low address byte), inverted as stored;
; mode 1 then combines each plane's rows straight from the RAM-disk stream (the lmx chain), modes 2 / 3 from MASKBUF
; (the cm2 / cm3 chains):
;   1 masked: dst = (dst & ~m) | data     2 black: dst &= ~m     3 mono: dst |= m where the colour bit is set, else &= ~m
lpmasked:       call    lr_patch        ; the row chains for n = V_NB bytes a row, V_PART bytes dropped after each
                ld      hl, (V_DST)
                ld      a, h
                and     1
                or      high MASKBUF
                ld      h, a
                ld      (lpm_mask), hl  ; the first row's mask
                ld      hl, (V_ROWOFF)
                call    far_seek_entry
                ld      hl, (lpm_mask)
                ld      a, (V_N)
                ld      d, a
                ld      c, RD_DATA
                call    lr_ent          ; the mask rows into MASKBUF
lpm_mend:       ld      a, (V_MODE)
                cp      1
                jr      z, lpx_set
                xor     a
                ld      (V_PLANE), a
                ld      a, (lpm_stride+1)
                ld      (lpm_skip+1), a ; the mask rows' stride is the compose rows' (8)
                ld      hl, cm2_table   ; mode 2 (mode 3 picks its chain per plane)
                ld      a, (V_NB)
                add     a, a
                ld      e, a
                ld      d, 0
                add     hl, de
                ld      a, (hl)
                ld      (lpm_call+1), a
                inc     hl
                ld      a, (hl)
                ld      (lpm_call+2), a
                jr      lpm_plane
                ; mode 1: combine straight from the RAM-disk stream; the plane loop in registers (A' planes left,
                ; A:HL the plane's RAM-disk page and address; dst, mask, rows and the plane size patched in)
lpx_set:        ld      hl, (V_DST)
                ld      (lpx_dst+1), hl
                ld      hl, (lpm_mask)
                ld      (lpx_msk+1), hl
                ld      hl, (V_PSIZE)
                ld      (lpx_ps+1), hl
                ld      a, (V_N)
                ld      (lpx_n+1), a
                ld      a, 4
                ex      af, af'
                ld      hl, (V_ROWOFF)
                ld      de, (V_PSIZE)
                add     hl, de          ; plane 0
                ld      e, (ix+2)
                ld      d, (ix+1)
                add     hl, de
                ld      a, (ix+0)
                adc     a, 0
lpx_plane:      out     (RD_PAGE), a
                ld      b, h
                ld      c, RD_ADDR
                out     (c), l
                push    af
                push    hl
lpx_dst:        ld      hl, 0           ; patched: the plane's first compose row
lpx_msk:        ld      de, 0           ; patched: its mask
lpx_n:          ld      b, 0            ; patched: rows
                call    lmx_ent
lpx_pe:         ld      hl, lpx_dst+2
                inc     (hl)
                inc     (hl)            ; the next plane (+ COMPOSE_PLANE)
                pop     hl
                pop     af
lpx_ps:         ld      de, 0           ; patched: the plane size
                add     hl, de
                adc     a, 0
                ex      af, af'
                dec     a
                ret     z
                ex      af, af'
                jp      lpx_plane
lpm_plane:      ld      a, (V_MODE)
                cp      3
                jr      nz, lpm_rows
                ; mono: chain = cm3 (set) if the colour has this plane's bit, else cm2 (clear)
                ld      a, (V_MONO)
                ld      hl, V_PLANE
                inc     (hl)
                ld      b, (hl)
                dec     (hl)
lpm_sh:         rrca
                djnz    lpm_sh
                ld      hl, cm3_table
                jr      c, lpm_t2
                ld      hl, cm2_table
lpm_t2:         ld      a, (V_NB)
                add     a, a
                ld      e, a
                ld      d, 0
                add     hl, de
                ld      a, (hl)
                ld      (lpm_call+1), a
                inc     hl
                ld      a, (hl)
                ld      (lpm_call+2), a
lpm_rows:       ld      hl, (V_DST)
                ld      bc, (lpm_mask)
                ld      a, (V_N)
lpm_row:        ex      af, af'
lpm_call:       call    0               ; patched: cm?_n  (HL, BC advance by n)
                push    bc
lpm_stride:     ld      c, 0            ; patched: CW - n
                ld      b, 0
                add     hl, bc
                pop     bc
lpm_skip:       ld      a, 0            ; patched: CW - n (the mask rows' stride)
                add     a, c
                ld      c, a
                jr      nc, lpm_k1
                inc     b
lpm_k1:         ex      af, af'
                dec     a
                jr      nz, lpm_row
                ; next plane
                ld      hl, (V_DST)
                ld      de, COMPOSE_PLANE
                add     hl, de
                ld      (V_DST), hl
                ld      hl, V_PLANE
                inc     (hl)
                ld      a, (hl)
                cp      4
                jp      nz, lpm_plane
                ret
lpm_mask:       dw      0               ; MASKBUF + (V_DST & 0x1FF): the mask of the first row

; ---------------------------------------------------------------- row chains (M8a part 20)
; lr_patch: set the chains below for rows of n = V_NB bytes (1..8) with k = V_PART bytes (0..7: pieces up to 8 bytes
; wide) read and dropped after each row (a piece clipped at the sides); kept while n and k stay the same
lr_patch:       ld      a, (V_NB)
                ld      hl, lr_kn
                cp      (hl)
                jr      z, lrp_k
                ld      (hl), a
                ld      b, a
                ld      a, CW
                sub     b               ; 8 - n
                ld      (lr_k+1), a
                ld      c, a
                inc     a
                ld      (lmx_k+1), a    ; 9 - n
                ld      a, c
                add     a, a
                ld      e, a
                ld      d, 0
                ld      hl, lr_8
                add     hl, de
                ld      (lr_ent+1), hl  ; lr_n = lr_8 + 2 (8 - n): every row
                ld      (lr_lp+1), hl
                ld      (lr_lp2+1), hl
                ld      a, c
                add     a, a
                add     a, a
                add     a, a
                add     a, c            ; 9 (8 - n)
                ld      e, a
                ld      hl, lmx_8
                add     hl, de
                ld      (lmx_ent+1), hl ; lmx_n = lmx_8 + 9 (8 - n)
                ld      a, 256 + lmx_8 - lmx_lp - 2
                add     a, e
                ld      (lmx_lp+1), a   ; (djnz lmx_n)
                ld      a, 256 + lmx_8 - lmx_lp2 - 2
                add     a, e
                ld      (lmx_lp2+1), a
lrp_k:          ld      a, (V_PART)
                ld      hl, lr_kk
                cp      (hl)
                ret     z
                ld      (hl), a
                add     a, a
                ld      e, a            ; 2 k
                ld      d, 0
                ld      hl, lr_k
                or      a
                sbc     hl, de
                ld      (lr_dj+1), hl   ; k drops before the next row
                ld      hl, lmx_step
                sbc     hl, de
                ld      (lmx_dj+1), hl
                ret
lr_kn:          db      0xff            ; the n of the chains' patch
lr_kk:          db      0xff            ; the k

; lr_ent: D rows of n bytes into HL (8-byte rows in a 512-byte aligned buffer), C = RD_DATA; k bytes dropped after
; each row (the rest of a clipped row and the next one's start)
lr_ent:         jp      0               ; patched: lr_n
lr_8:           rept    8
                ini
                endm
lr_dj:          jp      0               ; patched: lr_k - 2 k
                rept    7
                in      a, (RD_DATA)
                endm
lr_k:           ld      a, 0            ; (patched: 8 - n) the next row
                add     a, l
                ld      l, a
                jr      c, lr_pg
                dec     d
lr_lp:          jp      nz, 0           ; patched: lr_n
                ret
lr_pg:          inc     h
                dec     d
lr_lp2:         jp      nz, 0           ; patched: lr_n
                ret
; lre_patch: the lre chain for rows of n = V_NB bytes whose last one keeps the compose bits outside V_RM, k = V_PART
; dropped after each row (copy mode, a piece's partial last column visible; patched at every use)
lre_patch:      ld      a, (V_RM)
                ld      (lre_rm+1), a
                cpl
                ld      (lre_nrm+1), a
                ld      a, (V_NB)
                ld      b, a
                ld      a, CW
                sub     b               ; 8 - n
                ld      (lre_k+1), a
                add     a, a
                ld      e, a
                ld      d, 0
                ld      hl, lre_8
                add     hl, de
                ld      (lre_ent+1), hl ; lre_8 + 2 (8 - n): n - 1 INIs
                ld      (lre_lp+1), hl
                ld      (lre_lp2+1), hl
                ld      a, (V_PART)
                add     a, a
                ld      e, a
                ld      hl, lre_k
                or      a
                sbc     hl, de
                ld      (lre_dj+1), hl
                ret
; lre_ent: as lr_ent, the row's last byte merged: dst = (dst & ~RM) | (data & RM)
lre_ent:        jp      0               ; patched: lre_n
lre_8:          rept    7
                ini
                endm
                in      a, (RD_DATA)
lre_rm:         and     0               ; patched: RM
                ld      b, a
                ld      a, (hl)
lre_nrm:        and     0               ; patched: ~RM
                or      b
                ld      (hl), a
                inc     hl
lre_dj:         jp      0               ; patched: lre_k - 2 k
                rept    7
                in      a, (RD_DATA)
                endm
lre_k:          ld      a, 0            ; (patched: 8 - n) the next row
                add     a, l
                ld      l, a
                jr      c, lre_pg
                dec     d
lre_lp:         jp      nz, 0           ; patched: lre_n
                ret
lre_pg:         inc     h
                dec     d
lre_lp2:        jp      nz, 0           ; patched: lre_n
                ret
; lmx_ent: B rows of n bytes: HL = compose row, DE = its mask (E = L), dst = (dst & ~m) | data from the RAM disk;
; k bytes dropped after each row
lmx_ent:        jp      0               ; patched: lmx_n
lmx_8:          rept    7
                ld      a, (de)
                and     (hl)
                ld      c, a
                in      a, (RD_DATA)
                or      c
                ld      (hl), a
                inc     l
                inc     e
                endm
                ld      a, (de)         ; the row's last byte
                and     (hl)
                ld      c, a
                in      a, (RD_DATA)
                or      c
                ld      (hl), a
lmx_dj:         jp      0               ; patched: lmx_step - 2 k
                rept    7
                in      a, (RD_DATA)
                endm
lmx_step:       ld      a, l
lmx_k:          add     a, 0            ; patched: 9 - n (the next row)
                ld      l, a
                ld      e, a
                jr      c, lmx_pg
lmx_lp:         djnz    lmx_lp          ; patched: lmx_n
                ret
lmx_pg:         inc     h
                inc     d
lmx_lp2:        djnz    lmx_lp2         ; patched: lmx_n
                ret

; ---------------------------------------------------------------- black fill of a sub-rect of the compose buffer
; In: B = px, C = py, D = w (bytes), E = h  (screen coordinates); clipped to the compose rect
fill_black:     ld      a, b
                ld      (V_PX), a
                ld      a, c
                ld      (V_PY), a
                ld      a, d
                ld      (V_W), a
                ld      a, e
                ld      (V_H), a
                ; rows
                ld      a, (V_PY)
                ld      hl, CRY
                cp      (hl)
                jr      nc, fbr0
                ld      a, (hl)
fbr0:           ld      (V_R0), a
                ld      a, (V_PY)
                ld      l, a
                ld      h, 0
                ld      a, (V_H)
                ld      e, a
                ld      d, 0
                add     hl, de
                ld      a, (CRY)
                ld      e, a
                ld      a, (CRH)
                add     a, e
                ld      e, a
                ld      d, 0
                or      a
                sbc     hl, de
                jr      c, fbr1a
                ld      a, e
                jr      fbr1
fbr1a:          add     hl, de
                ld      a, l
fbr1:           ld      hl, V_R0
                sub     (hl)
                ret     z
                ret     c
                ld      (V_N), a
                ; cols
                ld      a, (V_PX)
                ld      hl, CRX
                cp      (hl)
                jr      nc, fbc0
                ld      a, (hl)
fbc0:           ld      (V_C0), a
                ld      a, (V_PX)
                ld      hl, V_W
                add     a, (hl)
                ld      c, a
                ld      a, (CRX)
                ld      hl, CRW
                add     a, (hl)
                cp      c
                jr      c, fbc1
                ld      a, c
fbc1:           ld      hl, V_C0
                sub     (hl)
                ret     z
                ret     c
                ld      (fb_n), a
                add     a, a
                ld      e, a
                ld      d, 0
                ld      hl, fill_table
                add     hl, de
                ld      a, (hl)
                ld      (fb_call+1), a
                inc     hl
                ld      a, (hl)
                ld      (fb_call+2), a
                ld      a, (V_R0)
                ld      hl, CRY
                sub     (hl)
                ld      l, a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl          ; (r0-CRY)*8, 16-bit
                ld      a, (V_C0)
                push    hl
                ld      hl, CRX
                sub     (hl)
                pop     hl
                ld      e, a
                ld      d, 0
                add     hl, de
                ld      de, (V_COMPOSE)
                add     hl, de          ; HL = dst row, plane 0
                ld      a, (fb_n)
                cp      CW
                jr      nz, fbrow
                ; full-width rows are contiguous: PUSH fill (5.5 T/byte), interrupts off while SP is inside the buffer
                di
                ld      (V_FBSP), sp
                ld      a, (V_N)
                add     a, a
                add     a, a            ; pushes per plane = rows*4 (<= 256; 0 means 256)
                neg
                ld      e, a
                ld      d, 0
                ld      a, (V_N)
                and     0x3f            ; rows (64 -> 0 -> pushes = 256 -> entry offset 0)
                push    hl
                ld      hl, pushrows
                add     hl, de          ; entry = pushrows + 256 - rows*4
                ld      (fbp_entry+1), hl
                pop     hl
                ld      a, 4
fbp_plane:      ld      (fbp_pl), a
                ld      (fbp_hl), hl
                ld      a, (V_N)
                ld      e, a
                ld      d, 0
                ex      de, hl
                add     hl, hl
                add     hl, hl
                add     hl, hl          ; rows*8
                add     hl, de
                ld      sp, hl          ; end of this plane's rows
                ld      de, 0
                ld      ix, fbp_back
fbp_entry:      jp      0               ; patched: pushrows entry
fbp_back:       ld      hl, (fbp_hl)
                inc     h
                inc     h               ; next plane
                ld      a, (fbp_pl)
                dec     a
                jr      nz, fbp_plane
                ld      sp, (V_FBSP)
                ei
                ret
fbp_pl:         db      0
fbp_hl:         dw      0
fb_n:           db      0
fbrow:          push    hl
                ld      c, 4
fbplane:        push    hl
                xor     a
fb_call:        call    0
                pop     hl
                inc     h
                inc     h
                dec     c
                jr      nz, fbplane
                pop     hl
                ld      bc, CW
                add     hl, bc
                ld      a, (V_N)
                dec     a
                ld      (V_N), a
                jr      nz, fbrow
                ret

; ---------------------------------------------------------------- compose -> VRAM
blit:           in      a, (0xe0)       ; map VRAM (and CG-ROM at 0x1000) over 0x8000-0x9FFF for the copy
                ld      a, (CRW)
                add     a, a
                ld      e, a
                ld      d, 0
                ld      hl, blq_table
                add     hl, de
                ld      a, (hl)
                ld      (bl_call+1), a
                inc     hl
                ld      a, (hl)
                ld      (bl_call+2), a
                ld      a, (CRY)
                ld      e, a
                ld      d, 0
                ld      h, d
                ld      l, e
                add     hl, hl
                add     hl, hl
                add     hl, de                  ; *5
                add     hl, hl
                add     hl, hl
                add     hl, hl                  ; *40
                ld      a, (CRX)
                ld      e, a
                add     hl, de
                ld      de, VRAM
                add     hl, de
                ex      de, hl                  ; DE = VRAM dst
                ld      hl, (V_COMPOSE)
                ld      a, (CRH)
                or      a
                jr      z, bl_done
bl_call:        call    0                       ; patched: blq_CRW, rows top to bottom, four planes per row
bl_done:
                in      a, (0xe1)       ; RAM back at 0x8000-0x9FFF
                ret
; blit_flip: blit while the screen is upside down (SDLPoP flip_screen; set_flip patches blit's first instruction into
; a jump here): a playfield rect goes to rows 191 - y, its compose rows taken bottom up so the screen still fills top
; down (the kernel's row step patched for the call); the bottom strip (rows 192-199) as it is
blit_flip:      in      a, (0xe0)
                ld      a, (CRY)
                cp      192
                ld      a, (CRW)
                jp      nc, blit + 5            ; (after blit's `ld a, (CRW)`)
                add     a, a
                ld      e, a
                ld      d, 0
                ld      hl, blq_table
                add     hl, de
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a                    ; the kernel blq_w (8 w + 64 bytes)
                ld      (bf_call + 1), hl
                ld      a, e
                add     a, a
                add     a, a
                add     a, 48
                ld      e, a
                add     hl, de                  ; its compose step from plane 3 to the next row (+ 8 - w - 1536)
                ld      e, (hl)
                inc     hl
                ld      d, (hl)
                push    hl
                push    de
                ex      de, hl
                ld      bc, -16                 ; one row up instead
                add     hl, bc
                ex      de, hl
                ld      (hl), d
                dec     hl
                ld      (hl), e
                ld      a, (CRH)                ; source: the rect's last compose row
                dec     a
                ld      l, a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      de, (V_COMPOSE)
                add     hl, de
                push    hl
                ld      a, (CRY)                ; screen: row 192 - CRY - CRH
                ld      hl, CRH
                add     a, (hl)
                neg
                add     a, 192
                ld      e, a
                ld      d, 0
                ld      h, d
                ld      l, e
                add     hl, hl
                add     hl, hl
                add     hl, de
                add     hl, hl
                add     hl, hl
                add     hl, hl                  ; *40
                ld      a, (CRX)
                ld      e, a
                add     hl, de
                ld      de, VRAM
                add     hl, de
                ex      de, hl
                pop     hl
                ld      a, (CRH)
                or      a
bf_call:        call    nz, 0                   ; patched: blq_CRW
                pop     de                      ; the kernel's step back
                pop     hl
                ld      (hl), d
                dec     hl
                ld      (hl), e
                in      a, (0xe1)
                ret

; ---------------------------------------------------------------- shadow room (clean background) in RAM disk page SHADOW_PAGE
; plane p row y byte x at SHADOW_PAGE : p*8000 + y*40 + x
SHADOW_PAGE     equ     1

; shadow_addr: A = plane (0..3), out DE = p*8000 + CRY*40 + CRX
shadow_addr:    ld      hl, 0
                or      a
                jr      z, sha0
                ld      de, 8000
sha1:           add     hl, de
                dec     a
                jr      nz, sha1
sha0:           ld      a, (CRY)
                ld      e, a
                ld      d, 0
                push    hl
                ld      h, d
                ld      l, e
                add     hl, hl
                add     hl, hl
                add     hl, de
                add     hl, hl
                add     hl, hl
                add     hl, hl                  ; CRY*40
                ld      a, (CRX)
                ld      e, a
                add     hl, de
                pop     de
                add     hl, de
                ex      de, hl
                ret

; restore_shadow: compose rect <- shadow (background without fore pieces). Per row: the row's address, CRW INIs
; (entered by a jump into rs_ini), the next shadow row (+40) and compose row (+CW: no add when CRW = CW); the row
; count in B', the plane count in C'.
restore_shadow: ld      a, (CRW)
                add     a, a
                ld      e, a
                ld      d, 0
                ld      hl, rs_iend
                or      a
                sbc     hl, de
                ld      (rs_jp+1), hl           ; the INI chain's entry for CRW bytes
                ld      a, (CRW)
                ld      hl, 0x18 + 256 * (rs_2 - rs_st - 2)
                sub     CW
                jr      z, rs_w8                ; full rows: jr rs_2 over the compose advance
                ld      hl, 0x7d + 256 * 0xc6   ; ld a, l / add a, CW - CRW
                neg
                ld      (rs_st+2), a
rs_w8:          ld      (rs_st), hl
                ld      a, (CRH)
                ld      (rs_rows+1), a
                ld      hl, (V_COMPOSE)
                ld      (V_ROWOFF), hl
                xor     a
                call    shadow_addr             ; DE = plane 0's address of the rect's first row
                ld      a, SHADOW_PAGE          ; (the page stays: each row only sets the address)
                out     (RD_PAGE), a
                exx
                ld      c, 4                    ; C' = planes left
                exx
rsplane:        push    de
                ld      hl, (V_ROWOFF)
                ld      c, RD_ADDR              ; C: RD_ADDR, RD_DATA = RD_ADDR - 1
rs_rows:        ld      a, 0                    ; patched: CRH
                exx
                ld      b, a                    ; B' = rows left
                exx
rsrow:          ld      b, d
                out     (c), e
                dec     c
rs_jp:          jp      0                       ; patched: rs_iend - 2 * CRW
rs_ini:         ini
                ini
                ini
                ini
                ini
                ini
                ini
                ini
rs_iend:        inc     c
                ld      a, e                    ; next shadow row
                add     a, 40
                ld      e, a
                jr      nc, rs_1
                inc     d
rs_1:
rs_st:          ld      a, l                    ; patched: (CRW = CW) jr rs_2
                add     a, 0                    ; patched: CW - CRW
                ld      l, a
                jr      nc, rs_2
                inc     h                       ; next compose row
rs_2:           exx
                dec     b
                exx
                jp      nz, rsrow
                pop     hl                      ; the next plane: shadow + 8000, compose + COMPOSE_PLANE
                ld      de, 8000
                add     hl, de
                ex      de, hl
                ld      hl, (V_ROWOFF)
                ld      bc, COMPOSE_PLANE
                add     hl, bc
                ld      (V_ROWOFF), hl
                exx
                dec     c
                exx
                jr      nz, rsplane
                ret

; shadow_write: compose rect -> shadow (call after composing a clean background cell)
shadow_write:   ld      a, (CRW)                ; the OUTI chain entry for CRW bytes: otr_end - 2 * CRW
                add     a, a
                ld      e, a
                ld      d, 0
                ld      hl, otr_end
                or      a
                sbc     hl, de
                ld      (sw_n+1), hl
                ld      a, (CRW)
                ld      c, a
                ld      a, CW
                sub     c
                ld      (sw_stride+1), a
                xor     a
                ld      (V_PLANE), a
                ld      hl, (V_COMPOSE)
                ld      (V_ROWOFF), hl
                ld      a, SHADOW_PAGE
                out     (RD_PAGE), a
swplane:        ld      a, (V_PLANE)
                call    shadow_addr     ; DE = shadow address of the first row
                ld      hl, (V_ROWOFF)
                ld      c, RD_ADDR      ; C: RD_ADDR, RD_DATA = RD_ADDR - 1
                ld      a, (CRW)
                cp      CW
                ld      a, (CRH)
                jr      z, sw8row
sw_rows:        ex      af, af'         ; A' = rows left
swrow:          ld      b, d
                out     (c), e          ; row address
                dec     c
sw_n:           call    0               ; patched: OUTI x CRW (HL advances by CRW)
                inc     c
                ld      a, e            ; DE += 40
                add     a, 40
                ld      e, a
                jr      nc, sw_de
                inc     d
sw_de:
sw_stride:      ld      a, 0            ; patched: CW - CRW
                add     a, l
                ld      l, a
                jr      nc, sw_hl
                inc     h
sw_hl:          ex      af, af'
                dec     a
                jr      z, sw_pn
                ex      af, af'
                jp      swrow
sw8row:         ex      af, af'         ; full rows: the compose rows are contiguous
sw8r:           ld      b, d
                out     (c), e
                dec     c
                outi
                outi
                outi
                outi
                outi
                outi
                outi
                outi
                inc     c
                ld      a, e
                add     a, 40
                ld      e, a
                jr      nc, sw8d
                inc     d
sw8d:           ex      af, af'
                dec     a
                jr      z, sw_pn
                ex      af, af'
                jp      sw8r
sw_pn:          ld      hl, (V_ROWOFF)
                ld      bc, COMPOSE_PLANE
                add     hl, bc
                ld      (V_ROWOFF), hl
                ld      hl, V_PLANE
                inc     (hl)
                ld      a, (hl)
                cp      4
                jr      nz, swplane
                ret
otr_8:          outi                    ; OUTI chain: enter at otr_end - 2n for n bytes
                outi
                outi
                outi
                outi
                outi
                outi
                outi
otr_end:        ret
                include "kernel_gen.inc"
