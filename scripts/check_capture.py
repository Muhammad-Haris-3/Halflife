"""Measure what share of real advisories a candidate frame would have caught.

Cross-references frame/frame.json against the 600-advisory sample in
data/pilot/advisory_capture.json (2026-06-18 .. 2026-08-27).

Reported at each depth cutoff so the depth can be chosen on evidence rather
than assumed. This is the last check available before the frame is frozen.
"""
import json, os, sys, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    frame = json.load(open(os.path.join(ROOT, 'frame', 'frame.json'), encoding='utf-8'))
    cap = json.load(open(os.path.join(ROOT, 'data', 'pilot', 'advisory_capture.json'), encoding='utf-8'))

    depth = frame['packages']
    dl = cap['dl']                       # package -> weekly downloads
    advcount = cap['advcount']           # package -> number of advisories
    total_adv = sum(advcount.values())
    advised = list(advcount)

    print('frame: %d packages (seed %d, depth<=%d)' % (len(depth), frame['seed_count'], frame['max_depth']))
    print('advisory sample: %d advisories over %d days, %s..%s'
          % (cap['n_adv'], cap['span_days'], *cap['window']))
    print('  %d distinct advised packages, %d advisory-package pairs' % (len(advised), total_adv))
    print()

    print('CAPTURE BY DEPTH CUTOFF')
    print('-' * 92)
    print('%-8s %10s %12s %14s %14s %12s' % ('depth<=', 'frame size', 'advised in', '% pkgs caught', '% advisories', 'w/ >=10k dl'))
    print('-' * 92)
    for d in range(0, frame['max_depth'] + 1):
        inframe = {p for p, dd in depth.items() if dd <= d}
        hit = [p for p in advised if p in inframe]
        wa = sum(advcount[p] for p in hit)
        big = [p for p in hit if dl.get(p, 0) >= 10000]
        wbig = sum(advcount[p] for p in big)
        print('%-8d %10d %12d %13.1f%% %13.1f%% %11.1f%%'
              % (d, len(inframe), len(hit), 100 * len(hit) / len(advised),
                 100 * wa / total_adv, 100 * wbig / total_adv))
    print('-' * 92)

    # full-depth detail
    inframe = set(depth)
    hit = [p for p in advised if p in inframe]
    missed = [p for p in advised if p not in inframe]
    print()
    print('MISSED ADVISORIES, RANKED BY WEEKLY DOWNLOADS  (frame would not have seen these)')
    print('-' * 78)
    mm = sorted(((dl.get(p, 0), p, advcount[p]) for p in missed), reverse=True)
    for n, p, c in mm[:15]:
        print('  %14s  %-40s %d advisor%s' % ('{:,}'.format(n), p[:40], c, 'y' if c == 1 else 'ies'))
    big_missed = [(n, p, c) for n, p, c in mm if n >= 10000]
    print('-' * 78)
    print('  missed packages with >=10k weekly downloads: %d (%d advisories)'
          % (len(big_missed), sum(c for _, _, c in big_missed)))
    print('  missed packages with 0 downloads (removed/malware): %d'
          % sum(1 for n, _, _ in mm if n == 0))

    print()
    print('CAUGHT, RANKED BY WEEKLY DOWNLOADS')
    print('-' * 78)
    hh = sorted(((dl.get(p, 0), p, advcount[p]) for p in hit), reverse=True)
    for n, p, c in hh[:15]:
        print('  %14s  %-40s depth %d' % ('{:,}'.format(n), p[:40], depth[p]))

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
