; ---------------------------------------------------------------- WD2793 sector I/O (the ROM IPL's sequences, E4DCh-E660h)
; Shared by the floppy loader (src/boot/boot.asm) and the game's save overlay (src/m4/save.asm). The includer defines
; fd_cyl (1 byte: the cylinder the head is on, 0xff = unknown: the next access seeks). Ports D8-DB are inverted (CPL
; every value written and read); the side register is written inverted (logical side 1 = 0xFE). Run with interrupts
; off: the data loops must answer every DRQ within 32 us. docs/research/mz800-hardware.md "M5 floppy loader findings".
FD_CMD          equ     0xd8            ; WD2793 (MB8876): the data bus is inverted on ports D8-DB
FD_TRK          equ     0xd9
FD_SEC          equ     0xda
FD_DATA         equ     0xdb
FD_MOTOR        equ     0xdc            ; bit 7 motor, bit 2 drive select enable, bits 1-0 drive
FD_SIDE         equ     0xdd            ; written inverted by the ROM: FSMZ logical side 1 = 0xFE

; fd_read: A = logical track, E = first sector, D = sectors, HL = buffer. Z = ok.
fd_read:        call    fd_pos
                ret     nz
                ld      a, (fd_rcmd)    ; read sectors, multiple (0x94: 15 ms settle; boot.asm fd_read_rot: 0x90)
                call    fd_go
                ret     nz
                ld      c, FD_DATA
fr_sec:         ld      b, 0
fr_byte:        in      a, (FD_CMD)     ; bit 0 = not busy, bit 1 = no DRQ (inverted bus)
                rrca
                jr      c, fr_ended
                rrca
                jr      c, fr_byte
                ini
                jr      nz, fr_byte
                dec     d
                jr      nz, fr_sec
                ld      a, 0xd8         ; force interrupt (ROM E658h)
                call    fd_cmd
fr_ended:
                if      defined FD_DIAG
                in      a, (FD_TRK)     ; (boot.asm DIAG: the WD's track and sector registers, its status)
                cpl
                ld      (dg_wtrk), a
                in      a, (FD_SEC)
                cpl
                ld      (dg_wsec), a
                in      a, (FD_CMD)
                cpl
                ld      (dg_st), a
                endif
                in      a, (FD_CMD)
                cpl
                or      d               ; error if it stopped before the last sector
                ret

; fd_write: A = logical track, E = sector, HL = the 256 bytes. Z = ok (status clean, all 256 bytes taken).
fd_write:       call    fd_pos
                ret     nz
                ld      a, 0xa4         ; write sector (one), 15 ms settle, normal data mark
                call    fd_go
                ret     nz
                ld      bc, FD_DATA     ; (B = 0: 256 bytes)
fw_byte:        in      a, (FD_CMD)
                rrca
                jr      c, fw_end       ; not busy: the command ended
                rrca
                jr      c, fw_byte
                outi
                jr      fw_byte
fw_end:         in      a, (FD_CMD)
                cpl                     ; write protect 40h, record not found 10h, CRC 08h, lost data 04h
                or      b               ; (B: 0 after 256 bytes)
                ret

; fd_pos: A = logical track, E = sector: side, a seek if the cylinder changes, the track and sector registers.
; Z = ok. Keeps D, E, HL.
fd_pos:         ld      c, a
                and     1               ; side: logical 1 -> 0xFE, 0 -> 0xFF (ROM E61Bh)
                cpl
                out     (FD_SIDE), a
                ld      a, c
                srl     a               ; cylinder
                ld      c, a
                ld      a, (fd_cyl)
                cp      c
                jr      z, fp_1
                ld      a, c
                ld      (fd_cyl), a
                cpl
                out     (FD_DATA), a
                ld      a, 0x1b         ; seek, head load, 30 ms steps (the ROM's command)
                if      defined FD_DIAG
                ld      (dg_cmd), a
                call    fd_type1
                ld      (dg_st), a
                else
                call    fd_type1
                endif
                and     0x99            ; (fd_type1 waited ~60 ms after it, as the ROM does)
                ret     nz
fp_1:           ld      a, c
                cpl
                out     (FD_TRK), a
                ld      a, e
                cpl
                out     (FD_SEC), a
                xor     a
                ret

fd_rcmd:        db      0x94
; fd_go: A = a type II command (true bits): out, wait for BUSY (it sets within microseconds; 256 polls = ~2 ms after
; the ~110 us delay). Z = busy, NZ = the command did not start.
fd_go:
                if      defined FD_DIAG
                ld      (dg_cmd), a
                endif
                cpl
                out     (FD_CMD), a
                call    delay_short
                ld      b, 0
fg_1:           in      a, (FD_CMD)
                rrca
                jr      nc, fg_ok
                djnz    fg_1
                if      defined FD_DIAG
                ld      a, 0xee         ; (the command did not start)
                ld      (dg_st), a
                endif
                inc     b               ; NZ
                ret
fg_ok:          xor     a
                ret

; fd_type1: A = command; waits until not busy, then the long delay. Out: A = status (true bits).
fd_type1:       call    fd_cmd
                push    af
                call    delay_long
                pop     af
                ret
; fd_cmd: A = command (true bits): out, wait until not busy (at most ~9 s: 65536 polls ~130 us apart; the ROM waits
; ~6 s, E568h. A seek or restore steps 30 ms a cylinder: 39 cylinders take 1.2 s, more than the 0.9 s this loop
; waited until 2026-11-14, which left the FDC busy and the next command ignored). Out: A = status (true bits).
fd_cmd:         cpl
                out     (FD_CMD), a
                call    delay_short
                push    hl
                ld      hl, 0
fc_1:           in      a, (FD_CMD)
                rrca
                jr      c, fc_2
                call    delay_short
                dec     hl
                ld      a, h
                or      l
                jr      nz, fc_1
fc_2:           pop     hl
                in      a, (FD_CMD)
                cpl
                ret
delay_short:    push    de              ; ~110 us (ROM E6B3h)
                ld      de, 0x0f
                jr      dl_1
delay_long:     push    de              ; ~60 ms (ROM E6BFh)
                ld      de, 0x2026
dl_1:           dec     de
                ld      a, e
                or      d
                jr      nz, dl_1
                pop     de
                ret
