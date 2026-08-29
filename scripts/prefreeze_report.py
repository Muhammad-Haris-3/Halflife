"""Pre-freeze report: everything that must be true before frame/MANIFEST exists.

Reads frame/frame_ranked.json and prints a PASS/FAIL verdict on the checks that
decide whether the frame is fit to freeze.

Note on what is REPORTED but does not block: the advisory-capture shortfall.
PREREGISTRATION.md §2.3 measured the frame against the 600-advisory sample,
found 20 advised packages above §3's 10,000-download floor sitting outside the
frame, and accepted that loss in writing — because the alternative is the census
§2.2 shows to be unconstructible. So this check prints the exact cost and does
not gate the freeze; §2.3 requires those figures to be published alongside every
result, which is what makes the frame's edge visible in the finding rather than
buried in its methods. A gate that contradicts the document it enforces is not a
gate, it is a bug.

Note on the weekly poll cost. It cannot be measured from this machine — npm
rate-limits per egress IP, and the answer differs between a home address and a
CI runner. It is established on GitHub Actions by scripts/poll_probe.py and
.github/workflows/shard-probe.yml, and supplied here as the AGGREGATE
seconds-per-package across all shards. Without it this script reports UNRESOLVED
rather than guessing, and the verdict is gated on it.

Writes nothing. Freezing is a separate deliberate act (scripts/freeze_frame.py).
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADMIT_FLOOR = 10000     # PREREGISTRATION.md §3 admissibility
POLL_PROVEN = os.environ.get('HALFLIFE_POLL_PROVEN_SECONDS')
CEILING_MIN = 360       # GitHub Actions job ceiling
TARGET_MIN = 300        # the poll must fit inside this, leaving an hour to commit
THROTTLE_MARGIN = 1.5   # a probe runs for minutes, the poll for hours


def main():
    fr = json.load(open(os.path.join(ROOT, 'frame', 'frame_ranked.json'), encoding='utf-8'))
    cap = json.load(open(os.path.join(ROOT, 'data', 'pilot', 'advisory_capture.json'), encoding='utf-8'))

    pkgs = set(fr['packages'])
    advcount, dl = cap['advcount'], cap['dl']
    total_adv = sum(advcount.values())
    advised = list(advcount)
    hit = [p for p in advised if p in pkgs]
    missed = [p for p in advised if p not in pkgs]
    wa = sum(advcount[p] for p in hit)
    realised = 100 * wa / total_adv

    print('=' * 76)
    print('HALFLIFE — PRE-FREEZE REPORT')
    print('=' * 76)
    print()
    print('1. FRAME')
    print('   rule           : %s' % fr['rule'])
    print('   built          : %s' % fr['built'])
    print('   size           : %s  (%s scoped, %s unscoped)'
          % ('{:,}'.format(fr['size']), '{:,}'.format(fr['scoped']), '{:,}'.format(fr['unscoped'])))
    print()

    print('2. ADVISORY CAPTURE  (measured, not estimated)')
    print('   sample         : %d advisories / %d days, %s..%s'
          % (cap['n_adv'], cap['span_days'], *cap['window']))
    print('   advised pkgs   : %d of %d in frame' % (len(hit), len(advised)))
    print('   captured       : %d of %d advisories = %.1f%%' % (wa, total_adv, realised))
    print()

    print('3. COVERAGE CHECK — does the frame miss anything the analysis could admit?')
    mm = sorted(((dl.get(p, 0), p, advcount[p]) for p in missed), reverse=True)
    over = [(n, p, c) for n, p, c in mm if n >= ADMIT_FLOOR]
    print('   §3 admits packages at >= %s weekly downloads.' % '{:,}'.format(ADMIT_FLOOR))
    print('   advised packages outside frame at/above that floor: %d' % len(over))
    if over:
        print('     largest misses:')
        for n, p, c in over[:8]:
            print('       %12s  %-34s %d adv' % ('{:,}'.format(n), p[:34], c))
    print('   largest advised package outside frame: %s weekly'
          % '{:,}'.format(mm[0][0] if mm else 0))
    lost_adv = sum(c for _, _, c in over)
    print('   advisories on those packages: %d of %d = %.1f%% of admissible events lost'
          % (lost_adv, total_adv, 100 * lost_adv / total_adv))
    if over:
        print('   ACCEPTED — §2.3 measured this cost and took it. Does not block the freeze.')
        print('   It is published alongside every result, per §2.3.')
    else:
        print('   PASS — frame misses nothing §3 would have admitted')
    print()

    print('4. POLL COST  (PREREGISTRATION.md §10)')
    if POLL_PROVEN:
        sec = float(POLL_PROVEN)
        raw = fr['size'] * sec / 60
        mins = raw * THROTTLE_MARGIN
        print('   proven rate    : %.4f s/pkg aggregate (%.2f req/s) on a clean runner'
              % (sec, 1 / sec))
        print('   weekly poll    : %.0f min raw, %.0f min with the %.1fx margin'
              % (raw, mins, THROTTLE_MARGIN))
        print('   against        : %d min target, %d min ceiling' % (TARGET_MIN, CEILING_MIN))
        poll_ok = mins < TARGET_MIN
        print('   %s' % ('PASS' if poll_ok
                         else 'FAIL — shard further, or reduce frame by rank per §10'))
    else:
        poll_ok = False
        print('   UNRESOLVED — no proven rate on a clean runner.')
        print('   npm rate-limits per egress IP, so this cannot be measured locally.')
        print('   Run .github/workflows/shard-probe.yml, then re-run this with')
        print('   HALFLIFE_POLL_PROVEN_SECONDS=<aggregate s per pkg>.')
    print()

    ok = poll_ok
    print('=' * 76)
    print('VERDICT: %s' % ('FIT TO FREEZE' if ok else 'NOT FIT TO FREEZE'))
    if not ok:
        print('         (frame content is sound; blocked only on the §10 poll-cost proof)')
    print('=' * 76)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
