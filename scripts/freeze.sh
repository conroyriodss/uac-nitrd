#!/usr/bin/env bash
# UAC NITRD freeze: the ONLY sanctioned engine run on the 480 evaluation projects.
# Owner order (2026-10-24): constants committed + hashed, THEN this single run, THEN the reveal,
# with nothing run in between. Usage: scripts/freeze.sh   (no arguments)
#
#   1. refuses if proposals/ already holds engine output (single run, never repeated)
#   2. refuses unless the whole tree is clean and HEAD == origin/main (constants committed AND pushed)
#   3. refuses unless engine constants + input hashes == docs/REVEAL_CONSTANTS.json
#   4. the single engine run, writing proposals/ (freeze-guard-v1 allows it only here)
#   5. build_sweep --freeze in the same invocation: S1-S8; S8 re-executes the engine on the
#      fixture and on a scrambled copy in temp dirs and byte-compares them with step 4's file.
# On PASS it prints the hashes to commit, tag and seal-log BEFORE the reveal. On any failure
# after step 4, proposals/ stays as written; a re-run is refused and the failure is reported
# as a seal issue, not worked around.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
FIX="fixtures/UAC_Uncoded_12-01-2025-updated-NIH_ODSS.csv"
OUT="proposals"

for f in proposals.csv explanations.jsonl proposals.meta.json; do
  [[ -e "$OUT/$f" ]] && { echo "FREEZE REFUSED: $OUT/$f exists; the freeze run happens once" >&2; exit 3; }
done
git fetch -q origin
[[ -z "$(git status --porcelain)" ]] || { echo "FREEZE REFUSED: working tree not clean" >&2; git status --short >&2; exit 3; }
[[ "$(git rev-parse HEAD)" == "$(git rev-parse origin/main)" ]] || { echo "FREEZE REFUSED: HEAD is not origin/main (push first)" >&2; exit 3; }
python3 tools/reveal_constants.py --check

echo "== freeze run: commit $(git rev-parse HEAD) =="
UAC_NITRD_FREEZE_RUN=1 PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 \
  python3 engine/run.py --fixture "$FIX" --out-dir "$OUT" --offline
UAC_NITRD_FREEZE_RUN=1 SWEEP_RECORD="$OUT/FREEZE_SWEEP.json" bash scripts/sweep.sh --freeze

echo "== FREEZE COMPLETE: commit proposals/, tag, and seal-log these BEFORE the reveal =="
echo "engine_commit $(git rev-parse HEAD)"
sha256sum "$OUT/proposals.csv" "$OUT/explanations.jsonl" "$OUT/proposals.meta.json" docs/REVEAL_CONSTANTS.json
