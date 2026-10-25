#!/usr/bin/env python3
"""Derive engine/synonyms.json MECHANICALLY from the independent FY2024 corpus
(synonym-derivation-v2-2026-10-24; see docs/SYNONYM_DERIVATION.md).

No term is chosen by hand. For each PCA p:
  D_p = corpus docs retrieved by any of p's verbatim NITRD seed phrases
  B   = corpus docs retrieved by the background query
For every unigram/bigram t (engine normalisation, doc-level presence):
  z = smoothed log-odds ratio of doc rates (D_p vs B), prior PRIOR, divided by its s.e.
t becomes a synonym of p iff all of:
  * |D_p| >= MIN_DOCS
  * df_p(t) >= max(MIN_DF_ABS, MIN_DF_FRAC * |D_p|)
  * z >= Z_MIN
  * t is not already in p's scope-derived vocabulary, and t is not made only of p's seed tokens
  * every token has >= 3 chars and a letter
  * p has the highest z for t among all qualifying PCAs (ties: PCA order)
  * t is within p's TOP_K by (z desc, term asc)
The fixture text, the 480, suggestions and the held-out key are never read.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.run import PCA_CODES, _build_vocabulary, _ngrams, _normalise  # noqa: E402

DERIVATION_ID = "synonym-derivation-v2-2026-10-24"
PCA_ORDER = tuple(PCA_CODES) + ("AW",)
PRIOR = 0.5
MIN_DOCS = 20
MIN_DF_ABS = 5
MIN_DF_FRAC = 0.05
Z_MIN = 4.0
TOP_K = 12
CONSTANTS = {"PRIOR": PRIOR, "MIN_DOCS": MIN_DOCS, "MIN_DF_ABS": MIN_DF_ABS, "MIN_DF_FRAC": MIN_DF_FRAC,
             "Z_MIN": Z_MIN, "TOP_K": TOP_K, "NGRAMS": [1, 2]}


def doc_terms(rec: dict) -> set[str]:
    w = _normalise(f"{rec.get('title') or ''}. {rec.get('abstract') or ''}")
    terms = set(w)
    terms.update(" ".join(g) for g in _ngrams(w, 2))
    return terms


def _ok_tokens(t: str) -> bool:
    return all(len(x) >= 3 and any(c.isalpha() for c in x) for x in t.split())


def z_score(a: int, n1: int, b: int, n2: int) -> float:
    lo = math.log((a + PRIOR) / (n1 - a + PRIOR)) - math.log((b + PRIOR) / (n2 - b + PRIOR))
    var = 1 / (a + PRIOR) + 1 / (n1 - a + PRIOR) + 1 / (b + PRIOR) + 1 / (n2 - b + PRIOR)
    return lo / math.sqrt(var)


def derive(corpus: list[dict], seeds: dict[str, list[str]], scope: dict) -> tuple[list[dict], dict]:
    vocab = _build_vocabulary(scope["scopes"], scope.get("cross_pca_guidance", {}))
    terms_of = [doc_terms(r) for r in corpus]
    bg = [i for i, r in enumerate(corpus) if "background" in r["queries"]]
    bg_df = Counter(t for i in bg for t in terms_of[i])
    n2 = len(bg)
    qualifying: dict[str, list[tuple[float, str, dict]]] = {}
    per_pca = {}
    for p in PCA_ORDER:
        ids = [i for i, r in enumerate(corpus) if any(q.startswith(f"seed:{p}:") for q in r["queries"])]
        n1 = len(ids)
        per_pca[p] = {"docs": n1}
        if n1 < MIN_DOCS or n2 == 0:
            per_pca[p]["skipped"] = f"fewer than MIN_DOCS={MIN_DOCS} docs" if n1 < MIN_DOCS else "no background"
            continue
        seed_toks = {x for s in seeds.get(p, []) for x in _normalise(s)}
        known = set(vocab.get(p, {}))
        df = Counter(t for i in ids for t in terms_of[i])
        need = max(MIN_DF_ABS, math.ceil(MIN_DF_FRAC * n1))
        for t, a in df.items():
            if a < need or t in known or not _ok_tokens(t) or set(t.split()) <= seed_toks:
                continue
            z = z_score(a, n1, bg_df.get(t, 0), n2)
            if z >= Z_MIN:
                qualifying.setdefault(t, []).append((z, p, {"df_pca": a, "n_pca": n1, "df_bg": bg_df.get(t, 0),
                                                            "n_bg": n2, "z": round(z, 3)}))
    chosen: dict[str, list[tuple[float, str, dict]]] = {p: [] for p in PCA_ORDER}
    for t, opts in qualifying.items():
        z, p, st = max(opts, key=lambda o: (o[0], -PCA_ORDER.index(o[1])))
        chosen[p].append((z, t, st))
    out = []
    for p in PCA_ORDER:
        top = sorted(chosen[p], key=lambda x: (-x[0], x[1]))[:TOP_K]
        per_pca[p]["synonyms"] = len(top)
        for z, t, st in top:
            seed_list = "; ".join(seeds.get(p, []))
            out.append({"term": t, "pca": p, "expands": seed_list,
                        "reason": (f"Over-represented in FY2024 RePORTER projects whose title/abstract contains a "
                                   f"verbatim {p} scope phrase ({seed_list}) vs the FY2024 background: "
                                   f"{st['df_pca']}/{st['n_pca']} vs {st['df_bg']}/{st['n_bg']} docs, z={st['z']}."),
                        "source": "FY2024 independent RePORTER corpus (corpus/fy2024_independent.v1.jsonl.gz)",
                        "stats": st})
    return out, per_pca


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, default=ROOT / "corpus" / "fy2024_independent.v1.jsonl.gz")
    ap.add_argument("--seeds", type=Path, default=ROOT / "scope" / "synonym_seeds.v1.json")
    ap.add_argument("--scope", type=Path, default=ROOT / "scope" / "nitrd_pca_scopes_fy2025.v1.json")
    # Output is evidence only: the reveal engine uses no synonyms (vocabulary-scope-only-2026-10-24).
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "evidence" / "synonyms_v2_derived_NOT_APPLIED.json")
    a = ap.parse_args(argv)
    raw = gzip.decompress(a.corpus.read_bytes())
    corpus = [json.loads(l) for l in raw.decode("utf-8").splitlines() if l.strip()]
    seeds = json.loads(a.seeds.read_text(encoding="utf-8"))["seeds"]
    scope = json.loads(a.scope.read_text(encoding="utf-8"))
    syns, per_pca = derive(corpus, seeds, scope)
    doc = {
        "schema": "uac-nitrd/scope-synonyms/v2",
        "version": 2,
        "derivation_id": DERIVATION_ID,
        "selection_method": {
            "statement": ("Mechanical: candidates and inclusion are computed by tools/derive_synonyms.py from an "
                          "independent FY2024 RePORTER corpus retrieved with verbatim NITRD scope phrases "
                          "(scope/synonym_seeds.v1.json). The corpus excludes the 480 fixture projects and every "
                          "record sharing a core project number with them. No term was chosen by hand, and the "
                          "480 texts, fixture suggestions and held-out key were not read. Replaces v1, whose "
                          "candidates came from term frequency in the 480 (withdrawn)."),
            "constants": CONSTANTS,
            "corpus_jsonl_sha256": hashlib.sha256(raw).hexdigest(),
            "seeds_sha256": hashlib.sha256(a.seeds.read_bytes()).hexdigest(),
            "scope_sha256": hashlib.sha256(a.scope.read_bytes()).hexdigest(),
            "per_pca": per_pca,
        },
        "provenance_policy": ("Each entry's 'expands' lists the verbatim NITRD scope phrases that retrieved the "
                              "documents; 'reason' gives the statistic that admitted it. SME review may flag "
                              "entries with 'sme_review'; flagged entries are excluded from the AI gate."),
        "synonyms": syns,
    }
    a.out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(per_pca, indent=1))
    print(f"synonyms: {len(syns)}  sha256={hashlib.sha256(a.out.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
