# Implementing Both Tool-Calling and Non-Tool-Calling Experiments

**Date:** 15-01-2026
**Purpose:** Document approaches for supporting LLMs that do not have native function/tool calling capabilities

## Background

The current Harmonia automation framework uses **Archytas ReAct agent** within **Beaker kernel**. This architecture relies on LLM tool/function calling to:
1. Invoke BDI-Kit functions (match_schema, match_values, etc.)
2. Execute Python code in the subkernel
3. Parse structured responses from tool results

**Problem:** Some LLMs do not support native function/tool calling:
- `olmo-3:latest` (NO tool support - use `olmo-3.1:32b` instead)
- Some free-tier OpenRouter models
- Older or smaller models

## Models with Confirmed Tool Support

Based on Ollama library verification:

| Model | Size | Tool Support | Notes |
|-------|------|--------------|-------|
| devstral:latest | 123B | ✅ Yes | Full tool support |
| devstral-small-2:latest | 24B | ✅ Yes | Full tool support |
| olmo-3.1:32b | 32B | ✅ Yes | Use this, NOT olmo-3 |
| olmo-3:latest | 32B | ❌ No | Does NOT support tools |
| qwen3-coder:30b | 30B | ✅ Yes | Full tool support |
| nemotron-3-nano:30b | 30B | ✅ Yes | MoE model with tool support |
| llama3.1:8b/70b | 8-70B | ✅ Yes | Full tool support |
| mistral:7b | 7B | ✅ Yes | Full tool support |

## Alternative Approaches for Non-Tool-Calling Models

---

### Alternative 2: Prompt-Based Tool Simulation

**Approach:** Use structured prompts that instruct the LLM to output JSON/code in a specific format, then parse and execute.

**Implementation:**
```python
TOOL_SIMULATION_PROMPT = """
You are a data harmonization assistant. When you need to perform an action,
output it in this exact format:

ACTION: <tool_name>
PARAMS:
  - dataset: <value>
  - target: <value>
  - method: <value>
END_ACTION

Available tools:
- match_schema: Maps columns to GDC schema
- match_values: Maps values between columns
- materialize_mapping: Creates final harmonized table

After I execute your action, I'll provide the result, then you can continue.
"""

class PromptSimulatedAgent:
    def parse_action(self, response: str) -> dict:
        """Parse ACTION blocks from LLM response."""
        match = re.search(r'ACTION:\s*(\w+)\nPARAMS:\n(.*?)\nEND_ACTION', response, re.DOTALL)
        if match:
            tool_name = match.group(1)
            params = yaml.safe_load(match.group(2))
            return {"tool": tool_name, "params": params}
        return None
```

**Pros:**
- Works with any text-generating LLM
- Preserves conversational nature
- Can use existing conversation flows

**Cons:**
- Requires robust parsing (LLMs may deviate from format)
- More error-prone than native tools
- Additional prompt engineering needed

---

### Alternative 3: Two-Stage Pipeline (LLM Planning + Code Execution)

**Approach:** Use LLM for high-level planning only, then execute pre-written code based on the plan.

**Implementation:**
```python
PLANNING_PROMPT = """
Given this dataset with columns: {columns}
And this task: {task}

Output a JSON plan with these steps:
1. Which columns to subset
2. Which mapping method to use
3. Which columns need value mapping

Format:
{
  "subset_columns": ["col1", "col2"],
  "schema_method": "ct_learning",
  "value_mapping_columns": ["col1"]
}
"""

class TwoStagePipeline:
    async def run(self, task: str):
        # Stage 1: Get plan from LLM
        plan = await self.get_plan_from_llm(task)

        # Stage 2: Execute deterministic code
        result = await self.execute_plan(plan)
        return result
```

**Pros:**
- LLM only does what it's good at (reasoning)
- Deterministic execution
- Easier to debug

**Cons:**
- Less flexible than full agent
- Plan parsing can fail
- Limited iterative refinement

---

### Alternative 4: ReAct-Style Text Parsing (Archytas Fallback)

**Approach:** Use Archytas with `force_text_output=True` to get text-based reasoning, then parse tool calls manually.

**Implementation:**
```python
from archytas.agent import Agent

class TextReActAgent(Agent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.force_text_output = True  # Disable native tool calling

    def parse_react_output(self, text: str):
        """Parse Thought/Action/Action Input from text output."""
        # Look for patterns like:
        # Thought: I need to match the schema
        # Action: match_schema
        # Action Input: {"dataset": "df", "target": "gdc"}
        pass
```

**Pros:**
- Uses existing Archytas infrastructure
- Compatible with ReAct prompting
- Works with text-only models

**Cons:**
- Requires parsing free-form text
- Less reliable than native tools
- May need model-specific tuning

---

### Alternative 5: Hybrid Mode with Graceful Degradation

**Approach:** Try native tool calling first, fall back to text parsing if tools aren't supported.

**Implementation:**
```python
class HybridRunner(ExperimentRunner):
    async def send_llm_request(self, message: str):
        try:
            # Try with tools first
            response = await self.client.send_llm_request(message)
            if "does not support tools" in str(response.get("error", "")):
                raise ToolNotSupportedError()
            return response
        except ToolNotSupportedError:
            # Fall back to text-based approach
            logger.warning("Model doesn't support tools, using text mode")
            return await self.send_text_request(message)

    async def send_text_request(self, message: str):
        """Send request with tool simulation prompt."""
        augmented_message = TOOL_SIMULATION_PROMPT + "\n\n" + message
        return await self.client.send_llm_request_no_tools(augmented_message)
```

**Config Extension:**
```yaml
llm:
  provider: ollama
  model: olmo-3:latest
  tool_mode: auto  # NEW: auto, native, text, code_only
  fallback_mode: text  # What to do if native tools fail
```

**Pros:**
- Maximum compatibility
- Automatic detection
- Single config for all models

**Cons:**
- More complex implementation
- Need to maintain two code paths
- Testing complexity increases

---

## Recommendation

For the current project, **prioritize using models with native tool support**:

1. **Switch olmo-3:latest → olmo-3.1:32b** (has tool support)
2. **Use devstral models** which have confirmed tool support
3. **Avoid free-tier OpenRouter models** without checking tool support first

If non-tool-calling models must be supported:
- Start with **Alternative 5 (Hybrid Mode)** for flexibility
- Use **Alternative 1 (Code-Only)** for deterministic baselines
- Consider **Alternative 2 (Prompt Simulation)** for research comparisons

## Implementation Priority

1. **Immediate:** Update configs to use only tool-supporting models
2. **Short-term:** Add tool support detection and clear error messages
3. **Medium-term:** Implement hybrid mode for broader model compatibility
4. **Long-term:** Build full prompt-simulation layer for research purposes
