; ---------------------------------------------------------------- RAM-disk read speed (the boot only)
; rd_speed (after rd_probe, before the launcher's copy: rd_spd is in the launcher's image) times reads from the RAM disk
; against the 8253's counter 0 and shows the result on the loading screen; a RAM disk too slow (or a measurement that
; cannot be right) stops the boot with a message (docs/ramdisk-tiers.md section 1).
;
; The clock: counter 0, CLK0 = 17.734475 MHz / 16 (the same crystal as the CPU's 17.734475 MHz / 5), so one count is
; exactly 3.2 CPU clock periods of real time, whatever WAIT does to the CPU. Mode 2, 65536, GATE0 = 1 (0xE008 bit 0
; with the ROM's I/O area at 0xE000: OUT E3h, then OUT E1h back), counting down for the whole measurement (59 ms a
; turn; every interval is far shorter, a 16-bit difference is right across the turn); its audio muted meanwhile (8255
; PC0 = 0, put back after). Read: latch (control 0x00), LSB, MSB. Interrupts are off (the boot runs under DI).
;
; What is timed (tm_op): from one latch to the next, the timed routine in between (op_chunk, op_run: the address OUT on EBh and
; an INIR of n bytes, the game's way of reading the RAM disk: set the address, INIR). The fixed cost around it is
; measured (rs_cal: 16 runs of the same frame with an empty routine, sum rs_s) and the routine's own nominal cost
; besides the 21 clocks a byte is subtracted as worked out (42 clocks: ld hl / ld b,d / ld c / OUT (C),E / ld c / ld b,
; INIR's last byte 16): "clocks/byte" = 21 + (the measured clocks - the nominal clocks) / n, so a RAM disk without wait
; states shows 21.0 and every wait clock, on the data reads or on the address OUT, adds 1 / n. Per area of the RAM disk:
;   - 16 chunks of 128 bytes aligned to 128 (base + k * 512) and 16 misaligned by 64 (base + k * 512 + 320), each at
;     an address no other chunk touched: a RAM disk with a 128-byte window (MZPico: a file behind an SD window) misses
;     once on an aligned chunk and twice on a misaligned one; MIN / MAX / AVG over all 32, ALIGN / MISAL the averages;
;   - GAME: 32 runs of the game's pattern, the address set and a 32-byte INIR, at scattered addresses (0x0123 + k *
;     0x0753, all over the page); the average.
; Areas: page 0 (base 0x0000), the last 8 KB (base 0xE000) of page 7 (the end of the 512 KB layout), of the middle page
; (rd_top / 2 + 1) and of the last page (rd_top), in page order, each once. Reads only (to TRKBUF): nothing changes.
; Precision: a count is 3.2 clocks; a single chunk is good to +-0.03 clocks/byte, the averages better (the 16 counts of
; the calibration: +-0.2 clocks of the fixed cost). Time: 5 KB an area, ~0.04 s an area without waits (0.15 s for 4).
;
; The stop: the GAME average over the areas above RD_SPEED_MAX or below RD_SPEED_MIN (faster than an INIR can be: the
; timer is wrong) shows the message and halts (rs_stop): no launch, nothing more loaded. Both are words of the boot's
; image (rd_max, rd_min: tests/m5_boot.py patches them). rd_spd (-> HO_RDSPD_MAIN) = the GAME average x 5.
; RD_SPEED_MAX = 36.0 clocks/byte (user, 2026-11-03): where RAM-disk waits slow the kid's walk by about 10 %. Measured
; (#19, tools/rdreads.py, mr1r18_wait): 1 T of wait on every RAM-disk port access costs +0.035 frames a tick walking
; (~2,700 accesses a tick), so 10 % of a ~5.2-frame tick is ~15 waits; the GAME pattern reads 21 + w + w/32, 15 -> 36.5.
RD_SPEED_MAX    equ     360             ; clocks/byte x 10: the slowest GAME average the boot accepts
RD_SPEED_MIN    equ     150             ; and the fastest (15.0)
PORT_CTC0       equ     0xd4            ; 8253 counter 0 (CLK0 = 1.108 MHz)
PORT_PPIC       equ     0xd2            ; 8255 port C (PC0: the CTC0 audio, 0 = muted)
PORT_PPICTL     equ     0xd3
RS_CHUNK        equ     128
RS_RUN          equ     32
RS_KC           equ     178             ; chunk: 42 clocks x 10 / 128 x 64 (the X scale) - 32 (rounding)
RS_KG           equ     202             ; game run: 42 x 10 / 32 x 16 - 8
RS_AREA         equ     12              ; rs_res an area: MIN, MAX, ALIGN, MISAL, GAME, AVG (words, clocks/byte x 10)
; the variables: in TRKBUF (free until the directory is read; the reads use its first 256 bytes), not in the image
RSV             equ     TRKBUF + 0x200
rs_n            equ     RSV             ; the areas measured, their pages, their results
rs_pg           equ     RSV + 1         ; (4)
rs_res          equ     RSV + 5         ; (4 x RS_AREA)
rs_s            equ     RSV + 53        ; the fixed cost of a timing (16 x counts)
rs_cav          equ     RSV + 55        ; the means over the areas: chunk AVG, GAME
rs_gav          equ     RSV + 57
rs_pc0          equ     RSV + 59        ; 8255 port C before
rs_rp           equ     RSV + 60
rs_pa           equ     RSV + 62        ; rs_area: the page, the base's high byte, a counter, the sums, MIN, MAX, the
rs_bh           equ     RSV + 63        ; game pattern's address
rs_k            equ     RSV + 64
rs_sa           equ     RSV + 65
rs_sm           equ     RSV + 67
rs_sg           equ     RSV + 69
rs_mn           equ     RSV + 71
rs_mx           equ     RSV + 73
rs_ga           equ     RSV + 75
rs_t0           equ     RSV + 77
rs_mode         equ     RSV + 79        ; the stop: 1 too slow, 0 the timer; the worst area's page and value
rs_wp           equ     RSV + 80
rs_wv           equ     RSV + 82
pd_any          equ     RSV + 86        ; put_dec: a digit written
rs_txt          equ     RSV + 95        ; (44) a text line for print_at

rd_speed:       in      a, (PORT_PPIC)  ; mute the CTC0 audio, start counter 0
                ld      (rs_pc0), a
                xor     a
                out     (PORT_PPICTL), a        ; (bit reset: PC0 = 0)
                ld      a, 0x34                 ; counter 0, LSB + MSB, mode 2 (a rate generator)
                out     (PORT_CTCC), a
                xor     a
                out     (PORT_CTC0), a
                out     (PORT_CTC0), a
                out     (0xe3), a               ; GATE0 = 1 (0xE008, the ROM's I/O area)
                ld      a, 1
                ld      (0xe008), a
                out     (0xe1), a
                ld      ix, rs_cal              ; the fixed cost: 16 empty runs
                ld      hl, 0
                ld      b, 16
rs_c1:          push    bc
                push    hl
                call    tm_op
                pop     de
                add     hl, de
                pop     bc
                djnz    rs_c1
                ld      (rs_s), hl
                ld      hl, rs_pg               ; the areas' pages: 0, then 7, the middle and the last in order
                xor     a
                ld      (hl), a
                inc     hl
                ld      a, (rd_top)
                srl     a
                inc     a
                ld      b, a                    ; B = the middle page
                cp      7
                jr      c, rs_a1
                ld      a, 7
                call    rs_add
                ld      a, b
                call    rs_add
                jr      rs_a2
rs_a1:          call    rs_add
                ld      a, 7
                call    rs_add
rs_a2:          ld      a, (rd_top)
                call    rs_add
                ld      de, rs_pg
                or      a
                sbc     hl, de
                ld      a, l
                ld      (rs_n), a
                ld      hl, rs_res
                ld      (rs_rp), hl
                ld      hl, rs_pg
rs_m:           ld      a, (hl)
                push    hl
                ld      h, 0                    ; page 0 from 0x0000, the others' last 8 KB
                or      a
                jr      z, rs_m1
                ld      h, 0xe0
rs_m1:          call    rs_area
                pop     hl
                inc     hl
                ld      a, (rs_n)
                ld      b, a
                ld      a, l
                sub     low rs_pg
                cp      b
                jr      c, rs_m
                ld      a, (rs_pc0)             ; the CTC0 audio as it was, GATE0 = 0 (counter 0 stops)
                and     1
                out     (PORT_PPICTL), a
                out     (0xe3), a
                xor     a
                ld      (0xe008), a
                out     (0xe1), a
                ld      hl, rs_res + 10         ; the averages over the areas: chunk AVG, GAME
                call    rs_mean
                ld      (rs_cav), hl
                ld      hl, rs_res + 8
                call    rs_mean
                ld      (rs_gav), hl
                inc     hl                      ; the handoff byte: GAME clocks/byte x 5 (rounded; 255 at most)
                srl     h
                rr      l
                ld      a, h
                or      a
                ld      a, l
                jr      z, rs_h2
                ld      a, 255
rs_h2:          ld      (rd_spd), a
                call    rs_show
                call    net_line                ; (bootscr.asm: the network line under it)
                ld      hl, (rs_gav)            ; the stop
                ld      de, (rd_max)
                ex      de, hl
                or      a
                sbc     hl, de                  ; max - average: carry = too slow
                jr      c, rs_slow
                ld      hl, (rs_gav)
                ld      de, (rd_min)
                or      a
                sbc     hl, de
                ret     nc
                ld      hl, s_fault             ; below the minimum: the timer cannot be right
                ld      bc, (rd_min)
                xor     a                       ; (the fastest area)
                jr      rs_err
rs_slow:        ld      hl, s_slow
                ld      bc, (rd_max)
                ld      a, 1                    ; (the slowest area)
rs_err:         ld      (rs_mode), a
                push    bc
                push    hl
                ld      hl, 80 * 40 + 1
                call    rs_line
                ld      a, 10
                ld      (rs_txt + 2), a
                pop     hl
                call    put_str
                ld      hl, (rs_gav)
                call    put_t10
                ld      hl, s_cpb
                call    put_str
                call    rs_print
                ld      hl, 90 * 40 + 0
                call    rs_line
                ld      a, 10
                ld      (rs_txt + 2), a
                ld      hl, s_limit
                call    put_str
                ld      hl, s_min
                ld      a, (rs_mode)
                or      a
                jr      z, re_0
                ld      hl, s_max
re_0:           call    put_str
                pop     hl
                call    put_t10
                ld      hl, s_worst
                call    put_str
                push    de
                ld      ix, rs_res              ; the worst area: the largest GAME (too slow) or the smallest
                ld      hl, rs_pg
                ld      (rs_wp), hl
                ld      e, (ix + 8)
                ld      d, (ix + 9)
                ld      (rs_wv), de
                ld      a, (rs_n)
                ld      b, a
re_1:           ld      e, (ix + 8)
                ld      d, (ix + 9)
                push    hl
                ld      hl, (rs_wv)
                ld      a, (rs_mode)
                or      a
                jr      z, re_2
                sbc     hl, de                  ; (CF = 0) wv - this: carry = this is larger
                pop     hl
                jr      nc, re_4
                jr      re_3
re_2:           ex      de, hl
                push    hl
                sbc     hl, de                  ; this - wv: carry = this is smaller
                pop     de
                pop     hl
                jr      nc, re_4
re_3:           ld      (rs_wv), de
                ld      (rs_wp), hl
re_4:           inc     hl
                ld      de, RS_AREA
                add     ix, de
                djnz    re_1
                pop     de
                ld      a, 'P'
                ld      (de), a
                inc     de
                ld      hl, (rs_wp)
                ld      l, (hl)
                ld      h, 0
                call    put_dec
                ld      a, ' '
                ld      (de), a
                inc     de
                ld      hl, (rs_wv)
                call    put_t10
                call    rs_print
                xor     a                       ; the motor off, halt
                out     (FD_MOTOR), a
rs_stop:        jr      rs_stop                 ; (harness breakpoint: the RAM disk is too slow)

; rs_area: A = page, H = the base's high byte: one area's six results to (rs_rp), which advances
rs_area:        ld      (rs_pa), a
                ld      a, h
                ld      (rs_bh), a
                ld      hl, 0
                ld      (rs_sa), hl
                ld      (rs_sm), hl
                ld      (rs_sg), hl
                ld      (rs_mx), hl
                dec     hl
                ld      (rs_mn), hl
                ld      ix, op_chunk
                xor     a
                ld      (rs_k), a
ra_1:           ld      a, (rs_k)               ; aligned: base + k * 512
                add     a, a
                ld      hl, rs_bh
                add     a, (hl)
                ld      d, a
                ld      e, 0
                call    rs_chunk
                ld      de, (rs_sa)
                add     hl, de
                ld      (rs_sa), hl
                ld      a, (rs_k)               ; misaligned: base + k * 512 + 320
                add     a, a
                ld      hl, rs_bh
                add     a, (hl)
                inc     a
                ld      d, a
                ld      e, 0x40
                call    rs_chunk
                ld      de, (rs_sm)
                add     hl, de
                ld      (rs_sm), hl
                ld      hl, rs_k
                inc     (hl)
                ld      a, (hl)
                cp      16
                jr      c, ra_1
                ld      ix, op_run              ; the game's pattern
                ld      hl, 0x0123
                ld      (rs_ga), hl
                xor     a
                ld      (rs_k), a
ra_2:           ld      de, (rs_ga)
                call    tm_one
                ld      de, 2048                ; (at most 2047 counts a run)
                call    rs_clamp
                ld      de, (rs_sg)
                add     hl, de
                ld      (rs_sg), hl
                ld      hl, (rs_ga)
                ld      de, 0x0753
                add     hl, de
                ld      (rs_ga), hl
                ld      hl, rs_k
                inc     (hl)
                ld      a, (hl)
                cp      32
                jr      c, ra_2
                ld      ix, (rs_rp)             ; the results
                ld      hl, (rs_mn)             ; MIN, MAX: X = 16 x counts
                call    x16
                call    cv_chunk
                ld      (ix + 0), l
                ld      (ix + 1), h
                ld      hl, (rs_mx)
                call    x16
                call    cv_chunk
                ld      (ix + 2), l
                ld      (ix + 3), h
                ld      hl, (rs_sa)             ; ALIGN, MISAL: X = the sum of 16
                call    cv_chunk
                ld      (ix + 4), l
                ld      (ix + 5), h
                ld      hl, (rs_sm)
                call    cv_chunk
                ld      (ix + 6), l
                ld      (ix + 7), h
                ld      hl, (rs_sa)             ; AVG: X = the sum of 32 / 2
                ld      de, (rs_sm)
                add     hl, de
                rr      h
                rr      l
                call    cv_chunk
                ld      (ix + 10), l
                ld      (ix + 11), h
                ld      hl, (rs_sg)             ; GAME: X = the sum of 32 / 2
                srl     h
                rr      l
                ld      de, (rs_s)
                or      a
                sbc     hl, de
                jr      c, ra_3
                ld      de, RS_KG
                sbc     hl, de
                jr      nc, ra_4
ra_3:           ld      hl, 0
ra_4:           srl     h                       ; / 16
                rr      l
                srl     h
                rr      l
                srl     h
                rr      l
                srl     h
                rr      l
                ld      (ix + 8), l
                ld      (ix + 9), h
                ld      de, RS_AREA
                add     ix, de
                ld      (rs_rp), ix
                ret
; rs_chunk: DE = address: one chunk's counts (HL, at most 4095), MIN / MAX updated
rs_chunk:       call    tm_one
                ld      de, 4096
                call    rs_clamp
                ex      de, hl
                ld      hl, (rs_mn)
                or      a
                sbc     hl, de
                jr      c, rk_1
                ld      (rs_mn), de
rk_1:           ld      hl, (rs_mx)
                or      a
                sbc     hl, de
                jr      nc, rk_2
                ld      (rs_mx), de
rk_2:           ex      de, hl
                ret
; rs_clamp: HL = min(HL, DE - 1)
rs_clamp:       push    hl
                or      a
                sbc     hl, de
                pop     hl
                ret     c
                ex      de, hl
                dec     hl
                ret
x16:            add     hl, hl
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ret
; cv_chunk: HL = X (16 x the counts of one 128-byte chunk): clocks/byte x 10 = (X - rs_s - RS_KC) / 64
cv_chunk:       ld      de, (rs_s)
                or      a
                sbc     hl, de
                jr      c, cc_0
                ld      de, RS_KC
                sbc     hl, de
                jr      nc, cc_1
cc_0:           ld      hl, 0
cc_1:           ld      b, 6
cc_2:           srl     h
                rr      l
                djnz    cc_2
                ret
; rs_mean: HL = the first area's word in rs_res: HL = the mean over the areas
rs_mean:        ld      a, (rs_n)
                ld      b, a
                ld      c, a
                push    hl
                pop     ix
                ld      hl, 0
                ld      de, RS_AREA
rn_1:           ld      a, l
                add     a, (ix + 0)
                ld      l, a
                ld      a, h
                adc     a, (ix + 1)
                ld      h, a
                add     ix, de
                djnz    rn_1
                jp      div8

; tm_one: DE = address, IX = the routine: HL = the counts (the page from rs_pa, set before the timing)
tm_one:         ld      a, (rs_pa)
                out     (RD_PAGE), a
; tm_op: IX = the routine (DE kept for it): HL = counter 0's counts from one latch to the next around it
tm_op:          xor     a
                out     (PORT_CTCC), a          ; latch
                in      a, (PORT_CTC0)
                ld      l, a
                in      a, (PORT_CTC0)
                ld      h, a
                ld      (rs_t0), hl
                call    rs_go
                xor     a
                out     (PORT_CTCC), a          ; latch
                in      a, (PORT_CTC0)
                ld      e, a
                in      a, (PORT_CTC0)
                ld      d, a
                ld      hl, (rs_t0)
                or      a
                sbc     hl, de                  ; counting down: t0 - t1 (mod 65536)
                ret
rs_go:          jp      (ix)
; the timed routines: DE = address. Nominal cost besides 21 clocks a byte: 42 (10 + 4 + 7 + 12 + 7 + 7 - 5)
op_chunk:       ld      hl, TRKBUF
                ld      b, d
                ld      c, RD_ADDR
                out     (c), e
                ld      c, RD_DATA
                ld      b, RS_CHUNK
                inir
rs_cal:         ret
op_run:         ld      hl, TRKBUF
                ld      b, d
                ld      c, RD_ADDR
                out     (c), e
                ld      c, RD_DATA
                ld      b, RS_RUN
                inir
                ret
; rs_add: A = page: to (HL) unless it is the last one there
rs_add:         dec     hl
                cp      (hl)
                inc     hl
                ret     z
                ld      (hl), a
                inc     hl
                ret

; rs_show: the loading screen's report, one line under the bar (row 126, colour 7): the size (in M when it is a whole
; number of MB, else in K) and the GAME mean over the areas (clocks/byte, "T" a byte: 21.0 = no wait states):
;   RAM DISK 1M, 21.0 T/BYTE
; (the areas' MIN / MAX / ALIGN / MISAL / GAME stay in rs_res for the tests, docs/ramdisk-tiers.md section 1)
rs_show:        ld      hl, 126 * 40 + 4
                call    rs_line
                ld      hl, s_rd
                call    put_str
                ld      a, (rd_top)
                ld      l, a
                ld      h, 0
                inc     hl                      ; 64 KB pages (8-256)
                ld      a, l
                and     15
                ld      c, 'M'
                ld      b, 4
                jr      z, sh_m                 ; a whole number of MB: pages / 16
                ld      c, 'K'
                ld      b, 6
sh_k:           add     hl, hl                  ; else K: pages x 64
                djnz    sh_k
                jr      sh_p
sh_m:           srl     h
                rr      l
                djnz    sh_m
sh_p:           push    bc
                call    put_dec
                pop     bc
                ld      a, c
                ld      (de), a
                inc     de
                ld      hl, s_unit
                call    put_str
                ld      hl, (rs_gav)
                call    put_t10
                ld      hl, s_tpb
                call    put_str
; rs_print: print rs_txt (DE = its end)
rs_print:       xor     a
                ld      (de), a
                ld      hl, rs_txt
                jp      print_at
; rs_line: HL = VRAM offset: rs_txt's header (the offset, colour 7); DE = its text. Keeps HL.
rs_line:        ld      (rs_txt), hl
                ld      a, 7
                ld      (rs_txt + 2), a
                ld      de, rs_txt + 3
                ret
; put_str: HL = text (0-terminated) to DE. put_dec: HL = number, in decimal to DE. put_t10: HL = x 10 as "21.0" to
; DE. All advance DE.
put_str:        ld      a, (hl)
                or      a
                ret     z
                ld      (de), a
                inc     hl
                inc     de
                jr      put_str
put_dec:        xor     a
                ld      (pd_any), a
                ld      bc, -10000
                call    pd_d
                ld      bc, -1000
                call    pd_d
                ld      bc, -100
                call    pd_d
                ld      bc, -10
                call    pd_d
                ld      a, l
                jr      pd_put
pd_d:           ld      a, -1
pd_1:           inc     a
                add     hl, bc
                jr      c, pd_1
                sbc     hl, bc                  ; (CF = 0) one too many back
                or      a
                jr      nz, pd_put
                ld      a, (pd_any)
                or      a
                ret     z
                xor     a
pd_put:         add     a, '0'
                ld      (de), a
                inc     de
                ld      a, 1
                ld      (pd_any), a
                ret
put_t10:        ld      c, 10
                call    div8
                push    af
                call    put_dec
                ld      a, '.'
                ld      (de), a
                inc     de
                pop     af
                add     a, '0'
                ld      (de), a
                inc     de
                ret
; div8: HL = HL / C, A = the remainder (C < 128)
div8:           xor     a
                ld      b, 16
dv_1:           add     hl, hl
                rla
                cp      c
                jr      c, dv_2
                sub     c
                inc     l
dv_2:           djnz    dv_1
                ret

rd_max:         dw      RD_SPEED_MAX    ; (tests/m5_boot.py patches these)
rd_min:         dw      RD_SPEED_MIN
s_rd:           db      "RAM DISK ", 0
s_unit:         db      ", ", 0
s_tpb:          db      " T/BYTE", 0
s_slow:         db      "RAM DISK TOO SLOW: ", 0
s_fault:        db      "RAM DISK TIMER FAULT: ", 0
s_cpb:          db      " CLOCKS/BYTE", 0
s_limit:        db      "GAME PATTERN, ", 0
s_max:          db      "MAX ", 0
s_min:          db      "MIN ", 0
s_worst:        db      ", WORST ", 0
