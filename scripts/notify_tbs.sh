#!/usr/bin/env bash
set -euo pipefail

# Usage: ./scripts/notify_tbs.sh "<project>" "<run_id>" "<used_prompt>"
# Falls back to env AGENT_NAME=VsCode_Agent_bot

PROJECT=${1:-"${PWD##*/}"}
RUN_ID=${2:-"run-$(date +%s)"}
USED_PROMPT=${3:-"no prompt provided"}
AGENT="${AGENT_NAME:-VsCode_Agent_bot}"

if [[ -f ".env" ]]; then
  # shellcheck disable=SC2046
  export $(grep -E '^(TBS_URL|TBS_API_TOKEN|AGENT_NAME)=' .env | xargs -d '\n')
fi

: "${TBS_URL:?missing TBS_URL}"
: "${TBS_API_TOKEN:?missing TBS_API_TOKEN}"

curl -sS -X POST "${TBS_URL}/v1/notify_finished" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TBS_API_TOKEN}" \
  -d @- <<EOF
{
  "agent": "${AGENT}",
  "project": "${PROJECT}",
  "run_id": "${RUN_ID}",
  "used_prompt": "${USED_PROMPT}"
}
EOF
echo