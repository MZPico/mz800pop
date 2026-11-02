#!/usr/bin/env python3
"""M3 camera demo driver. Headless: loads a level into the demo program, walks a few rooms with the joystick,
records one screenshot per game tick and writes build/m3_demo.gif. With --gui it launches the emulator
window instead (MCP over TCP), sets everything up and leaves it running for you to drive with the cursor keys
or joystick 1 (NUM_KEYPAD). usage: m3_demo.py [level] [--gui] [--ticks N]"""
import json, os, socket, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m3_test import *
TICKS = 0x0872; CUR_ROOM = 0x0871

class TcpEmu(Emu):
    """Emu over the emulator's MCP TCP listener (GUI build): same JSONL protocol."""
    def __init__(self, port):
        self.n = 0
        for _ in range(100):
            try: self.s = socket.create_connection(('127.0.0.1', port)); break
            except OSError: time.sleep(0.2)
        else: raise RuntimeError('no emulator on port %d' % port)
        self.f = self.s.makefile('rw')
        self.hello = self._read(); self.commands = set(self.hello.get('commands', []))
        for _ in range(50):
            try: self.call('ping'); break
            except RuntimeError: time.sleep(0.2)
    def _read(self):
        while True:
            line = self.f.readline()
            if not line: raise RuntimeError('emulator closed the connection')
            line = line.strip()
            if line.startswith('{'):
                try: return json.loads(line)
                except json.JSONDecodeError: pass
    def call(self, cmd, **data):
        self.n += 1
        req = {'req_id': self.n, 'cmd': cmd}
        if data: req['data'] = data
        self.f.write(json.dumps(req) + '\n'); self.f.flush()
        while True:
            r = self._read()
            if r.get('req_id') == self.n: break
        if not r.get('success', True) or 'error' in r: raise RuntimeError('%s failed: %s' % (cmd, r))
        return r.get('data', r)
    def close(self):
        try: self.s.close()
        except Exception: pass

def setup(e, level):
    e.run_mzf(os.path.join(ROOT, 'build', 'm3demo.mzf'))
    load_assets(e, level.type)
    e.call('mem_write', addr=LEVEL_ADDR, data_hex=level.raw.hex())
    e.call('mem_write', addr=LEVEL_TYPE, data_hex='%02x' % level.type)

def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    lv = int(args[0]) if args else 1
    level = Level(lv)
    gui = '--gui' in sys.argv
    ticks = int(sys.argv[sys.argv.index('--ticks') + 1]) if '--ticks' in sys.argv else 60
    if gui:
        import subprocess
        port = 5656
        p = subprocess.Popen([EXE_GUI, '--mcp-tcp-port', str(port), '--no-first-run-windows'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        e = TcpEmu(port)
        e.call('run', frames=3)             # 'run' with a frame count pauses the GUI emulator afterwards
        setup(e, level)
        e.call('set_speed', mode='normal')
        e.call('run')                        # resume free running
        print('demo running in the emulator window (level %d); cursor keys / joystick 1 change rooms. Ctrl+C here does not stop the emulator.' % lv)
        e.close(); return
    frames = []
    with Emu() as e:
        setup(e, level)
        e.run(8)
        last = 0; moves = {15: 0x02, 30: 0x01, 45: 0x04}   # tick -> joystick state (down, up, left); b0 up b1 down b2 left b3 right
        t = 0; n = 0
        while n < ticks:
            e.run(4)
            tk = int.from_bytes(e.mem(TICKS, 2), 'little')
            if tk == last or tk == 0: continue
            last = tk; n += 1
            if n in moves: e.call('input_send_joystick', port=0, state=moves[n], frames=6)
            im = e.vram_image().convert('RGB'); frames.append(im)
            room = e.mem(CUR_ROOM, 1)[0]
            if n % 10 == 0: print('tick %d room %d' % (n, room))
    out = os.path.join(ROOT, 'build', 'm3_demo.gif')
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=80, loop=0)
    print('wrote', out, len(frames), 'ticks')

EXE_GUI = os.environ.get('MZ800EMU_EXE', os.path.join(ROOT, 'emu', 'mz800emu-pop.sh'))
if __name__ == '__main__': main()
