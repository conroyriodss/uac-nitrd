"""Task 1 reveal metrics (REVEAL_METRICS_ID = task1-reveal-metrics-v1); pre-registration sections 6, 6a, 7.

Pure functions over arrays aligned to one scoring year's universe (no I/O, no clocks), so the same code
scores FY2024 (Tier 2 / 2x), FY2022-23 (Tier 3) and FY2026 (Tier 1), and is tested on hand-worked cases.

Definitions (pre-registration task1-prereg-v1-2026-11-04T18:00:50Z):
* Shortlists are cut on the WHOLE universe (K = ceil(f x N), N includes File A awards); metrics are then
  computed inside a scope (Tier 2 = non-File-A, Tier 2x = File A, and each one's new-core subset).
* Three-state label: nitrd; categorized (nitrd or another spending category); uncategorized otherwise.
* Recall = shortlisted NITRD / NITRD in scope (uncategorized awards are never NITRD, so recall is the same
  under both uncategorized treatments).
* Precision, primary = shortlisted NITRD / shortlisted categorized; sensitivity = / all shortlisted.
* Cohen's kappa, shortlist membership vs listing membership: primary on the categorized awards of the
  scope; sensitivity on all awards with uncategorized = not NITRD. 95% CI: percentile bootstrap over core
  projects (2,000 resamples; seed 20261103 + a fixed per-statistic offset, listed in each output).
* Machine-machine kappa (arms pairwise) on all awards of the scope, label-free, same bootstrap.
* Recall bootstrap CIs (same cluster bootstrap) are reported in addition; they are not a criterion.
"""

from __future__ import annotations

import math

import numpy as np

REVEAL_METRICS_ID = "task1-reveal-metrics-v1"
BOOT, BOOT_SEED, BATCH = 2000, 20261103, 50
BENCHMARKS = {
    "mateen_2013_kappa": {"value": 0.56, "what": "titles vs titles+abstracts screening, 96-97% agreement",
                          "ref": "Clin Epidemiol 2013;5:89-95, doi:10.2147/CLEP.S43118"},
    "neves_2023_kappa": {"value": 0.62, "what": "automatic classification of experimental models",
                         "ref": "J Biomed Semant 2023;14(1):13, doi:10.1186/s13326-023-00292-w"},
    "human_sr_screening_kappa": {"value": 0.72, "ref": "BMJ Open 2024;14(3):e076912"},
    "nih_peer_review_icc": {"value": 0.0, "ref": "Pier et al., PNAS 2018;115(12):2952-2957"},
    "use": "interpreted against, not tested against (pre-registration section 6 item 7)",
}


def shortlist_size(fraction: float, n: int) -> int:
    return int(math.ceil(fraction * n - 1e-9))  # identical to workflow/model_comparison.shortlist_size


def kappa_counts(n11, n10, n01, n00):
    """Cohen's kappa from 2x2 counts; works elementwise on arrays."""
    n11, n10, n01, n00 = (np.asarray(v, dtype=float) for v in (n11, n10, n01, n00))
    n = n11 + n10 + n01 + n00
    po = (n11 + n00) / n
    pa, pb = (n11 + n10) / n, (n11 + n01) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(pe < 1, (po - pe) / (1 - pe), 1.0)


class Cores:
    """Core-project index for the cluster bootstrap."""

    def __init__(self, core: list[str]):
        uniq: dict[str, int] = {}
        self.idx = np.array([uniq.setdefault(c or f"<none:{i}>", len(uniq)) for i, c in enumerate(core)], dtype=np.int64)
        self.n = len(uniq)

    def sums(self, cols: np.ndarray) -> np.ndarray:
        """Per-core column sums of a (n_awards x c) array."""
        out = np.zeros((self.n, cols.shape[1]))
        np.add.at(out, self.idx, cols)
        return out

    def boot(self, cols: np.ndarray, stat, seed: int, scope: np.ndarray) -> np.ndarray:
        """stat(sums over resampled cores) for BOOT resamples of the cores present in scope."""
        per = self.sums(cols * scope[:, None])
        present = np.flatnonzero(self.sums(scope[:, None].astype(float))[:, 0] > 0)
        per = per[present]
        m = len(present)
        rng = np.random.default_rng(seed)
        out = []
        for b0 in range(0, BOOT, BATCH):
            nb = min(BATCH, BOOT - b0)
            draws = rng.integers(0, m, (nb, m))
            counts = np.bincount((draws + np.arange(nb)[:, None] * m).ravel(), minlength=nb * m).reshape(nb, m)
            out.append(stat(counts @ per))
        return np.concatenate(out)


def _ci(v: np.ndarray) -> list[float]:
    v = v[np.isfinite(v)]
    return [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] if len(v) else [None, None]


def _confusion(m, y):
    return np.stack([m & y, m & ~y, ~m & y, ~m & ~y], axis=1).astype(float)


def arm_vs_listing(m, nitrd, categorized, scope, cores: Cores, seed: int) -> dict:
    """Every per-arm metric of pre-registration section 6 inside one scope."""
    m, nitrd, categorized, scope = (np.asarray(v, bool) for v in (m, nitrd, categorized, scope))
    prim = scope & categorized
    tp = int((m & nitrd & scope).sum())
    pos = int((nitrd & scope).sum())
    sl, sl_cat = int((m & scope).sum()), int((m & prim).sum())
    out = {"n": int(scope.sum()), "nitrd": pos, "uncategorized": int((scope & ~categorized).sum()),
           "shortlisted": sl, "shortlisted_uncategorized": sl - sl_cat, "tp": tp,
           "recall": tp / pos if pos else None,
           "precision_primary": tp / sl_cat if sl_cat else None,
           "precision_sensitivity": tp / sl if sl else None,
           "share_of_scope_shortlisted": sl / int(scope.sum()) if scope.sum() else None}
    if pos:
        rc = cores.boot(np.stack([m & nitrd, nitrd], 1).astype(float),
                        lambda s: s[:, 0] / np.where(s[:, 1] > 0, s[:, 1], np.nan), seed, scope)
        out["recall_ci95_core_bootstrap"] = _ci(rc)
    for name, sc, off in (("primary", prim, 1), ("sensitivity", scope, 2)):
        c = _confusion(m, nitrd)
        k = float(kappa_counts(*(c * sc[:, None]).sum(0)))
        kb = cores.boot(c, lambda s: kappa_counts(s[:, 0], s[:, 1], s[:, 2], s[:, 3]), seed + off, sc)
        out[f"kappa_{name}"] = k
        out[f"kappa_{name}_ci95"] = _ci(kb)
    out["bootstrap"] = {"resamples": BOOT, "unit": "core project", "seeds": {"recall": seed, "kappa_primary": seed + 1,
                                                                          "kappa_sensitivity": seed + 2}}
    return out


def pairwise_kappa(members: dict[str, np.ndarray], scope, cores: Cores, seed: int) -> dict:
    names, out = list(members), {}
    for i, a in enumerate(names):
        for j, b in enumerate(names):
            if j <= i:
                continue
            c = _confusion(np.asarray(members[a], bool), np.asarray(members[b], bool))
            s = seed + 100 * i + j
            kb = cores.boot(c, lambda t: kappa_counts(t[:, 0], t[:, 1], t[:, 2], t[:, 3]), s, scope)
            out[f"{a}|{b}"] = {"kappa": float(kappa_counts(*(c * scope[:, None]).sum(0))), "ci95": _ci(kb),
                               "seed": s, "n": int(scope.sum())}
    return out


def disagreement(members: dict[str, np.ndarray], scope, nitrd, categorized, new, ic: list[str]) -> dict:
    names = list(members)
    M = np.stack([np.asarray(members[n], bool) for n in names])
    any_, all_ = M.any(0), M.all(0)
    dis = any_ & ~all_ & scope
    pattern = np.array(["+".join(n for n, inside in zip(names, col) if inside) or "none" for col in M.T])
    pats = {}
    for p in sorted(set(pattern[dis])):
        sel = dis & (pattern == p)
        cat = sel & categorized
        pats[p] = {"size": int(sel.sum()), "new_core_share": float((sel & new).sum() / sel.sum()),
                   "nitrd": int((sel & nitrd).sum()), "categorized": int(cat.sum()),
                   "nitrd_rate_categorized": float((sel & nitrd).sum() / cat.sum()) if cat.sum() else None,
                   "ic_mix_top10": dict(sorted(_counts([ic[i] for i in np.flatnonzero(sel)]).items(),
                                               key=lambda kv: (-kv[1], kv[0]))[:10])}
    pos = int((nitrd & scope).sum())
    return {"arms": names, "size": int(dis.sum()), "union": int((any_ & scope).sum()),
            "intersection": int((all_ & scope).sum()), "patterns": pats,
            "nitrd_in_disagreement": int((dis & nitrd).sum()),
            "share_of_scope_nitrd_in_disagreement": float((dis & nitrd).sum() / pos) if pos else None,
            "nitrd_missed_by_every_arm": int((~any_ & nitrd & scope).sum())}, pattern


def _counts(values) -> dict:
    c: dict[str, int] = {}
    for v in values:
        c[v or ""] = c.get(v or "", 0) + 1
    return c


def curve(rank: np.ndarray, nitrd, scope, fractions) -> list[dict]:
    """Recall vs fraction for a ranked arm (rank 1-based over the whole universe)."""
    n, pos = len(rank), int((np.asarray(nitrd, bool) & scope).sum())
    out = []
    for f in fractions:
        k = shortlist_size(f, n)
        m = rank <= k
        out.append({"fraction": f, "k": k, "recall": float((m & nitrd & scope).sum() / pos) if pos else None})
    return out


def core_level(m, nitrd, categorized, scope, core: list[str]) -> dict:
    """Core-level secondary ('any' rule): a core is positive if any of its scope awards is NITRD and
    flagged if any is shortlisted; cores with no categorized scope award are left out."""
    pos_c, flag_c, cat_c = set(), set(), set()
    for i in np.flatnonzero(scope):
        c = core[i]
        if categorized[i]:
            cat_c.add(c)
        if nitrd[i]:
            pos_c.add(c)
        if m[i]:
            flag_c.add(c)
    flag_c &= cat_c
    hit = len(pos_c & flag_c)
    return {"cores": len(cat_c), "positive_cores": len(pos_c), "flagged_cores": len(flag_c), "hits": hit,
            "recall": hit / len(pos_c) if pos_c else None, "precision": hit / len(flag_c) if flag_c else None}
