"""fixture-correction chain: map a superseded fixture hash to its corrected hashes.

docs/FIXTURE_CORRECTION_v1.json records the 2026-11-04 removal of the non-public PCC column from
the FY2025 UAC fixture (single sanctioned history rewrite; old->new commit map in uac-witness
correction record 0003). docs/FIXTURE_CORRECTION_v2.json records the later removal of the PO Name
column by a forward commit (no history rewrite). Frozen records keep citing the original hash; a
check that compares a pinned hash with a file calls `accepted(rel, pinned)`, which follows the
chain of records in order for that one path only. Each record is pinned here, so none can change
silently.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORDS = (  # applied in this order
    ("docs/FIXTURE_CORRECTION_v1.json", "7036c30d12886ced4c354807f38a6dc5c82ee2fed295de369420aab435d9d540"),
    ("docs/FIXTURE_CORRECTION_v2.json", "237ed08328562fcfa71605054583f10d9fd467ac0101afb567d9efd9a8920473"),
)


def load_all() -> list[dict]:
    out = []
    for rel, want in RECORDS:
        raw = (ROOT / rel).read_bytes()
        if hashlib.sha256(raw).hexdigest() != want:
            raise RuntimeError(f"{rel} differs from its pinned sha256")
        out.append(json.loads(raw))
    return out


def load() -> dict:
    """The first record (fixture-correction-v1)."""
    return load_all()[0]


def accepted(rel: str, pinned: str) -> set[str]:
    """Hashes a file at `rel` may have when a frozen record pins `pinned` for it."""
    ok = {pinned}
    for c in load_all():
        if rel == c["path"] and c["superseded_sha256"] in ok:
            ok.add(c["corrected_sha256"])
    return ok


def current(rel: str) -> str | None:
    """The corrected hash of the last record for `rel` (None if no record covers it)."""
    hits = [c["corrected_sha256"] for c in load_all() if c["path"] == rel]
    return hits[-1] if hits else None
