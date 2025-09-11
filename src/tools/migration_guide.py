#!/usr/bin/env python3
"""
@agent.tool migration_guide

Migration Guide and Implementation Helper
This script provides step-by-step migration guidance and can automatically
apply certain improvements to the existing trading system codebase.
"""

import logging
import re
import sys
from pathlib import Path
from typing import Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Schema definitions for agent tool pattern
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "analyze_only": {
            "type": "boolean",
            "default": False,
            "description": "Only analyze codebase, skip migration plan",
        },
        "include_examples": {
            "type": "boolean",
            "default": True,
            "description": "Include code examples in output",
        },
    },
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "analysis": {
            "type": "object",
            "properties": {
                "files_analyzed": {"type": "integer"},
                "hardcoded_paths": {"type": "array", "items": {"type": "object"}},
                "print_statements": {"type": "array", "items": {"type": "object"}},
                "error_handling_issues": {"type": "array", "items": {"type": "object"}},
                "monolithic_classes": {"type": "array", "items": {"type": "object"}},
            },
        },
        "migration_plan": {"type": "array", "items": {"type": "string"}},
        "code_examples": {"type": "array", "items": {"type": "object"}},
        "next_steps": {"type": "array", "items": {"type": "string"}},
        "architecture_components": {"type": "object"},
    },
}

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class CodeMigrationAssistant:
    """Assists with migrating existing code to the new architecture"""

    def __init__(self):
        try:
            from src.core.config import get_config
            from src.core.error_handler import get_error_handler

            self.config = get_config()
            self.error_handler = get_error_handler()
        except ImportError:
            logger.warning("Core modules not available, using fallback")
            self.config = None
            self.error_handler = None
        self.workspace_root = Path(__file__).parent.parent

    def analyze_codebase(self) -> dict[str, Any]:  # noqa: C901
        """Analyze the entire codebase for migration opportunities"""

        logger.info("Analyzing codebase for migration opportunities")

        analysis: dict[str, Any] = {
            "files_analyzed": 0,
            "hardcoded_paths": [],
            "print_statements": [],
            "error_handling_issues": [],
            "monolithic_classes": [],
            "improvement_opportunities": [],
        }

        # Find all Python files
        python_files = list(self.workspace_root.glob("*.py"))

        for file_path in python_files:
            if file_path.name.startswith(
                (".", "test_", "architecture_demo", "test_runner", "migration_guide")
            ):
                continue

            print(f"\n📄 Analyzing {file_path.name}...")
            analysis["files_analyzed"] += 1

            try:
                content = file_path.read_text(encoding="utf-8")

                # Look for hardcoded paths
                hardcoded_patterns = [
                    r'["\']G:/Machine Learning["\']',
                    r'["\']G:\\Machine Learning["\']',
                    r'["\'].*\\Machine Learning.*["\']',
                    r'["\'].*/Machine Learning.*["\']',
                ]

                for pattern in hardcoded_patterns:
                    matches = re.findall(pattern, content)
                    if matches:
                        analysis["hardcoded_paths"].extend(
                            [
                                {"file": file_path.name, "pattern": match}
                                for match in matches
                            ]
                        )

                # Look for print statements
                print_matches = re.findall(r"print\s*\(.*\)", content)
                if print_matches:
                    analysis["print_statements"].append(
                        {
                            "file": file_path.name,
                            "count": len(print_matches),
                            "examples": print_matches[:3],  # First 3 examples
                        }
                    )

                # Look for large classes (potential monoliths)
                class_matches = re.findall(
                    r"class\s+(\w+).*?(?=class|\Z)", content, re.DOTALL
                )
                for _class_match in class_matches:  # Track for each class found
                    lines = content.count("\n")
                    if lines > 500:  # Large class threshold
                        analysis["monolithic_classes"].append(
                            {
                                "file": file_path.name,
                                "lines": lines,
                                "needs_refactoring": True,
                            }
                        )

                # Look for error handling issues
                try_matches = re.findall(r"try:.*?except.*?:", content, re.DOTALL)
                if len(try_matches) < 2 and len(content.split("\n")) > 100:
                    analysis["error_handling_issues"].append(
                        {
                            "file": file_path.name,
                            "issue": "Insufficient error handling for file size",
                        }
                    )

            except Exception as e:
                if self.error_handler:
                    # Use error handler if available
                    try:
                        from src.core.error_handler import handle_error

                        handle_error(
                            e, module="MigrationAssistant", function="analyze_codebase"
                        )
                    except ImportError:
                        logger.error(f"Error analyzing {file_path.name}: {e}")
                else:
                    logger.error(f"Error analyzing {file_path.name}: {e}")

        return analysis

    def generate_migration_plan(self, analysis: dict[str, Any]) -> list[str]:
        """Generate a prioritized migration plan"""

        plan = [
            "🚀 Trading System Migration Plan",
            "=" * 35,
            "",
            "📋 Priority Order (High to Low):",
            "",
        ]

        # Priority 1: Replace hardcoded paths
        if analysis["hardcoded_paths"]:
            plan.extend(
                [
                    "🔥 PRIORITY 1: Replace Hardcoded Paths",
                    "Problem: Hardcoded paths make code non-portable",
                    "Solution: Use ConfigManager for all file paths",
                    "",
                    "Files affected:",
                ]
            )

            affected_files = set(item["file"] for item in analysis["hardcoded_paths"])
            for file in affected_files:
                plan.append(f"  • {file}")

            plan.extend(
                [
                    "",
                    "Migration steps:",
                    "1. Import: from src.core import get_config",
                    "2. Get config: config = get_config()",
                    "3. Replace hardcoded paths with config.get_data_file_path()",
                    "",
                ]
            )

        # Priority 2: Improve error handling
        if analysis["print_statements"] or analysis["error_handling_issues"]:
            plan.extend(
                [
                    "⚠️  PRIORITY 2: Improve Error Handling",
                    "Problem: print() statements and insufficient error handling",
                    "Solution: Use ErrorHandler for all error reporting",
                    "",
                    "Files with print statements:",
                ]
            )

            for item in analysis["print_statements"]:
                plan.append(f"  • {item['file']}: {item['count']} print statements")

            plan.extend(
                [
                    "",
                    "Migration steps:",
                    "1. Import: from src.core import get_error_handler, handle_error",
                    "2. Replace print(error) with handle_error(error)",
                    "3. Add try-except blocks around risky operations",
                    "",
                ]
            )

        # Priority 3: Break down monolithic classes
        if analysis["monolithic_classes"]:
            plan.extend(
                [
                    "🔧 PRIORITY 3: Refactor Monolithic Classes",
                    "Problem: Large classes with mixed responsibilities",
                    "Solution: Break into focused, single-responsibility classes",
                    "",
                    "Large classes found:",
                ]
            )

            for item in analysis["monolithic_classes"]:
                plan.append(f"  • {item['file']}: {item['lines']} lines")

            plan.extend(
                [
                    "",
                    "Migration steps:",
                    "1. Use DataManager instead of requestCheckerCLS",
                    "2. Extract configuration logic to ConfigManager",
                    "3. Move data operations to repository pattern",
                    "",
                ]
            )

        # Add specific recommendations
        plan.extend(
            [
                "📊 Implementation Progress Tracking:",
                "",
                "Phase 1 (Week 1): Configuration Management",
                "  □ Replace all hardcoded paths",
                "  □ Test path generation on both Windows/Linux",
                "  □ Update configuration files",
                "",
                "Phase 2 (Week 2): Error Handling",
                "  □ Replace print statements with ErrorHandler",
                "  □ Add structured exception handling",
                "  □ Implement error recovery strategies",
                "",
                "Phase 3 (Week 3): Data Management",
                "  □ Migrate from requestCheckerCLS to DataManager",
                "  □ Implement repository pattern for data access",
                "  □ Add download tracking",
                "",
                "Phase 4 (Week 4): Testing & Performance",
                "  □ Add unit tests for critical functions",
                "  □ Performance monitoring and optimization",
                "  □ Documentation updates",
                "",
            ]
        )

        return plan

    def show_specific_examples(self, analysis: dict[str, Any]):
        """Show specific code examples for migration"""

        print("\n💡 Specific Migration Examples")
        print("=" * 35)

        # Example 1: Path replacement
        if analysis["hardcoded_paths"]:
            print("\n🔧 Example 1: Replacing Hardcoded Paths")
            print("-" * 40)
            print("❌ OLD CODE:")
            print('    data_path = "G:/Machine Learning/IBDownloads/"')
            print(
                '    file_path = data_path + f"{symbol}_USUSD_{timeframe}_{date}.ftr"'
            )
            print()
            print("✅ NEW CODE:")
            print("    from src.core import get_config")
            print("    config = get_config()")
            print("    file_path = config.get_data_file_path('ib_download',")
            print("                                          symbol=symbol,")
            print("                                          timeframe=timeframe,")
            print("                                          date_str=date)")

        # Example 2: Error handling
        if analysis["print_statements"]:
            print("\n🚨 Example 2: Improving Error Handling")
            print("-" * 42)
            print("❌ OLD CODE:")
            print("    try:")
            print("        result = risky_operation()")
            print("    except Exception as e:")
            print('        print(f"Error: {e}")')
            print()
            print("✅ NEW CODE:")
            print("    from src.core import handle_error")
            print("    try:")
            print("        result = risky_operation()")
            print("    except Exception as e:")
            print("        report = handle_error(e, module='YourModule',")
            print("                               function='your_function')")
            print("        # Error is now logged with ID and context")

        # Example 3: Data management
        print("\n📊 Example 3: Using DataManager")
        print("-" * 35)
        print("❌ OLD CODE:")
        print("    checker = requestCheckerCLS()")
        print("    if checker.check_file_exists(symbol, timeframe):")
        print("        data = checker.load_data()")
        print()
        print("✅ NEW CODE:")
        print("    from src.data.data_manager import DataManager")
        print("    dm = DataManager()")
        print("    if dm.data_exists(symbol, timeframe, date_str):")
        print("        # Use appropriate repository")
        print("        data = dm.feather_repo.load(identifier)")


def get_code_examples() -> list[dict[str, Any]]:
    """Get code migration examples."""
    return [
        {
            "title": "Replacing Hardcoded Paths",
            "old_code": [
                'data_path = "G:/Machine Learning/IBDownloads/"',
                'file_path = data_path + f"{symbol}_USUSD_{timeframe}_{date}.ftr"',
            ],
            "new_code": [
                "from src.core import get_config",
                "config = get_config()",
                "file_path = config.get_data_file_path('ib_download',",
                "                                      symbol=symbol,",
                "                                      timeframe=timeframe,",
                "                                      date_str=date)",
            ],
        },
        {
            "title": "Improving Error Handling",
            "old_code": [
                "try:",
                "    result = risky_operation()",
                "except Exception as e:",
                '    print(f"Error: {e}")',
            ],
            "new_code": [
                "from src.core import handle_error",
                "try:",
                "    result = risky_operation()",
                "except Exception as e:",
                "    report = handle_error(e, module='YourModule',",
                "                           function='your_function')",
                "    # Error is now logged with ID and context",
            ],
        },
        {
            "title": "Using DataManager",
            "old_code": [
                "checker = requestCheckerCLS()",
                "if checker.check_file_exists(symbol, timeframe):",
                "    data = checker.load_data()",
            ],
            "new_code": [
                "from src.data.data_manager import DataManager",
                "dm = DataManager()",
                "if dm.data_exists(symbol, timeframe, date_str):",
                "    # Use appropriate repository",
                "    data = dm.feather_repo.load(identifier)",
            ],
        },
    ]


def main(analyze_only: bool = False, include_examples: bool = True) -> dict[str, Any]:
    """Generate migration guide and analysis."""
    logger.info("Running migration guide analysis")

    # Import required modules
    try:
        from importlib.util import find_spec

        if (
            find_spec("src.core.config") is None
            or find_spec("src.core.error_handler") is None
        ):
            raise ImportError
    except ImportError:
        logger.warning("Unable to import core modules, running in limited mode")
        # Create minimal assistant for analysis
        assistant = type(
            "MockAssistant",
            (),
            {
                "workspace_root": Path(__file__).parent.parent,
                "analyze_codebase": lambda self: {
                    "files_analyzed": 0,
                    "hardcoded_paths": [],
                    "print_statements": [],
                    "error_handling_issues": [],
                    "monolithic_classes": [],
                },
                "generate_migration_plan": lambda self, analysis: [
                    "Migration requires core modules to be available"
                ],
            },
        )()
    else:
        assistant = CodeMigrationAssistant()

    # Analyze the current codebase
    analysis = assistant.analyze_codebase()

    result: dict[str, Any] = {
        "analysis": analysis,
        "next_steps": [
            "Review the migration plan",
            "Start with Priority 1 items (hardcoded paths)",
            "Use the new architecture components in src/",
            "Test each change thoroughly",
            "Run architecture_demo.py to verify setup",
        ],
        "architecture_components": {
            "configuration": "src/core/config.py",
            "error_handling": "src/core/error_handler.py",
            "data_management": "src/data/data_manager.py",
            "migration_helper": "src/migration_helper.py",
        },
    }

    if not analyze_only:
        # Generate migration plan
        plan = assistant.generate_migration_plan(analysis)
        result["migration_plan"] = plan

    if include_examples:
        result["code_examples"] = get_code_examples()

    return result


def run_cli() -> int:
    """CLI wrapper for the tool."""
    import argparse

    parser = argparse.ArgumentParser(description="Migration guide for trading system")
    parser.add_argument(
        "--analyze-only",
        action="store_true",
        help="Only analyze codebase, skip migration plan",
    )
    parser.add_argument(
        "--no-examples", action="store_true", help="Exclude code examples"
    )
    parser.add_argument("--describe", action="store_true", help="Show tool schemas")

    args = parser.parse_args()

    if args.describe:
        import json

        print(
            json.dumps(
                {"input_schema": INPUT_SCHEMA, "output_schema": OUTPUT_SCHEMA}, indent=2
            )
        )
        return 0

    result = main(analyze_only=args.analyze_only, include_examples=not args.no_examples)
    import json

    print(json.dumps(result, indent=2))

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(run_cli())
