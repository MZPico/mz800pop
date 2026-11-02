#!/usr/bin/env python3
"""M5: the game boots from build/pop800.dsk with no harness help. Two emulators run the same game:
  H: tests/m4_game.py setup() (the harness: run_mzf + the RAM-disk writes), the real game's options (guards on);
  F: the floppy: the ROM IPL boots the loader (src/boot/boot.asm), which probes the RAM disk, reads the files
     POP800.D1.. with its own WD2793 code, decompresses them into the RAM disk and main RAM and starts the game.
Before either runs, RAM-disk pages 0-7 are filled with the same pattern, so whole pages can be compared.
Checks, byte for byte:
  1. at `start`: main RAM 0x1200-0x7FFF and 0xC000-block2_end (the game's image; above it to 0xEBFF PRES's art may
     stay, 2026-11-01), RAM-disk pages 0-7 (everything setup() writes, and the rest untouched in both);
  2. at `level_ready` (the game has loaded level 1): the same areas again (the game's runtime areas included: both
     runs must have done the same);
  3. TICKS ticks later (no input, guards on), at `tick_done`: the kid's state (KV), the same RAM areas and VRAM.
     The game does not start in a fixed raster phase, so the two runs may count a different number of frames for the
     level start (FRAMES, at 0x0800, differs by one); pend_flush's copy of FRAMES (pf_f0, only read inside the same
     pend_flush call) is left out of the comparison, and (M7 step 3) its beam scratch pf_e..pf_s (raster lines, also
     only used inside one call): every PSG write waits for the PSG's clock (16 + 4..19 T in mz800emu, by the absolute
     cycle count mod 16), so the two runs, which start the game at different absolute cycles, drift by a line.
M7: the floppy boot goes through the launcher and PRES's title (M7 step 6: a key press at its step a) to the game;
the RAM-disk scratch PRES used (PRES_SCRATCH: its screen in the shadow room's place, its sound bank in the torch cache)
is not compared (the screen only until the game has redrawn it, at level_ready); the RAM-disk areas only
the boot writes (the launcher's copy, the handoff block, the game's compressed image: tools/mkgamedisk.py reserved())
are left out of the RAM-disk comparison (the harness does not write them). tests/m7_launch.py tests the swaps.
M7 step 3: the launched game's sound model is live (SND_MODE 1: snd_playing = the PSG player); the floppy run is set
to silent at level_ready, as every harness run is (live decisions only change which sounds start, i.e. the timing).
Also: the loader's progress bar is full when PRES starts, and with a 256 KB RAM disk (a temporary emulator INI) the
loader refuses (stops at rd_stop) and the game does not start. Prints the boot times in frames (50 per second).
The disk is mounted from a copy (mz800emu writes a mounted image back on eject, even read-only).
usage: m5_boot.py [ticks]"""
import base64, os, shutil, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools')); sys.path.insert(0, os.path.join(ROOT, 'tests'))
import emu
from emu import Emu
from m3_test import syms, RAMDISK
from m4_game import setup
import mkgamedisk
BUILD = os.path.join(ROOT, 'build')
DSK = os.path.join(BUILD, 'pop800.dsk')
G = syms(os.path.join(BUILD, 'm4game.sym')); BS = syms(os.path.join(BUILD, 'boot.sym')); PS = syms(os.path.join(BUILD, 'pres.sym'))
PAGES = 8
PATTERN = bytes((i * 37 + 11) & 255 for i in range(4096))
KV = 0x0A00
MAIN = ((0x1200, 0x8000), (0xC000, G['block2_end']))
REAL_GAME = dict(guards=True, place=[], sword=False)   # guard_opts zero, ev_opts as assembled
TICKS = int(sys.argv[1]) if len(sys.argv) > 1 else 300
SND_MODE_LAUNCHED = None

def fill_ramdisk(e):
    for p in range(PAGES):
        for off in range(0, 65536, 4096):
            e.call('region_write', region_id=RAMDISK[p], offset=off, data_b64=base64.b64encode(PATTERN).decode())

RESERVED = mkgamedisk.reserved()        # [(page, address, length, what)]: written by the boot only
# M7 step 6: the RAM-disk scratch PRES uses for the title (its screen in the shadow room's place, its sound bank in the
# torch cache): the harness never writes them; the game redraws the shadow room at its level start, the torch cache
# only where it caches a torch (TC_VALID)
PRES_SCRATCH = [(1, 0x0000, 32000, 'PRES: the screen'), (6, 0x0000, 0x2880, 'PRES: the sound bank')]
# what of it the game never overwrites: the torch cache, and the shadow room's rows 192-199 (the bottom text line,
# never drawn into the shadow; the shadow is plane-major, 8000 bytes a plane)
PRES_LEFT = [(1, p * 8000 + 192 * 40, 320, 'PRES: the screen, shadow rows 192-199') for p in range(4)] + PRES_SCRATCH[1:]

def ramdisk(e, masks=RESERVED):
    """pages 0-7, the masked areas (page, address, length, ...) as zeros"""
    pages = [bytearray(b''.join(e.region(RAMDISK[p], off, 4096) for off in range(0, 65536, 4096))) for p in range(PAGES)]
    for m in masks:
        pg, a, n = m[:3]
        pages[pg][a:a + n] = bytes(n)
    return [bytes(p) for p in pages]

def copy_disk(tmp):
    d = os.path.join(tmp, 'pop800.dsk'); shutil.copy(DSK, d); return d

def title_start(e, key='SPACE', frames=2):
    """PRES plays the title (M7 step 6) until a key: run to its first step, hold the key until PRES hands over to
    the launcher (p_go); returns the frames it took"""
    n = run_to(e, PS['ts_step'], 3000)
    e.call('input_press_key', key=key)
    n += run_to(e, PS['p_go'], 50)
    e.call('input_release_key', key=key)
    return n

def snapshot(e, masks=RESERVED):
    main = [e.mem(a, b - a) for a, b in MAIN]
    a = G['pf_f0'] - MAIN[0][0]                     # (pend_flush's FRAMES snapshot: absolute time, and its beam
    n = G['pf_s'] + 2 - G['pf_f0']                  # scratch pf_e..pf_s (raster lines inside one call), left out)
    assert n == 12
    main[0] = main[0][:a] + bytes(n) + main[0][a + n:]
    return {'main': main, 'rd': ramdisk(e, masks)}

def run_to(e, addr, limit=3000):
    """run until PC = addr; returns the frames it took"""
    e.call('bp_clear'); e.call('bp_add', addr=addr); n = 0
    while n < limit:
        r = e.run(min(1000, limit - n)); n += r['actual_frames']
        if r['stopped_by'] == 'breakpoint':
            e.call('bp_clear'); return n
    raise AssertionError('PC never reached %04X in %d frames (PC %04X)' % (addr, limit, e.call('get_registers')['PC']))

def diff_ranges(a, b, base):
    """[(start, end)] of differing bytes (runs closer than 16 bytes merged)"""
    out = []
    for i in range(len(a)):
        if a[i] != b[i]:
            if out and i + base - out[-1][1] < 16: out[-1][1] = i + base + 1
            else: out.append([i + base, i + base + 1])
    return out

def compare(what, h, f):
    bad = 0
    for (a, b), x, y in zip(MAIN, h['main'], f['main']):
        d = diff_ranges(x, y, a)
        if d:
            bad += sum(r[1] - r[0] for r in d)
            print('  %s: main RAM %04X-%04X differs at %s' % (what, a, b - 1, ', '.join('%04X-%04X' % (r[0], r[1] - 1) for r in d[:8])))
    for p in range(PAGES):
        d = diff_ranges(h['rd'][p], f['rd'][p], 0)
        if d:
            bad += sum(r[1] - r[0] for r in d)
            print('  %s: RAM-disk page %d differs at %s' % (what, p, ', '.join('%04X-%04X' % (r[0], r[1] - 1) for r in d[:8])))
    print('%s: main RAM %s, RAM-disk pages 0-%d: %s' % (what, ' + '.join('%04X-%04X' % (a, b - 1) for a, b in MAIN), PAGES - 1,
                                                       'identical' if not bad else '%d bytes DIFFER' % bad))
    return bad

def ticks(e, n):
    e.call('bp_clear'); e.call('bp_add', addr=G['tick_done']); frames = 0
    for _ in range(n):
        r = e.run(1000); frames += r['actual_frames']
        assert r['stopped_by'] == 'breakpoint', ('tick_done not reached', r)
    e.call('bp_clear')
    return frames

def harness_run():
    with Emu() as e:
        fill_ramdisk(e)
        setup(e, 1, opts=REAL_GAME)
        assert e.call('get_registers')['PC'] == G['start']
        s0 = snapshot(e, RESERVED + PRES_SCRATCH)
        run_to(e, G['level_ready'])
        s1 = snapshot(e, RESERVED + PRES_SCRATCH)
        fr = ticks(e, TICKS)
        s2 = snapshot(e, RESERVED + PRES_LEFT); s2['kv'] = e.mem(KV, 256); s2['vram'] = e.vram_planes(); s2['frames'] = fr
    return s0, s1, s2

def floppy_run(dsk):
    with Emu() as e:
        fill_ramdisk(e)
        e.call('media_insert', slot='fdc0_fd0', path=dsk, ro=True)
        e.call('reset')
        t_boot = run_to(e, BS['boot'])
        t_launch = t_boot + run_to(e, BS['launch_main'])
        bar = e.mem(BS['bar_cur'], 1)[0]
        e.screenshot(os.path.join(BUILD, 'm5_loader.png'))
        t_pres = t_launch + run_to(e, PS['pres'])
        t_title = t_pres + title_start(e)
        t_start = t_title + run_to(e, G['start'])
        s0 = snapshot(e, RESERVED + PRES_SCRATCH)
        t_ready = t_start + run_to(e, G['level_ready'])
        global SND_MODE_LAUNCHED                        # M7: the launched game plays sound live (psg.asm SND_MODE 1);
        SND_MODE_LAUNCHED = e.mem(G['SND_MODE'], 1)[0]  # the comparison with the harness runs it silent, as the
        e.call('mem_write', addr=G['SND_MODE'], data_hex='00')     # harness (live decisions change the timing only)
        s1 = snapshot(e, RESERVED + PRES_SCRATCH)
        fr = ticks(e, TICKS)
        s2 = snapshot(e, RESERVED + PRES_LEFT); s2['kv'] = e.mem(KV, 256); s2['vram'] = e.vram_planes(); s2['frames'] = fr
        e.screenshot(os.path.join(BUILD, 'm5_game.png'))
    return s0, s1, s2, (t_boot, t_launch, t_pres, t_title, t_start, t_ready), bar

def refuse_run(dsk):
    """boot with a 256 KB RAM disk (a temporary INI and launcher, its own RAM-disk file)"""
    tmp = tempfile.mkdtemp(prefix='m5boot')
    try:
        ini = open(os.path.join(ROOT, 'emu', 'mz800emu.ini')).read()
        lines = []
        for l in ini.splitlines():
            if l.startswith('mr1r18_size'): l = 'mr1r18_size = 256K'
            if l.startswith('mr1r18_filepath'): l = 'mr1r18_filepath = ' + os.path.join(tmp, 'rd256.dat')
            lines.append(l)
        open(os.path.join(tmp, 'mz800emu.ini'), 'w').write('\n'.join(lines) + '\n')
        real = open(emu.EXE).read().split('exec ', 1)[1].split()[0]
        sh = os.path.join(tmp, 'launch.sh')
        open(sh, 'w').write('#!/bin/sh\ncd %s\nexec %s --config %s --no-save-ini "$@"\n' % (tmp, real, os.path.join(tmp, 'mz800emu.ini')))
        os.chmod(sh, 0o755)
        with Emu(exe=sh) as e:
            e.call('media_insert', slot='fdc0_fd0', path=dsk, ro=True)
            e.call('reset')
            e.call('bp_add', addr=G['start']); e.call('bp_add', addr=BS['rd_stop'])
            r = e.run(400); pc = e.call('get_registers')['PC']
            e.call('bp_clear')
            e.run(5)        # (the loader loops at rd_stop) a fresh frame for the screenshot
            stuck = e.call('get_registers')['PC'] == BS['rd_stop']
            e.screenshot(os.path.join(BUILD, 'm5_refuse.png'))
        return r['stopped_by'] == 'breakpoint' and pc == BS['rd_stop'] and stuck, pc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def main():
    print('harness run (tests/m4_game.py setup, guards on) ...')
    h0, h1, h2 = harness_run()
    print('floppy run (a copy of build/pop800.dsk) ...')
    tmp = tempfile.mkdtemp(prefix='m5bootdsk')
    try:
        dsk = copy_disk(tmp)
        f0, f1, f2, (t_boot, t_launch, t_pres, t_title, t_start, t_ready), bar = floppy_run(dsk)
        ok, pc = refuse_run(dsk)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print('boot: loader entered after %d frames, launcher after %d frames (loader %d frames = %.1f s), PRES after %d, '
          'its title\'s step a after %d (a key: the game), game start after %d frames, level_ready after %d frames = %.1f s' % (
          t_boot, t_launch, t_launch - t_boot, (t_launch - t_boot) / 50.0, t_pres, t_title, t_start, t_ready, t_ready / 50.0))
    print('RAM-disk scratch of PRES not compared: %s (the screen at start and level_ready; then only its shadow rows '
          '192-199, which the game never writes)' % ', '.join('%s page %d %04X-%04X' % (w, p, a, a + n - 1) for p, a, n, w in PRES_SCRATCH))
    print('progress bar when the launcher starts: %d of 32 bytes' % bar)
    print('RAM-disk areas not compared (written by the boot only): %s' % ', '.join(
        '%s page %d %04X-%04X' % (w, p, a, a + n - 1) for p, a, n, w in RESERVED))
    bad = (bar != 32)
    print('the launched game\'s sound mode (psg.asm SND_MODE): %d (%s); set to 0 (silent, as the harness) for the comparison' % (
        SND_MODE_LAUNCHED, 'live' if SND_MODE_LAUNCHED == 1 else 'NOT LIVE'))
    bad += SND_MODE_LAUNCHED != 1
    bad += compare('at start', h0, f0)
    bad += compare('at level_ready', h1, f1)
    bad += compare('after %d ticks' % TICKS, h2, f2)
    same_kv = h2['kv'] == f2['kv']; same_vram = h2['vram'] == f2['vram']
    print('after %d ticks: kid state (KV 0x0A00-0x0AFF) %s, VRAM %s (frames: harness %d, floppy %d)' % (
        TICKS, 'identical' if same_kv else 'DIFFERS', 'identical' if same_vram else 'DIFFERS', h2['frames'], f2['frames']))
    bad += (not same_kv) + (not same_vram)
    print('256 KB RAM disk: loader %s (PC %04X; screenshot build/m5_refuse.png)' % ('refuses at rd_stop' if ok else 'DID NOT REFUSE', pc))
    bad += not ok
    print('M5 boot test %s' % ('OK' if not bad else 'FAILED'))
    sys.exit(1 if bad else 0)

if __name__ == '__main__':
    main()
