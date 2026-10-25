"""Build the Task 1 build universe from the public RePORTER API (identity + category-329 flag).

UNIVERSE_ID = task1-build-universe-v1-2026-10-25. DEV / not scored.

* Build FYs (FY2021-2023): every NIH record, identity fields only, plus a 0/1 flag for public
  spending category 329 (NITRD). The flag is the only category information requested.
* Score FY (FY2024): IDENTITY ONLY. No spending-category criterion is ever sent for FY2024 or FY2025;
  the FY2024 labels stay unread until the seal is opened. FY2025 is refused outright.
* Fields requested: ApplId, CoreProjectNum, FiscalYear, SubprojectId, AgencyIcAdmin. No text.
* Completeness: pulled records must equal RePORTER's NIH total for the FY, and every 329 record must
  be in the pulled universe, or the build fails.
* Built once and committed: refuses if the output directory already exists.

Usage: python tools/build_universe.py --out build/universe
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import hashlib
import io
import json
import sys
import time
from pathlib import Path

UNIVERSE_ID = "task1-build-universe-v1-2026-10-25"
URL = "https://api.reporter.nih.gov/v2/projects/search"
CAT_NITRD = 329
BUILD_FYS = (2021, 2022, 2023)
IDENTITY_ONLY_FYS = (2024,)          # score FY: identity only, labels never requested
REFUSED_FYS = (2025,)                # contaminated
FIELDS = ("ApplId", "CoreProjectNum", "FiscalYear", "SubprojectId", "AgencyIcAdmin")
PARTITION = ("NCI", "NEI", "NHLBI", "NHGRI", "NIA", "NIAAA", "NIAID", "NIAMS", "NIBIB", "NICHD", "NIDA",
             "NIDCD", "NIDCR", "NIDDK", "NIEHS", "NIGMS", "NIMH", "NIMHD", "NINDS", "NINR", "NLM", "NCCIH",
             "NCATS", "FIC", "OD", "CLC", "CC", "CIT")
PAGE, MAX_WINDOW = 500, 14999
LABEL = "DEV / not scored. Task 1 build universe (identity + public category-329 flag for build FYs only)."


class UniverseBoundaryError(RuntimeError):
    pass


def label_allowed(fy: int) -> bool:
    """Only build FYs may have their category-329 flag requested."""
    if fy in REFUSED_FYS:
        raise UniverseBoundaryError(f"FY{fy} is contaminated; refused")
    if fy in IDENTITY_ONLY_FYS:
        return False
    if fy in BUILD_FYS:
        return True
    raise UniverseBoundaryError(f"FY{fy} is not a declared build or score FY")


class Client:
    def __init__(self, session=None, pause=0.35):
        if session is None:
            import requests
            session = requests.Session()
        self.s, self.pause, self.calls = session, pause, 0

    def post(self, crit, offset=0, limit=PAGE):
        if "spending_categories" in crit and not label_allowed(crit["fiscal_years"][0]):
            raise UniverseBoundaryError("category criterion refused for an identity-only FY")
        body = {"criteria": crit, "include_fields": list(FIELDS), "offset": offset, "limit": limit,
                "sort_field": "appl_id", "sort_order": "asc"}
        for a in range(6):
            try:
                r = self.s.post(URL, json=body, timeout=90)
                self.calls += 1
                if r.status_code == 200:
                    return r.json()
            except Exception:  # noqa: BLE001 - network retry
                pass
            time.sleep(3 * (a + 1))
        raise RuntimeError(f"RePORTER request failed: {crit} @ {offset}")

    def total(self, crit):
        return self.post(crit, 0, 1)["meta"]["total"]

    def pull(self, crit):
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


def pull_fy(client: Client, fy: int) -> tuple[dict[int, dict], set[int] | None, int]:
    with_label = label_allowed(fy)
    n_all = client.total({"fiscal_years": [fy], "agencies": ["NIH"]})
    recs: dict[int, dict] = {}
    for ic in PARTITION:
        crit = {"fiscal_years": [fy], "agencies": [ic]}
        n = client.total(crit)
        if not n:
            continue
        if n <= MAX_WINDOW:
            recs.update(client.pull(crit))
        else:
            for t in "123456789":
                c2 = {**crit, "award_types": [t]}
                if client.total(c2):
                    recs.update(client.pull(c2))
    if len(recs) != n_all:
        raise RuntimeError(f"FY{fy}: universe {len(recs)} != NIH total {n_all}")
    pos = None
    if with_label:
        pos = set(client.pull({"fiscal_years": [fy], "agencies": ["NIH"],
                               "spending_categories": {"values": [CAT_NITRD], "match_all": False}}))
        if pos - set(recs):
            raise RuntimeError(f"FY{fy}: {len(pos - set(recs))} category-329 records outside the universe")
    return recs, pos, n_all


def render(fy: int, recs: dict[int, dict], pos: set[int] | None) -> str:
    cols = ["appl_id", "fy", "core_project_num", "subproject_id", "ic_admin"] + (["cat329"] if pos is not None else [])
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for a in sorted(recs):
        x = recs[a]
        if int(x["fiscal_year"]) != fy or not x.get("core_project_num"):
            raise RuntimeError(f"FY{fy}: bad identity for appl_id {a}")
        row = [a, fy, x["core_project_num"], x.get("subproject_id") or "",
               ((x.get("agency_ic_admin") or {}).get("abbreviation") or "")]
        w.writerow(row + ([int(a in pos)] if pos is not None else []))
    return buf.getvalue()


def summarise(fy, text, n_all, with_label):
    rows = list(csv.DictReader(io.StringIO(text)))
    cores = {r["core_project_num"] for r in rows}
    s = {"fy": fy, "records": len(rows), "nih_total_at_pull": n_all, "core_projects": len(cores),
         "subproject_records": sum(bool(r["subproject_id"]) for r in rows),
         "per_ic_admin": dict(sorted(collections.Counter(r["ic_admin"] or "(none)" for r in rows).items())),
         "labels": "category-329 flag" if with_label else "NONE (identity only; labels not requested)"}
    if with_label:
        pos_cores = {r["core_project_num"] for r in rows if r["cat329"] == "1"}
        s.update({"cat329_records": sum(r["cat329"] == "1" for r in rows), "cat329_core_projects_any": len(pos_cores)})
    return s


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.out.exists():
        print(f"refused: {a.out} exists (built once and committed)", file=sys.stderr)
        return 2
    client, files, started = Client(), {}, dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for fy in BUILD_FYS + IDENTITY_ONLY_FYS:
        recs, pos, n_all = pull_fy(client, fy)
        name = f"fy{fy}.csv" if pos is not None else f"fy{fy}_identity.csv"
        files[name] = (render(fy, recs, pos), (fy, n_all, pos is not None))
        print(f"FY{fy}: {len(recs)} records, labels={'cat329' if pos is not None else 'none'}", flush=True)
    a.out.mkdir(parents=True)
    manifest = {"universe_id": UNIVERSE_ID, "label": LABEL, "source": URL, "fields_requested": list(FIELDS),
                "text_requested": False, "category_requested": {str(f): ("329 only" if label_allowed(f) else "none")
                                                               for f in BUILD_FYS + IDENTITY_ONLY_FYS},
                "retrieved_utc_start": started,
                "retrieved_utc_end": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "api_calls": client.calls, "core_rule": "RePORTER core_project_num as returned",
                "files": {}}
    for name, (text, (fy, n_all, with_label)) in files.items():
        (a.out / name).write_text(text, encoding="utf-8")
        manifest["files"][name] = {"sha256": hashlib.sha256(text.encode()).hexdigest(),
                                   **summarise(fy, text, n_all, with_label)}
    (a.out / "MANIFEST.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: {x: v[x] for x in ("records", "core_projects", "sha256")} for k, v in manifest["files"].items()},
                     indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
