; ---------------------------------------------------------------- the loading screen's start (the boot only)
; boot_screen (the boot's first screen work, before rd_probe): checks for the MZ-800's VRAM extension (MZ-1R25: planes
; III and IV, 16 KB of the 32 KB that 320x200 in 16 colours needs), then clears the screen and shows the title, the
; credit line and the version. Without the extension it shows a message in 320x200 / 4 colours (planes I and II, all a 16 KB machine
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
; bs_head: the title, the credit line, the version (VERSION, tools/version.py: build/version.inc)
bs_head:        ld      hl, msg_title
                call    print_at
                ld      hl, msg_credit
                call    print_at
                ld      hl, msg_ver
                jp      print_at

vram_refuse:    call    video_init              ; (its REPLACE clears planes I and II, all there are)
                xor     a                       ; 320x200, 4 colours, frame A (planes I, II)
                out     (PORT_DMD), a
                inc     a                       ; RF back to plane I
                out     (PORT_RF), a
                ld      a, 0x1a                 ; PLT1 = 10 (the message, colour 1: plane I)
                out     (PORT_PAL), a
                ld      a, 0x3f                 ; PLT3 = 15 (the title, the credit, the version: their colours set
                out     (PORT_PAL), a           ; both planes)
                call    bs_head
                ld      hl, msg_vr1
                call    print_at
                ld      hl, msg_vr2
                call    print_at
vram_stop:      jr      vram_stop               ; (harness breakpoint: no VRAM extension)

msg_title:      dw      48 * 40 + 12
                db      COL_TEXT, "PRINCE OF PERSIA", 0
msg_credit:     dw      60 * 40 + 10
                db      7, "MZ-800 PORT BY MZPICO", 0
                include "../../build/version.inc"       ; msg_ver: "V0.1.0" under the credit (row 72, centred)
msg_vr1:        dw      112 * 40 + 4
                db      1, "SORRY, THIS GAME NEEDS 32 KB VRAM", 0
msg_vr2:        dw      124 * 40 + 4
                db      1, "(THE MZ-1R25 VRAM EXTENSION).", 0

; net_line (rd_speed, after its report): the network line under the RAM disk's (row 138, colour 7):
;   NETWORK: MZPICO NET (DUEL: CTRL+D)      an MZPico with the NET service (network play in the duel)
;   NETWORK: NONE (DUEL: CTRL+D)            none (the duel is local only)
; The detection is the duel's d_ndet (src/duel/duel.asm, docs/duel-design.md 14.3): REVD's status {02, 06, 04} (a
; Unicard-compatible device), then INFO (no ERROR, no BUSY, OUTPUT, the command echoed, >= 16 bytes) with the NET
; feature bit (byte 3, bit 3). Without a card the ports float (FFh: ERROR set), so the first status read fails it:
; nothing waits, nothing is written but the two command bytes. net_res: 0 = found (tests/m5_boot.py reads it).
NP_CMD          equ     0x50
NP_DATA         equ     0x51
NB              equ     TRKBUF + 0x380          ; the status / output bytes (TRKBUF: free until the directory)
net_res         equ     TRKBUF + 0x37f

                if      defined DIAG
                else
net_line:       call    net_det
                ld      a, 1
                jr      nz, nl_0
                xor     a
nl_0:           ld      (net_res), a
                ld      hl, 138 * 40 + 4
                call    rs_line
                push    af
                ld      hl, s_net
                call    put_str
                pop     af
                ld      hl, s_mzp
                jr      z, nl_1
                ld      hl, s_none
nl_1:           call    put_str
                ld      hl, s_duel
                call    put_str
                jp      rs_print
; net_det: Z (A = 0) when an MZPico NET card answers; NZ otherwise
net_det:        ld      a, 0x06                 ; REVD
                call    nd_cmd
                ld      hl, NB
                ld      a, (hl)
                cp      2
                ret     nz
                inc     hl
                ld      a, (hl)
                cp      0x06
                ret     nz
                inc     hl
                ld      a, (hl)
                cp      4
                ret     nz
                ld      b, 4                    ; (its 4 output bytes)
                call    nd_in
                ld      a, 0x95                 ; INFO
                call    nd_cmd
                ld      a, (NB)
                and     0xc3                    ; ERROR, IN_PROGRESS, OUTPUT, BUSY: OUTPUT alone
                cp      2
                ret     nz
                ld      a, (NB + 1)
                cp      0x95
                ret     nz
                ld      a, (NB + 2)
                cp      16
                jr      c, nd_f
                ld      b, 16
                call    nd_in
                ld      a, (NB + 3)
                cpl
                and     8
                ret
nd_f:           or      1
                ret
; nd_cmd: A = the command (no parameters), then its status (STSR, 4 bytes to NB) until it is no longer IN_PROGRESS
; without ERROR (at most 65,536 reads, ~1 s; the commands used here answer at once)
nd_cmd:         out     (NP_CMD), a
                ld      de, 0
nd_st:          ld      a, 0x03                 ; STSR
                out     (NP_CMD), a
                ld      hl, NB
                ld      bc, 4 * 256 + NP_CMD
                inir
                ld      a, (NB)
                and     0xc0
                cp      0x40
                ret     nz
                dec     de
                ld      a, d
                or      e
                jr      nz, nd_st
                ret
; nd_in: B bytes of output to NB
nd_in:          ld      hl, NB
                ld      c, NP_DATA
                inir
                ret

s_net:          db      "NETWORK: ", 0
s_mzp:          db      "MZPICO NET", 0
s_none:         db      "NONE", 0
s_duel:         db      " (DUEL: CTRL+D)", 0
                endif
