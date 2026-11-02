#!/usr/bin/env python3
"""Wrap a raw Z80 binary into a Sharp MZF file.
usage: mkmzf.py in.bin out.mzf NAME load_hex [exec_hex]
The ROM's tape loader (used by the emulator's CMT hack) cannot write 0xD000 and above (MZ-700 memory map
while loading), so the part of the image from 0xC000 on is written to <out>.b2 instead; tools/emu.py's
run_mzf() pokes it into RAM after the load. The real floppy loader (M5) loads both parts itself."""
import sys, struct, os
inp, outp, name, load = sys.argv[1:5]
load = int(load, 16); exec_ = int(sys.argv[5], 16) if len(sys.argv) > 5 else load
body = open(inp, 'rb').read()
SPLIT = 0xC000
b2 = b''
if load + len(body) > SPLIT:
    cut = SPLIT - load
    b2 = body[cut:]; body = body[:cut]
    # drop the zero padding between the end of block 1 and the split address
    while body.endswith(b'\0' * 256): body = body[:-256]
nm = name.upper().encode('ascii')[:16]
hdr = bytes([1]) + nm + b'\r' + b'\r' * (16 - len(nm))
hdr = hdr[:17] + b'\r'  # name field 0x01..0x10, terminator 0x11
hdr += struct.pack('<HHH', len(body), load, exec_)
hdr += b'\0' * (128 - len(hdr))
open(outp, 'wb').write(hdr + body)
b2path = os.path.splitext(outp)[0] + '.b2'
if b2:
    open(b2path, 'wb').write(struct.pack('<H', SPLIT) + b2)
elif os.path.exists(b2path): os.remove(b2path)
print(outp, len(body), 'bytes, load %04X exec %04X' % (load, exec_) + (', block 2 %d bytes at %04X' % (len(b2), SPLIT) if b2 else ''))
