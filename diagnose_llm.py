#!/usr/bin/env python3
"""Diagnostic script to debug LLM provider configuration.

Run this inside the apptainer container:
    apptainer exec --bind .:/jupyter --pwd /jupyter --env-file .env jupyter.sif python diagnose_llm.py
"""

import os
import sys

def main():
    print("=" * 70)
    print("LLM Provider Diagnostic Script")
    print("=" * 70)

    # Step 1: Check environment variables BEFORE any imports
    print("\n[1] Environment variables BEFORE imports:")
    print(f"    LLM_SERVICE_PROVIDER:     {os.environ.get('LLM_SERVICE_PROVIDER', 'NOT SET')}")
    print(f"    LLM_PROVIDER_IMPORT_PATH: {os.environ.get('LLM_PROVIDER_IMPORT_PATH', 'NOT SET')}")
    print(f"    LLM_SERVICE_MODEL:        {os.environ.get('LLM_SERVICE_MODEL', 'NOT SET')}")
    token = os.environ.get('LLM_SERVICE_TOKEN', '')
    print(f"    LLM_SERVICE_TOKEN:        {token[:20]}..." if token else "    LLM_SERVICE_TOKEN:        NOT SET")
    orkey = os.environ.get('OPENROUTER_API_KEY', '')
    print(f"    OPENROUTER_API_KEY:       {orkey[:20]}..." if orkey else "    OPENROUTER_API_KEY:       NOT SET")

    # Step 2: Import beaker-kernel config and check if already loaded
    print("\n[2] Importing beaker_kernel.lib.config...")
    from beaker_kernel.lib.config import config, reset_config

    print(f"    config.config_obj is None: {config.config_obj is None}")
    config_was_none = config.config_obj is None

    # Step 3: Check config values (this will trigger lazy load if needed)
    print("\n[3] Accessing config values (triggers lazy load if config_obj was None):")
    # Note: 'provider' is in ConfigClass, access via config_obj if available
    if config.config_obj:
        print(f"    config_obj.provider:               '{config.config_obj.provider}'")
    print(f"    config.model_provider_import_path: '{config.model_provider_import_path}'")
    print(f"    config.model_name:                 '{config.model_name}'")
    svc_token = config.llm_service_token or ''
    print(f"    config.llm_service_token:          '{svc_token[:20]}...'" if svc_token else "    config.llm_service_token:          ''")

    if config_was_none:
        print("\n    [!] Config was lazy-loaded just now. Values above are from env vars at load time.")
    else:
        print("\n    [!] Config was ALREADY loaded before this script ran!")

    # Step 4: Check environment AFTER config load
    print("\n[4] Environment variables AFTER config load (should be same as before):")
    print(f"    LLM_PROVIDER_IMPORT_PATH: {os.environ.get('LLM_PROVIDER_IMPORT_PATH', 'NOT SET')}")

    # Step 5: Import bdikit_context (this calls configure_llm_environment)
    print("\n[5] Importing bdikit_context (runs configure_llm_environment)...")
    try:
        # Add src to path if needed
        src_path = os.path.join(os.path.dirname(__file__), 'src')
        if src_path not in sys.path:
            sys.path.insert(0, src_path)

        import bdikit_context
        print("    Successfully imported bdikit_context")
    except Exception as e:
        print(f"    ERROR importing bdikit_context: {e}")
        import traceback
        traceback.print_exc()

    # Step 6: Check environment AFTER bdikit_context import
    print("\n[6] Environment variables AFTER bdikit_context import:")
    print(f"    LLM_PROVIDER_IMPORT_PATH: {os.environ.get('LLM_PROVIDER_IMPORT_PATH', 'NOT SET')}")
    print(f"    LLM_SERVICE_MODEL:        {os.environ.get('LLM_SERVICE_MODEL', 'NOT SET')}")
    token2 = os.environ.get('LLM_SERVICE_TOKEN', '')
    print(f"    LLM_SERVICE_TOKEN:        {token2[:20]}..." if token2 else "    LLM_SERVICE_TOKEN:        NOT SET")

    # Step 7: Check if config reflects the new values (it won't - it's cached!)
    print("\n[7] Config values AFTER bdikit_context import (cached - may not change!):")
    print(f"    config.model_provider_import_path: '{config.model_provider_import_path}'")
    print(f"    config.model_name:                 '{config.model_name}'")

    mismatch = config.model_provider_import_path != os.environ.get('LLM_PROVIDER_IMPORT_PATH', '')
    if mismatch:
        print("\n    [!!!] MISMATCH DETECTED!")
        print(f"         Config has: '{config.model_provider_import_path}'")
        print(f"         Env var is: '{os.environ.get('LLM_PROVIDER_IMPORT_PATH', '')}'")
        print("         This is the ROOT CAUSE - config is cached!")

    # Step 8: Try resetting config
    print("\n[8] Resetting config and re-checking:")
    reset_config()
    print(f"    config.config_obj is None after reset: {config.config_obj is None}")
    print(f"    config.model_provider_import_path: '{config.model_provider_import_path}'")
    print(f"    config.model_name:                 '{config.model_name}'")
    svc_token2 = config.llm_service_token or ''
    print(f"    config.llm_service_token:          '{svc_token2[:20]}...'" if svc_token2 else "    config.llm_service_token:          ''")

    # Step 9: Test get_model()
    print("\n[9] Testing config.get_model():")
    try:
        model = config.get_model()
        if model is None:
            print("    Model is None!")
        else:
            print(f"    Model type:  {type(model)}")
            print(f"    Model class: {model.__class__.__name__}")
            if hasattr(model, 'model_name'):
                print(f"    Model name:  {model.model_name}")
            if hasattr(model, 'base_url'):
                print(f"    Base URL:    {model.base_url}")
            if hasattr(model, 'client'):
                client = model.client
                if hasattr(client, 'base_url'):
                    print(f"    Client base_url: {client.base_url}")
    except Exception as e:
        print(f"    ERROR: {e}")
        import traceback
        traceback.print_exc()

    # Step 10: Check if archytas OpenRouter model exists
    print("\n[10] Checking archytas.models.openrouter:")
    try:
        from archytas.models.openrouter import OpenRouterModel
        print(f"    OpenRouterModel found: {OpenRouterModel}")
        # Check source file
        import inspect
        source_file = inspect.getfile(OpenRouterModel)
        print(f"    Source file: {source_file}")
        # Check __init__ signature
        sig = inspect.signature(OpenRouterModel.__init__)
        print(f"    __init__ parameters: {list(sig.parameters.keys())}")
    except ImportError as e:
        print(f"    ERROR: {e}")

    # Step 11: Try creating OpenRouterModel directly
    print("\n[11] Testing OpenRouterModel directly:")
    try:
        from archytas.models.openrouter import OpenRouterModel
        test_config = {
            "model_name": "xiaomi/mimo-v2-flash:free",
            "api_key": os.environ.get('OPENROUTER_API_KEY', os.environ.get('LLM_SERVICE_TOKEN', '')),
        }
        test_model = OpenRouterModel(test_config)
        print(f"    Created model: {test_model}")
        print(f"    Model class: {test_model.__class__.__name__}")
        if hasattr(test_model, 'client') and hasattr(test_model.client, 'base_url'):
            print(f"    Client base_url: {test_model.client.base_url}")
    except Exception as e:
        print(f"    ERROR: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 70)
    print("DIAGNOSIS COMPLETE")
    print("=" * 70)

    # Summary
    print("\nSUMMARY:")
    if mismatch:
        print("  - ROOT CAUSE: Config was cached before bdikit_context set env vars")
        print("  - FIX: Call reset_config() after configure_llm_environment()")
    else:
        print("  - Config values match environment - check other issues")

if __name__ == "__main__":
    main()
