# REFERENCE ONLY: This module is NOT imported at runtime by any Beaker context.
# The budget enforcement logic is injected into the Beaker Python subkernel via
# the FETCH_STATE_CODE patch in harmonia_beaker_LLM_agent_environment_apptainer.def.
# This file exists as a canonical reference and test target only.
"""
Kernel state budget enforcement for Beaker's FETCH_STATE_CODE.

This module is the canonical reference implementation of the budget logic that
is also inlined into FETCH_STATE_CODE via the Apptainer build patch. It serves as:
  - The unit test target
  - Documentation of the budget algorithm
  - A fallback for non-container use (e.g., manual interactive experiments)

The budget enforcement applies four strategies (in order):
  1. Type blacklisting: exclude variables whose type name contains blacklisted substrings
  2. Delta tracking: unchanged variables (same hash as previous call) get compact summaries
  3. Per-variable size cap: drop variables exceeding max_variable_size chars
  4. Total budget cap: stop adding variables once total budget is reached

Whitelisted variables are exempt from steps 1, 3, and 4 (always kept in full).
Delta tracking (step 2) is also skipped for whitelisted vars so they're always current.

Budget parameters are read from environment variables at runtime:
  HARMONIA_STATE_MAX_VAR_SIZE: max chars per variable (default: 20000)
  HARMONIA_STATE_TOTAL_BUDGET: absolute total budget in chars (default: 50000)
  HARMONIA_STATE_BUDGET_PCT: informational (% of context window, used by exec script to calc total)
  HARMONIA_STATE_TYPE_BLACKLIST: comma-separated type substrings to exclude
  HARMONIA_STATE_VAR_WHITELIST: comma-separated variable names to always keep in full

See: docs/plans/25_02_2026_2238_fix_context_issues.md (Fix 2)
"""

import json
import os
from dataclasses import dataclass, field


@dataclass
class BudgetConfig:
    """Configuration for kernel state budget enforcement."""
    max_variable_size: int = 20_000
    total_budget: int = 50_000
    type_blacklist: list[str] = field(default_factory=lambda: [
        "SchemaGraph", "SimilarityFloodingMatcher",
        "ColumnMappingSpec", "ValueMappingSpec",
    ])
    var_whitelist: list[str] = field(default_factory=lambda: [
        "df", "df_harmonized", "df_subset", "result", "results",
        "output", "harmonized", "mapping", "column_mapping", "value_mapping",
    ])

    @classmethod
    def from_env(cls) -> "BudgetConfig":
        """Create a BudgetConfig from environment variables."""
        type_bl_str = os.environ.get(
            "HARMONIA_STATE_TYPE_BLACKLIST",
            "SchemaGraph,SimilarityFloodingMatcher,ColumnMappingSpec,ValueMappingSpec",
        )
        var_wl_str = os.environ.get(
            "HARMONIA_STATE_VAR_WHITELIST",
            "df,df_harmonized,df_subset,result,results,output,harmonized,mapping,column_mapping,value_mapping",
        )
        return cls(
            max_variable_size=int(os.environ.get("HARMONIA_STATE_MAX_VAR_SIZE", "20000")),
            total_budget=int(os.environ.get("HARMONIA_STATE_TOTAL_BUDGET", "50000")),
            type_blacklist=[s.strip() for s in type_bl_str.split(",") if s.strip()],
            var_whitelist=[s.strip() for s in var_wl_str.split(",") if s.strip()],
        )


def apply_budget(
    state: dict | None,
    config: BudgetConfig | None = None,
    prev_hashes: dict[str, int] | None = None,
) -> tuple[dict, dict[str, int]]:
    """
    Apply budget enforcement to a FETCH_STATE_CODE result dict.

    Args:
        state: The raw state dict from FETCH_STATE_CODE (has keys: modules, variables, functions, classes).
        config: Budget configuration. If None, reads from env vars.
        prev_hashes: Dict mapping variable names to their previous hash values for delta tracking.
                     Pass None on first call; pass the returned new_hashes on subsequent calls.

    Returns:
        Tuple of (budgeted_state, new_hashes) where new_hashes should be passed back
        as prev_hashes on the next call.
    """
    if config is None:
        config = BudgetConfig.from_env()
    if prev_hashes is None:
        prev_hashes = {}

    if not state or not isinstance(state, dict):
        return state or {}, {}

    variables = state.get("variables", {})
    budgeted = {}
    running_size = 0
    dropped_count = 0
    unchanged_count = 0
    new_hashes: dict[str, int] = {}

    # Measure all variable sizes and compute hashes for delta tracking
    sized: list[tuple[str, dict, int, int]] = []
    for var_name, var_info in variables.items():
        try:
            serialized = json.dumps(var_info, default=str)
            var_size = len(serialized)
            var_hash = hash(serialized)
        except Exception:
            var_size = 0
            var_hash = 0
        sized.append((var_name, var_info, var_size, var_hash))
        new_hashes[var_name] = var_hash

    # Sort by size ascending to fit as many variables as possible within budget
    sized.sort(key=lambda x: x[2])

    for var_name, var_info, var_size, var_hash in sized:
        var_type = str(var_info.get("type", ""))
        is_whitelisted = var_name in config.var_whitelist

        # Step 1: Check type blacklist (whitelist overrides blacklist)
        if not is_whitelisted and any(bl in var_type for bl in config.type_blacklist):
            budgeted[var_name] = {
                "type": var_type,
                "value": f"<dropped: blacklisted_type, size={var_size:,}>",
                "_dropped": True,
            }
            dropped_count += 1
            continue

        # Step 2: Delta tracking — if variable unchanged, send compact summary only
        # (whitelisted vars always sent in full)
        if not is_whitelisted and var_name in prev_hashes and prev_hashes[var_name] == var_hash:
            compact = {"type": var_type, "size": var_info.get("size", ""), "_unchanged": True}
            budgeted[var_name] = compact
            running_size += len(json.dumps(compact, default=str))
            unchanged_count += 1
            continue

        # Step 3: Per-variable size check (whitelist exempt)
        if not is_whitelisted and config.max_variable_size > 0 and var_size > config.max_variable_size:
            budgeted[var_name] = {
                "type": var_type,
                "value": f"<dropped: size={var_size:,} > max={config.max_variable_size:,}>",
                "_dropped": True,
            }
            dropped_count += 1
            continue

        # Step 4: Total budget check (whitelist exempt from dropping but still counted)
        if not is_whitelisted and config.total_budget > 0 and (running_size + var_size) > config.total_budget:
            budgeted[var_name] = {
                "type": var_type,
                "value": f"<dropped: total_budget_exceeded, size={var_size:,}>",
                "_dropped": True,
            }
            dropped_count += 1
            continue

        budgeted[var_name] = var_info
        running_size += var_size

    state["variables"] = budgeted

    if dropped_count > 0 or unchanged_count > 0:
        state["_budget_metadata"] = {
            "dropped_count": dropped_count,
            "unchanged_count": unchanged_count,
            "budget_total": config.total_budget,
            "max_var_size": config.max_variable_size,
            "final_size_chars": running_size,
        }

    return state, new_hashes
