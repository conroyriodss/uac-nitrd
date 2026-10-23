#!/usr/bin/env python3
"""UAC NITRD build sweep: seal guard + proposal validation. Never reads the held-out key.

Checks, in order; any failure fails the sweep:
  S1 tool integrity  seal_guard.py and score_heldout.py match their committed SHA-256
                     (so validation runs the committed match rule, not an edited one)
  S2 seal guard      seal_guard.py over the whole tree must report CLEAN
  S3 validation      score_heldout.py --validate-only on the proposals must pass
                     (unknown code, non-boolean flag, duplicate ID, AI without the flag)
  S4 coverage        proposal appl_ids == fixture Appl IDs exactly: one row for every
                     fixture project (an empty primary_pca is allowed) and no extras
  S5 format v2       proposal-format-v2-2026-10-23 (Advanced Wireless as sub-PCA of ACNS):
                     a sub_pca column is required, with values "" or "AW"; primary_pca is
                     never "AW"; sub_pca=AW requires primary_pca=ACNS. This is stricter than the
                     committed scorer, which still tolerates "AW" and scores it as a miss.
  S6 input boundary  engine/ must never use the fixture's suggestion columns. No engine file
                     may name a suggestion column; only engine/inputs.py may open the
                     fixture; and its ALLOWED_COLUMNS must be exactly the identity columns.
                     Runs in every mode.
  S7 output label    proposals/proposals.meta.json must carry the fixed assist-proposal
                     label, official_uac_method=false and suggestion_columns_read=false.

Modes:
  default   S1 + S2 + S6. If there is no proposals file yet, S3-S5 and S7 are NOT_RUN (normal
            during the build).
  --freeze  S1-S7 are all required; a missing proposals file is a FAIL. On a PASS, the record
            gives the proposals SHA-256 to tag and log BEFORE the reveal.
Exit: 0 = PASS, 1 = a check failed, 2 = configuration error (fails closed).

Usage: python build_sweep.py --tree <repo> --fixture <uac csv> [--proposals <csv>] [--freeze]
                             [--out sweep_record.json]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import ast
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RULE_ID = "entry2-match-rule-v1-2026-10-23"
FORMAT_ID = "proposal-format-v2-2026-10-23"
ENGINE_ALLOWED_COLUMNS = ("Appl ID", "FY", "Project Number", "SubProj")
SUGGESTION_RE = re.compile(r"suggestion[\s_\-]*\d", re.IGNORECASE)
FIXTURE_RE = re.compile(r"UAC_Uncoded|fixtures[/\\]", re.IGNORECASE)
OUTPUT_LABEL = ("ASSIST PROPOSAL FOR SME REVIEW. Not a reproduction of the official UAC method "
                "(no UAC fingerprints exist). The 'most specific PCA' rule is NITRD's published "
                "guidance applied to project text, not a claim of official correctness.")
COMMITTED = {
    # 2026-10-23 docstring-only rename (AST-identical to 9678a1bb... / bde79169...); see seal log.
    "seal_guard.py": "8dfb241754afbac0aa85a111828c1b268cc75e61e9bea74b032a3964a3ace401",
    "score_heldout.py": "5b9860fa882e71d5790e1959b5fcc37cdb29ab723022c2a14a3643c1eb6636d1",
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

    # S6 input boundary (every mode)
    checks["S6_input_boundary"] = _input_boundary(a.tree, a.freeze)

    # S3 / S4 / S5 / S7 proposals
    if not a.proposals or not a.proposals.is_file():
        st = "FAIL" if a.freeze else "NOT_RUN"
        why = "no proposals file" + (" (required with --freeze)" if a.freeze else " yet")
        for k in ("S3_proposal_validation", "S4_coverage", "S5_format_v2", "S7_output_label"):
            checks[k] = {"status": st, "detail": why}
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
    checks["S5_format_v2"] = _format_v2(a.proposals)
    checks["S7_output_label"] = _output_label(a.proposals.with_name("proposals.meta.json"))
    checks["proposals_sha256"] = _sha(a.proposals)
    return _finish(a, checks)


def _input_boundary(tree: Path, freeze: bool) -> dict:
    eng = tree / "engine"
    if not eng.is_dir():
        return {"status": "FAIL" if freeze else "NOT_RUN", "detail": "no engine/ directory"}
    hits = []
    for p in sorted(eng.rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        text = p.read_bytes().decode("utf-8", errors="replace")
        rel = p.relative_to(tree).as_posix()
        if SUGGESTION_RE.search(text):
            hits.append(f"{rel}: names a suggestion column")
        if rel != "engine/inputs.py" and FIXTURE_RE.search(text):
            hits.append(f"{rel}: references the fixture (only engine/inputs.py may)")
    inp = eng / "inputs.py"
    allowed = None
    if inp.is_file():
        for node in ast.walk(ast.parse(inp.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "ALLOWED_COLUMNS" for t in node.targets):
                allowed = ast.literal_eval(node.value)
    if tuple(allowed or ()) != ENGINE_ALLOWED_COLUMNS:
        hits.append(f"engine/inputs.py ALLOWED_COLUMNS={allowed!r}, expected {ENGINE_ALLOWED_COLUMNS!r}")
    return {"status": "FAIL" if hits else "PASS", "violations": hits[:20]}


def _output_label(meta: Path) -> dict:
    if not meta.is_file():
        return {"status": "FAIL", "detail": f"missing {meta.name}"}
    try:
        m = json.loads(meta.read_text(encoding="utf-8"))
    except ValueError as e:
        return {"status": "FAIL", "detail": f"{meta.name} not JSON: {e}"}
    bad = [k for k, want in (("label", OUTPUT_LABEL), ("official_uac_method", False),
                             ("suggestion_columns_read", False)) if m.get(k) != want]
    return {"status": "FAIL" if bad else "PASS", "wrong_or_missing": bad}


def _format_v2(path: Path) -> dict:
    with path.open(newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        if "sub_pca" not in (r.fieldnames or []):
            return {"status": "FAIL", "format_id": FORMAT_ID, "detail": "missing sub_pca column"}
        bad = []
        for row in r:
            pca, sub = (row.get("primary_pca") or "").strip(), (row.get("sub_pca") or "").strip()
            why = ("primary_pca=AW (use primary_pca=ACNS, sub_pca=AW)" if pca == "AW"
                   else f"sub_pca={sub!r} not in ('', 'AW')" if sub not in ("", "AW")
                   else f"sub_pca=AW with primary_pca={pca!r} (must be ACNS)" if sub == "AW" and pca != "ACNS"
                   else None)
            if why:
                bad.append({"appl_id": (row.get("appl_id") or "").strip(), "why": why})
    return {"status": "FAIL" if bad else "PASS", "format_id": FORMAT_ID,
            "violations": len(bad), "first": bad[:10]}


def _finish(a, checks) -> int:
    statuses = [c["status"] for c in checks.values() if isinstance(c, dict) and "status" in c]
    verdict = "FAIL" if "FAIL" in statuses else "PASS"
    rec = {"at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "mode": "freeze" if a.freeze else "build",
           "rule_id": RULE_ID, "format_id": FORMAT_ID, "verdict": verdict, "checks": checks,
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
