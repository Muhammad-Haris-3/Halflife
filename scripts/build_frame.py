"""Resolve the dependency closure of frame/seed.txt to depth 3.

Fetches only the `latest` manifest per package (small) rather than the full
registry document. Records the depth at which each package first appeared so the
closure can be truncated after the fact without re-fetching.

Writes frame/frame.json. Does NOT freeze anything — freezing is writing
frame/MANIFEST, which is a separate deliberate act.
"""
import json, os, sys, time, urllib.request, urllib.parse, urllib.error, collections

UA = {'User-Agent': 'halflife-frame/0.1 (hariskhokhar975@gmail.com)'}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_DEPTH = 3
MAX_FETCH = 12000          # runaway guard; reported if hit
DELAY = 0.06

def fetch(pkg, tries=4):
    url = 'https://registry.npmjs.org/%s/latest' % urllib.parse.quote(pkg, safe='@/')
    for a in range(tries):
        try:
            r = urllib.request.Request(url, headers=UA)
            return json.load(urllib.request.urlopen(r, timeout=30))
        except urllib.error.HTTPError as e:
            if e.code in (404, 405): return None
            if e.code == 429:
                time.sleep(2 ** a); continue
            return None
        except Exception:
            time.sleep(0.5 * (a + 1))
    return None

def load_seed():
    out = []
    with open(os.path.join(ROOT, 'frame', 'seed.txt'), encoding='utf-8') as fh:
        for ln in fh:
            ln = ln.strip()
            if ln and not ln.startswith('#'):
                out.append(ln)
    return out

def main():
    seed = load_seed()
    print('seed packages: %d' % len(seed), flush=True)

    depth = {p: 0 for p in seed}
    frontier = list(seed)
    fetched = 0
    failed = []

    for d in range(MAX_DEPTH):
        nxt = []
        print('--- depth %d -> %d : expanding %d packages' % (d, d + 1, len(frontier)), flush=True)
        for i, p in enumerate(frontier):
            if fetched >= MAX_FETCH:
                print('!! MAX_FETCH reached', flush=True); break
            m = fetch(p); fetched += 1
            time.sleep(DELAY)
            if m is None:
                failed.append(p); continue
            deps = {}
            deps.update(m.get('dependencies') or {})
            deps.update(m.get('peerDependencies') or {})
            for dep in deps:
                if dep not in depth:
                    depth[dep] = d + 1
                    nxt.append(dep)
            if (i + 1) % 250 == 0:
                print('    %d/%d expanded, closure=%d, fetched=%d'
                      % (i + 1, len(frontier), len(depth), fetched), flush=True)
        frontier = nxt
        print('    depth %d added %d -> closure now %d' % (d + 1, len(nxt), len(depth)), flush=True)
        if not frontier: break

    by_depth = collections.Counter(depth.values())
    print()
    print('CLOSURE BY DEPTH')
    cum = 0
    for d in sorted(by_depth):
        cum += by_depth[d]
        print('  depth %d: %6d new   cumulative %6d' % (d, by_depth[d], cum))
    print('total closure: %d packages (%d fetches, %d manifests unavailable)'
          % (len(depth), fetched, len(failed)))

    os.makedirs(os.path.join(ROOT, 'frame'), exist_ok=True)
    with open(os.path.join(ROOT, 'frame', 'frame.json'), 'w', encoding='utf-8') as fh:
        json.dump({'max_depth': MAX_DEPTH,
                   'seed_count': len(seed),
                   'packages': depth,
                   'unavailable': failed}, fh, indent=0, sort_keys=True)
    print('wrote frame/frame.json')

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
