; ---------------------------------------------------------------- the shadow's start (seg002 do_init_shad)
; Included by both W1 overlays that start a shadow (genter.asm check_shadow, events.asm autocontrol_shadow level 12):
; one W1 overlay cannot call the other. m4test includes it once.
; do_init_shad: HL = frame x y direction col row action, A = sequence
do_init_shad:   push    af
                ld      de, KV
                ld      bc, 7
                ldir
                pop     af
                call    seqtbl_offset_char
                ld      a, CHARID_SHADOW
                ld      (K_CHARID), a
                xor     a
                ld      (DEMO_TIME), a
                ld      a, 3
                ld      (GUARD_SKILL), a
                ld      a, 4
                ld      (GUARDHP_DELTA), a
                ld      (GUARDHP_CURR), a
                ld      (GUARDHP_MAX), a
                jp      saveshad
init_shad_6:    db      0x0f, 0x51, 0x76, 0, 0, 1, 0
init_shad_5:    db      0x0f, 0x37, 0x37, 0, 0xff, 0, 0
init_shad_12:   db      0x0f, 0x51, 0xe8, 0, 0, 0, 0
