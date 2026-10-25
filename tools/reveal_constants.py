"""Pre-reveal record of every engine constant, input hash and output hash.

    python tools/reveal_constants.py --write   # regenerate docs/REVEAL_CONSTANTS.json
    python tools/reveal_constants.py --check   # exit 1 if anything differs from the committed record

The record is generated, never hand-edited: every UPPERCASE module constant of engine/run.py
(regex patterns as their source string), the sha256 of every engine input, and the sha256 of
the engine's proposals/explanations on the fixture (run offline in a temp dir). Reads no
sealed path and no fixture column beyond what engine/inputs.py allows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "REVEAL_CONSTANTS.json"
RECORD_ID = "reveal-constants-v1-2026-10-24"
FIXTURE = "fixtures/UAC_Uncoded_12-01-2025-updated-NIH_ODSS.csv"
INPUTS = ("engine/run.py", "engine/__init__.py", "engine/inputs.py",
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
    from engine import run  # noqa: E402
    consts = {k: _ser(getattr(run, k)) for k in sorted(vars(run))
              if k.lstrip("_").isupper() and not k.endswith("_PATH") and k != "ROOT"}
    with tempfile.TemporaryDirectory() as d:
        r = subprocess.run([sys.executable, str(ROOT / "engine" / "run.py"), "--fixture", str(ROOT / FIXTURE),
                            "--out-dir", d, "--offline"], capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"engine failed: {r.stderr}")
        outs = {n: _sha(Path(d) / n) for n in ("proposals.csv", "explanations.jsonl")}
        meta = json.loads((Path(d) / "proposals.meta.json").read_text(encoding="utf-8"))
    return {
        "record_id": RECORD_ID,
        "vocabulary": meta["vocabulary"],
        "synonyms_added": meta["synonyms_added"],
        "synonyms_path": None if run.SYNONYMS_PATH is None else str(run.SYNONYMS_PATH),
        "decision_record": "docs/SYNONYM_DERIVATION.md (Decision 2026-10-24)",
        "constants": consts,
        "input_sha256": {p: _sha(ROOT / p) for p in INPUTS},
        "output_sha256_on_fixture": outs,
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
