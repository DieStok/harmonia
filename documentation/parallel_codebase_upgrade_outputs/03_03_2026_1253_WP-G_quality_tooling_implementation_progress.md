# WP-G: Quality Tooling - Pre-commit + Smoke Tests

## Date: 2026-03-03

## Summary

Implemented Work Package G: added pre-commit hooks with ruff/shellcheck/yamllint, configured ruff linting in pyproject.toml, ran initial safe auto-fix cleanup across the codebase, and created two new smoke test suites.

## Changes Made

### G1: Ruff config in pyproject.toml
- Added `[tool.ruff]` section with `line-length = 100`
- Added `[tool.ruff.lint]` selecting F (pyflakes), E (pycodestyle errors), W (pycodestyle warnings), I (isort) rules
- Ignoring E501 (line length) since that is informational only with the line-length setting
- Excluding `src/context_management/test_*` and `src/bdikit_context/__about__.py` from linting

### G2: .pre-commit-config.yaml
- Created `.pre-commit-config.yaml` in repo root with three hooks:
  - `ruff-pre-commit` v0.4.0 with `--fix` argument
  - `shellcheck-py` v0.10.0.1 for `.sh` files (excluding `jobs/`)
  - `yamllint` v1.35.1 with relaxed config (excluding `experiments/`)

### G3: Install pre-commit and ruff cleanup
- Installed `pre-commit` (v4.5.1) and `ruff` (v0.15.4) into `.venv` using `uv pip install`
- Ran `pre-commit install` to wire up git hooks
- Ran `ruff check src/ --fix --select F,I` for safe auto-fixes only (unused imports + isort)
- Result: 44 fixes applied across ~30 files, 28 remaining errors (mostly Jinja2 template `.py` files with `{{ }}` syntax that ruff cannot parse)

### G4: tests/test_config_loading.py
- Created parametrized test that loads each of the 30 automated experiment configs via `automation.config.load_config()`
- Each test verifies the config has a name, LLM provider, and LLM model
- Sanity check test verifies at least 25 configs exist
- All 31 tests pass

### G5: tests/fixtures/sample_metrics.json and tests/test_metrics_smoke.py
- Created minimal but realistic `sample_metrics.json` fixture matching the `MetricsResult` pydantic schema
  - Includes `metadata`, `column_mapping` (with details), `column_values` (with error categorization and confusion matrix), `overall_summary`
  - Contains one column (`sample_type`) with 10 cells, one case-only error
- Created `test_metrics_smoke.py` with two tests:
  - `test_fixture_loads`: verifies JSON structure has required top-level keys
  - `test_build_tables_returns_dataframes`: calls `normalize.build_tables()` and verifies it returns a dict with the expected table keys (runs, column_mapping, column_values, confusion) and at least one row in runs
- Key design decision: `build_tables()` takes `list[tuple[Path, dict]]` not `list[dict]`, so the test correctly passes `[(FIXTURE, data)]`

### G6: pytest configuration in pyproject.toml
- Added `[tool.pytest.ini_options]` section with `testpaths = ["tests", "src/context_management"]` and `python_files = ["test_*.py"]`
- This ensures both the new `tests/` directory and the existing `src/context_management/test_kernel_state_budget.py` are discovered

## Test Results

- **New tests**: 33/33 passing (31 config loading + 1 config count + 1 fixture load + 1 build_tables smoke)
- **Existing kernel state budget tests**: 15/15 passing (unaffected by changes)
- **Pre-existing test failures**: 4 tests in `test_configurable_prompts_working.py` and `test_prompt_integration.py` were already failing before this WP (not introduced by these changes)

## Decisions

1. **Only safe ruff auto-fixes (F, I)**: As instructed, only ran pyflakes unused-import and isort fixes. Did not auto-fix E/W rules to avoid unintended behavior changes.
2. **Jinja2 template files**: Ruff reports syntax errors on `.py` files under `src/bdikit_context/procedures/python3/` that contain Jinja2 template syntax (`{{ }}`). These are expected and cannot be fixed -- they are templates, not regular Python.
3. **build_tables() signature**: The test correctly uses `list[tuple[Path, dict]]` rather than `list[dict]`, matching the actual `build_tables()` function signature in `normalize.py`.

## Files Created
- `.pre-commit-config.yaml`
- `tests/test_config_loading.py`
- `tests/test_metrics_smoke.py`
- `tests/fixtures/sample_metrics.json`
- `documentation/parallel_codebase_upgrade_outputs/03_03_2026_1253_WP-G_quality_tooling_implementation_progress.md`

## Files Modified
- `pyproject.toml` (added ruff config + pytest config)
- ~30 source files under `src/` (ruff auto-fix: unused import removal + isort)

## Commit Note
All WP-G changes (new files, ruff cleanups, pyproject.toml config) were initially swept into
a shared commit by another parallel work package (WP-F, commit 01e1638) because all 7 WPs share
the same working directory. A follow-up WP-G-specific commit is created to provide the correct
attribution and commit message.
