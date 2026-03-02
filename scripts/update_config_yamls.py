#!/usr/bin/env python3
"""
Script to update all 10 automated config YAMLs with evaluation block and mapping message.
"""

import yaml
from pathlib import Path

# Base directory
CONFIG_DIR = Path("/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/experiments/experiment_1_harmonia_dou2020_gdc/configs/automated")

# Config files to update
CONFIG_FILES = [
    "dou_harmonization_anyllm_devstral.yaml",
    "dou_harmonization_anyllm_openrouter.yaml",
    "dou_harmonization_devstral.yaml",
    "dou_harmonization_devstral-small.yaml",
    "dou_harmonization_glm-4.5-air.yaml",
    "dou_harmonization_kimi-k2.yaml",
    "dou_harmonization_mimo-v2-flash.yaml",
    "dou_harmonization_nemotron-3-nano.yaml",
    "dou_harmonization_olmo3.yaml",
    "dou_harmonization_qwen3-coder.yaml",
]

# Evaluation block to add
EVALUATION_BLOCK = {
    "gold_standard": "/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/raw/datasets_harmonia/one_metadata_table_gdc_schema/gold_standard/harmonized_dou_correct.csv",
    "input_file": "/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/raw/datasets_harmonia/one_metadata_table_gdc_schema/data/dou.csv",
    "gold_column_mapping": "/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/raw/datasets_harmonia/one_metadata_table_gdc_schema/gold_standard/gold_standard_column_mapping.json",
    "gold_value_mapping": "/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/raw/datasets_harmonia/one_metadata_table_gdc_schema/gold_standard/gold_standard_value_mapping.json",
    "acceptable_columns_file": "/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/raw/datasets_harmonia/one_metadata_table_gdc_schema/gold_standard/harmonization_acceptable_columns.json",
    "column_mapping_file": "column_mapping.json",
    "value_mapping_file": "value_mapping.json",
    "index_column": None,
    "numeric_tolerance": None,
}

# New message to insert after the "save dou_harmonized.csv" message
NEW_MESSAGE = {
    "content": """Now save the column mapping you used as "results/column_mapping.json".
The format should be a JSON object where each key is the original source
column name and each value is the GDC column name it was mapped to.
For example: {"Country": "country_of_birth", "Age": "age_at_index", ...}
Include all columns, even those that were not mapped (set value to null).

Also save the value mapping as "results/value_mapping.json".
The format should be a JSON object where each key is the original source
column name, and each value is another object mapping each unique source
value to its harmonized target value.
For example: {"Histologic_Grade_FIGO": {"FIGO grade 1": "G1", "FIGO grade 2": "G2"}, ...}
For columns where values were not changed, use the string "__identity__" instead of
the mapping object.""",
    "wait_seconds": 300,
    "decision_mode": "auto_accept",
}

# Updated save_artifacts list
NEW_SAVE_ARTIFACTS = [
    "dou_harmonized.csv",
    "column_mapping.json",
    "value_mapping.json",
]

# Retry policy to mitigate transient provider/model failures
RETRY_POLICY = {
    "retry_delay_seconds": 5,
    "n_retries_per_error_code": {
        "openrouter_500": 3,
        "openrouter_5xx": 2,
        "openrouter_429": 3,
        "timeout": 2,
        "aimessage_validation_error": 1,
        "default": 0,
    },
}


def update_config(config_path: Path):
    """Update a single config file."""
    print(f"Updating {config_path.name}...")

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # 1. Add evaluation block
    config["evaluation"] = EVALUATION_BLOCK
    config["retry_policy"] = RETRY_POLICY

    # 2. Insert new message after message 5 (index 5, which is the "save dou_harmonized.csv" message)
    # First, find the message that contains "save it as" or "dou_harmonized.csv"
    messages = config.get("messages", [])

    # Find the index of the "save dou_harmonized.csv" message
    save_message_idx = None
    for i, msg in enumerate(messages):
        content = msg.get("content", "")
        if "dou_harmonized.csv" in content and "save" in content.lower():
            save_message_idx = i
            break

    if save_message_idx is not None:
        # Insert after this message
        messages.insert(save_message_idx + 1, NEW_MESSAGE)
        print(f"  ✓ Inserted new message after message {save_message_idx}")
    else:
        print(f"  ⚠ Could not find save message, appending to end")
        messages.append(NEW_MESSAGE)

    # 3. Update save_artifacts
    if "output" in config:
        config["output"]["save_artifacts"] = NEW_SAVE_ARTIFACTS
        print(f"  ✓ Updated save_artifacts")

    # Keep messages as the final top-level YAML section
    config.pop("messages", None)
    config["messages"] = messages

    # Write back to file
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"  ✓ Saved {config_path.name}")


def main():
    print("=" * 80)
    print("UPDATING CONFIG YAMLS")
    print("=" * 80)
    print()

    for config_file in CONFIG_FILES:
        config_path = CONFIG_DIR / config_file
        if not config_path.exists():
            print(f"✗ File not found: {config_file}")
            continue

        try:
            update_config(config_path)
            print()
        except Exception as e:
            print(f"  ✗ Error updating {config_file}: {e}")
            print()

    print("=" * 80)
    print("✓ All configs updated!")
    print("=" * 80)


if __name__ == "__main__":
    main()
