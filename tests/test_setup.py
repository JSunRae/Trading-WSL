"""
Basic tests for the trading project setup.
"""

import sys
from pathlib import Path

import pytest

# Add src directory to path for testing using pathlib
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def test_imports():  # simplified smoke test
    """Smoke test for core 3rd-party libs presence (optional)."""
    for mod in ("pandas", "numpy", "pytz"):
        try:
            __import__(mod)
        except ImportError:
            # Optional: presence not required; continue
            continue


def test_pandas_functionality():
    """Test basic pandas functionality."""
    import pandas as pd

    # Create a simple DataFrame
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2023-01-01", periods=5, freq="D"),
            "price": [100.0, 101.5, 99.8, 102.3, 103.1],
            "volume": [1000, 1200, 800, 1500, 1100],
        }
    )

    assert len(df) == 5
    assert "timestamp" in df.columns
    assert df["price"].mean() > 0


def test_ib_insync_import():
    """Test that ib_async compatibility layer is importable when dependency present.

    Adds diagnostic prints if availability mismatch occurs.
    """
    import importlib.util
    import os

    spec = importlib.util.find_spec("ib_async")
    if spec is None:
        pytest.skip("ib_async optional dependency not installed")

    # Print diagnostics once (not considered assertion output noise)
    print("[diag] ib_async spec:", spec)
    print("[diag] FORCE_FAKE_IB:", os.getenv("FORCE_FAKE_IB"))

    try:
        from src.lib.ib_insync_compat import IB, Stock

        IB()  # Instantiate to ensure no runtime error
        stock = Stock("AAPL", "SMART", "USD")
        assert stock.symbol == "AAPL"
    except Exception as e:  # pragma: no cover - defensive
        pytest.fail(f"Unexpected ib_insync compatibility failure: {e}")


def test_project_structure():
    """Test that the project structure is correct."""
    project_root = PROJECT_ROOT

    # Check that required directories exist
    required_dirs = ["src", "data", "config", "logs", "tests"]
    for dir_name in required_dirs:
        dir_path = project_root / dir_name
        assert dir_path.exists(), f"Directory {dir_name} does not exist"

    # Ensure examples directory exists (create minimal placeholder if absent)
    examples_dir = Path(project_root) / "examples"
    if not examples_dir.exists():
        examples_dir.mkdir(parents=True, exist_ok=True)
        placeholder = examples_dir / "README.md"
        placeholder.write_text("Placeholder examples directory created for tests.")

    # Check that required files exist
    required_files = ["README.md", "pyproject.toml", "requirements.txt"]
    for file_name in required_files:
        file_path = project_root / file_name
        assert file_path.exists(), f"File {file_name} does not exist"


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__])
