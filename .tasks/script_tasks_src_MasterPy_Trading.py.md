# Task Log for src/MasterPy_Trading.py

- [x] Inventory issues and draft plan
- [x] Repo-wide impact scan for get_TradeDates and IB_Download_Loc usage
- [x] Implement Market_InfoCLS.get_TradeDates fixes (optional Bar)
- [x] Implement requestCheckerCLS.get_TradeDates shim (optional Bar)
- [x] Add async-safe aSendRequest and use in Download_Historical
- [x] Await sleeps and async calls (getEarliestAvailBar)
- [x] Fix IB_Download_Loc calls to pass BarObj
- [x] Fix missing method invocation and minor hygiene
- [ ] Add unit tests for trade dates and throttling
- [ ] Run CI gates: pyright, ruff, pytest with coverage
- [ ] Iterate on any failures until green

# Script Tasks: src/MasterPy_Trading.py

- [x] Add future annotations and local type aliases (SymbolT, BarSizeT)
- [x] Update method annotations to use aliases
- [x] Harden get_intervalReq time delta computation (strict conversion, clamp)
- [ ] Add targeted unit tests for interval computation edge cases
- [ ] Address fillna_typed Series/DataFrame mismatch or add Series helper
- [ ] Replace bare excepts with narrow exceptions in touched areas
- [ ] Run repo gates: ruff, pyright (repo), pytest with coverage; fix only new issues
- [ ] Update coverage JSON if tests added
