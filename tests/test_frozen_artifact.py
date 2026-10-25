"""S9 frozen artifact: post-freeze CI verifies the frozen proposals by hash, never by re-running.

Each test copies the repo (test trees exclude the frozen outputs) and then puts the REAL frozen
files back, optionally tampering one thing. The engine in the tree still refuses the 480
(S8 GUARDED), so no test runs the engine on the evaluation projects.
"""
import json
import shutil
import sys

from test_build_sweep import FIXTURE, ROOT, _tree
import subprocess

FROZEN = ("proposals.csv", "explanations.jsonl", "proposals.meta.json", "FREEZE_SWEEP.json")


def _frozen_tree(tmp_path):
    t = _tree(tmp_path)
    for n in FROZEN:
        shutil.copy2(ROOT / "proposals" / n, t / "proposals" / n)
    return t


def _build_sweep(t):
    rec = t.parent / "rec.json"
    r = subprocess.run([sys.executable, str(t / "tools" / "build_sweep.py"), "--tree", str(t),
                        "--fixture", str(t / "fixtures" / FIXTURE.name),
                        "--proposals", str(t / "proposals" / "proposals.csv"), "--out", str(rec)],
                       capture_output=True, text=True)
    return r, json.loads(rec.read_text())["checks"]


def test_s9_passes_on_the_frozen_artifact_with_engine_guarded(tmp_path):
    r, c = _build_sweep(_frozen_tree(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert c["S8_scramble_proof"]["status"] == "GUARDED"
    assert c["S9_frozen_artifact"]["status"] == "PASS", c["S9_frozen_artifact"]


def test_s9_not_run_before_the_freeze(tmp_path):
    t = _tree(tmp_path)
    shutil.copy2(ROOT / "proposals" / "proposals.csv", t / "proposals" / "proposals.csv")
    shutil.copy2(ROOT / "proposals" / "proposals.meta.json", t / "proposals" / "proposals.meta.json")
    _, c = _build_sweep(t)
    assert c["S9_frozen_artifact"]["status"] == "NOT_RUN"


def test_s9_fails_if_a_frozen_proposal_is_edited(tmp_path):
    t = _frozen_tree(tmp_path)
    p = t / "proposals" / "proposals.csv"
    lines = p.read_text().splitlines(keepends=True)
    lines[1] = lines[1].replace(",false,", ",true,", 1) if ",false," in lines[1] else lines[1].replace(",true,", ",false,", 1)
    p.write_text("".join(lines))
    r, c = _build_sweep(t)
    assert r.returncode == 1 and c["S9_frozen_artifact"]["status"] == "FAIL"
    assert any("proposals.csv" in x for x in c["S9_frozen_artifact"]["problems"])


def test_s9_fails_if_an_engine_constant_changes(tmp_path):
    t = _frozen_tree(tmp_path)
    run = t / "engine" / "run.py"
    run.write_text(run.read_text().replace("PCA_THRESHOLD = 1.0", "PCA_THRESHOLD = 0.5", 1))
    r, c = _build_sweep(t)
    assert r.returncode == 1 and c["S9_frozen_artifact"]["status"] == "FAIL"
    assert any("REVEAL_CONSTANTS" in x for x in c["S9_frozen_artifact"]["problems"])


def test_s9_fails_if_the_freeze_record_is_not_a_pass(tmp_path):
    t = _frozen_tree(tmp_path)
    f = t / "proposals" / "FREEZE_SWEEP.json"
    rec = json.loads(f.read_text())
    rec["verdict"] = "FAIL"
    f.write_text(json.dumps(rec))
    r, c = _build_sweep(t)
    assert r.returncode == 1 and c["S9_frozen_artifact"]["status"] == "FAIL"
