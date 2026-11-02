; Keys overlay (window W1, src/m4/ovl.asm): the keyboard's keys and their logic. Assembled after the main program against
; its symbols (build/ovl_keys.inc, tools/ovltool.py). key_read runs at a tick start when key_scan (src/m4/keyres.asm) saw
; a candidate key down; key_logic at the tick's control point (kid.asm) when KEYS has a key. Loading it replaces the room
; or events overlay in W1, whose stubs load them again when needed (a key costs ~0.3 frames, a tick with no key nothing).
; Pause: BREAK at a tick start. The stream is held (SP_WAIT kept here, 0 for the ISR) and goes on at the resume with
; the attenuations written back: a live wait (the death music, the end music) just takes longer, and the ticks do not
; run, so the clock is not charged. The key that resumes has no other effect.
                include "../../build/ovl_keys.inc"
                include "../boot/launch.inc"
                org     OVL_W1
ovl_id          equ     OVL_KEYS
ovl_entry:      jp      key_read                ; entry 0 (stub key_read, from key_scan)
                jp      key_logic               ; entry 1 (stub key_logic, from kid.asm)

K_ANY           equ     0xff                    ; key_tab: any modifiers
K_CTRL_A        equ     30                      ; codes without a key_logic code: KEYS bit 0, bit 2
K_CTRL_G        equ     31
; key_tab: column, bit mask, the modifiers it needs (column 8: CTRL 0x40, SHIFT 0x01; process_key compares them exactly,
; K_ANY: Esc works with SHIFT too), code. The first entry down counts.
key_tab:        db      8, 0x80, K_ANY, KEY_PAUSE
                db      6, 0x10, 0x00, KEY_SPACE
                db      0, 0x01, 0x00, KEY_ENTER
                db      3, 0x10, 0x01, KEY_SHIFT_L
                db      4, 0x80, 0x40, K_CTRL_A
                db      4, 0x02, 0x40, K_CTRL_G
                db      2, 0x40, 0x40, KEY_CTRL_R
                db      2, 0x80, 0x40, KEY_CTRL_R       ; Ctrl+Q: as Ctrl+R (nothing to quit to)
                db      2, 0x20, 0x40, KEY_CTRL_S
                db      2, 0x04, 0x40, KEY_CTRL_V
                if defined CHEATS
                db      3, 0x20, 0x00, 8                ; K
                db      2, 0x40, 0x00, 9                ; R
                db      9, 0x80, 0x00, 10               ; F1: +
                db      9, 0x40, 0x00, 11               ; F2: -
                db      2, 0x10, 0x01, 12               ; Shift+T
                db      2, 0x20, 0x01, 13               ; Shift+S
                db      2, 0x02, 0x01, 14               ; Shift+W
                db      3, 0x80, 0x01, 15               ; Shift+I
                db      4, 0x01, 0x00, 16               ; H
                db      3, 0x40, 0x00, 17               ; J
                db      2, 0x08, 0x00, 18               ; U
                db      3, 0x04, 0x00, 19               ; N
                db      4, 0x40, 0x40, 20               ; Ctrl+B
                db      4, 0x40, 0x01, 21               ; Shift+B
                db      2, 0x10, 0x00, 22               ; T
                endif
                db      0xff
; key_match: B = the code of the first key of key_tab down, 0 none
key_match:      ld      a, (KEYMAT + 8)
                and     0x41
                ld      c, a
                ld      hl, key_tab
km1:            ld      a, (hl)
                cp      0xff
                ld      b, 0
                ret     z
                add     a, KEYMAT % 256
                ld      e, a
                ld      d, KEYMAT / 256
                inc     hl
                ld      a, (de)
                and     (hl)
                inc     hl
                jr      z, km2
                ld      a, (hl)
                cp      K_ANY
                jr      z, km3
                cp      c
                jr      nz, km2
km3:            inc     hl
                ld      b, (hl)
                ret
km2:            inc     hl
                inc     hl
                jr      km1
; key_read: this tick's KEYS: a key counts once per press
key_read:       call    key_match
                ld      a, (edge_bits)
                cp      b
                ld      a, b
                ld      (edge_bits), a
                ld      a, 0
                jr      z, kr_set
                ld      a, b
                or      a
                jr      z, kr_set
                cp      KEY_PAUSE
                call    z, do_pause
                ld      a, b
                cp      K_CTRL_A
                ld      a, 1
                jr      z, kr_set
                ld      a, b
                cp      K_CTRL_G
                ld      a, 4
                jr      z, kr_set
                ld      a, b
                add     a, a
                add     a, a
                add     a, a
kr_set:         ld      (KEYS), a
                ret
; do_pause: "GAME PAUSED" (SPRBUF_B: pend_flush first, the text overlay in W2), the PSG muted, until a key but CTRL or
; SHIFT, or the fire button, after all were let go. Keeps B = KEY_PAUSE (the logic part: key_logic's erase_text).
do_pause:       call    pend_flush
                di
                ld      a, (SP_WAIT)
                ld      (dp_wait), a
                xor     a
                ld      (SP_WAIT), a
                call    psg_mute
                ei
                ld      a, TXT_MSG_PAUSED
                ld      (TEXT_MSG), a
                ld      a, (TEXT_GEN)
                ld      (TEXT_MSG_GEN), a
dp_shown:       call    text_draw
dp_rel:         call    dp_keys
                jr      nz, dp_rel
dp_wait_k:      call    dp_keys
                jr      z, dp_wait_k
dp_resume:      xor     a
                ld      (TEXT_MSG), a
                call    key_match               ; (the resuming key: not a press of its own)
                ld      a, b
                ld      (edge_bits), a
                ld      a, (dp_wait)
                call    psg_back
                ld      b, KEY_PAUSE
                ret
; dp_keys: a frame later: NZ = a key but CTRL / SHIFT is down, or fire
dp_keys:        halt
                call    read_inputs
                ld      hl, KEYMAT
                ld      b, 8
                xor     a
dpk1:           or      (hl)
                inc     hl
                djnz    dpk1
                ld      b, a
                ld      a, (KEYMAT + 8)
                and     0xbe
                or      b
                ld      b, a
                ld      a, (KEYMAT + 9)
                or      b
                ld      b, a
                ld      a, (JOY)
                and     0x10
                or      b
                ret
; psg_back: A = SP_WAIT: the stream goes on, the PSG as the envelopes have it (the tones stay latched; not when the
; sound is off, not without a stream)
psg_back:       di
                ld      (SP_WAIT), a
                or      a
                jr      z, pb_x
                ld      a, (KEY_OPT)
                rrca
                jr      c, pb_x
                ld      hl, ENV
                ld      c, 0x90
pb1:            ld      a, (hl)
                or      c
                out     (PORT_PSG), a
                inc     hl
                inc     hl
                inc     hl
                ld      a, c
                add     a, 0x20
                ld      c, a
                jr      nc, pb1
pb_x:           ei
                ret
; snd_onoff (Ctrl+S, KEY_OPT toggled): off: the PSG muted and the player's writes patched away (two NOPs for each OUT of
; psg.asm's ISR): the stream, and every wait on it, goes on as SDLPoP's silent mixer does. On: the OUTs back.
snd_onoff:      di
                ld      a, (KEY_OPT)
                rrca
                ld      hl, 0
                jr      c, so1
                ld      hl, PORT_PSG * 256 + 0xd3
so1:            ld      (spo_1), hl
                ld      (spo_2), hl
                ld      (spo_3), hl
                call    psg_mute
                ld      a, (SP_WAIT)
                jr      psg_back

                include "../m4/keys.asm"
                if KEY_OPT - (HO_MAIN + HO_OPTIONS)
                .error KEY_OPT is not the handoff's options byte
                endif
                if defined CHEATS
; blind_set: Shift+B: on: the playfield's 192 rows black (the VRAM window: nothing here is in it); off: the room again
blind_set:      ld      a, (KEY_OPT)
                and     2
                jr      z, bs_off
                in      a, (0xe0)
                ld      a, 0x80
                out     (PORT_WF), a
                ld      hl, VRAM
                ld      de, VRAM + 1
                ld      bc, 192 * 40 - 1
                ld      (hl), 0xff
                ldir
                in      a, (0xe1)
                ret
bs_off:         ld      a, 0xff
                ld      (SHOWN_ROOM), a
                ret
                endif
dp_wait:        db      0                       ; (do_pause: SP_WAIT; W1 stays loaded during the pause)
ovl_end:
                if ovl_end > OVL_W1_END
                .error the keys overlay is larger than its window W1
                endif
