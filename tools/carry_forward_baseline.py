"""Run the carry-forward baseline on the committed Task 1 build universe. DEV / not scored.

Outputs (deterministic; --check verifies the committed files rebuild byte-identical):
* dev/baseline/carry_forward_backtest.json : backtests INSIDE the build window
    FY2023 <- FY2021-2022  and  FY2022 <- FY2021, recall/precision by new vs continuing, core and appl level.
* build/baseline/carry_forward_fy2024.predictions.csv (+ .meta.json): frozen FY2024 baseline predictions from
    FY2024 IDENTITY + FY2021-2023 labels. No FY2024 label is read; nothing is scored against FY2024 here.

Usage: python tools/carry_forward_baseline.py [--write | --check]
"""
from __future__ import annotations

import argparse
import collections
import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow.baseline import BASELINE_ID, core_labels, evaluate, load_universe, predict  # noqa: E402
from workflow.common import sha256  # noqa: E402

UNIVERSE = ROOT / "build" / "universe"
BACKTEST = ROOT / "dev" / "baseline" / "carry_forward_backtest.json"
PRED = ROOT / "build" / "baseline" / "carry_forward_fy2024.predictions.csv"
PRED_META = PRED.with_suffix(".meta.json")
DEV_NOTE = ("DEV / not scored. Carry-forward baseline backtested inside the FY2021-2023 build window only; "
            "no FY2024 label was read.")
PRED_NOTE = ("Frozen FY2024 carry-forward baseline predictions (FY2024 identity + FY2021-2023 labels). "
             "NOT scored: to be compared to the sealed FY2024 listing only when the seal is opened.")
BACKTESTS = ((2023, (2021, 2022)), (2022, (2021,)))


def _dump(obj) -> str:
    return json.dumps(obj, indent=1, sort_keys=True) + "\n"


def _inputs() -> dict:
    man = json.loads((UNIVERSE / "MANIFEST.json").read_text(encoding="utf-8"))
    for name, meta in man["files"].items():
        got = sha256(UNIVERSE / name)
        if got != meta["sha256"]:
            raise SystemExit(f"{name}: sha256 {got} != manifest {meta['sha256']}")
    return {"universe_id": man["universe_id"], "manifest_sha256": sha256(UNIVERSE / "MANIFEST.json"),
            "files": {n: m["sha256"] for n, m in sorted(man["files"].items())}}


def build() -> dict[Path, str]:
    inputs = _inputs()
    U = {fy: load_universe(UNIVERSE / f"fy{fy}.csv") for fy in (2021, 2022, 2023)}
    L = {fy: core_labels(rows) for fy, rows in U.items()}
    back = {"label": DEV_NOTE, "baseline_id": BASELINE_ID, "inputs": inputs, "backtests": {}}
    for tfy, pfys in BACKTESTS:
        p = predict([{k: r[k] for k in ("appl_id", "fy", "core_project_num")} for r in U[tfy]],
                    {fy: L[fy] for fy in pfys})
        back["backtests"][f"FY{tfy}<-FY{'-'.join(map(str, pfys))}"] = evaluate(p, U[tfy])

    T = load_universe(UNIVERSE / "fy2024_identity.csv")
    if any("cat329" in r for r in T):
        raise SystemExit("FY2024 identity file carries a label column; refused")
    p24 = predict(T, L)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["appl_id", "core_project_num", "prediction", "stratum", "source_fy"])
    for a in sorted(p24["appls"]):
        x = p24["appls"][a]
        w.writerow([a, x["core_project_num"], x["prediction"], x["stratum"], x["source_fy"] or ""])
    csv_text = buf.getvalue()
    cores = p24["cores"].values()
    meta = {"label": PRED_NOTE, "baseline_id": BASELINE_ID, "inputs": inputs, "target_fy": 2024,
            "prior_fys": p24["prior_fys"], "labels_read": ["FY2021", "FY2022", "FY2023"],
            "fy2024_labels_read": False,
            "predictions_sha256": __import__("hashlib").sha256(csv_text.encode()).hexdigest(),
            "counts": {"appl_ids": len(p24["appls"]), "cores": len(p24["cores"]),
                       "cores_by_stratum": dict(collections.Counter(c["stratum"] for c in cores)),
                       "cores_predicted_329": sum(c["prediction"] for c in cores),
                       "appls_predicted_329": sum(x["prediction"] for x in p24["appls"].values()),
                       "continuing_cores_by_source_fy": {str(fy): sum(1 for c in cores if c["source_fy"] == fy)
                                                         for fy in p24["prior_fys"]}}}
    return {BACKTEST: _dump(back), PRED: csv_text, PRED_META: _dump(meta)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    out = build()
    if a.check:
        bad = [str(p.relative_to(ROOT)) for p, t in out.items() if not p.exists() or p.read_text(encoding="utf-8") != t]
        print("carry-forward baseline: " + ("MISMATCH " + ", ".join(bad) if bad else "committed outputs rebuild byte-identical"))
        return 1 if bad else 0
    for p, t in out.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(t, encoding="utf-8")
    print("wrote", ", ".join(str(p.relative_to(ROOT)) for p in out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
