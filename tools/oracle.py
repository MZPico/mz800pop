#!/usr/bin/env python3
"""Run a control script through SDLPoP (external/SDLPoP/prince with the pop-800 hooks) and write the kid trace.
Guards off unless the script has '# guards' or '# guard room:tile:dir:skill:color' lines (then the guard trace lines
'G ...' are written too), seed 12345, patches from the script's '# patch' line, '# sword' = the kid has the sword,
'# state' = the 'S' level-event state lines too, '# time min:tick' = time left at the start, '# start room:pos:dir' =
the kid's start position (first level start), '# sound ticks' = SDLPoP's waits on sound through the ticks model
(POP800_SOUND_TICKS with kidsim's lengths: deterministic instead of real-time audio), '# level1 music' = the level 1
start's music crouch kept (POP800_LEVEL1_MUSIC), '# cheats' = cheats on; a control line's optional
4th field holds keys (bit 0: Ctrl+A, restart the level; bits 3-7: a key code, kidsim KEY_*, through process_key).
usage: oracle.py <level> <script.txt> <trace_out.txt> [--notraps]"""
import os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import kidsim

def run(level, script, out, notraps=False):
    moves, patches = kidsim.read_script(script)
    plain = out + '.script'
    keys = kidsim.read_keys(script)
    open(plain, 'w').write('\n'.join('%d %d %d' % m + (' %d' % k if k else '') for m, k in zip(moves, keys)) + '\n')
    env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', POP800_SEED='12345',
               POP800_SCRIPT=os.path.abspath(plain), POP800_TRACE=os.path.abspath(out), POP800_TRACE_SOUND='1')
    o = kidsim.script_opts(script)
    if o['guards']:
        env['POP800_TRACE_GUARD'] = '1'
        if o['place']: env['POP800_GUARD'] = ','.join('%d:%d:%d:%d:%d' % g for g in o['place'])
    else: env['POP800_NOGUARDS'] = '1'
    if o['sword']: env['POP800_SWORD'] = '1'
    if o['state']: env['POP800_TRACE_STATE'] = '1'
    if o['time']: env['POP800_TIME'] = '%d:%d' % o['time']
    if o['start']: env['POP800_START'] = '%d:%d:%d' % o['start']
    if patches: env['POP800_PATCH'] = kidsim.patch_env(script)
    if notraps: env['POP800_NOTRAPS'] = '1'
    if o['sound'] == 'ticks':
        t12, t10 = kidsim.KidSim.sound_ticks_tables()
        env['POP800_SOUND_TICKS'] = ','.join(map(str, t12)) + ';' + ','.join(map(str, t10))
    elif o['sound'] != 'silent': raise ValueError('the oracle runs the silent (real-time) or the ticks model only')
    if o['level1_music']: env['POP800_LEVEL1_MUSIC'] = '1'
    if not o['cheats'] and any(k >> 3 for k in keys): env['POP800_NOCHEATS'] = '1'   # (`megahit` only picks the level)
    subprocess.run([os.path.join(ROOT, 'external', 'SDLPoP', 'prince'), 'megahit', str(level)], cwd=os.path.join(ROOT, 'external', 'SDLPoP'),
                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
    os.remove(plain)
    return [l for l in open(out).read().split('\n') if l and not l.startswith(('MODS', 'CTRL', 'R '))]   # (kid and 'G' lines)

def compare(level, script, oracle_lines):
    """Compare kidsim with the oracle trace (as tools/oracle_suite.py does: stops 8 kid ticks after a death, SDLPoP's
    death timer waits on sounds). Returns (kidsim line count, [(line, sdlpop, kidsim)] of the first difference)."""
    import oracle_suite
    n, d = oracle_suite.compare_lines(oracle_lines, kidsim.run_script(level, script),
                                      exact=kidsim.script_opts(script)['sound'] == 'ticks')
    return n, [d] if d else []

if __name__ == '__main__':
    lv, script, out = int(sys.argv[1]), sys.argv[2], sys.argv[3]
    lines = run(lv, script, out, '--notraps' in sys.argv)
    n, bad = compare(lv, script, lines)
    print('%s: %d lines, %s' % (os.path.basename(script), n, 'kidsim matches SDLPoP' if not bad else 'first diff at line %d:\n  sdlpop %s\n  kidsim %s' % bad[0]))
