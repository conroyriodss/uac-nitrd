"""Integrity tests for the versioned NITRD subcategory-scope objects (offline)."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_pca_scopes import PCA_CODES, page_lines  # noqa: E402

SETS = sorted((ROOT / "scope").glob("nitrd_pca_scopes_fy*.v*.json"))


def _load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def test_sets_present():
    assert {p.name for p in SETS} >= {"nitrd_pca_scopes_fy2025.v1.json", "nitrd_pca_scopes_fy2026.v1.json"}


@pytest.mark.parametrize("path", SETS, ids=lambda p: p.name)
def test_snapshot_hash_and_verbatim(path):
    o = _load(path)
    snap = ROOT / o["source"]["snapshot_file"]
    assert hashlib.sha256(snap.read_bytes()).hexdigest() == o["source"]["snapshot_sha256"]
    page = " ".join(page_lines(snap.read_bytes()))
    for s in o["scopes"]:
        assert len(s["scope_text"]) > 80 and s["scope_text"] in page, s["code"]
    g = o["cross_pca_guidance"]
    for t in [g["ai_definition"]["text"], *g["ai_cross_pca"]["items"]]:
        assert t in page


@pytest.mark.parametrize("path", SETS, ids=lambda p: p.name)
def test_codes_and_aw_representation(path):
    o = _load(path)
    pcas = [s for s in o["scopes"] if s["kind"] == "pca"]
    assert tuple(s["code"] for s in pcas) == PCA_CODES and all(s["standard_pca"] for s in pcas)
    (aw,) = [s for s in o["scopes"] if s["kind"] == "sub_pca"]
    assert aw["code"] == "AW" and aw["parent"] == "ACNS" and aw["standard_pca"] is False
    assert aw["selectable"] is True and aw["budget_crosscut_code"] is None
    assert aw["rollup"]["status"] == "UNRESOLVED"


@pytest.mark.parametrize("path", SETS, ids=lambda p: p.name)
def test_rebuild_is_byte_identical(path, tmp_path):
    o = _load(path)
    out = tmp_path / path.name
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "build_pca_scopes.py"),
                        "--snapshot", str(ROOT / o["source"]["snapshot_file"]),
                        "--snapshot-ref", o["source"]["snapshot_file"], "--fy", str(o["fiscal_year"]),
                        "--url", o["source"]["url"], "--retrieved-at", o["source"]["retrieved_at_utc"],
                        "--version", str(o["version"]), "--out", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert out.read_bytes() == path.read_bytes()
