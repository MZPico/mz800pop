; ---------------------------------------------------------------- the PSG player (M7 steps 3-4; block 2)
; Plays one stream at a time on the SN76489 (port F2h) from the 50 Hz VBLN interrupt: game.asm's isr ends with a jump
; to snd_isr, which returns from the interrupt. A stream is a sound of the bank tools/sndconv.py builds (RAM-disk page
; SB_PAGE at SB_ADDR: per sound id 4 bytes: stream address in the page, length; then the streams; format: sndconv.py).
; Every stream goes through the ring buffer MUS_BUF 0xFE02-0xFEFF (254 places, at most 253 bytes unread): snd_start
; (from sound.asm snd_next, main code) stops the playing stream, mutes the PSG and fills the ring; snd_fill (main code:
; snd_start, and once a tick from snd_playing, i.e. play_next_sound) tops it up from the RAM disk. The ISR never
; touches the RAM disk (the address register cannot be restored inside an interrupt); a music piece survives at least
; 229 frames without a refill (the ending; tools/sndsim.py max_gap), a full room draw takes ~110.
; Each interrupt while a stream plays: the four envelopes step (a channel's attenuation goes up by one every `per`
; frames until 15), then, when its wait has run out, the next group of commands:
;   0x00 end (all muted, stop); 0x01-0x7F wait n frames; 1cc0dddd + data byte: a tone (both written); 11100xxx: the
;   noise control (written); 1cc1aaaa: attenuation (written) + unless 15 a period byte: channel c's envelope.
;   0xE8 lo hi (after the stream's last wait, not counted in its length): the stream loops at bank address hi:lo;
;   read by snd_fill only (M7 step 11: the presentation's music), the ISR's code is unchanged.
; Everything the ISR touches is outside 0x1000-0x1FFF and 0x8000-0x9FFF (CG ROM and VRAM while blit runs).
; snd_playing is the game logic's check_sound_playing: the player's stream runs (SP_WAIT != 0), or never in the
; silent mode (SND_MODE 0: every harness run; the launched game sets 1 in game_init, the level-start overlay).
; tools/sndsim.py is the Python model of this player (tests/m7_sound.py compares the PSG state frame by frame).

PORT_PSG        equ     0xf2
                if defined PSG_BANK_PAGE        ; (PRES, src/pres/pres.asm: its own bank, M7 step 6)
SB_PAGE         equ     PSG_BANK_PAGE
SB_ADDR         equ     PSG_BANK_ADDR
                else
SB_PAGE         equ     1               ; the sound bank in the RAM disk (tools/sndconv.py SB_PAGE, SB_ADDR)
SB_ADDR         equ     0xe000          ; (low byte 0: the index entry is at SB_ADDR + 4 id)
                endif
SP_VARS         equ     0x03c8          ; player state (low RAM, runtime only; irq_init stops the player)
SP_WAIT         equ     SP_VARS + 0     ; frames until the next group (0 = no stream)
SP_PTR          equ     SP_VARS + 1     ; 16-bit: the next byte in the ring
MF_SRC          equ     SP_VARS + 3     ; 16-bit: the RAM-disk address of the next byte to copy into the ring
MF_LEFT         equ     SP_VARS + 5     ; 16-bit: bytes of the stream not yet copied
MF_W            equ     SP_VARS + 7     ; the ring's write position (low byte; high byte 0xFE)
SND_MODE        equ     SP_VARS + 8     ; 0 silent (snd_playing always 0), 1 live (the player's state)
ENV             equ     SP_VARS + 9     ; 4 x (attenuation, counter, period): the envelopes (0x03D1-0x03DC)
MUS_BUF         equ     0xfe02          ; the ring (0xFE02-0xFEFF)
                if (ENV / 256) - ((ENV + 11) / 256)
                .error ENV straddles a page
                endif

; snd_isr: the tail of the VBLN interrupt (game.asm isr pushed AF and HL): one frame of the stream
snd_isr:        ld      a, (SP_WAIT)
                or      a
                jr      z, spi_x                ; no stream
                push    bc
                push    de
                ld      hl, ENV
                ld      c, 0x90                 ; the attenuation latch of channel 0
spe:            ld      a, (hl)
                inc     hl
                cp      15
                jr      nc, spe_n               ; off
                dec     (hl)
                jr      nz, spe_n
                inc     a                       ; a step: attenuation + 1, the counter restarts at the period
                dec     hl
                ld      (hl), a
                or      c
spo_1:          out     (PORT_PSG), a           ; (spo_1-3: src/m4/ovl_keys.asm snd_onoff, sound off: patched to NOPs)
                inc     hl
                inc     hl
                ld      a, (hl)
                dec     hl
                ld      (hl), a
spe_n:          inc     hl
                inc     hl
                ld      a, c
                add     a, 0x20
                ld      c, a
                jr      nc, spe
                ld      hl, SP_WAIT
                dec     (hl)
                jr      nz, spi_done            ; the group is held
                ld      hl, (SP_PTR)
spg:            call    sp_rd
                or      a
                jr      z, spi_end
                jp      p, spi_hold             ; 1-127: the next group after A frames
spo_2:          out     (PORT_PSG), a
                ld      b, a
                bit     4, a
                jr      nz, spg_att
                cp      0xe0
                jr      nc, spg                 ; the noise control: one byte
                call    sp_rd                   ; a tone latch's data byte
spo_3:          out     (PORT_PSG), a
                jr      spg
spg_att:        rlca                            ; 1cc1aaaa: channel c's envelope starts at aaaa
                rlca
                rlca
                and     3
                ld      e, a
                add     a, a
                add     a, e
                add     a, ENV % 256
                ld      e, a
                ld      d, ENV / 256
                ld      a, b
                and     15
                ld      (de), a
                cp      15
                jr      z, spg                  ; (off: no period byte)
                call    sp_rd
                inc     de
                ld      (de), a
                inc     de
                ld      (de), a
                jr      spg
spi_hold:       ld      (SP_WAIT), a
                ld      (SP_PTR), hl
spi_done:       pop     de                      ; (tests/m7_sound.py: the frame's PSG writes are done here)
                pop     bc
spi_x:          pop     hl
                pop     af
                ei
spi_reti:       reti
spi_end:        ld      (SP_WAIT), a            ; (A = 0) the stream ended
                call    psg_mute
spi_ended:      jr      spi_done
; sp_rd: A = the next byte of the ring at HL, HL advanced (wrapping 0xFEFF -> 0xFE02)
sp_rd:          ld      a, (hl)
                inc     l
                ret     nz
                ld      l, MUS_BUF % 256
                ret

; psg_mute: attenuation 15 (off) on the four channels. Uses A.
psg_mute:       ld      a, 0x9f
psm1:           out     (PORT_PSG), a
                add     a, 0x20
                jr      nc, psm1
                ret

; snd_halt (stop_sounds, before a floppy access, irq_init): the stream stops (nothing more to copy), the PSG is
; muted. Keeps the interrupt state (also called with interrupts off). Uses A.
snd_halt:       ld      a, i                    ; (P/V = IFF2)
                di
snh_di:         push    af                      ; (tests/m7_sound.py: the stop happens here, no interrupt until the end)
                xor     a
                ld      (SP_WAIT), a
                ld      (MF_LEFT), a
                ld      (MF_LEFT + 1), a
                call    psg_mute
                pop     af
                ret     po
                ei
                ret

; snd_start (sound.asm snd_next starts a sound): A = sound id. The playing stream stops, the PSG is muted, the ring is
; filled with the start of the id's stream and armed (the next interrupt plays its first group). An id without a
; stream leaves the player stopped. Keeps BC, DE.
snd_start:      push    bc
                push    de
                push    af
                call    snd_halt
                pop     af
                add     a, a                    ; the index entry: SB_ADDR + 4 id
                add     a, a
                ld      e, a
                ld      d, SB_ADDR / 256
                ld      a, SB_PAGE
                call    far_seek
                ld      hl, MF_SRC
                ld      b, 4
                call    far_read                ; MF_SRC, MF_LEFT
                ld      hl, (MF_LEFT)
                ld      a, h
                or      l
                jr      z, sst_x
                ld      hl, ENV                 ; the envelopes off
                ld      b, 4
sst_e:          ld      (hl), 15
                inc     hl
                inc     hl
                inc     hl
                djnz    sst_e
                ld      hl, MUS_BUF             ; the ring empty
                ld      (SP_PTR), hl
                ld      a, l
                ld      (MF_W), a
                call    snd_fill
                ld      a, 1
snd_arm:        ld      (SP_WAIT), a
sst_x:          pop     de
                pop     bc
                ret

; snd_fill: as much of the stream as the ring has room for is copied from the RAM disk (main code only; the ISR may
; read the ring meanwhile: it only frees room). Uses AF, BC, DE, HL.
snd_fill:       ld      hl, (MF_LEFT)
                ld      a, h
                or      l
                ret     z                       ; all copied
                ld      a, (MF_W)
                ld      c, a
                ld      a, (SP_PTR)
                scf
                sbc     a, c                    ; room = read - write - 1 ...
                jr      nc, sf1
                sub     2                       ; ... + 254 when it wraps (the ring has 254 places)
sf1:            ld      b, a
                inc     h
                dec     h
                jr      nz, sf2                 ; more than 255 left
                cp      l
                jr      c, sf2
                ld      b, l                    ; the rest fits
sf2:            ld      a, b
                or      a
                ret     z                       ; no room
                ld      e, b
                ld      d, 0
                sbc     hl, de                  ; (carry clear)
                ld      (MF_LEFT), hl
                ld      hl, (MF_SRC)
                push    hl
                add     hl, de
                ld      (MF_SRC), hl
                pop     de
                ld      a, SB_PAGE
                push    bc
                call    far_seek
                pop     bc
                ld      h, MUS_BUF / 256
                ld      a, (MF_W)
                ld      l, a
sfl:            in      a, (RD_DATA)
                ld      (hl), a
                inc     l
                jr      nz, sf3
                ld      l, MUS_BUF % 256
sf3:            djnz    sfl
                ld      c, a                    ; (the last byte copied)
                ld      a, l
                ld      (MF_W), a
sf_x:           ld      hl, (MF_LEFT)           ; (tests/m7_sound.py: the copy is done, MF_W and MF_LEFT are written)
                ld      a, h
                or      l
                ret     nz                      ; more of the stream to come
                ; The stream's last byte was copied: 0x00 ends it (the ISR stops there). Otherwise the stream loops
                ; (M7 step 11, the presentation's music): its last byte is a wait and the loop command 0xE8 lo hi
                ; follows it in the bank (not counted in the length; the RAM disk is positioned there): the copying
                ; goes on at the loop point hi:lo, whose bytes follow the wait in the ring: the ISR never sees the
                ; command. The game's streams all end with 0x00, so the game never reads past a stream.
                ld      a, c
                or      a
                ret     z
                in      a, (RD_DATA)
                cp      0xe8
                ret     nz                      ; (not a loop command: the stream ends)
                in      a, (RD_DATA)
                ld      e, a
                in      a, (RD_DATA)
                ld      d, a                    ; DE = the loop point
                ld      hl, (MF_SRC)            ; = the command's address: the loop body is the loop point up to it
                ld      (MF_SRC), de
                or      a
                sbc     hl, de
                ld      (MF_LEFT), hl
sf_loop:        jp      snd_fill                ; (tests: a loop) the loop point's bytes right away (the ring may have room)

; snd_playing (check_sound_playing; play_next_sound asks it once a tick, so the ring is refilled here first):
; A = 1 while a stream runs (live mode), else 0
snd_playing:    call    snd_fill
                ld      a, (SND_MODE)
                or      a
                ret     z
snp_rd:         ld      a, (SP_WAIT)            ; (tests/m7_sound.py: the player's state is read here)
                or      a
                ret     z
                ld      a, 1
                ret
