"""Plotly Gantt-style chart for span hierarchy visualization."""

import pandas as pd
import plotly.graph_objects as go

# Color map for span kinds
SPAN_KIND_COLORS = {
    "AGENT": "#2196F3",   # blue
    "CHAIN": "#4CAF50",   # green
    "LLM": "#FF9800",     # orange
    "TOOL": "#9C27B0",    # purple
}


def create_span_waterfall(spans_df: pd.DataFrame) -> go.Figure:
    """
    Create a Gantt-style waterfall chart from Phoenix span data.

    Args:
        spans_df: DataFrame with span data from Phoenix.
                  Expected columns: name, start_time, end_time,
                  and optionally span_kind or attributes.openinference.span.kind.

    Returns:
        Plotly Figure with horizontal bar chart showing span hierarchy.
    """
    if spans_df is None or len(spans_df) == 0:
        fig = go.Figure()
        fig.update_layout(
            template="plotly_white",
            title="No span data available",
            height=200,
        )
        return fig

    # Try to find relevant columns
    df = spans_df.copy()

    # Determine span kind column
    kind_col = None
    for candidate in ["span_kind", "attributes.openinference.span.kind"]:
        if candidate in df.columns:
            kind_col = candidate
            break

    # Determine time columns
    start_col = None
    end_col = None
    for s_candidate in ["start_time", "start_nano"]:
        if s_candidate in df.columns:
            start_col = s_candidate
            break
    for e_candidate in ["end_time", "end_nano"]:
        if e_candidate in df.columns:
            end_col = e_candidate
            break

    if start_col is None or end_col is None:
        fig = go.Figure()
        fig.update_layout(
            template="plotly_white",
            title="Span data missing time columns",
            height=200,
        )
        return fig

    # Ensure datetime
    df[start_col] = pd.to_datetime(df[start_col], errors="coerce")
    df[end_col] = pd.to_datetime(df[end_col], errors="coerce")
    df = df.dropna(subset=[start_col, end_col])

    if len(df) == 0:
        fig = go.Figure()
        fig.update_layout(template="plotly_white", title="No valid span times", height=200)
        return fig

    # Sort by start time
    df = df.sort_values(start_col).reset_index(drop=True)

    # Build bars
    fig = go.Figure()

    for i, row in df.iterrows():
        kind = str(row.get(kind_col, "UNKNOWN")).upper() if kind_col else "UNKNOWN"
        color = SPAN_KIND_COLORS.get(kind, "#607D8B")
        name = str(row.get("name", f"span-{i}"))
        start = row[start_col]
        end = row[end_col]
        duration_ms = (end - start).total_seconds() * 1000

        fig.add_trace(go.Bar(
            y=[name],
            x=[duration_ms],
            base=[(start - df[start_col].min()).total_seconds() * 1000],
            orientation="h",
            marker_color=color,
            name=kind,
            showlegend=False,
            hovertemplate=(
                f"<b>{name}</b><br>"
                f"Kind: {kind}<br>"
                f"Duration: {duration_ms:.1f}ms<br>"
                "<extra></extra>"
            ),
        ))

    # Add legend entries for span kinds
    for kind, color in SPAN_KIND_COLORS.items():
        fig.add_trace(go.Bar(
            y=[None], x=[None], orientation="h",
            marker_color=color, name=kind,
            showlegend=True,
        ))

    fig.update_layout(
        template="plotly_white",
        title="Span Waterfall",
        xaxis_title="Time (ms from start)",
        yaxis=dict(autorange="reversed"),
        barmode="overlay",
        height=max(300, len(df) * 30 + 100),
        margin=dict(l=200),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )

    return fig
