"""Trace Explorer tab — deep-dive into a single experiment run."""

import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import dcc, html

from dashboard.components.span_waterfall import create_span_waterfall
from dashboard.components.turn_accordion import create_turn_accordion


def _confusion_matrix_chart(confusion_data: dict, column_name: str) -> go.Figure:
    """Plotly heatmap confusion matrix for a single column."""
    fig = go.Figure()

    if not confusion_data:
        fig.update_layout(
            template="plotly_white", title=f"Confusion Matrix: {column_name}", height=350
        )
        return fig

    labels = sorted(
        set(list(confusion_data.keys()) + [pred for row in confusion_data.values() for pred in row])
    )

    # Build matrix
    z = []
    for expected in labels:
        row_data = []
        for predicted in labels:
            count = confusion_data.get(expected, {}).get(predicted, 0)
            row_data.append(count)
        z.append(row_data)

    # Truncate labels for display
    display_labels = [lbl[:20] + "..." if len(lbl) > 20 else lbl for lbl in labels]

    fig.add_trace(
        go.Heatmap(
            z=z,
            x=display_labels,
            y=display_labels,
            colorscale="Blues",
            hovertemplate="Expected: %{y}<br>Predicted: %{x}<br>Count: %{z}<extra></extra>",
            text=z,
            texttemplate="%{text}",
        )
    )

    fig.update_layout(
        template="plotly_white",
        title=f"Confusion Matrix: {column_name}",
        xaxis_title="Predicted",
        yaxis_title="Expected",
        height=max(350, len(labels) * 25 + 150),
        yaxis=dict(autorange="reversed"),
    )

    return fig


def _token_per_turn_chart(turns: list[dict]) -> go.Figure:
    """Stacked bar: input + output tokens per turn."""
    fig = go.Figure()

    if not turns:
        fig.update_layout(template="plotly_white", title="Tokens per Turn", height=300)
        return fig

    turn_nums = [t.get("turn", i + 1) for i, t in enumerate(turns)]
    input_tokens = [t.get("input_tokens", 0) for t in turns]
    output_tokens = [t.get("output_tokens", 0) for t in turns]

    fig.add_trace(
        go.Bar(
            x=turn_nums,
            y=input_tokens,
            name="Input Tokens",
            marker_color="#2196F3",
        )
    )
    fig.add_trace(
        go.Bar(
            x=turn_nums,
            y=output_tokens,
            name="Output Tokens",
            marker_color="#FF9800",
        )
    )

    fig.update_layout(
        template="plotly_white",
        title="Token Usage per Turn",
        xaxis_title="Turn",
        yaxis_title="Tokens",
        barmode="stack",
        height=300,
    )

    return fig


def _cumulative_cost_chart(turns: list[dict]) -> go.Figure:
    """Line: cumulative cost across turns."""
    fig = go.Figure()

    if not turns:
        fig.update_layout(template="plotly_white", title="Cumulative Cost", height=300)
        return fig

    turn_nums = [t.get("turn", i + 1) for i, t in enumerate(turns)]
    costs = [t.get("cost_usd", 0) for t in turns]

    cumulative = []
    running = 0
    for c in costs:
        running += c
        cumulative.append(running)

    fig.add_trace(
        go.Scatter(
            x=turn_nums,
            y=cumulative,
            mode="lines+markers",
            name="Cumulative Cost",
            line=dict(color="#4CAF50", width=2),
        )
    )

    fig.update_layout(
        template="plotly_white",
        title="Cumulative Cost",
        xaxis_title="Turn",
        yaxis_title="Cost ($)",
        height=300,
    )

    return fig


def _run_header_card(
    trace_data: dict, run_id: str, has_phoenix: bool, phoenix_endpoint: str
) -> dbc.Card:
    """Header card with run metadata."""
    exp = trace_data.get("experiment", {})
    llm = trace_data.get("llm", {})
    timing = trace_data.get("timing", {})
    status = trace_data.get("status", "unknown")
    turns = trace_data.get("turns", [])

    total_input = sum(t.get("input_tokens", 0) for t in turns)
    total_output = sum(t.get("output_tokens", 0) for t in turns)
    total_cost = sum(t.get("cost_usd", 0) for t in turns)

    status_color = {
        "completed": "success",
        "failed": "danger",
        "timeout": "warning",
        "running": "info",
    }.get(status, "secondary")

    children = [
        dbc.CardHeader(
            html.H5(
                [
                    f"Run {run_id} ",
                    dbc.Badge(status, color=status_color),
                ]
            )
        ),
        dbc.CardBody(
            [
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.Small("Experiment", className="text-muted d-block"),
                                html.Strong(exp.get("name", "N/A")),
                            ],
                            width=3,
                        ),
                        dbc.Col(
                            [
                                html.Small("Model", className="text-muted d-block"),
                                html.Strong(f"{llm.get('provider', '')} / {llm.get('model', '')}"),
                            ],
                            width=3,
                        ),
                        dbc.Col(
                            [
                                html.Small("Duration", className="text-muted d-block"),
                                html.Strong(f"{timing.get('total_duration_seconds', 0):.1f}s"),
                            ],
                            width=1,
                        ),
                        dbc.Col(
                            [
                                html.Small("Turns", className="text-muted d-block"),
                                html.Strong(str(len(turns))),
                            ],
                            width=1,
                        ),
                        dbc.Col(
                            [
                                html.Small("Tokens", className="text-muted d-block"),
                                html.Strong(f"{total_input + total_output:,}"),
                            ],
                            width=2,
                        ),
                        dbc.Col(
                            [
                                html.Small("Cost", className="text-muted d-block"),
                                html.Strong(f"${total_cost:.4f}"),
                            ],
                            width=2,
                        ),
                    ]
                ),
            ]
        ),
    ]

    return dbc.Card(children, className="mb-3")


def render_trace_explorer(
    data_loader,
    selected_run_id: str | None = None,
    turn_page: int = 0,
) -> html.Div:
    """Render the Trace Explorer tab."""
    runs_df = data_loader.get_all_runs()

    # Build run options for dropdown
    run_options = []
    if runs_df is not None and len(runs_df) > 0:
        for _, row in runs_df.iterrows():
            label = f"{row['run_id']} — {row.get('model', '?')[:25]} ({row.get('status', '?')})"
            run_options.append({"label": label, "value": row["run_id"]})

    components = [
        dbc.Button(
            "Refresh Data", id="refresh-trace", color="primary", size="sm", className="mb-3 me-2"
        ),
        html.Label("Select Run:", className="me-2"),
        dcc.Dropdown(
            id="trace-run-selector",
            options=run_options,
            value=selected_run_id,
            placeholder="Select a run...",
            style={"width": "500px", "display": "inline-block", "verticalAlign": "middle"},
        ),
        html.Hr(),
    ]

    if not selected_run_id:
        components.append(
            html.P(
                "Select a run from the dropdown above to explore its trace.",
                className="text-muted text-center my-5",
            )
        )
        return html.Div(components)

    # Load trace data
    trace_data = data_loader.get_run_trace(selected_run_id)
    spans_df = data_loader.get_run_spans(selected_run_id)

    if trace_data is None and spans_df is None:
        components.append(
            dbc.Alert(
                "No trace or span data available for this run.",
                color="warning",
            )
        )
        return html.Div(components)

    # Run header
    if trace_data:
        components.append(
            _run_header_card(
                trace_data,
                selected_run_id,
                has_phoenix=(spans_df is not None),
                phoenix_endpoint=data_loader.phoenix_endpoint,
            )
        )

    # Span waterfall (only if Phoenix data available)
    if spans_df is not None:
        components.append(html.H5("Span Waterfall"))
        components.append(
            dcc.Graph(
                id="span-waterfall",
                figure=create_span_waterfall(spans_df),
            )
        )

    # Turn-level charts and accordion
    if trace_data:
        turns = trace_data.get("turns", [])

        if not turns:
            components.append(
                dbc.Alert(
                    "Experiment completed with no conversation turns.",
                    color="info",
                )
            )
        else:
            # Charts side by side
            components.append(
                dbc.Row(
                    [
                        dbc.Col(
                            dcc.Graph(
                                id="turn-tokens-chart",
                                figure=_token_per_turn_chart(turns),
                            ),
                            width=6,
                        ),
                        dbc.Col(
                            dcc.Graph(
                                id="turn-cost-chart",
                                figure=_cumulative_cost_chart(turns),
                            ),
                            width=6,
                        ),
                    ],
                    className="mb-3",
                )
            )

            # Error indicators
            error_turns = [t for t in turns if t.get("response_type") == "error"]
            if error_turns:
                components.append(
                    dbc.Alert(
                        f"{len(error_turns)} turn(s) had errors. Check turns: "
                        + ", ".join(str(t.get("turn", "?")) for t in error_turns),
                        color="danger",
                    )
                )

            # Turn accordion with pagination
            components.append(html.H5("Conversation Turns"))
            components.append(
                html.Div(
                    create_turn_accordion(turns, page=turn_page),
                    id="turn-accordion-container",
                )
            )
    elif spans_df is not None:
        components.append(
            dbc.Alert(
                "Trace data (trace.json) not available. Showing Phoenix span data only.",
                color="info",
            )
        )

    # Confusion matrices (from metrics.json, independent of trace)
    metrics = data_loader.get_run_metrics(selected_run_id)
    if metrics:
        col_vals = metrics.get("column_values", {})
        columns_with_cm = {
            name: data.get("confusion_matrix", {})
            for name, data in col_vals.items()
            if data.get("confusion_matrix")
        }
        if columns_with_cm:
            # Filter out columns with too many unique values (>25)
            columns_with_cm = {name: cm for name, cm in columns_with_cm.items() if len(cm) <= 25}
        if columns_with_cm:
            col_names = sorted(columns_with_cm.keys())
            default_col = col_names[0]

            components.append(html.Hr())
            components.append(html.H5("Confusion Matrices"))
            components.append(
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.Label("Select column:"),
                                dcc.Dropdown(
                                    id="confusion-column-selector",
                                    options=[{"label": c, "value": c} for c in col_names],
                                    value=default_col,
                                    clearable=False,
                                    style={"width": "300px"},
                                ),
                            ],
                            width=4,
                        ),
                    ],
                    className="mb-2",
                )
            )
            components.append(
                dcc.Graph(
                    id="confusion-matrix-chart",
                    figure=_confusion_matrix_chart(columns_with_cm[default_col], default_col),
                )
            )

    return html.Div(components)
