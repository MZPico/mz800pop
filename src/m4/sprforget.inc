; sprite_forget's body (M8a part 19: out of the low code block, sprite.asm): after a room change the characters' old
; rects belong to another room. Included by the room overlay (src/m4/ovl_room.asm rf_game) and the level-start overlay
; (src/m4/ovl_level.asm); ends with ret. Uses A, HL.
                ld      hl, 0
                ld      (SPR_A + SD_OXB), hl
                ld      (SPR_A + SD_OW2), hl
                ld      (SPR_G + SD_OXB), hl
                ld      (SPR_G + SD_OW2), hl
                ld      a, l
                ld      (OMOBR_N), a
                inc     a                       ; (st_look: no character as last tick)
                ld      (ST_OK), a
                ret
