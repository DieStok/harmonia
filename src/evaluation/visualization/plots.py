from __future__ import annotations

from pathlib import Path

import pandas as pd

SEABORN_READY = True
PLOTLY_READY = True
try:
    import matplotlib.pyplot as plt
    import seaborn as sns
except Exception:
    SEABORN_READY = False

try:
    import plotly.express as px
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
        fig, ax = plt.subplots(figsize=(10, 8))
        sns.heatmap(matrix, cmap="magma", ax=ax)
        ax.set_title(title or f"Confusion: {column_name} ({run_id})")
        ax.set_xlabel("Predicted")
        ax.set_ylabel("Expected")
        return fig

    fig = px.imshow(matrix, color_continuous_scale="Magma", aspect="auto", title=title or f"Confusion: {column_name} ({run_id})")
    return fig
