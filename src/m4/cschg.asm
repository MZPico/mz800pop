; cs_chg (M8a part 14; in the gate, door and button overlays): A = a tag of our room (0..29): NZ when its tile byte or modifier now
; differs from the tick's snapshot (view.asm view_snapshot: it changed this tick, its redraw is due or done)
cs_chg:         add     a, a
                ld      e, a
                ld      d, 0
                ld      hl, vs_ptrs
                add     hl, de
                ld      c, (hl)
                inc     hl
                ld      b, (hl)
                ld      hl, VIEW_SNAP
                add     hl, de
                ld      a, (bc)
                cp      (hl)
                ret     nz
                inc     hl
                ex      de, hl
                ld      hl, 720
                add     hl, bc
                ld      a, (de)
                cp      (hl)
                ret
