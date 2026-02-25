"""
Configuration loading and validation for experiments.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
import yaml


@dataclass
class LLMConfig:
    """LLM configuration for an experiment."""
    provider: str
    model: str
    temperature: float = 0.0
    context_length: Optional[int] = None


@dataclass
class MessageConfig:
    """Configuration for a single message in the conversation."""
    content: str
    wait_seconds: int = 30
    decision_mode: Optional[str] = None  # auto_accept, predefined, llm_decides


@dataclass
class OutputConfig:
    """Output configuration for an experiment."""
    base_dir: str = "./results"
    save_artifacts: list[str] = field(default_factory=list)


@dataclass
class DecisionConfig:
    """Configuration for handling agent decision points."""
    default_mode: str = "auto_accept"
    predefined_responses: dict[str, str] = field(default_factory=dict)


@dataclass
class EvaluationConfig:
    """Evaluation configuration for metrics calculation."""
    gold_standard: Optional[str] = None
    input_file: Optional[str] = None
    gold_column_mapping: Optional[str] = None
    gold_value_mapping: Optional[str] = None
    acceptable_columns_file: Optional[str] = None
    column_mapping_file: str = "column_mapping.json"
    value_mapping_file: str = "value_mapping.json"
    index_column: Optional[str] = None
    numeric_tolerance: Optional[float] = None
    numeric_precision: Optional[int] = None


@dataclass
class PromptsConfig:
    """Configuration for custom prompt overrides per experiment.

    All fields are optional. When None, the default prompts are used.
    Paths can be absolute or relative to prompts_base_dir.
    """
    prompts_base_dir: Optional[str] = None
    system_prompt_dir: Optional[str] = None
    react_prelude: Optional[str] = None
    code_context_prompt: Optional[str] = None
    codeact_prompt: Optional[str] = None
    tool_prompts_dir: Optional[str] = None


@dataclass
class ExperimentConfig:
    """Complete experiment configuration."""
    name: str
    description: str
    llm: LLMConfig
    messages: list[MessageConfig]
    output: OutputConfig = field(default_factory=OutputConfig)
    decision_handling: DecisionConfig = field(default_factory=DecisionConfig)
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)
    prompts: PromptsConfig = field(default_factory=PromptsConfig)
    # Manual mode: if True, this config is for manual experiments (no automated messages)
    manual_mode: bool = False
    # Optional reference to dataset metadata
    dataset_metadata: Optional[str] = None
    # Beaker context to use: "bdikit_context", "code_context", or "codeact_context"
    context: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentConfig":
        """Create ExperimentConfig from dictionary."""
        exp = data.get("experiment", {})
        llm_data = data.get("llm", {})
        messages_data = data.get("messages", [])
        output_data = data.get("output", {})
        decision_data = data.get("decision_handling", {})
        evaluation_data = data.get("evaluation", {})
        prompts_data = data.get("prompts", {})

        llm = LLMConfig(
            provider=llm_data.get("provider", "openai"),
            model=llm_data.get("model", "gpt-4o"),
            temperature=llm_data.get("temperature", 0.0),
            context_length=llm_data.get("context_length"),
        )

        messages = [
            MessageConfig(
                content=m.get("content", ""),
                wait_seconds=m.get("wait_seconds", 30),
                decision_mode=m.get("decision_mode"),
            )
            for m in messages_data
        ]

        output = OutputConfig(
            base_dir=output_data.get("base_dir", "./results"),
            save_artifacts=output_data.get("save_artifacts", []),
        )

        decision = DecisionConfig(
            default_mode=decision_data.get("default_mode", "auto_accept"),
            predefined_responses=decision_data.get("predefined_responses", {}),
        )

        evaluation = EvaluationConfig(
            gold_standard=evaluation_data.get("gold_standard"),
            input_file=evaluation_data.get("input_file"),
            gold_column_mapping=evaluation_data.get("gold_column_mapping"),
            gold_value_mapping=evaluation_data.get("gold_value_mapping"),
            acceptable_columns_file=evaluation_data.get("acceptable_columns_file"),
            column_mapping_file=evaluation_data.get("column_mapping_file", "column_mapping.json"),
            value_mapping_file=evaluation_data.get("value_mapping_file", "value_mapping.json"),
            index_column=evaluation_data.get("index_column"),
            numeric_tolerance=evaluation_data.get("numeric_tolerance"),
            numeric_precision=evaluation_data.get("numeric_precision"),
        )

        # Determine manual mode: explicit flag or no messages defined
        manual_mode = exp.get("manual_mode", len(messages) == 0)

        prompts = PromptsConfig(**prompts_data) if prompts_data else PromptsConfig()

        return cls(
            name=exp.get("name", "unnamed_experiment"),
            description=exp.get("description", ""),
            llm=llm,
            messages=messages,
            output=output,
            decision_handling=decision,
            evaluation=evaluation,
            prompts=prompts,
            manual_mode=manual_mode,
            dataset_metadata=exp.get("dataset_metadata"),
            context=exp.get("context"),
        )


def load_config(config_path: str | Path) -> ExperimentConfig:
    """Load experiment configuration from YAML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    return ExperimentConfig.from_dict(data)


def load_conversation(conversation_path: str | Path) -> list[MessageConfig]:
    """Load a reusable conversation script from YAML."""
    path = Path(conversation_path)
    if not path.exists():
        raise FileNotFoundError(f"Conversation file not found: {path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    messages = data.get("messages", [])
    return [
        MessageConfig(
            content=m.get("content", ""),
            wait_seconds=m.get("wait_seconds", 30),
            decision_mode=m.get("decision_mode"),
        )
        for m in messages
    ]
