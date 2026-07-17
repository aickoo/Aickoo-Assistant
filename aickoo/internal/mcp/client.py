#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.

MCP Client Implementation
Handles MCP protocol handshake, tool discovery, and RPC calls.
"""
import json
import queue
import threading
import uuid
from typing import Dict, Any, List, Optional, Callable

from .base import BaseTransport
from .transports import create_transport


class McpClient:
    """
    MCP Protocol Client.
    
    Handles:
    - Connection establishment
    - Protocol handshake (initialize/initialized)
    - Tool discovery (tools/list)
    - Tool invocation (tools/call)
    - Event handling (logs, notifications)
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.name = config.get("name", "mcp_client")
        self.transport: BaseTransport = create_transport(config)
        
        self._tools: List[Dict[str, Any]] = []
        self._callbacks: Dict[str, Dict[str, Any]] = {}  # {id: {"result": ..., "event": Event}}
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._initialized = False
        self._lock = threading.Lock()
    
    @property
    def tools(self) -> List[Dict[str, Any]]:
        """Get the list of available tools."""
        return self._tools
    
    @property
    def initialized(self) -> bool:
        """Check if client is initialized."""
        return self._initialized
    
    def connect(self) -> None:
        """Establish connection and perform MCP handshake."""
        # 1. Connect transport
        self.transport.connect()
        
        # 2. Perform handshake
        self._handshake()
        
        # 3. Discover tools
        self._discover_tools()
    
    def _handshake(self) -> None:
        """Perform MCP protocol handshake."""
        # Send initialize request
        init_request = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "clientInfo": {
                    "name": "Aickoo-Assistant",
                    "version": "1.0.0"
                },
                "capabilities": {}
            }
        }

        result = self._send_request(init_request)
        self._initialized = True

        # Send initialized notification（无id，纯通知）
        self.transport.send_message({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {}
        })
    
    def _discover_tools(self) -> None:
        """Discover available tools from the MCP server."""
        request = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/list",
            "params": {}
        }
        
        result = self._send_request(request)
        self._tools = result.get("tools", [])
    
    def _send_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Send a JSON-RPC request and wait for response."""
        request_id = request["id"]
        timeout = self.config.get("config", {}).get("timeout", 30)
        
        # Create event and callback entry
        event = threading.Event()
        with self._lock:
            self._callbacks[request_id] = {"event": event, "result": None, "error": None}
        
        try:
            # Send message (this will also receive the response for StreamableHttpSseTransport)
            self.transport.send_message(request)
            
            # For StreamableHttpSseTransport, the response is already in the queue
            # Poll the transport's message queue for our response
            start_time = __import__("time").time()
            while True:
                # Check if we already have the response
                with self._lock:
                    if request_id in self._callbacks:
                        cb = self._callbacks[request_id]
                        if cb["result"] is not None or cb["error"] is not None:
                            break
                
                # Try to get message from transport's queue
                try:
                    for message in self.transport.recv_messages():
                        self._handle_message(message)
                        # Check if this was our response
                        with self._lock:
                            if request_id in self._callbacks:
                                cb = self._callbacks[request_id]
                                if cb["result"] is not None or cb["error"] is not None:
                                    break
                except Exception:
                    pass
                
                # Check timeout
                if __import__("time").time() - start_time > timeout:
                    raise TimeoutError(
                        f"MCP request timed out after {timeout}s: "
                        f"{request.get('method')} (id={request_id})"
                    )
                
                # Small sleep to avoid busy waiting
                __import__("time").sleep(0.01)
            
            # Get result
            with self._lock:
                cb = self._callbacks.pop(request_id, None)
            
            if cb is None:
                raise RuntimeError(f"Callback for request {request_id} not found")
            
            if cb["error"]:
                raise cb["error"]
            
            return cb["result"] or {}
        except Exception:
            with self._lock:
                self._callbacks.pop(request_id, None)
            raise
    
    def _handle_message(self, message: Dict[str, Any]) -> None:
        """Handle incoming JSON-RPC message."""
        # Handle response messages
        if "id" in message:
            msg_id = message["id"]
            with self._lock:
                if msg_id in self._callbacks:
                    cb = self._callbacks[msg_id]
                    if "error" in message:
                        err = message["error"]
                        cb["error"] = Exception(f"[{err.get('code')}] {err.get('message', 'Unknown error')}")
                    else:
                        cb["result"] = message.get("result", {})
        
        # Handle notification messages
        if "method" in message:
            method = message["method"]
            params = message.get("params", {})
            
            # Handle log notifications
            if method == "log":
                self._handle_log(params)
            # Handle tool result notifications
            elif method == "tool_result":
                self._handle_tool_result(params)
            # Handle generic notifications
            else:
                self._handle_notification(method, params)
    
    def _handle_log(self, params: Dict[str, Any]) -> None:
        """Handle log notification."""
        level = params.get("level", "info")
        message = params.get("message", "")
        print(f"[MCP:{self.name}] [{level}] {message}")
    
    def _handle_tool_result(self, params: Dict[str, Any]) -> None:
        """Handle tool result notification."""
        # Can be used for async tool results
        pass
    
    def _handle_notification(self, method: str, params: Dict[str, Any]) -> None:
        """Handle generic notification."""
        if method in self._event_handlers:
            for handler in self._event_handlers[method]:
                try:
                    handler(params)
                except Exception as e:
                    print(f"Event handler error: {e}")
    
    def on_event(self, event: str, handler: Callable) -> None:
        """Register an event handler."""
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)
    
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call a tool on the MCP server.
        
        :param tool_name: Name of the tool to call
        :param arguments: Tool arguments
        :return: Tool result
        """
        request = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        try:
            result = self._send_request(request)
            return result
        except Exception as e:
            # 检查是否是 session 过期错误
            error_str = str(e)
            if "401" in error_str or "SessionExpired" in error_str or ("session" in error_str.lower() and "expir" in error_str.lower()):
                print(f"[MCP:{self.name}] Session expired, reinitializing...")
                # 重置 session-id
                if hasattr(self.transport, 'reset_session_id'):
                    self.transport.reset_session_id()
                # 重新进行 handshake
                self._handshake()
                # 重新发现工具
                self._discover_tools()
                # 重新执行工具调用
                result = self._send_request(request)
                return result
            raise
    
    def close(self) -> None:
        """Close the client connection."""
        self.transport.close()
    
    @staticmethod
    def _normalize_parameters(params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize MCP parameter schema to OpenAI function parameters format.
        OpenAI expects: {"type": "object", "properties": {...}, "required": [...]}
        """
        if not params:
            return {"type": "object", "properties": {}}

        # If params itself has properties, use it directly.
        # Some servers put the full JSON schema as the value of 'properties'.
        # We distinguish by checking whether params.properties looks like
        # the actual object schema (has its own properties/type) or is just
        # the property definitions.
        raw_props = params.get("properties", {})
        if isinstance(raw_props, dict):
            if "properties" in raw_props or raw_props.get("type") == "object":
                # params.properties is a wrapped object schema: unwrap it.
                return {
                    "type": "object",
                    "properties": raw_props.get("properties", {}),
                    "required": raw_props.get("required", [])
                }
            # params.properties is the actual property definitions.
            return {
                "type": "object",
                "properties": raw_props,
                "required": params.get("required", [])
            }

        return {"type": "object", "properties": {}}

    def get_tool_schema(self, prefix: bool = True) -> List[Dict[str, Any]]:
        """
        Get tool schemas in OpenAI format.
        
        :param prefix: Whether to prefix tool names with client name
        :return: List of tool schemas
        """
        schemas = []
        for tool in self._tools:
            # OpenAI requires function names to match ^[a-zA-Z0-9_-]+$
            # Use '---' as separator between service and tool name.
            name = f"{self.name}---{tool['name']}" if prefix else tool['name']
            raw_params = tool.get("parameters") or tool.get("inputSchema") or {}
            params = self._normalize_parameters(raw_params)
            schemas.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool.get("description", ""),
                    "parameters": params
                }
            })
        return schemas
