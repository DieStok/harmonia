"""AG Grid configuration for the runs table."""

import dash_ag_grid as dag
from dash import html


def create_run_table(row_data: list[dict], table_id: str = "runs-table") -> html.Div:
    """Create an AG Grid table for experiment runs."""
    column_defs = [
        {"field": "run_id", "headerName": "Run ID", "width": 110, "pinned": "left"},
        {"field": "experiment_name", "headerName": "Experiment", "width": 200},
        {"field": "model", "headerName": "Model", "width": 180},
        {"field": "provider", "headerName": "Provider", "width": 120},
        {"field": "status", "headerName": "Status", "width": 100,
         "cellStyle": {"styleConditions": [
             {"condition": "params.value === 'completed'", "style": {"color": "#28a745"}},
             {"condition": "params.value === 'failed'", "style": {"color": "#dc3545"}},
             {"condition": "params.value === 'timeout'", "style": {"color": "#ffc107"}},
         ]}},
        {"field": "total_turns", "headerName": "Turns", "width": 80, "type": "numericColumn"},
        {"field": "total_duration", "headerName": "Duration (s)", "width": 110,
         "type": "numericColumn",
         "valueFormatter": {"function": "params.value ? params.value.toFixed(1) : ''"}},
        {"field": "total_input_tokens", "headerName": "Input Tokens", "width": 120,
         "type": "numericColumn",
         "valueFormatter": {"function": "params.value ? params.value.toLocaleString() : ''"}},
        {"field": "total_output_tokens", "headerName": "Output Tokens", "width": 120,
         "type": "numericColumn",
         "valueFormatter": {"function": "params.value ? params.value.toLocaleString() : ''"}},
        {"field": "total_cost_usd", "headerName": "Cost ($)", "width": 100,
         "type": "numericColumn",
         "valueFormatter": {"function": "params.value ? '$' + params.value.toFixed(4) : ''"}},
        {"field": "accuracy", "headerName": "Value Accuracy", "width": 130,
         "type": "numericColumn",
         "valueFormatter": {"function": "params.value != null ? (params.value * 100).toFixed(1) + '%' : 'N/A'"}},
        {"field": "column_mapping_accuracy", "headerName": "Mapping Accuracy", "width": 140,
         "type": "numericColumn",
         "valueFormatter": {"function": "params.value != null ? (params.value * 100).toFixed(1) + '%' : 'N/A'"}},
        {"field": "start_time", "headerName": "Start Time", "width": 180},
    ]

    default_col_def = {
        "sortable": True,
        "filter": True,
        "resizable": True,
    }

    grid = dag.AgGrid(
        id=table_id,
        rowData=row_data,
        columnDefs=column_defs,
        defaultColDef=default_col_def,
        dashGridOptions={
            "rowSelection": "single",
            "animateRows": True,
            "pagination": True,
            "paginationPageSize": 25,
        },
        style={"height": "500px"},
    )

    return html.Div(grid)
