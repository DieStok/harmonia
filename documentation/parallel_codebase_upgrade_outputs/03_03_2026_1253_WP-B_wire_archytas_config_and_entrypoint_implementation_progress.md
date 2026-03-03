# WP-B: Wire ArchytasContextConfig + codeact_context Entry Point

**Date:** 2026-03-03
**Status:** Complete

## Summary

Wired `ArchytasContextConfig` fields (`max_react_steps`, `max_errors`) from YAML experiment
configs through to the Archytas `ReActAgent` instance at runtime, and registered the
`codeact_context` entry point in `pyproject.toml` for proper Beaker autodiscovery.

## Changes Made

### B1 -- Register `codeact_context` in `pyproject.toml`

**File:** `pyproject.toml`

Added `codeact_context = "codeact_context.context:CodeActContext"` to the
`[project.entry-points."beaker.contexts"]` section. Previously, `codeact_context` was missing
from entry points, meaning Beaker could only find it via `%set_context` magic fallback instead
of proper autodiscovery. Also added a comment noting that entry point changes require rebuilding
the Apptainer image.

### B2 -- Wire `max_react_steps` and `max_errors` in `bdikit_context/context.py`

**File:** `src/bdikit_context/context.py`

After `super().__init__()` (which creates `self.agent` internally via `BeakerContext.__init__`),
added a block that reads `ARCHYTAS_MAX_REACT_STEPS` and `ARCHYTAS_MAX_ERRORS` from environment
variables and patches the agent's instance attributes. This works because:

- `BeakerContext.__init__` instantiates the agent as `agent_cls(context=self, tools=...)` with
  no kwargs forwarded -- there is no way to pass these through the constructor.
- `ReActAgent.__init__` stores `max_errors` and `max_react_steps` as plain instance attributes
  (lines 234-235 of `react.py`) that are checked per-task in the react loop.
- Post-construction patching of these attributes is safe and effective.

The wiring block prints `[HarmoniaConfig]` messages to stdout when values are set, for
experiment log visibility.

### B3 -- Wire `max_react_steps` and `max_errors` in `code_context/context.py`

**File:** `src/code_context/context.py`

Identical wiring block added after `super().__init__()`. Also added `os` import (already
present) and `TYPE_CHECKING` imports for consistency.

### B4 -- Update `ArchytasContextConfig` comments in `config.py`

**File:** `src/automation/config.py`

Added inline comments to each field of `ArchytasContextConfig` indicating whether the field is:
- **WIRED** -- actually connected to the Archytas agent via env vars (`max_react_steps`,
  `max_errors`)
- **informational** -- defined in the config schema but not currently exposed in the installed
  Archytas `ReActAgent` API

### Verification: `generate_env.py` already writes ARCHYTAS env vars

**File:** `generate_env.py` (no changes needed)

Confirmed that `generate_env.py` already maps YAML config fields to environment variables:
- `max_react_steps` -> `ARCHYTAS_MAX_REACT_STEPS` (line 230)
- `max_errors` -> `ARCHYTAS_MAX_ERRORS` (line 231)

The full data flow is now: YAML config -> `generate_env.py` -> `.env` file -> env vars at
runtime -> context `__init__` -> `self.agent.max_react_steps` / `self.agent.max_errors`.

## Decisions

1. **codeact_context not wired:** The `CodeActContext` uses `CodeActAgent` which bypasses
   Archytas ReAct entirely (it manages its own agent loop via `CodeActAgentLoop`). It already
   reads `CODEACT_MAX_TURNS` from env vars for its own turn limit. The Archytas
   `max_react_steps`/`max_errors` wiring is not applicable here.

2. **Post-construction patching vs constructor kwargs:** Chose post-construction patching
   because `BeakerContext.__init__` does not forward kwargs to the agent constructor. This is
   a limitation of Beaker's architecture, not something we can change without forking Beaker.

3. **Print statements for observability:** Used `print()` with `[HarmoniaConfig]` prefix (not
   `logging`) to match the existing pattern in `bdikit_context/context.py` (e.g.,
   `[Harmonia] Using custom system prompt dir`).

## Files Modified

| File | Change |
|------|--------|
| `pyproject.toml` | Added `codeact_context` entry point + rebuild note |
| `src/bdikit_context/context.py` | Wired `max_react_steps` and `max_errors` from env vars |
| `src/code_context/context.py` | Wired `max_react_steps` and `max_errors` from env vars |
| `src/automation/config.py` | Added WIRED/informational comments to `ArchytasContextConfig` |

## Note

The `codeact_context` entry point change requires rebuilding the Apptainer image for the new
entry point to be discoverable at runtime. Until then, `codeact_context` continues to work
via `%set_context` magic fallback.
