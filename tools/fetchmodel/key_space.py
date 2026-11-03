"""the frame cache's full key space per set, from build/assets/<set>.dir (8 bytes an image: page, addr hi, lo, w, h, ...)"""
import os
A = os.path.join(os.path.dirname(__file__), '..', '..', 'build', 'assets')
tot = 0; totn = 0; mx = 0
for s in ('kid', 'sword', 'guard', 'guard_palace', 'fat', 'skel', 'vizier', 'shadow'):
    d = open(os.path.join(A, s + '.dir'), 'rb').read()
    ims = [(d[i + 3], d[i + 4]) for i in range(0, len(d), 8) if d[i + 3] and d[i + 4]]
    cell = sum((w + 1) * 4 * h for w, h in ims)
    raw = sum(w * 4 * h for w, h in ims)
    mx = max([mx] + [(w + 1) * 4 * h for w, h in ims])
    tot += cell * 16 + 4 * 16 * len(ims); totn += 16 * len(ims)
    print('%-13s %3d images (dir %d entries), pack %6.1f KB of planes, all 16 variants %7.1f KB' % (s, len(ims), len(d) // 8, raw / 1024, (cell * 16 + 64 * len(ims)) / 1024))
print('all sets: %d keys, %.0f KB (with a 4-byte header each); the largest entry %d bytes' % (totn, tot / 1024, mx + 4))
