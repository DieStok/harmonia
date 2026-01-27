#!/usr/bin/env python3
"""
CLI entry point for monitoring manual Beaker experiments with logging.

This script connects to a running Beaker server and monitors all WebSocket
traffic, logging user messages and agent responses to trace.json and
conversation.md files - just like automated experiments.

Usage:
    # Start Beaker server first (in one terminal):
    ./exec_apptainer_harmonia.sh --config configs/manual/dou_harmonization_manual_devstral.yaml

    # Start the monitor (in another terminal):
    python run_manual_experiment.py --config configs/manual/dou_harmonization_manual_devstral.yaml

    # Interact with Beaker via the web UI at http://<host>:8100
    # When done, press Ctrl+C to stop monitoring and save logs

The output will be saved to:
    results/<experiment_name>_<timestamp>/
    ├── trace.json        # Full execution trace with raw messages
    └── conversation.md   # Human-readable conversation log
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from automation import load_config, ManualExperimentRunner


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Monitor manual Beaker experiments and log interactions",
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
        "--server",
        "-s",
        default=os.environ.get("JUPYTER_SERVER", "http://localhost:8100"),
        help="Beaker server URL (default: http://localhost:8100 or JUPYTER_SERVER env)",
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

    return parser.parse_args()


async def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Validate config file exists
    if not args.config.exists():
        print(f"Error: Config file not found: {args.config}")
        return 1

    # Validate token
    if not args.token:
        print("Error: No authentication token provided.")
        print("Set JUPYTER_TOKEN environment variable or use --token flag.")
        print("")
        print("You can find the token in the Beaker server output, or in your .env file.")
        return 1

    # Load configuration
    print(f"Loading config: {args.config}")
    config = load_config(args.config)
    print(f"  Experiment: {config.name}")
    print(f"  LLM: {config.llm.provider}/{config.llm.model}")

    if config.manual_mode:
        print(f"  Mode: Manual (interactive)")
    else:
        print(f"  Mode: Automated ({len(config.messages)} messages)")
        print("")
        print("Note: This config has automated messages defined.")
        print("For automated experiments, use: python run_experiment.py --config ...")
        print("Continuing with manual monitoring anyway...")

    # Create runner
    runner = ManualExperimentRunner(
        server_url=args.server,
        token=args.token,
        config=config,
        output_dir=args.output_dir,
    )

    # Set up signal handler for graceful shutdown
    import signal

    def signal_handler(signum, frame):
        print("\n\nReceived interrupt signal...")
        runner.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        print(f"\nConnecting to Beaker server: {args.server}")
        await runner.start()
        return 0

    except ConnectionError as e:
        print(f"\nError connecting to server: {e}")
        print("")
        print("Make sure the Beaker server is running:")
        print("  ./exec_apptainer_harmonia.sh --config <your_config.yaml>")
        return 1

    except Exception as e:
        print(f"\nError: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
