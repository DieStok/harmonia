"""
Beaker client for interacting with running Beaker server via Jupyter protocol.

This client connects to a running Beaker/Jupyter server and sends messages
to the LLM agent, capturing responses for experiment automation.
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Optional

import aiohttp


@dataclass
class AgentResponse:
    """Response from the Beaker agent."""
    content: str
    response_type: str  # "llm_response", "code_cell", "stream", "error"
    raw_messages: list[dict] = field(default_factory=list)
    duration_seconds: float = 0.0
    tool_calls: list[dict] = field(default_factory=list)


class BeakerClient:
    """Client to interact with running Beaker server via Jupyter protocol."""

    def __init__(
        self,
        server_url: str,
        token: str,
        timeout: float = 300.0,
    ):
        """
        Initialize Beaker client.

        Args:
            server_url: Base URL of Beaker server (e.g., "http://localhost:8100")
            token: Jupyter authentication token
            timeout: Default timeout for requests in seconds
        """
        self.server_url = server_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.session: Optional[aiohttp.ClientSession] = None
        self.kernel_id: Optional[str] = None
        self.session_id: Optional[str] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Check if client is connected to server."""
        return self._connected and self.ws is not None and not self.ws.closed

    async def connect(self) -> None:
        """Connect to Beaker server and establish WebSocket connection."""
        if self.session is None:
            self.session = aiohttp.ClientSession(
                headers={"Authorization": f"token {self.token}"}
            )

        # Get or create a session with kernel
        await self._get_or_create_session()

        # Connect WebSocket to kernel
        ws_url = self._get_websocket_url()
        self.ws = await self.session.ws_connect(
            ws_url,
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        )
        self._connected = True

    async def _get_or_create_session(self) -> None:
        """Get existing session or create new one."""
        # List existing sessions
        async with self.session.get(f"{self.server_url}/api/sessions") as resp:
            if resp.status == 200:
                sessions = await resp.json()
                if sessions:
                    # Use existing session
                    session = sessions[0]
                    self.session_id = session["id"]
                    self.kernel_id = session["kernel"]["id"]
                    return

        # No existing session, create one
        # First, get available contexts
        async with self.session.get(f"{self.server_url}/api/contexts") as resp:
            if resp.status != 200:
                raise ConnectionError(f"Failed to get contexts: {resp.status}")
            contexts = await resp.json()

        # Find the bdikit context
        context_name = None
        for ctx in contexts:
            if "bdikit" in ctx.lower():
                context_name = ctx
                break

        if not context_name and contexts:
            context_name = contexts[0]

        # Create session with context
        session_data = {
            "name": "automation_session",
            "path": "automation",
            "type": "notebook",
            "kernel": {"name": "beaker_kernel"},
        }

        if context_name:
            # Use the context-aware session creation endpoint
            session_data["context"] = {"slug": context_name}
            async with self.session.post(
                f"{self.server_url}/api/sessions/create-with-context",
                json=session_data,
            ) as resp:
                if resp.status not in (200, 201):
                    # Fall back to regular session creation
                    async with self.session.post(
                        f"{self.server_url}/api/sessions",
                        json=session_data,
                    ) as resp2:
                        if resp2.status not in (200, 201):
                            raise ConnectionError(f"Failed to create session: {resp2.status}")
                        session = await resp2.json()
                else:
                    session = await resp.json()
        else:
            async with self.session.post(
                f"{self.server_url}/api/sessions",
                json=session_data,
            ) as resp:
                if resp.status not in (200, 201):
                    raise ConnectionError(f"Failed to create session: {resp.status}")
                session = await resp.json()

        self.session_id = session["id"]
        self.kernel_id = session["kernel"]["id"]

    def _get_websocket_url(self) -> str:
        """Get WebSocket URL for kernel connection."""
        # Convert http(s) to ws(s)
        ws_base = self.server_url.replace("http://", "ws://").replace("https://", "wss://")
        return f"{ws_base}/api/kernels/{self.kernel_id}/channels?token={self.token}"

    def _make_message(self, msg_type: str, content: dict) -> dict:
        """Create a Jupyter protocol message."""
        msg_id = str(uuid.uuid4())
        return {
            "header": {
                "msg_id": msg_id,
                "msg_type": msg_type,
                "username": "automation",
                "session": self.session_id or str(uuid.uuid4()),
                "date": datetime.utcnow().isoformat(),
                "version": "5.3",
            },
            "parent_header": {},
            "metadata": {},
            "content": content,
            "buffers": [],
            "channel": "shell",
        }

    async def send_message(self, message: str, timeout: Optional[float] = None) -> AgentResponse:
        """
        Send a user message to the agent and wait for complete response.

        Args:
            message: The user message to send
            timeout: Optional timeout override

        Returns:
            AgentResponse with the agent's response
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to Beaker server. Call connect() first.")

        timeout = timeout or self.timeout
        start_time = asyncio.get_event_loop().time()

        # Create llm_request message
        msg = self._make_message("llm_request", {"request": message})
        msg_id = msg["header"]["msg_id"]

        # Send the message
        await self.ws.send_json(msg)

        # Collect responses until we get the final response
        responses: list[dict] = []
        final_content = ""
        response_type = "llm_response"
        tool_calls = []

        try:
            async for raw_msg in self._receive_until_complete(msg_id, timeout):
                responses.append(raw_msg)
                msg_type = raw_msg.get("msg_type", "")
                content = raw_msg.get("content", {})

                if msg_type == "llm_response":
                    final_content = content.get("text", "")
                    response_type = "llm_response"
                elif msg_type == "code_cell":
                    final_content = content.get("code", "")
                    response_type = "code_cell"
                elif msg_type == "stream":
                    # Append stream output
                    if content.get("name") == "stdout":
                        final_content += content.get("text", "")
                elif msg_type == "error":
                    final_content = "\n".join(content.get("traceback", []))
                    response_type = "error"
                elif msg_type == "thought":
                    # Track tool calls from thoughts
                    thought = content.get("thought", "")
                    if "Action:" in thought:
                        tool_calls.append({"thought": thought})

        except asyncio.TimeoutError:
            response_type = "timeout"
            final_content = f"Request timed out after {timeout} seconds"

        duration = asyncio.get_event_loop().time() - start_time

        return AgentResponse(
            content=final_content,
            response_type=response_type,
            raw_messages=responses,
            duration_seconds=duration,
            tool_calls=tool_calls,
        )

    async def _receive_until_complete(
        self, parent_msg_id: str, timeout: float
    ) -> AsyncIterator[dict]:
        """Receive messages until the request is complete."""
        end_time = asyncio.get_event_loop().time() + timeout

        while True:
            remaining = end_time - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError()

            try:
                msg = await asyncio.wait_for(
                    self.ws.receive_json(),
                    timeout=min(remaining, 30.0),
                )
            except asyncio.TimeoutError:
                # Check if we should continue waiting
                if asyncio.get_event_loop().time() < end_time:
                    continue
                raise

            # Check if this message is for our request
            parent_header = msg.get("parent_header", {})
            if parent_header.get("msg_id") != parent_msg_id:
                continue

            msg_type = msg.get("msg_type", "")
            yield msg

            # Check for completion signals
            if msg_type in ("llm_response", "error", "execute_reply"):
                # Final response received
                break
            elif msg_type == "status":
                # Check if kernel is idle (request complete)
                if msg.get("content", {}).get("execution_state") == "idle":
                    break

    async def send_message_stream(
        self, message: str, timeout: Optional[float] = None
    ) -> AsyncIterator[dict]:
        """
        Send a message and yield responses as they arrive.

        Args:
            message: The user message to send
            timeout: Optional timeout override

        Yields:
            Individual response messages as they arrive
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to Beaker server. Call connect() first.")

        timeout = timeout or self.timeout

        # Create and send llm_request message
        msg = self._make_message("llm_request", {"request": message})
        msg_id = msg["header"]["msg_id"]
        await self.ws.send_json(msg)

        # Yield responses as they come
        async for raw_msg in self._receive_until_complete(msg_id, timeout):
            yield raw_msg

    async def disconnect(self) -> None:
        """Disconnect from Beaker server."""
        if self.ws and not self.ws.closed:
            await self.ws.close()
        if self.session:
            await self.session.close()
        self._connected = False
        self.ws = None
        self.session = None

    async def __aenter__(self) -> "BeakerClient":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()
