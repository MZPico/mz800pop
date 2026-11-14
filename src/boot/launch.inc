; ---------------------------------------------------------------- the launcher's interface (M7 step 1)
; Shared by the launcher (src/boot/boot.asm: the floppy loader is also the launcher), the presentation program PRES
; (src/pres/pres.asm) and the game's level-start overlay (src/m4/ovl_level.asm). docs/m7-design.md "As built".
;
; The launcher swaps two programs in main RAM: the GAME (restored from its compressed image in the RAM disk, written
; there by the boot) and PRES (loaded from the floppy file POP800.PRS, entry 0). A program hands over by writing the
; 16-byte handoff block to the RAM disk (HO_RD_PAGE:HO_RD_ADDR) and jumping to LN_LAUNCH (the game first copies the
; launcher's image from the RAM disk to LN_LOAD: it is not resident during play). The launcher zeroes 0x0000-0x11FF,
; puts a copy of the block at HO_MAIN for the program it starts and jumps to its start.
;
; Handoff block (16 bytes):
;   +0  2  magic HO_MAGIC ("P7"): the copy at HO_MAIN is the game's "started by the launcher" flag
;   +2  1  action (ACT_*): what the program started next has to do
;   +3  1  level (ACT_PLAY: the level to start; ACT_CUTSCENE: the level the scene comes before)
;   +4  1  rem_min           (the remaining time: SDLPoP does not count it during cutscenes, neither does PRES)
;   +5  2  rem_tick
;   +7  1  hitp_beg_lev
;   +8  1  options (reserved for M7: sound on/off; 0)
;   +9  2  K_TICK (kidsim's tick counter, only for traces) \ kept across a level change as the game does without
;   +11 1  last_loose (the loose floor sound, RNG draws)  / the swap
;   +12 1  result (reserved: the PRES -> game direction, e.g. a restored game)
;   +13 1  is_guard_notice   \ SDLPoP globals no level start resets (a bump noise, the last room-leave result):
;   +14 1  roomleave_result  / kept as the game keeps them without the swap
;   +15 1  rd_top (HO_RDTOP): the RAM disk's last 64 KB page as the boot's probe found it (7 = 512 KB, 15 = 1 MB,
;          255 = 16 MB); the launcher sets it in the copy at HO_MAIN each time it starts a program (what a program
;          wrote there in the RAM disk's block is ignored); 0 at HO_MAIN (the harness, which does not boot) = the 512 KB
;          layout (docs/ramdisk-tiers.md). The game's frame store reads it (src/m4/fstore.asm).
; ACT_FILL (the boot, 1 MB and more): the game fills the frame store on the loading screen and hands over to the title;
; its block: +4 2 the progress bar's first VRAM byte (row 0, its first byte column), +6 1 its width in bytes (0: no
; bar), +7 1 its colour (the loader's layout stays the loader's: docs/ramdisk-tiers.md section 11).
LN_LOAD         equ     0xb000          ; the launcher's image runs here (outside both programs' images)
LN_LAUNCH       equ     LN_LOAD + 3     ; jp: start the program the handoff block (RAM disk) asks for
LN_PRS_LOAD     equ     LN_LOAD + 6     ; call (PRES only, the launcher stays at 0xB000 while PRES runs): A = entry
                                        ; of POP800.PRS: its records into main RAM; DI, motor off at the end
LN_LOADING      equ     LN_LOAD + 9     ; call (PRES; the launcher itself before the GAME image): "LOADING..." on the
                                        ; screen (the loading screen's place, row 100, x 32); AF, AF', BC, DE, HL destroyed
LN_MAX          equ     0x0c00          ; the launcher's image in the RAM disk: at most this long (copied whole)
LN_RD_PAGE      equ     0               ; its copy in the RAM disk (written by the boot)
LN_RD_ADDR      equ     0xf000
GAME_RD_PAGE    equ     3               ; the game's compressed image (a record stream, tools/mkgamedisk.py): starts here,
GAME_RD_ADDR    equ     0xa000          ; continues where its 0xFD records point (page 4 0xD400)
HO_RD_PAGE      equ     5               ; the handoff block in the RAM disk
HO_RD_ADDR      equ     0x3ac0
HO_MAIN         equ     0x02a0          ; its copy in main RAM for the program started (low RAM, runtime only)
HO_SIZE         equ     16
HO_MAGIC        equ     0x3750          ; "P7" (little-endian word)
HO_ACTION       equ     2
HO_LEVEL        equ     3
HO_REM_MIN      equ     4
HO_REM_TICK     equ     5
HO_HITP         equ     7
HO_OPTIONS      equ     8
HO_KTICK        equ     9
HO_LOOSE        equ     11
HO_RESULT       equ     12
HO_NOTICE       equ     13
HO_ROOMLEAVE    equ     14
HO_RDTOP        equ     15
HO_RDSPD_MAIN   equ     HO_MAIN - 1     ; 0x029F (outside the block, which has no spare byte): the RAM disk's read
                                        ; speed as the boot measured it (src/boot/rdspeed.asm): the game pattern's
                                        ; average (address OUT + INIR of 32), clocks/byte x 5 (105 = 21.0, no wait
                                        ; states; 0.2 a step, 255 = 51.0 or more; the boot stops above 36.0); set by
                                        ; the launcher at every start as HO_RDTOP; 0 in the harness (not measured).
                                        ; Nothing reads it yet (docs/ramdisk-tiers.md section 1)
ACT_PLAY        equ     0x00            ; game: start level HO_LEVEL
ACT_DEMO        equ     0x01            ; game: the attract demo (level 0; later)
ACT_FILL        equ     0x02            ; game: fill the frame store (1 MB and more), then the title (the boot)
HO_BAR          equ     4               ; ACT_FILL: the progress bar (VRAM address, width, colour)
; the frame store's marker (tools/fstore.py FS_PAGE, FS_MARK; src/m4/fstore.asm checks them): the boot clears it, so
; every boot from the floppy fills the store anew (a store left in the RAM disk is never trusted)
LN_FS_PAGE      equ     8
LN_FS_MARK      equ     0x7700
LN_FS_TOP       equ     15              ; rd_top from which the store is used (1 MB)
ACT_TITLE       equ     0x10            ; PRES (bit 4): the title (then a new game)
ACT_EXPIRED     equ     0x11            ; PRES: the time has expired (then the title)
ACT_ENDING      equ     0x12            ; PRES: the ending (then the title)
ACT_CUTSCENE    equ     0x13            ; PRES: the cutscene before level HO_LEVEL (then that level)
ACT_PRES_BIT    equ     4
ACT_DUEL        equ     0x20            ; the duel easter egg (bit 5; docs/duel-design.md 1.4, 12; src/duel/duel.asm): the
                                        ; PRS entry PRS_DUEL1 (the patch's pieces, staged in the RAM disk), the GAME image,
                                        ; the PRS entry PRS_DUEL (its piece over the game's main loop), the game's start
ACT_DUEL_BIT    equ     5
LN_DUEL_RESERVE equ     100             ; launcher bytes kept for ACT_DUEL, its code included (boot.asm asserts it)
PRS_DUEL        equ     23              ; POP800.PRS entries (POP800.PR3, tools/mkgamedisk.py): the duel's main-RAM
PRS_DUEL1       equ     24              ; piece (P_main) and its staged pieces (build/duel_patch.json)
PRES_START      equ     0x2000          ; PRES's entry (its image: 0x1200-0x7FFF and 0xC000-0xFDFF, never 0x8000-0xBFFF:
                                        ; the launcher's buffers and image while it loads PRS entries)
