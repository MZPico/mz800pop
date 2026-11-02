#!/usr/bin/env python3
"""M7 step 7: the cutscene simulator, a Python port of SDLPoP seg001 (load_intro, proc_cutscene_frame, play_both_seq,
draw_princess_room_bg, princess_room_torch, draw_hourglass, draw_star, the level cutscenes cutscene_2_6, _4, _8, _9,
_12, pv_scene, time_expired and end_sequence_anim) with the frame engine's sequence table from tools/kidsim.py (play_seq,
load_frame, load_frame_to_obj: SDLPoP's seqtbl and frame tables), and a reference render with the EGA art of PV.DAT.

The two character slots: the "kid" slot (Kid: Jaffar, the mouse, the ending's kid) and the "shad" slot (Guard: the
princess); a slot is drawn and played while its frame is not 0. Per cutscene frame (one pass of proc_cutscene_frame's
loop) the 'C' line, which the SDLPoP hook POP800_CUT (external/SDLPoP/src/pop800_trace.c) writes the same way:
  C n  kid: frame x y direction  shad: frame x y direction  hourglass_state hourglass_sandflow  star colour
    torch0 torch1  flash_time cutscene_frame_time  next_sound current_sound playing
n counts the scene's frames from 0; star = the star draw_proom_drects drew this frame (-1 none) and its colour index;
torch0/1 = princess_torch_frame; playing = the ticks sound model (below). After the scene a 'W' line: the until-the-
music-ends waits as frame counts (each "do proc_cutscene_frame(1) while (check_sound_playing())" loop: its frames) and
then, as the last number, the SDLPoP ticks the scene's music still has when the scene function returns (play_level's
wait before the level starts: it waits while check_sound_playing()).

Deterministic models (as the hook has them):
  - random_seed = 12345 at load_intro (the scene's star and torch draws; SDLPoP continues the game's seed);
  - the stars' colours and princess_torch_frame start fresh (SDLPoP keeps them across scenes: static data);
  - the EGA fades (fade_in_1 / fade_out_1: interlaced passes, docs/m7-design.md §15, §17) run exactly ONE cutscene frame
    each, at their start, as DOSBox shows (§17): proc_cutscene_frame(1) with its star, its sound start, its objects in
    the offscreen surface (the fade-in's passes show them; the fade-out's frame shows nothing), and no frame time of its
    own: a fade takes FADE_TICKS instead (5 passes 4 ticks apart, the next frame 4 ticks after the last). SDLPoP's VGA
    fade runs frames until the palette fade ends: wall-clock dependent;
  - sound: the ticks model at the cutscene's rate: a sound started by play_next_sound plays ceil(seconds x 60) SDLPoP
    ticks (kidsim SOUND_SECONDS), each cutscene frame takes cutscene_frame_time ticks of it at its start;
    check_sound_playing() = ticks left > 0; stop_sounds ends it.

Render (Render(scene).screens()): SDLPoP's offscreen surface with its peels (midtable items restore the background
they covered at the next frame), the onscreen surface = the offscreen one plus the stars draw_star drew there; EGA
colours: chtab 8 (the room, palette res 950: res 951 room, 952 pillar, 953-959 hourglass, 960-962 sand) and 9 (the bed,
980: res 981, ORed onto the room in EGA colour numbers) with the 2 x 2 dither of their palettes' four tables at the
screen pixel, the princess (chtab 3 res 800, chtab 4 res 900; Jaffar 850 when which_imgs = 0), the torch flames
(PRINCE.DAT chtab 1) and the mouse (the kid pack as the game draws the kid); EGA 13 shows black. Screens: 200 rows of
320 MZ colours.
usage: cutsim.py <level | pv_scene | time_expired | end_sequence_anim> [rem_min] [--png DIR]   (prints the C and W lines)"""
import math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import kidsim
from kidsim import Char, s8, RIGHT, LEFT
from popdata import EGA2MZ, DOSDIR
from datfile import DatFile

CHARID_KID, CHARID_PRINCESS, CHARID_VIZIER, CHARID_MOUSE = 0, 5, 6, 24
SEQ = dict(start_run=1, stop_run=13, princess_stand_PV1=94, Jaffar_stand_PV1=95, Jaffar_walk=96, Jaffar_stop=97,
           princess_turn_around=98, princess_step_back=99, Jaffar_end_conjuring=100, mouse_stands_up=101,
           Jaffar_conjuring=102, princess_lying_PV2=103, mouse_forward=105, mouse=106, mouse_stand_up_and_go=107,
           princess_turn_and_hug=108, princess_stand_PV2=109, princess_crouching_PV2=110, princess_stand_up_PV2=111,
           princess_crouch_down_PV2=112, princess_look_down=113, mouse_stand=114)
N_STARS = 6
STARS = ((20, 97, 0), (16, 104, 1), (23, 110, 2), (17, 116, 3), (24, 120, 4), (18, 128, 0))
STAR_COLORS = (8, 7, 15, 15, 7)
TIME_BOUND = (6, 17, 33, 65)
TORCH_XH, TORCH_XL, TORCH_FRAME0 = (11, 26), (5, 3), (1, 6)
CUT_SEED = 12345
FADE_TICKS = 20              # an EGA fade: the passes at 0, 4, .., 16, the next frame at 20 (the DOSBox recordings, §17)
ROWS_FULL = ('pv_scene', 'time_expired')   # offscreen surface 320 x 200 (show_title, expired); else the game's 320 x 192
                                           # (rows 192-199 stay black: DOSBox and SDLPoP, §17)
SCENE_IMGS = {'pv_scene': 0, 'time_expired': 1, 'end_sequence_anim': 1}
LEVEL_SCENES = {2: 'cutscene_2_6', 4: 'cutscene_4', 6: 'cutscene_2_6', 8: 'cutscene_8', 9: 'cutscene_9',
                12: 'cutscene_12'}           # SDLPoP data.h tbl_cutscenes (load_intro(level > 2, ...))
# The ticks model's lengths of the presentation (M7 step 11, docs/m7-design.md 19): the DOS lengths (kidsim, the in-game
# model keeps them), except where the Master System pieces PRES plays decide the wait: the level cutscenes end when
# SMS song 7 ends (432 frames = 8.64 s, build/sound/sms/index.txt; DOS 27 12.0 s, 35 10.286 s, 40 6.857 s), and the
# ending's final wait (the ticks model's 56: the hail screen + TITLE_MAIN after the embrace's 840 ticks) lasts until
# the title theme (SMS song 1, 570 frames = 684 ticks) has played 3 times from the embrace's start: 2052 - 840 = 1212
# ticks (DOS 124.7 s). tools/cut_suite.py feeds these to the SDLPoP hook POP800_CUT_TICKS.
PRES_TICKS60 = {27: 519, 35: 519, 40: 519, 56: 1212}       # ceil(8.64 x 60) = 519
SOUND_SECONDS = list(kidsim.SOUND_SECONDS)
for _i, _t in PRES_TICKS60.items(): SOUND_SECONDS[_i] = _t / 60.0

def sound_ticks60(sid):
    """the ticks model's length of a sound in SDLPoP ticks (60 a second), rounded up (PRES_TICKS60 exact)"""
    if sid in PRES_TICKS60: return PRES_TICKS60[sid]
    return math.ceil(SOUND_SECONDS[sid] * 60 - 1e-9)

class Aborted(Exception): pass

class CutSim:
    """one load_intro(which_imgs, scene): the frames' states (frames: dicts) and the C / W lines"""
    def __init__(self, scene, rem_min=60, which_imgs=None, seed=CUT_SEED):
        self.k = k = kidsim.KidSim.__new__(kidsim.KidSim)          # (only its sequence and frame code is used)
        k.seqtbl = open(os.path.join(kidsim.ASSETS, 'seqtbl_z80.bin'), 'rb').read()
        k.seq_off = [int(l.split()[1]) for l in open(os.path.join(kidsim.ASSETS, 'seqtbl_offsets.txt'))]
        import build_assets as BA
        ft = BA.frame_tables(); k.frames, k.frames_guard, k.frames_cuts = ft['kid'], ft['guard'], ft['cuts']
        k.is_feather_fall = 0; k.is_guard_notice = 0
        k.level = type('L', (), {'number': 0})()
        k.play_sound = self.play_sound
        k.end_music = 0; k.next_level = 0; k.level_done = False
        self.scene = scene; self.rem_min = rem_min
        self.which_imgs = which_imgs
        self.seed = seed
        self.lines = []; self.frames = []; self.waits = []
        # reset_cutscene
        k.Kid = Char(); k.Guard = Char(); k.Char = Char()
        self.which_torch = 0; self.hourglass_state = 0; self.hourglass_sandflow = -1; self.cutscene_frame_time = 6
        self.disable_keys = 0; self.flash_time = 0; self.flash_color = 0
        self.next_sound = -1; self.current_sound = 0; self.snd_left = 0
        self.torch = list(TORCH_FRAME0); self.star_col = [s[2] for s in STARS]
        for i in range(N_STARS): self.draw_star(i)          # (load_intro: into the offscreen surface)
        self.stars0 = list(self.star_col)
        self.n = 0; self.fading = None; self.t = 0            # self.t: the scene's SDLPoP ticks
        getattr(self, scene)()
        self.end_left = self.snd_left                         # (play_level waits while the music plays)
        self.lines.append('W ' + ' '.join(str(v) for v in self.waits + [self.end_left]))

    # ---- SDLPoP helpers
    def prandom(self, mx):
        self.seed = (self.seed * 214013 + 2531011) & 0xFFFFFFFF
        return (self.seed >> 16) % (mx + 1)
    def play_sound(self, sid):
        if self.next_sound < 0 or kidsim.SOUND_PRIO[sid] <= kidsim.SOUND_PRIO[self.next_sound]:
            if sid in kidsim.SOUND_MISSING: return
            self.next_sound = sid
    def sound_playing(self): return 1 if self.snd_left > 0 else 0
    def play_next_sound(self):
        q = self.next_sound
        if q >= 0 and (not self.sound_playing() or (kidsim.SOUND_INTERRUPTIBLE[self.current_sound] and
                                                    kidsim.SOUND_PRIO[q] <= kidsim.SOUND_PRIO[self.current_sound])):
            self.current_sound = q; self.snd_left = sound_ticks60(q)
        self.next_sound = -1
    def stop_sounds(self): self.snd_left = 0
    def draw_star(self, i):
        self.star_col[i] = (self.star_col[i] + 1) % len(STAR_COLORS)
        return STAR_COLORS[self.star_col[i]]
    def loadkid(self): self.k.Char = self.k.Kid.copy()
    def savekid(self): self.k.Kid = self.k.Char.copy()
    def loadshad(self): self.k.Char = self.k.Guard.copy()
    def saveshad(self): self.k.Guard = self.k.Char.copy()
    @property
    def C(self): return self.k.Char
    def seqtbl_offset_char(self, sid): self.k.seqtbl_offset_char(sid)
    def play_seq(self): self.k.play_seq()
    def seqtbl_offset_shad_char(self, sid): self.loadshad(); self.seqtbl_offset_char(sid); self.saveshad()
    def seqtbl_offset_kid_char(self, sid): self.loadkid(); self.seqtbl_offset_char(sid); self.savekid()
    def set_hourglass_state(self, st): self.hourglass_sandflow = 0; self.hourglass_state = st
    def hourglass_frame(self):
        i = 0
        while i < 4 and not TIME_BOUND[i] > self.rem_min: i += 1
        return 6 - i

    # ---- the frame engine
    def proc_cutscene_frame(self, wait_frames):
        k = self.k
        while True:
            # play_both_seq
            for slot in ('kid', 'shad'):
                (self.loadkid if slot == 'kid' else self.loadshad)()
                if self.C.frame:
                    self.play_seq()
                    (self.savekid if slot == 'kid' else self.saveshad)()
            # draw_proom_drects: draw_princess_room_bg (princess_room_torch, draw_hourglass), the star
            objs = self.draw_list()
            star = (-1, -1)
            if wait_frames & 1:
                s = self.prandom(N_STARS - 1); self.draw_star(s); star = (s, self.star_col[s])
            fl = self.flash_time
            if self.flash_time: self.flash_time -= 1
            if not self.sound_playing(): self.play_next_sound()
            K, G = k.Kid, k.Guard
            self.lines.append('C %d  %d %d %d %d  %d %d %d %d  %d %d  %d %d  %d %d  %d %d  %d %d %d' % (
                self.n, K.frame, K.x, K.y, K.direction, G.frame, G.x, G.y, G.direction, self.hourglass_state,
                self.hourglass_sandflow, star[0], star[1], self.torch[0], self.torch[1], fl, self.cutscene_frame_time,
                self.next_sound, self.current_sound, self.sound_playing()))
            self.frames.append(dict(n=self.n, tick=self.t, fade=self.fading, objs=objs, star=star, stars=list(self.star_col), flash=fl,
                                    flash_color=self.flash_color, kid=K.copy(), shad=G.copy(),
                                    hourglass=(self.hourglass_state, self.hourglass_sandflow),
                                    torch=tuple(self.torch), ft=self.cutscene_frame_time))
            self.n += 1
            ft = FADE_TICKS if self.fading else self.cutscene_frame_time     # (its ticks)
            self.snd_left = max(0, self.snd_left - ft); self.t += ft
            wait_frames -= 1
            if not wait_frames: return 0

    def until_music(self):
        """do { proc_cutscene_frame(1) } while (check_sound_playing()): its frame count to the W line"""
        n = 0
        while True:
            self.proc_cutscene_frame(1); n += 1
            if not self.sound_playing(): break
        self.waits.append(n)

    def obj_of(self, C):
        """load_frame_to_obj + add_objtable + draw_objtable_item: (chtab, image, screen x, ybottom, flip) or None"""
        k = self.k; k.Char = C.copy(); k.load_frame_to_obj()
        if k.obj_id == 255: return None
        ox = k.obj_x
        return dict(chtab=k.obj_chtab, img=k.obj_id, x=int(ox * 8 / 7) if ox >= 0 else -int((-ox) * 8 / 7),
                    yb=k.obj_y, flip=C.direction == RIGHT, y=k.obj_y)

    def draw_list(self):
        """draw_princess_room_bg's tables as draw_tables paints them: backtable (the torches), midtable (the characters
        in draw_objtable_items_at_tile order, the hourglass), foretable (the pillar, the sand). Entries: (table, chtab,
        image index, x, ybottom, blit, flip, peel); x for chtabs 2-4 is the screen x before the flip's - w."""
        k = self.k; objs = []
        chars = []
        for slot, C in ((0, k.Kid), (1, k.Guard)):
            if C.frame:
                o = self.obj_of(C)
                if o: o['slot'] = slot; chars.append(o)
        # draw_objtable_items_at_tile: the objtable scanned last to first (shad, kid), bubble-sorted by y ascending
        cur = list(reversed(chars))
        swapped = True
        while swapped:
            swapped = False
            for i in range(len(cur) - 1):
                if cur[i]['y'] > cur[i + 1]['y']: cur[i], cur[i + 1] = cur[i + 1], cur[i]; swapped = True
        mid = [('mid', o['chtab'], o['img'], o['x'], o['yb'], 'transp', o['flip'], 1, o['slot']) for o in cur]
        fore = [('fore', 8, 1, 30 * 8, 167, 'transp', False, 0, None)]           # the pillar (id 2)
        back = []
        for which in (1, 0):                                                     # princess_room_torch
            self.which_torch = 1 - self.which_torch
            t = self.which_torch
            self.torch[t] = self.get_torch_frame(self.torch[t])
            back.append(('back', 1, self.torch[t], TORCH_XH[t] * 8 + TORCH_XL[t], 116, 'copy', False, 0, None))
        if self.hourglass_sandflow >= 0:                                         # draw_hourglass
            self.hourglass_sandflow = (self.hourglass_sandflow + 1) % 3
            if self.hourglass_state < 7:
                fore.append(('fore', 8, self.hourglass_sandflow + 9, 20 * 8, 164, 'transp', False, 0, None))
                if self.hourglass_state: mid.append(('mid', 8, self.hourglass_state + 1, 19 * 8, 168, 'transp', False, 1, None))
        elif self.hourglass_state:
            mid.append(('mid', 8, self.hourglass_state + 1, 19 * 8, 168, 'transp', False, 1, None))
        return back + mid + fore

    def get_torch_frame(self, curr):
        nxt = self.prandom(255)
        if nxt != curr:
            if nxt < 9: return nxt
            nxt = curr
        nxt += 1
        if nxt >= 9: nxt = 0
        return nxt

    # ---- character setups (seg001)
    def init_princess(self):
        C = self.C; C.charid = CHARID_PRINCESS; C.x = 120; C.y = 166; C.direction = LEFT
        self.seqtbl_offset_char(SEQ['princess_stand_PV1']); self.play_seq()
    def init_princess_right(self): self.init_princess(); self.C.direction = RIGHT
    def init_princess_x156(self): self.init_princess(); self.C.x = 156
    def princess_lying(self):
        self.init_princess(); C = self.C; C.x = 92; C.y = 162
        self.seqtbl_offset_char(SEQ['princess_lying_PV2']); self.play_seq()
    def princess_crouching(self):
        self.init_princess(); C = self.C; C.x = 131; C.y = 169
        self.seqtbl_offset_char(SEQ['princess_crouching_PV2']); self.play_seq()
    def princess_stand(self):
        self.init_princess_right(); C = self.C; C.x = 144; C.y = 169
        self.seqtbl_offset_char(SEQ['princess_stand_PV1']); self.play_seq()
    def init_mouse_go(self):
        C = self.C; C.charid = CHARID_MOUSE; C.x = 199; C.y = 167; C.direction = LEFT
        self.seqtbl_offset_char(SEQ['mouse_forward']); self.play_seq()
    def init_mouse_cu8(self):
        self.init_mouse_go(); self.C.x = 144
        self.seqtbl_offset_char(SEQ['mouse']); self.play_seq()
    def init_vizier(self):
        C = self.C; C.charid = CHARID_VIZIER; C.x = 198; C.y = 166; C.direction = LEFT
        self.seqtbl_offset_char(SEQ['Jaffar_stand_PV1']); self.play_seq()
    def fade_in_1(self):
        self.fading = 'in'; self.proc_cutscene_frame(1); self.fading = None
    def fade_out_1(self):
        self.fading = 'out'; self.proc_cutscene_frame(1); self.fading = None
    def init_ending_princess(self):
        self.init_princess(); C = self.C; C.x = 136; C.y = 164
        self.seqtbl_offset_char(SEQ['princess_stand_PV2']); self.play_seq()
    def init_ending_kid(self):
        C = self.C; C.charid = CHARID_KID; C.x = 198; C.y = 164; C.direction = LEFT
        self.seqtbl_offset_char(SEQ['start_run']); self.play_seq()
    def init_mouse_1(self):
        self.init_mouse_go(); self.C.x -= 2; self.C.y = 164

    # ---- the scenes (seg001.c)
    def cutscene_2_6(self):
        self.play_sound(27); self.set_hourglass_state(self.hourglass_frame())
        self.init_princess_right(); self.saveshad()
        self.fade_in_1(); self.proc_cutscene_frame(26); self.fade_out_1()
    def cutscene_4(self):
        self.play_sound(27); self.set_hourglass_state(self.hourglass_frame())
        self.princess_lying(); self.saveshad()
        self.fade_in_1(); self.proc_cutscene_frame(26); self.fade_out_1()
    def cutscene_8(self):
        self.play_sound(35); self.set_hourglass_state(self.hourglass_frame())
        self.init_mouse_cu8(); self.savekid(); self.princess_crouching(); self.saveshad()
        self.fade_in_1(); self.proc_cutscene_frame(20)
        self.seqtbl_offset_kid_char(SEQ['mouse_stand_up_and_go']); self.proc_cutscene_frame(20)
        self.seqtbl_offset_shad_char(SEQ['princess_stand_up_PV2']); self.proc_cutscene_frame(20)
        self.k.Kid.frame = 0; self.fade_out_1()
    def cutscene_9(self):
        self.play_sound(35); self.set_hourglass_state(self.hourglass_frame())
        self.princess_stand(); self.saveshad(); self.fade_in_1()
        self.init_mouse_go(); self.savekid(); self.proc_cutscene_frame(5)
        self.seqtbl_offset_shad_char(SEQ['princess_crouch_down_PV2']); self.proc_cutscene_frame(9)
        self.seqtbl_offset_kid_char(SEQ['mouse_stand']); self.proc_cutscene_frame(58)
        self.fade_out_1()
    def cutscene_12(self):
        f = self.hourglass_frame()
        if f >= 6:
            self.set_hourglass_state(f); self.init_princess_x156(); self.saveshad()
            self.play_sound(40); self.fade_in_1(); self.proc_cutscene_frame(2)
            self.seqtbl_offset_shad_char(SEQ['princess_turn_around']); self.proc_cutscene_frame(24); self.fade_out_1()
        else: self.cutscene_2_6()
    def wait_music(self):
        """while (check_sound_playing()) delay_ticks(1): its ticks to the W line"""
        n = 0
        while self.sound_playing(): n += 1; self.snd_left = max(0, self.snd_left - 1); self.t += 1
        self.waits.append(n)
    def time_expired(self):
        self.disable_keys = 1; self.set_hourglass_state(7); self.hourglass_sandflow = -1
        self.play_sound(36); self.fade_in_1(); self.proc_cutscene_frame(2); self.proc_cutscene_frame(100)
        self.fade_out_1()
        self.wait_music()
    def end_sequence_anim(self):
        self.disable_keys = 1
        self.play_sound(26); self.init_ending_princess(); self.saveshad(); self.init_ending_kid(); self.savekid()
        self.proc_cutscene_frame(8)
        self.seqtbl_offset_shad_char(SEQ['princess_turn_and_hug']); self.proc_cutscene_frame(5)
        self.seqtbl_offset_kid_char(SEQ['stop_run']); self.proc_cutscene_frame(2)
        self.k.Kid.frame = 0; self.proc_cutscene_frame(39)
        self.init_mouse_1(); self.savekid(); self.proc_cutscene_frame(9)
        self.seqtbl_offset_kid_char(SEQ['mouse_stands_up']); self.proc_cutscene_frame(41)
        self.fade_out_1()
        self.wait_music()
    def pv_scene(self):
        self.init_princess(); self.saveshad(); self.fade_in_1()
        self.init_vizier(); self.savekid(); self.proc_cutscene_frame(2)
        self.play_sound(50); self.until_music()
        self.cutscene_frame_time = 8; self.proc_cutscene_frame(5)
        self.play_sound(4); self.until_music()
        self.play_sound(51); self.proc_cutscene_frame(3)
        self.seqtbl_offset_shad_char(SEQ['princess_turn_around']); self.proc_cutscene_frame(5)
        self.seqtbl_offset_kid_char(SEQ['Jaffar_walk']); self.proc_cutscene_frame(6)
        self.play_sound(53); self.seqtbl_offset_kid_char(SEQ['Jaffar_stop']); self.proc_cutscene_frame(4)
        self.proc_cutscene_frame(18)
        self.seqtbl_offset_kid_char(SEQ['Jaffar_walk']); self.proc_cutscene_frame(30)
        self.seqtbl_offset_kid_char(SEQ['Jaffar_stop']); self.proc_cutscene_frame(35)
        self.seqtbl_offset_kid_char(SEQ['Jaffar_conjuring']); self.cutscene_frame_time = 7; self.proc_cutscene_frame(1)
        self.seqtbl_offset_shad_char(SEQ['princess_step_back']); self.proc_cutscene_frame(17)
        self.hourglass_state = 1; self.flash_time = 5; self.flash_color = 15
        self.until_music()
        self.seqtbl_offset_kid_char(SEQ['Jaffar_end_conjuring']); self.hourglass_sandflow = 0; self.proc_cutscene_frame(6)
        self.play_sound(52); self.proc_cutscene_frame(24)
        self.hourglass_state = 2; self.proc_cutscene_frame(9)
        self.seqtbl_offset_shad_char(SEQ['princess_look_down']); self.proc_cutscene_frame(28)
        self.fade_out_1()

def level_scene(level, rem_min=60):
    """the cutscene play_level runs before level (load_intro(level > 2, tbl_cutscenes[level]))"""
    return CutSim(LEVEL_SCENES[level], rem_min, which_imgs=1 if level > 2 else 0)

def named_scene(name, rem_min=60):
    """pv_scene (the title), time_expired (expired()), end_sequence_anim (end_sequence)"""
    return CutSim(name, rem_min, which_imgs=SCENE_IMGS[name])

# ---------------------------------------------------------------- the art (EGA, PV.DAT and PRINCE.DAT)
_DATS = {}
def dat(name):
    if name not in _DATS: _DATS[name] = DatFile(os.path.join(DOSDIR, name + '.DAT'))
    return _DATS[name]

def ega_tabs(dname, palres):
    r = dat(dname).resource(palres)
    return [[v for b in r[68 + 8 * t:76 + 8 * t] for v in (b >> 4, b & 15)] for t in range(4)]

def ega_image(dname, palres, res, x0=0, y0=0):
    """(w, h, rows of EGA colour numbers, None = index 0) of an image drawn at screen (x0, y0): the palette's four
    tables are a 2 x 2 dither at the screen pixel (table (y & 1) * 2 + (x & 1), as tools/build_assets.title_image)"""
    tabs = ega_tabs(dname, palres)
    w, h, rows, depth = dat(dname).image(res)
    out = []
    for y in range(h):
        out.append([None if v == 0 else tabs[((y0 + y) & 1) * 2 + ((x0 + x) & 1)][v] for x, v in enumerate(rows[y])])
    return w, h, out

BLACK0 = 4                   # MZ pixel value of EGA attribute 0 (black; the flash turns it white: cut.asm's palette: group
                             # 1, PLT0 = black); EGA 13 shows black too but does not flash: MZ 0 (DOSBox, §17). MZ 4 (EGA 2,
                             # green) occurs in no presentation art.
def mz(e):
    if e == 0: return BLACK0
    if e == 13: return 0
    assert e != 2, 'EGA 2 is not free: cut.asm\'s flash palette uses its MZ value'
    return EGA2MZ[e]

CHTAB_RES = {1: ('PRINCE', 150), 3: ('PV', 800), 8: ('PV', 950)}
def chtab_res(chtab, which_imgs):
    if chtab == 4: return ('PV', 850 + 50 * which_imgs)
    return CHTAB_RES[chtab]

_KP = None
def kid_pack():
    global _KP
    if _KP is None:
        sys.path.insert(0, os.path.join(HERE, '..', 'tests'))
        from m4_game import KidPack
        _KP = KidPack('kid')
    return _KP

_IMG = {}
def sprite(chtab, idx, which_imgs, x0=0, y0=0, flip=False):
    """(w, h, rows of MZ colours, -1 = transparent (index 0)) of chtab's image idx (0-based) at screen (x0, y0) (the
    dither of chtab 8; the others have four equal tables), flipped. The kid chtab (2: the mouse) as the game's kid pack."""
    key = (chtab, idx, which_imgs, (x0 & 1, y0 & 1) if chtab == 8 else None, flip)
    if key in _IMG: return _IMG[key]
    if chtab == 2:
        w, h, rows = kid_pack().get(idx + 1, flip)
        # (the game's pack shows the kid's black as colour 8, its value 0 being transparent; EGA shows black: DOSBox, §17)
        _IMG[key] = (w, h, [[0 if c == 8 else c for c in r] for r in rows]); return _IMG[key]
    dname, pal = chtab_res(chtab, which_imgs)
    w, h, rows = ega_image(dname, pal, pal + 1 + idx, x0, y0)
    out = [[-1 if e is None else mz(e) for e in r] for r in rows]
    if flip: out = [list(reversed(r)) for r in out]
    _IMG[key] = (w, h, out)
    return _IMG[key]

def room_screen():
    """load_intro's offscreen surface before the stars: res 951 at (0, 0), the bed res 981 ORed at (0, 142) (EGA colour
    numbers ORed: blitters_2_or onto the planes), as EGA colour numbers"""
    w, h, room = ega_image('PV', 950, 951, 0, 0)
    scr = [[(e or 0) for e in r] for r in room]
    bw, bh, bed = ega_image('PV', 980, 981, 0, 142)
    for y in range(bh):
        for x in range(bw):
            if bed[y][x]: scr[142 + y][x] |= bed[y][x]
    return scr

class Render:
    """the screens of a CutSim's frames: SDLPoP's offscreen surface with peels, plus the onscreen stars"""
    def __init__(self, cs):
        self.cs = cs
        self.which = cs.which_imgs if cs.which_imgs is not None else 1
        self.bg = [[mz(e) for e in r] for r in room_screen()]
        if cs.scene not in ROWS_FULL:
            for y in range(192, 200): self.bg[y] = [0] * 320
        for i, (x, y, _) in enumerate(STARS):                       # load_intro's draw_star(i, 0): offscreen
            self.bg[y][x] = EGA2MZ[STAR_COLORS[cs.stars0[i]]]
    def image(self, chtab, idx, x, y, flip):
        return sprite(chtab, idx, self.which, x, y, flip)
    def screens(self):
        off = [r[:] for r in self.bg]
        peels = []; stars = [None] * N_STARS
        for f in self.cs.frames:
            for (x0, y0, rows) in reversed(peels):                  # restore_peels
                for yy, r in enumerate(rows): off[y0 + yy][x0:x0 + len(r)] = r
            peels = []
            for (tab, ch, idx, x, yb, blit, flip, peel, _slot) in f['objs']:
                if ch == 8 or ch == 1: w, h, rows = self.image(ch, idx, x, yb, False)
                else:
                    w, h, rows = self.image(ch, idx, 0, 0, flip)
                    if flip: x -= w
                y = yb - h + 1
                if ch == 8: w, h, rows = self.image(ch, idx, x, y, False)      # (the dither at its place)
                clip = (0, 0, 320, 192) if ch in (2, 3, 4) else (0, 0, 320, 200)
                if peel:
                    x0, x1 = max(0, x), min(320, x + w); y0, y1 = max(0, y), min(200, y + h)
                    peels.append((x0, y0, [off[yy][x0:x1] for yy in range(y0, y1)]))
                for yy in range(h):
                    sy = y + yy
                    if not clip[1] <= sy < clip[3]: continue
                    r = rows[yy]; o = off[sy]
                    for xx in range(w):
                        sx = x + xx
                        if not clip[0] <= sx < clip[2]: continue
                        c = r[xx]
                        if c < 0:
                            if blit != 'copy': continue
                            c = BLACK0
                        o[sx] = c
            s, col = f['star']
            if s >= 0: stars[s] = col
            scr = [r[:] for r in off]
            for i, c in enumerate(stars):
                if c is not None: scr[STARS[i][1]][STARS[i][0]] = EGA2MZ[STAR_COLORS[c]]
            yield scr

    def background(self):
        return [r[:] for r in self.bg]

def boxes(cs, f):
    """the objects of frame f as drawn: [(x, y, w, h)] (for dirty-rectangle checks)"""
    out = []
    for (tab, ch, idx, x, yb, blit, flip, peel, _s) in f['objs']:
        w, h, _ = sprite(ch, idx, cs.which_imgs if cs.which_imgs is not None else 1, 0, 0, flip and ch in (2, 3, 4))
        if flip and ch in (2, 3, 4): x -= w
        out.append((x, yb - h + 1, w, h))
    return out

if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if not x.startswith('--')]
    lv = a[0]; rm = int(a[1]) if len(a) > 1 else 60
    cs = named_scene(lv, rm) if lv in SCENE_IMGS else level_scene(int(lv), rm)
    print('\n'.join(cs.lines))
    if '--png' in sys.argv:
        import titleref
        out = sys.argv[sys.argv.index('--png') + 1]; os.makedirs(out, exist_ok=True)
        for i, s in enumerate(Render(cs).screens()): titleref.png(s, os.path.join(out, 'cut%s_%03d.png' % (lv, i)))
