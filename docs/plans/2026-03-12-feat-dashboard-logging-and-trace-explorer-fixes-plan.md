---
title: Dashboard Comprehensive Logging + Trace Explorer Fixes
type: feat
status: completed
date: 2026-03-12
---

# Dashboard Comprehensive Logging + Trace Explorer Fixes

## Overview

Three related improvements to the Harmonia dashboard:

1. **Comprehensive interaction logging** — Log all user interactions (tab switches, run selections, chart clicks, filter changes, refresh actions) to daily-rotating files in `logs/dashboard/`.
2. **Activity Log tab** — New dashboard tab showing a chronological, filterable table of all recorded interactions across sessions.
3. **Trace Explorer fixes** — Remove content truncation so full LLM outputs/code are visible, and display the `tool_calls` field that exists in trace data but is never rendered.

## Problem Statement / Motivation

**Logging:** The dashboard currently has zero interaction tracking. All logging goes to console/SLURM stdout at INFO level — startup, Phoenix connection, and data loading errors only. There is no way to know which runs were reviewed, how the dashboard is being used, or to audit past sessions.

**Trace truncation:** `turn_accordion.py` hard-truncates content at multiple points:
- User messages: 2000 chars ([turn_accordion.py:55](src/dashboard/components/turn_accordion.py#L55))
- Agent responses: 3000 chars ([turn_accordion.py:70](src/dashboard/components/turn_accordion.py#L70), [turn_accordion.py:74](src/dashboard/components/turn_accordion.py#L74))
- Code execution code: 1000 chars ([turn_accordion.py:92](src/dashboard/components/turn_accordion.py#L92))
- Code execution stdout: 500 chars ([turn_accordion.py:96](src/dashboard/components/turn_accordion.py#L96))
- Code execution stderr: 500 chars ([turn_accordion.py:106](src/dashboard/components/turn_accordion.py#L106))
- Internal execution code: 500 chars ([turn_accordion.py:125](src/dashboard/components/turn_accordion.py#L125))
- Max 5 code executions shown per turn ([turn_accordion.py:89](src/dashboard/components/turn_accordion.py#L89))

This prevents viewing the full code an LLM produced, which is critical for understanding agent behavior.

**Missing tool calls:** The `tool_calls` field exists on `TurnRecord` ([logger.py:19](src/automation/logger.py#L19)) and is populated by both `client.py` and `manual_runner.py` with `{"thought": ...}` dicts when ReAct-style "Action:" patterns are detected. However, `_build_turn_item()` in `turn_accordion.py` never reads or renders this field — it's silently dropped.

## Proposed Solution

### Part 1: Interaction Logging Infrastructure

Create a dedicated `DashboardActivityLogger` that writes structured JSON-lines logs to `logs/dashboard/dashboard_YYYY-MM-DD.log` with daily rotation.

**Key design decisions:**
- **JSON-lines format** (one JSON object per line) — machine-readable, greppable, loadable by the Activity Log tab
- **Daily rotation** via `TimedRotatingFileHandler` — one file per day, easy to find sessions
- **Non-blocking** — logging must not slow down callbacks; use Python's built-in logging (already async-safe)
- **Structured events** — each log entry has: `timestamp`, `event_type`, `details` (dict), `session_id`

#### Event Types to Log

| Event Type | Trigger Callback | Details Logged |
|------------|-----------------|----------------|
| `tab_switch` | `render_tab` | `tab_id` |
| `run_select` | `sync_table_selection_to_store` | `run_ids` (list) |
| `run_clear` | `clear_selection` | — |
| `trace_run_select` | `select_trace_run` | `run_id` |
| `comparison_select` | `select_comp_a` / `select_comp_b` | `slot` (a/b), `run_id` |
| `date_range_change` | `update_date_range` | `range` |
| `chart_click_accuracy` | `click_bar_to_trace` | `run_id` |
| `chart_click_heatmap` | `click_heatmap_to_trace` | `run_id`, `status` |
| `radar_update` | `update_radar` | `selected_runs` |
| `boxplot_update` | `update_boxplot` | `group_by` |
| `confusion_column` | `update_confusion_matrix` | `column`, `run_id` |
| `cross_model_column` | `update_cross_model_heatmap` | `column` |
| `refresh` | `refresh_*` (6 callbacks) | `tab_id` |
| `regenerate_analysis` | `regenerate_analysis` | — |
| `accordion_sync` | `sync_accordions` | `active_item` |
| `url_navigation` | `sync_url_state` | `url_params` |

#### New File: `src/dashboard/activity_logger.py`

```python
"""
Dashboard activity logger — writes structured JSON-lines to logs/dashboard/.

Usage:
    from dashboard.activity_logger import activity_logger
    activity_logger.log("tab_switch", {"tab_id": "metrics"})
"""

import json
import logging
import uuid
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


class DashboardActivityLogger:
    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = uuid.uuid4().hex[:8]

        self._logger = logging.getLogger("harmonia.dashboard.activity")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False  # Don't duplicate to root logger

        # Active file: dashboard.log; rotated files: dashboard.log.2026-03-12 etc.
        handler = TimedRotatingFileHandler(
            filename=self.log_dir / "dashboard.log",
            when="midnight",
            backupCount=90,  # Keep 90 days
            utc=True,
        )
        handler.suffix = "%Y-%m-%d"
        handler.setFormatter(logging.Formatter("%(message)s"))  # Raw JSON
        self._logger.addHandler(handler)

    def log(self, event_type: str, details: dict | None = None):
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "session_id": self.session_id,
            "event_type": event_type,
            "details": details or {},
        }
        self._logger.info(json.dumps(entry, default=str))
```

#### Integration Pattern

Add a single `activity_logger.log(...)` call at the top of each existing callback in `app.py`. No structural changes to callbacks — just one line added per function.

**Important:** `render_tab` has 6 Inputs (`active_tab`, `selected-run-id`, `turn-page`, `comparison-run-a-store`, `comparison-run-b-store`, `selected-runs-store`). Any of them changing fires the callback. Use `ctx.triggered_id` to only log `tab_switch` when `active_tab` actually triggered it — otherwise every run selection or page change will produce a false `tab_switch` event.

Example for `render_tab`:
```python
def render_tab(active_tab, selected_run_id, turn_page, comp_a, comp_b, selected_runs):
    if ctx.triggered_id == "tabs":
        activity_logger.log("tab_switch", {"tab_id": active_tab})
    # ... existing code unchanged ...
```

### Part 2: Activity Log Tab

New tab added to the dashboard (8th tab) showing a chronological table of all interactions.

#### New File: `src/dashboard/tabs/activity_log.py`

**Components:**

| Component | Type | Details |
|-----------|------|---------|
| Activity table | AG Grid | Columns: timestamp, session_id, event_type, details. Sortable, filterable. |
| Event type filter | Dropdown | Multi-select filter for event types |
| Date range picker | DatePickerRange | Filter by date range (maps to which log files to load) |
| Session filter | Dropdown | Filter by session_id |
| Refresh button | Button | Reload log files |

**Data loading:**
- Read `logs/dashboard/dashboard*.log` files (JSON-lines)
- Parse each line as JSON
- Filter by selected date range / event type / session
- Return as list of dicts for AG Grid

```python
def render_activity_log(log_dir: Path) -> html.Div:
    """Render the Activity Log tab."""
    # Load all .log files from log_dir
    # Parse JSON-lines
    # Build AG Grid table with filters
```

**Performance consideration:** Only load the last 7 days of logs by default. User can expand via date picker. Each day's log file is small (a few hundred lines at most).

#### Registration in `app.py`

Add the tab to the existing `dbc.Tabs` list:
```python
dbc.Tab(label="Activity Log", tab_id="activity-log"),
```

Add routing in `render_tab`:
```python
elif active_tab == "activity-log":
    return render_activity_log(activity_logger.log_dir)
```

### Part 3: Trace Explorer — Remove Content Truncation

#### File: `src/dashboard/components/turn_accordion.py`

**Changes to `_build_turn_item()`:**

1. **Remove all character limits** — replace `user_msg[:2000]`, `agent_resp[:3000]`, `ce["code"][:1000]`, etc. with full content
2. **Remove the "..." truncation indicators**
3. **Remove the 5-execution limit** on `agent_execs[:5]` and `internal_execs[:5]`
4. **Wrap long content in scrollable containers** — use `style={"maxHeight": "600px", "overflowY": "auto"}` so the accordion items don't become infinitely tall, but ALL content is accessible via scroll

**Specific line changes:**

| Line | Current | New |
|------|---------|-----|
| 55 | `user_msg[:2000] + ("..." if len(user_msg) > 2000 else "")` | `user_msg` (full content, scrollable wrapper) |
| 70 | `agent_resp[:3000]` | `agent_resp` (full content) |
| 74 | `agent_resp[:3000] + ("..." if len(agent_resp) > 3000 else "")` | `agent_resp` (full content, scrollable wrapper) |
| 89 | `agent_execs[:5]` | `agent_execs` (all executions) |
| 92 | `ce["code"][:1000]` | `ce["code"]` (full code) |
| 96 | `ce["stdout"][:500]` | `ce["stdout"]` (full output, scrollable) |
| 106 | `ce["stderr"][:500]` | `ce["stderr"]` (full output, scrollable) |
| 121 | `internal_execs[:5]` | `internal_execs` (all executions) |
| 125 | `ce["code"][:500]` | `ce["code"]` (full code) |

**Scrollable wrapper pattern:**
```python
html.Div(
    dcc.Markdown(user_msg),
    style={
        "backgroundColor": "#e3f2fd",
        "padding": "10px",
        "borderRadius": "4px",
        "marginBottom": "10px",
        "maxHeight": "600px",
        "overflowY": "auto",
    },
)
```

### Part 4: Trace Explorer — Display Tool Calls

#### File: `src/dashboard/components/turn_accordion.py`

Add a new section in `_build_turn_item()` after the agent response block, before code executions:

```python
# Tool calls (ReAct thought/action patterns)
tool_calls = turn.get("tool_calls", [])
if tool_calls:
    children.append(html.H6(f"Tool Calls ({len(tool_calls)})", className="text-muted mt-2"))
    for j, tc in enumerate(tool_calls):
        thought = tc.get("thought", "")
        if thought:
            children.append(
                html.Div(
                    dcc.Markdown(thought),
                    style={
                        "backgroundColor": "#f3e5f5",  # Light purple for tool calls
                        "padding": "10px",
                        "borderRadius": "4px",
                        "marginBottom": "6px",
                        "maxHeight": "400px",
                        "overflowY": "auto",
                    },
                )
            )
```

**Placement:** Between the "Agent Response" section and the "Code Executions" section (around line 83 in current code).

## Technical Considerations

**Thread safety:** Python's `logging` module is thread-safe by design. The `DashboardActivityLogger` uses a dedicated logger name (`harmonia.dashboard.activity`) with `propagate=False` to avoid interfering with the existing root logger setup.

**Log directory:** `logs/dashboard/` follows the existing `logs/` convention. Since `logs/` is already gitignored, `logs/dashboard/` will also be gitignored automatically.

**Performance:** JSON-lines logging adds ~0.1ms per callback invocation (negligible). Loading 7 days of logs for the Activity Log tab should be <100ms for typical usage.

**No behavior changes:** All existing callbacks retain their exact Input/Output/State signatures. The only addition is a `activity_logger.log()` call at the start of each callback body.

## Acceptance Criteria

- [x] `logs/dashboard/` directory created on dashboard startup
- [x] All 24 callbacks in `app.py` emit structured JSON-lines log entries
- [x] Log files rotate daily with `dashboard_YYYY-MM-DD.log` naming
- [x] New "Activity Log" tab visible in dashboard navigation
- [x] Activity Log tab shows chronological table of all interactions
- [x] Activity Log tab supports filtering by event type, date range, and session
- [x] Turn accordion shows full content without truncation (user messages, agent responses, code, stdout, stderr)
- [x] Turn accordion wraps long content in scrollable containers (max-height 600px)
- [x] All code executions shown per turn (no 5-execution limit)
- [x] Tool calls from `trace.json` displayed in turn accordion with purple background
- [x] Existing dashboard functionality unchanged (no regressions)

## File Change Summary

### New Files

| File | Purpose |
|------|---------|
| `src/dashboard/activity_logger.py` | `DashboardActivityLogger` class — JSON-lines logging with daily rotation |
| `src/dashboard/tabs/activity_log.py` | Activity Log tab — renders chronological interaction table with filters |

### Modified Files

| File | Changes |
|------|---------|
| `src/dashboard/app.py` | Import `activity_logger`; add `activity_logger.log()` to all 24 callbacks; add "Activity Log" tab to layout; add routing in `render_tab` |
| `src/dashboard/components/turn_accordion.py` | Remove all content truncation limits; add scrollable wrappers; remove execution count limits; add tool_calls rendering section |

## Sources & References

### Internal References

- Existing callback structure: [app.py:120-517](src/dashboard/app.py#L120-L517)
- Turn accordion truncation: [turn_accordion.py:55-125](src/dashboard/components/turn_accordion.py#L55-L125)
- Tool calls field definition: [logger.py:19](src/automation/logger.py#L19)
- Tool calls population (automated): [client.py:261-319](src/automation/client.py#L261-L319)
- Tool calls population (manual): [manual_runner.py:282-295](src/automation/manual_runner.py#L282-L295)
- Existing timing infrastructure (unused): [data_loader.py:159-186](src/dashboard/data_loader.py#L159-L186)
- Dashboard plan: [09_03_2026_1201_create_plotly_plots_phoenix_traces_dashboard.md](docs/plans/09_03_2026_1201_create_plotly_plots_phoenix_traces_dashboard.md)
