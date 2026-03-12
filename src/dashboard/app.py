"""
Harmonia Experiment Dashboard — main Dash application.

Usage:
    cd harmonia_metadata_agent/analysis/dstoker/harmonia
    .venv/bin/python src/dashboard/app.py \\
        --phoenix-endpoint http://localhost:6006 \\
        --results-dir results/ \\
        --port 8050
"""

import argparse
import logging
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode

# Follow existing codebase pattern — do NOT add src/__init__.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dash
import dash_bootstrap_components as dbc
import diskcache
from dash import Dash, Input, Output, State, ctx, dcc, html, no_update

from dashboard.components.multi_filter import register_multi_filter_callbacks
from dashboard.data_loader import DashboardDataLoader
from dashboard.tabs.comparison import render_comparison
from dashboard.tabs.error_analysis import render_error_analysis
from dashboard.tabs.failure_analysis import render_failure_analysis
from dashboard.tabs.metrics import render_metrics
from dashboard.tabs.overview import render_overview
from dashboard.tabs.token_cost import render_token_cost
from dashboard.tabs.trace_explorer import render_trace_explorer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# App setup
# --------------------------------------------------------------------------- #

_cache = diskcache.Cache("./cache")
_background_callback_manager = dash.DiskcacheManager(_cache)

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.FLATLY],
    suppress_callback_exceptions=True,
    background_callback_manager=_background_callback_manager,
)

app.title = "GEO-LLM Experiment Dashboard"

app.layout = dbc.Container(
    [
        # Phoenix status banner (hidden when Phoenix is available)
        html.Div(id="phoenix-status-banner"),
        # Toast notification container
        dbc.Toast(
            id="notification-toast",
            is_open=False,
            duration=4000,
            dismissable=True,
            style={"position": "fixed", "top": 10, "right": 10, "zIndex": 1050},
        ),
        # Navbar
        dbc.NavbarSimple(
            brand="GEO-LLM Experiment Dashboard",
            color="primary",
            dark=True,
            className="mb-3",
        ),
        # Tabs
        dbc.Tabs(
            [
                dbc.Tab(label="Overview", tab_id="overview"),
                dbc.Tab(label="Metrics", tab_id="metrics"),
                dbc.Tab(label="Failure Analysis", tab_id="failure-analysis"),
                dbc.Tab(label="Error Analysis", tab_id="error-analysis"),
                dbc.Tab(label="Trace Explorer", tab_id="trace"),
                dbc.Tab(label="Tokens & Cost", tab_id="tokens"),
                dbc.Tab(label="Comparison", tab_id="comparison"),
            ],
            id="tabs",
            active_tab="overview",
        ),
        # Tab content
        html.Div(id="tab-content", className="mt-3"),
        # URL state sync
        dcc.Location(id="url", refresh=False),
        # New shared stores for selection-driven architecture
        dcc.Store(id="selected-runs-store", data=[], storage_type="session"),
        dcc.Store(id="active-filters-store", data=[], storage_type="session"),
        dcc.Store(id="date-range-store", data="last5d", storage_type="session"),
        dcc.Store(id="selection-explicit", data=False, storage_type="session"),
        # Legacy stores (still used by trace explorer and comparison)
        dcc.Store(id="selected-run-id", storage_type="session"),
        dcc.Store(id="turn-page", data=0, storage_type="session"),
        dcc.Store(id="comparison-run-a-store", storage_type="session"),
        dcc.Store(id="comparison-run-b-store", storage_type="session"),
    ],
    fluid=True,
)


# Register pattern-matching callbacks for multi-filter widget
register_multi_filter_callbacks(app, "overview-filter")

# --------------------------------------------------------------------------- #
# Callbacks
# --------------------------------------------------------------------------- #

# Global data_loader reference (set in main)
data_loader: DashboardDataLoader = None  # type: ignore


@app.callback(
    Output("phoenix-status-banner", "children"),
    Input("tabs", "active_tab"),
)
def update_phoenix_banner(_active_tab):
    """Show warning if Phoenix is unavailable."""
    if data_loader is None or data_loader.phoenix_available:
        return []
    return dbc.Alert(
        "Phoenix server not available. Showing local data only. "
        "Start Phoenix and refresh to enable span data.",
        color="warning",
        dismissable=True,
        className="mb-2",
    )


@app.callback(
    Output("url", "search"),
    Output("selected-runs-store", "data", allow_duplicate=True),
    Output("date-range-store", "data", allow_duplicate=True),
    Output("tabs", "active_tab", allow_duplicate=True),
    Input("url", "search"),
    Input("selected-runs-store", "data"),
    Input("date-range-store", "data"),
    Input("tabs", "active_tab"),
    prevent_initial_call="initial_duplicate",
)
def sync_url_state(url_search, selected_runs, date_range, active_tab):
    """Bidirectional URL ↔ store sync. Uses ctx.triggered_id to break cycles."""
    trigger = ctx.triggered_id
    if trigger == "url" or not ctx.triggered:
        # URL changed or initial load → parse params, push to stores
        params = parse_qs(url_search.lstrip("?")) if url_search else {}
        runs_val = params.get("runs", [""])[0].split(",") if params.get("runs") else no_update
        # Filter out empty strings from split
        if runs_val is not no_update:
            runs_val = [r for r in runs_val if r]
        return (
            no_update,
            runs_val,
            params.get("date", ["last5d"])[0],
            params.get("tab", ["overview"])[0],
        )
    else:
        # Store/tab changed → serialize to URL, don't touch stores
        params = {}
        if selected_runs:
            params["runs"] = ",".join(selected_runs)
        if date_range and date_range != "last5d":
            params["date"] = date_range
        if active_tab and active_tab != "overview":
            params["tab"] = active_tab
        return (
            f"?{urlencode(params)}" if params else "",
            no_update,
            no_update,
            no_update,
        )


@app.callback(
    Output("tab-content", "children"),
    Input("tabs", "active_tab"),
    Input("selected-run-id", "data"),
    Input("turn-page", "data"),
    Input("comparison-run-a-store", "data"),
    Input("comparison-run-b-store", "data"),
    Input("selected-runs-store", "data"),
)
def render_tab(active_tab, selected_run_id, turn_page, comp_a, comp_b, selected_runs):
    """Render the content for the selected tab."""
    if data_loader is None:
        return html.P("Loading...")

    selected_run_ids = selected_runs if selected_runs else []

    if active_tab == "overview":
        return render_overview(data_loader, selected_run_ids)
    elif active_tab == "metrics":
        return render_metrics(data_loader, selected_run_ids)
    elif active_tab == "failure-analysis":
        return render_failure_analysis(data_loader, selected_run_ids)
    elif active_tab == "error-analysis":
        return render_error_analysis(data_loader, selected_run_ids)
    elif active_tab == "trace":
        return render_trace_explorer(data_loader, selected_run_id, turn_page or 0)
    elif active_tab == "tokens":
        return render_token_cost(data_loader, selected_run_ids)
    elif active_tab == "comparison":
        return render_comparison(data_loader, comp_a, comp_b, selected_run_ids)
    return html.P("Select a tab.")


# Click-through: accuracy bar chart → trace explorer
@app.callback(
    Output("tabs", "active_tab", allow_duplicate=True),
    Output("selected-run-id", "data", allow_duplicate=True),
    Input("accuracy-bar-chart", "clickData"),
    prevent_initial_call=True,
)
def click_bar_to_trace(click_data):
    if click_data and click_data.get("points"):
        point = click_data["points"][0]
        run_id = point.get("customdata")
        if isinstance(run_id, list):
            run_id = run_id[0]
        if run_id:
            return "trace", run_id
    raise dash.exceptions.PreventUpdate


# Runs table selection → selected-runs-store sync
@app.callback(
    Output("selected-runs-store", "data", allow_duplicate=True),
    Output("selection-explicit", "data", allow_duplicate=True),
    Input("runs-table", "selectedRows"),
    prevent_initial_call=True,
)
def sync_table_selection_to_store(selected_rows):
    if selected_rows is not None:
        run_ids = [r.get("run_id") for r in selected_rows if r.get("run_id")]
        return run_ids, True
    raise dash.exceptions.PreventUpdate


# Clear selection button
@app.callback(
    Output("runs-table", "selectedRows"),
    Output("selected-runs-store", "data", allow_duplicate=True),
    Output("selection-explicit", "data", allow_duplicate=True),
    Input("clear-selection", "n_clicks"),
    prevent_initial_call=True,
)
def clear_selection(n_clicks):
    if n_clicks:
        return [], [], True
    raise dash.exceptions.PreventUpdate


# Date range toggle → re-render overview with filtered data
@app.callback(
    Output("date-range-store", "data", allow_duplicate=True),
    Input("date-range-toggle", "value"),
    prevent_initial_call=True,
)
def update_date_range(value):
    return value if value else "last5d"


# Trace explorer run selector
@app.callback(
    Output("selected-run-id", "data", allow_duplicate=True),
    Input("trace-run-selector", "value"),
    prevent_initial_call=True,
)
def select_trace_run(value):
    if value:
        return value
    raise dash.exceptions.PreventUpdate


# Comparison run selectors
@app.callback(
    Output("comparison-run-a-store", "data"),
    Input("comparison-run-a", "value"),
    prevent_initial_call=True,
)
def select_comp_a(value):
    return value


@app.callback(
    Output("comparison-run-b-store", "data"),
    Input("comparison-run-b", "value"),
    prevent_initial_call=True,
)
def select_comp_b(value):
    return value


# Synchronized scroll in comparison tab
@app.callback(
    Output("run-b-accordion", "active_item"),
    Input("run-a-accordion", "active_item"),
    prevent_initial_call=True,
)
def sync_accordions(active_item):
    return active_item


# Refresh buttons — all call data_loader.refresh() then re-render
@app.callback(
    Output("tab-content", "children", allow_duplicate=True),
    Input("refresh-overview", "n_clicks"),
    State("tabs", "active_tab"),
    prevent_initial_call=True,
)
def refresh_overview(n_clicks, active_tab):
    if n_clicks:
        data_loader.refresh()
    return render_overview(data_loader)


@app.callback(
    Output("tab-content", "children", allow_duplicate=True),
    Input("refresh-metrics", "n_clicks"),
    State("tabs", "active_tab"),
    prevent_initial_call=True,
)
def refresh_metrics(n_clicks, active_tab):
    if n_clicks:
        data_loader.refresh()
    return render_metrics(data_loader)


@app.callback(
    Output("tab-content", "children", allow_duplicate=True),
    Input("refresh-trace", "n_clicks"),
    State("tabs", "active_tab"),
    State("selected-run-id", "data"),
    State("turn-page", "data"),
    prevent_initial_call=True,
)
def refresh_trace(n_clicks, active_tab, run_id, turn_page):
    if n_clicks:
        data_loader.refresh()
    return render_trace_explorer(data_loader, run_id, turn_page or 0)


@app.callback(
    Output("tab-content", "children", allow_duplicate=True),
    Input("refresh-tokens", "n_clicks"),
    State("tabs", "active_tab"),
    prevent_initial_call=True,
)
def refresh_tokens(n_clicks, active_tab):
    if n_clicks:
        data_loader.refresh()
    return render_token_cost(data_loader)


@app.callback(
    Output("tab-content", "children", allow_duplicate=True),
    Input("refresh-comparison", "n_clicks"),
    State("tabs", "active_tab"),
    State("comparison-run-a-store", "data"),
    State("comparison-run-b-store", "data"),
    prevent_initial_call=True,
)
def refresh_comparison(n_clicks, active_tab, comp_a, comp_b):
    if n_clicks:
        data_loader.refresh()
    return render_comparison(data_loader, comp_a, comp_b)


# Background callback: regenerate analysis report
@dash.callback(
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
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    try:
        result = subprocess.run(
            [
                ".venv/bin/python",
                "code_development_tools_agents/monitoring_and_evaluation/"
                "read_and_analyze_logs_and_traces_cli.py",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            data_loader.refresh()
            return html.Div("Analysis report regenerated successfully.", className="text-success mt-2")
        else:
            return html.Div(
                f"Error: {result.stderr[:500]}", className="text-danger mt-2",
            )
    except subprocess.TimeoutExpired:
        return html.Div("Timed out after 5 minutes.", className="text-danger mt-2")
    except Exception as e:
        return html.Div(f"Error: {e}", className="text-danger mt-2")


# Radar chart update on run selection change
@app.callback(
    Output("radar-chart", "figure"),
    Input("radar-run-selector", "value"),
    prevent_initial_call=True,
)
def update_radar(selected_runs):
    from dashboard.tabs.metrics import _radar_chart

    return _radar_chart(data_loader, selected_runs or [])


# Boxplot grouping update
@app.callback(
    Output("metrics-boxplot", "figure"),
    Input("boxplot-group-selector", "value"),
    prevent_initial_call=True,
)
def update_boxplot(group_by):
    from dashboard.tabs.metrics import _metrics_boxplot

    metrics_df = data_loader.get_all_metrics()
    return _metrics_boxplot(metrics_df, group_by or "model_family")


# Confusion matrix column selector (trace explorer)
@app.callback(
    Output("confusion-matrix-chart", "figure"),
    Input("confusion-column-selector", "value"),
    State("selected-run-id", "data"),
    prevent_initial_call=True,
)
def update_confusion_matrix(column_name, run_id):
    if not run_id or not column_name:
        raise dash.exceptions.PreventUpdate
    from dashboard.tabs.trace_explorer import _confusion_matrix_chart

    metrics = data_loader.get_run_metrics(run_id)
    if not metrics:
        raise dash.exceptions.PreventUpdate
    cm = metrics.get("column_values", {}).get(column_name, {}).get("confusion_matrix", {})
    return _confusion_matrix_chart(cm, column_name)


# Cross-model comparison column selector
@app.callback(
    Output("cross-model-heatmap", "figure"),
    Input("cross-model-column-selector", "value"),
    State("comparison-run-a-store", "data"),
    State("comparison-run-b-store", "data"),
    prevent_initial_call=True,
)
def update_cross_model_heatmap(column_name, run_id_a, run_id_b):
    if not run_id_a or not run_id_b or not column_name:
        raise dash.exceptions.PreventUpdate
    from dashboard.tabs.comparison import _cross_model_heatmap

    return _cross_model_heatmap(data_loader, run_id_a, run_id_b, column_name)


# Refresh buttons for new tabs
@app.callback(
    Output("tab-content", "children", allow_duplicate=True),
    Input("refresh-failure-analysis", "n_clicks"),
    prevent_initial_call=True,
)
def refresh_failure_analysis(n_clicks):
    if n_clicks:
        data_loader.refresh()
    return render_failure_analysis(data_loader)


@app.callback(
    Output("tab-content", "children", allow_duplicate=True),
    Input("refresh-error-analysis", "n_clicks"),
    prevent_initial_call=True,
)
def refresh_error_analysis(n_clicks):
    if n_clicks:
        data_loader.refresh()
    return render_error_analysis(data_loader)


# Click-through: failure heatmap → trace explorer (for successful runs)
@app.callback(
    Output("tabs", "active_tab", allow_duplicate=True),
    Output("selected-run-id", "data", allow_duplicate=True),
    Input("success-failure-heatmap", "clickData"),
    prevent_initial_call=True,
)
def click_heatmap_to_trace(click_data):
    if click_data and click_data.get("points"):
        point = click_data["points"][0]
        text = point.get("text", "")
        if text == "OK":
            # Extract run_id from hovertext
            hover = point.get("hovertext", "")
            if "Run ID:" in hover:
                run_id = hover.split("Run ID:")[1].strip().split("<")[0].strip()
                if run_id and run_id != "N/A":
                    return "trace", run_id
    raise dash.exceptions.PreventUpdate


# --------------------------------------------------------------------------- #
# CLI entry point
# --------------------------------------------------------------------------- #


def check_port_available(port: int) -> bool:
    """Check if a port is available for binding."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("0.0.0.0", port))
            return True
    except OSError:
        return False


def main():
    global data_loader

    parser = argparse.ArgumentParser(description="Harmonia Experiment Dashboard")
    parser.add_argument(
        "--phoenix-endpoint",
        default="http://localhost:6006",
        help="Phoenix server endpoint (default: http://localhost:6006)",
    )
    parser.add_argument(
        "--results-dir",
        default="results/",
        help="Path to results directory (default: results/)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8050,
        help="Port to serve dashboard on (default: 8050)",
    )
    args = parser.parse_args()

    results_path = Path(args.results_dir).resolve()
    if not results_path.is_dir():
        logger.error(f"Results directory not found: {results_path}")
        sys.exit(1)

    # Port check
    if not check_port_available(args.port):
        logger.error(
            f"Port {args.port} is already in use. Use --port <number> to specify a different port."
        )
        sys.exit(1)

    logger.info(
        f"Initializing data loader: results={results_path}, phoenix={args.phoenix_endpoint}"
    )
    data_loader = DashboardDataLoader(
        phoenix_endpoint=args.phoenix_endpoint,
        results_base_dir=results_path,
    )

    run_count = len(data_loader.get_all_runs())
    logger.info(f"Found {run_count} experiment runs")
    if data_loader.phoenix_available:
        logger.info("Phoenix connection: OK")
    else:
        logger.warning("Phoenix connection: UNAVAILABLE (local data only)")

    logger.info(f"Starting dashboard on http://0.0.0.0:{args.port}")
    logger.info(f"Access via: ssh -L {args.port}:localhost:{args.port} <this-host>")

    app.run(host="0.0.0.0", port=args.port, debug=False)


if __name__ == "__main__":
    main()
