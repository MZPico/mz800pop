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
loader refuses (stops at rd_stop) and the game does not start; the probe finds 512 KB, 1 MB and 16 MB RAM disks
(rd_top 7, 15, 255; docs/ramdisk-tiers.md section 1) and puts back the bytes it wrote, and the launched game gets the
emulator's size at HO_MAIN + HO_RDTOP. The read-speed measurement (src/boot/rdspeed.asm, docs/ramdisk-tiers.md section 1):
with each size every area's MIN / MAX / ALIGN / MISAL / GAME / AVG is 21.0 clocks/byte +-0.1 (mz800emu has no wait
states), the boot goes on, and the launched game gets HO_RDSPD_MAIN = 105 (21.0 x 5); with a stop limit patched in
the image (the defaults: 50.0 and 15.0; rd_max 15.0: "too slow", rd_min 25.0: "timer fault") the boot halts at
rs_stop with the message (build/m5_rdslow.png, build/m5_rdfault.png) and the game does not start. With an emulator
that has mr1r18_wait (POP800_RD_WAIT): +1 T a RAM-disk access reads 22.0 everywhere and the boot goes on, +30 stops
it (above 50.0; build/m5_rdwait1.png, build/m5_rdwait30.png); without it these two are reported as not tested. Prints the boot times in frames (50 per second).
The disk is mounted from a copy (mz800emu writes a mounted image back on eject, even read-only).
usage: m5_boot.py [ticks]"""
import base64, os, re, shutil, sys, tempfile
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
RD_TOP_LAUNCHED = None
RD_SPD_LAUNCHED = None

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
        global RD_TOP_LAUNCHED                          # the probe's size, as the launcher handed it to the game
        RD_TOP_LAUNCHED = e.mem(BS['HO_MAIN'] + BS['HO_RDTOP'], 1)[0]
        global RD_SPD_LAUNCHED                          # the measured read speed, as the launcher handed it over
        RD_SPD_LAUNCHED = e.mem(BS['HO_RDSPD_MAIN'], 1)[0]
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

RD_TOP = {'256K': 3, '512K': 7, '1M': 15, '16M': 255}  # mz800emu's mr1r18_size -> the probe's rd_top (its last page)
def ini_rd_size():
    """the RAM-disk size the default emulator runs with: POP800_RD_SIZE (emu/mz800emu-pop.sh), else the INI's"""
    if os.environ.get('POP800_RD_SIZE'): return os.environ['POP800_RD_SIZE']
    for l in open(os.path.join(ROOT, 'emu', 'mz800emu.ini')):
        if l.startswith('mr1r18_size'): return l.split('=')[1].strip()

def emu_binary():
    """the emulator binary itself: emu.EXE when it is one (MZ800EMU_EXE may name a binary), else (the project's
    wrapper script, emu/mz800emu-pop.sh) MZ800EMU_BIN or the wrapper's default"""
    try: head = open(emu.EXE, 'rb').read(2)
    except OSError: head = b''
    if head != b'#!': return emu.EXE
    if os.environ.get('MZ800EMU_BIN'): return os.environ['MZ800EMU_BIN']
    m = re.search(r'MZ800EMU_BIN:-([^}"]+)', open(emu.EXE).read())
    if not m: raise SystemExit('m5_boot: cannot find the emulator binary in %s' % emu.EXE)
    return m.group(1)

def rd_emu(tmp, size, wait=None):
    """a launcher for an emulator with a RAM disk of `size` (a temporary INI; the RAM disk is in memory, as the INI's)
    and `wait` extra T-states on each of its port accesses (mz800emu's mr1r18_wait; None: the INI's)"""
    ini = open(os.path.join(ROOT, 'emu', 'mz800emu.ini')).read()
    lines = []
    for l in ini.splitlines():
        if l.startswith('mr1r18_wait') and wait is not None: continue
        if l.startswith('mr1r18_size'):
            l = 'mr1r18_size = ' + size
            if wait is not None: lines.append('mr1r18_wait = %d' % wait)
        lines.append(l)
    open(os.path.join(tmp, 'mz800emu.ini'), 'w').write('\n'.join(lines) + '\n')
    real = emu_binary()
    sh = os.path.join(tmp, 'launch.sh')
    open(sh, 'w').write('#!/bin/sh\ncd "%s"\nexec "%s" --config "%s" --no-save-ini "$@"\n' % (tmp, real, os.path.join(tmp, 'mz800emu.ini')))
    os.chmod(sh, 0o755)
    return sh

def refuse_run(dsk):
    """boot with a 256 KB RAM disk (a temporary INI and launcher)"""
    tmp = tempfile.mkdtemp(prefix='m5boot')
    try:
        with Emu(exe=rd_emu(tmp, '256K')) as e:
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

def rd_results(e):
    """rd_speed's results (clocks/byte x 10): {page: (MIN, MAX, ALIGN, MISAL, GAME, AVG)}"""
    n = e.mem(BS['rs_n'], 1)[0]; pages = e.mem(BS['rs_pg'], n); res = e.mem(BS['rs_res'], 12 * n)
    return {p: tuple(res[i * 12 + k] | res[i * 12 + k + 1] << 8 for k in range(0, 12, 2)) for i, p in enumerate(pages)}

def probe_run(dsk, size):
    """boot with a RAM disk of `size` up to the end of the probe (rd_probed): (rd_top, the bytes at offsets 0-1 of every
    page put back, the probe accepted it, rd_speed's results at rd_measured, the boot went on); offsets 0-1 of each page
    the emulator lets the test reach hold a pattern before the boot"""
    tmp = tempfile.mkdtemp(prefix='m5probe')
    try:
        with Emu(exe=rd_emu(tmp, size)) as e:
            pages = RD_TOP[size] + 1                    # (mz800emu lists every page, 256 with 16 MB: MZPico/mz800emu#2)
            listed = sum(r['kind'] == 'ramdisk_std' for r in e.call('regions_list')['regions'])
            assert listed == pages, 'the emulator lists %d RAM-disk pages of %d (an mz800emu before #2?)' % (listed, pages)
            pat = lambda p: bytes([(p * 7 + 3) & 255, (p * 13 + 200) & 255])
            for p in range(pages):
                e.call('region_write', region_id=RAMDISK[0] + p, offset=0, data_b64=base64.b64encode(pat(p)).decode())
            e.call('media_insert', slot='fdc0_fd0', path=dsk, ro=True)
            e.call('reset')
            e.call('bp_add', addr=BS['rd_probed'])
            r = e.run(400); assert r['stopped_by'] == 'breakpoint', r
            zf = bool(e.call('get_registers')['AF'] & 0x40)
            top = e.mem(BS['rd_top'], 1)[0]
            kept = all(e.region(RAMDISK[0] + p, 0, 2) == pat(p) for p in range(pages))
            e.call('bp_clear'); e.call('bp_add', addr=BS['rd_measured']); e.call('bp_add', addr=BS['rs_stop'])
            r = e.run(100); went_on = r['stopped_by'] == 'breakpoint' and e.call('get_registers')['PC'] == BS['rd_measured']
            res = rd_results(e)
        return top, kept, zf, res, went_on
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def has_rd_wait():
    """the emulator binary knows mr1r18_wait (MZPico/mz800emu#2; the project's POP800_RD_WAIT)"""
    try: return b'mr1r18_wait' in open(emu_binary(), 'rb').read()
    except OSError: return False

def wait_run(dsk, wait, png):
    """boot with a 1 MB RAM disk and `wait` T-states on each RAM-disk port access: (rd_speed's results, the boot went on
    (rd_measured) or stopped (rs_stop): 'on' / 'stop' / '?', the GAME mean x 10)"""
    tmp = tempfile.mkdtemp(prefix='m5wait')
    try:
        with Emu(exe=rd_emu(tmp, '1M', wait)) as e:
            e.call('media_insert', slot='fdc0_fd0', path=dsk, ro=True)
            e.call('reset')
            e.call('bp_add', addr=BS['rd_measured']); e.call('bp_add', addr=BS['rs_stop'])
            r = e.run(500); pc = e.call('get_registers')['PC']
            how = '?' if r['stopped_by'] != 'breakpoint' else 'on' if pc == BS['rd_measured'] else 'stop'
            res = rd_results(e); g = e.mem(BS['rs_gav'], 2); gav = g[0] | g[1] << 8
            e.call('bp_clear'); e.run(3)
            e.screenshot(os.path.join(BUILD, png))
        return res, how, gav
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def stop_run(dsk, what, value, png):
    """boot with rd_max or rd_min patched in the loaded image to value: (it halted at rs_stop and stays there, the game
    never started, rs_mode)"""
    with Emu() as e:
        e.call('media_insert', slot='fdc0_fd0', path=dsk, ro=True)
        e.call('reset')
        run_to(e, BS['boot'])
        e.call('mem_write', addr=BS[what], data_hex='%02x%02x' % (value & 255, value >> 8))
        e.call('bp_add', addr=G['start']); e.call('bp_add', addr=BS['rs_stop']); e.call('bp_add', addr=BS['launch_main'])
        r = e.run(400); pc = e.call('get_registers')['PC']
        e.call('bp_clear'); e.call('bp_add', addr=BS['launch_main']); e.call('bp_add', addr=G['start'])
        r2 = e.run(100)                                 # (it must stay in the loop: no launcher, no game)
        stuck = r2['stopped_by'] != 'breakpoint' and e.call('get_registers')['PC'] == BS['rs_stop']
        mode = e.mem(BS['rs_mode'], 1)[0]
        e.screenshot(os.path.join(BUILD, png))
    return r['stopped_by'] == 'breakpoint' and pc == BS['rs_stop'] and stuck, mode

def main():
    print('harness run (tests/m4_game.py setup, guards on) ...')
    h0, h1, h2 = harness_run()
    print('floppy run (a copy of build/pop800.dsk) ...')
    tmp = tempfile.mkdtemp(prefix='m5bootdsk')
    try:
        dsk = copy_disk(tmp)
        f0, f1, f2, (t_boot, t_launch, t_pres, t_title, t_start, t_ready), bar = floppy_run(dsk)
        ok, pc = refuse_run(dsk)
        probes = {size: probe_run(dsk, size) for size in ('512K', '1M', '16M')}
        slow = stop_run(dsk, 'rd_max', 150, 'm5_rdslow.png')
        fault = stop_run(dsk, 'rd_min', 250, 'm5_rdfault.png')
        waits = {w: wait_run(dsk, w, 'm5_rdwait%d.png' % w) for w in (1, 30)} if has_rd_wait() else None
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
    for size, (top, kept, zf, res, went_on) in probes.items():      # (docs/ramdisk-tiers.md section 1)
        good = top == RD_TOP[size] and kept and zf
        print('%s RAM disk: the probe found pages 0-%d, %s, the bytes it wrote put back: %s%s' % (
            size, top, 'accepted' if zf else 'REFUSED', 'yes' if kept else 'NO', '' if good else '  FAILED'))
        bad += not good
        want_pages = sorted({0, 7, RD_TOP[size] // 2 + 1, RD_TOP[size]})
        fast = sorted(res) == want_pages and all(209 <= v <= 211 for vs in res.values() for v in vs) and went_on
        print('%s RAM disk: read speed (clocks/byte, MIN MAX ALIGN MISAL GAME AVG) %s; boot %s%s' % (size, ', '.join(
            'P%d %s' % (p, ' '.join('%.1f' % (v / 10) for v in vs)) for p, vs in sorted(res.items())),
            'goes on' if went_on else 'STOPPED', '' if fast else '  FAILED (want 21.0 +-0.1 at pages %s)' % want_pages))
        bad += not fast
    for name, (ok, mode), want, png in (('too slow (rd_max 15.0)', slow, 1, 'm5_rdslow.png'),
                                       ('timer fault (rd_min 25.0)', fault, 0, 'm5_rdfault.png')):
        good = ok and mode == want
        print('read-speed stop, %s: %s (rs_mode %d; screenshot build/%s)' % (
            name, 'halts at rs_stop, no launch' if good else 'FAILED', mode, png))
        bad += not good
    if waits is None:
        print('RAM-disk wait states: not tested (the emulator has no mr1r18_wait)')
    else:       # +1 on each access: 22.0 (the address OUT adds 1/128 or 1/32); +30: above 50.0, the stop (mz800emu's
                # mr1r18_wait is linear to 9 only: 10 gives 37.1 clocks a byte, 30 gives 69.4; its own cycle counter agrees)
        for w, want_how, lo, hi in ((1, 'on', 219, 221), (30, 'stop', 501, 9999)):
            res, how, gav = waits[w]
            good = how == want_how and lo <= gav <= hi and all(lo <= vs[4] <= hi for vs in res.values())
            print('RAM disk +%d T a port access: GAME %.1f clocks/byte (%s), boot %s%s (screenshot build/m5_rdwait%d.png)' % (
                w, gav / 10, ', '.join('P%d %s' % (p, ' '.join('%.1f' % (v / 10) for v in vs)) for p, vs in sorted(res.items())),
                {'on': 'goes on', 'stop': 'stops at rs_stop', '?': 'NEITHER'}[how],
                '' if good else '  FAILED (want %s, GAME %.1f-%.1f)' % (want_how, lo / 10, hi / 10), w))
            bad += not good
    print('the launched game\'s HO_RDSPD_MAIN: %d (%s)' % (RD_SPD_LAUNCHED, 'right' if RD_SPD_LAUNCHED == 105 else 'WRONG, want 105'))
    bad += RD_SPD_LAUNCHED != 105
    want = RD_TOP.get(ini_rd_size())
    print('the launched game\'s HO_MAIN + HO_RDTOP: %d (the emulator\'s %s RAM disk: %s)' % (
        RD_TOP_LAUNCHED, ini_rd_size(), 'right' if RD_TOP_LAUNCHED == want else 'WRONG, want %s' % want))
    bad += RD_TOP_LAUNCHED != want
    print('M5 boot test %s' % ('OK' if not bad else 'FAILED'))
    sys.exit(1 if bad else 0)

if __name__ == '__main__':
    main()
