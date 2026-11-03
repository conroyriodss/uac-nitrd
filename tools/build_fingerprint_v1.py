"""Build the Task 1 fingerprint v1 from FY2021 (FINGERPRINT_ID = task1-fingerprint-v1), under the read guard.

Inputs (allow-list A1-A2; the guard refuses everything else, see docs/TASK1_READ_GUARD_SPEC.md):
  $SEED_ROOT/fy2019, fy2020: universe text, no labels (term stabilization: vocabulary + IDF only);
  $SEED_ROOT/fy2021: universe text + has_any_category + cat329 (the only labels used).

Steps (pre-registration sections 4-5):
  1. universe = reconstructed QVR filter (workflow/qvr_universe.py), each year;
  2. vocabulary: unigrams + bigrams with document frequency >= MIN_DF_PER_YEAR in EACH of the FY2019,
     FY2020 and FY2021 universes, and pooled document share <= MAX_DF; IDF (smooth) on the pooled
     FY2019-2021 universe text;
  3. labels: FY2021 universe awards with any spending category; y = category 329. Uncategorized FY2021
     awards are never negatives;
  4. C chosen by 5-fold CV grouped by core project (GroupKFold over the whole FY2021 universe; fits on
     the categorized training-fold awards; metric = average precision on the categorized test-fold
     awards; one-standard-error rule: the smallest C within one SE of the best mean AP);
  5. calibration: out-of-fold scores rank the whole FY2021 universe (uncategorized included, as at scoring
     time); the operating fraction is the smallest universe share whose shortlist reaches recall
     TARGET_RECALL of the FY2021 NITRD awards;
  6. final model: all categorized FY2021 universe awards at the chosen C.

Outputs (write-once) in build/task1_fingerprint_v1/: model.json.gz, shortlist_rule.json,
calibration.json, READ_MANIFEST.json.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow import build_guard as bg  # noqa: E402

FINGERPRINT_ID = "task1-fingerprint-v1"
OUT = Path(os.environ.get("UAC_NITRD_TASK1_FP_OUT", ROOT / "build" / "task1_fingerprint_v1"))
YEARS, LABEL_FY = (2019, 2020, 2021), 2021
MIN_DF_PER_YEAR, MAX_DF = 5, 0.5
C_GRID = (0.25, 1.0, 4.0, 16.0, 64.0, 256.0)
FOLDS = 5
TARGET_RECALL = 0.95
PREVALENCE_MULTIPLES = (1, 2, 3)
CURVE = tuple(round(0.005 * i, 3) for i in range(1, 81))  # 0.5% .. 40% of the universe


def log(msg: str) -> None:
    print(f"{datetime.now(UTC).strftime('%H:%M:%S')} {msg}", flush=True)


def load_year(guard: bg.Guard, fy: int) -> list[dict]:
    d = bg.SEED_ROOT / f"fy{fy}"
    summary = json.loads(guard.read_bytes(d / "FETCH_SUMMARY.json"))
    raw = guard.read_bytes(d / summary["file"])
    if hashlib.sha256(raw).hexdigest() != summary["sha256_gz"]:
        raise RuntimeError(f"FY{fy}: seed file sha256 differs from its FETCH_SUMMARY")
    rows = [json.loads(line) for line in gzip.decompress(raw).decode("utf-8").split("\n") if line]
    if len(rows) != summary["records"] or any(r["fy"] != fy for r in rows):
        raise RuntimeError(f"FY{fy}: record count or FY mismatch")
    if fy != LABEL_FY and any("cat329" in r or "has_any_category" in r for r in rows):
        raise RuntimeError(f"FY{fy}: label fields present in a text-only year")
    return rows


def curve_point(order, nitrd, categorized, k: int) -> dict:
    top = order[:k]
    tp = int(nitrd[top].sum())
    cat_top = int(categorized[top].sum())
    return {"k": k, "recall": tp / int(nitrd.sum()), "precision": tp / cat_top if cat_top else None,
            "precision_uncat_as_negative": tp / k if k else None,
            "uncategorized_on_shortlist": int(k - cat_top), "tp": tp}


def main() -> int:
    if OUT.exists():
        raise SystemExit(f"{OUT} exists; the fingerprint is built once")
    guard = bg.Guard("build", roots=(bg.SEED_ROOT,)).install()
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score
    from sklearn.model_selection import GroupKFold

    from workflow import fingerprint as fp
    from workflow import qvr_universe as qu

    t0 = time.time()
    years, drops = {}, {}
    for fy in YEARS:
        rows = load_year(guard, fy)
        drops[fy] = {}
        for r in rows:
            why = qu.exclusion(r)
            drops[fy][why or "in_universe"] = drops[fy].get(why or "in_universe", 0) + 1
        years[fy] = [r for r in rows if qu.in_universe(r)]
        log(f"FY{fy}: {len(rows)} records, universe {len(years[fy])}")

    # 2. vocabulary: present (df >= MIN_DF_PER_YEAR) in every year; IDF on the pooled text.
    keep = None
    for fy in YEARS:
        cv = fp.count_vectorizer(min_df=MIN_DF_PER_YEAR)
        cv.fit(fp.text_of(r) for r in years[fy])
        terms = set(cv.vocabulary_)
        keep = terms if keep is None else keep & terms
        log(f"FY{fy}: {len(terms)} terms with df >= {MIN_DF_PER_YEAR}; intersection {len(keep)}")
        del cv
    vocab = sorted(keep)
    cv = fp.count_vectorizer(vocabulary={t: i for i, t in enumerate(vocab)})
    counts = {fy: cv.transform([fp.text_of(r) for r in years[fy]]) for fy in YEARS}
    pooled_df = sum(np.asarray((c > 0).sum(axis=0)).ravel() for c in counts.values())
    n_pooled = sum(c.shape[0] for c in counts.values())
    ok = pooled_df <= MAX_DF * n_pooled
    vocab = [t for t, k in zip(vocab, ok) if k]
    idf = fp.smooth_idf(pooled_df[ok].astype(np.float64), n_pooled)
    c21 = counts[LABEL_FY][:, np.flatnonzero(ok)]
    del counts
    x = fp.tfidf(c21, idf)
    log(f"vocabulary {len(vocab)} terms (max_df dropped {int((~ok).sum())}); X {x.shape}")

    u = years[LABEL_FY]
    appl = np.array([r["appl_id"] for r in u], dtype=np.int64)
    cores = np.array([r["core_project_num"] or f"appl{r['appl_id']}" for r in u])
    categorized = np.array([bool(r["has_any_category"]) for r in u])
    nitrd = np.array([bool(r["cat329"]) for r in u])
    n, n_nitrd = len(u), int(nitrd.sum())
    log(f"FY2021 universe {n}: NITRD {n_nitrd}, uncategorized {int((~categorized).sum())}")

    def fit(idx, c):
        m = LogisticRegression(C=c, solver="liblinear", max_iter=1000)
        m.fit(x[idx], nitrd[idx])
        return m

    folds = list(GroupKFold(n_splits=FOLDS).split(np.zeros(n), groups=cores))
    cv_ap, oof_by_c = {}, {}
    for c in C_GRID:
        oof, aps = np.zeros(n), []
        for tr, te in folds:
            m = fit(tr[categorized[tr]], c)
            oof[te] = m.decision_function(x[te])
            te_c = te[categorized[te]]
            aps.append(float(average_precision_score(nitrd[te_c], oof[te_c])))
        cv_ap[c], oof_by_c[c] = aps, oof
        log(f"C={c}: AP per fold {[round(a, 4) for a in aps]} mean {np.mean(aps):.4f}")
    # One-standard-error rule: the most regularized C whose mean AP is within one standard error of
    # the best mean (AP plateaus as C grows; the smaller C keeps coefficients smaller and steadier).
    top_c = max(C_GRID, key=lambda c: np.mean(cv_ap[c]))
    se = float(np.std(cv_ap[top_c], ddof=1) / np.sqrt(FOLDS))
    best_c = min(c for c in C_GRID if np.mean(cv_ap[c]) >= np.mean(cv_ap[top_c]) - se)
    oof = oof_by_c[best_c]

    order = fp.rank(oof, appl)
    hits = np.cumsum(nitrd[order])
    k95 = int(np.searchsorted(hits, np.ceil(TARGET_RECALL * n_nitrd)) + 1)
    fraction = k95 / n
    prevalence = n_nitrd / n
    oof_p = 1.0 / (1.0 + np.exp(-oof))
    calib = {
        "fingerprint_id": FINGERPRINT_ID, "label_fy": LABEL_FY, "universe_rule": qu.UNIVERSE_RULE_ID,
        "universe_drops": drops, "universe_sizes": {fy: len(years[fy]) for fy in YEARS},
        "fy2021": {"universe": n, "nitrd": n_nitrd, "uncategorized": int((~categorized).sum()),
                   "prevalence": prevalence, "uncategorized_share": float((~categorized).mean())},
        "vocabulary": {"terms": len(vocab), "min_df_per_year": MIN_DF_PER_YEAR, "max_df": MAX_DF,
                       "idf_docs": n_pooled},
        "cv": {"folds": FOLDS, "grouping": "core_project_num", "metric": "average_precision",
               "ap_by_C": {str(c): v for c, v in cv_ap.items()}, "chosen_C": best_c,
               "selection": "one-standard-error rule", "best_mean_C": top_c, "best_mean_se": se},
        "calibration": {"target_recall": TARGET_RECALL, "k": k95, "fraction": fraction,
                        "point": curve_point(order, nitrd, categorized, k95)},
        "secondary_points": {f"{m}x_prevalence": curve_point(order, nitrd, categorized,
                                                             fp.shortlist_size(m * prevalence, n))
                             for m in PREVALENCE_MULTIPLES},
        "curve": [{"fraction": f, **curve_point(order, nitrd, categorized, fp.shortlist_size(f, n))}
                  for f in CURVE],
        "count_check": {"sum_oof_p_categorized": float(oof_p[categorized].sum()),
                        "sum_oof_p_universe": float(oof_p.sum()), "nitrd": n_nitrd},
        "oof_ap_categorized": float(average_precision_score(nitrd[categorized], oof[categorized])),
    }
    log(f"chosen C={best_c}; recall {TARGET_RECALL} at k={k95} = {fraction:.4%} of the universe")

    final = fit(np.flatnonzero(categorized), best_c)
    model = fp.Model(vocab, idf, final.coef_.ravel(), float(final.intercept_[0]),
                     meta={"fingerprint_id": FINGERPRINT_ID, "C": best_c, "label_fy": LABEL_FY,
                           "train_records": int(categorized.sum()), "train_nitrd": n_nitrd,
                           "universe_rule": qu.UNIVERSE_RULE_ID})
    blob = model.to_bytes()
    reloaded = fp.Model.from_bytes(blob)
    drift = float(np.max(np.abs(reloaded.score(reloaded.transform([fp.text_of(r) for r in u[:2000]]))
                                - model.score(x[:2000]))))
    if drift > 1e-4:
        raise RuntimeError(f"stored model reproduces scores only to {drift}")
    top = np.argsort(-model.coef)
    calib["top_terms"] = {"positive": [[vocab[i], round(float(model.coef[i]), 4)] for i in top[:40]],
                          "negative": [[vocab[i], round(float(model.coef[i]), 4)] for i in top[::-1][:20]]}
    calib["stored_model_max_score_drift"] = drift

    OUT.mkdir(parents=True)
    (OUT / "model.json.gz").write_bytes(blob)
    rule = {"fingerprint_id": FINGERPRINT_ID, "shortlist_fraction": fraction,
            "k_formula": "ceil(shortlist_fraction x universe size)",
            "order": "model score descending, ties by appl_id ascending",
            "calibrated_on": f"FY{LABEL_FY} out-of-fold, recall {TARGET_RECALL}",
            "secondary_fractions": {f"{m}x_prevalence": m * prevalence for m in PREVALENCE_MULTIPLES},
            "universe_rule": qu.UNIVERSE_RULE_ID,
            "model_sha256": hashlib.sha256(blob).hexdigest()}
    (OUT / "shortlist_rule.json").write_text(json.dumps(rule, indent=1, sort_keys=True) + "\n")
    (OUT / "calibration.json").write_text(json.dumps(calib, indent=1, sort_keys=True) + "\n")
    sha = guard.write_manifest(OUT / "READ_MANIFEST.json")
    log(f"done in {time.time() - t0:.0f}s; READ_MANIFEST sha256 {sha}")
    print(json.dumps({"rule": rule, "calibration": calib["calibration"], "cv": calib["cv"],
                      "secondary": calib["secondary_points"], "fy2021": calib["fy2021"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
