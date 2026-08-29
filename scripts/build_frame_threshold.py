"""REJECTED DESIGN — kept as evidence, not on any live path.

This builds the >=100,000-weekly-downloads THRESHOLD frame, which
PREREGISTRATION.md §2.2 drafted and rejected on constructibility: npm's bulk
endpoint rejects scoped names, individual scoped lookups measured 0.65-1.06
packages/second under throttling (~700 hours for 1.65M scoped names), and
ecosyste.ms rank is too noisy a predictor of npm weekly downloads for any pool
depth to guarantee a superset. The live frame rule is top-N by rank, built by
scripts/build_frame_rank.py.

It is retained because §2.2 cites its measurements, and a rejected rule whose
code was deleted cannot be checked. Its output is frame/frame_threshold.json —
it must never write frame/frame_ranked.json, which is the live frame.

Build the >=100k threshold frame.

Two sources, two distinct roles:

  ecosyste.ms  -- CANDIDATE GENERATION ONLY. Supplies a download-ordered list of
                  npm packages, scoped and unscoped alike. Its `downloads` field
                  appears to be a ~monthly figure and is never used as the
                  threshold.
  npm          -- AUTHORITATIVE. Every candidate's `last-week` download count is
                  resolved from npm directly, and the >=100,000 threshold in
                  PREREGISTRATION.md §2.1 is applied to that number only.

Why a candidate list at all: a full npm census is ~21,000 bulk requests and was
measured at 5-9 hours under heavy HTTP 429 throttling. Candidate generation cuts
it to ~400 ecosyste.ms pages plus verification of ~40,000 names.

Safety margin: CANDIDATES is set far deeper than the threshold requires. At rank
40,000 ecosyste.ms reports ~126k monthly, well under the ~430k monthly that
100k/week implies, so the candidate pool is a comfortable superset. That margin
is asserted here and CHECKED at the end -- if the deepest candidates are not
safely below threshold, the run says so rather than silently truncating.

Resumable. Safe to kill and re-run.
"""
import json, os, sys, time, urllib.request, urllib.parse, urllib.error

UA = {'User-Agent': 'halflife-frame/0.1 (hariskhokhar975@gmail.com)'}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAME = os.path.join(ROOT, 'frame')
CAND = os.path.join(FRAME, 'candidates.tsv')
VERIF = os.path.join(FRAME, 'verified.tsv')

CANDIDATES = 40000
PER_PAGE = 100
THRESHOLD = 100000
CHUNK = 128

stats = {'429': 0, 'err': 0}


def get(url, timeout=90, tries=5):
    for a in range(tries):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=timeout))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                stats['429'] += 1; time.sleep(min(60, 2 ** a)); continue
            if e.code in (400, 404):
                return None
            stats['err'] += 1; time.sleep(2 * (a + 1))
        except Exception:
            stats['err'] += 1; time.sleep(2 * (a + 1))
    return None


def phase_candidates():
    done_pages = 0
    if os.path.exists(CAND):
        with open(CAND, encoding='utf-8') as fh:
            done_pages = sum(1 for _ in fh) // PER_PAGE
        print('[cand] resuming after ~%d pages' % done_pages, flush=True)
    base = ('https://packages.ecosyste.ms/api/v1/registries/npmjs.org/packages'
            '?sort=downloads&order=desc&per_page=%d' % PER_PAGE)
    npages = CANDIDATES // PER_PAGE
    t0 = time.time()
    with open(CAND, 'a', encoding='utf-8') as fh:
        for page in range(done_pages + 1, npages + 1):
            d = get(base + '&page=%d' % page)
            if not d:
                print('[cand] page %d empty/failed, stopping' % page, flush=True); break
            for p in d:
                n = p.get('name')
                if n:
                    fh.write('%s\t%d\n' % (n, p.get('downloads') or 0))
            fh.flush()
            if page % 20 == 0:
                el = time.time() - t0
                pct = (page - done_pages) / max(npages - done_pages, 1)
                print('[cand] page %d/%d  %.0f min elapsed, ~%.0f min left'
                      % (page, npages, el / 60, (el / max(pct, 1e-9) - el) / 60), flush=True)
            time.sleep(0.2)
    print('[cand] done', flush=True)


def _npm_bulk(names):
    url = ('https://api.npmjs.org/downloads/point/last-week/'
           + ','.join(urllib.parse.quote(c, safe='') for c in names))
    d = get(url, timeout=45)
    if d is None:
        return [(c, -1) for c in names]
    if len(names) == 1 and 'downloads' in d:
        d = {names[0]: d}
    return [(c, ((d.get(c) or {}).get('downloads', 0) if d.get(c) else 0)) for c in names]


def _npm_single(name):
    # Scoped names cannot be bulked, so this runs once per package. Measured at
    # 4 workers with no delay it drew 1,126 HTTP 429s in ~12 minutes and slowed
    # to a crawl on backoff -- being gentler here is both politer and faster,
    # because every 429 costs an exponential sleep.
    time.sleep(0.25)
    d = get('https://api.npmjs.org/downloads/point/last-week/'
            + urllib.parse.quote(name, safe=''), timeout=30)
    return (name, (d or {}).get('downloads', -1) if d else -1)


def phase_verify(workers=4):
    import concurrent.futures as cf, threading
    have = set()
    if os.path.exists(VERIF):
        with open(VERIF, encoding='utf-8') as fh:
            for ln in fh:
                have.add(ln.split('\t')[0])
        print('[verify] resuming, %d already verified' % len(have), flush=True)
    cands = []
    with open(CAND, encoding='utf-8') as fh:
        for ln in fh:
            n = ln.split('\t')[0]
            if n and n not in have:
                cands.append(n)
    uns = [c for c in cands if not c.startswith('@')]
    sco = [c for c in cands if c.startswith('@')]
    print('[verify] %d to verify (%d unscoped, %d scoped)' % (len(cands), len(uns), len(sco)), flush=True)

    lock = threading.Lock(); t0 = time.time(); done = [0]
    total = len(cands)

    def emit(fh, rows):
        with lock:
            for n, v in rows:
                fh.write('%s\t%d\n' % (n, v))
            fh.flush()
            done[0] += len(rows)
            if done[0] % 2000 < len(rows):
                el = time.time() - t0; pct = done[0] / max(total, 1)
                print('[verify] %d/%d (%.1f%%)  %.0f min elapsed, ~%.0f min left  429s=%d'
                      % (done[0], total, 100 * pct, el / 60,
                         (el / max(pct, 1e-9) - el) / 60, stats['429']), flush=True)

    with open(VERIF, 'a', encoding='utf-8') as fh:
        chunks = [uns[i:i + CHUNK] for i in range(0, len(uns), CHUNK)]
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            for rows in ex.map(_npm_bulk, chunks):
                emit(fh, rows)
        # Scoped: half the concurrency of the bulk phase. Each request covers
        # one package instead of 128, so this phase is ~128x the request rate
        # for the same number of packages and is where throttling actually bites.
        with cf.ThreadPoolExecutor(max_workers=max(2, workers // 2)) as ex:
            for row in ex.map(_npm_single, sco):
                emit(fh, [row])
    print('[verify] done. 429s=%d errs=%d' % (stats['429'], stats['err']), flush=True)


def phase_assemble():
    dl = {}
    with open(VERIF, encoding='utf-8') as fh:
        for ln in fh:
            n, v = ln.rstrip('\n').split('\t')
            dl[n] = int(v)
    keep = {n: v for n, v in dl.items() if v >= THRESHOLD}
    scoped = sum(1 for n in keep if n.startswith('@'))
    unres = sum(1 for v in dl.values() if v < 0)

    # margin check: is the candidate pool actually a superset?
    order = []
    with open(CAND, encoding='utf-8') as fh:
        for ln in fh:
            order.append(ln.split('\t')[0])
    tail = [dl.get(n, -1) for n in order[-2000:]]
    tail_ok = [v for v in tail if v >= 0]
    over = sum(1 for v in tail_ok if v >= THRESHOLD)

    print()
    print('FRAME')
    print('  candidates verified : %d (%d unresolved)' % (len(dl), unres))
    print('  above %s/week   : %d' % ('{:,}'.format(THRESHOLD), len(keep)))
    print('    unscoped          : %d' % (len(keep) - scoped))
    print('    scoped            : %d' % scoped)
    print()
    print('  MARGIN CHECK — deepest 2000 candidates:')
    print('    at/above threshold: %d  (want 0; >0 means the pool truncated real members)' % over)
    if tail_ok:
        print('    max in tail       : %s/week' % '{:,}'.format(max(tail_ok)))

    json.dump({'threshold': THRESHOLD,
               'source': 'ecosyste.ms candidates, npm last-week authoritative',
               'candidates': len(dl), 'unresolved': unres,
               'size': len(keep), 'scoped': scoped, 'unscoped': len(keep) - scoped,
               'margin_tail_over_threshold': over,
               'packages': sorted(keep)},
              open(os.path.join(FRAME, 'frame_threshold.json'), 'w', encoding='utf-8',
                   newline='\n'), indent=0)
    print('\nwrote frame/frame_threshold.json')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    os.makedirs(FRAME, exist_ok=True)
    w = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if w in ('all', 'c'): phase_candidates()
    if w in ('all', 'v'): phase_verify()
    if w in ('all', 'a'): phase_assemble()
