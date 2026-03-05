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
