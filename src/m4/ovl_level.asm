; Level-start overlay (window W2 = COMPOSE_A/COMPOSE_B, src/m4/ovl.asm): load_level and everything only a level
; start runs (the alter-mods pass, the kid's and the guards' start state). Assembled after the main program
; against its symbols (build/ovl_level.inc, tools/ovltool.py); loaded at every call (the compose buffers
; overwrite it). Nothing in here may use the compose buffers.
; M7: the swaps to the presentation program (src/boot/launch.inc) start here too: when the game was started by the
; launcher (the handoff block's copy at HO_MAIN), game_init takes the level, the time and the hit points from it,
; load_level hands over to PRES for the cutscene before a new level (SDLPoP play_level: only when the level changes,
; tbl_cutscenes) and game_over for the time-out, the end and the death text's end. Without the launcher (the test
; harness) nothing changes: game over starts level 1 again.
                include "../../build/ovl_level.inc"
                include "../boot/launch.inc"
                org     OVL_W2
ovl_id          equ     OVL_LEVEL
ovl_entry:      jp      load_level_h            ; entry 0 (stub load_level)
                jp      game_init_h             ; entry 1 (stub game_init)
                jp      game_over_h             ; entry 2 (stub game_over): A = 1, the level to start (or no return)
                jp      game_start              ; entry 3 (stub game_start): the program's start (src/m4/gstart.asm)

; load_level_h: A = level number. Hybrid sound (the launched game): a level done first charges the level end's clock.
; Started by the launcher and a new level with a cutscene before it: to PRES.
load_level_h:   ld      c, a
                call    end_charge
                call    launched
                ld      a, c
                jp      nz, load_level
                ld      hl, level_number
                cp      (hl)
                jp      z, load_level           ; (a restart, the level's first start)
                ld      hl, cutscene_tbl
                call    k_tbl
                or      a
                ld      a, c
                jp      z, load_level
                ld      b, c
                ld      a, ACT_CUTSCENE
                jr      ho_swap
; game_init_h: a new game; started by the launcher: the level, the time, the hit points and the few globals a level
; change keeps (K_TICK, last_loose, is_guard_notice, roomleave_result) from the handoff block
game_init_h:    call    launched
                ld      a, 0                    ; the sound model: live in the launched game, silent in the harness
                jr      nz, gih1                ; (psg.asm snd_playing)
                ld      a, 1
gih1:           ld      (SND_MODE), a
                jp      nz, game_init
                ld      a, (HO_MAIN + HO_OPTIONS)       ; Ctrl+S's sound off goes on (src/m4/ovl_keys.asm snd_onoff)
                rrca
                jr      nc, gih2
                ld      hl, 0
                ld      (spo_1), hl
                ld      (spo_2), hl
                ld      (spo_3), hl
gih2:           ld      a, (HO_MAIN + HO_LEVEL)
                ld      (level_number), a
                call    game_init
                ld      a, (HO_MAIN + HO_REM_MIN)
                ld      (REM_MIN), a
                ld      hl, (HO_MAIN + HO_REM_TICK)
                ld      (REM_TICK), hl
                ld      a, (HO_MAIN + HO_HITP)
                ld      (HITP_BEG_LEV), a
                ld      hl, (HO_MAIN + HO_KTICK)
                ld      (K_TICK), hl
                ld      a, (HO_MAIN + HO_LOOSE)
                ld      (LAST_LOOSE), a
                ld      a, (HO_MAIN + HO_NOTICE)
                ld      (IS_GUARD_NOTICE), a
                ld      a, (HO_MAIN + HO_ROOMLEAVE)
                ld      (ROOMLEAVE), a
                ret
; game_over_h: GAME_OVER set (1 the time is up, 2 the end, 3 the death text ran out). Started by the launcher: to PRES
; (time expired, ending, title). Else a new game from level 1 (A = 1).
game_over_h:    call    launched
                jr      z, go_pres
                ld      a, 1
                ld      (level_number), a
                call    game_init
                ld      a, 1
                ret
go_pres:        ld      a, (GAME_OVER)
                ld      hl, go_act
                call    k_tbl
                ld      b, 0
; ho_swap: A = action, B = level: the handoff block (HO_MAIN, then the RAM disk), the launcher from the RAM disk to
; LN_LOAD (the compose buffers: the game is left for good), started
ho_swap:        di
                push    af
                call    psg_mute                ; (the launcher reads the floppy with interrupts off: no hanging tone)
                pop     af
                ld      hl, HO_MAIN + HO_ACTION
                ld      (hl), a
                inc     hl
                ld      (hl), b
                ld      a, (REM_MIN)
                ld      (HO_MAIN + HO_REM_MIN), a
                ld      hl, (REM_TICK)
                ld      (HO_MAIN + HO_REM_TICK), hl
                ld      a, (HITP_BEG_LEV)
                ld      (HO_MAIN + HO_HITP), a
                ld      hl, (K_TICK)
                ld      (HO_MAIN + HO_KTICK), hl
                ld      a, (LAST_LOOSE)
                ld      (HO_MAIN + HO_LOOSE), a
                ld      a, (IS_GUARD_NOTICE)
                ld      (HO_MAIN + HO_NOTICE), a
                ld      a, (ROOMLEAVE)
                ld      (HO_MAIN + HO_ROOMLEAVE), a
                ld      a, HO_RD_PAGE
                ld      de, HO_RD_ADDR
                call    far_seek
                ld      hl, HO_MAIN
                ld      bc, HO_SIZE * 256 + RD_DATA
                otir
                ld      a, LN_RD_PAGE
                ld      de, LN_RD_ADDR
                ld      hl, LN_LOAD
                ld      bc, LN_MAX
                call    far_copy
                jp      LN_LAUNCH
; end_charge (M7 step 5, docs/m7-design.md D4): the level end waited for the live music (sound.asm end_wait); the
; clock is charged what the ticks model (SND_LEFT) still had, one show_time per tick as the ticks mode counts it, so
; the time left at the next level is the original's whatever the live wait took (END_OVER stopped the clock when the
; live music outlasted the model). Only a level done (the stairs; a restart or the level 6 / 12 exit has nothing to
; charge) in the hybrid / live modes (SND_MODE bit 0). The time running out meanwhile: GAME_OVER (time expired), no
; return. Keeps C.
end_charge:     ld      a, (SND_MODE)
                rrca
                ret     nc
                ld      a, (LEVEL_DONE)
                or      a
                ret     z
ech1:           ld      hl, SND_LEFT
                ld      a, (hl)
                or      a
                ret     z
                dec     (hl)
                push    bc
                call    show_time
                pop     bc
                ld      a, (level_number)
                cp      13
                jr      nc, ech1
                ld      a, (REM_MIN)
                or      a
                jr      nz, ech1
                ld      a, GO_EXPIRED
                ld      (GAME_OVER), a
                pop     hl                      ; (load_level_h's return: no level change)
                call    game_over_h             ; (launched: to PRES, no return; else a new game, A = 1)
                jp      load_level
; launched: Z = the game was started by the launcher (the handoff block's magic at HO_MAIN)
launched:       ld      hl, (HO_MAIN)
                ld      de, HO_MAGIC
                or      a
                sbc     hl, de
                ret
; per level: a cutscene before it (SDLPoP tbl_cutscenes: levels 2, 4, 6, 8, 9, 12)
cutscene_tbl:   db      0, 0, 1, 0, 1, 0, 1, 0, 1, 1, 0, 0, 1, 0, 0, 0
; per GAME_OVER value: the action
go_act:         db      ACT_TITLE, ACT_EXPIRED, ACT_ENDING, ACT_TITLE

; load_level: A = level number: blueprint and directories from the RAM disk, then the level start (play_level)
load_level:     ld      (level_number), a
                ld      e, a            ; 2305 * n = 2048 n + 256 n + n
                ld      d, 0
                add     a, a
                add     a, a
                add     a, a            ; 8n (n <= 15)
                add     a, e            ; 9n = (2048 n + 256 n) >> 8
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
                or      a
                ld      de, 0xd100      ; dungeon directories
                ld      bc, 0xd800
                jr      z, ll_dirs
                ld      de, 0xdb00      ; palace
                ld      bc, 0xe200
ll_dirs:        ld      a, RD_LV_PAGE           ; the directories stay in the RAM disk (dir_entry reads them)
                ld      (dir_tab + 3 * CH_ENV), a
                ld      (dir_tab + 3 * CH_ENV + 1), de
                ld      (dir_tab + 3 * CH_WALL), a
                ld      (dir_tab + 3 * CH_WALL + 1), bc
                ld      (dir_tab + 3 * CH_OBJ), a
                ld      (dir_tab + 3 * CH_KID), a
                ld      (dir_tab + 3 * CH_SWORD), a
                ld      hl, RD_DIR_OBJ
                ld      (dir_tab + 3 * CH_OBJ + 1), hl
                ld      hl, RD_DIR_KID
                ld      (dir_tab + 3 * CH_KID + 1), hl
                ld      hl, RD_DIR_SWORD
                ld      (dir_tab + 3 * CH_SWORD + 1), hl
                ld      (dir_tab + 3 * CH_GUARD), a     ; the level's guard set (SDLPoP tbl_guard_type; a plain guard
                ld      a, (level_number)               ; uses the palace or dungeon set by level type)
                ld      hl, guard_type_tbl
                call    k_tbl
                or      a
                jr      nz, ll_g1
                ld      a, (LEVEL_TYPE)
                or      a
                jr      z, ll_g1
                ld      a, 5                            ; plain guard, palace
ll_g1:          push    af
                ld      l, a                            ; directory = RD_DIR_GUARD + 0x120 * set
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      e, l
                ld      d, h
                add     hl, hl
                add     hl, hl
                add     hl, hl
                add     hl, de                          ; * 72
                add     hl, hl
                add     hl, hl                          ; * 288
                ld      de, RD_DIR_GUARD
                add     hl, de
                ld      (dir_tab + 3 * CH_GUARD + 1), hl
                pop     af                              ; the frame store's guard set (1 MB and more: src/m4/fstore.asm
                ld      hl, OVL_WF + 3                  ; fs_guard; docs/ramdisk-tiers.md section 13)
                call    fs_ovl
                call    alter_mods
                call    play_level
                xor     a
                ld      (SHOWN_ROOM), a
                ld      a, 0xff                 ; the tile addresses of the view: rebuild
                ld      (vs_built), a
                ld      a, 0xff
                ld      (HP_SHOWN), a
                ld      (GHP_SHOWN), a          ; (the guard's strip: drawn again, empty)
                xor     a
                ld      (GHP_M), a
                jp      sprite_forget

; per level: the guard set (0 guard, 1 fat, 2 skeleton, 3 vizier, 4 shadow; 5 = the palace guard, chosen by level
; type) as SDLPoP's tbl_guard_type (-1 = none: 0)
guard_type_tbl: db      0, 0, 0, 2, 0, 0, 1, 0, 0, 0, 0, 0, 4, 3, 0, 0

                include "../m3/altmods.asm"
                include "../m4/levelstart.asm"
                include "../m4/gstart.asm"
ovl_end:
                if ovl_end > OVL_WF
                .error the level-start overlay runs into the fill overlay's window (OVL_WF)
                endif
