; ---------------------------------------------------------------- far storage driver
; Backend: STD / MZ-1R18 paged RAM disk (E9 page, EB address, EA data auto-increment), or with PICORD (`make picord`,
; build/pop800-picord.dsk) the MZPico's pico_rd (MZPico-firmware src/mz_devices/pico_rd.cpp; docs/ramdisk-tiers.md
; "pico_rd"; the firmware with the fixed address ports: base+2 / +3 / +4 each replace one byte). A pico_rd position =
; an MZ-1R18 page (byte 2) and address (bytes 1, 0): the same RAM-disk layout. The page goes to base+2 where the
; MZ-1R18 code writes E9h, the address to base+3 and base+4 (two OUTs where the MZ-1R18 has one with B on the high
; address lines, which the Frugal board cannot see), and only base+4 where the high byte is known to stay.
                if defined PICORD
RD_BASE         equ     0x45            ; (the card's [pico_rd] base_port, its default)
RD_DATA         equ     RD_BASE + 1
RD_PAGE         equ     RD_BASE + 2     ; address byte 2: the page (as the MZ-1R18's page register: the rest kept)
RD_A1           equ     RD_BASE + 3     ; address byte 1: the address's high byte
RD_A0           equ     RD_BASE + 4     ; address byte 0: its low byte
                if RD_PAGE - RD_DATA - 1
                .error far_seek leaves C = RD_DATA + 1 for its callers' dec c
                endif
                else
RD_PAGE         equ     0xe9
RD_DATA         equ     0xea
RD_ADDR         equ     0xeb
                if RD_ADDR - RD_DATA - 1
                .error shadow_write switches the ports with dec c / inc c
                endif
                endif

; far_seek: A = page, DE = address within the page; after it A = E and C = RD_DATA + 1 (callers: dec c); B = D on the
; MZ-1R18 only (no caller needs it). FAR_SEEK_ANY_C (PRES: every caller sets C itself): pico_rd's far_seek leaves C as
; it was (PRES's room: tools/mkgamedisk.py PRES_RESERVE)
                if defined PICORD
far_seek:       out     (RD_PAGE), a
                ld      a, d
                out     (RD_A1), a
                ld      a, e
                out     (RD_A0), a
                if defined FAR_SEEK_ANY_C
                else
                ld      c, RD_PAGE      ; (RD_DATA + 1, as the MZ-1R18's RD_ADDR)
                endif
                ret
                else
far_seek:       out     (RD_PAGE), a
                ld      b, d
                ld      c, RD_ADDR
                ld      a, e
                out     (c), a
                ret
                endif

; far_seek_entry: IX = directory entry, HL = 16-bit offset from the entry's start
far_seek_entry: ld      e, (ix+2)
                ld      d, (ix+1)
                add     hl, de
                ld      a, (ix+0)
                adc     a, 0
                ex      de, hl
                jr      far_seek

; far_read: HL = destination, B = byte count (1..255)
far_read:       ld      c, RD_DATA
                inir
                ret

; far_copy: A = page, DE = address in the page, HL = destination, BC = byte count (any size)
far_copy:       push    bc
                push    hl
                call    far_seek
                pop     hl
                pop     de              ; DE = count
                ld      c, RD_DATA
fc_full:        ld      a, d
                or      a
                jr      z, fc_rest
                ld      b, 0
                inir                    ; 256 bytes
                dec     d
                jr      fc_full
fc_rest:        ld      a, e
                or      a
                ret     z
                ld      b, a
                inir
                ret
