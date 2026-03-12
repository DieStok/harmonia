---
title: "GEO-LLM Experiment Dashboard Overhaul"
type: feat
status: active
date: 2026-03-12
origin: docs/brainstorms/2026-03-12-dashboard-improvements-brainstorm.md
---

# GEO-LLM Experiment Dashboard Overhaul

## Enhancement Summary

**Deepened on:** 2026-03-12
**Sections enhanced:** 8 (all implementation phases + architecture)
**Research agents used:** Dash URL state patterns, AG Grid v31 multi-select, Dash lazy loading/background callbacks, Dash UI components (DBC 1.6.0)

### Key Improvements from Research
1. **AG Grid v31 API change**: `checkboxSelection` column property is deprecated; must use `dashGridOptions.rowSelection: {mode: "multiRow", checkboxes: True}` instead
2. **URL sync pattern**: Single callback with `ctx.triggered_id` + `no_update` prevents circular loops; "state bundle" `dcc.Store` simplifies many-input sync
3. **Pattern-matching callbacks (`MATCH`)** for deferred plot gallery: one callback handles all 6 plots instead of 6 separate callbacks
4. **Background callbacks with `DiskcacheManager`** for subprocess CLI tool execution — keeps UI responsive
5. **`Patch()` for dynamic filter rows**: Partial children updates via `patched.append()` / `del patched[i]` instead of rebuilding the entire children list
6. **Searchable dropdown gotcha**: When using component labels (html.Span), must set `search` property on each option or search only matches `value`

### New Considerations Discovered
- AG Grid `selectedRows` supports `{"ids": [...]}` form for programmatic selection restore from URL — much cleaner than passing full row objects
- `dcc.Loading` with `target_components` (Dash 2.17+) enables per-plot spinners decoupled from container hierarchy
- Browser history pollution: each URL update creates a history entry — consider debouncing or using `hash` for volatile state
- Pattern-matching callbacks with >100 dynamic components have known performance issues (Dash #3008) — limit filter rows
- `parse_qs()` returns lists (e.g., `{"tab": ["trace"]}` not `{"tab": "trace"}`) — always index `[0]`
- `prevent_initial_call=False` needed for URL sync callback (must run on page load)
- `dcc.Clipboard` silently fails in non-HTTPS contexts (but localhost/SSH tunnels work fine)

---

## Overview

Major overhaul of the Harmonia experiment dashboard addressing six core problems: eager data loading causing slowness with 100-500 runs, limited Overview table (small, unsorted, no selection), broken failure categorization showing "Unknown" instead of named categories, metrics tab that never loads, no trace search capabilities, and no diagnostic transparency. The dashboard is renamed to **GEO-LLM Experiment Dashboard**.

## Problem Statement

The dashboard was built for small-scale use (~20 runs) and does not scale to the current 100-500 run workload. All data is loaded eagerly on startup, every tab renders all plots immediately, and there is no mechanism to select a subset of runs to focus on. The metrics tab is completely non-functional (never finishes loading). The failure analysis tab shows "Unknown" for all failures despite the CLI tool detecting 18 named categories. Users cannot see what data/files produced the visualizations.

## Proposed Solution

Restructure the dashboard around three principles:
1. **Lazy loading**: Only load data when needed (per-tab activation, deferred heavy plots)
2. **Selection-driven**: Overview table selection drives all other tabs
3. **Diagnostic transparency**: Every tab exposes its data sources and raw data

(see brainstorm: `docs/brainstorms/2026-03-12-dashboard-improvements-brainstorm.md`)

## Technical Approach

### Architecture

The existing Dash callback architecture is preserved. Key changes:

1. **New shared stores**: `selected-runs-store` (list of run_ids), `active-filters-store` (filter definitions), `date-range-store` ("last5d" or "all"), `selection-explicit` (boolean — distinguishes "no selection made yet" from "user cleared selection")
2. **URL state sync**: `dcc.Location` + single bidirectional callback using `ctx.triggered_id` + `no_update` to break cycles (research-validated pattern)
3. **Tab-level lazy loading**: `render_tab()` callback unchanged but each tab function now loads its own data on-demand rather than receiving pre-loaded data
4. **New shared components**: `options_panel.py` (using `dbc.Accordion`), `diagnostic_panel.py` (using `html.Details`), `multi_filter.py` (using pattern-matching callbacks + `Patch()`)
5. **Deferred plots**: Pattern-matching callbacks (`MATCH`) for the metrics plot gallery — one callback handles all 6 plots
6. **Background subprocess**: `DiskcacheManager` for the CLI tool regeneration — keeps UI responsive

### Implementation Phases

#### Phase 1: Foundation (Core Infrastructure)

Shared infrastructure that all subsequent phases depend on.

**1.1 Rename dashboard**
- [x] Update `app.py`: navbar brand → "GEO-LLM Experiment Dashboard"
- [x] Update `app.py`: `app.title` → "GEO-LLM Experiment Dashboard"
- Files: `src/dashboard/app.py`

**1.2 Add new dcc.Store components**
- [x] Add `selected-runs-store` (type=session, default=[]) — list of selected run_id strings
- [x] Add `active-filters-store` (type=session, default=[]) — list of filter dicts `{column, operator, value}`
- [x] Add `date-range-store` (type=session, default="last5d")
- [x] Add `selection-explicit` (type=session, default=False) — tracks whether user has made an explicit selection (prevents re-applying "last 10" default after user clears selection)
- [x] Add `dcc.Location(id="url", refresh=False)` for URL state
- [x] Add toast container at top-level layout: `dbc.Toast(id="notification-toast", is_open=False, duration=4000, dismissable=True, style={"position": "fixed", "top": 10, "right": 10, "zIndex": 1050})`
- Files: `src/dashboard/app.py`

**1.3 URL state sync callbacks**

*Research insight: Use a single bidirectional callback with `ctx.triggered_id` + `no_update` to prevent circular loops. The `no_update` return is the cycle-breaker — when URL triggers, update stores but return `no_update` for URL output, and vice versa.*

- [x] Single callback with both `url.search` and stores as Input/Output:
  ```python
  @app.callback(
      Output("url", "search"),
      Output("selected-runs-store", "data", allow_duplicate=True),
      Output("date-range-store", "data", allow_duplicate=True),
      Output("tabs", "active_tab", allow_duplicate=True),
      Input("url", "search"),
      Input("selected-runs-store", "data"),
      Input("date-range-store", "data"),
      Input("tabs", "active_tab"),
      prevent_initial_call=False,  # Must run on page load to parse initial URL
  )
  def sync_url_state(url_search, selected_runs, date_range, active_tab):
      trigger = ctx.triggered_id
      if trigger == "url" or not ctx.triggered:
          # URL changed or initial load → parse params, push to stores
          params = parse_qs(url_search.lstrip("?")) if url_search else {}
          return (no_update,
                  params.get("runs", [""])[0].split(",") if params.get("runs") else no_update,
                  params.get("date", ["last5d"])[0],
                  params.get("tab", ["overview"])[0])
      else:
          # Store/tab changed → serialize to URL, don't touch stores
          params = {}
          if selected_runs: params["runs"] = ",".join(selected_runs)
          if date_range != "last5d": params["date"] = date_range
          if active_tab != "overview": params["tab"] = active_tab
          return (f"?{urlencode(params)}" if params else "",
                  no_update, no_update, no_update)
  ```
- [x] Format: `?tab=metrics&runs=a1b2c3d4,e5f6g7h8&date=last5d&filter=model:contains:llama`
- [x] **Gotcha:** `parse_qs()` returns lists — always index `[0]`
- [x] **Gotcha:** Each URL update creates a browser history entry — consider debouncing rapid filter changes
- [x] **Gotcha:** On page load, both URL params AND session storage may have values — URL should take precedence
- Files: `src/dashboard/app.py`

**1.4 Data loader: timing instrumentation**
- [x] Add `_timing` dict to `DashboardDataLoader` tracking load durations per method
- [x] Wrap each public method with timing context manager
- [x] Add `get_timing_info() -> dict` method returning timing + cache hit/miss stats
- [x] Add `get_loaded_files() -> list[str]` method tracking which files were read
- Files: `src/dashboard/data_loader.py`

**1.5 Data loader: lightweight startup**
- [ ] Split `_parse_dir_metadata()` into two tiers: (deferred — current impl adequate for 500 runs)
  - Tier 1 (startup): Extract run_id, experiment_name, results_dir, start_time from directory name pattern + config_snapshot.yaml (no trace.json parse)
  - Tier 2 (on-demand): Full trace.json top-level parse for tokens/cost/status/turns
- [ ] `get_all_runs()` returns Tier 1 data by default; flag `full=True` triggers Tier 2 (deferred)
- [x] Add date filtering: `get_all_runs(since_days=5)` filters by start_time extracted from dir name timestamp
- Files: `src/dashboard/data_loader.py`

**1.6 Create shared diagnostic panel component**

*Research insight: Use `html.Details` + `html.Summary` — zero callbacks needed, semantic HTML5, lightweight. Use nested `html.Details` for raw JSON sub-section.*

- [x] New file `src/dashboard/components/diagnostic_panel.py`
- [x] Function: `create_diagnostic_panel(panel_id: str, source_files: list[str], raw_data: dict, timing: dict, cache_info: dict, cli_command: str | None) -> html.Details`
- [x] Renders as collapsible `<details>` (closed by default) with:
  - "Diagnostic Information" as `<summary>` (styled: cursor pointer, #6c757d color, 0.85rem font)
  - Source file paths as monospace table rows
  - Timing table (method → duration_ms)
  - Cache status badges (hit/miss per cache)
  - CLI command in a copyable code block with `dcc.Clipboard(target_id=panel_id+"-cli")`
  - Nested `html.Details` for "Raw JSON" sub-section with `html.Pre` (maxHeight: 300px, overflow: auto) + `dcc.Clipboard`
- [x] **Note:** `dcc.Clipboard` with `target_id` copies `.innerText` — works for `html.Pre` elements. Silently fails in non-HTTPS but localhost/SSH tunnels work fine.
- Files: `src/dashboard/components/diagnostic_panel.py`

**1.7 Create shared options panel component**

*Research insight: Use `dbc.Accordion` with `start_collapsed=True` and `flush=True` — gives built-in toggle header, styled, accessible. Better than `dbc.Collapse` (requires separate button) or `html.Details` (unstyled).*

- [x] New file `src/dashboard/components/options_panel.py`
- [x] Function: `create_options_panel(panel_id: str, title: str, children: list) -> dbc.Accordion`
- [ ] Implementation:
  ```python
  dbc.Accordion(
      [dbc.AccordionItem(children, title=title, item_id="options")],
      id=panel_id,
      start_collapsed=True,
      flush=True,
      className="mb-3",
  )
  ```
- [x] Default: collapsed (saves space). No `dcc.Store` needed — `dbc.Accordion` manages its own open/closed state.
- [x] For tabs needing multiple independent sections (e.g., "Filters" + "Display"), use `always_open=True`
- Files: `src/dashboard/components/options_panel.py`

**1.8 Create multi-filter widget component**

*Research insight: Use pattern-matching callbacks with dict IDs (`{"type": "filter-column", "index": N}`) + `Patch()` for partial children updates. `Patch().append()` adds rows without rebuilding the entire list; `del patched[pos]` removes rows. Track next index in `dcc.Store` to avoid ID collisions after deletion.*

- [x] New file `src/dashboard/components/multi_filter.py`
- [x] Function: `create_multi_filter(filter_id: str, columns: list[str]) -> html.Div`
- [x] Layout: container div + "Add filter" button + `dcc.Store(id=filter_id+"-next-index", data=0)`
- [x] Each filter row (created dynamically): column dropdown + operator dropdown (contains/does not contain) + text input + trash button (all with dict IDs `{"type": "filter-*", "index": N}`)
- [x] Add row callback: uses `Patch().append(make_filter_row(next_index))` + increments index store
- [x] Remove row callback: uses `ctx.triggered_id["index"]` to find position, then `del patched[pos]`
- [x] Collect callback: uses `ALL` selector to gather all filter values into `active-filters-store`
- [x] **Performance note:** Pattern-matching with >100 dynamic components has known issues (Dash #3008). Cap at reasonable limit (e.g., 20 filter rows).
- [ ] Invalid regex in "contains" filter: wrap in try/except, show `dbc.FormFeedback` validation error (deferred)
- Files: `src/dashboard/components/multi_filter.py`

---

#### Phase 2: Overview Tab Redesign

The central hub that drives all other tabs.

**2.1 Full-page table layout**
- [x] Remove the 9/3 column split (table + pie chart)
- [x] Table spans full width; pie chart moves to options panel or below table
- [x] Remove fixed `height: 500px` — let AG Grid fill available space
- Files: `src/dashboard/tabs/overview.py`, `src/dashboard/components/run_table.py`

**2.2 AG Grid configuration changes**

*Research insight: In dash-ag-grid v31, `checkboxSelection` and `headerCheckboxSelection` as column properties are **deprecated**. Selection config moved to `dashGridOptions.rowSelection` dict. Also, use `getRowId` for reliable programmatic selection restore from URL.*

- [x] Replace current `dashGridOptions` with v31 selection API:

  ```python
  dag.AgGrid(
      id="runs-table",
      getRowId="params.data.run_id",  # enables {"ids": [...]} selection restore
      dashGridOptions={
          "rowSelection": {
              "mode": "multiRow",
              "checkboxes": True,
              "headerCheckbox": True,
              "selectAll": "filtered",  # header checkbox selects all filtered rows
              "enableClickSelection": True,
          },
          "pagination": True,
          "paginationPageSize": 100,
          "paginationPageSizeSelector": [50, 100, 200, 500],
          "animateRows": False,  # disable for performance with 500 rows
      },
  )
  ```

- [x] Add default sort via `sort` + `sortIndex` in columnDefs (not dashGridOptions):

  ```python
  {"field": "start_time", "sort": "desc", "sortIndex": 0},
  {"field": "model", "sort": "asc", "sortIndex": 1},
  {"field": "context", "sort": "asc", "sortIndex": 2},
  ```

- [x] Add `context` column (from `infer_context(experiment_name)`)
- [x] Add new columns with `hide: True`:

  ```python
  {"field": "config_path", "headerName": "Config Path", "hide": True},
  {"field": "results_dir", "headerName": "Results Dir", "hide": True},
  {"field": "analysis_path", "headerName": "Analysis Path", "hide": True},
  ```

- [ ] Column visibility toggle via `columnState` property (deferred — AG Grid built-in column menu suffices):

  ```python
  @callback(
      Output("runs-table", "columnState"),
      Input("column-visibility-checklist", "value"),
      State("runs-table", "columnState"),
  )
  def toggle_columns(visible_cols, current_state):
      return [{**col, "hide": col["colId"] not in visible_cols} for col in current_state]
  ```

- [x] **Performance note:** 500 rows with client-side pagination is well within AG Grid's comfort zone. Page size 100 limits DOM nodes to 100. Keep `rowData` lean — exclude large fields not needed for display.
- Files: `src/dashboard/components/run_table.py`

**2.3 Selection → store sync**

*Research insight: AG Grid with `getRowId` supports `selectedRows = {"ids": [...]}` for programmatic selection — much cleaner than passing full row objects. Use this for URL state restore.*

- [x] Callback: `runs-table.selectedRows` → extract run_ids → update `selected-runs-store` + set `selection-explicit=True`
- [ ] Reverse sync (URL restore): callback sets `runs-table.selectedRows = {"ids": selected_run_ids}` (deferred — URL sync handles tab/runs)
- [x] Add "Select all visible" button → selects all rows matching current filters
- [x] Add "Clear selection" button → empties `selected-runs-store` + sets `selection-explicit=True` (so default doesn't re-apply)
- [ ] Default selection: when `selected-runs-store` is empty AND `selection-explicit` is False (first load), auto-select last 10 runs by date (deferred)
- [ ] **Edge case:** After data refresh, validate that selected run_ids still exist (deferred)
- Files: `src/dashboard/tabs/overview.py`, `src/dashboard/app.py`

**2.4 Date range toggle**
- [x] Add `dbc.RadioItems(id="date-range-toggle", options=["Last 5 days", "All runs"], value="Last 5 days")`
- [x] Callback: toggle value → `date-range-store` → filters `get_all_runs(since_days=5)` or `get_all_runs()`
- [x] Table data updates reactively
- Files: `src/dashboard/tabs/overview.py`

**2.5 Multi-filter integration**
- [x] Integrate `create_multi_filter()` in Overview options panel
- [x] Callback: `active-filters-store` → apply pandas `.str.contains()` / `.str.contains(...)==False` per filter → update table data
- Files: `src/dashboard/tabs/overview.py`

**2.6 Overview options panel**
- [x] Add collapsible options panel with:
  - Date range toggle
  - Column visibility checkboxes (default: hide path columns)
  - Multi-filter widget
  - Refresh button (moved from current position)
- Files: `src/dashboard/tabs/overview.py`

**2.7 Overview diagnostic panel**
- [x] Add `create_diagnostic_panel()` at bottom showing:
  - Results directory scanned
  - Number of trace.json / metrics.json / config files found
  - Analysis report path and freshness
  - Data loading timing
- Files: `src/dashboard/tabs/overview.py`

---

#### Phase 3: Selection Propagation & Tab Lazy Loading

Wire selection to all tabs and make them load on-demand.

**3.1 Refactor render_tab() for lazy loading**

*Research insight: Use the callback-based content method — do NOT put content in `dcc.Tab(children=...)`. Content for inactive tabs is never constructed. Wrap individual heavy components in `dcc.Loading`, NOT the entire tab-content div (avoids spinner flash on sub-callback triggers).*

- [x] Each tab render function now accepts `selected_run_ids: list[str]` parameter
- [x] Tab functions only call data_loader methods when rendered (not at startup)
- [ ] Wrap individual plot containers in `dcc.Loading(type="circle", delay_show=200)` (deferred — not blocking)
- [ ] Use `dcc.Loading(target_components={"graph-id": "figure"})` (Dash 2.17+) for precise spinner targeting (deferred)
- [x] Only the active tab renders; inactive tabs return placeholder `html.Div()`
- Files: `src/dashboard/app.py`

**3.2 Auto re-render on selection change**
- [x] Add `selected-runs-store` as Input to `render_tab()` callback
- [x] When selection changes, active tab re-renders with new selection
- [x] Inactive tabs re-render when navigated to (not eagerly)
- Files: `src/dashboard/app.py`

**3.3 Wire selection to Failure Analysis tab**
- [x] `render_failure_analysis()` receives `selected_run_ids`
- [x] Filters `get_all_runs_with_failures()` DataFrame to selected runs
- [x] All plots (heatmap, bar, sunburst) respect the filter
- Files: `src/dashboard/tabs/failure_analysis.py`

**3.4 Wire selection to Error Analysis tab**
- [x] `render_error_analysis()` receives `selected_run_ids`
- [x] Filters `get_error_breakdown()` and `get_column_errors()` to selected runs
- [ ] Add `html.H4("Error Analysis")` header at top (deferred cosmetic)
- Files: `src/dashboard/tabs/error_analysis.py`

**3.5 Wire selection to Tokens & Cost tab**
- [x] `render_token_cost()` receives `selected_run_ids`
- [x] Filters token summary data to selected runs
- Files: `src/dashboard/tabs/token_cost.py`

**3.6 Wire selection to Comparison tab**
- [x] Run A/B dropdowns: `render_comparison()` accepts `selected_run_ids` (selection-aware)
- [ ] If only 2 runs selected, auto-populate run A and run B (deferred)
- Files: `src/dashboard/tabs/comparison.py`

**3.7 Add options panels to all tabs (with specific defaults from brainstorm)**
- [ ] Failure Analysis: group-by selector (model/context/failure_reason/provider, default: model), show/hide charts (heatmap/bar/sunburst, **default: heatmap + bar shown, sunburst hidden**), severity filter (critical/error/warning/info, **default: all**)
- [ ] Error Analysis: error type filter (hallucinations/omissions/genuine/whitespace-only/case-only, default: all), group-by (run/column/error type, default: error type)
- [ ] Tokens & Cost: group-by (model/provider/experiment, default: model), chart selector (cost bars/token bars/cost vs turns/efficiency, **default: cost bars + token bars**)
- [ ] Comparison: show/hide sections (diff card/turn comparison/cross-model heatmap, **default: all shown**)
- [ ] All: use `create_options_panel()` component
- Files: all tab files

**3.8 Add diagnostic panels to all tabs**
- [ ] Each tab: append `create_diagnostic_panel()` at bottom
- [ ] Pass tab-specific file paths, raw data, timing, cache info
- [ ] Failure Analysis: include CLI command to regenerate analysis report
- Files: all tab files

---

#### Phase 4: Failure Analysis Fix

Fix "Unknown" categorization and add regeneration capability.

**4.1 Diagnose the Unknown problem**
- [x] In `data_loader.get_all_runs_with_failures()`: check if `get_analysis_report()` returns None
- [x] If None: all runs without metrics get `failure_reason="Unknown"` (this is the root cause)
- [x] Add logging: `logger.warning("No analysis report found — failure reasons will be 'Unknown'")`
- Files: `src/dashboard/data_loader.py`

**4.2 Analysis report staleness indicator**
- [ ] In Overview tab: show badge next to "Analysis Report" in diagnostic panel
  - Green: report < 1 hour old
  - Yellow: report 1-24 hours old
  - Red: report > 24 hours old or missing
- [ ] Show report generation timestamp in diagnostic panel
- Files: `src/dashboard/tabs/overview.py`

**4.3 "Regenerate Analysis" button**

*Research insight: Use Dash background callbacks with `DiskcacheManager` for subprocess calls. This runs the callback in a separate process so the main Dash server stays responsive. The `running` parameter auto-disables the button and shows status text.*

- [x] Add `diskcache` to dependencies: `import diskcache; cache = diskcache.Cache("./cache"); background_callback_manager = DiskcacheManager(cache)` — pass to `Dash(background_callback_manager=...)`
- [x] Add button in Failure Analysis options panel: "Regenerate Analysis Report"
- [x] Background callback:

  ```python
  @callback(
      Output("regenerate-output", "children"),
      Input("regenerate-btn", "n_clicks"),
      background=True,
      running=[
          (Output("regenerate-btn", "disabled"), True, False),
          (Output("regenerate-status", "children"), "Regenerating analysis...", ""),
      ],
      prevent_initial_call=True,
  )
  def regenerate_analysis(n_clicks):
      result = subprocess.run(
          [".venv/bin/python", "code_development_tools_agents/.../read_and_analyze_logs_and_traces_cli.py", "--json"],
          capture_output=True, text=True, timeout=300,
      )
      # Write output, refresh data_loader, show toast
  ```

- [x] After completion: call `data_loader.refresh()` and re-render tab
- [x] Show success/failure via `dbc.Toast` notification
- [x] **Always set `timeout=300`** on `subprocess.run` to avoid zombie processes
- Files: `src/dashboard/tabs/failure_analysis.py`, `src/dashboard/app.py`

**4.4 Better "Unknown" labeling**
- [x] In `failure_io.py`: change line 99 from `failure_reason = "Unknown"` to `failure_reason = "No output (undiagnosed)"`
- [x] This makes it clear the run failed but no pattern matched
- Files: `src/evaluation/visualization/failure_io.py`

**4.5 Display named failure taxonomy categories**
- [ ] Failure distribution bar chart and sunburst should display the specific named categories from the CLI tool (e.g., "Beaker Server Hung", "Ollama Model Not Found", "LLM-Side Timeout on Complex Tasks") — not just "Unknown"
- [ ] In the failure explanations list, include the taxonomy class code (e.g., "1A: Beaker Server Hung", "2A: Ollama Model Not Found") for traceability to `types_of_log_and_trace_problems.yaml`
- [ ] Group failure reasons by their 6 top-level categories (Infrastructure, Model Config, LLM Behavioral, Data/Path, Output, Diagnostic) in the sunburst chart hierarchy
- Files: `src/dashboard/tabs/failure_analysis.py`

**4.6 Failure Analysis diagnostic panel**
- [ ] Show: analysis report file path, generation timestamp, CLI command used
- [ ] Show raw problems list per run (from analysis report JSON)
- [ ] Include: "Run this command to regenerate: `.venv/bin/python code_development_tools_agents/...`"
- Files: `src/dashboard/tabs/failure_analysis.py`

---

#### Phase 5: Metrics Tab Rework

Transform from "load everything and render 6 plots" to "summary cards + on-demand plot gallery".

**5.1 Summary cards (lightweight)**
- [ ] On tab load: show 4 summary cards computed from run metadata + selected runs count:
  - "Selected Runs" (count)
  - "Models Represented" (unique model count)
  - "Experiments" (unique experiment count)
  - "Date Range" (min-max start_time)
- [ ] These require NO metrics.json loading (use `get_all_runs()` data)
- [ ] Add a second row of cards that loads asynchronously (with spinner placeholders):
  - "Avg Accuracy" (from metrics)
  - "Best Model" (highest avg accuracy)
  - "Total Cost" (from token data)
  - "Total Tokens" (from token data)
- Files: `src/dashboard/tabs/metrics.py`

**5.2 Plot gallery UI**
- [ ] Replace direct plot rendering with a grid of clickable cards:
  ```
  [Accuracy Bars] [Cost vs Accuracy] [Column Heatmap]
  [Token Usage]   [Radar Chart]      [Model Boxplots]
  ```
- [ ] Each card: title + brief description + "Show"/"Hide" toggle
- [ ] **Accuracy bars auto-shown by default** — this plot loads automatically when the tab opens (brainstorm decision: "default: accuracy bars only (auto-shown)")
- [ ] All other plots hidden by default, shown on click
- [ ] Multiple plots can be visible simultaneously via individual toggles
- Files: `src/dashboard/tabs/metrics.py`

**5.3 Deferred plot callbacks**

*Research insight: Use a single pattern-matching `MATCH` callback for all 6 plots. Each plot card gets a dict ID `{"type": "show-plot-btn", "index": "accuracy"}`. One callback dispatches to the right figure builder based on `ctx.triggered_id["index"]`. Use `prevent_initial_call=True` so plots don't fire on load.*

- [ ] Plot card IDs: `{"type": "show-plot-btn", "index": name}` and `{"type": "plot-container", "index": name}`
- [ ] Single MATCH callback:

  ```python
  PLOT_BUILDERS = {"accuracy": build_accuracy_bars, "cost_accuracy": build_cost_scatter, ...}

  @callback(
      Output({"type": "plot-container", "index": MATCH}, "children"),
      Input({"type": "show-plot-btn", "index": MATCH}, "n_clicks"),
      State({"type": "show-plot-btn", "index": MATCH}, "id"),
      State("selected-runs-store", "data"),
      prevent_initial_call=True,
  )
  def render_plot_on_click(n_clicks, btn_id, selected_runs):
      fig = PLOT_BUILDERS[btn_id["index"]](selected_runs)
      return dcc.Graph(figure=fig)
  ```

- [ ] Wrap each plot container in `dcc.Loading(type="circle", delay_show=200)`
- [ ] Auto-show accuracy bars: set `n_clicks=1` on the accuracy button at layout creation time, or render it directly
- [ ] Plots respect `selected-runs-store` filter via State
- Files: `src/dashboard/tabs/metrics.py`, `src/dashboard/app.py`

**5.4 Metrics options panel**
- [ ] Metric selector: accuracy / F1 / precision / recall (default: accuracy)
- [ ] Sort order: by accuracy / by model / by date
- [ ] Column subset selector (for heatmap/radar): multi-dropdown of harmonization column names
- Files: `src/dashboard/tabs/metrics.py`

**5.5 Metrics diagnostic panel**
- [ ] Show which metrics.json files were loaded
- [ ] Show per-run metric extraction timing
- [ ] Show raw metrics data as JSON for selected runs
- Files: `src/dashboard/tabs/metrics.py`

---

#### Phase 6: Trace Explorer Improvements

**6.1 Run selector with search**

*Research insight: When using component labels (html.Span) in dcc.Dropdown, search only matches `value` unless you set the `search` property on each option. Always set `search` with all searchable terms.*

- [ ] Replace `dcc.Dropdown` with searchable version:

  ```python
  dcc.Dropdown(
      id="trace-run-selector",
      options=[{
          "label": html.Span([
              html.Span(rid, style={"fontWeight": "bold"}),
              html.Span(f" | {model} | {exp} ({status})", style={"color": "#888"}),
          ]),
          "value": rid,
          "search": f"{rid} {model} {exp} {status}",  # All searchable terms
      } for rid, model, exp, status in run_info],
      placeholder="Type to search by run ID, model, or experiment...",
      searchable=True,
  )
  ```

- [ ] **Gotcha:** Without `search` property, typing "llama" won't find a run with model "llama-3.1" if label is an html.Span
- Files: `src/dashboard/tabs/trace_explorer.py`

**6.2 In-trace search bar**
- [ ] Add `dbc.Input(id="trace-search-input", placeholder="Search in trace content...", type="text")` above the turn accordion
- [ ] Callback: search text → filter turns where `user_message`, `agent_response`, or `code_executions` contain the search string (case-insensitive)
- [ ] Matching turns: expand accordion item, highlight match (wrap in `<mark>` via regex), **scroll to first match** (use `html.A(id="search-match-anchor")` or JS callback to scroll into view)
- [ ] Show: "X of Y turns match"
- [ ] Clear search: show all turns
- Files: `src/dashboard/tabs/trace_explorer.py`, `src/dashboard/app.py`

**6.3 Raw trace JSON panel**
- [ ] Add collapsible `html.Details` at bottom: "Raw Trace Information"
- [ ] Content: full trace.json rendered with `dcc.Markdown` in a ```json code fence
- [ ] Pre-process: unescape `\n` in code strings to actual newlines for readability
- [ ] Add copy-to-clipboard button (using `dcc.Clipboard`)
- Files: `src/dashboard/tabs/trace_explorer.py`

**6.4 Trace Explorer options panel**
- [ ] Turns per page selector: 10/20/50 (default: 20)
- [ ] Show/hide toggles: tool calls, timing info, token counts (default: show all)
- [ ] These filter what's displayed in turn accordion items
- Files: `src/dashboard/tabs/trace_explorer.py`

**6.5 Trace Explorer diagnostic panel**
- [ ] Show: trace.json file path, file size, number of turns
- [ ] Show: Phoenix span availability and span count
- [ ] Show: metrics.json availability and path
- Files: `src/dashboard/tabs/trace_explorer.py`

---

#### Phase 7: Remaining Tab Improvements

**7.1 Error Analysis tab header**
- [ ] Add `html.H4("Error Analysis")` at the top of the layout
- Files: `src/dashboard/tabs/error_analysis.py`

**7.2 Error Analysis options panel**
- [ ] Error type filter: checkboxes for hallucinations, omissions, genuine, whitespace-only, case-only (default: all checked)
- [ ] Group-by: run / column / error type (default: error type)
- Files: `src/dashboard/tabs/error_analysis.py`

**7.3 Tokens & Cost options panel**
- [ ] Group-by selector: model / provider / experiment (default: model)
- [ ] Chart selector: checkboxes for cost bars, token bars, cost vs turns, efficiency (default: cost bars + token bars shown)
- Files: `src/dashboard/tabs/token_cost.py`

**7.4 Comparison tab pre-filtered dropdowns**
- [ ] Run A/B dropdown options: selected runs first (with separator label "Selected Runs"), then all other runs under "All Runs"
- [ ] If exactly 2 runs selected on Overview, auto-populate run A and run B
- Files: `src/dashboard/tabs/comparison.py`

**7.5 All tabs: diagnostic panels**
- [ ] Ensure every tab has a diagnostic panel with appropriate content (covered per-tab in earlier phases, this is the verification step)
- Files: all tab files

---

## Alternative Approaches Considered

1. **Pre-aggregated cache (parquet file):** Fastest runtime (<1s load) but requires running an aggregator before dashboard viewing. Rejected because it adds an operational step. (see brainstorm)
2. **Hybrid lazy + cache:** Best of both but most complex. Over-engineered for current scale. (see brainstorm)
3. **Streaming/WebSocket updates:** Real-time updates as experiments complete. Out of scope for this overhaul — could be added later.

## System-Wide Impact

### Interaction Graph

- `selected-runs-store` change triggers re-render of the active tab (via `render_tab()` callback)
- `active-filters-store` change → Overview table re-filters → selection may change → cascading re-render
- `date-range-store` change → Overview re-queries `get_all_runs()` → table update → potential selection change
- URL sync callbacks fire on store changes; must prevent circular updates via `dash.callback_context.triggered`
- "Regenerate Analysis" button runs subprocess → refreshes data loader → re-renders failure analysis

### Error Propagation

- Data loader methods already wrap all I/O in try/except and return None/empty DataFrame on failure
- New timing instrumentation should not break existing error handling
- Subprocess call for CLI tool: capture stderr, show in toast notification on failure
- Filter widget: invalid regex in "contains" should be caught and shown as validation error, not crash the callback

### State Lifecycle Risks

- **URL ↔ Store circular updates:** Must use `dash.callback_context.triggered` to distinguish user navigation from programmatic updates. Without this, URL sync creates infinite callback loops.
- **Stale selection after refresh:** If selected run_ids no longer exist after data refresh, clear invalid IDs from `selected-runs-store`. Show info toast: "X selected runs no longer found."
- **Default selection timing:** The "last 10 runs" default must only apply when `selected-runs-store` is truly empty (first load), not when user explicitly cleared selection. Use a separate `selection-explicit` boolean store.

### API Surface Parity

- All tab render functions gain a `selected_run_ids` parameter — consistent interface
- All tabs gain options panel + diagnostic panel — consistent UX pattern
- `create_run_table()` signature changes: needs `selection_mode="multiple"` parameter (backward-compatible default)

### Integration Test Scenarios

1. **Selection round-trip:** Select 3 runs on Overview → switch to Metrics tab → verify only 3 runs in summary cards → switch back → verify selection preserved
2. **URL state restore:** Open dashboard with `?runs=abc,def&tab=metrics` → verify correct tab active, correct runs selected, metrics rendering for those runs
3. **Filter + selection interaction:** Apply filter "model contains llama" → select 2 visible runs → remove filter → verify selected runs remain selected even though table now shows all runs
4. **Regenerate analysis flow:** Click "Regenerate Analysis" → verify spinner appears → verify CLI tool runs → verify failure categories update from "Unknown" to named categories
5. **Metrics lazy loading:** Navigate to Metrics tab → verify summary cards appear fast → click "Show" on accuracy bars → verify plot loads → verify it respects selection

## Acceptance Criteria

### Functional Requirements

- [ ] Dashboard title shows "GEO-LLM Experiment Dashboard"
- [ ] Overview table: full-page width, page size 100, sorted by date/model/context, checkbox selection
- [ ] Date toggle works: "Last 5 days" (default) / "All runs"
- [ ] Multi-filter: can add/remove filters with AND logic on any column
- [ ] Run selection persists across tabs and in URL query params
- [ ] Default: last 10 runs selected when no explicit selection
- [ ] All tabs auto re-render when selection changes
- [ ] Failure Analysis shows named failure categories (not "Unknown") when analysis report is available
- [ ] "Regenerate Analysis" button works and refreshes failure data
- [ ] Metrics tab loads summary cards immediately, plots on-demand via gallery
- [ ] Trace Explorer: searchable run dropdown + in-trace text search
- [ ] Trace Explorer: raw trace JSON panel (prettified, collapsible)
- [ ] Every tab has options panel (top) and diagnostic panel (bottom)
- [ ] Comparison tab pre-filters to selected runs

### Non-Functional Requirements

- [ ] Initial page load <2s with 500 runs
- [ ] Tab switch <1s for tabs using only run metadata
- [ ] No tab causes browser hang or timeout (metrics tab fix)
- [ ] URL state is shareable and bookmarkable

### Quality Gates

- [ ] All existing callbacks still function (no regressions)
- [ ] Dashboard starts without Phoenix (graceful degradation preserved)
- [ ] Dashboard handles empty results directory (no crashes)
- [ ] Dashboard handles missing analysis report (shows "No output (undiagnosed)" not crash)

## Dependencies & Prerequisites

- **New package required:** `diskcache` — for background callback manager (`DiskcacheManager`). Install: `uv pip install diskcache`
- Dash 2.18.2 (installed) — supports `ctx.triggered_id`, `Patch()`, `allow_duplicate=True`, `dcc.Loading(target_components=...)`, `dcc.Clipboard`, background callbacks
- dash-ag-grid 31.2.0 (installed) — uses v31 `rowSelection` API (dict-based, not column-level)
- dash-bootstrap-components 1.6.0 (installed) — `dbc.Accordion`, `dbc.Toast` available
- `dcc.Location` available in dash >= 2.0 (already in use)
- `dcc.Clipboard` available in dash >= 2.0 (works on localhost/SSH tunnels)
- Analysis report must exist for failure categories to show (Regenerate button mitigates this)

## Risk Analysis & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| URL ↔ store circular callbacks | Dashboard freezes | Single bidirectional callback with `ctx.triggered_id` + `no_update`; tested pattern from research |
| AG Grid v31 API mismatch | Selection broken | Use `dashGridOptions.rowSelection: {mode: "multiRow"}` not deprecated column-level `checkboxSelection` |
| Browser history pollution from URL updates | Back button unusable | Debounce rapid filter/selection changes; or use `hash` for volatile state |
| Pattern-matching callbacks with many dynamic components | Slow front-end matching (Dash #3008) | Cap filter rows at 20; use 6 plot buttons (well within safe range) |
| Subprocess call for CLI tool hangs | UI blocked | Use `DiskcacheManager` background callbacks with `timeout=300`; `running` param disables button |
| `parse_qs` returns lists not strings | Silent bugs | Always index `[0]` on parsed values; documented in plan gotchas |
| Session storage vs URL conflict on page load | Wrong state restored | URL takes precedence; clear session stores when URL params present |

## Key Files to Modify

| File | Changes |
|------|---------|
| `src/dashboard/app.py` | Title rename, new stores, URL sync, selection propagation, lazy tab rendering, new callbacks for metrics gallery + trace search + regenerate analysis |
| `src/dashboard/data_loader.py` | Timing instrumentation, file tracking, lightweight startup (Tier 1/2 split), date filtering |
| `src/dashboard/tabs/overview.py` | Full-page table, date toggle, multi-filter, options panel, diagnostic panel, selection sync |
| `src/dashboard/tabs/metrics.py` | Complete rework: summary cards + plot gallery + deferred loading |
| `src/dashboard/tabs/failure_analysis.py` | Selection filter, regenerate button, options panel, diagnostic panel |
| `src/dashboard/tabs/error_analysis.py` | Header, selection filter, options panel, diagnostic panel |
| `src/dashboard/tabs/trace_explorer.py` | Searchable dropdown, in-trace search, raw JSON panel, options panel, diagnostic panel |
| `src/dashboard/tabs/token_cost.py` | Selection filter, options panel, diagnostic panel |
| `src/dashboard/tabs/comparison.py` | Pre-filtered dropdowns, options panel, diagnostic panel |
| `src/dashboard/components/run_table.py` | Multi-select, checkbox column, page size 100, default sort, new columns |
| `src/dashboard/components/diagnostic_panel.py` | **New file** — shared diagnostic panel component |
| `src/dashboard/components/options_panel.py` | **New file** — shared options panel component |
| `src/dashboard/components/multi_filter.py` | **New file** — stackable filter widget |
| `src/evaluation/visualization/failure_io.py` | Change "Unknown" to "No output (undiagnosed)" |

## Sources & References

### Origin

- **Brainstorm document:** [docs/brainstorms/2026-03-12-dashboard-improvements-brainstorm.md](docs/brainstorms/2026-03-12-dashboard-improvements-brainstorm.md) — Key decisions carried forward: lazy tab + deferred plots performance strategy, multi-filter with AND logic, URL query param state encoding, manual-only analysis regeneration, pre-filtered-but-overridable comparison tab.

### Internal References

- Data loader: `src/dashboard/data_loader.py` — `DashboardDataLoader` class
- Failure taxonomy: `code_development_tools_agents/monitoring_and_evaluation/types_of_log_and_trace_problems.yaml` (18 categories, 6 groups)
- Analysis CLI: `code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py` — `--json` output format
- Failure IO: `src/evaluation/visualization/failure_io.py:44` — `_primary_failure_reason()`
- Enrichment: `src/evaluation/visualization/enrich.py` — `infer_context()`, `infer_model_label()`
- Run table: `src/dashboard/components/run_table.py` — AG Grid columnDefs and dashGridOptions
- Current callback map: `src/dashboard/app.py` — 20+ callbacks (see research notes)

