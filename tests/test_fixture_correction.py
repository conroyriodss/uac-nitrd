"""fixture-correction-v1: the record is pinned, the fixture has the corrected hash and no PCC column."""
import csv
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import fixture_correction as fc  # noqa: E402


def test_record_is_pinned_and_fixture_is_corrected():
    c = fc.load()
    fx = ROOT / c["path"]
    assert hashlib.sha256(fx.read_bytes()).hexdigest() == c["corrected_sha256"]
    with fx.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    assert "PCC" not in rows[0] and len(rows) == 481 and {len(r) for r in rows} == {12}


def test_only_the_superseded_fixture_hash_is_mapped():
    c = fc.load()
    assert fc.accepted(c["path"], c["superseded_sha256"]) == {c["superseded_sha256"], c["corrected_sha256"]}
    assert fc.accepted(c["path"], "0" * 64) == {"0" * 64}
    assert fc.accepted("engine/run.py", c["superseded_sha256"]) == {c["superseded_sha256"]}


def test_frozen_records_still_cite_the_superseded_hash():
    c = fc.load()
    for rel in ("docs/REVEAL_CONSTANTS.json", "docs/TASK1_MATCH_RULE_v3.md", "docs/TASK1_MATCH_RULE_v4.md"):
        t = (ROOT / rel).read_text(encoding="utf-8")
        assert c["superseded_sha256"] in t and c["corrected_sha256"] not in t, rel
