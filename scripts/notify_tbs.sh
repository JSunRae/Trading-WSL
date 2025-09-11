#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./scripts/notify_tbs.sh "<project>" "<run_id>" "<used_prompt>" [status] [message]
# Notes:
#   - status defaults to "finished" (other examples: "waiting", "error")
#   - message is an optional human note
#   - Backward compatible with the older 3-arg form used by tasks

PROJECT=${1:-"${PWD##*/}"}
RUN_ID=${2:-"run-$(date +%s)"}
USED_PROMPT=${3:-"no prompt provided"}
STATUS=${4:-"finished"}
MESSAGE=${5:-""}
AGENT="${AGENT_NAME:-VsCode_Agent_bot}"

# Configurable knobs
TBS_NOTIFY_TIMEOUT=${TBS_NOTIFY_TIMEOUT:-5}
TBS_RETRY_ATTEMPTS=${TBS_RETRY_ATTEMPTS:-5}
TBS_QUEUE_DIR=${TBS_QUEUE_DIR:-"$(pwd)/artifacts/tbs_queue"}

if [[ -f ".env" ]]; then
  # Load only needed keys from .env, handling CRLF and optional quotes
  while IFS='=' read -r key value; do
    [[ -z "${key}" || "${key}" =~ ^# ]] && continue
    case "${key}" in
      TBS_URL|TBS_API_TOKEN|AGENT_NAME)
        # trim trailing CR if present (Windows line endings)
        value="${value%$'\r'}"
        # strip surrounding single/double quotes
        if [[ "${value}" == '"'*'"' ]]; then
          value="${value:1:${#value}-2}"
        elif [[ "${value}" == "'"*"'" ]]; then
          value="${value:1:${#value}-2}"
        fi
        export "${key}=${value}"
        ;;
    esac
  done < .env
fi

: "${TBS_URL:?missing TBS_URL}"
: "${TBS_API_TOKEN:?missing TBS_API_TOKEN}"

if [[ "${DEBUG:-0}" == "1" ]]; then
  printf 'Using TBS_URL=[%s]\n' "${TBS_URL}"
fi

# Helpers -------------------------------------------------------------------------------------------------
ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
mkdir -p "${TBS_QUEUE_DIR}"

build_payload() {
  local project="$1" run_id="$2" used_prompt="$3" status="$4" message="$5" agent="$6"
  IDMP_KEY="${run_id}:${status}"
  PAYLOAD=$(AGENT="${agent}" PROJECT="${project}" RUN_ID="${run_id}" USED_PROMPT="${used_prompt}" STATUS="${status}" MESSAGE="${message}" IDEMPOTENCY_KEY="${IDMP_KEY}" TS="$(ts)" \
    python3 - <<'PY'
import json, os
obj = {
  "agent": os.environ.get("AGENT", ""),
  "project": os.environ.get("PROJECT", ""),
  "run_id": os.environ.get("RUN_ID", ""),
  "status": os.environ.get("STATUS", ""),
  "message": os.environ.get("MESSAGE", ""),
  "used_prompt": os.environ.get("USED_PROMPT", ""),
  "idempotency_key": os.environ.get("IDEMPOTENCY_KEY", ""),
  "timestamp": os.environ.get("TS", ""),
}
print(json.dumps(obj, ensure_ascii=False))
PY
  )
}

post_with_retries() {
  # $1 JSON payload
  local payload="$1"
  local attempt=1
  local max_attempts=${TBS_RETRY_ATTEMPTS}
  local backoff=0.5
  while (( attempt <= max_attempts )); do
    # Use curl to capture HTTP status code separately
    local http
    http=$(curl -sS -m "${TBS_NOTIFY_TIMEOUT}" -o /tmp/tbs_resp.$$ -w "%{http_code}" -X POST "${TBS_URL}/v1/notify_finished" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer ${TBS_API_TOKEN}" \
      -d "${payload}" || true)
    if [[ "${http}" =~ ^2 ]]; then
      [[ "${DEBUG:-0}" == "1" ]] && echo "POST ok (HTTP ${http})" >&2
      rm -f /tmp/tbs_resp.$$ || true
      return 0
    fi
    [[ "${DEBUG:-0}" == "1" ]] && echo "POST failed (HTTP ${http}), attempt ${attempt}/${max_attempts}" >&2
    sleep "${backoff}"
    # Exponential-ish backoff with cap ~6s
    backoff=$(python3 - <<'PY' 2>/dev/null || echo 1
import os
b = float(os.environ.get("BACKOFF", "0.5"))
print(min(6.0, round(b*1.8,2)))
PY
)
    export BACKOFF="${backoff}"
    attempt=$((attempt+1))
  done
  return 1
}

queue_payload() {
  local payload="$1"
  local fname="${TBS_QUEUE_DIR}/tbs_${RUN_ID//\//-}_${STATUS}_$(date +%s)_$RANDOM.json"
  printf '%s' "${payload}" > "${fname}"
  echo "Queued notification -> ${fname}" >&2
}

flush_queue_if_possible() {
  # Try to send a handful of queued payloads if service is reachable
  if ! curl -fsS -m 2 "${TBS_URL}/health" >/dev/null; then
    return 0
  fi
  local count=0
  shopt -s nullglob
  for f in "${TBS_QUEUE_DIR}"/*.json; do
    (( count++ ))
    local p
    p=$(cat "$f")
    if post_with_retries "${p}"; then
      rm -f "$f" || true
    else
      # Leave the rest for later to avoid tight loops
      break
    fi
    # safety cap per run
    if (( count >= 50 )); then
      break
    fi
  done
}

# Quick preflight: ensure the service is reachable before posting; if not, try to auto-start if localhost.
preflight_or_queue() {
  if curl -fsS -m 3 "${TBS_URL}/health" > /dev/null; then
    return 0
  fi
  # Try to auto-start only if TBS_URL is localhost and this repo looks like the service repo
  local url_no_proto="${TBS_URL#http://}"
  url_no_proto="${url_no_proto#https://}"
  local host_port="${url_no_proto%%/*}"
  local host="${host_port%%:*}"
  local port="${host_port##*:}"
  if [[ "${host}" == "${port}" ]]; then port=8777; fi
  if [[ "${host}" =~ ^(127\.0\.0\.1|localhost|\[::1\])$ ]]; then
    local CURRENT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    local CANDIDATES=()
    [[ -n "${TBS_SERVICE_DIR:-}" ]] && CANDIDATES+=("${TBS_SERVICE_DIR}")
    CANDIDATES+=("${CURRENT_ROOT}")
    CANDIDATES+=("$(dirname "${CURRENT_ROOT}")/TelegramNotifications")
    local SERVICE_ROOT=""
    for c in "${CANDIDATES[@]}"; do
      if [[ -f "${c}/tbs_app.py" ]]; then SERVICE_ROOT="${c}"; break; fi
    done
    local APP_PATH="${SERVICE_ROOT}/tbs_app.py"
    local VENV_PY="${SERVICE_ROOT}/.venv/bin/python"
    local PYTHON_BIN="${VENV_PY}"; [[ -x "${PYTHON_BIN}" ]] || PYTHON_BIN="python3"
    if [[ -n "${SERVICE_ROOT}" && -f "${APP_PATH}" ]]; then
      local LOG_FILE="/tmp/tbs_app_${port}.log"
      [[ "${DEBUG:-0}" == "1" ]] && echo "Attempting to start local TBS service at ${host}:${port} using ${PYTHON_BIN} (root=${SERVICE_ROOT})" >&2
      (
        cd "${SERVICE_ROOT}"
        nohup "${PYTHON_BIN}" -m uvicorn tbs_app:app --host "${host}" --port "${port}" \
          >"${LOG_FILE}" 2>&1 & echo $! > "/tmp/tbs_app_${port}.pid"
      )
      for i in {1..30}; do
        if curl -fsS -m 1 "${TBS_URL}/health" > /dev/null; then
          [[ "${DEBUG:-0}" == "1" ]] && echo "TBS service is up at ${TBS_URL}" >&2
          return 0
        fi
        sleep 0.2
      done
      if ! curl -fsS -m 2 "${TBS_URL}/health" > /dev/null; then
        echo "Warning: Failed to start TBS service at ${TBS_URL}. Queuing notification locally." >&2
        return 1
      fi
    else
      echo "Warning: TBS service not reachable at ${TBS_URL}, and no local service app found. Queuing notification." >&2
      return 1
    fi
  else
    echo "Warning: TBS service not reachable at ${TBS_URL} (remote). Queuing notification for later delivery." >&2
    return 1
  fi
}

# Build payload first
build_payload "${PROJECT}" "${RUN_ID}" "${USED_PROMPT}" "${STATUS}" "${MESSAGE}" "${AGENT}"

# Try to flush any queued events opportunistically (best-effort)
flush_queue_if_possible || true

# Check service health (and maybe auto-start); if not available, enqueue and exit 0 (non-fatal)
if ! preflight_or_queue; then
  queue_payload "${PAYLOAD}"
  exit 0
fi

# Post with retries
if post_with_retries "${PAYLOAD}"; then
  echo "Notification delivered (status=${STATUS}, run_id=${RUN_ID})."
else
  echo "Warning: Delivery failed after retries. Queuing for later." >&2
  queue_payload "${PAYLOAD}"
fi

# Final opportunistic flush (in case service recovered mid-run)
flush_queue_if_possible || true

exit 0
