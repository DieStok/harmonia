"""Activity Log tab — chronological view of all dashboard interactions."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import dash_ag_grid as dag
import dash_bootstrap_components as dbc
from dash import dcc, html


def _load_log_entries(log_dir: Path, days: int = 7) -> list[dict]:
    """Load JSON-lines log entries from the last N days.

    Reads both the active log file (dashboard.log) and rotated files
    (dashboard.log.YYYY-MM-DD) within the date window.
    """
    entries = []
    if not log_dir.is_dir():
        return entries

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    for log_file in sorted(log_dir.glob("dashboard.log*")):
        try:
            with open(log_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        # Filter by date
                        ts = entry.get("timestamp", "")
                        if ts:
                            entry_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            if entry_dt < cutoff:
                                continue
                        entries.append(entry)
                    except (json.JSONDecodeError, ValueError):
                        continue
        except OSError:
            continue

    # Sort by timestamp descending (most recent first)
    entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return entries


def render_activity_log(log_dir: Path) -> html.Div:
    """Render the Activity Log tab."""
    entries = _load_log_entries(log_dir)

    # Extract unique event types and sessions for filters
    event_types = sorted({e.get("event_type", "") for e in entries if e.get("event_type")})
    sessions = sorted({e.get("session_id", "") for e in entries if e.get("session_id")})

    # Format details column as string for display
    row_data = []
    for e in entries:
        details = e.get("details", {})
        details_str = json.dumps(details) if details else ""
        row_data.append({
            "timestamp": e.get("timestamp", ""),
            "session_id": e.get("session_id", ""),
            "event_type": e.get("event_type", ""),
            "details": details_str,
        })

    column_defs = [
        {
            "field": "timestamp",
            "headerName": "Timestamp",
            "sortable": True,
            "filter": True,
            "width": 240,
        },
        {
            "field": "session_id",
            "headerName": "Session",
            "sortable": True,
            "filter": True,
            "width": 120,
        },
        {
            "field": "event_type",
            "headerName": "Event Type",
            "sortable": True,
            "filter": True,
            "width": 200,
        },
        {
            "field": "details",
            "headerName": "Details",
            "sortable": False,
            "filter": True,
            "flex": 1,
        },
    ]

    components = [
        dbc.Row(
            [
                dbc.Col(
                    dbc.Button(
                        "Refresh",
                        id="refresh-activity-log",
                        color="primary",
                        size="sm",
                        className="me-2",
                    ),
                    width="auto",
                ),
                dbc.Col(
                    [
                        html.Label("Event Type:", className="me-2"),
                        dcc.Dropdown(
                            id="activity-event-filter",
                            options=[{"label": t, "value": t} for t in event_types],
                            multi=True,
                            placeholder="All event types",
                            style={"minWidth": "250px"},
                        ),
                    ],
                    width="auto",
                ),
                dbc.Col(
                    [
                        html.Label("Session:", className="me-2"),
                        dcc.Dropdown(
                            id="activity-session-filter",
                            options=[{"label": s, "value": s} for s in sessions],
                            multi=True,
                            placeholder="All sessions",
                            style={"minWidth": "200px"},
                        ),
                    ],
                    width="auto",
                ),
            ],
            className="mb-3 align-items-end",
        ),
    ]

    if not row_data:
        components.append(
            html.P(
                "No activity log entries found. Interactions will appear here "
                "after using the dashboard.",
                className="text-muted text-center my-5",
            )
        )
    else:
        components.append(
            html.Small(
                f"{len(row_data)} entries from the last 7 days",
                className="text-muted mb-2 d-block",
            )
        )
        components.append(
            dag.AgGrid(
                id="activity-log-table",
                rowData=row_data,
                columnDefs=column_defs,
                defaultColDef={
                    "resizable": True,
                    "sortable": True,
                },
                dashGridOptions={
                    "pagination": True,
                    "paginationPageSize": 50,
                    "animateRows": True,
                },
                style={"height": "600px"},
                className="ag-theme-alpine",
            )
        )

    return html.Div(components)
