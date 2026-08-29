"""The weekly poll. This is the thing that makes the record exist.

npm publishes the per-version download split for a rolling seven days and
archives nothing (FEASIBILITY.md §1). Every package-week this script fails to
capture is permanently unobtainable — by anyone, including npm. That asymmetry
shapes every decision here: the collector prefers a recorded gap to a silent one,
and never interpolates.

Register layout (PREREGISTRATION.md §10.4) — gzipped files in git, not a
database, because the project's claim is the integrity of a record and a public
commit history is evidence where a database grant is only an assurance:

  data/register/<ISO-week>/snapshot.ndjson.gz   one line per package
  data/register/<ISO-week>/run.json             what happened, including failures

Each snapshot line is {"p": name, "t": unix_observed, "d": {version: downloads}}.
`t` is per package, not per run: a 40,000-package poll spans hours, so the first
and last packages are observed at materially different times and one run-level
timestamp would be a fiction.

Failures are data. Every 429, timeout and error is counted and the affected
package names are written to run.json, so a gap in the register reads as a gap
rather than as an absence (§10). A run that exhausts its retry budget is marked
incomplete and the packages it missed are excluded, never interpolated.

Resumable: safe to kill and re-run inside the same ISO week. Already-captured
packages are skipped, so a run that dies at hour 3 does not repeat hour 1.

Refuses to run before frame/MANIFEST exists. The first snapshot must not precede
the freeze commit, or the frame stops being a rule fixed in advance and becomes a
description of what was already seen.
"""
import argparse, datetime, gzip, json, os, sys, threading, time
import urllib.request, urllib.parse, urllib.error
from concurrent.futures import ThreadPoolExecutor

UA = {'User-Agent': 'halflife-collector/1.0 (+https://github.com/Muhammad-Haris-3/Halflife)'}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAME = os.path.join(ROOT, 'frame')
MANIFEST = os.path.join(FRAME, 'MANIFEST')
RANKED = os.path.join(FRAME, 'frame_ranked.json')
REGISTER = os.path.join(ROOT, 'data', 'register')

ENDPOINT = 'https://api.npmjs.org/versions/%s/last-week'
MAX_TRIES = 5           # per package, then it is recorded as a failure
BACKOFF_BASE = 2.0      # seconds; exponential


class Pacer:
    """Token bucket holding the poll to a measured-sustainable request rate.

    Measured on GitHub Actions runners 2026-08-29: a single egress IP sustains
    0.5 req/s against api.npmjs.org with zero refusals, and is refused 27% of the
    time at 1 req/s. Concurrency alone cannot beat that, so the collector paces
    rather than racing, and buys throughput by sharding across runners instead —
    eight shards measured 4.02 req/s aggregate with zero refusals.
    """

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


class Stats:
    """Counts shared across workers. Every field here ends up in run.json."""

    def __init__(self):
        self.lock = threading.Lock()
        self.ok = 0
        self.http429 = 0
        self.http404 = 0
        self.errors = 0
        self.retries = 0
        self.failed = {}        # package -> last error seen
        self.gone = []          # packages npm no longer resolves (§8 frame decay)

    def bump(self, field, n=1):
        with self.lock:
            setattr(self, field, getattr(self, field) + n)


class Budget:
    """Shared retry budget for the whole poll (§10: 'a per-poll retry budget').

    npm throttles by IP, so once a run is being rate-limited into the ground the
    right move is to stop and record it, not to spend six hours proving it.
    """

    def __init__(self, n):
        self.lock = threading.Lock()
        self.left = n
        self.exhausted = False

    def spend(self):
        with self.lock:
            if self.left <= 0:
                self.exhausted = True
                return False
            self.left -= 1
            return True


def rel(path):
    """Repo-relative path for logging, falling back to absolute.

    os.path.relpath raises on Windows when the two paths sit on different
    drives. Nothing about a log line is worth losing a completed poll over.
    """
    try:
        return os.path.relpath(path, ROOT)
    except ValueError:
        return path


def iso_week(dt=None):
    dt = dt or datetime.datetime.now(datetime.timezone.utc)
    y, w, _ = dt.isocalendar()
    return '%d-W%02d' % (y, w)


def fetch(pkg, stats, budget, pacer):
    """One package, with exponential backoff. Returns (row, None) or (None, reason)."""
    pacer.wait()
    url = ENDPOINT % urllib.parse.quote(pkg, safe='@')
    last = 'unknown'
    for attempt in range(MAX_TRIES):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.load(resp)
            stats.bump('ok')
            return {'p': pkg, 't': int(time.time()), 'd': body.get('downloads') or {}}, None
        except urllib.error.HTTPError as e:
            last = 'HTTP %d' % e.code
            if e.code == 404:
                # npm no longer resolves it. Not an error: §8 declares frame decay
                # as a secondary outcome, so this is a measurement.
                stats.bump('http404')
                with stats.lock:
                    stats.gone.append(pkg)
                return None, 'HTTP 404'
            if e.code == 429:
                stats.bump('http429')
                if not budget.spend():
                    return None, 'HTTP 429 (retry budget exhausted)'
            else:
                stats.bump('errors')
        except Exception as e:                      # timeouts, resets, bad JSON
            last = type(e).__name__
            stats.bump('errors')
        if attempt < MAX_TRIES - 1:
            stats.bump('retries')
            time.sleep(BACKOFF_BASE ** attempt)
            pacer.wait()
    return None, last


def already_captured(path):
    """Resume support: which packages this week's snapshot already holds."""
    done = set()
    if not os.path.exists(path):
        return done
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    done.add(json.loads(line)['p'])
                except (ValueError, KeyError):
                    # Truncated final line from a killed run. Dropping it is
                    # correct: the package is simply re-fetched.
                    pass
    except (OSError, EOFError):
        # Gzip stream cut mid-write. Everything readable was collected above.
        pass
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--limit', type=int, default=0,
                    help='poll only the first N frame packages (probing only)')
    ap.add_argument('--retry-budget', type=int, default=5000)
    ap.add_argument('--allow-unfrozen', action='store_true',
                    help='probe against an unfrozen frame; writes nothing to the register')
    ap.add_argument('--rate', type=float, default=0.5,
                    help='requests/second for THIS process (measured per-IP ceiling)')
    ap.add_argument('--shards', type=int, default=1,
                    help='split the frame across N runners, each with its own egress IP')
    ap.add_argument('--shard', type=int, default=0, help='which shard this process polls')
    args = ap.parse_args()

    frozen = os.path.exists(MANIFEST)
    if not frozen and not args.allow_unfrozen:
        print('REFUSING: frame/MANIFEST does not exist — the frame is not frozen.')
        print('The first snapshot must not precede the freeze commit. See')
        print('PREREGISTRATION.md §2.1 and scripts/freeze_frame.py.')
        return 2

    packages = json.load(open(RANKED, encoding='utf-8'))['packages']
    if args.limit:
        packages = packages[:args.limit]
    frame_n = len(packages)
    if args.shards > 1:
        # Rank-strided, so each shard spans the whole frame. A contiguous slice
        # would give the shard holding the head far more versions per request than
        # the shard holding the tail, and the slowest shard sets the wall clock.
        packages = packages[args.shard::args.shards]

    week = iso_week()
    outdir = os.path.join(REGISTER, week)
    part = 'snapshot.ndjson.gz' if args.shards == 1 else 'shard-%02d.ndjson.gz' % args.shard
    snap = os.path.join(outdir, part)

    if frozen:
        os.makedirs(outdir, exist_ok=True)
        done = already_captured(snap)
        todo = [p for p in packages if p not in done]
        if args.shards > 1:
            print('shard %d of %d — %s of %s frame packages, %.2f req/s'
                  % (args.shard, args.shards, '{:,}'.format(len(packages)),
                     '{:,}'.format(frame_n), args.rate))
        print('week %s — %s packages, %s already captured, %s to fetch'
              % (week, '{:,}'.format(len(packages)), '{:,}'.format(len(done)),
                 '{:,}'.format(len(todo))))
    else:
        done, todo = set(), packages
        print('PROBE MODE — frame not frozen, nothing will be written to the register')
        print('fetching %s packages with %d workers' % ('{:,}'.format(len(todo)), args.workers))

    stats, budget = Stats(), Budget(args.retry_budget)
    pacer = Pacer(args.rate)
    started = time.time()
    write_lock = threading.Lock()
    out = gzip.open(snap, 'at', encoding='utf-8', newline='\n') if frozen else None

    def work(pkg):
        row, reason = fetch(pkg, stats, budget, pacer)
        if row is not None and out is not None:
            line = json.dumps(row, separators=(',', ':'))
            with write_lock:
                out.write(line + '\n')
        elif row is None and reason != 'HTTP 404':
            with stats.lock:
                stats.failed[pkg] = reason
        return pkg

    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for i, _ in enumerate(pool.map(work, todo), 1):
                if i % 1000 == 0 or i == len(todo):
                    el = time.time() - started
                    print('  %s/%s  %.3f s/pkg  ok=%s 429=%d err=%d fail=%d  elapsed %.1f min'
                          % ('{:,}'.format(i), '{:,}'.format(len(todo)), el / i,
                             '{:,}'.format(stats.ok), stats.http429, stats.errors,
                             len(stats.failed), el / 60), flush=True)
                if budget.exhausted:
                    print('  RETRY BUDGET EXHAUSTED — stopping. Run is incomplete.', flush=True)
                    break
    finally:
        if out is not None:
            out.close()

    elapsed = time.time() - started
    attempted = len(todo)
    captured = len(done) + stats.ok
    # Against this shard's slice. Whole-frame coverage, which is what §9's 90%
    # floor is about, can only be computed after every shard has reported.
    coverage = 100.0 * captured / len(packages) if packages else 0.0
    per_pkg = elapsed / max(attempted, 1)

    print()
    print('captured  : %s of %s frame packages = %.2f%%'
          % ('{:,}'.format(captured), '{:,}'.format(len(packages)), coverage))
    print('elapsed   : %.1f min  (%.4f s/pkg over %s attempted)'
          % (elapsed / 60, per_pkg, '{:,}'.format(attempted)))
    print('429s      : %d   errors: %d   retries: %d   unresolved(404): %d'
          % (stats.http429, stats.errors, stats.retries, stats.http404))
    print('failed    : %d packages recorded as gaps' % len(stats.failed))

    # §9 declares collection broken below 90% coverage over an 8-week window. One
    # run cannot make that call, but it can flag the run that will cause it.
    if frozen and coverage < 90.0:
        print('WARNING: coverage below the 90%% floor in PREREGISTRATION.md §9.')

    if frozen:
        run = {
            'week': week,
            'shard': args.shard,
            'shards': args.shards,
            'rate': args.rate,
            'started_utc': datetime.datetime.fromtimestamp(
                started, datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'finished_utc': datetime.datetime.now(
                datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'frame_size': len(packages),
            'attempted': attempted,
            'captured': captured,
            'coverage_pct': round(coverage, 3),
            'complete': not budget.exhausted and not stats.failed,
            'retry_budget_exhausted': budget.exhausted,
            'elapsed_seconds': round(elapsed, 1),
            'seconds_per_package': round(per_pkg, 4),
            'workers': args.workers,
            'http_429': stats.http429,
            'http_404_unresolved': stats.http404,
            'errors': stats.errors,
            'retries': stats.retries,
            'gone_from_npm': sorted(stats.gone),
            'failed': stats.failed,
        }
        # Append rather than overwrite: a resumed run must not erase the failures
        # of the run it is resuming.
        runpath = os.path.join(
            outdir, 'run.json' if args.shards == 1 else 'run-%02d.json' % args.shard)
        prior = []
        if os.path.exists(runpath):
            existing = json.load(open(runpath, encoding='utf-8'))
            prior = existing if isinstance(existing, list) else [existing]
        json.dump(prior + [run], open(runpath, 'w', encoding='utf-8', newline='\n'), indent=1)
        print()
        print('wrote %s' % rel(runpath))
        print('wrote %s' % rel(snap))

    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
