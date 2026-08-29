"""Establish the weekly poll rate and the register's real storage cost, on clean
infrastructure.

These are the two open risks before the freeze. §10 records the first and leaves
it explicitly unresolved. The second is not recorded as a risk at all, which is
why it is measured here: §10.4's storage plan rests on a 30-package sample giving
2.2 KB and 103 versions per package, and if that figure is low the "gzipped files
in git" verdict changes.

WHY THIS CANNOT RUN LOCALLY. The clean local figure — 0.85 s/package, zero 429s —
was taken before this project had made heavy use of the API. After sustained
querying the same machine measured 0.77-1.06 packages/second with 643-931 429s in
a single 400-package sample. That is a measurement of the penalty box, not of
npm, and neither figure transfers to a runner with a different IP.

WHAT IT MEASURES

1. Concurrency. The poll's cost is dominated by concurrency, not by npm's rate:
   a single request takes ~1.6 s, so 40,000 of them are ~18 core-hours and the
   only question is how many can run at once before npm starts returning 429.
   A probe that tests one worker count answers the wrong question. This sweeps
   several and reports the highest that stays clean, because that — not a
   s/package figure — is the number the collector needs.

2. Response size. Sampled across the rank order and reported as a distribution,
   since the mean is dragged by a long tail: rank-1 packages carry hundreds of
   published versions, rank-39,000 ones carry a handful.

Each concurrency level draws a DISJOINT slice of the frame, so a later level
cannot be flattered by npm's cache warmed by an earlier one. Every slice is
strided across the whole rank order rather than taken from the head.

Output feeds scripts/prefreeze_report.py:

    HALFLIFE_POLL_PROVEN_SECONDS=<s per pkg> python scripts/prefreeze_report.py
"""
import argparse, json, os, statistics, sys, threading, time
import urllib.request, urllib.parse, urllib.error
from concurrent.futures import ThreadPoolExecutor

UA = {'User-Agent': 'halflife-probe/1.0'}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RANKED = os.path.join(ROOT, 'frame', 'frame_ranked.json')
ENDPOINT = 'https://api.npmjs.org/versions/%s/last-week'

CEILING_H = 6.0         # GitHub Actions job ceiling
TARGET_H = 5.0          # what the poll must fit inside, leaving an hour to commit

# A probe of a few hundred packages does not run long enough to provoke the
# throttling a four-hour poll will. The projection is inflated by this factor so
# the freeze is decided on a pessimistic number. §10 requires the frame to be cut
# by rank BEFORE the first snapshot, and that decision cannot be revisited later
# without throwing away the pre-period it was meant to protect.
THROTTLE_MARGIN = 1.5

# §10.4's storage plan, for comparison against what is actually measured.
PREREG_KB_PER_PKG = 2.2
PREREG_VERSIONS = 103
PREREG_GZ_GB_YEAR = 0.25
GZIP_RATIO = 0.18       # gzipped NDJSON of this shape, measured on the sample


class Level:
    """One concurrency level's result."""

    def __init__(self, workers):
        self.workers = workers
        self.lock = threading.Lock()
        self.latencies = []
        self.sizes = []
        self.versions = []
        self.ok = 0
        self.http429 = 0
        self.http404 = 0
        self.errors = 0
        self.elapsed = 0.0

    @property
    def per_pkg(self):
        return self.elapsed / max(self.ok + self.http404 + self.errors + self.http429, 1)

    @property
    def clean(self):
        return self.http429 == 0


def fetch(pkg, lv):
    url = ENDPOINT % urllib.parse.quote(pkg, safe='@')
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
        dt = time.time() - t0
        body = json.loads(raw.decode('utf-8'))
        nver = len(body.get('downloads') or {})
        with lv.lock:
            lv.ok += 1
            lv.latencies.append(dt)
            lv.sizes.append(len(raw))
            lv.versions.append(nver)
    except urllib.error.HTTPError as e:
        with lv.lock:
            if e.code == 429:
                lv.http429 += 1
            elif e.code == 404:
                lv.http404 += 1
            else:
                lv.errors += 1
    except Exception:
        with lv.lock:
            lv.errors += 1


def run_level(workers, sample):
    lv = Level(workers)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda p: fetch(p, lv), sample))
    lv.elapsed = time.time() - t0
    return lv


def pct(xs, p):
    if not xs:
        return 0
    s = sorted(xs)
    return s[min(int(len(s) * p), len(s) - 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--per-level', type=int, default=400,
                    help='packages sampled at each concurrency level')
    ap.add_argument('--workers', default='2,4,8,16',
                    help='comma-separated concurrency levels to sweep')
    ap.add_argument('--json-out', default='')
    args = ap.parse_args()

    levels = [int(w) for w in args.workers.split(',') if w.strip()]
    frame = json.load(open(RANKED, encoding='utf-8'))
    packages = frame['packages']
    N = len(packages)

    need = args.per_level * len(levels)
    if need > N:
        print('REFUSING: %d levels x %d packages exceeds the %s-package frame.'
              % (len(levels), args.per_level, '{:,}'.format(N)))
        return 2

    # Disjoint, each strided across the whole rank order: level k takes every
    # (need)th package starting at offset k*per_level... equivalently, interleave.
    stride = N / need
    allidx = [int(i * stride) for i in range(need)]
    slices = [allidx[k::len(levels)][:args.per_level] for k in range(len(levels))]

    print('HALFLIFE — POLL PROBE')
    print('=' * 68)
    print('frame          : %s packages' % '{:,}'.format(N))
    print('sweep          : %s workers, %d packages each (disjoint, rank-strided)'
          % (levels, args.per_level))
    print()

    results = []
    for workers, idxs in zip(levels, slices):
        sample = [packages[i] for i in idxs]
        print('  probing %2d workers ...' % workers, end='', flush=True)
        lv = run_level(workers, sample)
        results.append(lv)
        proj_h = lv.per_pkg * N * THROTTLE_MARGIN / 3600
        print('  %.4f s/pkg   429=%-4d err=%-3d   -> %.2f h full frame'
              % (lv.per_pkg, lv.http429, lv.errors, proj_h), flush=True)

    print()
    print('CONCURRENCY')
    print('  %-8s %-11s %-7s %-6s %-6s %-11s %s'
          % ('workers', 's/pkg', '429', 'err', '404', 'proj (h)', 'verdict'))
    for lv in results:
        proj_h = lv.per_pkg * N * THROTTLE_MARGIN / 3600
        if not lv.clean:
            verdict = 'THROTTLED'
        elif proj_h < TARGET_H:
            verdict = 'FITS'
        else:
            verdict = 'too slow'
        print('  %-8d %-11.4f %-7d %-6d %-6d %-11.2f %s'
              % (lv.workers, lv.per_pkg, lv.http429, lv.errors, lv.http404, proj_h, verdict))

    usable = [lv for lv in results if lv.clean and lv.per_pkg * N * THROTTLE_MARGIN / 3600 < TARGET_H]
    best = min(usable, key=lambda lv: lv.per_pkg) if usable else None

    # Response size — pooled across every level, since it does not depend on
    # concurrency. Reported as a distribution: the mean is dragged by the head of
    # the rank order and on its own would misstate the storage cost.
    sizes = [s for lv in results for s in lv.sizes]
    versions = [v for lv in results for v in lv.versions]
    mean_kb = statistics.mean(sizes) / 1024 if sizes else 0
    raw_wk_mb = mean_kb * N / 1024
    gz_gb_yr = raw_wk_mb * 52 * GZIP_RATIO / 1024

    print()
    print('RESPONSE SIZE  (n=%s, pooled)' % '{:,}'.format(len(sizes)))
    print('  bytes p50/p90/p99 : %s / %s / %s'
          % ('{:,}'.format(pct(sizes, .50)), '{:,}'.format(pct(sizes, .90)),
             '{:,}'.format(pct(sizes, .99))))
    print('  mean              : %.1f KB, %.0f versions   (§10.4 assumed %.1f KB, %d versions)'
          % (mean_kb, statistics.mean(versions) if versions else 0,
             PREREG_KB_PER_PKG, PREREG_VERSIONS))
    print()
    print('STORAGE PROJECTION  (PREREGISTRATION.md §10.4)')
    print('  raw per week      : %.0f MB      (§10.4 says 27 MB)' % raw_wk_mb)
    print('  gzipped per year  : %.2f GB     (§10.4 says %.2f GB)' % (gz_gb_yr, PREREG_GZ_GB_YEAR))
    storage_ok = gz_gb_yr <= PREREG_GZ_GB_YEAR * 1.5
    if not storage_ok:
        print('  §10.4 UNDERSTATES STORAGE by %.1fx. Its "gzipped files in git: Fits"'
              % (gz_gb_yr / PREREG_GZ_GB_YEAR))
        print('  verdict was reached on a 30-package sample. GitHub warns above 1 GB')
        print('  and soft-limits around 5 GB, and gzipped blobs do not delta-compress,')
        print('  so year-two is the same cost again. The compaction plan §10 defers')
        print('  is load-bearing sooner than §10.4 implies and must be amended before')
        print('  the freeze, not after.')
    else:
        print('  §10.4 storage plan holds.')

    print()
    print('=' * 68)
    if best is None:
        print('VERDICT: no probed concurrency fits the %s-package frame.' % '{:,}'.format(N))
        clean = [lv for lv in results if lv.clean]
        rate = min(clean, key=lambda lv: lv.per_pkg).per_pkg if clean else results[0].per_pkg
        print()
        print('§10 requires reduction by RANK, before the first snapshot, never by')
        print('dropping individual packages. At the best clean rate (%.4f s/pkg):' % rate)
        for size, capture in ((30000, 65.2), (20000, 49.6), (12000, 46.4), (5000, 35.1)):
            h = rate * size * THROTTLE_MARGIN / 3600
            print('  %s  top %-7s %.2f h   %.1f%% advisory capture'
                  % ('FITS' if h < TARGET_H else 'no  ', '{:,}'.format(size), h, capture))
    else:
        print('VERDICT: the %s-package frame fits at %d workers.'
              % ('{:,}'.format(N), best.workers))
        print('  %.4f s/pkg -> %.2f h with the %.1fx margin (target %.0f h, ceiling %.0f h)'
              % (best.per_pkg, best.per_pkg * N * THROTTLE_MARGIN / 3600,
                 THROTTLE_MARGIN, TARGET_H, CEILING_H))
        print()
        print('Next:')
        print('  HALFLIFE_POLL_PROVEN_SECONDS=%.4f python scripts/prefreeze_report.py'
              % best.per_pkg)
        print('  and set --workers %d in .github/workflows/collect.yml' % best.workers)
    print('=' * 68)

    if args.json_out:
        json.dump({
            'frame_size': N,
            'per_level': args.per_level,
            'throttle_margin': THROTTLE_MARGIN,
            'target_hours': TARGET_H,
            'levels': [{
                'workers': lv.workers,
                'seconds_per_package': round(lv.per_pkg, 5),
                'elapsed_seconds': round(lv.elapsed, 2),
                'ok': lv.ok, 'http_429': lv.http429, 'http_404': lv.http404,
                'errors': lv.errors,
                'latency_p50': round(pct(lv.latencies, .50), 3),
                'latency_p95': round(pct(lv.latencies, .95), 3),
                'projected_hours': round(lv.per_pkg * N * THROTTLE_MARGIN / 3600, 3),
                'clean': lv.clean,
            } for lv in results],
            'best_workers': best.workers if best else None,
            'seconds_per_package': round(best.per_pkg, 5) if best else None,
            'fits': best is not None,
            'response_bytes_mean': round(statistics.mean(sizes), 1) if sizes else 0,
            'response_bytes_p50': pct(sizes, .50),
            'response_bytes_p99': pct(sizes, .99),
            'versions_mean': round(statistics.mean(versions), 1) if versions else 0,
            'raw_mb_per_week': round(raw_wk_mb, 1),
            'gz_gb_per_year': round(gz_gb_yr, 3),
            'storage_matches_prereg': storage_ok,
        }, open(args.json_out, 'w', encoding='utf-8'), indent=1)
        print('\nwrote %s' % args.json_out)

    return 0 if best else 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
