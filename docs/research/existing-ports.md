# Existing Prince of Persia ports — what they did and what is reusable

## Z80 ports with public source
- **ZX Spectrum 128K, Sergey Potapov, 2026** — https://github.com/PotapovSergey77/POP_Spectrum_128K (branch `zx-spectrum-port`; `zx-spectrum-disk` adds a TR-DOS disk loader). Z80 assembly for pasmo, 22,250 lines: pop.asm 8314 (main loop, view/room, input, kid control, sequences, CHECKBARR, flames, crop, falling, grabbing, frames, draw, walls, erase, show, clock, slicers), fight.asm 2965 (AUTO.S + fighting half of CTRL.S), lvcode.asm 1970 (per-level special code), roomblk.asm 1817 (room composition from BGDATA tables, torches), bg.asm 4512 (FRAMEADV RedBlockSure + passes, pieces laid in Apple's 40-byte/7-px canvas layout then repacked), cutplay/cut1 (princess scenes), intro, tapeldr, ctlmenu. Logic ported "routine by routine" from the Apple II source. ~50 Python tools (popimg/poplevel/popseq/popframe/bgexport/mkassets/maketap/maketrd, a mos6502.py + z80.py for cross-checking traces, timing.py, frameprof.py). Game tick = 3 x 50 Hz periods (16.7 fps) on a 3.5 MHz Z80 with 1-bpp sprites stored byte aligned as (mask,data) pairs shifted at draw time; off-screen working copy of the room; only the changed rectangle copied to screen; 128K banks: art, spr1-3, bg, spare, canvas. Rights: fan port, no licence file beyond Mechner's note.
- No other Z80 PoP source is public (SAM Coupé 1991 Chris White — hand re-implementation from Amiga; Spectrum 1996 Nicodim; SMS 1992; MSX2 David Heremans 2026 in progress; CPC 1990 official).

## 6502 ports with public source
- **BBC Master 128, Kieran Connell / Bitshifters 2018** — https://github.com/kieranhj/pop-beeb . Kept Apple II code and 140x192 logical coordinates, replaced HIRES.S only. MODE 2 160x200 16-colour, double buffered via shadow RAM, 12.5 Hz tick (every 4th frame), sprites kept 1-bpp and shifted via tables, 4 x 16K sideways RAM for art, per-level loading from a 200 KB disc. Notes: Notes/pop notes.txt in the repo; write-up https://bitshifters.github.io/posts/prods/bs-pop-beeb.html
- **C64 open re-port, ulasb 2025-26** — https://github.com/ulasb/PrinceOfPersiaC64 (+ PrinceOfPersiaPy spec): SEQTABLE bytecode interpreter, FRAMEDEF and 2304-byte levels used verbatim; masked 2-bpp software blitter with shift tables; mask derived from pixel data via a 256-byte table; save-under buffer.
- C64 Mr. SID 2011 (closed): bitmap mode, software-drawn kid, double buffered, EasyFlash cart as RAM; blog https://popc64.blogspot.com/
- Atari XL/XE 2021 (closed, from the BBC port, 128K), Plus/4 2024, VIC-20 2024.

## Lessons shared by all faithful ports
- Keep Mechner's data verbatim (SEQTABLE, FRAMEDEF, BGDATA piece tables, levels); rewrite only control-flow glue and the whole render/IO layer.
- ~128 KB total is the practical floor: kid sprites ~30 KB (1-bpp), backgrounds ~14 KB, guard set ~9 KB, code ~48 KB, plus frame buffers; per-level loading from disk is universal.
- Game rate 12-16 fps; copy only the changed rectangle; save-under for characters.
