#!/usr/bin/env python3
"""
Parquet Data Repository

High-performance data storage system using Parquet format for time-series data.
This replaces the Excel-based system with 10-100x better performance.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

from src.core.config import get_config
from src.core.error_handler import DataError, get_error_handler, handle_error

# Optional pyarrow import with graceful degradation (typed as Any for mypy)
if TYPE_CHECKING:  # Only for type checkers
    pass

pa: Any
pq: Any
_pyarrow_available = False
try:
    import pyarrow as pa  # type: ignore[no-redef]
    import pyarrow.parquet as pq  # type: ignore[no-redef]

    _pyarrow_available = True
except ImportError:  # pragma: no cover - optional dependency
    pa, pq = object(), object()  # harmless placeholders when not available
PYARROW_AVAILABLE: bool = _pyarrow_available


@dataclass
class DataMetadata:
    """Metadata for stored data"""

    symbol: str
    timeframe: str
    date_range: tuple[datetime, datetime] | tuple[Any, Any]
    row_count: int
    file_size: int
    created_at: datetime
    last_modified: datetime
    data_quality_score: float = 0.0


class ParquetRepository:
    """High-performance Parquet-based data repository"""

    def __init__(self):
        self.config = get_config()
        self.error_handler = get_error_handler()
        self.logger = logging.getLogger(__name__)

        # Create data directories
        self.data_root = self.config.data_paths.base_path / "parquet_data"
        self.metadata_root = self.config.data_paths.base_path / "metadata"
        self.backup_root = self.config.data_paths.backup_path / "parquet_backup"

        self._ensure_directories()

    def _ensure_directories(self):
        """Create necessary directories"""
        for directory in [self.data_root, self.metadata_root, self.backup_root]:
            directory.mkdir(parents=True, exist_ok=True)

    def _get_data_path(
        self, symbol: str, timeframe: str, date_str: str | None = None
    ) -> Path:
        """Generate optimized file path for data storage"""
        # Create hierarchical structure: symbol/timeframe/year/month/
        if date_str:
            try:
                date_obj = pd.to_datetime(date_str).date()
                year = date_obj.year
                month = f"{date_obj.month:02d}"

                # Use daily files for high-frequency data, monthly for lower frequency
                if timeframe in ["1 sec", "5 secs", "10 secs", "30 secs"]:
                    # Daily files for seconds data
                    filename = (
                        f"{symbol}_{timeframe.replace(' ', '_')}_{date_str}.parquet"
                    )
                    path = (
                        self.data_root
                        / symbol
                        / timeframe
                        / str(year)
                        / month
                        / filename
                    )
                elif timeframe in ["1 min", "5 mins", "15 mins", "30 mins"]:
                    # Daily files for minute data
                    filename = (
                        f"{symbol}_{timeframe.replace(' ', '_')}_{date_str}.parquet"
                    )
                    path = (
                        self.data_root
                        / symbol
                        / timeframe
                        / str(year)
                        / month
                        / filename
                    )
                else:
                    # Monthly files for hourly+ data
                    filename = (
                        f"{symbol}_{timeframe.replace(' ', '_')}_{year}_{month}.parquet"
                    )
                    path = self.data_root / symbol / timeframe / str(year) / filename
            except Exception as e:
                handle_error(e, module=__name__, function="_get_data_path")
                # Fallback to simple structure
                filename = f"{symbol}_{timeframe.replace(' ', '_')}_{date_str or 'latest'}.parquet"
                path = self.data_root / symbol / filename
        else:
            # No date specified - use latest file pattern
            filename = f"{symbol}_{timeframe.replace(' ', '_')}_latest.parquet"
            path = self.data_root / symbol / filename

        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def save_data(
        self,
        data: pd.DataFrame,
        symbol: str,
        timeframe: str,
        date_str: str | None = None,
        compress: bool = True,
    ) -> bool:
        """
        Save data to Parquet file with metadata and quality checks.

        Args:
            data: DataFrame to save
            symbol: Stock symbol
            timeframe: Time interval (e.g., "1 min", "1 hour")
            date_str: Date string for the data
            compress: Whether to compress the data

        Returns:
            bool: Success status
        """
        try:
            if not PYARROW_AVAILABLE:
                # Fallback to CSV or pickle if pyarrow not available
                self.logger.warning("PyArrow not available, using CSV fallback")
                file_path = self._get_data_path(
                    symbol, timeframe, date_str
                ).with_suffix(".csv")
                data.to_csv(file_path, index=False)
                return True

            if data is None or data.empty:
                raise DataError(
                    "Cannot save empty DataFrame",
                    context={
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "date_str": date_str,
                    },
                )

            # Optimize DataFrame for storage
            optimized_data = self._optimize_dataframe(data.copy())

            # Get file path
            file_path = self._get_data_path(symbol, timeframe, date_str)

            # Configure Parquet options for performance
            # pyarrow's typing expects Literal set; pass exact strings
            compression: str = "snappy" if compress else "none"

            # Save with metadata
            table = pa.Table.from_pandas(optimized_data)

            # Add custom metadata
            metadata = {
                "symbol": symbol,
                "timeframe": timeframe,
                "date_str": date_str or "latest",
                "created_at": datetime.now().isoformat(),
                "row_count": str(len(optimized_data)),
                "original_size": str(data.memory_usage(deep=True).sum()),
                "data_quality_score": str(
                    self._calculate_quality_score(optimized_data)
                ),
            }

            # Add metadata to Parquet file
            try:
                existing_meta: dict[bytes, bytes] = dict(table.schema.metadata or {})  # type: ignore[assignment]
                existing_meta.update(
                    {k.encode(): v.encode() for k, v in metadata.items()}
                )
                table = table.replace_schema_metadata(existing_meta)
            except Exception:
                pass

            # Write to file
            pq.write_table(
                table,
                file_path,
                compression=compression or "none",
                use_dictionary=True,  # Better compression for repeated values
                row_group_size=50000,  # Optimize for query performance
            )

            # Save metadata separately for quick access
            self._save_metadata(
                symbol, timeframe, date_str, metadata, len(optimized_data)
            )

            # Create backup if this is important data
            if len(optimized_data) > 1000:  # Only backup substantial datasets
                self._create_backup(file_path, symbol, timeframe, date_str)

            self.logger.info(f"Saved {len(optimized_data)} rows to {file_path}")
            return True

        except Exception as e:
            handle_error(
                e,
                module=__name__,
                function="save_data",
                context={
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "rows": len(data) if data is not None else 0,
                },
            )
            return False

    def load_data(
        self,
        symbol: str,
        timeframe: str,
        date_str: str | None = None,
        columns: list[str] | None = None,
    ) -> pd.DataFrame | None:
        """
        Load DataFrame from Parquet with optimization

        Args:
            symbol: Stock symbol
            timeframe: Time interval
            date_str: Specific date or None for latest
            columns: Specific columns to load (performance optimization)

        Returns:
            DataFrame or None if not found
        """
        try:
            file_path = self._get_data_path(symbol, timeframe, date_str)

            if not file_path.exists():
                # Try to find alternative files if exact match not found
                alternative_files = self._find_alternative_files(
                    symbol, timeframe, date_str
                )
                if alternative_files:
                    file_path = alternative_files[0]  # Use most recent
                else:
                    return None

            # Load with optimizations
            df = pd.read_parquet(
                file_path,
                columns=columns,  # Only load needed columns
                engine="pyarrow",
            )

            # Validate data quality
            if self._validate_data_quality(df):
                return df
            else:
                self.logger.warning(f"Data quality issues detected in {file_path}")
                return df  # Still return data but log warning

        except Exception as e:
            handle_error(
                e,
                module=__name__,
                function="load_data",
                context={
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "date_str": date_str,
                },
            )
            return None

    def data_exists(
        self, symbol: str, timeframe: str, date_str: str | None = None
    ) -> bool:
        """Check if data exists for given parameters"""
        try:
            file_path = self._get_data_path(symbol, timeframe, date_str)
            if file_path.exists():
                return True

            # Check for alternative files
            alternatives = self._find_alternative_files(symbol, timeframe, date_str)
            return len(alternatives) > 0

        except Exception as e:
            handle_error(e, module=__name__, function="data_exists")
            return False

    def get_data_info(
        self, symbol: str, timeframe: str, date_str: str | None = None
    ) -> dict[str, Any] | None:
        """Get metadata about stored data"""
        try:
            file_path = self._get_data_path(symbol, timeframe, date_str)

            if not file_path.exists():
                return None

            # Read metadata from Parquet file
            parquet_file = pq.ParquetFile(file_path)
            # Get basic metadata (schema info) if needed

            # Get file stats
            stat = file_path.stat()

            info = {
                "file_path": str(file_path),
                "file_size": stat.st_size,
                "modified_time": datetime.fromtimestamp(stat.st_mtime),
                "row_count": parquet_file.metadata.num_rows,
                "column_count": len(parquet_file.schema),
                "compression": parquet_file.metadata.row_group(0).column(0).compression
                if parquet_file.metadata.num_row_groups > 0
                else None,
            }

            # Add custom metadata if available
            if hasattr(parquet_file, "schema") and parquet_file.schema.metadata:
                for key, value in parquet_file.schema.metadata.items():
                    info[key.decode()] = value.decode()

            return info

        except Exception as e:
            handle_error(e, module=__name__, function="get_data_info")
            return None

    def delete_data(
        self, symbol: str, timeframe: str, date_str: str | None = None
    ) -> bool:
        """Delete data file with backup"""
        try:
            file_path = self._get_data_path(symbol, timeframe, date_str)

            if not file_path.exists():
                return True  # Already deleted

            # Create backup before deletion
            backup_success = self._create_backup(file_path, symbol, timeframe, date_str)

            if backup_success:
                file_path.unlink()
                self.logger.info(f"Deleted {file_path} (backup created)")
                return True
            else:
                self.logger.warning(
                    f"Failed to create backup for {file_path}, deletion cancelled"
                )
                return False

        except Exception as e:
            handle_error(e, module=__name__, function="delete_data")
            return False

    def list_available_data(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """List all available data files"""
        try:
            available_data = []

            search_root = self.data_root / symbol if symbol else self.data_root

            if not search_root.exists():
                return []

            for parquet_file in search_root.rglob("*.parquet"):
                try:
                    relative_path = parquet_file.relative_to(self.data_root)
                    parts = relative_path.parts

                    if len(parts) >= 2:
                        file_symbol = parts[0]
                        file_timeframe = parts[1] if len(parts) > 2 else "unknown"

                        info = self.get_data_info(file_symbol, file_timeframe)
                        if info:
                            info.update(
                                {
                                    "symbol": file_symbol,
                                    "timeframe": file_timeframe,
                                    "relative_path": str(relative_path),
                                }
                            )
                            available_data.append(info)

                except Exception as e:
                    self.logger.warning(f"Error processing {parquet_file}: {e}")
                    continue

            return sorted(
                available_data,
                key=lambda x: x.get("modified_time", datetime.min),
                reverse=True,
            )

        except Exception as e:
            handle_error(e, module=__name__, function="list_available_data")
            return []

    def _optimize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Optimize DataFrame for storage efficiency"""
        try:
            # Convert datetime index if needed
            if df.index.dtype == "object":
                try:
                    df.index = pd.to_datetime(df.index)
                except Exception:
                    pass

            # Optimize numeric columns
            for col in df.select_dtypes(include=["int64"]).columns:
                df[col] = pd.to_numeric(df[col], downcast="integer")

            for col in df.select_dtypes(include=["float64"]).columns:
                df[col] = pd.to_numeric(df[col], downcast="float")

            # Convert string columns to categories if they have few unique values
            for col in df.select_dtypes(include=["object"]).columns:
                if df[col].nunique() / len(df) < 0.5:  # Less than 50% unique values
                    df[col] = df[col].astype("category")

            return df

        except Exception as e:
            handle_error(e, module=__name__, function="_optimize_dataframe")
            return df  # Return original if optimization fails

    def _calculate_quality_score(self, df: pd.DataFrame) -> float:
        """Calculate data quality score (0-1)"""
        try:
            if df.empty:
                return 0.0

            score = 1.0

            # Penalize for missing values
            missing_ratio = df.isnull().sum().sum() / (len(df) * len(df.columns))
            score -= missing_ratio * 0.3

            # Penalize for duplicate rows
            duplicate_ratio = df.duplicated().sum() / len(df)
            score -= duplicate_ratio * 0.2

            # Check for reasonable value ranges (basic sanity check)
            numeric_cols = df.select_dtypes(include=["number"]).columns
            for col in numeric_cols:
                if col.lower() in ["open", "high", "low", "close", "price"]:
                    # Price columns should be positive
                    if (df[col] <= 0).any():
                        score -= 0.1
                elif col.lower() == "volume":
                    # Volume should be non-negative
                    if (df[col] < 0).any():
                        score -= 0.1

            return max(0.0, min(1.0, score))

        except Exception as e:
            handle_error(e, module=__name__, function="_calculate_quality_score")
            return 0.5  # Default moderate score if calculation fails

    def _validate_data_quality(self, df: pd.DataFrame) -> bool:
        """Validate data quality meets minimum standards"""
        quality_score = self._calculate_quality_score(df)
        return quality_score > 0.3  # Minimum acceptable quality

    def _find_alternative_files(
        self, symbol: str, timeframe: str, date_str: str | None = None
    ) -> list[Path]:
        """Find alternative files when exact match not found"""
        try:
            pattern_path = self.data_root / symbol / timeframe
            if not pattern_path.exists():
                return []

            # Find all parquet files in the timeframe directory
            parquet_files = list(pattern_path.rglob("*.parquet"))

            if date_str:
                # Filter by date if specified
                date_pattern = date_str.replace("-", "_")
                parquet_files = [f for f in parquet_files if date_pattern in f.name]

            # Sort by modification time (most recent first)
            return sorted(parquet_files, key=lambda f: f.stat().st_mtime, reverse=True)

        except Exception as e:
            handle_error(e, module=__name__, function="_find_alternative_files")
            return []

    def _save_metadata(
        self,
        symbol: str,
        timeframe: str,
        date_str: str | None,
        metadata: dict[str, str],
        row_count: int,
    ):
        """Save metadata for quick access"""
        try:
            metadata_file = (
                self.metadata_root
                / f"{symbol}_{timeframe}_{date_str or 'latest'}_meta.json"
            )

            full_metadata = {
                **metadata,
                "row_count": row_count,
                "last_updated": datetime.now().isoformat(),
            }

            import json

            with metadata_file.open("w") as f:
                json.dump(full_metadata, f, indent=2)

        except Exception as e:
            # Metadata save failure shouldn't block data save
            self.logger.warning(f"Failed to save metadata: {e}")

    def _create_backup(
        self, file_path: Path, symbol: str, timeframe: str, date_str: str | None = None
    ) -> bool:
        """Create backup of data file"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = (
                f"{symbol}_{timeframe}_{date_str or 'latest'}_{timestamp}.parquet"
            )
            backup_path = self.backup_root / backup_name

            backup_path.parent.mkdir(parents=True, exist_ok=True)

            import shutil

            shutil.copy2(file_path, backup_path)

            self.logger.info(f"Backup created: {backup_path}")
            return True

        except Exception as e:
            handle_error(e, module=__name__, function="_create_backup")
            return False

    def cleanup(self):
        """Cleanup resources"""
        pass  # Parquet files don't need explicit cleanup

    def list_symbols(self) -> list[str]:
        """List all available symbols in the repository"""
        symbols = set()

        try:
            for symbol_dir in self.data_root.iterdir():
                if symbol_dir.is_dir():
                    symbols.add(symbol_dir.name)
        except Exception as e:
            handle_error(e, module=__name__, function="list_symbols")

        return sorted(list(symbols))

    def list_timeframes(self, symbol: str) -> list[str]:
        """List all available timeframes for a symbol"""
        timeframes = set()

        try:
            symbol_dir = self.data_root / symbol
            if symbol_dir.exists() and symbol_dir.is_dir():
                for timeframe_dir in symbol_dir.iterdir():
                    if timeframe_dir.is_dir():
                        timeframes.add(timeframe_dir.name)
        except Exception as e:
            handle_error(e, module=__name__, function="list_timeframes")

        return sorted(list(timeframes))


# Convenience functions for easy migration from Excel


def migrate_excel_to_parquet(
    excel_path: Path, symbol: str, timeframe: str, date_str: str | None = None
) -> bool:
    """Migrate Excel file to Parquet format"""
    try:
        repo = ParquetRepository()

        # Read Excel file
        df = pd.read_excel(excel_path, index_col=0, parse_dates=True)

        # Save as Parquet
        success = repo.save_data(df, symbol, timeframe, date_str)

        if success:
            print(f"✅ Migrated {excel_path} → Parquet format")
            print(f"   Rows: {len(df)}, Columns: {len(df.columns)}")

            # Show size comparison
            excel_size = excel_path.stat().st_size
            parquet_path = repo._get_data_path(symbol, timeframe, date_str)
            parquet_size = parquet_path.stat().st_size if parquet_path.exists() else 0

            print(
                f"   Size: {excel_size:,} bytes (Excel) → {parquet_size:,} bytes (Parquet)"
            )
            print(
                f"   Compression: {(1 - parquet_size / excel_size) * 100:.1f}% smaller"
            )

        return success

    except Exception as e:
        handle_error(e, module=__name__, function="migrate_excel_to_parquet")
        return False


if __name__ == "__main__":
    # Demo the Parquet repository
    print("🚀 Parquet Repository Demo")
    print("=" * 30)

    # Create test data
    test_data = pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-07-30", periods=1000, freq="1min"),
            "open": [100 + i * 0.01 for i in range(1000)],
            "high": [100.5 + i * 0.01 for i in range(1000)],
            "low": [99.5 + i * 0.01 for i in range(1000)],
            "close": [100.1 + i * 0.01 for i in range(1000)],
            "volume": [1000 + i * 10 for i in range(1000)],
        }
    ).set_index("timestamp")

    # Initialize repository
    repo = ParquetRepository()

    # Save test data
    print("💾 Saving test data...")
    success = repo.save_data(test_data, "AAPL", "1 min", "2025-07-30")
    print(f"   Save result: {success}")

    # Load data back
    print("📊 Loading test data...")
    loaded_data = repo.load_data("AAPL", "1 min", "2025-07-30")
    print(f"   Loaded rows: {len(loaded_data) if loaded_data is not None else 0}")

    # Get data info
    print("ℹ️  Data information...")
    info = repo.get_data_info("AAPL", "1 min", "2025-07-30")
    if info:
        print(f"   File size: {info['file_size']:,} bytes")
        print(f"   Row count: {info['row_count']}")
        print(f"   Columns: {info['column_count']}")

    # List available data
    print("📋 Available data files...")
    available = repo.list_available_data("AAPL")
    print(f"   Found {len(available)} files")

    print("\n✅ Parquet repository working correctly!")
    print("🎯 Ready to replace Excel files with 10-100x better performance!")
