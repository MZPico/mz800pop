; ---------------------------------------------------------------- the keys: the resident part (M7 step 10, block 2)
; key_scan (game.asm get_controls, after read_inputs): none of the keys that do something is down: KEYS = 0 and the last
; key forgotten, at a small cost per tick. Else the keys overlay (W1) decides: src/m4/ovl_keys.asm. The column and bit of
; every key: docs/m7-design.md §18.
key_scan:       ld      a, (KEYMAT + 8)         ; BREAK, CTRL
                and     0xc0
                ld      b, a
                ld      a, (KEYMAT + 6)         ; SPACE
                and     0x10
                or      b
                ld      b, a
                ld      a, (KEYMAT + 0)         ; ENTER
                and     1
                or      b
                ld      b, a
                ld      a, (KEYMAT + 3)         ; L (of Shift+L)
                and     0x10
                or      b
                if defined CHEATS
                ld      hl, KEYMAT + 1          ; every letter, F1, F2
                ld      b, 5
ks_c:           or      (hl)
                inc     hl
                djnz    ks_c
                ld      hl, KEYMAT + 9
                or      (hl)
                endif
                jp      nz, key_read            ; (stub: the keys overlay)
                ld      (KEYS), a
                ld      (edge_bits), a
                ret
