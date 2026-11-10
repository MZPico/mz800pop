; ---------------------------------------------------------------- traps, objects and hit points (M4)
; Z80 port of SDLPoP seg007 (animated tiles = "trobs", falling loose floors = "mobs", buttons and door
; links) and the related kid code (spikes, pressing, items, hit points) as reproduced by tools/kidsim.py.
; The level blueprint at LEVEL is live: fg/bg (tiles/modifiers) and the door-link timers change in place.

OV              equ     0x0b30
HITP_CURR       equ     OV + 0
HITP_MAX        equ     OV + 1
HITP_DELTA      equ     OV + 2          ; signed, applied by do_delta_hp at the end of the tick
LEVELDOOR_OPEN  equ     OV + 3
HAVE_SWORD      equ     OV + 4
PICKUP_TYPE     equ     OV + 5          ; signed: -1 sword, 1.. potion type
LAST_LOOSE      equ     OV + 6
LEVEL_DONE      equ     OV + 7          ; 1 = the exit sequence finished (SEQ_END_LEVEL)
KNOCK           equ     OV + 8          ; signed
O_CTILE         equ     OV + 9          ; get_curr_tile: curr_tile / curr_modifier
O_CMOD          equ     OV + 10
TROBS_N         equ     OV + 11
MOBS_N          equ     OV + 12
PT_I            equ     OV + 13
TROB_P          equ     OV + 14         ; 16-bit: current trob entry
                                        ; OV + 16: free (WANT_RESTART until the button restart moved to the tick's start)
O_T1            equ     OV + 17         ; scratch
O_T2            equ     OV + 18
O_T3            equ     OV + 19
O_T4            equ     OV + 20
MOB_P           equ     OV + 22         ; 16-bit: current mob entry
MOB_N0          equ     OV + 24         ; mobs to move this tick
MOB_I           equ     OV + 25
TR_SNAP         equ     OV + 26         ; trace snapshot: hitp_curr, hitp_max, trobs, mobs, checksum (2) = 6 bytes
KV_SNAP         equ     0x0ac0          ; trace snapshot of the 16 kid bytes
; level events (M5; kidsim's game-wide state): low RAM, runtime only, set by game_init (src/m4/levelstart.asm)
EV              equ     0x0280
NEXT_LEVEL      equ     EV + 0
REM_MIN         equ     EV + 1          ; the time left: minutes
REM_TICK        equ     EV + 2          ; 16-bit: ticks of the minute (719 .. 1)
IS_SHOW_TIME    equ     EV + 4
TEXT_REM        equ     EV + 5          ; 16-bit text_time_remaining
TEXT_TOTAL      equ     EV + 7          ; 16-bit text_time_total
FEATHER         equ     EV + 9          ; is_feather_fall (counts the ticks of a feather fall)
UPSIDE          equ     EV + 10         ; upside_down: 0 / 0xff
FLASH_COLOR     equ     EV + 11
FLASH_TIME      equ     EV + 12
JUMPED_MIRROR   equ     EV + 13         ; 0 / 0xff
DEMO_TIME       equ     EV + 14
DEMO_INDEX      equ     EV + 15
SHADOW_INIT     equ     EV + 16
HITP_BEG_LEV    equ     EV + 17
CHECKPOINT      equ     EV + 18
SEAMLESS        equ     EV + 19
FEATHER_MUSIC   equ     EV + 20         ; the sound model: the feather fall music plays (stop_sounds clears it)
IS_RESTART      equ     EV + 21         ; Ctrl+A: the level restarts after this tick
LEVEL_SWITCH    equ     EV + 22         ; the next level starts after this tick (level 6 / 12 exits)
GAME_OVER       equ     EV + 23         ; 1 time expired, 2 the end (level 14), 3 back to the title
KEYS            equ     EV + 24         ; this tick's keys: bit 0 Ctrl+A, bit 2 Ctrl+G, bits 3-7 a key code (src/m4/keys.asm)
TEXT_GEN        equ     EV + 25         ; drawing: counts set_text / erase_text calls (a new bottom text to draw)
FLASH_NOW       equ     EV + 26         ; drawing: the flash of this tick (EGA colour; draw_game_frame, flash_if_hurt)
MI_JUMPED       equ     EV + 27         ; drawing: the kid jumped through the mirror this tick (no mirror image)
TXT_GEN_SHOWN   equ     EV + 28         ; drawing: ~TEXT_GEN of the bottom text on screen (game_init: a text to draw)
TEXT_MSG        equ     EV + 29         ; the save overlay's text (1 GAME SAVED, 2 UNABLE TO SAVE GAME; src/m4/save.asm),
TEXT_MSG_GEN    equ     EV + 30         ; shown while TEXT_GEN still equals TEXT_MSG_GEN (any later text replaces it)
EV_SIZE         equ     31
GO_EXPIRED      equ     1
GO_END          equ     2
GO_TITLE        equ     3
COLOR_GREEN     equ     2
COLOR_RED       equ     4
COLOR_YELLOW    equ     14
COLOR_WHITE     equ     15
TROBS           equ     0x0b50          ; 30 x (room, pos, type)
MOBS            equ     0x0baa          ; 14 x (xh, y, room, speed, type, row)
TROBS_MAX       equ     30
MOBS_MAX        equ     14
DL1             equ     LEVEL + 1440    ; door links
DL2             equ     LEVEL + 1696
T_CLOSER_       equ     6
T_DEBRIS        equ     14
T_LEVELDOOR_R   equ     17
SQ_SPIKED       equ     51
SQ_LOOSE_ON_KID equ     52
SQ_CHOMPED      equ     54
SQ_GO_UP_DOOR   equ     70
SQ_DRINK        equ     78
SQ_GET_SWORD    equ     91

y_something:    db      255, 62, 125, 188, 25
y_loose_land:   db      2, 65, 128, 191, 254
loose_sound:    db      0, 1, 1, 1, 0, 1, 0, 0, 1, 0, 0, 0
gate_close_spd: db      0, 0, 0, 20, 40, 60, 80, 100, 120
door_delta:     db      255, 4, 4
ldoor_close_spd: db     0, 5, 17, 99, 0

; ---------------------------------------------------------------- tile helpers
; o_ptrs: A = room (1..24), C = pos -> HL = &fg, DE = &bg
o_ptrs:         call    tile_base
                ld      a, c
                add     a, l
                ld      l, a
                jr      nc, op1
                inc     h
op1:            ld      a, c
                add     a, e
                ld      e, a
                ret     nc
                inc     d
                ret
; get_curr_tile: A = pos in CURR_ROOM -> A = tile (O_CTILE), O_CMOD = modifier
get_curr_tile:  ld      c, a
                ld      a, (CURR_ROOM)
                call    o_ptrs
                ld      a, (de)
                ld      (O_CMOD), a
                ld      a, (hl)
                and     0x1f
                ld      (O_CTILE), a
                ret
; set_tile_cur / set_mod_cur: A = value, at (CURR_ROOM, CURR_TILEPOS)
set_tile_cur:   push    af
                ld      a, (CURR_TILEPOS)
                ld      c, a
                ld      a, (CURR_ROOM)
                call    o_ptrs
                pop     af
                ld      (hl), a
                ret
set_mod_cur:    push    af
                ld      a, (CURR_TILEPOS)
                ld      c, a
                ld      a, (CURR_ROOM)
                call    o_ptrs
                pop     af
                ld      (de), a
                ret
; mod_cur: A = modifier at (CURR_ROOM, CURR_TILEPOS), 0 in room 0 (= k_modif)
mod_cur:        jp      k_modif
; div10: A -> A = A / 10 (A < 40)
div10:          ld      b, 0
d10:            cp      10
                jr      c, d10x
                sub     10
                inc     b
                jr      d10
d10x:           ld      a, b
                ret

; ---------------------------------------------------------------- hit points
; take_hp: A = count -> A = 1 if that kills, HITP_DELTA set
take_hp:        ld      b, a
                ld      a, (K_CHARID)   ; (guard.asm: the guard's hit points)
                or      a
                jp      nz, take_hp_g
                ld      a, (HITP_CURR)
                cp      b
                jr      z, th_dead
                jr      c, th_dead
                ld      a, b
                neg
                ld      (HITP_DELTA), a
                xor     a
                ret
th_dead:        neg
                ld      (HITP_DELTA), a
                ld      a, 1
                ret
do_delta_hp:    ld      a, (HITP_DELTA)
                ld      hl, HITP_CURR
                add     a, (hl)         ; (small values: curr 0..10, delta -10..10)
                bit     7, a
                jr      z, ddh1
                xor     a
ddh1:           ld      hl, HITP_MAX
                cp      (hl)
                jr      c, ddh2
                ld      a, (hl)
ddh2:           ld      (HITP_CURR), a
                ret

; ---------------------------------------------------------------- trobs
; add_trob: B = room, C = pos, A = type
add_trob:       ld      (O_T1), a
                ld      a, (TROBS_N)
                or      a
                jr      z, at_new
                ld      e, a
                ld      hl, TROBS
at_find:        ld      a, (hl)
                cp      b
                jr      nz, at_nx
                inc     hl
                ld      a, (hl)
                dec     hl
                cp      c
                jr      nz, at_nx
                inc     hl
                inc     hl
                ld      a, (O_T1)
                ld      (hl), a
                ret
at_nx:          inc     hl
                inc     hl
                inc     hl
                dec     e
                jr      nz, at_find
at_new:         ld      a, (TROBS_N)
                cp      TROBS_MAX
                ret     nc
                ld      l, a
                ld      h, 0
                ld      e, l
                ld      d, h
                add     hl, hl
                add     hl, de
                ld      de, TROBS
                add     hl, de
                ld      (hl), b
                inc     hl
                ld      (hl), c
                inc     hl
                ld      a, (O_T1)
                ld      (hl), a
                ld      hl, TROBS_N
                inc     (hl)
                ret
; trob_type: HL = &type of the current trob, A = type
trob_type:      ld      hl, (TROB_P)
                inc     hl
                inc     hl
                ld      a, (hl)
                ret
trob_kill:      call    trob_type
                ld      (hl), 0xff
                ret
process_trobs:  ld      a, (TROBS_N)
                or      a
                ret     z
                xor     a
                ld      (PT_I), a
pt_loop:        ld      a, (PT_I)
                ld      hl, TROBS_N
                cp      (hl)
                jr      nc, pt_compact
                ld      l, a
                ld      h, 0
                ld      e, l
                ld      d, h
                add     hl, hl
                add     hl, de
                ld      de, TROBS
                add     hl, de
                ld      (TROB_P), hl
                call    animate_tile
                ld      hl, PT_I
                inc     (hl)
                jr      pt_loop
pt_compact:     ld      hl, TROBS
                ld      de, TROBS
                ld      a, (TROBS_N)
                ld      b, a
                ld      c, 0
ptc:            push    bc
                inc     hl
                inc     hl
                ld      a, (hl)
                dec     hl
                dec     hl
                bit     7, a
                jr      nz, ptc_skip
                ldi
                ldi
                ldi
                pop     bc
                inc     c
                jr      ptc_n
ptc_skip:       inc     hl
                inc     hl
                inc     hl
                pop     bc
ptc_n:          djnz    ptc
                ld      a, c
                ld      (TROBS_N), a
                ret
animate_tile:   ld      hl, (TROB_P)
                ld      a, (hl)
                ld      (CURR_ROOM), a
                inc     hl
                ld      a, (hl)
                call    get_curr_tile
                call    at_dispatch
                ld      hl, (TROB_P)
                ld      a, (hl)
                inc     hl
                ld      c, (hl)
                call    o_ptrs
                ld      a, (O_CMOD)
                ld      (de), a
                ret
at_dispatch:    ld      a, (O_CTILE)
                cp      T_TORCH
                jp      z, ob_torch
                cp      T_TORCH_DEBRIS
                jp      z, ob_torch
                cp      T_CLOSER_
                jp      z, an_button
                cp      T_OPENER
                jp      z, an_button
                cp      T_SPIKE
                jp      z, an_spike
                cp      T_LOOSE
                jp      z, an_loose
                cp      T_EMPTY
                jp      z, trob_kill
                cp      T_CHOMPER
                jp      z, an_chomper
                cp      T_GATE
                jp      z, an_door
                cp      T_LEVELDOOR_L
                jp      z, an_leveldoor
                cp      T_POTION
                jp      z, ob_potion
                cp      T_SWORD
                jp      z, an_sword
                jp      trob_kill
; trob_in_drawn: NZ if the trob is in the drawn room, else kills it (Z)
trob_in_drawn:  ld      hl, (TROB_P)
                ld      a, (DRAWN_ROOM)
                cp      (hl)
                jr      nz, tid_no
                ld      a, 1
                or      a
                ret
tid_no:         call    trob_kill
                xor     a
                ret
ob_torch:       ld      hl, (TROB_P)
                ld      a, (DRAWN_ROOM)
                cp      (hl)
                jr      z, ant_go
                or      a
                jp      z, trob_kill
                call    links_of        ; C = room left of the drawn room
                ld      hl, (TROB_P)
                ld      a, c
                cp      (hl)
                jp      nz, trob_kill
                inc     hl
                ld      a, (hl)
                call    mod10
                cp      9
                jp      nz, trob_kill
ant_go:         ld      a, 255
                call    prandom
                ld      b, a
                ld      a, (O_CMOD)
                cp      b
                jr      z, ant_inc
                ld      a, b
                cp      9
                jr      c, ant_set
                ld      a, (O_CMOD)
ant_inc:        inc     a
                cp      9
                jr      c, ant_set
                xor     a
ant_set:        ld      (O_CMOD), a
                ret
ob_potion:      call    trob_type
                bit     7, a
                ret     nz
                call    trob_in_drawn
                ret     z
                ld      a, (O_CMOD)
                and     7
                inc     a
                cp      8
                jr      c, anp1
                ld      a, 1
anp1:           ld      b, a
                ld      a, (O_CMOD)
                and     0xf8
                or      b
                ld      (O_CMOD), a
                ret
an_sword:       call    trob_in_drawn
                ret     z
                ld      a, (O_CMOD)
                dec     a
                ld      (O_CMOD), a
                ret     nz
                ld      a, 255
                call    prandom
                and     0x3f
                add     a, 0x28
                ld      (O_CMOD), a
                ret
an_chomper:     call    trob_type
                bit     7, a
                ret     nz
                ld      a, (O_CMOD)
                and     0x80
                ld      (O_T2), a       ; blood
                ld      a, (O_CMOD)
                and     0x7f
                inc     a
                cp      16
                jr      c, anc1
                ld      a, 1
anc1:           call    anc_snd         ; (sound.asm: frame 2 snaps; HL = O_T2)
                or      (hl)
                ld      (O_CMOD), a
                ; stop if (room != drawn || row != kid row || (kid alive >= 0 && no blood)) && frame >= 6
                and     0x7f
                cp      6
                ret     c
                ld      hl, (TROB_P)
                ld      a, (DRAWN_ROOM)
                cp      (hl)
                jp      nz, trob_kill
                inc     hl
                ld      a, (hl)
                call    div10
                ld      hl, K_ROW
                cp      (hl)
                jp      nz, trob_kill
                ld      a, (K_ALIVE)
                bit     7, a
                ret     nz
                ld      a, (O_T2)
                or      a
                ret     nz
                jp      trob_kill
an_spike:       call    trob_type
                bit     7, a
                ret     nz
                ld      a, (O_CMOD)
                cp      0xff
                ret     z
                bit     7, a
                jr      z, ans_up
                dec     a
                ld      (O_CMOD), a
                and     0x7f
                ret     nz
                ld      a, 6
                ld      (O_CMOD), a
                ret
ans_up:         inc     a
                cp      5
                jr      nz, ans2
                ld      a, 0x8f
                ld      (O_CMOD), a
                ret
ans2:           ld      (O_CMOD), a
                cp      9
                ret     nz
                xor     a
                ld      (O_CMOD), a
                jp      trob_kill
an_door:        call    trob_type
                bit     7, a
                ret     nz
                cp      3
                jr      c, and_slow
                cp      8
                jr      nc, and_f1
                inc     a
                ld      (hl), a
and_f1:         ld      hl, gate_close_spd
                call    k_tbl
                ld      b, a
                ld      a, (O_CMOD)
                sub     b
                jr      nc, and_f2
                xor     a
                ld      (O_CMOD), a
                jp      door_fast_end   ; (sound.asm)
and_f2:         ld      (O_CMOD), a
                ret
and_slow:       ld      c, a            ; anim type 0 closing, 1 open, 2 permanent open
                ld      a, (O_CMOD)
                cp      0xff
                jp      z, gate_stop    ; (sound.asm: and its sound)
                ld      a, c
                ld      hl, door_delta
                call    k_tbl
                ld      hl, O_CMOD
                add     a, (hl)
                ld      (hl), a
                ld      b, a
                ld      a, c
                or      a
                jp      nz, door_open   ; (sound.asm: opening, open, permanently open)
                jp      door_closing    ; (sound.asm: closing, stop at 0)
an_leveldoor:   call    trob_type
                bit     7, a
                ret     nz
                cp      3
                jr      c, anl_open
                inc     a
                ld      (hl), a
                sub     3
                ld      hl, ldoor_close_spd
                call    k_tbl
                ld      b, a
                ld      a, (O_CMOD)
                sub     b
                jp      ldoor_close     ; (sound.asm: closed below 0, the sliding sound)
anl_open:       ld      a, (O_CMOD)
                inc     a
                ld      (O_CMOD), a
                cp      43
                jp      c, ldoor_slide  ; (sound.asm)
                call    trob_kill
                call    snd_stop
                ld      a, (LEVELDOOR_OPEN)
                or      a
                jr      z, anl_set
                cp      2
                ret     nz
anl_set:        ld      a, 1
                ld      (LEVELDOOR_OPEN), a
                ld      a, (level_number)       ; level 4: the mirror appears (room 4, column 4, row 0)
                cp      4
                ret     nz
                ld      bc, 0x0004              ; (A = 4: the room)
                call    k_get_tile
                ld      a, T_MIRROR
                call    set_tile_cur
                ld      hl, (TROB_P)            ; (original bug: animate_tile then stores the door's modifier in
                ld      a, (CURR_ROOM)          ; the mirror's room, at the door's tile position)
                ld      (hl), a
                ret
an_button:      call    trob_type
                bit     7, a
                ret     nz
                ld      a, (O_CMOD)
                call    get_doorlink_timer
                dec     a               ; (0 - 1 = 0xFF: not below 2, as in C's word arithmetic)
                ld      b, a
                ld      a, (O_CMOD)
                call    set_doorlink_timer
                ld      a, b
                cp      2
                ret     nc
                jp      trob_kill
an_loose:       call    trob_type
                bit     7, a
                ret     nz
                ld      a, (O_CMOD)
                inc     a
                ld      (O_CMOD), a
                bit     7, a
                jr      z, anl_floor
                ld      a, (level_number)
                cp      13              ; level 13: keeps shaking
                ret     z
                ld      a, (O_CMOD)
                cp      0x84            ; shaking
                jr      c, anl_s1
                xor     a
                ld      (O_CMOD), a
                call    trob_kill
anl_s1:         ld      a, (O_CMOD)
                or      a
                ld      a, 1
                jr      z, loose_shake
                xor     a
                jr      loose_shake
anl_floor:      cp      11              ; loose_floor_delay
                jr      nc, anl_fall
                xor     a
                jr      loose_shake
anl_fall:       ld      hl, (TROB_P)
                ld      a, (hl)
                ld      (O_T3), a       ; room
                inc     hl
                ld      c, (hl)
                ld      a, c
                ld      (O_T4), a       ; pos
                ld      a, (O_T3)
                call    remove_loose
                ld      (O_CMOD), a
                call    trob_kill
                ; new mob: xh = col * 4, y = y_loose_land[row + 1], room, speed 0, type 0, row
                ld      a, (MOBS_N)
                cp      MOBS_MAX
                ret     nc
                call    mob_ptr_n
                ld      a, (O_T4)
                call    mod10
                add     a, a
                add     a, a
                ld      (hl), a         ; xh
                inc     hl
                ld      a, (O_T4)
                call    div10
                ld      (O_T2), a       ; row
                inc     a
                push    hl
                ld      hl, y_loose_land
                call    k_tbl
                pop     hl
                ld      (hl), a         ; y
                inc     hl
                ld      a, (O_T3)
                ld      (hl), a         ; room
                inc     hl
                ld      (hl), 0         ; speed
                inc     hl
                ld      (hl), 0         ; type
                inc     hl
                ld      a, (O_T2)
                ld      (hl), a         ; row
                ld      hl, MOBS_N
                inc     (hl)
                ret
; loose_shake: A = 1 to force (else only when the shake table says so): one of the shaking sounds 20-22 (never the
; last one again), and SDLPoP's wasted random number
loose_shake:    or      a
                jr      nz, ls_go
                ld      a, (O_CMOD)
                and     0x7f
                ld      hl, loose_sound
                call    k_tbl
                or      a
                ret     z
ls_go:          ld      a, 2
                call    prandom
                add     a, 20
                ld      hl, LAST_LOOSE
                cp      (hl)
                jr      z, ls_go
                ld      (hl), a
                jp      ls_snd          ; (sound.asm)
; remove_loose: A = room, C = pos -> tile becomes empty; A = level type (the modifier left behind)
remove_loose:   call    o_ptrs
                ld      (hl), T_EMPTY
                ld      a, (LEVEL_TYPE)
                ret
; mob_ptr_n: HL = &mobs[MOBS_N]; mob_ptr: A = index -> HL
mob_ptr_n:      ld      a, (MOBS_N)
mob_ptr:        ld      l, a
                ld      h, 0
                ld      e, l
                ld      d, h
                add     hl, hl
                add     hl, de
                add     hl, hl          ; *6
                ld      de, MOBS
                add     hl, de
                ret

; ---------------------------------------------------------------- door links and buttons
; get_doorlink_timer: A = index -> A = timer (5 bits)
get_doorlink_timer:
                ld      hl, DL2
                call    k_tbl
                and     0x1f
                ret
; set_doorlink_timer: A = index, B = value (low 5 bits)
set_doorlink_timer:
                ld      hl, DL2
                add     a, l
                ld      l, a
                jr      nc, sdt1
                inc     h
sdt1:           ld      a, (hl)
                and     0xe0
                ld      c, a
                ld      a, b
                and     0x1f
                or      c
                ld      (hl), a
                ret
; trigger_button, do_trigger_list, trigger_gate: src/m4/buttons.asm (main since M8a part 24); died_on_button: src/m4/events.asm (the events overlay, W1; stub in ovl.asm)

; ---------------------------------------------------------------- loose floors
; make_loose_fall: A = modifier, at CURR_ROOM/CURR_TILEPOS
make_loose_fall:
                ld      (O_T1), a
                ld      a, (CURR_TILEPOS)
                ld      c, a
                ld      a, (CURR_ROOM)
                or      a
                ret     z
                call    o_ptrs
                bit     5, (hl)         ; "solid" loose floor
                ret     nz
                ld      a, (de)
                dec     a               ; (sbyte)mod <= 0  <=>  mod - 1 >= 0x7F (unsigned)
                cp      0x7f
                ret     c
                ld      a, (O_T1)
                ld      (de), a
                ld      a, (CURR_ROOM)
                ld      b, a
                ld      a, (CURR_TILEPOS)
                ld      c, a
                xor     a
                jp      add_trob
loose_make_shake:
                ld      a, (level_number)       ; (not on level 13)
                cp      13
                ret     z
                ld      a, (CURR_TILEPOS)
                ld      c, a
                ld      a, (CURR_ROOM)
                or      a
                ret     z
                call    o_ptrs
                ld      a, (de)
                or      a
                ret     nz
                ld      a, 0x80
                ld      (de), a
                ld      a, (CURR_ROOM)
                ld      b, a
                ld      a, (CURR_TILEPOS)
                ld      c, a
                ld      a, 1
                jp      add_trob
; do_knock: A = room, B = row
do_knock:       ld      (dk_room), a
                ld      a, b
                ld      (dk_row), a
                xor     a
                ld      (dk_col), a
dk_loop:        ld      a, (dk_col)
                ld      c, a
                ld      a, (dk_row)
                ld      b, a
                ld      a, (dk_room)
                call    k_get_tile
                cp      T_LOOSE
                call    z, loose_make_shake
                ld      hl, dk_col
                inc     (hl)
                ld      a, (hl)
                cp      10
                jr      nz, dk_loop
                ret
dk_room:        db      0
dk_row:         db      0
dk_col:         db      0
check_knock:    ld      a, (KNOCK)
                or      a
                ret     z
                ld      b, a
                xor     a
                ld      (KNOCK), a
                ld      a, (K_ROW)
                bit     7, b
                jr      nz, ckn1        ; knock down: own row
                dec     a               ; knock up: the row above
ckn1:           ld      b, a
                ld      a, (K_ROOM)
                jp      do_knock

; ---------------------------------------------------------------- mobs
do_mobs:        ld      a, (MOBS_N)
                ld      (MOB_N0), a
                or      a
                ret     z
                xor     a
                ld      (MOB_I), a
dm_loop:        ld      a, (MOB_I)
                ld      hl, MOB_N0
                cp      (hl)
                jr      nc, dm_compact
                call    mob_ptr
                ld      (MOB_P), hl
                call    move_mob
                call    check_loose_fall_on_kid
                ld      hl, MOB_I
                inc     (hl)
                jr      dm_loop
dm_compact:     ld      hl, MOBS
                ld      de, MOBS
                ld      a, (MOBS_N)
                ld      b, a
                ld      c, 0
dmc:            push    bc
                inc     hl
                inc     hl
                inc     hl
                ld      a, (hl)         ; speed
                dec     hl
                dec     hl
                dec     hl
                cp      0xff
                jr      z, dmc_skip
                ld      bc, 6
                ldir
                pop     bc
                inc     c
                jr      dmc_n
dmc_skip:       ld      bc, 6
                add     hl, bc
                pop     bc
dmc_n:          djnz    dmc
                ld      a, c
                ld      (MOBS_N), a
                ret
move_mob:       ld      ix, (MOB_P)
                ld      a, (ix+4)       ; type 0: loose floor
                or      a
                call    z, move_loose
                ld      ix, (MOB_P)
                ld      a, (ix+3)
                dec     a               ; speed <= 0  <=>  speed - 1 >= 0x7F
                cp      0x7f
                ret     c
                inc     (ix+3)
                ret
move_loose:     ld      ix, (MOB_P)
                ld      a, (ix+3)
                bit     7, a
                ret     nz
                cp      29
                jr      nc, ml1
                add     a, 3
                ld      (ix+3), a
ml1:            ld      a, (ix+1)
                add     a, (ix+3)
                ld      (ix+1), a
                ld      a, (ix+2)
                or      a
                jr      nz, ml2
                ld      a, (ix+1)       ; outside the level: stop at the bottom
                cp      210
                ret     c
                ld      (ix+3), -2
                ret
ml2:            ld      a, (ix+1)
                cp      226
                ret     nc
                ld      b, a
                ld      a, (ix+5)
                inc     a
                ld      hl, y_something
                call    k_tbl
                ld      c, a
                ld      a, b
                cp      c
                ret     c               ; still above the next row
                ; fell into a different row
                ld      a, (ix+0)
                rrca
                rrca
                and     0x3f
                ld      c, a
                ld      b, (ix+5)
                ld      a, (ix+2)
                call    k_get_tile
                ld      (O_T4), a
                cp      T_LOOSE
                call    z, loose_fall
                ld      a, (O_T4)
                or      a
                jr      z, ml_down
                cp      T_LOOSE
                jr      z, ml_down
                ld      ix, (MOB_P)
                ld      a, (ix+2)
                ld      b, (ix+5)
                call    knock_snd       ; (sound.asm: the crash, do_knock)
                ld      ix, (MOB_P)
                ld      a, (ix+5)
                inc     a
                ld      hl, y_something
                call    k_tbl
                ld      (ix+1), a
                ld      (ix+3), -2
                jp      loose_land
ml_down:        ld      ix, (MOB_P)
; mob_down_a_row: IX = mob
mob_down_a_row: inc     (ix+5)
                ld      a, (ix+5)
                cp      3
                ret     c
                ld      a, (ix+1)
                sub     192
                ld      (ix+1), a
                ld      (ix+5), 0
                ld      a, (ix+2)
                or      a
                ret     z
                call    links_of
                ld      (ix+2), e       ; room below
                ret
loose_land:     ld      ix, (MOB_P)
                xor     a
                ld      (O_T3), a       ; button type
                call    ll_tile
                cp      T_OPENER
                jr      nz, lld1
                ld      a, T_DEBRIS
                call    set_tile_cur
                ld      a, T_DEBRIS
                ld      (O_T3), a
                jr      ll2
lld1:            cp      T_CLOSER_
                jr      nz, ll3
ll2:            ld      a, (O_T3)
                ld      b, a
                ld      c, 0xff
                ld      a, 1
                call    trigger_button
                call    ll_tile
ll3:            cp      T_OPENER
                jr      z, ll_set
                cp      T_CLOSER_
                jr      z, ll_set
                cp      T_FLOOR
                jr      z, ll_set
                cp      T_SPIKE
                jr      z, ll_set
                cp      T_POTION
                jr      z, ll_set
                cp      T_TORCH
                jr      z, ll_torch
                cp      T_TORCH_DEBRIS
                ret     nz
ll_torch:       ld      a, T_TORCH_DEBRIS
                jp      set_tile_cur
ll_set:         ld      a, T_DEBRIS
                jp      set_tile_cur
ll_tile:        ld      ix, (MOB_P)
                ld      a, (ix+0)
                rrca
                rrca
                and     0x3f
                ld      c, a
                ld      b, (ix+5)
                ld      a, (ix+2)
                jp      k_get_tile
; loose_fall: the loose floor at CURR_ROOM/CURR_TILEPOS falls with the mob: the mob keeps falling at half
; speed and a copy one row lower is added (SDLPoP's order)
loose_fall:     ld      a, (CURR_TILEPOS)
                ld      c, a
                ld      a, (CURR_ROOM)
                push    bc
                call    remove_loose
                pop     bc
                ld      b, a
                ld      a, (CURR_ROOM)
                call    o_ptrs
                ld      a, b
                ld      (de), a
                ld      ix, (MOB_P)
                ld      a, (ix+3)
                sra     a
                ld      (ix+3), a
                ld      a, (MOBS_N)
                cp      MOBS_MAX
                ret     nc
                call    mob_ptr_n
                ex      de, hl
                ld      hl, (MOB_P)
                ld      bc, 6
                push    de
                ldir
                pop     ix              ; the copy
                ld      a, (ix+1)
                add     a, 6
                ld      (ix+1), a
                call    mob_down_a_row
                ld      hl, MOBS_N
                inc     (hl)
                ret
check_loose_fall_on_kid:
                ld      ix, (MOB_P)
                ld      a, (K_ROOM)
                cp      (ix+2)
                ret     nz
                ld      a, (ix+0)
                rrca
                rrca
                and     0x3f
                ld      b, a
                ld      a, (K_COL)
                cp      b
                ret     nz
                ld      a, (ix+1)       ; mob.y < kid.y
                ld      hl, K_Y
                cp      (hl)
                ret     nc
                ld      a, (K_Y)        ; kid.y - 30 < mob.y  (kid.y - 30 may be negative: then true)
                sub     30
                jr      c, fell_on_your_head
                cp      (ix+1)
                ret     nc
fell_on_your_head:
                ld      a, (level_number)       ; (level 13: also while running)
                cp      13
                ld      a, (K_FRAME)
                ld      (O_T2), a
                jr      z, foh1
                cp      5
                jr      c, foh1
                cp      15
                ret     c
foh1:           ld      a, (K_ACTION)
                cp      AC_TURN
                jr      z, foh2
                cp      AC_HANG_CLIMB
                ret     nc
foh2:           ld      a, (K_ROW)
                inc     a
                ld      hl, y_land
                call    k_tbl
                ld      (K_Y), a
                ld      a, 1
                call    take_hp
                or      a
                jr      z, foh_hurt
                ld      a, SQ_CRUSHED
                call    seqtbl_offset_char
                ld      a, (O_T2)
                cp      177
                ret     nz
                ld      a, -12
                call    char_dx_forward
                ld      (K_X), a
                ret
foh_hurt:       ld      a, (O_T2)
                cp      109
                ret     z
                call    get_tile_behind_char
                or      a
                jr      nz, foh3
                ld      a, -2
                call    char_dx_forward
                ld      (K_X), a
foh3:           ld      a, SQ_LOOSE_ON_KID
                jp      seqtbl_offset_char

; ---------------------------------------------------------------- spikes and chompers
; is_spike_harmful: the tile last read (CURR_ROOM/CURR_TILEPOS) -> A = 0 / 1 / 2
is_spike_harmful:
                call    k_modif
                or      a
                ret     z
                cp      0xff
                jr      z, ish0
                bit     7, a
                jr      nz, ish1
                cp      5
                jr      nc, ish0
                ld      a, 2
                ret
ish1:           ld      a, 1
                ret
ish0:           xor     a
                ret
spiked:         ld      a, 0xff
                call    set_mod_cur
                ld      a, (K_ROW)
                inc     a
                ld      hl, y_land
                call    k_tbl
                ld      (K_Y), a
                ld      a, (TILE_COL)
                add     a, FIRST_COL
                ld      hl, x_bump
                call    k_tbl
                add     a, 10
                ld      (K_X), a
                ld      a, 8
                call    char_dx_forward
                ld      (K_X), a
                xor     a
                ld      (K_FALLY), a
                ld      a, 48
                call    kill_snd        ; (sound.asm: take_hp(100), the sound)
                ld      a, SQ_SPIKED
                call    seqtbl_offset_char
                jp      play_seq
check_spiked:   ld      a, (K_COL)
                ld      c, a
                ld      a, (K_ROW)
                ld      b, a
                ld      a, (K_ROOM)
                call    k_get_tile
                cp      T_SPIKE
                ret     nz
                call    is_spike_harmful
                ld      b, a
                ld      a, (K_FRAME)
                ld      c, a
                ld      a, b
                cp      2
                jr      c, csp2
                ld      a, c            ; harmful >= 2 and running or starting a running jump
                cp      7
                jr      c, csp1
                cp      15
                jp      c, spiked
csp1:           cp      34
                jr      c, csp2
                cp      40
                jp      c, spiked
csp2:           ld      a, b
                or      a
                ret     z
                ld      a, c            ; landing from a jump
                cp      43
                jp      z, spiked
                cp      26
                jp      z, spiked
                ret
; start_anim_spike: B = room, C = pos
start_anim_spike:
                ld      (O_T1), bc
                ld      a, b
                call    o_ptrs
                ld      a, (de)
                or      a
                jr      z, sas0
                bit     7, a
                ret     z               ; > 0: already moving
                cp      0xff
                ret     z               ; disabled
                ld      a, 0x8f
                ld      (de), a
                ret
sas0:           ld      bc, (O_T1)
                jp      sas_snd         ; (sound.asm: the sound, add_trob)
check_spike_below:
                ld      hl, (CX_RIGHT)  ; columns of char_x_right - 7 and char_x_left - 7 (16-bit: x_left may be < 0)
                ld      de, -7
                add     hl, de
                call    get_tile_div_mod
                bit     7, a
                ret     nz
                ld      (csb_right), a
                ld      hl, (CX_LEFT)
                ld      de, -7
                add     hl, de
                call    get_tile_div_mod
                ld      (csb_col), a
csb_col_loop:   ld      a, (csb_right)
                ld      b, a
                ld      a, (csb_col)
                sub     b               ; col > right (signed, small) -> done
                jr      z, csb_go
                jp      p, csb_done
csb_go:         ld      a, (K_ROW)
                ld      (csb_row), a
csb_row_loop:   ld      a, (csb_col)
                ld      c, a
                ld      a, (csb_row)
                ld      b, a
                ld      a, (K_ROOM)
                call    k_get_tile
                cp      T_SPIKE
                jr      nz, csb_nf
                ld      a, (CURR_ROOM)
                ld      b, a
                ld      a, (CURR_TILEPOS)
                ld      c, a
                call    start_anim_spike
                jr      csb_next
csb_nf:         call    k_is_floor
                jr      nz, csb_next
                ld      a, (CURR_ROOM)
                or      a
                jr      z, csb_next
                ld      hl, K_ROOM
                cp      (hl)
                jr      nz, csb_next
                ld      hl, csb_row
                inc     (hl)
                jr      csb_row_loop
csb_next:       ld      hl, csb_col
                inc     (hl)
                jr      csb_col_loop
csb_done:       ret
csb_right:      db      0
csb_col:        db      0
csb_row:        db      0
; start_chompers: the chompers in the kid's row start (SDLPoP start_chompers)
start_chompers: ld      a, (K_ROW)
                cp      3
                ret     nc              ; (also negative rows)
                ld      a, (K_ROOM)
                or      a
                ret     z
                ld      (CURR_ROOM), a
                ld      a, 15
                ld      (sc_timing), a
                ld      a, (K_ROW)
                ld      hl, tbl_line
                call    k_tbl
                ld      (sc_pos), a
                ld      b, 10
sc_loop:        push    bc
                ld      a, (sc_pos)
                call    get_curr_tile
                cp      T_CHOMPER
                jr      nz, sc_next
                ld      a, (O_CMOD)
                and     0x7f
                jr      z, sc_go
                cp      6
                jr      c, sc_next
sc_go:          ld      a, (O_CMOD)     ; start_anim_chomper: only if 0 or >= 6
                or      a
                jr      z, sc_set
                cp      6
                jr      c, sc_tim
sc_set:         and     0x80
                ld      hl, sc_timing
                or      (hl)
                push    af
                ld      a, (sc_pos)
                ld      c, a
                ld      a, (CURR_ROOM)
                call    o_ptrs
                pop     af
                ld      (de), a
                ld      a, (CURR_ROOM)
                ld      b, a
                ld      a, (sc_pos)
                ld      c, a
                ld      a, 1
                call    add_trob
sc_tim:         ld      a, (sc_timing)
                sub     3
                cp      6
                jr      nc, sc_t1
                add     a, 10
sc_t1:          ld      (sc_timing), a
sc_next:        ld      hl, sc_pos
                inc     (hl)
                pop     bc
                djnz    sc_loop
                ret
sc_timing:      db      0
sc_pos:         db      0

; ---------------------------------------------------------------- pressing, items
check_press:    ld      a, (K_FRAME)
                ld      b, a
                cp      87
                jr      c, cpr1
                cp      100
                jr      c, cpr_above
cpr1:           cp      135
                jr      c, cpr2
                cp      141
                jr      c, cpr_above
cpr2:           ld      a, (K_ACTION)
                cp      AC_TURN
                jr      z, cpr3
                cp      AC_BUMPED
                jr      z, cpr3
                cp      AC_HANG_CLIMB
                ret     nc
cpr3:           ld      a, b
                cp      79
                jr      nz, cpr4
                call    get_tile_above_char
                cp      T_LOOSE
                jr      nz, cpr4
                ld      a, 1
                jp      make_loose_fall
cpr4:           ld      a, (CF_FLAGS)
                and     F_NEEDS_FLOOR
                ret     z
                call    get_tile_at_char
                jr      cpr_tile
cpr_above:      call    get_tile_above_char
cpr_tile:       ld      a, (CURR_TILE2)
                cp      T_OPENER
                jr      z, cpr_button
                cp      T_CLOSER_
                jr      z, cpr_button
                cp      T_LOOSE
                ret     nz
                ld      a, 1
                ld      (IS_GUARD_NOTICE), a
                jp      make_loose_fall
cpr_button:     ld      a, (K_ALIVE)
                bit     7, a
                jp      z, died_on_button
                ld      b, 0
                ld      c, 0xff
                ld      a, 1
                jp      trigger_button
; check_get_item: A = 1 if an item is being taken
check_get_item: call    get_tile_at_char
                cp      T_POTION
                jr      z, cgi1
                cp      T_SWORD
                jr      nz, cgi2
cgi1:           call    get_tile_behind_char
                call    k_is_floor
                jr      z, cgi_no
                ld      a, -14
                call    char_dx_forward
                ld      (K_X), a
                call    load_fram_det_col
cgi2:           call    get_tile_infrontof_char
                cp      T_POTION
                jr      z, cgi_yes
                cp      T_SWORD
                jr      nz, cgi_no
cgi_yes:        call    get_item
                ld      a, 1
                ret
cgi_no:         xor     a
                ret
; get_item, do_pickup: src/m4/rare.asm (the rare overlay, W1; the stub get_item in ovl.asm)
; proc_get_object: src/m4/events.asm (the events overlay)

; anim_tile_modif (room entry): src/m4/genter.asm (the guard-enter overlay)
; (check_the_end: guard.asm)
                if not defined GAME_OVL         ; (m4test's trace; the game's harness computes it: M8a part 19)
; room_checksum: HL = sum of the kid room's tiles + 3 x modifiers (the trace's last field)
room_checksum:  ld      a, (K_ROOM)
                or      a
                jr      z, rcs0
                cp      25
                jr      nc, rcs0
                call    tile_base
                ld      bc, 0
                ld      a, 30
rcs1:           push    af
                ld      a, (hl)
                add     a, c
                ld      c, a
                jr      nc, rcs2
                inc     b
rcs2:           ld      a, (de)
                push    hl
                ld      l, a
                ld      h, 0
                push    de
                ld      d, h
                ld      e, l
                add     hl, hl
                add     hl, de
                add     hl, bc
                ld      b, h
                ld      c, l
                pop     de
                pop     hl
                inc     hl
                inc     de
                pop     af
                dec     a
                jr      nz, rcs1
                ld      h, b
                ld      l, c
                ret
rcs0:           ld      hl, 0
                ret
                endif
