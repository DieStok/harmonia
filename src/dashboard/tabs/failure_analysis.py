"""Failure Analysis tab — success/failure heatmap, failure distribution, sunburst."""

import dash_bootstrap_components as dbc
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import dcc, html


def _success_failure_heatmap(runs_df: pd.DataFrame) -> go.Figure:
    """Model x context grid showing success/failure with hover details."""
    fig = go.Figure()

    if runs_df.empty:
        fig.update_layout(template="plotly_white", title="Success/Failure Grid", height=400)
        return fig

    # Determine axes
    models = sorted(runs_df["model"].dropna().unique())
    contexts = sorted(runs_df["context"].dropna().unique())

    if not models or not contexts:
        fig.update_layout(template="plotly_white", title="Success/Failure Grid", height=400)
        return fig

    z_data, hover_data = [], []
    for model in models:
        z_row, hover_row = [], []
        for context in contexts:
            match = runs_df[(runs_df["model"] == model) & (runs_df["context"] == context)]
            if match.empty:
                z_row.append(np.nan)
                hover_row.append("No data")
                continue
            row = match.iloc[0]
            has_output = row.get("has_output", row.get("has_metrics", False))
            if has_output:
                z_row.append(1)
                acc = row.get("accuracy")
                cm_acc = row.get("column_mapping_accuracy")
                acc_s = f"{acc:.3f}" if pd.notna(acc) else "N/A"
                cm_s = f"{cm_acc:.3f}" if pd.notna(cm_acc) else "N/A"
                hover_row.append(
                    f"<b>{model} / {context}</b><br>"
                    f"Status: Success<br>"
                    f"Run ID: {row.get('run_id', 'N/A')}<br>"
                    f"Col Mapping: {cm_s}<br>"
                    f"Value Acc: {acc_s}"
                )
            else:
                z_row.append(0)
                reason = row.get("failure_reason", "Unknown")
                hover_row.append(
                    f"<b>{model} / {context}</b><br>"
                    f"Status: FAILED<br>"
                    f"Reason: {reason}<br>"
                    f"Run ID: {row.get('run_id', 'N/A')}"
                )
        z_data.append(z_row)
        hover_data.append(hover_row)

    fig.add_trace(
        go.Heatmap(
            z=z_data,
            x=contexts,
            y=models,
            hovertext=hover_data,
            hoverinfo="text",
            colorscale=[[0, "#ffc7ce"], [0.5, "#ffe8a1"], [1, "#c6efce"]],
            zmin=0,
            zmax=1,
            showscale=False,
            text=[["FAIL" if v == 0 else ("OK" if v == 1 else "") for v in row] for row in z_data],
            texttemplate="%{text}",
            textfont={"size": 14},
        )
    )

    n_ok = sum(1 for row in z_data for v in row if v == 1)
    n_total = sum(1 for row in z_data for v in row if not np.isnan(v))

    fig.update_layout(
        title=f"Run Success/Failure Grid ({n_ok}/{n_total} successful)",
        xaxis_title="Context",
        yaxis_title="Model",
        height=max(350, len(models) * 40 + 150),
        template="plotly_white",
        yaxis=dict(autorange="reversed"),
    )

    return fig


def _failure_distribution_bar(runs_df: pd.DataFrame) -> go.Figure:
    """Horizontal bar chart of failure reason counts."""
    fig = go.Figure()

    failed = runs_df[runs_df.get("has_output", runs_df.get("has_metrics", True)) == False].copy()  # noqa: E712
    if failed.empty or "failure_reason" not in failed.columns:
        fig.update_layout(template="plotly_white", title="No failures to display", height=350)
        return fig

    counts = failed["failure_reason"].value_counts().reset_index()
    counts.columns = ["failure_reason", "count"]

    fig = px.bar(
        counts,
        x="count",
        y="failure_reason",
        orientation="h",
        title=f"Failure Mode Distribution ({len(failed)} failed runs)",
        labels={"count": "Number of Runs", "failure_reason": ""},
        color="failure_reason",
        color_discrete_sequence=px.colors.qualitative.Set1,
        text="count",
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(
        showlegend=False,
        height=max(300, len(counts) * 35 + 100),
        template="plotly_white",
        xaxis_range=[0, counts["count"].max() + 1.5],
    )

    return fig


def _failure_sunburst(runs_df: pd.DataFrame) -> go.Figure:
    """Sunburst: failure_reason → model → context hierarchy."""
    failed = runs_df[runs_df.get("has_output", runs_df.get("has_metrics", True)) == False].copy()  # noqa: E712
    if failed.empty or "failure_reason" not in failed.columns:
        return go.Figure().update_layout(
            template="plotly_white",
            title="No failures to display",
            height=400,
        )

    records = [
        {
            "failure_reason": r["failure_reason"],
            "model": r.get("model", "?"),
            "context": r.get("context", "?"),
            "count": 1,
        }
        for _, r in failed.iterrows()
    ]
    df = pd.DataFrame(records)

    fig = px.sunburst(
        df,
        path=["failure_reason", "model", "context"],
        values="count",
        title=f"Failure Mode Breakdown ({len(failed)} failed runs)",
        color="failure_reason",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_layout(height=500, template="plotly_white")
    return fig


def render_failure_analysis(data_loader) -> html.Div:
    """Render the Failure Analysis tab."""
    runs_df = data_loader.get_all_runs_with_failures()

    if runs_df.empty:
        return html.Div(
            [
                dbc.Button(
                    "Refresh Data",
                    id="refresh-failure-analysis",
                    color="primary",
                    size="sm",
                    className="mb-3",
                ),
                html.P("No run data available.", className="text-muted text-center my-5"),
            ]
        )

    # Count successes and failures
    has_output_col = "has_output" if "has_output" in runs_df.columns else "has_metrics"
    n_success = runs_df[has_output_col].sum() if has_output_col in runs_df.columns else 0
    n_total = len(runs_df)
    n_failed = n_total - n_success

    # Failure reason explanations
    failure_explanations = []
    if "failure_reason" in runs_df.columns:
        reasons = runs_df["failure_reason"].dropna().unique()
        for reason in sorted(reasons):
            count = len(runs_df[runs_df["failure_reason"] == reason])
            failure_explanations.append(
                html.Li(f"{reason} ({count} run{'s' if count != 1 else ''})"),
            )

    return html.Div(
        [
            dbc.Button(
                "Refresh Data",
                id="refresh-failure-analysis",
                color="primary",
                size="sm",
                className="mb-3",
            ),
            # Summary cards
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            dbc.CardBody(
                                [
                                    html.H4(str(n_total), className="text-primary"),
                                    html.Small("Total Runs"),
                                ]
                            ),
                            className="text-center",
                        ),
                        width=3,
                    ),
                    dbc.Col(
                        dbc.Card(
                            dbc.CardBody(
                                [
                                    html.H4(str(int(n_success)), className="text-success"),
                                    html.Small("Successful"),
                                ]
                            ),
                            className="text-center",
                        ),
                        width=3,
                    ),
                    dbc.Col(
                        dbc.Card(
                            dbc.CardBody(
                                [
                                    html.H4(str(n_failed), className="text-danger"),
                                    html.Small("Failed"),
                                ]
                            ),
                            className="text-center",
                        ),
                        width=3,
                    ),
                    dbc.Col(
                        dbc.Card(
                            dbc.CardBody(
                                [
                                    html.H4(
                                        f"{n_success / n_total * 100:.0f}%"
                                        if n_total > 0
                                        else "N/A",
                                        className="text-info",
                                    ),
                                    html.Small("Success Rate"),
                                ]
                            ),
                            className="text-center",
                        ),
                        width=3,
                    ),
                ],
                className="mb-4",
            ),
            # Heatmap
            dcc.Graph(
                id="success-failure-heatmap",
                figure=_success_failure_heatmap(runs_df),
            ),
            # Failure distribution + sunburst side by side
            dbc.Row(
                [
                    dbc.Col(
                        dcc.Graph(
                            id="failure-distribution-bar",
                            figure=_failure_distribution_bar(runs_df),
                        ),
                        width=6,
                    ),
                    dbc.Col(
                        dcc.Graph(
                            id="failure-sunburst",
                            figure=_failure_sunburst(runs_df),
                        ),
                        width=6,
                    ),
                ],
                className="mb-4",
            ),
            # Failure reason explanations
            html.Div(
                [
                    html.H5("Failure Categories"),
                    html.Ul(failure_explanations)
                    if failure_explanations
                    else html.P(
                        "No failures detected.",
                        className="text-muted",
                    ),
                ],
                className="mt-3",
            )
            if failure_explanations
            else html.Div(),
        ]
    )
