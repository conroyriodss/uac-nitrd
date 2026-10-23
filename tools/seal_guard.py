#!/usr/bin/env python3
"""Entry 2 held-out seal guard (build-sweep gate).

Fails the build if the sealed held-out answer key (RCDC "File A", and the related
RCDC exports B and C) or any path to it appears anywhere in the buildable tree.

This file contains ONLY SHA-256 digests: no path, file name, header text or
category label from the sealed material. The guard never reads the sealed location.

Rules (each violation = exit 1):
  R1 byte-identity   any file whose SHA-256 equals a sealed or off-limits file
  R2 path-token      any token whose SHA-256 equals a sealed path/file-name/upload token
  R3 export-header   any line whose SHA-256 equals a header/preamble line of the RCDC exports
  R4 answer-pair     any line holding a fixture Appl ID AND a field that is an RCDC
                     final-category label (the answer format of File A/B)
Exit 2 = configuration error (fails closed): missing tree or fixture, or no Appl IDs.

Known limit: a hand-transcribed answer with no RCDC label (e.g. "11213742,AI") cannot
be told apart from a proposal by any content check. The protocol (freeze, then reveal)
and location isolation are the primary control; this guard is the tripwire.

Usage: python seal_guard.py --tree <repo root> --fixture <UAC fixture csv> [--self-test]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import tempfile
from pathlib import Path

SEAL_ID = "entry2-heldout-2026-10-23T19:18:20Z"
HELDOUT_SHA256 = "cbeab03e64f2dbc71a56caa68910dfabfb37dd6422284b1825ab462432b673ef"

BYTE_H = {
    "heldout": HELDOUT_SHA256,
    "fileA": "fa6940d2bfa4f2445e0eaee3eadf2c173dd69d03a0552e28cb8fe09ec2488830",
    "fileB": "7c9c57ab01f3a613f4baca582068bc5e3b8ebc672992d32a38338599da033cac",
    "fileC": "2a61dba5140397de80360836d97199aa02391f938e34916be6c09231a7265ae9",
}
TOKEN_H = {
    "10bdf1cd74574f530afb745ae4af5b51a3e606fcf749a0ce8c63232ac50f50a8",
    "119451efe5d68e033a9c063da4bd047659bfbf6261a70d04743926e00ad4dc70",
    "1a325ed84438c3052291ca15b2cc1a4d80a5e05001128eea7e608f4c51e55151",
    "75f49279a09392552ee100037f41bf7c852c0f73fcca65227df606d0b4cd3516",
    "88b6c135b4c4dab9d31096e9713d21d95f577ebb3803e9aa5fb8003e5af7c6a3",
    "af0a3dcb7c6dc3f694c2d30896560097003052aec93f3a8c679b66f8b8c32285",
    "b0a26947045609e000771ce0daa9b590a8db2508b16654bbddb8a6adbeae701d",
    "f40bdbb5899352d59329290fe58c4e49a19eba541a3df0b9b8505ea1124280dd",
    "fa7ff64da2c458022a572b2cbcd37e7a4600815ea57ce8050d065f2cd10dfef9",
}
LINE_H = {
    "07644e270d99a4279e849ce4399cde6790e375835cb1a91f58f9b8d2dfd86cec",
    "262bb7455babcfb799cd1786952b29f4a436a3a2dd72c2cff417437fd27edcc6",
    "480680bb14e8cca6666b9cc1e227a5d77abbfdeda31f959bacd0b135cec0b813",
    "49476df28523159c42e467abf64f73f1324d45e23cf50eba5b1aef536d6e3c93",
    "4aaddf6864f83d13b2af6d5f30ba2d2b00a9aa0b7283a3209ee90686d013ec22",
    "5402783e6ca0610a4e94a2656e5362ed68c577ca1510e2a465d2da3bc1c8055b",
    "7bddef1a4f085e7a0cbe3d9743178a5316e9deac48b90fedbbe3b922a1435ccb",
    "7ea9574f4ab7c6ea2ea284d5bfc78393012e8dd2e3ace175c713cda4ceb4e232",
    "7f7ad9507924bb929c6cea3da6a95891e37c0a18f2562d7f52876a30ef826dd3",
    "8352368d27ee2ac53ba700b757996fe5137cdc96648fa15056606eeb5c73d6d6",
    "cd6eddb656054fdf2d28a9123f51d20de8af015ba1bf0fd08e3fba8fb206e3b4",
    "ee701f942208a639f66eb441b0021a81ccc9205b8df041af465de2ec95e54590",
}
LABEL_H = {
    "060365b529a685412c6f239b88a5a505fc8cfed57148d6232a4839ef72fcf814",
    "275537acb7727580b682e7f9e2935e42e5f138d5378b15b750bad979334f5a0f",
    "39383d3711d6dfc4f40adcb284ec062fe5ddfa27c3cec5449bf32bb6d321a8cc",
    "3cfa7013b552afb4b324ec062a92e9b3eb7cda5d1d8aeb3f87a795871be7bb9d",
    "450f2f071238b9055c2c213115844028638bc0f8eb33eb2ca552bfd680154812",
    "6de37c5c31dfd3603074d6558e3a60fb2eee9afb7e30e2783ae3077b1ddebf1f",
    "8359b1b3e2c1d7e913d5427533e2244b2d11506ef5cffb261b234419ef7050b3",
    "a170cec0a64bb7326d23462e4f7e60860b82c4d186d6829b9fa9d10de8107835",
    "cc03d799172ebf56ff7dec621ad89d8508a408d9c26ac368666542f6d1f7f386",
    "d97504114c8fedfb6fc7c8cefc7f251f70d5cb1faf45e839d98d1ae3b41f8301",
    "e10afe19350e2b00f1da7aef0f446e89b96985b2382ce5db58a48af0a72adad4",
    "e36a626437775a09313d27265b18b8b40344509b843eea6e844463196658a21a",
    "f1fdf09745b7d92d9bee0221f13c35a949150b6e31c1034fc1928d57bf360f0a",
    "fb1fa53f152db4ad2a7b74aadd6c4fb69f7f350a7fcb9ad9820b63d96514ed9c",
}

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
TOKEN_RES = (re.compile(r"[A-Za-z0-9_\-]+"), re.compile(r"[A-Za-z0-9_.\-]+"))
FIELD_SPLIT = re.compile(r"[,\t|;\"]")
APPL_RE = re.compile(r"(?<!\d)\d{7,9}(?!\d)")


def _h(data: bytes | str) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def _norm_line(s: str) -> str:
    return s.replace("\ufeff", "").strip().rstrip(",").strip()


def fixture_appl_ids(fixture: Path) -> set[str]:
    text = fixture.read_bytes().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if "Appl ID" not in (reader.fieldnames or []):
        _cfg("fixture has no 'Appl ID' column")
    return {row["Appl ID"].strip() for row in reader if (row.get("Appl ID") or "").strip()}


def _cfg(msg: str):
    print(f"seal_guard CONFIG ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def scan_file(path: Path, rel: str, appl_ids: set[str]) -> list[dict]:
    out = []
    data = path.read_bytes()
    for name, digest in BYTE_H.items():
        if _h(data) == digest:
            out.append({"rule": "R1 byte-identity", "file": rel, "detail": f"identical to sealed/off-limits {name}"})
    # R2 on the relative path itself as well as the content.
    text = data.decode("utf-8", errors="ignore")
    for lineno, line in enumerate([rel] + text.splitlines(), start=0):
        where = "path" if lineno == 0 else f"line {lineno}"
        low = line.lower()
        toks = set()
        for rx in TOKEN_RES:
            toks.update(rx.findall(low))
        toks |= {t.lstrip("_") for t in toks}
        if any(_h(t) in TOKEN_H for t in toks):
            out.append({"rule": "R2 path-token", "file": rel, "detail": f"{where}: sealed path/file-name token"})
        if lineno == 0:
            continue
        if _h(_norm_line(line)) in LINE_H:
            out.append({"rule": "R3 export-header", "file": rel, "detail": f"{where}: RCDC export header/preamble line"})
        fields = {f.strip() for f in FIELD_SPLIT.split(line)}
        if any(_h(f) in LABEL_H for f in fields if f):
            if set(APPL_RE.findall(line)) & appl_ids:
                out.append({"rule": "R4 answer-pair", "file": rel,
                            "detail": f"{where}: fixture Appl ID together with an RCDC final-category label"})
    return out


def scan_tree(tree: Path, fixture: Path, self_path: Path | None = None) -> list[dict]:
    if not tree.is_dir():
        _cfg(f"tree not found: {tree}")
    if not fixture.is_file():
        _cfg(f"fixture not found: {fixture}")
    appl_ids = fixture_appl_ids(fixture)
    if not appl_ids:
        _cfg("fixture has no Appl IDs")
    findings = []
    for p in sorted(tree.rglob("*")):
        if not p.is_file() or any(part in SKIP_DIRS for part in p.relative_to(tree).parts):
            continue
        if self_path is not None and p.resolve() == self_path:
            continue  # the guard holds only digests; copies elsewhere are still scanned
        findings += scan_file(p, str(p.relative_to(tree)), appl_ids)
    return findings


def self_test() -> int:
    """Clean-tree check only (no false positive on a proposal-style line).

    Planted-violation tests for R1-R4 need the sealed preimages, so they are run once
    by the sealing session, outside the repo; results are in the seal record.
    """
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        fx = root / "fixture.csv"
        fx.write_text("FY,Category,Appl ID,suggestion_1\n2025,X,10000001,AI\n")
        (root / "tree").mkdir()
        (root / "tree" / "ok.py").write_text("print('proposal 10000001 -> AI')\n")
        assert scan_tree(root / "tree", fx) == [], "clean tree flagged"
    print("seal_guard self-test: clean-tree check PASS")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", type=Path)
    ap.add_argument("--fixture", type=Path)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if not a.tree or not a.fixture:
        _cfg("--tree and --fixture are required")
    findings = scan_tree(a.tree, a.fixture, Path(__file__).resolve())
    if a.json:
        print(json.dumps({"seal_id": SEAL_ID, "heldout_sha256": HELDOUT_SHA256, "findings": findings}, indent=2))
    for f in findings:
        print(f"SEAL VIOLATION [{f['rule']}] {f['file']}: {f['detail']}")
    print(f"seal_guard {SEAL_ID}: {'FAIL' if findings else 'CLEAN'} ({len(findings)} finding(s))")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
