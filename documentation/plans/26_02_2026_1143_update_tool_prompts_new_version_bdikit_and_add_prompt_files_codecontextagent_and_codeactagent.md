# Plan: Update Tool Prompts for bdi-kit v0.9 + Add Prompt Files for Code/CodeAct Contexts

**Date:** 26 February 2026
**Status:** Ready for implementation
**Prerequisites:** Execute alongside or after the bdi-kit v0.9 upgrade plan (`25_02_2026_1527_update_bdikit_and_add_proper_LLM_selection_for_schema_and_value_matching_tools.md`)

## 1. Problem Statement

Three issues need addressing:

### 1a. Tool prompts and procedures are outdated for bdi-kit v0.9

The bdi-kit upgrade from v0.5-dev to v0.9 renamed several API functions and parameters. Two procedure templates and their tool prompts reference functions/params that no longer exist:

| Procedure/Tool | Broken Call | v0.9 Replacement |
|---|---|---|
| `top_matches.py` | `bdi.top_matches(df, columns=[...])` | `bdi.rank_schema_matches(df, attributes=[...])` |
| `get_gdc_acceptable_values.py` | `bdi.preview_domain("gdc", column="...")` | `bdi.preview_domain("gdc", attribute="...")` |

Additionally, tool descriptions don't mention the new matching methods (`magneto_*`, `llm`, `llm_numeric`) or `method_args`.

### 1b. The `top_matches` Archytas tool must be renamed to `rank_schema_matches`

The agent-facing tool name, Python method, procedure template, and tool prompt all need renaming from `top_matches` to `rank_schema_matches`.

### 1c. Code Context and CodeAct Context have no versioned prompt files

Currently their system prompts are inline strings in `context.py`. This makes it impossible to:
- Track prompt changes across experiments
- Run the same experiment with different prompts
- Version prompts independently from code

## 2. Scope

### Files to modify

| File | Change |
|---|---|
| `src/bdikit_context/agent.py` | Rename `top_matches` tool to `rank_schema_matches`; update `get_gdc_acceptable_values` param |
| `src/bdikit_context/procedures/python3/top_matches.py` | Rename to `rank_schema_matches.py`, fix API call |
| `src/bdikit_context/procedures/python3/get_gdc_acceptable_values.py` | Fix `column` -> `attribute` param |
| `src/bdikit_context/prompts/tools/top_matches.j2` | Rename to `rank_schema_matches.j2`, update content |
| `src/bdikit_context/prompts/tools/match_schema.j2` | Update to list v0.9 methods |
| `src/bdikit_context/prompts/tools/match_values.j2` | Update to list v0.9 methods, fix description |
| `src/bdikit_context/prompts/tools/get_gdc_acceptable_values.j2` | Fix `column` -> `attribute` |
| `src/bdikit_context/prompts/system/main.j2` | Replace `top_matches` references with `rank_schema_matches` |
| `src/bdikit_context/context.py` | Update tool list in `auto_context()` |
| `src/code_context/prompts/v1/system.txt` | **NEW** — extract inline prompt |
| `src/codeact_context/prompts/v1/system.txt` | **NEW** — extract inline prompt |
| `src/codeact_context/prompts/v1/summary_template.txt` | **NEW** — extract inline summary template |
| `generate_env.py` | Add `codeact_summary_template` handling (already done per system reminders) |

### Files that do NOT need changes

- `materialize_mapping.j2` / `materialize_mapping.py` — API unchanged
- `pyproject.toml` — no dependency changes
- `exec_apptainer_harmonia.sh` — no env var changes needed
- `prompt_logging.py` — no new env vars

## 3. Detailed Implementation Steps

---

### Step 1: Rename `top_matches` tool to `rank_schema_matches` in `agent.py`

**File:** `src/bdikit_context/agent.py`

The current `top_matches` method (lines 118-161) must be renamed and updated. The v0.9 API is:

```python
bdi.rank_schema_matches(source, target="gdc", attributes=["col1"], top_k=10, method=..., method_args=...)
```

**Current code (lines 118-161):**
```python
@tool()
async def top_matches(
    self,
    dataset: str,
    columns: str,
    agent: AgentRef,
    target: Optional[str] = None,
) -> str:
    """
    Returns the top 10 schema matches between the source and target tables. This is useful
    for evaluating alternative column mappings.

    Args:
        dataset (str): The name of the dataset variable.
        columns (str): The column to match.
        target (str, optional): The target table or standard data vocabulary.

    Returns:
        str: returns the top 10 matches
    """
    # Apply defaults
    if target is None or target == "":
        target = DEFAULT_TARGET

    # Validate target
    if target not in VALID_TARGETS:
        return f"Error: Invalid target '{target}'. Valid targets are: {', '.join(VALID_TARGETS)}. Please try again with a valid target."

    code = agent.context.get_code(
        "top_matches",
        {
            "dataset": dataset,
            "columns": columns,
            "target": target
        },
    )
    result = await agent.context.evaluate(
        code,
        parent_header={},
    )

    match_result = result.get("return")

    return match_result
```

**Replace with:**
```python
@tool()
async def rank_schema_matches(
    self,
    dataset: str,
    attribute: str,
    agent: AgentRef,
    target: Optional[str] = None,
    top_k: Optional[int] = None,
) -> str:
    """
    Returns the top-k schema matches between the source and target tables for a given attribute.
    This is useful for evaluating alternative column mappings when the initial match_schema result seems incorrect.

    Args:
        dataset (str): The name of the dataset variable.
        attribute (str): The source attribute/column to find alternative matches for.
        target (str, optional): The target table or standard data vocabulary.
        top_k (int, optional): Number of top matches to return. Defaults to 10.

    Returns:
        str: returns the top-k alternative schema matches for the given attribute
    """
    # Apply defaults
    if target is None or target == "":
        target = DEFAULT_TARGET
    if top_k is None:
        top_k = 10

    # Validate target
    if target not in VALID_TARGETS:
        return f"Error: Invalid target '{target}'. Valid targets are: {', '.join(VALID_TARGETS)}. Please try again with a valid target."

    code = agent.context.get_code(
        "rank_schema_matches",
        {
            "dataset": dataset,
            "attribute": attribute,
            "target": target,
            "top_k": top_k,
        },
    )
    result = await agent.context.evaluate(
        code,
        parent_header={},
    )

    match_result = result.get("return")

    return match_result
```

**Key changes:**
- Method name: `top_matches` -> `rank_schema_matches`
- Parameter: `columns` -> `attribute` (singular, since it takes one column at a time)
- Added `top_k` parameter (default 10)
- Procedure key: `"top_matches"` -> `"rank_schema_matches"`
- Template variables: `columns` -> `attribute`

Also update `get_gdc_acceptable_values` (lines 321-349) — rename the parameter from `column` to `attribute` end-to-end to match v0.9's terminology. This avoids confusing the LLM if it inspects bdi-kit help or reads error tracebacks.

**Current code (lines 321-349):**
```python
@tool()
async def get_gdc_acceptable_values(self, column: str, agent: AgentRef) -> str:
    """
    Returns the acceptable values for a given column in the GDC standard.

    Args:
        column (str): The name of the variable/column in the GDC target schema.

    Returns:
        str: returns a list of acceptable values (and their descriptions) for the given column in the GDC standard
    """
    # Validate column is provided
    if not column or column.strip() == "":
        return "Error: Column name is required. Please provide a valid GDC column name."

    code = agent.context.get_code(
        "get_gdc_acceptable_values",
        {
            "column": column,
        },
    )
```

**Replace with:**
```python
@tool()
async def get_gdc_acceptable_values(self, attribute: str, agent: AgentRef) -> str:
    """
    Returns the acceptable values for a given attribute in the GDC standard.

    Args:
        attribute (str): The name of the attribute/column in the GDC target schema.

    Returns:
        str: returns a list of acceptable values (and their descriptions) for the given attribute in the GDC standard
    """
    # Validate attribute is provided
    if not attribute or attribute.strip() == "":
        return "Error: Attribute name is required. Please provide a valid GDC attribute name."

    code = agent.context.get_code(
        "get_gdc_acceptable_values",
        {
            "attribute": attribute,
        },
    )
```

**Changes:** `column` -> `attribute` in: Python parameter name, docstring, validation, and template variable. This keeps the LLM-facing interface consistent with the bdi-kit v0.9 API.

---

### Step 2: Rename and update procedure template `top_matches.py` -> `rank_schema_matches.py`

**Delete:** `src/bdikit_context/procedures/python3/top_matches.py`

**Create:** `src/bdikit_context/procedures/python3/rank_schema_matches.py`

**Current content of `top_matches.py`:**
```python
import bdikit as bdi
top_matches = bdi.top_matches({{ dataset }}, columns=["{{ columns }}"], target="{{ target }}")
top_matches.to_markdown()
```

**New content of `rank_schema_matches.py`:**
```python
import bdikit as bdi
top_matches = bdi.rank_schema_matches({{ dataset }}, attributes=["{{ attribute }}"], target="{{ target }}", top_k={{ top_k }})
top_matches.to_markdown()
```

**Changes:**
- `bdi.top_matches()` -> `bdi.rank_schema_matches()`
- `columns=` -> `attributes=`
- `{{ columns }}` -> `{{ attribute }}`
- Added `top_k={{ top_k }}`

---

### Step 3: Update procedure template `get_gdc_acceptable_values.py`

**File:** `src/bdikit_context/procedures/python3/get_gdc_acceptable_values.py`

**Current content:**
```python
import bdikit as bdi
gdc_acceptable_values = bdi.preview_domain("gdc", column="{{ column }}")
gdc_acceptable_values.to_markdown()
```

**New content:**
```python
import bdikit as bdi
gdc_acceptable_values = bdi.preview_domain("gdc", attribute="{{ attribute }}")
gdc_acceptable_values.to_markdown()
```

**Change:** `column=` -> `attribute=`, `{{ column }}` -> `{{ attribute }}`

---

### Step 4: Rename and update tool prompt `top_matches.j2` -> `rank_schema_matches.j2`

**Delete:** `src/bdikit_context/prompts/tools/top_matches.j2`

**Create:** `src/bdikit_context/prompts/tools/rank_schema_matches.j2`

**Current content of `top_matches.j2`:**
```jinja2
{# Tool description for top_matches #}
Returns the top {{ top_k | default(10) }} schema matches between the source and target tables.

This is useful for evaluating alternative column mappings when the initial match seems incorrect.

Args:
    dataset (str): The name of the dataset variable.
    columns (str): The column to match.
    target (str, optional): The target table or standard data vocabulary.

Returns:
    str: returns the top {{ top_k | default(10) }} matches
```

**New content of `rank_schema_matches.j2`:**
```jinja2
{# Tool description for rank_schema_matches #}
Returns the top-k alternative schema matches for a given source attribute.

Use this when the initial match_schema result looks incorrect for a particular column. It returns ranked alternatives so you can pick the best semantic match.

Args:
    dataset (str): The name of the dataset variable.
    attribute (str): The source attribute/column to find alternative matches for.
    target (str, optional): The target table or standard data vocabulary. Defaults to "gdc".
    top_k (int, optional): Number of top matches to return. Defaults to 10.

Returns:
    str: returns the top-k alternative schema matches ranked by similarity score

You should show the user the alternatives and help them pick the most semantically appropriate match.
```

---

### Step 5: Update tool prompt `match_schema.j2`

**File:** `src/bdikit_context/prompts/tools/match_schema.j2`

**Current content:**
```jinja2
{# Tool description for match_schema #}
This function performs schema mapping between the source table and the given target schema.

The target is either a DataFrame or a string representing a standard data vocabulary supported by the library. Currently, only the GDC (Genomic Data Commons) standard vocabulary is supported.

Args:
    dataset (str): The name of the dataset variable.
    target (str, optional): The target table or standard data vocabulary.
    method (str, optional): The method used for mapping.

Returns:
    str: returns the matched columns

You should show the user the result after this function runs.
```

**New content:**
```jinja2
{# Tool description for match_schema #}
Performs schema matching between the source table and the given target schema. For each source column, finds the best-matching column in the target schema.

The target is either a DataFrame or a string representing a standard data vocabulary. Currently, only the GDC (Genomic Data Commons) standard vocabulary is supported.

Available methods:
- magneto_ft_bp (default): Fine-tuned Magneto model with bipartite reranker. Good general-purpose method.
- magneto_zs_bp: Zero-shot Magneto with bipartite reranker.
- magneto_ft_llm: Fine-tuned Magneto with LLM-based reranker. Uses an LLM for final ranking.
- magneto_zs_llm: Zero-shot Magneto with LLM-based reranker.
- llm: Pure LLM-based schema matching. Sends column names to an LLM for matching.
- similarity_flooding, coma, cupid, distribution_based, jaccard_distance: Traditional schema matching algorithms.
- two_phase: Two-phase approach combining top-k retrieval with one-to-one matching.

Args:
    dataset (str): The name of the dataset variable.
    target (str, optional): The target table or standard data vocabulary. Defaults to "gdc".
    method (str, optional): The schema matching method. Defaults to "magneto_ft_bp".

Returns:
    str: returns the matched columns with similarity scores

You should show the user the result after this function runs.
```

---

### Step 6: Update tool prompt `match_values.j2`

**File:** `src/bdikit_context/prompts/tools/match_values.j2`

**Current content:**
```jinja2
{# Tool description for match_values #}
Returns the top 10 value matches between the values of the source and target columns.

This is useful for evaluating value matches between a pair of columns (column mappings) returned by the match_schema function.

Args:
    dataset (str): The name of the dataset variable.
    column_mapping (tuple): The column and target names for which to find value matches. Format: "source_column,target_column"
    target (str, optional): The target table or standard data vocabulary.
    method (str, optional): The method used for mapping.

Returns:
    str: returns the value matches for the given column mapping

Upon user's request, the output of match_values() can be fed to materialize_mapping() which materializes the final target using both schema and value mappings.
```

**New content:**
```jinja2
{# Tool description for match_values #}
Finds the best value mappings between source values and target values for a given pair of matched columns.

For each unique value in the source column, finds the closest matching value in the target column's acceptable values.

Available methods:
- tfidf (default): TF-IDF based text similarity. Fast, works well for similar text values.
- embedding: Embedding-based similarity using sentence transformers. Better for semantic similarity.
- llm: LLM-based value matching. Best for complex semantic mappings but slower.
- llm_numeric: LLM-based matching for numeric values. Derives transformation formulas.
- edit_distance: Character-level edit distance. Best for near-identical strings with typos.

Args:
    dataset (str): The name of the dataset variable.
    column_mapping (tuple): The source and target column names. Format: "source_column,target_column"
    target (str, optional): The target table or standard data vocabulary. Defaults to "gdc".
    method (str, optional): The value matching method. Defaults to "tfidf".

Returns:
    str: returns the value mappings for the given column pair

The output of match_values() can be fed to materialize_mapping() to create the final harmonized table.
```

---

### Step 7: Update tool prompt `get_gdc_acceptable_values.j2`

**File:** `src/bdikit_context/prompts/tools/get_gdc_acceptable_values.j2`

**Current content:**
```jinja2
{# Tool description for get_gdc_acceptable_values #}
Returns the acceptable values for a given column in the GDC (Genomic Data Commons) standard.

This is useful for checking what values can be used as target values when mapping to the GDC schema.

Args:
    column (str): The name of the variable/column in the GDC target schema.

Returns:
    str: returns a list of acceptable values (and their descriptions) for the given column in the GDC standard
```

**New content:**
```jinja2
{# Tool description for get_gdc_acceptable_values #}
Returns the acceptable values and their descriptions for a given attribute in the GDC (Genomic Data Commons) standard.

Use this to check what values are valid for a target attribute when correcting value mappings.

Args:
    attribute (str): The name of the attribute/column in the GDC target schema.

Returns:
    str: returns a list of acceptable values (and their descriptions) for the given attribute in the GDC standard
```

---

### Step 8: Update system prompt `main.j2`

**File:** `src/bdikit_context/prompts/system/main.j2`

Two changes needed:

**Change 1:** Replace `top_matches` with `rank_schema_matches` everywhere.

Line 20, change:
```
For all columns in the source table, find the best column mappings in the target GDC schema using `match_schema` and `top_matches`.
```
To:
```
For all columns in the source table, find the best column mappings in the target GDC schema using `match_schema` and `rank_schema_matches`.
```

Line 22, change:
```
Once you have run `match_schema`, analyze the matches. If any pair of columns seems incorrect (e.g., if they are semantically different), run `top_matches` and select the best alternative column match. The best alternative is not always the one with the highest score - consider the meaning of the column name to select the best match.
```
To:
```
Once you have run `match_schema`, analyze the matches. If any pair of columns seems incorrect (e.g., if they are semantically different), run `rank_schema_matches` and select the best alternative column match. The best alternative is not always the one with the highest score - consider the meaning of the column name to select the best match.
```

**Change 2: No other changes needed.** The rest of the system prompt is workflow guidance that remains valid. The tool list is dynamically generated from the `tools` variable passed in `auto_context()` (Step 9 handles that).

---

### Step 9: Update `auto_context()` tool list in `context.py`

**File:** `src/bdikit_context/context.py`

**Current (lines 93-98):**
```python
tools = [
    {"name": "match_schema", "description": "Performs schema mapping between source and target tables"},
    {"name": "top_matches", "description": "Returns top 10 alternative column mappings for evaluation"},
    {"name": "match_values", "description": "Finds value matches between column pairs"},
    {"name": "materialize_mapping", "description": "Creates the final harmonized table"},
    {"name": "get_gdc_acceptable_values", "description": "Lists acceptable values for GDC columns"},
]
```

**Replace with:**
```python
tools = [
    {"name": "match_schema", "description": "Performs schema matching between source and target tables"},
    {"name": "rank_schema_matches", "description": "Returns top-k alternative column mappings for a given attribute"},
    {"name": "match_values", "description": "Finds value mappings between matched column pairs"},
    {"name": "materialize_mapping", "description": "Creates the final harmonized table"},
    {"name": "get_gdc_acceptable_values", "description": "Lists acceptable values for GDC attributes"},
]
```

---

### Step 10: Create versioned prompt files for Code Context

**Create directory:** `src/code_context/prompts/v1/`

**Create file:** `src/code_context/prompts/v1/system.txt`

Extract the current inline prompt from `src/code_context/context.py` lines 64-83. The file should contain exactly:

```
You are a Python code execution assistant running in a Jupyter-like environment.

## Your Capabilities
- You can write and execute Python code
- You have access to a Python3 kernel
- Common data science libraries are available (pandas, numpy, etc.)

## Environment
- Working directory: Use `os.getcwd()` to check
- Available directories can be listed with `os.listdir()`

## Instructions
1. When asked to do something, write Python code to accomplish it
2. Execute the code to show results
3. Be concise in explanations
4. If you encounter errors, debug and fix them

## Code Execution
To execute code, use the code execution tool. The output will be shown to the user.
```

**Note:** The inline prompt uses `{self.subkernel.DISPLAY_NAME}` which resolves at runtime. In the file version, use "Python3" since that's the only enabled subkernel. This is a minor difference — if dynamic kernel names become needed, the loading code can do string substitution.

---

### Step 11: Create versioned prompt files for CodeAct Context

**Create directory:** `src/codeact_context/prompts/v1/`

**Create file:** `src/codeact_context/prompts/v1/system.txt`

Extract the current inline prompt from `src/codeact_context/context.py` lines 92-106:

```
You are a data scientist working in a Python environment with a persistent Jupyter kernel.

You have access to pandas, numpy, and other data science libraries.

When you need to do something, write Python code in a ```python code block.
I will execute it and show you the output. You can then write more code based on the results.

When you are done with the task and want to give a final answer, just respond with text (no code block).

Important:
- Variables persist between code blocks (this is a persistent kernel session)
- Use print() to see output — bare expressions do not display
- If you get an error, read the traceback and fix your code
- Working directory: use os.getcwd() and os.listdir() to explore
```

**Create file:** `src/codeact_context/prompts/v1/summary_template.txt`

Extract the current `DEFAULT_SUMMARY_TEMPLATE` from `src/codeact_context/agent.py` lines 40-52:

```
You have been working on a data harmonization task. Your conversation history is getting long and needs to be summarized to continue.

Please provide a concise summary of:
1. What task you were given
2. What steps you have completed so far
3. What the current state of the work is (any errors, partial results, etc.)
4. A list of all Python variables currently in the environment and their purpose

Write ONLY the summary, no code blocks. Be specific about file names, column names, and any mappings you have discovered or created.
```

---

### Step 12: Update `code_context/context.py` to use prompt file as default

**File:** `src/code_context/context.py`

The `auto_context()` method should try loading from the v1 prompt file as the default (instead of the inline string), while still respecting the `HARMONIA_CODE_CONTEXT_PROMPT` env var override.

**Replace the `auto_context()` method (lines 41-93) with:**

```python
async def auto_context(self):
    """
    Provide the system prompt for the LLM.

    Priority:
    1. HARMONIA_CODE_CONTEXT_PROMPT env var (custom file path)
    2. Built-in v1 prompt file (src/code_context/prompts/v1/system.txt)
    3. Hardcoded fallback (should never be needed)
    """
    custom_prompt_path = os.environ.get("HARMONIA_CODE_CONTEXT_PROMPT")
    if custom_prompt_path and Path(custom_prompt_path).exists():
        prompt = Path(custom_prompt_path).read_text()
        source = f"custom file: {custom_prompt_path}"
    else:
        # Load from built-in v1 prompt file
        default_prompt_file = Path(__file__).parent / "prompts" / "v1" / "system.txt"
        if default_prompt_file.exists():
            prompt = default_prompt_file.read_text()
            source = f"built-in: {default_prompt_file}"
        else:
            # Hardcoded fallback (should never be reached)
            prompt = (
                "You are a Python code execution assistant running in a "
                "Jupyter-like environment.\n\n"
                "You can write and execute Python code. Common data science "
                "libraries are available (pandas, numpy, etc.).\n\n"
                "When asked to do something, write Python code to accomplish it."
            )
            source = "hardcoded fallback"

    if not hasattr(self, '_auto_context_logged'):
        print(f"\n{'=' * 80}")
        print(f"AUTO-CONTEXT (domain prompt) -- code_context [{len(prompt)} chars]:")
        print(f"[source: {source}]")
        print(f"{'=' * 80}")
        print(prompt)
        print(f"{'=' * 80}\n")
        self._auto_context_logged = True

    return prompt
```

---

### Step 13: Update `codeact_context/context.py` to use prompt files as defaults

**File:** `src/codeact_context/context.py`

Same pattern — load from v1 files as default, with env var override.

**Replace the `auto_context()` method (lines 77-121) with:**

```python
async def auto_context(self):
    """
    Provide the system prompt for the LLM.

    Priority:
    1. HARMONIA_CODEACT_PROMPT env var
    2. HARMONIA_CODE_CONTEXT_PROMPT env var (backwards compatibility)
    3. Built-in v1 prompt file (src/codeact_context/prompts/v1/system.txt)
    4. Hardcoded fallback
    """
    custom_prompt_path = (
        os.environ.get("HARMONIA_CODEACT_PROMPT")
        or os.environ.get("HARMONIA_CODE_CONTEXT_PROMPT")
    )
    if custom_prompt_path and Path(custom_prompt_path).exists():
        prompt = Path(custom_prompt_path).read_text()
        source = f"custom file: {custom_prompt_path}"
    else:
        default_prompt_file = Path(__file__).parent / "prompts" / "v1" / "system.txt"
        if default_prompt_file.exists():
            prompt = default_prompt_file.read_text()
            source = f"built-in: {default_prompt_file}"
        else:
            prompt = (
                "You are a data scientist working in a Python environment with a "
                "persistent Jupyter kernel.\n\n"
                "You have access to pandas, numpy, and other data science libraries.\n\n"
                "When you need to do something, write Python code in a ```python code block.\n"
                "I will execute it and show you the output. You can then write more code "
                "based on the results.\n\n"
                "When you are done with the task and want to give a final answer, just "
                "respond with text (no code block).\n\n"
                "Important:\n"
                "- Variables persist between code blocks (this is a persistent kernel session)\n"
                "- Use print() to see output — bare expressions do not display\n"
                "- If you get an error, read the traceback and fix your code\n"
                "- Working directory: use os.getcwd() and os.listdir() to explore"
            )
            source = "hardcoded fallback"

    # Update the agent loop's system prompt
    self.codeact_loop.system_prompt = prompt

    if not hasattr(self, '_auto_context_logged'):
        print(f"\n{'=' * 80}")
        print(f"AUTO-CONTEXT (domain prompt) -- codeact_context [{len(prompt)} chars]:")
        print(f"[source: {source}]")
        print(f"{'=' * 80}")
        print(prompt)
        print(f"{'=' * 80}\n")
        self._auto_context_logged = True

    return prompt
```

Also update the summary template loading in `__init__()` (lines 57-60) to use the v1 file as default:

**Current:**
```python
# Load custom summary template if configured
summary_template = None
summary_template_path = os.environ.get("HARMONIA_CODEACT_SUMMARY_TEMPLATE")
if summary_template_path and Path(summary_template_path).exists():
    summary_template = Path(summary_template_path).read_text()
```

**Replace with:**
```python
# Load summary template: env var override, then built-in v1 file, then code default
summary_template = None
summary_template_path = os.environ.get("HARMONIA_CODEACT_SUMMARY_TEMPLATE")
if summary_template_path and Path(summary_template_path).exists():
    summary_template = Path(summary_template_path).read_text()
else:
    default_summary_file = Path(__file__).parent / "prompts" / "v1" / "summary_template.txt"
    if default_summary_file.exists():
        summary_template = default_summary_file.read_text()
```

---

### Step 14: Update experiment YAML configs to point to prompt versions

For configs that use the bdikit_context (the main Harmonia agent), the prompts are already controlled via `HARMONIA_PROMPTS_DIR` and `HARMONIA_TOOL_PROMPTS_DIR`.

For configs that use code_context or codeact_context, add prompt paths to the `prompts:` section. Example for a CodeAct config:

**File:** `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_codeact_devstral.yaml`

Add to the `prompts:` section (create it if it doesn't exist):
```yaml
prompts:
  codeact_prompt: ../../../../../../src/codeact_context/prompts/v1/system.txt
  codeact_summary_template: ../../../../../../src/codeact_context/prompts/v1/summary_template.txt
```

Or use absolute paths:
```yaml
prompts:
  codeact_prompt: /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/src/codeact_context/prompts/v1/system.txt
  codeact_summary_template: /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/src/codeact_context/prompts/v1/summary_template.txt
```

**Note:** This step is optional for now since the contexts fall back to the built-in v1 files by default. But for experiments that want explicit prompt versioning, the config should specify the path. Future prompt versions (v2, v3...) will require updating the config path.

---

## 4. Complete Summary of All Changes

### New files to create
| File | Content |
|---|---|
| `src/bdikit_context/procedures/python3/rank_schema_matches.py` | Procedure template calling `bdi.rank_schema_matches()` |
| `src/bdikit_context/prompts/tools/rank_schema_matches.j2` | Tool description for rank_schema_matches |
| `src/code_context/prompts/v1/system.txt` | Extracted default system prompt for Code Context |
| `src/codeact_context/prompts/v1/system.txt` | Extracted default system prompt for CodeAct Context |
| `src/codeact_context/prompts/v1/summary_template.txt` | Extracted default summary template for CodeAct |

### Files to delete
| File | Reason |
|---|---|
| `src/bdikit_context/procedures/python3/top_matches.py` | Renamed to `rank_schema_matches.py` |
| `src/bdikit_context/prompts/tools/top_matches.j2` | Renamed to `rank_schema_matches.j2` |

### Files to modify
| File | Changes |
|---|---|
| `src/bdikit_context/agent.py` | Rename `top_matches` -> `rank_schema_matches`; update params; rename `get_gdc_acceptable_values` param `column` -> `attribute` |
| `src/bdikit_context/procedures/python3/get_gdc_acceptable_values.py` | `column=` -> `attribute=` |
| `src/bdikit_context/prompts/tools/match_schema.j2` | Add method descriptions |
| `src/bdikit_context/prompts/tools/match_values.j2` | Add method descriptions, fix wording |
| `src/bdikit_context/prompts/tools/get_gdc_acceptable_values.j2` | Update wording |
| `src/bdikit_context/prompts/system/main.j2` | `top_matches` -> `rank_schema_matches` |
| `src/bdikit_context/context.py` | Update tools list in `auto_context()` |
| `src/code_context/context.py` | Load from prompt file with env var override |
| `src/codeact_context/context.py` | Load from prompt files with env var override |

---

## 5. How Prompt Versioning Works After This Change

### For bdikit_context:
- Default prompts: `src/bdikit_context/prompts/` (system/main.j2, tools/*.j2)
- Custom override: set `HARMONIA_PROMPTS_DIR`, `HARMONIA_TOOL_PROMPTS_DIR` in config YAML
- To create a new version: copy the prompts directory, modify, point config at new path

### For code_context:
- Default prompt: `src/code_context/prompts/v1/system.txt`
- Custom override: set `HARMONIA_CODE_CONTEXT_PROMPT` in config YAML
- To create v2: create `src/code_context/prompts/v2/system.txt`, point config at it

### For codeact_context:
- Default prompt: `src/codeact_context/prompts/v1/system.txt`
- Default summary: `src/codeact_context/prompts/v1/summary_template.txt`
- Custom overrides: `HARMONIA_CODEACT_PROMPT`, `HARMONIA_CODEACT_SUMMARY_TEMPLATE`
- To create v2: create `src/codeact_context/prompts/v2/` with both files

### In experiment YAML config:
```yaml
prompts:
  # bdikit_context prompts (Jinja2 templates)
  prompts_base_dir: ../../../src/bdikit_context/prompts
  system_prompt_dir: system
  tool_prompts_dir: tools

  # code_context prompt (plain text file)
  code_context_prompt: ../../../src/code_context/prompts/v1/system.txt

  # codeact_context prompts (plain text files)
  codeact_prompt: ../../../src/codeact_context/prompts/v1/system.txt
  codeact_summary_template: ../../../src/codeact_context/prompts/v1/summary_template.txt
```

---

## 6. Testing

1. **Verify agent tool names:** Start a container, check that `rank_schema_matches` appears in the LLM's tool list (not `top_matches`)
2. **Verify procedure execution:** Call `rank_schema_matches` via the agent and verify `bdi.rank_schema_matches()` is called
3. **Verify `get_gdc_acceptable_values`:** Call it and verify `bdi.preview_domain("gdc", attribute=...)` works
4. **Verify prompt loading for code_context:** Start with and without `HARMONIA_CODE_CONTEXT_PROMPT` env var
5. **Verify prompt loading for codeact_context:** Start with and without `HARMONIA_CODEACT_PROMPT` env var
6. **Verify prompt logging:** Check that `full_prompt_composition.json` correctly captures the loaded prompts and their source paths

---

## 7. Relationship to Other Plans

This plan should be executed **alongside** the bdi-kit v0.9 upgrade plan. The container rebuild at the end of that plan will include all changes from this plan as well (since the source files are copied into the container at build time via the `%files` section of the `.def` file).

The `generate_env.py` changes for `codeact_summary_template` handling have already been implemented (visible in the current file). No additional `generate_env.py` changes are needed from this plan.
