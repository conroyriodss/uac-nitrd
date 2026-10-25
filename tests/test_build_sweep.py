"""Model-free tests for the UAC NITRD build sweep. None of them read the held-out key."""
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "UAC_Uncoded_12-01-2025-updated-NIH_ODSS.csv"
CODES = ["ACNS", "AI", "CHuman", "CNPS", "CSP", "EdW", "EHCS", "ENIT", "HCIA", "IRAS", "LSDMA", "SPSQ", ""]


def _ids():
    with FIXTURE.open(newline="", encoding="utf-8-sig") as f:
        return [r["Appl ID"].strip() for r in csv.DictReader(f)]


def _tree(tmp_path, extra=None):
    t = tmp_path / "repo"
    # Test trees start from the pre-freeze state: the frozen engine outputs in proposals/
    # (tag uac-nitrd-freeze-v1) are NOT copied, so each test controls its own proposals and meta.
    # The 92 MB Task 1 FY2024 text snapshot is irrelevant to S1-S9 and is not copied either
    # (copying and guard-scanning it in every test tree made the suite exceed its time budget).
    shutil.copytree(ROOT, t, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", ".pytest_cache",
        "proposals.csv", "explanations.jsonl", "proposals.meta.json", "FREEZE_SWEEP.json",
        "task1_fy2024_text"))
    for rel, text in (extra or {}).items():
        (t / rel).parent.mkdir(parents=True, exist_ok=True)
        (t / rel).write_text(text)
    return t


def test_test_trees_exclude_the_frozen_outputs(tmp_path):
    """Regression (CI red on b0ccbe6/6fdc57f): a copied frozen meta made the 'missing meta' S7 case pass."""
    t = _tree(tmp_path)
    for n in ("proposals.csv", "explanations.jsonl", "proposals.meta.json", "FREEZE_SWEEP.json"):
        assert not (t / "proposals" / n).exists(), n


def _props(rows, header="appl_id,primary_pca,ai_relevant,sub_pca"):
    return header + "\n" + "".join(",".join(r) + "\n" for r in rows)


def _synthetic():  # placeholder values only; not derived from any key
    out = []
    for i, a in enumerate(_ids()):
        p = CODES[i % len(CODES)]
        out.append((a, p, "true" if p == "AI" or i % 2 else "false", "AW" if p == "ACNS" and i % 2 else ""))
    return out


def _sweep(t, proposals=None, freeze=False):
    cmd = [sys.executable, str(t / "tools" / "build_sweep.py"), "--tree", str(t),
           "--fixture", str(t / "fixtures" / FIXTURE.name)]
    if proposals is not None:
        p = t / "proposals" / "proposals.csv"
        p.write_text(proposals)
        cmd += ["--proposals", str(p)]
    if freeze:
        cmd.append("--freeze")
    return subprocess.run(cmd, capture_output=True, text=True)


def test_repo_tree_passes_build_mode(tmp_path):
    r = _sweep(_tree(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr


def test_freeze_requires_proposals(tmp_path):
    assert _sweep(_tree(tmp_path), freeze=True).returncode == 1


# A stand-in engine that obeys the contract and uses identity columns only. It reproduces
# _synthetic() exactly, so its output equals the synthetic frozen proposals.
HONEST_ENGINE = '''
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.inputs import load_project_refs
CODES = %r
ap = argparse.ArgumentParser(); ap.add_argument("--fixture", type=Path); ap.add_argument("--out-dir", type=Path)
ap.add_argument("--offline", action="store_true"); a = ap.parse_args()
rows = []
for i, r in enumerate(load_project_refs(a.fixture)):
    p = CODES[i %% len(CODES)]
    rows.append((str(r.appl_id), p, "true" if p == "AI" or i %% 2 else "false", "AW" if p == "ACNS" and i %% 2 else ""))
(a.out_dir / "proposals.csv").write_text("appl_id,primary_pca,ai_relevant,sub_pca\\n" + "".join(",".join(x) + "\\n" for x in rows))
(a.out_dir / "explanations.jsonl").write_text("".join('{"appl_id": %%s, "primary_pca": "%%s"}\\n' %% (x[0], x[1]) for x in rows))
''' % (CODES,)


def _meta_ok():
    sys.path.insert(0, str(ROOT))
    from engine import OUTPUT_LABEL
    return {"proposals/proposals.meta.json": json.dumps(
                {"label": OUTPUT_LABEL, "official_uac_method": False, "suggestion_columns_read": False}),
            "engine/run.py": HONEST_ENGINE}


def test_freeze_passes_on_valid_complete_proposals(tmp_path):
    r = _sweep(_tree(tmp_path, _meta_ok()), _props(_synthetic()), freeze=True)
    assert r.returncode == 0 and "FREEZE OK" in r.stdout, r.stdout + r.stderr


@pytest.mark.parametrize("mutate", [
    lambda rows: [(rows[0][0], "AI", "false", "")] + rows[1:],       # AI without flag
    lambda rows: [(rows[0][0], "LSN", "true", "")] + rows[1:],       # unknown code
    lambda rows: rows[:-1],                                           # missing project
    lambda rows: rows + [("99999999", "ACNS", "true", "")],          # extra project
    lambda rows: rows + [rows[0]],                                     # duplicate
    lambda rows: [(rows[0][0], "AW", "false", "")] + rows[1:],       # v2: AW as primary
    lambda rows: [(rows[0][0], "CHuman", "false", "AW")] + rows[1:], # v2: AW not under ACNS
    lambda rows: [(rows[0][0], "ACNS", "false", "5G")] + rows[1:],   # v2: unknown sub_pca
])
def test_freeze_rejects_bad_proposals(tmp_path, mutate):
    assert _sweep(_tree(tmp_path, _meta_ok()), _props(mutate(_synthetic())), freeze=True).returncode == 1


def test_freeze_rejects_missing_sub_pca_column(tmp_path):
    rows = [r[:3] for r in _synthetic()]
    r = _sweep(_tree(tmp_path), _props(rows, "appl_id,primary_pca,ai_relevant"), freeze=True)
    assert r.returncode == 1 and "S5_format_v2: FAIL" in r.stdout


def test_edited_scorer_fails_integrity(tmp_path):
    t = _tree(tmp_path)
    (t / "tools" / "score_heldout.py").write_text((t / "tools" / "score_heldout.py").read_text() + "\n# edit\n")
    r = _sweep(t)
    assert r.returncode == 1 and "S1_tool_integrity: FAIL" in r.stdout
