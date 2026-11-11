# The duel over the network: two emulators and a local relay (Windows / WSL)

The duel (Ctrl+D on the title) plays over the MZPico NET service (docs/duel-design.md section 14). In the emulator
the NET device is mz800emu's Unicard in MZPico mode, which talks to a relay over TCP: BomberNet's `relay/relay.py`
(https://github.com/MZPico/BomberNet). The public relay at mzpico.com speaks WebSocket only, so the native emulator
cannot reach it: run relay.py yourself, on the same PC or on the LAN.

## 1. The relay (in WSL)

```sh
git clone https://github.com/MZPico/BomberNet ~/src/bomberman      # (once; or use your checkout)
cd ~/src/bomberman
python3 -m venv build/venv && build/venv/bin/pip install -r relay/requirements.txt    # (once)
build/venv/bin/uvicorn --app-dir relay relay:app --port 8765
```

It listens for the emulators on TCP **127.0.0.1:8766** (the WebSocket on 8765 is for browsers). For emulators on other
machines of the LAN, or a Windows-native emulator that does not see WSL's 127.0.0.1, start it with
`RELAY_TCP_HOST=0.0.0.0` and use the WSL machine's address below. `RELAY_TRACE=1` prints the rooms and players.

## 2. Two emulators

The emulator must be MZPico's mz800emu (https://github.com/MZPico/mz800emu, branch `wasm`) with the Unicard's NET
device (`src/emulator/hw-generic/unicard/unimgr_net.c`); the commit the tests use is CI's `MZ800EMU_COMMIT` in
`.github/workflows/pr-checks.yml` (b4ebc084d639 today). Use an existing build of it, or build it in WSL as CI does
(SDL3 and minizip-ng into ~/mzdeps, the emulator into ~/mz800emu-bin; the apt packages are the workflow's "Packages"
step):

```sh
export MZ800EMU_COMMIT=b4ebc084d639d360888d328d06e1b3bc49236c05
tools/ci/build_deps.sh sdl3 && tools/ci/build_deps.sh emu
export LD_LIBRARY_PATH=$HOME/mzdeps/lib MZ800EMU_BIN=$HOME/mz800emu-bin/mz800emu
```

`emu/mz800emu-pop.sh` runs `$MZ800EMU_BIN` (without it, the author's local build path): set it in both terminals.

Each needs, in its INI (pop-800's `emu/mz800emu.ini` has it):

```ini
[UNICARD]
connected = 1
mzpico_mode = 1
net_relay = 127.0.0.1:8766
```

From the pop-800 tree in WSL (WSLg shows the windows), each in its own terminal:

```sh
cp build/pop800.dsk /tmp/a.dsk; cp build/pop800.dsk /tmp/b.dsk     # (one copy each: the emulator writes a disk back)
emu/mz800emu-pop.sh        # emulator A: insert /tmp/a.dsk in FD0, reset
emu/mz800emu-pop.sh        # emulator B: insert /tmp/b.dsk in FD0, reset
```

(`POP800_NET_RELAY=host:port emu/mz800emu-pop.sh` uses another relay; `POP800_RD_SIZE=512K` another RAM disk.) Both
emulators must boot the same disk build: the room checks a build id.

## 3. Playing

1. On both: wait for the title, press **Ctrl+D**. The arena appears with `1 LOCAL  2 HOST  3 JOIN`.
2. Emulator A: **2** (HOST). It shows `ROOM CODE ABCD`.
3. Emulator B: **3** (JOIN), type the four letters (DEL deletes), **ENTER**. It shows `WAITING`, then both start.
4. A plays the kid (player 1), B the shadow in blue (player 2), each with the cursor keys + SHIFT (or W A S D + Q, or a
   joystick). ENTER after a match: a rematch; BREAK: both back to the title.

Messages: `NO LINK` (no relay at net_relay), `NO SUCH ROOM` (a wrong code), `OTHER VERSION` (another disk build),
`OTHER PLAYER LEFT`, `CONNECTION LOST` (10 s without the other machine), `DESYNC` (a bug: please report it). Both
emulators must run at normal speed: a paused or much slower one makes the other wait (`WAITING`).

On two real MZ-800s with MZPicos the room goes through mzpico.com instead: nothing to set up, the same menu.
