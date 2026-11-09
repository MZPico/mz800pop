; kid.asm get_row_collision_data's data and variables, at the head of block 2 (game.asm, m4test.asm; M8a part 23):
; exactly the 12 bytes that put tables.inc's tile_div_tbl on a page boundary (get_tile_div_mod reads it, and
; tile_mod_tbl the page after, by H = the page, L = xpos). The tables keep their order and distances, so a read past
; the end of one (x_bump[LEFT_CHK + 5] reads up to 255 bytes on) still finds the same bytes as before.
; grc_wd: wall type 1..4 -> wall_dist_from_left + 1, 13 - wall_dist_from_right (both 0..13: zero-extended adds)
grc_wd:         db      11, 13, 1, 3, 0, 0, 1, 13
grc_row:        db      0
grc_rlo:        db      0               ; the rooms array's low byte (the page is CURR_ROOMS')
grc_tc0:        db      0               ; the segment's first TILE_COL
grc_nf:         db      0               ; the flags of a column without a wall
                if (grc_wd / 256) != ((grc_wd + 7) / 256)
                .error  grc_wd must not cross a 256-byte page
                endif
