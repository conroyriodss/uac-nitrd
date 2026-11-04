"""fixture-correction chain: records pinned, fixture at the last corrected hash, no PCC / PO Name."""
import csv
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import fixture_correction as fc  # noqa: E402


def test_records_are_pinned_and_fixture_is_corrected():
    v1, v2 = fc.load_all()
    assert v1["path"] == v2["path"] and v2["superseded_sha256"] == v1["corrected_sha256"]
    fx = ROOT / v2["path"]
    assert hashlib.sha256(fx.read_bytes()).hexdigest() == v2["corrected_sha256"] == fc.current(v2["path"])
    with fx.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    assert "PCC" not in rows[0] and "PO Name" not in rows[0]
    assert len(rows) == 481 and {len(r) for r in rows} == {11}


def test_only_the_chain_from_the_superseded_fixture_hash_is_mapped():
    v1, v2 = fc.load_all()
    p, s0, s1, s2 = v1["path"], v1["superseded_sha256"], v1["corrected_sha256"], v2["corrected_sha256"]
    assert fc.accepted(p, s0) == {s0, s1, s2}
    assert fc.accepted(p, s1) == {s1, s2}
    assert fc.accepted(p, s2) == {s2}
    assert fc.accepted(p, "0" * 64) == {"0" * 64}
    assert fc.accepted("engine/run.py", s0) == {s0}


def test_frozen_records_still_cite_the_superseded_hash():
    c = fc.load()
    final = fc.current(c["path"])
    for rel in ("docs/REVEAL_CONSTANTS.json", "docs/TASK1_MATCH_RULE_v3.md", "docs/TASK1_MATCH_RULE_v4.md"):
        t = (ROOT / rel).read_text(encoding="utf-8")
        assert c["superseded_sha256"] in t and c["corrected_sha256"] not in t and final not in t, rel
