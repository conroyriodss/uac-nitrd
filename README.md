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
| 1. Key sealed, hash published | Task 1 FY2024 key: `docs/seal/task1_fy2024_seal_manifest.json` (commit `1b08644`, 2026-10-25), key sha256 `81350a53...`; the same hash and the seal-log hash (`b1abcd7f...`, 31 lines) in [uac-witness `records/0002`](https://github.com/conroyriodss/uac-witness/blob/main/records/0002-post-amendment-lines-29-31.json) | done |
| 2. Build could not read the key | `workflow/build_guard.py` + `tests/test_build_guard.py` (run in CI); `build/task1_fingerprint_v1/READ_MANIFEST.json` lists every file the build opened, with sha256: only the FY2019-2021 public RePORTER fetches | done (`881bd77`) |
| 3. Fingerprint reproducible | `tools/fetch_task1_text.py` then `tools/build_fingerprint_v1.py` reproduce `model.json.gz` sha256 `b703083d...` from inputs whose sha256 is in the READ_MANIFEST (checked byte-identical 2026-11-03). The four seed fetches (74-86 MB each) are not in git; RePORTER changes over time, so a fresh fetch can differ from them | done; seed files not yet published |
| 4. FY2026 forecast before any FY2026 NITRD membership is public | `build/task1_forecast_fy2026/` (award-level ranking and shortlist, count forecast), pushed 2026-11-03 while public RePORTER showed 0 FY2026 category-329 records | done (`881bd77`) |
| 5. Pre-registration frozen | `docs/TASK1_PREREGISTRATION.md` with its sha256 and the pinned artifact hashes, committed, then recorded as the next `uac-witness` record | pending (target 2026-11-07) |
| 6. Reveal | key opened once by the scoring run; published key must hash to link 1; metrics recomputed from committed predictions + published key | after the freeze |

Timestamps: git commit dates are set by the committer. GitHub's server-side push records for this
repository and `uac-witness` are the independent record of when each link appeared.

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
