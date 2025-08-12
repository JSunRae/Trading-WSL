#!/bin/bash
# IB Gateway Startup Script
# This script helps start and monitor IB Gateway

echo "🚀 IB Gateway Startup Helper"
echo "=============================="

# Check if Gateway is already running
check_gateway() {
    python3 -c "
import socket
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    result = sock.connect_ex(('127.0.0.1', 4002))
    sock.close()
    exit(0 if result == 0 else 1)
except:
    exit(1)
"
    return $?
}

# Start Gateway if not running
if check_gateway; then
    echo "✅ IB Gateway is already running on port 4002"
else
    echo "🔄 IB Gateway not detected. Please:"
    echo "   1. Start IB Gateway application manually"
    echo "   2. Login with your IB credentials"
    echo "   3. Select Paper Trading mode"
    echo "   4. Ensure API is enabled (port 4002)"
    echo ""
    echo "⏳ Waiting for Gateway to start..."
    
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
        exit 1
    fi
fi

echo ""
echo "🧪 Testing connection..."
python3 -c "
import asyncio
import sys

async def test_connection():
    try:
        from src.lib.ib_async_wrapper import IBAsync
        ib = IBAsync()
        success = await ib.connect('127.0.0.1', 4002, 1, timeout=10)
        if success:
            print('✅ Gateway connection successful!')
            await ib.disconnect()
            return True
        else:
            print('❌ Gateway connection failed')
            return False
    except Exception as e:
        print(f'❌ Connection test error: {e}')
        return False

result = asyncio.run(test_connection())
sys.exit(0 if result else 1)
"

if [ $? -eq 0 ]; then
    echo "🎉 IB Gateway is ready for trading!"
else
    echo "⚠️  Connection test failed. Check Gateway settings."
fi
