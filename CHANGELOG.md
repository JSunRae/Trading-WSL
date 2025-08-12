# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog (https://keepachangelog.com/en/1.0.0/),
and this project adheres to Semantic Versioning.

## [0.9.0] - 2025-08-11

### Added

- Centralized async IB infrastructure (`ib_client.py`, `contract_factories.py`, `ib_requests.py`, `project_types.py`).
- Service registry for dependency-injected services in tests and production.
- `--describe` tooling interface across all major scripts.
- Fake IB client fallback enabling dependency-free test runs.
- Pre-commit configuration with Ruff, mypy, pytest, pyright hooks.

### Changed

- Migration from `ib_insync` style scattered clients to unified `ib_async` optional dependency.
- Strengthened error handling via `IntegratedErrorHandler` with registry-aware service resolution.
- Updated pandas helper utilities location and naming consistency.
- Tightened pytest configuration: coverage gate >=80%, warnings elevated, return-value warning eliminated.

### Fixed

- Flaky import cascades causing `ImportError` when optional IB deps absent.
- Incorrect service resolution in error handling tests (now registry-backed).
- Spurious PytestReturnNotNoneWarning by removing return values from test functions.
- Various path inconsistencies after repo restructuring.

### Removed

- Implicit reliance on `ib_insync` during test collection.

### Security

- Added pre-commit hooks for static analysis & type checking before commit.

## [0.8.0] - 2025-07-15

### Added

- Initial Level 2 market depth recorder & analyzer.
- Retry manager and connection pool foundations.

### Changed

- Data layer migrated to Parquet for performance.

### Fixed

- Early error handler recursion issues.

## [Unreleased]

- Phase 2 legacy component refactors (planned).

[0.9.0]: https://github.com/yourusername/trading-project/releases/tag/v0.9.0
