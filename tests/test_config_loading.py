"""
Smoke test: verify all automated experiment configs parse without errors.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from automation.config import load_config

CONFIG_DIR = (
    Path(__file__).parent.parent
    / "experiments/experiment_1_harmonia_dou2020_gdc/configs/automated"
)

config_files = sorted(CONFIG_DIR.glob("*.yaml"))


@pytest.mark.parametrize("config_path", config_files, ids=[p.stem for p in config_files])
def test_config_loads_without_error(config_path):
    """Each config YAML must parse into a valid ExperimentConfig."""
    config = load_config(config_path)
    assert config.name, f"Config has no name: {config_path}"
    assert config.llm.provider, f"Config has no LLM provider: {config_path}"
    assert config.llm.model, f"Config has no LLM model: {config_path}"


def test_all_configs_found():
    """Sanity check: at least 25 automated configs expected."""
    assert len(config_files) >= 25, f"Expected >=25 configs, found {len(config_files)}"
