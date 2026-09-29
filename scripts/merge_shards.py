"""Assemble a week's shard files into one register partition.

The poll runs as N parallel GitHub Actions jobs because npm's rate limit is
per-IP: one runner sustains 0.5 req/s, eight runners sustain 4.02 req/s between
them with zero refusals (measured 2026-08-29). Each shard writes its own
`shard-NN.ndjson.gz` and `run-NN.json`; this merges them into the
`snapshot.ndjson.gz` and `run.json` that PREREGISTRATION.md §10.4 defines, so
the register's on-disk shape does not leak the fact that collection was
parallelised.

Whole-frame coverage is computed here and nowhere else. A shard knows only its
own slice, and §9's 90% floor is a statement about the frame, so the only place
it can be evaluated is after every shard has reported.

Refuses to drop a shard silently. If a shard file is missing, the merged run
record says so and marks the week incomplete — a week that lost a shard is a
week with a hole in it, and the hole has to be visible or §9 cannot be applied
honestly.
"""
import argparse, gzip, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTER = os.path.join(ROOT, 'data', 'register')
RANKED = os.path.join(ROOT, 'frame', 'frame_ranked.json')
COVERAGE_FLOOR = 90.0       # PREREGISTRATION.md §9


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--week', required=True, help='ISO week, e.g. 2026-W35')
    ap.add_argument('--shards', type=int, required=True)
    ap.add_argument('--register-dir', default='',
                    help='merge a rehearsal directory instead of the register')
    ap.add_argument('--keep-parts', action='store_true',
                    help='leave the per-shard files in place after merging')
    args = ap.parse_args()

    outdir = os.path.join(args.register_dir or REGISTER, args.week)
    if not os.path.isdir(outdir):
        print('REFUSING: %s does not exist — no shard wrote anything.' % outdir)
        return 2

    frame = json.load(open(RANKED, encoding='utf-8'))['packages']
    frame_n = len(frame)

    snap = os.path.join(outdir, 'snapshot.ndjson.gz')
    tmp = snap + '.tmp'
    seen, rows, missing, truncated = set(), 0, [], []

    def copy_rows(path, out):
        """Append path's rows not already seen. A gzip stream cut mid-write (a
        shard killed at its timeout) keeps every row readable before the cut."""
        n = 0
        try:
            with gzip.open(path, 'rt', encoding='utf-8') as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        pkg = json.loads(line)['p']
                    except (ValueError, KeyError):
                        continue
                    if pkg in seen:
                        # Shards are disjoint by construction, and a recovery
                        # window skips what is already merged, so a repeat means a
                        # re-run with different arguments. The first observation
                        # stands: the register is append-only.
                        continue
                    seen.add(pkg)
                    out.write(line + '\n')
                    n += 1
        except (OSError, EOFError):
            return n, True
        return n, False

    # Written beside the snapshot and swapped in at the end, because the
    # committed snapshot is an input: a recovery window's merge must keep every
    # row the primary window already committed, never re-derive the week from
    # the recovery shards alone.
    with gzip.open(tmp, 'wt', encoding='utf-8', newline='\n') as out:
        if os.path.exists(snap):
            prior, _ = copy_rows(snap, out)
            print('  committed: %s packages kept from earlier in the week' % '{:,}'.format(prior))
        for k in range(args.shards):
            part = os.path.join(outdir, 'shard-%02d.ndjson.gz' % k)
            if not os.path.exists(part):
                missing.append(k)
                print('  shard %02d: MISSING' % k)
                continue
            n, cut = copy_rows(part, out)
            if cut:
                truncated.append(k)
            rows += n
            print('  shard %02d: %s packages%s' % (k, '{:,}'.format(n),
                                                   ' (stream truncated — kept what was readable)' if cut else ''))
    os.replace(tmp, snap)

    # Earlier windows' run records are evidence too; a recovery merge extends them.
    runs, failed_total, gone_total = [], {}, []
    runpath = os.path.join(outdir, 'run.json')
    if os.path.exists(runpath):
        runs.extend(json.load(open(runpath, encoding='utf-8')).get('shard_runs') or [])
        for r in runs:
            failed_total.update(r.get('failed') or {})
            gone_total.extend(r.get('gone_from_npm') or [])
    for k in range(args.shards):
        rp = os.path.join(outdir, 'run-%02d.json' % k)
        if not os.path.exists(rp):
            continue
        rec = json.load(open(rp, encoding='utf-8'))
        for r in (rec if isinstance(rec, list) else [rec]):
            runs.append(r)
            failed_total.update(r.get('failed') or {})
            gone_total.extend(r.get('gone_from_npm') or [])

    coverage = 100.0 * len(seen) / frame_n if frame_n else 0.0
    # A failure that a later window recovered is no longer a gap.
    failed_total = {p: why for p, why in failed_total.items() if p not in seen}
    # Complete means every frame package was either captured or is gone from npm.
    # Counting run records cannot say that once a recovery window has added its own.
    unaccounted = set(frame) - seen - set(gone_total)
    complete = not missing and not truncated and not unaccounted

    merged = {
        'week': args.week,
        'shards': args.shards,
        'shards_missing': missing,
        'shards_truncated': truncated,
        'unaccounted': len(unaccounted),
        'frame_size': frame_n,
        'captured': len(seen),
        'coverage_pct': round(coverage, 3),
        'below_section_9_floor': coverage < COVERAGE_FLOOR,
        'complete': complete,
        'http_429': sum(r.get('http_429', 0) for r in runs),
        'http_404_unresolved': sum(r.get('http_404_unresolved', 0) for r in runs),
        'errors': sum(r.get('errors', 0) for r in runs),
        'retries': sum(r.get('retries', 0) for r in runs),
        'elapsed_seconds_max_shard': max((r.get('elapsed_seconds', 0) for r in runs), default=0),
        'gone_from_npm': sorted(set(gone_total)),
        'failed': failed_total,
        'shard_runs': runs,
    }
    json.dump(merged, open(os.path.join(outdir, 'run.json'), 'w',
                           encoding='utf-8', newline='\n'), indent=1)

    if not args.keep_parts and not missing:
        for k in range(args.shards):
            for name in ('shard-%02d.ndjson.gz' % k, 'run-%02d.json' % k):
                fp = os.path.join(outdir, name)
                if os.path.exists(fp):
                    os.remove(fp)

    print()
    print('week %s: %s of %s frame packages = %.2f%% coverage'
          % (args.week, '{:,}'.format(len(seen)), '{:,}'.format(frame_n), coverage))
    print('429s=%d errors=%d retries=%d unresolved(404)=%d failed=%d'
          % (merged['http_429'], merged['errors'], merged['retries'],
             merged['http_404_unresolved'], len(failed_total)))
    if missing:
        print('INCOMPLETE: shards %s produced no data. Recorded as a gap, not interpolated.'
              % missing)
    if coverage < COVERAGE_FLOOR:
        print('WARNING: below the %.0f%% coverage floor in PREREGISTRATION.md §9.'
              % COVERAGE_FLOOR)
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
