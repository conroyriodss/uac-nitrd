"""Task 1: fingerprint shortlist (was-this-award-NITRD-relevant). DEV / not scored.

Input: a DEV award universe (identity columns via engine.inputs, text from a committed RePORTER
snapshot) and a versioned fingerprint. Output: a candidate shortlist where every candidate carries
its match evidence (which fingerprint term hit which character span of which text field), and
those candidates PROPOSED into a governed store (agent proposes; status PENDING SME review).

Deterministic and offline: same inputs -> byte-identical files. Uses the engine's normalisation
(_WORD_RE, STOP, the AI/AN rewrite rule) so a term means the same thing in Task 1 and Task 2.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.run import STOP, _AIAN_RE, _WORD_RE  # noqa: E402
from store import Actor, ParentListing, Rejected  # noqa: E402
from tools.load_proposals import build_listing  # noqa: E402
from workflow.common import (DEV_LABEL, PARENT_CODES, PARENT_CROSSCUT, WORKFLOW_ID, check_fingerprint,  # noqa: E402
                             load_cache, load_dev_refs, sha256, write_json)

AGENT = Actor("task1-shortlist", "agent")
TEXT_FIELDS = (("title", "title"), ("abstract", "abstract"), ("public_health_relevance", "phr"))
MAX_SPANS_PER_TERM = 3
_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")  # length-preserving


def _index(fp: dict) -> tuple[dict[int, dict[str, dict]], int]:
    by_n: dict[int, dict[str, dict]] = {}
    for t in fp["terms"]:
        by_n.setdefault(t["n"], {})[t["term"]] = t
    return by_n, int(fp["decision_rule"]["shortlist_if_distinct_terms_at_least"])


def match(rec: dict, by_n: dict[int, dict[str, dict]]) -> dict[str, dict]:
    """{term: {from, spans[{field, start, end, text}]}}; offsets index the original field text."""
    hits: dict[str, dict] = {}
    for key, field in TEXT_FIELDS:
        text = rec.get(key) or ""
        low = _AIAN_RE.sub(lambda m: " " * len(m.group()), text).translate(_ASCII_LOWER)
        toks = [(m.group(), m.start(), m.end()) for m in _WORD_RE.finditer(low) if m.group() not in STOP]
        for n, terms in sorted(by_n.items()):
            for i in range(len(toks) - n + 1):
                term = " ".join(w for w, _, _ in toks[i:i + n])
                if term in terms:
                    h = hits.setdefault(term, {"from": terms[term]["from"], "n_spans": 0, "spans": []})
                    h["n_spans"] += 1
                    if len(h["spans"]) < MAX_SPANS_PER_TERM:
                        s, e = toks[i][1], toks[i + n - 1][2]
                        h["spans"].append({"field": field, "start": s, "end": e, "text": text[s:e]})
    return dict(sorted(hits.items()))


def run(fixture: Path, cache: Path, out_dir: Path, fingerprint: Path | None = None,
        fingerprint_sha: str | None = "pinned") -> dict:
    from workflow.common import FINGERPRINT, FINGERPRINT_SHA256
    fp = check_fingerprint(fingerprint or FINGERPRINT, FINGERPRINT_SHA256 if fingerprint_sha == "pinned" else fingerprint_sha)
    refs, fy = load_dev_refs(fixture)
    recs, snaps = load_cache(cache)
    by_n, k = _index(fp)
    rows, evid = [], []
    for ref in sorted(refs, key=lambda r: r.appl_id):
        rec = recs.get(ref.appl_id)
        has_text = bool(rec and rec.get("status") == "found" and any((rec.get(f) or "").strip() for f, _ in TEXT_FIELDS))
        hits = match(rec, by_n) if has_text else {}
        cand = has_text and len(hits) >= k
        rows.append((ref.appl_id, "true" if cand else "false", len(hits), "" if has_text else "no_public_text"))
        evid.append({"appl_id": ref.appl_id, "candidate": cand, "distinct_terms": len(hits),
                     "abstain_reason": None if has_text else "no_public_text", "terms": hits,
                     "text_sha256": snaps.get(ref.appl_id), "fingerprint_id": fp["fingerprint_id"]})
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "shortlist.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["appl_id", "candidate", "distinct_terms", "abstain_reason"])
        w.writerows(rows)
    (out_dir / "evidence.jsonl").write_text(
        "".join(json.dumps(e, sort_keys=True, separators=(",", ":")) + "\n" for e in evid), encoding="utf-8")
    n_c = sum(1 for e in evid if e["candidate"])
    meta = {"label": DEV_LABEL, "stage": "task1_shortlist", "workflow_id": WORKFLOW_ID, "fiscal_year": fy,
            "fingerprint_id": fp["fingerprint_id"], "fingerprint_status": fp["status"], "fingerprint_sha256": fp["_sha256"],
            "decision_rule": fp["decision_rule"], "fixture_sha256": sha256(fixture), "cache_sha256": sha256(cache),
            "universe": len(evid), "candidates": n_c, "not_shortlisted": len(evid) - n_c,
            "no_public_text": sum(1 for e in evid if e["abstain_reason"]),
            "shortlist_sha256": sha256(out_dir / "shortlist.csv"), "evidence_sha256": sha256(out_dir / "evidence.jsonl")}
    write_json(out_dir / "shortlist.meta.json", meta)
    return {"meta": meta, "evidence": evid, "fy": fy}


def parent_listing(fixture: Path, cache: Path) -> ParentListing:
    """The Task 1 store's listing = the DEV award universe (invariant 1: SMEs work only within it)."""
    L = build_listing(fixture, cache, None, crosscut=PARENT_CROSSCUT)
    return ParentListing(PARENT_CROSSCUT, L.fy, L.projects, codes=PARENT_CODES)


def propose(store, result: dict) -> dict:
    fy, out = result["fy"], {"proposed": [], "rejected": []}
    for e in result["evidence"]:
        if not e["candidate"]:
            continue
        snap = store._listings[(PARENT_CROSSCUT, fy)]["snapshot"][e["appl_id"]]
        try:
            pid = store.propose(AGENT, PARENT_CROSSCUT, fy, e["appl_id"], primary_pca="NITRD", ai_relevant=False,
                                sub_pca="", score=float(e["distinct_terms"]), snapshot_sha=snap, explanation={
                                    "label": DEV_LABEL, "stage": "task1_shortlist",
                                    "fingerprint_id": e["fingerprint_id"], "distinct_terms": e["distinct_terms"],
                                    "terms": e["terms"], "text_sha256": e["text_sha256"],
                                    "note": "ai_relevant is not assessed at Task 1 (parent relevance only)"})
            out["proposed"].append({"appl_id": e["appl_id"], "proposal_id": pid})
        except Rejected as ex:
            out["rejected"].append({"appl_id": e["appl_id"], "reason": str(ex)})
    return out
