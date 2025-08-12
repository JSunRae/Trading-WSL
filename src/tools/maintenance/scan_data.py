#!/usr/bin/env python3
"""
@agent.tool scan_data

Data Scanner - Scan and report on existing trading data
This script scans your trading data directories and provides a comprehensive report on what data you have, what's missing, and what needs updating.
"""

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

# Schema definitions for agent tool pattern
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "scan_path": {
            "type": "string",
            "default": ".",
            "description": "Path to scan for data files"
        },
        "file_types": {
            "type": "array",
            "items": {"type": "string"},
            "default": ["ftr", "xlsx", "csv", "parquet", "json"],
            "description": "File extensions to search for"
        },
        "detailed_analysis": {
            "type": "boolean",
            "default": True,
            "description": "Perform detailed analysis of found files"
        }
    }
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "scan_summary": {
            "type": "object",
            "properties": {
                "total_files": {"type": "integer"},
                "file_types_found": {"type": "array", "items": {"type": "string"}},
                "total_size_mb": {"type": "number"}
            }
        },
        "files_by_type": {
            "type": "object",
            "description": "Files grouped by extension"
        },
        "feather_analysis": {
            "type": "object",
            "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}},
                "timeframes": {"type": "array", "items": {"type": "string"}},
                "date_range": {
                    "type": "object",
                    "properties": {
                        "min": {"type": "string"},
                        "max": {"type": "string"}
                    }
                },
                "file_count": {"type": "integer"},
                "total_size_mb": {"type": "number"}
            }
        },
        "recommendations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Data management recommendations"
        },
        "next_steps": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Suggested next actions"
        }
    }
}

# Set up logging
logger = logging.getLogger(__name__)


def scan_for_data_files():
    """Scan for existing data files."""
    print("🔍 Scanning for existing data files...")

    # Common data file patterns
    patterns = [
        "**/*.ftr",  # Feather files (your main format)
        "**/*.xlsx",  # Excel files
        "**/*.csv",  # CSV files
        "**/*.parquet",  # Parquet files
        "**/*.json",  # JSON files
    ]

    found_files = {}

    for pattern in patterns:
        extension = pattern.split(".")[-1]
        files = list(Path().glob(pattern))

        if files:
            found_files[extension] = files
            print(f"  Found {len(files)} .{extension} files")

    return found_files


def analyze_feather_files(files):
    """Analyze Feather files specifically."""
    print(f"\n📊 Analyzing {len(files)} Feather files...")

    analysis = {
        "symbols": set(),
        "timeframes": set(),
        "date_range": {"min": None, "max": None},
        "file_sizes": [],
        "total_size": 0,
    }

    for file_path in files:
        try:
            # Get file info
            stat = file_path.stat()
            analysis["file_sizes"].append(stat.st_size)
            analysis["total_size"] += stat.st_size

            # Parse filename for symbol and timeframe info
            filename = file_path.name

            # Try to extract symbol (usually at the beginning)
            parts = filename.replace(".ftr", "").split("_")
            if parts:
                potential_symbol = parts[0]
                if len(potential_symbol) <= 5 and potential_symbol.isalpha():
                    analysis["symbols"].add(potential_symbol.upper())

            # Extract timeframe info
            if "_1s" in filename:
                analysis["timeframes"].add("1 second")
            elif "_1M" in filename:
                analysis["timeframes"].add("1 minute")
            elif "_30M" in filename:
                analysis["timeframes"].add("30 minute")
            elif "_1Hour" in filename:
                analysis["timeframes"].add("1 hour")
            elif "_1D" in filename:
                analysis["timeframes"].add("1 day")
            elif "_Tick" in filename:
                analysis["timeframes"].add("tick")

            # Try to extract date
            for part in parts:
                if len(part) == 10 and part.count("-") == 2:  # YYYY-MM-DD format
                    try:
                        file_date = datetime.strptime(part, "%Y-%m-%d").date()
                        if (
                            analysis["date_range"]["min"] is None
                            or file_date < analysis["date_range"]["min"]
                        ):
                            analysis["date_range"]["min"] = file_date
                        if (
                            analysis["date_range"]["max"] is None
                            or file_date > analysis["date_range"]["max"]
                        ):
                            analysis["date_range"]["max"] = file_date
                    except ValueError:
                        continue

        except Exception as e:
            print(f"  Warning: Error analyzing {file_path}: {e}")

    return analysis


def check_data_freshness(analysis):
    """Check how fresh the data is."""
    print("\n🕒 Checking data freshness...")

    today = date.today()

    if analysis.get("date_range", {}).get("max"):
        latest_date = analysis["date_range"]["max"]
        days_old = (today - latest_date).days

        print(f"  Latest data: {latest_date} ({days_old} days ago)")

        if days_old == 0:
            print("  ✅ Data is current (today)")
        elif days_old <= 1:
            print("  ✅ Data is recent (yesterday)")
        elif days_old <= 7:
            print("  ⚠️ Data is somewhat old (within a week)")
        else:
            print("  ❌ Data is stale (more than a week old)")

        return days_old
    else:
        print("  ❓ Could not determine data freshness")
        return None


def suggest_updates(analysis, days_old):
    """Suggest what updates might be needed."""
    print("\n💡 Update Suggestions:")

    if days_old is None:
        print("  • Run data scanner to check existing data")
        return

    if days_old > 1:
        print(f"  • Update recent data (last {days_old} days)")
        print("    Command: make update-recent")

    if analysis.get("symbols"):
        num_symbols = len(analysis["symbols"])
        print(f"  • Full update for {num_symbols} symbols")
        print("    Command: make update-warrior")

    if "tick" not in analysis.get("timeframes", set()):
        print("  • Consider adding tick data for high-frequency analysis")

    if "1 second" not in analysis.get("timeframes", set()):
        print("  • Consider adding 1-second data for detailed analysis")


def print_summary(found_files, analysis):
    """Print comprehensive summary."""
    print("\n" + "=" * 60)
    print("📋 DATA SUMMARY REPORT")
    print("=" * 60)

    # File types summary
    print("File Types:")
    total_files = 0
    for ext, files in found_files.items():
        print(f"  {ext.upper()}: {len(files)} files")
        total_files += len(files)
    print(f"  TOTAL: {total_files} files")

    if "ftr" in found_files:
        # Detailed analysis for main data files
        print("\nMain Data (Feather files):")
        print(
            f"  Symbols: {len(analysis['symbols'])} ({', '.join(sorted(list(analysis['symbols']))[:10])}{'...' if len(analysis['symbols']) > 10 else ''})"
        )
        print(f"  Timeframes: {', '.join(sorted(analysis['timeframes']))}")

        if analysis["date_range"]["min"] and analysis["date_range"]["max"]:
            print(
                f"  Date range: {analysis['date_range']['min']} to {analysis['date_range']['max']}"
            )

        # File size info
        total_mb = analysis["total_size"] / (1024 * 1024)
        avg_mb = (
            (analysis["total_size"] / len(analysis["file_sizes"])) / (1024 * 1024)
            if analysis["file_sizes"]
            else 0
        )
        print(f"  Total size: {total_mb:.1f} MB")
        print(f"  Average file size: {avg_mb:.1f} MB")

    print("=" * 60)


def main() -> dict[str, Any]:
    """Main entry point for data scanning."""
    logger.info("Starting data scan")

    result = {
        "scan_summary": {
            "total_files": 0,
            "file_types_found": [],
            "total_size_mb": 0.0
        },
        "files_by_type": {},
        "feather_analysis": {
            "symbols": [],
            "timeframes": [],
            "date_range": {"min": None, "max": None},
            "file_count": 0,
            "total_size_mb": 0.0
        },
        "recommendations": [],
        "next_steps": [
            "To update recent data: make update-recent",
            "To update all data: make update-warrior",
            "To record Level 2 data: make level2-test"
        ]
    }

    try:
        # Scan for data files
        found_files = scan_for_data_files()

        total_files = sum(len(files) for files in found_files.values())
        result["scan_summary"]["total_files"] = total_files
        result["scan_summary"]["file_types_found"] = list(found_files.keys())
        result["files_by_type"] = {ext: len(files) for ext, files in found_files.items()}

        # Analyze feather files if found
        if "ftr" in found_files:
            feather_files = found_files["ftr"]
            feather_analysis = analyze_feather_files(feather_files)
            if isinstance(feather_analysis, dict):
                result["feather_analysis"] = feather_analysis

        # Add recommendations based on findings
        if total_files == 0:
            result["recommendations"].append("No data files found - run initial data collection")
        elif "ftr" not in found_files:
            result["recommendations"].append("No feather files found - consider converting existing data")
        else:
            result["recommendations"].append("Data files found - consider updating recent data")

        logger.info(f"Scan completed - found {total_files} files")

    except Exception as e:
        logger.error(f"Data scan failed: {e}")
        result["scan_summary"]["total_files"] = -1
        result["recommendations"].append(f"Scan failed: {e}")

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Data scanner and analyzer")
    parser.add_argument(
        "--describe", action="store_true", help="Show tool description and schemas"
    )
    args = parser.parse_args()

    if args.describe:
        print(json.dumps({
            "description": "Data Scanner - Scan and report on existing trading data",
            "input_schema": INPUT_SCHEMA,
            "output_schema": OUTPUT_SCHEMA
        }, indent=2))
    else:
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
        )
        logger = logging.getLogger(__name__)
        result = main()
        print(json.dumps(result, indent=2))
