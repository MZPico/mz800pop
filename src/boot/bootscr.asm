; ---------------------------------------------------------------- the loading screen's start (the boot only)
; boot_screen (the boot's first screen work, before rd_probe): checks for the MZ-800's VRAM extension (MZ-1R25: planes
; III and IV, 16 KB of the 32 KB that 320x200 in 16 colours needs), then clears the screen and shows the title and the
; credit line. Without the extension it shows a message in 320x200 / 4 colours (planes I and II, all a 16 KB machine
; has) and halts at vram_stop.
; The check: in 320x200 / 16 colours (DMD 02h), for planes III and IV, two patterns (5Ah, A5h): the pattern written
; to the plane at 8000h (WF SINGLE, that plane only), its complement to plane I at the same address (so neither a
; floating bus nor a plane aliased to plane I can echo it), then the plane read back (RF SINGLE, that plane) and
; compared (vram_cmp). A missing plane reads FFh and keeps nothing (docs/research/mz800-hardware.md; mz800emu built
; without EXTVRAM alike). The bytes overwritten at 8000h are not put back: video_init clears all four planes next.
PORT_RF         equ     0xcd

boot_screen:    call    draw_on
                ld      a, 0x02                 ; 320x200, 16 colours
                out     (PORT_DMD), a
                ld      hl, VRAM
                ld      c, 0x04                 ; plane III, then IV
vc_plane:       ld      b, 0x5a
vc_pat:         ld      a, c                    ; WF SINGLE: the pattern to the plane
                out     (PORT_WF), a
                ld      (hl), b
                ld      a, 0x01                 ; plane I: the complement
                out     (PORT_WF), a
                ld      a, b
                cpl
                ld      (hl), a
                ld      a, c                    ; RF SINGLE: the plane back
                out     (PORT_RF), a
                ld      a, (hl)
vram_cmp:       cp      b                       ; (tests/m5_boot.py: A = FFh here plays a 16 KB machine)
                jr      nz, vram_refuse
                ld      a, b
                cpl
                ld      b, a
                cp      0x5a
                jr      nz, vc_pat
                sla     c
                bit     4, c
                jr      z, vc_plane
                ld      a, 0x01                 ; RF back to plane I (its state after a reset)
                out     (PORT_RF), a
                call    video_init
                ld      hl, msg_title
                call    print_at
                ld      hl, msg_credit
                jp      print_at

vram_refuse:    call    video_init              ; (its REPLACE clears planes I and II, all there are)
                xor     a                       ; 320x200, 4 colours, frame A (planes I, II)
                out     (PORT_DMD), a
                inc     a                       ; RF back to plane I
                out     (PORT_RF), a
                ld      a, 0x1a                 ; PLT1 = 10 (the message, colour 1: plane I)
                out     (PORT_PAL), a
                ld      a, 0x3f                 ; PLT3 = 15 (the title and the credit: their colours set both planes)
                out     (PORT_PAL), a
                ld      hl, msg_title
                call    print_at
                ld      hl, msg_credit
                call    print_at
                ld      hl, msg_vr1
                call    print_at
                ld      hl, msg_vr2
                call    print_at
vram_stop:      jr      vram_stop               ; (harness breakpoint: no VRAM extension)

msg_title:      dw      48 * 40 + 12
                db      COL_TEXT, "PRINCE OF PERSIA", 0
msg_credit:     dw      60 * 40 + 10
                db      7, "MZ-800 PORT BY MZPICO", 0
msg_vr1:        dw      112 * 40 + 4
                db      1, "SORRY, THIS GAME NEEDS 32 KB VRAM", 0
msg_vr2:        dw      124 * 40 + 4
                db      1, "(THE MZ-1R25 VRAM EXTENSION).", 0
