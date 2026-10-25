"""DEV SME STAND-IN: rule-based placeholder decisions so the skeleton's write path can be exercised.

These are NOT SME judgments and carry no information about NITRD relevance. A real SME uses the
same store API (approve / reject / propose-as-coder) and the stand-in is simply not run. The rules
are fixed and printed in every decision record, so the drift report's input is fully visible:
  Task 1  approve a shortlisted candidate iff it has >= APPROVE_MIN_TERMS distinct fingerprint terms,
          otherwise reject it (an over-capture);
          ADD (propose as coder, then approve) up to MAX_ADDS non-shortlisted awards, lowest appl_id
          first, whose text contains an ADD_CUES word (an under-capture the fingerprint missed);
  Task 2  approve every pending subcategory proposal as proposed (AW stays unresolved, invariant 9).
"""
from __future__ import annotations

import re

from store import Actor
from workflow.common import DEV_LABEL, PARENT_CROSSCUT, SUBCAT_CROSSCUT

STANDIN = Actor("dev-sme-standin", "coder")
APPROVE_MIN_TERMS = 3
MAX_ADDS = 5
ADD_CUES = ("software", "algorithm", "algorithms", "computational", "informatics", "database")
RULES = {"label": DEV_LABEL, "who": "DEV SME STAND-IN (rule-based placeholder, not an SME)",
         "task1_approve_if_distinct_terms_at_least": APPROVE_MIN_TERMS, "task1_max_adds": MAX_ADDS,
         "task1_add_cues": list(ADD_CUES), "task2": "approve all pending as proposed"}
_CUE_RE = re.compile(r"\b(" + "|".join(ADD_CUES) + r")\b", re.IGNORECASE)


def _pending(store, cc, fy):
    return [p for pid, p in sorted(store._proposals.items())
            if p["status"] == "PENDING" and p["crosscut"] == cc and p["fy"] == fy]


def decide_task1(store, t1: dict, cache_recs: dict) -> list[dict]:
    fy, out = t1["fy"], []
    for p in _pending(store, PARENT_CROSSCUT, fy):
        n = p["explanation"]["distinct_terms"]
        if n >= APPROVE_MIN_TERMS:
            store.approve(p["proposal_id"], STANDIN, snapshot_sha=p["snapshot_sha"])
            out.append({"appl_id": p["appl_id"], "decision": "approve", "why": f"{n} distinct terms"})
        else:
            why = f"DEV stand-in: weak evidence ({n} < {APPROVE_MIN_TERMS} distinct terms)"
            store.reject(p["proposal_id"], STANDIN, reason=why)
            out.append({"appl_id": p["appl_id"], "decision": "reject", "why": why})
    L = store._listings[(PARENT_CROSSCUT, fy)]
    adds = 0
    for e in t1["evidence"]:
        if adds >= MAX_ADDS or e["candidate"] or e["abstain_reason"]:
            continue
        rec = cache_recs[e["appl_id"]]
        m = _CUE_RE.search(" ".join((rec.get(k) or "") for k in ("title", "abstract", "public_health_relevance")))
        if not m:
            continue
        snap = L["snapshot"][e["appl_id"]]
        pid = store.propose(STANDIN, PARENT_CROSSCUT, fy, e["appl_id"], primary_pca="NITRD", ai_relevant=False,
                            sub_pca="", score=0.0, snapshot_sha=snap, explanation={
                                "label": DEV_LABEL, "stage": "task1_sme_added", "cue": m.group(1).lower(),
                                "note": "added by the DEV SME stand-in; the fingerprint did not shortlist it"})
        store.approve(pid, STANDIN, snapshot_sha=snap)
        out.append({"appl_id": e["appl_id"], "decision": "add", "why": f"cue '{m.group(1).lower()}'"})
        adds += 1
    return out


def decide_task2(store, fy: int) -> list[dict]:
    out = []
    for p in _pending(store, SUBCAT_CROSSCUT, fy):
        store.approve(p["proposal_id"], STANDIN, snapshot_sha=p["snapshot_sha"])
        out.append({"appl_id": p["appl_id"], "decision": "approve", "primary_pca": p["primary_pca"],
                    "ai_relevant": p["ai_relevant"], "sub_pca": p["sub_pca"]})
    return out
