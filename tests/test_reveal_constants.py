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
    assert rec["record_id"] == "reveal-constants-v2-2026-10-24"
    assert rec["vocabulary"] == "vocabulary-scope-only-2026-10-24" and rec["synonyms_path"] is None
    c = rec["constants"]
    assert c["PCA_THRESHOLD"] == 1.0 and c["PHRASE_BONUS"] == 3.0 and c["AI_GATE_MIN_TERMS"] == 1
    assert len(c["AI_GATE_CORE"]) == 10


def test_record_holds_no_engine_output_and_pins_the_guard():
    """Freeze order: output hashes come only from the freeze run, never from the constants record."""
    rec = json.loads(REC.read_text(encoding="utf-8"))
    assert not any("output" in k for k in rec)
    assert "engine/freeze_guard.py" in rec["input_sha256"]
    g = rec["freeze_guard_constants"]
    assert g["GUARD_ID"] == "freeze-guard-v1-2026-10-24" and g["GUARD_EXIT"] == 3
    assert g["FREEZE_ENV"] == "UAC_NITRD_FREEZE_RUN"


def test_reveal_constants_never_runs_the_engine():
    src = (ROOT / "tools" / "reveal_constants.py").read_text(encoding="utf-8")
    assert "subprocess" not in src and "--fixture" not in src and "--offline" not in src


def test_record_lists_no_synonym_file():
    assert not any("synonym" in p for p in json.loads(REC.read_text(encoding="utf-8"))["input_sha256"])
