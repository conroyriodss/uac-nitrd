"""vocabulary-scope-only-2026-10-24: the reveal engine uses NO synonyms.

The engine must load no synonym file and cite no synonym in any explanation. Both withdrawn
synonym sets are kept as evidence: v1 (selected on the 480) and v2 (derived mechanically from
independent FY2024 text, not applied). v2 must still reproduce byte-for-byte from the committed
corpus, and the provenance checks below apply to it."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SYN = ROOT / "docs" / "evidence" / "synonyms_v2_derived_NOT_APPLIED.json"
SYN_V1 = ROOT / "docs" / "evidence" / "synonyms_v1_WITHDRAWN.json"
SCOPE = ROOT / "scope" / "nitrd_pca_scopes_fy2025.v1.json"
FIXTURE = ROOT / "fixtures" / "UAC_Uncoded_12-01-2025-updated-NIH_ODSS.csv"
CACHE = ROOT / "cache" / "reporter" / "reporter_text.v1.jsonl"
sys.path.insert(0, str(ROOT / "tests"))
import synthetic_projects  # noqa: E402  (freeze-guard-v1: never the 480 in tests)


def _engine(out, tmp_path, *extra):
    fx, cache = synthetic_projects.make(tmp_path / "syn")
    return subprocess.run([sys.executable, str(ROOT / "engine" / "run.py"), "--fixture", str(fx),
                           "--cache", str(cache), "--out-dir", str(out), "--offline", *extra],
                          capture_output=True, text=True)


PCA_CODES = {"ACNS", "AI", "CHuman", "CNPS", "CSP", "EdW", "EHCS", "ENIT", "HCIA", "IRAS", "LSDMA", "SPSQ", "AW"}
REQUIRED_FIELDS = {"term", "pca", "expands", "reason", "source"}


@pytest.fixture(scope="module")
def synonyms():
    data = json.loads(SYN.read_text(encoding="utf-8"))
    return [e for e in data["synonyms"] if "comment" not in e]


def test_valid_json():
    data = json.loads(SYN.read_text(encoding="utf-8"))
    assert data["schema"] == "uac-nitrd/scope-synonyms/v2"
    assert data["derivation_id"] == "synonym-derivation-v2-2026-10-24"
    assert isinstance(data["synonyms"], list) and len(data["synonyms"]) > 0


def test_every_entry_has_required_provenance_fields(synonyms):
    for i, e in enumerate(synonyms):
        missing = REQUIRED_FIELDS - set(e)
        assert not missing, f"entry {i} ({e.get('term','?')}) missing {missing}"


def test_every_pca_is_valid(synonyms):
    for e in synonyms:
        assert e["pca"] in PCA_CODES, f"unknown PCA {e['pca']} for term '{e['term']}'"


def test_every_expands_is_nonempty(synonyms):
    for e in synonyms:
        assert e["expands"].strip(), f"empty 'expands' for term '{e['term']}'"
        assert e["reason"].strip(), f"empty 'reason' for term '{e['term']}'"
        assert e["source"].strip(), f"empty 'source' for term '{e['term']}'"


def test_no_duplicate_term_pca_pairs(synonyms):
    seen = set()
    for e in synonyms:
        key = (e["term"].lower().strip(), e["pca"])
        assert key not in seen, f"duplicate ({key})"
        seen.add(key)


def test_no_key_or_suggestion_references(synonyms):
    """Synonym entries must not reference the key or suggestions (the policy header is OK)."""
    for e in synonyms:
        blob = json.dumps(e).lower()
        for forbidden in ("heldout", "answer key", "suggestion_1", "suggestion_2",
                          "rcdc", "file_a", "file_b", "file_c"):
            assert forbidden not in blob, f"forbidden reference '{forbidden}' in synonym '{e['term']}'"


def test_load_synonyms_adds_terms():
    from engine.run import _build_vocabulary, _load_synonyms
    scope_data = json.loads(SCOPE.read_text(encoding="utf-8"))
    vocab = _build_vocabulary(scope_data["scopes"], scope_data.get("cross_pca_guidance", {}))
    before = sum(len(v) for v in vocab.values())
    added = _load_synonyms(SYN, vocab)
    after = sum(len(v) for v in vocab.values())
    assert added > 0 and after > before
    assert added == after - before


def test_no_synonym_in_any_explanation(tmp_path):
    """Scope-only vocabulary: no explanation may cite a synonym term."""
    r = _engine(tmp_path / "o", tmp_path)
    assert r.returncode == 0, r.stderr
    expls = [json.loads(l) for l in (tmp_path / "o" / "explanations.jsonl").read_text().splitlines() if l.strip()]
    assert any(e.get("ranked") for e in expls)  # the synthetic texts do match scope terms
    syn_hits = 0
    for e in expls:
        for ranked in e.get("ranked", []):
            for mt in ranked.get("matched_terms", []):
                if mt.get("source_phrase", "").startswith("synonym:"):
                    syn_hits += 1
    assert syn_hits == 0, f"{syn_hits} synonym citations in explanations"


def test_meta_records_synonyms_sha(tmp_path):
    assert _engine(tmp_path / "o", tmp_path).returncode == 0
    meta = json.loads((tmp_path / "o" / "proposals.meta.json").read_text())
    assert meta["vocabulary"] == "vocabulary-scope-only-2026-10-24"
    assert meta["synonyms_sha256"] == "" and meta["synonyms_added"] == 0
    from engine.run import AI_GATE_CORE, _normalise
    assert sorted(meta["ai_gate"]["terms"]) == sorted(" ".join(_normalise(t)) for t, _ in AI_GATE_CORE)


def test_engine_cannot_load_synonyms():
    from engine import run
    assert run.SYNONYMS_PATH is None
    assert not (ROOT / "engine" / "synonyms.json").exists()
    assert "--synonyms" not in (ROOT / "engine" / "run.py").read_text(encoding="utf-8")
    r = _engine("/tmp/x", Path("/tmp/uac_nitrd_syn_test"), "--synonyms", str(SYN))
    assert r.returncode != 0 and "unrecognized arguments" in r.stderr


def test_withdrawn_v1_kept_as_evidence():
    assert json.loads(SYN_V1.read_text(encoding="utf-8"))["schema"] == "uac-nitrd/scope-synonyms/v1"


def test_engine_deterministic_scope_only(tmp_path):
    d1, d2 = tmp_path / "r1", tmp_path / "r2"
    for d in (d1, d2):
        r = _engine(d, tmp_path)
        assert r.returncode == 0, r.stderr
    assert (d1 / "proposals.csv").read_bytes() == (d2 / "proposals.csv").read_bytes()
    assert (d1 / "explanations.jsonl").read_bytes() == (d2 / "explanations.jsonl").read_bytes()


def test_synonyms_file_is_exactly_the_derivation_output(tmp_path):
    """No hand edits: re-running the committed derivation on the committed corpus reproduces
    the v2 evidence file exactly (it was judged unusable on FY2024 output and not applied)."""
    out = tmp_path / "s.json"
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "derive_synonyms.py"), "--out", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    committed = json.loads(SYN.read_text(encoding="utf-8"))
    for e in committed["synonyms"]:
        e.pop("sme_review", None)
    assert json.loads(out.read_text(encoding="utf-8")) == committed


def test_expands_is_the_pcas_verbatim_seeds(synonyms):
    seeds = json.loads((ROOT / "scope" / "synonym_seeds.v1.json").read_text(encoding="utf-8"))["seeds"]
    for e in synonyms:
        assert e["expands"] == "; ".join(seeds[e["pca"]]), e["term"]
