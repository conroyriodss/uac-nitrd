"""FY2021 Task 3 under-capture candidates (EXPORT_ID = task1-fy2021-under-capture-v1), a static snapshot.

Pre-registration section 5, item 10: uncategorized awards on the shortlist, listed with scores, not counted as
errors. This is the FY2021 (build year, exposed) version, for the reviewer portal's Task 3 panel. The FY2024 list
(build/task1_fy2024_score_v1/under_capture_tier2.csv) derives from the sealed key and is NOT exported.

Shortlist = the top K = 7,284 FY2021 universe awards by arm A's OUT-OF-FOLD score (build/task1_oof_scores_v1/arm_a,
log-odds, each award scored by a fold model that did not see it), in fp.rank order. That is the 11.55%
calibration point. "Uncategorized" = no RCDC spending category at all in the FY2021 seed (has_any_category false).
Writes build/task1_fy2021_under_capture_v1/{under_capture_fy2021.csv, SUMMARY.json} once.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

EXPORT_ID = "task1-fy2021-under-capture-v1"
OOF = ROOT / "build/task1_oof_scores_v1/arm_a"
OUT = ROOT / "build/task1_fy2021_under_capture_v1"
COLS = ["appl_id", "core_project_num", "admin_ic", "activity_code", "title", "armA_oof_logodds", "armA_oof_rank"]


def main() -> int:
    import numpy as np

    from tools.tier3_task1_v1 import SEED_ROOT
    from workflow import fingerprint as fp
    from workflow import qvr_universe as qu
    if OUT.exists():
        raise SystemExit(f"{OUT} exists (write-once)")
    summ = json.loads((OOF / "SUMMARY.json").read_text())
    raw = (OOF / summ["file"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != summ["sha256"]:
        raise RuntimeError("OOF scores do not match SUMMARY.json")
    oof = {int(r["appl_id"]): float(r["oof_score"]) for r in csv.DictReader(io.StringIO(gzip.decompress(raw).decode()))}
    fs = json.loads((SEED_ROOT / "fy2021" / "FETCH_SUMMARY.json").read_text())
    sraw = (SEED_ROOT / "fy2021" / fs["file"]).read_bytes()
    if hashlib.sha256(sraw).hexdigest() != fs["sha256_gz"]:
        raise RuntimeError("FY2021 seed does not match its FETCH_SUMMARY")
    u = {r["appl_id"]: r for r in (json.loads(x) for x in gzip.decompress(sraw).decode().split("\n") if x) if qu.in_universe(r)}
    if set(u) != set(oof) or len(oof) != summ["universe"]:
        raise RuntimeError("OOF universe differs from the FY2021 seed universe")
    appl = np.array(sorted(oof), dtype=np.int64)
    scores = np.array([oof[int(a)] for a in appl])
    order = fp.rank(scores, appl)
    k = summ["k95"]
    rows = []
    for pos, i in enumerate(order[:k], start=1):
        r = u[int(appl[i])]
        if not r["has_any_category"] and not r["cat329"]:
            rows.append([r["appl_id"], r["core_project_num"], r["admin_ic"], r["activity_code"], r["title"],
                         f"{scores[i]:.4f}", pos])
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(COLS)
    w.writerows(rows)
    data = buf.getvalue().encode("utf-8")
    OUT.mkdir(parents=True)
    (OUT / "under_capture_fy2021.csv").write_bytes(data)
    s = {"export_id": EXPORT_ID, "fy": 2021, "blind": False, "universe": len(u), "k": k,
         "shortlist_fraction": k / len(u), "candidates": len(rows),
         "score": "arm A (task1-fingerprint-v1) out-of-fold log-odds, FY2021 GroupKFold by core; NOT a probability "
                  "and NOT the deployed nitrd-classifier",
         "uncategorized": "no RCDC spending category in the FY2021 RePORTER record (has_any_category false)",
         "inputs": {"oof_scores_sha256": summ["sha256"], "fy2021_seed_sha256": fs["sha256_gz"]},
         "csv_sha256": hashlib.sha256(data).hexdigest(), "columns": COLS}
    (OUT / "SUMMARY.json").write_text(json.dumps(s, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k2: s[k2] for k2 in ("universe", "k", "candidates", "csv_sha256")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
