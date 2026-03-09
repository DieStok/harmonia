"""
Phoenix/OpenTelemetry tracing for Harmonia experiments.

Exports OTel spans to a Phoenix server via OTLP HTTP.
All instrumentation is manual - no auto-patching.
"""

import logging
import os
from contextlib import contextmanager
from dataclasses import asdict
from typing import Generator, Optional

import yaml

logger = logging.getLogger(__name__)

# Lazy imports — these are only available when tracing dependencies are installed.
# Functions guard against ImportError so that the rest of the codebase works
# without the tracing packages (tracing is opt-in via config).

_TRACING_AVAILABLE = False
try:
    from openinference.semconv.trace import (
        OpenInferenceSpanKindValues,
        SpanAttributes,
    )
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.trace import Span, StatusCode, Tracer
    _TRACING_AVAILABLE = True
except ImportError:
    # Stubs so type hints work even without the packages
    Tracer = object
    Span = object


def _check_phoenix_reachable(endpoint: str, timeout: float = 5.0) -> bool:
    """Check if Phoenix server is reachable."""
    import urllib.error
    import urllib.request
    try:
        req = urllib.request.Request(f"{endpoint}/api/v1/traces", method="GET")
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except Exception:
        # Try health endpoint as fallback
        try:
            req = urllib.request.Request(f"{endpoint}/healthz", method="GET")
            with urllib.request.urlopen(req, timeout=timeout):
                return True
        except Exception:
            return False


def init_tracing(
    phoenix_endpoint: str,
    run_id: str,
    experiment_name: str,
    service_name: str = "harmonia",
) -> tuple:
    """
    Configure OTel TracerProvider with OTLP HTTP exporter.

    Returns (Tracer, tracing_active: bool).
    If Phoenix is unreachable or deps missing, returns a no-op tracer and False.
    """
    if not _TRACING_AVAILABLE:
        logger.warning(
            "Tracing dependencies not installed (opentelemetry/openinference). "
            "Tracing disabled. Install with: uv pip install opentelemetry-api "
            "opentelemetry-sdk opentelemetry-exporter-otlp-proto-http "
            "openinference-semantic-conventions"
        )
        return None, False

    # Allow env var override (set by exec_apptainer_harmonia.sh via ensure_phoenix_server.py)
    env_endpoint = os.environ.get("PHOENIX_ENDPOINT")
    endpoint = env_endpoint or phoenix_endpoint
    source = "PHOENIX_ENDPOINT env var" if env_endpoint else f"config ({phoenix_endpoint})"

    import socket
    this_host = socket.gethostname().split(".")[0]

    if not _check_phoenix_reachable(endpoint):
        logger.warning(
            f"Phoenix server unreachable at {endpoint} (source: {source}, "
            f"checked from host: {this_host}). Tracing disabled."
        )
        return None, False

    resource = Resource.create({
        "service.name": service_name,
        "harmonia.run_id": run_id,
        "harmonia.experiment_name": experiment_name,
    })

    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(exporter))

    tracer = provider.get_tracer("harmonia", "1.0.0")

    logger.info(
        f"Tracing initialized: endpoint={endpoint} (source: {source}), "
        f"run_id={run_id}, host={this_host}"
    )
    return tracer, True


@contextmanager
def experiment_span(
    tracer,
    config,
    run_id: str,
    trace_type: str = "annotation",
    parent_run_id: Optional[str] = None,
) -> Generator:
    """
    Root AGENT span for the full experiment.

    Sets harmonia.run_id, harmonia.trace_type, harmonia.parent_run_id,
    llm.model_name, harmonia.llm_provider, harmonia.config_snapshot.
    """
    if not _TRACING_AVAILABLE:
        yield None
        return

    config_snapshot = ""
    try:
        config_snapshot = yaml.dump(asdict(config), default_flow_style=False)
    except Exception:
        pass

    with tracer.start_as_current_span(
        f"experiment:{config.name}",
        attributes={
            SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.AGENT.value,
            "harmonia.run_id": run_id,
            "harmonia.experiment_name": config.name,
            "harmonia.trace_type": trace_type,
            SpanAttributes.LLM_MODEL_NAME: config.llm.model,
            "harmonia.llm_provider": config.llm.provider,
            "harmonia.config_snapshot": config_snapshot,
        },
    ) as span:
        if parent_run_id:
            span.set_attribute("harmonia.parent_run_id", parent_run_id)
        try:
            yield span
            span.set_status(StatusCode.OK)
        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            span.record_exception(e)
            raise


@contextmanager
def turn_span(
    tracer,
    turn_number: int,
    user_message: str,
) -> Generator:
    """CHAIN span for a conversation turn."""
    if not _TRACING_AVAILABLE:
        yield None
        return

    with tracer.start_as_current_span(
        f"turn:{turn_number}",
        attributes={
            SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.CHAIN.value,
            "harmonia.turn_number": turn_number,
            SpanAttributes.INPUT_VALUE: user_message,
        },
    ) as span:
        try:
            yield span
        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            raise


@contextmanager
def llm_call_span(
    tracer,
    call_index: int,
    model_name: str,
) -> Generator:
    """LLM span for an individual LLM API call within a turn."""
    if not _TRACING_AVAILABLE:
        yield None
        return

    with tracer.start_as_current_span(
        f"llm_call:{call_index}",
        attributes={
            SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.LLM.value,
            SpanAttributes.LLM_MODEL_NAME: model_name,
        },
    ) as span:
        try:
            yield span
        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            raise


@contextmanager
def tool_span(
    tracer,
    tool_name: str,
    code: str,
) -> Generator:
    """TOOL span for a Beaker code execution."""
    if not _TRACING_AVAILABLE:
        yield None
        return

    with tracer.start_as_current_span(
        "beaker_execute",
        attributes={
            SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.TOOL.value,
            "tool.name": tool_name,
            SpanAttributes.INPUT_VALUE: code,
        },
    ) as span:
        try:
            yield span
        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            raise


def set_llm_usage(
    span,
    usage: dict,
    pricing_prompt_per_million: float = 0.0,
    pricing_completion_per_million: float = 0.0,
) -> None:
    """Set token count and cost attributes on an LLM span."""
    if not _TRACING_AVAILABLE or span is None:
        return

    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    total_tokens = usage.get("total_tokens", 0)

    span.set_attribute(SpanAttributes.LLM_TOKEN_COUNT_PROMPT, input_tokens)
    span.set_attribute(SpanAttributes.LLM_TOKEN_COUNT_COMPLETION, output_tokens)
    span.set_attribute(SpanAttributes.LLM_TOKEN_COUNT_TOTAL, total_tokens)

    cost = (
        (input_tokens * pricing_prompt_per_million / 1_000_000)
        + (output_tokens * pricing_completion_per_million / 1_000_000)
    )
    if cost > 0:
        span.set_attribute("harmonia.cost_usd", cost)


def extract_usage_records(raw_messages: list[dict]) -> list[dict]:
    """
    Extract usage_records from raw WebSocket messages.

    Scans messages in reverse for the first message containing usage_records.
    Returns list of dicts with keys: input_tokens, output_tokens, total_tokens.
    """
    for msg in reversed(raw_messages):
        content = msg.get("content", {})
        if isinstance(content, dict) and "usage_records" in content:
            records = content["usage_records"]
            if isinstance(records, list):
                return records
    return []


def extract_code_executions(raw_messages: list[dict]) -> list[dict]:
    """
    Parse raw WebSocket messages to extract structured code executions.

    Returns list of dicts with keys: code, stdout, stderr, status.
    Looks for execute_input -> execute_result/stream/error sequences.
    """
    executions = []
    current_exec = None

    for msg in raw_messages:
        msg_type = msg.get("msg_type", "")
        content = msg.get("content", {})

        if msg_type == "execute_input":
            if current_exec is not None:
                executions.append(current_exec)
            current_exec = {
                "code": content.get("code", ""),
                "stdout": "",
                "stderr": "",
                "status": "unknown",
            }

        elif msg_type == "stream" and current_exec is not None:
            name = content.get("name", "stdout")
            text = content.get("text", "")
            if name == "stderr":
                current_exec["stderr"] += text
            else:
                current_exec["stdout"] += text

        elif msg_type == "execute_result" and current_exec is not None:
            data = content.get("data", {})
            text = data.get("text/plain", "")
            if text:
                current_exec["stdout"] += text
            current_exec["status"] = "ok"

        elif msg_type == "error" and current_exec is not None:
            current_exec["status"] = "error"
            current_exec["stderr"] += "\n".join(content.get("traceback", []))

        elif msg_type == "status":
            exec_state = content.get("execution_state", "")
            if exec_state == "idle" and current_exec is not None:
                if current_exec["status"] == "unknown":
                    current_exec["status"] = "ok"
                executions.append(current_exec)
                current_exec = None

    # Don't forget the last one
    if current_exec is not None:
        executions.append(current_exec)

    return executions


def calculate_turn_cost(
    usage_records: list[dict],
    pricing_prompt_per_million: float = 0.0,
    pricing_completion_per_million: float = 0.0,
) -> tuple[int, int, float]:
    """
    Calculate total token counts and cost for a turn from usage records.

    Returns (total_input_tokens, total_output_tokens, total_cost_usd).
    """
    total_input = sum(r.get("input_tokens", 0) for r in usage_records)
    total_output = sum(r.get("output_tokens", 0) for r in usage_records)
    cost = (
        (total_input * pricing_prompt_per_million / 1_000_000)
        + (total_output * pricing_completion_per_million / 1_000_000)
    )
    return total_input, total_output, cost
