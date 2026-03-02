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
import json
import os
import shutil
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


def _load_json(path) -> dict | None:
    """Load JSON file, return None if not found."""
    if path is None:
        return None
    path = Path(path)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def on_turn_complete(turn: int, message: str, response) -> None:
    """Callback to print progress during experiment."""
    status_icon = "✓" if response.response_type == "llm_response" else "⚠"
    print(f"  {status_icon} Turn {turn}: {response.response_type} ({response.duration_seconds:.1f}s)")


def _resolve_required_artifacts(output_dir: Path, config) -> tuple[Path | None, list[Path]]:
    llm_output = output_dir / "dou_harmonized.csv"
    if not llm_output.exists():
        nested_output = output_dir / "results" / "dou_harmonized.csv"
        if nested_output.exists():
            llm_output = nested_output

    mapping_files: list[Path] = []
    if config.evaluation:
        if config.evaluation.column_mapping_file:
            mapping_files.append(output_dir / config.evaluation.column_mapping_file)
        if config.evaluation.value_mapping_file:
            mapping_files.append(output_dir / config.evaluation.value_mapping_file)
    return (llm_output if llm_output.exists() else None), mapping_files


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
        await client.connect(context_name=config.context)
        print(f"  Connected to kernel: {client.kernel_id}")
        if config.context:
            print(f"  Context: {config.context}")

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

        # Keep prompt composition adjacent to trace/metrics if written to run parent dir by context logger.
        prompt_src = output_dir.parent / "full_prompt_composition.json"
        prompt_dst = output_dir / "full_prompt_composition.json"
        if not prompt_dst.exists() and prompt_src.exists():
            shutil.copy2(prompt_src, prompt_dst)

        print(f"\n✓ Experiment complete!")
        print(f"  Output directory: {output_dir}")
        print(f"  - trace.json: Full execution trace")
        print(f"  - conversation.md: Simplified conversation log")

        llm_output, mapping_files = _resolve_required_artifacts(output_dir, config)
        missing_artifacts = []
        if llm_output is None:
            missing_artifacts.append("dou_harmonized.csv")
        missing_artifacts.extend(str(p.relative_to(output_dir)) for p in mapping_files if not p.exists())
        if missing_artifacts:
            print("  ✗ Required output artifacts missing:")
            for artifact in missing_artifacts:
                print(f"    - {artifact}")
            return 1

        # Calculate metrics if evaluation config is present
        if config.evaluation and config.evaluation.gold_standard:
            print(f"\nCalculating metrics...")
            try:
                from evaluation.metrics import calculate_all_metrics
                from evaluation.schemas import MetricsResult

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

                llm_output, _ = _resolve_required_artifacts(output_dir, config)

                # Check for value mapping file
                llm_value_mapping_path = output_dir / config.evaluation.value_mapping_file
                value_mapping_found = llm_value_mapping_path.exists() if config.evaluation.value_mapping_file else False

                if llm_output and llm_output.exists():
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
                    print(f"  - metrics.json: Harmonization metrics")
                else:
                    print("  ⚠ LLM output CSV not found")
                    print(f"  Skipping metrics calculation.")
            except Exception as e:
                print(f"  ⚠ Error calculating metrics: {e}")
                # Don't fail the whole experiment just because metrics failed

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
