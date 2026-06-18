#!/bin/bash
# =============================================================================
# COMC confidence-tier calibration evaluation script for the ASI-Evolve framework.
# Mirrors the contract used by the engineer: the candidate code lives at
# ${STEP_DIR}/code; we score it offline and write ${STEP_DIR}/results.json.
# =============================================================================
set -e
set -o pipefail

# The framework runs this via `bash eval.sh`, but `python3` may be NATIVE Windows
# Python (Git Bash / MSYS), which cannot open MSYS paths like /c/Users/...; it
# would write results.json to a different physical path than bash reads, and the
# error trap would then clobber a good score with the 0.0 fallback. cygpath -m
# yields a forward-slash mixed path (C:/Users/...) that both the shell and a
# Python string handle. On Linux cygpath is absent and the path passes through.
to_native() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }

# Resolve a Python interpreter robustly. On Windows the bare `python3` may be a
# disabled Microsoft Store stub; `python` is the real interpreter. The evaluator
# is pure-stdlib, so any Python 3 works; fall back to python3 (e.g. on Linux).
if command -v python >/dev/null 2>&1; then PY=python; else PY=python3; fi

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

"$PY" "$(to_native "$EVALUATOR_PY")" "$(to_native "$SRC_CODE_FILE")" "$(to_native "$RESULT_JSON")" >> "$LOG_FILE" 2>&1

if [ -f "$RESULT_JSON" ]; then
    eval_score=$("$PY" -c "import json; print(json.load(open('$(to_native "$RESULT_JSON")')).get('eval_score', 0.0))")
    echo "  F1 (eval_score): ${eval_score}"
fi
exit 0
