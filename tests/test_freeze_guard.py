"""freeze-guard-v1: the engine refuses the 480 evaluation projects outside the freeze run.

No test here produces engine output for an evaluation project: every refusal happens before
any scoring, and the positive cases use synthetic projects only.
"""
import csv
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import synthetic_projects  # noqa: E402
from engine import freeze_guard  # noqa: E402
from engine.inputs import EVALUATION_FIXTURE, evaluation_appl_ids  # noqa: E402

RUN = ROOT / "engine" / "run.py"
CLEAN = dict(porcelain="", record_ok=True)


def _engine(fixture, out, env_extra=None, *extra):
    import os
    env = {k: v for k, v in os.environ.items() if k != freeze_guard.FREEZE_ENV}
    env.update(env_extra or {})
    return subprocess.run([sys.executable, str(RUN), "--fixture", str(fixture), "--out-dir", str(out),
                           "--offline", *extra], capture_output=True, text=True, env=env)


def _fixture_with(tmp_path, ids, name="f.csv"):
    p = tmp_path / name
    with p.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["FY", "Appl ID", "SubProj", "Project Number"])
        for i in ids:
            w.writerow([2025, i, "", "x"])
    return p


# ---- pure decision ---------------------------------------------------------------------------
def test_non_evaluation_projects_always_run():
    assert freeze_guard.guard_problems(touches_eval=False, freeze_env=False, porcelain="M engine/run.py",
                                       record_ok=False) == []


def test_all_conditions_met_allows_the_freeze_run():
    assert freeze_guard.guard_problems(touches_eval=True, freeze_env=True, **CLEAN) == []


@pytest.mark.parametrize("kw, needle", [
    (dict(freeze_env=False, **CLEAN), "only the freeze run"),
    (dict(freeze_env=True, porcelain=" M engine/run.py\n", record_ok=True), "uncommitted changes"),
    (dict(freeze_env=True, porcelain="?? engine/synonyms.json\n", record_ok=True), "uncommitted changes"),
    (dict(freeze_env=True, porcelain=None, record_ok=True), "cannot verify"),
    (dict(freeze_env=True, porcelain="", record_ok=False), "differ from docs/REVEAL_CONSTANTS.json"),
    (dict(freeze_env=True, porcelain="", record_ok=None), "not checked"),
], ids=["no-freeze-env", "modified-engine", "untracked-synonyms", "git-unavailable", "record-drift",
        "record-unchecked"])
def test_each_condition_alone_refuses(kw, needle):
    probs = freeze_guard.guard_problems(touches_eval=True, **kw)
    assert probs and any(needle in p for p in probs), probs


def test_guarded_paths_cover_every_engine_input():
    for p in ("engine", "scope", "cache", "fixtures", "docs/REVEAL_CONSTANTS.json", "tools/reveal_constants.py"):
        assert p in freeze_guard.GUARDED_PATHS


def test_evaluation_set_is_the_480():
    assert len(evaluation_appl_ids()) == 480


# ---- the real engine -------------------------------------------------------------------------
def test_engine_refuses_the_real_fixture_outside_the_freeze_run(tmp_path):
    r = _engine(EVALUATION_FIXTURE, tmp_path / "o")
    assert r.returncode == freeze_guard.GUARD_EXIT and "REFUSED" in r.stderr, r.stderr
    assert not (tmp_path / "o").exists()


def test_engine_refuses_a_copy_naming_one_evaluation_project(tmp_path):
    """Keyed on projects, not file bytes: a one-row copy is still the evaluation set."""
    one = min(evaluation_appl_ids())
    r = _engine(_fixture_with(tmp_path, [one, 91000001]), tmp_path / "o")
    assert r.returncode == freeze_guard.GUARD_EXIT and not (tmp_path / "o").exists()


def test_freeze_env_alone_does_not_open_the_guard_on_a_dirty_tree(tmp_path):
    """Setting the variable by hand is not enough: inputs must be committed and recorded."""
    dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", *freeze_guard.GUARDED_PATHS],
                           capture_output=True, text=True).stdout.strip()
    if not dirty:
        pytest.skip("engine inputs are committed; the dirty-tree case is covered by the pure tests")
    r = _engine(EVALUATION_FIXTURE, tmp_path / "o", {freeze_guard.FREEZE_ENV: "1"})
    assert r.returncode == freeze_guard.GUARD_EXIT and "uncommitted changes" in r.stderr
    assert not (tmp_path / "o").exists()


def test_engine_refuses_scope_or_cache_override_on_evaluation_projects(tmp_path, monkeypatch):
    """Even if every other condition held, the freeze run must use the committed scope and cache."""
    from engine import run
    monkeypatch.setattr(freeze_guard, "check", lambda ids, ev, root=None: [])
    _, cache = synthetic_projects.make(tmp_path / "syn")
    rc = run.main(["--fixture", str(EVALUATION_FIXTURE), "--out-dir", str(tmp_path / "o"), "--offline",
                   "--cache", str(cache)])
    assert rc == freeze_guard.GUARD_EXIT and not (tmp_path / "o").exists()


def test_synthetic_projects_run_without_the_freeze_env(tmp_path):
    fx, cache = synthetic_projects.make(tmp_path / "syn")
    r = _engine(fx, tmp_path / "o", None, "--cache", str(cache))
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "o" / "proposals.csv").is_file()


def test_no_test_passes_the_evaluation_fixture_to_a_successful_engine_run():
    """Static check: the only tests naming the evaluation fixture alongside the real engine are
    the refusal tests in this file (fake engines in sweep tests don't carry the guard)."""
    for p in (ROOT / "tests").glob("test_*.py"):
        if p.name == "test_freeze_guard.py":
            continue
        src = p.read_text(encoding="utf-8")
        assert not ('"engine" / "run.py"' in src and "str(FIXTURE)" in src and "--fixture" in src
                    and "HONEST_ENGINE" not in src), p.name
