# Trading Project Makefile

.PHONY: help install install-dev test format lint clean setup verify run-main run-trader level2-test level2-record level2-analyze update-data update-warrior update-recent

# Default target
help:
	@echo "Available targets:"
	@echo "  setup       - Complete project setup (install + config)"
	@echo "  install     - Install production dependencies"
	@echo "  install-dev - Install development dependencies"
	@echo "  verify      - Verify installation and setup"
	@echo "  test        - Run tests"
	@echo "  format      - Format code with black and isort"
	@echo "  lint        - Run linting with flake8"
	@echo "  clean       - Clean up temporary files"
	@echo "  run-main    - Run main trading application"
	@echo "  run-trader  - Run trader module"
	@echo ""
	@echo "Data Management:"
	@echo "  scan-data      - Scan existing data files"
	@echo "  update-data    - Show data update options"
	@echo "  update-warrior - Update all warrior list data"
	@echo "  update-recent  - Update recent data (last 7 days)"
	@echo ""
	@echo "Level 2 Data Recording:"
	@echo "  level2-test    - Test Level 2 connection and setup"
	@echo "  level2-record  - Record Level 2 data (symbol required)"
	@echo "  level2-analyze - Analyze recorded Level 2 data"

# Python executable (use virtual environment if available)
PYTHON := $(shell if [ -f .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)
PIP := $(shell if [ -f .venv/bin/pip ]; then echo .venv/bin/pip; else echo pip3; fi)

# Complete setup
setup: install config
	@echo "✓ Setup complete!"
	@echo "Run 'make verify' to test the installation"

# Install production dependencies
install:
	$(PIP) install -r requirements.txt

# Install development dependencies
install-dev: install
	$(PIP) install pytest pytest-asyncio black flake8 isort mypy pre-commit

# Create config file from example
config:
	@if [ ! -f config/config.json ]; then \
		cp config/config.example.json config/config.json; \
		echo "✓ Created config/config.json from example"; \
		echo "  Please update it with your settings"; \
	else \
		echo "✓ config/config.json already exists"; \
	fi

# Verify installation
verify:
	$(PYTHON) verify_setup.py

# Run tests
test:
	$(PYTHON) -m pytest tests/ -v

# Format code
format:
	$(PYTHON) -m black src/ examples/ tests/ --line-length 88
	$(PYTHON) -m isort src/ examples/ tests/ --profile black

# Lint code
lint:
	$(PYTHON) -m flake8 src/ examples/ tests/ --max-line-length 88 --extend-ignore E203,W503

# Type checking
typecheck:
	$(PYTHON) -m mypy src/ --ignore-missing-imports

# Clean temporary files
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type f -name "*.log" -delete
	rm -rf build/ dist/ .pytest_cache/ .mypy_cache/

# Run main application
run-main:
	$(PYTHON) src/ib_main.py

# Run trader module  
run-trader:
	$(PYTHON) src/ib_trader.py

# Run example scripts
run-examples:
	@echo "Available examples:"
	@echo "  make run-qt-example     - PyQt5 ticker table"
	@echo "  make run-tk-example     - Tkinter interface"
	@echo "  make run-scanner-example - Web scanner"

run-qt-example:
	$(PYTHON) examples/example_ib_qt_ticker_table.py

run-tk-example:
	$(PYTHON) examples/example_Tkinter.py

run-scanner-example:
	$(PYTHON) examples/example_ib_WebScaner.py

# Development workflow
dev-setup: install-dev config
	@echo "Development environment ready!"

# Quick development check
dev-check: format lint test
	@echo "Development checks complete!"

# Install and setup everything
all: setup verify
	@echo "🎉 Trading project is ready to use!"

# Data Management Commands
update-data:
	@echo "Available data update options:"
	@echo "  make scan-data       - Scan existing data files"
	@echo "  make update-warrior  - Update all warrior list data"
	@echo "  make update-recent   - Update recent data (last 7 days)"
	@echo "  make update-check    - Check existing data files"
	@echo "  make update-legacy   - Run original update script"

scan-data:
	@echo "🔍 Scanning existing data..."
	$(PYTHON) scan_data.py

update-warrior:
	@echo "🔄 Updating all warrior list data..."
	@echo "This will download historical data for all stocks in the warrior list."
	@echo "Make sure IB TWS/Gateway is running on port 7497"
	$(PYTHON) run_data_update.py warrior

update-recent:
	@echo "🔄 Updating recent data (30-minute timeframe)..."
	@echo "Make sure IB TWS/Gateway is running on port 7497"
	$(PYTHON) run_data_update.py recent

update-check:
	@echo "🔍 Checking existing data files..."
	$(PYTHON) run_data_update.py check

update-legacy:
	@echo "🔄 Running legacy update script..."
	@echo "Make sure IB TWS/Gateway is running on port 7497"
	cd src && $(PYTHON) ib_Warror_dl.py

# Level 2 Data Recording Commands
level2-test:
	$(PYTHON) test_level2.py

level2-record:
	@echo "Usage: make level2-record SYMBOL=AAPL DURATION=60"
	@if [ -z "$(SYMBOL)" ]; then \
		echo "Error: SYMBOL not specified. Use: make level2-record SYMBOL=AAPL"; \
		exit 1; \
	fi
	$(PYTHON) src/data/record_depth.py --symbol $(SYMBOL) $(if $(DURATION),--duration $(DURATION),) $(if $(LEVELS),--levels $(LEVELS),) $(if $(INTERVAL),--interval $(INTERVAL),)

level2-analyze:
	@echo "Usage: make level2-analyze SYMBOL=AAPL DATE=2025-07-28"
	@if [ -z "$(SYMBOL)" ] || [ -z "$(DATE)" ]; then \
		echo "Error: SYMBOL and DATE required. Use: make level2-analyze SYMBOL=AAPL DATE=2025-07-28"; \
		exit 1; \
	fi
	$(PYTHON) src/data/analyze_depth.py --data-dir ./data/level2 --symbol $(SYMBOL) --date $(DATE) --plot
