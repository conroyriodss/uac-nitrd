"""Task 2: subcategory proposals for SME-CONFIRMED Task 1 candidates. DEV / not scored.

Reuses the existing deterministic engine unchanged (engine/run.py, scope-only vocabulary,
freeze-guard-v1), now positioned DOWNSTREAM of Task 1: its input universe is exactly the set of
awards an SME confirmed as NITRD-relevant in the Task 1 store. The engine is run as a subprocess
through its normal CLI on a DEV fixture (identity columns only), so input boundary 1 and the
freeze guard apply as they do everywhere: the guard refuses if any of the 480 appear.
The engine's proposals go into a second governed store (crosscut NITRD) whose listing is the
confirmed set, i.e. the Task 1 output becomes the Task 2 parent listing.
"""
from __future__ import annotations

import csv
import os
import subprocess
import sys
from pathlib import Path

from store import SandboxStore
from tools.load_proposals import build_listing, load_proposals
from workflow.common import (DEV_LABEL, PARENT_CROSSCUT, ROOT, SUBCAT_CROSSCUT, WORKFLOW_ID, check_dev_refs,
                             sha256, write_json)


def confirmed(store1, fy: int) -> list[dict]:
    """Awards with an ACTIVE Task 1 assignment (SME-approved or SME-added), from the store only."""
    L = store1._listings[(PARENT_CROSSCUT, fy)]
    ids = sorted(a for (c, f, a) in store1._active if (c, f) == (PARENT_CROSSCUT, fy) and L["status"][a] == "listed")
    return [L["projects"][a] for a in ids]


def run(store1, fy: int, cache: Path, out_dir: Path, coders: set[str]) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    projects = confirmed(store1, fy)
    fx = out_dir / "confirmed_fixture.csv"
    with fx.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Appl ID", "FY", "Project Number", "SubProj"])
        for p in projects:
            w.writerow([p["appl_id"], p["fy"], p["project_num"], p["subproj"]])
    from engine.inputs import load_project_refs
    check_dev_refs(load_project_refs(fx))
    env = {k: v for k, v in os.environ.items() if k != "UAC_NITRD_FREEZE_RUN"}
    env["PYTHONHASHSEED"] = "0"
    eng = out_dir / "engine"
    r = subprocess.run([sys.executable, str(ROOT / "engine" / "run.py"), "--fixture", str(fx), "--cache", str(cache),
                        "--out-dir", str(eng), "--offline"], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"engine exit {r.returncode}: {r.stderr.strip()[-500:]}")
    store2 = SandboxStore(out_dir / "store_task2", authorized_coders=coders)
    listing = build_listing(fx, cache, None, crosscut=SUBCAT_CROSSCUT)
    store2.load_listing(listing)
    loaded = load_proposals(store2, eng / "proposals.csv", eng / "explanations.jsonl", crosscut=SUBCAT_CROSSCUT)
    meta = {"label": DEV_LABEL, "stage": "task2_subcategory", "workflow_id": WORKFLOW_ID, "fiscal_year": fy,
            "input": "SME-confirmed Task 1 awards (active assignments in the Task 1 store)",
            "confirmed": len(projects), "engine_stdout": r.stdout.strip().splitlines(),
            "confirmed_fixture_sha256": sha256(fx), "proposals_sha256": sha256(eng / "proposals.csv"),
            "explanations_sha256": sha256(eng / "explanations.jsonl"),
            "loaded": {k: loaded[k] for k in ("proposed", "rejected", "abstained")}}
    write_json(out_dir / "task2.meta.json", meta)
    return {"meta": meta, "store": store2, "loaded": loaded}
