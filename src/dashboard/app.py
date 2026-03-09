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
import sys
from pathlib import Path

# Follow existing codebase pattern — do NOT add src/__init__.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dash
import dash_bootstrap_components as dbc
from dash import Dash, Input, Output, State, dcc, html

from dashboard.data_loader import DashboardDataLoader
from dashboard.tabs.comparison import render_comparison
from dashboard.tabs.metrics import render_metrics
from dashboard.tabs.overview import render_overview
from dashboard.tabs.token_cost import render_token_cost
from dashboard.tabs.trace_explorer import render_trace_explorer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# App setup
# --------------------------------------------------------------------------- #

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.FLATLY],
    suppress_callback_exceptions=True,
)

app.layout = dbc.Container([
    # Phoenix status banner (hidden when Phoenix is available)
    html.Div(id="phoenix-status-banner"),

    # Navbar
    dbc.NavbarSimple(
        brand="Harmonia Experiment Dashboard",
        color="primary",
        dark=True,
        className="mb-3",
    ),

    # Tabs
    dbc.Tabs([
        dbc.Tab(label="Overview", tab_id="overview"),
        dbc.Tab(label="Metrics", tab_id="metrics"),
        dbc.Tab(label="Trace Explorer", tab_id="trace"),
        dbc.Tab(label="Tokens & Cost", tab_id="tokens"),
        dbc.Tab(label="Comparison", tab_id="comparison"),
    ], id="tabs", active_tab="overview"),

    # Tab content
    html.Div(id="tab-content", className="mt-3"),

    # Hidden stores for cross-tab state
    dcc.Store(id="selected-run-id", storage_type="session"),
    dcc.Store(id="turn-page", data=0, storage_type="session"),
    dcc.Store(id="comparison-run-a-store", storage_type="session"),
    dcc.Store(id="comparison-run-b-store", storage_type="session"),
], fluid=True)


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
    Output("tab-content", "children"),
    Input("tabs", "active_tab"),
    Input("selected-run-id", "data"),
    Input("turn-page", "data"),
    Input("comparison-run-a-store", "data"),
    Input("comparison-run-b-store", "data"),
)
def render_tab(active_tab, selected_run_id, turn_page, comp_a, comp_b):
    """Render the content for the selected tab."""
    if data_loader is None:
        return html.P("Loading...")

    if active_tab == "overview":
        return render_overview(data_loader)
    elif active_tab == "metrics":
        return render_metrics(data_loader)
    elif active_tab == "trace":
        return render_trace_explorer(data_loader, selected_run_id, turn_page or 0)
    elif active_tab == "tokens":
        return render_token_cost(data_loader)
    elif active_tab == "comparison":
        return render_comparison(data_loader, comp_a, comp_b)
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


# Click-through: runs table row → trace explorer
@app.callback(
    Output("tabs", "active_tab", allow_duplicate=True),
    Output("selected-run-id", "data", allow_duplicate=True),
    Input("runs-table", "selectedRows"),
    prevent_initial_call=True,
)
def click_row_to_trace(selected_rows):
    if selected_rows and len(selected_rows) > 0:
        run_id = selected_rows[0].get("run_id")
        if run_id:
            return "trace", run_id
    raise dash.exceptions.PreventUpdate


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


# Radar chart update on run selection change
@app.callback(
    Output("radar-chart", "figure"),
    Input("radar-run-selector", "value"),
    prevent_initial_call=True,
)
def update_radar(selected_runs):
    from dashboard.tabs.metrics import _radar_chart
    return _radar_chart(data_loader, selected_runs or [])


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
        "--phoenix-endpoint", default="http://localhost:6006",
        help="Phoenix server endpoint (default: http://localhost:6006)",
    )
    parser.add_argument(
        "--results-dir", default="results/",
        help="Path to results directory (default: results/)",
    )
    parser.add_argument(
        "--port", type=int, default=8050,
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
            f"Port {args.port} is already in use. "
            f"Use --port <number> to specify a different port."
        )
        sys.exit(1)

    logger.info(f"Initializing data loader: results={results_path}, phoenix={args.phoenix_endpoint}")
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
