; ---------------------------------------------------------------- the duel patch (docs/duel-design.md, phase 2)
; The duel easter egg: the kid (player 1) against the shadow (player 2) in one room, both with the kid's moves, as
; tools/duelsim.py plays it (the oracle; docs/duel-design.md section 11 the rules, section 12 this patch as built).
; Not a program of its own: pieces of code laid over the GAME image (build/m4game.bin, restored by the launcher as for
; every game start) where the duel never runs the game's code: the holes (H_* below; tools/duelpatch.py checks every
; piece against them and the call graph against the holes). Assembled against the game's symbols (build/duel.inc,
; tools/ovltool.py equ), so a change of the game moves the pieces with it or fails the build here.
;
; How it gets there (src/boot/boot.asm, ACT_DUEL; Ctrl+D on PRES's title): the launcher loads POP800.PRS entry
; PRS_DUEL1 (the staged pieces, one RAM-disk record: page DUEL_STAGE_PAGE at DUEL_STAGE_ADDR, runtime scratch), restores
; the GAME image, loads entry PRS_DUEL (the piece P_main: main RAM over the game's main loop, level_ready on) and starts
; the game at its `start`. The game starts as always (game_start: the video, the tables, the interrupts, level 1's
; start: the game's code untouched until then), returns to level_ready = d_boot here, which copies the staged pieces
; into their holes and runs the duel (d_entry). Nothing of the patch is in the RAM disk's GAME image: the next game
; start restores a clean one.
;
; The rules (duelsim's DuelSim.step): the duel's own tick (d_tick) runs both players' frames with the game's routines;
; player 2's frame runs with Char.charid = the kid's and Opp.charid = the shadow's, so every charid test of the game's
; sword code takes the kid's rules (D1-D9: the kid's frame table, draw rule, sword sequences, parry rule) and the
; "opponent is the shadow" rule (D3) holds both ways; kid_sword_strike (set only by the real kid's strike) is kept
; around it. D10 (the kid's hurt sound) and D12 / D13 (each player's own hit points, both hurt in one tick) are the
; duel's own hurt (d_hurt); D11 (the shadow sees the kid) is check_can_guard_see_kid run with the record's charid a
; guard's; D14 / D15 are the only patches inside the game's kid code (kid.asm duel_d14, duel_d15). Player 2's block
; (duelsim BLOCK + COLL: 90 bytes) is swapped with the globals around its frame (d_swap).
;
; The drawing: the game's (the full room draw once, draw_objects, the hit point strips); player 2 is drawn as the
; kid (its record's charid is the kid's while drawing: the kid's images, no XOR look, its strip at the right) with
; a blue suit and grey hair (a plane operation per cell: d_sdraw, DUEL_LOOK; overlay.asm duel_sd1 / duel_sd2). Pacing: mode 0, every tick drawn, at least 4 frames (game.asm's).
; The torches flicker as in the game (P_w2 at an arena's setup, process_trobs, view_redraw: prandom, never hashed).
; The HUD (phase 3, docs/duel-design.md 13): player 2's strip as player 1's in blue (d_ghp), the bottom text line (the
; round, the score, the round's and the match's result, the rematch / quit prompt: d_hud, through the game's text
; overlay). Sound: the silent model for the logic (SND_MODE 0: nothing waits on a sound, the N line as duelsim's); the
; PSG gets the effects of both players with the game's priorities and a tune at a round's and the match's end (d_snd:
; audio only). The HUD and the audio only read the logic's state.
;
; Input (d_input; the byte of duel-design 11.6: bit 0 left, 1 right, 2 up, 3 down, 4 the button, 5 quit, 6 rematch):
; player 1 the game's (the cursor keys, SHIFT, joystick 1: read_inputs' INPUT), BREAK = quit, ENTER = rematch;
; player 2 W A S D + Q and joystick 2 (IN F1h). The harness (tests/duel_z80.py) sets d_script: two bytes a tick from
; RAM-disk page RD_LV_PAGE instead.

                include "../../build/duel.inc"
                include "../../build/duel_text.inc"     ; (the text overlay's labels: d_hud calls them in W2)
                include "../../build/duel_level.inc"    ; (the level-start overlay's labels: w_load calls its alter_mods)

; ---- the arena and the rules (tools/duelsim.py). The random arenas (docs/duel-design.md 15): per match a level, per
; round a room of its pool (build/duel_arenas.inc, tools/duelarenas.py --asm), set up by P_w2 (the arena piece: staged,
; copied into W2's top by d_arena for each use)
ROUND_HP        equ     3
WINS            equ     3
ROUND_END_TICKS equ     36
; ---- the HUD and the sound (phase 3: drawing and audio only, never read by the logic, never hashed)
ROUND_TEXT_TICKS equ    20              ; "ROUND n" alone for a round's first ticks, then the score line
HUD_ALT         equ     32              ; after the match: the winner and the prompt alternate (a bit of d_hcnt)
JINGLE_DELAY    equ     3               ; the round's or match's tune: ticks after the deciding one (the hurt sound first)
SND_ROUNDJ      equ     37              ; a round won: the guard's death tune (SDLPoP sound_37_victory, 4.1 s)
SND_MATCHJ      equ     41              ; the match won: the level's end music (sound_41_end_level_music, 12.8 s)
IN_QUIT         equ     5               ; (bits)
IN_REMATCH      equ     6
MATCH_QUIT      equ     3
DUEL_STAGE_PAGE equ     6               ; the staged pieces: RAM-disk scratch (duel-design 1.5 rule 1: page 6
DUEL_STAGE_ADDR equ     0x16c0          ; 0x16C0-0x287F; the chopper pictures' pool at runtime, none in the arena)
DUEL_STAGE_END  equ     0x2880
PORT_JOY2       equ     0xf1
; ---- the network (phase 4, docs/duel-design.md 4 and 14; the MZPico NET protocol: BomberNet docs/net-protocol.md)
NET_GAME        equ     0x5050          ; the game id: "PP" (the user's decision, duel-design 9)
NET_DELAY       equ     1               ; the input delay in ticks (the host's; the room's settings[0])
NET_SILENT      equ     500             ; frames without the other's input: the connection lost (10 s)
NET_WAITMSG     equ     25              ; frames of waiting before WAITING shows (0.5 s)
NET_LEAVEW      equ     50              ; frames before NETLEAVE (1 s: the other machine's last NETPOLL first)
NP_CMD          equ     0x50            ; the card's command / status port
NP_DATA         equ     0x51            ; its data port
N_STSR          equ     0x03
N_REVD          equ     0x06
N_INFO          equ     0x95
N_STATUS        equ     0xa0
N_CREATE        equ     0xa1
N_JOIN          equ     0xa2
N_LEAVE         equ     0xa3
N_READY         equ     0xa4
N_SEND          equ     0xa5
N_POLL          equ     0xa6
N_HASH          equ     0xa7
NS_INROOM       equ     2               ; (NETSTATUS states: 0 no link, 1 linked, 2 in a room, 3 running, 4 desync,
NS_RUNNING      equ     3               ; 5 dropped)
NS_DESYNC       equ     4
NS_DROPPED      equ     5
K_BREAK         equ     3               ; (d_kget's codes besides the characters)
K_DEL           equ     8
K_ENTER         equ     13

; ---- the holes: code of the game the duel never runs (tools/duelpatch.py: a piece lies inside one hole; the stubs and
; the patch sites are holes of their own). H_x .. H_x_END (exclusive).
H_MAIN          equ     level_ready             ; game.asm's main loop (the duel has its own): PRS_DUEL, main RAM
H_MAIN_END      equ     flip_now
H_KT            equ     kid_tick                ; kid.asm kid_tick (the duel has its own frame, d_frame)
H_KT_END        equ     level_number
H_TICK          equ     tick_pre                ; guard.asm tick_pre, tick_post, tick_end, timers, do_mouse, check_skel
H_TICK_END      equ     check_can_guard_see_kid
H_AI            equ     autocontrol_opponent    ; guard.asm the guard AI, play_guard_frame, play_guard, the guard's
H_AI_END        equ     check_sword_hurting     ; bumps and chompers
H_FREE          equ     end_of_code             ; main RAM free below W1
H_FREE_END      equ     OVL_W1
; the patch sites (kid.asm, overlay.asm: labels only in the game's source)
H_D14           equ     duel_d14
H_D14_END       equ     duel_d14 + 3
H_D15           equ     duel_d15 + 1
H_D15_END       equ     duel_d15 + 3
H_SD1           equ     duel_sd1 + 1
H_SD1_END       equ     duel_sd1 + 3
H_SD2           equ     duel_sd2 + 1
H_SD2_END       equ     duel_sd2 + 3
H_PP1           equ     duel_pp1 + 1
H_PP1_END       equ     duel_pp1 + 3
H_PP2           equ     duel_pp2 + 1
H_PP2_END       equ     duel_pp2 + 3
; the network's holes (phase 4, docs/duel-design.md 14): code the arena never reaches (the call graph and the code log
; check them as the others)
H_OBJ           equ     make_loose_fall         ; objects.asm the loose floors, the knocks, the falling floors (mobs)
H_OBJ_END       equ     foh2
H_LR            equ     leave_room              ; kid.asm leave_room, goto_other_room (the arena's edges are walls)
H_LR_END        equ     kid_tick
H_SPK           equ     check_spiked            ; objects.asm the spikes
H_SPK_END       equ     start_chompers
H_TIME          equ     death_text              ; evres.asm the death text, the clock (show_time)
H_TIME_END      equ     draw_game_frame
; the arenas' piece (docs/duel-design.md 15): not a hole of the game's code but W2's top (OVL_WF: the fill overlay's
; window, used only by a level start's fill; the duel never runs one). P_w2 is staged after the pieces of d_ptab and
; copied there by d_arena at each use (the compose buffers overwrite it at the next drawing)
H_W2A           equ     OVL_WF
H_W2A_END       equ     OVL_W2_END
                if LV_ovl_end > H_W2A
                .error the level-start overlay reaches the arenas' piece in W2 (w_load loads it below P_w2)
                endif
DSTAGE_W2       equ     DUEL_STAGE_ADDR + P_ai_end - P_ai + P_kt_end - P_kt + P_tick_end - P_tick + P_free_end - P_free + 13 + P_obj_end - P_obj + P_lr_end - P_lr + P_spk_end - P_spk + P_time_end - P_time
DIR_DUNGEON     equ     0xd100          ; (src/m4/ovl_level.asm load_level: the env's and the wall's directories in
DIR_DUNGEON_W   equ     0xd800          ; page RD_LV_PAGE, dungeon and palace)
DIR_PALACE      equ     0xdb00
DIR_PALACE_W    equ     0xe200

; ================================================================ P_main: over the game's main loop (main RAM)
                org     H_MAIN
P_main:
; d_boot: game_start returned here (level 1 started, the interrupts on): the staged pieces into their holes
d_boot:         ld      a, DUEL_STAGE_PAGE
                ld      de, DUEL_STAGE_ADDR
                call    far_seek
                ld      ix, d_ptab
db_p:           ld      l, (ix+0)
                ld      h, (ix+1)
                ld      a, h
                or      l
                jp      z, d_entry
                ld      e, (ix+2)
                ld      d, (ix+3)
                ld      bc, 4
                add     ix, bc
                ld      c, RD_DATA
db_f:           ld      a, d
                or      a
                jr      z, db_r
                ld      b, 0
                inir
                dec     d
                jr      db_f
db_r:           ld      a, e
                or      a
                jr      z, db_p
                ld      b, a
                inir
                jr      db_p
; the staged pieces in their order in the RAM disk (tools/duelpatch.py stages them so): address, length; 0 ends
d_ptab:         dw      P_ai, P_ai_end - P_ai
                dw      P_kt, P_kt_end - P_kt
                dw      P_tick, P_tick_end - P_tick
                dw      P_free, P_free_end - P_free
                dw      P_d14, 3
                dw      P_d15, 2
                dw      P_sd1, 2
                dw      P_sd2, 2
                dw      P_pp1, 2
                dw      P_pp2, 2
                dw      P_obj, P_obj_end - P_obj
                dw      P_lr, P_lr_end - P_lr
                dw      P_spk, P_spk_end - P_spk
                dw      P_time, P_time_end - P_time
                dw      0
d_script:       dw      0               ; (the harness: the next input pair's RAM-disk address in page RD_LV_PAGE; 0: live)
d_hnet:         db      0               ; (the harness with d_script: 0 local play at once, tests/duel_z80.py; 1 the menu
                                        ; and the lobby as a player has them, tests/duel_net.py)
d_seed:         dw      0               ; the arenas' seed (P_w2 w_entry: the frame counter; the joiner: the host's,
                                        ; from the room's settings; the harness: its own, kept with d_script set)
d_afix:         db      0               ; (the harness: 1 the fixed arena, level 1 room 3, every round)

; d_loop: the match loop (game.asm mainloop's mode 0: a tick every 4 frames at most, every tick drawn)
d_loop:         ld      hl, (FRAMES)
                ld      de, (LAST_TICK)
                or      a
                sbc     hl, de
                ld      a, h
                or      a
                jr      nz, dl_go
                ld      a, l
                cp      4
                jr      nc, dl_go
                halt
                jr      d_loop
dl_go:          ld      hl, (FRAMES)
                ld      (LAST_TICK), hl
                ld      hl, (TICKS)
                inc     hl
                ld      (TICKS), hl
                call    view_snapshot   ; (the tiles before the tick: the torches' frames, game.asm's way)
                call    dirty_reset
                call    d_input
                call    d_net           ; (the network: the agreed input bytes; local play: nothing)
                call    d_tick
d_tend:         ld      a, (d_match)    ; (harness: the tick's end, the D line)
                cp      MATCH_QUIT
                jr      z, d_quit
                call    d_draw
d_done:         jr      d_loop          ; (harness: the tick drawn)
; d_draw: the tick's drawing (also the arena's first, before the lobby: d_lobby)
d_draw:         ld      a, (DRAWN_ROOM) ; the arena, once
                ld      hl, SHOWN_ROOM
                cp      (hl)
                jr      z, dl_t
                ld      (hl), a
                call    draw_room_full
                ld      a, 0xff         ; (the HUD drawn again after it)
                ld      (d_key), a
                ld      (d_ghps), a
                jr      dl_d
dl_t:           ld      a, 1            ; the torches' changed frames: into the shadow room, on the dirty list
                ld      (RR_SHONLY), a  ; (game.asm gmt3: drawn with the people over them)
                ld      hl, dirty_hook
                ld      (RR_HOOK), hl
                call    view_redraw
                xor     a
                ld      (RR_SHONLY), a
dl_d:           ld      hl, GUARD_REC + OF_CHARID      ; player 2 drawn as the kid (d_sdraw: its colours)
                ld      (hl), 0
                call    draw_objects
                ld      hl, GUARD_REC + OF_CHARID
                ld      (hl), CHARID_SHADOW
                call    hp_draw         ; player 1's strip (ghp_draw: no shadow's strip off level 12)
                jp      d_hud           ; player 2's strip, the bottom text
; d_quit: back to PRES's title (the level-start overlay's handoff; without the launcher, the harness: it stops here);
; out of the network's room first
d_quit:         call    d_nleave
                ld      a, GO_TITLE
                ld      (GAME_OVER), a
                call    game_over
dq_stop:        halt
                jr      dq_stop

P_main_end:
                if P_main_end > H_MAIN_END
                .error the duel's main piece is larger than the game's main loop
                endif

; ================================================================ P_ai: over the guard AI (block 2)
                org     H_AI
P_ai:
; d_entry: the arena (level 1 is started), the first round, the match loop
d_entry:        ld      sp, STACK
                xor     a
                ld      (SND_MODE), a   ; the silent sound model (duel-design 11.4)
                ld      (NEED_L1M), a   ; (no level 1 music crouch)
                ld      (TROBS_N), a    ; no tile animations but the torches (P_w2), no falling floors
                ld      (MOBS_N), a
                ld      (IS_SHOW_TIME), a
                ld      (EXIT_TIMER), a
                ld      (d_rounds), a
                ld      (d_score1), a
                ld      (d_score2), a
                ld      (d_result), a
                ld      (d_match), a
                call    erase_text
                ld      a, 2            ; the fixed arena (level 1 room 3) behind the menu, the seed (P_w2 w_entry)
                call    d_arena
                jp      d_lobby

; d_tick: one tick (duelsim DuelSim.step) with the input bytes d_in1, d_in2
d_tick:         xor     a
                ld      (HITP_DELTA), a
                ld      (GUARDHP_DELTA), a
                call    process_trobs   ; (the torches' flicker: prandom, which no logic reads; not hashed)
                ld      hl, GUARD_REC + OF_CHARID      ; (D11: the shadow sees the kid on every level)
                ld      (hl), CHARID_GUARD
                call    check_can_guard_see_kid
                ld      hl, GUARD_REC + OF_CHARID
                ld      (hl), CHARID_SHADOW
                call    loadkid_and_opp ; player 1
                ld      a, (d_in1)
                ld      hl, HITP_CURR
                call    d_frame
                call    savekid
d_mid:          ld      hl, (K_TICK)    ; (harness: the kid line)
                inc     hl
                ld      (K_TICK), hl
                call    d_swap          ; player 2: its block in, the kid's rules
                call    loadshad_and_opp
                xor     a
                ld      (K_CHARID), a
                inc     a
                ld      (OPP_REC + OF_CHARID), a
                call    dh_x            ; (its own hit points in HITP: a take_hp in its frame, which runs with the kid's
                ld      a, (KID_SWORD_STRIKE)   ; charid, takes them from player 2: a 2-row drop, D16, section 16)
                push    af
                ld      a, (d_in2)
                ld      hl, HITP_CURR
                call    d_frame
                pop     af
                ld      (KID_SWORD_STRIKE), a
                call    dh_x
                ld      a, CHARID_SHADOW
                ld      (K_CHARID), a
                call    saveshad
                call    d_swap
                call    check_sword_hurting
                call    d_hurt
                call    sword_vs_sword
                call    do_delta_hp_g
d_gline:        call    d_round         ; (harness: the G line)
                call    d_snd           ; (play_next_sound: the N line at snd_snap)
                call    loadkid         ; (KV = the kid for the drawing)
                jp      d_hash

; d_frame: SDLPoP play_kid_frame for Char (KV), Opp set: A = the input byte, HL = the character's hit points (D12)
d_frame:        ld      (df_in), a
                ld      (df_hp), hl
                call    load_fram_det_col
                ld      a, (K_ALIVE)    ; out of hit points: dead (duelsim duel_control)
                rla
                jr      nc, df1
                ld      hl, (df_hp)
                ld      a, (hl)
                or      a
                jr      nz, df1
                ld      (K_ALIVE), a
df1:            ld      hl, GRAB_TIMER
                ld      a, (hl)
                or      a
                jr      z, df2
                dec     (hl)
df2:            ld      hl, CTRL1       ; rest_ctrl_1
                ld      de, C_FWD
                ld      bc, 5
                ldir
                ld      a, (df_in)      ; the input byte: right over left, down over up
                ld      b, a
                ld      c, 0
                rrca
                jr      nc, df3
                dec     c
df3:            rrca
                jr      nc, df4
                ld      c, 1
df4:            ld      e, 0
                rrca
                jr      nc, df5
                dec     e
df5:            rrca
                jr      nc, df6
                ld      e, 1
df6:            ld      a, c
                ld      (C_X), a
                ld      a, e
                ld      (C_Y), a
                ld      a, b
                and     0x10
                jr      z, df7
                ld      a, C_HELD
df7:            ld      (C_SHIFT), a
                call    read_user_control
                call    user_control
                ld      hl, C_FWD       ; save_ctrl_1
                ld      de, CTRL1
                ld      bc, 5
                ldir
                ld      a, (K_ALIVE)    ; the death counter: no wait on a sound, no music, no text (duel-design 11.4)
                rla
                jr      c, df_body
                ld      a, (K_FRAME)
                cp      177
                jr      z, df8
                cp      178
                jr      z, df8
                cp      185
                jr      nz, df_body
df8:            ld      a, (K_ALIVE)
                cp      100
                jr      nc, df_body
                inc     a
                ld      (K_ALIVE), a
df_body:        ld      a, (K_ROOM)
                or      a
                ret     z
                call    play_seq
                call    fall_accel
                call    fall_speed
                call    load_frame_to_obj
                call    load_fram_det_col
                call    set_char_collision
                call    bump_into_opponent
                call    check_collisions
                call    check_bumped
                call    check_gate_push
                jp      check_action    ; (no check_press, spikes, chompers, knocks: the arena has none)
df_in:          db      0
df_hp:          dw      0

; d_hurt: check_sword_hurt the duel's way (D13, the user's change 2026-11-11: both hurt in one tick is a clash, nobody
; is hurt, both play attack_was_parried, the kid first; D10: the shadow hurt by the kid's rules and sound; D12: take_hp
; on its own hit points: the kid's path with the two exchanged)
d_hurt:         ld      a, (KID_REC + OF_ACTION)
                cp      AC_HURT
                jr      nz, dh1
                ld      a, (GUARD_REC + OF_ACTION)
                cp      AC_HURT
                jr      z, dh_clash
                call    loadkid
                call    hurt_by_sword
                jp      savekid
dh_clash:       call    loadkid
                call    dh_par
                call    savekid
                call    loadshad
                call    dh_par
                jp      saveshad
dh_par:         ld      a, SQ_ATTACK_PARRIED
                call    seqtbl_offset_char
                jp      play_seq
dh1:            ld      a, (GUARD_REC + OF_ACTION)
                cp      AC_HURT
                ret     nz
                call    loadshad
                call    dh_x
                xor     a
                ld      (K_CHARID), a
                call    hurt_by_sword
                ld      a, CHARID_SHADOW
                ld      (K_CHARID), a
                call    dh_x
                jp      saveshad
; d_reset: a round's start (duelsim round_reset): both at their start tiles, standing, swords sheathed, full hit
; points, fresh blocks
d_reset:        ld      a, (d_c1)                       ; player 1: column, direction right; charid the kid
                ld      b, a
                ld      c, 0
                ld      e, c
                call    dr_char
                call    savekid
                ld      a, (d_c2)                       ; player 2: left, the shadow
                ld      b, a
                ld      c, 0xff
                ld      e, CHARID_SHADOW
                call    dr_char
                call    saveshad
                call    loadkid_and_opp
                call    d_fresh         ; the blocks: player 1's (the globals), then player 2's
                call    d_swap
                call    d_fresh
                ld      a, ROUND_HP
                ld      hl, HITP_CURR
                ld      (hl), a
                inc     hl
                ld      (hl), a         ; HITP_MAX
                ld      (GUARDHP_CURR), a
                ld      (GUARDHP_MAX), a
                xor     a
                ld      (d_rtick), a    ; (the HUD's: drawing only)
                ld      (HITP_DELTA), a
                ld      (GUARDHP_DELTA), a
                ld      (SND_SCREAM), a
                ld      (KNOCK), a
                ld      (d_timer), a
                ld      hl, CAN_SEE     ; can_guard_see_kid .. droppedout (holding_sword, offguard: the block's)
                ld      b, DROPPEDOUT + 1 - CAN_SEE
drs_z:          ld      (hl), a
                inc     hl
                djnz    drs_z
                dec     a               ; (audio only: any sound may cut the last round's tune)
                ld      (d_acur), a
                ret
; dr_char: Char (KV) = a fresh record: B = column, C = direction, E = charid; then the stand sequence played
dr_char:        ld      hl, KV
                push    bc
                ld      b, 16
drc_z:          ld      (hl), 0
                inc     hl
                djnz    drc_z
                pop     bc
                ld      a, e
                ld      (K_CHARID), a
                ld      a, c
                ld      (K_DIR), a
                ld      a, b
                ld      (K_COL), a
                add     a, FIRST_COL
                ld      hl, x_bump
                call    k_tbl
                add     a, TILE_SIZEX
                ld      (K_X), a
                ld      a, (d_arow)
                ld      (K_ROW), a
                inc     a
                ld      hl, y_land
                call    k_tbl
                ld      (K_Y), a
                ld      a, (d_room)
                ld      (K_ROOM), a
                ld      a, 0xff
                ld      (K_ALIVE), a
                ld      a, SQ_STAND
                call    seqtbl_offset_char
                jp      play_seq
; d_fresh: player 2's block fresh: ctrl1 released, grab_timer 0, have_sword 1, offguard 0, holding_sword 0, no collision
; rows (prev_collision_row -1, rooms -1, flags 0)
d_fresh:        ld      hl, d_blk2
                xor     a
                ld      b, 6
dfr1:           ld      (hl), a
                inc     hl
                djnz    dfr1
                inc     a
                ld      (hl), a         ; have_sword
                inc     hl
                dec     a
                ld      (hl), a         ; offguard
                inc     hl
                ld      (hl), a         ; holding_sword
                inc     hl
                dec     a
                ld      (hl), a         ; prev_collision_row
                inc     hl
                ld      c, 4
dfr2:           ld      b, 10
dfr3:           ld      (hl), 0xff      ; rooms
                inc     hl
                djnz    dfr3
                ld      b, 10
dfr4:           ld      (hl), 0         ; flags
                inc     hl
                djnz    dfr4
                dec     c
                jr      nz, dfr2
                ret
; d_swap: player 2's block (d_blk2) <-> the globals (duelsim swap_block)
d_swap:         ld      de, d_blk2
                ld      hl, d_blkmap
dsw_r:          ld      c, (hl)
                inc     hl
                ld      b, (hl)
                inc     hl
                ld      a, b
                or      c
                ret     z
                push    hl
                ld      a, (hl)
                ld      h, b
                ld      l, c
                ld      b, a
dsw_b:          ld      a, (de)
                ld      c, (hl)
                ld      (hl), a
                ld      a, c
                ld      (de), a
                inc     hl
                inc     de
                djnz    dsw_b
                pop     hl
                inc     hl
                jr      dsw_r
d_blkmap:       dw      CTRL1           ; ctrl1, grab_timer (KV + 24 .. 29)
                db      6
                dw      HAVE_SWORD
                db      1
                dw      OFFGUARD
                db      1
                dw      HOLDING_SWORD
                db      1
                dw      PREV_COLL_ROW
                db      1
                dw      PREV_ROOMS      ; the collision rows (KV + 96 .. 175)
                db      80
                dw      0
; d_hash: the state hash (duelsim state_bytes / hash16: 68 bytes, h = rotl16(h, 1) + byte) -> d_hashv
d_hash:         ld      hl, 0
                ld      ix, d_hashmap
dhs_r:          ld      e, (ix+0)
                ld      d, (ix+1)
                ld      a, d
                or      e
                jr      z, dhs_x
                ld      b, (ix+2)
                inc     ix
                inc     ix
                inc     ix
dhs_b:          add     hl, hl          ; rotate left by one
                jr      nc, dhs_1
                inc     l
dhs_1:          ld      a, (de)
                add     a, l
                ld      l, a
                jr      nc, dhs_2
                inc     h
dhs_2:          inc     de
                djnz    dhs_b
                jr      dhs_r
dhs_x:          ld      (d_hashv), hl
                ret
d_hashmap:      dw      d_aidx          ; the arena's entry (first: 0, the fixed arena, leaves the 68 bytes' hash as it was)
                db      1
                dw      KID_REC         ; the kid's and the shadow's records
                db      32
                dw      HITP_CURR       ; hitp_curr, hitp_max
                db      2
                dw      GUARDHP_CURR    ; guardhp_curr, guardhp_max
                db      2
                dw      CAN_SEE
                db      1
                dw      JUSTBLOCKED     ; justblocked, guard_refrac, kid_sword_strike, guard_notice_timer, is_guard_notice
                db      5
                dw      DROPPEDOUT      ; droppedout, guard_skill
                db      2
                dw      CTRL1           ; player 1's block: ctrl1, grab_timer
                db      6
                dw      HAVE_SWORD
                db      1
                dw      OFFGUARD
                db      1
                dw      HOLDING_SWORD
                db      1
                dw      d_blk2          ; player 2's block (its first 9 bytes)
                db      9
                dw      d_rounds        ; the round state
                db      6
                dw      0
; d_snd: play_next_sound, the silent model for the logic (the N line: the request starts, nothing plays), the PSG
; with the game's priorities against what the PSG really plays (audio only: d_acur, the player's SP_WAIT; never read
; by the logic, so two machines may differ in it); and the round's or match's tune a few ticks after the deciding tick
d_snd:          call    snd_playing     ; (the ring topped up, once a tick; A = 0: silent)
                ld      a, (d_timer)
                cp      ROUND_END_TICKS - JINGLE_DELAY
                jr      nz, ds1
                ld      a, (d_result)
                cp      3
                jr      z, ds1          ; (a draw: none)
                ld      hl, d_rounds    ; the winner's score (d_score1 = d_rounds + 1): WINS, the match's tune
                ld      e, a
                ld      d, 0
                add     hl, de
                ld      a, (hl)
                cp      WINS
                ld      a, SND_MATCHJ
                jr      nc, ds_j
                ld      a, SND_ROUNDJ
ds_j:           ld      (d_acur), a
                ld      b, a
                call    snd_again
ds1:            ld      a, (SND_NEXT)
                ld      c, a
                ld      b, 0xff
                inc     a
                jr      z, ds_x         ; nothing asked for
                ld      b, c            ; (the silent model: it starts)
                ld      a, c
                ld      (SND_CUR), a
                ld      a, (SP_WAIT)    ; the PSG plays a sound the request may not cut?
                or      a
                jr      z, ds_go
                ld      a, (d_acur)
                inc     a
                jr      z, ds_go        ; (0xff: any may)
                dec     a
                call    snd_ent
                bit     7, a
                jr      z, ds_x         ; (not interruptible)
                and     0x7f
                ld      d, a
                ld      a, c
                call    snd_ent
                and     0x7f
                cp      d
                jr      z, ds_go
                jr      nc, ds_x        ; (a lower priority)
ds_go:          ld      a, c
                ld      (d_acur), a
                call    snd_again       ; (A = B = the id; keeps BC, DE)
ds_x:           ld      a, 0xff
                ld      (SND_NEXT), a
                ld      e, 0            ; (the N line: playing 0, the silent model)
                jp      snd_snap

; the arena (P_w2): the level loaded, the match's number, the arena's entry (build/duel_arenas.inc w_pool; 0xff: set it up
; again), its room, row and the players' start columns
d_lvl:          db      1               ; (the game's start loaded level 1)
d_mtch:         db      0
d_room:         db      0
d_arow:         db      0
d_c1:           db      0
d_c2:           db      0
; the duel's state (the arena's entry, then the round state in the hash's order)
d_aidx:         db      0xff
d_rounds:       db      0
d_score1:       db      0
d_score2:       db      0
d_timer:        db      0
d_result:       db      0
d_match:        db      0
d_in1:          db      0
d_in2:          db      0
d_hashv:        dw      0
d_blk2:         ds      90              ; player 2's block: ctrl1 (5), grab_timer, have_sword, offguard, holding_sword,
                                        ; prev_collision_row, the collision rows (80, kid.asm PREV_ROOMS .. ABOVE_FLAGS)
; the HUD's and the audio's (never read by the logic, never hashed)
d_acur:         db      0xff            ; the sound the PSG was last given (0xff: none that must be kept)
d_rtick:        db      0               ; ticks drawn since the round's start (to 255)
d_hcnt:         db      0               ; ticks drawn (wraps)
; d_bswap: the hit point icons (game.asm's hp_full and hp_empty: 5 rows x 4 planes, plane-major) with planes I and II
; (B, R) exchanged in place: blue where the kid's are red. d_ghp calls it around player 2's strip, so the game's own
; icons are red again for player 1's (hp_draw) and the GAME image keeps its bytes
d_bswap:        ld      hl, hp_full
                ld      de, hp_full + 5
                call    dbs
                ld      hl, hp_empty
                ld      de, hp_empty + 5
dbs:            ld      b, 5
dbs_l:          ld      a, (de)
                ld      c, (hl)
                ld      (hl), a
                ld      a, c
                ld      (de), a
                inc     hl
                inc     de
                djnz    dbs_l
                ret
P_ai_end:
                if P_ai_end > H_AI_END
                .error the duel's piece P_ai is larger than its hole (the guard AI)
                endif

; ================================================================ P_kt: over kid.asm kid_tick
                org     H_KT
P_kt:
; d14 (kid.asm bumped, pushed left into a wall, duel_d14): D14, a wall of room 0 left of column 0 is the room's own
; column 9 (as SDLPoP does for the right edge)
d14:            ld      a, (TILE_COL)
                dec     a
                cp      0xff
                jr      nz, d14x
                ld      a, (CURR_ROOM)
                or      a
                ld      a, 0xff
                jr      nz, d14x
                ld      a, (K_ROOM)
                ld      (CURR_ROOM), a
                ld      a, 9
d14x:           ld      (TILE_COL), a
                ld      c, a
                jp      duel_d14r
; d15 (kid.asm is_obstacle's xpos_in_drawn_room, duel_d15): D15, room 0's column 0 is the right neighbour's
d15:            ld      a, (CURR_ROOM)
                or      a
                jp      nz, xpos_in_drawn_room
                ld      a, (TILE_COL)
                or      a
                jp      nz, xpos_in_drawn_room
                ld      de, TILE_SIZEX * 10
                add     hl, de
                ret
; d_sdraw (overlay.asm's spr_draw calls, duel_sd1 / duel_sd2): HL = the descriptor; the guard's slot (player 2) is
; drawn with its colours changed by one plane operation on the drawn pixels (DUEL_LOOK, below), else spr_draw. The same
; kernel as gfx.asm spr_draw (its own patched operands). The black outline (colour 8: plane IV alone) stays as it is in
; every variant. The planes: I = bit 0 (B), II = bit 1 (R), III = bit 2 (G), IV = bit 3 (the intensity). Extra T a
; drawn cell against spr_draw's cell (~110 T): 0 +117, 1 +32, 2 +16, 3 +16, 4 -7, 5 +20 (a kid image has ~100-290 cells,
; ~150 drawn: 0 costs ~0.25 frames a tick, the others at most ~0.1).
;   0 (default, the user's choice 2026-11-11) a blue suit, grey hair: where plane I (B) is set, planes II and III (R,
;     G) cleared (the kid's white 15 -> light blue 9, light grey 7 -> blue 1); where R alone of B, R, G is set (the hair,
;     colours 2 and 10) R cleared and plane IV (I) set: grey 8. The skin 6 and the outline 8 (the only other colours
;     of the kid's images) unchanged. Per cell: R' = R & G & ~B, G' = G & ~B, I' = I | (R & ~G & ~B), with ~B in IXL
;     and G | ~(drawn) in IXH, then the hair in IXH
;   1 a blue suit only (the hair as it is): R' = R & ~B, G' = G & ~B (~B kept in IXL)
;   2 R <-> B: planes I and II swapped (white stays white, the skin cyan, the hair blue)
;   3 R <-> G: planes II and III swapped (the hair green)
;   4 no B: plane I cleared (a golden outfit, the skin as it is)
;   5 I inverted: plane IV XOR (planes I | II | III), i.e. XOR 8 on every drawn pixel but the outline (light grey
;     clothes, light yellow skin, light red hair)
; Colour 8 (plane IV alone) is drawn as any other colour (the kernel's transparency is "no plane set", colour 0): the
; images' black is stored as 8 and shows dark grey, the grey hair is that grey.
                if not defined DUEL_LOOK
DUEL_LOOK       equ     0
                endif
d_sdraw:        push    hl
                ld      de, SPR_G
                or      a
                sbc     hl, de
                pop     hl
                jp      nz, spr_draw
                push    hl
                pop     iy
                xor     a
                call    sd_bounds       ; (returns from here when nothing is visible)
                push    ix              ; (IXL, IXH: DUEL_LOOK's masks; the caller keeps IX)
                ld      a, (V_PX)
                ld      (dsd_px + 1), a
                ld      (dsd_dst + 1), a
                add     a, a
                add     a, a
                ld      c, a
                ld      a, (sd_stride + 1)      ; (sd_bounds patched the kernel's: ow * 4)
                sub     c
                ld      (dsd_stride + 1), a
                ld      a, (V_N)
                exx
                ld      b, a
                exx
                ld      hl, (V_ROWOFF)
dsdrow:
dsd_px:         ld      c, 0
dsdcell:        ld      a, (hl)
                if DUEL_LOOK = 1
                cpl
                ld      ixl, a          ; ~(plane I): the suit's mask
                cpl
                endif
                inc     l
                or      (hl)
                inc     l
                or      (hl)
                if DUEL_LOOK = 5
                ld      (dsd_q + 1), a  ; planes I | II | III: the XOR on plane IV
                endif
                inc     l
                or      (hl)
                jr      z, dsdempty
                cpl
                ld      b, a
                dec     l
                dec     l
                dec     l
                if DUEL_LOOK = 0
                ld      a, (hl)
                cpl
                ld      ixl, a          ; ~(plane I)
                inc     l
                inc     l
                ld      a, (hl)
                or      b
                ld      ixh, a          ; plane III | the undrawn bits
                dec     l
                dec     l
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                and     ixl
                and     ixh             ; plane II: R & G & ~B
                ld      (de), a
                ld      a, ixh
                cpl
                and     ixl
                and     (hl)
                ld      ixh, a          ; the hair: R & ~G & ~B
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                and     ixl             ; plane III: G & ~B
                ld      (de), a
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                or      ixh             ; plane IV: I | the hair
                ld      (de), a
                endif
                if DUEL_LOOK = 1
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                and     ixl             ; plane II: not where plane I is
                ld      (de), a
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                and     ixl             ; plane III: not where plane I is
                ld      (de), a
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                endif
                if DUEL_LOOK = 2
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a               ; plane I into II
                inc     l
                dec     d
                dec     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a               ; plane II into I
                inc     l
                inc     d
                inc     d
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                endif
                if DUEL_LOOK = 3
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                inc     l
                inc     d
                inc     d
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a               ; plane II into III
                inc     l
                dec     d
                dec     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a               ; plane III into II
                inc     l
                inc     d
                inc     d
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                endif
                if DUEL_LOOK = 4
                ld      a, (de)
                and     b
                ld      (de), a               ; plane I cleared
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                endif
                if DUEL_LOOK = 5
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
                ld      (de), a
                inc     l
                inc     d
                inc     d
                ld      a, (de)
                and     b
                or      (hl)
dsd_q:          xor     0               ; (patched: planes I | II | III; within the drawn bits: or = xor)
                ld      (de), a
                endif
                if DUEL_LOOK > 5
                .error DUEL_LOOK: 0 to 5
                endif
                inc     hl
                ld      a, d
                sub     6
                ld      d, a
                inc     e
                dec     c
                jp      nz, dsdcell
                jr      dsdrowend
dsdempty:       inc     hl
                inc     e
                dec     c
                jp      nz, dsdcell
dsdrowend:
dsd_stride:     ld      bc, 0
                add     hl, bc
                ld      a, e
dsd_dst:        sub     0
                add     a, CW
                ld      e, a
                jr      nc, dsd_nc
                inc     d
dsd_nc:         exx
                dec     b
                exx
                jp      nz, dsdrow
                pop     ix              ; (the caller's descriptor pointer)
                ret
; d_ghp: player 2's hit point strip as player 1's, mirrored at the right (hpstrip.asm hp_strip: the kid's icons, full
; and empty, both in blue: d_bswap around the calls), drawn when the hit points change
d_ghp:          ld      a, (GUARDHP_CURR)
                ld      b, a
                ld      a, (GUARDHP_MAX)
                ld      c, a
                ld      hl, (d_ghps)
                ld      a, l
                cp      b
                jr      nz, dg1
                ld      a, h
                cp      c
                ret     z
dg1:            ld      l, b
                ld      h, c
                ld      (d_ghps), hl
                ld      a, b
                ld      (hp_nf), a
                ld      a, c
                ld      (hp_n), a
                ld      hl, hp_full
                ld      (hp_pf), hl
                ld      a, 32
                ld      (hp_base), a
                call    d_bswap         ; both icons blue for player 2's strip
                ld      bc, 0x0820      ; bytes 32..39, then 31 (overlay.asm ghp_draw's chunks)
                call    hp_strip
                ld      bc, 0x011f
                call    hp_strip
                jp      d_bswap         ; (the game's red icons again)
d_ghps:         dw      0xffff          ; player 2's hit points as drawn (current, max; 0xff: draw again)
P_kt_end:
                if P_kt_end > H_KT_END
                .error the duel's piece P_kt is larger than its hole (kid_tick)
                endif

; ================================================================ P_tick: over guard.asm tick_pre .. check_skel
                org     H_TICK
P_tick:
; d_input: d_in1, d_in2 (the input bytes) from the keys and the joysticks, or the harness's script
d_input:        ld      hl, (d_script)
                ld      a, h
                or      l
                jr      z, di_live
                ex      de, hl
                ld      a, RD_LV_PAGE
                call    far_seek
                in      a, (RD_DATA)
                ld      (d_in1), a
                in      a, (RD_DATA)
                ld      (d_in2), a
                ld      hl, (d_script)
                inc     hl
                inc     hl
                ld      (d_script), hl
                ret
di_live:        call    read_inputs     ; (game.asm: KEYMAT, player 1's INPUT: cursor keys, SHIFT, joystick 1)
                ld      a, (KEYMAT + 8) ; BREAK (8/7): quit
                and     0x80
                rrca
                rrca
                ld      b, a
                ld      a, (KEYMAT + 0) ; ENTER (0/0): rematch
                and     1
                rrca
                rrca
                or      b
                ld      hl, INPUT
                or      (hl)
                ld      (d_in1), a
                in      a, (PORT_JOY2)  ; player 2: joystick 2 (up, down, left, right, fire in bits 0-4, low active)
                cpl
                ld      c, a
                and     0x0c            ; left, right -> bits 0, 1
                rrca
                rrca
                ld      b, a
                ld      a, c
                and     0x03            ; up, down -> bits 2, 3
                add     a, a
                add     a, a
                or      b
                ld      b, a
                ld      a, c
                and     0x10            ; fire
                or      b
                ld      b, a
                ld      hl, di_keys     ; W A S D Q
                ld      c, 1
di_k:           ld      a, (hl)
                inc     hl
                add     a, KEYMAT % 256
                ld      e, a
                ld      d, KEYMAT / 256
                ld      a, (de)
                and     (hl)
                inc     hl
                jr      z, di_k1
                ld      a, b
                or      c
                ld      b, a
di_k1:          sla     c
                bit     5, c
                jr      z, di_k
                ld      a, b
                ld      (d_in2), a
                ret
di_keys:        db      4, 0x80, 4, 0x10, 2, 0x02, 2, 0x20, 2, 0x80     ; A left, D right, W up, S down, Q fire

; d_round: the rounds (duelsim round_step), after the tick's hit points are final
d_round:        ld      a, (d_in1)
                ld      hl, d_in2
                or      (hl)
                ld      b, a
                ld      a, (d_match)
                bit     IN_QUIT, b
                jr      z, dr1
                cp      MATCH_QUIT
                jr      z, dr1
                ld      a, MATCH_QUIT
                ld      (d_match), a
                ret
dr1:            or      a
                jr      z, dr_on
                cp      MATCH_QUIT
                ret     z
                bit     IN_REMATCH, b
                ret     z
                xor     a               ; rematch: a new match, its own level (P_w2 w_match)
                ld      (d_rounds), a
                ld      (d_score1), a
                ld      (d_score2), a
                ld      (d_result), a
                ld      (d_match), a
                ld      hl, d_mtch
                inc     (hl)
                jp      d_arena
dr_on:          ld      a, (d_timer)
                or      a
                jr      nz, dr_tm
                ld      c, a            ; C: bit 0 player 1 at 0, bit 1 player 2
                ld      a, (HITP_CURR)
                or      a
                jr      nz, dr2
                inc     c
dr2:            ld      a, (GUARDHP_CURR)
                or      a
                jr      nz, dr3
                set     1, c
dr3:            ld      a, c
                or      a
                ret     z
                cp      3               ; the result: 3 a draw, 1 player 1 (C = 2), 2 player 2 (C = 1)
                jr      z, dr4
                xor     3
dr4:            ld      (d_result), a
                ld      hl, d_rounds
                inc     (hl)
                cp      3
                jr      z, dr5
                ld      hl, d_rounds    ; (d_score1 = d_rounds + 1, d_score2 + 2)
                ld      e, a
                ld      d, 0
                add     hl, de
                inc     (hl)
dr5:            ld      a, ROUND_END_TICKS
                ld      (d_timer), a
                ret
dr_tm:          dec     a
                ld      (d_timer), a
                ret     nz
                ld      a, (d_score1)
                cp      WINS
                ld      a, 1
                jr      nc, dr_end
                ld      a, (d_score2)
                cp      WINS
                ld      a, 2
                jr      nc, dr_end
                ld      a, 1            ; the next round: its arena (P_w2 w_round)
                jp      d_arena
dr_end:         ld      (d_match), a
                ret

; d_ppchar (overlay.asm people_place's calls of pp_char, duel_pp1 / duel_pp2): the blades (the user's choice
; 2026-11-11, docs/duel-design.md 12.8): a character is drawn with another kid frame, body and sword together (the hilt
; stays in the hand), so that a parry's blades meet and the en-garde blades sit at two heights. Drawing only: KV is the
; drawing's copy of the record here (people_place restores it from PP_SAVE), the logic never sees it. B = the slot (0
; player 1, 2 player 2), A = the hit point delta (kept)
d_ppchar:       push    af
                ld      hl, dpp_p1
                ld      a, b
                or      a
                jr      z, dpp_l
                ld      hl, dpp_p2
dpp_l:          ld      a, (hl)
                or      a
                jr      z, dpp_x
                inc     hl
                ld      c, a
                ld      a, (K_FRAME)
                cp      c
                ld      a, (hl)
                inc     hl
                jr      nz, dpp_l
                ld      (K_FRAME), a
dpp_x:          pop     af
                jp      pp_char
dpp_p1:         db      161, 158, 0                             ; player 1: the parry (161) as en garde (158)
dpp_p2:         db      161, 157, 158, 157, 170, 157, 171, 157, 0   ; player 2: the parry and en garde as 157

; the bottom texts (d_hud): 1, 2, 3 = d_key's numbers (0..99); tools/duelpatch.py checks that every one has its
; glyphs (the game's font + d_font) and fits the line's 160 pixels with its widest numbers
d_strs:         dw      dst_round, dst_score, dst_won, dst_draw, dst_match, dst_prompt, 0
TX_ROUND        equ     0               ; (d_key's kind: the index here)
TX_SCORE        equ     1
TX_WON          equ     2
TX_DRAW         equ     3
TX_MATCH        equ     4
TX_PROMPT       equ     5
dst_round:      db      'ROUND ', 1, 0
dst_score:      db      'ROUND ', 1, '   P1 ', 2, ' : ', 3, ' P2', 0
dst_won:        db      'P', 1, ' WINS ROUND', 0
dst_draw:       db      'DRAW', 0
dst_match:      db      'P', 1, ' WINS THE MATCH', 0
dst_prompt:     db      'ENTER REMATCH  BREAK QUIT', 0
P_tick_end:
                if P_tick_end > H_TICK_END
                .error the duel's piece P_tick is larger than its hole (tick_pre .. check_skel)
                endif

; ================================================================ P_free: main RAM free below W1
                org     H_FREE
P_free:
; d_hud (the match loop, after the drawing): player 2's strip, then the bottom text line as the round state says
; (drawing only: it reads the round state, the logic never reads what it writes). The text: d_key = its kind (TX_*,
; d_strs) and up to three numbers; drawn when the key changes, with the game's text overlay (src/m4/text.asm: loaded
; into W2 as text_chk does, after the tick's drawing; its td_render / td_put / td_num called in place, the duel's
; glyphs d_font laid over the copy's lowercase ones)
d_hud:          call    d_ghp
                ld      hl, d_hcnt
                inc     (hl)
                ld      hl, d_rtick
                inc     (hl)
                jr      nz, hu0
                dec     (hl)            ; (stays at 255)
hu0:            ld      hl, 0           ; L, H: the second and third numbers
                ld      a, (d_match)
                or      a
                jr      z, hu_on
                ld      c, a            ; the match over: its winner and the prompt in turn
                ld      b, TX_MATCH
                ld      a, (d_hcnt)
                and     HUD_ALT
                jr      z, hu_k
                ld      b, TX_PROMPT
                jr      hu_k
hu_on:          ld      a, (d_timer)
                or      a
                jr      z, hu_play
                ld      a, (d_result)   ; a round's end: its result
                ld      c, a
                ld      b, TX_DRAW
                cp      3
                jr      z, hu_k
                ld      de, d_rounds    ; (d_score1 = d_rounds + 1)
                add     a, e
                ld      e, a
                jr      nc, hu1
                inc     d
hu1:            ld      a, (de)
                ld      b, TX_MATCH     ; (the winner's last round)
                cp      WINS
                jr      nc, hu_k
                ld      b, TX_WON
                jr      hu_k
hu_play:        ld      a, (d_rounds)   ; a round on: its number, then the score too
                inc     a
                cp      100
                jr      c, hu2
                ld      a, 99
hu2:            ld      c, a
                ld      b, TX_ROUND
                ld      a, (d_rtick)
                cp      ROUND_TEXT_TICKS
                jr      c, hu_k
                ld      b, TX_SCORE
                ld      hl, (d_score1)  ; (d_score1, d_score2)
hu_k:           ld      a, b            ; the key: B, C, L, H
                ld      de, d_key
                ex      de, hl
                cp      (hl)
                jr      nz, hu_new
                inc     hl
                ld      a, c
                cp      (hl)
                jr      nz, hu_new
                inc     hl
                ld      a, e
                cp      (hl)
                jr      nz, hu_new
                inc     hl
                ld      a, d
                cp      (hl)
                ret     z
hu_new:         ld      hl, d_key
                ld      (hl), b
                inc     hl
                ld      (hl), c
                inc     hl
                ld      (hl), e
                inc     hl
                ld      (hl), d
                ld      a, b            ; the string: d_strs[kind]
                add     a, a
                ld      l, a
                ld      h, 0
                ld      de, d_strs
                add     hl, de
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a
; d_text: HL = a string (bytes 1-3: d_key's numbers) on the bottom text line (also the lobby's and the network's texts)
d_text:         push    hl
                ld      a, OVL_TEXT     ; the text overlay into W2 (only loaded: its entry is not run)
                call    ovl_w2
                ld      hl, d_font      ; the duel's glyphs over its lowercase ones
                ld      de, TX_txt_font + DFONT_OFS
                ld      bc, DFONT_N * 9
                ldir
                ld      hl, MASKBUF     ; the line's bitmap (text.asm TXB: 7 rows x 20 bytes) blank
                ld      de, MASKBUF + 1
                ld      bc, 7 * 20 - 1
                ld      (hl), 0
                ldir
                pop     hl              ; the string into td_str, the numbers in decimal
                ld      de, TX_td_str
huf:            ld      a, (hl)
                inc     hl
                cp      4
                jr      nc, huf_c
                or      a
                jr      z, huf_e
                push    hl
                ld      hl, d_key
                add     a, l
                ld      l, a
                jr      nc, huf1
                inc     h
huf1:           ld      a, (hl)
                call    TX_td_num
                pop     hl
                jr      huf
huf_c:          ld      (de), a
                inc     de
                jr      huf
huf_e:          ld      (de), a
                call    TX_td_render    ; centred into the bitmap, then the screen (rows 193-199, x 80-239)
                jp      TX_td_put
d_key:          db      0xff, 0, 0, 0   ; the text drawn: kind, numbers (0xff: draw again)
P_free_end:
                if P_free_end > H_FREE_END
                .error the duel's piece P_free is larger than its hole (main RAM below W1)
                endif

; ================================================================ P_obj: over objects.asm's loose floors (the lobby)
                org     H_OBJ
P_obj:
; d_lobby (d_entry's end): no NET card (d_ndet: a machine without an MZPico): the local duel at once, no menu. Else the
; menu (1 LOCAL, 2 HOST, 3 JOIN) over the arena drawn first, then the match loop. HOST: a
; room on the relay (NETCREATE: the game id, the build id, 2 slots of 1 byte, the settings: the delay), its code shown
; until the other player is in, then ready; JOIN: the code typed (letters, DEL, ENTER), NETJOIN, ready; both: the match
; starts when the relay says RUNNING (tick 0 on both), ticks 0 .. D-1 sent without keys. An error in words, then the
; menu again; BREAK: the title. The harness (tests/duel_z80.py: d_script set, d_hnet 0) plays local at once.
d_lobby:        ld      hl, (d_script)
                ld      a, h
                or      l
                jr      z, dlb_0
                ld      a, (d_hnet)
                or      a
                jp      z, dlb_go
dlb_0:          call    d_ndet          ; no network card: the local duel at once (the menu only with a network)
                jp      nz, dlb_go
                call    d_draw          ; the arena first (the room's full draw)
dlb_menu:       call    d_nleave        ; (after an error: out of the room)
                ld      hl, dst_menu
                call    d_text
dlb_mk:         call    d_key1
                cp      K_BREAK
                jp      z, d_quit
                cp      '1'
                jp      z, dlb_go
                sub     '2'
                jp      z, dlb_host
                dec     a
                jr      nz, dlb_mk
; JOIN: the code typed into the text (dst_code's dots)
                ld      hl, dst_code + 10
                ld      b, 4
dlj_d:          ld      (hl), '.'
                inc     hl
                djnz    dlj_d
                ld      b, 0
dlj_s:          ld      a, b
                ld      (d_jpos), a
                ld      hl, dst_code
                call    d_text
dlj_k:          call    d_key1
                or      a
                jr      z, dlj_k
                cp      K_BREAK
                jp      z, d_quit
                ld      c, a
                ld      a, (d_jpos)
                ld      b, a
                ld      a, c
                cp      K_ENTER
                jr      z, dlj_go
                cp      K_DEL
                jr      z, dlj_del
                sub     'A'
                cp      26
                jr      nc, dlj_k
                ld      a, b
                cp      4
                jr      nc, dlj_k
                call    dlj_at
                ld      (hl), c
                inc     b
                jr      dlj_s
dlj_del:        ld      a, b
                or      a
                jr      z, dlj_k
                dec     b
                ld      a, b
                call    dlj_at
                ld      (hl), '.'
                jr      dlj_s
dlj_at:         ld      hl, dst_code + 10       ; HL = the code's character A
                add     a, l
                ld      l, a
                ret     nc
                inc     h
                ret
dlj_go:         ld      a, b
                cp      4
                jr      nz, dlj_k
                ld      a, N_JOIN       ; NETJOIN: the game id, the build id, the code (a string, 0x0D)
                ld      hl, d_ncreate
                ld      b, 4
                call    n_cmd
                ld      hl, dst_code + 10
                ld      b, 4
                call    n_out
                ld      a, 13
                out     (NP_DATA), a
                call    n_wait
                jr      nz, dlb_err
                ld      hl, nb_out      ; the slot, slots, bytes, settings' length, the settings
                ld      b, 20
                call    n_in
                ld      a, (nb_out + 4) ; settings[0]: the host's delay
                ld      (d_ndelay), a
                ld      hl, (nb_out + 5); settings[1, 2]: the host's seed (the arenas)
                ld      (d_seed), hl
                ld      a, 2            ; slot 1: player 2
                ld      (d_netm), a
                ld      hl, dst_wait
                call    d_text
                jp      dlb_ready
dlb_go:         call    d_mstart        ; the match's level and its first arena (P_w2), the hash
d_ready:        xor     a               ; (harness: the state before the first tick) the match: its first tick with
                ld      (d_rtick), a    ; the HUD's text drawn again
                dec     a
                ld      (d_key), a
                ld      hl, (FRAMES)
                ld      (LAST_TICK), hl
                jp      d_loop
dlb_st:         call    d_smsg          ; A = a NETSTATUS state: its text
                jr      dlb_e
dlb_err:        ld      hl, dst_link    ; A = an error code: its text
                cp      9
                jr      z, dlb_e
                ld      hl, dst_vers
                cp      6
                jr      z, dlb_e
                ld      hl, dst_room
                cp      7
                jr      z, dlb_e
                ld      hl, dst_err
dlb_e:          call    d_text
                ld      b, 100          ; 2 s, then the menu
dlb_ew:         halt
                djnz    dlb_ew
                jp      dlb_menu
; HOST: the room, its code shown until the other player is in
dlb_host:       ld      hl, (d_seed)    ; settings[1, 2]: this machine's seed as it is now (after a failed join: the
                ld      (d_ncreate + 8), hl     ; other host's, which this machine's arenas use too)
                ld      a, N_CREATE
                ld      hl, d_ncreate
                ld      b, 23
                call    n_do
                jr      nz, dlb_err
                ld      hl, dst_code + 10       ; the code (4 letters), 0x0D, the slot (0)
                ld      b, 4
                call    n_in
                ld      hl, nb_out
                ld      b, 2
                call    n_in
                ld      a, 1            ; slot 0: player 1
                ld      (d_netm), a
                ld      hl, dst_code
                call    d_text
dlh_w:          call    d_key1
                cp      K_BREAK
                jp      z, d_quit
                call    n_stat
                jr      nz, dlb_err
                cp      NS_INROOM
                jr      nz, dlb_st
                ld      a, (nb_out + 2) ; the members
                cp      2
                jr      c, dlh_w
; both: ready, then the match when the relay starts it
dlb_ready:      ld      a, N_READY
                ld      hl, d_one
                ld      b, 1
                call    n_do
                jr      nz, dlb_err
                ld      hl, nb_out      ; (the seed, the start frame: 0xFFFF while waiting)
                ld      b, 4
                call    n_in
dlr_w:          call    d_key1
                cp      K_BREAK
                jp      z, d_quit
                call    n_stat
                jp      nz, dlb_err
                cp      NS_INROOM
                jr      z, dlr_w
                cp      NS_RUNNING
                jp      nz, dlb_st
                ld      hl, 0           ; tick 0; ticks 0 .. D-1 without keys (BomberNet's net_match_start)
                ld      (d_ntick), hl
                ld      (nb_k), hl
dlr_s:          ld      (nb_f), hl
                ld      a, N_SEND
                ld      hl, nb_f
                ld      b, 6
                call    n_do
                jp      nz, dlb_err
                ld      hl, (nb_f)
                inc     hl
                ld      a, (d_ndelay)
                cp      l
                jr      nz, dlr_s
                jp      dlb_go

; d_key1: one frame, then A = the key newly pressed (d_kget), 0 when none or the same as before
d_key1:         halt
                call    d_kget
                ld      hl, d_kprev
                cp      (hl)
                ld      (hl), a
                ret     nz
                xor     a
                ret
; d_kget: A = the key down (KEYMAT, read_inputs): a digit 1-8, a letter A-Z (column 4 A-H, 3 I-P, 2 Q-X, 1 Y Z and
; higher codes for column 1's other keys), K_BREAK, K_ENTER, K_DEL, else 0
d_kget:         call    read_inputs
                ld      hl, KEYMAT + 5
                ld      de, dk_base
dk_c:           ld      a, (de)
                inc     de
                or      a
                jr      z, dk_sp
                ld      c, a
                ld      a, (hl)
                dec     hl
                ld      b, 8
dk_b:           rla
                jr      c, dk_hit
                inc     c
                djnz    dk_b
                jr      dk_c
dk_hit:         ld      a, c
                ret
dk_sp:          ld      a, (KEYMAT + 8) ; BREAK (8/7)
                rla
                ld      a, K_BREAK
                ret     c
                ld      a, (KEYMAT + 0) ; ENTER (0/0)
                rra
                ld      a, K_ENTER
                ret     c
                ld      a, (KEYMAT + 7) ; DEL (7/6)
                and     0x40
                ret     z
                ld      a, K_DEL
                ret
dk_base:        db      '1', 'A', 'I', 'Q', 'Y', 0      ; columns 5, 4, 3, 2, 1: bit 7's character

; ---- the NET driver (BomberNet c/common/netdev_card.c's calls on ports 0x50 / 0x51)
; d_ndet: Z when a NET card answers: REVD's status {02, 06, 04} (a Unicard-compatible device; a missing card floats the
; ports), then INFO (no ERROR, OUTPUT, the command, >= 16 bytes) with the NET feature bit (byte 3, bit 3)
d_ndet:         ld      a, N_REVD
                ld      b, 0
                call    n_do
                ld      hl, nb_st
                ld      a, (hl)
                cp      2
                ret     nz
                inc     hl
                ld      a, (hl)
                cp      N_REVD
                ret     nz
                inc     hl
                ld      a, (hl)
                cp      4
                ret     nz
                ld      hl, nb_out
                ld      b, 4
                call    n_in
                ld      a, N_INFO
                ld      b, 0
                call    n_do
                ret     nz
                ld      a, (nb_st)
                and     0x82
                cp      2
                ret     nz
                ld      a, (nb_st + 1)
                cp      N_INFO
                ret     nz
                ld      a, (nb_st + 2)
                cp      16
                jr      c, ndt_f
                ld      hl, nb_out
                ld      b, 16
                call    n_in
                ld      a, (nb_out + 3)
                cpl
                and     8
                ret
ndt_f:          or      1
                ret
; n_do: A = the command, HL = its parameters, B = their count: the command, then n_wait
n_do:           call    n_cmd
; n_wait: the command's end (the status, STSR: nb_st). -> Z, A = 0: done (its output, if any, to read with n_in); NZ:
; A = the error code (the status' byte 2; 10 the parameters incomplete; 9 no answer in ~20 s: IN_PROGRESS, which
; NETCREATE and NETJOIN show while they wait for the relay)
n_wait:         ld      de, (FRAMES)
nw_l:           ld      a, N_STSR
                out     (NP_CMD), a
                ld      hl, nb_st
                ld      bc, 4 * 256 + NP_CMD
                inir
                ld      a, (nb_st)
                rla
                jr      c, nw_err       ; (bit 7: ERROR)
                rla
                jr      c, nw_prog      ; (bit 6: IN_PROGRESS)
                ld      a, (nb_st)
                and     1               ; (bit 0: BUSY, the parameters incomplete)
                ret     z
                ld      a, 10
                ret
nw_err:         ld      a, (nb_st + 2)
                or      a
                ret     nz
                ld      a, 0xfe
                or      a
                ret
nw_prog:        ld      hl, (FRAMES)
                or      a
                sbc     hl, de
                ld      a, h
                cp      4               ; (1,024 frames)
                jr      c, nw_l
                ld      a, 9
                or      a
                ret
n_cmd:          out     (NP_CMD), a
                ld      a, b
                or      a
                ret     z
n_out:          ld      c, NP_DATA      ; B bytes from HL
                otir
                ret
n_in:           ld      c, NP_DATA      ; B bytes to HL
                inir
                ret
; n_stat: NETSTATUS (8 bytes to nb_out) -> Z, A = the state; NZ, A = the error code
n_stat:         ld      a, N_STATUS
                ld      b, 0
                call    n_do
                ret     nz
                ld      hl, nb_out
                ld      b, 8
                call    n_in
                ld      a, (nb_out)
                cp      a
                ret
P_obj_end:
                if P_obj_end > H_OBJ_END
                .error the duel's piece P_obj is larger than its hole (objects.asm's loose floors)
                endif

; ================================================================ P_lr: over kid.asm leave_room (the lockstep)
                org     H_LR
P_lr:
; d_net (every tick after d_input): the lockstep. The previous tick's hash to the relay (it compares the two: DESYNC);
; this machine's input byte for tick + D (NETSEND); then the tick's two bytes (NETPOLL until avail >= tick) into
; d_in1, d_in2 (slot 0 the host, player 1; slot 1 player 2). Waiting: WAITING after 0.5 s; NETSTATUS every try
; (desync, dropped, no link), BREAK, 10 s of silence: the connection lost. Network timing never enters the logic: the
; tick runs on the agreed bytes alone.
d_net:          ld      a, (d_netm)
                or      a
                ret     z
                ld      hl, (d_ntick)
                ld      a, h
                or      l
                jr      z, dn1
                dec     hl
                ld      (nb_f), hl
                ld      hl, (d_hashv)
                ld      (nb_k), hl
                ld      a, N_HASH
                ld      b, 4
                call    dn_do
dn1:            ld      a, (d_in1)      ; our byte: the harness's (its player's), or either local set of keys
                ld      b, a
                ld      a, (d_in2)
                ld      c, a
                ld      hl, (d_script)
                ld      a, h
                or      l
                ld      a, b
                jr      z, dn_live
                ld      a, (d_netm)
                dec     a
                ld      a, b
                jr      z, dn_k
                ld      a, c
                jr      dn_k
dn_live:        or      c
dn_k:           ld      l, a
                ld      h, 0
                ld      (nb_k), hl
                ld      hl, (d_ntick)
                ld      a, (d_ndelay)
                add     a, l
                ld      l, a
                jr      nc, dn2
                inc     h
dn2:            ld      (nb_f), hl
                ld      a, N_SEND
                ld      b, 6
                call    dn_do
                ld      hl, (d_ntick)
                ld      (nb_f), hl
                ld      hl, (FRAMES)
                ld      (d_nw0), hl
dn_p:           ld      a, N_POLL
                ld      b, 2
                call    dn_do
                ld      hl, nb_out      ; avail, the two slots' bytes
                ld      b, 4
                call    n_in
                ld      hl, (nb_out)
                ld      a, h
                and     l
                inc     a
                jr      z, dn_w         ; (0xFFFF: nothing yet)
                ld      de, (d_ntick)
                or      a
                sbc     hl, de
                jr      nc, dn_got
dn_w:           call    n_stat
                jr      nz, d_nfail
                cp      NS_RUNNING
                jr      nz, dnf_s
                call    read_inputs
                ld      a, (KEYMAT + 8) ; BREAK: give up (the other machine sees the room dropped)
                rla
                jp      c, d_quit
                ld      hl, (FRAMES)
                ld      de, (d_nw0)
                or      a
                sbc     hl, de
                ld      de, NET_SILENT
                sbc     hl, de          ; (no borrow from the sbc above)
                jr      nc, dnf_l
                add     hl, de
                ld      de, NET_WAITMSG
                or      a
                sbc     hl, de
                jr      c, dn_p
                ld      hl, d_nwt
                ld      a, (hl)
                or      a
                jr      nz, dn_p
                inc     (hl)
                ld      hl, dst_wait
                call    d_text
                jr      dn_p
dn_got:         ld      hl, (nb_out + 2)
                ld      (d_in1), hl     ; (d_in1, d_in2)
                ld      hl, (d_ntick)
                inc     hl
                ld      (d_ntick), hl
                ld      hl, d_nwt
                ld      a, (hl)
                or      a
                ret     z
                ld      (hl), 0
                ld      a, 0xff         ; (the HUD's text back after WAITING)
                ld      (d_key), a
                ret
dn_do:          ld      hl, nb_f        ; a lockstep command with nb_f's parameters: failed -> d_nfail
                call    n_do
                ret     z
; d_nfail: a failed command: why (NETSTATUS: a desync, the other gone; else the connection), the text 3 s, the title
d_nfail:        call    n_stat
                jr      nz, dnf_l
dnf_s:          call    d_smsg
                jr      dnf_m
dnf_l:          ld      hl, dst_lost
dnf_m:          call    d_text
                ld      b, 150
dnf_w:          halt
                djnz    dnf_w
                jp      d_quit
; d_smsg: A = a NETSTATUS state -> HL = its text (a desync, the other player gone, else the connection lost)
d_smsg:         ld      hl, dst_desync
                cp      NS_DESYNC
                ret     z
                ld      hl, dst_left
                cp      NS_DROPPED
                ret     z
                ld      hl, dst_lost
                ret
; d_nleave: out of the room (NETLEAVE), local play again
d_nleave:       ld      a, (d_netm)
                or      a
                ret     z
                xor     a
                ld      (d_netm), a
                ld      b, NET_LEAVEW   ; first a moment: a quit is both machines' at one tick, and the other's last
dnl_w:          halt                    ; input must reach it before the room is dropped (the device refuses NETPOLL
                djnz    dnl_w           ; then)
                ld      a, N_LEAVE
                jp      n_do
P_lr_end:
                if P_lr_end > H_LR_END
                .error the duel's piece P_lr is larger than its hole (kid.asm leave_room)
                endif

; ================================================================ P_spk: over objects.asm's spikes (the network's texts)
                org     H_SPK
P_spk:
; NETCREATE's parameters (the first 4 also NETJOIN's): the game id, the build id (tools/duelpatch.py: a CRC-16 of the
; game, its overlays and this patch, so two different disks cannot meet in a room), 2 slots, 1 byte a slot, the
; settings
d_ncreate:      dw      NET_GAME
d_build:        dw      0
                db      2, 1, 3         ; (the settings' length)
                db      NET_DELAY       ; settings[0]: the input delay
                dw      0               ; settings[1, 2]: the arenas' seed (dlb_host: d_seed)
                ds      13
; the lobby's and the network's texts (tools/duelpatch.py checks every dst_ string: its glyphs, its width)
dst_menu:       db      '1 LOCAL  2 HOST  3 JOIN', 0
dst_code:       db      'ROOM CODE ....', 0     ; (+10: the code)
dst_wait:       db      'WAITING', 0
dst_link:       db      'NO LINK', 0
dst_vers:       db      'OTHER VERSION', 0
dst_room:       db      'NO SUCH ROOM', 0
dst_err:        db      'NETWORK ERROR', 0
dst_desync:     db      'DESYNC', 0
dst_left:       db      'OTHER PLAYER LEFT', 0
dst_lost:       db      'CONNECTION LOST', 0
P_spk_end:
                if P_spk_end > H_SPK_END
                .error the duel's piece P_spk is larger than its hole (objects.asm's spikes)
                endif

; ================================================================ P_time: over evres.asm's death text and clock
                org     H_TIME
P_time:
                include "../../build/assets/font_duel.inc"
; dh_x (d_hurt; d_tick around player 2's frame): HITP_CURR <-> GUARDHP_CURR, HITP_DELTA <-> GUARDHP_DELTA
dh_x:           ld      hl, (HITP_CURR)
                ld      a, (GUARDHP_CURR)
                ld      (HITP_CURR), a
                ld      a, l
                ld      (GUARDHP_CURR), a
                ld      a, (HITP_DELTA)
                ld      l, a
                ld      a, (GUARDHP_DELTA)
                ld      (HITP_DELTA), a
                ld      a, l
                ld      (GUARDHP_DELTA), a
                ret
; d_mstart (the lobby's end, every mode): the match's level and its first arena, then the state's hash
d_mstart:       xor     a
                call    d_arena
                jp      d_hash
; d_arena: A = 0 a match's start, 1 the next round, 2 the duel's entry: the arenas' piece P_w2 from the RAM disk into W2's
; top (after any composed chunk still waiting there), then run (it ends in d_reset)
d_arena:        push    af
                call    pend_flush
                ld      a, DUEL_STAGE_PAGE
                ld      de, DSTAGE_W2
                ld      hl, P_w2
                ld      bc, P_w2_end - P_w2
                call    far_copy
                pop     af
                jp      P_w2
; the network's state (never hashed: the logic never reads it)
d_netm:         db      0               ; 0 local, 1 the host (slot 0, player 1), 2 the joiner (slot 1, player 2)
d_ndelay:       db      NET_DELAY       ; the input delay (ticks)
d_ntick:        dw      0               ; the next tick's number (the relay's frame)
d_nw0:          dw      0               ; (the wait's start, FRAMES)
d_nwt:          db      0               ; (WAITING shown)
d_kprev:        db      0               ; (the lobby's last key)
d_jpos:         db      0               ; (the code's characters typed)
d_one:          db      1
nb_f:           dw      0               ; the lockstep's parameters: the frame, then the input byte (NETSEND: 4 bytes,
nb_k:           db      0, 0, 0, 0      ; one used) or the hash (NETHASH)
nb_st:          ds      4               ; the last status
nb_out:         ds      20              ; a command's output
P_time_end:
                if P_time_end > H_TIME_END
                .error the duel's piece P_time is larger than its hole (evres.asm death_text, show_time)
                endif

; ================================================================ P_w2: the arenas (W2's top; staged, copied by d_arena)
; The random arenas (docs/duel-design.md 15; tools/duelsim.py match_start, next_round, arena_set, level_load): per
; match a level of 1-14, per round a room of its pool, both from the seed (d_seed), the match's number (d_mtch) and the
; round's (d_rounds); the room set up as an arena when it is another than the last one. Entry 0 of the table is the
; fixed arena (level 1 room 3): the duel's entry draws it behind the menu, and the harness's d_afix plays every round
; there. The logic's state it changes (the level, the room's tiles, the records through d_reset) is the same on both
; machines: the seed is the host's, the rest the agreed ticks. A = 0 a match's start, 1 the next round, 2 the entry.
                org     H_W2A
P_w2:           dec     a
                jr      z, w_round
                dec     a
                jp      z, w_entry
; w_match: the match's level (the seed, the match; the fixed arena: level 1), loaded when another, then its first round
                ld      a, (d_afix)
                or      a
                ld      a, 1
                jr      nz, wm_l
                ld      a, 0xff
                call    w_rnd
                ld      c, W_LEVELS
                call    w_mod
                inc     a
wm_l:           ld      hl, d_lvl
                cp      (hl)
                call    nz, w_load
; w_round: the round's arena: round 0 any room of the level's pool, later rounds another than the last one
w_round:        ld      a, (d_afix)
                or      a
                ld      a, 0
                jr      nz, w_set
                ld      a, (d_lvl)      ; E, C = the pool's first entry and its count (w_lvtab)
                add     a, a
                ld      hl, w_lvtab - 2
                add     a, l
                ld      l, a
                jr      nc, wr1
                inc     h
wr1:            ld      e, (hl)
                inc     hl
                ld      c, (hl)
                ld      a, (d_rounds)
                ld      b, a
                call    w_rnd
                inc     b
                dec     b
                jr      z, wr_0
                dec     c               ; ((the last entry - first) + 1 + rnd mod (n - 1)) mod n
                call    w_mod
                inc     c
                inc     a
                ld      hl, d_aidx
                add     a, (hl)
                sub     e
wr_0:           call    w_mod           ; (round 0: rnd mod n)
                add     a, e
; w_set: A = the arena's entry: set up unless it is the last one, then the players' reset
w_set:          ld      hl, d_aidx
                cp      (hl)
                jp      z, d_reset
                ld      (hl), a
                ld      l, a            ; w_pool[A]: the room + 32 x the row, player 1's column
                ld      h, 0
                add     hl, hl
                ld      de, w_pool
                add     hl, de
                ld      a, (hl)
                and     0x1f
                ld      (d_room), a
                ld      a, (hl)
                rlca
                rlca
                rlca
                and     3
                ld      (d_arow), a
                inc     hl
                ld      a, (hl)
                ld      (d_c1), a
                add     a, W_GAP
                ld      (d_c2), a
                ld      a, (d_room)     ; the room's links: room 0, a wall on every side (D14, D15)
                dec     a
                add     a, a
                add     a, a
                ld      l, a
                ld      h, 0
                ld      de, LV_LINKS
                add     hl, de
                ld      b, 4
ws_k:           ld      (hl), 0
                inc     hl
                djnz    ws_k
                ld      hl, LV_GTILE    ; no guards
                ld      b, 24
ws_g:           ld      (hl), 30
                inc     hl
                djnz    ws_g
                ld      a, (d_room)     ; the traps and mechanisms plain floor, the bottom row's holes filled
                call    tile_base       ; (duelsim substitute: w_cls 1 anywhere, 2 in the bottom row)
                ld      c, 0
ws_t:           ld      a, (hl)
                and     0x1f
                push    hl
                ld      hl, w_cls
                add     a, l
                ld      l, a
                jr      nc, ws_t1
                inc     h
ws_t1:          ld      a, (hl)
                pop     hl
                dec     a
                jr      z, ws_f
                dec     a
                jr      nz, ws_n
                ld      a, c
                cp      20
                jr      c, ws_n
ws_f:           ld      (hl), T_FLOOR
                xor     a
                ld      (de), a
ws_n:           inc     hl
                inc     de
                inc     c
                ld      a, c
                cp      30
                jr      nz, ws_t
                xor     a               ; no tile animations but the torches, no falling floors; drawn in full
                ld      (TROBS_N), a
                ld      (MOBS_N), a
                ld      (SHOWN_ROOM), a
                dec     a
                ld      (vs_built), a   ; (the view's tile addresses: rebuilt)
                ld      (HP_SHOWN), a   ; (player 1's strip: drawn again)
                ld      a, (d_room)
                ld      (DRAWN_ROOM), a
                ld      (NEXT_ROOM), a
; the torches start flickering as at a room entry (genter.asm anim_tile_modif's torch part: a random first frame, a
; trob each; the room on the left is room 0 here: none there)
                xor     a
                ld      (w_pos), a
wt_l:           ld      a, (d_room)
                ld      (CURR_ROOM), a
                ld      a, (w_pos)
                call    get_curr_tile
                cp      T_TORCH
                jr      z, wt_t
                cp      T_TORCH_DEBRIS
                jr      nz, wt_n
wt_t:           ld      a, 8
                call    prandom
                ld      b, a
                ld      a, (w_pos)
                ld      c, a
                ld      a, (d_room)
                call    o_ptrs
                ld      a, b
                ld      (de), a
                ld      a, (d_room)
                ld      b, a
                ld      a, (w_pos)
                ld      c, a
                ld      a, 1
                call    add_trob
wt_n:           ld      hl, w_pos
                inc     (hl)
                ld      a, (hl)
                cp      30
                jr      nz, wt_l
                jp      d_reset
; w_entry: the duel's entry: the seed (the frame counter; the harness keeps its own; HOST puts it into the room's
; settings, dlb_host); the fixed arena behind the menu
w_entry:        ld      hl, (d_script)
                ld      a, h
                or      l
                jr      nz, we1
                ld      hl, (FRAMES)
                ld      (d_seed), hl
we1:            xor     a
                jp      w_set
; w_load: A = the level: its blueprint (src/m4/ovl_level.asm load_level's copy and directories, no level start), the
; alter-mods pass (the level-start overlay's, loaded into W2 below this piece), its number 1 for the logic (the duel's
; rules were built on level 1: level 12's coupled hit points, its hidden floors, level 13's and 4's specials stay off)
w_load:         ld      (hl), a         ; (HL = d_lvl)
                ld      e, a            ; RD_LV_ADDR + 2305 x the level
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
                ld      a, (d_lvl)
                ld      hl, level_type_tbl
                call    k_tbl
                ld      (LEVEL_TYPE), a
                or      a
                ld      hl, DIR_DUNGEON
                ld      de, DIR_DUNGEON_W
                jr      z, wl1
                ld      hl, DIR_PALACE
                ld      de, DIR_PALACE_W
wl1:            ld      (dir_tab + 3 * CH_ENV + 1), hl
                ld      (dir_tab + 3 * CH_WALL + 1), de
                ld      a, OVL_LEVEL
                call    ovl_w2
                call    LV_alter_mods
                ld      a, 1
                ld      (level_number), a
                ld      a, 0xff
                ld      (d_aidx), a
                ret
; w_rnd: A = b (the round, 0xff the level) -> A = 8 bits (duelsim arena_rnd): x = the seed ^ the match << 8 ^ b, three
; times an xorshift16 (7, 9, 8) step (0 taken as 0xACE1) and + W_RND_ADD, then H ^ L. Keeps BC, DE
w_rnd:          push    bc
                ld      c, a
                ld      hl, (d_seed)
                ld      a, (d_mtch)
                xor     h
                ld      h, a
                ld      a, l
                xor     c
                ld      l, a
                ld      b, 3
wrn1:           ld      a, h
                or      l
                jr      nz, wrn2
                ld      hl, 0xace1
wrn2:           ld      a, h            ; x ^= x << 7
                rra
                ld      a, l
                rra
                xor     h
                ld      h, a
                ld      a, l
                and     1
                rrca
                xor     l
                ld      l, a
                ld      a, h            ; x ^= x >> 9
                srl     a
                xor     l
                ld      l, a
                xor     h               ; x ^= x << 8
                ld      h, a
                push    de
                ld      de, W_RND_ADD
                add     hl, de
                pop     de
                djnz    wrn1
                ld      a, h
                xor     l
                pop     bc
                ret
; w_mod: A = A mod C (C >= 1)
w_mod:          sub     c
                jr      nc, w_mod
                add     a, c
                ret
w_pos:          db      0
                include "../../build/duel_arenas.inc"
P_w2_end:
                if P_w2_end > H_W2A_END
                .error the arenas' piece P_w2 is larger than W2's top
                endif

; ================================================================ the patch sites
                org     H_D14
P_d14:          jp      d14
P_d14_end:
                org     H_D15
P_d15:          dw      d15
P_d15_end:
                org     H_SD1
P_sd1:          dw      d_sdraw
P_sd1_end:
                org     H_SD2
P_sd2:          dw      d_sdraw
P_sd2_end:
                org     H_PP1
P_pp1:          dw      d_ppchar
P_pp1_end:
                org     H_PP2
P_pp2:          dw      d_ppchar
P_pp2_end:
