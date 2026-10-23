"""Integrity and uniformity of the committed RePORTER text cache (offline; no network, no key)."""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import build_reporter_cache as brc  # noqa: E402
from build_sweep import _scramble_fixture  # noqa: E402
from engine.inputs import load_project_refs  # noqa: E402

FIXTURE = ROOT / "fixtures" / "UAC_Uncoded_12-01-2025-updated-NIH_ODSS.csv"
CACHE = ROOT / "cache" / "reporter"
ALLOWED_KEYS = {"appl_id", "status", "project_num", "fiscal_year", "title", "abstract",
                "public_health_relevance", "specific_aims"}


def _lines():
    return (CACHE / "reporter_text.v1.jsonl").read_bytes().splitlines()


def test_manifest_hashes_match_committed_cache():
    m = json.loads((CACHE / "MANIFEST.json").read_text(encoding="utf-8"))
    assert hashlib.sha256((CACHE / "reporter_text.v1.jsonl").read_bytes()).hexdigest() == m["jsonl_sha256"]
    recs = {json.loads(b)["appl_id"]: b for b in _lines()}
    assert {str(k) for k in recs} == set(m["record_sha256"])
    for k, b in recs.items():
        assert hashlib.sha256(b).hexdigest() == m["record_sha256"][str(k)]
        assert brc.canonical(json.loads(b)) == b  # stored canonically, so a re-fetch is byte-comparable


def test_cache_covers_exactly_the_fixture_and_only_public_fields():
    recs = [json.loads(b) for b in _lines()]
    assert [r["appl_id"] for r in recs] == sorted(r.appl_id for r in load_project_refs(FIXTURE))
    assert all(set(r) == ALLOWED_KEYS for r in recs)
    assert all(r["specific_aims"] is None for r in recs)  # not exposed by the public API, for every project


def test_cache_has_no_coder_or_category_content():
    text = (CACHE / "reporter_text.v1.jsonl").read_text(encoding="utf-8")
    # Every RCDC category label starts with "NITRD - "; the cache has no "NITRD" at all.
    for pat in (r"spending_categor", r"pref_terms", r'"terms"', r"suggestion[\s_\-]*\d", r"NITRD"):
        assert not re.search(pat, text, re.IGNORECASE), pat


def test_make_record_drops_unlisted_fields():
    raw = {"appl_id": 1, "project_title": "t", "abstract_text": "a", "phr_text": None,
           "spending_categories_desc": "X", "terms": "<y>", "pref_terms": "z"}
    assert set(brc.make_record(1, raw)) == ALLOWED_KEYS


def _fake_fetch(ids, offset):  # stands in for RePORTER; responds by Appl ID only
    res = [{"appl_id": a, "project_num": f"P{a}", "fiscal_year": 2025, "project_title": f"T{a}",
            "abstract_text": f"A{a}" * (a % 7 + 1), "phr_text": None, "spending_categories": [9]}
           for a in ids if a % 97]
    return {"meta": {"total": len(res)}, "results": res[offset:offset + brc.PAGE]}


def test_builder_is_uniform_under_scrambled_fixture(tmp_path):
    """Which projects are cached, and how, cannot depend on any non-identity fixture column."""
    scr = tmp_path / "scrambled.csv"
    _scramble_fixture(FIXTURE, scr, seed=12345)
    real = brc.build([r.appl_id for r in load_project_refs(FIXTURE)], _fake_fetch)
    scrambled = brc.build([r.appl_id for r in load_project_refs(scr)], _fake_fetch)
    assert real[0] == scrambled[0] and real[1]["record_sha256"] == scrambled[1]["record_sha256"]


def test_builder_source_names_no_forbidden_input():
    src = (ROOT / "tools" / "build_reporter_cache.py").read_text(encoding="utf-8")
    assert not re.search(r"suggestion[\s_\-]*\d", src, re.IGNORECASE)
    assert "load_project_refs" in src and "csv" not in re.findall(r"^import (\w+)", src, re.MULTILINE)
