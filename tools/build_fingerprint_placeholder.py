#!/usr/bin/env python3
"""Build the PLACEHOLDER Task 1 fingerprint (NITRD parent relevance) from public NITRD scope text.

This is NOT the curated fingerprint. It exists so the workflow skeleton has a versioned,
hashed, SME-owned artifact to run against. The curated fingerprint is authored by the SME and
ships as a new version; this tool never edits an existing version.

Derivation (mechanical, deterministic, no project text, no labels):
  * source: scope/nitrd_pca_scopes_fy2025.v1.json (verbatim NITRD FY2025 PCA definitions,
    the AI statutory definition and the AI cross-PCA guidance), recorded by SHA-256;
  * normalisation: the engine's own (engine.run _WORD_RE + STOP), so matches mean the same thing;
  * terms: every 2- and 3-word sequence of the normalised scope text whose tokens are all >= 3
    characters and none of which is in GENERIC below; plus the engine's 10 AI_GATE_CORE terms;
  * each term records which PCA scopes it came from (provenance for the SME).
Decision rule (placeholder): a project is shortlisted iff it hits >= MIN_DISTINCT_TERMS distinct terms.

Usage: python tools/build_fingerprint_placeholder.py [--write | --check]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.run import AI_GATE_CORE, STOP, _WORD_RE  # noqa: E402  (one normalisation for engine + workflow)

SCOPE = ROOT / "scope" / "nitrd_pca_scopes_fy2025.v1.json"
OUT = ROOT / "workflow" / "fingerprint" / "nitrd_parent_fingerprint.placeholder.v0.json"
FINGERPRINT_ID = "nitrd-parent-fingerprint-placeholder-v0-2026-10-25"
MIN_DISTINCT_TERMS = 2
NGRAM_SIZES = (2, 3)
MIN_TOKEN_LEN = 3
# Words too generic to carry NITRD meaning on their own inside a phrase (fixed before any match).
GENERIC = frozenset("""
research development including include includes related relevant support supports supporting
new novel use uses using used areas area such well also other others advances advance advanced
efforts effort activities activity based across within among various variety range wide broad
focus focuses focused enable enables enabling provide provides providing improve improving
work works program programs projects project federal agency agencies national nation level
levels part parts all any each both many more most less key important critical core basic
""".split())


def _words(text: str) -> list[str]:
    return [w for w in _WORD_RE.findall(text.lower()) if w not in STOP]


def _sources(scope: dict) -> list[tuple[str, str]]:
    out = [(s["code"], s["scope_text"]) for s in scope["scopes"]]
    g = scope["cross_pca_guidance"]
    ai = g["ai_definition"]
    out.append(("AI", ai["text"]))
    out += [("AI", str(it)) for it in ai.get("items", [])]
    x = g["ai_cross_pca"]
    out.append(("AI-cross-PCA", x["text"]))
    out += [("AI-cross-PCA", str(it)) for it in x.get("items", [])]
    return out


def _committed(p: Path) -> bool:
    import subprocess
    r = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--error-unmatch", str(p.relative_to(ROOT))],
                       capture_output=True, text=True)
    return r.returncode == 0


def build() -> bytes:
    raw = SCOPE.read_bytes()
    scope = json.loads(raw)
    terms: dict[str, set[str]] = {}
    for code, text in _sources(scope):
        w = _words(text)
        for n in NGRAM_SIZES:
            for i in range(len(w) - n + 1):
                g = w[i:i + n]
                if all(len(t) >= MIN_TOKEN_LEN and t not in GENERIC for t in g):
                    terms.setdefault(" ".join(g), set()).add(code)
    for t in AI_GATE_CORE:
        term = t[0] if isinstance(t, (tuple, list)) else t
        terms.setdefault(" ".join(_words(term)), set()).add("AI-gate-core")
    doc = {
        "schema": "uac-nitrd/parent-fingerprint/v0",
        "fingerprint_id": FINGERPRINT_ID,
        "status": "PLACEHOLDER: mechanically derived from public NITRD scope text for the workflow "
                  "skeleton. NOT the curated fingerprint; not for scoring.",
        "owner": "SME (unassigned). Changes ship as a new version authored by the SME; never edited in place.",
        "label": "DEV / not scored",
        "derived_from": {"scope_file": "scope/nitrd_pca_scopes_fy2025.v1.json",
                         "scope_sha256": hashlib.sha256(raw).hexdigest(),
                         "scope_set_id": scope.get("scope_set_id"), "version": scope.get("version")},
        "normalisation": "engine.run: lower-case, _WORD_RE tokens, STOP words dropped; no stemming",
        "derivation": {"ngram_sizes": list(NGRAM_SIZES), "min_token_len": MIN_TOKEN_LEN,
                       "generic_excluded": sorted(GENERIC), "plus": "engine AI_GATE_CORE terms"},
        "decision_rule": {"shortlist_if_distinct_terms_at_least": MIN_DISTINCT_TERMS},
        "terms": [{"term": t, "n": len(t.split()), "from": sorted(c)} for t, c in sorted(terms.items())],
    }
    return (json.dumps(doc, indent=1, sort_keys=True) + "\n").encode("utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    b = build()
    if a.write:
        if OUT.exists() and OUT.read_bytes() != b and _committed(OUT):
            print(f"refusing to overwrite committed {OUT.name}: a fingerprint version is never edited in place",
                  file=sys.stderr)
            return 1
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_bytes(b)
    elif not OUT.exists() or OUT.read_bytes() != b:
        print("placeholder fingerprint does not rebuild byte-identically", file=sys.stderr)
        return 1
    print(f"{FINGERPRINT_ID}: {len(json.loads(b)['terms'])} terms, sha256 {hashlib.sha256(b).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
