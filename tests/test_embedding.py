"""Arm B model format and hosted-encoder pin checks (offline; no endpoint, no torch)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflow import embedding as em  # noqa: E402


def _bank(rng, n, d):
    return em.quantize(rng.normal(size=(n, d)))


def _model(d=8):
    rng = np.random.default_rng(0)
    pos, neg = _bank(rng, 5, d), _bank(rng, 4, d)
    ex = {"nitrd": {"appl_id": np.arange(10, 15), "core": ["A", "A", "B", "C", "D"], "emb": pos,
                    "selection": "test"},
          "not_nitrd": {"appl_id": np.arange(20, 24), "core": ["E", "F", "G", "H"], "emb": neg,
                        "selection": "test"}}
    return em.Model(rng.normal(size=d), 0.5, ex, {"fingerprint_id": "t"}), pos


def test_quantize_is_unit_norm_and_rounded():
    e = em.quantize(np.array([[3.0, 4.0], [0.0, 0.0]]))
    assert e.dtype == np.float32
    assert np.allclose(e[0], [0.6, 0.8])
    assert np.all(e[1] == 0)


def test_roundtrip_is_byte_stable_and_scores_match():
    m, pos = _model()
    blob = m.to_bytes()
    r = em.Model.from_bytes(blob)
    assert r.to_bytes() == blob
    assert np.allclose(r.decision(pos), m.decision(pos), atol=1e-6)
    assert r.meta == m.meta and r.pin == em.PIN


def test_from_bytes_refuses_a_different_pin():
    m, _ = _model()
    m.pin = dict(em.PIN, served_model_version="other")
    with pytest.raises(ValueError):
        em.Model.from_bytes(m.to_bytes())


def test_explain_excludes_own_core_and_returns_both_sides():
    m, pos = _model()
    out = em.Model.from_bytes(m.to_bytes()).explain(pos[0], core="A", top=3)
    assert {d["core_project_num"] for d in out["nitrd"]}.isdisjoint({"A"})
    assert len(out["nitrd"]) == 3 and len(out["not_nitrd"]) == 3
    cos = [d["cosine"] for d in out["nitrd"]]
    assert cos == sorted(cos, reverse=True)


class _FakeApi:
    def __init__(self, model):
        self.model, self.calls = model, 0

    def do(self, method, path, body):
        self.calls += 1
        n = len(body["input"])
        return {"model": self.model, "data": [{"index": i, "embedding": [1.0] + [0.0] * 1023}
                                              for i in range(n)]}


class _FakeClient:
    def __init__(self, model):
        self.api_client = _FakeApi(model)


def test_hosted_encoder_keeps_order_and_checks_the_pin():
    enc = em.HostedEncoder(_FakeClient(em.PIN["served_model_version"]))
    e = enc.embed([f"t{i}" for i in range(em.BATCH * 2 + 3)])
    assert e.shape == (em.BATCH * 2 + 3, em.PIN["dimensions"]) and enc.calls == 3
    with pytest.raises(RuntimeError, match="served"):
        em.HostedEncoder(_FakeClient("some-other-version")).embed(["x"])
