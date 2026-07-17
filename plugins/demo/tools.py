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


from aickoo.internal.app.tools import BaseToolKit, Tool, ToolType


def greet_user(name: str) -> str:
    """Greet a user by name"""
    return f"Hello, {name}! Welcome to the demo plugin."


def calculate_sum(a: int, b: int) -> int:
    """Calculate the sum of two numbers"""
    return a + b


class GreetingToolKit(BaseToolKit):
    """Tool kit for greeting operations"""
    
    def __init__(self):
        super().__init__("greeting")
    
    def get_tools(self):
        return [
            Tool(
                name="greet_user",
                description="Greet a user by name",
                function=greet_user,
                parameters={
                    "name": {"type": "string", "description": "The name of the user to greet"}
                },
                type=ToolType.FUNCTION
            )
        ]


class CalculatorToolKit(BaseToolKit):
    """Tool kit for calculation operations"""
    
    def __init__(self):
        super().__init__("calculator")
    
    def get_tools(self):
        return [
            Tool(
                name="calculate_sum",
                description="Calculate the sum of two numbers",
                function=calculate_sum,
                parameters={
                    "a": {"type": "integer", "description": "The first number"},
                    "b": {"type": "integer", "description": "The second number"}
                },
                type=ToolType.FUNCTION
            )
        ]