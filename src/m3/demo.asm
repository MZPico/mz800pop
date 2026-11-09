; M3 camera demo: walks through the rooms of a level with the joystick / cursor keys and animates the torches
; and potion bubbles at the game tick (4 frames). The harness (tests/m3_demo.py) loads the packs into the RAM
; disk, the directories, the level and LEVEL_TYPE, then runs this program.
VARS            equ     0x0800
FRAMES          equ     VARS + 0        ; 16-bit, incremented by the VBLN ISR
; (0x0810-0x084F belong to the graphics kernel: keep the demo's variables above them)
KEYMAT          equ     VARS + 0x60     ; 10 bytes
JOY             equ     VARS + 0x6a
INPUT           equ     VARS + 0x6b     ; bit0 left, 1 right, 2 up, 3 down, 4 button
ISRMARK         equ     VARS + 0x6c
LAST_TICK       equ     VARS + 0x6e     ; 16-bit
PREV_IN         equ     VARS + 0x70
CUR_ROOM        equ     VARS + 0x71
TICKS           equ     VARS + 0x72     ; 16-bit tick counter (harness)
ANIM_POS        equ     VARS + 0x74
VECTAB          equ     0xfe00
STACK           equ     0xfe00
PORT_DMD        equ     0xce
PORT_SCRL       equ     0xcf
PORT_PAL        equ     0xf0
PORT_JOY1       equ     0xf0
PORT_KBD_COL    equ     0xd0
PORT_KBD_ROW    equ     0xd1
PIOA_CTRL       equ     0xfc

                org     0x2000
start:          di
                ld      sp, STACK
                out     (0xe0), a
                out     (0xe1), a
                in      a, (0xe0)
                call    video_init
                in      a, (0xe1)       ; VRAM window off: 0x8000-0x9FFF is RAM for the renderer's tables
                call    tables_init
                call    alter_mods
                call    irq_init
                ld      hl, 0
                ld      (TICKS), hl
                ld      a, (LV_START_ROOM)
                call    show_room
                xor     a
                ld      (PREV_IN), a
mainloop:       halt
                ld      hl, (FRAMES)
                ld      de, (LAST_TICK)
                or      a
                sbc     hl, de
                ld      a, l
                cp      4
                jr      c, mainloop
                ld      hl, (FRAMES)
                ld      (LAST_TICK), hl
                ld      hl, (TICKS)
                inc     hl
                ld      (TICKS), hl
                call    read_inputs
                ld      a, (INPUT)
                ld      b, a
                ld      a, (PREV_IN)
                cpl
                and     b               ; newly pressed bits
                ld      (edge_bits), a
                ld      a, b
                ld      (PREV_IN), a
                ld      a, (CUR_ROOM)
                call    links_of        ; C = left, B = right, D = up, E = down
                ld      a, (edge_bits)
                bit     0, a
                jr      z, k1
                ld      a, c
                jr      goroom
k1:             bit     1, a
                jr      z, k2
                ld      a, b
                jr      goroom
k2:             bit     2, a
                jr      z, k3
                ld      a, d
                jr      goroom
k3:             bit     3, a
                jr      z, tick_anim
                ld      a, e
goroom:         or      a
                jr      z, tick_anim
                call    show_room
                jr      mainloop
tick_anim:      call    animate
                jr      mainloop

; show_room: A = room; draws it and makes it current
show_room:      ld      (CUR_ROOM), a
                jp      draw_room_full

; animate: advance the torch flames and potion bubbles of the current room by one frame
animate:        xor     a
animloop:       ld      (ANIM_POS), a
                ld      a, (CUR_ROOM)
                call    tile_base       ; HL = &fg[(room-1)*30], DE = &bg[...]
                ld      a, (ANIM_POS)
                ld      c, a
                ld      b, 0
                add     hl, bc
                ex      de, hl
                add     hl, bc          ; HL = &mod, DE = &type
                ld      a, (de)
                and     0x1f
                cp      T_TORCH
                jr      z, an_torch
                cp      T_TORCH_DEBRIS
                jr      z, an_torch
                cp      T_POTION
                jr      z, an_potion
an_next:        ld      a, (ANIM_POS)
                inc     a
                cp      30
                jr      nz, animloop
                ret
an_torch:       ld      a, (hl)         ; current frame
                ld      c, a
                push    hl
                ld      a, 255
                call    prandom         ; next = prandom(255)
                cp      c
                jr      z, an_t1
                cp      9
                jr      c, an_t2        ; next < 9 -> use it
                ld      a, c
an_t1:          inc     a               ; next = curr + 1, wrapping at 9
                cp      9
                jr      c, an_t2
                xor     a
an_t2:          pop     hl
                ld      (hl), a
                ld      c, a
                ld      a, (ANIM_POS)   ; the flame is drawn by the tile to the right (column < 9 only)
                call    tag_col_a
                cp      9
                jr      z, an_next
                ld      a, (ANIM_POS)
                inc     a
                call    torch_redraw
                jr      an_next
an_potion:      ld      a, (hl)
                and     0xf8
                jr      z, an_next      ; empty potion: no bubble
                ld      c, a
                ld      a, (hl)
                and     7
                inc     a
                cp      8
                jr      c, an_p1
                ld      a, 1
an_p1:          or      c
                ld      (hl), a
                and     7
                ld      c, a
                ld      a, (ANIM_POS)
                call    bubble_redraw
                jr      an_next
tag_col_a:      cp      10              ; A = tag -> A = column
                ret     c
                sub     10
                jr      tag_col_a

; ---------------------------------------------------------------- video, input, interrupt (as in M0)
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
                ld      a, 0x80
                out     (PORT_WF), a
                ld      hl, VRAM
                ld      de, VRAM + 1
                ld      bc, 8000 - 1
                ld      (hl), 0xff
                ldir
                ret

read_inputs:    ld      hl, KEYMAT
                ld      c, 0
kbcol:          ld      a, c
                out     (PORT_KBD_COL), a
                in      a, (PORT_KBD_ROW)
                cpl
                ld      (hl), a
                inc     hl
                inc     c
                ld      a, c
                cp      10
                jr      nz, kbcol
                in      a, (PORT_JOY1)
                cpl
                ld      (JOY), a
                ld      d, a
                ld      e, 0
                ld      a, (KEYMAT + 7)
                bit     2, a
                jr      z, nl
                set     0, e
nl:             bit     3, a
                jr      z, nr
                set     1, e
nr:             bit     5, a
                jr      z, nu
                set     2, e
nu:             bit     4, a
                jr      z, nd
                set     3, e
nd:             ld      a, (KEYMAT + 6)
                bit     4, a
                jr      z, nb
                set     4, e
nb:             ld      a, d
                bit     2, a
                jr      z, jl
                set     0, e
jl:             bit     3, a
                jr      z, jr_
                set     1, e
jr_:            bit     0, a
                jr      z, ju
                set     2, e
ju:             bit     1, a
                jr      z, jd
                set     3, e
jd:             bit     4, a
                jr      z, jb
                set     4, e
jb:             ld      a, e
                ld      (INPUT), a
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
                in      a, (PORT_DMD)
                ld      (ISRMARK), a
                pop     hl
                pop     af
                ei
                reti
edge_bits:      db      0

                include "../m1/far.asm"
                include "../m1/gfx.asm"
                include "../m3/room.asm"
                include "../m3/roomfull.asm"
                include "../m3/altmods.asm"
rr_bkt_ent      equ     rr_bkt          ; (the M4 game: the room overlay's entry)
end_of_code:
                if end_of_code > 0x8000
                .error code overlaps the tables at 0x8000
                endif

; ---- second block: the data tables (0xC000-0xDFFF)
                org     0xc000
block2:
                include "../../build/assets/tables.inc"
                if $ - shift_tab < 4 * SV_WALLN + 1     ; (room.asm shift_variant's guess stays inside the table)
                .error shift_tab is shorter than shift_variant's wall-mark entries
                endif
block2_end:
                if block2_end > 0xe000
                .error block 2 overlaps the directories
                endif
