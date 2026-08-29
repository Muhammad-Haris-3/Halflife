"""Freeze the frame.

Writes frame/MANIFEST: the SHA-256 of frame_ranked.json, the freeze timestamp,
the resolved composition, the margin-check result and the realised advisory
capture rate.

This is the act that closes the frame. After it, §2 of PREREGISTRATION.md is
binding and any change requires a numbered amendment under §11.

Refuses to run if the pre-freeze report does not pass, and refuses to overwrite
an existing MANIFEST. Does NOT commit — that is a separate deliberate act, and
the commit is what makes the freeze tamper-evident.
"""
import hashlib, json, os, subprocess, sys, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAME = os.path.join(ROOT, 'frame')
RANKED = os.path.join(FRAME, 'frame_ranked.json')
CAND = os.path.join(FRAME, 'candidates.tsv')
MANIFEST = os.path.join(FRAME, 'MANIFEST')
ADMIT_FLOOR = 10000     # PREREGISTRATION.md §3


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for blk in iter(lambda: fh.read(65536), b''):
            h.update(blk)
    return h.hexdigest()


def main():
    if os.path.exists(MANIFEST):
        print('REFUSING: frame/MANIFEST already exists. The frame is frozen.')
        print('Changing it requires a numbered amendment under PREREGISTRATION.md §11.')
        return 2

    rc = subprocess.call([sys.executable, os.path.join(ROOT, 'scripts', 'prefreeze_report.py')])
    if rc != 0:
        print()
        print('REFUSING: pre-freeze report did not pass. Nothing written.')
        return 1

    fr = json.load(open(RANKED, encoding='utf-8'))
    cap = json.load(open(os.path.join(ROOT, 'data', 'pilot', 'advisory_capture.json'), encoding='utf-8'))
    pkgs = set(fr['packages'])
    advcount, dl = cap['advcount'], cap['dl']
    total_adv = sum(advcount.values())
    wa = sum(c for p, c in advcount.items() if p in pkgs)

    # The accepted coverage cost (§2.3). Recorded in the manifest because §2.3
    # requires it published alongside every result, and a figure that lives only
    # in a report nobody re-runs is not published.
    over = [(dl.get(p, 0), p, c) for p, c in advcount.items()
            if p not in pkgs and dl.get(p, 0) >= ADMIT_FLOOR]
    lost_adv = sum(c for _, _, c in over)

    prereg = os.path.join(ROOT, 'PREREGISTRATION.md')
    ts = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    lines = [
        'HALFLIFE FRAME MANIFEST',
        '=======================',
        '',
        'frozen_at_utc         : %s' % ts,
        'frame_file            : frame/frame_ranked.json',
        'frame_sha256          : %s' % sha256(RANKED),
        'candidates_sha256     : %s  (frozen input; rebuild is deterministic over it)'
        % sha256(CAND),
        'preregistration_sha256: %s' % sha256(prereg),
        '',
        'rule                  : %s' % fr['rule'],
        'candidate_source      : %s' % fr['source'],
        'frame_built           : %s' % fr['built'],
        '',
        'frame_size            : %d' % fr['size'],
        'frame_unscoped        : %d' % fr['unscoped'],
        'frame_scoped          : %d' % fr['scoped'],
        '',
        'capture_sample        : %d advisories, %d days, %s..%s'
        % (cap['n_adv'], cap['span_days'], *cap['window']),
        'capture_realised_pct  : %.1f' % (100 * wa / total_adv),
        '',
        'ACCEPTED COVERAGE COST (PREREGISTRATION.md §2.3 — publish with every result)',
        'advised_outside_frame_over_100k : %d' % fr['advised_pkgs_outside_frame_over_100k'],
        'advised_outside_frame_over_10k  : %d' % len(over),
        'advisories_lost                 : %d of %d = %.1f%%'
        % (lost_adv, total_adv, 100 * lost_adv / total_adv),
        'largest_advised_outside_frame   : %d weekly' % fr['max_weekly_dl_outside_frame'],
        '',
        'The frame is closed. Packages appearing after this timestamp are outside',
        'the primary analysis regardless of popularity. See PREREGISTRATION.md §2.1.',
        '',
    ]
    with open(MANIFEST, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines))

    print()
    print('wrote frame/MANIFEST — frame is frozen at %s' % ts)
    print()
    print('The freeze is not tamper-evident until it is committed. Next:')
    print('  git -C "%s" add -A' % ROOT)
    print('  git -C "%s" commit -m "Freeze Halflife frame and pre-registration v1.0"' % ROOT)
    print()
    print('The first snapshot must not be taken before that commit exists.')
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
