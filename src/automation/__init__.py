"""
Automation module for running reproducible Beaker experiments.

This module provides tools to:
- Connect to a running Beaker server via Jupyter protocol
- Send scripted conversations and capture responses
- Monitor manual/interactive sessions and log interactions
- Log full traces and simplified conversation outputs
- Run experiments on HPC with sbatch
"""

from .config import load_config, ExperimentConfig
from .client import BeakerClient
from .runner import ExperimentRunner
from .manual_runner import ManualExperimentRunner, run_manual_experiment
from .logger import TraceLogger, ConversationLogger

__all__ = [
    "load_config",
    "ExperimentConfig",
    "BeakerClient",
    "ExperimentRunner",
    "ManualExperimentRunner",
    "run_manual_experiment",
    "TraceLogger",
    "ConversationLogger",
]
