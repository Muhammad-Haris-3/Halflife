# Halflife — feasibility check

**Checked 28 August 2026, before any collection has begun and before
`PREREGISTRATION.md` exists. Every number below was measured against the live
APIs, not quoted.** Raw pilot output in [`data/pilot/`](data/pilot/), the two
scripts that produced it in [`scripts/`](scripts/).

Nothing in this document is a result. It is a check on whether a result is
obtainable, and the pilot data described here is explicitly **not** part of any
figure the project later publishes.

---

## Verdict

**Build it — but not with the control group that was pitched.** The measurement
premise holds and is stronger than expected. The identification strategy was
wrong, and this check is what caught it. A better one survived and is stated in
§5.

---

## 1. The load-bearing fact

Everything depends on one property of the npm API, so it was checked first.

| Endpoint | Result |
|---|---|
| `api.npmjs.org/versions/{pkg}/last-week` | **200** — downloads split by version |
| `api.npmjs.org/versions/{pkg}/range/{from}:{to}` | **404** |
| `api.npmjs.org/versions/{pkg}/last-month` | **404** |
| `api.npmjs.org/downloads/range/{period}/{pkg}` | 200, but **package total only** — no version split |

**npm publishes the per-version download split for a rolling seven days and
archives nothing.** The historical distribution is not merely inconvenient to
obtain, it is unobtainable after the fact — by anyone, including npm's own
public API.

This is the entire justification for the project. The record exists only if
someone keeps it, the clock cannot be rewound, and no amount of later effort
substitutes for having started earlier.

Supporting sources, all free and keyless, all verified returning usable fields:

- **OSV** `api.osv.dev/v1/query` — advisory id, `published`, severity, and
  `affected.ranges` with `introduced` / `fixed` / `last_affected` events.
- **GitHub Advisory API** — ecosystem filter, severity, `first_patched_version`.
- **registry.npmjs.org/{pkg}** — per-version publish timestamps (js-yaml: 91).

---

## 2. Exposure pilot — 27 packages

Current weekly downloads classified against published advisories:

```
TOTAL   5,030,773,360 weekly downloads    929,743,151 on advised versions   18.5%
```

| package | weekly downloads | on advised versions | oldest advisory |
|---|---|---|---|
| request | 14,415,603 | **100.0%** | 2018-11-09 |
| ip | 8,740,334 | **100.0%** | 2024-02-08 |
| tar | 87,699,722 | 68.8% | 2017-10-24 |
| axios | 121,741,524 | 57.4% | 2019-05-29 |
| body-parser | 138,647,450 | 54.4% | 2024-09-10 |
| qs | 182,568,783 | 53.8% | 2017-10-24 |
| ws | 268,042,391 | 44.4% | 2019-02-18 |
| lodash | 175,914,754 | 41.3% | 2018-07-26 |

`request` and `ip` are at 100% because **no fixed version exists**. That is a
categorically different condition from "a fix exists and has not been adopted,"
and the two must never be pooled into one figure. Separating them is a
requirement, not a refinement.

**This 18.5% is not the project's result and must not be published as one.**
npm downloads are not installs and not production exposure — CI re-pulls,
registry mirrors and cold caches inflate every row. The number is here to
establish that the phenomenon is large enough to be worth measuring properly,
and for no other purpose.

---

## 3. Power

The check that killed the previous candidate project, run first this time.

Measured over **600 unique advisories** spanning **70 days** (2026-06-18 to
2026-08-27), paginated by cursor. An earlier pass using a `page` parameter
returned the same 100 advisories four times — GitHub's advisories API is
cursor-paginated and silently ignores `page`. The figures below are from the
corrected pass.

| | Measured |
|---|---|
| Unique advisories / window | **600 over 70 days** → **~261 / month** |
| Distinct packages named | **279** |
| Advisory-package pairs | **928** |
| Advised packages with ≥10,000 weekly downloads | **134 / 279 = 48%** |
| Share of *advisories* landing on those packages | **73.0%** |
| Of those, carrying a fixed version | **88.3%** |
| Advised packages with **zero** weekly downloads | **65 / 279 = 23.3%** |

**The rate is bursty.** The most recent 22 days of that window ran at ~138
advisories/month against ~261/month across the full 70 days, so capacity
planning should use the lower figure and power calculations the higher one.

At ~73% advisory capture, six months yields well over a thousand candidate
events — the constraint is the frame and the pre-period requirement, not the
advisory supply. `js-yaml` — 296M weekly downloads — took a `high` advisory
during the window and published 5.4.1, 4.3.2 and 3.15.2 on the same day, the
backport-across-maintained-majors signature of a security fix.

**The 23.3% with zero downloads matter.** These are removed or malicious
packages, published and taken down inside the window. They have no adoption
dynamics to measure, and a frame frozen before they existed excludes them by
construction rather than by a filter applied after the fact.

Advisory range parsing is not a risk: **192 / 192 OSV range events (100%) parsed
cleanly as semver.**

---

## 4. The design that was wrong

The pitch proposed comparing the download decay of a version **named** by an
advisory against the decay of a version of the same package that **no advisory
named**, using background version churn as the counterfactual.

That control cannot be built. Measured across 14 packages, superseded versions
only, latest excluded:

| package | advised versions | control versions | median age advised (days) | median age control (days) | age-overlapping pairs |
|---|---|---|---|---|---|
| js-yaml | 81 | 8 | 4005 | 20 | **0** |
| axios | 139 | 4 | 1311 | 70 | **0** |
| lodash | 115 | 1 | 4113 | 149 | **0** |
| tar | 151 | 1 | 2529 | 37 | **0** |
| ws | 175 | 12 | 3201 | 44 | **0** |
| qs | 147 | 1 | 3461 | 103 | **0** |
| semver | 95 | 23 | 4171 | 840 | 95 / **0** |
| node-fetch | 80 | 15 | 3112 | 1322 | 11 / 5 |
| minimist | 27 | 3 | 4399 | 1416 | 2 / 2 |

**Packages with any age-overlapping control arm: 3 of 14.** In two of those the
overlap is one or two versions.

The reason is structural and should have been obvious. A mature, heavily-used
package has accumulated a decade of advisories, and advisories name *ranges* —
so nearly every old version is named by something. The versions no advisory
touches are the recent ones. Advised versions have a median age of eight to
twelve years; their would-be controls have a median age of weeks to months.

Comparing an eight-year-old version's decay against a three-week-old version's
growth would have produced a large, clean, entirely artefactual result. The
naive comparison does not fail loudly — it fails by returning exactly the answer
the project hoped to find.

---

## 5. The design that survived

The error was choosing the wrong unit. The comparison is not *advised version vs
non-advised version*. It is **the same version, before and after the advisory.**

A version's share of its package's downloads follows some decay trajectory
already. An advisory is an event landing on that trajectory. The question is
whether the decay rate **changes at the event** — an event study, with the
version as its own control, which removes every package-level and version-level
confound that killed §4.

This requires precisely what the project collects and what npm destroys: weekly
per-version snapshots spanning the advisory date. It is unanswerable with any
data obtainable today.

Concurrent trend controls come from packages that received no advisory that
week, matched on download volume and version age. For difference-in-differences
the requirement is **parallel pre-trends**, not equal levels or equal ages —
which is why cross-package controls work where the within-package matched pairs
of §4 did not.

**The consequence for the collection schedule**, and the rule that must go into
pre-registration: an advisory is only admissible if the register already holds
enough pre-advisory weekly observations of its named versions to test the
pre-trend. Advisories published before collection began are permanently
inadmissible to the primary analysis. The observation window does not start when
the project starts — it starts one pre-trend period later.

---

## 6. Collection cost

Measured over 15 packages: mean response **14.1 KB**, mean **553 versions per
package**, **0.85 s/package** including a 0.1 s courtesy delay.

| Cohort | Raw per week | Raw per year | Gzipped per year | Poll duration |
|---|---|---|---|---|
| 1,000 | 14.5 MB | 0.8 GB | ~0.1 GB | 14 min |
| 5,000 | 72.3 MB | 3.8 GB | ~0.5 GB | 71 min |
| 10,000 | 144.7 MB | 7.5 GB | ~0.9 GB | 141 min |

**Cost: zero.** Three free keyless APIs, GitHub Actions unlimited on public
repositories, and a 71-minute poll sits well inside the 6-hour job ceiling.
Storage growth is real and needs the compaction plan written before it bites,
not after.

### 6.1 Two facts that constrain the frame

**npm rate-limits the downloads API.** Sustained bulk querying returned
`HTTP 429 Too Many Requests` during cohort sampling. Any poll design must carry
backoff and retry, and the 0.85 s/package figure above is a floor, not an
estimate of real wall-clock time under load.

**A download-threshold frame is not constructible, and would be too large
anyway.** Scoped packages are **38.1% of the registry** — 1,653,334 of
4,335,856, measured from `_all_docs` offsets — and npm's bulk downloads endpoint
**rejects scoped names** (`HTTP 400`), capping at **128 unscoped names** per
request. Ranking the registry to find every package above a threshold would take
~1.65M individual requests against free infrastructure.

Stratified sample (2,322 unscoped, 875 scoped, drawn 2026-08-28) estimating how
many packages clear each threshold:

| Threshold | Estimated packages | 95% CI | Weekly poll | Weekly raw |
|---|---|---|---|---|
| ≥ 1M | 6,932 | 1,392 – 12,471 | 1.6 h | 95 MB |
| ≥ 100k | 11,553 | 4,408 – 18,698 | 2.7 h | 159 MB |
| ≥ 10k | **20,795** | 11,225 – 30,364 | **4.9 h** | 286 MB |
| ≥ 1k | 36,547 | 23,682 – 49,413 | 8.6 h | 503 MB |

A ≥10k frame is a ~4.9-hour weekly job before backoff, against a 6-hour ceiling.
That is not a margin worth building on.

**These estimates are weak and should be treated as order-of-magnitude only.**
The scoped stratum returned **zero** hits above 10k in 875 draws, so the totals
are carried almost entirely by the unscoped stratum. Popular scoped packages
plainly exist — `@babel/core` alone is 181,521,533 weekly downloads — they are
simply too rare to catch in a uniform sample of a registry where most scoped
names are private-adjacent and near-dormant. The true counts are higher than the
table says, which strengthens rather than weakens the conclusion.

---

## 6.2 The closure frame was built and it failed

The frame rule drafted in `PREREGISTRATION.md` §2.1 — dependency closure of a
fixed seed — was built and checked against the 600-advisory sample **before
freezing**. It does not work.

Seed of 79 packages spanning UI frameworks, meta-frameworks, server frameworks,
build tools, test runners, linters, ORMs, transports, state, styling, CLI
tooling, logging and utilities. `dependencies` + `peerDependencies`, depth 3,
zero manifest failures.

| depth ≤ | frame size | advised pkgs caught | **% of advisories caught** |
|---|---|---|---|
| 0 | 79 | 10 | 8.2% |
| 1 | 833 | 25 | 15.0% |
| 2 | 1,646 | 32 | 18.2% |
| **3** | **2,248** | **35** | **19.2%** |

**19.2%**, against the 73.0% a ≥10k-download frame would reach. Depth is not the
fix: going from depth 2 to depth 3 added 602 packages and bought **1.0
percentage point**. The closure saturates on low-value transitive utilities.

**102 missed packages have ≥10,000 weekly downloads, between them carrying 507
advisories.** The largest misses:

| weekly downloads | package | advisories |
|---|---|---|
| 175,503,782 | `pnpm` | **31** |
| 62,680,490 | `dompurify` | 2 |
| 58,685,094 | `hono` | 7 |
| 34,320,857 | `linkify-it` | 2 |
| 25,034,197 | `pdfjs-dist` | 1 |
| 19,243,722 | `crypto-js` | 1 |
| 15,212,808 | `mermaid` | 8 |

The reason is structural. Advisories do not concentrate in the dependency trees
of application frameworks. They land on **standalone tooling** (`pnpm`,
`mermaid`, `pdfjs-dist`), on **application-level libraries** nobody's framework
depends on (`dompurify`, `crypto-js`, `adm-zip`), and on **newer ecosystem
packages** outside any established seed (`hono`, `valibot`, `deepmerge-ts`). No
closure of a hand-picked seed reaches them, and enlarging the seed by hand is
just moving the arbitrariness around.

### The comparison that decides it

| Frame | Packages | % advisories | Weekly poll |
|---|---|---|---|
| closure (seed 79, depth ≤3) | 2,248 | **19.2%** | 32 min |
| ≥ 1M downloads | ~6,932 | 43.0% | 98 min |
| ≥ 100k downloads | ~11,553 | 59.4% | 164 min |
| ≥ 10k downloads | ~20,795 | 73.0% | 295 min |

Download rank is the better selector because it correlates with advisory
incidence directly, which is a measured fact rather than an assumption. The
closure is more efficient *per package* and cannot scale; the rank frame is less
efficient per package and buys capture linearly with poll budget.

**Consequence: `PREREGISTRATION.md` §2 is not fit to freeze and has not been
committed.** The frame must be rebuilt on download rank, which requires
exhaustively enumerating unscoped packages via the 128-name bulk endpoint
(~21,000 requests, one-time, with backoff for the `429`s in §6.1) and a separate
route for scoped packages, which the bulk endpoint rejects.

---

## 7. What is not claimed

- **Downloads are not installs and not exposure.** CI, mirrors and caches
  inflate everything. Only the before/after design of §5 is defensible, because
  that inflation is present on both sides of the event and cancels.
- **An advisory is not an exploitable condition.** Many are reachable only under
  specific usage. Halflife measures migration, never risk.
- **Spillover is unresolved.** Versions above the fix mechanically absorb what
  treated versions lose, so they cannot serve as controls. Cross-package controls
  avoid this; the choice must be fixed in pre-registration, not at analysis time.
- **npm only.** pypistats exposes package totals and category splits but no
  per-version endpoint, so PyPI would require paid BigQuery and is out of scope
  under the zero-cost constraint.
- The pilot's semver comparator ignores prerelease ordering. The collector needs
  a real resolver; the 100% parse rate in §3 says this is tractable, not done.

---

## 8. Open before pre-registration

1. **The cohort frame.** Which packages are polled weekly, fixed in code and in
   advance, so a later change of frame cannot be mistaken for a change in the
   world. Advisories are useless without pre-advisory data, so the frame must be
   chosen before anyone knows which packages will be advised.
2. **Minimum pre-advisory weeks** for an advisory to enter the primary set.
3. **The control definition**, chosen now and not after seeing a pre-trend plot.
4. **The kill condition** — the effect size below which the finding is
   "advisories do not move adoption," stated before the first snapshot.

---

## Reusable

The check that mattered was not whether the data existed. It was **whether the
comparison the design depended on could be constructed from it.** The naive
control arm looked fine in the pitch, cost nothing to test, and died to a single
table of medians in under an hour. That table should be the first thing built,
every time.
