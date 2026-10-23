# UAC NITRD held-out evaluation protocol (sealed answer key)

This file goes into the evaluation doc as written. It identifies the held-out set
by digest only. It deliberately contains no storage path, no file name and no
category labels from the sealed material, so it passes the seal guard.

## What is sealed

| Item | Value |
| --- | --- |
| Seal ID | `entry2-heldout-2026-10-23T19:18:20Z` |
| Sealed at (UTC) | 2026-10-23T19:18:20Z |
| Sealed by | conroyri@nih.gov, at the user's instruction (week-1 gate 0c) |
| Source | RCDC Trend Analysis Project Listing export "File A" (all NITRD AI subcategories), created by RCDC 2026-07-07 |
| Selection | File A rows with FY = 2025 whose Appl ID is in the UAC fixture (480 Appl IDs) |
| Held-out set | **214 projects, 240 rows** (some projects have more than one funding row) |
| Held-out file SHA-256 | `cbeab03e64f2dbc71a56caa68910dfabfb37dd6422284b1825ab462432b673ef` |
| Sorted Appl ID list SHA-256 | `3b81e5caa8b6e0454a15b30203b94f9244643c111ab0c88e67da1da621e01500` |
| Full File A SHA-256 (also sealed) | `fa6940d2bfa4f2445e0eaee3eadf2c173dd69d03a0552e28cb8fe09ec2488830` |
| Seal manifest SHA-256 | `db156b5fc8d63d226a5720bf278c1c2ec9bebe86545b4cb4ef182d7d45e0ae17` |
| Serialization | header + rows sorted by (Appl ID as int, Category, CAN, FY Reported $, Project Number); CSV minimal quoting; LF; UTF-8 without BOM; cell text unmodified |

The storage location is recorded in the seal manifest stored with the sealed files
and in the project notes, not in the repo.

Identifiers fixed at sealing keep their original `entry2` prefix: the seal ID, the
rule ID, and the volume and folder names. They are immutable references in the seal
log, and renaming them would break the audit trail.

## Off-limits to the build

The proposal engine, the fixture pipeline, and all build and test code have no path
to any of these:

* the whole of File A, not only the 214 FY2025 projects. Its FY2019-2024 rows code
  the same core projects in earlier years: at least 52 fixture core projects, 197 rows;
* RCDC exports B (LSDMA FY2023; 36 fixture core projects, 89 rows) and C (AI FY2019-2023;
  18 fixture core projects, 56 rows), for the same reason. Their digests are in the guard.

The NITRD budget crosscut is not project-level and stays usable as context.

## Protocol: freeze, reveal, compare, report. No iteration back.

1. **Build** proposals using only the UAC fixture and permitted sources. The seal guard
   (`seal_guard.py`) runs in every build sweep and must report CLEAN.
2. **Freeze** the proposals: commit and tag them, and record the proposal file's SHA-256
   and the commit before anything is revealed. A frozen proposal is never edited.
3. **Reveal**: in a separate evaluation step, outside the build tree, read the held-out
   file and verify that its SHA-256 equals the value above. A mismatch stops the
   evaluation; it is reported as a seal failure, not worked around.
4. **Compare** once, and only on the scorable scope: positive-only for the 214 projects
   with an AI-relevant final category. The 266 fixture projects absent from File A are
   unscorable, not negatives. Advanced Wireless R&D has no RCDC category and is
   reported separately.
5. **Report** the results as observed, with the proposal tag, both digests and the
   evaluation run ID. Any later proposal change is a new version, and it is evaluated
   only against a new, different held-out set, never re-scored against this one.

## The claim File A supports (fixed wording; state exactly this)

> For the 214 of 480 projects that File A finally coded as AI-relevant (one category
> each), we compare our frozen proposals against NIH's final UAC coding, held out
> during the build. Match rate: X/214. This validates AI-relevant categorization only;
> it does not score the 266 projects File A does not cover, the non-AI dimension of
> any PCA, or the 57 Advanced Wireless suggestions, which have no final category.

Rules for the claim:

* X is the only number to fill in. The denominator stays 214. Projects are never
  dropped from it after the reveal.
* No other accuracy figure is reported from File A: no precision, no recall, and no
  rate over 480.
* "57 Advanced Wireless suggestions" counts suggestions (38 first + 19 second, on
  57 distinct projects). It is the suggestion that has no final category; the project
  carrying it may still be among the 214.

### Committed match rule (rule ID `entry2-match-rule-v1-2026-10-23`)

Committed 2026-10-23, BEFORE the reveal; the key has not been read. The executable
form is `score_heldout.py` (SHA-256 recorded in the seal amendment log). Changing
either after the reveal is score-fitting and voids the result.

**What File A's labels mean.** Every File A project carries exactly one category.
The AI-PCA category means "primary PCA = AI". A "<PCA> - AI" category means
"primary PCA = <PCA>, and the project is also AI-relevant". The suffix is an
AI-relevance flag on a non-AI PCA; it is not a second PCA. All 214 key projects are
AI-relevant by construction, because that is how they entered File A.

**Proposal format (v1, superseded before the build by v2 below).** One row per
project: `appl_id`, `primary_pca` (one of the 12 PCA codes, `AW` for Advanced
Wireless, or empty), and `ai_relevant` (true/false). A second-ranked PCA, if the
engine produces one, is not scored.

**Proposal format v2 (`proposal-format-v2-2026-10-23`), committed 2026-10-23 before
the engine was built and before the reveal.** Columns: `appl_id`, `primary_pca` (one
of the 12 PCA codes, or empty; never `AW`), `ai_relevant` (true/false), and
`sub_pca` (`AW` or empty). `sub_pca` = `AW` requires `primary_pca` = `ACNS`. The
match rule and the scorer are unchanged: they read only `primary_pca` and
`ai_relevant`, so an Advanced Wireless project scores as ACNS. The build sweep's S5
enforces v2.

Why v2. NITRD's FY2025 PCA definitions print Advanced Wireless R&D as a `[Sub-PCA]`
inside the ACNS definition, so its scope is a subset of ACNS. It has no NITRD budget
line of its own and no RCDC category, so as a primary label it can never be right.
Modelling it as ACNS plus a breakout flag follows the public definition. The fixture
points the same way. Its 57 Advanced Wireless suggestions are on 57 different
projects, and no project has AW in both slots. In 55 of them the other slot holds a
PCA code (ACNS 19, CHuman 15, AI 14, EdW 4, CNPS 3); 2 have no second suggestion. Coders
treat AW as a tag added to a project, not as its PCA. The engine still has to pick
the most specific PCA, as NITRD's own rule says. If it judges a project to be
primarily CHuman with a wireless element, the proposal is CHuman with no `sub_pca`,
because AW lives inside ACNS.

What was not checked. Whether any held-out project carries an AW suggestion was not
determined, and the decision does not depend on it:

* The public hash of the sorted 214-ID list cannot answer it. A digest only confirms
  a complete list someone already has; it cannot test single IDs, and searching the
  subsets of 214 out of 480 is infeasible.
* Answering it from the sealed file would leak. Being in the 214 means "finally coded
  AI-relevant", which is half of what is scored. Even an aggregate overlap count
  would put key-derived information into a build decision.
* It would not change the choice. If no AW project is in the 214, v2 is chosen for
  fidelity and X is unaffected. If some are, v2 is still preferred, because v1 makes
  them automatic misses. The decision is v2 in both cases, so it is fixed now without
  looking.

After the reveal, the report states how many held-out projects had an AW suggestion
and how they scored. That is reporting only; the format is not changed after the
reveal.

**Mapping.** The AI-PCA category maps to (`AI`, AI-relevant). "<PCA> - AI" maps to
(`<PCA>`, AI-relevant), for the 11 non-AI codes. Any other label, such as the legacy
LSN, stops the evaluation as a key anomaly; it is reported, not remapped.

**Answers to the three questions:**

| Question | Rule |
| --- | --- |
| Does proposal `ACNS` match File A "ACNS - AI"? | Only if the proposal also sets `ai_relevant` = true. `ACNS` with the flag false is a PCA-only match, not a match. |
| Does the AI flag correspond to the "- AI" suffix? | Yes. The flag is the suffix. The AI PCA itself requires the flag (validation rejects `AI` with the flag false). |
| Does the primary PCA alone suffice? | No. **X = primary PCA equal AND AI-relevance flagged.** |

**Headline X (strict):** `primary_pca` equals the key PCA AND `ai_relevant` is
true. The denominator is fixed at 214.

**Consequences, fixed now:**

* Proposing `AI` for a "<PCA> - AI" key is a miss: AI is its own PCA, not the suffix.
  The scorer also lists these cases.
* Proposing `<PCA>` + flag for an AI-PCA key is a miss.
* No proposal, an empty `primary_pca`, or `AW` on a key project is a miss, listed
  separately. (Under format v2, `AW` cannot appear in `primary_pca`; the scorer keeps
  the case only as a fail-safe.)

**Secondary figures**, reported only with their labels and never substituted for X:

* PCA-only agreement, n/214, with the AI flag ignored;
* AI-flag recall, n/214. This is recall only: the key has no AI-negative projects, so
  precision cannot be measured.

**Stop conditions:** a key SHA-256 mismatch, a project with more than one category,
a key project count other than 214, or an unmapped label. Each one stops the run and
is reported. None is worked around.

**Freeze-time check:** `build_sweep.py --freeze` must PASS before tagging. It runs:

* S1: the guard and the scorer must match their committed SHA-256 values.
* S2: the seal guard must report CLEAN.
* S3: `score_heldout.py --validate-only`, which rejects unknown codes, a non-boolean
  flag, duplicate IDs, and `AI` with the flag false.
* S4: there must be exactly one proposal row per fixture project (all 480; an empty
  `primary_pca` is allowed) and no extra rows.
* S5: format v2. A `sub_pca` column must be present, with values `AW` or empty;
  `primary_pca` is never `AW`; and `sub_pca` = `AW` only with `primary_pca` = `ACNS`.

It never reads the key. On a PASS, it prints the proposals SHA-256, which is tagged
and logged before the reveal. During the build, the same sweep without `--freeze`
runs S1 and S2, and records S3-S5 as NOT_RUN until a proposals file exists.

**Scorer verification (synthetic data only, 2026-10-23):** a 6-project fabricated
key (IDs 90000001-6) gave strict 2/6, PCA-only 3/6, and the expected miss lists. All
four validation errors and all three stop conditions fired. The real key was not
read.

## Known exposure before sealing

During gate 0b, on 2026-10-23, an aggregate count of the 214 projects per final
category was shown in the working chat. No per-project category was shown, and no
suggestion-to-category comparison was made. Those counts are not used in the build.

## Limits of the guard

The guard is a tripwire, not access control. The same user can read the sealed
location. It catches byte copies, path references, re-saved export headers, and lines
that pair a fixture Appl ID with an RCDC final-category label. It cannot detect a
hand-transcribed answer that has no label. Isolation and this protocol are the
primary control.

## Guard verification at sealing (2026-10-23)

* Clean scratch tree with the UAC fixture, NITRD budget CSV and a proposal-style CSV:
  CLEAN, exit 0.
* The mcp-nih-reporter tree added: CLEAN (no false positives).
* Planted cases, each FAIL with exit 1 on the expected rule: copies of the held-out
  file and of A, B and C (R1); the sealed volume path in code, the upload ID, and the
  original file name used as a path (R2); a re-saved A header (R3); a fixture Appl ID
  next to a final-category label (R4). The same label with a non-fixture ID: CLEAN.
* A missing tree or fixture exits 2 (fails closed).
* No plaintext preimage of any digest occurs in the guard source.
