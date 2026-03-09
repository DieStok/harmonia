#!/usr/bin/env python3
"""Build Jupyter notebooks from Python source strings using nbformat.

Each notebook is defined as a list of (cell_type, source) tuples.
cell_type is 'markdown' or 'code'.
"""
from pathlib import Path

import nbformat

HERE = Path(__file__).parent


def make_notebook(cells: list[tuple[str, str]], path: Path):
    nb = nbformat.v4.new_notebook()
    nb.metadata.kernelspec = {
        "display_name": "Python 3 (.venv)",
        "language": "python",
        "name": "python3",
    }
    for cell_type, source in cells:
        if cell_type == "markdown":
            nb.cells.append(nbformat.v4.new_markdown_cell(source.strip()))
        else:
            nb.cells.append(nbformat.v4.new_code_cell(source.strip()))
    nbformat.write(nb, path)
    print(f"  wrote {path}")


# ── Notebook 01: Log Analysis ──────────────────────────────────────────
nb01 = [
    ("markdown", """# 1. Log & Trace Analysis

Analyze SLURM logs and trace.json files from Harmonia experiments using the CLI tool.

**Failure mode taxonomy:** 13 categories defined in `types_of_log_and_trace_problems.yaml`
"""),
    ("code", """import os, subprocess, json, textwrap
os.chdir("/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia")

CLI = "code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py"
PYTHON = ".venv/bin/python"
"""),
    ("markdown", "## Quick summary of recent runs"),
    ("code", """result = subprocess.run([PYTHON, CLI], capture_output=True, text=True)
print(result.stdout)
if result.stderr:
    print("STDERR (last 2000 chars):", result.stderr[-2000:])
"""),
    ("markdown", "## Verbose per-turn trace analysis"),
    ("code", """result = subprocess.run([PYTHON, CLI, "--verbose"], capture_output=True, text=True)
print(result.stdout)
if result.stderr:
    print("STDERR (last 2000 chars):", result.stderr[-2000:])
"""),
    ("markdown", "## JSON output for programmatic analysis"),
    ("code", """result = subprocess.run([PYTHON, CLI, "--json"], capture_output=True, text=True)
try:
    data = json.loads(result.stdout)
    for run in data.get("runs", []):
        run_id = run.get("run_id", "?")
        exp = run.get("experiment_name", "?")
        problems = run.get("problems", [])
        status = "OK" if not problems else f"{len(problems)} issue(s)"
        severities = [p.get("severity", "?") for p in problems]
        print(f"  {run_id} | {exp:50s} | {status:15s} | {severities}")
except json.JSONDecodeError:
    print("No valid JSON output")
    print(result.stdout[:2000])
    if result.stderr:
        print("STDERR:", result.stderr[-1000:])
"""),
    ("markdown", """## Analyze a specific run by ID

Change `RUN_ID` below to inspect a particular experiment."""),
    ("code", """RUN_ID = ""  # e.g. "a1b2c3d4"

if RUN_ID:
    result = subprocess.run([PYTHON, CLI, "--run-id", RUN_ID, "--verbose"],
                            capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr[-2000:])
else:
    print("Set RUN_ID above to analyze a specific run.")
"""),
    ("markdown", "## With diagnostics (RCA)"),
    ("code", """result = subprocess.run([PYTHON, CLI, "--diagnostics"], capture_output=True, text=True)
print(result.stdout)
if result.stderr:
    print("STDERR (last 2000 chars):", result.stderr[-2000:])
"""),
]

# ── Notebook 02: Seaborn Evaluation Plots ───────────────────────────────
nb02 = [
    ("markdown", """# 2. Seaborn Evaluation Plots

Generate standard evaluation plots using the **seaborn** (matplotlib) backend:
- Global bar charts (column_mapping_accuracy, avg_value_accuracy, avg_value_f1)
- Per-column performance heatmap
- Confusion matrices per run per column
- Cross-model comparison heatmaps
- Boxplots by model family, local/cloud, cost tier
"""),
    ("code", """import os, subprocess
from pathlib import Path
from IPython.display import Image, display

os.chdir("/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia")
PYTHON = ".venv/bin/python"
RESULTS_GLOB = "results/*/metrics.json"
"""),
    ("markdown", "## Step 1: Calculate metrics for all completed runs"),
    ("code", """# Calculate metrics for each result directory that has a trace.json but no metrics.json
from pathlib import Path
results_dir = Path("results")
for run_dir in sorted(results_dir.iterdir()):
    if not run_dir.is_dir() or run_dir.name in ("old", "older"):
        continue
    metrics_f = run_dir / "metrics.json"
    trace_f = run_dir / "trace.json"
    if trace_f.exists() and not metrics_f.exists():
        print(f"Calculating metrics for {run_dir.name}...")
        r = subprocess.run(
            [PYTHON, "calculate_metrics.py", "--results-dir", str(run_dir), "--verbose"],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            print(f"  OK")
        else:
            print(f"  FAILED (rc={r.returncode})")
            print(r.stderr[-500:] if r.stderr else r.stdout[-500:])
    elif metrics_f.exists():
        print(f"  {run_dir.name}: metrics.json already exists")
"""),
    ("markdown", "## Step 2: Generate standard seaborn plots"),
    ("code", """from datetime import datetime
out_dir = f"analysis/plots_seaborn_{datetime.now().strftime('%Y%m%d_%H%M')}"

cmd = [
    PYTHON, "src/evaluation/make_standard_evaluation_plots.py",
    "--metrics-glob", RESULTS_GLOB,
    "--out-dir", out_dir,
    "--backend", "seaborn",
    "--figure-format", "png",
    "--backfill-row-values",
    "--verbose",
]
print("Running:", " ".join(cmd))
result = subprocess.run(cmd, capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    print("STDERR:", result.stderr[-2000:])
else:
    print(f"\\nPlots saved to: {out_dir}")
"""),
    ("markdown", "## Step 3: Display generated plots"),
    ("code", """# Find and display all PNG plots
plots_dir = Path(out_dir) / "plots"
if plots_dir.exists():
    png_files = sorted(plots_dir.glob("*.png"))
    print(f"Found {len(png_files)} top-level plots\\n")
    for png in png_files:
        print(f"--- {png.name} ---")
        display(Image(filename=str(png), width=800))
else:
    print(f"No plots directory at {plots_dir}")
"""),
    ("markdown", "## Step 4: Display confusion matrices (sample)"),
    ("code", """# Show first 3 confusion matrices from each model subfolder
cm_dir = Path(out_dir) / "plots" / "confusion_matrices"
if cm_dir.exists():
    for model_dir in sorted(cm_dir.iterdir()):
        if model_dir.is_dir():
            pngs = sorted(model_dir.glob("*.png"))[:3]
            for png in pngs:
                print(f"--- {model_dir.name}/{png.name} ---")
                display(Image(filename=str(png), width=600))
else:
    print("No confusion matrices directory found")
"""),
    ("markdown", "## Step 5: Inspect saved data tables"),
    ("code", """import pandas as pd

tables_dir = Path(out_dir) / "tables"
if tables_dir.exists():
    for csv_f in sorted(tables_dir.glob("*.csv")):
        df = pd.read_csv(csv_f)
        print(f"\\n{'='*60}")
        print(f"{csv_f.name}: {df.shape[0]} rows x {df.shape[1]} cols")
        print(f"{'='*60}")
        display(df.head(10))
else:
    print("No tables directory found")
"""),
]

# ── Notebook 03: Plotly Evaluation Plots ────────────────────────────────
nb03 = [
    ("markdown", """# 3. Plotly Evaluation Plots

Generate interactive evaluation plots using the **plotly** backend.
Plots are saved as HTML files for interactive exploration.
"""),
    ("code", """import os, subprocess
from pathlib import Path
from IPython.display import HTML, display, IFrame

os.chdir("/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia")
PYTHON = ".venv/bin/python"
RESULTS_GLOB = "results/*/metrics.json"
"""),
    ("markdown", "## Step 1: Generate standard plotly plots"),
    ("code", """from datetime import datetime
out_dir = f"analysis/plots_plotly_{datetime.now().strftime('%Y%m%d_%H%M')}"

cmd = [
    PYTHON, "src/evaluation/make_standard_evaluation_plots.py",
    "--metrics-glob", RESULTS_GLOB,
    "--out-dir", out_dir,
    "--backend", "plotly",
    "--figure-format", "html",
    "--backfill-row-values",
    "--verbose",
]
print("Running:", " ".join(cmd))
result = subprocess.run(cmd, capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    print("STDERR:", result.stderr[-2000:])
else:
    print(f"\\nPlots saved to: {out_dir}")
"""),
    ("markdown", "## Step 2: Display interactive plotly plots"),
    ("code", """# Load and display plotly HTML files inline
plots_dir = Path(out_dir) / "plots"
if plots_dir.exists():
    html_files = sorted(plots_dir.glob("*.html"))
    print(f"Found {len(html_files)} interactive plots\\n")
    for html_f in html_files:
        print(f"--- {html_f.name} ---")
        # IFrame works well in Jupyter for HTML plots
        display(IFrame(src=str(html_f), width="100%", height=500))
else:
    print(f"No plots directory at {plots_dir}")
"""),
    ("markdown", "## Step 3: Use visualize_metrics_cli.py for individual plot types"),
    ("code", """# Example: interactive bar chart for a specific metric
cmd = [
    PYTHON, "src/evaluation/visualize_metrics_cli.py",
    "bars",
    "--metric", "avg_value_accuracy_excl_empty",
    "--metrics-glob", RESULTS_GLOB,
    "--interactive",
    "--figure-format", "html",
    "--out-dir", out_dir + "/cli_plots",
]
result = subprocess.run(cmd, capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    print("STDERR:", result.stderr[-1000:])
"""),
    ("code", """# Example: interactive heatmap
cmd = [
    PYTHON, "src/evaluation/visualize_metrics_cli.py",
    "heatmap",
    "--metric", "accuracy_excl_empty",
    "--metrics-glob", RESULTS_GLOB,
    "--interactive",
    "--figure-format", "html",
    "--out-dir", out_dir + "/cli_plots",
]
result = subprocess.run(cmd, capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    print("STDERR:", result.stderr[-1000:])
"""),
    ("code", """# Example: cross-model comparison
cmd = [
    PYTHON, "src/evaluation/visualize_metrics_cli.py",
    "cross-compare",
    "--metrics-glob", RESULTS_GLOB,
    "--interactive",
    "--figure-format", "html",
    "--out-dir", out_dir + "/cli_plots",
]
result = subprocess.run(cmd, capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    print("STDERR:", result.stderr[-1000:])
"""),
    ("markdown", "## Step 4: Inspect data tables"),
    ("code", """import pandas as pd

tables_dir = Path(out_dir) / "tables"
if tables_dir.exists():
    for csv_f in sorted(tables_dir.glob("*.csv")):
        df = pd.read_csv(csv_f)
        print(f"\\n{'='*60}")
        print(f"{csv_f.name}: {df.shape[0]} rows x {df.shape[1]} cols")
        print(f"{'='*60}")
        display(df.head(10))
else:
    print("No tables directory found")
"""),
]

# ── Notebook 04: Dashboard ──────────────────────────────────────────────
nb04 = [
    ("markdown", """# 4. Interactive Dash Dashboard

Launch the Harmonia experiment dashboard for interactive exploration of results.

The dashboard has 5 tabs:
1. **Overview** — Runs table with summary stats
2. **Metrics** — Bar charts, heatmaps, scatter plots
3. **Trace Explorer** — Deep-dive into individual run traces
4. **Token & Cost** — Token usage and cost analysis
5. **Comparison** — Side-by-side run comparison
"""),
    ("code", """import os, subprocess, socket, time, webbrowser
from pathlib import Path

os.chdir("/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia")
PYTHON = ".venv/bin/python"
RESULTS_DIR = "results/"
"""),
    ("markdown", """## Check what data is available for the dashboard"""),
    ("code", """# List results directories with metrics.json
results_path = Path(RESULTS_DIR)
runs_with_metrics = []
runs_without_metrics = []
for d in sorted(results_path.iterdir()):
    if not d.is_dir() or d.name in ("old", "older"):
        continue
    if (d / "metrics.json").exists():
        runs_with_metrics.append(d.name)
    elif (d / "trace.json").exists():
        runs_without_metrics.append(d.name)

print(f"Runs with metrics.json (ready for dashboard): {len(runs_with_metrics)}")
for r in runs_with_metrics:
    print(f"  ✓ {r}")

if runs_without_metrics:
    print(f"\\nRuns with trace but no metrics (need calculate_metrics.py): {len(runs_without_metrics)}")
    for r in runs_without_metrics:
        print(f"  ⚠ {r}")
"""),
    ("markdown", """## Find a free port and launch the dashboard

The dashboard binds to `0.0.0.0` so it's accessible from outside.
To access from your local machine, set up SSH port forwarding:

```bash
ssh -L 8050:<hostname>:8050 <hpc-login>
```

Then open http://localhost:8050 in your browser.
"""),
    ("code", """def find_free_port(start=8050, end=8099):
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port in {start}-{end}")

port = find_free_port()
hostname = socket.gethostname()
print(f"Will use port {port} on {hostname}")
print(f"\\nTo access from your local machine, run:")
print(f"  ssh -L {port}:{hostname}:{port} <your-hpc-login>")
print(f"\\nThen open: http://localhost:{port}")
"""),
    ("code", """# Launch the dashboard as a background subprocess
# (It will keep running until you stop the kernel or kill the process)

proc = subprocess.Popen(
    [PYTHON, "src/dashboard/app.py",
     "--results-dir", RESULTS_DIR,
     "--port", str(port)],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)

# Wait a moment and show initial output
import time
time.sleep(3)

# Read any available output
import select
import io

print(f"Dashboard PID: {proc.pid}")
print(f"Dashboard should be starting on port {port}...")
print(f"\\nAccess via: http://localhost:{port}")
print(f"SSH tunnel: ssh -L {port}:{hostname}:{port} <your-hpc-login>")
print(f"\\nTo stop: proc.terminate() or restart this kernel")
"""),
    ("markdown", "## Check dashboard status"),
    ("code", """# Check if the dashboard is still running
if proc.poll() is None:
    print(f"Dashboard is running (PID {proc.pid})")
    print(f"Access: http://localhost:{port}")
else:
    print(f"Dashboard exited with code {proc.returncode}")
    out = proc.stdout.read()
    print(out[-3000:] if len(out) > 3000 else out)
"""),
    ("markdown", "## Stop the dashboard"),
    ("code", """# Uncomment to stop:
# proc.terminate()
# proc.wait()
# print("Dashboard stopped")
"""),
]


if __name__ == "__main__":
    print("Building notebooks...")
    make_notebook(nb01, HERE / "01_log_analysis.ipynb")
    make_notebook(nb02, HERE / "02_seaborn_evaluation_plots.ipynb")
    make_notebook(nb03, HERE / "03_plotly_evaluation_plots.ipynb")
    make_notebook(nb04, HERE / "04_dashboard.ipynb")
    print("Done!")
