#!/usr/bin/env bash
# UAC NITRD build sweep. Usage: scripts/sweep.sh [--freeze]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROPOSALS="$ROOT/proposals/proposals.csv"
ARGS=(--tree "$ROOT" --fixture "$ROOT/fixtures/UAC_Uncoded_12-01-2025-updated-NIH_ODSS.csv")
if [[ -f "$PROPOSALS" ]]; then ARGS+=(--proposals "$PROPOSALS"); fi
if [[ "${1:-}" == "--freeze" ]]; then ARGS+=(--freeze); fi
exec python3 "$ROOT/tools/build_sweep.py" "${ARGS[@]}" --out "${SWEEP_RECORD:-/tmp/uac_nitrd_sweep_record.json}"
