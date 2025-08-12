# Contributing to Trading Project

Thank you for your interest in contributing to the Trading Project! This document provides guidelines for contributing to this Interactive Brokers trading system.

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Quality Standards](#quality-standards)
- [Testing](#testing)
- [Submitting Changes](#submitting-changes)
- [Review Process](#review-process)

## Code of Conduct

This project adheres to a code of conduct. By participating, you are expected to uphold this code. Please report unacceptable behavior to the project maintainers.

## Getting Started

### Prerequisites

- Python 3.10 or higher
- Interactive Brokers account (paper trading recommended for development)
- Basic knowledge of async/await patterns
- Familiarity with pandas and financial data

### Development Setup

1. **Clone the repository**:

   ```bash
   git clone <repository-url>
   cd Trading
   ```

2. **Set up virtual environment**:

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install development dependencies**:

   ```bash
   pip install -e .[dev]
   ```

4. **Install pre-commit hooks**:

   ```bash
   pre-commit install
   ```

5. **Set up environment variables**:

   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

6. **Run setup wizard** (optional):
   ```bash
   python setup_automated_trading.py
   ```

## Making Changes

### Branch Naming

Use descriptive branch names:

- `feature/add-new-indicator`
- `fix/connection-timeout-issue`
- `docs/update-api-documentation`
- `refactor/improve-error-handling`

### Commit Messages

Follow conventional commit format:

```
type(scope): brief description

More detailed description if needed

Fixes #123
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

### Code Style

This project uses modern Python tooling:

- **Formatter**: Ruff (replaces Black)
- **Linter**: Ruff (replaces Flake8)
- **Type Checker**: mypy
- **Import Sorting**: Ruff

### Pre-commit Hooks

Before committing, the following checks run automatically:

- Code formatting with Ruff
- Linting with Ruff
- Type checking with mypy
- Basic pytest run

## Quality Standards

### Code Quality Requirements

1. **Type Hints**: All functions must have type hints
2. **Docstrings**: Public functions need docstrings (Google style)
3. **Error Handling**: Proper exception handling with custom exceptions
4. **Logging**: Use structured logging, no print statements in production code
5. **Testing**: Minimum 85% test coverage for new code

### Example Code Style

```python
from typing import Optional
import logging

logger = logging.getLogger(__name__)

def calculate_moving_average(
    prices: list[float],
    window: int
) -> Optional[float]:
    """Calculate simple moving average for given prices.

    Args:
        prices: List of price values
        window: Number of periods for average calculation

    Returns:
        Moving average value or None if insufficient data

    Raises:
        ValueError: If window size is invalid
    """
    if window <= 0:
        raise ValueError("Window size must be positive")

    if len(prices) < window:
        logger.warning(f"Insufficient data: {len(prices)} < {window}")
        return None

    return sum(prices[-window:]) / window
```

### File Organization

```
src/
├── core/           # Core trading logic
├── services/       # Business logic services
├── automation/     # Headless automation
├── lib/           # Library wrappers
├── data/          # Data handling
└── utils/         # Utility functions

tests/
├── unit/          # Unit tests
├── integration/   # Integration tests
└── fixtures/      # Test fixtures

docs/
├── api/           # API documentation
├── guides/        # User guides
└── architecture/  # Architecture docs
```

## Testing

### Running Tests

```bash
# Run all tests
make test

# Run with coverage
make test-coverage

# Run specific test file
python -m pytest tests/test_specific_module.py

# Run tests matching pattern
python -m pytest -k "test_trading"
```

### Writing Tests

1. **Unit Tests**: Test individual functions/classes
2. **Integration Tests**: Test component interactions
3. **Mock External Services**: Use mocks for IB API calls
4. **Fixtures**: Use pytest fixtures for common test data

Example test:

```python
import pytest
from unittest.mock import Mock, patch
from src.services.market_data_service import MarketDataService

class TestMarketDataService:
    @pytest.fixture
    def service(self):
        return MarketDataService()

    @patch('src.services.market_data_service.IBAsync')
    def test_connect_success(self, mock_ib, service):
        mock_ib.return_value.connect.return_value = True

        result = service.connect()

        assert result is True
        mock_ib.return_value.connect.assert_called_once()
```

## Submitting Changes

### Pull Request Process

1. **Create Feature Branch**:

   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make Changes**: Follow coding standards and write tests

3. **Run Quality Checks**:

   ```bash
   make lint
   make type-check
   make test
   ```

4. **Commit Changes**:

   ```bash
   git add .
   git commit -m "feat(trading): add new technical indicator"
   ```

5. **Push and Create PR**:
   ```bash
   git push origin feature/your-feature-name
   ```

### Pull Request Template

```markdown
## Description

Brief description of changes

## Type of Change

- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## How Has This Been Tested?

- [ ] Unit tests
- [ ] Integration tests
- [ ] Manual testing

## Checklist:

- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] No breaking changes (or breaking changes documented)
```

## Review Process

### Automated Checks

All PRs must pass:

- ✅ Ruff linting and formatting
- ✅ mypy type checking
- ✅ pytest test suite (85% coverage minimum)
- ✅ Security scanning (pip-audit)
- ✅ Build verification

### Manual Review

Reviewers will check:

- Code quality and architecture
- Test coverage and quality
- Documentation updates
- Performance implications
- Security considerations

### Review Guidelines

**For Reviewers**:

- Be constructive and specific
- Focus on code quality, not style (automated tools handle style)
- Consider performance and security implications
- Suggest improvements, don't just point out problems

**For Contributors**:

- Respond to feedback promptly
- Ask questions if feedback is unclear
- Make requested changes in separate commits
- Update tests and documentation as needed

## Development Tips

### Local Development Workflow

```bash
# Start development
git checkout -b feature/my-feature

# During development
make lint           # Check code style
make type-check     # Check types
make test           # Run tests
make test-coverage  # Check coverage

# Before committing
make quality-check  # Run all checks

# Commit and push
git add .
git commit -m "feat: description"
git push origin feature/my-feature
```

### Debugging

- Use VS Code debug configurations in `.vscode/launch.json`
- Set breakpoints in trading logic
- Use paper trading for safe testing
- Check logs in `logs/` directory

### Performance Considerations

- Profile hot paths with `cProfile`
- Use async/await for I/O operations
- Minimize pandas operations in loops
- Cache expensive calculations

## Resources

- [Interactive Brokers API Documentation](https://interactivebrokers.github.io/tws-api/)
- [Python Type Hints Guide](https://docs.python.org/3/library/typing.html)
- [pytest Documentation](https://docs.pytest.org/)
- [Ruff Configuration](https://docs.astral.sh/ruff/)

## Getting Help

- **Issues**: Open GitHub issue for bugs or feature requests
- **Discussions**: Use GitHub discussions for questions
- **Documentation**: Check `docs/` directory
- **Examples**: See `examples/` directory

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to the Trading Project! 🚀📈
