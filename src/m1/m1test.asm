; M1 test: static room from tile pieces, two kid sprites moving with dirty-rect compose + blit.
; Loaded via the emulator CMT hack at 0x3000; the harness fills the RAM disk (pack) and DIR first.
VARS            equ     0x0800
FRAMES          equ     VARS + 0        ; 16-bit VBLN counter (ISR)
LASTTICK        equ     VARS + 2
TICKS           equ     VARS + 4        ; 16-bit tick counter
WAITVBLN        equ     VARS + 6        ; 1 = wait for VBLN before the first blit of a tick
SPR_A           equ     0x0840
SPR_B           equ     0x0860
ROOMMAP         equ     0x0900          ; 30 cells x 2 bytes: bg id, fore id (0xff = none)
VECTAB          equ     0xfe00
STACK           equ     0xfe00
PORT_DMD        equ     0xce
PORT_SCRL       equ     0xcf
PORT_PAL        equ     0xf0
PIOA_CTRL       equ     0xfc
TICK_FRAMES     equ     4

                org     0x3000
start:          di
                ld      sp, STACK
                out     (0xe0), a
                out     (0xe1), a
                in      a, (0xe0)
                call    video_init
                in      a, (0xe1)       ; VRAM window off: the kernel's tables live at 0x8000-0x9FFF
                call    tables_init
                call    room_init
                call    sprites_init
                call    draw_room
                call    irq_init
                ld      hl, (FRAMES)
                ld      (LASTTICK), hl
mainloop:       halt
                ld      hl, (FRAMES)
                ld      de, (LASTTICK)
                or      a
                sbc     hl, de
                ld      a, l
                cp      TICK_FRAMES
                jr      c, mainloop
                ld      hl, (LASTTICK)
                ld      de, TICK_FRAMES
                add     hl, de
                ld      (LASTTICK), hl
                call    tick
                jr      mainloop

; ---------------------------------------------------------------- tick
tick:
ph_tick:        ld      hl, (TICKS)
                inc     hl
                ld      (TICKS), hl
                ld      iy, SPR_A
                call    char_move
ph_fetch_a:     ld      iy, SPR_A
                call    char_fetch
ph_fetch_b:     ld      iy, SPR_B
                call    char_move
                ld      iy, SPR_B
                call    char_fetch
ph_compose_a:   ld      iy, SPR_A
                call    char_compose
ph_compose_b:   ld      iy, SPR_B
                call    char_compose
ph_wait:        ld      a, (WAITVBLN)
                or      a
                call    nz, wait_vbln
ph_blit:        ld      iy, SPR_A
                call    char_blit
                ld      iy, SPR_B
                call    char_blit
ph_end:         ret

; advance animation frame and position of the character at IY
char_move:      ld      a, (iy+SD_FRAME)
                inc     a
                cp      24
                jr      nz, cmf
                ld      a, 16
cmf:            ld      (iy+SD_FRAME), a
                ld      l, (iy+SD_X)
                ld      h, (iy+SD_X+1)
                ld      a, (iy+SD_DX)
                ld      e, a
                rla
                sbc     a, a
                ld      d, a            ; sign extend
                add     hl, de
                ; bounce between 4 and 270
                ld      de, 4
                or      a
                sbc     hl, de
                add     hl, de
                jr      nc, cmlo
                ld      hl, 4
                call    cm_flip
cmlo:           ld      de, 270
                or      a
                sbc     hl, de
                add     hl, de
                jr      c, cmhi
                ld      hl, 270
                call    cm_flip
cmhi:           ld      (iy+SD_X), l
                ld      (iy+SD_X+1), h
                ret
cm_flip:        ld      a, (iy+SD_DX)
                neg
                ld      (iy+SD_DX), a
                ld      a, (iy+SD_MIRROR)
                xor     1
                ld      (iy+SD_MIRROR), a
                ret

; fetch the frame of the character at IY (shifted/mirrored) into its buffer,
; unless the buffer already holds this frame at this shift and facing
char_fetch:     ld      a, (iy+SD_X)
                and     7
                ld      c, a
                ld      a, (iy+SD_MIRROR)
                add     a, a
                add     a, a
                add     a, a
                or      c
                ld      c, a                    ; key2
                ld      a, (iy+SD_FRAME)
                cp      (iy+SD_LKEY)
                jr      nz, cfdo
                ld      a, c
                cp      (iy+SD_LKEY2)
                jr      nz, cfdo
                ld      a, (iy+SD_X)            ; cached: only the byte column changes
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
                ld      l, a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      de, DIR
                add     hl, de
                push    hl
                pop     ix
                ld      e, (iy+SD_X)
                ld      d, (iy+SD_X+1)
                ld      a, (iy+SD_MIRROR)
                push    iy
                pop     hl
                jp      spr_fetch

; compose rect = old rect U new rect, restore background, draw both sprites, fore pieces, blit
char_compose:   ; new rect: xb, y, ow, h
                ld      a, (iy+SD_XB)
                ld      b, a
                ld      a, (iy+SD_OXB)
                cp      b
                jr      c, ccx
                ld      a, b
ccx:            ld      (CRX), a
                ld      a, (iy+SD_Y)
                ld      b, a
                ld      a, (iy+SD_OY)
                cp      b
                jr      c, ccy
                ld      a, b
ccy:            ld      (CRY), a
                ld      a, (iy+SD_XB)
                add     a, (iy+SD_OW)
                ld      b, a
                ld      a, (iy+SD_OXB)
                add     a, (iy+SD_OW2)
                cp      b
                jr      nc, ccw
                ld      a, b
ccw:            cp      41              ; clamp to the screen
                jr      c, ccw2
                ld      a, 40
ccw2:           ld      hl, CRX
                sub     (hl)
                cp      CW + 1
                jr      c, ccw3
                ld      a, CW
ccw3:           ld      (CRW), a
                ld      a, (iy+SD_Y)
                add     a, (iy+SD_H)
                ld      b, a
                ld      a, (iy+SD_OY)
                add     a, (iy+SD_OH)
                cp      b
                jr      nc, cch
                ld      a, b
cch:            cp      201
                jr      c, cch2
                ld      a, 200
cch2:           ld      hl, CRY
                sub     (hl)
                cp      CH + 1
                jr      c, cch3
                ld      a, CH
cch3:           ld      (CRH), a
                ; remember the new rect as old
                ld      a, (iy+SD_XB)
                ld      (iy+SD_OXB), a
                ld      a, (iy+SD_Y)
                ld      (iy+SD_OY), a
                ld      a, (iy+SD_OW)
                ld      (iy+SD_OW2), a
                ld      a, (iy+SD_H)
                ld      (iy+SD_OH), a
                ; keep the rect for the blit, select this character's buffer
                ld      a, (CRX)
                ld      (iy+SD_CR), a
                ld      a, (CRY)
                ld      (iy+SD_CR+1), a
                ld      a, (CRW)
                ld      (iy+SD_CR+2), a
                ld      a, (CRH)
                ld      (iy+SD_CR+3), a
                ld      l, (iy+SD_COMPOSE)
                ld      h, (iy+SD_COMPOSE+1)
                ld      (V_COMPOSE), hl
                push    iy
ph_restore:     call    restore_shadow
ph_draw:        ld      hl, SPR_A
                call    spr_draw
                ld      hl, SPR_B
                call    spr_draw
ph_fore:        call    draw_fore
ph_cdone:       pop     iy
                ret

; blit the character's composed rect from its own buffer
char_blit:      ld      a, (iy+SD_CR)
                ld      (CRX), a
                ld      a, (iy+SD_CR+1)
                ld      (CRY), a
                ld      a, (iy+SD_CR+2)
                ld      (CRW), a
                ld      a, (iy+SD_CR+3)
                ld      (CRH), a
                ld      l, (iy+SD_COMPOSE)
                ld      h, (iy+SD_COMPOSE+1)
                ld      (V_COMPOSE), hl
                jp      blit

wait_vbln:      ld      hl, (FRAMES)
wvl:            ld      de, (FRAMES)
                ld      a, e
                cp      l
                jr      z, wvl
                ret

; ---------------------------------------------------------------- room
; cells: 10 columns x 3 rows, cell = 4 bytes x 63 rows; bg piece bottom-aligned, fore piece at +1 byte
room_init:      ld      hl, ROOMMAP
                ld      b, 30
                ld      c, 0
rinit:          ld      a, c
                and     3
                inc     a               ; bg ids 1..3 (and 4 -> use 1)
                cp      4
                jr      nz, rinit1
                ld      a, 2
rinit1:         ld      (hl), a
                inc     hl
                ld      a, 0xff
                ld      d, c            ; fore piece (pillar, id 4) in cells 3, 7, 16, 25
                ld      e, 0
                ld      a, c
                cp      3
                jr      z, rfore
                cp      7
                jr      z, rfore
                cp      16
                jr      z, rfore
                cp      25
                jr      z, rfore
                ld      a, 0xff
                jr      rfore2
rfore:          ld      a, 4
rfore2:         ld      (hl), a
                inc     hl
                inc     c
                djnz    rinit
                ret

; for every cell intersecting the compose rect: black fill, then lay the bg piece (copy)
restore_bg:     ld      c, 0            ; cell index
rbcell:         push    bc
                call    cell_rect       ; B = px, C = py (D = 4, E = 63)
                call    cell_hits       ; carry = no overlap
                jr      c, rbnext
                push    bc
                ld      d, 4
                ld      e, 63
                call    fill_black
rb_f:           pop     bc
                push    bc
                pop     hl              ; H = px, L = py
                pop     bc
                push    bc
                ld      a, c
                add     a, a
                ld      e, a
                ld      d, 0
                push    hl
                ld      hl, ROOMMAP
                add     hl, de
                ld      a, (hl)         ; bg id
                pop     hl
                call    dir_lookup      ; IX = entry
                ld      a, 63
                sub     (ix+4)
                add     a, l            ; py + 63 - h
                ld      c, a
                ld      b, h
                xor     a               ; copy mode
                call    lay_piece
rb_l:           nop
rbnext:         pop     bc
                inc     c
                ld      a, c
                cp      30
                jr      nz, rbcell
                ret

draw_fore:      ld      c, 0
dfcell:         push    bc
                call    cell_rect
                call    cell_hits
                jr      c, dfnext
                push    bc
                pop     hl
                pop     bc
                push    bc
                ld      a, c
                add     a, a
                ld      e, a
                ld      d, 0
                push    hl
                ld      hl, ROOMMAP + 1
                add     hl, de
                ld      a, (hl)
                pop     hl
                cp      0xff
                jr      z, dfnext
                call    dir_lookup
                ld      a, 63
                sub     (ix+4)
                add     a, l
                ld      c, a
                ld      a, h
                inc     a
                ld      b, a
                ld      a, 1            ; masked
                call    lay_piece
df_l:           nop
dfnext:         pop     bc
                inc     c
                ld      a, c
                cp      30
                jr      nz, dfcell
                ret

; In: C = cell index 0..29. Out: B = px (bytes), C = py (rows)
cell_rect:      ld      a, c
                ld      b, 0
crrow:          cp      10
                jr      c, crdone
                sub     10
                inc     b
                jr      crrow
crdone:         add     a, a
                add     a, a            ; col*4
                ld      e, a
                ld      a, b
                add     a, a
                add     a, a
                add     a, a
                add     a, a
                add     a, a
                add     a, a            ; row*64 (row <= 2)
                sub     b               ; row*63
                ld      c, a
                ld      b, e
                ret

; In: B = px, C = py (cell 4x63). Out: carry set if the cell does not overlap the compose rect
cell_hits:      ld      a, (CRX)
                ld      e, a
                ld      a, b
                add     a, 4
                cp      e
                jr      c, chno         ; px+4 < CRX
                jr      z, chno         ; px+4 == CRX
                ld      a, (CRW)
                add     a, e
                cp      b
                jr      c, chno         ; CRX+CRW < px
                jr      z, chno
                ld      a, (CRY)
                ld      e, a
                ld      a, c
                add     a, 63
                cp      e
                jr      c, chno
                jr      z, chno
                ld      a, (CRH)
                add     a, e
                cp      c
                jr      c, chno
                jr      z, chno
                or      a               ; carry clear: overlap
                ret
chno:           scf
                ret

; In: A = image id. Out: IX = directory entry
dir_lookup:     push    hl
                push    de
                ld      l, a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      de, DIR
                add     hl, de
                push    hl
                pop     ix
                pop     de
                pop     hl
                ret

; draw every cell of the room through the compose buffer
draw_room:      ld      hl, COMPOSE_A
                ld      (V_COMPOSE), hl
                ld      c, 0
drcell:         push    bc
                call    cell_rect
                ld      a, b
                ld      (CRX), a
                ld      a, c
                ld      (CRY), a
                ld      a, 4
                ld      (CRW), a
                ld      a, 63
                ld      (CRH), a
                call    restore_bg
                call    shadow_write            ; clean background into the shadow room
                call    draw_fore
                call    blit
                pop     bc
                inc     c
                ld      a, c
                cp      30
                jr      nz, drcell
                ret

; ---------------------------------------------------------------- sprites
sprites_init:   ld      iy, SPR_A
                ld      (iy+SD_BUF), low SPRBUF_A
                ld      (iy+SD_BUF+1), high SPRBUF_A
                ld      (iy+SD_X), 8
                ld      (iy+SD_X+1), 0
                ld      (iy+SD_Y), 20
                ld      (iy+SD_YH), 0
                ld      (iy+SD_FRAME), 16
                ld      (iy+SD_MIRROR), 0
                ld      (iy+SD_DX), 3
                ld      (iy+SD_OXB), 1
                ld      (iy+SD_OY), 20
                ld      (iy+SD_OW2), 3
                ld      (iy+SD_OH), 42
                ld      (iy+SD_LKEY), 0xff
                ld      (iy+SD_COMPOSE), low COMPOSE_A
                ld      (iy+SD_COMPOSE+1), high COMPOSE_A
                ld      iy, SPR_B
                ld      (iy+SD_BUF), low SPRBUF_B
                ld      (iy+SD_BUF+1), high SPRBUF_B
                ld      (iy+SD_X), low 250
                ld      (iy+SD_X+1), high 250
                ld      (iy+SD_Y), 146
                ld      (iy+SD_YH), 0
                ld      (iy+SD_FRAME), 20
                ld      (iy+SD_MIRROR), 1
                ld      (iy+SD_DX), -2
                ld      (iy+SD_OXB), 31
                ld      (iy+SD_OY), 146
                ld      (iy+SD_OW2), 5
                ld      (iy+SD_OH), 40
                ld      (iy+SD_LKEY), 0xff
                ld      (iy+SD_COMPOSE), low COMPOSE_B
                ld      (iy+SD_COMPOSE+1), high COMPOSE_B
                ld      a, 1
                ld      (WAITVBLN), a
                ; initial fetch so the first compose has valid buffers
                ld      iy, SPR_A
                call    char_fetch
                ld      iy, SPR_B
                jp      char_fetch

; ---------------------------------------------------------------- video / irq (as M0)
video_init:     ld      a, 0x02
                out     (PORT_DMD), a
                ld      c, PORT_SCRL
                ld      b, 0x06
                xor     a
                out     (c), a
                ld      b, 0x01
                out     (c), a
                ld      b, 0x02
                out     (c), a
                ld      a, 0x40
                out     (PORT_PAL), a
                xor     a
                out     (PORT_PAL), a
                ld      a, 0x11
                out     (PORT_PAL), a
                ld      a, 0x22
                out     (PORT_PAL), a
                ld      a, 0x33
                out     (PORT_PAL), a
                ld      a, 0x80         ; clear all planes
                out     (PORT_WF), a
                ld      hl, VRAM
                ld      de, VRAM + 1
                ld      bc, 8000 - 1
                ld      (hl), 0xff
                ldir
                ret

irq_init:       ld      hl, VECTAB
                ld      b, 0
vtfill:         ld      (hl), low isr
                inc     hl
                ld      (hl), high isr
                inc     hl
                djnz    vtfill
                ld      a, high VECTAB
                ld      i, a
                im      2
                ld      a, 0x00
                out     (PIOA_CTRL), a
                ld      a, 0xcf
                out     (PIOA_CTRL), a
                ld      a, 0xff
                out     (PIOA_CTRL), a
                ld      a, 0x97
                out     (PIOA_CTRL), a
                ld      a, 0xdf
                out     (PIOA_CTRL), a
                ei
                ret

isr:            push    af
                push    hl
                ld      hl, (FRAMES)
                inc     hl
                ld      (FRAMES), hl
                pop     hl
                pop     af
                ei
                reti

                include "far.asm"
                include "gfx.asm"
end_of_code:

; ---- second block: the data tables (0xC000-0xDFFF)
                org     0xc000
block2:
                include "../../build/assets/tables.inc"
block2_end:
                if block2_end > 0xe000
                .error block 2 overlaps the directories
                endif
