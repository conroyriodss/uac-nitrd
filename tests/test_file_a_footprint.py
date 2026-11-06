"""File A footprint guard (docs/FILE_A_FOOTPRINT.md, audit 2026-11-06).

File A is a non-public RCDC export. Twice its footprint turned out larger than documented, so the set of
tracked files that mention it, its digests, or the artifacts derived from it is pinned here. A new
reference fails this test until docs/FILE_A_FOOTPRINT.md section 4 and EXPECTED below are updated together.
The test reads tracked repository files only; it never opens any sealed location.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TERMS = re.compile(
    r"File A|filea|\bFILE_A\b|\bfile_a\b|fa6940d2|cbeab03e|3b81e5ca|db156b5f|tier2x|Tier 2x|/214\b|of 214"
    r"|214 projects|heldout_report|entry2-heldout|EXPECTED_KEY_PROJECTS|open_sealed_key|def load_key|RCDC exports?\b"
)

EXPECTED = {
    "README.md",
    "build/task1_backtest_vs_reported_v1/report.json",
    "build/task1_fy2024_score_v1/report.json",
    "docs/FILE_A_FOOTPRINT.md",
    "docs/HELDOUT_PROTOCOL.md",
    "docs/PERFORMANCE_VS_REPORTED.md",
    "docs/SYNONYM_DERIVATION.md",
    "docs/TASK1_MATCH_RULE.md",
    "docs/TASK1_MATCH_RULE_v2.md",
    "docs/TASK1_MATCH_RULE_v3.md",
    "docs/TASK1_MATCH_RULE_v4.md",
    "docs/TASK1_PREREGISTRATION.md",
    "docs/TASK1_PREREG_DEVIATIONS.md",
    "docs/TASK1_READ_GUARD_SPEC.md",
    "docs/reference/subcategory_id_to_pca.v1.md",
    "docs/seal/task1_fy2024_seal_manifest.json",
    "proposals/FREEZE_SWEEP.json",
    "results/RESULT.md",
    "results/heldout_report_v1.json",
    "scope/README.md",
    "store/README.md",
    "tests/test_build_guard.py",
    "tests/test_file_a_footprint.py",
    "tests/test_report_heldout.py",
    "tests/test_synonyms.py",
    "tests/test_task1_seal.py",
    "tools/backtest_vs_reported_v1.py",
    "tools/build_reporter_cache.py",
    "tools/compare_arms.py",
    "tools/rank_task1_fy2024_v1.py",
    "tools/report_heldout.py",
    "tools/score_heldout.py",
    "tools/score_task1_fy2024_v1.py",
    "tools/seal_guard.py",
    "workflow/build_guard.py",
    "workflow/common.py",
    "workflow/reveal_metrics.py",
    "workflow/sealed.py",
}

# The only per-award File A-derived identifiers committed (abstentions in the UAC held-out report).
KNOWN_HELDOUT_APPL_IDS = {11189671, 11376321}


def _tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return [p for p in out.decode().split("\0") if p]


def _matches() -> set[str]:
    hits = set()
    for rel in _tracked():
        path = ROOT / rel
        try:
            text = path.read_bytes().decode("utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if TERMS.search(text):
            hits.add(rel)
    return hits


def test_file_a_footprint_is_the_documented_set():
    got = _matches()
    assert got - EXPECTED == set(), f"new File A reference(s); update docs/FILE_A_FOOTPRINT.md: {sorted(got - EXPECTED)}"
    assert EXPECTED - got == set(), f"inventory lists files that no longer match: {sorted(EXPECTED - got)}"


def test_inventory_doc_lists_every_expected_file():
    doc = (ROOT / "docs" / "FILE_A_FOOTPRINT.md").read_text(encoding="utf-8")
    for rel in EXPECTED:
        assert Path(rel).name in doc, f"{rel} missing from FILE_A_FOOTPRINT.md"


def test_heldout_report_lists_only_the_known_appl_ids():
    import json

    report = json.loads((ROOT / "results" / "heldout_report_v1.json").read_text(encoding="utf-8"))
    ids = {int(x) for v in report["lists"].values() for x in v}
    assert ids == KNOWN_HELDOUT_APPL_IDS
