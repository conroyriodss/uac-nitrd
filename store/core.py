"""Sandboxed UAC write store (store-invariants-v1): the governed write surface.

The proposal engine PROPOSES into this store; an authorized coder (the SME) DISPOSES. Every
write is validated against the 9 UAC write-safety invariants and then appended to an event log.
State is only ever derived from that log, so replaying the log rebuilds it exactly. Nothing
is deleted, and every refusal is logged.

  1 No new projects        work only on projects in a loaded parent listing; a listing is fixed
                           once it is loaded, and there is no API to add projects.
  2 Exactly one primary    one primary subcategory per coding, and one active assignment per
                           project per crosscut and FY.
  3 AI terminal            NITRD primary = AI means ai_relevant, no sub_pca, and no further coding.
  4 100%, never prorated   an assignment carries the project's full listing amount; share must
                           be exactly 1; the parent total is the sum of the full amounts.
  5 Exclusion governed     an MR flag puts the project into SIACB review. It stays in the totals
                           until an SIACB member decides; an exclusion is recorded, not deleted.
  6 Type-5 rollover        a non-competing continuation (type 5) carries forward the prior FY's
                           APPROVED coding of the same core project; nothing else rolls.
  7 Agent proposes, SME    a proposal is never an assignment. Only an authorized coder approves,
    disposes               and the approval is bound to the exact project snapshot the
                           proposal was made on.
  8 Non-overlap crosscut   a project listed in several crosscuts is assigned in only one: the
                           higher match score wins, a tie goes to the SME, and nothing is moved
                           automatically.
  9 AW surfaced ambiguity  ACNS + sub_pca AW is never folded into ACNS automatically. Its dollars
                           sit in an unresolved bucket until an SME records a roll-up decision.

SANDBOX: the store writes only SANDBOX.json and events.jsonl under its root. It is not RCDC,
and no write leaves the sandbox.
"""
from __future__ import annotations

import json
import math
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

STORE_ID = "store-invariants-v1-2026-10-23"
LABEL = ("SANDBOX write store (not RCDC). Assignments are SME-approved dispositions of assist "
         "proposals; not an official UAC record.")
NITRD = "NITRD"
NITRD_CODES = ("ACNS", "AI", "CHuman", "CNPS", "CSP", "EdW", "EHCS", "ENIT", "HCIA", "IRAS", "LSDMA", "SPSQ")
AW = "AW"
AW_DECISIONS = ("fold_into_acns", "report_separately")
PROJ_RE = re.compile(r"^(\d)?([A-Z0-9]{3}[A-Z]{2}\d{6})")


class Rejected(Exception):
    """A write that would break a UAC write-safety invariant. It is always logged."""


@dataclass(frozen=True)
class Actor:
    id: str
    role: str


@dataclass(frozen=True)
class ListedProject:
    appl_id: int
    fy: int
    project_num: str
    subproj: str
    amount: int
    snapshot_sha: str


@dataclass(frozen=True)
class ParentListing:
    crosscut: str
    fy: int
    projects: list
    codes: tuple = field(default=())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _core(project_num: str, subproj: str):
    """(application type, (core project, subproject)) from an NIH project number."""
    m = PROJ_RE.match((project_num or "").strip())
    if not m:
        return None, None
    return m.group(1), (m.group(2), (subproj or "").strip())


class SandboxStore:
    """Event-sourced sandbox store. The public methods are the only write surface, and none deletes."""

    def __init__(self, root, authorized_coders=(), siacb_members=()):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._coders, self._siacb = frozenset(authorized_coders), frozenset(siacb_members)
        marker = self.root / "SANDBOX.json"
        if not marker.exists():
            marker.write_text(json.dumps({"sandbox": True, "store_id": STORE_ID, "label": LABEL}, indent=2) + "\n")
        self._log = self.root / "events.jsonl"
        self._log.touch()
        self._reset()
        for line in self._log.read_text(encoding="utf-8").splitlines():  # rebuild state from the log
            if line.strip():
                self._apply(json.loads(line))

    @classmethod
    def replay(cls, root, authorized_coders=(), siacb_members=()):
        return cls(root, authorized_coders, siacb_members)

    # ------------------------------------------------------------ event core
    def _reset(self):
        self._seq = 0
        self._listings: dict = {}        # (cc, fy) -> {codes, projects{appl: dict}, status{}, snapshot{}}
        self._proposals: dict = {}       # pid -> dict
        self._assignments: dict = {}     # aid -> dict
        self._active: dict = {}          # (cc, fy, appl) -> aid
        self._mrs: dict = {}             # mid -> dict
        self._aw_resolution: dict = {}   # (cc, fy) -> dict
        self._ties: dict = {}            # (fy, appl) -> dict
        self._rejections: list = []
        self._history: dict = {}         # (cc, fy, appl) -> [event summaries]
        self._n = {"P": 0, "A": 0, "M": 0}

    def _next(self, k: str) -> str:
        return f"{k}{self._n[k] + 1:06d}"

    def _emit(self, ev: dict) -> dict:
        ev = {"seq": self._seq + 1, "at_utc": _now(), **ev}
        with self._log.open("a", encoding="utf-8") as f:  # append-only
            f.write(json.dumps(ev, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        self._apply(ev)
        return ev

    def _hist(self, cc, fy, appl, kind, **kw):
        self._history.setdefault((cc, fy, appl), []).append({"kind": kind, **kw})

    def _new_assignment(self, a: dict):
        self._n["A"] += 1
        self._assignments[a["assignment_id"]] = a
        self._active[(a["crosscut"], a["fy"], a["appl_id"])] = a["assignment_id"]

    def _apply(self, ev: dict):
        self._seq = ev["seq"]
        k = ev["kind"]
        if k == "listing_loaded":
            projects = {p["appl_id"]: p for p in ev["projects"]}
            self._listings[(ev["crosscut"], ev["fy"])] = {
                "codes": tuple(ev["codes"]), "projects": projects,
                "status": {a: "listed" for a in projects},
                "snapshot": {a: p["snapshot_sha"] for a, p in projects.items()}}
        elif k == "proposed":
            self._n["P"] += 1
            p = dict(ev["proposal"], status="PENDING")
            self._proposals[p["proposal_id"]] = p
            self._hist(p["crosscut"], p["fy"], p["appl_id"], "proposed", proposal_id=p["proposal_id"], by=ev["by"])
        elif k == "approved":
            a = ev["assignment"]
            self._proposals[a["proposal_id"]]["status"] = "APPROVED"
            for pid in ev["superseded"]:
                q = self._proposals[pid]
                q["status"] = "SUPERSEDED"
                self._hist(q["crosscut"], q["fy"], q["appl_id"], "superseded", proposal_id=pid)
            self._new_assignment(a)
            self._hist(a["crosscut"], a["fy"], a["appl_id"], "approved", assignment_id=a["assignment_id"], by=ev["by"])
        elif k == "proposal_rejected":
            q = self._proposals[ev["proposal_id"]]
            q["status"] = "REJECTED"
            self._hist(q["crosscut"], q["fy"], q["appl_id"], "proposal_rejected", by=ev["by"])
        elif k == "coding_added":
            a = self._assignments[ev["assignment_id"]]
            if ev.get("sub_pca") is not None:
                a["sub_pca"] = ev["sub_pca"]
            if ev.get("tag") is not None:
                a["tags"] = a["tags"] + [ev["tag"]]
            self._hist(a["crosscut"], a["fy"], a["appl_id"], "coding_added", by=ev["by"])
        elif k == "snapshot_updated":
            L = self._listings[(ev["crosscut"], ev["fy"])]
            L["snapshot"][ev["appl_id"]] = ev["snapshot_sha"]
            for pid in ev["staled"]:
                self._proposals[pid]["status"] = "STALE"
            self._hist(ev["crosscut"], ev["fy"], ev["appl_id"], "snapshot_updated", by=ev["by"])
        elif k == "mr_flagged":
            self._n["M"] += 1
            m = dict(ev["mr"], status="PENDING_SIACB")
            self._mrs[m["mr_id"]] = m
            self._hist(m["crosscut"], m["fy"], m["appl_id"], "mr_flagged", mr_id=m["mr_id"], by=ev["by"])
        elif k == "siacb_decided":
            m = self._mrs[ev["mr_id"]]
            m.update(status="EXCLUDED" if ev["decision"] == "exclude" else "RETAINED",
                     decided_by=ev["by"], note=ev["note"])
            if ev["decision"] == "exclude":
                self._listings[(m["crosscut"], m["fy"])]["status"][m["appl_id"]] = "excluded"
            self._hist(m["crosscut"], m["fy"], m["appl_id"], "siacb_decided", decision=ev["decision"], by=ev["by"])
        elif k == "rolled_over":
            for a in ev["assignments"]:
                self._new_assignment(a)
                self._hist(a["crosscut"], a["fy"], a["appl_id"], "rolled_over", assignment_id=a["assignment_id"],
                           by=ev["by"])
        elif k == "crosscut_tie_resolved":
            self._ties[(ev["fy"], ev["appl_id"])] = {"winner": ev["winner"], "by": ev["by"], "reason": ev["reason"]}
        elif k == "aw_rollup_resolved":
            self._aw_resolution[(ev["crosscut"], ev["fy"])] = {"decision": ev["decision"], "by": ev["by"],
                                                              "reason": ev["reason"], "seq": ev["seq"]}
        elif k == "rejected":
            self._rejections.append({x: ev.get(x) for x in ("seq", "op", "reason", "by", "crosscut", "fy", "appl_id")})

    def _reject(self, op, reason, actor=None, **ctx):
        self._emit({"kind": "rejected", "op": op, "reason": reason, "by": getattr(actor, "id", None), **ctx})
        raise Rejected(reason)

    # ------------------------------------------------------------ guards
    def _require_coder(self, op, actor, what, **ctx):
        if not (isinstance(actor, Actor) and actor.role == "coder" and actor.id in self._coders):
            self._reject(op, f"only an authorized coder may {what}", actor, **ctx)

    def _listed(self, op, actor, cc, fy, appl):
        L = self._listings.get((cc, fy))
        if L is None or appl not in L["projects"]:
            self._reject(op, f"Appl ID {appl} is not in the parent listing {cc} FY{fy} (no new projects)",
                         actor, crosscut=cc, fy=fy, appl_id=appl)
        if L["status"][appl] == "excluded":
            self._reject(op, f"Appl ID {appl} was excluded by SIACB from {cc} FY{fy}", actor,
                         crosscut=cc, fy=fy, appl_id=appl)
        return L

    def _coding(self, op, actor, cc, codes, primary, ai, sub, ctx):
        def bad(msg):
            self._reject(op, msg, actor, **ctx)
        if not isinstance(primary, str) or not primary.strip():
            bad("exactly one primary subcategory is required (got zero or several)")
        if primary not in codes:
            bad(f"{primary!r} is not a {cc} primary subcategory" + (" (AW is a sub-PCA of ACNS)" if primary == AW else ""))
        if not isinstance(ai, bool):
            bad("ai_relevant must be true or false")
        sub = sub or ""
        if cc == NITRD:
            if primary == "AI" and (sub or not ai):
                bad("AI is terminal: primary AI is AI-relevant and takes no further coding")
            if sub not in ("", AW) or (sub == AW and primary != "ACNS"):
                bad("sub_pca AW requires primary ACNS (format v2)")
        elif sub:
            bad(f"{cc} has no sub-subcategories")
        return {"primary_pca": primary, "ai_relevant": ai, "sub_pca": sub}

    # ------------------------------------------------------------ 1. listings
    def load_listing(self, listing: "ParentListing"):
        key, ctx = (listing.crosscut, listing.fy), {"crosscut": listing.crosscut, "fy": listing.fy}
        if key in self._listings:
            self._reject("load_listing", f"parent listing {key} already loaded; listings are fixed (no new projects)", **ctx)
        if listing.crosscut == NITRD:
            if listing.codes and tuple(listing.codes) != NITRD_CODES:
                self._reject("load_listing", "NITRD codes are fixed", **ctx)
            codes = NITRD_CODES
        elif not listing.codes:
            self._reject("load_listing", f"crosscut {listing.crosscut} must declare its subcategory codes", **ctx)
        else:
            codes = tuple(listing.codes)
        ids = [p.appl_id for p in listing.projects]
        if len(ids) != len(set(ids)):
            self._reject("load_listing", "duplicate Appl IDs in the listing", **ctx)
        for p in listing.projects:
            if p.fy != listing.fy:
                self._reject("load_listing", f"Appl ID {p.appl_id} has FY{p.fy}, not FY{listing.fy}", **ctx)
            if not isinstance(p.amount, int) or isinstance(p.amount, bool) or p.amount < 0:
                self._reject("load_listing", f"Appl ID {p.appl_id}: amount must be whole dollars", **ctx)
        self._emit({"kind": "listing_loaded", **ctx, "codes": list(codes),
                    "projects": [asdict(p) for p in sorted(listing.projects, key=lambda p: p.appl_id)]})

    def listing_status(self, crosscut, fy, appl_id):
        return self._listings[(crosscut, fy)]["status"][appl_id]

    def update_snapshot(self, crosscut, fy, appl_id, snapshot_sha, actor, reason):
        ctx = {"crosscut": crosscut, "fy": fy, "appl_id": appl_id}
        self._require_coder("update_snapshot", actor, "record a new project snapshot", **ctx)
        L = self._listed("update_snapshot", actor, crosscut, fy, appl_id)
        if not isinstance(snapshot_sha, str) or not snapshot_sha or snapshot_sha == L["snapshot"][appl_id]:
            self._reject("update_snapshot", "snapshot must be a new, non-empty hash", actor, **ctx)
        staled = [pid for pid, p in sorted(self._proposals.items()) if p["status"] == "PENDING"
                  and (p["crosscut"], p["fy"], p["appl_id"]) == (crosscut, fy, appl_id)]
        self._emit({"kind": "snapshot_updated", **ctx, "snapshot_sha": snapshot_sha, "staled": staled,
                    "by": actor.id, "reason": reason})

    # ------------------------------------------------------------ 7. propose / dispose
    def propose(self, actor, crosscut, fy, appl_id, *, primary_pca, ai_relevant, sub_pca, score, snapshot_sha,
                explanation):
        ctx = {"crosscut": crosscut, "fy": fy, "appl_id": appl_id}
        if not isinstance(actor, Actor) or actor.role not in ("agent", "coder"):
            self._reject("propose", "only the agent or a coder may propose", actor, **ctx)
        L = self._listed("propose", actor, crosscut, fy, appl_id)
        coding = self._coding("propose", actor, crosscut, L["codes"], primary_pca, ai_relevant, sub_pca, ctx)
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
            self._reject("propose", "score must be a finite number", actor, **ctx)
        if snapshot_sha != L["snapshot"][appl_id]:
            self._reject("propose", "snapshot mismatch: a proposal must be made on the current project snapshot",
                         actor, **ctx)
        pid = self._next("P")
        self._emit({"kind": "proposed", "by": actor.id, "proposal": {
            "proposal_id": pid, **ctx, **coding, "score": float(score), "snapshot_sha": snapshot_sha,
            "proposed_by": actor.id, "proposer_role": actor.role, "explanation": explanation}})
        return pid

    def approve(self, proposal_id, actor, *, snapshot_sha, override=None, share=1.0):
        p = self._proposals.get(proposal_id)
        ctx = {k: p[k] for k in ("crosscut", "fy", "appl_id")} if p else {}
        self._require_coder("approve", actor, "approve a proposal into an assignment", **ctx)
        if p is None:
            self._reject("approve", f"no proposal {proposal_id}", actor)
        if isinstance(share, bool) or share != 1:
            self._reject("approve", "assignments are at 100% of the project amount; never prorated", actor, **ctx)
        if p["status"] != "PENDING":
            why = " (made on a superseded snapshot)" if p["status"] == "STALE" else ""
            self._reject("approve", f"proposal is {p['status']}{why}", actor, **ctx)
        cc, fy, appl = p["crosscut"], p["fy"], p["appl_id"]
        L = self._listed("approve", actor, cc, fy, appl)
        if not (snapshot_sha == p["snapshot_sha"] == L["snapshot"][appl]):
            self._reject("approve", "snapshot mismatch: approval must be bound to the exact project snapshot "
                         "the proposal was made on", actor, **ctx)
        o = dict(override or {})
        if set(o) - {"primary_pca", "ai_relevant", "sub_pca"}:
            self._reject("approve", "override may change only primary_pca, ai_relevant, sub_pca", actor, **ctx)
        coding = self._coding("approve", actor, cc, L["codes"],
                              o.get("primary_pca", p["primary_pca"]), o.get("ai_relevant", p["ai_relevant"]),
                              o.get("sub_pca", p["sub_pca"]), ctx)
        if (cc, fy, appl) in self._active:
            self._reject("approve", f"Appl ID {appl} already has a primary subcategory assignment in {cc} FY{fy}",
                         actor, **ctx)
        superseded = self._crosscut_gate("approve", actor, cc, fy, appl, p["score"], ctx)
        aid = self._next("A")
        self._emit({"kind": "approved", "by": actor.id, "superseded": superseded, "assignment": {
            "assignment_id": aid, "proposal_id": proposal_id, **ctx, **coding, "tags": [],
            "provenance": "approval", "approved_by": actor.id, "snapshot_sha": snapshot_sha, "score": p["score"],
            "overridden": bool(o), "proposed": {k: p[k] for k in ("primary_pca", "ai_relevant", "sub_pca")},
            "rolled_from_appl_id": None, "rolled_from_assignment_id": None}})
        return aid

    def reject(self, proposal_id, actor, reason):
        p = self._proposals.get(proposal_id)
        ctx = {k: p[k] for k in ("crosscut", "fy", "appl_id")} if p else {}
        self._require_coder("reject", actor, "reject a proposal", **ctx)
        if p is None or p["status"] != "PENDING":
            self._reject("reject", f"proposal {proposal_id} is not pending", actor, **ctx)
        self._emit({"kind": "proposal_rejected", "proposal_id": proposal_id, "by": actor.id, "reason": reason})

    # ------------------------------------------------------------ 3. further coding
    def add_coding(self, assignment_id, actor, sub_pca=None, tag=None):
        a = self._assignments.get(assignment_id)
        ctx = {k: a[k] for k in ("crosscut", "fy", "appl_id")} if a else {}
        self._require_coder("add_coding", actor, "add coding", **ctx)
        if a is None or self._active.get((a["crosscut"], a["fy"], a["appl_id"])) != assignment_id:
            self._reject("add_coding", f"no active assignment {assignment_id}", actor, **ctx)
        L = self._listed("add_coding", actor, a["crosscut"], a["fy"], a["appl_id"])
        if a["crosscut"] == NITRD and a["primary_pca"] == "AI":
            self._reject("add_coding", "AI is terminal: primary AI takes no further coding", actor, **ctx)
        if sub_pca is None and tag is None:
            self._reject("add_coding", "nothing to add", actor, **ctx)
        if sub_pca is not None:
            self._coding("add_coding", actor, a["crosscut"], L["codes"], a["primary_pca"], a["ai_relevant"], sub_pca, ctx)
        self._emit({"kind": "coding_added", "assignment_id": assignment_id, "sub_pca": sub_pca, "tag": tag,
                    "by": actor.id})

    # ------------------------------------------------------------ 8. crosscut non-overlap
    def _crosscut_gate(self, op, actor, cc, fy, appl, score, ctx):
        others = [c for (c, f) in self._listings if f == fy and c != cc and appl in self._listings[(c, f)]["projects"]]
        for c in others:
            if (c, fy, appl) in self._active:
                self._reject(op, f"Appl ID {appl} is already assigned in {c} FY{fy} (non-overlap); the SME must "
                             f"revoke it there before assigning in {cc}. Nothing is moved automatically.", actor, **ctx)
        rival = [(q["score"], q["crosscut"], pid) for pid, q in sorted(self._proposals.items())
                 if q["status"] == "PENDING" and q["fy"] == fy and q["appl_id"] == appl and q["crosscut"] in others]
        tie = self._ties.get((fy, appl))
        if tie and tie["winner"] != cc:
            self._reject(op, f"SME tie resolution assigned Appl ID {appl} to {tie['winner']}", actor, **ctx)
        if rival and not tie:
            best = max(r[0] for r in rival)
            if best > score:
                c = max(rival)[1]
                self._reject(op, f"Appl ID {appl} has a higher match score in {c} ({best} > {score})", actor, **ctx)
            if best == score:
                self._reject(op, f"crosscut tie on match score {score}; the SME must resolve the tie", actor, **ctx)
        return [r[2] for r in rival]

    def resolve_crosscut_tie(self, appl_id, fy, actor, winner, reason):
        ctx = {"crosscut": winner, "fy": fy, "appl_id": appl_id}
        self._require_coder("resolve_crosscut_tie", actor, "resolve a crosscut tie", **ctx)
        self._listed("resolve_crosscut_tie", actor, winner, fy, appl_id)
        self._emit({"kind": "crosscut_tie_resolved", "fy": fy, "appl_id": appl_id, "winner": winner,
                    "by": actor.id, "reason": reason})

    def conflicts(self, fy):
        out = []
        for (c, f, appl), aid in sorted(self._active.items()):
            if f != fy:
                continue
            pend = sorted({q["crosscut"] for q in self._proposals.values() if q["status"] == "PENDING"
                           and q["fy"] == fy and q["appl_id"] == appl and q["crosscut"] != c})
            if pend:
                out.append({"appl_id": appl, "assigned_in": c, "assignment_id": aid, "pending_in": pend})
        return out

    # ------------------------------------------------------------ 5. governed exclusion
    def flag_exclusion(self, crosscut, fy, appl_id, actor, reason):
        ctx = {"crosscut": crosscut, "fy": fy, "appl_id": appl_id}
        ok = isinstance(actor, Actor) and (actor.role == "agent" or (actor.role == "coder" and actor.id in self._coders)
                                           or (actor.role == "siacb" and actor.id in self._siacb))
        if not ok:
            self._reject("flag_exclusion", "unknown actor may not flag", actor, **ctx)
        self._listed("flag_exclusion", actor, crosscut, fy, appl_id)
        if any(m["status"] == "PENDING_SIACB" and (m["crosscut"], m["fy"], m["appl_id"]) == (crosscut, fy, appl_id)
               for m in self._mrs.values()):
            self._reject("flag_exclusion", "an MR flag is already pending SIACB review", actor, **ctx)
        mid = self._next("M")
        self._emit({"kind": "mr_flagged", "by": actor.id, "mr": {"mr_id": mid, **ctx, "reason": reason,
                                                                "flagged_by": actor.id}})
        return mid

    def siacb_decide(self, mr_id, actor, decision, note):
        m = self._mrs.get(mr_id)
        ctx = {k: m[k] for k in ("crosscut", "fy", "appl_id")} if m else {}
        if not (isinstance(actor, Actor) and actor.role == "siacb" and actor.id in self._siacb):
            self._reject("siacb_decide", "only an SIACB member may decide an MR flag", actor, **ctx)
        if m is None or m["status"] != "PENDING_SIACB":
            self._reject("siacb_decide", f"MR {mr_id} is not pending SIACB review", actor, **ctx)
        if decision not in ("exclude", "retain"):
            self._reject("siacb_decide", "decision must be exclude or retain", actor, **ctx)
        self._emit({"kind": "siacb_decided", "mr_id": mr_id, "decision": decision, "note": note, "by": actor.id})

    # ------------------------------------------------------------ 6. type-5 rollover
    def rollover(self, crosscut, from_fy, to_fy, actor):
        ctx = {"crosscut": crosscut, "fy": to_fy}
        self._require_coder("rollover", actor, "run a type-5 rollover", **ctx)
        if (crosscut, from_fy) not in self._listings or (crosscut, to_fy) not in self._listings or to_fy <= from_fy:
            self._reject("rollover", "both listings must be loaded, and to_fy must follow from_fy", actor, **ctx)
        prior_L = self._listings[(crosscut, from_fy)]
        prior = {}
        for (c, f, appl), aid in self._active.items():
            if c == crosscut and f == from_fy and prior_L["status"][appl] == "listed":
                p = prior_L["projects"][appl]
                prior[_core(p["project_num"], p["subproj"])[1]] = self._assignments[aid]
        L = self._listings[(crosscut, to_fy)]
        rolled, requires, new = [], [], []
        for appl in sorted(L["projects"]):
            if L["status"][appl] != "listed" or (crosscut, to_fy, appl) in self._active:
                continue
            p = L["projects"][appl]
            typ, key = _core(p["project_num"], p["subproj"])
            src = prior.get(key) if typ == "5" else None
            elsewhere = any((c, to_fy, appl) in self._active for (c, f) in self._listings if f == to_fy and c != crosscut)
            if src is None or elsewhere:
                requires.append(appl)
                continue
            aid = f"A{self._n['A'] + len(new) + 1:06d}"
            new.append({"assignment_id": aid, "proposal_id": None, "crosscut": crosscut, "fy": to_fy, "appl_id": appl,
                        "primary_pca": src["primary_pca"], "ai_relevant": src["ai_relevant"], "sub_pca": src["sub_pca"],
                        "tags": list(src["tags"]), "provenance": "rollover", "approved_by": actor.id,
                        "snapshot_sha": L["snapshot"][appl], "score": None, "overridden": False, "proposed": None,
                        "rolled_from_appl_id": src["appl_id"], "rolled_from_assignment_id": src["assignment_id"]})
            rolled.append(appl)
        if new:
            self._emit({"kind": "rolled_over", "crosscut": crosscut, "from_fy": from_fy, "fy": to_fy,
                        "by": actor.id, "assignments": new})
        return {"rolled": rolled, "requires_coding": requires}

    # ------------------------------------------------------------ 9. AW roll-up
    def resolve_aw_rollup(self, crosscut, fy, actor, decision, reason):
        ctx = {"crosscut": crosscut, "fy": fy}
        self._require_coder("resolve_aw_rollup", actor, "resolve the AW roll-up", **ctx)
        if crosscut != NITRD or (crosscut, fy) not in self._listings:
            self._reject("resolve_aw_rollup", "AW roll-up exists only for a loaded NITRD listing", actor, **ctx)
        if decision not in AW_DECISIONS:
            self._reject("resolve_aw_rollup", f"decision must be one of {AW_DECISIONS}", actor, **ctx)
        self._emit({"kind": "aw_rollup_resolved", **ctx, "decision": decision, "by": actor.id, "reason": reason})

    # ------------------------------------------------------------ reads
    def proposal(self, proposal_id):
        return json.loads(json.dumps(self._proposals[proposal_id]))

    def assignment(self, assignment_id):
        return json.loads(json.dumps(self._assignments[assignment_id]))

    def assignments(self, crosscut, fy):
        return [self.assignment(aid) for (c, f, _), aid in sorted(self._active.items()) if (c, f) == (crosscut, fy)]

    def mr(self, mr_id):
        return dict(self._mrs[mr_id])

    def history(self, crosscut, fy, appl_id):
        return [dict(h) for h in self._history.get((crosscut, fy, appl_id), [])]

    def rejections(self):
        return [dict(r) for r in self._rejections]

    def rollup(self, crosscut, fy):
        L = self._listings[(crosscut, fy)]
        amt = {a: p["amount"] for a, p in L["projects"].items()}
        res = self._aw_resolution.get((crosscut, fy)) if crosscut == NITRD else None
        by, aw_un, aw_sep, coded, changed = {}, [], [], set(), []
        for (c, f, appl), aid in sorted(self._active.items()):
            if (c, f) != (crosscut, fy) or L["status"][appl] == "excluded":
                continue
            a = self._assignments[aid]
            coded.add(appl)
            if a["snapshot_sha"] != L["snapshot"][appl]:
                changed.append(appl)
            if crosscut == NITRD and a["sub_pca"] == AW and (res is None or res["decision"] == "report_separately"):
                (aw_un if res is None else aw_sep).append(appl)
                continue
            by[a["primary_pca"]] = by.get(a["primary_pca"], 0) + amt[appl]  # full amount, once
        listed = [a for a in sorted(L["projects"]) if L["status"][a] == "listed"]
        uncoded = [a for a in listed if a not in coded]
        bucket = lambda ids: {"amount": sum(amt[a] for a in ids), "appl_ids": ids}  # noqa: E731
        unresolved = []
        if aw_un:
            unresolved.append(f"AW roll-up unresolved: {len(aw_un)} ACNS+AW project(s), ${sum(amt[a] for a in aw_un):,} "
                              f"not counted in ACNS; an SME must record fold_into_acns or report_separately")
        pend = sorted((m for m in self._mrs.values() if m["status"] == "PENDING_SIACB"
                       and (m["crosscut"], m["fy"]) == (crosscut, fy)), key=lambda m: m["mr_id"])
        if pend:
            unresolved.append(f"{len(pend)} MR flag(s) pending SIACB review; those projects remain in totals")
        parent_total = sum(by.values()) + bucket(aw_un)["amount"] + bucket(aw_sep)["amount"]
        assert parent_total + bucket(uncoded)["amount"] == sum(amt[a] for a in listed)  # invariant 4
        return {
            "label": LABEL, "store_id": STORE_ID, "crosscut": crosscut, "fy": fy,
            "by_pca": dict(sorted(by.items())),
            "aw_unresolved": bucket(aw_un), "aw_separate": bucket(aw_sep),
            "aw_resolution": ({k: res[k] for k in ("decision", "by", "reason")} if res else None),
            "acns_complete": not aw_un,
            "parent_total": parent_total,
            "uncoded": bucket(uncoded),
            "listing_total": sum(amt[a] for a in listed),
            "excluded": [{"appl_id": a, "amount": amt[a]} for a in sorted(L["projects"]) if L["status"][a] == "excluded"],
            "mr_pending": [{"mr_id": m["mr_id"], "appl_id": m["appl_id"], "reason": m["reason"]} for m in pend],
            "snapshot_changed_since_approval": changed,
            "unresolved": unresolved,
        }
