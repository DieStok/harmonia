"""AG Grid configuration for the runs table."""

import dash_ag_grid as dag
from dash import html
from evaluation.visualization.enrich import infer_context


def create_run_table(
    row_data: list[dict],
    table_id: str = "runs-table",
    selection_mode: str = "multiple",
) -> html.Div:
    """Create an AG Grid table for experiment runs.

    Parameters
    ----------
    row_data : list[dict]
        Row data for the grid.
    table_id : str
        HTML id for the grid component.
    selection_mode : str
        "multiple" for checkbox multi-select (default), "single" for legacy behavior.
    """
    # Enrich rows with context column if missing
    for row in row_data:
        if "context" not in row:
            row["context"] = infer_context(row.get("experiment_name", ""))

    column_defs = [
        {"field": "run_id", "headerName": "Run ID", "width": 110, "pinned": "left"},
        {"field": "experiment_name", "headerName": "Experiment", "width": 200},
        {"field": "model", "headerName": "Model", "width": 180},
        {"field": "context", "headerName": "Context", "width": 120},
        {"field": "provider", "headerName": "Provider", "width": 120},
        {
            "field": "status",
            "headerName": "Status",
            "width": 100,
            "cellStyle": {
                "styleConditions": [
                    {"condition": "params.value === 'completed'", "style": {"color": "#28a745"}},
                    {"condition": "params.value === 'failed'", "style": {"color": "#dc3545"}},
                    {"condition": "params.value === 'timeout'", "style": {"color": "#ffc107"}},
                ]
            },
        },
        {"field": "total_turns", "headerName": "Turns", "width": 80, "type": "numericColumn"},
        {
            "field": "total_duration",
            "headerName": "Duration (s)",
            "width": 110,
            "type": "numericColumn",
            "valueFormatter": {"function": "params.value ? params.value.toFixed(1) : ''"},
        },
        {
            "field": "total_input_tokens",
            "headerName": "Input Tokens",
            "width": 120,
            "type": "numericColumn",
            "valueFormatter": {"function": "params.value ? params.value.toLocaleString() : ''"},
        },
        {
            "field": "total_output_tokens",
            "headerName": "Output Tokens",
            "width": 120,
            "type": "numericColumn",
            "valueFormatter": {"function": "params.value ? params.value.toLocaleString() : ''"},
        },
        {
            "field": "total_cost_usd",
            "headerName": "Cost ($)",
            "width": 100,
            "type": "numericColumn",
            "valueFormatter": {"function": "params.value ? '$' + params.value.toFixed(4) : ''"},
        },
        {
            "field": "accuracy",
            "headerName": "Value Accuracy",
            "width": 130,
            "type": "numericColumn",
            "valueFormatter": {
                "function": "params.value != null ? (params.value * 100).toFixed(1) + '%' : 'N/A'"
            },
        },
        {
            "field": "column_mapping_accuracy",
            "headerName": "Mapping Accuracy",
            "width": 140,
            "type": "numericColumn",
            "valueFormatter": {
                "function": "params.value != null ? (params.value * 100).toFixed(1) + '%' : 'N/A'"
            },
        },
        {
            "field": "start_time",
            "headerName": "Start Time",
            "width": 180,
            "sort": "desc",
            "sortIndex": 0,
        },
        # Hidden columns for diagnostic transparency
        {"field": "config_path", "headerName": "Config Path", "hide": True},
        {"field": "results_dir", "headerName": "Results Dir", "hide": True},
    ]

    default_col_def = {
        "sortable": True,
        "filter": True,
        "resizable": True,
    }

    # AG Grid v31 selection API
    if selection_mode == "multiple":
        row_selection = {
            "mode": "multiRow",
            "checkboxes": True,
            "headerCheckbox": True,
            "selectAll": "filtered",
            "enableClickSelection": True,
        }
    else:
        row_selection = {"mode": "singleRow", "enableClickSelection": True}

    grid = dag.AgGrid(
        id=table_id,
        rowData=row_data,
        columnDefs=column_defs,
        defaultColDef=default_col_def,
        getRowId="params.data.run_id",
        dashGridOptions={
            "rowSelection": row_selection,
            "pagination": True,
            "paginationPageSize": 100,
            "paginationPageSizeSelector": [50, 100, 200, 500],
            "animateRows": False,
        },
        style={"height": "calc(100vh - 350px)", "minHeight": "400px"},
    )

    return html.Div(grid)
