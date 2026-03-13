"""Metrics Comparison tab — bar charts, scatter, heatmap, radar."""

import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import dcc, html


def _accuracy_bar_chart(metrics_df) -> go.Figure:
    """Bar chart: column mapping accuracy + value accuracy per run."""
    fig = go.Figure()

    if metrics_df is None or len(metrics_df) == 0:
        fig.update_layout(template="plotly_white", title="Accuracy by Run", height=400)
        return fig

    df = metrics_df.sort_values("avg_accuracy_excl_empty", ascending=False).head(30)

    labels = [f"{r['run_id']}\n{(r['model'] or '')[:20]}" for _, r in df.iterrows()]

    fig.add_trace(
        go.Bar(
            x=labels,
            y=df["column_mapping_accuracy"].tolist(),
            name="Column Mapping",
            marker_color="#2196F3",
            customdata=df["run_id"].tolist(),
        )
    )

    fig.add_trace(
        go.Bar(
            x=labels,
            y=df["avg_accuracy_excl_empty"].tolist(),
            name="Value Accuracy",
            marker_color="#4CAF50",
            customdata=df["run_id"].tolist(),
        )
    )

    fig.update_layout(
        template="plotly_white",
        title="Accuracy by Run",
        xaxis_title="Run",
        yaxis_title="Accuracy",
        yaxis_range=[0, 1.05],
        barmode="group",
        height=450,
    )

    return fig


def _cost_vs_accuracy_scatter(metrics_df) -> go.Figure:
    """Scatter: cost vs accuracy, size=tokens, color=model."""
    fig = go.Figure()

    if metrics_df is None or len(metrics_df) == 0:
        fig.update_layout(template="plotly_white", title="Cost vs Accuracy", height=400)
        return fig

    df = metrics_df.dropna(subset=["avg_accuracy_excl_empty"])
    if len(df) == 0:
        fig.update_layout(template="plotly_white", title="Cost vs Accuracy", height=400)
        return fig

    total_tokens = df["total_input_tokens"] + df["total_output_tokens"]
    # Normalize size for display
    max_tokens = total_tokens.max() if total_tokens.max() > 0 else 1
    sizes = (total_tokens / max_tokens * 40 + 10).clip(10, 60)

    models = df["model"].unique()
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
    color_map = {m: colors[i % len(colors)] for i, m in enumerate(models)}

    for model in models:
        mask = df["model"] == model
        subset = df[mask]
        fig.add_trace(
            go.Scatter(
                x=subset["total_cost_usd"],
                y=subset["avg_accuracy_excl_empty"],
                mode="markers+text",
                marker=dict(size=sizes[mask].tolist(), color=color_map[model], opacity=0.7),
                text=subset["run_id"],
                textposition="top center",
                textfont=dict(size=8),
                name=model[:30],
                hovertemplate=(
                    "<b>%{text}</b><br>Cost: $%{x:.4f}<br>Accuracy: %{y:.3f}<br><extra></extra>"
                ),
            )
        )

    fig.update_layout(
        template="plotly_white",
        title="Cost vs Accuracy",
        xaxis_title="Total Cost ($)",
        yaxis_title="Value Accuracy",
        yaxis_range=[0, 1.05],
        height=450,
    )

    return fig


def _accuracy_heatmap(data_loader, metrics_df) -> go.Figure:
    """Heatmap: per-column accuracy across runs."""
    fig = go.Figure()

    if metrics_df is None or len(metrics_df) == 0:
        fig.update_layout(template="plotly_white", title="Per-Column Accuracy", height=400)
        return fig

    # Collect per-column accuracy for each run
    all_columns = set()
    run_column_acc = {}

    for _, row in metrics_df.iterrows():
        run_id = row["run_id"]
        metrics = data_loader.get_run_metrics(run_id)
        if metrics is None:
            continue
        col_vals = metrics.get("column_values", {})
        for col_name, col_data in col_vals.items():
            all_columns.add(col_name)
            run_column_acc.setdefault(run_id, {})[col_name] = col_data.get("accuracy_excl_empty", 0)

    if not all_columns or not run_column_acc:
        fig.update_layout(template="plotly_white", title="Per-Column Accuracy", height=400)
        return fig

    columns_sorted = sorted(all_columns)
    runs_sorted = list(run_column_acc.keys())

    z = []
    for col in columns_sorted:
        row = [run_column_acc.get(rid, {}).get(col) for rid in runs_sorted]
        z.append(row)

    # Abbreviate run labels
    run_labels = []
    for rid in runs_sorted:
        model = metrics_df.loc[metrics_df["run_id"] == rid, "model"]
        label = f"{rid}"
        if len(model) > 0:
            label = f"{rid}\n{model.iloc[0][:15]}"
        run_labels.append(label)

    fig.add_trace(
        go.Heatmap(
            z=z,
            x=run_labels,
            y=columns_sorted,
            colorscale="RdYlGn",
            zmin=0,
            zmax=1,
            hovertemplate="Run: %{x}<br>Column: %{y}<br>Accuracy: %{z:.3f}<extra></extra>",
        )
    )

    fig.update_layout(
        template="plotly_white",
        title="Per-Column Accuracy Heatmap",
        height=max(400, len(columns_sorted) * 25 + 100),
        margin=dict(l=150),
    )

    return fig


def _token_usage_bar(metrics_df) -> go.Figure:
    """Grouped bar: input vs output tokens per run."""
    fig = go.Figure()

    if metrics_df is None or len(metrics_df) == 0:
        fig.update_layout(template="plotly_white", title="Token Usage per Run", height=400)
        return fig

    df = metrics_df.sort_values("total_input_tokens", ascending=False).head(30)
    labels = [f"{r['run_id']}\n{r['model'][:15]}" for _, r in df.iterrows()]

    fig.add_trace(
        go.Bar(x=labels, y=df["total_input_tokens"], name="Input", marker_color="#2196F3")
    )
    fig.add_trace(
        go.Bar(x=labels, y=df["total_output_tokens"], name="Output", marker_color="#FF9800")
    )

    fig.update_layout(
        template="plotly_white",
        title="Token Usage per Run",
        xaxis_title="Run",
        yaxis_title="Tokens",
        barmode="group",
        height=400,
    )

    return fig


def _radar_chart(data_loader, run_ids: list[str]) -> go.Figure:
    """Radar/spider chart for F1/precision/recall per column for selected runs."""
    fig = go.Figure()

    if not run_ids:
        fig.update_layout(template="plotly_white", title="F1 / Precision / Recall", height=400)
        return fig

    colors = ["#2196F3", "#4CAF50", "#FF9800", "#9C27B0", "#F44336"]

    for i, run_id in enumerate(run_ids[:5]):
        metrics = data_loader.get_run_metrics(run_id)
        if metrics is None:
            continue

        col_vals = metrics.get("column_values", {})
        if not col_vals:
            continue

        categories = sorted(col_vals.keys())
        f1_values = [col_vals[c].get("f1_macro_excl_empty", 0) for c in categories]
        # Close the polygon
        f1_values.append(f1_values[0])
        categories_closed = categories + [categories[0]]

        fig.add_trace(
            go.Scatterpolar(
                r=f1_values,
                theta=categories_closed,
                fill="toself",
                name=run_id,
                opacity=0.5,
                line_color=colors[i % len(colors)],
            )
        )

    fig.update_layout(
        template="plotly_white",
        title="F1 Score by Column (Selected Runs)",
        polar=dict(radialaxis=dict(range=[0, 1])),
        height=500,
    )

    return fig


def _metrics_boxplot(metrics_df, group_by: str = "model_family") -> go.Figure:
    """Boxplots of accuracy/F1/precision/recall grouped by a category."""
    fig = go.Figure()

    if metrics_df is None or len(metrics_df) == 0:
        fig.update_layout(template="plotly_white", title="Metrics Distribution", height=400)
        return fig

    # Ensure group_by column exists; fall back gracefully
    if group_by not in metrics_df.columns:
        if group_by == "model_family" and "model" in metrics_df.columns:
            metrics_df = metrics_df.copy()
            metrics_df["model_family"] = metrics_df["model"]
        else:
            fig.update_layout(
                template="plotly_white", title=f"Column '{group_by}' not available", height=400
            )
            return fig

    metrics_to_plot = [
        ("avg_accuracy_excl_empty", "Accuracy", "#2196F3"),
        ("avg_f1_excl_empty", "F1", "#4CAF50"),
        ("avg_precision_excl_empty", "Precision", "#FF9800"),
        ("avg_recall_excl_empty", "Recall", "#9C27B0"),
    ]

    for col, name, color in metrics_to_plot:
        if col not in metrics_df.columns:
            continue
        df_valid = metrics_df.dropna(subset=[col])
        if df_valid.empty:
            continue
        fig.add_trace(
            go.Box(
                x=df_valid[group_by],
                y=df_valid[col],
                name=name,
                marker_color=color,
                boxpoints="all",
                jitter=0.3,
                pointpos=-1.5,
            )
        )

    group_label = group_by.replace("_", " ").title()
    fig.update_layout(
        template="plotly_white",
        title=f"Metrics Distribution by {group_label}",
        xaxis_title=group_label,
        yaxis_title="Score",
        yaxis_range=[0, 1.05],
        boxmode="group",
        height=500,
    )

    return fig


def render_metrics(data_loader, selected_run_ids: list[str] | None = None) -> html.Div:
    """Render the Metrics Comparison tab."""
    metrics_df = data_loader.get_all_metrics()

    if metrics_df is None or len(metrics_df) == 0:
        return html.Div(
            [
                dbc.Button(
                    "Refresh Data",
                    id="refresh-metrics",
                    color="primary",
                    size="sm",
                    className="mb-3",
                ),
                html.P(
                    "No metrics data available. Run experiments with evaluation enabled.",
                    className="text-muted text-center my-5",
                ),
            ]
        )

    # Run selection for radar chart
    all_run_ids = metrics_df["run_id"].tolist()
    radar_ids = selected_run_ids or all_run_ids[:3]

    return html.Div(
        [
            dbc.Button(
                "Refresh Data", id="refresh-metrics", color="primary", size="sm", className="mb-3"
            ),
            # Accuracy bar chart (with click-through)
            dbc.Row(
                [
                    dbc.Col(
                        dcc.Graph(
                            id="accuracy-bar-chart",
                            figure=_accuracy_bar_chart(metrics_df),
                        ),
                        width=8,
                    ),
                    dbc.Col(
                        dcc.Graph(
                            id="cost-accuracy-scatter",
                            figure=_cost_vs_accuracy_scatter(metrics_df),
                        ),
                        width=4,
                    ),
                ],
                className="mb-4",
            ),
            # Token usage
            dbc.Row(
                [
                    dbc.Col(
                        dcc.Graph(
                            id="token-usage-bar",
                            figure=_token_usage_bar(metrics_df),
                        ),
                        width=7,
                    ),
                    dbc.Col(
                        [
                            html.Label("Select runs for radar chart (max 5):"),
                            dcc.Dropdown(
                                id="radar-run-selector",
                                options=[
                                    {
                                        "label": f"{rid} ({metrics_df.loc[metrics_df['run_id'] == rid, 'model'].iloc[0][:20] if len(metrics_df.loc[metrics_df['run_id'] == rid]) > 0 else '?'})",
                                        "value": rid,
                                    }
                                    for rid in all_run_ids
                                ],
                                value=radar_ids[:5],
                                multi=True,
                            ),
                            dcc.Graph(
                                id="radar-chart",
                                figure=_radar_chart(data_loader, radar_ids),
                            ),
                        ],
                        width=5,
                    ),
                ],
                className="mb-4",
            ),
            # Heatmap
            dcc.Graph(
                id="accuracy-heatmap",
                figure=_accuracy_heatmap(data_loader, metrics_df),
            ),
            # Boxplots
            html.H5("Metrics Distribution", className="mt-4"),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Label("Group by:"),
                            dcc.Dropdown(
                                id="boxplot-group-selector",
                                options=[
                                    {"label": "Model Family", "value": "model_family"},
                                    {"label": "Model", "value": "model"},
                                    {"label": "Provider", "value": "provider"},
                                ],
                                value="model_family",
                                clearable=False,
                                style={"width": "200px"},
                            ),
                        ],
                        width=3,
                    ),
                ],
                className="mb-2",
            ),
            dcc.Graph(
                id="metrics-boxplot",
                figure=_metrics_boxplot(metrics_df, "model_family"),
            ),
            # Metrics detail table
            html.H5("Detailed Metrics", className="mt-4"),
            dag.AgGrid(
                id="metrics-detail-table",
                rowData=metrics_df.to_dict("records"),
                columnDefs=[
                    {
                        "field": c,
                        "headerName": c.replace("_", " ").title(),
                        "valueFormatter": {
                            "function": "typeof params.value === 'number' ? params.value.toFixed(4) : params.value"
                        }
                        if metrics_df[c].dtype in ["float64", "float32"]
                        else {},
                    }
                    for c in metrics_df.columns
                ],
                defaultColDef={"sortable": True, "filter": True, "resizable": True},
                dashGridOptions={"pagination": True, "paginationPageSize": 20},
                style={"height": "400px"},
            ),
        ]
    )
