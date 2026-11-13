#!/usr/bin/env python3
"""Duel phase 4 (docs/duel-design.md section 14): the duel over the network. Two emulators (mz800emu's Unicard in
MZPico mode: the NET device, [UNICARD] net_relay) meet through the reference relay, BomberNet's relay/relay.py, run
locally (its JSON-lines TCP server on a free port of 127.0.0.1; never the public relay). Each is the game with the duel
patch laid in as tests/duel_z80.py lays it, with the menu kept (duel.asm d_hnet = 1): A presses 2 (HOST), B 3 (JOIN),
types A's room code from the keyboard and ENTER; both play the same scripted duel, each machine its own player's byte
of the script (A player 1, B player 2) through the lockstep (duel.asm d_net: NETSEND tick + D, NETPOLL, NETHASH every
tick). Both machines' traces (the kid, G, N and D lines a tick: tests/duel_z80.py's) must equal duelsim's trace of the
script delayed by the input delay D (the first D ticks without keys, as the lockstep plays them). The script's random
arenas (docs/duel-design.md 15: default tests/duel_scripts/arenas_dungeon.txt, two matches on two levels, then
climb_dungeon.txt, a multi-row arena first, section 16) come from the
host's seed: A starts with the script's, B with another one, and B must take A's from the room's settings.

Then the failures, each with fresh machines: a joiner with another build id (OTHER VERSION, back to the menu), a
desync (a hashed byte changed on B: DESYNC on both, the title), the other machine gone (OTHER PLAYER LEFT), the other
machine silent (CONNECTION LOST after 10 s), no relay (NO LINK: the native emulator's NET device links only at the first
CREATE / JOIN, so the menu shows and HOST fails), a machine without the Unicard (POP800_UNICARD=0: no NET card, the
local duel at once, no menu), and a join that fails after it took the host's seed
(the host gone before the start: back to the menu) followed by HOST on that machine: the room must carry the seed its
arenas now use (a third machine joins, both play without a desync, as duelsim with that seed).

  POP800_RELAY_PY      the relay (default ~/src/bomberman/relay/relay.py: BomberNet's)
  POP800_RELAY_PYTHON  the Python that runs it (default this one; without fastapi a stand-in: only its TCP side runs)
usage: duel_net.py [--only match|version|desync|left|lost|nolink|rehost|nocard] [--realtime] [--delay N] [script.txt]
       (default tests/duel_scripts/arenas_dungeon.txt; --realtime and --delay: the speed at a real MZ-800's 50 Hz, docs/duel-design.md 14)"""
import os, socket, subprocess, sys, tempfile, threading, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools')); sys.path.insert(0, os.path.join(ROOT, 'tests'))
from m3_test import syms
from emu import Emu, Snap
import m4_game as G
import duelsim as DS
from duel_z80 import patch_in, kid_line, guard_line, duel_line, ranges, B

HOME = os.path.expanduser('~')
RELAY_PY = os.environ.get('POP800_RELAY_PY', os.path.join(HOME, 'src', 'bomberman', 'relay', 'relay.py'))
RELAY_PYTHON = os.environ.get('POP800_RELAY_PYTHON', sys.executable)
S = syms(os.path.join(B, 'm4game.sym')); D = syms(os.path.join(B, 'duel.sym'))
FAILS = []
REALTIME = False        # --realtime: both machines at a real MZ-800's 50 frames a second (the speed measurement)
DELAY = 0               # --delay N: the host's input delay (0: the build's, NET_DELAY)


def check(what, ok, detail=''):
    print('  %-74s %s%s' % (what, 'ok' if ok else 'FAILED', '' if ok else '  ' + str(detail)), flush=True)
    if not ok: FAILS.append(what)


def free_port():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); p = s.getsockname()[1]; s.close(); return p


class Relay:
    """relay.py's JSON-lines TCP server (the native emulator's transport) on 127.0.0.1:port, nothing else of it"""
    def __init__(self):
        self.port = free_port()
        code = ('import asyncio, sys, types\nsys.path.insert(0, %r)\n'
                'try:\n    import fastapi\n'                    # (only its WebSocket side needs it: a stand-in without)
                'except ImportError:\n'
                '    class App:\n'
                '        def __init__(self, *a, **k): pass\n'
                '        def on_event(self, *a): return lambda f: f\n'
                '        def websocket(self, *a): return lambda f: f\n'
                '    m = types.ModuleType("fastapi"); m.FastAPI = App; m.WebSocket = object\n'
                '    m.WebSocketDisconnect = type("WebSocketDisconnect", (Exception,), {}); sys.modules["fastapi"] = m\n'
                'import relay\n'
                'async def tcp(r, w):\n'                  # (the session's end closes the connection, as a WebSocket's
                '    try: await relay.tcp_client(r, w)\n'  # does: relay.py's TCP side leaves it open after a "leave",
                '    finally: w.close()\n'                 # and the device's next room would never be answered)
                'async def main():\n'
                '    s = await asyncio.start_server(tcp, "127.0.0.1", %d)\n'
                '    print("ready", flush=True)\n'
                '    await s.serve_forever()\n'
                'asyncio.run(main())\n') % (os.path.dirname(os.path.abspath(RELAY_PY)), self.port)
        self.log = tempfile.TemporaryFile(mode='w+')
        self.p = subprocess.Popen([RELAY_PYTHON, '-c', code], stdout=subprocess.PIPE, stderr=self.log, text=True)
        line = self.p.stdout.readline()
        if line.strip() != 'ready':
            self.log.seek(0); raise SystemExit('the relay did not start (%s %s): %s' % (RELAY_PYTHON, RELAY_PY, self.log.read()[-800:]))
    def close(self):
        self.p.terminate()
        try: self.p.wait(timeout=5)
        except Exception: self.p.kill()


class Machine:
    """one MZ-800: the game, the duel patch, the script (both players' bytes: each machine sends its own player's), the
    menu kept (d_hnet 1); its NET device on the relay's port (card False: a machine without the Unicard / MZPico,
    POP800_UNICARD=0)"""
    def __init__(self, name, port, script, seed=None, card=True):
        self.name = name
        os.environ['POP800_NET_RELAY'] = '127.0.0.1:%d' % port
        if card: os.environ.pop('POP800_UNICARD', None)
        else: os.environ['POP800_UNICARD'] = '0'
        try: self.e = Emu()
        finally: os.environ.pop('POP800_UNICARD', None)
        G.setup(self.e, DS.ARENA_LEVEL, fs_run=False)
        patch_in(self.e, S, D, script, seed)
        self.e.call('mem_write', addr=D['d_hnet'], data_hex='01')
    def run_to(self, addr, limit=600):
        e = self.e; e.call('bp_clear'); e.call('bp_add', addr=addr); n = 0
        while n < limit:
            r = e.run(min(100, limit - n)); n += r['actual_frames']
            if r['stopped_by'] == 'breakpoint': e.call('bp_clear'); return n
        raise AssertionError('%s: PC never reached %04X in %d frames (PC %04X)' % (self.name, addr, limit, e.call('get_registers')['PC']))
    def tap(self, key, frames=3):
        self.e.call('input_press_key', key=key); self.e.run(frames)
        self.e.call('input_release_key', key=key); self.e.run(frames)
    def mem(self, a, n): return self.e.mem(a, n)
    def poke(self, a, bs): self.e.call('mem_write', addr=a, data_hex=bytes(bs).hex())
    def close(self): self.e.close()


def both(fa, fb):
    """fa(), fb() at once (each machine in its own thread: the lockstep needs both running)"""
    out = [None, None]; err = []
    def run(i, f):
        try: out[i] = f()
        except BaseException as x: err.append(x)
    ts = [threading.Thread(target=run, args=(i, f)) for i, f in enumerate((fa, fb))]
    for t in ts: t.start()
    for t in ts: t.join()
    if err: raise err[0]
    return out


def menu(m):
    m.run_to(D['dlb_mk'], 1500)


def host(a):
    """A: the menu's 2 (HOST): the room's code (--delay: the host's input delay, d_ndelay and the room's settings[0])"""
    menu(a)
    if DELAY: a.poke(D['d_ndelay'], [DELAY]); a.poke(D['d_ncreate'] + 7, [DELAY])
    a.tap('2'); a.run_to(D['dlh_w'], 600)
    return a.mem(D['dst_code'] + 10, 4).decode()


def join(b, code):
    """B: the menu's 3 (JOIN), the code typed, ENTER (and a typo deleted first)"""
    menu(b); b.tap('3'); b.run_to(D['dlj_k'], 100)
    b.tap('X'); b.tap('DEL')
    for c in code: b.tap(c)
    typed = b.mem(D['dst_code'] + 10, 4).decode()
    b.tap('ENTER')
    return typed


class Trace:
    """the trace lines one machine plays (tests/duel_z80.py's tracepoints), its lobby texts and its end"""
    TEXTS = ('dst_desync', 'dst_left', 'dst_lost', 'dst_vers', 'dst_link', 'dst_room', 'dst_err', 'dst_wait')
    def __init__(self, m):
        self.m = m; e = m.e; self.R = ranges(S, D); self.at = {}
        e.call('bp_clear'); e.trace_clear()
        for k, a in (('mid', D['d_mid']), ('g', D['d_gline']), ('n', S['snd_snap']), ('end', D['d_tend']),
                     ('text', D['d_text']), ('quit', D['d_quit']), ('net', D['d_net']), ('tick', D['d_tick'])):
            e.trace_add(a, regs=('BC', 'DE') if k == 'n' else ('HL',) if k == 'text' else (), mem=self.R.get(k, [])); self.at[a] = k
        self.R['text'] = self.R['quit'] = self.R['net'] = self.R['tick'] = []
        inv = {D[k]: k for k in self.TEXTS}; self.inv = inv
        self.lines = []; self.tick = 0; self.stops = None; self.texts = []; self.quit = False; self.ends = []
        self.hash_ok = True; self.net_t = []; self._net = None; self.wait_at = self.lost_at = 0; self.t_next = None
        self.net_f = []
    def run(self, frames):
        """the emulator `frames` frames: at full speed (one frame is ~1 ms of wall time), or with --realtime one frame each
        20 ms of wall time (a real MZ-800's 50 Hz: the headless emulator's own normal speed is throttled far below it)"""
        if not REALTIME: return self.m.e.run(frames)
        if self.t_next is None: self.t_next = time.monotonic()
        for _ in range(frames):
            self.m.e.run(1); self.t_next += 0.02
            dt = self.t_next - time.monotonic()
            if dt > 0: time.sleep(dt)
            elif dt < -0.2: self.t_next = time.monotonic()        # (fallen behind: the host was busy)
        return True
    def step(self, frames=50):
        for rec in self.run(frames) and self.m.e.trace_read():
            k = self.at[rec['addr']]; m = Snap(self.R[k], rec) if self.R[k] else None
            if k == 'mid':
                self.tick += 1; self.lines.append(kid_line(m, S, self.tick - 1))
            elif k == 'g': self.lines.append(guard_line(m, S))
            elif k == 'n':
                st = m.mem(S['SND_STOPS'], 1)[0]; bc = rec['regs']['BC']; de = rec['regs']['DE']
                d = 0 if self.stops is None else (st - self.stops) & 0xFF; self.stops = st
                s8 = lambda v: v - 256 if v > 127 else v
                self.lines.append('N %d %d %d %d' % (s8(bc & 0xFF), s8(bc >> 8), de & 0xFF, d))
            elif k == 'end':
                self.ends.append(rec['frame'])
                line, ok = duel_line(m, S, D, self.tick); self.hash_ok &= ok
                n_line = self.lines.pop(); self.lines.append(line); self.lines.append(n_line)
            elif k == 'text':
                t = self.inv.get(rec['regs']['HL'])
                if t: self.texts.append((self.tick, t))
                if t == 'dst_lost': self.lost_at = rec['frame']
            elif k == 'net': self._net = rec['cycles']; self.wait_at = rec['frame']
            elif k == 'quit': self.quit = True
            elif k == 'tick' and self._net is not None:
                self.net_t.append(rec['cycles'] - self._net); self.net_f.append(rec['frame'] - self.wait_at); self._net = None
    def errors(self):
        """the texts shown but WAITING (which the emulators running at full speed show often: a wait of 25 of their
        frames is a few ms of the other's)"""
        return [x[1] for x in self.texts if x[1] != 'dst_wait']
    def until(self, cond, limit):
        n = 0
        while not cond() and n < limit: self.step(); n += 50
        return cond()


def ref_lines(path, delay):
    """duelsim's trace of the script with its first `delay` ticks without keys (the lockstep's start)"""
    inputs, opts = DS.read_duel_script(path)
    with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False) as f:
        f.write('# duel\n# p2 frames %s\n' % opts['p2_frames'] + ('# seed %d\n' % opts['seed'] if opts['seed'] is not None else ''))
        for a, b in [(0, 0)] * delay + inputs: f.write('0x%02x 0x%02x\n' % (a, b))
    lines, sim = DS.run_duel(f.name); os.unlink(f.name)
    return lines, inputs


def pair(relay, path):
    inputs, opts = DS.read_duel_script(path)
    script = b''.join(bytes(p) for p in inputs) + bytes(1024)     # (past the script's end: no keys)
    seed = opts['seed']                                         # (B's own seed another: it must take A's)
    a = Machine('A', relay.port, script, seed)
    try: return a, Machine('B', relay.port, script, None if seed is None else seed ^ 0x5A5A)
    except BaseException: a.close(); raise


def start(a, b):
    """host, join, both into the match; -> the room's code"""
    code = host(a)
    typed = join(b, code)
    check('A hosts: a room code of 4 letters (%s); B types it (DEL, letters, ENTER)' % code,
          len(code) == 4 and code.isalpha() and typed == code, (code, typed))
    b.run_to(D['dlr_w'], 300)                   # B ready, waiting for the start
    return code


def test_match(relay, path):
    print('1. a scripted duel over the relay: %s' % os.path.basename(path))
    a, b = pair(relay, path)
    try:
        start(a, b)
        delay = a.mem(D['d_ndelay'], 1)[0]
        check('B has the host\'s delay (%d) and slot 1, A slot 0' % delay,
              b.mem(D['d_ndelay'], 1)[0] == delay and a.mem(D['d_netm'], 1)[0] == 1 and b.mem(D['d_netm'], 1)[0] == 2)
        sa, sb = a.mem(D['d_seed'], 2), b.mem(D['d_seed'], 2)
        check('B has the host\'s seed for the arenas (%s; its own was another)' % sa[::-1].hex(), sa == sb, (sa.hex(), sb.hex()))
        ref, inputs = ref_lines(path, delay)
        want = sum(1 for l in ref if l.startswith('D ')) - 1
        ta, tb = Trace(a), Trace(b)
        t0 = time.time()
        both(lambda: ta.until(lambda: ta.tick >= want and ta.ends and len(ta.ends) >= want, 60 * want + 2000),
             lambda: tb.until(lambda: tb.tick >= want and tb.ends and len(tb.ends) >= want, 60 * want + 2000))
        quits = ref[-2].split()[9] == str(DS.MATCH_QUIT)       # (the script ends in a quit: both machines leave)
        if quits: both(lambda: ta.until(lambda: ta.quit, 200), lambda: tb.until(lambda: tb.quit, 200))
        wall = time.time() - t0
        for name, t in (('A', ta), ('B', tb)):
            refl = ref[1:]; got = t.lines[:len(refl)]          # (the D 0 line: the state before the first tick)
            n = min(len(refl), len(got)); bad = sum(1 for i in range(n) if refl[i] != got[i]) + abs(len(refl) - len(got))
            first = next(((i, refl[i], got[i]) for i in range(n) if refl[i] != got[i]), None)
            check('%s: %d ticks, %d differing lines against duelsim (delayed %d)%s' % (name, t.tick, bad, delay,
                  '' if not first else '; first at %d:\n     sim %s\n     z80 %s' % first), bad == 0)
            check('%s: its own hash equals the hash of its state, every tick' % name, t.hash_ok)
            check('%s: no error text%s' % (name, '; the quit at the script\'s end: back to the title (d_quit)' if quits else ''),
                  t.quit == quits and not t.errors(), t.errors())
            nt = sorted(t.net_t)
            if nt:
                quick = [x for x in nt if x < 10000]
                print('     %s: the network a tick (d_net): %d-%d T without a wait (%.3f frames); %d of %d ticks waited (the '
                      'emulators at full speed: a few ms of the other\'s is many frames); %.2f frames a tick in all' % (
                      name, quick[0], quick[-1], quick[-1] / 71136, len(nt) - len(quick), len(nt),
                      (t.ends[-1] - t.ends[2]) / (len(t.ends) - 3)))
                print('     %s: frames waited in d_net a tick: mean %.2f, %d ticks over 1 frame' % (
                      name, sum(t.net_f) / len(t.net_f), sum(1 for x in t.net_f if x > 1)))
        print('     %d ticks in %.1f s of wall time' % (want, wall))
    finally:
        a.close(); b.close()


def test_version(relay, path):
    print('2. a joiner with another build id')
    a, b = pair(relay, path)
    try:
        menu(b); bid = b.mem(D['d_build'], 2); b.poke(D['d_build'], [bid[0] ^ 0x55, bid[1]])
        code = host(a)
        tb = Trace(b)
        b.tap('3');
        for c in code: b.tap(c)
        b.tap('ENTER')
        tb.until(lambda: tb.texts, 300)
        check('B: OTHER VERSION', tb.texts[:1] == [(0, 'dst_vers')], tb.texts)
        b.e.trace_clear(); b.run_to(D['dlb_mk'], 300)
        check('B: back to the menu', True)
    finally:
        a.close(); b.close()


def in_match(relay, path, ticks=20):
    a, b = pair(relay, path)
    try:
        start(a, b)
        ta, tb = Trace(a), Trace(b)
        both(lambda: ta.until(lambda: ta.tick >= ticks, 2000), lambda: tb.until(lambda: tb.tick >= ticks, 2000))
    except BaseException:
        a.close(); b.close(); raise
    return a, b, ta, tb


def test_desync(relay, path):
    print('3. a desync: a hashed byte changed on B')
    a, b, ta, tb = in_match(relay, path)
    try:
        x = b.mem(S['KID_REC'] + 1, 1)[0]; b.poke(S['KID_REC'] + 1, [x ^ 4])      # (the kid's x on B only)
        both(lambda: ta.until(lambda: ta.quit, 1500), lambda: tb.until(lambda: tb.quit, 1500))
        for name, t in (('A', ta), ('B', tb)):
            check('%s: DESYNC, then the title' % name, t.quit and t.errors() == ['dst_desync'], t.texts)
    finally:
        a.close(); b.close()


def test_left(relay, path):
    print('4. the other machine gone')
    a, b, ta, tb = in_match(relay, path)
    try:
        b.close(); time.sleep(0.3)
        ta.until(lambda: ta.quit, 1500)
        check('A: OTHER PLAYER LEFT, then the title', ta.quit and ta.errors() == ['dst_left'], ta.texts)
    finally:
        a.close()


def test_lost(relay, path):
    print('5. the other machine silent')
    a, b, ta, tb = in_match(relay, path)
    try:
        ta.until(lambda: ta.quit, 1500)
        check('A: WAITING, then CONNECTION LOST after 10 s (%d frames), then the title' % (ta.lost_at - ta.wait_at),
              ta.quit and ta.errors() == ['dst_lost'] and ta.tick <= tb.tick + 2 and 495 <= ta.lost_at - ta.wait_at < 530, ta.texts)
    finally:
        a.close(); b.close()


def test_nolink(path):
    print('6. no relay')
    inputs, opts = DS.read_duel_script(path)
    m = Machine('A', free_port(), b''.join(bytes(p) for p in inputs), opts['seed'])
    try:
        menu(m); t = Trace(m); m.tap('2'); t.until(lambda: t.texts, 300)
        check('HOST without a relay: NO LINK', [x[1] for x in t.texts][:1] == ['dst_link'], t.texts)
        m.e.trace_clear(); m.run_to(D['dlb_mk'], 300); check('back to the menu', True)
        m.tap('1'); m.run_to(D['d_tend'], 100)
        check('then 1 (LOCAL): the local match runs', m.mem(D['d_netm'], 1)[0] == 0)
    finally:
        m.close()


def test_nocard(path):
    print('8. no network card (the emulator without the Unicard): the local duel at once, no menu')
    inputs, opts = DS.read_duel_script(path)
    m = Machine('A', free_port(), b''.join(bytes(p) for p in inputs), opts['seed'], card=False)
    try:
        e = m.e; e.call('bp_clear')
        for a in (D['dlb_mk'], D['d_draw'], D['d_ready']): e.call('bp_add', addr=a)
        n = 0
        while n < 1500:
            r = e.run(100); n += r['actual_frames']
            if r['stopped_by'] == 'breakpoint': break
        e.call('bp_clear'); pc = e.call('get_registers')['PC']
        check('straight into the match (d_ready; no menu, no arena drawn before it)', pc == D['d_ready'], '%04X' % pc)
        m.run_to(D['d_tend'], 300)
        check('the local match runs (d_netm 0)', m.mem(D['d_netm'], 1)[0] == 0)
    finally:
        m.close()


def test_rehost(relay, path, ticks=40):
    print('7. a join that fails after it took the host\'s seed, then HOST on the same machine')
    a, b = pair(relay, path)
    c = None
    try:
        start(a, b)
        sa = a.mem(D['d_seed'], 2)
        check('B took A\'s seed (%s)' % sa[::-1].hex(), b.mem(D['d_seed'], 2) == sa)
        a.close(); a = None                         # (A gone before the match starts: the room dropped)
        b.run_to(D['dlb_mk'], 1500)
        check('B: back to the menu, A\'s seed kept', b.mem(D['d_seed'], 2) == sa)
        inputs, opts = DS.read_duel_script(path)
        c = Machine('C', relay.port, b''.join(bytes(p) for p in inputs) + bytes(1024), 0x1111)
        # (the relay ends a session at its "leave", the emulator's NET device keeps the closed socket: its next CREATE
        # waits for the 1,024-frame timeout, NO LINK, back to the menu; the second HOST connects anew)
        tries = []
        for _ in range(2):
            b.run_to(D['dlb_mk'], 300); b.tap('2')
            e = b.e; e.call('bp_clear'); e.call('bp_add', addr=D['dlh_w']); e.call('bp_add', addr=D['dlb_e'])
            n = 0
            while n < 1500:
                r = e.run(100); n += r['actual_frames']
                if r['stopped_by'] == 'breakpoint': break
            e.call('bp_clear'); pc = e.call('get_registers')['PC']
            tries.append('the room' if pc == D['dlh_w'] else 'an error text (%04X)' % pc)
            if pc == D['dlh_w']: break
        code = b.mem(D['dst_code'] + 10, 4).decode()
        print('     B\'s HOST attempts: %s' % ', '.join(tries))
        check('B hosts again: its room carries the seed its arenas use',
              b.mem(D['d_ncreate'] + 8, 2) == sa, b.mem(D['d_ncreate'] + 8, 2).hex())
        typed = join(c, code); c.run_to(D['dlr_w'], 300)
        check('C joins (%s) and takes B\'s seed' % typed, c.mem(D['d_seed'], 2) == sa, c.mem(D['d_seed'], 2).hex())
        delay = b.mem(D['d_ndelay'], 1)[0]
        ref, _ = ref_lines(path, delay)
        tb, tc = Trace(b), Trace(c)
        both(lambda: tb.until(lambda: tb.tick > ticks, 60 * ticks + 2000),
             lambda: tc.until(lambda: tc.tick > ticks, 60 * ticks + 2000))
        n = 4 * ticks; refl = ref[1:1 + n]
        for name, t in (('B', tb), ('C', tc)):
            got = t.lines[:n]
            bad = sum(1 for x, y in zip(refl, got) if x != y) + abs(len(refl) - len(got))
            check('%s: %d ticks as duelsim with that seed, no desync' % (name, ticks), bad == 0 and not t.errors(),
                  (bad, t.errors()))
    finally:
        for m in (a, b, c):
            if m: m.close()


def main():
    global REALTIME, DELAY
    args = sys.argv[1:]; only = None
    if '--realtime' in args: args.remove('--realtime'); REALTIME = True
    if '--delay' in args: i = args.index('--delay'); DELAY = int(args[i + 1]); del args[i:i + 2]
    if '--only' in args: i = args.index('--only'); only = args[i + 1]; del args[i:i + 2]
    path = args[0] if args else os.path.join(ROOT, 'tests', 'duel_scripts', 'arenas_dungeon.txt')
    climb = [] if args else [os.path.join(ROOT, 'tests', 'duel_scripts', 'climb_dungeon.txt')]   # (a multi-row arena)
    relay = Relay()
    try:
        for name, f in (('match', lambda: [test_match(relay, q) for q in [path] + climb]),
                        ('version', lambda: test_version(relay, path)),
                        ('desync', lambda: test_desync(relay, path)), ('left', lambda: test_left(relay, path)),
                        ('lost', lambda: test_lost(relay, path)), ('nolink', lambda: test_nolink(path)),
                        ('rehost', lambda: test_rehost(relay, path)), ('nocard', lambda: test_nocard(path))):
            if only not in (None, name): continue
            try: f()
            except Exception as x:                      # (a scenario that broke: a failed check, the others still run)
                import traceback; traceback.print_exc()
                check('%s: ran to its end' % name, False, '%s: %s' % (type(x).__name__, x))
    finally:
        relay.close()
    print('FAILED: %s' % ', '.join(FAILS) if FAILS else 'all ok')
    sys.exit(1 if FAILS else 0)


if __name__ == '__main__':
    main()
