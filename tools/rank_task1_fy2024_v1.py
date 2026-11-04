"""Task 1 FY2024 freeze-run ranking from fingerprint v1 (RANKING_ID = task1-fy2024-ranking-v1).

The single freeze run of pre-registration section 0 step 3. It scores the FY2024 universe with arm A
(the shipped fingerprint) and writes, once, build/task1_fy2024_ranking_v1/:

* ranking.csv.gz: every FY2024 universe award (reconstructed QVR filter) with score, rank and
  on_shortlist at the calibrated fraction (K = ceil(f x N), N = the whole FY2024 universe,
  File A awards included; pre-registration section 5);
* ranking_summary.json: universe size, K, drops, input hashes;
* READ_MANIFEST.json: sha256 of every file this run opened.

Inputs, and nothing else:
  build/task1_fingerprint_v1/{model.json.gz, shortlist_rule.json}   arm A (committed)
  build/universe/fy2024_identity.csv                               identity only (pinned by the seal)
  cache/task1_fy2024_text/ via workflow/sealed.load_score_text()   label-free text snapshot
No FY2024 label is read: the sealed key and the has_any_category supplement live in the sealed
volume, which this tool never opens. load_score_text() refuses unless UAC_NITRD_TASK1_FREEZE_RUN=1
and cache/, workflow/, build/, docs/seal/ and docs/TASK1_MATCH_RULE.md are committed and clean.

`--verify-fy2026` runs the same scoring path on the committed FY2026 forecast inputs (label-free
FY2026 seed) and checks that it reproduces build/task1_forecast_fy2026/forecast.csv.gz byte for
byte. It writes nothing. Run it before the freeze run.
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
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RANKING_ID = "task1-fy2024-ranking-v1"
FY = 2024
FP_DIR = ROOT / "build" / "task1_fingerprint_v1"
IDENTITY = ROOT / "build" / "universe" / "fy2024_identity.csv"
OUT = ROOT / "build" / "task1_fy2024_ranking_v1"
FORECAST = ROOT / "build" / "task1_forecast_fy2026"
SEED_ROOT = Path(os.environ.get("UAC_NITRD_TASK1_SEED_ROOT", "/Volumes/users/conroyri/nitrd_hackathon_v1_raw/task1_seed_v1"))
HEADER = ["appl_id", "core_project_num", "admin_ic", "rank", "score", "on_shortlist"]


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class Reads:
    """Records the sha256 of every file opened by this run."""

    def __init__(self):
        self.files: dict[str, dict] = {}

    def read(self, p: Path) -> bytes:
        b = p.read_bytes()
        self.files[str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p)] = {"sha256": _sha(b), "bytes": len(b)}
        return b


def load_model(reads: Reads):
    from workflow import fingerprint as fp
    rule = json.loads(reads.read(FP_DIR / "shortlist_rule.json"))
    blob = reads.read(FP_DIR / "model.json.gz")
    if _sha(blob) != rule["model_sha256"]:
        raise RuntimeError("model.json.gz does not match shortlist_rule.json")
    return rule, fp.Model.from_bytes(blob)


def rank_rows(u: list[dict], model, rule) -> tuple[bytes, int, int]:
    """Score, rank and cut exactly as tools/forecast_task1_fy2026.py does. Returns (csv.gz, n, k)."""
    import numpy as np

    from workflow import fingerprint as fp
    n = len(u)
    scores = model.score(model.transform([fp.text_of(r) for r in u]))
    appl = np.array([r["appl_id"] for r in u], dtype=np.int64)
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
    return gzip.compress(buf.getvalue().encode("utf-8"), mtime=0), n, k


def verify_fy2026() -> int:
    from workflow import qvr_universe as qu
    reads = Reads()
    rule, model = load_model(reads)
    seed = SEED_ROOT / "fy2026"
    summary = json.loads(reads.read(seed / "FETCH_SUMMARY.json"))
    raw = reads.read(seed / summary["file"])
    if _sha(raw) != summary["sha256_gz"] or summary["labels_requested"]:
        raise RuntimeError("FY2026 seed does not match its label-free FETCH_SUMMARY")
    rows = [json.loads(x) for x in gzip.decompress(raw).decode("utf-8").split("\n") if x]
    data, n, k = rank_rows([r for r in rows if qu.in_universe(r)], model, rule)
    want = json.loads((FORECAST / "forecast_summary.json").read_text())["forecast_csv_sha256"]
    ok = _sha(data) == want == _sha((FORECAST / "forecast.csv.gz").read_bytes())
    print(json.dumps({"verify_fy2026": "PASS" if ok else "FAIL", "n": n, "k": k, "sha256": _sha(data),
                      "committed_sha256": want}, indent=1))
    return 0 if ok else 1


def freeze_run() -> int:
    from workflow import qvr_universe as qu
    from workflow import sealed
    if OUT.exists():
        raise SystemExit(f"{OUT} exists; the FY2024 ranking is written once")
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    reads = Reads()
    rule, model = load_model(reads)
    man = json.loads(reads.read(sealed.SEAL_MANIFEST))
    ident_raw = reads.read(IDENTITY)
    if _sha(ident_raw) != man["groups"]["universe_pins"]["fy2024_identity.csv"]:
        raise RuntimeError("fy2024_identity.csv does not match the seal manifest pin")
    ident = list(csv.DictReader(io.StringIO(ident_raw.decode("utf-8"))))
    if set(ident[0]) != {"appl_id", "fy", "core_project_num", "subproject_id", "ic_admin"}:
        raise RuntimeError(f"unexpected identity columns {sorted(ident[0])}")

    text = sealed.load_score_text()  # refuses outside the freeze run; verifies every shard + record hash
    for s in man["text_snapshot"]["shards"]:
        reads.files[s["file"]] = {"sha256": s["sha256"], "bytes": (ROOT / s["file"]).stat().st_size}
    if any(k not in sealed.manifest()["text_snapshot"]["fields"] for r in list(text.values())[:1] for k in r):
        raise RuntimeError("text snapshot record carries a field outside the sealed field list")

    ids = {int(r["appl_id"]) for r in ident}
    if ids != set(text) or len(ids) != len(ident) or len(ids) != man["text_snapshot"]["records"]:
        raise RuntimeError("identity file and text snapshot do not cover the same FY2024 awards")
    drops: dict[str, int] = {}
    u = []
    for r in ident:
        t = text[int(r["appl_id"])]
        if int(r["fy"]) != FY or int(t["fiscal_year"]) != FY or (t["core_project_num"] or "") != r["core_project_num"]:
            raise RuntimeError(f"appl_id {r['appl_id']}: identity and snapshot disagree")
        rec = {"appl_id": int(r["appl_id"]), "core_project_num": r["core_project_num"],
               "subproject_id": r["subproject_id"], "admin_ic": r["ic_admin"],
               "title": t.get("title"), "abstract": t.get("abstract"), "phr": t.get("public_health_relevance")}
        k = qu.exclusion(rec) or "in_universe"
        drops[k] = drops.get(k, 0) + 1
        if k == "in_universe":
            u.append(rec)
    del text

    data, n, k = rank_rows(u, model, rule)
    from workflow import fingerprint as fp
    import sklearn
    out = {
        "ranking_id": RANKING_ID, "fy": FY, "written_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_head": head, "freeze_env": sealed.FREEZE_ENV, "labels_read": 0,
        "fingerprint_id": rule["fingerprint_id"], "model_sha256": rule["model_sha256"],
        "seal_id": man["seal_id"], "text_snapshot_aggregate_sha256": man["text_snapshot"]["aggregate_sha256"],
        "identity_sha256": _sha(ident_raw), "universe_rule": qu.UNIVERSE_RULE_ID, "universe_drops": drops,
        "universe": n, "shortlist_fraction": rule["shortlist_fraction"], "k": k,
        "secondary_k": {name: fp.shortlist_size(f, n) for name, f in rule["secondary_fractions"].items()},
        "text_field_map": {"title": "title", "abstract": "abstract", "phr": "public_health_relevance"},
        "sklearn": sklearn.__version__, "ranking_csv_sha256": _sha(data),
    }
    OUT.mkdir(parents=True)
    (OUT / "ranking.csv.gz").write_bytes(data)
    (OUT / "ranking_summary.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    rm = {"ranking_id": RANKING_ID, "repo_head": head, "reads": dict(sorted(reads.files.items())),
          "never_opened": "the sealed volume (FY2024 key, has_any_category supplement); any FY2024 label"}
    (OUT / "READ_MANIFEST.json").write_text(json.dumps(rm, indent=1, sort_keys=True) + "\n")
    out["read_manifest_sha256"] = _sha((OUT / "READ_MANIFEST.json").read_bytes())
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verify-fy2026", action="store_true")
    a = ap.parse_args(argv)
    return verify_fy2026() if a.verify_fy2026 else freeze_run()


if __name__ == "__main__":
    sys.exit(main())
