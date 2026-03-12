"""
Prompt composition logging for Harmonia.

Two capabilities:
1. print_prompt_composition() — prints full prompt layers to stdout for SLURM log inspection
2. register_prompt_json_logger() — one-shot monkey-patch on agent.execute() that writes
   structured JSON to the results directory on the first LLM call

See docs/plans/11_06_2025_1715_make_logging_full_prompt_in_container.md for design.
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ============================================================
# OUTPUT A: Stdout printing for visual inspection (sync)
# ============================================================

def print_prompt_composition(agent, context_slug: str) -> None:
    """
    Print the prompt layers available at init time to stdout.

    Call this from Context.__init__() AFTER super().__init__() and all prompt
    overrides (custom prelude, tool description overrides) have been applied.

    This captures at init time:
    - Layer 1: System message (ReAct prelude + model instructions + tool descriptions)
    - Model-specific prompt instructions
    - Custom prelude (if any)
    - Prompt configuration env vars

    The auto-context (domain prompt) is NOT available at init time because
    auto_context()'s content_updater hasn't fired yet. That layer is printed
    on first auto_context() call separately.

    Args:
        agent: The BeakerAgent/BDIKitAgent instance
        context_slug: "bdikit_context" or "code_context"
    """
    separator = "=" * 80
    subsep = "-" * 40

    print(f"\n{separator}")
    print(f"PROMPT COMPOSITION — {context_slug}")
    print(f"Model class: {agent.model.__class__.__name__}")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print(separator)

    # Layer 1: System message (ReAct prelude + model instructions + tool descriptions)
    system_msg = agent.chat_history.system_message
    if system_msg:
        content = system_msg.message.content if hasattr(system_msg, 'message') else str(system_msg)
        print(f"\n{subsep}")
        print("LAYER 1: SYSTEM MESSAGE (ReAct prelude + model instructions)")
        print(subsep)
        print(content)
        print(f"[{len(content)} chars]")

    # Model-specific prompt instructions
    model_instructions = getattr(agent.model, 'MODEL_PROMPT_INSTRUCTIONS', '')
    print(f"\n{subsep}")
    print("MODEL-SPECIFIC PROMPT INSTRUCTIONS")
    print(subsep)
    if model_instructions.strip():
        print(model_instructions)
        print(f"[{len(model_instructions)} chars]")
    else:
        print("(none — empty for this model class)")

    # Custom prelude
    custom_prelude = getattr(agent, 'custom_prelude', None)
    if custom_prelude:
        print(f"\n{subsep}")
        print("CUSTOM PRELUDE (overrides default ReAct prelude)")
        print(subsep)
        print(custom_prelude)
        print(f"[{len(custom_prelude)} chars]")

    # Prompt configuration env vars
    prompt_env_vars = {
        "HARMONIA_PROMPTS_DIR": os.environ.get("HARMONIA_PROMPTS_DIR"),
        "HARMONIA_REACT_PRELUDE": os.environ.get("HARMONIA_REACT_PRELUDE"),
        "HARMONIA_TOOL_PROMPTS_DIR": os.environ.get("HARMONIA_TOOL_PROMPTS_DIR"),
        "HARMONIA_CODE_CONTEXT_PROMPT": os.environ.get("HARMONIA_CODE_CONTEXT_PROMPT"),
        "HARMONIA_RUN_ID": os.environ.get("HARMONIA_RUN_ID"),
        "HARMONIA_EXPERIMENT_NAME": os.environ.get("HARMONIA_EXPERIMENT_NAME"),
        "HARMONIA_LLM_FOR_INSTANCE_MATCHING": os.environ.get("HARMONIA_LLM_FOR_INSTANCE_MATCHING"),
        "HARMONIA_LLM_FOR_NUMERIC_INSTANCE_MATCHING": os.environ.get("HARMONIA_LLM_FOR_NUMERIC_INSTANCE_MATCHING"),
        "HARMONIA_EMBEDDING_MODEL_FOR_INSTANCE_MATCHING": os.environ.get("HARMONIA_EMBEDDING_MODEL_FOR_INSTANCE_MATCHING"),
        "HARMONIA_LLM_FOR_SCHEMA_MATCHING": os.environ.get("HARMONIA_LLM_FOR_SCHEMA_MATCHING"),
        "HARMONIA_LLM_FOR_MAGNETO_ZERO_SHOT_SCHEMA_MATCHING": os.environ.get("HARMONIA_LLM_FOR_MAGNETO_ZERO_SHOT_SCHEMA_MATCHING"),
        "HARMONIA_LLM_FOR_MAGNETO_FINE_TUNED_SCHEMA_MATCHING": os.environ.get("HARMONIA_LLM_FOR_MAGNETO_FINE_TUNED_SCHEMA_MATCHING"),
    }
    active_vars = {k: v for k, v in prompt_env_vars.items() if v is not None}
    print(f"\n{subsep}")
    print("PROMPT CONFIGURATION ENV VARS")
    print(subsep)
    if active_vars:
        print(json.dumps(active_vars, indent=2))
    else:
        print("(none set — using all defaults)")

    # Note about auto-context
    print(f"\n{subsep}")
    print("NOTE: Auto-context (domain prompt) will be printed on first auto_context() call.")
    print(f"{separator}\n")


# ============================================================
# OUTPUT B: Structured JSON logging for systematic comparison
# ============================================================

def _content_hash(text: str) -> str:
    """SHA-256 hash of content for comparison across runs."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def build_prompt_composition_log(
    messages: list,
    model_class_name: str,
    model_prompt_instructions: str,
    custom_prelude: Optional[str],
    experiment_name: str,
    run_id: str,
    context_slug: str,
) -> dict:
    """
    Build a structured log of the full prompt composition.

    Args:
        messages: The full list of LangChain BaseMessage objects from ChatHistory.records()
        model_class_name: e.g. "OllamaModel", "AnyLLMModel"
        model_prompt_instructions: The MODEL_PROMPT_INSTRUCTIONS string
        custom_prelude: The custom_prelude if set, else None
        experiment_name: From experiment config
        run_id: 8-char hex run ID
        context_slug: "bdikit_context" or "code_context"

    Returns:
        Dict suitable for JSON serialization
    """
    # Collect prompt env vars for provenance
    prompt_config = {
        "HARMONIA_PROMPTS_DIR": os.environ.get("HARMONIA_PROMPTS_DIR"),
        "HARMONIA_REACT_PRELUDE": os.environ.get("HARMONIA_REACT_PRELUDE"),
        "HARMONIA_TOOL_PROMPTS_DIR": os.environ.get("HARMONIA_TOOL_PROMPTS_DIR"),
        "HARMONIA_CODE_CONTEXT_PROMPT": os.environ.get("HARMONIA_CODE_CONTEXT_PROMPT"),
        "HARMONIA_LLM_FOR_INSTANCE_MATCHING": os.environ.get("HARMONIA_LLM_FOR_INSTANCE_MATCHING"),
        "HARMONIA_LLM_FOR_NUMERIC_INSTANCE_MATCHING": os.environ.get("HARMONIA_LLM_FOR_NUMERIC_INSTANCE_MATCHING"),
        "HARMONIA_EMBEDDING_MODEL_FOR_INSTANCE_MATCHING": os.environ.get("HARMONIA_EMBEDDING_MODEL_FOR_INSTANCE_MATCHING"),
        "HARMONIA_LLM_FOR_SCHEMA_MATCHING": os.environ.get("HARMONIA_LLM_FOR_SCHEMA_MATCHING"),
        "HARMONIA_LLM_FOR_MAGNETO_ZERO_SHOT_SCHEMA_MATCHING": os.environ.get("HARMONIA_LLM_FOR_MAGNETO_ZERO_SHOT_SCHEMA_MATCHING"),
        "HARMONIA_LLM_FOR_MAGNETO_FINE_TUNED_SCHEMA_MATCHING": os.environ.get("HARMONIA_LLM_FOR_MAGNETO_FINE_TUNED_SCHEMA_MATCHING"),
    }

    composition = {
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "experiment_name": experiment_name,
            "context_type": context_slug,
            "model_class": model_class_name,
            "prompt_config": {k: v for k, v in prompt_config.items() if v is not None},
        },
        "layers": {},
        "messages_sent_to_llm": [],
        "summary": {},
    }

    # Decompose messages into layers
    # Message order from ChatHistory.records():
    #   0: system_message (SystemMessage)
    #   1: auto_context_message (HumanMessage with domain prompt)
    #   2+: summaries, user_preamble, raw_records

    for i, msg in enumerate(messages):
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        msg_dict = {
            "type": msg.__class__.__name__,
            "content": content,
            "index": i,
            "content_hash": _content_hash(content),
            "char_count": len(content),
        }
        composition["messages_sent_to_llm"].append(msg_dict)

    # Identify layers by position and type
    if messages:
        system_content = messages[0].content if isinstance(messages[0].content, str) else str(messages[0].content)
        composition["layers"]["system_message"] = {
            "description": "ReAct prelude + model-specific instructions + tool descriptions",
            "content": system_content,
            "content_hash": _content_hash(system_content),
            "char_count": len(system_content),
            "custom_prelude_used": custom_prelude is not None,
            "custom_prelude_hash": _content_hash(custom_prelude) if custom_prelude else None,
        }

    if len(messages) > 1:
        auto_ctx_content = messages[1].content if isinstance(messages[1].content, str) else str(messages[1].content)
        composition["layers"]["auto_context_message"] = {
            "description": "Domain-specific system prompt (BDIKit harmonization or Code execution)",
            "content": auto_ctx_content,
            "content_hash": _content_hash(auto_ctx_content),
            "char_count": len(auto_ctx_content),
        }

    # Model-specific instructions (embedded in system message but logged separately for comparison)
    composition["layers"]["model_prompt_instructions"] = {
        "description": "Model-class-specific prompt additions (e.g., OllamaModel tool message handling)",
        "model_class": model_class_name,
        "content": model_prompt_instructions,
        "content_hash": _content_hash(model_prompt_instructions) if model_prompt_instructions else None,
        "char_count": len(model_prompt_instructions),
        "is_empty": len(model_prompt_instructions.strip()) == 0,
    }

    # Summary stats
    total_chars = sum(len(m.content) if isinstance(m.content, str) else len(str(m.content)) for m in messages)
    composition["summary"] = {
        "total_messages": len(messages),
        "total_char_count": total_chars,
        "layer_count": len(composition["layers"]),
        "has_custom_prelude": custom_prelude is not None,
        "has_model_specific_instructions": len(model_prompt_instructions.strip()) > 0,
        "uses_custom_prompts": any(v is not None for v in prompt_config.values()),
    }

    return composition


def write_prompt_composition_log(
    composition: dict,
    results_dir: Path,
) -> Path:
    """
    Write prompt composition log to results directory.

    Args:
        composition: Output of build_prompt_composition_log()
        results_dir: Path to the experiment results directory

    Returns:
        Path to the written JSON file
    """
    output_path = results_dir / "full_prompt_composition.json"
    output_path.write_text(json.dumps(composition, indent=2, ensure_ascii=False))
    return output_path


def register_prompt_json_logger(agent, context_slug: str) -> None:
    """
    Register a one-shot monkey-patch on Agent.execute() to capture
    prompt composition as structured JSON on the first LLM call.

    After firing once, it unwraps itself so subsequent calls are unaffected.

    Reads results directory from RESULTS_DIR env var (set by exec_apptainer_harmonia.sh
    to /workspace/results inside the container).

    Args:
        agent: The BeakerAgent/BDIKitAgent instance
        context_slug: "bdikit_context" or "code_context"
    """
    results_dir_env = os.environ.get("RESULTS_DIR")
    if not results_dir_env:
        print("[Harmonia] RESULTS_DIR not set — skipping structured prompt JSON logging")
        return

    results_dir = Path(results_dir_env)
    if not results_dir.exists():
        print(f"[Harmonia] RESULTS_DIR={results_dir_env} does not exist — skipping JSON logging")
        return

    original_execute = agent.execute

    async def logging_execute_wrapper(*args, **kwargs):
        """One-shot wrapper: logs prompt composition, then unwraps."""
        # Capture messages the same way execute() does
        try:
            records = await agent.chat_history.records(auto_update_context=True)
            messages = [record.message for record in records]
        except Exception as e:
            print(f"[Harmonia] Warning: Could not capture messages for prompt log: {e}")
            messages = []

        if messages:
            # Get model-specific info
            model_class_name = agent.model.__class__.__name__
            model_prompt_instructions = getattr(agent.model, 'MODEL_PROMPT_INSTRUCTIONS', '')
            custom_prelude = getattr(agent, 'custom_prelude', None)

            # Get run metadata from env vars
            run_id = os.environ.get("HARMONIA_RUN_ID", "unknown")
            experiment_name = os.environ.get("HARMONIA_EXPERIMENT_NAME", "unknown")

            composition = build_prompt_composition_log(
                messages=messages,
                model_class_name=model_class_name,
                model_prompt_instructions=model_prompt_instructions,
                custom_prelude=custom_prelude,
                experiment_name=experiment_name,
                run_id=run_id,
                context_slug=context_slug,
            )

            try:
                output_path = write_prompt_composition_log(composition, results_dir)
                print(f"[Harmonia] Structured prompt composition written to: {output_path}")
            except Exception as e:
                print(f"[Harmonia] Warning: Failed to write prompt composition: {e}")

        # Unwrap — restore original execute for all subsequent calls
        agent.execute = original_execute

        # Call the real execute
        return await original_execute(*args, **kwargs)

    agent.execute = logging_execute_wrapper
    print("[Harmonia] Registered one-shot prompt JSON logger (will fire on first LLM call)")
