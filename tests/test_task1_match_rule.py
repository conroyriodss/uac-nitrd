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


# ---- v2 (supersedes v1 for scoring; v1 stays pinned because the FY2024 seal records it) ----
RULE_V2 = ROOT / "docs" / "TASK1_MATCH_RULE_v2.md"
RULE_V2_ID = "nitrd-parent-match-rule-v2-2026-10-25"
RULE_V2_SHA256 = "93195c0a86d0652f55c7c77f66dfea3195fc8d73d5ffe4bf8460e278f674cbe5"
RULE67 = ("F37", "F38", "G07", "G08")


def test_v2_is_the_committed_version_and_supersedes_v1():
    text = RULE_V2.read_text(encoding="utf-8")
    assert text.splitlines()[0] == f"# Task 1 match rule: `{RULE_V2_ID}`"
    assert sha256(RULE_V2) == RULE_V2_SHA256
    assert RULE_ID in text and RULE_SHA256 in text           # names exactly what it supersedes
    seal = json.loads((ROOT / "docs" / "seal" / "task1_fy2024_seal_manifest.json").read_text())
    assert seal["match_rule"]["sha256"] == RULE_SHA256        # the seal still records v1, unchanged


def test_v2_pins_match_the_files():
    pins = dict(re.findall(r"^\| `([^`]+)`[^|]*\| `([0-9a-f]{64})` \|$", RULE_V2.read_text(encoding="utf-8"), re.M))
    assert len(pins) == 7
    for rel, want in pins.items():
        assert sha256(ROOT / rel) == want, rel


def test_v2_rule67_identity_count_matches_the_committed_universe():
    with (ROOT / "build" / "universe" / "fy2024_identity.csv").open(newline="") as f:
        sel = [r for r in csv.DictReader(f) if r["core_project_num"][:3] in RULE67]
    assert (len(sel), len({r["core_project_num"] for r in sel})) == (10, 9)
    assert "10 records in 9 cores, all G08" in RULE_V2.read_text(encoding="utf-8")
