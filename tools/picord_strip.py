#!/usr/bin/env python3
"""The MZ-1R18 build's view of the sources: every `if defined PICORD` block reduced to its else branch (the pico_rd
build's branch and the if / else / endif lines around the MZ-1R18's dropped), nested conditionals kept as they are.
The MZ-1R18 build must not depend on the pico_rd lines (`make picord`, docs/ramdisk-tiers.md "pico_rd"):
tools/fstore.py hashes these texts for the frame store's build id, and `make mz1r18-check` builds the disk from a
stripped copy of src/ and compares it with build/pop800.dsk.
  picord_strip.py DIR   strip every .asm / .inc under DIR in place"""
import os, sys


def mz1r18_text(src):
    """src (bytes): the text without the pico_rd lines"""
    out = []
    stack = []      # per open `if`: None (another condition: kept as it is), 'pico' or 'mz' (a PICORD block's branch)
    for line in src.split(b'\n'):
        t = line.split(b';')[0].split()
        dropping = any(s == 'pico' for s in stack)
        if t[:1] == [b'if']:
            if t == [b'if', b'defined', b'PICORD']:
                stack.append('pico'); continue
            stack.append(None)
        elif t == [b'else'] and stack:
            if stack[-1] is not None:
                stack[-1] = 'mz'; continue
        elif t == [b'endif'] and stack:
            if stack.pop() is not None: continue
        if not dropping: out.append(line)
    assert not stack, 'an unclosed if'
    return b'\n'.join(out)


def main():
    for root, _, files in os.walk(sys.argv[1]):
        for n in files:
            if n.endswith(('.asm', '.inc')):
                p = os.path.join(root, n); s = open(p, 'rb').read(); t = mz1r18_text(s)
                if t != s: open(p, 'wb').write(t)


if __name__ == '__main__':
    main()
