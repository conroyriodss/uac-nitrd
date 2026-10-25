"""Shared constants and boundary checks for the NITRD workflow skeleton (Tasks 1-3), DEV only.

The skeleton runs ONLY on a committed DEV slice of public RePORTER awards from a non-score FY.
It refuses the reserved FYs and any of the 480 evaluation projects, it never reads category
fields, and every output carries DEV_LABEL. Nothing here produces a scored result.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.inputs import ProjectRef, evaluation_appl_ids, load_project_refs  # noqa: E402
from workflow.sealed import guard_build_read  # noqa: E402

WORKFLOW_ID = "nitrd-workflow-skeleton-v0-2026-10-25"
DEV_LABEL = ("DEV / not scored. Workflow skeleton run on a development slice of public RePORTER awards; "
             "no held-out data was read and no result here is a score.")
# FYs the DEV skeleton must never run on. 2024 = proposed Task 1 score FY (held out, not yet sealed);
# 2025 = contaminated (UAC 480 and File A FY2025 already used and scored).
RESERVED_FYS = {2024: "proposed Task 1 score FY (held out)", 2025: "contaminated: UAC 480 / File A FY2025"}
PARENT_CROSSCUT = "NITRD_PARENT"      # Task 1 store: was-this-award-NITRD-relevant
PARENT_CODES = ("NITRD",)
SUBCAT_CROSSCUT = "NITRD"             # Task 2 store: PCA subcategory (existing invariants)
FINGERPRINT = ROOT / "workflow" / "fingerprint" / "nitrd_parent_fingerprint.placeholder.v0.json"
FINGERPRINT_SHA256 = "90a7e1cbed3bccf891ee06fd4b9d4bd198eaacf275b7d8d6e7cec054eba73c7d"
DEV_SLICE = ROOT / "dev" / "fy2023_dev_slice"


class DevBoundaryError(RuntimeError):
    """The DEV skeleton was pointed at data it must not touch."""


def sha256(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def check_dev_refs(refs: list[ProjectRef]) -> int:
    """Refuse reserved FYs, mixed FYs and any evaluation project. Returns the slice FY."""
    if not refs:
        raise DevBoundaryError("empty DEV slice")
    fys = {r.fy for r in refs}
    if len(fys) != 1:
        raise DevBoundaryError(f"DEV slice mixes FYs {sorted(fys)}")
    fy = fys.pop()
    if fy in RESERVED_FYS:
        raise DevBoundaryError(f"FY{fy} is reserved ({RESERVED_FYS[fy]}); the DEV skeleton refuses it")
    hit = sorted({r.appl_id for r in refs} & evaluation_appl_ids())
    if hit:
        raise DevBoundaryError(f"{len(hit)} evaluation project(s) in the DEV slice; refused")
    return fy


def load_dev_refs(fixture: Path) -> tuple[list[ProjectRef], int]:
    guard_build_read(fixture)                # never a sealed location or the FY2024 text snapshot
    refs = load_project_refs(fixture)        # identity columns only (input boundary 1)
    return refs, check_dev_refs(refs)


def load_cache(cache: Path) -> tuple[dict[int, dict], dict[int, str]]:
    """(records, per-record snapshot sha) keyed by appl_id; same hashing as tools/load_proposals."""
    guard_build_read(cache)
    recs, snaps = {}, {}
    for line in Path(cache).read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            recs[int(r["appl_id"])] = r
            snaps[int(r["appl_id"])] = hashlib.sha256(line.encode("utf-8")).hexdigest()
    return recs, snaps


def check_fingerprint(path: Path = FINGERPRINT, expected: str | None = FINGERPRINT_SHA256) -> dict:
    got = sha256(path)
    if expected is not None and got != expected:
        raise DevBoundaryError(f"fingerprint sha256 {got} != pinned {expected}; a new version needs a new pin")
    fp = json.loads(Path(path).read_text(encoding="utf-8"))
    fp["_sha256"] = got
    return fp


def write_json(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=1, sort_keys=True) + "\n", encoding="utf-8")
