#!/usr/bin/env python3
"""Duel phase 2 (docs/duel-design.md section 12): the Z80 duel (the game, build/m4game.mzf, with the duel patch
src/duel/duel.asm laid in as the launcher lays it: build/duel_patch.json) against tools/duelsim.py, tick for tick, on
the scripted duels of tests/duel_scripts. Per tick the four lines duelsim writes: the kid line (mid-tick, after player
1's frame: duel.asm d_mid), the G line (the shadow and the fight's globals, after the hit points: d_gline), the N line
(play_next_sound: the game's snd_snap) and the D line (the round state, the 129-byte hash, both blocks: d_tend); and
the state before the first tick (d_ready: the D 0 line's hash). The Z80's own hash (d_hashv) must equal the hash of
the 129 bytes as the harness reads them, and duelsim's. Drawing and audio, every tick against duelsim's state: the
images each player is drawn with (the blades, DRAW_MAP), the bottom text's key (duel.asm d_key: hud_key) and the
round's and match's tunes (duel.asm ds_j: jingles). Taken by tracepoints (tools/emu.py: the emulator never stops).
Then (with the default scripts, or --blades) player 2's blade (docs/duel-design.md 16.4, duel.asm d_blade): at the ticks
player 2 is first drawn in each of the body images that carry the blade in each facing (all 10 pairs the duel shows
since D19 required; tests/duel_blade/p2_both_ways.txt turns player 2 round), the blade's pixels
(tools/duelblade.py) on the screen are white, its suit light blue (with d_blade disabled the check fails: checked).
The inputs: the script's two bytes a tick in RAM-disk page 5 (game.asm RD_SCRIPT), read by duel.asm d_input (d_script).

  --cdl        the code log over every script (mz800emu's CDL): no byte of a hole outside the duel's pieces executed,
               none of tools/duelpatch.py's COLD callees (the call-graph check's other half)
  --shots DIR  screenshots of the duel at a few ticks per script (DIR/<script>_<tick>.png)
usage: duel_z80.py [--cdl] [--blades] [--shots DIR] [script.txt ...]   (default: tests/duel_scripts/*.txt and --blades)"""
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
SHOT_TICKS = (1, 12, 27, 40, 80)
# the blades (docs/duel-design.md 12.8): the kid frame each player is drawn with (duel.asm d_ppchar)
DRAW_MAP = ({161: 158}, {161: 157, 158: 157, 170: 157, 171: 157})
import build_assets as BA
SWORD_TBL = BA.frame_tables()['sword']
# the HUD and the tunes (duel.asm d_hud, d_snd; docs/duel-design.md 13): drawing and audio only
TX_ROUND, TX_SCORE, TX_WON, TX_DRAW, TX_MATCH, TX_PROMPT = range(6)
ROUND_TEXT_TICKS, HUD_ALT, JINGLE_DELAY, SND_ROUNDJ, SND_MATCHJ = 20, 32, 3, 37, 41


def hud_key(sim, tick, rtick):
    """the bottom text duel.asm d_hud shows after tick `tick` (rtick: ticks drawn since the round's start): (kind,
    numbers)"""
    if sim.match: return (TX_MATCH if tick & HUD_ALT == 0 else TX_PROMPT, sim.match, 0, 0)
    if sim.timer:
        if sim.result == DS.RES_DRAW: return (TX_DRAW, 3, 0, 0)
        return (TX_MATCH if sim.score[sim.result - 1] >= DS.WINS else TX_WON, sim.result, 0, 0)
    n = min(99, (sim.rounds & 0xFF) + 1)
    return (TX_ROUND, n, 0, 0) if rtick < ROUND_TEXT_TICKS else (TX_SCORE, n, sim.score[0], sim.score[1])


def jingle(sim):
    """the tune duel.asm d_snd starts at this tick's end, or None"""
    if sim.timer != DS.ROUND_END_TICKS - JINGLE_DELAY or sim.result == DS.RES_DRAW: return None
    return SND_MATCHJ if sim.score[sim.result - 1] >= DS.WINS else SND_ROUNDJ


def drawn_ids(sim, rec, p):
    """(body image, sword image or None) player p's record is drawn with: the kid's frame table (D1), the frame remapped
    by DRAW_MAP, the sword when drawn (overlay.asm pp_char: sheathed but frames 229-237: none)"""
    f = DRAW_MAP[p].get(rec.frame, rec.frame)
    img, sw = sim.frames[f][0], sim.frames[f][1] & 0x3F
    sid = None
    if (rec.sword or 229 <= rec.frame < 238) and sw and SWORD_TBL[sw][0] != 0xFF: sid = SWORD_TBL[sw][0] + 1
    return (img + 1 if img != 255 else None, sid)
s8 = lambda v: v - 256 if v > 127 else v


def patch_in(e, S, D, script_bytes, seed=None):
    """as the launcher (src/boot/boot.asm ACT_DUEL): the staged pieces into the RAM-disk scratch, the main piece over
    the game's main loop; then the harness's script and its pointer, and the arenas: the script's seed (d_seed), or
    none: the fixed arena every round (d_afix)"""
    j = json.load(open(os.path.join(B, 'duel_patch.json')))
    for st in (j['stage'], j['stage2']): write_pack(e, bytes.fromhex(st['data']), st['page'], st['addr'])
    for addr, hx in j['main']:
        e.call('mem_write', addr=addr, data_hex=hx)
    write_pack(e, script_bytes, S['RD_LV_PAGE'], RD_SCRIPT)
    e.call('mem_write', addr=D['d_script'], data_hex='%02x%02x' % (RD_SCRIPT & 255, RD_SCRIPT >> 8))
    e.call('mem_write', addr=D['d_seed'], data_hex='%02x%02x' % ((seed or 0) & 255, (seed or 0) >> 8))
    e.call('mem_write', addr=D['d_afix'], data_hex='00' if seed is not None else '01')


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
    """the 129 hashed bytes (duelsim state_bytes) as the Z80 has them"""
    g = m.mem(S['g_glob'], 14); blk1 = list(m.mem(S['CTRL1'], 6)) + [m.mem(S['HAVE_SWORD'], 1)[0], g[11], g[5]]
    return (list(m.mem(D['d_aidx'], 1)) + list(m.mem(S['KID_REC'], 32)) + list(m.mem(S['HITP_CURR'], 2)) + [g[0], g[1], g[4]] + list(g[6:11]) +
            [g[12], g[13]] + blk1 + list(m.mem(D['d_blk2'], 9)) + list(m.mem(D['d_rounds'], 6)) +
            list(m.mem(S['LV_FG'] + (m.mem(D['d_room'], 1)[0] - 1) * 30, 30)) +       # (the arena room's tiles and modifiers)
            list(m.mem(S['LV_FG'] + 720 + (m.mem(D['d_room'], 1)[0] - 1) * 30, 30)))


def duel_line(m, S, D, tick):
    r = m.mem(D['d_rounds'], 6); i = m.mem(D['d_in1'], 2); h = m.mem(D['d_hashv'], 2)
    sb = state_bytes(m, S, D); hv = h[0] | (h[1] << 8)
    own = DS.hash16(sb)
    line = 'D %d %d %d %d %d %d %d %d %d %d %s %s' % (tick, i[0], i[1], r[0], r[1], r[2], r[3], r[4], r[5], hv,
                                                    ' '.join(map(str, sb[45:54])), ' '.join(map(str, sb[54:63])))
    return line, own == hv


def ranges(S, D):
    gv = (S['KID_REC'], 82)                         # the records, CHAR_SAVE, the globals
    ov = (S['HITP_CURR'], 16)                       # OV: hit points, have_sword, TROBS_N, MOBS_N
    kv = (S['CTRL1'], 6)
    dv = (D['d_room'], D['d_hashv'] + 2 - D['d_room'])     # (the arena's room, entry, the round state, the inputs, the hash)
    lv = (S['LEVEL'], 1440)                         # (the hash: the arena room's tiles and modifiers)
    bv = (D['d_blk2'], 90)                          # (player 2's block: over d_boot, docs/duel-design.md 18)
    return {'ready': [gv, ov, kv, dv, bv, lv], 'mid': [gv, ov, lv], 'g': [gv, ov],
            'n': [(S['SND_STOPS'], 1)], 'end': [gv, ov, kv, dv, bv, lv],
            'drawn': [(S[k] + S['SD_FRAME'], 1) for k in ('SPR_A', 'SPR_S', 'SPR_G', 'SPR_GS')] + [(D['d_key'], 4)],
            'jingle': []}


# player 2's blade (duel.asm d_blade): scripts where player 2 shows the images that carry it, together every image in
# both facings (tests/duel_blade: player 2 runs past player 1 and does it all facing right too)
BLADE_SCRIPTS = ('duel_scripts/apart.txt', 'duel_scripts/clash.txt', 'duel_blade/p2_both_ways.txt')
# the images of frames 237 and 239 (put_sword_away, seq 92: SDLPoP's automatic sheathe) are never shown since D19 (the
# sword by hand, docs/duel-design.md 23: down puts it away fast, frames 234, 236, 238, 240)
BLADE_UNSHOWN = (169, 171)


def blade_check(S, D):
    """[failures]: for every (image, facing) pair of the blade images the duel shows, at the first tick of BLADE_SCRIPTS that duelsim
    draws player 2 so (drawn_ids), after its drawing the blade's pixels white on the screen; all 10 pairs required"""
    import duelblade as BL
    fails = []; seen = set(); plan = []; todo = set((i, d) for i in BL.BANDS if i not in BLADE_UNSHOWN for d in (-1, 0))
    for script in BLADE_SCRIPTS:
        inputs, opts = DS.read_duel_script(os.path.join(ROOT, 'tests', script)); sim = DS.DuelSim(seed=opts['seed']); want = {}
        for t, (a, b) in enumerate(inputs, 1):
            sim.step(a, b); k = (drawn_ids(sim, sim.Guard, 1)[0], sim.Guard.direction)
            if k in todo: todo.discard(k); want[t] = k[0]
        if want: plan.append((script, inputs, opts, want))
    if todo: fails.append('pairs (image, direction) the scripts never show: %s' % sorted(todo))
    for script, inputs, opts, want in plan:
        with Emu() as e:
            G.setup(e, DS.ARENA_LEVEL, fs_run=False)
            patch_in(e, S, D, b''.join(bytes(p) for p in inputs), opts['seed'])
            for t in range(1, max(want) + 2):
                e.call('bp_clear'); e.call('bp_add', addr=D['d_tend']); n = 0
                while e.run(200)['stopped_by'] != 'breakpoint':
                    n += 200; assert n < 4000, (script, t, 'no progress')
                if t - 1 not in want: continue
                sd = e.mem(S['SPR_G'], 24)            # (tick t - 1's drawing: the descriptor as it was drawn)
                img, mir, x, y = sd[8], sd[9], sd[6] | sd[7] << 8, sd[5]
                if img != want[t - 1]:
                    fails.append('%s tick %d: player 2 drawn as image %d, not %d' % (script, t - 1, img, want[t - 1])); continue
                wb = BL.image(img)[0]; pl = e.vram_planes()
                col = lambda px, py: sum(((pl[q][py * 40 + px // 8] >> (px & 7)) & 1) << q for q in range(4))
                px = BL.blade(img)
                got = [col(x + (wb * 8 - 1 - dx if mir else dx), y + dy) for dy, dx in px]
                suit = sum(1 for yy in range(y, y + sd[3]) for xx in range(x, x + wb * 8) if 0 <= xx < 320 and col(xx, yy) == 9)
                ok = all(c == 15 for c in got) and suit > 0
                print('  blade, %s tick %d: image %d %s, %d pixels white %s, the suit light blue (%d pixels)%s' % (
                    script, t - 1, img, 'mirrored' if mir else 'as stored', sum(c == 15 for c in got), 'ok' if ok else 'FAILED',
                    suit, '' if ok else ' ' + str(got)), flush=True)
                if not ok: fails.append('%s tick %d image %d' % (script, t - 1, img))
                seen.add((img, mir))
    want_n = 2 * len([i for i in BL.BANDS if i not in BLADE_UNSHOWN])
    if len(seen) != want_n: fails.append('(image, mirror) pairs checked: %d of %d' % (len(seen), want_n))
    return fails


def run_script(e, S, D, path, shots=None):
    inputs, opts = DS.read_duel_script(path)
    ref, sim = DS.run_duel(path)
    exp = []; s2 = DS.DuelSim(seed=opts['seed'])                             # the images each tick's drawing must show (DRAW_MAP)
    hud = []; jing = []; at_tick = [0]; reset = [0]         # the bottom text and the tunes each tick
    rr = s2.round_reset
    def round_reset():
        reset[0] = at_tick[0] - 1; rr()                     # (a reset inside tick t: t's drawing counts 1)
    s2.round_reset = round_reset
    for a, b in inputs:
        at_tick[0] += 1; t = at_tick[0]
        s2.step(a, b); exp.append((drawn_ids(s2, s2.Kid, 0), drawn_ids(s2, s2.Guard, 1)))
        hud.append(hud_key(s2, t, min(255, t - reset[0])))
        j = jingle(s2)
        if j: jing.append((t, j))
    script = b''.join(bytes(p) for p in inputs)
    G.setup(e, DS.ARENA_LEVEL, fs_run=False)
    patch_in(e, S, D, script, opts['seed'])
    R = ranges(S, D); at = {}
    e.call('bp_clear'); e.trace_clear()
    if CDL[0]:                                  # the code log and the profiler from the duel's entry on (the level start
        e.call('bp_add', addr=D['d_entry'])     # before it is the game's, unpatched)
        for _ in range(3):
            r = e.run(1000)
            if r['stopped_by'] == 'breakpoint': break
        assert r['stopped_by'] == 'breakpoint', r
        e.call('bp_clear'); e.call('cdl_start'); e.call('profiler_start')
    for k, a in (('ready', D['d_ready']), ('mid', D['d_mid']), ('g', D['d_gline']), ('n', S['snd_snap']), ('end', D['d_tend']),
                 ('drawn', D['d_done']), ('jingle', D['ds_j'])):
        e.trace_add(a, regs=('BC', 'DE') if k == 'n' else ('AF',) if k == 'jingle' else (), mem=R[k]); at[a] = k
    jgot = []; got = []; tick = 0; stops = None; bad = 0; first = None; hash_ok = True; ends = []; dbad = []
    want_ticks = sum(1 for l in ref if l.startswith('D ')) - 1
    shot_at = set(t for t in SHOT_TICKS if t <= want_ticks) if shots else set()
    frames = 0
    while len(ends) < want_ticks:                   # (to the last tick's end: its D line; a run of 100 frames may stop
                                                    # between its kid line and its end)
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
            elif k == 'drawn':
                a, sa, g, sg = (m.mem(S[x] + S['SD_FRAME'], 1)[0] for x in ('SPR_A', 'SPR_S', 'SPR_G', 'SPR_GS'))
                (eb1, es1), (eb2, es2) = exp[tick - 1]
                if (eb1 and a != eb1) or (es1 and sa != es1) or (eb2 and g != eb2) or (es2 and sg != es2):
                    dbad.append((tick, (a, sa, g, sg), (eb1, es1, eb2, es2)))
                key = tuple(m.mem(D['d_key'], 4))
                if key != hud[tick - 1]: dbad.append((tick, 'text %s' % (key,), 'text %s' % (hud[tick - 1],)))
            elif k == 'jingle': jgot.append((tick, rec['regs']['AF'] >> 8))
            elif k == 'end':
                ends.append(rec['frame'])
                line, ok = duel_line(m, S, D, tick); hash_ok &= ok
                # duelsim's order a tick: the kid line, G, D, N
                n_line = got.pop(); got.append(line); got.append(n_line)
                if tick in shot_at:
                    e.run(12); e.screenshot(os.path.join(shots, '%s_%03d.png' % (os.path.splitext(os.path.basename(path))[0], tick)))
            if tick >= want_ticks and k == 'end': break
        if len(ends) >= want_ticks: break
    e.trace_clear()
    n = min(len(ref), len(got))
    for i in range(n):
        if ref[i] != got[i]:
            bad += 1
            if first is None: first = (i, ref[i], got[i])
    if len(ref) != len(got): bad += 1; first = first or (n, 'lines %d' % len(ref), 'lines %d' % len(got))
    if dbad:                                    # the images drawn (body, sword of each) against duelsim + DRAW_MAP
        bad += len(dbad); first = first or (dbad[0][0], 'drawn %s' % (dbad[0][2],), 'drawn %s' % (dbad[0][1],))
    if jgot != jing:                            # the tunes (tick, sound id)
        bad += 1; first = first or (0, 'tunes %s' % jing, 'tunes %s' % jgot)
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
    holes = [(D[k], D[k + '_END'], k) for k in D if k.startswith('H_') and not k.endswith('_END') and not k.startswith(duelpatch.LIVE_HOLES)]
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
    blades = '--blades' in args or not [a for a in args if a.endswith('.txt')]
    if '--blades' in args: args.remove('--blades')
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
    if blades:
        bf = blade_check(S, D)
        print('player 2\'s blade: %s' % ('; '.join(bf) if bf else 'white in every image the duel shows, both facings'))
        total += len(bf)
    print('total differing:', total)
    sys.exit(1 if total else 0)


if __name__ == '__main__':
    main()
