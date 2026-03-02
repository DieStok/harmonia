from __future__ import annotations

import pandas as pd


def apply_filters(df: pd.DataFrame, include_runs: str | None = None, exclude_runs: str | None = None) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if include_runs:
        out = out[out["experiment_name"].str.contains(include_runs, case=False, na=False)]
    if exclude_runs:
        out = out[~out["experiment_name"].str.contains(exclude_runs, case=False, na=False)]
    return out


def aggregate_runs(runs_df: pd.DataFrame, metric: str, group_by: list[str], agg: str = "mean") -> pd.DataFrame:
    if runs_df.empty:
        return runs_df
    valid_group = [g for g in group_by if g in runs_df.columns]
    if not valid_group:
        valid_group = ["display_label"]
    if metric not in runs_df.columns:
        raise KeyError(f"Unknown metric '{metric}'")
    out = runs_df.groupby(valid_group, dropna=False)[metric].agg(agg).reset_index(name=metric)
    out["n_runs"] = runs_df.groupby(valid_group, dropna=False)[metric].size().values
    return out


def heatmap_matrix(
    column_values_df: pd.DataFrame,
    metric: str,
    row_key: str = "display_label",
    columns_mode: str = "union",
) -> pd.DataFrame:
    if column_values_df.empty:
        return pd.DataFrame()
    if metric not in column_values_df.columns:
        raise KeyError(f"Unknown column metric '{metric}'")

    pivot = column_values_df.pivot_table(index=row_key, columns="column_name", values=metric, aggfunc="mean")
    if columns_mode == "intersection":
        pivot = pivot.dropna(axis=1, how="any")
    return pivot.sort_index(axis=0)
