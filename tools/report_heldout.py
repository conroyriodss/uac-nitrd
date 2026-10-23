#!/usr/bin/env python3
"""Post-reveal miss breakdown (REPORTING ONLY; the match rule and X are unchanged).

Committed 2026-10-23, before the reveal: report-breakdown-v1-2026-10-23.

This tool never reads the held-out key. Its inputs are the committed scorer's JSON output
(score_heldout.py, the only reader of the key), the frozen proposals and the explanations.
The scorer already lists the no_proposal and advanced_wireless misses, and the PCA-only
count. That is enough to split the 214 - X misses into four disjoint parts that sum
exactly:

  abstained          no proposal for a key project (empty primary_pca). The engine declined.
                     Split by the engine's own abstain_reason into: no public text (RePORTER
                     record not found or empty) and below the scope-match threshold.
  aw_primary         primary_pca = AW. Expected 0, because format v2 forbids it.
  wrong_pca          a PCA was proposed and it is not the key PCA ("proposed incorrectly").
                     Sub-count: AI proposed for a "<PCA> - AI" key.
  right_pca_no_flag  the right PCA, but ai_relevant = false. The strict rule counts this as
                     a miss.

The headline is always "Match rate: X/214". The breakdown is stated next to it, never
instead of it. It reports COUNTS of misses only. No new rate is derived from them, such as
"X out of those proposed": that would be a precision figure, which the protocol's claim rules
forbid. Abstaining on text that doesn't match the scope wording is the deterministic
engine behaving as designed: it is reported as a decline, not as a wrong proposal, and it
still counts as a miss in X.

Usage: python tools/report_heldout.py --score score.json --proposals proposals/proposals.csv \
           --explanations proposals/explanations.jsonl [--out report.json]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

REPORT_ID = "report-breakdown-v1-2026-10-23"
EXPECTED_RULE_ID = "entry2-match-rule-v1-2026-10-23"
N = 214
# abstain_reason vocabulary (fixed in docs/ENGINE_DESIGN.md): every value starts with one of these.
REASON_PREFIX = {"no_public_text": "no_public_text", "below_threshold": "below_scope_threshold"}


def _count(s: str) -> int:
    m = re.match(r"\s*(\d+)\s*/\s*(\d+)", s)
    if not m or int(m.group(2)) != N:
        raise SystemExit(f"unexpected secondary figure {s!r}")
    return int(m.group(1))


def breakdown(score: dict, proposals: dict[int, dict], explanations: dict[int, dict]) -> dict:
    if score.get("rule_id") != EXPECTED_RULE_ID or score.get("denominator") != N or "STOPPED" in score:
        raise SystemExit("score output is not a completed run of the committed rule")
    x = int(score["X_strict"])
    pca_only = _count(score["secondary_labelled"]["pca_only_match"])
    ml = score["misses_listed"]
    abst, aw, ai_sfx = sorted(ml["no_proposal"]), sorted(ml["advanced_wireless"]), ml["ai_pca_proposed_for_suffix_key"]
    right_no_flag = pca_only - x
    wrong = N - pca_only - len(abst) - len(aw)
    misses = N - x
    if min(right_no_flag, wrong) < 0 or len(abst) + len(aw) + wrong + right_no_flag != misses:
        raise SystemExit("breakdown does not partition the misses; refusing to report")

    def reason(a: int) -> str:
        r = (explanations.get(a) or {}).get("abstain_reason") or ""
        for prefix, bucket in REASON_PREFIX.items():
            if r.startswith(prefix):
                return bucket
        raise SystemExit(f"appl_id {a}: abstained without a recognised abstain_reason ({r!r}); refusing to report")

    no_text = [a for a in abst if reason(a) == "no_public_text"]
    below = [a for a in abst if reason(a) == "below_scope_threshold"]
    return {
        "report_id": REPORT_ID, "rule_id": EXPECTED_RULE_ID,
        "headline": f"Match rate: {x}/{N}",
        "misses": misses,
        "breakdown": {
            "wrong_pca": {"n": wrong, "of_which_ai_for_suffix_key": len(ai_sfx),
                          "meaning": "proposed incorrectly"},
            "right_pca_no_ai_flag": {"n": right_no_flag, "meaning": "right PCA, AI flag not set"},
            "abstained": {"n": len(abst), "no_public_text": len(no_text), "below_scope_threshold": len(below),
                          "meaning": "declined to propose"},
            "aw_primary": {"n": len(aw), "meaning": "AW as primary (0 expected under format v2)"},
        },
        "statement": (
            f"Match rate: {x}/{N}. Of the {misses} misses, {wrong} proposed a wrong PCA, "
            f"{right_no_flag} proposed the right PCA without the AI flag, and {len(abst)} abstained "
            f"(declined to propose: {len(no_text)} with no public text, {len(below)} below the scope-match "
            f"threshold); {len(aw)} proposed Advanced Wireless as primary. Abstentions are the engine "
            f"declining where the project text does not match NITRD scope wording. They are reported as "
            f"declines, not as incorrect proposals, and they remain misses in X."),
        "lists": {"abstained_no_public_text": no_text, "abstained_below_threshold": below,
                  "aw_primary": aw, "ai_for_suffix_key": sorted(ai_sfx)},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--score", type=Path, required=True)
    ap.add_argument("--proposals", type=Path, required=True)
    ap.add_argument("--explanations", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    score = json.loads(a.score.read_text(encoding="utf-8"))
    with a.proposals.open(newline="", encoding="utf-8-sig") as f:
        props = {int(r["appl_id"]): r for r in csv.DictReader(f)}
    expl = {}
    for line in a.explanations.read_text(encoding="utf-8").splitlines():
        if line.strip():
            e = json.loads(line)
            expl[int(e["appl_id"])] = e
    rep = breakdown(score, props, expl)
    out = json.dumps(rep, indent=2)
    if a.out:
        a.out.write_text(out + "\n", encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
