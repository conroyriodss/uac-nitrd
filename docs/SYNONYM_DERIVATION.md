# Synonym derivation v2: independent text, mechanical selection

> **Decision 2026-10-24 (project owner): the reveal uses NO synonyms**
> (`vocabulary-scope-only-2026-10-24`). v2 was run as pre-registered (below) and its
> output was judged unusable on the FY2024 output alone (seed ambiguity: "networking" ->
> careers, "spectrum" -> autism, "data management" -> center cores; CHuman, CNPS, EHCS
> under 20 docs). The engine's vocabulary is the verbatim NITRD scope text, the AI
> statutory definition and the cross-PCA guidance; the AI gate is the 10 core terms. The
> engine has no option to load a synonym file. Kept as evidence, not used:
> `docs/evidence/synonyms_v1_WITHDRAWN.json` (selected on the 480) and
> `docs/evidence/synonyms_v2_derived_NOT_APPLIED.json` (this procedure's exact output).
> X/214 therefore measures scope-text matching with no vocabulary chosen from project text.

Derivation ID: `synonym-derivation-v2-2026-10-24`. Pre-registered (this file, the seeds,
both tools and the gate rule committed) **before** the FY2024 corpus was fetched and
before any v2 synonym was computed.

## Why

The v1 synonym set (76 hand-written entries) was built by counting IT terms in the cached
text of the 480 fixture projects, after a first engine run on them. The 214 held-out
projects are among the 480. That is selection on the evaluation set: the key was never
read, but the vocabulary was tuned toward the projects it is scored on, so X/214 would be
optimistic. Project owner decision (2026-10-24): withdraw v1 and rebuild from independent
text, so that X/214 means "how well the engine assists on projects it never saw."

## Method

1. **Seeds** (`scope/synonym_seeds.v1.json`): 31 phrases, each a verbatim substring of a
   PCA's NITRD scope text, the AI definition, or a cross-PCA sentence assigning the concept
   to that PCA. Tested in `tests/test_synonym_derivation.py`.
2. **Independent corpus** (`tools/build_independent_corpus.py`): RePORTER FY2024 only.
   For each seed, the first 500 records (by appl_id) whose title or abstract contains the
   exact phrase; plus a background of 4 x 500 FY2024 records at fixed appl_id offsets
   (0, 3000, 6000, 9000). Dropped: any of the 480 appl_ids, and any record sharing a core
   project number with one of the 480 (continuations carry near-identical text). Only
   title + abstract are requested; no RCDC field (terms, pref_terms, spending categories).
   Committed as `corpus/fy2024_independent.v1.jsonl.gz` with a manifest.
3. **Selection** (`tools/derive_synonyms.py`): engine normalisation; doc-level unigrams and
   bigrams; smoothed log-odds z of doc rate in the seed-retrieved set vs background.
   Admitted iff |D_p| >= 20, df >= max(5, 5% of |D_p|), z >= 4.0, not already in the PCA's
   scope vocabulary, not made only of seed tokens; a term qualifying for several PCAs goes
   to the highest z; top 12 per PCA. No hand edits to the output.
4. **AI gate (gate-v2.1)**: the 10 verbatim core terms plus derived AI synonyms that are
   multi-word and not SME-flagged. Single derived words never set `ai_relevant`.

## Known limitations (stated before seeing results)

* Seed-retrieved sets reflect how NIH projects use NITRD words, which is not the same as
  NITRD R&D (for example, "privacy" retrieves clinical-data privacy work).
* Some seeds ("high-capability computing", "human-to-machine") may retrieve fewer than 20
  FY2024 records; those PCAs then get no derived synonyms. That is reported, not patched.
* The background is a deterministic appl_id-ordered spread, not a random sample.
* The FY2024 corpus is independent of the 480 at the project level, not at the PI or
  institution level.
* Whatever the procedure outputs is used as-is. SME review can flag entries; flagging
  removes them from the AI gate only, and any further change is a new, dated amendment
  before the reveal.
