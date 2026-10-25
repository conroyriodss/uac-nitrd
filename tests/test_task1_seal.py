"""Task 1 FY2024 seal boundary: sealed key unreadable from the build path, text snapshot freeze-run only."""
import csv
import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import load_proposals as lp  # noqa: E402
from workflow import sealed  # noqa: E402
from workflow.baseline import load_universe  # noqa: E402
from workflow.common import load_cache, load_dev_refs, sha256  # noqa: E402

RULE_SHA = "154a26e4e2253aadee611c92864c184a9d10390d88bf0fd2636ad42e1a119123"
MANIFEST_SHA = "ae63372d8e34402aeb2e5f2c7338530cbf106a059b6a0fe74461e8e2f33b9b41"


@pytest.fixture()
def sealed_dir(tmp_path):
    d = tmp_path / "vol" / "task1_fy2024"
    d.mkdir(parents=True)
    (d / "TASK1_SEAL_RECORD.json").write_text("{}")
    key = d / "key.csv"
    key.write_text("appl_id,core_project_num,cat329,stratum,filea_exposed,record_sha256\n1,X,1,new,0,ab\n")
    return key


def test_every_build_path_loader_refuses_a_sealed_location(sealed_dir, tmp_path):
    for fn in (load_universe, load_cache, load_dev_refs):
        with pytest.raises(sealed.SealBoundaryError, match="sealed location"):
            fn(sealed_dir)
    with pytest.raises(sealed.SealBoundaryError):
        lp.build_listing(sealed_dir, sealed_dir, None)
    # a marker in an ancestor also seals descendants
    up = tmp_path / "vol2"
    (up / "sub").mkdir(parents=True)
    (up / "SEAL_MANIFEST.json").write_text("{}")
    (up / "sub" / "k.csv").write_text("x\n")
    with pytest.raises(sealed.SealBoundaryError):
        load_universe(up / "sub" / "k.csv")


def test_sealed_key_reader_is_scoring_only(sealed_dir):
    with pytest.raises(sealed.SealBoundaryError, match="scoring run"):
        sealed.open_sealed_key(sealed_dir, env={})
    assert sealed.open_sealed_key(sealed_dir, env={sealed.SCORE_ENV: "1"}).startswith("appl_id")


def test_build_path_loaders_refuse_the_text_snapshot():
    shard = ROOT / sealed.manifest()["text_snapshot"]["shards"][0]["file"]
    for fn in (load_cache, load_universe, load_dev_refs):
        with pytest.raises(sealed.SealBoundaryError, match="freeze run"):
            fn(shard)


def test_text_snapshot_is_freeze_run_only():
    assert sealed.text_access_problems(freeze_env=True, porcelain="") == []
    assert sealed.text_access_problems(freeze_env=False, porcelain="")
    assert sealed.text_access_problems(freeze_env=True, porcelain=" M cache/x\n")
    assert sealed.text_access_problems(freeze_env=True, porcelain=None)
    with pytest.raises(sealed.SealBoundaryError, match="freeze run only"):
        sealed.load_score_text(env={})


def test_manifest_and_snapshot_match_the_seal():
    assert sha256(sealed.SEAL_MANIFEST) == MANIFEST_SHA
    m = sealed.manifest()
    assert m["match_rule"] == {"id": "nitrd-parent-match-rule-v1-2026-10-25", "file": "docs/TASK1_MATCH_RULE.md",
                               "sha256": RULE_SHA} and sha256(ROOT / m["match_rule"]["file"]) == RULE_SHA
    assert sealed.verify_snapshot() == {"shards": 16, "records": 79721}
    assert m["text_snapshot"]["query"]["category_criteria_or_fields"] == "none"
    assert m["sealed_key"]["label_counts"] == "not recorded outside the sealed key"
    assert m["fy2024_label_reads_before_seal"][0]["entry"] == 1
    assert "carry-forward" in m["fy2024_label_reads_before_seal"][0]["what"]
    assert m["identity_aggregates"]["vs_committed_fy2024_identity"] == {"only_in_seal": 0, "only_in_committed": 0}
    g = m["identity_aggregates"]["cores_by_group"]
    assert g["new|filea_exposed=0"] + g["new|filea_exposed=1"] == 15472     # agrees with the committed baseline
    assert m["abstentions"]["count"] == len(m["abstentions"]["appl_ids"])


def test_no_repo_file_is_or_carries_the_sealed_key():
    key_sha = sealed.manifest()["sealed_key"]["aggregate_sha256"]
    skip = {".git", "__pycache__", ".pytest_cache"}
    for p in ROOT.rglob("*"):
        if not p.is_file() or skip & set(p.relative_to(ROOT).parts):
            continue
        assert hashlib.sha256(p.read_bytes()).hexdigest() != key_sha, p
        if p.suffix == ".csv":
            with p.open(newline="", encoding="utf-8", errors="replace") as f:
                r = csv.DictReader(f)
                if r.fieldnames and "cat329" in r.fieldnames:
                    assert all(row.get("fy") != "2024" for row in r), f"{p}: FY2024 rows with a label column"


def test_only_the_boundary_module_names_the_text_snapshot():
    hits = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*.py")
            if "tests" not in p.relative_to(ROOT).parts and "task1_fy2024_text" in p.read_text(encoding="utf-8")]
    assert hits == ["workflow/sealed.py"]
