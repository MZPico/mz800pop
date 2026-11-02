; ---------------------------------------------------------------- level events: the resident per-tick part (M5)
; Z80 port of tools/kidsim.py's time limit (seg008 show_time), the bottom text and flash timers (seg000
; draw_game_frame) and the death text (seg006 play_kid). Logic only: the texts and the flashes are drawn by game.asm
; (text_chk, flash_tick) from TEXT_GEN and FLASH_NOW. The state is the EV block (objects.asm). The rarer events run from the events overlay
; (src/m4/events.asm); the level start from the level-start overlay (src/m4/levelstart.asm).

; erase_text: no bottom text. set_text: HL = ticks the text stays (text_time_remaining = text_time_total); TEXT_GEN
; tells the drawing a text was set or erased (game.asm text_chk)
erase_text:     ld      hl, 0
set_text:       ld      (TEXT_REM), hl
                ld      (TEXT_TOTAL), hl
                ld      hl, TEXT_GEN
                inc     (hl)
                ret
; death_text: the kid has been dead long enough (alive = 7): game over if the time is up, then the text
death_text:     ld      a, (REM_MIN)
                or      a
                jr      nz, dtx1
                ld      a, GO_EXPIRED
                ld      (GAME_OVER), a
dtx1:           ld      a, (level_number)
                or      a
                jr      z, dtx36
                cp      15
                jr      z, dtx36
                ld      hl, 288                 ; "Press Button to Continue"
                jr      set_text
dtx36:          ld      hl, 36
                jr      set_text

; show_time (end of play_frame): the clock runs while the kid lives (levels 1-12, 13 until Jaffar is dead);
; minutes 60, 55, ... and the last five are announced, the last minute every second
show_time:      ld      a, (KID_REC + OF_ALIVE)
                bit     7, a
                jr      z, sht_msg
                ld      a, (REM_MIN)
                or      a
                jr      z, sht_msg
                ld      a, (level_number)
                cp      13
                jr      c, sht_run
                jr      nz, sht_msg
                ld      a, (LEVELDOOR_OPEN)
                or      a
                jr      nz, sht_msg
sht_run:        ld      hl, (REM_TICK)
                dec     hl
                ld      (REM_TICK), hl
                ld      a, h
                or      l
                jr      nz, sht_sec
                ld      hl, 719                 ; a minute = 720 ticks
                ld      (REM_TICK), hl
                ld      hl, REM_MIN
                dec     (hl)
                ld      a, (hl)
                or      a
                jr      z, sht_msg
                cp      6
                jr      c, sht_show
sht_m5:         sub     5
                jr      z, sht_show
                jr      nc, sht_m5
                jr      sht_msg
sht_sec:        ld      a, (REM_MIN)            ; the last minute: every 12 ticks
                dec     a
                jr      nz, sht_msg
                ld      de, 12                  ; (carry clear)
sht_d12:        sbc     hl, de
                jr      nc, sht_d12
                add     hl, de
                ld      a, h
                or      l
                jr      nz, sht_msg
                ld      (TEXT_REM), hl          ; (0: the message replaces the text)
sht_show:       ld      a, 1
                ld      (IS_SHOW_TIME), a
sht_msg:        ld      a, (IS_SHOW_TIME)
                or      a
                ret     z
                ld      hl, (TEXT_REM)
                ld      a, h
                or      l
                ret     nz
                ld      hl, 24
                call    set_text
                ld      a, (REM_MIN)
                dec     a
                jr      nz, sht_x
                ld      hl, (REM_TICK)          ; "1 SECOND LEFT" (rem_tick 11..22) stays 12 ticks
                ld      de, 11
                or      a
                sbc     hl, de
                jr      c, sht_x
                ld      de, 12
                sbc     hl, de
                jr      nc, sht_x
                ld      hl, 12
                call    set_text
sht_x:          xor     a
                ld      (IS_SHOW_TIME), a
                ret

; draw_game_frame (after the tick, not when a level starts next): the kid who jumped through the mirror (level 4),
; the bottom text's timer (the death text ending means back to the title), the flash's timer and the flash to show
draw_game_frame:
                ld      a, (JUMPED_MIRROR)
                or      a
                call    nz, jump_through_mirror ; (the events overlay)
                call    snd_frame               ; (sound.asm: the union's music, play_next_sound)
                ld      hl, (TEXT_REM)
                ld      a, h
                or      a
                jr      nz, dgf_dec
                or      l
                jr      z, dgf_fl
                dec     a
                jr      nz, dgf_dec
                ld      hl, (TEXT_TOTAL)        ; the text ends
                ld      de, 36
                or      a
                sbc     hl, de
                jr      z, dgf_title
                ld      de, 288 - 36
                or      a
                sbc     hl, de
                jr      z, dgf_title
                call    erase_text
                jr      dgf_fl
dgf_title:      ld      a, GO_TITLE             ; the death text ran out
                ld      (GAME_OVER), a
                jr      dgf_fl
dgf_dec:        ld      hl, (TEXT_REM)          ; (kidsim's text_time_total 1188 case never occurs)
                dec     hl
                ld      (TEXT_REM), hl
dgf_fl:         ld      hl, FLASH_TIME          ; flash_if_hurt / remove_flash_if_hurt: the flash shown (drawing)
                ld      a, (hl)
                or      a
                jr      z, dgf_hurt
                dec     (hl)
                ld      a, (FLASH_COLOR)
                ld      (FLASH_NOW), a
                ret
dgf_hurt:       ld      a, (HITP_DELTA)         ; the kid hurt: bright red
                rla
                ret     nc
                ld      a, 12
                ld      (FLASH_NOW), a
                ret
