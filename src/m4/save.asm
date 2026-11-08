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
; sv_off: the motor off (as the ROM does after a load), interrupts on
sv_off:         xor     a
                out     (FD_MOTOR), a
                ei
                ret
; sv_ts: sv_blk -> A = logical track (block / 16), E = sector (block mod 16 + 1), D = 1 (keeps nothing else)
sv_ts:          ld      hl, (sv_blk)
                ld      a, l
                and     15
                inc     a
                ld      e, a
                ld      d, 1
                ld      a, l
                srl     h
                rra
                srl     h
                rra
                srl     h
                rra
                srl     h
                rra
                ret

; sv_find: drive 0 on (wait for READY), the directory read, sv_blk = POP800.SAV's start block (sv_findn: HL = the
; name, 11 bytes). Z = found.
sv_find:        ld      hl, sv_name
sv_findn:       ld      (sv_np), hl
                ld      a, 0x84                 ; drive 0, motor on (the loader's fd_init)
                out     (FD_MOTOR), a
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
                ld      de, 0x0801              ; 8 sectors from sector 1
                ld      hl, SV_DIR
                call    sv_io
                ret     nz
                ld      hl, SV_DIR
                ld      b, 64
sf_ent:         push    bc
                push    hl
                ld      a, (hl)                 ; (type 0: a free entry)
                or      a
                jr      z, sf_next
                inc     hl
                ld      de, (sv_np)
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
; Up to 4 tries, a restore before each retry (the loader's fd_read_retry). Z = ok.
sv_io:          ld      b, 4
sio_1:          push    bc
                push    de
                push    hl
                push    af
                ld      c, a
                ld      a, (sv_wr)
                or      a
                ld      a, c
                jr      z, sio_r
                di
                call    fd_write
                jr      sio_2
sio_r:          di                      ; (sv_ei: interrupts on again after each transfer, the room-list fetch)
                call    fd_read
sio_2:          call    sio_ei
                jr      z, sio_ok
                ld      a, 0x0b                 ; restore, then seek again
                call    fd_type1
                ld      a, 0xff
                ld      (fd_cyl), a
                pop     af
                pop     hl
                pop     de
                pop     bc
                djnz    sio_1
                or      1
                ret
sio_ok:         pop     af
                pop     hl
                pop     de
                pop     bc
                xor     a
                ret
sio_ei:         push    af                      ; keeps the flags
                ld      a, (sv_ei)
                or      a
                jr      z, sie_1
                ei
sie_1:          pop     af
                ret

; ---------------------------------------------------------------- the level's room lists (M8a part 22)
                if defined RL_ON                ; (the game's save overlay; PRES includes this file for load_saved)
; rl_fetch_h: the blob of the level (level_number) from POP800.RLS into the RAM disk (src/m3/rlists.asm RL_PAGE:RL_BASE).
; Called from the room draw (rlists.asm rl_load) at the first room of a level. The file holds per level its PZ chunks
; (tools/roomlists.py: each unpacks to at most 2 KB of the blob), the block table is build/assets/rlists.inc. The
; interrupts stay on but for the sector transfers (the music plays on). Z = the blob is in the RAM disk.
RL_PZBUF        equ     OVL_W2 + 0x500          ; the level's packed blocks (11 at most: to the window's end)
RL_UNBUF        equ     0x9000                  ; a chunk unpacked (the op lists' place: the room draw rebuilds them)
rl_fetch_h:     ld      a, (level_number)
                dec     a
                cp      14
                jp      nc, rfe_no
                add     a, a
                add     a, a
                ld      e, a
                ld      d, 0
                ld      ix, rl_disk
                add     ix, de
                ld      a, 1
                ld      (sv_ei), a
                ld      hl, rl_name
                call    sv_findn
                jp      nz, rfe_err
                ld      hl, (sv_blk)            ; the file's first blocks: the compare's low code (src/m4/rllow.asm)
                push    hl
                ld      b, RL_LOWBLK
                ld      hl, RL_UNBUF
                call    rfe_read
                pop     de
                jp      nz, rfe_err
                ld      l, (ix + 0)             ; the level's first block
                ld      h, (ix + 1)
                add     hl, de
                ld      (sv_blk), hl
                ld      b, (ix + 2)             ; blocks
                ld      hl, RL_PZBUF
                call    rfe_read
                jp      nz, rfe_err
                ld      hl, RL_UNBUF            ; the low code to its place
                ld      de, RL_LOWCODE
                ld      bc, RL_LOWN
                ldir
                xor     a
                ld      (sv_ei), a
                call    sv_off
                ld      hl, RL_PZBUF            ; the chunks: unpacked, written to the RAM disk
                ld      de, RL_BASE
                ld      b, (ix + 3)
rfe_ch:         push    bc
                push    de
                ld      de, RL_UNBUF
                call    unpz                    ; DE = the chunk's end, HL = the next packed chunk
                pop     bc                      ; BC = the chunk's RAM-disk address
                push    hl
                push    bc
                ex      de, hl
                ld      de, RL_UNBUF
                or      a
                sbc     hl, de
                push    hl                      ; its length
                ld      e, c
                ld      d, b
                ld      a, RL_PAGE
                call    far_seek
                pop     de
                ld      hl, RL_UNBUF
                ld      c, RD_DATA
rfe_o1:         ld      a, d
                or      a
                jr      z, rfe_o2
                ld      b, 0
                otir
                dec     d
                jr      rfe_o1
rfe_o2:         ld      a, e
                or      a
                jr      z, rfe_o3
                ld      b, a
                otir
rfe_o3:         pop     de                      ; the next chunk's RAM-disk address: + 2 KB
                ld      hl, 0x800
                add     hl, de
                ex      de, hl
                pop     hl                      ; the next packed chunk
                pop     bc
                djnz    rfe_ch
                xor     a
                ret
; rfe_read: sv_blk = the first block, B = blocks, HL = the buffer: read a track's run at a time. Z = ok
rfe_read:
rfe_run:        push    hl
                push    bc
                call    sv_ts                   ; A = track, E = sector
                pop     bc
                ld      c, a
                ld      a, 17
                sub     e                       ; the sectors left on the track
                cp      b
                jr      c, rfe_r1
                ld      a, b
rfe_r1:         ld      d, a                    ; D = this run's sectors
                pop     hl
                push    bc
                push    de
                push    hl
                ld      a, c
                call    sv_io
                pop     hl
                pop     de
                pop     bc
                ret     nz
                ld      a, b                    ; blocks left
                sub     d
                ld      b, a
                ld      e, d
                ld      d, 0
                push    hl
                ld      hl, (sv_blk)
                add     hl, de
                ld      (sv_blk), hl
                pop     hl
                ld      a, h                    ; the buffer: + the run's 256-byte sectors
                add     a, e
                ld      h, a
                ld      a, b
                or      a
                jr      nz, rfe_run
                ret
rfe_err:        xor     a
                ld      (sv_ei), a
                call    sv_off
rfe_no:         or      1
                ret
                include "../boot/unpz.asm"
                include "../../build/assets/rlists.inc"
                if RL_DISK_LOW - RL_LOWBLK
                .error tools/roomlists.py's LOW_BLOCKS and game.asm's RL_LOWBLK differ
                endif
rl_name:        db      "POP800.RLS", 0x0d
up_neg:         dw      0
                endif
sv_ei:          db      0
sv_np:          dw      0

                include "../boot/fdc.asm"
sv_magic:       db      "POP8", 1
sv_name:        db      "POP800.SAV", 0x0d
fd_cyl:         db      0xff
sv_wr:          db      0
sv_blk:         dw      0
