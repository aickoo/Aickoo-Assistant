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


from pathlib import Path
import os
import importlib
from typing import Dict, Any, Callable, Optional, List
import inspect
from aickoo.internal.app.base import BasePlugin
import aickoo.logging as logging

def load_plugin_toolkits() -> []:
    plugins_dir = Path(os.getcwd()) / "plugins"
    if not plugins_dir.exists():
        return

    toolkits = []
    for item in plugins_dir.iterdir():
        if not item.is_dir():
            continue

        plugin_py = item / "plugin.py"
        if not plugin_py.exists():
            continue

        try:
            spec = importlib.util.spec_from_file_location(f"plugins.{item.name}.plugin", plugin_py)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BasePlugin) and obj is not BasePlugin:
                        # Register all tool kits provided by the plugin
                        for toolkit in obj.get_tool_kits():
                            toolkits.append(toolkit)
        except Exception as e:
            logging.error(f"Failed to load plugin {item.name}: {e}")

    return toolkits

def load_plugin_agents() -> dict:
    plugins_dir = Path(os.getcwd()) / "plugins"
    if not plugins_dir.exists():
        return

    agents = {}
    for item in plugins_dir.iterdir():
        if not item.is_dir():
            continue

        plugin_py = item / "plugin.py"
        if not plugin_py.exists():
            continue

        try:
            spec = importlib.util.spec_from_file_location(f"plugins.{item.name}.plugin", plugin_py)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BasePlugin) and obj is not BasePlugin:
                        # Register all tool kits provided by the plugin
                        for name, agent in obj.get_agent_dict():
                            agents[f'{name}'] = toolkit
        except Exception as e:
            logging.error(f"Failed to load plugin {item.name}: {e}")

    return agents
