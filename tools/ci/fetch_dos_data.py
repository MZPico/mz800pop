#!/usr/bin/env python3
"""Fetch the original DOS Prince of Persia v1.3 data files into external/dos/PRINCE (for CI; docs/ci.md).

The data is never committed and never leaves the job (no artifact, no cache). Source: the archive.org item
`prince-of-persia-mr-abandonware`, file `Prince of Persia.7z`: it holds `Prince of Persia (DOSBox) Installer.exe`, a 7z
self-extractor, which is unpacked with 7z (p7zip-full), never executed. Its paths are base64 of UTF-16-LE per path
component ('QwA=' = 'C'); the folder C/POP/POP13 holds v1.3. Its *.DAT files are copied and checked against the pinned
md5 list tools/ci/dos_data.md5 (made from the local copy the port was developed with): any missing file or mismatch
fails. If the source disappears, point --url (or POP800_DOS_URL) at another copy of the same archive, or --from-dir at a
folder that already holds the files: the md5 list keeps it honest.

usage: fetch_dos_data.py [--url URL] [--from-dir DIR] [--dest external/dos/PRINCE]"""
import argparse, base64, hashlib, os, shutil, subprocess, sys, tempfile, time, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
URL = 'https://archive.org/download/prince-of-persia-mr-abandonware/Prince%20of%20Persia.7z'
ARCHIVE_SIZE = 5482709
ATTEMPTS = 5                    # the download, with 15, 30, 60, 120 s between attempts
INSTALLER = 'Prince of Persia (DOSBox) Installer.exe'
FOLDER = ('C', 'POP', 'POP13')
MD5 = os.path.join(ROOT, 'tools', 'ci', 'dos_data.md5')


def enc(name):
    return base64.b64encode(name.encode('utf-16-le')).decode()


def dec(name):
    try:
        return base64.b64decode(name, validate=True).decode('utf-16-le')
    except Exception:
        return name


def pinned():
    out = {}
    for line in open(MD5):
        if line.strip():
            h, fn = line.split(None, 1)
            out[fn.strip().lstrip('*')] = h
    return out


def md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def seven_zip(*args):
    subprocess.run(['7z', *args], check=True, stdout=subprocess.DEVNULL)


def from_archive(url, tmp):
    arc = os.path.join(tmp, 'pop.7z')
    # archive.org answers parallel CI jobs with an occasional HTTP 5xx / 429 or a dropped connection: retry with backoff
    for attempt in range(1, ATTEMPTS + 1):
        print('downloading', url, '(attempt %d of %d)' % (attempt, ATTEMPTS))
        req = urllib.request.Request(url, headers={'User-Agent': 'pop800-ci'})
        try:
            with urllib.request.urlopen(req, timeout=300) as r, open(arc, 'wb') as f:
                shutil.copyfileobj(r, f)
            break
        except (urllib.error.URLError, OSError) as x:     # (HTTPError is a URLError)
            if isinstance(x, urllib.error.HTTPError) and x.code < 500 and x.code != 429:
                sys.exit('fetch_dos_data: download failed: %s (not retried: the URL is wrong or gone)' % x)
            if attempt == ATTEMPTS: sys.exit('fetch_dos_data: download failed %d times, last: %s' % (ATTEMPTS, x))
            wait = 15 * 2 ** (attempt - 1)
            print('download failed (%s); retrying in %d s' % (x, wait))
            time.sleep(wait)
    size = os.path.getsize(arc)
    if size != ARCHIVE_SIZE:
        print('note: archive is %d bytes (expected %d); the md5 check decides' % (size, ARCHIVE_SIZE))
    seven_zip('x', '-y', '-o' + os.path.join(tmp, 'a'), arc, INSTALLER)
    sfx = os.path.join(tmp, 'a', INSTALLER)
    folder = '/'.join(enc(c) for c in FOLDER)
    seven_zip('x', '-y', '-o' + os.path.join(tmp, 'b'), sfx, folder + '/*')
    src = os.path.join(tmp, 'b', *folder.split('/'))
    if not os.path.isdir(src):
        sys.exit('fetch_dos_data: %s not in the installer' % '/'.join(FOLDER))
    return {dec(n): os.path.join(src, n) for n in os.listdir(src)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--url', default=os.environ.get('POP800_DOS_URL', URL))
    ap.add_argument('--from-dir', help='take the files from this folder instead of downloading')
    ap.add_argument('--dest', default=os.path.join(ROOT, 'external', 'dos', 'PRINCE'))
    a = ap.parse_args()
    want = pinned()
    with tempfile.TemporaryDirectory(prefix='popdos-') as tmp:
        if a.from_dir:
            files = {n: os.path.join(a.from_dir, n) for n in os.listdir(a.from_dir)}
        else:
            files = from_archive(a.url, tmp)
        upper = {n.upper(): p for n, p in files.items()}
        bad = []
        os.makedirs(a.dest, exist_ok=True)
        for fn, h in sorted(want.items()):
            p = upper.get(fn.upper())
            if p is None:
                bad.append('%s: missing' % fn); continue
            got = md5(p)
            if got != h:
                bad.append('%s: md5 %s, expected %s' % (fn, got, h)); continue
            shutil.copyfile(p, os.path.join(a.dest, fn))
    if bad:
        sys.exit('fetch_dos_data: verification failed:\n  ' + '\n  '.join(bad))
    print('%d DOS data files verified (tools/ci/dos_data.md5) -> %s' % (len(want), os.path.relpath(a.dest, ROOT)))


if __name__ == '__main__':
    main()
