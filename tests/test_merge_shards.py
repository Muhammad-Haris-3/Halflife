"""The register is append-only: a recovery window may add to a week, never replace it.

Run: python -m pytest tests -q
"""
import gzip, json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MERGE = os.path.join(ROOT, 'scripts', 'merge_shards.py')
WEEK = '2099-W01'


def write_shard(weekdir, k, rows, truncate=False):
    path = os.path.join(weekdir, 'shard-%02d.ndjson.gz' % k)
    with gzip.open(path, 'wt', encoding='utf-8') as fh:
        for p, t in rows:
            fh.write(json.dumps({'p': p, 't': t, 'd': {'1.0.0': 1}}) + '\n')
    if truncate:
        data = open(path, 'rb').read()
        open(path, 'wb').write(data[:-12])      # a shard killed mid-write
    json.dump({'complete': not truncate, 'failed': {}, 'gone_from_npm': []},
              open(os.path.join(weekdir, 'run-%02d.json' % k), 'w'))


def merge(register):
    out = subprocess.run([sys.executable, MERGE, '--week', WEEK, '--shards', '2',
                          '--register-dir', str(register)], capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    weekdir = os.path.join(register, WEEK)
    with gzip.open(os.path.join(weekdir, 'snapshot.ndjson.gz'), 'rt', encoding='utf-8') as fh:
        rows = {r['p']: r['t'] for r in map(json.loads, fh)}
    return rows, json.load(open(os.path.join(weekdir, 'run.json')))


def test_recovery_window_adds_to_the_week_and_never_replaces_it(tmp_path):
    weekdir = tmp_path / WEEK
    weekdir.mkdir()

    # Monday: the primary window captures a and b.
    write_shard(weekdir, 0, [('a', 100)])
    write_shard(weekdir, 1, [('b', 100)])
    rows, _ = merge(tmp_path)
    assert rows == {'a': 100, 'b': 100}
    assert not list(weekdir.glob('shard-*'))           # parts cleaned up after merge

    # Wednesday: the recovery window captures c, and a re-observed a.
    write_shard(weekdir, 0, [('c', 300)])
    write_shard(weekdir, 1, [('a', 300)])
    rows, run = merge(tmp_path)
    assert rows == {'a': 100, 'b': 100, 'c': 300}      # Monday's observation of a stands
    assert len(run['shard_runs']) == 4                  # both windows' run records kept


def test_a_truncated_shard_keeps_what_was_readable(tmp_path):
    weekdir = tmp_path / WEEK
    weekdir.mkdir()
    write_shard(weekdir, 0, [('p%d' % i, 1) for i in range(500)], truncate=True)
    write_shard(weekdir, 1, [('q', 1)])
    rows, run = merge(tmp_path)
    assert 'q' in rows and len(rows) > 1               # the week is merged, not lost
    assert run['shards_truncated'] == [0]
    assert run['complete'] is False
