"""
MasterPy - Utility functions for the trading system

This is a stub implementation providing the essential functions used by
the trading system. This replaces the missing MasterPy module.
"""

import logging
from pathlib import Path


def setup_logger():
    """Setup basic logger."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    return logging.getLogger("MasterPy")


logger = setup_logger()


def ErrorCapture(module_name, message, duration=60, show_popup=False, continueOn=True):
    """
    Capture and log errors.

    Args:
        module_name: Name of the module reporting the error
        message: Error message
        duration: Duration to display (ignored in this implementation)
        show_popup: Whether to show popup (ignored in this implementation)
        continueOn: Whether to continue execution (ignored in this implementation)
    """
    logger.error(f"[{module_name}] {message}")
    if not continueOn:
        raise Exception(f"[{module_name}] {message}")


def ErrorCapture_ReturnAns(module_name, message, duration=60, return_answer=True):
    """
    Capture error and return answer.

    Args:
        module_name: Name of the module reporting the error
        message: Error message
        duration: Duration to display (ignored)
        return_answer: Whether to return an answer

    Returns:
        bool: The return_answer value
    """
    logger.error(f"[{module_name}] {message}")
    return return_answer


def LocExist(location):
    """
    Check if a location/path exists.

    Args:
        location: Path to check

    Returns:
        bool: True if location exists
    """
    if isinstance(location, str):
        location = Path(location)

    exists = location.exists()
    if not exists:
        logger.warning(f"Location does not exist: {location}")

    return exists


def create_directory(path):
    """Create directory if it doesn't exist."""
    Path(path).mkdir(parents=True, exist_ok=True)


def log_info(module_name, message):
    """Log info message."""
    logger.info(f"[{module_name}] {message}")


def log_warning(module_name, message):
    """Log warning message."""
    logger.warning(f"[{module_name}] {message}")


def log_debug(module_name, message):
    """Log debug message."""
    logger.debug(f"[{module_name}] {message}")


def Download_loc_IB(stock_code, bar_size, date_str=None):
    """
    Generate download location for IB data files.

    Args:
        stock_code: Stock symbol
        bar_size: Bar size (e.g., '1 hour', '1 sec', 'tick')
        date_str: Optional date string

    Returns:
        str: File path for the data file
    """
    # Create data directory if it doesn't exist
    data_dir = Path("data") / "historical"
    data_dir.mkdir(parents=True, exist_ok=True)

    # Generate filename
    if date_str:
        filename = f"{stock_code}_{bar_size.replace(' ', '_')}_{date_str}.xlsx"
    else:
        filename = f"{stock_code}_{bar_size.replace(' ', '_')}.xlsx"

    return str(data_dir / filename)


def Stock_Downloads_Load(*args, **kwargs):
    """
    Stub for Stock_Downloads_Load function.
    This function should be implemented based on your specific requirements.
    """
    logger.warning("Stock_Downloads_Load function called but not implemented in stub")
    return None


def SendTxt(message):
    """
    Send text message - placeholder implementation.

    Args:
        message: Message to send
    """
    logger.info(f"SendTxt: {message}")
    print(f"Message: {message}")
