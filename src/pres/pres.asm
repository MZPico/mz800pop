; PRES: the presentation program (M7). The launcher (src/boot/boot.asm, src/boot/launch.inc) loads it from POP800.PRS
; entry 0 and starts it at PRES_START with the handoff block at HO_MAIN. docs/m7-design.md §10 (the swaps), §15 (step 6).
;   ACT_TITLE              -> the title (SDLPoP show_title, docs/m7-design.md §1.2 steps a-k with pv_scene; the demo is
;                             step 9: until then the title starts again after k); a key or SHIFT / fire starts a new
;                             game (ACT_PLAY level 1), Ctrl+L the saved game (POP800.SAV)
;   ACT_CUTSCENE level n   -> the level's cutscene (M7 step 7: src/pres/cut.asm, docs/m7-design.md §16), then ACT_PLAY
;                             level n (the time does not run; the level starts when the scene's music ends); Ctrl+L
;                             plays the saved level's cutscene first too
;   ACT_EXPIRED            -> time_expired (cut.asm), no key ends it, then the title (M7 step 8, §17)
;   ACT_ENDING             -> end_sequence: the embrace, the hail screen, TITLE_MAIN until music 56 ends (no Hall of
;                             Fame: D7), no key ends it, then the title
; Music (M7 step 11, docs/m7-design.md 19): the Master System soundtrack's pieces from three banks (tools/presbank.py;
;   each a POP800.PRS entry copied to the torch cache, load_bank): A for the title a-g, the cutscenes, time_expired and the
;   ending, B from h (pv_scene, i), C from j; the pieces loop (psg.asm's loop command) and fade out at their screen's end;
;   the DOS cue lengths (the ticks model) still time the screens (cutsim PRES_TICKS60 where a piece decides a wait).
; The title (M7 step 6):
;   - art: POP800.PRS entries PRS_T_* (tools/mkgamedisk.py title_entries: the images of build/assets/title.pack in PZ
;     bands of at most 8000 bytes, stored as they are at the free places of main RAM, and the index art_idx), music:
;     entry PRS_SOUND (build/assets/sound_pres.bin) copied to the torch cache (RAM-disk page 6 0x0000, scratch the game
;     rebuilds) and played by the game's PSG player (src/m4/psg.asm, included);
;   - screens: composed in the shadow room's place (RAM-disk page 1 0x0000-0x7CFF, scratch): row y, plane p, byte
;     column x at y * 160 + p * 40 + x; a band is unpacked into DBUF and drawn row by row (the row read from page 1,
;     combined, written to VRAM or back to page 1); VRAM gets page-1 rows (the fades, the restores, the wipe);
;   - the step table title_steps: SDLPoP ticks counted into 50 Hz frames (x 5/6) with a remainder (t_adv), so every
;     wait ends at the frame floor(5 T / 6) after the start, T = the SDLPoP ticks so far (tests/m7_title.py checks it);
;   - fades: the EGA original has no palette fade: fade_in_2 / fade_out_2 draw / clear the screen in 5 interlaced
;     passes (rows y mod 5 = 0..4), one every 4 ticks (DOSBox, §15); the wipe transition_ltr: 40 columns of 8 pixels
;     from page 1, one every 2 ticks (SDLPoP: 160 of 2 pixels at 120 a second).
; Memory: the image from 0x2000 (code, variables, art_idx); the art's PZ bands in 0x1200-0x1FFF, end_of_pres-0x7FFF and
; ART2_START-ART2_END; DBUF 0xC000-0xDF3F (a band; also the scene / sound bank load area and load_saved's sector and
; directory buffers); the stack below 0xFE00; the IM2 vector 0xFE00, the PSG ring 0xFE02-0xFEFF; low RAM: FRAMES
; 0x0800 (as the game: tests/m7_sound.py's tracker), the player's SP_VARS 0x03C8. 0x8000-0xBFFF stay free (the
; launcher's buffers and its image: it stays resident at 0xB000 while PRES runs). The VRAM window (and the CG ROM at
; 0x1000-0x1FFF) is mapped only inside the row / column copies: the code, ROWBUF, the stack and the ISR's data are
; outside 0x1000-0x1FFF and 0x8000-0x9FFF.
                include "../boot/launch.inc"
                include "../../build/assets/title.inc"  ; TITLE_F_MUSIC, _REST (tools/build_assets.py build_title)

VRAM            equ     0x8000
PORT_WF         equ     0xcc
PORT_DMD        equ     0xce
PORT_SCRL       equ     0xcf
PORT_PAL        equ     0xf0
PORT_JOY1       equ     0xf0
PORT_KBD_COL    equ     0xd0
PORT_KBD_ROW    equ     0xd1
PIOA_CTRL       equ     0xfc
PORT_PPIC       equ     0xd3
P_VECTAB        equ     0xfe00
P_STACK         equ     0xfe00
FRAMES          equ     0x0800          ; 16-bit, counted by the VBLN interrupt
DBUF            equ     0xc000          ; a band of an image (8000 bytes at most, tools/mkgamedisk.py TITLE_BAND)
DBUF_SIZE       equ     8000
SBANK_TMP       equ     0xc000          ; POP800.PRS entry 2 (the sound bank) is loaded here ...
SBANK_MAX       equ     0x2880          ; ... and copied whole to the torch cache (page 6 0x0000-0x287F)
ART2_START      equ     DBUF + DBUF_SIZE        ; the art's third place (tools/mkgamedisk.py title_entries)
ART2_END        equ     0xfc00
OVL_W2          equ     DBUF - 0x700    ; save.asm's buffers: the sector at DBUF, the directory DBUF + 0x100..0x8FF
PRS_CEXP        equ     1               ; POP800.PRS entries (tools/mkgamedisk.py): time_expired (no sprites of its own)
PRS_SOUND       equ     2
PRS_T_MAIN      equ     3               ; the title's art: each entry holds its images' PZ bands and art_idx slots,
PRS_T_PG        equ     4               ;   at fixed places (the texts share one place: only one of them is loaded)
PRS_T_LOGO      equ     5               ;   res 54, 55
PRS_T_FRAME     equ     6
PRS_T_ABS       equ     7
PRS_T_MARRY     equ     8
PRS_T_CRED      equ     9
PRS_T_HAIL      equ     10
PRS_CROOM       equ     11              ; the cutscene engine (cut.asm), the room, the common sprites (tools/cutart.py)
PRS_C26         equ     12              ; the scenes' sprites: cutscene_2_6, _4, _8, _9, _12
PRS_C4          equ     13
PRS_C8          equ     14
PRS_C9          equ     15
PRS_C12         equ     16
PRS_CPV         equ     17              ; pv_scene's sprites (each PZ, unpacked into a slot buffer when drawn) ...
PRS_CPV2        equ     18              ; ... and the rest, loaded at DBUF and copied to 0x8000-0x9F3F
PRS_CEND        equ     19              ; end_sequence_anim's sprites
PRS_T_FRED      equ     20              ; the red STORY_FRAME
PRS_SND_B       equ     21              ; the sound banks B (h-i: Jaffar's piece) and C (j-k: the title theme, the credits);
PRS_SND_C       equ     22              ;   PRS_SOUND is A (tools/presbank.py; M7 step 11, docs/m7-design.md 19)
SLOT_ROOM       equ     0               ; the cutscene room's art_idx slot (the title's art is not loaded then)
PSG_BANK_PAGE   equ     6               ; the sound bank for src/m4/psg.asm (its stream addresses count from 0)
PSG_BANK_ADDR   equ     0x0000
P1_PAGE         equ     1               ; the screen in the RAM disk (the shadow room's place)
MUSIC_TITLE     equ     54              ; the title theme (bank A, C: SMS song 1, looped)
PM_CREDITS      equ     42              ; the credits' piece (bank C: SMS song 3; an id without a DOS sound)
; the art index (art_idx; tools/mkgamedisk.py writes it): per slot ART_ENT bytes
SLOT_MAIN       equ     0               ; res 51 TITLE_MAIN
SLOT_PRESENTS   equ     1               ; res 52
SLOT_GAME       equ     2               ; res 53
SLOT_POP        equ     3               ; res 54 (the logo, transparent)
SLOT_MECHNER    equ     4               ; res 55 (the copyright)
SLOT_FRAME      equ     5               ; res 41 STORY_FRAME
SLOT_CREDITS    equ     6               ; res 45 STORY_CREDITS (1 bpp)
SLOT_ABSENCE    equ     7               ; res 42 STORY_ABSENCE (1 bpp)
SLOT_MARRY      equ     8               ; res 43 STORY_MARRY (1 bpp)
SLOT_HAIL       equ     9               ; res 44 STORY_HAIL (1 bpp)
SLOT_FRAMER     equ     10              ; STORY_FRAME with the red background (the hail screen: load_title_images(0))
ART_SLOTS       equ     11
ART_ENT         equ     20              ; +0 byte column, +1 row, +2 wbytes, +3 h, +4 flags (bit 0 mask, bit 1 partial
                                        ; edge, bit 2 mono), +5 lm, +6 rm, +7 bands, +8 per band: rows, PZ address
ART_BANDS       equ     4
TGT_VRAM        equ     0
TGT_P1          equ     1
; the step table's operations
OP_LOOP         equ     0               ; word: continue there
OP_STEP         equ     1               ; byte: a step starts ('a'..'k': t_step; tests/m7_title.py: ts_step)
OP_MUSIC        equ     2               ; byte: the sound id (psg.asm snd_start)
OP_WAIT         equ     3               ; word: SDLPoP ticks, then wait until the clock reaches them
OP_DRAW         equ     4               ; slot, target (TGT_VRAM, TGT_P1): draw the image over page 1's screen
OP_RESTORE      equ     5               ; slot: page 1's screen back on VRAM in the image's box
OP_WIPE         equ     6               ; transition_ltr: page 1 to VRAM in 40 columns of 8 pixels, 2 ticks each
OP_FADEIN       equ     7               ; byte: music; fade_in_2 (EGA): page 1 to VRAM in 5 interlaced passes, 4 ticks
                                        ; apart; the music (0xFF: none) starts with the last pass
OP_FADEOUT      equ     8               ; fade_out_2 (EGA): VRAM cleared in 5 interlaced passes, 4 ticks apart
OP_SYNC         equ     9               ; the clock starts now (FRAMES; after the first screen's decoding)
; the cutscenes' operations (cut.asm): SDLPoP seg001's scene functions
OP_CSND         equ     10              ; byte: play_sound(id)
OP_CHG          equ     11              ; set_hourglass_state(hourglass_frame())
OP_CLOAD        equ     12              ; byte: Char = the slot (0 kid, 1 shad)
OP_CSAVE        equ     13              ; byte: the slot = Char
OP_CSET         equ     14              ; field, value: Char's field (cut.asm CR_*)
OP_CSEQ         equ     15              ; word: seqtbl_offset_char (an offset into the sequence table)
OP_CPLAY        equ     16              ; play_seq
OP_CFRAMES      equ     17              ; byte: proc_cutscene_frame(n)
OP_CIF6         equ     18              ; word: continue there unless hourglass_frame() >= 6 (cutscene_12)
OP_CEND         equ     19              ; the scene is over: wait until its music ends, then the level
OP_CFT          equ     20              ; byte: cutscene_frame_time (pv_scene)
OP_CUNTIL       equ     21              ; do proc_cutscene_frame(1) while the sound plays
OP_CFLASH       equ     22              ; n, colour: flash_time, flash_color
OP_CHGN         equ     23              ; byte: hourglass_state
OP_CSAND        equ     24              ; byte: hourglass_sandflow
OP_CFADEIN      equ     25              ; fade_in_1 (EGA): one frame, its objects shown by the 5 interlaced passes (§17)
OP_CFADEOUT     equ     26              ; fade_out_1 (EGA): one frame, not shown, then the 5 clearing passes
OP_WAITM        equ     27              ; wait until the music started last ends (mus_end, the ticks model)
OP_CRET         equ     28              ; the scene is over: back to the steps after it (t_ret)
OP_CSHOW        equ     29              ; copy_screen_rect(&screen_rect): the room at once (the ending has no fade-in)
OP_TITLE        equ     30              ; the title again (from its loading)
OP_LOAD         equ     31              ; byte: a POP800.PRS entry: the music pauses (interrupts off) while the floppy reads
OP_CSCENE       equ     32              ; h: pv_scene's art is loaded, its room goes to page 1; its script runs next
OP_EXPEND       equ     33              ; time_expired is over: the title
OP_KEYS         equ     34              ; byte: cut_mode (2 no keys, 3 a key ends the wait: do_wait); keys held count after release
OP_MUSE         equ     35              ; word: the music starting now lasts so many ticks (mus_end, OP_WAITM)
OP_MSTOP        equ     36              ; the music stops (snd_halt): a piece cut at its screen's end
OP_LOADB        equ     37              ; byte: a sound bank entry (PRS_SOUND, PRS_SND_B/C) to the torch cache unless it is there
OP_MFADE        equ     38              ; the music fades out now (psg.asm mf_start): silent and stopped MFADE_FRAMES (45)
                                        ; frames later
OP_MFADEM       equ     39              ; the fade scheduled to end when the music started last ends (mus_end; OP_WAITM)
OP_MFEND        equ     40              ; word: the fade scheduled to end so many ticks after the clock's target (MFWAIT)
; save.asm's variables: load_saved writes the time, the level and the hit points straight into the handoff block
level_number    equ     ho + HO_LEVEL
REM_MIN         equ     ho + HO_REM_MIN
REM_TICK        equ     ho + HO_REM_TICK
HITP_BEG_LEV    equ     ho + HO_HITP

                org     PRES_START
pres:           di
                ld      sp, P_STACK
                out     (0xe0), a
                out     (0xe1), a
                ld      hl, HO_MAIN     ; the request
                ld      de, ho
                ld      bc, HO_SIZE
                ldir
                ld      a, (ho + HO_ACTION)     ; (M7 step 10) Ctrl+S's sound off: kept in the options; the ending turns
                cp      ACT_ENDING              ; it on for good (SDLPoP end_sequence_anim)
                jr      nz, pr_opt
                xor     a
                ld      (ho + HO_OPTIONS), a
pr_opt:         ld      a, (ho + HO_OPTIONS)
                rrca
                jr      nc, pr_snd
                ld      hl, 0                   ; the player's writes patched away (as src/m4/ovl_keys.asm snd_onoff)
                ld      (spo_1), hl
                ld      (spo_2), hl
                ld      (spo_3), hl
                ld      (spo_4), hl             ; (the fade's writes)
                ld      (spo_5), hl
pr_snd:         call    video_init
                call    LN_LOADING      ; "LOADING..." until the first picture (the title's or the scene's fade-in covers it)
                ld      a, (ho + HO_ACTION)
                cp      ACT_TITLE
                jp      z, title
                cp      ACT_CUTSCENE
                jr      z, p_cutscene
                cp      ACT_ENDING
                ld      a, CK_END
                jr      z, p_kind
                ld      a, CK_EXP       ; (ACT_EXPIRED)
                jr      p_kind
; p_cutscene: the cutscene before level ho.level (from the game, or Ctrl+L), time_expired or the ending (A = its kind):
; the sound bank (unless the title loaded it), the engine with the room (PRS_CROOM), then cut.asm's cut_main (the
; scene's sprites, the scene, then the level or the title)
p_cutscene:     xor     a               ; CK_LEVEL
p_kind:         ld      (cut_kind), a
                di
                ld      sp, P_STACK
                ld      a, PRS_SOUND    ; (bank A: the cutscene piece, the hourglass piece, the title theme)
                call    load_bank
                ld      a, PRS_CROOM + PRS_KEEP ; (the scene's sprites follow: cut_setup)
                call    LN_PRS_LOAD
                jp      cut_main
; p_cutplay: after the cutscene: the level (ho as it came: the time and the hit points unchanged)
p_cutplay:      ld      a, ACT_PLAY
                ld      (ho + HO_ACTION), a
                call    snd_halt
p_go:           di                      ; the block to the RAM disk, then the launcher
                call    snd_halt
                call    pal_off
                ld      a, HO_RD_PAGE
                out     (RD_PAGE), a
                ld      bc, RD_ADDR + (HO_RD_ADDR & 0xff00)
                ld      a, HO_RD_ADDR & 0xff
                out     (c), a
                ld      hl, ho
                ld      bc, HO_SIZE * 256 + RD_DATA
                otir
                jp      LN_LAUNCH
; p_new: a new game (60 minutes, 719 ticks, 3 hit points; the options kept, K_TICK .. the end 0)
p_new:          ld      hl, ho_new
                ld      de, ho + HO_ACTION
                ld      bc, HO_OPTIONS - HO_ACTION
                ldir
p_play:         ld      a, ACT_PLAY     ; (Ctrl+L: load_saved set the level, the time and the hit points)
p_play_a:       ld      hl, ho + HO_KTICK
                ld      b, HO_SIZE - HO_KTICK
p_play_d:       ld      (ho + HO_ACTION), a     ; (p_duel: from K_TICK's next byte on)
pt_0:           ld      (hl), 0
                inc     hl
                djnz    pt_0
                call    snd_halt
                call    cls             ; (SDLPoP: draw_rect(&screen_rect, color_0_black) before start_game)
                ld      a, (ho + HO_LEVEL)      ; (Ctrl+L: a level with a cutscene plays it first: SDLPoP play_level)
                ld      hl, cut_has
                ld      bc, 6
                cpir
                jr      z, p_cutscene
                jr      p_go
cut_has:        db      2, 4, 6, 8, 9, 12       ; the levels with a cutscene (SDLPoP tbl_cutscenes)
; p_duel (Ctrl+D): the duel easter egg (src/duel/duel.asm): a new game's block (level 1, its arena) with ACT_DUEL; in
; K_TICK's place the duel's seed (src/duel/duel.asm w_entry; docs/duel-design.md 22.3): the frames since PRES started
; (the title's run: as long as the player waited)
p_duel:         ld      hl, ho_new
                ld      de, ho + HO_ACTION
                ld      bc, HO_OPTIONS - HO_ACTION
                ldir
                ld      hl, (FRAMES)
                ld      (ho + HO_KTICK), hl
                ld      hl, ho + HO_KTICK + 2
                ld      b, HO_SIZE - HO_KTICK - 2
                ld      a, ACT_DUEL
                jr      p_play_d
p_duel_end:
DUEL_PRES_USED  equ     p_duel_end - p_duel + p_duel_k_end - p_duel_k   ; (the duel's Ctrl+D code, for the figures; tools/mkgamedisk.py PRES_RESERVE)

; ---------------------------------------------------------------- the title
title:          di
                ld      sp, P_STACK
                call    pal_off
                ld      a, PRS_SOUND    ; (bank A: the title theme, the hourglass piece)
                call    load_bank
                ld      hl, tl_ents     ; the art (the cutscene engine, if any, is overwritten)
tl_1:           ld      a, (hl)
                inc     a
                jr      z, tl_2
                dec     a
                push    hl
                call    LN_PRS_LOAD
                pop     hl
                inc     hl
                jr      tl_1
tl_ents:        db      PRS_T_MAIN + PRS_KEEP, PRS_T_PG + PRS_KEEP, PRS_T_LOGO + PRS_KEEP, PRS_T_FRAME + PRS_KEEP, PRS_T_ABS, 0xff ; (PRS_KEEP: the next load
                                                                ; follows at once: the motor runs on)
tl_2:           call    irq_init        ; (EI; the player stopped)
                ld      a, 1            ; (psg.asm: snd_playing asks the player; PRES's waits do not ask it)
                ld      (SND_MODE), a
                xor     a
                ld      (k_armed), a    ; (keys held down from before count only after they were let go)
                ld      (cut_mode), a
                ld      (pv_on), a
                ld      hl, (FRAMES)
                ld      (t_target), hl
                ld      hl, title_steps
                ld      (t_pc), hl
ip_next:        ld      hl, (t_pc)
                ld      a, (hl)
                inc     hl
                ld      (t_pc), hl
                add     a, a
                ld      e, a
                ld      d, 0
                ld      hl, op_tab
                add     hl, de
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a
                ld      de, ip_next
                push    de
                jp      (hl)
op_tab:         dw      op_loop, op_step, op_music, op_wait, op_draw, op_restore, op_wipe, op_fadein, op_fadeout, op_sync
                dw      op_csnd, op_chg, op_cload, op_csave, op_cset, op_cseq, op_cplay, op_cframes, op_cif6, op_cend
                dw      op_cft, op_cuntil, op_cflash, op_chgn, op_csand, op_cfadein, op_cfadeout, op_waitm, op_cret, op_cshow
                dw      title, op_load, op_cscene, op_expend, op_keys, op_muse, snd_halt, op_loadb, mf_start, op_mfadem, op_mfend
; the operations' arguments: A = the next byte, DE = the next word
op_byte:        ld      hl, (t_pc)
                ld      a, (hl)
                inc     hl
                ld      (t_pc), hl
                ret
op_word:        ld      hl, (t_pc)
                ld      e, (hl)
                inc     hl
                ld      d, (hl)
                inc     hl
                ld      (t_pc), hl
                ret
op_sync:        ld      hl, (FRAMES)
                ld      (t_target), hl
                ld      hl, 0
                ld      (ct_tick), hl
                xor     a
                ld      (t_frac), a
ts_sync:        ret                     ; (tests/m7_title.py: the title's clock starts: tick 0)
op_loop:        call    op_word
                ld      (t_pc), de
                ret
op_step:        call    op_byte
                ld      (t_step), a
ts_step:        ret                     ; (tests/m7_title.py: a step starts here; VRAM = the last step's end)
op_music:       call    op_byte
                jp      snd_start
; op_load: a POP800.PRS entry while the player runs: the floppy with interrupts off: no hanging tone, the stream pauses
op_load:        call    op_byte
do_load:        push    af
                call    psg_mute
tc_mute:        pop     af              ; (tests/m7_cut.py: sndsim's chip is muted too)
                call    LN_PRS_LOAD
                ei
                ret
op_keys:        call    op_byte
                ld      (cut_mode), a
                xor     a
                ld      (k_armed), a
                ret
op_muse:        call    op_word
                ld      hl, (ct_tick)
                add     hl, de
                ld      (mus_end), hl
                ret
; op_waitm: until the music started last ends (the ticks model: mus_end on the clock's tick count)
op_waitm:       ld      hl, (mus_end)
                ld      de, (ct_tick)
                or      a
                sbc     hl, de
                ret     c
                ret     z
                ex      de, hl
                call    t_adv
                jp      t_wait
; op_mfend: DE = ticks: the music's fade is scheduled (psg.asm mf_delay) to end at the frame the clock reaches DE
; ticks after its target (t_adv's count, the clock itself unchanged): it starts MFADE_FRAMES before (at once if that
; has passed). The ISR counts the delay: the drawing done meanwhile does not move it.
op_mfend:       call    op_word
mfe_de:         ld      hl, (ct_tick)
                push    hl
                ld      hl, (t_target)
                push    hl
                ld      a, (t_frac)
                push    af
                call    t_adv
                ld      hl, (t_target)  ; the end frame
                pop     af
                ld      (t_frac), a
                pop     de
                ld      (t_target), de
                pop     de
                ld      (ct_tick), de
                ld      de, (FRAMES)
                or      a
                sbc     hl, de
                ld      de, -MFADE_FRAMES
                add     hl, de          ; the delay: frames until the fade must start
                bit     7, h
                jp      nz, mf_start    ; (passed: at once)
                ld      a, h
                or      a
                ld      a, l
                jr      nz, mfe_max
                cp      255 - MFADE_PER
                jp      c, mf_delay
mfe_max:        ld      a, 255 - MFADE_PER - 1  ; (too far ahead: earlier, ending before the screen's end; MFWAIT
                jp      mf_delay                ; splits its waits so that it never comes here)
; op_mfadem: the fade scheduled to end at mus_end (the end of the OP_WAITM that follows; more than MF_SPLIT ticks
; ahead: first a wait until MF_SPLIT before it, as MFWAIT)
op_mfadem:      ld      hl, (mus_end)
                ld      de, (ct_tick)
                or      a
                sbc     hl, de
                ex      de, hl
                jr      nc, omf_1
                ld      de, 0
omf_1:          ld      hl, MF_SPLIT
                or      a
                sbc     hl, de
                jr      nc, mfe_de
                ex      de, hl          ; DE = MF_SPLIT - left
                ld      hl, 0
                or      a
                sbc     hl, de
                ex      de, hl          ; = left - MF_SPLIT
                call    t_adv
                call    t_wait
                ld      de, MF_SPLIT
                jr      mfe_de
; op_cret: back to the steps after the scene (cut.asm's code is no longer needed: it may be overwritten)
op_cret:        call    pal_off
                ld      hl, (t_ret)
                ld      (t_pc), hl
                xor     a
                ld      (pv_on), a
                ret
; op_cscene: h: the loads (the music pauses meanwhile), then pv_scene's script (its first wait: the music of g ends)
op_cscene:      ld      hl, (t_pc)
                ld      (t_ret), hl
                ld      a, PRS_CROOM + PRS_KEEP ; (pv_scene's sprites follow: cut_setup)
                call    do_load
                jp      cut_pv
; pal_off: the palette as the title has it (cut.asm pal_on: the cutscenes' own)
pal_off:        ld      a, 0x40
                out     (PORT_PAL), a
                xor     a
                out     (PORT_PAL), a
                ld      a, 0x11
                out     (PORT_PAL), a
                ld      a, 0x22
                out     (PORT_PAL), a
                ld      a, 0x33
                out     (PORT_PAL), a
                ret
op_wait:        call    op_word
                call    t_adv
                jp      t_wait
op_draw:        call    op_byte
                push    af
                call    op_byte
                ld      c, a
                pop     af
                jp      draw_img
op_restore:     call    op_byte
                call    art_ent
                ld      c, (ix + 0)
                ld      b, (ix + 2)
                ld      e, (ix + 1)
                ld      d, (ix + 3)
                ld      a, 1
                jp      copy_rows
op_wipe:        xor     a
                ld      (t_col), a
ow_1:           call    t_wait
                ld      a, (t_col)
                call    wipe_col
tw_col:         ld      de, 2           ; (tests/m7_title.py: column t_col is on the screen)
                call    t_adv
                ld      hl, t_col
                inc     (hl)
                ld      a, (hl)
                cp      40
                jr      nz, ow_1
                ret
op_fadein:      call    op_byte         ; the music id that starts with the last pass (0xFF: none)
                ld      (t_music), a
                xor     a
                ld      (t_col), a
ofi_1:          call    t_wait
                ld      a, (t_col)
                cp      4
                jr      nz, ofi_2
                ld      a, (t_music)    ; (the last pass: SDLPoP plays the music when the fade is done)
                cp      0xff
                call    nz, snd_start
ofi_2:          ld      a, (t_col)
                ld      e, a
                ld      d, 40
                ld      bc, 40 * 256 + 0
                ld      a, 5
                call    copy_rows
tf_pass:        ld      a, (t_col)      ; (tests/m7_title.py: pass t_col is on the screen)
                cp      4
                ret     z               ; (the next operation starts with the last pass)
                inc     a
                ld      (t_col), a
                ld      de, 4
                call    t_adv
                jr      ofi_1
op_fadeout:     xor     a
                ld      (t_col), a
ofo_1:          call    t_wait
                ld      a, (t_col)
                call    clear_rows
tfo_pass:       ld      de, 4           ; (tests/m7_title.py: pass t_col is on the screen)           ; (the next fade-in's first pass 4 ticks after the last)
                call    t_adv
                ld      hl, t_col
                inc     (hl)
                ld      a, (hl)
                cp      5
                jr      nz, ofo_1
                ret

; load_bank: A = a sound bank's POP800.PRS entry: to the torch cache (SBANK_MAX bytes through SBANK_TMP) unless it is
; the one there (bank_cur); the motor kept running (its two callers load again at once). With the interrupts off (the title's and p_cutscene's loads); op_loadb while the music
; runs: the stream pauses for the floppy (do_load) and goes on after: a piece at the same bank address in both banks
; (tools/presbank.py SHARED: the hourglass piece of g in A and B) plays on across the reload at h.
load_bank:      ld      hl, bank_cur
                cp      (hl)
                ret     z
                ld      (hl), a
                or      PRS_KEEP        ; (the title's art or the cutscene's room follows at once: the motor runs on)
                call    LN_PRS_LOAD
lb_copy:        ld      a, PSG_BANK_PAGE
                ld      de, PSG_BANK_ADDR
                call    far_seek
                ld      hl, SBANK_TMP
                ld      de, SBANK_MAX
                call    rd_out
tc_bank:        ret                     ; (tests/m7_cut.py: the bank bank_cur is in the torch cache)
op_loadb:       call    op_byte
                ld      hl, bank_cur
                cp      (hl)
                ret     z
                ld      (hl), a
                call    do_load
                jr      lb_copy

; t_adv: DE = SDLPoP ticks: the clock's target t_target += (t_frac + 5 DE) / 6 frames, t_frac = the remainder; ct_tick
; (the cutscenes' tick count) += DE
t_adv:          ld      hl, (ct_tick)
                add     hl, de
                ld      (ct_tick), hl
                ld      h, d
                ld      l, e
                add     hl, hl
                add     hl, hl
                add     hl, de
                ld      a, (t_frac)
                ld      e, a
                ld      d, 0
                add     hl, de
                ld      bc, 0
                ld      de, 6
ta_1:           or      a
                sbc     hl, de
                jr      c, ta_2
                inc     bc
                jr      ta_1
ta_2:           add     hl, de
                ld      a, l
                ld      (t_frac), a
                ld      hl, (t_target)
                add     hl, bc
                ld      (t_target), hl
                ret
; t_wait: until FRAMES reaches t_target; meanwhile once a frame the music ring is refilled and the keys are read.
; The ring is also refilled on entry: a late frame returns at once, and frames that run late one after another (the
; ending's embrace) must not leave the ring unfilled (the dense SMS streams empty it in ~30 frames)
t_wait:         call    snd_fill
tw_loop:        ld      hl, (FRAMES)
                ld      de, (t_target)
                or      a
                sbc     hl, de
                bit     7, h
                ret     z
                halt
                call    snd_fill
                call    keys
                jr      tw_loop

; keys: a key (or the joystick's fire) pressed after all were let go: Ctrl+L loads the saved game (on failure the
; title goes on), any other a new game; CTRL alone does nothing
keys:           ld      a, (cut_mode)   ; time_expired, the ending: disable_keys
                cp      2
                ret     z
                ld      hl, kmat
                ld      c, 0
k_col:          ld      a, c
                out     (PORT_KBD_COL), a
                in      a, (PORT_KBD_ROW)
                cpl
                ld      (hl), a
                inc     hl
                inc     c
                ld      a, c
                cp      10
                jr      nz, k_col
                ld      a, (kmat + 8)   ; CTRL (column 8 bit 6) apart
                ld      c, a
                and     0xbf
                ld      (kmat + 8), a
                ld      a, c
                and     0x40
                ld      c, a
                in      a, (PORT_JOY1)
                cpl
                and     0x10            ; fire
                ld      b, a
                ld      hl, kmat
                ld      e, 10
k_or:           ld      a, (hl)         ; B = any key but CTRL, or fire
                or      b
                ld      b, a
                inc     hl
                dec     e
                jr      nz, k_or
                ld      hl, k_armed
                bit     0, (hl)
                jr      nz, k_arm
                ld      a, b
                or      c
                ret     nz              ; still something down from before
                inc     (hl)
                ret
k_arm:          ld      a, b
                or      a
                ret     z               ; nothing, or CTRL alone
                ld      (hl), 0         ; (let go before the next)
                ld      a, (cut_mode)   ; a cutscene: any key ends it (SDLPoP do_paused)
                or      a
                jr      z, k_title
                cp      3
                jp      nz, cut_abort
                ; the ending's waits (do_wait): the key ends the wait: the clock jumps to now, and ct_tick (which
                ; t_adv advanced by the whole wait when it was scheduled) gives back the ticks not waited
                ld      hl, (t_target)
                ld      de, (FRAMES)
                or      a
                sbc     hl, de
                ret     c
                ret     z
                ld      (t_target), de
                ld      d, h            ; (the frames left x 6 / 5 ticks)
                ld      e, l
                add     hl, hl
                add     hl, de
                add     hl, hl          ; x 6
                ld      a, 0
                ld      bc, 5
                ld      de, 0xffff
k_div:          inc     de
                sbc     hl, bc
                jr      nc, k_div
                ld      hl, (ct_tick)
                or      a
                sbc     hl, de
                ld      (ct_tick), hl
                ret
k_title:        
                ld      a, c
                or      a
                jr      z, p_new_k
p_duel_k:       ld      a, (kmat + 4)   ; Ctrl+D (D: column 4 bit 4): the duel (docs/duel-design.md)
                and     0x10
                jp      nz, p_duel
p_duel_k_end:   ld      a, (kmat + 3)   ; L: column 3 bit 4
                and     0x10
                jr      z, p_new_k
                call    psg_mute        ; Ctrl+L: the floppy with interrupts off: no hanging tone (the stream pauses)
tk_load:        call    load_saved      ; A = 0: ho's level, time and hit points set
                or      a
                jp      z, p_play
                ld      a, (pv_on)      ; no valid save, no disk: the title goes on; in pv_scene load_saved's buffers
                or      a               ; (DBUF) overwrote its sprites: the title starts again
                ret     z
                jp      title
p_new_k:        jp      p_new

; ---------------------------------------------------------------- drawing
; art_ent: A = slot -> IX = its art_idx entry
art_ent:        ld      l, a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                ld      d, h
                ld      e, l
                add     hl, hl
                add     hl, hl
                add     hl, de          ; x 20
                ld      de, art_idx
                add     hl, de
                push    hl
                pop     ix
                ret
; row_addr: A = row -> HL = 40 row, DE = 160 row
row_addr:       ld      l, a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      d, h
                ld      e, l
                add     hl, hl
                add     hl, hl
                add     hl, de
                ld      d, h
                ld      e, l
                ex      de, hl
                add     hl, hl
                add     hl, hl
                ex      de, hl
                ret

; copy_rows: page 1 -> VRAM in a box: C = byte column, B = wbytes, E = first row, D = rows, A = row step
copy_rows:      ld      (cr_step), a
                ld      (cr_x), bc
                ld      (cr_y), de
cr_row:         ld      a, (cr_y)
                call    row_addr
                ld      a, (cr_x)
                ld      c, a
                ld      b, 0
                add     hl, bc
                ex      de, hl
                add     hl, bc
                ex      de, hl
                ld      bc, VRAM
                add     hl, bc          ; HL = the VRAM address, DE = page 1's (plane 0)
                in      a, (0xe0)       ; VRAM mapped
                ld      a, 1
cr_pl:          out     (PORT_WF), a    ; (single plane writes)
                push    af
                push    hl
                ld      a, P1_PAGE
                call    far_seek
                ld      a, (cr_x + 1)
                ld      b, a
                ld      c, RD_DATA
                inir
                ld      hl, 40
                add     hl, de
                ex      de, hl
                pop     hl
                pop     af
                add     a, a
                cp      16
                jr      nz, cr_pl
                in      a, (0xe1)
                ld      a, (cr_step)
                ld      hl, cr_y
                add     a, (hl)
                ld      (hl), a
                ld      hl, cr_y + 1
                dec     (hl)
                jr      nz, cr_row
                ret

; clear_rows: A = first row: rows A, A + 5, ... (40 of them) of VRAM black
clear_rows:     push    af
                call    row_addr
                ld      de, VRAM
                add     hl, de
                in      a, (0xe0)
                ld      a, 0x80         ; REPLACE, colour 0: one write clears all four planes
                out     (PORT_WF), a
                ld      de, 200 - 40
                ld      c, 40
clr_r:          ld      b, 40
clr_b:          ld      (hl), 0
                inc     hl
                djnz    clr_b
                add     hl, de
                dec     c
                jr      nz, clr_r
                in      a, (0xe1)
                pop     af
                ret

; wipe_col: A = byte column: the column of page 1's screen to VRAM (800 bytes)
wipe_col:       ld      (wc_x), a
                in      a, (0xe0)
                ld      a, P1_PAGE
                out     (RD_PAGE), a
                ld      a, 1
wc_pl:          out     (PORT_WF), a
                push    af
                ld      hl, (wc_x)      ; (wc_x + 1 = 0)
                ld      de, VRAM
                add     hl, de          ; VRAM, column x
                ex      de, hl
                ld      hl, (wc_x)
                ld      a, (wc_p)       ; page 1: + 40 p
                ld      c, a
                ld      b, 0
                add     hl, bc
                ex      de, hl          ; HL = VRAM, DE = page 1
                ld      a, 200
wc_row:         ex      af, af'
                ld      b, d
                ld      c, RD_ADDR
                out     (c), e
                in      a, (RD_DATA)
                ld      (hl), a
                ld      bc, 40
                add     hl, bc
                ex      de, hl
                ld      bc, 160
                add     hl, bc
                ex      de, hl
                ex      af, af'
                dec     a
                jr      nz, wc_row
                ld      a, (wc_p)
                add     a, 40
                ld      (wc_p), a
                pop     af
                add     a, a
                cp      16
                jr      nz, wc_pl
                xor     a
                ld      (wc_p), a
                in      a, (0xe1)
                ret

; draw_img: A = slot, C = target (TGT_VRAM, TGT_P1): the image drawn over page 1's screen (copy: the box's pixels
; inside the image's extent; transp: where the mask says; mono: its set pixels white), the result written to the
; target. Bands are unpacked into DBUF one after the other; the music ring is refilled before each.
draw_img:       ld      b, a
                ld      a, c
                ld      (di_tgt), a
                ld      a, b
                call    art_ent
                ld      a, (ix + 1)
                ld      (di_y), a
                ld      a, (ix + 7)
                ld      (di_nb), a
                push    ix
                pop     hl
                ld      de, 8
                add     hl, de
                ld      (di_bp), hl
di_band:        call    snd_fill
                ld      hl, (di_bp)
                ld      a, (hl)
                ld      (di_rows), a
                ld      (di_r), a
                inc     hl
                ld      e, (hl)
                inc     hl
                ld      d, (hl)
                inc     hl
                ld      (di_bp), hl
                ex      de, hl
                ld      de, DBUF
                call    unpz
                ld      a, (di_rows)    ; a plane's block in the band: rows x wbytes
                ld      b, a
                ld      e, (ix + 2)
                ld      d, 0
                ld      hl, 0
di_m:           add     hl, de
                djnz    di_m
                ld      (di_pstr), hl
                ld      hl, DBUF
                ld      (di_src), hl
di_row:         call    row_do
                ld      hl, di_y
                inc     (hl)
                ld      hl, (di_src)
                ld      e, (ix + 2)
                ld      d, 0
                add     hl, de
                ld      (di_src), hl
                ld      hl, di_r
                dec     (hl)
                jr      nz, di_row
                ld      hl, di_nb
                dec     (hl)
                jr      nz, di_band
                ret
; row_do: row di_y of the image (its band data at di_src): read, combined, written
row_do:         ld      a, (di_y)
                call    row_addr
                ld      c, (ix + 0)
                ld      b, 0
                add     hl, bc
                ld      bc, VRAM
                add     hl, bc
                ld      (rd_v), hl      ; the VRAM address
                ld      c, (ix + 0)
                ld      b, 0
                ex      de, hl
                add     hl, bc
                ld      (rd_p), hl      ; page 1's (plane 0)
                ld      a, (ix + 4)
                and     7
                call    nz, row_get     ; (a plain copy needs no background)
                ld      a, (ix + 4)
                bit     2, a
                jp      nz, rd_mono
                bit     0, a
                jp      nz, rd_transp
                ; copy: the planes' rows over ROWBUF, the edge columns merged through lm / rm
                ld      hl, (di_src)
                ld      de, rowbuf
                ld      a, 4
rdc_pl:         push    af
                push    hl
                ld      a, (de)         ; the background's edge bytes
                ld      (rd_e0), a
                push    de
                ld      a, (ix + 2)
                dec     a
                ld      c, a
                ld      b, 0
                ex      de, hl
                add     hl, bc
                ld      a, (hl)
                ld      (rd_e1), a
                ex      de, hl
                pop     de
                push    de
                ld      c, (ix + 2)
                ldir
                pop     hl              ; HL = this plane's ROWBUF row
                ld      a, (rd_e0)      ; first: old ^ ((old ^ new) & lm)
                ld      c, a
                xor     (hl)
                and     (ix + 5)
                xor     c
                ld      (hl), a
                ld      a, (ix + 2)
                dec     a
                ld      c, a
                ld      b, 0
                add     hl, bc
                ld      a, (rd_e1)      ; last: the same with rm
                ld      c, a
                xor     (hl)
                and     (ix + 6)
                xor     c
                ld      (hl), a
                inc     hl
                ex      de, hl          ; DE = the next plane's ROWBUF row
                pop     hl
                ld      bc, (di_pstr)
                add     hl, bc
                pop     af
                dec     a
                jr      nz, rdc_pl
                jr      row_put
rd_transp:      ld      hl, (di_src)    ; (the mask block first, then the planes)
                ld      bc, (di_pstr)
                ld      iy, rowbuf
                ld      a, 4
rdt_pl:         push    af
                push    hl
                add     hl, bc          ; this plane's row
                ex      de, hl
                ld      hl, (di_src)    ; the mask's row
                ld      b, (ix + 2)
rdt_b:          ld      a, (iy + 0)
                and     (hl)
                ex      de, hl
                or      (hl)
                ex      de, hl
                ld      (iy + 0), a
                inc     iy
                inc     hl
                inc     de
                djnz    rdt_b
                pop     hl
                ld      bc, (di_pstr)
                add     hl, bc
                pop     af
                dec     a
                jr      nz, rdt_pl
                jr      row_put
rd_mono:        ld      hl, rowbuf      ; (the text's row ORed into every plane: colour 15)
                ld      c, 4
rdm_pl:         ld      de, (di_src)
                ld      b, (ix + 2)
rdm_b:          ld      a, (de)
                or      (hl)
                ld      (hl), a
                inc     hl
                inc     de
                djnz    rdm_b
                dec     c
                jr      nz, rdm_pl
                jr      row_put
; row_get: ROWBUF = page 1's row segment (4 planes x wbytes)
row_get:        ld      de, (rd_p)
                ld      hl, rowbuf
                ld      b, 4
rg_pl:          push    bc
                push    de
                ld      a, P1_PAGE
                call    far_seek
                ld      b, (ix + 2)
                ld      c, RD_DATA
                inir
                pop     de
                ex      de, hl
                ld      bc, 40
                add     hl, bc
                ex      de, hl
                pop     bc
                djnz    rg_pl
                ret
; row_put: ROWBUF to the target
row_put:        ld      a, (di_tgt)
                or      a
                jr      nz, rp_p1
                ld      de, (rd_v)
                ld      hl, rowbuf
                in      a, (0xe0)
                ld      a, 1
rpv_pl:         out     (PORT_WF), a
                push    de
                ld      c, (ix + 2)
                ld      b, 0
                ldir
                pop     de
                add     a, a
                cp      16
                jr      nz, rpv_pl
                in      a, (0xe1)
                ret
rp_p1:          ld      de, (rd_p)
                ld      hl, rowbuf
                ld      b, 4
rpp_pl:         push    bc
                push    de
                push    hl
                ld      a, P1_PAGE
                call    far_seek
                pop     hl
                ld      b, (ix + 2)
                ld      c, RD_DATA
                otir
                pop     de
                ex      de, hl
                ld      bc, 40
                add     hl, bc
                ex      de, hl
                pop     bc
                djnz    rpp_pl
                ret

; rd_out: HL = source, DE = count: to the RAM disk at its current address
rd_out:         ld      c, RD_DATA
ro_1:           ld      a, d
                or      a
                jr      z, ro_2
                ld      b, 0
                otir
                dec     d
                jr      ro_1
ro_2:           ld      a, e
                or      a
                ret     z
                ld      b, a
                otir
                ret

video_init:     in      a, (0xe0)
                ld      a, 0x02         ; 320x200, 16 colours
                out     (PORT_DMD), a
                ld      c, PORT_SCRL
                xor     a
                ld      b, 0x06         ; border black
                out     (c), a
                ld      b, 0x01         ; scroll offset 0
                out     (c), a
                ld      b, 0x02
                out     (c), a
                ld      a, 0x40         ; palette group 0, PLT0-3 identity
                out     (PORT_PAL), a
                xor     a
                out     (PORT_PAL), a
                ld      a, 0x11
                out     (PORT_PAL), a
                ld      a, 0x22
                out     (PORT_PAL), a
                ld      a, 0x33
                out     (PORT_PAL), a
                in      a, (0xe1)
cls:            in      a, (0xe0)       ; VRAM at 0x8000 (and the CG ROM at 0x1000)
                ld      a, 0x80         ; REPLACE, colour 0
                out     (PORT_WF), a
                ld      hl, VRAM
                ld      de, VRAM + 1
                ld      bc, 8000 - 1
                ld      (hl), 0xff
                ldir
                in      a, (0xe1)
                ret

; ---------------------------------------------------------------- the 50 Hz interrupt (VBLN through the PIO, as the game)
irq_init:       call    snd_halt        ; (psg.asm: no stream, the PSG muted; interrupts stay off)
                ld      hl, isr         ; IM2 with the PIO's vector 0: one table entry (0xFE02.. is the PSG ring)
                ld      (P_VECTAB), hl
                ld      a, high P_VECTAB
                ld      i, a
                im      2
                ld      a, 0x04         ; 8255 PC2 = 0: the 8253 counter 2 interrupt masked
                out     (PORT_PPIC), a
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
isr:            push    af
                push    hl
                ld      hl, (FRAMES)
                inc     hl
                ld      (FRAMES), hl
                jp      snd_isr         ; (psg.asm: the PSG player's frame; it pops HL, AF and returns)

                include "../m1/far.asm"
                include "../m4/psg.asm"
                include "../boot/unpz.asm"
SV_PRES         equ     1               ; (save.asm sv_off: the motor off through the launcher, LN_MOTOR_OFF)
                include "../m4/save.asm"        ; load_saved (Ctrl+L); its save_game is not used here

; ---------------------------------------------------------------- the title's steps (docs/m7-design.md §1.2; SDLPoP ticks)
; MFWAIT t, late: OP_WAIT of t ticks with the music's fade scheduled to end (silent) `late` ticks after the wait's end
; (OP_MFEND: the waits' total unchanged; a wait longer than MF_SPLIT is split, as the delay is at most 251 frames).
; MF_FO: the ticks from a fade_out_2's start to its last pass (the screen black): a fade that ends with the fade-out
; that follows the wait.
MF_SPLIT        equ     200
MFWAIT          macro   t, late
                if (t) > MF_SPLIT
                db      OP_WAIT
                dw      (t) - MF_SPLIT
                db      OP_MFEND
                dw      MF_SPLIT + (late)
                db      OP_WAIT
                dw      MF_SPLIT
                else
                db      OP_MFEND
                dw      (t) + (late)
                db      OP_WAIT
                dw      t
                endif
                endm
MF_FO           equ     16
title_steps:    db      OP_DRAW, SLOT_MAIN, TGT_P1      ; (load_title_images: the screen of step a in page 1)
                db      OP_SYNC
                db      OP_FADEIN, MUSIC_TITLE          ; fade_in_2 (EGA: 5 passes), music 54 with the last
                db      OP_STEP, 'a', OP_WAIT
                dw      130                             ; a: TITLE_MAIN, music 54 starts
                db      OP_STEP, 'b', OP_DRAW, SLOT_PRESENTS, TGT_VRAM, OP_WAIT
                dw      205                             ; b: + "Broderbund Software presents"
                db      OP_STEP, 'c', OP_RESTORE, SLOT_PRESENTS, OP_WAIT
                dw      65                              ; c: cleared
                db      OP_STEP, 'd', OP_DRAW, SLOT_GAME, TGT_VRAM, OP_WAIT
                dw      270                             ; d: "a game by Jordan Mechner"
                db      OP_STEP, 'e', OP_RESTORE, SLOT_GAME, OP_WAIT
                dw      235                             ; e: cleared
                db      OP_STEP, 'f', OP_DRAW, SLOT_POP, TGT_VRAM, OP_DRAW, SLOT_MECHNER, TGT_VRAM
                db      OP_DRAW, SLOT_FRAME, TGT_P1, OP_DRAW, SLOT_ABSENCE, TGT_P1, OP_WAIT
                dw      TITLE_F_MUSIC                   ; f: the logo and the copyright; g's screen in page 1; the title
                db      OP_MSTOP, OP_WAIT               ;   theme's 2nd pass ends (stopped between two interrupts: on
                dw      TITLE_F_REST                    ;   the pass boundary), then silence (a deviation: SDLPoP waits
                                                        ;   until music 54 ends, 1 s later; tools/titleref.py)
                db      OP_STEP, 'g', OP_MUSIC, 55, OP_WIPE
                MFWAIT  600, MF_FO                      ; g: frame + "In the Sultan's absence", music 55, faded out to
                db      OP_FADEOUT, OP_MSTOP            ;   silence at fade_out_2's last pass (the text gone)
                db      OP_STEP, 'h', OP_LOADB, PRS_SND_B, OP_CSCENE    ; h: bank B, pv_scene (cut.asm s_pv: waits for
                                                                ; music 55's DOS end first, as load_intro; silent until its cue 50)
                db      OP_LOAD, PRS_T_FRAME + PRS_KEEP, OP_LOAD, PRS_T_MARRY, OP_DRAW, SLOT_FRAME, TGT_P1, OP_DRAW, SLOT_MARRY, TGT_P1
                db      OP_WAIT
                dw      TITLE_I_LOAD                    ; (their decoding: the screen stays black, silent)
                db      OP_FADEIN, 52                   ; fade_in_2, the Grand Vizier again (DOS 52's screen; pv_scene's
                                                        ;   faded out at its end)
                db      OP_STEP, 'i', OP_MFADEM, OP_WAITM       ; i: frame + "Marry Jaffar", until music 52's DOS end, the
                db      OP_MSTOP, OP_LOADB, PRS_SND_C   ;   piece faded out over its last 54 ticks (the DOS is silent from here: bank C)
                db      OP_LOAD, PRS_T_MAIN + PRS_KEEP, OP_LOAD, PRS_T_LOGO + PRS_KEEP, OP_LOAD, PRS_T_CRED
                db      OP_DRAW, SLOT_MAIN, TGT_P1, OP_DRAW, SLOT_POP, TGT_P1, OP_DRAW, SLOT_MECHNER, TGT_P1, OP_WAIT
                dw      TITLE_J_LOAD                    ; (SDLPoP draws j's screen during i's wait: the floppy would stop 52)
                db      OP_STEP, 'j', OP_MUSIC, MUSIC_TITLE, OP_WIPE, OP_MFEND  ; j: main + logo + copyright (the wipe), the
                dw      120                             ;   title theme, faded out to j's end (scheduled before k's screen is
                db      OP_DRAW, SLOT_FRAME, TGT_P1, OP_DRAW, SLOT_CREDITS, TGT_P1, OP_WAIT     ; decoded into page 1: ~75
                dw      120                             ;   of the wait's 100 frames)
                db      OP_STEP, 'k', OP_MUSIC, PM_CREDITS, OP_WIPE
                MFWAIT  360, MF_FO                      ; k: frame + credits, the credits' piece (faded out with m's fade-out)
                ; l: no Hall of Fame (D7); m: the demo (step 9)
                db      OP_STEP, 'm', OP_FADEOUT, OP_MSTOP      ; fade_out_2 (EGA: 5 passes), then (until step 9) the title again
                db      OP_TITLE
TITLE_I_LOAD    equ     110                             ; ticks for the decoding of FRAME + MARRY (the emulator: tests/m7_title.py)
TITLE_J_LOAD    equ     130                             ; ticks for MAIN + logo + copyright

; the ending after the embrace (end_sequence, SDLPoP seg001.c; no Hall of Fame: D7): cut.asm's s_end returns here
ending_steps:   db      OP_LOAD, PRS_T_FRED + PRS_KEEP, OP_LOAD, PRS_T_HAIL + PRS_KEEP, OP_LOAD, PRS_T_MAIN
                db      OP_DRAW, SLOT_FRAMER, TGT_P1, OP_DRAW, SLOT_HAIL, TGT_P1
                db      OP_STEP, 'p', OP_MUSE
                dw      CUT_L56                         ; (the title theme started with the embrace loops on: no new music;
                db      OP_FADEIN, 0xff                 ; the ticks model's 56 ends when it has played 3 times) fade_in_2
                db      OP_STEP, 'q', OP_KEYS, 3, OP_DRAW, SLOT_MAIN, TGT_P1, OP_WAIT
                dw      900                             ; frame + "The tyrant Jaffar lies dead" (a key ends the wait: do_wait)
                db      OP_STEP, 'r', OP_KEYS, 2, OP_WIPE, OP_KEYS, 3, OP_WAIT
                dw      160                             ; TITLE_MAIN (the wipe's 80 ticks + 160 = start_timer(240))
                db      OP_STEP, 's', OP_KEYS, 2, OP_WAITM      ; while (check_sound_playing()): until the model's 56 ends
                db      OP_STEP, 't', OP_MSTOP, OP_FADEOUT, OP_TITLE    ; (the title theme has played 3 times: cut here)

; ---------------------------------------------------------------- data
ho_new:         db      ACT_PLAY, 1, 60 ; a new game: level 1, 60 minutes 719 ticks, 3 hit points (then the options
                dw      719             ; are kept, K_TICK, last_loose and the result are 0)
                db      3
ho:             ds      HO_SIZE
t_pc:           dw      0               ; the step table's next operation
t_step:         db      0               ; the step ('a'..)
t_target:       dw      0               ; the clock: the frame (FRAMES) the current wait ends at
t_frac:         db      0               ;   and the remainder in sixths of a frame (= SDLPoP ticks x 5 mod 6)
t_col:          db      0               ; the wipe's column, the fade's pass
t_music:        db      0               ; the fade-in's music
k_armed:        db      0               ; 1: every key was let go since the title started (or since the last press)
cut_mode:       db      0               ; 1: a level's cutscene runs (keys end it); 2: disable_keys; 0: the title's keys
cut_kind:       db      0               ; the scene p_cutscene starts (cut.asm CK_*)
pv_on:          db      0               ; 1: pv_scene runs (its sprites may lie in load_saved's buffers)
t_ret:          dw      0               ; the steps after the scene (OP_CRET)
mus_end:        dw      0               ; the tick (ct_tick) the music started last ends (ticks model)
bank_cur:       db      0               ; the sound bank in the torch cache (its POP800.PRS entry; 0: none)
ct_tick:        dw      0               ; SDLPoP ticks counted by t_adv
kmat:           ds      10
cr_step:        db      0
cr_x:           dw      0               ; byte column, wbytes
cr_y:           dw      0               ; row, rows left
wc_x:           dw      0
wc_p:           db      0
di_tgt:         db      0
di_y:           db      0
di_nb:          db      0
di_rows:        db      0
di_r:           db      0
di_bp:          dw      0
di_pstr:        dw      0
di_src:         dw      0
rd_v:           dw      0
rd_p:           dw      0
rd_e0:          db      0
rd_e1:          db      0
up_neg:         dw      0               ; (unpz.asm)
TEXT_REM:       dw      0               ; (save.asm's save_game: never called in PRES)
TEXT_GEN:       db      0
TEXT_MSG_GEN:   db      0
TEXT_MSG:       db      0
rowbuf:         ds      160             ; a row segment: 4 planes x wbytes
art_idx:        ds      ART_SLOTS * ART_ENT     ; (POP800.PRS's art entries write their slots)
end_of_pres:
                if end_of_pres > 0x8000
                .error PRES runs into the launcher's buffers
                endif
                include "cut.asm"       ; (not in PRES's image: POP800.PRS's room entry, tools/mkgamedisk.py)
                if end_of_cut > 0x6000
                .error the cutscene engine leaves too little room for the scenes' sprites
                endif
                if ART2_END > P_STACK - 0x100
                .error the art's third place runs into the stack
                endif
