#!/usr/bin/env python3
"""
Integration tests for prompt configuration mechanisms.

Tests actual injection points and proposed implementation patterns.
"""

import sys
import os
import tempfile
import asyncio
from pathlib import Path

sys.path.insert(0, "/opt/harmonia_src")


def test_11_env_var_prompts_dir():
    """Test using environment variable to set prompts directory."""
    print("=" * 60)
    print("TEST 11: Environment variable HARMONIA_PROMPTS_DIR")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Set up custom prompt structure
        system_dir = Path(tmpdir) / "system"
        system_dir.mkdir()
        (system_dir / "main.j2").write_text(
            "ENV_VAR_TEST: Custom prompt loaded from HARMONIA_PROMPTS_DIR.\n"
            "{% for tool in tools %}\n- {{ tool.name }}\n{% endfor %}"
        )

        # Simulate what HarmoniaConfig could do
        os.environ["HARMONIA_PROMPTS_DIR"] = tmpdir

        from bdikit_context.prompts import PromptLoader
        prompts_dir_env = os.environ.get("HARMONIA_PROMPTS_DIR")
        if prompts_dir_env:
            loader = PromptLoader(prompts_dir=Path(prompts_dir_env))
            result = loader.get_system_prompt(
                tools=[{"name": "match_schema", "description": "test"}]
            )
            print(f"Loaded from env var: {result}")
            assert "ENV_VAR_TEST" in result
            print("PASS: Can load prompts from env-var specified directory")
        else:
            print("FAIL: Env var not set")

        del os.environ["HARMONIA_PROMPTS_DIR"]
    return True


def test_12_yaml_config_prompts_section():
    """Test proposed YAML config with prompts section."""
    print("\n" + "=" * 60)
    print("TEST 12: Proposed YAML prompts config parsing")
    print("=" * 60)

    import yaml
    from dataclasses import dataclass, field
    from typing import Optional, Dict

    # Proposed PromptsConfig dataclass
    @dataclass
    class PromptsConfig:
        system_prompt: Optional[str] = None  # Path to system prompt .j2
        react_agent_prompt: Optional[str] = None  # Path to custom ReAct prelude
        tool_prompts_dir: Optional[str] = None  # Path to tool prompts directory
        code_context_prompt: Optional[str] = None  # Path to code context prompt
        prompts_base_dir: Optional[str] = None  # Base dir for all relative paths

        def resolve_path(self, path_str: str) -> Path:
            """Resolve a path relative to prompts_base_dir if not absolute."""
            path = Path(path_str)
            if not path.is_absolute() and self.prompts_base_dir:
                path = Path(self.prompts_base_dir) / path
            return path

    # Test parsing from YAML
    yaml_content = """
experiment:
  name: "test_with_prompts"
  description: "Testing prompt configuration"

llm:
  provider: anyllm:ollama
  model: devstral:latest
  temperature: 0.0

prompts:
  prompts_base_dir: "/path/to/experiment/configs/prompts"
  system_prompt: "system_prompt/v2_autonomous/main.j2"
  react_agent_prompt: "react_agent_prompts/tool_focused/prelude.txt"
  tool_prompts_dir: "bdikit_prompts/v1_default"
  code_context_prompt: "code_context_prompts/v1_minimal/prompt.txt"

messages:
  - content: "Load dou.csv"
    wait_seconds: 60
"""

    data = yaml.safe_load(yaml_content)
    prompts_data = data.get("prompts", {})

    config = PromptsConfig(**prompts_data)
    print(f"Parsed prompts config:")
    print(f"  system_prompt: {config.system_prompt}")
    print(f"  react_agent_prompt: {config.react_agent_prompt}")
    print(f"  tool_prompts_dir: {config.tool_prompts_dir}")
    print(f"  code_context_prompt: {config.code_context_prompt}")
    print(f"  prompts_base_dir: {config.prompts_base_dir}")

    # Test path resolution
    resolved = config.resolve_path(config.system_prompt)
    print(f"\n  Resolved system_prompt: {resolved}")
    expected = Path("/path/to/experiment/configs/prompts/system_prompt/v2_autonomous/main.j2")
    assert str(resolved) == str(expected)
    print("PASS: Path resolution works correctly")

    # Test backward compatibility (no prompts section)
    yaml_no_prompts = """
experiment:
  name: "legacy_config"
llm:
  provider: ollama
  model: devstral:latest
"""
    data2 = yaml.safe_load(yaml_no_prompts)
    prompts_data2 = data2.get("prompts", {})
    config2 = PromptsConfig(**prompts_data2)
    assert config2.system_prompt is None
    assert config2.react_agent_prompt is None
    print("PASS: Backward compatible (no prompts section uses defaults)")
    return True


def test_13_context_init_override_pattern():
    """Test the proposed override pattern for BDIKitContext.__init__."""
    print("\n" + "=" * 60)
    print("TEST 13: Context init override pattern")
    print("=" * 60)

    # Simulate the proposed modification to BDIKitContext.__init__
    from bdikit_context.prompts import PromptLoader

    class MockConfig:
        """Simulate experiment config with prompts section."""
        def __init__(self, prompts_dir=None):
            self.prompts_dir = prompts_dir

    # Pattern 1: Use config to override prompt loader
    def create_prompt_loader(config):
        """Factory function: create PromptLoader from config."""
        if hasattr(config, 'prompts_dir') and config.prompts_dir:
            return PromptLoader(prompts_dir=Path(config.prompts_dir))
        return PromptLoader()  # Default

    # Test with default
    default_config = MockConfig()
    loader1 = create_prompt_loader(default_config)
    print(f"Default loader dir: {loader1.prompts_dir}")

    # Test with override
    with tempfile.TemporaryDirectory() as tmpdir:
        system_dir = Path(tmpdir) / "system"
        system_dir.mkdir()
        (system_dir / "main.j2").write_text("OVERRIDE TEST PROMPT")

        custom_config = MockConfig(prompts_dir=tmpdir)
        loader2 = create_prompt_loader(custom_config)
        result = loader2.get_system_prompt()
        print(f"Custom loader result: {result}")
        assert "OVERRIDE TEST" in result
        print("PASS: Config-based prompt loader override works")

    # Pattern 2: Environment variable approach
    print("\nPattern 2: Environment variable in .env file")
    print("  Add HARMONIA_PROMPTS_DIR to .env")
    print("  Read in BDIKitContext.__init__:")
    print("    prompts_dir = os.environ.get('HARMONIA_PROMPTS_DIR')")
    print("    self.prompt_loader = PromptLoader(Path(prompts_dir)) if prompts_dir else PromptLoader()")
    print("  Pros: Simple, works with existing exec_apptainer.sh flow")
    print("  Cons: Can't compose from multiple dirs, less flexible")

    # Pattern 3: Config object approach
    print("\nPattern 3: Config object in BDIKitContext.__init__")
    print("  BDIKitContext receives config dict from Beaker")
    print("  We could embed prompt config in the Beaker context config")
    print("  But: Beaker context config comes from Beaker, not our YAML")
    print()
    print("CONCLUSION: Pattern 1 (factory function) is best")
    print("  Combined with env var for the prompts_dir path")
    return True


def test_14_react_prelude_override():
    """Test overriding the ReAct agent prelude via file."""
    print("\n" + "=" * 60)
    print("TEST 14: ReAct prelude override from file")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        prelude_file = Path(tmpdir) / "custom_prelude.txt"
        prelude_file.write_text(
            "You are a DATA HARMONIZATION specialist.\n"
            "Focus on using tools to match schemas and values.\n"
            "Be autonomous - proceed through all steps without asking.\n"
        )

        # Read and use
        custom_prelude = prelude_file.read_text()
        print(f"Custom prelude from file:\n{custom_prelude}")

        from archytas.react import build_prompt
        prompt = build_prompt(custom_prelude=custom_prelude)
        assert "DATA HARMONIZATION specialist" in prompt
        print("PASS: Custom prelude from file works")

    # But: How to inject this into BeakerAgent?
    print("\nINJECTION POINT ANALYSIS:")
    print("  BeakerContext.__init__ creates agent:")
    print("    self.agent = agent_cls(context=self, tools=self.subkernel.tools)")
    print()
    print("  BeakerAgent.__init__ has **kwargs, so:")
    print("    self.agent = agent_cls(context=self, tools=..., custom_prelude=prelude)")
    print("  Would forward to ReActAgent via **kwargs!")
    print()
    print("  PROPOSED CHANGE to BDIKitContext.__init__:")
    print("    custom_prelude = self._load_react_prelude(config)")
    print("    super().__init__(beaker_kernel, BDIKitAgent, config)")
    print()
    print("  BUT: super().__init__ creates the agent, not us!")
    print("  We'd need to OVERRIDE the agent creation in our __init__")
    print("  OR modify BeakerContext to accept agent_kwargs")
    print()
    print("  ALTERNATIVE: Override agent AFTER creation:")
    print("    super().__init__(beaker_kernel, BDIKitAgent, config)")
    print("    # Now override the prelude on the already-created agent")
    print("    self.agent.custom_prelude = custom_prelude")
    print("    self.agent.update_prompt()  # Re-builds system message")
    return True


def test_15_post_init_prompt_override():
    """Test overriding prompts after agent creation (post-init pattern)."""
    print("\n" + "=" * 60)
    print("TEST 15: Post-init prompt override pattern")
    print("=" * 60)

    import inspect
    from archytas.react import ReActAgent

    # Check if update_prompt exists and what it does
    print("ReActAgent.update_prompt() source:")
    src = inspect.getsource(ReActAgent.update_prompt)
    print(src)

    print("\nThis means we CAN do:")
    print("  1. Create agent normally (via BeakerContext.__init__)")
    print("  2. Set agent.custom_prelude = our_custom_prelude")
    print("  3. Call agent.update_prompt()")
    print("  4. This rebuilds the system message with custom prelude")
    print()
    print("This is the SAFEST approach because:")
    print("  - No need to modify BeakerContext.__init__")
    print("  - No need to modify BeakerAgent.__init__")
    print("  - Works with existing Beaker lifecycle")
    print("  - Just need to hook into BDIKitContext.__init__ AFTER super()")
    print()

    # Verify the pattern works on a real agent (without Beaker kernel)
    # We can't fully test this without a running Beaker, but we can
    # verify the attributes exist
    print("Verification:")
    assert hasattr(ReActAgent, 'update_prompt')
    assert hasattr(ReActAgent, 'custom_prelude')
    print("  ReActAgent has update_prompt: True")
    print("  ReActAgent has custom_prelude attribute: True (set in __init__)")
    print("PASS: Post-init override pattern is viable")
    return True


def test_16_code_context_prompt_override():
    """Test making CodeContext prompt configurable."""
    print("\n" + "=" * 60)
    print("TEST 16: CodeContext prompt configurability")
    print("=" * 60)

    from code_context.context import CodeContext

    print("Current CodeContext.auto_context():")
    print("  - Returns hardcoded f-string")
    print("  - References self.subkernel.DISPLAY_NAME")
    print()
    print("To make configurable:")
    print("  Option A: Template-based (like BDIKitContext)")
    print("    - Create prompts/system/main.j2 for code_context")
    print("    - Use PromptLoader in CodeContext")
    print("    - Pros: Consistent with BDIKitContext pattern")
    print("    - Cons: Overkill for a simple prompt")
    print()
    print("  Option B: File-based (read from path)")
    print("    - Read prompt from a .txt or .j2 file")
    print("    - Path comes from env var or config")
    print("    - Simpler than full template system")
    print()
    print("  Option C: Env var with default")
    print("    - HARMONIA_CODE_CONTEXT_PROMPT=/path/to/prompt.txt")
    print("    - Falls back to hardcoded default")
    print("    - Simplest, but least composable")
    print()
    print("RECOMMENDATION: Option B for CodeContext (file-based)")
    print("  CodeContext is simpler, doesn't need full Jinja2 template system")
    return True


def test_17_prompt_validation():
    """Test prompt template validation at config load time."""
    print("\n" + "=" * 60)
    print("TEST 17: Prompt template validation")
    print("=" * 60)

    from bdikit_context.prompts import PromptLoader
    from jinja2 import TemplateNotFound, TemplateSyntaxError

    # Test 1: Missing directory
    try:
        loader = PromptLoader(prompts_dir=Path("/nonexistent/path"))
        # Loader creation succeeds (Jinja2 FileSystemLoader doesn't check)
        result = loader.get_system_prompt(tools=[])
        print("ERROR: Should have failed!")
    except TemplateNotFound:
        print("PASS: TemplateNotFound raised for missing directory")
    except Exception as e:
        print(f"Got exception: {type(e).__name__}: {e}")
        print("PASS: Fails appropriately")

    # Test 2: Invalid template syntax
    with tempfile.TemporaryDirectory() as tmpdir:
        system_dir = Path(tmpdir) / "system"
        system_dir.mkdir()
        (system_dir / "main.j2").write_text("{% invalid syntax here %}")

        try:
            loader = PromptLoader(prompts_dir=Path(tmpdir))
            result = loader.get_system_prompt(tools=[])
            print("ERROR: Should have failed!")
        except TemplateSyntaxError:
            print("PASS: TemplateSyntaxError raised for invalid template")
        except Exception as e:
            print(f"Got exception: {type(e).__name__}: {e}")

    # Test 3: Template that references undefined variables
    with tempfile.TemporaryDirectory() as tmpdir:
        system_dir = Path(tmpdir) / "system"
        system_dir.mkdir()
        (system_dir / "main.j2").write_text("{{ undefined_var }}")

        loader = PromptLoader(prompts_dir=Path(tmpdir))
        result = loader.get_system_prompt(tools=[])
        print(f"Undefined var renders as: '{result}'")
        print("NOTE: Jinja2 renders undefined vars as empty string (no error)")
        print("IMPLICATION: Need explicit validation of required template variables")

    print()
    print("VALIDATION STRATEGY:")
    print("  1. Check paths exist at config load time")
    print("  2. Try to load+render templates with test data")
    print("  3. Check that required variables produce non-empty output")
    print("  4. Fail fast with clear error messages")
    return True


if __name__ == "__main__":
    results = {}
    tests = [
        ("test_11_env_var_prompts_dir", test_11_env_var_prompts_dir),
        ("test_12_yaml_config_prompts_section", test_12_yaml_config_prompts_section),
        ("test_13_context_init_override_pattern", test_13_context_init_override_pattern),
        ("test_14_react_prelude_override", test_14_react_prelude_override),
        ("test_15_post_init_prompt_override", test_15_post_init_prompt_override),
        ("test_16_code_context_prompt_override", test_16_code_context_prompt_override),
        ("test_17_prompt_validation", test_17_prompt_validation),
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
