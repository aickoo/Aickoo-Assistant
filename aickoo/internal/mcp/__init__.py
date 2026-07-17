#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.


MCP (Model Context Protocol) Client Framework
Core components:
- BaseTransport: Abstract transport interface
- McpClient: MCP protocol client
- McpManager: Multi-client manager with auto-discovery
"""

from .base import BaseTransport
from .transports import StdioTransport, StreamableHttpSseTransport, SseTransport, WebSocketTransport, create_transport
from .client import McpClient
from .manager import McpManager

__all__ = [
    "BaseTransport",
    "StdioTransport",
    "StreamableHttpSseTransport",
    "SseTransport",
    "WebSocketTransport",
    "create_transport",
    "McpClient",
    "McpManager"
]