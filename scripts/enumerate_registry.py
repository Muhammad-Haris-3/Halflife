"""Enumerate the npm registry and rank unscoped packages by weekly downloads.

Long-running and resumable. Safe to kill and re-run: every phase checkpoints to
disk and skips work already done.

  Phase 1  walk _all_docs -> frame/all_names.txt          (~4.3M names)
  Phase 2  bulk downloads for unscoped names, 128/request -> frame/dl_unscoped.tsv

Phase 2 is the expensive one: ~21,000 requests against api.npmjs.org, which
returns HTTP 429 under load. Backoff is exponential and every 429 is counted and
reported, because a silent retry loop makes a slow job look like a broken one.

Nothing here freezes the frame. Freezing is writing frame/MANIFEST.
"""
import json, os, sys, time, urllib.request, urllib.parse, urllib.error

UA = {'User-Agent': 'halflife/1.0 (+https://github.com/Muhammad-Haris-3/Halflife)'}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAME = os.path.join(ROOT, 'frame')
NAMES = os.path.join(FRAME, 'all_names.txt')
DLTSV = os.path.join(FRAME, 'dl_unscoped.tsv')
PAGE = 5000
CHUNK = 128

stats = {'429': 0, 'err': 0, 'req': 0}


def get(url, timeout=60, tries=6):
    for a in range(tries):
        try:
            stats['req'] += 1
            return json.load(urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=timeout))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                stats['429'] += 1
                time.sleep(min(60, 2 ** a))
                continue
            if e.code in (400, 404):
                return None
            stats['err'] += 1
            time.sleep(1.5 * (a + 1))
        except Exception:
            stats['err'] += 1
            time.sleep(1.5 * (a + 1))
    return None


def phase1():
    done = set()
    last = None
    if os.path.exists(NAMES):
        with open(NAMES, encoding='utf-8') as fh:
            for ln in fh:
                last = ln.rstrip('\n')
        done = True
        print('[p1] resuming after %r' % last, flush=True)
    n = 0
    with open(NAMES, 'a', encoding='utf-8') as fh:
        while True:
            sk = json.dumps(last if last is not None else '')
            url = ('https://replicate.npmjs.com/_all_docs?limit=%d&startkey=%s'
                   % (PAGE + 1, urllib.parse.quote(sk)))
            d = get(url)
            if d is None:
                print('[p1] give up at %r' % last, flush=True); break
            rows = d.get('rows', [])
            if last is not None and rows and rows[0]['id'] == last:
                rows = rows[1:]
            if not rows:
                break
            for r in rows:
                fh.write(r['id'] + '\n')
            n += len(rows)
            last = rows[-1]['id']
            fh.flush()
            if n % 100000 < PAGE:
                print('[p1] %d names, at %r (429s=%d)' % (n, last[:40], stats['429']), flush=True)
            time.sleep(0.05)
    print('[p1] done, %d new names' % n, flush=True)


def _fetch_chunk(ch):
    """Resolve one chunk of <=128 unscoped names. Returns list of (name, count)."""
    url = ('https://api.npmjs.org/downloads/point/last-week/'
           + ','.join(urllib.parse.quote(c, safe='') for c in ch))
    d = get(url, timeout=45)
    if d is None:
        return [(c, -1) for c in ch]
    if len(ch) == 1 and 'downloads' in d:
        d = {ch[0]: d}
    return [(c, ((d.get(c) or {}).get('downloads', 0) if d.get(c) else 0)) for c in ch]


def phase2(workers=5):
    """Resolve unscoped download counts.

    Latency-bound rather than rate-bound: a sequential sweep of ~21,000 chunk
    requests measured ~1.5 s each, i.e. ~9 hours. A small thread pool cuts that
    proportionally. Concurrency is kept deliberately low and the exponential
    backoff in get() is retained -- this is free public infrastructure and each
    request already covers 128 packages, so the polite ceiling is reached well
    before the useful one.
    """
    import concurrent.futures as cf
    import threading

    have = set()
    if os.path.exists(DLTSV):
        with open(DLTSV, encoding='utf-8') as fh:
            for ln in fh:
                have.add(ln.split('\t')[0])
        print('[p2] resuming, %d already resolved' % len(have), flush=True)
    todo = []
    with open(NAMES, encoding='utf-8') as fh:
        for ln in fh:
            p = ln.rstrip('\n')
            if not p or p.startswith('@'):
                continue
            if p not in have:
                todo.append(p)
    print('[p2] %d unscoped names to resolve, %d workers' % (len(todo), workers), flush=True)

    chunks = [todo[i:i + CHUNK] for i in range(0, len(todo), CHUNK)]
    lock = threading.Lock()
    t0 = time.time()
    done = [0]

    with open(DLTSV, 'a', encoding='utf-8') as fh:
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            for res in ex.map(_fetch_chunk, chunks):
                with lock:
                    for name, n in res:
                        fh.write('%s\t%d\n' % (name, n))
                    fh.flush()
                    done[0] += len(res)
                    if done[0] % (CHUNK * 50) < CHUNK:
                        el = time.time() - t0
                        pct = done[0] / max(len(todo), 1)
                        print('[p2] %d/%d (%.1f%%)  %.0f min elapsed, ~%.0f min left  429s=%d'
                              % (done[0], len(todo), 100 * pct, el / 60,
                                 (el / max(pct, 1e-9) - el) / 60, stats['429']), flush=True)
    print('[p2] done. requests=%d 429s=%d errs=%d' % (stats['req'], stats['429'], stats['err']), flush=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    os.makedirs(FRAME, exist_ok=True)
    which = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if which in ('all', '1'):
        phase1()
    if which in ('all', '2'):
        phase2()
