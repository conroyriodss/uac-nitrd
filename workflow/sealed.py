"""Task 1 FY2024 seal boundary: BOUNDARY_ID = task1-seal-boundary-v1-2026-10-25.

Two artifacts came out of the FY2024 seal, and this module is the only gate to either:

* SEALED KEY (labels + score groups): lives in the sealed volume, never in this repo. Any directory that
  holds a seal marker file (or has one in an ancestor) is sealed. guard_build_read() refuses such paths
  for every build-path loader. open_sealed_key() is the only reader, and only in a scoring run
  (UAC_NITRD_TASK1_SCORE_RUN=1).
* INPUT TEXT SNAPSHOT (cache/task1_fy2024_text/): label-free FY2024 text, committed. Its bytes may be
  hashed at any time (verify_snapshot), but its records are returned only to the fingerprint freeze run:
  load_score_text() requires UAC_NITRD_TASK1_FREEZE_RUN=1 and a clean committed tree. Build-path loaders
  refuse the snapshot directory outright.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import subprocess
from pathlib import Path

BOUNDARY_ID = "task1-seal-boundary-v1-2026-10-25"
ROOT = Path(__file__).resolve().parents[1]
SEAL_MARKERS = ("SEAL_MANIFEST.json", "TASK1_SEAL_RECORD.json")
SCORE_ENV = "UAC_NITRD_TASK1_SCORE_RUN"
FREEZE_ENV = "UAC_NITRD_TASK1_FREEZE_RUN"
SNAPSHOT_DIR = ROOT / "cache" / "task1_fy2024_text"
SEAL_MANIFEST = ROOT / "docs" / "seal" / "task1_fy2024_seal_manifest.json"
FREEZE_CLEAN_PATHS = ("cache", "workflow", "docs/TASK1_MATCH_RULE.md", "docs/seal", "build")


class SealBoundaryError(RuntimeError):
    """A sealed key or the score-FY text snapshot was reached outside its one permitted use."""


def in_sealed_dir(path: Path) -> bool:
    p = Path(path).resolve()
    for d in ([p] if p.is_dir() else []) + list(p.parents):
        try:
            if any((d / m).is_file() for m in SEAL_MARKERS):
                return True
        except OSError:
            continue
    return False


def in_snapshot(path: Path) -> bool:
    p, s = Path(path).resolve(), SNAPSHOT_DIR.resolve()
    return p == s or s in p.parents


def guard_build_read(path: Path) -> None:
    """Called by every build-path loader before it opens a file."""
    if in_sealed_dir(path):
        raise SealBoundaryError(f"{path}: sealed location; build-path tools may not read it")
    if in_snapshot(path):
        raise SealBoundaryError(f"{path}: FY2024 text snapshot; only the fingerprint freeze run may read it")


def open_sealed_key(path: Path, *, env=None) -> str:
    """The only reader of the sealed key. Scoring runs only."""
    env = os.environ if env is None else env
    if env.get(SCORE_ENV) != "1":
        raise SealBoundaryError(f"sealed key read refused: {SCORE_ENV}=1 is set only by the scoring run")
    return Path(path).read_text(encoding="utf-8")


def manifest() -> dict:
    return json.loads(SEAL_MANIFEST.read_text(encoding="utf-8"))


def verify_snapshot(root: Path = ROOT) -> dict:
    """Hash-only check of the snapshot shards against the manifest. Does not parse any record."""
    m = json.loads((root / SEAL_MANIFEST.relative_to(ROOT)).read_text(encoding="utf-8"))
    shards = m["text_snapshot"]["shards"]
    bad = [s["file"] for s in shards
           if hashlib.sha256((root / s["file"]).read_bytes()).hexdigest() != s["sha256"]]
    if bad:
        raise SealBoundaryError(f"text snapshot shard(s) do not match the seal manifest: {bad}")
    return {"shards": len(shards), "records": m["text_snapshot"]["records"]}


def text_access_problems(*, freeze_env: bool, porcelain: str | None) -> list[str]:
    """Pure decision for load_score_text. Empty list = allowed."""
    out = []
    if not freeze_env:
        out.append(f"{FREEZE_ENV}=1 is not set: the FY2024 text snapshot is for the fingerprint freeze run only")
    if porcelain is None:
        out.append("git status unavailable: cannot prove the freeze inputs are committed")
    elif porcelain.strip():
        out.append("uncommitted changes under " + ", ".join(FREEZE_CLEAN_PATHS))
    return out


def _porcelain(root: Path) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", *FREEZE_CLEAN_PATHS],
                           capture_output=True, text=True, timeout=60)
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def load_score_text(root: Path = ROOT, *, env=None) -> dict[int, dict]:
    """FY2024 text records keyed by appl_id, for the fingerprint freeze run only."""
    env = os.environ if env is None else env
    problems = text_access_problems(freeze_env=env.get(FREEZE_ENV) == "1", porcelain=_porcelain(root))
    if problems:
        raise SealBoundaryError("; ".join(problems))
    verify_snapshot(root)
    m = json.loads((root / SEAL_MANIFEST.relative_to(ROOT)).read_text(encoding="utf-8"))
    out: dict[int, dict] = {}
    agg = hashlib.sha256()
    for s in m["text_snapshot"]["shards"]:
        raw = gzip.decompress((root / s["file"]).read_bytes())
        agg.update(raw)
        for line in raw.decode("utf-8").splitlines():
            r = json.loads(line)
            body = {k: v for k, v in r.items() if k != "record_sha256"}
            if hashlib.sha256(canonical(body).encode("utf-8")).hexdigest() != r["record_sha256"]:
                raise SealBoundaryError(f"appl_id {r.get('appl_id')}: per-record sha mismatch")
            out[int(r["appl_id"])] = r
    if agg.hexdigest() != m["text_snapshot"]["aggregate_sha256"] or len(out) != m["text_snapshot"]["records"]:
        raise SealBoundaryError("text snapshot aggregate does not match the seal manifest")
    return out


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
