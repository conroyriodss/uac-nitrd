#!/usr/bin/env python3
"""Build versioned NITRD subcategory-scope objects from a saved NITRD PCA-definitions page.

Deterministic. Same snapshot + same metadata -> byte-identical JSON. Network access is
not used here: the snapshot is fetched separately and its SHA-256 recorded, so the
scope text can always be re-derived from the stored public source.

Usage:
  python build_pca_scopes.py --snapshot scope/sources/nitrd-pcas-2025.html \
      --snapshot-ref scope/sources/nitrd-pcas-2025.html \
      --fy 2025 --url https://www.nitrd.gov/program-component-areas/nitrd-pcas-2025/ \
      --retrieved-at 2026-10-23T20:27:27Z --version 1 --out scope/nitrd_pca_scopes_fy2025.v1.json

Object kinds:
  pca      one of the 12 standard NITRD Program Component Areas (scope = NITRD definition, verbatim)
  sub_pca  a breakout nested under a PCA (Advanced Wireless R&D under ACNS): selectable as a label
           but NOT a standard PCA scope; its dollar roll-up rule is recorded as UNRESOLVED
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

SCHEMA = "uac-nitrd/subcategory-scope/v1"
PCA_CODES = ("ACNS", "AI", "CHuman", "CNPS", "CSP", "EdW", "EHCS", "ENIT", "HCIA", "IRAS", "LSDMA", "SPSQ")
DASH = "\u2013"  # NITRD headings use an en dash: "ACNS – Advanced ..."
BACK = "\u2191 PCA List"
RULE_LINE = re.compile(r"^\u2014{5,}$")


def page_lines(html: bytes) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup.body
    return main.get_text("\n", strip=True).splitlines()


def parse(lines: list[str], fy: int) -> tuple[dict, dict]:
    start = lines.index(f"FY{fy} NITRD PCA Definitions") + 1
    end = next(i for i in range(start, len(lines)) if RULE_LINE.match(lines[i]))
    heading = re.compile(rf"^({'|'.join(PCA_CODES)}) {DASH} (.+)$")
    blocks: dict[str, dict] = {}
    cur = None
    for ln in lines[start:end]:
        m = heading.match(ln)
        if m and m.group(1) not in blocks:
            cur = {"code": m.group(1), "label": m.group(2), "body": [], "annotations": []}
            blocks[cur["code"]] = cur
        elif ln == BACK:
            cur = None
        elif cur is not None:
            if ln == "*":
                cur["annotations"].append("footnoted (see cross_pca_guidance)")
            elif re.fullmatch(r"\(new in FY\d{4}\)", ln):
                cur["annotations"].append(ln.strip("()"))
            else:
                cur["body"].append(ln)
    missing = [c for c in PCA_CODES if c not in blocks]
    if missing:
        raise SystemExit(f"definitions missing for {missing}")
    # Footnotes after the rule line: the AI definition (with its cited URL) and the
    # cross-PCA examples for AI. Kept verbatim, in page order.
    notes: list[dict] = []
    for ln in lines[end + 1:]:
        if ln.startswith("http") and notes:
            notes[-1]["cited"] = ln
        elif ln.startswith("* ") or not notes:
            notes.append({"text": ln[2:] if ln.startswith("* ") else ln, "items": []})
        else:
            notes[-1]["items"].append(ln)
    ai_note = next((n for n in notes if n["text"].startswith("The term")), None)
    xpca = next((n for n in notes if "intersect with multiple PCAs" in n["text"]), None)
    if ai_note is None or xpca is None:
        raise SystemExit("AI footnotes not found")
    return blocks, {"ai_definition": ai_note, "ai_cross_pca": xpca}


def build(snapshot: Path, snapshot_ref: str, fy: int, url: str, retrieved_at: str, version: int) -> dict:
    html = snapshot.read_bytes()
    lines = page_lines(html)
    blocks, guidance = parse(lines, fy)
    scopes = []
    sub = None
    for code in PCA_CODES:
        b = blocks[code]
        body = b["body"]
        if "[Sub-PCA]" in body:
            k = body.index("[Sub-PCA]")
            sub_text = " ".join(body[k + 1:])
            body = body[:k]
            sub = (code, sub_text)
        scopes.append({
            "code": code, "label": b["label"], "kind": "pca", "standard_pca": True, "selectable": True,
            "parent": None, "uac_suggestion_value": code, "budget_crosscut_code": code,
            "scope_text": " ".join(body), "annotations": b["annotations"],
        })
    if sub is None:
        raise SystemExit("expected a [Sub-PCA] breakout (Advanced Wireless R&D) and found none")
    parent, text = sub
    if not text.startswith("Advanced Wireless R&D"):
        raise SystemExit(f"unexpected Sub-PCA text under {parent}: {text[:60]!r}")
    scopes.append({
        "code": "AW", "label": "Advanced Wireless R&D", "kind": "sub_pca", "standard_pca": False,
        "selectable": True, "parent": parent, "uac_suggestion_value": "Advanced Wireless R&D",
        "budget_crosscut_code": None, "scope_text": text, "annotations": [f"[Sub-PCA] of {parent} on the NITRD page"],
        "rollup": {
            "status": "UNRESOLVED",
            "sourced_facts": [
                f"NITRD lists Advanced Wireless R&D as a [Sub-PCA] inside the {parent} definition (this page).",
                "The NITRD budget crosscut (context/NITRD_Budget_Tables.csv) has no Advanced Wireless line in any FY.",
                "The RCDC NITRD exports reviewed at gate 0b have no Advanced Wireless category.",
                "The UAC fixture offers 'Advanced Wireless R&D' as a suggestion value alongside the 12 PCA codes.",
            ],
            "open_question": f"Whether an Advanced Wireless assignment also counts toward {parent} (nested roll-up) or is a separate breakout; not stated in any source in hand.",
            "rule_until_resolved": f"Do not add AW dollars into {parent} totals or subtract them out; report AW separately.",
        },
    })
    return {
        "schema": SCHEMA,
        "scope_set_id": f"nitrd-pca-fy{fy}",
        "version": version,
        "fiscal_year": fy,
        "source": {
            "publisher": "NITRD National Coordination Office",
            "title": f"FY{fy} NITRD Program Component Areas (PCAs)",
            "url": url,
            "retrieved_at_utc": retrieved_at,
            "snapshot_file": snapshot_ref,
            "snapshot_sha256": hashlib.sha256(html).hexdigest(),
            "text_policy": "scope_text is verbatim NITRD wording (whitespace-joined lines); no paraphrase",
        },
        "scopes": scopes,
        "cross_pca_guidance": guidance,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", type=Path, required=True)
    ap.add_argument("--snapshot-ref", help="repo-relative path recorded in the object (default: file name)")
    ap.add_argument("--fy", type=int, required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--retrieved-at", required=True)
    ap.add_argument("--version", type=int, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    obj = build(a.snapshot, a.snapshot_ref or a.snapshot.name, a.fy, a.url, a.retrieved_at, a.version)
    a.out.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{a.out}: {len(obj['scopes'])} scopes, sha256 {hashlib.sha256(a.out.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
