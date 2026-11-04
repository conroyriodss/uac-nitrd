"""Hand-worked tests for workflow/reveal_metrics.py (task1-reveal-metrics-v1)."""

import numpy as np
import pytest

from workflow import model_comparison as mc
from workflow import reveal_metrics as rm


def test_kappa_hand_worked():
    # N=100, po=.85, pa=.25, pb=.30, pe=.60 -> kappa=.625
    assert float(rm.kappa_counts(20, 5, 10, 65)) == pytest.approx(0.625)


def test_kappa_matches_pinned_harness():
    rng = np.random.default_rng(1)
    a, b = rng.random(500) < 0.2, rng.random(500) < 0.3
    c = rm._confusion(a, b).sum(0)
    assert float(rm.kappa_counts(*c)) == pytest.approx(mc.kappa(a, b, np.ones(500)))


def test_shortlist_size_matches_harness():
    for n in (63074, 64065, 56508, 7):
        assert rm.shortlist_size(mc.PRIMARY_FRACTION, n) == mc.shortlist_size(mc.PRIMARY_FRACTION, n)
    assert rm.shortlist_size(mc.PRIMARY_FRACTION, 64065) == 7399


def _small():
    m = np.array([1, 1, 1, 0, 0, 0, 0, 0, 0, 0], bool)
    nitrd = np.array([1, 1, 0, 1, 0, 0, 0, 0, 0, 0], bool)
    cat = np.ones(10, bool)
    cat[2] = False  # shortlisted, uncategorized
    return m, nitrd, cat


def test_arm_vs_listing_hand_worked():
    m, nitrd, cat = _small()
    cores = rm.Cores([f"c{i}" for i in range(10)])
    o = rm.arm_vs_listing(m, nitrd, cat, np.ones(10, bool), cores, seed=7)
    assert o["recall"] == pytest.approx(2 / 3)
    assert o["precision_primary"] == pytest.approx(1.0)        # 2 / 2 categorized shortlisted
    assert o["precision_sensitivity"] == pytest.approx(2 / 3)  # 2 / 3 shortlisted
    assert o["shortlisted_uncategorized"] == 1 and o["uncategorized"] == 1
    # primary kappa on the 9 categorized: n11=2, n10=0, n01=1, n00=6 -> 24/33
    assert o["kappa_primary"] == pytest.approx(24 / 33)
    # sensitivity on 10: n11=2, n10=1, n01=1, n00=6 -> po=.8, pa=.3, pb=.3, pe=.58 -> .22/.42
    assert o["kappa_sensitivity"] == pytest.approx(0.22 / 0.42)


def test_scope_excludes_awards():
    m, nitrd, cat = _small()
    scope = np.ones(10, bool)
    scope[3] = False  # drop the missed NITRD award
    o = rm.arm_vs_listing(m, nitrd, cat, scope, rm.Cores([str(i) for i in range(10)]), seed=7)
    assert o["recall"] == 1.0 and o["n"] == 9 and o["nitrd"] == 2


def test_bootstrap_single_core_is_degenerate():
    m, nitrd, cat = _small()
    o = rm.arm_vs_listing(m, nitrd, cat, np.ones(10, bool), rm.Cores(["one"] * 10), seed=3)
    assert o["kappa_primary_ci95"] == pytest.approx([24 / 33, 24 / 33])
    assert o["recall_ci95_core_bootstrap"] == pytest.approx([2 / 3, 2 / 3])


def test_bootstrap_ci_brackets_point_and_is_deterministic():
    rng = np.random.default_rng(5)
    n = 3000
    y = rng.random(n) < 0.1
    m = y ^ (rng.random(n) < 0.05)
    core = [f"c{i // 3}" for i in range(n)]
    a = rm.arm_vs_listing(m, y, np.ones(n, bool), np.ones(n, bool), rm.Cores(core), seed=11)
    b = rm.arm_vs_listing(m, y, np.ones(n, bool), np.ones(n, bool), rm.Cores(core), seed=11)
    lo, hi = a["kappa_primary_ci95"]
    assert lo < a["kappa_primary"] < hi and a == b


def test_curve_and_disagreement():
    rank = np.arange(1, 11)
    nitrd = np.array([1, 0, 1, 0, 0, 0, 0, 0, 0, 1], bool)
    c = rm.curve(rank, nitrd, np.ones(10, bool), [0.1, 0.3, 1.0])
    assert [p["k"] for p in c] == [1, 3, 10]
    assert [p["recall"] for p in c] == pytest.approx([1 / 3, 2 / 3, 1.0])
    A = rank <= 3
    B = np.isin(rank, [1, 2, 4])
    d, pattern = rm.disagreement({"A": A, "B": B}, np.ones(10, bool), nitrd, np.ones(10, bool),
                                 np.zeros(10, bool), ["X"] * 10)
    assert d["size"] == 2 and d["intersection"] == 2 and d["union"] == 4
    assert d["patterns"]["A"]["nitrd"] == 1 and d["patterns"]["B"]["nitrd"] == 0
    assert d["nitrd_missed_by_every_arm"] == 1


def test_core_level_any_rule():
    m = np.array([1, 0, 0, 0], bool)
    nitrd = np.array([0, 1, 1, 0], bool)
    o = rm.core_level(m, nitrd, np.ones(4, bool), np.ones(4, bool), ["a", "a", "b", "c"])
    assert (o["positive_cores"], o["flagged_cores"], o["hits"]) == (2, 1, 1)
    assert o["recall"] == 0.5 and o["precision"] == 1.0
