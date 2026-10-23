"""S8: the behavioural scramble proof of input boundary 1 (offline; the held-out key is never read).

The key case is the leaky engines below. They pass the static S6 scan, because they never
name a suggestion column and get the fixture path only as an argument, yet S8 catches them.
That is why the static scan is necessary but not sufficient.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_build_sweep import FIXTURE, HONEST_ENGINE, _meta_ok, _props, _synthetic, _tree  # noqa: E402

_ENGINE_HEAD = '''
import argparse, csv, sys
from pathlib import Path
ap = argparse.ArgumentParser(); ap.add_argument("--fixture", type=Path); ap.add_argument("--out-dir", type=Path)
ap.add_argument("--offline", action="store_true"); a = ap.parse_args()
rows = list(csv.reader(a.fixture.open(newline="", encoding="utf-8-sig")))
h, body = rows[0], rows[1:]
'''
# Leak 1: finds the first assist column by prefix (no digit, so S6's regex can't see it) and echoes it.
LEAKY_SUGGESTION = _ENGINE_HEAD + '''
j = next(i for i, c in enumerate(h) if c.lower().startswith("sugg"))
k = h.index("Appl ID")
out = "".join(f"{r[k].strip()},{'ACNS' if r[j] else ''},false,\\n" for r in body)
(a.out_dir / "proposals.csv").write_text("appl_id,primary_pca,ai_relevant,sub_pca\\n" + out)
(a.out_dir / "explanations.jsonl").write_text("")
'''
# Leak 2: reads a non-suggestion, non-identity column (the fixture's own title).
LEAKY_TITLE = _ENGINE_HEAD + '''
j, k = h.index("Project Title"), h.index("Appl ID")
out = "".join(f"{r[k].strip()},{'AI' if 'learn' in r[j].lower() else ''},{'true' if 'learn' in r[j].lower() else 'false'},\\n" for r in body)
(a.out_dir / "proposals.csv").write_text("appl_id,primary_pca,ai_relevant,sub_pca\\n" + out)
(a.out_dir / "explanations.jsonl").write_text("")
'''
# Leak 3: labels are clean (identity only) but the EXPLANATION quotes a forbidden column.
LEAKY_EXPLANATION = _ENGINE_HEAD + '''
k, j = h.index("Appl ID"), h.index("PO Name")
(a.out_dir / "proposals.csv").write_text("appl_id,primary_pca,ai_relevant,sub_pca\\n" + "".join(f"{r[k].strip()},,false,\\n" for r in body))
(a.out_dir / "explanations.jsonl").write_text("".join(f'{{"appl_id": {r[k].strip()}, "note": "{r[j]}"}}\\n' for r in body))
'''
NO_EXPLANATIONS = HONEST_ENGINE.replace('(a.out_dir / "explanations.jsonl")', '(a.out_dir / "unused.txt")')
MODEL_CLIENT = "import requests\n" + HONEST_ENGINE
CACHE_MISS = "import sys\nsys.exit('offline cache miss for appl_id 1')\n"


def _run(t, freeze=False, proposals=None):
    rec = t / "rec.json"
    cmd = [sys.executable, str(t / "tools" / "build_sweep.py"), "--tree", str(t),
           "--fixture", str(t / "fixtures" / FIXTURE.name), "--out", str(rec)]
    if proposals is not None:
        p = t / "proposals" / "proposals.csv"
        p.write_text(proposals)
        cmd += ["--proposals", str(p)]
    if freeze:
        cmd.append("--freeze")
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r, json.loads(rec.read_text())["checks"]


def test_no_engine_is_not_run_in_build_and_fails_freeze(tmp_path):
    r, c = _run(_tree(tmp_path))
    assert r.returncode == 0 and c["S8_scramble_proof"]["status"] == "NOT_RUN"
    r, c = _run(_tree(tmp_path / "f"), freeze=True)
    assert r.returncode == 1 and c["S8_scramble_proof"]["status"] == "FAIL"


def test_honest_engine_passes_and_scramble_is_real(tmp_path):
    r, c = _run(_tree(tmp_path, {"engine/run.py": HONEST_ENGINE}))
    s8 = c["S8_scramble_proof"]
    assert r.returncode == 0 and s8["status"] == "PASS" and s8["A_equals_B"], s8
    assert {"suggestion_1", "suggestion_2", "Project Title", "Category", "PCC"} <= set(s8["scrambled_columns"])
    assert s8["cells_changed"] > 480 * 5


@pytest.mark.parametrize("engine", [LEAKY_SUGGESTION, LEAKY_TITLE], ids=["suggestion-by-prefix", "fixture-title"])
def test_leaky_engine_passes_s6_but_fails_s8(tmp_path, engine):
    r, c = _run(_tree(tmp_path, {"engine/run.py": engine}))
    assert c["S6_input_boundary"]["status"] == "PASS"  # the static scan is fooled...
    assert c["S8_scramble_proof"]["status"] == "FAIL"  # ...the behavioural proof is not
    assert c["S8_scramble_proof"]["A_equals_B"] is False and r.returncode == 1


def test_explanation_leak_fails_s8_even_with_identical_labels(tmp_path):
    r, c = _run(_tree(tmp_path, {"engine/run.py": LEAKY_EXPLANATION}))
    s8 = c["S8_scramble_proof"]
    assert s8["proposals.csv"]["A_equals_B"] is True and s8["explanations.jsonl"]["A_equals_B"] is False
    assert s8["status"] == "FAIL" and r.returncode == 1


def test_missing_explanations_fails_s8(tmp_path):
    r, c = _run(_tree(tmp_path, {"engine/run.py": NO_EXPLANATIONS}))
    assert r.returncode == 1 and c["S8_scramble_proof"]["status"] == "FAIL"
    assert "A/explanations.jsonl" in c["S8_scramble_proof"]["missing_outputs"]


def test_model_or_network_import_fails_s6(tmp_path):
    r, c = _run(_tree(tmp_path, {"engine/run.py": MODEL_CLIENT}))
    assert r.returncode == 1 and c["S6_input_boundary"]["status"] == "FAIL"


def test_engine_failure_fails_s8(tmp_path):
    r, c = _run(_tree(tmp_path, {"engine/run.py": CACHE_MISS}))
    assert r.returncode == 1 and c["S8_scramble_proof"]["status"] == "FAIL"


def test_freeze_passes_when_frozen_equals_engine_output(tmp_path):
    r, c = _run(_tree(tmp_path, _meta_ok()), freeze=True, proposals=_props(_synthetic()))
    assert r.returncode == 0 and c["S8_scramble_proof"]["frozen_equals_A"] is True, c


def test_freeze_fails_when_frozen_file_was_hand_edited(tmp_path):
    rows = _synthetic()
    rows[0] = (rows[0][0], "CSP", "true", "")  # still valid for S3-S5; just not what the engine produced
    r, c = _run(_tree(tmp_path, _meta_ok()), freeze=True, proposals=_props(rows))
    for k in ("S3_proposal_validation", "S4_coverage", "S5_format_v2", "S7_output_label"):
        assert c[k]["status"] == "PASS", (k, c[k])
    assert c["S8_scramble_proof"]["frozen_equals_A"] is False and r.returncode == 1
