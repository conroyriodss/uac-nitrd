"""synonym-derivation-v2: seeds are verbatim NITRD text; corpus excludes the 480; selection is mechanical."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import build_independent_corpus as bic  # noqa: E402
import derive_synonyms as ds  # noqa: E402

SCOPE = json.loads((ROOT / "scope" / "nitrd_pca_scopes_fy2025.v1.json").read_text(encoding="utf-8"))
SEEDS = json.loads((ROOT / "scope" / "synonym_seeds.v1.json").read_text(encoding="utf-8"))["seeds"]


def test_every_seed_is_verbatim_nitrd_text():
    g = SCOPE["cross_pca_guidance"]
    guidance = (g["ai_definition"]["text"] + " " + " ".join(g["ai_cross_pca"]["items"])).lower()
    scope_text = {s["code"]: s["scope_text"].lower() for s in SCOPE["scopes"]}
    assert set(SEEDS) == set(scope_text)
    for p, seeds in SEEDS.items():
        assert seeds, p
        for s in seeds:
            assert s.lower() in scope_text[p] or s.lower() in guidance, (p, s)


def test_core_of():
    assert bic.core_of("1R01AG087654-01A1") == "R01AG087654"
    assert bic.core_of("5P30AG066444-05") == "P30AG066444"
    assert bic.core_of("1ZIAMH002652-24") == "ZIAMH002652"
    assert bic.core_of("") is None


def _fake_post_factory():
    def post(body):
        crit, off = body["criteria"], body["offset"]
        assert crit["fiscal_years"] == [2024]
        assert set(body["include_fields"]) == set(bic.INCLUDE_FIELDS)  # never RCDC fields
        if "advanced_text_search" in crit:
            ats = crit["advanced_text_search"]
            assert ats["search_field"] == "projecttitle,abstracttext"
            res = [{"appl_id": 100, "core_project_num": "R01AG000001", "fiscal_year": 2024,
                    "project_title": "t", "abstract_text": "machine learning deep nets"},
                   {"appl_id": 101, "core_project_num": "R01XX999999", "fiscal_year": 2024,
                    "project_title": "same core as fixture", "abstract_text": "x"},
                   {"appl_id": 102, "core_project_num": "R01AG000002", "fiscal_year": 2024,
                    "project_title": "fixture appl", "abstract_text": "x"}]
        else:
            res = [{"appl_id": 200 + off, "core_project_num": f"R01BG{off:06d}", "fiscal_year": 2024,
                    "project_title": "bg", "abstract_text": "clinical cohort"}]
        return {"meta": {"total": len(res)}, "results": res if off == 0 or "advanced_text_search" not in crit else []}
    return post


def test_corpus_drops_fixture_projects_and_same_core():
    gz, m = bic.build({"AI": ["machine learning"]}, excluded_appl={102}, excluded_core={"R01XX999999"},
                      post=_fake_post_factory())
    import gzip
    recs = [json.loads(l) for l in gzip.decompress(gz).decode().splitlines()]
    ids = {r["appl_id"] for r in recs}
    assert 101 not in ids and 102 not in ids and 100 in ids
    assert m["dropped"]["same_core_as_fixture"] == 1 and m["dropped"]["fixture_appl_id"] == 1
    assert all(set(r) == {"appl_id", "core_project_num", "fiscal_year", "title", "abstract", "queries"} for r in recs)


def test_corpus_build_is_deterministic():
    a = bic.build({"AI": ["machine learning"]}, {102}, {"R01XX999999"}, post=_fake_post_factory())
    b = bic.build({"AI": ["machine learning"]}, {102}, {"R01XX999999"}, post=_fake_post_factory())
    assert a[0] == b[0] and a[1] == b[1]


def _synthetic_corpus():
    docs = []
    for i in range(40):  # AI seed set: 'gradient boosting' over-represented
        docs.append({"appl_id": i, "title": "t", "abstract": "machine learning gradient boosting cohort",
                     "queries": ["seed:AI:machine learning"]})
    for i in range(40, 240):  # background: cohort only
        docs.append({"appl_id": i, "title": "t", "abstract": "clinical cohort outcomes", "queries": ["background"]})
    return docs


def test_derivation_is_mechanical_and_excludes_seed_echo():
    syns, per = ds.derive(_synthetic_corpus(), {"AI": ["machine learning"]}, SCOPE)
    terms = {(s["term"], s["pca"]) for s in syns}
    assert ("gradient boosting", "AI") in terms and ("gradient", "AI") in terms
    assert not any(t in ("machine", "learning", "machine learning") for t, _ in terms)  # seed echo excluded
    assert not any(t == "cohort" for t, _ in terms)  # not over-represented
    assert per["CHuman"]["docs"] == 0 and "skipped" in per["CHuman"]
    for s in syns:
        assert s["stats"]["z"] >= ds.Z_MIN and s["expands"] == "machine learning"
    assert ds.derive(_synthetic_corpus(), {"AI": ["machine learning"]}, SCOPE)[0] == syns


def test_derivation_tools_never_read_fixture_text_or_key():
    for f in ("derive_synonyms.py", "build_independent_corpus.py"):
        src = (ROOT / "tools" / f).read_text(encoding="utf-8")
        assert not re.search(r"suggestion[\s_\-]*\d|heldout|reporter_text\.v1|entry2_heldout", src, re.IGNORECASE), f
    assert "load_project_refs" not in (ROOT / "tools" / "derive_synonyms.py").read_text(encoding="utf-8")
