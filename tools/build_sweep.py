#!/usr/bin/env python3
"""Entry 2 build sweep: seal guard + proposal validation. Never reads the held-out key.

Checks, in order; any failure fails the sweep:
  S1 tool integrity  seal_guard.py and score_heldout.py match their committed SHA-256
                     (so validation runs the committed match rule, not an edited one)
  S2 seal guard      seal_guard.py over the whole tree must report CLEAN
  S3 validation      score_heldout.py --validate-only on the proposals must pass
                     (unknown code, non-boolean flag, duplicate ID, AI without the flag)
  S4 coverage        proposal appl_ids == fixture Appl IDs exactly: one row for every
                     fixture project (an empty primary_pca is allowed) and no extras

Modes:
  default   S1 + S2. If there is no proposals file yet, S3/S4 are NOT_RUN (normal during the build).
  --freeze  S1-S4 are all required; a missing proposals file is a FAIL. On a PASS, the record
            gives the proposals SHA-256 to tag and log BEFORE the reveal.
Exit: 0 = PASS, 1 = a check failed, 2 = configuration error (fails closed).

Usage: python build_sweep.py --tree <repo> --fixture <uac csv> [--proposals <csv>] [--freeze]
                             [--out sweep_record.json]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RULE_ID = "entry2-match-rule-v1-2026-10-23"
COMMITTED = {
    "seal_guard.py": "9678a1bb6eb6c1ae141b580c02bb459b7a550ea8efad832f98579a06764e51ec",
    "score_heldout.py": "bde791698f0e610da59bc514d507a00e1baedcadc8375f7b0edab4dc13cb0a69",
}
HERE = Path(__file__).resolve().parent


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _cfg(msg: str):
    print(f"build_sweep CONFIG ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def _ids(path: Path, col: str) -> list[str]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        if col not in (r.fieldnames or []):
            _cfg(f"{path.name} has no '{col}' column")
        return [(row[col] or "").strip() for row in r]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", type=Path, required=True)
    ap.add_argument("--fixture", type=Path, required=True)
    ap.add_argument("--proposals", type=Path)
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    if not a.tree.is_dir():
        _cfg(f"tree not found: {a.tree}")
    if not a.fixture.is_file():
        _cfg(f"fixture not found: {a.fixture}")

    checks: dict[str, dict] = {}

    # S1 tool integrity
    s1 = {}
    for name, want in COMMITTED.items():
        p = HERE / name
        got = _sha(p) if p.is_file() else None
        s1[name] = {"sha256": got, "ok": got == want}
    checks["S1_tool_integrity"] = {"status": "PASS" if all(v["ok"] for v in s1.values()) else "FAIL", "files": s1}
    if checks["S1_tool_integrity"]["status"] == "FAIL":
        return _finish(a, checks)  # don't run tools whose code isn't the committed code

    # S2 seal guard
    g = subprocess.run([sys.executable, str(HERE / "seal_guard.py"), "--tree", str(a.tree),
                        "--fixture", str(a.fixture)], capture_output=True, text=True)
    checks["S2_seal_guard"] = {"status": "PASS" if g.returncode == 0 else "FAIL", "exit": g.returncode,
                               "summary": (g.stdout.strip().splitlines() or [g.stderr.strip()])[-1]}

    # S3 / S4 proposals
    if not a.proposals or not a.proposals.is_file():
        st = "FAIL" if a.freeze else "NOT_RUN"
        why = "no proposals file" + (" (required with --freeze)" if a.freeze else " yet")
        checks["S3_proposal_validation"] = {"status": st, "detail": why}
        checks["S4_coverage"] = {"status": st, "detail": why}
        return _finish(a, checks)

    v = subprocess.run([sys.executable, str(HERE / "score_heldout.py"), "--proposals", str(a.proposals),
                        "--validate-only"], capture_output=True, text=True)
    checks["S3_proposal_validation"] = {"status": "PASS" if v.returncode == 0 else "FAIL", "exit": v.returncode,
                                        "rule_id": RULE_ID,
                                        "detail": v.stdout.strip() if v.returncode == 0
                                        else (v.stderr.strip().splitlines() or [""])[-1]}

    fx = [x for x in _ids(a.fixture, "Appl ID") if x]
    pr = [x for x in _ids(a.proposals, "appl_id") if x]
    fx_set, pr_set = set(fx), set(pr)
    missing, extra = sorted(fx_set - pr_set), sorted(pr_set - fx_set)
    checks["S4_coverage"] = {
        "status": "PASS" if not missing and not extra and len(pr) == len(pr_set) else "FAIL",
        "fixture_projects": len(fx_set), "proposal_rows": len(pr), "distinct": len(pr_set),
        "missing_count": len(missing), "missing_first": missing[:10],
        "extra_count": len(extra), "extra_first": extra[:10],
    }
    checks["proposals_sha256"] = _sha(a.proposals)
    return _finish(a, checks)


def _finish(a, checks) -> int:
    statuses = [c["status"] for c in checks.values() if isinstance(c, dict) and "status" in c]
    verdict = "FAIL" if "FAIL" in statuses else "PASS"
    rec = {"at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "mode": "freeze" if a.freeze else "build",
           "rule_id": RULE_ID, "verdict": verdict, "checks": checks,
           "note": "The sweep never reads the held-out key."}
    if a.out:
        a.out.write_text(json.dumps(rec, indent=2))
    for k, c in checks.items():
        if isinstance(c, dict):
            print(f"{k}: {c['status']}")
    if verdict == "PASS" and a.freeze:
        print(f"FREEZE OK: tag and log proposals_sha256={checks['proposals_sha256']} BEFORE the reveal")
    print(f"build_sweep {rec['mode']}: {verdict}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
