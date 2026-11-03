; ---------------------------------------------------------------- the frame store fill's scratch (SPRBUF_B)
; Shared by the fill overlay (src/m4/fstore.asm, src/m4/fsgen.asm) and its caller in the level-start overlay
; (src/m4/gstart.asm: the loading screen's progress bar).
FF_MBUF         equ     SPRBUF_B                ; the masks (2 x FS_IDS words), fs_id (4), ff_class (1)
fs_mask1        equ     FF_MBUF
fs_mask2        equ     FF_MBUF + 2 * FS_IDS
fs_id           equ     FF_MBUF + 4 * FS_IDS
ff_class        equ     fs_id + 4               ; (right after fs_id: the marker's fifth byte)
ff_save         equ     FF_MBUF + 0x410         ; dir_buf's copy
FG_VARS         equ     FF_MBUF + 0x420         ; the generator's (src/m4/fsgen.asm)
ff_bw           equ     FF_MBUF + 0x460         ; the progress bar (ACT_FILL: the loading screen's): width in bytes
ff_bcol         equ     ff_bw + 1               ; (0: no bar), colour (right after ff_bw), its next byte in VRAM,
ff_bptr         equ     ff_bw + 2               ; the error term (keys x width)
ff_acc          equ     ff_bw + 4
ff_keys         equ     ff_bw + 6               ; the keys to fill
ff_snd          equ     ff_bw + 8               ; 1: snd_fill after each entry (the guard fill at a level start)
ff_set          equ     ff_bw + 9               ; the guard fill's set
FG_CODE         equ     FF_MBUF + 0x480         ; the generator's row code
