#!/usr/bin/env python3
"""Speed roadmap measurements (docs/perf.md "Speed roadmap (2026-11-08)"): the room change and whole stretches by stage.
  enter OUTDIR LV:ROOM ...    for each room a script (kidsim only) where the kid runs or walks into it from a neighbour
                              (left, right, or falls in from above), written as l<LV>r<ROOM>.txt; prints the tick of
                              the room change
  stages SCRIPT TICK          profile that tick alone (mz800emu's call profiler) and print the room change by stage
                              (inclusive frames): the op-list build (room_ops with slices_build), the cell buckets
                              (bkt_build), the 15 cells (run_rect: the black fill, laying the pieces (rec_lay, of it
                              lay_piece16 and the masked cmx_* rows), the shadow write, the copy to VRAM (blq_*
                              inside the cells), the scan), the overlay loads, the hooks after the draw (room_drawn:
                              flames_build, the caches), the kid's logic, the object pass; and the tick's RAM-disk
                              accesses (data-port reads / writes, seeks) counted by I/O breakpoints
  range SCRIPT T0 T1          ticks T0..T1-1 of a script (perfcheck's stretches: walk_level1 30 60, fight1 60 160): the
                              frames a tick (tick_done to tick_done, paced) and the work (ml_go to tick_done) as
                              median / p90 / mean, the ticks at the 4-frame floor, and the mean frames a tick by stage
                              (mz800emu's call profiler over the stretch, inclusive): the logic (kid_tick, the guard's
                              tick_pre / tick_post, the trobs and mobs), the redraw (view_redraw), the people's
                              placing (people_place, of it char_fetch), the object pass (obj_chunk: restore, flames,
                              torch cache, falling floors, people, fore), the copy (pf_blit1), the beam wait (pf_seq)
The routines of the room overlay (W1) are named from build/ovl_room.sym."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path[:0] = [os.path.join(ROOT, 'tests'), HERE]
import kidsim
from popdata import Level, T
import tickcost as TC
from emu import Emu
import m4_game as G
from m3_test import syms

def enter(outdir, lv, room):
    """a start in a neighbour room from which the kid gets into room: run / walk towards it"""
    L = Level(lv); sim0 = kidsim.KidSim(Level(lv))
    left, right, up, down = sim0.links(room)
    tries = []
    for nb, d in ((left, 1), (right, -1)):
        if not nb: continue
        for row in range(3):
            for col in ((9, 8, 7, 6, 5) if d == 1 else (0, 1, 2, 3, 4)):
                tries.append((nb, row * 10 + col, 0 if d == 1 else -1, d))
    if up:
        for p in range(20, 30): tries.append((up, p, 0, 1)); tries.append((up, p, -1, -1))
    for st in tries:
        for pat in ('run', 'walk'):
            mv = [((st[3], 0, 0) if pat == 'run' else (st[3], 0, 1))] * 40
            try:
                sim = kidsim.KidSim(Level(lv), start=st[:3], multi_level=True)
            except Exception:
                continue
            r0 = sim.drawn_room
            for t, m in enumerate(mv):
                sim.step(*m)
                if sim.game_over or sim.Kid.alive >= 0: break
                if sim.drawn_room != r0:
                    if sim.drawn_room == room and t >= 3:
                        mv = mv[:t + 4]
                        path = os.path.join(outdir, 'l%02dr%02d.txt' % (lv, room))
                        with open(path, 'w') as f:
                            f.write('# level %d\n# start %d:%d:%d\n' % (lv, st[0], st[1], st[2]))
                            f.write('# into room %d at tick %d (tools/roomchange.py)\n' % (room, t))
                            for (x, y, s) in mv: f.write('%d %d %d\n' % (x, y, s))
                        return path, t
                    break
    return None, None

STAGES = [
    ('tick', None),
    ('the room draw (draw_room_full)', 'draw_room_full'),
    ('  op-list build (room_ops)', 'room_ops'),
    ('  cell buckets (bkt_build)', 'bkt_build'),
    ('  15 cells (run_rect)', 'run_rect'),
    ('    black fill', 'fill_black'),
    ('    laying the ops (rec_lay)', 'rec_lay'),
    ('      lay_piece16', 'lay_piece16'),
    ('      masked rows cmx_1/2/4', ('cmx_1', 'cmx_2', 'cmx_4')),
    ('      seeks (far_seek_entry, RD_LV_ADDR)', ('far_seek_entry', 'RD_LV_ADDR')),
    ('      wall patterns (wp_*)', ('wp_botdiv', 'wp_middiv')),
    ('    shadow write', 'shadow_write'),
    ('    copy to VRAM (blq_*)', ('blq_1', 'blq_2', 'blq_3', 'blq_4', 'blq_5', 'blq_6', 'blq_7', 'blq_8')),
    ('overlay loads (ovl_w1)', 'ovl_w1'),
    ('after the draw (room_drawn)', 'room_drawn'),
    ('  flames_build', 'flames_build'),
    ('kid logic (kid_tick)', 'kid_tick'),
    ('object pass (draw_objects)', 'draw_objects'),
]

def stages(sp, tick):
    names = {}
    for k, v in syms(os.path.join(ROOT, 'build', 'ovl_room.sym')).items():
        if 0x7C00 <= v < 0x8000: names.setdefault('%04X' % v, k)
    fr, rows = TC.emu_profile(sp, [tick], 0)[tick]
    inc = {}; calls = {}
    for i, e, c, n in rows:
        n = names.get(n, n); inc[n] = inc.get(n, 0) + i; calls[n] = calls.get(n, 0) + c
    print('%s tick %d: %.2f frames (lay_piece16 %d calls, rec_lay %d, cmx rows %d)' % (os.path.basename(sp), tick, fr,
          calls.get('lay_piece16', 0), calls.get('rec_lay', 0), sum(calls.get(x, 0) for x in ('cmx_1', 'cmx_2', 'cmx_4'))))
    for lab, s in STAGES:
        v = fr if s is None else sum(inc.get(x, 0) for x in s) if isinstance(s, tuple) else inc.get(s, 0)
        print('  %-44s %7.2f' % (lab, v))
    # blq inside the cells: the object pass's copies use them too
    print('  (pf_blit1, the object pass copies: %.2f)' % inc.get('pf_blit1', 0))
    io(sp, tick)

def io(sp, tick):
    moves, patches = kidsim.read_script(sp)
    with Emu() as e:
        S, n = TC.emu_setup(e, sp)
        e.call('bp_add', addr=S['tick_done'])
        for t in range(tick): e.run(400)
        ids = {nm: e.call('bp_create_with_init', fields=['type', 'port', 'action'], type=ty, port=port, action='continue')['id']
               for nm, ty, port in (('reads', 'IORQ_R', 0xEA), ('writes', 'IORQ_W', 0xEA), ('seeks', 'IORQ_W', 0xEB), ('pages', 'IORQ_W', 0xE9))}
        h0 = {b['id']: b['hits'] for b in e.call('bp_list')['breakpoints']}
        e.run(400)
        h1 = {b['id']: b['hits'] for b in e.call('bp_list')['breakpoints']}
    print('  RAM disk this tick: ' + ', '.join('%s %d' % (nm, h1[i] - h0.get(i, 0)) for nm, i in ids.items()))

RANGE = [
    ('logic: kid_tick', 'kid_tick'), ('logic: tick_pre + tick_post (guard)', ('tick_pre', 'tick_post')),
    ('logic: process_trobs + do_mobs', ('process_trobs', 'do_mobs')),
    ('redraw (view_redraw)', 'view_redraw'), ('  of it tile_redraw', 'tile_redraw'),
    ('people_place', 'people_place'), ('  of it char_fetch', 'char_fetch'),
    ('object pass (obj_chunk)', 'obj_chunk'), ('  restore_shadow', 'restore_shadow'), ('  flames_lay', 'flames_lay'),
    ('  torch cache (tc_try, tc_save)', ('tc_try', 'tc_save')), ('  falling floors (lay_mob)', 'lay_mob'),
    ('  people (people_chunk)', 'people_chunk'), ('    of it spr_draw', 'spr_draw'), ('  fore (lay_fore_rect)', 'lay_fore_rect'),
    ('copy (pf_blit1)', 'pf_blit1'), ('beam wait (pf_seq)', 'pf_seq'), ('interrupt (isr)', 'isr'),
]

def prange(sp, t0, t1):
    import busyrooms as BR
    fw = BR.frames(sp)[t0:t1]
    fr = [f for f, w in fw]; wk = [w for f, w in fw]
    pct = BR.pct; mean = lambda v: sum(v) / len(v)
    print('%s ticks %d-%d: frames median %.2f p90 %.2f mean %.2f; work median %.2f p90 %.2f mean %.2f; ticks at the floor (< 4.05) %d of %d' % (
        os.path.basename(sp), t0, t1, pct(fr, .5), pct(fr, .9), mean(fr), pct(wk, .5), pct(wk, .9), mean(wk),
        sum(1 for f in fr if f < 4.05), len(fr)))
    moves, patches = kidsim.read_script(sp)
    with Emu() as e:
        S, n = TC.emu_setup(e, sp)
        names = {}
        for k, v in S.items(): names.setdefault(v, k)
        e.call('bp_add', addr=S['tick_done'])
        for t in range(t0): e.run(400)
        e.call('profiler_reset'); e.call('profiler_start')
        for t in range(t0, t1): e.run(400)
        e.call('profiler_stop')
        r = e.call('profiler_get', limit=1000)
    inc = {}
    for it in r['entries']:
        nm = names.get(it['addr'], '%04X' % it['addr']); inc[nm] = inc.get(nm, 0) + it['incl_cycles'] / (t1 - t0) / TC.FRAME
    for lab, s in RANGE:
        v = sum(inc.get(x, 0) for x in s) if isinstance(s, tuple) else inc.get(s, 0)
        print('  %-40s %6.2f' % (lab, v))

def main():
    a = sys.argv[1:]
    if not a: sys.exit(__doc__)
    if a[0] == 'enter':
        os.makedirs(a[1], exist_ok=True)
        for x in a[2:]:
            lv, room = (int(v) for v in x.split(':'))
            p, t = enter(a[1], lv, room)
            print('level %2d room %2d: %s' % (lv, room, ('%s, the room change at tick %d' % (p, t)) if p else 'no entry found'))
    elif a[0] == 'range':
        prange(TC.script_path(a[1]), int(a[2]), int(a[3]))
    elif a[0] == 'stages':
        stages(TC.script_path(a[1]), int(a[2]))

if __name__ == '__main__':
    main()
