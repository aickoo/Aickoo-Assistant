#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.

MCP Transport Implementations

- StdioTransport: subprocess pipe I/O
- StreamableHttpSseTransport: HTTP POST + SSE streaming
- WebSocketTransport: WebSocket bidirectional
"""
import json
import queue
import subprocess
import threading
import time
from typing import Dict, Any, Iterator, Optional, List

import requests
import websocket

from .base import BaseTransport


class StdioTransport(BaseTransport):
    """
    Transport using subprocess stdio pipes.
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._process: Optional[subprocess.Popen] = None
        self._message_queue: queue.Queue = queue.Queue()
        self._read_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
    
    def connect(self) -> None:
        """Spawn subprocess and connect to stdio pipes."""
        command = self.config.get("command", "")
        if not command:
            raise ValueError("Stdio transport requires 'command' in config")
        
        args = command.split()
        self._process = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Start reading thread
        self._stop_event.clear()
        self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._read_thread.start()
        self._connected = True
    
    def _read_loop(self) -> None:
        """Read lines from subprocess stdout."""
        assert self._process is not None
        
        while not self._stop_event.is_set():
            try:
                line = self._process.stdout.readline()
                if not line:
                    break
                try:
                    message = json.loads(line.strip())
                    self._message_queue.put(message)
                except json.JSONDecodeError:
                    # Handle non-JSON output (log messages, etc.)
                    pass
            except Exception:
                break
    
    def send_message(self, rpc_msg: Dict[str, Any]) -> None:
        """Send JSON-RPC message via stdin."""
        assert self._process is not None
        message = json.dumps(rpc_msg) + '\n'
        self._process.stdin.write(message)
        self._process.stdin.flush()
    
    def recv_messages(self) -> Iterator[Dict[str, Any]]:
        """Receive messages from queue."""
        while self._connected or not self._message_queue.empty():
            try:
                message = self._message_queue.get(timeout=1.0)
                yield message
            except queue.Empty:
                if not self._connected:
                    break
    
    def close(self) -> None:
        """Close the subprocess and clean up."""
        self._connected = False
        self._stop_event.set()
        
        if self._read_thread:
            self._read_thread.join(timeout=2.0)
        
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5.0)
            except Exception:
                self._process.kill()


class StreamableHttpSseTransport(BaseTransport):
    """
    Transport implementing MCP Streamable HTTP protocol.

    Per MCP spec (https://modelcontextprotocol.io/specification/basic/transports):
    - Client sends JSON-RPC via HTTP POST to the MCP endpoint.
    - Server MUST reply with Content-Type: text/event-stream (SSE) in the POST response body.
    - Each SSE event in the response carries one JSON-RPC message.
    - There is NO separate long-polling GET connection needed.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._base_url = self.config.get("url", "")
        self._send_url = self.config.get("send_url", self._base_url)

        self._message_queue: queue.Queue = queue.Queue()
        self._session: Optional[requests.Session] = None
        self._session_id: Optional[str] = None
        # base headers from config (e.g. Authorization)
        self.headers: Dict[str, str] = dict(self.config.get("headers", {}))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_headers(self) -> Dict[str, str]:
        """Build per-request headers."""
        headers = dict(self.headers)
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json, text/event-stream"
        if self._session_id:
            headers["mcp-session-id"] = self._session_id
        return headers

    def reset_session_id(self) -> None:
        """Reset the session ID (used when session expires)."""
        self._session_id = None

    def _update_session_id(self, headers) -> None:
        """Persist session ID returned by server."""
        sid = headers.get("mcp-session-id")
        if sid:
            self._session_id = sid

    @staticmethod
    def _iter_sse(response: requests.Response):
        """
        Generator: yield each complete SSE event's data payload.
        Handles both 'data: ...' lines and bare 'data:...' lines.
        An empty line signals end of one event.
        """
        data_lines: List[str] = []
        for line in response.iter_lines():
            if line is None:
                continue
            line = line.decode("utf-8").rstrip("\r\n")
            if not line:
                if data_lines:
                    yield "\n".join(data_lines)
                    data_lines = []
                continue
            if line.startswith("data: "):
                data_lines.append(line[6:])
            elif line.startswith("data:"):
                data_lines.append(line[5:])
            # ignore 'event:', 'id:', 'retry:' etc.
        # flush any trailing data
        if data_lines:
            yield "\n".join(data_lines)

    def _read_post_sse(self, response: requests.Response) -> None:
        """Read SSE events from a POST response body and push into queue."""
        self._update_session_id(response.headers)
        for event_data in self._iter_sse(response):
            if not event_data.strip():
                continue
            try:
                message = json.loads(event_data)
                self._message_queue.put(message)
            except json.JSONDecodeError as e:
                print(f"[MCP] SSE JSON parse error: {e} | data={event_data!r}")

    # ------------------------------------------------------------------
    # BaseTransport interface
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Create the shared HTTP session. No long-polling connection needed."""
        if not self._base_url:
            raise ValueError("HTTP-SSE transport requires 'url' in config")
        self._session = requests.Session()
        self._connected = True

    def send_message(self, rpc_msg: Dict[str, Any]) -> None:
        """
        POST the JSON-RPC message and read SSE response in the same request.
        The server streams back one or more SSE events in the response body.
        Each event is parsed and put into the internal queue so that
        _send_request's future can be resolved.
        """
        assert self._session is not None

        timeout_s = self.config.get("config", {}).get("timeout", 60)
        method = rpc_msg.get("method", "?")

        response = self._session.post(
            self._send_url,
            json=rpc_msg,
            headers=self._build_headers(),
            allow_redirects=False,
            timeout=timeout_s,
            stream=True,
        )
        
        print(f"[MCP:{self.config.get('name')}] POST {method} -> {response.status_code} "
              f"Content-Type={response.headers.get('Content-Type', '?')}")
        
        # 如果响应状态码表示错误，读取响应体以便调试
        if response.status_code >= 400:
            error_body = response.text[:500]
            print(f"[MCP:{self.config.get('name')}] Error response body: {error_body!r}")
            # 打印请求的 headers 以便调试
            print(f"[MCP:{self.config.get('name')}] Request headers: {self._build_headers()}")
        
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        if "text/event-stream" in content_type:
            # Server replied with SSE stream in the POST body
            self._read_post_sse(response)
        else:
            # Server replied with plain JSON (e.g. 202 Accepted / notification ack)
            self._update_session_id(response.headers)
            raw = response.text
            print(f"[MCP:{self.config.get('name')}] POST {method} plain body={raw[:200]!r}")
            if raw.strip():
                try:
                    message = json.loads(raw)
                    self._message_queue.put(message)
                except json.JSONDecodeError:
                    pass

    def recv_messages(self) -> Iterator[Dict[str, Any]]:
        """Yield messages from internal queue while connected."""
        while self._connected or not self._message_queue.empty():
            try:
                message = self._message_queue.get(timeout=1.0)
                yield message
            except queue.Empty:
                if not self._connected:
                    break

    def close(self) -> None:
        """Close the HTTP session."""
        self._connected = False
        if self._session:
            self._session.close()
            self._session = None


class SseTransport(BaseTransport):
    """
    Transport for legacy MCP SSE protocol (separate GET + POST).

    Per legacy MCP SSE transport:
    - GET <url> establishes a long-lived SSE connection.
      The first event carries an 'endpoint' URI for sending requests.
    - POST <base_url><endpoint> sends JSON-RPC requests.
    - Responses arrive as SSE events on the GET connection.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._sse_url = self.config.get("url", "")
        self._post_url: Optional[str] = None  # resolved from SSE endpoint event

        self._message_queue: queue.Queue = queue.Queue()
        self._listen_thread: Optional[threading.Thread] = None
        self._session: Optional[requests.Session] = None
        self._stop_event = threading.Event()
        self.headers: Dict[str, str] = dict(self.config.get("headers", {}))

    def _build_headers(self) -> Dict[str, str]:
        headers = dict(self.headers)
        headers["Accept"] = "text/event-stream"
        return headers

    def connect(self) -> None:
        """Establish the SSE long connection via GET."""
        if not self._sse_url:
            raise ValueError("SSE transport requires 'url' in config")

        self._session = requests.Session()
        self._connected = True
        self._stop_event.clear()
        self._listen_thread = threading.Thread(target=self._listen_sse, daemon=True)
        self._listen_thread.start()

        # Wait until the endpoint URL is resolved from the first SSE event.
        timeout_s = self.config.get("config", {}).get("timeout", 30)
        waited = 0.0
        while self._post_url is None and waited < timeout_s:
            time.sleep(0.1)
            waited += 0.1
        if self._post_url is None:
            raise TimeoutError(f"SSE endpoint not received within {timeout_s}s")

    def _listen_sse(self) -> None:
        """Listen for SSE events on the GET connection."""
        assert self._session is not None

        try:
            response = self._session.get(
                self._sse_url,
                headers=self._build_headers(),
                stream=True,
                timeout=None,
            )
            response.raise_for_status()

            data_lines: List[str] = []
            event_type: Optional[str] = None

            for line in response.iter_lines():
                if self._stop_event.is_set():
                    break
                    
                if line is None:
                    continue
                line = line.decode("utf-8").rstrip("\r\n")

                if not line:
                    # End of event
                    if data_lines:
                        event_data = "\n".join(data_lines)
                        data_lines = []

                        if event_type == "endpoint":
                            # Resolve POST endpoint relative to the SSE URL base
                            from urllib.parse import urljoin
                            self._post_url = urljoin(self._sse_url, event_data.strip())
                            print(f"[SSE] Resolved POST endpoint: {self._post_url}")
                        else:
                            # Regular data event carrying JSON-RPC message
                            try:
                                message = json.loads(event_data)
                                self._message_queue.put(message)
                            except json.JSONDecodeError:
                                pass
                    event_type = None
                    continue

                if line.startswith("event: "):
                    event_type = line[7:].strip()
                elif line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data: "):
                    data_lines.append(line[6:])
                elif line.startswith("data:"):
                    data_lines.append(line[5:])
        except Exception as e:
            print(f"[SSE] Listen error: {e}")

    def send_message(self, rpc_msg: Dict[str, Any]) -> None:
        """Send JSON-RPC via HTTP POST to the resolved endpoint."""
        assert self._session is not None
        if not self._post_url:
            raise RuntimeError("SSE POST endpoint not yet resolved")

        headers = dict(self.headers)
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "text/event-stream, application/json"

        timeout_s = self.config.get("config", {}).get("timeout", 60)

        response = self._session.post(
            self._post_url,
            json=rpc_msg,
            headers=headers,
            timeout=timeout_s,
            stream=True,
        )
        response.raise_for_status()
        # Responses are delivered via the SSE GET connection, not here.
        # But some servers may respond inline with JSON.
        content_type = response.headers.get("Content-Type", "")
        if "text/event-stream" not in content_type:
            raw = response.text
            if raw.strip():
                try:
                    message = json.loads(raw)
                    self._message_queue.put(message)
                except json.JSONDecodeError:
                    pass

    def recv_messages(self) -> Iterator[Dict[str, Any]]:
        """Yield messages from internal queue."""
        while self._connected or not self._message_queue.empty():
            try:
                message = self._message_queue.get(timeout=1.0)
                yield message
            except queue.Empty:
                if not self._connected:
                    break

    def close(self) -> None:
        """Close the SSE connection and HTTP session."""
        self._connected = False
        self._stop_event.set()

        if self._listen_thread:
            self._listen_thread.join(timeout=2.0)

        if self._session:
            self._session.close()
            self._session = None


class WebSocketTransport(BaseTransport):
    """
    Transport using WebSocket for bidirectional communication.
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._url = self.config.get("url", "")
        self._websocket: Optional[websocket.WebSocket] = None
        self._message_queue: queue.Queue = queue.Queue()
        self._listen_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
    
    def connect(self) -> None:
        """Establish WebSocket connection."""
        if not self._url:
            raise ValueError("WebSocket transport requires 'url' in config")
        
        self._websocket = websocket.create_connection(self._url)
        self._stop_event.clear()
        self._listen_thread = threading.Thread(target=self._listen_ws, daemon=True)
        self._listen_thread.start()
        self._connected = True
    
    def _listen_ws(self) -> None:
        """Listen for WebSocket messages."""
        assert self._websocket is not None
        
        while not self._stop_event.is_set():
            try:
                message = self._websocket.recv()
                if message:
                    try:
                        data = json.loads(message)
                        self._message_queue.put(data)
                    except json.JSONDecodeError:
                        pass
            except websocket.WebSocketConnectionClosedException:
                break
            except Exception:
                break
    
    def send_message(self, rpc_msg: Dict[str, Any]) -> None:
        """Send JSON-RPC message via WebSocket."""
        assert self._websocket is not None
        self._websocket.send(json.dumps(rpc_msg))
    
    def recv_messages(self) -> Iterator[Dict[str, Any]]:
        """Receive messages from queue."""
        while self._connected or not self._message_queue.empty():
            try:
                message = self._message_queue.get(timeout=1.0)
                yield message
            except queue.Empty:
                if not self._connected:
                    break
    
    def close(self) -> None:
        """Close the WebSocket connection."""
        self._connected = False
        self._stop_event.set()
        
        if self._listen_thread:
            self._listen_thread.join(timeout=2.0)
        
        if self._websocket:
            self._websocket.close()


def create_transport(config: Dict[str, Any]) -> BaseTransport:
    """
    Factory function to create transport based on configuration.
    
    :param config: MCP server configuration
    :return: Transport instance
    """
    transport_type = config.get("transport", "").lower()
    
    if transport_type == "stdio":
        return StdioTransport(config)
    elif transport_type in ("streamable-http", "streamable_http"):
        return StreamableHttpSseTransport(config)
    elif transport_type == "sse":
        return SseTransport(config)
    elif transport_type == "websocket":
        return WebSocketTransport(config)
    else:
        raise ValueError(f"Unsupported transport type: {transport_type}")
