#!/usr/bin/env python3
"""The local regression runner (docs/ci.md, "Local testing"): the tests of tools/ci/suite.py (the same list the CI jobs
run), in parallel, each result cached against a hash of everything it depends on.

  python3 tools/testrun.py [--tier check|smoke|all|full|pr] [--base REF] [--part P] [-j N] [-k TEXT ...] [--no-cache]
                           [--no-build] [--list] [--explain ID] [--display DISPLAY] [--idle S]

Tiers: check (`make check`): the full regression's tests that the changes since --base can affect (git: the files that
differ from REF in the working tree, and the untracked ones; default REF: the merge base with origin/main, which the
runners have checked), plus the tests that failed, hung or timed out in an earlier run; each one cached. smoke (`make
check-smoke`): suite.SMOKE, a few minutes cold. all: every test of the full regression, cached. full (`make
check-full`): every test, no cache (the full regression normally runs on GitHub's runners). pr: the PR tier
(suite.PARTS; --part a..d: one job's part), cached.

The tests: each step of the tier (suite.PARTS, FULL, SMOKE) is one test, with these exceptions: a program marked
by_script (m4_test, oracle_suite, m4_game) given control scripts runs one subtest per script; a program with a split
run without arguments (m7_launch, m7_title, m7_cut, m7_story, m7_keys, m8_pace) runs as its subtests. A test's id is
its command: the program, its environment, its arguments ('m4_game --every 1 m4/walk_level1', 'm7_cut 2:60',
'm7_launch M7_ONLY=round_trip', 'cheat/m4_test m7/key_cheats': the CHEATS=1 tree build/cheat). The same command in
two tiers is the same test (one cache entry). Per program suite.PROGRAMS gives the build artefacts and their sources,
the tools, the isolation and an expected time; build/testrun/times.json keeps the measured times.

Cache (build/testrun/cache.json): a pass is recorded against a sha256 over the command line, the test's file and the
repo modules it imports (static import analysis, tests/ and tools/ only), the control scripts it names, its build
artefacts, tools/ci/dos_data.md5 (the DOS data's proxy), assets/ (without *.md), tools/palettes.json, and, as it
uses them, the emulator (binary, emu/), SDLPoP (binary, commit, tools/sdlpop-pop800.patch, SDLPoP.ini), pasmo, mzdisk.
The same key again: "cached", not run. Failures are never cached; --no-cache runs everything.

Affected (tier check): a test is selected when a changed file is one of its repository inputs above or matches the
sources of its build artefacts (suite.Build.src: src/, tools/, assets/); *.md files never select. The Makefile, the
emulator, SDLPoP, pasmo and mzdisk select nothing: after changing one, --tier all (`make check ALL=1`).

Isolation: every test runs in its own working directory build/testrun/work/<id> (mz800emu writes its breakpoint file and
other state into its current directory; its RAM disk is in memory only, emu/mz800emu.ini). Tests that write files under
build/ that would collide between parallel subtests get a scratch tree build/testrun/scratch/<id> (the project's
directories as symlinks, build/ a directory of symlinks to the real artefacts, the test's disk image a copy); tests that
boot the game disk copy it themselves (tempfile). A lock (suite.PROGRAMS lock) serialises tests that share an external
directory (none now).

Watchdog: a test whose log has not grown and whose processes used less than 5 % CPU for --idle seconds (default 120:
an emulator that hangs at its start-up) is killed and run once more; hanging twice it is reported as hung. A test
running longer than 3 x its expected duration (at least 5 min; 30 min while it has no measured time) is killed as a
timeout.

Output: one line per finished test, a summary table, build/testrun/last.json, the logs in build/testrun/logs/.
Exit status 1 when a test failed, hung or timed out."""
import argparse, ast, glob, hashlib, json, os, re, shutil, signal, socket, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'ci'))
import suite

PY = sys.executable
OUT = os.path.join(ROOT, 'build', 'testrun')
CHEAT = 'build/cheat'                       # the CHEATS=1 tree (`make cheats`)
KEY_VERSION = 2                             # bump to invalidate every cached pass
CLK_TCK = os.sysconf('SC_CLK_TCK')
IDLE_CPU = 0.05                             # below this share of a CPU (and no log growth) a test counts as idle
COMMON = ['tools/ci/dos_data.md5', 'assets/**', '!assets/**/*.md', 'tools/palettes.json']


class Test:
    def __init__(self, prog, args, env, info):
        self.prog, self.args, self.env = prog, list(args), dict(env)
        self.cmd = [PY, prog] + self.args
        self.tree = CHEAT if prog.startswith(CHEAT + '/') else '.'
        name = os.path.basename(prog)[:-3]
        if self.tree == CHEAT: name = 'cheat/' + name
        self.id = ' '.join([name] + ['%s=%s' % kv for kv in sorted(self.env.items())] +
                           [short(a) if a.endswith('.txt') and '/' in a else a for a in self.args])
        builds = info.get('build', [])
        self.build = [g for b in builds for g in b.globs]
        self.src = [g for b in builds for g in b.src]
        self.uses = set(info.get('uses', {'emu'})); self.data = list(info.get('data', []))
        self.isolation, self.copy, self.lock = info.get('isolation', 'tree'), list(info.get('copy', [])), info.get('lock')
        self.expect0 = info.get('expect', 60)
        self.make, self.tags = [], set()    # (the build steps it needs beyond make ci-build; the tiers and parts it is in)

    def safe(self): return re.sub(r'[^A-Za-z0-9_.-]+', '_', self.id)


def short(sp):
    """tests/m4_scripts/walk_level1.txt -> m4/walk_level1"""
    return '%s/%s' % (os.path.basename(os.path.dirname(sp)).split('_')[0], os.path.basename(sp)[:-4])


def variants(cmd):
    """a step's command -> [(program, args, env)]: by_script programs one per script, a split program's full run its
    subtests, otherwise the command itself"""
    prog, args = cmd[1], cmd[2:]
    if prog not in suite.PROGRAMS: raise SystemExit('testrun: %s is not in tools/ci/suite.py PROGRAMS' % prog)
    info = suite.PROGRAMS[prog]
    scr = [a for a in args if a.endswith('.txt')]
    if info.get('by_script') and scr:
        flags = [a for a in args if not a.endswith('.txt')]
        return info, [(flags + [s], {}) for s in scr]
    split = info.get('split')
    if split and not args: return info, split() if callable(split) else split
    return info, [(args, {})]


def registry():
    """{tier: [Test]}: 'full' (suite.FULL), 'smoke', 'pr'; one Test object per id across the tiers"""
    byid = {}; tiers = {'full': [], 'smoke': [], 'pr': []}
    def add(tier, part, steps):
        makes = []
        for name, cmd in steps:
            if cmd[0] == 'make': makes.append(cmd); continue
            info, vs = variants(cmd)
            for args, env in vs:
                t = Test(cmd[1], args, env, info)
                t = byid.setdefault(t.id, t)
                for m in makes:
                    if m not in t.make: t.make.append(m)
                t.tags.add('%s:%s' % (tier, part) if part else tier)
                if t not in tiers[tier]: tiers[tier].append(t)
    for part, steps in sorted(suite.FULL.items()): add('full', part, steps)
    for part, steps in sorted(suite.PARTS.items()): add('pr', part, steps)
    add('smoke', None, suite.SMOKE)
    return tiers


# ---- the cache key
_hash = {}
def fhash(path):
    try: st = os.stat(path)
    except OSError: return 'missing'
    k = (path, st.st_size, st.st_mtime_ns)
    if k not in _hash:
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
        _hash[k] = h.hexdigest()
    return _hash[k]


def expand(patterns, base):
    """globs (relative to base; '**' recursive; '!' excludes) -> sorted files"""
    inc, exc = set(), set()
    for p in patterns:
        neg = p.startswith('!'); p = p.lstrip('!')
        hits = [f for f in glob.glob(os.path.join(base, p), recursive=True) if os.path.isfile(f)]
        (exc if neg else inc).update(os.path.relpath(f, base) for f in hits)
        if not hits and not neg and not any(c in p for c in '*?['): inc.add(p)       # (a named file that is missing)
    return sorted(inc - exc)


_imports = {}
def imports(path):
    """the repo modules a file imports, transitively (tests/ and tools/: the directories the tests put on sys.path)"""
    path = os.path.realpath(path)
    if path in _imports: return _imports[path]
    seen = {path}; todo = [path]
    while todo:
        f = todo.pop()
        try: tree = ast.parse(open(f).read())
        except (OSError, SyntaxError): continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import): names = [a.name.split('.')[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module: names = [node.module.split('.')[0]]
            else: continue
            for n in names:
                for d in (os.path.dirname(f), os.path.join(ROOT, 'tests'), os.path.join(ROOT, 'tools')):
                    m = os.path.join(d, n + '.py')
                    if os.path.isfile(m):
                        m = os.path.realpath(m)
                        if m not in seen: seen.add(m); todo.append(m)
                        break
    _imports[path] = sorted(seen)
    return _imports[path]


def named_scripts(prog, files):
    """the control scripts (tests/*_scripts/*.txt) named in the test's own file and the test modules it imports"""
    names = set()
    for f in files:
        if os.path.relpath(f, ROOT).startswith('tests' + os.sep) or f == os.path.realpath(prog):
            names.update(re.findall(r'([A-Za-z0-9_]+\.txt)', open(f).read()))
    return sorted(os.path.relpath(p, ROOT) for n in names for p in glob.glob(os.path.join(ROOT, 'tests', '*_scripts', n)))


def emu_binary():
    sh = open(os.path.join(ROOT, 'emu', 'mz800emu-pop.sh')).read()
    m = re.search(r'\$\{MZ800EMU_BIN:-([^}]+)\}', sh)
    return os.environ.get('MZ800EMU_BIN') or (m.group(1) if m else '')


def git_head(repo):
    """the commit a checkout is on, from its .git files (no git process)"""
    g = os.path.join(repo, '.git')
    if os.path.isfile(g):
        g = os.path.join(repo, open(g).read().split(':', 1)[1].strip())
    try: head = open(os.path.join(g, 'HEAD')).read().strip()
    except OSError: return 'none'
    if not head.startswith('ref:'): return head
    ref = head[4:].strip()
    try: return open(os.path.join(g, ref)).read().strip()
    except OSError: pass
    try:
        for l in open(os.path.join(g, 'packed-refs')):
            if l.strip().endswith(' ' + ref): return l.split()[0]
    except OSError: pass
    return head


def repo_files(t):
    """the repository files a test reads: its program and the modules it imports, the control scripts it is given or
    names, its data, COMMON, emu/ (the emulator's script and settings), the SDLPoP patch"""
    # a program of the CHEATS=1 tree (build/cheat/tests/...): its tests/ and tools/ are symlinks to the repository's
    # (Makefile: cheats), so read the repository's file: the tree need not exist yet (`make cheats` runs after selection)
    prog = os.path.join(ROOT, t.prog[len(CHEAT) + 1:] if t.prog.startswith(CHEAT + '/') else t.prog)
    mods = imports(prog)
    files = [os.path.relpath(m, ROOT) for m in mods]
    files += sorted(set(named_scripts(prog, mods) + t.data + [a for a in t.args if a.endswith('.txt')]))
    files += expand(COMMON, ROOT)
    if 'emu' in t.uses: files += expand(['emu/*'], ROOT)
    if 'sdlpop' in t.uses: files.append('tools/sdlpop-pop800.patch')
    return files


def inputs(t):
    """[(label, hash)]: everything the result depends on"""
    tree = os.path.join(ROOT, t.tree)
    out = [('key-version', str(KEY_VERSION)), ('python', '%d.%d' % sys.version_info[:2]), ('tree', t.tree),
           ('cmd', json.dumps(['python'] + t.cmd[1:])), ('env', json.dumps(t.env, sort_keys=True))]
    out += [(f, fhash(os.path.join(ROOT, f))) for f in repo_files(t)]
    for f in expand(t.build, tree): out.append((os.path.normpath(os.path.join(t.tree, f)), fhash(os.path.join(tree, f))))
    if 'emu' in t.uses: out += [('emu-binary', fhash(emu_binary())), ('emu-exe-env', os.environ.get('MZ800EMU_EXE', '')),
                               ('rd-size-env', os.environ.get('POP800_RD_SIZE', '')),
                               ('rd-wait-env', os.environ.get('POP800_RD_WAIT', ''))]
    if 'sdlpop' in t.uses:
        s = os.path.join(ROOT, 'external', 'SDLPoP')
        out += [('sdlpop-binary', fhash(os.path.join(s, 'prince'))), ('sdlpop-commit', git_head(s)),
                ('sdlpop-ini', fhash(os.path.join(s, 'SDLPoP.ini')))]
    if 'pasmo' in t.uses: out.append(('pasmo', fhash(shutil.which('pasmo') or 'pasmo')))
    if 'mzdisk' in t.uses: out.append(('mzdsk-fsmz', fhash(os.path.join(ROOT, 'external', 'mzdisk', 'build', 'mzdsk-fsmz'))))
    return out


def cache_key(t):
    return hashlib.sha256(json.dumps(inputs(t)).encode()).hexdigest()


# ---- affected (tier check)
def glob_re(p):
    """a repository glob ('**' any depth, '*' and '?' within a name) -> a regex"""
    out = ''
    i = 0
    while i < len(p):
        if p.startswith('**', i): out += '.*'; i += 2
        elif p[i] == '*': out += '[^/]*'; i += 1
        elif p[i] == '?': out += '[^/]'; i += 1
        else: out += re.escape(p[i]); i += 1
    return re.compile(out + '$')


_re = {}
def matches(path, pats):
    """the path matches one of the patterns and none of the '!' ones"""
    hit = False
    for p in pats:
        neg = p.startswith('!'); p = p.lstrip('!')
        if p not in _re: _re[p] = glob_re(p)
        if _re[p].match(path):
            if neg: return False
            hit = True
    return hit


def git(*args):
    r = subprocess.run(['git'] + list(args), cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode: raise SystemExit('testrun: git %s: %s' % (' '.join(args), r.stderr.strip()))
    return r.stdout


def default_base():
    for ref in ('origin/main', 'main'):
        r = subprocess.run(['git', 'merge-base', 'HEAD', ref], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        if r.returncode == 0: return r.stdout.strip(), 'the merge base with ' + ref
    raise SystemExit('testrun: no origin/main or main to compare with: give --base')


def changed_files(base):
    """the files that differ from base in the working tree (committed or not), and the untracked ones; not *.md"""
    files = set(git('diff', '--name-only', base).split()) | set(git('ls-files', '--others', '--exclude-standard').split())
    return sorted(f for f in files if not f.endswith('.md'))


def affected(t, changed):
    """the changed files that can affect the test (its repository inputs, its build artefacts' sources)"""
    files = set(repo_files(t))
    return [f for f in changed if f in files or matches(f, t.src)]


def load_json(path, default):
    try: return json.load(open(path))
    except (OSError, ValueError): return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    json.dump(data, open(tmp, 'w'), indent=1, sort_keys=True); os.replace(tmp, path)


# ---- isolation
def rmtree_safe(path):
    """remove a work or scratch tree: its symlinks (external/ among them) are unlinked first, never followed"""
    if not os.path.lexists(path): return
    if os.path.islink(path): os.unlink(path); return
    for d, dirs, files in os.walk(path, topdown=True, followlinks=False):
        for n in dirs + files:
            p = os.path.join(d, n)
            if os.path.islink(p): os.unlink(p)
    shutil.rmtree(path)


SCRATCH_SKIP = ('testrun', 'sound', 'cheat', 'pace')
def make_scratch(t, base):
    """build/testrun/scratch/<id>: the tree's entries as symlinks; build/ a directory of symlinks to the artefacts
    (not the images, sounds and other trees: the test's own outputs land here); t.copy copied"""
    src = os.path.join(ROOT, t.tree)
    rmtree_safe(base); os.makedirs(os.path.join(base, 'build'))
    for n in os.listdir(src):
        if n != 'build' and not n.startswith('.'): os.symlink(os.path.join(src, n), os.path.join(base, n))
    for n in os.listdir(os.path.join(src, 'build')):
        if n in SCRATCH_SKIP or n.endswith(('.png', '.gif', '.wav', '.log')): continue
        rel = 'build/' + n
        if rel in t.copy: shutil.copy2(os.path.join(src, rel), os.path.join(base, rel))
        else: os.symlink(os.path.join(src, rel), os.path.join(base, rel))
    return base


# ---- the X display
def probe_display(display, timeout=15):
    """True when the emulator starts on that display (and answers)"""
    work = os.path.join(OUT, 'work', '_display_probe'); rmtree_safe(work); os.makedirs(work)
    code = 'import sys; sys.path.insert(0, %r)\nfrom emu import Emu\ne = Emu(); e.run(2); e.close()' % os.path.join(ROOT, 'tools')
    env = dict(os.environ)
    if display: env['DISPLAY'] = display
    else: env.pop('DISPLAY', None)
    p = subprocess.Popen([PY, '-c', code], cwd=work, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    try: ok = p.wait(timeout) == 0
    except subprocess.TimeoutExpired: ok = False
    kill_session(p.pid)
    rmtree_safe(work)
    return ok


def free_display():
    for n in range(99, 200):
        if os.path.exists('/tmp/.X%d-lock' % n): continue
        s = socket.socket()
        try: s.bind(('127.0.0.1', 6000 + n)); return n
        except OSError: continue
        finally: s.close()
    raise RuntimeError('no free X display number')


def start_xvfb():
    """a private Xvfb; under WSL on TCP only (WSLg's /tmp/.X11-unix refuses or hangs connections)"""
    if not shutil.which('Xvfb'): return None, None
    n = free_display()
    wsl = 'microsoft' in open('/proc/version').read().lower()
    args = ['Xvfb', ':%d' % n, '-screen', '0', '1024x768x24', '-nolisten', 'unix', '-listen', 'tcp'] if wsl else \
           ['Xvfb', ':%d' % n, '-screen', '0', '1024x768x24']
    p = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    time.sleep(1.5)
    return p, ('127.0.0.1:%d' % n if wsl else ':%d' % n)


def choose_display(arg):
    if arg: return arg, None, 'given'
    d = os.environ.get('DISPLAY')
    if d and probe_display(d): return d, None, 'from the environment'
    if not d and probe_display(None): return None, None, 'none: the emulator starts headless'
    p, d2 = start_xvfb()
    if p and probe_display(d2): return d2, p, 'a private Xvfb (pid %d)' % p.pid
    if p: p.kill()
    raise SystemExit('testrun: no X display the emulator can open (DISPLAY=%s) and no working Xvfb' % d)


# ---- processes
def session_procs():
    """{session id: [cpu ticks of each process]} for all processes"""
    out = {}
    for pid in os.listdir('/proc'):
        if not pid.isdigit(): continue
        try: s = open('/proc/%s/stat' % pid).read()
        except OSError: continue
        f = s[s.rindex(')') + 2:].split()
        out.setdefault(int(f[3]), []).append((int(pid), sum(int(x) for x in f[11:15])))
    return out


def kill_session(sid):
    try: os.killpg(sid, signal.SIGKILL)
    except OSError: pass
    for pid, _ in session_procs().get(sid, []):
        try: os.kill(pid, signal.SIGKILL)
        except OSError: pass


class Run:
    def __init__(self, t, attempt, display, args):
        self.t, self.attempt = t, attempt
        root = ROOT                         # (the command's paths: the program's names its tree, build/cheat/...)
        self.work = os.path.join(OUT, 'work', t.safe()); rmtree_safe(self.work); os.makedirs(self.work)
        if t.isolation == 'scratch': root = make_scratch(t, os.path.join(OUT, 'scratch', t.safe()))
        self.cmd = [PY] + [os.path.join(root, c) if os.path.exists(os.path.join(root, c)) else c for c in t.cmd[1:]]
        self.log = os.path.join(OUT, 'logs', t.safe() + '.log')
        f = open(self.log, 'w' if attempt == 1 else 'a')
        f.write('# %s (attempt %d)\n# cd %s\n# %s%s\n' % (t.id, attempt, self.work, ''.join('%s=%s ' % kv for kv in t.env.items()),
                                                         ' '.join(self.cmd))); f.flush()
        env = dict(os.environ, PYTHONUNBUFFERED='1', **t.env)
        if display: env['DISPLAY'] = display
        self.t0 = time.time()
        self.p = subprocess.Popen(self.cmd, cwd=self.work, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                  env=env, start_new_session=True)
        f.close()
        self.size, self.cpu, self.active, self.sampled = 0, 0, self.t0, self.t0
        self.timeout = max(3 * args.expect(t), 300 if args.measured(t) else 1800)    # (a guess only: 30 min at least)

    def watch(self, procs, now, idle):
        """None while it runs normally, else 'hang' or 'timeout' (the processes are killed)"""
        size = os.path.getsize(self.log)
        cpu = sum(c for _, c in procs.get(self.p.pid, [])) / CLK_TCK
        if size != self.size or cpu - self.cpu > IDLE_CPU * (now - self.sampled): self.active = now
        self.size, self.cpu, self.sampled = size, cpu, now
        why = 'hang' if now - self.active > idle else 'timeout' if now - self.t0 > self.timeout else None
        if why: kill_session(self.p.pid); self.p.wait()
        return why


# ---- main
def select(tiers, args):
    """the tier's tests (tier check: the affected ones and the earlier failures), and a line saying why"""
    if args.tier == 'smoke': return list(tiers['smoke']), ''
    if args.tier == 'pr':
        return [t for t in tiers['pr'] if args.part == 'all' or 'pr:' + args.part in t.tags], ''
    if args.tier in ('all', 'full'): return list(tiers['full']), ''
    if args.base: base, how = git('rev-parse', '--verify', args.base + '^{commit}').strip(), args.base
    else: base, how = default_base()
    changed = changed_files(base)
    failed = load_json(os.path.join(OUT, 'failed.json'), {})
    sel = []; why = {}
    for t in tiers['full']:
        a = affected(t, changed)
        if a or t.id in failed:
            sel.append(t); why[t.id] = a[0] if a else 'failed: %s' % failed[t.id]
    args.why = why
    return sel, 'base %s (%s): %d changed files, %d of %d tests affected or failed before' % (
        base[:10], how, len(changed), len(sel), len(tiers['full']))


def prerequisites(sel, args):
    """the build: make ci-build (unless --no-build), then the build steps the selected tests need (the cheat tree, the
    M3 programs: the 'make' steps before them in their parts)"""
    steps = [] if args.no_build else [['make', '-s', 'ci-build']]
    for t in sel:
        for m in t.make:
            if m not in steps: steps.append(m)
    log = os.path.join(OUT, 'logs', '_build.log')
    with open(log, 'w') as f:
        for c in steps:
            t0 = time.time(); f.write('# %s\n' % ' '.join(c)); f.flush()
            rc = subprocess.run(c, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT).returncode
            print('%-44s %-7s %6.0f s' % ('(build) ' + ' '.join(c[2:]), 'ok' if rc == 0 else 'FAILED', time.time() - t0), flush=True)
            if rc: raise SystemExit('testrun: the build failed, see %s' % log)


def main():
    ap = argparse.ArgumentParser(description='the local regression runner (docs/ci.md)')
    ap.add_argument('--tier', default='check', choices=('check', 'smoke', 'all', 'full', 'pr'))
    ap.add_argument('--base', help='tier check: the commit the changes are counted from (default: the merge base with origin/main)')
    ap.add_argument('--part', default='all', help='tier pr: one CI job\'s part (a, b, c, d)')
    ap.add_argument('-j', '--jobs', type=int, default=max(1, (os.cpu_count() or 2) // 2))
    ap.add_argument('-k', action='append', default=[], help='only the tests whose id contains this (repeatable)')
    ap.add_argument('--no-cache', action='store_true', help='run every selected test (the passes are still recorded)')
    ap.add_argument('--no-build', action='store_true', help='skip make ci-build (the steps the tests need still run)')
    ap.add_argument('--list', action='store_true', help='list the selected tests, run nothing')
    ap.add_argument('--explain', metavar='ID', help='the inputs of one test and its cache key')
    ap.add_argument('--display'); ap.add_argument('--idle', type=float, default=120)
    args = ap.parse_args(); args.why = {}
    tiers = registry()
    measured = load_json(os.path.join(OUT, 'times.json'), {})
    args.measured = lambda t: measured.get(t.id)
    args.expect = lambda t: args.measured(t) or t.expect0
    if args.explain:
        t = [t for ts in tiers.values() for t in ts if t.id == args.explain]
        if not t: raise SystemExit('no test %r (see --list)' % args.explain)
        t = t[0]
        print('command: %s%s' % (''.join('%s=%s ' % kv for kv in t.env.items()), ' '.join(['python3'] + t.cmd[1:])))
        print('tiers: %s; build steps: %s' % (' '.join(sorted(t.tags)), ', '.join(' '.join(m) for m in t.make) or '-'))
        print('sources of its build artefacts: %s' % ' '.join(t.src))
        for k, v in inputs(t): print('%-64s %s' % (k, v[:16]))
        print('key', cache_key(t)); return
    sel, note = select(tiers, args)
    if args.k: sel = [t for t in sel if any(k in t.id for k in args.k)]
    sel.sort(key=lambda t: -args.expect(t))
    if note: print(note, flush=True)
    if args.list:
        for t in sel:
            print('%-44s %6.0f s  %-7s %s%s' % (t.id, args.expect(t), t.isolation, ' '.join(sorted(t.tags)),
                                                 '  <- %s' % args.why[t.id] if t.id in args.why else ''))
        print('%d tests, %.0f s serial' % (len(sel), sum(args.expect(t) for t in sel))); return
    if not sel:
        print('ok: nothing to run'); save_json(os.path.join(OUT, 'last.json'), dict(tier=args.tier, note=note, results=[]))
        return
    no_cache = args.no_cache or args.tier == 'full'
    for d in ('logs', 'work', 'scratch'): os.makedirs(os.path.join(OUT, d), exist_ok=True)
    T0 = time.time()
    prerequisites(sel, args)
    cache = load_json(os.path.join(OUT, 'cache.json'), {})
    failed = load_json(os.path.join(OUT, 'failed.json'), {})
    results = {}; pending = []
    n_total = len(sel); done = [0]
    def report(t, status, secs, attempts=1, key=None):
        done[0] += 1
        results[t.id] = dict(id=t.id, status=status, seconds=round(secs, 1), attempts=attempts, key=key,
                             log=os.path.relpath(os.path.join(OUT, 'logs', t.safe() + '.log'), ROOT))
        if status in ('pass', 'cached'): failed.pop(t.id, None)
        elif status in ('fail', 'hung', 'timeout'): failed[t.id] = status
        print('[%3d/%d] %-44s %-7s %7.1f s%s' % (done[0], n_total, t.id, status, secs, '' if attempts == 1 else '  (attempt %d)' % attempts), flush=True)
    for t in sel:
        key = cache_key(t)
        if not no_cache and key in [c['key'] for c in cache.get(t.id, [])]: report(t, 'cached', 0, key=key); continue
        pending.append((t, 1, key))
    display, xvfb, how = (None, None, '') if not pending else choose_display(args.display)
    if pending: print('display %s (%s); %d to run, %d jobs' % (display, how, len(pending), args.jobs), flush=True)
    running, locks = [], set()
    try:
        last_watch = 0
        while pending or running:
            while len(running) < args.jobs:
                nxt = next((x for x in pending if x[0].lock is None or x[0].lock not in locks), None)
                if nxt is None: break
                pending.remove(nxt); t, attempt, key = nxt
                if t.lock: locks.add(t.lock)
                running.append((Run(t, attempt, display, args), key))
            time.sleep(1)
            now = time.time(); procs = session_procs() if now - last_watch >= 10 else None
            if procs is not None: last_watch = now
            for r, key in list(running):
                rc = r.p.poll(); why = None
                if rc is None and procs is not None: why = r.watch(procs, now, args.idle)
                if rc is None and why is None: continue
                running.remove((r, key)); t = r.t; secs = time.time() - r.t0
                if t.lock: locks.discard(t.lock)
                if why == 'hang' and r.attempt == 1:
                    open(r.log, 'a').write('\n# testrun: idle for %.0f s: killed, running it again\n' % args.idle)
                    print('        %-44s idle %.0f s: killed, retrying' % (t.id, args.idle), flush=True)
                    pending.insert(0, (t, 2, key)); continue
                status = {'hang': 'hung', 'timeout': 'timeout'}.get(why) or ('pass' if rc == 0 else 'fail')
                if why: open(r.log, 'a').write('\n# testrun: %s after %.0f s\n' % (status, secs))
                if status in ('pass', 'fail'): measured[t.id] = round(secs)
                if status == 'pass':
                    cache[t.id] = ([c for c in cache.get(t.id, []) if c['key'] != key] + [dict(key=key, seconds=round(secs), when=time.strftime('%Y-%m-%d %H:%M'))])[-4:]
                    save_json(os.path.join(OUT, 'cache.json'), cache)
                    rmtree_safe(r.work)
                    if t.isolation == 'scratch': rmtree_safe(os.path.join(OUT, 'scratch', t.safe()))
                report(t, status, secs, r.attempt, key)
    except KeyboardInterrupt:
        for r, _ in running: kill_session(r.p.pid)
        print('\ninterrupted'); pending = []
        for r, key in running: report(r.t, 'killed', time.time() - r.t0, r.attempt, key)
    finally:
        if xvfb:                    # (SIGTERM: Xvfb removes its /tmp/.X<n>-lock)
            xvfb.terminate()
            try: xvfb.wait(5)
            except subprocess.TimeoutExpired: xvfb.kill()
        save_json(os.path.join(OUT, 'times.json'), measured)
        save_json(os.path.join(OUT, 'failed.json'), failed)
    wall = time.time() - T0
    res = [results[t.id] for t in sel if t.id in results]
    save_json(os.path.join(OUT, 'last.json'), dict(tier=args.tier, note=note, jobs=args.jobs, no_cache=no_cache, display=display,
                                                   started=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(T0)), wall=round(wall), results=res))
    # the summary: per program (the id's first word)
    groups = {}
    for r in res:
        g = groups.setdefault(r['id'].split()[0], dict(n=0, s=0.0))
        g['n'] += 1; g['s'] += r['seconds']; g[r['status']] = g.get(r['status'], 0) + 1
    cols = ('pass', 'cached', 'fail', 'hung', 'timeout', 'killed')
    print('\n%-18s %5s ' % ('program', 'tests') + ' '.join('%7s' % c for c in cols) + ' %9s' % 'test-s')
    for name, g in sorted(groups.items()):
        print('%-18s %5d ' % (name, g['n']) + ' '.join('%7s' % (g.get(c) or '') for c in cols) + ' %9.0f' % g['s'])
    tot = {c: sum(1 for r in res if r['status'] == c) for c in cols}
    print('%-18s %5d ' % ('total', len(res)) + ' '.join('%7s' % (tot[c] or '') for c in cols) +
          ' %9.0f' % sum(r['seconds'] for r in res))
    bad = [r for r in res if r['status'] in ('fail', 'hung', 'timeout', 'killed')]
    for r in bad: print('  %-8s %-44s %s' % (r['status'].upper(), r['id'], r['log']))
    print('%s: %d tests in %.0f s wall (%d jobs)%s; build/testrun/last.json' % (
        'FAILED' if bad else 'ok', len(res), wall, args.jobs, ', no cache' if no_cache else ''))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
