; pop-800 floppy loader (M5) and launcher (M7): the IPLPRO bootstrap of build/pop800.dsk (tools/mkgamedisk.py builds
; the disk). The ROM IPL reads it to 0x1200, moves it to LOAD and jumps to `boot`. It
;   1. checks for the 32 KB VRAM (bootscr.asm: without the MZ-1R25 extension a message and a stop at vram_stop),
;      switches to 320x200/16 colours and shows the title, the credit line and a progress bar,
;   2. probes the RAM disk (MZ-1R18 / STD protocol, ports E9-EB, F8): pages 0-7 must be distinct (512 KB or more),
;      else it shows a message and stops (rd_refuse); it measures the RAM disk's read speed (rd_speed, rdspeed.asm: a
;      table on the loading screen; too slow, or a timer that cannot be right: a message and a stop at rs_stop);
;      then it copies its own image to the RAM disk (LN_RD_PAGE:
;      LN_RD_ADDR, launch.inc): that copy is the launcher the game loads to swap itself out,
;   3. finds the data files POP800.D1, D2, ... in the FSMZ directory and reads them with its own WD2793 code
;      (multi-sector reads of whole tracks, as the ROM IPL does them),
;   4. decompresses the records (tools/mkgamedisk.py: the stream format; tools/pzpack.py: the PZ format) into the
;      RAM disk: the art, the overlays and the game's compressed image (a record stream itself, GAME_RD_PAGE:ADDR),
;   5. writes the handoff block "title" and launches (launch_main): PRES from POP800.PRS, which starts the game; on 1 MB
;      and more it first clears the frame store's marker and starts the game with ACT_FILL, which fills the store on
;      the loading screen ("PREPARING SPRITES", the bar) and then hands over to the title.
; The launcher (launch.inc: the interface and the handoff block) is entry LN_LAUNCH: it reads the handoff block from
; the RAM disk, zeroes 0x0000-0x11FF, copies the block to HO_MAIN and starts the GAME (its image decompressed from the
; RAM disk, ~0.5 s) or PRES (entry 0 of POP800.PRS from the floppy). LN_PRS_LOAD loads any POP800.PRS entry for PRES.
; Memory while loading: TRKBUF one track, OUTBUF/INBUF1 the RAM-disk records' buffers (boot only), INBUF2 the
; main-RAM records' input (their output goes straight to its place), the loader and its stack at 0xB000-0xBFFF.
; VRAM (0x8000-0x9FFF) and the CG ROM (0x1000-0x1FFF) are mapped only while drawing (draw_on / draw_off).

                include "launch.inc"
                if      defined DIAG
FD_DIAG         equ     1               ; (fdc.asm: the diagnostic hooks; dg_show)
                endif
LOAD            equ     LN_LOAD
STACK           equ     0xc000
TRKBUF          equ     0xa000          ; 4 KB: one track (16 x 256)
OUTBUF          equ     0x2000          ; RAM-disk records: decompressed block (16 KB)
INBUF1          equ     0x6000          ; RAM-disk records: compressed block (16 KB, to 0x9FFF)
INBUF2          equ     0x8000          ; main-RAM records: compressed block (8 KB)
GAME_START      equ     0x2000

VRAM            equ     0x8000
PORT_WF         equ     0xcc
PORT_DMD        equ     0xce
PORT_SCRL       equ     0xcf
PORT_PAL        equ     0xf0
RD_PAGE         equ     0xe9
RD_DATA         equ     0xea
RD_ADDR         equ     0xeb
RD_RESET        equ     0xf8
; FD_CMD .. FD_SIDE: fdc.asm

PORT_CTC1       equ     0xd5            ; 8253 counter 1, clocked by HSYNC (rd_speed)
PORT_CTCC       equ     0xd7            ; 8253 control
BAR_ROW         equ     112             ; progress bar: 8 rows from this line, 32 bytes from byte column 4
BAR_COL         equ     4
COL_TEXT        equ     15
COL_BAR_BG      equ     1
COL_BAR         equ     14
MSG_LOAD_AT     equ     100 * 40 + 4    ; "LOADING..." and "PREPARING SPRITES" (VRAM offset)

                org     LOAD
boot:           jp      boot_main       ; the ROM IPL's entry
launch:         jp      launch_main     ; LN_LAUNCH
prs_load:       jp      prs_load_main   ; LN_PRS_LOAD
; LN_LOADING: "LOADING..." where the loading screen has it (msg_load), over a black screen: before the GAME image
; is restored (the launcher itself) and after PRES's video_init (PRES), so no wait between the programs is blank. The
; launched game does not clear the screen (src/m4/gstart.asm video_init): the text stays until the room draw covers it.
loading:        ld      hl, msg_load
                jp      print_at
mot_off:        jp      motor_off       ; LN_MOTOR_OFF
                if launch - LN_LAUNCH
                .error the launcher's entries moved
                endif
                if prs_load - LN_PRS_LOAD
                .error the launcher's entries moved
                endif
                if loading - LN_LOADING
                .error the launcher's entries moved
                endif
                if mot_off - LN_MOTOR_OFF
                .error the launcher's entries moved
                endif
boot_main:      di
                ld      sp, STACK
                out     (0xe0), a       ; RAM at 0x0000-0x0FFF
                out     (0xe1), a       ; RAM at 0xE000-0xFFFF
                call    psg_off         ; (M7: the PSG muted before the floppy reads with interrupts off)
                call    zero_low
                call    boot_screen     ; (the boot only, bootscr.asm: the VRAM check, the title, the credit line)
                call    rd_probe
rd_probed:      jp      nz, rd_refuse   ; (harness breakpoint: rd_top is set)
                call    rd_speed        ; the read speed (rd_spd) on the loading screen; too slow: stops there
rd_measured:                            ; (harness breakpoint: rd_speed done)
                ld      a, LN_RD_PAGE   ; the launcher: this image as it is now (nothing in it has changed yet)
                ld      de, LN_RD_ADDR
                call    rd_seek
                ld      hl, LOAD
                ld      de, end_of_image - LOAD
                call    rd_out
                ld      hl, msg_load
                call    print_at
                if      defined DIAG
                ld      a, 0xff         ; (dg_who: the boot's own load)
                ld      (dg_who), a
                endif
                ld      hl, 0x0101      ; bar_on, and fd_on: the ROM's IPL load left the motor running (E5F6h)
                ld      (bar_on), hl
                call    bar_init
                call    fd_init
                call    dir_read
                call    dir_scan
                xor     a
                ld      (s_src), a
                call    s_next_file
                call    load_stream
                ld      hl, ho_title    ; the handoff block: the title, or on 1 MB and more first the frame store's
                ld      a, (rd_top)     ; fill (the game, ACT_FILL) on this screen (docs/ramdisk-tiers.md section 11)
                cp      LN_FS_TOP
                jr      c, bt_ho
                ld      a, LN_FS_PAGE   ; its marker cleared: every boot fills the store anew
                ld      de, LN_FS_MARK
                call    rd_seek
                ld      hl, ho_title + HO_BAR   ; (five zero bytes)
                ld      de, 5
                call    rd_out
                ld      hl, msg_prep    ; "PREPARING SPRITES" in the place of "LOADING...", the bar empty again; the
                ld      (loading + 1), hl       ; launcher below (fall through) prints its "LOADING..." with it: this
                call    print_at        ; one (the RAM disk's copy of the launcher, saved above, keeps msg_load)
                ld      a, BAR_COL
                ld      b, 32
                ld      c, COL_BAR_BG
                call    bar_fill
                ld      hl, ho_fill
bt_ho:          push    hl
                call    ho_seek
                pop     hl
                ld      de, HO_SIZE
                call    rd_out
                ; (fall through)

; ---------------------------------------------------------------- the launcher (LN_LAUNCH)
launch_main:    di
                ld      sp, STACK
                out     (0xe0), a
                out     (0xe1), a
                call    psg_off         ; (M7: the PSG muted before the floppy reads with interrupts off)
                call    draw_off
                call    motor_off       ; (A = 0) stopped while a program runs: the game never needs it (its save
                ld      (bar_on), a     ; overlay runs it itself), PRES's first load waits for the spin-up
                call    ho_seek
                ld      hl, ho_buf
                ld      de, HO_SIZE
                call    rd_in
                ld      hl, (ho_buf)
                ld      de, HO_MAGIC
                or      a
                sbc     hl, de
                jp      nz, data_err
                call    zero_low        ; the started program's variables start from a known state (SCRIPT_PTR 0x0876 = 0:
                ld      hl, ho_buf      ; no harness script), the block at HO_MAIN
                ld      de, HO_MAIN
                ld      bc, HO_SIZE
                ldir
                ld      a, (rd_top)     ; the RAM disk's last page (the probe), for the program started
                ld      (HO_MAIN + HO_RDTOP), a
                ld      a, (rd_spd)     ; and its read speed (rd_speed)
                ld      (HO_RDSPD_MAIN), a
                ld      a, (ho_buf + HO_ACTION)
                bit     ACT_PRES_BIT, a
                jr      nz, ln_pres
ln_duel1:       bit     ACT_DUEL_BIT, a ; the duel (src/duel/duel.asm): its staged pieces into the RAM disk's scratch
                ld      a, PRS_DUEL1 + PRS_KEEP ; first (a RAM-disk record: through the buffers the game's image
                call    nz, prs_load_main       ; overwrites; the motor kept on for PRS_DUEL below)
ln_duel1_end:   call    loading         ; "LOADING..." while the game is restored and starts (the screen is black)
                ld      a, 1            ; the game: its compressed image from the RAM disk
                ld      (s_src), a
                ld      a, GAME_RD_PAGE
                ld      de, GAME_RD_ADDR
                call    rd_seek
                call    load_stream
                xor     a               ; (the RAM disk left at page 0, address 0)
                ld      d, a
                ld      e, a
                call    rd_seek
ln_duel2:       ld      a, (ho_buf + HO_ACTION) ; the duel: its piece over the game's main loop (the game starts as
                bit     ACT_DUEL_BIT, a         ; always and runs into it after level 1's start)
                ld      a, PRS_DUEL
                call    nz, prs_load_main
ln_duel2_end:   jp      GAME_START
ln_pres:        ld      a, PRS_KEEP     ; PRES: entry 0 of POP800.PRS (the motor kept on: PRES loads next)
                call    prs_load_main
                jp      PRES_START

; prs_load_main (LN_PRS_LOAD): A = entry of POP800.PRS: its record stream (main-RAM records only) into main RAM; bit 7
; of A (PRS_KEEP): the motor keeps running after it (another load follows at once), else it stops (fd_on 0).
; POP800.PRS (tools/mkgamedisk.py): block 0 = the index: entry count (word), then per entry the first block (word,
; from the start of the file) and the block count (word); entry 0 is PRES, the others the scenes. The launcher reads the
; same as absolute blocks from the RAM disk's POP800.PRS table (launch.inc PRS_TAB_RD_ADDR, the boot's stream wrote it). Interrupts off,
; the motor off at the end (unless PRS_KEEP). Uses TRKBUF, INBUF2 and the launcher's own memory (0xA000-0xBFFF, 0x8000-0x9FFF).
prs_load_main:  di
                if      defined DIAG
                ld      (dg_who), a     ; (the entry, PRS_KEEP included)
                endif
                push    af
                call    psg_off         ; (M7: the PSG muted before the floppy reads with interrupts off)
                xor     a
                ld      (s_src), a
                ld      (bar_on), a
                ld      (f_cnt), a      ; (no next file: a 0xFE record is a data error)
                ld      (f_idx), a
                call    fd_init
                pop     af              ; its blocks: the POP800.PRS table in the RAM disk (no directory, no index read:
                push    af              ; the head goes straight to the entry's data)
                and     0x7f            ; (PRS_KEEP)
                add     a, a
                add     a, a
                ld      e, a
                ld      d, PRS_TAB_RD_ADDR >> 8
                ld      a, LN_RD_PAGE
                call    rd_seek
                ld      hl, s_blk       ; s_blk, s_left: the first block, the block count
                ld      de, 4
                call    rd_in
                ld      hl, (s_left)
                ld      a, h
                or      l
                jp      z, data_err     ; (no such entry)
                ld      hl, 0
                ld      (t_left), hl
                call    load_stream
                pop     af
                rlca                    ; PRS_KEEP: the motor stays on
                ret     c
motor_off:      xor     a               ; the motor off; fd_on 0: the next fd_init waits for the spin-up. A = 0
                out     (FD_MOTOR), a
                ld      (fd_on), a
                ret

; psg_off: attenuation 15 (off) on the four PSG channels (port F2h): a tone the game or PRES left playing would
; hang while the floppy is read with interrupts off. Uses A.
psg_off:        ld      a, 0x9f
po1:            out     (0xf2), a
                add     a, 0x20
                jr      nc, po1
                ret
zero_low:       ld      hl, 0           ; 0x0000-0x11FF to zero
                ld      de, 1
                ld      bc, 0x1200 - 1
                ld      (hl), l
                ldir
                ret

; ---------------------------------------------------------------- record streams
; load_stream: the records of the current stream (s_src: 0 the floppy, the current file; 1 the RAM disk at its
; current address) until the end record (0xFF). 0xFE: continue with the next file; 0xFD page, address (3 bytes):
; the stream continues there in the RAM disk.
load_stream:
rec_loop:       call    s_byte          ; record kind
                cp      0xff
                ret     z
                cp      0xfe
                jr      nz, rec_0
                call    s_next_file
                jp      rec_loop
rec_0:          cp      0xfd
                jr      nz, rec_1
                ld      de, r_kind      ; page, address
                ld      bc, 3
                call    s_get
                ld      a, (r_kind)
                ld      de, (r_addr)
                call    rd_seek
                jp      rec_loop
rec_1:          ld      (r_kind), a
                ld      de, r_addr      ; address, raw length, payload length, bar
                ld      bc, 7
                call    s_get
                ld      a, (r_kind)
                bit     6, a
                jr      nz, rec_main
                bit     7, a
                jr      nz, rec_rd_st
                ld      de, INBUF1
                ld      bc, (r_pay)
                call    s_get
                ld      hl, INBUF1
                ld      de, OUTBUF
                call    unpz
                ld      hl, OUTBUF
                call    rec_check
                jr      rec_rd_out
rec_rd_st:      ld      de, OUTBUF
                ld      bc, (r_pay)
                call    s_get
rec_rd_out:     ld      a, (r_kind)     ; copy OUTBUF to the RAM disk (floppy streams only)
                and     0x0f
                ld      de, (r_addr)
                call    rd_seek
                ld      hl, OUTBUF
                ld      de, (r_raw)
                call    rd_out
                jr      rec_bar
rec_main:       bit     7, a
                jr      nz, rec_m_st
                ld      de, INBUF2
                ld      bc, (r_pay)
                call    s_get
                ld      hl, INBUF2
                ld      de, (r_addr)
                call    unpz
                ld      hl, (r_addr)
                call    rec_check
                jr      rec_bar
rec_m_st:       ld      de, (r_addr)
                ld      bc, (r_pay)
                call    s_get
rec_bar:        ld      a, (r_bar)
                call    bar_to
                jp      rec_loop

; ho_seek: the RAM disk at the handoff block. rd_seek: A = RAM-disk page, DE = address. rd_out: HL = source, DE = count: to the RAM disk. rd_in: HL = destination,
; DE = count: from the RAM disk.
ho_seek:        ld      a, HO_RD_PAGE
                ld      de, HO_RD_ADDR
rd_seek:        out     (RD_PAGE), a
                ld      b, d
                ld      c, RD_ADDR
                out     (c), e
                ret
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
rd_in:          ld      c, RD_DATA
ri_1:           ld      a, d
                or      a
                jr      z, ri_2
                ld      b, 0
                inir
                dec     d
                jr      ri_1
ri_2:           ld      a, e
                or      a
                ret     z
                ld      b, a
                inir
                ret

; the decompressed block must end at HL + raw length (DE = the decoder's end)
rec_check:      ld      bc, (r_raw)
                add     hl, bc
                or      a
                sbc     hl, de
                ret     z
                ld      hl, msg_data
                jp      fatal

rd_refuse:      ld      hl, msg_rd1
                call    print_at
                ld      hl, msg_rd2
                call    print_at
rd_stop:        jr      rd_stop         ; (harness breakpoint: the RAM disk is too small)
fd_fail:
                if      defined DIAG
                call    dg_show
                endif
                ld      hl, msg_disk
fatal:          call    print_at
                xor     a
                out     (FD_MOTOR), a
fatal_stop:     jr      fatal_stop

                include "unpz.asm"

; ---------------------------------------------------------------- data stream (the files' blocks, a track at a time)
; s_next_file: continue with the next file of the table dir_scan built
s_next_file:    ld      a, (f_idx)
                ld      hl, f_cnt
                cp      (hl)
                jp      nc, data_err
                inc     a
                ld      (f_idx), a
                dec     a
                add     a, a
                add     a, a
                ld      e, a
                ld      d, 0
                ld      hl, f_tab
                add     hl, de
                ld      de, s_blk       ; s_blk, s_left = start block, block count
                ld      bc, 4
                ldir
                ld      hl, 0
                ld      (t_left), hl
                ret

; s_byte: A = the next byte of the stream
s_byte:         ld      de, s_tmp
                ld      bc, 1
                call    s_get
                ld      a, (s_tmp)
                ret

; s_get: copy BC bytes of the stream to DE
s_get:          ld      a, (s_src)
                or      a
                jr      nz, s_get_rd
sg_0:           ld      a, b
                or      c
                ret     z
                ld      hl, (t_left)
                ld      a, h
                or      l
                jr      nz, sg_1
                push    de
                push    bc
                call    s_fill
                pop     bc
                pop     de
                ld      hl, (t_left)
sg_1:           or      a               ; HL = t_left - wanted
                sbc     hl, bc
                jr      c, sg_part
                ld      (t_left), hl    ; all of it from this track
                ld      hl, (t_ptr)
                ldir
                ld      (t_ptr), hl
                ret
sg_part:        add     hl, bc          ; HL = t_left: take it all, the rest from the next track
                push    bc
                ld      b, h
                ld      c, l
                ex      (sp), hl        ; HL = wanted, (sp) = t_left
                or      a
                sbc     hl, bc
                ex      (sp), hl        ; (sp) = wanted - t_left
                ld      hl, (t_ptr)
                ldir
                ld      (t_ptr), hl
                ld      hl, 0
                ld      (t_left), hl
                pop     bc
                jr      sg_0
s_get_rd:       ex      de, hl          ; the RAM disk: at its current address
                ld      d, b
                ld      e, c
                jp      rd_in

; s_fill: read the next run of the current file's blocks that lies in one track into TRKBUF
s_fill:         ld      hl, (s_left)
                ld      a, h
                or      l
                jp      z, data_err
                ld      a, (s_blk)      ; first sector = block mod 16 + 1, at most 16 - block mod 16 sectors
                and     15
                ld      e, a
                inc     e
                neg
                add     a, 16
                ld      d, a
                ld      a, h
                or      a
                jr      nz, sf_1
                ld      a, l
                cp      d
                jr      nc, sf_1
                ld      d, l            ; fewer blocks left in the file
sf_1:           ld      hl, (s_blk)     ; logical track = block / 16 (blocks 0-1279)
                add     hl, hl
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      a, h
                ld      hl, TRKBUF
                call    fd_read_rot
                ld      a, d            ; t_left = sectors * 256, the block counters
                ld      h, a
                ld      l, 0
                ld      (t_left), hl
                ld      hl, TRKBUF
                ld      (t_ptr), hl
                ld      hl, (s_blk)
                ld      e, d
                ld      d, 0
                add     hl, de
                ld      (s_blk), hl
                ld      hl, (s_left)
                or      a
                sbc     hl, de
                ld      (s_left), hl
                ret
data_err:       ld      hl, msg_data
                jp      fatal

; ---------------------------------------------------------------- FSMZ directory
; dir_read: the directory's first block (block 16 = logical track 1, sector 1: its 8 entries hold every file the boot
; looks up, tools/mkgamedisk.py checks it) into TRKBUF. One sector: the track is almost all FFh (empty entries), the
; densest flux, which the MZPico floppy firmware's capture window does not fully cover (docs/research/mz800-hardware.md)
dir_read:       ld      a, 1
                ld      de, 0x0101      ; 1 sector from sector 1
                ld      hl, TRKBUF
                jp      fd_read_retry
; dir_find: DE = file name (CR-terminated) -> Z = found: HL = start block, BC = block count. 32-byte entries: +0 type,
; +1 name (CR-terminated), +0x14 size, +0x1E start block
dir_find:       ld      hl, TRKBUF
                ld      b, 8            ; (one block of entries)
df_ent:         push    bc
                push    hl
                push    de
                inc     hl
df_cmp:         ld      a, (de)
                cp      (hl)
                jr      nz, df_next
                inc     hl
                inc     de
                cp      0x0d
                jr      nz, df_cmp
                pop     de              ; found (DE is not kept)
                pop     hl
                pop     bc
                ld      de, 0x14        ; blocks = (size + 255) / 256
                add     hl, de
                ld      a, (hl)
                inc     hl
                add     a, 0xff
                ld      a, (hl)
                adc     a, 0
                ld      c, a
                sbc     a, a
                neg
                ld      b, a
                ld      e, 0x1e - 0x15  ; the start block
                add     hl, de
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a
                xor     a
                ret
df_next:        pop     de
                pop     hl
                ld      bc, 32
                add     hl, bc
                pop     bc
                djnz    df_ent
                or      1               ; NZ: not there
                ret
; dir_scan: f_tab from the entries POP800.D1, POP800.D2, ... (the directory in TRKBUF)
dir_scan:       xor     a
                ld      (f_cnt), a
                ld      (f_idx), a
                ld      a, '1'
                ld      (f_name + 8), a
                ld      ix, f_tab
ds_file:        ld      de, f_name
                call    dir_find
                jr      nz, ds_end
                ld      (ix + 0), l
                ld      (ix + 1), h
                ld      (ix + 2), c
                ld      (ix + 3), b
                ld      de, 4
                add     ix, de
                ld      hl, f_name + 8  ; next name
                inc     (hl)
                ld      hl, f_cnt
                inc     (hl)
                ld      a, (hl)
                cp      F_MAX
                jr      c, ds_file
                ret
ds_end:         ld      a, (f_cnt)      ; no more files
                or      a
                ret     nz
                jp      data_err

; ---------------------------------------------------------------- WD2793 (sequences as in the ROM IPL, E4DCh-E660h)
fd_init:        ld      a, 0x84         ; drive 0 (the IPL's), motor on
                out     (FD_MOTOR), a
                ld      hl, fd_on       ; 0: it was stopped
                xor     a
                or      (hl)
                ld      (hl), h         ; (nonzero: it runs from now on)
                jr      nz, fi_0
                ld      b, 16           ; the spin-up: 16 x ~60 ms = ~0.97 s, as the ROM (E517h). Whatever READY says:
fi_sp:          call    delay_long      ; a PC drive reports it at once or has none (its pin 34 may be DISKCHG), and
                djnz    fi_sp           ; reads fail while the disk is still speeding up
fi_0:           ld      hl, 0
fi_1:           dec     hl              ; wait for READY (status bit 7 low)
                ld      a, h
                or      l
                jp      z, fd_fail
                in      a, (FD_CMD)
                cpl
                rlca
                jr      c, fi_1
                ld      a, 0xff
                ld      (fd_cyl), a
                ret

; fd_read_retry: A = logical track (block / 16), E = first sector (1-16), D = sectors, HL = buffer; up to 6 tries,
; after a failed one a restore (fd_cmd waits for it however far the head steps), ~0.3 s for a slow drive to settle,
; then the seek again; then "DISK ERROR". A bad track: about 6 x (1.3 s + 2 x its cylinder x 30 ms) at most. Keeps D, E,
; HL.
fd_read_retry:
                if      defined DIAG
                ld      (dg_trk), a     ; (the call: track, first sector, sectors; the tries' statuses from dg_sts)
                ld      (dg_sec), de
                push    hl
                ld      hl, dg_sts
                ld      (dg_p), hl
                pop     hl
                endif
                ld      b, 6
frr_1:          ld      c, a
                push    bc
                push    de
                push    hl
                call    fd_read
                if      defined DIAG
                push    af
                ld      a, d            ; (the sectors not read)
                ld      (dg_rem), a
                ld      hl, (dg_p)
                ld      a, (dg_st)
                ld      (hl), a
                inc     hl
                ld      (dg_p), hl
                pop     af
                endif
frr_rd:         jr      z, frr_ok       ; (tests/m5_floppy.py: a read's result, a spinning-up drive's failures)
                ld      a, 0x0b         ; restore (and its ~60 ms), ~240 ms more, then seek again
                call    fd_type1
                ld      b, 4
frr_w:          call    delay_long
                djnz    frr_w
                ld      a, 0xff
                ld      (fd_cyl), a
                or      a               ; NZ
frr_ok:         pop     hl
                pop     de
                pop     bc
                ret     z
                ld      a, c
                djnz    frr_1
                jp      fd_fail

; fd_read_rot: as fd_read_retry (A = logical track, E = first sector, D = sectors, HL = the buffer for sector E; keeps
; D), but starting with the sector under the head: READ ADDRESS gives the ID field passing now (sector s); when s + 1
; lies inside the run, the sectors s + 1 .. end are read first (to their places in the buffer), then E .. s, both
; without the 15 ms settle delay (the head is loaded), so a track costs about one turn instead of 1.5 on average. Any
; READ ADDRESS trouble: the plain read. (mz800emu has no rotation: its READ ADDRESS reports the first sector of the
; track, or the last one read, with the ID bytes in another order: only the result is checked there, tests/m5_boot.py.)
fd_read_rot:    ld      (rot_trk), a
                push    de
                push    hl
                call    rot_addr
                pop     hl
                pop     de
                jr      nz, rot_plain
                ld      a, (rot_id + 2) ; WD ID field: track, side, sector, length, CRC (2); read through the
                cpl                     ; inverted bus (the IDs on the disk are true values)
                inc     a
                sub     e               ; k = s + 1 - E: the sectors to read last
                jr      z, rot_plain
                jr      c, rot_plain
                cp      d
                jr      nc, rot_plain
                ld      c, a
                ld      a, 0x90         ; read sectors, multiple, no settle delay
                ld      (fd_rcmd), a
                push    de
                push    hl
                push    bc
                ld      a, e            ; first E + k .. E + D - 1 at HL + 256 k
                add     a, c
                ld      e, a
                ld      a, d
                sub     c
                ld      d, a
                ld      a, h
                add     a, c
                ld      h, a
                ld      a, (rot_trk)
                call    fd_read_retry
                pop     bc
                pop     hl
                pop     de
                push    de
                ld      d, c            ; then E .. E + k - 1 at HL
                ld      a, (rot_trk)
                call    fd_read_retry
                pop     de
                ld      a, 0x94
                ld      (fd_rcmd), a
                ret
rot_plain:      ld      a, (rot_trk)
                jp      fd_read_retry
; rot_addr: READ ADDRESS on rot_trk (side and seek as for a read) into rot_id. Z = the 6 bytes and a clean status.
rot_addr:       ld      a, (rot_trk)
                call    fd_pos
                ret     nz
                ld      a, 0xc0         ; read address, no settle delay
                call    fd_go
                ret     nz
                ld      hl, rot_id
                ld      bc, 6 * 256 + FD_DATA
ra_byte:        in      a, (FD_CMD)
                rrca
                jr      c, ra_end
                rrca
                jr      c, ra_byte
                ini
                jr      nz, ra_byte
                ld      hl, 0
ra_wait:        in      a, (FD_CMD)     ; until it ends
                rrca
                jr      c, ra_end
                dec     hl
                ld      a, h
                or      l
                jr      nz, ra_wait
ra_end:         in      a, (FD_CMD)
                cpl
                and     0x99            ; not ready, record not found, CRC, busy
                or      b               ; (all 6 bytes)
                ret

                include "fdc.asm"           ; fd_read, fd_cmd, fd_type1, the delays (shared with the save overlay)

; ---------------------------------------------------------------- RAM disk probe
; The size of the RAM disk (docs/ramdisk-tiers.md section 1): a 2-byte marker (p, p xor 0x5A) at offset 0 of each page p,
; written from page 255 down to 0 (a card that ignores the high page bits aliases page p to a lower page, whose later
; write replaces the marker; a page with no memory behind it does not keep one), then read back from page 0 up: the
; pages up to the first wrong marker are the RAM disk. rd_top = its last page (7 = 512 KB, 15 = 1 MB, 255 = 16 MB; the
; launcher hands it to the programs it starts, launch.inc HO_RDTOP). The original bytes are saved in TRKBUF (free until
; the directory is read) and put back. Z = 512 KB or more.
rd_probe:       in      a, (RD_RESET)
                ld      hl, TRKBUF      ; save offsets 0-1 of pages 0-255
                ld      d, 0
rp_1:           ld      a, d
                call    rd_at0
                in      a, (RD_DATA)
                ld      (hl), a
                inc     hl
                in      a, (RD_DATA)
                ld      (hl), a
                inc     hl
                inc     d
                jr      nz, rp_1
                ld      d, 255          ; the markers, 255 down to 0
rp_2:           ld      a, d
                call    rd_at0
                ld      a, d
                out     (RD_DATA), a
                xor     0x5a
                out     (RD_DATA), a
                dec     d
                ld      a, d
                inc     a
                jr      nz, rp_2
                ld      d, 0            ; read back: D = the first page without its marker
rp_3:           ld      a, d
                call    rd_at0
                in      a, (RD_DATA)
                cp      d
                jr      nz, rp_4
                ld      e, a
                in      a, (RD_DATA)
                xor     0x5a
                cp      e
                jr      nz, rp_4
                inc     d
                jr      nz, rp_3
                ld      a, 255          ; all 256 pages
                jr      rp_5
rp_4:           ld      a, d            ; the page before D (D = 0, no RAM disk: 0, refused below)
                sub     1
                adc     a, 0
rp_5:           ld      (rd_top), a
                ld      d, 255          ; put the bytes back, 255 down to 0 (an aliased page gets its own bytes last)
                ld      hl, TRKBUF + 511
rp_6:           ld      a, d
                call    rd_at0
                dec     hl
                ld      a, (hl)
                out     (RD_DATA), a
                inc     hl
                ld      a, (hl)
                out     (RD_DATA), a
                dec     hl
                dec     hl
                dec     d
                ld      a, d
                inc     a
                jr      nz, rp_6
                ld      a, (rd_top)
                cp      7               ; 8 pages or more
                sbc     a, a
                ret
rd_at0:         out     (RD_PAGE), a
                ld      bc, RD_ADDR     ; B = 0: address 0
                xor     a
                out     (c), a
                ret

; ---------------------------------------------------------------- screen
draw_on:        in      a, (0xe0)       ; VRAM at 0x8000-0x9FFF (and the CG ROM at 0x1000-0x1FFF); A destroyed
                ret
draw_off:       in      a, (0xe1)
                ret

video_init:     call    draw_on
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
                ld      a, 0x80         ; REPLACE, colour 0
                out     (PORT_WF), a
                ld      hl, VRAM
                ld      de, VRAM + 1
                ld      bc, 8000 - 1
                ld      (hl), 0xff
                ldir
                jr      draw_off

; print_at: HL = message: VRAM offset (word), colour (byte), text (0-terminated); 8 pixels per character
print_at:       call    draw_on
                ld      e, (hl)
                inc     hl
                ld      d, (hl)
                inc     hl
                ld      a, (hl)
                inc     hl
                or      0x80            ; REPLACE: 1 bits in the colour, 0 bits black
                out     (PORT_WF), a
pa_ch:          ld      a, (hl)
                inc     hl
                or      a
                jr      z, draw_off
                push    hl
                sub     0x20
                ld      l, a            ; glyph = font + 7 * (char - 0x20)
                ld      h, 0
                ld      b, h
                ld      c, l
                add     hl, hl
                add     hl, hl
                add     hl, hl
                sbc     hl, bc
                ld      bc, font
                add     hl, bc
                push    de
                ex      de, hl
                ld      bc, VRAM
                add     hl, bc
                ld      bc, 40
                ld      a, 7
pa_row:         ex      af, af'
                ld      a, (de)
                ld      (hl), a
                inc     de
                add     hl, bc
                ex      af, af'
                dec     a
                jr      nz, pa_row
                pop     de
                inc     de
                pop     hl
                jr      pa_ch

bar_init:       xor     a
                ld      (bar_cur), a
                ld      a, BAR_COL
                ld      b, 32
                ld      c, COL_BAR_BG
                jr      bar_fill
; bar_to: A = bar width in bytes (0-32): fills the bar up to it (only while bar_on)
bar_to:         ld      hl, bar_on
                inc     (hl)
                dec     (hl)
                ret     z
                ld      hl, bar_cur
                sub     (hl)
                ret     z
                ret     c
                ld      b, a
                ld      a, (hl)
                add     a, b
                ld      (hl), a
                sub     b
                add     a, BAR_COL
                ld      c, COL_BAR
; bar_fill: A = first byte column, B = bytes, C = colour
bar_fill:       ld      e, a
                ld      d, 0
                call    draw_on         ; (destroys A)
                ld      hl, VRAM + BAR_ROW * 40
                add     hl, de
                ld      a, c
                or      0x80
                out     (PORT_WF), a
                ld      de, 40
bf_col:         push    hl
                ld      c, 8
bf_row:         ld      (hl), 0xff
                add     hl, de
                dec     c
                jr      nz, bf_row
                pop     hl
                inc     hl
                djnz    bf_col
                jp      draw_off

msg_load:       dw      MSG_LOAD_AT
                db      7, "LOADING...", 0
msg_rd1:        dw      112 * 40 + 4
                db      10, "SORRY, THIS GAME NEEDS A 512 KB", 0
msg_rd2:        dw      124 * 40 + 4
                db      10, "RAM DISK (MZ-1R18 OR COMPATIBLE).", 0
                if      defined DIAG
; dg_show (the diagnostic build): under DISK ERROR three lines of hex, each byte after its letter:
;   T track (logical: cylinder x 2 + side) S first sector N sectors C command R sectors not read W who (FF the boot,
;   else the POP800.PRS entry, 80h = PRS_KEEP), P the RAM disk's last page (07 = 512 KB), V its read speed (clocks
;   per byte x 5: 69h = 21.0 = 0 WS, + 5 a wait state); K the WD's track register, Q its sector register; I the last READ
;   ADDRESS's six ID bytes as read (inverted: cylinder = FF - I1, side FF - I2, sector FF - I3); 1-6 the WD status
;   (true bits) after each try (seek: 80 not ready, 10 seek error, 01 busy; read: 80 not ready, 10 record not found,
;   08 CRC, 04 lost data; EE the command did not start)
dg_show:        ld      hl, (rd_top)    ; (rd_top, rd_spd)
                ld      (dg_top), hl
                ld      hl, dg_trk
                ld      ix, dg_l1
                call    dg_line
                call    dg_line
dg_line:        ld      e, (ix + 0)     ; IX: offset (word), count, the letters; HL: the bytes
                ld      d, (ix + 1)
                ld      (dg_buf), de
                ld      a, 10
                ld      (dg_buf + 2), a
                ld      b, (ix + 2)
                inc     ix
                inc     ix
                inc     ix
                ld      de, dg_buf + 3
dgl_1:          ld      a, (ix + 0)
                inc     ix
                ld      (de), a
                inc     de
                ld      a, (hl)
                inc     hl
                push    af
                rrca
                rrca
                rrca
                rrca
                call    dg_nib
                pop     af
                call    dg_nib
                ld      a, ' '
                ld      (de), a
                inc     de
                djnz    dgl_1
                xor     a
                ld      (de), a
                push    hl
                ld      hl, dg_buf
                call    print_at
                pop     hl
                ret
dg_nib:         and     15
                add     a, 0x90
                daa
                adc     a, 0x40
                daa
                ld      (de), a
                inc     de
                ret
dg_l1:          dw      150 * 40 + 4
                db      8, "TSNCRWPV"
                dw      160 * 40 + 4
                db      8, "KQIIIIII"
                dw      170 * 40 + 4
                db      6, "123456"
                endif
msg_disk:       dw      84 * 40 + 4
                db      10, "DISK ERROR", 0
msg_data:       dw      84 * 40 + 4
                db      10, "DATA ERROR", 0

                include "font.inc"

F_MAX           equ     8
f_name:         db      "POP800.D1", 0x0d
f_idx:          db      0
f_cnt:          db      0
ho_title:       dw      HO_MAGIC        ; the boot's handoff block: the title
                db      ACT_TITLE, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
ho_fill:        dw      HO_MAGIC        ; on 1 MB and more: the frame store's fill first (launch.inc ACT_FILL)
                db      ACT_FILL, 0
                dw      VRAM + BAR_ROW * 40 + BAR_COL
                db      32, COL_BAR, 0, 0, 0, 0, 0, 0, 0, 0
msg_prep:       dw      MSG_LOAD_AT     ; (msg_load's place)
                db      7, "PREPARING SPRITES", 0
rd_top:         db      0               ; the RAM disk's last page (rd_probe; in the image: the launcher's copy keeps it)
rd_spd:         db      0               ; its read speed: GAME clocks/byte x 5 (rd_speed, rdspeed.asm; as rd_top)
end_of_image:
                if end_of_image - LOAD > PRS_TAB_OFF
                .error the launcher's image is larger than its RAM-disk area (up to the POP800.PRS table)
                endif
LN_DUEL_USED    equ     ln_duel1_end - ln_duel1 + ln_duel2_end - ln_duel2      ; (ACT_DUEL's code: within the reserve)
                if end_of_image - LOAD - LN_DUEL_USED > PRS_TAB_OFF - LN_DUEL_RESERVE
                .error the launcher's image leaves less than LN_DUEL_RESERVE bytes for the duel (docs/duel-design.md 1.5)
                endif
; variables (not in the image)
f_tab:          ds      F_MAX * 4       ; start block, block count
s_blk:          ds      2
s_left:         ds      2
t_ptr:          ds      2
t_left:         ds      2
s_tmp:          ds      1
fd_cyl:         ds      1
rot_trk:        ds      1
                if      defined DIAG    ; (dg_show prints dg_trk .. dg_sts in this order)
dg_trk:         ds      1
dg_sec:         ds      1
dg_cnt:         ds      1
dg_cmd:         ds      1
dg_rem:         ds      1
dg_who:         ds      1
dg_top:         ds      1               ; (rd_top: 07 = 512 KB, 0F = 1 MB)
dg_spd:         ds      1               ; (rd_spd: clocks/byte x 5; 105 = 0 WS, + 5 a wait state)
dg_wtrk:        ds      1
dg_wsec:        ds      1
                endif
rot_id:         ds      6
                if      defined DIAG
dg_sts:         ds      6
dg_st:          ds      1
dg_p:           ds      2
dg_buf:         ds      40
                endif
r_kind:         ds      1
r_addr:         ds      2
r_raw:          ds      2
r_pay:          ds      2
r_bar:          ds      1
up_neg:         ds      2
bar_cur:        ds      1
s_src:          ds      1               ; the stream: 0 the floppy, 1 the RAM disk
bar_on:         ds      1               ; the progress bar is drawn (the boot)
fd_on:          ds      1               ; (bar_on's next byte) the motor runs (fd_init: 0 = it waits for the spin-up)
ho_buf:         ds      HO_SIZE         ; the handoff block as read by the launcher
end_of_vars:
                if end_of_vars > STACK - 0x100
                .error loader variables run into the stack
                endif
; the boot only (not in the image): rd_speed (src/boot/rdspeed.asm) and boot_screen (src/boot/bootscr.asm), assembled over the variables above (the later
; bytes win in the binary): it runs before any of them is used
                org     end_of_image
                include "rdspeed.asm"
                include "bootscr.asm"
end_of_boot:
BOOT_STACK      equ     0x40            ; the stack while the boot-only code runs (boot_screen, rd_speed, net_line: at
                                        ; most ~20 bytes deep, tests/m5_boot.py measures it); after rd_speed the
                                        ; stack may grow into these bytes (dead code by then: STACK - 0x100 is the
                                        ; variables' limit above)
                if end_of_boot > STACK - BOOT_STACK
                .error the boot-only code runs into its stack
                endif
