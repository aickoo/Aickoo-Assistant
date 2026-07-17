#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.

MCP Manager - Multi-client management with auto-discovery.

Handles:
- Auto-scan mcp.json files in plugin directories
- Manage multiple MCP client instances
- Aggregate tools from all MCP services
- Route tool calls to appropriate clients
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Any, List, Optional

from .client import McpClient


class McpManager:
    """
    Manager for multiple MCP clients.
    
    Features:
    - Auto-discovery of MCP plugins
    - Multi-client lifecycle management
    - Tool aggregation
    - Tool routing
    """
    
    def __init__(self, plugin_dirs: Optional[List[str]] = None):
        self._clients: Dict[str, McpClient] = {}
        self._plugin_dirs = plugin_dirs or []
        self.all_config = {}
        self._initialized = False
        
        # Default plugin directories
        default_dirs = [
            "mcp",
            # os.path.join(os.path.expanduser("~"), ".aickoo", "mcp_plugins"),
            # os.path.join(os.path.dirname(__file__), "plugins")
        ]
        self._plugin_dirs.extend(default_dirs)
        self._scan_plugins()
    
    @property
    def clients(self) -> Dict[str, McpClient]:
        """Get all managed MCP clients."""
        return self._clients
    
    @property
    def initialized(self) -> bool:
        """Check if manager is initialized."""
        return self._initialized
    
    def ensure_connected(self) -> None:
        """确保已连接所有 MCP 服务（延迟初始化）"""
        if not self._initialized:
            self.discover_and_connect_all()
            self._initialized = True

    def connect_one(self, name: str) -> tuple:
        """连接单个 MCP 服务"""
        config = self.all_config.get(name)
        if config is None:
            return name, None

        try:
            client = McpClient(config)
            client.connect()
            return name, client
        except Exception as e:
            print(f"Failed to connect to {name}: {e}")
            return name, None
    
    def discover_and_connect_all(self) -> None:
        """
        Discover MCP plugins and connect to all services.
        
        Recursively scans for mcp.json files and connects to each service.
        """
        configs = self._scan_plugins()

        # 使用线程池并发执行所有连接任务
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(self.connect_one, cfg['name']): cfg['name']
                for cfg in configs
            }
            
            for future in as_completed(futures):
                name, client = future.result()
                if client is not None:
                    self._clients[name] = client
                    print(f"Success to connect to MCP service: {name}")
    
    def _scan_plugins(self) -> List[Dict[str, Any]]:
        """
        Scan all plugin directories for mcp.json files.
        
        :return: List of MCP configurations
        """
        self.all_config = {}
        
        for plugin_dir in self._plugin_dirs:
            path = Path(plugin_dir)
            if not path.exists():
                continue
            
            # Recursively find all mcp.json files
            for json_file in path.rglob("mcp.json"):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        # Add path context
                        config["_config_path"] = str(json_file.parent)
                        self.all_config[config["name"]] = config
                except json.JSONDecodeError as e:
                    print(f"Invalid mcp.json: {json_file} - {e}")
                except Exception as e:
                    print(f"Error reading {json_file}: {e}")
        
        return list(self.all_config.values())
    
    def get_all_tools(self) -> List[Dict[str, Any]]:
        """
        Get aggregated tools from all connected MCP services.
        
        :return: List of tool schemas with service prefixes
        """
        all_tools = []
        
        for client_name, client in self._clients.items():
            if client.initialized:
                all_tools.extend(client.get_tool_schema(prefix=True))
        
        return all_tools

    def get_client_tools(self, name: str) -> List[Dict[str, Any]]:
        """
        Get aggregated tools from all connected MCP services.

        :return: List of tool schemas with service prefixes
        """
        all_tools = []

        for client_name, client in self._clients.items():
            if client_name == name and client.initialized:
                all_tools.extend(client.get_tool_schema(prefix=True))

        return all_tools
    
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call a tool on the appropriate MCP service.
        
        :param tool_name: Tool name with prefix (e.g., "service---tool")
        :param arguments: Tool arguments
        :return: Tool result
        """
        # Parse service name and tool name using '---' separator.
        if "---" in tool_name:
            service_name, tool = tool_name.split("---", 1)
        else:
            # Try to find the tool in any service
            return self._find_and_call_tool(tool_name, arguments)
        
        # Check if service exists
        if service_name not in self._clients:
            raise ValueError(f"MCP service not found: {service_name}")
        
        client = self._clients[service_name]
        return client.call_tool(tool, arguments)
    
    def _find_and_call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Find and call tool without service prefix.
        
        :param tool_name: Tool name without prefix
        :param arguments: Tool arguments
        :return: Tool result
        """
        for client_name, client in self._clients.items():
            if client.initialized:
                tool_names = [t["name"] for t in client.tools]
                if tool_name in tool_names:
                    return client.call_tool(tool_name, arguments)
        
        raise ValueError(f"Tool not found in any MCP service: {tool_name}")
    
    def close_all(self) -> None:
        """Close all MCP client connections."""
        for client in self._clients.values():
            try:
                client.close()
            except Exception as e:
                print(f"Error closing client: {e}")
        self._clients.clear()
    
    def get_service_info(self) -> List[Dict[str, Any]]:
        """Get information about all connected MCP services."""
        info = []
        for name, client in self._clients.items():
            info.append({
                "name": name,
                "transport": client.config.get("transport", "unknown"),
                "initialized": client.initialized,
                "tool_count": len(client.tools)
            })
        return info
