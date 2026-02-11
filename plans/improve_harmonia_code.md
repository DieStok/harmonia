# Harmonia Codebase Improvement Plan

**Created**: 2026-01-13
**Status**: Ready for review

This document outlines issues discovered during a thorough audit of the Harmonia codebase, organized by priority.

---

## Priority 1: Critical Security & Error Fixes

### 1.1 Remove Exposed API Keys from .env

**File**: `.env`
**Issue**: Real API keys are committed in plain text
**Risk**: Security vulnerability - keys can be harvested from repo history

**Current state**:

**Fix**:
1. Add `.env` to `.gitignore`
2. Create `.env.example` with placeholder values
3. Rotate the exposed keys immediately
4. Use environment variables or secrets manager

---

### 1.2 Fix Runtime Error in check_archytas.py

**File**: `check_archytas.py` (Line 42)
**Issue**: Accessing `config.LLM_SERVICE_TOKEN` but the attribute is lowercase `llm_service_token`

**Current**:
```python
print(f'  config.LLM_SERVICE_TOKEN = {config.LLM_SERVICE_TOKEN[:30]}...')
```

**Fix**:
```python
print(f'  config.llm_service_token = {config.llm_service_token[:30]}...')
```

---

## Priority 2: Dead Code Removal

### 2.1 Remove Unused Functions

| File | Function | Lines | Reason |
|------|----------|-------|--------|
| `src/automation/config.py` | `load_conversation()` | 107-124 | Never imported or called |
| `src/automation/client.py` | `get_notebook()` | 309-317 | Defined but never used |
| `src/automation/client.py` | `send_message_stream()` | 319-344 | Superseded by `send_message()` |

**Note**: `get_notebook()` was just added for the notebook sync feature but is not actually called. Consider keeping it for future use or removing if not needed.

---

### 2.2 Empty/Incomplete Procedure Files

**Location**: `src/bdikit_context/procedures/python3/`

These files are essentially stubs (1-3 lines each):
- `materialize_mapping.py`
- `match_values.py`
- `match_schema.py`
- `get_gdc_acceptable_values.py`
- `top_matches.py`

**Decision needed**:
- If templates are in `prompts/` directory, these may be orphaned
- Remove if unused, or complete if needed

---

## Priority 3: Configuration Consolidation

### 3.1 Unify LLM Configuration Systems

**Problem**: Three separate LLM config systems exist with inconsistent fields:

| Location | Fields |
|----------|--------|
| `src/automation/config.py` | provider, model, temperature |
| `src/bdikit_context/config/__init__.py` | provider, model, temperature, max_tokens, extra, base_url, api_key |
| `src/bdikit_context/llm/__init__.py` | Provider mapping + env var manipulation |

**Recommendation**:
1. Create single `LLMConfig` class with all fields
2. Use optional fields with defaults for backward compatibility
3. Centralize provider mapping in one location
4. Remove `reset_config()` workaround by properly handling env var changes

**Proposed unified structure**:
```python
@dataclass
class LLMConfig:
    provider: str
    model: str
    temperature: float = 0.0
    max_tokens: Optional[int] = None
    api_key: Optional[str] = None  # Read from env if not provided
    base_url: Optional[str] = None
    extra: dict = field(default_factory=dict)
```

---

### 3.2 Fix Missing DEFAULTS Key

**File**: `generate_jobs.py` (Line 104)
**Issue**: `DEFAULTS["tmpspace"]` accessed but key not in DEFAULTS dict

**Fix**:
```python
DEFAULTS = {
    "time_limit": "01:00:00",
    "memory": "8G",
    "cpus": "2",
    "timeout": "300",
    "tmpspace": "10G",  # Add this line
}
```

---

## Priority 4: Code Duplication Reduction

### 4.1 Consolidate Agent Tool Pattern

**File**: `src/bdikit_context/agent.py`
**Issue**: Same pattern repeated 5 times

**Current** (repeated 5x):
```python
code = agent.context.get_code("<procedure_name>", {...})
result = await agent.context.evaluate(code, parent_header={})
<result_name> = result.get("return")
return <result_name>
```

**Proposed refactor**:
```python
async def _execute_procedure(agent, procedure_name: str, params: dict) -> Any:
    """Execute a Beaker procedure and return the result."""
    code = agent.context.get_code(procedure_name, params)
    result = await agent.context.evaluate(code, parent_header={})
    return result.get("return")
```

Then simplify each tool method:
```python
@tool()
async def match_schema(method: str = "embeddings", agent: "BdikitAgent" = None):
    return await _execute_procedure(agent, "match_schema", {"method": method})
```

**Impact**: Reduces ~75 lines to ~30 lines, easier maintenance

---

### 4.2 Consolidate Dual Logger Calls

**File**: `src/automation/runner.py`
**Issue**: Both loggers always called together with identical parameters

**Option A**: Create combined logging method
```python
def _log_to_both(self, method_name: str, **kwargs):
    getattr(self.trace_logger, method_name)(**kwargs)
    getattr(self.conversation_logger, method_name)(**kwargs)
```

**Option B**: Create composite logger class that wraps both

---

## Priority 5: Architecture Improvements

### 5.1 Evaluate Decision Handling System

**Files**: `src/automation/runner.py` (Lines 190-258)
**Status**: Entire subsystem appears untested

Functions to evaluate:
- `_is_decision_point()` - Pattern matching for decision prompts
- `_handle_decision()` - Auto-accept/predefined/LLM modes
- `_find_predefined_response()` - Pattern-based response lookup

**Questions**:
1. Is this feature actively used?
2. Are there tests covering these paths?
3. Should it be removed or properly tested?

---

### 5.2 Fix Async Context Manager

**File**: `src/automation/client.py` (Lines 356-363)
**Issue**: `__aexit__` ignores exception parameters

**Current**:
```python
async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
    await self.disconnect()
```

**Improved**:
```python
async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
    try:
        await self.disconnect()
    except Exception:
        if exc_type is None:
            raise  # Only raise disconnect errors if no other exception
```

---

## Priority 6: Documentation Improvements

### 6.1 Add Missing Docstrings

| File | Function | Location |
|------|----------|----------|
| `src/bdikit_context/config/__init__.py` | `get_config()` | Line 114 |
| `src/bdikit_context/config/__init__.py` | `reset_config()` | Line 127 |
| `src/bdikit_context/__about__.py` | Module-level | Line 1 |

### 6.2 Document Tool Parameter Formats

**File**: `src/bdikit_context/agent.py`
**Issue**: String parameters don't document expected format

Example - `column_mapping: str` should note:
```python
Args:
    column_mapping: Comma-separated "source:target" pairs, e.g., "gender:sex,age:years"
```

---

## Priority 7: Cleanup Tasks

### 7.1 Organize Diagnostic Scripts

**Current location**: Project root
**Files**:
- `quick_test.py`
- `check_archytas.py`
- `diagnose_llm.py`

**Recommendation**: Move to `tools/` or `debug/` directory with README explaining purpose

### 7.2 Remove Hardcoded Values

| File | Line | Value | Recommendation |
|------|------|-------|----------------|
| `src/automation/client.py` | 254 | `30.0` seconds | Make configurable |
| `src/automation/runner.py` | 186 | `1` second sleep | Make configurable or remove |

---

## Implementation Order

1. **Immediate** (before next commit):
   - 1.1 Remove exposed API keys
   - 1.2 Fix check_archytas.py error

2. **Short-term** (next development cycle):
   - 2.1 Remove clearly unused functions
   - 3.2 Fix missing DEFAULTS key

3. **Medium-term** (planned refactoring):
   - 3.1 Unify LLM configuration
   - 4.1 Consolidate agent tool pattern

4. **Long-term** (when resources permit):
   - 5.1 Evaluate decision handling
   - 6.x Documentation improvements
   - 7.x Cleanup tasks

---

## Summary Statistics

| Category | Count |
|----------|-------|
| Security issues | 1 |
| Runtime errors | 1 |
| Dead code functions | 3 |
| Duplicate patterns | 2 |
| Missing config values | 1 |
| Documentation gaps | 5+ |
| Total files affected | 12 |

---

## Notes

- This audit was performed on 2026-01-13
- Total Python lines analyzed: ~1,367 across 22 files
- The codebase is generally well-structured but has accumulated technical debt
- Priority should be given to security and correctness fixes before feature work
