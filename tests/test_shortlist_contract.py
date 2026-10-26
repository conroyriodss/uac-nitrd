"""The Task 1 shortlist contract (v4 section 5) rejects any file the scorer must not score.

Synthetic appl_ids only (no sealed data, no labels).
"""
import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow.shortlist_contract import COLUMNS, ShortlistContractError, validate_shortlist  # noqa: E402

U = {91000001, 91000002, 91000003, 91000004}
NO_TEXT = frozenset({91000004})
GOOD = [
    {"appl_id": "91000001", "decision": "candidate", "score": "0.91", "reason": ""},
    {"appl_id": "91000002", "decision": "candidate", "score": "0.40", "reason": ""},
    {"appl_id": "91000003", "decision": "not_candidate", "score": "-1.5", "reason": ""},
    {"appl_id": "91000004", "decision": "abstain", "score": "0", "reason": "no_public_text"},
]


def _write(tmp_path, rows, columns=COLUMNS):
    p = tmp_path / "shortlist.csv"
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return p


def _with(i, **kw):
    rows = [dict(r) for r in GOOD]
    rows[i].update(kw)
    return rows


def test_valid_shortlist_passes(tmp_path):
    out = validate_shortlist(_write(tmp_path, GOOD), U, NO_TEXT)
    assert out["decisions"] == {"abstain": 1, "candidate": 2, "not_candidate": 1}


@pytest.mark.parametrize("rows", [
    _with(0, score=""),                 # candidate without a score
    _with(1, score="high"),             # not a number
    _with(0, score="nan"),              # not finite
    _with(1, score="inf"),
    _with(2, score=""),                 # v4 (as v3) requires a score on not_candidate rows too
    _with(3, score=""),                 # ... and on abstain rows
], ids=["candidate-missing", "candidate-text", "nan", "inf", "not_candidate-missing", "abstain-missing"])
def test_score_required_and_finite_on_every_row(tmp_path, rows):
    with pytest.raises(ShortlistContractError, match="score"):
        validate_shortlist(_write(tmp_path, rows), U, NO_TEXT)


def test_missing_score_column_refused(tmp_path):
    with pytest.raises(ShortlistContractError, match="columns"):
        validate_shortlist(_write(tmp_path, GOOD, ["appl_id", "decision", "reason"]), U, NO_TEXT)


@pytest.mark.parametrize("rows,match", [
    (GOOD[:3], "no row"),                                                     # missing appl_id
    (GOOD + [GOOD[0]], "more than once"),                                     # duplicate
    (GOOD + [{"appl_id": "91000099", "decision": "candidate", "score": "1", "reason": ""}], "outside"),
    (_with(2, decision="maybe"), "decision"),
    (_with(3, reason="low confidence"), "no_public_text"),
    (_with(2, decision="abstain", reason="no_public_text"), "has public text"),
], ids=["missing", "duplicate", "outside-U", "bad-decision", "abstain-reason", "abstain-with-text"])
def test_other_section5_stop_conditions(tmp_path, rows, match):
    with pytest.raises(ShortlistContractError, match=match):
        validate_shortlist(_write(tmp_path, rows), U, NO_TEXT)


def test_contract_targets_v4_and_section5_change_is_seal_log_only():
    """RULE_ID is v4; v3 -> v4 section 5 differs only in the seal-log supersession bullet (scorer's job)."""
    import re
    from workflow import shortlist_contract as sc
    assert sc.RULE_ID == "nitrd-parent-match-rule-v4-2026-10-25"

    def sec5(name):
        t = (ROOT / "docs" / name).read_text()
        m = re.search(r"(?ms)^## 5\. .*?(?=^## 6\. )", t)
        assert m, name
        return m.group(0).splitlines()

    v3, v4 = sec5("TASK1_MATCH_RULE_v3.md"), sec5("TASK1_MATCH_RULE_v4.md")
    diff = [(a, b) for a, b in zip(v3, v4) if a != b]
    assert len(v3) == len(v4) and diff == [
        ("  * the seal log not recording the supersession to v3.",
         "  * the seal log not recording the supersession to v4.")]
