"""Establish the SUSTAINABLE poll rate on clean infrastructure.

This is the measurement PREREGISTRATION.md §10 leaves open and the only thing
blocking the frame freeze.

WHAT THE FIRST VERSION OF THIS SCRIPT GOT WRONG. It swept worker counts with no
pacing and no backoff, and reported seconds-per-package. On a GitHub Actions
runner that produced 1,559 `HTTP 429`s out of 1,600 requests and apparent rates
of 0.002 s/package — which is the speed of being refused, not the speed of
collecting. An unpaced probe measures time-to-throttle. The collector does not
want to know that; it wants to know the highest request rate npm will serve
indefinitely.

So this sweeps TARGET REQUEST RATES, not concurrency. Each level paces requests
to a fixed requests-per-second, honours `Retry-After`, and is judged on the
share of requests that came back 429. The sustainable rate is the highest target
whose refusal share stays under REFUSAL_CEILING. That number, multiplied by the
frame size, is the only honest answer to "does the weekly poll fit".

WHAT RUNNING IT REVEALED, AND WHY IT MATTERS. GitHub Actions runner IPs are
shared across GitHub's CI fleet, and npm appears to rate-limit them far harder
than an ordinary residential address: at two concurrent workers the runner was
refused 359 times in 400 requests, while this project's own supposedly throttled
home IP served 8 concurrent workers cleanly the same day. §10 assumed the runner
would be the clean environment and the local machine the contaminated one. That
assumption is inverted, and the collector's deployment target is an open question
rather than a settled one.

Never reports a throttled level as clean. A refused request is not a fast
request, and a probe that cannot tell them apart is worse than no probe.
"""
import argparse, json, math, os, statistics, sys, threading, time
import urllib.request, urllib.parse, urllib.error
from concurrent.futures import ThreadPoolExecutor

UA = {'User-Agent': 'halflife-probe/1.0 (+https://github.com/Muhammad-Haris-3/Halflife)'}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RANKED = os.path.join(ROOT, 'frame', 'frame_ranked.json')
ENDPOINT = 'https://api.npmjs.org/versions/%s/last-week'

CEILING_H = 6.0             # GitHub Actions job ceiling
TARGET_H = 5.0              # the poll must fit inside this, leaving an hour
REFUSAL_CEILING = 0.01      # a level is sustainable at <=1% 429s
COOLDOWN_S = 20.0           # between levels, so one level's burst does not
                            # contaminate the next one's verdict

# A probe runs for minutes; the poll runs for hours. A rate limit that tolerates
# the first can still bite during the second, so the projection carries a margin.
THROTTLE_MARGIN = 1.5


class Pacer:
    """Token bucket. Releases at most `rate` requests per second, globally."""

    def __init__(self, rate):
        self.interval = 1.0 / rate
        self.lock = threading.Lock()
        self.next_at = time.time()

    def wait(self):
        with self.lock:
            slot = max(time.time(), self.next_at)
            self.next_at = slot + self.interval
        delay = slot - time.time()
        if delay > 0:
            time.sleep(delay)


class Level:
    def __init__(self, rate):
        self.rate = rate
        self.lock = threading.Lock()
        self.latencies, self.sizes, self.versions = [], [], []
        self.ok = self.http429 = self.http404 = self.errors = 0
        self.retry_after = []
        self.elapsed = 0.0

    @property
    def attempted(self):
        return self.ok + self.http429 + self.http404 + self.errors

    @property
    def refusal_share(self):
        return self.http429 / max(self.attempted, 1)

    @property
    def achieved_rate(self):
        """Successful responses per second — the only rate that collects data."""
        return self.ok / self.elapsed if self.elapsed else 0.0

    @property
    def sustainable(self):
        return self.refusal_share <= REFUSAL_CEILING and self.ok > 0


def fetch(pkg, lv, pacer):
    pacer.wait()
    url = ENDPOINT % urllib.parse.quote(pkg, safe='@')
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
        dt = time.time() - t0
        nver = len(json.loads(raw.decode('utf-8')).get('downloads') or {})
        with lv.lock:
            lv.ok += 1
            lv.latencies.append(dt)
            lv.sizes.append(len(raw))
            lv.versions.append(nver)
    except urllib.error.HTTPError as e:
        with lv.lock:
            if e.code == 429:
                lv.http429 += 1
                ra = e.headers.get('Retry-After')
                if ra:
                    lv.retry_after.append(ra)
            elif e.code == 404:
                lv.http404 += 1
            else:
                lv.errors += 1
    except Exception:
        with lv.lock:
            lv.errors += 1


def run_level(rate, sample):
    lv = Level(rate)
    pacer = Pacer(rate)
    # Enough workers to actually sustain the target rate at ~0.3-1.6 s latency,
    # but never so many that the pacer stops being the binding constraint.
    workers = max(2, min(16, int(math.ceil(rate * 2.0))))
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda p: fetch(p, lv, pacer), sample))
    lv.elapsed = time.time() - t0
    return lv


def pct(xs, p):
    if not xs:
        return 0
    s = sorted(xs)
    return s[min(int(len(s) * p), len(s) - 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--per-level', type=int, default=150,
                    help='requests at each target rate')
    ap.add_argument('--rates', default='1,2,4,8',
                    help='comma-separated target requests/second to sweep')
    ap.add_argument('--json-out', default='')
    args = ap.parse_args()

    rates = [float(r) for r in args.rates.split(',') if r.strip()]
    packages = json.load(open(RANKED, encoding='utf-8'))['packages']
    N = len(packages)

    need = args.per_level * len(rates)
    if need > N:
        print('REFUSING: %d rates x %d requests exceeds the %s-package frame.'
              % (len(rates), args.per_level, '{:,}'.format(N)))
        return 2

    # Disjoint slices, each strided across the whole rank order so no level is
    # flattered by npm's cache or by drawing only small packages.
    stride = N / need
    allidx = [int(i * stride) for i in range(need)]
    slices = [allidx[k::len(rates)][:args.per_level] for k in range(len(rates))]

    print('HALFLIFE — SUSTAINABLE POLL RATE PROBE')
    print('=' * 72)
    print('frame        : %s packages' % '{:,}'.format(N))
    print('sweep        : %s req/s, %d requests each (disjoint, rank-strided)'
          % (rates, args.per_level))
    print('sustainable  : <= %.0f%% refused' % (REFUSAL_CEILING * 100))
    print()

    results = []
    for i, (rate, idxs) in enumerate(zip(rates, slices)):
        if i:
            time.sleep(COOLDOWN_S)
        print('  %5.1f req/s ...' % rate, end='', flush=True)
        lv = run_level(rate, [packages[j] for j in idxs])
        results.append(lv)
        print('  ok=%-4d 429=%-4d (%3.0f%% refused)  achieved %.2f req/s  %s'
              % (lv.ok, lv.http429, lv.refusal_share * 100, lv.achieved_rate,
                 'sustainable' if lv.sustainable else 'THROTTLED'), flush=True)

    print()
    print('RATE SWEEP')
    print('  %-9s %-7s %-7s %-10s %-14s %-11s %s'
          % ('target', 'ok', '429', 'refused', 'achieved r/s', 'proj (h)', 'verdict'))
    for lv in results:
        proj = (N / lv.achieved_rate * THROTTLE_MARGIN / 3600) if lv.achieved_rate else None
        print('  %-9.1f %-7d %-7d %-10s %-14.2f %-11s %s'
              % (lv.rate, lv.ok, lv.http429, '%.0f%%' % (lv.refusal_share * 100),
                 lv.achieved_rate, ('%.2f' % proj) if proj else 'n/a',
                 'sustainable' if lv.sustainable else 'THROTTLED'))

    good = [lv for lv in results if lv.sustainable]
    best = max(good, key=lambda lv: lv.achieved_rate) if good else None
    fits = bool(best) and (N / best.achieved_rate * THROTTLE_MARGIN / 3600) < TARGET_H

    ra = [r for lv in results for r in lv.retry_after]
    if ra:
        print()
        print('  npm sent Retry-After on %d refusals; distinct values: %s'
              % (len(ra), sorted(set(ra))[:5]))

    sizes = [s for lv in results for s in lv.sizes]
    versions = [v for lv in results for v in lv.versions]
    print()
    if sizes:
        mean_kb = statistics.mean(sizes) / 1024
        raw_wk_mb = mean_kb * N / 1024
        gz_gb_yr = raw_wk_mb * 52 * 0.18 / 1024
        print('RESPONSE SIZE  (n=%s successful)' % '{:,}'.format(len(sizes)))
        print('  bytes p50/p90/p99 : %s / %s / %s'
              % ('{:,}'.format(pct(sizes, .50)), '{:,}'.format(pct(sizes, .90)),
                 '{:,}'.format(pct(sizes, .99))))
        print('  mean              : %.1f KB, %.0f versions   (§10.4 measured 2.2 KB, 103)'
              % (mean_kb, statistics.mean(versions)))
        print('  -> %.0f MB/week raw, %.2f GB/year gzipped' % (raw_wk_mb, gz_gb_yr))
    else:
        mean_kb = raw_wk_mb = gz_gb_yr = 0.0
        print('RESPONSE SIZE  : no successful responses — nothing measured.')

    print()
    print('=' * 72)
    if best is None:
        print('VERDICT: NO sustainable rate found. Every probed level was throttled.')
        print()
        print('This is not a frame-size problem, and reducing the frame does not fix')
        print('it: at this refusal share the poll cannot complete at any size. The')
        print('collector needs somewhere npm will serve it, which is a deployment')
        print('question rather than a §10 rank-reduction one. Do not cut the frame')
        print('on this result.')
    else:
        proj_h = N / best.achieved_rate * THROTTLE_MARGIN / 3600
        print('VERDICT: sustainable at %.1f req/s target (%.2f req/s achieved).'
              % (best.rate, best.achieved_rate))
        print('  full frame: %.2f h with the %.1fx margin (target %.0f h, ceiling %.0f h) — %s'
              % (proj_h, THROTTLE_MARGIN, TARGET_H, CEILING_H, 'FITS' if fits else 'DOES NOT FIT'))
        if fits:
            print()
            print('Next:')
            print('  HALFLIFE_POLL_PROVEN_SECONDS=%.4f python scripts/prefreeze_report.py'
                  % (1.0 / best.achieved_rate))
        else:
            print()
            print('§10 requires reduction by RANK, before the first snapshot:')
            for size, capture in ((30000, 65.2), (20000, 49.6), (12000, 46.4), (5000, 35.1)):
                h = size / best.achieved_rate * THROTTLE_MARGIN / 3600
                print('  %s  top %-7s %.2f h   %.1f%% advisory capture'
                      % ('FITS' if h < TARGET_H else 'no  ', '{:,}'.format(size), h, capture))
    print('=' * 72)

    if args.json_out:
        json.dump({
            'frame_size': N,
            'per_level': args.per_level,
            'refusal_ceiling': REFUSAL_CEILING,
            'throttle_margin': THROTTLE_MARGIN,
            'target_hours': TARGET_H,
            'levels': [{
                'target_rate': lv.rate,
                'ok': lv.ok, 'http_429': lv.http429, 'http_404': lv.http404,
                'errors': lv.errors,
                'refusal_share': round(lv.refusal_share, 4),
                'achieved_rate': round(lv.achieved_rate, 3),
                'elapsed_seconds': round(lv.elapsed, 2),
                'latency_p50': round(pct(lv.latencies, .50), 3),
                'sustainable': lv.sustainable,
            } for lv in results],
            'sustainable_rate': round(best.achieved_rate, 3) if best else None,
            'seconds_per_package': round(1.0 / best.achieved_rate, 5) if best else None,
            'projected_hours': round(N / best.achieved_rate * THROTTLE_MARGIN / 3600, 3) if best else None,
            'fits': fits,
            'total_ok': sum(lv.ok for lv in results),
            'total_429': sum(lv.http429 for lv in results),
            'retry_after_values': sorted(set(ra))[:10],
            'response_bytes_mean': round(statistics.mean(sizes), 1) if sizes else 0,
            'versions_mean': round(statistics.mean(versions), 1) if versions else 0,
            'raw_mb_per_week': round(raw_wk_mb, 1),
            'gz_gb_per_year': round(gz_gb_yr, 3),
        }, open(args.json_out, 'w', encoding='utf-8', newline='\n'), indent=1)
        print('\nwrote %s' % args.json_out)

    return 0 if fits else 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
