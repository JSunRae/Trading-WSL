"""
Data Management Service

This service handles file operations, data loading/saving, and Excel utilities,
extracted from the monolithic MasterPy_Trading.py file.
Provides centralized data management with error handling and format support.
"""

import os
from pathlib import Path
from typing import Any, Literal

import pandas as pd

try:
    from ..core.config import get_config
    from ..core.error_handler import get_error_handler
    from .path_service import get_path_service

    error_handler = get_error_handler()
    config_manager = get_config()
    path_service = get_path_service()
except ImportError:
    error_handler = None
    config_manager = None
    path_service = None


def handle_error(module: str, message: str, duration: int = 60) -> None:
    """Fallback error handling for transition period"""
    if error_handler:
        try:
            from ..core.error_handler import TradingSystemError

            error = TradingSystemError(message)
            error_handler.handle_error(error, {"module": module, "duration": duration})
        except:
            print(f"ERROR [{module}]: {message}")
    else:
        print(f"ERROR [{module}]: {message}")


class DataFormat:
    """Data format configuration and validation"""

    SUPPORTED_FORMATS = {
        "excel": [".xlsx", ".xls"],
        "feather": [".ftr", ".feather"],
        "parquet": [".parquet", ".pq"],
        "csv": [".csv"],
        "pickle": [".pkl", ".pickle"],
        "json": [".json"],
    }

    @classmethod
    def get_format_from_extension(cls, file_path: str | Path) -> str:
        """Determine format from file extension"""
        extension = Path(file_path).suffix.lower()

        for format_name, extensions in cls.SUPPORTED_FORMATS.items():
            if extension in extensions:
                return format_name

        return "unknown"

    @classmethod
    def validate_format(cls, file_path: str | Path) -> bool:
        """Validate if file format is supported"""
        return cls.get_format_from_extension(file_path) != "unknown"


class ExcelManager:
    """Excel file operations manager"""

    def __init__(self):
        self.engine: Literal["openpyxl"] = "openpyxl"

    def save_dataframe(
        self,
        df: pd.DataFrame,
        file_path: str | Path,
        sheet_name: str = "Sheet1",
        index: bool = True,
        merge_cells: bool = False,
    ) -> bool:
        """Save DataFrame to Excel file"""
        try:
            # Handle timezone-aware datetime columns
            df_copy = df.copy()
            for col in df_copy.columns:
                if "datetime64[ns," in str(df_copy[col].dtype):
                    try:
                        # More robust timezone handling
                        col_series = df_copy[col]
                        if hasattr(col_series, "dt") and hasattr(col_series.dt, "tz"):
                            if col_series.dt.tz is not None:
                                df_copy[col] = col_series.dt.tz_convert(
                                    "America/New_York"
                                )
                                df_copy[col] = df_copy[col].dt.tz_localize(None)
                    except (AttributeError, TypeError):
                        # Handle cases where timezone operations fail
                        pass

            df_copy.to_excel(
                str(file_path),
                sheet_name=sheet_name,
                index=index,
                engine=self.engine,
                merge_cells=merge_cells,
            )
            return True

        except Exception as e:
            handle_error(__name__, f"Failed to save Excel file {file_path}: {e}")
            return False

    def load_dataframe(
        self,
        file_path: str | Path,
        sheet_name: str | int = 0,
        header: int | list[int] = 0,
        index_col: str | int | None = None,
    ) -> pd.DataFrame | None:
        """Load DataFrame from Excel file"""
        try:
            return pd.read_excel(
                str(file_path),
                sheet_name=sheet_name,
                header=header,
                engine=self.engine,
                index_col=index_col,
            )
        except (FileNotFoundError, PermissionError, ValueError) as e:
            print(f"Warning: Could not load Excel file {file_path}: {e}")
            return None

    def get_temp_review_path(self, name: str = "") -> Path:
        """Get temporary Excel file path for review"""
        if not name:
            name = "For Review"

        if path_service:
            return path_service.get_excel_review_location(name)

        # Centralized path using config manager
        try:
            from ..core.config import get_config

            base_path = get_config().data_paths.base_path
        except Exception:
            base_path = Path.home() / "Machine Learning"
        path = str(base_path / f"Temp-{name}.xlsx")
        count = 1

        while os.path.exists(path):
            count += 1
            path = str(base_path / f"Temp-{name}-{count}.xlsx")

        return Path(path)


class FeatherManager:
    """Feather file operations manager"""

    @staticmethod
    def save_dataframe(df: pd.DataFrame, file_path: str | Path) -> bool:
        """Save DataFrame to Feather file"""
        try:
            df.to_feather(str(file_path))
            return True
        except Exception as e:
            handle_error(__name__, f"Failed to save Feather file {file_path}: {e}")
            return False

    @staticmethod
    def load_dataframe(file_path: str | Path) -> pd.DataFrame | None:
        """Load DataFrame from Feather file"""
        try:
            return pd.read_feather(str(file_path))
        except Exception as e:
            print(f"Warning: Could not load Feather file {file_path}: {e}")
            return None


class DataManager:
    """Main data management service"""

    def __init__(self):
        self.excel = ExcelManager()
        self.feather = FeatherManager()
        self.path_service = path_service

    def save_dataframe(
        self,
        df: pd.DataFrame,
        file_path: str | Path,
        format_type: str | None = None,
        **kwargs,
    ) -> bool:
        """Save DataFrame in specified format"""
        if format_type is None:
            format_type = DataFormat.get_format_from_extension(file_path)

        if not DataFormat.validate_format(file_path):
            handle_error(__name__, f"Unsupported file format: {file_path}")
            return False

        # Ensure directory exists
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        try:
            if format_type == "excel":
                return self.excel.save_dataframe(df, file_path, **kwargs)
            elif format_type == "feather":
                return self.feather.save_dataframe(df, file_path)
            elif format_type == "csv":
                df.to_csv(str(file_path), **kwargs)
                return True
            elif format_type == "parquet":
                df.to_parquet(str(file_path), **kwargs)
                return True
            elif format_type == "pickle":
                df.to_pickle(str(file_path), **kwargs)
                return True
            elif format_type == "json":
                df.to_json(str(file_path), **kwargs)
                return True
            else:
                handle_error(__name__, f"Unsupported save format: {format_type}")
                return False

        except Exception as e:
            handle_error(__name__, f"Failed to save file {file_path}: {e}")
            return False

    def load_dataframe(
        self, file_path: str | Path, format_type: str | None = None, **kwargs
    ) -> pd.DataFrame | None:
        """Load DataFrame from specified format"""
        if not os.path.exists(file_path):
            print(f"Warning: File does not exist: {file_path}")
            return None

        if format_type is None:
            format_type = DataFormat.get_format_from_extension(file_path)

        try:
            if format_type == "excel":
                return self.excel.load_dataframe(file_path, **kwargs)
            elif format_type == "feather":
                return self.feather.load_dataframe(file_path)
            elif format_type == "csv":
                return pd.read_csv(str(file_path), **kwargs)
            elif format_type == "parquet":
                return pd.read_parquet(str(file_path), **kwargs)
            elif format_type == "pickle":
                return pd.read_pickle(str(file_path), **kwargs)
            elif format_type == "json":
                return pd.read_json(str(file_path), **kwargs)
            else:
                print(f"Warning: Unsupported load format: {format_type}")
                return None

        except Exception as e:
            print(f"Warning: Failed to load file {file_path}: {e}")
            return None

    def warrior_list_operations(
        self, operation: str, df: pd.DataFrame | None = None
    ) -> pd.DataFrame | None:
        """Handle Warrior Trading list operations"""
        try:
            from ..core.config import get_config as _gc

            warrior_path = _gc().get_data_file_path("warrior_trading_trades")
        except Exception:
            warrior_path = Path("./Warrior/WarriorTrading_Trades.xlsx")

        if operation.lower() == "load":
            return self.load_dataframe(warrior_path, sheet_name=0, header=0)
        elif operation.lower() == "save":
            if df is None:
                handle_error(__name__, "DataFrame is None, cannot save Warrior list")
                return None

            # Save using centralized path (warrior_path)
            success = self.save_dataframe(
                df, warrior_path, sheet_name="Sheet1", index=False
            )
            return df if success else None
        else:
            handle_error(
                __name__, "Must select 'load' or 'save' for Warrior list operation"
            )
            return None

    def train_list_operations(
        self, operation: str, train_type: str = "Test", df: pd.DataFrame | None = None
    ) -> pd.DataFrame | None:
        """Handle training list operations"""
        if path_service:
            file_path = path_service.get_train_list_location(train_type)
        else:
            try:
                from ..core.config import get_config

                base_path = get_config().data_paths.base_path
            except Exception:
                base_path = Path.home() / "Machine Learning"
            file_path = base_path / f"Train_List-{train_type}.xlsx"

        if operation.lower() == "load":
            loaded_df = self.load_dataframe(file_path, sheet_name=0, header=0)
            if loaded_df is None:
                # Return empty DataFrame with expected columns
                return pd.DataFrame(columns=["Stock", "DateStr"])
            return loaded_df

        elif operation.lower() == "save":
            if df is None:
                handle_error(__name__, "DataFrame is None, cannot save training list")
                return None

            success = self.save_dataframe(
                df, file_path, sheet_name="Sheet1", index=False
            )
            return df if success else None
        else:
            handle_error(
                __name__, "Must select 'load' or 'save' for training list operation"
            )
            return None

    def save_for_review(self, df: pd.DataFrame, name: str = "") -> Path:
        """Save DataFrame for review in Excel format"""
        review_path = self.excel.get_temp_review_path(name)
        self.save_dataframe(df, review_path, index=False)
        return review_path

    def get_data_summary(self, df: pd.DataFrame) -> dict[str, Any]:
        """Get comprehensive data summary"""
        return {
            "shape": df.shape,
            "columns": list(df.columns),
            "dtypes": df.dtypes.to_dict(),
            "memory_usage": df.memory_usage(deep=True).sum(),
            "null_counts": df.isnull().sum().to_dict(),
            "numeric_columns": list(df.select_dtypes(include=["number"]).columns),
            "datetime_columns": list(df.select_dtypes(include=["datetime"]).columns),
            "categorical_columns": list(df.select_dtypes(include=["category"]).columns),
        }

    def optimize_dataframe_memory(self, df: pd.DataFrame) -> pd.DataFrame:
        """Optimize DataFrame memory usage"""
        optimized_df = df.copy()

        # Optimize numeric columns
        for col in optimized_df.select_dtypes(include=["int"]).columns:
            col_min = optimized_df[col].min()
            col_max = optimized_df[col].max()

            if col_min >= -128 and col_max <= 127:
                optimized_df[col] = optimized_df[col].astype("int8")
            elif col_min >= -32768 and col_max <= 32767:
                optimized_df[col] = optimized_df[col].astype("int16")
            elif col_min >= -2147483648 and col_max <= 2147483647:
                optimized_df[col] = optimized_df[col].astype("int32")

        for col in optimized_df.select_dtypes(include=["float"]).columns:
            optimized_df[col] = optimized_df[col].astype("float32")

        # Convert object columns with low cardinality to category
        for col in optimized_df.select_dtypes(include=["object"]).columns:
            if optimized_df[col].nunique() / len(optimized_df) < 0.5:
                optimized_df[col] = optimized_df[col].astype("category")

        return optimized_df


class DataLoaderService:
    """Service for loading various data types"""

    def __init__(self):
        self.data_manager = DataManager()

    def load_stock_downloads(
        self, request_manager: Any, contract: Any, bar_size: str, for_date: str = ""
    ) -> pd.DataFrame | None:
        """Load stock download data"""
        try:
            if for_date == "":
                # Download multiple timeframes
                df_1sec = request_manager.Download_Historical(
                    contract=contract, BarSize="1 sec", forDate=""
                )
                df_30min = request_manager.Download_Historical(
                    contract=contract, BarSize="30 min", forDate=""
                )
                df_tick = request_manager.Download_Historical(
                    contract=contract, BarSize="tick", forDate=""
                )
                # Return the most relevant one (could be improved)
                return df_tick if df_tick is not None else df_1sec
            else:
                return request_manager.Download_Historical(
                    contract=contract, BarSize="tick", forDate=for_date
                )

        except Exception as e:
            handle_error(__name__, f"Failed to load stock downloads: {e}")
            return None


# Backward compatibility functions
def WarriorList(load_save: str, df: pd.DataFrame | None = None) -> pd.DataFrame | None:
    """Backward compatibility function for Warrior list operations"""
    service = get_data_service()
    return service.data_manager.warrior_list_operations(load_save, df)


def TrainList_LoadSave(
    load_save: str, train_type: str = "Test", df: pd.DataFrame | None = None
) -> pd.DataFrame | None:
    """Backward compatibility function for training list operations"""
    service = get_data_service()
    return service.data_manager.train_list_operations(load_save, train_type, df)


def Stock_Downloads_Load(
    req: Any, contract: Any, bar_size: str, for_date: str
) -> pd.DataFrame | None:
    """Backward compatibility function for stock downloads"""
    service = get_data_service()
    return service.load_stock_downloads(req, contract, bar_size, for_date)


def SaveExcel_ForReview(df: pd.DataFrame, str_name: str = "") -> Path:
    """Backward compatibility function for Excel review saves"""
    service = get_data_service()
    return service.data_manager.save_for_review(df, str_name)


# Singleton service instance
_data_service = None


def get_data_service() -> DataLoaderService:
    """Get singleton data service"""
    global _data_service
    if _data_service is None:
        _data_service = DataLoaderService()
    return _data_service
