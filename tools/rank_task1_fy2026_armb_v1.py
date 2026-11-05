"""Arm B FY2026 ranking (RANKING_ID = task1-fy2026-armb-ranking-v1), written while FY2026 NITRD is not public.

Pre-registration task1-prereg-v1-2026-11-04T18:00:50Z, section 6a, arm B row: FY2026 is "embedded once at
scoring time by the same endpoint and version" and the matrix is pinned. Owner decision 2026-11-05: embed it
now, before any FY2026 category-329 record is public, so arm B's Tier 1 ranking is prospective like arm A's.

Runs under the read guard in mode "forecast" (workflow/build_guard.py): it reads only the label-free FY2026
seed (task1-text-fetch-v1, labels_requested false), arm A's committed forecast (to check both arms rank the
same universe), arm A's shortlist rule (for K), the arm B model via MODEL_POINTER.json, and its own embedding
chunks. No label is read; the endpoint receives title + abstract + PHR only.

The universe (task1-universe-qvr-recon-v1, seed order, as tools/forecast_task1_fy2026.py) is embedded in
fixed 16-row batches, in CHUNK-row chunks checkpointed to the volume; rerun until DONE.

Outputs (write-once):
  $EMBED_ROOT/fy2026/{fy2026.appl_id.i64le, fy2026.emb.f32le, EMBED_SUMMARY.json}   pinned matrices
  build/task1_fy2026_armb_ranking_v1/{ranking.csv.gz, ranking_summary.json, READ_MANIFEST.json}
ranking.csv.gz has the forecast's columns; on_shortlist uses arm A's K (equal burden, binding rule 3).
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow import build_guard as bg  # noqa: E402

RANKING_ID = "task1-fy2026-armb-ranking-v1"
EMBED_ID = "task1-embed-cache-v1"
FY, CHUNK = 2026, 1024
POINTER_DIR = ROOT / "build" / "task1_fingerprint_embed_v1"
A_FP = ROOT / "build" / "task1_fingerprint_v1"
A_FORECAST = ROOT / "build" / "task1_forecast_fy2026"
OUT = ROOT / "build" / "task1_fy2026_armb_ranking_v1"
EMBED_ROOT = Path(os.environ.get("UAC_NITRD_TASK1_EMBED_ROOT", "/Volumes/users/conroyri/nitrd_hackathon_v1_raw/task1_embed_v1"))
EDIR = EMBED_ROOT / f"fy{FY}"
CHUNKS = EDIR / "_chunks"
HEADER = ["appl_id", "core_project_num", "admin_ic", "rank", "score", "on_shortlist"]


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def log(m: str) -> None:
    print(f"{datetime.now(UTC).strftime('%H:%M:%S')} {m}", flush=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget-min", type=float, default=50.0)
    a = ap.parse_args(argv)
    t_start = time.time()
    if OUT.exists():
        raise SystemExit(f"{OUT} exists; the arm B FY2026 ranking is written once")
    ptr = json.loads((POINTER_DIR / "MODEL_POINTER.json").read_text())
    seed = bg.SEED_ROOT / f"fy{FY}"
    CHUNKS.mkdir(parents=True, exist_ok=True)
    guard = bg.Guard("forecast", roots=(seed, POINTER_DIR, A_FP, A_FORECAST, Path(ptr["path"]).parent, EDIR)).install()
    import numpy as np

    from workflow import embedding as em
    from workflow import fingerprint as fp
    from workflow import qvr_universe as qu

    summary = json.loads(guard.read_bytes(seed / "FETCH_SUMMARY.json"))
    if summary["labels_requested"] or summary["guard_mode"] != "forecast":
        raise RuntimeError("FY2026 fetch was not a forecast-mode, label-free fetch")
    raw = guard.read_bytes(seed / summary["file"])
    if _sha(raw) != summary["sha256_gz"]:
        raise RuntimeError("FY2026 seed differs from its FETCH_SUMMARY")
    rows = [json.loads(x) for x in gzip.decompress(raw).decode("utf-8").split("\n") if x]
    if any(k in r for r in rows for k in ("cat329", "has_any_category")):
        raise RuntimeError("label field present in the FY2026 fetch")
    u = [r for r in rows if qu.in_universe(r)]
    del rows
    n = len(u)
    appl = np.array([r["appl_id"] for r in u], dtype="<i8")
    fa = guard.read_bytes(A_FORECAST / "forecast.csv.gz")
    a_ids = {int(r["appl_id"]) for r in csv.DictReader(io.StringIO(gzip.decompress(fa).decode()))}
    if set(appl.tolist()) != a_ids or len(a_ids) != n:
        raise RuntimeError("arm B universe differs from arm A's FY2026 forecast universe")
    texts = [fp.text_of(r) for r in u]
    order_file = CHUNKS / "appl_order.i64le"
    if not order_file.exists():
        order_file.write_bytes(appl.tobytes())
    if guard.read_bytes(order_file) != appl.tobytes():
        raise RuntimeError("checkpointed row order differs from this run's universe order")

    enc = em.HostedEncoder()
    starts = list(range(0, n, CHUNK))
    for s in starts:
        f, fm = CHUNKS / f"chunk_{s:06d}.f32le", CHUNKS / f"chunk_{s:06d}.json"
        if f.exists() and fm.exists():
            continue
        if f.exists():
            f.unlink()
        if (time.time() - t_start) / 60 > a.budget_min:
            done = sum((CHUNKS / f"chunk_{x:06d}.json").exists() for x in starts)
            log(f"PAUSED at budget: {done}/{len(starts)} chunks; rerun to continue")
            return 3
        x = enc.embed(texts[s:s + CHUNK])
        f.write_bytes(np.ascontiguousarray(x, dtype="<f4").tobytes())
        fm.write_text(json.dumps({"chunk": s, "rows": len(x), "sha256": _sha(f.read_bytes()),
                                  "session_calls": enc.calls, "versions": sorted(enc.versions_seen)}) + "\n")
        if s // CHUNK % 8 == 0:
            log(f"chunk {s // CHUNK + 1}/{len(starts)}")

    x = np.concatenate([np.frombuffer(guard.read_bytes(CHUNKS / f"chunk_{s:06d}.f32le"), dtype="<f4")
                        .reshape(-1, em.PIN["dimensions"]) for s in starts])
    if x.shape != (n, em.PIN["dimensions"]) or not np.isfinite(x).all():
        raise RuntimeError(f"assembled matrix shape {x.shape} or non-finite values")
    cmeta = [json.loads(guard.read_bytes(CHUNKS / f"chunk_{s:06d}.json")) for s in starts]
    for s, m in zip(starts, cmeta):
        if m["sha256"] != _sha(guard.read_bytes(CHUNKS / f"chunk_{s:06d}.f32le")):
            raise RuntimeError(f"chunk {s} does not match its record")
    versions = sorted({v for m in cmeta for v in m["versions"]})
    if versions != [em.PIN["served_model_version"]]:
        raise RuntimeError(f"served versions {versions}")
    emb_bytes, appl_bytes = x.tobytes(), appl.tobytes()
    efile, afile = EDIR / f"fy{FY}.emb.f32le", EDIR / f"fy{FY}.appl_id.i64le"
    if not (EDIR / "EMBED_SUMMARY.json").exists():
        afile.write_bytes(appl_bytes)
        efile.write_bytes(emb_bytes)
        esum = {"embed_id": EMBED_ID, "fy": FY, "records": n, "dims": int(x.shape[1]),
                "row_order": "FY2026 seed order, universe rows only (task1-universe-qvr-recon-v1)",
                "files": {afile.name: {"sha256": _sha(appl_bytes), "bytes": len(appl_bytes), "dtype": "<i8"},
                          efile.name: {"sha256": _sha(emb_bytes), "bytes": len(emb_bytes), "dtype": "<f4",
                                       "shape": [int(v) for v in x.shape]}},
                "seed_files_sha256": {summary["file"]: summary["sha256_gz"]},
                "embedding_pin": em.PIN, "encoding": em.ENCODING, "chunk_rows": CHUNK,
                "endpoint_batches": -(-n // em.BATCH), "served_versions_seen": versions,
                "label_fields_used": False, "written_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
        (EDIR / "EMBED_SUMMARY.json").write_text(json.dumps(esum, indent=1, sort_keys=True) + "\n")
    esum = json.loads(guard.read_bytes(EDIR / "EMBED_SUMMARY.json"))
    if esum["files"][efile.name]["sha256"] != _sha(guard.read_bytes(efile)) or _sha(emb_bytes) != esum["files"][efile.name]["sha256"]:
        raise RuntimeError("pinned FY2026 matrix differs from the chunks")

    guard.read_bytes(POINTER_DIR / "MODEL_POINTER.json")
    blob = guard.read_bytes(Path(ptr["path"]))
    if _sha(blob) != ptr["sha256"]:
        raise RuntimeError("arm B model does not match MODEL_POINTER.json")
    rule = json.loads(guard.read_bytes(A_FP / "shortlist_rule.json"))
    model = em.Model.from_bytes(blob)
    scores = model.score(x)
    order = fp.rank(scores, appl)
    k = fp.shortlist_size(rule["shortlist_fraction"], n)
    rank_of = np.empty(n, dtype=np.int64)
    rank_of[order] = np.arange(1, n + 1)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(HEADER)
    for i in order:
        w.writerow([int(appl[i]), u[i]["core_project_num"], u[i]["admin_ic"], int(rank_of[i]),
                    f"{scores[i]:.6f}", int(rank_of[i] <= k)])
    data = gzip.compress(buf.getvalue().encode("utf-8"), mtime=0)
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    summ = {"ranking_id": RANKING_ID, "fy": FY, "arm": "B", "fingerprint_id": ptr["fingerprint_id"],
            "model_sha256": ptr["sha256"], "universe": n, "k": k, "k_rule": "arm A's calibrated fraction (equal burden)",
            "shortlist_fraction": rule["shortlist_fraction"], "embedding_sha256": esum["files"][efile.name]["sha256"],
            "repo_head": head, "labels_read": 0, "ranking_csv_sha256": _sha(data), "guard_mode": "forecast",
            "written_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
    OUT.mkdir(parents=True)
    (OUT / "ranking.csv.gz").write_bytes(data)
    (OUT / "ranking_summary.json").write_text(json.dumps(summ, indent=1, sort_keys=True) + "\n")
    summ["read_manifest_sha256"] = guard.write_manifest(OUT / "READ_MANIFEST.json")
    log("DONE " + json.dumps(summ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
