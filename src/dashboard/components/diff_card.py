"""Summary diff card for side-by-side comparison."""

import dash_bootstrap_components as dbc
from dash import html


def _delta_badge(label: str, val_a, val_b, fmt: str = ".2f", higher_is_better: bool = True) -> dbc.Col:
    """Create a column showing the delta between two values."""
    if val_a is None or val_b is None:
        return dbc.Col([
            html.Small(label, className="text-muted d-block"),
            html.Span("N/A", className="text-muted"),
        ], width=True)

    delta = val_b - val_a
    if delta == 0:
        arrow = "="
        color = "secondary"
    elif (delta > 0) == higher_is_better:
        arrow = "▲"
        color = "success"
    else:
        arrow = "▼"
        color = "danger"

    return dbc.Col([
        html.Small(label, className="text-muted d-block"),
        html.Span([
            f"A: {val_a:{fmt}} → B: {val_b:{fmt}} ",
            dbc.Badge(f"{arrow} {delta:+{fmt}}", color=color),
        ]),
    ], width=True)


def create_diff_card(run_a: dict, run_b: dict) -> dbc.Card:
    """
    Create a summary diff card comparing two runs.

    Args:
        run_a: Metadata dict for run A (from get_all_runs row or trace/metrics)
        run_b: Metadata dict for run B
    """
    return dbc.Card([
        dbc.CardHeader(html.H5("Comparison Summary", className="mb-0")),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Strong("Run A: "),
                    html.Span(f"{run_a.get('run_id', '?')} — {run_a.get('model', '?')}"),
                ], width=6),
                dbc.Col([
                    html.Strong("Run B: "),
                    html.Span(f"{run_b.get('run_id', '?')} — {run_b.get('model', '?')}"),
                ], width=6),
            ], className="mb-3"),
            dbc.Row([
                _delta_badge("Value Accuracy", run_a.get("accuracy"), run_b.get("accuracy"),
                             fmt=".3f", higher_is_better=True),
                _delta_badge("Mapping Accuracy", run_a.get("column_mapping_accuracy"),
                             run_b.get("column_mapping_accuracy"), fmt=".3f", higher_is_better=True),
                _delta_badge("Total Tokens",
                             (run_a.get("total_input_tokens", 0) or 0) + (run_a.get("total_output_tokens", 0) or 0),
                             (run_b.get("total_input_tokens", 0) or 0) + (run_b.get("total_output_tokens", 0) or 0),
                             fmt=",.0f", higher_is_better=False),
                _delta_badge("Cost ($)", run_a.get("total_cost_usd"), run_b.get("total_cost_usd"),
                             fmt=".4f", higher_is_better=False),
                _delta_badge("Turns", run_a.get("total_turns"), run_b.get("total_turns"),
                             fmt=".0f", higher_is_better=False),
                _delta_badge("Duration (s)", run_a.get("total_duration"), run_b.get("total_duration"),
                             fmt=".1f", higher_is_better=False),
            ]),
        ]),
    ], className="mb-3")
