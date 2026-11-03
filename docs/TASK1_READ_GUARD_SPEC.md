# Task 1 fingerprint builder: read guard (spec, DRAFT 2026-11-03)

Status: implemented in `workflow/build_guard.py` (`task1-build-read-guard-v1`),
tests `tests/test_build_guard.py` (run in CI with the rest of `tests/`, so a
failure blocks). Not yet committed. Mode "build" (the fingerprint builder and
the FY2019-2021 fetches) and mode "forecast" (the FY2026 fetch and forecast:
FY2026 identity + text only, no label field, no warehouse).

## Purpose

The FY2021-seeded fingerprint builder, and any shortlist-rule fitting or
threshold choice, must never read reserved-year NITRD membership, File A, the
sealed volume, or any artifact derived from them. The guard makes that a
technical property of the build process, not a convention.

## Scope: what counts as "the builder"

Every process started by the build entry point (`tools/build_fingerprint_v1.py`,
name TBD) and everything it imports, up to and including writing the
fingerprint and the shortlist-rule file. Scoring and reveal code is out of
scope (it runs later under the existing seal boundary,
`workflow/sealed.py`).

## Denied inputs (any read is a hard failure)

| # | Path or source | Why |
|---|---|---|
| D1 | `build/universe/fy2022.csv`, `build/universe/fy2023.csv` | FY2022/23 per-award NITRD flag (public since `1b81fdd`) |
| D2 | `build/universe/fy2024_identity.csv` | scoring-year identity; not needed to build |
| D3 | `build/baseline/**`, `dev/baseline/**` | carry-forward predictions and backtests derived from FY2022/23 labels |
| D4 | `build/reconciliation/**` | per-award FY2021-23 NITRD flags (crosswalk) |
| D5 | `fixtures/UAC_Uncoded_12-01-2025-updated-NIH_ODSS.csv`, `cache/reporter/**` | FY2025 480 NITRD awards and their text |
| D6 | any location holding a seal marker file, or below one (`workflow/sealed.py`): the sealed volume as a whole (File A, the FY2025 held-out file, the Task 1 FY2024 key, any future three-state supplement). Its path is not named in the tree (the seal guard forbids it) | sealed and exposed label data |
| D7 | `cache/task1_fy2024_text/**`, `corpus/fy2024_independent*` | scoring-year text |
| D8 | RePORTER API requests with `fiscal_years` containing any year other than 2019-2021, or with `spending_categories` / `SpendingCategories*` / `Terms` for any year other than 2021 | label or scoring-year reads |
| D9 | Warehouse SQL on `users.conroyri.nitrd_hackathon_v1_*` that is not restricted to `file_fy <= 2021 AND fy <= 2021`, or that touches `nitrd_cores` (holds last NITRD FY up to 2023) | reserved-year labels in Unity Catalog |

## Allowed inputs (allow-list; anything else is denied)

| # | Input | Use |
|---|---|---|
| A1 | FY2021 text (title, abstract, PHR) and FY2021 NITRD flag + three-state status, fetched for this build into a new `build/seed_fy2021/` | seed of record |
| A2 | FY2019-2020 text only (no labels, no spending categories) | term stabilization only (for example, a document-frequency floor across years); never a positive or negative example |
| A3 | The universe-filter definition (QVR reconstruction rules) as code constants | universe construction |
| A4 | Generic resources (stop words, tokenizer) pinned by sha | preprocessing |

## Enforcement layers

1. **Allow-list loader.** The builder reads files only through one function
   `guarded_open(path)`. It resolves the real path (symlinks, `..`) and
   refuses anything not under an allow-listed root, before opening.
2. **Process audit hook.** At builder start, `sys.addaudithook` refuses
   `open`, `os.listdir`, `os.scandir` and `shutil.copyfile` events for any
   denied path (D1-D7), so a stray `open()` or `pandas.read_csv()` that
   bypasses the loader also fails. Known gap: native readers that do not go
   through Python's audit events (for example `pyarrow`'s C++ file system) are
   not covered, so the builder must not import `pyarrow` file readers; a test
   pins that.
3. **Network guard.** The only HTTP client the builder may use is a wrapper
   that checks every RePORTER request body against D8 before sending.
4. **SQL guard.** The builder does not query the warehouse. If a later version
   needs it, every statement goes through a checker that enforces D9.
5. **Read manifest.** The builder writes `build/seed_fy2021/READ_MANIFEST.json`:
   every file it opened with its sha256, and every API request body with its
   sha256 and record count. The pre-registration pins this manifest's hash.
   Reviewers can check that it lists only A1-A4.

## Tests (must pass before the pre-registration is hashed)

* Each denied path D1-D7 opened through `guarded_open`, through plain `open`,
  through `pandas.read_csv`, and through `os.listdir`: refused, with the rule
  ID in the message.
* A symlink and a `..` path to a denied file: refused.
* A RePORTER request body for FY2022 text, and one for FY2021 with
  `spending_categories` beyond the seed: refused before any network call.
* Control: every allow-listed input reads normally.
* Fault injection: remove the audit hook, then show the plain-`open` test
  fails (proves the hook is what blocks it).
* The real build's `READ_MANIFEST.json` contains no path outside A1-A4.

## Not covered (stated limits)

* People. The guard stops code, not someone looking at a file. Human exposure
  is recorded in the pre-registration's exposure ledger.
* Knowledge already in this project (the FY2022/23 backtest numbers, File A
  composition). Disclosed, not guardable.
