#!/bin/bash
# SeeAct Web Agent 评测启动脚本

# ======== 基本配置 ========
TASK_FILE="./task_json_path"
OUTPUT_DIR="./output_dir"
BASE_URL="http://XX.XXX.XXX.XXX"
API_URL=""
API_KEY=""
MODEL_NAME="gpt-4o"

# ======== 浏览器端口 ========
PORTS="9223 9225 9227 9229 9231 9233 9235 9237"

# ======== 任务控制 ========
MAX_TASKS=1000
MAX_OP=50
MAX_CONTINUOUS_NO_OP=10
CHOICE_BATCH_SIZE=30

# ======== 执行 ========
cd "$(dirname "$0")"

python seeact.py \
  --task-file "${TASK_FILE}" \
  --output-dir "${OUTPUT_DIR}" \
  --base-url "${BASE_URL}" \
  --ports ${PORTS} \
  --max-tasks ${MAX_TASKS} \
  --max-op ${MAX_OP} \
  --max-continuous-no-op ${MAX_CONTINUOUS_NO_OP} \
  --choice-batch-size ${CHOICE_BATCH_SIZE} \
  --api-url "${API_URL}" \
  --api-key "${API_KEY}" \
  --model-name "${MODEL_NAME}"
