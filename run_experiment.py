#!/usr/bin/env python3
"""
CLI entry point for running automated Beaker experiments.

Usage:
    # Start Beaker server first:
    ./exec_apptainer_harmonia.sh &

    # Then run experiment:
    python run_experiment.py --config experiments/configs/dou_harmonization.yaml

    # With custom server URL and token:
    python run_experiment.py --config experiments/configs/dou_harmonization.yaml \
                             --server http://localhost:8100 \
                             --token your_token_here
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from automation import BeakerClient, ExperimentRunner, load_config


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run automated Beaker experiments",
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

    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Run in interactive mode (pause between turns)",
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="Default timeout for requests in seconds (default: 300)",
    )

    return parser.parse_args()


def on_turn_complete(turn: int, message: str, response) -> None:
    """Callback to print progress during experiment."""
    status_icon = "✓" if response.response_type == "llm_response" else "⚠"
    print(f"  {status_icon} Turn {turn}: {response.response_type} ({response.duration_seconds:.1f}s)")


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
        return 1

    # Load configuration
    print(f"Loading config: {args.config}")
    config = load_config(args.config)
    print(f"  Experiment: {config.name}")
    print(f"  LLM: {config.llm.provider}/{config.llm.model}")
    print(f"  Messages: {len(config.messages)}")

    # Create client and run experiment
    print(f"\nConnecting to Beaker server: {args.server}")

    client = BeakerClient(
        server_url=args.server,
        token=args.token,
        timeout=args.timeout,
    )

    try:
        await client.connect()
        print(f"  Connected to kernel: {client.kernel_id}")

        # Create runner
        runner = ExperimentRunner(
            client=client,
            config=config,
            output_dir=args.output_dir,
            on_turn_complete=on_turn_complete,
        )

        # Run experiment
        print(f"\nRunning experiment...")
        if args.interactive:
            print("  (Interactive mode - press Enter after each turn)")

        output_dir = await runner.run(interactive=args.interactive)

        print(f"\n✓ Experiment complete!")
        print(f"  Output directory: {output_dir}")
        print(f"  - trace.json: Full execution trace")
        print(f"  - conversation.md: Simplified conversation log")

        return 0

    except ConnectionError as e:
        print(f"\nError connecting to server: {e}")
        print("Make sure the Beaker server is running:")
        print("  ./exec_apptainer_harmonia.sh")
        return 1

    except Exception as e:
        print(f"\nError running experiment: {e}")
        return 1

    finally:
        await client.disconnect()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
