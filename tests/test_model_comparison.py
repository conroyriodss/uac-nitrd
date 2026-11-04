"""Offline tests for the model-comparison harness, on hand-worked cases."""

import json

import numpy as np
import pytest

from workflow import model_comparison as mc

APPL = np.array([10, 20, 30, 40, 50, 60, 70, 80, 90, 100], dtype=np.int64)
CORES = ["C10", "C20", "C30", "C40", "", "C60", "C70", "C80", "C90", "C100"]


def uni(labelled=True):
    return mc.Universe(appl=APPL, core=CORES, ic=["X"] * 5 + ["Y"] * 5,
                       nitrd=np.array([1, 1, 1, 1, 0, 0, 0, 0, 0, 0], bool) if labelled else None,
                       categorized=np.array([1] * 9 + [0], bool) if labelled else None)


def ranked(name, score):
    return mc.Arm(name, "ranked", score=np.array(score, float))


def test_ranked_shortlist_ties_by_appl_id_and_recall():
    u = uni()
    tie = ranked("T", [1.0] * 10)
    assert APPL[mc.membership(tie, u, 0.3)].tolist() == [10, 20, 30]
    a = ranked("A", [9, 8, 7, 6, 5, 4, 3, 2, 1, 0])
    p = mc.point(a, u, 0.3)
    assert p["shortlist_size"] == 3 and p["recall"] == 0.75 and p["precision_categorized"] == 1.0
    assert mc.point(a, u, 0.4)["recall"] == 1.0


def test_shortlist_size_is_exact_for_integer_fractions():
    assert mc.shortlist_size(7284 / 63074, 63074) == 7284
    assert mc.shortlist_size(mc.PRIMARY_FRACTION, 63074) == 7284


def test_kappa_known_values():
    w = np.ones(4)
    assert mc.kappa(np.array([1, 1, 0, 0], bool), np.array([1, 0, 1, 0], bool), w) == 0.0
    assert mc.kappa(np.array([1, 0, 1, 0], bool), np.array([1, 0, 1, 0], bool), w) == 1.0
    assert mc.kappa(np.array([1, 1, 0, 0], bool), np.array([0, 0, 1, 1], bool), w) == -1.0


def test_sampled_arm_weighted_cut_and_recall():
    u = uni()
    w = np.zeros(10)
    w[[0, 4, 8]] = [2, 3, 5]
    s = np.full(10, np.nan)
    s[[0, 4, 8]] = [0.9, 0.8, 0.1]
    c = mc.Arm("C", "sampled", score=s, weight=w)
    assert APPL[mc.membership(c, u, 0.5)].tolist() == [10, 50]
    assert mc.point(c, u, 0.5)["recall"] == 1.0
    assert mc.point(c, u, 0.1)["recall"] == 0.0


def test_carry_forward_and_disagreement_reveal():
    u = uni()
    a = ranked("A", [9, 8, 7, 6, 5, 4, 3, 2, 1, 0])
    b = ranked("B", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
    cf = mc.carry_forward(u, {"C10", "C40", ""}, 2023, 2024)
    assert APPL[cf.members].tolist() == [10, 40]  # empty core never carries
    assert "exposed prior-year labels" in cf.note
    d = mc.disagreement([a, b, cf], u, "reveal", 0.3)
    s = d["summary"]
    assert s["size"] == 7 and s["intersection_size"] == 0
    assert dict(d["rows"]) == {10: "A+CF", 20: "A", 30: "A", 40: "CF", 80: "B", 90: "B", 100: "B"}
    assert s["share_of_all_nitrd_in_disagreement"] == 1.0 and s["nitrd_missed_by_every_arm"] == 0
    assert s["patterns"]["A"] == {"size": 2, "nitrd": 2, "nitrd_rate": 1.0}
    pre = mc.disagreement([a, b, cf], uni(False), "prereveal", 0.3)["summary"]
    assert "share_of_all_nitrd_in_disagreement" not in pre and pre["size"] == 7
    bld = mc.disagreement([a, b, cf], u, "build", 0.3)["summary"]
    assert "nitrd_in_disagreement" not in bld


def test_combined_puts_carry_forward_first():
    u = uni()
    a = ranked("A", [9, 8, 7, 6, 5, 4, 3, 2, 1, 0])
    cf = mc.carry_forward(u, {"C90", "C40"}, 2023, 2024)
    ac = mc.combined(a, cf, u)
    assert APPL[mc.order(ac.score, APPL)][:4].tolist() == [40, 90, 10, 20]


def test_compare_modes_and_determinism():
    a = ranked("A", [9, 8, 7, 6, 5, 4, 3, 2, 1, 0])
    b = ranked("B", [9, 8, 1, 6, 0, 4, 3, 2, 7, 5])
    with pytest.raises(ValueError):
        mc.compare(uni(), [a, b], "prereveal")
    with pytest.raises(ValueError):
        mc.compare(uni(False), [a, b], "reveal")
    r1 = json.dumps(mc.compare(uni(), [a, b], "build"), sort_keys=True)
    r2 = json.dumps(mc.compare(uni(), [a, b], "build"), sort_keys=True)
    assert r1 == r2
    rep = json.loads(r1)["report"]
    assert rep["k_at_equal_burden"] == 2 and set(rep["kappa_matrix"]) == {"A|B"}
    assert rep["kappa_matrix"]["A|B"]["kappa"] == 1.0  # both shortlists = {10, 20}
