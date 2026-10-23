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
* **Limit:** S6 is a static scan, so it can't catch, say, positional indexing into a
  raw CSV row. The engine can't do that without opening the fixture, and only
  `inputs.py` may open it. Once the engine exists, the scramble test is extended to
  the whole engine: the proposals must be byte-identical with the suggestion columns
  scrambled.

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
