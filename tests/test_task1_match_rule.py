"""The committed Task 1 match rule stays pinned to its inputs, and the baseline agrees with its definitions."""
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow.common import sha256  # noqa: E402

RULE = ROOT / "docs" / "TASK1_MATCH_RULE.md"
RULE_ID = "nitrd-parent-match-rule-v1-2026-10-25"
# Pinned at commit. Editing the rule means a new rule ID, a new pin, and a seal-log note.
RULE_SHA256 = "154a26e4e2253aadee611c92864c184a9d10390d88bf0fd2636ad42e1a119123"


def _pins() -> dict[str, str]:
    return dict(re.findall(r"^\| `([^`]+)` \| `([0-9a-f]{64})` \|$", RULE.read_text(encoding="utf-8"), re.M))


def test_rule_file_is_the_committed_version():
    text = RULE.read_text(encoding="utf-8")
    assert text.splitlines()[0] == f"# Task 1 match rule: `{RULE_ID}`"
    assert sha256(RULE) == RULE_SHA256


def test_pinned_inputs_match_the_files():
    pins = _pins()
    assert set(pins) == {"build/universe/fy2021.csv", "build/universe/fy2022.csv", "build/universe/fy2023.csv",
                         "build/universe/fy2024_identity.csv",
                         "build/baseline/carry_forward_fy2024.predictions.csv"}
    for rel, want in pins.items():
        assert sha256(ROOT / rel) == want, rel
    meta = json.loads((ROOT / "build" / "baseline" / "carry_forward_fy2024.predictions.meta.json").read_text())
    assert meta["predictions_sha256"] == pins["build/baseline/carry_forward_fy2024.predictions.csv"]
    assert meta["prior_fys"] == [2021, 2022, 2023]


def test_baseline_new_group_is_no_record_in_fy2021_2023():
    prior = set()
    for fy in (2021, 2022, 2023):
        with (ROOT / "build" / "universe" / f"fy{fy}.csv").open(newline="") as f:
            prior |= {r["core_project_num"] for r in csv.DictReader(f)}
    with (ROOT / "build" / "baseline" / "carry_forward_fy2024.predictions.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    strata = {}
    for r in rows:
        strata.setdefault(r["core_project_num"], r["stratum"])
        assert strata[r["core_project_num"]] == r["stratum"]          # one stratum per core
    assert all((s == "new") == (c not in prior) for c, s in strata.items())
    assert sum(s == "new" for s in strata.values()) == 15472
    assert all(r["prediction"] == "0" for r in rows if r["stratum"] == "new")
