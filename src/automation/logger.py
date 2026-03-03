"""
Logging utilities for experiment traces and conversation outputs.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class TurnRecord:
    """Record of a single conversation turn."""
    turn: int
    user_message: str
    agent_response: str
    response_type: str
    tool_calls: list[dict] = field(default_factory=list)
    duration_seconds: float = 0.0
    raw_messages: list[dict] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class ExperimentTrace:
    """Complete trace of an experiment run."""
    experiment_name: str
    description: str
    llm_provider: str
    llm_model: str
    start_time: str
    end_time: Optional[str] = None
    turns: list[TurnRecord] = field(default_factory=list)
    total_duration_seconds: float = 0.0
    status: str = "running"  # running, completed, failed, timeout
    error_message: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "experiment": {
                "name": self.experiment_name,
                "description": self.description,
            },
            "llm": {
                "provider": self.llm_provider,
                "model": self.llm_model,
            },
            "timing": {
                "start_time": self.start_time,
                "end_time": self.end_time,
                "total_duration_seconds": self.total_duration_seconds,
            },
            "status": self.status,
            "error_message": self.error_message,
            "turns": [asdict(t) for t in self.turns],
        }


class TraceLogger:
    """Logger for full experiment traces in JSON format."""

    def __init__(self, output_dir: Path):
        """
        Initialize trace logger.

        Args:
            output_dir: Directory to write trace files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.trace: Optional[ExperimentTrace] = None

    def start_experiment(
        self,
        experiment_name: str,
        description: str,
        llm_provider: str,
        llm_model: str,
    ) -> None:
        """Start tracking a new experiment."""
        self.trace = ExperimentTrace(
            experiment_name=experiment_name,
            description=description,
            llm_provider=llm_provider,
            llm_model=llm_model,
            start_time=datetime.utcnow().isoformat(),
        )

    def log_turn(
        self,
        turn: int,
        user_message: str,
        agent_response: str,
        response_type: str,
        tool_calls: list[dict] = None,
        duration_seconds: float = 0.0,
        raw_messages: list[dict] = None,
    ) -> None:
        """Log a conversation turn."""
        if self.trace is None:
            raise RuntimeError("Experiment not started. Call start_experiment first.")

        record = TurnRecord(
            turn=turn,
            user_message=user_message,
            agent_response=agent_response,
            response_type=response_type,
            tool_calls=tool_calls or [],
            duration_seconds=duration_seconds,
            raw_messages=raw_messages or [],
        )
        self.trace.turns.append(record)

    def end_experiment(
        self,
        status: str = "completed",
        error_message: Optional[str] = None,
    ) -> None:
        """Mark experiment as complete."""
        if self.trace is None:
            return

        self.trace.end_time = datetime.utcnow().isoformat()
        self.trace.status = status
        self.trace.error_message = error_message

        # Calculate total duration
        total = sum(t.duration_seconds for t in self.trace.turns)
        self.trace.total_duration_seconds = total

    def save(self, filename: str = "trace.json") -> Path:
        """Save trace to JSON file."""
        if self.trace is None:
            raise RuntimeError("No trace to save.")

        output_path = self.output_dir / filename
        with open(output_path, "w") as f:
            json.dump(self.trace.to_dict(), f, indent=2)

        return output_path

    def build_notebook_cells(self) -> list[dict]:
        """Convert conversation trace to notebook cell format for Beaker UI."""
        if self.trace is None:
            return []

        cells = []

        # Header cell with experiment info
        trace_dict = self.trace.to_dict()
        cells.append({
            "cell_type": "markdown",
            "metadata": {},
            "source": (
                f"# {trace_dict['experiment'].get('name', 'Experiment')}\n\n"
                f"**Description**: {trace_dict['experiment'].get('description', '')}\n"
                f"**LLM**: {trace_dict['llm'].get('provider', '')}/{trace_dict['llm'].get('model', '')}\n"
                f"**Started**: {trace_dict['timing'].get('start_time', '')}"
            )
        })

        for turn in self.trace.turns:
            # User message cell
            cells.append({
                "cell_type": "markdown",
                "metadata": {"beaker_cell_type": "user_message"},
                "source": f"**User (Turn {turn.turn}):**\n\n{turn.user_message}"
            })

            # Agent response cell
            if turn.response_type == "code_cell":
                cells.append({
                    "cell_type": "code",
                    "metadata": {"beaker_cell_type": "agent_code"},
                    "source": turn.agent_response,
                    "outputs": [],
                    "execution_count": None,
                })
            else:
                cells.append({
                    "cell_type": "markdown",
                    "metadata": {"beaker_cell_type": "agent_response"},
                    "source": f"**Agent ({turn.response_type}):**\n\n{turn.agent_response}"
                })

        return cells


class ConversationLogger:
    """Logger for simplified conversation output in Markdown format."""

    def __init__(self, output_dir: Path):
        """
        Initialize conversation logger.

        Args:
            output_dir: Directory to write conversation files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.lines: list[str] = []
        self.experiment_name: Optional[str] = None
        self.llm_info: Optional[str] = None

    def start_experiment(
        self,
        experiment_name: str,
        description: str,
        llm_provider: str,
        llm_model: str,
    ) -> None:
        """Start a new conversation log."""
        self.experiment_name = experiment_name
        self.llm_info = f"{llm_provider}/{llm_model}"
        self.lines = [
            f"# Experiment: {experiment_name}",
            "",
            f"**Description**: {description}",
            f"**LLM**: {self.llm_info}",
            f"**Date**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "",
            "---",
            "",
        ]

    def log_turn(
        self,
        turn: int,
        user_message: str,
        agent_response: str,
        response_type: str = "llm_response",
    ) -> None:
        """Log a conversation turn."""
        self.lines.extend([
            f"## Turn {turn}",
            "",
            f"**User**: {user_message}",
            "",
            f"**Agent** ({response_type}):",
            "",
            agent_response,
            "",
            "---",
            "",
        ])

    def log_error(self, error_message: str) -> None:
        """Log an error."""
        self.lines.extend([
            "## Error",
            "",
            "```",
            error_message,
            "```",
            "",
        ])

    def log_summary(
        self,
        total_turns: int,
        total_duration: float,
        status: str,
    ) -> None:
        """Log experiment summary."""
        self.lines.extend([
            "## Summary",
            "",
            f"- **Total turns**: {total_turns}",
            f"- **Total duration**: {total_duration:.2f} seconds",
            f"- **Status**: {status}",
            "",
        ])

    def save(self, filename: str = "conversation.md") -> Path:
        """Save conversation to Markdown file."""
        output_path = self.output_dir / filename
        with open(output_path, "w") as f:
            f.write("\n".join(self.lines))

        return output_path

    def get_content(self) -> str:
        """Get current conversation content as string."""
        return "\n".join(self.lines)
