"""Fetch one fiscal year of NIH award identity + text from RePORTER, under the Task 1 read guard.

FETCH_ID = task1-text-fetch-v1. Runs with workflow/build_guard.py installed:

* FY2019-2021 (guard mode "build"): identity + title/abstract/PHR. FY2021 only also requests
  SpendingCategories, reduced on receipt to two booleans per award (has_any_category, cat329); the
  category list itself is never written.
* FY2026 (guard mode "forecast"): identity + text only. No label field or criterion is ever sent.
* Every request body passes Guard.check_reporter_body before it is sent and is recorded (sha256 +
  record count) in the fetch's READ_MANIFEST.
* Completeness: pulled records must equal RePORTER's NIH total for the FY, or the fetch fails.
* Write-once: refuses if the output directory exists.

Usage: python tools/fetch_task1_text.py --fy 2021 [--out DIR]   (default DIR: $SEED_ROOT/fy<FY>)
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow import build_guard as bg  # noqa: E402

FETCH_ID = "task1-text-fetch-v1"
URL = "https://api.reporter.nih.gov/v2/projects/search"
CAT_NITRD = 329
PAGE, MAX_WINDOW = 500, 14999
ID_FIELDS = ("ApplId", "CoreProjectNum", "FiscalYear", "SubprojectId", "AgencyIcAdmin", "ActivityCode")
TEXT_FIELDS = ("ProjectTitle", "AbstractText", "PhrText")
LABEL_FIELDS = ("SpendingCategories",)
PARTITION = ("NCI", "NEI", "NHLBI", "NHGRI", "NIA", "NIAAA", "NIAID", "NIAMS", "NIBIB", "NICHD", "NIDA",
             "NIDCD", "NIDCR", "NIDDK", "NIEHS", "NIGMS", "NIMH", "NIMHD", "NINDS", "NINR", "NLM", "NCCIH",
             "NCATS", "FIC", "OD", "CLC", "CC", "CIT")


def mode_for(fy: int) -> str:
    for mode, rules in bg.MODES.items():
        if fy in rules["fys"]:
            return mode
    raise bg.BuildGuardError(f"{FETCH_ID}: FY{fy} is neither a build FY (2019-2021) nor the forecast FY (2026)")


class Client:
    def __init__(self, guard: bg.Guard, fields: tuple, pause: float = 0.3):
        import requests
        self.g, self.fields, self.pause, self.s, self.calls = guard, fields, pause, requests.Session(), 0

    def post(self, crit: dict, offset: int = 0, limit: int = PAGE) -> dict:
        body = {"criteria": crit, "include_fields": list(self.fields), "offset": offset, "limit": limit,
                "sort_field": "appl_id", "sort_order": "asc"}
        self.g.check_reporter_body(body)
        for a in range(6):
            try:
                r = self.s.post(URL, json=body, timeout=120)
                self.calls += 1
                if r.status_code == 200:
                    out = r.json()
                    self.g.record_request(body, len(out.get("results") or ()))
                    return out
            except Exception:  # noqa: BLE001 - network retry
                pass
            time.sleep(3 * (a + 1))
        raise RuntimeError(f"RePORTER request failed: {crit} @ {offset}")

    def total(self, crit: dict) -> int:
        return self.post(crit, 0, 1)["meta"]["total"]

    def pull(self, crit: dict) -> dict[int, dict]:
        n, out, off = self.total(crit), {}, 0
        if n > MAX_WINDOW:
            raise RuntimeError(f"{crit}: {n} records exceeds the API window; partition further")
        while off < n:
            for x in self.post(crit, off)["results"]:
                out[int(x["appl_id"])] = x
            off += PAGE
            time.sleep(self.pause)
        if len(out) != n:
            raise RuntimeError(f"{crit}: pulled {len(out)} != total {n}")
        return out


def reduce_record(x: dict, fy: int, with_labels: bool) -> dict:
    rec = {
        "appl_id": int(x["appl_id"]),
        "fy": fy,
        "core_project_num": x.get("core_project_num") or "",
        "subproject_id": x.get("subproject_id") or "",
        "admin_ic": (x.get("agency_ic_admin") or {}).get("abbreviation") or "",
        "activity_code": x.get("activity_code") or "",
        "title": x.get("project_title") or "",
        "abstract": x.get("abstract_text") or "",
        "phr": x.get("phr_text") or "",
    }
    if with_labels:
        cats = x.get("spending_categories") or []
        rec["has_any_category"] = bool(cats)
        rec["cat329"] = any(int(c) == CAT_NITRD for c in cats)
    return rec


def fetch(fy: int, out_dir: Path) -> dict:
    mode = mode_for(fy)
    guard = bg.Guard(mode, roots=(out_dir,)).install()
    with_labels = fy in bg.MODES[mode]["label_fys"]
    fields = ID_FIELDS + TEXT_FIELDS + (LABEL_FIELDS if with_labels else ())
    c = Client(guard, fields)
    started = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    n_all = c.total({"fiscal_years": [fy], "agencies": ["NIH"]})
    recs: dict[int, dict] = {}
    for ic in PARTITION:
        crit = {"fiscal_years": [fy], "agencies": [ic]}
        n = c.total(crit)
        if not n:
            continue
        if n <= MAX_WINDOW:
            recs.update(c.pull(crit))
        else:
            for t in "123456789":
                c2 = {**crit, "award_types": [t]}
                if c.total(c2):
                    recs.update(c.pull(c2))
    if len(recs) != n_all:
        raise RuntimeError(f"FY{fy}: pulled {len(recs)} != NIH total {n_all}")
    rows = [reduce_record(recs[k], fy, with_labels) for k in sorted(recs)]
    raw = "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in rows).encode("utf-8")
    out_dir.mkdir(parents=True)
    data_path = out_dir / f"fy{fy}.jsonl.gz"
    data_path.write_bytes(gzip.compress(raw, mtime=0))
    summary = {
        "fetch_id": FETCH_ID, "fy": fy, "guard_mode": mode, "labels_requested": with_labels,
        "fields": list(fields), "pull_utc": {"start": started, "end": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")},
        "api_calls": c.calls, "records": len(rows), "nih_total": n_all,
        "file": data_path.name, "sha256_gz": hashlib.sha256(data_path.read_bytes()).hexdigest(),
        "sha256_jsonl": hashlib.sha256(raw).hexdigest(),
    }
    if with_labels:  # build FY only
        summary["label_counts"] = {"cat329": sum(r["cat329"] for r in rows),
                                   "uncategorized": sum(not r["has_any_category"] for r in rows)}
    (out_dir / "FETCH_SUMMARY.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    summary["read_manifest_sha256"] = guard.write_manifest(out_dir / "READ_MANIFEST.json")
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fy", type=int, required=True)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    out = a.out or bg.SEED_ROOT / f"fy{a.fy}"
    if out.exists():
        raise SystemExit(f"{out} exists; fetches are write-once")
    print(json.dumps(fetch(a.fy, out), indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
