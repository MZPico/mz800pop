; pop-800 floppy loader (M5) and launcher (M7): the IPLPRO bootstrap of build/pop800.dsk (tools/mkgamedisk.py builds
; the disk). The ROM IPL reads it to 0x1200, moves it to LOAD and jumps to `boot`. It
;   1. switches to 320x200/16 colours and shows the title and a progress bar,
;   2. probes the RAM disk (MZ-1R18 / STD protocol, ports E9-EB, F8): pages 0-7 must be distinct (512 KB or more),
;      else it shows a message and stops (rd_refuse); it measures the RAM disk's read speed (rd_speed, rdspeed.asm: a
;      table on the loading screen; too slow, or a timer that cannot be right: a message and a stop at rs_stop);
;      then it copies its own image to the RAM disk (LN_RD_PAGE:
;      LN_RD_ADDR, launch.inc): that copy is the launcher the game loads to swap itself out,
;   3. finds the data files POP800.D1, D2, ... in the FSMZ directory and reads them with its own WD2793 code
;      (multi-sector reads of whole tracks, as the ROM IPL does them),
;   4. decompresses the records (tools/mkgamedisk.py: the stream format; tools/pzpack.py: the PZ format) into the
;      RAM disk: the art, the overlays and the game's compressed image (a record stream itself, GAME_RD_PAGE:ADDR),
;   5. writes the handoff block "title" and launches (launch_main): PRES from POP800.PRS, which starts the game.
; The launcher (launch.inc: the interface and the handoff block) is entry LN_LAUNCH: it reads the handoff block from
; the RAM disk, zeroes 0x0000-0x11FF, copies the block to HO_MAIN and starts the GAME (its image decompressed from the
; RAM disk, ~0.5 s) or PRES (entry 0 of POP800.PRS from the floppy). LN_PRS_LOAD loads any POP800.PRS entry for PRES.
; Memory while loading: TRKBUF one track, OUTBUF/INBUF1 the RAM-disk records' buffers (boot only), INBUF2 the
; main-RAM records' input (their output goes straight to its place), the loader and its stack at 0xB000-0xBFFF.
; VRAM (0x8000-0x9FFF) and the CG ROM (0x1000-0x1FFF) are mapped only while drawing (draw_on / draw_off).

                include "launch.inc"
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

                org     LOAD
boot:           jp      boot_main       ; the ROM IPL's entry
launch:         jp      launch_main     ; LN_LAUNCH
prs_load:       jp      prs_load_main   ; LN_PRS_LOAD
                if launch - LN_LAUNCH
                .error the launcher's entries moved
                endif
                if prs_load - LN_PRS_LOAD
                .error the launcher's entries moved
                endif
boot_main:      di
                ld      sp, STACK
                out     (0xe0), a       ; RAM at 0x0000-0x0FFF
                out     (0xe1), a       ; RAM at 0xE000-0xFFFF
                call    psg_off         ; (M7: the PSG muted before the floppy reads with interrupts off)
                call    zero_low
                call    video_init
                ld      hl, msg_title
                call    print_at
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
                ld      a, 1
                ld      (bar_on), a
                call    bar_init
                call    fd_init
                call    dir_read
                call    dir_scan
                xor     a
                ld      (s_src), a
                call    s_next_file
                call    load_stream
                ld      a, HO_RD_PAGE   ; the handoff block: the title
                ld      de, HO_RD_ADDR
                call    rd_seek
                ld      hl, ho_title
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
                xor     a
                ld      (bar_on), a
                ld      a, HO_RD_PAGE
                ld      de, HO_RD_ADDR
                call    rd_seek
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
                jp      GAME_START
ln_pres:        xor     a               ; PRES: entry 0 of POP800.PRS
                call    prs_load_main
                jp      PRES_START

; prs_load_main (LN_PRS_LOAD): A = entry of POP800.PRS: its record stream (main-RAM records only) into main RAM.
; POP800.PRS (tools/mkgamedisk.py): block 0 = the index: entry count (word), then per entry the first block (word,
; from the start of the file) and the block count (word); entry 0 is PRES, the others the scenes. Interrupts off,
; the motor off at the end. Uses TRKBUF, INBUF2 and the launcher's own memory (0xA000-0xBFFF, 0x8000-0x9FFF).
prs_load_main:  di
                push    af
                call    psg_off         ; (M7: the PSG muted before the floppy reads with interrupts off)
                xor     a
                ld      (s_src), a
                ld      (bar_on), a
                ld      (f_cnt), a      ; (no next file: a 0xFE record is a data error)
                ld      (f_idx), a
                call    fd_init
                call    dir_read
                ld      de, prs_name
                call    dir_find
                jp      nz, data_err
                ld      (s_blk), hl
                ld      a, l            ; the index: the file's first block
                and     15
                inc     a
                ld      e, a
                ld      a, l
                srl     h
                rra
                srl     h
                rra
                srl     h
                rra
                srl     h
                rra
                ld      d, 1
                ld      hl, TRKBUF
                call    fd_read_retry
                pop     af
                ld      hl, TRKBUF
                cp      (hl)
                jp      nc, data_err
                add     a, a
                add     a, a
                ld      e, a
                ld      d, 0
                ld      hl, TRKBUF + 2
                add     hl, de
                ld      e, (hl)
                inc     hl
                ld      d, (hl)
                inc     hl
                ld      c, (hl)
                inc     hl
                ld      b, (hl)
                ld      hl, (s_blk)
                add     hl, de
                ld      (s_blk), hl
                ld      (s_left), bc
                ld      hl, 0
                ld      (t_left), hl
                call    load_stream
                xor     a               ; motor off
                out     (FD_MOTOR), a
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

; rd_seek: A = RAM-disk page, DE = address. rd_out: HL = source, DE = count: to the RAM disk. rd_in: HL = destination,
; DE = count: from the RAM disk.
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
fd_fail:        ld      hl, msg_disk
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
                ld      a, l
                srl     h
                rra
                srl     h
                rra
                srl     h
                rra
                srl     h
                rra
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
; dir_read: the directory (blocks 16-23 = logical track 1, sectors 1-8) into TRKBUF
dir_read:       ld      a, 1
                ld      de, 0x0801      ; 8 sectors from sector 1
                ld      hl, TRKBUF
                jp      fd_read_retry
; dir_find: DE = file name (CR-terminated) -> Z = found: HL = start block, BC = block count. 32-byte entries: +0 type,
; +1 name (CR-terminated), +0x14 size, +0x1E start block
dir_find:       ld      hl, TRKBUF
                ld      b, 64
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
                pop     de              ; found
                pop     hl
                pop     bc
                push    hl
                ld      bc, 0x14        ; blocks = (size + 255) / 256
                add     hl, bc
                ld      a, (hl)
                inc     hl
                add     a, 0xff
                ld      a, (hl)
                adc     a, 0
                ld      c, a
                ld      a, 0
                adc     a, 0
                ld      b, a
                pop     hl
                push    bc
                ld      bc, 0x1e
                add     hl, bc
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a
                pop     bc
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
                ld      hl, 0
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

; fd_read_retry: A = logical track (block / 16), E = first sector (1-16), D = sectors, HL = buffer;
; up to 4 tries (a restore before each retry), then "DISK ERROR". Keeps D.
fd_read_retry:  ld      b, 4
frr_1:          push    bc
                push    de
                push    hl
                push    af
                call    fd_read
                jr      z, frr_ok
                ld      a, 0x0b         ; restore, then seek again
                call    fd_type1
                ld      a, 0xff
                ld      (fd_cyl), a
                pop     af
                pop     hl
                pop     de
                pop     bc
                djnz    frr_1
                jp      fd_fail
frr_ok:         pop     af
                pop     hl
                pop     de
                pop     bc
                ret

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

msg_title:      dw      48 * 40 + 12
                db      COL_TEXT, "PRINCE OF PERSIA", 0
msg_load:       dw      100 * 40 + 4
                db      7, "LOADING...", 0
msg_rd1:        dw      112 * 40 + 4
                db      10, "SORRY, THIS GAME NEEDS A 512 KB", 0
msg_rd2:        dw      124 * 40 + 4
                db      10, "RAM DISK (MZ-1R18 OR COMPATIBLE).", 0
msg_disk:       dw      84 * 40 + 4
                db      10, "DISK ERROR", 0
msg_data:       dw      84 * 40 + 4
                db      10, "DATA ERROR", 0

                include "font.inc"

F_MAX           equ     8
f_name:         db      "POP800.D1", 0x0d
prs_name:       db      "POP800.PRS", 0x0d
f_idx:          db      0
f_cnt:          db      0
ho_title:       dw      HO_MAGIC        ; the boot's handoff block: the title
                db      ACT_TITLE, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
rd_top:         db      0               ; the RAM disk's last page (rd_probe; in the image: the launcher's copy keeps it)
rd_spd:         db      0               ; its read speed: GAME clocks/byte x 5 (rd_speed, rdspeed.asm; as rd_top)
end_of_image:
                if end_of_image - LOAD > LN_MAX
                .error the launcher's image is larger than its RAM-disk area
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
rot_id:         ds      6
r_kind:         ds      1
r_addr:         ds      2
r_raw:          ds      2
r_pay:          ds      2
r_bar:          ds      1
up_neg:         ds      2
bar_cur:        ds      1
s_src:          ds      1               ; the stream: 0 the floppy, 1 the RAM disk
bar_on:         ds      1               ; the progress bar is drawn (the boot)
ho_buf:         ds      HO_SIZE         ; the handoff block as read by the launcher
end_of_vars:
                if end_of_vars > STACK - 0x100
                .error loader variables run into the stack
                endif
; the boot only (not in the image): rd_speed (src/boot/rdspeed.asm), assembled over the variables above (the later
; bytes win in the binary): it runs before any of them is used
                org     end_of_image
                include "rdspeed.asm"
end_of_boot:
                if end_of_boot > STACK - 0x100
                .error rd_speed runs into the stack
                endif
