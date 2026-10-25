# Task 1 match rule: `nitrd-parent-match-rule-v1-2026-10-25`

Status: COMMITTED before the FY2024 seal and before any fingerprint work. It replaces nothing. The seal
manifest must record this file's SHA-256. Any change after commit is a new rule version with a new ID.

Task: predict NITRD parent membership (public RePORTER spending category 329, "Networking and Information
Technology R&D (NITRD)") for every FY2024 NIH award. This is not the PCA subcategory task.

Owner sign-offs (2026-10-25): "new" = no record in FY2021-2023; the headline is a PAIR (section 6);
core label rule = "any" record is 329, with "all" kept as the sensitivity check.

## 0. Pinned inputs (group definitions and the baseline depend on these)

| File | SHA-256 |
| --- | --- |
| `build/universe/fy2021.csv` | `d7f7fadd03bb8cfce75ec0cf8329c232d8c3ffc89c73d4b58533baf743832abf` |
| `build/universe/fy2022.csv` | `5126368e4971542e6b4d3ad0f1f027a7da3af52ea83e5a4d345022c7581a4079` |
| `build/universe/fy2023.csv` | `d96da7b3cbb33d04eb81fa8272f3683348c7ab00acf276e40a1e2a41480338a3` |
| `build/universe/fy2024_identity.csv` | `9d996db94774a9b7e4b450361d4d903182411cd346a3b810b99938a3ee10936c` |
| `build/baseline/carry_forward_fy2024.predictions.csv` | `b57aab61d646ca423831c209760abb4ccfe0364f910f0e249abd57b7ffbfaff5` |

The universe files come from `task1-build-universe-v1-2026-10-25` (`build/universe/MANIFEST.json`). The
baseline is `carry-forward-v1-2026-10-25` (`workflow/baseline.py`). The File A exposure flag (section 5)
uses the sealed File A original, SHA-256 `fa6940d2bfa4f2445e0eaee3eadf2c173dd69d03a0552e28cb8fe09ec2488830`,
read through its identity columns (Appl ID, FY, Project Number) only. `tests/test_task1_match_rule.py`
fails if any pinned file stops matching.

## 1. Universe and label (fixed at seal time T)

* U = every FY2024 NIH appl_id in RePORTER at T, taken from the seal's identity snapshot. Records that
  appear after T are excluded. Records that disappear after T keep their sealed label.
* The appl-level label is the record's category-329 flag at T, read from the sealed key only. It is never
  re-pulled.

## 2. Primary key

* The primary unit is `core_project_num`, exactly as RePORTER returns it (not parsed). `appl_id` is the
  secondary key.
* A record without a core number is scored as its own unit, keyed by appl_id (none found in FY2020-2024).

## 3. Subprojects and the core label

* A subproject is one more record of the core it belongs to.
* A core is positive if ANY of its FY2024 records is flagged 329 at T, otherwise negative. Cores with
  mixed labels count as positive, and their count is reported.

## 4. Predictions, granularity, outcomes

* The fingerprint outputs exactly one row per appl_id in U, with decision `candidate`, `not_candidate`
  or `abstain`.
* A core is predicted positive if any of its records is `candidate` (this mirrors the label rule). A core
  abstains only if all its records abstain. A method that decides at core level copies its decision to
  every record of that core.
* `abstain` is allowed only with reason `no_public_text`: the sealed text snapshot has no title or
  abstract for that record.
* Outcomes:
  * hit = candidate, label positive;
  * over-capture = candidate, label negative;
  * miss = label positive, decision not_candidate or abstain (abstained positives count as misses);
  * correct negative = not_candidate, label negative.
* Abstentions are left out of the precision denominator and reported separately by label.
* Only the frozen agent output is scored. SME accept, reject and add decisions are never scored.
* STOP (no score is computed) on any of:
  * a seal, spec or pinned-input SHA mismatch;
  * an appl_id outside U, a missing appl_id, or a duplicate appl_id;
  * a decision value outside the three allowed;
  * an abstain with another reason, or on a record that has text in the snapshot.

## 5. Groups, and FY2024 label reads before the seal

Groups are computed from identity only, fixed at seal time and stored in the sealed key:

* **New core:** no NIH record in any of FY2021, FY2022 or FY2023 (pinned universe files).
* **Continuing core:** at least one record in FY2021-2023. Its prior label is its core label ("any" rule)
  in the most recent of those FYs in which it appears.
* **File A exposed:** the core appears in File A in any FY (identity columns only).

This is the definition the committed baseline already uses: FY2024 has 47,036 continuing and 15,472 new
cores. An earlier draft defined "new" as absent from FY2023 only; that wording is withdrawn.

### FY2024 label reads before the seal

The seal manifest must carry this list as `fy2024_label_reads_before_seal`, entry 1 first.

1. **2026-10-25, 2023->2024 carry-forward agreement check.** Owner-requested, public RePORTER API.
   * Read: FY2024 category-329 records, joined to the FY2023 and FY2024 universes at core level.
   * Totals reported:
     * FY2024: 4,758 category-329 records; 4,320 positive cores ("any"); 840 mixed cores.
     * Cores in both years: 45,603. "Any" rule: 2,969 positive both years, 42,313 neither, 148 only FY2023,
       173 only FY2024. "All" rule: 2,216 / 43,100 / 125 / 162.
   * Per-project sets were held in memory only and deleted. No per-project output was printed or saved.
2. **2026-10-25, Task 1 oracle reconnaissance (earlier the same day).** The FY2024 category-329 record
   count (4,758) was read from the API's result total. This was a count only.
3. **2026-10-25, File A selection-effect check.** File A identity columns only. File A has 2,281 FY2024
   appl_ids and 2,155 cores, and 1,365 of the FY2021-2023 File A cores are also FY2024 File A cores.
   Because File A rows are NITRD subcategory rows, this exposes the size of a subset of FY2024 positives.
   Aggregates only; no per-project output was saved.

Entries 2 and 3 were added for completeness. Figures quoted in later planning (for example "about 1,180
new positive cores") were derived from entry 1 and involved no further read.

## 6. Metrics (computed once, fixed denominators, no other figures)

**Headline: a pair, reported side by side with equal prominence.** Both are at core level:

* **H1: all new cores.**
* **H2: new cores not exposed in File A.**

For each: precision, recall, shortlist size (number of candidate cores), number of positives,
TP/FP/FN/TN counts, and Wilson 95% intervals for precision and recall. Neither is secondary to the other.

**Divergence flag.** If H1 and H2 differ by more than 3 percentage points (absolute) in precision or in
recall, the result must carry a `HEADLINE_DIVERGENCE` flag naming the metric(s) and both values. It must
appear wherever the headline pair appears.

Secondary figures, each labelled as secondary:

* New cores exposed in File A, for completeness of the pair.
* Continuing cores: the model's precision and recall next to the pinned carry-forward baseline predictions.
* Continuing cores whose label changed (prior label differs from the FY2024 label): recall on cores
  entering 329 and correct-negative rate on cores leaving it. The baseline scores 0 on these by
  construction.
* All cores combined, as a derived figure only.
* The same metrics at appl_id level, overall and per group (each record takes its core's group).
* Sensitivity: the "all" rule in place of "any", for both label and prediction.

Rules:

* Precision with no candidates is reported as n/a, not 0 or 1.
* The fingerprint version and threshold are frozen before the reveal.
* No threshold sweep, no per-group thresholds, no dropped groups, no re-scoring against this key after
  the reveal.

## 7. Committed with or before the scorer

* The scorer and its SHA, with a `--validate-only` mode tested on a synthetic key, never the real one.
* This rule file's SHA in the seal manifest.
