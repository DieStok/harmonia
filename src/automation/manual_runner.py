"""
Manual experiment runner that monitors Beaker sessions and logs interactions.

This runner connects to a running Beaker server and passively monitors all
WebSocket traffic, logging user messages and agent responses to trace.json
and conversation.md files - just like automated experiments.

Usage:
    # Start Beaker server first:
    ./exec_apptainer_harmonia.sh --config configs/manual/dou_harmonization_manual_devstral.yaml

    # In another terminal, start the monitor:
    python run_manual_experiment.py --config configs/manual/dou_harmonization_manual_devstral.yaml

    # Interact with Beaker via the web UI
    # When done, press Ctrl+C to stop monitoring and save logs
"""

import asyncio
import os
import shutil
import signal
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiohttp
import yaml

from .config import ExperimentConfig, load_config
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


class ManualExperimentRunner:
    """
    Runner that monitors a Beaker session and logs all interactions.

    Unlike ExperimentRunner which sends automated messages, this runner
    passively observes the WebSocket traffic and logs whatever the user
    does interactively via the Beaker web UI.
    """

    def __init__(
        self,
        server_url: str,
        token: str,
        config: ExperimentConfig,
        output_dir: Optional[Path] = None,
    ):
        """
        Initialize manual experiment runner.

        Args:
            server_url: Base URL of Beaker server (e.g., "http://localhost:8100")
            token: Jupyter authentication token
            config: Experiment configuration (for metadata)
            output_dir: Override output directory (default from config)
        """
        self.server_url = server_url.rstrip("/")
        self.token = token
        self.config = config

        # Set up output directory
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

        # Snapshot config to results directory
        if config.config_source_path:
            try:
                shutil.copy2(config.config_source_path, self.output_dir / "config_snapshot.yaml")
            except Exception:
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
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.kernel_id: Optional[str] = None
        self.is_running = False
        self.current_turn = 0

        # Track pending requests (msg_id -> user_message)
        self._pending_requests: dict[str, dict] = {}

        # Root span reference (for manual cleanup)
        self._root_span = None
        self._root_span_ctx = None

    async def start(self) -> None:
        """
        Start monitoring the Beaker session.

        This connects to the WebSocket and begins logging all interactions.
        Call stop() or press Ctrl+C to end monitoring and save logs.
        """
        self.is_running = True

        # Initialize loggers
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

        # Connect to server
        self.session = aiohttp.ClientSession(
            headers={"Authorization": f"token {self.token}"}
        )

        # Get existing session/kernel
        await self._connect_to_kernel()

        print(f"\n{'='*60}")
        print("Manual Experiment Monitor Started")
        print(f"{'='*60}")
        print(f"Experiment: {self.config.name}")
        print(f"LLM: {self.config.llm.provider}/{self.config.llm.model}")
        print(f"Output: {self.output_dir}")
        if self.tracing_active:
            print(f"Tracing: enabled ({self.config.tracing.phoenix_endpoint})")
        print(f"{'='*60}")
        print("\nMonitoring Beaker session... Press Ctrl+C to stop and save logs.\n")

        # Open root tracing span (manual lifecycle since monitoring is open-ended)
        if self.tracing_active and self.tracer:
            self._root_span_ctx = experiment_span(
                self.tracer, self.config, self.run_id,
            )
            self._root_span = self._root_span_ctx.__enter__()

        try:
            await self._monitor_loop()
        except asyncio.CancelledError:
            pass
        finally:
            # Close root span
            if self._root_span_ctx is not None:
                try:
                    self._root_span_ctx.__exit__(None, None, None)
                except Exception:
                    pass
            await self._finalize()

    async def _connect_to_kernel(self) -> None:
        """Connect to existing Beaker kernel via WebSocket."""
        # Wait for a session to be created (user needs to open browser first)
        print("Waiting for Beaker session to be created...")
        print("  \u2192 Open the Beaker URL in your browser to create a session")

        sessions = []
        wait_time = 0
        max_wait = 3600  # Wait up to 1 hour for user to connect

        while not sessions and wait_time < max_wait:
            async with self.session.get(f"{self.server_url}/api/sessions") as resp:
                if resp.status != 200:
                    raise ConnectionError(f"Failed to get sessions: {resp.status}")
                sessions = await resp.json()

            if not sessions:
                await asyncio.sleep(5)
                wait_time += 5
                if wait_time % 30 == 0:
                    print(f"  Still waiting for session... ({wait_time}s)")

        if not sessions:
            raise ConnectionError(
                "No active Beaker session found after timeout. "
                "Make sure to open the Beaker URL in your browser."
            )

        # Use the first session
        session = sessions[0]
        self.kernel_id = session["kernel"]["id"]
        session_id = session["id"]

        # Connect WebSocket
        ws_base = self.server_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_base}/api/kernels/{self.kernel_id}/channels?token={self.token}"

        self.ws = await self.session.ws_connect(
            ws_url,
            timeout=aiohttp.ClientTimeout(total=None),  # No timeout for monitoring
        )

        print(f"  Connected to kernel: {self.kernel_id}")
        print(f"  Session: {session_id}")

    async def _monitor_loop(self) -> None:
        """Main loop to monitor WebSocket messages."""
        while self.is_running:
            try:
                msg = await asyncio.wait_for(
                    self.ws.receive_json(),
                    timeout=1.0,  # Short timeout to check is_running flag
                )
                await self._handle_message(msg)
            except asyncio.TimeoutError:
                # No message received, continue monitoring
                continue
            except aiohttp.WSServerHandshakeError as e:
                print(f"WebSocket error: {e}")
                break

    async def _handle_message(self, msg: dict) -> None:
        """Handle a WebSocket message and log if relevant."""
        msg_type = msg.get("msg_type", "")
        content = msg.get("content", {})
        header = msg.get("header", {})
        parent_header = msg.get("parent_header", {})

        msg_id = header.get("msg_id", "")
        parent_msg_id = parent_header.get("msg_id", "")

        # Track llm_request messages (user input)
        if msg_type == "llm_request":
            user_message = content.get("request", "")
            self._pending_requests[msg_id] = {
                "user_message": user_message,
                "start_time": asyncio.get_event_loop().time(),
                "raw_messages": [msg],
                "tool_calls": [],
            }
            print(f"  [Turn {self.current_turn + 1}] User: {user_message[:80]}{'...' if len(user_message) > 80 else ''}")

        # Track responses to pending requests
        elif parent_msg_id in self._pending_requests:
            pending = self._pending_requests[parent_msg_id]
            pending["raw_messages"].append(msg)

            if msg_type == "thought":
                # Track tool calls from thoughts
                thought = content.get("thought", "")
                if "Action:" in thought:
                    pending["tool_calls"].append({"thought": thought})

            elif msg_type == "llm_response":
                # Final LLM response - log the complete turn
                self.current_turn += 1
                agent_response = content.get("text", "")
                duration = asyncio.get_event_loop().time() - pending["start_time"]

                # Extract token usage and code executions
                usage_records = extract_usage_records(pending["raw_messages"])
                code_execs = extract_code_executions(pending["raw_messages"])
                pricing_prompt = self.config.model_metadata.pricing_prompt_per_million_tokens
                pricing_completion = self.config.model_metadata.pricing_completion_per_million_tokens
                input_tokens, output_tokens, cost_usd = calculate_turn_cost(
                    usage_records, pricing_prompt, pricing_completion
                )

                # Create tracing spans
                if self.tracing_active and self.tracer:
                    with turn_span(self.tracer, self.current_turn, pending["user_message"]) as tspan:
                        for i, usage in enumerate(usage_records):
                            with llm_call_span(self.tracer, i, self.config.llm.model) as lspan:
                                set_llm_usage(lspan, usage, pricing_prompt, pricing_completion)
                        for exec_data in code_execs:
                            with tool_span(self.tracer, "beaker_execute", exec_data.get("code", "")) as ts:
                                if ts is not None:
                                    ts.set_attribute("output.value", exec_data.get("stdout", ""))
                                    ts.set_attribute("tool.status", exec_data.get("status", "unknown"))
                        if tspan is not None:
                            tspan.set_attribute("output.value", agent_response)
                            tspan.set_attribute("harmonia.duration_seconds", duration)

                self.trace_logger.log_turn(
                    turn=self.current_turn,
                    user_message=pending["user_message"],
                    agent_response=agent_response,
                    response_type="llm_response",
                    tool_calls=pending["tool_calls"],
                    duration_seconds=duration,
                    raw_messages=pending["raw_messages"],
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                    code_executions=code_execs,
                    usage_records=usage_records,
                )
                self.conversation_logger.log_turn(
                    turn=self.current_turn,
                    user_message=pending["user_message"],
                    agent_response=agent_response,
                    response_type="llm_response",
                )

                # Auto-save after each turn
                self._save_intermediate()

                print(f"  [Turn {self.current_turn}] Agent: {agent_response[:80]}{'...' if len(agent_response) > 80 else ''}")

                # Clean up
                del self._pending_requests[parent_msg_id]

            elif msg_type == "code_cell":
                # Code cell response
                self.current_turn += 1
                code = content.get("code", "")
                duration = asyncio.get_event_loop().time() - pending["start_time"]

                # Extract token usage and code executions
                usage_records = extract_usage_records(pending["raw_messages"])
                code_execs = extract_code_executions(pending["raw_messages"])
                pricing_prompt = self.config.model_metadata.pricing_prompt_per_million_tokens
                pricing_completion = self.config.model_metadata.pricing_completion_per_million_tokens
                input_tokens, output_tokens, cost_usd = calculate_turn_cost(
                    usage_records, pricing_prompt, pricing_completion
                )

                # Create tracing spans
                if self.tracing_active and self.tracer:
                    with turn_span(self.tracer, self.current_turn, pending["user_message"]) as tspan:
                        for i, usage in enumerate(usage_records):
                            with llm_call_span(self.tracer, i, self.config.llm.model) as lspan:
                                set_llm_usage(lspan, usage, pricing_prompt, pricing_completion)
                        if tspan is not None:
                            tspan.set_attribute("output.value", code)
                            tspan.set_attribute("harmonia.response_type", "code_cell")
                            tspan.set_attribute("harmonia.duration_seconds", duration)

                self.trace_logger.log_turn(
                    turn=self.current_turn,
                    user_message=pending["user_message"],
                    agent_response=code,
                    response_type="code_cell",
                    tool_calls=pending["tool_calls"],
                    duration_seconds=duration,
                    raw_messages=pending["raw_messages"],
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                    code_executions=code_execs,
                    usage_records=usage_records,
                )
                self.conversation_logger.log_turn(
                    turn=self.current_turn,
                    user_message=pending["user_message"],
                    agent_response=f"```python\n{code}\n```",
                    response_type="code_cell",
                )

                self._save_intermediate()
                print(f"  [Turn {self.current_turn}] Agent: [code_cell] {code[:60]}{'...' if len(code) > 60 else ''}")

                del self._pending_requests[parent_msg_id]

            elif msg_type == "error":
                # Error response
                self.current_turn += 1
                traceback = "\n".join(content.get("traceback", []))
                duration = asyncio.get_event_loop().time() - pending["start_time"]

                self.trace_logger.log_turn(
                    turn=self.current_turn,
                    user_message=pending["user_message"],
                    agent_response=traceback,
                    response_type="error",
                    tool_calls=pending["tool_calls"],
                    duration_seconds=duration,
                    raw_messages=pending["raw_messages"],
                )
                self.conversation_logger.log_turn(
                    turn=self.current_turn,
                    user_message=pending["user_message"],
                    agent_response=f"```\n{traceback}\n```",
                    response_type="error",
                )

                self._save_intermediate()
                print(f"  [Turn {self.current_turn}] Agent: [error] {content.get('ename', 'Error')}")

                del self._pending_requests[parent_msg_id]

    def _save_intermediate(self) -> None:
        """Save intermediate results (in case of crash or early termination)."""
        try:
            # Update end time and save
            if self.trace_logger.trace:
                self.trace_logger.trace.end_time = datetime.utcnow().isoformat()
                total = sum(t.duration_seconds for t in self.trace_logger.trace.turns)
                self.trace_logger.trace.total_duration_seconds = total
                self.trace_logger.trace.status = "running"
            self.trace_logger.save()
            self.conversation_logger.save()
        except Exception as e:
            print(f"  Warning: Failed to save intermediate results: {e}")

    async def _finalize(self) -> None:
        """Finalize logging and close connections."""
        print(f"\n{'='*60}")
        print("Stopping monitor and saving logs...")

        # End experiment
        self.trace_logger.end_experiment(status="completed")
        self.conversation_logger.log_summary(
            total_turns=self.current_turn,
            total_duration=self.trace_logger.trace.total_duration_seconds if self.trace_logger.trace else 0,
            status="completed",
        )

        # Save final logs
        trace_path = self.trace_logger.save()
        conv_path = self.conversation_logger.save()

        print("\nExperiment complete!")
        print(f"  Total turns: {self.current_turn}")
        print(f"  Output directory: {self.output_dir}")
        print(f"  - {trace_path.name}")
        print(f"  - {conv_path.name}")
        print(f"{'='*60}\n")

        # Close connections
        if self.ws and not self.ws.closed:
            await self.ws.close()
        if self.session:
            await self.session.close()

    def stop(self) -> None:
        """Stop monitoring."""
        self.is_running = False


async def run_manual_experiment(
    config_path: Path,
    server_url: str = "http://localhost:8100",
    token: Optional[str] = None,
    output_dir: Optional[Path] = None,
) -> Path:
    """
    Run a manual experiment with logging.

    Args:
        config_path: Path to experiment configuration YAML
        server_url: Beaker server URL
        token: Jupyter authentication token
        output_dir: Override output directory

    Returns:
        Path to output directory with logs
    """
    import os

    # Load config
    config = load_config(config_path)

    # Get token from environment if not provided
    if not token:
        token = os.environ.get("JUPYTER_TOKEN")
    if not token:
        raise ValueError("No token provided. Set JUPYTER_TOKEN or pass --token")

    # Create runner
    runner = ManualExperimentRunner(
        server_url=server_url,
        token=token,
        config=config,
        output_dir=output_dir,
    )

    # Set up signal handlers for graceful shutdown
    loop = asyncio.get_event_loop()

    def signal_handler():
        print("\n\nReceived interrupt signal...")
        runner.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    # Run
    await runner.start()

    return runner.output_dir
