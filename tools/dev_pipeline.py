#!/usr/bin/env python3
"""Run the NITRD workflow skeleton end to end on the committed DEV slice. DEV / not scored.

  Task 1  shortlist (placeholder fingerprint) -> PROPOSALS in the Task 1 governed store (PENDING)
  SME     DEV stand-in decisions (approve / reject / add) through the store API
  Task 2  engine subcategory proposals for the SME-confirmed set -> Task 2 governed store
  SME     DEV stand-in approves Task 2 proposals
  Task 3  drift report from the Task 1 store's decisions (for SME review; fingerprint untouched)

Offline and deterministic: every file except the stores' event timestamps is byte-identical across
runs; PIPELINE.json records the hashes plus a timestamp-free digest of each store's state.
Refuses the reserved FYs and any of the 480 evaluation projects (workflow.common, freeze guard).

Usage: python tools/dev_pipeline.py --out <new dir> [--slice dev/fy2023_dev_slice]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from store import SandboxStore  # noqa: E402
from workflow import drift, shortlist, sme_standin, subcategory  # noqa: E402
from workflow.common import (DEV_LABEL, DEV_SLICE, FINGERPRINT, WORKFLOW_ID, DevBoundaryError, load_cache,  # noqa: E402
                             sha256, write_json)


def state_digest(store) -> str:
    """Timestamp-free digest of a store's derived state (proposals + assignments)."""
    s = {"proposals": store._proposals, "assignments": store._assignments}
    return hashlib.sha256(json.dumps(s, sort_keys=True, default=str).encode()).hexdigest()


def run(out: Path, slice_dir: Path = DEV_SLICE) -> dict:
    if out.exists():
        raise DevBoundaryError(f"{out} exists; each DEV run writes a fresh directory")
    man = json.loads((slice_dir / "MANIFEST.json").read_text(encoding="utf-8"))
    fx, cache = slice_dir / "fixture.csv", slice_dir / "cache.jsonl"
    if (sha256(fx), sha256(cache)) != (man["fixture_sha256"], man["cache_sha256"]):
        raise DevBoundaryError("DEV slice does not match its MANIFEST hashes")
    recs, _ = load_cache(cache)
    coders = {sme_standin.STANDIN.id}

    t1 = shortlist.run(fx, cache, out / "task1")
    store1 = SandboxStore(out / "task1" / "store_task1", authorized_coders=coders)
    store1.load_listing(shortlist.parent_listing(fx, cache))
    proposed = shortlist.propose(store1, t1)
    d1 = sme_standin.decide_task1(store1, t1, recs)
    write_json(out / "sme" / "task1_decisions.json", {"rules": sme_standin.RULES, "decisions": d1})

    t2 = subcategory.run(store1, t1["fy"], cache, out / "task2", coders)
    d2 = sme_standin.decide_task2(t2["store"], t1["fy"])
    write_json(out / "sme" / "task2_decisions.json", {"rules": sme_standin.RULES, "decisions": d2})
    roll = t2["store"].rollup("NITRD", t1["fy"])

    rep = drift.report(store1, t1["fy"], FINGERPRINT, cache, out / "task3")
    files = sorted(p for p in out.rglob("*") if p.is_file() and p.name != "events.jsonl" and p.name != "PIPELINE.json")
    summary = {
        "label": DEV_LABEL, "workflow_id": WORKFLOW_ID, "slice_id": man["slice_id"], "fiscal_year": t1["fy"],
        "task1": {k: t1["meta"][k] for k in ("universe", "candidates", "not_shortlisted", "no_public_text")}
                 | {"proposed_into_store": len(proposed["proposed"]), "store_rejected": len(proposed["rejected"])},
        "sme_task1": {k: sum(1 for d in d1 if d["decision"] == k) for k in ("approve", "reject", "add")},
        "task2": {"confirmed_input": t2["meta"]["confirmed"], **t2["meta"]["loaded"],
                  "approved": len(d2), "by_pca_dollars": roll["by_pca"], "aw_unresolved": roll["aw_unresolved"],
                  "parent_total": roll["parent_total"], "listing_total": roll["listing_total"]},
        "task3": rep["counts"] | {"over_capture_terms": len(rep["over_capture_terms"]),
                                  "candidate_concepts": len(rep["under_capture_candidate_concepts"]),
                                  "fingerprint_unchanged": rep["fingerprint_sha256_before"] == rep["fingerprint_sha256_after"]},
        "store_state_sha256": {"task1": state_digest(store1), "task2": state_digest(t2["store"])},
        "files_sha256": {str(p.relative_to(out)): sha256(p) for p in files},
    }
    write_json(out / "PIPELINE.json", summary)
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--slice", type=Path, default=DEV_SLICE)
    a = ap.parse_args(argv)
    try:
        s = run(a.out, a.slice)
    except DevBoundaryError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 3
    print(json.dumps({k: s[k] for k in ("label", "task1", "sme_task1", "task2", "task3")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
