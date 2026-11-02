#!/usr/bin/env python3
"""M1 kernel test: load the image pack into the emulated RAM disk, run the sprite/room test
program, measure every phase in T-states with breakpoints, and dump screenshots."""
import base64, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from emu import Emu
RAMDISK_BANK0 = 76
DIR_ADDR = 0x7800

def syms(path):
    d = {}
    for line in open(path):
        m = re.match(r'(\S+)\s+EQU\s+([0-9A-Fa-f]+)H', line.strip())
        if m: d[m.group(1)] = int(m.group(2), 16)
    return d

def cycles(e): return e.call('get_raster_pos')['total_cycles']

def main():
    S = syms(os.path.join(ROOT, 'build', 'm1test.sym'))
    pack = open(os.path.join(ROOT, 'build', 'm1.pack'), 'rb').read()
    dirb = open(os.path.join(ROOT, 'build', 'm1.dir'), 'rb').read()
    phases = ['ph_tick', 'ph_fetch_a', 'ph_fetch_b', 'ph_compose_a', 'ph_restore', 'ph_draw', 'ph_fore', 'ph_cdone',
              'ph_compose_b', 'ph_wait', 'ph_blit', 'ph_end']
    with Emu() as e:
        e.run_mzf(os.path.join(ROOT, 'build', 'm1test.mzf'))
        for off in range(0, len(pack), 4096):
            e.call('region_write', region_id=RAMDISK_BANK0, offset=off, data_b64=base64.b64encode(pack[off:off+4096]).decode())
        e.call('mem_write', addr=DIR_ADDR, data_hex=dirb.hex())
        e.call('bp_add', addr=S['ph_tick'])
        r = e.run(1000); assert r['stopped_by'] == 'breakpoint', r
        e.screenshot(os.path.join(ROOT, 'build', 'm1_room.png'))
        e.vram_image(os.path.join(ROOT, 'build', 'm1_room_vram.png'))
        print('room drawn, first tick reached after %d frames' % r['actual_frames'])
        # phase timing over a few ticks
        addr2name = {S[p]: p for p in phases}
        for p in phases: e.call('bp_add', addr=S[p])
        totals = {}; last = ('start', cycles(e)); ticks = 0; tick_cycles = []
        for _ in range(400):
            r = e.run(50)
            if r['stopped_by'] != 'breakpoint': break
            pc = e.call('get_registers')['PC']; name = addr2name.get(pc, hex(pc)); c = cycles(e)
            totals[last[0]] = totals.get(last[0], 0) + (c - last[1])
            if name == 'ph_tick':
                ticks += 1; tick_cycles.append(c)
                if ticks > 8: break
            last = (name, c)
        print('ticks measured:', ticks - 1)
        per = (tick_cycles[-1] - tick_cycles[1]) / (len(tick_cycles) - 2)
        print('T-states per tick (work + idle wait):', int(per))
        order = ['ph_tick', 'ph_fetch_a', 'ph_fetch_b', 'ph_compose_a', 'ph_restore', 'ph_draw', 'ph_fore', 'ph_cdone', 'ph_compose_b', 'ph_wait', 'ph_blit', 'ph_end']
        n = max(1, ticks - 1)
        print('phase durations per tick (T-states, averaged; compose phases counted for both characters):')
        for k in order:
            if k in totals: print('  %-14s %8d' % (k + ' ->', totals[k] // n))
        work = sum(totals.get(k, 0) for k in order if k not in ('ph_end', 'ph_wait')) // n
        print('  work per tick (excluding VBLN wait) ~ %d T = %.2f frames' % (work, work / 70886.0))
        e.call('bp_clear')
        e.run(300)
        e.screenshot(os.path.join(ROOT, 'build', 'm1_anim.png'))
        e.vram_image(os.path.join(ROOT, 'build', 'm1_anim_vram.png'))
        print('frames counter', int.from_bytes(e.mem(0x0800, 2), 'little'), 'ticks', int.from_bytes(e.mem(0x0804, 2), 'little'))
    print('M1 test done')

if __name__ == '__main__': main()
