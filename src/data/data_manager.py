# Data management layer - Breaking down the monolithic requestCheckerCLS

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

# Import from the correct path
from ..core.config import ConfigManager, get_config
from ..core.dataframe_safety import SafeDataFrameAccessor
from ..core.error_handler import DataError, error_context, handle_error


@dataclass
class DownloadStatus:
    """Status of a data download operation"""

    symbol: str
    timeframe: str
    date: str
    success: bool
    data_size: int = 0
    error_message: str | None = None
    download_time: datetime | None = None


class BaseRepository(ABC):
    """Abstract base class for data repositories"""

    @abstractmethod
    def save(self, data: Any, identifier: str) -> bool:
        """Save data with given identifier"""
        pass

    @abstractmethod
    def load(self, identifier: str) -> Any:
        """Load data by identifier"""
        pass

    @abstractmethod
    def exists(self, identifier: str) -> bool:
        """Check if data exists"""
        pass

    @abstractmethod
    def delete(self, identifier: str) -> bool:
        """Delete data by identifier"""
        pass


class ExcelRepository(BaseRepository):
    """Repository for Excel file operations"""

    def __init__(self, config: ConfigManager):
        self.config = config
        self.logger = logging.getLogger(__name__)

    @error_context("ExcelRepository", "save")
    def save(self, data: pd.DataFrame, identifier: str) -> bool:
        """Save DataFrame to Excel file"""
        try:
            # Prefer standardized path if available; otherwise fallback to a generic file
            try:
                file_path = self.config.get_data_file_path("excel", symbol=identifier)
            except Exception:
                base = self.config.data_paths.base_path / "Machine Learning"
                base.mkdir(parents=True, exist_ok=True)
                file_path = base / f"{identifier}.xlsx"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            ok = SafeDataFrameAccessor.safe_to_excel(
                data, file_path, sheet_name="Sheet1", index=True, engine="openpyxl"
            )
            if not ok:
                raise DataError(f"Failed to save Excel file {identifier}: write failed")
            return ok
        except Exception as exc:
            raise DataError(
                f"Failed to save Excel file {identifier}: {str(exc)}"
            ) from exc

    @error_context("ExcelRepository", "load")
    def load(self, identifier: str) -> pd.DataFrame | None:
        """Load DataFrame from Excel file"""
        try:
            try:
                file_path = self.config.get_data_file_path("excel", symbol=identifier)
            except Exception:
                base = self.config.data_paths.base_path / "Machine Learning"
                file_path = base / f"{identifier}.xlsx"
            if file_path.exists():
                return SafeDataFrameAccessor.safe_read_excel(
                    file_path, sheet_name=0, header=0, engine="openpyxl"
                )
            return None
        except Exception as exc:
            raise DataError(
                f"Failed to load Excel file {identifier}: {str(exc)}"
            ) from exc

    def exists(self, identifier: str) -> bool:
        """Check if Excel file exists"""
        try:
            file_path = self.config.get_data_file_path("excel", symbol=identifier)
        except Exception:
            file_path = (
                self.config.data_paths.base_path
                / "Machine Learning"
                / f"{identifier}.xlsx"
            )
        return file_path.exists()

    def delete(self, identifier: str) -> bool:
        """Delete Excel file"""
        try:
            try:
                file_path = self.config.get_data_file_path("excel", symbol=identifier)
            except Exception:
                file_path = (
                    self.config.data_paths.base_path
                    / "Machine Learning"
                    / f"{identifier}.xlsx"
                )
            if file_path.exists():
                file_path.unlink()
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to delete Excel file {identifier}: {e}")
            return False


class FeatherRepository(BaseRepository):
    """Repository for Feather file operations"""

    def __init__(self, config: ConfigManager):
        self.config = config
        self.logger = logging.getLogger(__name__)

    @error_context("FeatherRepository", "save")
    def save(self, data: pd.DataFrame, identifier: str) -> bool:
        """Save DataFrame to Feather file"""
        try:
            # Parse identifier to get symbol, timeframe, date
            symbol, timeframe, date_str = self._parse_identifier(identifier)
            file_path = self.config.get_data_file_path(
                "ib_download", symbol=symbol, timeframe=timeframe, date_str=date_str
            )
            file_path.parent.mkdir(parents=True, exist_ok=True)

            data.to_feather(file_path)
            return True
        except Exception as exc:
            raise DataError(
                f"Failed to save Feather file {identifier}: {str(exc)}"
            ) from exc

    @error_context("FeatherRepository", "load")
    def load(self, identifier: str) -> pd.DataFrame | None:
        """Load DataFrame from Feather file"""
        try:
            symbol, timeframe, date_str = self._parse_identifier(identifier)
            file_path = self.config.get_data_file_path(
                "ib_download", symbol=symbol, timeframe=timeframe, date_str=date_str
            )
            if file_path.exists():
                return pd.read_feather(file_path)
            return None
        except Exception as exc:
            raise DataError(
                f"Failed to load Feather file {identifier}: {str(exc)}"
            ) from exc

    def exists(self, identifier: str) -> bool:
        """Check if Feather file exists"""
        try:
            symbol, timeframe, date_str = self._parse_identifier(identifier)
            file_path = self.config.get_data_file_path(
                "ib_download", symbol=symbol, timeframe=timeframe, date_str=date_str
            )
            return file_path.exists()
        except Exception:
            return False

    def delete(self, identifier: str) -> bool:
        """Delete Feather file"""
        try:
            symbol, timeframe, date_str = self._parse_identifier(identifier)
            file_path = self.config.get_data_file_path(
                "ib_download", symbol=symbol, timeframe=timeframe, date_str=date_str
            )
            if file_path.exists():
                file_path.unlink()
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to delete Feather file {identifier}: {e}")
            return False

    def _parse_identifier(self, identifier: str) -> tuple[str, str, str]:
        """Parse identifier into symbol, timeframe, date components"""
        # Expected format: "SYMBOL_TIMEFRAME_DATE"
        parts = identifier.split("_")
        if len(parts) >= 3:
            return parts[0], "_".join(parts[1:-1]), parts[-1]
        else:
            raise ValueError(f"Invalid identifier format: {identifier}")


class DownloadTracker:
    """Tracks download status and manages download history"""

    def __init__(self, config: ConfigManager):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.excel_repo = ExcelRepository(config)

        # Load tracking DataFrames
        self.df_failed = self._load_failed_downloads()
        self.df_downloadable = self._load_downloadable_stocks()
        self.df_downloaded = self._load_downloaded_stocks()

        # Track changes for batched saves
        self.failed_changes = 0
        self.downloadable_changes = 0
        self.downloaded_changes = 0

    def _load_failed_downloads(self) -> pd.DataFrame:
        """Load failed downloads tracking DataFrame"""
        try:
            file_path = self.config.get_data_file_path("excel_failed")
            if file_path.exists():
                df = SafeDataFrameAccessor.safe_read_excel(
                    file_path,
                    sheet_name=0,
                    header=0,
                    engine="openpyxl",
                    index_col="Stock",
                )
                if df is None:
                    return pd.DataFrame(index=pd.Index([], name="Stock"))
                return df
            else:
                return pd.DataFrame(index=pd.Index([], name="Stock"))
        except Exception as e:
            self.logger.warning(f"Could not load failed downloads: {e}")
            return pd.DataFrame(index=pd.Index([], name="Stock"))

    def _load_downloadable_stocks(self) -> pd.DataFrame:
        """Load downloadable stocks tracking DataFrame"""
        try:
            file_path = self.config.get_data_file_path("excel_downloadable")
            if file_path.exists():
                df = SafeDataFrameAccessor.safe_read_excel(
                    file_path,
                    sheet_name=0,
                    header=0,
                    engine="openpyxl",
                    index_col="Stock",
                )
                if df is None:
                    return pd.DataFrame(index=pd.Index([], name="Stock"))
                return df
            else:
                return pd.DataFrame(index=pd.Index([], name="Stock"))
        except Exception as e:
            self.logger.warning(f"Could not load downloadable stocks: {e}")
            return pd.DataFrame(index=pd.Index([], name="Stock"))

    def _load_downloaded_stocks(self) -> pd.DataFrame:
        """Load downloaded stocks tracking DataFrame"""
        try:
            file_path = self.config.get_data_file_path("excel_downloaded")
            if file_path.exists():
                df = SafeDataFrameAccessor.safe_read_excel(
                    file_path,
                    sheet_name=0,
                    header=0,
                    engine="openpyxl",
                    index_col="DateStock",
                )
                if df is None:
                    return pd.DataFrame(index=pd.Index([], name="DateStock"))
                return df
            else:
                return pd.DataFrame(index=pd.Index([], name="DateStock"))
        except Exception as e:
            self.logger.warning(f"Could not load downloaded stocks: {e}")
            return pd.DataFrame(index=pd.Index([], name="DateStock"))

    def mark_failed(
        self,
        symbol: str,
        timeframe: str,
        date_str: str,
        error_message: str,
        non_existent: bool = True,
    ) -> bool:
        """Mark a download as failed"""
        try:
            if symbol not in self.df_failed.index:
                # Create new entry
                self.df_failed.loc[symbol, "NonExistent"] = (
                    "Yes" if non_existent else "No"
                )
                self.df_failed.loc[symbol, "Stock"] = symbol

            # Add error details
            self.df_failed.loc[symbol, f"{timeframe}-LatestFailed"] = date_str

            # Add to comment columns
            for i in range(10):
                comment_col = f"Comment{i}"
                date_col = f"Date{i}"

                if comment_col not in self.df_failed.columns or pd.isnull(
                    self.df_failed.loc[symbol, comment_col]
                ):
                    self.df_failed.loc[symbol, date_col] = date_str
                    self.df_failed.loc[symbol, comment_col] = error_message
                    break

            self.failed_changes += 1

            # Auto-save if many changes
            if self.failed_changes >= 20:
                self.save_failed_downloads()

            return True
        except Exception as e:
            handle_error(
                e,
                context={"symbol": symbol, "timeframe": timeframe},
                module="DownloadTracker",
                function="mark_failed",
            )
            return False

    def mark_downloadable(
        self,
        symbol: str,
        timeframe: str,
        earliest_date: str,
        start_date: str = "",
        end_date: str = "",
    ) -> bool:
        """Mark a symbol as downloadable"""
        try:
            if symbol not in self.df_downloadable.index:
                self.df_downloadable.loc[symbol, "Stock"] = symbol

            self.df_downloadable.loc[symbol, "EarliestAvailBar"] = earliest_date
            if start_date:
                self.df_downloadable.loc[symbol, f"{timeframe}-StartDate"] = start_date
            if end_date:
                self.df_downloadable.loc[symbol, f"{timeframe}-EndDate"] = end_date

            self.downloadable_changes += 1

            if self.downloadable_changes >= 20:
                self.save_downloadable_stocks()

            return True
        except Exception as e:
            handle_error(
                e,
                context={"symbol": symbol, "timeframe": timeframe},
                module="DownloadTracker",
                function="mark_downloadable",
            )
            return False

    def mark_downloaded(self, symbol: str, timeframe: str, date_str: str) -> bool:
        """Mark a download as completed"""
        try:
            date_stock_key = f"{date_str}-{symbol}"

            if date_stock_key not in self.df_downloaded.index:
                self.df_downloaded.loc[date_stock_key, "Date"] = date_str
                self.df_downloaded.loc[date_stock_key, "Stock"] = symbol

            self.df_downloaded.loc[date_stock_key, timeframe] = "Yes"

            self.downloaded_changes += 1

            if self.downloaded_changes >= 20:
                self.save_downloaded_stocks()

            return True
        except Exception as e:
            handle_error(
                e,
                context={"symbol": symbol, "timeframe": timeframe},
                module="DownloadTracker",
                function="mark_downloaded",
            )
            return False

    def is_failed(self, symbol: str, timeframe: str, date_str: str = "") -> bool:
        """Check if a download is marked as failed"""
        try:
            if symbol not in self.df_failed.index:
                return False

            # Check if symbol is marked as non-existent
            non_existent = self.df_failed.loc[symbol, "NonExistent"]
            if non_existent == "Yes":
                return True

            # Check timeframe-specific failures
            latest_failed_col = f"{timeframe}-LatestFailed"
            if latest_failed_col in self.df_failed.columns:
                latest_failed = self.df_failed.loc[symbol, latest_failed_col]
                if pd.notna(latest_failed) and date_str:
                    # Convert both to strings for comparison
                    latest_failed_str = str(latest_failed)
                    if latest_failed_str >= date_str:
                        return True

            return False
        except Exception:
            return False

    def is_downloaded(self, symbol: str, timeframe: str, date_str: str) -> bool:
        """Check if data is already downloaded"""
        try:
            date_stock_key = f"{date_str}-{symbol}"

            if date_stock_key not in self.df_downloaded.index:
                return False

            downloaded_status = self.df_downloaded.loc[date_stock_key, timeframe]
            return downloaded_status == "Yes"
        except Exception:
            return False

    def save_all(self):
        """Save all tracking DataFrames"""
        self.save_failed_downloads()
        self.save_downloadable_stocks()
        self.save_downloaded_stocks()

    def save_failed_downloads(self):
        """Save failed downloads DataFrame"""
        try:
            if self.failed_changes > 0:
                file_path = self.config.get_data_file_path("excel_failed")
                df = self.df_failed.sort_index()
                # If 'Stock' exists as both column and index name, drop the column to avoid ambiguity
                if "Stock" in df.columns and df.index.name == "Stock":
                    df = df.drop(columns=["Stock"])
                SafeDataFrameAccessor.safe_to_excel(
                    df, file_path, sheet_name="Sheet1", index=True, engine="openpyxl"
                )
        except Exception as e:
            handle_error(e, module="DownloadTracker", function="save_failed_downloads")
        finally:
            if self.failed_changes > 0:
                self.failed_changes = 0

    def save_downloadable_stocks(self):
        """Save downloadable stocks DataFrame"""
        try:
            if self.downloadable_changes > 0:
                file_path = self.config.get_data_file_path("excel_downloadable")
                df = self.df_downloadable.sort_index()
                if "Stock" in df.columns and df.index.name == "Stock":
                    df = df.drop(columns=["Stock"])
                SafeDataFrameAccessor.safe_to_excel(
                    df, file_path, sheet_name="Sheet1", index=True, engine="openpyxl"
                )
        except Exception as e:
            handle_error(
                e, module="DownloadTracker", function="save_downloadable_stocks"
            )
        finally:
            if self.downloadable_changes > 0:
                self.downloadable_changes = 0

    def save_downloaded_stocks(self):
        """Save downloaded stocks DataFrame"""
        try:
            if self.downloaded_changes > 0:
                file_path = self.config.get_data_file_path("excel_downloaded")
                df = self.df_downloaded.sort_index()
                SafeDataFrameAccessor.safe_to_excel(
                    df, file_path, sheet_name="Sheet1", index=True, engine="openpyxl"
                )
        except Exception as e:
            handle_error(e, module="DownloadTracker", function="save_downloaded_stocks")
        finally:
            if self.downloaded_changes > 0:
                self.downloaded_changes = 0


class DataManager:
    """Main data management class that coordinates repositories and tracking"""

    def __init__(self, config: ConfigManager | None = None):
        self.config = config or get_config()
        self.logger = logging.getLogger(__name__)

        # Initialize repositories
        self.excel_repo = ExcelRepository(self.config)
        self.feather_repo = FeatherRepository(self.config)

        # Initialize download tracker
        self.download_tracker = DownloadTracker(self.config)

    def save_historical_data(
        self, data: pd.DataFrame, symbol: str, timeframe: str, date_str: str
    ) -> DownloadStatus:
        """Save historical data and update tracking"""
        try:
            identifier = f"{symbol}_{timeframe}_{date_str}"

            # Save data
            success = self.feather_repo.save(data, identifier)

            if success:
                # Update tracking
                self.download_tracker.mark_downloaded(symbol, timeframe, date_str)

                return DownloadStatus(
                    symbol=symbol,
                    timeframe=timeframe,
                    date=date_str,
                    success=True,
                    data_size=len(data),
                    download_time=datetime.now(),
                )
            else:
                return DownloadStatus(
                    symbol=symbol,
                    timeframe=timeframe,
                    date=date_str,
                    success=False,
                    error_message="Failed to save data",
                )
        except Exception as e:
            error_msg = f"Error saving historical data: {str(e)}"
            self.download_tracker.mark_failed(symbol, timeframe, date_str, error_msg)

            return DownloadStatus(
                symbol=symbol,
                timeframe=timeframe,
                date=date_str,
                success=False,
                error_message=error_msg,
            )

    def load_historical_data(
        self, symbol: str, timeframe: str, date_str: str
    ) -> pd.DataFrame | None:
        """Load historical data"""
        identifier = f"{symbol}_{timeframe}_{date_str}"
        return self.feather_repo.load(identifier)

    def data_exists(self, symbol: str, timeframe: str, date_str: str) -> bool:
        """Check if data exists"""
        return self.download_tracker.is_downloaded(symbol, timeframe, date_str)

    def is_download_failed(self, symbol: str, timeframe: str, date_str: str) -> bool:
        """Check if download previously failed"""
        return self.download_tracker.is_failed(symbol, timeframe, date_str)

    def get_download_summary(self) -> dict[str, Any]:
        """Get summary of download status"""
        return {
            "total_failed": len(self.download_tracker.df_failed),
            "total_downloadable": len(self.download_tracker.df_downloadable),
            "total_downloaded": len(self.download_tracker.df_downloaded),
            "pending_changes": {
                "failed": self.download_tracker.failed_changes,
                "downloadable": self.download_tracker.downloadable_changes,
                "downloaded": self.download_tracker.downloaded_changes,
            },
        }

    def cleanup(self):
        """Cleanup and save all pending changes"""
        self.download_tracker.save_all()

    # ---- Legacy convenience accessors (thin wrappers around service ops)
    def warrior_list(self) -> pd.DataFrame | None:
        """Load warrior trading list via data management service operations.

        Provided to ease migration from legacy DM.WarriorList("Load") calls.
        """
        try:
            from ..services.data_management_service import get_data_service

            return get_data_service().data_manager.warrior_list_operations("load")  # type: ignore[attr-defined]
        except Exception:
            return None

    def train_list_loadsave(
        self,
        mode: str = "Load",
        kind: str = "Warrior",
        records: list[dict[str, str]] | None = None,
    ) -> pd.DataFrame | None:
        """Load or save a training list.

        Parameters:
            mode: "Load" or "Save"
            kind: training list kind (e.g., Warrior)
            records: when saving, list of {Stock, DateStr}
        """
        try:
            from ..services.data_management_service import get_data_service

            svc = get_data_service().data_manager
            if mode.lower() == "load":
                return svc.train_list_operations("load", train_type=kind)  # type: ignore[attr-defined]
            if mode.lower() == "save" and records is not None:
                import pandas as _pd

                df = _pd.DataFrame(records)
                return svc.train_list_operations("save", train_type=kind, df=df)  # type: ignore[attr-defined]
            return None
        except Exception:
            return None
