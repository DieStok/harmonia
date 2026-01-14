#!/usr/bin/env python3
"""
Generate SBATCH job scripts from experiment configurations.

Usage:
    # Generate job for a single config:
    python generate_jobs.py --config experiments/configs/dou_harmonization.yaml

    # Generate jobs for all configs in a directory:
    python generate_jobs.py --config-dir experiments/configs/

    # Customize SLURM parameters:
    python generate_jobs.py --config experiments/configs/dou_harmonization.yaml \
                            --time 02:00:00 --memory 16G --tmpspace 60
"""

import argparse
import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from automation import load_config


# Default SLURM parameters
DEFAULTS = {
    "time_limit": "01:00:00",
    "memory": "8G",
    "cpus": "2",
    "timeout": "300",
    "tmpspace": "1",
}


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate SBATCH job scripts for Harmonia experiments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--config",
        "-c",
        type=Path,
        help="Path to single experiment config YAML",
    )
    group.add_argument(
        "--config-dir",
        "-d",
        type=Path,
        help="Directory containing experiment configs (generates job for each)",
    )

    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=Path("jobs"),
        help="Output directory for job scripts (default: jobs/)",
    )

    parser.add_argument(
        "--template",
        "-t",
        type=Path,
        default=Path("sbatch_template.sh"),
        help="Path to SBATCH template (default: sbatch_template.sh)",
    )

    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Path to .env file (default: .env)",
    )

    parser.add_argument(
        "--time",
        default=DEFAULTS["time_limit"],
        help=f"SLURM time limit (default: {DEFAULTS['time_limit']})",
    )

    parser.add_argument(
        "--memory",
        default=DEFAULTS["memory"],
        help=f"SLURM memory allocation (default: {DEFAULTS['memory']})",
    )

    parser.add_argument(
        "--cpus",
        type=int,
        default=int(DEFAULTS["cpus"]),
        help=f"SLURM CPUs per task (default: {DEFAULTS['cpus']})",
    )

    parser.add_argument(
        "--tmpspace",
        type=int,
        default=int(DEFAULTS["tmpspace"]),
        help=f"SLURM tmpspace in GB (default: {DEFAULTS['tmpspace']})",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=int(DEFAULTS["timeout"]),
        help=f"Experiment timeout in seconds (default: {DEFAULTS['timeout']})",
    )

    parser.add_argument(
        "--gpu",
        action="store_true",
        help="Use GPU template (sbatch_template_gpu.sh) for Ollama jobs",
    )

    return parser.parse_args()


def generate_job_script(
    config_path: Path,
    template_path: Path,
    output_dir: Path,
    env_file: Path,
    project_dir: Path,
    time_limit: str,
    memory: str,
    cpus: int,
    tmpspace: int,
    timeout: int,
) -> Path:
    """Generate a single job script from config and template."""
    # Load config to get experiment name and LLM settings
    config = load_config(config_path)

    # Read template
    template = template_path.read_text()

    # Check for SSL cert in env file
    ssl_bind = ""
    if env_file.exists():
        env_content = env_file.read_text()
        for line in env_content.split("\n"):
            if line.startswith("SSL_CERT_FILE="):
                ssl_path = line.split("=", 1)[1].strip()
                if ssl_path and Path(ssl_path).exists():
                    ssl_bind = f"--bind {ssl_path}:{ssl_path}:ro"
                break

    # Extract LLM provider and model from config
    # Format: provider/model (e.g., "ollama" + "qwen3-coder:30b" -> "ollama/qwen3-coder:30b")
    llm_provider = config.llm.provider
    llm_model = config.llm.model

    # Format model string for Beaker/Archytas
    # Beaker expects LLM_SERVICE_PROVIDER and LLM_SERVICE_MODEL separately
    # Provider mapping: ollama -> ollama, openrouter -> openrouter, openai -> openai
    llm_service_provider = llm_provider
    llm_service_model = llm_model

    # Replace template variables
    replacements = {
        "{{experiment_name}}": config.name,
        "{{config_path}}": str(config_path),
        "{{project_dir}}": str(project_dir),
        "{{env_file}}": str(env_file),
        "{{time_limit}}": time_limit,
        "{{memory}}": memory,
        "{{cpus}}": str(cpus),
        "{{tmpspace}}": str(tmpspace),
        "{{timeout}}": str(timeout),
        "{{ssl_bind}}": ssl_bind,
        "{{llm_provider}}": llm_service_provider,
        "{{llm_model}}": llm_service_model,
    }

    script = template
    for key, value in replacements.items():
        script = script.replace(key, value)

    # Write output
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{config.name}.sh"
    output_path.write_text(script)
    output_path.chmod(0o755)

    return output_path


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Select template based on --gpu flag
    if args.gpu:
        template_path = Path("sbatch_template_gpu.sh")
    else:
        template_path = args.template

    # Validate template exists
    if not template_path.exists():
        print(f"Error: Template not found: {template_path}")
        return 1

    # Validate env file exists
    if not args.env_file.exists():
        print(f"Warning: .env file not found: {args.env_file}")

    # Get project directory (where this script is)
    project_dir = Path(__file__).parent.absolute()

    # Collect config files
    if args.config:
        if not args.config.exists():
            print(f"Error: Config not found: {args.config}")
            return 1
        config_files = [args.config]
    else:
        if not args.config_dir.exists():
            print(f"Error: Config directory not found: {args.config_dir}")
            return 1
        config_files = list(args.config_dir.glob("*.yaml")) + list(args.config_dir.glob("*.yml"))
        if not config_files:
            print(f"Error: No YAML files found in {args.config_dir}")
            return 1

    # Generate job scripts
    print(f"Generating job scripts...")
    print(f"  Template: {template_path}" + (" (GPU)" if args.gpu else ""))
    print(f"  Output dir: {args.output_dir}")
    print(f"  SLURM: time={args.time}, mem={args.memory}, cpus={args.cpus}, tmpspace={args.tmpspace}G")
    print()

    generated = []
    for config_path in config_files:
        try:
            output_path = generate_job_script(
                config_path=config_path,
                template_path=template_path,
                output_dir=args.output_dir,
                env_file=args.env_file,
                project_dir=project_dir,
                time_limit=args.time,
                memory=args.memory,
                cpus=args.cpus,
                tmpspace=args.tmpspace,
                timeout=args.timeout,
            )
            generated.append(output_path)
            print(f"  ✓ {config_path.name} -> {output_path}")
        except Exception as e:
            print(f"  ✗ {config_path.name}: {e}")

    print()
    print(f"Generated {len(generated)} job script(s).")
    print()
    print("To submit jobs:")
    for path in generated:
        print(f"  sbatch {path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
