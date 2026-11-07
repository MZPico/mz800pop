; M4 logic test: runs the kid through a script of controls (one byte per tick at SCRIPT, or 0x40 + a key code first: bit0-1 x+1, bit2-3 y+1,
; bit4 shift, bit5 Ctrl+A; 0xff = end) and stops at `tick_done` after every tick so the harness can read the state
; (tests/m4_test.py). Levels come from the RAM disk as in the game (the 16 blueprints at RD_LV_PAGE:RD_LV_ADDR); a
; restart (Ctrl+A) or a level switch (the level 6 and 12 exits) loads the level again as the game does; a tick
; that restarts the level does not stop at tick_done (kidsim gives no trace lines for it). state_snap copies the
; 'S' trace line's fields (kidsim trace_state_line) to S_SNAP where the game's tick reaches that trace point;
; snd_snap the 'N' line (kidsim sound_line: queued, started, playing, stops) to N_SNAP at the end of snd_next.
VARS            equ     0x0800
FRAMES          equ     VARS + 0
SCRIPT          equ     0xe400          ; harness control bytes (0xE400-0xEBFF, after the tables block)
SCRIPT_PTR      equ     VARS + 8        ; 16-bit
VECTAB          equ     0xfe00
STACK           equ     0xfe00
PORT_DMD        equ     0xce
PORT_SCRL       equ     0xcf
PORT_PAL        equ     0xf0
PIOA_CTRL       equ     0xfc
DIR_KID         equ     0xf600          ; 220 entries x 8 (the level blueprint ends at 0xF501)
RD_LV_PAGE      equ     5               ; (game.asm's RAM-disk layout)
RD_LV_ADDR      equ     0x4000
S_SNAP          equ     0x02c0          ; 27 fields (ss_tab) + a counter of the snapshots
N_SNAP          equ     0x02b0          ; queued, started, playing, stops + a counter of the snapshots

                org     0x2000
start:          di
                ld      sp, STACK
                out     (0xe0), a
                out     (0xe1), a
                in      a, (0xe1)
                call    tables_init
                ld      hl, DIR_KID             ; the kid directory is in RAM here
                ld      (dir_tab + 3 * CH_KID + 1), hl
                xor     a
                ld      (S_SNAP + SS_N), a
                ld      (0x02a8), a             ; (KEY_OPT, src/m4/keys.asm: the sound on)
                call    game_init
                ld      a, (level_number)
                call    m4_load
                xor     a
                ld      (SND_STOPS), a  ; (kidsim counts the stops from the first level start on)
                ld      (N_SNAP + 4), a
                ld      hl, SCRIPT
                ld      (SCRIPT_PTR), hl
tick_loop:      ld      d, 0
tl_rd:          ld      hl, (SCRIPT_PTR)
                ld      a, (hl)
                cp      0xff
                jr      z, script_end
                inc     hl
                ld      (SCRIPT_PTR), hl
                bit     6, a
                jr      z, tl_go
                add     a, a                    ; 0x40 + key code (src/m4/keys.asm): KEYS bits 3-7, then the control byte
                add     a, a
                add     a, a
                ld      d, a
                jr      tl_rd
tl_go:          ld      b, a
                and     0x20
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
                ld      b, a            ; shift (nonzero)
                ld      a, c
                ld      c, e
                call    kid_tick
                ld      a, (GAME_OVER)          ; (Ctrl+R: as the game's main loop, GAME_OVER first)
                or      a
                jr      nz, tick_done
                ld      a, (IS_RESTART)
                or      a
                jr      nz, t_restart
tick_done:      nop                     ; harness breakpoint
                ld      a, (GAME_OVER)
                or      a
                jr      nz, script_end
                ld      a, (LEVEL_SWITCH)
                or      a
                jr      z, tick_loop
                call    snd_stop        ; the next level (kidsim play_level_2)
                ld      a, (HITP_MAX)
                ld      (HITP_BEG_LEV), a
                xor     a
                ld      (CHECKPOINT), a
                ld      a, (NEXT_LEVEL)
                call    m4_load
                jr      tick_loop
t_restart:      ld      a, (level_number)
                call    m4_load
                jr      tick_loop
script_end:     nop
                jr      script_end
; m4_load: A = level: blueprint from the RAM disk, level type, alter_mods, play_level (game: ovl_level.asm load_level)
m4_load:        ld      (level_number), a
                ld      e, a            ; 2305 * n = 2048 n + 256 n + n
                ld      d, 0
                add     a, a
                add     a, a
                add     a, a
                add     a, e
                ld      h, a
                ld      l, 0
                add     hl, de
                ld      de, RD_LV_ADDR
                add     hl, de
                ex      de, hl
                ld      a, RD_LV_PAGE
                ld      hl, LEVEL
                ld      bc, 2305
                call    far_copy
                ld      a, (level_number)
                ld      hl, level_type_tbl
                call    k_tbl
                ld      (LEVEL_TYPE), a
                call    alter_mods
                jp      play_level
; state_snap (guard.asm tick_post): the 'S' trace line's fields
state_snap:     ld      hl, ss_tab
                ld      de, S_SNAP
                ld      b, SS_N
ss1:            ld      a, (hl)
                inc     hl
                push    hl
                ld      h, (hl)
                ld      l, a
                ld      a, (hl)
                ld      (de), a
                inc     de
                pop     hl
                inc     hl
                djnz    ss1
                ex      de, hl
                inc     (hl)            ; (the counter)
                ret
; snd_snap (sound.asm snd_next's end: C queued, B started, E playing): the 'N' trace line's fields
snd_snap:       ld      hl, N_SNAP
                ld      (hl), c
                inc     hl
                ld      (hl), b
                inc     hl
                ld      (hl), e
                inc     hl
                ld      a, (SND_STOPS)
                ld      (hl), a
                inc     hl
                inc     (hl)            ; (the counter)
                xor     a
                ld      (SND_STOPS), a
                ret
ss_tab:         dw      level_number, NEXT_LEVEL, REM_MIN, REM_TICK, REM_TICK + 1, IS_SHOW_TIME, TEXT_REM, TEXT_REM + 1
                dw      TEXT_TOTAL, TEXT_TOTAL + 1, FEATHER, UPSIDE, FLASH_COLOR, FLASH_TIME, UNITED, LEVELDOOR_OPEN
                dw      CHECKPOINT, HITP_BEG_LEV, HITP_CURR, HITP_MAX, GUARDHP_CURR, GUARDHP_MAX, JUMPED_MIRROR
                dw      DEMO_TIME, DEMO_INDEX, SHADOW_INIT, HAVE_SWORD
SS_N            equ     ($ - ss_tab) / 2

                include "../m1/far.asm"
                include "../m1/gfx.asm"
                include "../m3/room.asm"
                include "../m4/kid.asm"
                include "../m4/objects.asm"
                include "../m4/buttons.asm"
                include "../m4/kid2.asm"
                include "../m4/sndobj.asm"
trace_cksum:    jp      room_checksum
; the PSG player (src/m4/psg.asm) is the game's: here no audio (the player never plays). The sound mode SND_MODE
; (psg.asm's address): 0 silent, 2 ticks ('# sound ticks' scripts: tests/m4_test.py pokes it before the start)
SND_MODE        equ     0x03c8 + 8
snd_start:
snd_halt:       ret
snd_playing:    xor     a
                ret
snd_onoff:                                      ; (Ctrl+S: no PSG here)
blind_set:      ret                             ; (CHEATS: no drawing here)
end_of_code:
                if end_of_code > 0x8000
                .error code too big
                endif

; ---- the game's overlay code (no loader here: included directly, in the compose buffers' place)
                org     0xa000
                include "../m3/roomfull.asm"
                include "../m3/altmods.asm"
rr_bkt_ent      equ     rr_bkt          ; (the M4 game: the room overlay's entry)
                include "../m4/levelstart.asm"
                include "../m4/evres.asm"
                include "../m4/events.asm"
                include "../m4/rare.asm"
                include "../m4/gleave.asm"
                include "../m4/genter.asm"
                include "../m4/shadinit.asm"
                include "../m4/keys.asm"
end_of_ovl:
                if end_of_ovl > 0xc000
                .error the overlay code is too big
                endif

; ---- second block: the data tables and the guard logic (0xC000-0xE3FF)
                org     0xc000
block2:
                include "../../build/assets/tables.inc"
                include "../m4/guard.asm"
                include "../m4/sound.asm"
block2_end:
                if block2_end > SCRIPT
                .error block 2 overlaps the harness script
                endif
