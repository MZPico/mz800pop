#!/usr/bin/env python3
"""M4/M5/M6: the Z80 game logic (build/m4test.mzf) versus tools/kidsim.py (itself verified against SDLPoP). Runs each
control script through both, the way kidsim.run_script plays it (restarts by the keys column, level switches, the
time option), and compares after every tick: the kid's state (kid line), for scripts with guards on (kidsim
script_opts: '# guards', '# guard room:tile:dir:skill:color') the guard trace line ('G ...', kidsim guard_line) from
the snapshot guard.asm takes where SDLPoP's hook writes it (after check_guard_fallout), the level-event state line
('S ...', kidsim trace_state_line, for every script) from m4test.asm's state_snap, the sound line ('N queued started
playing stops', kidsim sound_line in the silent sound mode, every script) from m4test.asm's snd_snap (src/m4/sound.asm
snd_next), and the EXPIRED / END points.
A tick that restarts the level (Ctrl+A) has no lines: the Z80 runs through it without stopping.
Level patches ('# patch') are written where SDLPoP's hook applies them: at the first tick's control step (a
breakpoint at guards_off_chk), after that tick's animated tiles. Script options go to the Z80 through guard.asm's guard_opts and ev_opts blocks (see guard_opts_bytes, ev_opts_bytes);
until a guard has entered (Guard.direction none on both sides) only the global fields of the G line are compared:
kidsim's Guard then holds what the level's intro cutscene left in SDLPoP (GUARD_LEFTOVER), the Z80's is zero.
Sound modes (M7 step 5): every script runs in the silent mode (SND_MODE 0, kidsim 'silent') unless it says
'# sound ticks' (tests/m7_scripts): then both run the ticks model (psg.asm SND_MODE 2 poked before the start, kidsim
'ticks'; the level 1 music crouch only with '# level1 music': sound.asm NEED_L1M poked at the first control tick) and
the comparison is exact: alive's value, every tick after a death. The Z80's ticks lengths (SND_T12/SND_T10, copied
by game_init) are checked against kidsim's sound_ticks_tables once.
usage: m4_test.py [script.txt ...]   (default: the scripts in tests/m4_scripts/, tests/m6_scripts/, tests/m5_scripts/,
tests/m7_scripts/)"""
import glob, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools')); sys.path.insert(0, os.path.join(ROOT, 'tests'))
from m3_test import syms, LEVEL_ADDR, RV, write_pack
from emu import Emu
from popdata import Level, T
import kidsim
KV = 0x0a00; SCRIPT = 0xE400; DIR_KID = 0xF600      # SCRIPT: m4test.asm
KV_SNAP = 0x0AC0; TR_SNAP = 0x0b30 + 26
S_SNAP = 0x02C0; S_N = 27                           # m4test.asm state_snap (+ a counter byte)
N_SNAP = 0x02B0                                     # m4test.asm snd_snap: queued, started, playing, stops, counter
LEVEL_TYPE = RV + 20
A = os.path.join(ROOT, 'build', 'assets')
GAME_OVER = {1: 'EXPIRED', 2: 'END', 3: 'TITLE'}    # objects.asm GO_*

def z80_state(e, tick):
    """The kid's state as of SDLPoP's trace point (snapshot taken by kid_tick), in kidsim's trace format."""
    k = e.mem(KV_SNAP, 16); t = e.mem(TR_SNAP, 6)
    s8 = lambda v: v - 256 if v > 127 else v
    seq = k[14] | (k[15] << 8)
    return '%d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d' % (tick, k[0], k[1], k[2], s8(k[3]), s8(k[5]), s8(k[4]), k[6], s8(k[7]), s8(k[8]), k[9], seq, s8(k[13]),
        t[0], t[1], t[2], t[3], t[4] | (t[5] << 8))

def guard_opts_bytes(o):
    """guard.asm guard_opts: flags (bit 0 guards off, bit 1 sword), count, (room, tile, dir, skill, colour) each"""
    b = bytes([(0 if o['guards'] else 1) | (2 if o['sword'] else 0), len(o['place'])])
    for g in o['place']: b += bytes(v & 0xFF for v in g)
    return b

def ev_opts_bytes(o):
    """guard.asm ev_opts: the kid's start (room, tile, dir; room 0 = the level's), the time left (min, tick word)"""
    room, pos, d = o['start'] if o.get('start') else (0, 0, 0)
    mn, tk = o['time'] if o.get('time') else (60, 719)
    return bytes([room & 0xFF, pos & 0xFF, d & 0xFF, mn & 0xFF, tk & 0xFF, tk >> 8])

def encode(moves, keys):
    """m4test / game control bytes: x+1, (y+1) << 2, shift << 4, Ctrl+A << 5; before it 0x40 + a key code (src/m4/keys.asm,
    the keys field's bits 3-7); 0xff ends"""
    b = bytearray()
    for (x, y, sh), k in zip(moves, keys):
        if k >> 3: b.append(0x40 | (k >> 3))
        b.append(((x + 1) & 3) | (((y + 1) & 3) << 2) | (0x10 if sh else 0) | (0x20 if k & 1 else 0))
    return bytes(b) + b'\xff'

def levels_blob():
    """the 16 level blueprints (2305 bytes each) for RAM-disk page 5 at 0x4000 (game.asm RD_LV_ADDR)"""
    lvf = lambda n: os.path.join(A, 'level%02d.bin' % n)
    return b''.join((open(lvf(n), 'rb').read()[:2305] if os.path.exists(lvf(n)) else b'').ljust(2305, b'\0') for n in range(16))

def z80_guard(e, addr):
    """The guard trace line from guard.asm's G_SNAP, in kidsim's guard_line format."""
    g = e.mem(addr, 30)
    s8 = lambda v: v - 256 if v > 127 else v
    v = [g[0], g[1], g[2], s8(g[3]), s8(g[5]), s8(g[4]), g[6], s8(g[7]), s8(g[8]), g[9], g[14] | (g[15] << 8), s8(g[13]), g[12], g[11]] + list(g[16:30])
    return 'G ' + ' '.join(str(x) for x in v)

def z80_state_line(e):
    """The 'S' line from m4test's S_SNAP (kidsim trace_state_line order) and the level's tiles (the checksum)."""
    s = e.mem(S_SNAP, S_N)
    s8 = lambda v: v - 256 if v > 127 else v
    w = lambda i: s[i] | (s[i + 1] << 8)
    lv = e.mem(LEVEL_ADDR, 1440)
    cs = sum((lv[i] + 3 * lv[720 + i]) * (i % 7 + 1) for i in range(720))
    v = [s[0], s[1], s[2], w(3), s[5], w(6), w(8), s[10], 65535 if s[11] else 0, s[12], s[13], s8(s[14]), s[15], s[16],
         s[17], s[18], s[19], s[20], s[21], s8(s[22]), s[23], s[24], s[25], 65535 if s[26] == 0xFF else s[26], cs]
    return 'S ' + ' '.join(str(x) for x in v)

def z80_sound_line(e):
    """The 'N' line from m4test's N_SNAP (kidsim sound_line: ids 0xff = -1)."""
    q, st, p, x = e.mem(N_SNAP, 4)
    s8 = lambda v: v - 256 if v > 127 else v
    return 'N %d %d %d %d' % (s8(q), s8(st), p, x)

def norm(line):
    """alive: only its sign is compared (SDLPoP's death timer waits on sounds)"""
    return ' '.join(v if k != 12 else str(min(int(v), 0)) for k, v in enumerate(line.split()))

def setup(e, S, lv, o):
    """m4test with the RAM disk (levels, logic tables), the kid directory, the level number and the options"""
    e.run_mzf(os.path.join(ROOT, 'build', 'm4test.mzf'))
    write_pack(e, open(os.path.join(A, 'logic.bin'), 'rb').read(), 6, 0xD000)   # kid.asm RD_SEQ
    write_pack(e, levels_blob(), 5, 0x4000)
    e.call('mem_write', addr=DIR_KID, data_hex=open(os.path.join(A, 'kid.dir'), 'rb').read().hex())
    e.call('mem_write', addr=S['level_number'], data_hex='%02x' % lv)
    e.call('mem_write', addr=S['guard_opts'], data_hex=guard_opts_bytes(o).hex())
    e.call('mem_write', addr=S['ev_opts'], data_hex=ev_opts_bytes(o).hex())

TABLES_CHECKED = False
def main():
    scripts = sys.argv[1:] or (sorted(glob.glob(os.path.join(ROOT, 'tests', 'm4_scripts', '*.txt'))) +
                               sorted(glob.glob(os.path.join(ROOT, 'tests', 'm6_scripts', '*.txt'))) +
                               sorted(glob.glob(os.path.join(ROOT, 'tests', 'm5_scripts', '*.txt'))) +
                               sorted(glob.glob(os.path.join(ROOT, 'tests', 'm7_scripts', '*.txt'))))
    S = syms(os.path.join(ROOT, 'build', 'm4test.sym'))
    total_bad = 0
    with Emu() as e:
        for sp in scripts:
            moves, patches = kidsim.read_script(sp); keys = kidsim.read_keys(sp); lv = kidsim.script_level(sp)
            o = kidsim.script_opts(sp)
            sim = kidsim.KidSim(Level(lv), patches=patches, guards=o['guards'], place=o['place'], sword=o['sword'],
                                time=o['time'], multi_level=True, trace_state=True, start=o['start'],
                                sound=o['sound'], level1_music=o['level1_music'])
            sim.cheats = 'kl_cheat' in S        # (the cheat keys act in the CHEATS=1 build only, whatever the script says)
            exact = o['sound'] == 'ticks'
            setup(e, S, lv, o)
            e.call('mem_write', addr=S['SND_MODE'], data_hex='02' if exact else '00')
            e.call('mem_write', addr=SCRIPT, data_hex=encode(moves, keys).hex())
            e.call('bp_clear'); e.call('bp_add', addr=S['guards_off_chk'])
            r = e.run(200); assert r['stopped_by'] == 'breakpoint', (sp, r)      # the first control tick: the patches
            if exact:                                                            # (the level 1 crouch: game_init set it)
                e.call('mem_write', addr=S['NEED_L1M'], data_hex='%02x' % (1 if o['level1_music'] and lv == 1 else 0))
            global TABLES_CHECKED
            if not TABLES_CHECKED:
                t12, t10 = kidsim.KidSim.sound_ticks_tables(); got = e.mem(S['SND_T12'], 100)
                assert got == bytes(t12[:50] + t10[:50]), ('the Z80 ticks lengths differ from kidsim', got.hex())
                print('the Z80\'s ticks model lengths (SND_T12, SND_T10) equal kidsim\'s sound_ticks_tables')
                TABLES_CHECKED = True
            for (rm, p, t, m) in patches:                                        # (as SDLPoP's pop800_control hook)
                e.call('mem_write', addr=LEVEL_ADDR + (rm - 1) * 30 + p, data_hex='%02x' % t)
                e.call('mem_write', addr=LEVEL_ADDR + 720 + (rm - 1) * 30 + p, data_hex='%02x' % m)
            e.call('bp_clear'); e.call('bp_add', addr=S['tick_done'])
            bad = 0; first = None; dead_at = None; entered = False; gbad = sbad = 0; ticks = 0; marker = ''
            snaps = e.mem(S_SNAP + S_N, 1)[0]; nsnaps = e.mem(N_SNAP + 4, 1)[0]; nbad = 0
            for t, ((x, y, sh), k) in enumerate(zip(moves, keys)):
                ref = sim.step(x, y, sh, k)
                if ref is None and not sim.game_over: continue          # a restart tick: no lines, the Z80 runs on
                if ref is None:                                         # Ctrl+R: no lines, GAME_OVER at the tick's end
                    r = e.run(50); assert r['stopped_by'] == 'breakpoint', (sp, t, r)
                    go = GAME_OVER.get(e.mem(S['GAME_OVER'], 1)[0])
                    if go != sim.game_over:
                        bad += 1; first = first or (t, 'game over %s' % sim.game_over, 'game over %s' % go)
                    marker = ' ' + sim.game_over
                    break
                r = e.run(50); assert r['stopped_by'] == 'breakpoint', (sp, t, r)
                ticks += 1
                got = z80_state(e, int(ref.split()[0]))
                ok = ref == got if exact else norm(ref) == norm(got)
                if o['guards'] and sim.guard_line is not None:
                    gref = sim.guard_line; ggot = z80_guard(e, S['G_SNAP'])
                    entered = entered or gref.split()[4] != '86' or ggot.split()[4] != '86'
                    gok = gref == ggot if entered else gref.split()[15:] == ggot.split()[15:]
                    if not gok:
                        gbad += 1
                        ref += '\n   sim ' + gref; got += '\n   z80 ' + ggot
                    ok = ok and gok
                n = e.mem(S_SNAP + S_N, 1)[0]
                if sim.state_line is not None:
                    sref = sim.state_line; sgot = z80_state_line(e) if n != snaps else 'S (no snapshot)'
                    if sref != sgot:
                        sbad += 1
                        ref += '\n   sim ' + sref; got += '\n   z80 ' + sgot
                        ok = False
                elif n != snaps:
                    ok = False; ref += '\n   sim (no S line)'; got += '\n   z80 S snapshot taken'
                snaps = n
                n = e.mem(N_SNAP + 4, 1)[0]
                if sim.sound_line is not None:
                    nref = sim.sound_line; ngot = z80_sound_line(e) if n != nsnaps else 'N (no snapshot)'
                    if nref != ngot:
                        nbad += 1
                        ref += '\n   sim ' + nref; got += '\n   z80 ' + ngot
                        ok = False
                elif n != nsnaps:
                    ok = False; ref += '\n   sim (no N line)'; got += '\n   z80 N snapshot taken'
                nsnaps = n
                go = GAME_OVER.get(e.mem(S['GAME_OVER'], 1)[0])
                if go != sim.game_over and (go or sim.game_over in ('EXPIRED', 'END')):
                    ok = False; ref += '\n   sim game over %s' % sim.game_over; got += '\n   z80 game over %s' % go
                if not ok:
                    bad += 1
                    if first is None: first = (t, ref, got)
                if sim.game_over:
                    marker = ' ' + sim.game_over
                    break
                if dead_at is None and int(ref.split()[12]) >= 0: dead_at = ticks
                if dead_at is not None and ticks >= dead_at + 8 and not exact: break
            total_bad += bad
            print('%-28s %4d ticks, %d differing%s%s%s%s' % (os.path.basename(sp), t + 1, bad, ' [ticks]' if exact else '',
                  ' (guard lines: %d, state lines: %d, sound lines: %d)' % (gbad, sbad, nbad) if o['guards'] else
                  ' (state lines: %d, sound lines: %d)' % (sbad, nbad), marker,
                  '' if not bad else '; first at tick %d:\n   sim %s\n   z80 %s' % first), flush=True)
    print('total differing ticks:', total_bad)
    sys.exit(1 if total_bad else 0)

if __name__ == '__main__': main()
