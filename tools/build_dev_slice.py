#!/usr/bin/env python3
"""Fetch the DEV slice for the NITRD workflow skeleton: a few hundred public RePORTER awards.

DEV / not scored. FY2023 (proposed build FY; not the score FY, not the contaminated FY2025).
Selection is fixed and label-free: for each administering IC, RePORTER records sorted by appl_id,
6 from the start and 6 from the middle of that IC's FY list. Only identity + text fields are
requested; no RCDC field (spending categories, terms, pref_terms) is requested or stored, and the
response is checked for that. Records of any core project in the 480 evaluation fixture are
dropped. The output is committed, so the skeleton itself runs offline.

Usage: python tools/build_dev_slice.py --out dev/fy2023_dev_slice   (network; run once)
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.inputs import EVALUATION_FIXTURE, load_project_refs  # noqa: E402
from workflow.common import DEV_LABEL, RESERVED_FYS, check_dev_refs  # noqa: E402

URL = "https://api.reporter.nih.gov/v2/projects/search"
FY = 2023
ICS = ("NCI", "NEI", "NHLBI", "NHGRI", "NIA", "NIAAA", "NIAID", "NIAMS", "NIBIB", "NICHD", "NIDCD", "NIDCR",
       "NIDDK", "NIDA", "NIEHS", "NIGMS", "NIMH", "NIMHD", "NINDS", "NINR", "NLM", "FIC", "NCATS", "NCCIH", "OD")
PER_BLOCK = 6
FIELDS = ["ApplId", "SubprojectId", "ProjectNum", "CoreProjectNum", "FiscalYear", "ProjectTitle",
          "AbstractText", "PhrText", "AwardAmount"]
ALLOWED_KEYS = {"appl_id", "subproject_id", "project_num", "core_project_num", "fiscal_year", "project_title",
                "abstract_text", "phr_text", "award_amount"}
CORE_RE = re.compile(r"^\d?([A-Z0-9]{3}[A-Z]{2}\d{6})")


def _post(criteria, offset, limit):
    body = {"criteria": criteria, "include_fields": FIELDS, "offset": offset, "limit": limit,
            "sort_field": "appl_id", "sort_order": "asc"}
    for attempt in range(4):
        try:
            r = requests.post(URL, json=body, timeout=120)
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            time.sleep(2 * (attempt + 1))
    raise SystemExit("RePORTER unavailable")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    assert FY not in RESERVED_FYS
    if a.out.exists():
        print(f"{a.out} exists; the DEV slice is built once and committed", file=sys.stderr)
        return 1
    eval_cores = {m.group(1) for r in load_project_refs(EVALUATION_FIXTURE)
                  if (m := CORE_RE.match(r.project_number))}
    recs, plan = {}, []
    for ic in ICS:
        crit = {"fiscal_years": [FY], "agencies": [ic]}
        n = _post(crit, 0, 1)["meta"]["total"]
        for off in sorted({0, min(n // 2, 14000)}):
            got = _post(crit, off, PER_BLOCK)["results"] if n else []
            plan.append({"ic": ic, "ic_total": n, "offset": off, "returned": len(got)})
            for r in got:
                extra = set(r) - ALLOWED_KEYS
                if extra:
                    raise SystemExit(f"unexpected RePORTER fields {sorted(extra)}; refusing")
                if r["fiscal_year"] != FY or (r.get("core_project_num") or "") in eval_cores:
                    continue
                recs[int(r["appl_id"])] = r
    a.out.mkdir(parents=True)
    fx, cache = a.out / "fixture.csv", a.out / "cache.jsonl"
    with fx.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Appl ID", "FY", "Project Number", "SubProj"])
        for i in sorted(recs):
            r = recs[i]
            w.writerow([i, FY, r["project_num"], r.get("subproject_id") or ""])
    lines = []
    for i in sorted(recs):
        r = recs[i]
        rec = {"abstract": r.get("abstract_text"), "appl_id": i, "award_amount": r.get("award_amount"),
               "fiscal_year": FY, "project_num": r["project_num"], "public_health_relevance": r.get("phr_text"),
               "specific_aims": None, "status": "found", "title": r.get("project_title")}
        lines.append(json.dumps(rec, sort_keys=True, separators=(",", ":")))
    cache.write_text("\n".join(lines) + "\n", encoding="utf-8")
    check_dev_refs(load_project_refs(fx))
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()  # noqa: E731
    manifest = {
        "label": DEV_LABEL, "slice_id": "dev-slice-fy2023-v1", "fiscal_year": FY,
        "source": "NIH RePORTER API v2 projects/search (public)", "fields_requested": FIELDS,
        "rcdc_fields_requested": False,
        "selection": f"per administering IC, sorted by appl_id: {PER_BLOCK} records at offset 0 and at the IC midpoint",
        "excluded": "records of any core project in the 480 evaluation fixture",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "plan": plan, "n_records": len(recs),
        "fixture_sha256": sha(fx), "cache_sha256": sha(cache),
    }
    (a.out / "MANIFEST.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("n_records", "fixture_sha256", "cache_sha256")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
