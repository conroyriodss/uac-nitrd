"""reveal-constants-v1: the committed pre-reveal record must match the engine exactly."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REC = ROOT / "docs" / "REVEAL_CONSTANTS.json"


def test_record_matches_engine():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "reveal_constants.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_record_is_scope_only():
    rec = json.loads(REC.read_text(encoding="utf-8"))
    assert rec["vocabulary"] == "vocabulary-scope-only-2026-10-24"
    assert rec["synonyms_added"] == 0 and rec["synonyms_path"] is None
    c = rec["constants"]
    assert c["PCA_THRESHOLD"] == 1.0 and c["PHRASE_BONUS"] == 3.0 and c["AI_GATE_MIN_TERMS"] == 1
    assert len(c["AI_GATE_CORE"]) == 10


def test_record_lists_no_synonym_file():
    assert not any("synonym" in p for p in json.loads(REC.read_text(encoding="utf-8"))["input_sha256"])
