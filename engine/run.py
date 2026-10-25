#!/usr/bin/env python3
"""Deterministic text-against-scope proposal engine (engine-method-deterministic-v1-2026-10-23).

Reads project text from the committed RePORTER cache, matches it against the
verbatim NITRD PCA scopes plus the AI cross-PCA examples, and applies NITRD's
"most specific PCA" rule. No model. No network in --offline mode.

Contract (required by S8):
  python engine/run.py --fixture F --out-dir D --offline
  writes D/proposals.csv and D/explanations.jsonl
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import write_meta  # noqa: E402
from engine.inputs import evaluation_appl_ids, load_project_refs  # noqa: E402
from engine import freeze_guard  # noqa: E402

# --------------------------------------------------------------------------- constants
SCOPE_PATH = ROOT / "scope" / "nitrd_pca_scopes_fy2025.v1.json"
# vocabulary-scope-only-2026-10-24 (owner decision): the reveal engine uses NO synonyms.
# Vocabulary = verbatim NITRD scope text + AI definition + cross-PCA guidance only.
# v1 (selected on the 480) and v2 (FY2024-derived, unusable) are kept as evidence in
# docs/evidence/. There is deliberately no CLI flag to load a synonym file.
VOCABULARY_ID = "vocabulary-scope-only-2026-10-24"
SYNONYMS_PATH = None
CACHE_PATH = ROOT / "cache" / "reporter" / "reporter_text.v1.jsonl"
PCA_CODES = ("ACNS", "AI", "CHuman", "CNPS", "CSP", "EdW", "EHCS", "ENIT", "HCIA", "IRAS", "LSDMA", "SPSQ")
AW = "AW"

# Scoring thresholds (fixed before running on the 480)
PCA_THRESHOLD = 1.0      # minimum score to propose a PCA
# ai_relevant gate (ai-gate-v2, decided 2026-10-24 before running on the 480).
# v1 summed IDF weights over the whole AI vocabulary, which includes generic words from
# the statutory definition ("systems", "models", "analysis", "human"), so almost any
# text passed. v2 requires at least AI_GATE_MIN_TERMS distinct AI-SPECIFIC terms.
AI_GATE_MIN_TERMS = 1
# AI-specific terms, each from the AI scope text, the statutory definition, or a
# cross-PCA sentence that assigns the concept to AI. Generic definition words excluded.
AI_GATE_CORE = (
    ("ai", "AI scope_text: 'research in AI and associated AI topics'"),
    ("human-ai", "AI scope_text: 'human-AI collaboration'"),
    ("artificial intelligence", "AI definition: 'The term artificial intelligence or AI'"),
    ("machine-based system", "AI definition: 'a machine-based system that can ... make predictions'"),
    ("model inference", "AI definition: 'use model inference to formulate options'"),
    ("machine vision", "cross-PCA 1: 'general methods for machine vision would fall under AI'"),
    ("intelligent autonomous systems", "cross-PCA 1: 'intelligent autonomous systems that exist only in cyberspace ... AI'"),
    ("computational linguistics", "cross-PCA 2: 'algorithms for computational linguistics would fall under AI'"),
    ("neural nets", "cross-PCA 4: 'chips optimized for neural nets would fall under AI'"),
    ("machine learning", "cross-PCA 5: 'R&D that is primarily machine learning would fall under AI'"),
)
# Synonyms with pca=AI also join the gate if MULTI-WORD and not flagged sme_review
# (gate-v2.1, pre-registered 2026-10-24 with synonym-derivation-v2, before deriving).
# NIH text writes American Indian/Alaska Native as "AI/AN"; rewrite before tokenising
# so it never reads as artificial intelligence (domain convention, not from the 480).
_AIAN_RE = re.compile(r"\bAI\s*/\s*ANs?\b", re.IGNORECASE)
PHRASE_BONUS = 3.0       # multiplier for multi-word phrase matches vs single words

# Stop words removed during normalisation
STOP = frozenset("a an and are as at be by for from has have in is it of on or "
                 "that the this to was were will with its been not can may such "
                 "these those which would should could also their than both but "
                 "into more other some most our we they all each no nor so do "
                 "does did about after between through during over under using "
                 "based upon along across among within including include includes "
                 "included related use uses used new".split())

# --------------------------------------------------------------------------- text normalisation
_WORD_RE = re.compile(r"[a-z][a-z0-9'-]*[a-z0-9]|[a-z]", re.ASCII)


def _normalise(text: str) -> list[str]:
    """Lower-case, split on non-alpha, drop stop words. No stemmer — exact scope words only."""
    return [w for w in _WORD_RE.findall(text.lower()) if w not in STOP]


def _ngrams(words: list[str], n: int) -> list[tuple[str, ...]]:
    return [tuple(words[i:i + n]) for i in range(len(words) - n + 1)]


# --------------------------------------------------------------------------- scope vocabulary
def _build_vocabulary(scopes: list[dict], guidance: dict) -> dict:
    """Build {pca_code: {term: (weight, source_phrase)}} from the scope text + AI guidance."""
    vocab: dict[str, dict[str, tuple[float, str]]] = {}
    doc_freq: Counter = Counter()  # term -> how many PCAs use it (for IDF)

    # Phase 1: extract terms from each PCA's scope_text
    for s in scopes:
        code = s["code"]
        if code == AW:
            continue  # AW vocabulary handled separately
        terms: dict[str, str] = {}  # normalised term -> source phrase
        text = s["scope_text"]
        words = _normalise(text)
        # single words
        for w in words:
            terms.setdefault(w, text)
        # 2-grams and 3-grams (phrases)
        for n in (2, 3):
            for ng in _ngrams(words, n):
                terms.setdefault(" ".join(ng), text)
        vocab[code] = {t: (1.0, src) for t, src in terms.items()}

    # Phase 2: AI definition and cross-PCA guidance → enrich AI vocabulary
    ai_def = guidance.get("ai_definition", {}).get("text", "")
    for w in _normalise(ai_def):
        vocab["AI"].setdefault(w, (1.0, ai_def))
    for ng in _ngrams(_normalise(ai_def), 2):
        vocab["AI"].setdefault(" ".join(ng), (1.0, ai_def))

    # Cross-PCA examples: add specific terms to the relevant PCA
    cross = guidance.get("ai_cross_pca", {}).get("items", [])
    _CROSS_MAP = [
        ("machine vision", "AI", cross[0] if len(cross) > 0 else ""),
        ("robot", "IRAS", cross[0] if len(cross) > 0 else ""),
        ("autonomous systems", "AI", cross[0] if len(cross) > 0 else ""),
        ("computational linguistics", "AI", cross[1] if len(cross) > 1 else ""),
        ("natural language processing", "CHuman", cross[1] if len(cross) > 1 else ""),
        ("human-machine interaction", "CHuman", cross[1] if len(cross) > 1 else ""),
        ("cybersecurity", "CSP", cross[2] if len(cross) > 2 else ""),
        ("neuromorphic", "EHCS", cross[3] if len(cross) > 3 else ""),
        ("neural net", "AI", cross[3] if len(cross) > 3 else ""),
        ("machine learning", "AI", cross[4] if len(cross) > 4 else ""),
        ("data management", "LSDMA", cross[4] if len(cross) > 4 else ""),
        ("data analysis", "LSDMA", cross[4] if len(cross) > 4 else ""),
    ]
    for term, pca, src in _CROSS_MAP:
        for t in [term] + list(" ".join(ng) for ng in _ngrams(_normalise(term), min(2, len(term.split())))):
            if t:
                vocab.setdefault(pca, {}).setdefault(t, (1.5, f"cross-PCA: {src[:80]}"))

    # Phase 3: compute IDF (inverse document frequency across the 12 PCAs)
    all_terms: set[str] = set()
    for code in PCA_CODES:
        all_terms.update(vocab.get(code, {}))
    for t in all_terms:
        doc_freq[t] = sum(1 for c in PCA_CODES if t in vocab.get(c, {}))
    n_docs = len(PCA_CODES)
    for code in PCA_CODES:
        for t, (w, src) in list(vocab.get(code, {}).items()):
            idf = math.log(n_docs / max(doc_freq[t], 1))
            is_phrase = " " in t
            weight = w * idf * (PHRASE_BONUS if is_phrase else 1.0)
            vocab[code][t] = (weight, src)

    # AW vocabulary (separate; only used for sub_pca tagging)
    aw_scope = next((s for s in scopes if s["code"] == AW), None)
    if aw_scope:
        aw_terms: dict[str, tuple[float, str]] = {}
        txt = aw_scope["scope_text"]
        for w in _normalise(txt):
            aw_terms.setdefault(w, (1.0, txt))
        for ng in _ngrams(_normalise(txt), 2):
            aw_terms.setdefault(" ".join(ng), (1.0, txt))
        vocab[AW] = aw_terms

    return vocab


def _load_synonyms(syn_path: Path, vocab: dict[str, dict[str, tuple[float, str]]]) -> int:
    """Merge synonyms.json into the vocabulary. Returns count of terms added."""
    if not syn_path.exists():
        return 0
    data = json.loads(syn_path.read_text(encoding="utf-8"))
    added = 0
    for entry in data.get("synonyms", []):
        if "comment" in entry:
            continue
        term = entry["term"].strip().lower()
        pca = entry["pca"].strip()
        src = f"synonym: {entry['expands'][:60]} ({entry['source']})"
        # Normalise the synonym term the same way as scope text
        norm = _normalise(term)
        if not norm:
            continue
        target = vocab.setdefault(pca, {})
        # Add normalised single-word and multi-word forms
        if len(norm) == 1:
            if norm[0] not in target:
                target[norm[0]] = (1.0, src)
                added += 1
        else:
            joined = " ".join(norm)
            if joined not in target:
                target[joined] = (1.0, src)
                added += 1
            # also add sub-phrases if the synonym is 3+ words
            for n in range(2, len(norm)):
                for ng in _ngrams(norm, n):
                    j = " ".join(ng)
                    if j not in target:
                        target[j] = (1.0, src)
                        added += 1
    return added


# --------------------------------------------------------------------------- scoring
def _score_text(words: list[str], pca_vocab: dict[str, tuple[float, str]]) -> list[dict]:
    """Return matched terms with weight and text span."""
    hits = []
    seen: set[str] = set()
    text_str = " ".join(words)
    # phrases first (2-grams, 3-grams), then single words
    for n in (3, 2, 1):
        for ng in (_ngrams(words, n) if n > 1 else [(w,) for w in words]):
            t = " ".join(ng)
            if t in seen or t not in pca_vocab:
                continue
            seen.add(t)
            weight, src = pca_vocab[t]
            # find the span in the original word list
            start = text_str.find(t)
            hits.append({"term": t, "weight": round(weight, 4), "source_phrase": src,
                         "text_span": text_str[max(0, start - 30):start + len(t) + 30].strip() if start >= 0 else ""})
    return hits


def _pca_score(hits: list[dict]) -> float:
    return sum(h["weight"] for h in hits)


# --------------------------------------------------------------------------- specificity rules
# Encoded from NITRD's cross-PCA AI examples. Each rule: if (project matches BOTH),
# the more specific PCA wins.
_SPECIFICITY = [
    # (general PCA, specific PCA, source)
    ("AI", "IRAS", "robots employing machine vision → IRAS, not AI"),
    ("AI", "CHuman", "broad HCI even with NLP → CHuman, not AI"),
    ("AI", "CSP", "AI supporting cybersecurity → CSP, not AI"),
    ("AI", "EHCS", "general neuromorphic computing → EHCS, not AI"),
    ("AI", "LSDMA", "wider data ecosystem with ML element → LSDMA, not AI"),
]


def _apply_specificity(ranked: list[dict]) -> tuple[list[dict], list[dict]]:
    """Re-rank by specificity rules. Returns (re-ranked, rules_applied)."""
    if len(ranked) < 2:
        return ranked, []
    codes = {r["pca"]: r for r in ranked}
    rules_applied = []
    for gen, spec, src in _SPECIFICITY:
        if gen in codes and spec in codes:
            gs, ss = codes[gen]["score"], codes[spec]["score"]
            if gs > 0 and ss > 0 and gs >= ss * 0.5:  # both qualify; specific wins if close
                rules_applied.append({"rule": f"{spec} over {gen}", "source": src})
                codes[gen]["score"] *= 0.5  # demote the general PCA
    re_ranked = sorted(codes.values(), key=lambda r: -r["score"])
    return re_ranked, rules_applied


# --------------------------------------------------------------------------- main logic
def build_ai_gate(syn_path: Path | None) -> tuple[tuple[tuple[str, ...], str], ...]:
    """AI-specific gate terms: AI_GATE_CORE + non-pending AI synonyms, as normalised tuples."""
    terms: dict[tuple[str, ...], str] = {}
    for t, src in AI_GATE_CORE:
        terms.setdefault(tuple(_normalise(t)), src)
    if syn_path is not None and syn_path.exists():
        for e in json.loads(syn_path.read_text(encoding="utf-8")).get("synonyms", []):
            if "comment" in e or e.get("pca") != "AI" or e.get("sme_review"):
                continue
            toks = tuple(_normalise(e["term"]))
            if len(toks) < 2:  # gate-v2.1: derived single words are too ambiguous to set the flag
                continue
            terms.setdefault(toks, f"synonym: {e['expands'][:60]} ({e['source']})")
    return tuple(sorted((k, v) for k, v in terms.items() if k))


def _ai_gate_hits(words: list[str], gate) -> list[dict]:
    hits = []
    for toks, src in gate:
        n = len(toks)
        for i in range(len(words) - n + 1):
            if tuple(words[i:i + n]) == toks:
                span = " ".join(words[max(0, i - 5):i + n + 5])
                hits.append({"term": " ".join(toks), "source_phrase": src, "text_span": span})
                break
    return hits


def propose(appl_id: int, text: dict, vocab: dict, scope_sha: str, ai_gate=()) -> dict:
    """Generate one proposal with full explanation."""
    title = (text.get("title") or "").strip()
    abstract = (text.get("abstract") or "").strip()
    phr = (text.get("public_health_relevance") or "").strip()
    combined = _AIAN_RE.sub("american indian alaska native", f"{title}. {abstract} {phr}".strip())
    text_sha = hashlib.sha256(json.dumps(text, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    if not title and not abstract:
        return {"appl_id": appl_id, "text_sha256": text_sha,
                "primary_pca": "", "ai_relevant": False, "sub_pca": "",
                "ranked": [], "rules_applied": [], "ai_evidence": [],
                "abstain_reason": f"no_public_text: title and abstract are both empty"}

    words = _normalise(combined)
    # Score each PCA
    ranked = []
    for code in PCA_CODES:
        hits = _score_text(words, vocab.get(code, {}))
        s = _pca_score(hits)
        if s > 0:
            ranked.append({"pca": code, "score": round(s, 4), "matched_terms": hits})
    ranked.sort(key=lambda r: -r["score"])

    # Apply specificity rules
    ranked, rules_applied = _apply_specificity(ranked)

    # AI evidence (for the ai_relevant flag): AI-specific gate terms only
    ai_hits = _ai_gate_hits(words, ai_gate)

    # Pick the winner
    primary = ""
    if ranked and ranked[0]["score"] >= PCA_THRESHOLD:
        primary = ranked[0]["pca"]

    ai_relevant = primary == "AI" or len(ai_hits) >= AI_GATE_MIN_TERMS

    # AW sub-PCA
    sub_pca = ""
    if primary == "ACNS":
        aw_hits = _score_text(words, vocab.get(AW, {}))
        if _pca_score(aw_hits) > 0:
            sub_pca = AW

    abstain = None
    if not primary:
        top = ranked[0]["score"] if ranked else 0.0
        abstain = f"below_threshold: top score {top:.2f} < {PCA_THRESHOLD}"

    return {"appl_id": appl_id, "text_sha256": text_sha,
            "primary_pca": primary, "ai_relevant": ai_relevant, "sub_pca": sub_pca,
            "ranked": [{"pca": r["pca"], "score": r["score"],
                        "matched_terms": r["matched_terms"][:15]} for r in ranked[:5]],
            "rules_applied": rules_applied,
            "ai_evidence": ai_hits[:10] if ai_relevant else [],
            "abstain_reason": abstain}


# --------------------------------------------------------------------------- CLI
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fixture", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--offline", action="store_true", required=True)
    ap.add_argument("--scope", type=Path, default=SCOPE_PATH)
    ap.add_argument("--cache", type=Path, default=CACHE_PATH)
    a = ap.parse_args(argv)

    # Load inputs
    refs = load_project_refs(a.fixture)
    # freeze-guard-v1: refuse the evaluation projects outside the freeze run, before anything is computed
    ids, eval_ids = {r.appl_id for r in refs}, evaluation_appl_ids()
    problems = freeze_guard.check(ids, eval_ids)
    if not problems and freeze_guard.touches(ids, eval_ids) and (
            a.scope.resolve() != SCOPE_PATH.resolve() or a.cache.resolve() != CACHE_PATH.resolve()):
        problems = ["evaluation projects must use the committed scope and cache, not --scope/--cache"]
    if problems:
        print(f"REFUSED ({freeze_guard.GUARD_ID}): " + " | ".join(problems), file=sys.stderr)
        return freeze_guard.GUARD_EXIT
    scope_data = json.loads(a.scope.read_text(encoding="utf-8"))
    scope_sha = hashlib.sha256(a.scope.read_bytes()).hexdigest()
    vocab = _build_vocabulary(scope_data["scopes"], scope_data.get("cross_pca_guidance", {}))

    # Load synonyms (before IDF is applied to synonym terms)
    syn_sha = ""
    syn_added = 0
    if SYNONYMS_PATH is not None:  # never true under vocabulary-scope-only
        syn_sha = hashlib.sha256(SYNONYMS_PATH.read_bytes()).hexdigest()
        syn_added = _load_synonyms(SYNONYMS_PATH, vocab)
        # Apply IDF + phrase bonus to newly-added synonym terms
        all_terms: set[str] = set()
        for code in list(PCA_CODES) + [AW]:
            all_terms.update(vocab.get(code, {}))
        doc_freq: Counter = Counter()
        for t in all_terms:
            doc_freq[t] = sum(1 for c in list(PCA_CODES) + [AW] if t in vocab.get(c, {}))
        n_docs = len(PCA_CODES)
        for code in list(PCA_CODES) + [AW]:
            for t, (w, src) in list(vocab.get(code, {}).items()):
                if src.startswith("synonym:"):
                    idf = math.log(n_docs / max(doc_freq[t], 1))
                    is_phrase = " " in t
                    vocab[code][t] = (w * idf * (PHRASE_BONUS if is_phrase else 1.0), src)
        print(f"Synonyms: {syn_added} terms added (SHA {syn_sha[:12]})")

    ai_gate = build_ai_gate(SYNONYMS_PATH)

    # Load cache
    cache: dict[int, dict] = {}
    for line in a.cache.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            cache[int(rec["appl_id"])] = rec
    missing = [r.appl_id for r in refs if r.appl_id not in cache]
    if missing and a.offline:
        print(f"FATAL: offline cache miss for {len(missing)} project(s): {missing[:5]}", file=sys.stderr)
        return 1

    # Generate proposals
    proposals = []
    for r in sorted(refs, key=lambda r: r.appl_id):
        text = cache.get(r.appl_id, {})
        proposals.append(propose(r.appl_id, text, vocab, scope_sha, ai_gate))

    # Write outputs
    a.out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = a.out_dir / "proposals.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["appl_id", "primary_pca", "ai_relevant", "sub_pca"])
        for p in proposals:
            w.writerow([p["appl_id"], p["primary_pca"],
                        str(p["ai_relevant"]).lower(), p["sub_pca"]])

    jsonl_path = a.out_dir / "explanations.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for p in proposals:
            f.write(json.dumps(p, sort_keys=True, ensure_ascii=False) + "\n")

    # Write meta
    write_meta(csv_path, scope_set=scope_data["scope_set_id"], scope_sha256=scope_sha,
               text_source="committed RePORTER text cache (cache/reporter/reporter_text.v1.jsonl)",
               vocabulary=VOCABULARY_ID, synonyms_sha256=syn_sha, synonyms_added=syn_added,
               ai_gate={"id": "ai-gate-v2-2026-10-24", "min_terms": AI_GATE_MIN_TERMS,
                        "terms": [" ".join(t) for t, _ in ai_gate]})

    # Summary
    by_pca = Counter(p["primary_pca"] for p in proposals if p["primary_pca"])
    abstained = sum(1 for p in proposals if not p["primary_pca"])
    ai_count = sum(1 for p in proposals if p["ai_relevant"])
    aw_count = sum(1 for p in proposals if p["sub_pca"] == AW)
    print(f"Proposals: {len(proposals)} projects, {abstained} abstained, {ai_count} ai_relevant, {aw_count} AW")
    print(f"By PCA: {dict(by_pca.most_common())}")
    print(f"SHA proposals.csv: {hashlib.sha256(csv_path.read_bytes()).hexdigest()}")
    print(f"SHA explanations.jsonl: {hashlib.sha256(jsonl_path.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
