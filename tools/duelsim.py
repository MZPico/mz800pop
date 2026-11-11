#!/usr/bin/env python3
"""The duel's logic (docs/duel-design.md, phase 1; the rules as built: its section 11): the kid (player 1) against the
shadow (player 2) in one closed room, both playing the kid's frame (SDLPoP play_kid_frame) with the kid's sword rules,
two input bytes a tick, rounds of 3 hit points, best of 5. A subclass of tools/kidsim.py's KidSim: the game's logic
as it is, with the duel's rule sites in kidsim marked '(duel Dn)' (they act only when KidSim.duel is set, as here)
and the duel's own tick (DuelSim.step) in place of play_frame. kidsim is the duel's oracle: SDLPoP has no two-player
mode (design section 7); the Z80 duel (phase 2) must match these traces tick for tick.

The input byte (one per player per tick; the same byte locally and over the network, design 3 and 5): bits 0-4 are the
game's INPUT byte (src/m4/game.asm read_inputs: 0 left, 1 right, 2 up, 3 down, 4 the button), 5 quit, 6 rematch, 7 0.
Decoded as the game's get_controls decodes INPUT: right wins over left, down over up.

Script (tests/duel_scripts/*.txt): '# duel' first; then one line per tick 'x1 y1 s1  x2 y2 s2' (x -1 left 0 1 right,
y -1 up 0 1 down, s 1 = the button; the screen's directions, as the kid's scripts) with optional tokens '*N' (the line
N times), 'Q1' / 'Q2' (that player's quit bit), 'R1' / 'R2' (rematch); or 'b1 b2' as two input bytes in hex ('0x..').
Options: '# p2 frames shadow' (player 2's frames 150-189 from the guard's frame table and the shadow's images, as
SDLPoP's shadow; default: the kid's table, see DUEL_KID_FRAMES). Expectations (tests/duel_test.py): '# expect rounds
1,2,3' (the round results in order), '# expect score 3:1', '# expect match 1' (at the end), '# expect matches 1,0,3' (the match state's changes),
'# expect mirror other.txt', '# expect digest <hex>' (the trace's).

Trace per tick: the kid line (kidsim trace_line), the 'G' line (kidsim trace_guard_line: the shadow's record and the
fight globals, as m4_test's G snapshot), the 'D' line ('D tick in1 in2 rounds score1 score2 timer result match hash',
then player 1's and player 2's blocks, 9 bytes each, see BLOCK) and the 'N' line (sounds, the silent model).

usage: duelsim.py <script.txt> [trace_out.txt]      the trace's last lines and the result
       duelsim.py --frames                          the shadow image set against the kid's sword sequences"""
import hashlib, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kidsim as K
from kidsim import KidSim, Char, SEQ, X_BUMP, Y_LAND, FIRST_ONSCREEN_COLUMN, TILE_SIZEX, RIGHT, LEFT, HELD, RELEASED
from kidsim import CHARID_KID, CHARID_SHADOW, A_HURT, A_STAND, DIR_NONE
from popdata import Level

# ---- the arena and the rules (design sections 2.3, 6, 9; section 11 for the choices made here)
ARENA_LEVEL, ARENA_ROOM, ARENA_ROW = 1, 3, 1     # the dungeon: level 1 room 3, the middle row (8 floor tiles)
START = ((2, RIGHT), (7, LEFT))                  # (column, direction) of player 1 (the kid) and player 2 (the shadow)
ROUND_HP = 3                                     # hit points of both at a round's start (hitp and guardhp, max = curr)
WINS = 3                                         # rounds to win the match: best of 5 (draws are replayed: no limit)
ROUND_END_TICKS = 36                             # the round end: ticks from the deciding tick to the reset
DUEL_KID_FRAMES = True                           # player 2's frames 150-189 from the kid's table (False: SDLPoP's shadow)

# ---- the input byte
IN_LEFT, IN_RIGHT, IN_UP, IN_DOWN, IN_FIRE, IN_QUIT, IN_REMATCH = 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40
def encode(cx, cy, shift, quit=0, rematch=0):
    return ((IN_LEFT if cx < 0 else IN_RIGHT if cx > 0 else 0) | (IN_UP if cy < 0 else IN_DOWN if cy > 0 else 0) |
            (IN_FIRE if shift else 0) | (IN_QUIT if quit else 0) | (IN_REMATCH if rematch else 0))
def decode(b):
    """-> (control_x, control_y, shift) as game.asm get_controls decodes INPUT (right over left, down over up)"""
    cx = 1 if b & IN_RIGHT else -1 if b & IN_LEFT else 0
    cy = 1 if b & IN_DOWN else -1 if b & IN_UP else 0
    return cx, cy, 1 if b & IN_FIRE else 0

# ---- results
RES_NONE, RES_P1, RES_P2, RES_DRAW = 0, 1, 2, 3            # a round's result (the last one stays until the next)
MATCH_ON, MATCH_P1, MATCH_P2, MATCH_QUIT = 0, 1, 2, 3      # the match

# ---- the per-player block: the kid-only globals of SDLPoP's kid frame. Player 1's live in the globals (as in the game);
# player 2's are swapped in around its frame (DuelSim.swap_block). BLOCK: 9 bytes (design 2.2, hashed); COLL: the
# collision rows (kid.asm PREV_COLL_ROW, PREV_ROOMS..ABOVE_FLAGS: 1 + 80 bytes), the character's wall memory between
# its ticks (check_collisions compares where it was against where it is: without its own rows a player would bump on
# the other one's walls).
BLOCK = ('ctrl1', 'grab_timer', 'have_sword', 'offguard', 'holding_sword')
COLL = ('prev_collision_row', 'prev_coll_room', 'prev_coll_flags', 'curr_row_coll_room', 'curr_row_coll_flags',
        'below_row_coll_room', 'below_row_coll_flags', 'above_row_coll_room', 'above_row_coll_flags')

def fresh_block():
    b = dict(ctrl1=[RELEASED] * 5, grab_timer=0, have_sword=1, offguard=0, holding_sword=0, prev_collision_row=-1)
    for nm in COLL[1:]: b[nm] = [-1] * 10 if nm.endswith('room') else [0] * 10
    return b

def rec_bytes(c):
    """a record as the Z80 keeps it (guard.asm OF_*: frame x y dir col row action fall_x fall_y room repeat charid sword
    alive seq_lo seq_hi)"""
    v = [c.frame, c.x, c.y, c.direction, c.curr_col, c.curr_row, c.action, c.fall_x, c.fall_y, c.room, c.repeat,
         c.charid, c.sword, c.alive, c.curr_seq & 0xFF, (c.curr_seq >> 8) & 0xFF]
    return [x & 0xFF for x in v]

def hash16(data):
    """the duel's state hash (design 4.3): 16-bit, per byte: rotate left by one, add the byte"""
    h = 0
    for b in data: h = (((h << 1) | (h >> 15)) + b) & 0xFFFF
    return h


class DuelSim(KidSim):
    duel = True

    def __init__(self, kid_frames=DUEL_KID_FRAMES, arena=(ARENA_LEVEL, ARENA_ROOM)):
        KidSim.__init__(self, Level(arena[0]), sound='silent')
        self.duel_kid_frames = kid_frames
        if not kid_frames: self.guard_wh = self.image_sizes('shadow')     # chtab 5 = the shadow's images (level 12's)
        self.arena = arena[1]
        self.arena_setup()
        self.score = [0, 0]; self.rounds = 0; self.timer = 0; self.result = RES_NONE; self.match = MATCH_ON
        self.round_reset()
        self.tick = 0
        self.duel_line = None

    def arena_setup(self):
        """design 6: the room's four links zeroed (room 0 is a wall: its edges draw and collide as walls), no guards,
        no tile animations but the room's torches, no level texts; the level's tiles are not touched (a trap in the room
        would stay: 10.1). The torches flicker as in the game (the user's choice 2026-11-11): the room's entry torch
        step (anim_tile_modif: random first frames, trobs) and process_trobs every tick, drawing on prandom: lockstep
        state the logic never reads, not hashed"""
        L = self.level; room = self.arena
        L.raw = bytearray(L.raw); o = 1952 + (room - 1) * 4; L.raw[o:o + 4] = bytes(4)
        for i in range(24): L.guards_tile[i] = 30
        self.trobs = []; self.mobs = []
        self.need_level1_music = 0; self.erase_bottom_text(); self.is_show_time = 0
        self.drawn_room = self.next_room = room; self.exit_room_timer = 0
        self.anim_tile_modif()                            # (the torches: random first frames, animated)

    def round_reset(self):
        """a round's start: both at their start tiles, standing, swords sheathed, full hit points, fresh blocks"""
        recs = []
        for p, (col, d) in enumerate(START):
            c = Char(); c.room = self.arena; c.curr_col = col; c.curr_row = ARENA_ROW
            c.x = X_BUMP[col + FIRST_ONSCREEN_COLUMN] + TILE_SIZEX; c.y = Y_LAND[ARENA_ROW + 1]
            c.direction = d; c.alive = -1; c.charid = CHARID_KID if p == 0 else CHARID_SHADOW
            self.Char = c; self.seqtbl_offset_char(SEQ['stand']); self.play_seq()
            recs.append(c)
        self.Kid, self.Guard = recs[0].copy(), recs[1].copy()
        self.Char = self.Kid.copy(); self.Opp = self.Guard.copy()
        for k, v in fresh_block().items(): setattr(self, k, v)
        self.pblock = fresh_block()
        self.hitp_curr = self.hitp_max = self.guardhp_curr = self.guardhp_max = ROUND_HP
        self.hitp_delta = self.guardhp_delta = 0
        self.can_guard_see_kid = self.justblocked = self.guard_refrac = self.kid_sword_strike = 0
        self.guard_notice_timer = self.is_guard_notice = self.droppedout = 0
        self.is_screaming = 0; self.knock = 0
        self.timer = 0

    def swap_block(self):
        """player 2's block in (or out): exchanged with the globals around its frame"""
        for k in BLOCK + COLL:
            v = getattr(self, k); setattr(self, k, self.pblock[k]); self.pblock[k] = v

    # ---- one tick
    def step(self, in1, in2):
        """one tick with both players' input bytes; returns the kid line (self.guard_line, duel_line, sound_line too)"""
        self.guard_line = self.duel_line = self.sound_line = self.kid_line = None
        self.sound_tick()
        self.guardhp_delta = 0; self.hitp_delta = 0
        # (no timers, do_mobs, check_skel: the arena has none of it)
        self.process_trobs()                              # (the torches' flicker: prandom, no logic reads it)
        self.check_can_guard_see_kid()                    # (duel D11)
        self.char_frame(0, in1)
        self.kid_line = self.trace_line()
        self.tick += 1
        self.swap_block(); self.char_frame(1, in2); self.swap_block()
        self.check_sword_hurting(); self.check_sword_hurt()
        self.check_sword_vs_sword()
        self.do_delta_hp()
        # (no exit_room, check_the_end, check_guard_fallout: the room never changes; no show_time: no clock)
        self.guard_line = self.trace_guard_line()
        self.round_step(in1, in2)
        self.play_next_sound()                            # (draw_game_frame's sound queue: the 'N' line)
        self.duel_line = 'D %d %d %d %d %d %d %d %d %d %d %s %s' % (
            self.tick, in1, in2, self.rounds, self.score[0], self.score[1], self.timer, self.result, self.match,
            self.state_hash(), ' '.join(map(str, self.block_bytes(0))), ' '.join(map(str, self.block_bytes(1))))
        return self.kid_line

    def char_frame(self, p, inp):
        """SDLPoP play_kid_frame for player p (0: the kid's record, 1: the shadow's), with the duel's control"""
        if p == 0: self.loadkid_and_opp()
        else: self.loadshad_and_opp()
        self.load_fram_det_col()
        self.duel_control(inp)
        C = self.Char
        if C.room != 0:
            self.play_seq(); self.fall_accel(); self.fall_speed()
            self.load_frame_to_obj(); self.load_fram_det_col(); self.set_char_collision()
            self.bump_into_opponent()
            self.check_collisions(); self.check_bumped(); self.check_gate_push()
            self.check_action(); self.check_press(); self.check_spike_below(); self.check_spiked(); self.check_chomped_kid()
            self.check_knock()
        if p == 0: self.savekid()
        else: self.saveshad()

    def duel_control(self, inp):
        """SDLPoP control_kid and play_kid's death counter, the duel's way: the character's own hit points (duel D12:
        take_hp's rule, hitp for the kid, guardhp for the shadow), no restart key, no level keys; the death counter
        counts without waiting for a sound, no death music, no text (the round end is the duel's, round_step)"""
        C = self.Char
        hp = self.hitp_curr if C.charid == CHARID_KID else self.guardhp_curr
        if C.alive < 0 and hp == 0: C.alive = 0
        if self.grab_timer: self.grab_timer -= 1
        (self.control_forward, self.control_backward, self.control_up, self.control_down, self.control_shift2) = self.ctrl1
        cx, cy, shift = decode(inp)
        self.control_x, self.control_y, self.control_shift = cx, cy, (HELD if shift else RELEASED)
        self.read_user_control(); self.user_control()
        self.ctrl1 = [self.control_forward, self.control_backward, self.control_up, self.control_down, self.control_shift2]
        if C.alive >= 0 and self.is_dead() and C.alive < 100: C.alive += 1

    def check_sword_hurt(self):
        """(duel D13, the user's change 2026-11-11: a clash) both hurt in one tick (each one's strike reached the other):
        nobody is hurt, both react as an attacker whose strike was parried (check_hurting's own reaction: the sequence
        attack_was_parried, played at once), the kid first; SDLPoP cancels the kid's hurt and hurts the shadow, which
        would favour player 1. One hurt: hurt_by_sword as SDLPoP. No guard_refrac (the guard AI's)."""
        kid_hurt, shad_hurt = self.Kid.action == A_HURT, self.Guard.action == A_HURT
        if kid_hurt and shad_hurt:
            self.loadkid(); self.seqtbl_offset_char(SEQ['attack_was_parried']); self.play_seq(); self.savekid()
            self.loadshad(); self.seqtbl_offset_char(SEQ['attack_was_parried']); self.play_seq(); self.saveshad()
        elif kid_hurt: self.loadkid(); self.hurt_by_sword(); self.savekid()
        elif shad_hurt: self.loadshad(); self.hurt_by_sword(); self.saveshad()

    def round_step(self, in1, in2):
        """the rounds (after the tick's hit points are final): the first tick with a player at 0 hit points decides the
        round (both at 0: a draw, replayed, nobody scores); ROUND_END_TICKS later the next round starts, or the match
        ends when a player has WINS rounds. Quit (either player's bit) ends the match at once; rematch (either
        player's bit) after the match's end starts a new one."""
        if (in1 | in2) & IN_QUIT and self.match != MATCH_QUIT: self.match = MATCH_QUIT; return
        if self.match != MATCH_ON:
            if self.match != MATCH_QUIT and (in1 | in2) & IN_REMATCH:
                self.score = [0, 0]; self.rounds = 0; self.result = RES_NONE; self.match = MATCH_ON; self.round_reset()
            return
        if self.timer == 0:
            d1, d2 = self.hitp_curr == 0, self.guardhp_curr == 0
            if d1 or d2:
                self.result = RES_DRAW if d1 and d2 else RES_P2 if d1 else RES_P1
                self.rounds += 1
                if self.result != RES_DRAW: self.score[self.result - 1] += 1
                self.timer = ROUND_END_TICKS
        else:
            self.timer -= 1
            if self.timer == 0:
                if self.score[0] >= WINS: self.match = MATCH_P1
                elif self.score[1] >= WINS: self.match = MATCH_P2
                else: self.round_reset()

    # ---- the state the machines compare (design 4.3)
    def block_bytes(self, p):
        """player p's block, 9 bytes: ctrl1 (5: forward backward up down shift2), grab_timer, have_sword, offguard,
        holding_sword"""
        src = (lambda k: getattr(self, k)) if p == 0 else (lambda k: self.pblock[k])
        return [v & 0xFF for v in list(src('ctrl1')) + [src(k) for k in BLOCK[1:]]]
    def round_bytes(self):
        """6 bytes; rounds counts draws too (no limit), so it is kept modulo 256, as the Z80's byte"""
        return [self.rounds & 0xFF, self.score[0], self.score[1], self.timer, self.result, self.match]
    def state_bytes(self):
        """the hashed state, 68 bytes: the kid's and the shadow's records (16 each, the Z80's layout), hitp_curr,
        hitp_max, guardhp_curr, guardhp_max, can_guard_see_kid, justblocked, guard_refrac, kid_sword_strike,
        guard_notice_timer, is_guard_notice, droppedout, guard_skill (12), player 1's block, player 2's block (9 each),
        the round state (6: rounds, score 1, score 2, timer, result, match). Not hashed: Opp, CHAR_SAVE (scratch
        copies), the deltas (zeroed every tick), the collision rows, prandom's seed (unused by the duel's logic)."""
        g = [self.hitp_curr, self.hitp_max, self.guardhp_curr, self.guardhp_max, self.can_guard_see_kid,
             self.justblocked, self.guard_refrac, self.kid_sword_strike, self.guard_notice_timer, self.is_guard_notice,
             self.droppedout, self.guard_skill]
        return (rec_bytes(self.Kid) + rec_bytes(self.Guard) + [v & 0xFF for v in g] + self.block_bytes(0) +
                self.block_bytes(1) + self.round_bytes())
    def state_hash(self): return hash16(self.state_bytes())


# ---- scripts
def read_duel_script(path):
    """-> (inputs [(in1, in2)], options {'p2_frames': 'kid'|'shadow', 'expect': {key: value}})"""
    inputs = []; opts = {'p2_frames': 'kid', 'expect': {}}; duel = False
    for l in open(path):
        if l.startswith('#'):
            p = l[1:].split()
            if p[:1] == ['duel']: duel = True
            elif p[:2] == ['p2', 'frames']: opts['p2_frames'] = p[2]
            elif p[:1] == ['expect'] and len(p) >= 3: opts['expect'][p[1]] = ' '.join(p[2:])
            continue
        p = l.split('#')[0].split()
        if not p: continue
        n = 1; q = [0, 0]; r = [0, 0]; nums = []
        for t in p:
            if t.startswith('*'): n = int(t[1:])
            elif t in ('Q1', 'Q2'): q[int(t[1]) - 1] = 1
            elif t in ('R1', 'R2'): r[int(t[1]) - 1] = 1
            else: nums.append(int(t, 0))
        if len(nums) == 2 and p[0].startswith('0x'): b = tuple(nums)
        elif len(nums) == 6:
            b = (encode(*nums[0:3], quit=q[0], rematch=r[0]), encode(*nums[3:6], quit=q[1], rematch=r[1]))
        else: raise SystemExit('%s: bad line %r' % (path, l))
        inputs += [b] * n
    if not duel: raise SystemExit('%s: not a duel script (no "# duel" line)' % path)
    return inputs, opts

def run_duel(path, out=None):
    """the trace of a duel script (the kid, G, D, N lines a tick); stops at a quit. -> (lines, sim)"""
    inputs, opts = read_duel_script(path)
    sim = DuelSim(kid_frames=opts['p2_frames'] != 'shadow')
    lines = ['D 0 0 0 0 0 0 0 0 0 %d' % sim.state_hash()]      # (the state before the first tick)
    for in1, in2 in inputs:
        lines.append(sim.step(in1, in2))
        lines += [sim.guard_line, sim.duel_line, sim.sound_line]
        if sim.match == MATCH_QUIT: break
    if out: open(out, 'w').write('\n'.join(lines) + '\n')
    return lines, sim

def digest(lines):
    return hashlib.sha256(('\n'.join(lines) + '\n').encode()).hexdigest()[:16]

def round_results(lines):
    """the round results in order, from the D lines (a tick where 'rounds' grows)"""
    res = []; prev = 0
    for l in lines:
        if l.startswith('D '):
            f = l.split()
            if int(f[4]) > prev: res.append(int(f[8]))
            prev = int(f[4])
    return res


# ---- the shadow's image set against the kid's sword sequences (design 8, phase 1)
SWORD_SEQS = ('draw_sword', 'turn_draw_sword', 'forward_with_sword', 'back_with_sword', 'strike', 'strike_after_parry',
              'parry', 'parry_after_strike', 'attack_was_parried', 'turn_with_sword', 'pushed_back_with_sword',
              'bump_forward_with_sword', 'hit_by_sword', 'stabbed_to_death', 'dying', 'put_sword_away',
              'put_sword_away_fast', 'guard_forward_with_sword', 'guard_strike', 'en_garde')

def seq_frames(sim, sid):
    """the frames a sequence shows, in order, until it loops or ends"""
    tbl = sim.seqtbl; p = sim.seq_off[sid]; out = []; seen = set()
    while p not in seen:
        seen.add(p); cmd = tbl[p]; p += 1
        if cmd in (K.SEQ_DX, K.SEQ_DY, K.SEQ_ACTION, K.SEQ_SOUND, K.SEQ_GET_ITEM): p += 1
        elif cmd in (K.SEQ_SET_FALL, K.SEQ_JMP_IF_FEATHER): p += 2
        elif cmd == K.SEQ_JMP: p = tbl[p] | (tbl[p + 1] << 8)
        elif cmd in (K.SEQ_FLIP, K.SEQ_UP, K.SEQ_DOWN, K.SEQ_KNOCK_UP, K.SEQ_KNOCK_DOWN, K.SEQ_END_LEVEL, K.SEQ_DIE): pass
        else: out.append(cmd)
    return out

def frame_check():
    """per sword sequence, the frames 150-189 player 2 shows, as SDLPoP's shadow draws them (frame_tbl_guard: the
    image in chtab 5, the shadow's set) and whether the image exists there; '*': the guard table's geometry (dx, dy,
    flags) differs from the kid's for that frame"""
    sim = KidSim(Level(1)); shadow = KidSim.image_sizes('shadow'); kid = KidSim.image_sizes('kid')
    missing = set(); differ = set(); lines = []
    for nm in SWORD_SEQS:
        row = []
        for f in seq_frames(sim, SEQ[nm]):
            if not 150 <= f < 190: row.append('%d' % f); continue
            g = sim.frames_guard[f - 149]; chtab = 2 + (g[1] >> 6)
            have = g[0] in (shadow if chtab == 5 else kid)
            if not have: missing.add(f)
            same = sim.frames[f][2:] == g[2:]
            if not same: differ.add(f)
            row.append('%d:%s%d%s' % (f, 's' if chtab == 5 else 'k', g[0] + 1, '' if have else '!') + ('' if same else '*'))
        lines.append('%-24s %s' % (nm, ' '.join(row)))
    lines.append('shadow set: %d images; missing (frame: image): %s' % (len(shadow), ', '.join(
        '%d: %d' % (f, sim.frames_guard[f - 149][0] + 1) for f in sorted(missing)) or 'none'))
    lines.append('frames whose guard-table geometry differs from the kid table: %s' % ' '.join(map(str, sorted(differ))))
    return lines, missing, differ


if __name__ == '__main__':
    if sys.argv[1:2] == ['--frames']:
        print('\n'.join(frame_check()[0])); sys.exit(0)
    lines, sim = run_duel(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print('\n'.join(lines[-4:]))
    print('ticks %d, rounds %s, score %d:%d, match %d, digest %s' % (sim.tick, round_results(lines), sim.score[0],
                                                                      sim.score[1], sim.match, digest(lines)))
