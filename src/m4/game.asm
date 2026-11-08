; M4: the prince in the game. The harness (tests/m4_game.py) or, later, the floppy loader fills the RAM disk:
;   page 0 dungeon env pack, page 1 shadow room (32 KB) + dungeon wall pack at 0x8000 + objects at 0xC000
;   + sword at 0xD000,
;   pages 2-3 kid pack, page 4 palace env pack, page 5 palace wall pack at 0, the 16 level blueprints at 0x4000
;   (2305 bytes each) and the directories (rebased to RAM-disk addresses) at 0xD100 (dungeon env), 0xD800
;   (dungeon wall), 0xDB00 (palace env), 0xE200 (palace wall), 0xE500 (objects), 0xE700 (kid), 0xEE00 (sword).
;   Nothing of the art is in main RAM: dir_entry reads a directory entry from the RAM disk when needed.
;   Page 6 from 0xE300: the code overlays (src/m4/ovl.asm: load_level and the full room draw run from there).
; A tick (4 frames): controls, kid logic (src/m4/kid.asm + objects.asm), room change or changed tiles redrawn,
; the kid and the falling floors (src/m4/sprite.asm), the hit points. After death the button restarts the
; level; the exit stairs lead to the next level.
VARS            equ     0x0800
GAME_BTNC       equ     1               ; room.asm tile_regen: the button picture cache (src/m4/anires.asm, M8a part 14)
FRAMES          equ     VARS + 0        ; 16-bit, incremented by the VBLN ISR
VB_LINE         equ     VARS + 2        ; 16-bit: 8253 counter 1 (HSYNC count, down) latched by the VBLN ISR
KEYMAT          equ     VARS + 0x60     ; 10 bytes
JOY             equ     VARS + 0x6a
INPUT           equ     VARS + 0x6b     ; bit0 left, 1 right, 2 up, 3 down, 4 button
ISRMARK         equ     VARS + 0x6c
LAST_TICK       equ     VARS + 0x6e     ; 16-bit
PREV_IN         equ     VARS + 0x70
SHOWN_ROOM      equ     VARS + 0x71     ; the room on screen (the logic's DRAWN_ROOM may have moved on)
TICKS           equ     VARS + 0x72     ; 16-bit tick counter (harness)
HP_SHOWN        equ     VARS + 0x74     ; 2: hit points as drawn (curr, max)
SCRIPT_PTR      equ     VARS + 0x76     ; 16-bit: 0 = read the joystick, else the next control byte (harness)
VS_IDX          equ     VARS + 0x78
VS_ROOM         equ     VARS + 0x79
VS_POS          equ     VARS + 0x7a
VS_TAG          equ     VARS + 0x7b
VS_KIND         equ     VARS + 0x7c
VS_PTR          equ     VARS + 0x7d     ; 16-bit
VS_PRESSED      equ     VARS + 0x5b
VS_LINKS        equ     VARS + 0x5c     ; 4: the shown room's links (left, right, up, down) for this snapshot/redraw
VIEW_SNAP       equ     0xf510          ; 53 x (tile, modifier), the buttons, the entries' tile addresses (view.asm; to 0xF5F4)
; M8a part 2: time-exact pacing (PACE_MODE 1, below): the tick clock and the skipped drawing (low RAM, runtime only)
NEXT_TICK       equ     0x01b8          ; 16-bit: the frame the next tick is due (mode 1)
SKIP_TICK       equ     0x01ba          ; mode 1: this tick is a whole tick late: its drawing may be skipped
SKIP_RUN        equ     0x01bb          ; ticks skipped in a row (at most SKIP_MAX)
SKIPPED         equ     0x01bc          ; the last tick's drawing was skipped (the next tick keeps its tile snapshot)
SKIP_MAX        equ     2
DEBT_MAX        equ     8               ; frames: later than this (a room change, a pause, a save) the clock is restarted
GAME_OVL        equ     1               ; the game: tables_init, pr_build run from the level-start overlay (gfx.asm, room.asm)
; the hit point strips' variables (src/m4/hpstrip.asm, the rare overlay; ghp_draw sets some before the overlay is loaded)
HP_VARS         equ     0x01c0          ; low RAM, runtime only (10 bytes)
hp_i            equ     HP_VARS + 0
hp_sh           equ     HP_VARS + 1
hp_xb           equ     HP_VARS + 2
hp_pat          equ     HP_VARS + 3     ; 16-bit
hp_n            equ     HP_VARS + 5
hp_nf           equ     HP_VARS + 6
hp_base         equ     HP_VARS + 7
hp_pf           equ     HP_VARS + 8     ; 16-bit
RD_SCRIPT       equ     0xf000          ; harness control bytes: RAM-disk page RD_LV_PAGE (after the directories)
RD_LV_PAGE      equ     5
RD_LV_ADDR      equ     0x4000
RD_DIR_OBJ      equ     0xe500          ; in page RD_LV_PAGE: objects (64 x 8), kid (220 x 8), sword (35 x 8) directories
RD_DIR_KID      equ     0xe700
RD_DIR_SWORD    equ     0xee00
RD_DIR_GUARD    equ     0x3400          ; in page RD_LV_PAGE: the six guard sets' directories, 0x120 apart (guard_dir_tbl)
VECTAB          equ     0xfe00          ; IM2: the one vector the PIO supplies (0): 0xFE00-0xFE01 (0xFE02-0xFEFF free)
STACK           equ     0xfe00
PORT_DMD        equ     0xce
PORT_SCRL       equ     0xcf
PORT_PAL        equ     0xf0
PORT_JOY1       equ     0xf0
PORT_KBD_COL    equ     0xd0
PORT_KBD_ROW    equ     0xd1
PIOA_CTRL       equ     0xfc
PORT_CTC1       equ     0xd5            ; 8253 counter 1, clocked by HSYNC
PORT_CTCC       equ     0xd7            ; 8253 control
PORT_PPIC       equ     0xd3            ; 8255 control (port C bit set/reset)

; ---- low block (0x1200-0x1FFF): code that does not fit below 0x8000. It never runs inside blit, where CG-ROM
; covers 0x1000-0x1FFF. (0x1000-0x11FF is the ROM monitor's work area while the tape loader runs: runtime data only.)
                org     0x1200
                include "../m4/kid2.asm"
                include "../m4/view.asm"
                include "../m4/sprite.asm"
                include "../m4/evres.asm"
                include "../m4/fx.asm"
end_of_low:
                if end_of_low > 0x2000
                .error the low block overlaps the program at 0x2000
                endif

                org     0x2000
start:          di
                ld      sp, STACK
                out     (0xe0), a
                out     (0xe1), a
                call    game_start      ; (stub: the level-start overlay, src/m4/gstart.asm) video, tables, interrupts, the
level_ready:    ld      hl, (FRAMES)    ; descriptors, PR_TAB, game_init, load_level (harness breakpoint: the level is
                                        ; loaded, nothing drawn yet)
                ld      (LAST_TICK), hl
mainloop:       ld      a, (PACE_MODE)
                or      a
                jr      nz, ml_pace
                ld      hl, (FRAMES)    ; mode 0: a tick every 4 frames at most; a late tick starts at once
                ld      de, (LAST_TICK)
                or      a
                sbc     hl, de
                ld      a, l
                cp      4
                jr      nc, ml_go
ml_halt:        halt
                jr      mainloop
; mode 1 (M8a part 2, a prototype): the logic runs on a fixed clock of 4 frames a tick (NEXT_TICK); a tick that starts a
; whole tick late (the last drawn ticks cost more than 4 frames) runs its logic without drawing, at most SKIP_MAX in a row,
; and the next drawn tick draws everything that changed since the last drawn one. Later than DEBT_MAX frames (a room
; change, a level load, a pause, a save) the clock restarts from now: no catching up after a stall.
ml_pace:        ld      hl, (FRAMES)
                ld      de, (NEXT_TICK)
                or      a
                sbc     hl, de          ; the lateness in frames (negative: not due yet)
                jp      m, ml_halt
                ld      a, h
                or      a
                jr      nz, ml_pstall
                ld      a, l
                cp      DEBT_MAX + 1
                jr      c, ml_p0
ml_pstall:      ld      hl, (FRAMES)
                ld      (NEXT_TICK), hl
                xor     a
ml_p0:          cp      4
                ld      a, 0
                jr      c, ml_p1
                ld      a, (SKIP_RUN)
                cp      SKIP_MAX
                ld      a, 0
                jr      nc, ml_p1
                inc     a
ml_p1:          ld      (SKIP_TICK), a
                ld      hl, (NEXT_TICK)
                ld      de, 4
                add     hl, de
                ld      (NEXT_TICK), hl
ml_go:          ld      hl, (FRAMES)
                ld      (LAST_TICK), hl
                ld      hl, (TICKS)
                inc     hl
                ld      (TICKS), hl
                ld      a, (SKIPPED)    ; (after a skipped drawing the snapshot stays: the changes accumulate)
                or      a
                call    z, view_snapshot
                call    dirty_reset
                call    get_controls    ; A = x, C = y, B = shift
                push    af
                ld      a, (KEYS)       ; Ctrl+G: save the game (the save overlay; SDLPoP's process_key runs before
                and     4               ; play_frame)
                call    nz, save_key
                pop     af
                call    kid_tick
                ld      a, (GAME_OVER)  ; game over (the time is up, the end, back to the title): the presentation
                or      a               ; program (no return), or without the launcher a new game from level 1
                jr      z, gmt_d
                call    game_over       ; (stub: the level-start overlay; A = 1)
                jr      gmt0
gmt_d:          ld      a, (LEVEL_SWITCH) ; the exit stairs after the wait on sound (sound.asm end_wait), the
                or      a               ; level 6 and 12 exits: the next level
                jr      z, gmt1
                ld      a, (HITP_MAX)   ; (it starts with the hit points the kid has)
                ld      (HITP_BEG_LEV), a
                xor     a
                ld      (CHECKPOINT), a
                ld      a, (NEXT_LEVEL)
                cp      15
                jr      c, gmt0
                ld      a, 1
gmt0:           ld      (NEXT_LEVEL), a
                call    load_level      ; (stub: src/m4/ovl.asm, the level-start overlay)
                jr      gmt2
gmt1:           ld      a, (WANT_RESTART) ; the button after death, Ctrl+A: the level again (or its checkpoint)
                ld      hl, IS_RESTART
                or      (hl)
                jr      z, gmt2
                ld      a, (level_number)
                jr      gmt0
gmt2:
                if defined CHEATS
                ld      a, (0x02a8)     ; (KEY_OPT bit 1: Shift+B, blind: no drawing)
                and     2
                jp      nz, tick_done
                endif
                ld      a, (SKIP_TICK)  ; mode 1: a late tick draws nothing unless the room or the screen's side changed, a
                or      a               ; flash or a hit (those ticks are drawn at once)
                jr      z, gmt_draw
                ld      a, (DRAWN_ROOM)
                ld      hl, SHOWN_ROOM
                cp      (hl)
                jr      nz, gmt_draw
                ld      a, (UPSIDE)
                ld      hl, UP_SHOWN
                cp      (hl)
                jr      nz, gmt_draw
                ld      a, (FLASH_NOW)
                or      a
                jr      nz, gmt_draw
                ld      a, (GUARDHP_DELTA) ; (the guard's hit: his strip keeps the hit points of the last tick with a delta,
                or      a               ; and his splash shows; the kid's hit flashes)
                jr      nz, gmt_draw
                ld      hl, SKIP_RUN
                inc     (hl)
                ld      a, 1
                ld      (SKIPPED), a
                jp      tick_done
gmt_draw:       xor     a
                ld      (SKIPPED), a
                ld      (SKIP_RUN), a
                ld      a, (UPSIDE)     ; the upside-down potion, death, a level start turned the screen: blit
                ld      hl, UP_SHOWN    ; patched (the room overlay's set_flip), the room drawn again
                cp      (hl)
                call    nz, flip_now
                ld      a, (DRAWN_ROOM) ; a room change (or a new level): draw the room
                ld      hl, SHOWN_ROOM
                cp      (hl)
                jr      z, gmt3
                ld      (hl), a
                call    draw_room_full  ; (the room overlay's rf_game: then sprite_forget, room_drawn's work)
                jr      gmt4
gmt3:           ld      a, 1            ; the tiles that changed this tick: into the shadow room only; their rects
                ld      (RR_SHONLY), a  ; go on the dirty list and draw_objects puts them on screen with the
                ld      hl, dirty_hook  ; prince and the falling floors over them (no flicker; anires.asm)
                ld      (RR_HOOK), hl
                call    view_redraw
                xor     a
                ld      (RR_SHONLY), a
gmt4:            call    draw_objects
                call    hp_draw
                call    text_chk        ; (fx.asm) the bottom text
                call    flash_tick      ; (fx.asm) the flash
tick_done:      nop                     ; harness breakpoint
                jp      mainloop
; PACE_MODE: 0 = every tick is drawn and paced to 4 frames at least (the release today, every test); 1 = time-exact (above).
; Tests poke it before the start; `make pace` builds a disk with 1 (pasmo --equ PACE=1) in build/pace.
                if defined PACE
PACE_MODE:      db      PACE
                else
PACE_MODE:      db      0
                endif
flip_now:       ld      (hl), a
                call    set_flip
                ld      a, 0xff
                ld      (SHOWN_ROOM), a
                ret

; ---------------------------------------------------------------- hit points (bottom strip, SDLPoP draw_kid_hp)
; the kid's icon i at x = 7 i, y = 194: full while i < curr, else empty; drawn in two compose chunks (bytes 0-7, 8-9).
; The guard's strip: overlay.asm ghp_draw (through hp_strip).
hp_draw:        call    ghp_draw
                ld      a, (HITP_CURR)
                ld      hl, HP_SHOWN
                cp      (hl)
                jr      nz, hp_redraw
                ld      a, (HITP_MAX)
                inc     hl
                cp      (hl)
                ret     z
hp_redraw:      ld      a, OVL_RARE     ; (stub) the strip drawn again: src/m4/hpstrip.asm, the rare overlay (W1); its
                call    ovl_w1          ; variables HP_VARS are low RAM; hp_strip's stub (ghp_draw): ovl.asm
                jp      OVL_W1 + 0

; get_controls: joystick / cursor keys, or the harness script (SCRIPT_PTR != 0: RAM-disk address in page 5 of the
; next byte = x+1 | (y+1)<<2 | shift<<4 | Ctrl+A<<5 | Ctrl+G<<7, before it optionally 0x40 + a key code (src/m4/keys.asm),
; 0xff = end of script, keep the last state). Out: A = x (-1/0/1 screen), C = y, B = shift (0/nonzero); KEYS: bit 0
; Ctrl+A, bit 2 Ctrl+G, bits 3-7 a key code (the keyboard: when pressed, once per press: src/m4/keyres.asm key_scan and
; the keys overlay; a script: every tick its bits are set).
get_controls:   ld      hl, (SCRIPT_PTR)
                ld      a, h
                or      l
                jr      z, gc_joy
                ex      de, hl
                ld      a, RD_LV_PAGE           ; the script is in the RAM disk (page 5 at RD_SCRIPT)
                call    far_seek
                ld      d, 0
gc_rd:          in      a, (RD_DATA)
                cp      0xff
                jr      z, gc_dec
                ld      hl, (SCRIPT_PTR)
                inc     hl
                ld      (SCRIPT_PTR), hl
                bit     6, a
                jr      z, gc_dec
                add     a, a            ; 0x40 + code: KEYS bits 3-7, the control byte follows
                add     a, a
                add     a, a
                ld      d, a
                jr      gc_rd
gc_dec:         ld      b, a
                and     0xa0            ; bit 5: Ctrl+A (restart the level) -> KEYS bit 0, bit 7: Ctrl+G (save) -> bit 2
                rlca
                rlca
                rlca
                or      d
                ld      (KEYS), a
                ld      a, b
                and     3
                dec     a
                ld      c, a            ; x
                ld      a, b
                rrca
                rrca
                and     3
                dec     a
                ld      e, a            ; y
                ld      a, b
                and     0x10
                ld      b, a
                ld      a, c
                ld      c, e
                ret
gc_joy:         call    read_inputs
                call    key_scan        ; (src/m4/keyres.asm: KEYS)
                ld      a, (INPUT)
                ld      b, a
                ld      c, 0
                ld      e, 0
                bit     0, b
                jr      z, gcj1
                ld      c, -1
gcj1:           bit     1, b
                jr      z, gcj2
                ld      c, 1
gcj2:           bit     2, b
                jr      z, gcj3
                ld      e, -1
gcj3:           bit     3, b
                jr      z, gcj4
                ld      e, 1
gcj4:           ld      a, b
                and     0x10
                ld      b, a
                ld      a, c
                ld      c, e
                ret

; ---------------------------------------------------------------- input, interrupt (as in M0; video_init and irq_init: src/m4/gstart.asm)
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
nd:             ld      a, (KEYMAT + 8)         ; SHIFT is the button (or the joystick's fire; SPACE shows the time)
                bit     0, a
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

isr:            push    af
                push    hl
                ld      hl, (FRAMES)
                inc     hl
                ld      (FRAMES), hl
                ld      a, 0x40                 ; latch counter 1: the line count at VBLN
                out     (PORT_CTCC), a
                in      a, (PORT_CTC1)
                ld      l, a
                in      a, (PORT_CTC1)
                ld      h, a
                ld      (VB_LINE), hl
                in      a, (PORT_DMD)
                ld      (ISRMARK), a
                jp      snd_isr                 ; (psg.asm: the PSG player's frame; it pops HL, AF and returns)
edge_bits:      db      0               ; key_scan: the key (key_tab's code) down at the last tick
; state_snap, snd_snap: the harness's 'S' and 'N' trace points (m4test takes snapshots there; the game has nothing to do)
state_snap:
snd_snap:       ret

; beam_lines: HL = lines since the last VBLN interrupt (the 8253 counter 1 counts HSYNCs down)
beam_lines:     di
                ld      a, 0x40
                out     (PORT_CTCC), a
                in      a, (PORT_CTC1)
                ld      e, a
                in      a, (PORT_CTC1)
                ld      d, a
                ld      hl, (VB_LINE)
                ei
                or      a
                sbc     hl, de
                ret

                include "../m1/far.asm"
                include "../m1/gfx.asm"
                include "../m3/room.asm"
                include "../m4/kid.asm"
                include "../m4/objects.asm"
                include "../m4/people2.asm"
                include "../m4/sndobj.asm"
                include "../m4/fslook.asm"
                include "../m4/spike.asm"
RL_ON           equ     1               ; M8a part 22: precomputed room lists (src/m3/rlists.asm; roomfull.asm draw_room_full)
RL_LEVEL        equ     level_number
RL_BP_PAGE      equ     RD_LV_PAGE
RL_BP_ADDR      equ     RD_LV_ADDR
RL_LOWCODE      equ     0x0500          ; rl_cmp in low RAM (src/m4/rllow.asm; 0x0500-0x077F, M8a part 19's free place)
RL_LOWN         equ     0x280           ; its size at most
RL_LOWBLK       equ     3               ; POP800.RLS's first blocks hold its image (tools/roomlists.py, mkgamedisk.py)
                include "../m3/rlists.asm"
                include "../m4/ovl.asm"
end_of_code:
                if end_of_code > OVL_W1
                .error the code overlaps the overlay window W1
                endif

; ---- second block: the data tables and more code (0xC000-0xEBFF)
                org     0xc000
block2:
                include "../../build/assets/tables.inc"
                include "../m4/overlay.asm"
                include "../m4/tcache.asm"
                include "../m4/rcache.asm"
                include "../m4/guard.asm"
                include "../m4/sound.asm"
                include "../m4/psg.asm"
                include "../m4/keyres.asm"
                include "../m4/gate.asm"
                include "../m4/anires.asm"
block2_end:
                if block2_end > LEVEL
                .error the tables block overlaps the level blueprint
                endif
                if flm_rect < GUARD_TABS + 88
                .error tcache.asm flm_rect overlaps guard.asm GUARD_TABS
                endif
