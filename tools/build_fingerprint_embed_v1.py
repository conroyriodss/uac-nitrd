"""Build Task 1 arm B (FINGERPRINT_ID = task1-fingerprint-embed-v1) under the read guard, mode "build".

Pre-registration section 6a, arm B: frozen hosted general-domain embeddings + logistic regression
(owner decision 2026-11-03: databricks-qwen3-embedding-0-6b, pinned by endpoint + served version).

Inputs, all read through the guard and listed in READ_MANIFEST:
  $SEED_ROOT/fy2021 (universe identity + has_any_category + cat329: the only labels used);
  $UAC_NITRD_TASK1_EMBED_ROOT/fy2021 (the stage-1 embedding cache, tools/embed_seed_embed_v1.py:
  FY2021 text embeddings, label-free), checked against the SHA-256 pinned below (EMBED_PIN).
The hosted encoder is not bit-deterministic at scale, so this fit never calls it: it reads the pinned
matrices, and a second run is byte-identical. FY2019-2020 embeddings exist in the cache (owner
decision) but the fit does not need them: arm B has no vocabulary to stabilize.

Steps (same protocol as arm A, tools/build_fingerprint_v1.py, except the features):
  1. universe = reconstructed QVR filter (workflow/qvr_universe.py), FY2021;
  2. features = the pinned FY2021 embedding matrix (title + abstract + PHR through the pinned
     endpoint, L2-normalized, rounded; workflow/embedding.py), rows matched to the universe by appl_id;
  3. labels: FY2021 universe awards with any spending category; y = category 329. Uncategorized
     FY2021 awards are never negatives;
  4. C by 5-fold CV on ARM A'S RECORDED FOLD ASSIGNMENT (build/task1_oof_scores_v1/arm_a/
     fold_assignment.i8, SHA-256 pinned as FOLD_PIN; core-grouped, checked here), fits on categorized
     training-fold awards, AP on categorized test-fold awards, one-standard-error rule (same C grid as
     arm A). Owner decision 2026-11-04: GroupKFold's assignment differs between scikit-learn 1.7.2
     (arm A) and 1.9.1, so arm B reads arm A's folds instead of recomputing them;
  5. calibration: out-of-fold scores rank the whole universe; the arm's own operating fraction is the
     smallest share reaching recall TARGET_RECALL; recall is also reported at arm A's fraction;
  6. final model on all categorized FY2021 universe awards at the chosen C.

Outputs (write-once): the model (model.json.gz: LR coefficients, the embedding pin, the exemplar bank;
JSON, no pickle; ~9.6 MB) on the volume at MODEL_DIR (owner decision 2026-11-04: not in git), and in
build/task1_fingerprint_embed_v1/: MODEL_POINTER.json (volume path + SHA-256 + bytes),
calibration.json, READ_MANIFEST.json.

Smoke mode (UAC_NITRD_TASK1_EMBED_SMOKE=N): every k-th universe award, about N, written to
UAC_NITRD_TASK1_FP_EMBED_OUT (required, never the canonical directory). Pipeline check only.
UAC_NITRD_TASK1_EMBED_UNPINNED_OK=1 allows a smoke run before EMBED_PIN is filled in.
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

FINGERPRINT_ID = "task1-fingerprint-embed-v1"
CANONICAL_OUT = ROOT / "build" / "task1_fingerprint_embed_v1"
EMBED_ROOT = Path(os.environ.get("UAC_NITRD_TASK1_EMBED_ROOT",
                                 "/Volumes/users/conroyri/nitrd_hackathon_v1_raw/task1_embed_v1"))
#: SHA-256 of the stage-1 FY2021 cache files (EMBED_SUMMARY.json, written once 2026-11-04 00:52Z;
#: FY2019 emb fe8c275a..., FY2020 emb c2f197ea... are pinned in their own summaries, not read here).
EMBED_PIN = {"fy2021.appl_id.i64le": "c173220cae1fbe92a51f6b0a9899212e2a6641137d89acbe5f72e4b07e381e52",
             "fy2021.emb.f32le": "69974f390015cbcf00357a59bd17aad675590ddc77e9095eb7556ff53b5229ba"}
#: Arm A's out-of-fold fold assignment (int8 fold index per FY2021 universe award, universe order),
#: written by tools/export_oof_scores_v1.py, which reproduced arm A's calibration exactly with it.
FOLD_FILE = ROOT / "build" / "task1_oof_scores_v1" / "arm_a" / "fold_assignment.i8"
FOLD_PIN = "f34c99f1220faca2e0b17c163d6d8422cd821f36a90b71e50b67f0e15951b6ef"
MODEL_DIR = Path(os.environ.get("UAC_NITRD_TASK1_EMBED_MODEL_DIR",
                                "/Volumes/users/conroyri/nitrd_hackathon_v1_raw/task1_fingerprint_embed_v1"))
SMOKE = int(os.environ.get("UAC_NITRD_TASK1_EMBED_SMOKE", "0") or 0)
OUT = Path(os.environ.get("UAC_NITRD_TASK1_FP_EMBED_OUT", CANONICAL_OUT))
LABEL_FY = 2021
C_GRID = (0.25, 1.0, 4.0, 16.0, 64.0, 256.0)  # arm A's grid
FOLDS = 5
TARGET_RECALL = 0.95
#: Arm A's calibrated operating fraction (build/task1_fingerprint_v1/shortlist_rule.json, model
#: sha256 b703083d...). Used only to report arm B's recall at equal burden.
PRIMARY_FINGERPRINT = "task1-fingerprint-v1"
PRIMARY_FRACTION = 0.11548340045026477
CURVE = tuple(round(0.005 * i, 3) for i in range(1, 81))  # 0.5% .. 40%, as arm A
NEG_EXEMPLARS, EXEMPLAR_SEED = 2000, 20261103
INTERPRETABILITY_NOTE = (
    "Arm B trades interpretability for semantics: its 1,024 coefficients act on dense embedding "
    "dimensions with no readable terms, so it cannot give arm A's per-term weights. In their place it "
    "explains a score by nearest exemplars: the FY2021 NITRD awards, and a fixed sample of FY2021 "
    "categorized non-NITRD awards, whose embeddings are closest (cosine) to the award, excluding the "
    "award's own core project. Similarity explains what the award resembles, not why the classifier "
    "weighs it.")


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
    return rows


def curve_point(order, nitrd, categorized, k: int) -> dict:
    top = order[:k]
    tp = int(nitrd[top].sum())
    cat_top = int(categorized[top].sum())
    return {"k": k, "recall": tp / int(nitrd.sum()), "precision": tp / cat_top if cat_top else None,
            "precision_uncat_as_negative": tp / k if k else None,
            "uncategorized_on_shortlist": int(k - cat_top), "tp": tp}


def main() -> int:
    if SMOKE and OUT == CANONICAL_OUT:
        raise SystemExit("smoke mode needs UAC_NITRD_TASK1_FP_EMBED_OUT (never the canonical directory)")
    model_dir = OUT if SMOKE else MODEL_DIR
    for d in {OUT, model_dir}:
        if d.exists():
            raise SystemExit(f"{d} exists; the fingerprint is built once")
    if "PENDING" in EMBED_PIN.values() and not os.environ.get("UAC_NITRD_TASK1_EMBED_UNPINNED_OK"):
        raise SystemExit("EMBED_PIN is not filled in; pin the stage-1 cache first")
    guard = bg.Guard("build", roots=(bg.SEED_ROOT, EMBED_ROOT, FOLD_FILE.parent)).install()
    import numpy as np
    import sklearn
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score

    from workflow import embedding as em
    from workflow import fingerprint as fp
    from workflow import qvr_universe as qu

    t0 = time.time()
    rows = load_year(guard, LABEL_FY)
    drops: dict[str, int] = {}
    for r in rows:
        why = qu.exclusion(r) or "in_universe"
        drops[why] = drops.get(why, 0) + 1
    u = [r for r in rows if qu.in_universe(r)]
    log(f"FY{LABEL_FY}: {len(rows)} records, universe {len(u)}")

    ed = EMBED_ROOT / f"fy{LABEL_FY}"
    esum = json.loads(guard.read_bytes(ed / "EMBED_SUMMARY.json"))
    blobs = {}
    for name, info in esum["files"].items():
        blobs[name] = guard.read_bytes(ed / name)
        got = hashlib.sha256(blobs[name]).hexdigest()
        if got != info["sha256"] or EMBED_PIN.get(name) not in (got, "PENDING"):
            raise RuntimeError(f"embedding cache {name}: sha256 {got} differs from its summary or EMBED_PIN")
    if esum["embedding_pin"] != em.PIN or esum["encoding"] != em.ENCODING:
        raise RuntimeError("embedding cache was made with a different pin / encoding")
    cache_appl = np.frombuffer(blobs[f"fy{LABEL_FY}.appl_id.i64le"], dtype="<i8")
    x = np.frombuffer(blobs[f"fy{LABEL_FY}.emb.f32le"], dtype="<f4").reshape(
        esum["files"][f"fy{LABEL_FY}.emb.f32le"]["shape"]).copy()
    if not np.array_equal(cache_appl, np.array([r["appl_id"] for r in u], dtype=np.int64)):
        raise RuntimeError("embedding cache rows do not match the FY2021 universe (appl_id order)")
    del blobs
    fold_raw = guard.read_bytes(FOLD_FILE)
    if hashlib.sha256(fold_raw).hexdigest() != FOLD_PIN:
        raise RuntimeError("arm A fold assignment differs from FOLD_PIN")
    fold_of = np.frombuffer(fold_raw, dtype="<i1").astype(np.int64)
    if len(fold_of) != len(u) or set(fold_of.tolist()) != set(range(FOLDS)):
        raise RuntimeError("arm A fold assignment does not cover the FY2021 universe in 5 folds")
    core_fold: dict[str, int] = {}
    for r, f in zip(u, fold_of.tolist()):
        c = r["core_project_num"] or f"appl{r['appl_id']}"
        if core_fold.setdefault(c, f) != f:
            raise RuntimeError(f"arm A folds split core {c}: not core-grouped")
    if SMOKE:
        keep = np.arange(0, len(u), max(1, len(u) // SMOKE))
        u, x, fold_of = [u[i] for i in keep], x[keep], fold_of[keep]
        log(f"SMOKE: {len(u)} awards")
    x_sha = hashlib.sha256(np.ascontiguousarray(x, dtype="<f4").tobytes()).hexdigest()
    log(f"embeddings {x.shape} from the pinned cache")

    appl = np.array([r["appl_id"] for r in u], dtype=np.int64)
    cores = np.array([r["core_project_num"] or f"appl{r['appl_id']}" for r in u])
    categorized = np.array([bool(r["has_any_category"]) for r in u])
    nitrd = np.array([bool(r["cat329"]) for r in u])
    n, n_nitrd = len(u), int(nitrd.sum())
    log(f"universe {n}: NITRD {n_nitrd}, uncategorized {int((~categorized).sum())}")

    def fit(idx, c):
        m = LogisticRegression(C=c, solver="liblinear", max_iter=1000)
        m.fit(x[idx], nitrd[idx])
        return m

    idx_all = np.arange(n)
    folds = [(idx_all[fold_of != k], idx_all[fold_of == k]) for k in range(FOLDS)]
    cv_ap, oof_by_c = {}, {}
    for c in C_GRID:
        oof, aps = np.zeros(n), []
        for tr, te in folds:
            m = fit(tr[categorized[tr]], c)  # uncategorized never enter a fit
            oof[te] = m.decision_function(x[te])
            te_c = te[categorized[te]]
            aps.append(float(average_precision_score(nitrd[te_c], oof[te_c])))
        cv_ap[c], oof_by_c[c] = aps, oof
        log(f"C={c}: AP per fold {[round(a, 4) for a in aps]} mean {np.mean(aps):.4f}")
    top_c = max(C_GRID, key=lambda c: np.mean(cv_ap[c]))
    se = float(np.std(cv_ap[top_c], ddof=1) / np.sqrt(FOLDS))
    best_c = min(c for c in C_GRID if np.mean(cv_ap[c]) >= np.mean(cv_ap[top_c]) - se)
    oof = oof_by_c[best_c]

    order = fp.rank(oof, appl)
    hits = np.cumsum(nitrd[order])
    k95 = int(np.searchsorted(hits, np.ceil(TARGET_RECALL * n_nitrd)) + 1)
    k_primary = fp.shortlist_size(PRIMARY_FRACTION, n)
    final = fit(np.flatnonzero(categorized), best_c)

    rng = np.random.default_rng(EXEMPLAR_SEED)
    pos = np.flatnonzero(nitrd)
    neg_pool = np.flatnonzero(categorized & ~nitrd)
    neg = np.sort(rng.choice(neg_pool, size=min(NEG_EXEMPLARS, len(neg_pool)), replace=False))
    exemplars = {
        "nitrd": {"appl_id": appl[pos], "core": [str(c) for c in cores[pos]], "emb": x[pos],
                  "selection": "all FY2021 universe NITRD (category 329) awards"},
        "not_nitrd": {"appl_id": appl[neg], "core": [str(c) for c in cores[neg]], "emb": x[neg],
                      "selection": f"{len(neg)} FY2021 categorized non-NITRD universe awards, "
                                   f"numpy default_rng({EXEMPLAR_SEED}) sample without replacement"},
    }
    meta = {"fingerprint_id": FINGERPRINT_ID, "arm": "B", "C": best_c, "label_fy": LABEL_FY,
            "train_records": int(categorized.sum()), "train_nitrd": n_nitrd,
            "universe_rule": qu.UNIVERSE_RULE_ID, "interpretability_note": INTERPRETABILITY_NOTE,
            "explanations": "nearest exemplars (Model.explain), not term weights",
            "embedding_cache": {"embed_id": esum["embed_id"], "files_sha256": {
                k: v["sha256"] for k, v in esum["files"].items()},
                "endpoint_calls": esum["endpoint_calls"],
                "served_versions_seen": esum["served_versions_seen"]},
            "smoke": SMOKE or None}
    model = em.Model(final.coef_.ravel(), float(final.intercept_[0]), exemplars, meta)
    blob = model.to_bytes()
    reloaded = em.Model.from_bytes(blob)
    drift = float(np.max(np.abs(reloaded.decision(x) - final.decision_function(x))))
    if drift > 1e-4:
        raise RuntimeError(f"stored model reproduces scores only to {drift}")

    shown = [int(i) for i in order[:3]]  # top-3 out-of-fold awards, as an illustration
    examples = [{"appl_id": int(appl[i]), "core_project_num": str(cores[i]), "nitrd": bool(nitrd[i]),
                 "explanation": reloaded.explain(x[i], core=str(cores[i]), top=3)} for i in shown]
    calib = {
        "fingerprint_id": FINGERPRINT_ID, "arm": "B (comparison; pre-registration section 6a)",
        "label_fy": LABEL_FY, "universe_rule": qu.UNIVERSE_RULE_ID, "universe_drops": drops,
        "fy2021": {"universe": n, "nitrd": n_nitrd, "uncategorized": int((~categorized).sum()),
                   "prevalence": n_nitrd / n, "uncategorized_share": float((~categorized).mean())},
        "embedding_pin": em.PIN, "encoding": em.ENCODING, "embeddings_sha256": x_sha,
        "runtime": {"sklearn": sklearn.__version__, "numpy": np.__version__},
        "cv": {"folds": FOLDS, "grouping": "core_project_num", "metric": "average_precision",
               "fold_assignment": {"source": "arm A (build/task1_oof_scores_v1/arm_a/fold_assignment.i8)",
                                   "sha256": FOLD_PIN},
               "ap_by_C": {str(c): v for c, v in cv_ap.items()}, "chosen_C": best_c,
               "selection": "one-standard-error rule", "best_mean_C": top_c, "best_mean_se": se,
               "chosen_C_at_grid_edge": best_c in (C_GRID[0], C_GRID[-1])},
        "oof_ap_categorized": float(average_precision_score(nitrd[categorized], oof[categorized])),
        "own_calibration": {"target_recall": TARGET_RECALL, "k": k95, "fraction": k95 / n,
                            "point": curve_point(order, nitrd, categorized, k95)},
        "at_primary_fraction": {"primary": PRIMARY_FINGERPRINT, "fraction": PRIMARY_FRACTION,
                                "point": curve_point(order, nitrd, categorized, k_primary)},
        "curve": [{"fraction": f, **curve_point(order, nitrd, categorized, fp.shortlist_size(f, n))}
                  for f in CURVE],
        "shortlist_rule": {"own_fraction": k95 / n, "k_formula": "ceil(fraction x universe size)",
                           "order": "model score descending, ties by appl_id ascending",
                           "comparison_fraction": PRIMARY_FRACTION},
        "interpretability_note": INTERPRETABILITY_NOTE,
        "example_explanations": examples,
        "stored_model_max_score_drift": drift,
        "model_sha256": hashlib.sha256(blob).hexdigest(),
    }
    log(f"chosen C={best_c}; own fraction {k95 / n:.4%}; recall at primary 11.55% "
        f"{calib['at_primary_fraction']['point']['recall']:.4f}")

    OUT.mkdir(parents=True)
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "model.json.gz").write_bytes(blob)  # SHA-256 re-checked after the build, outside the guard
    (OUT / "MODEL_POINTER.json").write_text(json.dumps(
        {"fingerprint_id": FINGERPRINT_ID, "path": str(model_dir / "model.json.gz"),
         "sha256": calib["model_sha256"], "bytes": len(blob),
         "why_not_in_git": "9.6 MB exemplar bank; owner decision 2026-11-04: volume + SHA-pin"},
        indent=1, sort_keys=True) + "\n")
    (OUT / "calibration.json").write_text(json.dumps(calib, indent=1, sort_keys=True) + "\n")
    sha = guard.write_manifest(OUT / "READ_MANIFEST.json")
    log(f"done in {time.time() - t0:.0f}s; READ_MANIFEST sha256 {sha}")
    print(json.dumps({k: calib[k] for k in ("cv", "oof_ap_categorized", "own_calibration",
                                            "at_primary_fraction", "model_sha256")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
