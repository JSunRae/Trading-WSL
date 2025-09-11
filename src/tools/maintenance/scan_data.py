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
from typing import Any, cast

# Schema definitions for agent tool pattern
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "scan_path": {
            "type": "string",
            "default": ".",
            "description": "Path to scan for data files",
        },
        "file_types": {
            "type": "array",
            "items": {"type": "string"},
            "default": ["ftr", "xlsx", "csv", "parquet", "json"],
            "description": "File extensions to search for",
        },
        "detailed_analysis": {
            "type": "boolean",
            "default": True,
            "description": "Perform detailed analysis of found files",
        },
    },
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "scan_summary": {
            "type": "object",
            "properties": {
                "total_files": {"type": "integer"},
                "file_types_found": {"type": "array", "items": {"type": "string"}},
                "total_size_mb": {"type": "number"},
            },
        },
        "files_by_type": {
            "type": "object",
            "description": "Files grouped by extension",
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
                        "max": {"type": "string"},
                    },
                },
                "file_count": {"type": "integer"},
                "total_size_mb": {"type": "number"},
            },
        },
        "recommendations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Data management recommendations",
        },
        "next_steps": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Suggested next actions",
        },
    },
}

# Set up logging
logger = logging.getLogger(__name__)


# ---- small helpers to keep function complexity low ----
def _parse_symbol_from_filename(filename: str) -> str | None:
    parts = filename.replace(".ftr", "").split("_")
    if parts:
        sym = parts[0]
        if len(sym) <= 5 and sym.isalpha():
            return sym.upper()
    return None


def _detect_timeframe_from_filename(filename: str) -> str | None:
    mapping = {
        "_1s": "1 second",
        "_1M": "1 minute",
        "_30M": "30 minute",
        "_1Hour": "1 hour",
        "_1D": "1 day",
        "_Tick": "tick",
    }
    for needle, tf in mapping.items():
        if needle in filename:
            return tf
    return None


def _try_parse_date_token(token: str) -> date | None:
    try:
        if len(token) == 10 and token.count("-") == 2:
            return datetime.strptime(token, "%Y-%m-%d").date()
    except Exception:
        return None
    return None


def scan_for_data_files() -> dict[str, list[Path]]:
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

    found_files: dict[str, list[Path]] = {}

    for pattern in patterns:
        extension = pattern.split(".")[-1]
        files = list(Path().glob(pattern))

        if files:
            found_files[extension] = files
            print(f"  Found {len(files)} .{extension} files")

    return found_files


def _analyze_single_feather(file_path: Path, analysis: dict[str, Any]) -> None:
    try:
        stat = file_path.stat()
        analysis["file_sizes"].append(stat.st_size)
        analysis["total_size"] += stat.st_size

        filename = file_path.name
        symbol = _parse_symbol_from_filename(filename)
        if symbol:
            analysis["symbols"].add(symbol)

        timeframe = _detect_timeframe_from_filename(filename)
        if timeframe:
            analysis["timeframes"].add(timeframe)

        for token in filename.replace(".ftr", "").split("_"):
            d = _try_parse_date_token(token)
            if not d:
                continue
            if (
                analysis["date_range"]["min"] is None
                or d < analysis["date_range"]["min"]
            ):
                analysis["date_range"]["min"] = d
            if (
                analysis["date_range"]["max"] is None
                or d > analysis["date_range"]["max"]
            ):
                analysis["date_range"]["max"] = d
    except Exception as e:
        print(f"  Warning: Error analyzing {file_path}: {e}")


def analyze_feather_files(files: list[Path]) -> dict[str, Any]:
    """Analyze Feather files specifically."""
    print(f"\n📊 Analyzing {len(files)} Feather files...")

    analysis: dict[str, Any] = {
        "symbols": set(),
        "timeframes": set(),
        "date_range": {"min": None, "max": None},
        "file_sizes": [],
        "total_size": 0,
    }

    for file_path in files:
        _analyze_single_feather(file_path, analysis)

    return analysis


def check_data_freshness(analysis: dict[str, Any]) -> int | None:
    """Check how fresh the data is."""
    print("\n🕒 Checking data freshness...")

    today = date.today()

    if analysis.get("date_range", {}).get("max"):
        latest_date = cast(date, analysis["date_range"]["max"])
        days_old: int = int((today - latest_date).days)

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


def suggest_updates(analysis: dict[str, Any], days_old: int | None) -> None:
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


def print_summary(found_files: dict[str, list[Path]], analysis: dict[str, Any]) -> None:
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

    result: dict[str, Any] = {
        "scan_summary": {
            "total_files": 0,
            "file_types_found": [],
            "total_size_mb": 0.0,
        },
        "files_by_type": {},
        "feather_analysis": {
            "symbols": [],
            "timeframes": [],
            "date_range": {"min": None, "max": None},
            "file_count": 0,
            "total_size_mb": 0.0,
        },
        "recommendations": [],
        "next_steps": [
            "To update recent data: make update-recent",
            "To update all data: make update-warrior",
            "To record Level 2 data: make level2-test",
        ],
    }

    # Scan for data files
    try:
        found_files = scan_for_data_files()
    except Exception as e:  # pragma: no cover - unexpected filesystem issues
        logger.error(f"Data scan failed to enumerate files: {e}")
        scan_summary = cast(dict[str, Any], result["scan_summary"])  # narrow type
        scan_summary["total_files"] = -1
        recs = cast(list[str], result["recommendations"])  # narrow type
        recs.append(f"Scan failed: {e}")
        return result

    # Summarize counts
    total_files = sum(len(files) for files in found_files.values())
    scan_summary = cast(dict[str, Any], result["scan_summary"])  # narrow type
    scan_summary["total_files"] = total_files
    scan_summary["file_types_found"] = list(found_files.keys())
    result["files_by_type"] = {ext: len(files) for ext, files in found_files.items()}

    # Analyze feather files if found
    if "ftr" in found_files:
        feather_files = found_files["ftr"]
        feather_analysis = analyze_feather_files(feather_files)
        result["feather_analysis"] = feather_analysis

    # Add recommendations based on findings
    recs = cast(list[str], result["recommendations"])  # narrow type
    if total_files == 0:
        recs.append("No data files found - run initial data collection")
    elif "ftr" not in found_files:
        recs.append("No feather files found - consider converting existing data")
    else:
        recs.append("Data files found - consider updating recent data")

    logger.info(f"Scan completed - found {total_files} files")
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Data scanner and analyzer")
    parser.add_argument(
        "--describe", action="store_true", help="Show tool description and schemas"
    )
    args = parser.parse_args()

    if args.describe:
        print(
            json.dumps(
                {
                    "description": "Data Scanner - Scan and report on existing trading data",
                    "input_schema": INPUT_SCHEMA,
                    "output_schema": OUTPUT_SCHEMA,
                },
                indent=2,
            )
        )
    else:
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
        )
        logger = logging.getLogger(__name__)
        result = main()
        print(json.dumps(result, indent=2))
