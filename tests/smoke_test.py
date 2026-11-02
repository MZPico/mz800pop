#!/usr/bin/env python3
"""M0 smoke test: boot the colour-bar program in mz800emu (headless pipe), check that
the 16-colour mode shows the expected bars in VRAM and that the VBLNK-driven frame
counter advances. Run from the project root: python3 tests/smoke_test.py"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from emu import Emu

def main():
    with Emu() as e:
        e.run_mzf(os.path.join(ROOT, 'build', 'colorbars.mzf'))
        r = e.run(100)
        assert r['stopped_by'] == 'frames', r
        ctr = e.mem(0x7FFE, 1)[0]
        assert 90 <= ctr <= 100, 'frame counter did not advance: %d' % ctr
        im = e.vram_image(os.path.join(ROOT, 'build', 'colorbars_vram.png'))
        px = im.load()
        for y in (0, 99, 199):
            bars = [px[x, y] for x in range(0, 256, 16)]
            assert bars == list(range(16)), (y, bars)
            assert [px[x, y] for x in (256, 257)] == [0, 15], (y, 'checker (0xAA: bit 0 = leftmost pixel)')
        g = e.call('get_periph_gdg')
        assert g['regDMD'] == 2 and g['palette'][:4] == [0, 1, 2, 3], g
    print('smoke test OK: 16-colour mode, VRAM planes, VBLNK counter =', ctr)

if __name__ == '__main__':
    main()
