# Plan: LLM Model Registry Integration for Config Generation & Visualization

## Context

Currently, Harmonia experiment configs are created manually or via `manage_configs.py clone` with hardcoded model names. There is no centralized source of truth for available models, their capabilities, or pricing. The visualization pipeline has no cost data, making cost-performance tradeoff analysis impossible. This plan adds:

1. Automated model registry fetching (OpenRouter + Ollama)
2. Pricing/metadata enrichment in config YAMLs
3. Flexible grouping and cost-aware visualization
4. A standalone lookup tool for Claude to wire model info into config generation

---

## Step 1: `fetch_openrouter_models.py` CLI

**New file:** `LLM_associated_metadata/fetch_openrouter_models.py`

**Behavior:**
- `GET https://openrouter.ai/api/v1/models` (unauthenticated first, fallback to `OPENROUTER_API_KEY` from env or `.env`)
- Save full JSON response to `LLM_associated_metadata/openrouter_models.json`
- By default, skip fetch if file exists and is < 24 hours old
- `--force` flag to overwrite regardless of age
- `--max-age HOURS` to customize staleness threshold (default 24)
- Print summary: number of models fetched, file size, timestamp

**Output format:** Raw JSON from API (preserves all fields: `id`, `name`, `pricing.prompt`, `pricing.completion`, `context_length`, `architecture`, `supported_parameters`, `top_provider`, `per_request_limits`, etc.)

**Fields we care about most** (for config generation and visualization):
- `id` (e.g., `anthropic/claude-sonnet-4.6`) — maps to `llm.model`
- `context_length` — maps to `context_management.archytas.context_window_override`
- `pricing.prompt` — cost per token (input)
- `pricing.completion` — cost per token (output)
- `architecture.tokenizer` — model family group (Claude, Gemini, DeepSeek, etc.)
- `architecture.input_modalities` / `output_modalities`
- `supported_parameters` — whether model supports `tools`, `structured_outputs`, etc.
- `top_provider.max_completion_tokens`

---

## Step 2: `fetch_ollama_models.py` CLI

**New file:** `LLM_associated_metadata/fetch_ollama_models.py`

**Behavior — two-phase HTML scraping:**

**Phase 1: Get all model names**
```
curl -s https://ollama.com/library | grep -oP 'href="/library/\K[^"]+'
```
Returns ~214 model names.

**Phase 2: For each model, scrape the model page for metadata**
From `https://ollama.com/library/<model>`, extract the mobile-view summary lines:
```
<tag>: <size> · <context> context window · <modalities> · <age>
```
Regex: `href="/library/(<model>:[^"]+)" class="sm:hidden"` paired with `([\d.]+GB|-) · (\d+K) context window · ([^·]+)·`

This gives us per-tag: **tag name, download size, context window length, input modalities**.

Parse parameter count from tag names (e.g., `24b` from `qwen3.5:24b`, `671b` from `deepseek-v3.1:671b`).

**Caching:** Same staleness logic as OpenRouter — skip if < 24h old, `--force` to override.

**Output:** `LLM_associated_metadata/ollama_models.json` with structure:
```json
{
  "fetched_at": "2026-03-03T13:00:00Z",
  "models": {
    "qwen3.5": {
      "tags": [
        {
          "tag": "qwen3.5:9b",
          "size_gb": 6.6,
          "context_k": 256,
          "modalities": ["Text", "Image"],
          "parameter_count_b": 9.0,
          "quantization": null
        },
        {
          "tag": "qwen3.5:9b-q4_K_M",
          "size_gb": 5.1,
          "context_k": 256,
          "modalities": ["Text", "Image"],
          "parameter_count_b": 9.0,
          "quantization": "q4_K_M"
        }
      ]
    }
  }
}
```

**Rate limiting:** Add a small delay between model page fetches (0.5s) to be polite. Add `--models <name1,name2>` flag to fetch only specific models (for faster targeted lookups). Add `--skip-tags` to only get the main page metadata (faster, no quantization variants).

**Note:** Ollama models have no pricing (local/free). The `pricing_prompt_per_million_tokens` and `pricing_completion_per_million_tokens` fields in config YAML will be `0.0` for Ollama models.

---

## Step 3: Add `model_metadata` section to config YAML schema

**Files to modify:**
- `src/automation/config.py` — add `ModelMetadataConfig` dataclass + field on `ExperimentConfig`
- `generate_env.py` — pass metadata through to `.env` if needed (optional)
- `manage_configs.py` — `clone` command populates `model_metadata` from registry

**New dataclass in `config.py`:**
```python
@dataclass
class ModelMetadataConfig:
    """Model metadata from registry, attached at config generation time."""
    pricing_prompt_per_million_tokens: float = 0.0
    pricing_completion_per_million_tokens: float = 0.0
    context_length: Optional[int] = None
    parameter_count_b: Optional[float] = None
    model_family_group: Optional[str] = None  # "Claude", "Gemini", "DeepSeek", "Llama3", etc.
    modalities: Optional[list[str]] = None
    supports_tools: Optional[bool] = None
    supports_structured_output: Optional[bool] = None
    source: Optional[str] = None  # "openrouter" or "ollama"
```

**New field on `ExperimentConfig`:**
```python
model_metadata: ModelMetadataConfig = field(default_factory=ModelMetadataConfig)
```

**Config YAML example after generation:**
```yaml
llm:
  provider: openrouter
  model: anthropic/claude-sonnet-4.6
  temperature: 0.0

model_metadata:
  pricing_prompt_per_million_tokens: 3.00
  pricing_completion_per_million_tokens: 15.00
  context_length: 200000
  parameter_count_b: null
  model_family_group: Claude
  modalities: [text, image]
  supports_tools: true
  supports_structured_output: true
  source: openrouter
```

---

## Step 4: Wire registry into `manage_configs.py clone`

**File:** `manage_configs.py`

When `clone` creates a new config with `--model` and `--provider`:
1. Load the appropriate registry file (`openrouter_models.json` or `ollama_models.json`) from `LLM_associated_metadata/`
2. Look up the model by ID
3. Auto-populate `model_metadata:` section
4. Auto-set `context_management.archytas.context_window_override` from registry `context_length` (if not explicitly overridden)
5. If registry file is missing or stale, print a warning suggesting to run the fetch CLI

This is a best-effort enrichment — if the model isn't found in the registry, `model_metadata` gets defaults and a warning is printed.

---

## Step 5: Flow pricing into metrics and visualization

### 5a. Propagate metadata through `.experiment_id` and `metrics.json`

**Files to modify:**
- `src/evaluation/schemas.py` — extend `ExperimentMetadata` with pricing fields
- `src/evaluation/normalize.py` — read `model_metadata` from config YAML or `.experiment_id`, populate new columns in `_run_row()`

**New fields on `ExperimentMetadata`:**
```python
pricing_prompt_per_million_tokens: Optional[float] = None
pricing_completion_per_million_tokens: Optional[float] = None
parameter_count_b: Optional[float] = None
model_family_group: Optional[str] = None
supports_tools: Optional[bool] = None
```

**In `_run_row()` (normalize.py):** add these fields to the row dict, reading from:
1. `.experiment_id` JSON (if enriched at experiment start time)
2. The config YAML in the results dir (if available)
3. Fallback: look up from the registry file directly

### 5b. Flexible grouping in visualization

**Files to modify:**
- `visualize_metrics_cli.py` — add `--group-by`, `--hue`, `--cost-bin-edges` flags
- `src/evaluation/aggregate.py` — add cost binning function
- `src/evaluation/normalize.py` — add cost tier column derivation
- `src/evaluation/plots.py` — add `plot_boxplot()` function

**New columns derived in `_run_row()` or post-processing:**
- `cost_tier` — categorical, derived from `pricing_prompt_per_million_tokens` using configurable bin edges (e.g., `[0, 0.001, 0.5, 5.0, inf]` → `free`, `cheap`, `moderate`, `expensive`)
- `is_local` — boolean (`pricing == 0` or `provider == ollama`)

**New CLI capabilities across subcommands (`bars`, `heatmap`, `compare`):**
- `--group-by <column>` — replaces the default `display_label` grouping. Can be: `model_label`, `context`, `model_family`, `model_family_group`, `cost_tier`, `is_local`, or any column in the runs DataFrame
- `--hue <column>` — color sub-grouping (already partially supported, generalize it)
- `--cost-bin-edges 0,0.5,5,999` — define custom cost tier boundaries
- `--sort-by <column>` — sort bars/rows by a metric or metadata column

**New subcommand: `boxplot`**
```bash
visualize_metrics_cli.py boxplot \
  --metrics-files results/*/metrics.json \
  --metric avg_value_accuracy_excl_empty \
  --group-by model_family_group \
  --hue is_local
```
Collapses all runs per group into a box-and-whisker plot. Useful for comparing "local vs frontier" or "cost tier" distributions.

**Enhanced `heatmap` default:** When `--group-by` is not specified, the heatmap shows one row per run (as today). When `--group-by model_label` is used, it averages over contexts/repeats. A new `--annotate-rows` flag adds columns to the row labels showing pricing, context_length, etc.

**Enhanced `compare` subcommand:** Generates the full default suite:
1. Heatmap: model (averaged over contexts) vs columns, with pricing/local annotations
2. Bar plots: for each metric, grouped by model, hued by context
3. Box plots: by `model_family_group`, by `is_local`, by `cost_tier`
4. All combinations exported as PNG + CSV

---

## Step 6: `lookup_model.py` — standalone tool for Claude

**New file:** `LLM_associated_metadata/lookup_model.py`

**Purpose:** Claude calls this to look up model information from registries when generating configs.

**Interface:**
```bash
# Search by name (fuzzy)
.venv/bin/python LLM_associated_metadata/lookup_model.py search "claude sonnet"

# Get full details for a specific model
.venv/bin/python LLM_associated_metadata/lookup_model.py details openrouter:anthropic/claude-sonnet-4.6

# List all models from a provider
.venv/bin/python LLM_associated_metadata/lookup_model.py list --source openrouter --filter-text-only

# Output config-ready YAML snippet
.venv/bin/python LLM_associated_metadata/lookup_model.py config-snippet openrouter:anthropic/claude-sonnet-4.6
```

The `config-snippet` subcommand outputs a YAML block that can be directly pasted into a config file:
```yaml
llm:
  provider: openrouter
  model: anthropic/claude-sonnet-4.6
  temperature: 0.0
model_metadata:
  pricing_prompt_per_million_tokens: 3.00
  pricing_completion_per_million_tokens: 15.00
  context_length: 200000
  model_family_group: Claude
  ...
context_management:
  archytas:
    context_window_override: 200000
```

---

## Step 7: Update CLAUDE.md

**File:** `.claude/CLAUDE.md` (project-level)

Add a section:

```markdown
## Model Registry Management

Before generating configs for OpenRouter models, check if the registry is current:
\`\`\`bash
# Check age of registry file
find LLM_associated_metadata/openrouter_models.json -mmin +1440 2>/dev/null && echo "STALE" || echo "FRESH"
# If stale or missing:
.venv/bin/python LLM_associated_metadata/fetch_openrouter_models.py
\`\`\`

For Ollama models:
\`\`\`bash
find LLM_associated_metadata/ollama_models.json -mmin +1440 2>/dev/null && echo "STALE" || echo "FRESH"
# If stale or missing:
.venv/bin/python LLM_associated_metadata/fetch_ollama_models.py
\`\`\`

When creating configs for specific models, use lookup_model.py to get accurate metadata:
\`\`\`bash
.venv/bin/python LLM_associated_metadata/lookup_model.py config-snippet openrouter:<model-id>
\`\`\`
```

---

## Step 8: Update codebase description

Per CLAUDE.md instructions, update `docs/codebase_descriptions/how_this_codebase_works_*.md` with the new registry system, `model_metadata` config section, and visualization changes.

---

## Implementation Order

1. **Step 1** — `fetch_openrouter_models.py` (standalone, no dependencies)
2. **Step 2** — `fetch_ollama_models.py` (standalone, no dependencies)
3. **Step 3** — `ModelMetadataConfig` dataclass in `config.py`
4. **Step 4** — Wire registry into `manage_configs.py clone`
5. **Step 5a** — Propagate metadata into schemas/normalize
6. **Step 6** — `lookup_model.py` (depends on Steps 1-2 for data)
7. **Step 5b** — Visualization enhancements (depends on Step 5a)
8. **Step 7** — CLAUDE.md update
9. **Step 8** — Codebase description update

Steps 1 and 2 can be done in parallel. Steps 3-4 are sequential. Step 6 can be done after 1-2.

---

## Files to Create
| File | Purpose |
|------|---------|
| `LLM_associated_metadata/fetch_openrouter_models.py` | OpenRouter registry fetcher CLI |
| `LLM_associated_metadata/fetch_ollama_models.py` | Ollama registry fetcher CLI |
| `LLM_associated_metadata/lookup_model.py` | Model lookup tool for Claude |

## Files to Modify
| File | Change |
|------|--------|
| `src/automation/config.py` | Add `ModelMetadataConfig` dataclass + field |
| `src/evaluation/schemas.py` | Add pricing fields to `ExperimentMetadata` |
| `src/evaluation/normalize.py` | Read model_metadata, add cost columns to `_run_row()` |
| `src/evaluation/enrich.py` | Add cost tier derivation function |
| `src/evaluation/aggregate.py` | Add cost binning, generalize grouping |
| `src/evaluation/plots.py` | Add `plot_boxplot()` |
| `src/evaluation/visualize_metrics_cli.py` | Add `--group-by`, `--hue`, `--cost-bin-edges`, `--sort-by`, `boxplot` subcommand |
| `manage_configs.py` | Enrich `clone` with registry lookup |
| `generate_env.py` | Optionally pass model_metadata to .env |
| `.claude/CLAUDE.md` | Add registry management instructions |

---

## Verification

1. **Fetch CLIs:** Run both fetch scripts, verify JSON files are created in `LLM_associated_metadata/` with expected structure
2. **Staleness check:** Run fetch again immediately — should skip. Run with `--force` — should re-fetch
3. **Config generation:** `manage_configs.py clone --model anthropic/claude-sonnet-4.6 --provider openrouter` should auto-populate `model_metadata:` section
4. **Lookup tool:** `lookup_model.py search "claude"` should return matching models with pricing
5. **Visualization:** Run `visualize_metrics_cli.py bars --group-by model_family_group --hue is_local` on existing results — should group correctly (existing runs without pricing get `0.0`/`null` defaults)
6. **Backward compatibility:** Existing configs without `model_metadata:` should load fine (defaults to empty `ModelMetadataConfig`)
