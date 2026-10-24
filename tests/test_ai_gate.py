"""ai-gate-v2: ai_relevant requires an AI-specific term. Synthetic text only (no fixture text)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.run import (AI_GATE_CORE, SCOPE_PATH, SYNONYMS_PATH, _build_vocabulary,  # noqa: E402
                        _load_synonyms, build_ai_gate, propose)


@pytest.fixture(scope="module")
def env():
    scope = json.loads(SCOPE_PATH.read_text(encoding="utf-8"))
    vocab = _build_vocabulary(scope["scopes"], scope.get("cross_pca_guidance", {}))
    _load_synonyms(SYNONYMS_PATH, vocab)
    return vocab, build_ai_gate(SYNONYMS_PATH)


def _p(env, abstract, title="A study"):
    vocab, gate = env
    return propose(1, {"title": title, "abstract": abstract, "public_health_relevance": ""}, vocab, "x", gate)


def test_generic_definition_words_do_not_set_flag(env):
    p = _p(env, "We build models and systems for the analysis of human environments and make "
                "recommendations and decisions from data inputs.")
    assert p["ai_relevant"] is False and p["ai_evidence"] == []


@pytest.mark.parametrize("phrase", ["machine learning", "artificial intelligence", "machine vision",
                                    "computational linguistics", "neural nets", "AI"])
def test_ai_specific_term_sets_flag(env, phrase):
    p = _p(env, f"We apply {phrase} to cardiac imaging.")
    assert p["ai_relevant"] is True
    assert p["ai_evidence"] and all("source_phrase" in h and "text_span" in h for h in p["ai_evidence"])


def test_ai_an_is_not_artificial_intelligence(env):
    for s in ("health disparities among AI/AN communities", "AI / AN youth", "serving AI/ANs"):
        assert _p(env, s)["ai_relevant"] is False, s


def test_derived_single_words_never_join_gate():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "s.json"
        p.write_text(json.dumps({"synonyms": [
            {"term": "algorithm", "pca": "AI", "expands": "x", "reason": "x", "source": "x"},
            {"term": "deep learning", "pca": "AI", "expands": "x", "reason": "x", "source": "x"},
            {"term": "neural network", "pca": "AI", "expands": "x", "reason": "x", "source": "x",
             "sme_review": "pending: test"}]}))
        terms = {" ".join(t) for t, _ in build_ai_gate(p)}
    assert "deep learning" in terms and "algorithm" not in terms and "neural network" not in terms


def _legacy_test_sme_pending_synonyms_excluded_from_gate(env):
    """pending synonyms are NOT in the gate (so they can't set ai_relevant on their own),
    but they ARE still in the PCA vocabulary (so AI may still win as primary_pca via
    the scoring path, which sets ai_relevant=True through primary=='AI', not the gate)."""
    _, gate = env
    terms = {" ".join(t) for t, _ in gate}
    for pending in ("predictive model", "predictive models", "predictive modeling"):
        assert pending not in terms
    # Text with only the pending synonym and NO other AI gate term:
    # ai_relevant can still be True if AI wins the PCA score. That's correct.
    # What the gate guarantees is: without an AI gate term AND without AI winning,
    # ai_relevant stays False.
    p = _p(env, "The weather patterns are interesting.")
    assert p["ai_relevant"] is False, "trivial text with no AI terms must not be flagged"


def test_gate_contains_every_core_term(env):
    _, gate = env
    terms = {" ".join(t) for t, _ in gate}
    assert {t for t, _ in AI_GATE_CORE} <= terms


def test_gate_is_deterministic():
    assert build_ai_gate(SYNONYMS_PATH) == build_ai_gate(SYNONYMS_PATH)


def test_no_text_still_abstains_unflagged(env):
    vocab, gate = env
    p = propose(1, {}, vocab, "x", gate)
    assert p["ai_relevant"] is False and p["abstain_reason"].startswith("no_public_text")
