#!/usr/bin/env python3
"""
CLI entry point for running manual Beaker experiments with logging.

Note: this is started from exec_apptainer_harmonia.sh with the --monitor flag
so no need to run it manually.

This script can either:
1. Start the Beaker server with experiment-specific paths AND monitor it (--start-server)
2. Connect to an already running Beaker server and monitor it (default)

Usage:
    # Full workflow: start server + monitor (recommended)
    python run_manual_experiment.py --config configs/manual/config.yaml --start-server

    # Or two-terminal workflow:
    # Terminal 1: Start Beaker server
    ./exec_apptainer_harmonia.sh --config configs/manual/config.yaml

    # Terminal 2: Start the monitor
    python run_manual_experiment.py --config configs/manual/config.yaml

    # Interact with Beaker via the web UI at http://<host>:8100
    # When done, press Ctrl+C to stop monitoring and save logs

The output will be saved to:
    results/<experiment_name>_<timestamp>/
    ├── trace.json        # Full execution trace with raw messages
    └── conversation.md   # Human-readable conversation log
"""

import argparse
import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from automation import ManualExperimentRunner, load_config


def _load_json(path) -> dict | None:
    """Load JSON file, return None if not found."""
    if path is None:
        return None
    path = Path(path)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run manual Beaker experiments with logging",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--config",
        "-c",
        required=True,
        type=Path,
        help="Path to experiment configuration YAML file",
    )

    parser.add_argument(
        "--start-server",
        action="store_true",
        help="Start Beaker server with experiment-specific paths (recommended)",
    )

    parser.add_argument(
        "--server",
        "-s",
        default=os.environ.get("JUPYTER_SERVER", "http://localhost:8100"),
        help="Beaker server URL (default: http://localhost:8100 or JUPYTER_SERVER env)",
    )

    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=8100,
        help="Port for Beaker server (default: 8100)",
    )

    parser.add_argument(
        "--token",
        "-t",
        default=os.environ.get("JUPYTER_TOKEN"),
        help="Jupyter authentication token (default: JUPYTER_TOKEN env)",
    )

    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        help="Override output directory from config",
    )

    parser.add_argument(
        "--global-results",
        action="store_true",
        help="Use global results dir instead of experiment-specific (not recommended)",
    )

    return parser.parse_args()


def create_experiment_output_dir(config, output_dir_override: Path = None) -> Path:
    """Create experiment-specific output directory."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = os.environ.get("RUN_ID", "")
    slurm_id = os.environ.get("SLURM_JOB_ID", os.environ.get("SLURM_JOBID", "manual"))
    base_dir = Path(output_dir_override or config.output.base_dir)
    name_parts = [timestamp, config.name, slurm_id]
    if run_id:
        name_parts.append(run_id)
    output_dir = base_dir / "_".join(name_parts)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def start_beaker_server(
    config_file: Path,
    results_dir: Path,
    port: int,
    script_dir: Path,
) -> subprocess.Popen:
    """Start Beaker server with experiment-specific results directory."""
    exec_script = script_dir / "exec_apptainer_harmonia.sh"

    if not exec_script.exists():
        raise FileNotFoundError(f"exec_apptainer_harmonia.sh not found at {exec_script}")

    cmd = [
        str(exec_script),
        "--config", str(config_file),
        "--results-dir", str(results_dir),
        "--port", str(port),
        "--job-name", results_dir.name,  # Use output dir name for log naming
    ]

    print("Starting Beaker server...")
    print(f"  Command: {' '.join(cmd)}")
    print(f"  Results dir: {results_dir}")
    print()

    # Start server in subprocess
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    return process


def wait_for_server(server_url: str, token: str, timeout: int = 300) -> bool:
    """Wait for Beaker server to be ready."""
    import urllib.error
    import urllib.request

    start_time = time.time()
    check_url = f"{server_url}/api/sessions"

    print(f"Waiting for Beaker server to be ready (up to {timeout}s)...")
    print("  (Local LLM model loading can take 2-4 minutes)")

    while time.time() - start_time < timeout:
        try:
            req = urllib.request.Request(
                check_url,
                headers={"Authorization": f"token {token}"}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    elapsed = int(time.time() - start_time)
                    print(f"  Server ready after {elapsed}s")
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            pass

        # Print progress every 30 seconds
        elapsed = int(time.time() - start_time)
        if elapsed % 30 == 0 and elapsed > 0:
            print(f"  Still waiting... ({elapsed}s)")

        time.sleep(5)

    return False


async def run_monitor(
    server_url: str,
    token: str,
    config,
    output_dir: Path,
) -> int:
    """Run the experiment monitor."""
    runner = ManualExperimentRunner(
        server_url=server_url,
        token=token,
        config=config,
        output_dir=output_dir,
    )

    # Set up signal handler for graceful shutdown
    def signal_handler(signum, frame):
        print("\n\nReceived interrupt signal...")
        runner.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        print(f"\nConnecting to Beaker server: {server_url}")
        await runner.start()

        # Calculate metrics if evaluation config is present
        if config.evaluation and config.evaluation.gold_standard:
            print("\nCalculating metrics...")
            try:
                from evaluation.metrics import calculate_all_metrics

                # Load gold standard files
                gold_column_mapping = _load_json(config.evaluation.gold_column_mapping)
                gold_value_mapping = _load_json(config.evaluation.gold_value_mapping)
                acceptable_columns = _load_json(config.evaluation.acceptable_columns_file)

                # Load LLM-produced mappings (if they exist)
                llm_column_mapping_path = output_dir / config.evaluation.column_mapping_file
                llm_column_mapping = _load_json(llm_column_mapping_path) if llm_column_mapping_path.exists() else None

                # Load trace.json for metadata
                trace_path = output_dir / "trace.json"
                trace_data = _load_json(trace_path) if trace_path.exists() else None

                # Find LLM output CSV
                llm_output = output_dir / "dou_harmonized.csv"

                # Check for value mapping file
                llm_value_mapping_path = output_dir / config.evaluation.value_mapping_file
                value_mapping_found = llm_value_mapping_path.exists() if config.evaluation.value_mapping_file else False

                if llm_output.exists():
                    result = calculate_all_metrics(
                        gold_standard_csv=Path(config.evaluation.gold_standard),
                        llm_output_csv=llm_output,
                        gold_column_mapping=gold_column_mapping,
                        llm_column_mapping=llm_column_mapping,
                        gold_value_mapping=gold_value_mapping,
                        acceptable_columns=acceptable_columns,
                        index_column=config.evaluation.index_column,
                        numeric_tolerance=config.evaluation.numeric_tolerance,
                        trace_json=trace_data,
                        value_mapping_file_found=value_mapping_found,
                    )

                    metrics_path = output_dir / "metrics.json"
                    metrics_path.write_text(result.model_dump_json(indent=2))
                    print(f"  ✓ Metrics saved to: {metrics_path}")
                    print("  - metrics.json: Harmonization metrics")
                else:
                    print(f"  ⚠ LLM output CSV not found at {llm_output}")
                    print("  Skipping metrics calculation.")
            except Exception as e:
                print(f"  ⚠ Error calculating metrics: {e}")
                # Don't fail the whole experiment just because metrics failed

        return 0

    except ConnectionError as e:
        print(f"\nError connecting to server: {e}")
        print("")
        print("Make sure the Beaker server is running:")
        print("  ./exec_apptainer_harmonia.sh --config <your_config.yaml>")
        return 1

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return 1


async def main() -> int:
    """Main entry point."""
    args = parse_args()
    script_dir = Path(__file__).parent

    # Validate config file exists
    if not args.config.exists():
        print(f"Error: Config file not found: {args.config}")
        return 1

    # Load configuration
    print(f"Loading config: {args.config}")
    config = load_config(args.config)
    print(f"  Experiment: {config.name}")
    print(f"  LLM: {config.llm.provider}/{config.llm.model}")

    if config.manual_mode:
        print("  Mode: Manual (interactive)")
    else:
        print(f"  Mode: Automated ({len(config.messages)} messages)")
        print("")
        print("Note: This config has automated messages defined.")
        print("For automated experiments, use: python run_experiment.py --config ...")
        print("Continuing with manual monitoring anyway...")

    # Create experiment-specific output directory
    output_dir = create_experiment_output_dir(config, args.output_dir)
    print(f"  Output: {output_dir}")

    # Determine results dir to pass to server
    if args.global_results:
        # Use global results dir (backward compatible)
        results_dir = Path(config.output.base_dir)
        print(f"  Using global results dir: {results_dir}")
    else:
        # Use experiment-specific dir (recommended)
        results_dir = output_dir
        print("  Using experiment-specific results dir")

    beaker_process = None
    server_output_lines = []

    try:
        if args.start_server:
            # Start server ourselves
            beaker_process = start_beaker_server(
                config_file=args.config,
                results_dir=results_dir,
                port=args.port,
                script_dir=script_dir,
            )

            # Read server output until we see the token or it's ready
            token = args.token
            server_url = f"http://localhost:{args.port}"

            # Read initial output to capture token
            print("Server output:")
            print("-" * 60)

            def read_output():
                """Read server output in background."""
                for line in beaker_process.stdout:
                    server_output_lines.append(line)
                    print(f"  {line}", end="")
                    # Look for token in output
                    if "token=" in line and not token:
                        # Extract token from URL
                        import re
                        match = re.search(r"token=([a-f0-9]+)", line)
                        if match:
                            return match.group(1)
                return None

            # Start reading output in thread
            import threading
            output_thread = threading.Thread(target=read_output, daemon=True)
            output_thread.start()

            # Wait a bit for server to start outputting
            time.sleep(5)

            # Try to get token from env file if not provided
            if not token:
                env_file = args.config.with_suffix("").with_name(
                    args.config.stem + "_associated.env"
                )
                if env_file.exists():
                    with open(env_file) as f:
                        for line in f:
                            if line.startswith("JUPYTER_TOKEN="):
                                token = line.strip().split("=", 1)[1]
                                break

            if not token:
                # Check the base .env file
                base_env = script_dir / ".env"
                if base_env.exists():
                    with open(base_env) as f:
                        for line in f:
                            if line.startswith("JUPYTER_TOKEN="):
                                token = line.strip().split("=", 1)[1]
                                break

            if not token:
                print("\nError: Could not determine authentication token.")
                print("Set JUPYTER_TOKEN environment variable or use --token flag.")
                return 1

            print("-" * 60)
            print(f"Token: {token[:20]}...")
            print(f"Server URL: {server_url}")

            # Wait for server to be ready
            if not wait_for_server(server_url, token, timeout=300):
                print("\nError: Beaker server failed to start within timeout")
                print("Check the server output above for errors.")
                return 1

            print()
            print("=" * 60)
            print("Beaker is ready! Connect via browser:")
            print(f"  {server_url}/?token={token}")
            print("=" * 60)
            print()

            args.server = server_url
            args.token = token

        else:
            # Connect to existing server
            if not args.token:
                print("Error: No authentication token provided.")
                print("Set JUPYTER_TOKEN environment variable or use --token flag.")
                print("")
                print("You can find the token in the Beaker server output, or in your .env file.")
                return 1

        # Run the monitor
        return await run_monitor(
            server_url=args.server,
            token=args.token,
            config=config,
            output_dir=output_dir,
        )

    finally:
        if beaker_process:
            print("\nShutting down Beaker server...")
            beaker_process.terminate()
            try:
                beaker_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                beaker_process.kill()
            print("Server stopped.")


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
