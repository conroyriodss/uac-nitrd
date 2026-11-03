"""Reconcile the committed FY2021-2023 build universe with QVR/RCDC NITRD award counts (audit artifact).

Identity columns only, from the pinned build/universe files. No API call, no text, no FY2024 or FY2025 data.
The category-329 flag (build-year label) is used only to count the NITRD subset against the QVR targets.

Sequential filters:
  0. starting count (committed universe)
  1. drop subprojects (subproject_id non-empty)
  2. keep extramural grants + admin supplements: drop intramural, contracts, other transactions,
     interagency agreements, classified by activity code = first 3 chars of core_project_num
  3. Contact PI only: no-op in RePORTER (one record per appl_id; PIs are a list with is_contact_pi)
  4. Project status AWARDED: no-op (RePORTER /projects holds funded awards only)
  X. informational, NOT applied: one appl_id per core per FY (would also drop admin supplements and
     multiple awards of a core, which QVR counts separately)

Outputs build/reconciliation/qvr_crosswalk_fy2021_2023.csv (one row per original appl_id) and
qvr_reconciliation.summary.json.
"""
import csv
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE = ROOT / "build" / "universe"
OUT = ROOT / "build" / "reconciliation"
RECON_ID = "qvr-reconcile-v1-2026-10-25"
FYS = (2021, 2022, 2023)
QVR_NITRD = {2021: 2715, 2022: 3111, 2023: 3403}        # owner-supplied QVR / RCDC download counts
TOLERANCE = 0.03
PINS = {  # build-universe pins (task1-build-universe-v1-2026-10-25)
    2021: "d7f7fadd03bb8cfce75ec0cf8329c232d8c3ffc89c73d4b58533baf743832abf",
    2022: "5126368e4971542e6b4d3ad0f1f027a7da3af52ea83e5a4d345022c7581a4079",
    2023: "d96da7b3cbb33d04eb81fa8272f3683348c7ab00acf276e40a1e2a41480338a3",
}
# Step 2 activity-code classes (first 3 chars of core_project_num). Everything else = extramural grant.
NON_GRANT_RULES = (
    ("intramural", "Z.."),
    ("contract", "75N | HHS... | N + 2 digits | starts with a digit (legacy contract numbers)"),
    ("other_transaction", "OT."),
    ("interagency", "Y + 2 digits"),
)


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def instrument(core: str) -> str:
    a = core[:3]
    if a.startswith("Z"):
        return "intramural"
    if a == "75N" or a.startswith("HHS") or re.match(r"^N\d\d$", a) or a[:1].isdigit():
        return "contract"
    if a.startswith("OT"):
        return "other_transaction"
    if re.match(r"^Y\d\d$", a):
        return "interagency"
    return "grant"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    xwalk, summary = [], {"recon_id": RECON_ID, "qvr_targets": QVR_NITRD, "tolerance": TOLERANCE,
                          "non_grant_rules": dict(NON_GRANT_RULES), "universe_pins": {}, "by_fy": {}}
    for fy in FYS:
        path = UNIVERSE / f"fy{fy}.csv"
        got = sha256(path)
        if got != PINS[fy]:
            raise SystemExit(f"{path.name}: sha {got} != pin {PINS[fy]}")
        summary["universe_pins"][path.name] = got
        with path.open(newline="") as f:
            rows = list(csv.DictReader(f))
        first_by_core = {}
        for r in sorted(rows, key=lambda r: int(r["appl_id"])):
            r["instrument"] = instrument(r["core_project_num"])
            if r["subproject_id"]:
                r["dropped_at"] = "1_subproject"
            elif r["instrument"] != "grant":
                r["dropped_at"] = f"2_non_grant:{r['instrument']}"
            else:
                r["dropped_at"] = ""
                # informational only: lowest appl_id kept per core
                r["core_dedup_would_drop"] = "true" if r["core_project_num"] in first_by_core else "false"
                first_by_core.setdefault(r["core_project_num"], r["appl_id"])
            r.setdefault("core_dedup_would_drop", "")
            xwalk.append(r)
        fy_sum = {}
        for scope, sel in (("nitrd_cat329", [r for r in rows if r["cat329"] == "1"]), ("all_nih", rows)):
            s0 = len(sel)
            s1 = sum(not r["subproject_id"] for r in sel)
            s2 = sum(r["dropped_at"] == "" for r in sel)
            sx = sum(r["dropped_at"] == "" and r["core_dedup_would_drop"] == "false" for r in sel)
            d = {"0_start": s0, "1_drop_subprojects": s1, "2_keep_extramural_grants": s2,
                 "3_contact_pi_only": s2, "4_status_awarded": s2, "X_core_dedup_not_applied": sx,
                 "dropped_step2_by_class": {c: sum(r["dropped_at"] == f"2_non_grant:{c}" for r in sel)
                                            for c, _ in NON_GRANT_RULES}}
            if scope == "nitrd_cat329":
                t = QVR_NITRD[fy]
                d["qvr"] = t
                d["diff_vs_qvr_final"] = s2 - t
                d["pct_vs_qvr_final"] = round((s2 - t) / t, 4)
                d["within_tolerance"] = abs(s2 - t) / t <= TOLERANCE
                d["pct_vs_qvr_if_core_dedup"] = round((sx - t) / t, 4)
            fy_sum[scope] = d
        summary["by_fy"][fy] = fy_sum
    cols = ["appl_id", "fy", "core_project_num", "subproject_id", "cat329", "instrument", "dropped_at",
            "core_dedup_would_drop"]
    out = OUT / "qvr_crosswalk_fy2021_2023.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(xwalk, key=lambda r: (int(r["fy"]), int(r["appl_id"]))))
    summary["crosswalk"] = {"path": str(out.relative_to(ROOT)), "rows": len(xwalk), "sha256": sha256(out)}
    (OUT / "qvr_reconciliation.summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    print(json.dumps(summary["by_fy"], indent=1))
    print("crosswalk:", summary["crosswalk"])


if __name__ == "__main__":
    main()
