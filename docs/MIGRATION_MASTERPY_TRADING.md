# Migration note: Replacing MasterPy_Trading

The legacy monolith `MasterPy_Trading.py` has been removed. Use the modern services below.

- Historical data
  - Module: `src/services/historical_data_service.py`
  - Example:
    - `from src.services.historical_data_service import HistoricalDataService`

- Market depth (Level 2) and tick data
  - Module: `src/services/market_data/market_data_service.py`
  - Class (L2): `MarketDepthManager`
  - Example:
    - `from src.services.market_data.market_data_service import MarketDepthManager`

- Orders and positions
  - Orders: `src/services/order_management_service.py`
  - Positions: `src/services/position_service.py`
  - Examples:
    - `from src.services.order_management_service import OrderManagementService`
    - `from src.services.position_service import PositionService`

Notes

- The old `MarketDepthCls` and all imports from `MasterPy_Trading` are deprecated and no longer available.
- Replace `from MasterPy_Trading import ...` with the modules above.
- For Level 2 streaming in existing apps, see `src/ib_Main.py` and `src/services/market_data/integration_example.py`.

If you need help mapping a specific legacy call to a modern API, open an issue with a minimal snippet and we’ll add the translation here.
