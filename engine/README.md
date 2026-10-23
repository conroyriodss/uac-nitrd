# Proposal engine: input and output boundaries

These two boundaries were fixed on 2026-10-23, before any engine logic existed. The
build sweep enforces them.

## 1. Inputs: project text against public scopes, nothing else

* **Reasoning input:** the project's title, abstract, and specific aims, taken from
  the public NIH RePORTER record. These are read against the verbatim NITRD PCA scopes
  and the AI cross-PCA guidance in `scope/nitrd_pca_scopes_fy2025.v1.json`.
* **What the fixture is for:** it says *which* projects to propose for, and nothing
  more. `engine/inputs.py` is the only engine file allowed to open it. It returns
  identity fields only (`Appl ID`, `FY`, `Project Number`, `SubProj`), through an
  allow-list.
* **Never read:** the fixture's two suggestion columns. They are NIH's internal assist
  output. Using them would echo NIH's suggestions instead of showing our own
  proposals, and they correlate with the held-out answer.
* **Also never read:** the coder and administrative columns (`Category`, `Class Code`,
  `PCC`, `PO Name`, `Admin IC`). The fixture's `Project Title` is excluded as well:
  text comes only from RePORTER.
* **Enforcement:** build-sweep S6 runs in every mode. It fails the build if any engine
  file names a suggestion column, if any engine file other than `inputs.py`
  references the fixture, or if the allow-list changes. A test also scrambles every
  non-identity fixture column and checks that the loader's output is unchanged.
* **S6 alone is not enough.** It is a static scan, and an engine that gets the fixture
  path as an argument, then finds a column by prefix or by position, gets past it.
  `tests/test_scramble_proof.py` contains two such engines.
* **S8 is the proof (required; no freeze without it green).**
  * **What it does:** the sweep runs the full engine offline twice. Run A uses the real
    fixture and produces `proposals_A`. Run B uses a copy in which both suggestion
    columns and every other non-identity column hold fresh random values (a new seed
    each run, recorded), and produces `proposals_B`.
  * **When it fails:** whenever `proposals_A` and `proposals_B` differ by even one
    byte. At freeze it also fails unless the committed `proposals/proposals.csv`
    equals `proposals_A`.
  * **When it runs:** in every mode once `engine/run.py` exists, so CI runs it on every
    push. With `--freeze`, a missing engine is a FAIL.

## Engine contract (required by S8)

* **Method:** deterministic text against scope, with no model (`docs/ENGINE_DESIGN.md`,
  decision `engine-method-deterministic-v1-2026-10-23`).
* **Command:** `python engine/run.py --fixture <csv> --out-dir <dir> --offline` writes
  `<dir>/proposals.csv` and `<dir>/explanations.jsonl`. The explanations file has one
  line per proposal, giving the matched scope terms, the rules applied and the AI
  evidence. S8 requires it and checks it for byte-identity too.
* **Fixture path:** it arrives only as that argument and is read only through
  `engine.inputs.load_project_refs`.
* **Offline means replay:** RePORTER text comes from a committed cache, keyed by Appl
  ID, with a SHA-256 per project. The fetcher lives in `tools/`, not `engine/`. No
  engine file may import a model client or a network library (S6). A cache miss exits
  non-zero, which fails S8; it never falls back silently.
* **Deterministic:** the same caches always give the same bytes. Rows are sorted by
  `appl_id`, with no timestamps and no dependence on row order.

## 2. Output: an assist proposal for SME review

* **What every proposals file is:** a proposal for subject-matter-expert review. It is
  **not** a reproduction of the official UAC method; no UAC fingerprints exist to
  reproduce.
* **The "most specific PCA" rule:** this is NITRD's published guidance, applied to
  project text. It is not a claim of official correctness.
* **The label:** `proposals/proposals.meta.json` carries the fixed label
  (`engine.OUTPUT_LABEL`), plus `official_uac_method: false`,
  `suggestion_columns_read: false`, and the reasoning inputs (text source, scope set
  and its hash).
* **Enforcement:** build-sweep S7 fails the freeze if the label is missing or
  altered.
