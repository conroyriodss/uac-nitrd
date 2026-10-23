#!/usr/bin/env python3
"""Entry 2 held-out scorer. Match rule COMMITTED 2026-10-23, BEFORE the reveal.

This file is the executable form of the match rule in HELDOUT_PROTOCOL.md section
"Committed match rule". It is committed, and its SHA-256 recorded, before the key is
read. It is run ONCE, in the evaluation step, outside the build tree. Any edit after
the reveal is score-fitting and invalidates the result.

INPUTS
  --proposals  frozen proposals CSV with columns:
                 appl_id      integer Appl ID
                 primary_pca  one of PCA_CODES, or "AW" (Advanced Wireless R&D), or empty (no proposal)
                 ai_relevant  "true" / "false"; empty is read as false
               (Other columns are ignored. A second-ranked PCA, if present, is NOT used.)
  --key        the sealed held-out file
  --key-sha256 expected digest; on a mismatch the run stops (seal failure)

MATCH RULE (per key project; the denominator is ALL key projects, fixed at 214)
  1. Key label -> (key_pca, key_ai=True):
       "NITRD - Artificial Intelligence (AI)" -> ("AI", True)
       "NITRD - <PCA> - AI"                   -> ("<PCA>", True), <PCA> in PCA_CODES and != "AI"
       anything else (e.g. legacy LSN) -> stop (key anomaly; reported, not remapped)
     All rows of one Appl ID must carry the same label; otherwise stop (key anomaly).
  2. STRICT match (the headline X):
       primary_pca == key_pca  AND  ai_relevant is true.
  3. Reported separately, always labelled, never substituted for X:
       pca_only    primary_pca == key_pca (AI flag ignored)
       ai_flag     ai_relevant is true (on the 214 this is RECALL only; every key project is AI-relevant)
  4. A missing proposal, empty primary_pca, or "AW" on a key project = a miss (listed separately).
  5. Proposal "AI" for key "<PCA> - AI" (PCA != AI) = a miss: AI is its own PCA, not the suffix.
     Proposal "<PCA>" with ai_relevant true for key "NITRD - Artificial Intelligence (AI)" = a miss.
VALIDATION (fails before any scoring; also run at freeze time with --validate-only)
  primary_pca outside PCA_CODES + {"AW", ""}; ai_relevant not a boolean; duplicate appl_id;
  primary_pca == "AI" with ai_relevant false (contradiction: the AI PCA implies AI-relevance).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from pathlib import Path

RULE_ID = "entry2-match-rule-v1-2026-10-23"
PCA_CODES = ("ACNS", "AI", "CHuman", "CNPS", "CSP", "EdW", "EHCS", "ENIT", "HCIA", "IRAS", "LSDMA", "SPSQ")
AW = "AW"
EXPECTED_KEY_PROJECTS = 214
_AI_PCA_LABEL = "NITRD - Artificial Intelligence (AI)"
_SUFFIX_RE = re.compile(r"^NITRD - (\S+) - AI$")


class Stop(RuntimeError):
    """A seal or key anomaly. The evaluation stops and is reported; nothing is worked around."""


def _bool(v: str, where: str) -> bool:
    s = (v or "").strip().lower()
    if s in ("", "false"):
        return False
    if s == "true":
        return True
    raise ValueError(f"{where}: ai_relevant must be true/false, got {v!r}")


def load_proposals(path: Path) -> dict[int, tuple[str, bool]]:
    out: dict[int, tuple[str, bool]] = {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        missing = {"appl_id", "primary_pca", "ai_relevant"} - set(r.fieldnames or [])
        if missing:
            raise ValueError(f"proposals missing columns: {sorted(missing)}")
        for i, row in enumerate(r, start=2):
            where = f"proposals line {i}"
            appl = int(row["appl_id"].strip())
            pca = (row["primary_pca"] or "").strip()
            if pca not in PCA_CODES and pca not in (AW, ""):
                raise ValueError(f"{where}: unknown primary_pca {pca!r}")
            ai = _bool(row["ai_relevant"], where)
            if pca == "AI" and not ai:
                raise ValueError(f"{where}: primary_pca AI with ai_relevant false is contradictory")
            if appl in out:
                raise ValueError(f"{where}: duplicate appl_id {appl}")
            out[appl] = (pca, ai)
    return out


def key_pca(label: str) -> str:
    label = label.strip().replace("\u2013", "-")
    if label == _AI_PCA_LABEL:
        return "AI"
    m = _SUFFIX_RE.match(label)
    if m and m.group(1) in PCA_CODES and m.group(1) != "AI":
        return m.group(1)
    raise Stop(f"key label outside the committed mapping: {label!r}")


def load_key(path: Path, expected_sha: str) -> dict[int, str]:
    data = path.read_bytes()
    got = hashlib.sha256(data).hexdigest()
    if got != expected_sha:
        raise Stop(f"key SHA-256 mismatch: {got} != {expected_sha} (seal failure)")
    key: dict[int, str] = {}
    for row in csv.DictReader(io.StringIO(data.decode("utf-8"))):
        appl, pca = int(row["Appl ID"]), key_pca(row["Category"])
        if key.setdefault(appl, pca) != pca:
            raise Stop(f"key anomaly: Appl ID {appl} carries more than one category")
    if len(key) != EXPECTED_KEY_PROJECTS:
        raise Stop(f"key has {len(key)} projects, expected {EXPECTED_KEY_PROJECTS}")
    return key


def score(proposals: dict[int, tuple[str, bool]], key: dict[int, str]) -> dict:
    n = len(key)
    strict = pca_only = ai_flag = 0
    no_proposal, aw, ai_for_suffix = [], [], []
    for appl, kp in sorted(key.items()):
        pca, ai = proposals.get(appl, ("", False))
        if appl not in proposals or pca == "":
            no_proposal.append(appl)
        elif pca == AW:
            aw.append(appl)
        if pca == "AI" and kp != "AI":
            ai_for_suffix.append(appl)
        strict += int(pca == kp and ai)
        pca_only += int(pca == kp)
        ai_flag += int(ai)
    return {
        "rule_id": RULE_ID,
        "denominator": n,
        "X_strict": strict,
        "headline": f"Match rate: {strict}/{n}",
        "secondary_labelled": {
            "pca_only_match": f"{pca_only}/{n} (primary PCA equal, AI flag ignored)",
            "ai_flag_recall": f"{ai_flag}/{n} (recall only; every key project is AI-relevant)",
        },
        "misses_listed": {"no_proposal": no_proposal, "advanced_wireless": aw,
                           "ai_pca_proposed_for_suffix_key": ai_for_suffix},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--proposals", type=Path, required=True)
    ap.add_argument("--key", type=Path)
    ap.add_argument("--key-sha256")
    ap.add_argument("--validate-only", action="store_true")
    a = ap.parse_args(argv)
    props = load_proposals(a.proposals)
    if a.validate_only:
        print(json.dumps({"rule_id": RULE_ID, "proposals_valid": True, "n": len(props)}))
        return 0
    if not a.key or not a.key_sha256:
        ap.error("--key and --key-sha256 are required to score")
    try:
        result = score(props, load_key(a.key, a.key_sha256))
    except Stop as e:
        print(json.dumps({"rule_id": RULE_ID, "STOPPED": str(e)}))
        return 3
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
