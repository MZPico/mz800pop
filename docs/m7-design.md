# M7 design study: presentation and sound (2026-10-30)

Status: proposal. No code was changed for it. The sources are SDLPoP (external/SDLPoP/src, run with fixes off),
the DOS v1.3 data (external/dos, never redistributed), our build (build/assets, build/m4game.sym), docs/memory.md,
docs/perf.md and mz800emu (~/src/mz800emu). Line numbers refer to the local SDLPoP copy. "Tick" means a game tick
unless it says "SDLPoP tick": SDLPoP's timer runs at 60 Hz, a game frame is 5 of them (12/s) or 6 in fights (10/s),
and a cutscene frame is `cutscene_frame_time` of them (6, 7 or 8).

## 0. Summary

- **Presentation.** Build a separate program, PRES. A small launcher swaps it with the game in main RAM. Nothing of
  the game is saved: the state between levels is about 8 bytes. The launcher restores a pristine, compressed copy of
  the game image from the RAM disk and passes those bytes in a handoff block.
  - PRES reuses the M1 kernel sources (gfx.asm, far.asm, the sprite code) by including them.
  - Level cutscenes use the PV art kept in the RAM disk, about 23 KB compressed.
  - The title art (about 37-48 KB compressed) and the intro-only Jaffar set are read from the floppy whenever the
    title runs. Music is silent while the floppy reads.
- **Sound.** Add a 50 Hz PSG player to the existing VBLN interrupt.
  - About 1.2 K T a frame (about 1.7% of the CPU), roughly 350 bytes of code in block 2, and 400 bytes of buffers in
    reclaimed RAM: the IM2 table and free low RAM.
  - Effects are re-made per 50 Hz frame from the DOS PC-speaker data. Music is arranged for 3 voices (plus the 8253
    as an optional bass voice) from the MIDI data.
  - The game logic sees sound through one deterministic model. A "silent" harness mode keeps every existing oracle
    test as it is.
- **Keys.** BREAK pauses the game. SPACE goes back to "show the time", as in the original, so the button is SHIFT and
  the joystick fire. Cheats are a W1 overlay assembled only with `CHEATS=1`.
- **Effort.** About 7.5 weeks part time as listed in §7, or 5-6 without the Hall of Fame and the 8253 voice. The
  plan has 3 weeks. The largest parts are the cutscene engine and the music arrangement.
- **Decisions.** Section 8 lists the 9 decisions needed from you.

## 1. What the original does

### 1.1 Flow

```
boot -> show_title (intro, pv_scene, story screens) -> demo level 0 -> show_title ...   (any key: level 1; Ctrl+L: saved level)
level n done -> [cutscene tbl_cutscenes[n+1]] -> level n+1           (cutscenes before levels 2, 4, 6, 8, 9, 12)
death -> "Press Button to Continue" 288 frames -> title (no separate game-over screen)
rem_min == 0 on levels 1-12 -> time_expired scene (cannot be skipped) -> title
level 14, room 5 -> end_sequence (embrace scene, "hail" text, logo, Hall of Fame) -> title
```

- `play_level` (seg003.c:57) runs a cutscene only when `level_number != current_level`. A restart (Ctrl+A or death)
  shows none. A restored game (Ctrl+L to level 4) shows that level's cutscene.
- The level 6 -> 7 fall exit and the seamless 12 -> 13 start show no cutscene, because tbl_cutscenes[7] and [13] are
  NULL.

### 1.2 Title and intro: `show_title` (seg000.c:1946)

Art comes from TITLE.DAT. Times are in SDLPoP ticks; ×5/6 gives 50 Hz frames.

| Step | Shows | Wait | Sound |
|---|---|---|---|
| a | TITLE_MAIN res51 (320x200) | 130 | 54 intro_theme starts |
| b | + "Broderbund Software presents" res52 at (96,106) | 205 | |
| c | cleared | 65 | |
| d | "a game by Jordan Mechner" res53 at (96,122) | 270 | |
| e | cleared | 235 | |
| f | logo res54 at (24,107), transparent, + copyright res55 at (48,184) | until 54 ends (24.3 s MIDI) | |
| g | STORY_FRAME res41 + text res42 "In the Sultan's absence..." | 600 | 55 story_1_absence |
| h | `pv_scene` (§1.3) | about 35 s | 50, 4, 51, 53, 52 |
| i | frame + res43 "Marry Jaffar..." | until 52 ends | |
| j | main + logo + copyright | 120 | |
| k | frame + credits res45 (the EGA version credits Leila Joslyn and Michael Barrett) | 360 | |
| l | only if the Hall of Fame has entries: frame + logo + `show_hof` | 240 | |
| m | the demo: `init_game(0)` | | |

- **Screen changes.** Steps g and j-l use `transition_ltr` (seg000.c:2048): a left-to-right wipe in 2-px columns,
  160 steps in about 1.33 s. Steps a-f blit `rect_titles` {106,24,195,296}.
- **Fades.** fade_in_2 / fade_out_2 exist only on VGA. Every EGA branch in SDLPoP is an empty `// ...`, so the EGA
  behaviour has to be checked in DOSBox (`build/dosbox/pop.conf` already sets `machine=ega`). It is most likely an
  instant blit.
- **Story texts** (res42-45) are 1-bpp bitmaps drawn in colour 15 into the 4-bpp frame res41. No font is involved.
- **Demo.** `do_demo` (seg006.c:1473) plays level 0 from LEVELS.DAT.
  - It uses the 25-pair `demo_moves` table (data.h:865).
  - After the kid kills the guard it sets `checkpoint`, and the kid then runs right. The guard uses
    `autocontrol_opponent` at skill 10.
  - The demo ends when the kid enters room 24 (seg000.c:886) or dies (36 frames later). Both go back to the title,
    so the demo has no fixed length.
- **Keys on the title and in the demo.**
  - Any key or SHIFT starts level 1.
  - Ctrl+L runs `load_game`; on failure the title continues.
  - Ctrl+Q quits. Ctrl+R returns to the title from anywhere. Ctrl+S toggles sound.
  - The original shows no "press button" text on the title.
  - `show_quotes` (press quotes in the font) runs only in the `demo` kiosk mode, and `show_splash` is SDLPoP-only.
    Both are out of scope.

### 1.3 Cutscenes (seg001.c)

**`load_intro(which_imgs, func)`** (seg001.c:658) sets up the room, then calls the scene function.
- **Room.** PV res951 (320x200) with the bed res981 (240x41) ORed in at (0,142).
- **Foreground.** Pillar res952 at xh 30.
- **Torches.** PRINCE.DAT flames at xh 11/26, ybottom 116.
- **Stars.** 6 one-pixel stars at (20,97)...(18,128). On odd frames one of the first five cycles colour {8,7,15,15,7}.
- **Sprites.** The princess slot ("opp") uses `frame_tbl_cuts` (seg006.c:417). Frames 1-18 come from PV res801-817
  (princess, PV1). Frames 19 and up come from chtab 4: res851-888 (Jaffar) when `which_imgs=0`, res901-930 (princess,
  PV2) when it is 1.
- **Second slot.** The "kid" slot plays Jaffar, the mouse or the kid. The mouse uses kid frames 186-188, and the
  ending uses the kid's own frames. Both come from the kid pack, which is already in the RAM disk.
- **Hourglass.**
  - The glass is res953-959 (states 1-7, 19x28, 7 = empty) at xh 19, ybottom 168.
  - The sand stream is res960-962 (2x8), cycling 0-2 each frame.
  - `hourglass_frame()` = 6 − (index of the first of {6,17,33,65} greater than rem_min). That gives state 3 at the
    normal 33-64 minutes, 4 at 17-32, 5 at 6-16 and 6 below 6 minutes.
- **Frame engine.** `proc_cutscene_frame(n)` advances both sequences (sequence table entries 94-114), redraws the
  dirty rectangles and starts a queued sound only when none is playing.
- **Keys.** A key aborts the scene, except when `disable_keys` is set (time_expired, the ending).

| Before | Function | Music | Content (frames of 6 ticks) |
|---|---|---|---|
| intro | `pv_scene` | 50, 53, 52; effects 4 and 51 | Princess standing; Jaffar enters, conjures (white flash 5 frames, hourglass appears), leaves (sand starts); princess slumps. 19 steps; frame time 6, then 8, then 7; three "until the music ends" loops |
| 2, 6 | `cutscene_2_6` | 27 (12.0 s) | Princess standing at x=120, hourglass = hourglass_frame(); 26 frames |
| 4 | `cutscene_4` | 27 | Princess lying (Plie) at x=92, y=162; 26 frames |
| 8 | `cutscene_8` | 35 (10.3 s) | Mouse and princess crouching; mouse leaves; princess rises: 20 + 20 + 20 frames |
| 9 | `cutscene_9` | 35 | Mouse scurries in, princess crouches, mouse stands up: 5 + 9 + 58 frames |
| 12 | `cutscene_12` | 40 (6.9 s) | Only if rem_min < 6: princess alerted, hourglass 6, 2 + 24 frames; otherwise cutscene_2_6 |
| time out | `time_expired` | 36 (14.5 s) | Room only, empty glass (res959): 2 + 100 frames, then waits for the music |
| end | `end_sequence_anim` | 26 (14.0 s) | Princess waits, kid runs in, embrace, mouse climbs: 104 frames, no fade-in |

Every scene except the ending fades in and fades out (VGA, about 128 SDLPoP ticks each).

### 1.4 Death, time-out and ending

- **Death** (seg006.c:1362).
  - The death music: 24 regular, 28 in a fight, 32 killed by the shadow.
  - Then "Press Button to Continue" for 288 frames. The text blinks in the last 72 frames with sound 38.
  - Enter or SHIFT acts as Ctrl+A.
  - When the text runs out, the game returns to the title.
  - Our port already draws the text. It goes back to level 1 instead of the title (GAME_OVER in game.asm).
- **Bottom texts** (already ported): LEVEL n, n MINUTES LEFT, SECONDS LEFT, TIME HAS EXPIRED!, GAME SAVED.
  "GAME PAUSED" is the one still missing.
- **Ending** (`end_sequence`, seg001.c:573):
  1. The embrace scene.
  2. Music 56 (ending, 124.7 s) starts with STORY_FRAME + res44 "The tyrant Jaffar lies dead...", shown for 900 ticks.
  3. TITLE_MAIN via the wipe, 240 ticks.
  4. The Hall of Fame, only if the time is in the top 6: font text, a typed name of up to 24 characters, written to
     PRINCE.HOF.
  5. It waits for the music, then returns to the title.

### 1.5 Art and what our packs already hold

All presentation art is already converted from the EGA DATs. The sizes below are for the current pack format
(mask + 4 planes, `5 × wbytes × h`); PZ is tools/pzpack.py in 16 KB blocks, measured.

| Group | Images | Raw | PZ | Needed by |
|---|---|---|---|---|
| title.pack res41 frame | 1 | 40,000 | 3,001 | story screens |
| title.pack res42-45 story texts (1 bpp in the DAT) | 4 | 92,045 | 18,735 | intro, ending |
| title.pack res51 main background | 1 | 40,000 | 19,703 | title, ending |
| title.pack res52-55 | 4 | 18,750 | 6,955 | title |
| pv.pack res801-817 princess PV1 | 17 | 11,775 | 2,789 | all scenes |
| pv.pack res851-888 Jaffar | 38 | 31,385 | 6,698 | intro only |
| pv.pack res901-930 princess PV2 | 30 | 18,385 | 5,417 | levels 4-12, ending |
| pv.pack res951-962, 981: room, pillar, hourglass, sand, bed | 13 | 49,690 | 14,387 | all scenes |
| font.pack (SDLPoP font, 0x21-0x83) | | 3,595 | ~1,100 | HOF, GAME PAUSED |

- **Smaller title pack.** Stored as 1-bpp bitmaps drawn with WF PSET colour 15 (one byte write fills all four planes),
  the story texts shrink to about 18.4 KB raw and an estimated 6-8 KB PZ. The two full-screen images need no mask
  (32,000 bytes each). With both changes the title set is about 37 KB PZ instead of 48 KB.
- **Already resident.** The cutscenes also need the kid pack (mouse and ending frames) and the flame images
  (objects pack). Both are already in the RAM disk.

## 2. Sound in the original

### 2.1 Ids, formats, rules

SDLPoP has 57 sound ids (types.h:698-754); ids 31, 34 and 42 are unused.

| Kind | Ids | Count |
|---|---|---|
| Effects | 0-23, 38, 44-49, 51 | 32 |
| Music | 24-30, 32, 33, 35-37, 39-41, 43, 50, 52-56 | 22 |

**Formats.**
- SDLPoP plays OGG (if files exist), digitized sound (DIGISND1-3), MIDI through its OPL3 emulation (MIDISND1/2), or
  the PC speaker (IBM_SND1/2).
- Our oracle (tools/oracle.py: SDL dummy audio, sound on) plays digitized effects and MIDI music in real time. The
  dummy driver consumes audio at wall-clock speed.

**PC-speaker format** (decoded; all 57 resources match SDLPoP's .bin files):
- `u8 type=0`, `u16 tempo` (length units per second), then `{u16 freq_Hz; u8 length}*`, ended by `u16 0x0012`.
- A frequency of 0 or 1 is a rest.
- Effect tempos are 288-576 units/s, so a note lasts 2-3.5 ms. Effects are rapid sweeps or noise made of many tiny
  notes.
- Music is monophonic, tempo 28-260.
- The 5 effects falling, sword_moving, draw_sword and loose_shake 1-3 have no speaker data, so DOS stays silent for
  them on the speaker.

**Sizes and lengths.**
- The speaker resources total 6.9 KB: effects 2.4 KB, music 4.5 KB, of which the ending is 1.8 KB.
- Notable lengths (speaker / MIDI): drink 1.46 s; feather (39) 18.6 / 18.7 s; level end (41) 11.3 / 12.75 s; death
  3.0 / 3.6 s; death in a fight 6.5 / 7.2 s; intro 24.7 / 24.3 s; ending 120 / 125 s.
- The decoder is in the session scratchpad (`pcspk_decode.py`). The M7 converter will move into tools/.

**Queue and priority** (seg000.c:1626-1648):
- `play_sound` only sets `next_sound`. The queued sound is replaced only by one of equal or higher priority (a lower
  table value).
- `play_next_sound` runs once per frame (draw_game_frame:956). It starts the queued sound if nothing plays, or if the
  current sound is interruptible and the new one has equal or higher priority. Otherwise the request is dropped.
- All music and the effects 0, 6, 14, 15, 18 and 44-51 are not interruptible, so **no effect starts while music
  plays**.
- `stop_sounds` is called by restarts, potions, feather fall, the level door fully open and level changes.

**Call sites.** The logic has about 40 `play_sound` call sites, in seg002-seg008, plus the cutscene and title sites in
seg001 and seg000.

### 2.2 Where the logic waits on sound, and what our port does

| Wait | SDLPoP (real time) | Port today (kidsim, src/m4) |
|---|---|---|
| Death timer (seg006.c:1362) | `alive` stops counting while any sound plays (except 5). It freezes at 7 until the death music ends (3.6 / 7.2 s), then shows "Press Button". Restart is possible from 7. | Counts every tick (blocked only by FEATHER_MUSIC). Text at once. The oracle suite compares only the sign of `alive` after death. |
| Level end (seg003.c:389) | The level changes when no sound plays: 12.75 s of end music (shadow music 7.25 s on level 4). The clock keeps running, which costs about 153 ticks of game time. | game.asm loads the next level at once (= SDLPoP with sound off). kidsim keeps the level, so the stairs are not oracle-compared. |
| Level 1 crouch (seg005.c:314) | Controls are locked until music 25 ends (about 2.5 s). | Absent. The oracle hook forces `need_level1_music=0` (pop800_trace.c:81). |
| Feather fall (seg003.c:517) | Ends when no sound plays or `is_feather_fall > 225`. The 18.67 s MIDI is a race of about 1 tick against the cap. Any stop_sounds ends it early. | FEATHER_MUSIC flag (objects.asm:51; events.asm; kid.asm:2563; guard.asm:726): ends at 226 or on stop_sounds. |
| Cutscene and title loops | "until the music ends": the number of cutscene frames depends on the music length. | n/a |
| RNG | `loose_shake` draws differently only with sfDigi (seg007.c:887). | Modelled as sfDigi (objects.asm:640). Keep it whatever the MZ audio does. |

## 3. MZ-800 sound hardware

**PSG: SN76489 at port F2h** (write only).
- Clock: CPU 3,546,895 Hz; mz800emu feeds the chip CPU/16.
- Tone: f = 3,546,895 / (32 N), with N a 10-bit value from 1 to 1023. The lowest tone is **108.3 Hz**.
- Commands:
  - latch byte `1 cc t dddd` (channel cc; t=0 tone low 4 bits, t=1 attenuation in 2 dB steps, 15 = off);
  - data byte `0 x dddddd` (tone high 6 bits).
- Noise: `1 11 0 x f rr`. f=1 is white noise, f=0 periodic. rr selects 6.93, 3.46 or 1.73 kHz, or channel 2's tone.
- Bass trick: periodic noise driven by channel 2 gives tone2/15 (or /16, depending on the chip's LFSR; check on
  hardware). That reaches far below 108 Hz at the cost of voice 2.
- No envelopes: volume is set per frame in software.

**8253 beeper ("MZ-700 sound").**
- Counter 0 is clocked at 1,108,404 Hz; mode 3 gives a square wave.
- The 16-bit divider reaches down to 17 Hz.
- 8255 PC0 gates it (bit set/reset via port D3h). Volume is fixed.
- Our game uses counter 1 (the HSYNC line counter) and masks counter 2's interrupt, so counter 0 is free.
- The MZ-800 mixes it with the PSG: a 4th, square-only voice for the notes below 108 Hz. The mixing level must be
  checked on the real machine.

**Interrupt.** The 50 Hz VBLN interrupt (game.asm `isr`, IM2, PIO vector 0, fires at line 245) is the player's clock.
The driver must respect four constraints:
1. **Never touch the RAM disk.** Main code streams E9h/EAh/EBh with interrupts enabled, and the MZ-1R18 address
   cannot be read back. All data the ISR reads must already be in main RAM.
2. **Placement.** The ISR runs inside `blit`, where 0x1000-0x1FFF is the CG ROM and 0x8000-0x9FFF is VRAM. The ISR's
   code and data must be outside both, so the renderer-list reclaims at 0x9000 cannot hold sound data.
3. **Silence before disk access.** Floppy reads (loader, save, title art) run with DI for whole tracks, because a byte
   is due every 32 µs. The PSG must be silenced first, or a tone hangs.
4. **Cost.** Writing 3 tones + noise + 4 volumes takes 11 OUTs, about 150 T. With note stepping for 2 voices plus
   effects, the ISR grows by about 0.8-1.5 K T a frame. At 5.98 frames a tick that is about 7 K T per tick (+0.1
   frame, under 2%), which is inside `make perf`'s 5% guard once the baseline is updated. The ISR's latency at line
   245 delays the start of a copy chunk by at most about 6 lines; the beam-timed scheduler reads the beam after the
   ISR, so it stays correct.

## 4. Proposal: how the presentation runs

### 4.1 Architecture: a separate program, swapped by a launcher

Three ways were weighed:

| | A. Separate PRES program, game image restored from the RAM disk | B. Large overlays inside the running game | C. Reload the game from floppy after each scene |
|---|---|---|---|
| Main RAM for PRES | about 50 KB (everything but the launcher) | 8 KB at 0xA000-0xBFFF, but the cutscene sprites need the same compose buffers | about 50 KB |
| Level change | +0.5 s (image restore) + scene | + scene | +3-5 s of floppy reads |
| RAM disk | about 20 KB (game image, PZ) + about 6 KB (PRES, PZ) | about 10 KB | about 6 KB |
| Risk | low: the boot path already does it | high: no room, kernel conflicts | slow, and music must stop |

**Recommendation: A.**
- **What survives a level change.** Between levels the game needs only level_number, REM_MIN, REM_TICK, HITP_BEG_LEV
  and an options byte. Everything else is rebuilt by `start` (tables_init, irq_init, game_init, load_level, the first
  full room draw). The shadow room (page 1, 32,000 B) and the torch cache (page 6, 10 KB) are scratch that PRES may
  use freely.
- **Launcher.** It is a RAM-disk variant of src/boot/boot.asm. It runs at 0xB000, outside both images, as the boot
  loader already does. It reads record streams (the mkgamedisk.py record format, PZ decoder already written) from the
  RAM disk instead of the floppy, writes them to main RAM and jumps.
- **Two streams in the RAM disk:**
  - `GAME`: the program records exactly as the floppy holds them: 0x1200-0x7FFF and 0xC000-block2_end, 38.5 KB raw,
    about 20 KB PZ.
  - `PRES`: the presentation program, estimated 10-13 KB raw, about 6 KB PZ.
- **Restore time.** About 20 KB read at 21 T/B plus decompression of 38.5 KB (to be measured; about 40 T/B expected)
  is about 1.9 M T, roughly 27 frames, half a second.
- **Handoff block.** 16 bytes in RAM-disk page 5 at 0x3AC0 (free):

  | Field | Content |
  |---|---|
  | magic | |
  | action | title / cutscene before level n / time expired / ending / play level n / demo |
  | level | |
  | rem_min, rem_tick | |
  | hitp_beg_lev | |
  | options | sound on, cheats |
  | result | the PRES -> game direction |

  Both programs read it at `start`. The game's `start` gains about 30 bytes: read the block and set the variables.
  It no longer always starts level 1.
- **Game side.** About 60 bytes, in the W2 level-start overlay (2.9 KB free), not resident:
  - before `load_level`, if tbl_cutscenes[next] and the level is not a restart: write the handoff, load the launcher,
    jump;
  - GAME_OVER (time out, the end of the death text): the same with action = title or time-expired;
  - level 14's END: the same with action = ending.
  - Only a call from game.asm's gmt0 path into the overlay is resident: about 8 bytes of the 173 free.
- **PRES** is its own pasmo assembly. It reuses gfx.asm, far.asm and the sprite blitter by `include`, plus fdc.asm
  for floppy reads and save.asm's read side for Ctrl+L. The main RAM is free from 0x1200 to 0xAFFF (and 0xC000
  upward), so it needs no overlays.

### 4.2 Where the art lives

| Item | Place | When loaded |
|---|---|---|
| PRES program (PZ ~6 KB) and GAME image (PZ ~20 KB) | RAM disk | written by the boot loader |
| Level cutscene art: PV1 princess, PV2, room set (PZ 22.6 KB) | RAM disk | written by the boot loader |
| In-game sound data (effects + 11 music pieces, about 3-4 KB) | RAM disk | written by the boot loader |
| Title art (about 37 KB PZ after the 1-bpp change), Jaffar set (6.7 KB), presentation music (about 10-20 KB PZ) | floppy file POP800.PRS | every time the title, intro or ending runs: about 55-65 KB, 14-16 tracks, an estimated 4-5 s on a real drive, silently, with the progress bar |

- **RAM-disk space.**
  - Free today: about 61 KB, in pieces: page 0 6 KB, page 1 9.6 KB, page 3's tail 21.7 KB, page 4 9.9 KB, page 5
    about 2.3 KB, page 6 1.5 KB, page 7 9.7 KB.
  - Plan: 6 + 20 + 22.6 + 4 = about 53 KB. PZ records are independent blocks of up to 16 KB, so they can be split
    across the pieces. That leaves about 8 KB.
  - The visited-room cache (M8a item 2) cannot then share these pages. It would need the per-level guard-set loading
    (about 90 KB freed), which is a separate decision.
- **Boot.**
  - About +32 KB of floppy reads, an estimated +4-5 s on a real drive. The GAME records already exist; they are
    copied as stored payload.
  - The boot then starts PRES instead of the game.
  - Alternative: load the cutscene art per scene from floppy instead (about 2 s per cutscene, frees 23 KB).
- **Disk.** 1280 blocks, files end at block 536, so about 190 KB are free. POP800.PRS takes about 65 KB.

### 4.3 PRES contents

- **Title.**
  - Full-screen images are decompressed into VRAM through the shadow layout in page 1: 32,000 B at about 21 T/B, about
    10 frames.
  - 1-bpp texts are drawn with WF PSET colour 15.
  - `transition_ltr` becomes 40 steps of 8-px columns over 1.33 s. Each step copies 800 B from the page-1 copy of the
    next screen.
  - Waits: SDLPoP ticks × 5/6 frames, kept in a 1/60 s accumulator so they add up exactly.
- **Cutscene engine.**
  - A port of `proc_cutscene_frame`: two slots driven by SDLPoP's sequence table (already in logic.bin, page 6) and
    `frame_tbl_cuts`.
  - A dirty-rectangle compositor over a background restore from the shadow copy: the game's sprite path.
  - Plus torches, stars, hourglass and sand.
  - Scenes are small bytecode scripts (place, seq, frames n, until-music, sound, hourglass, flash, fade), one per
    `pv_scene` / `cutscene_*` / `time_expired` / `end_sequence_anim`.
- **Cutscene speed.**
  - A frame of 6 SDLPoP ticks is exactly 5 MZ frames. 7 and 8 ticks become 5.83 and 6.67 frames, through the
    accumulator.
  - Cost: two characters about 2-3 frames (they are smaller than the kid), torches about 2.2 and stars nothing, so it
    fits in 5.
  - If a frame runs late, its drawing is skipped. Logic frames never are, so the frame counts stay exact.
- **Fades.** The MZ-800 can remap only 4 palette entries, so there is no real fade. Recommendation: verify the EGA
  original in DOSBox. If it is instant (likely), we match it. If not, use a black cut, or a 4-entry dim of the
  colour-0-3 group where the images allow it. The white flash in `pv_scene` uses the palette-register flash that
  already exists (M5).
- **Ctrl+L.** On the title or in the demo, PRES reads POP800.SAV (save.asm `load_saved` logic). Then it plays that
  level's cutscene, if it has one, and launches the game with the handoff.
- **Demo (attract mode).**
  - It runs in the game: action = demo, level 0.
  - Game side: `do_demo` (about 60 B in the events overlay, which has 375 B free, next to `do_auto_moves`), the 50-byte
    demo_moves table, and the room-24 / death exit to the title.
  - kidsim already has the level-0 checkpoint rule (`on_guard_killed`). It needs `do_demo` plus an oracle script that
    starts level 0 in demo mode.
- **Hall of Fame (optional, D7).** Needs font text, name entry, and a POP800.HOF block preallocated like POP800.SAV
  (writer: save.asm). About 1 KB of PRES code.

## 5. Proposal: sound

### 5.1 Driver and residency

**Resident player.** The VBLN `isr` calls `snd_frame` after its line latch. It plays:
- voice 0-2 + noise: one **effect** stream and one **music** stream;
- music uses up to 3 tones, plus the 8253 if enabled;
- effects use one tone and/or the noise channel, borrowed per frame from music voice 3 ("effect steals the top voice";
  the original never mixes, see §2.1);
- stream format: byte codes per 50 Hz frame step: set tone or noise, volume, wait n frames, end.

**Code and buffers.**

| Item | Size | Place |
|---|---|---|
| Player code | about 300 B | block 2 (929 B free) |
| Request side: `snd_play` with priority, interruptible and queue rules; `snd_next` once per tick; `snd_stop` | about 120 B | block 2 |
| Effect buffer | 128 B | 0x0148-0x01FF (184 B of free runtime RAM) |
| Music ring | 192 B | 0xFE02-0xFEFF |
| State | about 40 B | 0x03C1-0x03FF |

- The IM2 table can shrink to its one used vector (0xFE00-0xFE01): the PIO supplies vector 0, and the 8253 interrupt
  stays masked. That frees 254 B.
- **Call sites.** About 30 `play_sound` sites in resident logic at 5 B each (`ld a,id : call snd_play`), about 150 B,
  mostly in block 2 and the main code. The sites inside W1/W2 overlays cost overlay space only.
- **Total.** About 600 B of resident code and about 360 B of buffers. Free today: main 173 B, block 2 929 B, plus the
  IM2 reclaim. **That is sufficient. The op-list reclaim cannot help the ISR anyway (0x8000-0x9FFF), and it is still
  available for non-ISR code.**
- **Refill.** The main code refills the music ring from the RAM disk once a tick (`snd_fill`, never the ISR). A full
  room draw (about 106 frames) also calls it between cells, so the ring never starves. 192 B holds over 2 s of music
  even at the densest arrangement.
- **Effects** are copied whole into the effect buffer when `snd_next` starts them. The longest effect at 50 Hz is
  under 100 B.

### 5.2 Data

- **Effects.** Re-made, not played back: the DOS 2-3 ms notes cannot be played at 50 Hz.
  - tools/sndconv.py decodes IBM_SND1/2, reduces each 20 ms window to a dominant tone or "noise", and emits the frame
    stream.
  - A hand-tuned override table covers the sweep and crash effects (tile_crashing, chomped, spiked, gate_closing_fast,
    leveldoor_closing).
  - New PSG designs for the 5 effects that have no speaker data.
  - Size: an estimated 600-900 B in total.
- **Music.** tools/midi2psg.py converts the MIDISND1/2 resources (standard MIDI) to 3 voices.
  - It picks melody, counter-line and bass per piece, quantises to 50 Hz, and uses simple per-instrument decay tables.
  - Notes below 108 Hz move up an octave, or go to the 8253 voice or periodic noise (D5).
  - The fallback is the monophonic speaker tune (same data, one voice, already the right length).
  - The arranged length must equal the MIDI length, because waits and cutscene frame counts use it (§5.3).
- **Placement.** The in-game music (24, 25, 28-30, 32, 33, 37, 39, 41, 43; about 71 s) and the effects are in the RAM
  disk, about 3-4 KB. The presentation music (26, 27, 35, 36, 40, 50, 52-56; about 290 s, the ending alone 125 s)
  ships in POP800.PRS for PRES only.

### 5.3 Sound and the tick-exact logic

The logic gets one model with three modes:

| Mode | Behaviour | Use |
|---|---|---|
| silent | every sound has length 0 | the harness and every existing oracle test; the same as today |
| ticks | each sound has a length in game ticks: its MIDI length × the tick rate when it starts (12/s, or 10/s in a fight) | |
| live | `check_sound_playing` asks the player | |

`snd_play`, the queue and the priority rules run in every mode. They are deterministic and become a new oracle
comparison (§7).

**Recommended for the release:** a hybrid that keeps the logic deterministic where it affects play.

| Wait | Mode | Effect |
|---|---|---|
| Feather fall | ticks | ends at the 225 cap (in SDLPoP the 18.67 s music and the cap end within a tick of each other); on the MZ's slower ticks a live wait would cut it to about 157 ticks |
| Level-1 crouch | ticks | about 30 ticks |
| Death | live | it only delays the "Press Button" text; restart is possible during the music, as in the original |
| Level end | live | the screen waits for the music. The clock is charged the fixed SDLPoP cost of the piece (153 ticks for 41, 87 for 32), so the remaining time at the next level is exact. |
| Cutscene "until the music ends" | ticks | a fixed frame count per scene, taken from the oracle's hook log. PRES plays the music in parallel; with length-matched arrangements the two end together. |
| Title steps | live | wall-clock only |

kidsim gets the same model, so the Z80 code stays checked tick by tick in silent mode and in ticks mode.

## 6. Keys, pause, options, cheats

- **Original keys during play** (SDLPoP `process_key`, fixes off):

  | Key | Action |
  |---|---|
  | Esc | pause ("GAME PAUSED", any key resumes) |
  | Space | show the remaining time |
  | Ctrl+A | restart the level |
  | Ctrl+G | save (levels 3-13) |
  | Ctrl+R | back to the title |
  | Ctrl+S | sound on/off |
  | Ctrl+J / Ctrl+K | joystick / keyboard |
  | Ctrl+V | version |
  | Ctrl+Q | quit |
  | Shift+L | skip a level: levels 1-3 only; later it also caps the time at 15 minutes |
  | Enter or SHIFT while dead | Ctrl+A |

  Ctrl+A and Ctrl+G are ported. Everything else is new.
- **Port mapping.**
  - **Pause:** BREAK (keyboard column 8 bit 7; the emulator name is ESC/BREAK). The PSG is muted during the pause.
    "GAME PAUSED" is a new string in the W2 text overlay. About 40 B resident.
  - **SPACE:** today SPACE and SHIFT are both the button (game.asm get_controls `nd:`/`nb0:`). Recommendation (D6):
    SPACE = show time, as in the original, and the button = SHIFT or joystick fire. The `nd:` branch (6 B) moves to
    set IS_SHOW_TIME.
  - **Ctrl+R, Ctrl+S, Shift+L, Enter while dead:** about 60 B, reading the same keyboard matrix rows.
  - **Ctrl+J/K:** not needed, because joystick and keyboard are always both read.
  - **Ctrl+Q:** no meaning on the MZ. Map it to Ctrl+R.
  - **Ctrl+V:** the version as a bottom text, costing only the string.
  - No options menu (the original has none).
- **Cheats** (`cheats_enabled`, SDLPoP's "megahit"):
  - Shift+L at any level, K kill the guard, R revive, +/- time, Shift+T/Shift+S big/small potion, Shift+W feather,
    Shift+I flip, H/J/U/N view the neighbouring rooms, Ctrl+B back, Shift+B (blind), T timer display.
  - Assembled only with `CHEATS=1`: a W1 overlay `cheat_key`, called from get_controls on a key edge, about 0.5 KB.
    Resident cost: 0 B in the release, about 10 B with the flag.
  - The numeric-keypad +/- become the MZ-800 `+`/`-` keys or F1/F2.

## 7. Implementation plan

Effort is in part-time weeks.

1. **Handoff and launcher** (0.8 w).
   - boot.asm writes GAME/PRES/art/sound records to the RAM disk and starts PRES.
   - Launcher (RAM-disk stream reader, from boot.asm). Handoff block; `start` reads it. A stub PRES only launches
     level 1.
   - *Test:* tests/m5_boot.py extended: the RAM disk and main RAM after boot -> PRES -> game are byte-identical to the
     harness setup; the game is identical after 300 ticks. A round-trip test: game -> launcher -> game with a handoff
     for level 4 equals a direct level-4 start.
2. **Sound model in the logic** (0.7 w).
   - kidsim: play_sound / play_next_sound / stop_sounds with SDLPoP's tables, the three modes.
   - SDLPoP hook: an `N` trace line per tick (queued id, started id).
   - Z80: `snd_play` / `snd_next`, the call sites, the IM2 reclaim.
   - *Test:* oracle_suite compares the `N` lines on all 52 scripts (deterministic: requests do not depend on audio
     time); m4_test compares Z80 to kidsim; silent-mode traces unchanged; `make perf` within 5%.
3. **PSG player and effects** (1 w).
   - tools/sndconv.py, the effect streams, the ISR player, the mute before DI.
   - *Test:* tools/sndsim.py (a Python player plus a simple SN76489 model) gives the expected register state per frame
     for a script of `snd_play` events. The harness runs frame by frame and compares with the emulator's
     `get_periph_sn76489` (dispatch.c:10912; latched tone, attenuation and noise per channel).
   - A port breakpoint on OUT F2h counts writes per frame (the ISR cost check).
   - Listening: sndsim renders WAVs. SDLPoP with `SDL_AUDIODRIVER=disk` records the original for A/B. mz800emu's PSG
     write log (psg.c, GUI only today; a 20-line MCP command `psg_log` would expose it) gives an exact TSV.
4. **Music arrangement** (1 w; open-ended, quality-driven).
   - tools/midi2psg.py, the in-game pieces, then the presentation pieces. Optional 8253 bass.
   - *Test:* lengths equal the MIDI lengths to within 1 frame (sndsim); listening.
5. **Waits** (0.4 w): feather, crouch and cutscene waits in ticks; death and level-end waits live; the clock charge
   for the level end.
   - *Test:* new oracle scripts for the level 1 crouch (hook off) and the stairs (the level changes; the remaining
     time is compared). Feather scripts are unchanged.
6. **PRES title** (0.7 w).
   - The title.pack rework (1 bpp, maskless), image decode, the wipe, the step table, keys, Ctrl+L.
   - *Test:* VRAM after each step against a Python render of TITLE.DAT (pixel-exact, as M3) and against DOSBox EGA
     captures (colours, fades). The step durations are checked by frame counts.
7. **Cutscene engine and level cutscenes** (1.2 w).
   - tools/cutsim.py: a Python port of `proc_cutscene_frame` with the sequence table, giving per-frame sprite state
     and a reference render.
   - SDLPoP hook POP800_CUT: run cutscene n with rem_min m, emit a `C` line per cutscene frame (both slots' frame, x, y,
     direction; hourglass state; sand; star) and the frame counts of the until-music loops. Shots per cutscene frame
     reuse pop800_shot with a cutscene frame counter.
   - *Test:* `C` lines exact (cutsim vs SDLPoP, then Z80 vs cutsim); VRAM pixel-exact against cutsim's render on every
     frame; silhouettes against the SDLPoP shots (VGA colours), as in M6.
8. **Intro, time-out, ending, HOF** (0.8 w): `pv_scene`, `time_expired`, `end_sequence` with the kid pack, the hail
   screen, and the HOF if wanted. Same tests as step 7.
9. **Demo level** (0.5 w): do_demo in kidsim and the events overlay, the exits to PRES.
   - *Test:* an oracle script for level 0 (hook: start in demo mode) until room 24; Z80 vs kidsim.
10. **Keys and cheats** (0.4 w): pause, SPACE, Ctrl+R/S/V, Shift+L, Enter while dead, the cheat overlay.
    - *Test:* scripts with key fields (Ctrl+A already works this way); a cheat build test.
11. **Floppy and timing check on the real machine** (part of M8): POP800.PRS load times, beeper mixing, the PSG's
    LFSR.

| | Estimate |
|---|---|
| Total | about 7.5 weeks of listed work, 5-6 if the HOF and the 8253 voice are dropped |

**Main risks:**
- The music quality on 3 square voices with no envelopes (mitigation: the speaker tune as fallback).
- Cutscene frame cost over 5 frames (mitigation: draw skipping).
- The RAM-disk budget: 8 KB margin, which conflicts with M8a's visited-room cache.
- EGA fades unknown (DOSBox check first).

## 8. Decisions needed

| # | Question | Options | Recommendation |
|---|---|---|---|
| D1 | Presentation architecture | A separate PRES + game image restore / B overlays in the game / C reload from floppy | **A** |
| D2 | Where the cutscene art lives | level-cutscene art in the RAM disk (23 KB, boot +4-5 s) / everything per scene from floppy (+2 s per cutscene) | **RAM disk** for the level cutscenes; title and intro from floppy |
| D3 | RAM-disk budget vs M8a's visited-room cache | spend about 53 of the 61 free KB on M7 now / per-level guard sets first (frees about 90 KB, needs per-level floppy reads) | M7 now; revisit the cache in M8a |
| D4 | Sound and the logic | silent only / ticks only / hybrid (§5.3) | **hybrid** for the release, **silent** in every harness test |
| D5 | Music source and bass | MIDI arranged for 3 voices (+8253 bass) / the PC-speaker tunes, one voice / both (arranged, speaker as fallback) | MIDI 3 voices, notes below 108 Hz an octave up; 8253 bass as an optional later step |
| D6 | SPACE | original (SPACE = show time, button = SHIFT/fire) / keep SPACE as the button, show time on another key | **original** |
| D7 | Hall of Fame | port (name entry + POP800.HOF, about 1 KB code) / leave out | leave out for M7; add in M8 if wanted |
| D8 | Fades | match the EGA original after a DOSBox check / always instant | DOSBox check first; instant if EGA has none |
| D9 | Attract demo (level 0) | port it (0.5 w) / title loops without the demo | **port it**, as part of the original flow |

## 9. Decisions (user, 2026-10-30)

| # | Decision |
|---|---|
| D1 | A: a separate presentation program (PRES), swapped with the game by a launcher. |
| D2/D3 | **Keep the RAM disk free:** all presentation art (title, intro, level cutscenes, ending) is loaded from the floppy per scene (~2 s each); only the compressed game image needed for the swap (~20 KB) goes into the RAM disk. The RAM-disk space stays for M8a's visited-room cache. |
| D4 | Hybrid: tick-counted waits for feather fall, the level 1 crouch and cutscene waits; live death and level-end music with the level end's original length charged to the clock; every harness test silent. |
| D5 | MIDI arranged for 3 PSG voices, notes below 108 Hz an octave up; 8253 bass optional later. |
| D6 | SPACE shows the remaining time as in the original; the button is SHIFT or joystick fire. |
| D7 | No Hall of Fame. |
| D8 | Check the EGA original's fades in DOSBox first, then match them (instant if EGA has none). |
| D9 | Port the level-0 attract demo. **Reversed by the user 2026-10-31: no demo; the title loops after its fade-out (step 9 dropped).** |

Consequence of D2/D3 for §4.2 and §7: PRES loads each scene's compressed art from POP800.PRS (one floppy file,
records per scene) into its own RAM; step 1 builds that per-scene loader instead of the RAM-disk art copy.

## 10. As built: step 1, the launcher and the swaps (2026-10-30)

Code: src/boot/launch.inc (the interface and the handoff block), src/boot/boot.asm (the floppy loader is also the
launcher), src/pres/pres.asm (the PRES stub), src/m4/ovl_level.asm (the game side, in the W2 level-start overlay),
tools/mkgamedisk.py (the GAME image stream, POP800.PRS), tests/m7_launch.py, tests/m5_boot.py (boot -> PRES -> game).

- **Launcher = the boot loader's image.** After the RAM-disk probe the boot copies its own image (2,278 bytes, LN_MAX
  3 KB reserved) to RAM-disk page 0 0xF000. Entries: 0xB000 boot, 0xB003 LN_LAUNCH, 0xB006 LN_PRS_LOAD. The game
  copies the 3 KB to 0xB000 (from W2, the compose buffers) and jumps to LN_LAUNCH; PRES keeps it resident and calls
  LN_PRS_LOAD for its scenes. The launcher reuses the boot's record-stream loader (s_get reads either the floppy or
  the RAM disk at its current address; a 0xFD page/address record continues a RAM-disk stream elsewhere).
- **GAME image in the RAM disk:** the program's main-RAM records (PZ, 8 KB blocks) as a record stream at page 3
  0xA000-0xFF2B (24,364 bytes; the D files carry it as stored RAM-disk records). When it outgrows page 3's tail it
  continues at page 4 0xD400 (tools/mkgamedisk.py GAME_SEGS; checked once with MKGAMEDISK_SPLIT=E000). Pages 3 and 4
  hold only fixed art packs, so pages 6-7 (the guard sets) stay whole for M8a's per-level guard sets / room cache.
- **PRES from the floppy, not the RAM disk:** every PRES run reads the floppy anyway for its scene (D2/D3), so PRES's
  own code (933 bytes now, ~10-13 KB later, ~6 KB PZ) costs about 2 more tracks there and nothing in the RAM disk.
- **Handoff block** (16 bytes, page 5 0x3AC0, copied by the launcher to main RAM HO_MAIN 0x02A0): magic "P7", action
  (0x00 play level, 0x01 demo, 0x10 title, 0x11 time expired, 0x12 ending, 0x13 cutscene before level n; bit 4 =
  PRES), level, rem_min, rem_tick, hitp_beg_lev, options, K_TICK, last_loose, result, is_guard_notice,
  roomleave_result, 1 spare. The last four logic fields were added because tests/m7_launch.py showed they survive a
  direct level change (SDLPoP never resets them at a level start; last_loose steers RNG draws).
- **Game side** (all in the W2 level-start overlay, +231 bytes; resident +1 byte: GAME_OVER's 10 bytes became a call
  and an 8-byte stub): load_level hands over when the game was launched (HO_MAIN magic), the level changes and
  tbl_cutscenes has a scene (2, 4, 6, 8, 9, 12; verified in SDLPoP data.h / seg003.c play_level); game_over hands
  over with time expired / ending / title; game_init takes level, time, hit points and those four globals from HO_MAIN.
  Without the magic (the harness) everything is as before, so every existing test runs unchanged.
- **Time:** SDLPoP decrements rem_tick only in show_time (seg008.c, play_frame), never in seg001's cutscenes, so the
  handoff carries the time unchanged.
- **POP800.PRS:** block 0 the index (entry count word; per entry first block, block count), then per entry a record
  stream (main-RAM records only, 0xFF end, block-padded). Entry 0 PRES (0x2000), entry 1 the placeholder scene (a
  message record at 0xC000). One FSMZ file holds at most 0xFF00 bytes: the title art (~37-48 KB PZ) plus the cutscenes
  will need a second file (an index entry with a file number) in step 6/7.
- **Timings** (emulator frames; its floppy has no rotation, so floppy parts are ~0.5-1 s longer on a real drive):
  game -> launcher 1.4; launcher -> PRES 11.4 (floppy: directory, index, PRES, scene); PRES -> game start 62.2 (the
  GAME image: ~7 frames RAM-disk reads, 53.5 frames PZ decoding at ~100 T a byte: the design's 40 T/B estimate was
  optimistic; this code compresses to 63% in many short tokens); start -> level_ready ~20. A level change through
  the PRES stub (1 s wait) takes ~150 frames, game over -> title -> level 1 ~143. Boot to PRES ~773 frames.
  If 1.2 s back to the game is too slow: storing the image raw (38.5 KB, +14 KB of RAM disk) restores in ~13 frames.
- **Changes for the later steps:** §4.2's RAM-disk art plan is replaced by §9 (nothing of PRES in the RAM disk);
  PRES's memory is 0x1200-0x7FFF and 0xC000-0xFDFF (0x8000-0xBFFF are the launcher's while it loads); a scene loader
  that wants RAM-disk scratch (shadow room page 1, torch cache page 6) decompresses to main RAM first; the boot is
  10 blocks now (the IPL loads it fine).

## 11. As built: step 2, the sound model in the logic (2026-10-30)

Code: tools/kidsim.py (play_sound / play_next_sound / stop_sounds / sound_playing, the call sites), src/m4/sound.asm
(block 2: the model and the kid/guard call sites' sound parts), src/m4/sndobj.asm (main code: the traps' sound parts),
the call sites in kid.asm, kid2.asm, objects.asm, guard.asm, evres.asm and the overlays (events.asm, genter.asm,
levelstart.asm); SDLPoP hook POP800_TRACE_SOUND (pop800_trace_sound, a stop counter in seg009 stop_sounds);
tools/oracle.py, tools/oracle_suite.py (norm_sound), tests/m4_test.py, src/m4/m4test.asm (snd_snap).

- **Tables.** SDLPoP's sound_prio_table and sound_interruptible as the oracle runs them: FIX_SOUND_PRIORITIES is a
  compile-time define in config.h (not a runtime fix), so the PoP 1.3 values apply (sword_vs_sword 0x0D, spiked 0x15,
  spikes interruptible). play_sound ignores the ids without a resource (31, 34, 38, 42); the level door's sliding sound
  (15) is interruptible while it closes, not while it opens (animate_leveldoor changes the table). The Z80 keeps the
  ids 0-49 as ranks (32 distinct priorities, only the order matters) with bit 7 = interruptible (50 bytes).
- **Rules.** play_sound keeps the tick's request with the highest priority (equal replaces); draw_game_frame's
  play_next_sound starts it when nothing plays, or the playing sound is interruptible and not of higher priority, and
  empties the queue; play_level empties it too; stop_sounds ends the playing sound. Music is never interruptible, so
  no effect starts while music plays.
- **Call sites** (kidsim, Z80): the sequence table's sound command (footstep, bump, drink, the level's end music: 41,
  level 4 32, none on 13/15), bumps, the falling scream (once per fall: is_screaming, reset by land, a grab, a level
  start), soft/medium/crushed landings, spiked, chomped, hanging against a wall (not right after a grab), the grab,
  drawing the sword (kid), hurt by a sword (kid 13 / guard 12), the sword swish (11), blade on blade (10), a guard's
  death (37; Jaffar 43), the death music at alive 6 (shadow 32, in a fight 28, else 24; not levels 0/15), potions
  (33, 30, 39, 13; the sword 37), the jump through the mirror (45), the level 4 mirror and level 6 shadow music (25),
  meet Jaffar (29), the skeleton waking (44), the kid drawn as the united shadow (41), chompers (47 at frame 2),
  gates (5 opening, 7 stop, 6 fast close end, 4/7 closing only when visible: play_door_sound_if_visible with room_L),
  the level door (14, 15), loose floors shaking (20-22) and crashing (2), spikes (49), buttons (3, unless
  trigger_button's play flag is 0: the open potion, Jaffar's exit door, the level 1 start). Not ported: cheats, the
  fixes-only sites, teleports, the level 1 crouch music (the oracle hook disables it; step 5), the death text's
  blink (38: started directly, not through the queue; the player can do it in step 3).
- **Modes** (kidsim `KidSim(sound=...)`; the Z80 has the silent model only, snd_playing returns 0):
  - `silent` (default; every harness test): nothing ever plays, so every request starts at once. The waits keep the
    rules they had before: the death timer never waits, the feather fall music lasts until the 225-tick cap or a
    stop_sounds, and the level's end music never ends. New: a level done without end music (level 13's stairs)
    changes the level at once, as SDLPoP does (play_level_2) — found by the N lines (the oracle had no draw_game_frame
    on that tick); kidsim end_music, Z80 SND_ENDMUS + guard.asm tick_post end_wait.
  - `ticks`: a sound plays for ceil(length × tick rate) ticks from its start (rate 12/s, 10/s with the kid's sword
    drawn), counted down at each tick start; lengths (SOUND_SECONDS) from the DOS data: DIGISND1-3 (PoP 1.0 wave
    headers: rate, count; the copy's waves are the 1.0 format) and MIDISND1/2 (tempo map to the last event); e.g.
    feather 18.667 s = 224 ticks, level end 12.75 s = 153, death 3.6 s / 7.2 s. On walk_level1 the ticks model's N
    lines equal SDLPoP's real-time ones on 313 of 318 ticks.
  - `hybrid`: ticks, except the live waits (LIVE_WAITS: death, level end), which ask `live_playing` (kidsim: the
    ticks model). The waits themselves are unchanged (step 5 routes them through `sound_playing(wait)`).
- **The N line** (SDLPoP POP800_TRACE_SOUND, kidsim sound_line, Z80 snd_snap → N_SNAP 0x02B0): per draw_game_frame
  (no line on a restart or level-change tick) `N queued started playing stops`: queued = next_sound before
  play_next_sound (-1 none), started = the id it starts (-1 none), playing = check_sound_playing(), stops =
  stop_sounds calls since the previous N line (counted from the first level start: a restart is 2, a level change 2,
  the level 6/12 exits 3).
- **Real-time cases in the oracle** (oracle_suite norm_sound): SDLPoP plays real audio (SDL dummy driver, wall clock),
  so `playing` and therefore `started` depend on time. queued and stops are compared on every tick (they depend only
  on the logic); started and playing only where SDLPoP had no sound playing (there the start rule is the same in
  every model). After the kid's death SDLPoP's death timer freezes while a sound plays, which moves the death music
  request: a line where either side queued 24/28/32 is not compared (the existing 8-tick cut after a death stays).
- **The IM2 reclaim:** game.asm irq_init writes only the PIO's vector entry (0xFE00-0xFE01; the 8253's interrupt
  stays masked, the PIO supplies vector 0): 0xFE02-0xFF00 (255 bytes) are free for the music ring (step 3); also 12
  bytes of code. Verified in the emulator (scratchpad im2check.py): with 0xFE02-0xFF00 filled with 0xAA after start the
  game runs (406 interrupts in 406 frames, 62 ticks) and the ISR's 8253 latch steps 312 lines per frame.
- **Resident cost:** sound.asm 447 bytes in block 2 (the model ~200 incl. the 50-byte table, the kid/guard parts ~250),
  sndobj.asm 223 bytes in main, guard.asm +66, overlays +31 (events), +10 (genter), +20 (level start); the call sites replaced
  ~100 bytes of main code. State: 7 bytes at 0x03C1 (SND). Free after: main 12, low 53, block 2 416 bytes (481 in
  all) + 0xFE02-0xFF00 for buffers. The player (~300 bytes, step 3) fits in block 2 with ~110 bytes to spare; the
  op-list reclaim was not needed.
- **For steps 3-5:** snd_next's `snn_go` is where the player starts SND_CUR; snd_playing is the one place that asks
  whether a sound plays (silent: 0); snd_stop must also silence the PSG. The death text's blink (38) is not queued.
  The game (game.asm) still changes the level at once after the stairs (no end-music wait; m4test keeps kidsim's
  silent rule); step 5 adds the live wait and the clock charge. The feather fall's MIDI is 224 ticks at 12/s, one
  tick under the 225 cap: a ticks-mode feather wait ends one or two ticks before the cap unless the length is rounded
  up to the cap (decide in step 5; the design's "ends at the 225 cap" assumes the cap wins).

## 12. As built: step 3, the PSG player and the effects (2026-10-30)

Code: tools/sndconv.py (DOS data -> build/assets/sound.bin, sound.txt), src/m4/psg.asm (the player, block 2),
src/m4/sound.asm (snd_next starts the sound, snd_stop stops it), game.asm (isr's tail, irq_init), ovl_level.asm
(SND_MODE, the mute before the launcher), ovl_save.asm (the mute before the floppy), src/boot/boot.asm (psg_off at
the boot, LN_LAUNCH and LN_PRS_LOAD), tools/sndsim.py (Python player + SN76489 model + WAVs), tests/m7_sound.py.

- **Stream format.** One stream per sound id, played one record per VBLN interrupt: header H, then n = H & 15 bytes
  written as they are to port F2h (OTIR), the state held for (H >> 4) + 1 frames; H = 0 ends (all four channels muted,
  the player stops). Only the registers that change are written (tone = latch + data byte, noise control, one byte per
  attenuation); a hold longer than 16 frames takes one more header byte. The format is the PSG's own bytes, so the ISR
  part is 45 bytes and costs ~41-56 T per PSG byte (OTIR's 21 T plus the PSG's READY wait, 20-35 T in mz800emu).
- **Bank** (RAM-disk page 1 0xE000-0xEE76, 3,703 bytes; written by the boot (mkgamedisk.py ramdisk_writes) and
  tests/m4_game.py setup): 57 index entries of 5 bytes (stream address, buffer address, length), then the streams:
  effects 814 bytes (the longest 96), music placeholders 2,604.
- **Player** (psg.asm, 167 bytes in block 2): `snd_start` (called by snd_next where it starts a sound, main code)
  stops the stream, mutes the PSG (4 OUTs), reads the index entry and copies the stream into its buffer (effects:
  EFX_BUF 0x0148-0x01FF, 184 bytes; music: MUS_BUF 0xFE02-0xFF00, 255 bytes), then arms it (SP_WAIT = 1); the next
  interrupt plays its first frame. `snd_isr` is the tail of game.asm's isr (`jp snd_isr`; it pops and returns).
  `snd_halt` (snd_stop, irq_init, the save overlay) stops and mutes with interrupts off for its 4 OUTs and keeps the
  caller's interrupt state; ho_swap (to the launcher) calls psg_mute. The ISR never touches the RAM disk; its code and
  data are outside 0x1000-0x1FFF and 0x8000-0x9FFF (tests/m7_sound.py checks the addresses). State: SP_VARS 0x03C8
  (SP_WAIT, SP_PTR, SP_HDR, SND_MODE).
- **snd_playing** = the player's stream runs (SP_WAIT != 0) when SND_MODE = 1, else 0. game_init_h sets SND_MODE = 1
  only in the launched game (the handoff magic); the harness never has it, so every harness test is silent as before
  (m4test's own stubs: snd_start / snd_halt do nothing, snd_playing 0). The launched game is therefore "live" for
  play_next_sound until step 5 adds the ticks part of the hybrid mode.
- **Effects** (tools/sndconv.py SPEC; per 20 ms frame of the speaker timeline: rests over half the frame = silence; a
  line's notes in the frame -> the note with the most time, or noise when 3 or more notes span more than 2.5x (rate =
  4 x the median note, the LFSR shift rate whose zero crossings match a square wave of that pitch); notes below
  108.3 Hz -> a pulse of periodic noise clocked by channel 2 (CPU / (256 N2)), or an octave up when channel 2/3 are
  busy; speaker notes above 15 kHz = silence (the PIT divisor wraps); attenuation 2 for one line, 3 per line for
  two or three). Frames = the speaker length rounded to 20 ms, at least 1. The five ids without speaker data
  (falling, sword_moving, draw_sword, loose_shake 1-3) are made from the digitized effect (DIGISND, the sound SDLPoP
  plays): per frame its RMS (-> attenuation, 2 dB steps from a level of 60/128) and its pitch (autocorrelation) or
  zero-crossing rate (-> noise rate).

  | id | name | frames | bytes | made from |
  |---|---|---|---|---|
  | 0 | fell_to_death | 4 | 17 | random notes 24-1068 Hz (72 ms) -> white noise, rate following the notes |
  | 1 | falling | 55 | 96 | no speaker data: the digitized scream (1.09 s): its pitch (~367 Hz) and loudness per frame |
  | 2 | tile_crashing | 15 | 52 | random notes 51-1139 Hz (302 ms) -> noise following the notes, faded over the last 4 frames |
  | 3 | button_pressed | 2 | 9 | random notes (42 ms) -> 2 frames of noise |
  | 4 | gate_closing | 1 | 6 | one 101 Hz note (14 ms) -> 1 frame of a 101 Hz pulse |
  | 5 | gate_opening | 1 | 6 | one 101 Hz note (7 ms) -> 1 frame, 4 dB quieter than 4 |
  | 6 | gate_closing_fast | 6 | 21 | random notes 252-1861 Hz (128 ms) -> 6 frames of noise |
  | 7 | gate_stop | 1 | 5 | one 4999 Hz note (14 ms) -> 1 frame tone |
  | 8 | bumped | 2 | 6 | one 49 Hz note (42 ms) -> 2 frames of a 49 Hz pulse |
  | 9 | grab | 1 | 6 | one 61 Hz note (14 ms) -> 1 frame of a 61 Hz pulse |
  | 10 | sword_vs_sword | 3 | 9 | one 2999 Hz note (42 ms) -> 3 frames tone with a decay (the clang) |
  | 11 | sword_moving | 5 | 22 | no speaker data: the digitized swish (106 ms) -> noise, rate and level per frame |
  | 12 | guard_hurt | 3 | 18 | two interleaved falling lines 230->70 / 730->570 Hz (62 ms) -> two tones (the low line as a pulse below 108 Hz) |
  | 13 | kid_hurt | 3 | 18 | two interleaved falling lines 980->820 / 480->320 Hz (51 ms) -> two tones |
  | 14 | leveldoor_closing | 9 | 26 | rising octave pairs 208/416 -> 400/800 Hz, then a 97 ms rest -> two tones, then silence (the stream keeps the length) |
  | 15 | leveldoor_sliding | 13 | 42 | 18 notes 39->31->39 Hz (250 ms) -> a 31-39 Hz pulse following the notes |
  | 16 | medium_land | 3 | 20 | three interleaved lines: 121->201 and 101->181 Hz rising, one random (60 ms) -> two tones + noise |
  | 17 | soft_land | 2 | 6 | one 49 Hz note (42 ms) -> 2 frames of a 49 Hz pulse, 2 dB quieter than the bump |
  | 18 | drink | 73 | 82 | six rising sweeps (10 notes each, 138->256 Hz) with rests (1.46 s) -> tone sweeps and rests |
  | 19 | draw_sword | 12 | 33 | no speaker data: the digitized blade (254 ms) -> bright noise, level per frame |
  | 20 | loose_shake_1 | 6 | 25 | no speaker data: the digitized rattle (121 ms) -> noise |
  | 21 | loose_shake_2 | 3 | 19 | no speaker data: the digitized rattle (95 ms, a clink at 733 Hz) -> tone + noise |
  | 22 | loose_shake_3 | 5 | 29 | no speaker data: the digitized rattle (106 ms, 524 Hz) -> tone + noise |
  | 23 | footstep | 1 | 6 | one 61 Hz note (14 ms) -> 1 frame of a 61 Hz pulse, 4 dB quieter |
  | 38 | blink | 3 | 11 | 2500, 2000, 1500, 1000 Hz (56 ms) -> 3 frames of falling tone |
  | 44 | skel_alive | 19 | 62 | 19 notes of 20 ms each, 33-3132 Hz -> one tone per frame (pulses below 108 Hz) |
  | 45 | jump_through_mirror | 8 | 43 | two interleaved lines: 1758-2536 Hz jittering, 1002->2152 Hz rising (167 ms) -> two tones |
  | 46 | chomped | 3 | 21 | three interleaved lines: 501->581 Hz, random, 999->919 Hz (68 ms) -> two tones + noise |
  | 47 | chomper | 5 | 8 | 4000 / 750 Hz alternating (107 ms) -> two tones |
  | 48 | spiked | 8 | 41 | three interleaved lines: 499 Hz falling to 0, random, 999 Hz falling (151 ms) -> two falling tones + noise |
  | 49 | spikes | 3 | 25 | four interleaved lines 4300->5200, 2700->1800, 2800->3700, 1200->300 Hz (56 ms) -> three tones (the third line dropped) |
  | 51 | princess_door_opening | 27 | 24 | 9 notes 39->31 Hz (538 ms) -> a 31-39 Hz pulse (PRES) |

- **Music placeholders** (step 4 replaces them): the speaker tune as one voice on channel 0, notes below 108 Hz an
  octave up, attenuation 2 for a note's first 6 frames then 4, a repeated pitch re-struck after a 1-frame gap; the whole
  stream in MUS_BUF, so the four longer than 255 bytes are cut: low_weight (39) 6.2 of 18.6 s, and the presentation
  pieces 52, 54, 56. Every music id of the bank has one, so the queue and priorities (music is never interruptible)
  are audible end to end.
- **Tests** (tests/m7_sound.py; tools/sndsim.py is the reference): the PSG's registers change only on writes and the
  game writes them only in the player, so the emulator's state (get_periph_sn76489) is sampled after every record the
  ISR plays and every stream end and compared with sndsim stepped to the same interrupt (which must have played a record
  / ended there too); snd_halt and snd_arm drive sndsim; in the game the decision at snd_playing / snn_x (queued,
  playing, started) is checked against sndsim's player and play_next_sound's rule. A: a driver program plays every
  stream of the bank, overlaps and a stop; B: four scenes in the silent and the live mode. The breakpoints sit where
  an event takes effect (snh_di after snd_halt's DI, snd_arm, snp_rd where snd_playing reads SP_WAIT): an interrupt
  between a routine's entry and that point would otherwise be counted on the wrong side. The ISR's cost is measured
  with breakpoints at isr and the player's reti.
- **Existing tests**: tests/m5_boot.py and tests/m7_launch.py run the launched (live) game; they check SND_MODE = 1 and
  set it to 0 at level_ready, so the comparisons with the harness are silent on both sides. tests/m5_boot.py also leaves
  pend_flush's beam scratch (pf_e..pf_s, like pf_f0 before) out: the PSG's wait states depend on the absolute cycle
  phase, which differs between the two runs (one raster line).
- **Cost**: the ISR from isr to reti is 211 T idle (was 172: +39 T a frame, 0.06%); playing 235-798 T, average 417
  over effect-dense frames (at most 9 PSG bytes in one frame, 2.7 on average where a record is played; the PSG's wait
  states included: every write waits 16 + 4..19 T for the chip, so the timing depends on the absolute cycle phase and
  tests/m5_boot.py leaves pend_flush's beam scratch out). snd_start costs
  ~0.5 K T + 21 T per stream byte at a start (silent mode starts every request). tools/perfcheck.py: +0.9 to +1.3% over
  the baseline (step 2: +0.3 to +1.2%), baseline not updated (docs/perf.md).
- **Listening**: `python3 tools/sndsim.py --wav` -> build/sound/effects/<id>_<name>_{psg,pcspk,digi}.wav,
  build/sound/music/*, build/sound/ab_effects.wav (per effect: digitized original, speaker original, PSG),
  build/sound/all_effects_psg.wav; tests/m7_sound.py writes build/sound/scene_<script>_{silent,live}.wav from the
  emulator's PSG states and build/sound/driver_all_streams.wav; `tools/sndsim.py --sdlpop <script>` records SDLPoP
  (SDL_AUDIODRIVER=disk, real time) as build/sound/scene_<script>_sdlpop.wav for the A/B of a scene.
- **For steps 4-5**:
  - Step 4: the music ring in MUS_BUF needs the player to wrap (a reserved record or a pointer check: ~20 bytes in
    snd_isr) and `snd_fill` from main code; the format has no free header value (H = 0 ends, every other byte is a
    record), so the ring either uses a wrap check on SP_PTR or music gets its own record format. block 2 has 249 bytes.
    Arranged pieces must keep the MIDI lengths (SOUND_SECONDS) for the live waits.
  - Step 5: the hybrid mode needs the ticks model in the Z80 (a per-id length in ticks, counted down per tick) for
    play_next_sound and the tick waits; the live waits (death, level end) ask snd_playing as built. The effects' PSG
    lengths are the speaker lengths (1-73 frames), shorter than the digitized lengths the ticks model uses: in the
    hybrid mode a sound can count as playing after its stream ended (inaudible, the original's rule).
  - The death text's blink (38, not queued) can call snd_start directly; the pause (step 10) calls snd_halt.
  - To check on the real machine: the PSG's READY / WAIT at OTIR speed (docs/research/mz800-hardware.md), the
    periodic noise's LFSR length (the low pulses' pitch), the mixing level.

## 13. As built: step 4, the music (2026-10-31)

Code: tools/midi2psg.py (the arrangement; its helper renders SDLPoP's OPL playback), tools/sndconv.py (the new stream
format, both banks), tools/sndsim.py (the player model with the ring and the envelopes, max_gap), src/m4/psg.asm (the
player), tests/m7_sound.py.

- **Source and its rules.** The 22 pieces of MIDISND1/2 (type 0, 480 ticks a beat, 7 channels with one OPL instrument
  each, mostly octave doublings), read as SDLPoP plays them: note 69 - 12 + SysEx semitones = 440 Hz (12 in most
  pieces, 24 in 26, none in 25, 29, 35, 37, 43, 53); the file's first delta is never waited for; 53 / 54 run 3% faster
  / slower (midi_tempo_modifiers); the piece ends at its end-of-track event. A small C helper (embedded in
  midi2psg.py, compiled into build/sound/opl/ against external/SDLPoP/src/opl3.c) is SDLPoP's midi.c playback
  outside the game: it renders whole pieces (build/sound/music/*_midi.wav, lengths equal the MIDI's to the sample) and
  measures the level of every (instrument, velocity, key) used (700 combinations, one note at a time, RMS per 20 ms,
  cached in build/sound/opl/levels.json; since 2026-11-02 the reference curves are committed: assets/opl/levels.json).
- **Arrangement** (per 20 ms frame): every note's level curve (measured attack/decay/sustain until its note-off, then
  the measured release); its sounding pitch (the instrument's octave: programs 2, 7 an octave up, 3, 11, 15 an octave
  down, measured from their spectra), folded up by octaves to >= 108.3 Hz (D5); a folded note keeps its loudness
  (level + half the A-weighting difference between the two pitches: a 50 Hz bass at 110 Hz would sound too loud).
  Unisons after the fold merge. Up to 3 notes sound, by score: the level, +12 dB for the loudest note of the top
  pitch class (melody), +5 dB for the loudest of the bottom one (bass), +8 dB for a note that already has a channel,
  +8 dB for a note's first 3 frames, -20 dB for a pitch class already chosen (octave doublings give way to chord
  tones). A note that lost its channel returns only to a free channel (a held chord stays full); a repeated pitch is
  re-struck after a 1-frame gap. Attenuation = (piece peak - level) / 2 dB, quieter than 28 dB = off. No arpeggios
  and no noise: every instrument is tonal (spectra checked; no percussion channel), and the chords' doublings leave
  3 voices enough (harmony score: the cosine of PSG vs MIDI pitch-class amplitudes per frame, 0.86-1.00, mean 0.94;
  melody: the top MIDI note's pitch class sounds on the PSG in 93-100% of the frames). Per-piece settings: only the
  ending (56) raises the melody bonus to 30 dB (its melody runs in three octaves under busy broken chords: 0.74 ->
  0.93 melody). sound.txt lists per piece the notes, channels, folded notes and both scores.
- **Stream format** (sndconv.py has the full description): a group of commands per frame step, ended by a wait byte
  (1-127 frames) or the end (0): a tone latch + data byte, the noise control (1 byte), or an attenuation (1 byte) +
  unless off a period byte p: the ISR's envelope for that channel then adds 2 dB every p frames (p = 0: held). The
  encoder simulates the envelopes and writes a command only where the wanted attenuation leaves the envelope's by
  more than 1 step (or a note starts), choosing the period that follows longest; effects use p = 0 (their frames are
  exact, as in step 3). Result: 5-45 bytes a second (the ending 41, in-game at most 26: piece 41).
  **Loop command** (M7 step 11, §19): a stream whose last counted byte is not the end 0x00 (it is its last wait)
  loops: `0xE8 lo hi` follows it in the bank, not counted in the index length, hi:lo = the loop point's bank address.
  snd_fill reads it when the stream's last byte has been copied and goes on copying from the loop point, so the ring
  holds the loop point's group right after the last wait and the ISR plays on without seeing the command: the ISR's
  code and cost are unchanged. Opcode 0xE8 is in the free range 0xE8-0xEF of the command space (the noise control
  uses 11100xxx only). The game's streams all end with 0x00 (asserted), so the game never reads a trailer. Models:
  tools/sndsim.py Bank.loops / Player.fill, tools/vgm2psg.py encode(loop=): the loop point's group writes every
  attenuation (resetting the envelopes), its tones and its noise, so the state after it is the same from the intro
  and from the end; tools/presbank.py writes the banks.
- **Lengths**: every stream's frames = round(MIDI length x 50) (asserted; within 0.5 frame); SDLPoP's lengths of 53 /
  54 are 16.747 / 25.023 s (with the tempo modifier). Note for step 5: kidsim's SOUND_SECONDS[35] = 13.643 and [36] =
  15.729 differ from the MIDI (10.286 / 14.529 s, also design table 1.3), and [53] / [54] lack the tempo modifier
  (17.265 / 24.294 there); these are presentation pieces, the in-game values agree.
- **Player** (psg.asm, 321 bytes, was 167): every stream goes through the ring 0xFE02-0xFEFF (254 places, the read
  pointer's high byte fixed, so a wrap is `inc l` + a reset to 2); the ISR steps the four envelopes, then reads the
  group; snd_start mutes, reads the 4-byte index entry (address, length), clears the envelopes and fills the ring;
  snd_fill copies min(room, left) bytes from the RAM disk (main code only); it is called from snd_playing, i.e. once
  a tick from play_next_sound, so m4test's stubs need nothing new; snd_halt also ends the copying. State: SP_VARS
  0x03C8-0x03DC (MF_SRC, MF_LEFT, MF_W, ENV). The effect buffer 0x0148-0x01FF is free again. The ISR never touches
  the RAM disk; code and data outside 0x1000-0x1FFF / 0x8000-0x9FFF.
- **Refill during room draws**: not needed as a call inside the draw. The ring holds 253 bytes: the densest stretch
  of any piece needs 253 bytes only after 229 frames (the ending; 54: 260, 52: 366, 41 the only streaming in-game
  piece: 377; the other pieces fit whole), while a full room draw plus a tick is ~110-120 frames between two refills
  (tests/m7_sound.py measures it, below). The converter could assert a minimum gap if a denser piece ever comes.
- **Banks**: sound.bin (RAM-disk page 1 0xE000-0xE917, 2,328 bytes: index 228, effects 925, the 11 in-game pieces
  1,175; was 3,703 with the placeholders): 5.8 KB of the page free after it. sound_pres.bin (9,355 bytes: the effects
  and the 11 presentation pieces, 8,202 bytes, the ending 5,106; addresses from 0): for PRES in POP800.PRS (steps
  6-8); PRES can load it to its own RAM and play it with the same player (no streaming needed there).
- **Cost**: the ISR while a stream plays ~580-2,200 T, ~880-930 T on average in the driver runs (step 3: 235-798, avg
  417; the envelope loop is ~350 T); idle unchanged 211 T. snd_fill: ~60 T when nothing is to copy, ~47 T a byte
  copied (at most ~4 bytes a tick for the ending, ~2 in the game): < 300 T a tick.
- **Listening**: `make sound-wav` (or `python3 tools/midi2psg.py --wav`): build/sound/music/<id>_<name>_midi.wav
  (SDLPoP's OPL), _pcspk.wav (the DOS speaker tune), _psg.wav (the arrangement) and build/sound/ab_music.wav (per
  piece MIDI, speaker, PSG); tests/m7_sound.py writes build/sound/scene_run_rooms_ending_live.wav (the ending streamed
  through room changes, as the emulator played it).

## 14. As built: step 5, the waits on sound (2026-10-31)

Code: tools/kidsim.py (sound_playing(wait) at the four waits, sound_ticks / sound_ticks_tables, level_end_wait,
level_end_charge, end_over, need_level1_music, script options `# sound ticks`, `# level1 music`), src/m4/sound.asm
(snd_model, snd_live, feather_snd, death_wait, crouch_music, end_wait, the ticks model in snd_next / snd_stop),
guard.asm (timers: the ticks model's clock and the feather fall; tick_post: END_OVER), kid.asm (the death timer,
control_crouched), game.asm (the level changes on LEVEL_SWITCH only), levelstart.asm (game_init: the lengths table,
NEED_L1M; play_level: END_OVER), ovl_level.asm (end_charge), m4test.asm; SDLPoP hooks POP800_SOUND_TICKS,
POP800_LEVEL1_MUSIC (pop800_trace.c, seg000/003/009); tools/oracle.py, tools/oracle_suite.py; tests/m7_scripts (4 new
scripts), tests/m4_test.py, tests/m7_launch.py, tests/m7_sound.py, tests/m4_game.py.

**Sound modes** (psg.asm SND_MODE; kidsim `KidSim(sound=...)`):

| SND_MODE | kidsim | play_next_sound, feather fall, level 1 crouch | death timer, level end | Use |
|---|---|---|---|---|
| 0 silent | silent | nothing plays (the old rules: FEATHER_MUSIC, SND_ENDMUS, no crouch) | | every harness test, as before |
| 1 hybrid | hybrid | the ticks model | the PSG player (live), the level end's clock charged | the launched game (game_init_h) |
| 2 ticks | ticks | the ticks model | the ticks model | `# sound ticks` scripts (m4_test pokes it) |
| 3 live | (none) | the player | the player | tests/m7_sound.py's live scenes |

**The ticks model** (kidsim sound_ticks, Z80 SND_LEFT): a sound started by play_next_sound plays for ceil(length x
rate) ticks, rate = 10/s when the kid's sword is drawn at the start, else 12/s; counted down at each tick start (kidsim
step's sound_tick, guard.asm timers, SDLPoP's play_level_2 frame); stop_sounds ends it. Lengths: SOUND_SECONDS (the
DOS data; 35, 36, 53, 54 corrected to the MIDI lengths 10.286 / 14.529 / 16.747 / 25.023 s, 53 / 54 with SDLPoP's tempo
modifier). The Z80 has the 100-byte table for ids 0-49 at both rates (SND_T12 / SND_T10 at 0x9B88, behind the VRAM
window: only snd_next reads it, never inside blit), copied from the level-start overlay by game_init; tests/m4_test.py
checks it against kidsim's sound_ticks_tables.

**The waits as built:**

| Wait | SDLPoP | kidsim | Z80 | Mode in the release | Length source |
|---|---|---|---|---|---|
| Level 1 crouch (seg005 control_crouched) | need_level1_music (init_game: level 1): while crouched, no control; when no sound plays: 1 -> music 25, 2 -> done | control_crouched, need_level1_music (only with `level1_music`, as the oracle hook) | crouch_music (block 2, 4 bytes in kid.asm): NEED_L1M set by game_init on level 1, ignored when silent | ticks | 25: 2.471 s = 30 ticks (after the landing's own sound: the gate's 6 or 17); the script level1_crouch: the controls come back at tick 41 |
| Feather fall (seg003 timers) | ends when no sound plays or after 225 ticks | sound_playing('feather') | feather_snd (timers) | ticks | 39: 18.667 s = 224.0 ticks at 12/s, raised to the 225-tick cap (SOUND_TICKS_MIN): decided that the cap wins, as in every real-time SDLPoP run (the feather oracle scripts end at the cap); in the ticks model music and cap end in the same tick, at 10/s (187 ticks) the music would end first |
| Death timer (seg006 play_kid) | stops while a sound plays (not 5, the gate), and at alive 7 while any plays | sound_playing('death') | death_wait (kid.asm kt2a); the restart button works while it waits (alive 7) | live (the player) | 24 3.6 s, 28 7.2 s, 32 7.25 s as the stream plays |
| Level end (seg003 play_level_2) | no level change while any sound plays | level_end_wait, sound_playing('level_end') | end_wait (tick_post) -> LEVEL_SWITCH (game.asm changes the level only on it now) | live, clock charged | 41 12.75 s (153 ticks), level 4's 32 7.25 s (87) |

**The clock during the level end wait.** SDLPoP keeps running play_level_2's frames while the end music plays:
play_frame -> show_time decrements rem_tick every frame (Kid.alive < 0, levels 1-12; FREEZE_TIME_DURING_END_MUSIC is a
fix, off in the original), so the original charges the whole music to the clock: on walk_level1, music 41 starts at
60:436 and level 2 starts with 60:283, 153 ticks later (the oracle script level1_end_music, ticks model, matches).
Our release (hybrid): the PSG player's live music decides when the level changes, and the clock gets exactly what the
ticks model counts: it runs normally while SND_LEFT > 0; when the ticks model's sound has ended but the live music
plays on (the Z80's tick is shorter than 1/12 s while the kid is gone from the screen), end_wait sets END_OVER and
tick_post skips show_time; when the live music ends first, load_level_h's end_charge runs show_time once per tick
SND_LEFT still has (a time-out meanwhile is the time-expired game over). The time left at the next level therefore
equals the ticks mode's (= the original's frame count) whatever the live wait took. tests/m7_launch.py measured it on
walk_level1: the live music lasted 636 frames (12.72 s) = 160 Z80 ticks (12.6 ticks a second: the kid is off the
screen, a tick costs ~4 frames), so the ticks model ended first (153 ticks) and END_OVER stopped the clock for the last
7 ticks: level 2 starts with 60:283 as the direct ticks-mode path (and SDLPoP). With the ticks model's music made 60
ticks longer in both runs (case 2b), the live music ends first and the level change charges the remaining 53 ticks:
60:223 on both sides. kidsim's hybrid mode has the same END_OVER / charge rules (with its default live_playing = the
ticks model they never act; a fake live_playing of 60-154 ticks gave 60:283 in every case).

**SDLPoP hooks** (tools/sdlpop-pop800.patch regenerated):
- `POP800_SOUND_TICKS=t12;t10` (tools/oracle.py passes kidsim's sound_ticks_tables for `# sound ticks` scripts):
  check_sound_playing (seg009) returns the ticks model inside play_level_2's loop: pop800_sound_start in
  play_next_sound (seg000) sets the length by Kid.sword, pop800_sound_tick at each play_level_2 frame before timers
  (seg003) counts down and marks the model active, stop_sounds ends it, pop800_sound_outside at play_level's loop top
  (seg003) makes the cutscenes and the level-start wait ask the real audio again (their loops would never end).
- `POP800_LEVEL1_MUSIC=1` (`# level1 music`): pop800_control no longer clears need_level1_music.

**New scripts** (tests/m7_scripts, all `# sound ticks`, compared exactly by oracle_suite (every N field, S lines
after a death, alive up to 8: SDLPoP's death timer stops counting at 8, kidsim's at 100) and by m4_test (Z80 in
SND_MODE 2 vs kidsim ticks, alive exact, no 8-tick cut after a death)): level1_crouch (level 1 start, the crouch: 25
starts at tick 10 after the gate's 6, controls back at 41), level1_end_music (walk_level1 + the wait: level 2 starts
153 ticks after 41, through SDLPoP's level 2 cutscene; the S lines compare the time left), death_music (level 7 fall
to death: alive stays 7 for the 44 ticks of 24, then the text), feather_ticks (feather_fall in the ticks model: music
and cap end together, footsteps blocked by the music meanwhile). All 52 old scripts stay silent with unchanged traces.

**Memory.** Block 2 needed ~200 bytes (the waits ~150, the ticks model ~45) and had 91: the guard trace snapshot and
the guard records/globals (G_SNAP, gv_start..gv_end, 113 bytes of runtime-only data, the same layout) moved from block
2 to low RAM 0x0148-0x01B7 (free since step 4). The op-list sizing was measured and is no reclaim: the largest rooms
of levels 0-14 (tools/popdata.py, EGA) need 185 of the 192 back records (level 10 room 1) and 126 of the 128 fore
records (level 3 room 8), mid 1 of 8. New state: SND_LEFT 0x03DD, NEED_L1M 0x03DE, END_OVER 0x03DF; the lengths table
0x9B88-0x9BEB. Free after: main 9 bytes (end_of_code 0x7BF7), low block 53, block 2 9 (block2_end 0xEBF7); W2 level
overlay 1,665 bytes (+184: end_charge, the table, game_init's part). Runtime data room left: 0x01B8-0x01FF (72 B),
0x9BEC-0x9BFF (20 B) and 0x9F90-0x9FFF (112 B, behind the VRAM window: not for the ISR).

**For steps 6-9:**
- Resident code is used up (main 9, block 2 9 bytes). Further resident code needs a reclaim: constant tables of block
  2 can move to runtime RAM copied by game_init as the lengths table did (guard.asm's skill tables strikeprob ..
  tbl_guard_type, 84 bytes; snd_tab 50 bytes must stay where snd_ent finds it in one page), or more code into
  overlays.
- Cutscene "until the music ends" loops (PRES): a fixed frame count per scene from the ticks model of the cutscene's
  rate (the oracle's hooks can log them: pop800_sound_outside keeps cutscenes real-time today; a POP800_CUT hook
  would count frames there).
- The pause (step 10) halts the player (snd_halt): a pause during a live wait ends that wait at the resume (the clock
  stays exact through the charge, the death text comes earlier); keep it in mind or resume the stream instead.
- The death text's blink (38) is not queued (no length in the model); PRES's own waits do not use SND_LEFT.
- The handoff carries no sound state: every level change stops the sounds (SND_LEFT 0); game_init sets NEED_L1M for a
  new game on level 1 (the title's start), so the release crouches there as the original does.

## 15. As built: step 6, the title in PRES (2026-10-31)

Code: src/pres/pres.asm (the title, the step table, the drawing, the keys), src/m4/psg.asm (included; SB_PAGE / SB_ADDR
overridable with PSG_BANK_PAGE / PSG_BANK_ADDR, the game's binary unchanged), src/boot/unpz.asm (the PZ decoder moved
out of boot.asm, included by both; the boot image unchanged), src/m4/save.asm (included for load_saved),
tools/build_assets.py (build_title: title.pack / .dir / .json and title.inc), tools/titleref.py (the Python reference
render), tools/mkgamedisk.py (POP800.PRS entries 2 and 3), tools/dosbox_title.py (the DOSBox EGA recording and its
analysis), tests/m7_title.py; tests/m5_boot.py and tests/m7_launch.py press a key on the title now. No game-side change:
build/m4game.bin and build/m4ovl.bin are byte-identical to step 5's.

**The EGA original in DOSBox (D8).** tools/dosbox_title.py records DOSBox (machine=ega, cycles 3000) under Xvfb with
ffmpeg's x11grab at 50 frames a second (DOSBox's capture keys do not reach it there) and compares the stable screens with
tools/titleref.py; the recording stays in build/dosbox/title/.
- **No palette fade.** fade_in_2 / fade_out_2 (the empty `// ...` EGA branches of SDLPoP) are an interlaced line
  reveal / clear in 5 passes: pass k draws (or blacks out) the rows y mod 5 = k, top to bottom, no pixel changes colour
  in place. The passes come 3-3.25 frames (60-65 ms) apart; PRES uses 4 SDLPoP ticks (66.7 ms; the spacing may be CPU
  time on the original). Seen at the title's first screen, after story 1 (before pv_scene), the pv_scene fade-in, after
  pv_scene, at story 2 (i) and before the demo.
- **The wipes** at j and k are plain left-to-right column wipes (transition_ltr), no fade. Steps b-f are cuts.
- **Colours: a dither.** TITLE.DAT's palettes (res 40, 50) hold four 16-entry EGA tables (bytes 68-99): table
  (y & 1) * 2 + (x & 1) at screen pixel (x, y), so indices 3, 6, 8 and 10 are 2-colour checkerboards (5/6, 8/6, 7/14,
  9/1). The old title.pack used only the first table, and res 40's palette for res 51-55 too (they differ at index 14).
  Of the other DATs only PV.DAT's room (res 950: indices 11, 12) and bed (980: 2, 11, 15) dither: step 7 needs it.
- **Positions:** SDLPoP's full_image table, except the EGA credits (res 45, 143 rows) at y 23, not 26.
- With these, every title screen in DOSBox (MAIN, + PRESENTS, + GAME, + logo + copyright, FRAME + ABSENCE / MARRY /
  CREDITS) equals tools/titleref.py pixel for pixel outside the mouse cursor's square.
- The timing in DOSBox is not a reference: at 3000 cycles a full-screen draw takes ~2.7 s, longer than step c's 65
  ticks; the waits follow SDLPoP's ticks (§1.2).

**title.pack** (tools/build_assets.py build_title, from TITLE.DAT through the dither): res 51 and 41 4 planes maskless
(32,000 bytes each), res 52, 53, 55 4 planes maskless with the right edge mask of a box wider than the image (dir byte
7, flag bit 1), res 54 (the logo, transparent) the inverted mask + 4 planes, res 42-45 1 bpp (flag bit 2: drawn as
colour 15); 99,619 bytes raw. title.inc: TITLE_F_MUSIC = 463 and TITLE_F_REST = 74, step f's two waits (below, §19).

**POP800.PRS** (one FSMZ file, 36,864 bytes = 144 blocks; 0xFF00 holds; the intro / cutscene art of steps 7-8 will need
the second file with an index entry carrying a file number):

| Entry | Blocks | Content |
|---|---|---|
| index | 1 | entry count, per entry first block and block count |
| 0 PRES | 10 | build/pres.bin (3,638 bytes) at 0x2000, PZ |
| 1 placeholder scene | 1 | the stubs' message record at 0xC000 (cutscene, time expired, ending until steps 7-8) |
| 2 sound bank | 25 | build/assets/sound_pres.bin (9,355 bytes) PZ to SBANK_TMP 0xC000; PRES copies 0x2880 bytes to the torch cache |
| 3 title art | 107 | 14 PZ bands (whole rows, at most 8,000 bytes raw each: MAIN and FRAME 4 x 50 rows, the logo 2) stored as they are, 27,025 bytes, plus the art index art_idx (7 slots x 20 bytes: column, row, wbytes, h, flags, lm, rm, bands, per band rows and address) |

**PRES memory** (3,638 bytes of image):

| Range | Use |
|---|---|
| 0x03C8-0x03DC, 0x0800 | the PSG player's SP_VARS; FRAMES (as the game: tests/m7_sound.py's tracker reads it) |
| 0x1200-0x1FFF | title art bands (read only by unpz, never while VRAM / the CG ROM are mapped) |
| 0x2000-0x2E35 | PRES: code, the step table, the variables, ROWBUF (160), art_idx (140) |
| 0x2E36-0x7FFF | title art bands |
| 0x8000-0xBFFF | the launcher's (its buffers while it loads, its image at 0xB000) |
| 0xC000-0xDF3F | DBUF: one unpacked band; also the scene / sound bank load area and load_saved's sector + directory (OVL_W2 = 0xB900) |
| 0xDF40-0xFBFF | title art bands (not 0xEBF7-0xEBFF: tests/m5_boot.py compares the game's main RAM to 0xEBFF at its start) |
| 0xFD00-0xFDFF, 0xFE00-0xFEFF | the stack; the IM2 vector (one entry) and the PSG ring MUS_BUF |

4,848 bytes of the art places are left. **RAM-disk scratch:** the screen in the shadow room's place (page 1
0x0000-0x7CFF, row y plane p column x at y * 160 + p * 40 + x) and the sound bank in the torch cache (page 6
0x0000-0x287F, its stream addresses count from 0). The game rebuilds both; its shadow rows 192-199 keep PRES's bytes,
which tests/m5_boot.py and tests/m7_launch.py leave out (PRES_SCRATCH, PRES_LEFT). Nothing of PRES is written to the
RAM disk by the boot (D2/D3).

**The title** (pres.asm title_steps, interpreted by ip_next; g-i and the demo slot in as comments mark):
- Loading: entry 2 (the bank to page 6), entry 3 (the art), irq_init; step a's screen is decoded into page 1; then the
  clock starts (OP_SYNC, tick 0). 162 frames from PRES's start in the emulator (two floppy passes ~95, the decode ~65).
- The clock: OP_WAIT n adds n SDLPoP ticks as (frac + 5 n) / 6 frames to an absolute target, the remainder carried
  (t_adv), so every step starts at frame floor(5 T / 6); a draw that runs into a wait does not move the steps after it.
- Drawing: a band is unpacked into DBUF; per row the background is read from page 1 (unless a plain copy), combined
  (copy with the edge masks, transparent through the mask, mono ORed into all planes) and written to VRAM (b, d, f) or
  page 1 (f's logo for j, k's screen, the next a's). c and e copy page 1's box back to VRAM; the fade passes copy page
  1's rows (40 rows x 160 bytes, ~2 frames a pass); a wipe column is 800 bytes (~1 frame), one every 2 ticks.
- Steps (ticks / frames, the emulator: every one exact):

  | | a | b | c | d | e | f | j | k | m (fade-out) |
  |---|---|---|---|---|---|---|---|---|---|
  | ticks | 130 | 205 | 65 | 270 | 235 | 463 + 74 | 80 + 120 | 80 + 360 | 20, then the fade-in 16 |
  | frames | 108 | 171 | 54 | 225 | 196 | 448 | 166 | 367 | 30 |

  f: music 54 starts with the fade-in's last pass (tick 16) and lasts ceil(25.023 s x 60) = 1502 ticks in the ticks
  model (kidsim SOUND_SECONDS), so SDLPoP's f waits 1502 - 905 = 597 ticks. PRES deviates (2026-11-09, the user's
  decision): its title theme (§19, 570 frames a pass) plays exactly twice and f ends 60 ticks (1 s) earlier, a-f 1442
  ticks. f's first wait (TITLE_F_MUSIC 463) ends at tick 1384, frame 1153 = 13 + 2 x 570: after the interrupt that
  played the 2nd pass's last frame; OP_MSTOP (snd_halt: all four attenuations 15) comes before the next one, which
  would start a 3rd pass. That is the pass boundary's own state (the tones are off there, the loop group's first
  frame would mute the noise), so there is no click. The rest (TITLE_F_REST 74 ticks, 62 frames, 1.24 s) is silent;
  g starts at tick 1458, frame 1215. tools/titleref.py computes the ticks (music_stop_tick from the piece's frames in
  assets/sms/pieces.json), tools/build_assets.py writes them to title.inc. j's and k's next screens are decoded into page 1 during their own waits (FRAME + credits after j's wipe, MAIN
  after k's), ~65 frames each. After k: the fade-out (5 passes), then the title again from the fade-in (step 9 puts the
  demo there). Step a's code runs 2 frames after its tick (the last pass is drawn first); the clock is exact.
- Keys (polled once a frame in every wait): first all keys must be let go; then Ctrl+L, or any other key, SHIFT or the
  joystick's fire (CTRL alone nothing) as SDLPoP's process_key: a new game (ACT_PLAY level 1, 60:719, 3 hit points,
  K_TICK .. roomleave_result 0; game_init sets NEED_L1M on level 1, so the crouch music plays) after the screen is
  cleared (SDLPoP: draw_rect black) and the player halted. Ctrl+L: psg_mute (the stream pauses while the floppy runs
  with interrupts off and goes on after), load_saved (save.asm, writing straight into PRES's handoff copy); on success
  ACT_PLAY at the saved level with the saved time and hit points; on failure the title goes on (the steps and the music
  later by the floppy time).

**Tests** (tests/m7_title.py, ~25 min; all ok): 1. one title loop and the next one's first two steps: VRAM at every
step start, at the 10 fade passes, the 5 fade-out passes and 9 columns of each wipe against tools/titleref.py (42
screens, pixel-exact), every step's frame = floor(5 T / 6) (table above), music 54 armed at frame 13 with the
fade-in's last pass and stopped at frame 1153 (2 x 570 frames, the pass boundary; 2026-11-09), the PSG state at the 1,360 interrupts that played a group equal to
sndsim's (tests/m7_sound.py's tracker, the presentation bank). 2. SPACE at step a: the handoff, then main RAM, the
RAM disk, KV, EV and VRAM at level_ready and 100 ticks later as a direct level 1 start, NEED_L1M 1, SND_MODE 1; CTRL
alone does nothing; SHIFT starts. 3. a save made as tests/m5_save.py does (level 3, 41:290, Ctrl+G): Ctrl+L at step b
starts level 3 with that time, equal to a direct start of level 3 with it. 4. Ctrl+L with an empty POP800.SAV: the title
goes on (step c, its screen, the music), SPACE then starts. Gates: tests/m5_boot.py (boot -> PRES -> title, a key ->
game; boot 787 frames, PRES 805, title step a 984, level_ready 1069), tests/m7_launch.py, tests/m5_save.py,
tests/m7_sound.py --quick, tools/perfcheck.py (no game change).

**For steps 7-9:**
- Ctrl+L launches the saved level directly: its cutscene (if the level has one) belongs in front (step 7: ACT_CUTSCENE
  for the saved level instead of ACT_PLAY).
- g-i (step 8): STORY_FRAME + ABSENCE in page 1 during f, the wipe at g, music 55, fade-out, pv_scene, fade-in of FRAME
  + MARRY, then j's target (MAIN + logo + copyright) rebuilt in page 1 during i's wait for music 52, and the wait for
  52 after k. The texts 42-44 are in title.pack (1 bpp) but not in POP800.PRS yet; the art places have 4.8 KB left, so
  the intro's art goes into a second PRS file / per-scene loads. The fade operations exist (OP_FADEIN takes a music id).
- Cutscenes (step 7): PV.DAT's room and bed dither too (above); PRES's band drawer and the page-1 screen are reusable.
- The demo (step 9) replaces the title's OP_LOOP after the fade-out with the ACT_DEMO handoff.

## 16. As built: step 7, the level cutscenes (2026-10-31)

Code: tools/cutsim.py (the Python port of seg001's frame engine and scenes, the EGA reference render), tools/cut_suite.py
(cutsim against SDLPoP), tools/cut_shots.py (silhouettes against SDLPoP's screens), the SDLPoP hook POP800_CUT
(external/SDLPoP/src/pop800_trace.c, seg001.c; tools/sdlpop-pop800.patch regenerated), tools/cutart.py (the art, the
tables build/assets/cut.inc, the POP800.PRS entries), src/pres/cut.asm (the engine), src/pres/pres.asm (the entry, the
cutscene operations, Ctrl+L, the keys), tools/mkgamedisk.py (the entries, POP800.PR2), tests/m7_cut.py; tests/m7_launch.py
now goes through the real scenes. No game-side change: build/m4game.bin and build/m4ovl.bin are byte-identical to
step 6's (play_level's handover before a level with a cutscene is step 1's).

**What the level cutscenes are** (seg001.c; tbl_cutscenes: 2 and 6 cutscene_2_6, 4, 8, 9, 12; load_intro(level > 2)):
- No "until the music ends" loop inside them (pv_scene, time_expired and the ending have those, step 8): 26, 60 (20 + 20 +
  20), 72 (5 + 9 + 58) or 26 (2 + 24) frames of 6 ticks. The music (27: 12.0 s, 35: 10.286 s, 40: 6.857 s) is queued by
  play_sound and started by proc_cutscene_frame after frame 0's drawing. The wait is play_level's: after the scene
  `while (check_sound_playing()) idle();` before the level starts. So the level starts when the scene's music ends.
- Two slots: Kid (the mouse in 8 and 9: kid frames 186-188, the kid pack) and Guard (the princess: frame_tbl_cuts, PV
  chtab 3 res 801-817 and chtab 4 res 901-930; Jaffar's 851-888 when which_imgs = 0, level 2, but cutscene_2_6 uses PV1
  only). The princess's final state is what kidsim's GUARD_LEFTOVER holds (level 2: frame 11 at 120, 166; level 4: 19 at
  92, 162): cutsim reproduces both.
- Per frame: both sequences, the torches (two prandom(255)), the hourglass (the state from rem_min: 3 at 33-64 minutes,
  4, 5, 6 below 6; the sand cycles 0-2), on odd remaining-frame counts a star (prandom(5), its colour index + 1).

**The oracle hook POP800_CUT=<rem_min>** (`prince megahit N`: play_level runs the level's cutscene first). Deterministic:
random_seed 12345 at load_intro (SDLPoP continues the game's seed), current_sound 0, the ticks model at 60 a second
(POP800_CUT_TICKS: ceil(seconds x 60) from kidsim SOUND_SECONDS, each frame takes cutscene_frame_time ticks at its end,
delay_ticks(n) n), no frames in fade_in_1 / fade_out_1 (fade_in_1 copies the offscreen surface to the screen, as its
non-USE_FADE stub: SDLPoP's VGA fade runs proc_cutscene_frame(1) until the palette fade ends, wall-clock dependent; EGA
has the interlaced passes, §15), the frame's timer wait skipped. Per frame a `C` line (n; Kid frame x y dir; Guard frame
x y dir; hourglass state, sandflow; the star drawn and its colour; princess_torch_frame[0..1]; flash_time; the frame
time; next_sound, current_sound, playing), at the end a `W` line (the frame counts of the until-the-music loops, then the
ticks the music has left: play_level's wait). POP800_CUT_SHOTS=<dir> saves the screen of every frame and the room before
the first frame (cut_bg.bmp).

**cutsim** (tools/cutsim.py): KidSim's play_seq / load_frame / load_frame_to_obj (SDLPoP's seqtbl and frame tables) on
two slots, the scenes written as the C functions (pv_scene and time_expired too, for step 8: not yet checked against the
hook), the same deterministic models. `tools/cut_suite.py`: 60 cases (levels 2, 4, 6, 8, 9, 12 at rem_min 60, 30, 10, 3
and the hourglass boundaries 65, 33, 17, 6, 5, 1): every C and W line equal to SDLPoP's (60 of 60, ~4 s).
The render: SDLPoP's offscreen surface with its peels (the midtable items restore what they covered at the next frame)
and the stars drawn on the screen surface. EGA colours per chtab palette: PV.DAT 800 (princess PV1), 850 / 900 (Jaffar /
PV2), 950 (the room res 951, the pillar 952, the hourglass 953-959, the sand 960-962: the dither of its four tables at the
screen pixel, indices 11 and 12), 980 (the bed res 981, dithered, ORed onto the room in EGA colour numbers:
blitters_2_or), PRINCE.DAT 150 (the flames, blitters_0_no_transp: the whole 16 x 18 box), the kid pack for the mouse
(as the game draws the kid: black shows as colour 8); EGA 13 shows black. **Checked against DOSBox's EGA pv_scene** (the
title recording of §15, tools/dosbox_title.py's video): the room + bed (only the sprites, the cursor and the stars differ),
and cutsim's pv_scene frames match the recording's princess, Jaffar, hourglass and pillar with 0 differing pixels outside
the torches, stars and cursor; the torch boxes match a cutsim frame with the same flames (0-1 pixels).
Silhouettes against SDLPoP's VGA screens (tools/cut_shots.py, the cases of tests/m7_cut.py): SDLPoP's pixels that differ
from its room (cut_bg.bmp) all lie inside cutsim's drawn objects: 0 outside pixels in every frame of every case; ~34% of
the covered pixels show no difference in VGA (the flames' black box parts, sprite pixels in the room's colours).

**The engine** (src/pres/cut.asm, assembled after PRES's own image: POP800.PRS's room entry carries it):
- Scenes are scripts in the title's step interpreter (ip_next) with new operations: OP_CSND (play_sound), OP_CHG
  (set_hourglass_state(hourglass_frame())), OP_CLOAD / OP_CSAVE (Char <-> a slot), OP_CSET (a Char field), OP_CSEQ
  (seqtbl_offset_char: the offset, from cut.inc), OP_CPLAY (play_seq), OP_CFRAMES n (proc_cutscene_frame(n)), OP_CIF6
  (cutscene_12's branch), OP_CEND (the end), and for step 8 OP_CFT, OP_CUNTIL, OP_CFLASH, OP_CHGN, OP_CSAND (not used
  yet). The five scripts copy the C functions line by line (the character setups as macros: init_princess, init_mouse_go,
  seqtbl_offset_*_char).
- play_seq reads SDLPoP's sequence table where the game keeps it: logic.bin in RAM-disk page 6 at 0xD000 (it is there
  at PRES time: the boot writes it, nothing overwrites it; PRES's own scratch in page 6 is 0x0000-0x287F); the kid's
  frame table also from logic.bin (0xDA00), frame_tbl_cuts in cut.inc. prandom is room.asm's generator. The sound: the
  queue with SDLPoP's priorities (cut.inc), play_next_sound only when nothing plays, the ticks model (cut_left, the
  music's end tick cut_musend) and the PSG player (psg.asm snd_start, the presentation bank in page 6 as for the title).
- Drawing: the objects of a frame in SDLPoP's order (torch 1, torch 0; the characters by obj_y, the princess first at
  equal y; the hourglass; the pillar; the sand), each a pre-shifted, pre-flipped byte-aligned sprite (tools/cutart.py: every
  (image, flip, x & 7) a scene draws, found by cutsim over the scene; the engine looks it up by chtab | flip, image, shift;
  the flames, hourglass, sand and pillar at their fixed places). Format: wb, h, then per row and column the inverted mask
  and the four planes. Dirty rectangles: per object identity (kid slot, shad slot, the torches, hourglass, pillar, sand)
  the image and place last drawn; a change makes the old and the new box dirty, a star's colour change its pixel;
  overlapping rectangles merge; each rectangle lists the objects that cover part of it (columns and rows clipped once),
  then row by row: the room's row from page 1 (INIR), the objects (RB = RB AND mask OR plane, 4 planes per column),
  the stars, the row to VRAM (LDIR per plane). RB is 0xA000-0xA3FF (a page per plane, indexed by the byte column). The
  room is in page 1 as the title's screens are (load_intro's offscreen surface: res 951, the bed, the stars' first colours,
  drawn by the title's draw_img from 4 PZ bands); the pillar counts as drawn from the start (the room has it pixel for
  pixel: cutart asserts it), so frame 0 does not redraw it. The mouse leaving at the right is clipped at the screen's
  edge (columns <= 39); off the screen (its x wraps) it is not drawn, as SDLPoP's clip does.
- Timing: the title's clock (t_adv / t_wait; t_adv also counts ct_tick, zeroed by OP_SYNC). The scene: OP_SYNC, the setup,
  OP_FADEIN (the EGA fade-in: 5 interlaced passes of the room, 4 ticks apart), frame k at tick 16 + 6 k, OP_FADEOUT (5
  passes), OP_CEND: waits until the music's end tick (the ticks model: frame 0's tick + ceil(seconds x 60)), then the
  level (ACT_PLAY with the handoff as the game sent it: the time and the hit points unchanged). A frame starting
  SKIP_LATE = 4 frames or more after its time is not drawn (its logic runs; the next drawn frame repairs the screen
  through the same dirty boxes); the flash (step 8) sets PLT0 for 2 ticks of the frame.
- Keys: in every wait; first all keys let go, then any key or fire aborts as do_paused does: the player halted, the screen
  black, the level at once (cut_abort). Ctrl+L on the title with a save on 4, 6, 8, 9 or 12 (p_play): the cutscene first
  (the title's sound bank kept), then the level with the saved time.
- The flow: ACT_CUTSCENE -> p_cutscene: the sound bank (PRS_SOUND, unless the title loaded it), PRS_CROOM (the engine, the
  room's bands, the common sprites), cut_main: the room into page 1, the scene's entry (its sprites and cut_spr), irq_init,
  the script.

**Timings** (the emulator; SDLPoP ticks, frames of 50 Hz):

| Scene (level) | frames | music | the level starts at tick (= music start + its length) | from PRES's start (frames) |
|---|---|---|---|---|
| cutscene_2_6 (2, 6; 12 from 6 minutes) | 26 | 27 | 736 = 16 + 720 | ~160 loading + 613 |
| cutscene_4 | 26 | 27 | 736 | ~160 + 613 |
| cutscene_8 | 60 | 35 | 634 = 16 + 618 | ~176 + 528 |
| cutscene_9 | 72 | 35 | 634 | ~176 + 528 |
| cutscene_12 below 6 minutes | 26 | 40 | 428 = 16 + 412 | ~174 + 356 |

SDLPoP (the hook's W line) and PRES agree: the music starts with frame 0 and the level starts when it ends (in SDLPoP
the fade-in runs before frame 0 too; the 16 ticks of PRES's fade-in come before the music, as in the original). Every
frame starts exactly at floor(5 T / 6) of the clock (tests/m7_cut.py). Loading: launcher -> PRES 18 frames, then PRES's
three floppy loads (the bank 25 blocks, the room entry 65, the scene 1-17) and the room's decoding into page 1 ~160-176
frames (~3.3 s in the emulator; a real drive is slower, ~0.5-1 s); after the scene, PRES -> game start 64 and
level_ready 20 frames as before.

**Frame cost** (logic + drawing, MZ frames; budget 5 = 6 ticks): the torches, the sand and a star ~2.3-2.6 a frame; the
princess turning or crouching up to 5.3, the mouse and the princess together ~4-5; frame 0 (everything new) 5.3-5.7.
Every frame is drawn in all cases (0 skipped): frame 0's overrun makes frame 1 start up to 3 frames late, under
SKIP_LATE. (Before the column-interleaved sprite rows and the per-rectangle object lists: median 3.1-4.3, 1-4 frames
skipped per scene.)

**POP800.PRS** (255 blocks = 0xFF00 bytes: full; 552 + 255 blocks on the disk):

| Entry | Blocks | Content |
|---|---|---|
| 0 PRES | 11 | build/pres.bin up to end_of_pres (3,681 bytes at 0x2000) |
| 1 placeholder | 1 | the stubs' message (time expired, ending: step 8) |
| 2 sound bank | 25 | as step 6 |
| 3 title art | 107 | as step 6 (4,805 bytes of its places left) |
| 4 PRS_CROOM | 65 | the engine (0x2E61-0x3ED9, 4,217 bytes: code, scripts, cut.inc's tables, variables), the room's 4 PZ bands (10,073 bytes, stored, at end_of_cut..), art_idx slot 0, the common sprites (8,458 bytes: 18 flames, 7 hourglass states, 3 sand, the pillar; 0x1200-0x1FFF, 0xDF40-0xEBF6, 0xEC00-0xF36F) and cut_com |
| 5-9 PRS_C26, C4, C8, C9, C12 | 1, 2, 14, 17, 11 | the scene's character sprites (1, 1, 23, 26, 11 sprites: 647, 877, 8,681, 10,372, 7,712 bytes, at end_of_cut..0x675D) and cut_spr |

The file is full: step 8's entries go into POP800.PR2, which tools/mkgamedisk.py writes as the blocks right after
POP800.PRS (asserted from the directory): the launcher reads an entry as blocks counted from POP800.PRS's first block,
so an entry may lie in either file or across both with no launcher change.

**PRES memory during a cutscene:**

| Range | Use |
|---|---|
| 0x03C8-0x03DC, 0x0800 | SP_VARS, FRAMES (as step 6) |
| 0x1200-0x1FFF | common sprites (read only while VRAM and the CG ROM are not mapped) |
| 0x2000-0x2E60 | PRES (3,681 bytes: the title, the interpreter, the drawing of step 6, the dispatch) |
| 0x2E61-0x3ED9 | the cutscene engine (PRS_CROOM) |
| 0x3EDA-0x7FFF | the room's PZ bands, then (after their decoding) the scene's sprites (at most 10.4 KB) |
| 0x8000-0xBFFF | the launcher's (loads); after the loads RB 0xA000-0xA3FF |
| 0xC000-0xDF3F | DBUF (the room's bands are unpacked here) |
| 0xDF40-0xEBF6, 0xEC00-0xF36F | common sprites (not 0xEBF7-0xEBFF: tests/m5_boot.py) |
| 0xFD00-0xFEFF | the stack, the IM2 vector, the PSG ring |

RAM-disk scratch as step 6 (the room in page 1, the bank in page 6 0x0000-0x287F); logic.bin in page 6 is read only.

**Tests** (all ok):
- tools/cut_suite.py: 60 of 60 cases, C and W lines equal to SDLPoP's.
- tools/cut_suite.py --shots DIR + tools/cut_shots.py DIR (8 cases): no SDLPoP silhouette pixel outside cutsim's
  objects.
- tests/m7_cut.py (~15 min): 1. levels 2:60, 4:30, 6:10, 8:60, 9:3, 12:60, 12:3 (every scene, the hourglass states 3-6,
  both branches of 12): every C line equal to cutsim's, VRAM pixel-exact against cutsim's render after every drawn frame
  (all drawn), the fade-in's passes, every frame's start frame, the music with frame 0, the end tick (= the W line's), the
  screen black, then the level with the handoff's time. 3. SPACE at frame 20 of scene 8: aborted at once, black,
  level 8 starts. 4. Ctrl+L at the title with a save on level 4 (made as tests/m5_save.py does): the level 4 scene
  (exact as in 1), then level 4 with the saved time and hit points.
- tests/m7_launch.py: the round trip goes through the level 4 cutscene (771 frames in PRES: loading, the scene, the
  music to its end), level 1's end through the level 2 cutscene (836 frames from PRES to level 2's start): level 2
  equals the direct path tick by tick (logic, time, VRAM).
- Gates: tests/m7_title.py, tests/m5_boot.py, tests/m5_save.py, tests/m7_sound.py --quick, tools/perfcheck.py (no
  baseline update), tools/oracle_suite.py (the SDLPoP patch changed; the old hooks unchanged).

(Step 8 replaced the fades' model, the 200 rows of the level scenes' room and the black of the palette: §17.)

**Assumptions and limits (not verified):**
- That the EGA fade_in_1 / fade_out_1 run no cutscene frames is a decision, not a finding (§17: wrong, one frame each): SDLPoP's EGA branch is empty and
  the DOSBox recording only shows the passes, while the princess stands still. If the original runs frames during its fades,
  the scenes' frame counts and the music's start would differ from it (the hook and cutsim share this model, so the
  oracle cannot detect it). The fades' 4-tick spacing is step 6's.
- The seed, the stars' colours and the torch frames start fresh per scene (SDLPoP continues them): deliberate, in the oracle too.
- The DOSBox check is a sample: 9 recording times in pv_scene (best match over all cutsim frames, torches, stars and cursor
  masked), then 4 times for the left torch only (one has 1 differing pixel, not explained). Level scenes' PV2 sprites and the
  mouse were never compared with DOSBox: pv_scene does not show them; only their silhouettes against VGA are checked.
- The 34% "coincidences" in tools/cut_shots.py were looked at in one frame only (scene 8: the flames' boxes).
- The cutscene music is checked only for its id and start frame, not against sndsim per frame as in tests/m7_title.py.
- Not executed by any test: OP_CFT, OP_CUNTIL, OP_CFLASH, OP_CHGN, OP_CSAND and the flash's palette code, the SEQ_SOUND path
  of play_seq. The skip path (SKIP_LATE) no longer triggers in the final build: it was last exercised, VRAM exact, with
  SKIP_LATE = 3. POP800.PR2 is not on the disk now: the split was built once, before the sprites shrank, and never booted.
- Floppy times are the emulator's (no rotation); real-drive times are estimates.

**For steps 8-9:**
- pv_scene and time_expired are in cutsim (pv_scene's frames match DOSBox's recording) but not yet in the hook's checks
  (POP800_CUT only runs play_level's scenes; pv_scene needs a hook entry from show_title, time_expired from expired());
  their until-the-music loops are OP_CUNTIL (frames counted in the W line), the flash OP_CFLASH (PLT0 for 2 ticks: check
  in DOSBox whether EGA flashes at all), the hourglass operations OP_CHGN / OP_CSAND; cutscene_frame_time 8 and 7 go
  through t_adv's remainder (5.83 / 6.67 frames).
- Their art: Jaffar (PV res 851-888, palette 850, ~30 more sprites with shifts), the empty glass (state 7 is in the
  common sprites), the ending's kid (the kid pack's frames, as the mouse) and the hail screen; POP800.PR2 for the entries.
- The ending's first frame uses copy_screen_rect of the previous screen (no fade-in) and the kid runs in from the right.
- The demo (step 9) replaces the title's OP_LOOP as planned; nothing in the engine is needed for it.

## 17. As built: step 8, the intro story, the time-out and the ending (2026-10-31)

Code: src/pres/pres.asm (the step table g-m, the ending's steps, the keys, the loads; the stubs and the font removed),
src/pres/cut.asm (the fade frames, pv_scene, time_expired, end_sequence_anim, the PZ sprites, the flash palette, the 192-row
room), tools/cutsim.py, tools/cutart.py, tools/mkgamedisk.py, tools/build_assets.py + tools/titleref.py (the red frame), the
SDLPoP hook POP800_CUT_SCENE (tools/sdlpop-pop800.patch regenerated), tools/cut_suite.py, tools/cut_shots.py, tools/dosbox_scene.py (new: DOSBox
scenes from a prepared save), tests/m7_story.py (new), tests/m7_cut.py, tests/m7_title.py, tests/m7_launch.py. No game-side change:
build/m4game.bin and build/m4ovl.bin are byte-identical (md5 c833e8ba.., c8ea1f3a..).

**DOSBox (machine=ega; tools/dosbox_scene.py).** The recordings stay in build/dosbox/scene/ with a private copy of the game in
which only the copy protection's level (PRINCE.EXE v1.3 0x1B89B, SDLPoP options.c) is patched, so that a prepared PRINCE.SAV plus Ctrl+L
reaches any scene without the potion test. (`prince megahit N` does nothing useful in this EXE.)
- **The fades run one frame each, not none: step 7's assumption was wrong.** After the last pass frame 1 comes, but the pass already shows the
  sprites, the torches, the hourglass and the sand, and one star has moved (star 0 is colour 15 at the end of the fade-in, 7 after load_intro; a level
  scene after a fresh start, so no earlier scene moved it). Nothing changes between the passes (the row sets of consecutive changes hold only the
  pass's rows, no torch, no sand), at 3000 and at 30000 cycles. So the EGA fade_in_1 is the VGA code's loop with the
  first proc_cutscene_frame(1) drawing into the offscreen surface and the fade ending at once: one frame, wait_frames = 1 (hence the star), then the passes. The fade-out
  is taken as the same code: its frame shows nothing (only C lines and RNG can tell; not visible in DOSBox). Times: the passes 4 ticks apart, the
  next frame ~4 ticks after the last pass (3.3 video frames at 30000 cycles, 5 at 3000): FADE_TICKS = 20, frames then every 6 ticks (cutscene_8: 60 frames
  between the fades, exactly). The fix: cutsim (fade_in_1 / fade_out_1: proc_cutscene_frame(1) with FADE_TICKS instead of the frame time), the hook (the same;
  every scene has 2 C lines more, the queued music starts in the fade-in's frame, 20 ticks earlier against the frames than step 7 had), the engine (OP_CFADEIN: the frame's logic, then per
  pass the room's rows and the objects' rows of the pass; OP_CFADEOUT), all scripts. tests/m7_cut.py and tools/cut_suite.py rerun: green.
- **The flash exists in EGA:** 5 flashes, ~2-3 of the 5.8 video frames each, EGA attribute 0 only turns white. EGA 13 (black too on the screen) stays
  black: 21,200 pixels change, 6,358 black ones do not. To match it, attribute 0 is now MZ 4 and EGA 13 MZ 0: the cutscene palette is group 1 with PLT0 = black, so MZ 4 shows black
  (EGA 2, whose MZ value it was, occurs in no cutscene art: cutsim and cutart assert it), and the flash sets PLT0 = 15 as step 7's code did. PRES puts group 0 back before the title and the game.
- **The level scenes' room has 192 rows** (found by the same recording, a step 7 bug not caught by the silhouettes): the game's offscreen surface is 320 x 192 (seg003.c), so rows 192-199 stay black in the level
  scenes and the ending, while pv_scene (show_title) and time_expired (expired) have a 200-row surface. p1_black clears them in page 1; the scene record has a flag. DOSBox and SDLPoP agree.
- **The hail screen's frame is red:** load_title_images(0), index 14 of the palette (19,590 pixels). SDLPoP's EGA branch is an empty `// ...`, DOSBox shows it. A 4th variant of res 41 in title.pack (pseudo res 46, FRAME_RED), PRS_T_FRED.
- **A key ends the hail and TITLE_MAIN waits** (do_wait: word_1D63A is 1; DOSBox's hail lasted 1.1 s under a key), not the final wait for the music, not time_expired, not the embrace. Without a key 900 and 240 ticks as SDLPoP.
- **Sprites against DOSBox** (`dosbox_scene.py compare`: every change of the screen against the best cutsim frame; torches, stars and the cursor masked): level 8 and 9 (mouse, PV2 princess), level 4 (PV2 lying), level 12 below 6 minutes, the ending (kid, PV2 hug, mouse), pv_scene from the title recording: 0 differing pixels in every
  settled frame; the only differences are changes the recording caught half drawn. The kid: the game's pack shows his black as colour 8; EGA shows black, so the cutscene sprites have MZ 0. Hail screen and TITLE_MAIN after it: pixel-exact outside the cursor.
- **Not compared:** the music against the frames. DOSBox's audio showed no tones (SDL's disk driver: a constant DC level in the run inspected, similar sample statistics with SETUP.DAT's byte 2 at 0-7; the sound settings were not explored further), so the music's start relative to the fade could not be heard; it follows from the fade being a proc_cutscene_frame. The EGA torch and star RNG (SDLPoP's seed continues; a fresh one here, deliberately). The fade-out's invisible frame. Real hardware.

**The scenes** (cutsim and POP800_CUT_SCENE=pv|expired|ending; ticks of the scene; W: the until-the-music waits):

| Scene | frames (with the 2 fade frames) | ticks | W line |
|---|---|---|---|
| pv_scene | 368 | 2562 (then 52 has 1287 left) | 145, 1, 27 frames |
| time_expired | 104 | 872 = music 36 | 220 ticks |
| end_sequence_anim (no fade-in: 1 fade frame) | 105 | 840 = music 26 | 196 ticks |

Timing against SDLPoP: C and W lines equal in all 63 cases (60 level, 3 named). The title's clock, ticks / frame = floor(5 T / 6): g 1518, h 2218, pv_scene 2463 (when music 55 ends, as load_intro waits) to 5025, i 5151, j 6442, k 6642, m 7082, the title again 7102 (118 s). Against SDLPoP the title has
110 ticks before i and 130 before j more (TITLE_I_LOAD, TITLE_J_LOAD: decoding the screens in page 1; SDLPoP decodes during its i wait, but the floppy read here would stop music 52, so PRES reads when it has ended). The ending: embrace 840, hail 16 + 900, the wipe and TITLE_MAIN 240, then until 7482 after the music's start, fade-out 20.

**Art and memory.** PRES 3,465 bytes (0x2000-0x2D88: the stubs and font gone), the engine 4,935 bytes (to end_of_cut 0x40D0).

| Blocks | Entries (POP800.PRS block 552, 255 blocks, full + POP800.PR2 block 807, 202 blocks; index 1; 457 in all, 271 of 1280 free on the disk) |
|---|---|
| 10, 1, 25 | PRES; 1 PRS_CEXP (time_expired's empty sprite table; was the placeholder); 2 the sound bank |
| 65, 13, 11, 13 | 3-6 PRS_T_MAIN, _PG (res 52, 53), _LOGO (54, 55), _FRAME: the title's art, each entry its PZ bands and art_idx slots at fixed places |
| 7, 6, 6, 7 | 7-10 PRS_T_ABS, _MARRY, _CRED, _HAIL: the 1-bpp texts, one shared place (1.7 KB) |
| 77 | 11 PRS_CROOM: the engine, the room's bands (12,370 B: attribute 0 no longer all-zero planes), the common sprites (8,458 B) |
| 1, 2, 15, 17, 11 | 12-16 the level scenes |
| 88, 32 | 17-18 PRS_CPV, _CPV2: pv_scene's 115 sprites (103,880 B raw) as one PZ block each (28,531 B) |
| 36 | 19 PRS_CEND: the ending's 36 sprites (23,712 B, unpacked in the places) |
| 13 | 20 PRS_T_FRED: the red frame |

Nothing of it in the RAM disk beyond the old scratch (D2/D3). PRES's memory per scene (the art's 3 places: 0x1200-0x1FFF, end_of_pres..0x7FFF, 0xDF40-0xFBFF without 0xEBF7-0xEBFF):

| Scene | Loaded | Space |
|---|---|---|
| title a-g | MAIN, PG, LOGO, FRAME, ABSENCE (5 entries; ~45 frames more than one) | all title art together: 1,576 B of the places left |
| pv_scene | CROOM, the room to page 1, CPV2 (at DBUF, copied to 0x8000-0x9F3F), CPV | engine + room bands, then the PZ sprites end_of_cut-0x7FFF, DBUF, 0x8000-0x9F3F: 3,645 B left; slot buffers 0xA400 / 0xA940 (1,344 B each, largest sprite 1,227), RB 0xA000; cut_spr 0xF400-0xFBFF |
| i | FRAME, MARRY | over the engine |
| j, k | MAIN, LOGO, CREDITS | |
| time_expired | CROOM, CEXP | common sprites only |
| ending, hail | CROOM, CEND, then FRED, HAIL, MAIN | sprites end_of_cut-0x7FFF, DBUF |

A floppy read during music: OP_LOAD mutes the PSG (psg_mute), the stream pauses, FRAMES too (interrupts off), so the clock stays exact. It happens at h (music 55's tail) and before i (52's); the length of the gap was not measured (the emulator's floppy has no rotation).

**The PZ sprites:** pv_scene's sprites do not fit unpacked. A character's frame looks up its entry (now 8 bytes, with wb and h, so no sprite data is needed for the rectangles, a slot's last entry first); when the frame is drawn (never when it is skipped) and its entry changed, its block goes into the slot's buffer; the dirty-rectangle state keys on the entry, not the data address. The other scenes keep their sprites unpacked.

**Frame cost** (logic + drawing, MZ frames):

| Scene | budget | median | max | skipped of drawn |
|---|---|---|---|---|
| level scenes (7 cases) | 5 | 2.48 | 5.40 | scene 9: frame 2 only |
| pv_scene | 5, 6.67, 5.83 by frame time | 2.06 | 9.28 (two characters unpacked and redrawn) | 5 of 366 (322, 328, 331, 340, 342), all at the end of the conjuring, frame time 7 |
| time_expired | 5 | 1.91 | 1.92 | 0 |
| embrace | 5 | 1.96 | 6.89 (kid + hug) | 2 of 104 (12, 15) |

The fade-in's passes take ~4 frames against 3.33 (the room's rows ~3.3, the objects' rows), so the first frame after them starts up to 6 frames late; it is always drawn (cut_fresh); the clock catches up over the next frames (scene 9's frame 2 is skipped on the way).

**Tests** (all ok, final binaries):
- tools/cut_suite.py: 63 of 63 (C and W lines equal to SDLPoP's). tools/cut_suite.py --shots + tools/cut_shots.py, 10 cases incl. the named scenes: 0 silhouette pixels outside cutsim's objects (coincidences 34-47%, reported only).
- tests/m7_cut.py (now with PSG, palette, fades' passes; levels 2:60, 4:30, 6:10, 8:60, 9:3, 12:60, 12:3): C lines, VRAM after every drawn frame, every frame's clock, PSG per frame against sndsim. A key aborts. Ctrl+L: a save on level 4 and on level 9 (scene, then the saved time and hit points), on level 5 (no scene: the level at once).
- tests/m7_story.py: title h-m with POP800.PR2 read from the disk (C lines, VRAM, fades, flash, PZ, i, j, k, m screens, PSG against sndsim through the whole title); time_expired; the ending (embrace, hail, wipe, TITLE_MAIN, music 56 by the ticks model, PSG); keys at q, s and in the scenes; SPACE at g, h, i, j, k: level 1, after pv_scene equal to a direct start (main RAM, RAM disk, KV, EV, VRAM, at level_ready and 100 ticks later); Ctrl+L in pv_scene with an empty save: the title starts again; forced lateness; the flow: a poked clock running out in the launched game -> time_expired -> title -> new game = direct level 1, the palette back; level 14 from the title with the kid walking (a script, button, gates, room 5) -> the ending -> title -> new game = direct level 1.
- tests/m7_title.py now covers a-g (25 screens; j, k moved to m7_story) and its keys and Ctrl+L parts. Gates: tests/m5_boot.py, tests/m7_launch.py, tests/m5_save.py, tests/m7_sound.py --quick, tools/perfcheck.py (ok, +0.5..+2.1% with an unchanged game, as step 7 reported; no baseline update), tools/oracle_suite.py (the patch changed; its old hooks unchanged).

**Formerly untested code, and what runs it now:** OP_CFT, OP_CUNTIL, OP_CFLASH, OP_CHGN, OP_CSAND, the flash's palette: pv_scene in tests/m7_story.py title (C lines; the palette read from the GDG at tc_flash and at every frame start); OP_CHGN and OP_CSAND also time_expired. play_seq's SEQ_SOUND: the ending's kid (the footstep, id 23 in the C lines). **That path had a bug:** play_sound lost the id when a sound was queued (next_sound -58 in the C line; found by this test, fixed). The other SEQ_SOUND ids (bump, drink, the level's music) occur in no scene's sequences: removed. SKIP_LATE: tests/m7_story.py late: FRAMES pushed at chosen frames of scenes 8 and 9: frames skipped, C lines exact, every drawn frame VRAM-exact, the clock unchanged; and it occurs by itself now (above).

**Limits:**
- `cut_len60` keeps the MIDI lengths (D4); DOSBox's device could not confirm them. The level's music start moved 20 ticks with the fades' model; the level start equals the hook's W line.
- A flash's write can fall anywhere in the raster; PLT0 for 2 ticks (1.67 MZ frames, EGA ~2.4).
- The EGA fade timing is taken from DOSBox's 50 Hz recordings (±1 video frame).
- Ctrl+L inside pv_scene when the disk has no save restarts the title (load_saved's buffers overlap the sprites) instead of going on: SDLPoP goes on.
- Floppy times are the emulator's.

**For step 9:** the title's end is OP_TITLE after m's fade-out: the ACT_DEMO handoff goes there. The title reloads its art from the floppy at every start now (5 entries, 225 frames from PRES's start to step a in the emulator).

## 18. As built: step 10, the keys and the cheats (2026-10-31)

Code: src/m4/keys.asm (new: key_logic, the cheats), src/m4/keyres.asm (new: key_scan, block 2), src/m4/ovl_keys.asm (new: W1
overlay OVL_KEYS: key_read, key_tab, do_pause, snd_onoff, blind_set), src/m4/ovl.asm (stubs), game.asm (get_controls, read_inputs,
the main loop's blind check under CHEATS), kid.asm (one call at the control point), guard.asm + levelstart.asm (the tables), text.asm
(the new texts; a TEXT_MSG shows through the blink's dark phase), ovl_level.asm + src/pres/pres.asm (the sound-off option), psg.asm
(labels spo_1-3 only: the code is unchanged), m4test.asm, Makefile (`make m7keys`, `make cheats`), tools/kidsim.py (process_key,
KEY_*, `# cheats`), tools/oracle.py, tools/build_assets.py (glyphs), SDLPoP hooks (pop800_key_code, pop800_next_key, pop800_title,
POP800_NOCHEATS; tools/sdlpop-pop800.patch regenerated), tests/m4_test.py, tests/m7_keys.py (new), 15 scripts tests/m7_scripts/key_*.

**Room.** guard.asm's constant tables (strikeprob .. tbl_guard_type: 88 bytes, not 84) moved to 0x9F90 (GUARD_TABS), copied by
game_init from the level-start overlay. The Ctrl+A / Ctrl+G edge code, the Ctrl+A branch in kid.asm and the SPACE branch left main.
Free after: main 6 (end_of_code 0x7BFA), low 53, block 2 61 (block2_end 0xEBC3). The design's ~100 B resident became: key_scan 33 B,
two stubs 16 B, the script prefix 13 B, the call in kid.asm 8 B.

**Dispatch.** Script byte `0x40 + code` before a control byte; a script field = Ctrl+A | code << 3; KEYS has the same layout. On the
keyboard path key_scan looks at BREAK, CTRL, SPACE, ENTER, L only: if none is down KEYS = 0 and nothing else happens. Otherwise the
overlay loads (~0.3 frames, once; only the room and events overlays are displaced, their stubs reload them), and key_tab finds the
first key down with exactly its modifiers, as process_key compares them; one action per press. key_logic runs at the tick's control
point, where the oracle's hook runs SDLPoP's real process_key, so the same tick order holds (timers and mobs before the key).

| Key | Matrix | Effect | SDLPoP check |
|---|---|---|---|
| BREAK (any modifiers) | 8/7 | pause, below | key_pause (code 7: Esc + a key through do_paused) |
| SPACE (no modifier) | 6/4 | is_show_time = 1 | key_space, key_space_guard |
| SHIFT, fire | 8/0, joy | the button; SPACE no longer is | m7_keys |
| Shift+L | 3/4 + SHIFT | levels below 4: next level, time cut to 15:719 when above 15 minutes, stop_sounds, level changes after this tick | key_shift_l, _cap3, _nocap, _level4 |
| Enter (no modifier) | 0/0 | alive > 6, time left, not level 15: as Ctrl+A | key_enter_dead |
| SHIFT while dead | | WANT_RESTART, as before | m7_keys (game only) |
| Ctrl+R, Ctrl+Q | 2/6, 2/7 | GAME_OVER 3, the tick ends as a restart's: PRES title (harness: a new game) | key_ctrl_r (marker TITLE) |
| Ctrl+S | 2/5 | sound off/on, text 24 ticks | key_ctrl_s |
| Ctrl+V | 2/2 | 'PRINCE OF PERSIA V1.0', 24 ticks | key_ctrl_v (timers) |

**The pause: the stream resumes.** do_pause holds SP_WAIT in the overlay (0 for the ISR), mutes, and at the resume restores SP_WAIT and
writes the attenuations back from ENV (the tones stay latched), so §14's warning no longer applies: a live wait just lasts longer and ends
where it would have. Chosen because it costs only overlay bytes, psg.asm's code stays untouched, and the death text no longer comes early.
Ticks do not run during it, so the clock is not charged. Tested: the PSG state at each of 320 player frames equals a run with no pause.
Resume: any key but CTRL / SHIFT alone, or fire, after all keys were let go. As do_paused, the resume erases the bottom text and its
timers (a pause over the death text therefore cancels the return to the title, as in SDLPoP).

**Ctrl+S.** Two NOPs replace each of the player's three OUTs (patched by the overlay; the option HO_OPTIONS bit 0 reapplies it in
the launched game and PRES). The stream runs silently, as SDLPoP's mixer does, so live and ticks waits are unchanged.

**Intentional differences from the original:**
- Sound off, sound model: SDLPoP with is_sound_on = 0 asks for no death music, no level-end music and no level 1 crouch music, which
  shortens those waits. Here the requests and waits stay as with sound on (the brief for this step), so an oracle script must not combine
  Ctrl+S with those events.
- The key that resumes a pause has no effect of its own (SDLPoP processes it; Esc would pause again). Fire also resumes.
- Ctrl+V's text: SDLPoP prints its own version; the string is the original's commented-out one.
- Shift+L does not skip the next cutscene when SHIFT stays held (PRES counts keys only after they were let go).
- Ctrl+S, Ctrl+R etc. act in the game only; on the title any key starts a game, as before.
- Cheats: R revives at once without resurrect_time's 20 protected ticks and set_start_pos; T shows a 24-tick text instead of a permanent
  timer; Shift+B blanks once and stops all drawing; F1 / F2 are + / -.

**Cheats.** `make cheats` assembles the sources with CHEATS=1 in build/cheat (art shared, build/ untouched), including a disk,
build/cheat/build/pop800.dsk. Same keys overlay, 832 bytes instead of 469. Resident: key_scan + 13 B in block 2 (48 free), the main
loop + 8 B, absorbed by room.asm's page alignment near 0x4100 (main end unchanged). Release: 0 B of cheat code (symbols absent; the jump
table and K's routine not found in the release binaries). K, +, -, Shift+T, Shift+S, Shift+W, Shift+I, H/J/U/N, Ctrl+B and Shift+L
above level 3 are checked kidsim against SDLPoP and Z80 against kidsim (key_cheats, key_cheat_kill, key_cheat_l5); R, Shift+B and T on
the keyboard only (m7_keys). In the release m4_test expects these scripts' cheat codes to do nothing.

**Limits / not compared:** key_silent's codes run with cheats off only. The pause on the real keyboard path has no oracle: its logic part
is compared through code 7. Ctrl+V's and the pause's text pixels are against the Python reference, not SDLPoP shots. No resident room
is left to speak of in main: OVL_MAX 8 is full too (raise it for the next overlay).


## 19. As built: the presentation music (2026-11-01)

Code: tools/presbank.py (new: the three banks from build/sound/sms/*.vgm + the effects), tools/vgm2psg.py (encode(loop=),
verify of a looping stream), tools/sndsim.py (Bank.loops, Player.fill's loop, sound_states / consumed / max_gap with a frame
count), tools/sndconv.py (no longer writes sound_pres.bin; make_bank(loops)), src/m4/psg.asm (snd_fill: the loop command; the
ISR untouched), src/pres/pres.asm (OP_MSTOP, OP_LOADB, load_bank(A = entry) with bank_cur, the step table h-m and the
ending), src/pres/cut.asm (play_next_sound: a cue without a stream in the bank starts nothing), tools/cutsim.py (PRES_TICKS60),
tools/mkgamedisk.py (entries PRS_SND_B, PRS_SND_C), Makefile (sound_pres.bin: presbank.py), tests/m7_sound.py (the tracker's
fill through MF_W, the loop wraps, part A on the new banks), tests/m7_title.py, m7_cut.py, m7_story.py (the loops, the bank
reloads, the WAVs build/sound/pres/*.wav). The in-game bank build/assets/sound.bin is byte-identical; the game's binary changes
only by snd_fill's 36 bytes (block 2).
Since 2026-11-02 the five pieces are committed as converted streams (assets/sms/, its README; not GPL) and presbank.py
builds the banks from them (byte-identical); `presbank.py --from-vgm build/sound/sms` remakes them from the VGMs locally.

**The mapping** (decided 2026-11-01; every screen keeps its DOS duration from the ticks model unless stated; a piece shorter
than its screen loops, a longer one is cut at the screen's end). The streams are the exact variants (every attenuation change a
command; the tones rescaled by 1.0000006), build/sound/sms/index.txt:

| Screen | SMS piece (frames) | PRES id(s) | Loop | Bank |
|---|---|---|---|---|
| Title a-f (MAIN .. logo) | 01 title (570 = 11.40 s) | 54 | whole; stopped in f after exactly 2 plays (1140 frames), f 60 ticks shorter (§15) | A |
| Story text g, into h's black and fade-in | 11 hourglass (985) | 55 | from frame 25 (0.50 s intro, 19.20 s loop) | A, B (same address) |
| pv_scene h from its first cue (frame 2), "Marry Jaffar" i | 05 story_jaffar (1220 = 24.40 s) | 50 | whole | B |
| Main picture j | 01 | 54 | whole | C |
| Credits k | 03 story_credits (501 = 10.02 s) | PM_CREDITS 42 | one-shot, cut by OP_MSTOP at m (k lasts 440 ticks = 367 frames) | C |
| Level cutscenes 2/6, 4, 8, 9, 12 | 07 cutscene (432 = 8.64 s) | 27, 35, 40 | one-shot: the level starts when it ends | A |
| Time-out | 11 | 36 | as g | A |
| Ending: embrace, hail, TITLE_MAIN | 01 | 26 | whole; cut at step t after 3 plays (2052 ticks from the embrace's start) | A |

The pv_scene cues 4, 51, 53, 52 and the hail's 56 start nothing: Jaffar's piece / the title theme loop on. The cues'
ticks model (cut_left, mus_end) runs exactly as before, so every screen's duration is the DOS one: g 600 ticks, h waits for
55's DOS end (945 ticks after g's start) before the fade-in, i until 52's DOS end (1734 ticks after its cue), j 80 + 120,
k 80 + 360, the embrace 840 (26), the hail 16 + 900, the wipe + TITLE_MAIN 240.

**Bank reloads** (load_bank: the entry to SBANK_TMP, then 0x2880 bytes to the torch cache; op_loadb mutes for the floppy read
as OP_LOAD does, the stream pauses, FRAMES too): bank B at h (before PRS_CROOM; g's hourglass stream sits at the same bank
address 228 in A and B, so it plays on through h's black wait and the fade-in until the cue 50 at frame 2 starts Jaffar's
piece); bank C after i (OP_MSTOP first: the DOS is silent from i's end, so nothing is cut); bank A again at the next title
start, and at p_cutscene unless it is there (bank_cur). Three reloads instead of one because 01 + 11 + 05 (12.2 KB exact,
10.2 KB _env) do not fit the 10 KB torch cache with the index (228 B): all pieces stay exact. Sizes with all effects:
A 10,121 B (247 free), B 9,938 (430; without the effects 4 and 51, pv_scene's no-op cues), C 7,631 (2,737).

**The loop command** (§13): `0xE8 lo hi` after a stream whose last byte is a wait, not counted in the index length; snd_fill
reads it when it has copied the stream's last byte and goes on from hi:lo (`jp snd_fill`: the loop point's bytes follow the
wait in the ring at once, as room allows). Cost: 36 bytes of block 2 (block2_end 0xEAED -> 0xEB11, 239 free), about 60 T by hand count (not measured) once per
loop iteration (every 11-24 s) plus the copying; the ISR's code is unchanged, so its cost is too (the common path was the
constraint; snd_fill runs in main code). The encoder's loop group
(vgm2psg.encode(loop=)) writes all four attenuations (0x9F for the silent channels), the tones and the noise the frame needs,
so the loop is seamless and the envelopes restart identically on every pass (the exact variants hold p = 0). Streaming: the
pieces survive 30-43 frames without a refill (sndsim.max_gap over 3 loops); PRES refills once a frame in every wait and per
band of a draw, the cutscene engine once a frame.

**Lengths changed** (cutsim.PRES_TICKS60; kidsim.SOUND_SECONDS untouched): 27, 35, 40 -> 519 ticks (ceil(8.64 x 60); the
cutscene cue: the level starts when SMS 7 ends; DOS 720 / 618 / 412); 56 -> 1212 ticks (the hail + TITLE_MAIN wait after the
embrace's 840: 2052 = 3 x 684 = 3 plays of the title theme; DOS 7482). They reach cut.inc (cut_len60, CUT_L56), the SDLPoP hook
(tools/cut_suite.py passes cutsim.sound_ticks60 as POP800_CUT_TICKS) and the tests. title.inc's TITLE_F_TICKS stayed 597 (f ended
at the DOS 1502-tick point, the theme cut 2.2 s into a third play by g) until 2026-11-09: now two plays, f 60 ticks
shorter (§15: TITLE_F_MUSIC 463 + TITLE_F_REST 74).

**Timings as built** (the emulator; the music starts in the fade-in's frame, tick 0 of the scene, §17): the level scenes end at
tick 519 (was 720 / 618 / 412 by the same count): the scenes' frames and fade-out end at tick 196 (2/6, 4, 12), 400 (8) and 472 (9),
then the black screen with the music for 323 / 119 / 47 ticks. The piece is 518.4 ticks and
the model rounds up while the clock rounds down (floor(5 T / 6)), so the level start's snd_halt cuts its last 1-2 frames
(tests/m7_cut.py checks that every byte of the stream was copied and read by then). The title: unchanged ticks
(§17) but f (§15), the music under it as the table. The ending: embrace 840, hail 916, wipe + TITLE_MAIN 240, the final wait 56 ticks
(the third play of the title theme ends at 2052), fade-out 20: 2072 ticks (34.5 s) instead of 7502.

**Listening**: build/sound/pres/model_<piece>.wav (`python3 tools/presbank.py --wav`: the piece and one loop through the
model) and, as the emulator played them (the tests' PSG samples through sndsim.render): build/sound/pres/title_a-g.wav
(tests/m7_title.py), title_h-i.wav, title_j-m.wav, time_expired.wav, ending.wav (tests/m7_story.py), cutscene_<level>_<min>.wav
(tests/m7_cut.py).
