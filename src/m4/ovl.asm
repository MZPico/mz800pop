; ---------------------------------------------------------------- code overlays (RAM disk -> fixed windows)
; Code that does not run every tick lives in the RAM disk and is copied into a window of main RAM when called:
;   W1 OVL_W1 .. OVL_W1_END (top of the main code area): code that runs on events during play. The window keeps its
;      overlay (ovl_cur1) until another W1 overlay is called, so a call to the loaded one costs nothing.
;   W2 OVL_W2 .. OVL_W2_END (COMPOSE_A/COMPOSE_B): code that runs while nothing is composed (a level start, the
;      bottom text after the tick's drawing, the save at a tick start after pend_flush). The compose buffers overwrite
;      it at the next draw, so a W2 overlay is loaded at every call.
;   WF OVL_WF .. OVL_W2_END (W2's top): the fill overlay, loaded by the level-start overlay's code below it (gstart.asm
;      fs_ovl); its image is in RAM-disk page OVL_FILL_PAGE, not in the overlay area (its own ovl_rd_* symbols).
; Overlay k is a separate pasmo assembly (src/m4/ovl_*.asm) at its window, starting with a jump table (entry j at
; window + 3 j). It sees every resident symbol through an include of equ's generated from build/m4game.sym
; (tools/ovltool.py equ). tools/ovltool.py pack puts the images and the table below into one file
; (build/m4ovl.bin) that the harness (tests/m4_game.py setup) and later the floppy loader write to the RAM disk at
; OVL_RD_PAGE:OVL_RD_TAB. Table entry k (8 bytes): page, address (2), length (2), window address (2), 0.
; Resident code calls an entry through a stub here (loads the overlay, then jumps to the entry). Code inside an
; overlay calls its own routines directly; resident code that the overlay's own code reaches may jump back into
; the loaded overlay through the entry address without a stub (rr_bkt_ent: only while run_ops runs).
;
; Adding an overlay:
;  1. Move the code to its own include file (keep it out of the resident program; programs without the loader,
;     like the M3 tests and m4test, include that file directly). Data in an overlay is lost when the window is
;     reloaded: keep variables that must survive a call resident, and no self-modified state across calls.
;  2. Write src/m4/ovl_<name>.asm like ovl_room.asm: the generated equ include, org of its window,
;     `ovl_id equ OVL_<NAME>`, ovl_entry: the jump table, the code, the window size .error guard.
;  3. Here: an id OVL_<NAME> (next free number < OVL_MAX) and per entry a stub (push af / ld a, id / call ovl_w1
;     or ovl_w2 / pop af / jp window + 3 j). Stubs keep every register, so the entry's arguments pass through.
;  4. Makefile: the overlay's rules like build/ovl_room.* and its .bin in the build/m4ovl.bin pack line.
;  5. Resident code must not fall through into, or keep return addresses inside, an overlay that another call can
;     replace (a W1 overlay must not call another W1 overlay's entry; W2 code must not use the compose buffers).
;     Calling the loaded overlay's own stub again from resident code it reaches is fine (ovl_w1 loads nothing then):
;     the events overlay's autocontrol_shadow reaches play_seq, whose item step calls proc_get_object's stub.
OVL_W1          equ     0x7c00
OVL_W1_END      equ     0x8000
OVL_W2          equ     0xa000          ; COMPOSE_A, COMPOSE_B (SPRBUF_A at 0xB000 is kept)
OVL_W2_END      equ     0xb000
OVL_RD_PAGE     equ     7               ; the overlay table and images: RAM-disk page 7 after the vizier guard set (0x8D80-0xD8F3;
OVL_RD_TAB      equ     0xd900          ; page 6 0xE300-0xFFFF until 2026-11-01, full then) (256-aligned: entry k at low byte 8 k)
OVL_RD_LAST     equ     0xffff          ; (the area ends with the page)
OVL_MAX         equ     14              ; table entries (the images follow the table)
OVL_ROOM        equ     0               ; W1: the full room draw (src/m4/ovl_room.asm)
OVL_LEVEL       equ     1               ; W2: load_level and the level start (src/m4/ovl_level.asm)
OVL_EVENT       equ     2               ; W1: potions, scripted shadows, the mirror jump (src/m4/ovl_event.asm)
OVL_TEXT        equ     3               ; W2: the bottom text line (src/m4/ovl_text.asm)
OVL_GLEAVE      equ     4               ; W1: the guard when the kid leaves a room (src/m4/ovl_gleave.asm)
OVL_GENTER      equ     5               ; W1: a new room's tiles and guard (src/m4/ovl_genter.asm)
OVL_SAVE        equ     6               ; W2: save / restore on the game disk (src/m4/ovl_save.asm)
OVL_KEYS        equ     7               ; W1: the keys (src/m4/ovl_keys.asm)
OVL_RARE        equ     8               ; W1: the hit point strips, an item taken, chomped (src/m4/ovl_rare.asm)
OVL_FILL        equ     9               ; WF: the frame store's fills (src/m4/ovl_fill.asm; 1 MB and more)
OVL_ANIM        equ     10              ; W1: animated tiles' steps as moving parts: gates, the level door (src/m4/ovl_anim.asm)
OVL_BTN         equ     11              ; W1: a button's press or release from cached pictures (src/m4/ovl_btn.asm)
OVL_DOOR        equ     12              ; W1: the level door's opening step (src/m4/ovl_door.asm)
OVL_FRM         equ     13              ; W1: choppers' and spikes' pre-drawn pictures (src/m4/ovl_frm.asm)
OVL_WF          equ     0xaa00          ; the fill overlay's window: W2's top (the level-start overlay ends below it)
OVL_FILL_PAGE   equ     6               ; its image in the RAM disk (written on every size; page 7's area is nearly full)
OVL_FILL_RD     equ     0xec00
OVL_BTN_PAGE    equ     6               ; the button overlay's image: its own place too (page 7's area is full with the
OVL_BTN_RD      equ     0xf200          ; cheat build's keys overlay), after the fill overlay's (written by the same writers)
OVL_DOOR_PAGE   equ     6               ; the door overlay's image: its own place too
OVL_DOOR_RD     equ     0xf600
OVL_FRM_PAGE    equ     0               ; the frames overlay's image: its own place too (page 0 0xA400-0xA7FF)
OVL_FRM_RD      equ     0xa400

; stubs: the entries resident code calls
draw_room_full: push    af              ; A = room
                ld      a, OVL_ROOM
                call    ovl_w1
                pop     af
                jp      OVL_W1 + 0
rr_bkt_ent      equ     OVL_W1 + 3      ; rr_bkt (room.asm rr_table while bkt_on: the room overlay is loaded)
set_flip:       push    af              ; A = UPSIDE: blit and the copy scheduler for the upside-down screen (or back)
                ld      a, OVL_ROOM
                call    ovl_w1
                pop     af
                jp      OVL_W1 + 6
text_draw:      ld      a, OVL_TEXT     ; the bottom text as the state says (src/m4/text.asm)
                call    ovl_w2
                jp      OVL_W2 + 0
load_level:     push    af              ; A = level number
                ld      a, OVL_LEVEL
                call    ovl_w2
                pop     af
                jp      OVL_W2 + 0
game_init:      push    af              ; a new game (kidsim's initial state)
                ld      a, OVL_LEVEL
                call    ovl_w2
                pop     af
                jp      OVL_W2 + 3
game_over:      ld      a, OVL_LEVEL    ; GAME_OVER: to the presentation program (M7), or (no launcher) A = 1
                call    ovl_w2
                jp      OVL_W2 + 6
game_start:     ld      a, OVL_LEVEL    ; the program's start (game.asm start; src/m4/gstart.asm: video, tables, interrupts,
                call    ovl_w2          ; the descriptors, PR_TAB, then game_init and load_level)
                jp      OVL_W2 + 9
; the events overlay's entries take no arguments: their stubs do not keep A
proc_get_object:
                ld      a, OVL_EVENT
                call    ovl_w1
                jp      OVL_W1 + 0
autocontrol_shadow:
                ld      a, OVL_EVENT
                call    ovl_w1
                jp      OVL_W1 + 3
jump_through_mirror:
                ld      a, OVL_EVENT
                call    ovl_w1
                jp      OVL_W1 + 6
; trigger_button (src/m4/buttons.asm) is resident since M8a part 24 (main, game.asm)
died_on_button: ld      a, OVL_EVENT
                call    ovl_w1
                jp      OVL_W1 + 12
; the guard-leave and guard-enter overlays' entries (src/m4/gleave.asm, genter.asm) take no arguments
guard_leaves:   ld      a, OVL_GLEAVE
                call    ovl_w1
                jp      OVL_W1 + 0
guard_fallout:  ld      a, OVL_GLEAVE
                call    ovl_w1
                jp      OVL_W1 + 3
room_entered:   ld      a, OVL_GENTER
                call    ovl_w1
                jp      OVL_W1 + 0
lrs_body:       push    af              ; A = leave direction (guard.asm lr_special; src/m4/genter.asm)
                ld      a, OVL_GENTER
                call    ovl_w1
                pop     af
                jp      OVL_W1 + 3
; the rare overlay (src/m4/hpstrip.asm, rare.asm): hp_strip keeps B (width), C (column); hp_redraw's stub is in game.asm
; (hp_draw falls into it), chomped's in kid2.asm (the low block)
hp_strip:       push    af
                ld      a, OVL_RARE
                call    ovl_w1
                pop     af
                jp      OVL_W1 + 3
get_item:       ld      a, OVL_RARE
                call    ovl_w1
                jp      OVL_W1 + 6
; the keys overlay: key_read at a tick start (src/m4/keyres.asm key_scan), key_logic at the control point (kid.asm)
key_read:       ld      a, OVL_KEYS
                call    ovl_w1
                jp      OVL_W1 + 0
key_logic:      ld      a, OVL_KEYS
                call    ovl_w1
                jp      OVL_W1 + 3
; the gate and door overlays (src/m4/colshift.asm): gate_fast, door_fast keep C, E (the new and the old modifier); carry set
; when the step is not theirs (the caller redraws as before)
gate_fast:      push    af
                ld      a, OVL_ANIM
                call    ovl_w1
                pop     af
                jp      OVL_W1 + 0
door_fast:      push    af
                ld      a, OVL_DOOR
                call    ovl_w1
                pop     af
                jp      OVL_W1 + 0
; the button overlay (src/m4/btnstep.asm): view.asm vrd_cht sends a button's press or release here; B = the tile byte
btn_redraw:     ld      a, (VS_KIND)
                or      a
                jp      nz, vrd_tile            ; (another room's button: as before, no overlay load)
                call    btn_fast
                ret     nc
                jp      vrd_tile
btn_fast:       push    af
                ld      a, OVL_BTN
                call    ovl_w1
                pop     af
                jp      OVL_W1 + 0
; the frames overlay (src/m4/frames.asm): spike.asm chomp_redraw, spike_redraw; B = the picture, C = 0 a chopper, 1 a
; spike; carry: not this way
frm_fast:       push    af
                ld      a, OVL_FRM
                call    ovl_w1
                pop     af
                jp      OVL_W1 + 0
; the save overlay (src/m4/save.asm, W2): save_key at a tick start (game.asm: Ctrl+G; keeps BC), load_saved (M7: the
; title's Ctrl+L; A = 0 loaded, 1 no valid save, 2 disk error)
save_key:       push    bc
                call    pend_flush      ; (no composed chunk may wait in W2)
                ld      a, OVL_SAVE
                call    ovl_w2
                call    OVL_W2 + 0
                pop     bc
                ret
load_saved:     ld      a, OVL_SAVE
                call    ovl_w2
                jp      OVL_W2 + 3

; ovl_w1: A = overlay id of window W1: load it unless it is there. ovl_w2: A = overlay id of window W2: load it.
; Both keep BC, DE, HL, IX, IY.
ovl_w1:         push    hl
                ld      hl, ovl_cur1
                cp      (hl)
                pop     hl
                ret     z
                ld      (ovl_cur1), a
ovl_w2:
; ovl_load: A = overlay id: copy its image from the RAM disk to its window (entry read from the table)
ovl_load:       push    bc
                push    de
                push    hl
                add     a, a
                add     a, a
                add     a, a
                ld      e, a
                ld      d, high OVL_RD_TAB
                ld      a, OVL_RD_PAGE
                call    far_seek
                ld      hl, ovl_ent
                ld      b, 7
                call    far_read
                ld      hl, ovl_ent
                ld      a, (hl)         ; page
                inc     hl
                ld      e, (hl)
                inc     hl
                ld      d, (hl)         ; RAM-disk address
                inc     hl
                ld      c, (hl)
                inc     hl
                ld      b, (hl)         ; length
                inc     hl
                push    af
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a            ; window
                pop     af
                call    far_copy
                pop     hl
                pop     de
                pop     bc
                ret
ovl_cur1:       db      0xff            ; the overlay in W1 (0xff: none)
ovl_ent:        ds      7
                if OVL_RD_TAB & 0xff
                .error the overlay table must be 256-aligned
                endif
