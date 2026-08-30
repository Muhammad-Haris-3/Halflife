# Halflife

**npm publishes the per-version download split for a rolling seven days and
archives nothing. After that the distribution is gone — for everyone, npm
included.**

So the question *"does publishing a security advisory actually move anyone off
the versions it names?"* cannot be answered from data that exists today. It can
only be answered by someone who started keeping the record first. Halflife is
that record: **39,998 npm packages polled weekly**, committed to a public git
history so that what was written, and when, is checkable by any reader rather
than asserted by its author.

> **Status: not started. Nothing collected, nothing published.**
> The frame is built and the collector is rehearsed end to end on real
> infrastructure, but `frame/MANIFEST` does not exist yet, so the frame is not
> frozen and no snapshot has been taken. The first primary figure is roughly 34
> weeks after the freeze, because [`PREREGISTRATION.md`](PREREGISTRATION.md) §3
> requires 8 pre-advisory weeks per event and §6 requires 150 events matured
> through a horizon group before anything is reported.

---

## The question

The industry measures time-to-patch-**availability** — how long until a fix
exists — and stops there. Time-to-patch-**adoption** is not measured, because the
data required to measure it is deleted after seven days.

> Does publishing an advisory measurably accelerate migration away from the
> versions it names — and if so, by how much, and with what half-life?

The null this is built to be able to report is that advisories do not move
adoption at all, and that versions decay at their background rate whether or not
anyone is told they are vulnerable. That outcome is pre-committed as a
publishable finding, not a failure.

## The design that was killed first

The original plan was to compare an advised version's decay against a version of
the same package that **no advisory named**, using background version churn as
the counterfactual. That control arm cannot be built, and finding out cost an
hour.

| package | median age, advised | median age, control | age-overlapping pairs |
|---|---|---|---|
| js-yaml | 4,005 days | 20 days | **0** |
| lodash | 4,113 days | 149 days | **0** |
| tar | 2,529 days | 37 days | **0** |
| ws | 3,201 days | 44 days | **0** |
| qs | 3,461 days | 103 days | **0** |

Across 14 packages, **3 had any age-overlapping control arm**, and in two of
those the overlap was one or two versions. The reason is structural: advisories
name *ranges*, so on a mature package nearly every old version is named by
something, and the versions no advisory touches are the recent ones.

Comparing a decade-old version's decay against a three-week-old version's growth
would have produced a large, clean, entirely artefactual result — **in exactly
the direction the project hoped to find**. The naive comparison does not fail
loudly; it fails by returning the answer you wanted.

The design that replaced it is an **event study with the version as its own
control**: the same version-package pair before and after the advisory,
differenced against packages that received no advisory that week. That requires
precisely what npm destroys, which is why collection has to start before the
analysis can exist. The full measurement is in
[`FEASIBILITY.md`](FEASIBILITY.md) §4–5.

## What is being recorded

| File | What it holds |
|---|---|
| `data/register/<ISO-week>/snapshot.ndjson.gz` | One line per package: `{"p": name, "t": unix_observed, "d": {version: downloads}}` |
| `data/register/<ISO-week>/run.json` | What happened, including every request that failed, per shard |

`t` is stamped **per package, not per run**. A 39,998-package poll spans hours,
so one run-level timestamp would be a fiction.

Failures are data. Every 429, timeout and error is counted and the affected
package names are written to `run.json`, so a gap in the register reads as a gap
rather than as an absence. A run that exhausts its retry budget is marked
incomplete and the packages it missed are **excluded, never interpolated**.

Two cron windows rather than one — Monday and Wednesday. GitHub's scheduler drops
windows outright, and with a single weekly entry a dropped window costs a full
week of the pre-period for every package in the frame. Unlike an hourly feed
there is no recovering it: npm keeps seven days. The second window resumes into
the same partition and skips whatever the first captured.

**The register is gzipped files in git, not a database.** Cost is the smaller
reason. The larger one is that this project's claim is the integrity of a record,
and a public commit history is *evidence* where a database grant is only an
assurance. A `REVOKE UPDATE` only its owner can inspect is a promise; a public
commit history is checkable by a stranger.

## The frame

The cohort is the distinct packages among the **top 40,000 rows of the
ecosyste.ms download ranking**, resolved on the build date — 39,998 after
deduplication, 20,487 scoped and 19,511 unscoped. Measured against 600 real
advisories over 70 days, it captures **68.9%** of them.

The frame is closed at freeze and does not grow. It is built by
`scripts/build_frame_rank.py`, which reproduces `frame/frame_ranked.json`
**byte-for-byte** from the committed `frame/candidates.tsv` — that input is
committed rather than re-fetched because ecosyste.ms rank drifts daily, so a
rebuild from the live API would not reproduce the same frame.

A dependency-closure frame was drafted, built, and rejected first: it caught
19.2% of advisories, and depth was not the fix. A download-*threshold* frame was
also rejected, on constructibility. Both rejections and their measurements are in
[`FEASIBILITY.md`](FEASIBILITY.md) §6.2 and
[`PREREGISTRATION.md`](PREREGISTRATION.md) §2.2, and the code for both is kept —
a rejected rule whose code was deleted cannot be checked.

## Why the poll is sharded

npm rate-limits the per-version endpoint **per egress IP**, and the endpoint
accepts no bulk queries at all, so the poll is one request per package. Measured
on GitHub Actions runners, 2026-08-29:

| Target rate, one runner | Refused | Achieved |
|---|---|---|
| 0.5 req/s | **0%** | 0.50 req/s |
| 1 req/s | 27% | 0.73 req/s |
| 2 req/s | 58% | 0.84 req/s |
| 4 req/s | 77% | 0.94 req/s |

A single IP tops out below 1 req/s however it is driven — concurrency inside one
job buys nothing, because the ceiling is on the address, not the connection
count. That put the whole frame at roughly 22 hours against a 6-hour job ceiling.

Runners get **distinct egress IPs**, and four shards each behaved exactly as a
lone runner did at the same target. Eight shards at the sustainable 0.5 req/s
returned **1,200 requests, zero refusals, 4.02 req/s aggregate** — **4.14 hours**
for the full frame carrying a 1.5× margin. The frame therefore does not need
reducing, and capture stays at 68.9%.

## What is deliberately not claimed

- **Downloads are not installs and not production exposure.** CI re-pulls,
  registry mirrors and cold caches inflate every figure. Only the before/after
  design is defensible, because that inflation sits on both sides of the event
  and cancels.
- **An advisory is not an exploitable condition.** Many are reachable only under
  specific usage. Halflife measures migration, never risk.
- **Advisories with no fix are never pooled with the rest.** `request` and `ip`
  sit at 100% of downloads on advised versions because no fixed version exists.
  That is a categorically different condition from a fix existing and not being
  adopted, and combining them produces a number that means nothing.
- **The frame's edge is published with every result.** It misses 20 advised
  packages above the ≥10,000-download admissibility floor, worth 9.1% of
  otherwise-admissible events. That cost is recorded in `frame/MANIFEST` and
  reported alongside every figure rather than buried in the methods.

## Running it

```bash
python scripts/prefreeze_report.py
```

```bash
python scripts/collect.py --shards 8 --shard 0 --rate 0.5
```

The collector **refuses to run until `frame/MANIFEST` exists**. A snapshot taken
before the freeze commit would make the frame a description of what was already
seen rather than a rule fixed in advance.

To prove the pipeline without touching the register, `--rehearsal-dir` writes
elsewhere and is refused if it resolves inside `data/register`. The `rehearse`
workflow runs the full 8-shard path against a capped slice and asserts afterwards
that the register was never created.

## Cost

**Zero.** Three free keyless APIs — npm, OSV, and the GitHub Advisory API — and
GitHub Actions, which is unlimited on public repositories. No database on the
critical path: derived results are reproducible from the register, so losing them
costs a recompute and nothing else.

## Known, unresolved

**Storage.** Measured from the register's actual format, not estimated:
**2,566 bytes per package raw, 736 gzipped** — a compression ratio of 0.29, not
the 0.18 an earlier draft assumed, because version strings and download counts
are high-entropy. That is **1.43 GB/year**, which crosses the 1 GB mark at which
GitHub warns around **week 36** and its 5 GB soft limit in year four. Compaction
of closed partitions is a first-year commitment, and is deliberately *not*
implemented yet: it rewrites files the append-only guarantee protects, so it
should land as its own reviewed change rather than be folded into the collector.

**Prerelease ordering.** The pilot's semver comparator ignores prerelease
ordering. 192 of 192 OSV range events parsed cleanly as semver, so this is
tractable — but the collector needs a real resolver, and it does not have one yet.

**Frame decay.** Packages that stop resolving are recorded as such rather than
dropped, and the share that decays over time is a declared secondary outcome
(§8). Nobody knows what that rate is yet.

---

## Repository

| Path | |
|---|---|
| [`PREREGISTRATION.md`](PREREGISTRATION.md) | The rules, fixed in advance. Changes require a numbered amendment recording what had already been seen |
| [`FEASIBILITY.md`](FEASIBILITY.md) | What was measured before any of this was built, including the two designs that were rejected |
| `scripts/collect.py` | The weekly poll |
| `scripts/merge_shards.py` | Assembles shard files into one week partition; computes whole-frame coverage |
| `scripts/poll_probe.py` | Establishes the sustainable request rate on clean infrastructure |
| `scripts/freeze_frame.py` | Closes the frame. Refuses unless the pre-freeze report passes |

Every figure Halflife publishes cites the commit hash of `PREREGISTRATION.md` as
it stood when that figure's observation window **opened**.
