# 🚦 Copilot Instructions for This Repository

\_Copilot Chat & Copilot Agents mus- **Tests**: test scripts should be organised and go in the test folder. We want an organised test suite that is easy to navigate.

- **Activate Environment**: Always activate the project's Python environment before running, testing, or installing packages. Assume `.venv` unless otherwise specified.

- **Describe-first**: Before calling a tool, run it with `--describe` and plan arguments using the returned schema. Fail fast if JSON is invalid.follow every rule below when generating code or documentation here.\_

---

## 📚 Documentation Rules

1. **Do NOT create new README, TODO, GUIDE, or general doc files.**
   - Allowed documentation files: `README.md` and `TODO.md`.
   - **Exception:** `agent.yaml` is permitted as a machine-readable tool manifest (no prose).
   - Always update the existing files, never create duplicates.
2. Keep the `README.md` section order:
   1. Project Overview
   2. Quick Start
   3. Architecture
   4. Installation & Setup
   5. Usage Examples
   6. Migration Guide
   7. Level 2 Market-Depth Guide
   8. Testing & Validation
   9. Developer Guide
   10. Troubleshooting
3. When adding docs, **append** to the correct section—do not repeat headings.
   - **Agent content**: Place all agent-related instructions, tool catalogs, and JSON examples under Section 9 (`Developer Guide`) in a subsection `Agent Tooling`.
   - **Inventory summaries**: Place all script organisation or inventory summaries under Section 9 in a subsection `Script Inventory Summary`.

---

## 🧪 Testing Rules

1. **All tests live in `/tests/`** (or sub-folders beneath it).
   - File names must match `test_*.py`.
   - Shared fixtures go in `tests/conftest.py`.
   - No tests in `src/`, `scripts/`, or project root.
2. Include edge-case coverage and keep overall coverage **≥ 85 %**.

---

## 📝 Code Style & Structure

_The style guide follows Ruff + PEP 8 with a strict focus on readability._

| Guideline            | Rule                                                                                                                   |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| **Indentation**      | 4 spaces, no tabs                                                                                                      |
| **Line length**      | ≤ 88 chars (Ruff default)                                                                                              |
| **Strings**          | Prefer single quotes `'…'` unless the string contains a single quote                                                   |
| **Naming**           | `snake_case` for vars/functions, `PascalCase` for classes, `UPPER_CASE` for constants                                  |
| **Imports**          | One import per line, three blocks in order: stdlib → third-party → local; alphabetise inside each block; no `import *` |
| **Function size**    | Aim ≤ 30 lines; do one thing well                                                                                      |
| **Classes**          | Provide an `__init__` with clear parameters and a class-level docstring                                                |
| **Type hints**       | Annotate **all** public parameters and return types; use `Optional` and `Any` sparingly                                |
| **Error handling**   | Catch specific exceptions, log meaningful messages with `logging`, never `print` in production code                    |
| **Global variables** | Avoid; pass data via parameters or dependency injection                                                                |

### Agent Tooling Conventions

- Every executable script intended as a tool **must**:
  - Implement `--help` and `--describe`.
    `--describe` prints a single JSON object including: `name`, `version`, `inputs_schema`, `outputs_schema`, and `examples`.
  - Print a **single JSON object** with outputs on success.
  - Expose `INPUT_SCHEMA` and `OUTPUT_SCHEMA` constants (JSON Schema format).
  - Include a top-level docstring starting with `@agent.tool <tool_id>`.
  - Use `logging` for messages (no `print` except for the final JSON line).
  - Be idempotent where possible and avoid unnecessary side effects.

### Script Inventory Conventions

- Inventory tasks may create machine-readable reports under `reports/` (e.g., `.json`, `.csv`) but no prose docs.
- Summaries from inventory work must be added under `Developer Guide > Script Inventory Summary` in README.
- No file moves, deletions, or renames unless explicitly requested.

---

## 🤖 Copilot Agent Behaviour

- **Extend before creating**: modify existing code/docs when possible rather than adding new files.
- Output unified diffs (or patches) for code changes when asked to “rewrite” or “refactor.”
- Ask clarifying questions instead of guessing at unclear requirements.
- **No emojis**: do **not** include decorative emojis in commit messages, code comments, doc headings, or chat replies unless explicitly requested.
- **No duplicate script copies**: never create alternate or suffixed copies of existing scripts (e.g., `*-clean.ps1`); modify the original file or provide a diff instead.
- **Document rationale**: for every non-trivial change, add a short inline comment explaining _why_ the change was made.
- **Tests**: test scripts should be organised and go in the test folder. We want an organised test suite that is easy to navigate.
- **Activate Environment**: Always activate the project’s Python environment before running, testing, or installing packages. Assume .venv unless otherwise specified. Use source .venv/bin/activate (Linux/Mac) or .venv\Scripts\activate (Windows) before any terminal commands.

---

## 🛡️ Commit & Quality Gates (assumed pre-commit)

- Ruff linting and auto-formatting must pass.
- `pytest` must pass with ≥ 85 % coverage.
- No stray tests outside `/tests/`.
- Incremental PRs ≤ 400 LOC whenever possible.
- All tools must pass a `describe:all` quality gate (valid JSON from `--describe`).
- Inventory tasks must run without errors.

---

## 🏷️ Metadata

---

## applyTo: "\*\*"
