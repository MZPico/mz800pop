"""The regression tests, one list for CI and the local runner (docs/ci.md): the PR tier (PARTS: the jobs of
.github/workflows/pr-checks.yml), the full regression (FULL: the jobs of .github/workflows/full-regression.yml), the
smoke tier (SMOKE) and, per program, what the local runner (tools/testrun.py) needs to know about it (PROGRAMS: its
build artefacts and the sources they come from, the tools it uses, its isolation, how its full run splits into
subtests). tools/ci/check_pr.py runs the steps as they are; tools/testrun.py runs the same commands (a full run as its
subtests), cached and in parallel. A step is (name, command) or (name, command, environment); 'make' steps are the
build steps the steps after them in their part need."""
import ast, glob, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PY = sys.executable


def scripts(*sets):
    return sorted(os.path.relpath(p, ROOT) for d in sets for p in glob.glob(os.path.join(ROOT, 'tests', d, '*.txt')))


def literal(path, name):
    """a module-level literal of a test file (CASES, STRETCHES), without importing it"""
    for node in ast.parse(open(os.path.join(ROOT, path)).read()).body:
        if isinstance(node, ast.Assign) and any(getattr(t, 'id', None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise KeyError(name)


# ---- the PR tier (`check_pr.py PART`, `make check-pr`)
# Sized by the runs on GitHub's 2-vCPU runner: m4_test ~0.25 s a tick, the oracle (SDLPoP + kidsim) ~0.09 s a tick, so
# the full sets are the full regression's. Parts (measured on the runner): a ~15 min, b ~18 min, c ~17 min, d ~14.5 min,
# + ~3 min setup and build each.
M7 = scripts('m7_scripts')
# a few scripts of each earlier set: a level walk, jumps, a fight, the kill push, the shadow, the feather, Jaffar
EARLY = ['tests/m4_scripts/walk_level1.txt', 'tests/m4_scripts/jumps_climbs.txt',
         'tests/m6_scripts/fight1.txt', 'tests/m6_scripts/fight_killpush.txt',
         'tests/m5_scripts/level12_shadow_merge.txt', 'tests/m5_scripts/feather_fall.txt', 'tests/m5_scripts/level13_jaffar.txt']
# m4_game: three scripts (a level walk, a fight, the shadow), the state every tick, the screen every 10th
# the duel's logic (tools/duelsim.py, kidsim in duel mode): its scripted duels, a second (no emulator, no SDLPoP)
DUEL = [PY, 'tests/duel_test.py'] + scripts('duel_scripts')
# the Z80 duel (src/duel/duel.asm laid over the game) against duelsim on the same scripts, with the code log's hole check
DUEL_Z80 = [PY, 'tests/duel_z80.py', '--cdl']
# the duel over the network: two emulators through the local NET relay (BomberNet's relay/relay.py, POP800_RELAY_PY),
# a scripted match (both traces against duelsim) and the failures (another build, a desync, the other gone or silent, no
# relay)
DUEL_NET = [PY, 'tests/duel_net.py']
M4_GAME = ['tests/m4_scripts/walk_level1.txt', 'tests/m6_scripts/fight1.txt', 'tests/m5_scripts/level12_shadow_merge.txt']
CHEAT_BUILD = ('cheat build', ['make', '-s', 'cheats'])
PARTS = {
    'a': [
        ('perfcheck', [PY, 'tools/perfcheck.py']),
        ('m4_game sample', [PY, 'tests/m4_game.py', '--every', '10'] + M4_GAME),
        ('m4_test early', [PY, 'tests/m4_test.py'] + EARLY),
        ('edsk_check', [PY, 'tests/edsk_check.py']),
        ('m5_boot', [PY, 'tests/m5_boot.py']),
        ('m5_floppy', [PY, 'tests/m5_floppy.py']),
        ('m5_save', [PY, 'tests/m5_save.py']),
        ('m8_fstore', [PY, 'tests/m8_fstore.py']),
        # the other two full-suite RAM-disk sizes, cheaply (m5_boot probes all six itself): the frame budget against
        # that size's baseline and the frame store's layout (512K: none; 4M: classes 1 + 2, every guard set), ~1.5 min
    ] + [(n + ' ' + size, [PY, f], {'POP800_RD_SIZE': size}) for size in ('512K', '4M')
         for n, f in (('perfcheck', 'tools/perfcheck.py'), ('m8_fstore', 'tests/m8_fstore.py'))],
    'b': [
        ('m4_test m7', [PY, 'tests/m4_test.py'] + M7),
        ('oracle_suite subset', [PY, 'tools/oracle_suite.py'] + M7 + EARLY),
        ('cut_suite', [PY, 'tools/cut_suite.py']),
        ('duel_test', DUEL),
        ('duel_z80', DUEL_Z80),
        ('duel_net', DUEL_NET),
    ],
    # the game disk (build/pop800.dsk): the launcher round trips, PRES's title and cutscenes, the keys
    'c': [
        ('m7_launch', [PY, 'tests/m7_launch.py']),
        ('m7_cut quick', [PY, 'tests/m7_cut.py', '--quick']),
        ('duel_boot', [PY, 'tests/duel_boot.py']),
    ],
    'd': [
        ('m7_title quick', [PY, 'tests/m7_title.py', '--quick']),
        CHEAT_BUILD,
        ('m7_keys', [PY, 'tests/m7_keys.py']),
    ],
}

# ---- the full regression (`check_pr.py --full PART`): every test on its full set, split so that each part fits a 2-vCPU
# runner job (with the tracepoints of MZPico/mz800emu#1 the emulator no longer stops at every tick or interrupt). A
# branch can restrict a run to some parts: a file tools/ci/regress_only listing part names (one per line).
KEYS = [s for s in M7 if os.path.basename(s).startswith('key_')]
FULL = {
    'logic': [
        ('m4_test all', [PY, 'tests/m4_test.py'] + scripts('m4_scripts', 'm6_scripts', 'm5_scripts', 'm7_scripts')),
        ('cut_suite', [PY, 'tools/cut_suite.py']),
        ('duel_test', DUEL),
    ],
    'oracle-m4m6': [('oracle_suite m4+m6', [PY, 'tools/oracle_suite.py'] + scripts('m4_scripts', 'm6_scripts'))],
    'oracle-m5m7': [('oracle_suite m5+m7', [PY, 'tools/oracle_suite.py'] + scripts('m5_scripts', 'm7_scripts'))],
    'pixels-m4': [('m4_game m4 set', [PY, 'tests/m4_game.py', '--every', '1'] + scripts('m4_scripts'))],
    'pixels-m6': [('m4_game m6 set', [PY, 'tests/m4_game.py', '--every', '1'] + scripts('m6_scripts')),
                  ('duel_z80', DUEL_Z80), ('duel_net', DUEL_NET)],
    'pixels-m5': [('m4_game m5 set', [PY, 'tests/m4_game.py', '--every', '1'] + scripts('m5_scripts'))],
    'sound': [
        ('perfcheck', [PY, 'tools/perfcheck.py']),      # (here, not in logic: its baseline is per size)
        ('m7_sound full', [PY, 'tests/m7_sound.py']),
        ('edsk_check', [PY, 'tests/edsk_check.py']),
        ('m5_boot', [PY, 'tests/m5_boot.py']),
        ('m5_floppy', [PY, 'tests/m5_floppy.py']),
        ('m5_save', [PY, 'tests/m5_save.py']),
        ('m8_pace', [PY, 'tests/m8_pace.py']),
        ('m8_fstore', [PY, 'tests/m8_fstore.py']),
    ],
    'pres': [
        ('m7_title', [PY, 'tests/m7_title.py']),
        ('m7_cut', [PY, 'tests/m7_cut.py']),
    ],
    'story': [('m7_story', [PY, 'tests/m7_story.py'])],
    'launch-keys': [
        ('m7_launch', [PY, 'tests/m7_launch.py']),
        ('duel_boot', [PY, 'tests/duel_boot.py']),
        CHEAT_BUILD,
        ('m7_keys', [PY, 'tests/m7_keys.py']),
        # the CHEATS=1 build (build/cheat): the cheat keys, and the key scripts' cheats Z80 against kidsim
        ('m7_keys cheats', [PY, 'build/cheat/tests/m7_keys.py']),
        ('m4_test cheat keys', [PY, 'build/cheat/tests/m4_test.py'] + KEYS),
    ],
    # the early milestones: the colour bars, the M0 boot disk, the M1 compositor, the M3 room renderer and animated
    # tiles on every level, the M3 camera demo (records only). Not here: tests/m2_oracle.py (`make m2`: the M2 Python
    # renderer against SDLPoP's level maps, a measurement with known differences: 1518 pixels on level 1, 4298 on 4).
    # Two parts: m3_anim is ~1,350 s of the ~1,450 (the runner), levels 1-6 here, 7-14 in early-anim (~13 / ~12.5 min).
    'early': [
        ('smoke_test', [PY, 'tests/smoke_test.py']),
        ('m0_test', [PY, 'tests/m0_test.py']),
        ('m1_compare', [PY, 'tests/m1_compare.py']),
        ('m1_test', [PY, 'tests/m1_test.py']),
        ('m3 build', ['make', '-s', 'build/m3test.mzf', 'build/m3demo.mzf']),
    ] + [('m3_test %d' % lv, [PY, 'tests/m3_test.py', str(lv)]) for lv in range(1, 15)]
      + [('m3_anim %d' % lv, [PY, 'tests/m3_anim_test.py', str(lv)]) for lv in range(1, 7)]
      + [('m3_demo', [PY, 'tests/m3_demo.py'])],
    'early-anim': [('m3 build', ['make', '-s', 'build/m3test.mzf'])]
      + [('m3_anim %d' % lv, [PY, 'tests/m3_anim_test.py', str(lv)]) for lv in range(7, 15)],
}

# ---- the full regression's RAM-disk dimension (.github/workflows/full-regression.yml, tools/ci/regress_matrix.py;
# docs/ci.md "The RAM-disk sizes"). Every part runs at 512K, 1M and 4M (POP800_RD_SIZE; 4M = the top tier, which 8M and
# 16M share and the 16M jobs ran until 2026-11-13: docs/ramdisk-tiers.md section 15), except the parts below,
# whose tests never see the size: kidsim against SDLPoP (no emulator), the logic program m4test (fixed RAM-disk
# pages, all within 512 KB; it never reads the size: the probe and the frame store are the game's), cutsim, the M0-M3 programs (fixed
# pages): they run at 1M only. And the parts that also run once at 1M with POP800_RD_WAIT=1 (the MZPico: at least 1 T
# of wait on every RAM-disk access): the boot from the floppy with the frame store's fill, PRES, the game and the
# launcher's round trips, the keys: the whole disk path, without a timing reference (the cycle-exact checks,
# perfcheck, m7_title/m7_cut's step timing, measure a 0-wait card).
SIZES = ['512K', '1M', '4M']
SIZE_FREE = {'logic', 'oracle-m4m6', 'oracle-m5m7', 'early', 'early-anim'}
WAIT_PARTS = ['launch-keys']
# the parts' job times on the runner (minutes, the whole job: setup ~2.5 + the steps; regress/rd-sizes run
# 41712495363), to list the longest jobs first (GitHub does not keep to the order when the jobs outnumber the runners)
PART_MIN = {'sound': 29, 'oracle-m4m6': 28, 'launch-keys': 26, 'story': 18, 'oracle-m5m7': 16, 'early': 16,
            'early-anim': 15, 'pixels-m4': 13, 'pres': 9, 'pixels-m5': 8, 'pixels-m6': 8, 'logic': 3}

# ---- the smoke tier (`make check-smoke`, ~3 min cold locally): the build, the colour bars, the disk boot, three short
# logic scripts, one scene every tick, PRES's title (first steps) and one cutscene, the frame budget, cutsim. Each
# command is also one of the full regression's tests (the same cache entry).
SMOKE = [
    ('smoke_test', [PY, 'tests/smoke_test.py']),
    ('m5_boot', [PY, 'tests/m5_boot.py']),
    ('m4_test 3 scripts', [PY, 'tests/m4_test.py', 'tests/m4_scripts/potion_heal.txt', 'tests/m6_scripts/fight1.txt',
                           'tests/m4_scripts/sword.txt']),
    ('m4_game potion_heal', [PY, 'tests/m4_game.py', '--every', '1', 'tests/m4_scripts/potion_heal.txt']),
    ('m7_title quick', [PY, 'tests/m7_title.py', '--quick']),
    ('m7_cut 2:60', [PY, 'tests/m7_cut.py', '2:60']),
    ('perfcheck', [PY, 'tools/perfcheck.py']),
    ('cut_suite', [PY, 'tools/cut_suite.py']),
    ('duel_test', DUEL),
    ('duel_z80 parry', [PY, 'tests/duel_z80.py', 'tests/duel_scripts/parry.txt']),
]


# ---- per program: what the local runner needs
class Build:
    """build artefacts (globs relative to the test's tree, '!' excludes) and the sources they are made from (globs
    relative to the repository: a change there can change the artefacts)"""
    def __init__(self, globs, src):
        self.globs, self.src = list(globs), list(src)


MAKE_SRC = ['tools/mkmzf.py']                  # (not the Makefile: a build change there -> make check ALL=1)
TOOLS_SRC = ['tools/**', '!tools/ci/**', '!tools/testrun.py']      # (the asset converters: any tool, coarsely)
ASSETS_ALL = Build(['build/assets/*'], ['assets/**', 'tools/ci/dos_data.md5'] + TOOLS_SRC + MAKE_SRC)
ASSETS_GAME = Build(['build/assets/*', '!build/assets/title.*', '!build/assets/cut.inc', '!build/assets/pv.*',
                     '!build/assets/sound_pres*'], ASSETS_ALL.src)    # (the presentation's art and music: the disk only)
CORE_SRC = ['src/m4/**', 'src/m3/**', 'src/m1/**', 'tools/gen_kernel.py'] + MAKE_SRC
M4TEST = Build(['build/m4test.*'], CORE_SRC)
M4GAME = Build(['build/m4game.*', 'build/m4ovl.bin', 'build/ovl_*.bin', 'build/ovl_*.sym'],
               CORE_SRC + ['src/boot/**', 'tools/ovltool.py'])
DISK = Build(['build/pop800.dsk', 'build/pop800_*.mzf', 'build/boot.*', 'build/pres.*'],
             ['src/**', 'tools/mkgamedisk.py', 'tools/edsk.py', 'tools/pzpack.py', 'tools/cutart.py', 'tools/cutsim.py', 'VERSION',
              'tools/version.py'] + MAKE_SRC)
CHEAT_KEYS = Build(['build/cheat/build/ovl_keys.*', 'build/cheat/build/m4game.sym'], M4GAME.src)  # (m7_keys release)
M1 = Build(['build/m1test.*', 'build/m1.pack', 'build/m1.dir', 'build/m1.json'],
           ['src/m1/**', 'tools/pack.py', 'tools/gen_kernel.py'] + MAKE_SRC)
M3 = Build(['build/m3test.*'], ['src/m3/**', 'src/m1/**', 'tools/gen_kernel.py'] + MAKE_SRC)
M3DEMO = Build(['build/m3demo.*'], M3.src)
M0 = Build(['build/m0.dsk', 'build/m0boot.*'], ['src/m0/**'] + MAKE_SRC)
DUEL_PATCH = Build(['build/duel*'], CORE_SRC + ['src/duel/**', 'tools/duelpatch.py', 'tools/z80flow.py', 'tools/ovltool.py',
                                             'tools/build_assets.py', 'tools/duelarenas.py', 'tools/duelsim.py', 'tools/duelblade.py'])
COLORBARS = Build(['build/colorbars.*'], ['src/test/**'] + MAKE_SRC)


def cut_split():
    return [(['%d:%d' % c], {}) for c in literal('tests/m7_cut.py', 'CASES')] + [(['--rest'], {})]


# Per program (the command's script, as the steps name it): build (Build groups), uses (emu, sdlpop, pasmo, mzdisk: as
# cache inputs), data (more repository files it reads), isolation ('tree': its own working directory; 'scratch': also
# its own copy of the tree, for tests whose outputs under build/ would collide; copy: files copied there, not linked),
# lock (tests sharing an external directory run one at a time), by_script (one subtest per control script given),
# split (the run without arguments as subtests: [(args, env)], or a function giving them), expect (seconds, a guess
# for the scheduling until a time is measured).
PROGRAMS = {
    'tests/smoke_test.py': dict(build=[COLORBARS], expect=10),
    'tests/m0_test.py': dict(build=[M0], isolation='scratch', copy=['build/m0.dsk'], expect=15),
    'tests/m1_compare.py': dict(build=[M1], expect=20),
    'tests/m1_test.py': dict(build=[M1], expect=20),
    'tests/m3_test.py': dict(build=[M3, ASSETS_ALL], isolation='scratch', expect=40),
    'tests/m3_anim_test.py': dict(build=[M3, ASSETS_ALL], isolation='scratch', expect=90),
    'tests/m3_demo.py': dict(build=[M3DEMO, ASSETS_ALL], expect=30),
    'tests/m4_test.py': dict(build=[M4TEST, ASSETS_GAME], by_script=True, expect=20),
    'build/cheat/tests/m4_test.py': dict(build=[M4TEST, ASSETS_GAME], by_script=True, expect=20),
    'tools/oracle_suite.py': dict(build=[ASSETS_GAME], uses={'sdlpop'}, by_script=True, expect=30),
    'tests/m4_game.py': dict(build=[M4GAME, ASSETS_GAME], by_script=True, expect=60),
    'tools/cut_suite.py': dict(build=[ASSETS_ALL], uses={'sdlpop'}, expect=10),
    'tests/duel_test.py': dict(build=[ASSETS_GAME], uses=set(), expect=5),
    'tests/duel_z80.py': dict(build=[DUEL_PATCH, M4GAME, ASSETS_GAME], data=scripts('duel_scripts') + scripts('duel_blade'), expect=90),
    'tests/duel_net.py': dict(build=[DUEL_PATCH, M4GAME, ASSETS_GAME], data=['tests/duel_scripts/arenas_dungeon.txt', 'tests/duel_scripts/climb_dungeon.txt'], uses={'emu'},
                              expect=150),
    'tests/duel_boot.py': dict(build=[DISK, DUEL_PATCH, M4GAME, ASSETS_ALL], uses={'emu', 'mzdisk'}, expect=60),
    'tools/perfcheck.py': dict(build=[M4GAME, ASSETS_GAME], data=['tests/perf_baseline.json', 'tests/perf_baseline_512K.json', 'tests/perf_baseline_4M.json'], expect=40),
    'tests/m8_pace.py': dict(build=[M4GAME, ASSETS_GAME],
                             split=lambda: [([s], {}) for s in sorted(literal('tests/m8_pace.py', 'STRETCHES'))], expect=120),
    'tests/m8_fstore.py': dict(build=[M4GAME, ASSETS_GAME], expect=30),
    'tests/m7_sound.py': dict(build=[M4GAME, ASSETS_ALL], uses={'emu', 'pasmo'}, expect=400),
    'tests/m5_boot.py': dict(build=[DISK, M4GAME, ASSETS_ALL], uses={'emu', 'mzdisk'}, expect=90),
    'tests/edsk_check.py': dict(build=[DISK, M0], uses=set(), expect=3),
    'tests/m5_floppy.py': dict(build=[DISK, M4GAME, ASSETS_ALL], uses={'emu', 'mzdisk'}, expect=120),
    'tests/m5_save.py': dict(build=[DISK, M4GAME, ASSETS_ALL], uses={'emu', 'mzdisk'}, expect=40),
    'tests/m7_launch.py': dict(build=[DISK, M4GAME, ASSETS_ALL],
                               split=[([], {'M7_ONLY': p}) for p in ('round_trip', 'level_end', 'game_over')], expect=200),
    'tests/m7_title.py': dict(build=[DISK, M4GAME, ASSETS_ALL], split=[(['--quick'], {}), (['--rest'], {})], expect=120),
    'tests/m7_cut.py': dict(build=[DISK, M4GAME, ASSETS_ALL], split=cut_split, expect=90),
    'tests/m7_story.py': dict(build=[DISK, M4GAME, ASSETS_ALL],
                              split=[([p], {}) for p in ('title', 'expired', 'ending', 'keys', 'late', 'flow')], expect=300),
    'tests/m7_keys.py': dict(build=[DISK, M4GAME, ASSETS_ALL, CHEAT_KEYS], uses={'emu', 'mzdisk'},
                             split=[([p], {}) for p in ('texts', 'sound', 'pause', 'levels', 'launched', 'release')], expect=90),
    'build/cheat/tests/m7_keys.py': dict(build=[M4GAME, ASSETS_GAME], data=['tests/m7_scripts/death_music.txt'], expect=60),
}
