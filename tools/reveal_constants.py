"""Pre-reveal record of every engine constant and input hash (no output: see freeze order).

    python tools/reveal_constants.py --write   # regenerate docs/REVEAL_CONSTANTS.json
    python tools/reveal_constants.py --check   # exit 1 if anything differs from the committed record

The record is generated, never hand-edited: every UPPERCASE module constant of engine/run.py
and engine/freeze_guard.py (regex patterns as their source string) and the sha256 of every
engine input. It does NOT run the engine and records no output: under the owner's freeze
order (constants committed + hashed, THEN the single engine run, THEN the reveal) output
hashes come only from the freeze run (scripts/freeze.sh). Reads no sealed path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "REVEAL_CONSTANTS.json"
RECORD_ID = "reveal-constants-v2-2026-10-24"
FIXTURE = "fixtures/UAC_Uncoded_12-01-2025-updated-NIH_ODSS.csv"
INPUTS = ("engine/run.py", "engine/__init__.py", "engine/inputs.py", "engine/freeze_guard.py",
          "scope/nitrd_pca_scopes_fy2025.v1.json", "cache/reporter/reporter_text.v1.jsonl", FIXTURE)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _ser(v):
    if isinstance(v, re.Pattern):
        return {"regex": v.pattern, "flags": int(v.flags)}
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, (tuple, list)):
        return [_ser(x) for x in v]
    if isinstance(v, (set, frozenset)):
        return sorted(_ser(x) for x in v)
    if isinstance(v, dict):
        return {str(k): _ser(x) for k, x in v.items()}
    raise TypeError(f"unserialisable constant type {type(v).__name__}")


def build() -> dict:
    sys.path.insert(0, str(ROOT))
    from engine import freeze_guard, run  # noqa: E402

    def consts(mod):
        return {k: _ser(getattr(mod, k)) for k in sorted(vars(mod))
                if k.lstrip("_").isupper() and not k.endswith("_PATH") and k != "ROOT"}
    return {
        "record_id": RECORD_ID,
        "vocabulary": run.VOCABULARY_ID,
        "synonyms_path": None if run.SYNONYMS_PATH is None else str(run.SYNONYMS_PATH),
        "decision_record": "docs/SYNONYM_DERIVATION.md (Decision 2026-10-24)",
        "freeze_order": "constants committed + hashed -> single engine run (scripts/freeze.sh) -> reveal",
        "constants": consts(run),
        "freeze_guard_constants": consts(freeze_guard),
        "input_sha256": {p: _sha(ROOT / p) for p in INPUTS},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    rec = json.dumps(build(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if a.write:
        OUT.write_text(rec, encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT)} sha256={hashlib.sha256(rec.encode()).hexdigest()}")
        return 0
    if not OUT.is_file() or OUT.read_text(encoding="utf-8") != rec:
        print("REVEAL CONSTANTS DRIFT: engine constants, inputs or outputs differ from the committed record",
              file=sys.stderr)
        return 1
    print(f"reveal constants match {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
