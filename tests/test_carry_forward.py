"""Carry-forward baseline and Task 1 build universe. DEV / not scored."""
import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import build_universe as bu  # noqa: E402
import carry_forward_baseline as cfb  # noqa: E402
from workflow.baseline import core_labels, evaluate, predict  # noqa: E402
from workflow.common import DevBoundaryError, sha256  # noqa: E402


def R(appl, fy, core, y=None):
    r = {"appl_id": appl, "fy": fy, "core_project_num": core}
    if y is not None:
        r["cat329"] = y
    return r


def test_most_recent_prior_label_wins_and_new_is_zero():
    prior = {2021: {"A": 1, "B": 0, "C": 1}, 2022: {"A": 0, "B": 1}}
    p = predict([R(1, 2023, "A"), R(2, 2023, "B"), R(3, 2023, "C"), R(4, 2023, "D"), R(5, 2023, "D")], prior)
    c = p["cores"]
    assert (c["A"]["prediction"], c["A"]["source_fy"]) == (0, 2022)       # 2022 overrides 2021
    assert (c["B"]["prediction"], c["B"]["source_fy"]) == (1, 2022)
    assert (c["C"]["prediction"], c["C"]["source_fy"], c["C"]["stratum"]) == (1, 2021, "continuing")  # gap year
    assert (c["D"]["prediction"], c["D"]["stratum"], c["D"]["source_fy"]) == (0, "new", None)
    assert p["appls"][5]["prediction"] == 0 and p["appls"][2]["prediction"] == 1   # appl inherits its core


def test_core_label_any_rule_and_metrics_by_stratum():
    assert core_labels([R(1, 2023, "A", 0), R(2, 2023, "A", 1), R(3, 2023, "B", 0)]) == {"A": 1, "B": 0}
    tgt = [R(1, 2023, "A", 1), R(2, 2023, "B", 1), R(3, 2023, "C", 0), R(4, 2023, "N", 1)]
    p = predict([{k: r[k] for k in ("appl_id", "fy", "core_project_num")} for r in tgt],
                {2022: {"A": 1, "B": 0, "C": 1}})
    e = evaluate(p, tgt)
    assert (e["core"]["continuing"]["tp"], e["core"]["continuing"]["fn"], e["core"]["continuing"]["fp"]) == (1, 1, 1)
    assert e["core"]["new"]["recall"] == 0.0 and e["core"]["new"]["positives"] == 1
    assert e["continuing_core_flips"] == {"n": 2, "entered_329": 1, "left_329": 1, "baseline_correct_on_flips": 0}


def test_refuses_reserved_fy_labels_and_bad_windows():
    with pytest.raises(DevBoundaryError):
        core_labels([R(1, 2024, "A", 1)])
    p = predict([R(1, 2024, "A")], {2023: {"A": 1}})
    with pytest.raises(DevBoundaryError, match="reserved"):
        evaluate(p, [R(1, 2024, "A", 1)])
    with pytest.raises(ValueError):
        predict([R(1, 2023, "A")], {2023: {"A": 1}})


def test_universe_builder_never_requests_score_fy_labels():
    assert bu.label_allowed(2023) is True and bu.label_allowed(2024) is False
    for fy in (2025, 2019):
        with pytest.raises(bu.UniverseBoundaryError):
            bu.label_allowed(fy)

    class NoNet:
        def post(self, *a, **k):
            raise AssertionError("network must not be reached")
    c = bu.Client(session=NoNet())
    with pytest.raises(bu.UniverseBoundaryError):
        c.post({"fiscal_years": [2024], "spending_categories": {"values": [329], "match_all": False}})


def test_committed_universe_matches_manifest_and_fy2024_is_identity_only():
    man = json.loads((cfb.UNIVERSE / "MANIFEST.json").read_text())
    assert man["universe_id"] == bu.UNIVERSE_ID and man["text_requested"] is False
    assert man["category_requested"] == {"2021": "329 only", "2022": "329 only", "2023": "329 only", "2024": "none"}
    for name, meta in man["files"].items():
        assert sha256(cfb.UNIVERSE / name) == meta["sha256"]
        assert meta["records"] == meta["nih_total_at_pull"]
    with (cfb.UNIVERSE / "fy2024_identity.csv").open() as f:
        assert "cat329" not in next(csv.reader(f))


def test_committed_baseline_outputs_rebuild_and_read_no_fy2024_label():
    assert cfb.main(["--check"]) == 0
    meta = json.loads(cfb.PRED_META.read_text())
    assert meta["fy2024_labels_read"] is False and meta["labels_read"] == ["FY2021", "FY2022", "FY2023"]
    assert sha256(cfb.PRED) == meta["predictions_sha256"]
    back = json.loads(cfb.BACKTEST.read_text())
    assert back["label"].startswith("DEV / not scored") and set(back["backtests"]) == {"FY2023<-FY2021-2022", "FY2022<-FY2021"}
    for bt in back["backtests"].values():
        assert bt["core"]["new"]["tp"] == 0 and bt["core"]["new"]["recall"] == 0.0
