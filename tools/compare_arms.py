"""Run the Task 1 model-comparison harness (workflow/model_comparison.py) and write its report, once.

NOT under the build guard (evaluation code; carry-forward uses exposed prior-year labels by design).

FY2021 build report, now:
  python tools/compare_arms.py --preset fy2021-build
    universe + FY2021 labels from the seed; arm A and arm B out-of-fold scores (build/task1_oof_scores_v1);
    arm C run-1 scores + weights (build/task1_llm_v1, sampled arm) unless --without-arm-c REASON.
    Carry-forward is not computed for FY2021: the seed's FY2020 file is text-only (no labels), so CF is
    reported at reveal only (FY2023 -> FY2024, FY2025 -> FY2026). Output: build/task1_comparison_fy2021/.

Reveal (identical harness, generic inputs), for example FY2024 excluding File A:
  python tools/compare_arms.py --mode reveal --label FY2024-non-File-A --universe U.csv \
      --arm A=ranked:A.csv.gz:score --arm B=ranked:B.csv.gz:score --arm C=sampled:C.csv.gz:score_run1:weight \
      --cf-prior FY2023_nitrd_cores.csv --cf-years 2023:2024 --combined --out build/task1_comparison_fy2024
  U.csv columns: appl_id, core_project_num, admin_ic, and in build/reveal mode nitrd, categorized (0/1).
  Mode prereveal takes the same inputs without labels and reports sizes, kappa and patterns only.

Outputs (write-once, deterministic: no clocks, sorted keys, gzip mtime 0): report.json (every input's
sha256 included), disagreement.csv.gz (appl_id, pattern; plus nitrd in reveal mode).
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np  # noqa: E402

from workflow import model_comparison as mc  # noqa: E402

SEED_ROOT = Path("/Volumes/users/conroyri/nitrd_hackathon_v1_raw/task1_seed_v1")
OOF = ROOT / "build" / "task1_oof_scores_v1"
LLM = ROOT / "build" / "task1_llm_v1"
CF_FY2021_NOTE = ("not computed for FY2021: FY2020 labels are not available (the seed's FY2020 file is text-only), "
                  "so carry-forward is reported at reveal only, FY2023 -> FY2024 and FY2025 -> FY2026, "
                  "labelled as using exposed prior-year labels")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(path: Path) -> str:
    p = Path(path).resolve()
    return str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(path)


def read_csv(path: Path) -> list[dict]:
    raw = path.read_bytes()
    text = gzip.decompress(raw).decode() if path.suffix == ".gz" else raw.decode()
    return list(csv.DictReader(io.StringIO(text)))


def universe_fy2021() -> tuple[mc.Universe, dict]:
    from workflow import qvr_universe as qu

    d = SEED_ROOT / "fy2021"
    summary = json.loads((d / "FETCH_SUMMARY.json").read_text())
    raw = (d / summary["file"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != summary["sha256_gz"]:
        raise RuntimeError("FY2021 seed sha256 mismatch")
    rows = [json.loads(x) for x in gzip.decompress(raw).decode("utf-8").split("\n") if x]
    u = [r for r in rows if qu.in_universe(r)]
    uni = mc.Universe(appl=np.array([r["appl_id"] for r in u], dtype=np.int64),
                      core=[r["core_project_num"] or "" for r in u], ic=[r.get("admin_ic") or "" for r in u],
                      nitrd=np.array([bool(r["cat329"]) for r in u]),
                      categorized=np.array([bool(r["has_any_category"]) for r in u]))
    return uni, {"seed_fy2021": summary["sha256_gz"], "universe_rule": qu.UNIVERSE_RULE_ID}


def universe_csv(path: Path, labelled: bool) -> mc.Universe:
    rows = read_csv(path)
    return mc.Universe(appl=np.array([int(r["appl_id"]) for r in rows], dtype=np.int64),
                       core=[r["core_project_num"] for r in rows], ic=[r.get("admin_ic", "") for r in rows],
                       nitrd=np.array([r["nitrd"] == "1" for r in rows]) if labelled else None,
                       categorized=np.array([r["categorized"] == "1" for r in rows]) if labelled else None)


def arm_from_spec(name: str, spec: str, u: mc.Universe) -> mc.Arm:
    kind, path, *cols = spec.split(":")
    p = Path(path)
    rows = read_csv(p)
    col = cols[0] if cols else "score"
    ids = [int(r["appl_id"]) for r in rows]
    score = mc.align(u, ids, [float(r[col]) if r[col] != "" else np.nan for r in rows])
    arm = mc.Arm(name, kind, score=score, inputs={"file": rel(p), "sha256": sha256(p), "column": col})
    if kind == "sampled":
        arm.weight = np.nan_to_num(mc.align(u, ids, [float(r[cols[1]]) for r in rows]), nan=0.0)
        arm.inputs["weight_column"] = cols[1]
    elif kind == "ranked" and np.isnan(score).any():
        raise ValueError(f"ranked arm {name} lacks a score for {int(np.isnan(score).sum())} universe awards")
    return arm


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", choices=["fy2021-build"])
    ap.add_argument("--without-arm-c", metavar="REASON")
    ap.add_argument("--mode", choices=mc.MODES)
    ap.add_argument("--label")
    ap.add_argument("--universe", type=Path)
    ap.add_argument("--arm", action="append", default=[], metavar="NAME=KIND:PATH[:COL[:WEIGHTCOL]]")
    ap.add_argument("--cf-prior", type=Path, help="CSV of prior-year NITRD core_project_num")
    ap.add_argument("--cf-years", help="PRIOR:YEAR, e.g. 2023:2024")
    ap.add_argument("--combined", action="store_true", help="add the A+CF arm")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()

    meta: dict = {}
    if a.preset == "fy2021-build":
        mode, label = "build", "FY2021 (build year; out-of-fold scores; not blind)"
        out = a.out or ROOT / "build" / "task1_comparison_fy2021"
        u, meta = universe_fy2021()
        arms, fold_sha = [], {}
        for name in ("A", "B"):
            d = OOF / f"arm_{name.lower()}"
            info = json.loads((d / "SUMMARY.json").read_text())
            fold_sha[name] = info["fold_assignment_sha256"]
            p = d / info["file"]
            if sha256(p) != info["sha256"] or not all(info["checks"].values()):
                raise RuntimeError(f"{p}: sha256 or reproduction checks fail")
            arm = arm_from_spec(name, f"ranked:{p}:oof_score", u)
            arm.note = (f"{info['fingerprint_id']}, out-of-fold decision score at C={info['C']} "
                        f"(sklearn {info['sklearn']}, folds {info['fold_assignment_sha256'][:12]})")
            arms.append(arm)
        meta["folds"] = ({"same_fold_assignment": True, "sha256": fold_sha["A"],
                          "note": "arms A and B out-of-fold scores come from the same core-grouped 5-fold "
                                  "assignment (arm A's, recorded; arm B rebuilt on it 2026-11-04)"}
                         if fold_sha["A"] == fold_sha["B"] else
                         {"same_fold_assignment": False, "sha256": fold_sha,
                          "note": "arms A and B out-of-fold scores come from different fold assignments"})
        if (LLM / "summary.json").exists():
            s = json.loads((LLM / "summary.json").read_text())
            if sha256(LLM / "scores.csv.gz") != s["scores_csv_gz_sha256"]:
                raise RuntimeError("arm C scores differ from their summary sha256")
            arm = arm_from_spec("C", f"sampled:{LLM / 'scores.csv.gz'}:score_run1:weight", u)
            arm.note = f"{s['classifier_id']}, run 1 of 3, {s['pin']['served_model_version']}, stratified sample"
            arms.append(arm)
        elif a.without_arm_c:
            meta["arm_c"] = f"not included: {a.without_arm_c}"
        else:
            raise SystemExit("arm C output missing: wait for build/task1_llm_v1 or pass --without-arm-c REASON")
        meta["carry_forward"] = CF_FY2021_NOTE
    else:
        if not (a.mode and a.universe and a.arm and a.out and a.label):
            raise SystemExit("--mode, --label, --universe, --arm and --out are required without --preset")
        mode, label, out = a.mode, a.label, a.out
        u = universe_csv(a.universe, labelled=mode != "prereveal")
        meta["universe_file"] = {"file": rel(a.universe), "sha256": sha256(a.universe)}
        arms = [arm_from_spec(*s.split("=", 1), u) for s in a.arm]
        if a.cf_prior:
            prior, year = (int(x) for x in a.cf_years.split(":"))
            cores = {r["core_project_num"] for r in read_csv(a.cf_prior) if r["core_project_num"]}
            cf = mc.carry_forward(u, cores, prior, year)
            cf.inputs = {"file": rel(a.cf_prior), "sha256": sha256(a.cf_prior), "prior_nitrd_cores": len(cores)}
            arms.append(cf)
            if a.combined:
                arms.append(mc.combined(next(x for x in arms if x.name == "A"), cf, u))
    if out.exists():
        raise SystemExit(f"{out} exists; the comparison is written once")

    res = mc.compare(u, arms, mode)
    report = {"label": label, **res["report"], "meta": meta}
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    lab = {int(x): bool(y) for x, y in zip(u.appl, u.nitrd)} if mode == "reveal" else None
    w.writerow(["appl_id", "pattern"] + (["nitrd"] if lab else []))
    for appl, pattern in res["rows"]:
        w.writerow([appl, pattern] + ([int(lab[appl])] if lab else []))
    blob = gzip.compress(buf.getvalue().encode(), mtime=0)
    report["disagreement_csv_gz_sha256"] = hashlib.sha256(blob).hexdigest()
    out.mkdir(parents=True)
    (out / "disagreement.csv.gz").write_bytes(blob)
    (out / "report.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: report[k] for k in ("label", "k_at_equal_burden", "kappa_matrix")}, indent=1))
    print(json.dumps({n: e.get("at_equal_burden") or e.get("set") for n, e in report["arms"].items()}, indent=1))
    print(json.dumps(report["disagreement"], indent=1)[:1500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
