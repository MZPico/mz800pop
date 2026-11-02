#!/usr/bin/env python3
"""The PR test tier (`make check-pr`, .github/workflows/pr-checks.yml; docs/ci.md): runs the steps of one part (or all),
each to its end, prints the wall time of each and fails if any failed. Needs the build (`make ci-build`) and an X
display for the emulator (DISPLAY, e.g. xvfb-run).
usage: check_pr.py [all | a | b ...] [--list]"""
import glob, os, subprocess, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PY = sys.executable

# m4_test: all of tests/m7_scripts (the sound ticks model, the keys) + a few of each earlier set
M4_SUBSET = ['tests/m4_scripts/walk_level1.txt', 'tests/m4_scripts/jumps_climbs.txt', 'tests/m4_scripts/traps_b9.txt',
             'tests/m6_scripts/fight1.txt', 'tests/m6_scripts/fight_killpush.txt',
             'tests/m5_scripts/level12_shadow_merge.txt', 'tests/m5_scripts/feather_fall.txt', 'tests/m5_scripts/level13_jaffar.txt']
# m4_game: three scripts (a level walk, a fight, the shadow), the screen every 10th tick (the state every tick)
M4_GAME = ['tests/m4_scripts/walk_level1.txt', 'tests/m6_scripts/fight1.txt', 'tests/m5_scripts/level12_shadow_merge.txt']
PARTS = {
    'a': [
        ('perfcheck', [PY, 'tools/perfcheck.py']),
        ('m4_game sample', [PY, 'tests/m4_game.py', '--every', '10'] + M4_GAME),
        ('m4_test subset', [PY, 'tests/m4_test.py'] + sorted(glob.glob(os.path.join(ROOT, 'tests', 'm7_scripts', '*.txt'))) + M4_SUBSET),
    ],
    'b': [
        ('oracle_suite', [PY, 'tools/oracle_suite.py']),
        ('cut_suite', [PY, 'tools/cut_suite.py']),
    ],
}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')] or ['all']
    names = sorted(PARTS) if 'all' in args else args
    steps = [s for n in names for s in PARTS[n]]
    if '--list' in sys.argv:
        for name, cmd in steps: print('%-20s %s' % (name, ' '.join(['python3'] + [os.path.relpath(c, ROOT) for c in cmd[1:]])))
        return
    res = []
    for name, cmd in steps:
        print('==== %s: %s' % (name, ' '.join(cmd[1:])), flush=True)
        t0 = time.time(); rc = subprocess.run(cmd, cwd=ROOT).returncode; dt = time.time() - t0
        res.append((name, rc, dt))
        print('==== %s: %s in %.0f s' % (name, 'ok' if rc == 0 else 'FAILED (exit %d)' % rc, dt), flush=True)
    print('\nPR tier (%s):' % ' '.join(names))
    for name, rc, dt in res: print('  %-20s %-6s %5.0f s' % (name, 'ok' if rc == 0 else 'FAILED', dt))
    sys.exit(1 if any(rc for _, rc, _ in res) else 0)


if __name__ == '__main__':
    main()
