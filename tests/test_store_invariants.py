"""The 9 UAC write-safety invariants for the sandboxed write store (store-invariants-v1).

Written BEFORE the store, as failing tests. They use synthetic listings with fabricated Appl
IDs (1001-3999) and synthetic dollar amounts; no fixture, cache or key data is used.
"""
import hashlib
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from store import Actor, ListedProject, ParentListing, Rejected, SandboxStore  # noqa: E402

AGENT = Actor("engine", "agent")
CODER = Actor("coder1", "coder")
UNAUTH = Actor("intruder", "coder")  # claims the coder role but is not on the authorized list
BOARD = Actor("board1", "siacb")


def snap(a, v=0):
    return hashlib.sha256(f"{a}:{v}".encode()).hexdigest()


def P(a, num, amt, fy=2025, subproj=""):
    return ListedProject(appl_id=a, fy=fy, project_num=num, subproj=subproj, amount=amt, snapshot_sha=snap(a))


NITRD_2025 = [P(1001, "1R01AA000001-01", 100_000), P(1002, "5R01AA000002-03", 250_000),
              P(1003, "1U01AA000003-01", 75_000), P(1004, "2R01AA000004-06", 40_000)]


@pytest.fixture
def s(tmp_path):
    st = SandboxStore(tmp_path / "sandbox", authorized_coders={"coder1"}, siacb_members={"board1"})
    st.load_listing(ParentListing("NITRD", 2025, NITRD_2025))
    return st


def prop(st, a, pca, ai=True, sub="", score=1.0, cc="NITRD", fy=2025, snapshot=None):
    return st.propose(AGENT, cc, fy, a, primary_pca=pca, ai_relevant=ai, sub_pca=sub, score=score,
                      snapshot_sha=snapshot or snap(a), explanation={"matched": ["test"]})


def approve(st, pid, a, actor=CODER, **kw):
    return st.approve(pid, actor, snapshot_sha=kw.pop("snapshot_sha", snap(a)), **kw)


# ---------------------------------------------------------------- 1. No new projects
class TestI1NoNewProjects:
    def test_proposing_unlisted_project_is_rejected(self, s):
        with pytest.raises(Rejected, match="not in the parent listing"):
            prop(s, 9999, "AI")

    def test_listing_is_fixed_once_loaded(self, s):
        with pytest.raises(Rejected, match="already loaded"):
            s.load_listing(ParentListing("NITRD", 2025, NITRD_2025 + [P(1005, "1R01AA000005-01", 1)]))

    def test_project_in_other_fy_is_not_listed(self, s):
        with pytest.raises(Rejected, match="not in the parent listing"):
            prop(s, 1001, "AI", fy=2024)

    def test_no_api_to_add_projects(self, s):
        assert not [m for m in dir(s) if re.search(r"add_project|insert|append_project|new_project", m)]


# ---------------------------------------------------------------- 2. Exactly one primary
class TestI2ExactlyOnePrimary:
    @pytest.mark.parametrize("bad", [["AI", "CSP"], [], "", None, "AW", "XYZ"])
    def test_zero_multiple_or_invalid_primary_rejected(self, s, bad):
        with pytest.raises(Rejected):
            prop(s, 1001, bad)

    def test_second_assignment_for_same_project_rejected(self, s):
        approve(s, prop(s, 1001, "CSP"), 1001)
        with pytest.raises(Rejected, match="already has a primary"):
            approve(s, prop(s, 1001, "HCIA"), 1001)
        assert [a["primary_pca"] for a in s.assignments("NITRD", 2025)] == ["CSP"]

    def test_override_with_multiple_primaries_rejected(self, s):
        with pytest.raises(Rejected):
            approve(s, prop(s, 1001, "CSP"), 1001, override={"primary_pca": ["CSP", "HCIA"]})


# ---------------------------------------------------------------- 3. AI terminal
class TestI3AITerminal:
    def test_no_further_coding_after_ai_primary(self, s):
        aid = approve(s, prop(s, 1001, "AI"), 1001)
        with pytest.raises(Rejected, match="terminal"):
            s.add_coding(aid, CODER, sub_pca="AW")
        with pytest.raises(Rejected, match="terminal"):
            s.add_coding(aid, CODER, tag="anything")

    def test_ai_primary_cannot_carry_sub_pca_or_false_flag(self, s):
        with pytest.raises(Rejected):
            prop(s, 1001, "AI", sub="AW")
        with pytest.raises(Rejected):
            prop(s, 1001, "AI", ai=False)

    def test_control_non_ai_primary_accepts_further_coding(self, s):
        aid = approve(s, prop(s, 1001, "ACNS"), 1001)
        s.add_coding(aid, CODER, sub_pca="AW")
        assert s.assignment(aid)["sub_pca"] == "AW"


# ---------------------------------------------------------------- 4. 100%, never prorated
class TestI4FullAmountNeverProrated:
    @pytest.mark.parametrize("share", [0.5, 0.0, 1.5, 50])
    def test_partial_share_rejected(self, s, share):
        with pytest.raises(Rejected, match="100%"):
            approve(s, prop(s, 1001, "CSP"), 1001, share=share)

    def test_parent_total_is_sum_of_full_assignments(self, s):
        approve(s, prop(s, 1001, "AI"), 1001)
        approve(s, prop(s, 1002, "CSP"), 1002, share=1.0)
        r = s.rollup("NITRD", 2025)
        assert r["by_pca"] == {"AI": 100_000, "CSP": 250_000}
        assert r["parent_total"] == 350_000 == sum(r["by_pca"].values()) + r["aw_unresolved"]["amount"]
        assert r["uncoded"]["amount"] == 115_000 and r["listing_total"] == 465_000
        assert all(isinstance(v, int) for v in r["by_pca"].values())

    def test_amount_comes_from_listing_not_caller(self, s):
        with pytest.raises(TypeError):
            s.approve(prop(s, 1001, "CSP"), CODER, snapshot_sha=snap(1001), amount=1)


# ---------------------------------------------------------------- 5. Exclusion governed
class TestI5ExclusionGoverned:
    def test_no_delete_api(self, s):
        assert not [m for m in dir(s) if re.search(r"delete|remove|drop|purge|erase", m, re.IGNORECASE)]

    def test_mr_flag_keeps_project_pending_siacb(self, s):
        approve(s, prop(s, 1001, "CSP"), 1001)
        mr = s.flag_exclusion("NITRD", 2025, 1001, CODER, reason="out of scope?")
        r = s.rollup("NITRD", 2025)
        assert r["by_pca"]["CSP"] == 100_000  # still counted
        assert [m["appl_id"] for m in r["mr_pending"]] == [1001] and s.mr(mr)["status"] == "PENDING_SIACB"

    def test_only_siacb_decides(self, s):
        mr = s.flag_exclusion("NITRD", 2025, 1001, AGENT, reason="agent may flag")
        for actor in (AGENT, CODER):
            with pytest.raises(Rejected, match="SIACB"):
                s.siacb_decide(mr, actor, "exclude", note="x")

    def test_siacb_exclusion_is_recorded_not_deleted(self, s):
        approve(s, prop(s, 1001, "CSP"), 1001)
        mr = s.flag_exclusion("NITRD", 2025, 1001, CODER, reason="r")
        s.siacb_decide(mr, BOARD, "exclude", note="board minute 7")
        r = s.rollup("NITRD", 2025)
        assert "CSP" not in r["by_pca"] and [x["appl_id"] for x in r["excluded"]] == [1001]
        assert s.listing_status("NITRD", 2025, 1001) == "excluded"
        kinds = [e["kind"] for e in s.history("NITRD", 2025, 1001)]
        assert kinds[:4] == ["proposed", "approved", "mr_flagged", "siacb_decided"]
        with pytest.raises(Rejected, match="excluded"):
            prop(s, 1001, "AI")

    def test_siacb_retain_keeps_totals(self, s):
        approve(s, prop(s, 1001, "CSP"), 1001)
        s.siacb_decide(s.flag_exclusion("NITRD", 2025, 1001, CODER, reason="r"), BOARD, "retain", note="n")
        assert s.rollup("NITRD", 2025)["by_pca"]["CSP"] == 100_000

    def test_event_log_is_append_only(self, s):
        log = s.root / "events.jsonl"
        before = log.read_bytes()
        approve(s, prop(s, 1001, "CSP"), 1001)
        s.siacb_decide(s.flag_exclusion("NITRD", 2025, 1001, CODER, reason="r"), BOARD, "exclude", note="n")
        after = log.read_bytes()
        assert after.startswith(before) and len(after) > len(before)


# ---------------------------------------------------------------- 6. Type-5 rollover
class TestI6Type5Rollover:
    @pytest.fixture
    def two_years(self, tmp_path):
        st = SandboxStore(tmp_path / "sb", authorized_coders={"coder1"}, siacb_members={"board1"})
        st.load_listing(ParentListing("NITRD", 2024, [
            P(2001, "1R01BB000010-01", 90_000, fy=2024), P(2002, "1R01BB000011-04", 80_000, fy=2024),
            P(2003, "1R01BB000012-01", 70_000, fy=2024), P(2004, "1R01BB000013-01", 60_000, fy=2024)]))
        approve(st, prop(st, 2001, "AI", fy=2024), 2001)
        approve(st, prop(st, 2002, "CSP", fy=2024), 2002)
        prop(st, 2003, "HCIA", fy=2024)  # proposed only, never approved
        a4 = approve(st, prop(st, 2004, "ACNS", fy=2024), 2004)
        st.add_coding(a4, CODER, sub_pca="AW")
        st.load_listing(ParentListing("NITRD", 2025, [
            P(3001, "5R01BB000010-02", 95_000), P(3002, "2R01BB000011-05", 85_000),
            P(3003, "5R01BB000012-02", 72_000), P(3004, "5R01BB000013-02", 61_000),
            P(3005, "5R01BB000099-02", 10_000)]))
        return st

    def test_type5_carries_prior_approved_coding(self, two_years):
        rep = two_years.rollover("NITRD", 2024, 2025, CODER)
        a = {x["appl_id"]: x for x in two_years.assignments("NITRD", 2025)}
        assert a[3001]["primary_pca"] == "AI" and a[3001]["provenance"] == "rollover"
        assert a[3001]["rolled_from_appl_id"] == 2001 and a[3001]["snapshot_sha"] == snap(3001)
        assert two_years.rollup("NITRD", 2025)["by_pca"]["AI"] == 95_000
        assert 3001 in rep["rolled"]

    def test_competing_renewal_and_unapproved_prior_are_not_rolled(self, two_years):
        rep = two_years.rollover("NITRD", 2024, 2025, CODER)
        rolled = {x["appl_id"] for x in two_years.assignments("NITRD", 2025)}
        assert 3002 not in rolled and 3003 not in rolled and 3005 not in rolled
        assert {3002, 3003, 3005} <= set(rep["requires_coding"])

    def test_rollover_needs_authorized_coder(self, two_years):
        for actor in (AGENT, UNAUTH):
            with pytest.raises(Rejected):
                two_years.rollover("NITRD", 2024, 2025, actor)

    def test_rolled_aw_stays_unresolved(self, two_years):
        two_years.rollover("NITRD", 2024, 2025, CODER)
        r = two_years.rollup("NITRD", 2025)
        assert r["aw_unresolved"]["amount"] == 61_000 and "ACNS" not in r["by_pca"]

    def test_rollover_is_idempotent(self, two_years):
        two_years.rollover("NITRD", 2024, 2025, CODER)
        rep = two_years.rollover("NITRD", 2024, 2025, CODER)
        assert rep["rolled"] == [] and len(two_years.assignments("NITRD", 2025)) == 2


# ---------------------------------------------------------------- 7. Agent proposes, SME disposes
class TestI7AgentProposesSMEDisposes:
    def test_proposal_is_not_an_assignment(self, s):
        prop(s, 1001, "CSP")
        assert s.assignments("NITRD", 2025) == [] and s.rollup("NITRD", 2025)["parent_total"] == 0

    @pytest.mark.parametrize("actor", [AGENT, UNAUTH, BOARD])
    def test_only_authorized_coder_approves(self, s, actor):
        with pytest.raises(Rejected, match="authorized coder"):
            approve(s, prop(s, 1001, "CSP"), 1001, actor=actor)

    def test_agent_cannot_propose_as_coder_and_coder_proposal_still_needs_approval(self, s):
        pid = s.propose(CODER, "NITRD", 2025, 1001, primary_pca="CSP", ai_relevant=True, sub_pca="",
                        score=1.0, snapshot_sha=snap(1001), explanation={})
        assert s.assignments("NITRD", 2025) == [] and s.proposal(pid)["status"] == "PENDING"

    def test_approval_bound_to_exact_snapshot(self, s):
        pid = prop(s, 1001, "CSP")
        with pytest.raises(Rejected, match="snapshot"):
            approve(s, pid, 1001, snapshot_sha=snap(1001, 99))  # coder viewed something else
        s.update_snapshot("NITRD", 2025, 1001, snap(1001, 1), CODER, reason="RePORTER text revised")
        with pytest.raises(Rejected, match="snapshot"):
            approve(s, pid, 1001, snapshot_sha=snap(1001, 1))  # proposal was made on the old text
        with pytest.raises(Rejected, match="snapshot"):
            approve(s, pid, 1001)  # old text is no longer current
        assert s.proposal(pid)["status"] == "STALE"
        pid2 = prop(s, 1001, "CSP", snapshot=snap(1001, 1))
        aid = approve(s, pid2, 1001, snapshot_sha=snap(1001, 1))
        assert s.assignment(aid)["snapshot_sha"] == snap(1001, 1)

    def test_override_and_reject_are_recorded_dispositions(self, s):
        aid = approve(s, prop(s, 1001, "AI"), 1001, override={"primary_pca": "CSP", "ai_relevant": True})
        a = s.assignment(aid)
        assert a["primary_pca"] == "CSP" and a["proposed"]["primary_pca"] == "AI" and a["approved_by"] == "coder1"
        pid = prop(s, 1002, "HCIA")
        s.reject(pid, CODER, reason="not IT R&D")
        assert s.proposal(pid)["status"] == "REJECTED"
        with pytest.raises(Rejected):
            approve(s, pid, 1002)

    def test_proposal_snapshot_must_be_current_at_proposal_time(self, s):
        with pytest.raises(Rejected, match="snapshot"):
            prop(s, 1001, "CSP", snapshot=snap(1001, 5))


# ---------------------------------------------------------------- 8. Non-overlap crosscut
class TestI8NonOverlapCrosscut:
    @pytest.fixture
    def both(self, s):
        # NNI subcategories are not modelled here; a crosscut other than NITRD must declare its codes.
        s.load_listing(ParentListing("NNI", 2025, [P(1001, "1R01AA000001-01", 100_000)], codes=("NANO",)))
        return s

    def test_higher_score_crosscut_wins(self, both):
        p_nitrd = prop(both, 1001, "EHCS", score=2.0)
        p_nni = prop(both, 1001, "NANO", score=3.0, cc="NNI")
        with pytest.raises(Rejected, match="higher match score in NNI"):
            approve(both, p_nitrd, 1001)
        approve(both, p_nni, 1001)
        assert both.assignments("NITRD", 2025) == [] and len(both.assignments("NNI", 2025)) == 1

    def test_tie_is_surfaced_for_sme(self, both):
        p1 = prop(both, 1001, "EHCS", score=2.0)
        prop(both, 1001, "NANO", score=2.0, cc="NNI")
        with pytest.raises(Rejected, match="tie"):
            approve(both, p1, 1001)
        both.resolve_crosscut_tie(1001, 2025, CODER, winner="NITRD", reason="primarily computing")
        approve(both, p1, 1001)
        assert len(both.assignments("NITRD", 2025)) == 1

    def test_never_assigned_in_both_and_never_auto_moved(self, both):
        approve(both, prop(both, 1001, "EHCS", score=2.0), 1001)
        p_nni = prop(both, 1001, "NANO", score=3.0, cc="NNI")
        with pytest.raises(Rejected, match="already assigned in NITRD"):
            approve(both, p_nni, 1001)
        assert len(both.assignments("NITRD", 2025)) == 1 and both.assignments("NNI", 2025) == []
        assert [c["appl_id"] for c in both.conflicts(2025)] == [1001]

    def test_crosscut_membership_still_required(self, s):
        with pytest.raises(Rejected, match="not in the parent listing"):
            prop(s, 1001, "NANO", cc="NNI")


# ---------------------------------------------------------------- 9. AW surfaced ambiguity
class TestI9AWSurfacedAmbiguity:
    def test_aw_not_folded_into_acns_by_default(self, s):
        approve(s, prop(s, 1001, "ACNS", sub="AW"), 1001)
        approve(s, prop(s, 1002, "ACNS"), 1002)
        r = s.rollup("NITRD", 2025)
        assert r["by_pca"]["ACNS"] == 250_000 and r["aw_unresolved"] == {"amount": 100_000, "appl_ids": [1001]}
        assert r["acns_complete"] is False and r["aw_resolution"] is None
        assert any("AW roll-up" in u for u in r["unresolved"])
        assert r["parent_total"] == 350_000

    def test_aw_requires_acns_primary(self, s):
        with pytest.raises(Rejected):
            prop(s, 1001, "CHuman", sub="AW")

    def test_only_coder_resolves_and_resolution_is_recorded(self, s):
        approve(s, prop(s, 1001, "ACNS", sub="AW"), 1001)
        with pytest.raises(Rejected):
            s.resolve_aw_rollup("NITRD", 2025, AGENT, "fold_into_acns", reason="x")
        s.resolve_aw_rollup("NITRD", 2025, CODER, "fold_into_acns", reason="SME decision")
        r = s.rollup("NITRD", 2025)
        assert r["by_pca"]["ACNS"] == 100_000 and r["aw_unresolved"]["amount"] == 0 and r["acns_complete"]
        assert r["aw_resolution"]["decision"] == "fold_into_acns" and r["aw_resolution"]["by"] == "coder1"

    def test_report_separately_keeps_acns_complete_without_aw(self, s):
        approve(s, prop(s, 1001, "ACNS", sub="AW"), 1001)
        s.resolve_aw_rollup("NITRD", 2025, CODER, "report_separately", reason="SME decision")
        r = s.rollup("NITRD", 2025)
        assert "ACNS" not in r["by_pca"] and r["aw_separate"]["amount"] == 100_000 and r["acns_complete"]
        assert r["parent_total"] == 100_000

    def test_unknown_resolution_rejected(self, s):
        with pytest.raises(Rejected):
            s.resolve_aw_rollup("NITRD", 2025, CODER, "prorate", reason="x")


# ---------------------------------------------------------------- sandbox + audit
class TestSandbox:
    def test_replay_rebuilds_identical_state(self, s):
        approve(s, prop(s, 1001, "ACNS", sub="AW"), 1001)
        approve(s, prop(s, 1002, "AI"), 1002)
        s.flag_exclusion("NITRD", 2025, 1003, CODER, reason="r")
        again = SandboxStore.replay(s.root, authorized_coders={"coder1"}, siacb_members={"board1"})
        assert again.rollup("NITRD", 2025) == s.rollup("NITRD", 2025)

    def test_writes_stay_inside_sandbox_and_are_labelled(self, s):
        approve(s, prop(s, 1001, "CSP"), 1001)
        assert sorted(p.name for p in s.root.iterdir()) == ["SANDBOX.json", "events.jsonl"]
        assert s.rollup("NITRD", 2025)["label"].startswith("SANDBOX")

    def test_rejections_are_logged(self, s):
        with pytest.raises(Rejected):
            prop(s, 9999, "AI")
        assert s.rejections()[-1]["appl_id"] == 9999
