#!/bin/bash
set -euo pipefail

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
PORT="$(sanitize_port "$PORT")"

is_wsl=false; grep -qi microsoft /proc/version 2>/dev/null && is_wsl=true || true
if [[ -z "$HOST" ]]; then
  if $is_wsl; then HOST=$(awk '/nameserver/ {print $2; exit}' /etc/resolv.conf 2>/dev/null || echo 127.0.0.1); else HOST=127.0.0.1; fi
fi

echo "Target host: $HOST"; echo "Target port: $PORT";
if $is_wsl; then echo "Environment: WSL"; else echo "Environment: Native"; fi
if $is_wsl; then echo -e "\n🔎 Windows portproxy rules:"; powershell.exe -NoProfile -Command "netsh interface portproxy show v4tov4" 2>/dev/null | tr -d '\r' || true; fi

check_listener_once(){ python - <<'PY'
import os,re,socket,sys
h=os.environ.get('CHK_HOST','127.0.0.1'); raw=os.environ.get('CHK_PORT','0'); m=re.search(r"\d+",raw); p=int(m.group(0)) if m else 0
s=socket.socket(); s.settimeout(1.5)
try: r=s.connect_ex((h,p))
finally: s.close()
sys.exit(0 if r==0 else 1)
PY
}

has_nc(){ command -v nc >/dev/null 2>&1; }
can_nc(){ local h="$1" p="$2"; nc -z -w1 "$h" "$p" >/dev/null 2>&1; }

check_any(){
  local hosts=("$HOST"); $is_wsl && hosts+=("127.0.0.1")
  local ports=("$PORT" "${IB_GATEWAY_PAPER_PORT:-4002}" "${IB_PAPER_PORT:-7497}" 4003)
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
  echo "🔄 Attempting Windows auto-discovery"
  powershell.exe -NoProfile -Command '
    & {
      $gw = Get-ChildItem -Path "C:\Jts\ibgateway" -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending | Select-Object -First 1
      if ($gw) {
        Start-Process -WindowStyle Minimized -FilePath (Join-Path $gw.FullName "ibgateway.exe")
        "Launched:" + $gw.FullName
      } else {
        "NoInstallFound"
      }
    }
  ' 2>/dev/null | tr -d '\r' || true
}

launch_if_needed(){ if check_any; then echo "✅ Gateway already running"; return 0; fi; if [[ -n "${IB_GATEWAY_START_CMD:-}" ]]; then echo "🔄 Launching via IB_GATEWAY_START_CMD"; ( eval "$IB_GATEWAY_START_CMD" >/dev/null 2>&1 & ) || true; else attempt_windows_autofind; fi; echo "⏳ Waiting for listener..."; for i in {1..70}; do if check_any; then echo "✅ Up (after $i attempts)"; return 0; fi; sleep 3; done; echo "❌ Timeout" >&2; return 1; }

launch_if_needed || exit 1

echo -e "\n🧪 API connectivity test..."
python - <<'PY'
import asyncio,os,sys
HOST=os.environ.get('HOST'); PORT=int(os.environ.get('PORT','0') or 0); CID=int(os.environ.get('IB_CLIENT_ID','2011') or 2011)
async def main():
  try:
    from src.lib.ib_async_wrapper import IBAsync
    ib=IBAsync(); ok=await ib.connect(HOST,PORT,CID,timeout=12)
    if ok:
      print(f"✅ Connected to IB @ {HOST}:{PORT} (clientId={CID})"); await ib.disconnect(); return 0
    print('❌ API connect returned False'); return 2
  except Exception as e:
    print(f"❌ API test error: {e}"); return 3
raise SystemExit(asyncio.run(main()))
PY
res=$?; if [[ $res -eq 0 ]]; then echo "🎉 IB Gateway ready."; else echo "⚠️  API test failed ($res)"; fi
