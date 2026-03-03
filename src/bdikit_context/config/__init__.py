"""
Harmonia configuration management.

Configuration priority (highest to lowest):
1. Environment variables
2. Config file (config.yaml)
3. Default values
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

# Optional YAML support (graceful fallback if not installed)
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


@dataclass
class ContainerLLMConfig:
    """
    LLM provider configuration.

    Supports litellm unified providers: "openrouter", "ollama", "litellm:openrouter", etc.
    """
    provider: str = "openai"
    model: str = "gpt-4o"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.0
    max_tokens: int = 4096
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HarmoniaConfig:
    """Main Harmonia configuration."""
    llm: ContainerLLMConfig = field(default_factory=ContainerLLMConfig)
    prompts_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent / "prompts")
    debug: bool = True

    @classmethod
    def from_env(cls) -> "HarmoniaConfig":
        """Load configuration from environment variables."""
        provider = os.getenv("LLM_SERVICE_PROVIDER", "openai").lower()

        # Extract actual provider for API key lookup (handle litellm: prefix)
        if ":" in provider:
            actual_provider = provider.split(":", 1)[1]
        else:
            actual_provider = provider

        api_key_map = {
            "openai": os.getenv("OPENAI_API_KEY"),
            "openrouter": os.getenv("OPENROUTER_API_KEY"),
            "anthropic": os.getenv("ANTHROPIC_API_KEY"),
            "ollama": None,  # No API key needed
            "groq": os.getenv("GROQ_API_KEY"),
            "gemini": os.getenv("GOOGLE_API_KEY"),
            "azure": os.getenv("AZURE_OPENAI_API_KEY"),
            "bedrock": os.getenv("AWS_ACCESS_KEY_ID"),
            "mistral": os.getenv("MISTRAL_API_KEY"),
            "together": os.getenv("TOGETHER_API_KEY"),
            "cohere": os.getenv("COHERE_API_KEY"),
            "deepseek": os.getenv("DEEPSEEK_API_KEY"),
            "fireworks": os.getenv("FIREWORKS_API_KEY"),
        }

        api_key = os.getenv("LLM_SERVICE_TOKEN") or api_key_map.get(actual_provider)

        return cls(
            llm=ContainerLLMConfig(
                provider=provider,
                model=os.getenv("LLM_SERVICE_MODEL", "gpt-4o"),
                api_key=api_key,
                base_url=os.getenv("LLM_BASE_URL"),
                temperature=float(os.getenv("LLM_TEMPERATURE", "0.0")),
                max_tokens=int(os.getenv("LLM_MAX_TOKENS", "4096")),
            ),
            debug=os.getenv("DEBUG", "1") == "1",
        )

    @classmethod
    def from_yaml(cls, path: Path) -> "HarmoniaConfig":
        """Load configuration from YAML file."""
        if not YAML_AVAILABLE:
            raise ImportError("PyYAML not installed. Install with: pip install pyyaml")

        if not path.exists():
            return cls.from_env()

        with open(path) as f:
            data = yaml.safe_load(f) or {}

        llm_data = data.get("llm", {})
        provider = llm_data.get("provider", "openai")

        # Extract actual provider for API key lookup (handle litellm: prefix)
        if ":" in provider.lower():
            actual_provider = provider.lower().split(":", 1)[1]
        else:
            actual_provider = provider.lower()

        # Environment variables override YAML for API keys (security)
        api_key = (
            os.getenv("LLM_SERVICE_TOKEN") or
            os.getenv(f"{actual_provider.upper()}_API_KEY") or
            llm_data.get("api_key")
        )

        return cls(
            llm=ContainerLLMConfig(
                provider=provider,
                model=llm_data.get("model", "gpt-4o"),
                api_key=api_key,
                base_url=llm_data.get("base_url"),
                temperature=llm_data.get("temperature", 0.0),
                max_tokens=llm_data.get("max_tokens", 4096),
                extra=llm_data.get("extra", {}),
            ),
            prompts_dir=Path(data.get("prompts_dir", cls.prompts_dir)),
            debug=data.get("debug", True),
        )


# Global config instance
_config: Optional[HarmoniaConfig] = None


def get_config() -> HarmoniaConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        config_path = Path(os.getenv("HARMONIA_CONFIG", "config.yaml"))
        if config_path.exists() and YAML_AVAILABLE:
            _config = HarmoniaConfig.from_yaml(config_path)
        else:
            _config = HarmoniaConfig.from_env()
    return _config


def reset_config():
    """Reset config (useful for testing)."""
    global _config
    _config = None
