"""fixture-correction-v1: map the one superseded fixture hash to its corrected hash.

docs/FIXTURE_CORRECTION_v1.json records the 2026-11-04 removal of the non-public PCC column from
the FY2025 UAC fixture (single sanctioned history rewrite; old->new commit map in uac-witness
correction record 0003). Frozen records keep citing the superseded hash; a check that compares a
pinned hash with a file calls `accepted(rel, pinned)` and accepts the corrected hash for that one
path only. The record itself is pinned here, so it cannot change silently.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "FIXTURE_CORRECTION_v1.json"
RECORD_SHA256 = "7036c30d12886ced4c354807f38a6dc5c82ee2fed295de369420aab435d9d540"


def load() -> dict:
    raw = RECORD.read_bytes()
    if hashlib.sha256(raw).hexdigest() != RECORD_SHA256:
        raise RuntimeError("docs/FIXTURE_CORRECTION_v1.json differs from its pinned sha256")
    return json.loads(raw)


def accepted(rel: str, pinned: str) -> set[str]:
    """Hashes a file at `rel` may have when a frozen record pins `pinned` for it."""
    c = load()
    if rel == c["path"] and pinned == c["superseded_sha256"]:
        return {pinned, c["corrected_sha256"]}
    return {pinned}
