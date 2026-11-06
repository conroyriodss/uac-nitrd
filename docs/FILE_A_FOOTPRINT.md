# File A footprint: every read and every derived artifact (audit 2026-11-06)

**Scope.** This audit covers the three repositories (`entry2-uac-nitrd`, `nitrd-mcp`, `uac-witness`) plus the one workspace folder outside them that held seal-time code. File A itself was not opened. The search was a regular-expression scan of every tracked file, in the current tree and in history (`git log -S`). The terms were: "File A", `filea`, `file_a`, the File A, held-out, sorted-ID-list and seal-manifest digests, Tier 2x, "/214", the held-out report, `open_sealed_key` and `load_key`. Each hit was then read and classified.

**The class is closed by a test.** `tests/test_file_a_footprint.py` recomputes the set of files in this repository that match those terms. It fails if the set differs from section 4 below. A new File A reference therefore cannot be committed without updating this inventory.

## 1. Uses: what File A was read for

| # | Date (UTC) | Read | What it produced | Where it is recorded |
|---|---|---|---|---|
| U1 | 2026-10-23 (gate 0b) | the 214-project held-out file | aggregate count of the 214 per final category, shown in the working chat; not used in the build | `docs/HELDOUT_PROTOCOL.md:266-270` |
| U2 | 2026-10-23 (gate 0c, seal) | File A rows with FY = 2025 and an Appl ID in the UAC fixture | the held-out file (214 projects, 240 rows), sealed by digest | `docs/HELDOUT_PROTOCOL.md:7-21` |
| U3 | 2026-10-25 00:46Z (reveal, scored once; run `uac-nitrd-eval-1-2026-10-25T00:46:27Z`, commit `1346b63`) | the held-out file, by `tools/score_heldout.py` | UAC held-out "Match rate: 24/214", plus secondary figures and miss counts | `results/RESULT.md`, `results/heldout_report_v1.json` |
| U4 | 2026-10-25 (before the seal) | File A FY2024 identity columns (selection-effect check, entry 3) | aggregates: 2,281 FY2024 appl_ids, 2,155 cores, and 1,365 FY2021-2023 cores that are also FY2024 cores. They are the source of the pre-registration's "2,281" and of hypothesis H2 | `docs/TASK1_MATCH_RULE.md:94-97` (and v2-v4), `docs/seal/task1_fy2024_seal_manifest.json` (`fy2024_label_reads_before_seal`) |
| U5 | 2026-10-25 17:56Z (Task 1 seal) | File A `Project Number` column, any FY | the `filea_exposed` column of the sealed FY2024 key, and 95 unparsed project numbers | seal manifest `groups` and `identity_aggregates`; `docs/TASK1_PREREG_DEVIATIONS.md` |
| U6 | 2026-11-04 19:39Z (Task 1 reveal, scored once) | the sealed key, including `filea_exposed`, by `tools/score_task1_fy2024_v1.py` | the Tier 2 / Tier 2x split: 61,423 / 2,642 awards | `build/task1_fy2024_score_v1/report.json`, uac-witness record 0005 |

U1-U3 are the UAC held-out evaluation. U4-U6 are Task 1. U4 is a third, separate read: it happened before the seal and fed the match-rule design.

## 2. Code that reads File A or a sealed file derived from it

| File:line | Reads | Committed? |
|---|---|---|
| workspace `entry2-seal/task1_seal_fy2024.py:37-38, 131-151, 189` | **File A itself** (`Project Number` column), to build `filea_exposed` (U5); its log entry at :67-69 records U4 | **No.** The file lives outside every repository. Only its outputs are committed: the manifest and the text snapshot, in `19689a2` |
| `tools/score_heldout.py:100-115` (`load_key`) | the held-out file (U3), digest-checked | yes |
| `tools/score_task1_fy2024_v1.py:133-134, 154, 158` | the sealed key and its `has_any_category` supplement (U6). The supplement comes from RePORTER, not File A | yes |
| `workflow/sealed.py:61-66` (`open_sealed_key`) | the only gate to the sealed key; it refuses unless `UAC_NITRD_TASK1_SCORE_RUN=1` | yes |
| none found | the code that extracted the held-out file (U2) and ran the U1 and U4 aggregates | **No code exists in the repositories or the workspace scan.** These steps are recorded in prose only (section 1) |

No code in `nitrd-mcp` or `uac-witness` reads File A or anything derived from it. In `nitrd-mcp` the matching terms appear only in documentation and the submission files (section 4).

## 3. Committed content derived from File A, by kind

* **Per-award identifiers.** `results/heldout_report_v1.json` lists two held-out Appl IDs, 11189671 and 11376321, as abstentions. This is the only per-award File A-derived content found.
* **Label-format example.** `docs/HELDOUT_PROTOCOL.md:165` quotes one File A category string as an example of the label format. No Appl ID is on that line.
* **Aggregates and figures:**
  * U3: `results/RESULT.md` and `results/heldout_report_v1.json`.
  * U4: the TASK1_MATCH_RULE files and the seal manifest.
  * U5: the seal manifest's `groups` and `identity_aggregates` (cores 1,757 + 695 exposed).
  * U6: `build/task1_fy2024_score_v1/report.json` (`tier2x` scopes, `filea_exposed: 2642`), `docs/PERFORMANCE_VS_REPORTED.md:23,34` (Tier 2x recall 0.974), and the README rows.
  * Also: `docs/HELDOUT_PROTOCOL.md:16,35-38` (held-out size; File A, B and C overlap counts with the fixture).
* **Digests only.** File A, held-out, sorted-ID-list and manifest digests appear in `docs/HELDOUT_PROTOCOL.md:17-20`, `tools/seal_guard.py:36-41` (and its header-line and label hash sets), `uac-witness/records/0001` (:39, :59, :63) and `0002` (:43, :63, :67). The sealed key's digest `81350a53...` is in `uac-witness/records/0004:15` and `0005:18`.

## 4. Inventory of files in this repository that match the audit terms (the test's expected set)

The Kind column uses these letters:
* R: code that reads (section 2);
* D: content derived from File A (section 3);
* C: code or tests that consume Tier 2 / Tier 2x labels without reading File A;
* G: guard or prohibition text only;
* A: this audit.

| File | Kind |
|---|---|
| `README.md` | D (reveal row, D1/D2, X/214) |
| `build/task1_backtest_vs_reported_v1/report.json` | D (mixed-scope label) |
| `build/task1_fy2024_score_v1/report.json` | D (U6) |
| `docs/FILE_A_FOOTPRINT.md` | A |
| `docs/HELDOUT_PROTOCOL.md` | D (U1-U3) |
| `docs/PERFORMANCE_VS_REPORTED.md` | D (U6) |
| `docs/SYNONYM_DERIVATION.md` | D (X/214 wording) |
| `docs/TASK1_MATCH_RULE.md`, `docs/TASK1_MATCH_RULE_v2.md`, `docs/TASK1_MATCH_RULE_v3.md`, `docs/TASK1_MATCH_RULE_v4.md` | D (U4, the H2 definition) |
| `docs/TASK1_PREREGISTRATION.md` | D (2,281 from U4) |
| `docs/TASK1_PREREG_DEVIATIONS.md` | D (U5, U6) |
| `docs/TASK1_READ_GUARD_SPEC.md` | G |
| `docs/reference/subcategory_id_to_pca.v1.md` | G (public-status note) |
| `docs/seal/task1_fy2024_seal_manifest.json` | D (U4, U5) |
| `proposals/FREEZE_SWEEP.json` | G (seal-guard result) |
| `results/RESULT.md`, `results/heldout_report_v1.json` | D (U3) |
| `scope/README.md`, `store/README.md` | G |
| `tests/test_build_guard.py`, `tests/test_synonyms.py` | G |
| `tests/test_file_a_footprint.py` | A |
| `tests/test_report_heldout.py`, `tests/test_task1_seal.py` | C (synthetic data only) |
| `tools/backtest_vs_reported_v1.py`, `tools/compare_arms.py`, `tools/rank_task1_fy2024_v1.py`, `tools/report_heldout.py`, `workflow/reveal_metrics.py` | C |
| `tools/build_reporter_cache.py`, `workflow/build_guard.py`, `workflow/common.py` | G |
| `tools/score_heldout.py`, `tools/score_task1_fy2024_v1.py`, `workflow/sealed.py` | R |
| `tools/seal_guard.py` | D (digests only) |

Other repositories, not covered by the test:
* `nitrd-mcp`: `eval/README.md`, plus `submission/NITRD_Evaluation_2026-11-06.docx` and `NITRD_Hackathon_Presentation_2026-11-06.pptx` (and their `.txt` extracts). These are disclosure text, D.
* `uac-witness`: `records/0001`, `0002`, `0004` and `0005` (digests).
* No other `nitrd-mcp` source file matches.
