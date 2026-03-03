"""
Beaker client for interacting with running Beaker server via Jupyter protocol.

This client connects to a running Beaker/Jupyter server and sends messages
to the LLM agent, capturing responses for experiment automation.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator, Optional

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

    async def connect(self, context_name: str = None) -> None:
        """Connect to Beaker server and establish WebSocket connection.

        Args:
            context_name: Optional context slug to use (e.g. "codeact_context").
                If None, falls back to auto-detection (prefers bdikit_context).
        """
        if self.session is None:
            self.session = aiohttp.ClientSession(
                headers={"Authorization": f"token {self.token}"}
            )

        # Get or create a session with kernel
        selected_context = await self._get_or_create_session(context_name)

        # Connect WebSocket to kernel
        ws_url = self._get_websocket_url()
        self.ws = await self.session.ws_connect(
            ws_url,
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        )
        self._connected = True

        # Set context via execute_request with magic command after WebSocket connection
        if selected_context:
            await self._set_context_magic(selected_context)

    async def _get_or_create_session(self, context_name: str = None) -> Optional[str]:
        """Get existing session or create new one.

        Returns the context slug to set after WebSocket connection.
        """
        # List existing sessions
        async with self.session.get(f"{self.server_url}/api/sessions") as resp:
            if resp.status == 200:
                sessions = await resp.json()
                if sessions:
                    # Use existing session
                    session = sessions[0]
                    self.session_id = session["id"]
                    self.kernel_id = session["kernel"]["id"]
                    # Still return context to set it via WebSocket
                    return await self._find_context(context_name)

        # No existing session, create one
        selected_context = await self._find_context(context_name)

        # Create session - use standard Jupyter API with kernel name
        # The beaker_kernel will load context via set_context message
        session_data = {
            "name": "automation_session",
            "path": "automation",
            "type": "notebook",
            "kernel": {"name": "beaker_kernel"},
        }

        # Create session via standard Jupyter API
        async with self.session.post(
            f"{self.server_url}/api/sessions",
            json=session_data,
        ) as resp:
            if resp.status not in (200, 201):
                raise ConnectionError(f"Failed to create session: {resp.status}")
            session = await resp.json()

        self.session_id = session["id"]
        self.kernel_id = session["kernel"]["id"]

        return selected_context

    async def _find_context(self, context_name: str = None) -> Optional[str]:
        """Find the best context to use (prefer bdikit_context)."""
        # Get available contexts from Beaker
        async with self.session.get(f"{self.server_url}/contexts") as resp:
            if resp.status != 200:
                print(f"  Warning: Failed to get contexts: {resp.status}")
                return None
            contexts = await resp.json()

        # Find the bdikit context (required for harmonization tools)
        selected_context = context_name
        if not selected_context:
            for ctx in contexts:
                if "bdikit" in ctx.lower():
                    selected_context = ctx
                    break
            # Fall back to first context if bdikit not found
            if not selected_context and contexts:
                selected_context = contexts[0]

        return selected_context

    async def _set_context_magic(self, context_slug: str) -> None:
        """Set the Beaker context via execute_request with magic command.

        This enables bdi-kit tools and harmonization functions.
        Uses the %set_context magic command format.
        """
        if not self.ws or self.ws.closed:
            print(f"  Warning: WebSocket not connected, cannot set context '{context_slug}'")
            return

        # Format: %set_context {context_slug} {language} {context_config (json)}
        magic_code = f"%set_context {context_slug} python3 {{}}"

        # Send execute_request message
        msg = self._make_message("execute_request", {
            "code": magic_code,
            "silent": False,
            "store_history": False,
            "user_expressions": {},
            "allow_stdin": False,
            "stop_on_error": True,
        })
        msg_id = msg["header"]["msg_id"]

        try:
            await self.ws.send_json(msg)

            # Wait for execution to complete
            end_time = asyncio.get_event_loop().time() + 30  # 30s timeout
            while asyncio.get_event_loop().time() < end_time:
                try:
                    response = await asyncio.wait_for(self.ws.receive_json(), timeout=5.0)
                    parent = response.get("parent_header", {})
                    if parent.get("msg_id") == msg_id:
                        msg_type = response.get("msg_type", "")
                        if msg_type == "status":
                            state = response.get("content", {}).get("execution_state")
                            if state == "idle":
                                print(f"  Context '{context_slug}' set successfully")
                                return
                        elif msg_type == "error":
                            error = response.get("content", {}).get("evalue", "Unknown error")
                            print(f"  Warning: Error setting context '{context_slug}': {error}")
                            return
                        elif msg_type == "stream":
                            # Log stdout/stderr from context setting
                            text = response.get("content", {}).get("text", "")
                            if text:
                                print(f"  {text.strip()}")
                except asyncio.TimeoutError:
                    continue

            print(f"  Warning: Timeout setting context '{context_slug}'")
        except Exception as e:
            print(f"  Warning: Failed to set context '{context_slug}': {e}")

    async def _set_context_ws(self, context_slug: str) -> None:
        """Set the Beaker context via WebSocket message.

        This enables bdi-kit tools and harmonization functions.
        Must be called after WebSocket is connected.
        """
        if not self.ws or self.ws.closed:
            print(f"  Warning: WebSocket not connected, cannot set context '{context_slug}'")
            return

        # Send set_context message via Jupyter protocol
        msg = self._make_message("set_context", {
            "context": context_slug,
            "payload": {}
        })
        msg_id = msg["header"]["msg_id"]

        try:
            await self.ws.send_json(msg)

            # Wait for context to be set (look for status=idle or context_set confirmation)
            end_time = asyncio.get_event_loop().time() + 30  # 30s timeout
            while asyncio.get_event_loop().time() < end_time:
                try:
                    response = await asyncio.wait_for(self.ws.receive_json(), timeout=5.0)
                    parent = response.get("parent_header", {})
                    if parent.get("msg_id") == msg_id:
                        msg_type = response.get("msg_type", "")
                        if msg_type == "status":
                            state = response.get("content", {}).get("execution_state")
                            if state == "idle":
                                print(f"  Context '{context_slug}' set successfully")
                                return
                        elif msg_type == "error":
                            error = response.get("content", {}).get("evalue", "Unknown error")
                            print(f"  Warning: Error setting context '{context_slug}': {error}")
                            return
                except asyncio.TimeoutError:
                    continue

            print(f"  Warning: Timeout setting context '{context_slug}'")
        except Exception as e:
            print(f"  Warning: Failed to set context '{context_slug}': {e}")

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
                    text = (
                        content.get("text")
                        or content.get("content")
                        or content.get("message")
                        or ""
                    )
                    if text:
                        final_content = str(text)
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

        if response_type == "llm_response" and not final_content.strip():
            for raw in reversed(responses):
                c = raw.get("content", {})
                if raw.get("msg_type") == "stream":
                    text = c.get("text", "")
                elif raw.get("msg_type") == "llm_response":
                    text = c.get("text") or c.get("content") or c.get("message") or ""
                else:
                    continue
                if text and str(text).strip():
                    final_content = str(text)
                    break

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
            if msg_type in ("error", "execute_reply"):
                break
            if msg_type == "llm_response":
                text = msg.get("content", {}).get("text", "")
                if text:
                    break
            elif msg_type == "status":
                # Check if kernel is idle (request complete)
                if msg.get("content", {}).get("execution_state") == "idle":
                    break

    async def _get_xsrf_cookie(self) -> Optional[str]:
        """Fetch XSRF cookie from server for POST requests."""
        try:
            async with self.session.get(f"{self.server_url}/") as resp:
                if "_xsrf" in resp.cookies:
                    return resp.cookies["_xsrf"].value
        except Exception:
            pass
        return None

    async def save_notebook(self, cells: list[dict], name: str = "experiment") -> dict:
        """
        Save/update notebook content on Beaker server.

        Args:
            cells: List of notebook cells
            name: Notebook name

        Returns:
            Notebook info from server
        """
        notebook_content = {
            "metadata": {
                "kernelspec": {"name": "beaker_kernel", "display_name": "Beaker"},
                "beaker": {"session_id": self.session_id},
            },
            "nbformat": 4,
            "nbformat_minor": 5,
            "cells": cells,
        }

        # Get XSRF cookie and include in headers
        xsrf = await self._get_xsrf_cookie()
        headers = {}
        if xsrf:
            headers["X-XSRFToken"] = xsrf

        # Include token in URL and XSRF token in header
        url = f"{self.server_url}/notebook?token={self.token}"
        async with self.session.post(
            url,
            json={"content": notebook_content, "session": self.session_id, "name": name},
            headers=headers,
        ) as resp:
            if resp.status not in (200, 201):
                text = await resp.text()
                raise RuntimeError(f"Failed to save notebook: {resp.status} - {text}")
            return await resp.json()

    async def get_notebook(self, session_id: str = None) -> Optional[dict]:
        """Retrieve notebook by session ID."""
        session_id = session_id or self.session_id
        url = f"{self.server_url}/notebook?session={session_id}&token={self.token}"
        async with self.session.get(url) as resp:
            if resp.status == 200:
                return await resp.json()
            return None

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

    async def execute_code(self, code: str, timeout: float = 60.0) -> dict:
        """
        Execute Python code directly in the kernel.

        Args:
            code: Python code to execute
            timeout: Timeout in seconds

        Returns:
            Dict with 'status', 'output', and 'error' keys
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to Beaker server. Call connect() first.")

        msg = self._make_message("execute_request", {
            "code": code,
            "silent": False,
            "store_history": True,
            "user_expressions": {},
            "allow_stdin": False,
            "stop_on_error": True,
        })
        msg_id = msg["header"]["msg_id"]

        await self.ws.send_json(msg)

        # Collect execution results
        output = []
        error = None
        status = "ok"

        end_time = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < end_time:
            try:
                response = await asyncio.wait_for(self.ws.receive_json(), timeout=5.0)
                parent = response.get("parent_header", {})
                if parent.get("msg_id") != msg_id:
                    continue

                msg_type = response.get("msg_type", "")
                content = response.get("content", {})

                if msg_type == "stream":
                    output.append(content.get("text", ""))
                elif msg_type == "execute_result":
                    output.append(str(content.get("data", {}).get("text/plain", "")))
                elif msg_type == "error":
                    error = "\n".join(content.get("traceback", []))
                    status = "error"
                elif msg_type == "status":
                    if content.get("execution_state") == "idle":
                        break
                elif msg_type == "execute_reply":
                    if content.get("status") == "error":
                        status = "error"
                        error = content.get("evalue", "Unknown error")
                    break

            except asyncio.TimeoutError:
                continue

        return {
            "status": status,
            "output": "".join(output),
            "error": error,
        }

    async def __aenter__(self) -> "BeakerClient":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()
