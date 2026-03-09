"""
Experiment runner for automated Beaker experiments.
"""

import asyncio
import os
import re
import shutil
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import yaml

from .client import AgentResponse, BeakerClient
from .config import ExperimentConfig, MessageConfig
from .logger import ConversationLogger, TraceLogger
from .tracing import (
    calculate_turn_cost,
    experiment_span,
    extract_code_executions,
    extract_usage_records,
    init_tracing,
    llm_call_span,
    set_llm_usage,
    tool_span,
    turn_span,
)


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

        # Set up output directory (includes RUN_ID if available from environment)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        self.run_id = os.environ.get("RUN_ID", "")
        base_dir = Path(output_dir or config.output.base_dir)
        if self.run_id:
            self.output_dir = base_dir / f"{config.name}_{timestamp}_{self.run_id}"
        else:
            self.output_dir = base_dir / f"{config.name}_{timestamp}"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize loggers
        self.trace_logger = TraceLogger(self.output_dir)
        self.conversation_logger = ConversationLogger(self.output_dir)

        # Snapshot config to trace logger and results directory
        try:
            config_dict = asdict(config)
            self.trace_logger.trace_config_snapshot = config_dict
        except Exception:
            pass

        if config.config_source_path:
            try:
                shutil.copy2(config.config_source_path, self.output_dir / "config_snapshot.yaml")
            except Exception:
                # Fallback: serialize config to YAML
                try:
                    config_dict = asdict(config)
                    with open(self.output_dir / "config_snapshot.yaml", "w") as f:
                        yaml.dump(config_dict, f, default_flow_style=False)
                except Exception:
                    pass

        # Initialize tracing
        self.tracer = None
        self.tracing_active = False
        if config.tracing.enabled:
            self.tracer, self.tracing_active = init_tracing(
                phoenix_endpoint=config.tracing.phoenix_endpoint,
                run_id=self.run_id,
                experiment_name=config.name,
            )

        # State
        self.current_turn = 0
        self.is_running = False
        self.notebook_id: Optional[str] = None

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
            run_id=self.run_id or None,
        )
        # Attach config snapshot to trace
        if hasattr(self.trace_logger, 'trace') and self.trace_logger.trace:
            try:
                self.trace_logger.trace.config_snapshot = asdict(self.config)
            except Exception:
                pass

        self.conversation_logger.start_experiment(
            experiment_name=self.config.name,
            description=self.config.description,
            llm_provider=self.config.llm.provider,
            llm_model=self.config.llm.model,
        )

        # Create initial notebook on server for UI visibility
        try:
            cells = self.trace_logger.build_notebook_cells()
            notebook_info = await self.client.save_notebook(cells, name=self.config.name)
            self.notebook_id = notebook_info.get("id")
        except Exception as e:
            print(f"  Warning: Could not create initial notebook: {e}")

        # Set up kernel working directory for output files
        await self._setup_kernel_working_directory()

        status = "completed"
        error_message = None

        # Wrap experiment in root tracing span
        if self.tracing_active and self.tracer:
            with experiment_span(
                self.tracer,
                self.config,
                self.run_id,
            ) as root_span:
                status, error_message = await self._run_experiment_loop(interactive)
                if error_message:
                    from opentelemetry.trace import StatusCode
                    root_span.set_status(StatusCode.ERROR, error_message)
        else:
            status, error_message = await self._run_experiment_loop(interactive)

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

        # Final notebook save with completion status
        try:
            cells = self.trace_logger.build_notebook_cells()
            # Add completion cell
            cells.append({
                "cell_type": "markdown",
                "metadata": {},
                "source": f"---\n\n**Experiment {status}** in {self.trace_logger.trace.total_duration_seconds:.1f}s"
            })
            await self.client.save_notebook(cells, name=self.config.name)
        except Exception as e:
            print(f"  Warning: Could not save final notebook: {e}")

        self.is_running = False
        return self.output_dir

    async def _run_experiment_loop(self, interactive: bool) -> tuple[str, Optional[str]]:
        """Run the main experiment message loop. Returns (status, error_message)."""
        status = "completed"
        error_message = None

        try:
            for msg_config in self.config.messages:
                if not self.is_running:
                    status = "cancelled"
                    break

                await self._run_turn(msg_config)

                if interactive:
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

        return status, error_message

    async def _run_turn(self, msg_config: MessageConfig) -> AgentResponse:
        """Run a single conversation turn."""
        self.current_turn += 1
        main_turn = self.current_turn

        # Wrap turn in tracing span
        if self.tracing_active and self.tracer:
            with turn_span(self.tracer, main_turn, msg_config.content) as t_span:
                response = await self._run_turn_inner(msg_config, main_turn, t_span)
        else:
            response = await self._run_turn_inner(msg_config, main_turn, None)

        return response

    async def _run_turn_inner(
        self, msg_config: MessageConfig, main_turn: int, t_span
    ) -> AgentResponse:
        """Inner turn logic with tracing support."""
        # Send message and get response
        response = await self._send_with_retries(
            msg_config.content,
            timeout=float(msg_config.wait_seconds),
        )

        # Extract token usage and code executions from raw messages
        usage_records = extract_usage_records(response.raw_messages)
        code_execs = extract_code_executions(response.raw_messages)

        # Calculate aggregated token counts and cost
        pricing_prompt = self.config.model_metadata.pricing_prompt_per_million_tokens
        pricing_completion = self.config.model_metadata.pricing_completion_per_million_tokens
        input_tokens, output_tokens, cost_usd = calculate_turn_cost(
            usage_records, pricing_prompt, pricing_completion
        )

        # Create child LLM spans for each usage record
        if self.tracing_active and self.tracer:
            for i, usage in enumerate(usage_records):
                with llm_call_span(self.tracer, i, self.config.llm.model) as lspan:
                    set_llm_usage(lspan, usage, pricing_prompt, pricing_completion)

            # Create child TOOL spans for each code execution
            for exec_data in code_execs:
                with tool_span(self.tracer, "beaker_execute", exec_data.get("code", "")) as tspan:
                    if tspan is not None:
                        tspan.set_attribute("output.value", exec_data.get("stdout", ""))
                        tspan.set_attribute("tool.status", exec_data.get("status", "unknown"))

            # Set turn span output
            if t_span is not None:
                t_span.set_attribute("output.value", response.content)
                t_span.set_attribute("harmonia.response_type", response.response_type)
                t_span.set_attribute("harmonia.duration_seconds", response.duration_seconds)

        # Log the primary turn response
        self.trace_logger.log_turn(
            turn=main_turn,
            user_message=msg_config.content,
            agent_response=response.content,
            response_type=response.response_type,
            tool_calls=response.tool_calls,
            duration_seconds=response.duration_seconds,
            raw_messages=response.raw_messages,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            code_executions=code_execs,
            usage_records=usage_records,
        )
        self.conversation_logger.log_turn(
            turn=main_turn,
            user_message=msg_config.content,
            agent_response=response.content,
            response_type=response.response_type,
        )

        # Handle decision points as a distinct follow-up turn
        if self._is_decision_point(response):
            decision_response, decision_mode, decision = await self._handle_decision(
                response, msg_config
            )
            self.current_turn += 1
            decision_turn = self.current_turn

            # Extract usage for decision turn too
            decision_usage = extract_usage_records(decision_response.raw_messages)
            decision_code_execs = extract_code_executions(decision_response.raw_messages)
            d_input, d_output, d_cost = calculate_turn_cost(
                decision_usage, pricing_prompt, pricing_completion
            )

            self.trace_logger.log_turn(
                turn=decision_turn,
                user_message=f"[AUTO-DECISION: {decision_mode}] {decision}",
                agent_response=decision_response.content,
                response_type=decision_response.response_type,
                tool_calls=decision_response.tool_calls,
                duration_seconds=decision_response.duration_seconds,
                raw_messages=decision_response.raw_messages,
                input_tokens=d_input,
                output_tokens=d_output,
                cost_usd=d_cost,
                code_executions=decision_code_execs,
                usage_records=decision_usage,
            )
            self.conversation_logger.log_turn(
                turn=decision_turn,
                user_message=f"[AUTO-DECISION] {decision}",
                agent_response=decision_response.content,
                response_type=decision_response.response_type,
            )
            response = decision_response

        # Call callback if provided
        if self.on_turn_complete:
            self.on_turn_complete(self.current_turn, msg_config.content, response)

        # Save updated notebook to server for real-time UI visibility
        try:
            cells = self.trace_logger.build_notebook_cells()
            await self.client.save_notebook(cells, name=self.config.name)
        except Exception:
            pass  # Don't fail experiment if notebook save fails

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
    ) -> tuple[AgentResponse, str, str]:
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
        decision_response = await self._send_with_retries(decision, timeout=60.0)
        return decision_response, decision_mode, decision

    def _retry_budget_for_error(self, error_code: str) -> int:
        policy = self.config.retry_policy.n_retries_per_error_code
        if error_code in policy:
            return policy[error_code]
        if error_code.startswith("openrouter_"):
            suffix = error_code.replace("openrouter_", "", 1)
            if suffix.isdigit():
                bucket = f"{suffix[0]}xx"
                if f"openrouter_{bucket}" in policy:
                    return policy[f"openrouter_{bucket}"]
                if bucket in policy:
                    return policy[bucket]
        return policy.get("default", 0)

    def _classify_retryable_error(self, response: AgentResponse) -> Optional[str]:
        text = (response.content or "").strip()
        if response.response_type == "timeout":
            return "timeout"
        if response.response_type != "llm_response" or not text:
            return None
        m = re.search(r"Error from OpenRouter:.*'code':\s*(\d+)", text, re.DOTALL)
        if m:
            return f"openrouter_{m.group(1)}"
        if "validation errors for AIMessage" in text:
            return "aimessage_validation_error"
        if "Internal Server Error" in text and "OpenRouter" in text:
            return "openrouter_500"
        return None

    async def _send_with_retries(self, message: str, timeout: float) -> AgentResponse:
        attempt = 0
        while True:
            response = await self.client.send_message(message, timeout=timeout)
            error_code = self._classify_retryable_error(response)
            if not error_code:
                return response
            budget = self._retry_budget_for_error(error_code)
            if attempt >= budget:
                return response
            attempt += 1
            delay = max(self.config.retry_policy.retry_delay_seconds, 0.0) * attempt
            print(
                f"  \u21bb Retrying turn after {error_code} "
                f"({attempt}/{budget}) in {delay:.1f}s"
            )

            # Create retry span for tracing
            if self.tracing_active and self.tracer:
                with llm_call_span(self.tracer, attempt, self.config.llm.model) as rspan:
                    if rspan is not None:
                        from opentelemetry.trace import StatusCode
                        rspan.set_status(StatusCode.ERROR, error_code)
                        rspan.set_attribute("harmonia.error_code", error_code)
                        rspan.set_attribute("harmonia.retry_attempt", attempt)
                        rspan.set_attribute("harmonia.retry_delay_seconds", delay)

            await asyncio.sleep(delay)

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

    async def _setup_kernel_working_directory(self) -> None:
        """Set up the kernel working directory to save output files to results folder.

        This executes code in the kernel to:
        1. Change to the output directory
        2. Copy input data files to results directory for easy access
        3. Store paths for data access
        """
        # Get absolute path for output directory
        output_path = str(self.output_dir.absolute())

        # Data files to copy (configurable via output.input_files)
        data_files = self.config.output.input_files

        setup_code = f'''
import os
import shutil

# Store original working directory for data access
_original_cwd = os.getcwd()
_data_dir = _original_cwd

# Create and change to results directory for output files
os.makedirs("{output_path}", exist_ok=True)

# Copy input data files to results directory
data_files = {data_files}
for filename in data_files:
    src = os.path.join(_data_dir, filename)
    if os.path.exists(src):
        dst = os.path.join("{output_path}", filename)
        if not os.path.exists(dst):
            shutil.copy2(src, dst)
            print(f"Copied {{filename}} to results directory")

os.chdir("{output_path}")

# Make original data directory accessible via import path
import sys
if _data_dir not in sys.path:
    sys.path.insert(0, _data_dir)

print(f"Working directory set to: {{os.getcwd()}}")
print(f"Data directory: {{_data_dir}}")
'''
        try:
            result = await self.client.execute_code(setup_code, timeout=30.0)
            if result["status"] == "ok":
                print(f"  Kernel working directory: {output_path}")
                if result.get("output"):
                    for line in result["output"].strip().split("\n"):
                        if line:
                            print(f"  {line}")
            else:
                print(f"  Warning: Could not set working directory: {result.get('error', 'Unknown error')}")
        except Exception as e:
            print(f"  Warning: Failed to set kernel working directory: {e}")


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
