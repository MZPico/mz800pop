#!/usr/bin/env python3
"""Minimal JSONL client for `mz800emu --mcp-pipe` (same wire protocol the MCP wrapper uses).

    from emu import Emu
    with Emu() as e:
        e.run_mzf('build/colorbars.mzf'); e.run(50); e.screenshot('out.png')

Non-stopping tracing (mz800emu trace_add / trace_read / psg_log_* / vram_hash): `e.tracing` is true when the emulator
has the commands and POP800_EMU_TRACE is not 0 (POP800_EMU_TRACE=0 makes the tests take their old breakpoint paths,
to compare the two). A tracepoint records the requested registers / memory / VRAM hash every time the instruction at
its address is about to execute, without stopping; `collect` runs the emulation and returns the records as they come.

CLI: emu.py <file.mzf> <frames> <out.png>
"""
import base64, collections, json, os, struct, subprocess, sys, zlib
EXE = os.environ.get('MZ800EMU_EXE', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'emu', 'mz800emu-pop.sh'))

# the MZ-800 IGRB colours (vram_image's palette)
PALETTE = [0,0,0,0x40,0x40,0xAC,0xD0,0x34,0,0xB4,0x0C,0x8C,0x40,0x6C,0,0x24,0xCC,0xFF,0xE8,0xD4,0x30,0xD0,0xD0,0xD0,
           0x84,0x84,0x84,0,0x8C,0xE8,0xFF,0,0,0xF0,0x54,0xCC,0x54,0xFF,0x54,0x80,0xFF,0xFF,0xFF,0xFF,0x28,0xFF,0xFF,0xFF]

def image_planes(im):
    """the four 8000-byte VRAM planes (I, II, III, IV) of a 320x200 image of colour numbers 0-15 (bit 0 of a byte =
    its leftmost pixel; plane k holds bit k of the colour), as the Z80 leaves them for that picture"""
    import numpy as np
    a = np.frombuffer(im.tobytes(), np.uint8).reshape(200, 40, 8)
    return [np.packbits((a >> k) & 1, axis=2, bitorder='little').tobytes() for k in range(4)]

def planes_crc(planes):
    """mz800emu vram_hash: zlib's CRC-32 of each plane"""
    return tuple(zlib.crc32(p) for p in planes)

class Emu:
    def __init__(self, exe=EXE):
        self.p = subprocess.Popen([exe, '--mcp-pipe'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.n = 0
        self.hello = self._read()           # first JSON line = hello
        self.commands = set(self.hello.get('commands', []))
        import time
        for _ in range(50):                 # wait until the emulator core answers
            try:
                self.call('ping'); self.call('run', frames=1); break
            except RuntimeError:
                time.sleep(0.2)
        else:
            raise RuntimeError('emulator did not become ready')
        # headless pipe mode is throttled to ~1 frame/s at 'normal' speed (audio sync);
        # warp mode runs frame-exact and fast, which is what a test harness wants.
        self.call('set_speed', mode='max')
        self.call('bp_clear')   # the emulator persists breakpoints across sessions (mz800-breakpoints.bpt)
    def _read(self):
        while True:
            line = self.p.stdout.readline()
            if not line: raise RuntimeError('emulator closed the pipe')
            line = line.strip()
            if line.startswith('{'):
                try: return json.loads(line)
                except json.JSONDecodeError: pass
    def call(self, cmd, **data):
        self.n += 1
        req = {'req_id': self.n, 'cmd': cmd}
        if data: req['data'] = data
        self.p.stdin.write(json.dumps(req) + '\n'); self.p.stdin.flush()
        while True:
            r = self._read()
            if r.get('req_id') == self.n: break
        if not r.get('success', True) or 'error' in r:
            raise RuntimeError('%s failed: %s' % (cmd, r))
        return r.get('data', r)
    # helpers
    def run(self, frames): return self.call('run', frames=frames)
    # ---- non-stopping tracing
    @property
    def tracing(self):
        return 'trace_add' in self.commands and os.environ.get('POP800_EMU_TRACE', '1') != '0'
    def trace_add(self, addr, regs=(), mem=(), vram_hash=False):
        """a tracepoint at addr: each record has 'regs' {name: value} (names as get_registers), 'mem' [bytes per
        (addr, len) range], 'vram' (the four planes' CRC-32s, planes_crc) with vram_hash, and 'addr', 'cycles' (the CPU's
        total_cycles, as get_raster_pos), 'ticks' (GDG clock, 5 per T-state), 'frame'. Returns its id."""
        return self.call('trace_add', addr=addr, regs=list(regs), mem=[list(m) for m in mem], vram_hash=bool(vram_hash))['id']
    def trace_clear(self, id=None):
        return self.call('trace_clear', **({'id': id} if id else {}))['cleared']
    def trace_read(self):
        """all buffered records (oldest first); a lost record is an error"""
        out = []
        while True:
            d = self.call('trace_read', max=20000)
            if d['overflow'] or d['dropped']: raise RuntimeError('trace buffer overflow: %d records lost' % d['dropped'])
            for r in d['records']:
                r['mem'] = [bytes.fromhex(h) for h in r.get('mem', ())]
                if 'vram_crc32' in r: r['vram'] = tuple(r.pop('vram_crc32'))
                out.append(r)
            if not d['pending']: return out
    def collect(self, frames=200, stop=None):
        """run the emulation in steps of `frames` frames, yielding the tracepoint records as they come, until the
        generator is closed or stop(record) is true for a record (the run stops at the end of that step). A breakpoint
        stop ends the step early (yields its records, then the generator returns: the caller handles the breakpoint)."""
        while True:
            r = self.run(frames)
            recs = self.trace_read()
            for x in recs:
                yield x
                if stop and stop(x): return
            if r['stopped_by'] == 'breakpoint': return
    def psg_log_start(self): return self.call('psg_log_start')
    def psg_log_stop(self): return self.call('psg_log_stop')
    def psg_log_read(self):
        """all logged PSG writes [(ticks, cycles, frame, value, channel)], oldest first; a lost write is an error"""
        out = []
        while True:
            d = self.call('psg_log_read', max=200000)
            if d['overflow'] or d['dropped']: raise RuntimeError('PSG log overflow: %d writes lost' % d['dropped'])
            out += [tuple(w) for w in d['writes']]
            if not d['pending']: return out
    def vram_hash(self):
        """the CRC-32s of the four 8000-byte planes (I, II, III, IV), as planes_crc computes them"""
        return tuple(self.call('vram_hash')['crc32'])
    def mem(self, addr, n): return base64.b64decode(self.call('mem_read', addr=addr, len=n)['data_b64'])
    def run_mzf(self, path):
        hdr = open(path, 'rb').read(128); exec_ = struct.unpack_from('<H', hdr, 0x16)[0]
        self.run(3)  # let the ROM initialise before the CMT hack
        self.call('media_load_mzf', path=os.path.abspath(path))
        for port in (0xE0, 0xE1): self.call('io_write', port=port, value=0)
        b2 = os.path.splitext(path)[0] + '.b2'          # second block (0xC000+), see tools/mkmzf.py
        if os.path.exists(b2):
            data = open(b2, 'rb').read(); addr = struct.unpack_from('<H', data, 0)[0]; data = data[2:]
            for off in range(0, len(data), 4096):
                self.call('mem_write', addr=addr + off, data_hex=data[off:off+4096].hex())
        self.call('set_register', reg='PC', value=exec_)
    def region(self, region_id, offset=0, length=8000):
        return base64.b64decode(self.call('region_read', region_id=region_id, offset=offset, length=length)['data_b64'])
    def vram_planes(self):
        """Return the four 8000-byte planes (I,II,III,IV) of the 320x200 modes."""
        return [self.region(i) for i in (8, 9, 10, 11)]
    def vram_image(self, out=None, planes=None):
        """Decode the planes to an indexed 320x200 PIL image (MZ IGRB colours)."""
        from PIL import Image
        pl = planes or self.vram_planes(); im = Image.new('P', (320, 200)); px = im.load()
        for y in range(200):
            for xb in range(40):
                b = [p[y*40+xb] for p in pl]
                for bit in range(8):
                    m = 1 << bit          # MZ-800: bit 0 = leftmost pixel
                    px[xb*8+bit, y] = (1 if b[0]&m else 0)|(2 if b[1]&m else 0)|(4 if b[2]&m else 0)|(8 if b[3]&m else 0)
        im.putpalette(PALETTE + [0]*(768-48))
        if out: im.save(out)
        return im
    def screenshot(self, out):
        for _ in range(5):
            try: d = self.call('get_frame_screenshot_raw'); break
            except RuntimeError: self.run(1)
        else: raise
        from PIL import Image
        raw = base64.b64decode(d['data_b64'])
        Image.frombytes('RGBA', (d['width'], d['height']), raw).save(out); return d
    def close(self):
        try: self.call('bp_clear')
        except Exception: pass
        try: self.call('shutdown')
        except Exception: pass
        try: self.p.wait(timeout=5)
        except Exception: self.p.kill()
    def __enter__(self): return self
    def __exit__(self, *a): self.close()

class Snap:
    """the memory a tracepoint record captured: mem(addr, n) as Emu.mem, from the record's ranges only (a read outside
    them is an error, never a read of the live memory)"""
    def __init__(self, ranges, rec):
        self.rec = rec; self.parts = list(zip(ranges, rec['mem']))
    def mem(self, addr, n):
        for (a, l), d in self.parts:
            if a <= addr and addr + n <= a + l: return d[addr - a:addr - a + n]
        raise KeyError('not captured by the tracepoint: 0x%04x+%d' % (addr, n))

class Hits:
    """the machine at each execution of an address, for a loop that reads memory there (e.g. every tick's end).
    next() returns an object with mem(addr, n): with tracing a Snap of the ranges a tracepoint captured (the emulation
    runs on in steps, no stops), else the Emu itself stopped at a breakpoint there (the old way). Either way a hit must
    come within `limit` frames of the previous one (the breakpoint way: run(limit) must stop at the breakpoint).
    close() ends at a hit (a breakpoint stop), as the breakpoint way leaves the emulator. fast: tracing or not (default
    e.tracing)."""
    def __init__(self, e, addr, ranges, limit, vram_hash=False, fast=None):
        self.e, self.addr, self.ranges, self.limit = e, addr, list(ranges), limit
        self.fast = e.tracing if fast is None else fast; self.buf = collections.deque(); self.last = None
        e.call('bp_clear')
        if self.fast:
            self.prev = e.call('get_raster_pos')['frame_number']
            e.trace_add(addr, mem=self.ranges, vram_hash=vram_hash)
        else:
            e.call('bp_add', addr=addr)
    def next(self, what=()):
        e = self.e
        if not self.fast:
            r = e.run(self.limit); assert r['stopped_by'] == 'breakpoint', tuple(what) + (r,)
            return e
        while not self.buf:
            e.run(200); self.buf.extend(e.trace_read())
            if not self.buf:
                f = e.call('get_raster_pos')['frame_number']
                assert f - self.prev < self.limit, tuple(what) + ('no hit at 0x%04x within %d frames' % (self.addr, self.limit),)
        r = self.buf.popleft()
        assert r['frame'] - self.prev < self.limit, tuple(what) + ('no hit at 0x%04x within %d frames' % (self.addr, self.limit), r)
        self.prev = r['frame']; self.last = r
        return Snap(self.ranges, r)
    def close(self):
        if self.fast:
            self.e.trace_clear(); self.e.call('bp_add', addr=self.addr); self.e.run(self.limit)

if __name__ == '__main__':
    mzf, frames, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    with Emu() as e:
        print('hello:', e.hello.get('type'), len(e.commands), 'commands')
        e.run_mzf(mzf); print('run', e.run(frames))
        print('screenshot', {k: v for k, v in e.screenshot(out).items() if k != 'data_b64'})
        print('frame counter @1FFE =', e.mem(0x1FFE, 1)[0])
