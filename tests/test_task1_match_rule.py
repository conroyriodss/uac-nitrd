"""The committed Task 1 match rule stays pinned to its inputs, and the baseline agrees with its definitions."""
import collections
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


# ---- v4 (supersedes v1, v2, v3 for scoring; one rule change: primary-only core dollars) ----
RULE_V4 = ROOT / "docs" / "TASK1_MATCH_RULE_v4.md"
RULE_V4_ID = "nitrd-parent-match-rule-v4-2026-10-25"
# Pinned at commit. Editing v4 means a new rule ID, a new pin, and a seal-log note.
RULE_V4_SHA256 = "2741cc0f23ec7285e9671ea64d802c2a97f4324ad28003d2488d274dd72a2cdd"
_V3_SHA = "5f31cadecfa514f2478336c333e1ba0941dae5cac476ec0d3d96030fc2ae0a99"
_V2_SHA = "93195c0a86d0652f55c7c77f66dfea3195fc8d73d5ffe4bf8460e278f674cbe5"
# Every v3 -> v4 edit. Applying exactly these to v3 must reproduce v4 byte for byte.
V3_TO_V4 = [
    ("# Task 1 match rule: `nitrd-parent-match-rule-v3-2026-10-25`",
     "# Task 1 match rule: `nitrd-parent-match-rule-v4-2026-10-25`"),
    ("It\nSUPERSEDES v1 and v2 for scoring. Both stay in the repo unchanged: v1 because the FY2024 seal manifest\n"
     "records its SHA, v2 because it was committed.\n",
     "It\nSUPERSEDES v1, v2 and v3 for scoring. All three stay in the repo unchanged: v1 because the FY2024 seal\n"
     "manifest records its SHA, v2 and v3 because they were committed.\n"),
    (f"* v2 = `docs/TASK1_MATCH_RULE_v2.md`, sha256 `{_V2_SHA}`\n",
     f"* v2 = `docs/TASK1_MATCH_RULE_v2.md`, sha256 `{_V2_SHA}`\n"
     f"* v3 = `docs/TASK1_MATCH_RULE_v3.md`, sha256 `{_V3_SHA}`\n"),
    ("must record\nthat v3 supersedes v1. Any later change is a new rule version with a new ID.\n",
     "must record\nthat v4 supersedes v1. Any later change is a new rule version with a new ID.\n\n"
     "**Only rule change from v3:** in section 6, core dollars are the sum of `award_amount` over primary\n"
     "(non-subproject) records only. Everything else is v3 verbatim, apart from this header, the section 0 pins\n"
     "(v3 added as superseded; the FY2024 amounts file added) and the supersession references in sections 5\n"
     "and 10.\n"),
    (f"| `docs/TASK1_MATCH_RULE_v2.md` (v2, superseded) | `{_V2_SHA}` |\n",
     f"| `docs/TASK1_MATCH_RULE_v2.md` (v2, superseded) | `{_V2_SHA}` |\n"
     f"| `docs/TASK1_MATCH_RULE_v3.md` (v3, superseded) | `{_V3_SHA}` |\n"
     "| `build/amounts/fy2024_amounts.v1.csv` | `090397b3a3822e5fb45a190a7c3b33553fddfcec6a7f798092aac43e8dbefae8` |\n"),
    ("  * the seal log not recording the supersession to v3.\n",
     "  * the seal log not recording the supersession to v4.\n"),
    ("Each core is weighted by the sum of FY2024 `award_amount`\n  across its records, in place of 1.\n",
     "Each core is weighted by the sum of FY2024 `award_amount`\n"
     "  across its primary (non-subproject) records only, in place of 1. A subproject's amount is contained in\n"
     "  its parent award, so subproject amounts are never added. (v4 change: v3 summed every record, which\n"
     "  overstates the universe total by 10.4%, $47,167,811,504 vs $42,731,736,160 in the pinned amounts file.)\n"),
    ("* The FY2024 amounts file and its SHA (label-free).\n* The seal-log entry recording the supersession to v3.\n",
     "* The FY2024 amounts file and its SHA (label-free): committed, pinned in section 0.\n"
     "* The seal-log entry recording the supersession to v4.\n"),
]


def test_v4_is_v3_plus_exactly_the_listed_edits():
    text = (ROOT / "docs" / "TASK1_MATCH_RULE_v3.md").read_text(encoding="utf-8")
    for old, new in V3_TO_V4:
        assert text.count(old) == 1, old[:60]
        text = text.replace(old, new)
    assert text == RULE_V4.read_text(encoding="utf-8")


def test_v4_is_the_committed_version():
    text = RULE_V4.read_text(encoding="utf-8")
    assert text.splitlines()[0] == f"# Task 1 match rule: `{RULE_V4_ID}`"
    assert sha256(RULE_V4) == RULE_V4_SHA256
    for prior in ("154a26e4e2253aadee611c92864c184a9d10390d88bf0fd2636ad42e1a119123", _V2_SHA, _V3_SHA):
        assert prior in text
    assert sha256(ROOT / "docs" / "TASK1_MATCH_RULE_v3.md") == _V3_SHA          # v3 untouched


def test_v4_pins_match_the_files():
    pins = dict(re.findall(r"^\| `([^`]+)`[^|]*\| `([0-9a-f]{64})` \|$", RULE_V4.read_text(encoding="utf-8"), re.M))
    assert len(pins) == 11
    for rel, want in pins.items():
        assert sha256(ROOT / rel) == want, rel


def test_v4_primary_only_dollars_from_the_pinned_files():
    with (ROOT / "build" / "universe" / "fy2024_identity.csv").open(newline="") as f:
        primary = {r["appl_id"] for r in csv.DictReader(f) if not r["subproject_id"]}
    total = every = 0
    with (ROOT / "build" / "amounts" / "fy2024_amounts.v1.csv").open(newline="") as f:
        for r in csv.DictReader(f):
            a = int(r["award_amount"] or 0)
            every += a
            total += a if r["appl_id"] in primary else 0
    assert (total, every) == (42_731_736_160, 47_167_811_504)
    assert "$47,167,811,504 vs $42,731,736,160" in RULE_V4.read_text(encoding="utf-8")


# ---- v3 (supersedes v1 and v2 for scoring) ----
RULE_V3 = ROOT / "docs" / "TASK1_MATCH_RULE_v3.md"
RULE_V3_ID = "nitrd-parent-match-rule-v3-2026-10-25"
RULE_V3_SHA256 = "5f31cadecfa514f2478336c333e1ba0941dae5cac476ec0d3d96030fc2ae0a99"


def rcdc_view_keep(row: dict) -> bool:
    """Section 2 RCDC-view filter, exactly as written in v3 (identity columns only)."""
    a = row["core_project_num"][:3]
    contract = a == "75N" or a.startswith("HHS") or bool(re.match(r"^N\d\d$", a)) or a[:1].isdigit()
    return not row["subproject_id"] and not a.startswith("Z") and not contract and not a.startswith("OT")


def test_v3_is_the_committed_version_and_supersedes_v1_v2():
    text = RULE_V3.read_text(encoding="utf-8")
    assert text.splitlines()[0] == f"# Task 1 match rule: `{RULE_V3_ID}`"
    assert sha256(RULE_V3) == RULE_V3_SHA256
    assert RULE_SHA256 in text and RULE_V2_SHA256 in text
    assert sha256(RULE) == RULE_SHA256 and sha256(RULE_V2) == RULE_V2_SHA256      # superseded files untouched


def test_v3_pins_match_the_files():
    pins = dict(re.findall(r"^\| `([^`]+)`[^|]*\| `([0-9a-f]{64})` \|$", RULE_V3.read_text(encoding="utf-8"), re.M))
    assert len(pins) == 9
    for rel, want in pins.items():
        assert sha256(ROOT / rel) == want, rel


def test_v3_rcdc_view_filter_reproduces_the_stated_fy2023_counts():
    with (ROOT / "build" / "universe" / "fy2023.csv").open(newline="") as f:
        pos = [r for r in csv.DictReader(f) if r["cat329"] == "1"]            # build-year labels
    kept = [r for r in pos if rcdc_view_keep(r)]
    assert (len(pos), len({r["core_project_num"] for r in pos})) == (4583, 4104)
    assert (len(kept), len({r["core_project_num"] for r in kept})) == (3407, 3241)
    assert "3,407 records in 3,241 cores" in RULE_V3.read_text(encoding="utf-8")


def test_v3_uac_worklist_spans_instruments_outside_the_rcdc_view():
    with (ROOT / "fixtures" / "UAC_Uncoded_12-01-2025-updated-NIH_ODSS.csv").open(newline="", encoding="utf-8-sig") as f:
        fx = list(csv.DictReader(f))
    cls = collections.Counter(r["Class Code"] for r in fx)
    assert (cls["C"], cls["M"], cls["O"], cls["I"]) == (15, 9, 45, 1)
    assert sum(bool(r["SubProj"].strip()) for r in fx) == 81


# ---- FY2024 amounts (v3 section 10: committed with or before the scorer; label-free) ----
AMOUNTS = ROOT / "build" / "amounts" / "fy2024_amounts.v1.csv"
AMOUNTS_SHA256 = "090397b3a3822e5fb45a190a7c3b33553fddfcec6a7f798092aac43e8dbefae8"
AMOUNTS_MANIFEST = AMOUNTS.with_name("fy2024_amounts.v1.manifest.json")


def test_fy2024_amounts_pinned_label_free_and_cover_the_sealed_universe():
    assert sha256(AMOUNTS) == AMOUNTS_SHA256
    m = json.loads(AMOUNTS_MANIFEST.read_text())
    assert m["output"]["sha256"] == AMOUNTS_SHA256
    assert m["labels_requested"] is False and m["text_requested"] is False
    assert m["request"]["include_fields"] == ["ApplId", "AwardAmount"]
    assert set(m["request"]["criteria_keys"]) == {"agencies", "fiscal_years"}
    with AMOUNTS.open(newline="") as f:
        rd = csv.DictReader(f)
        assert rd.fieldnames == ["appl_id", "award_amount"]          # no label or text column
        ids = [int(r["appl_id"]) for r in rd]
    with (ROOT / "build" / "universe" / "fy2024_identity.csv").open(newline="") as f:
        sealed = {int(r["appl_id"]) for r in csv.DictReader(f)}
    assert ids == sorted(sealed)


def test_amounts_tool_refuses_label_or_text_requests():
    import pytest
    sys.path.insert(0, str(ROOT / "tools"))
    import pull_fy2024_amounts as p
    for bad in ({"criteria": {"fiscal_years": [2024], "spending_categories": {"values": [329]}},
                 "include_fields": ["ApplId", "AwardAmount"]},
                {"criteria": {"fiscal_years": [2024]}, "include_fields": ["ApplId", "AwardAmount", "SpendingCategories"]},
                {"criteria": {"fiscal_years": [2024]}, "include_fields": ["ApplId", "AbstractText"]}):
        with pytest.raises(SystemExit):
            p.check_body(bad)
