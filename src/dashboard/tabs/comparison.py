"""Side-by-Side Comparison tab — compare two experiment runs."""

import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import dcc, html

from dashboard.components.diff_card import create_diff_card
from dashboard.components.span_waterfall import create_span_waterfall
from dashboard.components.turn_accordion import create_turn_accordion


def _metric_comparison_bar(metrics_a: dict | None, metrics_b: dict | None,
                           run_id_a: str, run_id_b: str) -> go.Figure:
    """Grouped bar: per-column accuracy side by side for two runs."""
    fig = go.Figure()

    if not metrics_a and not metrics_b:
        fig.update_layout(template="plotly_white", title="Per-Column Accuracy Comparison", height=400)
        return fig

    cols_a = metrics_a.get("column_values", {}) if metrics_a else {}
    cols_b = metrics_b.get("column_values", {}) if metrics_b else {}

    # Union of column sets
    all_cols = sorted(set(cols_a.keys()) | set(cols_b.keys()))

    acc_a = [cols_a.get(c, {}).get("accuracy_excl_empty") for c in all_cols]
    acc_b = [cols_b.get(c, {}).get("accuracy_excl_empty") for c in all_cols]

    fig.add_trace(go.Bar(
        x=all_cols, y=acc_a,
        name=f"Run A ({run_id_a})",
        marker_color="#2196F3",
    ))
    fig.add_trace(go.Bar(
        x=all_cols, y=acc_b,
        name=f"Run B ({run_id_b})",
        marker_color="#FF9800",
    ))

    fig.update_layout(
        template="plotly_white",
        title="Per-Column Accuracy Comparison",
        xaxis_title="Column",
        yaxis_title="Accuracy",
        yaxis_range=[0, 1.05],
        barmode="group",
        height=400,
    )

    return fig


def _token_comparison_bar(turns_a: list[dict], turns_b: list[dict],
                          run_id_a: str, run_id_b: str) -> go.Figure:
    """Grouped bar: per-turn token usage side by side."""
    fig = go.Figure()

    max_turns = max(len(turns_a), len(turns_b)) if turns_a or turns_b else 0
    if max_turns == 0:
        fig.update_layout(template="plotly_white", title="Token Comparison", height=350)
        return fig

    turn_nums = list(range(1, max_turns + 1))

    def total_tokens(turns, idx):
        if idx < len(turns):
            return turns[idx].get("input_tokens", 0) + turns[idx].get("output_tokens", 0)
        return 0

    tokens_a = [total_tokens(turns_a, i) for i in range(max_turns)]
    tokens_b = [total_tokens(turns_b, i) for i in range(max_turns)]

    fig.add_trace(go.Bar(
        x=turn_nums, y=tokens_a,
        name=f"Run A ({run_id_a})",
        marker_color="#2196F3",
    ))
    fig.add_trace(go.Bar(
        x=turn_nums, y=tokens_b,
        name=f"Run B ({run_id_b})",
        marker_color="#FF9800",
    ))

    fig.update_layout(
        template="plotly_white",
        title="Token Usage per Turn",
        xaxis_title="Turn",
        yaxis_title="Tokens",
        barmode="group",
        height=350,
    )

    return fig


def render_comparison(data_loader, run_id_a: str | None = None,
                      run_id_b: str | None = None) -> html.Div:
    """Render the Side-by-Side Comparison tab."""
    runs_df = data_loader.get_all_runs()

    run_options = []
    if runs_df is not None and len(runs_df) > 0:
        for _, row in runs_df.iterrows():
            label = f"{row['run_id']} — {row.get('model', '?')[:25]} ({row.get('status', '?')})"
            run_options.append({"label": label, "value": row["run_id"]})

    components = [
        dbc.Button("Refresh Data", id="refresh-comparison", color="primary",
                   size="sm", className="mb-3"),
        dbc.Row([
            dbc.Col([
                html.Label("Run A:"),
                dcc.Dropdown(id="comparison-run-a", options=run_options, value=run_id_a,
                             placeholder="Select Run A..."),
            ], width=6),
            dbc.Col([
                html.Label("Run B:"),
                dcc.Dropdown(id="comparison-run-b", options=run_options, value=run_id_b,
                             placeholder="Select Run B..."),
            ], width=6),
        ], className="mb-3"),
        html.Hr(),
    ]

    if not run_id_a or not run_id_b:
        components.append(html.P(
            "Select two runs above to compare.", className="text-muted text-center my-5",
        ))
        return html.Div(components)

    if run_id_a == run_id_b:
        components.append(dbc.Alert("Select two different runs to compare.", color="warning"))
        return html.Div(components)

    # Load data for both runs
    trace_a = data_loader.get_run_trace(run_id_a)
    trace_b = data_loader.get_run_trace(run_id_b)
    metrics_a = data_loader.get_run_metrics(run_id_a)
    metrics_b = data_loader.get_run_metrics(run_id_b)

    # Build run metadata dicts for diff card
    def _run_meta(run_id, trace, metrics):
        meta = {"run_id": run_id}
        if trace:
            turns = trace.get("turns", [])
            meta["model"] = trace.get("llm", {}).get("model", "")
            meta["total_turns"] = len(turns)
            meta["total_duration"] = trace.get("timing", {}).get("total_duration_seconds", 0)
            meta["total_input_tokens"] = sum(t.get("input_tokens", 0) for t in turns)
            meta["total_output_tokens"] = sum(t.get("output_tokens", 0) for t in turns)
            meta["total_cost_usd"] = sum(t.get("cost_usd", 0) for t in turns)
        if metrics:
            meta["accuracy"] = metrics.get("overall_summary", {}).get("avg_accuracy_excl_empty")
            meta["column_mapping_accuracy"] = metrics.get("column_mapping", {}).get("accuracy")
        return meta

    meta_a = _run_meta(run_id_a, trace_a, metrics_a)
    meta_b = _run_meta(run_id_b, trace_b, metrics_b)

    # Diff summary card
    components.append(create_diff_card(meta_a, meta_b))

    # Metric comparison
    if metrics_a or metrics_b:
        components.append(dcc.Graph(
            id="metric-comparison-bar",
            figure=_metric_comparison_bar(metrics_a, metrics_b, run_id_a, run_id_b),
        ))

    # Token comparison
    turns_a = trace_a.get("turns", []) if trace_a else []
    turns_b = trace_b.get("turns", []) if trace_b else []

    if turns_a or turns_b:
        components.append(dcc.Graph(
            id="token-comparison-bar",
            figure=_token_comparison_bar(turns_a, turns_b, run_id_a, run_id_b),
        ))

    # Side-by-side turn accordions
    if turns_a or turns_b:
        components.append(html.H5("Conversation Turns"))
        components.append(dbc.Row([
            dbc.Col([
                html.H6(f"Run A: {run_id_a}", className="text-muted"),
                create_turn_accordion(turns_a, accordion_id="run-a-accordion"),
            ], width=6),
            dbc.Col([
                html.H6(f"Run B: {run_id_b}", className="text-muted"),
                create_turn_accordion(turns_b, accordion_id="run-b-accordion"),
            ], width=6),
        ]))

    # Timeline overlay (if Phoenix data available for both)
    spans_a = data_loader.get_run_spans(run_id_a)
    spans_b = data_loader.get_run_spans(run_id_b)
    if spans_a is not None and spans_b is not None:
        components.append(html.H5("Span Waterfall Comparison", className="mt-4"))
        components.append(dbc.Row([
            dbc.Col([
                html.H6(f"Run A: {run_id_a}", className="text-muted"),
                dcc.Graph(figure=create_span_waterfall(spans_a)),
            ], width=6),
            dbc.Col([
                html.H6(f"Run B: {run_id_b}", className="text-muted"),
                dcc.Graph(figure=create_span_waterfall(spans_b)),
            ], width=6),
        ]))

    return html.Div(components)
