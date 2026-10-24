#!/usr/bin/env python3
"""Fetch the INDEPENDENT FY2024 RePORTER corpus used to derive scope synonyms
(synonym-derivation-v2-2026-10-24; see docs/SYNONYM_DERIVATION.md).

Independence from the evaluation set:
  * fiscal_years = [CORPUS_FY] (2024), never 2025;
  * any record whose core project number matches a core project of the 480 fixture
    projects is DROPPED (continuations of the same project carry near-identical text);
  * any record whose appl_id is one of the 480 is DROPPED;
  * the fixture is read only through engine.inputs.load_project_refs (identity columns).
No RCDC field is requested or kept (no terms, pref_terms, spending_categories).
Text search covers project title + abstract only (never RePORTER 'terms').

Output (deterministic; fetched_at_utc in the manifest is the only varying field):
  corpus/fy2024_independent.v1.jsonl.gz   one record per appl_id, sorted, with the query ids that matched
  corpus/MANIFEST.json
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.inputs import load_project_refs  # noqa: E402  (identity columns only)

API_URL = "https://api.reporter.nih.gov/v2/projects/search"
DERIVATION_ID = "synonym-derivation-v2-2026-10-24"
CORPUS_FY = 2024
PAGE = 500
SEED_CAP = 500                               # first SEED_CAP matches per seed, by appl_id asc
BACKGROUND_OFFSETS = (0, 3000, 6000, 9000)   # 4 x 500 FY2024 records, by appl_id asc
INCLUDE_FIELDS = ("ApplId", "CoreProjectNum", "FiscalYear", "ProjectTitle", "AbstractText")
CORE_RE = re.compile(r"^\d?([A-Z0-9]{3}[A-Z]{2}\d{6})")


def core_of(project_num: str | None) -> str | None:
    m = CORE_RE.match((project_num or "").strip().upper())
    return m.group(1) if m else None


def _post(body: dict) -> dict:
    import requests  # tools/ only
    for attempt in range(5):
        r = requests.post(API_URL, json=body, timeout=120)
        if r.status_code == 200:
            time.sleep(1.0)  # RePORTER asks for <= 1 request/second
            return r.json()
        time.sleep(2 ** attempt)
    r.raise_for_status()
    raise RuntimeError("unreachable")


def _body(criteria: dict, offset: int) -> dict:
    return {"criteria": {"fiscal_years": [CORPUS_FY], **criteria}, "include_fields": list(INCLUDE_FIELDS),
            "offset": offset, "limit": PAGE, "sort_field": "appl_id", "sort_order": "asc"}


def fetch_seed(seed: str, post=_post) -> list[dict]:
    crit = {"advanced_text_search": {"operator": "advanced", "search_field": "projecttitle,abstracttext",
                                     "search_text": f'"{seed}"'}}
    out, offset = [], 0
    while len(out) < SEED_CAP:
        d = post(_body(crit, offset))
        res = d.get("results") or []
        out.extend(res)
        offset += len(res)
        if not res or offset >= int(d.get("meta", {}).get("total", 0)):
            break
    return out[:SEED_CAP]


def fetch_background(post=_post) -> list[dict]:
    out = []
    for off in BACKGROUND_OFFSETS:
        out.extend(post(_body({}, off)).get("results") or [])
    return out


def build(seeds: dict[str, list[str]], excluded_appl: set[int], excluded_core: set[str], post=_post):
    docs: dict[int, dict] = {}
    dropped = {"same_core_as_fixture": 0, "fixture_appl_id": 0, "no_text": 0, "wrong_fy": 0}

    def add(raw: dict, qid: str):
        a = int(raw["appl_id"])
        if a in excluded_appl:
            dropped["fixture_appl_id"] += 1; return
        core = (raw.get("core_project_num") or "").upper() or None
        if core in excluded_core:
            dropped["same_core_as_fixture"] += 1; return
        if int(raw.get("fiscal_year") or 0) != CORPUS_FY:
            dropped["wrong_fy"] += 1; return
        if not (raw.get("project_title") or raw.get("abstract_text")):
            dropped["no_text"] += 1; return
        d = docs.setdefault(a, {"appl_id": a, "core_project_num": core, "fiscal_year": CORPUS_FY,
                                "title": raw.get("project_title"), "abstract": raw.get("abstract_text"),
                                "queries": []})
        if qid not in d["queries"]:
            d["queries"].append(qid)

    for pca in sorted(seeds):
        for s in seeds[pca]:
            for raw in fetch_seed(s, post):
                add(raw, f"seed:{pca}:{s}")
    for raw in fetch_background(post):
        add(raw, "background")
    recs = [docs[a] for a in sorted(docs)]
    for r in recs:
        r["queries"].sort()
    lines = [json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":")) for r in recs]
    raw_jsonl = ("\n".join(lines) + "\n").encode("utf-8")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, filename="") as g:
        g.write(raw_jsonl)
    per_query: dict[str, int] = {}
    for r in recs:
        for q in r["queries"]:
            per_query[q] = per_query.get(q, 0) + 1
    manifest = {"derivation_id": DERIVATION_ID, "corpus_fy": CORPUS_FY, "api": API_URL,
                "include_fields": list(INCLUDE_FIELDS), "search_field": "projecttitle,abstracttext",
                "seed_cap": SEED_CAP, "background_offsets": list(BACKGROUND_OFFSETS),
                "excluded": {"fixture_appl_ids": len(excluded_appl), "fixture_core_projects": len(excluded_core)},
                "dropped": dropped, "docs": len(recs), "docs_per_query": dict(sorted(per_query.items())),
                "jsonl_sha256": hashlib.sha256(raw_jsonl).hexdigest()}
    return buf.getvalue(), manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", type=Path, required=True)
    ap.add_argument("--seeds", type=Path, default=ROOT / "scope" / "synonym_seeds.v1.json")
    ap.add_argument("--out", type=Path, default=ROOT / "corpus")
    a = ap.parse_args(argv)
    refs = load_project_refs(a.fixture)
    excluded_appl = {r.appl_id for r in refs}
    excluded_core = {c for c in (core_of(r.project_number) for r in refs) if c}
    seeds = json.loads(a.seeds.read_text(encoding="utf-8"))["seeds"]
    gz, manifest = build(seeds, excluded_appl, excluded_core)
    manifest["fetched_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest["gz_sha256"] = hashlib.sha256(gz).hexdigest()
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "fy2024_independent.v1.jsonl.gz").write_bytes(gz)
    (a.out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("docs", "dropped", "excluded", "jsonl_sha256")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
