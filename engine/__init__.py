"""UAC NITRD proposal engine: assist proposals for SME review (see engine/README.md)."""
from __future__ import annotations

import json
from pathlib import Path

# Boundary 2: every proposals file ships with this label. It must match build-sweep S7 exactly.
OUTPUT_LABEL = ("ASSIST PROPOSAL FOR SME REVIEW. Not a reproduction of the official UAC method "
                "(no UAC fingerprints exist). The 'most specific PCA' rule is NITRD's published "
                "guidance applied to project text, not a claim of official correctness.")


def write_meta(proposals_csv: Path, *, scope_set: str, scope_sha256: str, text_source: str, **extra) -> Path:
    """Write proposals.meta.json next to the proposals CSV."""
    meta = {
        "label": OUTPUT_LABEL,
        "official_uac_method": False,
        "suggestion_columns_read": False,
        "reasoning_inputs": {"project_text": text_source, "scope_set": scope_set,
                             "scope_sha256": scope_sha256,
                             "guidance": "NITRD AI cross-PCA examples + 'most specific PCA' rule"},
        **extra,
    }
    out = proposals_csv.with_name("proposals.meta.json")
    out.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return out
