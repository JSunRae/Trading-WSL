#!/usr/bin/env python3
"""
Critical Issue Fix #1: Eliminate Hardcoded Paths

This script addresses the immediate critical issue of hardcoded paths
throughout the system by migrating them to use the ConfigManager.

Priority: IMMEDIATE (Week 1)
Impact: Platform independence, environment portability, team development
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


class HardcodedPathFixer:
    """Fixes hardcoded paths throughout the codebase"""

    def __init__(self):
        self.project_root = Path(__file__).parent
        self.fixes_made = 0
        self.files_processed = 0

        # Patterns to find and fix
        self.hardcoded_patterns = [
            (
                r'"G:/Machine Learning/"',
                'config.data_paths.base_path / "Machine Learning"',
            ),
            (
                r"'G:/Machine Learning/'",
                'config.data_paths.base_path / "Machine Learning"',
            ),
            (
                r'"G:\\Machine Learning\\\\"',
                'config.data_paths.base_path / "Machine Learning"',
            ),
            (
                r"'G:\\Machine Learning\\\\'",
                'config.data_paths.base_path / "Machine Learning"',
            ),
            (
                r'"G:/Machine Learning/IB Failed Stocks\.xlsx"',
                'config.get_data_file_path("ib_failed_stocks")',
            ),
            (
                r'"G:/Machine Learning/IB Downloadable Stocks\.xlsx"',
                'config.get_data_file_path("ib_downloadable_stocks")',
            ),
            (
                r'"G:/Machine Learning/IB Downloaded Stocks\.xlsx"',
                'config.get_data_file_path("ib_downloaded_stocks")',
            ),
            (
                r'LocG = "G:\\Machine Learning\\\\"',
                'LocG = str(config.data_paths.base_path / "Machine Learning")',
            ),
            (
                r"LocG = 'G:/Machine Learning/'",
                'LocG = str(config.data_paths.base_path / "Machine Learning")',
            ),
            (
                r'os\.path\.expanduser\("~/Machine Learning/"\)',
                'str(config.data_paths.base_path / "Machine Learning")',
            ),
        ]

    def find_python_files(self) -> list[Path]:
        """Find all Python files that need to be processed"""
        python_files = []

        # Search in main source directories
        search_dirs = [
            self.project_root / "src",
            self.project_root,  # Root level files
        ]

        for search_dir in search_dirs:
            if search_dir.exists():
                python_files.extend(search_dir.glob("**/*.py"))

        # Filter out specific files we don't want to modify
        exclude_patterns = [
            "test_",
            "__pycache__",
            ".git",
            "venv",
            "env",
            "build",
            "dist",
        ]

        filtered_files = []
        for file_path in python_files:
            if not any(pattern in str(file_path) for pattern in exclude_patterns):
                filtered_files.append(file_path)

        return filtered_files

    def analyze_file(self, file_path: Path) -> dict[str, list[tuple[int, str]]]:
        """Analyze a file for hardcoded paths"""
        try:
            with file_path.open(encoding="utf-8") as f:
                content = f.read()
                lines = content.split("\n")
        except (UnicodeDecodeError, PermissionError) as e:
            print(f"⚠️  Could not read {file_path}: {e}")
            return {}

        findings = {}

        for i, line in enumerate(lines, 1):
            for pattern, _ in self.hardcoded_patterns:
                if re.search(pattern, line):
                    if pattern not in findings:
                        findings[pattern] = []
                    findings[pattern].append((i, line.strip()))

        return findings

    def fix_file(self, file_path: Path) -> bool:
        """Fix hardcoded paths in a single file"""
        try:
            with file_path.open(encoding="utf-8") as f:
                content = f.read()
        except (UnicodeDecodeError, PermissionError) as e:
            print(f"⚠️  Could not read {file_path}: {e}")
            return False

        original_content = content
        fixes_in_file = 0

        # Add import for ConfigManager if we're making fixes
        needs_config_import = False
        for pattern, _ in self.hardcoded_patterns:
            if re.search(pattern, content):
                needs_config_import = True
                break

        if needs_config_import:
            # Check if config import already exists
            if (
                "from src.core.config import" not in content
                and "import src.core.config" not in content
            ):
                # Add import after other imports
                import_pattern = r"(import [^\n]+\n|from [^\n]+ import [^\n]+\n)+"
                import_match = re.search(import_pattern, content)
                if import_match:
                    import_end = import_match.end()
                    content = (
                        content[:import_end]
                        + "\n# Added for hardcoded path fix\n"
                        + "from src.core.config import get_config\n"
                        + "config = get_config()\n\n"
                        + content[import_end:]
                    )
                else:
                    # Add at the beginning if no imports found
                    content = (
                        "# Added for hardcoded path fix\n"
                        + "from src.core.config import get_config\n"
                        + "config = get_config()\n\n"
                        + content
                    )

        # Apply pattern fixes
        for pattern, replacement in self.hardcoded_patterns:
            if re.search(pattern, content):
                content = re.sub(pattern, replacement, content)
                fixes_in_file += re.subn(pattern, replacement, original_content)[1]

        # Only write if changes were made
        if content != original_content:
            try:
                with file_path.open("w", encoding="utf-8") as f:
                    f.write(content)
                self.fixes_made += fixes_in_file
                print(
                    f"✅ Fixed {fixes_in_file} hardcoded paths in {file_path.relative_to(self.project_root)}"
                )
                return True
            except PermissionError as e:
                print(f"⚠️  Could not write to {file_path}: {e}")
                return False

        return False

    def add_config_helper_methods(self):
        """Add helper methods to the config system for common file paths"""
        config_file = self.project_root / "src" / "core" / "config.py"

        if not config_file.exists():
            print(f"⚠️  Config file not found: {config_file}")
            return False

        try:
            with config_file.open(encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            print(f"⚠️  Could not read config file: {e}")
            return False

        # Check if helper methods already exist
        if "get_data_file_path" in content:
            print("✅ Config helper methods already exist")
            return True

        # Add helper methods to ConfigManager class
        helper_methods = '''
    def get_data_file_path(self, file_type: str) -> Path:
        """Get path for common data files"""
        file_paths = {
            "ib_failed_stocks": self.data_paths.base_path / "Machine Learning" / "IB Failed Stocks.xlsx",
            "ib_downloadable_stocks": self.data_paths.base_path / "Machine Learning" / "IB Downloadable Stocks.xlsx",
            "ib_downloaded_stocks": self.data_paths.base_path / "Machine Learning" / "IB Downloaded Stocks.xlsx",
            "warrior_trading_trades": self.data_paths.base_path / "Machine Learning" / "WarriorTrading_Trades.xlsx",
            "ib_stocklist": self.data_paths.base_path / "Machine Learning" / "IB_StockList.ftr",
        }

        if file_type not in file_paths:
            raise ValueError(f"Unknown file type: {file_type}")

        # Ensure directory exists
        file_paths[file_type].parent.mkdir(parents=True, exist_ok=True)
        return file_paths[file_type]

    def get_download_path(self, symbol: str, bar_size: str, date_str: str = None) -> Path:
        """Get path for IB download files"""
        downloads_dir = self.data_paths.base_path / "Machine Learning" / "IBDownloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)

        if date_str:
            filename = f"{symbol}_USUSD_{bar_size}_{date_str}.ftr"
        else:
            filename = f"{symbol}_USUSD_{bar_size}.ftr"

        return downloads_dir / filename
'''

        # Find the end of the ConfigManager class
        class_pattern = r"class ConfigManager:.*?(?=\nclass|\nif __name__|\Z)"
        class_match = re.search(class_pattern, content, re.DOTALL)

        if class_match:
            # Find the last method in the class
            class_content = class_match.group(0)
            # Add helper methods before the end of the class
            new_class_content = class_content.rstrip() + helper_methods + "\n"
            content = content.replace(class_content, new_class_content)
        else:
            print("⚠️  Could not find ConfigManager class to add helper methods")
            return False

        try:
            with config_file.open("w", encoding="utf-8") as f:
                f.write(content)
            print("✅ Added helper methods to ConfigManager")
            return True
        except Exception as e:
            print(f"⚠️  Could not write config file: {e}")
            return False

    def run_analysis(self) -> dict[Path, dict[str, list[tuple[int, str]]]]:
        """Run analysis on all Python files"""
        print("🔍 Analyzing codebase for hardcoded paths...")

        python_files = self.find_python_files()
        print(f"📁 Found {len(python_files)} Python files to analyze")

        all_findings = {}
        files_with_issues = 0

        for file_path in python_files:
            findings = self.analyze_file(file_path)
            if findings:
                all_findings[file_path] = findings
                files_with_issues += 1

        print(f"⚠️  Found hardcoded paths in {files_with_issues} files")
        return all_findings

    def run_fixes(self) -> bool:
        """Run fixes on all Python files"""
        print("🔧 Starting hardcoded path fixes...")

        # First, add helper methods to config
        self.add_config_helper_methods()

        python_files = self.find_python_files()
        print(f"📁 Processing {len(python_files)} Python files")

        files_fixed = 0

        for file_path in python_files:
            if self.fix_file(file_path):
                files_fixed += 1
            self.files_processed += 1

        print("\n📊 Fix Results:")
        print(f"   📁 Files processed: {self.files_processed}")
        print(f"   ✅ Files fixed: {files_fixed}")
        print(f"   🔧 Total fixes applied: {self.fixes_made}")

        return files_fixed > 0


def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(description="Fix hardcoded paths in codebase")
    parser.add_argument("--describe", action="store_true", help="Show tool description")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be fixed without making changes",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    if args.describe:
        describe_info = {
            "name": "fix_hardcoded_paths.py",
            "description": "Fix hardcoded paths throughout the codebase using ConfigManager",
            "inputs": ["--dry-run", "--verbose"],
            "outputs": ["Modified Python files", "console report"],
            "dependencies": ["pathlib", "re"],
        }
        print(json.dumps(describe_info, indent=2))
        return True

    print("🚨 CRITICAL ISSUE FIX #1: Hardcoded Paths")
    print("=" * 50)
    print("Priority: IMMEDIATE")
    print("Impact: Platform independence, environment portability")
    print()

    fixer = HardcodedPathFixer()

    # First run analysis
    print("PHASE 1: Analysis")
    print("-" * 20)
    findings = fixer.run_analysis()

    if not findings:
        print("✅ No hardcoded paths found! System is clean.")
        return True

    # Show findings
    print("\n📋 Hardcoded Paths Found:")
    for file_path, file_findings in findings.items():
        print(f"\n📄 {file_path.relative_to(fixer.project_root)}")
        for pattern, locations in file_findings.items():
            print(f"   🔍 Pattern: {pattern}")
            for line_num, line_content in locations[:3]:  # Show first 3 matches
                print(f"      Line {line_num}: {line_content}")
            if len(locations) > 3:
                print(f"      ... and {len(locations) - 3} more matches")

    # Ask for confirmation
    print(f"\n⚠️  Found hardcoded paths in {len(findings)} files")
    print("This will:")
    print("• Add ConfigManager imports where needed")
    print("• Replace hardcoded paths with config-based paths")
    print("• Add helper methods to ConfigManager")
    print("• Make the system platform-independent")

    response = input("\n🤔 Proceed with fixes? (y/N): ").strip().lower()
    if response != "y":
        print("❌ Fixes cancelled by user")
        return False

    # Run fixes
    print("\nPHASE 2: Applying Fixes")
    print("-" * 25)
    success = fixer.run_fixes()

    if success:
        print("\n🎉 SUCCESS! Hardcoded paths have been eliminated.")
        print("\n🔄 Next Steps:")
        print("• Test the system to ensure all paths work correctly")
        print("• Update any deployment scripts to use ConfigManager")
        print("• Verify cross-platform compatibility")
        print("• Move to Critical Issue #2: Monolithic Class Decomposition")
        return True
    else:
        print("\n❌ No fixes were needed or applied")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
