#!/usr/bin/env python3
"""
Generate .env files from experiment configuration YAML files.

This script reads an experiment config and creates an associated .env file
with the appropriate LLM settings, based on the base .env file.

Usage:
    python generate_env.py --config path/to/config.yaml
    python generate_env.py --config-dir path/to/configs/  # Generate for all configs in directory
"""

import argparse
import re
import sys
from pathlib import Path

import yaml


def load_base_env(base_env_path: Path) -> str:
    """Load the base .env file content."""
    if not base_env_path.exists():
        raise FileNotFoundError(f"Base .env file not found: {base_env_path}")
    return base_env_path.read_text()


def load_experiment_config(config_path: Path) -> dict:
    """Load experiment configuration from YAML."""
    with open(config_path) as f:
        return yaml.safe_load(f)


def update_env_value(env_content: str, key: str, value: str) -> str:
    """Update or add an environment variable in .env content."""
    # Pattern to match the key (with optional comment prefix)
    pattern = rf'^(#\s*)?{re.escape(key)}=.*$'
    replacement = f'{key}={value}'

    # Check if key exists (commented or not)
    if re.search(pattern, env_content, re.MULTILINE):
        return re.sub(pattern, replacement, env_content, flags=re.MULTILINE)
    else:
        # Add at the end of LLM Provider Configuration section
        return env_content + f'\n{key}={value}\n'


def get_provider_import_path(provider: str) -> str:
    """Get the archytas import path for a provider."""
    # Map provider names to archytas model import paths
    provider_map = {
        'openai': 'archytas.models.openai.OpenAIModel',
        'openrouter': 'archytas.models.openrouter.OpenRouterModel',
        'anthropic': 'archytas.models.anthropic.AnthropicModel',
        'ollama': 'archytas.models.ollama.OllamaModel',
        'groq': 'archytas.models.groq.GroqModel',
        'gemini': 'archytas.models.gemini.GeminiModel',
        # anyllm providers use a custom path
        'anyllm:openrouter': 'bdikit_context.llm.anyllm.AnyLLMModel',
        'anyllm:ollama': 'bdikit_context.llm.anyllm.AnyLLMModel',
        'anyllm:openai': 'bdikit_context.llm.anyllm.AnyLLMModel',
        'anyllm:anthropic': 'bdikit_context.llm.anyllm.AnyLLMModel',
        'anyllm:groq': 'bdikit_context.llm.anyllm.AnyLLMModel',
        'anyllm:gemini': 'bdikit_context.llm.anyllm.AnyLLMModel',
    }
    return provider_map.get(provider, 'bdikit_context.llm.anyllm.AnyLLMModel')


def get_api_key_for_provider(provider: str, env_content: str) -> str:
    """Extract the appropriate API key from env content based on provider."""
    # Determine which API key to use based on provider
    if 'openrouter' in provider.lower():
        match = re.search(r'^OPENROUTER_API_KEY=(.+)$', env_content, re.MULTILINE)
    elif 'openai' in provider.lower():
        match = re.search(r'^OPENAI_API_KEY=(.+)$', env_content, re.MULTILINE)
    elif 'anthropic' in provider.lower():
        match = re.search(r'^ANTHROPIC_API_KEY=(.+)$', env_content, re.MULTILINE)
    elif 'groq' in provider.lower():
        match = re.search(r'^GROQ_API_KEY=(.+)$', env_content, re.MULTILINE)
    elif 'gemini' in provider.lower() or 'google' in provider.lower():
        match = re.search(r'^GOOGLE_API_KEY=(.+)$', env_content, re.MULTILINE)
    elif 'ollama' in provider.lower():
        # Ollama doesn't need an API key
        return ''
    else:
        match = None

    return match.group(1) if match else ''


def generate_env_from_config(config_path: Path, base_env_path: Path, output_dir: Path = None) -> Path:
    """
    Generate an .env file from an experiment configuration.

    Args:
        config_path: Path to the experiment config YAML
        base_env_path: Path to the base .env file to copy from
        output_dir: Directory to save the generated .env file (default: same as config)

    Returns:
        Path to the generated .env file
    """
    # Load base env and config
    env_content = load_base_env(base_env_path)
    config = load_experiment_config(config_path)

    # Extract LLM settings from config
    llm_config = config.get('llm', {})
    env_settings = config.get('env_settings', {})

    provider = llm_config.get('provider', env_settings.get('LLM_SERVICE_PROVIDER', 'openai'))
    model = llm_config.get('model', env_settings.get('LLM_SERVICE_MODEL', 'gpt-4o'))
    temperature = llm_config.get('temperature', env_settings.get('LLM_TEMPERATURE', 0.0))

    # Update env content with new values
    env_content = update_env_value(env_content, 'LLM_SERVICE_PROVIDER', provider)
    env_content = update_env_value(env_content, 'LLM_SERVICE_MODEL', model)
    env_content = update_env_value(env_content, 'LLM_TEMPERATURE', str(temperature))

    # Set the import path based on provider
    import_path = get_provider_import_path(provider)
    env_content = update_env_value(env_content, 'LLM_PROVIDER_IMPORT_PATH', import_path)

    # Set the service token based on provider
    api_key = get_api_key_for_provider(provider, env_content)
    if api_key:
        env_content = update_env_value(env_content, 'LLM_SERVICE_TOKEN', api_key)

    # Handle base_url and context_length for Ollama
    if 'ollama' in provider.lower():
        base_url = llm_config.get('base_url', 'http://localhost:11434')
        env_content = update_env_value(env_content, 'LLM_BASE_URL', base_url)

        context_length = llm_config.get('context_length')
        if context_length is not None:
            env_content = update_env_value(env_content, 'OLLAMA_CONTEXT_LENGTH', str(context_length))

    # Determine output path
    if output_dir is None:
        output_dir = config_path.parent

    # Generate output filename: config_name_associated.env
    config_name = config_path.stem  # filename without extension
    output_path = output_dir / f"{config_name}_associated.env"

    # Write the generated .env file
    output_path.write_text(env_content)

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate .env files from experiment configuration YAML files"
    )
    parser.add_argument(
        '--config', '-c',
        type=Path,
        help='Path to experiment configuration YAML file'
    )
    parser.add_argument(
        '--config-dir', '-d',
        type=Path,
        help='Directory containing experiment config files (generates .env for all)'
    )
    parser.add_argument(
        '--base-env', '-b',
        type=Path,
        default=Path(__file__).parent / '.env',
        help='Path to base .env file to copy from (default: .env in script directory)'
    )
    parser.add_argument(
        '--output-dir', '-o',
        type=Path,
        help='Output directory for generated .env files (default: same as config)'
    )

    args = parser.parse_args()

    if not args.config and not args.config_dir:
        parser.error("Either --config or --config-dir must be specified")

    configs_to_process = []

    if args.config:
        if not args.config.exists():
            print(f"Error: Config file not found: {args.config}")
            return 1
        configs_to_process.append(args.config)

    if args.config_dir:
        if not args.config_dir.exists():
            print(f"Error: Config directory not found: {args.config_dir}")
            return 1
        configs_to_process.extend(args.config_dir.glob('*.yaml'))
        configs_to_process.extend(args.config_dir.glob('*.yml'))

    if not configs_to_process:
        print("No config files found to process")
        return 1

    print(f"Generating .env files from {len(configs_to_process)} config(s)...")
    print(f"Base .env: {args.base_env}")

    for config_path in configs_to_process:
        try:
            output_path = generate_env_from_config(
                config_path,
                args.base_env,
                args.output_dir
            )
            print(f"  ✓ {config_path.name} -> {output_path.name}")
        except Exception as e:
            print(f"  ✗ {config_path.name}: {e}")

    print("\nDone!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
