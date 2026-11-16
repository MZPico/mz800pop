#!/usr/bin/env python3
"""The MZPico's RAM-disk image (tools/rdimage.py, docs/ramdisk-tiers.md section 16) against the card's copy-on-write
pool: the game played from the image, every RAM-disk write the game makes replayed into a model of the pool.

Needs an mz800emu with the RAM-disk access log (tools/rdlog.py; `tools/ci/build_deps.sh emu_rdlog` builds one from the
pinned commit): POP800_RDLOG_EMU names its binary (default ~/mz800emu-rdlog/mz800emu). The stock emulator writes no log,
so this test is local only: the runners do not build the patched emulator (`make rdimage-check`).

Each scenario runs in its own emulator with a 512 KB RAM disk and the image's wait states (1): the image is written into
the RAM disk (the card starts with it), the floppy boots, the scenario plays, and the log has every RAM-disk port write
from the reset on. The model (tools/rdlog.py Cow): 1 KB blocks, write-compare (a write of the image's byte allocates
nothing), no block freed; besides, the same with a card that frees a block matching the image again. Scenarios:
  title   the boot, PRES's title and story (4,000 frames: the title's steps, the story, the title again), then a game
          start from it (SPACE) to the first play ticks
  walk    the boot, a game start at the title's first step, level 1 by tests/m4_scripts/walk_level1.txt (guards off, as
          recorded: room changes, the level door), the cutscene, level 2 by tests/m6_scripts/level2_fight.txt with one
          hit point left (a fight: the guard kills the kid), 60 ticks, then levels 3-14 by load_level (the cutscenes'
          swaps among them), 40 ticks each
  traps   the boot, a game start, then by load_level with the scripts' start rooms: level 10 room 10 by
          tests/m4_scripts/frm_button.txt (a chopper and a closer button: the picture slots, the complete pictures, the
          button pictures) and level 7 room 19 by frm_spike_btn.txt (a spike, gates)
  duel    the boot, Ctrl+D with no Unicard (the local duel), tests/duel_scripts/match.txt to its end, back to the title,
          a new game, 20 ticks
Checks: the disk is the image's (its sidecar's sha256); the log is complete (the image + the harness's own pokes + the
logged writes = the RAM disk at the end, byte for byte); the boot allocates at most BOOT_MAX blocks; every scenario's
pool stays within BUDGET blocks. Prints the blocks after each phase and the regions allocated; build/rdimage_check/
holds each scenario's log, marks and output, and results.json.
usage: rdimage_check.py [--image IMG] [scenario ...]   (rdimage_check.py --run NAME DIR: one scenario, internal)"""
import base64, json, os, shutil, subprocess, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools')); sys.path.insert(0, os.path.join(ROOT, 'tests'))
import rdlog, rdimage
from m3_test import syms

BUILD = os.path.join(ROOT, 'build')
OUT = os.path.join(BUILD, 'rdimage_check')
BLOCK = 1024
# the card's pool in 1 KB blocks (POP800_RD_POOL): v0.1.0 needs 63 (traps), 6 of them only for the boot probe's markers,
# which it puts back (57 on a card that frees a block matching the image again): ~60 KB is not enough without that rule
BUDGET = int(os.environ.get('POP800_RD_POOL', '64'))
JOBS = int(os.environ.get('POP800_RDCHECK_JOBS', '3'))
BOOT_MAX = 10               # the boot: the probe's markers (one block a page) and rd_spd at most
SCENARIOS = ('title', 'walk', 'traps', 'duel')
EMU_RDLOG = os.environ.get('POP800_RDLOG_EMU', os.path.expanduser('~/mz800emu-rdlog/mz800emu'))
FAILS = []


def check(what, ok, detail=''):
    print('  %s %s%s' % ('OK  ' if ok else 'FAIL', what, '' if ok else ': %s' % (detail,)), flush=True)
    if not ok: FAILS.append(what)


# ---- one scenario (in its own process and directory)
class Run:
    def __init__(self, e, BS, PS, G):
        self.e, self.BS, self.PS, self.G = e, BS, PS, G
        self.hi = 0; self.last = 0; self.marks = []; self.pokes = []; self.regions = rdlog.rd_regions(e)
    def now(self):
        """the CPU cycle as the log counts it (a 32-bit counter, its wraps and the reset's restart counted alike)"""
        c = self.e.call('get_raster_pos')['total_cycles']
        if c < self.last: self.hi += 1 << 32
        self.last = c; return self.hi | c
    def mark(self, label):
        self.marks.append((self.now(), label)); print('    %s' % label, flush=True)
    def poke(self, page, addr, data):
        """a harness write into the RAM disk (not a port access: not in the log, and nothing the card would see)"""
        self.pokes.append((self.now(), page, addr, data.hex()))
        for off in range(0, len(data), 4096):
            self.e.call('region_write', region_id=self.regions[page], offset=addr + off,
                        data_b64=base64.b64encode(data[off:off + 4096]).decode())
    def run_to(self, addrs, limit=8000):
        e = self.e; addrs = [addrs] if isinstance(addrs, int) else list(addrs)
        e.call('bp_clear')
        for a in addrs: e.call('bp_add', addr=a)
        n = 0
        while True:
            r = e.run(min(1000, limit - n)); n += r['actual_frames']
            if r['stopped_by'] == 'breakpoint': break
            if n >= limit:
                raise AssertionError('PC %04X never reached %s' % (e.call('get_registers')['PC'], ['%04X' % a for a in addrs]))
        e.call('bp_clear')
        return e.call('get_registers')['PC']
    def ticks(self, n, stop=()):
        for _ in range(n):
            pc = self.run_to([self.G['tick_done']] + list(stop), 2000)
            if pc != self.G['tick_done']: return pc
        return None
    def title_start(self, key='SPACE'):
        e = self.e
        self.run_to(self.PS['ts_step'], 3000)
        e.call('input_press_key', key=key); self.run_to(self.PS['p_go'], 50); e.call('input_release_key', key=key)
    def script(self, path, pad, patches_ok=False):
        import kidsim, m4_game as MG
        from m4_test import encode
        moves, patches = kidsim.read_script(path); keys = kidsim.read_keys(path)
        assert patches_ok or not patches, path
        self.poke(5, MG.SCRIPT, encode(moves + [(0, 0, 0)] * pad, keys + [0] * pad))
        self.e.call('mem_write', addr=MG.SCRIPT_PTR, data_hex='%02x%02x' % (MG.SCRIPT & 255, MG.SCRIPT >> 8))
        return len(moves)
    def script_off(self):
        import m4_game as MG
        self.e.call('mem_write', addr=MG.SCRIPT_PTR, data_hex='0000')
    def to_level(self, label):
        """from a game start or a load_level to level_ready (a level without a cutscene loads in place, in the tick)"""
        G, BS, PS = self.G, self.BS, self.PS
        pc = self.run_to([G['level_ready'], BS['LN_LAUNCH'], G['tick_done']])
        if pc == BS['LN_LAUNCH']:
            self.run_to(PS['pres']); self.run_to(PS['p_go'], 8000); self.run_to(G['start']); self.run_to(G['level_ready'])
        self.mark('%s (%s)' % (label, 'in place' if pc == G['tick_done'] else 'level_ready'))


def call_at_tick_done(e, G, addr, a):
    reg = e.call('get_registers'); sp = (reg['SP'] - 2) & 0xFFFF
    e.call('mem_write', addr=sp, data_hex='%02x%02x' % (G['tick_done'] & 255, G['tick_done'] >> 8))
    e.call('set_register', reg='SP', value=sp); e.call('set_register', reg='PC', value=addr)
    e.call('set_register', reg='AF', value=(a << 8) | (reg['AF'] & 255))


def scenario_title(R):
    R.run_to(R.PS['ts_step'], 3000)
    for _ in range(4): R.e.run(1000)
    R.mark('title and story, 4,000 frames')
    R.title_start()
    R.run_to(R.G['start']); R.run_to(R.G['level_ready']); R.ticks(20)
    R.mark('game start, 20 ticks')


def scenario_walk(R):
    e, G, BS, PS = R.e, R.G, R.BS, R.PS
    R.title_start()
    R.run_to(G['start'])
    e.call('mem_write', addr=G['guard_opts'], data_hex='01')       # (walk_level1 is recorded without guards)
    R.script(os.path.join(ROOT, 'tests', 'm4_scripts', 'walk_level1.txt'), 400)
    R.run_to(G['level_ready'])
    e.call('mem_write', addr=G['NEED_L1M'], data_hex='00')
    R.mark('level 1 start')
    assert R.ticks(800, [BS['LN_LAUNCH']]) == BS['LN_LAUNCH'], 'level 1 never ended'
    R.mark('level 1 walked (room changes, the level door)')
    R.run_to(PS['pres']); R.run_to(PS['p_go'], 8000); R.run_to(G['start']); R.run_to(G['level_ready'])
    R.mark('cutscene, level 2 start')
    e.call('mem_write', addr=G['HITP_CURR'], data_hex='01')       # (one hit point left: the guard's first hit kills)
    n = R.script(os.path.join(ROOT, 'tests', 'm6_scripts', 'level2_fight.txt'), 20)
    t = 0
    while e.mem(G['HITP_CURR'], 1)[0] and t < n + 400:
        if t == n: R.script_off()                                   # (then standing still before the guard)
        R.ticks(1); t += 1
    assert e.mem(G['HITP_CURR'], 1)[0] == 0, 'the kid did not die on level 2'
    R.script_off(); R.ticks(60)
    R.mark('level 2: a fight, the kid killed at tick %d, 60 ticks dead' % t)
    for lv in range(3, 15):
        call_at_tick_done(e, G, G['load_level'], lv)
        R.to_level('level %d' % lv)
        if R.ticks(40, [BS['LN_LAUNCH']]) is not None: raise AssertionError('level %d left by itself' % lv)
    R.mark('levels 3-14, 40 ticks each')


def scenario_traps(R):
    import kidsim, m4_game as MG
    from m4_test import ev_opts_bytes
    e, G = R.e, R.G
    R.title_start(); R.run_to(G['start']); R.run_to(G['level_ready']); R.ticks(5)
    R.mark('game start, 5 ticks')
    for name in ('frm_button.txt', 'frm_spike_btn.txt'):
        path = os.path.join(ROOT, 'tests', 'm4_scripts', name)
        o = kidsim.script_opts(path); lv = kidsim.script_level(path); _, patches = kidsim.read_script(path)
        e.call('mem_write', addr=G['ev_opts'], data_hex=ev_opts_bytes(o).hex())    # (the script's start room)
        e.call('mem_write', addr=G['guard_opts'], data_hex='00' if o['guards'] else '01')
        call_at_tick_done(e, G, G['load_level'], lv)
        R.to_level('level %d at %d:%d' % (lv, o['start'][0], o['start'][1]))
        for (rm, p, t, m) in patches:
            e.call('mem_write', addr=MG.LEVEL_ADDR + (rm - 1) * 30 + p, data_hex='%02x' % t)
            e.call('mem_write', addr=MG.LEVEL_ADDR + 720 + (rm - 1) * 30 + p, data_hex='%02x' % m)
        n = R.script(path, 20, patches_ok=True)
        R.ticks(n + 10); R.script_off(); R.ticks(20)
        R.mark('%s, %d ticks' % (name, n + 30))
    e.call('mem_write', addr=G['ev_opts'], data_hex=ev_opts_bytes({}).hex())


def scenario_duel(R):
    import duelsim as DS
    e, G, PS = R.e, R.G, R.PS
    D = syms(os.path.join(BUILD, 'duel.sym'))
    inputs, _ = DS.read_duel_script(os.path.join(ROOT, 'tests', 'duel_scripts', 'match.txt'))
    R.run_to(PS['ts_step'], 3000); e.run(37)
    for k in ('CTRL', 'D'): e.call('input_press_key', key=k)
    R.run_to(PS['p_go'], 100)
    for k in ('CTRL', 'D'): e.call('input_release_key', key=k)
    R.run_to(G['start'], 3000); R.run_to(D['d_entry'], 3000)
    R.poke(G['RD_LV_PAGE'], 0xF000, b''.join(bytes(p) for p in inputs))
    e.call('mem_write', addr=D['d_script'], data_hex='00f0')
    R.run_to(D['d_ready'], 1000)
    R.mark('duel start')
    n = 0; pc = None
    while n < len(inputs) + 200:
        pc = R.run_to([D['d_tend'], PS['pres']], 2000)
        if pc == PS['pres']: break
        n += 1
    R.mark('duel match, %d ticks' % n)
    if pc != PS['pres']: R.run_to(PS['pres'], 3000)
    R.title_start()
    R.run_to(G['start']); R.run_to(G['level_ready']); R.ticks(20)
    R.mark('the title, a new game, 20 ticks')


def run_one(name, d, image_path):
    """scenario `name` in directory d: d/rd.log (the emulator's), d/run.json (marks, pokes), d/end.img"""
    BS = syms(os.path.join(BUILD, 'boot.sym')); PS = syms(os.path.join(BUILD, 'pres.sym')); G = syms(os.path.join(BUILD, 'm4game.sym'))
    from emu import Emu
    img = open(image_path, 'rb').read()
    log = os.path.join(d, 'rd.log')
    env = {'MZ800EMU_BIN': EMU_RDLOG, 'MZ800EMU_RDLOG': log, 'POP800_RD_SIZE': rdimage.SIZE, 'POP800_RD_WAIT': str(rdimage.WAIT)}
    if name == 'duel': env['POP800_UNICARD'] = '0'
    dsk = os.path.join(d, 'pop800.dsk'); shutil.copy(os.path.join(BUILD, 'pop800.dsk'), dsk)
    with Emu(exe=rdimage.launcher(d, env)) as e:
        R = Run(e, BS, PS, G)
        assert len(R.regions) == rdimage.PAGES, 'not a 512 KB RAM disk: %d pages' % len(R.regions)
        rdlog.write_image(e, img)
        e.call('media_insert', slot='fdc0_fd0', path=dsk, ro=True)
        e.call('reset')
        R.hi = R.last = 0                   # (the reset restarts the cycle count; the log's first access comes after it)
        R.run_to(BS['launch_main'], 5000); R.run_to(PS['pres'], 5000)
        assert e.mem(BS['HO_MAIN'], 16)[BS['HO_ACTION']] == BS['ACT_TITLE']
        R.mark('boot (PRES_START)')
        globals()['scenario_' + name](R)
        R.mark('end')
        end = rdlog.read_image(e)
    open(os.path.join(d, 'end.img'), 'wb').write(end)
    json.dump({'marks': R.marks, 'pokes': R.pokes}, open(os.path.join(d, 'run.json'), 'w'))


# ---- the analysis
def analyse(name, d, img):
    J = json.load(open(os.path.join(d, 'run.json'))); log = os.path.join(d, 'rd.log')
    end = open(os.path.join(d, 'end.img'), 'rb').read()
    marks = J['marks']; pokes = [(c, p, a, bytes.fromhex(h)) for c, p, a, h in J['pokes']]
    cow = rdlog.Cow(img, BLOCK); cowf = rdlog.Cow(img, BLOCK, free=True); replay = bytearray(img)
    per = []; mi = 0; pi = 0; nrec = 0; first = None
    def at_mark(label):
        per.append((label, cow.blocks(), cowf.blocks(), cowf.peak)); cowf.peak = cowf.blocks()
    for k, pg, st, ln, cy, data in rdlog.read_log(log):
        nrec += 1
        if first is None: first = cy
        while mi < len(marks) and marks[mi][0] <= cy: at_mark(marks[mi][1]); mi += 1
        while pi < len(pokes) and pokes[pi][0] <= cy:
            _, p, a, b = pokes[pi]; o = p * 65536 + a; replay[o:o + len(b)] = b; pi += 1
        if k == 'W':
            cow.write(pg, st, data, cy); cowf.write(pg, st, data, cy); o = pg * 65536 + st; replay[o:o + ln] = data
    for _, label in marks[mi:]: at_mark(label)
    for _, p, a, b in pokes[pi:]: o = p * 65536 + a; replay[o:o + len(b)] = b
    bad = sum(1 for x, y in zip(replay, end) if x != y)
    return dict(first=first, boot_mark=marks[0][0], per=per, blocks=cow.blocks(), peak_free=max(x[3] for x in per),
                written=cow.writes, records=nrec, replay_diff=bad, outside=cow.outside, regions=cow.regions(),
                pool=sorted(cow.pool))


def main():
    a = sys.argv[1:]
    if a[:1] == ['--run']:
        run_one(a[1], a[2], a[3]); return
    image = os.path.join(BUILD, rdimage.image_name())
    if a[:1] == ['--image']: image = os.path.abspath(a[1]); a = a[2:]
    names = a or list(SCENARIOS)
    for n in names:
        if n not in SCENARIOS: raise SystemExit('rdimage_check: no scenario %s (%s)' % (n, ', '.join(SCENARIOS)))
    if not os.access(EMU_RDLOG, os.X_OK):
        raise SystemExit('rdimage_check: needs mz800emu with the RAM-disk log at %s (POP800_RDLOG_EMU; '
                         'tools/ci/build_deps.sh emu_rdlog builds it)' % EMU_RDLOG)
    print('rdimage_check: %s, the emulator %s' % (os.path.relpath(image, ROOT), EMU_RDLOG))
    img = open(image, 'rb').read()
    check('the image is 512 KB', len(img) == rdimage.PAGES * 65536, len(img))
    side = open(image + '.sha256').read().split()
    check('the image\'s sidecar: its sha256', side[0] == rdimage.sha256(image), side[:2])
    check('the image was made from this build/pop800.dsk (sha256)', side[2] == rdimage.sha256(os.path.join(BUILD, 'pop800.dsk')),
          'the image belongs to another disk: make rdimage')
    os.makedirs(OUT, exist_ok=True)
    procs = {}; t0 = time.time()
    def start(n):
        d = os.path.join(OUT, n); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
        procs[n] = subprocess.Popen([sys.executable, os.path.abspath(__file__), '--run', n, d, image],
                                    stdout=open(os.path.join(d, 'out.txt'), 'w'), stderr=subprocess.STDOUT, cwd=d)
    waiting = list(names)
    for n in waiting[:JOBS]: start(n)                       # (at most JOBS emulators at a time)
    waiting = waiting[JOBS:]
    res = {}; union = set()
    for n in names:
        rc = procs[n].wait(); d = os.path.join(OUT, n)
        if waiting: start(waiting.pop(0))
        print('%s (%.0f s):' % (n, time.time() - t0))
        if rc:
            check('%s: the scenario ran' % n, False, open(os.path.join(d, 'out.txt')).read()[-1500:]); continue
        r = res[n] = analyse(n, d, img)
        check('%s: the log is complete (the image + the pokes + %d logged runs = the RAM disk at the end)' % (n, r['records']),
              r['replay_diff'] == 0 and r['records'] > 0, '%d bytes differ' % r['replay_diff'])
        check('%s: the log and the marks count the same cycles (the first access after the reset, before the boot\'s end)' % n,
              r['first'] < r['boot_mark'] < 1 << 32, (r['first'], r['boot_mark']))
        print('    blocks of 1 KB in the pool after each phase (a card that frees a block matching the image again: '
              'its blocks then, its peak within the phase)')
        for label, b, bf, pf in r['per']: print('    %4d   (%2d, peak %2d)  %s' % (b, bf, pf, label))
        boot = r['per'][0]
        check('%s: the boot allocates %d blocks (at most %d; %d with the freeing card)' % (n, boot[1], BOOT_MAX, boot[2]),
              boot[0] == 'boot (PRES_START)' and boot[1] <= BOOT_MAX)
        check('%s: the pool peaks at %d blocks of 1 KB (budget %d; the freeing card: %d)' % (n, r['blocks'], BUDGET, r['peak_free']),
              r['blocks'] <= BUDGET)
        check('%s: no write outside the image' % n, r['outside'] == 0, r['outside'])
        print('    %d bytes written; allocated: %s' % (r['written'], rdlog.format_regions(r['regions'])))
        union |= set(r['pool'])
    json.dump(res, open(os.path.join(OUT, 'results.json'), 'w'), indent=1)
    if res:
        print('rdimage_check: peak blocks %s' % ', '.join('%s %d' % (n, r['blocks']) for n, r in res.items()))
        check('all scenarios\' blocks together (one session playing them all): %d (budget %d)' % (len(union), BUDGET),
              len(union) <= BUDGET)
    if FAILS: raise SystemExit('rdimage_check: %d FAILED: %s' % (len(FAILS), '; '.join(FAILS)))
    print('rdimage_check: all OK')


if __name__ == '__main__':
    main()
