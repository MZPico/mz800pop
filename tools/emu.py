#!/usr/bin/env python3
"""Minimal JSONL client for `mz800emu --mcp-pipe` (same wire protocol the MCP wrapper uses).

    from emu import Emu
    with Emu() as e:
        e.run_mzf('build/colorbars.mzf'); e.run(50); e.screenshot('out.png')

CLI: emu.py <file.mzf> <frames> <out.png>
"""
import base64, json, os, struct, subprocess, sys
EXE = os.environ.get('MZ800EMU_EXE', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'emu', 'mz800emu-pop.sh'))

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
    def vram_image(self, out=None):
        """Decode the planes to an indexed 320x200 PIL image (MZ IGRB colours)."""
        from PIL import Image
        pl = self.vram_planes(); im = Image.new('P', (320, 200)); px = im.load()
        for y in range(200):
            for xb in range(40):
                b = [p[y*40+xb] for p in pl]
                for bit in range(8):
                    m = 1 << bit          # MZ-800: bit 0 = leftmost pixel
                    px[xb*8+bit, y] = (1 if b[0]&m else 0)|(2 if b[1]&m else 0)|(4 if b[2]&m else 0)|(8 if b[3]&m else 0)
        pal=[0,0,0,0x40,0x40,0xAC,0xD0,0x34,0,0xB4,0x0C,0x8C,0x40,0x6C,0,0x24,0xCC,0xFF,0xE8,0xD4,0x30,0xD0,0xD0,0xD0,
             0x84,0x84,0x84,0,0x8C,0xE8,0xFF,0,0,0xF0,0x54,0xCC,0x54,0xFF,0x54,0x80,0xFF,0xFF,0xFF,0xFF,0x28,0xFF,0xFF,0xFF]
        im.putpalette(pal + [0]*(768-48))
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

if __name__ == '__main__':
    mzf, frames, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    with Emu() as e:
        print('hello:', e.hello.get('type'), len(e.commands), 'commands')
        e.run_mzf(mzf); print('run', e.run(frames))
        print('screenshot', {k: v for k, v in e.screenshot(out).items() if k != 'data_b64'})
        print('frame counter @1FFE =', e.mem(0x1FFE, 1)[0])
