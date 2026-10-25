"""HITL write path on Task 1 (parent NITRD) candidates in the governed store. DEV / not scored."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from store import Actor, Rejected, SandboxStore  # noqa: E402
from workflow import drift, shortlist  # noqa: E402
from workflow.common import DEV_LABEL, DEV_SLICE, FINGERPRINT, FINGERPRINT_SHA256, PARENT_CROSSCUT, sha256  # noqa: E402

FX, CACHE = DEV_SLICE / "fixture.csv", DEV_SLICE / "cache.jsonl"
SME, INTRUDER = Actor("sme_alice", "coder"), Actor("mallory", "coder")


@pytest.fixture()
def t1(tmp_path):
    res = shortlist.run(FX, CACHE, tmp_path / "t1")
    st = SandboxStore(tmp_path / "store", authorized_coders={SME.id})
    st.load_listing(shortlist.parent_listing(FX, CACHE))
    out = shortlist.propose(st, res)
    P = {x["appl_id"]: x["proposal_id"] for x in out["proposed"]}
    missed = next(e for e in res["evidence"] if not e["candidate"] and e["distinct_terms"] == 0)["appl_id"]
    return st, res, P, missed, tmp_path


def _snap(st, fy, appl):
    return st._listings[(PARENT_CROSSCUT, fy)]["snapshot"][appl]


def _add(st, fy, appl, actor=SME):
    return st.propose(actor, PARENT_CROSSCUT, fy, appl, primary_pca="NITRD", ai_relevant=False, sub_pca="", score=0.0,
                      snapshot_sha=_snap(st, fy, appl), explanation={"label": DEV_LABEL, "stage": "task1_sme_added"})


def test_agent_proposals_are_pending_not_assignments(t1):
    st, res, P, _, _ = t1
    assert P and all(st.proposal(p)["status"] == "PENDING" for p in P.values())
    assert st.assignments(PARENT_CROSSCUT, res["fy"]) == [] and st.rollup(PARENT_CROSSCUT, res["fy"])["parent_total"] == 0
    pid = next(iter(P.values()))
    sha = st.proposal(pid)["snapshot_sha"]
    for who in (shortlist.AGENT, INTRUDER):
        with pytest.raises(Rejected, match="authorized coder"):
            st.approve(pid, who, snapshot_sha=sha)
    assert st.proposal(pid)["status"] == "PENDING" and len(st.rejections()) == 2


def test_accept_enters_confirmed_set_bound_to_snapshot(t1):
    st, res, P, _, _ = t1
    appl = sorted(P)[0]
    p = st.proposal(P[appl])
    with pytest.raises(Rejected, match="snapshot"):
        st.approve(P[appl], SME, snapshot_sha="0" * 64)
    a = st.assignment(st.approve(P[appl], SME, snapshot_sha=p["snapshot_sha"]))
    assert (a["appl_id"], a["approved_by"], a["provenance"], a["primary_pca"]) == (appl, SME.id, "approval", "NITRD")
    assert a["snapshot_sha"] == p["snapshot_sha"]
    with pytest.raises(Rejected):
        st.approve(P[appl], SME, snapshot_sha=p["snapshot_sha"])
    assert [x["appl_id"] for x in st.assignments(PARENT_CROSSCUT, res["fy"])] == [appl]


def test_reject_is_recorded_not_deleted(t1):
    st, res, P, _, _ = t1
    appl = sorted(P)[1]
    st.reject(P[appl], SME, reason="SME: not NITRD")
    p = st.proposal(P[appl])
    assert p["status"] == "REJECTED" and p["explanation"]["terms"] and len(st._proposals) == len(P)
    with pytest.raises(Rejected):
        st.approve(P[appl], SME, snapshot_sha=p["snapshot_sha"])
    with pytest.raises(Rejected):
        st.reject(P[appl], SME, reason="again")
    with pytest.raises(Rejected, match="authorized coder"):
        st.reject(P[sorted(P)[2]], shortlist.AGENT, reason="agent cannot dispose")


def test_sme_add_is_a_governed_human_decision(t1):
    st, res, P, missed, _ = t1
    fy = res["fy"]
    assert missed not in P
    with pytest.raises(Rejected, match="not in the parent listing"):
        st.propose(SME, PARENT_CROSSCUT, fy, 99999999, primary_pca="NITRD", ai_relevant=False, sub_pca="",
                   score=0.0, snapshot_sha=_snap(st, fy, missed), explanation={})
    with pytest.raises(Rejected):
        st.propose(SME, PARENT_CROSSCUT, fy, missed, primary_pca="AI", ai_relevant=True, sub_pca="",
                   score=0.0, snapshot_sha=_snap(st, fy, missed), explanation={})
    pid = _add(st, fy, missed)
    assert st.proposal(pid)["status"] == "PENDING" and st.proposal(pid)["proposer_role"] == "coder"
    with pytest.raises(Rejected, match="authorized coder"):
        st.approve(pid, INTRUDER, snapshot_sha=_snap(st, fy, missed))
    a = st.assignment(st.approve(pid, SME, snapshot_sha=_snap(st, fy, missed)))
    assert (a["appl_id"], a["approved_by"]) == (missed, SME.id)
    kinds = [(h["kind"], h["by"]) for h in st.history(PARENT_CROSSCUT, fy, missed)]
    assert kinds == [("proposed", SME.id), ("approved", SME.id)]


def test_unauthorized_add_cannot_be_self_confirmed(t1):
    st, res, _, missed, _ = t1
    pid = _add(st, res["fy"], missed, actor=INTRUDER)  # anyone may propose; only an authorized SME disposes
    with pytest.raises(Rejected, match="authorized coder"):
        st.approve(pid, INTRUDER, snapshot_sha=_snap(st, res["fy"], missed))
    assert st.assignments(PARENT_CROSSCUT, res["fy"]) == []


def test_decisions_feed_task3_and_replay_is_identical(t1):
    st, res, P, missed, tmp = t1
    fy, ids = res["fy"], sorted(P)
    st.approve(P[ids[0]], SME, snapshot_sha=st.proposal(P[ids[0]])["snapshot_sha"])
    st.reject(P[ids[1]], SME, reason="SME: not NITRD")
    st.approve(_add(st, fy, missed), SME, snapshot_sha=_snap(st, fy, missed))
    # an agent proposal that did not come from the shortlist must not count as a capture
    probe = st.propose(shortlist.AGENT, PARENT_CROSSCUT, fy, ids[3], primary_pca="NITRD", ai_relevant=False, sub_pca="",
                       score=0.0, snapshot_sha=_snap(st, fy, ids[3]), explanation={"stage": "probe"})
    assert probe
    with pytest.raises(Rejected):
        st.approve(P[ids[0]], SME, snapshot_sha="0" * 64)
    rep = drift.report(st, fy, FINGERPRINT, CACHE, tmp / "t3")
    c = rep["counts"]
    assert (c["sme_approved"], c["sme_rejected_over_captures"], c["sme_added_under_captures"]) == (1, 1, 1)
    assert c["shortlisted"] == len(P) and c["other_agent_proposals_excluded"] == 1
    assert [o["appl_id"] for o in rep["over_captures"]] == [ids[1]] and rep["over_captures"][0]["sme_reason"] == "SME: not NITRD"
    assert [u["appl_id"] for u in rep["under_captures"]] == [missed]
    assert sha256(FINGERPRINT) == FINGERPRINT_SHA256
    re = SandboxStore.replay(st.root, authorized_coders={SME.id})
    assert re._proposals == st._proposals and re._assignments == st._assignments and re._active == st._active
    assert re.rejections() == st.rejections() and re._history == st._history
    assert re.rollup(PARENT_CROSSCUT, fy) == st.rollup(PARENT_CROSSCUT, fy)


def test_store_is_a_sandbox_writing_only_under_its_root(t1):
    st, _, P, _, tmp = t1
    pid = next(iter(P.values()))
    st.approve(pid, SME, snapshot_sha=st.proposal(pid)["snapshot_sha"])
    assert sorted(p.name for p in st.root.iterdir()) == ["SANDBOX.json", "events.jsonl"]
    marker = json.loads((st.root / "SANDBOX.json").read_text())
    assert marker["sandbox"] is True and "SANDBOX" in marker["label"] and "not RCDC" in marker["label"]
    assert {p.name for p in tmp.iterdir()} == {"t1", "store"}
