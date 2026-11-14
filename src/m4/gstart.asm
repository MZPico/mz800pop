; ---------------------------------------------------------------- the game's start (the level-start overlay, W2)
; Split out of src/m4/game.asm, gfx.asm, room.asm, sprite.asm and overlay.asm (2026-11-01, the memory reclaim): everything
; that runs once, when the program starts (game.asm start: the stub game_start, src/m4/ovl.asm). Resident code never calls
; these again. Interrupts are off until irq_init's ei; the overlay was loaded with the RAM disk only (far_*), VRAM unmapped.
game_start:     call    launched        ; the boot's ACT_FILL (1 MB and more): the frame store's fill on the loading
                jr      nz, gs_play     ; screen, then the title (src/boot/boot.asm, docs/ramdisk-tiers.md section 11)
                ld      a, (HO_MAIN + HO_ACTION)
                cp      ACT_FILL
                jr      z, gs_fill
gs_play:        ld      a, OVL_LOW      ; the low code (M8a part 25: src/m4/ovl_low.asm; the launcher zeroed low RAM)
                call    ovl_load
                ld      a, OVL_LOW2
                call    ovl_load
                in      a, (0xe0)       ; VRAM on: the screen cleared, the palette set
                call    video_init
                in      a, (0xe1)       ; VRAM window off: 0x8000-0x9FFF is RAM for the renderer's tables
                call    tables_init
                xor     a               ; the frame store (1 MB and more: src/m4/fstore.asm; needs the shift tables): the
                ld      (ff_bw), a      ; boot filled it (ACT_FILL), so this only finds the marker; the harness fills
                ld      hl, OVL_WF + 0  ; here (no bar)
                call    fs_ovl
                call    irq_init
                call    sprite_init
                call    sword_init
                ld      hl, rc_run              ; run_rect lays from its recorded ops
                ld      (rc_hook + 1), hl
                ld      hl, 0
                ld      (TICKS), hl     ; (SCRIPT_PTR is left alone: the harness may set it before start)
                call    pr_build        ; the wall pattern's random table (src/m3/prbuild.asm; built at the first room before)
                call    game_init_h     ; kidsim's initial state (this overlay's entry 1)
                ld      a, (level_number)
                jp      load_level_h    ; (entry 0; returns to game.asm level_ready)
gs_fill:        call    tables_init     ; (the screen and its mode stay the loader's)
                ld      hl, (HO_MAIN + HO_BAR)  ; the loader's progress bar: the fill fills it
                ld      (ff_bptr), hl
                ld      hl, (HO_MAIN + HO_BAR + 2)
                ld      (ff_bw), hl             ; (ff_bw, ff_bcol)
                ld      hl, OVL_WF + 0
                call    fs_ovl
                ld      a, ACT_TITLE
                ld      b, 0
                jp      ho_swap
; fs_ovl: HL = an entry of the fill overlay (src/m4/ovl_fill.asm: OVL_WF + 0 fs_fill, + 3 fs_guard with A), on a RAM
; disk of 1 MB and more only (512 KB: nothing, not even the load)
fs_ovl:         ld      c, a
                ld      a, (HO_MAIN + HO_RDTOP)
                cp      FS_TOP1
                ret     c
                ld      a, OVL_FILL
                call    ovl_load                ; (keeps BC, DE, HL)
                ld      a, c
                jp      (hl)
                include "../m1/tables.asm"
                include "../m3/prbuild.asm"
                include "../m4/fsvars.inc"
pr_ok:          db      0                       ; (pr_build sets it; the game never reads it)

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
                call    launched                ; launched: the screen is black but for the launcher's "LOADING..." (PRES
                ret     z                       ; cleared it), which stays until the room draw covers it (row 100)
                ld      a, 0x80
                out     (PORT_WF), a
                ld      hl, VRAM
                ld      de, VRAM + 1
                ld      bc, 8000 - 1
                ld      (hl), 0xff
                ldir
                ret

irq_init:       call    snd_halt                ; (psg.asm: no stream, the PSG muted; interrupts stay off)
                ld      hl, isr                 ; IM2 with the PIO's vector 0 (below): one table entry
                ld      (VECTAB), hl
                ld      a, high VECTAB
                ld      i, a
                im      2
                ld      a, 0x04                 ; 8255 PC2 = 0: mask the counter 2 interrupt (the PIO's VBLN is the only
                out     (PORT_PPIC), a          ; interrupt source)
                ld      a, 0x74                 ; counter 1: mode 2, period 65536 lines, a free-running line counter
                out     (PORT_CTCC), a
                xor     a
                out     (PORT_CTC1), a
                out     (PORT_CTC1), a
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

; sprite_init: the kid's descriptor SPR_A (src/m4/sprite.asm)
sprite_init:    ld      hl, SPR_A
                ld      de, SPR_A + 1
                ld      bc, SD_SIZE - 1
                ld      (hl), 0
                ldir
                ld      iy, SPR_A
                ld      (iy+SD_BUF), low SPRBUF_A
                ld      (iy+SD_BUF+1), high SPRBUF_A
                ld      (iy+SD_LKEY), 0xff
                ld      (iy+SD_COMPOSE), low COMPOSE_A
                ld      (iy+SD_COMPOSE+1), high COMPOSE_A
                xor     a
                ld      (iy+SD_OW2), a  ; no old rect yet
                ret

; sword_init: the sword's, the guard's, the splashes' and the mirror image's descriptors (src/m4/overlay.asm)
sword_init:     ld      iy, SPR_S
                ld      (iy+SD_BUF), low SWORDBUF
                ld      (iy+SD_BUF+1), high SWORDBUF
                ld      (iy+SD_LKEY), 0xff
                xor     a
                ld      (UP_SHOWN), a
                dec     a
                ld      (TXT_GEN_SHOWN), a      ; (no text drawn yet: TEXT_GEN starts at 0)
                ld      ix, SPR_GS
                ld      hl, GSWBUF
                call    pi_one
                ld      ix, SPR_SP2
                ld      hl, SPLBUF2
                call    pi_one
                ld      ix, SPR_MI
                ld      hl, SPRBUF_MI
                call    pi_one
                ld      ix, SPR_G
                ld      hl, SPRBUF_G
                call    pi_one
                ld      ix, SPR_SP
                ld      hl, SPLBUF
pi_one:         ld      (ix+SD_BUF), l
                ld      (ix+SD_BUF+1), h
                ld      (ix+SD_LKEY), 0xff
                ret
