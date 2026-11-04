"""Task 1 Tier 2 / 2x scoring run, FY2024 (SCORE_ID = task1-fy2024-score-v1). Runs ONCE.

Pre-registration task1-prereg-v1-2026-11-04T18:00:50Z, section 8 step 2: open the FY2024 key and the sealed
has_any_category supplement under UAC_NITRD_TASK1_SCORE_RUN=1 and score once. No re-fit, no iteration.

Inputs (each SHA-256 checked before the key is opened):
  build/task1_fy2024_ranking_v1/ranking.csv.gz       arm A, freeze run (primary)
  build/task1_fy2024_armb_ranking_v1/ranking.csv.gz  arm B, written before the key was opened
  build/universe/fy2023.csv                         FY2023 labels for carry-forward (exposed, labelled)
  docs/TASK1_PREREGISTRATION.md                     the frozen pre-registration
  <sealed dir>/key.csv, has_any_category.csv         via workflow/sealed.open_sealed_key (path given on
                                                    the command line; it never appears in the repo)
Arms: A, B (ranked, K = arm A's K on the whole universe), CF (set, FY2023 NITRD cores -> FY2024), A+CF
(workflow/model_comparison.combined, cut at K_A). Arm C is FY2021-only in v1 and is not scored here.
Scopes: Tier 2 = filea_exposed 0 (blind), Tier 2x = filea_exposed 1 (exposed; its recall is the AI-flag
recall), each also for new cores (stratum new). Metrics: workflow/reveal_metrics.py.

Outputs (write-once) build/task1_fy2024_score_v1/: report.json, under_capture_tier2.csv (uncategorized
awards on arm A's shortlist, with scores), disagreement_tier2.csv.gz (appl_id, membership pattern; no
label), READ_MANIFEST.json. Aggregates only: no per-award label leaves the run.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SCORE_ID = "task1-fy2024-score-v1"
PREREG_ID = "task1-prereg-v1-2026-11-04T18:00:50Z"
OUT = ROOT / "build" / "task1_fy2024_score_v1"
PINS = {
    "build/task1_fy2024_ranking_v1/ranking.csv.gz": "e49e844d1ebf43691cf3d66ef70f7c415d7dd50f1deccac845709cd656ffa8dd",
    "build/task1_fy2024_armb_ranking_v1/ranking.csv.gz": "5d8e213537f9938b4658245ae58ff97d66a1de7f4ecbe1ed812945246534b45b",
    "build/universe/fy2023.csv": "d96da7b3cbb33d04eb81fa8272f3683348c7ab00acf276e40a1e2a41480338a3",
    "docs/TASK1_PREREGISTRATION.md": "c770a502777725545f9cff5130e329fe83bb003c39f3c11f61beb0e0259a0280",
}
KEY_SHA = "81350a5328ceb485eb41c7095765c3a7f2d5f8f648cc7b2159610b8bf52efc02"
SUPP_SHA = "5639acfaa2246953c853549b9e87cf8ccb72756480346b271fc2a31580493f5f"
CRITERION = 0.90


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _ranking(raw: bytes) -> dict[int, dict]:
    return {int(r["appl_id"]): r for r in csv.DictReader(io.StringIO(gzip.decompress(raw).decode("utf-8")))}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sealed-dir", help="directory holding key.csv and has_any_category.csv")
    ap.add_argument("--synthetic-out", help="rehearsal: random synthetic labels, no sealed read, write here")
    a = ap.parse_args(argv)
    global OUT
    if a.synthetic_out:
        OUT = Path(a.synthetic_out)
    elif not a.sealed_dir:
        raise SystemExit("--sealed-dir is required for the scoring run")
    if OUT.exists():
        raise SystemExit(f"{OUT} exists; FY2024 is scored once")
    dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", "tools", "workflow", "build", "docs"],
                           capture_output=True, text=True, check=True).stdout.strip()
    if dirty and not a.synthetic_out:
        raise SystemExit(f"tree not clean:\n{dirty}")
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    raw = {}
    for rel, want in PINS.items():
        raw[rel] = (ROOT / rel).read_bytes()
        if _sha(raw[rel]) != want:
            raise SystemExit(f"{rel} does not match its pin")

    import numpy as np

    from workflow import model_comparison as mc
    from workflow import reveal_metrics as rm
    from workflow import sealed

    A = _ranking(raw["build/task1_fy2024_ranking_v1/ranking.csv.gz"])
    B = _ranking(raw["build/task1_fy2024_armb_ranking_v1/ranking.csv.gz"])
    if set(A) != set(B):
        raise SystemExit("arm A and arm B rank different universes")
    appl = np.array(sorted(A), dtype=np.int64)
    n = len(appl)
    core = [A[x]["core_project_num"] for x in appl.tolist()]
    ic = [A[x]["admin_ic"] for x in appl.tolist()]
    rank_a = np.array([int(A[x]["rank"]) for x in appl.tolist()])
    rank_b = np.array([int(B[x]["rank"]) for x in appl.tolist()])
    k = rm.shortlist_size(mc.PRIMARY_FRACTION, n)
    m_a, m_b = rank_a <= k, rank_b <= k
    if not (m_a == np.array([A[x]["on_shortlist"] == "1" for x in appl.tolist()])).all() or \
       not (m_b == np.array([B[x]["on_shortlist"] == "1" for x in appl.tolist()])).all():
        raise SystemExit("recomputed shortlists differ from the committed on_shortlist columns")

    prior = list(csv.DictReader(io.StringIO(raw["build/universe/fy2023.csv"].decode("utf-8"))))
    cf_cores = {r["core_project_num"] for r in prior if r["cat329"] == "1" and r["core_project_num"]}
    u = mc.Universe(appl=appl, core=core, ic=ic)
    cf = mc.carry_forward(u, cf_cores, 2023, 2024)
    arm_a = mc.Arm("A", "ranked", score=-rank_a.astype(float))  # rank order = the committed ranking
    acf = mc.combined(arm_a, cf, u)
    order_acf = mc.order(acf.score, appl)
    rank_acf = np.empty(n, dtype=np.int64)
    rank_acf[order_acf] = np.arange(1, n + 1)
    m_cf, m_acf = cf.members.astype(bool), rank_acf <= k
    k_cf = int(m_cf.sum())

    # ---- the key: opened here, once ----
    if a.synthetic_out:  # rehearsal only: labels are random, nothing sealed is touched
        g = np.random.default_rng(0)
        kb, sb = io.StringIO(), io.StringIO()
        kb.write("appl_id,core_project_num,cat329,stratum,filea_exposed,record_sha256\n")
        sb.write("appl_id,has_any_category\n")
        for x, c, r in zip(appl.tolist(), core, rank_a.tolist()):
            y = int(g.random() < (0.35 if r <= k else 0.005))
            kb.write(f"{x},{c},{y},{'new' if g.random() < 0.25 else 'continuing'},{int(g.random() < 0.04)},x\n")
            sb.write(f"{x},{int(y or g.random() < 0.92)}\n")
        key_txt, supp_txt = kb.getvalue(), sb.getvalue()
        opened_utc = "SYNTHETIC"
    else:
        sd = Path(a.sealed_dir)
        key_txt = sealed.open_sealed_key(sd / "key.csv")
        supp_txt = sealed.open_sealed_key(sd / "has_any_category.csv")
        opened_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        if _sha(key_txt.encode("utf-8")) != KEY_SHA or _sha(supp_txt.encode("utf-8")) != SUPP_SHA:
            raise SystemExit("sealed key or supplement does not match its sealed hash")
    key = {int(r["appl_id"]): r for r in csv.DictReader(io.StringIO(key_txt))}
    supp = {int(r["appl_id"]): r["has_any_category"] for r in csv.DictReader(io.StringIO(supp_txt))}
    if not a.synthetic_out:
        bad = sum(_sha(",".join(r[c] for c in ("appl_id", "core_project_num", "cat329", "stratum", "filea_exposed"))
                       .encode()) != r["record_sha256"] for r in key.values())
        if bad:
            raise SystemExit(f"{bad} key records fail their per-record sha256")
    missing = [x for x in appl.tolist() if x not in key or x not in supp]
    if missing:
        raise SystemExit(f"{len(missing)} universe awards missing from the key or supplement")
    core_mismatch = sum(key[x]["core_project_num"] != c for x, c in zip(appl.tolist(), core))
    nitrd = np.array([key[x]["cat329"] == "1" for x in appl.tolist()])
    has_any = np.array([supp[x] == "1" for x in appl.tolist()])
    categorized = nitrd | has_any                         # rule R1; R2: cat329=1 is authoritative
    r2 = int((nitrd & ~has_any).sum())
    new = np.array([key[x]["stratum"] == "new" for x in appl.tolist()])
    filea = np.array([key[x]["filea_exposed"] == "1" for x in appl.tolist()])
    del key, supp, key_txt, supp_txt

    cores = rm.Cores(core)
    scopes = {"tier2": ~filea, "tier2_new_cores": ~filea & new, "tier2x": filea, "tier2x_new_cores": filea & new}
    members = {"A": m_a, "B": m_b, "CF": m_cf, "A+CF": m_acf}
    ranks = {"A": rank_a, "B": rank_b, "A+CF": rank_acf}
    fr_cf = k_cf / n
    report = {
        "score_id": SCORE_ID, "preregistration": PREREG_ID, "metrics_id": rm.REVEAL_METRICS_ID,
        "key_opened_utc": opened_utc, "repo_head": head, "universe": n, "k": k,
        "shortlist_fraction": mc.PRIMARY_FRACTION, "review_burden_k_over_n": k / n,
        "k_cf": k_cf, "k_cf_over_n": fr_cf,
        "label_rules": {"R1": "NITRD if key cat329=1; else not-NITRD if has_any_category=1; else uncategorized",
                        "R2_cat329_with_supplement_not_1": r2},
        "universe_counts": {"nitrd": int(nitrd.sum()), "uncategorized": int((~categorized).sum()),
                            "filea_exposed": int(filea.sum()), "new_core_awards": int(new.sum())},
        "key_core_mismatch": core_mismatch,
        "arms": {"A": "task1-fingerprint-v1 (primary, shipped)", "B": "task1-fingerprint-embed-v1 (comparison)",
                 "CF": mc.CF_LABEL + ": FY2023 NITRD cores -> FY2024",
                 "A+CF": "carry-forward picks first (by arm A's rank), then arm A; cut at K_A; " + mc.CF_LABEL,
                 "C": "FY2021-only in v1; not scored on FY2024"},
        "benchmarks": rm.BENCHMARKS, "scopes": {},
    }
    for si, (sname, sc) in enumerate(scopes.items()):
        S = {"n": int(sc.sum()), "at_equal_burden": {}, "ranked_arms_at_k_cf": {}, "curves": {}}
        for ai, (an, m) in enumerate(members.items()):
            S["at_equal_burden" if an != "CF" else "cf_at_own_size"] = S.get("at_equal_burden" if an != "CF" else "cf_at_own_size", {})
            S["at_equal_burden" if an != "CF" else "cf_at_own_size"][an] = rm.arm_vs_listing(
                m, nitrd, categorized, sc, cores, seed=rm.BOOT_SEED + 1000 * si + 10 * ai)
        for ai, (an, r) in enumerate(ranks.items()):
            S["ranked_arms_at_k_cf"][an] = rm.arm_vs_listing(
                r <= k_cf, nitrd, categorized, sc, cores, seed=rm.BOOT_SEED + 1000 * si + 500 + 10 * ai)
            S["curves"][an] = rm.curve(r, nitrd, sc, list(mc.CURVE))
        S["kappa_matrix_A_B_CF"] = rm.pairwise_kappa({"A": m_a, "B": m_b, "CF": m_cf}, sc, cores,
                                                     seed=rm.BOOT_SEED + 1000 * si + 900)
        S["core_level_secondary_A"] = rm.core_level(m_a, nitrd, categorized, sc, core)
        report["scopes"][sname] = S
    report["core_level_secondary_A_all_cores"] = rm.core_level(m_a, nitrd, categorized, np.ones(n, bool), core)
    dis, pattern = rm.disagreement({"A": m_a, "B": m_b, "CF": m_cf}, scopes["tier2"], nitrd, categorized, new, ic)
    report["disagreement_tier2_A_B_CF"] = dis
    t2 = report["scopes"]["tier2"]["at_equal_burden"]["A"]
    report["criterion"] = {"rule": "arm A, Tier 2, recall at K >= 0.90 (primary)", "recall": t2["recall"],
                           "threshold": CRITERION, "result": "PASS" if t2["recall"] >= CRITERION else "FAIL"}

    OUT.mkdir(parents=True)
    uc = io.StringIO()
    w = csv.writer(uc, lineterminator="\n")
    w.writerow(["appl_id", "core_project_num", "admin_ic", "rank", "score"])
    sel = m_a & ~categorized & scopes["tier2"]
    for i in sorted(np.flatnonzero(sel), key=lambda i: rank_a[i]):
        x = int(appl[i])
        w.writerow([x, core[i], ic[i], int(rank_a[i]), A[x]["score"]])
    (OUT / "under_capture_tier2.csv").write_bytes(uc.getvalue().encode("utf-8"))
    dg = io.StringIO()
    w = csv.writer(dg, lineterminator="\n")
    w.writerow(["appl_id", "pattern"])
    dmask = scopes["tier2"] & np.stack([m_a, m_b, m_cf]).any(0) & ~np.stack([m_a, m_b, m_cf]).all(0)
    for i in np.flatnonzero(dmask):
        w.writerow([int(appl[i]), pattern[i]])
    (OUT / "disagreement_tier2.csv.gz").write_bytes(gzip.compress(dg.getvalue().encode("utf-8"), mtime=0))
    report["outputs"] = {p.name: _sha(p.read_bytes()) for p in sorted(OUT.iterdir())}
    (OUT / "report.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    reads = {rel: _sha(b) for rel, b in raw.items()}
    reads.update({"<sealed>/key.csv": KEY_SHA, "<sealed>/has_any_category.csv": SUPP_SHA})
    (OUT / "READ_MANIFEST.json").write_text(json.dumps({"score_id": SCORE_ID, "repo_head": head, "reads": reads,
                                                        "key_opened_utc": opened_utc}, indent=1, sort_keys=True) + "\n")
    h = report["scopes"]
    print(json.dumps({"criterion": report["criterion"], "k": k, "k_cf": k_cf, "r2": r2,
                      "tier2_A": {x: h["tier2"]["at_equal_burden"]["A"][x] for x in ("recall", "recall_ci95_core_bootstrap", "precision_primary", "kappa_primary", "kappa_primary_ci95")},
                      "report_sha256": _sha((OUT / "report.json").read_bytes())}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
