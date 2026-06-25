#!/bin/bash
# ── NavEval: run eval.py ───────────────────────────────────────────
#
# Usage:
#   bash run_eval.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ====== 实验配置 ======
TEST_DIR="./task_path"
SAVE_DIR="./output"

MODE="both"           # filter | eval | both
MAX_WORKERS=8

# ====== LLM 配置 ======
API_KEY="api_key"
API_BASE="base_url"
SCRIBE_TOKEN=""          # Scribe API access token (用于 formatter 阶段访问 scribehow.com)
MODEL="claude-sonnet-4-5"

# ====== 运行 ======
SCRIBE_TOKEN="$SCRIBE_TOKEN" python "$SCRIPT_DIR/naveval.py" \
    --mode "$MODE" \
    --max-workers "$MAX_WORKERS" \
    --api-key "$API_KEY" \
    --api-base "$API_BASE" \
    --model "$MODEL" \
    --test-dir "$TEST_DIR" \
    --save-dir "$SAVE_DIR"
