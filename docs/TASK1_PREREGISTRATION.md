# Task 1 pre-registration: NITRD parent shortlisting from an FY2021 fingerprint

**FROZEN. Pre-registration ID: `task1-prereg-v1-2026-11-04T18:00:50Z`.**
Drafted 2026-11-03 (fields settled by the owner 2026-11-03; success criteria
corrected and comparison arms added by the owner 2026-11-03, sections 6a, 7;
section 6a rewritten as "Model comparison" by the owner 2026-11-03; owner
decisions of 2026-11-04 applied). Frozen 2026-11-04, ahead of the 2026-11-07
target, while public RePORTER showed 0 FY2026 category-329 records (count
only, 2026-11-04T17:54:25Z; 67,665 NIH FY2026 records). The FY2024 freeze run
(section 0 step 3) was committed first, in `5e3bfa4`. This file's own SHA-256
cannot be written inside it. It is recorded in the commit that adds this
file, in uac-witness record 0004 and in seal-log line 33.

Commit SHAs: this repository's history was rewritten once, on 2026-11-04, to
remove the non-public PCC column from the FY2025 fixture (uac-witness record
0003). Commits are cited by their current SHA, followed by the SHA they had
when they were pushed.

## 0. Freeze procedure

1. The read guard (`workflow/build_guard.py`, spec
   `docs/TASK1_READ_GUARD_SPEC.md`) passes its tests (blocking in CI).
2. The fingerprint, shortlist rule and FY2026 forecast are built under the
   guard; their READ_MANIFESTs list only allow-listed inputs (A1-A2).
3. Code, fingerprint and FY2026 forecast are committed, and so is every
   comparison arm that is to count (section 6a), each with its READ_MANIFEST.
   Then, in the freeze run
   (`UAC_NITRD_TASK1_FREEZE_RUN=1`, clean committed tree), the FY2024 ranking is
   computed from the sealed-manifest text snapshot and committed. No FY2024
   label is read.
4. This file is finalized with: UTC timestamp, the SHA-256 of every pinned
   artifact (section 9), committed and pushed; its SHA-256 and the commit are
   recorded in the witness repo (`uac-witness`), and the seal log records the
   supersession of `TASK1_MATCH_RULE_v4.md` (section 10). Each of those writes
   gets its own go.
5. Only then: any FY2024 key read (Tier 2) or FY2026 listing read (Tier 1).
   Nothing in sections 3-7 changes after step 4; a change is a new version
   with its own timestamp and hash, and the old one is reported too.

## 1. Question and evaluation tiers

Task 1: for every NIH award in a fiscal year's universe, propose whether it
belongs in the RCDC NITRD parent listing (spending category 329), as a
shortlist for SME review. One fingerprint, built once from FY2021.

| Tier | Data | Blind? | Role |
|---|---|---|---|
| 1 (headline) | FY2026, prospective: award-level ranking and shortlist committed before any FY2026 NITRD membership is public | yes | headline result |
| 1c | FY2026 count forecast: the filtered NITRD count under the reconstructed universe | substantially blind (see 7.4) | reported next to Tier 1, not tested |
| 2 | FY2024, sealed key (`task1-fy2024-seal-2026-10-25T17:56:21Z`), **non-File-A awards only** (`filea_exposed = false`) | yes | blind retrospective result |
| 2x | FY2024 File A awards (`filea_exposed = true`), 2,281 awards | no (exposed) | reported separately, never pooled with Tier 2 |
| 3 | FY2022, FY2023 | no (burned) | dev baselines and descriptive decay-curve points only |

The out-of-time decay curve is FY2022, FY2023, FY2024 (non-File-A) and FY2026
from the single FY2021 fingerprint. Only the FY2024 and FY2026 points are
blind; the curve is labeled that way. FY2025 is not used (burned, section 2).

## 2. Exposure ledger

Per-award NITRD membership, reserved and scoring years. "Builder" = the
FY2021 fingerprint builder under the read guard; none of these items is an
allowed input to it.

| Year | Exposure | Evidence | Status |
|---|---|---|---|
| FY2022, FY2023 | Every award's category-329 flag in `build/universe/fy2022.csv` (sha256 5126368e...) and `fy2023.csv` (d96da7b3...) | commit `d8c5a56f3c0c` (pushed as `1b81fdd0d33b`), 2026-10-25, on public `origin/main` | burned |
| FY2022, FY2023 | Carry-forward baseline scored on them (`dev/baseline/carry_forward_backtest.json`, 75a30a6e...); results seen by the owner and the assistant | commit `d8c5a56f3c0c` (pushed as `1b81fdd0d33b`) | burned |
| FY2021-23 | Per-award flags in `build/reconciliation/qvr_crosswalk_fy2021_2023.csv` (dd5b46a2...) | untracked, written 2026-10-25 21:20Z | derived from the above |
| FY2022-23 (nitrd-mcp) | `exporter_projects` holds spending categories; `nitrd_cores` holds the last NITRD FY per core (to 2023); FY2022 demo fixtures and routing analysis | Unity Catalog, `users.conroyri.nitrd_hackathon_v1_*` | burned (same years) |
| FY2024 | File A ID columns read: 2,281 AI-tagged NITRD awards | sealed File A, read 2026-10-25 | exposed subset, Tier 2x |
| FY2024 | 2023->2024 carry-forward agreement: FY2024 category-329 records joined to cores in memory; only aggregates reported, nothing per award saved | seal manifest `fy2024_label_reads_before_seal` entry 1 (`docs/seal/task1_fy2024_seal_manifest.json`, ae63372d...) | disclosed aggregate read |
| FY2024 | Record count 4,758 from the API total | same manifest, entry 2 | count only |
| FY2024 | Full membership in the sealed key (79,721 records; aggregate sha256 81350a53...) | commits `19689a22a931`, `842c822568e5` (pushed as `1b08644bfd4f`, `a5c9b9c826cf`) | sealed, unread |
| FY2025 | 480 NITRD awards in `fixtures/UAC_Uncoded_12-01-2025-updated-NIH_ODSS.csv` (8c92c8af... as read; now e9e44785... after the PCC and PO Name columns were removed, `docs/FIXTURE_CORRECTION_v1.json` and `_v2.json`), read by the Task 2 engine; 214 held-out awards scored in Task 2 `eval_run_1`; File A FY2025 ID columns (2,424). Union 2,690 of 4,707 NITRD awards (57%) | commit `c69c2fdd5798` (pushed as `31b9135d16f0`), 2026-10-23, public | burned, not used |
| FY2026 | Public RePORTER: 0 category-329 records (count only, 2026-11-03 14:07Z; 67,665 NIH records) | API count | blind |
| FY2026 | The owner saw one rough, unfiltered aggregate FY2026 NITRD count in QVR on 2026-10-25 (about 3,787; no activity-code exclusions, no subproject handling, slightly different underlying data). Context only: it is a different quantity from the filtered count forecast and is not an input to anything | owner attestation, 7.4 | context, not an anchor |

FY2024 text (scoring year) was read for Task 2 synonym derivation
(`corpus/fy2024_independent.v1.jsonl.gz`, text-search selected, no spending
categories). That is text, not membership; the builder may not read it (guard
D7).

## 3. Universe

The same rules apply to every year.

1. NIH awards in RePORTER for the fiscal year.
2. **Reconstructed QVR filter, pending ODSS confirmation:** drop subprojects;
   drop intramural (core starts `Z`), contracts (`75N`, `HHS`, `N` + 2 digits,
   or a leading digit), other transactions (`OT`) and interagency agreements
   (`Y` + 2 digits); keep extramural grants and admin supplements. Evidence:
   on FY2021-23 it reproduces the owner's QVR NITRD counts within 0.13-0.44%
   (2,727 vs 2,715; 3,115 vs 3,111; 3,407 vs 3,403). If ODSS gives a different
   filter before the freeze, this section changes; after the freeze it does
   not.
3. **Clinical Center excluded** (admin IC `CC` in RePORTER, `CL` in ExPORTER):
   intramural, about 130 awards a year, never categorized in FY2015-2021.
4. **Three-state label** per award: NITRD (category 329), not NITRD (has at
   least one spending category, not 329), uncategorized (no spending category).
   Uncategorized awards stay in the universe and are scored by the model, but
   are an unscored group for the primary metrics (section 6). In FY2015-2021,
   7-9% of NIH awards a year were uncategorized, across all mechanisms and in
   long-closed years, so they are neither out-of-scope mechanisms nor
   pending review; the cause is not public.
5. The scoring-year fetch is ID + text only. The three-state status comes only
   from the sealed key (FY2024: two-state key plus the approved sealed
   `has_any_category` supplement; FY2026: fetched at reveal).
6. FY2026 universe = the frozen snapshot fetched 2026-11-03 (`task1-text-fetch-v1`,
   identity + text, no label field), filtered as above. Awards RePORTER adds
   after the snapshot are reported separately at reveal and are not in the
   Tier 1 metrics.
7. Code: `workflow/qvr_universe.py` (`task1-universe-qvr-recon-v1`). Measured on
   the build fetch: FY2019 59,205, FY2020 61,896, FY2021 63,074 universe
   awards; FY2021 NITRD 2,727 (4.32%), uncategorized 4,633 (7.35%).

## 4. Fingerprint

`task1-fingerprint-v1`, code `tools/build_fingerprint_v1.py` +
`workflow/fingerprint.py`. TF-IDF + logistic regression, stored as plain arrays
(vocabulary, IDF, coefficients) so every score decomposes into per-term
contributions for `classifier_explain`.

* **Text** = title + abstract + public health relevance. Unigrams + bigrams,
  lowercase, English stop words removed; sublinear tf x IDF, L2-normalized.
* **Term stabilization (vocabulary + IDF): FY2019-2021 text only, no labels.**
  A term is kept if its document frequency is >= 5 in each of the FY2019,
  FY2020 and FY2021 universes separately, and <= 50% of the pooled documents.
  IDF (smoothed) is computed on the pooled FY2019-2021 universe text.
* **Supervised fit: FY2021 labels only.** Training set = FY2021 universe
  awards with any spending category; y = category 329. Uncategorized FY2021
  awards are never used as negatives.
* **C**: 5-fold cross-validation inside FY2021, grouped by core project
  (GroupKFold over the whole FY2021 universe); metric = average precision on
  the categorized test-fold awards; grid 0.25, 1, 4, 16, 64, 256;
  one-standard-error rule (the smallest C within one SE of the best mean).
* Not used: any NITRD-internal or RCDC fingerprint, the placeholder
  fingerprint v0 (built from NITRD PCA scope text), the PCA scope files, the
  nitrd-mcp shipped model (trained FY2015-2018).
* Build disclosure: attempt 1 (grid up to 16, best-mean rule) picked the grid
  edge; attempt 2 (grid up to 256) showed AP plateaus (16: 0.7978, 64: 0.7997,
  256: 0.7999); the one-SE rule was then adopted. All three runs used FY2021
  only; their logs and artifacts are kept
  (`task1_seed_v1/_build_attempts/`).

## 5. Shortlist rule and operating size

* Score every universe award (uncategorized included); rank by score
  descending, ties by appl_id ascending.
* **Operating fraction f, calibrated on FY2021**: the smallest share of the
  FY2021 universe whose shortlist, ranked by out-of-fold scores, reaches
  recall 0.95 of the FY2021 NITRD awards. K = ceil(f x N) for a scoring year
  with universe size N. f is fixed by FY2021 alone. Value: see
  `build/task1_fingerprint_v1/shortlist_rule.json` (pinned, section 9).
* For Tier 2, N is the whole FY2024 universe (File A awards included) and K
  applies to that ranking; metrics are then computed on the non-File-A subset.
* Declared secondary points: 1x, 2x, 3x FY2021 prevalence (4.32%, 8.65%,
  12.97% of the universe), and the full recall-vs-fraction curve (0.5% to 40%
  in 0.5% steps).
* Calibrate to 0.95 on the build year, require >= 0.90 on the held-out years:
  a declared 0.05 drift tolerance.

## 6. Metrics (declared before any reveal)

For each tier separately, never pooled. **Headline comparison: the new-core
subset.** Carry-forward already handles continuing cores (FY2022 precision
0.93), so the fingerprint earns its keep only on newly relevant awards; every
metric below is reported for all awards and, prominently, for new cores (FY2024:
core with no NIH record in FY2021-2023, the seal manifest's `new` group;
FY2026: no NIH record in FY2023-2025, from identity-only fetches at reveal).

1. **Recall at K**: NITRD awards on the shortlist / NITRD awards.
2. **Precision at K**: NITRD awards on the shortlist / K (excluding
   uncategorized from both numerator and denominator in the primary version).
3. **Shortlist size K** itself, as a share of the universe.
4. **Both ways on uncategorized**: primary = uncategorized excluded;
   sensitivity = uncategorized counted as not NITRD.
5. **AI-flag recall, separately**: recall at K on awards with an AI
   subcategory signal. On FY2024 this is only computable on the File A group
   (Tier 2x, exposed), because File A is the AI subset; the blind non-File-A
   subset is depleted of AI awards by construction, so its recall is not an
   AI-inclusive recall. Stated as a selection effect.
6. **Cohen's kappa** between shortlist membership (top K) and listing
   membership, with a 95% CI from a bootstrap over core projects (2,000
   resamples, seed 20261103). This is model-vs-listing agreement against a
   single noisy oracle (the RCDC listing), not agreement between two human
   raters. Reported, not a gate (section 7).
7. **Benchmarks, external and inferred, not a NITRD measurement.** Kappa is
   reported next to two literature analogs verified by the owner: kappa 0.56 at
   96-97% (Mateen et al.) and kappa 0.62 (Neves et al.), and next to: human
   systematic-review abstract screening, kappa about 0.72 (BMJ Open
   2024;14(3):e076912); NIH grant peer review, ICC about 0 (Pier et al., PNAS
   2018;115(12):2952-2957). Kappa is interpreted against these analogs, not
   tested against them. Raw agreement is not reported as a headline (it is
   inflated by the large not-NITRD majority).

   References for the two analogs (supplied by the owner, 2026-11-04):

   * Mateen FJ, Oh J, Tergas AI, Bhayani NH, Kamdar BB. Titles versus titles
     and abstracts for initial screening of articles for systematic reviews.
     Clin Epidemiol. 2013;5:89-95. doi:10.2147/CLEP.S43118. PMID: 23526335.
   * Neves M, Klippert A, Knöspel F, Rudeck J, Stolz A, Ban Z, Becker M,
     Diederich K, Grune B, Kahnau P, Ohnesorge N, Pucher J, Schönfelder G,
     Bert B, Butzke D. Automatic classification of experimental models in
     biomedical literature to support searching for alternative methods to
     animal experiments. J Biomed Semant. 2023;14(1):13.
     doi:10.1186/s13326-023-00292-w.
8. Comparator: carry-forward vs fingerprint vs combined (CF, A and A+CF,
   section 6a), same universe and tier, all awards and new cores. Reported as a
   comparison, not pass/fail (section 7).
9. **Review burden** (reported, not tested): the shortlist fraction at the
   operating point (K / N) per tier.
10. Under-capture candidates (Task 3): uncategorized awards on the shortlist,
    listed with scores, not counted as errors.
11. FY2026 count forecast (Tier 1c): (1 - u2021) x r2021 x sum of scores over
    the FY2026 universe snapshot, with u2021 = FY2021 uncategorized share and
    r2021 = FY2021 NITRD count / sum of FY2021 out-of-fold scores over
    categorized awards. Reported with its error against the filtered FY2026
    count at reveal.

## 6a. Model comparison (pre-registered; the shipped model is fixed)

**Evaluation endpoints, stated explicitly.** (i) Independent SME-SME
reliability, meaning two NITRD coders labelling the same awards blind: not
measurable from public data and not claimed. (ii) Model vs listing, meaning
agreement with the published RCDC NITRD listing: what this pre-registration
measures. (iii) Assisted workflow, meaning SME decisions made with the
shortlist in hand: future work. Its results would carry an automation-bias
caveat, because reviewers shown a model suggestion tend to accept it.

**Pre-registered arms.** Every blind-tier arm (A, B, CF) is evaluated on the
same held-out data at reveal: the same universe, tiers (section 1), labels and
uncategorized handling (section 6, item 4). Each arm is scored once. Arm C is
FY2021-only in v1 (see its row).

| Arm | Role | Definition | Built where, on what |
| --- | --- | --- | --- |
| A | primary, shipped | TF-IDF + logistic regression: the shipped fingerprint `task1-fingerprint-v1` (sections 4-5) | under `build_guard`, FY2019-2021 text, FY2021 labels (done, `984e895`, pushed as `881bd77`) |
| B | comparison | frozen hosted general-domain embeddings + logistic regression (`task1-fingerprint-embed-v1`): the same award text (section 4) embedded by the Databricks-hosted endpoint `databricks-qwen3-embedding-0-6b`, served version `qwen3-embedding-0-6b-112025` (general-domain, not biomedical; no fine-tuning). The endpoint is not bit-deterministic between passes, so FY2019-2021 are embedded once and the matrices are SHA-256-pinned (`task1-embed-cache-v1`); the fit reads only the pinned matrices. LR fit on the same FY2021 categorized awards with the **same 5 core-grouped folds as arm A** (arm A's recorded fold assignment, `fold_assignment.i8`, sha256 `f34c99f1...`), C grid, one-SE rule and calibration rule (f at 0.95 FY2021 out-of-fold recall), under scikit-learn 1.7.2 as arm A. Explanations are nearest FY2021 exemplars, not term weights. Change record (owner, 2026-11-04, before the freeze): the first arm B fit (scikit-learn 1.9.1) had used its own GroupKFold split, which differs from arm A's under 1.7.2 (23% of awards shared a fold); arm B's LR was refit on arm A's recorded folds from the same pinned embedding cache. Chosen C (4) and the final model (sha256 `227b91cb...`, fit on all categorized awards) are unchanged; the out-of-fold calibration changed (own fraction 15.33% -> 14.90%; recall at 11.55% 0.9197 -> 0.9204; FY2021 kappa A|B 0.733 -> 0.739). The first fit's outputs are archived outside git with their SHA-256s. The model file (9.6 MB, mostly the exemplar bank) is kept on the volume, SHA-256-pinned through `MODEL_POINTER.json`, not in git | under `build_guard`, FY2019-2021 text, FY2021 labels, own READ_MANIFEST (seed files + pinned cache). The endpoint is the only added network target and receives text only. FY2024 and FY2026 are embedded once at scoring time by the same endpoint and version, and those matrices are pinned the same way |
| C | **secondary** | LLM, zero-shot (`task1-llm-v1`), with the public FY2026 NITRD PCA definitions and AI cross-PCA guidance in context, verbatim from https://www.nitrd.gov/program-component-areas/nitrd-pcas-2026/: Meta Llama 4 Maverick via Databricks Foundation Model APIs, endpoint `databricks-llama-4-maverick`, served version `meta-llama-4-maverick-040225` (first pin, Llama 3.3 70B, replaced for a workspace QPS limit before any run finished; disclosed in the artifact), temperature 0, prompt `prompts/task1_llm_v1.prompt.txt` (sha256 `3aea5422...`, committed `9d1cf0a`, pushed as `2d76541`, before scoring). The prompt holds only the definitions and the award's title, abstract and PHR: no label, no prior-year membership, no examples. The model returns a 0-100 likelihood per award; ranked by that score, ties broken by `appl_id`. FY2021 is scored on a declared stratified sample (1,000 NITRD / 3,000 categorized non-NITRD / 500 uncategorized, seed 20261104), inverse-probability weighted, stratified-bootstrap CIs; scored three times to measure run-to-run variance at temperature 0. **Scope in v1: FY2021 only** (owner, 2026-11-04). Arm C does not score FY2024 or FY2026 and takes no part in any blind-tier result; every arm C number is a FY2021, sample-based estimate and is labelled so. Scoring a full year was estimated at about 63,000 awards x 3 runs, about 26 hours per run at this workspace's sustained rate, and is not attempted in v1 | under `build_guard`, FY2021 text; FY2021 labels only to draw and weight the sample, never in the prompt; READ_MANIFEST lists the seed, prompt and scope files |
| CF | baseline | carry-forward from prior-year NITRD membership (`carry-forward-v1`): an award is predicted NITRD if its core was NITRD in the previous fiscal year. FY2024 uses FY2023 labels; FY2026 uses FY2025 labels. It is a set (size K_CF), not a ranking | in the scoring harness after the freeze, **not under `build_guard`**. It uses **exposed prior-year labels** (FY2023 -> FY2024, FY2025 -> FY2026) and is labelled that way in every table and figure |

Combined arm A+CF (reported with the carry-forward comparison, not a model arm):
carry-forward's predicted set first (ordered by arm A's score), then arm A's
ranking, cut at K_A. It has arm A's K, so it shows what carry-forward adds to,
or takes from, the fingerprint at equal review burden.

**Binding rules.**

1. **The shipped model is fixed.** Arm A (TF-IDF + LR) is the shipped model.
   It was chosen on FY2021 grounds, determinism and interpretability, and that
   choice does not depend on any blind-set result. Arms B, C and CF are
   comparison-only. If an arm beats arm A on a blind tier, that becomes future
   work (a new pre-registration), never a post-hoc swap. Arm A's result stands
   as the result of this pre-registration, and the section 7 criterion applies
   to arm A only.
2. **Same build data for every model arm.** Arms A, B and C are built under
   `build_guard` from FY2019-2021 text and FY2021 labels only. Scoring-year text
   is read only in the freeze run, with no labels. Carry-forward is the one
   exception: it uses exposed prior-year labels (FY2023 -> FY2024,
   FY2025 -> FY2026), runs in the scoring harness, and is labelled as using
   them.
3. **Equal burden.** Arms are compared at equal shortlist size K: arm A's
   calibrated operating fraction, 11.55% of the universe (f = 0.115483), which
   gives a recall-at-equal-burden comparison. Each ranked arm (A, B, C) also
   gets its own recall-vs-fraction curve per tier, at fractions 1%, 2%, ..., 30%
   plus 11.55%. Carry-forward is a set, not a ranking. It is reported at its own
   size K_CF (one point on the curve), and the ranked arms are also reported at
   K_CF. A+CF gives the equal-K_A version.

**Comparison metrics** (per tier, never pooled; for all awards and for new
cores):

1. **Recall@K per arm** on each tier, at the equal K of rule 3.
2. **Pairwise machine-machine kappa matrix** on binary shortlist membership at
   equal K, for every pair of arms (A, B, C, CF), with bootstrap CIs over cores
   (2,000 resamples, seed 20261103). It is reported next to the human screening
   benchmarks, kappa 0.56-0.62 (section 6, item 7). Caveat, stated with the
   matrix: the model arms share the FY2021 labels (and carry-forward shares the
   listing process), so they are expected to agree more than independent human
   raters. High machine-machine kappa is therefore not evidence of reliability.
   At the freeze only the FY2021 (build-year, out-of-fold, pre-reveal) matrix
   is pinned (`build/task1_comparison_fy2021/`; arm C on its FY2021 sample).
   The blind-year matrices (FY2024, FY2026; arms A, B, CF) are reveal outputs,
   computed by the pinned harness at scoring; no blind-year ranking other than
   arm A's FY2024 freeze-run ranking exists before the hash.
3. **Disagreement-set analysis.** The disagreement set is the awards on some
   but not all of the arms' shortlists at equal K, broken down by membership
   pattern (which arms include the award). FY2021: pinned at the freeze with
   the FY2021 matrix. Blind years: pattern sizes, new-core share, IC mix and the
   NITRD rate in each pattern are reveal outputs, which show whose unique picks
   are right.

**No-blind-selection rule.** The primary arm, the operating fraction and the
criterion are fixed at the freeze. No arm, ensemble, K or threshold is chosen,
promoted or tuned after any reveal. Anything built after the freeze is
labelled post hoc.

## 7. Success criterion (one pass/fail; everything else reported)

**Pass/fail (arm A only):** Tier 1 and Tier 2 each: recall at K >= 0.90 on the
held-out year at the calibrated fraction (11.55% of the universe, f = 0.115483;
primary version, uncategorized excluded). Each tier passes
or fails on its own.

Reported, not tested:

* kappa with its 95% CI, next to the 0.56 / 0.62 analogs and the benchmarks in
  section 6 (formerly a criterion);
* carry-forward vs fingerprint vs combined (CF, A, A+CF), overall and new-core:
  a comparison, not pass/fail (formerly "beat carry-forward on new cores");
* the model comparison (section 6a): recall@K per arm, the kappa matrix,
  the disagreement sets, the recall-vs-fraction curves;
* review burden (shortlist fraction at the operating point).

No other pass/fail criterion applies. Change record: the owner's settled
fields (2026-11-03) had three criteria. Before any freeze or reveal, the owner
reduced them to this one and moved kappa and the carry-forward comparison to
reported metrics. One-SE C selection is confirmed unchanged.

**7.4 Conditions for Tier 1 to count as prospective.** This file, the
fingerprint and the FY2026 forecast are committed and witnessed while public
RePORTER shows 0 FY2026 category-329 records. Owner attestation:

> As of the freeze, the owner has seen only a rough, unfiltered aggregate
> FY2026 NITRD count in QVR (2026-10-25; no activity-code exclusions, no
> subproject handling, slightly different underlying data), and has not read,
> exported, or recorded award-level FY2026 NITRD membership.

Consequence: the FY2026 award-level ranking and shortlist are the blind
headline. The FY2026 count forecast predicts the filtered count under the
reconstructed universe, a different quantity from the unfiltered glimpse, and
is reported as substantially blind, with the glimpse listed in the exposure
ledger as context, not as an anchor.

**7.5** A tier that fails is reported as failed; no re-fit on revealed data
counts as the same pre-registration.

## 8. Reveal order

1. Freeze (section 0).
2. Tier 2: open the FY2024 key and the sealed supplement under
   `UAC_NITRD_TASK1_SCORE_RUN=1`; score once.
3. Tier 3: compute FY2022/FY2023 points (already exposed).
4. Tier 1: when public RePORTER shows FY2026 category-329 records, fetch the
   three-state status and score the committed forecast once.

## 9. Pinned artifacts (filled at freeze)

| Artifact | sha256 |
|---|---|
| this file | not self-pinned: recorded in its commit message, uac-witness record 0004 and seal-log line 33 |
| `docs/TASK1_READ_GUARD_SPEC.md` | 07eab822960ce6a9a257e627840b1bbd0d0f0acc8a31d85573d2fa74e4e38ce2 |
| `workflow/build_guard.py` | ef411c9dcf86547e50fedfe9a575ca099f4550ecc3c65e24555ab02b7a305c79 |
| `tests/test_build_guard.py` | cca4f7282df5db415f3419b89d56aba6fb7745d286339aff78fc0ce87ccf7fe8 |
| `workflow/qvr_universe.py` | b52136ee6ebf3140bc665caff68f5e833f76de55003dcca22994ed9d7740e1fb |
| `workflow/fingerprint.py` | 14c03b2a9f2d09c8d2960ec3ef92204035d71c1a75176667782eb1f64fafca76 |
| `tools/fetch_task1_text.py` | 12122cd521e3f5269896e8709eadd686470eb46f7dc8a9ddfc8000c86493a985 |
| `tools/build_fingerprint_v1.py` | 46f8f22a12f86fdfa6c6d064095d04392058d7f68f919b3013e1b097b692a09e |
| `tools/forecast_task1_fy2026.py` | 13f38dbf31f207da0868a968e5d8e6727146b80d808d1e97fb36d140137aa4cf |
| seed FY2019 `task1_seed_v1/fy2019/fy2019.jsonl.gz` (75,898 records; outside git) | 75a48b70b37151b0767dd3d143b04a5e65fdde5c38c0729f8a8bcf59cdc919e5 |
| seed FY2020 `fy2020.jsonl.gz` (78,279; text only) | ae495e0d49096df45746cdeaa793f10bc743985acb6889b9660a966b085d38ed |
| seed FY2021 `fy2021.jsonl.gz` (79,126) | 5e561149f60ca252fcfce812a4e135b10f72fb94a8eaf2eb2e710982b344ce42 |
| seed FY2026 `fy2026.jsonl.gz` (67,665; text only) | 454d6c31141ae678064fcc1ca936d158b3fe8ea7c4b30b8dc2ac48fd5c828a10 |
| **Arm A** `build/task1_fingerprint_v1/model.json.gz` | b703083d8a122015071bdf9c7035f2b5e3375b6dae3fdcc42e847f46b49049ce |
| Arm A `shortlist_rule.json` | 122e400069c9bdc161624a9effce4d1768a751e29eaf0165ca422232643e9893 |
| Arm A `calibration.json` | 876b3226e298f830b87726e79cacab755b3061a1d1ffe2a563681f0498472f24 |
| Arm A `READ_MANIFEST.json` (FY2019-2021 seed only) | 321ecb119e56e809779c62c25dfda13909c1b9986156d66e84d60a64d602929b |
| Arm A FY2026 forecast `build/task1_forecast_fy2026/forecast.csv.gz` | b0b42f78a6041425395625c39f4062bc728c29c3658f8df63c31919ac23bca2a |
| Arm A `forecast_summary.json` | 4ecb98bde969bf6830174212e49d04962d6cb83ecc0299f49ff0e5b4292ff4b1 |
| Arm A forecast `READ_MANIFEST.json` (FY2026 text + arm A artifacts) | 1e6cd8345440a16ac781e73fc9cb382d87787a2f443c2a3226aa404f7a0a533c |
| FY2024 ranking (freeze run, `task1-fy2024-ranking-v1`, commit `5e3bfa4`): `build/task1_fy2024_ranking_v1/ranking.csv.gz` (64,065 universe awards, K 7,399) | e49e844d1ebf43691cf3d66ef70f7c415d7dd50f1deccac845709cd656ffa8dd |
| FY2024 ranking `ranking_summary.json` | 098b6131f6bfecd8ef582e39e538aa119bb1ffd4d57f1a8c16f15389f9229d11 |
| FY2024 ranking `READ_MANIFEST.json` (arm A model + rule, FY2024 identity, the 16 text-snapshot shards, seal manifest; no label) | 5c2cdff3052d77606f454bc74401102710ed81bf404ce563abbb3e2aa21ec9d6 |
| Freeze-run tool `tools/rank_task1_fy2024_v1.py` (its `--verify-fy2026` reproduced `forecast.csv.gz` b0b42f78... byte for byte before the run) | bc8515daf9bdab847b1bf0708260a828bbb4310197f6352eab569deaa4a67a48 |
| **Arm B** embedding-model pin | endpoint `databricks-qwen3-embedding-0-6b`, foundation model `system.ai.qwen3-embedding-0-6b`, served version `qwen3-embedding-0-6b-112025`, 1024 dims (hosted: no weight file to hash) |
| Arm B `workflow/embedding.py` | 0eae1fe256241cf085dc95f6d9db16f23e8d5cc25cbb7885c220943fa34b5037 |
| Arm B `tools/embed_seed_embed_v1.py` | 4900ddc7c437fbe78ea2198df94b29e43dcd81be6e17aeb1045157ebde2bd97c |
| Arm B `tools/build_fingerprint_embed_v1.py` | e67b3792a2fd97df6175e8b62b26a4b86ef74062baa8fcbd3562548db9c36308 |
| Arm B `tests/test_embedding.py` | 62e8ec34f3ce7cdf5a13d782028f6c0cf71ee23db63942e11adcc9f001432d0f |
| Arm B `tools/vendor_embed_model.py` (PubMedBERT alternative; not used by arm B v1) | 5dcd1d7152f59e56b64b5a79af0096f0b0a435e03af3d1d6aa2c2a1cd49e0771 |
| Arm B cache `task1_embed_v1/fy2019/fy2019.emb.f32le` / `.appl_id.i64le` (outside git) | fe8c275a9d49965b9e40237a35eb674a81de436c0c409112880b21a173b35a64 / 4c08f501c0c6fd1af6b20b6245200f8bde2f631f400859b78d190a342f0b7b28 |
| Arm B cache FY2020 `.emb.f32le` / `.appl_id.i64le` | c2f197ea16e47fd242bb98c6210d767869dcd55cb2b377d25c2f6125987679d4 / e2b913a9f908245bf122d55f172283e55986ce0bfea26571abd83369ccb7f7d5 |
| Arm B cache FY2021 `.emb.f32le` / `.appl_id.i64le` | 69974f390015cbcf00357a59bd17aad675590ddc77e9095eb7556ff53b5229ba / c173220cae1fbe92a51f6b0a9899212e2a6641137d89acbe5f72e4b07e381e52 |
| Arm B model `/Volumes/users/conroyri/nitrd_hackathon_v1_raw/task1_fingerprint_embed_v1/model.json.gz` (9,586,531 bytes; outside git) | 227b91cb7d9ac0bcc94dfcee33e4e19401dc52fde402d20dcbd8d9fcd2e4678d |
| Arm B `build/task1_fingerprint_embed_v1/MODEL_POINTER.json` | d0968db384de9b705e8e7e246c40d6a907230c34679d8fde6fae7b2e0fc66485 |
| Arm B `calibration.json` (arm A's folds) | 7d4e2cdad149032ae04a059ca06569909391182eeefc23ef8c0c3ebb8bb00587 |
| Arm B `READ_MANIFEST.json` (FY2021 seed + FY2021 cache + arm A fold assignment) | 2668844a4e339be2c2151002fe50aaa3f450537d36bf87f85859854e99866cce |
| Arm B FY2026 and FY2024 rankings | after the hash, at scoring (embedded once by the pinned endpoint + version; matrices pinned the same way) |
| **Arm C** model pin | endpoint `databricks-llama-4-maverick`, served version `meta-llama-4-maverick-040225`, temperature 0, max_tokens 16; zero-shot (no few-shot examples) |
| Arm C prompt `prompts/task1_llm_v1.prompt.txt` (committed `9d1cf0a`, pushed as `2d76541`, before any scoring; identical to `build/task1_llm_v1/prompt.txt`) | 3aea5422f8094a86f50bd9f063df509f70777a58b859df83fac7f8a33667328c |
| Arm C public PCA-definition text `scope/nitrd_pca_scopes_fy2026.v1.json` | 29ad15b320b363227dbe5ab590351578cffefe7ab171cb3a364d55f4803b8c79 |
| Arm C `tools/build_llm_classifier_v1.py` | a3cd21e25e2db7040e85a3e216863c29d09928b6fc001cc4544a9415250224b8 |
| Arm C `build/task1_llm_v1/scores.csv.gz` (FY2021 declared sample only, 3 runs; v1 scope) | d61c0bbc6ad9fbb93aa619872b28a8c421f07a2d9d9da5b3080d3ba7ec3ffd46 |
| Arm C `summary.json` | fe723dad6a1ba52b2d5c9ada342e18a1565f64fddbb633079af133ae5cd403f8 |
| Arm C `READ_MANIFEST.json` (FY2021 seed + prompt + PCA text) | 05e9ec0224df5886278126ac8fcae51d5376d34dc48b6a0fd50d9a5e663dc438 |
| OOF export `tools/export_oof_scores_v1.py` | f1e193f7281c68a9d6bab2ca1a6192a06065f4654c0ca8542695ac8d25d74c6c |
| Arm A OOF `build/task1_oof_scores_v1/arm_a/` scores.csv.gz / SUMMARY.json / READ_MANIFEST.json / fold_assignment.i8 | 3aac2aaf9bcd0262b578b3121b4bc5e56f5356be2792bb750eddf605568253d3 / 02007899df1f3973fbce5c9501b6ba24e2431612a55257d005247ed39393d6a7 / 15a5842496007f033f7d0a05723c4476cdb191bc4af0b870d2dc916be5140e0f / f34c99f1220faca2e0b17c163d6d8422cd821f36a90b71e50b67f0e15951b6ef |
| Arm B OOF `build/task1_oof_scores_v1/arm_b/` scores.csv.gz / SUMMARY.json / READ_MANIFEST.json / fold_assignment.i8 | 072464f9de52db31cd0d9ecf83b3f77a3cbc537e39fecf2a6d36fa75a84aea0a / 641d35c732f27c1d805742cc10e7e258622bbb6eafa5225a78ab165a85539be5 / f6f65d2e7be791295c02b20855d9fcfa5281bae8d4da39c9476aee3ddbd957ad / f34c99f1220faca2e0b17c163d6d8422cd821f36a90b71e50b67f0e15951b6ef (= arm A's) |
| Comparison harness `workflow/model_comparison.py` (incl. carry-forward `carry-forward-v1`) | 338fa92c13e3e21476e070b54111903adf8f0f56d917b52f0e787607f91bd2ca |
| Harness `tools/compare_arms.py` | a1e050c7ee376470e971f5e5aa0239f3a26f6b23ac6988adc1a5d71cdc6791d6 |
| Harness `tests/test_model_comparison.py` | 24a2d193f6dd1af30748ca8631360a402a9a738e3d0c4f64577d39371fded781 |
| FY2021 pre-reveal comparison (kappa matrix + disagreement) `build/task1_comparison_fy2021/report.json` | 6170facc9ddbf28d561d3d470c77cb5c5eed7446db448537c0db31c469021305 |
| FY2021 pre-reveal comparison `disagreement.csv.gz` | 5969ed30af7c81001f81e5c2b6144bdc5f66dde17bce617b3e6967091cb18b2c |
| FY2024 sealed key (aggregate) | 81350a5328ceb485eb41c7095765c3a7f2d5f8f648cc7b2159610b8bf52efc02 |
| FY2024 `has_any_category` supplement | (at its seal; sealed before the Tier 2 scoring run, and its hash is logged then) |

## 10. Relationship to earlier rules

`docs/TASK1_MATCH_RULE_v4.md` (core-level FY2024 scoring, H1/H2 headline pair)
was committed for a FY2021-23 build. This pre-registration supersedes it as
the primary Task 1 analysis. v4's core-level metrics are retained as a declared
secondary analysis, computed from the same frozen FY2024 ranking. The
supersession is logged in the seal log (`SEAL_AMENDMENTS.jsonl`) at the freeze.
