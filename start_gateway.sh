#!/bin/bash
# IB Gateway Startup Script
# This script helps start and monitor IB Gateway

echo "🚀 IB Gateway Startup Helper"
echo "=============================="

# Resolve host/port from env (default to Gateway Paper)
# WSL2 note: Windows host isn't 127.0.0.1 from Linux. Try nameserver IP as fallback.
HOST=${IB_HOST:-}
PORT=${IB_PORT:-}

# Helper: sanitize a port string (strip comments and non-digits)
sanitize_port() {
    local x="$1"
    # Drop everything after a '#'
    x="${x%%#*}"
    # Remove all non-digits
    x="$(echo "$x" | sed 's/[^0-9]//g')"
    echo "$x"
}

# Detect WSL and compute Windows host IP (first nameserver)
is_wsl=false
if grep -qi "microsoft" /proc/version 2>/dev/null; then
    is_wsl=true
fi

if [ -z "$HOST" ]; then
    if [ "$is_wsl" = true ]; then
        # Common WSL2 Windows host IP via resolv.conf nameserver
        WIN_HOST=$(awk '/nameserver/ {print $2; exit}' /etc/resolv.conf 2>/dev/null)
        HOST=${WIN_HOST:-127.0.0.1}
    else
        HOST=127.0.0.1
    fi
fi

# Default ports if not provided
if [ -z "$PORT" ]; then
    if [ "${IB_USE_TWS:-0}" = "1" ]; then
        PORT="$(sanitize_port "${IB_PAPER_PORT:-7497}")"
    else
        PORT="$(sanitize_port "${IB_GATEWAY_PAPER_PORT:-4002}")"
    fi
else
    PORT="$(sanitize_port "$PORT")"
fi

# Optional: Show Windows portproxy rules (WSL-only) for quick diagnostics
if [ "$is_wsl" = true ]; then
    echo "\n🔎 Checking Windows portproxy rules (if any):"
    powershell.exe -NoProfile -Command "netsh interface portproxy show v4tov4" 2>/dev/null | tr -d '\r' || true
fi

# Check if Gateway is already running
check_once() {
    local h="$1" p="$2"
    PYBIN=${VENV_PY:-./.venv/bin/python}
    "$PYBIN" - <<'PY'
import os, re, socket, sys
h = os.environ.get('CHK_HOST')
raw = os.environ.get('CHK_PORT', '0') or '0'
# Extract first integer from the string safely (tolerate inline comments)
m = re.search(r"\d+", raw)
p = int(m.group(0)) if m else 0
s = socket.socket()
s.settimeout(2)
try:
    r = s.connect_ex((h, p))
finally:
    s.close()
sys.exit(0 if r == 0 else 1)
PY
}

check_gateway() {
    # Try a small matrix of host/port candidates
    CANDIDATE_HOSTS=("$HOST")
    [ "$is_wsl" = true ] && CANDIDATE_HOSTS+=("127.0.0.1")
    # Include explicit Windows host if provided
    [ -n "$WIN_HOST" ] && CANDIDATE_HOSTS+=("$WIN_HOST")
    # Enumerate Windows IPv4 addresses (best-effort) to cover Wi-Fi/Ethernet/vEthernet
    if [ "$is_wsl" = true ]; then
        mapfile -t WIN_IPS < <(powershell.exe -NoProfile -Command "Get-NetIPAddress -AddressFamily IPv4 | Select-Object -ExpandProperty IPAddress" 2>/dev/null | tr -d '\r' | sed 's/\s\+//g' | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' || true)
        for ip in "${WIN_IPS[@]}"; do
            # Skip 127.0.0.1
            [ "$ip" = "127.0.0.1" ] && continue
            CANDIDATE_HOSTS+=("$ip")
        done
    fi

    # Build sanitized candidate port list
    CANDIDATE_PORTS=()
    sp="$(sanitize_port "$PORT")"; [ -n "$sp" ] && CANDIDATE_PORTS+=("$sp")
    for v in "${IB_GATEWAY_PAPER_PORT:-4002}" "${IB_GATEWAY_LIVE_PORT:-4001}" "${IB_PAPER_PORT:-7497}" "${IB_LIVE_PORT:-7496}"; do
        sp="$(sanitize_port "$v")"
        [ -n "$sp" ] && CANDIDATE_PORTS+=("$sp")
    done

    for h in "${CANDIDATE_HOSTS[@]}"; do
        for p in "${CANDIDATE_PORTS[@]}"; do
            CHK_HOST="$h" CHK_PORT="$p" check_once
            if [ $? -eq 0 ]; then
                HOST="$h"; PORT="$p"; export HOST PORT
                echo "✅ Detected listener at $HOST:$PORT"
                return 0
            fi
        done
    done
    return 1
}

# Start Gateway if not running
if check_gateway; then
    echo "✅ IB Gateway is already running on ${HOST}:${PORT}"
else
    if [ -n "${IB_GATEWAY_START_CMD}" ]; then
        echo "🔄 Attempting to auto-start IB Gateway via IB_GATEWAY_START_CMD"
        echo "    ${IB_GATEWAY_START_CMD}"
        # Try to launch Windows app from WSL (non-blocking)
        ( eval "${IB_GATEWAY_START_CMD}" >/dev/null 2>&1 & ) || true
        sleep 3
    else
        echo "🔄 IB Gateway not detected. Please:"
        echo "   1. Start IB Gateway/TWS on Windows"
        echo "   2. Login and enable API"
        echo "   3. Ensure correct port: ${PORT}"
        echo "   4. If using TWS, set IB_PORT=7497 and IB_USE_TWS=1 in test env"
        echo "   5. In Gateway/TWS API settings:"
        echo "      - Enable 'ActiveX and Socket Clients'"
        echo "      - Uncheck 'Allow connections from localhost only'"
        echo "      - Or add your WSL IP to Trusted IPs: $(awk '/nameserver/ {print $2; exit}' /etc/resolv.conf 2>/dev/null)"
        echo ""
    fi

    echo "⏳ Waiting for Gateway to start on ${HOST}:${PORT}..."

    # Wait for Gateway to become available
    for i in {1..60}; do
        if check_gateway; then
            echo "✅ Gateway is now running!"
            break
        fi
        echo "   Waiting... ($i/60)"
        sleep 5
    done

    if ! check_gateway; then
    echo "❌ Gateway startup timeout. Please start Gateway manually."
        echo "   Hint: If IBKR binds only on 127.0.0.1, WSL cannot reach it."
        echo "   Fix: Uncheck 'Allow connections from localhost only' and/or add Trusted IP."
        exit 1
    fi
fi

echo ""
echo "🧪 Testing connection..."
PYBIN=${VENV_PY:-./.venv/bin/python}
"$PYBIN" - <<PY
import asyncio,sys,os
HOST=os.environ.get('HOST')
PORT=int(os.environ.get('PORT','0') or '0')

async def test_connection():
    try:
        from src.lib.ib_async_wrapper import IBAsync
        ib = IBAsync()
        ok = await ib.connect(HOST, PORT, 1, timeout=10)
        if ok:
            print('✅ Gateway connection successful!')
            await ib.disconnect()
            return True
        print('❌ Gateway connection failed')
        return False
    except Exception as e:
        print(f'❌ Connection test error: {e}')
        return False

raise SystemExit(0 if asyncio.run(test_connection()) else 1)
PY

if [ $? -eq 0 ]; then
    echo "🎉 IB Gateway is ready for trading!"
else
    echo "⚠️  Connection test failed. Check Gateway settings."
fi
