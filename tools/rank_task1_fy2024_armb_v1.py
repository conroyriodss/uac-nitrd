"""Arm B FY2024 ranking (RANKING_ID = task1-fy2024-armb-ranking-v1), computed before the FY2024 key is opened.

Pre-registration task1-prereg-v1-2026-11-04T18:00:50Z, section 6a, arm B row: "FY2024 and FY2026 are
embedded once at scoring time by the same endpoint and version, and those matrices are pinned the same
way". Arm B is a blind-tier arm, so its FY2024 ranking is written and committed here, from text only,
before the scoring run opens the key. No FY2024 label is read; the sealed volume is never opened.

Inputs: the arm B model (volume, via build/task1_fingerprint_embed_v1/MODEL_POINTER.json, sha-checked),
build/universe/fy2024_identity.csv, the sealed-manifest FY2024 text snapshot through
workflow/sealed.load_score_text() (requires UAC_NITRD_TASK1_FREEZE_RUN=1 and a clean committed tree;
this is the snapshot's second, declared use: arm B's scoring-time embedding), and arm A's committed
freeze-run ranking, used only to check that both arms rank the same 64,065 universe awards.

The universe (same rule and order as tools/rank_task1_fy2024_v1.py) is embedded by the pinned hosted
endpoint in fixed 16-row batches, in chunks of CHUNK rows checkpointed to the volume, so the run can
resume across sessions (chunk boundaries are multiples of the batch, so batching is the same as one
pass). Each invocation embeds until --budget-min, then exits; rerun until it reports DONE.

Outputs (write-once):
  $EMBED_ROOT/fy2024/{fy2024.appl_id.i64le, fy2024.emb.f32le, EMBED_SUMMARY.json}   pinned matrices
  build/task1_fy2024_armb_ranking_v1/{ranking.csv.gz, ranking_summary.json, READ_MANIFEST.json}
ranking.csv.gz has arm A's columns; on_shortlist uses arm A's K (equal burden, binding rule 3).
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

RANKING_ID = "task1-fy2024-armb-ranking-v1"
EMBED_ID = "task1-embed-cache-v1"
FY, CHUNK = 2024, 1024
POINTER = ROOT / "build" / "task1_fingerprint_embed_v1" / "MODEL_POINTER.json"
A_DIR = ROOT / "build" / "task1_fy2024_ranking_v1"
A_RULE = ROOT / "build" / "task1_fingerprint_v1" / "shortlist_rule.json"
IDENTITY = ROOT / "build" / "universe" / "fy2024_identity.csv"
OUT = ROOT / "build" / "task1_fy2024_armb_ranking_v1"
EMBED_ROOT = Path(os.environ.get("UAC_NITRD_TASK1_EMBED_ROOT", "/Volumes/users/conroyri/nitrd_hackathon_v1_raw/task1_embed_v1"))
EDIR = EMBED_ROOT / f"fy{FY}"
CHUNKS = EDIR / "_chunks"
HEADER = ["appl_id", "core_project_num", "admin_ic", "rank", "score", "on_shortlist"]


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def log(m: str) -> None:
    print(f"{datetime.now(UTC).strftime('%H:%M:%S')} {m}", flush=True)


def universe(reads: dict) -> list[dict]:
    """FY2024 universe rows in identity order, with text; identical rule to tools/rank_task1_fy2024_v1.py."""
    from workflow import qvr_universe as qu
    from workflow import sealed
    man_raw = sealed.SEAL_MANIFEST.read_bytes()
    man = json.loads(man_raw)
    reads["docs/seal/task1_fy2024_seal_manifest.json"] = _sha(man_raw)
    ident_raw = IDENTITY.read_bytes()
    if _sha(ident_raw) != man["groups"]["universe_pins"]["fy2024_identity.csv"]:
        raise RuntimeError("fy2024_identity.csv does not match the seal manifest pin")
    reads["build/universe/fy2024_identity.csv"] = _sha(ident_raw)
    text = sealed.load_score_text()
    for s in man["text_snapshot"]["shards"]:
        reads[s["file"]] = s["sha256"]
    u = []
    for r in csv.DictReader(io.StringIO(ident_raw.decode("utf-8"))):
        t = text[int(r["appl_id"])]
        rec = {"appl_id": int(r["appl_id"]), "core_project_num": r["core_project_num"],
               "subproject_id": r["subproject_id"], "admin_ic": r["ic_admin"],
               "title": t.get("title"), "abstract": t.get("abstract"), "phr": t.get("public_health_relevance")}
        if qu.in_universe(rec):
            u.append(rec)
    return u


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget-min", type=float, default=50.0)
    a = ap.parse_args(argv)
    t_start = time.time()
    if OUT.exists():
        raise SystemExit(f"{OUT} exists; the arm B FY2024 ranking is written once")
    import numpy as np

    from workflow import embedding as em
    from workflow import fingerprint as fp
    reads: dict[str, str] = {}
    u = universe(reads)
    a_raw = (A_DIR / "ranking.csv.gz").read_bytes()
    reads["build/task1_fy2024_ranking_v1/ranking.csv.gz"] = _sha(a_raw)
    a_ids = {int(r["appl_id"]) for r in csv.DictReader(io.StringIO(gzip.decompress(a_raw).decode()))}
    appl = np.array([r["appl_id"] for r in u], dtype="<i8")
    if set(appl.tolist()) != a_ids or len(appl) != len(a_ids):
        raise RuntimeError("arm B universe differs from arm A's FY2024 ranking universe")
    n = len(u)
    texts = [fp.text_of(r) for r in u]
    CHUNKS.mkdir(parents=True, exist_ok=True)
    (CHUNKS / "appl_order.i64le").exists() or (CHUNKS / "appl_order.i64le").write_bytes(appl.tobytes())
    if (CHUNKS / "appl_order.i64le").read_bytes() != appl.tobytes():
        raise RuntimeError("checkpointed row order differs from this run's universe order")

    enc = em.HostedEncoder()
    starts = list(range(0, n, CHUNK))
    for s in starts:
        f, fm = CHUNKS / f"chunk_{s:06d}.f32le", CHUNKS / f"chunk_{s:06d}.json"
        if f.exists() and fm.exists():
            continue
        if f.exists():  # data without its record: redo the chunk
            f.unlink()
        if (time.time() - t_start) / 60 > a.budget_min:
            done = sum((CHUNKS / f"chunk_{x:06d}.f32le").exists() for x in starts)
            log(f"PAUSED at budget: {done}/{len(starts)} chunks; rerun to continue")
            return 3
        x = enc.embed(texts[s:s + CHUNK])
        f.write_bytes(np.ascontiguousarray(x, dtype="<f4").tobytes())
        fm.write_text(json.dumps({"chunk": s, "rows": len(x), "sha256": _sha(f.read_bytes()),
                                  "session_calls": enc.calls, "versions": sorted(enc.versions_seen)}) + "\n")
        if s // CHUNK % 8 == 0:
            log(f"chunk {s // CHUNK + 1}/{len(starts)}")

    # all chunks present: assemble the pinned matrix (write-once), then rank
    x = np.concatenate([np.frombuffer((CHUNKS / f"chunk_{s:06d}.f32le").read_bytes(), dtype="<f4").reshape(-1, em.PIN["dimensions"])
                        for s in starts])
    if x.shape != (n, em.PIN["dimensions"]) or not np.isfinite(x).all():
        raise RuntimeError(f"assembled matrix shape {x.shape} or non-finite values")
    cmeta = [json.loads((CHUNKS / f"chunk_{s:06d}.json").read_text()) for s in starts]
    if any(m["sha256"] != _sha((CHUNKS / f"chunk_{s:06d}.f32le").read_bytes()) for s, m in zip(starts, cmeta)):
        raise RuntimeError("a chunk does not match its record")
    versions = sorted({v for m in cmeta for v in m["versions"]})
    if versions != [em.PIN["served_model_version"]]:
        raise RuntimeError(f"served versions {versions}")
    emb_bytes, appl_bytes = x.tobytes(), appl.tobytes()
    efile, afile = EDIR / f"fy{FY}.emb.f32le", EDIR / f"fy{FY}.appl_id.i64le"
    if not (EDIR / "EMBED_SUMMARY.json").exists():
        afile.write_bytes(appl_bytes)
        efile.write_bytes(emb_bytes)
        calls = -(-n // em.BATCH)
        esum = {"embed_id": EMBED_ID, "fy": FY, "records": n, "dims": int(x.shape[1]),
                "row_order": "fy2024_identity.csv order, universe rows only (task1-universe-qvr-recon-v1)",
                "files": {afile.name: {"sha256": _sha(appl_bytes), "bytes": len(appl_bytes), "dtype": "<i8"},
                          efile.name: {"sha256": _sha(emb_bytes), "bytes": len(emb_bytes), "dtype": "<f4",
                                       "shape": [int(v) for v in x.shape]}},
                "text_source": "sealed-manifest FY2024 text snapshot (workflow/sealed.load_score_text)",
                "embedding_pin": em.PIN, "encoding": em.ENCODING, "chunk_rows": CHUNK,
                "endpoint_batches": calls, "served_versions_seen": versions,
                "label_fields_used": False, "written_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
        (EDIR / "EMBED_SUMMARY.json").write_text(json.dumps(esum, indent=1, sort_keys=True) + "\n")
    esum_raw = (EDIR / "EMBED_SUMMARY.json").read_bytes()
    esum = json.loads(esum_raw)
    if esum["files"][efile.name]["sha256"] != _sha(efile.read_bytes()) or _sha(emb_bytes) != _sha(efile.read_bytes()):
        raise RuntimeError("pinned FY2024 matrix differs from the chunks")
    reads[f"{EDIR}/EMBED_SUMMARY.json"] = _sha(esum_raw)
    reads[str(efile)] = esum["files"][efile.name]["sha256"]

    ptr_raw = POINTER.read_bytes()
    ptr = json.loads(ptr_raw)
    blob = Path(ptr["path"]).read_bytes()
    if _sha(blob) != ptr["sha256"]:
        raise RuntimeError("arm B model does not match MODEL_POINTER.json")
    reads["build/task1_fingerprint_embed_v1/MODEL_POINTER.json"] = _sha(ptr_raw)
    reads[ptr["path"]] = ptr["sha256"]
    rule_raw = A_RULE.read_bytes()
    rule = json.loads(rule_raw)
    reads["build/task1_fingerprint_v1/shortlist_rule.json"] = _sha(rule_raw)
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
            "repo_head": head, "labels_read": 0, "ranking_csv_sha256": _sha(data),
            "written_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
    OUT.mkdir(parents=True)
    (OUT / "ranking.csv.gz").write_bytes(data)
    (OUT / "ranking_summary.json").write_text(json.dumps(summ, indent=1, sort_keys=True) + "\n")
    (OUT / "READ_MANIFEST.json").write_text(json.dumps(
        {"ranking_id": RANKING_ID, "repo_head": head, "reads": dict(sorted(reads.items())),
         "never_opened": "the sealed volume (FY2024 key, has_any_category supplement); any FY2024 label"},
        indent=1, sort_keys=True) + "\n")
    log("DONE " + json.dumps(summ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
