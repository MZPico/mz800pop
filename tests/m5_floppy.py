#!/usr/bin/env python3
"""M5/M8: the launcher's floppy code against a real drive's spin-up (docs/research/mz800-hardware.md "Real drive
findings"). mz800emu's drive is ready and readable the moment a command arrives; a PC 3.5" drive reports READY at once
(or has none) while its disk still speeds up, so reads fail for a while after the motor starts. The test models that
drive: breakpoints follow the motor (the launcher's fd_init turns it on, motor_off stops it; the ROM's IPL load leaves
it running for the boot) and, at frr_rd (a read's result in fd_read_retry), a read that ends less than UNREADY seconds
after the motor started is made to fail (Z cleared). Every floppy load of the launcher goes through these: the boot's
data files, PRES and its scenes (LN_PRS_LOAD), the duel's pieces.
  1. timing: the spin-up wait (fd_init to fi_0) is ~0.97 s whenever the motor was stopped and 0 when it runs;
  2. a drive that reads nothing for 0.8 s after the motor starts (a typical PC drive is up to speed in 0.3-0.5 s):
     boot -> the title -> the game, no read fails (the wait covers it);
  3. a slow drive, 2.0 s: the same path, the retries (6, ~0.3 s apart) take it;
  4. a bad disk: every read of PRES's first load fails: DISK ERROR (fd_fail) within a few seconds of emulated time.
Prints the boot's and the title's times (emulated seconds) and the spin-up waits seen. The disk is mounted from a copy.
usage: m5_floppy.py [--build DIR]   (DIR: another build's directory, e.g. one without the spin-up wait: the
                                     scenarios then show what that code does; its boot.sym needs frr_rd or fd_read_retry)"""
import os, shutil, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools')); sys.path.insert(0, os.path.join(ROOT, 'tests'))
from emu import Emu
from m3_test import syms
ARGV, sys.argv[1:] = sys.argv[1:], []       # (m5_boot reads its own arguments when imported)
import m5_boot as M5
CPU = 3546875                   # the MZ-800's CPU clock (PAL)
FAILS = []


def check(what, ok, detail=''):
    print('  %-74s %s%s' % (what, 'ok' if ok else 'FAILED', '' if ok else '  ' + str(detail)))
    if not ok: FAILS.append(what)


def cyc(e): return e.call('get_raster_pos')['total_cycles']


class Drive:
    """the drive model: the motor's state and start, the reads failed, the spin-up waits seen"""
    def __init__(self, e, bs, unready, fail_all_from=None):
        self.e, self.bs, self.unready, self.fail_all_from = e, bs, unready, fail_all_from
        self.running, self.t_on = True, 0       # (the ROM's IPL load left the motor running: it reads with it on)
        self.failed = 0; self.reads = 0; self.waits = []; self.t_init = None; self.fail_all = False
        rd = bs.get('frr_rd')
        if rd is None:                          # (an older build: after fd_read_retry's ld b,4; push x 4; call fd_read)
            rd = bs['fd_read_retry'] + 2 + 4 + 3
        self.inits = 0
        self.rd = rd
        self.bps = [bs['fd_init'], bs['fi_0'] if 'fi_0' in bs else None, bs.get('motor_off'), rd, bs['fd_fail']]
        self.bps = [a for a in self.bps if a is not None]

    def run_to(self, stops, limit_s=60):
        """run until PC is in stops, handling the drive's breakpoints; returns the PC"""
        e = self.e; t0 = cyc(e)
        while True:
            e.call('bp_clear')
            for a in set(self.bps) | set(stops): e.call('bp_add', addr=a)
            r = e.run(500)
            assert (cyc(e) - t0) / CPU < limit_s, 'PC %04X: no stop within %d s' % (e.call('get_registers')['PC'], limit_s)
            if r['stopped_by'] != 'breakpoint': continue
            pc = e.call('get_registers')['PC']; now = cyc(e)
            if pc in stops:
                e.call('bp_clear'); return pc
            if pc == self.bs['fd_init']:
                if 'motor_off' not in self.bs and self.inits:   # (an older build stopped it after every PRES load)
                    self.running = False
                self.inits += 1
                self.t_init = (now, self.running)
                if not self.running: self.running, self.t_on = True, now
            elif pc == self.bs.get('fi_0'):
                if self.t_init is not None:
                    self.waits.append(((now - self.t_init[0]) / CPU, self.t_init[1])); self.t_init = None
            elif pc == self.bs.get('motor_off'):
                self.running = False
            elif pc == self.rd:
                self.reads += 1
                reg = e.call('get_registers')
                if not reg['AF'] & 0x40:        # (a read that failed by itself)
                    self.failed += 1
                elif self.fail_all or not self.running or (now - self.t_on) / CPU < self.unready:
                    e.call('set_register', reg='AF', value=reg['AF'] & ~0x40)   # the drive could not have read it yet
                    self.failed += 1
            e.call('bp_clear'); e.call('step_into')     # (over the breakpoint)


def boot(e, dsk):
    M5.fill_ramdisk(e)
    e.call('media_insert', slot='fdc0_fd0', path=dsk, ro=True)
    e.call('reset')


def scenario(build, dsk, unready, label):
    bs = syms(os.path.join(build, 'boot.sym')); ps = syms(os.path.join(build, 'pres.sym'))
    g = syms(os.path.join(build, 'm4game.sym'))
    with Emu() as e:
        boot(e, dsk)
        d = Drive(e, bs, unready)
        t0 = cyc(e)
        pc = d.run_to([ps['ts_step'], bs['fd_fail']], 120)
        t_title = (cyc(e) - t0) / CPU
        ok = pc == ps['ts_step']
        if ok:
            e.call('input_press_key', key='SPACE')
            pc = d.run_to([ps['p_go'], bs['fd_fail']], 30)
            e.call('input_release_key', key='SPACE')
            pc = d.run_to([g['start'], bs['fd_fail']], 30) if pc == ps['p_go'] else pc
            ok = pc == g['start']
        e.screenshot(os.path.join(M5.BUILD, 'm5_floppy_%s.png' % label))
    return ok, t_title, d


def bad_disk(build, dsk):
    """every read fails from PRES's first load on: DISK ERROR, and how long it took"""
    bs = syms(os.path.join(build, 'boot.sym'))
    with Emu() as e:
        boot(e, dsk)
        d = Drive(e, bs, 0)
        d.run_to([bs['launch_main']], 120)
        d.run_to([bs['prs_load_main']], 30)
        d.fail_all = True; t0 = cyc(e); r0 = d.reads
        pc = d.run_to([bs['fd_fail'], bs['fatal_stop']], 120)
        t = (cyc(e) - t0) / CPU; d.reads -= r0
        e.screenshot(os.path.join(M5.BUILD, 'm5_floppy_bad.png'))
    return pc == bs['fd_fail'], t, d


def main(argv):
    build = M5.BUILD
    if argv[:1] == ['--build']: build = os.path.abspath(argv[1])
    with tempfile.TemporaryDirectory() as tmp:
        dsk = os.path.join(tmp, 'pop800.dsk')
        print('m5_floppy: %s' % os.path.relpath(build, ROOT))
        res = {}
        for unready, label in ((0, 'emulator'), (0.8, 'pc'), (2.0, 'slow')):
            shutil.copy(os.path.join(build, 'pop800.dsk'), dsk)
            res[label] = scenario(build, dsk, unready, label)
            ok, t, d = res[label]
            print('  %-8s unready %.1f s: %s, boot -> title %.2f s, %d reads, %d failed, spin-up waits %s' % (
                label, unready, 'title and game' if ok else 'DISK ERROR', t, d.reads, d.failed,
                ', '.join('%.2f%s' % (w, '' if run else '*') for w, run in d.waits) or '-'))
        print('  (* = the motor was stopped before that load)')
        ok, t, d = res['emulator']
        waits = d.waits
        check('every load with the motor stopped waits ~0.97 s (%d of %d loads)' % (
              sum(not r for w, r in waits), len(waits)), any(not r for w, r in waits) and
              all(0.95 <= w <= 1.0 for w, r in waits if not r), waits)
        check('every load with the motor running (the boot, PRS_KEEP chains) does not wait',
              any(r for w, r in waits) and all(w < 0.01 for w, r in waits if r), waits)
        check('no read fails without a spin-up model', res['emulator'][0] and d.failed == 0, d.failed)
        ok, t, d = res['pc']
        check('a drive unreadable for 0.8 s after motor on: title and game, no failed read', ok and d.failed == 0,
              (ok, d.failed))
        ok, t, d = res['slow']
        check('a slow drive (2.0 s): the retries take it, title and game', ok and d.failed > 0, (ok, d.failed))
        print('  spin-up cost: boot -> title %.2f s with the waits (0.8 s model %.2f s, 2.0 s model %.2f s)' % (
            res['emulator'][1], res['pc'][1], res['slow'][1]))
        shutil.copy(os.path.join(build, 'pop800.dsk'), dsk)
        ok, t, d = bad_disk(build, dsk)
        check('a bad disk: DISK ERROR within 15 s (%.1f s, %d reads)' % (t, d.reads), ok and t < 15, (ok, t))
    print('m5_floppy: %s' % ('PASS' if not FAILS else 'FAIL (%s)' % '; '.join(FAILS)))
    sys.exit(1 if FAILS else 0)


if __name__ == '__main__':
    main(ARGV)
