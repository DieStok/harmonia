from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SEABORN_READY = True
PLOTLY_READY = True
try:
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt
    import seaborn as sns
except Exception:
    SEABORN_READY = False

try:
    import plotly.express as px
    import plotly.graph_objects as go
except Exception:
    PLOTLY_READY = False


def _require_backend(backend: str):
    if backend == "seaborn" and not SEABORN_READY:
        raise RuntimeError("seaborn/matplotlib not available")
    if backend == "plotly" and not PLOTLY_READY:
        raise RuntimeError("plotly not available")


def save_figure(fig, out_path: Path, backend: str, figure_format: str = "png", dpi: int = 160):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if backend == "seaborn":
        fig.savefig(out_path.with_suffix(f".{figure_format}"), dpi=dpi, bbox_inches="tight")
        plt.close(fig)
    else:
        if figure_format == "html":
            fig.write_html(str(out_path.with_suffix(".html")), include_plotlyjs="cdn")
        else:
            try:
                fig.write_image(str(out_path.with_suffix(f".{figure_format}")))
            except Exception:
                fig.write_html(str(out_path.with_suffix(".html")), include_plotlyjs="cdn")


def plot_global_bars(df: pd.DataFrame, metric: str, x_col: str = "display_label", hue_col: str | None = "context", backend: str = "seaborn", title: str | None = None, palette: str = "tab10"):
    _require_backend(backend)
    data = df.dropna(subset=[metric]).copy()
    if backend == "seaborn":
        sns.set_theme(style="whitegrid")
        fig, ax = plt.subplots(figsize=(12, 6))
        sns.barplot(data=data, x=x_col, y=metric, hue=hue_col if hue_col in data.columns else None, ax=ax, palette=palette)
        ax.set_xticklabels(ax.get_xticklabels(), rotation=35, ha="right")
        ax.set_ylim(0, max(1.0, float(data[metric].max()) * 1.1))
        ax.set_title(title or metric)
        return fig

    fig = px.bar(
        data,
        x=x_col,
        y=metric,
        color=hue_col if hue_col in data.columns else None,
        title=title or metric,
        hover_data=[c for c in ["model_label", "context", "model_family", "run_id", "experiment_name"] if c in data.columns],
    )
    fig.update_layout(xaxis_tickangle=-35)
    return fig


def plot_heatmap(matrix_df: pd.DataFrame, backend: str = "seaborn", title: str | None = None):
    _require_backend(backend)
    if backend == "seaborn":
        sns.set_theme(style="white")
        fig, ax = plt.subplots(figsize=(max(10, matrix_df.shape[1] * 0.8), max(4, matrix_df.shape[0] * 0.6)))
        sns.heatmap(matrix_df, cmap="viridis", vmin=0, vmax=1, linewidths=0.3, linecolor="white", ax=ax)
        ax.set_title(title or "Per-column performance heatmap")
        ax.set_xlabel("Column")
        ax.set_ylabel("Run")
        return fig

    fig = px.imshow(
        matrix_df,
        color_continuous_scale="Viridis",
        zmin=0,
        zmax=1,
        title=title or "Per-column performance heatmap",
        aspect="auto",
    )
    fig.update_xaxes(side="bottom")
    return fig


def plot_boxplot(df: pd.DataFrame, metric: str, group_col: str = "model_family_group", hue_col: str | None = None, backend: str = "seaborn", title: str | None = None, palette: str = "tab10"):
    _require_backend(backend)
    data = df.dropna(subset=[metric]).copy()
    if backend == "seaborn":
        sns.set_theme(style="whitegrid")
        fig, ax = plt.subplots(figsize=(12, 6))
        sns.boxplot(
            data=data,
            x=group_col,
            y=metric,
            hue=hue_col if hue_col and hue_col in data.columns else None,
            ax=ax,
            palette=palette,
        )
        ax.set_xticklabels(ax.get_xticklabels(), rotation=35, ha="right")
        ax.set_ylim(0, max(1.0, float(data[metric].max()) * 1.1))
        ax.set_title(title or f"{metric} by {group_col}")
        return fig

    fig = px.box(
        data,
        x=group_col,
        y=metric,
        color=hue_col if hue_col and hue_col in data.columns else None,
        title=title or f"{metric} by {group_col}",
        hover_data=[c for c in ["model_label", "context", "model_family", "run_id"] if c in data.columns],
    )
    fig.update_layout(xaxis_tickangle=-35)
    return fig


def plot_success_failure_heatmap(
    all_runs_df: pd.DataFrame,
    row_col: str = "model",
    col_col: str = "context",
    backend: str = "seaborn",
    title: str | None = None,
):
    """Success/failure grid heatmap (model x context).

    Expects ``all_runs_df`` to have columns: ``row_col``, ``col_col``,
    ``has_output`` (bool), and optionally ``failure_reason``,
    ``column_mapping_accuracy``, ``avg_value_accuracy_excl_empty``, ``run_id``.
    """
    _require_backend(backend)
    df = all_runs_df.copy()

    row_labels = sorted(df[row_col].unique())
    col_labels = sorted(df[col_col].unique())

    # Build pivot grid (1=success, 0=fail, NaN=missing)
    grid = df.pivot_table(
        index=row_col, columns=col_col, values="has_output",
        aggfunc="first",
    ).reindex(index=row_labels, columns=col_labels).astype(float)

    if backend == "seaborn":
        # Build annotation matrix
        annot_rows = []
        for model in row_labels:
            row = []
            for ctx in col_labels:
                val = grid.loc[model, ctx] if model in grid.index and ctx in grid.columns else np.nan
                if val == 1.0:
                    row.append("OK")
                elif val == 0.0:
                    match = df[(df[row_col] == model) & (df[col_col] == ctx)]
                    reason = match.iloc[0].get("failure_reason", "N/A") if not match.empty else "N/A"
                    short = (reason[:20] + "...") if reason and len(str(reason)) > 20 else (str(reason) if reason else "N/A")
                    row.append(short)
                else:
                    row.append("N/A")
            annot_rows.append(row)

        annot_df = pd.DataFrame(annot_rows, index=row_labels, columns=col_labels)

        sns.set_theme(style="white", font_scale=1.1)
        fig, ax = plt.subplots(figsize=(max(8, len(col_labels) * 2.5), max(4, len(row_labels) * 0.9)))
        cmap = sns.color_palette(["#ffc7ce", "#c6efce"])
        sns.heatmap(
            grid.fillna(-1), annot=annot_df, fmt="", cmap=cmap,
            linewidths=2, linecolor="white", cbar=False, ax=ax,
            vmin=0, vmax=1,
        )
        n_ok = int((grid == 1.0).sum().sum())
        n_total = int(grid.notna().sum().sum())
        ax.set_title(title or f"Run Success/Failure Grid ({n_ok}/{n_total} successful)")
        ax.set_ylabel(row_col.replace("_", " ").title())
        ax.set_xlabel(col_col.replace("_", " ").title())
        return fig

    # Plotly
    z_data, hover_data = [], []
    for model in row_labels:
        z_row, hover_row = [], []
        for ctx in col_labels:
            match = df[(df[row_col] == model) & (df[col_col] == ctx)]
            if match.empty:
                z_row.append(np.nan)
                hover_row.append("No data")
                continue
            r = match.iloc[0]
            if r.get("has_output"):
                z_row.append(1)
                cm = r.get("column_mapping_accuracy")
                va = r.get("avg_value_accuracy_excl_empty")
                cm_s = f"{cm:.3f}" if pd.notna(cm) else "N/A"
                va_s = f"{va:.3f}" if pd.notna(va) else "N/A"
                hover_row.append(
                    f"<b>{model} / {ctx}</b><br>"
                    f"Status: Success<br>"
                    f"Run ID: {r.get('run_id', 'N/A')}<br>"
                    f"Col Mapping: {cm_s}<br>"
                    f"Value Acc: {va_s}"
                )
            else:
                z_row.append(0)
                hover_row.append(
                    f"<b>{model} / {ctx}</b><br>"
                    f"Status: FAILED<br>"
                    f"Reason: {r.get('failure_reason', 'Unknown')}<br>"
                    f"Run ID: {r.get('run_id', 'N/A')}"
                )
        z_data.append(z_row)
        hover_data.append(hover_row)

    fig = go.Figure(data=go.Heatmap(
        z=z_data, x=col_labels, y=row_labels,
        hovertext=hover_data, hoverinfo="text",
        colorscale=[[0, "#ffc7ce"], [0.5, "#ffe8a1"], [1, "#c6efce"]],
        zmin=0, zmax=1, showscale=False,
        text=[["FAIL" if v == 0 else ("OK" if v == 1 else "") for v in row] for row in z_data],
        texttemplate="%{text}", textfont={"size": 14},
    ))
    n_ok = sum(1 for row in z_data for v in row if v == 1)
    n_total = sum(1 for row in z_data for v in row if not (isinstance(v, float) and np.isnan(v)))
    fig.update_layout(
        title=title or f"Run Success/Failure Grid ({n_ok}/{n_total} successful)",
        xaxis_title=col_col.replace("_", " ").title(),
        yaxis_title=row_col.replace("_", " ").title(),
        height=max(350, len(row_labels) * 55 + 120),
        template="plotly_white",
        yaxis=dict(autorange="reversed"),
    )
    return fig


def plot_failure_distribution(
    all_runs_df: pd.DataFrame,
    backend: str = "seaborn",
    title: str | None = None,
):
    """Horizontal bar chart of failure reason counts.

    Expects ``all_runs_df`` with ``has_output`` and ``failure_reason`` columns.
    """
    _require_backend(backend)

    failed = all_runs_df[~all_runs_df["has_output"].astype(bool)].copy()
    if failed.empty:
        raise ValueError("No failed runs to plot")

    counts = failed["failure_reason"].value_counts().reset_index()
    counts.columns = ["failure_reason", "count"]

    n_fail = len(failed)
    n_total = len(all_runs_df)
    default_title = f"Failure Mode Distribution ({n_fail}/{n_total} failed)"

    if backend == "seaborn":
        sns.set_theme(style="whitegrid", font_scale=1.1)
        fig, ax = plt.subplots(figsize=(10, max(3, len(counts) * 0.8 + 1)))
        colors = sns.color_palette("Reds_r", n_colors=len(counts))
        sns.barplot(data=counts, x="count", y="failure_reason", palette=colors,
                    ax=ax, edgecolor="white")
        ax.set_xlabel("Number of Runs")
        ax.set_ylabel("")
        ax.set_title(title or default_title)
        for container in ax.containers:
            ax.bar_label(container, fmt="%d", fontsize=11, padding=5)
        ax.set_xlim(0, counts["count"].max() + 1.5)
        return fig

    fig = px.bar(
        counts, x="count", y="failure_reason", orientation="h",
        title=title or default_title,
        labels={"count": "Number of Runs", "failure_reason": ""},
        color="failure_reason",
        color_discrete_sequence=px.colors.qualitative.Set1,
        text="count",
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(
        showlegend=False,
        height=max(300, len(counts) * 50 + 100),
        template="plotly_white",
        xaxis_range=[0, counts["count"].max() + 1.5],
    )
    return fig


def plot_failure_sunburst(
    all_runs_df: pd.DataFrame,
    backend: str = "seaborn",
    title: str | None = None,
    row_col: str = "model",
    col_col: str = "context",
):
    """Sunburst (plotly) or grouped bar (seaborn) of failure breakdown.

    Hierarchy: failure_reason -> model -> context.
    """
    _require_backend(backend)

    failed = all_runs_df[~all_runs_df["has_output"].astype(bool)].copy()
    if failed.empty:
        raise ValueError("No failed runs to plot")

    n_fail = len(failed)
    default_title = f"Failure Mode Breakdown ({n_fail} failed runs)"

    if backend == "seaborn":
        # Sunburst not available in seaborn; use grouped bar instead
        counts = (
            failed.groupby(["failure_reason", row_col])
            .size()
            .reset_index(name="count")
        )
        sns.set_theme(style="whitegrid")
        fig, ax = plt.subplots(figsize=(10, max(4, len(counts) * 0.5 + 2)))
        sns.barplot(data=counts, x="count", y="failure_reason", hue=row_col,
                    ax=ax, edgecolor="white")
        ax.set_title(title or default_title)
        ax.set_xlabel("Number of Runs")
        ax.set_ylabel("")
        return fig

    records = [
        {"failure_reason": r["failure_reason"], row_col: r[row_col],
         col_col: r[col_col], "count": 1}
        for _, r in failed.iterrows()
    ]
    df = pd.DataFrame(records)
    fig = px.sunburst(
        df, path=["failure_reason", row_col, col_col], values="count",
        title=title or default_title,
        color="failure_reason",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_layout(height=550, template="plotly_white")
    return fig


def plot_error_breakdown(
    runs_df: pd.DataFrame,
    backend: str = "seaborn",
    title: str | None = None,
    x_col: str = "display_label",
):
    """Stacked bar chart: hallucinations / omissions / genuine errors per run.

    Accepts either total counts (``total_hallucinations``,
    ``total_omissions``, ``total_genuine_errors``) or rates
    (``avg_hallucination_rate``, ``avg_omission_rate``) as fallback.
    """
    _require_backend(backend)

    # Prefer total counts; fall back to rates
    total_types = ["total_hallucinations", "total_omissions", "total_genuine_errors"]
    rate_types = ["avg_hallucination_rate", "avg_omission_rate"]

    available_totals = [c for c in total_types if c in runs_df.columns]
    available_rates = [c for c in rate_types if c in runs_df.columns]

    use_rates = False
    if available_totals:
        available = available_totals
    elif available_rates:
        available = available_rates
        use_rates = True
    else:
        raise ValueError("No error breakdown columns found in runs data")

    data = runs_df.dropna(subset=available, how="all").copy()
    if data.empty:
        raise ValueError("No runs with error breakdown data")

    long_rows = []
    for _, row in data.iterrows():
        label = row.get(x_col, row.get("run_id", "unknown"))
        for etype in available:
            val = row.get(etype)
            if pd.notna(val):
                nice_name = (
                    etype.replace("total_", "")
                    .replace("avg_", "")
                    .replace("_rate", "")
                    .replace("_", " ")
                    .title()
                )
                value = float(val) if use_rates else int(val)
                long_rows.append({"run": label, "error_type": nice_name, "count": value})

    if not long_rows:
        raise ValueError("No error breakdown data to plot")

    edf = pd.DataFrame(long_rows)
    if use_rates:
        default_title = "Error Rates (Hallucination / Omission)"
    else:
        default_title = "Error Breakdown (Hallucinations / Omissions / Genuine Errors)"

    color_map = {
        "Hallucinations": "#e74c3c",
        "Hallucination": "#e74c3c",
        "Omissions": "#f39c12",
        "Omission": "#f39c12",
        "Genuine Errors": "#8e44ad",
        "Genuine": "#8e44ad",
    }
    # Canonical ordering (works for both total and rate column names)
    canonical_order = ["Hallucinations", "Hallucination", "Omissions", "Omission",
                       "Genuine Errors", "Genuine"]

    if backend == "seaborn":
        sns.set_theme(style="whitegrid")
        # Pivot for stacked bars
        pivot = edf.pivot_table(index="run", columns="error_type", values="count", fill_value=0)
        ordered_cols = [c for c in canonical_order if c in pivot.columns]
        pivot = pivot[ordered_cols]

        fig, ax = plt.subplots(figsize=(max(8, len(pivot) * 1.5 + 2), 6))
        pivot.plot.bar(stacked=True, ax=ax, color=[color_map.get(c, "#999") for c in ordered_cols],
                       edgecolor="white")
        ax.set_title(title or default_title)
        ax.set_ylabel("Rate" if use_rates else "Count")
        ax.set_xlabel("")
        ax.set_xticklabels(ax.get_xticklabels(), rotation=35, ha="right")
        ax.legend(title="Error Type")
        return fig

    fig = px.bar(
        edf, x="run", y="count", color="error_type", barmode="stack",
        title=title or default_title,
        labels={"count": "Rate" if use_rates else "Count", "run": ""},
        color_discrete_map=color_map,
        text="count",
    )
    fig.update_traces(textposition="inside")
    fig.update_layout(height=450, template="plotly_white", xaxis_tickangle=-20)
    return fig


def _collapse_to_top_labels(df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    expected_top = df.groupby("expected_value")["count"].sum().nlargest(top_n).index
    predicted_top = df.groupby("predicted_value")["count"].sum().nlargest(top_n).index

    out = df.copy()
    out["expected_value"] = out["expected_value"].where(out["expected_value"].isin(expected_top), "__OTHER__")
    out["predicted_value"] = out["predicted_value"].where(out["predicted_value"].isin(predicted_top), "__OTHER__")
    return out.groupby(["expected_value", "predicted_value"], as_index=False)["count"].sum()


def plot_confusion(confusion_df: pd.DataFrame, run_id: str, column_name: str, normalize: str = "none", top_n_labels: int = 20, backend: str = "seaborn", title: str | None = None):
    _require_backend(backend)
    subset = confusion_df[(confusion_df["run_id"] == run_id) & (confusion_df["column_name"] == column_name)].copy()
    if subset.empty:
        raise ValueError(f"No confusion data for run_id={run_id}, column={column_name}")
    subset = _collapse_to_top_labels(subset, top_n=top_n_labels)
    matrix = subset.pivot_table(index="expected_value", columns="predicted_value", values="count", aggfunc="sum", fill_value=0)

    if normalize == "rows":
        matrix = matrix.div(matrix.sum(axis=1).replace(0, 1), axis=0)

    if backend == "seaborn":
        sns.set_theme(style="white")
        fig, ax = plt.subplots(figsize=(max(10, matrix.shape[1] * 0.9), max(8, matrix.shape[0] * 0.7)))
        sns.heatmap(matrix, cmap="Blues", annot=True, fmt=".2f" if normalize == "rows" else "g",
                    linewidths=0.5, linecolor="white", ax=ax)
        ax.set_title(title or f"Confusion: {column_name} ({run_id})")
        ax.set_xlabel("Predicted")
        ax.set_ylabel("Expected")
        return fig

    fig = px.imshow(matrix, color_continuous_scale="Blues", aspect="auto",
                    title=title or f"Confusion: {column_name} ({run_id})",
                    text_auto=True)
    return fig


def _prepare_cross_model_data(
    row_values_df: pd.DataFrame,
    column_name: str,
    errors_only: bool = False,
    row_filter: list[int] | None = None,
    id_filter: list[str] | None = None,
    id_column: str | None = None,
    max_rows: int | None = None,
):
    """Prepare pivoted data for cross-model comparison.

    Returns (pred_matrix, correct_matrix, gold_series) where:
        pred_matrix: rows=row_index, cols=display_label, values=predicted_value
        correct_matrix: same shape, values=1.0 (correct/empty_empty) or 0.0
        gold_series: row_index→gold_value
    """
    subset = row_values_df[row_values_df["column_name"] == column_name].copy()
    if subset.empty:
        return None, None, None

    # Apply row filters
    if row_filter is not None:
        subset = subset[subset["row_index"].astype(int).isin(row_filter)]
    if id_filter is not None and id_column is not None and id_column in subset.columns:
        subset = subset[subset[id_column].isin(id_filter)]

    # errors_only: keep rows where at least one model has an error
    if errors_only:
        error_rows = subset[
            ~subset["classification"].isin(["correct", "empty_empty"])
        ]["row_index"].unique()
        subset = subset[subset["row_index"].isin(error_rows)]

    if subset.empty:
        return None, None, None

    # Extract gold values (should be same across runs for same row_index)
    gold_series = (
        subset.drop_duplicates(subset=["row_index"])
        .set_index("row_index")["gold_value"]
    )

    # Pivot predicted values
    pred_matrix = subset.pivot_table(
        index="row_index",
        columns="display_label",
        values="predicted_value",
        aggfunc="first",
    )

    # Pivot correctness (1.0 = correct/empty_empty, 0.0 = error/hallucination/omission)
    subset["is_correct"] = subset["classification"].isin(["correct", "empty_empty"]).astype(float)
    correct_matrix = subset.pivot_table(
        index="row_index",
        columns="display_label",
        values="is_correct",
        aggfunc="first",
    )

    # Sort by row_index
    pred_matrix = pred_matrix.sort_index()
    correct_matrix = correct_matrix.sort_index()
    gold_series = gold_series.sort_index()

    # Apply max_rows
    if max_rows and len(pred_matrix) > max_rows:
        pred_matrix = pred_matrix.iloc[:max_rows]
        correct_matrix = correct_matrix.iloc[:max_rows]
        gold_series = gold_series.iloc[:max_rows]

    return pred_matrix, correct_matrix, gold_series


def plot_cross_model_comparison(
    row_values_df: pd.DataFrame,
    column_name: str,
    backend: str = "seaborn",
    title: str | None = None,
    row_filter: list[int] | None = None,
    id_filter: list[str] | None = None,
    id_column: str | None = None,
    errors_only: bool = False,
    max_rows: int | None = None,
):
    """Cross-model comparison heatmap for a specific column.

    Shows a grid where:
        - Rows = individual data samples (by row_index)
        - First column = gold standard value
        - Remaining columns = each model/context combo's prediction
        - Color = green (correct) / red (incorrect) / grey (empty_empty)
        - Text = the actual predicted value
    """
    _require_backend(backend)

    pred_matrix, correct_matrix, gold_series = _prepare_cross_model_data(
        row_values_df, column_name,
        errors_only=errors_only,
        row_filter=row_filter,
        id_filter=id_filter,
        id_column=id_column,
        max_rows=max_rows,
    )

    if pred_matrix is None or pred_matrix.empty:
        raise ValueError(f"No cross-model data for column '{column_name}'")

    default_title = f"Cross-model comparison: {column_name}"
    if errors_only:
        default_title += " (errors only)"

    n_rows = len(pred_matrix)
    n_cols = len(pred_matrix.columns) + 1  # +1 for gold column

    if backend == "seaborn":
        # Build combined text and color matrices including gold column
        col_labels = ["Gold Standard"] + list(pred_matrix.columns)
        text_data = []
        color_data = []

        for row_idx in pred_matrix.index:
            gold_val = gold_series.get(row_idx, "")
            row_text = [str(gold_val)]
            row_colors = [0.5]  # grey for gold column

            for col in pred_matrix.columns:
                pred_val = pred_matrix.loc[row_idx, col]
                is_correct = correct_matrix.loc[row_idx, col]
                row_text.append(str(pred_val) if pd.notna(pred_val) else "")
                row_colors.append(float(is_correct) if pd.notna(is_correct) else 0.5)

            text_data.append(row_text)
            color_data.append(row_colors)

        color_array = np.array(color_data)
        text_array = np.array(text_data)

        # Custom colormap: red (0) → grey (0.5) → green (1)
        cmap = mcolors.LinearSegmentedColormap.from_list(
            "correctness",
            [(0.0, "#ffc7ce"), (0.5, "#e0e0e0"), (1.0, "#c6efce")],
        )

        cell_height = 0.35
        cell_width = max(2.0, 12.0 / n_cols)
        fig_width = max(12, n_cols * cell_width)
        fig_height = max(4, n_rows * cell_height + 2)

        sns.set_theme(style="white")
        fig, ax = plt.subplots(figsize=(fig_width, fig_height))

        ax.imshow(color_array, cmap=cmap, vmin=0, vmax=1, aspect="auto")

        # Add text annotations
        for i in range(n_rows):
            for j in range(n_cols):
                txt = text_array[i, j]
                # Truncate long values for readability
                display_txt = txt[:25] + "..." if len(txt) > 28 else txt
                ax.text(j, i, display_txt, ha="center", va="center", fontsize=6,
                        color="black")

        ax.set_xticks(range(n_cols))
        ax.set_xticklabels(col_labels, rotation=45, ha="right", fontsize=8)
        ax.set_yticks(range(n_rows))
        ax.set_yticklabels([f"row {idx}" for idx in pred_matrix.index], fontsize=7)
        ax.set_title(title or default_title)

        return fig

    # Plotly implementation
    col_labels = ["Gold Standard"] + list(pred_matrix.columns)
    z_data = []
    text_data = []
    hover_data = []

    for row_idx in pred_matrix.index:
        gold_val = gold_series.get(row_idx, "")
        z_row = [0.5]  # grey for gold
        text_row = [str(gold_val)]
        hover_row = [f"Gold: {gold_val}"]

        for col in pred_matrix.columns:
            pred_val = pred_matrix.loc[row_idx, col]
            is_correct = correct_matrix.loc[row_idx, col]
            pred_str = str(pred_val) if pd.notna(pred_val) else ""
            z_row.append(float(is_correct) if pd.notna(is_correct) else 0.5)
            text_row.append(pred_str)
            hover_row.append(f"Gold: {gold_val}<br>Predicted: {pred_str}<br>{'Correct' if is_correct == 1.0 else 'Incorrect'}")

        z_data.append(z_row)
        text_data.append(text_row)
        hover_data.append(hover_row)

    colorscale = [[0, "#ffc7ce"], [0.5, "#e0e0e0"], [1, "#c6efce"]]

    fig = go.Figure(data=go.Heatmap(
        z=z_data,
        text=text_data,
        hovertext=hover_data,
        hoverinfo="text",
        texttemplate="%{text}",
        textfont={"size": 9},
        colorscale=colorscale,
        zmin=0,
        zmax=1,
        showscale=False,
        x=col_labels,
        y=[f"row {idx}" for idx in pred_matrix.index],
    ))

    fig.update_layout(
        title=title or default_title,
        xaxis=dict(side="top", tickangle=-45),
        height=max(400, n_rows * 25 + 150),
        width=max(600, n_cols * 120),
    )

    return fig
