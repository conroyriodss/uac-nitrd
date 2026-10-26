"""Shortlist file contract for the Task 1 scorer (nitrd-parent-match-rule-v4-2026-10-25, section 5).

v4 is the scoring rule (seal-log line 30). v4 section 5 differs from v3 section 5 only in its last bullet
("the seal log not recording the supersession to v4"); that is a seal-log check done by the scorer, not
a property of the shortlist file, so the checks below are unchanged from the v3 version (4dec201).

The scorer MUST call validate_shortlist() before computing anything; any ShortlistContractError is a
STOP (no score). Enforced, exactly as v4 section 5 states:

* columns exactly: appl_id, decision, score, reason
* exactly one row per appl_id in the universe U (no extra, missing or duplicate appl_ids)
* decision in {candidate, not_candidate, abstain}
* score present and a finite real number on EVERY row (v4 requires it for all rows, not only
  candidates; higher = more candidate-like). Ranking for the SME-effort metric uses candidates' scores.
* abstain only with reason no_public_text, and only on an appl_id whose sealed text has neither title
  nor abstract (the caller passes that set; the seal froze 0 such records)

No label is read here.
"""
import csv
import math
from pathlib import Path

CONTRACT_ID = "task1-shortlist-contract-v1-2026-10-25"
RULE_ID = "nitrd-parent-match-rule-v4-2026-10-25"
COLUMNS = ["appl_id", "decision", "score", "reason"]
DECISIONS = {"candidate", "not_candidate", "abstain"}
ABSTAIN_REASON = "no_public_text"


class ShortlistContractError(ValueError):
    """The shortlist file violates v4 section 5; the scorer must STOP."""


def _score(raw: str, appl_id: str) -> float:
    try:
        s = float(raw)
    except (TypeError, ValueError):
        raise ShortlistContractError(f"appl_id {appl_id}: score {raw!r} is missing or not a number") from None
    if not math.isfinite(s):
        raise ShortlistContractError(f"appl_id {appl_id}: score {raw!r} is not finite")
    return s


def validate_shortlist(path: Path, universe: set[int], no_public_text: frozenset[int] = frozenset()) -> dict:
    with Path(path).open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        if rd.fieldnames != COLUMNS:
            raise ShortlistContractError(f"columns {rd.fieldnames} != {COLUMNS}")
        rows = list(rd)
    seen, counts = set(), {d: 0 for d in sorted(DECISIONS)}
    for r in rows:
        a = r["appl_id"]
        try:
            ai = int(a)
        except ValueError:
            raise ShortlistContractError(f"appl_id {a!r} is not an integer") from None
        if ai in seen:
            raise ShortlistContractError(f"appl_id {ai} appears more than once")
        seen.add(ai)
        if ai not in universe:
            raise ShortlistContractError(f"appl_id {ai} is outside the universe")
        d = r["decision"]
        if d not in DECISIONS:
            raise ShortlistContractError(f"appl_id {ai}: decision {d!r} not in {sorted(DECISIONS)}")
        _score(r["score"], a)
        if d == "abstain":
            if r["reason"] != ABSTAIN_REASON:
                raise ShortlistContractError(f"appl_id {ai}: abstain needs reason {ABSTAIN_REASON!r}")
            if ai not in no_public_text:
                raise ShortlistContractError(f"appl_id {ai}: abstain on a record that has public text")
        counts[d] += 1
    missing = universe - seen
    if missing:
        raise ShortlistContractError(f"{len(missing)} universe appl_ids have no row")
    return {"contract_id": CONTRACT_ID, "rule_id": RULE_ID, "rows": len(rows), "decisions": counts}
