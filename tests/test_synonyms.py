"""Synonym file integrity, provenance, and engine integration."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SYN = ROOT / "engine" / "synonyms.json"
SCOPE = ROOT / "scope" / "nitrd_pca_scopes_fy2025.v1.json"
FIXTURE = ROOT / "fixtures" / "UAC_Uncoded_12-01-2025-updated-NIH_ODSS.csv"
CACHE = ROOT / "cache" / "reporter" / "reporter_text.v1.jsonl"
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


def test_synonym_provenance_in_explanations(tmp_path):
    """At least some explanations cite a synonym term."""
    r = subprocess.run(
        [sys.executable, str(ROOT / "engine" / "run.py"),
         "--fixture", str(FIXTURE), "--out-dir", str(tmp_path), "--offline"],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    expls = [json.loads(l) for l in (tmp_path / "explanations.jsonl").read_text().splitlines() if l.strip()]
    # At least one explanation should have a matched_term whose source_phrase starts with 'synonym:'
    syn_hits = 0
    for e in expls:
        for ranked in e.get("ranked", []):
            for mt in ranked.get("matched_terms", []):
                if mt.get("source_phrase", "").startswith("synonym:"):
                    syn_hits += 1
    assert syn_hits > 0, "no synonym terms appeared in any explanation"


def test_meta_records_synonyms_sha(tmp_path):
    subprocess.run(
        [sys.executable, str(ROOT / "engine" / "run.py"),
         "--fixture", str(FIXTURE), "--out-dir", str(tmp_path), "--offline"],
        capture_output=True, text=True)
    meta = json.loads((tmp_path / "proposals.meta.json").read_text())
    assert meta["synonyms_sha256"] == hashlib.sha256(SYN.read_bytes()).hexdigest()
    assert meta["synonyms_added"] > 0


def test_engine_deterministic_with_synonyms(tmp_path):
    d1, d2 = tmp_path / "r1", tmp_path / "r2"
    for d in (d1, d2):
        r = subprocess.run(
            [sys.executable, str(ROOT / "engine" / "run.py"),
             "--fixture", str(FIXTURE), "--out-dir", str(d), "--offline"],
            capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    assert (d1 / "proposals.csv").read_bytes() == (d2 / "proposals.csv").read_bytes()
    assert (d1 / "explanations.jsonl").read_bytes() == (d2 / "explanations.jsonl").read_bytes()


def test_synonyms_file_is_exactly_the_derivation_output(tmp_path):
    """No hand edits: re-running the committed derivation on the committed corpus reproduces
    engine/synonyms.json byte-for-byte (SME flags, if any, are added by a separate dated step)."""
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
