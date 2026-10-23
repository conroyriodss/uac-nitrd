"""Post-reveal miss breakdown (report-breakdown-v1). Synthetic scorer output only; no key is read."""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from report_heldout import breakdown  # noqa: E402

IDS = list(range(90000001, 90000001 + 214))  # fabricated; not fixture IDs


def _score(x=100, pca_only=120, no_prop=IDS[:50], aw=(), ai_sfx=IDS[60:65]):
    # Same shape as score_heldout.score()
    return {"rule_id": "entry2-match-rule-v1-2026-10-23", "denominator": 214, "X_strict": x,
            "headline": f"Match rate: {x}/214",
            "secondary_labelled": {"pca_only_match": f"{pca_only}/214 (primary PCA equal, AI flag ignored)",
                                   "ai_flag_recall": "150/214 (recall only)"},
            "misses_listed": {"no_proposal": list(no_prop), "advanced_wireless": list(aw),
                              "ai_pca_proposed_for_suffix_key": list(ai_sfx)}}


def _expl(no_text=IDS[:10], below=IDS[10:50]):
    e = {a: {"appl_id": a, "abstain_reason": "no_public_text: RePORTER record not_found"} for a in no_text}
    e.update({a: {"appl_id": a, "abstain_reason": "below_threshold: top score 0.8 < 2.0"} for a in below})
    return e


def test_partition_sums_and_headline_unchanged():
    r = breakdown(_score(), {}, _expl())
    b = r["breakdown"]
    assert r["headline"] == "Match rate: 100/214"
    assert (b["wrong_pca"]["n"], b["right_pca_no_ai_flag"]["n"], b["abstained"]["n"], b["aw_primary"]["n"]) == (44, 20, 50, 0)
    assert sum(v["n"] for v in b.values()) == r["misses"] == 114
    assert (b["abstained"]["no_public_text"], b["abstained"]["below_scope_threshold"]) == (10, 40)
    assert b["wrong_pca"]["of_which_ai_for_suffix_key"] == 5


def test_statement_states_both_and_keeps_headline_first():
    s = breakdown(_score(), {}, _expl())["statement"]
    assert s.startswith("Match rate: 100/214.")
    assert "44 proposed a wrong PCA" in s and "50 abstained" in s and "declined to propose" in s
    assert "remain misses in X" in s


def test_no_new_rate_is_derived():
    """Protocol claim rules: no other accuracy figure (no precision) from File A."""
    r = breakdown(_score(), {}, _expl())
    assert "secondary_labelled" not in r
    rates = re.findall(r"\d+/\d+", r["statement"])
    assert rates == ["100/214"]  # the headline is the only n/d figure in the statement


def test_aw_primary_counted_separately():
    r = breakdown(_score(pca_only=120, no_prop=IDS[:50], aw=IDS[200:202]), {}, _expl())
    assert r["breakdown"]["aw_primary"]["n"] == 2 and r["breakdown"]["wrong_pca"]["n"] == 42


@pytest.mark.parametrize("bad", [
    {"rule_id": "other"},
    {"denominator": 213},
    {"STOPPED": "key anomaly"},
])
def test_refuses_non_committed_or_stopped_runs(bad):
    with pytest.raises(SystemExit):
        breakdown({**_score(), **bad}, {}, _expl())


def test_refuses_abstention_without_reason():
    e = _expl()
    e[IDS[0]]["abstain_reason"] = None
    with pytest.raises(SystemExit):
        breakdown(_score(), {}, e)


def test_refuses_inconsistent_counts():
    with pytest.raises(SystemExit):
        breakdown(_score(x=130, pca_only=120), {}, _expl())  # X cannot exceed PCA-only


def test_scorer_output_shape_still_matches():
    src = (ROOT / "tools" / "score_heldout.py").read_text(encoding="utf-8")
    for k in ("X_strict", "denominator", "pca_only_match", "no_proposal", "advanced_wireless",
              "ai_pca_proposed_for_suffix_key"):
        assert re.search(rf'"{k}"', src), k


def test_report_tool_never_reads_the_key():
    src = (ROOT / "tools" / "report_heldout.py").read_text(encoding="utf-8")
    assert "--key" not in src and "load_key" not in src
