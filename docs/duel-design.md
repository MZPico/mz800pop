# The duel easter egg: analysis and design (2026-11-10)

Status: **design only, nothing built; the user's decisions in section 9, later iterations in section 10.** The duel is built after the remaining speed work and the AV fine-tuning (PLAN.md
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
| Arena | Level 1 room 3 (dungeon) or level 10 room 21 (palace): 8 plain floor tiles between pillars, walls above and below, no objects; the room's links are zeroed, so its edges are walls (section 6). |
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

Cheap follow-ups that make the reservation stick (not in this PR): `tools/mkgamedisk.py` asserts that
`DUEL_BLOCKS = 40` blocks stay free; launch.inc names `ACT_DUEL equ 0x20`. The loose-floor speed work is unaffected:
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
  scores); the normal game keeps SDLPoP's rule. (A patch site of ~10 B, in the sword-rules line of 1.3.)
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
| 1 | kidsim duel mode, the per-player block, the kid's sword rules for P2, rounds; scripted duels; check the shadow set's frames against seq 75 / 86 | 3-4 days | low |
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
