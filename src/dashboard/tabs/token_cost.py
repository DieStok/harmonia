"""Token & Cost Analysis tab."""

import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import dcc, html


def _cost_per_model(token_df) -> go.Figure:
    """Bar chart: total cost by model."""
    fig = go.Figure()

    if token_df is None or len(token_df) == 0:
        fig.update_layout(template="plotly_white", title="Cost per Model", height=400)
        return fig

    grouped = token_df.groupby("model")["total_cost_usd"].sum().sort_values(ascending=False)

    fig.add_trace(
        go.Bar(
            x=grouped.index.tolist(),
            y=grouped.values.tolist(),
            marker_color="#4CAF50",
        )
    )

    fig.update_layout(
        template="plotly_white",
        title="Total Cost by Model",
        xaxis_title="Model",
        yaxis_title="Cost ($)",
        height=400,
    )

    return fig


def _tokens_per_model(token_df) -> go.Figure:
    """Grouped bar: input vs output tokens per model."""
    fig = go.Figure()

    if token_df is None or len(token_df) == 0:
        fig.update_layout(template="plotly_white", title="Tokens per Model", height=400)
        return fig

    grouped = (
        token_df.groupby("model")
        .agg(
            input_tokens=("total_input_tokens", "sum"),
            output_tokens=("total_output_tokens", "sum"),
        )
        .sort_values("input_tokens", ascending=False)
    )

    fig.add_trace(
        go.Bar(
            x=grouped.index.tolist(),
            y=grouped["input_tokens"].tolist(),
            name="Input Tokens",
            marker_color="#2196F3",
        )
    )
    fig.add_trace(
        go.Bar(
            x=grouped.index.tolist(),
            y=grouped["output_tokens"].tolist(),
            name="Output Tokens",
            marker_color="#FF9800",
        )
    )

    fig.update_layout(
        template="plotly_white",
        title="Token Usage by Model",
        xaxis_title="Model",
        yaxis_title="Tokens",
        barmode="group",
        height=400,
    )

    return fig


def _cost_vs_turns(token_df) -> go.Figure:
    """Scatter: cost vs turns, color by model."""
    fig = go.Figure()

    if token_df is None or len(token_df) == 0:
        fig.update_layout(template="plotly_white", title="Cost vs Turns", height=400)
        return fig

    models = token_df["model"].unique()
    colors = [
        "#2196F3",
        "#4CAF50",
        "#FF9800",
        "#9C27B0",
        "#F44336",
        "#00BCD4",
        "#795548",
        "#607D8B",
        "#E91E63",
        "#3F51B5",
    ]

    for i, model in enumerate(models):
        subset = token_df[token_df["model"] == model]
        fig.add_trace(
            go.Scatter(
                x=subset["total_turns"],
                y=subset["total_cost_usd"],
                mode="markers",
                marker=dict(size=10, color=colors[i % len(colors)]),
                name=model[:30],
                text=subset["run_id"],
                hovertemplate="<b>%{text}</b><br>Turns: %{x}<br>Cost: $%{y:.4f}<extra></extra>",
            )
        )

    fig.update_layout(
        template="plotly_white",
        title="Cost vs Number of Turns",
        xaxis_title="Number of Turns",
        yaxis_title="Cost ($)",
        height=400,
    )

    return fig


def _token_efficiency(token_df, data_loader) -> go.Figure:
    """Scatter: total tokens vs accuracy."""
    fig = go.Figure()

    if token_df is None or len(token_df) == 0:
        fig.update_layout(template="plotly_white", title="Token Efficiency", height=400)
        return fig

    # Join with metrics data to get accuracy
    metrics_df = data_loader.get_all_metrics()
    if metrics_df is None or len(metrics_df) == 0:
        fig.update_layout(
            template="plotly_white", title="Token Efficiency (no metrics)", height=400
        )
        return fig

    merged = token_df.merge(
        metrics_df[["run_id", "avg_accuracy_excl_empty"]],
        on="run_id",
        how="inner",
    )
    merged = merged.dropna(subset=["avg_accuracy_excl_empty"])

    if len(merged) == 0:
        fig.update_layout(template="plotly_white", title="Token Efficiency (no data)", height=400)
        return fig

    models = merged["model"].unique()
    colors = [
        "#2196F3",
        "#4CAF50",
        "#FF9800",
        "#9C27B0",
        "#F44336",
        "#00BCD4",
        "#795548",
        "#607D8B",
        "#E91E63",
        "#3F51B5",
    ]

    for i, model in enumerate(models):
        subset = merged[merged["model"] == model]
        fig.add_trace(
            go.Scatter(
                x=subset["total_tokens"],
                y=subset["avg_accuracy_excl_empty"],
                mode="markers",
                marker=dict(size=10, color=colors[i % len(colors)]),
                name=model[:30],
                text=subset["run_id"],
                hovertemplate="<b>%{text}</b><br>Tokens: %{x:,}<br>Accuracy: %{y:.3f}<extra></extra>",
            )
        )

    fig.update_layout(
        template="plotly_white",
        title="Token Efficiency (Tokens vs Accuracy)",
        xaxis_title="Total Tokens",
        yaxis_title="Accuracy",
        yaxis_range=[0, 1.05],
        height=400,
    )

    return fig


def _cost_over_time(token_df) -> go.Figure:
    """Line: cumulative cost over time."""
    fig = go.Figure()

    if token_df is None or len(token_df) == 0:
        fig.update_layout(template="plotly_white", title="Cumulative Cost Over Time", height=350)
        return fig

    df = token_df.copy()
    df["start_time"] = df["start_time"].apply(lambda x: x if x else None)
    df = df.dropna(subset=["start_time"]).sort_values("start_time")

    if len(df) == 0:
        fig.update_layout(template="plotly_white", title="Cumulative Cost Over Time", height=350)
        return fig

    df["cumulative_cost"] = df["total_cost_usd"].cumsum()

    fig.add_trace(
        go.Scatter(
            x=df["start_time"].tolist(),
            y=df["cumulative_cost"].tolist(),
            mode="lines+markers",
            line=dict(color="#4CAF50", width=2),
            text=df["run_id"],
            hovertemplate="<b>%{text}</b><br>Date: %{x}<br>Cumulative: $%{y:.4f}<extra></extra>",
        )
    )

    fig.update_layout(
        template="plotly_white",
        title="Cumulative Cost Over Time",
        xaxis_title="Date",
        yaxis_title="Cumulative Cost ($)",
        height=350,
    )

    return fig


def render_token_cost(data_loader) -> html.Div:
    """Render the Token & Cost Analysis tab."""
    token_df = data_loader.get_token_summary()

    if token_df is None or len(token_df) == 0:
        return html.Div(
            [
                dbc.Button(
                    "Refresh Data",
                    id="refresh-tokens",
                    color="primary",
                    size="sm",
                    className="mb-3",
                ),
                html.P("No token/cost data available.", className="text-muted text-center my-5"),
            ]
        )

    return html.Div(
        [
            dbc.Button(
                "Refresh Data", id="refresh-tokens", color="primary", size="sm", className="mb-3"
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dcc.Graph(id="cost-per-model", figure=_cost_per_model(token_df)), width=6
                    ),
                    dbc.Col(
                        dcc.Graph(id="tokens-per-model", figure=_tokens_per_model(token_df)),
                        width=6,
                    ),
                ],
                className="mb-3",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dcc.Graph(id="cost-vs-turns", figure=_cost_vs_turns(token_df)), width=6
                    ),
                    dbc.Col(
                        dcc.Graph(
                            id="token-efficiency", figure=_token_efficiency(token_df, data_loader)
                        ),
                        width=6,
                    ),
                ],
                className="mb-3",
            ),
            dcc.Graph(id="cost-over-time", figure=_cost_over_time(token_df)),
            # Cost breakdown table
            html.H5("Cost Breakdown", className="mt-4"),
            dag.AgGrid(
                id="cost-breakdown-table",
                rowData=token_df.to_dict("records"),
                columnDefs=[
                    {"field": "run_id", "headerName": "Run ID", "width": 110},
                    {"field": "model", "headerName": "Model", "width": 180},
                    {"field": "provider", "headerName": "Provider", "width": 120},
                    {
                        "field": "total_input_tokens",
                        "headerName": "Input Tokens",
                        "type": "numericColumn",
                        "valueFormatter": {
                            "function": "params.value ? params.value.toLocaleString() : ''"
                        },
                    },
                    {
                        "field": "total_output_tokens",
                        "headerName": "Output Tokens",
                        "type": "numericColumn",
                        "valueFormatter": {
                            "function": "params.value ? params.value.toLocaleString() : ''"
                        },
                    },
                    {
                        "field": "total_tokens",
                        "headerName": "Total Tokens",
                        "type": "numericColumn",
                        "valueFormatter": {
                            "function": "params.value ? params.value.toLocaleString() : ''"
                        },
                    },
                    {
                        "field": "total_cost_usd",
                        "headerName": "Total Cost ($)",
                        "type": "numericColumn",
                        "valueFormatter": {
                            "function": "params.value ? '$' + params.value.toFixed(4) : ''"
                        },
                    },
                    {"field": "total_turns", "headerName": "Turns", "type": "numericColumn"},
                ],
                defaultColDef={"sortable": True, "filter": True, "resizable": True},
                dashGridOptions={"pagination": True, "paginationPageSize": 20},
                style={"height": "400px"},
            ),
        ]
    )
