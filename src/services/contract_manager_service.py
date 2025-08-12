"""
Contract Manager Service - P0 Critical Architecture Migration
Handles IB contract creation, qualification, and management.
Extracted from monolithic requestCheckerCLS (300+ lines).
"""

import sys
from datetime import date
from pathlib import Path
from typing import Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from ib_async import Contract, Forex, Future, Option, Stock

    from src.core.config import get_config
    from src.core.error_handler import get_error_handler
except ImportError as e:
    print(f"Warning: Could not import dependencies: {e}")

    # Define fallback classes for development
    class Stock:
        def __init__(self, symbol, exchange, currency):
            self.symbol = symbol
            self.exchange = exchange
            self.currency = currency

    class Contract:
        pass

    Option = Future = Forex = Contract


class ContractManagerService:
    """
    Enterprise-grade contract management for Interactive Brokers.

    Responsibilities:
    - Contract creation and qualification
    - Symbol validation and normalization
    - Exchange and currency mapping
    - Contract caching for performance
    - Error handling and recovery
    """

    def __init__(self, ib_connection=None, config=None):
        """Initialize contract manager with IB connection."""
        self.error_handler = get_error_handler()
        self.config = config or get_config()
        self.ib = ib_connection

        # Contract cache for performance
        self._contract_cache = {}

        # Default settings
        self.default_exchange = "SMART"
        self.default_currency = "USD"

        # Exchange mappings
        self.exchange_mappings = {
            "NASDAQ": "NASDAQ",
            "NYSE": "NYSE",
            "SMART": "SMART",
            "ISLAND": "ISLAND",
            "ARCA": "ARCA",
        }

        # Currency mappings
        self.currency_mappings = {
            "USD": "USD",
            "EUR": "EUR",
            "GBP": "GBP",
            "JPY": "JPY",
            "CAD": "CAD",
            "AUD": "AUD",
        }

    def create_stock_contract(
        self, symbol: str, exchange: str | None = None, currency: str | None = None
    ) -> Contract | None:
        """
        Create a stock contract with proper validation.

        Args:
            symbol: Stock symbol (e.g., "AAPL")
            exchange: Exchange (defaults to SMART)
            currency: Currency (defaults to USD)

        Returns:
            IB Contract object or None if failed
        """
        try:
            # Normalize inputs
            symbol = symbol.upper().strip()
            exchange = exchange or self.default_exchange
            currency = currency or self.default_currency

            # Check cache first
            cache_key = f"{symbol}_{exchange}_{currency}"
            if cache_key in self._contract_cache:
                self.error_handler.logger.debug(
                    f"Using cached contract for {cache_key}"
                )
                return self._contract_cache[cache_key]

            # Validate symbol
            if not self._validate_symbol(symbol):
                self.error_handler.logger.error(f"Invalid symbol: {symbol}")
                return None

            # Create contract
            contract = Stock(symbol, exchange, currency)

            # Qualify contract if IB connection available
            if self.ib and hasattr(self.ib, "qualifyContracts"):
                qualified_contracts = self.ib.qualifyContracts(contract)
                if qualified_contracts:
                    contract = qualified_contracts[0]
                    self.error_handler.logger.info(f"Qualified contract for {symbol}")
                else:
                    self.error_handler.logger.warning(
                        f"Could not qualify contract for {symbol}"
                    )
                    return None

            # Cache the contract
            self._contract_cache[cache_key] = contract

            return contract

        except Exception as e:
            self.error_handler.handle_error(
                e,
                context={"symbol": symbol, "exchange": exchange, "currency": currency},
                module="contract_manager_service",
                function="create_stock_contract",
            )
            return None

    def create_option_contract(
        self,
        symbol: str,
        expiry: str,
        strike: float,
        right: str,
        exchange: str | None = None,
        currency: str | None = None,
    ) -> Contract | None:
        """
        Create an option contract.

        Args:
            symbol: Underlying symbol
            expiry: Expiry date (YYYYMMDD format)
            strike: Strike price
            right: "C" for call, "P" for put
            exchange: Exchange (defaults to SMART)
            currency: Currency (defaults to USD)

        Returns:
            IB Contract object or None if failed
        """
        try:
            # Normalize inputs
            symbol = symbol.upper().strip()
            right = right.upper().strip()
            exchange = exchange or self.default_exchange
            currency = currency or self.default_currency

            # Validate inputs
            if right not in ["C", "P"]:
                self.error_handler.logger.error(f"Invalid option right: {right}")
                return None

            if not self._validate_expiry_date(expiry):
                self.error_handler.logger.error(f"Invalid expiry date: {expiry}")
                return None

            # Create cache key
            cache_key = f"OPT_{symbol}_{expiry}_{strike}_{right}_{exchange}_{currency}"
            if cache_key in self._contract_cache:
                return self._contract_cache[cache_key]

            # Create option contract
            contract = Option()
            contract.symbol = symbol
            contract.lastTradeDateOrContractMonth = expiry
            contract.strike = strike
            contract.right = right
            contract.exchange = exchange or "SMART"
            contract.currency = currency or "USD"

            # Qualify if IB connection available
            if self.ib and hasattr(self.ib, "qualifyContracts"):
                qualified_contracts = self.ib.qualifyContracts(contract)
                if qualified_contracts:
                    contract = qualified_contracts[0]
                else:
                    self.error_handler.logger.warning(
                        "Could not qualify option contract"
                    )
                    return None

            # Cache the contract
            self._contract_cache[cache_key] = contract

            return contract

        except Exception as e:
            self.error_handler.handle_error(
                e,
                context={
                    "symbol": symbol,
                    "expiry": expiry,
                    "strike": strike,
                    "right": right,
                },
                module="contract_manager_service",
                function="create_option_contract",
            )
            return None

    def create_forex_contract(
        self, base_currency: str, quote_currency: str = "USD"
    ) -> Contract | None:
        """
        Create a forex contract.

        Args:
            base_currency: Base currency (e.g., "EUR")
            quote_currency: Quote currency (defaults to "USD")

        Returns:
            IB Contract object or None if failed
        """
        try:
            # Normalize inputs
            base_currency = base_currency.upper().strip()
            quote_currency = quote_currency.upper().strip()

            # Validate currencies
            if base_currency not in self.currency_mappings:
                self.error_handler.logger.error(
                    f"Invalid base currency: {base_currency}"
                )
                return None

            if quote_currency not in self.currency_mappings:
                self.error_handler.logger.error(
                    f"Invalid quote currency: {quote_currency}"
                )
                return None

            # Create cache key
            cache_key = f"FX_{base_currency}_{quote_currency}"
            if cache_key in self._contract_cache:
                return self._contract_cache[cache_key]

            # Create forex contract
            symbol = f"{base_currency}.{quote_currency}"
            contract = Forex()
            contract.symbol = symbol

            # Cache the contract
            self._contract_cache[cache_key] = contract

            return contract

        except Exception as e:
            self.error_handler.handle_error(
                e,
                context={
                    "base_currency": base_currency,
                    "quote_currency": quote_currency,
                },
                module="contract_manager_service",
                function="create_forex_contract",
            )
            return None

    def _validate_symbol(self, symbol: str) -> bool:
        """Validate stock symbol format."""
        if not symbol or len(symbol) < 1:
            return False

        # Basic validation - alphanumeric characters only
        if not symbol.replace(".", "").replace("-", "").isalnum():
            return False

        # Length check (most symbols are 1-5 characters)
        if len(symbol) > 10:
            return False

        return True

    def _validate_expiry_date(self, expiry: str) -> bool:
        """Validate option expiry date format (YYYYMMDD)."""
        try:
            if len(expiry) != 8:
                return False

            # Try to parse as date
            year = int(expiry[:4])
            month = int(expiry[4:6])
            day = int(expiry[6:8])

            # Basic range checks
            if year < 2020 or year > 2030:
                return False
            if month < 1 or month > 12:
                return False
            if day < 1 or day > 31:
                return False

            # Try to create actual date
            date(year, month, day)
            return True

        except (ValueError, TypeError):
            return False

    def get_contract_details(self, contract: Contract) -> dict[str, Any]:
        """
        Get detailed information about a contract.

        Args:
            contract: IB Contract object

        Returns:
            Dictionary with contract details
        """
        try:
            if not contract:
                return {"error": "Contract is None"}

            details = {
                "symbol": getattr(contract, "symbol", "Unknown"),
                "secType": getattr(contract, "secType", "Unknown"),
                "exchange": getattr(contract, "exchange", "Unknown"),
                "currency": getattr(contract, "currency", "Unknown"),
                "primaryExchange": getattr(contract, "primaryExchange", ""),
                "conId": getattr(contract, "conId", 0),
            }

            # Add option-specific details
            if hasattr(contract, "strike") and getattr(contract, "strike", None):
                details["strike"] = getattr(contract, "strike", 0)
                details["right"] = getattr(contract, "right", "")
                details["expiry"] = getattr(
                    contract, "lastTradeDateOrContractMonth", ""
                )

            return details

        except Exception as e:
            self.error_handler.handle_error(
                e,
                context={},
                module="contract_manager_service",
                function="get_contract_details",
            )
            return {"error": str(e)}

    def batch_create_contracts(
        self,
        symbols: list[str],
        exchange: str | None = None,
        currency: str | None = None,
    ) -> dict[str, Contract | None]:
        """
        Create multiple stock contracts efficiently.

        Args:
            symbols: List of stock symbols
            exchange: Exchange for all symbols
            currency: Currency for all symbols

        Returns:
            Dictionary mapping symbols to contracts
        """
        results = {}

        self.error_handler.logger.info(f"Creating contracts for {len(symbols)} symbols")

        for symbol in symbols:
            contract = self.create_stock_contract(symbol, exchange, currency)
            results[symbol] = contract

            if contract:
                self.error_handler.logger.debug(f"Created contract for {symbol}")
            else:
                self.error_handler.logger.warning(
                    f"Failed to create contract for {symbol}"
                )

        return results

    def clear_cache(self):
        """Clear the contract cache."""
        cache_size = len(self._contract_cache)
        self._contract_cache.clear()
        self.error_handler.logger.info(f"Cleared contract cache ({cache_size} entries)")

    def get_cache_statistics(self) -> dict[str, Any]:
        """Get contract cache statistics."""
        return {
            "cached_contracts": len(self._contract_cache),
            "cache_keys": list(self._contract_cache.keys()),
        }


# Singleton instance for global access
_contract_manager_instance = None


def get_contract_manager(ib_connection=None, config=None) -> ContractManagerService:
    """Get or create the global contract manager instance."""
    global _contract_manager_instance

    if _contract_manager_instance is None:
        _contract_manager_instance = ContractManagerService(ib_connection, config)

    return _contract_manager_instance


def reset_contract_manager():
    """Reset the global contract manager (useful for testing)."""
    global _contract_manager_instance
    _contract_manager_instance = None


if __name__ == "__main__":
    # Test the contract manager
    print("🔧 Testing Contract Manager Service")

    contract_manager = ContractManagerService()

    # Test stock contract creation
    aapl_contract = contract_manager.create_stock_contract("AAPL")
    if aapl_contract:
        print(f"AAPL Contract: {contract_manager.get_contract_details(aapl_contract)}")
    else:
        print("Failed to create AAPL contract")

    # Test batch creation
    symbols = ["AAPL", "MSFT", "GOOGL", "TSLA"]
    contracts = contract_manager.batch_create_contracts(symbols)
    print(
        f"Created {len([c for c in contracts.values() if c])} out of {len(symbols)} contracts"
    )

    # Test cache statistics
    cache_stats = contract_manager.get_cache_statistics()
    print(f"Cache Statistics: {cache_stats}")

    print("✅ Contract Manager Service test completed")
