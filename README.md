# UAC NITRD subcategory proposals

This repo proposes NITRD PCA codes, with an AI-relevance flag, for the projects in
the ODSS UAC "uncoded" fixture. The proposals are judged once, after they are
frozen, against a held-out answer key that the build cannot see.

**Canonical repo: https://github.com/conroyriodss/uac-nitrd** (the only remote).
The Databricks working copy lives at `/Workspace/Users/conroyri@nih.gov/entry2-uac-nitrd`.
That is a local folder path, not a second repo. No GitHub repo named `entry2-uac-nitrd`
exists, and none should be created.

Part of a three-repository submission; the primary repository is
[nitrd-categorization-mcp](https://github.com/conroyriodss/nitrd-categorization-mcp), and the witness
records are in [uac-witness](https://github.com/conroyriodss/uac-witness).

## Verifying the blind evaluation from the repositories alone

The held-out answer keys live in a sealed Databricks volume that reviewers cannot see. What makes the
blind evaluation checkable anyway is a chain of hashes and timestamps in public repositories:
the key's hash is published before the predictions exist, the predictions are committed before the key
is opened, and the key published after scoring must match the hash.

| Link | Where (public) | Status |
| --- | --- | --- |
| 1. Key sealed, hash published | Task 1 FY2024 key: `docs/seal/task1_fy2024_seal_manifest.json` (commit `19689a2`, pushed 2026-10-25 as `1b08644`; see History correction), key sha256 `81350a53...`; the same hash and the seal-log hash (`b1abcd7f...`, 31 lines) in [uac-witness `records/0002`](https://github.com/conroyriodss/uac-witness/blob/main/records/0002-post-amendment-lines-29-31.json) | done |
| 2. Build could not read the key | `workflow/build_guard.py` + `tests/test_build_guard.py` (run in CI); `build/task1_fingerprint_v1/READ_MANIFEST.json` lists every file the build opened, with sha256: only the FY2019-2021 public RePORTER fetches | done (`984e895`, pushed 2026-11-03 as `881bd77`) |
| 3. Fingerprint reproducible | `tools/fetch_task1_text.py` then `tools/build_fingerprint_v1.py` reproduce `model.json.gz` sha256 `b703083d...` from inputs whose sha256 is in the READ_MANIFEST (checked byte-identical 2026-11-03). The four seed fetches (74-86 MB each) are not in git; RePORTER changes over time, so a fresh fetch can differ from them | done; seed files not yet published |
| 4. FY2026 forecast before any FY2026 NITRD membership is public | `build/task1_forecast_fy2026/` (award-level ranking and shortlist, count forecast), pushed 2026-11-03 while public RePORTER showed 0 FY2026 category-329 records | done (`984e895`, pushed 2026-11-03 as `881bd77`) |
| 5. Pre-registration frozen | `docs/TASK1_PREREGISTRATION.md` (`task1-prereg-v1-2026-11-04T18:00:50Z`, sha256 `c770a502...`), with the pinned artifact hashes, committed after the FY2024 freeze-run ranking (`build/task1_fy2024_ranking_v1/`, `5e3bfa4`), then recorded in [uac-witness `records/0004`](https://github.com/conroyriodss/uac-witness/blob/main/records/0004-task1-preregistration-freeze.json) and seal-log line 33 | done (`8409dc3`, 2026-11-04; FY2026 category-329 count 0 at the freeze) |
| 6. Reveal | key opened once by the scoring run; published key must hash to link 1; metrics recomputed from committed predictions + published key | Tier 2 (FY2024) done: key and sealed `has_any_category` supplement opened once (2026-11-04T19:39:35Z) by `tools/score_task1_fy2024_v1.py`; results `build/task1_fy2024_score_v1/` (`faadcd2`), [uac-witness `records/0005`](https://github.com/conroyriodss/uac-witness/blob/main/records/0005-task1-tier2-fy2024-reveal.json), seal-log line 35. Arm A Tier 2 recall at K 0.934 (pre-registered criterion >= 0.90: pass). The key itself is not yet published. Tier 3 (FY2022/23, not blind): `build/task1_tier3_v1/` (`acbee36`). Tier 1 (FY2026): pending until public RePORTER lists FY2026 category-329 records |

Timestamps: git commit dates are set by the committer. GitHub's server-side push records for this
repository and `uac-witness` are the independent record of when each link appeared. Those records
name the pre-rewrite SHAs (see below); map them with uac-witness record 0003.

## History correction (2026-11-04)

The history of this repository has been rewritten once. On 2026-11-04 the non-public `PCC` column
was removed from `fixtures/UAC_Uncoded_12-01-2025-updated-NIH_ODSS.csv` in every commit. The tool
was `git-filter-repo`, and it replaced that one file version only: no other file, author, date or
commit message changed. The engine never read `PCC`.

* Every commit SHA changed. The full old-to-new map is in
  [uac-witness record 0003](https://github.com/conroyriodss/uac-witness/blob/main/records/0003-correction-pcc-history-rewrite.json)
  and in seal-log line 32.
* The tag `uac-nitrd-freeze-v1` was moved to the rewritten freeze commit (`b0ccbe6` became `f945869`).
* Fixture sha256 `8c92c8af...` (superseded) became `73c87d5a...`. The frozen records that pin the old
  hash (`docs/REVEAL_CONSTANTS.json` and the Task 1 match rules v3 and v4) are not edited.
  `docs/FIXTURE_CORRECTION_v1.json` maps the old hash to the new one, and CI accepts the new hash
  through that record only.
* Records written before the rewrite (seal-log lines 1-31, older docs and commit messages) cite the
  old SHAs. Old commits may stay reachable by SHA on GitHub until GitHub Support purges them.

Commit convention: commits already used as part of the documented evidence chronology are not
squashed or rebased, amended after push, or force-pushed. The one exception is the single sanctioned
PCC rewrite above, recorded with its full old-to-new commit map in
[uac-witness record 0003](https://github.com/conroyriodss/uac-witness/blob/main/records/0003-correction-pcc-history-rewrite.json).
Any further change is made by a forward commit.

CI note (2026-11-05): build-sweep shows red on `d021181` through `c590404`, including the freeze commits
`5e3bfa4` and `8409dc3`. The sole cause was one guard test,
`tests/test_task1_seal.py::test_only_the_boundary_module_names_the_text_snapshot`, which matched the
snapshot directory name in the module docstring of `tools/rank_task1_fy2024_v1.py`. That tool is pinned in
the pre-registration, so it was not edited; the test was fixed forward in `854b507` (the tool's code must
still not name the snapshot and must read it through `sealed.load_score_text()`). It was not an
environment-bound step and not a pin mismatch. Frozen hashes are unchanged and still match
[uac-witness record 0004](https://github.com/conroyriodss/uac-witness/blob/main/records/0004-task1-preregistration-freeze.json):
pre-registration `c770a502...`, arm A FY2024 ranking `e49e844d...`, model `b703083d...`, FY2021 comparison
`6170facc...`, freeze-run tool `bc8515da...`.

## Follow the evidence for a specific task

This repository contains related categorization and evaluation work with different inputs, rules, and stages. Identify the task and its applicable protocol before interpreting an output.

| Starting question | Read first | Verification boundary |
|---|---|---|
| How are UAC subcategory proposals generated? | [Engine design](docs/ENGINE_DESIGN.md), [engine boundaries](engine/README.md), and [proposal artifacts](proposals/) | Inspect the frozen proposal and its explanation under the applicable protocol. |
| How are proposal matches evaluated? | [Held-out protocol](docs/HELDOUT_PROTOCOL.md) and the committed rule it identifies | A match result applies to that task, rule, denominator, and freeze. |
| How is the Task 1 workflow documented? | The verification-status table above and [task documents](docs/) | Check the referenced version, input manifest, prediction commit, preregistration state, and witness record separately. |
| What supports the declared seal state? | [Seal manifest](docs/seal/task1_fy2024_seal_manifest.json) and [witness repository](https://github.com/conroyriodss/uac-witness) | Hash records support comparisons when the corresponding bytes become available; they are not themselves the answer key or an independent access audit. |
| How are reviewed changes recorded? | [Store design](store/README.md) | Inspect the sandbox write invariants separately from scientific classification performance. |

Use the current status table to distinguish committed artifacts from pending work. A missing preregistration, unpublished seed file, unperformed evaluation, or unavailable review instrument is a different gap; report the specific one. Do not transfer a metric from one task or rule version to another.

## Layout

| Path | What it is |
| --- | --- |
| `fixtures/UAC_Uncoded_12-01-2025-updated-NIH_ODSS.csv` | Build input: 480 FY2025 projects; `suggestion_1`/`suggestion_2` hold the subcategories |
| `context/NITRD_Budget_Tables.csv` | Context only: the NITRD budget crosscut by PCA and agency (FY2025 is a request) |
| `scope/` | Versioned NITRD subcategory-scope objects: the 12 PCA definitions plus the Advanced Wireless sub-PCA, verbatim from nitrd.gov, with page snapshots. See `scope/README.md`. |
| `tools/build_pca_scopes.py` | Deterministically rebuilds the scope objects from the stored snapshots |
| `cache/reporter/` | Public RePORTER text (title, abstract, public health relevance) for the 480, with a per-project SHA-256 manifest. The engine replays it offline. See `cache/README.md`. |
| `tools/build_reporter_cache.py` | Builds and `--verify`s the cache from RePORTER by Appl ID, applying the same fields to every project |
| `docs/ENGINE_DESIGN.md` | Method decision: deterministic text against scope, no model, every proposal explained by the scope terms and rules that drove it |
| `store/` | **The write surface.** A sandboxed, event-sourced UAC write store that enforces the 9 write-safety invariants: the agent proposes, an authorized coder approves against the exact project snapshot, and nothing is deleted. See `store/README.md`. |
| `engine/` | The proposal engine. Input and output boundaries are in `engine/README.md`: it reasons from RePORTER project text, never reads the fixture's suggestion columns, and labels its output as an assist proposal for SME review |
| `proposals/` | The engine's output; frozen as `proposals/proposals.csv` |
| `tools/seal_guard.py` | Fails the build if the held-out key, or a path to it, enters the tree |
| `tools/score_heldout.py` | The committed match rule (`entry2-match-rule-v1-2026-10-23`); `--validate-only` at freeze |
| `tools/build_sweep.py` | The build sweep: S1 tool integrity, S2 seal guard, S3 proposal validation, S4 coverage |
| `docs/HELDOUT_PROTOCOL.md` | The held-out protocol, the fixed claim wording, and the committed match rule |

The held-out key is not in this repo, and no file here references its location.

## Build sweep (runs on every push)

```
scripts/sweep.sh            # build mode: S1 + S2; S3/S4 run if proposals/proposals.csv exists
scripts/sweep.sh --freeze   # freeze mode: S1-S4 all required; prints the proposals SHA-256 to tag
```

Exit 0 = PASS, 1 = a check failed, 2 = configuration error.

## Protocol

Freeze, reveal, compare, report. No iteration back. See `docs/HELDOUT_PROTOCOL.md`.
The only accuracy claim this evaluation supports is "Match rate: X/214", in the
exact wording given there.
