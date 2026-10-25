"""The engine's only gateway to the UAC fixture (input boundary 1).

The fixture is used for exactly one thing: the list of projects to propose for. The
engine's reasoning input is PROJECT TEXT from the public RePORTER record, read against
the verbatim NITRD PCA scopes and the AI cross-PCA guidance in scope/.

Not exposed, ever: the suggestion columns (NIH's internal assist output, which
correlates with the held-out answer), and the coder or administrative columns
(Category, Class Code, PCC, PO Name, Admin IC). The fixture's Project Title isn't
exposed either: titles come from RePORTER, so there is one text source. This file
must stay the only engine file that opens the fixture; build-sweep S6 enforces that.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

# Allow-list, not deny-list: a column added to the fixture later stays hidden by default.
ALLOWED_COLUMNS = ("Appl ID", "FY", "Project Number", "SubProj")


@dataclass(frozen=True)
class ProjectRef:
    """Identity only: enough to fetch the public RePORTER record, nothing about coding."""
    appl_id: int
    fy: int
    project_number: str
    subproj: str


def load_project_refs(fixture: Path) -> list[ProjectRef]:
    with fixture.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
        missing = [c for c in ALLOWED_COLUMNS if c not in header]
        if missing:
            raise ValueError(f"fixture lacks identity columns {missing}")
        idx = {c: header.index(c) for c in ALLOWED_COLUMNS}  # positions of allowed columns only
        refs = [ProjectRef(appl_id=int(row[idx["Appl ID"]].strip()), fy=int(row[idx["FY"]].strip()),
                           project_number=row[idx["Project Number"]].strip(),
                           subproj=row[idx["SubProj"]].strip())
                for row in reader if row and row[idx["Appl ID"]].strip()]
    if len({r.appl_id for r in refs}) != len(refs):
        raise ValueError("duplicate Appl ID in fixture")
    return refs


# The committed evaluation fixture. Used by the freeze guard to recognise the 480 evaluation
# projects in ANY fixture passed to the engine (identity column only).
EVALUATION_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "UAC_Uncoded_12-01-2025-updated-NIH_ODSS.csv"


def evaluation_appl_ids() -> frozenset[int]:
    return frozenset(r.appl_id for r in load_project_refs(EVALUATION_FIXTURE))
