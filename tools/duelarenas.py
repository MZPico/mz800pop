#!/usr/bin/env python3
"""The duel's random arenas: a survey of every room of levels 1-14 as a duel arena (the user's decision "B",
2026-11-12: per match a level, per round a random room of it; the room's traps and mechanisms turned into plain floor
at its setup, its floor holes filled, multi-row rooms allowed where they are safe).

Per room, after the substitutions (substitute()):
  - the traps and mechanisms are floor: spikes, loose floors, choppers, buttons (opener, closer, a pressed one),
    gates and their door tops with floor, potions, the sword, the mirror, the level door; the modifier 0;
  - a hole of the bottom row (any tile without a floor: empty, a door top, a big pillar's top, a lattice piece) is floor:
    the room's links are zeroed as the arena's are (design 6), so below it there is nothing to land on;
  - the guards are gone and the four links are 0 (room 0: a wall on every side, the edges D14 / D15).
The runs: per row the contiguous tiles a player can stand on (kidsim tile_is_floor). The fight run: the longest run of
at least MIN_RUN tiles; the start tiles on it: 5 columns apart (as today's 2 and 7: both draw at once), centred.
The moves between runs: kidsim (DuelSim with player 2 parked outside) plays the kid's own moves from each run of the
start's component (climb up, jump up, run off an edge, step to an edge and climb down, standing and running jumps) and
records where he stands afterwards and what it cost him (a 2-row drop: one hit point). A run reached from the fight
run that cannot get back to it is a trap.
The duel itself: tests/duel_scripts/*.txt played in the arena (both start tiles, the room) against the reference arena
(level 1 room 3): whether the round results are the same and both players stay in the room on their rows.

Grades: A one row (the players cannot leave the fight run), the run >= 8; B one row, the run 6-7; C several rows, every
run reached gets back, no 2-row drop; D several rows with a 2-row drop (a hit point lost by falling); X not usable (no
run of MIN_RUN, a trap, a death, a player leaving the room). Substitutions do not change the grade: they are listed.

The duel's pool (tools/duelsim.py ARENA_POOL: the user's pick from this survey, 2026-11-12) and its table for the Z80:
--asm (build/duel_arenas.inc, a make dependency of src/duel/duel.asm; docs/duel-design.md 15).

usage: duelarenas.py [--levels 1-14] [--out DIR] [--no-render] [--no-scripts] [--no-fuzz] [--json FILE]
       duelarenas.py --room L R                    one room in detail (its tiles after the substitutions, the moves)
       duelarenas.py --render-from FILE [--levels 1-14] [--out DIR]   the contact sheets of a --json survey
       duelarenas.py --asm OUT                     the arena table for the Z80"""
import argparse, glob, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import duelsim as D
import kidsim as K
from kidsim import Char, SEQ, X_BUMP, Y_LAND, FIRST_ONSCREEN_COLUMN, TILE_SIZEX, RIGHT, LEFT, CHARID_KID, CHARID_SHADOW
from popdata import Level, RoomRenderer, T, B_TRANSP, LEVEL_TYPE, GUARD_TYPE, GUARD_SETS

from duelsim import MIN_RUN, START_GAP, TRAPS, NOFLOOR, runs, fight_run, start_cols
LEVELS = range(1, 15)
OUT = os.path.join(ROOT, 'build', 'duelarenas')            # (renders of the original art: never in git)

def substitute(level, room):
    """the room's setup as the duel does it (duelsim substitute and zero_links: in place on level) -> the substitutions
    [(pos, old tile, what)]"""
    subs = D.substitute(level, room); D.zero_links(level, room)
    return subs

def tiles(level, room):
    return [level.fg[(room - 1) * 30 + p] & 0x1F for p in range(30)]

TORCHES = (T.torch, T.torch_with_debris)
SYMS = {T.empty: ' ', T.floor: '_', T.spike: 'x', T.pillar: '|', T.gate: 'G', T.stuck: 'b', T.closer: 'b',
        T.doortop_with_floor: 'd', T.bigpillar_bottom: 'P', T.bigpillar_top: 'p', T.potion: 'o', T.loose: '~',
        T.doortop: 'D', T.mirror: 'M', T.debris: ',', T.opener: 'B', T.level_door_left: 'E', T.level_door_right: 'e',
        T.chomper: 'C', T.torch: 't', T.wall: '#', T.skeleton: 'S', T.sword: '/', T.balcony_left: '[',
        T.balcony_right: ']', T.lattice_pillar: 'l', T.lattice_down: 'v', T.lattice_small: 'v', T.lattice_left: 'v',
        T.lattice_right: 'v', T.torch_with_debris: 'T'}
def rows_text(tl): return ['%s' % ''.join(SYMS.get(t, '?') for t in tl[r * 10:r * 10 + 10]) for r in range(3)]


# ---- the arena in duelsim: any level, room, row and start columns (the duel's own setup: duelsim level_load,
# arena_set; the level's number 1 for the logic as in the duel)
class ArenaSim(D.DuelSim):
    def __init__(self, level_no, room, row, cols):
        D.DuelSim.__init__(self)
        if level_no != self.lvl: self.level_load(level_no)
        self.arena_set(-1, geometry=(room, row) + tuple(cols))
        self.round_reset()
    def match_start(self): self.next_round()           # (every round, every match in this one arena)
    def next_round(self):
        if self.aidx == -1: self.round_reset()
        else: D.DuelSim.next_round(self)
    def clone(self):
        n = K.KidSim.clone(self)
        n.pblock = {k: (list(v) if isinstance(v, list) else v) for k, v in self.pblock.items()}
        return n

def place(sim, row, col, d):
    """player 1 standing at (row, col) facing d, player 2 parked outside the room (room 0: its frame is skipped)"""
    c = Char(); c.room = sim.arena; c.curr_col = col; c.curr_row = row
    c.x = X_BUMP[col + FIRST_ONSCREEN_COLUMN] + TILE_SIZEX; c.y = Y_LAND[row + 1]
    c.direction = d; c.alive = -1; c.charid = CHARID_KID
    sim.Char = c; sim.seqtbl_offset_char(SEQ['stand']); sim.play_seq()
    sim.Kid = sim.Char.copy()
    g = sim.Guard.copy(); g.room = 0; g.alive = -1; sim.Guard = g
    sim.Char = sim.Kid.copy(); sim.Opp = sim.Guard.copy()
    for k, v in D.fresh_block().items(): setattr(sim, k, v)
    sim.hitp_curr = sim.hitp_max = 3

def macros(d):
    """the kid's own moves from a standing tile facing d: (name, [(x, y, shift) per tick]); x in the screen's terms"""
    f = 1 if d == RIGHT else -1
    idle = [(0, 0, 0)]
    edge = ([(f, 0, 1)] + idle * 10) * 5                    # careful steps to the edge
    return [
        ('up', [(0, -1, 0)] * 40),                          # jump up / grab / climb up
        ('edge+up', edge + [(0, -1, 0)] * 40),
        ('back+up', [(-f, 0, 1)] + idle * 10 + [(0, -1, 0)] * 40),   # one careful step back, then up
        ('jump', [(f, -1, 0)] * 3),                         # standing jump
        ('run6', [(f, 0, 0)] * 6),
        ('run12', [(f, 0, 0)] * 12),
        ('run20', [(f, 0, 0)] * 20),
        ('runjump4', [(f, 0, 0)] * 4 + [(f, -1, 0)] * 4),
        ('runjump8', [(f, 0, 0)] * 8 + [(f, -1, 0)] * 4),
        ('edge+turn+down', edge + [(-f, 0, 0)] + idle * 10 + [(0, 1, 0)] * 3),
        ('down', [(0, 1, 0)] * 3),
    ]

def play_macro(base, row, col, d, inputs, settle=80):
    """-> (row, col, dir, hit points lost, dead, left the room) where the kid stands after the move"""
    sim = base.clone(); place(sim, row, col, d)
    try:
        for x, y, s in inputs:
            sim.step(D.encode(x, y, s), 0)
            if sim.Kid.room != sim.arena: return None, 0, False, True
    except IndexError: return None, 0, False, True          # (a fall out of the room's rows: kidsim's tables end)
    still = 0
    for _ in range(settle):
        try: sim.step(0, 0)
        except IndexError: return None, 0, False, True
        k = sim.Kid
        if k.room != sim.arena: return None, 0, False, True
        if k.alive >= 0: return None, 3 - sim.hitp_curr, True, False
        if k.frame == 15 and k.action == K.A_STAND: still += 1
        else: still = 0
        if still >= 3: break
    k = sim.Kid
    if still < 3: return None, 3 - sim.hitp_curr, False, False
    return (k.curr_row, k.curr_col, k.direction), 3 - sim.hitp_curr, False, False

def run_of(rs, row, col):
    for i, (r, a, b) in enumerate(rs):
        if r == row and a <= col <= b: return i
    return None

def moves_graph(base, rs, start_run):
    """the runs reached from start_run by the kid's moves: {run: {run2: (macro, hp lost)}}, deaths, exits"""
    graph = {}; todo = [start_run]; deaths = []; exits = []
    while todo:
        i = todo.pop()
        if i in graph: continue
        graph[i] = {}
        r, a, b = rs[i]
        for col in range(a, b + 1):
            for d in (RIGHT, LEFT):
                for name, inp in macros(d):
                    pos, hp, dead, left = play_macro(base, r, col, d, inp)
                    if dead: deaths.append((i, col, d, name)); continue
                    if left: exits.append((i, col, d, name)); continue
                    if pos is None: continue
                    j = run_of(rs, pos[0], pos[1])
                    if j is None or j == i: continue
                    if j not in graph[i] or graph[i][j][1] > hp: graph[i][j] = (name, hp)
                    todo.append(j)
    return graph, deaths, exits

def reach(graph, frm):
    seen = {frm}; todo = [frm]
    while todo:
        i = todo.pop()
        for j in graph.get(i, {}):
            if j not in seen: seen.add(j); todo.append(j)
    return seen

# ---- the duel's scripts in the arena
SCRIPTS = sorted(glob.glob(os.path.join(ROOT, 'tests', 'duel_scripts', '*.txt')))
_ref = {}
def script_run(sim_factory, path):
    inputs, opts = D.read_duel_script(path)
    sim = sim_factory(); rows = {sim.arena_row} if hasattr(sim, 'arena_row') else {D.ARENA_ROW}
    lines = []; stray = 0; crash = False
    for in1, in2 in inputs:
        try: lines.append(sim.step(in1, in2)); lines.append(sim.duel_line)
        except IndexError: crash = True; break             # (fell out of the room's rows)
        for c in (sim.Kid, sim.Guard):
            if c.room != sim.arena: crash = True
            elif c.curr_row not in rows: stray += 1
        if crash or sim.match == D.MATCH_QUIT: break
    return D.round_results(lines), stray, sim.score[:], crash

def scripts_check(level_no, room, row, cols):
    out = []
    for p in SCRIPTS:
        if p not in _ref: _ref[p] = script_run(lambda: D.DuelSim(), p)
        got = script_run(lambda: ArenaSim(level_no, room, row, cols), p)
        out.append((os.path.basename(p), got[0] == _ref[p][0] and got[2] == _ref[p][2], got[1], got[3]))
    return out

# ---- random duels in the arena: both players' keys at random (held 1-12 ticks; mostly towards the other one and the
# button, so they fight, push and get pushed at the walls and the edges), rematch after a match
FUZZ_SEEDS, FUZZ_TICKS = 6, 1200
def fuzz(level_no, room, row, cols, rs, others=(), seeds=FUZZ_SEEDS, ticks=FUZZ_TICKS):
    """others: the other runs reached: one more seed per run with both players starting on it"""
    import random
    out = dict(crash=0, left=0, inwall=0, rounds=0, runs=set(), ticks=0, where=[])
    for seed, start in [(s, None) for s in range(seeds)] + [(seeds + k, rs[j]) for k, j in enumerate(others)]:
        rng = random.Random(seed * 7919 + level_no * 131 + room)
        if start is None: sim = ArenaSim(level_no, room, row, cols)
        else: sim = ArenaSim(level_no, room, start[0], (start[1], start[2]))
        held = [[0, 0, 0, 0], [0, 0, 0, 0]]          # x y shift ticks
        for t in range(ticks):
            ins = []
            for p in (0, 1):
                me, other = (sim.Kid, sim.Guard) if p == 0 else (sim.Guard, sim.Kid)
                h = held[p]
                if h[3] <= 0:
                    tw = 1 if other.x > me.x else -1
                    k = rng.choices(range(8), weights=(2, 4, 2, 1.5, 1, 3, 1, 1))[0]
                    h[:3] = [(0, 0, 0), (tw, 0, 0), (-tw, 0, 0), (0, -1, 0), (0, 1, 0), (0, 0, 1), (tw, 0, 1),
                             (tw, -1, 0)][k]
                    h[3] = rng.randint(1, 12)
                h[3] -= 1
                ins.append(D.encode(h[0], h[1], h[2], rematch=sim.match in (D.MATCH_P1, D.MATCH_P2)))
            r0 = sim.rounds
            try: sim.step(*ins)
            except IndexError: out['crash'] += 1; out['where'].append((start, t)); break
            out['ticks'] += 1
            out['rounds'] += sim.rounds != r0
            bad = False
            for c in (sim.Kid, sim.Guard):
                if c.room != sim.arena: bad = True
                elif c.frame == 15 and c.action == K.A_STAND:
                    if 0 <= c.curr_col < 10 and 0 <= c.curr_row < 3:
                        if sim.level.fg[(room - 1) * 30 + c.curr_row * 10 + c.curr_col] & 0x1F == T.wall: out['inwall'] += 1
                        j = run_of(rs, c.curr_row, c.curr_col)
                        if j is not None: out['runs'].add(j)
            if bad: out['left'] += 1; out['where'].append((start, t)); break
    return out

# ---- the room change's cost: the full room draw's frames estimated from its op count (a fit over docs/perf.md's six
# measured room changes, M8a part 27: l01r01 74.66, l01r07 77.27, l03r16 81.78, l04r04 68.07, l05r24 84.73, l10r01
# 89.48 frames at 1 MB; residuals within 6.5 frames)
DRAW_FIT = (0.291, 32.80)
def room_ops(level, room):
    rr = RoomRenderer(level, ega=True); rr.paint = lambda: None
    rr.draw_room(room)
    return sum(len(rr.ops[k]) for k in ('back', 'mid', 'fore'))

# ---- the survey
def survey_room(level_no, room, scripts=True, fuzzing=True):
    lv = Level(level_no); lv.fg = bytearray(lv.fg); lv.bg = bytearray(lv.bg)
    orig = tiles(lv, room)
    subs = substitute(lv, room)
    tl = tiles(lv, room)
    rs = runs(tl)
    ops = room_ops(lv, room)
    fr = fight_run(rs)
    res = dict(level=level_no, room=room, orig=rows_text(orig), rows=rows_text(tl), subs=subs, runs=rs,
               torches=sum(1 for t in tl if t in TORCHES), fight=fr, grade='X', notes=[], ops=ops,
               draw=round(DRAW_FIT[0] * ops + DRAW_FIT[1], 1))
    if fr is None:
        res['notes'].append('no run of %d' % MIN_RUN); return res
    c1, c2 = start_cols(fr)
    res['cols'] = (c1, c2); res['row'] = fr[0]
    base = ArenaSim(level_no, room, fr[0], (c1, c2))
    i0 = rs.index(fr)
    graph, deaths, exits = moves_graph(base, rs, i0)
    res['graph'] = {i: dict(v) for i, v in graph.items()}
    reached = set(graph)
    back = [i for i in reached if i0 not in reach(graph, i)]
    drop2 = sorted({(i, j) for i, v in graph.items() for j, (nm, hp) in v.items() if hp > 0})
    # a 2-row drop counts only when it is the only way (the one move kidsim found that costs a hit point)
    res.update(reached=sorted(reached), traps=back, deaths=deaths, exits=exits, drop2=drop2)
    rows_used = sorted({rs[i][0] for i in reached})
    res['rows_used'] = rows_used
    L = fr[2] - fr[1] + 1
    if deaths: res['notes'].append('death by a move: %s' % (deaths[:2],))
    if exits: res['notes'].append('leaves the room: %s' % (exits[:2],))
    if back: res['notes'].append('trap: runs %s cannot get back' % [rs[i] for i in back])
    if deaths or exits or back: res['grade'] = 'X'
    elif len(reached) == 1: res['grade'] = 'A' if L >= 8 else 'B'
    elif drop2: res['grade'] = 'D'
    else: res['grade'] = 'C'
    if fuzzing:
        fz = fuzz(level_no, room, fr[0], (c1, c2), rs, others=sorted(reached - {i0}))
        res['fuzz'] = dict(fz, runs=sorted(fz['runs']))
        extra = sorted(fz['runs'] - reached)
        if fz['crash'] or fz['left']:
            res['grade'] = 'X'; res['notes'].append('random duels: %d fell out of the room %s' % (fz['crash'] + fz['left'], fz['where'][:3]))
        if fz['inwall']: res['notes'].append('random duels: %d ticks standing in a wall' % fz['inwall'])
        if extra: res['notes'].append('random duels reach runs %s' % [rs[i] for i in extra])
        res['notes'].append('random duels: %d rounds in %d ticks' % (fz['rounds'], fz['ticks']))
    if scripts and res['grade'] != 'X':
        sc = scripts_check(level_no, room, fr[0], (c1, c2))
        res['scripts'] = sc
        same = sum(1 for s in sc if s[1]); stray = sum(s[2] for s in sc)
        if any(s[3] for s in sc):
            res['grade'] = 'X'; res['notes'].append('a script falls out of the room: %s' % [s[0] for s in sc if s[3]])
        res['notes'].append('scripts %d/%d as the reference%s' % (same, len(sc), ', off the row %d ticks' % stray if stray else ''))
    return res

def sub_summary(subs):
    from collections import Counter
    c = Counter(w for _, _, w in subs)
    return ', '.join('%s %d' % (k, v) for k, v in sorted(c.items()))

# ---- the pictures: the room as the duel draws it, both players at their start tiles
DUEL_LOOK = True
class KidImages:
    """build/assets/kid.pack images as the Z80's sprite kernel sees them; P2 in the duel's look (duel.asm d_sdraw,
    DUEL_LOOK 0: a blue suit, grey hair)"""
    def __init__(self):
        A = os.path.join(ROOT, 'build', 'assets')
        self.pack = open(os.path.join(A, 'kid.pack'), 'rb').read(); self.dir = open(os.path.join(A, 'kid.dir'), 'rb').read()
        self.info = json.load(open(os.path.join(A, 'kid.json')))['images']; self.cache = {}
    @staticmethod
    def p2(c):
        """colour index bits: 0 B, 1 R, 2 G, 3 I. Where B: R, G cleared; where R alone of B R G: R cleared, I set"""
        b, r, g, i = c & 1, (c >> 1) & 1, (c >> 2) & 1, (c >> 3) & 1
        if b: r = g = 0
        elif r and not g: r = 0; i = 1
        return b | r << 1 | g << 2 | i << 3
    def get(self, key):
        pid, mirror, p2 = key
        if key in self.cache: return self.cache[key]
        d = self.dir[pid * 8:pid * 8 + 8]; off = (d[0] << 16) | (d[1] << 8) | d[2]; wb, h, flags = d[3], d[4], d[5]
        n = wb * h
        if flags & 1:
            mask = self.pack[off:off + n]; planes = [self.pack[off + n * (p + 1):off + n * (p + 2)] for p in range(4)]
        else:
            planes = [self.pack[off + n * p:off + n * (p + 1)] for p in range(4)]
            mask = bytes(planes[0][i] | planes[1][i] | planes[2][i] | planes[3][i] for i in range(n))
        w = self.info[str(pid)]['w']; rows = []
        for y in range(h):
            row = []
            for x in range(wb * 8):
                o = y * wb + (x >> 3); bit = 1 << (x & 7)
                if mask[o] & bit:
                    c = sum(1 << p for p in range(4) if planes[p][o] & bit)
                    row.append(self.p2(c) if p2 else c)
                else: row.append(-1)
            row = row[:w]
            rows.append(list(reversed(row)) if mirror else row)
        self.cache[key] = (w, h, rows)
        return self.cache[key]
    def mono_colour(self, c): return 0

_kimg = None
def render(res):
    """the arena at round start: the substituted room (EGA art, as the game shows it) and both players"""
    global _kimg
    if _kimg is None: _kimg = KidImages()
    sim = ArenaSim(res['level'], res['room'], res['row'], res['cols'])
    rr = RoomRenderer(sim.level, ega=True)
    rr.draw_room(res['room'])
    rr.sets[2] = _kimg
    for p, c in enumerate((sim.Kid, sim.Guard)):
        sim.Char = c.copy(); sim.load_frame_to_obj()
        img = sim.cur_frame[0]
        if img == 255: continue
        mirror = c.direction >= 0
        ox = sim.obj_x; x = int(ox * 8 / 7) if ox >= 0 else -int((-ox) * 8 / 7)
        w, h, _ = _kimg.get((img + 1, mirror, p == 1))
        if mirror: x -= w
        rr.ops['mid'].append((2, (img + 1, mirror, p == 1), x, sim.obj_y - h + 1, B_TRANSP))
    return rr.paint()

def contact_sheet(level_no, results, out):
    from PIL import Image, ImageDraw, ImageFont
    cands = [r for r in results if r['grade'] != 'X']
    if not cands: return None
    try: font = ImageFont.truetype('DejaVuSans.ttf', 18); small = ImageFont.truetype('DejaVuSans.ttf', 15)
    except OSError: font = small = ImageFont.load_default()
    cols = 3; cw, ch = 640, 400 + 70; pad = 12
    nrow = (len(cands) + cols - 1) // cols
    kind = 'palace' if LEVEL_TYPE[level_no] else 'dungeon'
    sheet = Image.new('RGB', (cols * (cw + pad) + pad, 44 + nrow * (ch + pad) + pad), (32, 32, 36))
    dr = ImageDraw.Draw(sheet)
    dr.text((pad, 10), 'level %d (%s): %d candidates of %d rooms' % (level_no, kind, len(cands), len(results)),
            fill=(240, 240, 240), font=font)
    for k, r in enumerate(cands):
        x0 = pad + (k % cols) * (cw + pad); y0 = 44 + (k // cols) * (ch + pad)
        im = render(r).convert('RGB').resize((640, 400), Image.NEAREST)
        sheet.paste(im, (x0, y0))
        gc = {'A': (120, 230, 120), 'B': (200, 230, 120), 'C': (240, 200, 90), 'D': (240, 140, 90)}[r['grade']]
        dr.text((x0, y0 + 404), 'L%d R%d  grade %s  row %d cols %d,%d  run %d-%d  torches %d  draw ~%d fr' % (
            level_no, r['room'], r['grade'], r['row'], r['cols'][0], r['cols'][1], r['fight'][1], r['fight'][2],
            r['torches'], r['draw']), fill=gc, font=font)
        sub = sub_summary(r['subs']) or 'no substitutions'
        extra = ('rows %s' % ','.join(map(str, r['rows_used']))) if len(r['rows_used']) > 1 else 'one row'
        if r.get('drop2'): extra += ', 2-row drop'
        sc = r.get('scripts')
        if sc: extra += ', scripts %d/%d' % (sum(1 for s in sc if s[1]), len(sc))
        dr.text((x0, y0 + 428), sub, fill=(220, 220, 220), font=small)
        dr.text((x0, y0 + 448), extra, fill=(180, 180, 200), font=small)
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, 'level%02d_%s.png' % (level_no, kind))
    sheet.save(path)
    return path

def write_asm(out):
    """build/duel_arenas.inc: duelsim's arena table for duel.asm's P_w2 (w_lvtab: per level its pool's first entry and
    count; w_pool: per entry the room + 32 x the row, player 1's column (player 2's: + START_GAP); w_cls: per tile type
    duelsim tile_class: 1 a trap or mechanism, 2 no floor)"""
    A = D.arenas()
    L = ['; generated by tools/duelarenas.py --asm from tools/duelsim.py ARENA_POOL (do not edit): the random arenas,',
         '; docs/duel-design.md 15. Entry 0 the fixed arena (level 1 room 3), then each level\'s pool',
         'W_LEVELS        equ     %d' % D.ARENA_LEVELS, 'W_GAP           equ     %d' % START_GAP,
         'W_RND_ADD       equ     0x%04x' % D.RND_ADD, 'W_ENTRIES       equ     %d' % len(A),
         'w_lvtab:']
    for n in range(1, D.ARENA_LEVELS + 1):
        first, cnt = D.level_slice(n)
        assert all(A[first + i][0] == n for i in range(cnt))
        L.append('                db      %d, %d               ; level %d (%s)' % (first, cnt, n, 'palace' if LEVEL_TYPE[n] else 'dungeon'))
    L.append('w_pool:')
    for i, (n, room, row, c1) in enumerate(A):
        assert 1 <= room <= 24 and 0 <= row <= 2 and 0 <= c1 and c1 + START_GAP <= 9
        L.append('                db      %d + %d * 32, %d        ; %d: level %d room %d, row %d, columns %d and %d' % (
            room, row, c1, i, n, room, row, c1, c1 + START_GAP))
    L.append('w_cls:          db      ' + ', '.join(str(D.tile_class(t)) for t in range(32)))
    assert len(A) < 255
    open(out, 'w').write('\n'.join(L) + '\n')
    print('%s: %d arenas' % (out, len(A)))

def parse_levels(s):
    out = []
    for part in s.split(','):
        if '-' in part: a, b = part.split('-'); out += range(int(a), int(b) + 1)
        else: out.append(int(part))
    return out

def line(r):
    run = '%d:%d-%d' % r['fight'] if r['fight'] else '-'
    return 'L%-2d R%-2d %s  %-10s %-10s %-10s run %-7s cols %-5s torches %d  %s%s%s' % (
        r['level'], r['room'], r['grade'], *r['rows'], run,
        '%d,%d' % r['cols'] if 'cols' in r else '-', r['torches'],
        sub_summary(r['subs']) or '-', ('; rows %s' % r['rows_used']) if len(r.get('rows_used', [])) > 1 else '',
        ('; ' + '; '.join(r['notes'])) if r['notes'] else '')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--levels', default='1-14')
    ap.add_argument('--out', default=OUT)
    ap.add_argument('--no-render', action='store_true')
    ap.add_argument('--no-scripts', action='store_true')
    ap.add_argument('--no-fuzz', action='store_true')
    ap.add_argument('--room', nargs=2, type=int)
    ap.add_argument('--json')
    ap.add_argument('--render-from', help='the contact sheets from a --json survey')
    ap.add_argument('--asm', help="the arena table for src/duel/duel.asm (build/duel_arenas.inc) from duelsim's pool")
    a = ap.parse_args()
    if a.asm:
        write_asm(a.asm); return
    if a.render_from:
        allres = json.load(open(a.render_from))
        for n in parse_levels(a.levels):
            p = contact_sheet(n, [r for r in allres if r['level'] == n], a.out)
            if p: print('  ->', p, flush=True)
        return
    if a.room:
        r = survey_room(*a.room, scripts=not a.no_scripts, fuzzing=not a.no_fuzz)
        print('before:', *['|%s|' % x for x in r['orig']], sep='\n  ')
        print('after: ', *['|%s|' % x for x in r['rows']], sep='\n  ')
        print(line(r))
        for i, v in r.get('graph', {}).items():
            for j, (nm, hp) in v.items(): print('  run %s -> %s by %s%s' % (r['runs'][i], r['runs'][j], nm, ' (-%d hp)' % hp if hp else ''))
        for s in r.get('scripts', []): print('  ', s)
        return
    allres = []
    for n in parse_levels(a.levels):
        lv = Level(n); res = []
        for room in range(1, lv.used_rooms + 1):
            r = survey_room(n, room, scripts=not a.no_scripts, fuzzing=not a.no_fuzz)
            res.append(r); print(line(r), flush=True)
        allres += res
        if not a.no_render:
            p = contact_sheet(n, res, a.out)
            if p: print('  ->', p, flush=True)
    print()
    for n in parse_levels(a.levels):
        rs = [r for r in allres if r['level'] == n]
        cnt = {g: sum(1 for r in rs if r['grade'] == g) for g in 'ABCDX'}
        print('level %2d %-7s rooms %2d  A %d B %d C %d D %d X %d  guard set %s' % (
            n, 'palace' if LEVEL_TYPE[n] else 'dungeon', len(rs), cnt['A'], cnt['B'], cnt['C'], cnt['D'], cnt['X'],
            GUARD_SETS[GUARD_TYPE[n]] if GUARD_TYPE[n] >= 0 else '-'))
    if a.json:
        def clean(r):
            r = dict(r); r.pop('graph', None); return r
        json.dump([clean(r) for r in allres], open(a.json, 'w'), indent=1, default=str)

if __name__ == '__main__':
    main()
