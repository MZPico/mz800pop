; ---------------------------------------------------------------- the traps' sound parts (M7 step 2; main code)
; The sounds of SDLPoP seg007's animated tiles as tools/kidsim.py asks for them (src/m4/sound.asm has the model):
; called from objects.asm, which keeps only a call or a jump in their place. In the main code (not block 2, which
; keeps its room for the M7 PSG player).

; anc_snd (animate_chomper): A = the new frame: frame 2 snaps. Out: A kept, HL = O_T2
anc_snd:        cp      2
                push    af
                ld      a, 47
                call    z, snd_play
                pop     af
                ld      hl, O_T2
                ret
; animate_door's sounds (objects.asm an_door): B = the new modifier, C = the anim type
door_fast_end:  ld      a, 6                    ; fast closing done
                call    snd_play
                jp      trob_kill
door_closing:   ld      a, b
                or      a
                jr      z, gate_stop
                cp      188
                ret     nc
                and     3
                cp      3
                ret     nz
                ld      a, 4
                jr      door_vis
door_open:      ld      a, b                    ; opening (types 1, 2)
                cp      188
                jr      nc, dop1
                and     7
                ret     nz
                ld      a, 5
                jp      snd_play
dop1:           ld      a, c
                cp      2
                jr      nc, dop_perm
                ld      a, 238                  ; open: it starts closing
                ld      (O_CMOD), a
                call    trob_type
                ld      (hl), 0
                ld      a, 7
                jp      snd_play
dop_perm:       ld      a, 0xff                 ; permanently open
                ld      (O_CMOD), a
gate_stop:      call    trob_kill
                ld      a, 7
; door_vis (play_door_sound_if_visible): A = sound; only for a gate in the drawn room (not its column 9) or column 9
; of the room on its left (level 3: room 2 always)
door_vis:       push    af
                ld      a, (DRAWN_ROOM)
                call    links_of                ; C = room_L (0 without a drawn room)
                ld      hl, (TROB_P)
                ld      a, (level_number)
                cp      3
                jr      nz, dv1
                ld      a, (hl)
                cp      2
                jr      z, dv_play
dv1:            inc     hl
                ld      a, (hl)
                call    mod10
                ld      b, a                    ; column
                dec     hl
                ld      a, (hl)                 ; room
                cp      c
                jr      nz, dv2
                ld      a, b
                cp      9
                jr      z, dv_play
                jr      dv_no
dv2:            ld      hl, DRAWN_ROOM
                cp      (hl)
                jr      nz, dv_no
                ld      a, b
                cp      9
                jr      z, dv_no
dv_play:        pop     af
                jp      snd_play
dv_no:          pop     af
                ret
; animate_leveldoor's sounds: ldoor_close: A = the closing door's new modifier (not stored yet); ldoor_slide: opening
ldoor_close:    ld      (O_CMOD), a
                bit     7, a
                jr      nz, ldc_end
                call    trob_type
                cp      4
                ret     nz
                ld      a, 0x80                 ; sliding (closing): interruptible
                ld      (SND_INT15), a
                ld      a, 15
                jp      snd_play
ldc_end:        xor     a
                ld      (O_CMOD), a
                call    trob_kill
                ld      a, 14
                jp      snd_play
ldoor_slide:    xor     a                       ; sliding (opening): not interruptible
                ld      (SND_INT15), a
                ld      a, 15
                jp      snd_play
; ls_snd (loose_shake): A = the shake sound (20-22), then the wasted random number
ls_snd:         call    snd_play
                ld      a, 2
                jp      prandom
; sas_snd (start_anim_spike: the spikes start): BC = room, pos
sas_snd:        ld      a, 49
                call    snd_play
                ld      a, 1
                jp      add_trob
; tb_notice (trigger_button: the button goes down): a guard notices, the click if trigger_button was asked to
tb_notice:      ld      a, 1
                ld      (IS_GUARD_NOTICE), a
                ld      a, (TB_SND)
                or      a
                ret     z
                ld      a, 3
                jp      snd_play
; knock_snd (move_loose: a falling floor crashes): A = room, B = row for do_knock
knock_snd:      push    af
                ld      a, 2
                call    snd_play
                pop     af
                jp      do_knock

                if defined GAME_OVL             ; (m4test: a stub, src/m4/m4test.asm)
; snd_again (sound.asm snd_next starts a sound; main code: block 2 is full): A = B = the sound id. When the player is
; still copying a stream (MF_LEFT != 0) and its copy position MF_SRC lies inside this id's stream, the id plays already:
; it goes on (the looping level door's sliding 15, which animate_leveldoor asks for every tick of the opening and the
; ticks model restarts every 20 ticks; a long piece asked for again mid-way); otherwise snd_start restarts it (an
; effect is copied whole at its start, so a short one is always restarted, as before). The PSG player's state only:
; the sound model (SND_CUR, SND_LEFT, the 'N' line) is snd_next's as before. Keeps BC, DE (snd_start's contract).
snd_again:      ld      hl, (MF_LEFT)
                ld      a, h
                or      l
                ld      a, b
                jp      z, snd_start            ; (nothing being copied)
                push    bc
                push    de
                add     a, a                    ; the index entry: SB_ADDR + 4 id (psg.asm snd_start)
                add     a, a
                ld      e, a
                ld      d, SB_ADDR / 256
                ld      a, SB_PAGE
                call    far_seek
                in      a, (RD_DATA)
                ld      e, a
                in      a, (RD_DATA)
                ld      d, a                    ; DE = the stream's start
                in      a, (RD_DATA)
                ld      c, a
                in      a, (RD_DATA)
                ld      b, a                    ; BC = its length
                ld      hl, (MF_SRC)
                or      a
                sbc     hl, de                  ; (C: before the stream)
                jr      c, sag_new              ; (C: restart)
                sbc     hl, bc                  ; (C: inside it)
                ccf                             ; (C: after it: restart)
sag_new:        pop     de
                pop     bc
                ld      a, b
                jp      c, snd_start            ; (another stream)
sag_on:         ret                             ; (tests: the stream goes on)
                endif
