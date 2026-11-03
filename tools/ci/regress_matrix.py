#!/usr/bin/env python3
"""The full regression's job matrix (.github/workflows/full-regression.yml; docs/ci.md "The RAM-disk sizes"): the parts
of FULL (tools/ci/suite.py) times the RAM-disk variants. A variant is a size (512K, 1M, 16M: POP800_RD_SIZE) or 1M+N
(1M with POP800_RD_WAIT=N wait states on every RAM-disk access, N at most 14: the boot stops above that). By default every part runs at 512K, 1M and 16M,
except suite.SIZE_FREE (tests that never see the size: 1M only), and suite.WAIT_PARTS also at 1M+1.
Which variants and parts run:
  - the workflow's inputs on a manual run (environment REGRESS_SIZES, REGRESS_PARTS: words separated by spaces or
    commas; empty = the branch's files or the default), else
  - the branch's files: tools/ci/regress_sizes (variants, one per line or several on a line, `#` comments) and
    tools/ci/regress_only (part names; check_pr.py --full reads it too), else the default.
  The word `every-size` among the variants runs the SIZE_FREE parts at every listed size too (to check that claim,
  e.g. after an emulator change); a variant 1M+N runs only the WAIT_PARTS at that wait, `every-size` or not (the
  other parts compare cycles with a 0-wait reference: perfcheck, m8_pace, m7_title / m7_cut's step timing).
  A variant list without 1M leaves out the SIZE_FREE parts (unless `every-size`).
Prints the matrix as JSON ({"include": [{part, variant, size, wait, label}]}: size and wait empty at the INI's 1M / 0), the longest jobs first (suite.PART_MIN: with
more jobs than concurrent runners, the short ones queue); with GITHUB_OUTPUT set, also writes `matrix=...` there.
usage: regress_matrix.py [--sizes "512K 1M"] [--parts "pres story"] [--list]"""
import json, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from suite import FULL, SIZES, SIZE_FREE, WAIT_PARTS, PART_MIN

DEFAULT = SIZES + ['1M+1']
MAX_WAIT = 14       # the most wait states the boot accepts (below)


def words(text):
    return [w for l in text.splitlines() for w in re.split(r'[\s,]+', l.split('#')[0]) if w]


def from_file(name):
    p = os.path.join(ROOT, 'tools', 'ci', name)
    return words(open(p).read()) if os.path.exists(p) else None


def arg(name):
    a = sys.argv[1:]
    return a[a.index(name) + 1] if name in a else None


def matrix(variants, parts):
    every = 'every-size' in variants
    variants = [v for v in variants if v != 'every-size'] or DEFAULT
    bad = [v for v in variants if not re.fullmatch(r'(512K|1M|16M)(\+[0-9]+)?', v)]
    if bad: sys.exit('regress_matrix.py: unknown RAM-disk variant(s) %s (known: 512K 1M 16M, SIZE+N for N wait states, every-size)' % ' '.join(bad))
    # every part boots the floppy or starts the game, and the boot stops when its GAME read speed is above 36.0
    # clocks/byte (src/boot/rdspeed.asm RD_SPEED_MAX): 21 + N + N/32 is 35.4 at +14, 36.5 at +15. No part expects the
    # stop (tests/m5_boot.py boots at +16 itself for that), so a variant beyond +14 could only fail.
    bad = [v for v in variants if '+' in v and int(v.split('+')[1]) > MAX_WAIT]
    if bad: sys.exit('regress_matrix.py: %s: the boot stops above 36.0 clocks/byte (src/boot/rdspeed.asm): at most +%d '
                     'wait states' % (' '.join(bad), MAX_WAIT))
    parts = sorted(FULL) if not parts or parts == ['all'] else parts
    bad = sorted(set(parts) - set(FULL))
    if bad: sys.exit('regress_matrix.py: unknown part(s) %s (known: %s)' % (' '.join(bad), ' '.join(sorted(FULL))))
    jobs = []
    for v in dict.fromkeys(variants):
        size, _, wait = v.partition('+')
        for p in parts:
            if wait and wait != '0':
                if p not in WAIT_PARTS: continue        # (every-size widens the sizes, never the waits)
            elif p in SIZE_FREE and size != '1M' and not every: continue
            jobs.append(dict(part=p, variant=v, size='' if size == '1M' else size, wait='' if wait in ('', '0') else wait,
                             label=size + (' +%s wait' % wait if wait not in ('', '0') else '')))
    if not jobs: sys.exit('regress_matrix.py: no jobs (variants %s, parts %s)' % (' '.join(variants), ' '.join(parts)))
    order = {v: i for i, v in enumerate(variants)}
    jobs.sort(key=lambda j: (-PART_MIN.get(j['part'], 30), order[j['variant']]))
    return {'include': jobs}


def main():
    sizes = arg('--sizes') if arg('--sizes') is not None else os.environ.get('REGRESS_SIZES', '')
    parts = arg('--parts') if arg('--parts') is not None else os.environ.get('REGRESS_PARTS', '')
    variants = words(sizes) or from_file('regress_sizes') or DEFAULT
    m = matrix(variants, words(parts) or from_file('regress_only'))
    if '--list' in sys.argv:
        for j in m['include']: print('%-12s %-12s ~%d min' % (j['part'], j['label'], PART_MIN.get(j['part'], 30)))
        print('%d jobs, ~%d runner minutes' % (len(m['include']), sum(PART_MIN.get(j['part'], 30) for j in m['include'])))
        return
    out = json.dumps(m, separators=(',', ':'))
    print(out)
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f: f.write('matrix=%s\n' % out)


if __name__ == '__main__':
    main()
