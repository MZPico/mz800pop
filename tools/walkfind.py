#!/usr/bin/env python3
"""Find a control script that finishes a level, by best-first search over short control macros in
tools/kidsim.py (no guards). Used to produce long, realistic test scripts (tests/m4_scripts/walk_level*.txt).
usage: walkfind.py <level> <out.txt> [max_expansions] [exit|drink]"""
import copy, heapq, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kidsim
from popdata import Level, T

MACROS = {
    'R': [(1, 0, 0)] * 4, 'L': [(-1, 0, 0)] * 4, 'r': [(1, 0, 1)] * 4, 'l': [(-1, 0, 1)] * 4,      # run / careful step
    'S': [(0, 0, 0)] * 4,
    'U': [(0, -1, 0)] * 6, 'Us': [(0, -1, 1)] * 10, 'D': [(0, 1, 0)] * 6, 'Ds': [(0, 1, 1)] * 6,     # up / climb, down / hang
    'JR': [(1, -1, 0)] * 6, 'JL': [(-1, -1, 0)] * 6,                                                  # jumps
    'G': [(0, 0, 1)] * 6,                                                                             # hold shift (grab / pick up)
}

def key(sim):
    K = sim.Kid
    return (K.room, K.x, K.y, K.frame, K.direction & 1, K.curr_row, K.action, K.fall_y,
            bytes(sim.level.bg), bytes(sim.level.fg), tuple(sim.ctrl1), sim.hitp_curr, sim.leveldoor_open)

def search(level_no, max_exp=200000, goal='exit', prefix=None):
    lv = Level(level_no); sim = kidsim.KidSim(lv)
    potions0 = sum(1 for i in range(720) if lv.fg[i] & 31 == T.potion)
    if prefix:                                     # continue from the end of an existing script
        for (x, y, sh) in kidsim.read_script(prefix)[0]: sim.step(x, y, sh)
    else:
        for _ in range(10): sim.step(0, 0, 0)
    seen = {key(sim)}
    # priority: rooms visited first (exploration), then the exit door distance once its room is known
    if goal.startswith('at'):                      # 'at<room>:<pos>': standing on that tile
        at_room, at_pos = (int(v) for v in goal[2:].split(':')); door_room = at_room
    else:
        door_room = next((r for r in range(1, 25) for p in range(30) if lv.fg[(r - 1) * 30 + p] & 31 == {'drink': T.potion, 'sword': T.sword}.get(goal, T.level_door_left)), None)
    # room-graph distance to the exit door's room (ignores gates and walls: only a guide)
    dist = {door_room: 0}; frontier = [door_room]
    while frontier:
        nxt = []
        for r in frontier:
            o = 1952 + (r - 1) * 4
            for nb in lv.raw[o:o + 4]:
                if nb and nb not in dist: dist[nb] = dist[r] + 1; nxt.append(nb)
        frontier = nxt
    heap = [(0, 0, [], sim)]; n = 0; count = 0; t0 = time.time(); visits = {}
    while heap and n < max_exp:
        pr, _, path, s = heapq.heappop(heap); n += 1
        for name, moves in MACROS.items():
            s2 = s.clone(); dead = False; found_sword = False
            for (x, y, sh) in moves:
                s2.step(x, y, sh)
                if 229 <= s2.Kid.frame < 238: found_sword = True
                if s2.Kid.alive >= 0: dead = True; break
                if s2.level_done: break
            if dead: continue
            if goal == 'exit': done = s2.level_done
            elif goal == 'climb_right': done = 140 <= s2.Kid.frame < 150 and s2.Kid.direction >= 0
            elif goal == 'climb_left': done = 140 <= s2.Kid.frame < 150 and s2.Kid.direction < 0
            elif goal == 'sword': done = found_sword
            elif goal.startswith('at'): done = s2.Kid.room == at_room and s2.Kid.curr_row * 10 + s2.Kid.curr_col == at_pos and s2.Kid.frame == 15
            else: done = sum(1 for i in range(720) if s2.level.fg[i] & 31 == T.potion) < potions0 and s2.Kid.frame == 15
            if done:
                print('found after %d expansions (%.0fs), %d macros' % (n, time.time() - t0, len(path) + 1)); return path + [name]
            k = key(s2)
            if k in seen: continue
            seen.add(k)
            K = s2.Kid
            cell = (K.room, K.curr_row, K.curr_col, s2.leveldoor_open)
            visits[cell] = visits.get(cell, 0) + 1
            score = 25 * dist.get(K.room, 9) + 0.3 * len(path) + 2 * visits[cell] - (30 if s2.leveldoor_open else 0)
            heapq.heappush(heap, (score, count, path + [name], s2)); count += 1
        if n % 2000 == 0: print('  %d expanded, %d queued, %.0fs, best score %.1f' % (n, len(heap), time.time() - t0, pr)); sys.stdout.flush()
    return None

def write_script(level_no, macros, out, prefix=None):
    lines = [l for l in open(prefix).read().split('\n') if l and not l.startswith('#')] if prefix else ['0 0 0'] * 10
    for m in macros: lines += ['%d %d %d' % mv for mv in MACROS[m]]
    if not prefix: lines += ['0 0 0'] * 20
    open(out, 'w').write('\n'.join(lines) + '\n')
    print('wrote', out, len(lines), 'ticks:', ' '.join(macros))

if __name__ == '__main__':
    lv = int(sys.argv[1]); out = sys.argv[2]; mx = int(sys.argv[3]) if len(sys.argv) > 3 else 200000
    goal = sys.argv[4] if len(sys.argv) > 4 else 'exit'
    prefix = sys.argv[5] if len(sys.argv) > 5 else None   # optional: a script to continue from
    path = search(lv, mx, goal, prefix)
    if path: write_script(lv, path, out, prefix)
    else: print('no walkthrough found')
