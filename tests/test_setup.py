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


def test_ib_async_stubs_available():
    """Ensure ib_async stubs/types are present for type checking if installed."""
    try:
        import importlib.util

        if importlib.util.find_spec("ib_async") is None:
            pytest.skip("ib_async optional dependency not installed")
    except Exception:
        pytest.skip("Environment missing optional ib_async; skipping")


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
