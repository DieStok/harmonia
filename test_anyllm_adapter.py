#!/usr/bin/env python3
"""
Test script for the any-llm adapter integration.

This script verifies that:
1. The any-llm library can be imported
2. The AnyLLMModel adapter can be instantiated
3. Configuration is correctly parsed
4. (Optional) LLM calls work with available providers

Usage:
    # Quick import test
    python test_anyllm_adapter.py

    # With Ollama test (requires running Ollama server)
    OLLAMA_HOST=http://localhost:11434 python test_anyllm_adapter.py --test-ollama

    # With OpenRouter test (requires API key)
    OPENROUTER_API_KEY=your-key python test_anyllm_adapter.py --test-openrouter
"""

import os
import sys
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


def test_imports():
    """Test that all required modules can be imported."""
    print("Testing imports...")

    try:
        from any_llm import AnyLLM, acompletion, completion
        print("  ✓ any_llm imported successfully")
    except ImportError as e:
        print(f"  ✗ Failed to import any_llm: {e}")
        print("  Try: pip install -e /hpc/compgen/projects/llm_GEO_project/any-llm[all]")
        return False

    try:
        from bdikit_context.llm.anyllm import AnyLLMModel, ChatAnyLLM
        print("  ✓ AnyLLMModel imported successfully")
    except ImportError as e:
        print(f"  ✗ Failed to import AnyLLMModel: {e}")
        return False

    try:
        from bdikit_context.llm.direct import DirectLLMRunner, quick_complete
        print("  ✓ DirectLLMRunner imported successfully")
    except ImportError as e:
        print(f"  ✗ Failed to import DirectLLMRunner: {e}")
        return False

    try:
        from bdikit_context.llm import configure_llm_environment, PROVIDER_IMPORT_MAP
        print("  ✓ LLM configuration module imported successfully")
    except ImportError as e:
        print(f"  ✗ Failed to import LLM config: {e}")
        return False

    return True


def test_provider_mapping():
    """Test that any-llm providers are correctly mapped."""
    print("\nTesting provider mappings...")

    from bdikit_context.llm import PROVIDER_IMPORT_MAP

    anyllm_providers = [k for k in PROVIDER_IMPORT_MAP if k.startswith("anyllm")]
    print(f"  Found {len(anyllm_providers)} any-llm provider mappings:")
    for provider in anyllm_providers[:5]:
        print(f"    - {provider}: {PROVIDER_IMPORT_MAP[provider]}")
    if len(anyllm_providers) > 5:
        print(f"    ... and {len(anyllm_providers) - 5} more")

    return len(anyllm_providers) > 0


def test_config_parsing():
    """Test configuration parsing for any-llm providers."""
    print("\nTesting configuration parsing...")

    from bdikit_context.config import LLMConfig, HarmoniaConfig

    # Test anyllm:ollama provider
    config = LLMConfig(
        provider="anyllm:ollama",
        model="devstral:latest",
        base_url="http://localhost:11434",
        temperature=0.0,
    )
    print(f"  Config created: provider={config.provider}, model={config.model}")
    print(f"  Effective provider: {config.get_effective_provider()}")

    # Test use_anyllm flag
    config2 = LLMConfig(
        provider="openai",
        model="gpt-4o",
        use_anyllm=True,
    )
    effective = config2.get_effective_provider()
    print(f"  With use_anyllm=True: openai -> {effective}")

    return "anyllm" in config.get_effective_provider() and "anyllm" in effective


def test_anyllm_model_instantiation():
    """Test that AnyLLMModel can be instantiated."""
    print("\nTesting AnyLLMModel instantiation...")

    from bdikit_context.llm.anyllm import AnyLLMModel

    # Test with Ollama (no API key required)
    os.environ["LLM_SERVICE_PROVIDER"] = "anyllm:ollama"
    os.environ["LLM_SERVICE_MODEL"] = "llama3"
    os.environ["OLLAMA_HOST"] = "http://localhost:11434"

    try:
        model = AnyLLMModel({"model_name": "llama3"})
        print(f"  ✓ AnyLLMModel instantiated: provider={model.provider}, model={model.config.model_name}")
        return True
    except Exception as e:
        print(f"  ✗ Failed to instantiate AnyLLMModel: {e}")
        return False


async def test_ollama_completion():
    """Test actual completion with Ollama (requires running server)."""
    print("\nTesting Ollama completion...")

    from bdikit_context.llm.direct import DirectLLMRunner

    ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    runner = DirectLLMRunner(
        provider="ollama",
        model="llama3",
        api_base=ollama_host,
        max_tokens=50,
    )

    try:
        result = await runner.complete("Say 'hello' and nothing else.")
        print(f"  Response: {result.content[:100]}...")
        print(f"  Duration: {result.duration_seconds:.2f}s")
        print(f"  Tokens: {result.total_tokens}")
        return True
    except Exception as e:
        print(f"  ✗ Completion failed: {e}")
        return False


async def test_openrouter_completion():
    """Test actual completion with OpenRouter (requires API key)."""
    print("\nTesting OpenRouter completion...")

    from bdikit_context.llm.direct import DirectLLMRunner

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("  ✗ OPENROUTER_API_KEY not set")
        return False

    runner = DirectLLMRunner(
        provider="openrouter",
        model="xiaomi/mimo-v2-flash:free",
        api_key=api_key,
        max_tokens=50,
    )

    try:
        result = await runner.complete("Say 'hello' and nothing else.")
        print(f"  Response: {result.content[:100]}...")
        print(f"  Duration: {result.duration_seconds:.2f}s")
        return True
    except Exception as e:
        print(f"  ✗ Completion failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test any-llm adapter integration")
    parser.add_argument("--test-ollama", action="store_true", help="Test Ollama completion (requires running server)")
    parser.add_argument("--test-openrouter", action="store_true", help="Test OpenRouter completion (requires API key)")
    args = parser.parse_args()

    print("=" * 60)
    print("any-llm Adapter Integration Test")
    print("=" * 60)

    results = {}

    # Basic tests
    results["imports"] = test_imports()
    if not results["imports"]:
        print("\n✗ Import test failed. Cannot continue.")
        sys.exit(1)

    results["provider_mapping"] = test_provider_mapping()
    results["config_parsing"] = test_config_parsing()
    results["model_instantiation"] = test_anyllm_model_instantiation()

    # Optional completion tests
    if args.test_ollama:
        import asyncio
        results["ollama_completion"] = asyncio.run(test_ollama_completion())

    if args.test_openrouter:
        import asyncio
        results["openrouter_completion"] = asyncio.run(test_openrouter_completion())

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    all_passed = True
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {test_name}: {status}")
        if not passed:
            all_passed = False

    if all_passed:
        print("\n✓ All tests passed!")
        return 0
    else:
        print("\n✗ Some tests failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
