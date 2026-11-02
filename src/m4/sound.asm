; ---------------------------------------------------------------- the sound model (M7 step 2; block 2)
; Z80 port of tools/kidsim.py's sound model (SDLPoP seg000 play_sound / play_next_sound, seg009 stop_sounds): the game
; logic asks for sounds (snd_play), draw_game_frame starts the tick's request (snd_next), restarts, potions, the level
; door and level changes stop the playing sound (snd_stop). The request side runs in every mode. Whether a sound
; plays (docs/m7-design.md 5.3, 14) depends on SND_MODE (psg.asm):
;   0 silent  nothing plays (every harness test; the waits keep their silent rules: FEATHER_MUSIC, SND_ENDMUS)
;   1 hybrid  the launched game (game_init_h): play_next_sound, the feather fall and the level 1 crouch ask the ticks
;             model (snd_model: SND_LEFT, the playing sound's length in ticks, counted down at each tick start);
;             the death timer and the level end ask the PSG player (snd_live -> psg.asm snd_playing); the level end's
;             clock is charged as the ticks model counts it (END_OVER here, the charge in ovl_level.asm)
;   2 ticks   every wait asks the ticks model (the harness's '# sound ticks' scripts: kidsim's 'ticks' mode)
;   3 live    every wait and play_next_sound ask the player (tests/m7_sound.py)
; snd_next starts the sound on the PSG player (psg.asm snd_start); snd_stop stops and mutes it.
; The harness compares the 'N' line (queued started playing stops) every tick: m4test's snd_snap takes it at the end
; of snd_next (the game's snd_snap is a ret).
; Also here: the sound parts of the kid code (called from kid.asm, kid2.asm, guard.asm, evres.asm, which keep only
; a call or a jump in their place); the traps' sound parts are in src/m4/sndobj.asm (main code).

SND             equ     0x03c1          ; runtime state (low RAM; game_init clears it)
SND_NEXT        equ     SND + 0         ; next_sound: the tick's request so far (0xff none)
SND_CUR         equ     SND + 1         ; current_sound: the last sound started
SND_INT15       equ     SND + 2         ; sound_interruptible[15] (0 / 0x80; animate_leveldoor changes it)
SND_STOPS       equ     SND + 3         ; stop_sounds calls (the harness's 'N' line: m4test counts and clears it)
SND_SCREAM      equ     SND + 4         ; is_screaming (the falling scream, once per fall)
TB_SND          equ     SND + 5         ; trigger_button's play-sound argument
SND_ENDMUS      equ     SND + 6         ; the level's end music was asked for (the silent model's level end wait:
                                        ; it never ends; stop_sounds clears it)
SND_SIZE        equ     7
SND_LEFT        equ     0x03dd          ; the ticks model: ticks the playing sound has left (game_init / snd_stop: 0)
NEED_L1M        equ     0x03de          ; need_level1_music: 1 at a new game on level 1, 2 its music asked for, 0 done
END_OVER        equ     0x03df          ; hybrid: the ticks model's level end wait is over, the live one is not: the
                                        ; clock stops (guard.asm tick_post; play_level clears it)
SND_T12         equ     0x9b88          ; the ticks model's lengths per id 0-49 at 12 ticks a second, then at 10 (the
SND_T10         equ     SND_T12 + 50    ; kid's sword drawn); copied by game_init (levelstart.asm snd_ticks_tab, from
                                        ; tools/kidsim.py sound_ticks_tables); runtime RAM behind the VRAM window, read
                                        ; only by snd_next (never inside blit)
                if (SND_T12 / 256) != ((SND_T10 + 49) / 256)
                .error SND_T12/SND_T10 straddle a page (snd_next)
                endif

; snd_play (play_sound): A = sound id. The request is kept when nothing is queued yet or its priority is equal or
; higher (a lower rank) than the queued one's. Keeps BC, DE, HL.
snd_play:       push    hl
                push    bc
                ld      c, a
                ld      a, (SND_NEXT)
                inc     a
                jr      z, spl_set              ; nothing queued yet
                dec     a
                call    snd_ent
                and     0x7f
                ld      b, a                    ; rank of the queued sound
                ld      a, c
                call    snd_ent
                and     0x7f
                cp      b
                jr      z, spl_set
                jr      nc, spl_x               ; a lower priority: dropped
spl_set:        ld      a, c
                ld      (SND_NEXT), a
spl_x:          pop     bc
                pop     hl
                ret
; snd_ent: A = sound id -> A = snd_tab entry (bit 7 interruptible, bits 0-6 the priority rank); HL used
snd_ent:        ld      h, snd_tab / 256        ; (snd_tab does not straddle a page: see below)
                add     a, snd_tab % 256
                ld      l, a
                ld      a, (hl)
                ret
; snd_frame (draw_game_frame, after draw_people): the kid drawn as the united shadow (level 12: united_with_shadow
; == 2) asks for the end music, then play_next_sound
snd_frame:      ld      a, (UNITED)
                cp      2
                jr      nz, snd_next
                ld      a, (KID_REC + OF_ROOM)
                or      a
                jr      z, snd_next
                ld      hl, DRAWN_ROOM
                cp      (hl)
                ld      a, 41
                call    z, snd_play
; snd_next (play_next_sound): starts the queued sound when nothing plays, or when the playing sound is interruptible
; and of no higher priority; the queue is emptied; the ticks model's length starts (the tick rate: 10/s with the kid's
; sword drawn, else 12/s). Out (snd_snap): C queued, B started (0xff none), E playing.
snd_next:       call    snd_model
                ld      e, a
                ld      a, (SND_NEXT)
                ld      c, a
                ld      b, 0xff
                inc     a
                jr      z, snn_x                ; nothing asked for
                ld      a, e
                or      a
                jr      z, snn_go
                ld      a, (SND_CUR)            ; a sound plays: is it interruptible (bit 7) ...
                call    snd_ent
                ld      d, a
                ld      a, (SND_CUR)
                cp      15
                jr      nz, snn1
                ld      a, (SND_INT15)
                or      d
                ld      d, a
snn1:           bit     7, d
                jr      z, snn_x
                ld      a, c                    ; ... and the new one of equal or higher priority?
                call    snd_ent
                and     0x7f
                ld      l, a
                ld      a, d
                and     0x7f
                cp      l
                jr      c, snn_x
snn_go:         ld      hl, SND_T12
                ld      a, (KID_REC + OF_SWORD)
                cp      2                       ; (SWORD_DRAWN)
                jr      nz, snn2
                ld      l, SND_T10 % 256
snn2:           ld      a, c
                ld      (SND_CUR), a
                ld      b, a
                add     a, l
                ld      l, a
                ld      a, (hl)
                ld      (SND_LEFT), a
                ld      a, b
                call    snd_start               ; (psg.asm: the player starts it; keeps BC, DE)
snn_x:          ld      a, 0xff
                ld      (SND_NEXT), a
                jp      snd_snap                ; (m4test: the 'N' trace snapshot; the game: ret)
; snd_stop (stop_sounds): the playing sound ends. Out: A = 0. Keeps BC, DE, HL.
snd_stop:       push    hl
                ld      hl, SND_STOPS
                inc     (hl)
                pop     hl
                call    snd_halt                ; (psg.asm: the stream stops, the PSG is muted)
                xor     a
                ld      (FEATHER_MUSIC), a      ; (the silent model's feather fall wait: kidsim feather_music)
                ld      (SND_ENDMUS), a         ; (the silent model's level end wait)
                ld      (SND_LEFT), a           ; (the ticks model)
                ret
; snd_model: check_sound_playing for play_next_sound and the tick-counted waits: A = 1 / NZ while a sound plays.
; Silent: never; hybrid, ticks: the ticks model (SND_LEFT); live: the player. The ring is refilled first (snd_fill,
; in snd_playing: play_next_sound asks once a tick).
snd_model:      call    snd_playing             ; (psg.asm: the ring refilled; A = the player's state, 0 when silent)
                ld      l, a
                ld      a, (SND_MODE)
                cp      3
                ld      a, l
                jr      z, snm_x                ; live: the player
                ld      a, (SND_MODE)
                or      a
                ret     z                       ; silent
snd_ticks:      ld      a, (SND_LEFT)
snm_x:          or      a
                ret     z
                ld      a, 1
                ret
; snd_live: check_sound_playing for the live waits (the death timer, the level end): A = 1 / NZ while a sound plays.
; Hybrid, live: the player; ticks: the ticks model; silent: never.
snd_live:       ld      a, (SND_MODE)
                rrca
                jp      c, snd_playing          ; (hybrid, live: bit 0)
                or      a
                ret     z
                jr      snd_ticks
; feather_snd (timers: the feather fall ends when no sound plays): A = 1 / NZ while one plays. Silent: the feather
; music until a stop_sounds (FEATHER_MUSIC: the 225-tick cap ends the fall)
feather_snd:    ld      a, (SND_MODE)
                or      a
                jr      nz, snd_model
                ld      a, (FEATHER_MUSIC)
                or      a
                ret
; death_wait (kid.asm kid_tick's death timer): SDLPoP stops the timer while a sound plays, unless it is the gate
; opening (5); at alive 7 (the death music was asked for at 6) while any sound plays. Out: NC, A = 0: the timer runs;
; C, A = K_ALIVE: it waits (the restart button still works from alive 7). Silent: only the feather music waits.
death_wait:     ld      a, (SND_MODE)
                or      a
                jr      nz, dw1
                ld      a, (FEATHER_MUSIC)
                or      a
                ret     z                       ; (NC)
dw_hold:        ld      a, (K_ALIVE)
                scf
                ret
dw1:            call    snd_live
                ret     z                       ; (A = 0, NC)
                ld      a, (SND_CUR)
                cp      5
                jr      nz, dw_hold
                ld      a, (K_ALIVE)
                cp      7
                jr      nz, dw_run
                xor     a                       ; (alive 7, the gate sound: is_show_time = 0, then it waits)
                ld      (IS_SHOW_TIME), a
                jr      dw_hold
dw_run:         xor     a
                ret
; crouch_music (kid.asm control_crouched; seg005 control_crouched): the level 1 start keeps the kid crouched until its
; music (25) ends: NZ = no control this tick. Silent: never (kidsim: the oracle hook skips it)
crouch_music:   ld      hl, NEED_L1M
                ld      a, (hl)
                or      a
                ret     z
                ld      a, (SND_MODE)
                or      a
                jr      z, cm_clr
                ld      a, (level_number)
                dec     a
                jr      nz, cm_clr
                call    snd_model
                ret     nz                      ; (the music or another sound plays: wait)
                ld      hl, NEED_L1M
                dec     (hl)
                jr      nz, cm_end
                ld      (hl), 2                 ; (1: the music starts)
                ld      a, 25
                call    snd_play
                or      1
                ret
cm_end:         ld      (hl), 0                 ; (2: it ended; the controls come back next tick)
                inc     a                       ; (A = 1, NZ)
                ret
cm_clr:         xor     a
                ld      (hl), a
                ret
; end_wait (tick_post, before draw_game_frame): play_level_2's level change: a level done (the stairs) changes now
; unless a sound plays (silent model: the end music never ends, kidsim end_music; level 13 has none). Hybrid: when the
; ticks model's sound has ended but the live one plays on, END_OVER stops the clock (the ticks mode would have changed
; the level by now); the level change charges what the ticks model still had (ovl_level.asm load_level_h)
end_wait:       ld      a, (LEVEL_DONE)
                or      a
                ret     z
                ld      a, (SND_MODE)
                or      a
                jr      nz, ew1
                ld      a, (SND_ENDMUS)
                or      a
                ret     nz
ew_go:          ld      a, 1
                ld      (LEVEL_SWITCH), a
                ret
ew1:            call    snd_live
                jr      z, ew_go
                ld      a, (SND_MODE)
                dec     a
                ret     nz                      ; (hybrid only)
                ld      a, (SND_LEFT)
                or      a
                ret     nz
                inc     a
                ld      (END_OVER), a
                ret
; sound ranks (SDLPoP sound_prio_table, PoP 1.3 values = FIX_SOUND_PRIORITIES, ranked: only the order matters) with
; bit 7 = sound_interruptible, for the ids 0-49 the game logic asks for (tools/kidsim.py SOUND_PRIO)
                if (($ + 49) / 256) != ($ / 256)
                ds      256 - ($ % 256)         ; (the next page: today only in m4test's layout)
                endif
snd_tab:        db      0x09, 0x8c, 0x8d, 0x93, 0x8f, 0x90, 0x0e, 0x8e, 0x91, 0x92, 0x84, 0x87, 0x83, 0x82, 0x14, 0x15
                db      0x96, 0x97, 0x18, 0x99, 0x9c, 0x9d, 0x9e, 0x9f, 0x01, 0x01, 0x01, 0x01, 0x01, 0x88, 0x01, 0x01
                db      0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x01, 0x01, 0x01, 0x01, 0x1a, 0x1b, 0x05, 0x86
                db      0x0a, 0x8b
snd_tab_end:
                if (snd_tab / 256) != ((snd_tab_end - 1) / 256)
                .error snd_tab straddles a page (snd_ent: move it)
                endif

; ================================================================ the call sites' sound parts
; seq_sound (play_seq's sound command, kid.asm ps_skip1): A = 0 silent, 1 footstep, 2 bump (these three let a guard
; notice the kid), 3 drink, 4 the level's end music (level 4: the shadow's; none on 13 and 15). Keeps HL.
seq_sound:      cp      3
                jr      nc, sqs3
                push    af
                ld      a, 1
                ld      (IS_GUARD_NOTICE), a
                pop     af
                or      a
                ret     z
                dec     a
                ld      a, 23
                jp      z, snd_play
                ld      a, 8
                jp      snd_play
sqs3:           jr      nz, sqs4
                ld      a, 18
                jp      snd_play
sqs4:           cp      4
                ret     nz
                ld      a, (level_number)
                cp      13
                ret     z
                cp      15
                ret     z
                ld      a, 1
                ld      (SND_ENDMUS), a
                ld      a, (level_number)
                cp      4
                ld      a, 32
                jp      z, snd_play
                ld      a, 41
                jp      snd_play
; df_pre (do_fall's start): the scream once per fall (fall_y >= 31). Out: A = K_ROW
df_pre:         ld      a, (SND_SCREAM)
                or      a
                jr      nz, dfp1
                ld      a, (K_FALLY)
                bit     7, a
                jr      nz, dfp1
                cp      31
                jr      c, dfp1
                ld      a, 1
                ld      (SND_SCREAM), a
                call    snd_play                ; (sound 1: falling)
dfp1:           ld      a, (K_ROW)
                ret
; land_pre (land's start): the scream is over. Out: A = K_ROW
land_pre:       xor     a
                ld      (SND_SCREAM), a
                ld      a, (K_ROW)
                ret
; kill_snd: A = sound; take_hp(100) (spiked, chomped, crushed after a fall)
kill_snd:       push    af
                ld      a, 100
                call    take_hp
                pop     af
                jp      snd_play
; ch_wall_snd (control_hanging against a wall): the bump unless the grab is fresh
ch_wall_snd:    ld      a, (GRAB_TIMER)
                or      a
                ld      a, 8
                call    z, snd_play
                ld      a, SQ_HANG_WALL
                jp      seqtbl_offset_char
; grab_snd (check_grab: a ledge grabbed in a fall)
grab_snd:       ld      a, 12
                ld      (GRAB_TIMER), a
                xor     a
                ld      (SND_SCREAM), a
                ld      a, 9
                jp      snd_play
; death_chk (kid_tick's death timer, Char = the kid): alive 6 the death music (not on levels 0 and 15: by the
; shadow, in a fight, or the regular one), alive 7 the text
death_chk:      ld      a, (K_ALIVE)
                cp      7
                jp      z, death_text
                cp      6
                ret     nz
                ld      a, (level_number)
                or      a
                ret     z
                cp      15
                ret     z
                ld      a, (GUARD_REC + OF_CHARID)
                cp      CHARID_SHADOW
                ld      a, 32
                jp      z, snd_play
                ld      a, (HOLDING_SWORD)
                or      a
                ld      a, 28
                jp      nz, snd_play
                ld      a, 24
                jp      snd_play
; hbs_snd (hurt_by_sword's end): the kid's or the guard's hurt sound, then the sequence
hbs_snd:        ld      a, (K_CHARID)
                or      a
                ld      a, 13
                jr      z, hbs_s1
                dec     a
hbs_s1:         call    snd_play
                jp      play_seq
; chu_snd (check_hurting, Char poking (frame 154) out of hurting range): the sword swishes unless Opp parries or is hurt
chu_snd:        ld      a, (K_DIR)
                cp      DIR_NONE
                ret     z
                ld      a, (OPP_REC + OF_FRAME)
                cp      161
                ret     z
                ld      a, (OPP_REC + OF_ACTION)
                cp      AC_HURT
                ret     z
                ld      a, 11
                jp      snd_play
; sword_vs_sword (check_sword_vs_sword): a blade meets a blade (frame 167)
sword_vs_sword: ld      a, (KID_REC + OF_FRAME)
                cp      167
                jr      z, svs1
                ld      a, (GUARD_REC + OF_FRAME)
                cp      167
                ret     nz
svs1:           ld      a, 10
                jp      snd_play
