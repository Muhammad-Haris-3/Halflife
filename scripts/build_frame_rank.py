"""Build the download-ranked frame — the script that actually produces frame/frame_ranked.json.

This is the rule fixed in PREREGISTRATION.md §2.1: the frame is the top-N npm
packages by ecosyste.ms download rank, as resolved on the build date. There is no
download threshold and no npm verification step — §2.1 says so explicitly, and
the reason is in §2.2: npm's bulk endpoint rejects scoped names, so any
verification pass is either 700 hours of individual lookups or an asymmetry
between the scoped and unscoped halves of the frame. Neither is worth buying,
because the design never needed a census (§2.2) — only a frame fixed in advance
and not selected on the outcome.

  Phase 1  ecosyste.ms pages, downloads-descending -> frame/candidates.tsv
  Phase 2  top-N of that ordering, plus the realised capture measured against
           the advisory sample                     -> frame/frame_ranked.json

Phase 1 is resumable and safe to kill and re-run. Phase 2 is pure: it reads
candidates.tsv and writes frame_ranked.json with no network access, so the frame
can be rebuilt from committed inputs by anyone, which is what §2.1's
"publicly reproducible" claim requires.

Note that ecosyste.ms rank drifts daily, so re-running Phase 1 on a later date
will NOT reproduce an earlier frame. That is why candidates.tsv is committed
rather than ignored: it is the frozen input, and Phase 2 over it is
deterministic.

Writes no MANIFEST. Freezing is a separate deliberate act (scripts/freeze_frame.py).
"""
import json, os, sys, time, urllib.request, urllib.error

UA = {'User-Agent': 'halflife-frame/0.1 (hariskhokhar975@gmail.com)'}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAME = os.path.join(ROOT, 'frame')
CAND = os.path.join(FRAME, 'candidates.tsv')
RANKED = os.path.join(FRAME, 'frame_ranked.json')
CAPTURE = os.path.join(ROOT, 'data', 'pilot', 'advisory_capture.json')

SIZE = 40000            # PREREGISTRATION.md §2.1
# The build date is evidence, not metadata: it is what establishes that the frame
# was fixed before the advisories under study. A rebuild from the same frozen
# candidates.tsv must reproduce it rather than re-stamp today, so it is taken
# from HALFLIFE_FRAME_BUILT when reproducing a prior build.
BUILT = os.environ.get('HALFLIFE_FRAME_BUILT')
PER_PAGE = 100
API = ('https://packages.ecosyste.ms/api/v1/registries/npmjs.org/packages'
       '?sort=downloads&order=desc&per_page=%d&page=%d')


def get(url, tries=6):
    """GET with exponential backoff. ecosyste.ms rate-limits; a silent retry loop
    makes a slow job look like a broken one, so every retry is announced."""
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            return json.load(urllib.request.urlopen(req, timeout=60))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            if i == tries - 1:
                raise
            wait = 2 ** i
            print('    retry %d/%d in %ds (%s)' % (i + 1, tries - 1, wait, e), flush=True)
            time.sleep(wait)


def fetch_candidates():
    """Phase 1. Appends to candidates.tsv; resumes from whatever is already there."""
    have = 0
    if os.path.exists(CAND):
        with open(CAND, encoding='utf-8') as fh:
            have = sum(1 for l in fh if l.strip())
    if have >= SIZE:
        print('phase 1: candidates.tsv already holds %s rows — skipping fetch' % '{:,}'.format(have))
        return

    npages = -(-SIZE // PER_PAGE)
    start = have // PER_PAGE + 1
    print('phase 1: fetching pages %d..%d of ecosyste.ms (have %s rows)'
          % (start, npages, '{:,}'.format(have)))

    with open(CAND, 'a', encoding='utf-8', newline='\n') as out:
        for page in range(start, npages + 1):
            rows = get(API % (PER_PAGE, page))
            if not rows:
                print('  page %d empty — pool exhausted at %s' % (page, '{:,}'.format(have)))
                break
            for r in rows:
                name, dl = r.get('name'), r.get('downloads')
                if not name or dl is None:
                    continue
                out.write('%s\t%d\n' % (name, dl))
                have += 1
            out.flush()
            if page % 25 == 0 or page == npages:
                print('  page %d/%d  rows=%s' % (page, npages, '{:,}'.format(have)), flush=True)
            time.sleep(0.1)


def build():
    """Phase 2. Deterministic: candidates.tsv -> frame_ranked.json, no network."""
    names = []
    with open(CAND, encoding='utf-8') as fh:
        for line in fh:
            if line.strip():
                names.append(line.split('\t')[0])
    if len(names) < SIZE:
        print('REFUSING: candidates.tsv holds %s rows, need %s. Re-run phase 1.'
              % ('{:,}'.format(len(names)), '{:,}'.format(SIZE)))
        return 1

    packages = names[:SIZE]
    inframe = set(packages)
    scoped = sum(1 for n in packages if n.startswith('@'))

    cap = json.load(open(CAPTURE, encoding='utf-8'))
    advcount, dl = cap['advcount'], cap['dl']
    total_adv = sum(advcount.values())
    caught = sum(c for p, c in advcount.items() if p in inframe)
    missed = [p for p in advcount if p not in inframe]

    out = {
        'rule': 'top-N npm packages by ecosyste.ms download rank, frozen at build date',
        'source': 'packages.ecosyste.ms/api/v1/registries/npmjs.org/packages?sort=downloads&order=desc',
        'built': BUILT or time.strftime('%Y-%m-%d'),
        'size': len(packages),
        'scoped': scoped,
        'unscoped': len(packages) - scoped,
        'capture_pct': round(100 * caught / total_adv, 1),
        'capture_sample': {'advisories': cap['n_adv'], 'days': cap['span_days'],
                           'window': cap['window']},
        'max_weekly_dl_outside_frame': max((dl.get(p, 0) for p in missed), default=0),
        'advised_pkgs_outside_frame_over_100k': sum(1 for p in missed if dl.get(p, 0) >= 100000),
        'packages': packages,
    }

    print()
    print('FRAME')
    print('  built             : %s%s' % (out['built'],
          '' if BUILT else '  (today — set HALFLIFE_FRAME_BUILT to reproduce a prior build)'))
    print('  size              : %s  (%s scoped, %s unscoped)'
          % ('{:,}'.format(out['size']), '{:,}'.format(out['scoped']),
             '{:,}'.format(out['unscoped'])))
    print('  advisory capture  : %d of %d = %.1f%%' % (caught, total_adv, out['capture_pct']))
    print('  largest advised package outside frame: %s weekly'
          % '{:,}'.format(out['max_weekly_dl_outside_frame']))
    print('  advised >=100k outside frame          : %d  (§2.2 asserts 0)'
          % out['advised_pkgs_outside_frame_over_100k'])

    json.dump(out, open(RANKED, 'w', encoding='utf-8', newline='\n'), indent=0)
    print('\nwrote frame/frame_ranked.json')
    return 0


def main():
    if '--build-only' not in sys.argv:
        fetch_candidates()
    return build()


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
