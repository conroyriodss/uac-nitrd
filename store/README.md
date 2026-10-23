# Sandboxed UAC write store (`store-invariants-v1-2026-10-23`)

This is the write surface. The proposal engine *proposes* into the store, and an
authorized coder (the SME) *disposes*. Every write is checked against the 9 UAC
write-safety invariants before it is appended to `events.jsonl`. State is only ever
derived from that log, so a replay rebuilds it exactly. Nothing is deleted, and every
refusal is logged.

It is a sandbox. The store writes only `SANDBOX.json` and `events.jsonl` under its
root, it is not RCDC, and every roll-up carries the label `SANDBOX write store (not RCDC)`.

## Built test-first

`tests/test_store_invariants.py` (52 tests) was written before the store. It was run
against a naive store that had the same API and no governance: 49 failed and 3
passed. The 3 that passed were a control test and two checks for an API that
shouldn't exist. The evidence is in `docs/evidence/store_red_run.txt` and
`docs/evidence/store_naive_red_baseline.py.txt`.

The governed store then passes all 52. The test file is byte-identical between the
red run and the green run (SHA-256 `d793af37…`).

## The invariants, as implemented

| # | Invariant | What the store does |
| --- | --- | --- |
| 1 | No new projects | A write is accepted only for an Appl ID in a loaded parent listing for that crosscut and FY. A listing is fixed once loaded, and there is no API to add projects. |
| 2 | Exactly one primary | A coding has exactly one primary subcategory; zero, several, unknown codes, or `AW` as primary are rejected. A project has at most one active assignment per crosscut and FY. |
| 3 | AI terminal | NITRD primary `AI` requires `ai_relevant` = true and no `sub_pca`. `add_coding` on an AI assignment is rejected. |
| 4 | 100%, never prorated | `share` must be exactly 1. The amount always comes from the listing; the caller can't pass one. Parent total = the sum of full assignment amounts, and parent total + uncoded = listing total, asserted on every roll-up. |
| 5 | Exclusion governed | `flag_exclusion` opens an MR flag, `PENDING_SIACB`, and the project stays in the totals. Only an SIACB member can decide `exclude` or `retain`. An exclusion is recorded; the project and its history are kept. There is no delete API. |
| 6 | Type-5 rollover | A type-5 project in the new FY carries forward the prior FY's *approved* coding of the same core project and subproject. The run needs an authorized coder, keeps a link to the prior assignment, is bound to the new snapshot, and is idempotent. Competing renewals, other types, and priors that were only proposed are listed as needing coding. |
| 7 | Agent proposes, SME disposes | A proposal is never counted. Only an authorized coder approves, overrides or rejects. The approval must carry the snapshot hash the coder saw, and that hash must equal both the proposal's snapshot and the current one. A snapshot update makes pending proposals `STALE`. |
| 8 | Non-overlap crosscut | A project listed in several crosscuts is assigned in only one. The higher match score wins; a tie is rejected until an SME resolves it. An existing assignment in another crosscut blocks the new one and is reported by `conflicts()`. Nothing is moved automatically. |
| 9 | AW surfaced ambiguity | Dollars for ACNS + `sub_pca` AW go into `aw_unresolved`, not ACNS. `acns_complete` is false and `unresolved` names the open decision. Only a coder can record `fold_into_acns` or `report_separately`. There is no default, and the decision is logged. |

## Interpretations to confirm (SME)

These readings of UAC practice are encoded and tested. Each is easy to change, but
none should change silently.

* **Dollars:** the fixture has no dollar column. The amounts come from the parent
  listing that is loaded, synthetic in the tests. Real amounts need a permitted
  source.
* **Exclusion flags:** an agent, a coder or an SIACB member may raise an MR flag.
  Only an SIACB member may decide one.
* **Rollover:** the source is this store's own prior-FY approved assignments. It is
  never an RCDC export: File A is off-limits. A rollover counts as an authorized coder
  applying the standing type-5 rule, not as a new SME judgment.
* **Non-overlap:** an existing assignment is never displaced automatically, even by a
  higher-scoring rival, because invariant 7 forbids writes nobody approved.
* **AW resolution:** it is made once per crosscut and FY and applies to all AW-tagged
  projects. A later resolution supersedes it and is logged as well.
* **Other crosscuts:** subcategories other than NITRD's, such as NNI, are not
  modelled. A crosscut other than NITRD must declare its codes when its listing is
  loaded.

## API

* **Construction:** `SandboxStore(root, authorized_coders, siacb_members)` replays any
  existing log under `root`.
* **Writes:** `load_listing`, `propose`, `approve`, `reject`, `add_coding`,
  `update_snapshot`, `flag_exclusion`, `siacb_decide`, `rollover`,
  `resolve_crosscut_tie`, `resolve_aw_rollup`.
* **Reads:** `rollup`, `assignments`, `assignment`, `proposal`, `mr`, `history`,
  `conflicts`, `rejections`, `listing_status`.
