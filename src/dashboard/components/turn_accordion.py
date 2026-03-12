"""Accordion component for conversation turns."""

import dash_bootstrap_components as dbc
from dash import dcc, html

TURNS_PER_PAGE = 20


def _format_code_block(code: str, language: str = "python") -> html.Div:
    """Render a code block with syntax highlighting via Markdown."""
    return dcc.Markdown(
        f"```{language}\n{code}\n```",
        style={"backgroundColor": "#f5f5f5", "padding": "8px", "borderRadius": "4px"},
    )


def _build_turn_item(turn: dict, idx: int) -> dbc.AccordionItem:
    """Build a single accordion item for a turn."""
    turn_num = turn.get("turn", idx + 1)
    response_type = turn.get("response_type", "")
    input_tokens = turn.get("input_tokens", 0)
    output_tokens = turn.get("output_tokens", 0)
    cost = turn.get("cost_usd", 0)
    duration = turn.get("duration_seconds", 0)

    # Badge for response type
    badge_color = "primary"
    if response_type == "code_cell":
        badge_color = "success"
    elif response_type == "error":
        badge_color = "danger"

    # Header with key stats
    title = html.Span(
        [
            f"Turn {turn_num} ",
            dbc.Badge(response_type, color=badge_color, className="me-2"),
            dbc.Badge(f"{input_tokens + output_tokens} tokens", color="info", className="me-1"),
            dbc.Badge(f"${cost:.4f}", color="warning", className="me-1")
            if cost > 0
            else html.Span(),
            dbc.Badge(f"{duration:.1f}s", color="secondary") if duration > 0 else html.Span(),
        ]
    )

    # Content
    children = []

    # User message
    user_msg = turn.get("user_message", "")
    if user_msg:
        children.append(html.H6("User Message", className="text-muted mt-2"))
        children.append(
            html.Div(
                dcc.Markdown(user_msg[:2000] + ("..." if len(user_msg) > 2000 else "")),
                style={
                    "backgroundColor": "#e3f2fd",
                    "padding": "10px",
                    "borderRadius": "4px",
                    "marginBottom": "10px",
                },
            )
        )

    # Agent response
    agent_resp = turn.get("agent_response", "")
    if agent_resp:
        children.append(html.H6("Agent Response", className="text-muted"))
        if response_type == "code_cell":
            children.append(_format_code_block(agent_resp[:3000]))
        else:
            children.append(
                html.Div(
                    dcc.Markdown(agent_resp[:3000] + ("..." if len(agent_resp) > 3000 else "")),
                    style={
                        "backgroundColor": "#f1f8e9",
                        "padding": "10px",
                        "borderRadius": "4px",
                        "marginBottom": "10px",
                    },
                )
            )

    # Agent code executions (shown by default)
    # Backward-compatible: fall back to old "code_executions" field for un-migrated traces
    agent_execs = turn.get("agent_code_executions", turn.get("code_executions", []))
    if agent_execs:
        children.append(html.H6(f"Code Executions ({len(agent_execs)})", className="text-muted mt-2"))
        for j, ce in enumerate(agent_execs[:5]):  # Limit display
            children.append(html.Strong(f"Execution {j+1} [{ce.get('status', '?')}]"))
            if ce.get("code"):
                children.append(_format_code_block(ce["code"][:1000]))
            if ce.get("stdout"):
                children.append(
                    html.Pre(
                        ce["stdout"][:500],
                        style={
                            "fontSize": "0.85em",
                            "backgroundColor": "#fff3e0",
                            "padding": "6px",
                        },
                    )
                )
            if ce.get("stderr"):
                children.append(
                    html.Pre(
                        ce["stderr"][:500],
                        style={
                            "fontSize": "0.85em",
                            "backgroundColor": "#ffebee",
                            "padding": "6px",
                            "color": "#c62828",
                        },
                    )
                )

    # Internal executions (collapsible, hidden by default)
    internal_execs = turn.get("internal_code_executions", [])
    if internal_execs:
        internal_children = []
        for j, ce in enumerate(internal_execs[:5]):
            category = ce.get("category", "unknown")
            internal_children.append(html.Strong(f"{category} [{ce.get('status', '?')}]"))
            if ce.get("code"):
                internal_children.append(_format_code_block(ce["code"][:500]))
        children.append(html.Details([
            html.Summary(
                f"Internal Executions ({len(internal_execs)})",
                style={"fontSize": "0.85em", "color": "#999", "cursor": "pointer"},
            ),
            html.Div(internal_children),
        ], style={"marginTop": "8px"}))

    # Token details row
    children.append(html.Hr())
    children.append(
        dbc.Row(
            [
                dbc.Col(html.Small(f"Input: {input_tokens:,} tokens"), width=3),
                dbc.Col(html.Small(f"Output: {output_tokens:,} tokens"), width=3),
                dbc.Col(html.Small(f"Cost: ${cost:.4f}"), width=3),
                dbc.Col(html.Small(f"Duration: {duration:.1f}s"), width=3),
            ]
        )
    )

    return dbc.AccordionItem(children, title=title, item_id=f"turn-{turn_num}")


def create_turn_accordion(
    turns: list[dict],
    page: int = 0,
    accordion_id: str = "turn-accordion",
) -> html.Div:
    """
    Create an accordion showing conversation turns with pagination.

    Args:
        turns: List of turn dicts from trace.json
        page: Current page (0-indexed)
        accordion_id: Component ID for callbacks
    """
    if not turns:
        return html.Div(
            html.P("No conversation turns available.", className="text-muted text-center my-4"),
        )

    total_pages = max(1, (len(turns) + TURNS_PER_PAGE - 1) // TURNS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    start = page * TURNS_PER_PAGE
    end = min(start + TURNS_PER_PAGE, len(turns))
    page_turns = turns[start:end]

    items = [_build_turn_item(t, start + i) for i, t in enumerate(page_turns)]

    components = [
        dbc.Accordion(items, id=accordion_id, start_collapsed=True),
    ]

    # Pagination controls (only if needed)
    if total_pages > 1:
        components.append(
            html.Div(
                [
                    dbc.ButtonGroup(
                        [
                            dbc.Button(
                                "Previous",
                                id=f"{accordion_id}-prev",
                                color="secondary",
                                size="sm",
                                disabled=(page == 0),
                            ),
                            html.Span(
                                f" Page {page + 1} / {total_pages} ",
                                className="mx-2 align-self-center",
                            ),
                            dbc.Button(
                                "Next",
                                id=f"{accordion_id}-next",
                                color="secondary",
                                size="sm",
                                disabled=(page >= total_pages - 1),
                            ),
                        ],
                        className="mt-2",
                    ),
                    html.Small(
                        f"Showing turns {start + 1}-{end} of {len(turns)}",
                        className="text-muted ms-2",
                    ),
                ],
                className="d-flex align-items-center mt-2",
            )
        )

    return html.Div(components)
