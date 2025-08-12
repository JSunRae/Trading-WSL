#!/usr/bin/env python3
"""
Root directory cleanup analyzer
Analyzes Python files in root and creates move plan
"""

import csv
import os
import re


def analyze_python_file(filepath: str) -> dict[str, str]:
    """Analyze a Python file to determine its role and target location."""
    try:
        with open(filepath, encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return {
            "role": "unknown",
            "target": "manual_review",
            "reason": f"read_error: {e}",
            "confidence": "0.3"
        }

    filename = os.path.basename(filepath)

    # Check for main entrypoint
    has_main = 'if __name__ == "__main__":' in content

    # Check imports to understand usage
    imports = re.findall(r'^\s*(?:from|import)\s+([a-zA-Z_][a-zA-Z0-9_.]*)', content, re.MULTILINE)

    # Specific file analysis based on name patterns and content
    if filename.startswith('test_'):
        return {
            "role": "test",
            "target": f"tests/{filename}",
            "reason": "test file (test_ prefix)",
            "confidence": "0.9"
        }

    # Infrastructure modules
    infra_files = [
        'ib_client.py', 'ib_requests.py', 'contract_factories.py',
        'async_utils.py', 'async_utils_new.py'
    ]
    if filename in infra_files:
        return {
            "role": "infra",
            "target": f"src/infra/{filename}",
            "reason": "IB/async infrastructure module",
            "confidence": "0.9"
        }

    # Data helpers
    if 'pandas_helpers.py' == filename:
        return {
            "role": "data_helper",
            "target": "src/data/pandas_helpers.py",
            "reason": "data processing helper utilities",
            "confidence": "0.9"
        }

    # Setup tools
    setup_patterns = ['setup_', 'install_', 'configure_']
    if any(pattern in filename for pattern in setup_patterns):
        return {
            "role": "setup_tool",
            "target": f"src/tools/setup/{filename}",
            "reason": "setup/installation tool",
            "confidence": "0.9"
        }

    # Analysis tools
    analysis_patterns = ['analyze', 'analysis', 'check', 'validate', 'script_inventory']
    if any(pattern in filename for pattern in analysis_patterns):
        return {
            "role": "analysis_tool",
            "target": f"src/tools/analysis/{filename}",
            "reason": "analysis/reporting tool",
            "confidence": "0.9"
        }

    # Migration tools
    migration_patterns = ['migrate', 'migration', 'demo']
    if any(pattern in filename for pattern in migration_patterns):
        return {
            "role": "migration_tool",
            "target": f"src/tools/migration/{filename}",
            "reason": "migration/demo tool",
            "confidence": "0.8"
        }

    # Example/demo files
    if filename.startswith('example_') or 'demo' in filename:
        return {
            "role": "example",
            "target": f"examples/{filename}",
            "reason": "example/demo code",
            "confidence": "0.8"
        }

    # Type definitions
    if 'types' in filename:
        return {
            "role": "types",
            "target": f"src/types/{filename}",
            "reason": "type definitions",
            "confidence": "0.8"
        }

    # CLI tools with main
    if has_main and 'quick_start' in filename:
        return {
            "role": "cli_tool",
            "target": f"src/tools/{filename}",
            "reason": "CLI tool with main entrypoint",
            "confidence": "0.8"
        }

    # Default for unclear files
    return {
        "role": "unknown",
        "target": f"src/tools/misc/{filename}",
        "reason": "unclear role, needs manual review",
        "confidence": "0.4"
    }

def main():
    # Get all Python files in root
    root_files = []
    for file in os.listdir('.'):
        if file.endswith('.py') and os.path.isfile(file):
            root_files.append(file)

    print("🔍 **ROOT DIRECTORY PYTHON FILES AUDIT**")
    print("=" * 80)
    print(f"Found {len(root_files)} Python files in root directory")
    print()

    # Analyze each file
    move_plan = []
    for filepath in sorted(root_files):
        analysis = analyze_python_file(filepath)
        move_plan.append({
            'current_path': filepath,
            'target_path': analysis['target'],
            'role': analysis['role'],
            'reason': analysis['reason'],
            'confidence': analysis['confidence']
        })

        conf_float = float(analysis['confidence'])
        conf_icon = "✅" if conf_float >= 0.7 else "⚠️" if conf_float >= 0.5 else "❌"
        print(f"{conf_icon} {filepath:<35} → {analysis['target']:<45} ({analysis['confidence']})")

    # Save as CSV
    with open('root_cleanup_move_plan.csv', 'w', newline='') as csvfile:
        fieldnames = ['current_path', 'target_path', 'role', 'reason', 'confidence']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(move_plan)

    # Summary statistics
    high_confidence = [item for item in move_plan if float(item['confidence']) >= 0.7]
    medium_confidence = [item for item in move_plan if 0.5 <= float(item['confidence']) < 0.7]
    low_confidence = [item for item in move_plan if float(item['confidence']) < 0.5]

    print("\n📊 **DRY-RUN MOVE PLAN SUMMARY**:")
    print(f"  ✅ High confidence (≥0.7): {len(high_confidence)} files")
    print(f"  ⚠️  Medium confidence (0.5-0.7): {len(medium_confidence)} files")
    print(f"  ❌ Low confidence (<0.5): {len(low_confidence)} files")
    print("  📋 Move plan saved to: root_cleanup_move_plan.csv")

    print("\n📋 **DETAILED MOVE PLAN**:")
    print(f"{'File':<35} {'Target':<45} {'Role':<15} {'Conf'}")
    print("-" * 100)
    for item in move_plan:
        conf_icon = "✅" if float(item['confidence']) >= 0.7 else "⚠️" if float(item['confidence']) >= 0.5 else "❌"
        print(f"{conf_icon} {item['current_path']:<33} {item['target_path']:<43} {item['role']:<13} {item['confidence']}")

    if low_confidence:
        print("\n⚠️  **FILES REQUIRING MANUAL REVIEW**:")
        for item in low_confidence:
            print(f"  • {item['current_path']} - {item['reason']}")

    return move_plan

if __name__ == "__main__":
    move_plan = main()
