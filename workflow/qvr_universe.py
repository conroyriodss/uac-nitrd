"""Task 1 universe: the reconstructed QVR filter (UNIVERSE_RULE_ID = task1-universe-qvr-recon-v1).

Reconstructed, pending ODSS confirmation. Same rule for every fiscal year, identity fields only:

  1. drop subprojects (subproject_id non-empty);
  2. keep extramural grants + admin supplements; drop intramural (core starts Z), contracts (75N, HHS...,
     N + 2 digits, or a leading digit), other transactions (OT...) and interagency agreements (Y + 2 digits),
     classified by the first 3 characters of core_project_num (as in tools/qvr_reconcile.py);
  3. drop the Clinical Center (admin IC CC in RePORTER, CL in ExPORTER).
"""

from __future__ import annotations

import re

UNIVERSE_RULE_ID = "task1-universe-qvr-recon-v1"
CLINICAL_CENTER = ("CC", "CL", "CLC")


def instrument(core: str) -> str:
    a = (core or "")[:3]
    if a.startswith("Z"):
        return "intramural"
    if a == "75N" or a.startswith("HHS") or re.match(r"^N\d\d$", a) or a[:1].isdigit():
        return "contract"
    if a.startswith("OT"):
        return "other_transaction"
    if re.match(r"^Y\d\d$", a):
        return "interagency"
    return "grant"


def exclusion(rec: dict) -> str | None:
    """None if the record is in the universe, else the first rule that drops it."""
    if rec.get("subproject_id"):
        return "1_subproject"
    kind = instrument(rec.get("core_project_num") or "")
    if kind != "grant":
        return f"2_{kind}"
    if (rec.get("admin_ic") or "").upper() in CLINICAL_CENTER:
        return "3_clinical_center"
    return None


def in_universe(rec: dict) -> bool:
    return exclusion(rec) is None
