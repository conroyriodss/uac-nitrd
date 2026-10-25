# Task 1 match rule: `nitrd-parent-match-rule-v3-2026-10-25`

Status: COMMITTED after the FY2024 seal and before any candidate-shortlister work or any score. It
SUPERSEDES v1 and v2 for scoring. Both stay in the repo unchanged: v1 because the FY2024 seal manifest
records its SHA, v2 because it was committed.

* v1 = `docs/TASK1_MATCH_RULE.md`, sha256 `154a26e4e2253aadee611c92864c184a9d10390d88bf0fd2636ad42e1a119123`
* v2 = `docs/TASK1_MATCH_RULE_v2.md`, sha256 `93195c0a86d0652f55c7c77f66dfea3195fc8d73d5ffe4bf8460e278f674cbe5`

The scorer checks this file's SHA. Before the scorer runs, the seal log in the sealed volume must record
that v3 supersedes v1. Any later change is a new rule version with a new ID.

Why a new ID rather than editing v1: the seal (`task1-fy2024-seal-2026-10-25T17:56:21Z`, manifest
sha256 `ae63372d...e2f33b9b41`) pins v1. Rewriting v1 under the same ID would leave the seal pointing at
a rule that no longer exists.

Task: predict NITRD parent membership (public RePORTER spending category 329, "Networking and Information
Technology R&D (NITRD)") for FY2024 NIH awards. This is not the PCA subcategory task.

**Terminology.** "Fingerprint" means ONLY RCDC's thesaurus-based category fingerprint: a weighted list of
RCDC Thesaurus concepts compared with a project's concept index. Our Task 1 tool is a different mechanism
and is called the **candidate shortlister** (or parent-match model). Existing file names, IDs and
environment variables that contain "fingerprint" are pinned audit references and keep their names.

## 0. Pinned inputs

| File | SHA-256 |
| --- | --- |
| `build/universe/fy2021.csv` | `d7f7fadd03bb8cfce75ec0cf8329c232d8c3ffc89c73d4b58533baf743832abf` |
| `build/universe/fy2022.csv` | `5126368e4971542e6b4d3ad0f1f027a7da3af52ea83e5a4d345022c7581a4079` |
| `build/universe/fy2023.csv` | `d96da7b3cbb33d04eb81fa8272f3683348c7ab00acf276e40a1e2a41480338a3` |
| `build/universe/fy2024_identity.csv` | `9d996db94774a9b7e4b450361d4d903182411cd346a3b810b99938a3ee10936c` |
| `build/baseline/carry_forward_fy2024.predictions.csv` | `b57aab61d646ca423831c209760abb4ccfe0364f910f0e249abd57b7ffbfaff5` |
| `docs/seal/task1_fy2024_seal_manifest.json` | `ae63372d8e34402aeb2e5f2c7338530cbf106a059b6a0fe74461e8e2f33b9b41` |
| `docs/TASK1_MATCH_RULE.md` (v1, superseded) | `154a26e4e2253aadee611c92864c184a9d10390d88bf0fd2636ad42e1a119123` |
| `docs/TASK1_MATCH_RULE_v2.md` (v2, superseded) | `93195c0a86d0652f55c7c77f66dfea3195fc8d73d5ffe4bf8460e278f674cbe5` |
| `fixtures/UAC_Uncoded_12-01-2025-updated-NIH_ODSS.csv` | `8c92c8af62b65b9a48b913c83d4c9f61f6f8956b84f0ceede9ba1eb1067edb9c` |

Other references:
* Universe: `task1-build-universe-v1-2026-10-25`. Baseline: `carry-forward-v1-2026-10-25`.
* File A original (exposure flag, identity columns only): sha256
  `fa6940d2bfa4f2445e0eaee3eadf2c173dd69d03a0552e28cb8fe09ec2488830`.

`tests/test_task1_match_rule.py` fails if any pinned file stops matching.

## 1. Purpose and positioning (RCDC maintenance)

Owner-stated, 2026-10-25:

* **Supports General Maintenance** through the candidate shortlister (Task 1) and the subcategory engine
  (Task 2). Both propose; ICO/SME reviewers accept, reject or add in the governed store.
* **Supports Fundamental Maintenance** through the drift report (Task 3). It summarises over-captures (SME
  rejections) and under-captures (SME adds) for SME review, and never edits a definition.
* **Does not support Revisit maintenance** (structural redefinition of the PCAs).
* **What the score compares against:** the published FY2024 category-329 membership at seal time T. That
  membership comes from RCDC's thesaurus-based fingerprint plus its business rules.
  * The fingerprint version is **unknown**: it is not exposed by RePORTER or by the public RCDC and NITRD
    pages. The RCDC FAQ states fingerprints are reviewed and updated each year.
  * RCDC indexes specific aims, which RePORTER does not publish. The shortlister sees title, abstract and
    public health relevance only.

## 2. Universe and label (fixed at seal time T = 2026-10-25T17:56:21Z)

**Primary universe U:** all 79,721 FY2024 NIH appl_ids in the sealed key. That is every funding
instrument (grants, contracts, intramural, other transactions) and every subproject. The appl-level label
is the record's category-329 flag at T, read only from the sealed key in the scoring run.

How the population question was resolved (identity columns and build-year labels only, 2026-10-25):

* **The RCDC download is a reporting view.** The download shows FY2023 NITRD at 3,403 awards under
  "Extramural Grants + Admin Supplements, Contact PI Only, Primary/Admin Projects Only". Our FY2023 pull has
  4,583 category-329 records in 4,104 cores. Applying the RCDC-view filter (below) to the committed FY2023
  universe gives 3,407 records in 3,241 cores. That is 4 records from the download figure (download date
  and Contact-PI handling not recorded), so the gap is the filter.
* **The filter removes:**
  * 933 subprojects;
  * 127 intramural records;
  * 74 contracts (53 `75N` plus 21 legacy numeric contract numbers);
  * 42 other transactions.
* **What UAC coders actually see:** the committed UAC worklist (the 480, pinned above), using its own
  `Class Code`, `Activity Code` and `SubProj` columns, includes:
  * 15 contracts (C);
  * 9 intramural records (M);
  * 45 other transactions (O, all OT2);
  * 1 interagency record (I);
  * 81 subprojects.

  So coders do assign categories outside the RCDC-view filter.
* **Decision:** scoring stays on all of U. Restricting to the RCDC view would drop records that coders
  label. The RCDC view is reported as a labelled secondary.

**RCDC-view filter** (secondary, exact). It is computed from identity at score time, so no re-seal is
needed. Keep a record only if all of these hold:
* `subproject_id` is empty;
* the activity code (first three characters of `core_project_num`) does not start with `Z` (intramural);
* it is not a contract: `75N`, `N` followed by two digits, `HHS`, or starting with a digit;
* it does not start with `OT` (other transaction).

"Contact PI only" changes nothing, because RePORTER returns one record per appl_id.

## 3. Primary key

* The primary unit is `core_project_num` as RePORTER returns it. `appl_id` is the secondary key.

## 4. Subprojects and the core label

* A subproject is one more record of its core.
* A core is positive if ANY of its FY2024 records is flagged 329 at T, otherwise negative. Cores with
  mixed labels count as positive, and their count is reported.

## 5. Predictions, granularity, outcomes

* The shortlister outputs exactly one row per appl_id in U: `appl_id`, `decision` (`candidate`,
  `not_candidate` or `abstain`), `score` (a finite real number, higher = more likely), and `reason`.
* Core aggregation:
  * a core is predicted positive if any of its records is `candidate`;
  * a core's score is the maximum of its records' scores;
  * a core abstains only if all its records abstain.
* `abstain` is allowed only with reason `no_public_text`: the sealed text snapshot has neither a title nor
  an abstract. The seal froze 0 such records. A further 375 records have a title but no abstract; they are
  NOT abstentions.
* Outcomes:
  * hit = candidate, label positive;
  * over-capture = candidate, label negative;
  * miss = label positive, decision not_candidate or abstain;
  * correct negative = not_candidate, label negative.
* Abstentions are left out of the precision denominator and reported separately.
* Only the frozen shortlister output is scored. SME decisions are never scored.
* STOP (no score is computed) on any of:
  * a seal, spec or pinned-input SHA mismatch;
  * an appl_id outside U, a missing appl_id, or a duplicate appl_id;
  * a decision value outside the three allowed;
  * a non-finite score;
  * an abstain with another reason, or on a record that has text in the snapshot;
  * the seal log not recording the supersession to v3.

## 6. Groups and metrics

Groups are computed from identity and build-year labels only, never from FY2024 labels. Rule 67 cores
(section 7) are removed from every group before scoring.

* **New Project:** the core has no NIH record in FY2021-2023 (sealed stratum `new`: 15,472 cores, of which
  14,777 are not File A exposed and 695 are).
  * Deviation recorded: the owner asked for "no prior core project in any FY". The committed build universe
    covers FY2021-2023 only, so "any FY" means any FY in that window. Extending it would need a new
    identity-only pull for FY2008-2020 (label-free, a new universe version). A core with a record before
    FY2021 but none in FY2021-2023 counts here as a New Project.
* **New in Category:** the core has at least one NIH record in FY2021-2023, and its prior label (the "any"
  label in the most recent of those FYs, from the committed build universe) is 0. Its positives are the
  cores that entered category 329 in FY2024.
* **Continuing in Category** (secondary): prior label 1. Its misses are the cores that left category 329.
* **File A exposed:** the core appears in File A in any FY.
  * File A lists category-329 projects, so for New Project and New in Category cores, exposure mostly comes
    from FY2024/2025 File A and implies a positive. That is why H2 excludes them.

**Headline: two PAIRS, four figures, all with equal prominence**, at core level on the scored set:

| | H1: all cores in group | H2: cores not File A exposed |
| --- | --- | --- |
| New Project | NP-H1 | NP-H2 |
| New in Category | NiC-H1 | NiC-H2 |

For each figure:
* precision (strict: every over-capture counts);
* recall (section 7: (a) misses only);
* shortlist size, number of positives, TP/FP/FN/TN counts;
* Wilson 95% intervals.

No figure is secondary to another.

**Divergence flag.** Within each pair, if H1 and H2 differ by more than 3 percentage points (absolute) in
precision or in recall, the result carries `HEADLINE_DIVERGENCE`, naming the group, metric(s) and both
values, wherever the pair appears.

**Operational and dollar metrics** (secondary, each labelled, computed for all four headline figures):

* **Dollar-weighted precision and recall.** Each core is weighted by the sum of FY2024 `award_amount`
  across its records, in place of 1.
  * Precision$ = $ of hits / $ of candidates. Recall$ = $ of hits / $ of positives.
  * Amounts come from a label-free FY2024 amounts file (appl_id + award_amount only, no category or text
    field), pulled and pinned by SHA before the scorer runs. A null amount counts as $0, and the number of
    such records is reported.
* **SME review effort to 95% recall.** This is the General Maintenance operational metric.
  1. Rank the shortlisted cores (candidates) by core score, descending; ties go by `core_project_num`
     ascending.
  2. k* = the smallest k such that the top k contain at least ceil(0.95 * positives in the group) hits.
  3. Report k* / shortlist size and k*.
  4. If the whole shortlist holds fewer hits than that, report `NOT_REACHED`, the shortlist's recall, and
     (labelled) the review fraction needed to recover 95% of the shortlist's own hits.

Other secondary figures, each labelled:
* New Project and New in Category cores that are File A exposed;
* Continuing in Category against the pinned carry-forward baseline;
* all cores combined (derived only);
* the same metrics at appl_id level;
* the RCDC-view filter (section 2) applied to every headline figure;
* precision excluding attributed (c) and (d) over-captures, only if determinable;
* the "all" rule sensitivity check.

Rules:
* Precision with no candidates is n/a.
* The shortlister version, threshold and score are frozen before the reveal.
* No threshold sweep, no per-group thresholds, no dropped groups, no re-scoring after the reveal.

## 7. Rule-attributed outcomes: Rules 67, 91, 1

An outcome is attributed to an RCDC business rule only by the mechanical test fixed here. It is never
attributed by judgment after the score.

**(b) Rule 67: mechanism-based inclusion.**
* Test: cores whose activity code is F37, F38, G07 or G08.
* These cores are EXCLUDED from every scored group before scoring.
* FY2024 identity count: 10 records in 9 cores, all G08. F37, F38 and G07 do not occur in FY2021-2024.
* Mandatory result line: "Rule 67 excluded: N records / M cores", plus how many carry the 329 flag and how
  many the shortlister marked candidate.
* The same exclusion applies to the build-year training labels.
* In the build years, 5 of 8 FY2023 G08 cores are category 329.

**(a) Model failure.**
* Every miss in the scored set is (a).
* Headline recall counts (a) and only (a): recall = hits / (hits + (a)).

**(c) Rule 91: reassignment to Climate Change / Nanotechnology.**
**(d) Rule 1: captured but not subcategorized (the "480-equivalent").**

Deviation from the owner's instruction, recorded deliberately and carried from v2. (c) and (d) cannot be
misses:
* A project that Rule 91 reassigned away from NITRD has a published category-329 label of 0. If the
  shortlister flags it, it is an **over-capture**; otherwise it is a correct negative.
* A Rule 1 dropout is either still in 329 (an ordinary hit or (a) miss) or dropped from it (an
  over-capture).

So (c) and (d) are mandatory separate lines on the **over-capture** side, and neither can lower headline
recall. Each is attributed only when a mechanical source covering FY2024 at T exists:
* (c) a Rule 91 routing record, or a separately authorized, sealed and logged FY2024 membership read for
  "Nanotechnology" and "Climate-Related Exposures and Conditions" (proxy);
* (d) a per-project subcategory status, or ICO validation records (section 9).

RePORTER exposes neither. With no source, each line reads "not determinable from public data", and those
over-captures stay in headline precision.

Mandatory result lines:
* Rule 67 excluded;
* (c);
* (d);
* abstentions by label;
* null-amount records.

## 8. FY2024 label reads before the seal

Recorded in the seal manifest as `fy2024_label_reads_before_seal`:

1. **2026-10-25, 2023->2024 carry-forward agreement check.** Aggregates only, per-project sets deleted,
   nothing per-project printed or saved.
   * FY2024: 4,758 category-329 records; 4,320 positive cores ("any"); 840 mixed cores.
   * Cores in both years: 45,603. "Any" rule: 2,969 / 42,313 / 148 / 173 (both / neither / only FY2023 /
     only FY2024). "All" rule: 2,216 / 43,100 / 125 / 162.
2. **2026-10-25, Task 1 reconnaissance:** the FY2024 category-329 record count (4,758). Count only.
3. **2026-10-25, File A selection-effect check:** File A FY2024 identity counts (2,281 appl_ids, 2,155
   cores; 1,365 overlap with FY2021-2023 File A cores). Aggregates only.

No FY2024 label has been read since the seal. The FY2008-2025 category-329 count pivot reused entry 2's
value for FY2024. The FY2024 co-funding count was not conditioned on category 329. The FY2024
mechanism-by-329 pivot was withheld.

Read relevant to a future FY2026 seal: on 2026-10-25, FY2026 had 67,593 NIH records, 0 in category 329,
and none of 500 sampled records carried any spending category.

## 9. Known unknown: ICO validation records

If RCDC retains per-project ICO validation decisions on parent-category membership (approve or reject), or
MR/UE flags, they would be a directly labelled dataset for this task and could attribute (c) and (d).
* Status: **unknown**. They are not in RePORTER or in any public RCDC page reviewed. Access would have to
  come from the RCDC team.
* Not a blocker for scoring.
* If obtained, any use is governed by a new rule version. FY2024 records count as FY2024 labels and are
  off-limits to the build.

## 10. Committed with or before the scorer

* The scorer and its SHA, with a `--validate-only` mode tested on a synthetic key.
* The FY2024 amounts file and its SHA (label-free).
* The seal-log entry recording the supersession to v3.
