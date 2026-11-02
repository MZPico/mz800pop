; M0 boot program for the Sharp MZ-800 (pop-800).
; Loaded by the ROM IPL from the floppy (IPLPRO bootstrap, mzdsk-fsmz boot put),
; relocated to LOAD and started at `start`.
;
; What it does:
;   - switches to 320x200 16-colour mode, identity palette, black border
;   - installs a 50 Hz VBLN interrupt through the Z80 PIO (port A bit 5, IM2)
;   - scans the keyboard matrix and joystick 1 every frame, shows 5 game inputs
;   - probes the RAM disk: MZ-1R18/STD paged protocol (E9/EA/EB) and MZPico pico_rd (45h..)
;   - prints the results and a running frame counter in hex
; Variables live at VARS (0x7000..), the IM2 vector table at 0xFE00, stack below it.

LOAD            equ     0x3000
VARS            equ     0x7000
FRAMES          equ     VARS + 0        ; 16-bit, incremented by the VBLN ISR
KEYMAT          equ     VARS + 0x10     ; 10 bytes, 1 = pressed
JOY             equ     VARS + 0x1a     ; joystick 1 raw (inverted: 1 = active)
INPUT           equ     VARS + 0x1b     ; bit0 left, 1 right, 2 up, 3 down, 4 button
RDFLAGS         equ     VARS + 0x20     ; bit0 STD ramdisk present, bit1 pico_rd present
RDSTDSZ         equ     VARS + 0x21     ; STD size in 64 KB pages (1..16)
RDPICOSZ        equ     VARS + 0x22     ; pico_rd size in 64 KB pages (1..16)
ISRMARK         equ     VARS + 0x24     ; last VBLN: GDG status byte (harness check)
VECTAB          equ     0xfe00
STACK           equ     0xfe00
RDBUF           equ     0xa000          ; 4 KB buffer for the speed test

VRAM            equ     0x8000
PORT_WF         equ     0xcc
PORT_DMD        equ     0xce
PORT_SCRL       equ     0xcf
PORT_PAL        equ     0xf0
PORT_JOY1       equ     0xf0
PORT_KBD_COL    equ     0xd0
PORT_KBD_ROW    equ     0xd1
PIOA_DATA       equ     0xfe            ; MZ-800: FC/FD = control A/B, FE/FF = data A/B
PIOA_CTRL       equ     0xfc
RD_PAGE         equ     0xe9
RD_DATA         equ     0xea
RD_ADDR         equ     0xeb
RD_RESET        equ     0xf8
PRD_BASE        equ     0x45            ; pico_rd: +0 ctrl, +1 data, +2/+3/+4 addr2/1/0

                org     LOAD
start:          di
                ld      sp, STACK
                out     (0xe0), a       ; low ROM off  -> RAM at 0000-1FFF
                out     (0xe1), a       ; high ROM off -> RAM at E000-FFFF
                in      a, (0xe0)       ; VRAM window 8000-9FFF (+ CG ROM 1000-1FFF)
                ; clear variables
                ld      hl, VARS
                ld      de, VARS + 1
                ld      bc, 0xff
                ld      (hl), 0
                ldir
                call    video_init
                call    draw_static
                call    rd_probe
                call    show_rd
                call    irq_init
mainloop:       halt                    ; one VBLN period
                call    read_inputs
                call    show_inputs
                ld      hl, (FRAMES)
                ld      a, h
                ld      de, 40 * 120 + 2
                call    hex_at
                ld      a, l
                ld      de, 40 * 120 + 4
                call    hex_at
                jr      mainloop

; ---------------------------------------------------------------- video
video_init:     ld      a, 0x02         ; 320x200, 16 colours
                out     (PORT_DMD), a
                ld      c, PORT_SCRL
                ld      b, 0x06         ; border black
                xor     a
                out     (c), a
                ld      b, 0x01         ; SOF = 0 (16-colour mode adds SOF to CPU access!)
                out     (c), a
                ld      b, 0x02
                out     (c), a
                ld      a, 0x40         ; palette group 0 through PLT0-3
                out     (PORT_PAL), a
                xor     a               ; PLT0..3 = identity
                out     (PORT_PAL), a
                ld      a, 0x11
                out     (PORT_PAL), a
                ld      a, 0x22
                out     (PORT_PAL), a
                ld      a, 0x33
                out     (PORT_PAL), a
                ; clear screen: REPLACE with colour 0 writes 0 to all four planes
                ld      a, 0x80
                out     (PORT_WF), a
                ld      hl, VRAM
                ld      de, VRAM + 1
                ld      bc, 8000 - 1
                ld      (hl), 0xff
                ldir
                ret

; Fill a byte-aligned rectangle with one colour.
; In: HL = VRAM address of top-left byte, B = height, C = width in bytes, A = colour
fill_rect:      or      0x80            ; REPLACE, planes = colour
                out     (PORT_WF), a
                ld      de, 40
frrow:          push    hl
                push    bc
                ld      a, 0xff
frcol:          ld      (hl), a
                inc     hl
                dec     c
                jr      nz, frcol
                pop     bc
                pop     hl
                add     hl, de
                djnz    frrow
                ret

; Print hex byte. In: A = value, DE = VRAM offset of the top-left byte (row*40+col)
hex_at:         push    af
                rra
                rra
                rra
                rra
                call    hex_digit
                inc     de
                pop     af
; fall through: low nibble
hex_digit:      and     0x0f
                ld      l, a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl          ; *8
                ld      bc, font
                add     hl, bc
                push    de
                ex      de, hl          ; DE = glyph, HL = screen
                ld      bc, VRAM
                add     hl, bc
                ld      a, 0x8f         ; REPLACE, colour 15 (bright white), 0 bits -> black
                out     (PORT_WF), a
                ld      b, 8
hdrow:          ld      a, (de)
                ld      (hl), a
                inc     de
                push    de
                ld      de, 40
                add     hl, de
                pop     de
                djnz    hdrow
                pop     de
                ret

draw_static:    ; colour bars: 16 x (2 bytes wide, 12 rows) at the top
                ld      hl, VRAM
                ld      b, 0
cbar:           push    bc
                ld      a, b
                ld      b, 12
                ld      c, 2
                push    hl
                call    fill_rect
                pop     hl
                inc     hl
                inc     hl
                pop     bc
                inc     b
                ld      a, b
                cp      16
                jr      nz, cbar
                ; labels: "L R U D B" above the input boxes (row 30) as hex digits of a legend
                ret

; input boxes: 5 boxes 16 px wide, 12 rows, at row 40, x = 1 + 3*i bytes
show_inputs:    ld      a, (INPUT)
                ld      c, a
                ld      hl, VRAM + 40 * 40 + 1
                ld      b, 5
sibox:          push    bc
                push    hl
                ld      a, 8            ; grey = released
                rr      c
                jr      nc, sicol
                ld      a, 12           ; light green = pressed
sicol:          push    bc
                ld      b, 12
                ld      c, 2
                call    fill_rect
                pop     bc
                pop     hl
                inc     hl
                inc     hl
                inc     hl
                pop     bc
                djnz    sibox
                ; raw bytes: keyboard column 7, column 6, joystick
                ld      a, (KEYMAT + 7)
                ld      de, 40 * 60 + 1
                call    hex_at
                ld      a, (KEYMAT + 6)
                ld      de, 40 * 60 + 4
                call    hex_at
                ld      a, (JOY)
                ld      de, 40 * 60 + 7
                call    hex_at
                ld      a, (INPUT)
                ld      de, 40 * 60 + 10
                call    hex_at
                ret

; ---------------------------------------------------------------- input
read_inputs:    ld      hl, KEYMAT
                ld      c, 0
kbcol:          ld      a, c
                out     (PORT_KBD_COL), a
                in      a, (PORT_KBD_ROW)
                cpl                     ; 1 = pressed
                ld      (hl), a
                inc     hl
                inc     c
                ld      a, c
                cp      10
                jr      nz, kbcol
                in      a, (PORT_JOY1)
                cpl                     ; 1 = active (b0 up b1 down b2 left b3 right b4 fire)
                ld      (JOY), a
                ld      d, a
                ; game input byte: bit0 left, 1 right, 2 up, 3 down, 4 button
                ld      e, 0
                ld      a, (KEYMAT + 7) ; cursor keys: bit2 left, bit3 right, bit5 up, bit4 down
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
nd:             ld      a, (KEYMAT + 6) ; space = column 6 bit 4
                bit     4, a
                jr      z, nb
                set     4, e
nb:             ld      a, d            ; joystick
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

; ---------------------------------------------------------------- VBLN interrupt
irq_init:       ; IM2 vector table: 256 bytes, every entry -> isr (vector byte may be anything)
                ld      hl, VECTAB
                ld      b, 0
vtfill:         ld      (hl), low isr
                inc     hl
                ld      (hl), high isr
                inc     hl
                djnz    vtfill
                ld      a, high VECTAB
                ld      i, a
                im      2
                ; Z80 PIO port A: mode 3, all inputs, interrupt when bit 5 (VBLN) is low
                ld      a, 0x00         ; interrupt vector (low byte, even)
                out     (PIOA_CTRL), a
                ld      a, 0xcf         ; mode 3 (bit control)
                out     (PIOA_CTRL), a
                ld      a, 0xff         ; I/O mask: all bits input
                out     (PIOA_CTRL), a
                ld      a, 0x97         ; int control: enable, OR, active LOW, mask follows
                out     (PIOA_CTRL), a
                ld      a, 0xdf         ; mask: monitor bit 5 only (0 = monitored)
                out     (PIOA_CTRL), a
                ei
                ret

isr:            push    af
                push    hl
                ld      hl, (FRAMES)
                inc     hl
                ld      (FRAMES), hl
                in      a, (PORT_DMD)   ; GDG status at interrupt time (bit6 VBLNK)
                ld      (ISRMARK), a
                pop     hl
                pop     af
                ei
                reti

; ---------------------------------------------------------------- RAM disk probe
; STD / MZ-1R18 paged protocol: OUT E9 = page, OUT (C),A with B = addr high / A = addr low on EB,
; EA = data with auto-increment, IN F8 = reset address and page.
rd_std_seek0:   xor     a
                out     (RD_PAGE), a    ; page 0 (A holds the page on entry for other callers)
rd_std_seek:    ld      bc, RD_ADDR     ; B = 0 = address high, C = port
                xor     a
                out     (c), a          ; address low = 0  -> offset 0
                ret

rd_probe:       ; --- STD ---
                in      a, (RD_RESET)
                call    rd_std_seek0
                ld      a, 0x5a
                out     (RD_DATA), a
                ld      a, 0xa5
                out     (RD_DATA), a
                ld      a, 0x3c
                out     (RD_DATA), a
                call    rd_std_seek0
                in      a, (RD_DATA)
                cp      0x5a
                jr      nz, rd_pico
                in      a, (RD_DATA)
                cp      0xa5
                jr      nz, rd_pico
                in      a, (RD_DATA)
                cp      0x3c
                jr      nz, rd_pico
                ld      hl, RDFLAGS
                set     0, (hl)
                ; size: write marker 0x80|p at offset 0 of page p (p = 1..16), then read page 0;
                ; when page 0 changed, page p aliases page 0 -> size = p pages
                call    rd_std_seek0
                ld      a, 0x80
                out     (RD_DATA), a
                ld      d, 1
stdsz:          ld      a, d
                cp      16
                jr      z, stdszdone    ; 16 pages = 1 MB or more: stop
                out     (RD_PAGE), a
                call    rd_std_seek
                ld      a, d
                or      0x80
                out     (RD_DATA), a
                call    rd_std_seek0
                in      a, (RD_DATA)
                cp      0x80
                jr      nz, stdszdone   ; aliased
                inc     d
                jr      stdsz
stdszdone:      ld      a, d
                ld      (RDSTDSZ), a
                call    rd_std_seek0
                ; speed test: 4096 bytes from page 0 into RDBUF with INIR (harness measures cycles)
                ld      hl, RDBUF
                ld      c, RD_DATA
                ld      b, 0
spd_start:      inir
                inir
                inir
                inir
                inir
                inir
                inir
                inir
                inir
                inir
                inir
                inir
                inir
                inir
                inir
                inir
spd_end:        nop
rd_pico:        ; --- MZPico pico_rd ---
                out     (PRD_BASE), a   ; reset position
                xor     a
                out     (PRD_BASE + 2), a
                out     (PRD_BASE + 3), a
                out     (PRD_BASE + 4), a
                ld      a, 0x5a
                out     (PRD_BASE + 1), a
                ld      a, 0xa5
                out     (PRD_BASE + 1), a
                xor     a
                out     (PRD_BASE + 4), a   ; position = 0 again
                out     (PRD_BASE + 3), a
                out     (PRD_BASE + 2), a
                in      a, (PRD_BASE + 1)
                cp      0x5a
                ret     nz
                in      a, (PRD_BASE + 1)
                cp      0xa5
                ret     nz
                ld      hl, RDFLAGS
                set     1, (hl)
                ; size: marker at 64 KB multiples (addr2 = p)
                xor     a
                out     (PRD_BASE + 2), a
                out     (PRD_BASE + 3), a
                out     (PRD_BASE + 4), a
                ld      a, 0x80
                out     (PRD_BASE + 1), a
                ld      d, 1
picosz:         ld      a, d
                cp      16
                jr      z, picoszdone
                out     (PRD_BASE + 2), a
                xor     a
                out     (PRD_BASE + 3), a
                out     (PRD_BASE + 4), a
                ld      a, d
                or      0x80
                out     (PRD_BASE + 1), a
                xor     a
                out     (PRD_BASE + 2), a
                out     (PRD_BASE + 3), a
                out     (PRD_BASE + 4), a
                in      a, (PRD_BASE + 1)
                cp      0x80
                jr      nz, picoszdone
                inc     d
                jr      picosz
picoszdone:     ld      a, d
                ld      (RDPICOSZ), a
                ret

show_rd:        ld      a, (RDFLAGS)
                ld      de, 40 * 80 + 1
                call    hex_at
                ld      a, (RDSTDSZ)
                ld      de, 40 * 80 + 4
                call    hex_at
                ld      a, (RDPICOSZ)
                ld      de, 40 * 80 + 7
                call    hex_at
                ret

                include "font.inc"
end_of_code:
