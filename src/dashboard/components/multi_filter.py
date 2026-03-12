"""Multi-filter widget — stackable column filters with AND logic.

Uses pattern-matching callbacks with dict IDs and Patch() for partial updates.
"""

import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, Patch, State, ctx, dcc, html


def _make_filter_row(index: int, columns: list[str]) -> html.Div:
    """Create a single filter row with column, operator, value, and remove button."""
    return html.Div(
        dbc.Row(
            [
                dbc.Col(
                    dcc.Dropdown(
                        id={"type": "filter-column", "index": index},
                        options=[{"label": c, "value": c} for c in columns],
                        placeholder="Column...",
                        clearable=False,
                        style={"fontSize": "0.85rem"},
                    ),
                    width=3,
                ),
                dbc.Col(
                    dcc.Dropdown(
                        id={"type": "filter-operator", "index": index},
                        options=[
                            {"label": "contains", "value": "contains"},
                            {"label": "does not contain", "value": "not_contains"},
                            {"label": "equals", "value": "equals"},
                            {"label": "not equals", "value": "not_equals"},
                        ],
                        value="contains",
                        clearable=False,
                        style={"fontSize": "0.85rem"},
                    ),
                    width=3,
                ),
                dbc.Col(
                    dbc.Input(
                        id={"type": "filter-value", "index": index},
                        placeholder="Value...",
                        type="text",
                        size="sm",
                    ),
                    width=4,
                ),
                dbc.Col(
                    dbc.Button(
                        "×",
                        id={"type": "filter-remove", "index": index},
                        color="danger",
                        outline=True,
                        size="sm",
                    ),
                    width=2,
                ),
            ],
            className="mb-1 g-1",
        ),
        id={"type": "filter-row", "index": index},
    )


def create_multi_filter(filter_id: str, columns: list[str]) -> html.Div:
    """Create a multi-filter widget.

    Parameters
    ----------
    filter_id : str
        Base ID for the filter widget. Used to namespace sub-component IDs.
    columns : list[str]
        Column names available for filtering.
    """
    return html.Div(
        [
            html.Div(id=f"{filter_id}-rows"),
            dbc.Button(
                "+ Add Filter",
                id=f"{filter_id}-add",
                color="secondary",
                outline=True,
                size="sm",
                className="mt-1",
            ),
            dcc.Store(id=f"{filter_id}-next-index", data=0),
            dcc.Store(id=f"{filter_id}-columns", data=columns),
        ],
        id=filter_id,
    )


def register_multi_filter_callbacks(app, filter_id: str):
    """Register the pattern-matching callbacks for a multi-filter widget.

    Must be called at app startup (not inside a layout function).
    """

    @app.callback(
        Output(f"{filter_id}-rows", "children", allow_duplicate=True),
        Output(f"{filter_id}-next-index", "data", allow_duplicate=True),
        Input(f"{filter_id}-add", "n_clicks"),
        State(f"{filter_id}-next-index", "data"),
        State(f"{filter_id}-columns", "data"),
        prevent_initial_call=True,
    )
    def add_filter_row(n_clicks, next_index, columns):
        patched = Patch()
        patched.append(_make_filter_row(next_index, columns))
        return patched, next_index + 1

    @app.callback(
        Output(f"{filter_id}-rows", "children", allow_duplicate=True),
        Input({"type": "filter-remove", "index": ALL}, "n_clicks"),
        State(f"{filter_id}-rows", "children"),
        prevent_initial_call=True,
    )
    def remove_filter_row(n_clicks_list, current_children):
        if not ctx.triggered_id or not any(n_clicks_list):
            from dash.exceptions import PreventUpdate

            raise PreventUpdate
        remove_index = ctx.triggered_id["index"]
        patched = Patch()
        # Find position of the row with this index
        if current_children:
            for pos, child in enumerate(current_children):
                if child and child.get("props", {}).get("id", {}).get("index") == remove_index:
                    del patched[pos]
                    return patched
        return patched

    @app.callback(
        Output("active-filters-store", "data", allow_duplicate=True),
        Input({"type": "filter-column", "index": ALL}, "value"),
        Input({"type": "filter-operator", "index": ALL}, "value"),
        Input({"type": "filter-value", "index": ALL}, "value"),
        prevent_initial_call=True,
    )
    def collect_filters(columns, operators, values):
        filters = []
        for col, op, val in zip(columns, operators, values):
            if col and val:
                filters.append({"column": col, "operator": op, "value": val})
        return filters
