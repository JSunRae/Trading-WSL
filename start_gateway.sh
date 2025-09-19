#!/bin/bash
set -euo pipefail

# Set default Python path to project's virtual environment if available
DEFAULT_PYTHON="${PYTHON:-}"
if [[ -z "$DEFAULT_PYTHON" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [[ -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
    DEFAULT_PYTHON="$SCRIPT_DIR/.venv/bin/python"
  else
    DEFAULT_PYTHON="python3"
  fi
fi
export PYTHON="$DEFAULT_PYTHON"

echo "🚀 IB Gateway Startup Helper"
echo "=============================="

DEFAULT_HOST="${IB_HOST:-127.0.0.1}"
HOST="$DEFAULT_HOST"
USE_TWS="${IB_USE_TWS:-0}"
PREFER_LINUX="${IB_PREFER_LINUX:-1}"

if [[ -n "${IB_PORT:-}" ]]; then
  PORT="$IB_PORT"
else
  if [[ "$USE_TWS" == "1" ]]; then PORT="${IB_PAPER_PORT:-7497}"; else PORT="${IB_GATEWAY_PAPER_PORT:-4002}"; fi
fi

sanitize_port(){ local x="$1"; x="${x%%#*}"; echo "$x" | sed 's/[^0-9]//g'; }
ensure_port_valid(){ local n="$1"; [[ "$n" =~ ^[0-9]+$ ]] || { echo 0; return; }; if (( n>=1 && n<=65535 )); then echo "$n"; else echo 0; fi }
PORT="$(sanitize_port "$PORT")"
PV="$(ensure_port_valid "$PORT")"; if [[ "$PV" == "0" ]]; then PORT="${IB_GATEWAY_PAPER_PORT:-4002}"; else PORT="$PV"; fi

is_wsl=false; grep -qi microsoft /proc/version 2>/dev/null && is_wsl=true || true
if [[ -z "$HOST" ]]; then
  if $is_wsl; then HOST=$(awk '/nameserver/ {print $2; exit}' /etc/resolv.conf 2>/dev/null || echo 127.0.0.1); else HOST=127.0.0.1; fi
fi

echo "Target host: $HOST"; echo "Target port: $PORT";
if $is_wsl; then echo "Environment: WSL"; else echo "Environment: Native"; fi
if $is_wsl; then echo -e "\n🔎 Windows portproxy rules:"; powershell.exe -NoProfile -Command "netsh interface portproxy show v4tov4" 2>/dev/null | tr -d '\r' || true; fi

check_listener_once(){ "$PYTHON" - <<'PY'
import os,re,socket,sys
h=os.environ.get('CHK_HOST','127.0.0.1'); raw=os.environ.get('CHK_PORT','4002'); m=re.search(r"\d+",raw); p=int(m.group(0)) if m else 4002
# Clamp port to valid range to avoid :0 bug
if not (1 <= p <= 65535): p=4002
s=socket.socket(); s.settimeout(1.5)
try: r=s.connect_ex((h,p))
finally: s.close()
sys.exit(0 if r==0 else 1)
PY
}

has_nc(){ command -v nc >/dev/null 2>&1; }
can_nc(){ local h="$1" p="$2"; nc -z -w1 "$h" "$p" >/dev/null 2>&1; }

check_any(){
  # Get canonical connection plan
  local plan_json
  if ! plan_json="$("$PYTHON" scripts/get_ib_plan.py 2>/dev/null)"; then
    echo "⚠️  Failed to get canonical plan, falling back to legacy logic" >&2
    # Fallback to original logic
    local hosts=("$HOST"); $is_wsl && hosts+=("127.0.0.1")
    local ports=("$PORT" "${IB_GATEWAY_PAPER_PORT:-4002}" "${IB_PAPER_PORT:-7497}" 4000 4001)
    # Only include Windows/portproxy ports when explicitly allowed
    if [[ "${IB_ALLOW_WINDOWS:-0}" == "1" ]]; then
      ports+=(4003 4004)
    fi
  else
    # Parse JSON plan
    local plan_host plan_candidates
    plan_host=$(echo "$plan_json" | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin)['host'])")
    plan_candidates=$(echo "$plan_json" | "$PYTHON" -c "import sys,json; print(' '.join(map(str, json.load(sys.stdin)['candidates'])))")
    local hosts=("$plan_host")
    local ports=($plan_candidates)
    echo "📋 Using canonical plan: host=$plan_host, candidates=$plan_candidates"
  fi

  for h in "${hosts[@]}"; do
    for p in "${ports[@]}"; do
      if has_nc && can_nc "$h" "$p"; then HOST="$h" PORT="$p"; echo "✅ Detected listener $h:$p (nc)"; return 0; fi
      CHK_HOST="$h" CHK_PORT="$p" check_listener_once && HOST="$h" PORT="$p" && echo "✅ Detected listener $h:$p" && return 0 || true
    done
  done
  return 1
}

attempt_windows_autofind(){
  $is_wsl || return 0
  [[ "$PREFER_LINUX" == "1" ]] && return 0
  [[ -n "${IB_GATEWAY_START_CMD:-}" ]] && return 0
  # Prefer explicit Windows Gateway exe if provided
  if [[ -n "${IB_WINDOWS_GATEWAY_EXE:-}" ]]; then
    echo "� Launching Windows Gateway via IB_WINDOWS_GATEWAY_EXE"
    powershell.exe -NoProfile -Command "Start-Process -WindowStyle Minimized -FilePath \"${IB_WINDOWS_GATEWAY_EXE}\"" 2>/dev/null | tr -d '\r' || true
    return 0
  fi
  echo "�🔄 Attempting Windows auto-discovery"
  powershell.exe -NoProfile -Command "
    & {
      $base = '${IB_JTS_WINDOWS_DIR:-C:\\Jts}'
      if (Test-Path $base) {
        $gwDir = Join-Path $base 'ibgateway'
        $gw = Get-ChildItem -Path $gwDir -Directory -ErrorAction SilentlyContinue |
              Sort-Object Name -Descending | Select-Object -First 1
        if ($gw) {
          $exe = Join-Path $gw.FullName 'ibgateway.exe'
          Start-Process -WindowStyle Minimized -FilePath $exe
          'Launched:' + $exe
        } else {
          'NoInstallFound'
        }
      } else {
        'BaseNotFound:' + $base
      }
    }
  " 2>/dev/null | tr -d '\r' || true
}

interactive_launcher(){
  # Only show a prompt if attached to a TTY and interactive mode is enabled
  [[ -t 0 ]] || return 1
  if [[ "${IB_INTERACTIVE:-1}" != "1" ]]; then return 1; fi

  echo
  echo "No listener detected. Choose a launcher to start IB so you can log in:"
  echo "  1) Launch Linux Gateway (local)"
  if $is_wsl; then
    echo "  2) Launch Windows Gateway"
    echo "  3) Launch Windows TWS"
  fi
  echo "  s) Skip (I'll start it myself)"
  read -rp "Select [1${is_wsl:+/2/3}/s]: " choice

  case "$choice" in
    1)
      # Try explicit override first
      LNX_PATH="${IB_LINUX_GATEWAY_PATH:-}"
      if [[ -z "$LNX_PATH" ]]; then
        # Discover from base JTS directory
        local JTS_BASE="${IB_JTS_LINUX_DIR:-$HOME/Jts}"
        latest_dir=$(ls -1d "$JTS_BASE"/ibgateway/* 2>/dev/null | sort -V | tail -n1 || true)
        for cand in \
          "$latest_dir/ibgateway" \
          "$latest_dir/ibgateway.sh" \
          "$JTS_BASE/ibgateway/ibgateway" \
          "$JTS_BASE/ibgateway/ibgateway.sh"; do
          [[ -n "$cand" && -x "$cand" ]] && LNX_PATH="$cand" && break
        done
      fi
      if [[ -z "$LNX_PATH" ]]; then
        read -rp "Enter full path to Linux ibgateway launcher: " LNX_PATH
      fi
      if [[ -n "$LNX_PATH" ]]; then
        echo "🚀 Launching Linux Gateway: $LNX_PATH"
        ( nohup "$LNX_PATH" >/dev/null 2>&1 & ) || true
        return 0
      else
        echo "⚠️  No path provided; skipping."
        return 1
      fi
      ;;
    2)
      $is_wsl || { echo "⚠️  Windows options only available in WSL"; return 1; }
      if [[ -n "${IB_WINDOWS_GATEWAY_EXE:-}" ]]; then
        echo "🚀 Launching Windows Gateway via IB_WINDOWS_GATEWAY_EXE"
        powershell.exe -NoProfile -Command "Start-Process -WindowStyle Minimized -FilePath \"${IB_WINDOWS_GATEWAY_EXE}\"" 2>/dev/null | tr -d '\r' || true
      else
        echo "🚀 Launching Windows Gateway (from base ${IB_JTS_WINDOWS_DIR:-C:\\Jts})"
        powershell.exe -NoProfile -Command "
          $base = '${IB_JTS_WINDOWS_DIR:-C:\\Jts}'
          $gwDir = Join-Path $base 'ibgateway'
          $gw = Get-ChildItem -Path $gwDir -Directory -ErrorAction SilentlyContinue |
               Sort-Object Name -Descending | Select-Object -First 1
          if ($gw) { Start-Process -WindowStyle Minimized -FilePath (Join-Path $gw.FullName 'ibgateway.exe') }
        " 2>/dev/null | tr -d '\r' || true
      fi
      return 0
      ;;
    3)
      $is_wsl || { echo "⚠️  Windows options only available in WSL"; return 1; }
      if [[ -n "${IB_WINDOWS_TWS_EXE:-}" ]]; then
        echo "🚀 Launching Windows TWS via IB_WINDOWS_TWS_EXE"
        powershell.exe -NoProfile -Command "Start-Process -WindowStyle Minimized -FilePath \"${IB_WINDOWS_TWS_EXE}\"" 2>/dev/null | tr -d '\r' || true
      else
        echo "🚀 Launching Windows TWS (from base ${IB_JTS_WINDOWS_DIR:-C:\\Jts})"
        powershell.exe -NoProfile -Command "
          $base = '${IB_JTS_WINDOWS_DIR:-C:\\Jts}'
          $twsDir = Join-Path $base 'TWS'
          $tws = Get-ChildItem -Path $twsDir -Directory -ErrorAction SilentlyContinue |
                 Sort-Object Name -Descending | Select-Object -First 1
          if ($tws) { Start-Process -WindowStyle Minimized -FilePath (Join-Path $tws.FullName 'tws.exe') }
        " 2>/dev/null | tr -d '\r' || true
      fi
      return 0
      ;;
    s|S|"" )
      echo "ℹ️  Skipping autostart; waiting for manual launch..."
      return 1
      ;;
    *)
      echo "ℹ️  Unknown choice; skipping autostart."
      return 1
      ;;
  esac
}

launch_if_needed(){
  # Fast exit if already running
  if check_any; then echo "✅ Gateway already running"; return 0; fi

  # Launch via env command or Windows auto-discovery (WSL)
  if [[ -n "${IB_GATEWAY_START_CMD:-}" ]]; then
    echo "🔄 Launching via IB_GATEWAY_START_CMD"
    ( eval "$IB_GATEWAY_START_CMD" >/dev/null 2>&1 & ) || true
  else
    # Offer interactive launcher menu first (if allowed), otherwise best-effort autodiscovery (WSL)
    if ! interactive_launcher; then
      attempt_windows_autofind
    fi
  fi

  # Configurable wait with quick probes
  local TIMEOUT="${IB_GATEWAY_START_TIMEOUT:-180}"   # seconds (default: 180s for login time)
  local INTERVAL="${IB_GATEWAY_CHECK_INTERVAL:-2}"  # seconds between checks (default: 2s)
  local start_ts
  start_ts=$(date +%s)
  echo "⏳ Waiting for listener (max ${TIMEOUT}s)..."
  echo "💡 Please log into the IB Gateway window that should have opened..."
  while true; do
    if check_any; then
      local now
      now=$(date +%s)
      local took=$(( now - start_ts ))
      echo "✅ Up after ${took}s"
      # Post-listener grace period to allow user to complete secondary login (e.g., account selection/2FA)
      # Configure via IB_POST_LISTENER_GRACE (seconds). Set to 0 to disable. Default: 30s.
      local POST_GRACE
      POST_GRACE="${IB_POST_LISTENER_GRACE:-30}"
      if [[ "$POST_GRACE" =~ ^[0-9]+$ ]] && (( POST_GRACE > 0 )); then
        echo "⏳ Grace period: waiting ${POST_GRACE}s so you can finish logging in (second screen)..."
        sleep "$POST_GRACE"
      fi
      return 0
    fi
    local now
    now=$(date +%s)
    if (( now - start_ts >= TIMEOUT )); then
      echo "❌ Timeout after ${TIMEOUT}s" >&2
      return 1
    fi
    sleep "${INTERVAL}"
  done
}

launch_if_needed || exit 1

echo -e "\n🧪 API connectivity test (handshake-based readiness)..."
export HOST PORT  # ensure Python sees resolved values; prevents :0 fallback
"$PYTHON" - <<'PY'
import asyncio,os,sys
HOST=os.environ.get('HOST') or '127.0.0.1'
try:
  PORT=int(os.environ.get('PORT') or '4002')
  if not (1 <= PORT <= 65535): PORT=4002
except Exception:
  PORT=4002
CID=int(os.environ.get('IB_CLIENT_ID','2011') or 2011)

async def test_port(host, port, cid):
  try:
    from src.lib.ib_async_wrapper import IBAsync
    ib=IBAsync(); ok=await ib.connect(host,port,cid,timeout=8,fallback=False)
    if ok:
      await ib.disconnect(); return port
  except Exception:
    pass
  return None

async def main():
  # Try multiple possible ports
  test_ports = [PORT, 4002, 4000, 4001, 7497]
  test_ports = list(dict.fromkeys(test_ports))  # Remove duplicates while preserving order

  for port in test_ports:
    print(f"Testing {HOST}:{port}...")
    result = await test_port(HOST, port, CID)
    if result:
      print(f"✅ Connected to IB @ {HOST}:{result} (clientId={CID})")
      return 0

  print(f"❌ API handshake failed for all tested ports: {test_ports}")
  print("💡 Make sure IB Gateway is logged in and API is enabled in settings")
  return 2

raise SystemExit(asyncio.run(main()))
PY
res=$?; if [[ $res -eq 0 ]]; then echo "🎉 IB Gateway ready."; else echo "⚠️  API test failed ($res)"; fi
