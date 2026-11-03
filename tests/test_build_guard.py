"""task1-build-read-guard-v1: the Task 1 builder cannot read reserved-year labels, File A or sealed data.

Every check that installs the audit hook runs in a subprocess (a hook cannot be removed). No test reads
the content of a denied file: the guarded snippets only try to open it, and the hook refuses first.
"""

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow import build_guard as bg  # noqa: E402
from workflow import sealed  # noqa: E402

REAL_DENIED = [
    ("D1", ROOT / "build/universe/fy2022.csv"),
    ("D1", ROOT / "build/universe/fy2023.csv"),
    ("D2", ROOT / "build/universe/fy2024_identity.csv"),
    ("D3", ROOT / "build/baseline/carry_forward_fy2024.predictions.csv"),
    ("D3", ROOT / "dev/baseline/carry_forward_backtest.json"),
    ("D4", ROOT / "build/reconciliation/qvr_crosswalk_fy2021_2023.csv"),
    ("D5", ROOT / "fixtures/UAC_Uncoded_12-01-2025-updated-NIH_ODSS.csv"),
    ("D5", ROOT / "cache/reporter/reporter_text.v1.jsonl"),
    ("D7", sealed.SNAPSHOT_DIR),
    ("D7", ROOT / "corpus/fy2024_independent.v1.jsonl.gz"),
]


def _run(body: str, *, install: bool = True, extra: str = "()", env_path: str = "") -> subprocess.CompletedProcess:
    head = f"""
        import sys, os, json
        sys.path.insert(0, {str(ROOT)!r})
        from workflow import build_guard as bg
        g = bg.Guard("build", roots=(), extra_denied={extra})
        if {install!r}:
            g.install()
        def attempt(fn):
            try:
                fn()
                print("ALLOWED")
            except bg.BuildGuardError as e:
                print("REFUSED", e)
            except OSError as e:
                print("OSERROR", type(e).__name__)
    """
    code = textwrap.dedent(head) + textwrap.dedent(body)
    env = None
    if env_path:
        import os
        env = {**os.environ, "PYTHONPATH": env_path}
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, env=env)


@pytest.mark.parametrize("rule,path", REAL_DENIED, ids=[f"{r}-{p.name}" for r, p in REAL_DENIED])
def test_denied_rule_matches(rule, path):
    assert bg.denied_rule(path) == rule


@pytest.mark.parametrize("rule,path", REAL_DENIED, ids=[f"{r}-{p.name}" for r, p in REAL_DENIED])
def test_plain_open_and_listdir_refused_by_hook(rule, path):
    r = _run(f"""
        p = {str(path)!r}
        attempt(lambda: open(p, "rb").close())
        attempt(lambda: os.listdir(p))
        attempt(lambda: g.read_bytes(p))
    """)
    lines = r.stdout.splitlines()
    assert len(lines) == 3, r.stdout + r.stderr
    assert all(line.startswith("REFUSED") and f" {rule}:" in line for line in lines), r.stdout


def test_pandas_read_refused_by_hook():
    pytest.importorskip("pandas")
    r = _run(f"""
        import pandas as pd
        attempt(lambda: pd.read_csv({str(ROOT / 'build/universe/fy2022.csv')!r}, nrows=1))
    """)
    assert r.stdout.startswith("REFUSED") and " D1:" in r.stdout, r.stdout + r.stderr


def test_sealed_marker_location_refused(tmp_path):
    """D6: anything at or below a directory holding a seal marker, however it is reached."""
    vol = tmp_path / "vol"
    (vol / "sub").mkdir(parents=True)
    (vol / sealed.SEAL_MARKERS[0]).write_text("{}")
    key = vol / "sub" / "key.csv"
    key.write_text("appl_id,cat329\n1,1\n")
    link = tmp_path / "plain.csv"
    link.symlink_to(key)
    assert bg.denied_rule(key) == "D6" and bg.denied_rule(vol) == "D6" and bg.denied_rule(link) == "D6"
    r = _run(f"""
        attempt(lambda: open({str(key)!r}, "rb").close())
        attempt(lambda: os.listdir({str(vol)!r}))
        attempt(lambda: open({str(link)!r}, "rb").close())
    """)
    assert [line.split()[:2] for line in r.stdout.splitlines()] == [["REFUSED", bg.GUARD_ID]] * 3, r.stdout + r.stderr
    assert all(" D6:" in line for line in r.stdout.splitlines())


def test_symlink_and_dotdot_refused(tmp_path):
    link = tmp_path / "innocent.csv"
    link.symlink_to(ROOT / "build/universe/fy2022.csv")
    dotdot = ROOT / "workflow" / ".." / "build" / "universe" / "fy2023.csv"
    r = _run(f"""
        attempt(lambda: open({str(link)!r}, "rb").close())
        attempt(lambda: open({str(dotdot)!r}, "rb").close())
    """)
    assert [line.split()[0] for line in r.stdout.splitlines()] == ["REFUSED", "REFUSED"], r.stdout + r.stderr


def test_fault_injection_hook_is_what_blocks(tmp_path):
    """Same synthetic denied file: refused with the hook installed, readable without it."""
    f = tmp_path / "synthetic_denied.csv"
    f.write_text("appl_id,cat329\n1,0\n")
    extra = repr((("DX", str(f), "synthetic"),))
    body = f"attempt(lambda: open({str(f)!r}, 'rb').close())\n"
    on, off = _run(body, extra=extra), _run(body, install=False, extra=extra)
    assert on.stdout.startswith("REFUSED") and " DX:" in on.stdout, on.stdout + on.stderr
    assert off.stdout.strip() == "ALLOWED", off.stdout + off.stderr


def test_native_reader_import_refused(tmp_path):
    """A stand-in pyarrow package: importing its file readers is refused once the guard is installed."""
    pkg = tmp_path / "pyarrow"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "parquet.py").write_text("")
    (tmp_path / "polars.py").write_text("")
    r = _run("""
        import importlib
        attempt(lambda: importlib.import_module("pyarrow.parquet"))
        attempt(lambda: importlib.import_module("polars"))
        attempt(lambda: __import__("pyarrow.parquet"))
        def stmt():
            import polars  # noqa: F401
        attempt(stmt)
        attempt(lambda: importlib.import_module("pyarrow"))
        attempt(lambda: importlib.import_module("json"))
    """, env_path=str(tmp_path))
    got = [line.split()[0] for line in r.stdout.splitlines()]
    assert got == ["REFUSED"] * 4 + ["ALLOWED", "ALLOWED"], r.stdout + r.stderr


def test_install_refuses_if_native_reader_already_loaded(tmp_path):
    (tmp_path / "duckdb.py").write_text("")
    code = f"import sys; sys.path.insert(0, {str(ROOT)!r}); import duckdb; from workflow import build_guard as bg; bg.Guard('build').install()"
    import os
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(tmp_path)}, timeout=60)
    assert r.returncode != 0 and "native readers already imported" in r.stderr


def test_allow_list_loader(tmp_path):
    ok = tmp_path / "seed" / "fy2021.jsonl"
    ok.parent.mkdir()
    ok.write_bytes(b'{"a":1}\n')
    outside = tmp_path / "elsewhere.txt"
    outside.write_text("x")
    g = bg.Guard("build", roots=(ok.parent,))
    assert g.read_bytes(ok) == b'{"a":1}\n'
    with pytest.raises(bg.BuildGuardError, match="ALLOW"):
        g.read_bytes(outside)
    with pytest.raises(bg.BuildGuardError, match="D1"):
        bg.Guard("build", roots=(ROOT,)).read_bytes(ROOT / "build/universe/fy2022.csv")
    assert list(g.manifest()["files"].values()) == [__import__("hashlib").sha256(b'{"a":1}\n').hexdigest()]


@pytest.mark.parametrize("mode,body,ok", [
    ("build", {"criteria": {"fiscal_years": [2021]}, "include_fields": ["ApplId", "AbstractText"]}, True),
    ("build", {"criteria": {"fiscal_years": [2019]}, "include_fields": ["ApplId", "AbstractText"]}, True),
    ("build", {"criteria": {"fiscal_years": [2021]}, "include_fields": ["ApplId", "SpendingCategories"]}, True),
    ("build", {"criteria": {"fiscal_years": [2020]}, "include_fields": ["ApplId", "SpendingCategoriesDesc"]}, False),
    ("build", {"criteria": {"fiscal_years": [2022]}, "include_fields": ["ApplId", "AbstractText"]}, False),
    ("build", {"criteria": {"fiscal_years": [2021, 2024]}}, False),
    ("build", {"criteria": {"fiscal_years": [2020], "spending_categories": {"values": [329]}}}, False),
    ("build", {"criteria": {"fiscal_years": [2019]}, "include_fields": ["Terms"]}, False),
    ("build", {"criteria": {}}, False),
    ("forecast", {"criteria": {"fiscal_years": [2026]}, "include_fields": ["ApplId", "AbstractText"]}, True),
    ("forecast", {"criteria": {"fiscal_years": [2026]}, "include_fields": ["ApplId", "SpendingCategories"]}, False),
    ("forecast", {"criteria": {"fiscal_years": [2026], "spending_categories": {"values": [329]}}}, False),
    ("forecast", {"criteria": {"fiscal_years": [2026]}, "include_fields": ["PrefTerms"]}, False),
    ("forecast", {"criteria": {"fiscal_years": [2021]}}, False),
])
def test_reporter_body_checks(mode, body, ok):
    g = bg.Guard(mode)
    if ok:
        g.check_reporter_body(body)
    else:
        with pytest.raises(bg.BuildGuardError, match="D8"):
            g.check_reporter_body(body)


T = "users.conroyri.nitrd_hackathon_v1_exporter_projects"


@pytest.mark.parametrize("sql,ok", [
    (f"SELECT application_id, nih_spending_cats FROM {T} p WHERE p.file_fy <= 2021 AND CAST(p.fy AS INT) = 2021", True),
    (f"SELECT application_id, project_title FROM {T} WHERE file_fy <= 2021 AND CAST(fy AS INT) BETWEEN 2019 AND 2021", True),
    (f"SELECT application_id, nih_spending_cats FROM {T} WHERE file_fy <= 2021 AND CAST(fy AS INT) <= 2021", False),
    (f"SELECT application_id FROM {T} WHERE CAST(fy AS INT) <= 2021", False),
    (f"SELECT application_id FROM {T} WHERE file_fy <= 2021 AND CAST(fy AS INT) <= 2021 OR 1=1", False),
    (f"SELECT application_id FROM {T} WHERE file_fy <= 2023 AND CAST(fy AS INT) <= 2023", False),
    ("SELECT * FROM users.conroyri.nitrd_hackathon_v1_nitrd_cores WHERE file_fy <= 2021 AND CAST(fy AS INT) <= 2021", False),
    (f"SELECT * FROM {T} p JOIN users.conroyri.nitrd_hackathon_v1_review_requests r ON 1=1 WHERE p.file_fy <= 2021 AND CAST(p.fy AS INT) <= 2021", False),
])
def test_sql_checks(sql, ok):
    g = bg.Guard("build")
    if ok:
        g.check_sql(sql)
    else:
        with pytest.raises(bg.BuildGuardError, match="D9"):
            g.check_sql(sql)
    with pytest.raises(bg.BuildGuardError, match="D9"):
        bg.Guard("forecast").check_sql(sql)


def test_manifest_round_trip(tmp_path):
    g = bg.Guard("forecast")
    g.record_request({"criteria": {"fiscal_years": [2026]}}, 500)
    sha = g.write_manifest(tmp_path / "READ_MANIFEST.json")
    m = json.loads((tmp_path / "READ_MANIFEST.json").read_text())
    assert m["guard_id"] == bg.GUARD_ID and m["reporter_requests"][0]["records"] == 500
    assert sha == __import__("hashlib").sha256((tmp_path / "READ_MANIFEST.json").read_bytes()).hexdigest()
