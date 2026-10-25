# NITRD workflow skeleton (Tasks 1-3): DEV / not scored

`nitrd-workflow-skeleton-v0-2026-10-25`. Plumbing only: it shows the whole pipeline running before
any Task 1 seal or reveal. Nothing here is a score.

## Stages

| Stage | Code | Writes |
| --- | --- | --- |
| Task 1 shortlist | `workflow/shortlist.py` | `shortlist.csv`, `evidence.jsonl` (term -> field + character span), PROPOSALS into the Task 1 store |
| SME | store API (`approve`, `reject`, `propose` as coder = SME-added) | store events |
| Task 2 subcategory | `workflow/subcategory.py` -> `engine/run.py` unchanged | engine outputs, PROPOSALS into the Task 2 store |
| SME | store API | store events |
| Task 3 drift | `workflow/drift.py` | `drift_report.json` / `.md`, for SME review |

Runner: `python tools/dev_pipeline.py --out <new dir>`. Demo: notebook "NITRD Workflow DEV Skeleton".

## Two governed stores

The store (`store-invariants-v1`, unchanged) keeps one active assignment per project across
crosscuts in an FY (invariant 8), so the stages use separate store roots:

* **Task 1 store**: crosscut `NITRD_PARENT`, single code `NITRD`, listing = the DEV award universe.
  The agent proposes; an SME approves or rejects, and can add an award the candidate shortlister missed by
  proposing it as a coder (invariant 1 still holds: only awards in the universe).
* **Task 2 store**: crosscut `NITRD`, listing = the awards with an active Task 1 assignment. The
  Task 1 output becomes the Task 2 parent listing, and all 9 invariants apply as before.

## Candidate shortlister (parent-match model)

Terminology: in these docs, **"fingerprint" means only RCDC's thesaurus-based category
fingerprint** (a weighted list of RCDC Thesaurus concepts). Our Task 1 tool is a different
mechanism and is called the **candidate shortlister** (or parent-match model). File names, IDs and
environment variables that already contain "fingerprint" (for example
`nitrd-parent-fingerprint-placeholder-v0-2026-10-25`, `UAC_NITRD_TASK1_FREEZE_RUN`) are pinned audit
references and keep their names.

`workflow/fingerprint/nitrd_parent_fingerprint.placeholder.v0.json` (sha256 pinned in
`workflow/common.py`) is the shortlister's **placeholder** term list. It is built mechanically by
`tools/build_fingerprint_placeholder.py` from the committed NITRD scope file: 2-3 word scope
phrases plus the engine's 10 AI core terms, with the engine's normalisation. It is not the
curated term list. It's versioned and SME-owned: a committed version is never rewritten (the
tool refuses), and a change ships as a new file with a new pin. Task 3 records the term list's
hash before and after, and never edits it.

Known placeholder weakness, visible in the DEV run: nested n-grams ("natural language",
"language processing", "natural language processing") count as 3 distinct terms.

## Boundaries

* DEV slice `dev/fy2023_dev_slice` (`tools/build_dev_slice.py`, run once, committed): 300 FY2023
  NIH awards, identity + title/abstract/PHR only, no RCDC or category field, no core project of the
  480. FY2023 is the proposed build FY.
* `workflow/common.py` refuses FY2024 (proposed Task 1 score FY) and FY2025 (contaminated), mixed
  FYs, and any of the 480 evaluation projects. The freeze guard also still refuses the 480 inside
  the engine.
* Input boundary 1: fixtures are read only through `engine.inputs` (identity columns). A test
  shows the shortlist is byte-identical with random suggestion/category/title columns added.
* SME decisions in the DEV run come from `workflow/sme_standin.py`, a rule-based **stand-in**
  whose rules are printed in every decision record. They are not SME judgments, so the drift
  report on DEV reflects the stand-in's rules, not real shortlister drift.
* Deterministic and offline: two runs give byte-identical files and identical store-state digests
  (only the event timestamps differ).
