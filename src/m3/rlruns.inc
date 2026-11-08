; the 64 slots as runs: selector (RL_ROOMS: 0 R, 1 its left, 2 below, 3 below-left, 4 above, 5 above's left, 6 above's
; below, 7 above's below-left), first row, rows, first column, columns
rl_runs:        db      0, 0, 3, 0, 10
                db      1, 0, 3, 9, 1
                db      2, 0, 1, 0, 9
                db      3, 0, 1, 9, 1
                db      4, 2, 1, 0, 10
                db      5, 2, 1, 9, 1
                db      6, 0, 1, 0, 9
                db      7, 0, 1, 9, 1
                db      0xff
