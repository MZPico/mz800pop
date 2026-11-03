#!/usr/bin/env python3
"""RAM-disk accesses per tick (docs/perf.md "M8a part 9"): the reads of the data port (IN from RAM_DATA 0xEA: every
INIR / INI / IN byte), the writes to it (OUT / OTIR) and the address and page writes (0xEB, 0xE9), counted by the
emulator's I/O breakpoints (mz800emu smart breakpoints IORQ_R / IORQ_W with a 'continue' action: they count `hits`
and never stop), read at a breakpoint on tick_done every tick; the stretches as tools/perfcheck.py runs them (same
setup, same script), on the emulated RAM disk's size (POP800_RD_SIZE). Prints per stretch the frames per tick, the
accesses per tick and the cost of 1, 2 and 3 wait states (T) on every data-port read in frames per tick (71,136 T).
usage: rdreads.py [stretch name substring...]"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path[:0] = [os.path.join(ROOT, 'tests'), HERE]
import m4_game as G, kidsim
from emu import Emu
F = 71136
STRETCHES = {
    'walk_level1 30-60': ('walk_level1.txt', 30, 60),
    'room change (walk_level1 89)': ('walk_level1.txt', 89, 90),
    'fight1 60-160': ('fight1.txt', 60, 160),
    'traps_b1 0-300': ('traps_b1.txt', 0, 300),
}
PORTS = (('rd', 'IORQ_R', 0xEA), ('wr', 'IORQ_W', 0xEA), ('addr', 'IORQ_W', 0xEB), ('page', 'IORQ_W', 0xE9))

def hits(e, ids):
    h = {b['id']: b['hits'] for b in e.call('bp_list')['breakpoints']}
    return {nm: h[i] for nm, i in ids.items()}

def measure(script, t0, t1):
    sp = os.path.join(ROOT, 'tests', 'm4_scripts', script)          # (as tools/perfcheck.py script_path)
    if not os.path.exists(sp): sp = os.path.join(ROOT, 'tests', 'm6_scripts', script)
    moves, patches = kidsim.read_script(sp)
    with Emu() as e:
        S = G.setup(e, kidsim.script_level(sp), opts=kidsim.script_opts(sp))
        enc = bytes([((x + 1) & 3) | (((y + 1) & 3) << 2) | (0x10 if sh else 0) for (x, y, sh) in moves]) + b'\xff'
        G.write_pack(e, enc, 5, G.SCRIPT)
        e.call('mem_write', addr=G.SCRIPT_PTR, data_hex='%02x%02x' % (G.SCRIPT & 255, G.SCRIPT >> 8))
        e.call('bp_clear'); e.call('bp_add', addr=S['level_ready']); e.run(400)
        for (rm, p, t, m) in patches:
            e.call('mem_write', addr=G.LEVEL_ADDR + (rm - 1) * 30 + p, data_hex='%02x' % t)
            e.call('mem_write', addr=G.LEVEL_ADDR + 720 + (rm - 1) * 30 + p, data_hex='%02x' % m)
        e.call('bp_clear')
        e.call('bp_add', addr=S['tick_done'])
        ids = {nm: e.call('bp_create_with_init', fields=['type', 'port', 'action'], type=ty, port=port, action='continue')['id']
               for nm, ty, port in PORTS}
        cyc = lambda: e.call('get_raster_pos')['total_cycles']
        marks = {0: (cyc(), hits(e, ids))}             # (as perfcheck: mark t = the end of tick t, 0 = level_ready)
        for t in range(1, t1 + 1):
            r = e.run(1000); assert r['stopped_by'] == 'breakpoint', r
            if t in (t0, t1): marks[t] = (cyc(), hits(e, ids))
    (c0, h0), (c1, h1) = marks[t0], marks[t1]
    n = t1 - t0
    return (c1 - c0) / n / F, {k: (h1[k] - h0[k]) / n for k in h1}

def main():
    sel = sys.argv[1:]
    print('RAM disk %s' % G.rd_size())
    print('%-30s %8s %9s %8s %8s %8s   %s' % ('stretch', 'frames', 'reads', 'writes', 'addr', 'page', '+1 / +2 / +3 T a read (frames a tick)'))
    for name, (sc, t0, t1) in STRETCHES.items():
        if sel and not any(s in name for s in sel): continue
        fr, h = measure(sc, t0, t1)
        print('%-30s %8.3f %9.0f %8.0f %8.0f %8.0f   %s' % (name, fr, h['rd'], h['wr'], h['addr'], h['page'],
              ' / '.join('%.3f' % (k * h['rd'] / F) for k in (1, 2, 3))))

if __name__ == '__main__':
    main()
