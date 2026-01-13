#!/usr/bin/env python3
"""Quick test to verify LLM configuration."""

import os

print("=== Quick LLM Configuration Test ===")
print()

# Check env vars
print("[1] Environment Variables:")
token = os.environ.get("LLM_SERVICE_TOKEN", "NOT SET")
print(f"    LLM_SERVICE_TOKEN:        {token[:30]}..." if token and token != "NOT SET" else f"    LLM_SERVICE_TOKEN:        {token}")
print(f"    LLM_PROVIDER_IMPORT_PATH: {os.environ.get('LLM_PROVIDER_IMPORT_PATH', 'NOT SET')}")
print(f"    LLM_SERVICE_MODEL:        {os.environ.get('LLM_SERVICE_MODEL', 'NOT SET')}")
print(f"    LLM_SERVICE_PROVIDER:     {os.environ.get('LLM_SERVICE_PROVIDER', 'NOT SET')}")

# Check beaker config
print()
print("[2] Beaker Config:")
from beaker_kernel.lib.config import config
print(f"    config.config_obj is None: {config.config_obj is None}")
print(f"    config repr: {repr(config)[:200]}...")

# Test get_model
print()
print("[4] Testing config.get_model():")
try:
    model = config.get_model()
    if model:
        print(f"    Model class:  {model.__class__.__name__}")
        print(f"    Model module: {model.__class__.__module__}")
        if hasattr(model, 'client') and hasattr(model.client, 'base_url'):
            print(f"    Client base_url: {model.client.base_url}")
    else:
        print("    Model is None!")
except Exception as e:
    import traceback
    print(f"    ERROR: {e}")
    traceback.print_exc()

print()
print("=== Test Complete ===")
