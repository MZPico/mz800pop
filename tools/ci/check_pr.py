#!/usr/bin/env python3
"""The PR test tier (`make check-pr`, .github/workflows/pr-checks.yml; docs/ci.md): runs the steps of one part (or all),
each to its end, prints the wall time of each and fails if any failed. Needs the build (`make ci-build`) and an X
display for the emulator (DISPLAY, e.g. xvfb-run).
usage: check_pr.py [all | a | b | c | d ...] [--list]
       check_pr.py --full [all | logic | oracle-m4m6 | ... | early] [--list]   (the full regression; a branch can limit
                   it to some parts: tools/ci/regress_only, one part name per line, the others print "skipped")
       check_pr.py --smoke [--list]   (the smoke tier, one at a time; `make check-smoke` runs it in parallel)"""
import os, subprocess, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PY = sys.executable

# The lists (the PR tier PARTS, the full regression FULL, the smoke tier SMOKE) are in tools/ci/suite.py, shared with
# the local runner (tools/testrun.py).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from suite import PARTS, FULL, SMOKE


def main():
    tier = FULL if '--full' in sys.argv else {'smoke': SMOKE} if '--smoke' in sys.argv else PARTS
    args = [a for a in sys.argv[1:] if not a.startswith('--')] or ['all']
    names = sorted(tier) if 'all' in args else args
    bad = [n for n in names if n not in tier]
    if bad: sys.exit('check_pr.py: unknown part(s) %s (known: %s)' % (' '.join(bad), ' '.join(sorted(tier))))
    only = os.path.join(ROOT, 'tools', 'ci', 'regress_only')
    if '--full' in sys.argv and os.path.exists(only):
        keep = {l.strip() for l in open(only) if l.strip() and not l.startswith('#')}
        bad = sorted(keep - set(tier))
        if bad: sys.exit('check_pr.py: tools/ci/regress_only names unknown part(s) %s (known: %s)' % (' '.join(bad), ' '.join(sorted(tier))))
        for n in [n for n in names if n not in keep]: print('==== %s: skipped (tools/ci/regress_only)' % n)
        names = [n for n in names if n in keep]
    steps = [s for n in names for s in tier[n]]
    if '--list' in sys.argv:
        for name, cmd in steps: print('%-20s %s' % (name, ' '.join((['python3'] if cmd[0] == PY else cmd[:1]) + cmd[1:])))
        return
    res = []
    for name, cmd in steps:
        print('==== %s: %s' % (name, ' '.join(cmd[1:] if cmd[0] == PY else cmd)), flush=True)
        t0 = time.time(); rc = subprocess.run(cmd, cwd=ROOT).returncode; dt = time.time() - t0
        res.append((name, rc, dt))
        print('==== %s: %s in %.0f s' % (name, 'ok' if rc == 0 else 'FAILED (exit %d)' % rc, dt), flush=True)
    print('\n%s (%s):' % ('full regression' if tier is FULL else 'smoke tier' if '--smoke' in sys.argv else 'PR tier', ' '.join(names)))
    for name, rc, dt in res: print('  %-20s %-6s %5.0f s' % (name, 'ok' if rc == 0 else 'FAILED', dt))
    sys.exit(1 if any(rc for _, rc, _ in res) else 0)


if __name__ == '__main__':
    main()
