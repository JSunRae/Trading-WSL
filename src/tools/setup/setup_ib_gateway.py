#!/usr/bin/env python3
"""
IB Gateway Setup and Configuration Guide

This script helps you set up and configure IB Gateway for automated trading
without needing TWS (Trader Workstation) to be open.

IB Gateway is the preferred method for automated trading as it:
- Runs headless (no GUI required)
- More stable for automated connections
- Lower resource usage
- Better for server/cloud deployments
- Doesn't require TWS to be running

Ports:
- Gateway Paper Trading: 4002
- Gateway Live Trading: 4001
- TWS Paper Trading: 7497 (requires TWS open)
- TWS Live Trading: 7496 (requires TWS open)
"""

import json
import os
from pathlib import Path
from typing import Any


class IBGatewaySetup:
    """Interactive Brokers Gateway setup and configuration"""

    def __init__(self):
        self.gateway_config = {
            "paper_trading": {
                "port": 4002,
                "description": "IB Gateway Paper Trading",
                "recommended": True,
            },
            "live_trading": {
                "port": 4001,
                "description": "IB Gateway Live Trading",
                "recommended": False,
            },
        }

    def print_setup_guide(self):
        """Print comprehensive IB Gateway setup guide"""
        print("=" * 80)
        print("🚀 INTERACTIVE BROKERS GATEWAY SETUP GUIDE")
        print("=" * 80)

        print("\n📋 WHAT IS IB GATEWAY?")
        print("IB Gateway is a lightweight, headless version of TWS designed for")
        print("automated trading. It provides API access without the full GUI.")

        print("\n✅ BENEFITS OF IB GATEWAY:")
        print("• No need to keep TWS open")
        print("• More stable for automated trading")
        print("• Lower memory and CPU usage")
        print("• Better for server deployments")
        print("• Handles reconnections automatically")
        print("• Designed specifically for API access")

        print("\n🔧 SETUP STEPS:")

        print("\n1️⃣  DOWNLOAD IB GATEWAY:")
        print("   • Go to: https://www.interactivebrokers.com/en/trading/ib-api.php")
        print("   • Download 'IB Gateway' (not TWS)")
        print("   • Install following the setup wizard")

        print("\n2️⃣  CONFIGURE IB GATEWAY:")
        print("   • Run IB Gateway from your applications")
        print("   • Login with your IB credentials")
        print("   • Choose 'Paper Trading' for testing")
        print("   • Navigate to: Configure → API → Settings")

        print("\n3️⃣  API CONFIGURATION:")
        print("   • ✅ Enable ActiveX and Socket Clients")
        print("   • ✅ Allow connections from localhost (127.0.0.1)")
        print("   • Socket Port: 4002 (Paper) or 4001 (Live)")
        print("   • ✅ Download open orders on connection")
        print("   • ❌ Read-Only API (must be unchecked)")
        print("   • Client ID: Any unique number (default: 1)")

        print("\n4️⃣  SECURITY SETTINGS:")
        print("   • Trusted IPs: 127.0.0.1 (localhost)")
        print("   • You can add specific IPs if running remotely")
        print("   • Consider using IB's built-in authentication")

        print("\n5️⃣  CONNECTION SETTINGS:")
        print("   Paper Trading:")
        print("   • Host: 127.0.0.1")
        print(f"   • Port: {self.gateway_config['paper_trading']['port']}")
        print(
            f"   • Description: {self.gateway_config['paper_trading']['description']}"
        )
        print("   Live Trading:")
        print("   • Host: 127.0.0.1")
        print(f"   • Port: {self.gateway_config['live_trading']['port']}")
        print(f"   • Description: {self.gateway_config['live_trading']['description']}")

        print("\n⚠️  IMPORTANT NOTES:")
        print("• Gateway must be running before starting your trading scripts")
        print("• Use Paper Trading (port 4002) for testing")
        print("• Live Trading (port 4001) requires funded account")
        print("• Gateway will automatically reconnect if disconnected")
        print("• Keep your IB account credentials secure")

        print("\n🧪 TESTING CONNECTION:")
        print("After setup, test your connection with:")
        print("""
python3 -c "
import asyncio
from src.lib.ib_async_wrapper import IBAsync, Stock

async def test():
    ib = IBAsync()
    success = await ib.connect('127.0.0.1', 4002, 1)
    print(f'Gateway Connection: {\"✅ Success\" if success else \"❌ Failed\"}')
    if success:
        contract = Stock('AAPL')
        data = await ib.req_historical_data(contract, '1 D', '5 min')
        print(f'Data Test: {\"✅ Success\" if data is not None else \"❌ Failed\"}')
        await ib.disconnect()

asyncio.run(test())
"
        """)

        print("\n🚨 TROUBLESHOOTING:")
        print("Connection Failed? Check:")
        print("• Is IB Gateway running and logged in?")
        print("• Is API enabled in Gateway settings?")
        print("• Is the correct port configured (4002 for paper)?")
        print("• Is 127.0.0.1 in trusted IPs?")
        print("• Is Read-Only API disabled?")
        print("• Is your internet connection stable?")

        print("\n📊 GATEWAY STATUS MONITORING:")
        self.show_status_check()

    def show_status_check(self):
        """Show how to check Gateway status"""
        print("Use this command to check if Gateway is accessible:")

        status_script = """
import socket
import sys

def check_gateway_port(port, name):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        
        if result == 0:
            print(f"✅ {name} (port {port}): Gateway is accessible")
            return True
        else:
            print(f"❌ {name} (port {port}): Gateway not accessible")
            return False
    except Exception as e:
        print(f"❌ {name} (port {port}): Error - {e}")
        return False

print("🔍 Checking IB Gateway Status...")
paper_ok = check_gateway_port(4002, "Paper Trading")
live_ok = check_gateway_port(4001, "Live Trading")

if not paper_ok and not live_ok:
    print("\\n💡 Gateway appears to be offline. Please:")
    print("   1. Start IB Gateway application")
    print("   2. Login with your credentials") 
    print("   3. Ensure API is enabled in settings")
else:
    print("\\n✅ Gateway is running and accessible!")
"""

        print("\nSave this as 'check_gateway.py':")
        print(status_script)

    def create_gateway_config(self) -> dict[str, Any]:
        """Create Gateway configuration file"""
        config = {
            "ib_gateway": {
                "paper_trading": {
                    "host": "127.0.0.1",
                    "port": 4002,
                    "client_id": 1,
                    "timeout": 30,
                    "enabled": True,
                },
                "live_trading": {
                    "host": "127.0.0.1",
                    "port": 4001,
                    "client_id": 2,
                    "timeout": 30,
                    "enabled": False,
                },
            },
            "connection_settings": {
                "auto_reconnect": True,
                "max_reconnect_attempts": 5,
                "reconnect_delay": 30,
                "heartbeat_interval": 60,
            },
            "api_settings": {
                "request_pacing": True,
                "max_requests_per_minute": 60,
                "enable_logging": True,
                "log_level": "INFO",
            },
        }

        config_file = Path("config/ib_gateway_config.json")
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        print(f"\n✅ Created Gateway configuration: {config_file}")
        return config

    def create_startup_script(self):
        """Create a startup script for IB Gateway"""
        startup_script = """#!/bin/bash
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
"""

        script_file = Path("start_gateway.sh")
        with open(script_file, "w") as f:
            f.write(startup_script)

        # Make executable
        os.chmod(script_file, 0o755)
        print(f"\n✅ Created startup script: {script_file}")
        print("   Run with: ./start_gateway.sh")

    def run_setup(self):
        """Run the complete Gateway setup"""
        print("🛠️  CREATING IB GATEWAY SETUP FILES...")

        # Create configuration
        self.create_gateway_config()

        # Create startup script
        self.create_startup_script()

        # Create status checker
        self.create_status_checker()

        print("\n🎯 NEXT STEPS:")
        print("1. Follow the setup guide above")
        print("2. Run: ./start_gateway.sh")
        print("3. Test: python3 check_gateway_status.py")
        print("4. Run your trading scripts!")

    def create_status_checker(self):
        """Create Gateway status checker script"""
        checker_script = '''#!/usr/bin/env python3
"""
IB Gateway Status Checker
Monitors IB Gateway connectivity and provides diagnostics
"""

import socket
import asyncio
import sys
from datetime import datetime

class GatewayStatusChecker:
    def __init__(self):
        self.ports = {
            4002: "Paper Trading Gateway",
            4001: "Live Trading Gateway",
            7497: "TWS Paper Trading", 
            7496: "TWS Live Trading"
        }
    
    def check_port(self, port: int, name: str) -> bool:
        """Check if a specific port is accessible"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()
            
            status = "✅ Online" if result == 0 else "❌ Offline"
            print(f"   {name} (port {port}): {status}")
            return result == 0
            
        except Exception as e:
            print(f"   {name} (port {port}): ❌ Error - {e}")
            return False
    
    async def test_api_connection(self, port: int) -> bool:
        """Test actual API connection"""
        try:
            from src.lib.ib_async_wrapper import IBAsync
            ib = IBAsync()
            success = await ib.connect('127.0.0.1', port, 1, timeout=5)
            if success:
                await ib.disconnect()
            return success
        except Exception:
            return False
    
    def run_diagnostics(self):
        """Run comprehensive Gateway diagnostics"""
        print("="*60)
        print("🔍 IB GATEWAY STATUS CHECKER")
        print("="*60)
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        print("\\n📡 PORT ACCESSIBILITY:")
        available_ports: list[int] = []
        for port, name in self.ports.items():
            if self.check_port(port, name):
                available_ports.append(port)
        
        if not available_ports:
            print("\\n❌ No IB services detected!")
            print("\\n💡 TROUBLESHOOTING:")
            print("   • Start IB Gateway or TWS")
            print("   • Login with your credentials")
            print("   • Enable API in settings")
            print("   • Check firewall settings")
            return False
        
        print(f"\\n🧪 API CONNECTION TEST:")
        for port in available_ports:
            name = self.ports[port]
            print(f"   Testing {name}...")
            
            async def test():
                return await self.test_api_connection(port)
            
            try:
                success = asyncio.run(test())
                status = "✅ Success" if success else "❌ Failed"
                print(f"   {name}: {status}")
            except Exception as e:
                print(f"   {name}: ❌ Error - {e}")
        
        print("\\n✅ Status check complete!")
        return True

if __name__ == "__main__":
    checker = GatewayStatusChecker()
    success = checker.run_diagnostics()
    sys.exit(0 if success else 1)
'''

        checker_file = Path("check_gateway_status.py")
        with open(checker_file, "w") as f:
            f.write(checker_script)

        os.chmod(checker_file, 0o755)
        print(f"✅ Created status checker: {checker_file}")


def main():
    """Main setup function"""
    setup = IBGatewaySetup()

    print("Choose an option:")
    print("1. Show setup guide")
    print("2. Create setup files")
    print("3. Both")

    try:
        choice = input("Enter choice (1-3): ").strip()

        if choice in ["1", "3"]:
            setup.print_setup_guide()

        if choice in ["2", "3"]:
            setup.run_setup()

    except KeyboardInterrupt:
        print("\n\nSetup cancelled.")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
