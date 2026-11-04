"""Task 1 model-comparison harness (COMPARISON_ID = task1-model-comparison-v1); pre-registration section 6a.

One harness for every year: FY2021 (build, now) and, unchanged, FY2024-non-File-A and FY2026 (reveal).
It is NOT under the build guard: it is evaluation code, and the carry-forward baseline it computes uses
exposed prior-year labels by design (labelled so everywhere).

Arms (per-award inputs, aligned to the year's universe):
  ranked   a score per universe award; shortlist at fraction f = top ceil(f x N) by score descending,
           ties by appl_id ascending (arms A and B, and the combined A+CF arm);
  sampled  a score and an inverse-probability weight for a declared sample (arm C); its shortlist at f is
           the scored awards, in the same order, whose cumulative weight stays within f x N. Statistics
           involving it are weighted and computed on its sample only;
  set      a fixed membership set (carry-forward, CF): not a ranking, so it has one size, K_CF.

Outputs at equal burden (arm A's calibrated fraction, PRIMARY_FRACTION): recall@K per arm; each arm's
recall-vs-fraction curve (1%..30% plus PRIMARY_FRACTION); a pairwise Cohen's kappa matrix on binary
shortlist membership with bootstrap CIs; the disagreement set (awards in some but not all universe-level
shortlists) with its size and membership patterns. Mode "reveal" additionally reports, inside the
disagreement set, the share of all true NITRD awards it contains and the NITRD rate per pattern (the
awards human review should prioritise). Mode "prereveal" uses no labels at all.

Everything is deterministic: fixed tie-breaks, fixed bootstrap seeds, no clocks.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

COMPARISON_ID = "task1-model-comparison-v1"
PRIMARY_FRACTION = 0.11548340045026477  # arm A (task1-fingerprint-v1) calibrated operating fraction
CURVE = tuple(round(0.01 * i, 2) for i in range(1, 31)) + (PRIMARY_FRACTION,)
BOOT, BOOT_SEED = 2000, 20261103
MODES = ("build", "prereveal", "reveal")
CF_LABEL = "carry-forward (uses exposed prior-year labels; not built under build_guard)"


@dataclass
class Universe:
    appl: np.ndarray                 # int64, one row per universe award
    core: list[str]
    ic: list[str]
    nitrd: np.ndarray | None = None  # bool; None in prereveal mode
    categorized: np.ndarray | None = None

    @property
    def n(self) -> int:
        return len(self.appl)


@dataclass
class Arm:
    name: str
    kind: str                        # "ranked" | "sampled" | "set"
    score: np.ndarray | None = None  # float, NaN where unscored (sampled arms)
    weight: np.ndarray | None = None  # sampled arms: IPW weight where scored, 0 elsewhere
    members: np.ndarray | None = None  # set arms
    note: str = ""
    inputs: dict = field(default_factory=dict)

    @property
    def scored(self) -> np.ndarray:
        if self.kind == "sampled":
            return self.weight > 0
        return np.ones(len(self.score if self.score is not None else self.members), bool)


def align(u: Universe, appl_ids, values, fill=np.nan) -> np.ndarray:
    """Values keyed by appl_id -> array aligned to the universe; every key must be a universe award."""
    pos = {int(a): i for i, a in enumerate(u.appl.tolist())}
    out = np.full(u.n, fill, dtype=float)
    for a, v in zip(appl_ids, values):
        if int(a) not in pos:
            raise ValueError(f"appl_id {a} is not in the universe")
        out[pos[int(a)]] = v
    return out


def order(score: np.ndarray, appl: np.ndarray) -> np.ndarray:
    """Score descending, ties by appl_id ascending; NaN last."""
    s = np.where(np.isnan(score), -np.inf, score)
    return np.lexsort((appl, -s))


def shortlist_size(fraction: float, n: int) -> int:
    return int(math.ceil(fraction * n - 1e-9))  # the epsilon keeps K_CF / N -> K_CF exact


def membership(arm: Arm, u: Universe, fraction: float) -> np.ndarray:
    if arm.kind == "set":
        return arm.members.copy()
    o = order(arm.score, u.appl)
    m = np.zeros(u.n, bool)
    if arm.kind == "ranked":
        m[o[:shortlist_size(fraction, u.n)]] = True
        return m
    o = o[arm.weight[o] > 0]
    cum = np.cumsum(arm.weight[o])
    m[o[cum <= fraction * u.n + 1e-9]] = True
    return m


def _w(arm_list: list[Arm], n: int) -> tuple[np.ndarray, np.ndarray]:
    """Scope + weights for statistics over these arms: the sampled arm's sample if any, else everything."""
    sampled = [a for a in arm_list if a.kind == "sampled"]
    if len(sampled) > 1:
        raise ValueError("at most one sampled arm per statistic")
    if sampled:
        w = sampled[0].weight
        return np.flatnonzero(w > 0), w
    return np.arange(n), np.ones(n)


def recall(mask: np.ndarray, nitrd: np.ndarray, scope: np.ndarray, w: np.ndarray) -> float:
    pos = w[scope] * nitrd[scope]
    return float((pos * mask[scope]).sum() / pos.sum())


def point(arm: Arm, u: Universe, fraction: float) -> dict:
    m = membership(arm, u, fraction)
    scope, w = _w([arm], u.n)
    out = {"fraction": fraction, "shortlist_size": float((w[scope] * m[scope]).sum())}
    if u.nitrd is not None:
        tp = float((w[scope] * (m & u.nitrd)[scope]).sum())
        cat = float((w[scope] * (m & u.categorized)[scope]).sum())
        out.update(recall=recall(m, u.nitrd, scope, w), precision_categorized=tp / cat if cat else None)
    return out


def kappa(a: np.ndarray, b: np.ndarray, w: np.ndarray) -> float:
    sw = w.sum()
    po = (w * (a == b)).sum() / sw
    pa, pb = (w * a).sum() / sw, (w * b).sum() / sw
    pe = pa * pb + (1 - pa) * (1 - pb)
    return float((po - pe) / (1 - pe)) if pe < 1 else 1.0


def kappa_matrix(arms: list[Arm], u: Universe, fraction: float = PRIMARY_FRACTION) -> dict:
    mem = {a.name: membership(a, u, fraction) for a in arms}
    out = {}
    for i, a in enumerate(arms):
        for j, b in enumerate(arms):
            if j <= i:
                continue
            scope, w = _w([a, b], u.n)
            x, y, ws = mem[a.name][scope], mem[b.name][scope], w[scope]
            rng = np.random.default_rng(BOOT_SEED + 100 * i + j)
            boot = []
            for _ in range(BOOT):
                idx = rng.integers(0, len(scope), len(scope))
                boot.append(kappa(x[idx], y[idx], ws[idx]))
            out[f"{a.name}|{b.name}"] = {
                "kappa": kappa(x, y, ws), "ci95": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))],
                "scope": "sample of " + next(c.name for c in (a, b) if c.kind == "sampled")
                         if any(c.kind == "sampled" for c in (a, b)) else "universe",
                "weighted": any(c.kind == "sampled" for c in (a, b)), "n": int(len(scope))}
    return out


def disagreement(arms: list[Arm], u: Universe, mode: str, fraction: float = PRIMARY_FRACTION) -> dict:
    """Awards on some but not all of the shortlists of these arms (universe-level arms only)."""
    if any(a.kind == "sampled" for a in arms):
        raise ValueError("the universe-level disagreement set takes ranked and set arms only")
    names = [a.name for a in arms]
    M = np.stack([membership(a, u, fraction) for a in arms])
    any_, all_ = M.any(0), M.all(0)
    dis = any_ & ~all_
    pattern = np.array(["+".join(nm for nm, inside in zip(names, col) if inside) for col in M.T])
    pats = sorted({p for p in pattern[dis]})
    out = {"arms": names, "size": int(dis.sum()), "union_size": int(any_.sum()),
           "intersection_size": int(all_.sum()), "share_of_universe": float(dis.mean()),
           "patterns": {p: {"size": int((pattern == p).sum())} for p in pats},
           "ic_mix": _counts([u.ic[i] for i in np.flatnonzero(dis)])}
    if mode == "reveal":
        n_nitrd = int(u.nitrd.sum())
        out["nitrd_in_disagreement"] = int((dis & u.nitrd).sum())
        out["share_of_all_nitrd_in_disagreement"] = float((dis & u.nitrd).sum() / n_nitrd)
        out["nitrd_rate_in_disagreement"] = float((dis & u.nitrd).sum() / dis.sum()) if dis.sum() else None
        out["nitrd_missed_by_every_arm"] = int((~any_ & u.nitrd).sum())
        for p in pats:
            sel = pattern == p
            out["patterns"][p].update(nitrd=int((sel & u.nitrd).sum()),
                                      nitrd_rate=float((sel & u.nitrd).sum() / sel.sum()))
    return {"summary": out, "rows": [(int(u.appl[i]), str(pattern[i])) for i in np.flatnonzero(dis)]}


def _counts(values) -> dict:
    c: dict[str, int] = {}
    for v in values:
        c[v or ""] = c.get(v or "", 0) + 1
    return dict(sorted(c.items(), key=lambda kv: (-kv[1], kv[0])))


def carry_forward(u: Universe, prior_nitrd_cores: set[str], prior_fy: int, fy: int) -> Arm:
    """CF: an award is predicted NITRD if its core project was NITRD in the prior fiscal year."""
    members = np.array([bool(c) and c in prior_nitrd_cores for c in u.core])
    return Arm("CF", "set", members=members,
               note=f"{CF_LABEL}: FY{prior_fy} NITRD cores -> FY{fy}")


def combined(a: Arm, cf: Arm, u: Universe) -> Arm:
    """A+CF: carry-forward picks first (ordered by arm A's score), then arm A's ranking; cut at K_A."""
    o = order(a.score, u.appl)
    rank = np.empty(u.n)
    rank[o] = np.arange(u.n)
    s = np.where(cf.members, 2.0 * u.n - rank, u.n - rank)  # every CF pick above every non-CF award
    return Arm("A+CF", "ranked", score=s, note="carry-forward picks first, then arm A; " + CF_LABEL)


def compare(u: Universe, arms: list[Arm], mode: str, fraction: float = PRIMARY_FRACTION) -> dict:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if mode == "prereveal" and u.nitrd is not None:
        raise ValueError("prereveal mode must not be given labels")
    if mode != "prereveal" and u.nitrd is None:
        raise ValueError(f"{mode} mode needs labels")
    report = {"comparison_id": COMPARISON_ID, "mode": mode, "universe": u.n, "equal_burden_fraction": fraction,
              "k_at_equal_burden": shortlist_size(fraction, u.n), "arms": {}, "curve_fractions": list(CURVE)}
    if u.nitrd is not None:
        report["universe_nitrd"] = int(u.nitrd.sum())
        report["universe_uncategorized"] = int((~u.categorized).sum())
    for a in arms:
        entry = {"kind": a.kind, "note": a.note, "inputs": a.inputs, "scored": int(a.scored.sum())}
        if a.kind == "set":
            entry["set"] = point(a, u, fraction)
            entry["k_cf"] = int(a.members.sum())
        else:
            entry["at_equal_burden"] = point(a, u, fraction)
            entry["curve"] = [point(a, u, f) for f in CURVE]
        report["arms"][a.name] = entry
    cfs = [a for a in arms if a.kind == "set"]
    if cfs:  # ranked arms also at K_CF (pre-registration rule 3)
        k_cf = int(cfs[0].members.sum())
        report["at_k_cf"] = {a.name: point(a, u, k_cf / u.n) for a in arms if a.kind != "set"}
    base = [a for a in arms if a.name != "A+CF"]  # A+CF is derived from A and CF: reported, not compared
    report["kappa_matrix"] = kappa_matrix(base, u, fraction)
    universe_arms = [a for a in base if a.kind != "sampled"]
    dis = disagreement(universe_arms, u, mode, fraction)
    report["disagreement"] = dis["summary"]
    kept = {a.name for a in universe_arms}
    report["disagreement"]["excluded"] = {a.name: ("sampled arm: universe membership unknown" if a.kind == "sampled"
                                                   else "derived from A and CF") for a in arms
                                          if a.name not in kept}
    return {"report": report, "rows": dis["rows"]}
