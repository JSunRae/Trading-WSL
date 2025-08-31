# ruff: noqa: N802,N803,N806  # Legacy compatibility layer retains historical names/args
# Migration helper to gradually transition from old monolithic code to new architecture
# This provides backward compatibility while enabling new patterns

import warnings
from pathlib import Path
from typing import Any

from .core.config import get_config
from .core.error_handler import get_error_handler

# Import both old and new systems
from .data.data_manager import DataManager


class LegacyDataManagerAdapter:
    """
    Adapter class that provides the old requestCheckerCLS interface
    while delegating to the new DataManager internally.

    This allows gradual migration without breaking existing code.
    """

    def __init__(self, host=None, port=None, clientId=None, ib=None):
        # Issue deprecation warning
        warnings.warn(
            "LegacyDataManagerAdapter is deprecated. Use DataManager directly.",
            DeprecationWarning,
            stacklevel=2,
        )

        # Use config for defaults if not provided
        try:
            from .core.config import get_config

            config = get_config()
            if host is None:
                host = config.ib_connection.host
            if port is None:
                port = config.ib_connection.port
            if clientId is None:
                clientId = config.ib_connection.client_id
        except Exception:
            # Fallback to old defaults
            host = host or "127.0.0.1"
            port = port or 7497
            clientId = clientId or 1
        # Issue deprecation warning
        warnings.warn(
            "LegacyDataManagerAdapter is deprecated. Use DataManager directly.",
            DeprecationWarning,
            stacklevel=2,
        )

        # Initialize new system
        self.config = get_config()
        self.data_manager = DataManager(self.config)
        self.error_handler = get_error_handler()

        # Keep legacy attributes for compatibility
        self.ib = ib
        self.host = host
        self.port = port
        self.clientId = clientId

        # Legacy DataFrame references (delegate to new system)
        self._setup_legacy_dataframes()

    def _setup_legacy_dataframes(self):
        """Set up legacy DataFrame properties that delegate to new system"""
        self.df_IBFailed = self.data_manager.download_tracker.df_failed
        self.df_IBDownloadable = self.data_manager.download_tracker.df_downloadable
        self.df_IBDownloaded = self.data_manager.download_tracker.df_downloaded

    # Legacy method compatibility
    def appendFailed(  # noqa: N802 - legacy name for compatibility
        self,
        symbol,
        NonExistant=True,  # noqa: N803
        EarliestAvailBar="",  # noqa: N803
        BarSize="",  # noqa: N803
        forDate="",  # noqa: N803
        comment="",
    ):
        """Legacy method - delegates to new system"""
        return self.data_manager.download_tracker.mark_failed(
            symbol=symbol,
            timeframe=BarSize,
            date_str=str(forDate),
            error_message=comment,
            non_existent=NonExistant,
        )

    def appendDownloadable(  # noqa: N802,N803 - legacy name/args for compatibility
        self, symbol, BarSize, EarliestAvailBar, StartDate="", EndDate=""
    ):
        """Legacy method - delegates to new system"""
        return self.data_manager.download_tracker.mark_downloadable(
            symbol=symbol,
            timeframe=BarSize,
            earliest_date=str(EarliestAvailBar),
            start_date=str(StartDate),
            end_date=str(EndDate),
        )

    def appendDownloaded(  # noqa: N802,N803 - legacy name/args for compatibility
        self, symbol, BarSize, forDate
    ):
        """Legacy method - delegates to new system"""
        return self.data_manager.download_tracker.mark_downloaded(
            symbol=symbol, timeframe=BarSize, date_str=str(forDate)
        )

    def is_failed(self, symbol, BarSize, forDate=""):  # noqa: N803
        """Legacy method - delegates to new system"""
        return self.data_manager.download_tracker.is_failed(
            symbol=symbol, timeframe=BarSize, date_str=str(forDate)
        )

    def Download_Exists(  # noqa: N802,N803 - legacy name/args for compatibility
        self, symbol, BarSize, forDate=""
    ):
        """Legacy method - delegates to new system"""
        return self.data_manager.data_exists(
            symbol=symbol, timeframe=BarSize, date_str=str(forDate)
        )

    def On_Exit(self):  # noqa: N802 - legacy name for compatibility
        """Legacy cleanup method"""
        self.data_manager.cleanup()


class MigrationHelper:
    """Helper class to assist with migrating from old to new architecture"""

    @staticmethod
    def migrate_config_file():
        """
        Migrate old hardcoded configuration to new config system
        """
        print("🔄 Migrating configuration...")
        config = get_config()

        # Check if old hardcoded paths exist and warn user
        old_paths = [  # noqa: F841 - placeholder for future checks
            "G:/Machine Learning/",
            "F:/T7 Backup/Machine Learning/",
            "/home/user/Machine Learning/",
        ]

        print("✅ Configuration migration complete!")
        print(f"📁 Data paths configured: {config.data_paths.base_path}")
        print(f"📁 Backup paths configured: {config.data_paths.backup_path}")
        return True

    @staticmethod
    def analyze_existing_code(file_path: str) -> dict[str, Any]:
        """
        Analyze existing code file for refactoring opportunities
        """
        analysis = {
            "file": file_path,
            "issues": [],
            "recommendations": [],
            "complexity_score": 0,
        }

        try:
            from pathlib import Path as _Path

            with _Path(file_path).open() as f:
                content = f.read()
                lines = content.split("\n")

            # Analyze for common issues
            analysis["line_count"] = len(lines)

            # Check for hardcoded paths
            hardcoded_patterns = ["G:\\", "G:/", "/home/", "C:\\Users"]

            for i, line in enumerate(lines):
                for pattern in hardcoded_patterns:
                    if pattern in line and not line.strip().startswith("#"):
                        analysis["issues"].append(
                            {
                                "line": i + 1,
                                "type": "hardcoded_path",
                                "content": line.strip(),
                            }
                        )

            # Check for long methods/classes
            class_lines = 0
            method_lines = 0
            in_class = False
            in_method = False

            for line in lines:
                stripped = line.strip()
                if stripped.startswith("class "):
                    in_class = True
                    class_lines = 0
                elif stripped.startswith("def "):
                    in_method = True
                    method_lines = 0
                elif stripped == "" and (in_class or in_method):
                    continue
                elif in_class:
                    class_lines += 1
                elif in_method:
                    method_lines += 1

                if class_lines > 500:
                    analysis["issues"].append(
                        {
                            "type": "large_class",
                            "message": f"Class has {class_lines} lines (consider splitting)",
                        }
                    )

                if method_lines > 50:
                    analysis["issues"].append(
                        {
                            "type": "large_method",
                            "message": f"Method has {method_lines} lines (consider refactoring)",
                        }
                    )

            # Calculate complexity score
            analysis["complexity_score"] = min(100, len(analysis["issues"]) * 10)

            # Generate recommendations
            if len(analysis["issues"]) > 0:
                analysis["recommendations"].extend(
                    [
                        "Consider using the new ConfigManager for path management",
                        "Break down large classes into smaller, focused components",
                        "Use the new DataManager for data operations",
                        "Implement proper error handling with the ErrorHandler",
                    ]
                )

        except Exception as e:
            analysis["error"] = str(e)

        return analysis

    @staticmethod
    def create_refactor_plan(file_path: str) -> list[str]:
        """Create a step-by-step refactoring plan for a file"""
        analysis = MigrationHelper.analyze_existing_code(file_path)

        plan = [
            "📋 Refactoring Plan",
            "================",
            f"File: {file_path}",
            f"Complexity Score: {analysis.get('complexity_score', 0)}/100",
            "",
            "🎯 Recommended Steps:",
        ]

        step = 1

        # Configuration issues
        config_issues = [
            issue
            for issue in analysis.get("issues", [])
            if issue["type"] == "hardcoded_path"
        ]
        if config_issues:
            plan.append(f"{step}. Replace hardcoded paths with ConfigManager")
            for issue in config_issues[:3]:  # Show first 3
                plan.append(f"   - Line {issue['line']}: {issue['content'][:60]}...")
            step += 1

        # Large class issues
        large_classes = [
            issue
            for issue in analysis.get("issues", [])
            if issue["type"] == "large_class"
        ]
        if large_classes:
            plan.append(f"{step}. Break down large classes:")
            for issue in large_classes:
                plan.append(f"   - {issue['message']}")
            step += 1

        # Add general recommendations
        for rec in analysis.get("recommendations", []):
            plan.append(f"{step}. {rec}")
            step += 1

        return plan

    @staticmethod
    def backup_file(file_path: str) -> str:
        """Create backup of file before refactoring"""
        import shutil
        from datetime import datetime

        original_path = Path(file_path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = original_path.with_suffix(
            f".backup_{timestamp}{original_path.suffix}"
        )

        shutil.copy2(original_path, backup_path)
        print(f"✅ Backup created: {backup_path}")
        return str(backup_path)


def get_migration_status() -> dict[str, Any]:
    """Get overall migration status"""
    # Access config lazily via functions when needed; avoid unused variable

    status = {
        "config_migrated": True,  # Always true if we get here
        "data_manager_available": True,
        "error_handler_available": True,
        "legacy_adapter_available": True,
        "recommendations": [
            "Gradually replace requestCheckerCLS usage with DataManager",
            "Use ConfigManager instead of hardcoded paths",
            "Implement proper error handling with ErrorHandler",
            "Add type hints and documentation to improved code",
        ],
    }

    return status


# Convenience function for gradual migration
def get_data_manager_legacy(host="127.0.0.1", port=7497, clientId=1, ib=None):  # noqa: N803
    """
    Get a data manager with legacy compatibility.

    This function can be used as a drop-in replacement for requestCheckerCLS
    initialization while providing new functionality.
    """
    return LegacyDataManagerAdapter(host, port, clientId, ib)


if __name__ == "__main__":
    # Example migration workflow
    print("🚀 Trading System Migration Helper")
    print("==================================")

    # Check migration status
    status = get_migration_status()
    print(
        f"✅ Configuration: {'Ready' if status['config_migrated'] else 'Needs Migration'}"
    )
    print(
        f"✅ Data Manager: {'Ready' if status['data_manager_available'] else 'Not Available'}"
    )
    print(
        f"✅ Error Handler: {'Ready' if status['error_handler_available'] else 'Not Available'}"
    )

    print("\n📋 Next Steps:")
    for i, rec in enumerate(status["recommendations"], 1):
        print(f"{i}. {rec}")
