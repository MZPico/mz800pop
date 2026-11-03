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
MASKBUF         equ     0x0c00          ; lay_piece masked modes: inverted mask block (rows x n, <= 512)
DATABUF         equ     0x0e00          ; plane block
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
V_EDGE          equ     0x0837          ; copy mode: 1 = merge the edge columns through V_LM/V_RM
V_LM            equ     0x0838          ; bits of the first visible column taken from the piece
V_RM            equ     0x0839          ; same for the last visible column
V_OLDL          equ     0x083a          ; compose bytes saved before the row copy
V_OLDR          equ     0x083b
V_DST           equ     0x083c          ; 16-bit: compose dst of the current plane's first row
V_POFF          equ     0x083e          ; 16-bit: far offset of the current plane's first (visible) row
V_NB            equ     0x0840          ; bytes per row laid
V_PART          equ     0x0841          ; 0 = rows contiguous in far memory (n == w), else re-seek every row
V_ROWS          equ     0x0842          ; row counter
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
lay_piece16:    bit     7, d
                jr      z, lp16pos
                ; negative top: clip the first -DE rows away, piece starts at row 0
                ld      (V_MODE), a
                ld      a, b
                ld      (V_PX), a
                xor     a
                ld      (V_PY), a
                ld      a, e
                neg
                ld      (V_SKIP), a     ; rows skipped at the top of the piece
                jr      lp_common
lp16pos:        ld      c, e
lay_piece:      ld      (V_MODE), a
                ld      a, b
                ld      (V_PX), a
                ld      a, c
                ld      (V_PY), a
                xor     a
                ld      (V_SKIP), a
lp_common:      ld      a, (V_PX)       ; negative byte column: clip the left columns away
                bit     7, a
                jr      z, lp_cs0
                neg
                ld      (V_CSKIP), a
                xor     a
                ld      (V_PX), a
                jr      lp_cs1
lp_cs0:         xor     a
                ld      (V_CSKIP), a
lp_cs1:
                ; plane size = w*h
                ld      a, (ix+4)
                ld      e, (ix+3)
                call    mul8
                ld      (V_PSIZE), hl
                ; rows
                ld      a, (V_PY)
                ld      hl, CRY
                cp      (hl)
                jr      nc, lpr0
                ld      a, (hl)
lpr0:           ld      (V_R0), a
                ld      a, (V_PY)
                ld      l, a
                ld      h, 0
                ld      a, (ix+4)
                ld      e, a
                ld      a, (V_SKIP)
                ld      d, a
                ld      a, e
                sub     d
                ret     c               ; entirely above the screen
                ret     z
                ld      e, a
                ld      d, 0
                add     hl, de          ; py + visible height
                ld      a, (CRY)
                ld      e, a
                ld      a, (CRH)
                add     a, e
                ld      e, a
                ld      d, 0
                or      a
                sbc     hl, de
                jr      c, lpr1a
                ld      a, e
                jr      lpr1
lpr1a:          add     hl, de
                ld      a, l
lpr1:           ld      (V_R1), a
                ld      hl, V_R0
                sub     (hl)
                ret     z
                ret     c
                ld      (V_N), a        ; rows to do
                ; cols
                ld      a, (V_PX)
                ld      hl, CRX
                cp      (hl)
                jr      nc, lpc0
                ld      a, (hl)
lpc0:           ld      (V_C0), a
                ld      a, (ix+3)
                ld      hl, V_CSKIP
                sub     (hl)
                ret     c
                ret     z
                ld      hl, V_PX
                add     a, (hl)
                ld      c, a
                ld      a, (CRX)
                ld      hl, CRW
                add     a, (hl)
                cp      c
                jr      c, lpc1
                ld      a, c
lpc1:           ld      (V_C1), a
                ld      hl, V_C0
                sub     (hl)
                ret     z
                ret     c
                ld      c, a            ; n bytes per row
                ; far offset of the first row's first byte within plane 0 data: (r0-py+skip)*w + (c0-px) [+ psize if mask plane first]
                ld      a, (V_R0)
                ld      hl, V_PY
                sub     (hl)
                ld      hl, V_SKIP
                add     a, (hl)
                ld      e, (ix+3)
                push    bc
                call    mul8
                pop     bc
                ld      a, (V_C0)
                ld      de, V_PX
                ex      de, hl
                sub     (hl)
                ex      de, hl
                ld      e, a
                ld      a, (V_CSKIP)
                add     a, e
                ld      e, a
                ld      d, 0
                add     hl, de
                ld      (V_ROWOFF), hl  ; offset of mask row (if mask) / plane 0 row
                ; dst = COMPOSE + (r0-CRY)*8 + (c0-CRX)
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
                ex      de, hl          ; DE = dst row (plane 0)
                ld      (V_DST), de
                ld      a, c
                ld      (V_NB), a
                add     a, a
                ld      e, a
                ld      d, 0
                ld      hl, inr_table   ; INI chain for n bytes
                add     hl, de
                ld      a, (hl)
                ld      (lp_ini+1), a
                inc     hl
                ld      a, (hl)
                ld      (lp_ini+2), a
                ld      a, CW
                sub     c
                ld      (lpc_stride+1), a
                ld      (lpm_stride+1), a
                ld      a, (ix+3)
                sub     c
                ld      (V_PART), a     ; 0: every row fully visible -> rows are contiguous in far memory
                ld      a, (V_MODE)
                or      a
                jp      nz, lpmasked
                ; copy mode: pixels outside the image extent (partial first/last byte column) keep the
                ; compose contents. V_LM/V_RM = bits taken from the piece in the first/last visible column.
                xor     a
                ld      (V_EDGE), a
                ld      a, (ix+5)
                and     2
                jr      z, lpc_planes
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
                jr      z, lpc_planes   ; both 0xff: plain copy
                ld      a, 1
                ld      (V_EDGE), a
                ld      a, (V_LM)
                inc     a
                jr      nz, lpc_planes  ; left edge partial too: general (slow) merge
                ld      a, 2            ; right edge only: fast path
                ld      (V_EDGE), a
                ld      a, (V_RM)
                ld      (lpc_rm+1), a
                cpl
                ld      (lpc_nrm+1), a
; fast copy (no edge or a right edge only): per row INIR the visible bytes (the last one merged through
; V_RM), drop the rest of the piece's row (V_PART bytes, cheaper than a seek), row counter in A'
lpc_planes:     ld      a, (V_PART)              ; bytes of a row past the visible ones: read and dropped
                ld      (lpf_dk+1), a
                ld      (lpf_dk2+1), a
                ld      a, (V_NB)
                ld      (lpf_n+1), a
                dec     a
                ld      (lpf_n1+1), a
                ld      b, a
                ld      a, CW
                sub     b
                dec     a
                ld      (lpf_st+1), a           ; CW - n
                ld      a, (V_RM)
                ld      (lpf_rm+1), a
                ld      (lpf_lrm+1), a
                cpl
                ld      (lpf_nrm+1), a
                ld      (lpf_lnrm+1), a
                ld      a, (V_LM)               ; left edge (V_EDGE 1): the first byte through LM, or LM & RM
                ld      b, a                    ; when the row is one byte
                ld      a, (V_NB)
                dec     a
                ld      a, b
                jr      nz, lpf_lm1
                ld      hl, V_RM
                and     (hl)
lpf_lm1:        ld      (lpf_llm+1), a
                cpl
                ld      (lpf_lnlm+1), a
                ld      a, (V_NB)
                sub     2
                jr      nc, lpf_lm2
                xor     a
lpf_lm2:        ld      (lpf_lmid+1), a          ; middle bytes
                xor     a
                ld      (V_PLANE), a
                ld      hl, (V_ROWOFF)
                ld      a, (ix+5)
                and     1
                jr      z, lpf_p
                ld      de, (V_PSIZE)
                add     hl, de
lpf_p:          ld      (V_POFF), hl
                call    far_seek_entry
                ld      hl, (V_DST)
                ld      c, RD_DATA
                ld      d, 0
lpf_st:         ld      e, 0                    ; patched: CW - n
                ld      a, (V_N)
                ex      af, af'
                ld      a, (V_EDGE)
                or      a
                jr      z, lpf_row
                cp      1
                jp      z, lpf_lrow
                jp      lpf_rrow
lpf_row:
lpf_n:          ld      b, 0                    ; patched: n
                inir
                add     hl, de
lpf_dk:         ld      a, 0                    ; patched: V_PART
                or      a
                jr      z, lpf_d1
                ld      b, a
lpf_d0:         in      a, (c)
                djnz    lpf_d0
lpf_d1:         ex      af, af'
                dec     a
                jr      z, lpf_pe
                ex      af, af'
                jp      lpf_row
lpf_rrow:
lpf_n1:         ld      b, 0                    ; patched: n - 1
                ld      a, b
                or      a
                jr      z, lpf_r1
                inir
lpf_r1:         in      a, (c)
lpf_rm:         and     0                       ; patched: RM (bits from the piece)
                ld      b, a
                ld      a, (hl)
lpf_nrm:        and     0                       ; patched: ~RM
                or      b
                ld      (hl), a
                inc     hl
                add     hl, de
lpf_dk2:        ld      a, 0                    ; patched: V_PART
                or      a
                jr      z, lpf_d3
                ld      b, a
lpf_d2:         in      a, (c)
                djnz    lpf_d2
lpf_d3:         ex      af, af'
                dec     a
                jr      z, lpf_pe
                ex      af, af'
                jp      lpf_rrow
lpf_lrow:       in      a, (c)                  ; first byte
lpf_llm:        and     0                       ; patched: LM (or LM & RM)
                ld      b, a
                ld      a, (hl)
lpf_lnlm:       and     0                       ; patched: ~that
                or      b
                ld      (hl), a
                inc     hl
                ld      a, (V_NB)
                dec     a
                jr      z, lpf_l3
lpf_lmid:       ld      b, 0                    ; patched: n - 2
                ld      a, b
                or      a
                jr      z, lpf_l2
                inir
lpf_l2:         in      a, (c)                  ; last byte
lpf_lrm:        and     0                       ; patched: RM
                ld      b, a
                ld      a, (hl)
lpf_lnrm:       and     0                       ; patched: ~RM
                or      b
                ld      (hl), a
                inc     hl
lpf_l3:         add     hl, de
                ld      a, (lpf_dk+1)
                or      a
                jr      z, lpf_l5
                ld      b, a
lpf_l4:         in      a, (c)
                djnz    lpf_l4
lpf_l5:         ex      af, af'
                dec     a
                jr      z, lpf_pe
                ex      af, af'
                jp      lpf_lrow
lpf_pe:         ld      hl, (V_DST)
                ld      de, COMPOSE_PLANE
                add     hl, de
                ld      (V_DST), hl
                ld      a, (V_PLANE)
                inc     a
                ld      (V_PLANE), a
                cp      4
                ret     z
                ld      hl, (V_POFF)
                ld      de, (V_PSIZE)
                add     hl, de
                jp      lpf_p
lpc_gen:        xor     a
                ld      (V_PLANE), a
                ld      hl, (V_ROWOFF)
                ld      a, (ix+5)       ; flags bit0: skip the mask plane
                and     1
                jr      z, lpc_plane
                ld      de, (V_PSIZE)
                add     hl, de
lpc_plane:      ld      (V_POFF), hl
                call    far_seek_entry
                ld      a, (V_N)
                ld      (V_ROWS), a
                ld      hl, (V_DST)
lpc_row:        ld      a, (V_EDGE)
                or      a
                jr      z, lpc_r1
                cp      2
                jr      nz, lpc_slow
                ; right edge only: DE -> last byte of the row
                ld      a, (V_NB)
                dec     a
                add     a, l
                ld      e, a
                ld      d, h
                jr      nc, lpc_f1
                inc     d
lpc_f1:         ld      a, (de)
lpc_nrm:        and     0               ; patched: ~RM  (old bits outside the extent)
                ex      af, af'
                ld      c, RD_DATA
                call    lp_ini
                ex      af, af'
                ld      b, a
                ld      a, (de)
lpc_rm:         and     0               ; patched: RM
                or      b
                ld      (de), a
                jr      lpc_r2
lpc_slow:       ld      a, (hl)
                ld      (V_OLDL), a
                push    hl
                ld      a, (V_NB)
                dec     a
                add     a, l
                ld      l, a
                jr      nc, lpc_r0
                inc     h
lpc_r0:         ld      a, (hl)
                ld      (V_OLDR), a
                pop     hl
                push    hl
                ld      c, RD_DATA
                call    lp_ini
                pop     de              ; DE = row start
                call    lp_merge
                jr      lpc_r2
lpc_r1:         ld      c, RD_DATA
                call    lp_ini          ; HL = row start + n
lpc_r2:
lpc_stride:     ld      c, 0            ; patched: CW - n
                ld      b, 0
                add     hl, bc
                ld      a, (V_PART)
                or      a
                jr      z, lpc_r3
                push    hl              ; partial rows: seek the next row (stride w)
                ld      hl, (V_POFF)
                ld      e, (ix+3)
                ld      d, 0
                add     hl, de
                ld      (V_POFF), hl
                call    far_seek_entry
                pop     hl
lpc_r3:         ld      a, (V_ROWS)
                dec     a
                ld      (V_ROWS), a
                jr      nz, lpc_row
                ; next plane
                ld      hl, (V_DST)
                ld      de, COMPOSE_PLANE
                add     hl, de
                ld      (V_DST), hl
                ld      a, (V_PLANE)
                inc     a
                ld      (V_PLANE), a
                cp      4
                ret     z
                ld      hl, (V_ROWOFF)  ; plane base = rowoff [+ psize if mask first] + plane*psize
                ld      de, (V_PSIZE)
                ld      c, a
                ld      a, (ix+5)
                and     1
                add     a, c
                ld      b, a
lpc_pb:         add     hl, de
                djnz    lpc_pb
                jp      lpc_plane
lp_ini:         jp      0               ; patched: inr_n
; lp_merge: DE = row start; restore the bits outside the extent from V_OLDL/V_OLDR through V_LM/V_RM
lp_merge:       ld      a, (V_OLDL)     ; dst = old ^ ((old ^ dst) & LM)
                ex      de, hl
                xor     (hl)
                ld      b, a
                ld      a, (V_LM)
                and     b
                ld      b, a
                ld      a, (V_OLDL)
                xor     b
                ld      (hl), a
                ld      a, (V_NB)
                dec     a
                add     a, l
                ld      l, a
                jr      nc, lp_mg1
                inc     h
lp_mg1:         ld      a, (V_OLDR)
                xor     (hl)
                ld      b, a
                ld      a, (V_RM)
                and     b
                ld      b, a
                ld      a, (V_OLDR)
                xor     b
                ld      (hl), a
                ex      de, hl
                ret

; masked modes: the mask block (rows x n) is read once into MASKBUF and inverted; for mode 1 each plane
; block is read into DATABUF; rows are combined with the cm1/cm2/cm3 chains:
;   1 masked: dst = (dst & ~m) | data     2 black: dst &= ~m     3 mono: dst |= m where the colour bit is set, else &= ~m
lpmasked:       ld      a, (V_NB)       ; block size: rows * n, or (rows - 1) * w + n read in one go when the
                ld      e, a            ; rows are partial (one RAM-disk seek instead of one per row) and it fits
                ld      a, (V_N)
                call    mul8            ; HL = rows * n  (mul8: HL = A*E)
                xor     a
                ld      (lpm_skip+1), a
                ld      (lpm_skip2+1), a
                ld      a, (V_PART)
                or      a
                jr      z, lpm_sz
                ld      a, (V_N)
                dec     a
                ld      e, (ix+3)
                call    mul8
                ld      a, (V_NB)
                ld      e, a
                ld      d, 0
                add     hl, de          ; (rows - 1) * w + n
                ld      de, 513
                or      a
                sbc     hl, de
                add     hl, de
                jr      nc, lpm_rn      ; too big for the buffers: row by row, compacted
                ld      (lpb_len), hl
                ld      a, (V_PART)
                ld      (lpm_skip+1), a
                ld      (lpm_skip2+1), a
                jr      lpm_sz
lpm_rn:         ld      a, (V_NB)
                ld      e, a
                ld      a, (V_N)
                call    mul8
lpm_sz:         push    hl
                ld      hl, (V_ROWOFF)
                ld      de, MASKBUF
                call    lp_block
                pop     hl              ; (the mask plane is stored inverted: used as read)
                ; chain for this mode / n
                ld      a, (V_MODE)
                ld      hl, cm1_table
                cp      1
                jr      z, lpm_t
                ld      hl, cm2_table
lpm_t:          ld      a, (V_NB)
                add     a, a
                ld      e, a
                ld      d, 0
                add     hl, de
                ld      a, (hl)
                ld      (lpm_call+1), a
                inc     hl
                ld      a, (hl)
                ld      (lpm_call+2), a
                xor     a
                ld      (V_PLANE), a
                ld      hl, (V_ROWOFF)
                ld      de, (V_PSIZE)
                add     hl, de
                ld      (V_POFF), hl    ; plane 0 block
lpm_plane:      ld      a, (V_MODE)
                cp      1
                jr      nz, lpm_nodata
                ; mode 1: combine straight from the RAM-disk stream (no plane block); a row's unused bytes
                ; (a piece clipped at the sides) are read and dropped
                ld      a, (V_NB)
                add     a, a
                ld      e, a
                ld      d, 0
                ld      hl, cmx_table
                add     hl, de
                ld      a, (hl)
                ld      (lpx_call+1), a
                inc     hl
                ld      a, (hl)
                ld      (lpx_call+2), a
                ld      a, (lpm_stride+1)
                ld      (lpx_st+1), a
                ld      a, (lpm_skip+1)
                ld      (lpx_sk+1), a
                ld      a, (V_PART)
                ld      (lpx_dk+1), a
                ld      hl, (V_POFF)
                call    far_seek_entry
                ld      hl, (V_DST)
                ld      de, MASKBUF
                ld      c, RD_DATA
                ld      a, (V_N)
lpx_row:        ex      af, af'
lpx_call:       call    0               ; patched: cmx_n
lpx_st:         ld      a, 0            ; patched: CW - n
                add     a, l
                ld      l, a
                jr      nc, lpx_1
                inc     h
lpx_1:
lpx_sk:         ld      a, 0            ; patched: mask row skip
                add     a, e
                ld      e, a
                jr      nc, lpx_2
                inc     d
lpx_2:
lpx_dk:         ld      b, 0            ; patched: data bytes to drop (w - n)
                ld      a, b
                or      a
                jr      z, lpx_3
lpx_d:          in      a, (c)
                djnz    lpx_d
lpx_3:          ex      af, af'
                dec     a
                jr      nz, lpx_row
                jp      lpm_pnext
lpm_nodata:     cp      3
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
                ld      bc, MASKBUF
                ld      de, DATABUF
                ld      a, (V_N)
lpm_row:        ex      af, af'
lpm_call:       call    0               ; patched: cm?_n  (HL, DE, BC advance by n)
                push    bc
lpm_stride:     ld      c, 0            ; patched: CW - n
                ld      b, 0
                add     hl, bc
                pop     bc
lpm_skip:       ld      a, 0            ; patched: source row skip (w - n for strided blocks, else 0)
                add     a, c
                ld      c, a
                jr      nc, lpm_k1
                inc     b
lpm_k1:         ld      a, e
lpm_skip2:      add     a, 0            ; patched: the same
                ld      e, a
                jr      nc, lpm_k2
                inc     d
lpm_k2:         ex      af, af'
                dec     a
                jr      nz, lpm_row
lpm_pnext:      ; next plane
                ld      hl, (V_DST)
                ld      de, COMPOSE_PLANE
                add     hl, de
                ld      (V_DST), hl
                ld      hl, (V_POFF)
                ld      de, (V_PSIZE)
                add     hl, de
                ld      (V_POFF), hl
                ld      hl, V_PLANE
                inc     (hl)
                ld      a, (hl)
                cp      4
                jp      nz, lpm_plane
                ret

; lp_block: read V_N rows of V_NB bytes from far offset HL (entry IX) into DE; rows are contiguous in far
; memory when V_PART = 0, else spaced (ix+3) apart.
lp_block:       ld      (lpb_dst), de
                ld      a, (lpm_skip+1)
                or      a
                jr      nz, lpb_strided
                ld      a, (V_PART)
                or      a
                jr      nz, lpb_part
                call    far_seek_entry
                ld      a, (V_NB)
                ld      e, a
                ld      a, (V_N)
                call    mul8            ; HL = rows * n (<= 512)
lpb_read:       ex      de, hl
                ld      hl, (lpb_dst)
                ld      c, RD_DATA
                ld      a, d
                or      a
                jr      z, lpb_rem
lpb_full:       ld      b, 0
                inir                    ; 256 bytes
                dec     a
                jr      nz, lpb_full
lpb_rem:        ld      a, e
                or      a
                ret     z
                ld      b, a
                inir
                ret
lpb_part:       ld      (lpb_off), hl
                ld      a, (V_N)
lpb_prow:       ex      af, af'
                ld      hl, (lpb_off)
                call    far_seek_entry
                ld      hl, (lpb_off)
                ld      e, (ix+3)
                ld      d, 0
                add     hl, de
                ld      (lpb_off), hl
                ld      hl, (lpb_dst)
                ld      c, RD_DATA
                call    lp_ini
                ld      (lpb_dst), hl
                ex      af, af'
                dec     a
                jr      nz, lpb_prow
                ret
lpb_strided:    call    far_seek_entry  ; partial rows read whole: rows lie w apart in the buffer too
                ld      hl, (lpb_len)
                jr      lpb_read
lpb_dst:        dw      0
lpb_off:        dw      0
lpb_len:        dw      0               ; bytes of a strided block: (rows - 1) * w + n

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

; restore_shadow: compose rect <- shadow (background without fore pieces)
restore_shadow: ld      a, (CRW)
                add     a, a
                ld      e, a
                ld      d, 0
                ld      hl, inr_table
                add     hl, de
                ld      a, (hl)
                ld      (rs_call+1), a
                inc     hl
                ld      a, (hl)
                ld      (rs_call+2), a
                ld      a, (CRH)
                ld      (rs_rows+1), a
                ld      a, (CRW)
                ld      c, a
                ld      a, CW
                sub     c
                ld      (rs_stride+1), a        ; compose row advance after the INI chain: CW - CRW
                xor     a
                ld      (V_PLANE), a
                ld      hl, (V_COMPOSE)
                ld      (V_ROWOFF), hl
rsplane:        ld      a, (V_PLANE)
                call    shadow_addr             ; DE = shadow address of the rect's first row
                ld      hl, (V_ROWOFF)
                ld      a, SHADOW_PAGE          ; (the page stays: each row only sets the address)
                out     (RD_PAGE), a
                ld      c, RD_ADDR              ; C: RD_ADDR, RD_DATA = RD_ADDR - 1
rs_rows:        ld      a, 0
                ex      af, af'
rsrow:          ld      b, d
                out     (c), e
                dec     c
rs_call:        call    0                       ; INI x CRW into HL
                inc     c
                ld      a, e                    ; next shadow row
                add     a, 40
                ld      e, a
                jr      nc, rsde
                inc     d
rsde:
rs_stride:      ld      a, 0                    ; patched: CW - CRW
                add     a, l
                ld      l, a
                jr      nc, rsnc
                inc     h                       ; next compose row
rsnc:           ex      af, af'
                dec     a
                jr      z, rsrow_x
                ex      af, af'
                jp      rsrow
rsrow_x:        ex      af, af'
                ld      hl, (V_ROWOFF)
                ld      bc, COMPOSE_PLANE
                add     hl, bc
                ld      (V_ROWOFF), hl
                ld      hl, V_PLANE
                inc     (hl)
                ld      a, (hl)
                cp      4
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
