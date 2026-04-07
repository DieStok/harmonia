#!/usr/bin/env python3
"""
Table Profiler — generates curated markdown summaries of data tables.

Uses ydata-profiling to analyze CSV/XLSX files and produce agent-friendly
markdown summaries with optional detailed reports and JSON dumps.

Usage:
    python profile_tables.py /path/to/data/directory/
    python profile_tables.py file1.csv file2.csv
    python profile_tables.py /path/to/data/ --detailed --json

Examples:
    # Profile all tables in a dataset directory
    python profile_tables.py ../../raw/datasets_harmonia/two_metadata_tables_harmonize/data/

    # Detailed profile with JSON dump
    python profile_tables.py ../../raw/datasets_harmonia/two_metadata_tables_harmonize/data/ \
        --detailed --json

    # Override separator for tricky CSVs
    python profile_tables.py data/ --separator ","
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# =============================================================================
# GLOBAL DEFAULTS
# =============================================================================

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS_DIR = Path(__file__).resolve().parent


# =============================================================================
# FILE DISCOVERY & LOADING
# =============================================================================


def discover_files(inputs: list[str]) -> list[Path]:
    """Discover tabular files from a directory or explicit file list."""
    files = []
    for inp in inputs:
        p = Path(inp)
        if p.is_dir():
            csv_files = sorted(p.glob("*.csv"))
            xlsx_files = sorted(p.glob("*.xlsx"))
            files.extend(csv_files)
            files.extend(xlsx_files)
        elif p.is_file():
            if p.suffix.lower() in (".csv", ".xlsx"):
                files.append(p)
            else:
                print(
                    f"Warning: skipping '{p.name}' (unsupported format)",
                    file=sys.stderr,
                )
        else:
            print(f"Error: '{inp}' does not exist", file=sys.stderr)
            sys.exit(2)

    if not files:
        print("Error: no .csv or .xlsx files found", file=sys.stderr)
        sys.exit(2)

    # Warn about potential csv/xlsx duplicates
    stems = {}
    for f in files:
        stem = f.stem
        if stem in stems:
            print(
                f"Warning: possible duplicate data — both '{stems[stem].name}' "
                f"and '{f.name}' discovered. Consider passing explicit file "
                f"paths to avoid profiling the same data twice.",
                file=sys.stderr,
            )
        stems[stem] = f

    return files


def detect_separator(filepath: Path) -> str:
    """Auto-detect CSV separator by counting candidates in the header line.

    csv.Sniffer can be fooled when values contain commas (e.g., "1,234").
    Instead, count occurrences of candidate delimiters in the first line
    (the header), and pick the one that appears most often.
    """
    with open(filepath, encoding="utf-8-sig", newline="") as f:
        header = f.readline()

    candidates = {";": 0, ",": 0, "\t": 0, "|": 0}
    for char in header:
        if char in candidates:
            candidates[char] += 1

    # Pick the delimiter with the highest count in the header
    best = max(candidates, key=candidates.get)
    if candidates[best] == 0:
        return ","  # fallback
    return best


def load_table(
    filepath: Path,
    separator: str | None = None,
    sheet: str | int | None = None,
) -> pd.DataFrame:
    """Load a CSV or XLSX file into a DataFrame."""
    if filepath.suffix.lower() == ".xlsx":
        kwargs = {}
        if sheet is not None:
            kwargs["sheet_name"] = sheet
        df = pd.read_excel(filepath, **kwargs)
        # Warn if multiple sheets
        try:
            xls = pd.ExcelFile(filepath)
            if len(xls.sheet_names) > 1:
                used = sheet if sheet is not None else xls.sheet_names[0]
                print(
                    f"Warning: '{filepath.name}' has {len(xls.sheet_names)} "
                    f"sheets ({', '.join(xls.sheet_names)}). Using '{used}'. "
                    f"Pass --sheet to select a different one.",
                    file=sys.stderr,
                )
        except Exception:
            pass
        return df

    sep = separator if separator is not None else detect_separator(filepath)
    print(f"  Detected separator: {repr(sep)}", file=sys.stderr)
    return pd.read_csv(filepath, sep=sep, encoding="utf-8-sig")


# =============================================================================
# MARKDOWN GENERATION
# =============================================================================


def format_number(val) -> str:
    """Format a numeric value for display."""
    if pd.isna(val):
        return "N/A"
    if isinstance(val, float):
        if abs(val) >= 1000:
            return f"{val:,.0f}"
        if abs(val) >= 1:
            return f"{val:.2f}"
        return f"{val:.4f}"
    return str(val)


def _top_values_from_series(series: pd.Series, n: int = 5) -> str:
    """Compute top N value counts from a pandas Series, formatted as string."""
    vc = series.dropna().value_counts()
    total = len(series.dropna())
    if total == 0 or len(vc) == 0:
        return ""
    top_items = vc.head(n)
    parts = []
    for val, count in top_items.items():
        pct = count / total * 100
        parts.append(f'"{val}" ({pct:.0f}%)')
    return "top: " + ", ".join(parts)


def generate_curated_markdown(
    filepath: Path,
    df: pd.DataFrame,
    detailed: bool = False,
) -> str:
    """Generate a curated markdown profile from a DataFrame."""
    from ydata_profiling import ProfileReport

    print(f"  Profiling ({df.shape[0]} rows x {df.shape[1]} cols)...", file=sys.stderr)

    if detailed:
        print(
            "  Warning: --detailed produces larger output that may consume "
            "significant LLM context",
            file=sys.stderr,
        )
        # Full mode but disable correlations (too expensive for wide tables)
        profile = ProfileReport(
            df,
            minimal=False,
            correlations={"auto": {"calculate": False}},
            progress_bar=False,
        )
    else:
        profile = ProfileReport(df, minimal=True, progress_bar=False)

    desc = profile.get_description()

    lines = []
    lines.append(f"# Profile: {filepath.name}")
    lines.append("")

    # Table overview
    table_stats = desc.table
    n_rows = table_stats.get("n", len(df))
    n_cols = table_stats.get("n_var", len(df.columns))
    n_cells_missing = table_stats.get("n_cells_missing", 0)
    total_cells = n_rows * n_cols
    p_cells_missing = (n_cells_missing / total_cells * 100) if total_cells > 0 else 0
    mem_bytes = table_stats.get("memory_size", 0)
    mem_mb = mem_bytes / (1024 * 1024) if mem_bytes else 0

    lines.append("## Table Overview")
    lines.append("")
    lines.append(f"- Rows: {n_rows}")
    lines.append(f"- Columns: {n_cols}")
    lines.append(f"- Total missing cells: {n_cells_missing} ({p_cells_missing:.1f}%)")
    lines.append(f"- Memory usage: {mem_mb:.1f} MB")
    lines.append("")

    # Column summary table
    lines.append("## Column Summary")
    lines.append("")
    lines.append(
        "| Column | Type | Missing | Missing % | Unique | Unique % | Notes |"
    )
    lines.append(
        "|--------|------|---------|-----------|--------|----------|-------|"
    )

    variables = desc.variables
    for col_name, var_info in variables.items():
        var_type = str(var_info.get("type", "Unknown"))
        # Clean up type name
        type_display = var_type.split(".")[-1] if "." in var_type else var_type

        n_missing = var_info.get("n_missing", 0)
        p_missing = var_info.get("p_missing", 0) * 100

        n_distinct = var_info.get("n_distinct", 0)
        p_distinct = var_info.get("p_distinct", 0) * 100

        # Build notes based on type
        notes = _build_notes(var_info, type_display, detailed, df, col_name)

        # Escape pipe characters in column names and notes
        col_display = str(col_name).replace("|", "\\|")
        notes = notes.replace("|", "\\|")

        lines.append(
            f"| {col_display} | {type_display} | {n_missing} | "
            f"{p_missing:.1f}% | {n_distinct} | {p_distinct:.1f}% | "
            f"{notes} |"
        )

    # Detailed mode: alerts
    if detailed and hasattr(desc, "alerts") and desc.alerts:
        lines.append("")
        lines.append("## Data Quality Alerts")
        lines.append("")
        for alert in desc.alerts:
            alert_type = str(alert.alert_type).split(".")[-1]
            col = getattr(alert, "column_name", "N/A")
            lines.append(f"- **{alert_type}**: {col}")

    lines.append("")
    return "\n".join(lines)


def _build_notes(
    var_info: dict,
    type_display: str,
    detailed: bool,
    df: pd.DataFrame,
    col_name: str,
) -> str:
    """Build the Notes column content for a variable."""
    notes_parts = []

    if type_display in ("Numeric", "Real", "Integer"):
        mean = var_info.get("mean")
        std = var_info.get("std")
        vmin = var_info.get("min")
        vmax = var_info.get("max")
        notes_parts.append(
            f"mean={format_number(mean)}, std={format_number(std)}, "
            f"min={format_number(vmin)}, max={format_number(vmax)}"
        )
        if detailed:
            histogram = var_info.get("histogram")
            if histogram is not None:
                counts = histogram.get("counts", [])
                if counts:
                    notes_parts.append(f"histogram: {len(counts)} bins")

    elif type_display in ("Categorical", "Boolean", "Text"):
        # Try ydata-profiling value_counts first, fall back to pandas
        value_counts = var_info.get("value_counts_without_nan")
        if value_counts is not None and len(value_counts) > 0:
            top_items = list(value_counts.items())[:5]
            total = sum(v for _, v in value_counts.items())
            top_strs = []
            for val, count in top_items:
                pct = count / total * 100 if total > 0 else 0
                top_strs.append(f'"{val}" ({pct:.0f}%)')
            notes_parts.append("top: " + ", ".join(top_strs))
        elif col_name in df.columns:
            # Minimal mode may not populate value_counts for Text type
            top_str = _top_values_from_series(df[col_name])
            if top_str:
                notes_parts.append(top_str)

        if detailed and value_counts is not None and len(value_counts) <= 20:
            notes_parts.append(f"all {len(value_counts)} values shown")

    elif type_display == "DateTime":
        vmin = var_info.get("min")
        vmax = var_info.get("max")
        if vmin is not None and vmax is not None:
            notes_parts.append(f"range: {vmin} to {vmax}")

    return "; ".join(notes_parts) if notes_parts else ""


# =============================================================================
# JSON OUTPUT
# =============================================================================


def generate_json_output(filepath: Path, df: pd.DataFrame) -> str:
    """Generate full ydata-profiling JSON output."""
    from ydata_profiling import ProfileReport

    print(f"  Generating JSON profile for {filepath.name}...", file=sys.stderr)
    profile = ProfileReport(df, minimal=True, progress_bar=False)
    return profile.to_json()


# =============================================================================
# OUTPUT DIRECTORY
# =============================================================================


def resolve_output_dir(output_dir: str | None, input_path: str) -> Path:
    """Resolve the output directory, using default timestamped naming if needed."""
    if output_dir:
        out = Path(output_dir)
    else:
        # Default: DD_MM_YYYY_HH_MM_{folder_name}_output/ under tools dir
        input_p = Path(input_path)
        folder_name = input_p.name if input_p.is_dir() else input_p.parent.name
        timestamp = datetime.now().strftime("%d_%m_%Y_%H_%M")
        dirname = f"{timestamp}_{folder_name}_output"
        out = TOOLS_DIR / dirname

    # Handle collision
    base = out
    suffix = 2
    while out.exists():
        out = base.parent / f"{base.name}_{suffix}"
        suffix += 1

    return out


# =============================================================================
# CLI
# =============================================================================


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="profile_tables.py",
        description="Profile data tables and generate agent-friendly markdown summaries.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  %(prog)s /path/to/data/
  %(prog)s file1.csv file2.csv --separator ";"
  %(prog)s /path/to/data/ --detailed --json
  %(prog)s /path/to/data/ --output-dir /tmp/profiles/
""",
    )

    parser.add_argument(
        "inputs",
        nargs="+",
        help="Directory containing tables or explicit file paths (.csv, .xlsx)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: timestamped dir under tool directory)",
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Generate richer reports with alerts and distributions",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Also dump full ydata-profiling JSON alongside markdown",
    )
    parser.add_argument(
        "--separator",
        default=None,
        help="Override CSV separator (default: auto-detect)",
    )
    parser.add_argument(
        "--sheet",
        default=None,
        help="Sheet name or index for XLSX files (default: first sheet)",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    # Discover files
    print("Discovering files...", file=sys.stderr)
    files = discover_files(args.inputs)
    print(f"Found {len(files)} file(s): {', '.join(f.name for f in files)}", file=sys.stderr)

    # Resolve output directory
    out_dir = resolve_output_dir(args.output_dir, args.inputs[0])
    profiles_dir = out_dir / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {out_dir}", file=sys.stderr)

    # Parse sheet arg
    sheet = args.sheet
    if sheet is not None:
        try:
            sheet = int(sheet)
        except ValueError:
            pass  # Keep as string (sheet name)

    # Profile each file
    for filepath in files:
        print(f"\nProcessing: {filepath.name}", file=sys.stderr)

        df = load_table(filepath, separator=args.separator, sheet=sheet)

        # Generate curated markdown
        md = generate_curated_markdown(filepath, df, detailed=args.detailed)
        stem = filepath.stem
        md_path = profiles_dir / f"{stem}_profile.md"
        md_path.write_text(md, encoding="utf-8")
        print(f"  Written: {md_path}", file=sys.stderr)

        # Optionally generate JSON
        if args.json:
            json_str = generate_json_output(filepath, df)
            json_path = profiles_dir / f"{stem}_profile.json"
            json_path.write_text(json_str, encoding="utf-8")
            print(f"  Written: {json_path}", file=sys.stderr)

    print(f"\nDone. {len(files)} profile(s) written to {profiles_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
