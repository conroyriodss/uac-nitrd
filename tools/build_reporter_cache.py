#!/usr/bin/env python3
"""Build, or verify, the public RePORTER text cache the engine replays offline.

The same rules apply to every project:
  * Which projects: every Appl ID returned by engine.inputs.load_project_refs, which exposes
    identity columns only. The builder never sees suggestion, Category or coder columns, and
    it never reads any RCDC export.
  * Which text: the same public fields for all projects, requested by name (include_fields)
    and filtered again on receipt. Title, abstract and public health relevance come back as
    RePORTER returns them, with no reformatting.
    Specific aims: the public RePORTER API exposes no aims field, so every record carries
    "specific_aims": null. Where an abstract contains the aims, they come in with it.
  * Never cached: RePORTER's derived and coder-side fields (terms, pref_terms,
    spending_categories, spending_categories_desc, and anything else not listed below).
    spending_categories in particular can carry RCDC category assignments.
  * The same code path for every project: there is no per-project branching on anything
    except the API response itself.

Output (deterministic; only fetched_at_utc in the manifest varies between fetches):
  <out>/reporter_text.v1.jsonl   one canonical JSON record per Appl ID, sorted by appl_id
  <out>/MANIFEST.json            per-project record SHA-256, the request spec, and counts

Usage:
  build:  python tools/build_reporter_cache.py --fixture <csv> --out cache/reporter
  verify: python tools/build_reporter_cache.py --fixture <csv> --out cache/reporter --verify
          (re-fetches from RePORTER and compares every record hash with the committed manifest)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.inputs import load_project_refs  # noqa: E402  (identity columns only)

CACHE_VERSION = "reporter-text-v1"
API_URL = "https://api.reporter.nih.gov/v2/projects/search"
# Requested from RePORTER. Identity fields are used to check each record; text fields are cached.
INCLUDE_FIELDS = ("ApplId", "ProjectNum", "FiscalYear", "ProjectTitle", "AbstractText", "PhrText", "AwardAmount")
# Response key -> cache key. Any key not listed is dropped on receipt.
KEEP = {"appl_id": "appl_id", "project_num": "project_num", "fiscal_year": "fiscal_year",
        "project_title": "title", "abstract_text": "abstract", "phr_text": "public_health_relevance",
         "award_amount": "award_amount"}
TEXT_KEYS = ("title", "abstract", "public_health_relevance", "specific_aims")
PAGE = 500


def canonical(rec: dict) -> bytes:
    return json.dumps(rec, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def http_fetch(appl_ids: list[int], offset: int) -> dict:
    import requests  # tools/ only; engine/ has no network access (S6)
    body = {"criteria": {"appl_ids": appl_ids}, "include_fields": list(INCLUDE_FIELDS),
            "offset": offset, "limit": PAGE, "sort_field": "appl_id", "sort_order": "asc"}
    for attempt in range(4):
        r = requests.post(API_URL, json=body, timeout=120)
        if r.status_code == 200:
            return r.json()
        time.sleep(2 ** attempt)
    r.raise_for_status()
    raise RuntimeError("unreachable")


def fetch_all(appl_ids: list[int], fetch: Callable[[list[int], int], dict]) -> dict[int, dict]:
    got: dict[int, dict] = {}
    for i in range(0, len(appl_ids), PAGE):
        batch, offset = appl_ids[i:i + PAGE], 0
        while True:
            d = fetch(batch, offset)
            res = d.get("results") or []
            for x in res:
                got.setdefault(int(x["appl_id"]), x)  # first record wins; duplicates are counted below
            offset += len(res)
            if not res or offset >= int(d.get("meta", {}).get("total", 0)):
                break
    return got


def make_record(appl_id: int, raw: dict | None) -> dict:
    """One rule for all projects: keep the listed public fields, drop everything else."""
    rec = {"appl_id": appl_id, "status": "found" if raw else "not_found", "project_num": None,
           "fiscal_year": None, "title": None, "abstract": None, "public_health_relevance": None,
           "specific_aims": None, "award_amount": None}
    if raw:
        for src, dst in KEEP.items():
            if src in raw and dst != "appl_id":
                rec[dst] = raw[src]
    return rec


def build(appl_ids: Iterable[int], fetch: Callable[[list[int], int], dict]) -> tuple[bytes, dict]:
    ids = sorted(set(appl_ids))
    raw = fetch_all(ids, fetch)
    lines, per = [], {}
    for a in ids:
        b = canonical(make_record(a, raw.get(a)))
        lines.append(b)
        per[str(a)] = hashlib.sha256(b).hexdigest()
    body = b"\n".join(lines) + b"\n"
    recs = [json.loads(x) for x in lines]
    manifest = {
        "cache_version": CACHE_VERSION,
        "source": {"api": API_URL, "include_fields": list(INCLUDE_FIELDS),
                   "kept_fields": sorted(set(KEEP.values()) | {"specific_aims", "status"}),
                   "specific_aims": "not exposed by the public RePORTER API; null for every project"},
        "selection": "all Appl IDs from engine.inputs.load_project_refs (identity columns only); uniform fields",
        "counts": {"projects": len(ids), "found": sum(r["status"] == "found" for r in recs),
                   "not_found": sum(r["status"] == "not_found" for r in recs),
                   **{f"with_{k}": sum(bool(r[k]) for r in recs) for k in TEXT_KEYS}},
        "jsonl_sha256": hashlib.sha256(body).hexdigest(),
        "record_sha256": per,
    }
    return body, manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args(argv)
    ids = [r.appl_id for r in load_project_refs(a.fixture)]
    body, manifest = build(ids, http_fetch)
    if a.verify:
        old = json.loads((a.out / "MANIFEST.json").read_text(encoding="utf-8"))
        diff = sorted(k for k in set(old["record_sha256"]) | set(manifest["record_sha256"])
                      if old["record_sha256"].get(k) != manifest["record_sha256"].get(k))
        same_file = (a.out / "reporter_text.v1.jsonl").read_bytes() == body
        print(json.dumps({"verified_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                          "projects": len(manifest["record_sha256"]), "records_differing": len(diff),
                          "differing_first": diff[:20], "jsonl_identical": same_file}, indent=2))
        return 0 if not diff and same_file else 1
    a.out.mkdir(parents=True, exist_ok=True)
    manifest["fetched_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (a.out / "reporter_text.v1.jsonl").write_bytes(body)
    (a.out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{manifest['counts']} jsonl_sha256={manifest['jsonl_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
