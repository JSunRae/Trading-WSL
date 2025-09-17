#!/usr/bin/env python3
"""
Headless IB Gateway Automation
Automatically starts and logs into IB Gateway without manual intervention

This module provides fully automated IB Gateway management:
- Automatic startup in headless mode
- Credential-based login
- API configuration
- Health monitoring
- Graceful shutdown

Usage:
    from src.automation.headless_gateway import HeadlessGateway

    gateway = HeadlessGateway("username", "password", paper_trading=True)
    await gateway.start_gateway()
    # Your trading code here
    await gateway.stop_gateway()
"""

import asyncio
import logging
import os
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

import psutil


class HeadlessGateway:
    """Fully automated IB Gateway management"""

    def __init__(
        self,
        username: str,
        password: str,
        paper_trading: bool = True,
        java_heap: str = "512m",
        timeout: int = 120,
    ):
        """
        Initialize Headless Gateway

        Args:
            username: IB account username
            password: IB account password
            paper_trading: Use paper trading (True) or live trading (False)
            java_heap: Java heap size for Gateway (default: 512m)
            timeout: Startup timeout in seconds
        """
        self.username = username
        self.password = password
        self.paper_trading = paper_trading
        self.java_heap = java_heap
        self.timeout = timeout

        # Configuration
        self.port = 4002 if paper_trading else 4001
        self.trading_mode = "paper" if paper_trading else "live"
        self.client_id = 1

        # Process management
        self.gateway_process: subprocess.Popen | None = None
        self.config_dir = Path.home() / ".ibgateway_automated"
        self.config_dir.mkdir(exist_ok=True)

        # Logging
        self.logger = logging.getLogger(__name__)

        # Gateway paths (common installation locations)
        self.gateway_paths = [
            "/opt/ibgateway/ibgateway",
            "/usr/local/ibgateway/ibgateway",
            Path.home() / "Jts" / "ibgateway" / "ibgateway",
            Path.home() / "IBJts" / "ibgateway" / "ibgateway",
            "/Applications/IB Gateway.app/Contents/MacOS/ibgateway",  # macOS
        ]

        # Search candidates for Java; filter out None from which()
        self.java_paths: list[str] = [
            "/opt/ibgateway/jre/bin/java",
            "/usr/bin/java",
            "/usr/local/bin/java",
        ]
        _which_java = shutil.which("java")
        if _which_java:
            self.java_paths.append(_which_java)

    def find_gateway_installation(self) -> Path | None:
        """Find IB Gateway installation"""
        for path in self.gateway_paths:
            p = Path(str(path))
            if p.exists():
                self.logger.info(f"Found IB Gateway at: {p}")
                return p

        self.logger.error("IB Gateway installation not found")
        return None

    def find_java_executable(self) -> str | None:
        """Find Java executable"""
        for java_path in self.java_paths:
            if java_path and Path(java_path).exists():
                self.logger.info(f"Found Java at: {java_path}")
                return str(java_path)

        self.logger.error("Java executable not found")
        return None

    def is_gateway_running(self) -> bool:
        """Check if IB Gateway is already running on our port"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex(("127.0.0.1", self.port))
            sock.close()
            return result == 0
        except Exception:
            return False

    def kill_existing_gateway(self):
        """Kill any existing IB Gateway processes"""
        killed_processes: list[int] = []

        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                # Check for IB Gateway processes
                if proc.info["name"] and "java" in proc.info["name"].lower():
                    if proc.info["cmdline"]:
                        cmdline = " ".join(proc.info["cmdline"])
                        if "ibgateway" in cmdline.lower() or "jts" in cmdline.lower():
                            proc.kill()
                            killed_processes.append(proc.info["pid"])
                            self.logger.info(
                                f"Killed existing Gateway process: {proc.info['pid']}"
                            )

                # Also check for processes using our port
                try:
                    conns = proc.net_connections()
                except Exception:
                    conns = []
                for conn in conns:
                    try:
                        if (
                            conn.laddr
                            and getattr(conn.laddr, "port", None) == self.port
                        ):
                            proc.kill()
                            killed_processes.append(proc.info["pid"])
                            self.logger.info(
                                f"Killed process using port {self.port}: {proc.info['pid']}"
                            )
                    except Exception:
                        continue

            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        if killed_processes:
            time.sleep(3)  # Give processes time to die

        return len(killed_processes)

    def create_gateway_config(self) -> Path:
        """Create IB Gateway configuration files"""

        # Create main config directory structure
        jts_dir = self.config_dir / "Jts"
        jts_dir.mkdir(exist_ok=True)

        # Create jts.ini file
        jts_ini = jts_dir / "jts.ini"
        jts_ini_content = f"""[IBGateway]
LoginDialogDisplayTime=5
ApiOnly=true
colorPalletCode=0
Steps=0
displayedproxy=
LocalServerPort={self.port}
ApiLogLevel=5
TrustedIPs=127.0.0.1
MasterClientID={self.client_id}
SuppressInfoDlg=yes
ReadOnlyApi=no
AcceptIncomingConnectionAction=accept
ShowAllTrades=no
useRemoteSettings=no
Steps11=0
SupressInfoDlg=yes
"""
        jts_ini.write_text(jts_ini_content)

        # Create login configuration
        login_config = jts_dir / "loginpreset.ini"
        login_content = f"""[LoginPreset]
username={self.username}
password={self.password}
mode={"paper" if self.paper_trading else "live"}
"""
        login_config.write_text(login_content)

        self.logger.info(f"Created Gateway configuration in {jts_dir}")
        return jts_dir

    def create_startup_script(self, jts_dir: Path) -> Path:
        """Create gateway startup script"""
        java_exec = self.find_java_executable()
        if not java_exec:
            raise RuntimeError("Java executable not found")

        gateway_path = self.find_gateway_installation()
        if not gateway_path:
            raise RuntimeError("IB Gateway installation not found")

        # Find JAR files
        gateway_dir = gateway_path.parent

        # Common JAR locations
        jar_locations = [
            gateway_dir / "ibgateway.jar",
            gateway_dir / "jars",
            gateway_dir / "lib",
            gateway_dir / "3rdparty",
        ]

        classpath_parts: list[str] = []
        for location in jar_locations:
            if location.is_file() and location.suffix == ".jar":
                classpath_parts.append(str(location))
            elif location.is_dir():
                for jar_file in location.glob("*.jar"):
                    classpath_parts.append(str(jar_file))

        if not classpath_parts:
            # Fallback - try to find all JARs in gateway directory
            for jar_file in gateway_dir.rglob("*.jar"):
                classpath_parts.append(str(jar_file))

        classpath = ":".join(classpath_parts)

        # Create startup script
        startup_script = self.config_dir / "start_gateway.sh"

        script_content = f"""#!/bin/bash
# Automated IB Gateway Startup Script
set -e

export DISPLAY=:99  # Virtual display
export TWS_CONFIG_PATH="{jts_dir}"
export USER_HOME="{Path.home()}"

# Start Xvfb for headless GUI if not running
if ! pgrep -x "Xvfb" > /dev/null; then
    Xvfb :99 -screen 0 1024x768x24 -ac +extension GLX +render -noreset &
    export XVFB_PID=$!
    sleep 2
fi

# Start IB Gateway
cd "{gateway_dir}"

"{java_exec}" \\
    -Xmx{self.java_heap} \\
    -XX:+UseG1GC \\
    -XX:MaxGCPauseMillis=200 \\
    -XX:+UnlockExperimentalVMOptions \\
    -XX:+UseCGroupMemoryLimitForHeap \\
    -Duser.timezone=America/New_York \\
    -Dsun.java2d.noddraw=true \\
    -Dsun.java2d.d3d=false \\
    -Dswing.defaultlaf=javax.swing.plaf.metal.MetalLookAndFeel \\
    -Dsun.locale.formatasdefault=true \\
    -Dfile.encoding=UTF-8 \\
    -Duser.home="{Path.home()}" \\
    -Djts.dir="{jts_dir}" \\
    -cp "{classpath}" \\
    ibgateway.GWClient \\
    "{jts_dir}" &

export GATEWAY_PID=$!
echo "Gateway PID: $GATEWAY_PID"
echo "Config Dir: {jts_dir}"
echo "Port: {self.port}"
echo "Mode: {self.trading_mode}"

# Keep script running
wait $GATEWAY_PID
"""

        startup_script.write_text(script_content)
        startup_script.chmod(0o755)

        self.logger.info(f"Created startup script: {startup_script}")
        return startup_script

    async def start_gateway(self) -> bool:
        """
        Start IB Gateway with automatic login
        Returns True if successfully started and logged in
        """
        if self.is_gateway_running():
            self.logger.info(f"IB Gateway already running on port {self.port}")
            return True

        try:
            # Kill any existing Gateway processes
            killed = self.kill_existing_gateway()
            if killed > 0:
                await asyncio.sleep(5)  # Wait for cleanup

            # Create configuration
            jts_dir = self.create_gateway_config()

            # Install Xvfb if not available (for headless GUI)
            await self._ensure_xvfb()

            # Create and run startup script
            startup_script = self.create_startup_script(jts_dir)

            self.logger.info(
                f"Starting IB Gateway in {self.trading_mode} mode on port {self.port}"
            )

            # Start the gateway process
            env = os.environ.copy()
            env.update(
                {
                    "DISPLAY": ":99",
                    "TWS_CONFIG_PATH": str(jts_dir),
                    "USER_HOME": str(Path.home()),
                }
            )

            self.gateway_process = subprocess.Popen(
                [str(startup_script)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=str(self.config_dir),
                preexec_fn=os.setsid,  # Create new process group
            )

            # Wait for Gateway to start and be ready
            success = await self._wait_for_startup()

            if success:
                self.logger.info("🎉 IB Gateway started and ready for API connections!")
                return True
            else:
                self.logger.error("❌ Failed to start IB Gateway")
                await self.stop_gateway()
                return False

        except Exception as e:
            self.logger.error(f"Error starting IB Gateway: {e}")
            await self.stop_gateway()
            return False

    async def _ensure_xvfb(self):
        """Ensure Xvfb is available for headless GUI"""
        try:
            # Check if Xvfb is installed
            result = subprocess.run(["which", "Xvfb"], capture_output=True, text=True)
            if result.returncode != 0:
                self.logger.info("Installing Xvfb for headless display...")

                # Try to install Xvfb
                install_commands = [
                    ["sudo", "apt-get", "update"],
                    ["sudo", "apt-get", "install", "-y", "xvfb"],
                ]

                for cmd in install_commands:
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    if result.returncode != 0:
                        self.logger.warning(f"Command failed: {' '.join(cmd)}")
                        # Continue anyway - might work without it

            # Start Xvfb if not running
            if (
                not subprocess.run(
                    ["pgrep", "-x", "Xvfb"], capture_output=True
                ).returncode
                == 0
            ):
                subprocess.Popen(
                    [
                        "Xvfb",
                        ":99",
                        "-screen",
                        "0",
                        "1024x768x24",
                        "-ac",
                        "+extension",
                        "GLX",
                        "+render",
                        "-noreset",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                await asyncio.sleep(2)  # Give Xvfb time to start

        except Exception as e:
            self.logger.warning(f"Could not setup Xvfb: {e}")
            # Continue anyway - Gateway might work without it

    async def _wait_for_startup(self) -> bool:
        """Wait for Gateway to be ready for API connections"""
        start_time = time.time()

        self.logger.info("Waiting for Gateway to start...")

        while time.time() - start_time < self.timeout:
            # Check if process is still running
            if self.gateway_process and self.gateway_process.poll() is not None:
                # Process terminated - check output
                stdout, stderr = self.gateway_process.communicate()
                self.logger.error("Gateway process terminated:")
                if stdout:
                    self.logger.error(f"STDOUT: {stdout.decode()}")
                if stderr:
                    self.logger.error(f"STDERR: {stderr.decode()}")
                return False

            # Check if API port is available
            if self.is_gateway_running():
                # Give it a moment to fully initialize
                await asyncio.sleep(5)

                # Test actual API connection
                if await self._test_api_connection():
                    elapsed = time.time() - start_time
                    self.logger.info(f"✅ Gateway ready after {elapsed:.1f}s")
                    return True

            await asyncio.sleep(2)

            # Show progress
            elapsed = time.time() - start_time
            if int(elapsed) % 10 == 0:  # Every 10 seconds
                self.logger.info(f"Still waiting... ({elapsed:.0f}s/{self.timeout}s)")

        self.logger.error(f"Gateway startup timeout after {self.timeout}s")
        return False

    async def _test_api_connection(self) -> bool:
        """Test if Gateway API is responding correctly"""
        try:
            # Try to make a simple connection
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", self.port), timeout=5
            )

            # Send a simple API request to verify it's actually IB Gateway
            # This is a minimal test - just check if connection is accepted
            writer.close()
            await writer.wait_closed()

            self.logger.info(f"✅ API connection test successful on port {self.port}")
            return True

        except Exception as e:
            self.logger.debug(f"API connection test failed: {e}")
            return False

    async def stop_gateway(self):
        """Stop IB Gateway gracefully"""
        if self.gateway_process:
            try:
                # Try graceful shutdown first
                self.gateway_process.terminate()

                # Wait up to 10 seconds for graceful shutdown
                try:
                    await asyncio.wait_for(
                        asyncio.create_task(
                            asyncio.to_thread(self.gateway_process.wait)
                        ),
                        timeout=10,
                    )
                except TimeoutError:
                    # Force kill if graceful shutdown failed
                    self.logger.warning("Graceful shutdown failed, force killing...")
                    self.gateway_process.kill()
                    try:
                        os.killpg(os.getpgid(self.gateway_process.pid), signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        pass

                self.gateway_process = None
                self.logger.info("✅ IB Gateway stopped")

            except Exception as e:
                self.logger.error(f"Error stopping Gateway: {e}")

        # Also kill any remaining processes
        self.kill_existing_gateway()

        # Kill Xvfb if we started it
        try:
            subprocess.run(
                ["pkill", "-f", "Xvfb :99"], capture_output=True, check=False
            )
        except Exception:
            pass

    async def wait_for_api_ready(self, timeout: int = 30) -> bool:
        """Wait for API to be ready for trading connections"""
        return await self._test_api_connection()

    async def get_status(self) -> dict[str, Any]:
        """Get Gateway status information"""
        return {
            "running": self.is_gateway_running(),
            "port": self.port,
            "trading_mode": self.trading_mode,
            "process_alive": self.gateway_process
            and self.gateway_process.poll() is None,
            "api_ready": await self._test_api_connection()
            if self.is_gateway_running()
            else False,
        }

    async def restart_gateway(self) -> bool:
        """Restart Gateway (useful for recovery)"""
        self.logger.info("Restarting IB Gateway...")
        await self.stop_gateway()
        await asyncio.sleep(5)  # Give it time to fully stop
        return await self.start_gateway()


# Usage example and demo
async def demo_headless_gateway():
    """Demo: Fully automated trading setup"""
    logging.basicConfig(level=logging.INFO)

    # Get credentials from environment or prompt
    username = os.getenv("IB_USERNAME")
    password = os.getenv("IB_PASSWORD")

    if not username:
        username = input("IB Username: ")
    if not password:
        import getpass

        password = getpass.getpass("IB Password: ")

    # Create and start Gateway
    gateway = HeadlessGateway(
        username=username,
        password=password,
        paper_trading=True,  # Use paper trading for safety
    )

    try:
        # Start Gateway automatically
        if await gateway.start_gateway():
            print("✅ Gateway started successfully!")

            # Test with your trading system
            print("Testing API connection...")

            # Import your async wrapper
            import sys

            sys.path.append(str(Path(__file__).parent.parent))
            from infra.ib_conn import get_ib_connect_plan, try_connect_candidates
            from lib.ib_async_wrapper import IBAsync

            ib = IBAsync()
            plan = get_ib_connect_plan()
            ok, used = await try_connect_candidates(
                ib.connect,
                plan["host"],
                [int(p) for p in plan["candidates"]],
                int(plan["client_id"]),
                autostart=False,
            )
            connected = ok

            if connected:
                print(f"✅ Connected to IB API on port {used}!")

                # Test data retrieval
                contract = ib.create_stock_contract("AAPL")
                df = await ib.req_historical_data(contract, "1 D", "1 min")

                if df is not None and not df.empty:
                    print(f"✅ Downloaded {len(df)} AAPL bars!")
                    print(f"Latest price: ${df['close'].iloc[-1]:.2f}")
                else:
                    print("❌ No data received")

                await ib.disconnect()
            else:
                print("❌ Failed to connect to IB API")

            # Keep Gateway running for a bit
            print("Gateway will remain running. Press Ctrl+C to stop...")
            try:
                await asyncio.sleep(3600)  # Run for 1 hour
            except KeyboardInterrupt:
                print("\nShutting down...")
        else:
            print("❌ Failed to start Gateway")

    finally:
        # Always clean up
        await gateway.stop_gateway()
        print("🧹 Cleanup complete")


if __name__ == "__main__":
    asyncio.run(demo_headless_gateway())
