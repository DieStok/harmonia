#!/usr/bin/env python3
"""
Column Matcher — finds likely column correspondences between table pairs.

Uses Valentine schema matching algorithms to discover column mappings
across data tables, outputting results as CSV.

Usage:
    python match_columns.py /path/to/data/directory/
    python match_columns.py file1.csv file2.csv
    python match_columns.py /path/to/data/ --matchers distribution cupid jaccard

Examples:
    # Match columns across all table pairs (default matchers)
    python match_columns.py ../../raw/datasets_harmonia/two_metadata_tables_harmonize/data/

    # Dry run to see what would be matched
    python match_columns.py /path/to/data/ --dry-run

    # Match with specific matchers, threshold, and one-to-one constraint
    python match_columns.py /path/to/data/ \
        --matchers distribution cupid jaccard \
        --threshold 0.5 --one-to-one --top-n 10

    # Match specific pairs only
    python match_columns.py /path/to/data/ \
        --pairs table1.csv table2.csv --pairs table1.csv table3.csv
"""

from __future__ import annotations

import argparse
import csv
import itertools
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# =============================================================================
# GLOBAL DEFAULTS
# =============================================================================

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS_DIR = Path(__file__).resolve().parent

DEFAULT_MATCHERS = ["distribution", "cupid"]
ALL_MATCHERS = ["distribution", "cupid", "jaccard", "similarity_flooding", "coma"]

SAMPLE_SEED = 42
AUTO_SAMPLE_THRESHOLD = 500


# =============================================================================
# FILE DISCOVERY & LOADING (same pattern as profile_tables.py)
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
                f"paths to avoid matching the same data twice.",
                file=sys.stderr,
            )
        stems[stem] = f

    return files


def detect_separator(filepath: Path) -> str:
    """Auto-detect CSV separator by counting candidates in the header line."""
    with open(filepath, encoding="utf-8-sig", newline="") as f:
        header = f.readline()

    candidates = {";": 0, ",": 0, "\t": 0, "|": 0}
    for char in header:
        if char in candidates:
            candidates[char] += 1

    best = max(candidates, key=candidates.get)
    if candidates[best] == 0:
        return ","
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
        try:
            xls = pd.ExcelFile(filepath)
            if len(xls.sheet_names) > 1:
                used = sheet if sheet is not None else xls.sheet_names[0]
                print(
                    f"Warning: '{filepath.name}' has {len(xls.sheet_names)} "
                    f"sheets. Using '{used}'. Pass --sheet to select.",
                    file=sys.stderr,
                )
        except Exception:
            pass
        return df

    sep = separator if separator is not None else detect_separator(filepath)
    print(f"  Detected separator for {filepath.name}: {repr(sep)}", file=sys.stderr)
    return pd.read_csv(filepath, sep=sep, encoding="utf-8-sig")


# =============================================================================
# PAIR GENERATION
# =============================================================================


def generate_pairs(
    files: list[Path],
    pairs_filter: list[list[str]] | None = None,
) -> list[tuple[Path, Path]]:
    """Generate table pairs to compare.

    Default: all unique unordered pairs (N choose 2).
    If pairs_filter is provided, only those specific pairs are used.
    """
    if pairs_filter:
        # Resolve filenames to paths
        name_to_path = {f.name: f for f in files}
        resolved = []
        for pair in pairs_filter:
            a_name, b_name = pair
            a_path = name_to_path.get(a_name)
            b_path = name_to_path.get(b_name)
            if a_path is None:
                print(f"Error: '{a_name}' not found among discovered files", file=sys.stderr)
                sys.exit(1)
            if b_path is None:
                print(f"Error: '{b_name}' not found among discovered files", file=sys.stderr)
                sys.exit(1)
            resolved.append((a_path, b_path))
        return resolved

    return list(itertools.combinations(files, 2))


# =============================================================================
# MATCHER INSTANTIATION
# =============================================================================


def instantiate_matcher(name: str):
    """Instantiate a Valentine matcher by short name."""
    if name == "distribution":
        from valentine.algorithms import DistributionBased
        return DistributionBased()
    elif name == "cupid":
        from valentine.algorithms import Cupid
        return Cupid()
    elif name == "jaccard":
        from valentine.algorithms import JaccardDistanceMatcher
        return JaccardDistanceMatcher()
    elif name == "similarity_flooding":
        from valentine.algorithms import SimilarityFlooding
        return SimilarityFlooding()
    elif name == "coma":
        try:
            from valentine.algorithms import Coma
            return Coma(use_instances=True)
        except Exception as e:
            print(
                f"Warning: Coma matcher unavailable (requires Java): {e}",
                file=sys.stderr,
            )
            return None
    else:
        print(f"Error: unknown matcher '{name}'", file=sys.stderr)
        sys.exit(1)


# =============================================================================
# SAMPLING
# =============================================================================


def maybe_sample(df: pd.DataFrame, sample_rows: int | None) -> pd.DataFrame:
    """Apply row sampling if needed."""
    n_rows = len(df)

    if sample_rows is not None:
        # Explicit user override
        if sample_rows >= n_rows:
            return df
        return df.sample(n=sample_rows, random_state=SAMPLE_SEED)

    # Auto-cap at threshold
    if n_rows > AUTO_SAMPLE_THRESHOLD:
        print(
            f"  Auto-sampling to {AUTO_SAMPLE_THRESHOLD} rows "
            f"(from {n_rows}), seed={SAMPLE_SEED}",
            file=sys.stderr,
        )
        return df.sample(n=AUTO_SAMPLE_THRESHOLD, random_state=SAMPLE_SEED)

    return df


# =============================================================================
# MATCHING
# =============================================================================


def run_matching(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    table1_name: str,
    table2_name: str,
    matcher,
    matcher_name: str,
    threshold: float,
    top_n: int | None,
    one_to_one: bool,
) -> list[dict]:
    """Run a single matcher on a table pair and return rows."""
    from valentine import valentine_match

    print(f"    Running {matcher_name}...", file=sys.stderr)
    matches = valentine_match(df1, df2, matcher, df1_name=table1_name, df2_name=table2_name)

    # Apply one-to-one constraint
    if one_to_one:
        matches = matches.one_to_one()

    # Convert to list of dicts
    rows = []
    for (src_key, tgt_key), score in matches.items():
        if score < threshold:
            continue
        rows.append({
            "source_table": src_key[0],
            "source_column": src_key[1],
            "target_table": tgt_key[0],
            "target_column": tgt_key[1],
            "similarity_score": round(score, 6),
            "matcher": matcher_name,
        })

    # Sort by score descending
    rows.sort(key=lambda r: r["similarity_score"], reverse=True)

    # Apply top-n per source column
    if top_n is not None:
        filtered = []
        col_counts: dict[str, int] = {}
        for row in rows:
            key = row["source_column"]
            count = col_counts.get(key, 0)
            if count < top_n:
                filtered.append(row)
                col_counts[key] = count + 1
        rows = filtered

    print(f"    {matcher_name}: {len(rows)} matches", file=sys.stderr)
    return rows


# =============================================================================
# OUTPUT
# =============================================================================


def resolve_output_dir(output_dir: str | None, input_path: str) -> Path:
    """Resolve output directory with default timestamped naming."""
    if output_dir:
        out = Path(output_dir)
    else:
        input_p = Path(input_path)
        folder_name = input_p.name if input_p.is_dir() else input_p.parent.name
        timestamp = datetime.now().strftime("%d_%m_%Y_%H_%M")
        dirname = f"{timestamp}_{folder_name}_output"
        out = TOOLS_DIR / dirname

    base = out
    suffix = 2
    while out.exists():
        out = base.parent / f"{base.name}_{suffix}"
        suffix += 1

    return out


def write_csv(rows: list[dict], output_path: Path):
    """Write match results to CSV."""
    fieldnames = [
        "source_table", "source_column", "target_table",
        "target_column", "similarity_score", "matcher",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# =============================================================================
# CLI
# =============================================================================


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="match_columns.py",
        description="Find column correspondences between table pairs using Valentine.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  %(prog)s /path/to/data/
  %(prog)s file1.csv file2.csv --matchers distribution cupid jaccard
  %(prog)s /path/to/data/ --threshold 0.5 --one-to-one --top-n 10
  %(prog)s /path/to/data/ --pairs table1.csv table2.csv
  %(prog)s /path/to/data/ --dry-run
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
        "--matchers",
        nargs="+",
        choices=ALL_MATCHERS,
        default=DEFAULT_MATCHERS,
        help=f"Matchers to use (default: {' '.join(DEFAULT_MATCHERS)})",
    )
    parser.add_argument(
        "--pairs",
        nargs=2,
        action="append",
        metavar=("FILE1", "FILE2"),
        help="Specific table pair to compare (repeatable). Filenames only.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.0,
        help="Minimum similarity score (default: 0.0, no filtering)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=None,
        help="Top N matches per source column per matcher (default: all)",
    )
    parser.add_argument(
        "--one-to-one",
        action="store_true",
        help="Enforce one-to-one column mapping (greedy, highest-score-first)",
    )
    parser.add_argument(
        "--sample-rows",
        type=int,
        default=None,
        help=f"Sample N rows (default: all, auto-caps at {AUTO_SAMPLE_THRESHOLD})",
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List discovered files, planned pairs, and matchers without executing",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    # Discover files
    print("Discovering files...", file=sys.stderr)
    files = discover_files(args.inputs)
    print(f"Found {len(files)} file(s): {', '.join(f.name for f in files)}", file=sys.stderr)

    # Generate pairs
    pairs = generate_pairs(files, args.pairs)
    if not pairs:
        print("Error: need at least 2 files to form pairs", file=sys.stderr)
        sys.exit(1)

    print(f"Planned pairs ({len(pairs)}):", file=sys.stderr)
    for a, b in pairs:
        print(f"  {a.name}  <->  {b.name}", file=sys.stderr)
    print(f"Matchers: {', '.join(args.matchers)}", file=sys.stderr)

    # Dry run: just show plan and exit
    if args.dry_run:
        print("\n[dry-run] Would match the above pairs. Exiting.", file=sys.stderr)
        sys.exit(0)

    # Instantiate matchers
    matchers = []
    for name in args.matchers:
        m = instantiate_matcher(name)
        if m is not None:
            matchers.append((name, m))

    if not matchers:
        print("Error: no valid matchers available", file=sys.stderr)
        sys.exit(1)

    # Resolve output directory
    out_dir = resolve_output_dir(args.output_dir, args.inputs[0])
    matches_dir = out_dir / "matches"
    matches_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {out_dir}", file=sys.stderr)

    # Parse sheet arg
    sheet = args.sheet
    if sheet is not None:
        try:
            sheet = int(sheet)
        except ValueError:
            pass

    # Process each pair
    for file_a, file_b in pairs:
        print(f"\nMatching: {file_a.name} <-> {file_b.name}", file=sys.stderr)

        df_a = load_table(file_a, separator=args.separator, sheet=sheet)
        df_b = load_table(file_b, separator=args.separator, sheet=sheet)

        # Apply sampling
        df_a_sampled = maybe_sample(df_a, args.sample_rows)
        df_b_sampled = maybe_sample(df_b, args.sample_rows)

        all_rows = []
        for matcher_name, matcher in matchers:
            rows = run_matching(
                df_a_sampled,
                df_b_sampled,
                table1_name=file_a.stem,
                table2_name=file_b.stem,
                matcher=matcher,
                matcher_name=matcher_name,
                threshold=args.threshold,
                top_n=args.top_n,
                one_to_one=args.one_to_one,
            )
            all_rows.extend(rows)

        # Write combined CSV
        csv_name = f"{file_a.stem}_vs_{file_b.stem}_matches.csv"
        csv_path = matches_dir / csv_name
        write_csv(all_rows, csv_path)
        print(f"  Written: {csv_path} ({len(all_rows)} rows)", file=sys.stderr)

    print(
        f"\nDone. {len(pairs)} pair(s) matched, results in {matches_dir}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
