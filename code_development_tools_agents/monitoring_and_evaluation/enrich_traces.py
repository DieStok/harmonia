#!/usr/bin/env python3
"""
Enrich existing trace.json files with classified code executions.

Migrates old traces (which have a single `code_executions` list mixing Beaker
internal and agent code) to the new format with separate `agent_code_executions`
and `internal_code_executions` fields. Also regenerates conversation.md with
agent code executions included.

Usage:
    # Preview changes without writing (dry run)
    python enrich_traces.py --dry-run results/

    # Enrich all traces under a results directory
    python enrich_traces.py results/

    # Enrich a specific trace file
    python enrich_traces.py results/20260312_experiment_12345_b0e6e2a0/trace.json

    # Re-process already-migrated traces
    python enrich_traces.py --force results/
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

# Add repo root to sys.path so we can import from src.automation
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.automation.logger import ConversationLogger  # noqa: E402
from src.automation.tracing import classify_code_execution, extract_code_executions  # noqa: E402


def classify_existing_executions(code_executions: list[dict]) -> dict[str, list[dict]]:
    """Classify an existing code_executions list (fallback when raw_messages unavailable)."""
    agent = []
    internal = []
    for ce in code_executions:
        category = classify_code_execution(ce.get("code", ""))
        if category == "agent":
            agent.append(ce)
        else:
            internal.append({**ce, "category": category})
    return {"agent_code_executions": agent, "internal_code_executions": internal}


def enrich_trace(trace_path: Path, dry_run: bool, force: bool) -> dict:
    """Enrich a single trace.json. Returns stats dict."""
    trace = json.loads(trace_path.read_text())
    turns = trace.get("turns", [])

    stats = {
        "path": str(trace_path),
        "turns": len(turns),
        "total_old": 0,
        "agent": 0,
        "internal": 0,
        "skipped": False,
        "modified": False,
    }

    for turn in turns:
        # Skip if already migrated (unless --force)
        if "agent_code_executions" in turn and not force:
            stats["skipped"] = True
            continue

        # Prefer re-extraction from raw_messages
        if turn.get("raw_messages"):
            classified = extract_code_executions(turn["raw_messages"])
        elif turn.get("code_executions"):
            # Fallback: classify existing code_executions by code content
            classified = classify_existing_executions(turn["code_executions"])
        else:
            classified = {"agent_code_executions": [], "internal_code_executions": []}

        old_count = len(turn.get("code_executions", []))
        stats["total_old"] += old_count
        stats["agent"] += len(classified["agent_code_executions"])
        stats["internal"] += len(classified["internal_code_executions"])

        # Replace fields
        turn["agent_code_executions"] = classified["agent_code_executions"]
        turn["internal_code_executions"] = classified["internal_code_executions"]
        turn.pop("code_executions", None)
        stats["modified"] = True

    if stats["modified"] and not dry_run:
        # Backup
        backup = trace_path.parent / "trace.json.bak"
        shutil.copy2(trace_path, backup)
        # Write enriched
        trace_path.write_text(json.dumps(trace, indent=2))

    return stats


def regenerate_conversation_md(trace_path: Path, trace: dict, dry_run: bool) -> bool:
    """Regenerate conversation.md from enriched trace data. Returns True if regenerated."""
    conv_path = trace_path.parent / "conversation.md"
    if not conv_path.exists():
        return False

    if not dry_run:
        shutil.copy2(conv_path, trace_path.parent / "conversation.md.bak")

    # Extract experiment metadata from trace
    experiment_info = trace.get("experiment", {})
    llm_info = trace.get("llm", {})

    logger = ConversationLogger(trace_path.parent)
    logger.start_experiment(
        experiment_name=experiment_info.get("name", ""),
        description=experiment_info.get("description", ""),
        llm_provider=llm_info.get("provider", ""),
        llm_model=llm_info.get("model", ""),
    )
    for turn in trace.get("turns", []):
        logger.log_turn(
            turn=turn["turn"],
            user_message=turn["user_message"],
            agent_response=turn["agent_response"],
            response_type=turn["response_type"],
            agent_code_executions=turn.get("agent_code_executions"),
        )

    # Add summary if status info available
    timing = trace.get("timing", {})
    status = trace.get("status", "completed")
    total_duration = timing.get("total_duration_seconds", 0)
    logger.log_summary(
        total_turns=len(trace.get("turns", [])),
        total_duration=total_duration,
        status=status,
    )

    if not dry_run:
        logger.save()

    return True


def main():
    parser = argparse.ArgumentParser(
        prog="enrich_traces",
        description="Enrich existing trace.json files with classified code executions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python enrich_traces.py --dry-run results/\n"
            "  python enrich_traces.py results/\n"
            "  python enrich_traces.py results/20260312_experiment/trace.json\n"
        ),
    )
    parser.add_argument(
        "path",
        type=Path,
        help="Path to results directory or specific trace.json file. "
             "Recursively finds all **/trace.json files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing files.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-process traces that already have new fields.",
    )
    args = parser.parse_args()

    # Find trace files
    target = args.path.resolve()
    if target.is_file() and target.name == "trace.json":
        trace_files = [target]
    elif target.is_dir():
        trace_files = sorted(target.rglob("trace.json"))
    else:
        print(f"Error: {target} is not a trace.json file or directory", file=sys.stderr)
        sys.exit(1)

    if not trace_files:
        print(f"No trace.json files found under {target}")
        sys.exit(0)

    print(f"Found {len(trace_files)} trace.json file(s)")
    if args.dry_run:
        print("[DRY RUN] No files will be modified.\n")
    print()

    total_stats = {"files": 0, "skipped": 0, "modified": 0, "agent": 0, "internal": 0, "conv_regenerated": 0}

    for trace_path in trace_files:
        stats = enrich_trace(trace_path, dry_run=args.dry_run, force=args.force)
        total_stats["files"] += 1

        if stats["skipped"] and not stats["modified"]:
            total_stats["skipped"] += 1
            print(f"  SKIP  {trace_path.parent.name}/trace.json (already migrated, use --force)")
            continue

        total_stats["modified"] += 1
        total_stats["agent"] += stats["agent"]
        total_stats["internal"] += stats["internal"]

        # Regenerate conversation.md
        trace_data = json.loads(trace_path.read_text()) if not args.dry_run else json.loads(trace_path.read_text())
        conv_ok = regenerate_conversation_md(trace_path, trace_data, dry_run=args.dry_run)
        if conv_ok:
            total_stats["conv_regenerated"] += 1

        action = "WOULD" if args.dry_run else "OK   "
        print(
            f"  {action} {trace_path.parent.name}/trace.json: "
            f"{stats['turns']} turns, {stats['total_old']} code_executions "
            f"-> {stats['agent']} agent + {stats['internal']} internal"
            f"{' (+ conversation.md)' if conv_ok else ''}"
        )

    print(f"\n{'=' * 60}")
    print(f"Summary: {total_stats['files']} files, {total_stats['modified']} modified, {total_stats['skipped']} skipped")
    print(f"  Agent executions:   {total_stats['agent']}")
    print(f"  Internal executions: {total_stats['internal']}")
    print(f"  Conversations regenerated: {total_stats['conv_regenerated']}")
    if args.dry_run:
        print("\n[DRY RUN] No files were modified. Run without --dry-run to apply changes.")


if __name__ == "__main__":
    main()
