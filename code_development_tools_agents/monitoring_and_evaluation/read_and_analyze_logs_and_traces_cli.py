#!/usr/bin/env python3
"""
Harmonia Experiment Log & Trace Analyzer CLI

Analyzes experiment logs and traces from the Harmonia metadata harmonization
agent framework. Cross-references SLURM logs with trace.json files in results
folders to categorize failures using a YAML-based taxonomy.

Usage:
    python read_and_analyze_logs_and_traces_cli.py [OPTIONS]

Examples:
    # Analyze 10 most recent automated runs (default)
    python read_and_analyze_logs_and_traces_cli.py

    # Analyze 5 most recent runs, output JSON
    python read_and_analyze_logs_and_traces_cli.py -n 5 --json

    # Analyze a specific run by ID (new-style only)
    python read_and_analyze_logs_and_traces_cli.py --run-id a3f7b2c1

    # Analyze manual experiments only
    python read_and_analyze_logs_and_traces_cli.py --mode manual

    # Verbose output with per-turn trace analysis
    python read_and_analyze_logs_and_traces_cli.py --verbose

    # Filter by experiment name pattern
    python read_and_analyze_logs_and_traces_cli.py --experiment devstral
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel

# =============================================================================
# GLOBAL VARIABLES — edit these if naming conventions change
# =============================================================================

DEFAULT_LOG_DIR = "/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/logs"
DEFAULT_RESULTS_DIR = "/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/results"
DEFAULT_TAXONOMY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "types_of_log_and_trace_problems.yaml")

# Log filename patterns (regex)
# Automated: {DD-MM-YYYY_HHMM}_{experiment_name}_{SLURM_JOB_ID}[_{run_id}].out
AUTO_LOG_PATTERN = re.compile(
    r"^(\d{2}-\d{2}-\d{4}_\d{4})_(.+?)_(\d+?)(?:_([a-f0-9]{8}))?\.(out|err)$"
)

# Automated beaker/ollama logs: {experiment_name}_{SLURM_JOB_ID}[_{run_id}]_(beaker|ollama).log
AUTO_COMPONENT_LOG_PATTERN = re.compile(
    r"^(.+?)_(\d{5,})(?:_([a-f0-9]{8}))?_(beaker|ollama)\.log$"
)

# Manual beaker logs: beaker_{YYYYMMDD_HHMMSS}.log
MANUAL_BEAKER_LOG_PATTERN = re.compile(
    r"^(?:(.+?)_)?beaker_?(\d{8}_\d{6})(?:_([a-f0-9]{8}))?\.log$"
)

# Manual ollama logs: ollama_{YYYYMMDD_HHMMSS}.log
# Also: {experiment_name}_{YYYYMMDD_HHMMSS}_ollama.log
MANUAL_OLLAMA_LOG_PATTERN = re.compile(
    r"^(?:(.+?)_)?ollama_?(\d{8}_\d{6})(?:_([a-f0-9]{8}))?\.log$"
)

# Results folder pattern: {experiment_name}_{YYYYMMDD_HHMMSS}[_{run_id}]
RESULTS_FOLDER_PATTERN = re.compile(
    r"^(.+?)_(\d{8}_\d{6})(?:_([a-f0-9]{8}))?$"
)


# =============================================================================
# Pydantic Output Schema (version 1.0)
# =============================================================================

class SchemaVersion(str, Enum):
    V1 = "1.0"


class ExperimentMode(str, Enum):
    AUTOMATED = "automated"
    MANUAL = "manual"


class Severity(str, Enum):
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class DetectedProblem(BaseModel):
    problem_id: str
    category: str
    name: str
    severity: Severity
    evidence: str
    remediation: list[str]


class TurnAnalysis(BaseModel):
    turn: int
    response_type: str
    duration_seconds: float
    has_tool_calls: bool
    raw_message_count: int
    agent_response_empty: bool = False
    problems: list[DetectedProblem]


class RunAnalysis(BaseModel):
    run_id: Optional[str]
    experiment_name: str
    mode: ExperimentMode
    slurm_job_id: Optional[int]
    timestamp: str
    llm_provider: Optional[str]
    llm_model: Optional[str]
    log_file: Optional[str]
    results_folder: Optional[str]
    has_trace: bool
    has_metrics: bool
    total_turns: int
    successful_turns: int
    timed_out_turns: int
    total_duration_seconds: Optional[float]
    problems: list[DetectedProblem]
    turns: Optional[list[TurnAnalysis]] = None


class AnalysisReport(BaseModel):
    schema_version: SchemaVersion
    generated_at: str
    log_dir: str
    results_dir: str
    taxonomy_file: str
    num_runs_analyzed: int
    runs: list[RunAnalysis]
    summary: dict


# =============================================================================
# Taxonomy loader
# =============================================================================

class ProblemClass:
    """In-memory representation of a problem class from the YAML taxonomy."""

    def __init__(self, data: dict):
        self.id = data["id"]
        self.category = data["category"]
        self.name = data["name"]
        self.description = data.get("description", "")
        self.severity = data.get("severity", "error")
        self.log_keywords: list[str] = data.get("detection", {}).get("log_keywords", [])
        self.log_regex: list[re.Pattern] = [
            re.compile(p) for p in data.get("detection", {}).get("log_regex", [])
        ]
        self.trace_keywords: list[str] = data.get("detection", {}).get("trace_keywords", [])
        self.trace_regex: list[re.Pattern] = [
            re.compile(p) for p in data.get("detection", {}).get("trace_regex", [])
        ]
        self.remediation: list[str] = data.get("remediation", [])


def load_taxonomy(taxonomy_path: str) -> list[ProblemClass]:
    """Load problem classes from YAML taxonomy file."""
    with open(taxonomy_path, "r") as f:
        data = yaml.safe_load(f)
    return [ProblemClass(pc) for pc in data.get("problem_classes", [])]


# =============================================================================
# Log and results discovery
# =============================================================================

class DiscoveredLog:
    """A parsed log file with extracted metadata."""

    def __init__(
        self,
        path: Path,
        experiment_name: str,
        mode: ExperimentMode,
        slurm_job_id: Optional[int] = None,
        run_id: Optional[str] = None,
        timestamp_str: Optional[str] = None,
        log_type: str = "stdout",  # stdout, stderr, beaker, ollama
    ):
        self.path = path
        self.experiment_name = experiment_name
        self.mode = mode
        self.slurm_job_id = slurm_job_id
        self.run_id = run_id
        self.timestamp_str = timestamp_str
        self.log_type = log_type
        self.mtime = path.stat().st_mtime if path.exists() else 0.0


class DiscoveredResults:
    """A parsed results folder with extracted metadata."""

    def __init__(
        self,
        path: Path,
        experiment_name: str,
        timestamp_str: str,
        run_id: Optional[str] = None,
    ):
        self.path = path
        self.experiment_name = experiment_name
        self.timestamp_str = timestamp_str
        self.run_id = run_id
        self.has_trace = (path / "trace.json").exists()
        self.has_metrics = (path / "metrics.json").exists()
        self.has_experiment_id = (path / ".experiment_id").exists()


def discover_auto_logs(log_dir: Path) -> list[DiscoveredLog]:
    """Discover automated experiment .out logs."""
    logs = []
    for f in log_dir.iterdir():
        m = AUTO_LOG_PATTERN.match(f.name)
        if m and m.group(5) == "out":
            logs.append(DiscoveredLog(
                path=f,
                experiment_name=m.group(2),
                mode=ExperimentMode.AUTOMATED,
                slurm_job_id=int(m.group(3)),
                run_id=m.group(4),
                timestamp_str=m.group(1),
                log_type="stdout",
            ))
    return logs


def discover_manual_logs(log_dir: Path) -> list[DiscoveredLog]:
    """Discover manual experiment beaker/ollama logs."""
    logs = []
    for f in log_dir.iterdir():
        # beaker logs
        m = MANUAL_BEAKER_LOG_PATTERN.match(f.name)
        if m:
            logs.append(DiscoveredLog(
                path=f,
                experiment_name=m.group(1) or "manual",
                mode=ExperimentMode.MANUAL,
                run_id=m.group(3),
                timestamp_str=m.group(2),
                log_type="beaker",
            ))
            continue
        # ollama logs (standalone)
        m = MANUAL_OLLAMA_LOG_PATTERN.match(f.name)
        if m:
            logs.append(DiscoveredLog(
                path=f,
                experiment_name=m.group(1) or "manual",
                mode=ExperimentMode.MANUAL,
                run_id=m.group(3),
                timestamp_str=m.group(2),
                log_type="ollama",
            ))
    return logs


def discover_component_logs(log_dir: Path) -> list[DiscoveredLog]:
    """Discover automated experiment beaker/ollama component logs."""
    logs = []
    for f in log_dir.iterdir():
        m = AUTO_COMPONENT_LOG_PATTERN.match(f.name)
        if m:
            logs.append(DiscoveredLog(
                path=f,
                experiment_name=m.group(1),
                mode=ExperimentMode.AUTOMATED,
                slurm_job_id=int(m.group(2)),
                run_id=m.group(3),
                log_type=m.group(4),
            ))
    return logs


def discover_results(results_dir: Path) -> list[DiscoveredResults]:
    """Discover results folders."""
    results = []
    for d in results_dir.iterdir():
        if not d.is_dir():
            continue
        m = RESULTS_FOLDER_PATTERN.match(d.name)
        if m:
            results.append(DiscoveredResults(
                path=d,
                experiment_name=m.group(1),
                timestamp_str=m.group(2),
                run_id=m.group(3),
            ))
    return results


# =============================================================================
# Linkage: match logs to results folders
# =============================================================================

def link_log_to_results(
    log: DiscoveredLog,
    all_results: list[DiscoveredResults],
) -> Optional[DiscoveredResults]:
    """
    Link a log to its results folder.

    New-style (with run_id): match by run_id.
    Legacy (without run_id): match by experiment_name, pick most recent
    results folder with a matching name.
    """
    # New-style: match by run_id
    if log.run_id:
        for r in all_results:
            if r.run_id == log.run_id:
                return r

    # Legacy: match by experiment_name
    candidates = [
        r for r in all_results
        if r.experiment_name == log.experiment_name
    ]

    if not candidates:
        return None

    if len(candidates) == 1:
        return candidates[0]

    # Multiple matches: pick the one closest in time to the log.
    # For automated logs, we can parse the log timestamp and find the closest
    # results folder timestamp.
    if log.timestamp_str:
        try:
            log_dt = _parse_log_timestamp(log.timestamp_str)
        except ValueError:
            # Can't parse, just pick the latest
            candidates.sort(key=lambda r: r.timestamp_str, reverse=True)
            return candidates[0]

        def results_time_distance(r: DiscoveredResults) -> float:
            try:
                r_dt = _parse_results_timestamp(r.timestamp_str)
                return abs((r_dt - log_dt).total_seconds())
            except ValueError:
                return float("inf")

        candidates.sort(key=results_time_distance)
        return candidates[0]

    # Fallback: pick the latest
    candidates.sort(key=lambda r: r.timestamp_str, reverse=True)
    return candidates[0]


def _parse_log_timestamp(ts: str) -> datetime:
    """Parse DD-MM-YYYY_HHMM log timestamp."""
    return datetime.strptime(ts, "%d-%m-%Y_%H%M")


def _parse_results_timestamp(ts: str) -> datetime:
    """Parse YYYYMMDD_HHMMSS results folder timestamp."""
    return datetime.strptime(ts, "%Y%m%d_%H%M%S")


# =============================================================================
# Log and trace reading
# =============================================================================

def read_log_content(log: DiscoveredLog, max_bytes: int = 5_000_000) -> str:
    """Read log file content, capped at max_bytes."""
    try:
        with open(log.path, "r", errors="replace") as f:
            return f.read(max_bytes)
    except OSError:
        return ""


def read_trace(results: DiscoveredResults) -> Optional[dict]:
    """Read and parse trace.json from a results folder."""
    trace_path = results.path / "trace.json"
    if not trace_path.exists():
        return None
    try:
        with open(trace_path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def read_metrics(results: DiscoveredResults) -> Optional[dict]:
    """Read and parse metrics.json from a results folder."""
    metrics_path = results.path / "metrics.json"
    if not metrics_path.exists():
        return None
    try:
        with open(metrics_path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def read_experiment_id(results: DiscoveredResults) -> Optional[dict]:
    """Read .experiment_id metadata file if present."""
    eid_path = results.path / ".experiment_id"
    if not eid_path.exists():
        return None
    try:
        with open(eid_path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


# =============================================================================
# Problem detection
# =============================================================================

def detect_problems(
    log_content: str,
    trace: Optional[dict],
    metrics: Optional[dict],
    results: Optional[DiscoveredResults],
    taxonomy: list[ProblemClass],
    verbose: bool = False,
) -> tuple[list[DetectedProblem], Optional[list[TurnAnalysis]]]:
    """
    Detect problems using both YAML taxonomy patterns and compound Python logic.

    Returns (run-level problems, optional per-turn analysis).
    """
    problems: list[DetectedProblem] = []
    turn_analyses: Optional[list[TurnAnalysis]] = [] if verbose else None

    # Serialize trace for keyword/regex searching
    trace_text = json.dumps(trace, indent=2) if trace else ""

    # --- YAML-based keyword/regex detection ---
    for pc in taxonomy:
        evidence = _check_patterns(pc, log_content, trace_text)
        if evidence:
            problems.append(DetectedProblem(
                problem_id=pc.id,
                category=pc.category,
                name=pc.name,
                severity=Severity(pc.severity),
                evidence=evidence[:500],  # cap evidence length
                remediation=pc.remediation,
            ))

    # --- Compound detection logic (Python-only) ---

    if trace and "turns" in trace:
        turns = trace["turns"]

        # 1A: Beaker Server Hung
        # All turns timeout + each has <= 1 raw_message + total ~2220s
        hung_problem = _detect_beaker_server_hung(turns, taxonomy)
        if hung_problem:
            # Replace any duplicate 1A from simple keyword match
            problems = [p for p in problems if p.problem_id != "1A"]
            problems.append(hung_problem)

        # 3A: LLM-Side Timeout (differs from 1A by raw_message count > 1)
        llm_timeout_problems = _detect_llm_side_timeout(turns, taxonomy)
        # Only add if 1A is not already detected (they share "timed out" keyword)
        if not any(p.problem_id == "1A" for p in problems):
            problems.extend(llm_timeout_problems)
        elif llm_timeout_problems:
            # If 1A detected, these timeouts are infra, not LLM. Skip 3A.
            pass

        # 3B: Not Using Tools
        tool_problem = _detect_not_using_tools(turns, taxonomy)
        if tool_problem:
            problems.append(tool_problem)

        # Per-turn analysis
        if verbose:
            for t in turns:
                turn_problems = _detect_turn_problems(t, log_content, trace_text, taxonomy)
                response_empty = (
                    t.get("response_type") == "llm_response"
                    and not t.get("agent_response", "").strip()
                )
                ta = TurnAnalysis(
                    turn=t.get("turn", 0),
                    response_type=t.get("response_type", "unknown"),
                    duration_seconds=t.get("duration_seconds", 0.0),
                    has_tool_calls=bool(t.get("tool_calls")),
                    raw_message_count=len(t.get("raw_messages", [])),
                    agent_response_empty=response_empty,
                    problems=turn_problems,
                )
                turn_analyses.append(ta)

    # 3E: Context Window Exhaustion
    if trace and "turns" in trace:
        context_problem = _detect_context_window_exhaustion(trace["turns"], trace_text, taxonomy)
        if context_problem:
            problems.append(context_problem)

    # 3F: Response Stream Truncated
    if trace and "turns" in trace:
        stream_problem = _detect_response_stream_truncated(trace["turns"], trace_text, taxonomy)
        if stream_problem:
            problems.append(stream_problem)

    # 3G: Silent Empty Response (cross-cutting)
    if trace and "turns" in trace:
        silent_problem = _detect_silent_empty_response(trace["turns"], taxonomy)
        if silent_problem:
            problems.append(silent_problem)

    # 3C: Hallucinated Output (check metrics.json)
    hallucination_problem = _detect_hallucinated_output(metrics, taxonomy)
    if hallucination_problem:
        problems.append(hallucination_problem)

    # 5A: No Output Produced (check results folder contents)
    no_output_problem = _detect_no_output(results, taxonomy)
    if no_output_problem:
        problems.append(no_output_problem)

    # Deduplicate by problem_id
    seen_ids = set()
    unique_problems = []
    for p in problems:
        if p.problem_id not in seen_ids:
            seen_ids.add(p.problem_id)
            unique_problems.append(p)

    return unique_problems, turn_analyses


def _check_patterns(pc: ProblemClass, log_content: str, trace_text: str) -> Optional[str]:
    """Check keyword/regex patterns against log and trace text. Returns first match."""
    for kw in pc.log_keywords:
        if kw in log_content:
            # Extract line containing keyword
            for line in log_content.splitlines():
                if kw in line:
                    return f"Log: {line.strip()}"
            return f"Log keyword match: {kw}"

    for rx in pc.log_regex:
        m = rx.search(log_content)
        if m:
            return f"Log regex match: {m.group(0)}"

    for kw in pc.trace_keywords:
        if kw in trace_text:
            # Find first occurrence in trace
            for line in trace_text.splitlines():
                if kw in line:
                    return f"Trace: {line.strip()}"
            return f"Trace keyword match: {kw}"

    for rx in pc.trace_regex:
        m = rx.search(trace_text)
        if m:
            return f"Trace regex match: {m.group(0)}"

    return None


def _detect_beaker_server_hung(
    turns: list[dict], taxonomy: list[ProblemClass]
) -> Optional[DetectedProblem]:
    """
    1A: Beaker Server Hung
    Compound logic: ALL turns timeout AND each has <= 1 raw_message
    AND total duration ~2220s (± 200s).
    """
    if not turns:
        return None

    all_timeout = all(t.get("response_type") == "timeout" for t in turns)
    if not all_timeout:
        return None

    max_raw_msgs = max(len(t.get("raw_messages", [])) for t in turns)
    if max_raw_msgs > 1:
        return None

    total_duration = sum(t.get("duration_seconds", 0) for t in turns)
    # The signature pattern totals ~2220s, but we use a wider range to catch variants
    if total_duration < 500:
        return None

    pc = _find_pc(taxonomy, "1A")
    durations = [t.get("duration_seconds", 0) for t in turns]
    return DetectedProblem(
        problem_id="1A",
        category=pc.category if pc else "infrastructure",
        name=pc.name if pc else "Beaker Server Hung",
        severity=Severity.CRITICAL,
        evidence=(
            f"All {len(turns)} turns timed out with <=1 raw_message each. "
            f"Duration pattern: {[round(d, 1) for d in durations]}. "
            f"Total: {total_duration:.0f}s"
        ),
        remediation=pc.remediation if pc else [],
    )


def _detect_llm_side_timeout(
    turns: list[dict], taxonomy: list[ProblemClass]
) -> list[DetectedProblem]:
    """
    3A: LLM-Side Timeout
    Compound logic: some turns timeout with > 1 raw_message
    (kernel is processing, but LLM is slow).
    """
    problems = []
    timed_out_turns = [
        t for t in turns
        if t.get("response_type") == "timeout"
        and len(t.get("raw_messages", [])) > 1
    ]
    if not timed_out_turns:
        return problems

    pc = _find_pc(taxonomy, "3A")
    turn_nums = [t.get("turn", "?") for t in timed_out_turns]
    problems.append(DetectedProblem(
        problem_id="3A",
        category=pc.category if pc else "llm_behavioral",
        name=pc.name if pc else "LLM-Side Timeout on Complex Tasks",
        severity=Severity.ERROR,
        evidence=(
            f"Turns {turn_nums} timed out with >1 raw_message each "
            f"(kernel was processing, LLM was slow)."
        ),
        remediation=pc.remediation if pc else [],
    ))
    return problems


def _detect_not_using_tools(
    turns: list[dict], taxonomy: list[ProblemClass]
) -> Optional[DetectedProblem]:
    """
    3B: LLM Not Using Tools
    Compound logic: turns with llm_response but empty tool_calls,
    and response contains refusal phrases.
    """
    refusal_phrases = [
        "I don't have the capability",
        "I can't directly",
        "I cannot directly",
        "here's how you could",
        "you could run",
        "I'm unable to",
        "I can guide you",
    ]

    no_tool_turns = []
    for t in turns:
        if t.get("response_type") != "llm_response":
            continue
        if t.get("tool_calls"):
            continue
        response = t.get("agent_response", "")
        if any(phrase.lower() in response.lower() for phrase in refusal_phrases):
            no_tool_turns.append(t.get("turn", "?"))

    if not no_tool_turns:
        return None

    pc = _find_pc(taxonomy, "3B")
    return DetectedProblem(
        problem_id="3B",
        category=pc.category if pc else "llm_behavioral",
        name=pc.name if pc else "LLM Not Using Tools",
        severity=Severity.ERROR,
        evidence=(
            f"Turns {no_tool_turns} returned text guidance instead of using tools. "
            f"Agent refused to execute code directly."
        ),
        remediation=pc.remediation if pc else [],
    )


def _detect_context_window_exhaustion(
    turns: list[dict], trace_text: str, taxonomy: list[ProblemClass]
) -> Optional[DetectedProblem]:
    """
    3E: Context Window Exhaustion (API Token Limit Exceeded)
    Compound logic: turns with response_type == "llm_response",
    empty agent_response, fast duration (<2s), and raw_messages
    containing "maximum context length".
    """
    affected_turns = []
    token_info = ""
    for t in turns:
        if t.get("response_type") != "llm_response":
            continue
        response = t.get("agent_response", "")
        if response.strip():
            continue
        duration = t.get("duration_seconds", 999)
        if duration > 5.0:
            continue
        # Check raw_messages for context length error
        raw_text = json.dumps(t.get("raw_messages", []))
        if "maximum context length" in raw_text:
            affected_turns.append(t.get("turn", "?"))
            # Extract token count from first match
            if not token_info:
                m = re.search(r"you requested about (\d+) tokens", raw_text)
                limit_m = re.search(r"maximum context length is (\d+) tokens", raw_text)
                if m and limit_m:
                    token_info = f" (requested ~{m.group(1)} tokens, limit {limit_m.group(1)})"

    if not affected_turns:
        return None

    pc = _find_pc(taxonomy, "3E")
    return DetectedProblem(
        problem_id="3E",
        category=pc.category if pc else "llm_behavioral",
        name=pc.name if pc else "Context Window Exhaustion",
        severity=Severity.ERROR,
        evidence=(
            f"Turns {affected_turns} returned empty responses in <2s due to "
            f"context window overflow{token_info}. "
            f"Errors silently swallowed in raw_messages."
        ),
        remediation=pc.remediation if pc else [],
    )


def _detect_response_stream_truncated(
    turns: list[dict], trace_text: str, taxonomy: list[ProblemClass]
) -> Optional[DetectedProblem]:
    """
    3F: Response Stream Truncated (Premature Connection Close)
    Compound logic: turns with response_type == "llm_response",
    empty agent_response, significant duration (>5s), and raw_messages
    containing "Response ended prematurely" or "ChunkedEncodingError".
    """
    affected_turns = []
    for t in turns:
        if t.get("response_type") != "llm_response":
            continue
        response = t.get("agent_response", "")
        if response.strip():
            continue
        duration = t.get("duration_seconds", 0)
        if duration < 5.0:
            continue
        raw_text = json.dumps(t.get("raw_messages", []))
        if "Response ended prematurely" in raw_text or "ChunkedEncodingError" in raw_text:
            affected_turns.append(t.get("turn", "?"))

    if not affected_turns:
        return None

    pc = _find_pc(taxonomy, "3F")
    return DetectedProblem(
        problem_id="3F",
        category=pc.category if pc else "llm_behavioral",
        name=pc.name if pc else "Response Stream Truncated",
        severity=Severity.ERROR,
        evidence=(
            f"Turns {affected_turns} completed with empty agent_response after "
            f"significant processing time. HTTP response stream was severed "
            f"mid-transfer (ChunkedEncodingError / Response ended prematurely)."
        ),
        remediation=pc.remediation if pc else [],
    )


def _detect_silent_empty_response(
    turns: list[dict], taxonomy: list[ProblemClass]
) -> Optional[DetectedProblem]:
    """
    3G: Silent Empty Response (No Agent Output)
    Cross-cutting detection: any turn where response_type is "llm_response"
    but agent_response is empty or whitespace-only. This catches all cases
    of silently swallowed errors, including those already covered by 3E/3F
    and unknown error types.
    """
    affected_turns = []
    for t in turns:
        if t.get("response_type") != "llm_response":
            continue
        response = t.get("agent_response", "")
        if not response.strip():
            affected_turns.append(t.get("turn", "?"))

    if not affected_turns:
        return None

    pc = _find_pc(taxonomy, "3G")
    return DetectedProblem(
        problem_id="3G",
        category=pc.category if pc else "llm_behavioral",
        name=pc.name if pc else "Silent Empty Response",
        severity=Severity.WARNING,
        evidence=(
            f"Turns {affected_turns} completed with response_type 'llm_response' "
            f"but agent_response is empty. Errors may have been silently swallowed. "
            f"Check raw_messages for these turns to diagnose root cause."
        ),
        remediation=pc.remediation if pc else [],
    )


def _detect_hallucinated_output(
    metrics: Optional[dict], taxonomy: list[ProblemClass]
) -> Optional[DetectedProblem]:
    """
    3C: Hallucinated / Fabricated Output
    Compound logic: metrics.json exists AND column_mapping_accuracy == 0.0
    AND extra_columns present.
    """
    if not metrics:
        return None

    accuracy = metrics.get("column_mapping_accuracy", -1)
    extra_cols = metrics.get("extra_columns", [])

    if accuracy == 0.0 and extra_cols:
        pc = _find_pc(taxonomy, "3C")
        return DetectedProblem(
            problem_id="3C",
            category=pc.category if pc else "llm_behavioral",
            name=pc.name if pc else "Hallucinated Output",
            severity=Severity.ERROR,
            evidence=(
                f"metrics.json shows 0% accuracy with {len(extra_cols)} extra columns: "
                f"{extra_cols[:5]}{'...' if len(extra_cols) > 5 else ''}"
            ),
            remediation=pc.remediation if pc else [],
        )
    return None


def _detect_no_output(
    results: Optional[DiscoveredResults], taxonomy: list[ProblemClass]
) -> Optional[DetectedProblem]:
    """
    5A: No Output Produced
    Compound logic: results dir exists, trace.json exists,
    but no dou_harmonized.csv.
    """
    if not results:
        return None

    if not results.has_trace:
        return None

    harmonized_csv = results.path / "dou_harmonized.csv"
    if harmonized_csv.exists():
        return None

    pc = _find_pc(taxonomy, "5A")
    contents = [f.name for f in results.path.iterdir()]
    return DetectedProblem(
        problem_id="5A",
        category=pc.category if pc else "output",
        name=pc.name if pc else "No Output Produced",
        severity=Severity.WARNING,
        evidence=(
            f"Results folder contains {contents} but no dou_harmonized.csv"
        ),
        remediation=pc.remediation if pc else [],
    )


def _detect_turn_problems(
    turn: dict, log_content: str, trace_text: str, taxonomy: list[ProblemClass]
) -> list[DetectedProblem]:
    """Detect problems for a single turn (used in verbose mode)."""
    problems = []
    turn_text = json.dumps(turn, indent=2)

    for pc in taxonomy:
        # Check trace patterns against this turn's serialized text
        for kw in pc.trace_keywords:
            if kw in turn_text:
                for line in turn_text.splitlines():
                    if kw in line:
                        evidence = f"Turn {turn.get('turn', '?')}: {line.strip()}"
                        break
                else:
                    evidence = f"Turn {turn.get('turn', '?')}: keyword '{kw}'"
                problems.append(DetectedProblem(
                    problem_id=pc.id,
                    category=pc.category,
                    name=pc.name,
                    severity=Severity(pc.severity),
                    evidence=evidence[:500],
                    remediation=pc.remediation,
                ))
                break

        for rx in pc.trace_regex:
            m = rx.search(turn_text)
            if m:
                problems.append(DetectedProblem(
                    problem_id=pc.id,
                    category=pc.category,
                    name=pc.name,
                    severity=Severity(pc.severity),
                    evidence=f"Turn {turn.get('turn', '?')}: regex match '{m.group(0)}'",
                    remediation=pc.remediation,
                ))
                break

    return problems


def _find_pc(taxonomy: list[ProblemClass], problem_id: str) -> Optional[ProblemClass]:
    """Find a ProblemClass by ID in the taxonomy."""
    for pc in taxonomy:
        if pc.id == problem_id:
            return pc
    return None


# =============================================================================
# Run assembly: combine logs + results into analyzable runs
# =============================================================================

def assemble_runs(
    log_dir: Path,
    results_dir: Path,
    mode_filter: Optional[str],
    experiment_filter: Optional[str],
    run_id_filter: Optional[str],
    num_runs: int,
) -> list[dict]:
    """
    Discover logs and results, link them, and return the N most recent runs.

    A "run" is anchored by either:
    - An automated .out log file (for automated mode)
    - A results folder with trace.json (for manual mode, or as fallback)
    """
    all_results = discover_results(results_dir)

    runs = []

    # Automated runs: anchored by .out log files
    if mode_filter in (None, "all", "auto", "automated"):
        auto_logs = discover_auto_logs(log_dir)
        component_logs = discover_component_logs(log_dir)

        for log in auto_logs:
            if experiment_filter and experiment_filter.lower() not in log.experiment_name.lower():
                continue
            if run_id_filter and log.run_id != run_id_filter:
                continue

            linked_results = link_log_to_results(log, all_results)

            # Find associated component logs (beaker, ollama)
            assoc_beaker = None
            assoc_ollama = None
            for cl in component_logs:
                if cl.slurm_job_id == log.slurm_job_id and cl.experiment_name == log.experiment_name:
                    if cl.log_type == "beaker":
                        assoc_beaker = cl
                    elif cl.log_type == "ollama":
                        assoc_ollama = cl

            runs.append({
                "log": log,
                "results": linked_results,
                "beaker_log": assoc_beaker,
                "ollama_log": assoc_ollama,
                "sort_key": log.mtime,
            })

    # Manual runs: anchored by results folders that have trace.json
    # but no matching automated log
    if mode_filter in (None, "all", "manual"):
        auto_experiment_names = set()
        if mode_filter not in ("manual",):
            auto_logs = discover_auto_logs(log_dir)
            for log in auto_logs:
                auto_experiment_names.add(log.experiment_name)

        manual_beaker_logs = discover_manual_logs(log_dir)

        for r in all_results:
            if r.experiment_name in auto_experiment_names and mode_filter != "manual":
                continue
            if not r.has_trace:
                continue
            if experiment_filter and experiment_filter.lower() not in r.experiment_name.lower():
                continue
            if run_id_filter and r.run_id != run_id_filter:
                continue

            # Try to find associated manual logs
            assoc_beaker = None
            for bl in manual_beaker_logs:
                if bl.log_type == "beaker":
                    if r.run_id and bl.run_id == r.run_id:
                        assoc_beaker = bl
                        break
                    if r.timestamp_str and bl.timestamp_str and bl.timestamp_str in r.timestamp_str:
                        assoc_beaker = bl
                        break

            runs.append({
                "log": None,
                "results": r,
                "beaker_log": assoc_beaker,
                "ollama_log": None,
                "sort_key": r.path.stat().st_mtime if r.path.exists() else 0.0,
            })

    # Sort by most recent first, take top N
    runs.sort(key=lambda r: r["sort_key"], reverse=True)
    return runs[:num_runs]


# =============================================================================
# Analysis pipeline
# =============================================================================

def analyze_run(
    run: dict,
    taxonomy: list[ProblemClass],
    verbose: bool = False,
) -> RunAnalysis:
    """Analyze a single run: read log+trace, detect problems."""
    log: Optional[DiscoveredLog] = run.get("log")
    results: Optional[DiscoveredResults] = run.get("results")

    # Read log content
    log_content = ""
    if log:
        log_content = read_log_content(log)

    # Read trace
    trace = None
    if results and results.has_trace:
        trace = read_trace(results)

    # Read metrics
    metrics = None
    if results and results.has_metrics:
        metrics = read_metrics(results)

    # Read .experiment_id if available
    experiment_id = None
    if results and results.has_experiment_id:
        experiment_id = read_experiment_id(results)

    # Determine metadata
    experiment_name = ""
    if log:
        experiment_name = log.experiment_name
    elif results:
        experiment_name = results.experiment_name

    run_id = None
    if log and log.run_id:
        run_id = log.run_id
    elif results and results.run_id:
        run_id = results.run_id
    elif experiment_id:
        run_id = experiment_id.get("run_id")

    slurm_job_id = None
    if log and log.slurm_job_id:
        slurm_job_id = log.slurm_job_id

    mode = ExperimentMode.AUTOMATED
    if log:
        mode = log.mode
    elif results:
        # If no .out log is associated, it's likely manual
        mode = ExperimentMode.MANUAL

    timestamp = ""
    if log and log.timestamp_str:
        timestamp = log.timestamp_str
    elif results:
        timestamp = results.timestamp_str

    # Extract LLM info from trace
    llm_provider = None
    llm_model = None
    if trace:
        llm_info = trace.get("llm", {})
        llm_provider = llm_info.get("provider")
        llm_model = llm_info.get("model")

    # Count turns
    total_turns = 0
    successful_turns = 0
    timed_out_turns = 0
    total_duration = None
    if trace and "turns" in trace:
        turns = trace["turns"]
        total_turns = len(turns)
        successful_turns = sum(
            1 for t in turns
            if t.get("response_type") == "llm_response"
            and t.get("agent_response", "").strip()
        )
        timed_out_turns = sum(1 for t in turns if t.get("response_type") == "timeout")
        timing = trace.get("timing", {})
        total_duration = timing.get("total_duration_seconds")

    # Detect problems
    problems, turn_analyses = detect_problems(
        log_content, trace, metrics, results, taxonomy, verbose
    )

    return RunAnalysis(
        run_id=run_id,
        experiment_name=experiment_name,
        mode=mode,
        slurm_job_id=slurm_job_id,
        timestamp=timestamp,
        llm_provider=llm_provider,
        llm_model=llm_model,
        log_file=str(log.path) if log else None,
        results_folder=str(results.path) if results else None,
        has_trace=results.has_trace if results else False,
        has_metrics=results.has_metrics if results else False,
        total_turns=total_turns,
        successful_turns=successful_turns,
        timed_out_turns=timed_out_turns,
        total_duration_seconds=total_duration,
        problems=problems,
        turns=turn_analyses,
    )


def generate_report(
    runs: list[RunAnalysis],
    log_dir: str,
    results_dir: str,
    taxonomy_file: str,
) -> AnalysisReport:
    """Generate the final analysis report."""
    # Aggregate problem counts by category
    summary: dict = {}
    for run in runs:
        for p in run.problems:
            cat = p.category
            if cat not in summary:
                summary[cat] = {"count": 0, "problems": {}}
            summary[cat]["count"] += 1
            pid = p.problem_id
            if pid not in summary[cat]["problems"]:
                summary[cat]["problems"][pid] = {"name": p.name, "count": 0, "severity": p.severity.value}
            summary[cat]["problems"][pid]["count"] += 1

    return AnalysisReport(
        schema_version=SchemaVersion.V1,
        generated_at=datetime.now(timezone.utc).isoformat(),
        log_dir=log_dir,
        results_dir=results_dir,
        taxonomy_file=taxonomy_file,
        num_runs_analyzed=len(runs),
        runs=runs,
        summary=summary,
    )


# =============================================================================
# Output formatting
# =============================================================================

SEVERITY_SYMBOLS = {
    "critical": "[CRIT]",
    "error": "[ERR] ",
    "warning": "[WARN]",
    "info": "[INFO]",
}


def format_human_readable(report: AnalysisReport) -> str:
    """Format the report as human-readable text."""
    lines = []
    lines.append("=" * 78)
    lines.append("HARMONIA EXPERIMENT ANALYSIS REPORT")
    lines.append("=" * 78)
    lines.append(f"Generated: {report.generated_at}")
    lines.append(f"Log dir:   {report.log_dir}")
    lines.append(f"Results:   {report.results_dir}")
    lines.append(f"Taxonomy:  {report.taxonomy_file}")
    lines.append(f"Runs:      {report.num_runs_analyzed}")
    lines.append("")

    # Summary
    if report.summary:
        lines.append("-" * 78)
        lines.append("SUMMARY BY CATEGORY")
        lines.append("-" * 78)
        for cat, data in sorted(report.summary.items()):
            lines.append(f"\n  {cat.upper()} ({data['count']} occurrences)")
            for pid, pdata in sorted(data["problems"].items()):
                sym = SEVERITY_SYMBOLS.get(pdata["severity"], "[???]")
                lines.append(f"    {sym} {pid}: {pdata['name']} (x{pdata['count']})")
        lines.append("")

    # Per-run details
    lines.append("-" * 78)
    lines.append("PER-RUN DETAILS")
    lines.append("-" * 78)

    for run in report.runs:
        lines.append("")
        header = f"  {run.experiment_name}"
        if run.slurm_job_id:
            header += f" (job {run.slurm_job_id})"
        if run.run_id:
            header += f" [run_id: {run.run_id}]"
        lines.append(header)
        lines.append(f"  Mode: {run.mode.value} | Timestamp: {run.timestamp}")
        if run.llm_provider or run.llm_model:
            lines.append(f"  LLM: {run.llm_provider or '?'} / {run.llm_model or '?'}")
        lines.append(
            f"  Turns: {run.total_turns} total, "
            f"{run.successful_turns} ok, "
            f"{run.timed_out_turns} timeout"
        )
        if run.total_duration_seconds is not None:
            mins = run.total_duration_seconds / 60
            lines.append(f"  Duration: {run.total_duration_seconds:.0f}s ({mins:.1f} min)")
        lines.append(f"  Log: {run.log_file or 'N/A'}")
        lines.append(f"  Results: {run.results_folder or 'N/A'}")
        lines.append(f"  Trace: {'yes' if run.has_trace else 'no'} | Metrics: {'yes' if run.has_metrics else 'no'}")

        if run.problems:
            lines.append(f"  Problems ({len(run.problems)}):")
            for p in run.problems:
                sym = SEVERITY_SYMBOLS.get(p.severity.value, "[???]")
                lines.append(f"    {sym} {p.problem_id}: {p.name}")
                lines.append(f"           Evidence: {p.evidence[:120]}")
        else:
            lines.append("  Problems: none detected")

        # Verbose per-turn output
        if run.turns:
            lines.append(f"  Per-turn analysis:")
            for ta in run.turns:
                if ta.response_type == "llm_response":
                    status = "EMPTY" if ta.agent_response_empty else "OK"
                else:
                    status = ta.response_type.upper()
                tools = "tools" if ta.has_tool_calls else "no-tools"
                lines.append(
                    f"    Turn {ta.turn}: {status} | "
                    f"{ta.duration_seconds:.1f}s | "
                    f"{tools} | "
                    f"{ta.raw_message_count} raw_msgs"
                )
                for tp in ta.problems:
                    sym = SEVERITY_SYMBOLS.get(tp.severity.value, "[???]")
                    lines.append(f"      {sym} {tp.problem_id}: {tp.name}")

    lines.append("")
    lines.append("=" * 78)
    lines.append("END OF REPORT")
    lines.append("=" * 78)
    return "\n".join(lines)


# =============================================================================
# Main
# =============================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="read_and_analyze_logs_and_traces_cli",
        description=(
            "Analyze Harmonia experiment logs and traces. "
            "Cross-references SLURM logs with trace.json files to "
            "categorize failures using a YAML-based taxonomy."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s                          # Analyze 10 most recent runs\n"
            "  %(prog)s -n 5 --json              # 5 runs, JSON output\n"
            "  %(prog)s --mode manual --verbose   # Manual runs with per-turn detail\n"
            "  %(prog)s --run-id a3f7b2c1         # Specific run by ID\n"
            "  %(prog)s --experiment devstral     # Filter by experiment name\n"
        ),
    )
    parser.add_argument(
        "-n", "--num-runs",
        type=int, default=10,
        help="Number of most recent runs to analyze (default: 10)",
    )
    parser.add_argument(
        "-l", "--log-dir",
        type=str, default=DEFAULT_LOG_DIR,
        help=f"Log directory (default: {DEFAULT_LOG_DIR})",
    )
    parser.add_argument(
        "-r", "--results-dir",
        type=str, default=DEFAULT_RESULTS_DIR,
        help=f"Results directory (default: {DEFAULT_RESULTS_DIR})",
    )
    parser.add_argument(
        "-t", "--taxonomy",
        type=str, default=DEFAULT_TAXONOMY_FILE,
        help=f"Error taxonomy YAML file (default: {DEFAULT_TAXONOMY_FILE})",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "manual", "all"],
        default="all",
        help="Filter by experiment mode (default: all)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of human-readable text",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed per-turn trace analysis",
    )
    parser.add_argument(
        "--run-id",
        type=str, default=None,
        help="Analyze a specific run by its 8-char hex ID",
    )
    parser.add_argument(
        "--experiment",
        type=str, default=None,
        help="Filter by experiment name pattern (case-insensitive substring match)",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    log_dir = Path(args.log_dir)
    results_dir = Path(args.results_dir)
    taxonomy_file = args.taxonomy

    if not log_dir.exists():
        print(f"Error: log directory not found: {log_dir}", file=sys.stderr)
        sys.exit(1)
    if not results_dir.exists():
        print(f"Error: results directory not found: {results_dir}", file=sys.stderr)
        sys.exit(1)
    if not Path(taxonomy_file).exists():
        print(f"Error: taxonomy file not found: {taxonomy_file}", file=sys.stderr)
        sys.exit(1)

    # Load taxonomy
    taxonomy = load_taxonomy(taxonomy_file)

    # Discover and assemble runs
    runs = assemble_runs(
        log_dir=log_dir,
        results_dir=results_dir,
        mode_filter=args.mode,
        experiment_filter=args.experiment,
        run_id_filter=args.run_id,
        num_runs=args.num_runs,
    )

    if not runs:
        print("No runs found matching the given criteria.", file=sys.stderr)
        sys.exit(0)

    # Analyze each run
    analyzed_runs = []
    for run in runs:
        analyzed = analyze_run(run, taxonomy, verbose=args.verbose)
        analyzed_runs.append(analyzed)

    # Generate report
    report = generate_report(
        runs=analyzed_runs,
        log_dir=str(log_dir),
        results_dir=str(results_dir),
        taxonomy_file=taxonomy_file,
    )

    # Output
    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        print(format_human_readable(report))


if __name__ == "__main__":
    main()
