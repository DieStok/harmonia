"""
Automation module for running reproducible Beaker experiments.

This module provides tools to:
- Connect to a running Beaker server via Jupyter protocol
- Send scripted conversations and capture responses
- Monitor manual/interactive sessions and log interactions
- Log full traces and simplified conversation outputs
- Run experiments on HPC with sbatch
"""

from .client import BeakerClient
from .config import ExperimentConfig, TracingConfig, load_config
from .logger import ConversationLogger, TraceLogger
from .manual_runner import ManualExperimentRunner, run_manual_experiment
from .runner import ExperimentRunner
from .tracing import (
    calculate_turn_cost,
    classify_code_execution,
    extract_code_executions,
    extract_usage_records,
    init_tracing,
)

__all__ = [
    "load_config",
    "ExperimentConfig",
    "TracingConfig",
    "BeakerClient",
    "ExperimentRunner",
    "ManualExperimentRunner",
    "run_manual_experiment",
    "TraceLogger",
    "ConversationLogger",
    "init_tracing",
    "extract_usage_records",
    "classify_code_execution",
    "extract_code_executions",
    "calculate_turn_cost",
]
