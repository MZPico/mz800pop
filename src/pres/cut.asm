; ---------------------------------------------------------------- the cutscene engine (M7 steps 7-8, docs/m7-design.md §16, §17)
; Included by pres.asm right after end_of_pres: this code and its variables are not part of PRES's own image (POP800.PRS
; entry 0) but of the room entry PRS_CROOM (tools/mkgamedisk.py, tools/cutart.py), which PRES loads for a cutscene
; (p_cutscene, op_cscene). A port of SDLPoP seg001's frame engine (tools/cutsim.py is the reference, checked against SDLPoP by
; tools/cut_suite.py):
;   - the scenes are scripts in the title's step interpreter (ip_next; the OP_C* operations below), one per SDLPoP scene
;     function (cutscene_2_6, _4, _8, _9, _12, pv_scene, time_expired, end_sequence_anim), written as the C code is;
;   - proc_cutscene_frame (cut_frame): both characters' sequences (play_seq: SDLPoP's sequence table in logic.bin,
;     RAM-disk page 6 0xD000, read in place; the frame tables: the kid's in logic.bin, frame_tbl_cuts in cut.inc), the
;     torches (prandom), the hourglass and its sand, a star when the frames left are odd, the flash, the sound (the ticks model at 60 a
;     second: the level start waits until the music ends, OP_CEND), then the drawing;
;   - the drawing (cut_draw): the objects of the frame in SDLPoP's draw order (the torches; the characters by their y;
;     the hourglass; the pillar; the sand), byte-aligned sprites (tools/cutart.py pre-shifts and pre-flips every image a
;     scene draws); dirty rectangles: an object whose image or place changed since the last drawn frame makes its old
;     and its new box dirty, a star its pixel; overlapping rectangles merge; each row of a rectangle is composed in
;     RB (the background row from the room in page 1, then every object that covers it, then the stars) and copied to
;     VRAM. A frame that starts SKIP_LATE frames or more after its time is not drawn (its logic always runs); the next
;     drawn frame catches up through the same dirty rectangles;
;   - timing: the title's clock (t_adv / t_wait: SDLPoP ticks x 5/6 frames); a cutscene frame is cut_ft ticks (6);
;     the EGA fades (OP_CFADEIN / OP_CFADEOUT): one frame at their start, no frame time of its own, then 5 interlaced
;     passes 4 ticks apart and 4 more ticks (DOSBox: §17); the fade-in's passes show the room and that frame's objects;
;   - pv_scene's sprites do not fit unpacked (103 KB): each is its own PZ block, unpacked into its slot's buffer
;     (SLOTBUF0/1, 0xA400..) when the frame is drawn and its image changed;
;   - the palette (pal_on): group 1, PLT0 = black: EGA attribute 0 is MZ 4 (the flash sets PLT0 white, as the EGA original
;     flashes attribute 0), EGA 13 (black too, but it does not flash) MZ 0;
;   - a key (or the joystick's fire) aborts the scene as SDLPoP's do_paused does: the sound stops, the screen is
;     cleared and the level starts at once (keys: cut_abort).
; Memory (a cutscene run): the engine end_of_pres..end_of_cut; the room's PZ bands, later the scene's sprites, from
; end_of_cut to 0x7FFF and in DBUF (pv_scene also 0x8000-0x9F3F: read only while VRAM is not mapped); the common sprites
; (flames, hourglass, sand, pillar) in 0x1200-0x1FFF and 0xDF40-0xF3FF; cut_spr 0xF400-0xFBFF; RB
; 0xA000-0xA3FF and the slot buffers 0xA400-0xAFFF (the launcher's track buffer: free once the loads are done).
; The sprites are read only while VRAM (and the CG ROM at 0x1000) is not mapped.

RB_PAGE         equ     0xa0            ; the row being composed: plane p at (RB_PAGE + p) * 256 + byte column
LOGIC_PAGE      equ     6
LOGIC_SEQ       equ     0xd000          ; logic.bin (tools/build_assets.py LOGIC_LAYOUT): the sequence table
LOGIC_KIDFR     equ     0xda00          ;   the kid's frame table (5 bytes a frame)
SKIP_LATE       equ     4               ; a frame this many frames late is not drawn
CUT_SPR         equ     0xf400          ; cut_spr (the scene's entry writes it, tools/cutart.py): 8 bytes per sprite, 0xFF ends
CUT_SPR_MAX     equ     (0xfc00 - CUT_SPR) / 8
SLOTBUF0        equ     0xa400          ; pv_scene: the sprite shown in the kid slot, the shad slot
SLOTBUF1        equ     0xa400 + 0x540
SLOTBUF_MAX     equ     0x540
FADE_TICKS      equ     20              ; (tools/cutsim.py FADE_TICKS)
CK_LEVEL        equ     0               ; cut_kind: the level's scene; pv_scene; time_expired; the ending
CK_PV           equ     1
CK_EXP          equ     2
CK_END          equ     3
CF_FULL         equ     1               ; a scene's flags: the room's 200 rows (else rows 192-199 black: the game's offscreen)
CF_NOKEYS       equ     2               ; disable_keys
CF_TKEYS        equ     4               ; the title's keys (pv_scene)
CF_PZ           equ     8               ; cut_spr's addresses are PZ blocks
CUT_COM_N       equ     30              ; cut_com: the flames of torch 0 (9), of torch 1 (9), the hourglass (8: states
COM_TORCH       equ     0               ; 0-7, 0 unused), the sand (3), the pillar
COM_GLASS       equ     18
COM_SAND        equ     26
COM_PILLAR      equ     29
TORCH_Y         equ     99              ; (ybottom 116, 18 rows)
GLASS_COL       equ     19
GLASS_Y         equ     141             ; (ybottom 168, 28 rows)
SAND_COL        equ     20
SAND_Y          equ     157             ; (ybottom 164, 8 rows)
PILLAR_COL      equ     30
PILLAR_Y        equ     120             ; (ybottom 167, 48 rows)
N_IDS           equ     7               ; the objects' identities: 0 kid slot, 1 shad slot, 2 torch 0, 3 torch 1,
ID_TORCH        equ     2               ; 4 hourglass, 5 pillar, 6 sand
ID_GLASS        equ     4
ID_PILLAR       equ     5
ID_SAND         equ     6
OBJ_SIZE        equ     8               ; an object: sprite (2: its rows; wb, h before it), byte column, ytop, identity,
MAX_OBJS        equ     8               ; (spare), key (2: what identifies the image: its cut_spr entry, else the sprite)
SHOWN_SIZE      equ     6               ; cut_shown: key (2), byte column, ytop, wb, h
MAX_RECTS       equ     16
RO_SIZE         equ     9               ; cut_ro: an object in the rectangle being drawn (comp_rect)
; a character record (SDLPoP char_type, the fields the scenes use)
CR_FRAME        equ     0
CR_X            equ     1
CR_Y            equ     2
CR_DIR          equ     3
CR_CHARID       equ     4
CR_SEQ          equ     5               ; (word: an offset into the sequence table)
CR_SIZE         equ     7
CHARID_KID      equ     0
CHARID_MOUSE    equ     24

; ---------------------------------------------------------------- entry (from p_cutscene: the room entry loaded)
cut_main:       call    cut_setup
                call    irq_init        ; (EI)
                ld      a, 1
                ld      (SND_MODE), a
                ld      a, (cut_kind)
                cp      CK_END
                jr      nz, cm_go
                ld      hl, ending_steps
                ld      (t_ret), hl
cm_go:          jp      ip_next
; cut_pv: from op_cscene (the title runs: the interrupts and the music 55 go on; floppy reads pause it)
cut_pv:         ld      a, CK_PV
                ld      (cut_kind), a
                ld      (pv_on), a
                call    cut_setup
                ei
                ret
; cut_setup: the room into page 1 (load_intro's offscreen surface), the scene's sprites, the engine's state, t_pc
cut_setup:      ld      a, SLOT_ROOM
                ld      c, TGT_P1
                call    draw_img
                ld      a, (cut_kind)
                or      a
                jr      nz, cs_named
                ld      a, (ho + HO_LEVEL)
                ld      hl, cut_levels
cm_find:        inc     (hl)
                dec     (hl)
                jp      z, p_cutplay    ; (no scene: the level at once)
                cp      (hl)
                jr      z, cm_found
                ld      de, 5
                add     hl, de
                jr      cm_find
cs_named:       dec     a               ; CK_PV, CK_EXP, CK_END: cut_named's records
                ld      l, a
                add     a, a
                add     a, a
                add     a, l
                ld      e, a
                ld      d, 0
                ld      hl, cut_named
                add     hl, de
cm_found:       inc     hl
                ld      a, (hl)         ; the scene's entry
                inc     hl
                ld      e, (hl)
                inc     hl
                ld      d, (hl)
                ld      (t_pc), de      ; its script
                inc     hl
                ld      c, (hl)         ; its flags
                ld      b, a
                ld      a, c
                ld      (cut_flags), a
                push    bc
                bit     0, c            ; CF_FULL
                call    z, p1_black
                pop     bc
                ld      a, c
                and     CF_PZ
                ld      a, b
                jr      z, cm_load
                push    af              ; pv_scene: the sprites' second part first (loaded in DBUF, copied up)
                ld      a, PRS_CPV2
                call    cs_load
                ld      hl, DBUF
                ld      de, 0x8000
                ld      bc, DBUF_SIZE
                ldir
                pop     af
cm_load:        call    cs_load         ; the scene's sprites
                ld      hl, cut_init    ; the engine's state (SDLPoP reset_cutscene, load_intro's stars, the seed)
                ld      de, cut_vars
                ld      bc, cut_vars_end - cut_vars
                ldir
                ld      hl, cut_star0   ; the stars as load_intro left them (logic and screen)
                ld      de, cut_stcol
                ld      bc, 6
                ldir
                ld      hl, cut_star0
                ld      bc, 6
                ldir
                ld      hl, cut_kid     ; the characters and the drawing state: 0
                ld      de, cut_kid + 1
                ld      bc, cut_zero_end - cut_kid - 1
                ld      (hl), 0
                ldir
                ld      a, COM_PILLAR   ; the pillar is on the screen already: the room has it, pixel for pixel
                call    com_ptr         ; (tools/cutart.py checks it); it is drawn again only where a rectangle
                ld      (cut_shown + ID_PILLAR * SHOWN_SIZE), hl        ; around a moving object covers it
                ld      de, PILLAR_Y * 256 + PILLAR_COL
                ld      (cut_shown + ID_PILLAR * SHOWN_SIZE + 2), de
                dec     hl
                ld      a, (hl)         ; h
                dec     hl
                ld      c, (hl)         ; wb
                ld      (cut_shown + ID_PILLAR * SHOWN_SIZE + 4), bc
                ld      (cut_shown + ID_PILLAR * SHOWN_SIZE + 5), a
                ld      a, 0xff
                ld      (cr_pass), a
                xor     a
                ld      (cut_fresh), a
                ld      (k_armed), a
                ld      a, (cut_flags)
                ld      b, 1            ; (a level's scene: keys end it)
                bit     1, a
                jr      z, cs_k1
                ld      b, 2            ; disable_keys
cs_k1:          bit     2, a
                jr      z, cs_k2
                ld      b, 0            ; the title's keys
cs_k2:          ld      a, b
                ld      (cut_mode), a
; pal_on: group 1 with PLT0 black, PLT1-3 as they are: MZ 4 (EGA attribute 0) shows black, the flash turns it white
pal_on:         ld      a, 0x41
                out     (PORT_PAL), a
                xor     a
                out     (PORT_PAL), a
                ld      a, 0x15
                out     (PORT_PAL), a
                ld      a, 0x26
                out     (PORT_PAL), a
                ld      a, 0x37
                out     (PORT_PAL), a
                ret
; cs_load: A = entry: from the title (pv_scene: the player runs) as op_load; from the launcher (the interrupts stay off
; until irq_init: the game's PIO may still interrupt) a plain load
cs_load:        ld      b, a
                ld      a, (pv_on)
                or      a
                ld      a, b
                jp      nz, do_load
                jp      LN_PRS_LOAD
; p1_black: rows 192-199 of page 1 black (the game's offscreen surface has 192 rows: DOSBox, SDLPoP: §17)
p1_black:       ld      a, P1_PAGE
                ld      de, 192 * 160
                call    far_seek
                ld      de, 8 * 160
                xor     a
p1b_1:          out     (RD_DATA), a
                dec     de
                ld      b, a
                ld      a, d
                or      e
                ld      a, b
                jr      nz, p1b_1
                ret
; level -> the scene's PRS entry, script and flags (SDLPoP tbl_cutscenes; pres.asm cut_has lists the levels)
cut_levels:     db      2, PRS_C26
                dw      s_2_6
                db      0
                db      4, PRS_C4
                dw      s_4
                db      0
                db      6, PRS_C26
                dw      s_2_6
                db      0
                db      8, PRS_C8
                dw      s_8
                db      0
                db      9, PRS_C9
                dw      s_9
                db      0
                db      12, PRS_C12
                dw      s_12
                db      0
                db      0
cut_named:      db      0, PRS_CPV
                dw      s_pv
                db      CF_FULL + CF_TKEYS + CF_PZ
                db      0, PRS_CEXP
                dw      s_exp
                db      CF_FULL + CF_NOKEYS
                db      0, PRS_CEND
                dw      s_end
                db      CF_NOKEYS

; ---------------------------------------------------------------- the scenes (seg001.c)
; the character setups as the C code has them: Char := ..., play_seq
INIT_PRINCESS   macro                   ; init_princess
                db      OP_CSET, CR_CHARID, 5, OP_CSET, CR_X, 120, OP_CSET, CR_Y, 166, OP_CSET, CR_DIR, 0xff
                db      OP_CSEQ
                dw      CSEQ_94
                db      OP_CPLAY
                endm
INIT_VIZIER     macro                   ; init_vizier
                db      OP_CSET, CR_CHARID, 6, OP_CSET, CR_X, 198, OP_CSET, CR_Y, 166, OP_CSET, CR_DIR, 0xff
                db      OP_CSEQ
                dw      CSEQ_95
                db      OP_CPLAY
                endm
INIT_MOUSE_GO   macro                   ; init_mouse_go
                db      OP_CSET, CR_CHARID, CHARID_MOUSE, OP_CSET, CR_X, 199, OP_CSET, CR_Y, 167, OP_CSET, CR_DIR, 0xff
                db      OP_CSEQ
                dw      CSEQ_105
                db      OP_CPLAY
                endm
SEQ_SLOT        macro   slot, seq       ; seqtbl_offset_kid_char / seqtbl_offset_shad_char
                db      OP_CLOAD, slot, OP_CSEQ
                dw      seq
                db      OP_CSAVE, slot
                endm
s_2_6:          db      OP_SYNC, OP_CSND, 27, OP_CHG
                INIT_PRINCESS                                   ; init_princess_right
                db      OP_CSET, CR_DIR, 0, OP_CSAVE, 1
                db      OP_CFADEIN, OP_CFRAMES, 26, OP_CFADEOUT, OP_CEND
s_4:            db      OP_SYNC, OP_CSND, 27, OP_CHG
                INIT_PRINCESS                                   ; princess_lying
                db      OP_CSET, CR_X, 92, OP_CSET, CR_Y, 162, OP_CSEQ
                dw      CSEQ_103
                db      OP_CPLAY, OP_CSAVE, 1
                db      OP_CFADEIN, OP_CFRAMES, 26, OP_CFADEOUT, OP_CEND
s_8:            db      OP_SYNC, OP_CSND, 35, OP_CHG
                INIT_MOUSE_GO                                   ; init_mouse_cu8
                db      OP_CSET, CR_X, 144, OP_CSEQ
                dw      CSEQ_106
                db      OP_CPLAY, OP_CSAVE, 0
                INIT_PRINCESS                                   ; princess_crouching
                db      OP_CSET, CR_X, 131, OP_CSET, CR_Y, 169, OP_CSEQ
                dw      CSEQ_110
                db      OP_CPLAY, OP_CSAVE, 1
                db      OP_CFADEIN, OP_CFRAMES, 20
                SEQ_SLOT 0, CSEQ_107
                db      OP_CFRAMES, 20
                SEQ_SLOT 1, CSEQ_111
                db      OP_CFRAMES, 20
                db      OP_CLOAD, 0, OP_CSET, CR_FRAME, 0, OP_CSAVE, 0  ; Kid.frame = 0
                db      OP_CFADEOUT, OP_CEND
s_9:            db      OP_SYNC, OP_CSND, 35, OP_CHG
                INIT_PRINCESS                                   ; princess_stand (init_princess_right, x 144, y 169)
                db      OP_CSET, CR_DIR, 0, OP_CSET, CR_X, 144, OP_CSET, CR_Y, 169, OP_CSEQ
                dw      CSEQ_94
                db      OP_CPLAY, OP_CSAVE, 1
                db      OP_CFADEIN
                INIT_MOUSE_GO
                db      OP_CSAVE, 0, OP_CFRAMES, 5
                SEQ_SLOT 1, CSEQ_112
                db      OP_CFRAMES, 9
                SEQ_SLOT 0, CSEQ_114
                db      OP_CFRAMES, 58
                db      OP_CFADEOUT, OP_CEND
s_12:           db      OP_CIF6                                 ; hourglass_frame() >= 6, else cutscene_2_6
                dw      s_2_6
                db      OP_SYNC, OP_CHG
                INIT_PRINCESS                                   ; init_princess_x156
                db      OP_CSET, CR_X, 156, OP_CSAVE, 1, OP_CSND, 40
                db      OP_CFADEIN, OP_CFRAMES, 2
                SEQ_SLOT 1, CSEQ_98
                db      OP_CFRAMES, 24, OP_CFADEOUT, OP_CEND
; pv_scene (load_intro waits for music 55 first: g started it 80 + 600 + 20 ticks ago; the loads ran meanwhile)
s_pv:           db      OP_WAIT
                dw      CUT_L55 - 700
                INIT_PRINCESS
                db      OP_CSAVE, 1, OP_CFADEIN
                INIT_VIZIER
                db      OP_CSAVE, 0, OP_CFRAMES, 2, OP_CSND, 50, OP_CUNTIL
                db      OP_CFT, 8, OP_CFRAMES, 5, OP_CSND, 4, OP_CUNTIL
                db      OP_CSND, 51, OP_CFRAMES, 3
                SEQ_SLOT 1, CSEQ_98
                db      OP_CFRAMES, 5
                SEQ_SLOT 0, CSEQ_96
                db      OP_CFRAMES, 6, OP_CSND, 53
                SEQ_SLOT 0, CSEQ_97
                db      OP_CFRAMES, 4, OP_CFRAMES, 18
                SEQ_SLOT 0, CSEQ_96
                db      OP_CFRAMES, 30
                SEQ_SLOT 0, CSEQ_97
                db      OP_CFRAMES, 35
                SEQ_SLOT 0, CSEQ_102
                db      OP_CFT, 7, OP_CFRAMES, 1
                SEQ_SLOT 1, CSEQ_99
                db      OP_CFRAMES, 17, OP_CHGN, 1, OP_CFLASH, 5, 15, OP_CUNTIL
                SEQ_SLOT 0, CSEQ_100
                db      OP_CSAND, 0, OP_CFRAMES, 6, OP_CSND, 52, OP_CFRAMES, 24, OP_CHGN, 2, OP_CFRAMES, 9
                SEQ_SLOT 1, CSEQ_113
                db      OP_CFRAMES, 28, OP_CFADEOUT, OP_CRET
; time_expired, then the title
s_exp:          db      OP_SYNC, OP_CHGN, 7, OP_CSND, 36, OP_CFADEIN, OP_CFRAMES, 2, OP_CFRAMES, 100, OP_CFADEOUT, OP_WAITM
                db      OP_EXPEND
; end_sequence_anim, then pres.asm's ending_steps
s_end:          db      OP_CSHOW, OP_SYNC, OP_CSND, 26
                INIT_PRINCESS                                   ; init_ending_princess
                db      OP_CSET, CR_X, 136, OP_CSET, CR_Y, 164, OP_CSEQ
                dw      CSEQ_109
                db      OP_CPLAY, OP_CSAVE, 1
                db      OP_CSET, CR_CHARID, 0, OP_CSET, CR_X, 198, OP_CSET, CR_Y, 164, OP_CSET, CR_DIR, 0xff   ; init_ending_kid
                db      OP_CSEQ
                dw      CSEQ_1
                db      OP_CPLAY, OP_CSAVE, 0, OP_CFRAMES, 8
                SEQ_SLOT 1, CSEQ_108
                db      OP_CFRAMES, 5
                SEQ_SLOT 0, CSEQ_13
                db      OP_CFRAMES, 2
                db      OP_CLOAD, 0, OP_CSET, CR_FRAME, 0, OP_CSAVE, 0  ; Kid.frame = 0
                db      OP_CFRAMES, 39
                INIT_MOUSE_GO                                   ; init_mouse_1
                db      OP_CSET, CR_X, 197, OP_CSET, CR_Y, 164, OP_CSAVE, 0, OP_CFRAMES, 9
                SEQ_SLOT 0, CSEQ_101
                db      OP_CFRAMES, 41, OP_CFADEOUT, OP_WAITM, OP_CRET

; ---------------------------------------------------------------- the script operations
op_csnd:        call    op_byte         ; play_sound(id)
                jp      play_sound
op_chg:         call    hg_frame        ; set_hourglass_state(hourglass_frame())
                ld      (cut_hg), a
                xor     a
                ld      (cut_sand), a
                ret
op_chgn:        call    op_byte         ; hourglass_state = n
                ld      (cut_hg), a
                ret
op_csand:       call    op_byte         ; hourglass_sandflow = v
                ld      (cut_sand), a
                ret
op_cft:         call    op_byte         ; cutscene_frame_time = n
                ld      (cut_ft), a
                ret
op_cflash:      call    op_byte         ; flash_time = n, flash_color = c
                ld      (cut_flash), a
                call    op_byte
                ld      (cut_flcol), a
                ret
op_cload:       call    op_byte         ; Char = slot (loadkid / loadshad)
                call    cut_rec
                ld      de, cut_char
cl_cp:          ld      bc, CR_SIZE
                ldir
                ret
op_csave:       call    op_byte         ; slot = Char (savekid / saveshad)
                call    cut_rec
                ex      de, hl
                ld      hl, cut_char
                jr      cl_cp
op_cset:        call    op_byte         ; Char.field = value
                ld      e, a
                ld      d, 0
                ld      hl, cut_char
                add     hl, de
                push    hl
                call    op_byte
                pop     hl
                ld      (hl), a
                ret
op_cseq:        call    op_word         ; seqtbl_offset_char
                ld      (cut_char + CR_SEQ), de
                ret
op_cplay:       jp      play_seq
op_cif6:        call    op_word         ; if hourglass_frame() < 6: continue at the word
                call    hg_frame
                cp      6
                ret     nc
                ld      (t_pc), de
                ret
op_cframes:     call    op_byte         ; proc_cutscene_frame(n)
                ld      (cut_wait), a
ocf_1:          call    cut_frame
                ld      hl, cut_wait
                dec     (hl)
                jr      nz, ocf_1
                ret
op_cfadein:     call    cf_fadefr       ; fade_in_1: the frame, its objects composed row by row with the passes
                call    cut_dirty
                xor     a
                ld      (t_col), a
ocfi_1:         call    t_wait
                ld      a, (t_col)
                ld      e, a
                ld      d, 40
                ld      bc, 40 * 256 + 0
                ld      a, 5
                call    copy_rows
                ld      a, (t_col)
                ld      (cr_pass), a
                call    cut_paint
tcf_pass:       ld      de, 4           ; (tests/m7_cut.py: pass t_col is on the screen)
                call    t_adv
                ld      hl, t_col
                inc     (hl)
                ld      a, (hl)
                cp      5
                jr      nz, ocfi_1
                ld      a, 0xff
                ld      (cr_pass), a
                ld      a, 1
                ld      (cut_fresh), a
                ret
op_cfadeout:    call    cf_fadefr       ; fade_out_1: the frame (nothing of it shows), then the passes
                jp      op_fadeout
; cf_fadefr: the fade's frame: proc_cutscene_frame(1) without its drawing; the fade's ticks instead of the frame's
cf_fadefr:      ld      a, 1
                ld      (cut_wait), a
                xor     a
                ld      (cut_late), a
                call    cf_logic
                ld      bc, FADE_TICKS
                jp      cf_left
op_cshow:       ld      bc, 40 * 256 + 0        ; the room at once
                ld      de, 200 * 256 + 0
                ld      a, 1
                jp      copy_rows
op_expend:
tc_exptitle:    jp      title           ; (tests/m7_story.py: time_expired and its music are over)
op_cuntil:      ld      a, 1            ; do proc_cutscene_frame(1) while (check_sound_playing())
                ld      (cut_wait), a
                call    cut_frame
                ld      hl, (cut_left)
                ld      a, h
                or      l
                jr      nz, op_cuntil
                ret
; op_cend: the scene is over: play_level waits while the music plays (the ticks model: until its end tick), then the
; level starts (the handoff as the game sent it: ACT_PLAY, the same level, time and hit points)
op_cend:        call    op_waitm
tc_end:         xor     a               ; (tests/m7_cut.py: the scene and its music are over)
                ld      (cut_mode), a
                jp      p_cutplay
; cut_abort: a key during the scene (keys): stop_sounds, the screen black, the level at once
cut_abort:      ld      sp, P_STACK
                xor     a
                ld      (cut_mode), a
                call    snd_halt
                call    cls
tc_abort:       jp      p_cutplay       ; (p_go: the palette as it was)

; cut_rec: A = slot (0 kid, 1 shad) -> HL = its record
cut_rec:        ld      hl, cut_kid
                or      a
                ret     z
                ld      hl, cut_shad
                ret
; hg_frame: A = hourglass_frame(): 6 - the index of the first time_bound (6, 17, 33, 65) above rem_min
hg_frame:       ld      a, (ho + HO_REM_MIN)
                ld      c, a
                ld      hl, hg_bound
                ld      b, 6
hgf_1:          ld      a, c
                cp      (hl)
                jr      c, hgf_2
                inc     hl
                dec     b
                ld      a, b
                cp      2
                jr      nz, hgf_1
hgf_2:          ld      a, b
                ret
hg_bound:       db      6, 17, 33, 65

; ---------------------------------------------------------------- sounds (seg000.c play_sound / play_next_sound)
; play_sound: A = id: queued (next_sound) unless a queued one has a higher priority (lower value); ids without a
; resource are ignored
play_sound:     ld      b, a
                ld      e, a
                ld      d, 0
                ld      hl, cut_prio
                add     hl, de
                ld      a, (hl)
                cp      0xff
                ret     z
                ld      c, a
                ld      a, (cut_next)
                cp      0xff
                jr      z, psd_set
                ld      l, a
                ld      h, 0
                ld      de, cut_prio
                add     hl, de
                ld      a, (hl)
                cp      c
                ret     c               ; (the queued one wins: its priority value is lower)
psd_set:        ld      a, b
                ld      (cut_next), a
                ret
; play_next_sound (proc_cutscene_frame calls it only when nothing plays): the queued sound starts: the ticks model's
; length (cut_left, the music's end tick cut_musend) and the PSG player
play_next_sound:
                ld      a, (cut_next)
                cp      0xff
                ret     z
                ld      (cut_cur), a
                ld      l, a
                ld      h, 0
                add     hl, hl
                ld      de, cut_len60
                add     hl, de
                ld      e, (hl)
                inc     hl
                ld      d, (hl)
                ld      (cut_left), de
                ld      hl, (ct_tick)
                add     hl, de
                ld      (mus_end), hl
                ld      a, 0xff
                ld      (cut_next), a
                ; (M7 step 11) a cue whose id has no stream in the bank starts nothing: the piece playing goes on
                ; (pv_scene's 4, 51, 53, 52 under Jaffar's piece: tools/presbank.py bank B); the ticks model runs as before
                ld      a, (cut_cur)
                add     a, a
                add     a, a
                ld      e, a
                ld      d, PSG_BANK_ADDR / 256
                ld      a, PSG_BANK_PAGE
                call    far_seek        ; (the index entry: address, length)
                in      a, (RD_DATA)
                in      a, (RD_DATA)
                in      a, (RD_DATA)
                ld      c, a
                in      a, (RD_DATA)
                or      c
                ret     z
pns_start:      ld      a, (cut_cur)    ; (tests: the cue starts its stream)
                jp      snd_start

; ---------------------------------------------------------------- play_seq (seg006.c) on cut_char
play_seq:       ld      hl, (cut_char + CR_SEQ)
pq_seek:        push    hl
                ld      de, LOGIC_SEQ
                add     hl, de
                ex      de, hl
                ld      a, LOGIC_PAGE
                call    far_seek
                pop     hl
pq_next:        in      a, (RD_DATA)
                inc     hl
                cp      0xf1
                jr      c, pq_frame
                cp      0xfb            ; SEQ_DX
                jr      nz, pq_1
                in      a, (RD_DATA)
                inc     hl
                call    dx_forward
                ld      (cut_char + CR_X), a
                jr      pq_next
pq_1:           cp      0xfa            ; SEQ_DY
                jr      nz, pq_2
                in      a, (RD_DATA)
                inc     hl
                ld      c, a
                ld      a, (cut_char + CR_Y)
                add     a, c
                ld      (cut_char + CR_Y), a
                jr      pq_next
pq_2:           cp      0xfe            ; SEQ_FLIP
                jr      nz, pq_3
                ld      a, (cut_char + CR_DIR)
                cpl
                ld      (cut_char + CR_DIR), a
                jr      pq_next
pq_3:           cp      0xff            ; SEQ_JMP
                jr      nz, pq_4
                in      a, (RD_DATA)
                ld      l, a
                in      a, (RD_DATA)
                ld      h, a
                jr      pq_seek
pq_4:           cp      0xf7            ; SEQ_JMP_IF_FEATHER (no feather fall here), SEQ_SET_FALL: 2 bytes
                jr      z, pq_skip2
                cp      0xf8
                jr      z, pq_skip2
                cp      0xf9            ; SEQ_ACTION, SEQ_GET_ITEM: 1 byte
                jr      z, pq_skip1
                cp      0xf3
                jr      z, pq_skip1
                cp      0xf2            ; SEQ_SOUND
                jr      nz, pq_next     ; (UP, DOWN, KNOCK_UP/DOWN, END_LEVEL, DIE: nothing a scene shows)
                in      a, (RD_DATA)
                inc     hl
                dec     a
                jr      nz, pq_next     ; (only the footstep occurs in the scenes' sequences: tests/m7_story.py's kid)
                push    hl
                ld      a, 23
                call    play_sound
                pop     hl              ; (play_sound leaves the RAM disk alone: the stream goes on)
                jr      pq_next
pq_skip2:       in      a, (RD_DATA)
                inc     hl
pq_skip1:       in      a, (RD_DATA)
                inc     hl
                jr      pq_next
pq_frame:       ld      (cut_char + CR_FRAME), a
                ld      (cut_char + CR_SEQ), hl
                ret
; dx_forward: A = dx -> A = Char.x + dx forward (char_dx_forward: the direction's sign), a byte; dx_fwd: C = x,
; B = direction
dx_forward:     push    af
                ld      a, (cut_char + CR_X)
                ld      c, a
                ld      a, (cut_char + CR_DIR)
                ld      b, a
                pop     af
dx_fwd:         bit     7, b
                jr      z, dxf_1
                neg
dxf_1:          add     a, c
                ret

; ---------------------------------------------------------------- prandom (seg009.c; the generator of src/m3/room.asm)
; prandom: A = max -> A = (seed >> 16) % (max + 1), seed = seed * 214013 + 2531011; max 255: the byte
prandom:        ld      (pr_max_c), a
                ld      hl, (cut_seed)
                ld      de, (cut_seed + 2)
                add     hl, hl
                ex      de, hl
                adc     hl, hl
                ex      de, hl          ; 2S
                ld      bc, (cut_seed)
                add     hl, bc
                ex      de, hl
                ld      bc, (cut_seed + 2)
                adc     hl, bc
                ex      de, hl          ; 3S
                ld      (pr_t), hl
                ld      (pr_t + 2), de
                ld      hl, (cut_seed)
                ld      de, (cut_seed + 2)
                ld      d, e            ; << 8
                ld      e, h
                ld      h, l
                ld      l, 0
                add     hl, hl
                rl      e
                rl      d
                add     hl, hl
                rl      e
                rl      d               ; X = S << 10
                ld      (pr_a), hl
                ld      (pr_a + 2), de
                ld      b, 4
pr_s4:          add     hl, hl          ; X << 4
                rl      e
                rl      d
                djnz    pr_s4
                ld      bc, (pr_a)
                add     hl, bc
                ex      de, hl
                ld      bc, (pr_a + 2)
                adc     hl, bc
                ex      de, hl          ; X * 17
                ld      bc, (pr_t)
                or      a
                sbc     hl, bc
                ex      de, hl
                ld      bc, (pr_t + 2)
                sbc     hl, bc          ; - 3S (HL = the high word)
                ld      bc, (pr_t)
                add     hl, bc          ; high += low16(3S)
                ex      de, hl
                ld      bc, 0x9ec3      ; + 2531011
                add     hl, bc
                ex      de, hl
                ld      bc, 0x0026
                adc     hl, bc
                ex      de, hl
                ld      (cut_seed), hl
                ld      (cut_seed + 2), de
                ld      a, (pr_max_c)
                inc     a
                jr      nz, pr_mod
                ld      a, e            ; (max 255: the low byte of the high word)
                ret
pr_mod:         ld      c, a
                ex      de, hl
                xor     a
                ld      b, 16
pr_d:           add     hl, hl
                rla
                cp      c
                jr      c, pr_d2
                sub     c
pr_d2:          djnz    pr_d
                ret

; ---------------------------------------------------------------- proc_cutscene_frame: one frame
cut_frame:
tc_fstart:      ld      hl, (FRAMES)    ; late? (then the frame's drawing is skipped) (tests/m7_cut.py: the frame starts)
                ld      de, (t_target)
                or      a
                sbc     hl, de
                bit     7, h
                ld      a, 0
                jr      nz, cf_late     ; (before the target: on time)
                ld      a, h
                or      a
                ld      a, 1
                jr      nz, cf_late
                ld      a, l
                cp      SKIP_LATE
                ld      a, 0
                jr      c, cf_late
                inc     a
cf_late:        ld      (cut_late), a
                ld      hl, cut_fresh   ; (the first frame after the fade-in always shows: its passes take ~4 frames each
                bit     0, (hl)         ; against the 3.33 of their ticks, so it starts ~4 frames late)
                jr      z, cf_l0
                ld      (hl), 0
                xor     a
                ld      (cut_late), a
cf_l0:          call    cf_logic
                ld      a, (cut_late)
                or      a
                jr      nz, cf_skip
                call    cut_dirty
                call    cut_paint
tc_drawn:       ld      hl, cut_ndrawn  ; (tests/m7_cut.py: VRAM = the frame)
                inc     (hl)
cf_skip:        ld      a, (cut_ft)     ; the frame's ticks: the sound model, the clock
                ld      c, a
                ld      b, 0
                call    cf_left
                ld      a, (cut_flshow) ; the flash: the background white for 2 ticks (SDLPoP do_flash: timer_2)
                or      a
                jr      z, cf_clock
                ld      a, (cut_late)
                or      a
                jr      nz, cf_clock
                ld      a, (cut_flcol)
                and     15
                out     (PORT_PAL), a   ; PLT0 = the colour
tc_flash:       ld      de, 2           ; (tests/m7_story.py: the flash is on)
                call    t_adv
                call    t_wait
                xor     a
                out     (PORT_PAL), a   ; PLT0 = black
                ld      a, (cut_ft)
                sub     2
                jr      cf_clk1
cf_clock:       ld      a, (cut_ft)
cf_clk1:        ld      e, a
                ld      d, 0
                call    t_adv
                jp      t_wait
; cf_left: BC = ticks off the sound model
cf_left:        ld      hl, (cut_left)
                or      a
                sbc     hl, bc
                jr      nc, cfl_1
                ld      hl, 0
cfl_1:          ld      (cut_left), hl
                ret
; cf_logic: the frame's logic: play_both_seq, the tables, the star, the flash's count, the sound
cf_logic:       ld      a, 0            ; play_both_seq
                call    cf_seq
                ld      a, 1
                call    cf_seq
                call    cut_objects     ; draw_princess_room_bg's tables: the torches, the hourglass
                ld      a, 0xff         ; draw_proom_drects: on odd frames a star
                ld      (cut_star), a
                ld      a, (cut_wait)
                and     1
                jr      z, cf_nostar
                ld      a, 5
                call    prandom
                ld      (cut_star), a
                ld      e, a
                ld      d, 0
                ld      hl, cut_stcol
                add     hl, de
                ld      a, (hl)
                inc     a
                cp      5
                jr      c, cf_st1
                xor     a
cf_st1:         ld      (hl), a
cf_nostar:      ld      a, (cut_flash)  ; the flash: shown this frame, then one less
                ld      (cut_flshow), a
                or      a
                jr      z, cf_nofl
                dec     a
                ld      (cut_flash), a
cf_nofl:        ld      hl, (cut_left)  ; if (!check_sound_playing()) play_next_sound()
                ld      a, h
                or      l
                call    z, play_next_sound
tc_frame:       ld      hl, cut_n       ; (tests/m7_cut.py: the frame's state is complete: the 'C' line)
                inc     (hl)
                ret
; cf_seq: A = slot: if its frame is not 0, its sequence plays one frame (play_kid_seq / play_opp_seq)
cf_seq:         push    af
                call    cut_rec
                ld      a, (hl)
                or      a
                jr      z, cfs_x
                ld      de, cut_char
                ld      bc, CR_SIZE
                ldir
                call    play_seq
                pop     af
                call    cut_rec
                ex      de, hl
                ld      hl, cut_char
                ld      bc, CR_SIZE
                ldir
                ret
cfs_x:          pop     af
                ret

; ---------------------------------------------------------------- the frame's objects (draw_princess_room_bg)
; cut_objects: cut_objs in draw order: the torches (backtable: torch 1, torch 0), the characters (midtable,
; draw_objtable_items_at_tile: by y, the shad slot first at equal y), the hourglass (midtable), the pillar and the
; sand (foretable)
cut_objects:    xor     a
                ld      (cut_nobj), a
                ld      ix, cut_objs
                ld      b, 2            ; princess_room_torch: for (which = 2; which--; ) which_torch = !which_torch
co_torch:       push    bc
                ld      a, (cut_which)
                xor     1
                ld      (cut_which), a
                ld      e, a
                ld      d, 0
                ld      hl, cut_torch
                add     hl, de
                push    hl
                push    de
                ld      c, (hl)         ; get_torch_frame(curr)
                push    bc
                ld      a, 255
                call    prandom
                pop     bc
                cp      c
                jr      z, cot_inc
                cp      9
                jr      c, cot_set
                ld      a, c
cot_inc:        inc     a
                cp      9
                jr      c, cot_set
                xor     a
cot_set:        pop     de              ; E = which
                pop     hl
                ld      (hl), a
                ld      c, a            ; the flame: cut_com[9 which + frame]
                ld      a, e
                add     a, a
                add     a, a
                add     a, a
                add     a, e
                add     a, c
                add     a, COM_TORCH
                push    de
                call    com_ptr
                pop     de
                ld      a, e            ; column 11 / 26 (x 93 / 211)
                or      a
                ld      c, 11
                jr      z, cot_c
                ld      c, 26
cot_c:          ld      b, TORCH_Y
                ld      a, e
                add     a, ID_TORCH
                call    add_obj
                pop     bc
                djnz    co_torch
                ld      a, 0            ; the characters
                call    char_obj
                ld      (co_k), hl
                ld      (co_ky), de
                ld      a, 1
                call    char_obj
                ld      (co_s), hl
                ld      (co_sy), de
                ld      hl, (co_ky)     ; the kid first only when its y is lower (the bubble sort's order)
                ld      de, (co_sy)
                or      a
                sbc     hl, de
                jr      nc, co_sfirst
                call    co_kid
                call    co_shad
                jr      co_glass
co_sfirst:      call    co_shad
                call    co_kid
co_glass:       ld      a, (cut_sand)   ; draw_hourglass
                bit     7, a
                jr      nz, cog_glass
                inc     a               ; hourglass_sandflow = (hourglass_sandflow + 1) % 3
                cp      3
                jr      c, cog_1
                xor     a
cog_1:          ld      (cut_sand), a
                ld      a, (cut_hg)
                cp      7
                jr      nc, co_pillar   ; (state 7: neither the sand nor the glass)
cog_glass:      ld      a, (cut_hg)
                or      a
                jr      z, co_pillar
                add     a, COM_GLASS
                call    com_ptr
                ld      c, GLASS_COL
                ld      b, GLASS_Y
                ld      a, ID_GLASS
                call    add_obj
co_pillar:      ld      a, COM_PILLAR
                call    com_ptr
                ld      c, PILLAR_COL
                ld      b, PILLAR_Y
                ld      a, ID_PILLAR
                call    add_obj
                ld      a, (cut_sand)   ; the sand (after the pillar: added to the foretable later)
                bit     7, a
                ret     nz
                ld      a, (cut_hg)
                cp      7
                ret     nc
                ld      a, (cut_sand)
                add     a, COM_SAND
                call    com_ptr
                ld      c, SAND_COL
                ld      b, SAND_Y
                ld      a, ID_SAND
                jp      add_obj
co_kid:         ld      hl, (co_k)
                ld      a, h
                or      l
                ret     z
                ld      bc, (co_kcb)
                xor     a
                call    add_obj
                ld      hl, (co_ent)
                jr      co_setk
co_shad:        ld      hl, (co_s)
                ld      a, h
                or      l
                ret     z
                ld      bc, (co_scb)
                ld      a, 1
                call    add_obj
                ld      hl, (co_ent + 2)
co_setk:        ld      (ix - 2), l     ; (a character: its cut_spr entry identifies the image)
                ld      (ix - 1), h
                ret
; com_ptr: A = cut_com index -> HL = the sprite
com_ptr:        ld      l, a
                ld      h, 0
                add     hl, hl
                ld      de, cut_com
                add     hl, de
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a
                ret
; add_obj: HL = sprite, C = byte column, B = ytop, A = identity: the next entry of cut_objs (IX)
add_obj:        ld      (ix + 0), l
                ld      (ix + 1), h
                ld      (ix + 6), l
                ld      (ix + 7), h
                ld      (ix + 2), c
                ld      (ix + 3), b
                ld      (ix + 4), a
                ld      de, OBJ_SIZE
                add     ix, de
                ld      hl, cut_nobj
                inc     (hl)
                ret
; char_obj: A = slot -> HL = its sprite (0: not drawn), DE = obj_y (SDLPoP's sort key; 0xFFFF when not drawn), and
; co_kcb / co_scb = byte column, ytop (load_frame, load_frame_to_obj, calc_screen_x_coord, the flip)
char_obj:       ld      (co_slot), a
                call    cut_rec
                push    hl
                pop     iy
                ld      hl, 0
                ld      de, 0xffff
                ld      a, (iy + CR_FRAME)
                or      a
                ret     z
                ld      l, a            ; the frame's entry: 5 bytes (image, sword, dx, dy, flags)
                ld      h, 0
                ld      c, l
                ld      b, h
                add     hl, hl
                add     hl, hl
                add     hl, bc
                ld      a, (iy + CR_CHARID)
                cp      CHARID_KID
                jr      z, chf_kid
                cp      CHARID_MOUSE
                jr      z, chf_kid
                ld      de, frame_tbl_cuts
                add     hl, de
                ld      de, cut_fr
                ld      bc, 5
                ldir
                jr      chf_got
chf_kid:        ld      de, LOGIC_KIDFR ; (the kid's table in logic.bin)
                add     hl, de
                ex      de, hl
                ld      a, LOGIC_PAGE
                call    far_seek
                ld      hl, cut_fr
                ld      b, 5
                ld      c, RD_DATA
                inir
chf_got:        ld      a, (cut_fr)     ; image 255: nothing
                cp      255
                ld      hl, 0
                ld      de, 0xffff
                ret     z
                ld      c, (iy + CR_X)  ; obj_x = (char_dx_forward(dx) << 1) - 116, + 1 when the frame's odd flag and
                ld      b, (iy + CR_DIR)        ; the direction agree
                ld      a, (cut_fr + 2)
                call    dx_fwd
                ld      l, a
                ld      h, 0
                add     hl, hl
                ld      de, -116
                add     hl, de
                ld      a, (cut_fr + 4)
                xor     (iy + CR_DIR)
                jp      m, chf_even
                inc     hl
chf_even:       ld      a, h            ; screen x = obj_x * 320 / 280, toward 0
                push    af
                bit     7, h
                jr      z, chf_pos
                call    neg_hl
chf_pos:        add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      c, 7
                call    div16_8
                pop     af
                bit     7, a
                call    nz, neg_hl
                ld      (co_x), hl
                ld      a, (cut_fr + 3) ; obj_y = dy + y
                ld      e, a
                ld      d, 0
                bit     7, a
                jr      z, chf_dy
                dec     d
chf_dy:         ld      l, (iy + CR_Y)
                ld      h, 0
                add     hl, de
                ld      (co_y), hl
                ld      a, (cut_fr + 1) ; the key: chtab (2 + sword >> 6) | 0x80 when flipped (facing right), image
                rlca
                rlca
                and     3
                add     a, 2
                ld      c, a
                ld      a, (iy + CR_DIR)
                or      a
                jr      nz, chf_left
                set     7, c
chf_left:       ld      a, (cut_fr)
                ld      b, a
                ld      (co_key), bc
                ld      e, 0xff         ; any shift: the image's width
                call    spr_find
                jp      nz, chf_none
                ld      e, (hl)         ; w
                ld      hl, (co_x)
                ld      a, (co_key)
                bit     7, a
                jr      z, chf_nofl
                ld      d, 0            ; flipped: x - w
                or      a
                sbc     hl, de
chf_nofl:       bit     7, h            ; off the screen (the mouse runs out at the right, its x wraps): not
                jp      nz, chf_none    ; drawn (tools/cutart.py: no image is cut at the left edge)
                ld      de, 320
                or      a
                sbc     hl, de
                add     hl, de
                jp      nc, chf_none
                ld      a, l
                and     7
                ld      e, a            ; the shift
                ld      (co_x), hl
                ld      bc, (co_key)
                call    spr_find
                jp      nz, chf_none
                push    hl              ; the entry + 2
                ld      de, (co_x)      ; column = x >> 3
                srl     d
                rr      e
                srl     d
                rr      e
                srl     d
                rr      e
                inc     hl
                inc     hl
                inc     hl
                inc     hl
                inc     hl
                ld      a, (co_y)       ; ytop = obj_y - h + 1 (the entry's h)
                sub     (hl)
                inc     a
                ld      d, a
                ld      a, (co_slot)
                or      a
                jr      nz, chf_s
                ld      (co_kcb), de
                jr      chf_r
chf_s:          ld      (co_scb), de
chf_r:          pop     hl
                dec     hl              ; the entry
                dec     hl
                ld      a, (co_slot)    ; the key for the dirty rectangles
                add     a, a
                ld      e, a
                ld      d, 0
                push    hl
                ld      hl, co_ent
                add     hl, de
                pop     de
                ld      (hl), e
                inc     hl
                ld      (hl), d
                ld      a, (cut_flags)  ; the sprite: its slot's buffer (filled when drawn), or its place
                and     CF_PZ
                jr      z, chf_raw
                ld      a, (co_slot)
                or      a
                ld      hl, SLOTBUF0 + 2
                jr      z, chf_ret
                ld      hl, SLOTBUF1 + 2
                jr      chf_ret
chf_raw:        ld      hl, 4
                add     hl, de
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a
chf_ret:        ld      de, (co_y)
                ret
chf_none:       ld      hl, 0           ; (no such sprite: tools/cutart.py missed it; tests/m7_cut.py would see it)
                ld      de, 0xffff
                ret
; spr_find: C = key 0, B = key 1 (image), E = shift (0xFF: any) -> Z and HL = the entry + 2 (w, shift, address, wb, h).
; The slot's last entry first (a character mostly keeps its image), then the table
spr_find:       ld      a, (co_slot)
                add     a, a
                ld      l, a
                ld      h, 0
                push    de
                ld      de, co_last
                add     hl, de
                pop     de
                push    hl              ; the slot's co_last
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a
                or      h
                jr      z, sf_tab
                call    sf_match
                jr      z, sf_got
sf_tab:         ld      hl, CUT_SPR
sf_1:           ld      a, (hl)
                cp      0xff
                jr      z, sf_no
                call    sf_match
                jr      z, sf_got
                ld      a, l
                add     a, 8
                ld      l, a
                jr      nc, sf_1
                inc     h
                jr      sf_1
sf_got:         pop     de              ; the entry is the slot's last now
                ex      de, hl
                ld      (hl), e
                inc     hl
                ld      (hl), d
                ex      de, hl
                inc     hl
                inc     hl
                xor     a               ; Z
                ret
sf_no:          pop     hl
                or      a               ; NZ (A = 0xFF)
                ret
; sf_match: HL = an entry: Z when it has the key (and the shift); keeps HL, BC, DE
sf_match:       ld      a, (hl)
                cp      c
                ret     nz
                inc     hl
                ld      a, (hl)
                dec     hl
                cp      b
                ret     nz
                ld      a, e
                cp      0xff
                ret     z
                inc     hl
                inc     hl
                inc     hl
                ld      a, (hl)
                dec     hl
                dec     hl
                dec     hl
                cp      e
                ret
neg_hl:         xor     a
                sub     l
                ld      l, a
                sbc     a, a
                sub     h
                ld      h, a
                ret
; div16_8: HL / C -> HL (A = the remainder)
div16_8:        xor     a
                ld      b, 16
d168_1:         add     hl, hl
                rla
                cp      c
                jr      c, d168_2
                sub     c
                inc     l
d168_2:         djnz    d168_1
                ret

; ---------------------------------------------------------------- the drawing
; cut_dirty: the dirty rectangles of this frame (pv_scene: a character's new image unpacked first)
cut_dirty:      ld      a, (cut_flags)
                and     CF_PZ
                call    nz, slots_fill
                xor     a
                ld      (cut_nd), a
                ld      ix, cut_shown   ; per identity: the object drawn last (key, column, ytop, wb, h) against now
                ld      c, 0
cd_id:          push    bc
                call    find_obj        ; HL = the entry now (0 none)
                ld      a, h
                or      l
                jr      z, cd_none
                push    hl
                ld      de, 6
                add     hl, de
                ld      e, (hl)
                inc     hl
                ld      d, (hl)         ; DE = the key
                pop     hl
                ld      a, (ix + 0)
                cp      e
                jr      nz, cd_chg
                ld      a, (ix + 1)
                cp      d
                jr      nz, cd_chg
                inc     hl
                inc     hl
                ld      a, (ix + 2)
                cp      (hl)
                dec     hl
                dec     hl
                jr      nz, cd_chg
                inc     hl
                inc     hl
                inc     hl
                ld      a, (ix + 3)
                cp      (hl)
                dec     hl
                dec     hl
                dec     hl
                jr      z, cd_next
cd_chg:         push    hl
                push    de
                call    shown_box       ; the old box (if any)
                pop     de
                pop     hl
                ld      (ix + 0), e
                ld      (ix + 1), d
                ld      e, (hl)
                inc     hl
                ld      d, (hl)         ; DE = the sprite
                inc     hl
                ld      a, (hl)
                ld      (ix + 2), a
                inc     hl
                ld      a, (hl)
                ld      (ix + 3), a
                ex      de, hl
                dec     hl
                ld      a, (hl)
                ld      (ix + 5), a     ; h
                dec     hl
                ld      a, (hl)
                ld      (ix + 4), a     ; wb
                call    shown_box       ; the new box
                jr      cd_next
cd_none:        call    shown_box       ; gone: its old box
                ld      (ix + 0), 0
                ld      (ix + 1), 0
cd_next:        ld      de, SHOWN_SIZE
                add     ix, de
                pop     bc
                inc     c
                ld      a, c
                cp      N_IDS
                jr      nz, cd_id
                ld      b, 6            ; the stars whose colour changed: their pixel
                ld      hl, cut_stcol
                ld      de, cut_stshow
                ld      ix, cut_stars
cd_st:          ld      a, (de)
                cp      (hl)
                jr      z, cd_st1
                ld      a, (hl)
                ld      (de), a
                push    bc
                push    de
                push    hl
                ld      a, (ix + 0)     ; x
                rrca
                rrca
                rrca
                and 31
                ld      c, a
                ld      b, c
                ld      e, (ix + 1)     ; y
                ld      d, e
                call    add_rect
                pop     hl
                pop     de
                pop     bc
cd_st1:         inc     hl
                inc     de
                inc     ix
                inc     ix
                djnz    cd_st
                jp      merge_rects
; slots_fill: pv_scene: every character whose image changed: its PZ block into its slot's buffer
slots_fill:     ld      c, 0
                call    slf_1
                ld      c, 1
slf_1:          call    find_obj        ; (C kept)
                ld      a, h
                or      l
                ret     z
                ld      de, 6
                add     hl, de
                ld      e, (hl)
                inc     hl
                ld      d, (hl)         ; DE = its cut_spr entry
                ld      a, c
                add     a, a
                ld      l, a
                ld      h, 0
                push    bc
                ld      bc, slot_cur
                add     hl, bc
                pop     bc
                ld      a, (hl)
                cp      e
                jr      nz, slf_2
                inc     hl
                ld      a, (hl)
                dec     hl
                cp      d
                ret     z
slf_2:          ld      (hl), e
                inc     hl
                ld      (hl), d
                ld      hl, 4
                add     hl, de
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a            ; HL = the PZ block
                ld      a, c
                or      a
                ld      de, SLOTBUF0
                jr      z, slf_3
                ld      de, SLOTBUF1
slf_3:          push    bc
tc_unpz:        call    unpz
                pop     bc
                ret
; cut_paint: the rectangles composed row by row to VRAM (cr_pass 0..4: only the rows y mod 5 = cr_pass)
cut_paint:      ld      a, (cut_nd)     ; every rectangle, row by row
                or      a
                ret     z
                ld      b, a
                ld      hl, cut_dr
cd_r:           push    bc
                push    hl
                ld      a, (hl)
                ld      (cr_c0), a
                inc     hl
                ld      a, (hl)
                ld      (cr_c1), a
                inc     hl
                ld      a, (hl)
                ld      (cr_yy), a
                inc     hl
                ld      a, (hl)
                ld      (cr_y1), a
                call    comp_rect
                pop     hl
                ld      de, 4
                add     hl, de
                pop     bc
                djnz    cd_r
                ret
; find_obj: C = identity -> HL = its cut_objs entry + 0 (0: none); IX kept
find_obj:       ld      a, (cut_nobj)
                or      a
                jr      z, fo_no
                ld      b, a
                ld      hl, cut_objs
fo_1:           push    hl
                ld      de, 4
                add     hl, de
                ld      a, (hl)
                pop     hl
                cp      c
                ret     z
                ld      de, OBJ_SIZE
                add     hl, de
                djnz    fo_1
fo_no:          ld      hl, 0
                ret
; shown_box: IX = a cut_shown entry: its box to the dirty list (nothing when empty)
shown_box:      ld      a, (ix + 0)
                or      (ix + 1)
                ret     z
                ld      a, (ix + 5)     ; h
                ld      b, (ix + 4)     ; wb
                ld      c, (ix + 2)     ; c0
                ld      e, (ix + 3)     ; y0
                dec     a
                add     a, e
                ld      d, a            ; y1
                ld      a, c
                add     a, b
                dec     a
                cp      40
                jr      c, sb_c1
                ld      a, 39           ; (an image cut at the right edge)
sb_c1:          ld      b, a            ; c1
; add_rect: C = c0, B = c1, E = y0, D = y1: to the dirty list (cut_dr: c0, c1, y0, y1)
add_rect:       ld      a, (cut_nd)
                cp      MAX_RECTS
                jr      c, ar_1
                ld      a, MAX_RECTS - 1        ; (full: the last one grows; the scenes need few)
                ld      (cut_nd), a
                push    bc
                push    de
                call    ar_addr
                pop     de
                pop     bc
                jp      merge_into
ar_1:           push    bc
                push    de
                call    ar_addr
                pop     de
                pop     bc
                ld      (hl), c
                inc     hl
                ld      (hl), b
                inc     hl
                ld      (hl), e
                inc     hl
                ld      (hl), d
                ld      hl, cut_nd
                inc     (hl)
                ret
ar_addr:        add     a, a            ; HL = cut_dr + 4 A
                add     a, a
                ld      l, a
                ld      h, 0
                ld      de, cut_dr
                add     hl, de
                ret
; merge_into: HL = a rectangle, C, B, E, D = another: HL's becomes their bounding box
merge_into:     ld      a, c
                cp      (hl)
                jr      nc, mi_1
                ld      (hl), a
mi_1:           inc     hl
                ld      a, (hl)
                cp      b
                jr      nc, mi_2
                ld      (hl), b
mi_2:           inc     hl
                ld      a, e
                cp      (hl)
                jr      nc, mi_3
                ld      (hl), a
mi_3:           inc     hl
                ld      a, (hl)
                cp      d
                ret     nc
                ld      (hl), d
                ret
; merge_rects: overlapping rectangles merged until none overlap
merge_rects:    ld      a, (cut_nd)
                cp      2
                ret     c
                ld      ix, cut_dr      ; i
                ld      (mr_i), a
mr_i1:          ld      a, (mr_i)
                dec     a
                ld      (mr_j), a       ; the ones after i
                push    ix
                pop     iy
mr_j1:          ld      a, (mr_j)
                or      a
                jr      z, mr_inext
                ld      de, 4
                add     iy, de
                ld      a, (iy + 0)     ; overlap: i.c0 <= j.c1, j.c0 <= i.c1, i.y0 <= j.y1, j.y0 <= i.y1
                cp      (ix + 1)
                jr      z, mr_o1
                jr      nc, mr_jnext
mr_o1:          ld      a, (ix + 0)
                cp      (iy + 1)
                jr      z, mr_o2
                jr      nc, mr_jnext
mr_o2:          ld      a, (iy + 2)
                cp      (ix + 3)
                jr      z, mr_o3
                jr      nc, mr_jnext
mr_o3:          ld      a, (ix + 2)
                cp      (iy + 3)
                jr      z, mr_o4
                jr      nc, mr_jnext
mr_o4:          ld      c, (iy + 0)     ; i := the bounding box; j := the last one; start again
                ld      b, (iy + 1)
                ld      e, (iy + 2)
                ld      d, (iy + 3)
                push    ix
                pop     hl
                call    merge_into
                ld      a, (cut_nd)
                dec     a
                ld      (cut_nd), a
                call    ar_addr
                push    iy
                pop     de
                ld      bc, 4
                ldir
                jr      merge_rects
mr_jnext:       ld      hl, mr_j
                dec     (hl)
                jr      mr_j1
mr_inext:       ld      de, 4
                add     ix, de
                ld      hl, mr_i
                dec     (hl)
                ld      a, (hl)
                cp      2
                jr      nc, mr_i1
                ret

; comp_rect: the rectangle cr_c0..cr_c1 x cr_yy..cr_y1: the objects that cover part of it (in draw order) are listed
; once with their clipped columns and rows (cut_ro), then every row is composed in RB: the room's row from page 1, the
; listed objects (RB = RB AND mask OR plane), the stars (only in a star's own rectangle), and copied to VRAM
comp_rect:      ld      a, 1
                ld      (cr_rstep), a
                ld      a, (cr_pass)
                inc     a
                jr      z, crt_all
                ld      a, 5
                ld      (cr_rstep), a
                ld      a, (cr_yy)      ; the first row of the pass in the rectangle
                call    pass_up
                ld      (cr_yy), a
                ld      hl, cr_y1
                cp      (hl)
                jr      z, crt_all
                ret     nc
crt_all:        ld      a, (cr_c1)
                ld      hl, cr_c0
                sub     (hl)
                inc     a
                ld      (cr_n), a
                xor     a
                ld      (cr_nro), a
                ld      a, (cut_nobj)
                or      a
                jr      z, crt_st
                ld      b, a
                ld      ix, cut_objs
                ld      iy, cut_ro
crt_o:          push    bc
                call    ro_add
                ld      de, OBJ_SIZE
                add     ix, de
                pop     bc
                djnz    crt_o
crt_st:         ld      a, (cr_c0)      ; a star's rectangle: 1 x 1, at a star (the objects never come near them)
                ld      hl, cr_c1
                cp      (hl)
                jr      nz, crt_nost
                ld      a, (cr_yy)
                ld      hl, cr_y1
                cp      (hl)
                jr      nz, crt_nost
                ld      a, 1
                jr      crt_st1
crt_nost:       xor     a
crt_st1:        ld      (cr_star), a
crt_row:        call    comp_row
                ld      a, (cr_rstep)
                ld      hl, cr_yy
                add     a, (hl)
                ld      (hl), a
                ld      hl, cr_y1
                cp      (hl)
                jr      c, crt_row
                jr      z, crt_row
                ret
; pass_up: A = a row -> the first row >= A with row mod 5 = cr_pass (keeps BC, DE, HL)
pass_up:        push    bc
                ld      b, a
pu_1:           ld      a, b
pu_2:           sub     5
                jr      nc, pu_2
                add     a, 5
                ld      c, a
                ld      a, (cr_pass)
                cp      c
                ld      a, b
                jr      z, pu_3
                inc     b
                jr      pu_1
pu_3:           pop     bc
                ret
; ro_add: IX = an object: if it covers part of the rectangle, its entry in cut_ro (IY, then IY moves on): the data
; at its first row and column in the rectangle, the row stride 5 wb, wb, the first column, the columns, the first and
; last row
ro_add:         ld      l, (ix + 0)
                ld      h, (ix + 1)
                dec     hl
                ld      a, (hl)         ; h
                dec     hl
                ld      c, (hl)         ; wb
                ld      b, a
                ld      a, (ix + 3)     ; rows: max(ytop, y0) .. min(ytop + h - 1, y1)
                ld      e, a
                add     a, b
                dec     a
                ld      hl, cr_y1
                cp      (hl)
                jr      c, roa_1
                ld      a, (hl)
roa_1:          ld      (iy + 8), a     ; yb
                ld      a, e
                ld      hl, cr_yy
                cp      (hl)
                jr      nc, roa_2
                ld      a, (hl)
roa_2:          ld      d, a
                ld      a, (cr_rstep)
                cp      5
                ld      a, d
                call    z, pass_up      ; (a pass: its first row in the object)
                ld      (iy + 7), a     ; ya
                ld      d, a
                ld      a, (iy + 8)
                cp      d
                ret     c               ; (no common row)
                ld      a, (ix + 2)     ; columns: max(col, c0) .. min(col + wb - 1, c1)
                ld      b, a
                add     a, c
                dec     a
                ld      hl, cr_c1
                cp      (hl)
                jr      c, roa_3
                ld      a, (hl)
roa_3:          ld      h, a            ; cb
                ld      a, b
                push    hl
                ld      hl, cr_c0
                cp      (hl)
                jr      nc, roa_4
                ld      a, (hl)
roa_4:          pop     hl
                ld      l, a            ; ca
                ld      a, h
                sub     l
                ret     c               ; (no common column)
                inc     a
                ld      (iy + 6), a     ; the columns
                ld      (iy + 5), l     ; ca
                ld      (iy + 4), c     ; wb
                ld      a, l            ; the data: sprite + (ya - ytop) * 5 wb + 5 (ca - col)
                sub     b
                ld      b, a
                add     a, a
                add     a, a
                add     a, b
                ld      l, a
                ld      h, 0
                ld      a, c
                ld      c, l
                ld      b, h            ; BC = 5 (ca - col)
                ld      l, a
                add     hl, hl
                add     hl, hl
                ld      e, a
                ld      d, 0
                add     hl, de          ; 5 wb
                ld      (iy + 2), l
                ld      (iy + 3), h
                ex      de, hl          ; DE = 5 wb
                ld      l, (ix + 0)
                ld      h, (ix + 1)
                add     hl, bc
                ld      a, (iy + 7)
                sub     (ix + 3)
                jr      z, roa_6
roa_5:          add     hl, de
                dec     a
                jr      nz, roa_5
roa_6:          ld      (iy + 0), l
                ld      (iy + 1), h
                ld      a, (cr_rstep)
                cp      5
                jr      nz, roa_7
                ld      l, (iy + 2)     ; (a pass: every 5th row)
                ld      h, (iy + 3)
                ld      d, h
                ld      e, l
                add     hl, hl
                add     hl, hl
                add     hl, de
                ld      (iy + 2), l
                ld      (iy + 3), h
roa_7:          ld      de, RO_SIZE
                add     iy, de
                ld      hl, cr_nro
                inc     (hl)
                ret

; comp_row: row cr_yy of the rectangle: the room (page 1: y * 160 + p * 40 + c0), the listed objects, the stars -> VRAM
comp_row:       ld      a, (cr_yy)
                ld      l, a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl
                add     hl, hl
                add     hl, hl          ; 32 y
                ld      d, h
                ld      e, l
                add     hl, hl
                add     hl, hl
                add     hl, de          ; 160 y
                ld      a, (cr_c0)
                ld      e, a
                ld      d, 0
                add     hl, de
                ld      a, P1_PAGE
                out     (RD_PAGE), a
                ex      de, hl          ; DE = the RAM-disk address
                ld      a, (cr_c0)
                ld      l, a
                ld      h, RB_PAGE      ; HL = RB plane 0
                ld      a, (cr_n)
                ld      (crg_n + 2), a
                ld      a, 4
crg_pl:         ld      b, d
                ld      c, RD_ADDR
                out     (c), e
crg_n:          ld      bc, RD_DATA     ; (B: the columns, patched)
                inir
                ld      bc, 40
                ex      de, hl
                add     hl, bc
                ex      de, hl          ; the next plane's address
                ld      bc, (cr_n)
                ld      b, 0
                or      a
                sbc     hl, bc
                inc     h               ; RB's next plane, column c0
                dec     a
                jr      nz, crg_pl
                ld      a, (cr_nro)     ; the objects
                or      a
                jr      z, cr_stars
                ld      b, a
                ld      ix, cut_ro
cr_obj:         push    bc
                ld      a, (cr_yy)
                cp      (ix + 7)
                jr      c, cro_n
                ld      c, a
                ld      a, (ix + 8)
                cp      c
                jr      c, cro_n
                call    ro_row
cro_n:          ld      de, RO_SIZE
                add     ix, de
                pop     bc
                djnz    cr_obj
cr_stars:       ld      a, (cr_star)
                or      a
                call    nz, star_row
                ld      a, (cr_yy)      ; VRAM: y * 40 + c0, plane by plane
                ld      l, a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      d, h
                ld      e, l
                add     hl, hl
                add     hl, hl
                add     hl, de
                ld      a, (cr_c0)
                ld      e, a
                ld      d, 0
                add     hl, de
                ld      de, VRAM
                add     hl, de
                ex      de, hl          ; DE = VRAM
                ld      a, (cr_c0)
                ld      l, a
                ld      h, RB_PAGE
                ld      a, (cr_n)
                ld      c, a
                ld      b, 0
                in      a, (0xe0)
                ld      a, 1
crp_pl:         out     (PORT_WF), a
                push    hl
                push    de
                push    bc
                ldir
                pop     bc
                pop     de
                pop     hl
                inc     h
                add     a, a
                cp      16
                jr      nz, crp_pl
                in      a, (0xe1)
                ret
; ro_row: IX = a cut_ro entry on this row: its row into RB (RB = RB AND mask OR plane; the sprite's bytes column by
; column: mask, planes 0-3), then its data to the next row
ro_row:         ld      e, (ix + 0)
                ld      d, (ix + 1)
                ld      l, (ix + 5)
                ld      h, RB_PAGE
                ld      b, (ix + 6)
ror_c:          ld      a, (de)         ; the inverted mask
                inc     de
                ld      c, a
                ld      a, (hl)         ; plane 0
                and     c
                ex      de, hl
                or      (hl)
                inc     hl
                ex      de, hl
                ld      (hl), a
                inc     h
                ld      a, (hl)         ; plane 1
                and     c
                ex      de, hl
                or      (hl)
                inc     hl
                ex      de, hl
                ld      (hl), a
                inc     h
                ld      a, (hl)         ; plane 2
                and     c
                ex      de, hl
                or      (hl)
                inc     hl
                ex      de, hl
                ld      (hl), a
                inc     h
                ld      a, (hl)         ; plane 3
                and     c
                ex      de, hl
                or      (hl)
                inc     hl
                ex      de, hl
                ld      (hl), a
                ld      a, h
                sub     3
                ld      h, a
                inc     l
                djnz    ror_c
                ld      l, (ix + 0)     ; the next row
                ld      h, (ix + 1)
                ld      e, (ix + 2)
                ld      d, (ix + 3)
                add     hl, de
                ld      (ix + 0), l
                ld      (ix + 1), h
                ret
; star_row: the stars on row cr_yy in the rectangle's columns: their pixel in RB
star_row:       ld      b, 6
                ld      iy, cut_stars
                ld      hl, cut_stcol
srw_1:          ld      a, (cr_yy)
                cp      (iy + 1)
                jr      nz, srw_n
                ld      a, (iy + 0)
                rrca
                rrca
                rrca
                and     31
                ld      c, a
                ld      a, (cr_c0)
                cp      c
                jr      nz, srw_n
                push    bc
                push    hl
                ld      e, (hl)         ; the colour: star_colors[index] (EGA 8, 7, 15 = MZ 8, 7, 15)
                ld      d, 0
                ld      hl, cut_stc
                add     hl, de
                ld      d, (hl)
                ld      a, (iy + 0)     ; the bit
                and     7
                ld      b, a
                ld      a, 1
                jr      z, srw_b2
srw_b:          add     a, a
                djnz    srw_b
srw_b2:         ld      e, a
                ld      l, c
                ld      h, RB_PAGE
                ld      b, 4
srw_p:          ld      a, e
                cpl
                and     (hl)
                rr      d
                jr      nc, srw_p1
                or      e
srw_p1:         ld      (hl), a
                inc     h
                djnz    srw_p
                pop     hl
                pop     bc
srw_n:          inc     iy
                inc     iy
                inc     hl
                djnz    srw_1
                ret

; ---------------------------------------------------------------- data
cut_stars:      db      20, 97, 16, 104, 23, 110, 17, 116, 24, 120, 18, 128    ; SDLPoP stars[] (x, y)
cut_stc:        db      8, 7, 15, 15, 7                                         ; star_colors (EGA = MZ for these)
                include "../../build/assets/cut.inc"    ; frame_tbl_cuts, CSEQ_*, cut_prio, cut_intr, cut_len60, cut_star0
cut_init:       dw      12345 & 0xffff, 12345 >> 16     ; the seed (SDLPoP: the game's; the oracle hook: 12345)
                db      1, 6, 0         ; princess_torch_frame, which_torch
                db      0, 0xff, 6      ; hourglass_state, hourglass_sandflow, cutscene_frame_time
                db      0, 0            ; flash_time, flash_color
                db      0xff, 0         ; next_sound, current_sound
                dw      0               ; the ticks model: left
                ds      6, 0            ; (the stars' colours: copied from cut_star0 below)
                ds      6, 0
cut_vars:
cut_seed:       ds      4
cut_torch:      ds      2
cut_which:      ds      1
cut_hg:         ds      1
cut_sand:       ds      1
cut_ft:         ds      1
cut_flash:      ds      1
cut_flcol:      ds      1
cut_next:       ds      1
cut_cur:        ds      1
cut_left:       ds      2
cut_stcol:      ds      6               ; the stars' colour indices (logic)
cut_stshow:     ds      6               ; the ones on the screen
cut_vars_end:
cut_kid:        ds      CR_SIZE         ; (from here to cut_zero_end: 0 at the start)
cut_shad:       ds      CR_SIZE
cut_char:       ds      CR_SIZE
cut_shown:      ds      N_IDS * SHOWN_SIZE
co_last:        ds      4               ; per slot: the cut_spr entry found last
slot_cur:       ds      4               ; per slot: the entry whose PZ block is in its buffer
cut_n:          ds      1
cut_ndrawn:     ds      1
cut_zero_end:
cut_wait:       ds      1
cut_late:       ds      1
cut_fresh:      ds      1
cut_star:       ds      1
cut_flshow:     ds      1
cut_nobj:       ds      1
cut_objs:       ds      MAX_OBJS * OBJ_SIZE
cut_nd:         ds      1
cut_dr:         ds      MAX_RECTS * 4
cut_fr:         ds      5
co_slot:        ds      1
co_x:           ds      2
co_y:           ds      2
co_key:         ds      2
co_k:           ds      2
co_ky:          ds      2
co_s:           ds      2
co_sy:          ds      2
co_kcb:         ds      2
co_scb:         ds      2
co_ent:         ds      4               ; per slot: its object's cut_spr entry
cr_c0:          ds      1
cr_c1:          ds      1
cr_yy:          ds      1
cr_y1:          ds      1
cr_n:           ds      2
cr_nro:         ds      1
cr_star:        ds      1
cr_pass:        ds      1               ; a fade-in's pass (0-4), 0xFF: all rows
cr_rstep:       ds      1
cut_flags:      ds      1
cut_ro:         ds      MAX_OBJS * RO_SIZE
mr_i:           ds      1
mr_j:           ds      1
pr_max_c:       ds      1
pr_t:           ds      4
pr_a:           ds      4
cut_com:        ds      CUT_COM_N * 2   ; (the room entry writes it)
end_of_cut:
