; M4: which tiles changed since the last tick (view_snapshot before the kid logic, view_redraw after it).
; Low block: never runs inside blit.
; ---------------------------------------------------------------- tiles that changed
; The tiles that affect the room on screen: its own 30 (entries 0..29), column 9 of the room on its left
; (30..32: torches and the left neighbour of column 0), row 2 of the room above (33..42: drawn at the top),
; row 0 of the room below (43..52: the row below row 2).
; vs_entry: VS_IDX -> VS_ROOM (0 none), VS_POS, VS_TAG (the tile to redraw, 0xff none), VS_KIND (0..3)
vs_entry:       ld      a, (VS_IDX)
                cp      30
                jr      nc, vse1
                ld      (VS_POS), a
                ld      (VS_TAG), a
                xor     a
                ld      (VS_KIND), a
                ld      a, (SHOWN_ROOM)
                ld      (VS_ROOM), a
                ret
vse1:           cp      33
                jr      nc, vse2
                sub     30
                ld      hl, tbl_line
                call    k_tbl
                ld      (VS_TAG), a
                add     a, 9
                ld      (VS_POS), a
                ld      a, 1
                ld      (VS_KIND), a
                ld      a, (VS_LINKS)   ; left
                ld      (VS_ROOM), a
                ret
vse2:           cp      43
                jr      nc, vse3
                sub     33
                ld      b, a
                add     a, 20
                ld      (VS_POS), a
                ld      a, b
                add     a, 30
                ld      (VS_TAG), a
                ld      a, 2
                ld      (VS_KIND), a
                ld      a, (VS_LINKS+2) ; above
                ld      (VS_ROOM), a
                ret
vse3:           sub     43
                ld      (VS_POS), a
                ld      b, 0xff
                cp      9
                jr      nc, vse4
                add     a, 21
                ld      b, a            ; row 2, column + 1
vse4:           ld      a, b
                ld      (VS_TAG), a
                ld      a, 3
                ld      (VS_KIND), a
                ld      a, (VS_LINKS+3) ; below
                ld      (VS_ROOM), a
                ret
vs_links:       ld      a, (SHOWN_ROOM)
                or      a
                jr      z, vsl0
                call    links_of
                ld      a, c
                ld      (VS_LINKS), a
                ld      a, b
                ld      (VS_LINKS+1), a
                ld      a, d
                ld      (VS_LINKS+2), a
                ld      a, e
                ld      (VS_LINKS+3), a
                ret
vsl0:           ld      hl, 0
                ld      (VS_LINKS), hl
                ld      (VS_LINKS+2), hl
                ret
; vs_check: the 53 entries' tile addresses (fg; bg = fg + 720; 0 = no room) for the room on screen,
; rebuilt when SHOWN_ROOM changes (load_level sets vs_built to 0xff)
vs_check:       ld      a, (SHOWN_ROOM)
                ld      hl, vs_built
                cp      (hl)
                ret     z
                ld      (hl), a
                call    vs_links
                xor     a
                ld      (VS_IDX), a
                ld      hl, vs_ptrs
                ld      (vr_pp), hl
vb_l:           call    vs_entry
                ld      hl, 0
                ld      a, (VS_ROOM)
                or      a
                jr      z, vb_st
                ld      a, (VS_POS)
                ld      c, a
                ld      a, (VS_ROOM)
                call    o_ptrs          ; HL = &fg
vb_st:          ex      de, hl
                ld      hl, (vr_pp)
                ld      (hl), e
                inc     hl
                ld      (hl), d
                inc     hl
                ld      (vr_pp), hl
                ld      hl, VS_IDX
                inc     (hl)
                ld      a, (hl)
                cp      53
                jr      nz, vb_l
                ret
; vs_get: BC = &fg (0: none) -> B = tile byte, C = modifier, A = 1 for a pressed button (door-link timer
; above 1), else 0. Keeps DE, HL.
vs_get:         ld      a, b
                or      c
                ret     z               ; (A = B = C = 0)
                push    hl
                ld      hl, 720
                add     hl, bc
                ld      a, (bc)
                ld      b, a
                ld      c, (hl)
                pop     hl
                and     0x1f
                cp      T_CLOSER_R
                jr      z, vg1
                cp      T_OPENER
                jr      z, vg1
                xor     a
                ret
vg1:            push    bc
                push    de
                push    hl
                ld      a, c
                call    get_doorlink_timer
                pop     hl
                pop     de
                pop     bc
                cp      2
                ld      a, 1
                ret     nc
                xor     a
                ret
view_snapshot:  call    vs_check
                ld      hl, vs_ptrs
                ld      de, VIEW_SNAP
                ld      a, 53
vsn_l:          ld      (vs_n), a
                ld      c, (hl)
                inc     hl
                ld      b, (hl)
                inc     hl
                call    vs_get
                ex      de, hl
                ld      (hl), b
                inc     hl
                ld      (hl), c
                inc     hl
                ld      (hl), a
                inc     hl
                ex      de, hl
                ld      a, (vs_n)
                dec     a
                jr      nz, vsn_l
                ret
view_redraw:    xor     a
                ld      (VS_IDX), a
                ld      hl, vs_ptrs
                ld      (vr_pp), hl
                ld      hl, VIEW_SNAP
                ld      (VS_PTR), hl
vrd_loop:       ld      hl, (vr_pp)
                ld      c, (hl)
                inc     hl
                ld      b, (hl)
                inc     hl
                ld      (vr_pp), hl
                call    vs_get          ; B, C = new tile byte, modifier; A = pressed
                ld      (VS_PRESSED), a
                ld      hl, (VS_PTR)
                ld      d, (hl)         ; D, E = old
                inc     hl
                ld      e, (hl)
                inc     hl
                cp      (hl)            ; a button pressed or released: redraw it
                inc     hl
                ld      (VS_PTR), hl
                jr      nz, vrd_cht
                ld      a, b
                cp      d
                jr      nz, vrd_cht     ; the tile itself changed
                ld      a, c
                cp      e
                jp      z, vrd_next     ; nothing changed
                push    bc
                push    de
                call    vs_entry
                pop     de
                pop     bc
                ; only the modifier changed: the flame of a torch, a potion's bubble
                ld      a, b
                and     0x1f
                cp      T_TORCH
                jr      z, vrd_torch
                cp      T_TORCH_DEBRIS
                jr      z, vrd_torch
                cp      T_GATE
                jr      z, vrd_gate
                cp      T_POTION
                jr      nz, vrd_tile
                ld      a, (VS_KIND)
                or      a
                jr      nz, vrd_tile
                ld      a, c
                xor     e
                and     0xf8
                jr      nz, vrd_tile    ; the potion's type changed
                ld      a, c
                and     7
                ld      c, a
                ld      a, (VS_TAG)
                call    bubble_redraw
                jr      vrd_next
vrd_torch:      ld      a, c
                cp      9
                jr      nc, vrd_tile
                ld      a, (VS_KIND)
                cp      1
                jr      z, vrd_tleft
                or      a
                jr      nz, vrd_tile
                ld      a, (VS_POS)     ; own torch: the flame is drawn by the tile on its right
                call    mod10
                cp      9
                jr      z, vrd_next     ; (that tile is in the next room)
                ld      a, (VS_TAG)
                inc     a
                call    torch_fast
                jr      vrd_next
vrd_tleft:      ld      a, (VS_TAG)     ; left room's column 9: its flame is drawn by our column 0
                call    torch_fast
                jr      vrd_next
vrd_cht:        push    bc
                push    de
                call    vs_entry
                pop     de
                pop     bc
vrd_tile:       ld      a, (VS_TAG)
                cp      0xff
                jr      z, vrd_next
                call    tile_redraw
                ld      a, (VS_KIND)            ; a left-room tile also feeds our column 0 one row up (the
                cp      1                       ; top of a gate: draw_tile_anim_topright), which tile_redraw
                jr      nz, vrd_next            ; (of our column 0) does not regenerate
                ld      a, (VS_TAG)
                sub     10
                jr      nc, vrd_up
                ld      a, 30                   ; row 0: the row above
vrd_up:         call    tile_redraw
vrd_next:       ld      hl, VS_IDX
                inc     (hl)
                ld      a, (hl)
                cp      53
                jp      nz, vrd_loop
                jp      flames_sync             ; ops moved (any tile_redraw): the registry follows
; a gate's modifier changed (M8a part 2): its bars are drawn by its right neighbour (draw_gate_back) and their top by
; the tile above that (draw_tile_anim_topright), both from min(modifier, 188) / 4; the gate's own tile draws nothing
; of them. So nothing changes on screen for a gate in the above room's row 2 (draw_tile_above has no anim_right) or in
; our own column 9 (seen only from the room on the right), nor while the position min(modifier, 188) / 4 is the same
; (a closing gate moves one row every 4 ticks and not at all above 188). Else gate_redraw (block 2) regenerates the
; drawing tile(s) and lays one rect.
vrd_gate:       ld      a, (VS_KIND)
                cp      2
                jr      z, vrd_next
                or      a
                jr      nz, vrd_gp
                ld      a, (VS_POS)
                call    mod10
                cp      9
                jr      z, vrd_next
vrd_gp:         ld      a, c            ; min(new, 188) / 4 == min(old, 188) / 4 ?
                cp      189
                jr      c, vgp1
                ld      a, 188
vgp1:           ld      b, a
                ld      a, e
                cp      189
                jr      c, vgp2
                ld      a, 188
vgp2:           xor     b
                and     0xfc
                jr      z, vrd_next
                call    gate_redraw
                jr      vrd_next

; ---------------------------------------------------------------- torch flames as objects
; A torch flame is one opaque op that covers its 2 x 18 rect; where it is also the last back/mid op there
; ("exclusive"), its frame need not be in the shadow room: every object chunk that touches it lays the
; current frame right after restoring the shadow, and a chunk inside a flame does not restore at all. A
; torch tick then only patches the op and marks the rect dirty. flames_build lists the exclusive flames of
; the room on screen (after a room draw and after ops were regenerated).
FLM_MAX         equ     8
flames_build:   ld      a, (ops_gen)
                ld      (flm_gen), a
                xor     a
                ld      (flm_n), a
                ld      hl, (opl_base)          ; the back list
                ld      a, (OPCOUNT)
                or      a
                ret     z
                ld      b, a
fb_rec:         push    bc
                push    hl
                inc     hl
                ld      a, (hl)                 ; chtab
                cp      CH_OBJ
                jp      nz, fb_next
                inc     hl
                ld      a, (hl)                 ; id: flames 1..9
                dec     a
                cp      9
                jp      nc, fb_next
                inc     hl
                ld      a, (hl)
                ld      (CRX), a
                inc     hl
                ld      a, (hl)
                ld      (CRY), a
                inc     hl
                ld      a, (hl)
                or      a
                jp      nz, fb_next             ; (above the screen: never)
                inc     hl
                ld      a, (hl)
                ld      (CRW), a
                inc     hl
                ld      a, (hl)
                ld      (CRH), a
                ld      a, (CRX)                ; candidate tag columns as dr_run computes them
                sub     6
                jp      p, fb_c0
                xor     a
fb_c0:          rrca
                rrca
                and     63
                ld      (RR_C0), a
                ld      a, (CRX)
                ld      hl, CRW
                add     a, (hl)
                dec     a
                rrca
                rrca
                and     63
                ld      (RR_C1), a
                call    rect_bounds
                ld      a, 1
                ld      (RR_MODE), a
                xor     a
                ld      (rr_cnt), a
                ld      (rr_last), a
                call    rr_table
                ld      a, 1
                call    rr_table
                xor     a
                ld      (RR_MODE), a
                ld      a, (rr_cnt)             ; exclusive: the last op there is the cover, and it is this flame
                ld      hl, rr_last
                cp      (hl)
                jp      nz, fb_next
                pop     hl
                push    hl
                ld      de, 8
                add     hl, de
                ld      de, (rr_lastrec)
                or      a
                sbc     hl, de
                jp      nz, fb_next
                ld      a, (flm_n)
                cp      FLM_MAX
                jp      nc, fb_next
                ld      l, a
                inc     a
                ld      (flm_n), a
                ld      h, 0
                add     hl, hl
                ld      de, flm_rec
                add     hl, de
                pop     de                      ; the record
                push    de
                ld      (hl), e
                inc     hl
                ld      (hl), d
fb_next:        pop     hl
                ld      de, 8
                add     hl, de
                pop     bc
                dec     b
                jp      nz, fb_rec
                ret
; torch_fast: A = tag of the tile that draws the flame, C = frame: an exclusive flame only gets its op patched
; and its rect marked dirty (the object pass lays it); else the full torch_redraw
torch_fast:     ld      (tf_tag), a
                ld      a, c
                ld      (tf_frm), a
                call    flames_sync             ; ops moved earlier in this pass: the registry follows first
                ld      a, (tf_tag)
                ld      (OP_TAG), a
                ld      a, (tf_frm)
                inc     a
                ld      (OP_NEW), a
                xor     a
                ld      (OP_LIST), a
                ld      a, CH_OBJ
                ld      (OP_CH), a
                ld      a, 1
                ld      (OP_LO), a
                ld      (OP_ONLY), a
                ld      a, 9
                ld      (OP_HI), a
                call    op_patch
                push    af
                xor     a
                ld      (OP_ONLY), a
                pop     af
                or      a
                jp      z, tf_full
                ex      de, hl                  ; DE = the record: registered?
                ld      a, (flm_n)
                or      a
                jp      z, tf_full
                ld      b, a
                ld      hl, flm_rec
tf_l:           ld      a, (hl)
                inc     hl
                cp      e
                jp      nz, tf_l2
                ld      a, (hl)
                cp      d
                jp      z, tf_hit
tf_l2:          inc     hl
                djnz    tf_l
tf_full:        ld      a, (tf_frm)
                ld      c, a
                ld      a, (tf_tag)
                jp      torch_redraw
tf_hit:         ex      de, hl                  ; HL = record: new image (all flames are 16 x 18)
                inc     hl
                inc     hl
                ld      a, (OP_NEW)
                ld      (hl), a
                inc     hl
                ld      b, (hl)                 ; x0
                inc     hl
                ld      c, (hl)                 ; y0
                inc     hl
                inc     hl
                ld      a, (hl)
                add     a, b
                ld      d, a                    ; x1
                inc     hl
                ld      a, (hl)
                add     a, c
                ld      e, a                    ; y1
                jp      dr_add_xy
; flames_lay: lay the registered flames that touch the compose rect (after the shadow restore)
flames_lay:     ld      a, (flm_n)
                or      a
                ret     z
                ld      b, a
                ld      hl, flm_rec
fl_l:           push    bc
                push    hl
                ld      e, (hl)
                inc     hl
                ld      d, (hl)
                push    de
                call    rect_bounds
                pop     hl                      ; HL = record
                ld      de, 8
                add     hl, de
                ld      (OPL_PTR), hl
                call    rec_lay                 ; (lays it if it touches the compose rect)
                pop     hl
                inc     hl
                inc     hl
                pop     bc
                djnz    fl_l
                ret
; flames_cover: carry set when a registered flame covers the whole compose rect
flames_cover:   ld      a, (flm_n)
                or      a
                ret     z
                ld      b, a
                ld      hl, flm_rec
fc_l:           ld      e, (hl)
                inc     hl
                ld      d, (hl)
                inc     hl
                push    hl
                ex      de, hl
                inc     hl
                inc     hl
                inc     hl
                ld      a, (CRX)                ; xb <= CRX and xb + w >= CRX + CRW
                cp      (hl)
                jp      c, fc_n
                ld      c, (hl)
                inc     hl
                ld      a, (CRY)                ; y0 <= CRY and y0 + h >= CRY + CRH
                cp      (hl)
                jp      c, fc_n
                ld      e, (hl)
                inc     hl
                inc     hl
                ld      a, (hl)
                add     a, c
                push    hl
                ld      hl, CRX
                ld      d, (hl)
                ld      hl, CRW
                ld      c, a
                ld      a, d
                add     a, (hl)
                pop     hl
                cp      c
                jp      z, fc_x
                jp      nc, fc_n
fc_x:           inc     hl
                ld      a, (hl)
                add     a, e
                ld      c, a
                ld      a, (CRY)
                ld      hl, CRH
                add     a, (hl)
                cp      c
                jp      z, fc_y
                jp      nc, fc_n
fc_y:           pop     hl
                scf
                ret
fc_n:           pop     hl
                djnz    fc_l
                or      a
                ret
flm_n:          db      0
flm_gen:        db      0xff
flm_rec:        ds      2 * FLM_MAX
tf_tag:         db      0
tf_frm:         db      0
vs_ptrs:        ds      106
vr_pp:          dw      0
vs_n:           db      0
vs_built:       db      0xff
