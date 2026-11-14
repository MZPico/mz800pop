# Sharp MZ-800 hardware facts relevant to the port

Sources: mz800emu source + docs/agent (local checkout at ~/src/mz800emu), Hučík's GDG documentation https://www.ordoz.com/gdg-documented/ , Brázda's reference http://mz-800.scav.cz/ , Sharp Technical Reference, MZPico firmware CLAUDE.md. Items marked [unverified] come from gate-level simulation, not measured hardware.

## CPU / timing
- Z80A 3.546895 MHz (17.734475 MHz / 5). PAL line 227.2 T, frame 312 lines = 70,886 T (50.03 Hz). Canvas 200 lines, 112 blank lines (= 25.4k T of vertical blank).
- Interrupts: no dedicated VBLANK IRQ line, but two usable sources: (a) Z80 PIO (ports FC-FF) mode 3 on port A bit 5 = VBLN -> IM2 50 Hz interrupt, the usual choice for games/demos (mz800emu docs/agent/memory_layout.md); (b) i8253 counter 1 clocked by HSYNC, counter 2 chained, OUT2 -> /INT gated by 8255 PC2 (IM1 RST 38). Polling: IN (CEh) bit6 = VBLNK (1 during canvas), bit7 = HBLNK; 8255 PC7 = VBLNK too.
- VRAM (8000h-9FFFh window) wait states [unverified, from HDL]: reads always +2..5 T; a single write is free but opens a "hot phase" (~24-39 CLK0 visible); a second VRAM access inside it costs +3..7 T (write) / +6..10 T (read). Writes >= 8 T apart pay nothing => LDI/LDIR RAM->VRAM runs at full speed; PUSH-to-VRAM tricks lose. VRAM->RAM LDIR costs +2..5 T/byte. Main DRAM has no waits.

## Video (GDG WHID 65040-032)
- DMD (port CEh write): 02h = 320x200 16-colour (planes I-IV, needs MZ-1R25 extension; without it planes III/IV read FFh). 00/01 = 320x200 4-colour frame A/B, 04/05 = 640x200 2-colour A/B, 06 = 640x200 4-colour, 08 = MZ-700 text.
- VRAM: 4 planes x 8000 bytes, 40 bytes/line, **bit 0 = leftmost pixel** (verified in M0 by writing 01h: pixel 8*byte lights; the GDG docs' 'bit 7' claim is wrong or refers to a different convention). Plane I=B, II=R, III=G, IV=I; colour = IV*8+III*4+II*2+I. In 320x200 modes all planes share ONE 8 KB CPU window 8000h-9FFFh (A000h-BFFFh stays DRAM). Plane selection by WF/RF.
- WF (CCh): bits7:5 mode, bit4 A/B, bits3:0 plane enable. Modes: 000 SINGLE (data -> every selected plane), 001 EXOR, 010 OR, 011 RESET (and-not), 10x REPLACE (pixels with bit=1 get colour WF[3:0], bit=0 get colour 0; all four planes written by one byte), 11x PSET (bit=1 pixels get colour WF[3:0], others untouched). After reset WF=0 => writes do nothing; set WF first.
- RF (CDh): bit7 SEARCH (returns mask of pixels whose colour == bits3:0) else read the single selected plane. Bit4 A/B latch shared with WF.
- Palette (F0h): `0 S2 S1 S0 I G R B`. S2=0 sets PLT(S1:S0) to colour IGRB. S2=1: SW bits choose which group of 4 colours (upper two colour bits) passes through PLT0-3; the other 12 colours are fixed IGRB. Border CF06h unpaletted.
- 16 colours (IGRB): 0 #000000, 1 #4040AC, 2 #D03400, 3 #B40C8C, 4 #406C00, 5 #24CCFF, 6 #E8D430, 7 #D0D0D0, 8 #848484, 9 #008CE8, A #FF0000, B #F054CC, C #54FF54, D #80FFFF, E #FFFF28, F #FFFFFF.
- HW scroll (CFh sub-registers SOF/SW/SSA/SEA): vertical only, 8-line granularity, ring-buffer region with fixed rows above/below. Gotcha: in 16-colour mode SOF is ALSO added to CPU VRAM accesses, always. Keep SOF = 0.
- Registers apply immediately (mid-line raster effects possible).

## Memory / banking (MZ-800 mode, port number selects, data ignored)
- OUT E0h: RAM at 0000h-1FFFh (ROM + CG ROM off). OUT E1h: RAM at E000h-FFFFh. OUT E2h/E3h: ROMs back. OUT E4h: reset mapping. IN E0h: map CG ROM + VRAM window in; IN E1h: map them out. Avoid E5h/E6h.
- All 64 KB RAM with VRAM window kept: OUT (E0h), OUT (E1h), IN (E0h) (window 8000h-9FFFh then hides 8 KB of DRAM; IN (E1h) reveals it again, 11 T per switch).
- I/O: 8255 D0h-D3h (keyboard: PA bits3:0 column strobe, PB return bits active low; PC0 sound gate, PC2 IRQ mask, PC7 VBLNK), 8253 D4h-D7h, PSG SN76489 F2h (clock 3.547 MHz, 3 tones + noise), joystick IN F0h/F1h (active low: b0 up b1 down b2 left b3 right b4 fire1 b5 fire2 [unverified bit order]), Z80 PIO FCh-FFh.

## Floppy (MZ-1E05 + MZ-1F11, WD2793)
- Ports D8h cmd/status, D9h track, DAh sector, DBh data (D8-DB data bus INVERTED), DCh motor/drive (bit7 motor, bits1:0 drive), DDh side, DEh density. Sharp FSMZ data on disk is also inverted.
- Format 2 sides x 40 tracks x 16 sectors x 256 B = 320 KB MFM (80-track drives common in CZ/SK, MZPico images any size). Container: Extended CPC DSK.
- Boot: IPL ROM reads cylinder 0 side 1, sectors 1-16; sector 1 starts with 03h "IPLPRO" + 13-char name + size/load/exec (MZF-like header); IPL loads `size` bytes to `load` and jumps to `exec` [semantics inferred from mzdisk/MZTools]. mzdisk: `mzdsk-create --format-basic 40 --sides 2 game.dsk`, `mzdsk-fsmz game.dsk boot put loader.mzf`, `mzdsk-fsmz game.dsk put file.mzf`.
- Driver prior art: https://www.ordoz.com/sharp/fddrv/ (Z80 + SDCC source), mz800emu src/emulator/hw-generic/fdc, MZPico fdc.cpp.

## RAM disk
- MZ-1R18 (64 KB): EBh = 16-bit address (OUT (C),A with B = high byte), EAh = data with auto-increment (INIR/OTIR ~21 T/byte), E9h = page select on paged clones (64 KB pages), F8h = reset counter. Bigger clones: MR-25 256 KB, MR-50 512 KB, up to 16 MB in mz800emu "STD" model. Pezik 512 KB (E8h-EFh) is NOT MZ-1R18 compatible (explicit 16-bit address per byte, slower).
- MZPico: `[ramdisk]` = paged MZ-1R18 protocol (E9/EA/EB, reset F8), 64 KB pages, Deluxe board only; `[pico_rd]` simple protocol on port 45h, all boards; `[sramdisk]` F8h instant-boot MZF; `[fdc]` D8h with .dsk images.
- mz800emu also emulates memory-mapped RAM extensions ("memext", Luftner/PEHU) — a faster alternative to a port-based RAM disk if real hardware for it exists in the target setup.

## Formats / tools
- MZF: 128-byte header (00 type 01=OBJ, 01-10 name Sharp ASCII 0Dh-terminated, 12 size, 14 load, 16 exec, 18-7F comment) + body.
- Tools: mz800emu (+ MCP server, headless, profiler, snapshots), mzdisk, bin2mzf, MZTools, pasmo / sjasmplus / z88dk `+mz` (no MZ-800 graphics lib) / SDCC 4.5.
- Prior art 16-colour MZ-800 games: International Karate, Uridium cV16, J.O. Vsetín colour releases, Recycler (2016); BomberNet (2026, C/z88dk, 8253 frame limiter): https://github.com/MZPico/BomberNet

## MZPico pico_rd protocol (from MZPico-firmware src/mz_devices/pico_rd.cpp, base port 45h)
- base+0 control: any read or write resets the position to 0 (read returns 0).
- base+1 data: read/write one byte at the current position, position auto-increments.
- base+2 / +3 / +4: write address byte 2 / 1 / 0 of the 24-bit position (read returns the current byte); writing any of them also resets the "sequential address index".
- base+5 addrs: sequential address load: successive writes set byte 0, 1, 2 of the position (index cycles 0->1->2->0).
- base+6 addri: add the written byte to the position (wraps at size).
- Default size 64 KB (configurable via image). Asserts /EXWAIT. Works on every MZPico board.
- Driver sketch: seek = OUT base+2/+3/+4 (3 OUTs); read n bytes = `LD C,base+1 : INIR` (21 T/byte, same as MZ-1R18).

## mz800emu harness findings (2026-10-25)
- JSONL pipe protocol (`mz800emu --mcp-pipe`): first line = hello {type, version, capabilities, commands[]};
  requests {"req_id", "cmd", "data"}; responses {"type":"response","req_id","success","data"|"error"}.
  tools/emu.py wraps it. The core answers only after a short start-up (ping/run retry loop).
- At speed mode `normal` the headless pipe emulator advances ~1 frame per second (audio 20 ms sync
  timeouts); `set_speed mode=max` runs frame-exact at full host speed (200 frames in 0.2 s). The
  harness always uses max. Worth reporting upstream.
- `get_state` returns "Emulator unavailable" in pipe mode; use ping/run/get_speed instead.
- Region ids for `region_read`: 8/9/10/11 = VRAM planes I-IV (8000 bytes each); ramdisk STD banks
  start at id 76 (64 KB each, 16 banks = 1 MB with the current INI); memext PEHU 4 KB banks precede them.
- media_load_mzf (CMT hack) needs the ROM to have run a few frames first; `IN (E0h)` maps CG-ROM over
  1000h-1FFFh, so test programs must keep their variables elsewhere (0x7FFE used).
- The colour-bar test confirmed: DMD=02h gives 16-colour mode, WF REPLACE paints all four planes with
  one byte write, colours 0-3 pass through PLT0-3 (must be set to identity), VBLNK polling on CEh bit 6
  gives one count per frame.

## M0 results (2026-10-25, src/m0/m0boot.asm + tests/m0_test.py, all verified in mz800emu)
- Floppy boot: `mzdsk-create --format-basic 40 --sides 2` + `mzdsk-fsmz boot put prog.mzf` makes a disk the
  ROM IPL boots: it reads the bootstrap to 1200h, moves it to the MZF load address (ROM ECFCh) and jumps to
  exec. Load the program above 2000h: `IN (E0h)` later maps the CG ROM over 1000h-1FFFh. Boot takes ~83 frames.
- Z80 PIO ports: **FCh = control A, FDh = control B, FEh = data A, FFh = data B** (mz800emu pioz80.h). VBLN =
  port A bit 5, high during the 200 canvas lines, low in vertical blank. Mode 3 setup for a 50 Hz interrupt:
  vector, CFh, FFh (all inputs), 97h (enable, OR, active low, mask follows), DFh (bit 5 only). IM2 with the
  vector table at FE00h. The interrupt fires at scanline 245 (top border 46 + canvas 200 = first blank line).
- 8255 PA: bits 3:0 keyboard column, bit 5 = joystick 1 strobe (low = enabled), bit 6 = joystick 2 strobe.
  Writing the bare column number (0-9) keeps both joysticks strobed. Joystick 1 read: IN (F0h), active low
  b0 up, b1 down, b2 left, b3 right, b4 fire (verified with the emulator's NUM_KEYPAD joystick).
- Keyboard: cursor keys column 7 (bit2 left, bit3 right, bit5 up, bit4 down), SPACE column 6 bit 4.
  CTRL column 8 bit 6, SHIFT column 8 bit 0, letters A-H column 4 bits 7-0 (A bit 7, G bit 1), I-P column 3 bits 7-0
  (L bit 4) (mz800emu iface_keyboard.c / `get_input_keyboard_matrix_info`; letters are not in that list). The game
  (game.asm get_controls) reads Ctrl+A (restart) and Ctrl+G (save) from these, once per press.
- STD/MZ-1R18 RAM disk: `IN (F8h)` reset, `OUT (E9h)` page, address via `LD B,hi : LD C,EBh : OUT (C),A` (A =
  low byte), data `EAh` with auto-increment. Probe found 16 pages (1 MB) with the project INI. **INIR reads
  4096 bytes in 86,077 T = 21.0 T/byte.** pico_rd (port 45h) is not emulated by mz800emu: untested until hardware.
- Emulator harness: `input_send_joystick` holds the state while running `frames` frames and then releases, so
  read the program's input copy right after the call; `input_press_key`/`input_release_key` use names from
  `get_input_keyboard_matrix_info` (LEFT, RIGHT, UP, DOWN, SPACE, ...); joystick needs `joy1_type = NUM_KEYPAD`
  in the INI; `bp_add {addr}` + `run` + `get_raster_pos` gives scanline/cycle counts for timing measurements.

## M5 floppy loader findings (2026-10-30, src/boot/boot.asm, tools/mkgamedisk.py, tests/m5_boot.py)
- WD2793 (MB8876) on the Sharp FDC: ports D8h command/status, D9h track, DAh sector, DBh data are **inverted** (CPL
  every value written and read); DCh motor/drive (bit 7 motor, bit 2 select enable, bits 1-0 drive), DDh side and
  DEh density are not inverted. Read status bit 0 = not BUSY, bit 1 = no DRQ (inverted bus).
- FSMZ block b (256 B) = logical track b / 16, sector b mod 16 + 1; logical track t = cylinder t >> 1, logical side
  t & 1, and the ROM writes the side **inverted** to DDh (logical side 1 -> FEh, 0 -> FFh), so in the DSK image block
  b sits on track (b / 16) XOR 1 (mzdsk-fsmz dump-block shows it: block 0 = DSK track 1). File data is stored
  inverted on the disk (mzdsk does it): with the inverted bus the CPU reads the true bytes.
- FSMZ layout (mzdsk-create --format-basic 40 --sides 2): 1280 blocks; IPLPRO header block 0, DINFO (bitmap) block 15,
  directory blocks 16-23 (32-byte entries: +0 type, +1 name CR-padded to 17, +14h size, +16h load, +18h exec,
  +1Eh start block; entry 0 is a header with type 80h), the file area from block 48 (the bootstrap first). Files are
  contiguous; `mzdsk-fsmz put` takes the first free blocks.
- The ROM IPL's floppy sequence (E4DCh-E660h; ROM image in mz800emu ROM_MZ800_E000.c): `OUT (DCh),84h` (drive 0 +
  motor), wait for READY (status bit 7); restore 0Bh once per drive; per track: data register = cylinder, seek 1Bh
  (wait not busy, ~60 ms delay loop E6BFh, status AND 99h must be 0), track register = cylinder, sector register,
  read sectors multiple **94h**, then poll `IN (D8h) / RRCA / JR C,end / RRCA / JR C,poll / INI` (61 T a byte; the
  disk needs one every 32 us = 113 T), after the last wanted sector force interrupt **D8h**, wait not busy, status
  must read 0. After the load `OUT (DCh),80h` keeps the motor on (the bootstrap starts with it running); `OUT
  (DCh),0` stops it. The loader copies this sequence (multi-sector reads of the whole needed part of a track,
  retries with a restore, "DISK ERROR" after 4 failures; 6 since 2026-11-14, below).
- mz800emu's WD279x (src/emulator/hw-generic/fdc/wd279x.c, "phase B") executes every command instantly: no
  rotation, no step or settle time, DRQ at once. Boot times measured in the emulator are CPU time only (the
  loader's own delay loops included). On a real drive each track read costs about half a turn of latency plus
  n x 12.5 ms (300 rpm, 16 x 256 B), each seek 30 ms a cylinder step (command 1Bh) + the 60 ms loop + 15 ms settle.
  Emulator quirks: a track register write of 0 (CPU FFh) is ignored (a CP/M 1.4 workaround), more than 10 status
  reads before the first data byte of a READ SECTOR end the sector early (the polling loop reads data at once).
- MZ-1R18 in mz800emu: the 16-bit address auto-increments without carrying into the page register (keep a
  transfer inside one 64 KB page); the page register is ANDed with the size mask (256 KB = 3, 512 KB = 7), so a
  smaller RAM disk aliases pages: the loader writes a marker to offset 0 of pages 7 down to 0, reads them back
  (all distinct = 512 KB or more) and restores the bytes (since 2026-11-03 pages 255 down to 0: it counts the pages,
  rd_top, docs/ramdisk-tiers.md; mz800emu supports 64K / 256K / 512K / 1M / 16M, its MCP lists all 256 pages of 16M since MZPico/mz800emu#2, pages 0-51 before). `mr1r18_size = 256K` in a copy
  of the INI tests the refusal. The INI's `mr1r18_type = STANDARD` keeps the RAM disk in memory (0xFF at start, no
  file); `SRAM` saves it to `mr1r18_filepath` on every exit.
- To check on real hardware (not emulated): the real drive's timing (latency, the 1Bh step rate on the
  installed drive; first real-drive results: "Real drive findings" below), booting from a drive other than 0 (the loader always uses drive 0), the MZ-1R18 page aliasing
  of a 256 KB card (the probe assumes unused page bits are ignored), and MZPico (its FDC emulation and pico_rd
  RAM disk, port 45h): the loader only uses the standard WD2793 ports and the MZ-1R18 protocol.

## M5 save findings (2026-10-30, src/m4/save.asm, src/boot/fdc.asm, tests/m5_save.py)
- WRITE SECTOR A4h (one sector, 15 ms settle) through the inverted bus: the CPU writes the true bytes (OUTI), the
  disk then holds them inverted like every FSMZ file, so mzdsk and the loader read them back true. Poll as for reads
  (bit 0 not busy, bit 1 no DRQ), the final status (CPL) must be 0 and all 256 bytes taken; write protect = 40h.
- READ ADDRESS (C0h): the six ID bytes come through the inverted bus too, and the IDs on the disk are true values:
  CPL them. WD order: track, side, sector, length, CRC (2). mz800emu returns track, **sector, side**, length, 0, 0
  (its "MB8876A quirk", from its older FDC code) and, having no rotation, always the first sector of the track or
  the last one read; the loader uses byte 2 (WD order), so in the emulator it sees the side value: both lead to a
  correct read (only the starting sector differs). To check on a real drive: the byte order and the gain.
- mz800emu: `media_insert`'s `ro` flag is ignored (the drive stays writable); a disk file without write permission
  is mounted write-protected (fs_readonly). FDD storage mode `cached` (the INI default): the image lives in memory
  and is written back to the file at eject (`media_eject`), reset or exit. Writes from a test therefore go to the
  mounted file: tests mount copies (tests/m5_boot.py mounts build/pop800.dsk only for reads).

## Real drive findings (2026-11-14, the first real-floppy test: a PC 3.5" drive, src/boot/boot.asm, src/boot/fdc.asm, src/m4/save.asm, tools/edsk.py, tests/m5_floppy.py)
The user wrote build/pop800.dsk with a Greaseweazle (gw 0.34) and booted a real MZ-800 from a PC 3.5" DD drive
(300 rpm, 80 tracks; the 40 cylinders of the image go to its cylinders 0-39, single steps).
- **"No master" (the ROM found no IPLPRO): the image.** mzdisk (DSKLib) writes every Extended DSK sector-info entry
  with bytes 6-7, the "actual data length", set to 0; mz800emu ignores the field, gw trusts it and wrote the sectors
  without data. With 128 << N there (256) the disk boots. The build now sets them (tools/edsk.py fix, called by
  tools/mkgamedisk.py for every game disk, the cheats and pacing ones included, and by the Makefile for build/m0.dsk);
  tests/edsk_check.py and the release workflow (tools/edsk.py check) fail on any 0 or wrong length.
- **DISK ERROR after the boot's load, intermittent: the spin-up.** With the fixed disk the boot loaded, then "DISK
  ERROR" (the drive seeking): on the loading screen with the bar full (the launcher's first PRES load), on the black
  screen with "LOADING..." (PRES's first loads), and once a game ran, again when it went back to the title after a
  death. Every one of these is a load right after a motor start: until then each LN_PRS_LOAD ended with the motor off
  and the next one's fd_init turned it on and only waited for READY. A PC drive reports READY at once (or the adapter
  ties it; its pin 34 may even be DISKCHG) while the disk still speeds up (0.3-0.5 s typical, up to ~1 s), and the
  reads fail until it is at speed; the 4 tries ~70 ms apart (restore + 60 ms each) were over in ~0.3 s. The ROM waits
  16 x 60 ms (E517h, ~0.97 s) after it turns the motor on, before it even selects the drive (+60 ms) and asks for READY;
  so the bootstrap's own load was safe, and mz800emu (no rotation, ready at once) never showed it. Fixed:
  - the launcher's fd_init waits ~0.97 s (16 x delay_long, the ROM's figure; READY is not trusted for it) whenever
    the motor was stopped (fd_on, the launcher's own record: 0 after motor_off; launch_main always stops the motor,
    so the first load after any program waits; the boot's load does not, the ROM left the motor running); the save
    overlay's and PRES's sv_find always waits (the game runs with the motor off); PRES's sv_off stops the motor
    through the launcher's entry LN_MOTOR_OFF, which clears fd_on;
  - LN_PRS_LOAD keeps the motor running when A has PRS_KEEP (bit 7): PRES marks the loads that another follows at
    once (the title's art, the script's back-to-back OP_LOADs, the cutscene room before its sprites; the duel's first
    piece), so a chain pays one spin-up; a load without it stops the motor (no spinning while the title plays);
  - retries: 6 tries, after a failed one a restore, ~0.3 s (4 x 60 ms more after the restore's 60 ms) and the seek
    again; a bad disk ends in DISK ERROR after about 6 x (0.3 s + a turn or the 5-turn RNF + the restore and the seek
    back): ~2 s in the emulator (tests/m5_floppy.py), up to ~10-15 s on a drive for a far track;
  - fd_cmd's not-busy wait: 65536 polls ~130 us apart (~9 s; the ROM waits ~6 s, E568h, 7 x 65536 polls); it was
    0.9 s, shorter than a seek or restore of 30 cylinders or more at 30 ms a step (pv_scene, the ending and the duel
    lie on cylinders 27-34; PRES's loads seek to the directory on cylinder 0 first), which left the FDC busy and the
    next command ignored;
  - fd_go waits for BUSY with 256 polls (~2 ms after the ~110 us delay) instead of 65536 (BUSY sets within
    microseconds; it only has to tell a command that did not start).
- Step and settle timing: the seek 1Bh (head load, no verify, r = 30 ms at the WD2793's 1 MHz clock) and the restore
  0Bh step at 30 ms; PC drives take 3 ms or more, so stepping is well within spec, not a cause. Every seek is followed
  by fd_type1's ~60 ms delay, longer than a PC drive's head settle (~15-18 ms) and the WD's own 15 ms E delay, so the
  reads without the settle delay (fd_read_rot's 90h and READ ADDRESS C0h) only ever run on a cylinder the head has
  been on for at least 60 ms: kept. READ ADDRESS's ID order is only used to pick the first sector to read; any value
  reads the whole run correctly (it costs at most one more turn). The force interrupt D8h after the last wanted
  sector is the ROM's; INTRQ is polled, not wired to an interrupt, so its latched interrupt does not matter.
- The reference driver https://www.ordoz.com/sharp/fddrv/ (M. Hucik, fddrv 0.3, 2012, Z80/SDCC; read only, nothing
  of it copied): a motor counter (IM2 calls it, the motor stops 128 calls after the last access) and a 500 ms
  spin-up wait only when the counter says the motor was stopped; no READY check at all; read/write tries 5, after a
  failure a READ ADDRESS check of the track and, if that fails, a restore by single step-out commands to TRK00;
  stepping 6 ms (r = 00) with a 6 ms software delay per step and a 6 ms settle; on a BUSY timeout it sends Force
  Interrupt (D0h) until the FDC answers. Adopted: the idea of a spin-up wait only after a real motor start (our
  fd_on record), with the ROM's longer ~1 s rather than its 500 ms (a drive we have not measured; the cost is paid
  once per load chain), not relying on READY, and more tries with a recalibration between them. Not adopted: the
  interrupt-driven motor-off timer (the launcher has no interrupt of its own; PRS_KEEP chains and launch_main's motor
  off do the same job), the 6 ms step rate (30 ms is the ROM's and safe on every drive; the seeks are not the
  bottleneck), the step-by-step seeks and the D0h force interrupt (our fd_cmd now waits long enough that a command
  never stays busy; only a dead FDC would, and then DISK ERROR follows).
- Writing the disk: `gw write --drive A pop800.dsk` wrote and verified all 40 cylinders once the lengths were right
  (the user's command line: gw 0.34 on Windows, a PC 3.5" drive; the Greaseweazle on COM6: `--device COM6`).
- **The remaining DISK ERROR: the MZPico floppy controller's read window.** With the spin-up fix the user still saw
  DISK ERROR now and then, on two different floppies, always in the same call. The machine's floppy controller is the
  user's own work-in-progress MZPico floppy board (firmware ~/src/MZPico-floppy-firmware, a7fbb6f), which emulates the
  WD for the MZ-800 bus and decodes the drive's flux in software; it also speaks the Greaseweazle protocol (the "gw" on
  COM6: gw's write, verify and rpm went through the same firmware). The diagnostic build (`make diag`) showed: the
  launcher's directory read (logical track 1 = cylinder 0, head 0, sectors 1-8, read multiple 94h, PRS entry 0), the
  WD sector register 03 with 3 sectors taken, status 08 (data CRC) on 5 tries and 10 (record not found) on one, the
  head on cylinder 0 (track register 00), 512 KB at 0 WS; the boot had read the same sector moments earlier. The
  sectors 2-8 of that track hold the same bytes (empty directory blocks), so it is no data pattern.
  - The cause (read in the firmware, not changed): a read command captures one flux window and decodes the wanted
    sectors from it (a read multiple reuses it; no index sync). The window is sized in flux transitions,
    `FDC_READ_CAPTURE_BYTES_DD = 45700` (src/bus/fdc.cpp:1190), "~1.05 revolutions" for a measured ~43.5k transitions
    a revolution. MFM has 8 transitions in a byte of FFh or 00h: the directory track, almost all FFh, has ~46,450 a
    revolution (gw's layout, gap3 63), so the window covers 0.984 of a turn; 3 ms of every revolution is never
    captured, and the sector in that hole decodes truncated: CRC error (or record not found). Which sector depends on
    the rotational phase at the capture, so it is intermittent; retries at a similar phase fail alike. Our compressed
    data tracks have 39-42k transitions (1.09-1.17 turns): unaffected. The firmware fix (a window of at least one turn
    plus a sector for the densest data) is the user's.
  - The game now sidesteps it: the boot's dir_read and save.asm's sv_find read only the directory's first block
    (sector 1: its 8 entries hold every file looked up, tools/mkgamedisk.py check_lookups fails the build otherwise),
    and LN_PRS_LOAD no longer reads the directory or POP800.PRS's index block: the boot's stream writes the table of the
    entries' absolute blocks into the RAM disk (launch.inc PRS_TAB_RD_ADDR, page 0 0xFB00, in the launcher's area;
    tools/mkgamedisk.py prs_table), and the launcher reads its 4 bytes from there. After the boot nothing reads the
    directory track again (but a save or Ctrl+L: one sector).
  - The READ ADDRESS bytes the diagnostic build showed (7B C9 EA 8F EC 83, and 7B C9 EA 8F FC 80 on the second disk)
    are no ID field in any byte order and no valid CRC; they were written at runtime (not the image's leftovers, not on
    the disk), so the firmware delivered six bytes that are not a decoded ID (it hands over only CRC-valid IDs). The
    loader treats any READ ADDRESS trouble as a reason for the plain read, so loads are unaffected. The real WD's ID
    byte order is still to be seen.
  - Media: the drive turns at 298.9 rpm (`gw rpm`, -0.37 %); both floppies were HD media with the density hole taped.
    Not the cause (two disks failed identically), but 2DD / 720 KB media are the safer choice.
- Seeks per load (mz800emu trace, the title and the story, 512 KB). Before: every LN_PRS_LOAD went to the directory
  (cylinder 0) and to POP800.PRS's index block (cylinder 18) before the entry's data (e.g. PRS_T_MAIN: 19 -> 0,
  0 -> 18, 18 -> 19, 19 -> 20, 20 -> 21): ~1.5-2.5 s a load on a drive (30 ms a step + 60 ms a seek, two reads). Now:
  one move to the entry's first cylinder, then one step a cylinder of data (PRS_T_MAIN: 19 -> 19, 19 -> 20, 20 -> 21).
  fd_init's fd_cyl FFh only makes the next fd_pos issue a seek (the WD steps from its own track register); restores
  happen only after a failed try.

## PSG findings (M7 step 3, 2026-10-30, src/m4/psg.asm, tools/sndsim.py, tests/m7_sound.py)
- mz800emu's SN76489 (src/emulator/hw-generic/psg/psg.c): clocked at CPU/16 (221.7 kHz); a tone channel toggles every N
  steps (f = CPU / (32 N); N < 2 = a constant level, silent). A latch byte for a tone channel only stores the low 4 bits:
  the divider changes with the data byte that follows (the real chip applies the low bits at once; the player always
  writes latch + data pairs, so both behave the same). Noise: a 16-bit LFSR from 1 << 15, white = feedback bit 0 XOR
  bit 3, periodic = rotate (one pulse in 16 shifts), reset only when the noise type changes (the real chip resets it at
  every noise-register write: the player writes the noise register only when it changes). Shift every 16/32/64 steps
  (13.9 / 6.9 / 3.5 kHz) or every channel-2 period (rate 3). Periodic noise clocked by channel 2 = a pulse at
  CPU / (256 N2): 13.5 Hz-13.9 kHz, the player's voice for the speaker's notes below 108 Hz (footstep 61 Hz, bump 49 Hz,
  the level door 31-39 Hz). [To check on hardware: the LFSR length (15 or 16 bits) changes that pitch by 1/16.]
- A channel whose attenuation is 15 does not advance in the emulator (no phase); irrelevant for the register state.
- Every PSG write waits for the chip: mz800emu (mzarch.c INSIDEOP_IORQ_PSG_WRITE, "measured with an analyzer") adds
  16 + (4..19) wait T, the second part syncing to the PSG's clock (the absolute CPU cycle count mod 16): an OUT to F2h
  costs ~31-46 T, a byte of OTIR ~41-56 T. So the MZ-800 routes the SN76489's READY to /WAIT and OTIR is safe; the
  player's cost figures (docs/perf.md) include these waits. Side effect: code that writes the PSG has a timing that
  depends on the absolute cycle phase, so two runs that start at different cycles drift by a raster line (tests/m5_boot.py
  leaves pend_flush's beam scratch out of its comparison).
- MCP: `get_periph_sn76489` gives per channel the attenuation, tone divider, noise rate (div_16 / div_32 / div_64 /
  tone2_controlled) and type (periodic / white). Every pipe command costs ~20 ms of wall time (a stop at a breakpoint
  ~80 ms), so a frame-by-frame comparison samples only where the program writes the PSG (tests/m7_sound.py).
- SDLPoP records its own audio with SDL_AUDIODRIVER=disk (SDL_DISKAUDIOFILE: raw S16 stereo 44.1 kHz, real time:
  a 320-tick script takes 26.5 s); tools/sndsim.py --sdlpop.
