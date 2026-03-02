# Visualization CLI Implementation Plan (Single-table / Single-schema first)

## 1) Objective and scope

Build a reusable command-line visualization tool that compares harmonization performance across runs/models/contexts using existing `metrics.json` outputs from:

- `src/evaluation/metrics.py`
- `src/evaluation/schemas.py`

Primary first target:

- one table (e.g., dou.csv),
- one schema mapping task (e.g., GDC),
- many runs/configs/models/contexts.

The CLI should generate high-quality static plots (Seaborn/Matplotlib), tabular summaries, and machine-readable intermediate tables suitable for downstream notebook use.

---

## 2) Core user questions this tool must answer

1. Which run/model/context has best overall schema mapping quality?
2. Which run/model/context has best average value harmonization quality?
3. Which columns are consistently difficult across models?
4. How do contexts compare for the same model (CodeAct vs BDI-kit vs code-context)?
5. How do model families compare (frontier vs local)?
6. What are the confusion patterns for specific problematic columns?

---

## 3) Input contracts and data model

### 3.1 Required input artifacts

- One or more `metrics.json` files (from result directories).

Optional enrichment inputs:

- Run config YAML path(s) for extracting context + additional config parameters.
- Additional metadata mapping file (CSV/JSON) to override/fill labels (e.g., model family tags).

### 3.2 Existing metrics schema fields to consume

From `MetricsResult`:

- `metadata` (experiment_name, llm_provider, llm_model, timing_seconds)
- `column_mapping` (accuracy/precision/recall + per-column detail)
- `column_values` (per-target-column metrics, confusion_matrix, misclassifications)
- `overall_summary` (averages and totals)
- `extra_columns_count`, `extra_columns`

### 3.3 Canonical internal tables (tidy format)

The CLI should normalize into these tables:

1. **runs_table** (one row per metrics file)
   - run_id
   - experiment_name
   - model_label
   - provider
   - context
   - model_family (frontier/local/unknown)
   - overall metrics columns (`column_mapping_accuracy`, `avg_value_accuracy_excl_empty`, etc.)
   - tags blob / flattened config attributes

2. **column_mapping_table** (one row per source column per run)
   - run_id, source_column, expected_target, actual_target, is_correct, is_wrong, is_missing, is_acceptable

3. **column_value_table** (one row per target column per run)
   - run_id, column_name, source_column_name
   - metric fields (`accuracy_excl_empty`, `f1_macro_excl_empty`, etc.)
   - hallucination/omission/error categories

4. **confusion_long_table** (optional expanded)
   - run_id, column_name, expected_value, predicted_value, count

All plotting functions operate only on these normalized tables.

---

## 4) CLI design

Suggested script:

- `src/evaluation/visualize_metrics_cli.py`

Suggested command:

- `python src/evaluation/visualize_metrics_cli.py <subcommand> [options]`

### 4.1 Subcommands

1. `summarize`
   - prints textual run comparison table + writes CSV.

2. `bars`
   - global side-by-side barplots for run-level metrics.

3. `heatmap`
   - model × column heatmap (configurable metric).

4. `confusion`
   - confusion matrix for selected run+column (or top-N columns).

5. `compare`
   - convenience command to generate a full report bundle (all key plots + CSV tables).

### 4.2 Shared CLI options

- `--metrics-glob` or `--metrics-files` (required input source)
- `--out-dir` (required)
- `--metric` (default: `accuracy_excl_empty`; alternatives: `f1_macro_excl_empty`, etc.)
- `--group-by` (repeatable; e.g., `model`, `context`, `model_family`)
- `--facet-by` (optional subplot split)
- `--agg` (`mean|median|max|best`)
- `--include-runs` / `--exclude-runs` regex
- `--columns-mode` (`union|intersection|topk`) for heatmaps
- `--topk-columns` for sparse column selection
- `--backend` (`seaborn|plotly`) and `--interactive` (shortcut for `--backend plotly`)
- `--dpi`, `--style`, `--palette`, `--figure-format` (`png`, `svg`, `pdf`, `html`)
- `--save-dataframes` flag

### 4.3 Metadata enrichment options

- `--config-root` (scan corresponding config YAML for parameters/context)
- `--labels-file` (CSV/JSON mapping run/model to tags like local/frontier)
- `--model-family-rules` (optional YAML rules for auto-classification)

---

## 5) Plot suite (phase 1: single-table comparisons)

All plotting commands should support both static and interactive rendering:

- static: Seaborn/Matplotlib output
- interactive: Plotly output with hover tooltips and optional HTML export

Each plotting function should expose a common signature parameter (e.g., `backend="seaborn"`), and the CLI should route this via `--backend`.

### 5.1 Global run comparison bars

Output examples:

- `global_column_mapping_accuracy_bar.png`
- `global_avg_value_accuracy_bar.png`
- `global_avg_value_f1_bar.png`

Design:

- x: run or grouped label (`model + context`)
- y: chosen metric
- hue: configurable (`context` or `model_family`)
- optional error bars for repeated runs (mean ± std/CI if grouped)

### 5.2 Per-column heatmap (main requested visualization)

Output:

- `per_column_metric_heatmap_<metric>.png`

Design:

- rows: models/runs (with deterministic sorted order)
- columns: schema columns
- cell value: selected metric (default accuracy)
- optional row annotation strip: context + model_family
- colorbar fixed range [0,1] for comparability
- optional clustering off by default; keep semantic ordering

### 5.3 Per-column grouped bars

Output:

- `per_column_grouped_bar_<metric>.png`

Design:

- x: column
- y: metric
- hue: run/model/context
- useful when number of runs is small.

### 5.4 Confusion matrices (column-level deep-dive)

Outputs:

- `confusion_<run>_<column>.png`
- optionally normalized confusion matrix variant.

Design details:

- limit labels to top-N frequent classes, aggregate others into `__OTHER__`
- support raw counts and row-normalized percentages
- include support table export for reproducibility.

### 5.5 Error-category composition plots

Output:

- `error_categorization_stacked_bar.png`

Shows whitespace-only/case-only/genuine error decomposition across runs and columns.

---

## 6) Grouping and comparison logic

### 6.1 Hierarchical grouping keys

Support grouping by any combination:

- model (canonicalized)
- context
- provider
- model_family
- selected config params (temperature, prompt version, summarization threshold, etc.)

### 6.2 Canonical label strategy

Define canonical run label builder:

- `display_label = "{model_short} | {context} | {optional tags}"`

Add stable sort logic:

1. model_family (frontier/local)
2. model_short
3. context
4. run timestamp

### 6.3 Collapse/aggregate modes

When multiple runs share same grouping key:

- aggregate metric by mean (default)
- keep support count (`n_runs`)
- optionally show spread.

---

## 7) Module structure and reusable API design

Create reusable plotting/data modules, then thin CLI wrapper.

Suggested files:

- `src/evaluation/visualization/io.py`
  - metrics discovery/loading/validation
- `src/evaluation/visualization/normalize.py`
  - convert metrics.json → tidy DataFrames
- `src/evaluation/visualization/enrich.py`
  - derive context/model/model_family/labels from config + rules
- `src/evaluation/visualization/aggregate.py`
  - grouping + aggregation helpers
- `src/evaluation/visualization/plots.py`
  - plot functions (bars, heatmap, confusion, stacked errors) with backend switch (`seaborn` / `plotly`)
- `src/evaluation/visualization/styles.py`
  - shared seaborn/matplotlib style config
- `src/evaluation/visualization/report.py`
  - optional index markdown/html summary generation
- `src/evaluation/visualize_metrics_cli.py`
  - argparse entrypoint wiring all pieces

Design principle:

- All plotting functions accept DataFrame + explicit parameters, return `(fig, ax)` and never read files directly.
- CLI handles file I/O and orchestration only.
- For Plotly backend, plotting functions should return a Plotly Figure object; save logic should write HTML (and image where available).

---

## 8) Configuration and extensibility

### 8.1 Optional visualization config file

Support `--viz-config <yaml>` to define defaults:

- default metric
- palette
- grouping priorities
- model-family mapping rules
- output formats
- top columns for confusion analysis

### 8.2 Metric selector map

Create centralized map:

- user metric key → column in normalized table + semantic type (higher-is-better, [0,1] or unbounded)

This enables future metrics without changing plotting code.

---

## 9) Edge cases and handling strategy

1. Missing `metadata.llm_model`/provider in metrics:
   - infer from experiment name or run config; fallback to `unknown`.

2. Different column sets across runs:
   - `union` mode (missing values shown as NaN/gray)
   - `intersection` mode for strict comparison.

3. Repeated runs with same labels:
   - keep run-level table + grouped aggregate views.

4. Sparse confusion matrices with many labels:
   - top-N + `OTHER` bucket.

5. Invalid/corrupt metrics.json:
   - skip with warning, collect in `skipped_files.csv`.

6. Mixed tasks (future multi-table):
   - include `task_id` field in internal schema from experiment metadata/filepath pattern.

7. Plot readability with many runs/columns:
   - auto figure sizing
   - label wrapping/rotation
   - optional filtered subsets.

---

## 10) Validation strategy

### 10.1 Functional validation on current Gemini pair

Use:

- codeact gemini metrics
- bdikit-context gemini metrics

Checks:

- bars reflect known performance gap
- heatmap rows include both runs
- confusion plot renders for selected problematic columns
- generated CSV tables contain expected columns and values.

### 10.2 Robustness checks

- run with one metrics file only
- run with intentionally missing metadata
- run with multiple repeated files for same model/context.

---

## 11) Deliverables (phase 1)

1. CLI script with subcommands: `summarize`, `bars`, `heatmap`, `confusion`, `compare`.
2. Reusable visualization package modules under `src/evaluation/visualization/`.
3. Output bundle structure:
   - `plots/*.(png|svg|pdf|html)`
   - `tables/*.csv`
   - `manifest.json` (inputs, options, generated artifacts)
4. Minimal docs:
   - usage examples
   - metric names supported
   - grouping examples.

---

## 12) Phase 2 (interactive notebook integration)

After CLI is stable:

1. Create notebook helper API that imports the same `io/normalize/plots` functions.
2. Provide starter notebook:
   - load run set
   - interactive filtering/grouping cells
   - quick redraw of bar/heatmap/confusion.
3. Keep notebook thin; no duplicated plotting logic.

---

## 13) Implementation sequence (recommended)

1. Build loader + schema validation + tidy normalization.
2. Add metadata enrichment and canonical labeling.
3. Implement `summarize` + CSV exports.
4. Implement global barplots.
5. Implement per-column heatmap with annotation strips.
6. Implement confusion matrix plotting.
7. Add `compare` orchestration command.
8. Add docs/examples and run validation on Gemini CodeAct vs BDI-kit.

---

## 14) Immediate assumptions (for first implementation)

- Metrics files are produced by current `run_experiment.py` pipeline.
- Single-table task comparisons are the focus; task-level disambiguation can be inferred from path names initially.
- Seaborn + Matplotlib are acceptable plotting backend for phase 1.
- Static plots are sufficient first; interactivity will be notebook-based using same core functions.

---

## 15) Success criteria

The first CLI version is complete when:

1. It can compare at least the two latest Gemini runs end-to-end.
2. It generates:
   - global metric barplots,
   - per-column metric heatmap,
   - at least one confusion matrix.
3. Grouping by model/context/model_family works from CLI options.
4. Outputs are reproducible and notebook-ready (CSV + clean function API).
