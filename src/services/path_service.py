"""
Path Service

This service handles all file path generation and location management,
extracted from the monolithic MasterPy_Trading.py file.
Provides centralized path management with platform-specific handling.
"""

import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

try:
    from ..core.config import get_config
    from ..core.error_handler import get_error_handler

    config_manager = get_config()
    error_handler = get_error_handler()
except ImportError:
    config_manager = None
    error_handler = None

# Version constant for compatibility
VERSION = "V1"

# Global location for compatibility during transition
if config_manager is not None:
    try:
        LOC_G = str(config_manager.data_paths.base_path)
        if not LOC_G.endswith("/"):
            LOC_G += "/"
    except Exception:
        LOC_G = str(Path.home() / "Machine Learning/")
else:
    LOC_G = str(Path.home() / "Machine Learning/")


def handle_error(module: str, message: str, duration: int = 60) -> None:
    """Fallback error handling for transition period"""
    if error_handler:
        try:
            from ..core.error_handler import TradingSystemError

            error = TradingSystemError(message)
            error_handler.handle_error(error, {"module": module, "duration": duration})
        except Exception:
            print(f"ERROR [{module}]: {message}")
    else:
        print(f"ERROR [{module}]: {message}")


def ensure_directory_exists(location: str | Path) -> None:
    """Ensure directory exists, create if necessary"""
    try:
        Path(location).mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"Warning: Could not create directory {location}: {e}")


class PathService:
    """Service for managing file paths and locations"""

    def __init__(self):
        self.config = config_manager
        self.version = VERSION
        self._setup_base_paths()

    def _setup_base_paths(self):
        """Setup base paths based on configuration or platform"""
        if self.config:
            try:
                data_paths = self.config.data_paths
                base = str(data_paths.base_path)
                if not base.endswith(("/", "\\")):
                    base += "/"
                self.base_path = base
                self.downloads_path = (
                    self.base_path + self.config.get_env("IB_DOWNLOADS_DIRNAME") + "/"
                )
                self.stocks_path = self.base_path + "Stocks/"
                return
            except Exception as e:
                print(f"Warning: Could not get config paths: {e}")

        # Fallback to user home path only (remove Windows drive hardcode)
        self.base_path = str(Path.home() / "Machine Learning/")
        self.downloads_path = self.base_path + "IBDownloads/"
        self.stocks_path = self.base_path + "Stocks/"

    def get_ib_download_location(
        self,
        stock_code: str,
        bar_config: Any,
        date_str: str | datetime | date = "",
        file_ext: str = ".ftr",
    ) -> Path:
        """Get Interactive Brokers download file location"""
        if not file_ext.startswith("."):
            file_ext = "." + file_ext

        # Handle different date string formats
        if hasattr(date_str, "strftime") and callable(
            getattr(date_str, "strftime", None)
        ):
            date_str = date_str.strftime("%Y-%m-%d %H:%M:%S")
        elif hasattr(date_str, "__class__") and "Timestamp" in str(type(date_str)):
            date_str = str(date_str)

        # Determine bar string based on bar type
        bar_type_map = {
            0: "_Tick",
            1: "_1s",
            2: "_1M",
            3: "_30M",
            4: "_1Hour",
            5: "_1D",
        }

        bar_type = getattr(bar_config, "bar_type", 0)
        if bar_type in bar_type_map:
            bar_str = bar_type_map[bar_type]
        else:
            handle_error(__name__, "Timeframe must be day/hour/minute/second/tick")
            bar_str = "_Unknown"

        # Handle date string formatting for filename
        if bar_type <= 2:  # ticks, seconds, 1-minute need date strings
            if date_str == "":
                handle_error(__name__, "need start and end string")
                date_str = ""
            else:
                if isinstance(date_str, date | datetime):
                    date_str = "_" + date_str.strftime("%Y-%m-%d")
                else:
                    date_str = "_" + str(date_str)[:10]
        else:
            date_str = ""

        filename = f"{stock_code}_USUSD{bar_str}{date_str}{file_ext}"
        ensure_directory_exists(self.downloads_path)

        return Path(self.downloads_path + filename)

    def _compute_date_suffix(
        self, bar_type: int, date_str: str | datetime | date
    ) -> str:
        """Return an underscore-prefixed date suffix or empty string based on bar_type."""
        if bar_type <= 2:
            if date_str == "":
                handle_error(__name__, "ticks need start and end string")
                return ""
            if isinstance(date_str, date):
                return "_" + date_str.strftime("%Y-%m-%d")
            return "_" + str(date_str)[:10]
        return ""

    def _normalize_file_ext(self, file_ext: str) -> str:
        return file_ext if file_ext.startswith(".") else "." + file_ext

    def _resolve_bar_str(self, bar_config: Any) -> str:
        bar_str = getattr(bar_config, "BarStr", None) or getattr(
            bar_config, "bar_str", None
        )
        if bar_str is not None:
            return bar_str
        bs_val = getattr(bar_config, "BarSize", getattr(bar_config, "bar_size", ""))
        s = bs_val.lower() if isinstance(bs_val, str) else ""
        if "tick" in s:
            return "_Tick"
        if "sec" in s:
            return "_1s"
        if "30" in s and "min" in s:
            return "_30m"
        if "min" in s:
            return "_1m"
        if "hour" in s or "1 hour" in s:
            return "_1h"
        if "day" in s or "1 day" in s or s == "1d":
            return "_1d"
        return "_Unknown"

    def _normalize_scalar_type(self, st: str) -> str:
        low = st.lower()
        if "st" in low:
            return "Std"
        if "min" in low:
            return "MinMax"
        handle_error(__name__, "Scalar type needs to be Standard or Min Max.")
        return "Unknown"

    def _resolve_scalar_context(
        self,
        scalar_what: str,
        bar_config: Any | None,
        feature_str: str | None,
    ) -> tuple[str, str]:
        if feature_str is not None:
            low = scalar_what.lower()
            if "float" in low:
                scalar_what = "float_"
            elif "outstanding" in low:
                scalar_what = "outstanding-shares_"
            elif "short" in low:
                scalar_what = "shares-short_"
            elif "volume" in low:
                scalar_what = "av-volume"
            else:
                handle_error(__name__, "Scalar type needs to be for Prices or Volumes")
            return "Fr", scalar_what
        if bar_config is not None:
            scalar_for_local = getattr(bar_config, "bar_str", "_Unknown")
            low = scalar_what.lower()
            if low.startswith("p"):
                scalar_what = "prices"
            elif low.startswith("v"):
                scalar_what = "volumes"
            else:
                handle_error(__name__, "Scalar type needs to be for Prices or Volumes")
            return scalar_for_local, scalar_what
        handle_error(__name__, "Scalar needs a BarObj or a FeatureStr")
        return "Unknown", scalar_what

    def get_dataframe_location(
        self,
        stock_code: str,
        bar_config: Any,
        date_str: str | datetime | date,
        normalised: bool,
        file_ext: str = ".ftr",
        create_cx_file: bool = False,
    ) -> Path:
        """Get dataframe file location"""
        location = self._df_base_location(stock_code, create_cx_file, file_ext)
        date_suffix = self._date_suffix_from_bar_config(bar_config, date_str)
        bar_str = self._resolve_bar_str(bar_config)
        ext = self._normalize_file_ext(file_ext)
        filename = self._build_df_filename(
            stock_code, bar_str, normalised, date_suffix, ext
        )
        return Path(location + filename)

    def _df_base_location(
        self, stock_code: str, create_cx_file: bool, file_ext: str
    ) -> str:
        if create_cx_file:
            if file_ext != ".xlsx":
                handle_error(
                    __name__, "This should be a xlsx file if its a Check file", 60
                )
            location = self.base_path + "CxData - "
        else:
            location = self.stocks_path + stock_code + "/Dataframes/"
        ensure_directory_exists(location)
        return location

    def _date_suffix_from_bar_config(
        self, bar_config: Any, date_str: str | datetime | date
    ) -> str:
        bt = getattr(bar_config, "bar_type", getattr(bar_config, "BarType", 0))
        return self._compute_date_suffix(int(bt), date_str)

    def _build_df_filename(
        self,
        stock_code: str,
        bar_str: str,
        normalised: bool,
        date_suffix: str,
        file_ext: str,
    ) -> str:
        norm_suffix = "_NORM" if normalised else "_df"
        return (
            f"{stock_code}{bar_str}{norm_suffix}_{self.version}{date_suffix}{file_ext}"
        )

    def get_level2_location(
        self,
        stock_code: str,
        start_str: str | datetime | date,
        end_str: str | datetime | date,
        normalised: bool,
        file_ext: str = ".ftr",
        create_cx_file: bool = False,
    ) -> Path:
        """Get Level 2 market depth file location"""
        if create_cx_file:
            location = self.base_path + "CxData - "
            if file_ext != ".xlsx":
                handle_error(
                    __name__, "This should be a xlsx file if its a Check file", 60
                )
        else:
            location = self.stocks_path + stock_code + "/Dataframes/"

        ensure_directory_exists(location)

        # Format start and end strings
        if isinstance(start_str, date) and not isinstance(start_str, datetime):
            start_str = "_" + datetime.combine(start_str, datetime.min.time()).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        elif isinstance(start_str, datetime):
            start_str = "_" + start_str.strftime("%Y-%m-%d %H:%M:%S")
        else:
            start_str = "_" + str(start_str)

        if isinstance(end_str, date) and not isinstance(end_str, datetime):
            end_str = "_" + datetime.combine(end_str, datetime.min.time()).strftime(
                "%H:%M:%S"
            )
        elif isinstance(end_str, datetime):
            end_str = "_" + end_str.strftime("%H:%M:%S")
        else:
            end_str = "_" + str(end_str)

        # Normalization suffix
        norm_suffix = "_NORM" if normalised else "_df"

        # File extension handling
        if not file_ext.startswith("."):
            file_ext = "." + file_ext

        filename = f"{stock_code}_L2_{norm_suffix}_{self.version}{start_str} to {end_str}{file_ext}"

        return Path(location + filename)

    def get_training_location(
        self, stock_code: str, date_str: str | datetime | date, train_type: str = ""
    ) -> Path:
        """Get training data file location"""
        # Determine if features or labels
        train_type_lower = train_type.lower()
        if "y" in train_type_lower or "label" in train_type_lower:
            train_type = "TrainY"
        elif "x" in train_type_lower or "feature" in train_type_lower:
            train_type = "TrainX"
        else:
            handle_error(__name__, "Could not determine if it is a Feature or Label")
            train_type = "TrainUnknown"

        location = self.stocks_path + stock_code + "/Dataframes/"
        ensure_directory_exists(location)

        # Format date string
        if isinstance(date_str, datetime | date):
            date_formatted = date_str.strftime("%Y%m%d")
        else:
            date_formatted = (
                str(date_str).replace("-", "").replace(" ", "").replace(":", "")[:8]
            )

        filename = f"{stock_code}_1s_{train_type}_{self.version}_{date_formatted}.ftr"

        return Path(location + filename)

    def get_scalar_location(
        self,
        scalar_type: str,
        scalar_what: str,
        bar_config: Any | None = None,
        feature_str: str | None = None,
        load_scalar: bool = True,
    ) -> Path | Any:
        """Get scalar file location or load scalar"""
        file_path = self._scalar_file_path(
            scalar_type, scalar_what, bar_config, feature_str
        )
        if load_scalar:
            return self._load_scalar_from_file(file_path)
        return file_path

    def _scalar_file_path(
        self,
        scalar_type: str,
        scalar_what: str,
        bar_config: Any | None,
        feature_str: str | None,
    ) -> Path:
        location = self.base_path + "Scalars/"
        ensure_directory_exists(location)
        stype = self._normalize_scalar_type(scalar_type)
        sfor, swhat = self._resolve_scalar_context(scalar_what, bar_config, feature_str)
        filename = f"scaler_{stype}{sfor}_{swhat}.bin"
        return Path(location + filename)

    def _load_scalar_from_file(self, file_path: Path) -> Any | None:
        try:
            from joblib import load

            return load(str(file_path))
        except Exception as e:  # pragma: no cover - IO dependent
            handle_error(__name__, f"Could not load scalar from {file_path}: {e}")
            return None

    def get_excel_review_location(self, name: str = "") -> Path:
        """Get location for Excel review files"""
        if name == "":
            name = "For Review"

        # Build candidate path using pathlib and ensure uniqueness
        base = Path(self.base_path) / f"Temp-{name}.xlsx"
        path = base
        count = 1

        while path.exists():
            count += 1
            path = Path(self.base_path) / f"Temp-{name}-{count}.xlsx"

        return path

    def get_ib_status_files(self) -> dict[str, Path]:
        """Get Interactive Brokers status file locations (centralized)"""
        if self.config:
            return {
                "failed": self.config.get_data_file_path("ib_failed_stocks"),
                "downloadable": self.config.get_data_file_path(
                    "ib_downloadable_stocks"
                ),
                "downloaded": self.config.get_data_file_path("ib_downloaded_stocks"),
            }
        return {
            "failed": Path(self.base_path + "IB Failed Stocks.xlsx"),
            "downloadable": Path(self.base_path + "IB Downloadable Stocks.xlsx"),
            "downloaded": Path(self.base_path + "IB Downloaded Stocks.xlsx"),
        }

    def get_request_checker_location(self) -> Path:
        """Get request checker binary file location (centralized)"""
        if self.config:
            try:
                return self.config.get_special_file("request_checker_bin")
            except Exception:
                return Path("./Files/requestChecker.bin")
        return Path("./Files/requestChecker.bin")

    def validate_path(self, path: str | Path) -> bool:
        """Validate if path is accessible"""
        try:
            path_obj = Path(path)
            return path_obj.parent.exists() or path_obj.exists()
        except Exception:
            return False

    def create_directory_structure(self, stock_code: str) -> None:
        """Create complete directory structure for a stock"""
        base_dir = self.stocks_path + stock_code
        directories = [
            base_dir,
            base_dir + "/Dataframes",
            base_dir + "/Models",
            base_dir + "/Analysis",
            base_dir + "/Reports",
        ]

        for directory in directories:
            ensure_directory_exists(directory)

    def get_path_summary(self) -> dict[str, Any]:
        """Get summary of all configured paths"""
        return {
            "base_path": self.base_path,
            "downloads_path": self.downloads_path,
            "stocks_path": self.stocks_path,
            "version": self.version,
            "platform": sys.platform,
            "config_available": self.config is not None,
        }


# Backward compatibility functions
def IB_Download_Loc(  # noqa: N802 - legacy API name maintained for compatibility
    stock_code: str, bar_obj: Any, date_str: str = "", file_ext: str = ".ftr"
) -> Path:
    """Backward compatibility function for IB download location"""
    service = get_path_service()
    return service.get_ib_download_location(stock_code, bar_obj, date_str, file_ext)


def IB_Df_Loc(  # noqa: N802 - legacy API name maintained for compatibility
    stock_code: str,
    bar_obj: Any,
    date_str: str,
    normalised: bool,
    file_ext: str = ".ftr",
    create_cx_file: bool = False,
) -> Path:
    """Backward compatibility function for dataframe location"""
    service = get_path_service()
    return service.get_dataframe_location(
        stock_code, bar_obj, date_str, normalised, file_ext, create_cx_file
    )


def IB_L2_Loc(  # noqa: N802 - legacy API name maintained for compatibility
    stock_code: str,
    start_str: str | datetime | date,
    end_str: str | datetime | date,
    normalised: bool,
    file_ext: str = ".ftr",
    create_cx_file: bool = False,
) -> Path:
    """Backward compatibility function for Level 2 location"""
    service = get_path_service()
    return service.get_level2_location(
        stock_code, start_str, end_str, normalised, file_ext, create_cx_file
    )


def IB_Train_Loc(  # noqa: N802 - legacy API name maintained for compatibility
    stock_code: str, date_str: str | datetime | date, train_type: str = ""
) -> Path:
    """Backward compatibility function for training location"""
    service = get_path_service()
    return service.get_training_location(stock_code, date_str, train_type)


def IB_Scalar(  # noqa: N802 - legacy API name maintained for compatibility
    scalar_type: str,
    scalar_what: str,
    load_scalar: bool = True,
    bar_obj: Any | None = None,
    feature_str: str | None = None,
) -> Path | Any:
    """Backward compatibility function for scalar location"""
    service = get_path_service()
    return service.get_scalar_location(
        scalar_type, scalar_what, bar_obj, feature_str, load_scalar
    )


# Singleton service instance
_path_service = None


def get_path_service() -> PathService:
    """Get singleton path service"""
    global _path_service
    if _path_service is None:
        _path_service = PathService()
    return _path_service
