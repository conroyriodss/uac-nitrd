# UAC NITRD held-out result (evaluation run 1, scored once)

**Match rate: 24/214.**

Fixed claim wording (HELDOUT_PROTOCOL.md): For the 214 of 480 projects that File A finally
coded as AI-relevant (one category each), we compare our frozen proposals against NIH's
final UAC coding, held out during the build. Match rate: 24/214. This validates
AI-relevant categorization only; it does not score the 266 projects File A does not cover,
the non-AI dimension of any PCA, or the 57 Advanced Wireless suggestions, which have no
final category.

## Secondary figures (labelled; never substituted for X)

* PCA-only match: 36/214 (primary PCA equal, AI flag ignored)
* AI-flag recall: 155/214 (recall only; every key project is AI-relevant)

## Miss breakdown (report-breakdown-v1-2026-10-23; counts only)

Of the 190 misses: 176 proposed a wrong PCA (0 of them AI for a "<PCA> - AI" key),
12 proposed the right PCA without the AI flag, 2 abstained (no public RePORTER text),
0 proposed Advanced Wireless as primary. Full output: `results/heldout_report_v1.json`.

## What was scored

* Engine: deterministic text against the verbatim NITRD FY2025 scope text, the AI
  statutory definition and cross-PCA guidance; no synonyms
  (`vocabulary-scope-only-2026-10-24`); AI gate = 10 core terms, at least 1 required.
  This number is lower than a tuned vocabulary would give; the owner accepted it as the
  real held-out number (see `docs/SYNONYM_DERIVATION.md`).
* Frozen proposals: commit `b0ccbe6`, tag `uac-nitrd-freeze-v1`, produced by the single
  freeze run (`scripts/freeze.sh`, engine commit `38d5d7d`); build_sweep --freeze S1-S8 PASS.
  `proposals.csv` sha256 `08519115626ad367ea9c5b938520558e2802e763768f310864aa86c35fdb6572`.
* Constants record: `docs/REVEAL_CONSTANTS.json` (reveal-constants-v2), sha256
  `2de4670d303f04033ca1d55abbabf66341a7314f90b4ee279254673d0c14226a`.
* Scorer: `tools/score_heldout.py` (sha256 `5b9860fa...`), match rule
  `entry2-match-rule-v1-2026-10-23`, committed 2026-10-23 before the reveal.
* Key: sealed held-out file, sha256 verified
  `cbeab03e64f2dbc71a56caa68910dfabfb37dd6422284b1825ab462432b673ef` (seal
  `entry2-heldout-2026-10-23T19:18:20Z`).
* Evaluation run ID `uac-nitrd-eval-1-2026-10-25T00:46:27Z`. The scorer's full output
  (with per-project miss lists) stays with the key in the sealed volume
  (`eval_run_1/score.json`, sha256 `2d2dc7e5...`); only the count breakdown is in the repo.

## No iteration back

This comparison was run once. Any later change to the engine or proposals is a new
version, evaluated only against a new, different held-out set, never re-scored against
this one. Disclosed history before the freeze: `SEAL_AMENDMENTS.jsonl` lines 1-26.
