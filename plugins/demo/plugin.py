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


from typing import List, Dict
from aickoo.internal.app.tools import BaseToolKit
from aickoo.internal.app.base import BasePlugin
from .tools import GreetingToolKit, CalculatorToolKit


class Plugin(BasePlugin):
    """Demo plugin implementation"""
    
    @staticmethod
    def get_tool_kits() -> List[BaseToolKit]:
        """Get all tool kits provided by this plugin"""
        return [
            GreetingToolKit(),
            CalculatorToolKit()
        ]
    
    @staticmethod
    def get_agent_dict() -> Dict:
        """Get all agents provided by this plugin"""
        return {}