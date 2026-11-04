"""Task 1 arm C (CLASSIFIER_ID = task1-llm-v1): zero-shot LLM scoring, under the read guard, mode "build".

SECONDARY arm (pre-registration section 6a). If it cannot be completed cleanly before the freeze it is
declared a v2 pre-registration arm instead; the freeze does not move for it.

Pinned: provider + endpoint + served model version (PIN; every response's `model` field must equal
PIN["served_model_version"], else the run stops), temperature 0, max_tokens 16 (PARAMS), and the exact
prompt file (PROMPT_FILE, SHA-256 PROMPT_SHA256, committed in 2d76541 before any scoring). The prompt
holds only the public FY2026 NITRD PCA definitions and NITRD's AI cross-PCA guidance, verbatim from
https://www.nitrd.gov/program-component-areas/nitrd-pcas-2026/ (scope/nitrd_pca_scopes_fy2026.v1.json,
checked string-for-string at start), plus the award's title, abstract and PHR. Never a label, a
spending category, or any prior-year membership; zero-shot, so no examples either.

Scored set: a declared stratified sample of the FY2021 universe (DESIGN; full-universe scoring x 3 runs
is about 190k calls / 380M tokens, not justified for a secondary arm). Strata use FY2021 labels
(allowed in build mode) only to draw the sample and weight the estimates; the model never sees them.
Estimates are inverse-probability weighted (w = N_h / n_h), with stratified-bootstrap 95% CIs.

Three runs over the same sample, same prompt, same parameters. Run 1 is the arm-C result; runs 2-3
exist to measure run-to-run variance at temperature 0 (per-award score agreement, metric spread,
shortlist flips). That variance is reported as evidence for shipping the deterministic arm A.

Outputs (write-once) in build/task1_llm_v1/: prompt.txt (exact copy), scores.csv.gz (per award: appl_id,
core, stratum, weight, score per run), summary.json (pins, prompt hash, design, metrics per run with
CIs, the three-run variance), READ_MANIFEST.json. Per-run checkpoints (resumable) go to SCRATCH.

Smoke mode (UAC_NITRD_TASK1_LLM_SMOKE=n per stratum): writes to UAC_NITRD_TASK1_LLM_OUT (required).
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow import build_guard as bg  # noqa: E402

CLASSIFIER_ID = "task1-llm-v1"
PIN = {
    "provider": "Meta Llama 4 Maverick (open weights), served by Databricks Foundation Model APIs",
    "endpoint": "databricks-llama-4-maverick",
    "foundation_model": "system.ai.llama-4-maverick",
    "served_model_version": "meta-llama-4-maverick-040225",
}
#: Pin history, disclosed: databricks-meta-llama-3-3-70b-instruct (meta-llama-3.3-70b-instruct-121024) was
#: pinned first; this workspace's QPS limit on it held throughput near 0.15 awards/s (about 25 h for 3 runs),
#: so it was replaced on 2026-11-04 ~02:20Z before any run finished. Its partial checkpoint (88 awards of
#: run 1) was set aside unread and is not part of any result.
PIN_HISTORY = [{"endpoint": "databricks-meta-llama-3-3-70b-instruct",
                "served_model_version": "meta-llama-3.3-70b-instruct-121024",
                "replaced": "workspace QPS limit; no run completed; partial scores set aside unread"}]
PARAMS = {"temperature": 0, "max_tokens": 16}
PROMPT_FILE = ROOT / "prompts" / "task1_llm_v1.prompt.txt"
PROMPT_SHA256 = "3aea5422f8094a86f50bd9f063df509f70777a58b859df83fac7f8a33667328c"
PROMPT_COMMIT = "2d76541"
SCOPE_FILE = ROOT / "scope" / "nitrd_pca_scopes_fy2026.v1.json"
SCOPE_SHA256 = "29ad15b320b363227dbe5ab590351578cffefe7ab171cb3a364d55f4803b8c79"
SOURCE_URL = "https://www.nitrd.gov/program-component-areas/nitrd-pcas-2026/"
LABEL_FY = 2021
RUNS = 3
WORKERS = int(os.environ.get("UAC_NITRD_TASK1_LLM_WORKERS", "6"))
DESIGN = {"nitrd": 1000, "categorized_not_nitrd": 3000, "uncategorized": 500}
SAMPLE_SEED, BOOT, BOOT_SEED = 20261104, 2000, 20261103
PRIMARY_FRACTION = 0.11548340045026477  # arm A's operating fraction (equal burden, rule 3)
TARGET_RECALL = 0.95
CURVE = tuple(round(0.01 * i, 2) for i in range(1, 31)) + (PRIMARY_FRACTION,)
SMOKE = int(os.environ.get("UAC_NITRD_TASK1_LLM_SMOKE", "0") or 0)
CANONICAL_OUT = ROOT / "build" / "task1_llm_v1"
OUT = Path(os.environ.get("UAC_NITRD_TASK1_LLM_OUT", CANONICAL_OUT))
# On the volume, so a recycled compute session can resume (see run_scores).
SCRATCH = Path(os.environ.get("UAC_NITRD_TASK1_LLM_SCRATCH",
                              "/Volumes/users/conroyri/nitrd_hackathon_v1_raw/_progress/task1_llm_v1_maverick"))
SCORE_RE = re.compile(r'"score"\s*:\s*(-?\d+)')


def log(msg: str) -> None:
    print(f"{datetime.now(UTC).strftime('%H:%M:%S')} {msg}", flush=True)


def load_year(guard: bg.Guard, fy: int) -> list[dict]:
    d = bg.SEED_ROOT / f"fy{fy}"
    summary = json.loads(guard.read_bytes(d / "FETCH_SUMMARY.json"))
    raw = guard.read_bytes(d / summary["file"])
    if hashlib.sha256(raw).hexdigest() != summary["sha256_gz"]:
        raise RuntimeError(f"FY{fy}: seed file sha256 differs from its FETCH_SUMMARY")
    rows = [json.loads(line) for line in gzip.decompress(raw).decode("utf-8").split("\n") if line]
    if len(rows) != summary["records"] or any(r["fy"] != fy for r in rows):
        raise RuntimeError(f"FY{fy}: record count or FY mismatch")
    return rows


def load_prompt(guard: bg.Guard) -> str:
    raw = guard.read_bytes(PROMPT_FILE)
    if hashlib.sha256(raw).hexdigest() != PROMPT_SHA256:
        raise RuntimeError("prompt file differs from the committed PROMPT_SHA256")
    scope_raw = guard.read_bytes(SCOPE_FILE)
    if hashlib.sha256(scope_raw).hexdigest() != SCOPE_SHA256:
        raise RuntimeError("scope file differs from SCOPE_SHA256")
    p, scope = raw.decode("utf-8"), json.loads(scope_raw)
    if scope["source"]["url"] != SOURCE_URL or scope["fiscal_year"] != 2026:
        raise RuntimeError("scope file is not the FY2026 nitrd.gov definitions")
    g = scope["cross_pca_guidance"]
    verbatim = [s["scope_text"] for s in scope["scopes"]] + [g["ai_definition"]["text"], g["ai_cross_pca"]["text"],
                                                           *g["ai_cross_pca"]["items"]]
    missing = [t[:50] for t in verbatim if t not in p]
    if missing:
        raise RuntimeError(f"prompt is missing verbatim definitions: {missing}")
    if any(p.count(t) != 1 for t in ("<<TITLE>>", "<<ABSTRACT>>", "<<PHR>>")):
        raise RuntimeError("prompt placeholders are not exactly <<TITLE>>, <<ABSTRACT>>, <<PHR>> once each")
    return p


def render(template: str, rec: dict) -> str:
    """The only award fields that reach the model: title, abstract, PHR."""
    return (template.replace("<<TITLE>>", rec.get("title") or "")
            .replace("<<ABSTRACT>>", rec.get("abstract") or "")
            .replace("<<PHR>>", rec.get("phr") or ""))


def parse(content: str) -> int | None:
    m = SCORE_RE.search(content or "")
    if not m:
        return None
    v = int(m.group(1))
    return v if 0 <= v <= 100 else None


class Scorer:
    def __init__(self) -> None:
        from databricks.sdk import WorkspaceClient

        self.client = WorkspaceClient()
        self.path = f"/serving-endpoints/{PIN['endpoint']}/invocations"
        self.tokens = {"prompt": 0, "completion": 0}
        self.retries = 0

    def __call__(self, prompt: str) -> dict:
        body = {"messages": [{"role": "user", "content": prompt}], **PARAMS}
        for attempt in range(8):
            try:
                r = self.client.api_client.do("POST", self.path, body=body)
                break
            except Exception as e:  # transient (429 / 5xx); retried, then the run stops
                self.retries += 1
                if attempt == 7:
                    raise
                log(f"retry {attempt + 1}: {type(e).__name__}: {str(e)[:120]}")
                time.sleep(min(60, 2 ** attempt))
        if r.get("model") != PIN["served_model_version"]:
            raise RuntimeError(f"endpoint served {r.get('model')!r}, pinned {PIN['served_model_version']!r}")
        content = r["choices"][0]["message"]["content"]
        u = r.get("usage") or {}
        self.tokens["prompt"] += int(u.get("prompt_tokens", 0))
        self.tokens["completion"] += int(u.get("completion_tokens", 0))
        return {"score": parse(content), "content": content[:200], "model": r["model"]}


def run_scores(run: int, sample: list[dict], template: str, scorer: Scorer) -> dict[int, dict]:
    """Score every sampled award once for this run, resuming from the run's checkpoint."""
    from concurrent.futures import as_completed

    # Durable checkpoint: one closed part file per flush (survives a recycled compute session; the
    # volume FUSE mount shows a file only once it is closed, so nothing is appended in place).
    ckdir = SCRATCH / f"run{run}{'_smoke' if SMOKE else ''}"
    ckdir.mkdir(parents=True, exist_ok=True)
    done: dict[int, dict] = {}
    for part in sorted(ckdir.glob("part-*.jsonl")):
        for line in part.read_text().splitlines():
            d = json.loads(line)
            if d.get("model") != PIN["served_model_version"]:
                raise RuntimeError(f"checkpoint {part} holds a different model version ({d.get('model')!r})")
            done[d["appl_id"]] = d
    todo = [r for r in sample if r["appl_id"] not in done]
    log(f"run {run}: {len(done)} from checkpoint, {len(todo)} to score")
    t0, last, pending = time.time(), time.time(), []

    def flush() -> None:
        if pending:
            name = f"part-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}.jsonl"
            (ckdir / name).write_text("".join(json.dumps(d) + "\n" for d in pending))
            pending.clear()

    with ThreadPoolExecutor(WORKERS) as pool:
        futs = {pool.submit(scorer, render(template, r)): r for r in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            rec, res = futs[fut], fut.result()
            d = {"appl_id": rec["appl_id"], **res}
            done[rec["appl_id"]] = d
            pending.append(d)
            now = time.time()
            if now - last > 60 or i == len(todo):
                flush()
                last = now
                rate = i / max(now - t0, 1e-9)
                log(f"run {run}: {i}/{len(todo)} {rate:.2f}/s ETA {round((len(todo) - i) / rate)}s "
                    f"(retries so far {scorer.retries})")
                (SCRATCH / "_progress.json").write_text(json.dumps(
                    {"run": run, "done": i, "total": len(todo), "rate": round(rate, 2),
                     "updated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}) + "\n")
    return done


# --- weighted estimators (scores are integers with many ties: tie blocks enter fractionally) ---------
def _blocks(score, w, y, cat):
    import numpy as np

    s = np.where(np.isnan(score), -1.0, score)
    levels = np.unique(s)[::-1]
    W = np.array([w[s == v].sum() for v in levels])
    Wn = np.array([w[(s == v) & y].sum() for v in levels])
    Wc = np.array([w[(s == v) & cat].sum() for v in levels])
    return levels, W, Wn, Wc


def at_fraction(blocks, f: float, N: float, Nn: float) -> dict:
    import numpy as np

    levels, W, Wn, Wc = blocks
    cum = np.concatenate([[0.0], np.cumsum(W)])
    j = int(np.searchsorted(cum[1:], f * N - 1e-9))  # block where the cut falls
    j = min(j, len(W) - 1)
    lam = (f * N - cum[j]) / W[j] if W[j] else 0.0
    tp = Wn[:j].sum() + lam * Wn[j]
    catm = Wc[:j].sum() + lam * Wc[j]
    return {"fraction": f, "recall": float(tp / Nn), "precision": float(tp / catm) if catm else None,
            "cut_score": float(levels[j]), "tie_share_included": float(lam)}


def fraction_for_recall(blocks, target: float, N: float, Nn: float) -> float:
    import numpy as np

    _levels, W, Wn, _ = blocks
    cumn = np.concatenate([[0.0], np.cumsum(Wn)])
    cum = np.concatenate([[0.0], np.cumsum(W)])
    j = int(np.searchsorted(cumn[1:], target * Nn - 1e-9))
    j = min(j, len(W) - 1)
    lam = (target * Nn - cumn[j]) / Wn[j] if Wn[j] else 0.0
    return float((cum[j] + lam * W[j]) / N)


def metrics(score, w, y, cat, N, Nn) -> dict:
    import numpy as np
    from sklearn.metrics import average_precision_score

    b = _blocks(score, w, y, cat)
    s = np.where(np.isnan(score), -1.0, score)
    return {"ap_categorized_weighted": float(average_precision_score(y[cat], s[cat], sample_weight=w[cat])),
            "recall_at_primary_fraction": at_fraction(b, PRIMARY_FRACTION, N, Nn)["recall"],
            "own_fraction_at_recall_0.95": fraction_for_recall(b, TARGET_RECALL, N, Nn)}


def main() -> int:
    if SMOKE and OUT == CANONICAL_OUT:
        raise SystemExit("smoke mode needs UAC_NITRD_TASK1_LLM_OUT (never the canonical directory)")
    if OUT.exists():
        raise SystemExit(f"{OUT} exists; arm C is built once")
    guard = bg.Guard("build", roots=(bg.SEED_ROOT, PROMPT_FILE.parent, SCOPE_FILE.parent)).install()
    import numpy as np

    from workflow import qvr_universe as qu

    template = load_prompt(guard)
    rows = load_year(guard, LABEL_FY)
    u = [r for r in rows if qu.in_universe(r)]
    del rows
    strata = {"nitrd": [], "categorized_not_nitrd": [], "uncategorized": []}
    for r in u:
        k = "uncategorized" if not r["has_any_category"] else ("nitrd" if r["cat329"] else "categorized_not_nitrd")
        strata[k].append(r)
    design = {k: (min(SMOKE, v) if SMOKE else v) for k, v in DESIGN.items()}
    rng = np.random.default_rng(SAMPLE_SEED)
    sample, info = [], {}
    for k in ("nitrd", "categorized_not_nitrd", "uncategorized"):
        pop = sorted(strata[k], key=lambda r: r["appl_id"])
        idx = np.sort(rng.choice(len(pop), size=design[k], replace=False))
        for i in idx:
            sample.append({**pop[i], "_stratum": k, "_w": len(pop) / design[k]})
        info[k] = {"population": len(pop), "sampled": int(design[k]), "weight": len(pop) / design[k]}
    N, Nn = float(len(u)), float(len(strata["nitrd"]))
    log(f"universe {len(u)}; sample {len(sample)} {info}")

    scorer = Scorer()
    t0 = time.time()
    runs = [run_scores(r, sample, template, scorer) for r in range(1, RUNS + 1)]
    models_seen = sorted({d["model"] for run in runs for d in run.values()})

    appl = np.array([r["appl_id"] for r in sample], dtype=np.int64)
    w = np.array([r["_w"] for r in sample])
    y = np.array([r["_stratum"] == "nitrd" for r in sample])
    cat = np.array([r["_stratum"] != "uncategorized" for r in sample])
    strat = np.array([r["_stratum"] for r in sample])
    S = np.array([[np.nan if run[a]["score"] is None else run[a]["score"] for a in appl] for run in runs])

    boot_rng = np.random.default_rng(BOOT_SEED)
    groups = [np.flatnonzero(strat == k) for k in ("nitrd", "categorized_not_nitrd", "uncategorized")]
    boot_idx = [np.concatenate([g[boot_rng.integers(0, len(g), len(g))] for g in groups]) for _ in range(BOOT)]

    per_run = []
    for r in range(RUNS):
        m = metrics(S[r], w, y, cat, N, Nn)
        bs = [metrics(S[r][b], w[b], y[b], cat[b], N, Nn) for b in boot_idx]
        ci = {k: [float(np.percentile([x[k] for x in bs], 2.5)), float(np.percentile([x[k] for x in bs], 97.5))]
              for k in m}
        blocks = _blocks(S[r], w, y, cat)
        per_run.append({"run": r + 1, **m, "ci95": ci, "parse_failures": int(np.isnan(S[r]).sum()),
                        "curve": [at_fraction(blocks, f, N, Nn) for f in CURVE],
                        "score_distribution": {str(int(v)): int((S[r] == v).sum())
                                               for v in np.unique(S[r][~np.isnan(S[r])])}})
        log(f"run {r + 1}: AP {m['ap_categorized_weighted']:.4f}, recall@11.55% "
            f"{m['recall_at_primary_fraction']:.4f}, own f {m['own_fraction_at_recall_0.95']:.4f}")

    def flips(a: int, b: int) -> int:
        ca = at_fraction(_blocks(S[a], w, y, cat), PRIMARY_FRACTION, N, Nn)["cut_score"]
        cb = at_fraction(_blocks(S[b], w, y, cat), PRIMARY_FRACTION, N, Nn)["cut_score"]
        return int(((np.nan_to_num(S[a], nan=-1) >= ca) != (np.nan_to_num(S[b], nan=-1) >= cb)).sum())

    valid = ~np.isnan(S).any(axis=0)
    rng_ = np.where(valid, np.nanmax(S, 0) - np.nanmin(S, 0), np.nan)
    pairs = [(0, 1), (0, 2), (1, 2)]
    variance = {
        "awards": len(sample), "awards_scored_in_all_runs": int(valid.sum()),
        "identical_in_all_runs": int((rng_[valid] == 0).sum()),
        "share_identical_in_all_runs": float((rng_[valid] == 0).mean()),
        "share_any_difference": float((rng_[valid] > 0).mean()),
        "score_range_mean": float(rng_[valid].mean()), "score_range_max": float(rng_[valid].max()),
        "score_range_ge_10": int((rng_[valid] >= 10).sum()),
        "pairwise_exact_agreement": {f"{a + 1}-{b + 1}": float((S[a][valid] == S[b][valid]).mean()) for a, b in pairs},
        "pairwise_spearman": {f"{a + 1}-{b + 1}": float(__import__("scipy.stats", fromlist=["spearmanr"])
                                                       .spearmanr(S[a][valid], S[b][valid]).statistic)
                              for a, b in pairs},
        "shortlist_membership_flips_at_primary_fraction": {f"{a + 1}-{b + 1}": flips(a, b) for a, b in pairs},
        "metric_spread": {k: [min(p[k] for p in per_run), max(p[k] for p in per_run)]
                          for k in ("ap_categorized_weighted", "recall_at_primary_fraction",
                                    "own_fraction_at_recall_0.95")},
        "reading": "Same prompt, same pinned model version, temperature 0, three runs. Any non-zero difference "
                   "is run-to-run nondeterminism of the hosted model; arm A (TF-IDF + LR) reproduces byte-for-byte.",
    }
    log(f"variance: identical in all runs {variance['share_identical_in_all_runs']:.4f}; "
        f"flips {variance['shortlist_membership_flips_at_primary_fraction']}")

    buf = io.StringIO()
    wr = csv.writer(buf, lineterminator="\n")
    wr.writerow(["appl_id", "core_project_num", "stratum", "weight"] + [f"score_run{r}" for r in range(1, RUNS + 1)])
    for i, r in enumerate(sample):
        wr.writerow([r["appl_id"], r["core_project_num"] or "", r["_stratum"], repr(r["_w"])]
                    + ["" if np.isnan(S[k][i]) else int(S[k][i]) for k in range(RUNS)])
    scores_gz = gzip.compress(buf.getvalue().encode(), mtime=0)
    summary = {
        "classifier_id": CLASSIFIER_ID, "arm": "C (secondary; pre-registration section 6a)",
        "pin": PIN, "pin_history": PIN_HISTORY, "params": PARAMS, "served_versions_seen": models_seen,
        "prompt": {"file": str(PROMPT_FILE.relative_to(ROOT)), "sha256": PROMPT_SHA256, "commit": PROMPT_COMMIT,
                   "shot": "zero-shot", "contents": "FY2026 NITRD PCA definitions + AI cross-PCA guidance "
                   "(verbatim) and the award's title, abstract, PHR; no labels, no prior-year membership",
                   "definitions_source": SOURCE_URL, "scope_file": str(SCOPE_FILE.relative_to(ROOT)),
                   "scope_sha256": SCOPE_SHA256},
        "label_fy": LABEL_FY, "universe_rule": qu.UNIVERSE_RULE_ID, "universe": int(N), "universe_nitrd": int(Nn),
        "design": {"kind": "stratified random sample, without replacement, by FY2021 label stratum",
                   "strata": info, "seed": SAMPLE_SEED, "estimator": "inverse-probability weighted; score "
                   "ties at the cut enter fractionally; parse failures rank last",
                   "ci": f"stratified bootstrap, {BOOT} resamples, seed {BOOT_SEED}, percentile 95%",
                   "why_sample": "full universe x 3 runs is ~190k calls / ~380M tokens; not justified for a "
                   "secondary arm", "smoke": SMOKE or None},
        "result_run": 1, "runs": per_run, "variance": variance,
        "equal_burden": {"primary": "task1-fingerprint-v1", "fraction": PRIMARY_FRACTION},
        "tokens": scorer.tokens, "transient_retries": scorer.retries, "scores_csv_gz_sha256": hashlib.sha256(scores_gz).hexdigest(),
        "elapsed_s_this_process": round(time.time() - t0),
    }
    OUT.mkdir(parents=True)
    (OUT / "prompt.txt").write_bytes(template.encode("utf-8"))
    (OUT / "scores.csv.gz").write_bytes(scores_gz)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    sha = guard.write_manifest(OUT / "READ_MANIFEST.json")
    log(f"done; READ_MANIFEST sha256 {sha}")
    print(json.dumps({"runs": [{k: v for k, v in p.items() if k not in ('curve', 'score_distribution')}
                               for p in per_run], "variance": variance}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
