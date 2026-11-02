# Apple II source (Mechner) and SDLPoP — notes for the MZ-800 port

Sources: https://github.com/jmechner/Prince-of-Persia-Apple-II , https://github.com/NagyD/SDLPoP

## Apple II repo layout (Merlin 6502, ~30,900 lines, 29 .S files, fixed org + jump table per module)
Portable game logic:
- TOPCTRL.S (1740) main loop, NextFrame, FrameAdv, level change, timers
- CTRL.S (2168) player control, floor check, pressplates, impale; CTRLSUBS.S (2120) GETFRAME/GETSEQ, x/y<->block, distances
- COLL.S (1515) ANIMCHAR (sequence interpreter), barrier/gate/slicer collisions, enemy collision
- AUTO.S (1955) guard/shadow/skeleton/vizier AI, strike/stab, off-screen cuts, demo playback
- MOVER.S (2174) "transitional objects": gates, spikes, plates, loose floors, slicers, torches, flasks, mirror; door links
- SEQTABLE.S (1716) + SEQDATA.S animation bytecode; FRAMEDEF.S (490) per-frame tables; BGDATA.S/MOVEDATA.S tile ids + piece/mask tables; TABLES.S lookups
- FRAMEADV.S (2267) room renderer logic: SURE (full 10x3 redraw), FAST (dirty blocks via redraw buffers), object list sort/draw
- GAMEBG.S (1192) meters, object add, level messages; MISC.S, SUBS.S (page flip, potions, demo, pause); SPECIALK.S keyboard/joystick/cheats; EQ.S/GAMEEQ.S memory map
Apple II specific (replace): HIRES.S (2130, blitter: lay/fastlay/layrsave/peel/fastmask, crop, mirror, 7-bit shift tables), HRTABLES.S/HRPARAMS.S, GRAFIX.S (image lists ADDBACK/ADDFORE/ADDMID/ADDWIPE/ADDPEEL, DRAWALL, VBLANK), UNPACK.S (title screens), MASTER.S (RW18 disk loader, LOADLEVEL, save/load), SOUND.S, BOOT.S.

## Data formats
- Level blueprint 2304 bytes: BLUETYPE 24*30, BLUESPEC 24*30, LINKLOC 256, LINKMAP 256, MAP 24*4 (l/r/u/d), INFO 256 (kid start, sword, 24 guards: block/face/x/seq/skill). DOS LEVELS.DAT identical semantics (SDLPoP level_type, 2305 bytes).
- 24 rooms x (10 cols x 3 rows) blocks; the bottom row of the room above is also drawn (D sections).
- Tile types: 0 space,1 floor,2 spikes,3 posts,4 gate,5 dpressplate,6 pressplate,7 panel w/floor,8 pillarbottom,9 pillartop,10 flask,11 loose,12 panel w/o floor,13 mirror,14 rubble,15 upressplate,16/17 exit,18 slicer,19 torch,20 wall,21 bones,22 sword,23/24 window,25-29 arch. Drawn as pieces A/B/C/D via piecea/pieceb/maska/maskb + front pieces (SDLPoP doc/tiles.md).
- Image tables IMG.BGTAB1/2 (.DUN/.PAL), IMG.CHTAB1..7: table of 2-byte pointers; image = width(bytes), height, rows (stored bottom-first), 7 px/byte; faces LEFT, mirrored at blit time; max 127 images/table.
- FRAMEDEF: 5 bytes/frame (Fimage, Fsword, Fdx, Fdy, Fcheck: bits0-4 weight x, bit5 thin, bit6 needs floor, bit7 odd pixel). 240 kid frames, altset1 40 (guards), altset2 90, sword table 64x(image,dx,dy).
- SEQTABLE bytecode: positive = frame; negatives: goto, aboutface, up, down, chx, chy, act, setfall, ifwtless, die, jaru, jard, effect, tap, nextlevel. 88 named entries + cutscene seqs.
- Coordinates: logic x in 140 units across the room (Apple 280 px = 2 px/unit; block = 14 units); DOS maps to 320 px (32 px/block). Rows 63 px (DOS TILE_SIZEY 63, y = 63*row+65).
- Apple frame loop runs as fast as drawing allows, design rate ~12 fps (SDLPoP: 1/12 s per frame, 1/10 s in fights, 60 Hz tick / 5).
- Rendering: double-buffered page flip; image lists background(200)/fore(100)/mid(46, sorted objects)/peel(46)/wipe(20)/msg(32); characters drawn with layrsave (save-under into peel buffers) then peel restores; dirty-block countdown buffers per block (redbuf, fredbuf, floorbuf, wipebuf, movebuf, objbuf...). Object entries 12 bytes (X,OFF,Y,IMG,FACE,TYP,CU/CD/CL/CR,TAB).

## SDLPoP (C, GPLv3, 35.6k lines) — near 1:1 translation of the DOS 1.0 disassembly
- seg000 main/game flow/level load (SDL heavy), seg001 cutscenes, seg002 kid control + guard AI (no SDL), seg003 timers/init, seg004 collision/tile queries (no SDL), seg005 sequence interpreter (no SDL), seg006 movement/physics (3 SDL refs), seg007 trobs/mobs (no SDL), seg008 room drawing (15 SDL refs), seg009 platform (4248 lines: DAT loading, RLE/LZG, palettes, sound), seqtbl.c, types.h/data.h.
- Logic is 8/16-bit, global-state style (Kid/Guard/Char/Opp = char_type), small static arrays. Sprites are SDL surfaces -> not portable; working set ~340 KB on the smallest known port (Game & Watch STM32).
- DAT format: header {u32 table_offset; u16 table_size}; table {u16 count; {u16 id; u32 offset; u16 size}}; 1-byte checksum before each resource. Image: {u16 h; u16 w; u8 0; u8 type} type low nibble = compression (0 raw,1 RLE_LR,2 RLE_UD,3 LZG_LR,4 LZG_UD), bits4-6 = bpp-1. Palette resource 100 bytes (vga[16] 6-bit RGB, cga[16], ega[32]). IDs: KID pal 400 imgs 401-619; VDUNGEON/VPALACE pal 200 (+360 walls) imgs 201+; PRINCE pal 150/700; GUARD-family pal 750 imgs 751-784; PV 800+; LEVELS 2001-2014.
- SDLPoP data/ ships all VGA images as indexed PNG + .pal (copyrighted Ubisoft art, no licence).
- Tools: PR (Princed Resources) https://github.com/NagyD/PR ; apoplexy / leapop level editors; https://github.com/lvcabral/PoPSpritesConverter ; princed.org wiki (DAT_file_format, Legacy_combos); popot.org format spec PDF.
- Docs: Fabien Sanglard code review https://fabiensanglard.net/prince_of_persia/ ; Mechner's 1989 technical document https://jordanmechner.com/en/library ; SDLPoP doc/internals_sequence-table.txt, doc/tiles.md.

## Licensing
Apple II source: informal permission to study/modify; no rights in the PoP franchise (Ubisoft). SDLPoP code GPLv3; DOS art/levels remain Ubisoft's. Any MZ-800 release is a non-commercial fan port on the same footing as the Spectrum/BBC/C64/Atari ports.
