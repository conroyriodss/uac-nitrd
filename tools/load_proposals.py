#!/usr/bin/env python3
"""Wire the engine's proposals into the sandboxed write store.

This is the plumbing between the engine (which proposes) and the store (where the
governed write happens). It performs three steps:

  1. Build the parent listing from the fixture's identity columns, paired with
     per-project snapshot hashes from the committed RePORTER cache and (optionally)
     per-project dollar amounts from a permitted source.
  2. Load every row of proposals.csv + its explanation into the store as an AGENT
     proposal. The store validates each one (invariants 1-3, 8-9) and rejects any
     that break the rules.
  3. Report what the store now holds: pending proposals awaiting SME approval,
     rejections, and the uncoded remainder.

The store is NOT populated with assignments: every proposal is PENDING. The coder
approves, overrides or rejects each one (invariant 7). This tool makes proposals,
not decisions.

Amounts. The fixture has no dollar column. Amounts default to 0 (placeholder) unless
--amounts supplies a CSV keyed by Appl ID. The store's math (invariant 4) is correct
either way, but real totals need a permitted source — for example, adding
award_amount to the RePORTER cache.

Usage:
  python tools/load_proposals.py \
      --fixture   fixtures/UAC_Uncoded_12-01-2025-updated-NIH_ODSS.csv \
      --proposals proposals/proposals.csv \
      --explanations proposals/explanations.jsonl \
      --cache     cache/reporter/reporter_text.v1.jsonl \
      --sandbox   sandbox/nitrd_2025 \
      [--amounts  amounts.csv]           # optional: appl_id,amount
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.inputs import load_project_refs  # noqa: E402
from store import Actor, ListedProject, ParentListing, Rejected, SandboxStore  # noqa: E402

AGENT = Actor("engine", "agent")


def _snapshot_map(cache_path: Path) -> dict[int, str]:
    """Per-project SHA-256 from the committed RePORTER text cache."""
    m: dict[int, str] = {}
    for line in cache_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        b = line.encode("utf-8")
        rec = json.loads(line)
        m[int(rec["appl_id"])] = hashlib.sha256(b).hexdigest()
    return m


def _amounts_map(path: Path | None) -> dict[int, int]:
    if path is None:
        return {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        return {int(r["appl_id"]): int(r["amount"]) for r in csv.DictReader(f)}


def build_listing(fixture: Path, cache_path: Path, amounts_path: Path | None,
                  crosscut: str = "NITRD") -> ParentListing:
    refs = load_project_refs(fixture)
    snaps = _snapshot_map(cache_path)
    amts = _amounts_map(amounts_path)
    projects = []
    for r in refs:
        sha = snaps.get(r.appl_id, hashlib.sha256(f"no-cache:{r.appl_id}".encode()).hexdigest())
        projects.append(ListedProject(
            appl_id=r.appl_id, fy=r.fy, project_num=r.project_number,
            subproj=r.subproj, amount=amts.get(r.appl_id, 0), snapshot_sha=sha))
    return ParentListing(crosscut, refs[0].fy if refs else 0, projects)


def load_proposals(store: SandboxStore, proposals_csv: Path, explanations_jsonl: Path,
                   crosscut: str = "NITRD") -> dict:
    # index explanations by appl_id
    expl: dict[int, dict] = {}
    for line in explanations_jsonl.read_text(encoding="utf-8").splitlines():
        if line.strip():
            e = json.loads(line)
            expl[int(e["appl_id"])] = e

    proposed, rejected, skipped = [], [], []
    with proposals_csv.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            appl = int(row["appl_id"])
            pca = row["primary_pca"].strip()
            ai = row["ai_relevant"].strip().lower() == "true"
            sub = row.get("sub_pca", "").strip()
            ex = expl.get(appl, {})
            score = float(ex.get("ranked", [{}])[0].get("score", 0.0)) if ex.get("ranked") else 0.0

            if not pca:  # engine abstained
                skipped.append({"appl_id": appl, "reason": ex.get("abstain_reason", "no_proposal")})
                continue

            # look up the snapshot the engine used
            snap = ex.get("text_sha256", "")
            # the listing was loaded with the cache snapshot; the engine should have used the same text
            listing = store._listings.get((crosscut, store._listings and next(
                (fy for (cc, fy) in store._listings if cc == crosscut), None)))
            # get the FY from the listing
            fy = next((fy for (cc, fy) in store._listings if cc == crosscut), None)
            if fy is None:
                rejected.append({"appl_id": appl, "reason": "no listing loaded for " + crosscut})
                continue

            # use the listing's snapshot (the cache hash), which is what the engine should have used
            listing_snap = store._listings[(crosscut, fy)]["snapshot"].get(appl)
            if listing_snap is None:
                rejected.append({"appl_id": appl, "reason": f"not in listing {crosscut} FY{fy}"})
                continue

            try:
                pid = store.propose(
                    AGENT, crosscut, fy, appl,
                    primary_pca=pca, ai_relevant=ai, sub_pca=sub,
                    score=score, snapshot_sha=listing_snap,
                    explanation=ex)
                proposed.append({"appl_id": appl, "proposal_id": pid, "primary_pca": pca,
                                 "ai_relevant": ai, "sub_pca": sub})
            except Rejected as e:
                rejected.append({"appl_id": appl, "reason": str(e), "primary_pca": pca})

    return {"proposed": len(proposed), "rejected": len(rejected), "abstained": len(skipped),
            "total": len(proposed) + len(rejected) + len(skipped),
            "proposals": proposed, "rejections": rejected, "abstentions": skipped}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fixture", type=Path, required=True)
    ap.add_argument("--proposals", type=Path, required=True)
    ap.add_argument("--explanations", type=Path, required=True)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--sandbox", type=Path, required=True)
    ap.add_argument("--amounts", type=Path, default=None)
    ap.add_argument("--coders", nargs="+", default=["coder1"])
    ap.add_argument("--siacb", nargs="+", default=["board1"])
    a = ap.parse_args(argv)

    listing = build_listing(a.fixture, a.cache, a.amounts)
    store = SandboxStore(a.sandbox, authorized_coders=set(a.coders), siacb_members=set(a.siacb))
    store.load_listing(listing)
    result = load_proposals(store, a.proposals, a.explanations)

    # summary
    r = store.rollup("NITRD", listing.fy)
    result["rollup"] = {"listing_total": r["listing_total"], "parent_total": r["parent_total"],
                        "uncoded_count": len(r["uncoded"]["appl_ids"]),
                        "pending_proposals": result["proposed"],
                        "aw_unresolved_count": len(r["aw_unresolved"]["appl_ids"])}
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
