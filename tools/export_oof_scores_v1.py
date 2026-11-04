"""Export the FY2021 out-of-fold scores of arms A and B for the comparison harness (under the read guard).

The arm builders kept only aggregates (calibration.json), but the harness needs per-award scores. A
final-model (in-sample) score would flatter both arms, so this re-derives the out-of-fold decision
scores at each arm's chosen C with the builders' exact protocol, and refuses to write unless they
reproduce the committed calibration exactly: per-fold AP at the chosen C, OOF AP and the 0.95-recall k.

Arm A: tools/build_fingerprint_v1.py steps 1-4 (FY2019-2021 text for the vocabulary and IDF, FY2021
labels). Arm B: tools/build_fingerprint_embed_v1.py (pinned FY2021 embedding cache, FY2021 labels).
Uncategorized awards never enter a fit; they are scored out of fold like every other award.

One arm per process (UAC_NITRD_TASK1_OOF_ARM=A or B). GroupKFold's fold assignment differs between
scikit-learn 1.7.2 and 1.9.1 (23% of awards share a fold), so: arm A uses GroupKFold as its builder did
(1.7.2) and writes the assignment; arm B (rebuilt 2026-11-04 on arm A's folds) reads that assignment,
checked against its SHA-256 in arm B's calibration. Version and fold hash are recorded per arm.

Outputs (write-once) in build/task1_oof_scores_v1/arm_<a|b>/: scores.csv.gz (appl_id, oof_score;
score = LR decision value, rank order = score descending, ties by appl_id), SUMMARY.json (checks,
sklearn version, fold sha256), READ_MANIFEST.json.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow import build_guard as bg  # noqa: E402

EXPORT_ID = "task1-oof-scores-v1"
ARM = os.environ.get("UAC_NITRD_TASK1_OOF_ARM", "")
OUT = Path(os.environ.get("UAC_NITRD_TASK1_OOF_OUT", ROOT / "build" / "task1_oof_scores_v1" / f"arm_{ARM.lower()}"))
ARM_A = ROOT / "build" / "task1_fingerprint_v1"
ARM_B = ROOT / "build" / "task1_fingerprint_embed_v1"
EMBED_ROOT = Path(os.environ.get("UAC_NITRD_TASK1_EMBED_ROOT",
                                 "/Volumes/users/conroyri/nitrd_hackathon_v1_raw/task1_embed_v1"))
YEARS, LABEL_FY, FOLDS, TARGET_RECALL = (2019, 2020, 2021), 2021, 5, 0.95
MIN_DF_PER_YEAR, MAX_DF = 5, 0.5  # arm A's vocabulary rule


def load_year(guard, fy):
    d = bg.SEED_ROOT / f"fy{fy}"
    summary = json.loads(guard.read_bytes(d / "FETCH_SUMMARY.json"))
    raw = guard.read_bytes(d / summary["file"])
    if hashlib.sha256(raw).hexdigest() != summary["sha256_gz"]:
        raise RuntimeError(f"FY{fy}: seed sha256 mismatch")
    return [json.loads(x) for x in gzip.decompress(raw).decode("utf-8").split("\n") if x]


def main() -> int:
    if ARM not in ("A", "B"):
        raise SystemExit("set UAC_NITRD_TASK1_OOF_ARM=A or B")
    if OUT.exists():
        raise SystemExit(f"{OUT} exists; written once")
    guard = bg.Guard("build", roots=(bg.SEED_ROOT, EMBED_ROOT, ARM_A, ARM_B,
                                     ROOT / "build" / "task1_oof_scores_v1" / "arm_a")).install()
    import numpy as np
    import sklearn
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score
    from sklearn.model_selection import GroupKFold

    from workflow import fingerprint as fp
    from workflow import qvr_universe as qu

    cal = {ARM: json.loads(guard.read_bytes((ARM_A if ARM == "A" else ARM_B) / "calibration.json"))}
    # arm A's vocabulary and IDF use FY2019-2021 text; arm B reads only FY2021 (as its builder did)
    years = {fy: [r for r in load_year(guard, fy) if qu.in_universe(r)]
             for fy in (YEARS if ARM == "A" else (LABEL_FY,))}
    u = years[LABEL_FY]
    appl = np.array([r["appl_id"] for r in u], dtype=np.int64)
    cores = np.array([r["core_project_num"] or f"appl{r['appl_id']}" for r in u])
    categorized = np.array([bool(r["has_any_category"]) for r in u])
    nitrd = np.array([bool(r["cat329"]) for r in u])
    n = len(u)
    if ARM == "A":
        folds = list(GroupKFold(n_splits=FOLDS).split(np.zeros(n), groups=cores))
        fold_of = np.zeros(n, dtype="<i1")
        for i, (_, te) in enumerate(folds):
            fold_of[te] = i
    else:
        want_fold = cal[ARM]["cv"]["fold_assignment"]["sha256"]
        raw = guard.read_bytes(ROOT / "build" / "task1_oof_scores_v1" / "arm_a" / "fold_assignment.i8")
        if hashlib.sha256(raw).hexdigest() != want_fold:
            raise RuntimeError("arm A fold assignment differs from the one arm B was built on")
        fold_of = np.frombuffer(raw, dtype="<i1").copy()
        folds = [(np.flatnonzero(fold_of != k), np.flatnonzero(fold_of == k)) for k in range(FOLDS)]
    fold_sha = hashlib.sha256(fold_of.tobytes()).hexdigest()
    x = arm_a_features(years, np, fp) if ARM == "A" else arm_b_features(guard, cal, appl, n, np)
    del years

    summary = {"export_id": EXPORT_ID, "arm": ARM, "label_fy": LABEL_FY, "universe": n,
               "sklearn": sklearn.__version__, "numpy": np.__version__, "fold_assignment_sha256": fold_sha,
               "fold_assignment": "int8 fold index per FY2021 universe award in universe order"}
    c = cal[ARM]["cv"]["chosen_C"]
    oof, aps = np.zeros(n), []
    for tr, te in folds:
        m = LogisticRegression(C=c, solver="liblinear", max_iter=1000)
        idx = tr[categorized[tr]]
        m.fit(x[idx], nitrd[idx])
        oof[te] = m.decision_function(x[te])
        te_c = te[categorized[te]]
        aps.append(float(average_precision_score(nitrd[te_c], oof[te_c])))
    order = fp.rank(oof, appl)
    k95 = int(np.searchsorted(np.cumsum(nitrd[order]), np.ceil(TARGET_RECALL * nitrd.sum())) + 1)
    oof_ap = float(average_precision_score(nitrd[categorized], oof[categorized]))
    want = cal[ARM]
    want_k = want["calibration"]["k"] if ARM == "A" else want["own_calibration"]["k"]
    checks = {"fold_ap_equal": aps == want["cv"]["ap_by_C"][str(c)],
              "oof_ap_equal": oof_ap == want["oof_ap_categorized"], "k95_equal": k95 == want_k}
    if not all(checks.values()):
        raise RuntimeError(f"arm {ARM}: OOF scores do not reproduce its calibration: {checks}, "
                           f"folds {aps} vs {want['cv']['ap_by_C'][str(c)]}, k {k95} vs {want_k}")
    lines = "appl_id,oof_score\n" + "".join(f"{a},{s!r}\n" for a, s in zip(appl.tolist(), oof.tolist()))
    blob = gzip.compress(lines.encode(), mtime=0)
    summary.update(fingerprint_id=want["fingerprint_id"], C=c, file="scores.csv.gz",
                   sha256=hashlib.sha256(blob).hexdigest(), checks=checks, oof_ap_categorized=oof_ap, k95=k95)
    print(ARM, checks, k95, sklearn.__version__, fold_sha[:16], flush=True)
    OUT.mkdir(parents=True)  # only once the arm reproduces its calibration
    (OUT / "scores.csv.gz").write_bytes(blob)
    (OUT / "fold_assignment.i8").write_bytes(fold_of.tobytes())
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    guard.write_manifest(OUT / "READ_MANIFEST.json")
    return 0


def arm_a_features(years, np, fp):
    """build_fingerprint_v1 step 2: vocabulary in every year, IDF on the pooled FY2019-2021 text."""
    keep = None
    for fy in YEARS:
        cv = fp.count_vectorizer(min_df=MIN_DF_PER_YEAR)
        cv.fit(fp.text_of(r) for r in years[fy])
        keep = set(cv.vocabulary_) if keep is None else keep & set(cv.vocabulary_)
        del cv
    vocab = sorted(keep)
    cv = fp.count_vectorizer(vocabulary={t: i for i, t in enumerate(vocab)})
    counts = {fy: cv.transform([fp.text_of(r) for r in years[fy]]) for fy in YEARS}
    pooled_df = sum(np.asarray((c > 0).sum(axis=0)).ravel() for c in counts.values())
    n_pooled = sum(c.shape[0] for c in counts.values())
    ok = pooled_df <= MAX_DF * n_pooled
    idf = fp.smooth_idf(pooled_df[ok].astype(np.float64), n_pooled)
    return fp.tfidf(counts[LABEL_FY][:, np.flatnonzero(ok)], idf)


def arm_b_features(guard, cal, appl, n, np):
    """Pinned FY2021 embedding cache, checked against arm B's recorded hashes."""
    pins = cal["B"]["embeddings_sha256"]
    ed = EMBED_ROOT / f"fy{LABEL_FY}"
    eb = guard.read_bytes(ed / f"fy{LABEL_FY}.emb.f32le")
    ab = guard.read_bytes(ed / f"fy{LABEL_FY}.appl_id.i64le")
    if hashlib.sha256(eb).hexdigest() != pins:
        raise RuntimeError("embedding cache differs from arm B's embeddings_sha256")
    if not np.array_equal(np.frombuffer(ab, dtype="<i8"), appl):
        raise RuntimeError("embedding cache rows do not match the FY2021 universe")
    return np.frombuffer(eb, dtype="<f4").reshape(n, -1).copy()


if __name__ == "__main__":
    sys.exit(main())
