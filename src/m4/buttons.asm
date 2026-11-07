; ---------------------------------------------------------------- buttons (seg007 trigger_button, do_trigger_list, trigger_gate)
; Resident in the main block since M8a part 14 (from the events overlay, src/m4/events.asm, where they were 2026-11-01..07):
; check_press calls trigger_button every tick while the kid stands on a plate, and with the events overlay in W1 for it
; a gate or the level door moving at the same time (the animation overlay, src/m4/colshift.asm) would load both overlays
; every tick (~0.6 frames). Called from the kid (check_press), a guard, a loose floor and lr_special; levelstart.asm (W2),
; autocontrol_shadow and died_on_button (the events overlay) too. tb_type .. dt_res are scratch of one call.
trigger_button: ld      (TB_SND), a
                ld      (O_T1), bc
                ld      a, (CURR_TILEPOS)
                call    get_curr_tile
                ld      bc, (O_T1)
                ld      a, b
                or      a
                jr      nz, tb1
                ld      a, (O_CTILE)
                ld      b, a
tb1:            ld      a, c
                cp      0xff
                jr      nz, tb2
                ld      a, (O_CMOD)
                ld      c, a
tb2:            ld      (tb_type), bc   ; C -> tb_type (modifier), B -> tb_type+1 (button type)
                ld      a, c
                call    get_doorlink_timer
                cp      0x1f
                ret     z               ; jammed
                ld      (O_T3), a       ; old timer
                ld      a, (tb_type)
                ld      b, 5
                call    set_doorlink_timer
                ld      a, (O_T3)
                cp      2
                jr      nc, tb3
                ld      a, (CURR_ROOM)
                ld      b, a
                ld      a, (CURR_TILEPOS)
                ld      c, a
                ld      a, 1
                call    add_trob
                call    tb_notice       ; (sound.asm: a guard notices, the click)
tb3:            ld      a, (tb_type)
                ld      (dt_index), a
; do_trigger_list: dt_index = first link, tb_type+1 = button type
do_trigger_list:
                ld      a, (dt_index)
                ld      hl, DL1
                call    k_tbl
                ld      (O_T2), a       ; d1
                ld      a, (dt_index)
                ld      hl, DL2
                call    k_tbl
                and     0xe0
                rrca
                rrca
                rrca
                ld      b, a
                ld      a, (O_T2)
                and     0x60
                rrca
                rrca
                rrca
                rrca
                rrca
                add     a, b
                ld      (dt_room), a
                ld      a, (O_T2)
                and     0x1f
                ld      (dt_pos), a
                ld      a, (dt_room)
                or      a
                jr      z, dt_next
                ld      a, (dt_pos)
                ld      c, a
                ld      a, (dt_room)
                call    o_ptrs
                ld      a, (hl)
                and     0x1f
                cp      T_GATE
                jr      z, dt_gate
                cp      T_LEVELDOOR_L
                jr      nz, dt_next
                ld      a, (de)         ; level door: start opening if closed
                or      a
                jr      nz, dt_next
                ld      a, 1
                ld      (dt_res), a
                jr      dt_add
dt_gate:        call    trigger_gate    ; DE = &modifier -> A = result (0xff none), also dt_res
                cp      0xff
                jr      z, dt_next
dt_add:         ld      a, (dt_room)
                ld      b, a
                ld      a, (dt_pos)
                ld      c, a
                ld      a, (dt_res)
                call    add_trob
dt_next:        ld      a, (O_T2)
                bit     7, a
                ret     nz
                ld      hl, dt_index
                inc     (hl)
                jp      do_trigger_list
; trigger_gate: DE = &modifier of the gate, (tb_type+1) = button type -> A = trob type or 0xff, also in dt_res
trigger_gate:   ld      a, (tb_type+1)
                cp      T_OPENER
                jr      nz, tg2
                ld      a, (de)
                cp      0xff
                jr      z, tg_none
                cp      188
                jr      c, tgt1
                ld      a, 238
                ld      (de), a
                jr      tg_none
tgt1:            add     a, 3
                and     0xfc
                ld      (de), a
                ld      a, 1
                jr      tg_ret
tg2:            cp      T_DEBRIS
                jr      nz, tg3
                ld      a, (de)
                cp      188
                ld      a, 2
                jr      c, tg_ret
                ld      a, 0xff
                ld      (de), a
                jr      tg_none
tg3:            ld      a, (de)
                or      a
                jr      z, tg_none
                ld      a, 3
                jr      tg_ret
tg_none:        ld      a, 0xff
tg_ret:         ld      (dt_res), a
                ret
tb_type:        dw      0
dt_index:       db      0
dt_room:        db      0
dt_pos:         db      0
dt_res:         db      0
