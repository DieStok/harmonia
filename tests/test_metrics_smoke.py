"""
Smoke test: verify normalize.build_tables() works on a sample metrics.json.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

FIXTURE = Path(__file__).parent / "fixtures" / "sample_metrics.json"


def test_fixture_loads():
    data = json.loads(FIXTURE.read_text())
    assert "column_mapping" in data
    assert "column_values" in data
    assert "overall_summary" in data


def test_build_tables_returns_dataframes():
    from evaluation.visualization.normalize import build_tables

    data = json.loads(FIXTURE.read_text())
    # build_tables expects list[tuple[Path, dict]], not list[dict]
    bundle = [(FIXTURE, data)]
    tables = build_tables(bundle)
    assert tables is not None
    assert len(tables) > 0
    # Verify expected table keys
    assert "runs" in tables
    assert "column_mapping" in tables
    assert "column_values" in tables
    assert "confusion" in tables
    # Verify runs table has at least one row
    assert len(tables["runs"]) >= 1
