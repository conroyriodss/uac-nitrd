"""Synthetic projects for engine tests (freeze-guard-v1: tests never run the engine on the 480).

IDs 91000001-91000008 are not evaluation projects; the text is written here, not taken from
any project. Same record shape as cache/reporter/reporter_text.v1.jsonl.
"""
import csv
import json
from pathlib import Path

TEXTS = {
    91000001: ("Machine learning for cardiac imaging",
               "We apply machine learning and artificial intelligence to cardiac imaging."),
    91000002: ("A data repository",
               "Large-scale data management, curation and analysis of biomedical data."),
    91000003: ("Securing health records", "Cybersecurity and privacy for electronic health records."),
    91000004: ("Surgical robots", "Robotics and autonomous systems for surgical assistance."),
    91000005: ("Training program", "Education and workforce training in computing for scientists."),
    91000006: ("Wireless sensing", "Wireless networking and spectrum for body sensors."),
    91000007: ("Bench biology", "We study protein folding in yeast."),
    91000008: None,  # not found in RePORTER -> abstain
}
IDS = tuple(TEXTS)


def make(dirpath: Path) -> tuple[Path, Path]:
    """Write a synthetic fixture (identity columns + two decoy columns) and cache; return paths."""
    dirpath.mkdir(parents=True, exist_ok=True)
    fx, cache = dirpath / "synthetic_fixture.csv", dirpath / "synthetic_cache.jsonl"
    with fx.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["FY", "Appl ID", "SubProj", "Project Number", "Project Title", "PCC"])
        for i in IDS:
            w.writerow([2025, i, "", f"1R01ZZ{i % 1000000:06d}-01", "decoy title", "DECOY"])
    lines = []
    for i, t in TEXTS.items():
        if t is None:
            rec = {"abstract": None, "appl_id": i, "award_amount": None, "fiscal_year": None, "project_num": None,
                   "public_health_relevance": None, "specific_aims": None, "status": "not_found", "title": None}
        else:
            rec = {"abstract": t[1], "appl_id": i, "award_amount": 100000 + i % 1000, "fiscal_year": 2025,
                   "project_num": f"1R01ZZ{i % 1000000:06d}-01", "public_health_relevance": None,
                   "specific_aims": None, "status": "found", "title": t[0]}
        lines.append(json.dumps(rec, sort_keys=True, separators=(",", ":")))
    cache.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return fx, cache
