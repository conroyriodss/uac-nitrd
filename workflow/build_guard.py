"""Task 1 build read guard: GUARD_ID = task1-build-read-guard-v1 (spec: docs/TASK1_READ_GUARD_SPEC.md).

The FY2021-seeded fingerprint builder and the FY2026 forecast run install a Guard at process start.
From then on, in that process:

* any open / listdir / scandir / copy of a DENIED path (rules D1-D7) raises BuildGuardError, whether it
  comes through Guard.read_bytes or through plain open(), pandas, etc. (a sys.addaudithook hook, which
  cannot be removed once installed);
* importing a native file reader (pyarrow's file readers, polars, duckdb, fastparquet) raises, because
  those read files without Python audit events (the known gap of the hook);
* Guard.read_bytes is the only sanctioned reader: it also refuses anything outside the allow-listed
  roots and records the sha256 of every file read;
* RePORTER request bodies (check_reporter_body, rule D8) and warehouse SQL (check_sql, rule D9) are
  checked before they are sent;
* write_manifest() writes READ_MANIFEST.json: every file read and every request, with hashes.

Mode "build": FY2019-2021 only; label fields only for FY2021. Mode "forecast": FY2026 identity + text
only, never a label field.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from workflow import sealed  # noqa: E402  (seal markers + the FY2024 text snapshot location)

GUARD_ID = "task1-build-read-guard-v1"
ROOT = Path(__file__).resolve().parents[1]
SEED_ROOT = Path(os.environ.get("UAC_NITRD_TASK1_SEED_ROOT", "/Volumes/users/conroyri/nitrd_hackathon_v1_raw/task1_seed_v1"))

DENIED: tuple[tuple[str, Path, str], ...] = (
    ("D1", ROOT / "build" / "universe" / "fy2022.csv", "FY2022 per-award NITRD flags"),
    ("D1", ROOT / "build" / "universe" / "fy2023.csv", "FY2023 per-award NITRD flags"),
    ("D2", ROOT / "build" / "universe" / "fy2024_identity.csv", "scoring-year identity"),
    ("D3", ROOT / "build" / "baseline", "carry-forward predictions from FY2022/23 labels"),
    ("D3", ROOT / "dev" / "baseline", "carry-forward backtests on FY2022/23"),
    ("D4", ROOT / "build" / "reconciliation", "per-award FY2021-23 NITRD flags"),
    ("D5", ROOT / "fixtures" / "UAC_Uncoded_12-01-2025-updated-NIH_ODSS.csv", "FY2025 480 NITRD awards"),
    ("D5", ROOT / "cache" / "reporter", "FY2025 480 text cache"),
    ("D7", sealed.SNAPSHOT_DIR, "FY2024 scoring-year text"),
    ("D7", ROOT / "corpus", "FY2024 synonym corpus text"),
)

# Native readers that bypass Python's audit events (spec, enforcement layer 2).
BANNED_MODULES = (
    "pyarrow.parquet", "pyarrow.csv", "pyarrow.json", "pyarrow.fs", "pyarrow.dataset", "pyarrow.feather",
    "pyarrow.orc", "polars", "duckdb", "fastparquet",
)

MODES = {
    "build": {"fys": (2019, 2020, 2021), "label_fys": (2021,)},
    "forecast": {"fys": (2026,), "label_fys": ()},
}
# RePORTER criteria / fields that carry RCDC labels.
LABEL_CRITERIA = ("spending_categories",)
LABEL_FIELD_RE = re.compile(r"^(spending_?categor|terms$|pref_?terms$)", re.IGNORECASE)
SQL_TABLES_OK = ("nitrd_hackathon_v1_exporter_projects", "nitrd_hackathon_v1_exporter_abstracts")
SQL_LABEL_COLUMNS = ("nih_spending_cats", "project_terms")


class BuildGuardError(RuntimeError):
    """A guarded process tried to read something the Task 1 builder must never read."""


def _resolve(path) -> Path | None:
    if isinstance(path, int):
        return None  # an already-open file descriptor
    if isinstance(path, bytes):
        path = os.fsdecode(path)
    try:
        return Path(os.path.realpath(os.fspath(path)))
    except (TypeError, ValueError):
        return None


def denied_rule(path, extra: tuple = ()) -> str | None:
    """Rule ID if path is (inside) a denied location, else None. Symlinks and '..' are resolved first.

    D6 (sealed data: File A, the FY2025 held-out file, the FY2024 key and its supplements) is any
    location holding a seal marker file, or below one (workflow/sealed.py); its path is never named in
    the tree."""
    p = _resolve(path)
    if p is None:
        return None
    for rule, target, _why in DENIED + tuple(extra):
        t = Path(os.path.realpath(target))
        if p == t or t in p.parents:
            return rule
    if sealed.in_sealed_dir(p):
        return "D6"
    return None


def _banned(name: str) -> bool:
    return any(name == m or name.startswith(m + ".") for m in BANNED_MODULES)


class _BannedReaderFinder:
    """First entry on sys.meta_path: refuses banned native readers for every import mechanism
    (import statement, importlib.import_module, __import__), before any finder can locate them."""

    def find_spec(self, name, path=None, target=None):
        if _banned(name):
            raise BuildGuardError(f"{GUARD_ID}: import of native file reader {name!r} refused")
        return None


class Guard:
    def __init__(self, mode: str, roots: tuple = (), extra_denied: tuple = ()):
        if mode not in MODES:
            raise ValueError(f"mode must be one of {sorted(MODES)}")
        self.mode = mode
        self.roots = tuple(Path(os.path.realpath(r)) for r in roots)
        self.extra = tuple(extra_denied)
        self.files: dict[str, str] = {}
        self.requests: list[dict] = []
        self.sql: list[dict] = []
        self.installed = False

    # --- layer 2: process audit hook ---------------------------------------------------------------
    def install(self) -> Guard:
        loaded = [m for m in BANNED_MODULES if m in sys.modules]
        if loaded:
            raise BuildGuardError(f"{GUARD_ID}: native readers already imported: {loaded}")
        sys.meta_path.insert(0, _BannedReaderFinder())
        sys.addaudithook(self._hook)
        self.installed = True
        return self

    def _hook(self, event: str, args: tuple) -> None:
        if event == "import":
            name = args[0] if args else ""
            if _banned(str(name)):
                raise BuildGuardError(f"{GUARD_ID}: import of native file reader {name!r} refused")
            return
        if event in ("open", "os.listdir", "os.scandir"):
            targets = args[:1]
        elif event == "shutil.copyfile":
            targets = args[:2]
        else:
            return
        for t in targets:
            rule = denied_rule(t, self.extra)
            if rule:
                raise BuildGuardError(f"{GUARD_ID} {rule}: {event} of {t!s} refused")

    # --- layer 1: allow-listed loader --------------------------------------------------------------
    def read_bytes(self, path) -> bytes:
        p = _resolve(path)
        rule = denied_rule(p, self.extra)
        if rule:
            raise BuildGuardError(f"{GUARD_ID} {rule}: read of {path!s} refused")
        if not any(p == r or r in p.parents for r in self.roots):
            raise BuildGuardError(f"{GUARD_ID} ALLOW: {path!s} is outside the allow-listed roots")
        data = p.read_bytes()
        self.files[str(p)] = hashlib.sha256(data).hexdigest()
        return data

    # --- layer 3: RePORTER request bodies ----------------------------------------------------------
    def check_reporter_body(self, body: dict) -> None:
        rules = MODES[self.mode]
        crit = body.get("criteria") or {}
        fys = crit.get("fiscal_years")
        if not fys or any(int(fy) not in rules["fys"] for fy in fys):
            raise BuildGuardError(f"{GUARD_ID} D8: fiscal_years {fys} not within {rules['fys']} ({self.mode})")
        wants_labels = any(k in crit for k in LABEL_CRITERIA) or any(
            LABEL_FIELD_RE.search(re.sub(r"(?<!^)(?=[A-Z])", "_", f)) for f in body.get("include_fields") or ()
        )
        if wants_labels and any(int(fy) not in rules["label_fys"] for fy in fys):
            raise BuildGuardError(f"{GUARD_ID} D8: label fields requested for {fys} ({self.mode})")

    def record_request(self, body: dict, n_records: int) -> None:
        canon = json.dumps(body, sort_keys=True, separators=(",", ":"))
        self.requests.append({"sha256": hashlib.sha256(canon.encode()).hexdigest(), "records": n_records,
                              "fiscal_years": body.get("criteria", {}).get("fiscal_years")})

    # --- layer 4: warehouse SQL --------------------------------------------------------------------
    def check_sql(self, sql: str) -> None:
        s = " ".join(sql.split()).lower()
        if self.mode != "build":
            raise BuildGuardError(f"{GUARD_ID} D9: no warehouse reads in {self.mode} mode")
        tables = set(re.findall(r"\b(?:from|join)\s+([\w.`]+)", s))
        bad = [t for t in tables if not t.strip("`").endswith(SQL_TABLES_OK)]
        if bad:
            raise BuildGuardError(f"{GUARD_ID} D9: table(s) {bad} not allowed")
        if "nitrd_cores" in s:
            raise BuildGuardError(f"{GUARD_ID} D9: nitrd_cores holds reserved-year membership")
        if re.search(r"\bor\b", s):
            raise BuildGuardError(f"{GUARD_ID} D9: OR is not allowed (the year restriction must be conjunctive)")
        if not re.search(r"\bfile_fy\s*<=\s*2021\b", s) or not re.search(r"cast\(\s*(\w+\.)?fy\s+as\s+int\s*\)\s*(<=\s*2021|=\s*20(19|20|21)|between\s+2019\s+and\s+2021)\b", s):
            raise BuildGuardError(f"{GUARD_ID} D9: statement is not restricted to file_fy <= 2021 and fy <= 2021")
        if any(c in s for c in SQL_LABEL_COLUMNS) and not re.search(r"cast\(\s*(\w+\.)?fy\s+as\s+int\s*\)\s*=\s*2021\b", s):
            raise BuildGuardError(f"{GUARD_ID} D9: label columns may be read for FY2021 only")

    def record_sql(self, sql: str, n_rows: int) -> None:
        self.sql.append({"sha256": hashlib.sha256(" ".join(sql.split()).encode()).hexdigest(), "rows": n_rows})

    # --- layer 5: read manifest --------------------------------------------------------------------
    def manifest(self) -> dict:
        return {"guard_id": GUARD_ID, "mode": self.mode, "hook_installed": self.installed,
                "written_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "allowed_roots": [str(r) for r in self.roots], "files": dict(sorted(self.files.items())),
                "reporter_requests": self.requests, "sql_statements": self.sql}

    def write_manifest(self, path) -> str:
        data = (json.dumps(self.manifest(), indent=1, sort_keys=True) + "\n").encode()
        Path(path).write_bytes(data)
        return hashlib.sha256(data).hexdigest()
