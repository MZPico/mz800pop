; ---------------------------------------------------------------- M6: the guard when the kid leaves a room (W1 overlay)
; Split out of guard.asm (2026-10-30): the parts of exit_room and check_guard_fallout that run only when the kid leaves a
; room with a guard in it or a guard falls out of the room. In the game: the guard-leave overlay (window W1,
; src/m4/ovl_gleave.asm; entries guard_leaves, guard_fallout through the stubs in src/m4/ovl.asm). m4test includes this
; file directly. Calls no W1 overlay. The room entry (check_the_end's part) is src/m4/genter.asm.
; guard_leaves (exit_room, after the kid left the room and a guard is there): the guard stays behind (leave_guard) or
; follows the kid (follow_guard)
guard_leaves:
                ld      a, (GUARD_REC + OF_ALIVE)
                bit     7, a
                jp      z, leave_guard
                ld      a, (GUARD_REC + OF_SWORD)
                cp      2
                jp      nz, leave_guard
                ld      a, (KID_REC + OF_ROOM)
                dec     a
                cp      24
                jp      nc, leave_guard
                ld      e, a
                ld      d, 0
                ld      hl, LV_GTILE
                add     hl, de
                ld      a, (hl)
                cp      30
                jr      nc, exr_chk
                ld      hl, LV_GSEQHI
                add     hl, de
                ld      a, (hl)
                or      a
                jp      z, leave_guard
exr_chk:        ld      a, (ROOMLEAVE)
                or      a
                jr      nz, exr_c1
                ld      a, (GUARD_REC + OF_X)   ; left
                cp      91
                jp      nc, leave_guard
                jp      follow_guard
exr_c1:         cp      1
                jr      nz, exr_c2
                ld      a, (GUARD_REC + OF_X)   ; right
                cp      165
                jp      c, leave_guard
                jp      follow_guard
exr_c2:         cp      2
                ld      a, (GUARD_REC + OF_ROW)
                jr      nz, exr_c3
                bit     7, a                    ; up
                jp      z, leave_guard
                jp      follow_guard
exr_c3:         bit     7, a                    ; down
                jp      nz, leave_guard
                cp      3
                jp      c, leave_guard
                jp      follow_guard
leave_guard:    ld      a, (GUARD_REC + OF_DIR)
                cp      DIR_NONE
                ret     z
                ld      a, (GUARD_REC + OF_CHARID)
                cp      CHARID_SHADOW
                ret     z
                cp      CHARID_MOUSE
                ret     z
                ld      a, (GUARD_REC + OF_ROOM)
                or      a
                jr      z, lgu_done
                dec     a
                ld      e, a
                ld      d, 0
                ld      a, (GUARD_REC + OF_ROW) ; get_tilepos(0, row)
                ld      b, 0xff
                bit     7, a
                jr      nz, lgu1
                ld      b, 30
                cp      3
                jr      nc, lgu1
                ld      hl, tbl_line
                call    k_tbl
                ld      b, a
lgu1:           ld      hl, LV_GTILE
                add     hl, de
                ld      (hl), b
                ld      a, (CURR_GUARD_COLOR)
                and     0x0f
                ld      hl, LV_GCOLOR
                add     hl, de
                ld      (hl), a
                ld      a, (GUARD_REC + OF_X)
                ld      hl, LV_GX
                add     hl, de
                ld      (hl), a
                ld      a, (GUARD_REC + OF_DIR)
                ld      hl, LV_GDIR
                add     hl, de
                ld      (hl), a
                ld      a, (GUARD_SKILL)
                ld      hl, LV_GSKILL
                add     hl, de
                ld      (hl), a
                ld      a, (GUARD_REC + OF_ALIVE)
                bit     7, a
                ld      b, 0
                jr      nz, lgu2
                ld      hl, (GUARD_REC + OF_SEQ)
                ld      bc, SEQ_BASE
                add     hl, bc
                ld      b, h
                ld      a, l
                ld      hl, LV_GSEQLO
                add     hl, de
                ld      (hl), a
lgu2:           ld      hl, LV_GSEQHI
                add     hl, de
                ld      (hl), b
lgu_done:       ld      a, DIR_NONE
                ld      (GUARD_REC + OF_DIR), a
                xor     a
                ld      (GUARDHP_CURR), a
                ret
follow_guard:   ld      a, (KID_REC + OF_ROOM)
                call    guard_tile_ptr
                ld      (hl), 0xff
                ld      a, (GUARD_REC + OF_ROOM)
                call    guard_tile_ptr
                ld      (hl), 0xff
                call    loadshad
                ld      a, (ROOMLEAVE)
                call    goto_other_room
                jp      saveshad
; guard_fallout (check_guard_fallout, a guard other than the shadow fell below the room): the skeleton of level 3 lands
; in room 3, any other guard dies
guard_fallout:  ld      a, (GUARD_REC + OF_CHARID)
cgf1:           cp      CHARID_SKELETON
                jr      nz, cgf2
                ld      a, (GUARD_REC + OF_ROOM)
                call    links_of
                ld      a, e
                cp      3
                jr      nz, cgf2
                ld      (GUARD_REC + OF_ROOM), a
                ld      a, 133
                ld      (GUARD_REC + OF_X), a
                ld      a, 1
                ld      (GUARD_REC + OF_ROW), a
                xor     a
                ld      (GUARD_REC + OF_DIR), a
                dec     a
                ld      (GUARD_REC + OF_ALIVE), a
                jp      leave_guard
cgf2:           call    on_guard_killed
                ld      a, (DRAWN_ROOM)
                call    guard_tile_ptr
                ld      (hl), 0xff
                ld      a, DIR_NONE
                ld      (GUARD_REC + OF_DIR), a
                xor     a
                ld      (GUARDHP_CURR), a
                ret
; guard_tile_ptr: A = room (1..24) -> HL = &guards_tile[room - 1] (room 0: [23], as kidsim's Python index -1)
guard_tile_ptr: dec     a
                cp      24
                jr      c, gtp1
                ld      a, 23
gtp1:           ld      e, a
                ld      d, 0
                ld      hl, LV_GTILE
                add     hl, de
                ret
