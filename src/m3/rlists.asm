; ---------------------------------------------------------------- precomputed room lists (M8a part 22)
; Every room's op lists, built at build time by tools/roomlists.py for the level's canonical state (load_level's tiles:
; the blueprint, then alter_mods; potions at bubble frame 1), one blob a level in the RAM disk (RL_PAGE:RL_BASE). A room
; draw reads the room's lists back instead of room_ops (roomfull.asm draw_room_full: rl_load, rl_regen):
;   rl_cmp   the 64 tiles the room's lists read (rl_runs: its 30, the left room's column 9, the row below, the row
;            above and that row's own left and below neighbours), as drawn now (get_tile: buttons pressed by their
;            door-link timers) against the canonical state (the blueprint in the RAM disk, alter_mods' rule): a torch's
;            flame or a potion's bubble that changed is a new image id in its one record (RL_OVB / RL_OVF, op_patch's
;            rule), any other difference marks the tiles that read it (RL_REGEN)
;   rl_dec   the room's stream: per position key the group of dictionary records (relative to the tile), the patches,
;            the slice tables (as slices_build)
;   rl_regen tile_regen for every marked tile (as tile_redraw in play), after rl_dec built the slice tables
; The level's blob is fetched from the floppy (rl_fetch: the game's save overlay, POP800.RLS) at the first room draw
; of a level (rl_lv); a level whose fetch failed (rl_try) is drawn by room_ops. The includer defines RL_LEVEL (the
; level number's byte), rl_fetch (Z = the blob is in the RAM disk), RL_BP_PAGE / RL_BP_ADDR (the 16 blueprints, 2305
; bytes each) and, in the game, GAME_BTNC.
RL_PAGE         equ     6               ; page 6 0x16C0-0x287F: runtime data (PRES's scratch: refetched after a swap)
RL_BASE         equ     0x16c0
RL_SIZE         equ     0x11c0
RL_HDRN         equ     54              ; tools/roomlists.py HDR
RL_DICT         equ     COMPOSE_A       ; the level's dictionary while a room is read back (COMPOSE_A/B: 4 KB)
RL_REGEN        equ     0x0e00          ; 40: tiles to regenerate (low RAM 0x0E00-0x0FFF: runtime scratch)
RL_OVB          equ     0x0e28          ; 40: per tag the new flame id (0: none), back list
RL_OVF          equ     0x0e50          ; 40: per tag the new bubble id, fore list
RL_HDR          equ     0x0e78          ; 54: the blob's header
RL_ROOMS        equ     0x0eae          ; 8: the rooms of the slots (rl_runs' selectors 0..7)
RL_V            equ     0x0eb6          ; variables (to 0x0EE0)
rl_room         equ     RL_V + 0
rl_key          equ     RL_V + 1
rl_tag          equ     RL_V + 2
rl_xa           equ     RL_V + 3
rl_ya           equ     RL_V + 4        ; 16-bit
rl_dp           equ     RL_V + 6        ; 16-bit: the next record
rl_tp           equ     RL_V + 8        ; 16-bit: the next tag
rl_cp           equ     RL_V + 10       ; 16-bit: the list's count
rl_ovp          equ     RL_V + 12       ; 16-bit: the list's patch table
rl_lo           equ     RL_V + 14       ; the patched records' ids: lo..hi (chtab CH_OBJ)
rl_hi           equ     RL_V + 15
rl_gtab         equ     RL_V + 16       ; 16-bit: the group table
rl_soff         equ     RL_V + 18       ; 16-bit: the room's stream
rl_lvb          equ     RL_V + 20       ; 16-bit: the blueprint's address - LEVEL
rl_cur          equ     RL_V + 24       ; 2: the tile as drawn now (modifier, type)
rl_s            equ     RL_V + 26       ; the slot: selector, row, col, room
rl_r            equ     RL_V + 27
rl_c            equ     RL_V + 28
rl_sr           equ     RL_V + 29
rl_d            equ     RL_V + 30       ; 3: the tiles that read it
rl_f            equ     RL_V + 33       ; its patch rules
rl_tb           equ     RL_V + 34       ; 16-bit: the slot room's fg bytes in LEVEL
rl_ip           equ     RL_V + 36       ; 16-bit: rl_grp's record indices
rl_n            equ     RL_V + 38       ; their count
rl_y0           equ     RL_V + 39       ; the slice's extent (SL_Y0, SL_Y1) while its records are placed
rl_y1           equ     RL_V + 40
rl_slo          equ     RL_V + 41       ; the list's slices: list * 40
rl_one          equ     RL_V + 42       ; a mid record's index
RL_BPB          equ     0x0ee8          ; 60: the slot room's 30 fg and 30 bg bytes in the blueprint (to 0x0F23)

rl_lv:          db      0               ; the level whose blob is in the RAM disk (0: none)
rl_try:         db      0               ; the level whose fetch failed

; rl_load: A = room. NC: the room's lists, tags and counts are in place (the patches applied; R_ROOM = A, its links
; loaded, RL_REGEN set for rl_regen); C: no blob for this level or room (nothing changed but R_ROOM: room_ops).
rl_load:        ld      (rl_room), a
                ld      a, (RL_LEVEL)
                ld      hl, rl_lv
                cp      (hl)
                jr      z, rlo_have
                ld      hl, rl_try
                cp      (hl)
                scf
                ret     z
                ld      (hl), a
                call    rl_fetch
                scf
                ret     nz
                ld      a, (RL_LEVEL)
                ld      (rl_lv), a
rlo_have:       ld      a, RL_PAGE
                ld      de, RL_BASE
                call    far_seek
                ld      hl, RL_HDR
                ld      bc, RL_HDRN * 256 + RD_DATA
                inir
                ld      a, (RL_HDR)
                cp      'R'
                scf
                ret     nz
                ld      a, (RL_LEVEL)
                ld      hl, RL_HDR + 1
                cp      (hl)
                scf
                ret     nz
                ld      a, (rl_room)
                dec     a
                cp      24
                ccf
                ret     c
                add     a, a
                ld      e, a
                ld      d, 0
                ld      hl, RL_HDR + 6
                add     hl, de
                ld      e, (hl)
                inc     hl
                ld      d, (hl)
                ld      a, d
                or      e
                scf
                ret     z
                ld      (rl_soff), de
                ld      a, (RL_HDR + 2)         ; the group table after the records
                ld      l, a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      de, RL_DICT
                add     hl, de
                ld      (rl_gtab), hl
                ld      bc, (RL_HDR + 4)        ; the dictionary
                ld      a, RL_PAGE
                ld      de, RL_BASE + RL_HDRN
                ld      hl, RL_DICT
                call    far_copy
                ld      hl, ops_gen             ; (records move, as room_ops)
                inc     (hl)
                call    rl_cmp
                call    rl_dec
                or      a
                ret

                if defined RL_LOWCODE           ; (the game: rl_cmp in low RAM, src/m4/rllow.asm)
rl_cmp          equ     RL_LOWCODE
                else
                include "../m3/rlcmp.asm"
                endif
                include "../m3/rlruns.inc"      ; (rl_cmp's table: resident, low RAM is full)

; rl_dec: the room's stream into the lists (back, fore: a group per position key; mid: key, record pairs), their
; tags and counts, and the slice tables as slices_build leaves them (SL_START, SL_CNT, SL_Y0 / SL_Y1 clamped 0..200)
rl_dec:         ld      hl, (rl_soff)
                ld      de, RL_BASE
                add     hl, de
                ex      de, hl
                ld      a, RL_PAGE
                call    far_seek
                xor     a
                ld      (OPCOUNT), a
                ld      (OPCOUNT + 1), a
                ld      (OPCOUNT + 2), a
                ld      (PTR_TABLE), a
                ld      hl, SL_CNT              ; (slices_build with sb_full: no slice, no extent; SL_START stays)
                ld      de, SL_CNT + 1
                ld      bc, 119
                ld      (hl), a
                ldir
                ld      hl, SL_Y1
                ld      de, SL_Y1 + 1
                ld      bc, 119
                ld      (hl), a
                ldir
                ld      hl, SL_Y0
                ld      de, SL_Y0 + 1
                ld      bc, 119
                ld      (hl), 0xff
                ldir
                ld      hl, OPL_BACK
                ld      de, OPT_BACK
                ld      bc, OPCOUNT
                ld      ix, RL_OVB
                ld      a, 1                    ; flames: CH_OBJ ids 1..9 (torch_redraw)
                ld      (rl_lo), a
                ld      a, 9
                ld      (rl_hi), a
                xor     a                       ; (the slices of list 0)
                call    rl_list
                ld      hl, OPL_FORE
                ld      de, OPT_FORE
                ld      bc, OPCOUNT + 2
                ld      ix, RL_OVF
                ld      a, (bubble_var + 1)     ; bubbles (bubble_redraw)
                ld      (rl_lo), a
                ld      a, (bubble_var + 7)
                ld      (rl_hi), a
                ld      a, 80
                call    rl_list
                ld      hl, OPL_MID
                ld      de, OPT_MID
                ld      bc, OPCOUNT + 1
                ld      a, 40
                call    rl_set
                ld      a, 0xff                 ; (no patches)
                ld      (rl_lo), a
                xor     a
                ld      (rl_hi), a
                in      a, (RD_DATA)
                or      a
                ret     z
                ld      b, a
rd_mid:         push    bc
                in      a, (RD_DATA)
                call    rl_kset
                in      a, (RD_DATA)
                ld      hl, rl_one
                ld      (hl), a
                ld      b, 1
                call    rl_grp
                pop     bc
                djnz    rd_mid
                ret
; rl_set: HL = records, DE = tags, BC = count, IX = patches, A = the list's slices (40 list)
rl_set:         ld      (rl_dp), hl
                ld      (rl_tp), de
                ld      (rl_cp), bc
                ld      (rl_ovp), ix
                ld      (rl_slo), a
                ret
; rl_list: rl_set's arguments: 40 groups, one per position key
rl_list:        call    rl_set
                xor     a
                ld      (rl_key), a
rll_k:          in      a, (RD_DATA)            ; the group
                or      a
                jr      z, rll_n
                ld      l, a
                ld      h, 0
                add     hl, hl
                ld      de, (rl_gtab)
                add     hl, de
                ld      e, (hl)
                inc     hl
                ld      d, (hl)
                ld      hl, RL_DICT
                add     hl, de
                ld      b, (hl)
                inc     hl
                push    hl
                push    bc
                ld      a, (rl_key)
                call    rl_kset
                pop     bc
                pop     hl
                call    rl_grp
rll_n:          ld      hl, rl_key
                inc     (hl)
                ld      a, (hl)
                cp      40
                jr      nz, rll_k
                ret
; rl_kset: A = position key -> rl_key, rl_tag (tag_of_key), rr_xa's 4 col, rr_yl / rr_yh's 63 row (the row above -63)
rl_kset:        ld      (rl_key), a
                ld      hl, tag_of_key
                call    tab_get
                ld      (rl_tag), a
                ld      a, (rl_key)
                ld      hl, rl_yt
rks_1:          cp      10
                jr      c, rks_2
                sub     10
                inc     hl
                inc     hl
                jr      rks_1
rks_2:          add     a, a
                add     a, a
                ld      (rr_xa + 1), a
                ld      a, (hl)
                ld      (rr_yl + 1), a
                inc     hl
                ld      a, (hl)
                ld      (rr_yh + 1), a
                ret
rl_yt:          dw      126, 63, 0, -63
; rl_grp: HL = B dictionary record indices (B >= 1) for the tile rl_tag: placed, patched, appended; its slice
rl_grp:         ld      (rl_ip), hl
                ld      a, b
                ld      (rl_n), a
                ld      a, (rl_slo)
                ld      hl, rl_tag
                add     a, (hl)
                ld      e, a
                ld      d, 0                    ; DE = the slice (list * 40 + tag)
                ld      hl, (rl_cp)
                ld      a, (hl)                 ; the list's count before
                ld      c, a
                add     a, b
                ld      (hl), a
                ld      hl, SL_CNT
                add     hl, de
                ld      a, (hl)
                or      a
                jr      nz, rlg_1
                push    hl
                ld      hl, SL_START
                add     hl, de
                ld      (hl), c
                pop     hl
rlg_1:          add     a, b
                ld      (hl), a
                ld      hl, SL_Y0
                add     hl, de
                ld      a, (hl)
                ld      (rl_y0), a
                ld      hl, SL_Y1
                add     hl, de
                ld      a, (hl)
                ld      (rl_y1), a
                push    de                      ; the slice
                ld      de, (rl_dp)             ; DE = the next record
                exx                             ; HL' = the indices, B' = count, C' = tag, DE' = the next tag
                ld      hl, (rl_ip)
                ld      a, (rl_n)
                ld      b, a
                ld      a, (rl_tag)
                ld      c, a
                ld      de, (rl_tp)
rr_l:           ld      a, c                    ; the tag
                ld      (de), a
                inc     de
                ld      a, (hl)                 ; the record's index
                inc     hl
                exx
                ld      l, a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      bc, RL_DICT
                add     hl, bc
                ldi                             ; flags
                ld      a, (hl)
                ldi                             ; chtab
                cp      CH_OBJ
                ld      a, (hl)                 ; id
                call    z, rl_patch
                ld      (de), a
                inc     hl
                inc     de
rr_xa:          ld      a, 0                    ; (rl_kset: 4 col) + the relative xbyte
                add     a, (hl)
                ld      (de), a
                inc     hl
                inc     de
rr_yl:          ld      a, 0                    ; (rl_kset: 63 row) + the relative ytop
                add     a, (hl)
                ld      (de), a
                ld      c, a
                inc     hl
                inc     de
rr_yh:          ld      a, 0
                adc     a, (hl)
                ld      (de), a
                ld      b, a                    ; BC = ytop
                inc     hl
                inc     de
                ld      a, (hl)                 ; w
                ld      (de), a
                inc     hl
                inc     de
                ld      a, (hl)                 ; h
                ld      (de), a
                inc     de
                add     a, c                    ; the slice's extent (slices_build's sb_yr: yr_merge, yr_clamp)
                ld      l, a                    ; ytop + h, clamped 0..200: the slice's bottom (max)
                ld      a, b
                adc     a, 0
                jr      nz, rlr_y1c
                ld      a, l
                cp      201
                jr      c, rlr_y1v
                ld      a, 200
                jr      rlr_y1v
rlr_y1c:         rla                             ; (negative: 0, else 200)
                ld      a, 0
                jr      c, rlr_y1v
                ld      a, 200
rlr_y1v:         ld      hl, rl_y1
                cp      (hl)
                jr      c, rlr_y0
                ld      (hl), a
rlr_y0:          ld      a, b                    ; ytop, clamped: the slice's top (min)
                or      a
                jr      nz, rlr_y0c
                ld      a, c
                cp      201
                jr      c, rlr_y0v
                ld      a, 200
                jr      rlr_y0v
rlr_y0c:         rla
                ld      a, 0
                jr      c, rlr_y0v
                ld      a, 200
rlr_y0v:         ld      hl, rl_y0
                cp      (hl)
                jr      nc, rr_e2
                ld      (hl), a
rr_e2:
                exx
                djnz    rr_l
                ld      (rl_tp), de
                exx
                ld      (rl_dp), de
                pop     de                      ; the slice
                ld      hl, SL_Y0
                add     hl, de
                ld      a, (rl_y0)
                ld      (hl), a
                ld      hl, SL_Y1
                add     hl, de
                ld      a, (rl_y1)
                ld      (hl), a
                ret
; rl_patch: A = the id of a CH_OBJ record: the patched id when it is in rl_lo..rl_hi and the tile has one (op_patch's
; first matching record: a tile draws one flame, one bubble). Keeps HL, DE.
rl_patch:       ld      c, a
                ld      a, (rl_lo)
                dec     a
                cp      c
                jr      nc, rp_0
                ld      a, (rl_hi)
                cp      c
                jr      c, rp_0
                push    hl
                push    de
                ld      hl, (rl_ovp)
                ld      a, (rl_tag)
                ld      e, a
                ld      d, 0
                add     hl, de
                ld      a, (hl)
                pop     de
                pop     hl
                or      a
                ret     nz
rp_0:           ld      a, c
                ret

; rl_regen: after rl_dec (the slices built), every marked tile regenerated (tile_redraw's tile_regen, without the drawing)
rl_regen:
                if defined GAME_BTNC
                xor     a                       ; (the button cache belongs to the room before: rf_game clears it)
                ld      (bc_v), a
                endif
                ld      c, 0
rg_l:           ld      hl, RL_REGEN
                ld      b, 0
                add     hl, bc
                ld      a, (hl)
                or      a
                jr      z, rg_n
                push    bc
                call    load_room_links
                call    load_leftroom
                pop     bc
                push    bc
                ld      a, c
                call    tile_regen
                pop     bc
rg_n:           inc     c
                ld      a, c
                cp      40
                jr      nz, rg_l
                call    load_room_links
                jp      load_leftroom
