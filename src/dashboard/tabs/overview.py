"""Experiment Overview tab — entry point showing all runs with selection-driven architecture."""

import re

import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import dcc, html

from dashboard.components.diagnostic_panel import create_diagnostic_panel
from dashboard.components.multi_filter import create_multi_filter
from dashboard.components.options_panel import create_options_panel
from dashboard.components.run_table import create_run_table


def _summary_card(title: str, value: str, color: str = "primary") -> dbc.Col:
    """Create a summary statistic card."""
    return dbc.Col(
        dbc.Card(
            [
                dbc.CardBody(
                    [
                        html.H6(title, className="text-muted mb-1"),
                        html.H4(value, className="mb-0"),
                    ]
                ),
            ],
            color=color,
            outline=True,
        ),
        width=True,
    )


def create_status_pie(runs_df) -> go.Figure:
    """Create a pie chart of run status distribution."""
    if runs_df is None or len(runs_df) == 0:
        fig = go.Figure()
        fig.update_layout(template="plotly_white", title="Status Distribution", height=300)
        return fig

    status_counts = runs_df["status"].value_counts()

    color_map = {
        "completed": "#28a745",
        "failed": "#dc3545",
        "timeout": "#ffc107",
        "running": "#17a2b8",
        "cancelled": "#6c757d",
        "unknown": "#adb5bd",
    }

    fig = go.Figure(
        data=[
            go.Pie(
                labels=status_counts.index.tolist(),
                values=status_counts.values.tolist(),
                marker_colors=[color_map.get(s, "#adb5bd") for s in status_counts.index],
                hole=0.4,
                textinfo="label+value",
            )
        ]
    )

    fig.update_layout(
        template="plotly_white",
        title="Status Distribution",
        height=300,
        margin=dict(t=40, b=20, l=20, r=20),
    )

    return fig


def _apply_filters(runs_df, filters: list[dict]):
    """Apply multi-filter conditions (AND logic) to the DataFrame."""
    df = runs_df.copy()
    for f in filters:
        col = f.get("column", "")
        op = f.get("operator", "contains")
        val = f.get("value", "")
        if not col or not val or col not in df.columns:
            continue
        col_str = df[col].astype(str)
        try:
            if op == "contains":
                mask = col_str.str.contains(val, case=False, na=False, regex=True)
                df = df[mask]
            elif op == "not_contains":
                mask = col_str.str.contains(val, case=False, na=False, regex=True)
                df = df[~mask]
            elif op == "equals":
                df = df[col_str.str.lower() == val.lower()]
            elif op == "not_equals":
                df = df[col_str.str.lower() != val.lower()]
        except re.error:
            # Invalid regex — skip this filter silently
            pass
    return df


def render_overview(data_loader, selected_run_ids: list[str] | None = None) -> html.Div:
    """Render the Experiment Overview tab."""
    runs_df = data_loader.get_all_runs()

    if runs_df is None or len(runs_df) == 0:
        return html.Div(
            [
                dbc.Button(
                    "Refresh Data",
                    id="refresh-overview",
                    color="primary",
                    size="sm",
                    className="mb-3",
                ),
                html.Div(
                    html.P(
                        "No experiment runs found. Run experiments first, then refresh.",
                        className="text-muted",
                    ),
                    className="text-center my-5",
                ),
            ]
        )

    # Summary statistics
    total_runs = len(runs_df)
    completed = len(runs_df[runs_df["status"] == "completed"]) if "status" in runs_df.columns else 0
    success_rate = f"{completed / total_runs * 100:.0f}%" if total_runs > 0 else "N/A"

    avg_accuracy = runs_df["accuracy"].dropna().mean() if "accuracy" in runs_df.columns else None
    avg_accuracy_str = f"{avg_accuracy * 100:.1f}%" if avg_accuracy is not None else "N/A"

    total_cost = runs_df["total_cost_usd"].sum() if "total_cost_usd" in runs_df.columns else 0
    total_tokens = (
        (runs_df["total_input_tokens"].sum() + runs_df["total_output_tokens"].sum())
        if "total_input_tokens" in runs_df.columns
        else 0
    )

    # Build row data for AG Grid
    row_data = runs_df.to_dict("records")

    # Filterable columns for multi-filter widget
    filter_columns = [
        "run_id", "experiment_name", "model", "context", "provider", "status",
    ]

    # Options panel content
    options_content = [
        # Date range toggle
        html.Label("Date Range:", className="fw-bold mb-1"),
        dbc.RadioItems(
            id="date-range-toggle",
            options=[
                {"label": "Last 5 days", "value": "last5d"},
                {"label": "All runs", "value": "all"},
            ],
            value="last5d",
            inline=True,
            className="mb-3",
        ),
        html.Hr(),
        # Multi-filter
        html.Label("Filters:", className="fw-bold mb-1"),
        create_multi_filter("overview-filter", filter_columns),
        html.Hr(),
        # Selection controls
        html.Label("Selection:", className="fw-bold mb-1"),
        html.Div([
            dbc.Button(
                "Select All Visible",
                id="select-all-visible",
                color="secondary",
                outline=True,
                size="sm",
                className="me-2",
            ),
            dbc.Button(
                "Clear Selection",
                id="clear-selection",
                color="secondary",
                outline=True,
                size="sm",
            ),
        ], className="mb-2"),
    ]

    # Diagnostic panel
    timing_info = data_loader.get_timing_info()
    diag = create_diagnostic_panel(
        "overview-diagnostic",
        source_files=[str(data_loader.results_dir)],
        timing=timing_info.get("timing"),
        cache_info=timing_info.get("cache"),
    )

    return html.Div(
        [
            # Top bar: refresh + selection info
            dbc.Row([
                dbc.Col(
                    dbc.Button(
                        "Refresh Data", id="refresh-overview", color="primary", size="sm",
                    ),
                    width="auto",
                ),
                dbc.Col(
                    html.Div(id="selection-info-banner"),
                    width=True,
                ),
            ], className="mb-3 align-items-center"),
            # Summary cards
            dbc.Row(
                [
                    _summary_card("Total Runs", str(total_runs)),
                    _summary_card("Success Rate", success_rate),
                    _summary_card("Avg Accuracy", avg_accuracy_str),
                    _summary_card("Total Cost", f"${total_cost:.2f}"),
                    _summary_card("Total Tokens", f"{total_tokens:,}"),
                ],
                className="mb-3",
            ),
            # Options panel
            create_options_panel("overview-options", "Options & Filters", options_content),
            # Full-width table
            html.H5("Experiment Runs"),
            create_run_table(row_data),
            # Status pie (below table, less prominent)
            dbc.Row([
                dbc.Col(
                    dcc.Graph(
                        id="status-pie",
                        figure=create_status_pie(runs_df),
                    ),
                    width=4,
                ),
            ], className="mt-3"),
            # Diagnostic panel
            diag,
        ]
    )
