#!/usr/bin/env bash
set -euo pipefail

# Usage: ./scripts/notify_tbs.sh "<project>" "<run_id>" "<used_prompt>"
# Falls back to env AGENT_NAME=VsCode_Agent_bot

PROJECT=${1:-"${PWD##*/}"}
RUN_ID=${2:-"run-$(date +%s)"}
USED_PROMPT=${3:-"no prompt provided"}
AGENT="${AGENT_NAME:-VsCode_Agent_bot}"

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

# Quick preflight: ensure the service is reachable before posting
if ! curl -fsS -m 3 "${TBS_URL}/health" > /dev/null; then
  # Try to auto-start only if TBS_URL is localhost and this repo looks like the service repo
  url_no_proto="${TBS_URL#http://}"
  url_no_proto="${url_no_proto#https://}"
  host_port="${url_no_proto%%/*}"
  host="${host_port%%:*}"
  port="${host_port##*:}"

  # Default port if none was provided in TBS_URL
  if [[ "${host}" == "${port}" ]]; then
    port=8777
  fi

  if [[ "${host}" =~ ^(127\.0\.0\.1|localhost|\[::1\])$ ]]; then
    # Try locations in order: explicit TBS_SERVICE_DIR, current repo root, sibling 'TelegramNotifications'
    CURRENT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    CANDIDATES=()
    [[ -n "${TBS_SERVICE_DIR:-}" ]] && CANDIDATES+=("${TBS_SERVICE_DIR}")
    CANDIDATES+=("${CURRENT_ROOT}")
    CANDIDATES+=("$(dirname "${CURRENT_ROOT}")/TelegramNotifications")

    SERVICE_ROOT=""
    for c in "${CANDIDATES[@]}"; do
      if [[ -f "${c}/tbs_app.py" ]]; then
        SERVICE_ROOT="${c}"
        break
      fi
    done

    APP_PATH="${SERVICE_ROOT}/tbs_app.py"
    VENV_PY="${SERVICE_ROOT}/.venv/bin/python"
    PYTHON_BIN="${VENV_PY}"
    [[ -x "${PYTHON_BIN}" ]] || PYTHON_BIN="python3"

    if [[ -n "${SERVICE_ROOT}" && -f "${APP_PATH}" ]]; then
      LOG_FILE="/tmp/tbs_app_${port}.log"
      [[ "${DEBUG:-0}" == "1" ]] && echo "Attempting to start local TBS service at ${host}:${port} using ${PYTHON_BIN} (root=${SERVICE_ROOT})" >&2
      (
        cd "${SERVICE_ROOT}"
        nohup "${PYTHON_BIN}" -m uvicorn tbs_app:app --host "${host}" --port "${port}" \
          >"${LOG_FILE}" 2>&1 & echo $! > "/tmp/tbs_app_${port}.pid"
      )

      # Wait until healthy (max ~6s)
      for i in {1..30}; do
        if curl -fsS -m 1 "${TBS_URL}/health" > /dev/null; then
          [[ "${DEBUG:-0}" == "1" ]] && echo "TBS service is up at ${TBS_URL}" >&2
          break
        fi
        sleep 0.2
      done

      # Final health check
      if ! curl -fsS -m 2 "${TBS_URL}/health" > /dev/null; then
        echo "Error: Failed to start TBS service at ${TBS_URL}. See log: ${LOG_FILE}" >&2
        { echo "--- tbs_app last 80 lines ---"; tail -n 80 "${LOG_FILE}" 2>/dev/null || true; } >&2
        exit 7
      fi
    else
      echo "Error: TBS service not reachable at ${TBS_URL}, and no service app found. Set TBS_SERVICE_DIR to the TelegramNotifications repo (containing tbs_app.py) or start the service manually." >&2
      exit 7
    fi
  else
    echo "Error: TBS service not reachable at ${TBS_URL}. It is not localhost; won't auto-start. Update TBS_URL or ensure remote service is running." >&2
    exit 7
  fi
fi

PAYLOAD=$(AGENT="${AGENT}" PROJECT="${PROJECT}" RUN_ID="${RUN_ID}" USED_PROMPT="${USED_PROMPT}" \
  python3 - <<'PY'
import json, os, sys
obj = {
  "agent": os.environ.get("AGENT", ""),
  "project": os.environ.get("PROJECT", ""),
  "run_id": os.environ.get("RUN_ID", ""),
  "used_prompt": os.environ.get("USED_PROMPT", ""),
}
print(json.dumps(obj, ensure_ascii=False))
PY
)

curl -sS -X POST "${TBS_URL}/v1/notify_finished" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TBS_API_TOKEN}" \
  -d "${PAYLOAD}"
echo
