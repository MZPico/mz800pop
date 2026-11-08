; ---------------------------------------------------------------- precomputed room lists: the compare (M8a part 22)
; rl_cmp (src/m3/rlists.asm's header): which tiles of a room differ from the canonical state the stored lists were
; built for. The M3 test program includes it with rlists.asm; the game runs it from low RAM (src/m4/rllow.asm at
; RL_LOWCODE, loaded by the room-list fetch with the level's blob: it runs only when a blob is there).
; rl_cmp: RL_REGEN, RL_OVB, RL_OVF from the 64 slots (rl_runs, below)
rl_cmp:         ld      hl, RL_REGEN
                ld      de, RL_REGEN + 1
                ld      bc, 119
                ld      (hl), 0
                ldir
                ld      a, (rl_room)            ; the slots' rooms: R, its left, below, below-left (load_room_links)
                ld      (RL_ROOMS), a
                ld      (R_ROOM), a
                call    load_room_links
                ld      hl, RL_ROOMS + 1
                call    rl_rooms
                ld      a, (R_A)                ; above, and as drawn from there: its left, below, below-left
                ld      (hl), a
                inc     hl
                ld      (R_ROOM), a
                push    hl
                call    load_room_links
                pop     hl
                call    rl_rooms
                ld      a, (rl_room)
                ld      (R_ROOM), a
                call    load_room_links
                ld      a, (RL_LEVEL)           ; the blueprint: RL_BP_ADDR + 2305 n (load_level's product)
                ld      e, a
                ld      d, 0
                add     a, a
                add     a, a
                add     a, a
                add     a, e
                ld      h, a
                ld      l, 0
                add     hl, de
                ld      de, RL_BP_ADDR - LEVEL
                add     hl, de
                ld      (rl_lvb), hl
                ld      hl, rl_runs
rlc_run:        ld      a, (hl)                 ; a run: selector, first row, rows, first column, columns
                cp      0xff
                ret     z
                ld      (rl_s), a
                push    hl
                ld      e, a
                ld      d, 0
                ld      hl, RL_ROOMS
                add     hl, de
                ld      a, (hl)
                pop     hl
                or      a                       ; (no room: the default tiles, as in the stored lists)
                jr      nz, rlc_r1
                ld      de, 5
                add     hl, de
                jr      rlc_run
rlc_r1:         ld      (rl_sr), a
                push    hl
                call    rl_bp                   ; the room's tiles: now (rl_tb) and in the blueprint (RL_BPB)
                pop     hl
                inc     hl
                ld      a, (hl)
                ld      (rl_r), a
                inc     hl
                ld      b, (hl)
                inc     hl
                ld      c, (hl)
                inc     hl
                ld      e, (hl)
                inc     hl
                push    hl
rlc_row:        push    bc
                push    de
                ld      a, c
                ld      (rl_c), a
rlc_col:        push    de
                call    rl_slot
                pop     de
                ld      hl, rl_c
                inc     (hl)
                dec     e
                jr      nz, rlc_col
                pop     de
                pop     bc
                ld      hl, rl_r
                inc     (hl)
                djnz    rlc_row
                pop     hl
                jr      rlc_run
rl_rooms:       ld      a, (R_L)                ; (HL) = R_L, R_B, R_BL
                ld      (hl), a
                inc     hl
                ld      a, (R_B)
                ld      (hl), a
                inc     hl
                ld      a, (R_BL)
                ld      (hl), a
                inc     hl
                ret
; rl_bp: room rl_sr: rl_tb = its fg bytes in LEVEL, RL_BPB = its 30 fg bytes, then its 30 bg bytes in the blueprint
rl_bp:          ld      a, (rl_sr)
                call    tile_base
                ld      (rl_tb), hl
                ld      de, (rl_lvb)
                add     hl, de
                push    hl
                ex      de, hl
                ld      a, RL_BP_PAGE
                call    far_seek
                ld      hl, RL_BPB
                ld      bc, 30 * 256 + RD_DATA
                inir
                pop     hl
                ld      de, 720
                add     hl, de
                ex      de, hl
                ld      a, RL_BP_PAGE
                call    far_seek
                ld      hl, RL_BPB + 30
                ld      bc, 30 * 256 + RD_DATA
                inir
                ret
; rl_slot: the tile (rl_sr, rl_r, rl_c) as drawn now against the canonical state
rl_slot:        ld      a, (rl_r)
                add     a, a
                ld      e, a
                add     a, a
                add     a, a
                add     a, e
                ld      e, a
                ld      a, (rl_c)
                add     a, e
                ld      e, a
                ld      d, 0                    ; DE = pos
                ld      hl, RL_BPB
                add     hl, de
                ld      a, (hl)
                and     0x1f
                ld      b, a                    ; B = the canonical type
                push    de
                ld      de, 30
                add     hl, de
                pop     de
                ld      c, (hl)                 ; C = the blueprint's modifier: alter_mods' rule
                cp      T_GATE
                jr      nz, rlc_c1
                ld      a, c
                cp      1
                ld      c, 0
                jr      nz, rlc_cur
                ld      c, 188
                jr      rlc_cur
rlc_c1:         cp      T_LOOSE
                jr      z, rlc_c0
                cp      T_TORCH
                jr      z, rlc_c0
                cp      T_TORCH_DEBRIS
                jr      z, rlc_c0
                cp      T_POTION
                jr      nz, rlc_cur
                ld      a, c
                add     a, a
                add     a, a
                add     a, a
                or      1                       ; (bubble frame 1: tools/roomlists.py canonical)
                ld      c, a
                jr      rlc_cur
rlc_c0:         ld      c, 0
rlc_cur:        ld      hl, (rl_tb)             ; the tile now: as get_tile draws it
                add     hl, de
                ld      a, (hl)
                and     0x1f
                ld      d, a
                push    bc
                ld      bc, 720
                add     hl, bc
                pop     bc
                ld      e, (hl)                 ; D, E = type, modifier now (A = the type)
                cp      T_OPENER
                jr      z, rlc_btn
                cp      T_CLOSER_R
                jr      nz, rlc_cmp
rlc_btn:        push    bc                      ; a button: pressed by its door-link timer (get_tile)
                ld      a, (rl_r)
                ld      b, a
                ld      a, (rl_c)
                ld      c, a
                ld      a, (rl_sr)
                ld      e, 0
                call    get_tile
                pop     bc
rlc_cmp:        ld      a, d                    ; D = type, E = modifier now; B, C canonical
                cp      b
                jr      nz, rlc_diff
                cp      T_WALL                  ; a wall keeps the modifier alter_mods gave it
                ret     z
                ld      a, e
                cp      c
                ret     z
                push    de
                push    bc
                call    rl_deps
                pop     bc
                pop     de
                ld      a, (rl_f)
                ld      h, a                    ; H = the slot's patch rules (rl_deps)
                ld      a, d
                cp      T_TORCH
                jr      z, rlc_torch
                cp      T_TORCH_DEBRIS
                jr      z, rlc_torch
                cp      T_POTION
                jr      nz, rlc_dif2
                bit     3, h                    ; a potion of the room: its bubble (bubble_redraw's rule)
                jr      z, rlc_dif2
                ld      a, e
                xor     c
                and     0xf8
                jr      nz, rlc_dif2
                ld      a, e
                and     7
                jr      z, rlc_dif2             ; (frame 0 draws no bubble)
                ld      hl, bubble_var
                call    tab_get
                ld      hl, RL_OVF
                jr      rlc_ov1
rlc_torch:      ld      a, h                    ; the flame (torch_redraw's rule; the canonical modifier 0 < 9)
                and     7
                jr      z, rlc_dif2
                bit     2, h
                ret     nz                      ; not drawn on this screen
                ld      a, e
                cp      9
                jr      nc, rlc_dif2            ; no flame (another record count)
                inc     a
                bit     1, h
                ld      hl, RL_OVB
                jr      z, rlc_ov1              ; the left room's column 9: our column 0 draws it (d1)
                ld      e, a                    ; our torch: the tile on its right (d2)
                ld      a, (rl_d + 1)
                jr      rlc_ov2
rlc_ov1:        ld      e, a
                ld      a, (rl_d)
rlc_ov2:        add     a, l                    ; (the tables do not cross a page)
                ld      l, a
                ld      (hl), e
                ret
rlc_diff:       call    rl_deps
rlc_dif2:       ld      hl, rl_d                ; every tile that reads this one: regenerate
                ld      b, 3
rlcd_1:         ld      a, (hl)
                inc     hl
                cp      40
                jr      nc, rlcd_2
                ex      de, hl
                ld      hl, RL_REGEN
                add     a, l
                ld      l, a
                ld      (hl), 1
                ex      de, hl
rlcd_2:         djnz    rlcd_1
                ret
; rl_deps: rl_d = the tiles that read the slot's tile (d1 its own, d2 the one on its right: TILE_LEFT, d3 the one
; above-right: ROWBELOW; 255 none), rl_f = its patch rules (bit 0: a torch's flame is drawn by d1, bit 1: by d2,
; bit 2: a torch's modifier draws nothing here, bit 3: a potion's bubble is d1's)
rl_deps:        ld      hl, rl_d
                ld      a, 255
                ld      (hl), a
                inc     hl
                ld      (hl), a
                inc     hl
                ld      (hl), a
                ld      a, (rl_c)
                ld      c, a
                ld      a, (rl_r)
                ld      b, a
                add     a, a
                ld      e, a
                add     a, a
                add     a, a
                add     a, e
                ld      e, a                    ; E = 10 row
                ld      a, (rl_s)
                or      a
                jr      nz, rdp_1
                ld      a, e                    ; 0: our tile (row, col)
                add     a, c
                ld      (rl_d), a
                ld      e, a
                ld      a, 0x0c
                ld      (rl_f), a
                ld      a, c
                cp      9
                ret     z
                ld      a, 0x0a
                ld      (rl_f), a
                ld      a, e
                inc     a
                ld      (rl_d + 1), a
                ld      a, b
                or      a
                ret     z
                ld      a, e
                sub     9
                ld      (rl_d + 2), a
                ret
rdp_1:          dec     a
                jr      nz, rdp_2
                inc     a                       ; 1: the left room's (row, 9): our (row, 0), (row - 1, 0)
                ld      (rl_f), a
                ld      a, e
                ld      (rl_d), a
                or      a
                ret     z
                sub     10
                ld      (rl_d + 1), a
                ret
rdp_2:          ld      e, a
                ld      a, 4
                ld      (rl_f), a
                ld      a, e
                dec     a
                jr      nz, rdp_3
                ld      a, c                    ; 2: below's (0, col): our (2, col + 1)
                add     a, 21
                ld      (rl_d), a
                ret
rdp_3:          dec     a
                jr      nz, rdp_4
                ld      a, 20                   ; 3: below-left's (0, 9): our (2, 0)
                ld      (rl_d), a
                ret
rdp_4:          dec     a
                jr      nz, rdp_5
                ld      a, c                    ; 4: above's (2, col): the row above's col, col + 1
                add     a, 30
                ld      (rl_d), a
                ld      a, c
                cp      9
                ret     z
                add     a, 31
                ld      (rl_d + 1), a
                ret
rdp_5:          dec     a
                jr      z, rdp_30               ; 5: above's left room (2, 9): the row above's 0
                dec     a
                jr      nz, rdp_30              ; 7: above's below-left room (0, 9): the row above's 0
                ld      a, c                    ; 6: above's below room (0, col): the row above's col + 1
                add     a, 31
                ld      (rl_d), a
                ret
rdp_30:         ld      a, 30
                ld      (rl_d), a
                ret
