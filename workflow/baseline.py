"""Carry-forward baseline for Task 1 (NITRD parent membership). DEV / not scored.

BASELINE_ID = carry-forward-v1-2026-10-25.

Rule (deterministic, labels from prior FYs only):
* A core project is category-329 in a FY if ANY of its records that FY carries the flag ("any" rule).
* For a target FY, each core project present in at least one prior FY of the window is CONTINUING and is
  predicted with its label from the MOST RECENT prior FY in which it appears. A core present in no prior
  FY is NEW and is predicted 0 (the baseline has nothing to carry).
* Every appl_id inherits its core's prediction (appl-level predictions are the core prediction copied).

evaluate() reads the target FY's labels, so it refuses any reserved FY: the baseline is backtested inside
the build window only. FY2024 predictions are produced from FY2024 IDENTITY + build-FY labels and are never
compared to an FY2024 label here.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

from workflow.common import RESERVED_FYS, DevBoundaryError

BASELINE_ID = "carry-forward-v1-2026-10-25"


def load_universe(path: Path) -> list[dict]:
    with Path(path).open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["appl_id"], r["fy"] = int(r["appl_id"]), int(r["fy"])
        if "cat329" in r:
            r["cat329"] = int(r["cat329"])
    return rows


def core_labels(rows: list[dict]) -> dict[str, int]:
    """Core-level label by the 'any' rule. Requires a labelled (build-FY) universe."""
    fys = {r["fy"] for r in rows}
    if fys & set(RESERVED_FYS):
        raise DevBoundaryError(f"labels for reserved FY{sorted(fys & set(RESERVED_FYS))} refused")
    out: dict[str, int] = {}
    for r in rows:
        out[r["core_project_num"]] = max(out.get(r["core_project_num"], 0), r["cat329"])
    return out


def predict(target_rows: list[dict], prior: dict[int, dict[str, int]]) -> dict:
    """Carry-forward predictions for the target FY's identity rows. Never reads target labels."""
    tfy = {r["fy"] for r in target_rows}
    if len(tfy) != 1:
        raise ValueError(f"target rows span FYs {sorted(tfy)}")
    tfy = tfy.pop()
    if any(fy >= tfy for fy in prior):
        raise ValueError("prior FYs must all precede the target FY")
    cores: dict[str, dict] = {}
    for c in sorted({r["core_project_num"] for r in target_rows}):
        src = max((fy for fy, lab in prior.items() if c in lab), default=None)
        cores[c] = {"stratum": "new" if src is None else "continuing", "source_fy": src,
                    "prediction": 0 if src is None else prior[src][c]}
    appls = {r["appl_id"]: {"core_project_num": r["core_project_num"], **cores[r["core_project_num"]]}
             for r in target_rows}
    return {"baseline_id": BASELINE_ID, "target_fy": tfy, "prior_fys": sorted(prior), "cores": cores, "appls": appls}


def _wilson(k: int, n: int, z: float = 1.959964) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4) + 0.0, round(min(1.0, c + h), 4)]


def _metrics(pairs: list[tuple[int, int]]) -> dict:
    tp = sum(1 for p, y in pairs if p and y)
    fp = sum(1 for p, y in pairs if p and not y)
    fn = sum(1 for p, y in pairs if not p and y)
    tn = len(pairs) - tp - fp - fn
    return {"n": len(pairs), "positives": tp + fn, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "recall": round(tp / (tp + fn), 4) if tp + fn else None, "recall_ci95": _wilson(tp, tp + fn),
            "precision": round(tp / (tp + fp), 4) if tp + fp else None, "precision_ci95": _wilson(tp, tp + fp)}


def evaluate(pred: dict, target_rows: list[dict]) -> dict:
    """Backtest inside the build window. Refuses reserved FYs (their labels are held out)."""
    tfy = pred["target_fy"]
    if tfy in RESERVED_FYS:
        raise DevBoundaryError(f"FY{tfy} is reserved ({RESERVED_FYS[tfy]}); the baseline is not scored against it")
    y_core = core_labels(target_rows)
    y_appl = {r["appl_id"]: r["cat329"] for r in target_rows}
    if set(y_core) != set(pred["cores"]) or set(y_appl) != set(pred["appls"]):
        raise ValueError("predictions do not cover the target universe exactly")
    out = {}
    for level, P, Y in (("core", pred["cores"], y_core), ("appl", pred["appls"], y_appl)):
        out[level] = {s: _metrics([(P[k]["prediction"], Y[k]) for k in sorted(P) if s == "all" or P[k]["stratum"] == s])
                      for s in ("all", "new", "continuing")}
    cont = [c for c in sorted(pred["cores"]) if pred["cores"][c]["stratum"] == "continuing"]
    flips = [c for c in cont if pred["cores"][c]["prediction"] != y_core[c]]
    out["continuing_core_flips"] = {"n": len(flips), "entered_329": sum(y_core[c] for c in flips),
                                    "left_329": sum(1 - y_core[c] for c in flips),
                                    "baseline_correct_on_flips": 0}
    out["source_fy_mix"] = {str(fy): sum(1 for c in cont if pred["cores"][c]["source_fy"] == fy)
                            for fy in pred["prior_fys"]}
    return out
