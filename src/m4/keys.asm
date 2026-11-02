; ---------------------------------------------------------------- the keys' logic (M7 step 10, docs/m7-design.md §6, §18)
; key_logic: SDLPoP process_key's effects at the point the oracle's hook runs them (kid.asm kid_tick: the control point,
; Char = the Kid), for this tick's KEYS: bit 0 Ctrl+A, bit 2 Ctrl+G (game.asm: at the tick start, not here), bits 3-7 a
; key code. The keyboard (the keys overlay, src/m4/ovl_keys.asm key_read) and the harness script both set KEYS. Runs from
; window W1 in the game (no other W1 overlay is called from here), m4test includes it directly.
; Assembled with CHEATS=1 (make cheats): the cheats too; the release has none of them.
KEY_SPACE       equ     1
KEY_SHIFT_L     equ     2
KEY_ENTER       equ     3
KEY_CTRL_R      equ     4
KEY_CTRL_S      equ     5
KEY_CTRL_V      equ     6
KEY_PAUSE       equ     7
KEY_OPT         equ     0x02a8                  ; HO_MAIN + HO_OPTIONS (src/boot/launch.inc): bit 0 the sound is off
TXT_MSG_S_OFF   equ     3                       ; TEXT_MSG (src/m4/text.asm)
TXT_MSG_S_ON    equ     4
TXT_MSG_VERSION equ     5
TXT_MSG_PAUSED  equ     6
TXT_MSG_TIMER   equ     7                       ; (CHEATS)
key_logic:      ld      a, (KEYS)               ; Ctrl+A: the level restarts (not on level 15)
                rrca
                jr      nc, kl1
                ld      a, (level_number)
                cp      15
                call    nz, kl_restart
kl1:            ld      a, (KEYS)
                rrca
                rrca
                rrca
                and     31
                ret     z
                dec     a
                jr      nz, kl2
                inc     a                       ; SPACE: the time left at this tick's show_time
                ld      (IS_SHOW_TIME), a
                ret
kl2:            dec     a
                jr      z, kl_shift_l
                dec     a
                jr      z, kl_enter
                dec     a
                jr      z, kl_title
                dec     a
                jr      z, kl_sound
                dec     a
                ld      a, TXT_MSG_VERSION
                jr      z, kl_msg
                ld      a, (KEYS)
                rrca
                rrca
                rrca
                and     31
                cp      KEY_PAUSE
                jp      z, erase_text           ; (do_paused's erase_bottom_text at the resume)
                if defined CHEATS
                jp      kl_cheat
                else
                ret
                endif
kl_restart:     call    snd_stop
                inc     a
                ld      (IS_RESTART), a
                ret
; Shift+L: the next level (levels below 4, SDLPoP's shift_L_allowed_until_level), the time cut to 15 minutes; the level
; changes after this tick (play_level_2: the sounds were stopped)
kl_shift_l:     ld      a, (level_number)
                if defined CHEATS
                cp      15
                jr      z, kl_stop
                cp      14
                jr      nz, ksl1
                xor     a                       ; (14 -> 1)
ksl1:           inc     a
                ld      (NEXT_LEVEL), a
                else
                cp      4
                ret     nc
                inc     a
                ld      (NEXT_LEVEL), a
                ld      a, (REM_MIN)
                cp      16
                jr      c, kl_stop
                ld      a, 15
                ld      (REM_MIN), a
                ld      hl, 719
                ld      (REM_TICK), hl
                endif
kl_stop:        call    snd_stop
                inc     a
                ld      (LEVEL_SWITCH), a
                ret
; Enter while dead: Ctrl+A (process_key: rem_min != 0, Kid.alive > 6)
kl_enter:       ld      a, (REM_MIN)
                or      a
                ret     z
                ld      a, (K_ALIVE)
                bit     7, a
                ret     nz
                cp      7
                ret     c
                ld      a, (level_number)
                cp      15
                ret     z
                jr      kl_restart
; Ctrl+R: back to the title (the tick ends as a restart's; the main loop sees GAME_OVER first)
kl_title:       ld      a, GO_TITLE
                ld      (GAME_OVER), a
                ld      (IS_RESTART), a
                ret
; Ctrl+S: the sound on / off (snd_onoff: the PSG only, the sound model goes on) and its text
kl_sound:       ld      hl, KEY_OPT
                ld      a, (hl)
                xor     1
                ld      (hl), a
                call    snd_onoff
                ld      a, (KEY_OPT)
                rrca
                ld      a, TXT_MSG_S_OFF
                jr      c, kl_msg
                ld      a, TXT_MSG_S_ON
; kl_msg: A = a TEXT_MSG: the text for 24 ticks (need_show_text)
kl_msg:         push    af
                ld      hl, 24
                call    set_text
                ld      a, (TEXT_GEN)
                ld      (TEXT_MSG_GEN), a
                pop     af
                ld      (TEXT_MSG), a
                ret

                if defined CHEATS
; ---------------------------------------------------------------- the cheats (SDLPoP process_key, cheats_enabled)
KEY_C_KILL      equ     8
kl_cheat:       sub     KEY_C_KILL
                ret     c
                ld      hl, ck_tab
                add     a, a
                ld      e, a
                ld      d, 0
                add     hl, de
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a
                jp      (hl)
ck_tab:         dw      ck_kill, ck_revive, ck_plus, ck_minus, ck_life, ck_heal, ck_feather, ck_flip
                dw      ck_view, ck_view, ck_view, ck_view, ck_back, ck_blind, ck_timer
; K: the guard dies (not a skeleton)
ck_kill:        ld      a, (GUARD_REC + OF_CHARID)
                cp      CHARID_SKELETON
                ret     z
                ld      a, (GUARDHP_CURR)
                neg
                ld      (GUARDHP_DELTA), a
                xor     a
                ld      (GUARD_REC + OF_ALIVE), a
                ret
; R: back to life, at once (SDLPoP keeps resurrect_time 20 ticks of no traps and no sword hurts: not ported)
ck_revive:      ld      a, (K_ALIVE)
                or      a
                ret     z
                ret     m
                ld      a, 0xff
                ld      (K_ALIVE), a
                call    erase_text
                call    snd_stop
                ld      a, (HITP_MAX)
                ld      (HITP_DELTA), a
                ld      a, SQ_STAND
                call    seqtbl_offset_char
                ld      hl, K_X
                ld      a, (hl)
                add     a, 8
                ld      (hl), a
                call    play_seq
                jp      load_fram_det_col
; + / -: minutes; the time shown at once
ck_plus:        ld      hl, REM_MIN
                inc     (hl)
                jr      ck_show
ck_minus:       ld      hl, REM_MIN
                ld      a, (hl)
                cp      2
                jr      c, ck_show
                dec     (hl)
ck_show:        ld      hl, 0
                ld      (TEXT_REM), hl
                ld      (TEXT_TOTAL), hl
                ld      hl, TEXT_GEN
                inc     (hl)
                ld      a, 1
                ld      (IS_SHOW_TIME), a
                ret
; Shift+T: a hit point more (no stop_sounds, unlike the potion)
ck_life:        ld      a, 30
                call    snd_play
                ld      bc, 4 * 256 + COLOR_RED
                call    set_flash
                ld      a, (HITP_MAX)
                inc     a
                cp      11
                jr      c, ckl1
                ld      a, 10
ckl1:           ld      (HITP_MAX), a
                ld      hl, HITP_CURR
                sub     (hl)
                ld      (HITP_DELTA), a
                ret
; Shift+S: a hit point back
ck_heal:        ld      a, (HITP_MAX)
                ld      hl, HITP_CURR
                cp      (hl)
                ret     z
                ld      a, 33
                call    snd_play
                ld      a, 1
                ld      (HITP_DELTA), a
                ld      bc, 2 * 256 + COLOR_RED
                jp      set_flash
; Shift+W: the feather fall (as the potion)
ck_feather:     call    snd_stop
                ld      a, 39
                call    snd_play
                ld      a, 1
                ld      (FEATHER), a
                ld      (FEATHER_MUSIC), a
                ld      bc, 3 * 256 + COLOR_GREEN
                jp      set_flash
; Shift+I: the screen upside down
ck_flip:        ld      a, (UPSIDE)
                cpl
                ld      (UPSIDE), a
                ret
; H, J, U, N: the room to the left, right, above, below the room on screen
ck_view:        ld      a, (KEYS)
                rrca
                rrca
                rrca
                and     3                       ; (codes 16-19)
                ld      c, a
                ld      a, (DRAWN_ROOM)
                dec     a
                ld      l, a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                ld      b, 0
                add     hl, bc
                ld      bc, LEVEL + 1952
                add     hl, bc
                ld      a, (hl)
                ld      (NEXT_ROOM), a
                ret
; Ctrl+B: back to the kid's room
ck_back:        ld      a, (K_ROOM)
                ld      (NEXT_ROOM), a
                ret
; Shift+B: blind: the playfield black, no drawing (game.asm main loop, CHEATS only) until Shift+B again
ck_blind:       ld      hl, KEY_OPT
                ld      a, (hl)
                xor     2
                ld      (hl), a
                jp      blind_set
; T: the time as a text for 24 ticks (SDLPoP's debug timer stays on screen)
ck_timer:       ld      a, TXT_MSG_TIMER
                jp      kl_msg
                endif
