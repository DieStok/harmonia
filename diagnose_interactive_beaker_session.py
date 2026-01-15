#!/usr/bin/env python3
"""
Diagnostic script for Beaker interactive sessions.

This script checks:
1. Environment variables required for Beaker/Ollama
2. Entry points registration for beaker.contexts
3. BDIKitContext and BDIKitAgent availability
4. Tool registration with archytas
5. Ollama connectivity (if applicable)
6. Beaker configuration and model setup

Usage:
    # Inside container:
    python diagnose_interactive_beaker_session.py

    # Or via apptainer:
    apptainer exec jupyter.sif python /jupyter/diagnose_interactive_beaker_session.py
"""

import os
import sys
import json
import inspect
from pathlib import Path

# Colors for output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def ok(msg):
    print(f"{Colors.GREEN}✓{Colors.RESET} {msg}")

def fail(msg):
    print(f"{Colors.RED}✗{Colors.RESET} {msg}")

def warn(msg):
    print(f"{Colors.YELLOW}⚠{Colors.RESET} {msg}")

def info(msg):
    print(f"{Colors.BLUE}ℹ{Colors.RESET} {msg}")

def header(msg):
    print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{msg}{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*60}{Colors.RESET}\n")


def check_environment_variables():
    """Check required environment variables."""
    header("1. Environment Variables")

    required_vars = {
        'LLM_SERVICE_PROVIDER': 'LLM provider (ollama, openrouter, etc.)',
        'LLM_SERVICE_MODEL': 'LLM model name',
    }

    optional_vars = {
        'LLM_BASE_URL': 'Base URL for LLM service',
        'OLLAMA_HOST': 'Ollama server host',
        'OPENROUTER_API_KEY': 'OpenRouter API key',
        'JUPYTER_SERVER': 'Jupyter server URL',
        'JUPYTER_TOKEN': 'Jupyter authentication token',
        'SSL_CERT_FILE': 'SSL certificate file path',
    }

    print("Required variables:")
    for var, desc in required_vars.items():
        value = os.environ.get(var)
        if value:
            # Mask sensitive values
            display = value[:20] + '...' if len(value) > 20 else value
            ok(f"{var} = {display}")
        else:
            fail(f"{var} is NOT SET ({desc})")

    print("\nOptional variables:")
    for var, desc in optional_vars.items():
        value = os.environ.get(var)
        if value:
            # Mask API keys
            if 'KEY' in var or 'TOKEN' in var:
                display = value[:10] + '...' if len(value) > 10 else '***'
            else:
                display = value[:50] + '...' if len(value) > 50 else value
            ok(f"{var} = {display}")
        else:
            info(f"{var} is not set ({desc})")

    # Check SSL cert file exists if set
    ssl_cert = os.environ.get('SSL_CERT_FILE')
    if ssl_cert:
        if os.path.exists(ssl_cert):
            ok(f"SSL_CERT_FILE exists: {ssl_cert}")
        else:
            fail(f"SSL_CERT_FILE does NOT exist: {ssl_cert}")


def check_entry_points():
    """Check beaker entry points registration."""
    header("2. Beaker Entry Points")

    try:
        from importlib.metadata import entry_points

        groups = ['beaker.contexts', 'beaker.subkernels', 'beaker.integrations']

        for group in groups:
            eps = entry_points(group=group)
            names = list(eps.names) if hasattr(eps, 'names') else [ep.name for ep in eps]

            if names:
                ok(f"{group}: {names}")
            else:
                warn(f"{group}: (empty)")

        # Specifically check for bdikit_context
        contexts = entry_points(group='beaker.contexts')
        context_names = list(contexts.names) if hasattr(contexts, 'names') else [ep.name for ep in contexts]

        if 'bdikit_context' in context_names:
            ok("bdikit_context is registered in beaker.contexts")
        else:
            fail("bdikit_context is NOT registered in beaker.contexts")
            info("Fix: Add entry point to pyproject.toml and rebuild image")

    except Exception as e:
        fail(f"Error checking entry points: {e}")


def check_bdikit_context():
    """Check BDIKitContext and BDIKitAgent."""
    header("3. BDIKit Context & Agent")

    # Check BDIKitContext
    try:
        from bdikit_context.context import BDIKitContext
        ok(f"BDIKitContext imported: {BDIKitContext}")
        ok(f"BDIKitContext.SLUG = '{BDIKitContext.SLUG}'")
    except ImportError as e:
        fail(f"Cannot import BDIKitContext: {e}")
        return

    # Check BDIKitAgent
    try:
        from bdikit_context.agent import BDIKitAgent
        ok(f"BDIKitAgent imported: {BDIKitAgent}")
    except ImportError as e:
        fail(f"Cannot import BDIKitAgent: {e}")
        return

    # Check workflows directory
    context_dir = Path(inspect.getfile(BDIKitContext)).parent
    workflows_dir = context_dir / 'workflows'

    if workflows_dir.exists():
        yaml_files = list(workflows_dir.glob('*.yaml'))
        if yaml_files:
            ok(f"Workflows directory exists with {len(yaml_files)} YAML file(s)")
            for f in yaml_files:
                info(f"  - {f.name}")
        else:
            warn("Workflows directory exists but is empty")
    else:
        info("No workflows directory (this is OK - 'Context has no workflows' warning is harmless)")


def check_tool_registration():
    """Check tool registration with archytas."""
    header("4. Tool Registration (Archytas)")

    try:
        from archytas.tool_utils import is_tool, tool
        ok("archytas.tool_utils imported")
    except ImportError as e:
        fail(f"Cannot import archytas.tool_utils: {e}")
        return

    try:
        from bdikit_context.agent import BDIKitAgent

        # Find all @tool decorated methods
        tools_found = []
        for name, method in inspect.getmembers(BDIKitAgent):
            if not name.startswith('_') and callable(method):
                if is_tool(method):
                    tools_found.append(name)

        expected_tools = [
            'match_schema',
            'top_matches',
            'match_values',
            'materialize_mapping',
            'get_gdc_acceptable_values',
        ]

        print("Expected BDI-Kit tools:")
        for tool_name in expected_tools:
            if tool_name in tools_found:
                ok(f"  {tool_name}")
            else:
                fail(f"  {tool_name} - NOT FOUND")

        print(f"\nAll tools found on BDIKitAgent: {tools_found}")

        # Check inherited tools
        inherited = [t for t in tools_found if t not in expected_tools]
        if inherited:
            info(f"Inherited/other tools: {inherited}")

    except Exception as e:
        fail(f"Error checking tools: {e}")


def check_beaker_config():
    """Check beaker-kernel configuration."""
    header("5. Beaker Configuration")

    try:
        from beaker_kernel.lib.config import config
        ok("beaker_kernel.lib.config imported")

        # Check key config values
        attrs_to_check = [
            'LLM_SERVICE_TOKEN',
            'LLM_SERVICE_PROVIDER',
            'LLM_SERVICE_MODEL',
            'LLM_BASE_URL',
        ]

        for attr in attrs_to_check:
            if hasattr(config, attr):
                value = getattr(config, attr)
                if value:
                    # Mask sensitive values
                    if 'TOKEN' in attr or 'KEY' in attr:
                        display = str(value)[:10] + '...' if value else 'None'
                    else:
                        display = str(value)[:50] if value else 'None'
                    ok(f"config.{attr} = {display}")
                else:
                    warn(f"config.{attr} = None/empty")
            else:
                info(f"config.{attr} not found")

    except ImportError as e:
        fail(f"Cannot import beaker_kernel.lib.config: {e}")
    except Exception as e:
        fail(f"Error checking config: {e}")


def check_ollama_connectivity():
    """Check Ollama server connectivity."""
    header("6. Ollama Connectivity")

    provider = os.environ.get('LLM_SERVICE_PROVIDER', '')
    if provider.lower() != 'ollama':
        info(f"LLM provider is '{provider}', skipping Ollama checks")
        return

    ollama_host = os.environ.get('OLLAMA_HOST') or os.environ.get('LLM_BASE_URL') or 'http://localhost:11434'

    # Clean up URL
    if not ollama_host.startswith('http'):
        ollama_host = f'http://{ollama_host}'
    ollama_host = ollama_host.rstrip('/')

    info(f"Testing Ollama at: {ollama_host}")

    try:
        import urllib.request
        import urllib.error

        # Test /api/tags endpoint
        url = f"{ollama_host}/api/tags"
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read().decode())
                models = [m.get('name', 'unknown') for m in data.get('models', [])]
                ok(f"Ollama responding at {url}")
                ok(f"Available models: {models}")
        except urllib.error.URLError as e:
            fail(f"Cannot connect to Ollama at {url}: {e}")
        except Exception as e:
            fail(f"Error querying Ollama: {e}")

    except ImportError:
        warn("urllib not available for connectivity test")


def check_model_loading():
    """Check if model can be loaded via archytas."""
    header("7. Model Loading Test")

    try:
        from beaker_kernel.lib.config import config

        provider = os.environ.get('LLM_SERVICE_PROVIDER', '')
        model = os.environ.get('LLM_SERVICE_MODEL', '')

        info(f"Provider: {provider}")
        info(f"Model: {model}")

        # Try to get the model class
        try:
            model_instance = config.get_model()
            ok(f"Model loaded successfully: {type(model_instance).__name__}")
        except Exception as e:
            fail(f"Failed to load model: {e}")

            # Check if it's the SSL error
            if 'SSL_CERT_FILE' in str(e) or 'ssl' in str(e).lower():
                warn("This appears to be an SSL certificate error")
                warn("Make sure SSL_CERT_FILE is set and the file exists in the container")

    except ImportError as e:
        fail(f"Cannot import beaker config: {e}")
    except Exception as e:
        fail(f"Error during model loading test: {e}")


def check_autodiscovery():
    """Check beaker autodiscovery."""
    header("8. Beaker Autodiscovery")

    try:
        from beaker_kernel.lib.autodiscovery import autodiscover

        for resource_type in ['contexts', 'subkernels']:
            try:
                items = autodiscover(resource_type)
                names = list(items.keys()) if hasattr(items, 'keys') else list(items)
                ok(f"autodiscover('{resource_type}'): {names}")
            except Exception as e:
                fail(f"autodiscover('{resource_type}') failed: {e}")

    except ImportError as e:
        fail(f"Cannot import autodiscovery: {e}")


def check_context_instantiation():
    """Test instantiating the context (without full kernel)."""
    header("9. Context Instantiation Test")

    try:
        from bdikit_context.context import BDIKitContext
        from bdikit_context.agent import BDIKitAgent

        # Check agent can be inspected
        ok("BDIKitContext and BDIKitAgent classes are available")

        # Check __init__ signature
        sig = inspect.signature(BDIKitContext.__init__)
        params = list(sig.parameters.keys())
        info(f"BDIKitContext.__init__ params: {params}")

        # Check agent tools exist as methods
        agent_methods = [m for m in dir(BDIKitAgent) if not m.startswith('_')]
        info(f"BDIKitAgent methods: {agent_methods[:10]}...")  # First 10

    except Exception as e:
        fail(f"Error testing context: {e}")


def main():
    print(f"\n{Colors.BOLD}Beaker Interactive Session Diagnostics{Colors.RESET}")
    print(f"Python: {sys.executable}")
    print(f"Version: {sys.version}")
    print(f"Working directory: {os.getcwd()}")

    check_environment_variables()
    check_entry_points()
    check_bdikit_context()
    check_tool_registration()
    check_beaker_config()
    check_ollama_connectivity()
    check_model_loading()
    check_autodiscovery()
    check_context_instantiation()

    header("Summary")
    print("If all checks pass but the context still fails to load in the UI,")
    print("the issue is likely in the Beaker kernel's runtime initialization.")
    print("\nCheck the server logs for specific error messages.")
    print("Common issues:")
    print("  - SSL certificate not found (bind mount the cert file)")
    print("  - Workflow YAML format errors (remove or fix workflow files)")
    print("  - Model connection timeouts (ensure Ollama is running)")


if __name__ == '__main__':
    main()
