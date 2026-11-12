# The duel easter egg: analysis and design (2026-11-10)

Status: **the random arenas built (section 15, PLAN status 86); phase 4 built (network play: section 14, PLAN status 85); phase 3 built (the HUD, the texts, the sound: section 13, PLAN status 84); phase 2 built (the local duel in Z80, a patch over the game: section 12, PLAN status 82; the blades 12.8, status 83); phase 1 (the duel's logic in Python: section 11, PLAN status 81); the user's decisions in section 9, later iterations in section 10.** The duel is built after the remaining speed work and the AV fine-tuning (PLAN.md
item 35d). This note says what it needs, and above all what has to be **reserved now** so the work in between does not
take it (section 1.5). Figures are from main 960bcaf unless a section says otherwise; frames are 71,136 T (20 ms).

The user's decisions: a two-player sword duel reachable from the title, played on one machine or over the network as
BomberNet plays (the MZPico NET protocol, ~/src/bomberman docs/net-protocol.md); the kid against the shadow, both with the
kid's full move set; one fixed room as the arena; the host gets a generated room code and the joiner types it in; the
protocol's game id gets a fixed value for PoP (proposed in section 4.6, to be confirmed).

## 0. Summary

| Question | Answer |
|---|---|
| Shape | **The game itself in duel mode: the GAME image, restored from the RAM disk as for every game start, with a "duel patch" from the floppy laid over the routines and overlays the arena never uses** (traps, gates, buttons, doors, loose floors, potions, the guard AI, the tile-change redraw...): their entry points become `ret` stubs, the duel's code goes into the holes (section 1). The game's binary and its tests stay untouched: the patch exists only in main RAM while a duel runs. A separate DUEL program (PRES-like, from the same sources) is the fallback. |
| Reserve now | **No resident game bytes, no overlay window, no persistent RAM-disk space.** ~40 floppy blocks (of 209 free), ~100 bytes of the launcher (666 free), ~64 bytes of PRES (1,239 free), the action code 0x20, and three rules (section 1.5). |
| Room in duel mode | **~5.0 KB** of resident code the arena never runs, in ~15 holes (the largest 887, 737, 680, 599 bytes), against **~2.0 KB** of resident duel code: margin ~3 KB. The level-start, room, fill, rare (hit point strips) and text overlays are reused unchanged. |
| Second player | The shadow (charid 1, GUARD_REC) runs the **kid's** frame (SDLPoP play_kid_frame) with its own copy of the kid-only globals (9 bytes, swapped around its frame; its hit points stay GUARDHP_*), a duel visibility rule and a fair simultaneous-hit rule, keys instead of autocontrol_shadow, and the kid's sword rules (section 2). |
| Speed | A duel tick costs what the level 12 shadow fight costs: **8.6 frames (512 KB), 8.0 (1 MB), 7.2 (16 MB)** mean, p90 10-12 (measured, section 5). The logic is 0.3 of it. |
| Lockstep | Fits well: a tick is 100-170 ms, so an input delay of **1 tick** covers the production relay's ~130 ms round trip (2 x D x tick >= rtt). Every tick is drawn and the slower machine sets the pace (the user's decision 6; a fixed clock with skipped drawings was the alternative, section 5). |
| Arena | Level 1 room 3 (dungeon) or level 10 room 21 (palace): 8 plain floor tiles between pillars, walls above and below, no objects; the room's links are zeroed, so its edges are walls (section 6). **Since section 15: a random level per match, a random room of its pool of 4-6 per round, traps and holes turned into floor.** |
| Oracle | kidsim.py with a duel mode (two input streams); SDLPoP cannot be the oracle for the changed rules (section 7). |
| Effort | ~4 weeks in five phases; the risks: patch sites drifting with the speed work (caught at build time), the drawing speed, the real MZPico's NET path (section 8). |

## 1. Architecture and memory

### 1.1 Three shapes weighed

| | **A. Duel patch over the GAME image (recommended)** | B. A separate program DUEL from the same sources (PRES-like) | C. Inside the game, resident hooks (PLAN 35d's first idea) |
|---|---|---|---|
| How | the launcher restores the GAME image (as at every game start), then loads the patch's records from the floppy over the dropped routines and jumps to the duel's entry | the game's sources assembled with `DUEL` defined, the unneeded modules left out; loaded from the floppy like PRES | hooks in the resident code, the duel's code in W1 / W2 overlays |
| Resident game bytes | **0** (labels at the patch sites cost nothing) | **0** | local ~100 B, network +400-600 B; today main has ~315 B free, low 35, block 2 13 (0 in the cheat build) |
| Overlay windows, RAM disk | the game's overlays reused as they are; the duel's one-shot code in RAM-disk scratch (page 6), nothing persistent | its own copies of the room draw, level start, fill, HP strips, text (~5 KB) | W1 shared with the room, rare (every hit), keys, gate, frames overlays; 3-5 KB of overlay images in the RAM disk, nearly all of 512 KB's free bytes |
| Floppy | **~40 blocks** (patch ~6 KB raw + one-shot ~5 KB raw, PZ) | ~120 blocks (a whole ~38 KB image) | ~10-15 blocks |
| Start from the title | ~2 s (the image 1.2 s + ~10 KB of floppy) | ~3 s | ~1.2 s |
| Main-RAM margin | **~3 KB** (5.0 KB of holes, 2.0 KB needed) | ~1.5 KB (its own copies of the overlays' code must be resident or reloaded) | ~0.3 KB, shrinking with every speed PR |
| Same logic as the game | yes, the same bytes | yes, the same source lines | yes |
| Exactness tests of the game | untouched | untouched (a CI byte-compare proves the `if defined DUEL` blocks emit nothing) | the full gates |
| Fragility | patch sites and holes move with every game change: the patch is assembled against build/m4game.sym (as the overlays are, tools/ovltool.py equ) and asserts each piece fits its hole, so a change that breaks it fails the build, not the duel | `if defined DUEL` in shared files; a second configuration to keep building | competes for every byte with the speed and AV work |

**Recommendation: A.** It frees more than B (the arena's unused features are ~5 KB of resident code), reuses even the
game's overlays (the level start, the room draw, the frame store's fill, the HP strips, the bottom text), takes a third
of B's floppy space and needs no conditional assembly in the shared sources. B stays the fallback if the holes ever stop
sufficing; C is rejected (it takes the very bytes the speed work needs).

### 1.2 What duel mode drops, with figures

From build/m4game.sym at 960bcaf (this tree's build). "Hole" = bytes the duel can overwrite once the kept entry points
are stubs. Which routines the arena still reaches is checked in phase 2 by a static call graph from the duel's entry
points and by the profiler over duel scripts (tools/profile.py): every routine in a hole must show zero calls.

| Feature dropped | Code (address, bytes) | Stubs (kept entry points: `ret` or `xor a; ret`) | Hole |
|---|---|---|---|
| Tile animations, potions, the sword, chompers, doors, the level door, buttons, loose floors and falling floors, knocks (objects.asm animate_tile .. check_get_item) | 0x6943-0x71B0, 2,157 | process_trobs, check_knock, do_mobs, check_spiked, check_spike_below, start_chompers, check_press, check_get_item | **2,096** in 7 pieces: 887 (0x6996-0x6D0C), 680 (0x6D27-0x6FCE), 231, 102, 91, 82, 23 |
| The tile-change redraw (view.asm vs_*, view_snapshot, view_redraw, loose_pic, the gate parts) | 0x12A5-0x1586, 738 | none: the duel's main loop does not call them | **737** (low block: never inside blit) |
| Chopper, spike, door and loose-floor pictures (spike.asm, not frm_reset) and buttons / gates (buttons.asm trigger_button ..) | 0x76DE-0x77D6, 0x7809-0x7918 | frm_reset stays (the room overlay ends in it); **trigger_button stays as a `ret` stub**: level 1's start event (events.asm pgo6, the button of room 8) and guard.asm's exit-button path call it, and the level-start path runs before the arena setup | **521** (249 + 272, less the stub's byte) |
| The traps' sounds (sndobj.asm) | 0x7594-0x7679 | none (callers dropped) | **~230** |
| The guard AI, the mouse (autocontrol_mouse .. g_prob's tables) | 0xE0CF-0xE325, 599 | autocontrol_opponent's jump to the shadow is patched to the duel's P2 input | **599** (block 2) |
| The skeleton's wake, the mouse's level 8 run (check_skel, do_mouse) | 0xDC0B-0xDCD8, 206 | check_skel, do_mouse | **~200** |
| The clock (evres.asm show_time) | 0x1D8D-0x1E1B, 143 | show_time | **~140** |
| gate_redraw (gate.asm) | 0xEAE0-0xEB2F, 80 | none | **80** |
| Free today | main 0x7AC5-0x7BFF 315, low 35, block 2 13 | | **363** |
| **Total** | | | **~5.0 KB** in ~15 pieces |

Not counted (kept, or not resident anyway): the level events, save, keys, gate / button / door / frames, guard-leave /
guard-enter overlays (they are RAM-disk overlays: in duel mode they are simply never loaded, so they cost nothing and
free nothing in main RAM); the low code part 2 (ovl_low2, 483 B: the chopper and spike steps) is likely droppable too
but sits behind gfx.asm's hooks: left out of the figures. Runtime data is **not** counted as free and the duel's state does not go there: FRM_TAB 0x0700-0x076D is cleared by the
room overlay's frm_clr at every full room draw, the level-event state EV 0x0280 is cleared by game_init and read by the
reused text and flash paths (text_chk, flash_tick), MOBS_N / TROBS_N are read by kid.asm, guard.asm and sprite.asm every
tick, and VIEW_SNAP 0xF510-0xF5F4 is left alone too. The duel's variables (~60 B: the per-player block, the round state,
the net state) go into the code holes with the code (none of the ~5.0 KB above is data).

### 1.3 What the duel puts there

| Duel code | Bytes (est.) | Hole |
|---|---|---|
| the duel's main loop: two inputs, the pacing (mode 0: every tick drawn, at least 4 frames, both machines waiting for each other's input, so the slower one sets the pace: decision 6), the draw calls (draw_objects, hp_draw, text_chk, flash_tick are the game's) | ~250 | objects 887 |
| P2's input (a second decode of KEYMAT, joystick 2) and the per-player block swap | ~150 | objects 887 |
| P2's frame: play_kid_frame's sequence on GUARD_REC (the kid.asm / guard.asm routines called in SDLPoP's order), patched in for play_guard_frame's call in tick_post | ~200 | objects 680 |
| the sword rules' DUEL branches: ~6 patch sites in kid.asm / guard.asm (a `jp hole` where a charid test sits, 3 bytes over the original; labels added to the game source, 0 bytes) | ~60 | small holes |
| rounds, score, reset, quit, the round-end texts (the duel's own text routine, ~120-150 B: the text overlay prints only the game's fixed messages) | ~550 | view 737 |
| network per tick: the NET driver's core (command, status wait, read / write), send, poll, the wait indicator, the hash, the delay's byte | ~800 | objects 680 + guard AI 599 |
| **Total resident** | **~2.0 KB** (with the duel's variables, ~60 B) | of ~5.0 KB |
| One-shot (the menu, NET detection, the lobby: create / join, the code entry, the ready handshake; the arena's setup: the blueprint's links zeroed, the guard removed, the start tiles) | ~1.8 KB | a W2 overlay of its own (0xA000), image in RAM-disk scratch page 6 0x16C0-0x287F (4,544 B). **W2 overlaps the compose area the full room draw uses (COMPOSE_A)**, so: the lobby's state lives in a hole, not in W2; W2 returns to resident code before the arena's full room draw (and before any text-overlay use that shares W2); the ready handshake reloads W2 after the draw (~0.1 s) |

Reused unchanged: the level-start overlay (game_start: video, tables, PR_TAB, the fill on 1 MB+, game_init, load_level
of the arena's level), the room overlay (the one full room draw), the fill overlay, the rare overlay (both hit point
strips, at each hit), the text overlay's bottom-line drawing for the game's fixed messages only: it selects from the game's message table
and cannot print a score or "P1 WINS". **The duel adds its own short text routine** (the score digits and 3-4 fixed
strings through the game's font: ~120-150 B, counted in the rounds line of the table above, which grows to ~550).

### 1.4 How duel mode starts and ends

- **Entry.** PRES's title (and its step loop) checks a key combination (proposed: Ctrl+D; open question 7) and hands over
  with the handoff block's action `ACT_DUEL` (0x20, a new bit-5 class beside PRES's bit 4). ~40-64 bytes of PRES.
- **Load.** The launcher restores the GAME image from the RAM disk exactly as for ACT_PLAY (~62 frames), then reads the
  floppy entry `PRS_DUEL` (main-RAM records: the patch; its records may go anywhere but 0x8000-0xBFFF while the launcher
  runs, which the holes never are) and the one-shot entry `PRS_DUEL1` (records for RAM-disk page 6 0x16C0-0x287F: a
  record type the launcher's PRS loader does not have yet, or a main-RAM bounce through a hole), and jumps to the
  patch's entry instead of `start`. ~80-100 bytes of the launcher.
- **Start.** The duel's entry first sets the game's stack (`ld sp, STACK`, 0xFE00, as game.asm's `start` does): the
  launcher leaves SP at its own 0xC000, which grows down into SPRBUF_B (0xB800-0xBFFF), a compose buffer of the drawing.
  Then it calls game_start (the level-start overlay) with HO_MAIN's level = the arena's level, then
  its own W2 overlay: menu, lobby, arena setup; then the match loop.
- **Exit** (BREAK in the menu, quit after a match, a lost link): the level-start overlay's existing handoff path (it
  copies the launcher back from page 0 0xF000) with `ACT_TITLE`. The next game start restores a clean GAME image from the
  RAM disk (25,992 B PZ, never written by the duel), so nothing of the patch survives.

### 1.5 What to reserve now

| Item | Reserve | Today (960bcaf) | Why |
|---|---|---|---|
| Resident game bytes, overlay windows, RAM-disk bytes | **none** | main 315, low 35, block 2 13 free | the duel lives in holes of dropped features while it runs |
| Floppy blocks | **40 blocks (10 KB)** | 209 free of 1280 (files end at block 1071: POP800.PR2 229 blocks) | the patch (~6 KB raw) and the one-shot overlay (~5 KB raw), PZ ~8-9 KB. PR2 has 26 blocks left (an FSMZ file holds 255): the entries go into a third file POP800.PR3, contiguous after PR2 as PR2 is after PRS. B would need 120 |
| Launcher | **100 bytes** of LN_MAX 3,072 | 2,406 used (end_of_image 0xB966), 666 free | ACT_DUEL: the GAME image, then the PRS entries, then the patch's entry; page-6 records |
| PRES main RAM | **64 bytes** | 1,239 bytes free for the title art (mkgamedisk: 21 bands, 35,013 B PZ) | the key combination and the handoff |
| Handoff action | **0x20 (ACT_DUEL)**; HO_RESULT for the way back | 0x00-0x02, 0x10-0x13 used | |
| PRS index | 2 entries | ~30 of the 256-byte index | |
| Rule 1: page 6 0x16C0-0x287F stays runtime scratch | no persistent data there | already scratch: PRES's sound bank overwrites 0x0000-0x287F, the game rebuilds it at every start | the duel's one-shot overlay |
| Rule 2: the dropped features stay droppable | trap, door, button, loose-floor, AI code is not merged into routines the arena runs; when the speed work moves such code into an overlay, the bytes it frees in main RAM count as holes just the same | the holes total ~5.0 KB, the duel needs ~2.0 KB | the patch's build asserts catch a shortfall at once |
| Rule 3: the logic stays drawing-independent | no logic reading the drawing's state, the frame counter or the live PSG | true today (kidsim has no drawing; PACE_MODE 1 skips drawings) | lockstep (section 5) |

Phase 0 (2026-11-11, PLAN status 80) makes the reservation stick: `tools/mkgamedisk.py` asserts that `DUEL_BLOCKS =
40` blocks stay free behind the last file (it prints the figure) and that PRES keeps `DUEL_PRES_BYTES = 64` bytes free;
launch.inc names `ACT_DUEL equ 0x20` and `LN_DUEL_RESERVE equ 100`, which boot.asm asserts against LN_MAX. The loose-floor speed work is unaffected:
loose floors are among the dropped features, so whatever it adds there only enlarges a hole; nothing here touches its
files or its overlay space.

### 1.6 The fallback, B, in figures

If the holes stop sufficing (rule 2 broken) or the patch sites prove too fragile, the same duel code becomes a separate
program: the game's sources with `DUEL` defined, the features of 1.2 left out (~4.4 KB freed, + W1 1 KB with the room draw
one-shot), its own copies of the overlays' code (~2.7 KB resident, ~5 KB one-shot), ~1.5 KB of margin, ~120 floppy blocks
(~26 KB PZ at the GAME image's ratio). Reserving 40 blocks now and 80 more later is the switch's only cost on the disk.

## 2. The second player

### 2.1 Which code path drives the shadow

SDLPoP runs the shadow (charid 1) through play_guard_frame: autocontrol_shadow writes the control bytes, then the kid's
own control() acts on them (control_standing, running, jumping are the kid's for charid < 2). Two things do not suit a
human player:

| Guard path (play_guard_frame) | Consequence for a player |
|---|---|
| physics only while 44 <= x < 211; no check_collisions, check_bumped (only check_guard_bumped), check_gate_push, bump_into_opponent, check_knock | a running or jumping shadow is not stopped by the arena's walls: it can leave into room 0 |
| no read_user_control / user_control: autocontrol writes CONTROL_HELD directly; no ctrl1 save / restore | no edge detection and no direction flip of the keys |

**Proposal:** in DUEL the shadow runs the **kid's frame** (kid.asm kid_tick's body, SDLPoP play_kid_frame) on GUARD_REC
with Opp = KID_REC (loadshad_and_opp ... saveshad_and_opp, the pattern tick_post already uses), its input through
rest_ctrl / read_user_control / user_control / save_ctrl like the kid's. Both characters then have the same moves and
the same collisions; the kid's frame runs first, as in SDLPoP.

### 2.2 What assumes a single kid or an AI guard

| Place | Kid-only or AI state | DUEL change |
|---|---|---|
| kid_tick: CTRL1 (KV + 24, 5 B), GRAB_TIMER (KV + 29) | the kid's control memory | a per-player block swapped around P2's frame: ctrl1 5, grab_timer 1, have_sword 1, offguard 1, holding_sword 1 = 9 B, ~35 B of swap code. **Hit points are not in the block**: the shadow's are GUARDHP_CURR / GUARDHP_MAX, the single source the retained damage path (take_hp, do_delta_hp after the frames) updates; P2's frame reads them in place of HITP_* (its zero-hit-point check too) through the swap: HITP_CURR / MAX <-> GUARDHP_CURR / MAX exchanged around P2's frame and back before the damage path runs |
| control_standing: `charid != kid` draws with down + forward; the kid draws when have_sword and the opponent is near | different draw rules | DUEL: P2 takes the kid's branch |
| draw_sword (seq 55; the guard's en garde 90), forward_with_sword (86 kid / 56 guard), sword_strike (75 kid / 58 guard), parry (the kid's rule on the opponent's frames 151, 152, 153, 162, 168 / the guard's on 152 only), swordfight's down (93 kid fast / 92 shadow) | the guard's sword sequences and timing | DUEL: P2 takes the kid's sequences and rules: "the kid's full move set" (open question 4). The shadow's sword images (frames 150-189 through frame_tbl_guard) exist for seq 75 / 86 too: to be checked frame by frame in phase 1 |
| take_hp, do_delta_hp: HITP_* for charid 0, GUARDHP_* else; level 12 couples them (check_killed_shadow, do_delta_hp) | | kept; DUEL never sets level 12 |
| check_can_guard_see_kid (tick_pre): the guard's view of the kid, lit rooms | gates the sword fight (>= 2) | **a duel rule is required**: for a shadow outside level 12 the routine sets CAN_SEE to 0 (guard.asm cgs: charid shadow and level != 12), which would block the sword path in either arena. DUEL patches that test: CAN_SEE = 2 whenever both are alive on one row of the arena (the rest of the routine as it is). The normal game keeps the routine unchanged |
| autocontrol_opponent, guard_skill, justblocked, guard_refrac, kid_sword_strike | AI timers | not called for P2 (its input replaces them) |
| on_guard_killed (victory music), the kid's death text and "press button", WANT_RESTART | level flow | the duel's round end (2.3) |
| sounds: SDLPoP plays many only for charid 0 (sword drawn, soft land, hurt 13 / 12) | P2 quieter | kept as SDLPoP has it (faithful), or DUEL plays the kid's (open question) |
| exit_room, check_the_end, guard leave / enter | room changes | never triggered in a closed room; compiled in, cold |

### 2.3 Hit points, rounds, score

- Both start a round with the same hit points (the kid's start value 3, or a setting); the strips: the kid's at the
  left (hp_draw), the shadow's at the right (ghp_draw; SDLPoP draws it for the shadow only on level 12, DUEL always).
- Who strikes whom needs no change: check_sword_hurting already runs both ways (loadkid_and_opp, loadshad_and_opp).
- A round ends N ticks (e.g. 36, about the death music) after one dies. **Simultaneous hits:** the retained check_sword_hurt
  cancels the kid's hurt when both records are AC_HURT (the kid's action becomes AC_RUN_JUMP) and hurts only the shadow:
  with the host always the kid that would favour the host. DUEL patches check_sword_hurt to hurt both (loadkid /
  hurt_by_sword / savekid, then the shadow's), so a same-tick double death is a draw (the round is replayed, nobody
  scores); the normal game keeps SDLPoP's rule. (A patch site of ~10 B, in the sword-rules line of 1.3.) **Changed by the
  user 2026-11-11 (11.2 D13): simultaneous hits are a clash, nobody is hurt, both react as parried.**
  The reset puts both back at their start tiles with full hit points and sheathed swords, without a room draw (only the
  people are drawn again). Score "P1 2 : 1 P2" in the bottom text line (text.asm); best of 5 (a setting).
- All of this is logic in lockstep: the round end, the reset and the quit (a key bit, 3.3) happen at the same tick on both
  machines, with no extra messages.

### 2.4 Drawing both

Nothing new: the kid's slot (SPR_A, SPRBUF_A) and the guard's slot (SPR_G, SPRBUF_G, which holds the shadow's kid images,
1,148 B at most), both swords (GSWBUF, the kid's at 0x1000), both splashes, the shadow's look (overlay.asm PP_XD: the
image, then the image XORed further right, SDLPoP draw_objtable_item case 1). The look costs (section 5): open question 3
offers the plain look.

## 3. Input

### 3.1 Local: two players on one machine

| Player | Keys | Joystick |
|---|---|---|
| P1, the kid | the cursor keys + SHIFT (matrix 7/2-5, 8/0: as today) | joystick 1 (IN F0h) |
| P2, the shadow | four letters + a fire key away from rows 7 and 8 (proposed W A S D + Q; open question 8) | joystick 2 (IN F1h; 8255 PA bit 6 strobe, already set by the column write) |

read_inputs reads the whole matrix once a tick already (10 columns, KEYMAT); P2's byte is a second decode of it (~40 B).
To check on a real keyboard: two players pressing at once must not ghost (the MZ-800's matrix diodes; mz800emu does not
model ghosting).

### 3.2 Network

Each machine reads its own player from its own keys or joystick 1 (the host is the kid, the joiner the shadow) and sends
one byte a tick: x-, x+, y-, y+, fire, quit, rematch. The second byte of the slot (BomberNet's ADAPT_BYTE idea) carries
the delay's figures (4.4).

## 4. Network

### 4.1 BomberNet's model in short

The MZPico NET device (ports 0x50 / 0x51, commands 0xA0-0xA9) keeps rooms on a relay (mzpico.com's Durable Object; the
reference relay `relay/relay.py`): NETCREATE (game WORD, build WORD, slots, bytes per slot, 16 settings bytes) -> a
4-letter code; NETJOIN with the code; NETREADY -> seed + start frame once all are ready; per frame NETSEND(F + D, keys),
NETPOLL(F) until it is there; NETHASH(F, h): the relay flags DESYNC. BomberNet's Z80 client: `c/common/netdev_card.c`
(160 lines of C, the ten calls), the lockstep in `c/core/netplay.c` (input delay, wait indicator, 10 s silence = lost,
the delay adjusted in the match, an optional run-ahead).

### 4.2 Fit at our tick rate

| | BomberNet | DUEL |
|---|---|---|
| Step | a 60 ms frame | a tick: 100 ms at a 5-frame clock, 120 ms at 6, 172 ms at today's 512 KB mean of 8.6 frames |
| Round trip MZ - MZ (production relay; lobby measure incl. both devices) | 86-92 ms wire, ~130 ms in all | the same device and relay |
| Delay that covers it (2 x D x step >= rtt) | 2 frames (120 ms), 1 on a near link | **1 tick** (100-170 ms); 2 only on a far link |
| Network work per step | 3.4 ms in C (JSON lines on the card) | ~1-2 ms in assembly: < 0.1 frames of a 6-9-frame tick |
| Key to effect | d x 60 ms + sampling | sampling 0-1 tick + D = 1 tick: ~1.5 ticks (150-250 ms) against ~0.5 tick locally |

PoP's sword fight is slow and pose-based (a strike is a sequence over several ticks, a parry answers it): one tick of
delay should be playable (to be felt in phase 4). No rollback is needed to start with; DUEL's logic state is small (the two records, the per-player blocks, the
sword timers, the round state: ~200 B, re-running a tick ~0.3 frames), so BomberNet's run-ahead (docs/rollback-plan.md
there) stays an option for phase 5.

### 4.3 Start, late and lost input, the end

- **Start.** Both machines draw the arena first (~2 s on 512 KB), then NETREADY(1). The relay's start broadcast is tick
  0 on both; the seed seeds prandom (unused by the duel's logic today, but kept equal). Ticks 0..D-1 carry no keys
  (BomberNet's net_match_start).
- **Late input.** The relay transport is TCP / WebSocket: input is never lost, only late. A machine waits in NETPOLL; after
  ~0.5 s it shows WAITING; every 16th poll it reads NETSTATUS (DESYNC, DROPPED, NO_LINK) and BREAK; 10 s without a tick
  = CONNECTION LOST, back to the title (BomberNet's wait_check).
- **Quit and rematch** are key bits in the tick's byte, so both machines leave or restart at the same tick; NETLEAVE
  after it.
- **Desync.** NETHASH every 16 ticks: a 16-bit sum-rotate over the logic state (gv_start..gv_end, 82 B: the three
  records, CHAR_SAVE, guard hit points and the fight timers; plus HITP_CURR / HITP_MAX (OV + 0, + 1, outside that range),
  the per-player blocks and the round state: ~100 B); ~3 K T. On DESYNC
  both show it and stop. The relay keeps 256 steps per room: 25-40 s of ticks.
- **Build id.** A CRC-16 of the GAME image and the duel patch, computed by mkgamedisk (as fstore.py's build id): two different disks are
  refused at join (error 6) and nobody has to remember to bump a constant.

### 4.4 The delay

The host measures the round trip in the lobby (NETMSG pings, as BomberNet's lobby) and sets D = ceil(rtt / (2 x tick)),
at least 1, in the settings. A small in-match rule from BomberNet 0.2.0 (raise by one when both waited in 6 of 32 ticks,
never above the lobby's figure; lower when the margins allow) costs ~150 B; worth it only if phase 4's measurements show
waits at D = 1.

### 4.5 Lobby and room code

DUEL's menu: LOCAL, HOST, JOIN (HOST and JOIN dimmed with "NO NETWORK CARD" when detection fails). HOST: NETCREATE, show
the code ("ABCD", letters without I and O) and WAITING FOR PLAYER, then READY. JOIN: type four letters + ENTER;
errors in words (6 different version, 7 no such room or full, 9 no link). Detection as netdev_card.c's net_detect:
REVD's status {02, cmd, 04}, then INFO (0x95) with the NET bit; an absent card floats the ports and fails the REVD check.
All of it is one-shot code (1.3).

### 4.6 Game id and room parameters (proposal)

| Field | Proposal |
|---|---|
| game id | **0x5050 ("PP", Prince of Persia)**; alternative 0x5044 ("PD", Persia Duel). BomberNet is 0x424E ("BN"). The relay namespaces codes per game id. To be confirmed by the user. |
| build | CRC-16 of the GAME image + the duel patch (4.3) |
| slots, bytes per slot | 2, 2 (keys; the delay's byte) |
| settings (16 B) | arena id, hit points, rounds to win, D, the host's tick clock (5.2), RAM-disk tiers of the host (informational) |

## 5. Pacing and determinism

### 5.1 Measured: a duel tick costs a shadow fight

tools/roadmap.py range level12_shadow_hit.txt 120 170 (the kid against the level 12 shadow with swords: the closest
existing scene) and fight1 60 160 for comparison, on this tree (2026-11-10):

| Stretch | 512 KB | 1 MB | 16 MB |
|---|---|---|---|
| shadow fight, frames a tick: median / p90 / mean | 7.83 / 12.08 / **8.59** | 7.46 / 10.95 / **8.03** | 6.46 / 9.95 / **7.22** |
| of it: people_place (char_fetch) | 2.36 (1.77) | 1.79 (1.19) | 1.01 (0.41) |
| of it: spr_draw of the people (the shadow drawn twice: the XOR look) | 1.36 | 1.36 | 1.36 |
| of it: the logic (kid_tick, tick_pre / post) | 0.32 | 0.32 | 0.32 |
| fight1 (kid against a guard), mean | 6.40 (spr_draw 0.96, char_fetch 1.53) | 5.63-5.68 (docs/perf.md) | 5.42 (docs/perf.md) |

A duel tick is ~2.2 frames dearer than a guard fight at 512 KB, and the tiers differ by ~1.4 frames a tick (the fetch).
When the look was built (docs/perf.md, M5 drawing) it cost 2.6 of 12.3 frames a tick in this stretch.
At one tick per drawn picture the duel would run at 5.8 ticks a second on 512 KB, 7 on 16 MB (the design rate is 12.5,
DOS fights 10). The speed work still to come lowers this; the shadow's XOR draw itself is not on its list yet.

### 5.2 How lockstep absorbs different machines

- The **logic** of a tick depends only on the state and the two keys: identical on 512 KB and 16 MB, drawn or skipped
  (kidsim has no drawing; PACE_MODE 1 already skips drawings with the same logic; the frame store changes only speed).
- **Not chosen (decision 6), kept as the alternative: a fixed tick clock agreed in the settings** (5 frames = 10 ticks a second as DOS fights, or 6), run by
  game.asm's mode 1 (NEXT_TICK, SKIP_TICK, SKIP_MAX 2, DEBT_MAX): a machine whose drawing is late skips drawings, never
  ticks. Each tick also waits for the other's keys; a machine that falls behind (a long draw, a late packet) catches up
  through skipped drawings, and DEBT_MAX restarts its clock after a stall. Both MZ-800s count the same 50 Hz frames, so
  the clocks drift apart only by their crystals' tolerance, which the waits absorb.
- **Chosen (decision 6): without the clock** (mode 0: every tick drawn, at least 4 frames), the slower machine sets the pace for both: 512 KB
  against 16 MB plays at ~8.6 frames a tick. Simpler, but slow and uneven (p90 12 frames).
- **The 4-frame minimum** matters only for local play on a fast machine; with the clock it is the clock.
- **SND_MODE.** The launched game's hybrid mode lets the death timer and the level end ask the live PSG player: that is
  machine time, not logic. DUEL uses mode 2 (every wait asks the ticks model) and has no such wait anyway (its round end
  counts ticks). Sound on / off (Ctrl+S) never changes the logic in this port, so the two machines may differ in it.

## 6. The arena

Rooms with a full row of plain floor (floor, debris, torch, pillar), from tools/popdata.py over levels 1-14 (scratch
script); `|` pillar, `_` floor, `t` torch, `#` wall, `l` lattice:

| Room | Rows (top, middle, bottom) | Links (L, R, U, D) | Notes |
|---|---|---|---|
| **level 1 room 3** (dungeon) | `##########` / <code>&#124;__t_t___&#124;</code> / `##########` | 2, 9, 0, 0 | a corridor: 8 floor tiles between two pillars, two torches, walls above and below: no climbing |
| level 1 room 21 (dungeon) | <code>&#124;__t_t___&#124;</code> / `##########` / `##########` | 17, 5, 0, 8 | the same row at the top |
| level 7 room 22 (dungeon) | `##########` / `##########` / <code>&#124;__t_t___&#124;</code> | 23, 24, 0, 10 | the same row at the bottom |
| **level 10 room 21** (palace) | `##########` / <code>&#124;&#124;_t_t__&#124;&#124;</code> / `##########` | 3, 5, 0, 0 | 6 floor tiles between double pillars, palace walls |
| level 6 room 16 (palace) | `llllllllll` / `l_l_lt_l_l` / `##########` | 15, 2, 0, 0 | lattice pillars: busy fore pieces |
| level 12 room 15 (the shadow's room) | `_S_ttLL_` / `###    #__` / <code>#o&#124;    #&#124;</code> | 2, 20, 22, 18 | not flat (loose floors, gaps): unsuitable |

**Proposal: level 1 room 3**, or level 10 room 21 for the palace look (open question 2). DUEL loads that level's
blueprint, zeroes the room's four links (SDLPoP get_tile: room 0 is a wall, so the edges draw and collide as walls),
removes the room's guard, and places the kid and the shadow at fixed tiles facing each other (e.g. columns 2 and 7). The
room draw is the game's full room draw (~100 frames once per match), the torch cache, no tile changes. A custom room
(one 2,305-byte blueprint with one room) is possible but needs its own wall pattern and art checks; an existing room
looks right by construction.

## 7. Testing

| What | How | Oracle |
|---|---|---|
| The duel's logic | kidsim.py gets a duel mode: P2 through play_kid_frame on the shadow's record with its own block (2.2), two input streams in a script (`# duel`, then `x y s  x2 y2 s2` lines) | **kidsim is the oracle.** SDLPoP has no two-player mode and DUEL changes rules SDLPoP does not have (the shadow with the kid's sword rules and frame), so it cannot be one. SDLPoP still checks what DUEL does not change: the kid's frame and the shadow's look are its code paths already under test |
| The Z80 against kidsim | tests/m4_game.py-style harness for DUEL: the state every tick (both records, hit points, the round), at 512 KB, 1 MB, 16 MB | per tick, exact |
| Mode 0 pacing across tiers | one input log on 512 KB and on 16 MB: every tick drawn, the hash of every tick equal | each other |
| The game untouched | the patch only adds labels to the game's sources: m4game.bin and the overlays byte-identical before and after | CI byte-compare |
| The holes | every routine in a hole is called 0 times over all duel scripts (tools/profile.py), and a static call graph from the duel's entry points never reaches one; the patch's build asserts each piece fits its hole | the build and the profiler |
| Network | two headless mz800emu-trace instances (its Unicard emulation has the NET device: unimgr_net.c, `[UNICARD] mzpico_mode = 1`, `net_relay = host:port`) against BomberNet's `relay/relay.py` (TCP 8766); a driver after BomberNet's tools/nettest.py: host, read the code from VRAM or a symbol, join, play a scripted log on both, compare the hashes; also a relay that delays or reorders lines (tools/netproxy.py) | the two machines' hashes and the local run's trace |
| Real hardware | two MZ-800s with MZPicos through mzpico.com | by hand |

## 8. Phased plan

| Phase | Content | Effort | Risk |
|---|---|---|---|
| 0 (now, tiny PRs) | the reservations of 1.5: mkgamedisk's DUEL_BLOCKS assert, ACT_DUEL named in launch.inc | 1 hour | none |
| 1 (**done**, section 11) | kidsim duel mode, the per-player block, the kid's sword rules for P2, rounds; scripted duels; check the shadow set's frames against seq 75 / 86 | 3-4 days | low |
| 2 | `make duel`: the patch assembled against build/m4game.sym (tools/ovltool.py's equ step) with an assert per hole, the stubs, the labels at the patch sites; the call graph and profiler check of the holes; the launcher action, the PRS entries, PRES's key; the arena start; local P2 input; Z80 against kidsim exact; the game byte-identical | 1-1.5 weeks | medium: a routine in a hole that the arena reaches after all (caught by the profiler check), patch sites inside hot kid.asm code |
| 3 | HUD, score, rematch, quit, mode 0 pacing (every tick drawn), sound; decide the look (open question 3) from measurements | 3-4 days | low |
| 4 | network: the NET driver in assembly (netdev_card.c's ten calls), the lobby, lockstep, the hash, the delay; two emulators with the relay | 1.5-2 weeks | medium: the emulator's NET path is proven by BomberNet; the real MZPico with the RAM disk on the same board is not |
| 5 (optional) | the in-match delay rule, run-ahead, real-hardware tuning | 1 week | |

In all ~4 weeks (PLAN 35d estimated 1-1.5 + 2-3); B would add ~3-4 days (its own configuration and overlay copies).

**Biggest risks.** (1) The holes: ~3 KB of margin on paper, but a hole's routine reached by the arena would crash only in the duel; the profiler and call-graph check of phase 2 and the build asserts guard it, and each game change re-runs the asserts (a duel build in CI). (2) Speed: a
duel tick is 7.2-8.6 frames today; with the 5-6-frame clock many drawings are skipped, which shows as a choppier fight
than a guard fight; the speed work's gains carry over, the XOR look is its own lever. (3) The MZPico doing both the RAM
disk (pico_rd, PLAN 35a) and the NET device while the duel reads ~100 KB a second of art: an open firmware question. (4)
Keyboard ghosting with two players on one keyboard.

## 9. The user's decisions (2026-11-10)

| # | Question | Decision |
|---|---|---|
| 1 | Game id | **0x5050 ("PP")** |
| 2 | Arena | **the dungeon: level 1 room 3** |
| 3 | The shadow's look | **the cheaper one** (no XOR double draw); the two players still need to be told apart: a colour variant only if it costs nothing measurable, to be decided in phase 3 |
| 4 | The shadow's moves | **the kid's sword sequences, parry rule and sounds** |
| 5 | Rules | **3 hit points a round, best of 5** |
| 6 | Pacing | **every tick drawn, at the slower machine's pace** (mode 0: no tick clock, no skipped drawings; section 5.2's second option) |
| 7 | Entry | **Ctrl+D on the title** |
| 8 | Local P2 | **joystick 2 and W A S D + Q** |
| 9 | Shape | either is acceptable to the user; **A (the duel patch) as recommended**, B the fallback; 40 floppy blocks reserved |
| 10 | Roles | **the host is always the kid** |

Not wanted: the loose floors (they stay among the dropped features).

## 10. Later iterations: what the design keeps open

### 10.1 Choppers and spikes in the arena (optional, later)

The duel patch overwrites their code by default; a later iteration may keep it. What keeping them costs:

| Kept | Code (960bcaf) | Effect on the holes |
|---|---|---|
| the spikes' and choppers' logic (objects.asm: check_spiked, spiked, check_spike_below, start_chompers and their animate_tile cases) | part of the objects pieces (0x6F94-0x71B0 and the animate_tile cases): ~0.6-0.7 KB | the 680-byte piece and some small ones stay; estimated, to measure in phase 2 |
| their pictures (spike.asm chomp_redraw / chomp_pic / spike_redraw, the frame slots frm_*, cs_put; the low code part 2 overlay with the steps) | ~0.3 KB main (part of the 521), the slots' tables in low RAM, ovl_low2 (an overlay: costs nothing resident) | the 521-byte piece mostly stays |
| the tile-change redraw (view.asm) when a trap's tile changes | 737 B | stays (the duel's rounds code needs another home) |
| **Total kept** | **~1.7 KB** of the ~5.0 KB | the duel's ~2.0 KB still fits (~5.0 - 1.7 = ~3.3 KB of holes), margin ~1.3 KB instead of ~3 KB |

Rules for keeping it possible: the duel's own code is placed first in the holes that are NOT chopper/spike code (the
guard AI, the clock, the skeleton, the gates, buttons, doors, loose floors, potions, the traps' sounds), and the patch's
build gets a switch `DUEL_TRAPS` that leaves those routines and their stubs in place. The arena then needs another room:
level 1 room 3 has no traps, so a room with a chopper or spikes on a flat row (to look up with popdata.py), or a
patched copy of room 3 with a chopper tile placed (the blueprint is read and patched at the arena setup anyway).
Rounds: a death on a trap ends the round like a sword death, the other player scores. Speed: a chopper step is
~1-1.5 frames on top of the duel's tick (docs/perf.md part 25), both machines pay it in the same tick.

### 10.2 Four players over the network: possible, but not recommended

The protocol allows it (BomberNet plays 4 machines, one byte a player a tick). The MZ-800 side does not:

| | 2 players (the duel) | 4 players |
|---|---|---|
| logic | the kid's frame twice; each character has one opponent (Opp), check_sword_hurting both ways | SDLPoP's fight logic is built around one opponent per character: who fights whom has to be chosen every tick (nearest facing enemy), hits resolved between more pairs; a new oracle in kidsim; ~1-1.5 KB more code |
| memory | two characters' records and sprite buffers (SPRBUF_A, SPRBUF_G up to 1,148 B each) | two more records, two more sprite and sword buffers (~2.5-3 KB of buffers in main RAM) and object slots 5 -> 9: above the ~3 KB margin, i.e. a different, larger memory plan (B or more) |
| speed | ~7-8.5 frames a tick today (the plain look less) | each character costs ~1.5-2 frames (fetch + compose + restore); ~11-14 frames a tick: ~3.5-4.5 ticks a second, at the slowest machine's pace (decision 6) |
| screen | one room, two fighters | four fighters in a 10-tile room overlap constantly; the fight's frames are drawn for two |

Conclusion: technically conceivable, but it would play at about half the duel's speed and needs its own memory design;
not worth it for an easter egg. A 3-player mode has the same problems at ~3/4 the cost.

### 10.3 Co-operative play (2 kids against 2 guards)

| Variant | Verdict |
|---|---|
| **co-op through the real levels** | **not feasible**: one screen shows one room; two kids in different rooms would need a split or a shared camera that the game cannot draw (a room change is ~1.4-1.8 s each), and the level's events assume one kid |
| **2 kids against 2 guards in the arena** | four characters: the same costs as 10.2 (speed ~11-14 frames a tick, memory above the margin), plus the guard AI choosing a target between two kids (SDLPoP's AI watches only the kid). Not recommended |
| **2 kids against 1 guard in the arena** (co-op "survival", guards entering one after another) | the realistic co-op: three characters, ~9.5-11 frames a tick (estimate), ~1.5 KB more than the duel (a third record and sprite buffer, the AI's target choice); fits only if the dropped features' holes suffice after the duel's code (on paper, barely: to size in phase 2). A later iteration after the duel, if at all |

The duel's design keeps these open by: the per-player block (2.2) written for N players, P2's input path written for a
player index, the guard AI only stubbed (not overwritten) when a co-op mode is built, and the network byte format
(3.2) per slot as BomberNet's N-player rooms already are.

## 11. Phase 1: the rules as built (2026-11-11)

The duel's logic in Python: **tools/duelsim.py** (DuelSim, a subclass of kidsim's KidSim), the rule sites in
**tools/kidsim.py** marked `(duel Dn)` (each acts only with `KidSim.duel` set: every game test runs with it off and
gives byte-identical traces: all 82 scripts of m4 / m5 / m6 / m7 compared before and after), the scripted duels in
**tests/duel_scripts**, their test **tests/duel_test.py** (PR tier b, the full regression's logic part, the smoke tier;
~1 s, no emulator). kidsim in duel mode is the oracle the Z80 duel (phase 2) must match tick for tick. Where a rule
below is a choice (the design left it open, or SDLPoP's behaviour would be unfair), it is marked **[choice]**: the
user's decisions to confirm are collected in 11.10.

### 11.1 The tick

DuelSim.step(in1, in2), in SDLPoP play_frame's order, with what the arena never needs left out:

1. (sound_tick; the deltas zeroed) check_can_guard_see_kid (with D11).
2. Player 1's frame: play_kid_frame on the kid's record (loadkid_and_opp ... savekid) with the duel's control (11.4). The
   kid trace line is taken here, as in the game (mid-tick).
3. tick + 1.
4. Player 2's frame: **the same play_kid_frame** on the shadow's record (loadshad_and_opp ... saveshad), its block swapped
   in before and out after (11.3). Same collisions, bumps, gate push, the kid's checks (spikes, presses, chompers,
   knocks: no-ops without such tiles).
5. check_sword_hurting (the shadow's check first, then the kid's: SDLPoP), check_sword_hurt (D13), check_sword_vs_sword,
   do_delta_hp.
6. The rounds (11.5), then play_next_sound (the 'N' line).

Not run: timers, do_mobs, process_trobs, check_skel, exit_room, check_the_end, check_guard_fallout, show_time (no clock,
the room never changes), the guard AI (autocontrol_*), play_guard. **The torches** are animated by process_trobs in
the game (prandom): the duel's logic does not animate them (they change nothing in the logic); phase 2 decides whether
the drawing keeps them flickering (11.9). **Decided 2026-11-11 (phase 2): they flicker as in the game; duelsim runs the room-entry torch step at the arena setup and process_trobs before check_can_guard_see_kid, prandom never hashed (12.4).**

### 11.2 The rule sites (the Z80 patch sites of phase 2)

| Site | Where (kidsim; SDLPoP) | Duel rule |
|---|---|---|
| D1 | load_frame (seg006 load_frame) | **[choice]** player 2's frames 150-189 come from the **kid's** frame table (frame_table_kid, chtab 2: the kid's images), not frame_tbl_guard (the shadow's set) (11.8) |
| D2 | control_standing: `charid != kid` draws with down + forward | player 2 takes the kid's branch (draws when the opponent is near, as the kid) |
| D3 | control_standing: no auto-draw while `Opp.charid == shadow` jumps (Opp midair or frames 107-117) | **[choice]** for both players (the opponent is always "the shadow"), so the rule is symmetric |
| D4 | forward_with_sword | seq 86 (kid), not 56 |
| D5 | draw_sword | the kid's: sound 19, offguard = 0, seq 55 |
| D6 | control_with_sword | the kid's: holding_sword = 0 when alive |
| D7 | swordfight, down with the sword drawn | the kid's: offguard = 1, guard_refrac = 9, holding_sword = 0, seq 93 (put_sword_away_fast), not 92 |
| D8 | sword_strike | seq 75 (kid), not 58 |
| D9 | parry | the kid's rule (parries any attack but frame 168; plays on at frame 153), not the guard's (only frame 152, backs off at 32) |
| D10 | hurt_by_sword | the kid's sound 13 (not 12); the gate fix for a killed guard does not apply |
| D11 | check_can_guard_see_kid: a shadow outside level 12 is blind | the shadow sees on every level (the rest of the routine as it is: both alive, one room and row, no wall between); can_guard_see_kid = 2 in the open arena |
| D12 | control_kid: `hitp_curr == 0` -> dead (duelsim duel_control) | the character's own hit points: hitp for the kid, guardhp for the shadow (take_hp's own rule) |
| D13 | check_sword_hurt | **changed by the user 2026-11-11: a clash.** Both hurt in one tick (each one's strike reached the other: check_sword_hurting marked both AC_HURT): **nobody is hurt**, both react as an attacker whose strike was parried: check_hurting's own reaction, the sequence attack_was_parried (69) played at once, the kid first, then the shadow (check_sword_vs_sword then plays the clash sound on their frame 167). One hurt: hurt_by_sword as SDLPoP. (First built: both hurt, a double death a draw. SDLPoP cancels the kid's hurt and hurts only the shadow: it would favour player 1.) No guard_refrac |
| D14 | bumped, pushed left into a wall of room 0 | **[choice]** the floor check uses the room's own column 9, as SDLPoP does for the left edge (`curr_room == 0 && tile_col == 10` -> the room's column 0). Without it a player bumping the arena's right edge falls back (seq 45 bumpfall) where the left edge gives a plain bump |
| D15 | xpos_in_drawn_room for room 0 | **[choice]** with both links 0, SDLPoP takes room 0 for the left neighbour: the right edge's wall lands 140 units too far left and a player bumping it is thrown back ~28 units (the left edge: 3). The duel puts room 0's column 0 on the right |

Not changed (charid tests that stay the shadow's / SDLPoP's): kid_sword_strike = 15 on a strike and justblocked = 4 on
a parried strike (inputs of the guard AI only, which the duel never runs: they keep their value, they are hashed); land
(a 2-row fall: the shadow lands softly; the arena has no fall); is_obstacle's mirror, proc_get_object (kid only, nothing
in the arena); take_hp / do_delta_hp (hitp for the kid, guardhp for the shadow).

Without D14 and D15 the two edges were measurably different (tests/duel_scripts/edges.txt): with them both bump with
frames 50-52 and stop at x 68 and 201 (SDLPoP's left/right rounding: 68 + 201 = 269, the start positions mirror around
270).

### 11.3 The per-player block

Player 1's lives in the game's globals (as today); player 2's in a block swapped with them around its frame:

| Part | Bytes | Z80 (kid.asm / guard.asm / objects.asm) |
|---|---|---|
| ctrl1 (forward backward up down shift2) | 5 | CTRL1 (KV + 24) |
| grab_timer | 1 | GRAB_TIMER (KV + 29) |
| have_sword | 1 | HAVE_SWORD (OV + 4) |
| offguard | 1 | OFFGUARD (g_glob + 11) |
| holding_sword | 1 | HOLDING_SWORD (g_glob + 5) |
| **the collision rows** (prev_collision_row, prev / curr / below / above rooms and flags) | **81** | PREV_COLL_ROW (KV + 71), PREV_ROOMS .. ABOVE_FLAGS (KV + 96 .. KV + 175) |

**The collision rows are new against design 2.2.** check_collisions compares where the character's sides were against
the walls at its last call with where they are now (the flags depend on char_x_left / right_coll), and move_coll_to_prev
carries the rows from one call to the next. SDLPoP runs it for the kid only; with two players calling it, each would
compare against the other's walls (spurious or missed bumps). So the block is **90 bytes** (9 hashed + 81), and the swap
is two block exchanges (KV + 71, 1 B; KV + 96, 80 B), in and out: ~25 B of code, ~5 K T a tick. (Rows prev_* are rebuilt at every
check_collisions except on a turn, where check_gate_push reads the old ones: swapped as well.)

Hit points are **not** in the block (design 2.2): the shadow's stay in GUARDHP_CURR / MAX. **[choice]** The design's
HITP <-> GUARDHP exchange around player 2's frame is replaced by D12: with the exchange, a take_hp inside player 2's
frame (spikes, chompers: DUEL_TRAPS, 10.1) would compute its delta from the kid's hit points (take_hp picks guardhp by
charid). D12 is one read in control_kid.

### 11.4 Control, death, sound

- **The duel's control** (duelsim duel_control) is SDLPoP's control_kid without the restart: no Ctrl+A, **no restart by
  the button after death** (`shift && alive > 6`: in the game a dead player's fire would restart the level), no level
  keys, no level patches; then play_kid's death counter (alive counts up while is_dead(), capped at 100) **without
  waiting for a sound, without the death music, without the "Press Button" text and its 288-tick return to the title**.
  The same for player 1: the game's kid_tick needs these patched in the duel as well (11.9).
- **Sound**: the silent model (KidSim sound='silent'): the logic never waits on a sound; the requests (play_sound with
  SDLPoP's priorities) go into the 'N' line. Player 2 makes the kid's sounds (D5, D10). The round end's sound or music
  is phase 3.

### 11.5 Rounds, results, reset

| Constant | Value |
|---|---|
| ROUND_HP | 3: hitp_curr = hitp_max = guardhp_curr = guardhp_max = 3 at every round's start |
| WINS | 3 (best of 5); draws do not count: a match has no round limit |
| ROUND_END_TICKS | 36 |
| START | player 1 (the kid, charid 0): column 2 facing right; player 2 (the shadow, charid 1): column 7 facing left; row 1 of room 3 |

- **The decision** (after the tick's do_delta_hp): the first tick at which hitp_curr == 0 or guardhp_curr == 0 decides
  the round: both 0 = **draw** (result 3, nobody scores, the round is replayed), else the player still above 0 wins it
  (result 1 or 2) and scores. rounds += 1 (draws counted), timer = 36. **[choice]** Whatever happens in the 36 ticks
  after does not change the result (a dying player cannot strike: hurt_by_sword starts the death sequence at once).
- **The round end**: the timer counts down one a tick; at 0: a player with WINS rounds ends the match (match = 1 or 2,
  no reset: the survivor keeps standing, the loser lies dead), else **the reset**: both records rebuilt (room 3, row 1,
  x = x_bump[col + 5] + 14 (100 and 170), y = y_land[2] = 118, the direction above, alive -1, sword sheathed, action 0,
  fall_x = fall_y = repeat = 0, seq 2 "stand" played: frame 15); both blocks fresh (ctrl1 0, grab_timer 0, have_sword 1,
  offguard 0, holding_sword 0, collision rows empty: prev_collision_row -1, rooms -1, flags 0); hit points 3; deltas,
  can_guard_see_kid, justblocked, guard_refrac, kid_sword_strike, guard_notice_timer, is_guard_notice, droppedout,
  is_screaming, knock 0. The match's first round starts from the same reset (tick 0).
- **[choice]** Columns 2 and 7 are 83 units apart (70 + 13 for facing each other): inside the kid's draw distance (90),
  so **both draw their swords on the first tick of every round** with no key pressed (the kid's auto-draw, control_standing)
  and stand en garde ~8 ticks later. Columns 1 and 8 (111) would start them sheathed.
- **Quit** (bit 5 of either player's byte): match = 3 at that tick, nothing else changes (the network sends NETLEAVE
  after it). **Rematch** (bit 6 of either byte) after a match's end (match 1 or 2): score, rounds and result to 0,
  match 0, the reset. Both are logic, so both machines act at the same tick (design 2.3).

The round state (6 bytes, hashed): rounds (draws included, so unbounded: one byte, modulo 256), score 1, score 2, timer, result (0 none yet, 1 P1, 2 P2, 3 draw; the last
round's until the next decision), match (0 on, 1 P1 won, 2 P2 won, 3 quit).

### 11.6 The input byte

One byte per player per tick, the same locally and over the network (decision 10: the host is player 1):

| Bit | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| Meaning | left | right | up | down | the button (SHIFT / fire) | quit | rematch | 0 |

Bits 0-4 are the game's INPUT byte as read_inputs builds it (game.asm), so player 1's byte is INPUT plus the two key bits
and player 2's is a second decode (W A S D + Q, joystick 2: phase 2) into the same layout. Decoded as get_controls
decodes INPUT: **right wins over left, down over up** (left+right = right). The directions are the screen's (as the kid's
scripts): user_control flips them for a character facing right.

### 11.7 The state hash and the traces

**The hash** (design 4.3; duelsim state_bytes / hash16): 68 bytes in this order, 16 bits, per byte `h = rotl16(h, 1) +
byte`:

| Bytes | Content |
|---|---|
| 16 | the kid's record, the Z80's layout (guard.asm OF_*: frame x y direction col row action fall_x fall_y room repeat charid sword alive seq_lo seq_hi; direction 0 / 0xFF, alive 0xFF alive) |
| 16 | the shadow's record |
| 12 | hitp_curr, hitp_max, guardhp_curr, guardhp_max, can_guard_see_kid, justblocked, guard_refrac, kid_sword_strike, guard_notice_timer, is_guard_notice, droppedout, guard_skill |
| 9 + 9 | player 1's block, player 2's block (11.3's first five rows) |
| 6 | the round state |

Not hashed **[choice]**: OPP_REC and CHAR_SAVE (scratch copies whose contents between ticks are an implementation detail
of the Z80), the deltas (zeroed every tick), the collision rows (they follow from the records within a tick or two),
prandom's seed (the duel's logic never draws a number). The design's "gv_start..gv_end" is therefore an explicit list,
not the memory range: the Z80 hashes these addresses in this order.

**The trace** per tick (tests/duel_test.py; `tools/duelsim.py script out.txt` writes it): the kid line (kidsim
trace_line, mid-tick: the m4_test kid snapshot), the 'G' line (kidsim trace_guard_line: the shadow's record and the
fight globals, the m4_test G snapshot at the tick's end), `D tick in1 in2 rounds score1 score2 timer result match hash
<P1 block 9> <P2 block 9>` (the tick's end), and the 'N' sound line; a first line `D 0 ... hash` holds the state before
the first tick. Phase 2's harness can reuse m4_test's kid and G snapshots and add the D line's bytes.

**Scripts** (tests/duel_scripts): `# duel`, then one line a tick `x1 y1 s1  x2 y2 s2` (x -1 left / 1 right, y -1 up / 1
down, s 1 the button) with optional `*N` (repeat), `Q1` / `Q2` (quit bit), `R1` / `R2` (rematch bit), or two hex bytes
`0x.. 0x..`; options `# p2 frames shadow`; expectations `# expect rounds|score|match|matches|mirror|hurt|sheathe|digest ...`
(tests/duel_test.py's header).

### 11.8 The shadow's image set against the kid's sword sequences

`tools/duelsim.py --frames`: per sword sequence, the frames 150-189 player 2 shows when drawn as SDLPoP draws the
shadow (frame_tbl_guard[frame - 149], chtab 5 = the shadow's set, 32 images):

- **Seq 75 (strike: 151-158, 170, 171) and seq 86 (forward_with_sword: 164, 165, 158, 170, 171) are covered**, as are
  draw_sword, back_with_sword, parry (169, 150), parry_after_strike, strike_after_parry (162), attack_was_parried (167),
  turn_with_sword, the pushes, hit_by_sword (172-174). The frame numbers mean the same poses in both tables (seq 58,
  the guard's strike, uses the same 151-157).
- **Missing: frames 183 and 185** (images 33 and 34 of the guard table: the last two poses of stabbed_to_death and dying,
  falling down dead and lying dead). The shadow never dies in SDLPoP (on level 12 it is cleared), so its set ends at 32.
  A dead player 2 would have no image, and its collision box would be 0 x 0 (set_char_collision: no size).
- **The geometry differs** for nearly every sword frame (150-171, 179-185): the guard table's dy is 1 where the kid's
  is 2, dx differs for 150-152, 159, 161, 162, 166, 168, 179-183, 185, and the flags (weight, odd pixel, thin, needs
  floor) for 150, 151, 153, 157 (weight 14 against 0), 159, 161, 162, 166, 183, 185. Positions in a fight come from the sequences' dx (identical), so a fight in the open plays
  the same (p2_wins with `# p2 frames shadow` mirrors p1_wins frame for frame, only the digest differs: columns and
  collision boxes), but at walls and in the drawing player 2 would differ from player 1 by a pixel or a column.

**[choice] D1: player 2 uses the kid's frame table for all frames**, i.e. the kid's images, drawn as the user's "cheaper
look" with a colour variant (approved 2026-11-10 as the R <-> B plane swap of the kid blit; the user chose a **blue
suit and grey hair** instead on 2026-11-11: section 12.4). Then the shadow's image set
is not needed at all (no missing frames, no guard image set for level 1, no guard_wh table), and the two players are
exactly symmetric (tests/duel_scripts/p2_wins.txt mirrors p1_wins.txt tick for tick, checked). Kept as an option:
`DuelSim(kid_frames=False)` / `# p2 frames shadow` gives SDLPoP's shadow (frame_tbl_guard, the shadow's sizes for
collisions); it would need images for frames 183 and 185 (e.g. the kid's 215 and 79 in the kid's chtab) and the arena
loading the shadow's set where level 1 loads the guard's (TBL_GUARD_TYPE[1] = 0).

### 11.9 What phase 2 needs that the design did not foresee

1. **The collision rows per player**: +81 bytes of player 2's block (90 in all, not 9) and its swap (11.3).
2. **More patch sites**: D3, D12, D14, D15 besides the design's sword sites; and the duel's control for **both** players:
   the game's kid_tick (player 1) must not restart on the button after death, nor print the death text, nor play the
   death music, nor wait on a sound in the death counter; show_time must not run (else the duel expires after 60 min).
3. **Level 1 specifics of the arena**: the release's level 1 music crouch (need_level1_music: the kid would sit until
   the music ends) cleared; have_sword = 1 (level 1 starts without the sword); the level 1 start (the falling entry, the
   button of room 5 via trigger_button, the "LEVEL 1" text) overwritten by the arena setup and the round reset.
4. **The torches**: process_trobs is a stub in the design's table, but the arena's two torches flicker only through it
   (animate_tile's torch case, prandom). Either keep that path (the duel's logic does not depend on it, the seed is not
   hashed) or freeze the flames.
5. **Player 2's images** (D1): with the kid's table, player 2 draws the kid's images (the kid's whole set, sword
   frames included) in the guard's slot: the guard slot's fetch has to read the kid's set (frame store, SPRBUF_G
   up to the kid's largest frame), plus the colour variant. With the shadow's table instead: the arena must load the
   shadow's set (not level 1's guard set) and frames 183 / 185 need images.
6. **check_sword_hurt's order** with both hurt (the clash, D13): the kid's attack_was_parried first, then the shadow's; one hurt: hurt_by_sword reads the current frame's geometry (cur_frame, the last one loaded: player 2's), as SDLPoP's does; the Z80 must keep the same order.
7. **The trace's sample points**: the kid line is mid-tick (after player 1's frame), the G and D lines at the tick's end.

### 11.10 Decisions for the user

**All nine accepted by the user 2026-11-11, as built** (D1: player 2 drawn with the kid's images, **in a blue suit with grey hair** (12.4: the R <-> B swap first
approved, the blue suit and grey hair chosen 2026-11-11)plane swap; 8: no death music, text or restart in the duel).

1. **D1** player 2 = the kid's frame table and images (colour variant), not the shadow's set (11.8).
2. **D3** the "opponent jumping: no auto-draw" rule for both players.
3. **D14 / D15** the right edge bumps like the left one (a deviation from SDLPoP's behaviour at a room-0 edge).
4. **D12** instead of the design's HITP <-> GUARDHP exchange.
5. The round is decided at the first tick with a player at 0 hit points; a same-tick double death is a draw and is
   replayed (since the clash, D13, only possible from causes other than the sword: none in the arena today); the 36
   ticks after it change nothing. **D13 changed by the user 2026-11-11**: simultaneous hits are a clash, nobody is
   hurt (11.2).
6. ROUND_END_TICKS = 36; the match ends 36 ticks after the deciding tick; quit at once, rematch after the end.
7. Start columns 2 and 7: both draw their swords on a round's first tick.
8. In the duel no death music, death text or restart on the button; the death counter never waits on a sound; the
   silent sound model.
9. The hash: the explicit 68-byte list (11.7), without OPP_REC, CHAR_SAVE and the collision rows.

## 12. Phase 2: the local duel in Z80, as built (2026-11-11)

The duel runs on the MZ-800 from the title: **Ctrl+D**, two players on one machine, the rules of section 11 tick for tick.
Code: **src/duel/duel.asm** (the patch), **tools/duelpatch.py** (its pieces, the holes, the call-graph check),
**tools/z80flow.py** (the static control-flow walk), `make duel`; the launcher (src/boot/boot.asm ACT_DUEL), PRES
(src/pres/pres.asm p_duel), tools/mkgamedisk.py (POP800.PR3); tests **tests/duel_z80.py** (Z80 against duelsim) and
**tests/duel_boot.py** (from the floppy). The game's own code changed only by labels (kid.asm duel_d14, duel_d14r,
duel_d15; overlay.asm duel_sd1, duel_sd2): m4game.bin, its block 2, every overlay and m4test are byte-identical.

### 12.1 The patch: staged, laid in after the level start

**New against 1.4: the patch is staged.** The game's own level start (game_start, load_level, play_level) runs code
and writes variables inside the design's holes before the duel could take over (find_start_level_door writes
objects.asm's sc_pos, the level 1 start calls trigger_button, the guard-enter overlay runs at the first room): a patch
laid in before the start would be run or overwritten by it. So the launcher loads two POP800.PR3 entries:

| Entry | What | Where |
|---|---|---|
| PRS_DUEL1 (24) | every piece but P_main, concatenated in d_ptab's order (1,489 B raw) | one RAM-disk record: page 6 0x16C0 (rule 1's scratch: the chopper pictures' pool at runtime, none in the arena), before the GAME image (its buffers 0x2000-0x9FFF are the image's) |
| PRS_DUEL (23) | P_main (212 B): d_boot, the match loop, the quit | main RAM over game.asm's main loop (level_ready on), after the GAME image |

Then `jp GAME_START` as for any game: the game starts level 1 untouched and returns from game_start to level_ready,
which is now d_boot: it copies the staged pieces into their holes (d_ptab) and jumps to d_entry. The level start of the
duel is therefore the game's own, byte for byte (as duelsim's: KidSim(Level(1)) with its play_level); d_entry then does
the arena (duelsim arena_setup: room 3's links zeroed, no guards, no trobs / mobs, no level 1 music crouch, the text
erased, drawn room 3) and the first round (d_reset). The design's stubs (trigger_button and the trap entries as `ret`)
are not needed: nothing of the level start runs patched code, and the arena reaches none of the holes used (12.2).

### 12.2 The holes and the call-graph check

The holes used (duel.asm H_*, by the game's labels; tools/duelpatch.py checks every piece against them):

| Hole | Range (this tree) | Size | Used | Free |
|---|---|---|---|---|
| H_MAIN: game.asm's main loop (level_ready .. flip_now) | 0x200B-0x2133 | 297 | 212 | 85 |
| H_KT: kid.asm kid_tick (the duel has its own frame) | 0x6737-0x6858 | 290 | 207 | 83 |
| H_TICK: guard.asm tick_pre, tick_post, tick_end, timers, do_mouse, check_skel | 0xDAD4-0xDCD8 | 517 | 365 | 152 |
| H_AI: guard.asm the guard AI, play_guard_frame, play_guard, check_guard_bumped, dist_from_wall_behind, check_chomped_guard | 0xE096-0xE4C6 | 1,073 | 904 | 169 |
| H_FREE: main RAM free below W1 | 0x7B1B-0x7BFF | 229 | 0 | 229 |
| the patch sites H_D14 (3), H_D15 (2), H_SD1 (2), H_SD2 (2), H_PP1 (2), H_PP2 (2) | kid.asm, overlay.asm | 13 | 13 | 0 |
| **Code holes** | | **2,406** | **1,688** | **718** |

kid_tick and tick_pre / tick_post were not in 1.2's list: the duel has its own tick, so they are the cleanest holes. The
design's trap, view, gate / button / door, sound and clock holes (~3.5 KB more) stay unused: no stub is written, and
they stay available for phase 3-4 (with stubs for their statically reachable entries: the check names them, e.g.
start_chompers from land, check_get_item from control_standing is **reached** in the arena and must stay).

**The check (tools/duelpatch.py build, at every `make duel`, so in every CI build):** a walk of every path from d_boot
and the interrupt (isr) over the game with the patch laid in, the overlays at their windows (an overlay stub's
`ld a, id / call ovl_w1` names the overlay its jump enters), the kernel's self-modified calls resolved by hand
(INDIRECT: shr_call and the other unrolled chains of gfx.asm / kernel_gen.inc), the launcher (LN_LAUNCH) an exit.
Errors: a path reaching a hole's byte outside a piece; an edge from the game's code into a hole (a dropped routine's
entry, where a duel piece now lies); a fall-through into a hole; a game instruction naming a hole's address as memory.
Today: 19,424 instructions reached (the room, level, rare, events, low code overlays, and with the torches' tile redraw
the anim, button, door, frames and loose-floor overlays), no error, no cut needed (COLD is empty); two `jp (hl)`
dispatches stay unresolved and are left to the code log: room.asm dr_run's RR_HOOK (dirty_hook) and op_found's op handlers. Negative checks (a fake hole over play_seq, check_get_item, trigger_button, snd_again, start_chompers, sc_pos)
each fail the build with the paths.

**The profiler and code-log check (tests/duel_z80.py --cdl):** mz800emu's code log and call profiler from each script's
d_entry on: no byte of a hole outside the pieces executed, no call into a hole but to a duel label, no COLD callee;
over the seven scripts 1,304 of the pieces' 1,645 bytes run, 253 routines called, no hole reached.

### 12.3 The rules at their Z80 sites

| Site | How |
|---|---|
| D1-D9 (the kid's frame table, draw rule, sequences, parry, holding_sword, put away fast) | player 2's frame runs with **Char.charid = 0** and **Opp.charid = 1** (d_tick): every charid test of the game's sword code takes the kid's branch, the "opponent is the shadow" draw rule (D3) holds both ways. The only charid effect the duel must not take, kid_sword_strike = 15 on player 2's strike, is saved and restored around the frame. No patch in the game's code |
| D10, D12 (hurt), D13 | d_hurt: both hurt in one tick: the clash (the user's change 2026-11-11, 11.2): nobody hurt, both play attack_was_parried, the kid first; one hurt: the kid's or the shadow's hurt_by_sword; the shadow's with charid 0 (the kid's sound 13, no gate fix) and HITP_CURR / DELTA exchanged with GUARDHP_CURR / DELTA around it (take_hp on its own hit points) |
| D11 | check_can_guard_see_kid with the guard record's charid a guard's (2) for the call |
| D12 (death) | d_frame: the character's own hit points (HITP_CURR for player 1, GUARDHP_CURR for player 2) |
| D14 | kid.asm duel_d14 (bumped, pushed left into a wall): `jp d14`, which redoes the 4 instructions and maps room 0's column -1 to the room's own column 9 |
| D15 | kid.asm duel_d15 (is_obstacle's call of xpos_in_drawn_room): the call goes to d15 (room 0, column 0: +140) |
| the duel's control (11.4) | d_frame: control_kid without restart, keys, death music, text or wait; the death counter counts to 100 |
| the block (11.3) | d_swap: 90 bytes exchanged around player 2's frame (d_blkmap: ctrl1 + grab_timer, have_sword, offguard, holding_sword, prev_collision_row, the 80 bytes of collision rows) |
| rounds, reset, hash | d_round, d_reset, d_hash (the 68-byte list of 11.7; the round count is a byte: it wraps at 256 as duelsim's & 0xFF) |

Not called in the duel's frame: check_press, check_spike_below, check_spiked, check_chomped_kid, check_knock (no such
tiles; duelsim calls them, they do nothing there). The tick's end calls snd_next (play_next_sound, the N line).

### 12.4 Input, pacing, drawing, sound

- **Input** (d_input, the byte of 11.6): player 1 the game's read_inputs (cursor keys, SHIFT, joystick 1), **BREAK**
  quit, **ENTER** rematch; player 2 **W A S D**, **Q** the button, joystick 2 (IN F1h, the layout of joystick 1).
  Checked in tests/duel_boot.py from the emulator's keyboard; joystick 2 not (the harness has no second joystick).
- **Pacing**: mode 0, every tick drawn, at least 4 frames (game.asm's rule). Measured over match.txt (572 ticks, the
  4-frame floor included): **5.55 frames a tick at 512 KB, 5.26 at 1 MB, 4.95 at 16 MB** (design 5.1 expected 7.2-8.6
  with the XOR look; the cheaper look makes the difference; the torches cost ~0.44 of it).
- **Drawing**: the game's (the full room draw once, draw_objects, hp_draw). Player 2 is drawn with its record's charid
  0 for the drawing (d_loop): the kid's images through the kid's frame table, no XOR look, its strip at the right
  (ghp_draw; GHP_M set at each round's start so the full strip shows at once). Its colours: **one plane operation on the drawn
  pixels** (d_sdraw, a copy of gfx.asm spr_draw's kernel, at overlay.asm's two spr_draw calls for the guard's
  descriptor SPR_G), chosen at build time by `DUEL_LOOK` (`make duel DUEL_LOOK=n`; extra T a drawn cell against the
  kernel's ~110): **0 a blue suit, grey hair** (the default, the user's choice 2026-11-11). The kid's images use only
  colours 2, 6, 7, 8, 10 and 15. Where plane I (B) is set, planes II and III (R, G) are cleared: white 15 becomes light
  blue 9, light grey 7 blue 1. Where R alone of B, R, G is set (the hair, 2 and 10), R is cleared and plane IV set:
  grey 8. The skin 6 and the outline 8 stay. Per cell: R' = R & G & ~B, G' = G & ~B, I' = I | (R & ~G & ~B), with ~B
  in IXL and G | ~drawn, then the hair, in IXH: +117 T a drawn cell, measured +0.02-0.05 frames a tick against the
  suit alone. Colour 8 needs nothing special: the kernel's transparency is "no plane set" (colour 0), the images' black
  is stored as 8 and shows dark grey, and the grey hair is that grey. The other looks, for comparison: **1 a blue suit
  only** (+32), **2 R <-> B** (planes I and II swapped, the skin cyan, the hair blue; +16), **3 R <-> G** (the hair
  green; +16), **4 no B** (plane I cleared: a golden outfit; -7), **5 I inverted** (plane IV XOR (I | II | III): XOR 8
  on every drawn pixel but the outline: light grey clothes, light yellow skin, light red hair; +20). The outline stays
  as it is in all six. Its sword and splash are plain. **The torches flicker as in the game** (the user's choice 2026-11-11, 11.9.4): d_entry registers the room's two torches as at a room entry (d_torches: genter.asm anim_tile_modif's torch part, a random first frame and a trob each), d_tick runs the game's process_trobs (animate_tile's torch case, prandom) where SDLPoP's tick does, and the match loop takes the game's view_snapshot / view_redraw path for the changed tiles. prandom is lockstep state only the torches use: no logic reads it, it is not hashed; duelsim does the same (arena_setup anim_tile_modif, process_trobs in step), so the trace (the trob count, the room's checksum) stays exact. Measured cost: +0.44 frames a tick at 1 MB (match.txt 4.82 -> 5.26). No flash on a hit (the game's
  flash is the kid's only).
- **Sound**: the silent model (SND_MODE 0, decision 8): every effect plays, nothing waits on one.
- **Exit**: BREAK (quit) -> GAME_OVER 3 -> the level-start overlay's handoff with ACT_TITLE: PRES's title. The next
  game start restores a clean GAME image (checked: the main loop's bytes back).

### 12.5 Figures

| | Reserved (1.5) | Used | Left |
|---|---|---|---|
| Resident game bytes | 0 | **0** (the holes only) | main 229, low 6, block 2 13 as before |
| Floppy | 40 blocks | **6** (POP800.PR3, blocks 1076-1081) | 34 |
| Launcher | 100 B | **17** (LN_DUEL_USED) | 83 |
| PRES | 64 B | **23** (DUEL_PRES_USED: Ctrl+D) | 41 |
| RAM-disk scratch (page 6 0x16C0-0x287F) | runtime only | 1,489 B while the duel starts | |

PRES grew by 23 bytes, so the title art's first fit moved some bands (POP800.PRS / PR2 differ in PRES's and the title
art entries and the index; the D files, the GAME image and every game program are unchanged).

### 12.6 Tests

- tests/duel_z80.py: per tick the kid line (mid-tick), the G line, the N line, the D line (the round state, the hash,
  both blocks) of the Z80 (tracepoints at d_mid, d_gline, snd_snap, d_tend) against duelsim; the Z80's own hash
  against the hash of the bytes it hashes. All seven scripts (1,231 ticks): **0 differing lines at 512 KB, 1 MB, 16 MB**.
  PR tier b (with --cdl), the full regression's pixels-m6 part (three sizes), the smoke tier (parry).
- tests/duel_boot.py: the floppy path (Ctrl+D, the handoff, the pieces in main RAM, the start tiles, the input bytes,
  BREAK back to the title, a clean game after). PR tier c, the full regression's launch-keys part.

### 12.7 Open for the user

1. The torches: decided (they flicker as in the game, 12.4).
2. Player 2's colours: decided (a blue suit, grey hair: DUEL_LOOK 0); the others stay selectable at build time.
3. Player 2's hit point strip uses the guard's icon (level 1's guard set); the kid's icon in the suit's colours is a phase
   3 HUD question.
4. Local keys: BREAK quit and ENTER rematch (both players' bits are the same locally); after a match the players stand
   until ENTER or BREAK (no HUD yet: phase 3).
5. PRS_DUEL1 holds the staged patch (not a one-shot overlay as 1.4 planned); phase 4's lobby code can go into the same
   staging (4.5 KB scratch, 1.3 KB used) and be copied to W2 when needed.

From the user's playtest (2026-11-11): simultaneous hits became a clash (D13, 11.2); "only player 1 puts the sword
away when the two are far apart" did not reproduce (duelsim and the Z80 sheathe both on the same tick when they walk
apart, tests/duel_scripts/apart.txt, also from the keyboard in the emulator; a player pressing down sheathes at once);
after a match the players stand until ENTER (rematch) or BREAK (the title): kept until phase 3.

### 12.8 The blades (the user's decision, 2026-11-11)

Kid against kid, both drawn from the kid's frame table (D1), the blades did not meet in a parry and lay on top of each
other en garde: SDLPoP's poses were drawn for the kid against a guard. At the parried tick the attacker is in frame 167
(blade at mid height, y - 19) and the parrier in 161 (blade raised, y - 35); the kid's en garde (158, 170, 171) holds its
blade level at y - 23 for both players. With the user's constraint that the hilt stays in the hand, a sword-only nudge
(the gap is ~13 rows) and shifting a body were ruled out, and so were the guard table's swords on a kid body (off the
hand). **Chosen: whole kid frames remapped for the drawing, body and sword together (C2 + E1):**

| Player | Logic frame | Drawn as | Effect |
|---|---|---|---|
| 1 | 161 (parry) | 158 (en garde, level blade) | meets player 2's mid-height lunge |
| 2 | 161, 158, 170, 171 | 157 (after a strike: a lower, angled blade) | meets player 1's lunge; en garde the two blades sit at two heights |

Drawing only: duel.asm d_ppchar, at overlay.asm people_place's two calls of pp_char (duel_pp1, duel_pp2; labels only in the
game), changes K_FRAME in the drawing's copy of the record (people_place restores KV from PP_SAVE): no logic, hash or
trace change. 44 bytes in H_TICK, 8 in d_ptab and two 2-byte operands; ~80 T per character per drawn tick. Checked by
tests/duel_z80.py every tick: the body and sword images the Z80 draws (the descriptors' SD_FRAME at d_done) equal
duelsim's records through the same map (DRAW_MAP; with the map emptied the check fails). Renders: the candidates
against SDLPoP's kid against a guard (docs only, the user's renders blades2_*.png).

Phase 3 is section 13, phase 4 (the network) section 14. A hit flash for both players is not built (the game's flash is the kid's).

## 13. Phase 3: the HUD, the texts and the sound, as built (2026-11-11)

Drawing and audio only: the logic, the hash and duelsim's trace (every line, the 'N' line included) are unchanged, and
nothing of it waits on the screen or the PSG. Code: src/duel/duel.asm d_hud, d_ghp, d_snd; the checks in
tools/duelpatch.py (the texts, the W2 calls) and tests/duel_z80.py (the text and the tunes every tick against duelsim's
state). The game's own code is unchanged (no new label either): m4game.bin, every overlay and m4test byte-identical.

### 13.1 The screen

The bottom row as the game has it: player 1's hit point strip at the left (the game's hp_draw), player 2's at the right
and the text line between them (x 80-239, rows 193-199, the game's font, white).

| When | The text line (duel.asm d_strs) |
|---|---|
| a round's first 20 ticks drawn (ROUND_TEXT_TICKS) | `ROUND n` |
| the rest of the round | `ROUND n   P1 a : b P2` (the round's number, then the score) |
| the 36 ticks after a round's decision | `P1 WINS ROUND` / `P2 WINS ROUND`; `DRAW` for a same-tick double death (not reachable by the sword since the clash, D13); `P1 WINS THE MATCH` / `P2 WINS THE MATCH` when that round was the third win |
| the match over (waiting for ENTER / BREAK, no auto-return) | `P1 WINS THE MATCH` and `ENTER REMATCH  BREAK QUIT` in turn, 32 ticks each (HUD_ALT) |

The round's number counts the draws (the round state's `rounds` + 1, shown up to 99). Rematch (ENTER) and quit (BREAK)
are phase 2's: the prompt only shows them.

**Player 2's strip** is drawn like player 1's (d_ghp through the rare overlay's hp_strip): the full icons and the empty
ones up to its maximum, mirrored from the right edge, the full icon the kid's with planes I and II (B, R) swapped: blue
where player 1's is red (d_hpicon, made from hp_full at the duel's start). The game's guard strip (the guard's icon, only
the full ones) is no longer drawn: the match loop calls hp_draw with player 2's record's charid back to the shadow's,
for which ghp_draw draws nothing off level 12. The empty icons are the game's (hp_empty, red outlines) for both.

### 13.2 The texts: the game's text overlay, called in place

The text overlay (src/m4/text.asm, W2) prints only the game's messages from its table, so d_hud uses its parts: when the
text's key (d_key: its kind and up to three numbers) changes, d_hud loads the overlay into W2 as text_chk does (after
the tick's drawing, when the compose buffers are free), writes the string into its td_str (the numbers through its
td_num), blanks the line's bitmap (MASKBUF) and calls its td_render and td_put (centred, three chunks, blit). The
labels come from build/ovl_text.sym (tools/ovltool.py equp -> build/duel_text.inc, TX_*).

The game's font has only the glyphs of the game's texts. The duel's texts need four more (K, Q, W and the colon): taken
from SDLPoP's font like the others (tools/build_assets.py --font-duel -> build/assets/font_duel.inc: d_font, 36 B) and
laid by d_hud over the loaded copy's lowercase records (e, i, n, o: the duel's texts are capitals); the RAM disk's image
of the overlay stays the game's. **tools/duelpatch.py checks every string of d_strs** at every build: each character has
a glyph in that font, and its width (SDLPoP draw_text: each glyph + 1, the numbers as the widest two digits) fits the
line's 160 pixels. "ENTER: REMATCH  BREAK: QUIT" is 165 pixels; the prompt is therefore `ENTER REMATCH  BREAK QUIT`
(159). Widths today: ROUND n 54, the score line 145, P1 WINS ROUND 93, DRAW 29, P1 WINS THE MATCH 119, the prompt 159.

**The call graph** (12.2): a jump from a duel piece into W2 is resolved to the text overlay (duelpatch.py PIECE_W2; it
must hit a label of that overlay), so the walk covers td_render, td_put, td_num and what they call (the text overlay now
in the reached list). Run-time the code log check is unchanged (W2 is no hole).

Cost: a text change loads the overlay (1,021 B) and draws the line, ~1 frame, on ~4 ticks of a round; an unchanged text
costs the key's compare.

### 13.3 The sound

Phase 2 already played every requested effect for both players: player 2's frame runs with the kid's charid, so its
sounds are the kid's (the sword drawn 19, the clash 10, the hit 13, the footsteps 23, the swish 11...). But with the
silent model every request started at once, cutting whatever the PSG played. **d_snd** replaces the game's snd_next in
the duel's tick:

- **The logic's side is the silent model, unchanged**: the queued request starts (SND_CUR), nothing "plays" (the 'N'
  line's third figure 0), snd_snap (the trace) as before. So duelsim's 'N' line and every logic wait stay as they were.
- **The PSG's side** applies the game's priorities (sound.asm snd_tab) against what the PSG really plays (the player's
  SP_WAIT, the last id given, d_acur): a request starts on the PSG when the PSG is idle, or the playing sound is
  interruptible and the request's priority is equal or higher. Audio only: it may differ between two machines.
- **The tunes**: JINGLE_DELAY (3) ticks after a round's decision (after the hit's sound), the guard's death tune
  (sound 37, 4.1 s) for a round, the level's end music (41, 12.8 s) for the match's deciding round, none for a draw.
  Both are non-interruptible, so the fight's leftover sounds do not cut them; a round's reset (d_reset: d_acur = none)
  lets the next round's first sound (the swords drawn) cut them, also after a rematch. Both pieces are in the game's
  in-game bank already (sndconv.py MUSIC_GAME).

Sound off (Ctrl+S on the title) is the game's: it mutes the PSG writes.

### 13.4 Memory, disk, speed

| Hole | Size | Used (phase 2 -> 3) | Free |
|---|---|---|---|
| H_MAIN | 297 | 212 -> 227 (the HUD's calls, the redraw after the room draw) | 70 |
| H_KT | 290 | 207 -> 283 (d_ghp, the icon) | 7 |
| H_FREE (new piece P_free) | 229 | 0 -> 216 (d_hud, d_key) | 13 |
| H_TICK | 517 | 365 -> 508 (the strings, d_font) | 9 |
| H_AI | 1,073 | 904 -> 1,041 (d_snd, the icon's set-up, the HUD's variables) | 32 |
| **code holes** | 2,406 | 1,688 -> **2,275** | **131** |

Resident game bytes 0. Staged (PRS_DUEL1) 2,061 of 4,544 B; P_main 227 B. Floppy: POP800.PR3 6 -> **8** blocks (32 of
the 40 reserved left). Launcher and PRES unchanged (83 and 41 B of their reserves left). The design's trap, view, button
and clock holes (~3.5 KB) are still unused: phase 4's network code needs them.

Speed (tests/duel_z80.py, match.txt, 572 ticks, frames a tick; the text's redraws included): **5.49 at 512 KB, 5.22 at 1 MB, 4.89 at 16 MB** (phase 2 with the blades on the same tree: 5.46, 5.18, 4.86): +0.03-0.04 frames a tick.

### 13.5 Tests

- tests/duel_z80.py, every tick besides phase 2's lines: the text's key d_key against hud_key (duelsim's round state,
  the ticks since the round's reset), the tunes (ds_j: tick and id) against jingle(). All seven scripts 0 differing
  lines at 512 KB, 1 MB, 16 MB; the code log check: no hole reached. (Checked negatively: a 21-tick ROUND text or
  another tune id fails.)
- tests/duel_boot.py (from the floppy): the first text is `ROUND 1`, the swords' sound (19) plays on the PSG.
- tools/duelpatch.py at every `make duel`: the pieces in their holes, the call graph (the text overlay walked), the
  texts' glyphs and widths.

### 13.6 Decisions for the user (defaults chosen, each one constant or string in duel.asm)

1. The wording: `ROUND n`, `ROUND n   P1 a : b P2`, `P1 WINS ROUND`, `DRAW`, `P1 WINS THE MATCH`, and the prompt
   **without colons** `ENTER REMATCH  BREAK QUIT` (with the colons it is 5 pixels too wide for the line).
2. The timing: `ROUND n` alone for 20 ticks; the winner and the prompt alternating every 32 ticks after the match.
3. Player 2's strip: the kid's icons in blue with the empty ones (as player 1's), instead of the guard's icon.
4. The tunes: 37 (the guard's death) after a round, 41 (the level's end) after the match, starting 3 ticks after the
   deciding hit; none after a draw.
5. The PSG respects the game's priorities (a playing non-interruptible sound is not cut), the logic stays silent.

## 14. Phase 4: network play, as built (2026-11-11)

Two MZ-800s play the duel over the MZPico NET service as BomberNet plays (section 4): the host is player 1 (the kid),
the joiner player 2; one input byte a player a tick (11.6) in lockstep, the 16-bit state hash (of the 68 bytes of 11.7) every tick compared by the
relay. Code: src/duel/duel.asm (d_lobby, the NET driver n_*, d_net, d_nfail); tests/duel_net.py (two emulators through
BomberNet's relay/relay.py run locally); tools/duelpatch.py (four new holes, the build id, every `dst_` text checked).
The game's own code is unchanged: m4game.bin, every overlay, the launcher and PRES are byte-identical to phase 3's.

### 14.1 The fit (milestone 0)

The design's "trap, view, button and clock holes, ~3.5 KB" was an estimate from 960bcaf. On this tree the view hole is
no longer free (the torches' redraw uses view_snapshot / view_redraw since phase 2) and some trap code is reached by
the torch path (animate_tile). A walk with tools/duelpatch.py's call graph over the patched image (every m4game.sym label
range with no reached byte and no memory or immediate reference into it) gave these code holes, all taken:

| Hole | Range | Size | Used | Free | The game's code there | The duel's piece |
|---|---|---|---|---|---|---|
| H_OBJ | make_loose_fall .. foh2 (objects.asm) | 675 | 656 | 19 | loose floors, knocks, falling floors | P_obj: the lobby (410), the keys (70), the NET driver and detection (176) |
| H_LR | leave_room .. kid_tick (kid.asm) | 311 | 281 | 30 | the room change | P_lr: the lockstep d_net (215), the failures (47), NETLEAVE (19) |
| H_SPK | check_spiked .. start_chompers (objects.asm) | 205 | 176 | 29 | the spikes | P_spk: NETCREATE's parameters (23), the 11 texts (153) |
| H_TIME | death_text .. draw_game_frame (evres.asm) | 174 | 103 | 71 | the death text, the clock | P_time: d_font (63, moved from H_TICK: 3 more glyphs), the network's variables (40) |

With phase 3's: **code holes 3,771 B, used 3,481, free 290** (phase 3: 2,406 / 2,275 / 131). P_main 253 B of 297
(+26: the hooks, four d_ptab rows). Staged (PRS_DUEL1) 3,241 of 4,544 B. **Resident game bytes 0, no overlay window,
no new RAM-disk space; launcher and PRES unchanged** (83 and 41 B of their reserves left). Floppy: POP800.PR3 8 -> **12
blocks** (28 of the 40 reserved left). The code log and the static check cover the new holes as the others.

### 14.2 What the player sees

Ctrl+D on the title: the arena is drawn first (the full room draw, both players standing), then the bottom line
`1 LOCAL  2 HOST  3 JOIN` (BREAK: the title).

- **1**: the local duel of phases 2-3, unchanged.
- **2 HOST**: NETCREATE; `ROOM CODE ABCD` until the other player is in (NETSTATUS members = 2), then ready.
- **3 JOIN**: `ROOM CODE ....`; letters fill the dots (DEL deletes, ENTER with four letters joins); `WAITING` until the
  match starts.
- Both: when the relay starts the room (NETSTATUS RUNNING) the match starts at tick 0 on both machines.
- In the match: `WAITING` on the text line when the other machine's input is 0.5 s late (the HUD's text comes back
  after); BREAK while waiting gives up. Quit (BREAK) and rematch (ENTER) are the input byte's bits as in local play:
  both machines act on them at the same tick.
- Errors in the lobby (2 s, then the menu): `NO NETWORK CARD`, `NO LINK` (error 9: no relay), `OTHER VERSION` (6: the
  other disk's build id differs), `NO SUCH ROOM` (7), `NETWORK ERROR` (other). In the match (3 s, then the title):
  `DESYNC` (the relay saw two hashes differ), `OTHER PLAYER LEFT` (the room dropped), `CONNECTION LOST` (no link, a
  failed command, or 10 s without the other's input).

The player's own keys over the network: either local set (the cursor keys / SHIFT / joystick 1 or W A S D / Q /
joystick 2, ORed), BREAK and ENTER.

### 14.3 The driver (duel.asm P_obj; BomberNet c/common/netdev_card.c)

Ports 0x50 (command, status) and 0x51 (data). `n_do` (A command, HL parameters, B count) sends the command and its
fixed-size parameters (otir), then `n_wait` reads the 4-byte status (STSR, inir) until it is neither IN_PROGRESS nor
BUSY: Z = done, else A = the error (status byte 2; 10 parameters incomplete; 9 when IN_PROGRESS lasts 1,024 frames,
~20 s). A missing card floats the ports: ERROR is set, nothing hangs. Detection (`d_ndet`, at HOST or JOIN): REVD's
status {02, 06, 04}, then INFO with no ERROR, OUTPUT, the command echoed, >= 16 bytes, and the NET bit (byte 3 bit 3).
Commands used: STATUS, CREATE, JOIN, LEAVE, READY, SEND, POLL, HASH (not MSG / RECV).

### 14.4 The lockstep (duel.asm P_lr d_net, called in d_loop after d_input)

Per tick T (the relay's frame number, 16 bits from 0):

1. NETHASH(T - 1, d_hashv): the 16-bit state hash after the previous tick (2 bytes: the hash of the 68 bytes of 11.7,
   already computed every tick);
   the relay compares the two machines' hashes of each frame and flags DESYNC.
2. NETSEND(T + D, own byte) (4 bytes, the room's 1 used).
3. NETPOLL(T) until avail >= T; its two bytes become d_in1 (slot 0, the host) and d_in2 (slot 1). While waiting:
   NETSTATUS every try (DESYNC, DROPPED, NO LINK end the match), BREAK, `WAITING` after 25 frames, CONNECTION LOST after
   500 frames (10 s) since the wait began.
4. The tick runs (d_tick) on those two bytes alone, then the drawing.

The start: both send frames 0 .. D-1 without keys (BomberNet's net_match_start), so the first D ticks are keyless on
both machines. **The logic sees only the agreed bytes**: d_net writes d_in1 / d_in2 and nothing else of the logic's
state; WAITING and the error texts are drawing; prandom (the torches) is untouched; the network's variables are never
hashed. The harness (d_script) feeds each machine's own player's byte from the script instead of the keys.

**The leave**: NETLEAVE waits 1 s first (NET_LEAVEW). A quit is both machines' at one tick, and the device refuses
NETPOLL as soon as its room is dropped: without the wait the slower machine, still polling the quit tick's input, saw
OTHER PLAYER LEFT (found by tests/duel_net.py).

### 14.5 The room (design 4.6, decision 1)

| Field | Value |
|---|---|
| game id | 0x5050 ("PP") |
| build | a CRC-16 (CCITT) of build/m4game.bin, build/m4ovl.bin and every piece of the patch (d_build 0 while computed), laid into d_build by tools/duelpatch.py (`the network's build id` in the build's output): two different disks are refused at JOIN (OTHER VERSION) |
| slots, bytes a slot | 2, 1 (the input byte; no delay byte: the delay stays the lobby's) |
| settings | 1 byte: the input delay D (the host's NET_DELAY = 1; the joiner takes it) |

### 14.6 Speed

Local play is unchanged (tests/duel_z80.py match.txt: **5.50 / 5.22 / 4.90 frames a tick at 512 KB / 1 MB / 16 MB**,
as phase 3). The network's own work a tick, without waiting: **1,470-2,180 T (0.03 frames)**: NETHASH, NETSEND, one
NETPOLL and its read, in the emulator's NET device.

**At a real MZ-800's speed** (`tests/duel_net.py --realtime`: each emulator advanced one frame per 20 ms of wall time,
both through the local relay over TCP; the headless emulator's own "normal" speed is throttled to ~0.6 frames a
second and cannot be used):

| Script, D (1 MB, the local relay) | Local (duel_z80) | Host A | Joiner B | Frames waited in d_net a tick (A / B) |
|---|---|---|---|---|
| match.txt (573 ticks), D = 1 | 5.22 | 5.24 | 5.50 | 0.03 / 0.82 |
| p1_wins.txt (149 ticks), D = 1 | 5.35 | 5.29 | 5.31 | 0.09 / 0.13 |
| p1_wins.txt, D = 2 | 5.35 | 5.28 | 5.47 | 0.01 / 0.43 |
| p1_wins.txt, D = 3 | 5.35 | 5.28 | 5.48 | 0.01 / 0.59 |

So a networked match plays at the local pace within ~5 % (the frames of the two machines differ a little because the
harness paces two emulators from Python threads, not because of the duel). A larger delay brings nothing: with no tick
clock (decision 6) the pace is the slower machine's drawing, and D only has to cover the one-way trip within a tick
(~105 ms at 5.3 frames); on a local relay that is ~1 ms, through mzpico.com ~65 ms (section 4.2). The poll loop spins
on NETPOLL without a halt, so the input is taken within microseconds of its arrival; a different strategy would gain
nothing measurable. **Recommendation: keep D = 1**; raise NET_DELAY to 2 only if real-hardware play through mzpico.com
shows WAITING often.

**The ~13-16 frames a tick of the full-speed test runs are the harness's, not the duel's.** At full speed the headless
emulator runs ~1,000 frames a second (50 frames in 0.05 s, measured), so 1 ms of wall time is one emulated frame: a
line through the local relay's TCP (the emulator's NET device writes the line and its newline in two send() calls:
Nagle's algorithm and the delayed ACK hold the second for up to ~40 ms), the Python relay and the other emulator's
thread scheduling are tens of ms, so tens of frames in which the waiting machine spins in NETPOLL (the debug trace:
waits ending at the 50-frame step boundaries of the driver). At 50 Hz the same wall time is a frame or two, inside
the tick's ~5 frames of drawing.

### 14.7 Tests

- **tests/duel_net.py** (new; PR tier b and the full regression's pixels-m6 part, so at 512K, 1M, 16M): the relay
  (BomberNet relay/relay.py's JSON-lines TCP server on a free port of 127.0.0.1; a stand-in for its fastapi import when
  that is missing; CI fetches relay.py at a pinned BomberNet commit, `BOMBERNET_COMMIT`), two emulators
  (`POP800_NET_RELAY`: emu/mz800emu-pop.sh writes the INI's `net_relay`), the game and the patch laid in as
  duel_z80.py does with the menu kept (d_hnet = 1): A presses 2, B presses 3, types X, DEL and A's code, ENTER; both play
  match.txt (573 ticks), each machine its own player's byte of the script. **Both machines' kid, G, N and D lines equal
  duelsim's trace of the script delayed by D, every tick, 0 differing lines**; both hashes equal their states. Then
  with fresh machines: another build id (OTHER VERSION, the menu again), a hashed byte changed on B (DESYNC on both,
  the title), B closed (OTHER PLAYER LEFT), B paused (WAITING, then CONNECTION LOST 500 frames after the wait began),
  no relay (NO LINK, the menu, then 1 LOCAL plays). Never the public relay.
- tests/duel_z80.py: unchanged scripts, the harness's d_script skips the menu; all seven scripts 0 differing lines at
  512K, 1M, 16M; the code log over the new holes: no hole reached.
- tests/duel_boot.py: from the floppy, the menu over the arena, 1 LOCAL, then as before.

### 14.8 What only real hardware can show

1. The MZPico doing the RAM disk (pico_rd, port 0x45, ~100 KB a second of art in a duel) and the NET device at once:
   the firmware's NET commands answer from ring buffers; whether the art streaming delays them is untested.
2. The detection on a real MZPico (REVD / INFO's NET bit) and on a machine without one (floating ports: NO NETWORK CARD).
3. The round trip through mzpico.com's production relay (WebSocket, Pico W): the delay D = 1 is sized for its ~130 ms
   (section 4.2); `WAITING` showing often would mean D = 2.
4. Two players on the two keyboards: the lobby's key decoding (the digits 1-3, letters, DEL) on a real MZ-800 matrix.
5. A long session: the frame number is 16 bits, so a room plays ~65,000 ticks (~1.8 h at 5 frames a tick); after that
   the device has no frame to give and the match ends with CONNECTION LOST.

### 14.9 Decisions for the user (defaults chosen)

1. The menu: `1 LOCAL  2 HOST  3 JOIN` after Ctrl+D, over the drawn arena; the room code shown as `ROOM CODE ABCD`.
2. The input delay **D = 1 tick** (NET_DELAY; the room's settings carry it). See 14.6 for D = 2 and 3.
3. The texts: `WAITING`, `NO NETWORK CARD`, `NO LINK`, `OTHER VERSION`, `NO SUCH ROOM`, `NETWORK ERROR`, `DESYNC`,
   `OTHER PLAYER LEFT`, `CONNECTION LOST`; lobby errors return to the menu after 2 s, match errors to the title after 3 s.
4. Over the network a player's own fighter takes either local key set (cursor keys / SHIFT / joystick 1 and W A S D /
   Q / joystick 2).
5. The hash goes to the relay every tick (the design had every 16th): ~2 lines a tick more, the desync seen at once.
6. NETLEAVE 1 s after a quit (14.4).
7. No in-match delay adaptation and no MSG-based RTT measure in the lobby (design 4.4): the delay byte is not sent; a
   phase 5 option if real play shows waits.

The native mz800emu reaches only a relay over TCP (relay.py, `net_relay` in [UNICARD]); the production relay at
mzpico.com is WebSocket-only, so two emulators play through a relay.py on a LAN or one PC (docs/duel-net-howto.md).

## 15. The random arenas, as built (2026-11-12)

The user's decision "B": **per match a level (any of 1-14), per round a random room of that level**, the same on both
machines and in duelsim. The rooms' traps and mechanisms become plain floor at the room's setup (their game code is the
duel's holes), the bottom row's holes are filled, the room's links are zeroed as before (its edges are walls: D14,
D15). Code: src/duel/duel.asm P_w2 (the arenas' piece), d_arena, d_mstart; tools/duelsim.py (the pool, the choice, the
setup: the oracle); tools/duelarenas.py (the survey, the contact sheets, the arena table for the Z80). The game's own
code is unchanged (m4game.bin, every overlay, the launcher and PRES byte-identical).

### 15.1 The survey and the pool

tools/duelarenas.py grades every room of levels 1-14 after the substitutions: the fight run (the longest run of at
least 6 tiles a player can stand on; the start columns 5 apart, centred: today's 2 and 7 on a full row), the kid's own
moves between the runs played by kidsim (climb up, jump, run off an edge, climb down, standing and running jumps: a run
reached that cannot get back is a trap), random duels (6 seeds x 1,200 ticks of mostly approach-and-strike input, plus a
seed starting on each other run reached: a player leaving the room fails it) and the duel scripts. Grades: A one row,
the run >= 8; B one row, 6-7; C several rows, safe; D a 2-row drop (a hit point); X unusable. Of the 330 rooms: A 107,
B 17, C 48, D 14, X 144. The random duels found what the move graph missed: in a narrow pit next to an interior thick
wall (level 2 room 5, level 1 room 6) a pushed-back player falls out of the room (SDLPoP's bumpfall in a closed room).
The contact sheets (2x, both players at their start tiles, as the duel draws them) went to the user; renders are not in
git (`duelarenas.py --render-from`).

**The pool (the user's pick, 2026-11-12: the proposal, grade A only), 72 rooms**, duelsim ARENA_POOL:

| Level | Rooms | Level | Rooms |
|---|---|---|---|
| 1 (dungeon) | 3, 2, 21, 19, 24 | 8 (dungeon) | 6, 24, 16, 4, 3, 12 |
| 2 (dungeon) | 4, 11, 19, 23, 18 | 9 (dungeon) | 11, 13, 21, 9, 2, 5 |
| 3 (dungeon) | 13, 9, 6, 2 | 10 (palace) | 21, 5, 2, 19, 15, 8 |
| 4 (palace) | 2, 10, 14, 6, 1 | 11 (palace) | 15, 19, 8, 14, 7 |
| 5 (palace) | 12, 16, 18, 7 | 12 (dungeon) | 20, 2, 1, 19, 16 |
| 6 (palace) | 16, 12, 2, 4, 6 | 13 (dungeon) | 23, 16, 1, 19, 10 |
| 7 (dungeon) | 22, 2, 13, 6, 19, 12 | 14 (palace) | 1, 2, 3, 4, 5 |

`duelarenas.py --asm` writes the table the Z80 reads (build/duel_arenas.inc, a make dependency of the patch): entry 0 the
fixed arena (level 1 room 3), then each level's pool (the room + 32 x the row, player 1's column: 2 bytes an entry, 146
B), w_lvtab (each level's first entry and count, 28 B) and w_cls (per tile type: 1 a trap or mechanism, 2 no floor; 32
B). The rows and columns come from duelsim's own fight-run rule, so the pool is the only hand-written part.

### 15.2 The choice (duelsim arena_rnd, match_level, round_arena; duel.asm w_rnd, w_match, w_round)

From the 16-bit seed, the match's number (d_mtch, +1 at every rematch) and a byte b: x = seed ^ (match << 8) ^ b; three
times an xorshift16 step (7, 9, 8; 0 taken as 0xACE1) and + 0x7F4A; the result's high byte XOR its low. The carries of
the addition make it non-linear (with two plain xorshift steps only 56 of the 196 level pairs of two matches ever came
out); over all seeds every pair of levels and every triple of rooms comes out, within about +-20 % of uniform.

- the match's level: 1 + rnd(b = 0xFF) mod 14 (a rematch: the next match number, so a new level);
- round k (the round state's `rounds`, draws included, modulo 256): round 0 the pool's entry rnd(k) mod n; later
  rounds (last + 1 + rnd(k) mod (n - 1)) mod n: **never the same room twice in a row** (a drawn round, replayed, gets a
  new room too).

The arena's entry (0 the fixed arena, else its index in the table) is **the first byte of the state hash** (69 bytes):
0 leaves the hash of the 68 bytes as it was, so the fixed arena's traces and digests are those of phases 1-4.

### 15.3 The room's setup (duelsim arena_set; duel.asm w_set)

Unless the entry is the last one set up: the room, row and columns into d_room, d_arow, d_c1, d_c2 (d_reset reads them
instead of phase 2's constants); the room's four links 0; no guards; every tile of class 1 (spike, loose floor, chopper,
the three buttons, gate, its door top with floor, potion, sword, mirror, both level door halves) and every bottom-row tile
of class 2 (empty, door top, big pillar top, the four lattice pieces) becomes floor (the byte 1) with modifier 0;
TROBS_N, MOBS_N 0; SHOWN_ROOM 0 (the full draw), vs_built and HP_SHOWN 0xff; DRAWN_ROOM, NEXT_ROOM; the torches as at a
room entry (phase 2's d_torches, now here: a random first frame and a trob each); then d_reset. The substitution changes
only the duel's copy of the level in main RAM.

### 15.4 The level per match (duelsim level_load; duel.asm w_load)

When the match's level is not the one loaded (d_lvl): the blueprint from the RAM disk (page RD_LV_PAGE, as load_level
copies it), LEVEL_TYPE and the env's and wall's directories (dungeon or palace), the alter-mods pass (the level-start
overlay loaded into W2 below P_w2, its alter_mods called in place: build/duel_level.inc), then **level_number = 1**: the
level's own rules stay off (level 12's coupled hit points in do_delta_hp and its guard strip, its hidden floors, level
13's and level 4's specials); the duel's rules were built and checked on level 1. duelsim does the same (the level's
number 1; the survey found the coupling: level 12's rooms played only 5 of 7 scripts as level 1 room 3 before it). No
level start runs (no guards, no events, no cutscene, no frame store fill: player 2 is drawn with the kid's images). The
guard image set of the level the game started with stays in the frame store, unused.

The duel's entry is unchanged in what the player sees: the fixed arena (level 1 room 3, the game started level 1) behind
the menu; after the lobby (`1 LOCAL`, or the network's start) d_mstart sets up the match's level and first arena, which is
drawn at the first tick.

### 15.5 The seed

- Local play: the frame counter at the duel's entry (w_entry; it varies with how long the title ran).
- The network: the host's seed goes into NETCREATE's settings (now 3 bytes: the delay, the seed), written from d_seed
  right before NETCREATE (dlb_host), so a machine whose join failed after it took another host's seed advertises the
  seed its arenas now use (found by review: an entry-time copy would have desynced); the joiner takes it from NETJOIN's
  answer (settings[1, 2]) and both choose the same levels and rooms. **The level is not sent**: it follows
  from the seed and the match's number, so a rematch's level agrees too. The relay's NETREADY seed was not used: READY
  answers 0xFFFF while the room waits, and the match starts the moment the relay runs it (one more command to read it).
- The harness: its own seed (d_seed, kept while d_script is set) and d_afix (1: the fixed arena every round, the scripts
  without `# seed`).

### 15.6 Where it lives

| | Before (phase 4) | Now |
|---|---|---|
| Code holes (resident while a duel runs) | 3,481 of 3,771 B, 290 free | **3,451**, 320 free (phase 2's d_torches and d_entry's room setup moved into P_w2; added: d_arena 22 B, d_mstart 7, 7 variables, the joiner's seed 6, HOST's settings seed 6, d_reset's variables, d_round's calls of d_arena, the hash map's entry) |
| P_main (main RAM over the main loop) | 253 B | 256 (d_seed, d_afix: the harness writes them before d_boot) |
| **P_w2, the arenas' piece** | - | **654 B** (code ~448, tables 206): staged, copied by d_arena into W2's top (OVL_WF 0xAA00, 1,536 B: the fill overlay's window, used only by a level start's fill) at a match's and a round's start (after pend_flush); the level-start overlay is loaded below it (it ends at 0xA905: asserted) |
| Staged (PRS_DUEL1, RAM-disk page 6 0x16C0-) | 3,241 of 4,544 B | 3,862 (the staging area stays untouched during the duel: no chopper or spike in an arena) |
| Floppy (POP800.PR3) | 12 blocks | 14 (26 of the 40 reserved left) |
| Resident game bytes, launcher, PRES, overlay windows of the game | 0, unchanged | **0, unchanged** |

tools/duelpatch.py: P_w2 must lie in H_W2A (not a dropped hole: no checks of the game's code against it) and be staged
right after d_ptab's pieces (DSTAGE_W2); the call graph walks it (a jump from d_arena into W2 is P_w2, a call from P_w2
into W2 the level-start overlay's label) and the level overlay's alter_mods: no hole reached.

### 15.7 Speed

The room change is the full room draw of a new room: **51-85 frames (1.0-1.7 s) for the round's first tick** at every
RAM-disk size (arenas_dungeon / arenas_palace at 512 KB, 1 MB, 16 MB; level 12 room 16: 51, level 5 room 12: 85), right
after the 36-tick round end; copying P_w2 and the setup are well under a frame. A level change at a rematch adds a few
frames (82 for level 10 room 2, whose draw alone the op-count fit estimates at ~74). In play a room's ticks cost what
its torches cost (each ~0.2 frames): match.txt in level 1 room 3 5.50 / 5.22 / 4.90 frames a tick at 512 KB / 1 MB / 16
MB as before; the dungeon script's rooms (0-2 torches) 5.17 / 4.90 / 4.59; the palace script's (2-4 torches) 5.67 /
5.39 / 5.07.

### 15.8 duelsim and the tests

- duelsim: DuelSim(seed=None) the fixed arena (every phase 1-4 script and digest unchanged); DuelSim(seed=s) the random
  arenas: the entry's fixed arena (as the Z80's w_entry, the torches drawing on prandom in the same order), then
  match_start; next_round at every round's end, match_start after a rematch. Scripts: `# seed 0x..`; `# expect arenas
  12:1,12:16,...` (the rounds' level:room in order).
- tests/duel_scripts/arenas_dungeon.txt (seed 0xCA: level 12, the rematch level 10) and arenas_palace.txt (0x18: level 5,
  then 13): match.txt's moves, four rounds and a rematch, a new room every round, a level loaded in the duel.
- tests/duel_z80.py (the seed and d_afix poked; the hash's 69 bytes): all nine scripts 0 differing lines at 512 KB, 1 MB
  and 16 MB; the code log over all of them: no hole reached.
- tests/duel_net.py: arenas_dungeon.txt over the relay; A starts with the script's seed, B with another: B takes A's from
  the room, both traces equal duelsim's every tick; the failures as before; and a join that fails after it took the
  host's seed (the host gone before the start), then HOST on that machine: a third machine joins, takes that seed, and
  both play 40 ticks as duelsim, no DESYNC (without dlb_host's refresh: DESYNC, checked). The harness's relay now closes
  a TCP connection at its session's end, as a WebSocket closes (relay.py's TCP side leaves it open after a "leave",
  and the emulator's NET device would send its next room into a dead connection: a test setup matter).
- tests/duel_boot.py: from the floppy, the fixed arena behind the menu, then 1 LOCAL: the level and room duelsim chooses
  for the seed the duel took, loaded and drawn, the players at its start tiles.
- tests/duel_test.py: the nine scripts (determinism, results, arenas, digests).

### 15.9 Decisions for the user (defaults chosen)

1. Only the seed travels in the room's settings; the level follows from the seed and the match's number (the brief
   named both: the level would be redundant and could not cover the rematch's new level).
2. A rematch is a new match: a new level (and its rooms).
3. A round never gets the room of the round before; a drawn round, replayed, gets a new room as well.
4. The menu keeps level 1 room 3 behind it; the match's own arena is drawn at its first tick (one more full draw, ~1.5 s).
5. Local play's seed: the frame counter at Ctrl+D's duel entry.
6. The level's own rules are off (level_number 1) on every level.
