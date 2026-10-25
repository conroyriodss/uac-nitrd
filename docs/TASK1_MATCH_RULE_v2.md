# Task 1 match rule: `nitrd-parent-match-rule-v2-2026-10-25`

Status: COMMITTED after the FY2024 seal and before any candidate-shortlister work or any score. It
SUPERSEDES `nitrd-parent-match-rule-v1-2026-10-25` (`docs/TASK1_MATCH_RULE.md`, sha256
`154a26e4e2253aadee611c92864c184a9d10390d88bf0fd2636ad42e1a119123`) for scoring. v1 stays in the repo
unchanged because the FY2024 seal manifest records its SHA. The scorer must check this file's SHA, and
the sealed volume's seal log must record the v1 -> v2 supersession before the scorer runs. Any later
change is a new rule version with a new ID.

Why a new ID rather than editing v1: v1 was committed in `9181f03` and is pinned by the seal
(`task1-fy2024-seal-2026-10-25T17:56:21Z`, manifest sha256 `ae63372d...6e2f33b9b41`). Rewriting v1
under the same ID would leave the seal pointing at a rule that no longer exists.

Task: predict NITRD parent membership (public RePORTER spending category 329, "Networking and Information
Technology R&D (NITRD)") for every FY2024 NIH award. This is not the PCA subcategory task.

**Terminology.** "Fingerprint" means ONLY RCDC's thesaurus-based category fingerprint (a weighted list of
RCDC Thesaurus concepts compared with a project's concept index). Our Task 1 tool is a different
mechanism and is called the **candidate shortlister** (or parent-match model). Existing file names, IDs and
environment variables that contain "fingerprint" are pinned audit references and keep their names.

Owner sign-offs (2026-10-25):
* "new" = no record in FY2021-2023;
* the headline is a PAIR (section 7);
* the core label rule is "any" record is 329, with "all" kept as the sensitivity check;
* Rule 67 excluded and reported separately (section 6).

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

Other references:
* Universe files: `task1-build-universe-v1-2026-10-25`.
* Baseline: `carry-forward-v1-2026-10-25`.
* File A original (exposure flag, identity columns only): sha256
  `fa6940d2bfa4f2445e0eaee3eadf2c173dd69d03a0552e28cb8fe09ec2488830`.
* Sealed key aggregate: sha256 `81350a5328ceb485eb41c7095765c3a7f2d5f8f648cc7b2159610b8bf52efc02`.

`tests/test_task1_match_rule.py` fails if any pinned file stops matching.

## 1. Purpose and positioning (RCDC maintenance)

Owner-stated positioning, 2026-10-25:

* **Supports General Maintenance:** adjusting the category definition based on ICO expert validation.
  The candidate shortlister proposes NITRD-parent candidates; ICO/SME reviewers accept, reject or add in
  the governed store.
* **The Task 3 drift report also supports Fundamental Maintenance.** It summarises over-captures
  (SME rejections) and under-captures (SME adds) for SME review. It never edits a definition.
* **Does not support Revisit activities** (structural redefinition of the PCAs).
* **What the score compares against:** the published FY2024 category-329 membership at seal time T. That
  membership was produced by RCDC's thesaurus-based fingerprint and business rules.
  * The fingerprint version is **unknown**: it is not exposed by RePORTER or by the public RCDC and NITRD
    pages. The RCDC FAQ states fingerprints are reviewed and updated each year.
  * RCDC indexes specific aims, which RePORTER does not publish. The shortlister sees title, abstract and
    public health relevance only.

## 2. Universe and label (fixed at seal time T = 2026-10-25T17:56:21Z)

* U = the 79,721 FY2024 NIH appl_ids in the sealed key.
* The appl-level label is the record's category-329 flag at T, read from the sealed key only (scoring run).

## 3. Primary key

* The primary unit is `core_project_num` as RePORTER returns it. `appl_id` is the secondary key.

## 4. Subprojects and the core label

* A subproject is one more record of its core.
* A core is positive if ANY of its FY2024 records is flagged 329 at T, otherwise negative. Cores with
  mixed labels count as positive, and their count is reported.

## 5. Predictions, granularity, outcomes

* The shortlister outputs exactly one row per appl_id in U, with decision `candidate`, `not_candidate`
  or `abstain`. Rule 67 records are included in the output but are not scored (section 6).
* A core is predicted positive if any of its records is `candidate`. A core abstains only if all its
  records abstain. A core-level method copies its decision to every record of that core.
* `abstain` is allowed only with reason `no_public_text`: the sealed text snapshot has neither a title nor
  an abstract. The seal froze 0 such records. A further 375 records have a title but no abstract; they
  are NOT abstentions.
* Outcomes:
  * hit = candidate, label positive;
  * over-capture = candidate, label negative;
  * miss = label positive, decision not_candidate or abstain;
  * correct negative = not_candidate, label negative.
* Abstentions are left out of the precision denominator and reported separately.
* Only the frozen shortlister output is scored. SME accept, reject and add decisions are never scored.
* STOP (no score is computed) on any of:
  * a seal, spec or pinned-input SHA mismatch;
  * an appl_id outside U, a missing appl_id, or a duplicate appl_id;
  * a decision value outside the three allowed;
  * an abstain with another reason, or on a record that has text in the snapshot;
  * the seal log not recording the v1 -> v2 supersession.

## 6. Rule-attributed outcomes: Rules 67, 91, 1

An outcome is attributed to an RCDC business rule only by the mechanical test fixed here. It is never
attributed by judgment after the score.

**(b) Rule 67: mechanism-based inclusion.**
* Test: cores whose activity code (the first three characters of `core_project_num`) is F37, F38, G07 or
  G08.
* These cores are EXCLUDED from every scored group before scoring.
* FY2024 identity count: 10 records in 9 cores, all G08. F37, F38 and G07 do not occur in FY2021-2024.
* Mandatory result line: "Rule 67 excluded: N records / M cores", plus how many carry the 329 flag and
  how many the shortlister marked candidate.
* The same exclusion applies to the build-year training labels.
* In the build years the rule is not fully visible in public labels: 5 of 8 FY2023 G08 cores are
  category 329.

**(a) Model failure.**
* Every miss in the scored set (after the Rule 67 exclusion) is (a).
* Headline recall counts (a) and only (a): recall = hits / (hits + (a)).

**(c) Rule 91: reassignment to Climate Change / Nanotechnology.**
**(d) Rule 1: captured but not subcategorized (the "480-equivalent").**

Deviation from the owner's instruction, recorded deliberately. The owner asked that (c) and (d) be
classes of misses. They cannot be:
* A project that Rule 91 reassigned away from NITRD has category-329 = 0 in the published label. If the
  shortlister marks it candidate, it is an **over-capture**; if not, it is a correct negative.
* A Rule 1 dropout is either still in category 329 (then it is an ordinary positive: a hit or an (a)
  miss) or dropped from it (then it is an over-capture).

So (c) and (d) are reported as separate lines on the **over-capture** side, and neither can lower
headline recall. Each is attributed only when a mechanical source covering FY2024 at T exists:
* (c) a Rule 91 routing record, or a separately authorized, sealed and logged FY2024 membership read for
  "Nanotechnology" and "Climate-Related Exposures and Conditions" (proxy only);
* (d) a per-project subcategory status, or ICO validation records (section 9).

RePORTER exposes no routing field and no subcategories. With no source, each line reads "not
determinable from public data", and those over-captures stay in headline precision.

## 7. Groups and metrics

Groups are computed from identity only and stored in the sealed key:
* new core = no NIH record in FY2021-2023;
* continuing core = at least one record in FY2021-2023, prior label = the "any" label in the most recent of
  those FYs;
* File A exposed = the core appears in File A, any FY.

Sealed counts: new 14,777 not exposed + 695 exposed = 15,472; continuing 45,279 + 1,757. Rule 67 cores
are removed from these before scoring.

**Headline: a PAIR, reported side by side with equal prominence**, both at core level on the scored set:
* **H1: all new cores.**
* **H2: new cores not exposed in File A.**

For each: precision (strict: every over-capture counts), recall (section 6), shortlist size, number of
positives, TP/FP/FN/TN counts, and Wilson 95% intervals. Neither is secondary to the other.

**Divergence flag.** If H1 and H2 differ by more than 3 percentage points (absolute) in precision or in
recall, the result carries `HEADLINE_DIVERGENCE`, naming the metric(s) and both values, wherever the pair
appears.

Mandatory lines:
* Rule 67 excluded (section 6 b);
* Rule 91 over-captures (c);
* Rule 1 over-captures (d);
* abstentions by label.

Secondary figures, each labelled as secondary:
* new cores exposed in File A;
* continuing cores against the pinned carry-forward baseline;
* continuing cores whose label changed (entering and leaving 329);
* all cores combined (derived only);
* the same metrics at appl_id level;
* precision excluding attributed (c) and (d) over-captures, only if they are determinable;
* the "all" rule sensitivity check.

Rules:
* Precision with no candidates is n/a.
* The shortlister version and threshold are frozen before the reveal.
* No threshold sweep, no per-group thresholds, no dropped groups, no re-scoring after the reveal.

## 8. FY2024 label reads before the seal

Carried unchanged from v1 and recorded in the seal manifest as `fy2024_label_reads_before_seal`:

1. **2026-10-25, 2023->2024 carry-forward agreement check.** Aggregates only, per-project sets deleted,
   nothing per-project printed or saved.
   * FY2024: 4,758 category-329 records; 4,320 positive cores ("any"); 840 mixed cores.
   * Cores in both years: 45,603. "Any" rule: 2,969 / 42,313 / 148 / 173 (both / neither / only FY2023 /
     only FY2024). "All" rule: 2,216 / 43,100 / 125 / 162.
2. **2026-10-25, Task 1 reconnaissance:** the FY2024 category-329 record count (4,758). Count only.
3. **2026-10-25, File A selection-effect check:** File A FY2024 identity counts (2,281 appl_ids, 2,155
   cores; 1,365 overlap with FY2021-2023 File A cores). Aggregates only.

No FY2024 label has been read since the seal.

Read relevant to a future FY2026 seal: on 2026-10-25, FY2026 had 67,593 NIH records, 0 in category 329,
and none of 500 sampled records carried any spending category. FY2026 categorization had not been
published.

## 9. Known unknown: ICO validation records

If RCDC retains per-project ICO validation decisions on parent-category membership (approve or reject),
they would be a directly labelled dataset for this exact task, and could attribute (c) and (d).
* Status: **unknown**. They are not in RePORTER (no such field) or in any public RCDC page reviewed.
  Access would have to come from the RCDC team.
* Not a blocker for scoring.
* If obtained, any use is governed by a new rule version. FY2024 validation records count as FY2024
  labels and are off-limits to the build.

## 10. Committed with or before the scorer

* The scorer and its SHA, with a `--validate-only` mode tested on a synthetic key.
* The seal-log entry recording v1 -> v2.
