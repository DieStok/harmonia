"""
Experiment runner for automated Beaker experiments.
"""

import asyncio
import re
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .client import AgentResponse, BeakerClient
from .config import DecisionConfig, ExperimentConfig, MessageConfig
from .logger import ConversationLogger, TraceLogger


class ExperimentRunner:
    """Runner for executing scripted experiments with Beaker agent."""

    def __init__(
        self,
        client: BeakerClient,
        config: ExperimentConfig,
        output_dir: Optional[Path] = None,
        on_turn_complete: Optional[Callable[[int, str, AgentResponse], None]] = None,
    ):
        """
        Initialize experiment runner.

        Args:
            client: Connected BeakerClient instance
            config: Experiment configuration
            output_dir: Override output directory (default from config)
            on_turn_complete: Optional callback after each turn
        """
        self.client = client
        self.config = config
        self.on_turn_complete = on_turn_complete

        # Set up output directory
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        base_dir = Path(output_dir or config.output.base_dir)
        self.output_dir = base_dir / f"{config.name}_{timestamp}"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize loggers
        self.trace_logger = TraceLogger(self.output_dir)
        self.conversation_logger = ConversationLogger(self.output_dir)

        # State
        self.current_turn = 0
        self.is_running = False

    async def run(self, interactive: bool = False) -> Path:
        """
        Run the complete experiment.

        Args:
            interactive: If True, pause between turns for manual inspection

        Returns:
            Path to output directory with results
        """
        self.is_running = True

        # Start logging
        self.trace_logger.start_experiment(
            experiment_name=self.config.name,
            description=self.config.description,
            llm_provider=self.config.llm.provider,
            llm_model=self.config.llm.model,
        )
        self.conversation_logger.start_experiment(
            experiment_name=self.config.name,
            description=self.config.description,
            llm_provider=self.config.llm.provider,
            llm_model=self.config.llm.model,
        )

        status = "completed"
        error_message = None

        try:
            for msg_config in self.config.messages:
                if not self.is_running:
                    status = "cancelled"
                    break

                await self._run_turn(msg_config)

                if interactive:
                    # Pause for interactive mode
                    print(f"\n[Turn {self.current_turn} complete. Press Enter to continue...]")
                    await asyncio.get_event_loop().run_in_executor(None, input)

        except asyncio.CancelledError:
            status = "cancelled"
        except asyncio.TimeoutError as e:
            status = "timeout"
            error_message = str(e)
        except Exception as e:
            status = "failed"
            error_message = str(e)
            self.conversation_logger.log_error(error_message)

        # Finalize logging
        self.trace_logger.end_experiment(status=status, error_message=error_message)
        self.conversation_logger.log_summary(
            total_turns=self.current_turn,
            total_duration=self.trace_logger.trace.total_duration_seconds,
            status=status,
        )

        # Save outputs
        self.trace_logger.save()
        self.conversation_logger.save()

        self.is_running = False
        return self.output_dir

    async def _run_turn(self, msg_config: MessageConfig) -> AgentResponse:
        """Run a single conversation turn."""
        self.current_turn += 1

        # Send message and get response
        response = await self.client.send_message(
            msg_config.content,
            timeout=float(msg_config.wait_seconds),
        )

        # Handle decision points if needed
        if self._is_decision_point(response):
            response = await self._handle_decision(response, msg_config)

        # Log the turn
        self.trace_logger.log_turn(
            turn=self.current_turn,
            user_message=msg_config.content,
            agent_response=response.content,
            response_type=response.response_type,
            tool_calls=response.tool_calls,
            duration_seconds=response.duration_seconds,
            raw_messages=response.raw_messages,
        )
        self.conversation_logger.log_turn(
            turn=self.current_turn,
            user_message=msg_config.content,
            agent_response=response.content,
            response_type=response.response_type,
        )

        # Call callback if provided
        if self.on_turn_complete:
            self.on_turn_complete(self.current_turn, msg_config.content, response)

        # Wait between turns
        if msg_config.wait_seconds > 0:
            await asyncio.sleep(1)  # Small delay between turns

        return response

    def _is_decision_point(self, response: AgentResponse) -> bool:
        """Check if response requires a decision from user."""
        # Look for common decision indicators in response
        decision_patterns = [
            r"please choose",
            r"select.*option",
            r"which.*would you prefer",
            r"option \d+:",
            r"\d+\)",
            r"alternative.*:",
        ]
        content_lower = response.content.lower()
        return any(re.search(p, content_lower) for p in decision_patterns)

    async def _handle_decision(
        self, response: AgentResponse, msg_config: MessageConfig
    ) -> AgentResponse:
        """Handle a decision point based on configuration."""
        # Determine decision mode
        decision_mode = (
            msg_config.decision_mode or self.config.decision_handling.default_mode
        )

        if decision_mode == "auto_accept":
            # Accept first option or continue
            decision = "Please proceed with the first option."

        elif decision_mode == "predefined":
            # Match against predefined responses
            decision = self._find_predefined_response(response.content)
            if not decision:
                decision = "Please proceed with the recommended option."

        elif decision_mode == "llm_decides":
            # Ask LLM to pick (this will be another turn)
            decision = "Please pick the best option based on the data."

        else:
            decision = "Please continue."

        # Send the decision
        decision_response = await self.client.send_message(decision, timeout=60.0)

        # Log the decision as an additional turn
        self.current_turn += 1
        self.trace_logger.log_turn(
            turn=self.current_turn,
            user_message=f"[AUTO-DECISION: {decision_mode}] {decision}",
            agent_response=decision_response.content,
            response_type=decision_response.response_type,
            duration_seconds=decision_response.duration_seconds,
        )
        self.conversation_logger.log_turn(
            turn=self.current_turn,
            user_message=f"[AUTO-DECISION] {decision}",
            agent_response=decision_response.content,
        )

        return decision_response

    def _find_predefined_response(self, agent_content: str) -> Optional[str]:
        """Find a predefined response matching the agent's question."""
        content_lower = agent_content.lower()

        for pattern, response in self.config.decision_handling.predefined_responses.items():
            if re.search(pattern, content_lower):
                return response

        return None

    def stop(self) -> None:
        """Stop the running experiment."""
        self.is_running = False


async def run_single_message(
    client: BeakerClient,
    message: str,
    timeout: float = 60.0,
) -> AgentResponse:
    """
    Send a single message to the agent (utility for interactive testing).

    Args:
        client: Connected BeakerClient
        message: Message to send
        timeout: Response timeout

    Returns:
        AgentResponse with the result
    """
    return await client.send_message(message, timeout=timeout)
