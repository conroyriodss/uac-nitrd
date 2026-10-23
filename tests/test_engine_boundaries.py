"""Engine input/output boundary tests (offline, model-free; the held-out key is never read)."""
import csv
import json
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from engine import OUTPUT_LABEL, write_meta  # noqa: E402
from engine.inputs import ALLOWED_COLUMNS, load_project_refs  # noqa: E402
from test_build_sweep import FIXTURE, _props, _sweep, _synthetic, _tree  # noqa: E402


def test_loader_exposes_identity_only():
    refs = load_project_refs(FIXTURE)
    assert len(refs) == 480
    assert set(vars(refs[0])) == {"appl_id", "fy", "project_number", "subproj"}


def test_loader_invariant_to_every_non_identity_column(tmp_path):
    with FIXTURE.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    header, body = rows[0], rows[1:]
    rng = random.Random(7)
    scrambled = []
    for r in body:  # overwrite every column the engine must not see
        scrambled.append([v if h in ALLOWED_COLUMNS else f"X{rng.randint(0, 10**9)}" for h, v in zip(header, r)])
    p = tmp_path / "fx.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([header] + scrambled)
    assert load_project_refs(p) == load_project_refs(FIXTURE)


def test_repo_engine_passes_s6(tmp_path):
    r = _sweep(_tree(tmp_path))
    assert r.returncode == 0 and "S6_input_boundary: PASS" in r.stdout, r.stdout


@pytest.mark.parametrize("rel,text", [
    ("engine/propose.py", 'hint = row["suggestion_1"]\n'),
    ("engine/propose.py", "cols = ['Suggestion 2']\n"),
    ("engine/propose.py", 'open("fixtures/UAC_Uncoded_x.csv")\n'),
    ("engine/notes.md", "use suggestion_2 as a prior\n"),
])
def test_s6_rejects_planted_leaks(tmp_path, rel, text):
    r = _sweep(_tree(tmp_path, {rel: text}))
    assert r.returncode == 1 and "S6_input_boundary: FAIL" in r.stdout


def test_s6_rejects_widened_allow_list(tmp_path):
    t = _tree(tmp_path)
    p = t / "engine" / "inputs.py"
    p.write_text(p.read_text().replace('"SubProj")', '"SubProj", "PCC")'))
    r = _sweep(t)
    assert r.returncode == 1 and "S6_input_boundary: FAIL" in r.stdout


def _freeze_with_meta(tmp_path, meta):
    t = _tree(tmp_path)
    if meta is not None:
        (t / "proposals" / "proposals.meta.json").write_text(json.dumps(meta))
    return _sweep(t, _props(_synthetic()), freeze=True)


def test_freeze_passes_with_engine_meta(tmp_path):
    t = _tree(tmp_path)
    csvp = t / "proposals" / "proposals.csv"
    csvp.write_text(_props(_synthetic()))
    write_meta(csvp, scope_set="nitrd-pca-fy2025 v1", scope_sha256="0" * 64, text_source="NIH RePORTER")
    r = _sweep(t, csvp.read_text(), freeze=True)
    assert r.returncode == 0 and "S7_output_label: PASS" in r.stdout, r.stdout


@pytest.mark.parametrize("meta", [
    None,
    {"label": "Official UAC coding", "official_uac_method": False, "suggestion_columns_read": False},
    {"label": OUTPUT_LABEL, "official_uac_method": True, "suggestion_columns_read": False},
    {"label": OUTPUT_LABEL, "official_uac_method": False, "suggestion_columns_read": True},
])
def test_s7_rejects_missing_or_wrong_label(tmp_path, meta):
    r = _freeze_with_meta(tmp_path, meta)
    assert r.returncode == 1 and "S7_output_label: FAIL" in r.stdout


def test_label_matches_sweep():
    sys.path.insert(0, str(ROOT / "tools"))
    import build_sweep
    assert build_sweep.OUTPUT_LABEL == OUTPUT_LABEL
