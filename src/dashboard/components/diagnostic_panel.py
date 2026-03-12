"""Shared diagnostic panel component — collapsible details showing data sources and timing."""

import json

from dash import dcc, html


def create_diagnostic_panel(
    panel_id: str,
    source_files: list[str] | None = None,
    raw_data: dict | None = None,
    timing: dict | None = None,
    cache_info: dict | None = None,
    cli_command: str | None = None,
) -> html.Details:
    """Create a collapsible diagnostic information panel.

    Uses semantic HTML5 <details>/<summary> — zero callbacks needed.
    """
    children = []

    # Source files table
    if source_files:
        file_rows = [
            html.Tr([html.Td(f, style={"fontFamily": "monospace", "fontSize": "0.85rem"})])
            for f in source_files
        ]
        children.append(html.H6("Source Files", className="mt-2 mb-1"))
        children.append(
            html.Table(
                [html.Tbody(file_rows)],
                className="table table-sm table-borderless",
                style={"fontSize": "0.85rem"},
            )
        )

    # Timing table
    if timing:
        timing_rows = [
            html.Tr([
                html.Td(method, style={"fontFamily": "monospace"}),
                html.Td(f"{duration:.0f} ms"),
            ])
            for method, duration in timing.items()
        ]
        children.append(html.H6("Timing", className="mt-2 mb-1"))
        children.append(
            html.Table(
                [
                    html.Thead(html.Tr([html.Th("Method"), html.Th("Duration")])),
                    html.Tbody(timing_rows),
                ],
                className="table table-sm",
                style={"fontSize": "0.85rem"},
            )
        )

    # Cache status
    if cache_info:
        badges = []
        for name, count in cache_info.items():
            badges.append(
                html.Span(
                    f"{name}: {count}",
                    className="badge bg-secondary me-1",
                    style={"fontSize": "0.8rem"},
                )
            )
        children.append(html.H6("Cache", className="mt-2 mb-1"))
        children.append(html.Div(badges))

    # CLI command
    if cli_command:
        cmd_id = f"{panel_id}-cli"
        children.append(html.H6("CLI Command", className="mt-2 mb-1"))
        children.append(
            html.Div([
                html.Pre(
                    cli_command,
                    id=cmd_id,
                    style={
                        "backgroundColor": "#f8f9fa",
                        "padding": "8px",
                        "borderRadius": "4px",
                        "fontSize": "0.85rem",
                    },
                ),
                dcc.Clipboard(target_id=cmd_id, style={"position": "absolute", "top": 5, "right": 5}),
            ], style={"position": "relative"})
        )

    # Raw JSON sub-section
    if raw_data:
        json_id = f"{panel_id}-raw-json"
        children.append(
            html.Details([
                html.Summary(
                    "Raw JSON",
                    style={"cursor": "pointer", "color": "#6c757d", "fontSize": "0.85rem"},
                ),
                html.Div([
                    html.Pre(
                        json.dumps(raw_data, indent=2, default=str),
                        id=json_id,
                        style={
                            "maxHeight": "300px",
                            "overflow": "auto",
                            "backgroundColor": "#f8f9fa",
                            "padding": "8px",
                            "borderRadius": "4px",
                            "fontSize": "0.75rem",
                        },
                    ),
                    dcc.Clipboard(target_id=json_id, style={"position": "absolute", "top": 5, "right": 5}),
                ], style={"position": "relative"}),
            ], className="mt-2")
        )

    return html.Details(
        [
            html.Summary(
                "Diagnostic Information",
                style={"cursor": "pointer", "color": "#6c757d", "fontSize": "0.85rem"},
            ),
            html.Div(children, className="p-2"),
        ],
        className="mt-3 mb-2",
        id=panel_id,
    )
