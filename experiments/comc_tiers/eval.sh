#!/bin/bash
# =============================================================================
# COMC confidence-tier calibration evaluation script for the ASI-Evolve framework.
# Mirrors the contract used by the engineer: the candidate code lives at
# ${STEP_DIR}/code; we score it offline and write ${STEP_DIR}/results.json.
# =============================================================================
set -e
set -o pipefail

STEP_DIR="$(pwd)"
# evaluator.py lives next to this script, so derive EXPERIMENT_DIR from the
# script location — robust both for real runs (cwd = steps/step_N) and for a
# manual smoke test (cwd = experiment dir).
EXPERIMENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Allow a manual smoke test:  bash eval.sh path/to/initial_program
SRC_CODE_FILE="${1:-${STEP_DIR}/code}"
RESULT_JSON="${STEP_DIR}/results.json"
LOG_FILE="${STEP_DIR}/eval.log"
EVALUATOR_PY="${EXPERIMENT_DIR}/evaluator.py"

handle_error() {
    local exit_code=$?
    echo "ERROR: Evaluation failed (Exit Code: $exit_code)" >&2
    cat > "$RESULT_JSON" << EOF
{
    "success": false,
    "eval_score": 0.0,
    "combined_score": 0.0,
    "eval_time": 0.0,
    "temp": {"error": "Evaluation failed. See eval.log for details."}
}
EOF
    exit 0
}
trap 'if [ $? -ne 0 ]; then handle_error; fi' EXIT

echo "=== COMC Tiers Evaluation ===" > "$LOG_FILE"
echo "Step Directory: ${STEP_DIR}" >> "$LOG_FILE"
echo "Candidate: ${SRC_CODE_FILE}" >> "$LOG_FILE"
echo "Evaluator: ${EVALUATOR_PY}" >> "$LOG_FILE"

if [ ! -f "$SRC_CODE_FILE" ]; then
    echo "ERROR: Source code file not found: ${SRC_CODE_FILE}" >> "$LOG_FILE"
    exit 1
fi
if [ ! -f "$EVALUATOR_PY" ]; then
    echo "ERROR: Evaluator script not found: ${EVALUATOR_PY}" >> "$LOG_FILE"
    exit 1
fi

python3 "$EVALUATOR_PY" "$SRC_CODE_FILE" "$RESULT_JSON" >> "$LOG_FILE" 2>&1

if [ -f "$RESULT_JSON" ]; then
    eval_score=$(python3 -c "import json; print(json.load(open('$RESULT_JSON')).get('eval_score', 0.0))")
    echo "  F1 (eval_score): ${eval_score}"
fi
exit 0
