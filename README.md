# UAC NITRD subcategory proposals

This repo proposes NITRD PCA codes, with an AI-relevance flag, for the projects in
the ODSS UAC "uncoded" fixture. The proposals are judged once, after they are
frozen, against a held-out answer key that the build cannot see.

**Canonical repo: https://github.com/conroyriodss/uac-nitrd** (the only remote).
The Databricks working copy lives at `/Workspace/Users/conroyri@nih.gov/entry2-uac-nitrd`.
That is a local folder path, not a second repo. No GitHub repo named `entry2-uac-nitrd`
exists, and none should be created.

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
