"""Tests for IB connection plan builder and candidate logic."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.infra.ib_conn import (
    _build_candidate_ports,
    _filter_valid_ports,
    _is_valid_port,
    _parse_jts_config,
    get_ib_connect_plan,
)


class TestIBConnPlanBuilder(unittest.TestCase):
    """Test the canonical connection plan builder."""

    def setUp(self) -> None:
        """Reset environment for each test."""
        # Store original env values
        self.orig_env = {
            key: os.environ.get(key)
            for key in ["IB_PORT", "IB_HOST", "IB_CLIENT_ID", "IB_ALLOW_WINDOWS"]
        }
        # Clear test-relevant env vars
        for key in ["IB_PORT", "IB_HOST", "IB_CLIENT_ID", "IB_ALLOW_WINDOWS"]:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        """Restore original environment."""
        for key, value in self.orig_env.items():
            if value is not None:
                os.environ[key] = value
            else:
                os.environ.pop(key, None)

    def test_port_validation_rejects_invalid_ports(self) -> None:
        """Test that invalid ports are rejected."""
        self.assertFalse(_is_valid_port(0))
        self.assertFalse(_is_valid_port(-1))
        self.assertFalse(_is_valid_port(65536))
        self.assertFalse(_is_valid_port(100000))

    def test_port_validation_accepts_valid_ports(self) -> None:
        """Test that valid ports are accepted."""
        self.assertTrue(_is_valid_port(1))
        self.assertTrue(_is_valid_port(4002))
        self.assertTrue(_is_valid_port(7497))
        self.assertTrue(_is_valid_port(65535))

    def test_filter_valid_ports_removes_invalid(self) -> None:
        """Test that invalid ports are filtered out."""
        ports = [0, 4002, -1, 7497, 65536, 4003]
        filtered = _filter_valid_ports(ports)
        self.assertEqual(filtered, [4002, 7497, 4003])

    def test_filter_valid_ports_deduplicates(self) -> None:
        """Test that duplicate ports are removed."""
        ports = [4002, 4002, 7497, 4002, 4003]
        filtered = _filter_valid_ports(ports)
        self.assertEqual(filtered, [4002, 7497, 4003])

    def test_build_candidate_ports_linux_only_default(self) -> None:
        """Test default Linux-only candidate list."""
        candidates = _build_candidate_ports()
        # Should have 4002, 7497 but not 4003, 4004
        self.assertIn(4002, candidates)
        self.assertIn(7497, candidates)
        self.assertNotIn(4003, candidates)
        self.assertNotIn(4004, candidates)

    def test_build_candidate_ports_with_env_port(self) -> None:
        """Test that IB_PORT is prioritized in candidates."""
        os.environ["IB_PORT"] = "5000"
        candidates = _build_candidate_ports()
        # Should start with 5000
        self.assertEqual(candidates[0], 5000)
        self.assertIn(4002, candidates)
        self.assertIn(7497, candidates)

    def test_build_candidate_ports_with_windows_enabled(self) -> None:
        """Test that Windows ports are included when IB_ALLOW_WINDOWS=1."""
        os.environ["IB_ALLOW_WINDOWS"] = "1"
        candidates = _build_candidate_ports()
        self.assertIn(4002, candidates)
        self.assertIn(7497, candidates)
        self.assertIn(4003, candidates)
        self.assertIn(4004, candidates)

    def test_build_candidate_ports_windows_disabled_by_default(self) -> None:
        """Test that Windows ports are excluded by default."""
        candidates = _build_candidate_ports()
        self.assertNotIn(4003, candidates)
        self.assertNotIn(4004, candidates)

    def test_get_ib_connect_plan_defaults(self) -> None:
        """Test the complete connection plan with defaults."""
        plan = get_ib_connect_plan()

        self.assertEqual(plan["host"], "127.0.0.1")
        self.assertIsInstance(plan["candidates"], list)
        self.assertIn(4002, plan["candidates"])
        self.assertIn(7497, plan["candidates"])
        self.assertNotIn(4003, plan["candidates"])  # Windows disabled by default
        # Client ID may vary based on environment, just check it's an int
        self.assertIsInstance(plan["client_id"], int)
        self.assertEqual(plan["timeout"], 20)
        self.assertEqual(plan["method"], "linux")

    def test_get_ib_connect_plan_with_env_overrides(self) -> None:
        """Test connection plan with environment overrides."""
        os.environ["IB_HOST"] = "192.168.1.100"
        os.environ["IB_PORT"] = "5000"
        os.environ["IB_CLIENT_ID"] = "3000"
        os.environ["IB_ALLOW_WINDOWS"] = "1"

        plan = get_ib_connect_plan()

        self.assertEqual(plan["host"], "192.168.1.100")
        self.assertEqual(plan["candidates"][0], 5000)  # Prioritized
        self.assertIn(4003, plan["candidates"])  # Windows enabled
        self.assertEqual(plan["client_id"], 3000)

    def test_get_ib_connect_plan_sanitizes_host_comments(self) -> None:
        """Test that host comments are stripped."""
        os.environ["IB_HOST"] = "127.0.0.1  # test comment"
        plan = get_ib_connect_plan()
        self.assertEqual(plan["host"], "127.0.0.1")

    def test_parse_jts_config_file_not_found(self) -> None:
        """Test JTS config parsing when file doesn't exist."""
        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = Path("/nonexistent")
            config = _parse_jts_config()
            self.assertFalse(config["found"])
            self.assertIsNone(config["api_port"])

    def test_parse_jts_config_with_valid_content(self) -> None:
        """Test JTS config parsing with valid content."""
        jts_content = """
# Test config
socketPort=4001
useSSL=true
trustedIPs=127.0.0.1,192.168.1.0/24
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            jts_dir = Path(temp_dir) / "Jts"
            jts_dir.mkdir()
            jts_file = jts_dir / "jts.ini"
            jts_file.write_text(jts_content)

            with patch("pathlib.Path.home") as mock_home:
                mock_home.return_value = Path(temp_dir)
                config = _parse_jts_config()

                self.assertTrue(config["found"])
                self.assertEqual(config["api_port"], 4001)
                self.assertTrue(config["ssl_enabled"])
                self.assertIn("127.0.0.1", config["trusted_ips"])

    def test_windows_flag_variations(self) -> None:
        """Test various ways to enable Windows fallback."""
        for value in ["1", "true", "True", "YES", "on"]:
            with self.subTest(value=value):
                os.environ["IB_ALLOW_WINDOWS"] = value
                candidates = _build_candidate_ports()
                self.assertIn(4003, candidates, f"Failed for value: {value}")
                # Clean up for next iteration
                del os.environ["IB_ALLOW_WINDOWS"]

    def test_windows_flag_false_variations(self) -> None:
        """Test various ways Windows fallback stays disabled."""
        for value in ["0", "false", "False", "NO", "off", ""]:
            with self.subTest(value=value):
                os.environ["IB_ALLOW_WINDOWS"] = value
                candidates = _build_candidate_ports()
                self.assertNotIn(4003, candidates, f"Failed for value: {value}")
                # Clean up for next iteration
                del os.environ["IB_ALLOW_WINDOWS"]


class TestConnectionPolicyBehavior(unittest.TestCase):
    """Test that the connection policy behaves correctly."""

    def setUp(self) -> None:
        """Reset environment for each test."""
        for key in ["IB_PORT", "IB_HOST", "IB_CLIENT_ID", "IB_ALLOW_WINDOWS"]:
            os.environ.pop(key, None)

    def test_no_port_zero_in_candidates(self) -> None:
        """Ensure port 0 never appears in candidates."""
        # Try various scenarios that might produce port 0
        os.environ["IB_PORT"] = "0"
        candidates = _build_candidate_ports()
        self.assertNotIn(0, candidates)

        os.environ["IB_PORT"] = "invalid"
        candidates = _build_candidate_ports()
        self.assertNotIn(0, candidates)

    def test_linux_first_ordering(self) -> None:
        """Test that Linux ports come before Windows ports."""
        os.environ["IB_ALLOW_WINDOWS"] = "1"
        candidates = _build_candidate_ports()

        # Find positions
        pos_4002 = candidates.index(4002) if 4002 in candidates else -1
        pos_7497 = candidates.index(7497) if 7497 in candidates else -1
        pos_4003 = candidates.index(4003) if 4003 in candidates else -1
        pos_4004 = candidates.index(4004) if 4004 in candidates else -1

        # Linux ports should come before Windows ports
        if pos_4003 >= 0:
            self.assertLess(pos_4002, pos_4003)
            self.assertLess(pos_7497, pos_4003)
        if pos_4004 >= 0:
            self.assertLess(pos_4002, pos_4004)
            self.assertLess(pos_7497, pos_4004)

    def test_env_port_prioritized(self) -> None:
        """Test that IB_PORT is tried first."""
        os.environ["IB_PORT"] = "8888"
        candidates = _build_candidate_ports()
        self.assertEqual(candidates[0], 8888)


if __name__ == "__main__":
    unittest.main()
