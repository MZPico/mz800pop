; M0 smoke test: 320x200 16-colour mode, 16 vertical colour bars drawn with
; WF REPLACE (one byte write paints 8 pixels in all four planes), then a
; frame counter in the border colour. pasmo --bin colorbars.asm
                org     0x2000
start:          di
                in      a, (0xe0)       ; map VRAM window 8000-9FFF (+ CG ROM)
                ld      a, 0x02         ; DMD: 320x200 16-colour
                out     (0xce), a
                ld      b, 0x06         ; border = black (CF06h)
                ld      c, 0xcf
                xor     a
                out     (c), a
                ld      b, 0x01         ; SOF low = 0
                out     (c), a
                ld      b, 0x02         ; SOF high = 0
                out     (c), a
                ld      a, 0x40         ; palette group 0 goes through PLT0-3
                out     (0xf0), a
                xor     a               ; PLT0..3 = identity (0,1,2,3)
                out     (0xf0), a
                ld      a, 0x11
                out     (0xf0), a
                ld      a, 0x22
                out     (0xf0), a
                ld      a, 0x33
                out     (0xf0), a
                ; 16 bars, each 20 px = 2.5 bytes; use 2 bytes (16 px) per bar
                ; + leave the rest: bar i covers bytes 2i..2i+1 and byte 32..39 = white/black
                ld      hl, 0x8000
                ld      e, 200          ; rows
rowloop:        ld      d, 0            ; colour
colloop:        ld      a, d
                or      0x80            ; WF: REPLACE (100), planes = colour
                out     (0xcc), a
                ld      a, 0xff
                ld      (hl), a
                inc     hl
                ld      (hl), a
                inc     hl
                inc     d
                ld      a, d
                cp      16
                jr      nz, colloop
                ; remaining 8 bytes: checker of colour 15 / 0
                ld      a, 0x8f
                out     (0xcc), a
                ld      a, 0xaa
                ld      b, 8
tailloop:           ld      (hl), a
                inc     hl
                djnz    tailloop
                dec     e
                jr      nz, rowloop
                ; frame counter in border via VBLNK polling (status CEh bit 6)
                ld      d, 0
loop:           in      a, (0xce)
                bit     6, a
                jr      z, loop         ; wait for canvas
waitblank:      in      a, (0xce)
                bit     6, a
                jr      nz, waitblank   ; wait for vertical blank
                inc     d
                ld      a, d
                ld      (0x7ffe), a     ; frame counter visible to the harness
                and     15
                ld      b, 0x06
                ld      c, 0xcf
                out     (c), a          ; border cycles through 16 colours
                jr      loop
finish:
