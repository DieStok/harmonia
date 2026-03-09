# Code Review Prompt: Dash Dashboard Implementation Plan

You are a senior engineer reviewing an implementation plan for a Plotly Dash dashboard that will be added to the **Harmonia** codebase — a research framework for LLM-driven metadata harmonization experiments, running on an HPC cluster (SLURM). The plan is appended at the end of this prompt.

Your job is to verify the plan is **consistent with the existing codebase** and to surface **edge cases, contradictions, or gaps** the implementer would hit. Do NOT rubber-stamp — be adversarial and specific.

---

## 1. Codebase Consistency Checks

For each item below, read the referenced source file, compare it against what the plan assumes, and report any mismatch.

### 1.1 Schema alignment
- Open `src/evaluation/schemas.py`. Confirm the exact top-level keys and nested structure of `MetricsResult` match what Section 0.1 ("Data Formats Reference → `metrics.json` top-level keys") claims. Flag any fields the plan omits or invents.
- Open `src/automation/logger.py`. Confirm `TurnRecord` and `ExperimentTrace` fields match the plan's `trace.json` description. Pay special attention to whether the tracing-plan additions (`input_tokens`, `output_tokens`, `cost_usd`, `code_executions`, `usage_records`, `run_id` on `ExperimentTrace`) are actually present yet or still TODO — the dashboard hard-depends on them.
- Open `src/automation/config.py`. Confirm `ExperimentConfig` and `ModelMetadataConfig` have the pricing fields the plan references (`pricing_prompt_per_million_tokens`, `pricing_completion_per_million_tokens`). Check whether cost calculation lives in config or elsewhere.

### 1.2 Import paths and package structure
- The plan says "`src/` is not a proper Python package" and recommends either `sys.path.insert` or adding `__init__.py` files. Check what pattern the rest of the codebase uses (e.g., `run_experiment.py`, `visualize_metrics_cli.py`). Is the plan's proposed approach (`python -m src.dashboard.app`) compatible with the existing pattern, or would it break relative imports elsewhere?
- Check if there is already a `src/__init__.py`. If not, adding one could change how existing scripts resolve imports.

### 1.3 Results directory conventions
- Scan actual directory names under `results/`. Confirm the plan's regex assumption (`{name}_{timestamp}_{run_id}` with 8-char hex suffix) holds. Identify counter-examples (SLURM job IDs, missing run_ids, unusual separators).
- Check whether `find_results_dir()` or equivalent already exists elsewhere in the codebase. If so, the dashboard should reuse it, not reimplement.

### 1.4 Phoenix integration
- Open `src/automation/tracing.py` (created by the tracing plan). Verify the span attribute names the plan lists (e.g., `harmonia.run_id`, `harmonia.turn_number`, `harmonia.cost_usd`) match what the tracing code actually sets. A single typo in an attribute name means an empty column in the dashboard.
- Check the Phoenix client API: does `get_spans_dataframe()` actually return columns named `attributes`, `context.trace_id`, `context.span_id` as the plan claims? Or has the Phoenix API changed? (Check the installed or pinned version of `arize-phoenix`.)

### 1.5 Existing visualization code
- Open `src/evaluation/visualize_metrics_cli.py`. Check whether the dashboard duplicates logic that could be shared (e.g., metric loading, color maps, figure styling). Flag opportunities to extract shared utilities rather than reimplementing.

---

## 2. Edge Case Analysis

For each edge case, state whether the plan handles it, partially handles it, or misses it entirely.

| # | Edge Case | What to check |
|---|-----------|---------------|
| 1 | **Run with no `metrics.json` and no `trace.json`** (e.g., immediately-failed experiment) | Does the overview table still show the run (from Phoenix data alone)? What happens when Trace Explorer is opened for it? |
| 2 | **Run with `metrics.json` but no Phoenix spans** (Phoenix was down or not configured during the run) | Can the dashboard still display metrics-only data? The plan's `get_all_runs()` queries Phoenix first — what's the fallback? |
| 3 | **Run with 0 turns** (agent errored on first LLM call) | Does the Trace Explorer handle an empty turns list? Do per-turn charts render an empty state or crash? |
| 4 | **Run with 50+ turns** (runaway agent hitting max-turns) | Does the turn accordion become unusably long? Is there pagination or virtualization? Do per-turn bar charts remain readable? |
| 5 | **Two runs with the same `run_id`** (hash collision or re-run with forced ID) | Does the results directory lookup return the wrong one? Is `run_id` assumed unique globally? |
| 6 | **`metrics.json` with `schema_version` != expected** | Is there version checking? What if a future schema change adds/removes fields? |
| 7 | **Phoenix returns spans from non-Harmonia traces** (other projects sharing the same Phoenix instance) | Does the query filter on `harmonia.run_id IS NOT NULL` or `harmonia.trace_type`? Or does it pull all spans? |
| 8 | **`trace.json` exists but is malformed or partially written** (experiment killed mid-write) | Does `get_run_trace()` handle JSON decode errors? |
| 9 | **Results directory with Unicode or spaces in experiment name** | The plan's directory-name parsing splits on `_`. What if the experiment name itself contains underscores (it does — e.g., `dou_harmonization_code-context_kimi-k2.5`)? How is the run_id reliably extracted? |
| 10 | **Side-by-side comparison of runs with different column sets** | If Run A evaluated columns {A, B, C} and Run B evaluated {B, C, D}, how does the per-column comparison handle the mismatch? |
| 11 | **Dashboard started before any experiments have run** (empty `results/` directory, empty Phoenix) | Does every tab handle the zero-data case without tracebacks? |
| 12 | **Port 8050 already in use** (another dashboard instance or service) | Does the app detect this and fail with a clear message, or silently fail? |
| 13 | **Stale cache after new experiment completes** | The plan says "refreshes on tab switch." What if a user stays on the Overview tab for an hour? Is there a manual refresh button on every tab, or only some? |
| 14 | **`config_snapshot.yaml` missing** (older runs before config snapshotting was added) | `get_run_config()` returns `Optional[dict]` — but do downstream consumers (e.g., cost calculation from pricing fields) handle `None`? |
| 15 | **AG Grid community edition feature usage** | Audit every AG Grid column definition in the plan. Does any use row grouping, pivoting, tree data, or server-side row model? These are enterprise-only and will silently fail or throw. |

---

## 3. Architectural Concerns

Evaluate the following and provide a recommendation for each:

1. **Single-process data loading bottleneck**: The `DashboardDataLoader` loads all `metrics.json` files at startup (Section 0.1, Gotcha 9). With 500+ runs, each requiring a file open + JSON parse, estimate the startup time. Should this be async or use a pre-built index/cache file?

2. **Memory footprint**: Phoenix `get_spans_dataframe()` for 500 runs × ~50 spans each = ~25K rows. Combined with trace.json data for selected runs, estimate peak memory. Does the 8GB SLURM allocation suffice?

3. **Callback complexity**: The plan defines click-through callbacks that cross tabs (click bar chart on Metrics tab → switch to Trace Explorer tab → populate run selector → render trace data). Count the number of chained callbacks this requires. Are there circular dependency risks beyond what `suppress_callback_exceptions=True` handles?

4. **Thread safety**: Dash runs on Flask, which can serve requests from multiple threads. Is `DashboardDataLoader` thread-safe? Does it use any mutable shared state (e.g., a cache dict) without locks?

5. **Graceful degradation ordering**: The plan handles "Phoenix not available" (Gotcha 6). But what about partial degradation — e.g., Phoenix is available but returns spans for only some runs (because older runs were traced before Phoenix was set up)? Does the join between Phoenix data and `metrics.json` handle outer-join semantics correctly?

---

## 4. Dependency and Environment Risks

1. Check whether `dash>=2.14`, `dash-bootstrap-components>=1.5`, `dash-ag-grid>=2.3`, and `plotly>=5.18` have any known conflicts with packages already in `.venv` (especially `arize-phoenix`, `pandas`, `pydantic` versions).
2. The plan pins no upper bounds. Could a future `dash 3.x` break the AG Grid integration or callback API?
3. Is `dash-ag-grid` compatible with the version of AG Grid JS that ships with it for community-edition features?

---

## 5. Output Format

Structure your review as:

```
## Critical Issues (must fix before implementation)
- [C1] ...
- [C2] ...

## Important Issues (should fix, risk of bugs)
- [I1] ...
- [I2] ...

## Minor Issues (nice to fix, low risk)
- [M1] ...
- [M2] ...

## Questions for the Plan Author
- [Q1] ...

## Positive Observations
- [P1] ...
```

For each issue, provide: **(a)** the specific file or section where the problem exists, **(b)** what the plan says vs. what the code actually does, and **(c)** a concrete fix or recommendation.

---

## Plan Under Review

{INSERT THE FULL IMPLEMENTATION PLAN HERE}