# Halflife — pre-registration v1.0 (DRAFT — NOT FROZEN)

> ## ⚠ DRAFT — not frozen. One open item blocks the freeze.
>
> **§2 has been rebuilt and the invalidation it carried is resolved.** The
> original §2.1 rule — dependency closure of a fixed seed — was built and checked
> before freezing, as intended, and captured **19.2% of advisories** against the
> 73.0% it had assumed ([`FEASIBILITY.md`](FEASIBILITY.md) §6.2). It was replaced
> with the download-rank frame now stated in §2.1, which was built and measured
> at **68.9% capture** against the same 600-advisory sample. The rejected closure
> rule is preserved in §2.2 and must not be reintroduced without an amendment.
>
> **Blocking the freeze: §10's weekly poll cost is unproven.** The frame is
> 40,000 packages against a 6-hour job ceiling, and no clean measurement exists —
> local figures were taken from an IP this project had already throttled. It must
> be established on a GitHub Actions runner before this document is frozen. If
> the poll cannot complete, the frame is reduced by rank per §10, *before* the
> first snapshot.
>
> **No snapshot has been taken. The clock has not started.**

**Drafted 28 August 2026, before the first weekly snapshot exists and before
any advisory has been observed under this design.** The pilot described in
[`FEASIBILITY.md`](FEASIBILITY.md) had been seen when this was written. That
pilot is explicitly **not** part of any result reported under this document.

Everything below is fixed. Changes require a numbered amendment under §11
stating what changed, why, and what had already been seen, kept in git history
beside the original.

---

## 0. Why this document exists

npm publishes the per-version download split for a rolling seven days and
archives nothing. Once collection starts, the register becomes the only record
of what it saw, and its keeper is the only person who can check it. A rule
written after seeing that record is not a rule; it is a description of what
already happened.

Every figure Halflife publishes cites the commit hash of this file as it stood
when the observation window for that figure **opened**.

---

## 1. The question

When a security advisory names a package version, the industry measures
time-to-patch-*availability* and stops. Time-to-patch-*adoption* is not
measured, because the data required to measure it is deleted after seven days.

> **Does publishing an advisory measurably accelerate migration away from the
> versions it names — and if so, by how much, and with what half-life?**

The null this is built to be able to report is that advisories do not move
adoption at all, and that versions decay at their background rate whether or not
anyone is told they are vulnerable.

---

## 2. The frame

### 2.1 The rule, fixed now

The cohort is the **top 40,000 npm packages by ecosyste.ms download rank**, as
resolved on the build date and recorded in `frame/frame_ranked.json`.

That is the entire rule. There is no download threshold applied at collection
time, and no npm verification step.

**Composition as built (2026-08-28):** 40,000 packages — 20,487 scoped, 19,513
unscoped.

**The frame is a defined set, not a claimed census.** It does not assert that it
contains every npm package above any download level, because no such assertion
is constructible (§2.2). It asserts only that it is a large, download-ordered,
publicly reproducible sample of npm, fixed before any advisory under study was
published. That is what the design actually requires: a frame chosen in advance
and not selected on the outcome.

**Collect wide, admit narrow.** Membership in the frame is a *collection*
decision and is irreversible — a package outside it can never have pre-advisory
history, at any later date, for any amount of money. Admission to the primary
set is an *analysis* decision (§3), applied later, reversibly, under a rule that
can be reasoned about. So the frame is deliberately wider than the analysis
needs, and §3's ≥10,000-weekly-downloads rule does the filtering where filtering
is cheap.

The frame is written to `frame/frame_ranked.json` by
[`scripts/build_frame_rank.py`](scripts/build_frame_rank.py), with a SHA-256 hash
recorded in `frame/MANIFEST` alongside the freeze timestamp, the resolved size,
the scoped and unscoped counts, the realised advisory capture, and the accepted
coverage cost of §2.3. The manifest also records the SHA-256 of
`frame/candidates.tsv`, the frozen ecosyste.ms ordering the frame is cut from —
that ordering drifts daily, so the input is committed rather than re-fetched, and
the build over it is deterministic. There is no margin check and no count of
unresolved candidates: both belonged to the threshold rule rejected in §2.2.

The frame is closed at freeze and **does not grow**. Packages that appear later,
however popular, are out of the primary analysis until a numbered amendment adds
them, and any such amendment starts a separate cohort with its own window.

**Known dependency.** Membership rests on ecosyste.ms's coverage being complete
down to rank 40,000. A package popular enough to clear 100,000 weekly downloads
but absent from their index is missed, and nothing in this design would detect
that. The alternative — a full npm census — was measured at 5–9 hours under
heavy `HTTP 429` throttling for a single build, and is rejected on cost, not on
principle.

### 2.2 Why download rank, and why candidates rather than a census

**A dependency-closure frame was drafted, built and rejected.** The closure of a
79-package seed to depth 3 gave 2,248 packages and would have caught **19.2% of
advisories**. Depth was not the fix: depth 2→3 added 602 packages for 1.0
percentage point. 102 missed packages had ≥10,000 weekly downloads, including
`pnpm` (175M weekly, 31 advisories), `dompurify` (62M) and `mermaid` (15M, 8
advisories). Advisories land on standalone tooling, on application-level
libraries no framework depends on, and on newer packages outside any established
seed — none of which a closure reaches. The full measurement is in
[`FEASIBILITY.md`](FEASIBILITY.md) §6.2, and the rejected rule must not be
reintroduced without an amendment.

Download rank is used instead because it **correlates with advisory incidence
directly**, which is measured rather than assumed.

**A download-threshold frame was also drafted and rejected, on constructibility.**
It cannot be built by census: scoped packages are 38.1% of the registry, npm's
bulk endpoint rejects them, and individual scoped lookups measured **0.65–1.06
packages/second under throttling** — roughly 700 hours for the 1.65M scoped
names. It cannot be built by candidate generation either, because ecosyste.ms
rank is a *noisy* predictor of npm weekly downloads: a package at rank 34,316 was
measured clearing 5M weekly, so no pool depth guarantees a superset. Demanding
completeness was the error; the design never needed it.

**What the pool does guarantee, measured:** across the 600-advisory sample, of
279 advised packages, **every one with ≥100,000 weekly downloads is inside the
40,000 pool**. The largest advised package outside it is 58,089 weekly.

**Why candidates rather than a census.** Scoped packages are **38.1% of the
registry** (1,653,334 of 4,335,856, from `_all_docs` offsets) and npm's bulk
downloads endpoint rejects them (`HTTP 400`), capping at 128 unscoped names per
request. A full census means ~21,000 bulk requests plus ~1.65M individual ones;
the unscoped half alone was measured at **5–9 hours** with `HTTP 429` throttling
throughout. Candidate generation reduces this to ~400 ecosyste.ms pages and
nothing else: §2.1 applies no threshold, so there is no verification pass to pay
for. Because ecosyste.ms orders scoped and unscoped packages together, this also
removes the scoped/unscoped asymmetry an earlier draft of this section was forced
into.

### 2.3 What the frame captures

Measured over **600 unique advisories spanning 70 days** (2026-06-18 to
2026-08-27) — 279 distinct packages, 928 advisory-package pairs — against the
frame as actually built, not estimated:

| Frame | Packages | Share of advisories captured |
|---|---|---|
| top 5,000 by rank | 5,000 | 35.1% |
| top 12,000 | 12,000 | 46.4% |
| top 20,000 | 20,000 | 49.6% |
| top 30,000 | 30,000 | 65.2% |
| **top 40,000 (this frame)** | **40,000** | **68.9%** |

**What the missed 31.1% costs, stated exactly.** Of the advisories outside the
frame:

| Missed packages above | Packages | Advisories | Share of sample |
|---|---|---|---|
| 100,000 weekly downloads | **0** | **0** | 0.0% |
| 10,000 weekly downloads (§3's floor) | 20 | 84 | **9.1%** |

So the frame loses nothing at the 100k level, but it does discard roughly **9%
of genuinely admissible events** — packages between 10k and 58k weekly that §3
would otherwise accept. The largest single loss is `ghost` (29,074 weekly, 17
advisories in 70 days).

This is a real cost and is not written off. It is accepted because the
alternative — extending the pool deep enough to reach every package above 10k —
requires the census shown in §2.2 to be unconstructible. The 9.1% is reported
alongside every result so that the frame's edge is visible in the finding rather
than buried in its methods.

**23.3% of advised packages had zero weekly downloads** — removed or malicious
packages, published and taken down inside the advisory window. A frozen frame
excludes these by construction, since they did not exist at freeze. This is a
property of the design, not a filter applied afterwards, and no figure will be
reported that required removing them by hand.

---

## 3. Admissibility

An advisory enters the **primary set** only if all of the following hold. Each
is checkable from the register without judgement.

| Condition | Threshold |
|---|---|
| Package is in the frozen frame | required |
| Advisory `published` date falls after the frame freeze | required |
| Pre-advisory weekly observations of the package in the register | **≥ 8** |
| Package weekly downloads in the advisory week | **≥ 10,000** |
| Advisory carries a fixed version | required for the primary set |
| Affected range parses as semver against the package's published versions | required |

**Advisories with no fixed version are tracked in a separate register and never
pooled with the primary set.** `request` and `ip` sit at 100% of downloads on
advised versions because no fix exists; that is a different condition from a fix
existing and not being adopted, and combining them would produce a number that
means nothing.

Failed admissions are recorded with their reason. The count of excluded
advisories, by reason, is published alongside every result.

---

## 4. Outcome measure

For package `p`, advisory `a`, week `t`:

```
affected_share(p, a, t) = downloads on versions of p named by a in week t
                          ------------------------------------------------
                                 total downloads of p in week t
```

A **share**, not a count, so that package-level popularity trends — a package
growing or shrinking overall — cannot masquerade as migration.

**Primary estimand:** the change in the weekly decay rate of
`log(affected_share)` at the advisory week, and the cumulative displacement at
each horizon in §6.

---

## 5. Identification

### 5.1 The design

An **event study in event-time**, with the version-package pair as its own
control, differenced against a matched control arm.

The comparison rejected in `FEASIBILITY.md` §4 — advised versions against
non-advised versions of the same package — is not used, and must not be
reintroduced without an amendment. It fails because advised versions have a
median age of eight to twelve years while their would-be controls have a median
age of weeks, so it returns a large artefactual result in exactly the direction
this project hopes to find.

### 5.2 Control construction, fixed now

For each treated event on package `p` at week `T`, controls are drawn from frame
packages with **no advisory in `[T − 8, T + 26]` weeks**, matched on:

1. weekly-download decile at `T`, and
2. pseudo-`affected_share` at `T` within 0.10, where the pseudo-affected range
   for a control package `q` is **every version of `q` published strictly before
   the latest version of `q` published on or before `T`** — the same
   "everything below the fix" rule applied to a package nobody warned about.

Up to **5 controls per treated event**, selected by nearest-neighbour on (1)
then (2), without replacement within an event.

Versions **above** the fix are never used as controls. They mechanically absorb
what treated versions lose, and using them would build the answer into the
design.

### 5.3 The pre-trend gate

Event-time coefficients are estimated over `[T − 8, T + 26]` with `T − 1` as the
reference week. An event enters the primary set only if a joint Wald test on the
pre-period coefficients (`T − 8` through `T − 2`) does **not** reject parallel
pre-trends at **p < 0.10**.

This gate is a fixed rule, not a judgement. The number of events it excludes is
published with every result, because a gate that quietly removes half the sample
is itself a finding.

---

## 6. Horizons and maturity

Fixed here. Tests are computed within groups, never on individual weeks, because
26 separate weekly tests would produce a "significant" result from multiplicity
alone.

| Group | Event-time weeks | Reported as |
|---|---|---|
| `H30` | +1 to +4 | 30-day displacement |
| `H90` | +5 to +13 | 90-day displacement |
| `H180` | +14 to +26 | 180-day displacement, and the fitted half-life |

A group publishes only when **≥ 150 admitted events have fully matured through
that group**. Groups publish independently; `H30` maturing does not license any
statement about `H180`.

**No provisional figure will be shown, at any point, for any reason.** Not a
partial curve, not a preliminary half-life, not a count of events with a
direction attached.

---

## 7. Forecasts committed before outcomes

At the week an admitted advisory is first observed, and **before any post-event
data exists**, Halflife writes a forecast of `affected_share` at +4, +13 and +26
weeks to the append-only register defined in §10.4.

Three forecasters, fixed now, all writing under their own `model_version`:

1. **Persistence** — the pre-advisory trend extrapolated forward unchanged. The
   baseline it would be embarrassing to lose to, and the one whose defeat *is*
   the project's headline claim.
2. **Background churn** — the matched control arm's realised trajectory. The
   honest counterfactual.
3. **Fitted** — features restricted to what is knowable at `T`: severity, CVSS
   vector, whether the fix is a major-version bump, package age, count of
   published versions, weekly downloads, and `affected_share` at `T`.

Scored by mean absolute error within horizon group, with Diebold–Mariano
(Harvey–Leybourne–Newbold small-sample correction) as the primary test and paired
Wilcoxon signed-rank as confirmatory. Nothing in a forecast row records which
forecaster served the public page; that is held separately with effective dates,
so role history cannot be back-edited into the evidence.

---

## 8. Secondary outcomes

Declared now so that they cannot be promoted to primary after the fact:

- **Half-life** — weeks until `affected_share` falls to half its value at `T`,
  fitted on `H180`, reported with the share of events that never reach half.
- **Severity gradient** — displacement by advisory severity. Reported as a
  distribution, never as a single headline number.
- **No-fix register** — the separate population from §3, reported only as
  descriptive counts.
- **Frame decay** — the share of frame packages that stop resolving over time.

---

## 9. Kill conditions

Fixed now, with no idea what the answer will be.

| Condition | Consequence |
|---|---|
| `H90` displacement 95% CI contained within ±10% relative to control | Finding is **"advisories do not measurably move adoption"** and is published as that |
| Pre-trend gate excludes > 50% of otherwise-admissible events | Design is reported as failed; no displacement figure is published |
| Fewer than 150 admitted events matured in a group 52 weeks after freeze | That group is reported as underpowered and left unpublished |
| Weekly snapshot coverage falls below 90% of frame packages over any 8-week window | Collection is declared broken for that window and those weeks are excluded, with the exclusion published |

The ±10% figure is set now. If the true acceleration turns out to be 3%, that is
the finding and it gets published as such.

---

## 10. Collection

Weekly, on a fixed weekday, via **two independent cron windows** rather than
one. GitHub's scheduler drops windows outright; with a single weekly entry a
dropped window costs a full week of the pre-period for every package in the
frame, and unlike an hourly feed there is no way to recover it.

Everything is stamped when **observed**, never when scheduled. Every poll writes
a `runs` record including every request that failed, so gaps in the register are
visible as gaps rather than as absences.

Measured collection cost, from `FEASIBILITY.md` §6: 14.1 KB and 0.85 s per
package. **npm returns `HTTP 429` under sustained querying**, so the collector
carries exponential backoff with a per-poll retry budget, and every 429 is
written to the `runs` record rather than silently absorbed. A poll that exhausts
its retry budget is recorded as incomplete for the packages it missed; those
package-weeks are excluded, not interpolated.

**The frame is 40,000 packages and the weekly poll cost is not yet established.**
This is the one unresolved risk before freeze.

The per-version endpoint accepts no bulk queries at all, scoped or unscoped, so
the poll is 40,000 individual requests. Measured cleanly, before this project
had made heavy use of the API: **0.85 s/package with zero `HTTP 429`s**, which
implies ~9.4 hours sequentially and roughly 2.4 hours at four workers. Measured
again after sustained querying had throttled the originating IP: **0.77–1.06
packages/second with 643–931 429s in a single 400-package sample** — a
measurement of the penalty box, not of npm.

**The binding constraint is concurrency, not npm's rate.** A single request to
the per-version endpoint takes roughly 1.6 s at the median, so 40,000 of them are
about 18 core-hours no matter how the poll is written, and the only question that
decides the frame is how many can run at once before npm starts returning 429.
A figure in seconds-per-package is therefore not a property of npm at all — it is
a property of a chosen worker count — and the sequential and four-worker numbers
above answer a question the collector does not ask.

The honest position is that the true concurrency limit is unknown from this
machine and must be established **on a GitHub Actions runner**, which is where
the collector will run and which does not inherit the local IP's throttling
history. [`scripts/poll_probe.py`](scripts/poll_probe.py) sweeps worker counts
over disjoint rank-strided samples and reports the highest that stays clean of
429s, projected to the full frame with a **1.5× margin** for the throttling a
short probe does not run long enough to provoke.

If no concurrency completes the poll inside the 6-hour job ceiling with backoff,
the frame is reduced by rank — top 30,000 (65.2% capture), then top 20,000
(49.6%) — *before* the first snapshot, never after, and never by dropping
individual packages the advisory feed has already touched.

Compaction of closed partitions must land as its own reviewed change, never
folded into the collector, and — per the correction in §10.4 — **before the
register passes 1 GB**, which at 0.8 GB/year is inside the first year rather than
at some unstated later point.

### 10.4 Where the register lives, and why not a database

The register is **gzipped snapshot files committed to the public repository**,
partitioned by ISO week. Not a database.

Measured on 30 real frame candidates: **2.2 KB and 103 versions per package.**
Against the 40,000-package frame of §2.1 that is **~4.1M version-rows and ~86 MB
of raw JSON per week** — about 214M rows and 4.4 GB/year, or roughly **0.8 GB/year
gzipped**.

| Option | Year-one size | Verdict |
|---|---|---|
| Postgres, all version-rows | ~9.9 GB | **Over every free tier** (Neon 0.5 GB, Supabase 500 MB) |
| Gzipped files in git | ~0.8 GB | Fits year one; see the compaction requirement below |

> **Correction, made before freeze.** An earlier draft of this section stated
> 1.2M rows, 27 MB/week and 250 MB/year gzipped. Those figures are arithmetically
> consistent with a **12,000-package** frame — 27 MB ÷ 2.2 KB = 12,567, and 1.2M
> ÷ 103 = 11,650 — and were never updated when §2.1 was rebuilt to 40,000. The
> per-package measurement was right; the multiplication was against a frame size
> that no longer existed. The figures above are the same measurement against the
> frame actually specified.

**What the correction changes.** Gzipped-files-in-git still wins, and for the
reason below rather than on size. But the margin is 3.3× tighter than the
superseded figures implied: GitHub warns above 1 GB and soft-limits around 5 GB,
and gzipped blobs do not delta-compress, so each year costs the same again rather
than less. Year one lands in warning territory and year five at the soft limit.
Compaction is therefore **load-bearing inside the first year**, which is a
schedule commitment, not the open-ended "before it bites" the draft carried.

Cost is the smaller reason. The larger one is that this project's claim is the
integrity of a record, and **git history is a stronger guarantee than a database
grant**: any reader can verify what was written and when, independently, without
trusting that permissions were configured correctly or that they still are. A
`REVOKE UPDATE` that only the author can inspect is an assurance; a public commit
history is evidence.

A database is used only for **derived results** — event-study coefficients,
decay curves, per-advisory records — which are thousands of rows and fit any free
tier. Those are reproducible from the register, so losing them costs a recompute
and nothing else.

**Render's free Postgres tier expires after 90 days and must not be used for
anything on this project's critical path.** The first primary figure is not due
for roughly 34 weeks (§6), so any store with a 90-day lifetime guarantees data
loss before the first result exists.

---

## 11. Amendment procedure

Any change to this document requires a numbered amendment recording:

1. what changed, quoting the original text;
2. why;
3. **what had already been seen at the time of the change**, including which
   groups had matured and what they showed;
4. the commit hash of this file as it stood before the change.

Amendments are appended below and never edited. A result computed under an
amended rule cites the amendment number, and any result whose rule changed after
its window opened is republished with both figures side by side.

### Change log

*(none)*
