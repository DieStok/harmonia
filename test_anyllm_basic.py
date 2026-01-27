#!/usr/bin/env python3
"""
Basic test script for any-llm functionality (without archytas dependency).

This script verifies that:
1. The any-llm library works correctly
2. Direct LLM calls can be made
3. Provider switching works

Note: The full AnyLLMModel adapter test must run inside the Beaker container
where archytas is available.

Usage:
    # Quick import test
    python test_anyllm_basic.py

    # With Ollama test (requires running Ollama server)
    OLLAMA_HOST=http://localhost:11434 python test_anyllm_basic.py --test-ollama
"""

import os
import sys
import argparse
import asyncio
from pathlib import Path


def test_anyllm_imports():
    """Test that any-llm modules can be imported."""
    print("Testing any-llm imports...")

    try:
        from any_llm import AnyLLM, acompletion, completion
        print("  ✓ any_llm core imported successfully")
    except ImportError as e:
        print(f"  ✗ Failed to import any_llm: {e}")
        return False

    try:
        from any_llm.constants import LLMProvider
        providers = list(LLMProvider)
        print(f"  ✓ Found {len(providers)} LLM providers")
    except ImportError as e:
        print(f"  ✗ Failed to import LLMProvider: {e}")
        return False

    try:
        from any_llm.types.completion import ChatCompletion, ChatCompletionChunk
        print("  ✓ Completion types imported successfully")
    except ImportError as e:
        print(f"  ✗ Failed to import completion types: {e}")
        return False

    return True


def test_provider_creation():
    """Test that providers can be created."""
    print("\nTesting provider creation...")

    from any_llm import AnyLLM

    # Test creating Ollama provider (no API key needed)
    try:
        ollama_provider = AnyLLM.create(
            "ollama",
            api_base=os.getenv("OLLAMA_HOST", "http://localhost:11434")
        )
        print(f"  ✓ Ollama provider created: {type(ollama_provider).__name__}")
    except Exception as e:
        print(f"  ✗ Failed to create Ollama provider: {e}")
        return False

    # Test creating OpenAI provider (requires API key, but creation should work)
    try:
        # Just test the class lookup, not actual creation which needs API key
        from any_llm.constants import LLMProvider
        provider_class = AnyLLM.get_provider_class(LLMProvider.OPENAI)
        print(f"  ✓ OpenAI provider class found: {provider_class.__name__}")
    except Exception as e:
        print(f"  ✗ Failed to lookup OpenAI provider: {e}")
        return False

    return True


def test_supported_providers():
    """List all supported providers."""
    print("\nSupported providers:")

    from any_llm import AnyLLM

    providers = AnyLLM.get_supported_providers()
    for i, provider in enumerate(providers[:10]):
        print(f"  - {provider}")
    if len(providers) > 10:
        print(f"  ... and {len(providers) - 10} more")

    print(f"\n  Total: {len(providers)} providers")
    return True


async def test_ollama_direct():
    """Test direct Ollama completion using any-llm."""
    print("\nTesting Ollama direct completion...")

    from any_llm import acompletion

    ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model = os.getenv("TEST_MODEL", "llama3")

    print(f"  Ollama host: {ollama_host}")
    print(f"  Model: {model}")

    try:
        response = await acompletion(
            model=model,
            provider="ollama",
            messages=[{"role": "user", "content": "Say 'hello world' and nothing else."}],
            api_base=ollama_host,
            max_tokens=20,
            temperature=0.0,
        )

        content = response.choices[0].message.content
        print(f"  Response: {content[:80]}...")
        print(f"  ✓ Completion successful")
        return True

    except Exception as e:
        print(f"  ✗ Completion failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test any-llm basic functionality")
    parser.add_argument("--test-ollama", action="store_true", help="Test Ollama completion (requires running server)")
    args = parser.parse_args()

    print("=" * 60)
    print("any-llm Basic Functionality Test")
    print("=" * 60)

    results = {}

    # Basic tests
    results["imports"] = test_anyllm_imports()
    if not results["imports"]:
        print("\n✗ Import test failed. Cannot continue.")
        sys.exit(1)

    results["provider_creation"] = test_provider_creation()
    results["supported_providers"] = test_supported_providers()

    # Optional completion test
    if args.test_ollama:
        results["ollama_completion"] = asyncio.run(test_ollama_direct())

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
        print("\nNote: Full adapter tests require the Beaker container environment.")
        return 0
    else:
        print("\n✗ Some tests failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
