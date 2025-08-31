#!/usr/bin/env python3
"""
Test ML imports in a cleaner way
"""

import sys
from pathlib import Path

from src.tools._cli_helpers import env_dep, print_json

# Ultra-early describe path to guarantee JSON-only output before other side effects
if "--describe" in sys.argv[1:]:  # pragma: no cover - executed only in describe mode
    raise SystemExit(
        print_json(
            {
                "name": "validate_ml_structure",
                "description": "Validate presence and structure of ML-related modules (legacy text tool).",
                "inputs": {
                    "--describe": {
                        "type": "flag",
                        "description": "Show schema JSON and exit",
                    }
                },
                "outputs": {
                    "stdout": {
                        "type": "text",
                        "description": "Human-readable validation report or schema JSON",
                    }
                },
                "dependencies": [env_dep("PROJECT_ROOT")],
                "examples": [
                    {
                        "description": "Show schema",
                        "command": "python -m src.tools.analysis.validate_ml_structure --describe",
                    }
                ],
            }
        )
    )


def describe() -> dict[str, object]:
    """Machine-readable metadata for --describe."""
    return {
        "name": "validate_ml_structure",
        "description": "Validate presence and structure of ML-related modules (legacy text tool).",
        "inputs": {
            "--describe": {"type": "flag", "description": "Show schema JSON and exit"}
        },
        "outputs": {
            "stdout": {
                "type": "text",
                "description": "Human-readable validation report or schema JSON",
            }
        },
        "dependencies": [env_dep("PROJECT_ROOT")],
        "examples": [
            {
                "description": "Show schema",
                "command": "python -m src.tools.analysis.validate_ml_structure --describe",
            }
        ],
    }


# Add the specific module paths to avoid conflicts
src_path = Path(__file__).parent / "src"
execution_path = src_path / "execution"
risk_path = src_path / "risk"
domain_path = src_path / "domain"

sys.path.insert(0, str(execution_path))
sys.path.insert(0, str(risk_path))
sys.path.insert(0, str(domain_path))


def test_check_modules_exist():
    """Check that the required modules exist"""
    print("🔄 Checking ML module files exist...")

    # Check execution module
    ml_signal_executor = execution_path / "ml_signal_executor.py"
    if ml_signal_executor.exists():
        print(f"✅ Found: {ml_signal_executor}")
    else:
        print(f"❌ Missing: {ml_signal_executor}")
        return False

    # Check risk module
    ml_risk_manager = risk_path / "ml_risk_manager.py"
    if ml_risk_manager.exists():
        print(f"✅ Found: {ml_risk_manager}")
    else:
        print(f"❌ Missing: {ml_risk_manager}")
        return False

    # Check domain module
    ml_types = domain_path / "ml_types.py"
    if ml_types.exists():
        print(f"✅ Found: {ml_types}")
    else:
        print(f"❌ Missing: {ml_types}")
        return False

    return True


def test_pyright_config():
    """Check if pyrightconfig.json has our fixes"""
    print("\n🔄 Checking pyrightconfig.json...")

    config_file = Path(__file__).parent / "pyrightconfig.json"
    if not config_file.exists():
        print("❌ pyrightconfig.json not found")
        return False

    content = config_file.read_text()
    if '"extraPaths"' in content and '"src"' in content:
        print("✅ pyrightconfig.json has extraPaths configuration")
        return True
    else:
        print("❌ pyrightconfig.json missing extraPaths configuration")
        return False


def test_domain_types_structure():
    """Check the domain types module structure"""
    print("\n🔄 Checking domain types module...")

    ml_types_file = domain_path / "ml_types.py"
    if not ml_types_file.exists():
        print("❌ ml_types.py not found")
        return False

    content = ml_types_file.read_text()

    # Check for key classes
    required_classes = [
        "class SignalType",
        "class SizingMode",
        "class RiskLevel",
        "class MLTradingSignal",
        "class RiskAssessment",
        "class ExecutionReport",
    ]

    missing = []
    for cls in required_classes:
        if cls not in content:
            missing.append(cls)

    if missing:
        print(f"❌ Missing classes in ml_types.py: {missing}")
        return False
    else:
        print("✅ All required domain classes found")
        return True


def test_api_module():
    """Check the API module structure"""
    print("\n🔄 Checking API module...")

    api_file = src_path / "api.py"
    if not api_file.exists():
        print("❌ api.py not found")
        return False

    content = api_file.read_text()

    # Check for imports from domain
    if "from .domain.ml_types import" in content:
        print("✅ API module imports from domain types")
        return True
    else:
        print("❌ API module doesn't import from domain types")
        return False


def test_test_file_structure():
    """Check the updated test file"""
    print("\n🔄 Checking updated test file...")

    test_file = Path(__file__).parent / "tests" / "test_ml_infrastructure_priorities.py"
    if not test_file.exists():
        print("❌ test_ml_infrastructure_priorities.py not found")
        return False

    content = test_file.read_text()

    # Check that it uses src.execution imports instead of src.api
    if "from src.execution.ml_signal_executor import" in content:
        print("✅ Test file uses direct module imports")
        return True
    else:
        print("❌ Test file still using problematic imports")
        return False


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if "--describe" in args:  # early pure JSON path
        return print_json(describe())

    print("=" * 60)
    print("ML INFRASTRUCTURE STRUCTURE VALIDATION")
    print("=" * 60)

    tests = [
        test_check_modules_exist,
        test_pyright_config,
        test_domain_types_structure,
        test_api_module,
        test_test_file_structure,
    ]

    results = [t() for t in tests]

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    if passed == total:
        print(f"✅ All {total} structure tests passed!")
        print("\n🎯 NEXT STEPS:")
        print("   1. Install required dependencies as needed (IB API, etc.)")
        print("   2. Run: python -m pytest tests/test_ml_infrastructure_priorities.py")
        print("   3. Check that Pyright shows fewer unknown type warnings")
        return 0
    else:
        print(f"❌ {total - passed} of {total} tests failed")
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
