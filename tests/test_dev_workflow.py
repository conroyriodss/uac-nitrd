"""NITRD workflow skeleton (Tasks 1-3) on the committed DEV slice. DEV / not scored."""
import csv
import json
import random
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.inputs import evaluation_appl_ids  # noqa: E402
from store import Rejected, SandboxStore  # noqa: E402
from tools import dev_pipeline  # noqa: E402
from workflow import shortlist  # noqa: E402
from workflow.common import (DEV_LABEL, DEV_SLICE, FINGERPRINT, FINGERPRINT_SHA256, RESERVED_FYS,  # noqa: E402
                             DevBoundaryError, check_dev_refs, load_dev_refs, sha256)

FX, CACHE = DEV_SLICE / "fixture.csv", DEV_SLICE / "cache.jsonl"
ENGINE_CACHE_KEYS = {"abstract", "appl_id", "award_amount", "fiscal_year", "project_num", "public_health_relevance",
                     "specific_aims", "status", "title"}


def test_fingerprint_is_a_pinned_placeholder_that_rebuilds():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "build_fingerprint_placeholder.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert sha256(FINGERPRINT) == FINGERPRINT_SHA256
    fp = json.loads(FINGERPRINT.read_text())
    assert fp["status"].startswith("PLACEHOLDER") and fp["label"] == "DEV / not scored"
    assert fp["derived_from"]["scope_sha256"] == sha256(ROOT / "scope" / "nitrd_pca_scopes_fy2025.v1.json")


def test_dev_slice_is_label_free_non_score_fy_and_disjoint_from_the_480():
    man = json.loads((DEV_SLICE / "MANIFEST.json").read_text())
    assert (sha256(FX), sha256(CACHE)) == (man["fixture_sha256"], man["cache_sha256"])
    assert man["rcdc_fields_requested"] is False and man["label"] == DEV_LABEL
    refs, fy = load_dev_refs(FX)
    assert fy == 2023 and fy not in RESERVED_FYS and len(refs) == man["n_records"] == 300
    assert not ({r.appl_id for r in refs} & evaluation_appl_ids())
    with FX.open() as f:
        assert next(csv.reader(f)) == ["Appl ID", "FY", "Project Number", "SubProj"]
    for line in CACHE.read_text().splitlines():
        assert set(json.loads(line)) == ENGINE_CACHE_KEYS  # no RCDC / category field anywhere


@pytest.mark.parametrize("fy", sorted(RESERVED_FYS))
def test_refuses_reserved_fys(tmp_path, fy):
    p = tmp_path / "fx.csv"
    p.write_text(f"Appl ID,FY,Project Number,SubProj\n91000001,{fy},1R01ZZ000001-01,\n")
    with pytest.raises(DevBoundaryError, match="reserved"):
        load_dev_refs(p)


def test_refuses_any_evaluation_project(tmp_path):
    appl = min(evaluation_appl_ids())
    p = tmp_path / "fx.csv"
    p.write_text(f"Appl ID,FY,Project Number,SubProj\n{appl},2023,1R01ZZ000001-01,\n")
    with pytest.raises(DevBoundaryError, match="evaluation"):
        load_dev_refs(p)


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    base = tmp_path_factory.mktemp("dev")
    return base, dev_pipeline.run(base / "run1"), dev_pipeline.run(base / "run2")


def test_pipeline_runs_end_to_end_and_is_deterministic(runs):
    base, a, b = runs
    assert a["files_sha256"] == b["files_sha256"] and a["store_state_sha256"] == b["store_state_sha256"]
    t1, sme, t2, t3 = a["task1"], a["sme_task1"], a["task2"], a["task3"]
    assert t1["universe"] == 300 and t1["candidates"] == t1["proposed_into_store"] > 0
    assert sme["approve"] + sme["reject"] == t1["candidates"] and sme["add"] > 0
    assert t2["confirmed_input"] == sme["approve"] + sme["add"] == t3["confirmed_nitrd_relevant"]
    assert t2["proposed"] + t2["abstained"] == t2["confirmed_input"] and t2["rejected"] == 0
    assert t2["parent_total"] + 0 <= t2["listing_total"]
    assert t3["sme_rejected_over_captures"] == sme["reject"] and t3["sme_added_under_captures"] == sme["add"]
    assert t3["fingerprint_unchanged"] and sha256(FINGERPRINT) == FINGERPRINT_SHA256


def test_every_output_is_labelled_dev_not_scored(runs):
    base, _, _ = runs
    out = base / "run1"
    for rel in ("PIPELINE.json", "task1/shortlist.meta.json", "task2/task2.meta.json", "task3/drift_report.json",
                "sme/task1_decisions.json", "sme/task2_decisions.json"):
        assert DEV_LABEL in (out / rel).read_text(), rel
    assert DEV_LABEL in (out / "task3" / "drift_report.md").read_text()
    for line in (out / "task1" / "store_task1" / "events.jsonl").read_text().splitlines():
        ev = json.loads(line)
        if ev["kind"] == "proposed":
            assert ev["proposal"]["explanation"]["label"] == DEV_LABEL


def test_task1_evidence_spans_point_at_the_text(runs):
    base, _, _ = runs
    recs = {json.loads(l)["appl_id"]: json.loads(l) for l in CACHE.read_text().splitlines()}
    field = {"title": "title", "abstract": "abstract", "phr": "public_health_relevance"}
    n = 0
    for line in (base / "run1" / "task1" / "evidence.jsonl").read_text().splitlines():
        e = json.loads(line)
        for term, h in e["terms"].items():
            for s in h["spans"]:
                assert recs[e["appl_id"]][field[s["field"]]][s["start"]:s["end"]] == s["text"]
                n += 1
    assert n > 0


def test_task1_proposals_are_pending_until_an_sme_disposes(tmp_path):
    res = shortlist.run(FX, CACHE, tmp_path / "t1")
    st = SandboxStore(tmp_path / "s", authorized_coders={"sme"})
    st.load_listing(shortlist.parent_listing(FX, CACHE))
    out = shortlist.propose(st, res)
    assert out["proposed"] and not st._assignments
    assert all(p["status"] == "PENDING" for p in st._proposals.values())
    pid = out["proposed"][0]["proposal_id"]
    with pytest.raises(Rejected):  # invariant 7: the agent cannot approve its own proposal
        st.approve(pid, shortlist.AGENT, snapshot_sha=st.proposal(pid)["snapshot_sha"])


def test_shortlist_is_invariant_to_non_identity_columns(tmp_path):
    """Scramble discipline: decoy/suggestion columns never change the shortlist or its evidence."""
    rows = list(csv.reader(FX.open()))
    rng = random.Random(20261025)
    fx2 = tmp_path / "scrambled.csv"
    with fx2.open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Category", "suggestion_1"] + rows[0] + ["Project Title"])
        for r in rows[1:]:
            w.writerow([rng.choice(["NITRD", "X"]), rng.choice(["AI", "LSDMA", ""])] + r + [f"decoy {rng.random()}"])
    a = shortlist.run(FX, CACHE, tmp_path / "a")
    b = shortlist.run(fx2, CACHE, tmp_path / "b")
    for n in ("shortlist.csv", "evidence.jsonl"):
        assert (tmp_path / "a" / n).read_bytes() == (tmp_path / "b" / n).read_bytes()
    assert a["meta"]["candidates"] == b["meta"]["candidates"]


def test_dev_pipeline_refuses_existing_out_dir(tmp_path):
    (tmp_path / "x").mkdir()
    with pytest.raises(DevBoundaryError):
        dev_pipeline.run(tmp_path / "x")


def test_check_dev_refs_rejects_mixed_fys():
    from engine.inputs import ProjectRef
    with pytest.raises(DevBoundaryError, match="mixes"):
        check_dev_refs([ProjectRef(91000001, 2022, "1R01ZZ000001-01", ""), ProjectRef(91000002, 2023, "x", "")])
