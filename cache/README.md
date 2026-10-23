# RePORTER text cache (`reporter-text-v1`)

The engine replays this public text offline. It was built by
`tools/build_reporter_cache.py` from the NIH RePORTER v2 API
(`/v2/projects/search`, by Appl ID) on 2026-10-23. The exact time is
`fetched_at_utc` in the manifest.

| File | What it is |
| --- | --- |
| `reporter_text.v1.jsonl` | One canonical JSON record per fixture Appl ID (480), sorted by `appl_id`. SHA-256 `18926932e261353eb2513df54508db822b3bceb6d47f469b69c69714f138f935`. |
| `MANIFEST.json` | The request spec, counts, the file hash, and a SHA-256 for each project's record. |

## What each record holds

Each record has `appl_id`, `status`, `project_num`, `fiscal_year`, `title`, `abstract`,
`public_health_relevance` and `specific_aims`. The text is exactly as RePORTER returns
it. Nothing else is kept: RePORTER's `terms`, `pref_terms`, `spending_categories` and
every other field are dropped, both in the request (`include_fields`) and again on
receipt.

## The same rule for every project

* **Which projects:** the builder gets Appl IDs only from `engine.inputs.load_project_refs`,
  which exposes identity columns only.
* **Never read:** the suggestion columns, Category, any coder column, and any RCDC
  export.
* **Same treatment:** every project gets the same fields and the same handling, on one
  code path.
* **Tested:** a test builds the cache from the real fixture and from a scrambled copy,
  and checks that the output is byte-identical.

## Coverage, as fetched

| | Projects |
| --- | --- |
| Found | 478 of 480 |
| Not found by Appl ID | 2 (`11189671`, `11376321`). They are kept as `status: not_found`, and the engine abstains on them. There is no per-project workaround. |
| With an abstract | 478 |
| With public health relevance | 375 |
| With specific aims | 0. The public API doesn't expose aims for any project, so the field is `null` everywhere. Aims that an abstract contains are included through the abstract. |

## How a reviewer checks it

Run `python tools/build_reporter_cache.py --fixture <fixture csv> --out cache/reporter --verify`.
It re-fetches every project from RePORTER and compares each record's hash with the
manifest. On 2026-10-23 it reported `records_differing: 0` and `jsonl_identical: true`.

A later run may show differences if RePORTER has edited a record. A difference means
the public record changed; it doesn't mean the cache was altered. The committed hashes
show what the engine actually read.

## Seal guard

The seal guard scans this directory; a planted sealed-path token here is flagged. The
committed cache is CLEAN.

The cache contains no occurrence of "NITRD" at all. Every RCDC category label starts
with "NITRD - ", so no Appl-ID-plus-category pair can be present, and
`tests/test_reporter_cache.py` checks this on every build.
