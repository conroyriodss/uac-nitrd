"""Arm B stage 1: embed the FY2019-2021 seed universes once, under the read guard (mode "build").

The hosted encoder (workflow.embedding.PIN) is not bit-deterministic at scale (2026-11-03: about 5% of
rows differ between passes, max |diff| 0.0021, min cosine 0.99992; batch-level, so rounding does not
remove it). Owner decision 2026-11-03: embed FY2019-2021 once, keep the matrices on the volume, and
SHA-pin them; the arm-B fit (tools/build_fingerprint_embed_v1.py) then reads only the pinned matrices,
so it is byte-reproducible.

Per year, $UAC_NITRD_TASK1_EMBED_ROOT/fy{YYYY}/ (write-once; a finished year is never redone):
  fy{YYYY}.appl_id.i64le   universe appl_ids, in seed order (int64 little-endian);
  fy{YYYY}.emb.f32le       embeddings, same row order (float32 little-endian, L2-normalized, rounded);
  EMBED_SUMMARY.json       pin, encoding, shapes, SHA-256 of both files and of the seed files, calls;
  READ_MANIFEST.json       the guard's manifest for this process (seed files read so far).
Text only: no label field is read into, or written to, the cache. The endpoint receives title +
abstract + PHR only.
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

EMBED_ID = "task1-embed-cache-v1"
EMBED_ROOT = Path(os.environ.get("UAC_NITRD_TASK1_EMBED_ROOT",
                                 "/Volumes/users/conroyri/nitrd_hackathon_v1_raw/task1_embed_v1"))
PROGRESS = EMBED_ROOT / "_progress.json"
YEARS = (2019, 2020, 2021)


def log(msg: str) -> None:
    print(f"{datetime.now(UTC).strftime('%H:%M:%S')} {msg}", flush=True)


def load_year(guard: bg.Guard, fy: int) -> tuple[list[dict], dict]:
    d = bg.SEED_ROOT / f"fy{fy}"
    summary_raw = guard.read_bytes(d / "FETCH_SUMMARY.json")
    summary = json.loads(summary_raw)
    raw = guard.read_bytes(d / summary["file"])
    if hashlib.sha256(raw).hexdigest() != summary["sha256_gz"]:
        raise RuntimeError(f"FY{fy}: seed file sha256 differs from its FETCH_SUMMARY")
    rows = [json.loads(line) for line in gzip.decompress(raw).decode("utf-8").split("\n") if line]
    if len(rows) != summary["records"] or any(r["fy"] != fy for r in rows):
        raise RuntimeError(f"FY{fy}: record count or FY mismatch")
    seed = {"FETCH_SUMMARY.json": hashlib.sha256(summary_raw).hexdigest(), summary["file"]: summary["sha256_gz"]}
    return rows, seed


def main() -> int:
    guard = bg.Guard("build", roots=(bg.SEED_ROOT,)).install()
    import numpy as np

    from workflow import embedding as em
    from workflow import fingerprint as fp
    from workflow import qvr_universe as qu

    EMBED_ROOT.mkdir(parents=True, exist_ok=True)
    for fy in YEARS:
        out = EMBED_ROOT / f"fy{fy}"
        if (out / "EMBED_SUMMARY.json").exists():
            log(f"FY{fy}: already embedded; skipped (write-once)")
            continue
        if out.exists() and any(out.iterdir()):
            raise SystemExit(f"{out} has partial files; inspect before rerunning")
        rows, seed = load_year(guard, fy)
        u = [r for r in rows if qu.in_universe(r)]
        texts = [fp.text_of(r) for r in u]  # title + abstract + phr; nothing else leaves the process
        appl = np.array([r["appl_id"] for r in u], dtype="<i8")
        del rows
        log(f"FY{fy}: universe {len(u)}; embedding")
        enc = em.HostedEncoder()
        t0, last = time.time(), [0.0]

        def progress(done: int, total: int, fy=fy, t0=t0, last=last) -> None:
            now = time.time()
            if now - last[0] < 30 and done < total:
                return
            last[0] = now
            rate = done / max(now - t0, 1e-9)
            state = {"embed_id": EMBED_ID, "fy": fy, "done": done, "total": total,
                     "elapsed_s": round(now - t0), "docs_per_s": round(rate, 1),
                     "eta_s": round((total - done) / rate) if rate else None,
                     "updated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
            log(f"FY{fy} embed {done}/{total} {rate:.1f}/s ETA {state['eta_s']}s")
            PROGRESS.write_text(json.dumps(state) + "\n")

        x = enc.embed(texts, progress=progress)
        emb_bytes = np.ascontiguousarray(x, dtype="<f4").tobytes()
        appl_bytes = appl.tobytes()
        out.mkdir(parents=True, exist_ok=True)
        (out / f"fy{fy}.appl_id.i64le").write_bytes(appl_bytes)
        (out / f"fy{fy}.emb.f32le").write_bytes(emb_bytes)
        summary = {
            "embed_id": EMBED_ID, "fy": fy, "universe_rule": qu.UNIVERSE_RULE_ID, "records": len(u),
            "dims": int(x.shape[1]), "row_order": "seed file order, universe rows only",
            "files": {f"fy{fy}.appl_id.i64le": {"sha256": hashlib.sha256(appl_bytes).hexdigest(),
                                                 "bytes": len(appl_bytes), "dtype": "<i8"},
                      f"fy{fy}.emb.f32le": {"sha256": hashlib.sha256(emb_bytes).hexdigest(),
                                            "bytes": len(emb_bytes), "dtype": "<f4",
                                            "shape": [int(s) for s in x.shape]}},
            "seed_files_sha256": seed, "embedding_pin": em.PIN, "encoding": em.ENCODING,
            "endpoint_calls": enc.calls, "served_versions_seen": sorted(enc.versions_seen),
            "label_fields_used": False, "label_fields_written": False, "elapsed_s": round(time.time() - t0),
            "written_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        guard.write_manifest(out / "READ_MANIFEST.json")
        (out / "EMBED_SUMMARY.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
        log(f"FY{fy}: wrote {x.shape}; emb sha256 {summary['files'][f'fy{fy}.emb.f32le']['sha256']}")
        del x, emb_bytes, texts, u
    log("all years embedded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
