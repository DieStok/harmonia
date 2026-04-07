#!/usr/bin/env python3
"""
Script to create index CSV files by prepending Proteomics_Participant_ID column.

Creates:
1. dou_with_index.csv - dou.csv with Proteomics_Participant_ID prepended
2. harmonized_dou_correct_with_index.csv - harmonized_dou_correct.csv with Proteomics_Participant_ID prepended
"""

from pathlib import Path

import pandas as pd

# Define base paths
BASE_DIR = Path("/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/raw/datasets_harmonia/one_metadata_table_gdc_schema")
DATA_DIR = BASE_DIR / "data"
GOLD_DIR = BASE_DIR / "gold_standard"

def create_dou_with_index():
    """Create dou_with_index.csv by prepending Proteomics_Participant_ID to dou.csv"""
    print("Creating dou_with_index.csv...")

    # Read the discovery file (first 104 rows)
    discovery_df = pd.read_csv(DATA_DIR / "dou-ucec-discovery.csv", nrows=104)
    participant_ids = discovery_df["Proteomics_Participant_ID"]

    # Read the existing dou.csv
    dou_df = pd.read_csv(DATA_DIR / "dou.csv")

    # Verify row count matches
    if len(participant_ids) != len(dou_df):
        raise ValueError(f"Row count mismatch: discovery has {len(participant_ids)} rows, dou.csv has {len(dou_df)} rows")

    # Create new dataframe with Proteomics_Participant_ID as first column
    dou_with_index = pd.DataFrame({
        "Proteomics_Participant_ID": participant_ids.values
    })

    # Add all columns from dou.csv
    for col in dou_df.columns:
        dou_with_index[col] = dou_df[col].values

    # Write to file
    output_path = DATA_DIR / "dou_with_index.csv"
    dou_with_index.to_csv(output_path, index=False)
    print(f"✓ Created {output_path}")
    print(f"  Columns: {list(dou_with_index.columns)}")
    print(f"  Rows: {len(dou_with_index)}")

    return dou_with_index

def create_harmonized_dou_correct_with_index():
    """Create harmonized_dou_correct_with_index.csv by prepending Proteomics_Participant_ID"""
    print("\nCreating harmonized_dou_correct_with_index.csv...")

    # Read the discovery file (first 104 rows)
    discovery_df = pd.read_csv(DATA_DIR / "dou-ucec-discovery.csv", nrows=104)
    participant_ids = discovery_df["Proteomics_Participant_ID"]

    # Read the existing harmonized_dou_correct.csv
    harmonized_df = pd.read_csv(GOLD_DIR / "harmonized_dou_correct.csv")

    # Verify row count matches
    if len(participant_ids) != len(harmonized_df):
        raise ValueError(f"Row count mismatch: discovery has {len(participant_ids)} rows, harmonized has {len(harmonized_df)} rows")

    # Create new dataframe with Proteomics_Participant_ID as first column
    harmonized_with_index = pd.DataFrame({
        "Proteomics_Participant_ID": participant_ids.values
    })

    # Add all columns from harmonized_dou_correct.csv
    for col in harmonized_df.columns:
        harmonized_with_index[col] = harmonized_df[col].values

    # Write to file
    output_path = GOLD_DIR / "harmonized_dou_correct_with_index.csv"
    harmonized_with_index.to_csv(output_path, index=False)
    print(f"✓ Created {output_path}")
    print(f"  Columns: {list(harmonized_with_index.columns)}")
    print(f"  Rows: {len(harmonized_with_index)}")

    return harmonized_with_index

if __name__ == "__main__":
    try:
        dou_with_index = create_dou_with_index()
        harmonized_with_index = create_harmonized_dou_correct_with_index()

        print("\n✓ Successfully created both index CSV files!")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        raise
