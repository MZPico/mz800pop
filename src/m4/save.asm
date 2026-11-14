; ---------------------------------------------------------------- save / restore (M5, SDLPoP seg000 save_game / load_game)
; The save overlay (window W2, src/m4/ovl_save.asm). Ctrl+G during play on levels 3-13 (SDLPoP's original rule) writes
; SDLPoP's PRINCE.SAV fields to the game disk's file POP800.SAV (one FSMZ block, preallocated by tools/mkgamedisk.py)
; and shows "GAME SAVED" or "UNABLE TO SAVE GAME" on the bottom line for 24 ticks. load_saved reads it back (for the
; title's Ctrl+L, M7). The game is paused while the drive works (interrupts off: the FDC loops answer every DRQ).
; Runs at the start of a tick (game.asm, before kid_tick: SDLPoP's process_key runs before play_frame), after
; pend_flush: COMPOSE_A/B (this window) hold nothing then.
;
; The record (sector 0 of POP800.SAV, the rest of the 256 bytes 0):
;   0  "POP8"      magic
;   4  1           version
;   5  rem_min     16-bit (SDLPoP word; REM_MIN)
;   7  rem_tick    16-bit (REM_TICK)
;   9  level       16-bit (current_level; level_number)
;  11  hitp_beg_lev 16-bit (HITP_BEG_LEV)
;  13  checksum    the bytes 0-13 sum to 0 (mod 256)
SV_LEN          equ     14
SV_SEC          equ     OVL_W2 + 0x700          ; the sector (256 bytes)
SV_DIR          equ     OVL_W2 + 0x800          ; the FSMZ directory (blocks 16-23: logical track 1, sectors 1-8)
TXT_MSG_SAVED   equ     1                       ; TEXT_MSG (src/m4/text.asm)
TXT_MSG_UNABLE  equ     2

; save_game: Ctrl+G (KEYS bit 2). Keeps nothing.
save_game:      ld      a, (level_number)
                cp      3
                ret     c
                cp      14
                ret     nc
                ld      hl, SV_SEC              ; the record
                ld      de, SV_SEC + 1
                ld      bc, 255
                ld      (hl), b
                ldir
                ld      hl, sv_magic
                ld      de, SV_SEC
                ld      bc, 5
                ldir
                ex      de, hl
                ld      a, (REM_MIN)
                call    sv_w8
                ld      de, (REM_TICK)
                ld      (hl), e
                inc     hl
                ld      (hl), d
                inc     hl
                ld      a, (level_number)
                call    sv_w8
                ld      a, (HITP_BEG_LEV)
                call    sv_w8
                call    sv_sum                  ; A = the sum of bytes 0-12, HL = SV_SEC + 13
                neg
                ld      (hl), a
                di
                call    sv_find                 ; HL = the file's block
                jr      nz, sg_fail
                ld      a, 1
                ld      (sv_wr), a
                call    sv_ts
                ld      hl, SV_SEC
                call    sv_io
                jr      nz, sg_fail
                xor     a                       ; read it back into the directory buffer and compare
                ld      (sv_wr), a
                call    sv_ts
                ld      hl, SV_DIR
                call    sv_io
                jr      nz, sg_fail
                ld      hl, SV_SEC
                ld      de, SV_DIR
                ld      b, 0
sg_cmp:         ld      a, (de)
                cp      (hl)
                jr      nz, sg_fail
                inc     hl
                inc     de
                djnz    sg_cmp
                ld      b, TXT_MSG_SAVED
                jr      sg_text
sg_fail:        ld      b, TXT_MSG_UNABLE
sg_text:        call    sv_off
                ld      hl, 24                  ; text_time_remaining = 24 (text_time_total stays)
                ld      (TEXT_REM), hl
                ld      hl, TEXT_GEN            ; a new text to draw
                inc     (hl)
                ld      a, (hl)
                ld      (TEXT_MSG_GEN), a
                ld      a, b
                ld      (TEXT_MSG), a
                ret

; load_saved: POP800.SAV -> level_number, REM_MIN, REM_TICK, HITP_BEG_LEV (SDLPoP load_game: start_level etc.; the
; caller then starts that level without resetting the time). Out: A = 0 and Z: loaded; A = 1: no valid save (magic,
; version, checksum or values wrong: nothing changed); A = 2: disk error.
load_saved:     di
                call    sv_find
                jr      nz, ls_err
                xor     a
                ld      (sv_wr), a
                call    sv_ts
                ld      hl, SV_SEC
                call    sv_io
                jr      nz, ls_err
                call    sv_off
                ld      hl, SV_SEC              ; magic and version
                ld      de, sv_magic
                ld      b, 5
ls_mg:          ld      a, (de)
                cp      (hl)
                jr      nz, ls_bad
                inc     hl
                inc     de
                djnz    ls_mg
                call    sv_sum
                add     a, (hl)
                jr      nz, ls_bad
                ld      ix, SV_SEC
                ld      a, (ix + 5)             ; rem_min 1..60 (the time left), high bytes 0
                dec     a
                cp      60
                jr      nc, ls_bad
                ld      a, (ix + 9)             ; level 3..13
                cp      3
                jr      c, ls_bad
                cp      14
                jr      nc, ls_bad
                ld      a, (ix + 11)            ; hit points 1..10
                dec     a
                cp      10
                jr      nc, ls_bad
                ld      a, (ix + 8)             ; rem_tick 0..719
                cp      3
                jr      nc, ls_bad
                ld      a, (ix + 6)
                or      (ix + 10)
                or      (ix + 12)
                jr      nz, ls_bad
                ld      a, (ix + 5)
                ld      (REM_MIN), a
                ld      l, (ix + 7)
                ld      h, (ix + 8)
                ld      (REM_TICK), hl
                ld      a, (ix + 9)
                ld      (level_number), a
                ld      a, (ix + 11)
                ld      (HITP_BEG_LEV), a
                xor     a
                ei
                ret
ls_bad:         ld      a, 1
                or      a
                ei
                ret
ls_err:         call    sv_off
                ld      a, 2
                or      a
                ret

; sv_w8: A -> (HL) as a 16-bit word, HL += 2
sv_w8:          ld      (hl), a
                inc     hl
                ld      (hl), 0
                inc     hl
                ret
; sv_sum: A = the sum of SV_SEC's bytes 0-12, HL = SV_SEC + 13
sv_sum:         ld      hl, SV_SEC
                ld      bc, 256 * (SV_LEN - 1)
ss_1:           ld      a, c
                add     a, (hl)
                ld      c, a
                inc     hl
                djnz    ss_1
                ret
; sv_off: the motor off (as the ROM does after a load), interrupts on. In PRES (SV_PRES 1) through the resident
; launcher (LN_MOTOR_OFF), which records it (boot.asm fd_on): its next load then waits for the spin-up.
sv_off:
                if      SV_PRES = 0
                xor     a
                out     (FD_MOTOR), a
                else
                call    LN_MOTOR_OFF
                endif
                ei
                ret
; sv_ts: sv_blk -> A = logical track (block / 16), E = sector (block mod 16 + 1), D = 1 (keeps nothing else)
sv_ts:          ld      hl, (sv_blk)
                ld      a, l
                and     15
                inc     a
                ld      e, a
                ld      d, 1
                add     hl, hl          ; (blocks < 4096: H = block / 16)
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      a, h
                ret

; sv_find: drive 0 on, the spin-up wait, READY, the directory read, sv_blk = POP800.SAV's start block. Z = found.
; The motor is off here in the game (the launcher stops it before it starts the game) and may be either in PRES:
; always the full spin-up (~1 s, 16 x 60 ms as the ROM, E517h; a PC drive reports READY at once, or has no READY).
sv_find:        ld      a, 0x84                 ; drive 0, motor on (the loader's fd_init)
                out     (FD_MOTOR), a
                ld      b, 16
sf_spin:        call    delay_long
                djnz    sf_spin
                ld      hl, 0
sf_rdy:         in      a, (FD_CMD)             ; READY: status bit 7 low (inverted bus)
                cpl
                rlca
                jr      nc, sf_go
                dec     hl
                ld      a, h
                or      l
                jr      nz, sf_rdy
                or      1                       ; NZ: no drive / no disk
                ret
sf_go:          ld      a, 0xff                 ; the head's cylinder is not known here: seek
                ld      (fd_cyl), a
                xor     a
                ld      (sv_wr), a
                ld      a, 1
                ld      de, 0x0101              ; the directory's first block (POP800.SAV's entry is in it: mkgamedisk
                ld      hl, SV_DIR              ; checks; the track is dense flux, src/boot/boot.asm dir_read)
                call    sv_io
                ret     nz
                ld      hl, SV_DIR
                ld      b, 8                    ; (one block of entries)
sf_ent:         push    bc
                push    hl
                ld      a, (hl)                 ; (type 0: a free entry)
                or      a
                jr      z, sf_next
                inc     hl
                ld      de, sv_name
                ld      b, 11
sf_cmp:         ld      a, (de)
                cp      (hl)
                jr      nz, sf_next
                inc     hl
                inc     de
                djnz    sf_cmp
                pop     hl
                pop     bc
                ld      de, 0x1e                ; the start block
                add     hl, de
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a
                ld      (sv_blk), hl
                xor     a
                ret
sf_next:        pop     hl
                ld      de, 32
                add     hl, de
                pop     bc
                djnz    sf_ent
                or      1                       ; NZ: not on this disk
                ret

; sv_io: A = logical track, E = first sector, D = sectors, HL = buffer, sv_wr = 1: write (one sector), 0: read.
; Up to 6 tries; after a failed one a restore, ~0.3 s (a slow drive settles) and a seek again (the loader's
; fd_read_retry). Z = ok (A = 0). Keeps D, E, HL.
sv_io:          ld      b, 6
sio_1:          ld      c, a
                push    bc
                push    de
                push    hl
                ld      a, (sv_wr)
                or      a
                ld      a, c
                jr      z, sio_r
                call    fd_write
                jr      sio_2
sio_r:          call    fd_read
sio_2:          jr      z, sio_ok
                ld      a, 0x0b                 ; restore (and its ~60 ms), ~240 ms more, then seek again
                call    fd_type1
                ld      b, 4
sio_w:          call    delay_long
                djnz    sio_w
                ld      a, 0xff
                ld      (fd_cyl), a
                or      a                       ; NZ
sio_ok:         pop     hl
                pop     de
                pop     bc
                ret     z
                ld      a, c
                djnz    sio_1
                ret                             ; NZ: every try failed

                include "../boot/fdc.asm"
sv_magic:       db      "POP8", 1
sv_name:        db      "POP800.SAV", 0x0d
fd_cyl:         db      0xff
sv_wr:          db      0
sv_blk:         dw      0
