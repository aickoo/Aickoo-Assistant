#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.
"""


from abc import ABC, abstractmethod
from typing import List
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, Callable, Optional, List


class ToolType(Enum):
    """Types of tools"""
    FILE = "file"
    CODE = "code"
    SYSTEM = "system"
    EXTERNAL = "external"
    FUNCTION = "function"  # 目前schema里只有这个选项


@dataclass
class Tool:
    """A tool that can be called by the AI"""
    name: str
    description: str
    function: Callable
    parameters: Dict[str, Dict[str, Any]]
    type: ToolType = ToolType.FUNCTION
    requires_permission: bool = True


class BaseToolKit(ABC):
    """Abstract base class for tool kits"""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def get_tools(self) -> List[Tool]:
        """Get all tools in this tool kit"""
        pass


class BasePlugin(ABC):
    """Abstract base class for plugins"""

    @staticmethod
    @abstractmethod
    def get_tool_kits() -> List[BaseToolKit]:
        """Get all tool kits provided by this plugin"""
        pass

    @staticmethod
    @abstractmethod
    def get_agent_dict() -> Dict:
        """Get all agents provided by this plugin"""
        pass

