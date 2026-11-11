#!/usr/bin/env python3
"""Duel phase 2 (docs/duel-design.md section 12): the Z80 duel (the game, build/m4game.mzf, with the duel patch
src/duel/duel.asm laid in as the launcher lays it: build/duel_patch.json) against tools/duelsim.py, tick for tick, on
the scripted duels of tests/duel_scripts. Per tick the four lines duelsim writes: the kid line (mid-tick, after player
1's frame: duel.asm d_mid), the G line (the shadow and the fight's globals, after the hit points: d_gline), the N line
(play_next_sound: the game's snd_snap) and the D line (the round state, the 68-byte hash, both blocks: d_tend); and
the state before the first tick (d_ready: the D 0 line's hash). The Z80's own hash (d_hashv) must equal the hash of
the 68 bytes as the harness reads them, and duelsim's. Taken by tracepoints (tools/emu.py: the emulator never stops).
The inputs: the script's two bytes a tick in RAM-disk page 5 (game.asm RD_SCRIPT), read by duel.asm d_input (d_script).

  --cdl        the code log over every script (mz800emu's CDL): no byte of a hole outside the duel's pieces executed,
               none of tools/duelpatch.py's COLD callees (the call-graph check's other half)
  --shots DIR  screenshots of the duel at a few ticks per script (DIR/<script>_<tick>.png)
usage: duel_z80.py [--cdl] [--shots DIR] [script.txt ...]   (default: tests/duel_scripts/*.txt)"""
import glob, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools')); sys.path.insert(0, os.path.join(ROOT, 'tests'))
from m3_test import syms, write_pack
from m4_test import level_cksum
from emu import Emu, Snap
import m4_game as G
import duelsim as DS, duelpatch

B = os.path.join(ROOT, 'build')
RD_SCRIPT = 0xF000                      # game.asm RD_SCRIPT (page RD_LV_PAGE)
SHOT_TICKS = (1, 12, 40, 80)
s8 = lambda v: v - 256 if v > 127 else v


def patch_in(e, S, D, script_bytes):
    """as the launcher (src/boot/boot.asm ACT_DUEL): the staged pieces into the RAM-disk scratch, the main piece over
    the game's main loop; then the harness's script and its pointer"""
    j = json.load(open(os.path.join(B, 'duel_patch.json')))
    st = j['stage']; write_pack(e, bytes.fromhex(st['data']), st['page'], st['addr'])
    for addr, hx in j['main']:
        e.call('mem_write', addr=addr, data_hex=hx)
    write_pack(e, script_bytes, S['RD_LV_PAGE'], RD_SCRIPT)
    e.call('mem_write', addr=D['d_script'], data_hex='%02x%02x' % (RD_SCRIPT & 255, RD_SCRIPT >> 8))


def kid_line(m, S, tick):
    """duelsim's kid line (kidsim trace_line) from the d_mid capture"""
    k = m.mem(S['KID_REC'], 16); hp = m.mem(S['HITP_CURR'], 2); n = m.mem(S['TROBS_N'], 2)
    cs = level_cksum(m.mem(S['LEVEL'], 1440), k[9])
    return '%d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d' % (tick, k[0], k[1], k[2], s8(k[3]), s8(k[5]), s8(k[4]),
        k[6], s8(k[7]), s8(k[8]), k[9], k[14] | (k[15] << 8), s8(k[13]), hp[0], hp[1], n[0], n[1], cs)


def guard_line(m, S):
    """the G line (kidsim trace_guard_line, guard.asm's G_SNAP layout) from the d_gline capture"""
    g = m.mem(S['GUARD_REC'], 16); gl = m.mem(S['g_glob'], 14)
    v = [g[0], g[1], g[2], s8(g[3]), s8(g[5]), s8(g[4]), g[6], s8(g[7]), s8(g[8]), g[9], g[14] | (g[15] << 8), s8(g[13]),
         g[12], g[11], gl[0], gl[1], m.mem(S['HITP_CURR'], 1)[0], m.mem(S['KID_REC'] + 12, 1)[0]] + list(gl[4:14])
    return 'G ' + ' '.join(str(x) for x in v)


def state_bytes(m, S, D):
    """the 68 hashed bytes (duelsim state_bytes) as the Z80 has them"""
    g = m.mem(S['g_glob'], 14); blk1 = list(m.mem(S['CTRL1'], 6)) + [m.mem(S['HAVE_SWORD'], 1)[0], g[11], g[5]]
    return (list(m.mem(S['KID_REC'], 32)) + list(m.mem(S['HITP_CURR'], 2)) + [g[0], g[1], g[4]] + list(g[6:11]) +
            [g[12], g[13]] + blk1 + list(m.mem(D['d_blk2'], 9)) + list(m.mem(D['d_rounds'], 6)))


def duel_line(m, S, D, tick):
    r = m.mem(D['d_rounds'], 6); i = m.mem(D['d_in1'], 2); h = m.mem(D['d_hashv'], 2)
    sb = state_bytes(m, S, D); hv = h[0] | (h[1] << 8)
    own = DS.hash16(sb)
    line = 'D %d %d %d %d %d %d %d %d %d %d %s %s' % (tick, i[0], i[1], r[0], r[1], r[2], r[3], r[4], r[5], hv,
                                                    ' '.join(map(str, sb[44:53])), ' '.join(map(str, sb[53:62])))
    return line, own == hv


def ranges(S, D):
    gv = (S['KID_REC'], 82)                         # the records, CHAR_SAVE, the globals
    ov = (S['HITP_CURR'], 16)                       # OV: hit points, have_sword, TROBS_N, MOBS_N
    kv = (S['CTRL1'], 6)
    dv = (D['d_rounds'], D['d_blk2'] + 90 - D['d_rounds'])
    return {'ready': [gv, ov, kv, dv], 'mid': [gv, ov, (S['LEVEL'], 1440)], 'g': [gv, ov],
            'n': [(S['SND_STOPS'], 1)], 'end': [gv, ov, kv, dv]}


def run_script(e, S, D, path, shots=None):
    inputs, opts = DS.read_duel_script(path)
    ref, sim = DS.run_duel(path)
    script = b''.join(bytes(p) for p in inputs)
    G.setup(e, DS.ARENA_LEVEL, fs_run=False)
    patch_in(e, S, D, script)
    R = ranges(S, D); at = {}
    e.call('bp_clear'); e.trace_clear()
    if CDL[0]:                                  # the code log and the profiler from the duel's entry on (the level start
        e.call('bp_add', addr=D['d_entry'])     # before it is the game's, unpatched)
        for _ in range(3):
            r = e.run(1000)
            if r['stopped_by'] == 'breakpoint': break
        assert r['stopped_by'] == 'breakpoint', r
        e.call('bp_clear'); e.call('cdl_start'); e.call('profiler_start')
    for k, a in (('ready', D['d_ready']), ('mid', D['d_mid']), ('g', D['d_gline']), ('n', S['snd_snap']), ('end', D['d_tend'])):
        e.trace_add(a, regs=('BC', 'DE') if k == 'n' else (), mem=R[k]); at[a] = k
    got = []; tick = 0; stops = None; bad = 0; first = None; hash_ok = True; ends = []
    want_ticks = sum(1 for l in ref if l.startswith('D ')) - 1
    shot_at = set(t for t in SHOT_TICKS if t <= want_ticks) if shots else set()
    frames = 0
    while tick < want_ticks:
        r = e.run(100); frames += 100
        assert frames < 400 + 60 * want_ticks, (path, 'no progress', tick)
        for rec in e.trace_read():
            k = at[rec['addr']]
            m = Snap(R[k], rec)
            if k == 'ready':
                line, ok = duel_line(m, S, D, 0)
                got.append('D 0 0 0 0 0 0 0 0 0 %s' % line.split()[10]); hash_ok &= ok
            elif k == 'mid':
                tick += 1; got.append(kid_line(m, S, tick - 1))   # (duelsim: before its tick + 1)
            elif k == 'g': got.append(guard_line(m, S))
            elif k == 'n':
                st = m.mem(S['SND_STOPS'], 1)[0]; bc = rec['regs']['BC']; de = rec['regs']['DE']
                d = 0 if stops is None else (st - stops) & 0xFF; stops = st
                got.append('N %d %d %d %d' % (s8(bc & 0xFF), s8(bc >> 8), de & 0xFF, d))
            elif k == 'end':
                ends.append(rec['frame'])
                line, ok = duel_line(m, S, D, tick); hash_ok &= ok
                # duelsim's order a tick: the kid line, G, D, N
                n_line = got.pop(); got.append(line); got.append(n_line)
                if tick in shot_at:
                    e.run(12); e.screenshot(os.path.join(shots, '%s_%03d.png' % (os.path.splitext(os.path.basename(path))[0], tick)))
            if tick >= want_ticks and k == 'end': break
        if tick >= want_ticks: break
    e.trace_clear()
    n = min(len(ref), len(got))
    for i in range(n):
        if ref[i] != got[i]:
            bad += 1
            if first is None: first = (i, ref[i], got[i])
    if len(ref) != len(got): bad += 1; first = first or (n, 'lines %d' % len(ref), 'lines %d' % len(got))
    pace = (ends[-1] - ends[2]) / (len(ends) - 3) if len(ends) > 3 else 0     # (after the arena's draw)
    return bad, first, hash_ok, want_ticks, pace


CDL = [False]


def cdl_check(e, S, D):
    """after the scripts (the code log and the profiler ran from each one's d_entry): no byte of a hole outside the
    duel's pieces executed, no call into a hole but to a duel routine, none of duelpatch.COLD's callees executed.
    -> (errors, figures)"""
    import struct, tempfile
    e.call('cdl_stop'); e.call('profiler_stop')
    prof = e.call('profiler_get', limit=1000)['entries']
    d = tempfile.mkdtemp(prefix='duelcdl'); path = os.path.join(d, 'cdl')
    e.call('cdl_export', path=path)
    ram = open(path + '_ram.cdl', 'rb').read()
    x = [struct.unpack_from('<I', ram, 16 * a + 8)[0] for a in range(0x10000)]
    pieces = sorted((D[k], D[k + '_end'], k) for k in D if k.startswith('P_') and not k.endswith('_end'))
    holes = [(D[k], D[k + '_END'], k) for k in D if k.startswith('H_') and not k.endswith('_END') and not k.startswith(('H_D1', 'H_SD'))]
    in_piece = lambda a: any(p[0] <= a < p[1] for p in pieces)
    errs = []
    for lo, hi, k in holes:
        bad = [a for a in range(lo, hi) if x[a] and not in_piece(a)]
        if bad: errs.append('%s: executed outside the pieces at %s' % (k, ' '.join('%04X' % a for a in bad[:8])))
    duel_labels = set(v for k, v in D.items() if any(p[0] <= v < p[1] for p in pieces))
    for it in prof:
        a = it['addr']
        if any(lo <= a < hi for lo, hi, k in holes) and a not in duel_labels:
            errs.append('a call into %s at %04X (%d calls)' % ([k for lo, hi, k in holes if lo <= a < hi][0], a, it['calls']))
    for (caller, callee) in duelpatch.COLD:
        if x[S[callee]]: errs.append('COLD %s executed' % callee)
    ran = sum(1 for lo, hi, k in pieces for a in range(lo, hi) if x[a])
    fig = 'executed: %d of the pieces\' %d bytes; %d routines called' % (ran, sum(hi - lo for lo, hi, k in pieces), len(prof))
    import shutil; shutil.rmtree(d, ignore_errors=True)
    return errs, fig


def main():
    args = sys.argv[1:]
    shots = None; cdl = CDL[0] = '--cdl' in args
    if cdl: args.remove('--cdl')
    if '--shots' in args:
        i = args.index('--shots'); shots = args[i + 1]; del args[i:i + 2]; os.makedirs(shots, exist_ok=True)
    scripts = args or sorted(glob.glob(os.path.join(ROOT, 'tests', 'duel_scripts', '*.txt')))
    S = syms(os.path.join(B, 'm4game.sym')); D = syms(os.path.join(B, 'duel.sym'))
    total = 0
    with Emu() as e:
        if cdl: e.call('cdl_reset'); e.call('profiler_reset')
        for sp in scripts:
            bad, first, hok, n, pace = run_script(e, S, D, sp, shots)
            total += bad + (0 if hok else 1)
            print('%-16s %4d ticks (%.2f frames a tick), %d differing lines%s%s' % (os.path.basename(sp), n, pace, bad, '' if hok else ', the Z80 hash differs from its state',
                  '' if not first else '; first at line %d:\n   sim %s\n   z80 %s' % first), flush=True)
            if CDL[0]: e.call('cdl_stop'); e.call('profiler_stop')
        if CDL[0]:
            errs, fig = cdl_check(e, S, D)
            print('code log and profiler over the scripts: %s; %s' % ('; '.join(errs) if errs else 'no hole reached', fig))
            total += len(errs)
    print('total differing:', total)
    sys.exit(1 if total else 0)


if __name__ == '__main__':
    main()
