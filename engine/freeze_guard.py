"""freeze-guard-v1-2026-10-24: no engine run on the evaluation projects outside the freeze run.

Owner rule (2026-10-24): constants committed + hashed, THEN the single engine run, THEN the
reveal, in that order, with nothing run in between. So the engine refuses to run on ANY of
the 480 evaluation projects unless all of these hold:

  1. the caller is the freeze run (environment variable UAC_NITRD_FREEZE_RUN=1, set only
     by scripts/freeze.sh);
  2. every engine input is committed: `git status --porcelain` is empty for GUARDED_PATHS;
  3. the engine's constants and input hashes equal the committed record
     (`tools/reveal_constants.py --check`).

The trigger is the project set, not the fixture file: a scrambled or trimmed copy of the
fixture still names the evaluation projects and still produces their proposals, so it is
guarded too. Fixtures with no evaluation project (synthetic tests) run freely.

Limit: this is a tripwire against accidental runs, not access control. Someone who edits
this file can remove it, but that edit is itself uncommitted and visible in git.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

GUARD_ID = "freeze-guard-v1-2026-10-24"
GUARD_EXIT = 3
FREEZE_ENV = "UAC_NITRD_FREEZE_RUN"
GUARDED_PATHS = ("engine", "scope", "cache", "fixtures", "docs/REVEAL_CONSTANTS.json",
                 "tools/reveal_constants.py")
ROOT = Path(__file__).resolve().parents[1]


def guard_problems(*, touches_eval: bool, freeze_env: bool, porcelain: str | None,
                   record_ok: bool | None) -> list[str]:
    """Pure decision. Returns the reasons to refuse; an empty list means the run may proceed."""
    if not touches_eval:
        return []
    out = []
    if not freeze_env:
        out.append(f"fixture names evaluation projects; only the freeze run may run on them "
                   f"(scripts/freeze.sh sets {FREEZE_ENV}=1)")
    if porcelain is None:
        out.append("cannot verify that engine inputs are committed (git status failed)")
    elif porcelain.strip():
        out.append("uncommitted changes in engine inputs: " + "; ".join(porcelain.strip().splitlines()[:10]))
    if record_ok is None:
        out.append("constants record not checked")
    elif record_ok is False:
        out.append("engine constants or inputs differ from docs/REVEAL_CONSTANTS.json")
    return out


def _porcelain(root: Path) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", *GUARDED_PATHS],
                           capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def _record_ok(root: Path) -> bool:
    r = subprocess.run([sys.executable, str(root / "tools" / "reveal_constants.py"), "--check"],
                       capture_output=True, text=True, timeout=600)
    return r.returncode == 0


def touches(fixture_ids: set[int], eval_ids: frozenset[int]) -> bool:
    return bool(fixture_ids & eval_ids)


def check(fixture_ids: set[int], eval_ids: frozenset[int], root: Path = ROOT) -> list[str]:
    if not touches(fixture_ids, eval_ids):
        return []
    return guard_problems(touches_eval=True, freeze_env=os.environ.get(FREEZE_ENV) == "1",
                          porcelain=_porcelain(root), record_ok=_record_ok(root))
