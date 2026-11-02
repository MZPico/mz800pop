#!/usr/bin/env python3
"""Prince (kid) and guard simulator: a Python port of the SDLPoP game logic (seg000/002/003/004/005/006/007) that
the Z80 game code is written from. Ticks the kid through scripted controls in SDLPoP's play_frame order and yields
the same state lines as the oracle hooks in external/SDLPoP (pop800_trace.c): per tick the kid line (tick frame x y
dir row col action fall_x fall_y room curr_seq alive hitp_curr hitp_max trobs mobs room_checksum), with guards on the
guard line ('G ...', see trace_guard_line) and with '# state' the level-event line ('S ...', see trace_state_line).
Covers traps (spikes, loose floors, chompers), buttons and gates, the level door, potions (heal, life, hurt, open,
feather fall, upside down), hit points and death, guards (entering/leaving/following through rooms, the guard AI,
sword fighting, hurting, falling, dying), the level events: level 1/7/13 entries, the level 3 checkpoint and skeleton,
the level 4 mirror and its shadow, the level 5/6/12 shadows (level 12: fight, uniting, hidden floors), the level 6
and 12 exits, level 13's falling floors and Jaffar, the level 14 end; the time limit and its messages, flashes, level
restarts (Ctrl+A). Sounds: SDLPoP's request side (play_sound with its priorities, play_next_sound, stop_sounds) at
every call site the logic reaches, traced as the 'N' line (sound_line: queued started playing stops, per
draw_game_frame), with three models of whether a sound plays (KidSim(sound=...): 'silent' (default, every test),
'ticks', 'hybrid'; see play_sound). The waits on sound (M7 step 5: the feather fall, the level 1 crouch, the death
timer, the level end) ask the model: in the silent mode (every harness test) they keep the rules they had before it
(the death timer never waits, the feather fall music lasts until the 225-tick cap or a stop_sounds, the level's end
music (stairs on levels 1-12) never ends, so the level does not change; level 13's stairs have none: the level
changes at once; no level 1 crouch: the oracle hook skips it).

usage: kidsim.py <level> <script.txt> [trace_out.txt]   (script: one "x y shift [keys]" line per tick)"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from popdata import Level, T
import build_assets as BA
ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'build', 'assets')

# ---- constants (SDLPoP types.h)
RIGHT, LEFT = 0, -1
A_STAND, A_RUN_JUMP, A_HANG_CLIMB, A_MIDAIR, A_FREEFALL, A_BUMPED, A_HANG_STRAIGHT, A_TURN = 0, 1, 2, 3, 4, 5, 6, 7
HELD, RELEASED, IGNORE = -1, 0, 1
X_FORWARD, X_BACKWARD = -1, 1          # control_x inside control()
Y_UP, Y_DOWN = -1, 1
FRAME_WEIGHT_X, FRAME_THIN, FRAME_NEEDS_FLOOR, FRAME_ODD = 0x1F, 0x20, 0x40, 0x80
SEQ_DX, SEQ_DY, SEQ_FLIP, SEQ_JMP_IF_FEATHER, SEQ_JMP, SEQ_UP, SEQ_DOWN, SEQ_ACTION = 0xFB, 0xFA, 0xFE, 0xF7, 0xFF, 0xFD, 0xFC, 0xF9
SEQ_SET_FALL, SEQ_KNOCK_UP, SEQ_KNOCK_DOWN, SEQ_SOUND, SEQ_END_LEVEL, SEQ_GET_ITEM, SEQ_DIE = 0xF8, 0xF5, 0xF4, 0xF2, 0xF1, 0xF3, 0xF6
EDGE_CLOSER, EDGE_WALL, EDGE_FLOOR = 0, 1, 2
TILE_SIZEX, TILE_MIDX, TILE_RIGHTX, SCREENSPACE_X = 14, 7, 13, 58
FIRST_ONSCREEN_COLUMN = 5
X_BUMP = [-12, 2, 16, 30, 44, 58, 72, 86, 100, 114, 128, 142, 156, 170, 184, 198, 212, 226, 240, 254]
Y_LAND = [-8, 55, 118, 181, 244]
TBL_LINE = [0, 10, 20]
WALL_DIST_FROM_LEFT = [0, 10, 0, -1, 0, 0]
WALL_DIST_FROM_RIGHT = [0, 0, 10, 13, 0, 0]
FALLING_SPEED_MAX, FALLING_SPEED_ACCEL = 33, 3
FALLING_SPEED_MAX_FEATHER, FALLING_SPEED_ACCEL_FEATHER = 4, 1
FEATHER_MAX = 225                  # feather fall ends after 225 ticks (or when the feather music stops)
# the level 5 shadow's moves (custom shad_drink_move: (demo_time, move); moves 0 nothing 1 forward 2 backward 3 up
# 4 down 5 up+forward 6 shift 7 release shift, -1/-2 keep the controls)
SHAD_DRINK_MOVE = [(0x00, 0), (0x01, 1), (0x0E, 0), (0x12, 6), (0x1D, 7), (0x2D, 2), (0x31, 1), (0xFF, -2)]
COLOR_GREEN, COLOR_RED, COLOR_BRIGHTYELLOW, COLOR_BRIGHTWHITE = 2, 4, 14, 15     # flash colours
# sequence ids
Y_SOMETHING = [-1, 62, 125, 188, 25]
Y_LOOSE_LAND = [2, 65, 128, 191, 254]
LOOSE_SOUND = [0, 1, 1, 1, 0, 1, 0, 0, 1, 0, 0, 0]
GATE_CLOSE_SPEEDS = [0, 0, 0, 20, 40, 60, 80, 100, 120]
DOOR_DELTA = [-1, 4, 4]
LEVELDOOR_CLOSE_SPEEDS = [0, 5, 17, 99, 0]
LOOSE_FLOOR_DELAY = 11
SEQ = dict(start_run=1, stand=2, standing_jump=3, run_jump=4, turn=5, run_turn=6, fall=7, jump_up_and_grab_straight=8,
           grab_while_jumping=9, climb_up=10, release_ledge_and_land=11, stop_run=13, jump_up_into_ceiling=14,
           grab_ledge_midair=15, jump_up_and_grab=16, soft_land=17, fall_after_standing_jump=18, fall2=19,
           medium_land=20, fall_after_running_jump=21, crushed=22, release_ledge_and_fall=23,
           jump_up_and_grab_forward=24, hang_against_wall=25, crouch_while_running=26, jump_up_with_nothing_above=28,
           safe_step_11=39, start_run_after_turn=43, step_on_edge=44, bumpfall=45, hardbump=46, bump=47,
           stand_up_from_crouch=49, crouch=50, climb_down=68, dying=71, climb_up_to_closed_gate=73, crouch_hop=79,
           start_fall_in_front_of_wall=104, spiked=51, loose_floor_fell_on_kid=52, go_up_on_level_door=70, drink=78, get_sword=91,
           chomped=54, draw_sword=55, guard_forward_with_sword=56, back_with_sword=57, guard_strike=58, turn_with_sword=60,
           parry_after_strike=61, parry=62, guard_active_after_fall=63, pushed_back_with_sword=64, bump_forward_with_sword=65,
           strike_after_parry=66, attack_was_parried=69, hit_by_sword=74, strike=75, guard_stand_inactive=77,
           stand_flipped=80, kid_pushed_off_ledge=81, guard_pushed_off_ledge=82, guard_fall=83, stabbed_to_death=85,
           forward_with_sword=86, guard_become_inactive=87, skel_wake_up=88, turn_draw_sword=89, en_garde=90,
           put_sword_away=92, put_sword_away_fast=93, mouse_forward=105, mouse_stand_up_and_go=107, run=84)
# ---- guards and sword fighting (SDLPoP types.h / data.h custom defaults)
DIR_NONE = 0x56                                   # dir_56_none: no guard
CHARID_KID, CHARID_SHADOW, CHARID_GUARD, CHARID_SKELETON, CHARID_MOUSE = 0, 1, 2, 4, 24
A_HURT = 99                                       # actions_99_hurt
SWORD_SHEATHED, SWORD_DRAWN = 0, 2
SND_SILENT, SND_FOOTSTEP, SND_BUMP, SND_DRINK, SND_LEVEL = 0, 1, 2, 3, 4   # the sequence table's sound ids
# ---- sounds (SDLPoP types.h sound ids, seg000.c sound_prio_table, data.h sound_interruptible). The oracle's SDLPoP is
# built with FIX_SOUND_PRIORITIES (config.h: a compile-time define, not one of the runtime fixes), which restores the
# PoP 1.3 values: sword_vs_sword 0x0D, spiked 0x15, spikes interruptible. Lower value = higher priority.
SOUND_PRIO = [0x14, 0x1E, 0x23, 0x66, 0x32, 0x37, 0x30, 0x30, 0x4B, 0x50, 0x0D, 0x12, 0x0C, 0x0B, 0x69, 0x6E, 0x73,
              0x78, 0x7D, 0x82, 0x91, 0x96, 0x9B, 0xA0, 0x01, 0x01, 0x01, 0x01, 0x01, 0x13, 0x01, 0x01, 0x01, 0x01,
              0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x01, 0x01, 0x01, 0x01, 0x87, 0x8C, 0x0F, 0x10, 0x15, 0x16, 0x01,
              0x00, 0x01, 0x01, 0x01, 0x01, 0x01]
SOUND_INTERRUPTIBLE = [0, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 1, 0, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 1, 0, 0,
                       0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0]
SOUND_MISSING = (31, 34, 38, 42)      # no digitized/MIDI resource: play_sound ignores them (sound_pointers NULL)
# Lengths in seconds of the sounds SDLPoP plays (sfDigi + sfMidi): DIGISND1-3 (PoP 1.0 wave header: rate, count) and the
# MIDISND1/2 tunes (tempo map, to the last event); 0 = none. The 'ticks' model's lengths come from these.
# (M7 step 5: 35, 36, 53, 54 corrected to the MIDI lengths as SDLPoP plays them, tools/midi2psg.py length(): 53 / 54
# with SDLPoP's tempo modifier; the arranged PSG streams last exactly these lengths)
SOUND_SECONDS = [0.150, 1.093, 0.564, 0.106, 0.097, 0.123, 0.503, 0.075, 0.147, 0.249, 0.319, 0.107, 0.116, 0.345,
                 0.689, 1.613, 0.431, 0.383, 0.626, 0.254, 0.122, 0.095, 0.106, 0.121, 3.600, 2.471, 13.995, 12.000,
                 7.200, 5.294, 3.542, 0, 7.250, 2.344, 0, 10.286, 14.529, 4.125, 0, 18.667, 6.857, 12.750, 0, 3.833,
                 0.243, 0.385, 0.419, 0.465, 0.164, 0.400, 14.500, 0.442, 28.887, 16.747, 25.023, 15.750, 124.700]
# The ticks model's lengths: ceil(seconds x the tick rate), except the feather fall music (39, 18.6666 s = 224.0 ticks
# at 12/s), which lasts at least the feather fall's 225-tick cap: in SDLPoP's real-time runs it still plays when the
# cap ends the fall (every feather oracle script ends at the cap), decided in M7 step 5 (docs/m7-design.md 14).
SOUND_TICKS_MIN = {39: 225}
SOUND_MODES = ('silent', 'ticks', 'hybrid')
LIVE_WAITS = ('death', 'level_end')   # the hybrid mode's live waits (docs/m7-design.md section 9, D4); the rest: ticks
                                      # (the feather fall 'feather', the level 1 crouch 'crouch', play_next_sound)
SEQ_BASE = 0x196E          # kidsim curr_seq = SDLPoP curr_seq - SEQ_BASE (level guards_seq_lo/hi hold SDLPoP's value)
NUM_GUARD_SKILLS = 12
STRIKEPROB    = [61, 100, 61, 61, 61, 40, 100, 220, 0, 48, 32, 48]
RESTRIKEPROB  = [0, 0, 0, 5, 5, 175, 16, 8, 0, 255, 255, 150]
BLOCKPROB     = [0, 150, 150, 200, 200, 255, 200, 250, 0, 255, 255, 255]
IMPBLOCKPROB  = [0, 61, 61, 100, 100, 145, 100, 250, 0, 145, 255, 175]
ADVPROB       = [255, 200, 200, 200, 255, 255, 200, 0, 0, 255, 100, 100]
REFRACTIMER   = [16, 16, 16, 16, 8, 8, 8, 8, 0, 8, 0, 0]
EXTRASTRENGTH = [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0]
TBL_GUARD_TYPE = [0, 0, 0, 2, 0, 0, 1, 0, 0, 0, 0, 0, 4, 3, -1, -1]   # 0 guard, 1 fat, 2 skeleton, 3 vizier, 4 shadow
TBL_GUARD_HP = [4, 3, 3, 3, 3, 4, 5, 4, 4, 5, 5, 5, 4, 6, 0, 0]
GUARD_IMAGES = ['guard', 'fat', 'skel', 'vizier', 'shadow']          # build/assets/<name>.json per guard type (chtab 5)
HAVE_SWORD_FROM_LEVEL = 2
INIT_SHAD_6 = (0x0F, 0x51, 0x76, 0, 0, 1, 0)       # frame x y direction curr_col curr_row action
INIT_SHAD_5 = (0x0F, 0x37, 0x37, 0, -1, 0, 0)
INIT_SHAD_12 = (0x0F, 0x51, 0xE8, 0, 0, 0, 0)
# The Guard SDLPoP has before the first guard enters: what the level's intro cutscene (run by 'prince megahit N')
# left in it (frame x y curr_seq; the rest is zero, charid 2, no direction). Only visible in the guard trace.
GUARD_LEFTOVER = {2: (11, 120, 166, 2088), 4: (19, 92, 162, 2127)}

def s8(v):
    v &= 255
    return v - 256 if v > 127 else v

class Char:
    __slots__ = ('frame', 'x', 'y', 'direction', 'curr_col', 'curr_row', 'action', 'fall_x', 'fall_y', 'room', 'repeat', 'charid', 'sword', 'alive', 'curr_seq')
    def __init__(self):
        for k in self.__slots__: setattr(self, k, 0)
    def copy(self):
        c = Char()
        for k in self.__slots__: setattr(c, k, getattr(self, k))
        return c

# the key codes of a script's 4th field (field = Ctrl+A | code << 3; src/m4/keys.asm, SDLPoP hook pop800_key_code)
KEY_SPACE, KEY_SHIFT_L, KEY_ENTER, KEY_CTRL_R, KEY_CTRL_S, KEY_CTRL_V, KEY_PAUSE = range(1, 8)
KEY_C_KILL, KEY_C_REVIVE, KEY_C_PLUS, KEY_C_MINUS, KEY_C_LIFE, KEY_C_HEAL, KEY_C_FEATHER, KEY_C_FLIP = range(8, 16)   # cheats
KEY_C_VIEW_L, KEY_C_VIEW_R, KEY_C_VIEW_U, KEY_C_VIEW_D, KEY_C_BACK, KEY_C_BLIND, KEY_C_TIMER = range(16, 23)
VERSION_TEXT = 'PRINCE OF PERSIA V1.0'

class KidSim:
    def __init__(self, level, notraps=False, seed=12345, patches=(), guards=False, place=(), sword=False, time=None,
                 multi_level=False, trace_state=False, start=None, sound='silent', level1_music=False):
        self.guards = guards              # False: no guards anywhere (POP800_NOGUARDS, applied at the first control tick)
        self.patches = list(patches)      # (room, pos, tile, modifier) applied at the first control tick (POP800_PATCH)
        if notraps:   # first cut / test mode: traps, buttons, potions and loose floors are plain floor (POP800_NOTRAPS)
            for i in range(24 * 30):
                if level.fg[i] & 0x1F in (T.spike, T.closer, T.potion, T.loose, T.opener, T.chomper): level.fg[i] = T.floor
        self.seqtbl = open(os.path.join(ASSETS, 'seqtbl_z80.bin'), 'rb').read()
        self.seq_off = [int(l.split()[1]) for l in open(os.path.join(ASSETS, 'seqtbl_offsets.txt'))]
        ft = BA.frame_tables()
        self.frames = ft['kid']; self.frames_guard = ft['guard']; self.frames_cuts = ft['cuts']   # (image, sword, dx, dy, flags)
        self.img_wh = self.image_sizes('kid')                                  # chtab 2
        self.Kid = Char(); self.Char = Char(); self.Opp = Char()
        self.Guard = Char(); self.Guard.curr_seq = -SEQ_BASE
        if level.number in GUARD_LEFTOVER:        # (the level's intro cutscene ran before the first level only)
            G = self.Guard; G.frame, G.x, G.y, G.curr_seq = GUARD_LEFTOVER[level.number]
        self.guardhp_curr = self.guardhp_max = self.guardhp_delta = 0
        self.guard_skill = 0; self.curr_guard_color = 0
        self.can_guard_see_kid = 0; self.holding_sword = 0; self.justblocked = 0; self.guard_refrac = 0
        self.kid_sword_strike = 0; self.guard_notice_timer = 0; self.is_guard_notice = 0; self.offguard = 0
        self.droppedout = 0; self.united_with_shadow = 0; self.roomleave_result = 0
        self.guard_line = None; self.state_line = None; self.end_line = None
        # controls
        self.control_x = self.control_y = self.control_shift = 0
        self.control_forward = self.control_backward = self.control_up = self.control_down = self.control_shift2 = 0
        self.ctrl1 = [0, 0, 0, 0, 0]
        self.grab_timer = 0; self.have_sword = 0; self.is_feather_fall = 0; self.knock = 0
        self.prev_collision_row = -1
        self.prev_coll_room = [-1] * 10; self.prev_coll_flags = [0] * 10
        self.gate_pushes = 0
        self.curr_row_coll_room = [-1] * 10; self.curr_row_coll_flags = [0] * 10
        self.below_row_coll_room = [-1] * 10; self.below_row_coll_flags = [0] * 10
        self.above_row_coll_room = [-1] * 10; self.above_row_coll_flags = [0] * 10
        self.exit_room_timer = 0; self.next_room = 0
        self.drawn_room = 0
        self.tick = 0
        self.seed = self.seed0 = seed; self.trobs = []; self.mobs = []
        self.hitp_curr = self.hitp_max = 3; self.hitp_delta = 0
        self.leveldoor_open = 0; self.pickup_obj_type = 0; self.last_loose_sound = 0
        self.level_done = False; self.want_restart = False
        self.curr_tile = 0; self.curr_modifier = 0
        self.sword_opt = sword; self.place = list(place)
        # level events (seg000/002/003): SDLPoP init_game
        self.text_time_remaining = self.text_time_total = 0; self.is_show_time = 0
        self.checkpoint = 0; self.upside_down = 0; self.seamless = 0
        self.rem_min, self.rem_tick = time if time else (60, 719)     # (POP800_TIME: the time left at the start)
        self.hitp_beg_lev = 3
        self.flash_color = self.flash_time = 0
        self.jumped_through_mirror = 0; self.demo_time = 0; self.demo_index = 0; self.shadow_initialized = 0
        self.feather_music = 0            # the feather fall music is playing (sound model: see timers)
        self.cheats = False; self.sound_on = True; self.key_title = False
        self.is_restart_level = 0; self.game_over = None; self.bottom_text = ''; self.distance_mirror = 0
        self.multi_level = multi_level; self.level_switch = False; self.trace_state = trace_state
        self.next_level = level.number    # (load_lev_spr: current_level = next_level = level)
        self.start_opt = start            # (POP800_START: the first level start only)
        # the sound model (play_sound / play_next_sound / stop_sounds / check_sound_playing, see sound_playing)
        assert sound in SOUND_MODES, sound
        self.sound_mode = sound
        self.next_sound = -1; self.current_sound = 0; self.snd_left = 0; self.snd_stops = 0; self.sound_line = None
        self.snd_interruptible = list(SOUND_INTERRUPTIBLE)   # (animate_leveldoor changes the level door's entry)
        self.live_playing = None          # hybrid: a callable for the live waits (default: the ticks model)
        self.end_music = 0                # the level's end music was asked for (silent: it never ends, see step)
        self.end_over = 0                 # hybrid: the ticks model's level end wait is over, the live one is not: no clock
        # SDLPoP init_game: need_level1_music = (level == 1): the level 1 start crouches until its music (25) ends. The
        # oracle hook skips it unless POP800_LEVEL1_MUSIC (script option '# level1 music'; the release always has it)
        self.need_level1_music = 1 if (level1_music and level.number == 1) else 0
        self.is_screaming = 0
        self.play_level(level)
        self.snd_stops = 0                # (the 'N' line counts stop_sounds from the first level start, as the hook)

    @staticmethod
    def image_sizes(name):
        imgs = json.load(open(os.path.join(ASSETS, name + '.json')))['images']
        return {int(k) - 1: (v['w'], v['h']) for k, v in imgs.items()}   # image index -> (w, h)

    def play_level(self, level):
        """SDLPoP play_level (one pass of its loop): the level loaded fresh, the kid at the start (or the checkpoint)."""
        self.level = level
        for nm in ('guards_tile', 'guards_dir', 'guards_x', 'guards_seq_lo', 'guards_skill', 'guards_seq_hi', 'guards_color'):
            setattr(level, nm, bytearray(getattr(level, nm)))   # live per-room guard state (SDLPoP level.guards_*)
        gt = TBL_GUARD_TYPE[level.number] if 0 <= level.number < 16 else -1
        self.guard_wh = self.image_sizes(GUARD_IMAGES[gt]) if gt >= 0 else {}  # chtab 5 (the level's guard graphics)
        self.dl1 = bytearray(level.raw[1440:1696]); self.dl2 = bytearray(level.raw[1696:1952])
        level.dl2 = self.dl2            # (shared: the renderer draws pressed buttons from the live timers)
        self.pos_guards()
        # clear_coll_rooms, clear_saved_ctrl
        self.prev_coll_room = [-1] * 10; self.curr_row_coll_room = [-1] * 10
        self.below_row_coll_room = [-1] * 10; self.above_row_coll_room = [-1] * 10
        self.prev_coll_flags = [0] * 10; self.curr_row_coll_flags = [0] * 10
        self.below_row_coll_flags = [0] * 10; self.above_row_coll_flags = [0] * 10
        self.prev_collision_row = -1
        self.ctrl1 = [0, 0, 0, 0, 0]
        self.drawn_room = 0; self.mobs = []; self.trobs = []; self.next_sound = -1
        self.holding_sword = 0; self.grab_timer = 0; self.can_guard_see_kid = 0; self.united_with_shadow = 0
        self.flash_time = 0; self.leveldoor_open = 0; self.demo_index = 0; self.demo_time = 0
        self.guardhp_curr = 0; self.hitp_delta = 0
        self.Guard.charid = CHARID_GUARD; self.Guard.direction = DIR_NONE
        if self.start_opt:                # pop800_startpos (oracle hook): a chosen start position
            level.start_room, level.start_pos, level.start_dir = self.start_opt[0], self.start_opt[1], self.start_opt[2] & 0xFF
            self.start_opt = None
        self.do_startpos()
        self.have_sword = 1 if level.number == 0 or level.number >= HAVE_SWORD_FROM_LEVEL else 0
        self.find_start_level_door()
        self.stop_sounds()              # (after waiting until no sound plays)
        self.end_over = 0
        self.draw_level_first()

    def draw_level_first(self):
        # pop800_level_start (oracle hook, start of draw_level_first): the seed, the sword, placed guards
        self.seed = self.seed0
        if self.sword_opt: self.have_sword = 1
        for (r, t, d, sk, c) in self.place:
            L = self.level
            L.guards_tile[r - 1] = t; L.guards_dir[r - 1] = d & 0xFF; L.guards_skill[r - 1] = sk
            L.guards_color[r - 1] = c; L.guards_seq_lo[r - 1] = 0; L.guards_seq_hi[r - 1] = 0
            L.guards_x[r - 1] = X_BUMP[(t % 10) + FIRST_ONSCREEN_COLUMN] + TILE_SIZEX
        self.next_room = self.Kid.room
        self.check_the_end()
        self.show_level()
        self.check_mirror()             # (redraw_screen -> draw_people)
        self.exit_room_timer = 2

    def clone(self):
        """Cheap copy for searches: shares the read-only tables, copies the mutable state."""
        import copy as _c
        n = _c.copy(self)
        n.level = _c.copy(self.level); n.level.fg = bytearray(self.level.fg); n.level.bg = bytearray(self.level.bg)
        n.Kid = self.Kid.copy(); n.Char = self.Char.copy(); n.Guard = self.Guard.copy(); n.Opp = self.Opp.copy()
        for nm in ('guards_tile', 'guards_dir', 'guards_x', 'guards_seq_lo', 'guards_skill', 'guards_seq_hi', 'guards_color'):
            setattr(n.level, nm, bytearray(getattr(self.level, nm)))
        n.trobs = [list(t) for t in self.trobs]; n.mobs = [dict(m) for m in self.mobs]
        n.dl2 = bytearray(self.dl2); n.level.dl2 = n.dl2; n.ctrl1 = list(self.ctrl1)
        for nm in ('prev_coll_room', 'prev_coll_flags', 'curr_row_coll_room', 'curr_row_coll_flags', 'below_row_coll_room',
                   'below_row_coll_flags', 'above_row_coll_room', 'above_row_coll_flags'):
            setattr(n, nm, list(getattr(self, nm)))
        return n
    # ---- random (DOS LCG, shared with the room renderer's wall patterns)
    def prandom(self, mx):
        self.seed = (self.seed * 214013 + 2531011) & 0xFFFFFFFF
        return (self.seed >> 16) % (mx + 1)
    # ---- level access (fg/bg are the live tile/modifier arrays; room 0 = outside)
    def tiles(self, room): return (room - 1) * 30
    def tile_at(self, room, pos): return self.level.fg[(room - 1) * 30 + pos] & 0x1F
    def mod_at(self, room, pos): return self.level.bg[(room - 1) * 30 + pos]
    def set_tile(self, room, pos, t): self.level.fg[(room - 1) * 30 + pos] = t
    def set_mod(self, room, pos, m): self.level.bg[(room - 1) * 30 + pos] = m & 0xFF
    def get_curr_tile(self, pos):
        """SDLPoP get_curr_tile for the room selected by get_room_address (self.curr_room)"""
        self.curr_modifier = self.mod_at(self.curr_room, pos); self.curr_tile = self.tile_at(self.curr_room, pos)
        return self.curr_tile
    def links(self, room):
        o = 1952 + (room - 1) * 4; r = self.level.raw
        return r[o], r[o + 1], r[o + 2], r[o + 3]       # left, right, up, down
    def get_tile(self, room, col, row):
        self.curr_room = room; self.tile_col = col; self.tile_row = row
        # find_room_of_tile (with FIX_CORNER_GRAB order: row first)
        while True:
            if self.tile_row < 0:
                self.tile_row += 3
                if self.curr_room: self.curr_room = self.links(self.curr_room)[2]
                continue
            if self.tile_col < 0:
                self.tile_col += 10
                if self.curr_room: self.curr_room = self.links(self.curr_room)[0]
                continue
            if self.tile_col >= 10:
                self.tile_col -= 10
                if self.curr_room: self.curr_room = self.links(self.curr_room)[1]
                continue
            if self.tile_row >= 3:
                self.tile_row -= 3
                if self.curr_room: self.curr_room = self.links(self.curr_room)[3]
                continue
            break
        if self.curr_room > 0:
            self.curr_tilepos = TBL_LINE[self.tile_row] + self.tile_col
            self.curr_tile2 = self.level.fg[(self.curr_room - 1) * 30 + self.curr_tilepos] & 0x1F
        else:
            self.curr_tilepos = 0
            self.curr_tile2 = T.wall
        return self.curr_tile2
    def modif(self):
        if self.curr_room > 0: return self.level.bg[(self.curr_room - 1) * 30 + self.curr_tilepos]
        return 0
    @staticmethod
    def tile_is_floor(t):
        return t not in (T.empty, T.bigpillar_top, T.doortop, T.wall, T.lattice_down, T.lattice_small, T.lattice_left, T.lattice_right)
    @staticmethod
    def wall_type(t):
        if t in (T.gate, T.doortop_with_floor, T.doortop): return 1
        if t == T.mirror: return 2
        if t == T.chomper: return 3
        if t == T.wall: return 4
        return 0

    # ---- frame / position helpers
    def load_frame(self):
        C = self.Char; f = C.frame; add_frame = 0
        if C.charid in (CHARID_KID, CHARID_MOUSE): tbl, i = self.frames, f
        elif C.charid in (CHARID_GUARD, CHARID_SKELETON):
            if 102 <= f < 107: add_frame = 70                 # (guard falling frames)
            tbl, i = self.frames_guard, f + add_frame - 149
        elif C.charid == CHARID_SHADOW:
            if f < 150 or f >= 190: tbl, i = self.frames, f
            else: tbl, i = self.frames_guard, f - 149
        else: tbl, i = self.frames_cuts, f
        self.cur_frame = tbl[i] if 0 <= i < len(tbl) else (255, 0, 0, 0, 0)
    def dx_weight(self):
        img, sw, dx, dy, flags = self.cur_frame
        return self.char_dx_forward(dx - (flags & FRAME_WEIGHT_X))
    def char_dx_forward(self, d):
        if self.Char.direction < RIGHT: d = -d
        return (d + self.Char.x) & 0xFF         # Char.x is a byte
    def back_delta_x(self, d):
        return d if self.Char.direction < RIGHT else -d
    def get_tile_div_mod(self, xpos):
        x = xpos - SCREENSPACE_X
        xh, xl = divmod(x, TILE_SIZEX)           # Python floors
        self.obj_xl = xl
        return xh
    def get_tile_div_mod_m7(self, xpos): return self.get_tile_div_mod(xpos - 7)
    def determine_col(self): self.Char.curr_col = self.get_tile_div_mod_m7(self.dx_weight())
    def load_fram_det_col(self): self.load_frame(); self.determine_col()
    @staticmethod
    def y_to_row_mod4(y): return (y + 60) // 63 % 4 - 1
    def distance_to_edge(self, xpos):
        self.get_tile_div_mod_m7(xpos); d = self.obj_xl
        if self.Char.direction == RIGHT: d = TILE_RIGHTX - d
        return d
    def distance_to_edge_weight(self): return self.distance_to_edge(self.dx_weight())
    def get_tile_at_char(self): return self.get_tile(self.Char.room, self.Char.curr_col, self.Char.curr_row)
    def dir_front(self): return 1 if self.Char.direction == RIGHT else -1
    def get_tile_infrontof_char(self):
        self.infrontx = self.dir_front() + self.Char.curr_col
        return self.get_tile(self.Char.room, self.infrontx, self.Char.curr_row)
    def get_tile_behind_char(self): return self.get_tile(self.Char.room, self.Char.curr_col - self.dir_front(), self.Char.curr_row)
    def get_tile_above_char(self): return self.get_tile(self.Char.room, self.Char.curr_col, self.Char.curr_row - 1)
    def get_tile_behind_above_char(self): return self.get_tile(self.Char.room, self.Char.curr_col - self.dir_front(), self.Char.curr_row - 1)
    def get_tile_front_above_char(self):
        self.infrontx = self.dir_front() + self.Char.curr_col
        return self.get_tile(self.Char.room, self.infrontx, self.Char.curr_row - 1)

    # ---- sequences
    def seqtbl_offset_char(self, seq_id): self.Char.curr_seq = self.seq_off[seq_id]
    def play_seq(self):
        C = self.Char; tbl = self.seqtbl
        while True:
            cmd = tbl[C.curr_seq]; C.curr_seq += 1
            if cmd == SEQ_DX: C.x = self.char_dx_forward(s8(tbl[C.curr_seq])); C.curr_seq += 1
            elif cmd == SEQ_DY: C.y = (C.y + s8(tbl[C.curr_seq])) & 0xFF; C.curr_seq += 1
            elif cmd == SEQ_FLIP: C.direction = ~C.direction
            elif cmd == SEQ_JMP_IF_FEATHER:
                if not self.is_feather_fall: C.curr_seq += 2
                else: C.curr_seq = tbl[C.curr_seq] | (tbl[C.curr_seq + 1] << 8)
            elif cmd == SEQ_JMP: C.curr_seq = tbl[C.curr_seq] | (tbl[C.curr_seq + 1] << 8)
            elif cmd == SEQ_UP: C.curr_row -= 1; self.start_chompers()
            elif cmd == SEQ_DOWN: self.inc_curr_row(); self.start_chompers()
            elif cmd == SEQ_ACTION: C.action = tbl[C.curr_seq]; C.curr_seq += 1
            elif cmd == SEQ_SET_FALL: C.fall_x = s8(tbl[C.curr_seq]); C.fall_y = s8(tbl[C.curr_seq + 1]); C.curr_seq += 2
            elif cmd == SEQ_KNOCK_UP: self.knock = 1
            elif cmd == SEQ_KNOCK_DOWN: self.knock = -1
            elif cmd == SEQ_SOUND:
                w = tbl[C.curr_seq]
                if w in (SND_SILENT, SND_FOOTSTEP, SND_BUMP): self.is_guard_notice = 1
                if w == SND_FOOTSTEP: self.play_sound(23)
                elif w == SND_BUMP: self.play_sound(8)
                elif w == SND_DRINK: self.play_sound(18)
                elif w == SND_LEVEL:                    # (sound on)
                    if self.level.number == 4: self.play_sound(32); self.end_music = 1
                    elif self.level.number not in (13, 15): self.play_sound(41); self.end_music = 1
                C.curr_seq += 1
            elif cmd == SEQ_END_LEVEL: self.next_level += 1; self.level_done = True
            elif cmd == SEQ_GET_ITEM:
                if tbl[C.curr_seq] == 1: self.proc_get_object()
                C.curr_seq += 1
            elif cmd == SEQ_DIE: pass
            else: C.frame = cmd; return

    # ---- start
    def do_startpos(self):
        L = self.level; C = self.Char
        if L.number == 3 and self.checkpoint:                             # start at the checkpoint
            L.start_dir = 0xFF; L.start_room = 2; L.start_pos = 6
            self.get_tile(7, 4, 0); self.set_tile(self.curr_room, self.curr_tilepos, T.empty)   # remove the loose floor
        C.room = L.start_room; self.next_room = C.room
        x = L.start_pos
        C.curr_col = x % 10; C.curr_row = x // 10
        C.x = X_BUMP[C.curr_col + FIRST_ONSCREEN_COLUMN] + TILE_SIZEX
        C.direction = ~s8(L.start_dir)                                    # (turns into the start direction)
        if self.seamless == 0:
            self.hitp_max = self.hitp_curr = self.hitp_beg_lev if L.number != 0 else 4
        if L.number == 1:                                                 # level 1: press button + falling entry
            self.get_tile(5, 2, 0); self.trigger_button(0, 0, -1)
            self.seqtbl_offset_char(SEQ['fall'])
        elif L.number == 13: self.seqtbl_offset_char(SEQ['run'])          # level 13: running entry
        else: self.seqtbl_offset_char(SEQ['turn'])
        self.set_start_pos()
    def set_start_pos(self):
        C = self.Char
        C.y = Y_LAND[C.curr_row + 1]; C.alive = -1; C.charid = 0
        self.knock = 0; self.upside_down = 0; self.is_feather_fall = 0; self.is_screaming = 0
        C.fall_y = 0; C.fall_x = 0; self.offguard = 0; C.sword = 0; self.droppedout = 0
        self.play_seq()
        if self.level.number == 7 and C.room == 17: self.goto_other_room(3)    # level 7 falling entry: the room below
        self.savekid()
    def find_start_level_door(self):
        room = self.Kid.room
        for pos in range(30):
            if self.tile_at(room, pos) == T.level_door_left:
                self.set_mod(room, pos, 43); self.add_trob(room, pos, 3)      # start fully open, closing

    # ---- trobs (animated tiles)
    def add_trob(self, room, pos, typ):
        for tr in self.trobs:
            if tr[0] == room and tr[1] == pos: tr[2] = typ; return
        self.trobs.append([room, pos, typ])
    def process_trobs(self):
        for tr in self.trobs:
            self.trob = tr; self.animate_tile(); 
        self.trobs = [tr for tr in self.trobs if tr[2] >= 0]
    def animate_tile(self):
        tr = self.trob; room, pos = tr[0], tr[1]
        self.curr_room = room; t = self.get_curr_tile(pos)
        self.modif_room = room            # (C: curr_room_modif, the room of the last get_room_address)
        if t in (T.torch, T.torch_with_debris): self.animate_torch()
        elif t in (T.closer, T.opener): self.animate_button()
        elif t == T.spike: self.animate_spike()
        elif t == T.loose: self.animate_loose()
        elif t == T.empty: tr[2] = -1
        elif t == T.chomper: self.animate_chomper()
        elif t == T.gate: self.animate_door()
        elif t == T.level_door_left: self.animate_leveldoor()
        elif t == T.potion: self.animate_potion()
        elif t == T.sword: self.animate_sword()
        else: tr[2] = -1
        self.set_mod(self.modif_room, pos, self.curr_modifier)
    def is_trob_in_drawn_room(self):
        if self.trob[0] != self.drawn_room: self.trob[2] = -1; return 0
        return 1
    def animate_torch(self):
        tr = self.trob
        if tr[0] == self.drawn_room or (tr[0] == self.links(self.drawn_room)[0] and tr[1] % 10 == 9 and self.drawn_room):
            nxt = self.prandom(255); cur = self.curr_modifier
            if nxt != cur:
                if nxt < 9: self.curr_modifier = nxt; return
                nxt = cur
            nxt += 1
            if nxt >= 9: nxt = 0
            self.curr_modifier = nxt
        else: tr[2] = -1
    def animate_potion(self):
        if self.trob[2] >= 0 and self.is_trob_in_drawn_room():
            typ = self.curr_modifier & 0xF8; nxt = (self.curr_modifier & 7) + 1
            if nxt >= 8: nxt = 1
            self.curr_modifier = typ | nxt
    def animate_sword(self):
        if self.is_trob_in_drawn_room():
            self.curr_modifier = (self.curr_modifier - 1) & 0xFF
            if self.curr_modifier == 0: self.curr_modifier = (self.prandom(255) & 0x3F) + 0x28
    def animate_chomper(self):
        tr = self.trob
        if tr[2] >= 0:
            blood = self.curr_modifier & 0x80; frame = (self.curr_modifier & 0x7F) + 1
            if frame > 15: frame = 1
            self.curr_modifier = blood | frame
            if frame == 2: self.play_sound(47)
            if (tr[0] != self.drawn_room or tr[1] // 10 != self.Kid.curr_row or (self.Kid.alive >= 0 and blood == 0)) and (self.curr_modifier & 0x7F) >= 6:
                tr[2] = -1
    def animate_spike(self):
        tr = self.trob
        if tr[2] >= 0:
            m = self.curr_modifier
            if m == 0xFF: return
            if m & 0x80:
                m -= 1
                if m & 0x7F: self.curr_modifier = m; return
                m = 6
            else:
                m += 1
                if m == 5: m = 0x8F
                elif m == 9: m = 0; tr[2] = -1
            self.curr_modifier = m
    def animate_door(self):
        tr = self.trob; at = tr[2]
        if at >= 0:
            if at >= 3:
                if at < 8: at += 1; tr[2] = at
                nm = self.curr_modifier - GATE_CLOSE_SPEEDS[at]
                if nm < 0: nm = 0; tr[2] = -1; self.play_sound(6)
                self.curr_modifier = nm
            else:
                if self.curr_modifier != 0xFF:
                    self.curr_modifier = (self.curr_modifier + DOOR_DELTA[at]) & 0xFF
                    if at == 0:
                        if self.curr_modifier != 0:
                            if self.curr_modifier < 188 and (self.curr_modifier & 3) == 3: self.play_door_sound_if_visible(4)
                        else: self.gate_stop()
                    else:
                        if self.curr_modifier < 188:
                            if (self.curr_modifier & 7) == 0: self.play_sound(5)
                        elif at < 2: self.curr_modifier = 238; tr[2] = 0; self.play_sound(7)
                        else: self.curr_modifier = 0xFF; self.gate_stop()
                else: self.gate_stop()
    def gate_stop(self):
        self.trob[2] = -1; self.play_door_sound_if_visible(7)
    def play_door_sound_if_visible(self, sid):
        pos, room = self.trob[1], self.trob[0]
        room_L = self.links(self.drawn_room)[0] if self.drawn_room else 0     # (load_room_links)
        if (self.level.number == 3 and room == 2) or (pos % 10 == 9 if room == room_L else (room == self.drawn_room and pos % 10 != 9)):
            self.play_sound(sid)
    def animate_leveldoor(self):
        tr = self.trob
        if tr[2] >= 0:
            if tr[2] >= 3:
                tr[2] += 1
                m = (self.curr_modifier - LEVELDOOR_CLOSE_SPEEDS[tr[2] - 3]) & 0xFF
                if m >= 0x80: m = 0; tr[2] = -1; self.play_sound(14)
                elif tr[2] == 4: self.snd_interruptible[15] = 1; self.play_sound(15)     # (sfDigi)
                self.curr_modifier = m
            else:
                self.curr_modifier += 1
                if self.curr_modifier >= 43:
                    tr[2] = -1
                    self.stop_sounds()
                    if self.leveldoor_open in (0, 2):
                        self.leveldoor_open = 1
                        if self.level.number == 4:                     # level 4: the mirror appears
                            self.get_tile(4, 4, 0); self.set_tile(self.curr_room, self.curr_tilepos, T.mirror)
                            # (original bug: animate_tile then stores the door's modifier in this room, at the
                            # door's tile position: the door stays at 42, room 4 tile 12 gets 43)
                            self.modif_room = self.curr_room
                else: self.snd_interruptible[15] = 0; self.play_sound(15)
    def animate_button(self):
        tr = self.trob
        if tr[2] >= 0:
            timer = (self.get_doorlink_timer(self.curr_modifier) - 1) & 0xFFFF     # C: word (0 - 1 is not < 2)
            self.set_doorlink_timer(self.curr_modifier, timer)
            if timer < 2: tr[2] = -1
    def animate_loose(self):
        tr = self.trob
        if tr[2] >= 0:
            self.curr_modifier = (self.curr_modifier + 1) & 0xFF
            if self.curr_modifier & 0x80:
                if self.level.number == 13: return     # level 13: keeps shaking (the auto-falling floors)
                if self.curr_modifier >= 0x84: self.curr_modifier = 0; tr[2] = -1
                self.loose_shake(not self.curr_modifier)
            else:
                if self.curr_modifier >= LOOSE_FLOOR_DELAY:
                    room, pos = tr[0], tr[1]
                    self.curr_modifier = self.remove_loose(room, pos); tr[2] = -1
                    row = pos // 10
                    self.mobs.append({'xh': (pos % 10) << 2, 'y': Y_LOOSE_LAND[row + 1], 'room': room, 'speed': 0, 'type': 0, 'row': row})
                else: self.loose_shake(0)
    def loose_shake(self, arg):
        if arg or LOOSE_SOUND[self.curr_modifier & 0x7F]:
            while True:
                sid = self.prandom(2) + 20
                if sid != self.last_loose_sound: break
            self.prandom(2)
            self.last_loose_sound = sid
            self.play_sound(sid)
    def remove_loose(self, room, pos):
        self.set_tile(room, pos, T.empty); return self.level.type
    def make_loose_fall(self, modifier):
        if (self.level.fg[(self.curr_room - 1) * 30 + self.curr_tilepos] & 0x20) == 0:
            if s8(self.mod_at(self.curr_room, self.curr_tilepos)) <= 0:
                self.set_mod(self.curr_room, self.curr_tilepos, modifier); self.add_trob(self.curr_room, self.curr_tilepos, 0)
    def loose_make_shake(self):
        if self.mod_at(self.curr_room, self.curr_tilepos) == 0 and self.level.number != 13: self.set_mod(self.curr_room, self.curr_tilepos, 0x80); self.add_trob(self.curr_room, self.curr_tilepos, 1)
    def do_knock(self, room, row):
        for col in range(10):
            if self.get_tile(room, col, row) == T.loose: self.loose_make_shake()
    def start_anim_spike(self, room, pos):
        old = s8(self.mod_at(room, pos))
        if old <= 0:
            if old == 0: self.add_trob(room, pos, 1); self.play_sound(49)
            elif old != -1: self.set_mod(room, pos, 0x8F)
    def start_chompers(self):
        timing = 15; C = self.Char
        if 0 <= C.curr_row < 3 and C.room:
            self.curr_room = C.room
            for col in range(10):
                pos = TBL_LINE[C.curr_row] + col
                if self.get_curr_tile(pos) == T.chomper:
                    m = self.curr_modifier & 0x7F
                    if m == 0 or m >= 6:
                        old = self.curr_modifier
                        if old == 0 or old >= 6: self.set_mod(C.room, pos, timing | (old & 0x80)); self.add_trob(C.room, pos, 1)
                        timing -= 3
                        if timing < 6: timing += 10
    def anim_tile_modif(self):
        room = self.drawn_room; self.curr_room = room
        for pos in range(30):
            t = self.get_curr_tile(pos)
            if t == T.potion: self.set_mod(room, pos, (self.curr_modifier & 0xF8) | (self.prandom(6) + 1)); self.add_trob(room, pos, 1)
            elif t in (T.torch, T.torch_with_debris): self.set_mod(room, pos, self.prandom(8)); self.add_trob(room, pos, 1)
            elif t == T.sword: self.set_mod(room, pos, self.prandom(0xFF) & 0x1F); self.add_trob(room, pos, 1)
        room_L = self.links(room)[0]
        for row in range(3):
            if self.get_tile(room_L, 9, row) in (T.torch, T.torch_with_debris):
                self.set_mod(room_L, row * 10 + 9, self.prandom(8)); self.add_trob(room_L, row * 10 + 9, 1)
    def check_the_end(self):
        if self.next_room != 0 and self.next_room != self.drawn_room:
            self.drawn_room = self.next_room
            if self.level.number == 14 and self.drawn_room == 5:     # the princess's room: the game is won (end_sequence)
                self.game_over = 'END'; return
            self.loadkid()
            self.anim_tile_modif(); self.start_chompers(); self.check_fall_flo(); self.check_shadow()
            self.exit_room_timer = 2          # redraw_screen() after a room change
    # ---- buttons and door links
    def get_doorlink_timer(self, i): return self.dl2[i] & 0x1F
    def set_doorlink_timer(self, i, v): self.dl2[i] = (self.dl2[i] & 0xE0) | (v & 0x1F)
    def trigger_button(self, playsound, button_type, modifier):
        self.get_curr_tile(self.curr_tilepos)
        if button_type == 0: button_type = self.curr_tile
        if modifier == -1: modifier = self.curr_modifier
        lt = self.get_doorlink_timer(modifier)
        if lt != 0x1F:
            self.set_doorlink_timer(modifier, 5)
            if lt < 2:
                self.add_trob(self.curr_room, self.curr_tilepos, 1); self.is_guard_notice = 1
                if playsound: self.play_sound(3)
            self.do_trigger_list(modifier, button_type)
    def do_trigger_list(self, index, button_type):
        while True:
            d1 = self.dl1[index]; d2 = self.dl2[index]
            room = ((d1 & 0x60) >> 5) + ((d2 & 0xE0) >> 3); pos = d1 & 0x1F
            target = self.tile_at(room, pos) if room else T.wall
            res = -1
            if target == T.gate: res = self.trigger_gate(room, pos, button_type)
            elif target == T.level_door_left: res = -1 if self.mod_at(room, pos) != 0 else 1
            if res >= 0: self.add_trob(room, pos, res)
            if d1 & 0x80: break
            index += 1
    def trigger_gate(self, room, pos, button_type):
        m = self.mod_at(room, pos)
        if button_type == T.opener:
            if m == 0xFF: return -1
            if m >= 188: self.set_mod(room, pos, 238); return -1
            self.set_mod(room, pos, (m + 3) & 0xFC); return 1
        elif button_type == T.debris:
            if m < 188: return 2
            self.set_mod(room, pos, 0xFF); return -1
        else:
            return 3 if m != 0 else -1
    def died_on_button(self):
        bt = self.get_curr_tile(self.curr_tilepos); m = self.curr_modifier
        if self.curr_tile == T.opener:
            self.set_tile(self.curr_room, self.curr_tilepos, T.floor); self.set_mod(self.curr_room, self.curr_tilepos, 0); bt = T.debris
        else: self.set_tile(self.curr_room, self.curr_tilepos, T.stuck)
        self.trigger_button(1, bt, m)
    # ---- mobs (falling loose floors)
    def do_mobs(self):
        for i in range(len(self.mobs)):
            self.curmob_index = i; self.curmob = self.mobs[i]
            self.move_mob(); self.check_loose_fall_on_kid(); self.mobs[i] = self.curmob
        self.mobs = [m for m in self.mobs if m['speed'] != -1]
    def move_mob(self):
        if self.curmob['type'] == 0: self.move_loose()
        if self.curmob['speed'] <= 0: self.curmob['speed'] += 1
    def move_loose(self):
        m = self.curmob
        if m['speed'] < 0: return
        if m['speed'] < 29: m['speed'] += 3
        m['y'] = (m['y'] + m['speed']) & 0xFF
        if m['room'] == 0:
            if m['y'] >= 210: m['speed'] = -2
            return
        if m['y'] < 226 and Y_SOMETHING[m['row'] + 1] <= m['y']:
            t = self.get_tile(m['room'], m['xh'] >> 2, m['row'])
            if t == T.loose: self.loose_fall()
            if t in (T.empty, T.loose): self.mob_down_a_row(); return
            self.play_sound(2)
            self.do_knock(m['room'], m['row'])
            m['y'] = Y_SOMETHING[m['row'] + 1]; m['speed'] = -2
            self.loose_land()
    def loose_land(self):
        m = self.curmob; bt = 0
        t = self.get_tile(m['room'], m['xh'] >> 2, m['row'])
        if t == T.opener:
            self.set_tile(self.curr_room, self.curr_tilepos, T.debris); bt = T.debris
        if t in (T.opener, T.closer):
            self.trigger_button(1, bt, -1); t = self.get_tile(m['room'], m['xh'] >> 2, m['row'])
        if t in (T.opener, T.closer, T.floor, T.spike, T.potion, T.torch, T.torch_with_debris):
            if t in (T.torch, T.torch_with_debris): self.set_tile(self.curr_room, self.curr_tilepos, T.torch_with_debris)
            else: self.set_tile(self.curr_room, self.curr_tilepos, T.debris)
    def loose_fall(self):
        self.set_mod(self.curr_room, self.curr_tilepos, self.remove_loose(self.curr_room, self.curr_tilepos))
        m = self.curmob; m['speed'] = m['speed'] >> 1; self.mobs[self.curmob_index] = dict(m)
        m['y'] = (m['y'] + 6) & 0xFF; self.mob_down_a_row(); self.mobs.append(dict(m))
        self.curmob = self.mobs[self.curmob_index]
    def mob_down_a_row(self):
        m = self.curmob; m['row'] += 1
        if m['row'] >= 3: m['y'] = (m['y'] - 192) & 0xFF; m['row'] = 0; m['room'] = self.links(m['room'])[3] if m['room'] else 0
    def check_loose_fall_on_kid(self):
        m = self.curmob; self.Char = self.Kid.copy(); C = self.Char
        if C.room == m['room'] and C.curr_col == m['xh'] >> 2 and m['y'] < C.y and C.y - 30 < m['y']:
            self.fell_on_your_head(); self.Kid = C.copy()
    def fell_on_your_head(self):
        C = self.Char; f = C.frame; a = C.action
        if (self.level.number == 13 or f < 5 or f >= 15) and (a < A_HANG_CLIMB or a == A_TURN):   # (level 13: also running)
            C.y = Y_LAND[C.curr_row + 1]
            if self.take_hp(1):
                self.seqtbl_offset_char(SEQ['crushed'])
                if f == 177: C.x = self.char_dx_forward(-12)
            else:
                if f != 109:
                    if self.get_tile_behind_char() == 0: C.x = self.char_dx_forward(-2)
                    self.seqtbl_offset_char(SEQ['loose_floor_fell_on_kid'])
    # ---- hit points
    def take_hp(self, count):
        if self.Char.charid == CHARID_KID:
            if count >= self.hitp_curr: self.hitp_delta = -self.hitp_curr; return 1
            self.hitp_delta = -count; return 0
        if count >= self.guardhp_curr: self.guardhp_delta = -self.guardhp_curr; return 1
        self.guardhp_delta = -count; return 0
    def do_delta_hp(self):
        if self.Opp.charid == CHARID_SHADOW and self.level.number == 12 and self.guardhp_delta != 0:
            self.hitp_delta = self.guardhp_delta          # level 12: hurting the shadow hurts the kid
        self.hitp_curr = min(max(self.hitp_curr + self.hitp_delta, 0), self.hitp_max)
        self.guardhp_curr = min(max(self.guardhp_curr + self.guardhp_delta, 0), self.guardhp_max)

    # ---- control
    def release_arrows(self):
        self.control_backward = self.control_forward = self.control_up = self.control_down = RELEASED
        return 1
    def read_user_control(self):
        if self.control_forward >= RELEASED:
            if self.control_x == X_FORWARD:
                if self.control_forward == RELEASED: self.control_forward = HELD
            else: self.control_forward = RELEASED
        if self.control_backward >= RELEASED:
            if self.control_x == X_BACKWARD:
                if self.control_backward == RELEASED: self.control_backward = HELD
            else: self.control_backward = RELEASED
        if self.control_up >= RELEASED:
            if self.control_y == Y_UP:
                if self.control_up == RELEASED: self.control_up = HELD
            else: self.control_up = RELEASED
        if self.control_down >= RELEASED:
            if self.control_y == Y_DOWN:
                if self.control_down == RELEASED: self.control_down = HELD
            else: self.control_down = RELEASED
        if self.control_shift2 >= RELEASED:
            if self.control_shift == HELD:
                if self.control_shift2 == RELEASED: self.control_shift2 = HELD
            else: self.control_shift2 = RELEASED
    def flip_control_x(self):
        self.control_x = -self.control_x
        self.control_forward, self.control_backward = self.control_backward, self.control_forward
    def user_control(self):
        if self.Char.direction >= RIGHT:
            self.flip_control_x(); self.control(); self.flip_control_x()
        else: self.control()
    def control(self):
        C = self.Char; f = C.frame
        if C.alive >= 0:
            if f in (15, 166, 158, 171): self.seqtbl_offset_char(SEQ['dying'])
            return
        a = C.action
        if a in (A_BUMPED, A_FREEFALL): self.release_arrows()
        elif C.sword == SWORD_DRAWN: self.control_with_sword()
        elif C.charid >= CHARID_GUARD: self.control_guard_inactive()
        elif f == 15 or 50 <= f < 53: self.control_standing()
        elif f == 48: self.control_turning()
        elif f < 4: self.control_startrun()
        elif 67 <= f < 70: self.control_jumpup()
        elif f < 15: self.control_running()
        elif 87 <= f < 100: self.control_hanging()
        elif f == 109: self.control_crouched()
    def control_crouched(self):
        if self.need_level1_music and self.level.number == 1:      # the level 1 start: crouched until the music ends
            if not self.sound_playing('crouch'):
                if self.need_level1_music == 1: self.play_sound(25); self.need_level1_music = 2
                else: self.need_level1_music = 0
            return
        self.need_level1_music = 0
        if self.control_shift2 == HELD and self.check_get_item(): return
        if self.control_y != Y_DOWN: self.seqtbl_offset_char(SEQ['stand_up_from_crouch'])
        elif self.control_forward == HELD:
            self.control_forward = IGNORE; self.seqtbl_offset_char(SEQ['crouch_hop'])
    def control_standing(self):
        if self.control_shift2 == HELD and self.control_shift == HELD and self.check_get_item(): return
        if self.Char.charid != CHARID_KID and self.control_down == HELD and self.control_forward == HELD:
            self.draw_sword(); return
        offguard_skip = False                 # C: goto loc_6213 (skip the shift branch)
        if self.have_sword:
            if self.offguard != 0 and self.control_shift >= RELEASED: offguard_skip = True
            elif self.can_guard_see_kid >= 2:
                distance = self.char_opp_dist()
                if -10 <= distance < 90:
                    self.holding_sword = 1
                    if (distance & 0xFFFF) < 0xFFFA:                     # (word)distance < (word)-6
                        O = self.Opp
                        if O.charid == CHARID_SHADOW and (O.action == A_MIDAIR or 107 <= O.frame < 118):
                            self.offguard = 0
                        else:
                            self.draw_sword(); return
                    else:
                        self.back_pressed(); return
            else: self.offguard = 0
        if self.control_shift == HELD and not offguard_skip:
            if self.control_backward == HELD: self.back_pressed()
            elif self.control_up == HELD: self.up_pressed()
            elif self.control_down == HELD: self.down_pressed()
            elif self.control_x == X_FORWARD and self.control_forward == HELD: self.safe_step()
        elif self.control_forward == HELD:                              # keyboard mode: up+forward = standing jump
            if self.control_up == HELD: self.standing_jump()
            else: self.forward_pressed()
        elif self.control_backward == HELD: self.back_pressed()
        elif self.control_up == HELD:
            if self.control_forward == HELD: self.standing_jump()
            else: self.up_pressed()
        elif self.control_down == HELD: self.down_pressed()
        elif self.control_x == X_FORWARD: self.forward_pressed()
    def up_pressed(self):
        ld = -1
        if self.get_tile_at_char() == T.level_door_left: ld = self.curr_tilepos
        elif self.get_tile_behind_char() == T.level_door_left: ld = self.curr_tilepos
        elif self.get_tile_infrontof_char() == T.level_door_left: ld = self.curr_tilepos
        if ld != -1 and self.level.start_room != self.drawn_room and self.leveldoor_open:
            self.Char.x = (X_BUMP[self.tile_col + FIRST_ONSCREEN_COLUMN] + 10) & 0xFF
            self.Char.direction = LEFT
            self.seqtbl_offset_char(SEQ['go_up_on_level_door']); return
        if self.control_x == X_FORWARD: self.standing_jump()
        else: self.check_jump_up()
    def down_pressed(self):
        self.control_down = IGNORE
        if not self.tile_is_floor(self.get_tile_infrontof_char()) and self.distance_to_edge_weight() < 3:
            self.Char.x = self.char_dx_forward(5); self.load_fram_det_col()
        elif not self.tile_is_floor(self.get_tile_behind_char()) and self.distance_to_edge_weight() >= 8:
            self.through_tile = self.get_tile_behind_char()
            self.get_tile_at_char()
            if self.can_grab() and (self.Char.direction >= RIGHT or self.get_tile_at_char() != T.gate or self.modif() >> 2 >= 6):
                self.Char.x = self.char_dx_forward(self.distance_to_edge_weight() - 9)
                self.seqtbl_offset_char(SEQ['climb_down'])
            else: self.crouch()
        else: self.crouch()
    def control_turning(self):
        if self.control_shift >= RELEASED and self.control_x == X_FORWARD and self.control_y >= RELEASED:
            self.seqtbl_offset_char(SEQ['start_run_after_turn'])
    def crouch(self):
        self.seqtbl_offset_char(SEQ['crouch']); self.control_down = self.release_arrows()
    def back_pressed(self):
        self.control_backward = self.release_arrows()
        # after the turn the kid draws the sword if he has it, sees the guard, the guard was behind him and there is room
        if (self.have_sword == 0 or self.can_guard_see_kid < 2 or self.char_opp_dist() > 0 or
                self.distance_to_edge_weight() < 2):
            seq = SEQ['turn']
        else:
            self.Char.sword = SWORD_DRAWN; self.offguard = 0; seq = SEQ['turn_draw_sword']
        self.seqtbl_offset_char(seq)
    def forward_pressed(self):
        d = self.get_edge_distance()
        if self.edge_type == EDGE_WALL and self.curr_tile2 != T.chomper and d < 8:
            if self.control_forward == HELD: self.safe_step()
        else: self.seqtbl_offset_char(SEQ['start_run'])
    def control_running(self):
        C = self.Char
        if self.control_x == RELEASED and C.frame in (7, 11):
            self.control_forward = self.release_arrows(); self.seqtbl_offset_char(SEQ['stop_run'])
        elif self.control_x == X_BACKWARD:
            self.control_backward = self.release_arrows(); self.seqtbl_offset_char(SEQ['run_turn'])
        elif self.control_y == Y_UP and self.control_up == HELD: self.run_jump()
        elif self.control_down == HELD:
            self.control_down = IGNORE; self.seqtbl_offset_char(SEQ['crouch_while_running'])
    def safe_step(self):
        self.control_shift2 = IGNORE; self.control_forward = IGNORE
        d = self.get_edge_distance()
        if d:
            self.Char.repeat = 1; self.seqtbl_offset_char(d + 28)
        elif self.edge_type != EDGE_WALL and self.Char.repeat != 0:
            self.Char.repeat = 0; self.seqtbl_offset_char(SEQ['step_on_edge'])
        else: self.seqtbl_offset_char(SEQ['safe_step_11'])
    def control_startrun(self):
        if self.control_y == Y_UP and self.control_x == X_FORWARD: self.standing_jump()
    def control_jumpup(self):
        if self.control_x == X_FORWARD or self.control_forward == HELD: self.standing_jump()
    def standing_jump(self):
        self.control_up = self.control_forward = IGNORE; self.seqtbl_offset_char(SEQ['standing_jump'])
    def check_jump_up(self):
        self.control_up = self.release_arrows()
        self.through_tile = self.get_tile_above_char()
        self.get_tile_front_above_char()
        if self.can_grab(): self.grab_up_with_floor_behind()
        else:
            self.through_tile = self.get_tile_behind_above_char()
            self.get_tile_above_char()
            if self.can_grab(): self.jump_up_or_grab()
            else: self.jump_up()
    def jump_up_or_grab(self):
        d = self.distance_to_edge_weight()
        if d < 6: self.jump_up()
        elif not self.tile_is_floor(self.get_tile_behind_char()): self.grab_up_no_floor_behind()
        else:
            self.Char.x = self.char_dx_forward(d - TILE_SIZEX); self.load_fram_det_col()
            self.grab_up_with_floor_behind()
    def grab_up_no_floor_behind(self):
        self.get_tile_above_char()
        self.Char.x = self.char_dx_forward(self.distance_to_edge_weight() - 10)
        self.seqtbl_offset_char(SEQ['jump_up_and_grab'])
    def jump_up(self):
        self.control_up = self.release_arrows()
        d = self.get_edge_distance()
        if d < 4 and self.edge_type == EDGE_WALL: self.Char.x = self.char_dx_forward(d - 3)
        delta_x = 0               # (feather fall: grabbing 2 rows up is easier from a floor's edge)
        if self.is_feather_fall and not self.tile_is_floor(self.get_tile_above_char()) and self.curr_tile2 != T.wall:
            delta_x = 1 if self.Char.direction == LEFT else 3
        self.get_tile(self.Char.room, self.get_tile_div_mod(self.back_delta_x(delta_x) + self.dx_weight() - 6), self.Char.curr_row - 1)
        if self.curr_tile2 != T.wall and not self.tile_is_floor(self.curr_tile2): self.seqtbl_offset_char(SEQ['jump_up_with_nothing_above'])
        else: self.seqtbl_offset_char(SEQ['jump_up_into_ceiling'])
    def control_hanging(self):
        C = self.Char
        if C.alive < 0:
            if self.grab_timer == 0 and self.control_y == HELD: self.can_climb_up()
            elif self.control_shift == HELD:
                if C.action != A_HANG_STRAIGHT and (self.get_tile_at_char() == T.wall or (C.direction == LEFT and self.curr_tile2 in (T.doortop_with_floor, T.doortop))):
                    if self.grab_timer == 0: self.play_sound(8)
                    self.seqtbl_offset_char(SEQ['hang_against_wall'])
                elif not self.tile_is_floor(self.get_tile_above_char()): self.hang_fall()
            else: self.hang_fall()
        else: self.hang_fall()
    def can_climb_up(self):
        seq_id = SEQ['climb_up']
        self.control_up = self.control_shift2 = self.release_arrows()
        self.get_tile_above_char()
        if ((self.curr_tile2 in (T.mirror, T.chomper) and self.Char.direction == RIGHT) or
                (self.curr_tile2 == T.gate and self.Char.direction != RIGHT and self.modif() >> 2 < 6)):
            seq_id = SEQ['climb_up_to_closed_gate']
        self.seqtbl_offset_char(seq_id)
    def hang_fall(self):
        self.control_down = self.release_arrows()
        if not self.tile_is_floor(self.get_tile_behind_char()) and not self.tile_is_floor(self.get_tile_at_char()):
            self.seqtbl_offset_char(SEQ['release_ledge_and_fall'])
        else:
            if self.get_tile_at_char() == T.wall or (self.Char.direction < RIGHT and self.curr_tile2 in (T.doortop_with_floor, T.doortop)):
                self.Char.x = self.char_dx_forward(-7)
            self.seqtbl_offset_char(SEQ['release_ledge_and_land'])
    def grab_up_with_floor_behind(self):
        d = self.distance_to_edge_weight()
        ed = self.get_edge_distance()
        if d < 4 and ed < 4 and self.edge_type != EDGE_WALL:
            self.Char.x = self.char_dx_forward(d); self.seqtbl_offset_char(SEQ['jump_up_and_grab_straight'])
        else:
            self.Char.x = self.char_dx_forward(d - 4); self.seqtbl_offset_char(SEQ['jump_up_and_grab_forward'])
    def run_jump(self):
        C = self.Char
        if C.frame >= 7:
            xpos = self.char_dx_forward(4); col = self.get_tile_div_mod_m7(xpos)
            for tiles_forward in range(2):
                col += self.dir_front()
                self.get_tile(C.room, col, C.curr_row)
                if self.curr_tile2 == T.spike or not self.tile_is_floor(self.curr_tile2):
                    adj = self.distance_to_edge(xpos) + TILE_SIZEX * tiles_forward - TILE_SIZEX
                    if (adj & 0xFFFF) < 0xFFF8 or adj >= 2:
                        if adj < 128: return
                        adj = -3
                    C.x = self.char_dx_forward(adj + 4)
                    break
            self.control_up = self.release_arrows()
            self.seqtbl_offset_char(SEQ['run_jump'])
    # ---- sword (seg005)
    def back_with_sword(self):
        if self.Char.frame in (158, 170, 171):
            self.control_backward = IGNORE; self.seqtbl_offset_char(SEQ['back_with_sword'])
    def forward_with_sword(self):
        if self.Char.frame in (158, 170, 171):
            self.control_forward = IGNORE
            if self.Char.charid != CHARID_KID: self.seqtbl_offset_char(SEQ['guard_forward_with_sword'])
            else: self.seqtbl_offset_char(SEQ['forward_with_sword'])
    def draw_sword(self):
        seq = SEQ['draw_sword']
        self.control_forward = self.control_shift2 = self.release_arrows()
        if self.Char.charid == CHARID_KID: self.play_sound(19); self.offguard = 0
        elif self.Char.charid != CHARID_SHADOW: seq = SEQ['en_garde']
        self.Char.sword = SWORD_DRAWN
        self.seqtbl_offset_char(seq)
    def control_with_sword(self):
        C = self.Char
        if C.action < A_HANG_CLIMB:
            if self.get_tile_at_char() == T.loose or self.can_guard_see_kid >= 2:
                distance = self.char_opp_dist()
                if (distance & 0xFFFF) < 90: self.swordfight(); return        # (word)distance < 90
                elif distance < 0:
                    if (distance & 0xFFFF) < 0xFFFC: self.seqtbl_offset_char(SEQ['turn_with_sword']); return   # < (word)-4
                    else: self.swordfight(); return
            if C.charid == CHARID_KID and C.alive < 0: self.holding_sword = 0
            if C.charid < CHARID_GUARD:
                if C.frame == 171: C.sword = SWORD_SHEATHED; self.seqtbl_offset_char(SEQ['put_sword_away'])
            else: self.swordfight()
    def swordfight(self):
        C = self.Char; frame = C.frame; charid = C.charid
        if frame == 161 and self.control_shift2 >= 0:
            self.seqtbl_offset_char(SEQ['back_with_sword']); return      # back with sword (when parrying)
        elif self.control_shift2 == HELD:
            if charid == CHARID_KID: self.kid_sword_strike = 15
            self.sword_strike()
            if self.control_shift2 == IGNORE: return
        if self.control_down == HELD:
            if frame in (158, 170, 171):
                self.control_down = IGNORE
                C.sword = SWORD_SHEATHED
                if charid == CHARID_KID:
                    self.offguard = 1; self.guard_refrac = 9; self.holding_sword = 0; seq = SEQ['put_sword_away_fast']
                elif charid == CHARID_SHADOW: seq = SEQ['put_sword_away']
                else: seq = SEQ['guard_become_inactive']
                self.seqtbl_offset_char(seq)
        elif self.control_up == HELD: self.parry()
        elif self.control_forward == HELD: self.forward_with_sword()
        elif self.control_backward == HELD: self.back_with_sword()
    def sword_strike(self):
        frame = self.Char.frame
        if frame in (157, 158, 170, 171, 165):
            seq = SEQ['strike'] if self.Char.charid == CHARID_KID else SEQ['guard_strike']
        elif frame in (150, 161): seq = SEQ['strike_after_parry']
        else: return
        self.control_shift2 = IGNORE
        self.seqtbl_offset_char(seq)
    def parry(self):
        char_frame = self.Char.frame; opp_frame = self.Opp.frame; char_charid = self.Char.charid
        seq = SEQ['parry']; do_play_seq = 0
        if char_frame in (158, 170, 171, 168, 165):
            if self.char_opp_dist() >= 32 and char_charid != CHARID_KID:
                self.back_with_sword(); return
            elif char_charid == CHARID_KID:
                if opp_frame == 168: return
                if opp_frame not in (151, 152, 162):
                    if opp_frame == 153: do_play_seq = 1
                    elif char_charid != CHARID_KID: self.back_with_sword(); return
            else:
                if opp_frame != 152: return
        else:
            if char_frame != 167: return
            seq = SEQ['parry_after_strike']
        self.control_up = IGNORE
        self.seqtbl_offset_char(seq)
        if do_play_seq: self.play_seq()
    def control_guard_inactive(self):
        if self.Char.frame == 166 and self.control_down == HELD:
            if self.control_forward == HELD: self.draw_sword()
            else: self.control_down = IGNORE; self.seqtbl_offset_char(SEQ['stand_flipped'])
    def can_grab(self):
        m = self.modif(); C = self.Char
        if self.through_tile == T.wall: return 0
        if self.through_tile == T.doortop and C.direction >= RIGHT: return 0
        if self.tile_is_floor(self.through_tile): return 0
        if self.curr_tile2 == T.loose and m != 0: return 0
        if self.curr_tile2 == T.doortop_with_floor and C.direction < RIGHT: return 0
        if not self.tile_is_floor(self.curr_tile2): return 0
        return 1
    def can_grab_front_above(self):
        self.through_tile = self.get_tile_above_char(); self.get_tile_front_above_char(); return self.can_grab()
    def can_bump_into_gate(self): return (self.modif() >> 2) + 6 < self.char_height
    def dist_from_wall_forward(self, tiletype):
        if tiletype == T.gate and not self.can_bump_into_gate(): return -1
        self.coll_tile_left_xpos = X_BUMP[self.tile_col + FIRST_ONSCREEN_COLUMN] + TILE_MIDX
        wt = self.wall_type(tiletype)
        if wt == 0: return -1
        if self.Char.direction < RIGHT:
            return self.char_x_left_coll - (self.coll_tile_left_xpos + TILE_RIGHTX - WALL_DIST_FROM_RIGHT[wt])
        return WALL_DIST_FROM_LEFT[wt] + self.coll_tile_left_xpos - self.char_x_right_coll
    def get_edge_distance(self):
        self.determine_col(); self.load_frame_to_obj(); self.set_char_collision()
        tiletype = self.get_tile_at_char()
        def wall_result(distance):
            if distance <= TILE_RIGHTX: self.edge_type = EDGE_WALL; return distance
            self.edge_type = EDGE_FLOOR; return 11
        distance = None
        if self.wall_type(tiletype) != 0:
            self.tile_col = self.Char.curr_col
            d = self.dist_from_wall_forward(tiletype)
            if d >= 0: distance = wall_result(d)
        if distance is None:
            tiletype = self.get_tile_infrontof_char()
            if tiletype == T.doortop and self.Char.direction >= RIGHT:
                self.edge_type = EDGE_CLOSER; distance = self.distance_to_edge_weight()
            else:
                if self.wall_type(tiletype) != 0:
                    self.tile_col = self.infrontx
                    d = self.dist_from_wall_forward(tiletype)
                    if d >= 0: distance = wall_result(d)
                if distance is None:
                    if tiletype == T.loose:
                        self.edge_type = EDGE_CLOSER; distance = self.distance_to_edge_weight()
                    elif tiletype in (T.closer, T.sword, T.potion):
                        distance = self.distance_to_edge_weight()
                        if distance != 0: self.edge_type = EDGE_CLOSER
                        else: self.edge_type = EDGE_FLOOR; distance = 11
                    elif self.tile_is_floor(tiletype): self.edge_type = EDGE_FLOOR; distance = 11
                    else: self.edge_type = EDGE_CLOSER; distance = self.distance_to_edge_weight()
        self.curr_tile2 = tiletype
        return distance

    # ---- drawing: SDLPoP clip_char (add_kid_to_objtable) for the kid as he is after the tick
    Y_CLIP = [-60, 3, 66, 129, 192]
    def draw_cols(self):
        """SDLPoP redraw_at_char (drawing only): a character holding the sword widens char_col_left/right by one
        column in his facing direction; clip_char and redraw_at_char2 see the widened columns."""
        C = self.Char
        if C.sword >= SWORD_DRAWN:
            if C.direction >= RIGHT: self.char_col_right = min(self.char_col_right + 1, 9)
            else: self.char_col_left = max(self.char_col_left - 1, 0)
    def clip_char(self, who=None):
        """(clip_top, clip_right) in screen pixels for drawing the kid (or the character who: clip_left 0, clip_bottom 192)."""
        C = self.Char = (who or self.Kid).copy()
        self.load_fram_det_col(); self.load_frame_to_obj(); self.set_char_collision(); self.draw_cols()
        f, a, room, row = C.frame, C.action, C.room, C.curr_row
        top, right = 0, 320
        if 224 <= f < 229:
            for col in range(10):                   # the level door in his row (game.asm's kid_clip, door fully open)
                pos = row * 10 + col
                if 0 <= row < 3 and self.tile_at(room, pos) == T.level_door_left:
                    right = ((col + 1) * 4 + 6 + (1 if self.level.type else 0)) * 8
                    yb = (63 * row + 49) & 0xFF; m = self.mod_at(room, pos)
                    lb = (yb - (m & 3) - 48) & 0xFF; y = (yb - m) & 0xFF
                    while lb < y: lb = (lb + 4) & 0xFF
                    top = lb + 1
                    break
            return top, right
        if self.get_tile(room, self.char_col_left, self.char_top_row) == T.wall or self.tile_is_floor(self.curr_tile2):
            if (a == A_STAND and f in (79, 81)) or self.get_tile(room, self.char_col_right, self.char_top_row) == T.wall or self.tile_is_floor(self.curr_tile2):
                clip_row = row + 1; clip_y = self.Y_CLIP[clip_row]
                if clip_row == 1 or (clip_y < self.obj_y and clip_y - 15 < self.char_top_y):
                    top = min(max(clip_y, 0), 192)
        col = self.get_tile_div_mod(self.char_x_left_coll - 4)
        if self.get_tile(room, col + 1, row) == T.doortop_with_floor or self.curr_tile2 == T.doortop:
            right = (self.tile_col << 5) + 32
        else:
            if ((self.get_tile(room, col, row) != T.doortop_with_floor and self.curr_tile2 != T.doortop) or a == A_MIDAIR or
                    (a == A_FREEFALL and f == 106) or (a == A_BUMPED and f == 107) or
                    (C.direction < RIGHT and (a in (A_HANG_CLIMB, A_HANG_STRAIGHT) or (a == A_RUN_JUMP and 137 <= f < 140)))):
                col = self.get_tile_div_mod(self.char_x_right_coll)
                if ((self.get_tile(room, col, row) == T.wall or (self.curr_tile2 == T.mirror and C.direction == RIGHT)) and
                        (self.get_tile(room, col, self.char_top_row) == T.wall or self.curr_tile2 == T.mirror) and room == self.curr_room):
                    right = self.tile_col << 5
            else:
                right = (self.tile_col << 5) + 32
        return top, right

    def overlay_tiles(self, who=None):
        """SDLPoP redraw_at_char2 + set_objtile_at_char for the kid (or the character who): (kind, tileposes, objtile)
        or None. kind 'other' = draw_other_overlay, 'floor' = draw_floor_overlay (climb frames 137..144); a tilepos < 0
        is a column of the row above the room (-(col + 1)), 30 = none."""
        C = self.Char = (who or self.Kid).copy()
        self.load_fram_det_col(); self.load_frame_to_obj(); self.set_char_collision(); self.draw_cols()
        f, a = C.frame, C.action
        kind = 'other'
        if f < 78 or f >= 80:
            if 137 <= f < 145: kind = 'floor'
            elif not (a in (A_HANG_CLIMB, A_MIDAIR, A_FREEFALL, A_HANG_STRAIGHT) or (a == A_BUMPED and 102 <= f <= 106)):
                return None
        def tilepos(col, row):
            if row < 0: return -(col + 1)
            if row >= 3 or col >= 10 or col < 0: return 30
            return row * 10 + col
        tiles = set()
        for col in range(self.char_col_right, self.char_col_left - 1, -1):
            if a != A_HANG_CLIMB: tiles.add(tilepos(col, self.char_bottom_row))
            if self.char_top_row != self.char_bottom_row: tiles.add(tilepos(col, self.char_top_row))
        if a == A_RUN_JUMP: row, col = self.char_bottom_row, self.char_col_left
        else: row, col = C.curr_row, C.curr_col
        if (135 <= f < 149) or a in (A_HANG_CLIMB, A_MIDAIR, A_FREEFALL, A_HANG_STRAIGHT): col -= 1
        obj = tilepos(col, row)
        if obj < 0: obj = 30
        return kind, tiles, obj

    # ---- object / collision geometry
    def load_frame_to_obj(self):
        self.load_frame(); C = self.Char
        img, sw, dx, dy, flags = self.cur_frame
        self.obj_direction = C.direction; self.obj_id = img
        self.obj_chtab = 2 + (sw >> 6)                          # 2 kid, 5 guard
        self.obj_x = (self.char_dx_forward(dx) << 1) - 116      # (int, may be negative)
        self.obj_y = dy + C.y
        if s8(flags ^ (C.direction & 0xFF)) >= 0: self.obj_x += 1
    def set_char_collision(self):
        wh = (self.img_wh if self.obj_chtab == 2 else self.guard_wh if self.obj_chtab == 5 else {}).get(self.obj_id)
        if wh is None or self.obj_id == 255: self.char_width_half = 0; self.char_height = 0
        else: self.char_width_half = (wh[0] + 1) // 2; self.char_height = wh[1]
        self.char_x_left = self.obj_x // 2 + 58       # C: int division truncates toward zero
        if self.obj_x < 0: self.char_x_left = -((-self.obj_x) // 2) + 58
        if self.Char.direction >= RIGHT: self.char_x_left -= self.char_width_half
        self.char_x_left_coll = self.char_x_left
        self.char_x_right_coll = self.char_x_right = self.char_x_left + self.char_width_half
        self.char_top_y = self.obj_y - self.char_height + 1
        if self.char_top_y >= 192: self.char_top_y = 0
        self.char_top_row = self.y_to_row_mod4(self.char_top_y)
        self.char_bottom_row = self.y_to_row_mod4(self.obj_y)
        if self.char_bottom_row == -1: self.char_bottom_row = 3
        self.char_col_left = max(self.get_tile_div_mod(self.char_x_left), 0)
        self.char_col_right = min(self.get_tile_div_mod(self.char_x_right), 9)
        if self.cur_frame[4] & FRAME_THIN:
            self.char_x_left_coll += 4; self.char_x_right_coll -= 4
    def check_collisions(self):
        C = self.Char
        self.bump_col_left_of_wall = self.bump_col_right_of_wall = -1
        if C.action == A_TURN: return
        self.collision_row = C.curr_row
        self.move_coll_to_prev()
        self.prev_collision_row = self.collision_row
        self.right_checked_col = min(self.get_tile_div_mod_m7(self.char_x_right_coll) + 2, 11)
        self.left_checked_col = self.get_tile_div_mod_m7(self.char_x_left_coll) - 1
        self.get_row_collision_data(self.collision_row, self.curr_row_coll_room, self.curr_row_coll_flags)
        self.get_row_collision_data(self.collision_row + 1, self.below_row_coll_room, self.below_row_coll_flags)
        self.get_row_collision_data(self.collision_row - 1, self.above_row_coll_room, self.above_row_coll_flags)
        for column in range(9, -1, -1):
            if self.curr_row_coll_room[column] >= 0 and self.prev_coll_room[column] == self.curr_row_coll_room[column]:
                if (self.prev_coll_flags[column] & 0x0F) == 0 and (self.curr_row_coll_flags[column] & 0x0F) != 0:
                    self.bump_col_left_of_wall = column
                if (self.prev_coll_flags[column] & 0xF0) == 0 and (self.curr_row_coll_flags[column] & 0xF0) != 0:
                    self.bump_col_right_of_wall = column
    def move_coll_to_prev(self):
        cr, pr = self.collision_row, self.prev_collision_row
        if cr == pr or cr + 3 == pr or cr - 3 == pr: src_r, src_f = self.curr_row_coll_room, self.curr_row_coll_flags
        elif cr + 1 == pr or cr - 2 == pr: src_r, src_f = self.above_row_coll_room, self.above_row_coll_flags
        else: src_r, src_f = self.below_row_coll_room, self.below_row_coll_flags
        for c in range(10):
            self.prev_coll_room[c] = src_r[c]; self.prev_coll_flags[c] = src_f[c]
            self.below_row_coll_room[c] = -1; self.above_row_coll_room[c] = -1; self.curr_row_coll_room[c] = -1
            self.curr_row_coll_flags[c] = 0; self.below_row_coll_flags[c] = 0; self.above_row_coll_flags[c] = 0   # FIX_COLL_FLAGS
    def get_row_collision_data(self, row, rooms, flags):
        room = self.Char.room
        self.coll_tile_left_xpos = X_BUMP[self.left_checked_col + FIRST_ONSCREEN_COLUMN] + TILE_MIDX
        for column in range(self.left_checked_col, self.right_checked_col + 1):
            lw = self.get_left_wall_xpos(room, column, row)
            rw = self.get_right_wall_xpos(room, column, row)
            f = (0x0F if lw < self.char_x_right_coll else 0) | (0xF0 if rw > self.char_x_left_coll else 0)
            flags[self.tile_col] = f; rooms[self.tile_col] = self.curr_room
            self.coll_tile_left_xpos += TILE_SIZEX
    def get_left_wall_xpos(self, room, column, row):
        t = self.wall_type(self.get_tile(room, column, row))
        return WALL_DIST_FROM_LEFT[t] + self.coll_tile_left_xpos if t else 0xFF
    def get_right_wall_xpos(self, room, column, row):
        t = self.wall_type(self.get_tile(room, column, row))
        return self.coll_tile_left_xpos - WALL_DIST_FROM_RIGHT[t] + TILE_RIGHTX if t else 0
    def check_bumped(self):
        C = self.Char
        if C.action not in (A_HANG_CLIMB, A_HANG_STRAIGHT) and (C.frame < 135 or C.frame >= 149):
            if self.bump_col_left_of_wall >= 0: self.check_bumped_look_right()
            elif self.bump_col_right_of_wall >= 0: self.check_bumped_look_left()
    def check_bumped_look_left(self):
        if (self.Char.sword == 2 or self.Char.direction < RIGHT) and self.is_obstacle_at_col(self.bump_col_right_of_wall):
            self.bumped(self.get_right_wall_xpos(self.curr_room, self.tile_col, self.tile_row) - self.char_x_left_coll, RIGHT)
    def check_bumped_look_right(self):
        if (self.Char.sword == 2 or self.Char.direction == RIGHT) and self.is_obstacle_at_col(self.bump_col_left_of_wall):
            self.bumped(self.get_left_wall_xpos(self.curr_room, self.tile_col, self.tile_row) - self.char_x_right_coll, LEFT)
    def is_obstacle_at_col(self, tile_col):
        tile_row = self.Char.curr_row
        if tile_row < 0: tile_row += 3
        if tile_row >= 3: tile_row -= 3
        self.get_tile(self.curr_row_coll_room[tile_col], tile_col, tile_row)
        return self.is_obstacle()
    def is_obstacle(self):
        t = self.curr_tile2
        if t == T.potion: return 0
        if t == T.gate and not self.can_bump_into_gate(): return 0
        if t == T.chomper and self.modif() != 2: return 0
        C = self.Char
        if t == T.mirror and C.charid == CHARID_KID and 39 <= C.frame < 44 and C.direction < RIGHT:   # run-jump, right to left
            self.set_mod(self.curr_room, self.curr_tilepos, 0x56); self.jumped_through_mirror = -1     # (broken mirror)
            return 0
        self.coll_tile_left_xpos = self.xpos_in_drawn_room(X_BUMP[self.tile_col + FIRST_ONSCREEN_COLUMN]) + TILE_MIDX
        return 1
    def xpos_in_drawn_room(self, xpos):
        if self.curr_room != self.drawn_room:
            L, R, U, D = self.links(self.drawn_room) if self.drawn_room else (0, 0, 0, 0)
            BL = self.links(D)[0] if D else 0; BR = self.links(D)[1] if D else 0
            if self.curr_room in (L, BL): xpos -= TILE_SIZEX * 10
            elif self.curr_room in (R, BR): xpos += TILE_SIZEX * 10
        return xpos
    def bumped(self, delta_x, push_direction):
        C = self.Char
        if C.alive < 0 and C.frame != 177:
            C.x = (C.x + delta_x) & 0xFF
            if push_direction < RIGHT:
                if self.curr_tile2 == T.wall:
                    self.tile_col -= 1; self.get_tile(self.curr_room, self.tile_col, self.tile_row)
            else:
                if self.curr_tile2 in (T.doortop, T.doortop_with_floor, T.wall):
                    self.tile_col += 1
                    if self.curr_room == 0 and self.tile_col == 10: self.curr_room = C.room; self.tile_col = 0
                    self.get_tile(self.curr_room, self.tile_col, self.tile_row)
            if self.tile_is_floor(self.curr_tile2): self.bumped_floor(push_direction)
            else: self.bumped_fall()
    def bumped_fall(self):
        C = self.Char; a = C.action
        C.x = self.char_dx_forward(-4)
        if a == A_FREEFALL: C.fall_x = 0
        else: self.seqtbl_offset_char(SEQ['bumpfall']); self.play_seq()
        self.bumped_sound()
    def bumped_floor(self, push_direction):
        C = self.Char
        if C.sword != SWORD_DRAWN and ((Y_LAND[C.curr_row + 1] - C.y) & 0xFFFF) >= 15: self.bumped_fall()
        else:
            C.y = Y_LAND[C.curr_row + 1]
            if C.fall_y >= 22: C.x = self.char_dx_forward(-5)
            else:
                C.fall_y = 0
                if C.alive:
                    if C.sword == SWORD_DRAWN:
                        if push_direction == C.direction:
                            self.seqtbl_offset_char(SEQ['bump_forward_with_sword']); self.play_seq()
                            C.x = self.char_dx_forward(1)
                            return
                        seq = SEQ['pushed_back_with_sword']
                    else:
                        f = C.frame
                        if f in (24, 25) or 40 <= f < 43 or 102 <= f < 107: seq = SEQ['hardbump']
                        else: seq = SEQ['bump']
                    self.seqtbl_offset_char(seq); self.play_seq()
                    self.bumped_sound()
    def bumped_sound(self):
        self.is_guard_notice = 1; self.play_sound(8)

    # ---- falling / floor
    def fall_accel(self):
        C = self.Char
        if C.action == A_FREEFALL:
            if self.is_feather_fall:                  # (any character: guards fall slowly too)
                C.fall_y += FALLING_SPEED_ACCEL_FEATHER
                if C.fall_y > FALLING_SPEED_MAX_FEATHER: C.fall_y = FALLING_SPEED_MAX_FEATHER
            else:
                C.fall_y += FALLING_SPEED_ACCEL
                if C.fall_y > FALLING_SPEED_MAX: C.fall_y = FALLING_SPEED_MAX
    def fall_speed(self):
        C = self.Char
        C.y = (C.y + C.fall_y) & 0xFF
        if C.action == A_FREEFALL:
            C.x = self.char_dx_forward(C.fall_x); self.load_fram_det_col()
    def check_action(self):
        C = self.Char; a = C.action; f = C.frame
        if a in (A_HANG_STRAIGHT, A_BUMPED):
            if f == 109: self.check_on_floor()
        elif a == A_FREEFALL: self.do_fall()
        elif a == A_MIDAIR:
            if 102 <= f < 106: self.check_grab()
        elif a != A_HANG_CLIMB: self.check_on_floor()
    def check_on_floor(self):
        if self.cur_frame[4] & FRAME_NEEDS_FLOOR:
            if self.get_tile_at_char() == T.wall: self.in_wall()
            if not self.tile_is_floor(self.curr_tile2):
                C = self.Char
                if (self.level.number == 12 and self.united_with_shadow < 0 and C.curr_row == 0 and
                        (C.room == 2 or (C.room == 13 and self.tile_col >= 6))):     # level 12: the hidden floors appear
                    self.set_tile(self.curr_room, self.curr_tilepos, T.floor)
                else: self.start_fall()
    def in_wall(self):
        d = self.distance_to_edge_weight()
        if d >= 8 or self.get_tile_infrontof_char() == T.wall: d = 6 - d
        else: d += 4
        self.Char.x = self.char_dx_forward(d); self.load_fram_det_col()
        self.get_tile_at_char()
    def start_fall(self):
        C = self.Char; f = C.frame
        C.sword = SWORD_SHEATHED; self.inc_curr_row(); self.start_chompers()
        self.fall_frame = f
        if f == 9: seq = SEQ['fall']
        elif f == 13: seq = SEQ['fall2']
        elif f == 26: seq = SEQ['fall_after_standing_jump']
        elif f == 44: seq = SEQ['fall_after_running_jump']
        elif 81 <= f < 86:
            seq = SEQ['fall2']; C.x = self.char_dx_forward(5); self.load_fram_det_col()
        elif 150 <= f < 180:                               # with sword (+ fall + dead)
            if C.charid == CHARID_GUARD:
                if C.curr_row == 3 and C.curr_col == 10: self.clear_char(); return
                if C.fall_x < 0:
                    seq = SEQ['guard_pushed_off_ledge']
                    if C.direction < RIGHT and self.distance_to_edge_weight() <= 7: C.x = self.char_dx_forward(-5)
                else:
                    self.droppedout = 0; seq = SEQ['guard_fall']
            else:
                self.droppedout = 1
                if C.direction < RIGHT and self.distance_to_edge_weight() <= 7: C.x = self.char_dx_forward(-5)
                seq = SEQ['kid_pushed_off_ledge']
        else: seq = SEQ['fall']
        self.seqtbl_offset_char(seq); self.play_seq()
        self.load_fram_det_col()
        if self.get_tile_at_char() == T.wall: self.in_wall(); return
        if self.get_tile_infrontof_char() == T.wall:
            if self.fall_frame != 44 or self.distance_to_edge_weight() >= 6: C.x = self.char_dx_forward(-1)
            else: self.seqtbl_offset_char(SEQ['start_fall_in_front_of_wall']); self.play_seq()
            self.load_fram_det_col()
    def do_fall(self):
        C = self.Char
        if self.is_screaming == 0 and C.fall_y >= 31: self.play_sound(1); self.is_screaming = 1
        if (Y_LAND[C.curr_row + 1] & 0xFFFF) > C.y: self.check_grab()
        else:
            if self.get_tile_at_char() == T.wall: self.in_wall()
            if self.tile_is_floor(self.curr_tile2): self.land()
            else: self.inc_curr_row()
    def is_spike_harmful(self):
        m = s8(self.mod_at(self.curr_room, self.curr_tilepos)) if self.curr_room else 0
        if m == 0 or m == -1: return 0
        if m < 0: return 1
        if m < 5: return 2
        return 0
    def spiked(self):
        C = self.Char
        self.set_mod(self.curr_room, self.curr_tilepos, 0xFF)
        C.y = Y_LAND[C.curr_row + 1]
        C.x = (X_BUMP[self.tile_col + FIRST_ONSCREEN_COLUMN] + 10) & 0xFF
        C.x = self.char_dx_forward(8); C.fall_y = 0
        self.play_sound(48)
        self.take_hp(100)
        self.seqtbl_offset_char(SEQ['spiked']); self.play_seq()
    def land(self):
        C = self.Char
        self.is_screaming = 0
        C.y = Y_LAND[C.curr_row + 1]
        # (C: gotos between the branches; 'go' names the label reached)
        if self.get_tile_at_char() != T.spike:
            if not self.tile_is_floor(self.get_tile_infrontof_char()) and self.distance_to_edge_weight() < 3:
                C.x = self.char_dx_forward(-3)
            self.start_chompers()
            if C.alive < 0:
                if ((self.distance_to_edge_weight() >= 12 and self.get_tile_behind_char() == T.spike) or
                        self.get_tile_at_char() == T.spike): go = 'spikes'
                else: go = 'alive'
            else: go = 'dead'
        else: go = 'spikes'                       # (fell on spikes: even when already dead)
        if go == 'spikes':
            if self.is_spike_harmful(): self.spiked(); return
            go = 'alive'
        if go == 'alive':
            if C.fall_y < 22: go = 'soft'                         # fell 1 row
            elif C.fall_y < 33:                                   # fell 2 rows
                if C.charid == CHARID_SHADOW: go = 'soft'
                elif C.charid == CHARID_GUARD: go = 'dead'
                elif not self.take_hp(1):                         # kid (or skeleton (bug!))
                    self.play_sound(16); self.is_guard_notice = 1; seq = SEQ['medium_land']
                else: go = 'crushed'
            else: go = 'dead'                                     # fell 3 or more rows
        if go == 'soft':
            if C.charid >= CHARID_GUARD or C.sword == SWORD_DRAWN:
                C.sword = SWORD_DRAWN; seq = SEQ['guard_active_after_fall']
            else: seq = SEQ['soft_land']
            if C.charid == CHARID_KID: self.play_sound(17); self.is_guard_notice = 1
        if go == 'dead': self.take_hp(100); go = 'crushed'
        if go == 'crushed': self.play_sound(0); seq = SEQ['crushed']
        self.seqtbl_offset_char(seq); self.play_seq(); C.fall_y = 0
    def check_spiked(self):
        C = self.Char; f = C.frame
        if self.get_tile(C.room, C.curr_col, C.curr_row) == T.spike:
            h = self.is_spike_harmful()
            if (h >= 2 and (7 <= f < 15 or 34 <= f < 40)) or (f in (43, 26) and h != 0): self.spiked()
    def check_gate_push(self):
        """A closing gate pushes a standing, turning or crouching kid out of its tile."""
        C = self.Char; f = C.frame
        if C.action == A_TURN or f == 15 or 108 <= f < 111:
            self.get_tile_at_char()
            orig_col = self.tile_col
            if ((self.curr_tile2 == T.gate or self.get_tile(self.curr_room, self.tile_col - 1, self.tile_row) == T.gate) and
                    (self.curr_row_coll_flags[self.tile_col] & self.prev_coll_flags[self.tile_col]) == 0xFF and
                    self.can_bump_into_gate()):
                self.gate_pushes += 1; self.bumped_sound()
                C.x = (C.x + 5 - (10 if orig_col <= self.tile_col else 0)) & 0xFF
    def check_chomped_kid(self):
        C = self.Char
        for col in range(10):
            if (self.curr_row_coll_flags[col] == 0xFF and self.get_tile(self.curr_row_coll_room[col], col, C.curr_row) == T.chomper
                    and (self.modif() & 0x7F) == 2):           # a closed chomper
                self.chomped()
    def chomped(self):
        C = self.Char
        if self.curr_room > 0: self.level.bg[(self.curr_room - 1) * 30 + self.curr_tilepos] |= 0x80   # blood
        if C.frame != 178 and C.room == self.curr_room:
            C.x = X_BUMP[self.tile_col + FIRST_ONSCREEN_COLUMN] + TILE_MIDX
            C.x = self.char_dx_forward(7 - (1 if C.direction == 0 else 0))
            C.y = Y_LAND[C.curr_row + 1]
            self.take_hp(100)
            self.play_sound(46)
            self.seqtbl_offset_char(SEQ['chomped'])
            self.play_seq()
    def check_spike_below(self):
        C = self.Char
        right_col = self.get_tile_div_mod_m7(self.char_x_right)
        if right_col < 0: return
        room = C.room
        for col in range(self.get_tile_div_mod_m7(self.char_x_left), right_col + 1):
            row = C.curr_row
            while True:
                if self.get_tile(room, col, row) == T.spike: self.start_anim_spike(self.curr_room, self.curr_tilepos); break
                elif not self.tile_is_floor(self.curr_tile2) and self.curr_room != 0 and room == self.curr_room: row += 1
                else: break
    def check_press(self):
        C = self.Char; f = C.frame; a = C.action
        if 87 <= f < 100 or 135 <= f < 141: self.get_tile_above_char()
        elif a == A_TURN or a == A_BUMPED or a < A_HANG_CLIMB:
            if f == 79 and self.get_tile_above_char() == T.loose: self.make_loose_fall(1); return
            if not (self.cur_frame[4] & FRAME_NEEDS_FLOOR): return
            self.get_tile_at_char()
        else: return
        if self.curr_tile2 in (T.opener, T.closer):
            if C.alive < 0: self.trigger_button(1, 0, -1)
            else: self.died_on_button()
        elif self.curr_tile2 == T.loose: self.is_guard_notice = 1; self.make_loose_fall(1)
    def check_knock(self):
        if self.knock: self.do_knock(self.Char.room, self.Char.curr_row - (1 if self.knock > 0 else 0)); self.knock = 0
    # ---- items
    def check_get_item(self):
        if self.get_tile_at_char() == T.potion or self.curr_tile2 == T.sword:
            if not self.tile_is_floor(self.get_tile_behind_char()): return 0
            self.Char.x = self.char_dx_forward(-14); self.load_fram_det_col()
        if self.get_tile_infrontof_char() == T.potion or self.curr_tile2 == T.sword: self.get_item(); return 1
        return 0
    def get_item(self):
        C = self.Char
        if C.frame != 109:
            d = self.get_edge_distance()
            if self.edge_type != EDGE_FLOOR: C.x = self.char_dx_forward(d)
            if C.direction >= RIGHT: C.x = self.char_dx_forward((1 if self.curr_tile2 == T.potion else 0) - 2)
            self.crouch()
        elif self.curr_tile2 == T.sword: self.do_pickup(-1); self.seqtbl_offset_char(SEQ['get_sword'])
        else: self.do_pickup(self.mod_at(self.curr_room, self.curr_tilepos) >> 3); self.seqtbl_offset_char(SEQ['drink'])
    def do_pickup(self, t):
        self.pickup_obj_type = t; self.control_shift2 = IGNORE
        self.set_tile(self.curr_room, self.curr_tilepos, T.floor); self.set_mod(self.curr_room, self.curr_tilepos, 0)
    def proc_get_object(self):
        t = self.pickup_obj_type
        if self.Char.charid != CHARID_KID or t == 0: return
        if t == -1:
            self.have_sword = -1; self.play_sound(37); self.flash_color = COLOR_BRIGHTYELLOW; self.flash_time = 8
        elif t == 1:                                        # health
            if self.hitp_curr != self.hitp_max:
                self.stop_sounds(); self.play_sound(33); self.hitp_delta = 1; self.flash_color = COLOR_RED; self.flash_time = 2
        elif t == 2:                                        # life
            self.stop_sounds(); self.play_sound(30); self.flash_color = COLOR_RED; self.flash_time = 4; self.add_life()
        elif t == 3: self.feather_fall()                    # feather
        elif t == 4: self.toggle_upside()                   # upside down
        elif t == 6: self.get_tile(8, 0, 0); self.trigger_button(0, 0, -1)     # open
        elif t == 5:                                        # hurt (potions level 15: half the hit points)
            self.stop_sounds(); self.play_sound(13)
            self.hitp_delta = -((self.hitp_max + 1) >> 1) if self.level.number == 15 else -1
    def add_life(self):
        self.hitp_max = min(self.hitp_max + 1, 10); self.set_health_life()
    def set_health_life(self): self.hitp_delta = self.hitp_max - self.hitp_curr
    def feather_fall(self):
        self.is_feather_fall = 1
        self.flash_color = COLOR_GREEN; self.flash_time = 3
        self.stop_sounds(); self.play_sound(39)
        self.feather_music = 1                              # (silent: the feather fall wait, see timers)
    def toggle_upside(self):
        """The screen is drawn upside down (drawing only: the controls are not swapped)."""
        self.upside_down = ~self.upside_down & 0xFFFF
    # ---- the sound model (SDLPoP seg000 play_sound / play_next_sound, seg009 stop_sounds / check_sound_playing)
    # Every mode runs the request side: play_sound keeps the tick's highest-priority request (next_sound), play_next_sound
    # (draw_game_frame) starts it when nothing plays or the playing sound is interruptible and not of higher priority,
    # stop_sounds ends the playing sound. Modes (sound_playing, i.e. check_sound_playing):
    #   silent  every sound has length 0: nothing ever plays (the harness and every oracle test). The waits keep the
    #           behaviour they had before the model: the feather fall music (feather_music) lasts until the 225-tick cap
    #           or a stop_sounds, the death timer never waits, a level door exit keeps the level (its music never ends).
    #   ticks   a sound plays for its length (SOUND_SECONDS) in game ticks at the tick rate it starts at (12/s, 10/s with
    #           the kid's sword drawn), counted down at each tick start.
    #   hybrid  the release (docs/m7-design.md D4): ticks, except the live waits (LIVE_WAITS: death, level end) which ask
    #           the player (live_playing; kidsim: the ticks model).
    # The waits (M7 step 5) ask sound_playing(wait) in the ticks and hybrid modes: the feather fall (timers), the level 1
    # crouch (control_crouched), the death timer (play_kid), the level end (step; any sound, as SDLPoP's check). Hybrid:
    # the level end's clock is charged what the ticks model would have counted (step: end_over, level_end_charge), so
    # the time left at the next level is the ticks mode's whatever the live wait took. The 'N' trace line (sound_line,
    # per draw_game_frame): queued started playing stops (pop800_trace_sound).
    def play_sound(self, sid):
        if self.next_sound < 0 or SOUND_PRIO[sid] <= SOUND_PRIO[self.next_sound]:
            if sid in SOUND_MISSING: return
            self.next_sound = sid
    def sound_playing(self, wait=None):
        """check_sound_playing; wait names the logic wait that asks (hybrid: LIVE_WAITS ask the player)"""
        if self.sound_mode == 'silent': return 0
        if self.sound_mode == 'hybrid' and wait in LIVE_WAITS and self.live_playing: return 1 if self.live_playing() else 0
        return 1 if self.snd_left > 0 else 0
    def sound_ticks(self, sid):
        rate = 10 if self.Kid.sword == SWORD_DRAWN else 12
        n = -int(-SOUND_SECONDS[sid] * rate // 1)               # (rounded up)
        return max(n, SOUND_TICKS_MIN.get(sid, 0)) if rate == 12 else n
    @staticmethod
    def sound_ticks_tables():
        """the ticks model's lengths per id at 12 and at 10 ticks a second (the Z80's tables, the SDLPoP hook's)"""
        t12 = [max(-int(-s * 12 // 1), SOUND_TICKS_MIN.get(i, 0)) for i, s in enumerate(SOUND_SECONDS)]
        t10 = [-int(-s * 10 // 1) for s in SOUND_SECONDS]
        return t12, t10
    def play_next_sound(self):
        q = self.next_sound; p = self.sound_playing(); st = -1
        if q >= 0 and (not p or (self.snd_interruptible[self.current_sound] and SOUND_PRIO[q] <= SOUND_PRIO[self.current_sound])):
            self.current_sound = st = q
            self.snd_left = self.sound_ticks(q)
        self.next_sound = -1
        self.sound_line = 'N %d %d %d %d' % (q, st, p, self.snd_stops); self.snd_stops = 0
    def sound_tick(self):
        """the ticks model's clock: one game tick passed"""
        if self.snd_left > 0: self.snd_left -= 1
    def stop_sounds(self):
        self.snd_stops += 1; self.snd_left = 0
        self.feather_music = 0            # (silent: the feather fall wait)
        self.end_music = 0                # (silent: the level end wait)
    def check_grab(self):
        C = self.Char
        if self.control_shift == HELD and C.fall_y < 32 and C.alive < 0 and (Y_LAND[C.curr_row + 1] & 0xFFFF) <= ((C.y + 25) & 0xFFFF):
            old_x = C.x
            C.x = self.char_dx_forward(-8); self.load_fram_det_col()
            if not self.can_grab_front_above(): C.x = old_x
            else:
                C.x = self.char_dx_forward(self.distance_to_edge_weight())
                C.y = Y_LAND[C.curr_row + 1]; C.fall_y = 0
                self.seqtbl_offset_char(SEQ['grab_ledge_midair']); self.play_seq()
                self.grab_timer = 12
                self.play_sound(9); self.is_screaming = 0

    # ---- characters (seg006): Char is the one being played, Opp a copy of the other one
    def loadkid(self): self.Char = self.Kid.copy()
    def savekid(self): self.Kid = self.Char.copy()
    def loadshad(self): self.Char = self.Guard.copy()
    def saveshad(self): self.Guard = self.Char.copy()
    def loadkid_and_opp(self): self.loadkid(); self.Opp = self.Guard.copy()
    def savekid_and_opp(self): self.savekid(); self.Guard = self.Opp.copy()
    def loadshad_and_opp(self): self.loadshad(); self.Opp = self.Kid.copy()
    def saveshad_and_opp(self): self.saveshad(); self.Kid = self.Opp.copy()
    def inc_curr_row(self): self.Char.curr_row += 1
    def char_opp_dist(self):
        """> 0 if Opp is in front of Char, < 0 if behind (999: other room)"""
        C, O = self.Char, self.Opp
        if C.room != O.room: return 999
        distance = O.x - C.x
        if C.direction < RIGHT: distance = -distance
        if distance >= 0 and C.direction != O.direction: distance += 13
        return distance
    def get_tile_infrontof2_char(self):
        self.infrontx = (self.dir_front() << 1) + self.Char.curr_col
        return self.get_tile(self.Char.room, self.infrontx, self.Char.curr_row)
    @staticmethod
    def get_tilepos(col, row):
        if row < 0: return -(col + 1)
        if row >= 3 or col >= 10 or col < 0: return 30
        return TBL_LINE[row] + col
    def is_dead(self):
        f = self.Char.frame
        return f >= 177 and (f <= 178 or f == 185)        # spiked, chomped, dead
    def clear_char(self):
        C = self.Char
        C.direction = DIR_NONE; C.alive = 0; C.action = 0
        self.guardhp_curr = 0
    def on_guard_killed(self):
        if self.level.number == 0: self.checkpoint = 1; self.demo_index = self.demo_time = 0   # demo level: run out of the room
        elif self.level.number == 13:                                   # Jaffar killed: flash, show the time, open the door
            self.flash_color = COLOR_BRIGHTWHITE; self.flash_time = 18; self.is_show_time = 1; self.leveldoor_open = 2
            self.play_sound(43)
        elif self.Char.charid != CHARID_SHADOW: self.play_sound(37)
    def check_killed_shadow(self):
        """level 12: killing the shadow kills the kid"""
        if self.level.number == 12:
            C, O = self.Char, self.Opp
            if (C.charid | O.charid) == CHARID_SHADOW and C.alive < 0 and O.alive >= 0:
                self.flash_color = COLOR_BRIGHTWHITE; self.flash_time = 5; self.take_hp(100)
    def timers(self):
        if self.united_with_shadow > 0:
            self.united_with_shadow -= 1
            if self.united_with_shadow == 0: self.united_with_shadow -= 1
        if self.guard_notice_timer > 0: self.guard_notice_timer -= 1
        # feather fall: ends when no sound plays (check_sound_playing) or after FEATHER_MAX ticks. Silent model: the
        # music outlasts the 225 ticks and nothing interrupts it, only stop_sounds() (potions, level door, restart);
        # ticks / hybrid: the ticks model (the music lasts the cap: SOUND_TICKS_MIN)
        if self.is_feather_fall: self.is_feather_fall += 1
        playing = self.feather_music if self.sound_mode == 'silent' else self.sound_playing('feather')
        if self.is_feather_fall and (not playing or self.is_feather_fall > FEATHER_MAX):
            self.is_feather_fall = 0; self.feather_music = 0
        if self.level.number == 8 and self.Char.room == 16 and self.leveldoor_open:     # the mouse
            self.leveldoor_open += 1
            if self.leveldoor_open == 150: self.do_mouse()
    def do_mouse(self):
        self.loadkid(); C = self.Char
        C.charid = CHARID_MOUSE; C.x = 200; C.curr_row = 0; C.y = Y_LAND[C.curr_row + 1]; C.alive = -1; C.direction = LEFT
        self.guardhp_curr = 1
        self.seqtbl_offset_char(SEQ['mouse_forward']); self.play_seq()
        self.saveshad()

    # ---- guards entering and leaving rooms (seg002, seg003)
    def pos_guards(self):
        L = self.level
        for room1 in range(24):
            t = L.guards_tile[room1]
            if t < 30:
                L.guards_x[room1] = X_BUMP[(t % 10) + FIRST_ONSCREEN_COLUMN] + TILE_SIZEX
                L.guards_seq_hi[room1] = 0
    def get_guard_hp(self):
        self.guardhp_delta = self.guardhp_curr = self.guardhp_max = EXTRASTRENGTH[self.guard_skill] + TBL_GUARD_HP[self.level.number]
    def do_init_shad(self, source, seq_index):
        C = self.Char
        C.frame, C.x, C.y, C.direction, C.curr_col, C.curr_row, C.action = source
        self.seqtbl_offset_char(seq_index)
        C.charid = CHARID_SHADOW
        self.demo_time = 0
        self.guard_skill = 3
        self.guardhp_delta = self.guardhp_curr = self.guardhp_max = 4
        self.saveshad()
    def check_shadow(self):
        """the room's guard (or the shadow on levels 5, 6 and 12) enters the drawn room"""
        self.offguard = 0
        lv = self.level.number; C = self.Char
        if lv == 12 and not self.united_with_shadow and self.drawn_room == 15:
            C.room = self.drawn_room
            if self.get_tile(15, 1, 0) == T.sword: return
            self.shadow_initialized = 0
            self.do_init_shad(INIT_SHAD_12, SEQ['fall']); return
        if lv == 6:
            C.room = self.drawn_room
            if C.room == 1:
                if self.leveldoor_open != 0x4D: self.play_sound(25)
                self.leveldoor_open = 0x4D
                self.do_init_shad(INIT_SHAD_6, SEQ['stand']); return
        if lv == 5:
            C.room = self.drawn_room
            if C.room == 24:
                if self.get_tile(24, 3, 0) != T.potion: return
                self.do_init_shad(INIT_SHAD_5, SEQ['stand']); return
        self.enter_guard()
    def enter_guard(self):
        L = self.level; C = self.Char
        rm1 = self.drawn_room - 1
        guard_tile = L.guards_tile[rm1]
        if guard_tile >= 30: return
        C.room = self.drawn_room
        C.curr_row = guard_tile // 10
        C.y = Y_LAND[C.curr_row + 1]
        C.x = L.guards_x[rm1]
        C.curr_col = self.get_tile_div_mod_m7(C.x)
        C.direction = s8(L.guards_dir[rm1])
        self.curr_guard_color = L.guards_color[rm1] if TBL_GUARD_TYPE[L.number] == 0 else 0   # (VGA)
        self.curr_guard_color &= 0x0F
        C.charid = CHARID_SKELETON if TBL_GUARD_TYPE[L.number] == 2 else CHARID_GUARD
        seq_hi = L.guards_seq_hi[rm1]
        if seq_hi == 0:
            if C.charid == CHARID_SKELETON:
                C.sword = SWORD_DRAWN; self.seqtbl_offset_char(SEQ['guard_active_after_fall'])
            else:
                C.sword = SWORD_SHEATHED; self.seqtbl_offset_char(SEQ['guard_stand_inactive'])
        else:
            C.curr_seq = L.guards_seq_lo[rm1] + (seq_hi << 8) - SEQ_BASE
        self.play_seq()
        self.guard_skill = L.guards_skill[rm1]
        if self.guard_skill >= NUM_GUARD_SKILLS: self.guard_skill = 3
        if C.frame in (185, 177, 178):                      # dead
            C.alive = 1
            self.guardhp_curr = 0
        else:
            C.alive = -1
            self.justblocked = 0; self.guard_refrac = 0; self.is_guard_notice = 0
            self.get_guard_hp()
        C.fall_y = 0; C.fall_x = 0
        C.action = A_RUN_JUMP
        self.saveshad()
    def check_guard_fallout(self):
        G = self.Guard; L = self.level
        if G.direction == DIR_NONE or G.y < 211: return
        if G.charid == CHARID_SHADOW:
            if G.action != A_FREEFALL: return
            self.loadshad(); self.clear_char(); self.saveshad()
        elif G.charid == CHARID_SKELETON and self.links(G.room)[3] == 3:
            # the skeleton falls down into room 3 (level 3) and comes back there
            G.room = self.links(G.room)[3]
            G.x = 133; G.curr_row = 1; G.direction = RIGHT; G.alive = -1
            self.leave_guard()
        else:
            self.on_guard_killed()
            L.guards_tile[self.drawn_room - 1] = 0xFF
            G.direction = DIR_NONE
            self.guardhp_curr = 0
    def leave_guard(self):
        G = self.Guard; L = self.level
        if G.direction == DIR_NONE or G.charid in (CHARID_SHADOW, CHARID_MOUSE): return
        rm1 = G.room - 1
        if rm1 >= 0:            # (C: room 0 would write in front of the arrays)
            L.guards_tile[rm1] = self.get_tilepos(0, G.curr_row) & 0xFF
            L.guards_color[rm1] = self.curr_guard_color & 0x0F
            L.guards_x[rm1] = G.x & 0xFF
            L.guards_dir[rm1] = G.direction & 0xFF
            L.guards_skill[rm1] = self.guard_skill
            if G.alive < 0: L.guards_seq_hi[rm1] = 0
            else:
                seq = (G.curr_seq + SEQ_BASE) & 0xFFFF
                L.guards_seq_lo[rm1] = seq & 0xFF; L.guards_seq_hi[rm1] = seq >> 8
        G.direction = DIR_NONE
        self.guardhp_curr = 0
    def follow_guard(self):
        L = self.level
        L.guards_tile[self.Kid.room - 1] = 0xFF
        L.guards_tile[self.Guard.room - 1] = 0xFF
        self.loadshad(); self.goto_other_room(self.roomleave_result); self.saveshad()
    def check_skel(self):
        """level 3: the skeleton wakes up when the kid comes near it (the level door open)"""
        if (self.level.number == 3 and self.Guard.direction == DIR_NONE and self.drawn_room == 1 and
                self.leveldoor_open != 0 and self.Kid.curr_col in (2, 3)):
            self.get_tile(self.drawn_room, 5, 1)
            if self.curr_tile2 == T.skeleton:
                self.set_tile(self.curr_room, self.curr_tilepos, T.floor)
                C = self.Char
                C.room = self.drawn_room; C.curr_row = 1; C.y = Y_LAND[C.curr_row + 1]; C.curr_col = 5
                C.x = X_BUMP[C.curr_col + FIRST_ONSCREEN_COLUMN] + TILE_SIZEX
                C.direction = LEFT
                self.seqtbl_offset_char(SEQ['skel_wake_up']); self.play_seq()
                self.play_sound(44)
                self.guard_skill = 2
                C.alive = -1
                self.guardhp_max = self.guardhp_curr = 3
                C.fall_x = C.fall_y = 0
                self.is_guard_notice = self.guard_refrac = 0
                C.sword = SWORD_DRAWN; C.charid = CHARID_SKELETON
                self.saveshad()
    def check_fall_flo(self):
        """level 13: the loose floors above start falling"""
        if self.level.number == 13 and self.drawn_room in (23, 16):
            self.curr_room = self.links(self.drawn_room)[2]
            for self.curr_tilepos in range(22, 28):
                self.make_loose_fall((-(self.prandom(0xFF) & 0x0F)) & 0xFF)

    # ---- seeing and bumping (seg003)
    def check_can_guard_see_kid(self):
        """0: the guard can't see the kid, 1: sees him but won't come, 2: sees him and will come"""
        K, G = self.Kid, self.Guard; kid_frame = K.frame
        if G.charid == CHARID_MOUSE: self.can_guard_see_kid = 0; return
        if ((G.charid != CHARID_SHADOW or self.level.number == 12) and kid_frame != 0 and (kid_frame < 219 or kid_frame >= 229) and
                G.direction != DIR_NONE and K.alive < 0 and G.alive < 0 and K.room == G.room and K.curr_row == G.curr_row):
            self.can_guard_see_kid = 2
            left_pos = X_BUMP[K.curr_col + FIRST_ONSCREEN_COLUMN] + TILE_MIDX
            right_pos = X_BUMP[G.curr_col + FIRST_ONSCREEN_COLUMN] + TILE_MIDX
            if left_pos > right_pos: left_pos, right_pos = right_pos, left_pos
            if self.get_tile_at_kid(left_pos) == T.chomper: left_pos += TILE_SIZEX     # (a chomper is on a tile's left)
            if self.get_tile_at_kid(right_pos) == T.gate: right_pos -= TILE_SIZEX      # (a gate is on a tile's right)
            if right_pos >= left_pos:
                while left_pos <= right_pos:
                    if self.get_tile_at_kid(left_pos) == T.wall or self.curr_tile2 in (T.doortop_with_floor, T.doortop):
                        self.can_guard_see_kid = 0; return
                    t = self.curr_tile2
                    if t in (T.loose, T.chomper) or (t == T.gate and self.modif() < 112) or not self.tile_is_floor(t):
                        self.can_guard_see_kid = 1
                    left_pos += TILE_SIZEX
        else: self.can_guard_see_kid = 0
    def get_tile_at_kid(self, xpos):
        return self.get_tile(self.Kid.room, self.get_tile_div_mod_m7(xpos), self.Kid.curr_row)
    def bump_into_opponent(self):
        """(char = Kid, Opp = Guard) an unarmed kid bumps into an armed guard he faces"""
        C, O = self.Char, self.Opp
        if (self.can_guard_see_kid >= 2 and C.sword == SWORD_SHEATHED and O.sword != SWORD_SHEATHED and O.action < 2 and
                C.direction != O.direction):
            distance = self.char_opp_dist()
            if abs(distance) <= 15:
                C.y = Y_LAND[C.curr_row + 1]; C.fall_y = 0
                self.seqtbl_offset_char(SEQ['bump']); self.play_seq()

    # ---- guard collisions (seg004)
    def check_guard_bumped(self):
        C = self.Char
        if C.action == A_RUN_JUMP and C.alive < 0 and C.sword >= SWORD_DRAWN:
            if (self.get_tile_at_char() == T.wall or self.curr_tile2 == T.doortop_with_floor or
                    (self.curr_tile2 == T.gate and self.can_bump_into_gate()) or
                    (C.direction >= RIGHT and (self.get_tile(self.curr_room, self.tile_col - 1, self.tile_row) == T.doortop_with_floor or
                                               (self.curr_tile2 == T.gate and self.can_bump_into_gate())))):
                self.load_frame_to_obj(); self.set_char_collision()
                if self.is_obstacle():
                    delta_x = self.dist_from_wall_behind(self.curr_tile2)
                    if -13 < delta_x < 0:
                        C.x = self.char_dx_forward(-delta_x)
                        self.seqtbl_offset_char(SEQ['bump_forward_with_sword']); self.play_seq()
                        self.load_fram_det_col()
    def dist_from_wall_behind(self, tiletype):
        wt = self.wall_type(tiletype)
        if wt == 0: return 99
        if self.Char.direction >= RIGHT:
            return self.char_x_left_coll - (self.coll_tile_left_xpos + TILE_RIGHTX - WALL_DIST_FROM_RIGHT[wt])
        return WALL_DIST_FROM_LEFT[wt] + self.coll_tile_left_xpos - self.char_x_right_coll
    def check_chomped_guard(self):
        self.get_tile_at_char()
        if not self.check_chomped_here():
            self.get_tile(self.curr_room, self.tile_col + 1, self.tile_row)
            self.check_chomped_here()
    def check_chomped_here(self):
        if self.curr_tile2 == T.chomper and (self.modif() & 0x7F) == 2:
            self.coll_tile_left_xpos = X_BUMP[self.tile_col + FIRST_ONSCREEN_COLUMN] + TILE_MIDX
            if (self.get_left_wall_xpos(self.curr_room, self.tile_col, self.tile_row) < self.char_x_right_coll and
                    self.get_right_wall_xpos(self.curr_room, self.tile_col, self.tile_row) > self.char_x_left_coll):
                self.chomped(); return 1
        return 0

    # ---- guard AI (seg002)
    def move_0_nothing(self):
        self.control_shift = self.control_y = self.control_x = self.control_shift2 = RELEASED
        self.control_down = self.control_up = self.control_backward = self.control_forward = RELEASED
    def move_1_forward(self): self.control_x = X_FORWARD; self.control_forward = HELD
    def move_2_backward(self): self.control_backward = HELD; self.control_x = X_BACKWARD
    def move_3_up(self): self.control_y = Y_UP; self.control_up = HELD
    def move_4_down(self): self.control_down = HELD; self.control_y = Y_DOWN
    def move_up_back(self): self.control_up = HELD; self.move_2_backward()
    def move_down_back(self): self.control_down = HELD; self.move_2_backward()
    def move_down_forw(self): self.control_down = HELD; self.move_1_forward()
    def move_6_shift(self): self.control_shift = HELD; self.control_shift2 = HELD
    def move_7(self): self.control_shift = RELEASED
    def autocontrol_opponent(self):
        self.move_0_nothing()
        charid = self.Char.charid
        if charid == CHARID_KID: self.autocontrol_kid()
        else:
            if self.justblocked: self.justblocked -= 1
            if self.kid_sword_strike: self.kid_sword_strike -= 1
            if self.guard_refrac: self.guard_refrac -= 1
            if charid == CHARID_MOUSE: self.autocontrol_mouse()
            elif charid == CHARID_SKELETON: self.autocontrol_skeleton()
            elif charid == CHARID_SHADOW: self.autocontrol_shadow()
            elif self.level.number == 13: self.autocontrol_Jaffar()
            else: self.autocontrol_guard()
    def autocontrol_mouse(self):
        C = self.Char
        if C.direction == DIR_NONE: return
        if C.action == A_STAND:
            if C.x >= 200: self.clear_char()
        elif C.x < 166:
            self.seqtbl_offset_char(SEQ['mouse_stand_up_and_go']); self.play_seq()
    def autocontrol_shadow(self):
        lv = self.level.number
        if lv == 4: self.autocontrol_shadow_level4()
        if lv == 5: self.autocontrol_shadow_level5()
        if lv == 6: self.autocontrol_shadow_level6()
        if lv == 12: self.autocontrol_shadow_level12()
    def do_auto_moves(self, moves):
        if self.demo_time >= 0xFE: return
        self.demo_time += 1
        demoindex = self.demo_index
        if moves[demoindex][0] <= self.demo_time: self.demo_index += 1
        else: demoindex = self.demo_index - 1
        m = moves[demoindex][1]
        if m == 0: self.move_0_nothing()
        elif m == 1: self.move_1_forward()
        elif m == 2: self.move_2_backward()
        elif m == 3: self.move_3_up()
        elif m == 4: self.move_4_down()
        elif m == 5: self.move_3_up(); self.move_1_forward()
        elif m == 6: self.move_6_shift()
        elif m == 7: self.move_7()
    def autocontrol_shadow_level4(self):
        """level 4: the shadow out of the mirror runs left and vanishes"""
        C = self.Char
        if C.room == 4:
            if C.x < 80: self.clear_char()
            else: self.move_1_forward()
    def autocontrol_shadow_level5(self):
        """level 5: once the gate is open the shadow drinks the potion and runs away"""
        C = self.Char
        if C.room == 24:
            if self.demo_time == 0:
                self.get_tile(24, 1, 0)
                if self.mod_at(self.curr_room, self.curr_tilepos) < 80: return      # the gate is not open yet
                self.demo_index = 0
            self.do_auto_moves(SHAD_DRINK_MOVE)
            if C.x < 15: self.clear_char()
    def autocontrol_shadow_level6(self):
        """level 6: the shadow steps forward when the kid run-jumps"""
        if self.Char.room == 1 and self.Kid.frame == 43 and self.Kid.x < 128:
            self.move_6_shift(); self.move_1_forward()
    def autocontrol_shadow_level12(self):
        """level 12: the shadow fights the kid; when the kid sheathes his sword and walks into it, they unite"""
        C, O = self.Char, self.Opp
        if C.room == 15 and self.shadow_initialized == 0:
            if O.x >= 150:
                self.do_init_shad(INIT_SHAD_12, SEQ['fall']); return
            self.shadow_initialized = 1
        if C.sword >= SWORD_DRAWN:
            if self.offguard == 0 or self.guard_refrac == 0: self.autocontrol_guard_active()
            else: self.move_4_down()
            return
        if O.sword >= SWORD_DRAWN or self.offguard == 0:
            xdiff = 0x7000
            if self.can_guard_see_kid < 2 or (xdiff := self.char_opp_dist()) >= 90:
                if xdiff < 0: self.move_2_backward()
                return
            if C.frame == 15: self.move_down_forw()             # the shadow draws his sword
            return
        if self.char_opp_dist() < 10:                           # unite with the shadow
            self.flash_color = COLOR_BRIGHTWHITE; self.flash_time = 18
            self.add_life()
            self.united_with_shadow = 42
            C.charid = CHARID_KID; self.savekid()               # (the kid stands where the shadow was)
            self.clear_char()
            return
        if self.can_guard_see_kid == 2:                         # the kid runs to the shadow: the shadow runs to him
            f = O.frame
            if 3 <= f < 15 or 127 <= f < 133: self.move_1_forward()
    def autocontrol_skeleton(self): self.Char.sword = SWORD_DRAWN; self.autocontrol_guard()
    def autocontrol_Jaffar(self): self.autocontrol_guard()
    def autocontrol_kid(self): self.autocontrol_guard()
    def autocontrol_guard(self):
        if self.Char.sword < SWORD_DRAWN: self.autocontrol_guard_inactive()
        else: self.autocontrol_guard_active()
    def autocontrol_guard_inactive(self):
        C, O = self.Char, self.Opp
        if self.Kid.alive >= 0: return
        distance = self.char_opp_dist()
        if O.curr_row != C.curr_row or (distance & 0xFFFF) < 0xFFF8:          # (word)distance < (word)-8
            if self.is_guard_notice:                    # the kid made a sound ...
                self.is_guard_notice = 0
                if distance < 0:                        # ... and is behind the guard: the guard turns around
                    if (distance & 0xFFFF) < 0xFFFC: self.move_4_down()      # (word)distance < (word)-4
                    return
            elif distance < 0: return
        if self.can_guard_see_kid:                      # en garde
            if self.level.number != 13 or self.guard_notice_timer == 0: self.move_down_forw()
    def autocontrol_guard_active(self):
        C, O = self.Char, self.Opp
        char_frame = C.frame
        if char_frame != 166 and char_frame >= 150 and self.can_guard_see_kid != 1:
            if self.can_guard_see_kid == 0:
                if self.droppedout != 0: self.guard_follows_kid_down()
                elif C.charid != CHARID_SKELETON: self.move_down_back()
            else:
                opp_frame = O.frame
                distance = self.char_opp_dist()
                if distance >= 12 and 102 <= opp_frame < 118 and O.action == A_BUMPED: return
                if distance < 35:
                    if (C.sword < SWORD_DRAWN and distance < 8) or distance < 12:
                        if C.direction == O.direction: self.move_2_backward()     # turn around
                        else: self.move_1_forward()
                    else: self.autocontrol_guard_kid_in_sight(distance)
                else:
                    if self.guard_refrac != 0: return
                    if C.direction != O.direction:
                        if 7 <= opp_frame < 15:                 # the kid runs at him
                            if distance < 40: self.move_6_shift()
                            return
                        elif 34 <= opp_frame < 44:              # run-jump
                            if distance < 50: self.move_6_shift()
                            return
                    self.autocontrol_guard_kid_far()
    def autocontrol_guard_kid_far(self):
        if self.tile_is_floor(self.get_tile_infrontof_char()) or self.tile_is_floor(self.get_tile_infrontof2_char()):
            self.move_1_forward()
        else: self.move_2_backward()
    def guard_follows_kid_down(self):
        C, O = self.Char, self.Opp
        if O.action in (A_HANG_CLIMB, A_HANG_STRAIGHT): return
        if (self.wall_type(self.get_tile_infrontof_char()) != 0 or
                (not self.tile_is_floor(self.curr_tile2) and (
                    self.get_tile(self.curr_room, self.tile_col, self.tile_row + 1) == T.spike or
                    self.curr_tile2 == T.loose or           # would fall on a loose floor
                    self.wall_type(self.curr_tile2) != 0 or
                    not self.tile_is_floor(self.curr_tile2) or  # ... or into a chasm
                    C.curr_row + 1 != O.curr_row))):        # ... or the kid is not below
            self.droppedout = 0; self.move_2_backward()     # don't follow
        else: self.move_1_forward()
    def autocontrol_guard_kid_in_sight(self, distance):
        if self.Opp.sword == SWORD_DRAWN: self.autocontrol_guard_kid_armed(distance)
        elif self.guard_refrac == 0:
            if distance < 29: self.move_6_shift()
            else: self.move_1_forward()
    def autocontrol_guard_kid_armed(self, distance):
        if distance < 10 or distance >= 29: self.guard_advance()
        else:
            self.guard_block()
            if self.guard_refrac == 0:
                if distance < 12 or distance >= 29: self.guard_advance()
                else: self.guard_strike()
    def guard_advance(self):
        if self.guard_skill == 0 or self.kid_sword_strike == 0:
            if ADVPROB[self.guard_skill] > self.prandom(255): self.move_1_forward()
    def guard_block(self):
        if self.Opp.frame in (152, 153, 162):
            if self.justblocked != 0:
                if IMPBLOCKPROB[self.guard_skill] > self.prandom(255): self.move_3_up()
            else:
                if BLOCKPROB[self.guard_skill] > self.prandom(255): self.move_3_up()
    def guard_strike(self):
        if self.Opp.frame in (169, 151): return
        if self.Char.frame in (161, 150):
            if RESTRIKEPROB[self.guard_skill] > self.prandom(255): self.move_6_shift()
        else:
            if STRIKEPROB[self.guard_skill] > self.prandom(255): self.move_6_shift()

    # ---- sword hits (seg002)
    def hurt_by_sword(self):
        C = self.Char
        if C.alive >= 0: return
        if C.sword != SWORD_DRAWN:
            self.take_hp(100)                               # hurt when not in fighting pose: death
            self.seqtbl_offset_char(SEQ['stabbed_to_death'])
            killed = True
        else:
            killed = False
            if C.charid != CHARID_SKELETON:                 # (skeletons can't be hurt)
                if self.take_hp(1): killed = True
            if not killed:
                self.seqtbl_offset_char(SEQ['hit_by_sword'])
                C.y = Y_LAND[C.curr_row + 1]; C.fall_y = 0
        if killed:                                          # C: loc_4276
            if self.get_tile_behind_char() != 0 or (distance := self.distance_to_edge_weight()) < 4:
                self.seqtbl_offset_char(SEQ['stabbed_to_death'])
                if (C.charid != CHARID_KID and C.direction < RIGHT and
                        (self.curr_tile2 == T.gate or self.get_tile_at_char() == T.gate)):
                    C.x = X_BUMP[self.tile_col - (1 if self.curr_tile2 != T.gate else 0) + FIRST_ONSCREEN_COLUMN] + TILE_MIDX
                    C.x = self.char_dx_forward(10)
                C.y = Y_LAND[C.curr_row + 1]; C.fall_y = 0
            else:
                C.x = self.char_dx_forward(distance - 20)   # killed and pushed off the ledge
                self.load_fram_det_col(); self.inc_curr_row()
                self.seqtbl_offset_char(SEQ['kid_pushed_off_ledge'])
        self.play_sound(13 if C.charid == CHARID_KID else 12)
        self.play_seq()
    def play_death_music(self):
        self.play_sound(32 if self.Guard.charid == CHARID_SHADOW else 28 if self.holding_sword else 24)
    def check_sword_vs_sword(self):
        if self.Kid.frame == 167 or self.Guard.frame == 167: self.play_sound(10)
    def check_sword_hurt(self):
        if self.Guard.action == A_HURT:
            if self.Kid.action == A_HURT: self.Kid.action = A_RUN_JUMP
            self.loadshad(); self.hurt_by_sword(); self.saveshad()
            self.guard_refrac = REFRACTIMER[self.guard_skill]
        elif self.Kid.action == A_HURT:
            self.loadkid(); self.hurt_by_sword(); self.savekid()
    def check_sword_hurting(self):
        kid_frame = self.Kid.frame
        if kid_frame != 0 and (kid_frame < 219 or kid_frame >= 229):       # (not on the stairs)
            self.loadshad_and_opp(); self.check_hurting(); self.saveshad_and_opp()
            self.loadkid_and_opp(); self.check_hurting(); self.savekid_and_opp()
    def check_hurting(self):
        C, O = self.Char, self.Opp
        if C.sword != SWORD_DRAWN or C.curr_row != O.curr_row: return
        if C.frame not in (153, 154): return               # (poking with the sword)
        distance = self.char_opp_dist()
        if distance < 0 or distance >= 29 or O.frame not in (161, 150):
            if C.frame == 154:                              # ... and Opp is not parrying
                min_hurt_range = 8 if O.sword < SWORD_DRAWN else 12
                distance = self.char_opp_dist()
                if min_hurt_range <= distance < 29: O.action = A_HURT
        else:
            O.frame = 161
            if C.charid != CHARID_KID: self.justblocked = 4
            self.seqtbl_offset_char(SEQ['attack_was_parried']); self.play_seq()
        if C.direction == DIR_NONE: return
        if C.frame == 154 and O.frame != 161 and O.action != A_HURT: self.play_sound(11)

    # ---- the guard's tick (seg000 play_guard_frame, seg006 play_guard)
    def play_guard(self):
        C = self.Char
        if C.charid == CHARID_MOUSE: self.autocontrol_opponent(); return
        if C.alive < 0:
            if self.guardhp_curr == 0:
                C.alive = 0; self.on_guard_killed()
                if C.charid == CHARID_SHADOW: self.clear_char()
        elif C.charid == CHARID_SHADOW: self.clear_char()
        self.autocontrol_opponent()
        self.control()
    def play_guard_frame(self):
        if self.Guard.direction != DIR_NONE:
            self.loadshad_and_opp(); self.load_fram_det_col(); self.check_killed_shadow()
            self.play_guard()
            C = self.Char
            if C.room == self.drawn_room:
                self.play_seq()
                if 44 <= C.x < 211:
                    self.fall_accel(); self.fall_speed()
                    self.load_frame_to_obj(); self.load_fram_det_col(); self.set_char_collision()
                    self.check_guard_bumped(); self.check_action(); self.check_press(); self.check_spike_below()
                    self.check_spiked(); self.check_chomped_guard()
            self.saveshad()

    # ---- room change
    def leave_room(self):
        C = self.Char; y = C.y; a = C.action; f = C.frame
        if a not in (A_BUMPED, A_FREEFALL, A_MIDAIR) and s8(y) < 10 and s8(y) > -16: leave_dir = 2
        elif y >= 211: leave_dir = 3
        elif 135 <= f < 150 or 110 <= f < 120 or 150 <= f < 163 or 166 <= f < 169 or a == A_TURN: return -1
        elif C.direction != RIGHT:
            if self.char_x_left <= 54: leave_dir = 0
            elif self.char_x_left >= 198: leave_dir = 1
            else: return -1
        else:
            self.get_tile(C.room, 9, C.curr_row)
            if self.curr_tile2 not in (T.doortop_with_floor, T.doortop) and self.char_x_right >= 201: leave_dir = 1
            elif self.char_x_right <= 57: leave_dir = 0
            else: return -1
        lv = self.level.number
        if leave_dir == 0:
            # play_mirr_mus (level 4: the mirror music marks the level door open state), level3_set_chkp, Jaffar_exit
            if self.leveldoor_open not in (0, 0x4D) and lv == 4 and C.curr_row == 0 and C.room == 11: self.play_sound(25); self.leveldoor_open = 0x4D
            if lv == 3 and C.room == 7: self.checkpoint = 1; self.hitp_beg_lev = self.hitp_max     # level3_set_chkp
            if self.leveldoor_open == 2: self.get_tile(24, 0, 0); self.trigger_button(0, 0, -1)
        elif leave_dir == 1:
            if lv == 12 and C.room == 18:            # sword_disappears
                self.get_tile(15, 1, 0); self.set_tile(self.curr_room, self.curr_tilepos, T.floor); self.set_mod(self.curr_room, self.curr_tilepos, 0)
            if lv == 13 and self.leveldoor_open == 0 and C.room == 3: self.play_sound(29); self.guard_notice_timer = 28    # meet_Jaffar
        elif leave_dir == 3:
            if lv == 6 and C.room == 1: return -2    # level 6 falling exit
        self.goto_other_room(leave_dir)
        return leave_dir
    def goto_other_room(self, direction):
        C = self.Char
        C.room = self.links(C.room)[direction] if C.room else 0
        if direction == 0: C.x = (C.x + 140) & 0xFF
        elif direction == 1: C.x = (C.x - 140) & 0xFF
        elif direction == 2: C.y = (C.y + 189) & 0xFF; C.curr_row = self.y_to_row_mod4(C.y)
        else: C.y = (C.y - 189) & 0xFF; C.curr_row = self.y_to_row_mod4(C.y)
    def exit_room(self):
        if self.exit_room_timer != 0: self.exit_room_timer -= 1; return
        self.loadkid()
        self.load_frame_to_obj(); self.set_char_collision()
        self.roomleave_result = self.leave_room()
        if self.roomleave_result < 0: return
        self.savekid(); self.next_room = self.Char.room
        G = self.Guard; L = self.level; leave = 0
        if G.direction == DIR_NONE: return
        if G.alive < 0 and G.sword == SWORD_DRAWN:
            kid_room_m1 = self.Kid.room - 1
            if 0 <= kid_room_m1 <= 23 and (L.guards_tile[kid_room_m1] >= 30 or L.guards_seq_hi[kid_room_m1] != 0):
                r = self.roomleave_result
                if r == 0: leave = G.x >= 91               # left
                elif r == 1: leave = G.x < 165             # right
                elif r == 2: leave = G.curr_row >= 0       # up
                else: leave = G.curr_row < 3               # down
            else: leave = 1
        else: leave = 1
        if leave: self.leave_guard()
        else: self.follow_guard()                          # the guard follows the kid into the next room

    # ---- one tick (SDLPoP play_level_2 + play_frame)
    def step(self, cx, cy, shift, keys=0):
        """One tick with the kid's controls (keys bit 0: Ctrl+A, restart the level); returns the kid trace line (None
        on a restart tick); the guard line is in self.guard_line, the state line in self.state_line. With
        self.multi_level a restart or a level change without music (level 6 falling exit, level 12 running exit) loads
        the level as SDLPoP does; self.game_over is set when the game leaves the levels ('EXPIRED', 'END', 'TITLE')."""
        self.guard_line = self.state_line = self.kid_line = self.sound_line = None
        self.sound_tick()
        self.guardhp_delta = 0; self.hitp_delta = 0
        self.timers()
        self.play_frame(cx, cy, shift, keys)
        if self.game_over: return self.kid_line
        if self.is_restart_level:
            self.is_restart_level = 0
            if self.multi_level: self.play_level(Level(self.level.number))
        elif self.next_level != self.level.number and (self.level_switch or not self.level_end_wait()):
            # play_level_2: the level is done and no sound plays (stop_sounds): the next level starts. The silent
            # model's level end wait: the end music (levels 1-12: 41, level 4: 32) never ends, so only the exits
            # without it change the level here (the level 6 / 12 exits, level 13's stairs). Ticks: any sound of the
            # ticks model (SDLPoP: check_sound_playing); hybrid: live (live_playing), the clock charged as ticks
            self.level_switch = False
            if self.sound_mode == 'hybrid' and self.level_end_charge(): return self.kid_line
            self.stop_sounds()
            if self.multi_level:
                self.hitp_beg_lev = self.hitp_max; self.checkpoint = 0
                self.play_level(Level(self.next_level))
        else:
            if self.sound_mode == 'hybrid' and self.next_level != self.level.number and self.snd_left == 0:
                self.end_over = 1         # (the ticks mode would have changed the level by now: the clock stops)
            self.draw_game_frame()
        return self.kid_line
    def level_end_wait(self):
        """play_level_2's check_sound_playing for the level change"""
        return self.end_music if self.sound_mode == 'silent' else self.sound_playing('level_end')
    def level_end_charge(self):
        """hybrid (docs/m7-design.md D4): the live level end wait ended while the ticks model still plays: the clock
        is charged the ticks it would still have run (show_time per tick, as the ticks mode). True: the time ran out"""
        while self.snd_left > 0:
            self.snd_left -= 1; self.show_time()
            if self.level.number < 13 and self.rem_min == 0: self.expired(); return True
        return False
    def play_frame(self, cx, cy, shift, keys=0):
        self.do_mobs(); self.process_trobs()
        self.check_skel()
        self.check_can_guard_see_kid()
        if self.play_kid_frame(cx, cy, shift, keys): return         # (the level restarts)
        self.tick += 1
        self.play_guard_frame()
        self.check_sword_hurting(); self.check_sword_hurt()
        self.check_sword_vs_sword()
        self.do_delta_hp()
        self.exit_room()
        self.check_the_end()
        if self.game_over: return
        self.check_guard_fallout()
        self.guard_line = self.trace_guard_line() if self.guards else None
        lv = self.level.number
        if lv == 6:
            if self.roomleave_result == -2:                         # level 6 falling exit
                self.Kid.y = 0xFF; self.stop_sounds(); self.next_level += 1; self.level_done = True; self.level_switch = True
        elif lv == 12:
            if self.Kid.room == 23:                                 # level 12 running exit (seamless into level 13)
                self.next_level += 1; self.stop_sounds(); self.seamless = 1; self.level_done = True; self.level_switch = True
        if not self.end_over: self.show_time()       # (hybrid: no clock after the ticks model's level end wait)
        self.state_line = self.trace_state_line() if self.trace_state else None
        if lv < 13 and self.rem_min == 0: self.expired()            # (expiring doesn't count on Jaffar's/princess level)
    def expired(self):
        """the time has run out: the 'time expired' cutscene and the title (the game is over)"""
        self.game_over = 'EXPIRED'
    def play_kid_frame(self, cx, cy, shift, keys=0):
        self.loadkid_and_opp()
        self.load_fram_det_col()
        self.check_killed_shadow()
        self.play_kid(cx, cy, shift, keys)
        if self.upside_down and self.Char.alive >= 0: self.upside_down = 0     # (death turns the screen back)
        if self.is_restart_level: return 1
        C = self.Char
        if C.room != 0:
            self.play_seq(); self.fall_accel(); self.fall_speed()
            self.load_frame_to_obj(); self.load_fram_det_col(); self.set_char_collision()
            self.bump_into_opponent()
            self.check_collisions(); self.check_bumped(); self.check_gate_push()
            self.check_action(); self.check_press(); self.check_spike_below(); self.check_spiked(); self.check_chomped_kid()
            self.check_knock()
        self.savekid()
        self.kid_line = self.trace_line()
        return 0
    def play_kid(self, cx, cy, shift, keys=0):
        C = self.Char
        if C.alive < 0 and C.room == 0:                                         # fell_out
            self.take_hp(100); C.alive = 0; self.erase_bottom_text(); C.frame = 185
        self.control_kid(cx, cy, shift, keys)
        # death timer: SDLPoP waits while a sound plays (but the gate opening, 5), and at alive 7 (the death music
        # queued at 6) while any sound plays. Silent model: only the feather music waits.
        if self.sound_mode == 'silent': p = 0; wait = self.feather_music
        else: p = self.sound_playing('death'); wait = p and self.current_sound != 5
        if C.alive >= 0 and self.is_dead() and not wait:
            self.is_show_time = 0
            if C.alive == 6 and self.level.number not in (0, 15): self.play_death_music()   # (sound on)
            if C.alive == 7 and p: pass                                         # (the gate sound still plays)
            else:
                if C.alive == 7:                                                # (C: after the death music)
                    if self.rem_min == 0: self.expired()
                    if self.level.number not in (0, 15): self.set_text(288, 'Press Button to Continue')
                    else: self.set_text(36, '')
                if C.alive < 100: C.alive += 1     # (capped: the Z80 keeps it in a byte where 0xFF means alive)
        self.want_restart = C.alive > 6 and shift
    def control_kid(self, cx, cy, shift, keys=0):
        C = self.Char
        if C.alive < 0 and self.hitp_curr == 0: C.alive = 0
        if self.grab_timer: self.grab_timer -= 1
        (self.control_forward, self.control_backward, self.control_up, self.control_down, self.control_shift2) = self.ctrl1
        if (keys & 1) and self.level.number != 15:                             # Ctrl+A: restart the level
            self.stop_sounds(); self.is_restart_level = 1
        if keys >> 3: self.process_key(keys >> 3)
        # pop800_control: the first control tick applies the level patches and (guards off) removes all guards
        for (r, p, t, m) in self.patches: self.set_tile(r, p, t); self.set_mod(r, p, m)
        self.patches = []
        if not self.guards and self.tick == 0:
            self.Guard.direction = DIR_NONE; self.Guard.room = 0
            for i in range(24): self.level.guards_tile[i] = 30
        self.control_x, self.control_y, self.control_shift = cx, cy, (HELD if shift else RELEASED)
        self.read_user_control(); self.user_control()
        self.ctrl1 = [self.control_forward, self.control_backward, self.control_up, self.control_down, self.control_shift2]

    def process_key(self, k):
        """SDLPoP process_key for a script's key code (KEY_*; the oracle's hook runs the real one at this point). The
        sound switch only shows its text here: the port's sound model keeps asking (docs/m7-design.md 18)."""
        lv, C = self.level.number, self.Char
        if k == KEY_SPACE: self.is_show_time = 1
        elif k == KEY_SHIFT_L:
            if lv < 4 or self.cheats:
                if lv == 14: self.next_level = 1
                elif lv != 15:
                    self.next_level = lv + 1
                    if not self.cheats and self.rem_min > 15: self.rem_min = 15; self.rem_tick = 719
                self.stop_sounds()
        elif k == KEY_ENTER:
            if self.rem_min != 0 and C.alive > 6 and lv != 15: self.stop_sounds(); self.is_restart_level = 1
        elif k == KEY_CTRL_R: self.game_over = 'TITLE'; self.key_title = True; self.is_restart_level = 1
        elif k == KEY_CTRL_S:
            self.sound_on = not self.sound_on; self.set_text(24, 'SOUND ON' if self.sound_on else 'SOUND OFF')
        elif k == KEY_CTRL_V: self.set_text(24, VERSION_TEXT)
        elif k == KEY_PAUSE: self.erase_bottom_text()
        elif not self.cheats: pass
        elif k == KEY_C_KILL:
            if self.Guard.charid != CHARID_SKELETON: self.guardhp_delta = -self.guardhp_curr; self.Guard.alive = 0
        elif k in (KEY_C_PLUS, KEY_C_MINUS):
            if k == KEY_C_PLUS: self.rem_min += 1
            elif self.rem_min > 1: self.rem_min -= 1
            self.text_time_total = self.text_time_remaining = 0; self.is_show_time = 1
        elif k == KEY_C_LIFE: self.play_sound(30); self.flash_color = COLOR_RED; self.flash_time = 4; self.add_life()
        elif k == KEY_C_HEAL:
            if self.hitp_curr != self.hitp_max:
                self.play_sound(33); self.hitp_delta = 1; self.flash_color = COLOR_RED; self.flash_time = 2
        elif k == KEY_C_FEATHER: self.feather_fall()
        elif k == KEY_C_FLIP: self.toggle_upside()
        elif k in (KEY_C_VIEW_L, KEY_C_VIEW_R, KEY_C_VIEW_U, KEY_C_VIEW_D):
            self.next_room = self.links(self.drawn_room)[k - KEY_C_VIEW_L]
        elif k == KEY_C_BACK: self.next_room = self.Kid.room
    # ---- bottom text, time, flashes, the mirror (seg008 show_time/show_level, seg000 draw_game_frame, seg003)
    def set_text(self, ticks, text):
        self.text_time_remaining = self.text_time_total = ticks; self.bottom_text = text
    def erase_bottom_text(self):
        self.text_time_total = self.text_time_remaining = 0; self.bottom_text = ''
    def show_level(self):
        self.text_time_remaining = self.text_time_total = 0
        n = self.level.number
        if n != 0 and n < 14 and self.seamless == 0:
            self.set_text(24, 'LEVEL %d' % (12 if n == 13 else n))
            self.is_show_time = 1
        self.seamless = 0
    def show_time(self):
        lv = self.level.number
        if (self.Kid.alive < 0 and self.rem_min != 0 and (lv < 13 or (lv == 13 and self.leveldoor_open == 0)) and lv < 15):
            self.rem_tick -= 1                                  # time passes
            if self.rem_tick == 0:
                self.rem_tick = 719; self.rem_min -= 1          # 720 ticks = 1 minute
                if self.rem_min != 0 and (self.rem_min <= 5 or self.rem_min % 5 == 0): self.is_show_time = 1
            elif self.rem_min == 1 and self.rem_tick % 12 == 0:
                self.is_show_time = 1; self.text_time_remaining = 0
        if self.is_show_time and self.text_time_remaining == 0:
            self.set_text(24, '')
            if self.rem_min > 0:
                if self.rem_min == 1:
                    rem_sec = (self.rem_tick + 1) // 12
                    if rem_sec == 1: self.set_text(12, '1 SECOND LEFT')
                    else: self.bottom_text = '%d SECONDS LEFT' % rem_sec
                else: self.bottom_text = '%d MINUTES LEFT' % self.rem_min
            else: self.bottom_text = 'TIME HAS EXPIRED!'
            self.is_show_time = 0
    def draw_game_frame(self):
        """the game-state side of SDLPoP draw_game_frame + flash_if_hurt/remove_flash_if_hurt (after play_frame)"""
        self.check_mirror()                                     # (draw_people)
        if self.united_with_shadow == 2 and self.Kid.room != 0 and self.Kid.room == self.drawn_room:
            self.play_sound(41)                                 # (draw_kid: the kid drawn as the shadow, united)
        self.play_next_sound()
        if self.text_time_remaining == 1:
            if self.text_time_total in (36, 288): self.game_over = 'TITLE'     # died: back to the title (start_game)
            else: self.erase_bottom_text()
        elif self.text_time_remaining != 0 and self.text_time_total != 1188:
            self.text_time_remaining -= 1
        if self.flash_time: self.flash_time -= 1
    def check_mirror(self):
        if self.jumped_through_mirror == -1: self.jump_through_mirror()
        elif self.get_tile_at_char() == T.mirror:               # (the mirror image: drawing only, Char is scratch)
            self.loadkid(); self.load_frame(); self.check_mirror_image()
    def jump_through_mirror(self):
        """level 4: the kid jumped through the mirror: his mirror image becomes the shadow, he keeps 1 hit point"""
        self.loadkid(); self.load_frame(); self.check_mirror_image()
        self.jumped_through_mirror = 0
        self.Char.charid = CHARID_SHADOW
        self.play_sound(45)
        self.saveshad()
        self.guardhp_max = self.guardhp_curr = self.hitp_max
        self.hitp_curr = 1
    def check_mirror_image(self):
        C = self.Char
        xpos = X_BUMP[C.curr_col + FIRST_ONSCREEN_COLUMN] + 10
        distance = self.distance_to_edge_weight()
        if C.direction >= RIGHT: distance = (~distance) + TILE_SIZEX
        self.distance_mirror = distance - 2
        C.x = ((xpos << 1) - C.x) & 0xFF
        C.direction = ~C.direction

    def room_checksum(self):
        r = self.Kid.room
        if not 1 <= r <= 24: return 0
        b = (r - 1) * 30
        return sum(self.level.fg[b + i] + 3 * self.level.bg[b + i] for i in range(30))
    def trace_line(self):
        K = self.Kid
        return '%d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d' % (self.tick, K.frame, K.x, K.y, K.direction, K.curr_row, K.curr_col, K.action, K.fall_x, K.fall_y, K.room, K.curr_seq, K.alive,
            self.hitp_curr, self.hitp_max, len(self.trobs), len(self.mobs), self.room_checksum())
    def trace_state_line(self):
        L = self.level
        cs = sum((L.fg[i] + 3 * L.bg[i]) * (i % 7 + 1) for i in range(24 * 30))
        return 'S %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d' % (
            L.number, self.next_level, self.rem_min, self.rem_tick, self.is_show_time, self.text_time_remaining,
            self.text_time_total, self.is_feather_fall, self.upside_down & 0xFFFF, self.flash_color, self.flash_time,
            self.united_with_shadow, self.leveldoor_open, self.checkpoint, self.hitp_beg_lev, self.hitp_curr, self.hitp_max,
            self.guardhp_curr, self.guardhp_max, self.jumped_through_mirror, self.demo_time, self.demo_index,
            self.shadow_initialized, self.have_sword & 0xFFFF, cs)
    def trace_guard_line(self):
        G = self.Guard; K = self.Kid
        return 'G %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d' % (
            G.frame & 0xFF, G.x & 0xFF, G.y & 0xFF, s8(G.direction), s8(G.curr_row), s8(G.curr_col), G.action & 0xFF, s8(G.fall_x),
            s8(G.fall_y), G.room & 0xFF, 0 if G.curr_seq == -SEQ_BASE else G.curr_seq, s8(G.alive), G.sword & 0xFF, G.charid & 0xFF,
            self.guardhp_curr, self.guardhp_max, self.hitp_curr, K.sword & 0xFF, self.can_guard_see_kid, self.holding_sword,
            self.justblocked, self.guard_refrac, self.kid_sword_strike, self.guard_notice_timer, self.is_guard_notice,
            self.offguard, self.droppedout, self.guard_skill)

def read_script(path):
    """Control script: one 'x y shift' line per tick; '# patch room:pos:tile:mod,...' lines give level patches.
    Returns (moves, patches)."""
    moves, patches = [], []
    for l in open(path):
        if l.startswith('# patch'):
            for item in l.split()[2].split(','):
                patches.append(tuple(int(v) for v in item.split(':')))
            continue
        p = l.split()
        if len(p) >= 3 and not l.startswith('#'): moves.append((int(p[0]), int(p[1]), int(p[2])))
    return moves, patches

def read_keys(path):
    """The optional 4th field of the script's control lines: keys per tick (bit 0: Ctrl+A, restart the level; bits 3-7: a
    key code KEY_*, SDLPoP's process_key at the control point)."""
    keys = []
    for l in open(path):
        p = l.split()
        if len(p) >= 3 and not l.startswith('#'): keys.append(int(p[3]) if len(p) > 3 else 0)
    return keys

def script_level(path, default=1):
    """The level a control script plays ('# level N' line), else default."""
    for l in open(path):
        if l.startswith('# level'): return int(l.split()[2])
    return default

def script_opts(path):
    """Script options: '# guards' (the level's guards on), '# guard room:tile:dir:skill:color' (a placed guard, guards on),
    '# sword' (the kid starts with the sword), '# state' (trace the 'S' state line), '# time min:tick' (time left at the start),
    '# start room:pos:dir' (where the kid starts the first level, dir 0 right / -1 left), '# sound ticks' (the ticks sound
    model: deterministic waits on sound; the oracle's SDLPoP uses the same model, POP800_SOUND_TICKS), '# level1 music'
    (the level 1 start crouches until its music ends: SDLPoP POP800_LEVEL1_MUSIC)."""
    o = dict(guards=False, place=[], sword=False, state=False, time=None, start=None, sound='silent', level1_music=False, cheats=False)
    for l in open(path):
        if l.startswith('# guards'): o['guards'] = True
        elif l.startswith('# state'): o['state'] = True                       # the 'S' level-event state lines
        elif l.startswith('# time '): o['time'] = tuple(int(v) for v in l.split()[2].split(':'))   # min:tick left at the start
        elif l.startswith('# start '): o['start'] = tuple(int(v) for v in l.split()[2].split(':'))  # room:pos:dir (the kid's start)
        elif l.startswith('# guard '):
            o['guards'] = True; o['place'].append(tuple(int(v) for v in l.split()[2].split(':')))
        elif l.startswith('# sword'): o['sword'] = True
        elif l.startswith('# sound '): o['sound'] = l.split()[2]
        elif l.startswith('# level1 music'): o['level1_music'] = True
        elif l.startswith('# cheats'): o['cheats'] = True                     # (the key codes of the cheats act)
    return o

def patch_env(path):
    """POP800_PATCH value for the SDLPoP oracle."""
    return ','.join('%d:%d:%d:%d' % p for p in read_script(path)[1])

def run_script(level_no, script_path, out=None, mods=None, notraps=False, seed=12345, patches=None):
    """The trace lines for a script: per tick the kid line, (guards on) the guard 'G' line, ('# state') the 'S' line;
    restarts (keys) and level changes without music are played through; 'EXPIRED' / 'END' when the game leaves the levels."""
    level = Level(level_no)
    moves, pp = read_script(script_path)
    keys = read_keys(script_path)
    o = script_opts(script_path)
    sim = KidSim(level, notraps=notraps, seed=seed, patches=pp if patches is None else patches,
                 guards=o['guards'], place=o['place'], sword=o['sword'], time=o['time'], multi_level=True,
                 trace_state=o['state'], start=o['start'], sound=o['sound'], level1_music=o['level1_music']); lines = []
    sim.cheats = o['cheats']
    if mods: level.bg[:] = mods            # modifiers as the oracle has them at its first tick (frozen-trap mode)
    for (x, y, sh), k in zip(moves, keys):
        kl = sim.step(x, y, sh, k)
        if kl is not None: lines.append(kl)
        if sim.guard_line is not None: lines.append(sim.guard_line)
        if sim.state_line is not None: lines.append(sim.state_line)
        if sim.sound_line is not None: lines.append(sim.sound_line)
        if sim.game_over in ('EXPIRED', 'END'): lines.append(sim.game_over); break
        if sim.key_title: lines.append('TITLE')                               # (Ctrl+R: the oracle's marker)
        if sim.game_over: break
    if out: open(out, 'w').write('\n'.join(lines) + '\n')
    return lines

if __name__ == '__main__':
    lines = run_script(int(sys.argv[1]), sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    print('\n'.join(lines[:5])); print('...', len(lines), 'ticks')
