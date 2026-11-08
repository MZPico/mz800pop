; ---------------------------------------------------------------- PR_TAB: the wall pattern's random draws mod 140
; pr_build: for each seed 0..PR_SEEDS-1 the first PR_DRAWS draws of the generator (src/m3/room.asm pr_slow) mod 140, into
; PR_TAB (RAM-disk page PR_PAGE, runtime; low RAM 0x0500 until M8a part 19); SEED is kept. Built once: by pr_start at
; the first wall pattern (the test programs), or at every start of the game program (after a PRES swap too: PRES uses
; page 6 0x0000-0x287F as scratch) from the level-start overlay (src/m4/gstart.asm, GAME_OVL: pr_start does not check
; pr_ok then).
pr_build:       ld      hl, 0
                ld      (pr_ptr), hl
                ld      hl, (SEED)
                push    hl
                ld      hl, (SEED+2)
                push    hl
                ld      a, PR_PAGE              ; the draws go to the RAM disk in order (pr_slow does not touch it)
                ld      de, PR_TAB
                call    far_seek
                xor     a
pb_s:           push    af
                ld      l, a
                ld      h, 0
                ld      (SEED), hl
                ld      hl, 0
                ld      (SEED+2), hl
                ld      b, PR_DRAWS
pb_d:           xor     a                       ; step the generator; its high word mod 140
                call    pr_slow
                push    bc
                push    hl
                ld      hl, (SEED+2)
                xor     a
                ld      b, 16
pb_m:           add     hl, hl
                rla
                jp      c, pb_ms                ; (A + 256 >= 140)
                cp      140
                jp      c, pb_mn
pb_ms:          sub     140
pb_mn:          djnz    pb_m
                pop     hl
                pop     bc
                out     (RD_DATA), a
                djnz    pb_d
                pop     af
                inc     a
                cp      PR_SEEDS
                jp      nz, pb_s
                pop     hl
                ld      (SEED+2), hl
                pop     hl
                ld      (SEED), hl
                ld      a, 1
                ld      (pr_ok), a
                ret
