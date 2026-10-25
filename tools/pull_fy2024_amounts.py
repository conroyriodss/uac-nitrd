"""Pull FY2024 award_amount per appl_id from RePORTER: identity + amount only, NO label, NO text.

Feeds the dollar-weighted precision/recall in nitrd-parent-match-rule-v3 section 6.

* Universe = the sealed FY2024 universe (build/universe/fy2024_identity.csv, all instruments and
  subprojects; full RePORTER, not the RCDC view). Records RePORTER added after the seal are dropped
  and counted; a sealed appl_id that RePORTER no longer returns is a hard failure.
* Every request body is checked against a whitelist before it is sent: criteria keys may only be
  fiscal_years / agencies, include_fields may only be ApplId / AwardAmount. No spending_categories
  criterion or field, no terms, no text. Every response record is checked to carry only appl_id /
  award_amount.
* Output build/amounts/fy2024_amounts.v1.csv (appl_id, award_amount; empty = null in RePORTER),
  sorted by appl_id, plus fy2024_amounts.v1.manifest.json. Refuses to overwrite.
"""
import csv
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
URL = "https://api.reporter.nih.gov/v2/projects/search"
AMOUNTS_ID = "fy2024-amounts-v1-2026-10-25"
FY = 2024
IDENTITY = ROOT / "build" / "universe" / "fy2024_identity.csv"
IDENTITY_SHA256 = "9d996db94774a9b7e4b450361d4d903182411cd346a3b810b99938a3ee10936c"
OUT = ROOT / "build" / "amounts" / "fy2024_amounts.v1.csv"
MANIFEST = OUT.with_name("fy2024_amounts.v1.manifest.json")
INCLUDE_FIELDS = ("ApplId", "AwardAmount")
ALLOWED_CRITERIA = {"fiscal_years", "agencies"}
ALLOWED_RESPONSE_KEYS = {"appl_id", "award_amount"}
ICS = ("NCI", "NHLBI", "NIAID", "NIGMS", "NIDDK", "NINDS", "NIMH", "NICHD", "NIA", "NIEHS", "NIDA", "NEI",
       "NIAMS", "NIAAA", "NIDCD", "NIDCR", "NHGRI", "NIBIB", "NIMHD", "NINR", "NLM", "NCATS", "NCCIH", "FIC",
       "OD", "CLC")
PAGE, OFFSET_CAP = 500, 14_999


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def check_body(body: dict) -> dict:
    crit = body["criteria"]
    if set(crit) - ALLOWED_CRITERIA:
        raise SystemExit(f"refused: criteria keys {sorted(set(crit) - ALLOWED_CRITERIA)} not allowed")
    if tuple(body["include_fields"]) != INCLUDE_FIELDS:
        raise SystemExit(f"refused: include_fields {body['include_fields']} != {INCLUDE_FIELDS}")
    if crit["fiscal_years"] != [FY]:
        raise SystemExit("refused: fiscal year")
    return body


def post(body: dict) -> dict:
    check_body(body)
    for i in range(6):
        try:
            r = requests.post(URL, json=body, timeout=120)
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            time.sleep(2 + 3 * i)
    raise RuntimeError("RePORTER API failed")


def pull_ic(ic: str):
    out, off, total = {}, 0, None
    while True:
        j = post({"criteria": {"fiscal_years": [FY], "agencies": [ic]}, "include_fields": list(INCLUDE_FIELDS),
                  "offset": off, "limit": PAGE, "sort_field": "appl_id", "sort_order": "asc"})
        total = j["meta"]["total"]
        if total > OFFSET_CAP + PAGE:
            raise SystemExit(f"{ic}: {total} records exceed the API offset cap; partition further")
        for x in j["results"]:
            extra = set(x) - ALLOWED_RESPONSE_KEYS
            if extra:
                raise SystemExit(f"refused: response carried fields {sorted(extra)}")
            out[int(x["appl_id"])] = x.get("award_amount")
        off += PAGE
        if off >= total:
            return ic, out, total


def main() -> None:
    if OUT.exists() or MANIFEST.exists():
        raise SystemExit(f"refused: {OUT.parent} already has v1 output; a change ships as a new version")
    if sha256(IDENTITY) != IDENTITY_SHA256:
        raise SystemExit("fy2024_identity.csv does not match its pin")
    with IDENTITY.open(newline="") as f:
        sealed = {int(r["appl_id"]) for r in csv.DictReader(f)}
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with ThreadPoolExecutor(6) as ex:
        parts = list(ex.map(pull_ic, ICS))
    amounts, per_ic = {}, {}
    for ic, d, total in parts:
        per_ic[ic] = total
        amounts.update(d)
    missing = sealed - amounts.keys()
    if missing:
        raise SystemExit(f"{len(missing)} sealed appl_ids not returned by RePORTER; refused")
    added_after_seal = len(amounts.keys() - sealed)
    rows = sorted((a, amounts[a]) for a in sealed)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["appl_id", "award_amount"])
        for a, amt in rows:
            w.writerow([a, "" if amt is None else int(amt)])
    nulls = sum(amt is None for _, amt in rows)
    zeros = sum(amt == 0 for _, amt in rows)
    manifest = {
        "amounts_id": AMOUNTS_ID, "fiscal_year": FY, "pulled_at_utc": started, "source": URL,
        "purpose": "dollar-weighted precision/recall, nitrd-parent-match-rule-v3 section 6",
        "request": {"criteria_keys": sorted(ALLOWED_CRITERIA), "include_fields": list(INCLUDE_FIELDS),
                    "partition": "agencies, one IC per request", "ics": list(ICS)},
        "labels_requested": False, "text_requested": False,
        "universe": {"path": str(IDENTITY.relative_to(ROOT)), "sha256": IDENTITY_SHA256, "appl_ids": len(sealed),
                     "filter": "full sealed FY2024 universe (all instruments, all subprojects); not the RCDC view"},
        "reporter_records_returned": len(amounts), "reporter_added_after_seal_dropped": added_after_seal,
        "per_ic_totals": per_ic,
        "rows": len(rows), "null_award_amount": nulls, "zero_award_amount": zeros,
        "sum_award_amount": sum(int(amt) for _, amt in rows if amt is not None),
        "output": {"path": str(OUT.relative_to(ROOT)), "sha256": sha256(OUT)},
    }
    MANIFEST.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: manifest[k] for k in ("rows", "reporter_records_returned", "reporter_added_after_seal_dropped",
                                               "null_award_amount", "zero_award_amount", "sum_award_amount", "output")},
                     indent=1))


if __name__ == "__main__":
    main()
