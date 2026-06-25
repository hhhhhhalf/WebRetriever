#!/bin/bash
# Agent-E Web Agent 多进程评测启动脚本

# ======== 基本配置 ========
TASK_FILE="./task_path"
OUTPUT_DIR="./output_dir"
BASE_URL="http://XX.XXX.XXX.XXX"
LLM_CONFIG="./agents_llm_config.json"
LLM_CONFIG_KEY="openai_gpt"

# ======== 浏览器端口 ========
PORTS="9223 9225 9227 9229 9231 9233 9235 9237 9239 9241 9243 9245 9247 9249 9251 9253"

# ======== 任务控制 ========
MAX_TASKS=0              # 0 表示不限制
USE_KEYPOINTS=false      # true=协议2(带关键路径), false=协议1(不带关键路径)
WAIT_TIME=5

# ======== 执行 ========
cd "$(dirname "$0")"

KEYPOINTS_FLAG=""
if [ "${USE_KEYPOINTS}" = "true" ]; then
  KEYPOINTS_FLAG="--use-keypoints"
fi

python agent_e.py \
  --task-file "${TASK_FILE}" \
  --output-dir "${OUTPUT_DIR}" \
  --base-url "${BASE_URL}" \
  --llm-config "${LLM_CONFIG}" \
  --llm-config-key "${LLM_CONFIG_KEY}" \
  --ports ${PORTS} \
  --max-tasks ${MAX_TASKS} \
  --wait-time ${WAIT_TIME} \
  --take-screenshots \
  ${KEYPOINTS_FLAG}
