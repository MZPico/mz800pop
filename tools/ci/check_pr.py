#!/usr/bin/env python3
"""The PR test tier (`make check-pr`, .github/workflows/pr-checks.yml; docs/ci.md): runs the steps of one part (or all),
each to its end, prints the wall time of each and fails if any failed. Needs the build (`make ci-build`) and an X
display for the emulator (DISPLAY, e.g. xvfb-run).
usage: check_pr.py [all | a | b | c | d ...] [--list]"""
import glob, os, subprocess, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PY = sys.executable

# Sized by the runs on GitHub's 2-vCPU runner: m4_test ~0.25 s a tick, the oracle (SDLPoP + kidsim) ~0.09 s a tick, so
# the full sets (m4_test ~75 min, oracle_suite ~33 min) stay local (docs/ci.md). Parts (measured on the runner): a ~15 min,
# b ~18 min, c ~17 min, d ~14.5 min, + ~3 min setup and build each.
M7 = sorted(os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, 'tests', 'm7_scripts', '*.txt')))
# a few scripts of each earlier set: a level walk, jumps, a fight, the kill push, the shadow, the feather, Jaffar
EARLY = ['tests/m4_scripts/walk_level1.txt', 'tests/m4_scripts/jumps_climbs.txt',
         'tests/m6_scripts/fight1.txt', 'tests/m6_scripts/fight_killpush.txt',
         'tests/m5_scripts/level12_shadow_merge.txt', 'tests/m5_scripts/feather_fall.txt', 'tests/m5_scripts/level13_jaffar.txt']
# m4_game: three scripts (a level walk, a fight, the shadow), the state every tick, the screen every 10th
M4_GAME = ['tests/m4_scripts/walk_level1.txt', 'tests/m6_scripts/fight1.txt', 'tests/m5_scripts/level12_shadow_merge.txt']
PARTS = {
    'a': [
        ('perfcheck', [PY, 'tools/perfcheck.py']),
        ('m4_game sample', [PY, 'tests/m4_game.py', '--every', '10'] + M4_GAME),
        ('m4_test early', [PY, 'tests/m4_test.py'] + EARLY),
        ('m5_boot', [PY, 'tests/m5_boot.py']),
        ('m5_save', [PY, 'tests/m5_save.py']),
    ],
    'b': [
        ('m4_test m7', [PY, 'tests/m4_test.py'] + M7),
        ('oracle_suite subset', [PY, 'tools/oracle_suite.py'] + M7 + EARLY),
        ('cut_suite', [PY, 'tools/cut_suite.py']),
    ],
    # the game disk (build/pop800.dsk): the launcher round trips, PRES's title and cutscenes, the keys
    'c': [
        ('m7_launch', [PY, 'tests/m7_launch.py']),
        ('m7_cut quick', [PY, 'tests/m7_cut.py', '--quick']),
    ],
    'd': [
        ('m7_title quick', [PY, 'tests/m7_title.py', '--quick']),
        ('cheat build', ['make', '-s', 'cheats']),
        ('m7_keys', [PY, 'tests/m7_keys.py']),
    ],
}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')] or ['all']
    names = sorted(PARTS) if 'all' in args else args
    steps = [s for n in names for s in PARTS[n]]
    if '--list' in sys.argv:
        for name, cmd in steps: print('%-20s %s' % (name, ' '.join((['python3'] if cmd[0] == PY else cmd[:1]) + cmd[1:])))
        return
    res = []
    for name, cmd in steps:
        print('==== %s: %s' % (name, ' '.join(cmd[1:] if cmd[0] == PY else cmd)), flush=True)
        t0 = time.time(); rc = subprocess.run(cmd, cwd=ROOT).returncode; dt = time.time() - t0
        res.append((name, rc, dt))
        print('==== %s: %s in %.0f s' % (name, 'ok' if rc == 0 else 'FAILED (exit %d)' % rc, dt), flush=True)
    print('\nPR tier (%s):' % ' '.join(names))
    for name, rc, dt in res: print('  %-20s %-6s %5.0f s' % (name, 'ok' if rc == 0 else 'FAILED', dt))
    sys.exit(1 if any(rc for _, rc, _ in res) else 0)


if __name__ == '__main__':
    main()
