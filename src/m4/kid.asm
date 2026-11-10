; ---------------------------------------------------------------- the prince (M4 first cut)
; Z80 port of the SDLPoP kid logic as reproduced by tools/kidsim.py (seg002/004/005/006): control, sequence
; interpreter, falling, collisions with walls/gates, ledge grabbing and climbing, room changes (traps, buttons,
; potions, hit points: objects.asm; the guard and sword fighting: guard.asm; no sound). Coordinates are the DOS logical ones: x 58..257 across
; the room (14 units per tile), y = row of the feet (y_land), rows 0..2, columns 0..9 (outside = other rooms).
;
; Conventions: KV holds Char, the character being played: the kid's routines serve the guard too (src/m4/guard.asm
; keeps the Kid and Guard records, loads one into KV and saves it back, as SDLPoP's loadkid/saveshad; between
; ticks KV holds the Kid). Small signed quantities are 8-bit two's complement; x geometry
; (obj_x, char_x_*, wall positions) is 16-bit signed. Tile reads go through k_get_tile (A = room, C = column,
; B = row, both signed; wraps into the linked rooms like SDLPoP's find_room_of_tile).

; ---- the character
KV              equ     0x0a00
K_FRAME         equ     KV + 0
K_X             equ     KV + 1
K_Y             equ     KV + 2
K_DIR           equ     KV + 3          ; 0 right, 0xff left
K_COL           equ     KV + 4          ; signed
K_ROW           equ     KV + 5          ; signed
K_ACTION        equ     KV + 6
K_FALLX         equ     KV + 7
K_FALLY         equ     KV + 8
K_ROOM          equ     KV + 9
K_REPEAT        equ     KV + 10
K_CHARID        equ     KV + 11
K_SWORD         equ     KV + 12
K_ALIVE         equ     KV + 13         ; 0xff alive, 0 dead
K_SEQ           equ     KV + 14         ; 16-bit offset into seqtbl
; ---- controls
C_X             equ     KV + 16         ; -1 forward/left, 0, 1 (control_x: screen left/right before user_control flips it)
C_Y             equ     KV + 17         ; -1 up, 1 down
C_SHIFT         equ     KV + 18         ; -1 held, 0 released
C_FWD           equ     KV + 19         ; control_forward/backward/up/down/shift2: -1 held, 0 released, 1 ignore
C_BACK          equ     KV + 20
C_UP            equ     KV + 21
C_DOWN          equ     KV + 22
C_SHIFT2        equ     KV + 23
CTRL1           equ     KV + 24         ; 5 bytes saved across ticks
GRAB_TIMER      equ     KV + 29
; ---- geometry of the current frame
CF_IMG          equ     KV + 32         ; cur_frame: image, sword, dx, dy, flags
CF_SWORD        equ     KV + 33
CF_DX           equ     KV + 34
CF_DY           equ     KV + 35
CF_FLAGS        equ     KV + 36
OBJ_X           equ     KV + 38         ; 16-bit signed
OBJ_Y           equ     KV + 40         ; 16-bit
OBJ_XL          equ     KV + 42
OBJ_ID          equ     KV + 43
CHAR_WH         equ     KV + 44         ; char_width_half
CHAR_H          equ     KV + 45
CX_LEFT         equ     KV + 46         ; 16-bit signed: char_x_left
CX_RIGHT        equ     KV + 48
CX_LCOLL        equ     KV + 50
CX_RCOLL        equ     KV + 52
CHAR_TOP_Y      equ     KV + 54         ; 16-bit
CHAR_TOP_ROW    equ     KV + 56
CHAR_BOT_ROW    equ     KV + 57
CHAR_COL_L      equ     KV + 58
CHAR_COL_R      equ     KV + 59
; ---- tile access results
CURR_ROOM       equ     KV + 60
TILE_COL        equ     KV + 61
TILE_ROW        equ     KV + 62
CURR_TILEPOS    equ     KV + 63
CURR_TILE2      equ     KV + 64
INFRONTX        equ     KV + 65
THROUGH_TILE    equ     KV + 66
EDGE_TYPE       equ     KV + 67
COLL_TLX        equ     KV + 68         ; 16-bit coll_tile_left_xpos
; ---- collisions
COLL_ROW        equ     KV + 70
PREV_COLL_ROW   equ     KV + 71
LEFT_CHK        equ     KV + 72
RIGHT_CHK       equ     KV + 73
BUMP_L          equ     KV + 74         ; bump_col_left_of_wall
BUMP_R          equ     KV + 75
FALL_FRAME      equ     KV + 76
EXIT_TIMER      equ     KV + 77
NEXT_ROOM       equ     KV + 78
DRAWN_ROOM      equ     KV + 79
K_TMP           equ     KV + 80         ; scratch bytes 80..95
K_TMP2          equ     KV + 81
K_TMP3          equ     KV + 82
K_TMP4          equ     KV + 83
K_TMPW          equ     KV + 84         ; 16-bit scratch
K_TMPW2         equ     KV + 86
K_TMPW3         equ     KV + 88
K_TICK          equ     KV + 90         ; 16-bit tick counter
GU_DIST         equ     KV + 92         ; grab_up_with_floor_behind: distance, edge distance (survive get_edge_distance)
GU_EDGE         equ     KV + 93
PREV_ROOMS      equ     KV + 96         ; collision rows: 10 bytes each (0xff = none) + 10 flag bytes
PREV_FLAGS      equ     KV + 106
CURR_ROOMS      equ     KV + 116
CURR_FLAGS      equ     KV + 126
BELOW_ROOMS     equ     KV + 136
BELOW_FLAGS     equ     KV + 146
ABOVE_ROOMS     equ     KV + 156
ABOVE_FLAGS     equ     KV + 166
; actions / directions / tiles / sequences
T_DOORTOP_FLOOR equ     7
T_MIRROR        equ     13
T_CLOSER        equ     6
AC_STAND        equ     0
AC_RUN_JUMP     equ     1
AC_HANG_CLIMB   equ     2
AC_MIDAIR       equ     3
AC_FREEFALL     equ     4
AC_BUMPED       equ     5
AC_HANG_STRAIGHT equ    6
AC_TURN         equ     7
D_RIGHT         equ     0
D_LEFT          equ     0xff
C_HELD          equ     0xff
C_RELEASED      equ     0
C_IGNORE        equ     1
X_FORWARD       equ     0xff
X_BACKWARD      equ     1
Y_UP            equ     0xff
Y_DOWN          equ     1
F_WEIGHT        equ     0x1f
F_THIN          equ     0x20
F_NEEDS_FLOOR   equ     0x40
EDGE_CLOSER     equ     0
EDGE_WALL       equ     1
EDGE_FLOOR      equ     2
SQ_START_RUN    equ     1
SQ_STANDING_JUMP equ    3
SQ_RUN_JUMP     equ     4
SQ_TURN         equ     5
SQ_RUN_TURN     equ     6
SQ_FALL         equ     7
SQ_GRAB_STRAIGHT equ    8
SQ_CLIMB_UP     equ     10
SQ_RELEASE_LAND equ     11
SQ_STOP_RUN     equ     13
SQ_JUMP_CEILING equ     14
SQ_GRAB_MIDAIR  equ     15
SQ_JUMP_GRAB    equ     16
SQ_SOFT_LAND    equ     17
SQ_FALL_SJ      equ     18
SQ_FALL2        equ     19
SQ_MEDIUM_LAND  equ     20
SQ_FALL_RJ      equ     21
SQ_CRUSHED      equ     22
SQ_RELEASE_FALL equ     23
SQ_GRAB_FORWARD equ     24
SQ_HANG_WALL    equ     25
SQ_CROUCH_RUN   equ     26
SQ_JUMP_NOTHING equ     28
SQ_SAFE_STEP11  equ     39
SQ_RUN_AFTER_TURN equ   43
SQ_STEP_EDGE    equ     44
SQ_BUMPFALL     equ     45
SQ_HARDBUMP     equ     46
SQ_BUMP         equ     47
SQ_STAND_UP     equ     49
SQ_CROUCH       equ     50
SQ_CLIMB_DOWN   equ     68
SQ_DYING        equ     71
SQ_CLIMB_GATE   equ     73
SQ_CROUCH_HOP   equ     79
SQ_FALL_WALL    equ     104
SEQ_DX          equ     0xfb
SEQ_DY          equ     0xfa
SEQ_FLIP        equ     0xfe
SEQ_JMP_FEATHER equ     0xf7
SEQ_JMP         equ     0xff
SEQ_UP          equ     0xfd
SEQ_DOWN        equ     0xfc
SEQ_ACTION      equ     0xf9
SEQ_SET_FALL    equ     0xf8
SEQ_KNOCK_UP    equ     0xf5
SEQ_KNOCK_DOWN  equ     0xf4
SEQ_SOUND       equ     0xf2
SEQ_END_LEVEL   equ     0xf1
SEQ_GET_ITEM    equ     0xf3
SEQ_DIE         equ     0xf6
TILE_SIZEX      equ     14
TILE_MIDX       equ     7
TILE_RIGHTX     equ     13
FIRST_COL       equ     5

; ================================================================ helpers
; signed 8-bit compare helpers: A vs B -> flags as if signed (values |v| < 128)
; ks_lt: carry set if A < B (signed)
ks_lt:          sub     b
                ret     po              ; no overflow: sign = result
                xor     0x80
                ret
; k_neg8: A = -A
; k_sext: HL = sign-extended A
k_sext:         ld      l, a
                rla
                sbc     a, a
                ld      h, a
                ret
; k_tbl: A = table[A] (HL = table, A index 0..255), page safe
k_tbl:          add     a, l
                ld      l, a
                jr      nc, ktb1
                inc     h
ktb1:           ld      a, (hl)
                ret
; k_is_floor: A = tile -> Z set if NOT floor (A = 1 floor / 0 not)
k_is_floor:  ld      hl, tile_floor_tbl
                and     0x1f
                call    k_tbl
                or      a
                ret
; wall_type: A = tile -> A = wall type (flags: Z if 0)
wall_type:      ld      hl, wall_type_tbl
                and     0x1f
                call    k_tbl
                or      a
                ret
; dir_front: A = +1 facing right, -1 facing left
dir_front:      ld      a, (K_DIR)
                or      a
                ld      a, 1
                ret     z
                ld      a, -1
                ret

; ================================================================ tiles
; k_get_tile: A = room, C = column (signed), B = row (signed). Out: A = CURR_TILE2 (also CURR_ROOM, TILE_COL,
; TILE_ROW, CURR_TILEPOS). Room 0 reads as wall.
; M8a part 23: the column and the row inside the room (0..9, 0..2) take a short path to the same stores, registers
; and flags (row * 10 + column without tbl_line; room 0 still a wall)
k_get_tile:     ld      (CURR_ROOM), a
                ld      a, b
                ld      (TILE_ROW), a
                ld      a, c
                ld      (TILE_COL), a
                cp      10
                jp      nc, kgt_loop
                ld      a, b
                cp      3
                jp      nc, kgt_loop
                ld      a, (CURR_ROOM)
                or      a
                jp      z, kgt_wall
                ld      a, b
                add     a, a
                add     a, a
                add     a, b
                add     a, a
                add     a, c
                ld      (CURR_TILEPOS), a
                ld      a, (CURR_ROOM)
                jp      kgt_rd
kgt_loop:       ld      a, (TILE_ROW)
                bit     7, a
                jp      z, kgt_c
                add     a, 3
                ld      (TILE_ROW), a
                ld      a, (CURR_ROOM)
                or      a
                jp      z, kgt_loop
                call    links_of
                ld      a, d            ; up
                ld      (CURR_ROOM), a
                jp      kgt_loop
kgt_c:          ld      a, (TILE_COL)
                bit     7, a
                jp      z, kgt_c2
                add     a, 10
                ld      (TILE_COL), a
                ld      a, (CURR_ROOM)
                or      a
                jp      z, kgt_loop
                call    links_of
                ld      a, c            ; left
                ld      (CURR_ROOM), a
                jp      kgt_loop
kgt_c2:         cp      10
                jp      c, kgt_r
                sub     10
                ld      (TILE_COL), a
                ld      a, (CURR_ROOM)
                or      a
                jp      z, kgt_loop
                call    links_of
                ld      a, b            ; right
                ld      (CURR_ROOM), a
                jp      kgt_loop
kgt_r:          ld      a, (TILE_ROW)
                cp      3
                jp      c, kgt_done
                sub     3
                ld      (TILE_ROW), a
                ld      a, (CURR_ROOM)
                or      a
                jp      z, kgt_loop
                call    links_of
                ld      a, e            ; down
                ld      (CURR_ROOM), a
                jp      kgt_loop
kgt_done:       ld      a, (CURR_ROOM)
                or      a
                jp      z, kgt_wall
                ld      a, (TILE_ROW)
                ld      hl, tbl_line
                call    k_tbl
                ld      hl, TILE_COL
                add     a, (hl)
                ld      (CURR_TILEPOS), a
                ld      a, (CURR_ROOM)
kgt_rd:         call    tile_base       ; HL = &fg[(room-1)*30]
                ld      a, (CURR_TILEPOS)
                call    k_tbl
                and     0x1f
                ld      (CURR_TILE2), a
                ret
kgt_wall:       xor     a
                ld      (CURR_TILEPOS), a
                ld      a, T_WALL
                ld      (CURR_TILE2), a
                ret
; k_modif: A = modifier of the tile last read (0 in room 0)
k_modif:        ld      a, (CURR_ROOM)
                or      a
                ret     z
                call    tile_base       ; DE = &bg[...]
                ex      de, hl
                ld      a, (CURR_TILEPOS)
                jp      k_tbl
; the usual neighbours (all return A = tile)
get_tile_at_char:
                ld      a, (K_COL)
                ld      c, a
                ld      a, (K_ROW)
                ld      b, a
                ld      a, (K_ROOM)
                jp      k_get_tile
get_tile_infrontof_char:
                call    dir_front
                ld      hl, K_COL
                add     a, (hl)
                ld      (INFRONTX), a
                ld      c, a
                ld      a, (K_ROW)
                ld      b, a
                ld      a, (K_ROOM)
                jp      k_get_tile
get_tile_behind_char:
                call    dir_front
                neg
                ld      hl, K_COL
                add     a, (hl)
                ld      c, a
                ld      a, (K_ROW)
                ld      b, a
                ld      a, (K_ROOM)
                jp      k_get_tile
get_tile_above_char:
                ld      a, (K_COL)
                ld      c, a
                ld      a, (K_ROW)
                dec     a
                ld      b, a
                ld      a, (K_ROOM)
                jp      k_get_tile
get_tile_behind_above_char:
                call    dir_front
                neg
                ld      hl, K_COL
                add     a, (hl)
                ld      c, a
                ld      a, (K_ROW)
                dec     a
                ld      b, a
                ld      a, (K_ROOM)
                jp      k_get_tile
get_tile_front_above_char:
                call    dir_front
                ld      hl, K_COL
                add     a, (hl)
                ld      (INFRONTX), a
                ld      c, a
                ld      a, (K_ROW)
                dec     a
                ld      b, a
                ld      a, (K_ROOM)
                jp      k_get_tile

; ================================================================ frame / position
; the frame and sequence tables are in the RAM disk (build_assets.py LOGIC_LAYOUT)
RD_LOGIC_PAGE   equ     6
RD_SEQ          equ     0xd000
RD_FRAMES_KID   equ     0xda00
RD_FRAMES_GUARD equ     0xdf00
RD_KID_W        equ     0xe000          ; kid image index -> pixel width
RD_GUARD_WH     equ     0xe100          ; guard set x GUARD_WH_N images -> half width, height
SEQBUF          equ     0x07e0          ; 16 bytes: the sequence window play_seq reads (a step uses at most 15)
load_frame:     ld      a, (K_CHARID)   ; (guard.asm: other characters' frame tables)
                or      a
                jp      nz, load_frame_ch
lf_kid:         ld      a, (K_FRAME)
                ld      l, a
                ld      h, 0
                ld      d, h
                ld      e, l
                add     hl, hl
                add     hl, hl
                add     hl, de          ; *5
                ld      de, RD_FRAMES_KID
                add     hl, de
                ex      de, hl
                ld      a, RD_LOGIC_PAGE
                call    far_seek
                ld      hl, CF_IMG
                ld      bc, 0x0500 | RD_DATA
                inir
                ret
; rd_logic: DE = address in the logic page -> A = byte (the RAM-disk port then reads on from DE + 1)
rd_logic:       ld      a, RD_LOGIC_PAGE
                call    far_seek
                in      a, (RD_DATA)
                ret
; char_dx_forward: A = delta (signed) -> A = Char.x + (dir right ? delta : -delta), byte
char_dx_forward:
                ld      b, a
                ld      a, (K_DIR)
                rla
                ld      a, b
                jr      nc, cdf1
                neg
cdf1:           ld      hl, K_X
                add     a, (hl)
                ret
; back_delta_x: A = delta -> A = (dir left ? delta : -delta)
back_delta_x:   ld      b, a
                ld      a, (K_DIR)
                rla
                ld      a, b
                ret     c
                neg
                ret
; dx_weight: A = char_dx_forward(dx - weight)
dx_weight:      ld      a, (CF_FLAGS)
                and     F_WEIGHT
                ld      b, a
                ld      a, (CF_DX)
                sub     b
                jr      char_dx_forward
; get_tile_div_mod: HL = xpos (16-bit signed) -> A = tile column (signed), OBJ_XL = position in the tile
get_tile_div_mod:
                bit     7, h
                jr      nz, gtdm_neg
                ld      a, h
                or      a
                jr      nz, gtdm_big
                ld      h, tile_mod_tbl / 256 ; (page-aligned, tile_div_tbl the page before: M8a part 23)
                ld      a, (hl)
                ld      (OBJ_XL), a
                dec     h
                ld      a, (hl)
                ret
gtdm_neg:       ld      de, 70          ; xpos + 70 (five tiles), column - 5
                add     hl, de
                call    get_tile_div_mod
                sub     5
                ret
gtdm_big:       ld      de, -70
                add     hl, de
                call    get_tile_div_mod
                add     a, 5
                ret
; get_tile_div_mod_m7: A = xpos (byte, unsigned) -> column of xpos - 7
get_tile_div_mod_m7:
                ld      l, a
                ld      h, 0
                ld      de, -7
                add     hl, de
                jp      get_tile_div_mod
determine_col:  call    dx_weight
                call    get_tile_div_mod_m7
                ld      (K_COL), a
                ret
load_fram_det_col:
                call    load_frame
                jr      determine_col
; y_to_row_mod4: HL = y (16-bit signed) -> A = (y + 60) / 63 % 4 - 1
y_to_row_mod4:  ld      de, 60
                add     hl, de
                ld      b, -1           ; count 63s (y + 60 >= 0 always here)
ytr1:           inc     b
                ld      de, 63
                or      a
                sbc     hl, de
                jr      nc, ytr1
                ld      a, b
                and     3
                dec     a
                ret
; distance_to_edge: A = xpos (byte) -> A = distance to the edge in the facing direction
distance_to_edge:
                call    get_tile_div_mod_m7
                ld      a, (OBJ_XL)
                ld      b, a
                ld      a, (K_DIR)
                or      a
                ld      a, b
                ret     nz
                ld      a, TILE_RIGHTX
                sub     b
                ret
distance_to_edge_weight:
                call    dx_weight
                jr      distance_to_edge

; ================================================================ sequences
; seqtbl_offset_char: A = sequence id
seqtbl_offset_char:
                ld      l, a
                ld      h, 0
                add     hl, hl
                ld      de, seq_offsets
                add     hl, de
                ld      a, (hl)
                ld      (K_SEQ), a
                inc     hl
                ld      a, (hl)
                ld      (K_SEQ+1), a
                ret
play_seq:       ld      hl, (K_SEQ)
ps_fetch:       ld      (ps_base), hl   ; the window at this offset
                ld      de, RD_SEQ
                add     hl, de
                ex      de, hl
                ld      a, RD_LOGIC_PAGE
                call    far_seek
                ld      hl, SEQBUF
                ld      bc, 0x1000 | RD_DATA
                inir
                ld      hl, SEQBUF
ps_loop:        ld      a, (hl)
                inc     hl
                cp      SEQ_DX
                jp      z, ps_dx
                cp      SEQ_DY
                jp      z, ps_dy
                cp      SEQ_FLIP
                jp      z, ps_flip
                cp      SEQ_JMP_FEATHER
                jp      z, ps_jmpf
                cp      SEQ_JMP
                jp      z, ps_jmp
                cp      SEQ_UP
                jp      z, ps_up
                cp      SEQ_DOWN
                jp      z, ps_down
                cp      SEQ_ACTION
                jp      z, ps_action
                cp      SEQ_SET_FALL
                jp      z, ps_setfall
                cp      SEQ_KNOCK_UP
                jp      z, ps_knock_up
                cp      SEQ_KNOCK_DOWN
                jp      z, ps_knock_down
                cp      SEQ_SOUND
                jp      z, ps_skip1
                cp      SEQ_END_LEVEL
                jp      z, ps_endlevel
                cp      SEQ_GET_ITEM
                jp      z, ps_getitem
                cp      SEQ_DIE
                jp      z, ps_loop
                ld      (K_FRAME), a    ; a frame: done
                ld      de, SEQBUF
                or      a
                sbc     hl, de
                ld      de, (ps_base)
                add     hl, de
                ld      (K_SEQ), hl
                ret
ps_base:        dw      0
ps_dx:          ld      a, (hl)
                inc     hl
                push    hl
                call    char_dx_forward
                ld      (K_X), a
                pop     hl
                jp      ps_loop
ps_dy:          ld      a, (hl)
                inc     hl
                ld      b, a
                ld      a, (K_Y)
                add     a, b
                ld      (K_Y), a
                jp      ps_loop
ps_flip:        ld      a, (K_DIR)
                cpl
                ld      (K_DIR), a
                jp      ps_loop
ps_jmpf:        ld      a, (FEATHER)    ; a jump in feather fall only
                or      a
                jp      nz, ps_jmp
                inc     hl
                inc     hl
                jp      ps_loop
ps_jmp:         ld      a, (hl)
                inc     hl
                ld      h, (hl)
                ld      l, a
                jp      ps_fetch
ps_up:          ld      a, (K_ROW)
                dec     a
                jp      ps_row
ps_down:        ld      a, (K_ROW)
                inc     a
ps_row:         ld      (K_ROW), a
                push    hl
                call    start_chompers
                pop     hl
                jp      ps_loop
ps_action:      ld      a, (hl)
                inc     hl
                ld      (K_ACTION), a
                jp      ps_loop
ps_setfall:     ld      a, (hl)
                inc     hl
                ld      (K_FALLX), a
                ld      a, (hl)
                inc     hl
                ld      (K_FALLY), a
                jp      ps_loop
ps_skip1:       ld      a, (hl)         ; a sound (sound.asm seq_sound: silent, footstep, bump let the guard notice)
                inc     hl
                call    seq_sound
                jp      ps_loop
ps_knock_up:    ld      a, 1
                ld      (KNOCK), a
                jp      ps_loop
ps_knock_down:  ld      a, 0xff
                ld      (KNOCK), a
                jp      ps_loop
ps_endlevel:    ld      a, 1
                ld      (LEVEL_DONE), a
                ld      a, (NEXT_LEVEL)
                inc     a
                ld      (NEXT_LEVEL), a
                jp      ps_loop
ps_getitem:     ld      a, (hl)
                inc     hl
                cp      1
                jp      nz, ps_loop
                ld      a, (K_CHARID)   ; (the kid only)
                or      a
                jp      nz, ps_loop
                push    hl
                call    proc_get_object ; (the events overlay)
                pop     hl
                jp      ps_loop

; ================================================================ controls
release_arrows: xor     a
                ld      (C_BACK), a
                ld      (C_FWD), a
                ld      (C_UP), a
                ld      (C_DOWN), a
                ld      a, 1
                ret
; read_user_control: edge logic for the held/released/ignore flags
read_user_control:
                ld      hl, C_FWD
                ld      a, (C_X)
                cp      X_FORWARD
                call    ruc_one
                ld      hl, C_BACK
                ld      a, (C_X)
                cp      X_BACKWARD
                call    ruc_one
                ld      hl, C_UP
                ld      a, (C_Y)
                cp      Y_UP
                call    ruc_one
                ld      hl, C_DOWN
                ld      a, (C_Y)
                cp      Y_DOWN
                call    ruc_one
                ld      hl, C_SHIFT2
                ld      a, (C_SHIFT)
                cp      C_HELD
                ; fall through
; ruc_one: HL = flag, Z = the control is active now
ruc_one:        ld      a, (hl)
                jr      z, ruc_active
                bit     7, a            ; flag >= RELEASED (not IGNORE... IGNORE = 1 also >= 0)
                ret     nz              ; HELD (negative): leave? no: C code: if flag >= RELEASED and not active -> RELEASED
                ld      (hl), C_RELEASED
                ret
ruc_active:     ld      a, (hl)
                or      a
                ret     nz              ; HELD or IGNORE stay
                ld      (hl), C_HELD
                ret
flip_control_x: ld      a, (C_X)
                neg
                ld      (C_X), a
                ld      a, (C_FWD)
                ld      b, a
                ld      a, (C_BACK)
                ld      (C_FWD), a
                ld      a, b
                ld      (C_BACK), a
                ret
user_control:   ld      a, (K_DIR)
                or      a
                jr      nz, control     ; facing left
                call    flip_control_x
                call    control
                jr      flip_control_x
control:        ld      a, (K_ALIVE)
                bit     7, a
                jr      nz, ctl_alive
                ld      a, (K_FRAME)
                cp      15
                jp      z, ctl_dying
                cp      166
                jp      z, ctl_dying
                cp      158
                jp      z, ctl_dying
                cp      171
                ret     nz
ctl_dying:      ld      a, SQ_DYING
                jp      seqtbl_offset_char
ctl_alive:      ld      a, (K_ACTION)
                cp      AC_BUMPED
                jp      z, release_arrows
                cp      AC_FREEFALL
                jp      z, release_arrows
                ld      a, (K_SWORD)
                cp      2
                jp      z, control_with_sword
                ld      a, (K_CHARID)
                cp      2
                jp      nc, control_guard_inactive
                ld      a, (K_FRAME)
                cp      15
                jr      z, control_standing
                cp      50
                jr      c, ctl_a1
                cp      53
                jr      c, control_standing
ctl_a1:         cp      48
                jp      z, control_turning
                cp      4
                jp      c, control_startrun
                cp      67
                jr      c, ctl_a2
                cp      70
                jp      c, control_jumpup
ctl_a2:         cp      15
                jp      c, control_running
                cp      87
                jr      c, ctl_a3
                cp      100
                jp      c, control_hanging
ctl_a3:         cp      109
                jr      z, control_crouched
                ret
control_crouched:
                call    crouch_music    ; (sound.asm: the level 1 start's music crouch)
                ret     nz
                ld      a, (C_SHIFT2)
                cp      C_HELD
                jr      nz, ccr0
                call    check_get_item
                or      a
                ret     nz
ccr0:           ld      a, (C_Y)
                cp      Y_DOWN
                jr      z, cc1
                ld      a, SQ_STAND_UP
                jp      seqtbl_offset_char
cc1:            ld      a, (C_FWD)
                cp      C_HELD
                ret     nz
                ld      a, C_IGNORE
                ld      (C_FWD), a
                ld      a, SQ_CROUCH_HOP
                jp      seqtbl_offset_char
control_standing:
                ld      a, (C_SHIFT2)
                cp      C_HELD
                jp      nz, cst0
                ld      a, (C_SHIFT)
                cp      C_HELD
                jp      nz, cst0
                call    check_get_item
                or      a
                ret     nz
cst0:           jp      cs_guard        ; (guard.asm: draw the sword, offguard; back at cs_shift / cs_noshift)
cs_shift:       ld      a, (C_SHIFT)
                cp      C_HELD
                jr      nz, cs_noshift
                ld      a, (C_BACK)
                cp      C_HELD
                jp      z, back_pressed
                ld      a, (C_UP)
                cp      C_HELD
                jr      z, up_pressed
                ld      a, (C_DOWN)
                cp      C_HELD
                jp      z, down_pressed
                ld      a, (C_X)
                cp      X_FORWARD
                ret     nz
                ld      a, (C_FWD)
                cp      C_HELD
                ret     nz
                jp      safe_step
cs_noshift:     ld      a, (C_FWD)
                cp      C_HELD
                jr      nz, cs2
                ld      a, (C_UP)       ; keyboard mode: up + forward = standing jump
                cp      C_HELD
                jp      z, standing_jump
                jp      forward_pressed
cs2:            ld      a, (C_BACK)
                cp      C_HELD
                jp      z, back_pressed
                ld      a, (C_UP)
                cp      C_HELD
                jr      nz, cs3
                ld      a, (C_FWD)
                cp      C_HELD
                jp      z, standing_jump
                jr      up_pressed
cs3:            ld      a, (C_DOWN)
                cp      C_HELD
                jr      z, down_pressed
                ld      a, (C_X)
                cp      X_FORWARD
                jp      z, forward_pressed
                ret
up_pressed:     call    get_tile_at_char        ; an open level door at, behind or in front of him: go up
                cp      T_LEVELDOOR_L
                jp      z, upr_door
                call    get_tile_behind_char
                cp      T_LEVELDOOR_L
                jp      z, upr_door
                call    get_tile_infrontof_char
                cp      T_LEVELDOOR_L
                jr      nz, upr_jump
upr_door:       ld      a, (LV_START_ROOM)
                ld      hl, DRAWN_ROOM
                cp      (hl)
                jp      z, upr_jump
                ld      a, (LEVELDOOR_OPEN)
                or      a
                jp      z, upr_jump
                ld      a, (TILE_COL)
                add     a, FIRST_COL
                ld      hl, x_bump
                call    k_tbl
                add     a, 10
                ld      (K_X), a
                ld      a, D_LEFT
                ld      (K_DIR), a
                ld      a, SQ_GO_UP_DOOR
                jp      seqtbl_offset_char
upr_jump:       ld      a, (C_X)
                cp      X_FORWARD
                jp      z, standing_jump
                jp      check_jump_up
down_pressed:   ld      a, C_IGNORE
                ld      (C_DOWN), a
                call    get_tile_infrontof_char
                call    k_is_floor
                jr      nz, dp2
                call    distance_to_edge_weight
                cp      3
                jr      nc, dp2
                ld      a, 5
                call    char_dx_forward
                ld      (K_X), a
                jp      load_fram_det_col
dp2:            call    get_tile_behind_char
                call    k_is_floor
                jr      nz, crouch
                call    distance_to_edge_weight
                cp      8
                jp      c, crouch
                call    get_tile_behind_char
                ld      (THROUGH_TILE), a
                call    get_tile_at_char
                call    can_grab
                or      a
                jr      z, crouch
                ld      a, (K_DIR)
                or      a
                jr      z, dp_climb     ; facing right
                ld      a, (CURR_TILE2) ; (get_tile_at_char again: same result)
                cp      T_GATE
                jr      nz, dp_climb
                call    k_modif
                rrca
                rrca
                and     0x3f
                cp      6
                jp      c, crouch
dp_climb:       call    distance_to_edge_weight
                sub     9
                call    char_dx_forward
                ld      (K_X), a
                ld      a, SQ_CLIMB_DOWN
                jp      seqtbl_offset_char
control_turning:
                ld      a, (C_SHIFT)
                bit     7, a
                ret     nz
                ld      a, (C_X)
                cp      X_FORWARD
                ret     nz
                ld      a, (C_Y)
                bit     7, a
                ret     nz
                ld      a, SQ_RUN_AFTER_TURN
                jp      seqtbl_offset_char
crouch:         ld      a, SQ_CROUCH
                call    seqtbl_offset_char
                call    release_arrows
                ld      (C_DOWN), a
                ret
back_pressed:   call    release_arrows
                ld      (C_BACK), a
                jp      back_pressed_g  ; (guard.asm: turn, or turn and draw the sword)
forward_pressed:
                call    get_edge_distance
                ld      b, a
                ld      a, (EDGE_TYPE)
                cp      EDGE_WALL
                jr      nz, fp_run
                ld      a, (CURR_TILE2)
                cp      T_CHOMPER
                jr      z, fp_run
                ld      a, b
                cp      8
                jr      nc, fp_run
                ld      a, (C_FWD)
                cp      C_HELD
                ret     nz
                jr      safe_step
fp_run:         ld      a, SQ_START_RUN
                jp      seqtbl_offset_char
control_running:
                ld      a, (C_X)
                or      a
                jp      nz, cr2
                ld      a, (K_FRAME)
                cp      7
                jr      z, cr_stop
                cp      11
                jp      nz, cr2
cr_stop:        call    release_arrows
                ld      (C_FWD), a
                ld      a, SQ_STOP_RUN
                jp      seqtbl_offset_char
cr2:            ld      a, (C_X)
                cp      X_BACKWARD
                jr      nz, cr3
                call    release_arrows
                ld      (C_BACK), a
                ld      a, SQ_RUN_TURN
                jp      seqtbl_offset_char
cr3:            ld      a, (C_Y)
                cp      Y_UP
                jr      nz, cr4
                ld      a, (C_UP)
                cp      C_HELD
                jp      z, run_jump
cr4:            ld      a, (C_DOWN)
                cp      C_HELD
                ret     nz
                ld      a, C_IGNORE
                ld      (C_DOWN), a
                ld      a, SQ_CROUCH_RUN
                jp      seqtbl_offset_char
safe_step:      ld      a, C_IGNORE
                ld      (C_SHIFT2), a
                ld      (C_FWD), a
                call    get_edge_distance
                or      a
                jr      z, ss2
                ld      b, a
                ld      a, 1
                ld      (K_REPEAT), a
                ld      a, b
                add     a, 28
                jp      seqtbl_offset_char
ss2:            ld      a, (EDGE_TYPE)
                cp      EDGE_WALL
                jp      z, ss3
                ld      a, (K_REPEAT)
                or      a
                jp      z, ss3
                xor     a
                ld      (K_REPEAT), a
                ld      a, SQ_STEP_EDGE
                jp      seqtbl_offset_char
ss3:            ld      a, SQ_SAFE_STEP11
                jp      seqtbl_offset_char
control_startrun:
                ld      a, (C_Y)
                cp      Y_UP
                ret     nz
                ld      a, (C_X)
                cp      X_FORWARD
                ret     nz
                jr      standing_jump
control_jumpup: ld      a, (C_X)
                cp      X_FORWARD
                jr      z, standing_jump
                ld      a, (C_FWD)
                cp      C_HELD
                ret     nz
standing_jump:  ld      a, C_IGNORE
                ld      (C_UP), a
                ld      (C_FWD), a
                ld      a, SQ_STANDING_JUMP
                jp      seqtbl_offset_char
check_jump_up:  call    release_arrows
                ld      (C_UP), a
                call    get_tile_above_char
                ld      (THROUGH_TILE), a
                call    get_tile_front_above_char
                call    can_grab
                or      a
                jp      nz, grab_up_with_floor_behind
                call    get_tile_behind_above_char
                ld      (THROUGH_TILE), a
                call    get_tile_above_char
                call    can_grab
                or      a
                jr      nz, jump_up_or_grab
                jr      jump_up
jump_up_or_grab:
                call    distance_to_edge_weight
                cp      6
                jr      c, jump_up
                ld      (K_TMP), a
                call    get_tile_behind_char
                call    k_is_floor
                jr      z, grab_up_no_floor_behind
                ld      a, (K_TMP)
                sub     TILE_SIZEX
                call    char_dx_forward
                ld      (K_X), a
                call    load_fram_det_col
                jp      grab_up_with_floor_behind
grab_up_no_floor_behind:
                call    get_tile_above_char
                call    distance_to_edge_weight
                sub     10
                call    char_dx_forward
                ld      (K_X), a
                ld      a, SQ_JUMP_GRAB
                jp      seqtbl_offset_char
jump_up:        call    release_arrows
                ld      (C_UP), a
                call    get_edge_distance
                cp      4
                jr      nc, ju2
                ld      b, a
                ld      a, (EDGE_TYPE)
                cp      EDGE_WALL
                jr      nz, ju2
                ld      a, b
                sub     3
                call    char_dx_forward
                ld      (K_X), a
ju2:            ld      a, (FEATHER)    ; feather fall: the tile 2 rows up is checked a bit further back
                or      a
                jr      z, ju3
                call    get_tile_above_char
                cp      T_WALL
                jr      z, ju_d0
                call    k_is_floor
                jr      nz, ju_d0
                ld      a, (K_DIR)
                or      a
                ld      a, 3
                jr      z, ju3
                ld      a, 1
                jr      ju3
ju_d0:          xor     a
ju3:            call    back_delta_x
                ld      (K_TMP2), a
                call    dx_weight
                ld      hl, K_TMP2
                add     a, (hl)
                sub     6
                ld      l, a
                ld      h, 0
                call    get_tile_div_mod
                ld      c, a
                ld      a, (K_ROW)
                dec     a
                ld      b, a
                ld      a, (K_ROOM)
                call    k_get_tile
                cp      T_WALL
                jr      z, ju_ceil
                call    k_is_floor
                jr      nz, ju_ceil
                ld      a, SQ_JUMP_NOTHING
                jp      seqtbl_offset_char
ju_ceil:        ld      a, SQ_JUMP_CEILING
                jp      seqtbl_offset_char
control_hanging:
                ld      a, (K_ALIVE)
                bit     7, a
                jp      z, hang_fall
                ld      a, (GRAB_TIMER)
                or      a
                jr      nz, ch2
                ld      a, (C_Y)
                cp      C_HELD
                jr      z, can_climb_up
ch2:            ld      a, (C_SHIFT)
                cp      C_HELD
                jr      nz, hang_fall
                ld      a, (K_ACTION)
                cp      AC_HANG_STRAIGHT
                jp      z, ch3
                call    get_tile_at_char
                cp      T_WALL
                jp      z, ch_wall
                ld      a, (K_DIR)
                or      a
                jp      z, ch3
                ld      a, (CURR_TILE2)
                cp      T_DOORTOP_FLOOR
                jp      z, ch_wall
                cp      T_DOORTOP
                jp      z, ch_wall
ch3:            call    get_tile_above_char
                call    k_is_floor
                ret     nz
                jr      hang_fall
ch_wall:        jp      ch_wall_snd     ; (sound.asm: the bump, SQ_HANG_WALL)
can_climb_up:   call    release_arrows
                ld      (C_UP), a
                ld      (C_SHIFT2), a
                call    get_tile_above_char
                ld      b, a
                ld      a, (K_DIR)
                or      a
                jr      nz, ccu_left
                ld      a, b
                cp      T_MIRROR
                jp      z, ccu_gate
                cp      T_CHOMPER
                jp      z, ccu_gate
                jr      ccu_up
ccu_left:       ld      a, b
                cp      T_GATE
                jr      nz, ccu_up
                call    k_modif
                rrca
                rrca
                and     0x3f
                cp      6
                jr      c, ccu_gate
ccu_up:         ld      a, SQ_CLIMB_UP
                jp      seqtbl_offset_char
ccu_gate:       ld      a, SQ_CLIMB_GATE
                jp      seqtbl_offset_char
hang_fall:      call    release_arrows
                ld      (C_DOWN), a
                call    get_tile_behind_char
                call    k_is_floor
                jp      nz, hf2
                call    get_tile_at_char
                call    k_is_floor
                jp      nz, hf2
                ld      a, SQ_RELEASE_FALL
                jp      seqtbl_offset_char
hf2:            call    get_tile_at_char
                cp      T_WALL
                jp      z, hf_back
                ld      b, a
                ld      a, (K_DIR)
                or      a
                jr      z, hf3
                ld      a, b
                cp      T_DOORTOP_FLOOR
                jp      z, hf_back
                cp      T_DOORTOP
                jr      nz, hf3
hf_back:        ld      a, -7
                call    char_dx_forward
                ld      (K_X), a
hf3:            ld      a, SQ_RELEASE_LAND
                jp      seqtbl_offset_char
grab_up_with_floor_behind:
                call    distance_to_edge_weight
                ld      (GU_DIST), a    ; distance
                call    get_edge_distance
                ld      (GU_EDGE), a    ; edge distance
                ld      a, (GU_DIST)
                cp      4
                jp      nc, guf_fwd
                ld      a, (GU_EDGE)
                cp      4
                jp      nc, guf_fwd
                ld      a, (EDGE_TYPE)
                cp      EDGE_WALL
                jr      z, guf_fwd
                ld      a, (GU_DIST)
                call    char_dx_forward
                ld      (K_X), a
                ld      a, SQ_GRAB_STRAIGHT
                jp      seqtbl_offset_char
guf_fwd:        ld      a, (GU_DIST)
                sub     4
                call    char_dx_forward
                ld      (K_X), a
                ld      a, SQ_GRAB_FORWARD
                jp      seqtbl_offset_char
run_jump:       ld      a, (K_FRAME)
                cp      7
                ret     c
                ld      a, 4
                call    char_dx_forward
                ld      (K_TMP), a      ; xpos
                call    get_tile_div_mod_m7
                ld      (K_TMP2), a     ; col
                xor     a
                ld      (K_TMP3), a     ; tiles_forward
rj_loop:        call    dir_front
                ld      hl, K_TMP2
                add     a, (hl)
                ld      (hl), a
                ld      c, a
                ld      a, (K_ROW)
                ld      b, a
                ld      a, (K_ROOM)
                call    k_get_tile
                cp      T_SPIKE
                jp      z, rj_edge
                call    k_is_floor
                jp      z, rj_edge
                ld      a, (K_TMP3)
                inc     a
                ld      (K_TMP3), a
                cp      2
                jr      c, rj_loop
                jr      rj_go
rj_edge:        ld      a, (K_TMP)
                call    distance_to_edge
                ld      b, a
                ld      a, (K_TMP3)
                or      a
                ld      a, b
                jr      z, rj_e1
                add     a, TILE_SIZEX   ; + 14 * tiles_forward (1)
rj_e1:          sub     TILE_SIZEX      ; adj (signed, -14..)
                ld      b, a
                ; C: if ((word)adj < (word)-8 || adj >= 2) { if (adj < 128) return; adj = -3; }  -> in effect
                ; only adj in -8..-1 goes on, everything else returns without a jump
                cp      -8
                ret     c               ; (unsigned) below 0xF8: 0..127 or < -8
rj_apply:       ld      a, b
                add     a, 4
                call    char_dx_forward
                ld      (K_X), a
rj_go:          call    release_arrows
                ld      (C_UP), a
                ld      a, SQ_RUN_JUMP
                jp      seqtbl_offset_char
; can_grab: Out A = 1/0 (uses THROUGH_TILE, CURR_TILE2 and the last tile's modifier)
can_grab:       ld      a, (THROUGH_TILE)
                cp      T_WALL
                jp      z, cg_no
                cp      T_DOORTOP
                jr      nz, cg1
                ld      a, (K_DIR)
                or      a
                jp      z, cg_no
                ld      a, (THROUGH_TILE)
cg1:            call    k_is_floor
                jp      nz, cg_no
                ld      a, (CURR_TILE2)
                cp      T_LOOSE
                jr      nz, cg2
                call    k_modif
                or      a
                jp      nz, cg_no
cg2:            ld      a, (CURR_TILE2)
                cp      T_DOORTOP_FLOOR
                jr      nz, cg3
                ld      a, (K_DIR)
                or      a
                jr      nz, cg_no
cg3:            ld      a, (CURR_TILE2)
                call    k_is_floor
                jr      z, cg_no
                ld      a, 1
                ret
cg_no:          xor     a
                ret
can_grab_front_above:
                call    get_tile_above_char
                ld      (THROUGH_TILE), a
                call    get_tile_front_above_char
                jr      can_grab
; can_bump_into_gate: Z flag clear (NZ) if (modif >> 2) + 6 < char_height  -> A = 1 yes / 0 no
can_bump_into_gate:
                call    k_modif
                rrca
                rrca
                and     0x3f
                add     a, 6
                ld      b, a
                ld      a, (CHAR_H)
                cp      b              ; A = 1 when b < char_h (carry: char_h < b, zero: equal -> 0)
                ld      a, 0
                ret     c
                ret     z
                inc     a
                ret
; dist_from_wall_forward: A = tiletype -> HL = distance (16-bit signed), or -1 (and A = 0xff flag)
dist_from_wall_forward:
                ld      (K_TMP), a
                cp      T_GATE
                jr      nz, dfw1
                call    can_bump_into_gate
                or      a
                jr      z, dfw_none
dfw1:           ld      a, (TILE_COL)
                add     a, FIRST_COL
                ld      hl, x_bump
                call    k_tbl
                add     a, TILE_MIDX    ; x_bump + 7 (0..255 + wrap: x_bump[19] + 7 = 261 -> use 16-bit)
                ld      l, a
                ld      h, 0
                jr      nc, dfw1b
                inc     h
dfw1b:          ld      (COLL_TLX), hl
                ld      a, (K_TMP)
                call    wall_type
                jr      z, dfw_none
                ld      (K_TMP2), a     ; type
                ld      a, (K_DIR)
                or      a
                jr      z, dfw_right
                ; looking left: char_x_left_coll - (coll_tlx + 13 - wall_dist_from_right[type])
                ld      a, (K_TMP2)
                ld      hl, wall_dist_from_right
                call    k_tbl
                ld      b, a
                ld      a, TILE_RIGHTX
                sub     b
                call    k_sext
                ld      de, (COLL_TLX)
                add     hl, de
                ex      de, hl
                ld      hl, (CX_LCOLL)
                or      a
                sbc     hl, de
                ret
dfw_right:      ld      a, (K_TMP2)
                ld      hl, wall_dist_from_left
                call    k_tbl
                call    k_sext
                ld      de, (COLL_TLX)
                add     hl, de
                ld      de, (CX_RCOLL)
                or      a
                sbc     hl, de
                ret
dfw_none:       ld      hl, -1
                ret
; get_edge_distance: Out A = distance (0..13 or 11), EDGE_TYPE set, CURR_TILE2 = the tile looked at
get_edge_distance:
                call    determine_col
                call    load_frame_to_obj
                call    set_char_collision
                call    get_tile_at_char
                ld      (K_TMP3), a     ; tiletype
                call    wall_type
                jr      z, ged_front
                ld      a, (K_COL)
                ld      (TILE_COL), a
                ld      a, (K_TMP3)
                call    dist_from_wall_forward
                bit     7, h
                jr      nz, ged_front
                jr      ged_wall
ged_wall:       ; distance in HL (>= 0): wall if <= 13 else floor/11
                ld      a, h
                or      a
                jr      nz, ged_floor
                ld      a, l
                cp      TILE_RIGHTX + 1
                jr      nc, ged_floor
                ld      (K_TMP4), a
                ld      a, EDGE_WALL
                ld      (EDGE_TYPE), a
                jr      ged_done
ged_floor:      ld      a, EDGE_FLOOR
                ld      (EDGE_TYPE), a
                ld      a, 11
                ld      (K_TMP4), a
                jr      ged_done
ged_front:      call    get_tile_infrontof_char
                ld      (K_TMP3), a
                cp      T_DOORTOP
                jr      nz, ged_f2
                ld      a, (K_DIR)
                or      a
                jr      z, ged_closer
ged_f2:         ld      a, (K_TMP3)
                call    wall_type
                jr      z, ged_f3
                ld      a, (INFRONTX)
                ld      (TILE_COL), a
                ld      a, (K_TMP3)
                call    dist_from_wall_forward
                bit     7, h
                jr      z, ged_wall
ged_f3:         ld      a, (K_TMP3)
                cp      T_LOOSE
                jp      z, ged_closer
                cp      T_CLOSER
                jp      z, ged_item
                cp      T_SWORD
                jp      z, ged_item
                cp      T_POTION
                jp      z, ged_item
                call    k_is_floor
                jp      z, ged_closer
                jr      ged_floor
ged_item:       call    distance_to_edge_weight
                or      a
                jr      z, ged_floor
                ld      (K_TMP4), a
                ld      a, EDGE_CLOSER
                ld      (EDGE_TYPE), a
                jr      ged_done
ged_closer:     call    distance_to_edge_weight
                ld      (K_TMP4), a
                ld      a, EDGE_CLOSER
                ld      (EDGE_TYPE), a
ged_done:       ld      a, (K_TMP3)
                ld      (CURR_TILE2), a
                ld      a, (K_TMP4)
                ret

; ================================================================ object geometry / collisions
load_frame_to_obj:
                call    load_frame
                ld      a, (CF_IMG)
                ld      (OBJ_ID), a
                ld      a, (CF_DX)
                call    char_dx_forward ; byte
                ld      l, a
                ld      h, 0
                add     hl, hl
                ld      de, -116
                add     hl, de
                ld      a, (CF_FLAGS)
                ld      b, a
                ld      a, (K_DIR)
                xor     b
                bit     7, a
                jr      nz, lfo1
                inc     hl
lfo1:           ld      (OBJ_X), hl
                ld      a, (CF_DY)
                call    k_sext
                ld      a, (K_Y)
                ld      e, a
                ld      d, 0
                add     hl, de
                ld      (OBJ_Y), hl
                ret
set_char_collision:
                ld      a, (OBJ_ID)
                cp      255
                jr      z, scc_noimg
                ld      a, (CF_SWORD)   ; chtab 2 + (sword >> 6): not the kid's images (guard.asm)
                and     0xc0
                jp      nz, scc_guard
                ld      a, (OBJ_ID)
                inc     a               ; pack id = image + 1
                ld      c, a
                ld      a, CH_KID
                call    dir_entry
                inc     hl
                inc     hl
                inc     hl
                ld      a, (hl)         ; width in bytes - but the C uses the pixel width: use the extent masks
                inc     hl
                ld      a, (hl)         ; h
                ld      (CHAR_H), a
                ld      a, (OBJ_ID)     ; pixel width (logic.bin kid_width)
                ld      e, a
                ld      d, high RD_KID_W
                call    rd_logic
                inc     a
                srl     a
                ld      (CHAR_WH), a
                jr      scc1
scc_noimg:      xor     a
                ld      (CHAR_WH), a
                ld      (CHAR_H), a
scc1:           ld      hl, (OBJ_X)     ; char_x_left = obj_x / 2 (toward zero) + 58
                bit     7, h
                jr      z, scc2
                ld      de, 0
                ex      de, hl
                or      a
                sbc     hl, de          ; -obj_x
                srl     h
                rr      l
                ld      de, 0
                ex      de, hl
                or      a
                sbc     hl, de          ; -(-obj_x / 2)
                jr      scc3
scc2:           srl     h
                rr      l
scc3:           ld      de, 58
                add     hl, de
                ld      a, (K_DIR)
                rla
                jr      c, scc4
                ld      a, (CHAR_WH)
                ld      e, a
                ld      d, 0
                or      a
                sbc     hl, de
scc4:           ld      (CX_LEFT), hl
                ld      (CX_LCOLL), hl
                ld      a, (CHAR_WH)
                ld      e, a
                ld      d, 0
                add     hl, de
                ld      (CX_RIGHT), hl
                ld      (CX_RCOLL), hl
                ld      hl, (OBJ_Y)     ; char_top_y = obj_y - h + 1
                ld      a, (CHAR_H)
                ld      e, a
                ld      d, 0
                or      a
                sbc     hl, de
                inc     hl
                bit     7, h
                jr      nz, scc5
                ld      de, 192
                or      a
                sbc     hl, de
                add     hl, de
                jr      c, scc5
                ld      hl, 0
scc5:           ld      (CHAR_TOP_Y), hl
                call    y_to_row_mod4
                ld      (CHAR_TOP_ROW), a
                ld      hl, (OBJ_Y)
                call    y_to_row_mod4
                cp      -1
                jr      nz, scc6
                ld      a, 3
scc6:           ld      (CHAR_BOT_ROW), a
                ld      hl, (CX_LEFT)
                call    get_tile_div_mod
                bit     7, a
                jr      z, scc7
                xor     a
scc7:           ld      (CHAR_COL_L), a
                ld      hl, (CX_RIGHT)
                call    get_tile_div_mod
                bit     7, a
                jr      nz, scc8
                cp      10
                jr      c, scc8
                ld      a, 9
scc8:           ld      (CHAR_COL_R), a
                ld      a, (CF_FLAGS)
                and     F_THIN
                ret     z
                ld      hl, (CX_LCOLL)
                ld      de, 4
                add     hl, de
                ld      (CX_LCOLL), hl
                ld      hl, (CX_RCOLL)
                or      a
                sbc     hl, de
                ld      (CX_RCOLL), hl
                ret
check_collisions:
                ld      a, -1
                ld      (BUMP_L), a
                ld      (BUMP_R), a
                ld      a, (K_ACTION)
                cp      AC_TURN
                ret     z
                ld      a, (K_ROW)
                ld      (COLL_ROW), a
                call    move_coll_to_prev
                ld      a, (COLL_ROW)
                ld      (PREV_COLL_ROW), a
                ld      hl, (CX_RCOLL)
                ld      de, -7
                add     hl, de
                call    get_tile_div_mod
                add     a, 2
                bit     7, a            ; min(.., 11), signed
                jr      nz, cc_r1
                cp      12
                jr      c, cc_r1
                ld      a, 11
cc_r1:          ld      (RIGHT_CHK), a
                ld      hl, (CX_LCOLL)
                ld      de, -7
                add     hl, de
                call    get_tile_div_mod
                dec     a
                ld      (LEFT_CHK), a
                ld      a, (COLL_ROW)
                ld      hl, CURR_ROOMS
                ld      de, CURR_FLAGS
                call    get_row_collision_data
                ld      a, (COLL_ROW)
                inc     a
                ld      hl, BELOW_ROOMS
                ld      de, BELOW_FLAGS
                call    get_row_collision_data
                ld      a, (COLL_ROW)
                dec     a
                ld      hl, ABOVE_ROOMS
                ld      de, ABOVE_FLAGS
                call    get_row_collision_data
                ld      hl, CURR_ROOMS + 9 ; M8a part 23: by pointers (HL the current row, DE the previous; the flags
                ld      de, PREV_ROOMS + 9 ; 10 bytes on, all in KV's page: move_coll_to_prev's guards)
                ld      b, 9
cc_loop:        ld      a, (de)
                cp      (hl)            ; the same room as before (and not none: 0xff)
                jr      nz, cc_next
                or      a
                jp      m, cc_next
                ld      a, l
                add     a, 10
                ld      l, a
                ld      a, e
                add     a, 10
                ld      e, a
                ld      a, (de)
                ld      c, a            ; prev flags
                and     0x0f
                jr      nz, cc_hi
                ld      a, (hl)         ; curr flags
                and     0x0f
                jr      z, cc_hi
                ld      a, b
                ld      (BUMP_L), a
cc_hi:          ld      a, c
                and     0xf0
                jr      nz, cc_back
                ld      a, (hl)
                and     0xf0
                jr      z, cc_back
                ld      a, b
                ld      (BUMP_R), a
cc_back:        ld      a, l
                sub     10
                ld      l, a
                ld      a, e
                sub     10
                ld      e, a
cc_next:        dec     l
                dec     e
                dec     b
                jp      p, cc_loop
                ret
move_coll_to_prev:
                ld      a, (COLL_ROW)
                ld      b, a
                ld      a, (PREV_COLL_ROW)
                cp      b
                jp      z, mcp_curr
                ld      c, a
                ld      a, b
                add     a, 3
                cp      c
                jp      z, mcp_curr
                ld      a, b
                sub     3
                cp      c
                jp      z, mcp_curr
                ld      a, b
                inc     a
                cp      c
                jp      z, mcp_above
                ld      a, b
                sub     2
                cp      c
                jp      z, mcp_above
                ld      hl, BELOW_ROOMS
                jr      mcp_copy
mcp_above:      ld      hl, ABOVE_ROOMS
                jr      mcp_copy
mcp_curr:       ld      hl, CURR_ROOMS
mcp_copy:       ld      de, PREV_ROOMS  ; rooms then flags (contiguous 20 bytes in every set)
                ld      bc, 20
                ldir
                ld      hl, CURR_ROOMS  ; the three rows (rooms 0xff, flags 0), two bytes a djnz (M8a part 21)
                ld      c, 3
mcp_row:        ld      a, 0xff
                ld      b, 5
mcp_clr:        ld      (hl), a
                inc     l
                ld      (hl), a
                inc     l
                djnz    mcp_clr
                xor     a
                ld      b, 5
mcp_clr2:       ld      (hl), a
                inc     l
                ld      (hl), a
                inc     l
                djnz    mcp_clr2
                dec     c
                jp      nz, mcp_row
                ret
                if (CURR_ROOMS / 256) != ((ABOVE_ROOMS + 19) / 256)
                .error  the collision rows must stay in one 256-byte page (inc l)
                endif
                if (BELOW_ROOMS != CURR_ROOMS + 20) or (ABOVE_ROOMS != CURR_ROOMS + 40)
                .error  the three collision rows must be contiguous
                endif
                if ((PREV_ROOMS / 256) != (CURR_FLAGS + 9) / 256) or (PREV_FLAGS != PREV_ROOMS + 10) or (CURR_FLAGS != CURR_ROOMS + 10)
                .error  check_collisions' bump loop: the previous and the current row in one page, the flags 10 bytes on
                endif
; get_row_collision_data: A = row, HL = rooms array (check_collisions: CURR_ROOMS, BELOW_ROOMS or ABOVE_ROOMS; the
; flags array is HL + 10, DE is not read). SDLPoP seg004.c: columns LEFT_CHK..RIGHT_CHK, each one's tile from
; get_tile(Char.room, column, row), flags[tile_col] = (left wall < char_x_right_coll) * 0x0F | (right wall >
; char_x_left_coll) * 0xF0, rooms[tile_col] = curr_room, coll_tile_left_xpos += 14 a column.
; M8a part 23: a row walker. k_get_tile resolves the first column, and again only where tile_col would reach 10 (the
; next column is then in the room on the right, as k_get_tile finds it from Char.room: the rows' links first, the
; columns', then the rows' downwards). Inside a room a column's k_get_tile only adds one to TILE_COL and CURR_TILEPOS
; and reads the next byte of fg (room 0: T_WALL, CURR_TILEPOS 0), so a pointer walks fg. The two compares are running
; 16-bit differences in the alternate set: HL' = coll_tile_left_xpos - char_x_right_coll - 1, the left wall's flag when
; HL' + (wall_dist_from_left + 1) is negative; DE' = coll_tile_left_xpos - char_x_left_coll - 1, the right wall's
; when DE' + (13 - wall_dist_from_right) is not (the same 16-bit values as the old subtractions, plus or minus one).
; A column without a wall gets the row's constant flags (0xFF < rcoll, 0 > lcoll). The rooms array is filled per
; room segment. At the end CURR_ROOM, TILE_ROW (k_get_tile's), TILE_COL, CURR_TILEPOS, CURR_TILE2 and COLL_TLX are
; the last column's, as before. (The old code's scratch K_TMP, K_TMPW, K_TMPW2 is not written: no reader.)
get_row_collision_data:
                ld      (grc_row), a
                ld      a, l
                ld      (grc_rlo), a
                ld      a, (LEFT_CHK)
                ld      c, a
                add     a, FIRST_COL
                ld      hl, x_bump
                call    k_tbl
                add     a, TILE_MIDX
                ld      l, a
                ld      h, 0
                jr      nc, grc0
                inc     h
grc0:           ld      (COLL_TLX), hl
                ld      a, (RIGHT_CHK)
                sub     c               ; right - left < 0: no column (signed, small values)
                ret     m
                inc     a
                ld      b, a            ; B = the columns, C = LEFT_CHK
                push    bc
                ld      de, (CX_RCOLL)
                push    hl
                scf
                sbc     hl, de
                ex      (sp), hl        ; (SP) = tlx - rcoll - 1
                ld      bc, (CX_LCOLL)
                scf
                sbc     hl, bc
                ex      de, hl          ; DE = tlx - lcoll - 1
                xor     a               ; no wall: 0x00FF - rcoll < 0 (its high byte is -H): 0x0F
                sub     h
                rla
                sbc     a, a
                and     0x0f
                ld      l, a
                ld      a, b            ; lcoll - 0 < 0: 0xF0
                rla
                sbc     a, a
                and     0xf0
                or      l
                ld      (grc_nf), a
                pop     hl
                exx
                pop     bc
; grc_get: k_get_tile (Char.room, column C, the row): a segment's first column (B = the columns left with it)
grc_get:        push    bc
                ld      a, (grc_row)
                ld      b, a
                ld      a, (K_ROOM)
                call    k_get_tile
                pop     bc
                ld      a, (CURR_ROOM)
                or      a
                ld      hl, grc_walls   ; room 0: walls (TILE_COL is normalised, CURR_TILEPOS 0)
                jr      z, grc_s1
                call    tile_base       ; HL = the room's fg (keeps BC)
                ld      a, (CURR_TILEPOS)
                add     a, l
                ld      l, a
                jr      nc, grc_s1
                inc     h
grc_s1:         ld      a, (TILE_COL)
                ld      (grc_tc0), a
                ld      c, a            ; C = TILE_COL
                ld      a, (grc_rlo)
                add     a, 10
                add     a, c
                ld      e, a
                ld      d, CURR_ROOMS / 256 ; DE = &flags[TILE_COL]
                jr      grc_col
; the walk. Main: HL = the tile's byte, DE = &flags[TILE_COL], C = TILE_COL, B = columns left. Alternate: HL', DE' the
; differences, BC' scratch; AF' holds the left wall's flag
grc_next:       inc     c
                ld      a, c
                cp      10
                jr      z, grc_cross
                inc     hl
grc_col:        ld      a, (hl)
                and     0x1f
                exx
                add     a, wall_type_tbl & 255
                ld      c, a
                ld      b, wall_type_tbl / 256
                ld      a, (bc)         ; the wall type
                or      a
                jp      z, grc_none
                add     a, a
                add     a, (grc_wd - 2) & 255
                ld      c, a
                ld      b, grc_wd / 256
                ld      a, (bc)         ; wall_dist_from_left + 1
                add     a, l
                ld      a, h
                adc     a, 0
                rla                     ; CY: the left wall < rcoll
                ex      af, af'
                inc     c
                ld      a, (bc)         ; 13 - wall_dist_from_right
                add     a, e
                ld      a, d
                adc     a, 0
                rla                     ; no CY: the right wall > lcoll
                sbc     a, a
                cpl
                and     0xf0
                ld      c, a
                ex      af, af'
                sbc     a, a
                and     0x0f
                or      c
grc_adv:        ld      bc, TILE_SIZEX
                add     hl, bc
                ex      de, hl
                add     hl, bc
                ex      de, hl
                exx
                ld      (de), a
                inc     e
                djnz    grc_next
; the end: the last column's tile variables (CURR_ROOM and TILE_ROW are k_get_tile's), COLL_TLX
                call    grc_fill
                ld      a, (CURR_ROOM)
                or      a
                jr      z, grc_e1
                ld      a, (grc_tc0)
                ld      e, a
                ld      a, (CURR_TILEPOS) ; + TILE_COL - the segment's first
                add     a, c
                sub     e
                ld      (CURR_TILEPOS), a
grc_e1:         ld      a, c
                ld      (TILE_COL), a
                ld      a, (hl)
                and     0x1f
                ld      (CURR_TILE2), a
                exx
                ld      de, (CX_RCOLL)
                add     hl, de
                inc     hl
                ld      (COLL_TLX), hl
                exx
                ret
grc_none:       ld      a, (grc_nf)
                jp      grc_adv
; grc_cross: TILE_COL would be 10: the segment ends; the next column (RIGHT_CHK + 1 - columns left) from k_get_tile
grc_cross:      dec     c
                call    grc_fill
                ld      a, (RIGHT_CHK)
                inc     a
                sub     b
                ld      c, a
                jp      grc_get
; grc_fill: rooms[grc_tc0 .. C] = CURR_ROOM (keeps BC, HL)
grc_fill:       push    bc
                ld      a, (grc_tc0)
                ld      e, a
                ld      a, c
                sub     e
                inc     a
                ld      b, a
                ld      a, (grc_rlo)
                add     a, e
                ld      e, a
                ld      d, CURR_ROOMS / 256
                ld      a, (CURR_ROOM)
grf1:           ld      (de), a
                inc     e
                djnz    grf1
                pop     bc
                ret
grc_walls:      db      T_WALL, T_WALL, T_WALL, T_WALL, T_WALL, T_WALL, T_WALL, T_WALL, T_WALL, T_WALL
; get_left_wall_xpos / get_right_wall_xpos: A = tile (just read) -> HL
get_left_wall_xpos:
                call    wall_type
                jp      z, glw_none
                ld      hl, wall_dist_from_left
                call    k_tbl
                call    k_sext
                ld      de, (COLL_TLX)
                add     hl, de
                ret
glw_none:       ld      hl, 0xff
                ret
get_right_wall_xpos:
                call    wall_type
                jp      z, grw_none
                ld      hl, wall_dist_from_right
                call    k_tbl
                ld      b, a
                ld      a, TILE_RIGHTX
                sub     b
                call    k_sext
                ld      de, (COLL_TLX)
                add     hl, de
                ret
grw_none:       ld      hl, 0
                ret
check_bumped:   ld      a, (K_ACTION)
                cp      AC_HANG_CLIMB
                ret     z
                cp      AC_HANG_STRAIGHT
                ret     z
                ld      a, (K_FRAME)
                cp      135
                jp      c, cb1
                cp      149
                ret     c
cb1:            ld      a, (BUMP_L)
                bit     7, a
                jp      z, check_bumped_look_right
                ld      a, (BUMP_R)
                bit     7, a
                ret     nz
check_bumped_look_left:
                ld      a, (K_SWORD)
                cp      2
                jp      z, cbl1
                ld      a, (K_DIR)
                or      a
                ret     z               ; facing right: no
cbl1:           ld      a, (BUMP_R)
                call    is_obstacle_at_col
                or      a
                ret     z
                ld      a, (CURR_TILE2)
                call    get_right_wall_xpos
                ld      de, (CX_LCOLL)
                or      a
                sbc     hl, de
                ld      a, l
                ld      c, D_RIGHT
                jp      bumped
check_bumped_look_right:
                ld      a, (K_SWORD)
                cp      2
                jp      z, cbr1
                ld      a, (K_DIR)
                or      a
                ret     nz
cbr1:           ld      a, (BUMP_L)
                call    is_obstacle_at_col
                or      a
                ret     z
                ld      a, (CURR_TILE2)
                call    get_left_wall_xpos
                ld      de, (CX_RCOLL)
                or      a
                sbc     hl, de
                ld      a, l
                ld      c, D_LEFT
                jp      bumped
; is_obstacle_at_col: A = column -> A = 1/0
is_obstacle_at_col:
                ld      c, a
                ld      hl, CURR_ROOMS
                call    k_tbl
                ld      (K_TMP), a      ; room of that column's collision data
                ld      a, (K_ROW)
                bit     7, a
                jp      z, ioc1
                add     a, 3
ioc1:           cp      3
                jp      c, ioc2
                sub     3
ioc2:           ld      b, a
                ld      a, (K_TMP)
                call    k_get_tile
                jp      is_obstacle
; is_obstacle: uses the last tile read -> A = 1/0
is_obstacle:    ld      a, (CURR_TILE2)
                cp      T_POTION
                jp      z, io_no
                cp      T_GATE
                jp      nz, io1
                call    can_bump_into_gate
                or      a
                jp      z, io_no
                jp      io2
io1:            cp      T_MIRROR
                jp      z, io_mirror
                cp      T_CHOMPER
                jp      nz, io2
                call    k_modif
                cp      2
                jp      nz, io_no
io2:            ld      a, (TILE_COL)
                add     a, FIRST_COL
                ld      hl, x_bump
                call    k_tbl
                ld      l, a
                ld      h, 0
                call    xpos_in_drawn_room
                ld      de, TILE_MIDX
                add     hl, de
                ld      (COLL_TLX), hl
                ld      a, 1
                ret
io_no:          xor     a
                ret
io_mirror:      ld      a, (K_CHARID)   ; the kid run-jumping left through the mirror breaks it
                or      a
                jp      nz, io2
                ld      a, (K_FRAME)
                cp      39
                jp      c, io2
                cp      44
                jp      nc, io2
                ld      a, (K_DIR)
                or      a
                jp      z, io2
                ld      a, 0x56
                call    set_mod_cur
                ld      a, 0xff
                ld      (JUMPED_MIRROR), a
                jp      io_no
; dead_button: the button held while the kid is dead (SDLPoP process_key: rem_min != 0, Kid.alive > 6, as at the tick's
; start): Ctrl+A, the level restarts (not on level 15) and this tick does nothing more, as the Enter key (keys.asm kl_enter)
dead_button:    ld      a, (REM_MIN)
                or      a
                ret     z
                ld      a, (K_ALIVE)    ; 7 .. 100 (-1: alive)
                sub     7
                cp      94
                ret     nc
                ld      a, (level_number)
                cp      15
                ret     z
                call    snd_stop
                inc     a
                ld      (IS_RESTART), a
                ret
; xpos_in_drawn_room: HL = xpos -> HL adjusted when the tile's room is left/right of the drawn room (SDLPoP
; seg004.c: room_L or room_BL -140, else room_R or room_BR +140; seg008.c load_room_links: with no room below, room_BL /
; room_BR are the left / right room's below, and a missing link is room 0, which the tile's room 0 matches)
xpos_in_drawn_room:
                ld      a, (DRAWN_ROOM)
                ld      b, a
                ld      a, (CURR_ROOM)
                cp      b
                ret     z
                ld      (K_TMP), a
                push    hl
                ld      a, b
                or      a
                jr      z, xdr_none
                call    links_of        ; C = L, B = R, D = U, E = D
                push    bc
                ld      a, e
                or      a
                jr      z, xdr_nb
                call    links_of        ; C = BL, B = BR
                ld      h, c
                ld      l, b
                jr      xdr_cmp
xdr_nb:         pop     bc              ; no room below: the left and right rooms' below
                push    bc
                ld      a, b
                call    links_of
                ld      a, e
                pop     bc
                push    bc
                push    af
                ld      a, c
                call    links_of
                pop     af
                ld      h, e
                ld      l, a
xdr_cmp:        pop     bc
                ld      a, (K_TMP)
                cp      c
                jr      z, xdr_left
                cp      h
                jr      z, xdr_left
                cp      b
                jr      z, xdr_right
                cp      l
                jr      z, xdr_right
xdr_none:       pop     hl
                ret
xdr_left:       pop     hl
                ld      de, -140
                add     hl, de
                ret
xdr_right:      pop     hl
                ld      de, 140
                add     hl, de
                ret
; bumped: A = delta_x (signed byte), C = push direction
bumped:         ld      (K_TMP2), a
                ld      a, c
                ld      (K_TMP3), a
                ld      a, (K_ALIVE)
                bit     7, a
                ret     z
                ld      a, (K_FRAME)
                cp      177
                ret     z
                ld      a, (K_X)
                ld      hl, K_TMP2
                add     a, (hl)
                ld      (K_X), a
                ld      a, (K_TMP3)
                or      a
                jp      z, bp_right
                ld      a, (CURR_TILE2) ; pushing left
                cp      T_WALL
                jp      nz, bp_floor
                ld      a, (TILE_COL)
                dec     a
                ld      (TILE_COL), a
                ld      c, a
                ld      a, (TILE_ROW)
                ld      b, a
                ld      a, (CURR_ROOM)
                call    k_get_tile
                jp      bp_floor
bp_right:       ld      a, (CURR_TILE2)
                cp      T_DOORTOP
                jp      z, bp_r1
                cp      T_DOORTOP_FLOOR
                jp      z, bp_r1
                cp      T_WALL
                jp      nz, bp_floor
bp_r1:          ld      a, (TILE_COL)
                inc     a
                ld      (TILE_COL), a
                ld      c, a
                ld      a, (CURR_ROOM)
                or      a
                jp      nz, bp_r2
                ld      a, c
                cp      10
                jp      nz, bp_r2
                ld      a, (K_ROOM)
                ld      (CURR_ROOM), a
                ld      c, 0
bp_r2:          ld      a, (TILE_ROW)
                ld      b, a
                ld      a, (CURR_ROOM)
                call    k_get_tile
bp_floor:       ld      a, (CURR_TILE2)
                call    k_is_floor
                jp      z, bumped_fall
                ld      a, (K_TMP3)
                jp      bumped_floor
bumped_fall:    ld      a, -4
                call    char_dx_forward
                ld      (K_X), a
                ld      a, (K_ACTION)
                cp      AC_FREEFALL
                jp      nz, bf1
                xor     a
                ld      (K_FALLX), a
                jp      bumped_sound
bf1:            ld      a, SQ_BUMPFALL
                call    seqtbl_offset_char
                call    play_seq
                jp      bumped_sound
; bumped_floor: A = push direction
bumped_floor:   ld      (K_TMP3), a
                ld      a, (K_SWORD)
                cp      2
                jp      z, bfl1
                ld      a, (K_ROW)
                inc     a
                ld      hl, y_land
                call    k_tbl
                ld      hl, K_Y
                sub     (hl)            ; (y_land - y) as byte; C: (word) compare >= 15 of the 16-bit value
                ; y_land[] - Char.y is computed in 16-bit in C: negative -> huge -> >= 15 true
                jp      c, bumped_fall  ; y > y_land (negative result) -> fall
                cp      15
                jp      nc, bumped_fall
bfl1:           ld      a, (K_ROW)
                inc     a
                ld      hl, y_land
                call    k_tbl
                ld      (K_Y), a
                ld      a, (K_FALLY)
                cp      22
                jp      c, bfl2
                ld      a, -5
                call    char_dx_forward
                ld      (K_X), a
                ret
bfl2:           xor     a
                ld      (K_FALLY), a
                ld      a, (K_ALIVE)
                or      a
                ret     z
                ld      a, (K_SWORD)
                cp      2
                jp      z, bfl_sword
                ld      a, (K_FRAME)
                cp      24
                jp      z, bfl_hard
                cp      25
                jp      z, bfl_hard
                cp      40
                jp      c, bfl3
                cp      43
                jp      c, bfl_hard
bfl3:           cp      102
                jp      c, bfl_soft
                cp      107
                jp      c, bfl_hard
bfl_soft:       ld      a, SQ_BUMP
                jp      bfl_go
bfl_hard:       ld      a, SQ_HARDBUMP
bfl_go:         call    seqtbl_offset_char
                call    play_seq
                jp      bumped_sound

; ================================================================ falling / floor
fall_accel:     ld      a, (K_ACTION)
                cp      AC_FREEFALL
                ret     nz
                ld      a, (FEATHER)
                or      a
                ld      a, (K_FALLY)
                jr      nz, fa_feather
                add     a, 3
                cp      34
                jp      c, fa1
                ld      a, 33
fa1:            ld      (K_FALLY), a
                ret
fa_feather:     inc     a               ; (any character: guards fall slowly too)
                bit     7, a
                jr      nz, fa1
                cp      5
                jr      c, fa1
                ld      a, 4
                jr      fa1
fall_speed:     ld      a, (K_Y)
                ld      hl, K_FALLY
                add     a, (hl)
                ld      (K_Y), a
                ld      a, (K_ACTION)
                cp      AC_FREEFALL
                ret     nz
                ld      a, (K_FALLX)
                call    char_dx_forward
                ld      (K_X), a
                jp      load_fram_det_col
check_action:   ld      a, (K_ACTION)
                cp      AC_HANG_STRAIGHT
                jp      z, ca_crouchq
                cp      AC_BUMPED
                jp      z, ca_crouchq
                cp      AC_FREEFALL
                jp      z, do_fall
                cp      AC_MIDAIR
                jp      z, ca_midair
                cp      AC_HANG_CLIMB
                ret     z
                jp      check_on_floor
ca_crouchq:     ld      a, (K_FRAME)
                cp      109
                ret     nz
                jp      check_on_floor
ca_midair:      ld      a, (K_FRAME)
                cp      102
                ret     c
                cp      106
                ret     nc
                jp      check_grab
check_on_floor: ld      a, (CF_FLAGS)
                and     F_NEEDS_FLOOR
                ret     z
                call    get_tile_at_char
                cp      T_WALL
                jp      nz, cof1
                call    in_wall
cof1:           ld      a, (CURR_TILE2)
                call    k_is_floor
                ret     nz
                ld      a, (level_number)
                cp      12
                jp      nz, start_fall
                ld      a, (UNITED)     ; level 12, united with the shadow: the hidden floors of rooms 2 and 13
                and     0x80
                ld      hl, K_ROW
                or      (hl)
                cp      0x80            ; (united < 0 and row 0)
                jp      nz, start_fall
                ld      a, (K_ROOM)
                cp      2
                jr      z, cof_hidden
                cp      13
                jp      nz, start_fall
                ld      a, (TILE_COL)
                cp      6
                jp      c, start_fall
cof_hidden:     ld      a, T_FLOOR
                jp      set_tile_cur
in_wall:        call    distance_to_edge_weight
                ld      (K_TMP), a
                cp      8
                jp      nc, iw1
                call    get_tile_infrontof_char
                cp      T_WALL
                jp      z, iw1
                ld      a, (K_TMP)
                add     a, 4
                jp      iw2
iw1:            ld      a, 6
                ld      hl, K_TMP
                sub     (hl)
iw2:            call    char_dx_forward
                ld      (K_X), a
                call    load_fram_det_col
                jp      get_tile_at_char
start_fall:     ld      a, (K_FRAME)
                ld      (FALL_FRAME), a
                xor     a
                ld      (K_SWORD), a
                ld      a, (K_ROW)
                inc     a
                ld      (K_ROW), a
                call    start_chompers
                ld      a, (FALL_FRAME)
                cp      9
                jp      z, sf_fall
                cp      13
                jp      z, sf_fall2
                cp      26
                jp      z, sf_sj
                cp      44
                jp      z, sf_rj
                cp      81
                jp      c, sf_fall
                cp      86
                jp      nc, sf_more     ; (guard.asm: with the sword)
                ld      a, 5
                call    char_dx_forward
                ld      (K_X), a
                call    load_fram_det_col
sf_fall2:       ld      a, SQ_FALL2
                jp      sf_go
sf_sj:          ld      a, SQ_FALL_SJ
                jp      sf_go
sf_rj:          ld      a, SQ_FALL_RJ
                jp      sf_go
sf_fall:        ld      a, SQ_FALL
sf_go:          call    seqtbl_offset_char
                call    play_seq
                call    load_fram_det_col
                call    get_tile_at_char
                cp      T_WALL
                jp      z, in_wall
                call    get_tile_infrontof_char
                cp      T_WALL
                ret     nz
                ld      a, (FALL_FRAME)
                cp      44
                jp      nz, sf_back1
                call    distance_to_edge_weight
                cp      6
                jp      nc, sf_back1
                ld      a, SQ_FALL_WALL
                call    seqtbl_offset_char
                call    play_seq
                jp      load_fram_det_col
sf_back1:       ld      a, -1
                call    char_dx_forward
                ld      (K_X), a
                jp      load_fram_det_col
do_fall:        call    df_pre          ; (sound.asm: the scream; A = K_ROW)
                inc     a
                ld      hl, y_land
                call    k_tbl
                ld      b, a
                ld      a, (K_Y)
                cp      b               ; y_land > y  (both unsigned bytes; y_land[row+1] for row >= 0 is 55..244)
                jp      c, check_grab   ; y < y_land
                call    get_tile_at_char
                cp      T_WALL
                jp      nz, df1
                call    in_wall
df1:            ld      a, (CURR_TILE2)
                call    k_is_floor
                jp      nz, land
                ld      a, (K_ROW)
                inc     a
                ld      (K_ROW), a
                ret
land:           call    land_pre        ; (sound.asm: the scream ends; A = K_ROW)
                inc     a
                ld      hl, y_land
                call    k_tbl
                ld      (K_Y), a
                call    get_tile_at_char
                cp      T_SPIKE
                jp      z, ld_spikes            ; (C: a goto into the alive branch, dead or not)
                call    get_tile_infrontof_char
                call    k_is_floor
                jp      nz, ld0
                call    distance_to_edge_weight
                cp      3
                jp      nc, ld0
                ld      a, -3
                call    char_dx_forward
                ld      (K_X), a
ld0:            call    start_chompers
                ld      a, (K_ALIVE)
                bit     7, a
                jp      z, ld_dead
                call    distance_to_edge_weight
                cp      12
                jp      c, ld0b
                call    get_tile_behind_char
                cp      T_SPIKE
                jp      z, ld_spikes
ld0b:           call    get_tile_at_char
                cp      T_SPIKE
                jp      nz, ld1
ld_spikes:      call    is_spike_harmful
                or      a
                jp      nz, spiked
ld1:            jp      land_alive      ; (guard.asm: soft / medium / dead per character)
ld_dead:        xor     a               ; take_hp(100), sound 0: crushed (sound.asm)
                call    kill_snd
                ld      a, SQ_CRUSHED
ld_go:          call    seqtbl_offset_char
                call    play_seq
                xor     a
                ld      (K_FALLY), a
                ret
check_grab:     ld      a, (C_SHIFT)
                cp      C_HELD
                ret     nz
                ld      a, (K_FALLY)
                cp      32
                ret     nc
                ld      a, (K_ALIVE)
                bit     7, a
                ret     z
                ld      a, (K_ROW)      ; y_land[row+1] <= y + 25  (16-bit unsigned in C; y + 25 may exceed 255)
                inc     a
                ld      hl, y_land
                call    k_tbl
                ld      e, a
                ld      d, 0
                ld      a, (K_Y)
                ld      l, a
                ld      h, 0
                ld      bc, 25
                add     hl, bc
                or      a
                sbc     hl, de
                ret     c               ; y + 25 < y_land: no
                ld      a, (K_X)
                ld      (K_TMP), a
                ld      a, -8
                call    char_dx_forward
                ld      (K_X), a
                call    load_fram_det_col
                call    can_grab_front_above
                or      a
                jp      nz, cgr1
                ld      a, (K_TMP)
                ld      (K_X), a
                ret
cgr1:           call    distance_to_edge_weight
                call    char_dx_forward
                ld      (K_X), a
                ld      a, (K_ROW)
                inc     a
                ld      hl, y_land
                call    k_tbl
                ld      (K_Y), a
                xor     a
                ld      (K_FALLY), a
                ld      a, SQ_GRAB_MIDAIR
                call    seqtbl_offset_char
                call    play_seq
                jp      grab_snd        ; (sound.asm: grab_timer 12, the grab, the scream ends)

; ================================================================ room change
; leave_room: A = direction left (0..3) or 0xff
leave_room:     ld      a, (K_ACTION)
                cp      AC_BUMPED
                jp      z, lr_notup
                cp      AC_FREEFALL
                jp      z, lr_notup
                cp      AC_MIDAIR
                jp      z, lr_notup
                ld      a, (K_Y)        ; (sbyte)y < 10 && > -16
                ld      b, a
                cp      10
                jp      c, lr_up        ; 0..9
                cp      -15
                jp      nc, lr_up       ; -15..-1
lr_notup:       ld      a, (K_Y)
                cp      211
                jp      nc, lr_down
                ld      a, (K_FRAME)
                cp      135
                jp      c, lr_f1
                cp      150
                jp      c, lr_no
lr_f1:          cp      110
                jp      c, lr_f2
                cp      120
                jp      c, lr_no
lr_f2:          cp      150
                jp      c, lr_f3
                cp      163
                jp      c, lr_no
lr_f3:          cp      166
                jp      c, lr_f4
                cp      169
                jp      c, lr_no
lr_f4:          ld      a, (K_ACTION)
                cp      AC_TURN
                jp      z, lr_no
                ld      a, (K_DIR)
                or      a
                jp      z, lr_right_facing
                ld      hl, (CX_LEFT)
                ld      de, 55
                or      a
                sbc     hl, de
                jp      m, lr_left      ; char_x_left <= 54
                ld      hl, (CX_LEFT)
                ld      de, 198
                or      a
                sbc     hl, de
                jp      p, lr_right     ; >= 198
                jp      lr_no
lr_right_facing:
                ld      c, 9
                ld      a, (K_ROW)
                ld      b, a
                ld      a, (K_ROOM)
                call    k_get_tile
                cp      T_DOORTOP_FLOOR
                jp      z, lr_rf2
                cp      T_DOORTOP
                jp      z, lr_rf2
                ld      hl, (CX_RIGHT)
                ld      de, 201
                or      a
                sbc     hl, de
                jp      p, lr_right
lr_rf2:         ld      hl, (CX_RIGHT)
                ld      de, 58
                or      a
                sbc     hl, de
                jp      m, lr_left
lr_no:          ld      a, 0xff
                ret
lr_up:          ld      a, 2
                jp      lr_special
lr_down:        ld      a, 3
                jp      lr_special
lr_left:        xor     a
                jp      lr_special
lr_right:       ld      a, 1
                jp      lr_special      ; (guard.asm: level specials, then goto_other_room)
; goto_other_room: A = direction -> returns A = direction
goto_other_room:
                ld      (K_TMP), a
                ld      a, (K_ROOM)
                or      a
                jp      z, gor_room0
                call    links_of        ; C L, B R, D U, E D
                ld      a, (K_TMP)
                or      a
                jp      nz, gor1
                ld      a, c
                jp      gor_set
gor1:           cp      1
                jp      nz, gor2
                ld      a, b
                jp      gor_set
gor2:           cp      2
                jp      nz, gor3
                ld      a, d
                jp      gor_set
gor3:           ld      a, e
                jp      gor_set
gor_room0:      xor     a
gor_set:        ld      (K_ROOM), a
                ld      a, (K_TMP)
                or      a
                jp      nz, gor_d1
                ld      a, (K_X)
                add     a, 140
                ld      (K_X), a
                jp      gor_ret
gor_d1:         cp      1
                jp      nz, gor_d2
                ld      a, (K_X)
                sub     140
                ld      (K_X), a
                jp      gor_ret
gor_d2:         cp      2
                jp      nz, gor_d3
                ld      a, (K_Y)
                add     a, 189
                jp      gor_y
gor_d3:         ld      a, (K_Y)
                sub     189
gor_y:          ld      (K_Y), a
                ld      l, a
                ld      h, 0
                call    y_to_row_mod4
                ld      (K_ROW), a
gor_ret:        ld      a, (K_TMP)
                ret
; ================================================================ start / tick
; kid_tick: A = control_x (-1/0/1 screen), C = control_y (-1/0/1), B = shift (0/1)
kid_tick:       ld      (C_X), a
                ld      a, c
                ld      (C_Y), a
                ld      a, b
                or      a
                jp      z, kt0
                ld      a, C_HELD
kt0:            ld      (C_SHIFT), a
                call    tick_pre        ; (guard.asm: timers, mobs, trobs, check_skel, can_guard_see_kid, Char = Kid)
                call    load_fram_det_col
                call    check_killed_shadow
                ld      a, (K_ALIVE)    ; fell_out
                bit     7, a
                jp      z, kt1
                ld      a, (K_ROOM)
                or      a
                jp      nz, kt1
                ld      a, 100
                call    take_hp
                xor     a
                ld      (K_ALIVE), a
                call    erase_text
                ld      a, 185
                ld      (K_FRAME), a
kt1:            ld      a, (K_ALIVE)    ; out of hit points
                bit     7, a
                jp      z, kt1b
                ld      a, (HITP_CURR)
                or      a
                jp      nz, kt1b
                ld      (K_ALIVE), a
kt1b:           ld      a, (GRAB_TIMER)
                or      a
                jp      z, kt2
                dec     a
                ld      (GRAB_TIMER), a
kt2:            ld      hl, CTRL1       ; rest_ctrl_1
                ld      de, C_FWD
                ld      bc, 5
                ldir
                ld      a, (C_SHIFT)    ; the button after death: Ctrl+A (do_paused's process_key, before the controls)
                or      a
                call    nz, dead_button
                ld      a, (KEYS)       ; a key: Ctrl+A, SPACE, Shift+L ... (src/m4/keys.asm; Ctrl+G: game.asm)
                and     0xf9
                call    nz, key_logic
kt2k:           call    guards_off_chk
                call    read_user_control
                call    user_control
                ld      hl, C_FWD       ; save_ctrl_1
                ld      de, CTRL1
                ld      bc, 5
                ldir
                ld      a, (K_ALIVE)    ; death timer (SDLPoP waits while a sound plays: sound.asm death_wait)
                bit     7, a
                jp      nz, kt2c
                ld      a, (K_FRAME)
                cp      177
                jp      z, kt2a
                cp      178
                jp      z, kt2a
                cp      185
                jp      nz, kt2u
kt2a:           call    death_wait      ; (sound.asm: C, A = alive while a sound plays)
                jp      c, kt2b
                ld      (IS_SHOW_TIME), a
                call    death_chk       ; (sound.asm: alive 6 the death music, 7 the text)
                ld      a, (K_ALIVE)
                cp      100
                jp      nc, kt2b
                inc     a
                ld      (K_ALIVE), a
kt2b:
kt2u:           xor     a               ; dead: the screen turns back
                ld      (UPSIDE), a
kt2c:           ld      a, (IS_RESTART) ; Ctrl+A: nothing more this tick (the caller restarts the level)
                or      a
                jp      nz, tick_end
                ld      a, (K_ROOM)
                or      a
                jp      z, kt3
                call    play_seq
                call    fall_accel
                call    fall_speed
                call    load_frame_to_obj
                call    load_fram_det_col
                call    set_char_collision
                call    bump_into_opponent
                call    check_collisions
                call    check_bumped
                call    check_gate_push
                call    check_action
                call    check_press
                call    check_spike_below
                call    check_spiked
                call    check_chomped_kid
                call    check_knock
kt3:            call    savekid
                ld      hl, KV          ; snapshot for the harness (SDLPoP's trace point)
                ld      de, KV_SNAP
                ld      bc, 16
                ldir
                ld      a, (HITP_CURR)
                ld      (TR_SNAP), a
                ld      a, (HITP_MAX)
                ld      (TR_SNAP+1), a
                ld      a, (TROBS_N)
                ld      (TR_SNAP+2), a
                ld      a, (MOBS_N)
                ld      (TR_SNAP+3), a
                if not defined GAME_OVL         ; the room checksum (the trace's last field): m4test only; the game's
                call    room_checksum           ; harness computes it from memory (tests/m4_test.py level_cksum)
                ld      (TR_SNAP+4), hl
                endif
                jp      tick_post       ; (guard.asm: the guard's frame, sword hits, room change)
level_number:   db      1
