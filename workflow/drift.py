"""Task 3: fingerprint drift report from the store's SME decisions. DEV / not scored. FOR SME REVIEW.

Reads ONLY the Task 1 governed store (its state and its append-only event log), the fingerprint
(read-only) and the committed text snapshot. It reports, as concepts and counts:
  over-captures   the fingerprint shortlisted it and the SME REJECTED it; per fingerprint term, how
                  often it fired on rejected vs approved candidates, with example spans;
  under-captures  the SME ADDED it (coder-proposed, approved) and the fingerprint did not shortlist
                  it; which fingerprint terms it did hit (near-misses) and which words/phrases recur
                  in those awards but are not fingerprint terms (candidate concepts).
It never edits the fingerprint: the file's SHA-256 is recorded before and after, and a change is
only ever a new fingerprint version authored by the SME.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

from engine.run import STOP, _WORD_RE
from tools.build_fingerprint_placeholder import GENERIC
from workflow.common import DEV_LABEL, PARENT_CROSSCUT, WORKFLOW_ID, load_cache, sha256, write_json
from workflow.shortlist import TEXT_FIELDS, _index, match

NOTICE = ("FOR SME REVIEW. Concepts and counts only. This report does not change the fingerprint; any change "
          "is a new fingerprint version authored and committed by the SME.")
MAX_EXAMPLES = 3
TOP_CONCEPTS = 15
MIN_CONCEPT_DF = 2      # a candidate concept must recur in >= 2 under-captures
MIN_CONCEPT_LIFT = 2.0  # ... and be >= 2x as frequent there as in the unconfirmed background


def _words(rec: dict) -> list[str]:
    text = " ".join((rec.get(k) or "") for k, _ in TEXT_FIELDS).lower()
    return [w for w in _WORD_RE.findall(text) if w not in STOP]


def _concepts(words: list[str]) -> set[str]:
    ok = lambda w: len(w) >= 4 and w not in GENERIC and not w.isdigit()  # noqa: E731
    uni = {w for w in words if ok(w)}
    bi = {f"{a} {b}" for a, b in zip(words, words[1:]) if ok(a) and ok(b)}
    return uni | bi


def report(store1, fy: int, fingerprint_path: Path, cache: Path, out_dir: Path) -> dict:
    fp_sha_before = sha256(fingerprint_path)
    fp = json.loads(Path(fingerprint_path).read_text(encoding="utf-8"))
    by_n, _ = _index(fp)
    fp_terms = {t["term"] for t in fp["terms"]}
    recs, _snaps = load_cache(cache)
    L = store1._listings[(PARENT_CROSSCUT, fy)]
    reasons = {}
    for line in (store1.root / "events.jsonl").read_text(encoding="utf-8").splitlines():
        ev = json.loads(line)
        if ev["kind"] == "proposal_rejected":
            reasons[ev["proposal_id"]] = ev["reason"]
    props = [p for _, p in sorted(store1._proposals.items()) if (p["crosscut"], p["fy"]) == (PARENT_CROSSCUT, fy)]
    # Only proposals the shortlist made are fingerprint captures; any other agent proposal is reported
    # separately and never counted as an over- or under-capture.
    agent = [p for p in props if p["proposer_role"] == "agent"
             and (p["explanation"] or {}).get("stage") == "task1_shortlist"]
    other_agent = [p["proposal_id"] for p in props if p["proposer_role"] == "agent" and p not in agent]
    added = [p for p in props if p["proposer_role"] == "coder" and p["status"] == "APPROVED"]
    status = collections.Counter(p["status"] for p in agent)

    # over-captures: term firing on rejected vs approved candidates
    stats: dict[str, dict] = {}
    for p in agent:
        for term, h in p["explanation"]["terms"].items():
            s = stats.setdefault(term, {"term": term, "from": h["from"], "rejected": 0, "approved": 0, "pending": 0,
                                        "examples": []})
            k = {"REJECTED": "rejected", "APPROVED": "approved"}.get(p["status"], "pending")
            s[k] += 1
            if k == "rejected" and len(s["examples"]) < MAX_EXAMPLES:
                s["examples"].append({"appl_id": p["appl_id"], "span": h["spans"][0]})
    over_terms = sorted((s for s in stats.values() if s["rejected"]),
                        key=lambda s: (-s["rejected"], s["approved"], s["term"]))
    for s in over_terms:
        s["rejected_share"] = round(s["rejected"] / (s["rejected"] + s["approved"]), 3)
    over = [{"appl_id": p["appl_id"], "distinct_terms": p["explanation"]["distinct_terms"],
             "terms": sorted(p["explanation"]["terms"]), "sme_reason": reasons.get(p["proposal_id"])}
            for p in agent if p["status"] == "REJECTED"]

    # under-captures: what the SME added that the fingerprint missed
    added_ids = {p["appl_id"] for p in added}
    confirmed_ids = added_ids | {p["appl_id"] for p in agent if p["status"] == "APPROVED"}
    df_u, df_bg, under = collections.Counter(), collections.Counter(), []
    n_bg = 0
    for appl in sorted(L["projects"]):
        rec = recs.get(appl)
        if not rec:
            continue
        c = _concepts(_words(rec)) - fp_terms
        if appl in added_ids:
            df_u.update(c)
            hits = match(rec, by_n)
            under.append({"appl_id": appl, "near_miss_terms": sorted(hits), "distinct_terms": len(hits),
                          "sme_cue": next(p for p in added if p["appl_id"] == appl)["explanation"].get("cue")})
        elif appl not in confirmed_ids:
            df_bg.update(c)
            n_bg += 1
    n_u = len(added_ids)
    cands = [{"concept": t, "in_under_captures": df_u[t], "in_unconfirmed_background": df_bg[t],
              "lift": round((df_u[t] / n_u) / ((df_bg[t] + 1) / (n_bg + 1)), 2)}
             for t in df_u if df_u[t] >= MIN_CONCEPT_DF] if n_u else []
    cands = [c for c in cands if c["lift"] >= MIN_CONCEPT_LIFT]
    cands.sort(key=lambda c: (-c["in_under_captures"], -c["lift"], c["concept"]))

    fp_sha_after = sha256(fingerprint_path)
    assert fp_sha_after == fp_sha_before, "the drift report must never modify the fingerprint"
    rep = {
        "label": DEV_LABEL, "notice": NOTICE, "stage": "task3_drift", "workflow_id": WORKFLOW_ID, "fiscal_year": fy,
        "fingerprint_id": fp["fingerprint_id"], "fingerprint_sha256_before": fp_sha_before,
        "fingerprint_sha256_after": fp_sha_after, "source": "Task 1 governed store (state + events.jsonl)",
        "counts": {"universe": len(L["projects"]), "shortlisted": len(agent),
                   "sme_approved": status.get("APPROVED", 0), "sme_rejected_over_captures": status.get("REJECTED", 0),
                   "pending": status.get("PENDING", 0), "sme_added_under_captures": n_u,
                   "confirmed_nitrd_relevant": len(confirmed_ids),
                   "other_agent_proposals_excluded": len(other_agent)},
        "over_capture_terms": over_terms, "over_captures": over,
        "under_captures": under, "under_capture_candidate_concepts": cands[:TOP_CONCEPTS],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "drift_report.json", rep)
    (out_dir / "drift_report.md").write_text(_md(rep), encoding="utf-8")
    return rep


def _md(r: dict) -> str:
    c = r["counts"]
    out = [f"# Fingerprint drift report: {r['fingerprint_id']}", "", f"**{r['label']}**", "", r["notice"], "",
           f"FY{r['fiscal_year']} DEV universe {c['universe']}: shortlisted {c['shortlisted']}, SME-approved "
           f"{c['sme_approved']}, SME-rejected (over-captures) {c['sme_rejected_over_captures']}, pending {c['pending']}, "
           f"SME-added (under-captures) {c['sme_added_under_captures']}; confirmed {c['confirmed_nitrd_relevant']}.", "",
           "## Over-capture terms (fired on SME-rejected candidates)", "",
           "| term | from | rejected | approved | rejected share |", "| --- | --- | --- | --- | --- |"]
    out += [f"| {s['term']} | {', '.join(s['from'])} | {s['rejected']} | {s['approved']} | {s['rejected_share']} |"
            for s in r["over_capture_terms"]]
    out += ["", "## Under-captures (SME-added; fingerprint missed)", "", "| appl_id | near-miss terms | SME cue |",
            "| --- | --- | --- |"]
    out += [f"| {u['appl_id']} | {', '.join(u['near_miss_terms']) or '(none)'} | {u['sme_cue']} |" for u in r["under_captures"]]
    out += ["", "## Candidate concepts recurring in under-captures (not fingerprint terms)", "",
            "| concept | in under-captures | in unconfirmed background | lift |", "| --- | --- | --- | --- |"]
    out += [f"| {x['concept']} | {x['in_under_captures']} | {x['in_unconfirmed_background']} | {x['lift']} |"
            for x in r["under_capture_candidate_concepts"]]
    return "\n".join(out) + "\n"
