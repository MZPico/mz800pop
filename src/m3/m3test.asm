; M3 test: draw a room of a level with the Z80 room renderer.
; The harness loads the packs into the RAM disk, the directories, the level and sets LEVEL_TYPE and
; ROOM_REQ, then runs; the program draws the room and stops at `draw_done` (breakpoint).
VARS            equ     0x0800
FRAMES          equ     VARS + 0
ROOM_REQ        equ     VARS + 8        ; room to draw (set by the harness)
OPS_ONLY        equ     VARS + 9        ; 1 = only build the op list, 2 = tile_redraw(TILE_REQ) from `again`
TILE_REQ        equ     VARS + 10
TILE_FRAME      equ     VARS + 11
RL_TLEVEL       equ     VARS + 12       ; 4 = the precomputed lists (src/m3/rlists.asm) of level RL_TLEVEL, room ROOM_REQ
RL_FAIL         equ     VARS + 13       ; (rl_load said none: 1)
VECTAB          equ     0xfe00
STACK           equ     0xfe00
PORT_DMD        equ     0xce
PORT_SCRL       equ     0xcf
PORT_PAL        equ     0xf0
PIOA_CTRL       equ     0xfc

                org     0x2000
start:          di
                ld      sp, STACK
                out     (0xe0), a
                out     (0xe1), a
                in      a, (0xe0)
                call    video_init
                in      a, (0xe1)       ; VRAM window off: 0x8000-0x9FFF is RAM for the renderer's tables
                call    tables_init
                call    alter_mods
again:          ld      a, (OPS_ONLY)
                cp      4
                jr      z, rl_req
                cp      2
                jr      nc, tile_req
                ld      a, (ROOM_REQ)
                call    room_ops
ops_done:       ld      a, (OPS_ONLY)
                or      a
                jr      nz, draw_done
                call    run_ops
draw_done:      nop                     ; harness breakpoint; it sets ROOM_REQ and PC = again for the next room
                jr      draw_done
rl_req:         xor     a               ; 4: the room's lists read back and patched (roomfull.asm draw_room_full's RL_ON
                ld      (RL_FAIL), a    ; path without run_ops); the harness put the blob and the blueprint in the RAM disk
                ld      a, (ROOM_REQ)
                call    rl_load
                jr      c, rl_none
                call    rl_regen
                jr      draw_done
rl_none:        ld      a, 1
                ld      (RL_FAIL), a
                jr      draw_done
tile_req:       ld      a, (OPS_ONLY)
                cp      3
                jr      z, torch_req
                ld      a, (TILE_REQ)
                call    tile_redraw
                jr      draw_done
torch_req:      ld      a, (TILE_REQ)   ; 3 = torch_redraw(TILE_REQ, frame TILE_FRAME)
                ld      c, a
                ld      a, (TILE_FRAME)
                ld      c, a
                ld      a, (TILE_REQ)
                call    torch_redraw
                jr      draw_done

video_init:     ld      a, 0x02
                out     (PORT_DMD), a
                ld      c, PORT_SCRL
                ld      b, 0x06
                xor     a
                out     (c), a
                ld      b, 0x01
                out     (c), a
                ld      b, 0x02
                out     (c), a
                ld      a, 0x40
                out     (PORT_PAL), a
                xor     a
                out     (PORT_PAL), a
                ld      a, 0x11
                out     (PORT_PAL), a
                ld      a, 0x22
                out     (PORT_PAL), a
                ld      a, 0x33
                out     (PORT_PAL), a
                ld      a, 0x80
                out     (PORT_WF), a
                ld      hl, VRAM
                ld      de, VRAM + 1
                ld      bc, 8000 - 1
                ld      (hl), 0xff
                ldir
                ret

                include "../m1/far.asm"
                include "../m1/gfx.asm"
                include "../m3/room.asm"
                include "../m3/roomfull.asm"
                include "../m3/altmods.asm"
RL_LEVEL        equ     RL_TLEVEL
RL_BP_PAGE      equ     5               ; (the harness writes the level's blueprint there, as the game has it)
RL_BP_ADDR      equ     0x4000
rl_fetch:       or      1               ; (the harness writes the blob and sets rl_lv)
                ret
                include "../m3/rlists.asm"
rr_bkt_ent      equ     rr_bkt          ; (the M4 game: the room overlay's entry)
end_of_code:
                if end_of_code > 0x8000
                .error code overlaps the tables at 0x8000
                endif

; ---- second block: the data tables (0xC000-0xDFFF)
                org     0xc000
block2:
                include "../../build/assets/tables.inc"
block2_end:
                if block2_end > 0xe000
                .error block 2 overlaps the directories
                endif
