; ---------------------------------------------------------------- room renderer (M3)
; Port of SDLPoP seg008 draw_room() as reproduced by tools/popdata.py. Builds a list of
; drawing operations for a room, then executes it cell by cell through the compose buffer
; (fill black, lay pieces, shadow write, blit). EGA rules (palace walls like dungeon walls).
; The whole-room parts (room_ops, slices_build, the per-cell buckets, run_ops, draw_room_full) are in roomfull.asm,
; the level-load alter-mods pass in altmods.asm (the M4 game runs both from code overlays, src/m4/ovl.asm).

; memory
DIR_ENV         equ     0xe000          ; directories: 8 bytes per image id (env 224 ids, wall 96, objects 64)
DIR_WALL        equ     0xe700
DIR_OBJ         equ     0xea00
LEVEL           equ     0xec00          ; 2305-byte blueprint (fg 720, bg 720, links...)
LV_FG           equ     LEVEL
LV_BG           equ     LEVEL + 720
LV_LINKS        equ     LEVEL + 1952    ; 24 x (left, right, up, down)
LV_USED         equ     LEVEL + 2048
LV_START_ROOM   equ     LEVEL + 2112
; op lists, one per table; record = flags (tbl | blit<<2 | mono<<4), chtab, id, xbyte (signed), ytop lo, ytop hi, w (bytes), h
OPL_BACK        equ     0x9000          ; 192 records (0x8000-0x9FFF: RAM behind the VRAM window)
OPL_MID         equ     0x9600          ; 8
OPL_FORE        equ     0x9640          ; 128  (ends 0x9a40)
OPMAX_BACK      equ     192
OPMAX_MID       equ     8
OPMAX_FORE      equ     128

; room variables
RV              equ     0x0900
R_ROOM          equ     RV + 0
R_L             equ     RV + 1
R_R             equ     RV + 2
R_A             equ     RV + 3
R_B             equ     RV + 4
R_AL            equ     RV + 5
R_AR            equ     RV + 6
R_BL            equ     RV + 7
R_BR            equ     RV + 8
DRAWN_ROW       equ     RV + 9
DRAWN_COL       equ     RV + 10
DRAW_XH         equ     RV + 11
DRAW_MAIN_Y     equ     RV + 12         ; 16-bit signed
DRAW_BOTTOM_Y   equ     RV + 14         ; 16-bit signed
CURR_TILE       equ     RV + 16
CURR_MOD        equ     RV + 17
TILE_LEFT       equ     RV + 18
MOD_LEFT        equ     RV + 19
LEVEL_TYPE      equ     RV + 20         ; 0 dungeon, 1 palace
PTR_TABLE       equ     RV + 21         ; 0 back, 1 mid (ptr_add_table)
PR_TAB          equ     0x0500          ; wall pattern draws mod 140: PR_SEEDS seeds x PR_DRAWS (runtime, built once)
PR_SEEDS        equ     64
PR_DRAWS        equ     10
RR_PTRS         equ     0x0200          ; the scan's records in the rect, in lay order (RC_MAX words, page-aligned)
RC_MAX          equ     64
OPCOUNT         equ     RV + 22         ; 3 bytes: back, mid, fore counts (OPCOUNT+tbl)
V_TBL           equ     RV + 25         ; add_op parameters
V_BLIT          equ     RV + 26
V_MONOC         equ     RV + 27
V_XH            equ     RV + 28
V_XL            equ     RV + 29         ; signed pixel offset
A_TMP           equ     RV + 110        ; scratch (A_TMP2 is also used as a 16-bit cell: RV+111..112)
A_TMP2          equ     RV + 111
AO_CH           equ     RV + 104        ; add_op private scratch: chtab, shift
AO_SHIFT        equ     RV + 105
OPL_PTR         equ     RV + 106        ; 16-bit: current list base (run_rect)
OPL_END         equ     RV + 108        ; 16-bit
CUR_TAG         equ     RV + 113        ; tile tag written into every op record's tag byte: row*10+col, 30+col above row
DR_X0           equ     RV + 114        ; dirty rect (byte columns / rows), x1/y1 exclusive
DR_X1           equ     RV + 115
DR_Y0           equ     RV + 116
DR_Y1           equ     RV + 117
TR_TAG          equ     RV + 118        ; tile_regen state
TR_TBL          equ     RV + 119
TR_I0           equ     RV + 120
TR_NOLD         equ     RV + 121
TR_NNEW         equ     RV + 122        ; 3 bytes
TR_KEY          equ     RV + 125
TR_SAVE         equ     RV + 126        ; 18 bytes: opl_base(6) opl_max(3) OPCOUNT(3) opt_base(6)
R_SAVED         equ     RV + 144        ; room saved across the above-row pass
RR_C0           equ     RV + 145        ; run_rect: only ops of tiles in columns RR_C0..RR_C1 are examined
RR_C1           equ     RV + 146
RR_TAGP         equ     RV + 147        ; 16-bit: tag pointer parallel to OPL_PTR
RR_CB           equ     RV + 149        ; rr_table: columns left in the row (the cell being examined)
RR_N            equ     RV + 150        ; ops left in the slice
RR_CP           equ     RV + 151        ; 16-bit: rr_table's cell pointer in SL_CNT
RR_RP           equ     RV + 153        ; 16-bit: rr_table's row pointer in rr_rows
RR_CB0          equ     RV + 164        ; rr_table: SL_CNT's low byte at the list's column RR_C0 of row 0
RR_NC           equ     RV + 165        ; rr_table: columns a row
OP_TAG          equ     RV + 155        ; op_patch parameters
OP_LIST         equ     RV + 156
OP_CH           equ     RV + 157
OP_LO           equ     RV + 158
OP_HI           equ     RV + 159
OP_NEW          equ     RV + 160
RR_SHONLY       equ     RV + 161        ; 1: run_rect writes the shadow room only (no fore pieces, no blit) and dr_run
RR_HOOK         equ     RV + 162        ; reports its rect through RR_HOOK (16-bit address) - the game composes objects
; slice tables: per list, per tag: first record index and record count (rebuilt by slices_build)
SL_START        equ     0x8100          ; 3 x 40 (page 0x81 is free between the bit-reverse table and the shift tables;
SL_Y0           equ     0x0400          ; 3 x 40: each slice's top row and bottom row + 1 (0..200), rebuilt
SL_Y1           equ     0x0478          ; with the slices (runtime data in low RAM, nothing to load)
SL_CNT          equ     0x8180          ; 3 x 40  0x8F00 was the shift-7 hi table)
; op tags (one byte per record, parallel to the lists) and the temp lists used while regenerating one tile
OPT_BACK        equ     0x9a40
OPT_MID         equ     0x9b00
OPT_FORE        equ     0x9b08
TMP_BACK        equ     0x9c00          ; 48 records
TMP_MID         equ     0x9d80          ; 8
TMP_FORE        equ     0x9dc0          ; 48
TMP_TAGS        equ     0x9f40          ; 48 bytes, tags written during regeneration (ignored)
TMPMAX_BACK     equ     48
TMPMAX_MID      equ     8
TMPMAX_FORE     equ     48
LEFTROOM        equ     RV + 32         ; 3 x (type, mod)
ROWBELOW        equ     RV + 40         ; 10 x (type, mod)
SEED            equ     RV + 64         ; 32-bit PRNG state
SEEDSAVE        equ     RV + 68
MUL_T           equ     RV + 72         ; 32-bit temp
MUL_A           equ     RV + 76         ; 32-bit temp
WP_MD           equ     RV + 80         ; wall pattern randoms
WP_MDO          equ     RV + 81
WP_BD           equ     RV + 82
WP_BDO          equ     RV + 83
WP_PART         equ     RV + 84
WP_TABLE        equ     RV + 85
GATE_TOP        equ     RV + 86         ; 16-bit
GATE_BOTTOM     equ     RV + 88         ; 16-bit
GATE_YB         equ     RV + 90         ; 16-bit
LD_YB           equ     RV + 92         ; 16-bit
LD_Y            equ     RV + 94         ; 16-bit
CELL            equ     RV + 96
RUN_TBL         equ     RV + 97
RUN_IDX         equ     RV + 98

; chtabs / blits
CH_OBJ          equ     1
CH_ENV          equ     6
CH_SWORD        equ     0
CH_KID          equ     2
CH_GUARD        equ     5
CH_WALL         equ     7
BL_COPY         equ     0
BL_OR           equ     1
BL_BLACK        equ     2
BL_MONO         equ     3
TBL_BACK        equ     0
TBL_MID         equ     1
TBL_FORE        equ     2
; tile types
T_EMPTY         equ     0
T_FLOOR         equ     1
T_SPIKE         equ     2
T_PILLAR        equ     3
T_CLOSER_R      equ     6
T_GATE          equ     4
T_STUCK         equ     5
T_DOORTOP_F     equ     7
T_BIGPILLAR_T   equ     9
T_POTION        equ     10
T_LOOSE         equ     11
T_DOORTOP       equ     12
T_OPENER        equ     15
T_LEVELDOOR_L   equ     16
T_CHOMPER       equ     18
T_TORCH         equ     19
T_WALL          equ     20
T_SWORD         equ     22
T_LATTICE_DOWN  equ     26
T_LATTICE_SMALL equ     27
T_TORCH_DEBRIS  equ     30
; tile_table fields (12 bytes per tile)
TT_BASE_ID      equ     0
TT_FLOOR_LEFT   equ     1
TT_BASE_Y       equ     2
TT_RIGHT_ID     equ     3
TT_FLOOR_RIGHT  equ     4
TT_RIGHT_Y      equ     5
TT_STRIPE_ID    equ     6
TT_TOPRIGHT_ID  equ     7
TT_BOTTOM_ID    equ     8
TT_FORE_ID      equ     9
TT_FORE_X       equ     10
TT_FORE_Y       equ     11

; tab_get: A = (HL + A), page-crossing safe
tab_get:        add     a, l
                ld      l, a
                jp      nc, tg1
                inc     h
tg1:            ld      a, (hl)
                ret
tbl_line:       db      0, 10, 20
; tag_of_key: list order (row 2, row 1, row 0, above row) -> tile tag
tag_of_key:     db      20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19
                db      0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39
col_xh:         db      0, 4, 8, 12, 16, 20, 24, 28, 32, 36
; tile_is_floor: 1,2,3,4,5,6,7,8,10,11,13,14,15,16,17,18,19,20,21,22,23,24,25,30
tile_is_floor:  db      0,1,1,1,1,1,1,1,1,0,1,1,0,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0,0,1
lpos_tab:       db      58, 41, 37, 20, 16
rpos_tab:       db      52, 42, 31, 21

; A = pos -> A = pos mod 10 (pos < 30)
mod10:          cp      10
                ret     c
                sub     10
                jp      mod10

; In: A = room (1..24). Out: HL = &fg[(room-1)*30], DE = &bg[(room-1)*30]
tile_base:      add     a, a            ; (room 1..24: a table instead of room * 30)
                ld      l, a
                ld      h, 0
                ld      de, tb_tbl - 2
                add     hl, de
                ld      e, (hl)
                inc     hl
                ld      d, (hl)
                ld      hl, 720
                add     hl, de
                ex      de, hl          ; DE = bg, HL = fg
                ret
tb_tbl:         dw      LV_FG, LV_FG + 30, LV_FG + 60, LV_FG + 90, LV_FG + 120, LV_FG + 150, LV_FG + 180, LV_FG + 210
                dw      LV_FG + 240, LV_FG + 270, LV_FG + 300, LV_FG + 330, LV_FG + 360, LV_FG + 390, LV_FG + 420
                dw      LV_FG + 450, LV_FG + 480, LV_FG + 510, LV_FG + 540, LV_FG + 570, LV_FG + 600, LV_FG + 630
                dw      LV_FG + 660, LV_FG + 690

; R_L, R_R, R_A, R_B of room (R_ROOM)
room_links_raw: ld      a, (R_ROOM)
                or      a
                jp      nz, rlr1
                xor     a
                ld      (R_L), a
                ld      (R_R), a
                ld      (R_A), a
                ld      (R_B), a
                ret
rlr1:           dec     a
                ld      l, a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                ld      de, LV_LINKS
                add     hl, de
                ld      a, (hl)
                ld      (R_L), a
                inc     hl
                ld      a, (hl)
                ld      (R_R), a
                inc     hl
                ld      a, (hl)
                ld      (R_A), a
                inc     hl
                ld      a, (hl)
                ld      (R_B), a
                ret

; In: A = room (may be 0). Out: C = left, B = right, D = up, E = down
links_of:       or      a
                jp      nz, lo1
                ld      bc, 0
                ld      de, 0
                ret
lo1:            dec     a
                ld      l, a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                push    de
                ld      de, LV_LINKS
                add     hl, de
                pop     de
                ld      c, (hl)
                inc     hl
                ld      b, (hl)
                inc     hl
                ld      d, (hl)
                inc     hl
                ld      e, (hl)
                ret

; load_room_links for R_ROOM
load_room_links: call   room_links_raw
                xor     a
                ld      (R_AL), a
                ld      (R_AR), a
                ld      (R_BL), a
                ld      (R_BR), a
                ld      a, (R_ROOM)
                or      a
                ret     z
                ld      a, (R_A)
                or      a
                jp      z, lrl1
                call    links_of
                ld      a, c
                ld      (R_AL), a
                ld      a, b
                ld      (R_AR), a
                jp      lrl2
lrl1:           ld      a, (R_L)
                or      a
                jp      z, lrl1b
                call    links_of
                ld      a, d
                ld      (R_AL), a
lrl1b:          ld      a, (R_R)
                or      a
                jp      z, lrl2
                call    links_of
                ld      a, d
                ld      (R_AR), a
lrl2:           ld      a, (R_B)
                or      a
                jp      z, lrl3
                call    links_of
                ld      a, c
                ld      (R_BL), a
                ld      a, b
                ld      (R_BR), a
                ret
lrl3:           ld      a, (R_L)
                or      a
                jp      z, lrl3b
                call    links_of
                ld      a, e
                ld      (R_BL), a
lrl3b:          ld      a, (R_R)
                or      a
                ret     z
                call    links_of
                ld      a, e
                ld      (R_BR), a
                ret

; get_tile_to_draw. In: A = room, C = col (signed, -1 allowed), B = row, E = default type.
; Out: D = type, E = modifier
get_tile:       bit     7, c
                jp      z, gt1
                ld      hl, LEFTROOM    ; col == -1
                ld      a, b
                add     a, a
                call    tab_get
                ld      d, a
                inc     hl
                ld      e, (hl)
                ret
gt1:            or      a
                jp      nz, gt2
                ld      d, e            ; room 0: default, modifier 0
                ld      e, 0
                ret
gt2:            push    bc
                call    tile_base       ; HL = fg, DE = bg
                ld      a, b
                add     a, a
                ld      b, a
                add     a, a
                add     a, a
                add     a, b            ; row*10
                add     a, c
                ld      c, a
                ld      b, 0
                add     hl, bc
                ex      de, hl
                add     hl, bc
                ld      a, (de)
                and     0x1f
                ld      d, a
                ld      e, (hl)
                pop     bc
                ; a button whose door-link timer runs is drawn pressed (SDLPoP get_tile_to_draw)
                cp      T_CLOSER_R
                jp      z, gt_btn
                cp      T_OPENER
                ret     nz
gt_btn:         push    hl
                ld      hl, LEVEL + 1696        ; door-link timers
                ld      a, e
                call    tab_get
                pop     hl
                and     0x1f
                cp      2
                ret     c
                ld      a, d
                cp      T_OPENER
                jp      z, gt_open
                ld      d, T_STUCK              ; closer: drawn as the stuck (pressed) plate
                ret
gt_open:        ld      d, T_FLOOR              ; opener: drawn as floor
                ld      e, 0
                ret

load_leftroom:  ld      b, 0
ll1:            push    bc
                ld      a, (R_L)
                ld      c, 9
                ld      e, T_WALL
                call    get_tile
                pop     bc
                ld      hl, LEFTROOM
                ld      a, b
                add     a, a
                add     a, l
                ld      l, a
                ld      (hl), d
                inc     hl
                ld      (hl), e
                inc     b
                ld      a, b
                cp      3
                jp      nz, ll1
                ret

load_rowbelow:  ld      a, (DRAWN_ROW)
                cp      2
                jp      nz, lrb1
                ld      a, (R_B)
                ld      (A_TMP), a      ; room
                ld      a, (R_BL)
                ld      (A_TMP2), a     ; room_left
                ld      b, 0            ; row below
                jp      lrb2
lrb1:           ld      a, (R_ROOM)
                ld      (A_TMP), a
                ld      a, (R_L)
                ld      (A_TMP2), a
                ld      a, (DRAWN_ROW)
                inc     a
                ld      b, a
lrb2:           ld      c, 1            ; column 1..9 -> tile at col-1
lrb3:           push    bc
                ld      a, (A_TMP)
                dec     c
                ld      e, T_EMPTY
                call    get_tile
                pop     bc
                push    bc
                ld      hl, ROWBELOW
                ld      a, c
                add     a, a
                add     a, l
                ld      l, a
                ld      (hl), d
                inc     hl
                ld      (hl), e
                pop     bc
                inc     c
                ld      a, c
                cp      10
                jp      nz, lrb3
                ld      a, (A_TMP2)
                ld      c, 9
                ld      e, T_WALL
                call    get_tile
                ld      hl, ROWBELOW
                ld      (hl), d
                inc     hl
                ld      (hl), e
                ret

load_curr_left: ld      a, (DRAWN_ROW)
                ld      e, T_WALL
                cp      2
                jp      nz, lcl1
                ld      e, T_FLOOR      ; top of level: floor
lcl1:           ld      b, a
                push    de
                ld      a, (R_ROOM)
                ld      hl, DRAWN_COL
                ld      c, (hl)
                call    get_tile
                ld      a, d
                ld      (CURR_TILE), a
                ld      a, e
                ld      (CURR_MOD), a
                pop     de
                ld      a, (DRAWN_ROW)
                ld      b, a
                ld      a, (DRAWN_COL)
                dec     a
                ld      c, a
                ld      a, (R_ROOM)
                call    get_tile
                ld      a, d
                ld      (TILE_LEFT), a
                ld      a, e
                ld      (MOD_LEFT), a
                ld      a, (DRAWN_COL)
                ld      hl, col_xh
                call    tab_get
                ld      (DRAW_XH), a
                ret

; In: A = tile type. Out: IX = tile_table entry
tt_entry:       ld      l, a
                ld      h, 0
                ld      d, h
                ld      e, l
                add     hl, hl
                add     hl, de          ; *3
                add     hl, hl
                add     hl, hl          ; *12
                ld      de, tile_table
                add     hl, de
                push    hl
                pop     ix
                ret

; ---------------------------------------------------------------- op list
; add_op: A = chtab, C = image id, HL = ybottom (signed 16-bit); V_TBL, V_BLIT, V_MONOC, V_XH, V_XL set.
; Out: A = 1 added / 0 skipped (Z flag set when skipped). Preserves nothing else.
add_op:         ld      b, a
                ld      a, c
                or      a
                ret     z               ; id 0: nothing
                push    hl
                ld      a, b
                ld      (AO_CH), a      ; chtab
                ; x = xh*8 + xl (signed) -> byte = x >> 3, shift = x & 7
                ld      a, (V_XH)
                ld      l, a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      a, (V_XL)
                ld      e, a
                rla
                sbc     a, a
                ld      d, a
                add     hl, de          ; HL = x
                ld      a, l
                and     7
                ld      (AO_SHIFT), a     ; shift
                sra     h
                rr      l
                sra     h
                rr      l
                sra     h
                rr      l
                ld      a, l
                ld      (V_XH), a       ; byte column (signed) reused for the record
                ld      a, (AO_SHIFT)
                or      a
                jp      z, ao_noshift
                call    shift_variant   ; C = variant id (or 0 if none)
                ld      a, c
                or      a
                jp      z, ao_skip
ao_noshift:     ld      a, c
                ld      (ao_id), a      ; final image id
                ld      a, (AO_CH)
                call    dir_entry       ; HL = the entry (a copy)
                ld      a, (hl)
                inc     hl
                or      (hl)
                inc     hl
                or      (hl)
                inc     hl
                or      (hl)            ; off|wb
                inc     hl
                or      (hl)            ; h
                jp      z, ao_skip      ; empty entry: no image
                ld      a, (hl)         ; h
                ld      (ao_h), a
                dec     hl
                ld      a, (hl)         ; w
                ld      (ao_w), a
                pop     hl              ; ybottom
                ld      a, (ao_h)
                ld      e, a
                ld      d, 0
                or      a
                sbc     hl, de
                inc     hl              ; ytop = ybottom - h + 1
                push    hl
                ld      a, (V_TBL)      ; list of this table: count, max, base
                ld      hl, OPCOUNT
                add     a, l
                ld      l, a
                ld      a, (hl)
                ld      (ao_cnt), hl
                ld      (ao_n), a
                ld      c, a
                ld      a, (V_TBL)
                ld      hl, opl_max
                add     a, l
                ld      l, a
                ld      a, (hl)
                cp      c
                jp      z, ao_full
                ld      a, (V_TBL)
                add     a, a
                ld      hl, opl_base
                add     a, l
                ld      l, a
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a            ; HL = list base
                ld      e, c
                ld      d, 0
                ex      de, hl
                add     hl, hl
                add     hl, hl
                add     hl, hl
                add     hl, de          ; HL = record
                ld      (ao_rec), hl
                pop     de              ; DE = ytop
                ld      a, (V_TBL)
                ld      b, a
                ld      a, (V_BLIT)
                add     a, a
                add     a, a
                or      b
                ld      b, a
                push    bc
                ld      a, (V_MONOC)    ; mono colour: EGA number -> MZ colour of the art set
                and     15
                ld      c, a
                ld      hl, mono_map_dungeon
                ld      a, (LEVEL_TYPE)
                or      a
                jp      z, ao_mm
                ld      a, (AO_CH)
                cp      CH_OBJ
                jp      z, ao_mm
                ld      hl, mono_map_palace
ao_mm:          ld      a, c
                call    tab_get
                pop     bc
                rrca
                rrca
                rrca
                rrca
                and     0xf0
                or      b
                ld      hl, (ao_rec)
                ld      (hl), a
                inc     hl
                ld      a, (AO_CH)
                ld      (hl), a
                inc     hl
                ld      a, (ao_id)
                ld      (hl), a
                inc     hl
                ld      a, (V_XH)
                ld      (hl), a
                inc     hl
                ld      (hl), e
                inc     hl
                ld      (hl), d
                inc     hl
                ld      a, (ao_w)
                ld      (hl), a
                inc     hl
                ld      a, (ao_h)
                ld      (hl), a
                ld      a, (V_TBL)      ; tag byte
                add     a, a
                ld      hl, opt_base
                add     a, l
                ld      l, a
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a
                ld      a, (ao_n)
                ld      e, a
                ld      d, 0
                add     hl, de
                ld      a, (CUR_TAG)
                ld      (hl), a
                ld      hl, (ao_cnt)
                inc     (hl)
                ld      a, 1
                or      a
                ret
ao_full:        pop     hl
                xor     a
                ret
ao_skip:        pop     hl
                xor     a
                ret
ao_id:          db      0
ao_w:           db      0
ao_h:           db      0
ao_cnt:         dw      0
ao_n:           db      0
ao_rec:         dw      0
                if ($ & 0xff) > 0xdf            ; the 33 bytes below are indexed without a page carry: one page
                ds      0x100 - ($ & 0xff)
                endif
opl_max:        db      OPMAX_BACK, OPMAX_MID, OPMAX_FORE
opl_base:       dw      OPL_BACK, OPL_MID, OPL_FORE
opt_base:       dw      OPT_BACK, OPT_MID, OPT_FORE
tmp_cfg:        dw      TMP_BACK, TMP_MID, TMP_FORE
                db      TMPMAX_BACK, TMPMAX_MID, TMPMAX_FORE
                db      0, 0, 0
                dw      TMP_TAGS, TMP_TAGS, TMP_TAGS

; dir_entry: A = chtab, C = image id -> HL = a copy of its 8-byte directory entry (dir_buf; valid until the
; next call). Keeps BC, DE. dir_tab says where each chtab's directory is: RAM-disk page + address, or page
; 0xFF = main RAM (the test programs). The game keeps them all in the RAM disk (~300 T a lookup).
dir_entry:      push    bc
                push    de
                ld      l, c
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ex      de, hl          ; DE = id * 8
                ld      l, a
                ld      h, 0
                ld      c, l
                ld      b, h
                add     hl, hl
                add     hl, bc          ; chtab * 3
                ld      bc, dir_tab
                add     hl, bc
                ld      a, (hl)         ; page
                inc     hl
                ld      c, (hl)
                inc     hl
                ld      b, (hl)         ; base
                ex      de, hl
                add     hl, bc          ; address of the entry
                cp      0xff
                jp      z, de_ram
                ex      de, hl
                call    far_seek
                ld      hl, dir_buf
                ld      bc, 0x0800 | RD_DATA
                inir
                jp      de_done
de_ram:         ld      de, dir_buf
                ld      bc, 8
                ldir
de_done:        ld      hl, dir_buf
                pop     de
                pop     bc
                ret
dir_buf:        ds      8
; per chtab (0 sword, 1 objects, 2 kid, 3-5 -, 6 environment, 7 wall): page, address
dir_tab:        db      0xff
                dw      0
                db      0xff
                dw      DIR_OBJ
                db      0xff
                dw      0
                ds      9
                db      0xff
                dw      DIR_ENV
                db      0xff
                dw      DIR_WALL

; shift_variant: (AO_CH = chtab, C = id, AO_SHIFT = shift) -> C = variant id or 0
shift_variant:  ld      hl, shift_tab
sv1:            ld      a, (hl)
                cp      0xff
                jp      z, sv_none
                ld      a, (AO_CH)
                cp      (hl)
                jp      nz, sv_next
                inc     hl
                ld      a, (hl)
                cp      c
                dec     hl
                jp      nz, sv_next
                inc     hl
                inc     hl
                ld      a, (AO_SHIFT)
                cp      (hl)
                dec     hl
                dec     hl
                jp      nz, sv_next
                inc     hl
                inc     hl
                inc     hl
                ld      c, (hl)
                ret
sv_next:        inc     hl
                inc     hl
                inc     hl
                inc     hl
                jp      sv1
sv_none:        ld      c, 0
                ret

; convenience wrappers: set table/blit/mono then add. In: A = chtab, C = id, HL = ybottom, B = xl
; (V_XH must be set by the caller; xl in B)
add_back:       push    af
                ld      a, TBL_BACK
                jp      addc
add_fore:       push    af
                ld      a, TBL_FORE
                jp      addc
add_mid:        push    af
                ld      a, TBL_MID
                jp      addc
add_ptr:        push    af
                ld      a, (PTR_TABLE)
addc:           ld      (V_TBL), a
                ld      a, b
                ld      (V_XL), a
                pop     af
                jp      add_op

; set blit: A = code (0 copy, 1 or/transp, 2 black, 3 mono), C = mono colour
set_blit:       ld      (V_BLIT), a
                ld      a, c
                ld      (V_MONOC), a
                ret
; helpers for the common blits (preserve BC/DE/HL)
blit_copy:      xor     a
                jp      set_blit0
blit_or:        ld      a, BL_OR
                jp      set_blit0
blit_black:     ld      a, BL_BLACK
set_blit0:      ld      (V_BLIT), a
                xor     a
                ld      (V_MONOC), a
                ret
; xh helpers: V_XH = DRAW_XH + A
xh_plus:        ld      hl, DRAW_XH
                add     a, (hl)
                ld      (V_XH), a
                ret
; HL = DRAW_MAIN_Y + A (signed 8-bit)
main_plus:      ld      hl, (DRAW_MAIN_Y)
                ld      e, a
                rla
                sbc     a, a
                ld      d, a
                add     hl, de
                ret
bottom_plus:    ld      hl, (DRAW_BOTTOM_Y)
                ld      e, a
                rla
                sbc     a, a
                ld      d, a
                add     hl, de
                ret

; ---------------------------------------------------------------- draw_tile parts
can_see_bl:     ld      a, (CURR_TILE)  ; Z set when the bottom-left can be seen
                cp      T_EMPTY
                ret     z
                cp      T_BIGPILLAR_T
                ret     z
                cp      T_DOORTOP
                ret     z
                cp      T_LATTICE_DOWN
                ret

draw_tile_floorright:
                call    can_see_bl
                ret     nz
                call    draw_tile_topright
                ld      a, (TILE_LEFT)
                call    tt_entry
                ld      a, (ix+TT_FLOOR_RIGHT)
                or      a
                ret     z
                xor     a
                call    xh_plus
                ld      a, T_FLOOR
                call    tt_entry
                ld      a, (ix+TT_RIGHT_Y)
                call    main_plus
                call    blit_black
                ld      a, CH_ENV
                ld      c, 42
                ld      b, 0
                jp      add_back

draw_tile_topright:
                ld      a, (DRAWN_COL)
                add     a, a
                ld      hl, ROWBELOW
                add     a, l
                ld      l, a
                ld      d, (hl)         ; type
                inc     hl
                ld      e, (hl)         ; mod
                xor     a
                call    xh_plus
                ld      a, d
                cp      T_DOORTOP_F
                jp      z, dtr_door
                cp      T_DOORTOP
                jp      z, dtr_door
                cp      T_WALL
                jp      nz, dtr_other
                ld      hl, (DRAW_BOTTOM_Y)
                call    blit_or
                ld      a, CH_WALL
                ld      c, 2
                ld      b, 0
                jp      add_back
dtr_door:       ld      a, (LEVEL_TYPE)
                or      a
                ret     z
                ld      hl, doortop_fram_top
                ld      a, e
                call    tab_get
                ld      c, a
                ld      hl, (DRAW_BOTTOM_Y)
                call    blit_or
                ld      a, CH_ENV
                ld      b, 0
                jp      add_back
dtr_other:      call    tt_entry
                ld      c, (ix+TT_TOPRIGHT_ID)
                ld      hl, (DRAW_BOTTOM_Y)
                call    blit_or
                ld      a, CH_ENV
                ld      b, 0
                jp      add_back

draw_tile_anim_topright:
                call    can_see_bl
                ret     nz
                ld      a, (CURR_TILE)
                cp      T_LATTICE_DOWN
                ret     z               ; (empty, bigpillar top, doortop only)
                ld      a, (DRAWN_COL)
                add     a, a
                ld      hl, ROWBELOW
                call    tab_get
                cp      T_GATE
                ret     nz
                inc     hl
                ld      a, (hl)
                cp      189
                jp      c, dtat1
                ld      a, 188
dtat1:          ld      (A_TMP), a
                xor     a
                call    xh_plus
                ld      a, BL_MONO
                ld      c, 0
                call    set_blit
                ld      hl, (DRAW_BOTTOM_Y)
                ld      a, CH_ENV
                ld      c, 68
                ld      b, 0
                call    add_back
                ld      a, (A_TMP)
                rrca
                rrca
                and     7
                ld      hl, door_fram_top
                call    tab_get
                ld      c, a
                ld      hl, (DRAW_BOTTOM_Y)
                call    blit_or
                ld      a, CH_ENV
                ld      b, 0
                jp      add_back

draw_tile_right:
                ld      a, (CURR_TILE)
                cp      T_WALL
                ret     z
                xor     a
                call    xh_plus
                ld      a, (TILE_LEFT)
                ld      hl, MOD_LEFT
                ld      e, (hl)         ; E = modifier_left
                cp      T_EMPTY
                jp      z, dtr_empty
                cp      T_FLOOR
                jp      z, dtr_floor
                cp      T_DOORTOP_F
                jp      z, dtr_dtop
                cp      T_DOORTOP
                jp      z, dtr_dtop
                cp      T_WALL
                jp      z, dtr_wall
                ; default
                call    tt_entry
                ld      a, (ix+TT_RIGHT_ID)
                or      a
                jp      z, dtr_def2
                ld      c, a
                call    blit_or
                ld      a, (TILE_LEFT)
                cp      T_STUCK
                jp      nz, dtr_def1
                ld      a, BL_OR
                ld      (V_BLIT), a     ; transp (same code)
                ld      a, (CURR_TILE)
                cp      T_EMPTY
                jp      z, dtr_42
                cp      T_STUCK
                jp      z, dtr_42
                ld      hl, tile_is_floor
                call    tab_get
                or      a
                jp      nz, dtr_def1
dtr_42:         ld      c, 42
dtr_def1:       push    bc
                ld      a, (ix+TT_RIGHT_Y)
                call    main_plus
                pop     bc
                ld      a, CH_ENV
                ld      b, 0
                call    add_back
                ld      a, (TILE_LEFT)
                call    tt_entry
dtr_def2:       ld      a, (LEVEL_TYPE)
                or      a
                jp      z, dtr_def3
                ld      c, (ix+TT_STRIPE_ID)
                ld      a, -27
                call    main_plus
                call    blit_or
                ld      a, CH_ENV
                ld      b, 0
                call    add_back
dtr_def3:       ld      a, (TILE_LEFT)
                cp      T_TORCH
                jp      z, dtr_torch
                cp      T_TORCH_DEBRIS
                ret     nz
dtr_torch:      ld      a, -28
                call    bottom_plus
                call    blit_copy
                ld      a, CH_ENV
                ld      c, 146
                ld      b, 0
                jp      add_back
dtr_empty:      ld      a, e
                cp      4
                ret     nc
                ld      hl, blueline_fram1
                call    tab_get
                ld      c, a
                ld      hl, blueline_fram_y
                ld      a, e
                call    tab_get
                call    main_plus
                call    blit_or
                ld      a, CH_ENV
                ld      b, 0
                jp      add_back
dtr_floor:      push    de
                ld      a, T_FLOOR
                call    tt_entry
                ld      a, (ix+TT_RIGHT_Y)
                call    main_plus
                call    blit_or         ; transp
                ld      a, CH_ENV
                ld      c, 42
                ld      b, 0
                call    add_back
                pop     de
                ld      a, e
                cp      4
                jp      c, dtrf1
                xor     a
dtrf1:          ld      e, a
                ld      a, (LEVEL_TYPE)
                or      a
                jp      z, dtrf2
                ld      a, 1
dtrf2:          cp      e
                ret     z
                ld      hl, blueline_fram3
                ld      a, e
                call    tab_get
                ld      c, a
                ld      a, -20
                call    main_plus
                call    blit_copy
                ld      a, CH_ENV
                ld      b, 0
                jp      add_back
dtr_dtop:       ld      a, (LEVEL_TYPE)
                or      a
                ret     z
                ld      hl, doortop_fram_bot
                ld      a, e
                call    tab_get
                ld      c, a
                ld      a, (TILE_LEFT)
                call    tt_entry
                ld      a, (ix+TT_RIGHT_Y)
                call    main_plus
                call    blit_or
                ld      a, CH_ENV
                ld      b, 0
                jp      add_back
dtr_wall:       ld      a, (LEVEL_TYPE)
                or      a
                jp      z, dtrw1
                bit     7, e
                jp      nz, dtrw1
                ld      a, 3
                call    xh_plus
                ld      a, -27
                call    main_plus
                call    blit_copy
                ld      a, CH_ENV
                ld      c, 84
                ld      b, 0
                call    add_back
                xor     a
                call    xh_plus
dtrw1:          ld      a, T_WALL
                call    tt_entry
                ld      a, (ix+TT_RIGHT_Y)
                call    main_plus
                call    blit_or
                ld      a, CH_WALL
                ld      c, 1
                ld      b, 0
                jp      add_back

; A = modifier -> A = spike frame
spike_frame:    bit     7, a
                ret     z
                ld      a, 5
                ret
; A = modifier -> A = loose frame
loose_frame:    bit     7, a
                ret     z
                and     0x7f
                cp      11
                ret     c
                ld      a, 1
                ret

draw_tile_anim_right:
                xor     a
                call    xh_plus
                ld      a, (MOD_LEFT)
                ld      e, a
                ld      a, (TILE_LEFT)
                cp      T_SPIKE
                jp      z, dtar_spike
                cp      T_GATE
                jp      z, draw_gate_back
                cp      T_LOOSE
                jp      z, dtar_loose
                cp      T_LEVELDOOR_L
                jp      z, draw_leveldoor
                cp      T_TORCH
                jp      z, dtar_torch
                cp      T_TORCH_DEBRIS
                ret     nz
dtar_torch:     ld      a, e
                cp      9
                ret     nc
                inc     a
                ld      c, a
                ld      a, 1
                call    xh_plus
                ld      a, -40
                call    main_plus
                call    blit_copy
                ld      a, CH_OBJ
                ld      b, 0
                jp      add_back
dtar_spike:     ld      a, e
                call    spike_frame
                ld      hl, spikes_fram_right
                call    tab_get
                ld      c, a
                ld      a, -7
                call    main_plus
                call    blit_or
                ld      a, CH_ENV
                ld      b, 0
                jp      add_back
dtar_loose:     ld      a, e
                call    loose_frame
                ld      hl, loose_fram_right
                call    tab_get
                ld      c, a
                ld      a, -1
                call    bottom_plus
                call    blit_or
                ld      a, CH_ENV
                ld      b, 0
                jp      add_back

; draw_tile_bottom: A = arg (also fore when nonzero)
draw_tile_bottom:
                ld      (A_TMP2), a
                xor     a
                call    xh_plus
                ld      a, (CURR_TILE)
                cp      T_WALL
                jp      nz, dtb1
                ld      a, (CURR_MOD)
                and     0x7f
                ld      hl, wall_fram_bottom
                call    tab_get
                ld      c, a
                ld      d, CH_WALL
                call    blit_copy
                jp      dtb2
dtb1:           push    af
                call    blit_copy
                pop     af
                cp      T_DOORTOP
                jp      nz, dtb1b
                ld      a, BL_OR
                ld      (V_BLIT), a
                ld      a, T_DOORTOP
dtb1b:          call    tt_entry
                ld      c, (ix+TT_BOTTOM_ID)
                ld      d, CH_ENV
dtb2:           push    de
                push    bc
                ld      hl, (DRAW_BOTTOM_Y)
                ld      a, d
                ld      b, 0
                call    add_ptr
                pop     bc
                pop     de
                or      a
                jp      z, dtb3
                ld      a, (A_TMP2)
                or      a
                jp      z, dtb3
                ld      hl, (DRAW_BOTTOM_Y)
                ld      a, d
                ld      b, 0
                push    de
                call    add_fore
                pop     de
dtb3:           ld      a, d
                cp      CH_WALL
                ret     nz
                xor     a
                ld      (WP_PART), a
                ld      (WP_TABLE), a   ; back
                jp      wall_pattern

draw_loose:     ld      a, (CURR_TILE)
                cp      T_LOOSE
                ret     nz
                xor     a
                call    xh_plus
                ld      a, (CURR_MOD)
                call    loose_frame
                ld      hl, loose_fram_bottom
                call    tab_get
                ld      c, a
                push    bc
                call    blit_copy
                ld      hl, (DRAW_BOTTOM_Y)
                ld      a, CH_ENV
                ld      b, 0
                call    add_back
                pop     bc
                ld      hl, (DRAW_BOTTOM_Y)
                ld      a, CH_ENV
                ld      b, 0
                jp      add_fore

draw_tile_base: xor     a
                call    xh_plus
                ld      hl, (DRAW_MAIN_Y)
                ld      (A_TMP), hl     ; yb (16-bit at A_TMP/A_TMP2)
                ld      a, (TILE_LEFT)
                cp      T_LATTICE_DOWN
                jp      nz, dtba1
                ld      a, (CURR_TILE)
                cp      T_DOORTOP
                jp      nz, dtba1
                ld      c, 6
                ld      hl, (A_TMP)
                inc     hl
                inc     hl
                inc     hl
                ld      (A_TMP), hl
                jp      dtba_go
dtba1:          ld      a, (CURR_TILE)
                cp      T_LOOSE
                jp      nz, dtba2
                ld      a, (CURR_MOD)
                call    loose_frame
                ld      hl, loose_fram_left
                call    tab_get
                ld      c, a
                jp      dtba_go
dtba2:          cp      T_OPENER
                jp      nz, dtba3
                ld      a, (TILE_LEFT)
                or      a
                jp      nz, dtba3
                ld      a, (LEVEL_TYPE)
                or      a
                jp      nz, dtba3
                ld      c, 148
                jp      dtba_go
dtba3:          ld      a, (CURR_TILE)
                call    tt_entry
                ld      c, (ix+TT_BASE_ID)
dtba_go:        push    bc
                ld      a, (CURR_TILE)
                call    tt_entry
                ld      a, (ix+TT_BASE_Y)
                ld      hl, (A_TMP)
                ld      e, a
                rla
                sbc     a, a
                ld      d, a
                add     hl, de
                call    blit_or
                pop     bc
                ld      a, CH_ENV
                ld      b, 0
                jp      add_ptr

draw_tile_anim: ld      a, (CURR_MOD)
                ld      e, a
                ld      a, (CURR_TILE)
                cp      T_SPIKE
                jp      z, dta_spike
                cp      T_POTION
                jp      z, dta_potion
                cp      T_SWORD
                jp      z, dta_sword
                cp      T_CHOMPER
                jp      z, dta_chomper
                ret
dta_spike:      xor     a
                call    xh_plus
                ld      a, e
                call    spike_frame
                ld      hl, spikes_fram_left
                call    tab_get
                ld      c, a
                ld      a, -2
                call    main_plus
                call    blit_or
                ld      a, CH_ENV
                ld      b, 0
                jp      add_ptr
dta_potion:     ld      a, e
                and     0xf8
                rrca
                rrca
                rrca
                ld      d, a            ; potion type
                or      a
                ret     z
                ld      c, 12           ; colour
                ld      b, 0            ; pot size
                cp      5
                jp      z, dtap_blue
                cp      6
                jp      z, dtap_blue
                cp      3
                jp      z, dtap_green
                cp      4
                jp      z, dtap_green
                cp      2
                jp      nz, dtap_go
                ld      b, 1
                jp      dtap_go
dtap_green:     ld      c, 10
                ld      b, 1
                jp      dtap_go
dtap_blue:      ld      c, 9
dtap_go:        ld      a, c
                ld      (A_TMP), a      ; colour
                ld      a, b
                add     a, a
                add     a, a
                add     a, 14
                neg                     ; -(pot<<2) - 14
                call    main_plus
                ld      (A_TMP2), hl    ; (A_TMP2, +1): y (16-bit)
                ld      a, 3
                call    xh_plus
                ld      a, BL_MONO
                ld      c, 0
                call    set_blit
                ld      hl, (A_TMP2)
                ld      a, CH_OBJ
                ld      c, 23
                ld      b, 1
                call    add_back
                ld      a, (CURR_MOD)
                and     7
                ld      hl, potion_fram_bubb
                call    tab_get
                ld      c, a
                ld      a, (A_TMP)
                push    bc
                ld      c, a
                ld      a, BL_MONO
                call    set_blit
                pop     bc
                ld      hl, (A_TMP2)
                ld      a, CH_OBJ
                ld      b, 1
                jp      add_fore
dta_sword:      xor     a
                call    xh_plus
                ld      c, 10
                ld      a, e
                cp      1
                jp      nz, dtas1
                inc     c
dtas1:          ld      a, -3
                call    main_plus
                call    blit_or
                ld      a, CH_OBJ
                ld      b, 0
                jp      add_mid
dta_chomper:    ld      a, e
                and     0x7f
                cp      7
                jp      c, dtac1
                ld      a, 6
dtac1:          ld      hl, chomper_fram1
                call    tab_get
                ld      (A_TMP), a      ; n
                xor     a
                call    xh_plus
                ld      a, (A_TMP)
                ld      hl, chomper_fram_bot
                call    tab_get
                ld      c, a
                ld      hl, (DRAW_MAIN_Y)
                call    blit_or
                ld      a, CH_ENV
                ld      b, 0
                call    add_back
                ld      a, (CURR_MOD)
                bit     7, a
                jp      z, dtac2
                ld      a, 1
                call    xh_plus
                ld      a, (A_TMP)
                add     a, 114
                ld      c, a
                ld      a, BL_MONO
                push    bc
                ld      c, 12
                call    set_blit
                pop     bc
                ld      a, -6
                call    main_plus
                ld      a, CH_ENV
                ld      b, 4
                call    add_back
                xor     a
                call    xh_plus
dtac2:          ld      a, (A_TMP)
                ld      hl, chomper_fram_top
                call    tab_get
                ld      c, a
                ld      a, (A_TMP)
                ld      hl, chomper_fram_y
                call    tab_get
                neg
                call    main_plus
                call    blit_or
                ld      a, CH_ENV
                ld      b, 0
                jp      add_back

draw_tile_fore: ld      a, (CURR_MOD)
                ld      e, a
                ld      a, (CURR_TILE)
                cp      T_SPIKE
                jp      z, dtf_spike
                cp      T_CHOMPER
                jp      z, dtf_chomper
                cp      T_WALL
                jp      z, dtf_wall
                ; default
                call    tt_entry
                ld      a, (ix+TT_FORE_ID)
                or      a
                ret     z
                ld      c, a
                ld      a, (CURR_TILE)
                cp      T_POTION
                jp      nz, dtf_d1
                ld      a, (CURR_MOD)   ; (E was clobbered by tt_entry)
                and     0xf8
                rrca
                rrca
                rrca
                cp      2
                jp      c, dtf_d1
                cp      5
                jp      nc, dtf_d1
                ld      c, 13
dtf_d1:         ld      a, (ix+TT_FORE_X)
                call    xh_plus
                ld      a, (ix+TT_FORE_Y)
                call    main_plus
                ld      a, (CURR_TILE)
                cp      T_POTION
                jp      nz, dtf_d2
                ld      a, (LEVEL_TYPE)
                or      a
                jp      z, dtf_d1b
                inc     c
                inc     c
dtf_d1b:        push    bc
                call    blit_or
                pop     bc
                ld      a, CH_OBJ
                ld      b, 6
                jp      add_fore
dtf_d2:         push    hl
                push    bc
                call    blit_or
                ld      a, (CURR_TILE)
                cp      T_PILLAR
                jp      nz, dtf_d3
                ld      a, (LEVEL_TYPE)
                or      a
                jp      nz, dtf_d4
                jp      dtf_copy
dtf_d3:         cp      T_LATTICE_SMALL
                jp      c, dtf_d4
                cp      T_TORCH_DEBRIS
                jp      nc, dtf_d4
dtf_copy:       call    blit_copy
dtf_d4:         pop     bc
                pop     hl
                ld      a, CH_ENV
                ld      b, 0
                jp      add_fore
dtf_spike:      xor     a
                call    xh_plus
                ld      a, e
                call    spike_frame
                ld      hl, spikes_fram_fore
                call    tab_get
                ld      c, a
                ld      a, -2
                call    main_plus
                call    blit_or
                ld      a, CH_ENV
                ld      b, 0
                jp      add_fore
dtf_chomper:    ld      a, e
                and     0x7f
                cp      7
                jp      c, dtfc1
                ld      a, 6
dtfc1:          ld      hl, chomper_fram1
                call    tab_get
                ld      (A_TMP), a
                xor     a
                call    xh_plus
                ld      a, (A_TMP)
                ld      hl, chomper_fram_for
                call    tab_get
                ld      c, a
                ld      hl, (DRAW_MAIN_Y)
                call    blit_or
                ld      a, CH_ENV
                ld      b, 0
                call    add_fore
                ld      a, (CURR_MOD)
                bit     7, a
                ret     z
                ld      a, 1
                call    xh_plus
                ld      a, (A_TMP)
                add     a, 119
                ld      c, a
                push    bc
                ld      a, BL_MONO
                ld      c, 12
                call    set_blit
                pop     bc
                ld      a, -6
                call    main_plus
                ld      a, CH_ENV
                ld      b, 4
                jp      add_fore
dtf_wall:       xor     a
                call    xh_plus
                ld      a, e
                and     0x7f
                ld      hl, wall_fram_main
                call    tab_get
                ld      c, a
                ld      hl, (DRAW_MAIN_Y)
                call    blit_copy
                ld      a, CH_WALL
                ld      b, 0
                call    add_fore
                ld      a, 1
                ld      (WP_PART), a
                ld      (WP_TABLE), a   ; fore
                jp      wall_pattern

; ---------------------------------------------------------------- gate / level door
draw_gate_back: ld      hl, (DRAW_BOTTOM_Y)
                ld      de, 62
                or      a
                sbc     hl, de
                ld      (GATE_TOP), hl
                ld      a, (MOD_LEFT)
                cp      189
                jp      c, dgb1
                ld      a, 188
dgb1:           rrca
                rrca
                and     0x3f
                inc     a               ; openness
                ld      e, a
                ld      d, 0
                ld      hl, (DRAW_MAIN_Y)
                or      a
                sbc     hl, de
                ld      (GATE_BOTTOM), hl
                ; if gate_bottom + 12 < main_y
                ld      de, 12
                add     hl, de
                ld      de, (DRAW_MAIN_Y)
                or      a
                sbc     hl, de          ; (gb+12) - main
                jp      p, dgb_closed
                xor     a
                call    xh_plus
                ld      hl, (GATE_BOTTOM)
                call    blit_copy
                ld      a, CH_ENV
                ld      c, 50
                ld      b, 0
                call    add_back
                jp      dgb_slices
dgb_closed:     xor     a
                call    xh_plus
                ld      a, T_GATE
                call    tt_entry
                ld      c, (ix+TT_RIGHT_ID)
                ld      a, (ix+TT_RIGHT_Y)
                call    main_plus
                call    blit_copy
                ld      a, CH_ENV
                ld      b, 0
                call    add_back
                call    can_see_bl
                call    z, draw_tile_topright
                xor     a
                call    draw_tile_bottom
                call    draw_loose
                call    draw_tile_base
                xor     a
                call    xh_plus
                ld      hl, (GATE_BOTTOM)
                dec     hl
                dec     hl
                call    blit_or
                ld      a, CH_ENV
                ld      c, 51
                ld      b, 0
                call    add_back
dgb_slices:     ld      hl, (GATE_BOTTOM)
                ld      de, 12
                or      a
                sbc     hl, de
                ld      (GATE_YB), hl
                ; if yb < 192
                ld      de, 192
                or      a
                sbc     hl, de
                jp      p, dgb_frame
dgb_loop:       ld      hl, (GATE_YB)   ; while yb >= 0 and yb > 7 and yb - 7 > gate_top
                bit     7, h
                jp      nz, dgb_frame
                ld      de, 8
                or      a
                sbc     hl, de          ; yb - 8 >= 0  <=> yb > 7
                jp      m, dgb_frame
                ld      hl, (GATE_YB)
                ld      de, 7
                or      a
                sbc     hl, de          ; yb - 7
                ld      de, (GATE_TOP)
                or      a
                sbc     hl, de          ; (yb-7) - gate_top > 0 ?
                jp      m, dgb_frame
                ld      a, h
                or      l
                jp      z, dgb_frame
                xor     a
                call    xh_plus
                ld      hl, (GATE_YB)
                call    blit_copy
                ld      a, CH_ENV
                ld      c, 52
                ld      b, 0
                call    add_back
                ld      hl, (GATE_YB)
                ld      de, 8
                or      a
                sbc     hl, de
                ld      (GATE_YB), hl
                jp      dgb_loop
dgb_frame:      ld      hl, (GATE_YB)
                ld      de, (GATE_TOP)
                or      a
                sbc     hl, de
                inc     hl              ; frame
                ld      a, h
                or      a
                ret     nz              ; negative or >= 256
                ld      a, l
                or      a
                ret     z
                cp      9
                ret     nc
                ld      hl, door_fram_slice
                call    tab_get
                ld      c, a
                xor     a
                call    xh_plus
                ld      hl, (GATE_YB)
                call    blit_copy
                ld      a, CH_ENV
                ld      b, 0
                jp      add_back

draw_leveldoor: ld      a, -13
                call    main_plus
                ld      (LD_YB), hl     ; yb
                ld      a, 1
                call    xh_plus
                call    blit_copy
                ld      hl, (LD_YB)
                ld      a, CH_ENV
                ld      c, 99
                ld      b, 0
                call    add_back
                ld      a, (MOD_LEFT)
                or      a
                jp      z, dld1
                ld      a, (LV_START_ROOM)
                ld      hl, R_ROOM
                cp      (hl)
                jp      z, dld1         ; start room: wipe (not drawn statically)
                ld      a, 1
                call    xh_plus
                ld      hl, (LD_YB)
                ld      de, 4
                or      a
                sbc     hl, de
                call    blit_copy
                ld      a, CH_ENV
                ld      c, 144
                ld      b, 0
                call    add_back
dld1:           ld      a, (MOD_LEFT)
                and     3
                add     a, 48
                ld      e, a
                ld      d, 0
                ld      hl, (LD_YB)
                or      a
                sbc     hl, de
                ld      (LD_Y), hl      ; leveldoor_ybottom (LD_Y)
                ld      a, (MOD_LEFT)
                ld      e, a
                ld      hl, (LD_YB)
                or      a
                sbc     hl, de
                ld      (A_TMP), hl     ; y
dld_loop:       ld      a, 1
                call    xh_plus
                call    blit_copy
                ld      hl, (LD_Y)
                ld      a, CH_ENV
                ld      c, 33
                ld      b, 0
                call    add_back
                ld      hl, (A_TMP)
                ld      de, (LD_Y)
                or      a
                sbc     hl, de          ; y - ld_yb > 0 ?
                jp      m, dld2
                ld      a, h
                or      l
                jp      z, dld2
                ld      hl, (LD_Y)
                inc     hl
                inc     hl
                inc     hl
                inc     hl
                ld      (LD_Y), hl
                jp      dld_loop
dld2:           ld      a, 1
                call    xh_plus
                ld      a, -64
                call    main_plus
                call    blit_copy
                ld      a, CH_ENV
                ld      c, 34
                ld      b, 0
                jp      add_back

; ---------------------------------------------------------------- PRNG (seed = seed*214013 + 2531011; result = (seed>>16) % (max+1))
; prandom: A = max -> A = random in 0..max
MUL_K           equ     RV + 100        ; 32-bit constant copy
; The wall pattern seeds the generator with row*10 + col + room and draws at most 10 numbers, all reduced mod
; 2, 4, 5 or 7 (divisors of 140): for seeds below 64 they come from a table of the draws mod 140 (PR_TAB,
; built once by the generator itself); other seeds use the generator.
prandom:        push    hl
                ld      hl, (pr_ptr)            ; 0: the generator
                inc     h
                dec     h
                jp      z, pr_gen
                push    bc
                ld      c, a                    ; max
                ld      b, (hl)                 ; the draw mod 140
                inc     hl
                ld      (pr_ptr), hl
                inc     a
                and     c
                jp      nz, pr_md
                ld      a, b                    ; max + 1 a power of two
                and     c
                pop     bc
                pop     hl
                ret
pr_md:          ld      a, c                    ; mod 5 or 7: subtract 16d, 8d, 4d, 2d, d
                inc     a
                add     a, a
                add     a, a
                add     a, a
                add     a, a
                ld      c, a
                ld      a, b
                ld      b, 5
pr_dl:          cp      c
                jp      c, pr_dn
                sub     c
pr_dn:          srl     c
                djnz    pr_dl
                pop     bc
                pop     hl
                ret
pr_gen:         pop     hl
pr_slow:        push    bc
                push    de
                push    hl
                ld      (pr_max), a
                ; seed = seed * 214013 + 2531011  (mod 2^32), computed as (S<<10)*17 - 3S + (low16(3S) << 16) + K
                ld      hl, (SEED)
                ld      de, (SEED+2)    ; DE:HL = S
                add     hl, hl
                ex      de, hl
                adc     hl, hl
                ex      de, hl          ; 2S
                ld      bc, (SEED)
                add     hl, bc
                ex      de, hl
                ld      bc, (SEED+2)
                adc     hl, bc
                ex      de, hl          ; 3S
                ld      (MUL_T), hl
                ld      (MUL_T+2), de
                ld      hl, (SEED)
                ld      de, (SEED+2)
                ld      d, e            ; << 8
                ld      e, h
                ld      h, l
                ld      l, 0
                add     hl, hl          ; << 2
                rl      e
                rl      d
                add     hl, hl
                rl      e
                rl      d               ; X = S << 10
                ld      (MUL_A), hl
                ld      (MUL_A+2), de
                add     hl, hl          ; X << 4
                rl      e
                rl      d
                add     hl, hl
                rl      e
                rl      d
                add     hl, hl
                rl      e
                rl      d
                add     hl, hl
                rl      e
                rl      d
                ld      bc, (MUL_A)
                add     hl, bc
                ex      de, hl
                ld      bc, (MUL_A+2)
                adc     hl, bc
                ex      de, hl          ; X * 17
                ld      bc, (MUL_T)
                or      a
                sbc     hl, bc
                ex      de, hl
                ld      bc, (MUL_T+2)
                sbc     hl, bc          ; - 3S  (HL = high word now)
                ld      bc, (MUL_T)
                add     hl, bc          ; high += low16(3S)
                ex      de, hl
                ld      bc, 0x9ec3
                add     hl, bc
                ex      de, hl
                ld      bc, 0x0026
                adc     hl, bc
                ex      de, hl
                ld      (SEED), hl
                ld      (SEED+2), de
                ; (seed >> 16) % (max+1): 16-bit by 8-bit restoring division, remainder in A
                ld      a, (pr_max)
                inc     a
                ld      c, a
                ld      hl, (SEED+2)
                xor     a
                ld      b, 16
pr_div:         add     hl, hl
                rla
                cp      c
                jp      c, pr_div2
                sub     c
pr_div2:        djnz    pr_div
                pop     hl
                pop     de
                pop     bc
                ret
pr_max:         db      0
pr_ptr:         dw      0                       ; the next table draw (0: the generator)
; pr_start: after the wall pattern's seed is set: draw from the table when the seed has one
                if not defined GAME_OVL          ; (the game builds PR_TAB at its start: src/m4/gstart.asm)
pr_ok:          db      0                       ; PR_TAB built
                endif
pr_start:
                if not defined GAME_OVL
                ld      a, (pr_ok)
                or      a
                call    z, pr_build
                endif
                ld      hl, 0
                ld      a, (SEED)
                cp      PR_SEEDS
                jp      nc, prs_x
                ld      l, a
                add     hl, hl
                ld      e, l
                ld      d, h
                add     hl, hl
                add     hl, hl
                add     hl, de                  ; seed * 10
                ld      de, PR_TAB
                add     hl, de
prs_x:          ld      (pr_ptr), hl
                ret
; pr_build: src/m3/prbuild.asm (the game: the level-start overlay)
                if not defined GAME_OVL
                include "../m3/prbuild.asm"
                endif

; ---------------------------------------------------------------- wall pattern (dungeon style; palace in EGA uses it too, without marks)
wall_pattern:   ld      hl, (SEED)
                ld      (SEEDSAVE), hl
                ld      hl, (SEED+2)
                ld      (SEEDSAVE+2), hl
                ld      a, (DRAWN_ROW)
                ld      hl, tbl_line
                call    tab_get
                ld      hl, DRAWN_COL
                add     a, (hl)
                ld      hl, R_ROOM
                add     a, (hl)
                ld      l, a
                ld      h, 0
                ld      (SEED), hl
                ld      hl, 0
                ld      (SEED+2), hl
                call    pr_start
                ld      a, 1
                call    prandom         ; discard
                ld      a, 1
                call    prandom
                ld      (WP_MD), a
                ld      a, 4
                call    prandom
                ld      (WP_MDO), a
                ld      a, 1
                call    prandom
                ld      (WP_BD), a
                ld      a, 4
                call    prandom
                ld      (WP_BDO), a
                ld      a, (CURR_MOD)
                and     0x7f
                cp      3
                jp      z, wp_www
                cp      0
                jp      z, wp_sws
                cp      1
                jp      z, wp_sww
                cp      2
                jp      z, wp_wws
                jp      wp_end
wp_www:         ld      a, (WP_PART)
                or      a
                jp      z, wp_www2
                call    wp_rndblock
                call    wp_middiv
wp_www2:        call    wp_botdiv
                ld      a, (WP_PART)
                or      a
                jp      z, wp_end
                ld      a, (LEVEL_TYPE)
                or      a
                jp      nz, wp_end
                ld      a, 4
                call    prandom
                or      a
                jp      nz, wp_www3
                ld      a, 3
                call    prandom
                call    right_mark
wp_www3:        ld      a, 4
                call    prandom
                or      a
                jp      nz, wp_end
                ld      a, 4
                call    prandom
                call    left_mark
                jp      wp_end
wp_sws:         ld      a, (LEVEL_TYPE)
                or      a
                jp      nz, wp_end
                ld      a, (WP_PART)
                or      a
                jp      z, wp_end
                ld      a, 6
                call    prandom
                or      a
                jp      nz, wp_end
                ld      a, 1
                call    prandom
                call    left_mark
                jp      wp_end
wp_sww:         ld      a, (WP_PART)
                or      a
                jp      z, wp_end
                call    wp_rndblock
                call    wp_middiv
                ld      a, (LEVEL_TYPE)
                or      a
                jp      nz, wp_end
                ld      a, 4
                call    prandom
                or      a
                jp      nz, wp_sww2
                ld      a, 3
                call    prandom
                call    right_mark
wp_sww2:        ld      a, 4
                call    prandom
                or      a
                jp      nz, wp_end
                ld      a, 3
                call    prandom
                call    left_mark
                jp      wp_end
wp_wws:         ld      a, (WP_PART)
                or      a
                jp      z, wp_wws2
                call    wp_middiv
wp_wws2:        call    wp_botdiv
                ld      a, (WP_PART)
                or      a
                jp      z, wp_end
                ld      a, (LEVEL_TYPE)
                or      a
                jp      nz, wp_end
                ld      a, 4
                call    prandom
                or      a
                jp      nz, wp_wws3
                ld      a, 1
                call    prandom
                add     a, 2
                call    right_mark
wp_wws3:        ld      a, 4
                call    prandom
                or      a
                jp      nz, wp_end
                ld      a, 4
                call    prandom
                call    left_mark
wp_end:         ld      hl, (SEEDSAVE)
                ld      (SEED), hl
                ld      hl, (SEEDSAVE+2)
                ld      (SEED+2), hl
                ld      hl, 0                   ; other draws (the game's) come from the generator
                ld      (pr_ptr), hl
                ret

; add through the wall-pattern table (WP_TABLE: 0 back, 1 fore)
wp_add:         push    af
                ld      a, (WP_TABLE)
                or      a
                jp      z, wpa_back
                pop     af
                jp      add_fore
wpa_back:       pop     af
                jp      add_back

wp_rndblock:    ld      a, 4
                call    prandom
                or      a
                ret     nz
                xor     a
                call    xh_plus
                ld      a, -42
                call    bottom_plus
                call    blit_copy
                ld      a, CH_WALL
                ld      c, 13
                ld      b, 0
                jp      wp_add
wp_middiv:      ld      a, 1
                call    xh_plus
                ld      a, (WP_MD)
                add     a, 11
                ld      c, a
                ld      a, (WP_MDO)
                ld      b, a
                ld      a, -21
                call    bottom_plus
                call    blit_or
                ld      a, CH_WALL
                jp      wp_add
wp_botdiv:      xor     a
                call    xh_plus
                ld      a, (WP_BD)
                add     a, 11
                ld      c, a
                ld      a, (WP_BDO)
                ld      b, a
                ld      hl, (DRAW_BOTTOM_Y)
                call    blit_or
                ld      a, CH_WALL
                jp      wp_add

; left_mark: A = variant; arg2 = mdo - md, arg1 = bdo - bd
left_mark:      ld      e, a            ; v
                ld      c, 14           ; image
                bit     0, a
                jp      z, lm1
                ld      c, 15
lm1:            ld      b, 0            ; lv2
                cp      4
                jp      c, lm2
                ld      a, (WP_BDO)
                ld      hl, WP_BD
                sub     (hl)
                add     a, 6
                ld      b, a
                jp      lm3
lm2:            cp      2
                jp      c, lm3
                ld      a, (WP_MDO)
                ld      hl, WP_MD
                sub     (hl)
                add     a, 6
                ld      b, a
lm3:            ld      a, e
                cp      2
                jp      z, lm_x1
                cp      3
                jp      z, lm_x1
                xor     a
                jp      lm4
lm_x1:          ld      a, 1
lm4:            call    xh_plus
                push    bc
                ld      hl, lpos_tab
                ld      a, e
                call    tab_get
                neg
                call    bottom_plus
                call    blit_or
                pop     bc
                ld      a, CH_WALL
                jp      wp_add
; right_mark: A = variant; arg1 = mdo
right_mark:     ld      e, a
                ld      c, 16
                bit     0, a
                jp      z, rm1
                ld      c, 17
rm1:            cp      2
                jp      nc, rm2
                ld      b, 24
                xor     a
                jp      rm3
rm2:            ld      a, (WP_MDO)
                sub     3
                ld      b, a
                ld      a, 1
rm3:            call    xh_plus
                push    bc
                ld      hl, rpos_tab
                ld      a, e
                call    tab_get
                neg
                call    bottom_plus
                call    blit_or
                pop     bc
                ld      a, CH_WALL
                jp      wp_add

; ---------------------------------------------------------------- draw_tile sequences and draw_room
draw_tile:      call    draw_tile_floorright
                call    draw_tile_anim_topright
                call    draw_tile_right
                call    draw_tile_anim_right
                xor     a
                call    draw_tile_bottom
                call    draw_loose
                call    draw_tile_base
                call    draw_tile_anim
                jp      draw_tile_fore
draw_tile_above:
                call    draw_tile_floorright
                call    draw_tile_anim_topright
                call    draw_tile_right
                xor     a
                call    draw_tile_bottom
                call    draw_loose
                jp      draw_tile_fore

; row_ys: A = row -> DRAW_BOTTOM_Y = 63*row + 65, DRAW_MAIN_Y = bottom - 3
row_ys:         ld      l, a
                ld      h, 0
                ld      d, h
                ld      e, l
                add     hl, hl
                add     hl, hl
                add     hl, hl
                add     hl, hl
                add     hl, hl
                add     hl, hl          ; *64
                or      a
                sbc     hl, de          ; *63
                ld      de, 65
                add     hl, de
                ld      (DRAW_BOTTOM_Y), hl
                dec     hl
                dec     hl
                dec     hl
                ld      (DRAW_MAIN_Y), hl
                ret
; ---------------------------------------------------------------- per-tile regeneration (animated tiles)
; tile_gen: A = tag; generate the ops of that one tile into the current lists (state set up as room_ops does)
tile_gen:       ld      (CUR_TAG), a
                cp      30
                jp      nc, tg_above
                ld      b, 0
tg_r:           cp      10
                jp      c, tg_r2
                sub     10
                inc     b
                jp      tg_r
tg_r2:          ld      (DRAWN_COL), a
                ld      a, b
                ld      (DRAWN_ROW), a
                call    load_rowbelow
                ld      a, (DRAWN_ROW)
                call    row_ys
                call    load_curr_left
                jp      draw_tile
tg_above:       sub     30
                ld      (DRAWN_COL), a
                ld      a, (R_ROOM)
                ld      (R_SAVED), a
                ld      a, (R_A)
                ld      (R_ROOM), a
                call    load_room_links
                call    load_leftroom
                ld      a, 2
                ld      (DRAWN_ROW), a
                call    load_rowbelow
                call    load_curr_left
                ld      hl, -1
                ld      (DRAW_MAIN_Y), hl
                ld      hl, 2
                ld      (DRAW_BOTTOM_Y), hl
                call    draw_tile_above
                ld      a, (R_SAVED)
                ld      (R_ROOM), a
lrl_lr:         call    load_room_links ; (also called alone: src/m4/gate.asm gate_redraw)
                jp      load_leftroom

; tag_key: A = tag -> A = position key in list order (row 2 first, then 1, 0, then the above row)
tag_key:        cp      30
                ret     nc
                push    bc
                ld      b, 0
tk_r:           cp      10
                jp      c, tk_r2
                sub     10
                inc     b
                jp      tk_r
tk_r2:          ld      c, a            ; col
                ld      a, 2
                sub     b
                add     a, a
                ld      b, a
                add     a, a
                add     a, a
                add     a, b            ; (2-row)*10
                add     a, c
                pop     bc
                ret

; tile_regen: A = tag. Regenerate the tile's ops into the temp lists, splice them over the old slice in each
; list, add old and new op rects to the dirty rect.
tile_regen:     ld      (TR_TAG), a
                ld      hl, ops_gen             ; (records move: callers keeping record addresses check this)
                inc     (hl)
                call    tag_key
                ld      (TR_KEY), a
                ld      hl, opl_base    ; save the list configuration, switch to the temp lists
                ld      de, TR_SAVE
                ld      bc, 6
                ldir
                ld      hl, opl_max
                ld      bc, 3
                ldir
                ld      hl, OPCOUNT
                ld      bc, 3
                ldir
                ld      hl, opt_base
                ld      bc, 6
                ldir
                ld      hl, tmp_cfg
                ld      de, opl_base
                ld      bc, 6
                ldir
                ld      de, opl_max
                ld      bc, 3
                ldir
                ld      de, OPCOUNT
                ld      bc, 3
                ldir
                ld      de, opt_base
                ld      bc, 6
                ldir
                ld      a, (TR_TAG)
                call    tile_gen
                ld      hl, OPCOUNT
                ld      de, TR_NNEW
                ld      bc, 3
                ldir
                ld      hl, TR_SAVE     ; restore
                ld      de, opl_base
                ld      bc, 6
                ldir
                ld      de, opl_max
                ld      bc, 3
                ldir
                ld      de, OPCOUNT
                ld      bc, 3
                ldir
                ld      de, opt_base
                ld      bc, 6
                ldir
                xor     a
tr_tbl:         ld      (TR_TBL), a
                call    splice_tbl
                ld      a, (TR_TBL)
                inc     a
                cp      3
                jp      nz, tr_tbl
                jp      slices_fast

; splice_tbl: list TR_TBL: replace the slice tagged TR_TAG (or insert at its ordered position) with the temp list
splice_tbl:     ld      a, (TR_TBL)
                add     a, a
                ld      hl, opt_base
                add     a, l
                ld      l, a
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a
                ld      (sp_tags), hl
                ld      a, (TR_TBL)
                add     a, a
                ld      hl, opl_base
                add     a, l
                ld      l, a
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a
                ld      (sp_base), hl
                ld      a, (TR_TBL)
                ld      hl, OPCOUNT
                add     a, l
                ld      l, a
                ld      (sp_cntp), hl
                ld      a, (hl)
                ld      (sp_cnt), a
                ld      a, (TR_TBL)
                ld      hl, TR_NNEW
                add     a, l
                ld      l, a
                ld      a, (hl)
                ld      (sp_nnew), a
                ; i0 / n_old from the slice tables; a tile without ops is inserted before the next tile (in
                ; key order) that has some, or at the end
                ld      a, (TR_TBL)
                ld      c, a
                add     a, a
                add     a, a
                add     a, c
                add     a, a
                add     a, a
                add     a, a            ; tbl*40
                ld      c, a
                ld      hl, SL_CNT
                add     a, l
                ld      l, a
                ld      (sp_slc), hl
                ld      a, c
                ld      hl, SL_START
                add     a, l
                ld      l, a
                ld      (sp_sls), hl
                ld      hl, (sp_slc)
                ld      a, (TR_TAG)
                call    tab_get
                ld      (TR_NOLD), a
                or      a
                jp      z, sp_ins
                ld      hl, (sp_sls)
                ld      a, (TR_TAG)
                call    tab_get
                ld      (TR_I0), a
                jp      sp_move
sp_ins:         ld      a, (TR_KEY)
sp_ins1:        inc     a
                cp      40
                jp      z, sp_ins_end
                push    af
                ld      hl, tag_of_key
                call    tab_get
                ld      c, a
                ld      hl, (sp_slc)
                call    tab_get
                or      a
                jp      z, sp_ins2
                ld      hl, (sp_sls)
                ld      a, c
                call    tab_get
                ld      (TR_I0), a
                pop     af
                jp      sp_move
sp_ins2:        pop     af
                jp      sp_ins1
sp_ins_end:     ld      a, (sp_cnt)
                ld      (TR_I0), a
sp_move:        ; dirty rect: old and new records compared pairwise; only differing ones (and the surplus of
                ; the longer slice) are added
                ld      a, (TR_I0)
                call    sp_rec
                ld      (sp_old), hl
                ld      a, (TR_TBL)
                add     a, a
                ld      hl, tmp_cfg
                add     a, l
                ld      l, a
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a
                ld      (sp_new), hl
                ld      a, (TR_NOLD)
                ld      b, a
                ld      a, (sp_nnew)
                ld      c, a
sp_dcmp:        ld      a, b
                or      a
                jp      z, sp_dnew      ; old exhausted: remaining new ones
                ld      a, c
                or      a
                jp      z, sp_dold      ; new exhausted: remaining old ones
                push    bc
                ld      hl, (sp_old)
                ld      de, (sp_new)
                ld      b, 8
sp_dc1:         ld      a, (de)
                cp      (hl)
                jp      nz, sp_ddiff
                inc     hl
                inc     de
                djnz    sp_dc1
                jp      sp_dnext
sp_ddiff:       ld      hl, (sp_old)
                call    dr_add
                ld      hl, (sp_new)
                call    dr_add
sp_dnext:       ld      hl, (sp_old)
                ld      de, 8
                add     hl, de
                ld      (sp_old), hl
                ld      hl, (sp_new)
                add     hl, de
                ld      (sp_new), hl
                pop     bc
                dec     b
                dec     c
                jp      sp_dcmp
sp_dnew:        ld      a, c
                or      a
                jp      z, sp_m1
                ld      b, c
                ld      hl, (sp_new)
                jp      sp_drest
sp_dold:        ld      hl, (sp_old)
sp_drest:       push    bc
                push    hl
                call    dr_add
                pop     hl
                pop     bc
                ld      de, 8
                add     hl, de
                djnz    sp_drest
sp_m1:          ; capacity: cnt - n_old + n_new <= max
                ld      a, (sp_cnt)
                ld      hl, TR_NOLD
                sub     (hl)
                ld      hl, sp_nnew
                add     a, (hl)
                ld      (sp_newcnt), a
                ld      c, a
                ld      a, (TR_TBL)
                ld      hl, opl_max
                add     a, l
                ld      l, a
                ld      a, (hl)
                cp      c
                ret     c               ; would overflow: leave the list alone
                ; move the tail: records [i0+n_old, cnt) -> [i0+n_new, ...)
                ld      a, (TR_I0)
                ld      hl, TR_NOLD
                add     a, (hl)
                ld      e, a            ; src index
                ld      a, (sp_cnt)
                sub     e
                ld      (sp_tail), a    ; tail records
                ld      a, (TR_I0)
                ld      hl, sp_nnew
                add     a, (hl)
                ld      d, a            ; dst index
                ld      a, (sp_tail)
                or      a
                jp      z, sp_copy
                ld      a, d
                cp      e
                jp      z, sp_copy
                jp      c, sp_down
                ; up (delta > 0): LDDR from the last byte of the tail
                ld      a, (sp_cnt)
                call    sp_rec
                dec     hl
                push    hl              ; src last byte = rec(cnt) - 1
                ld      a, (TR_I0)
                ld      hl, sp_nnew
                add     a, (hl)
                ld      hl, sp_tail
                add     a, (hl)
                call    sp_rec
                dec     hl
                ex      de, hl          ; dst last byte = rec(i0 + n_new + tail) - 1
                pop     hl
                ld      a, (sp_tail)
                call    mul8_bc
sp_up2:         lddr
                ld      a, (sp_cnt)     ; tags: src last = tags + cnt - 1, dst last = tags + i0 + n_new + tail - 1
                dec     a
                ld      hl, (sp_tags)
                call    sp_idx
                push    hl
                ld      a, (TR_I0)
                ld      hl, sp_nnew
                add     a, (hl)
                ld      hl, sp_tail
                add     a, (hl)
                dec     a
                ld      hl, (sp_tags)
                call    sp_idx
                ex      de, hl
                pop     hl
                ld      a, (sp_tail)
                ld      c, a
                ld      b, 0
                lddr
                jp      sp_copy
sp_down:        ; down (delta < 0): copy forwards
                ld      a, e
                call    sp_rec
                push    hl
                ld      a, d
                call    sp_rec
                ex      de, hl
                pop     hl
                ld      a, (sp_tail)
                call    mul8_bc
sp_dn2:         ldir
                ld      a, (TR_I0)      ; tags
                ld      hl, TR_NOLD
                add     a, (hl)
                ld      hl, (sp_tags)
                call    sp_idx
                push    hl
                ld      a, (TR_I0)
                ld      hl, sp_nnew
                add     a, (hl)
                ld      hl, (sp_tags)
                call    sp_idx
                ex      de, hl
                pop     hl
                ld      a, (sp_tail)
                ld      c, a
                ld      b, 0
                ldir
sp_copy:        ; copy the new records in, tag them, add their rects
                ld      a, (sp_newcnt)
                ld      hl, (sp_cntp)
                ld      (hl), a
                ld      a, (sp_nnew)
                or      a
                ret     z
                ld      a, (TR_TBL)
                add     a, a
                ld      hl, tmp_cfg
                add     a, l
                ld      l, a
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a            ; temp list base
                push    hl
                ld      a, (TR_I0)
                call    sp_rec
                ex      de, hl
                pop     hl
                push    hl
                ld      a, (sp_nnew)
                call    mul8_bc
sp_cp2:         ldir
                pop     hl
                ld      a, (TR_I0)
                ld      hl, (sp_tags)
                call    sp_idx
                ld      a, (sp_nnew)
                ld      b, a
                ld      a, (TR_TAG)
sp_cp4:         ld      (hl), a
                inc     hl
                djnz    sp_cp4
                ret
; mul8_bc: BC = A * 8 (16-bit)
mul8_bc:        push    hl
                ld      l, a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      b, h
                ld      c, l
                pop     hl
                ret
; sp_rec: A = record index -> HL = address in the list (sp_base)
sp_rec:         push    de
                ld      l, a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      de, (sp_base)
                add     hl, de
                pop     de
                ret
; sp_idx: HL = base, A = index -> HL = base + A
sp_idx:         ld      e, a
                ld      d, 0
                add     hl, de
                ret
sp_tags:        dw      0
sp_base:        dw      0
sp_cntp:        dw      0
sp_cnt:         db      0
sp_nnew:        db      0
sp_newcnt:      db      0
sp_tail:        db      0
sp_old:         dw      0
sp_new:         dw      0
sp_slc:         dw      0
sp_sls:         dw      0

; slices_fast: after tile_regen spliced tag TR_TAG: its three counts are TR_NNEW, the starts follow as running
; sums in list (key) order, and only its slices' extents are recomputed (slices_build walks every record)
slices_fast:    xor     a
sf_tbl:         ld      (sb_t), a
                ld      c, a
                add     a, a
                add     a, a
                add     a, c
                add     a, a
                add     a, a
                add     a, a                    ; tbl * 40
                ld      (sb_off), a
                ld      e, a
                ld      d, 0
                ld      a, (TR_TAG)             ; the new count
                add     a, e
                ld      l, a
                ld      h, 0
                ld      bc, SL_CNT
                add     hl, bc
                ld      a, (sb_t)
                ld      c, a
                ld      b, 0
                push    hl
                ld      hl, TR_NNEW
                add     hl, bc
                ld      a, (hl)
                pop     hl
                cp      (hl)
                jp      z, sf_ext               ; same count: the starts stand
                ld      (hl), a
                ld      c, 0                    ; running start
                ld      b, 40
                ld      hl, tag_of_key
sf_key:         ld      a, (sb_off)
                add     a, (hl)
                push    hl
                ld      l, a
                ld      h, 0
                ld      de, SL_START
                add     hl, de
                ld      (hl), c
                ld      de, SL_CNT - SL_START
                add     hl, de
                ld      a, c
                add     a, (hl)
                ld      c, a
                pop     hl
                inc     hl
                djnz    sf_key
sf_ext:         ld      a, (sb_off)             ; the extent of TR_TAG's slice
                ld      e, a
                ld      a, (TR_TAG)
                add     a, e
                ld      e, a
                ld      d, 0
                ld      hl, SL_Y0
                add     hl, de
                ld      (hl), 0xff
                ld      hl, SL_Y1
                add     hl, de
                ld      (hl), 0
                ld      hl, SL_CNT
                add     hl, de
                ld      a, (hl)
                or      a
                jp      z, sf_next
                ld      b, a
                ld      hl, SL_START
                add     hl, de
                ld      l, (hl)
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl
                push    de
                push    hl
                ld      a, (sb_t)
                add     a, a
                ld      e, a
                ld      d, 0
                ld      hl, opl_base
                add     hl, de
                ld      e, (hl)
                inc     hl
                ld      d, (hl)
                pop     hl
                add     hl, de
                ld      (sb_rec), hl
                pop     de
sf_rec:         push    bc
                call    sb_yr
                pop     bc
                djnz    sf_rec
sf_next:        ld      a, (sb_t)
                inc     a
                cp      3
                jp      nz, sf_tbl
                ret

sb_t:           db      0
sb_off:         db      0
sb_rec:         dw      0
; sb_yr: widen slot DE's extent by the record at sb_rec, then step sb_rec to the next record
sb_yr:          ld      hl, (sb_rec)
                push    hl
                ld      bc, 8
                add     hl, bc
                ld      (sb_rec), hl
                pop     hl
                ld      bc, 4
                add     hl, bc
                ld      c, (hl)
                inc     hl
                ld      b, (hl)         ; BC = ytop
                inc     hl
                inc     hl
                ld      l, (hl)
                ld      h, 0
                add     hl, bc          ; HL = ytop + h
; yr_merge: BC = ytop, HL = ybottom + 1 (16-bit signed), DE = slot: SL_Y0/SL_Y1 = min/max (clamped 0..200)
yr_merge:       call    yr_clamp
                ld      a, l
                push    hl
                ld      hl, SL_Y1
                add     hl, de
                cp      (hl)
                jp      c, yrm1
                ld      (hl), a
yrm1:           pop     hl
                ld      h, b
                ld      l, c
                call    yr_clamp
                ld      a, l
                ld      hl, SL_Y0
                add     hl, de
                cp      (hl)
                ret     nc
                ld      (hl), a
                ret
yr_clamp:       bit     7, h            ; HL -> 0..200 in L
                jp      nz, yrc0
                ld      a, h
                or      a
                jp      nz, yrc1
                ld      a, l
                cp      201
                ret     c
yrc1:           ld      l, 200
                ret
yrc0:           ld      l, 0
                ret

; ---------------------------------------------------------------- dirty rect
dr_reset:       ld      a, 40
                ld      (DR_X0), a
                xor     a
                ld      (DR_X1), a
                ld      (DR_Y1), a
                ld      a, 192
                ld      (DR_Y0), a
                ret
; dr_add: HL = op record; union its screen rect into DR_*
dr_add:         inc     hl
                inc     hl
                inc     hl
                ld      a, (hl)         ; xb (signed)
                inc     hl
                ld      e, (hl)
                inc     hl
                ld      d, (hl)         ; ytop
                inc     hl
                ld      b, (hl)         ; w
                inc     hl
                ld      c, (hl)         ; h
                ld      l, a            ; x0 = max(xb, 0)
                add     a, b
                ld      h, a            ; x1 = xb + w
                bit     7, l
                jr      z, dr_x0
                ld      l, 0
dr_x0:          bit     7, h            ; x1 negative: off screen
                ret     nz
                ld      a, h
                cp      41
                jr      c, dr_x1
                ld      h, 40
dr_x1:          ld      a, (DR_X0)
                cp      l
                jr      c, dr_x2
                ld      a, l
                ld      (DR_X0), a
dr_x2:          ld      a, (DR_X1)
                cp      h
                jr      nc, dr_y
                ld      a, h
                ld      (DR_X1), a
dr_y:           ; y0 = max(ytop, 0), y1 = min(ytop + h, 192)  (16-bit)
                push    de
                ld      l, c
                ld      h, 0
                add     hl, de          ; y1
                pop     de
                bit     7, h
                ret     nz              ; entirely above the screen
                ld      a, h
                or      a
                jr      nz, dr_y1c      ; >= 256
                ld      a, l
                cp      193
                jr      c, dr_y1
dr_y1c:         ld      a, 192
dr_y1:          ld      c, a            ; y1 clipped
                bit     7, d
                jr      z, dr_y0
                ld      e, 0
                ld      d, 0
dr_y0:          ld      a, d
                or      a
                ret     nz              ; ytop >= 256: below the screen
                ld      a, e
                cp      192
                ret     nc
                ld      hl, DR_Y0
                cp      (hl)
                jr      nc, dr_y2
                ld      (hl), a
dr_y2:          ld      a, (DR_Y1)
                cp      c
                ret     nc
                ld      a, c
                ld      (DR_Y1), a
                ret
; dr_run: re-lay the dirty rect in chunks of CW x CH through run_rect
dr_run:         ld      a, (RR_SHONLY)  ; background only: the caller's object pass redraws the rect on screen
                or      a
                jr      z, dr_run0
                ld      a, (DR_Y1)      ; (nothing to do for an empty rect)
                ld      hl, DR_Y0
                cp      (hl)
                jr      z, dr_run0
                jr      c, dr_run0
                ld      hl, (RR_HOOK)
                ld      de, dr_run0
                push    de
                jp      (hl)
dr_run0:        ld      a, (DR_X0)
                sub     6
                jp      p, dr_c0
                xor     a
dr_c0:          rrca
                rrca
                and     63
                ld      (RR_C0), a
                ld      a, (DR_X1)
                dec     a
                rrca
                rrca
                and     63
                ld      (RR_C1), a
                ld      a, (DR_Y0)
dr_yl:          ld      hl, DR_Y1
                cp      (hl)
                ret     nc
                ld      (CRY), a
                ld      c, a
                ld      a, (hl)
                sub     c
                cp      CH
                jr      c, dr_h
                ld      a, CH
dr_h:           ld      (CRH), a
                ld      a, (DR_X0)
dr_xl:          ld      hl, DR_X1
                cp      (hl)
                jr      nc, dr_ynext
                ld      (CRX), a
                ld      c, a
                ld      a, (hl)
                sub     c
                cp      CW
                jr      c, dr_w
                ld      a, CW
dr_w:           ld      (CRW), a
                call    run_rect
                ld      a, (CRX)
                add     a, CW
                jp      dr_xl
dr_ynext:       ld      a, (CRY)
                add     a, CH
                jp      dr_yl

; tile_redraw: A = tag of a tile whose modifier changed. Regenerates the ops of the tile, of its right
; neighbour and of the tile above-right (they draw from this tile's state), then re-lays the dirty rect.
tile_redraw:    ld      (tr_t), a
                call    dr_reset
                call    load_room_links ; room state shared by the regenerated tiles
                call    load_leftroom
                ld      a, (tr_t)
                call    tile_regen
                ld      a, (tr_t)
                cp      30
                jp      nc, dr_run      ; above-row tile: nothing else depends on it here
                call    tag_col
                cp      9
                jp      z, dr_run
                ld      a, (tr_t)
                inc     a
                call    tile_regen      ; right neighbour
                ld      a, (tr_t)
                cp      10
                jr      c, trd_top
                sub     9               ; (row-1, col+1)
                call    tile_regen
                jp      dr_run
trd_top:        call    tag_col
                add     a, 31           ; above row, col+1
                call    tile_regen
                jp      dr_run
; op_patch: animated pieces that are a single op whose image changes with the frame (torch flames, potion
; bubbles): in the slice of tile OP_TAG of list OP_LIST (0 back, 2 fore) the first record with chtab OP_CH and
; OP_LO <= id <= OP_HI gets id OP_NEW (w/h from the directory); the old and new rects are re-laid.
; Out: A = 1 patched, 0 no such op (nothing drawn; the caller may fall back to tile_redraw).
op_patch:       call    dr_reset
                ld      a, (OP_LIST)
                ld      c, a
                add     a, a
                add     a, a
                add     a, c
                add     a, a
                add     a, a
                add     a, a            ; list*40
                ld      hl, SL_CNT
                add     a, l
                ld      l, a
                ld      a, (OP_TAG)
                call    tab_get
                or      a
                ret     z
                ld      b, a
                ld      a, (OP_LIST)
                ld      c, a
                add     a, a
                add     a, a
                add     a, c
                add     a, a
                add     a, a
                add     a, a
                ld      hl, SL_START
                add     a, l
                ld      l, a
                ld      a, (OP_TAG)
                call    tab_get
                ld      l, a
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      a, (OP_LIST)
                add     a, a
                ld      de, opl_base
                add     a, e
                ld      e, a
                ld      a, (de)
                inc     de
                ld      (op_tmp), a
                ld      a, (de)
                ld      d, a
                ld      a, (op_tmp)
                ld      e, a
                add     hl, de          ; HL = first record of the slice
op_scan:        inc     hl
                ld      a, (OP_CH)
                cp      (hl)
                jp      nz, op_next
                inc     hl
                ld      a, (hl)         ; id
                dec     hl
                ld      c, a
                ld      a, (OP_LO)
                cp      c
                jp      z, op_found
                jp      nc, op_next
                ld      a, (OP_HI)
                cp      c
                jp      nc, op_found
op_next:        dec     hl
                ld      de, 8
                add     hl, de
                djnz    op_scan
                xor     a
                ret
op_found:       dec     hl              ; HL = record
                ld      a, (OP_ONLY)            ; find only: HL = the record, A != 0
                or      a
                ret     nz
                ld      a, (OP_LIST)            ; a fore op changes (a potion bubble): images cached with the
                cp      2                       ; fore pieces in them are stale
                jp      nz, opf1
                ld      a, (fore_gen)
                inc     a
                ld      (fore_gen), a
opf1:
                push    hl
                call    dr_add          ; old rect
                pop     hl
                push    hl
                inc     hl
                inc     hl
                ld      a, (OP_NEW)
                ld      (hl), a         ; new id
                ld      c, a
                ld      a, (OP_CH)
                call    dir_entry
                inc     hl
                inc     hl
                inc     hl
                ld      a, (hl)         ; w
                inc     hl
                ld      c, (hl)         ; h
                pop     hl
                push    hl
                ld      de, 6
                add     hl, de
                ld      (hl), a
                inc     hl
                ld      (hl), c
                pop     hl
                push    hl                      ; the slice's extent grows with the new image
                ld      de, 4
                add     hl, de
                ld      c, (hl)
                inc     hl
                ld      b, (hl)
                inc     hl
                inc     hl
                ld      l, (hl)
                ld      h, 0
                add     hl, bc
                ld      a, (OP_LIST)
                ld      e, a
                add     a, a
                add     a, a
                add     a, e
                add     a, a
                add     a, a
                add     a, a                    ; list * 40
                ld      e, a
                ld      a, (OP_TAG)
                add     a, e
                ld      e, a
                ld      d, 0
                call    yr_merge
                pop     hl
                call    dr_add          ; new rect
                call    dr_run
                ld      a, 1
                ret
op_tmp:         db      0

; torch_redraw: A = tag of the tile whose draw emits the flame (the tile right of the torch, or column 0 for a
; torch in the left room's column 9), C = new flame frame (0..8). Falls back to tile_redraw of that tile.
torch_redraw:   ld      (OP_TAG), a
                ld      a, c
                inc     a
                ld      (OP_NEW), a     ; flame image id = frame + 1
                xor     a
                ld      (OP_LIST), a
                ld      a, CH_OBJ
                ld      (OP_CH), a
                ld      a, 1
                ld      (OP_LO), a
                ld      a, 9
                ld      (OP_HI), a
                call    op_patch
                or      a
                ret     nz
                ld      a, (OP_TAG)
                jp      tile_redraw

; bubble_redraw: A = tag of the potion tile, C = bubble frame (1..7); patches the fore bubble op
bubble_redraw:  ld      (OP_TAG), a
                ld      a, c
                ld      hl, bubble_var
                call    tab_get
                ld      (OP_NEW), a
                ld      a, 2
                ld      (OP_LIST), a
                ld      a, CH_OBJ
                ld      (OP_CH), a
                ld      a, (bubble_var + 1)
                ld      (OP_LO), a
                ld      a, (bubble_var + 7)
                ld      (OP_HI), a
                call    op_patch
                or      a
                ret     nz
                ld      a, (OP_TAG)
                jp      tile_redraw

tag_col:        ld      a, (tr_t)
tc_l:           cp      10
                ret     c
                sub     10
                jp      tc_l
tr_t:           db      0

; ---------------------------------------------------------------- execute the op lists into one compose rect
; In: CRX, CRY, CRW (<= CW), CRH (<= CH) set by the caller. Fill black, lay every op of the three lists that
; touches the rect (back, mid, fore in that order), write the shadow room, blit to VRAM.
; Occlusion: a first pass over the back and mid ops only counts the ones that touch the rect and notes the
; last opaque one (copy mode, no partial edge) that covers the whole rect; the black fill and every op
; before it are then skipped (a torch flame covers its rect: the wall behind it is not laid at all).
run_rect:       ld      hl, COMPOSE_A
                ld      a, (RR_SHONLY)          ; background only: into SPRBUF_B, kept for the object pass
                or      a
                jp      z, rr_ca
                ld      hl, SPRBUF_B
rr_ca:          ld      (V_COMPOSE), hl
                call    rect_bounds
                ld      a, 1
                ld      (RR_MODE), a
                xor     a
                ld      (rr_cnt), a
                ld      (rr_last), a
                call    rr_table        ; back (scan)
                ld      a, 1
                call    rr_table        ; mid (scan)
                xor     a
                ld      (RR_MODE), a
                call    rc_hook         ; (M4: lays the recorded ops itself: carry)
                jp      c, rr_sw
                ld      a, (rr_last)
                or      a
                jp      z, rr_fill
                dec     a
                ld      (rr_skip), a    ; ops before the cover
                jp      z, rr_lay
                ld      a, 2
                ld      (RR_MODE), a
                jp      rr_lay
rr_fill:        ld      a, (CRX)
                ld      b, a
                ld      a, (CRY)
                ld      c, a
                ld      a, (CRW)
                ld      d, a
                ld      a, (CRH)
                ld      e, a
                call    fill_black
rr_lay:         xor     a
                call    rr_table        ; back
                ld      a, 1
                call    rr_table        ; mid
                xor     a
                ld      (RR_MODE), a
rr_sw:          call    shadow_write    ; the shadow room holds the background without the fore pieces
                ld      a, (RR_SHONLY)
                or      a
                jp      z, rr_fore
                ld      hl, (CRX)               ; the kept picture: SPRBUF_B holds this rect's background
                ld      (rr_kr), hl
                ld      hl, (CRW)
                ld      (rr_kr + 2), hl
                ld      a, 1
                ld      (rr_kv), a
                ret
rr_fore:
                ld      a, 2
                call    rr_table        ; fore
                jp      blit
; lay_fore_rect: lay the fore pieces that touch the compose rect (CRX/CRY/CRW/CRH, V_COMPOSE) over whatever
; the compose buffer holds (a character drawn over the restored shadow); candidate tile columns from the rect
lay_fore_rect:  call    rect_bounds
                ld      a, (rr_x1)
                dec     a
                rrca
                rrca
                and     63
                ld      (RR_C1), a
                ld      a, (CRX)
                sub     6
                jp      p, lfr1
                xor     a
lfr1:           rrca
                rrca
                and     63
                ld      (RR_C0), a
                ld      a, 2
                ; fall through
; rr_table: A = table (0 back, 1 mid, 2 fore): lay its candidate ops into the compose rect (rect_bounds set).
; Lay order: tile rows 2, 1, 0, the above row; in each columns RR_C0..RR_C1; a slice's ops in list order. The
; cells of a row are walked by pointer in SL_CNT (an empty cell: ~35 T); the slice tables share their low byte
; tbl*40 + tag: SL_START (L - 0x80) and SL_CNT (L) on one page, SL_Y0 / SL_Y1 (+120) on another.
                if (SL_CNT & 0xff) != 0x80 or SL_START != SL_CNT - 0x80 or (SL_Y0 & 0xff) != 0 or SL_Y1 != SL_Y0 + 120
                .error rr_table: the slice tables' layout
                endif
rr_table:       ld      (RUN_TBL), a
                ld      a, (bkt_on)
                or      a
                jp      nz, rr_bkt_ent          ; (src/m3/roomfull.asm rr_bkt, through the program's rr_bkt_ent)
rr_tbl:         ld      a, (RUN_TBL)
                add     a, a
                ld      hl, opl_base
                add     a, l
                ld      l, a
                ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a
                ld      (OPL_END), hl   ; list base
                ld      a, (RUN_TBL)    ; RR_CB0 = SL_CNT's low byte at tbl*40 + RR_C0
                ld      c, a
                add     a, a
                add     a, a
                add     a, c
                add     a, a
                add     a, a
                add     a, a            ; *40
                ld      hl, RR_C0
                add     a, (hl)
                add     a, SL_CNT & 0xff
                ld      (RR_CB0), a
                ld      a, (RR_C1)
                sub     (hl)
                inc     a
                ld      (RR_NC), a      ; columns a row
                ld      hl, rr_rows
rr_row:         ld      (RR_RP), hl
                ld      a, (RR_CB0)
                add     a, (hl)
                ld      l, a
                ld      h, SL_CNT >> 8
                ld      a, (RR_NC)
                ld      b, a
rr_cy:          ld      a, (rr_y1)
                ld      c, a            ; C = CRY + CRH
rr_cell:        ld      a, (hl)         ; the cell's op count
                or      a
                jr      nz, rr_hit
rr_cnext:       inc     l
                djnz    rr_cell
rr_rnext:       ld      hl, (RR_RP)
                inc     hl
                ld      a, l
                cp      (rr_rows + 4) & 0xff
                jp      nz, rr_row
                ret
rr_hit:         ld      a, l                    ; the slice's rows miss the rect: skip it whole
                and     0x7f
                ld      e, a
                ld      d, SL_Y0 >> 8
                ld      a, (de)                 ; y0
                cp      c
                jr      nc, rr_cnext            ; y0 >= CRY + CRH
                ld      a, e
                add     a, 120
                ld      e, a
                ld      a, (de)                 ; y1
                ld      e, a
                ld      a, (rr_y0)
                cp      e
                jr      nc, rr_cnext            ; y1 <= CRY
                ld      (RR_CP), hl
                ld      a, b
                ld      (RR_CB), a
                ld      a, (hl)
                ld      (RR_N), a
                res     7, l
                ld      l, (hl)                 ; SL_START
                ld      h, 0
                add     hl, hl
                add     hl, hl
                add     hl, hl
                ld      de, (OPL_END)
                add     hl, de
                ld      (OPL_PTR), hl   ; first record of the slice
rr_op:          ld      hl, (OPL_PTR)
                ld      de, 8
                add     hl, de
                ld      (OPL_PTR), hl   ; next record
                call    rec_lay
rr_next:        ld      hl, RR_N
                dec     (hl)
                jp      nz, rr_op
                ld      hl, (RR_CP)
                ld      a, (RR_CB)
                ld      b, a
                inc     l
                dec     b
                jp      nz, rr_cy
                jp      rr_rnext
rr_rows:        db      20, 10, 0, 30   ; the rows' first tags in lay order
rr_x1:          db      0
rr_y0:          dw      0
rr_y1:          dw      0

; rec_lay: lay the record that ends at OPL_PTR into the compose rect if it touches it (rr_x1, rr_y0, rr_y1 set)
rec_lay:        ld      de, -5
                add     hl, de          ; HL = &xb
                ; quick reject on columns: xb + w <= CRX  or  xb >= CRX + CRW   (small signed values)
                ld      a, (hl)         ; xb
                ld      b, a
                inc     hl
                inc     hl
                inc     hl
                add     a, (hl)         ; xb + w
                ld      c, a
                ld      a, (CRX)
                sub     c
                ret     p        ; CRX - (xb+w) >= 0: left of the rect
                ld      a, (rr_x1)
                sub     b
                ret     m        ; xb > CRX+CRW... (xb - x1 >= 0 <=> x1 - xb <= 0)
                ret     z
                ; rows: ytop + h <= CRY  or  ytop >= CRY + CRH   (16-bit signed)
                inc     hl
                ld      e, (hl)         ; h
                ld      d, 0
                dec     hl
                dec     hl
                ld      a, (hl)         ; ytop hi
                dec     hl
                ld      l, (hl)
                ld      h, a            ; HL = ytop
                push    hl
                add     hl, de          ; ytop + h
                ld      de, (rr_y0)
                or      a
                sbc     hl, de          ; (ytop+h) - CRY <= 0 ?
                pop     de              ; DE = ytop
                ret     m
                ld      a, h
                or      l
                ret     z
                ld      hl, (rr_y1)
                or      a
                sbc     hl, de          ; (CRY+CRH) - ytop <= 0 ?
                ret     m
                ld      a, h
                or      l
                ret     z
                ld      a, (RR_MODE)
                or      a
                jp      nz, rl_mode
                ; lay it: record fields
rl_lay:         ld      hl, (OPL_PTR)
                ld      de, -8
                add     hl, de
                ld      a, (hl)
                rrca
                rrca
                and     3
                ld      (A_TMP), a      ; blit code = lay mode
                ld      a, (hl)
                rrca
                rrca
                rrca
                rrca
                and     15
                ld      (V_MONO), a
                inc     hl
                ld      a, (hl)         ; chtab
                inc     hl
                ld      c, (hl)         ; id
                inc     hl
                ld      b, (hl)         ; byte column (signed)
                inc     hl
                ld      e, (hl)
                inc     hl
                ld      d, (hl)         ; ytop
                call    dir_entry
                push    hl
                pop     ix
                ld      a, (A_TMP)
                call    lay_piece16             ; (a call: the profiler sees the piece apart from the scan)
                ret

; rec_lay outside the normal mode (run_rect): 1 = scan for the last cover, 2 = skip rr_skip ops
rl_mode:        cp      2
                jp      nz, rl_scan
                ld      hl, rr_skip
                dec     (hl)
                ret     nz
                xor     a               ; the cover itself is laid next
                ld      (RR_MODE), a
                ret
rl_scan:        ld      hl, rr_cnt
                inc     (hl)
                ld      a, (hl)                 ; record it: RR_PTRS[rr_cnt - 1] = the record's end
                cp      RC_MAX + 1
                jp      nc, rls0
                add     a, a
                ld      l, a
                ld      h, RR_PTRS >> 8
                dec     l
                ld      de, (OPL_PTR)
                ld      (hl), d
                dec     l
                ld      (hl), e
rls0:
                ld      hl, (OPL_PTR)
                ld      de, -8
                add     hl, de
                ld      a, (hl)
                and     0x0c            ; copy mode only
                ret     nz
                push    hl
                pop     ix              ; IX = record
                ld      a, (ix+3)       ; xb <= CRX (signed)
                bit     7, a
                jp      nz, rls1
                ld      b, a
                ld      a, (CRX)
                cp      b
                ret     c
rls1:           ld      a, (ix+3)       ; xb + w >= CRX + CRW
                add     a, (ix+6)
                ret     m
                ld      b, a
                ld      a, (rr_x1)
                cp      b
                jp      z, rls2
                ret     nc
rls2:           ld      l, (ix+4)       ; ytop <= CRY
                ld      h, (ix+5)
                ld      de, (rr_y0)
                or      a
                sbc     hl, de
                jp      z, rls3
                ret     p
rls3:           ld      l, (ix+4)       ; ytop + h >= CRY + CRH
                ld      h, (ix+5)
                ld      e, (ix+7)
                ld      d, 0
                add     hl, de
                ld      de, (rr_y1)
                or      a
                sbc     hl, de
                ret     m
                ld      a, (ix+1)       ; no partial edge columns
                ld      c, (ix+2)
                call    dir_entry
                inc     hl
                inc     hl
                inc     hl
                inc     hl
                inc     hl
                ld      a, (hl)
                and     2
                ret     nz
                ld      a, (rr_cnt)
                ld      (rr_last), a
                ld      hl, (OPL_PTR)
                ld      (rr_lastrec), hl
                ret
rc_hook:        jp      rc_none                 ; M4 points it at rc_run
rc_none:        or      a
                ret
rr_kr:          ds      4               ; the last background-only rect (in SPRBUF_B) and whether it is unused
rr_kv:          db      0
ops_gen:        db      0               ; bumped whenever op records may move (tile_regen, room_ops)
fore_gen:       db      0               ; bumped when a fore op is patched (op_patch)
rr_lastrec:     dw      0               ; the cover's record (its end)
OP_ONLY:        db      0
rr_cnt:         db      0
rr_last:        db      0
rr_skip:        db      0
RR_MODE:        db      0

; lay_list: HL = op list, B = record count: lay every record that touches the compose rect, in list order
lay_list:       ld      a, b
                or      a
                ret     z
                push    bc
                push    hl
                call    rect_bounds
                pop     hl
                pop     bc
ll_rec:         ld      de, 8
                add     hl, de
                ld      (OPL_PTR), hl
                push    bc
                call    rec_lay
                pop     bc
                ld      hl, (OPL_PTR)
                djnz    ll_rec
                ret
; rect_bounds: rr_x1 = CRX + CRW, rr_y0 = CRY, rr_y1 = CRY + CRH
rect_bounds:    ld      a, (CRX)
                ld      hl, CRW
                add     a, (hl)
                ld      (rr_x1), a
                ld      a, (CRY)
                ld      l, a
                ld      h, 0
                ld      (rr_y0), hl
                ld      a, (CRH)
                ld      e, a
                ld      d, 0
                add     hl, de
                ld      (rr_y1), hl
                ret

bkt_on:         db      0               ; nonzero while run_ops (roomfull.asm) draws from the per-cell buckets
; (build/assets/tables.inc is included by the program in its second block at 0xC000)
