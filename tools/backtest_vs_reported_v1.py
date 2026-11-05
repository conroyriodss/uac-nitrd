"""Performance vs reported NITRD data (BACKTEST_ID = task1-backtest-vs-reported-v1). Evaluation code, NOT under
the build guard; nothing here feeds a model.

The frozen arm A fingerprint (task1-fingerprint-v1, model b703083d) is applied unchanged to the FY2022, FY2023
and FY2025 universes (task1-universe-qvr-recon-v1) and compared with the publicly reported NITRD listing:
RePORTER per-award membership in spending category 329, reduced on receipt (tools/fetch_task1_text.reduce_record).

  FY2022, FY2023  exposed (labels read 2026-10-25); fetches from tools/tier3_task1_v1.py, re-scored here
  FY2024          blind point: read from the committed one-shot score report (build/task1_fy2024_score_v1,
                  faadcd2); the key is NOT re-opened. Tier 2 (non-File-A) is the blind value; the all-awards
                  value pools Tier 2 and the exposed Tier 2x and is labeled mixed
  FY2025          exposed (FY2025 NITRD awards were read by Task 2 in 2026-10); fetched here with the same fetch
                  function, write-once to $UAC_NITRD_TASK1_BACKTEST_ROOT/fy2025/
  FY2026          count forecast (build/task1_forecast_fy2026) against the reported count trend; no labels

recall@K at arm A's calibrated fraction (11.55%), precision, new-core recall (no NIH record in the three
prior FYs), and the pre-registered count forecast formula (1 - u2021) x r2021 x sum(score) applied to each year
with the frozen FY2021 constants. Nothing before FY2022 is evaluated; FY2021 is shown only as the training-year
reference count. The pre-FY2019 NITRD definition regime is not comparable and is not used.

Writes build/task1_backtest_vs_reported_v1/{report.json, performance_vs_reported.png, READ_MANIFEST.json} once.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BACKTEST_ID = "task1-backtest-vs-reported-v1"
OUT = ROOT / "build" / "task1_backtest_vs_reported_v1"
BT_ROOT = Path(os.environ.get("UAC_NITRD_TASK1_BACKTEST_ROOT",
                              "/Volumes/users/conroyri/nitrd_hackathon_v1_raw/task1_backtest_v1"))
SCORE_REPORT = ("build/task1_fy2024_score_v1/report.json", "2fc574fe781fb2fedcc05319c97c3714ed7d3201ac1989ca5dd9480c5c891e11")
RANK_2024 = ("build/task1_fy2024_ranking_v1/ranking.csv.gz", "e49e844d1ebf43691cf3d66ef70f7c415d7dd50f1deccac845709cd656ffa8dd")
FORECAST = ("build/task1_forecast_fy2026/forecast_summary.json", None)
ID_2024 = "build/universe/fy2024_identity.csv"
REGIME_NOTE = ("NITRD category definitions before FY2019 are a different regime and are not comparable; "
               "no point before FY2022 is evaluated (FY2021 = training-year reference only).")


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class Reads(dict):
    def get_bytes(self, p: Path, pin: str | None = None) -> bytes:
        b = Path(p).read_bytes()
        if pin and _sha(b) != pin:
            raise RuntimeError(f"{p} does not match its pin")
        self[str(p)] = _sha(b)
        return b


def _load_fetch(d: Path, reads: Reads) -> list[dict]:
    summ = json.loads(reads.get_bytes(d / "FETCH_SUMMARY.json"))
    raw = reads.get_bytes(d / summ["file"], summ["sha256_gz"])
    return [json.loads(x) for x in gzip.decompress(raw).decode("utf-8").split("\n") if x]


def main() -> int:
    import numpy as np

    import tools.tier3_task1_v1 as t3
    from workflow import fingerprint as fp
    from workflow import qvr_universe as qu
    from workflow import reveal_metrics as rm
    if OUT.exists():
        raise SystemExit(f"{OUT} exists (write-once)")
    if not (BT_ROOT / "fy2025" / "FETCH_SUMMARY.json").exists():
        t3.T3_ROOT = BT_ROOT
        s = t3.fetch(2025)
        print("fetched FY2025", s["records"], s["nih_total"], s["sha256_gz"], flush=True)
    reads = Reads()
    rule = json.loads(reads.get_bytes(ROOT / "build/task1_fingerprint_v1/shortlist_rule.json"))
    model = fp.Model.from_bytes(reads.get_bytes(ROOT / "build/task1_fingerprint_v1/model.json.gz", rule["model_sha256"]))
    frac = rule["shortlist_fraction"]
    fc = json.loads(reads.get_bytes(ROOT / FORECAST[0]))
    u21, r21 = fc["count_forecast"]["u2021"], fc["count_forecast"]["r2021"]
    count_fc = lambda s: (1 - u21) * r21 * s  # noqa: E731 - the pre-registered formula, frozen constants

    # FY2021 training-year reference (exposed, the build year): universe count and u2021 cross-check.
    seed21 = _load_fetch(t3.SEED_ROOT / "fy2021", reads)
    u = [r for r in seed21 if qu.in_universe(r)]
    ref21 = {"universe": len(u), "nitrd": sum(bool(r["cat329"]) for r in u),
             "u2021_recomputed": sum(not r["has_any_category"] and not r["cat329"] for r in u) / len(u),
             "u2021_frozen": u21, "label": "training year (exposed); reference only"}
    core_sets = {fy: {r["core_project_num"] for r in _load_fetch(t3.SEED_ROOT / f"fy{fy}", reads) if r.get("core_project_num")}
                 for fy in (2019, 2020)}
    core_sets[2021] = {r["core_project_num"] for r in seed21 if r.get("core_project_num")}
    del seed21, u

    years: dict[str, dict] = {}
    t3_root = Path(os.environ.get("UAC_NITRD_TASK1_TIER3_ROOT", "/Volumes/users/conroyri/nitrd_hackathon_v1_raw/task1_tier3_v1"))
    srcs = {2022: t3_root / "fy2022", 2023: t3_root / "fy2023", 2025: BT_ROOT / "fy2025"}
    labels = {2022: "exposed (labels read 2026-10-25)", 2023: "exposed (labels read 2026-10-25)",
              2025: "exposed (FY2025 NITRD awards read by Task 2, 2026-10); not blind"}
    for fy in (2022, 2023, 2025):
        rows = _load_fetch(srcs[fy], reads)
        core_sets[fy] = {r["core_project_num"] for r in rows if r.get("core_project_num")}
        if fy == 2025 and 2024 not in core_sets:
            core_sets[2024] = {r["core_project_num"] for r in csv.DictReader(io.StringIO(reads.get_bytes(ROOT / ID_2024).decode()))
                               if r["core_project_num"]}
        u = sorted((r for r in rows if qu.in_universe(r)), key=lambda r: r["appl_id"])
        n = len(u)
        appl = np.array([r["appl_id"] for r in u], dtype=np.int64)
        core = [r["core_project_num"] for r in u]
        nitrd = np.array([bool(r["cat329"]) for r in u])
        categorized = np.array([bool(r["has_any_category"]) for r in u]) | nitrd
        prior = core_sets[fy - 3] | core_sets[fy - 2] | core_sets[fy - 1]
        new = np.array([c not in prior for c in core])
        scores = model.score(model.transform([fp.text_of(r) for r in u]))
        o = fp.rank(scores, appl)
        rank = np.empty(n, dtype=np.int64)
        rank[o] = np.arange(1, n + 1)
        k = fp.shortlist_size(frac, n)
        m = rank <= k
        cx = rm.Cores(core)
        base = rm.BOOT_SEED + 50000 + fy
        years[str(fy)] = {
            "label": labels[fy], "blind": False, "universe": n, "k": k, "reported_nitrd": int(nitrd.sum()),
            "reported_uncategorized": int((~categorized).sum()), "new_core_awards": int(new.sum()),
            "all": rm.arm_vs_listing(m, nitrd, categorized, np.ones(n, bool), cx, base),
            "new_cores": rm.arm_vs_listing(m, nitrd, categorized, new, cx, base + 1),
            "curve": rm.curve(rank, nitrd, np.ones(n, bool), [0.05, 0.1, frac, 0.15, 0.2, 0.3]),
            "count_forecast": round(count_fc(float(scores.sum())), 1), "sum_scores": float(scores.sum())}
        print(f"FY{fy}: N {n} K {k} recall {years[str(fy)]['all']['recall']:.4f}", flush=True)

    # FY2024: committed one-shot report + committed ranking; no key read.
    rep = json.loads(reads.get_bytes(ROOT / SCORE_REPORT[0], SCORE_REPORT[1]))
    t2, t2x = rep["scopes"]["tier2"], rep["scopes"]["tier2x"]
    a2, a2x = t2["at_equal_burden"]["A"], t2x["at_equal_burden"]["A"]
    rk = gzip.decompress(reads.get_bytes(ROOT / RANK_2024[0], RANK_2024[1])).decode()
    s24 = sum(float(r["score"]) for r in csv.DictReader(io.StringIO(rk)))
    tp, ny = a2["tp"] + a2x["tp"], a2["nitrd"] + a2x["nitrd"]
    years["2024"] = {
        "label": "blind (Tier 2, non-File-A; sealed key opened once 2026-11-04T19:39:35Z)", "blind": True,
        "universe": rep["universe"], "k": rep["k"], "reported_nitrd": rep["universe_counts"]["nitrd"],
        "reported_uncategorized": rep["universe_counts"]["uncategorized"],
        "tier2_blind": {"recall": a2["recall"], "recall_ci95_core_bootstrap": a2["recall_ci95_core_bootstrap"],
                        "precision_primary": a2["precision_primary"], "nitrd": a2["nitrd"], "tp": a2["tp"]},
        "tier2_new_cores_blind": {k2: rep["scopes"]["tier2_new_cores"]["at_equal_burden"]["A"][k2]
                                  for k2 in ("recall", "recall_ci95_core_bootstrap", "nitrd", "tp")},
        "all_awards_mixed": {"recall": tp / ny, "tp": tp, "nitrd": ny,
                             "label": "pools blind Tier 2 with exposed Tier 2x (File A); comparable in scope to the other years"},
        "count_forecast": round(count_fc(s24), 1), "sum_scores": s24,
        "source": f"{SCORE_REPORT[0]} (sha {SCORE_REPORT[1][:8]}), {RANK_2024[0]} (sha {RANK_2024[1][:8]})"}
    for y in years.values():
        y["count_forecast_error"] = round(y["count_forecast"] - y["reported_nitrd"], 1)
        y["count_forecast_error_pct"] = round(100 * y["count_forecast_error"] / y["reported_nitrd"], 2)

    reported = {"2021": ref21["nitrd"], **{fy: years[fy]["reported_nitrd"] for fy in ("2022", "2023", "2024", "2025")}}
    xs = np.array([2022, 2023, 2024, 2025], float)
    ys = np.array([reported[str(int(x))] for x in xs], float)
    slope, icpt = np.polyfit(xs, ys, 1)
    fc26 = fc["count_forecast"]["value"]
    trend = {"reported_universe_nitrd": reported, "linear_trend_fy2022_2025": {"slope_per_year": round(float(slope), 1),
             "fy2026_extrapolated": round(float(slope * 2026 + icpt), 1)},
             "fy2026_count_forecast": fc26, "fy2026_universe": fc["universe"],
             "fy2026_forecast_vs_trend_pct": round(100 * (fc26 - (slope * 2026 + icpt)) / (slope * 2026 + icpt), 2),
             "reported_prevalence": {fy: round(c / (ref21["universe"] if fy == "2021" else years[fy]["universe"]), 5)
                                     for fy, c in reported.items()},
             "fy2026_forecast_prevalence": round(fc26 / fc["universe"], 5),
             "fy2026_reported": None, "note": "FY2026 reported count is not yet public (daily zero-count check); "
             "the forecast is scored against it at the Tier 1 reveal. Prevalence differs by universe size: "
             "FY2026 universe is a mid-year snapshot."}
    report = {"backtest_id": BACKTEST_ID, "metrics_id": rm.REVEAL_METRICS_ID, "fingerprint_id": rule["fingerprint_id"],
              "model_sha256": rule["model_sha256"], "shortlist_fraction": frac, "listing": "RePORTER spending category 329, per award",
              "universe_rule": qu.UNIVERSE_RULE_ID, "regime_note": REGIME_NOTE, "fy2021_reference": ref21,
              "years": dict(sorted(years.items())), "count_trend": trend, "benchmarks": rm.BENCHMARKS,
              "framing": "high-recall triage at ~12% review burden; kappa is context only"}
    OUT.mkdir(parents=True)
    (OUT / "report.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    _chart(report, OUT / "performance_vs_reported.png")
    (OUT / "READ_MANIFEST.json").write_text(json.dumps({"backtest_id": BACKTEST_ID, "reads": dict(sorted(reads.items())),
                                                       "sealed_volume_opened": False}, indent=1, sort_keys=True) + "\n")
    print("report sha256", _sha((OUT / "report.json").read_bytes()))
    return 0


def _chart(r: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    Y = r["years"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.6))
    for fy in ("2022", "2023", "2025"):
        v = Y[fy]["all"]
        lo, hi = v["recall_ci95_core_bootstrap"]
        a1.errorbar(int(fy), v["recall"], yerr=[[v["recall"] - lo], [hi - v["recall"]]], fmt="o", mfc="white", color="C0", capsize=3)
        n = Y[fy]["new_cores"]
        a1.plot(int(fy) + 0.08, n["recall"], "s", mfc="white", color="C1")
    b = Y["2024"]["tier2_blind"]
    lo, hi = b["recall_ci95_core_bootstrap"]
    a1.errorbar(2024, b["recall"], yerr=[[b["recall"] - lo], [hi - b["recall"]]], fmt="o", color="C0", capsize=3)
    a1.plot(2024.08, Y["2024"]["tier2_new_cores_blind"]["recall"], "s", color="C1")
    a1.plot(2023.92, Y["2024"]["all_awards_mixed"]["recall"], "D", mfc="white", color="C2")
    a1.axhline(0.90, ls="--", color="grey", lw=1)
    a1.text(2021.9, 0.903, "pre-registered criterion 0.90", fontsize=8, color="grey")
    a1.set_xticks([2022, 2023, 2024, 2025])
    a1.set_xlim(2021.7, 2025.4)
    a1.set_ylim(0.80, 1.0)
    a1.set_ylabel("recall at K (11.55% of universe reviewed)")
    a1.set_title("Arm A vs reported NITRD listing")
    from matplotlib.lines import Line2D
    a1.legend(handles=[Line2D([], [], marker="o", ls="", color="C0", label="all awards, blind (FY2024 Tier 2)"),
                       Line2D([], [], marker="o", ls="", mfc="white", color="C0", label="all awards, exposed"),
                       Line2D([], [], marker="s", ls="", color="C1", mfc="white", label="new cores (filled = blind)"),
                       Line2D([], [], marker="D", ls="", mfc="white", color="C2", label="FY2024 all awards (mixed)")],
              fontsize=7.5, loc="lower left")
    t = r["count_trend"]
    rep = t["reported_universe_nitrd"]
    a2.plot([int(k) for k in rep], list(rep.values()), "-o", color="k", label="reported (universe)")
    fys = [2022, 2023, 2024, 2025]
    a2.plot(fys, [Y[str(f)]["count_forecast"] for f in fys], "o", mfc="white", color="C3", label="count forecast (frozen FY2021 constants)")
    a2.plot(2026, t["fy2026_count_forecast"], "*", ms=13, color="C3", label="FY2026 forecast (prospective)")
    a2.plot(2026, t["linear_trend_fy2022_2025"]["fy2026_extrapolated"], "x", color="grey", label="FY2022-25 linear trend")
    a2.axvspan(2020.5, 2021.5, color="0.92")
    a2.text(2020.55, min(rep.values()) * 0.985, "training\nyear", fontsize=7.5)
    a2.set_xticks([2021, 2022, 2023, 2024, 2025, 2026])
    a2.set_ylabel("NITRD awards in universe")
    a2.set_title("Count forecast vs reported count")
    a2.legend(fontsize=7.5, loc="lower right")
    fig.text(0.5, 0.005, r["regime_note"], ha="center", fontsize=7.5, color="0.3")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, dpi=130, metadata={"Software": None})


if __name__ == "__main__":
    sys.exit(main())
