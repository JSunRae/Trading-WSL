# IB Gateway Connection Refactoring Audit Report

## Executive Summary

Successfully refactored the IB Gateway connection protocol to be Linux-first and robust, eliminated duplicate connection code across the repository, and fixed the probe bug that emitted `host:0` errors.

## Key Objectives Achieved

✅ **Linux-first connection protocol** - Default candidates are now [IB_PORT, 4002, 7497] with Windows/portproxy [4003, 4004] only when `IB_ALLOW_WINDOWS=1`

✅ **Eliminated duplicate connection code** - All scripts now use the canonical `ib_conn.get_ib_connect_plan()` + `IBAsync.connect()` path

✅ **Fixed probe :0 bug** - Port validation now clamps to 1..65535, preventing invalid port 0 attempts

✅ **Handshake-based readiness** - Connection success is now determined by actual IB API handshake, not just TCP open

✅ **ClientId cycling** - Automatic cycling through clientId+0, clientId+1, clientId+2 to avoid duplicate client collisions

## Files Modified

### Core Infrastructure Changes

#### `src/infra/ib_conn.py`

- **Enhanced `try_connect_candidates()`**: Added TCP probing before handshake attempts, clientId cycling, and detailed diagnostics
- **Added JTS config parsing**: `_parse_jts_config()` and `_log_jts_diagnostics()` for non-invasive troubleshooting
- **Improved port validation**: `_is_valid_port()` and `_filter_valid_ports()` prevent :0 bugs
- **Linux-first policy**: `_build_candidate_ports()` respects `IB_ALLOW_WINDOWS` flag

#### `src/lib/ib_async_wrapper.py`

- **Refactored `IBAsync.connect()`**: Removed duplicate Windows fallback logic, now delegates to canonical connection path
- **Simplified fallback behavior**: Uses `get_ib_connect_plan()` and `try_connect_candidates()` when no explicit parameters provided
- **Maintained backward compatibility**: Explicit host/port parameters still work for custom connections

### Script Updates

#### `start_gateway.sh`

- **Fixed :0 bug**: Changed `CHK_PORT` default from `'0'` to `'4002'` with port validation
- **Handshake-based readiness**: API test now requires successful handshake, not just TCP open
- **Improved diagnostics**: Clear messages distinguish TCP vs API handshake failures

#### `src/tools/setup/setup_ib_gateway.py`

- **Canonical connection**: Removed custom HOST/PORT/CID logic, now uses `IBAsync.connect()` directly
- **Simplified template**: Generated probe scripts use canonical connection path

#### `src/tools/run_trading_fully_automated.py`

- **Streamlined connection**: Removed custom plan building, uses `IBAsync.connect()` directly
- **Cleaner logging**: Reports actual connected host:port from IBAsync instance

#### `src/automation/headless_gateway.py`

- **Simplified logic**: Removed manual plan execution, delegates to `IBAsync.connect()`

#### `src/tools/auto_backfill_from_warrior.py`

- **Preserved overrides**: Still supports custom `--ib-host` and `--ib-port` but uses canonical path when possible
- **Cleaner implementation**: Removed unused import dependencies

## Connection Call Site Audit

### Before (Duplicate Logic)

```python
# Multiple different patterns across the repo:

# Pattern 1: Custom plan building (run_trading_fully_automated.py)
plan = get_ib_connect_plan()
async def _cb(h, p, c): return await ib.connect(h, p, c, fallback=bool(allow_windows))
ok, port = await try_connect_candidates(_cb, plan["host"], plan["candidates"], plan["client_id"])

# Pattern 2: Manual fallback (IBAsync.connect)
# 50+ lines of Windows IP enumeration and manual candidate attempts

# Pattern 3: Shell probing (start_gateway.sh)
# Raw socket probing with port 0 default causing :0 bug

# Pattern 4: Custom host/port resolution (setup_ib_gateway.py)
HOST='__HOST__'; PORT=__PORT__; CID=__CID__
await ib.connect(HOST, PORT, CID, fallback=bool(allow_windows))
```

### After (Canonical Path)

```python
# Single unified pattern:

# Simple canonical connection (most tools)
ib = IBAsync()
ok = await ib.connect()  # Uses get_ib_connect_plan() internally

# With explicit overrides (when needed)
ok = await ib.connect(host="custom_host", port=5000)

# All connection attempts now include:
# - TCP probe before handshake
# - ClientId cycling (cid, cid+1, cid+2)
# - Detailed diagnostics
# - Port validation (no :0)
# - JTS config awareness
```

## Connection Policy Implementation

### Linux-First Candidate Order

1. **IB_PORT** (if valid and set in environment)
2. **4002** (Gateway paper trading port)
3. **7497** (TWS paper trading port)
4. **4003, 4004** (Windows/portproxy ports, ONLY when `IB_ALLOW_WINDOWS=1`)

### Port Validation

- All ports clamped to range 1..65535
- Invalid ports (0, negative, >65535) are filtered out
- Duplicate ports are removed while preserving order

### Handshake Validation

- TCP connectivity check first
- If TCP open but handshake fails: "TCP open but API handshake failed → not API socket or SSL-only"
- Includes actionable guidance about IB API settings

### ClientId Cycling

- Attempts clientId, clientId+1, clientId+2 for each port
- Prevents "duplicate clientId" errors in multi-instance scenarios

## Configuration Awareness

### JTS Config Parsing (Non-invasive)

- Parses `~/Jts/jts.ini` for diagnostic information
- Reports: API port, SSL status, Trusted IPs
- Logs localhost inclusion in Trusted IPs for troubleshooting

### Environment Variable Behavior

- **IB_ALLOW_WINDOWS=1**: Enables Windows/portproxy fallback [4003, 4004]
- **IB_HOST**: Override connection host (default: 127.0.0.1)
- **IB_PORT**: Override and prioritize specific port
- **IB_CLIENT_ID**: Override client ID (default: 2011)

## Test Coverage

### New Test Suite: `tests/test_ib_conn.py`

- **18 test cases** covering all connection policy scenarios
- **Port validation tests**: Ensures no port 0, validates ranges
- **Windows flag behavior**: Tests all truthy/falsy variations
- **Linux-first ordering**: Verifies port precedence
- **Environment override**: Tests IB_PORT prioritization
- **JTS config parsing**: Tests file parsing and error handling

## Quality Gates Status

✅ **Ruff lint**: All files pass linting
✅ **Type checking**: No type errors
✅ **Test coverage**: 18/18 tests pass, core functionality covered
✅ **--describe validation**: All tools pass JSON validation

## Acceptance Criteria Validation

✅ **No :0 attempts**: Port validation prevents invalid port 0 usage
✅ **Handshake-based readiness**: Connection success requires API handshake
✅ **Windows gating**: IB_ALLOW_WINDOWS=1 required for 4003/4004 ports
✅ **Canonical delegation**: No script builds own host/port lists
✅ **Backwards compatibility**: Existing environment variables still work

## Diagnostics Improvements

### Before

```
❌ API connect returned False
TCP 127.0.0.1:0 connection attempt  # :0 bug
```

### After

```
✅ TCP probe successful for 127.0.0.1:4002, attempting API handshake
✅ API handshake successful for 127.0.0.1:4002 (clientId=2011)
JTS config diagnostics:
  API port (jts.ini): 4002
  SSL enabled: False
  Trusted IPs: 127.0.0.1
  Localhost in trusted IPs: True
```

## Breaking Changes

⚠️ **Minimal breaking changes**:

- `IB_ALLOW_WINDOWS=1` now required for Windows/portproxy fallback (previously auto-detected)
- `:0` port attempts eliminated (was causing connection failures anyway)
- Connection timeout may be slightly longer due to TCP probing (more reliable)

## Rollback Plan

If issues arise, the main changes can be reverted by:

1. Restoring `IBAsync.connect()` fallback logic from git history
2. Reverting `start_gateway.sh` probe changes
3. Re-enabling auto Windows detection in connection tools

All changes maintain API compatibility - existing scripts will continue to work.

---

**Report Generated**: 2025-01-17
**Total Files Modified**: 7 core files + 1 new test file
**Lines of Duplicate Code Eliminated**: ~150+ lines across multiple files
**Test Coverage Added**: 18 comprehensive test cases
