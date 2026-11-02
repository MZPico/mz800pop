; ---------------------------------------------------------------- hit points (bottom strip, SDLPoP draw_kid_hp): the rare overlay
; Split out of src/m4/game.asm (2026-11-01, the memory reclaim): the kid's strip (hp_redraw = hpd_go, from hp_draw when the hit
; points shown change) and hp_strip (also the guard's strip, overlay.asm ghp_draw). Both run through the stubs in src/m4/ovl.asm
; (window W1, src/m4/ovl_rare.asm). The variables HP_VARS are low RAM (game.asm): ghp_draw sets hp_n, hp_nf, hp_base and hp_pf
; before the overlay is loaded, so they cannot live in the overlay image.
; the kid's icon i at x = 7 i, y = 194: full while i < curr, else empty; drawn in two compose chunks (bytes 0-7, 8-9).
hp_redraw:
hpd_go:         ld      a, (HITP_CURR)
                ld      (HP_SHOWN), a
                ld      (hp_nf), a
                ld      a, (HITP_MAX)
                ld      (HP_SHOWN+1), a
                ld      (hp_n), a
                ld      hl, hp_full
                ld      (hp_pf), hl
                xor     a
                ld      (hp_base), a
                ld      bc, 0x0800
                call    hp_strip
                ld      bc, 0x0208
; hp_strip: C = byte column, B = width: the chunk of the strip (rows 194-198) black, then hp_n icons (i < hp_nf: hp_pf,
; else hp_empty; 5 rows x 4 planes, plane-major) at x = 7 i (hp_base 0) or 314 - 7 i (hp_base 32), blit
hp_strip:       ld      a, c
                ld      (CRX), a
                ld      a, b
                ld      (CRW), a
                ld      a, 194
                ld      (CRY), a
                ld      a, 5
                ld      (CRH), a
                ld      hl, COMPOSE_A
                ld      (V_COMPOSE), hl
                ld      d, b
                ld      b, c
                ld      c, 194
                ld      e, 5
                call    fill_black
                xor     a
                ld      (hp_i), a
hpc_l:          ld      a, (hp_i)
                ld      hl, hp_n
                cp      (hl)
                jp      nc, blit
                ld      b, a
                ld      hl, hp_nf
                cp      (hl)
                ld      hl, (hp_pf)
                jr      c, hpc_p
                ld      hl, hp_empty
hpc_p:          ld      (hp_pat), hl
                ld      a, b            ; x = 7 i, or 314 - 7 i = 256 + 58 - 7 i
                add     a, a
                add     a, a
                add     a, a
                sub     b
                ld      b, a
                ld      a, (hp_base)
                or      a
                ld      a, b
                jr      z, hpc_x
                neg
                add     a, 58
hpc_x:          ld      b, a
                and     7
                ld      (hp_sh), a
                ld      a, b
                sra     a
                sra     a
                sra     a
                ld      hl, hp_base
                add     a, (hl)
                ld      (hp_xb), a
                ld      c, 0            ; row
hpr:            ld      b, 0            ; plane
hpp:            ld      a, b            ; plane * 5 + row
                add     a, a
                add     a, a
                add     a, b
                add     a, c
                ld      hl, (hp_pat)
                call    k_tbl
                ld      l, a
                ld      h, 0
                ld      a, (hp_sh)
                or      a
                jr      z, hps_x
hps:            add     hl, hl
                dec     a
                jr      nz, hps
hps_x:          ld      e, l
                ld      d, h
                ld      a, (hp_xb)
                call    hp_or
                ld      e, d
                ld      a, (hp_xb)
                inc     a
                call    hp_or
                inc     b
                ld      a, b
                cp      4
                jr      nz, hpp
                inc     c
                ld      a, c
                cp      5
                jr      nz, hpr
                ld      hl, hp_i
                inc     (hl)
                jr      hpc_l
; hp_or: A = screen byte column, E = bits, B = plane, C = row: OR into the compose chunk if inside it
hp_or:          ld      hl, CRX
                sub     (hl)
                ret     c
                ld      hl, CRW
                cp      (hl)
                ret     nc
                ld      l, a
                ld      a, c
                add     a, a
                add     a, a
                add     a, a
                add     a, l
                ld      l, a            ; row * 8 + column
                ld      a, b
                add     a, a
                ld      h, a            ; plane * 512
                push    de
                ld      de, (V_COMPOSE)
                add     hl, de
                pop     de
                ld      a, (hl)
                or      e
                ld      (hl), a
                ret
