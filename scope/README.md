# NITRD subcategory scopes

These files are the public domain knowledge the proposal engine reasons against. Each
scope set is a versioned JSON object, built by `tools/build_pca_scopes.py` from a
stored snapshot of the public NITRD PCA-definitions page. Scope text is NITRD's wording,
verbatim; nothing is paraphrased.

| File | FY | Version | Status |
| --- | --- | --- | --- |
| `nitrd_pca_scopes_fy2025.v1.json` | 2025 | 1 | **Active**: matches the fixture FY. These are the definitions agencies used to compile FY2025 PCA budgets. |
| `nitrd_pca_scopes_fy2026.v1.json` | 2026 | 1 | Reference only: shows how the wording drifts from FY2025 |
| `sources/nitrd-pcas-2025.html`, `sources/nitrd-pcas-2026.html` | | | Raw page snapshots. The SHA-256 of each is recorded in its scope set. |

Source: NITRD NCO, https://www.nitrd.gov/program-component-areas/nitrd-pcas-2025/ (and `-2026/`),
retrieved 2026-10-23T20:27:56Z and 20:27:57Z (the HTTP `Date` header for each fetch).

## Object fields

* **Set level:** `schema`, `scope_set_id`, `version`, `fiscal_year`, and `source`. `source` holds publisher, title, url, retrieved_at_utc, snapshot_file, snapshot_sha256 and text_policy.
* **`scopes[]`:** `code`, `label`, `kind` (`pca` or `sub_pca`), `standard_pca`, `selectable`, `parent`, `uac_suggestion_value`, `budget_crosscut_code`, `scope_text`, `annotations`. AW also has a `rollup` block.
* **`cross_pca_guidance`:** NITRD's statutory AI definition, plus its examples of where AI work falls among other PCAs. Example: general machine vision is AI, but robots that use machine vision are IRAS. NITRD's closing rule is "report an activity under the PCA that is most specific to that activity".

## Advanced Wireless R&D

AW is represented as `kind: sub_pca`, `parent: ACNS`, `standard_pca: false`, `selectable: true`:

* **Nested under ACNS:** NITRD prints it as a `[Sub-PCA]` inside the ACNS definition, so its scope is a subset of ACNS's.
* **Selectable:** the UAC fixture offers "Advanced Wireless R&D" as a suggestion value alongside the 12 codes.
* **Not a standard PCA scope:** it has no line in the NITRD budget crosscut and no category in the RCDC exports.
* **Roll-up `UNRESOLVED`:** no source in hand says whether an AW assignment also counts toward ACNS. Until that is confirmed, AW dollars are neither added into ACNS totals nor subtracted from them; AW is reported separately.

Scoring is unchanged. Under the committed match rule, an `AW` primary proposal on a
held-out project is a miss, and AW has no final category to score against.

## Versioning

If the source page changes, or a field changes meaning, the version goes up. Never edit
a published version in place. A new version needs a new snapshot, a new retrieval time
and a new file, and the older file stays.
