"""Error Analysis tab — error breakdown stacked bars, error type pie, per-column error table."""

import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import dcc, html


def _error_breakdown_stacked(error_df) -> go.Figure:
    """Stacked bar chart: hallucinations / omissions / genuine errors per run."""
    fig = go.Figure()

    if error_df is None or len(error_df) == 0:
        fig.update_layout(template="plotly_white", title="Error Breakdown", height=400)
        return fig

    df = error_df.sort_values("total_errors", ascending=False).head(30)
    labels = df["display_label"].tolist()

    fig.add_trace(
        go.Bar(
            x=labels,
            y=df["total_hallucinations"],
            name="Hallucinations",
            marker_color="#e74c3c",
            text=df["total_hallucinations"],
            textposition="inside",
        )
    )
    fig.add_trace(
        go.Bar(
            x=labels,
            y=df["total_omissions"],
            name="Omissions",
            marker_color="#f39c12",
            text=df["total_omissions"],
            textposition="inside",
        )
    )
    fig.add_trace(
        go.Bar(
            x=labels,
            y=df["total_genuine"],
            name="Genuine Errors",
            marker_color="#8e44ad",
            text=df["total_genuine"],
            textposition="inside",
        )
    )

    fig.update_layout(
        template="plotly_white",
        title="Error Breakdown by Run",
        xaxis_title="",
        yaxis_title="Count",
        barmode="stack",
        height=450,
        xaxis_tickangle=-30,
    )

    return fig


def _error_type_pie(error_df) -> go.Figure:
    """Pie chart: aggregate error types across all runs."""
    fig = go.Figure()

    if error_df is None or len(error_df) == 0:
        fig.update_layout(template="plotly_white", title="Error Type Distribution", height=400)
        return fig

    totals = {
        "Hallucinations": int(error_df["total_hallucinations"].sum()),
        "Omissions": int(error_df["total_omissions"].sum()),
        "Genuine Errors": int(error_df["total_genuine"].sum()),
        "Whitespace Only": int(error_df["total_whitespace_only"].sum()),
        "Case Only": int(error_df["total_case_only"].sum()),
    }
    # Remove zeros
    totals = {k: v for k, v in totals.items() if v > 0}

    if not totals:
        fig.update_layout(template="plotly_white", title="No errors found", height=400)
        return fig

    colors = {
        "Hallucinations": "#e74c3c",
        "Omissions": "#f39c12",
        "Genuine Errors": "#8e44ad",
        "Whitespace Only": "#95a5a6",
        "Case Only": "#bdc3c7",
    }

    fig.add_trace(
        go.Pie(
            labels=list(totals.keys()),
            values=list(totals.values()),
            marker_colors=[colors.get(k, "#333") for k in totals],
            textinfo="label+percent+value",
            hole=0.3,
        )
    )

    fig.update_layout(
        template="plotly_white",
        title="Aggregate Error Type Distribution",
        height=400,
    )

    return fig


def render_error_analysis(data_loader, selected_run_ids: list[str] | None = None) -> html.Div:
    """Render the Error Analysis tab."""
    error_df = data_loader.get_error_breakdown()
    column_errors_df = data_loader.get_column_errors()
    if selected_run_ids:
        if not error_df.empty and "run_id" in error_df.columns:
            error_df = error_df[error_df["run_id"].isin(selected_run_ids)].reset_index(drop=True)
        if not column_errors_df.empty and "run_id" in column_errors_df.columns:
            column_errors_df = column_errors_df[column_errors_df["run_id"].isin(selected_run_ids)].reset_index(drop=True)

    if (error_df is None or len(error_df) == 0) and (
        column_errors_df is None or len(column_errors_df) == 0
    ):
        return html.Div(
            [
                dbc.Button(
                    "Refresh Data",
                    id="refresh-error-analysis",
                    color="primary",
                    size="sm",
                    className="mb-3",
                ),
                html.P(
                    "No error data available. Run experiments with evaluation enabled.",
                    className="text-muted text-center my-5",
                ),
            ]
        )

    components = [
        dbc.Button(
            "Refresh Data",
            id="refresh-error-analysis",
            color="primary",
            size="sm",
            className="mb-3",
        ),
    ]

    # Error breakdown stacked bars + pie chart
    if error_df is not None and len(error_df) > 0:
        components.append(
            dbc.Row(
                [
                    dbc.Col(
                        dcc.Graph(
                            id="error-breakdown-stacked",
                            figure=_error_breakdown_stacked(error_df),
                        ),
                        width=7,
                    ),
                    dbc.Col(
                        dcc.Graph(
                            id="error-type-pie",
                            figure=_error_type_pie(error_df),
                        ),
                        width=5,
                    ),
                ],
                className="mb-4",
            )
        )

    # Per-column error table
    if column_errors_df is not None and len(column_errors_df) > 0:
        components.append(html.H5("Per-Column Error Counts", className="mt-4"))
        components.append(
            dag.AgGrid(
                id="column-errors-table",
                rowData=column_errors_df.to_dict("records"),
                columnDefs=[
                    {"field": "run_id", "headerName": "Run ID", "width": 100},
                    {"field": "model", "headerName": "Model", "width": 150},
                    {"field": "column_name", "headerName": "Column", "width": 150},
                    {
                        "field": "hallucinations",
                        "headerName": "Hallucinations",
                        "width": 120,
                        "type": "numericColumn",
                    },
                    {
                        "field": "omissions",
                        "headerName": "Omissions",
                        "width": 100,
                        "type": "numericColumn",
                    },
                    {
                        "field": "genuine_errors",
                        "headerName": "Genuine",
                        "width": 100,
                        "type": "numericColumn",
                    },
                    {
                        "field": "whitespace_errors",
                        "headerName": "Whitespace",
                        "width": 100,
                        "type": "numericColumn",
                    },
                    {
                        "field": "case_errors",
                        "headerName": "Case",
                        "width": 80,
                        "type": "numericColumn",
                    },
                    {
                        "field": "total_errors",
                        "headerName": "Total",
                        "width": 80,
                        "type": "numericColumn",
                    },
                ],
                defaultColDef={"sortable": True, "filter": True, "resizable": True},
                dashGridOptions={"pagination": True, "paginationPageSize": 25},
                style={"height": "500px"},
            )
        )

    return html.Div(components)
