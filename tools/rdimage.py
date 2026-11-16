#!/usr/bin/env python3
"""The MZPico's RAM-disk image (docs/ramdisk-tiers.md section 16): the 512 KB RAM disk as the game's floppy boot leaves
it, for the card's mode that serves the RAM disk from an image in its flash with a copy-on-write pool in SRAM.

Boots the game disk in mz800emu with a 512 KB RAM disk (the RAM disk starts as the emulator's, 0xFF), runs to the
boot's end, PRES's first instruction (PRES_START) with the launcher's handoff ACT_TITLE (as tests/m5_boot.py to_pres;
512 KB has no frame-store fill), and writes the 8 pages, page 0 first, as one raw file (524,288 bytes), and a sidecar
in sha256sum's format: the image's hash and the game disk's it came from (`sha256sum -c --ignore-missing` checks
both). The image belongs to that disk alone: another build writes other bytes at boot and the pool fills up.

The boot measures the RAM disk's read speed and keeps it in the launcher's image in page 0 (rd_spd, 0xF936: the GAME
mean x 5): 105 with no wait states, 110 with 1. The MZPico asserts at least 1 wait state on every RAM-disk port access,
so the image is made with POP800_RD_WAIT=1 (--wait) by default: on a card that reads faster or slower that one byte
differs, one block of the pool.

usage: rdimage.py [--disk DSK] [--out IMG] [--wait N] [--check]
  --check   also boot with other timings (no wait states, 3 wait states, a later reset) and without the MZPico's NET
            card, and print the bytes that differ from the image; fails if anything differs but rd_spd
"""
import argparse, hashlib, os, shlex, shutil, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools')); sys.path.insert(0, os.path.join(ROOT, 'tests'))
import version
from emu import Emu
from m3_test import syms
import rdlog

BUILD = os.path.join(ROOT, 'build')
SIZE, PAGES = '512K', 8
RD_TOP = PAGES - 1
WAIT = 1                                    # the MZPico: at least 1 wait state on every RAM-disk port access
LAUNCHER = (0, 0xF000)                      # the launcher's copy in the RAM disk (docs/memory.md "RAM disk")


def image_name(v=None):
    return 'pop800-rd512-%s.img' % (v or version.version())


def launcher(tmp, env):
    """a launch script for the project's emulator wrapper with `env`, run in its own directory `tmp`"""
    sh = os.path.join(tmp, 'launch.sh')
    sets = ''.join('export %s=%s\n' % (k, shlex.quote(v)) for k, v in sorted(env.items()))
    open(sh, 'w').write('#!/bin/sh\ncd %s\n%sexec %s "$@"\n' % (shlex.quote(tmp), sets,
                                                              shlex.quote(os.path.join(ROOT, 'emu', 'mz800emu-pop.sh'))))
    os.chmod(sh, 0o755)
    return sh


def run_to(e, addr, limit=3000):
    e.call('bp_clear'); e.call('bp_add', addr=addr); n = 0
    while n < limit:
        r = e.run(min(1000, limit - n)); n += r['actual_frames']
        if r['stopped_by'] == 'breakpoint':
            e.call('bp_clear'); return n
    raise SystemExit('rdimage: PC never reached %04X in %d frames (PC %04X)' % (addr, limit, e.call('get_registers')['PC']))


def boot_to_pres(e, dsk, BS, PS, pre=0, fill=False):
    """reset (after `pre` frames) with the disk in drive 0 and run to PRES's start (`fill`: past the frame store's fill
    of 1 MB and more); returns the frames of the boot"""
    e.call('media_insert', slot='fdc0_fd0', path=dsk, ro=True)
    if pre: e.run(pre)
    e.call('reset')
    n = run_to(e, BS['launch_main'], 5000)
    n += run_to(e, PS['pres'], 5000)
    ho = e.mem(BS['HO_MAIN'], 16)
    if ho[BS['HO_ACTION']] == BS['ACT_FILL'] and fill:
        n += run_to(e, PS['pres'], 5000); ho = e.mem(BS['HO_MAIN'], 16)
    if ho[BS['HO_ACTION']] == BS['ACT_FILL']:
        raise SystemExit('rdimage: the boot started the frame store\'s fill: not a 512 KB RAM disk')
    if ho[BS['HO_ACTION']] != BS['ACT_TITLE'] or e.call('get_registers')['PC'] != PS['PRES_START']:
        raise SystemExit('rdimage: not at PRES_START with ACT_TITLE (handoff %s)' % ho.hex())
    return n


def make(dsk, wait=WAIT, unicard=None, pre=0, size=SIZE):
    """boot the disk; -> (the RAM disk's first PAGES pages, the boot's frames, the probe's rd_top, the sha256 of the
    disk copy that booted)"""
    BS = syms(os.path.join(BUILD, 'boot.sym')); PS = syms(os.path.join(BUILD, 'pres.sym'))
    os.makedirs(BUILD, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='rdimage', dir=BUILD)
    try:
        d = os.path.join(tmp, 'pop800.dsk'); shutil.copy(dsk, d)      # (mz800emu writes a mounted disk back on eject)
        dsk_sha = sha256(d)
        env = {'POP800_RD_SIZE': size, 'POP800_RD_WAIT': str(wait)}
        if unicard is not None: env['POP800_UNICARD'] = str(unicard)
        with Emu(exe=launcher(tmp, env)) as e:
            n = boot_to_pres(e, d, BS, PS, pre, fill=size != SIZE)
            top = e.mem(BS['HO_MAIN'] + BS['HO_RDTOP'], 1)[0]
            img = rdlog.read_image(e, PAGES)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return img, n, top, dsk_sha


def diff(a, b):
    """[(page, address, a's byte, b's byte)]"""
    return [(i >> 16, i & 0xFFFF, a[i], b[i]) for i in range(len(a)) if a[i] != b[i]]


def sha256(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def write_sidecar(img_path, dsk_sha, v=None):
    """the sidecar: the image's sha256 and the sha256 of the disk that booted (hashed before the boot)"""
    side = img_path + '.sha256'; tmp = side + '.tmp'
    open(tmp, 'w').write('%s  %s\n%s  pop800-%s.dsk\n' % (sha256(img_path), os.path.basename(img_path),
                                                         dsk_sha, v or version.version()))
    os.replace(tmp, side)
    return side


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--disk', default=os.path.join(BUILD, 'pop800.dsk'))
    ap.add_argument('--out', default=None)
    ap.add_argument('--wait', type=int, default=WAIT)
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    out = a.out or os.path.join(BUILD, image_name())
    BS = syms(os.path.join(BUILD, 'boot.sym'))
    img, n, top, dsk_sha = make(a.disk, a.wait)
    if top != RD_TOP: raise SystemExit('rdimage: the probe found rd_top %d, not %d (512 KB)' % (top, RD_TOP))
    spd = LAUNCHER[1] + BS['rd_spd'] - BS['boot']
    print('rdimage: boot to PRES_START in %d frames, rd_top %d, rd_spd %d (wait %d)' % (n, top, img[spd], a.wait))
    tmp = out + '.tmp'; open(tmp, 'wb').write(img); os.replace(tmp, out)
    side = write_sidecar(out, dsk_sha)
    print('rdimage: %s (%d bytes), sha256 %s; %s' % (os.path.relpath(out, ROOT), len(img), sha256(out), os.path.relpath(side, ROOT)))
    if not a.check: return
    bad = 0
    for what, kw in (('again', {}), ('a reset 37 frames later', dict(pre=37)), ('0 wait states', dict(wait=0)),
                     ('3 wait states', dict(wait=3)), ('no NET card', dict(unicard=0))):
        kw.setdefault('wait', a.wait)
        b, n2, _, _ = make(a.disk, **kw)
        d = diff(img, b)
        other = [x for x in d if x[0] != 0 or x[1] != spd]
        bad += bool(other)
        print('  %-24s boot %d frames: %d bytes differ%s' % (what, n2, len(d), ''.join(
            ' %d:%04X %02X/%02X%s' % (p, ad, x, y, ' (rd_spd)' if (p, ad) == (0, spd) else '') for p, ad, x, y in d[:12])))
    b, n2, top, _ = make(a.disk, a.wait, size='1M')       # (information: what a 1 MB card's boot leaves in pages 0-7)
    d = diff(img, b)
    print('  %-24s boot %d frames (the fill included), rd_top %d: %d bytes of pages 0-7 differ, in %d blocks of 1 KB:%s'
          % ('a 1 MB RAM disk', n2, top, len(d), len({(p, ad >> 10) for p, ad, _, _ in d}),
             ''.join(' %d:%04X %02X/%02X' % x for x in d[:8])))
    if bad: raise SystemExit('rdimage: the image depends on more than the read speed')
    print('rdimage: the same bytes in every run but rd_spd')


if __name__ == '__main__':
    main()
