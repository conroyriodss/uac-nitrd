# Task 1 pre-registration: disclosed deviations

This file lists every known place where the frozen pre-registration
(`docs/TASK1_PREREGISTRATION.md`, `task1-prereg-v1-2026-11-04T18:00:50Z`, sha256 `c770a502...0280`, commit
`8409dc3`) says something different from what the scoring run did. The pre-registration is not edited.
Each entry gives what the frozen text says, what was done, when the operative definition was fixed, and
what it changes.

## D1. Tier 2x is described with the wrong set (found 2026-11-06)

**What the pre-registration says.**
* Section 2, Tier 2x row: "FY2024 File A awards (`filea_exposed = true`), 2,281 awards".
* The exposure ledger row for FY2024 ("File A ID columns read: 2,281 AI-tagged NITRD awards ... exposed
  subset, Tier 2x") ties the same count to Tier 2x.

**What was scored.** The scorer split Tier 2 and Tier 2x on the sealed key's `filea_exposed` column.
* `tools/score_task1_fy2024_v1.py`: `scopes = {"tier2": ~filea, ..., "tier2x": filea, ...}`.
* The seal manifest defines that flag as
  `"filea_exposed": "core appears in File A, any FY (Project Number identity column)"`
  (`docs/seal/task1_fy2024_seal_manifest.json`).

**Two different sets.**

| Set | Rule | Count | Source |
| --- | --- | --- | --- |
| FY2024 File A appl_ids | the appl_id is a FY2024 row of File A | 2,281 | seal manifest `fy2024_label_reads_before_seal` entry 3, `"filea_fy2024_appl_ids": 2281` |
| Scored Tier 2x | the FY2024 award's **core project** appears in File A in **any** FY | 2,642 | `build/task1_fy2024_score_v1/report.json`: `universe_counts.filea_exposed = 2642`, `scopes.tier2x.n = 2642` |

The 2,281 is a count quoted from the first rule, placed next to a flag that runs on the broader second
rule. The pre-registration's description of Tier 2x is wrong.

**The operative definition predates the reveal.**
* The flag definition was committed with the seal manifest in `19689a2` (2026-10-25T18:34:56Z).
* That is before the pre-registration froze (`8409dc3`, 2026-11-04T18:03:05Z), and before the key was
  opened (2026-11-04T19:39:35Z, `READ_MANIFEST.json`).
* The key's `filea_exposed` column was written at the seal and was not derived or changed at scoring time.

**No reported figure changes.** The scoring was internally consistent:
* Tier 2 n = 61,423 and Tier 2x n = 2,642, which sum to the universe of 64,065.
* NITRD positives: 1,479 in Tier 2 plus 2,081 in Tier 2x make 3,560, the universe total.
* Every published Tier 2 and Tier 2x figure, including Tier 2 recall 0.934, was computed on the 61,423 /
  2,642 split. None is recomputed or restated here.
* The File-A-independent figure, all-awards FY2024 recall 0.958, does not use the split at all.

**Not determinable without a further sealed read.**
* How many of the 2,281 FY2024 File A appl_ids are inside the filtered 64,065 universe, and therefore
  inside the 2,642.
* The committed outputs are aggregates only ("no per-award label leaves the run"), so answering this
  would need File A or the key to be read again. It has not been checked.

## D2. The File A stratification has a known parse failure (disclosed 2026-11-06)

* The seal manifest records `"filea_project_numbers_unparsed": 95`. There were 95 File A Project Number
  values from which no core project number could be parsed.
* A File A row whose Project Number did not parse cannot mark its core as exposed. Any such core that
  has a FY2024 award, and no other parsed File A row, would sit in Tier 2 (blind) when it should be in
  Tier 2x (exposed).
* The error can only go one way: it can move awards from Tier 2x into Tier 2, never the reverse.
* How many FY2024 awards it affects, from 0 up to the awards of at most 95 cores, cannot be determined
  without reading File A again.
* The manifest gives the bare number only. It does not say whether 95 counts File A rows or distinct
  Project Number values.
* This is a data-quality caveat on the split. It is not a change to any reported figure.
