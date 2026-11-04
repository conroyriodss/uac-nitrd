"""Task 1 Tier 3: FY2022 / FY2023 out-of-time points (TIER3_ID = task1-tier3-v1). Not blind.

Pre-registration task1-prereg-v1-2026-11-04T18:00:50Z, section 1 (Tier 3: burned years, dev baselines and
descriptive decay-curve points only) and section 8 step 3. Evaluation code, NOT under the build guard: these
years' labels were exposed on 2026-10-25 (build/universe/fy2022.csv, fy2023.csv) and nothing here feeds
any model. The shipped fingerprint (arm A, task1-fingerprint-v1) is applied unchanged.

  fetch  FY2022 and FY2023 identity + title/abstract/PHR + SpendingCategories from RePORTER, reduced on
         receipt to has_any_category and cat329 (tools/fetch_task1_text.reduce_record); write-once to
         $UAC_NITRD_TASK1_TIER3_ROOT/fy<FY>/ with a FETCH_SUMMARY.
  score  per year: universe (task1-universe-qvr-recon-v1), arm A ranking at K = ceil(f x N), carry-forward
         from the prior year's pinned universe labels, A+CF; metrics from workflow/reveal_metrics.py for all
         awards and new cores (no NIH record in the three prior FYs). Writes build/task1_tier3_v1/ once.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TIER3_ID = "task1-tier3-v1"
YEARS = (2022, 2023)
URL = "https://api.reporter.nih.gov/v2/projects/search"
PAGE, WINDOW = 500, 14999
FIELDS = ["ApplId", "CoreProjectNum", "FiscalYear", "SubprojectId", "AgencyIcAdmin", "ActivityCode",
          "ProjectTitle", "AbstractText", "PhrText", "SpendingCategories"]
T3_ROOT = Path(os.environ.get("UAC_NITRD_TASK1_TIER3_ROOT", "/Volumes/users/conroyri/nitrd_hackathon_v1_raw/task1_tier3_v1"))
SEED_ROOT = Path(os.environ.get("UAC_NITRD_TASK1_SEED_ROOT", "/Volumes/users/conroyri/nitrd_hackathon_v1_raw/task1_seed_v1"))
OUT = ROOT / "build" / "task1_tier3_v1"
PRIOR_PINS = {2021: ("build/universe/fy2021.csv", "d7f7fadd03bb8cfce75ec0cf8329c232d8c3ffc89c73d4b58533baf743832abf"),
              2022: ("build/universe/fy2022.csv", "5126368e4971542e6b4d3ad0f1f027a7da3af52ea83e5a4d345022c7581a4079"),
              2023: ("build/universe/fy2023.csv", "d96da7b3cbb33d04eb81fa8272f3683348c7ab00acf276e40a1e2a41480338a3")}


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(fy: int) -> dict:
    import requests

    from tools.fetch_task1_text import PARTITION, reduce_record
    out = T3_ROOT / f"fy{fy}"
    if out.exists():
        raise SystemExit(f"{out} exists (write-once)")
    s, calls = requests.Session(), [0]

    def post(crit, off=0, lim=PAGE):
        body = {"criteria": crit, "include_fields": FIELDS, "offset": off, "limit": lim,
                "sort_field": "appl_id", "sort_order": "asc"}
        for a in range(8):
            try:
                r = s.post(URL, json=body, timeout=120)
                calls[0] += 1
                if r.status_code == 200:
                    return r.json()
            except requests.RequestException:
                pass
            time.sleep(3 * (a + 1))
        raise RuntimeError(f"request failed {crit} @ {off}")

    def pull(crit):
        n, got, off = post(crit, 0, 1)["meta"]["total"], {}, 0
        if n > WINDOW:
            raise RuntimeError(f"{crit}: {n} > window")
        while off < n:
            for x in post(crit, off)["results"]:
                got[int(x["appl_id"])] = x
            off += PAGE
            time.sleep(0.3)
        if len(got) != n:
            raise RuntimeError(f"{crit}: {len(got)} != {n}")
        return got

    t0 = _now()
    n_all = post({"fiscal_years": [fy], "agencies": ["NIH"]}, 0, 1)["meta"]["total"]
    recs: dict[int, dict] = {}
    for ic in PARTITION:
        crit = {"fiscal_years": [fy], "agencies": [ic]}
        n = post(crit, 0, 1)["meta"]["total"]
        if not n:
            continue
        if n <= WINDOW:
            recs.update(pull(crit))
        else:
            for t in "123456789":
                c2 = {**crit, "award_types": [t]}
                if post(c2, 0, 1)["meta"]["total"]:
                    recs.update(pull(c2))
    if len(recs) != n_all:
        raise RuntimeError(f"FY{fy}: pulled {len(recs)} != NIH total {n_all}")
    rows = [reduce_record(recs[k], fy, True) for k in sorted(recs)]
    raw = "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in rows).encode("utf-8")
    out.mkdir(parents=True)
    (out / f"fy{fy}.jsonl.gz").write_bytes(gzip.compress(raw, mtime=0))
    summ = {"tier3_id": TIER3_ID, "fy": fy, "fields": FIELDS, "pull_utc": {"start": t0, "end": _now()},
            "api_calls": calls[0], "records": len(rows), "nih_total": n_all, "file": f"fy{fy}.jsonl.gz",
            "sha256_gz": _sha((out / f"fy{fy}.jsonl.gz").read_bytes()), "labels": "has_any_category + cat329 (exposed year)"}
    (out / "FETCH_SUMMARY.json").write_text(json.dumps(summ, indent=1, sort_keys=True) + "\n")
    return summ


def _load(path: Path) -> list[dict]:
    return [json.loads(x) for x in gzip.decompress(path.read_bytes()).decode("utf-8").split("\n") if x]


def _cores(fy: int, reads: dict) -> set[str]:
    """Every core with an NIH record in FY (any record, not only the universe)."""
    if fy in (2019, 2020, 2021):
        summ = json.loads((SEED_ROOT / f"fy{fy}" / "FETCH_SUMMARY.json").read_text())
        p = SEED_ROOT / f"fy{fy}" / summ["file"]
    else:
        summ = json.loads((T3_ROOT / f"fy{fy}" / "FETCH_SUMMARY.json").read_text())
        p = T3_ROOT / f"fy{fy}" / summ["file"]
    b = p.read_bytes()
    if _sha(b) != summ["sha256_gz"]:
        raise RuntimeError(f"{p} does not match its FETCH_SUMMARY")
    reads[str(p)] = _sha(b)
    return {r["core_project_num"] for r in _load(p) if r.get("core_project_num")}


def score() -> int:
    import numpy as np

    from workflow import fingerprint as fp
    from workflow import model_comparison as mc
    from workflow import qvr_universe as qu
    from workflow import reveal_metrics as rm
    if OUT.exists():
        raise SystemExit(f"{OUT} exists (write-once)")
    reads: dict[str, str] = {}
    rule_raw = (ROOT / "build/task1_fingerprint_v1/shortlist_rule.json").read_bytes()
    rule = json.loads(rule_raw)
    blob = (ROOT / "build/task1_fingerprint_v1/model.json.gz").read_bytes()
    if _sha(blob) != rule["model_sha256"]:
        raise RuntimeError("arm A model mismatch")
    reads["build/task1_fingerprint_v1/model.json.gz"] = _sha(blob)
    reads["build/task1_fingerprint_v1/shortlist_rule.json"] = _sha(rule_raw)
    model = fp.Model.from_bytes(blob)
    report = {"tier3_id": TIER3_ID, "metrics_id": rm.REVEAL_METRICS_ID, "blind": False,
              "label": "Tier 3: burned years (labels exposed 2026-10-25); descriptive decay-curve points only",
              "fingerprint_id": rule["fingerprint_id"], "shortlist_fraction": rule["shortlist_fraction"],
              "benchmarks": rm.BENCHMARKS, "years": {}}
    for yi, fy in enumerate(YEARS):
        summ = json.loads((T3_ROOT / f"fy{fy}" / "FETCH_SUMMARY.json").read_text())
        p = T3_ROOT / f"fy{fy}" / summ["file"]
        b = p.read_bytes()
        if _sha(b) != summ["sha256_gz"]:
            raise RuntimeError(f"FY{fy} fetch mismatch")
        reads[str(p)] = _sha(b)
        u = sorted((r for r in _load(p) if qu.in_universe(r)), key=lambda r: r["appl_id"])
        n = len(u)
        appl = np.array([r["appl_id"] for r in u], dtype=np.int64)
        core = [r["core_project_num"] for r in u]
        ic = [r["admin_ic"] for r in u]
        nitrd = np.array([bool(r["cat329"]) for r in u])
        categorized = np.array([bool(r["has_any_category"]) for r in u]) | nitrd
        prior3 = set().union(*(_cores(y, reads) for y in (fy - 3, fy - 2, fy - 1)))
        new = np.array([c not in prior3 for c in core])
        scores = model.score(model.transform([fp.text_of(r) for r in u]))
        o = fp.rank(scores, appl)
        rank_a = np.empty(n, dtype=np.int64)
        rank_a[o] = np.arange(1, n + 1)
        k = fp.shortlist_size(rule["shortlist_fraction"], n)
        m_a = rank_a <= k
        ppath, psha = PRIOR_PINS[fy - 1]
        praw = (ROOT / ppath).read_bytes()
        if _sha(praw) != psha:
            raise RuntimeError(f"{ppath} pin mismatch")
        reads[ppath] = psha
        cf_cores = {r["core_project_num"] for r in csv.DictReader(io.StringIO(praw.decode())) if r["cat329"] == "1"}
        U = mc.Universe(appl=appl, core=core, ic=ic)
        cf = mc.carry_forward(U, cf_cores, fy - 1, fy)
        acf = mc.combined(mc.Arm("A", "ranked", score=-rank_a.astype(float)), cf, U)
        oc = mc.order(acf.score, appl)
        rank_acf = np.empty(n, dtype=np.int64)
        rank_acf[oc] = np.arange(1, n + 1)
        m_cf = cf.members.astype(bool)
        k_cf = int(m_cf.sum())
        cpath, csha = PRIOR_PINS[fy]
        craw = (ROOT / cpath).read_bytes()
        if _sha(craw) != csha:
            raise RuntimeError(f"{cpath} pin mismatch")
        reads[cpath] = csha
        pinned = {int(r["appl_id"]): r["cat329"] == "1" for r in csv.DictReader(io.StringIO(craw.decode()))}
        common = [i for i, x in enumerate(appl.tolist()) if x in pinned]
        agree = sum(pinned[int(appl[i])] == bool(nitrd[i]) for i in common)
        cores_ix = rm.Cores(core)
        Y = {"universe": n, "k": k, "k_cf": k_cf, "nitrd": int(nitrd.sum()), "uncategorized": int((~categorized).sum()),
             "new_core_awards": int(new.sum()), "cf_from": f"FY{fy - 1} NITRD cores ({ppath})",
             "labels_vs_pinned_universe_file": {"file": cpath, "common_awards": len(common), "cat329_agree": agree,
                                                 "universe_only_in_fetch": n - len(common)},
             "scopes": {}}
        for si, (sname, sc) in enumerate({"all": np.ones(n, bool), "new_cores": new}.items()):
            base = rm.BOOT_SEED + 10000 * (yi + 1) + 1000 * si
            Y["scopes"][sname] = {
                "at_equal_burden": {"A": rm.arm_vs_listing(m_a, nitrd, categorized, sc, cores_ix, base),
                                    "A+CF": rm.arm_vs_listing(rank_acf <= k, nitrd, categorized, sc, cores_ix, base + 10)},
                "cf_at_own_size": {"CF": rm.arm_vs_listing(m_cf, nitrd, categorized, sc, cores_ix, base + 20)},
                "ranked_at_k_cf": {"A": rm.arm_vs_listing(rank_a <= k_cf, nitrd, categorized, sc, cores_ix, base + 30)},
                "curve_A": rm.curve(rank_a, nitrd, sc, list(mc.CURVE)),
                "kappa_A_CF": rm.pairwise_kappa({"A": m_a, "CF": m_cf}, sc, cores_ix, base + 900)}
        report["years"][str(fy)] = Y
        print(f"FY{fy}: N {n} K {k} recall A {Y['scopes']['all']['at_equal_burden']['A']['recall']:.4f}", flush=True)
    OUT.mkdir(parents=True)
    (OUT / "report.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    (OUT / "READ_MANIFEST.json").write_text(json.dumps({"tier3_id": TIER3_ID, "reads": dict(sorted(reads.items()))},
                                                       indent=1, sort_keys=True) + "\n")
    print("report sha256", _sha((OUT / "report.json").read_bytes()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("fetch", "score"))
    a = ap.parse_args(argv)
    if a.cmd == "fetch":
        for fy in YEARS:
            if (T3_ROOT / f"fy{fy}" / "FETCH_SUMMARY.json").exists():
                print(f"FY{fy} already fetched")
                continue
            s = fetch(fy)
            print(json.dumps({k: s[k] for k in ("fy", "records", "nih_total", "api_calls", "pull_utc", "sha256_gz")}))
        return 0
    return score()


if __name__ == "__main__":
    sys.exit(main())
