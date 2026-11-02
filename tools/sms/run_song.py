#!/usr/bin/env python3
"""Log the Sega Master System Prince of Persia (E) sound driver's PSG writes with MAME (0.264, driver smspal).

The ROM (the user's, outside the project, never copied) runs headless in MAME with a Lua autoboot script
(tools/sms/songlog.lua) that taps the Z80 I/O writes to 0x40-0x7F (the SN76489) and logs them per frame, starting
one piece by redirecting the game's per-frame driver call (see the Lua script). MAME's smspal needs a BIOS image:
this writes a 128 KB stub of our own (not Sega's: `di; copy "ld a,A8h; out (3Eh),a; jp 0" to RAM; run it` = enable
the cartridge, start it) under the expected file name; MAME warns about the checksum and runs.
MAME must not see WSLg's X/Wayland/Pulse/D-Bus sockets (it blocks on them under load): the environment is stripped
and SDL's dummy drivers used.

usage: run_song.py --rom pop_e.sms --work DIR music 1 6000        -> DIR/logs/music_1.log (6000 frames logged)
       run_song.py --rom pop_e.sms --work DIR sfx 20 600
The driver's song numbers: music 1 3 5 7 8 10 11 14 15 16, sfx 17-34 (tools/vgm2psg.py converts the logs)."""
import argparse, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))

STUB = bytes([0x3E, 0xA8, 0xD3, 0x3E, 0xC3, 0x00, 0x00])             # ld a,A8h; out (3Eh),a; jp 0000h
BOOT = bytes([0xF3, 0x21, 0x20, 0x00, 0x11, 0x00, 0xC0, 0x01, len(STUB), 0x00, 0xED, 0xB0, 0xC3, 0x00, 0xC0])

def stub_bios(romdir):
    d = os.path.join(romdir, 'smspal'); os.makedirs(d, exist_ok=True)
    p = os.path.join(d, 'mpr-12808.ic2')
    if not os.path.exists(p):
        img = bytearray(b'\xff' * 131072); img[0:len(BOOT)] = BOOT; img[0x20:0x20 + len(STUB)] = STUB
        open(p, 'wb').write(img)
    return romdir

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True); ap.add_argument('--work', required=True)
    ap.add_argument('--start', type=int, default=400, help='the frame the piece is started at (the title is up)')
    ap.add_argument('kind', choices=('music', 'sfx')); ap.add_argument('n', type=int); ap.add_argument('frames', type=int)
    a = ap.parse_args()
    logs = os.path.join(a.work, 'logs'); os.makedirs(logs, exist_ok=True)
    rompath = stub_bios(os.path.join(a.work, 'mame-roms'))
    log = os.path.join(logs, '%s_%d.log' % (a.kind, a.n))
    env = {k: v for k, v in os.environ.items()
           if k not in ('DISPLAY', 'WAYLAND_DISPLAY', 'PULSE_SERVER', 'DBUS_SESSION_BUS_ADDRESS')}
    env.update(SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', PSGLOG=log, KIND=a.kind, SONG=str(a.n),
               MAXF=str(a.frames), START=str(a.start))
    # (MAME is run with the work dir as cwd and its output piped: with a fresh temp dir as cwd and stdout redirected
    # to a file it was seen to hang at startup under load)
    d = os.path.join(a.work, 'mame-state'); os.makedirs(d, exist_ok=True)
    cmd = ['mame', 'smspal', '-bios', 'alexkidd', '-rompath', rompath, '-cart', os.path.abspath(a.rom),
           '-nothrottle', '-video', 'none', '-sound', 'none', '-seconds_to_run', str((a.frames + a.start + 200) // 50 + 5),
           '-autoboot_script', os.path.join(HERE, 'songlog.lua'), '-skip_gameinfo',
           '-nvram_directory', os.path.join(d, 'nvram_%s_%d' % (a.kind, a.n)), '-cfg_directory', os.path.join(d, 'cfg_%s_%d' % (a.kind, a.n))]
    r = subprocess.run(cmd, cwd=a.work, env=env, capture_output=True, text=True, timeout=900)
    bad = [l for l in r.stdout.splitlines() + r.stderr.splitlines() if 'error' in l.lower() and 'deprecated' not in l]
    if bad or r.returncode: print('\n'.join(bad) or r.stderr[-500:]); sys.exit(1)
    print(log, sum(1 for l in open(log) if l.startswith('w')), 'writes')

if __name__ == '__main__':
    main()
