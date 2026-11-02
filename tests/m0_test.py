#!/usr/bin/env python3
"""M0 acceptance test: boot build/m0.dsk (the M0 disk; build/pop800.dsk is the game disk since M5) in the headless emulator through the ROM IPL,
then check the VBLN interrupt, the raster position of the interrupt, keyboard + joystick
input, the RAM-disk probe and the RAM-disk read speed."""
import os, re, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from emu import Emu

FRAMES, KEYMAT, JOY, INPUT, RDFLAGS, RDSTDSZ, RDPICOSZ, ISRMARK = 0x7000, 0x7010, 0x701A, 0x701B, 0x7020, 0x7021, 0x7022, 0x7024

def syms():
    d = {}
    for line in open(os.path.join(ROOT, 'build', 'm0boot.sym')):
        m = re.match(r'(\S+)\s+EQU\s+([0-9A-Fa-f]+)H', line.strip())
        if m: d[m.group(1)] = int(m.group(2), 16)
    return d

def main():
    S = syms()
    with Emu() as e:
        e.call('media_insert', slot='fdc0_fd0', path=os.path.join(ROOT, 'build', 'm0.dsk'), ro=True)
        e.call('reset')
        # run until the boot program starts (the IPL reads the bootstrap first)
        e.call('bp_add', addr=S['start'])
        r = e.run(1000)
        assert r['stopped_by'] == 'breakpoint', ('IPL did not start the bootstrap', r)
        print('booted from floppy: PC at start after %d frames' % r['actual_frames'])
        e.call('bp_clear')
        e.run(20)
        f0 = int.from_bytes(e.mem(FRAMES, 2), 'little'); e.run(50)
        f1 = int.from_bytes(e.mem(FRAMES, 2), 'little')
        print('VBLN ISR frames in 50 video frames:', f1 - f0, ' GDG status at ISR: 0x%02x' % e.mem(ISRMARK, 1)[0])
        assert 48 <= f1 - f0 <= 52, 'ISR rate wrong'
        # raster position when the ISR fires
        e.call('bp_add', addr=S['isr']); e.run(5); rp = e.call('get_raster_pos'); e.call('bp_clear')
        print('ISR fires at scanline %d column %d (canvas = 200 lines after the top border)' % (rp['scanline'], rp['column_pixel']))
        # inputs: joystick then keys
        # input_send_joystick holds the state while the emulator runs `frames` frames, then releases;
        # read the program's copy right after it returns (no further frames)
        e.call('input_send_joystick', port=0, state=0x04, frames=10)   # LEFT
        inp = e.mem(INPUT, 1)[0]; joy = e.mem(JOY, 1)[0]
        print('joystick LEFT -> JOY=0x%02x INPUT=0x%02x' % (joy, inp)); assert inp & 1, 'joystick left not seen'
        e.run(3); assert e.mem(INPUT, 1)[0] == 0, 'joystick not released'
        for key, bit in (('LEFT', 0), ('RIGHT', 1), ('UP', 2), ('DOWN', 3), ('SPACE', 4)):
            e.call('input_press_key', key=key); e.run(3); inp = e.mem(INPUT, 1)[0]
            e.call('input_release_key', key=key); e.run(3); inp2 = e.mem(INPUT, 1)[0]
            print('  %-12s INPUT=0x%02x released=0x%02x' % (key, inp, inp2))
            assert inp & (1 << bit) and not inp2 & (1 << bit), key
        # RAM disk probe
        fl, sz, psz = e.mem(RDFLAGS, 1)[0], e.mem(RDSTDSZ, 1)[0], e.mem(RDPICOSZ, 1)[0]
        print('RAM disk: flags=0x%02x (bit0 STD, bit1 pico_rd), STD size=%d x 64 KB, pico_rd size=%d' % (fl, sz, psz))
        assert fl & 1, 'STD RAM disk not detected'
        e.screenshot(os.path.join(ROOT, 'build', 'm0boot.png'))
        # speed test: rerun the probe's INIR block between two breakpoints and count cycles
        e.call('set_register', reg='PC', value=S['spd_start']); e.call('set_register', reg='HL', value=0xA000)
        e.call('set_register', reg='BC', value=0x00EA)
        e.call('bp_add', addr=S['spd_end']); t0 = e.call('get_raster_pos')['total_cycles']; e.run(100)
        t1 = e.call('get_raster_pos')['total_cycles']; e.call('bp_clear')
        print('INIR 4096 bytes from the STD RAM disk: %d T-states = %.1f T/byte' % (t1 - t0, (t1 - t0) / 4096.0))
    print('M0 test OK')

if __name__ == '__main__':
    main()
