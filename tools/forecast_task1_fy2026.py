"""Task 1 FY2026 prospective forecast from fingerprint v1 (FORECAST_ID = task1-forecast-fy2026-v1).

Runs under the read guard in "forecast" mode. Reads only: the FY2026 identity + text fetch
($SEED_ROOT/fy2026, no label field was requested) and build/task1_fingerprint_v1/. Writes, once,
build/task1_forecast_fy2026/:

* forecast.csv.gz: every FY2026 universe award (reconstructed QVR filter) with score, rank and
  on_shortlist at the calibrated fraction; this is the award-level forecast (blind headline);
* forecast_summary.json: universe size, K, drops, the count forecast and its formula;
* READ_MANIFEST.json.

Count forecast (filtered count under the reconstructed universe, frozen snapshot):
  (1 - u2021) x r2021 x sum of scores over the FY2026 universe,
where u2021 = FY2021 uncategorized share and r2021 = FY2021 NITRD count / sum of out-of-fold scores over
FY2021 categorized awards (both fixed by the build).
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow import build_guard as bg  # noqa: E402

FORECAST_ID = "task1-forecast-fy2026-v1"
FY = 2026
FP_DIR = ROOT / "build" / "task1_fingerprint_v1"
OUT = ROOT / "build" / "task1_forecast_fy2026"


def main() -> int:
    if OUT.exists():
        raise SystemExit(f"{OUT} exists; the forecast is written once")
    seed = bg.SEED_ROOT / f"fy{FY}"
    guard = bg.Guard("forecast", roots=(seed, FP_DIR)).install()
    import numpy as np

    from workflow import fingerprint as fp
    from workflow import qvr_universe as qu

    rule = json.loads(guard.read_bytes(FP_DIR / "shortlist_rule.json"))
    calib = json.loads(guard.read_bytes(FP_DIR / "calibration.json"))
    blob = guard.read_bytes(FP_DIR / "model.json.gz")
    if hashlib.sha256(blob).hexdigest() != rule["model_sha256"]:
        raise RuntimeError("model.json.gz does not match shortlist_rule.json")
    model = fp.Model.from_bytes(blob)

    summary = json.loads(guard.read_bytes(seed / "FETCH_SUMMARY.json"))
    if summary["labels_requested"] or summary["guard_mode"] != "forecast":
        raise RuntimeError("FY2026 fetch was not a forecast-mode, label-free fetch")
    raw = guard.read_bytes(seed / summary["file"])
    if hashlib.sha256(raw).hexdigest() != summary["sha256_gz"]:
        raise RuntimeError("FY2026 seed file sha256 differs from its FETCH_SUMMARY")
    rows = [json.loads(line) for line in gzip.decompress(raw).decode("utf-8").split("\n") if line]
    if any(k in r for r in rows for k in ("cat329", "has_any_category")):
        raise RuntimeError("label field present in the FY2026 fetch")
    drops: dict[str, int] = {}
    for r in rows:
        k = qu.exclusion(r) or "in_universe"
        drops[k] = drops.get(k, 0) + 1
    u = [r for r in rows if qu.in_universe(r)]
    n = len(u)

    scores = model.score(model.transform([fp.text_of(r) for r in u]))
    appl = np.array([r["appl_id"] for r in u], dtype=np.int64)
    order = fp.rank(scores, appl)
    k = fp.shortlist_size(rule["shortlist_fraction"], n)
    rank_of = np.empty(n, dtype=np.int64)
    rank_of[order] = np.arange(1, n + 1)

    u21 = calib["fy2021"]["uncategorized_share"]
    r21 = calib["count_check"]["nitrd"] / calib["count_check"]["sum_oof_p_categorized"]
    count_forecast = (1.0 - u21) * r21 * float(scores.sum())

    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["appl_id", "core_project_num", "admin_ic", "rank", "score", "on_shortlist"])
    for i in order:
        w.writerow([int(appl[i]), u[i]["core_project_num"], u[i]["admin_ic"], int(rank_of[i]),
                    f"{scores[i]:.6f}", int(rank_of[i] <= k)])
    data = gzip.compress(buf.getvalue().encode("utf-8"), mtime=0)

    out = {
        "forecast_id": FORECAST_ID, "fy": FY, "written_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fingerprint_id": rule["fingerprint_id"], "model_sha256": rule["model_sha256"],
        "seed": {"sha256_gz": summary["sha256_gz"], "records": summary["records"],
                 "pull_utc": summary["pull_utc"]},
        "universe_rule": qu.UNIVERSE_RULE_ID, "universe_drops": drops, "universe": n,
        "shortlist_fraction": rule["shortlist_fraction"], "k": k,
        "secondary_k": {name: fp.shortlist_size(f, n) for name, f in rule["secondary_fractions"].items()},
        "count_forecast": {"value": round(count_forecast, 1), "sum_scores": float(scores.sum()),
                           "u2021": u21, "r2021": r21,
                           "formula": "(1 - u2021) x r2021 x sum(score) over the FY2026 universe snapshot"},
        "forecast_csv_sha256": hashlib.sha256(data).hexdigest(),
    }
    OUT.mkdir(parents=True)
    (OUT / "forecast.csv.gz").write_bytes(data)
    (OUT / "forecast_summary.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    out["read_manifest_sha256"] = guard.write_manifest(OUT / "READ_MANIFEST.json")
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
