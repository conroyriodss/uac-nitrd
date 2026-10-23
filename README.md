# Entry 2: UAC NITRD subcategory proposals

This repo proposes NITRD PCA codes, with an AI-relevance flag, for the projects in
the ODSS UAC "uncoded" fixture. The proposals are judged once, after they are
frozen, against a held-out answer key that the build cannot see.

## Layout

| Path | What it is |
| --- | --- |
| `fixtures/UAC_Uncoded_12-01-2025-updated-NIH_ODSS.csv` | Build input: 480 FY2025 projects; `suggestion_1`/`suggestion_2` hold the subcategories |
| `context/NITRD_Budget_Tables.csv` | Context only: the NITRD budget crosscut by PCA and agency (FY2025 is a request) |
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
