#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.

MCP Transport Base Classes
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Iterator, Optional


class BaseTransport(ABC):
    """
    Abstract base class for MCP transports.
    
    All transport implementations must implement these methods.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._connected = False
    
    @property
    def connected(self) -> bool:
        return self._connected
    
    @abstractmethod
    def connect(self) -> None:
        """
        Establish connection:
        - stdio: spawn subprocess
        - http-sse: establish long connection
        - websocket: handshake
        """
        pass
    
    @abstractmethod
    def send_message(self, rpc_msg: Dict[str, Any]) -> None:
        """
        Send JSON-RPC message through the transport.
        """
        pass
    
    @abstractmethod
    def recv_messages(self) -> Iterator[Dict[str, Any]]:
        """
        Continuously receive messages from server.
        Returns an iterator of parsed JSON-RPC messages.
        """
        pass
    
    @abstractmethod
    def close(self) -> None:
        """
        Close the connection:
        - stdio: kill subprocess
        - http-sse/ws: disconnect
        """
        pass
