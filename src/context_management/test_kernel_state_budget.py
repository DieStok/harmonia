"""Tests for kernel state budget enforcement."""

import pytest

from context_management.kernel_state_budget import BudgetConfig, apply_budget


def _make_state(variables: dict) -> dict:
    """Helper to create a minimal FETCH_STATE_CODE result dict."""
    return {
        "modules": {},
        "variables": variables,
        "functions": {},
        "classes": {},
    }


class TestBudgetConfig:
    def test_defaults(self):
        config = BudgetConfig()
        assert config.max_variable_size == 20_000
        assert config.total_budget == 50_000
        assert "SchemaGraph" in config.type_blacklist
        assert "df" in config.var_whitelist

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("HARMONIA_STATE_MAX_VAR_SIZE", "5000")
        monkeypatch.setenv("HARMONIA_STATE_TOTAL_BUDGET", "10000")
        monkeypatch.setenv("HARMONIA_STATE_TYPE_BLACKLIST", "Foo,Bar")
        monkeypatch.setenv("HARMONIA_STATE_VAR_WHITELIST", "x,y")
        config = BudgetConfig.from_env()
        assert config.max_variable_size == 5000
        assert config.total_budget == 10000
        assert config.type_blacklist == ["Foo", "Bar"]
        assert config.var_whitelist == ["x", "y"]


class TestApplyBudget:
    def test_empty_state(self):
        result, hashes = apply_budget(None, config=BudgetConfig())
        assert result == {}
        assert hashes == {}

    def test_empty_dict(self):
        result, hashes = apply_budget({}, config=BudgetConfig())
        assert result == {}
        assert hashes == {}

    def test_passthrough_small_variables(self):
        state = _make_state({
            "x": {"type": "int", "value": 42},
            "y": {"type": "str", "value": "hello"},
        })
        config = BudgetConfig(max_variable_size=0, total_budget=0)
        result, hashes = apply_budget(state, config=config)
        assert result["variables"]["x"]["value"] == 42
        assert result["variables"]["y"]["value"] == "hello"
        assert "_budget_metadata" not in result

    def test_type_blacklist_drops_variable(self):
        state = _make_state({
            "graph": {"type": "SchemaGraph", "value": "big"},
            "df": {"type": "DataFrame", "value": "small"},
        })
        config = BudgetConfig(
            type_blacklist=["SchemaGraph"],
            var_whitelist=[],
            max_variable_size=0,
            total_budget=0,
        )
        result, _ = apply_budget(state, config=config)
        assert result["variables"]["graph"]["_dropped"] is True
        assert "blacklisted_type" in result["variables"]["graph"]["value"]
        assert result["variables"]["df"]["value"] == "small"

    def test_whitelist_overrides_blacklist(self):
        state = _make_state({
            "df": {"type": "SchemaGraph", "value": "important"},
        })
        config = BudgetConfig(
            type_blacklist=["SchemaGraph"],
            var_whitelist=["df"],
            max_variable_size=0,
            total_budget=0,
        )
        result, _ = apply_budget(state, config=config)
        # Whitelisted var should be kept despite type blacklist
        assert result["variables"]["df"]["value"] == "important"
        assert result["variables"]["df"].get("_dropped") is None

    def test_per_variable_size_cap(self):
        large_value = "x" * 30_000
        state = _make_state({
            "small": {"type": "int", "value": 1},
            "big": {"type": "dict", "value": large_value},
        })
        config = BudgetConfig(
            max_variable_size=20_000,
            total_budget=0,
            type_blacklist=[],
            var_whitelist=[],
        )
        result, _ = apply_budget(state, config=config)
        assert result["variables"]["small"]["value"] == 1
        assert result["variables"]["big"]["_dropped"] is True

    def test_whitelist_overrides_size_cap(self):
        large_value = "x" * 30_000
        state = _make_state({
            "df_harmonized": {"type": "DataFrame", "value": large_value},
            "big_internal": {"type": "dict", "value": large_value},
        })
        config = BudgetConfig(
            max_variable_size=20_000,
            total_budget=0,
            var_whitelist=["df_harmonized"],
            type_blacklist=[],
        )
        result, _ = apply_budget(state, config=config)
        assert result["variables"]["df_harmonized"].get("_dropped") is None  # kept
        assert result["variables"]["big_internal"]["_dropped"] is True  # dropped

    def test_total_budget_cap(self):
        # Create variables that individually fit but together exceed the budget
        val = "x" * 5000
        state = _make_state({
            "a": {"type": "str", "value": val},
            "b": {"type": "str", "value": val},
            "c": {"type": "str", "value": val},
        })
        config = BudgetConfig(
            max_variable_size=0,  # disabled
            total_budget=12_000,  # will fit ~2 of the 3 vars
            type_blacklist=[],
            var_whitelist=[],
        )
        result, _ = apply_budget(state, config=config)
        vars_ = result["variables"]
        dropped = [k for k, v in vars_.items() if v.get("_dropped")]
        kept = [k for k, v in vars_.items() if not v.get("_dropped")]
        # At least one should be dropped due to budget
        assert len(dropped) >= 1
        assert len(kept) >= 1

    def test_delta_tracking_unchanged(self):
        state = _make_state({
            "x": {"type": "int", "value": 42, "size": ""},
            "y": {"type": "str", "value": "hello", "size": "5"},
        })
        config = BudgetConfig(
            max_variable_size=0,
            total_budget=0,
            type_blacklist=[],
            var_whitelist=[],
        )

        # First call: everything is new, all sent in full
        result1, hashes1 = apply_budget(state, config=config, prev_hashes=None)
        assert result1["variables"]["x"]["value"] == 42
        assert result1["variables"]["y"]["value"] == "hello"

        # Second call with same state and previous hashes: unchanged → compact
        state2 = _make_state({
            "x": {"type": "int", "value": 42, "size": ""},
            "y": {"type": "str", "value": "hello", "size": "5"},
        })
        result2, hashes2 = apply_budget(state2, config=config, prev_hashes=hashes1)
        assert result2["variables"]["x"].get("_unchanged") is True
        assert result2["variables"]["y"].get("_unchanged") is True

    def test_delta_tracking_changed_var_sent_in_full(self):
        state1 = _make_state({
            "x": {"type": "int", "value": 42, "size": ""},
        })
        config = BudgetConfig(
            max_variable_size=0,
            total_budget=0,
            type_blacklist=[],
            var_whitelist=[],
        )
        _, hashes1 = apply_budget(state1, config=config, prev_hashes=None)

        # Change the value
        state2 = _make_state({
            "x": {"type": "int", "value": 99, "size": ""},
        })
        result2, _ = apply_budget(state2, config=config, prev_hashes=hashes1)
        # Changed variable should be sent in full
        assert result2["variables"]["x"]["value"] == 99
        assert result2["variables"]["x"].get("_unchanged") is None

    def test_budget_metadata_present_when_dropped(self):
        state = _make_state({
            "graph": {"type": "SchemaGraph", "value": "big"},
            "x": {"type": "int", "value": 1},
        })
        config = BudgetConfig(
            type_blacklist=["SchemaGraph"],
            var_whitelist=[],
            max_variable_size=0,
            total_budget=0,
        )
        result, _ = apply_budget(state, config=config)
        assert "_budget_metadata" in result
        assert result["_budget_metadata"]["dropped_count"] == 1

    def test_budget_metadata_absent_when_nothing_dropped(self):
        state = _make_state({
            "x": {"type": "int", "value": 1},
        })
        config = BudgetConfig(
            type_blacklist=[],
            var_whitelist=[],
            max_variable_size=0,
            total_budget=0,
        )
        result, _ = apply_budget(state, config=config, prev_hashes=None)
        assert "_budget_metadata" not in result

    def test_whitelist_skips_delta_tracking(self):
        """Whitelisted vars are always sent in full, even if unchanged."""
        state = _make_state({
            "df": {"type": "DataFrame", "value": "data", "size": "10x3"},
        })
        config = BudgetConfig(
            max_variable_size=0,
            total_budget=0,
            type_blacklist=[],
            var_whitelist=["df"],
        )
        _, hashes1 = apply_budget(state, config=config, prev_hashes=None)

        # Same state, same hashes — but df is whitelisted so should be full
        state2 = _make_state({
            "df": {"type": "DataFrame", "value": "data", "size": "10x3"},
        })
        result2, _ = apply_budget(state2, config=config, prev_hashes=hashes1)
        assert result2["variables"]["df"]["value"] == "data"
        assert result2["variables"]["df"].get("_unchanged") is None
