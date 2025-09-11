# Copilot Instructions for This Repository

This document defines what AI assistants may change and how they should operate within this repo.

## Documentation Rules

1. Do NOT create new general-purpose doc files (README, TODO, GUIDE, ADR, etc.).
   - Allowed documentation files: README.md, TODO.md, agent.yaml, docs/TF_1_ALIGNMENT.md, docs/ENVIRONMENT.md.
   - Only update the above files. Do not add new files in docs/ or elsewhere.
2. Keep the README.md section order intact. Append to the correct section; do not duplicate headings.
   - Agent content belongs under Developer Guide > Agent Tooling.
   - Inventory summaries belong under Developer Guide > Script Inventory Summary.
3. Cross-repo contract changes (schemas, parquet columns, manifest formats) must go through the shared ml-contracts location (or submodule when created). Do not unilaterally change contracts here.

## Testing Rules

1. All tests live under tests/ with filenames test\_\*.py. Shared fixtures go in tests/conftest.py.
2. Include edge-case coverage; target overall coverage ≥ 85%.

## Code Style & Structure

- Follow Ruff + PEP 8. Prefer readability over cleverness.
- Imports: stdlib, third-party, local; no wildcard imports.
- Annotate public APIs with type hints. Use logging for progress; avoid print in production paths.

### Agent Tooling Conventions

- Every executable tool must implement --describe that prints a single JSON object with name, inputs, outputs, and examples.
- Tools should be idempotent and use logging for progress; only the final JSON or SUMMARY may be printed.

## Copilot Agent Behaviour

- Prefer modifying existing code/docs rather than adding new files.
- Ask clarifying questions when requirements are ambiguous.
- Never create duplicate/alternate script copies; edit in place.
- Always activate the project’s Python environment before running or testing.

## Commit & Quality Gates

- Ruff lint and format must pass.
- Pytest must pass with ≥ 85% coverage.
- All tools must pass --describe JSON validation (see the VS Code task describe:all).

---

## Contracts Governance (ml-contracts)

- The canonical TF_1 manifest schema (manifest.schema.v1.json), promotion rules (promotion.rule.json), and the tiny canonical L2 parquet fixture (l2_fixture.parquet) live only in the shared ml-contracts repository, vendored here under `contracts/` (git submodule).
- Do not edit or duplicate these files locally. Propose changes in ml-contracts instead.
- Code must read contract artifacts from `contracts/` by default, or from an override directory via the CONTRACTS_DIR environment variable.
- Sessions and run windows are defined in ET with DST respected. Backfill enforces ET windows.
- The validator rejects unknown `schema_version` and fails when `production.alias` is missing (and when the `production.alias` file is absent in the model directory for non-dry emissions).

## Agent Workflow

1. **Check Documentation**
   - Read `README.md` and `ARCHITECTURE.md` before making any changes.
   - Preserve section order and headings.
   - Update the correct section (e.g., Script Inventory Summary for new scripts).

2. **Implement Changes**
   - Modify existing code or docs in place.
   - Follow style, logging, and idempotency rules.

3. **Run Quality Gates**
   - Activate the project’s Python environment.
   - Run Ruff lint + format, pytest (≥ 85% coverage), and `--describe` checks.

4. **Update Documentation**
   - Ensure all relevant documentation (`README.md` and `ARCHITECTURE.md`) is updated to reflect any new useful information.

5. **Notify (Optional)**
   - Run the notifier script to alert completion of run:

```bash
./scripts/notify_tbs.sh "${workspaceFolderBasename}" "run-$(date +%s)" "<paste-the-prompt-here>"
```
