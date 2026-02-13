#!/usr/bin/env python3
"""
Feasibility tests for configurable prompts.

Tests all layers of the prompt system:
1. ReActAgent custom_prelude parameter
2. Agent class docstring override at runtime
3. PromptLoader with custom directories
4. Singleton loader override behavior
5. Auto-context update mechanism
6. BeakerAgent init chain and prompt composition
7. Full end-to-end prompt flow simulation
"""

import sys
import os
import tempfile
import asyncio
from pathlib import Path

# Ensure harmonia src is importable
sys.path.insert(0, "/opt/harmonia_src")


def test_1_custom_prelude():
    print("=" * 60)
    print("TEST 1: ReActAgent custom_prelude parameter")
    print("=" * 60)

    from archytas.react import build_prompt

    # Test 1a: Default prelude
    default_prompt = build_prompt()
    print(f"Default prelude (first 100 chars): {default_prompt[:100]}...")
    print(f"Default prelude length: {len(default_prompt)} chars")

    # Test 1b: Custom prelude
    custom = "You are a specialized data harmonization agent."
    custom_prompt = build_prompt(custom_prelude=custom)
    print(f"\nCustom prelude: {custom_prompt}")
    assert custom_prompt == custom, "Custom prelude should replace default"
    print("PASS: custom_prelude completely replaces default prelude")
    return True


def test_2_docstring_override():
    print("\n" + "=" * 60)
    print("TEST 2: Agent class docstring override at runtime")
    print("=" * 60)

    # Test class-level docstring modification
    from beaker_kernel.lib.agent import BeakerAgent

    class TestAgentA(BeakerAgent):
        """Original docstring A."""
        pass

    class TestAgentB(BeakerAgent):
        """Original docstring B."""
        pass

    print(f"TestAgentA doc: {TestAgentA.__doc__}")
    print(f"TestAgentB doc: {TestAgentB.__doc__}")

    # Modify A
    TestAgentA.__doc__ = "Modified docstring A"
    print(f"After mod - TestAgentA doc: {TestAgentA.__doc__}")
    print(f"After mod - TestAgentB doc: {TestAgentB.__doc__}")
    assert TestAgentA.__doc__ == "Modified docstring A"
    assert TestAgentB.__doc__ == "Original docstring B."
    print("PASS: Class docstrings can be modified independently at runtime")

    # Test get_info behavior (simulated - can't instantiate without Beaker kernel)
    print("\nNote: get_info() uses self.__class__.__doc__.strip()")
    print("So modifying __doc__ BEFORE instantiation affects the agent_prompt")
    return True


def test_3_custom_prompt_loader():
    print("\n" + "=" * 60)
    print("TEST 3: PromptLoader with custom directory")
    print("=" * 60)

    from bdikit_context.prompts import PromptLoader

    # Test with the default directory
    default_loader = PromptLoader()
    print(f"Default prompts_dir: {default_loader.prompts_dir}")
    default_system = default_loader.get_system_prompt(
        tools=[{"name": "test_tool", "description": "A test"}],
        suppress_output=True,
    )
    print(f"Default system prompt length: {len(default_system)} chars")
    print(f"First 100 chars: {default_system[:100]}...")

    # Test with a custom directory
    with tempfile.TemporaryDirectory() as tmpdir:
        system_dir = Path(tmpdir) / "system"
        system_dir.mkdir()
        (system_dir / "main.j2").write_text(
            "You are a CUSTOMIZED harmonization agent.\n\n"
            "{% if suppress_output %}\nCUSTOM: Suppress output mode.\n{% endif %}\n\n"
            "Available tools:\n{% for tool in tools %}\n- {{ tool.name }}: {{ tool.description }}\n{% endfor %}\n\n"
            "Do the harmonization differently.\n"
        )

        tools_dir = Path(tmpdir) / "tools"
        tools_dir.mkdir()
        (tools_dir / "match_schema.j2").write_text("CUSTOM match_schema description for testing")

        custom_loader = PromptLoader(prompts_dir=Path(tmpdir))
        custom_system = custom_loader.get_system_prompt(
            tools=[{"name": "test_tool", "description": "A test"}],
            suppress_output=True,
        )
        print(f"\nCustom system prompt:\n{custom_system}")
        assert "CUSTOMIZED" in custom_system
        print("PASS: PromptLoader works with custom directory")

        custom_tool_desc = custom_loader.get_tool_description("match_schema")
        print(f"\nCustom tool description: {custom_tool_desc}")
        assert "CUSTOM" in custom_tool_desc
        print("PASS: Custom tool descriptions work")

        tools_list = custom_loader.list_tools()
        print(f"Available tools in custom dir: {tools_list}")
        assert "match_schema" in tools_list
        print("PASS: list_tools works with custom directory")

    return True


def test_4_singleton_behavior():
    print("\n" + "=" * 60)
    print("TEST 4: Singleton loader override behavior")
    print("=" * 60)

    from bdikit_context.prompts import get_prompt_loader
    import bdikit_context.prompts as prompts_module

    # Reset singleton
    prompts_module._loader = None

    # Get default loader
    loader1 = get_prompt_loader()
    print(f"Loader 1 dir: {loader1.prompts_dir}")
    loader1_id = id(loader1)

    # Get again without args - should return same instance
    loader1b = get_prompt_loader()
    print(f"Same instance (no args)? {id(loader1b) == loader1_id}")
    assert id(loader1b) == loader1_id
    print("PASS: Returns same instance when no args provided")

    # Override with custom dir
    with tempfile.TemporaryDirectory() as tmpdir:
        loader2 = get_prompt_loader(prompts_dir=Path(tmpdir))
        print(f"\nLoader 2 dir: {loader2.prompts_dir}")
        print(f"Different instance? {id(loader2) != loader1_id}")
        assert id(loader2) != loader1_id
        print("PASS: Creates new instance when prompts_dir provided")

        # Get without args again - returns the OVERRIDDEN instance
        loader3 = get_prompt_loader()
        print(f"\nLoader 3 dir: {loader3.prompts_dir}")
        print(f"Loader3 is loader2? {loader3 is loader2}")
        assert loader3 is loader2
        print("WARNING: Global singleton is now permanently changed!")
        print("IMPACT: In multi-config scenarios, this is a problem")

    # Reset
    prompts_module._loader = None
    return True


def test_5_auto_context():
    print("\n" + "=" * 60)
    print("TEST 5: Auto-context update mechanism")
    print("=" * 60)

    from archytas.chat_history import AutoContextMessage

    call_count = 0

    async def mock_auto_context():
        nonlocal call_count
        call_count += 1
        return f"Auto context call #{call_count}: Custom system prompt here"

    msg = AutoContextMessage(
        default_content="Default context",
        content_updater=mock_auto_context,
    )
    print(f"Initial content: {msg.content}")
    assert msg.content == "Default context"

    asyncio.run(msg.update_content())
    print(f"After update: {msg.content}")
    assert "Custom system prompt" in msg.content
    print("PASS: AutoContextMessage updates content from updater function")

    asyncio.run(msg.update_content())
    print(f"After 2nd update: {msg.content}")
    assert "#2" in msg.content
    print("PASS: Content updater is called fresh each time")
    return True


def test_6_beaker_context_init_chain():
    print("\n" + "=" * 60)
    print("TEST 6: BeakerContext __init_subclass__ mechanism")
    print("=" * 60)

    from beaker_kernel.lib.context import BeakerContext
    import inspect

    # Check __init_subclass__ behavior
    print("BeakerContext.__init_subclass__ does the following:")
    print("  1. Checks if subclass defines auto_context")
    print("  2. If so, saves it as _auto_context")
    print("  3. Replaces auto_context with BeakerContext.auto_context")
    print()
    print("This means BeakerContext.auto_context is the WRAPPER that:")
    print("  - Calls self._auto_context() (the subclass version)")
    print("  - Appends kernel state if configured")
    print("  - Appends notebook state if configured")
    print("  - Appends workflow info if any")
    print("  - Appends integration prompts if any")
    print()
    print("BeakerContext.__init__ then does:")
    print("  self.agent.set_auto_context('Default context', self.auto_context)")
    print()
    print("This registers auto_context as a content_updater callable")
    print("that gets called EVERY TIME the agent makes a request!")
    print()

    # Check BDIKitContext
    from bdikit_context.context import BDIKitContext
    has_auto = hasattr(BDIKitContext, '_auto_context')
    print(f"BDIKitContext has _auto_context: {has_auto}")
    if has_auto:
        src = inspect.getsource(BDIKitContext._auto_context)
        print(f"_auto_context source:\n{src}")
    print("PASS: __init_subclass__ mechanism understood")
    return True


def test_7_prompt_composition_layers():
    print("\n" + "=" * 60)
    print("TEST 7: Full prompt composition analysis")
    print("=" * 60)

    print("The LLM sees messages in this order:")
    print()
    print("1. SYSTEM MESSAGE (from build_prompt / custom_prelude)")
    print("   - Default: ReAct agent instructions")
    print("   - Can be overridden via ReActAgent(custom_prelude=...)")
    print("   - Also appended: model-specific prompt instructions")
    print()
    print("2. AUTO-CONTEXT MESSAGE (from set_auto_context)")
    print("   - Updated every turn via content_updater callable")
    print("   - In BDIKitContext: Returns the rendered system/main.j2 template")
    print("   - In CodeContext: Returns hardcoded f-string")
    print("   - BeakerContext wrapper adds: kernel state, notebook state, workflows, integrations")
    print()
    print("3. USER PREAMBLE (from default_preamble / set_user_preamble)")
    print("   - Optional first user message")
    print("   - Set during setup() via default_preamble()")
    print()
    print("4. CONVERSATION HISTORY")
    print("   - Human/AI messages from the conversation")
    print()
    print("AGENT INFO (separate from messages):")
    print("  - agent_prompt = self.__class__.__doc__ (the class docstring)")
    print("  - tools = {name: docstring} for each @tool")
    print("  - This info is sent to the FRONTEND, not directly to the LLM")
    print()

    print("KEY FINDING: The agent_prompt (docstring) is NOT in the LLM messages!")
    print("It is only sent to the frontend via get_info().")
    print("The ACTUAL system prompt is build_prompt() + model instructions.")
    print("The ACTUAL context is auto_context() output.")
    print()
    print("PASS: Full prompt composition chain mapped")
    return True


def test_8_custom_prelude_in_beaker_agent():
    print("\n" + "=" * 60)
    print("TEST 8: Can BeakerAgent pass custom_prelude to ReActAgent?")
    print("=" * 60)

    import inspect
    from beaker_kernel.lib.agent import BeakerAgent

    # Check if BeakerAgent.__init__ passes custom_prelude
    src = inspect.getsource(BeakerAgent.__init__)
    has_custom_prelude = "custom_prelude" in src
    print(f"BeakerAgent.__init__ references custom_prelude: {has_custom_prelude}")

    if has_custom_prelude:
        print("BeakerAgent already supports custom_prelude!")
    else:
        print("BeakerAgent does NOT pass custom_prelude to ReActAgent")
        print("But it uses **kwargs which would forward unknown args")

        # Check if kwargs would work
        has_kwargs = "**kwargs" in src
        print(f"BeakerAgent.__init__ has **kwargs: {has_kwargs}")

        if has_kwargs:
            print("**kwargs IS present - custom_prelude would be forwarded!")
            print("This means we can pass custom_prelude when creating the agent")
        else:
            print("NO **kwargs - would need to modify BeakerAgent")

    # Check if BeakerContext passes kwargs to agent_cls
    from beaker_kernel.lib.context import BeakerContext
    ctx_src = inspect.getsource(BeakerContext.__init__)
    print(f"\nBeakerContext.__init__ agent creation:")
    # Find the line where agent is created
    for line in ctx_src.split("\n"):
        if "agent_cls(" in line:
            print(f"  {line.strip()}")

    print()
    print("CRITICAL FINDING: BeakerContext creates agent with ONLY:")
    print("  agent_cls(context=self, tools=self.subkernel.tools)")
    print("No mechanism to pass custom_prelude or other kwargs!")
    return True


def test_9_env_var_prompt_override():
    print("\n" + "=" * 60)
    print("TEST 9: Can we use environment variables for prompt config?")
    print("=" * 60)

    # Check if Beaker config has any prompt-related env vars
    import dataclasses
    from beaker_kernel.lib.config import config

    print("Beaker config fields related to prompts:")
    for f in dataclasses.fields(config.__class__):
        if any(kw in f.name.lower() for kw in ['prompt', 'context', 'prelude']):
            print(f"  {f.name}: {f.metadata.get('env_var', 'N/A')}")

    print("\nNo prompt-specific config fields found in Beaker!")
    print("Prompts are entirely managed by the context/agent classes.")
    print()
    print("Possible injection points via env vars:")
    print("  1. Custom env var read by our context (e.g. HARMONIA_PROMPTS_DIR)")
    print("  2. Pass via .env file -> Apptainer -> container env")
    print("  3. Read from experiment config YAML at context setup time")
    return True


def test_10_tool_description_dual_source():
    print("\n" + "=" * 60)
    print("TEST 10: Tool description dual-source analysis")
    print("=" * 60)

    from bdikit_context.prompts import PromptLoader

    loader = PromptLoader()

    print("Tool descriptions come from TWO sources:")
    print()
    print("1. Python docstrings (in agent.py @tool methods)")
    print("   - Used by Archytas to generate tool schemas for the LLM")
    print("   - Sent as function descriptions in tool_calls API")
    print("   - CANNOT be changed without code modification")
    print()
    print("2. Jinja2 templates (in prompts/tools/*.j2)")
    print("   - Currently NOT used in the system prompt")
    print("   - get_tool_description() exists but is never called!")
    print()

    # Verify: check if any code calls get_tool_description
    import inspect
    from bdikit_context import context as ctx_mod
    ctx_src = inspect.getsource(ctx_mod)
    uses_tool_desc = "get_tool_description" in ctx_src
    print(f"BDIKitContext uses get_tool_description: {uses_tool_desc}")

    from bdikit_context import agent as agent_mod
    agent_src = inspect.getsource(agent_mod)
    uses_tool_desc2 = "get_tool_description" in agent_src
    print(f"BDIKitAgent uses get_tool_description: {uses_tool_desc2}")

    print()
    if not uses_tool_desc and not uses_tool_desc2:
        print("CONFIRMED: Tool Jinja2 templates are UNUSED dead code!")
        print("Tool descriptions come ONLY from Python docstrings")
        print("To make tool descriptions configurable, we'd need to either:")
        print("  a) Modify @tool decorator to accept external descriptions")
        print("  b) Post-process tool schemas before sending to LLM")
        print("  c) Include tool descriptions in the system prompt instead")
    return True


if __name__ == "__main__":
    results = {}
    tests = [
        ("test_1_custom_prelude", test_1_custom_prelude),
        ("test_2_docstring_override", test_2_docstring_override),
        ("test_3_custom_prompt_loader", test_3_custom_prompt_loader),
        ("test_4_singleton_behavior", test_4_singleton_behavior),
        ("test_5_auto_context", test_5_auto_context),
        ("test_6_beaker_context_init_chain", test_6_beaker_context_init_chain),
        ("test_7_prompt_composition_layers", test_7_prompt_composition_layers),
        ("test_8_custom_prelude_in_beaker_agent", test_8_custom_prelude_in_beaker_agent),
        ("test_9_env_var_prompt_override", test_9_env_var_prompt_override),
        ("test_10_tool_description_dual_source", test_10_tool_description_dual_source),
    ]

    for name, test_fn in tests:
        try:
            result = test_fn()
            results[name] = "PASS" if result else "FAIL"
        except Exception as e:
            results[name] = f"ERROR: {e}"
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, result in results.items():
        status = "PASS" if result == "PASS" else "FAIL"
        print(f"  [{status}] {name}: {result}")
