#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.

Configuration management for Aickoo-Assistant
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

from pywin.framework.toolmenu import tools

from aickoo import logging


@dataclass
class ProviderConfig:
    """Configuration for an AI provider"""
    api_key: Optional[str] = None
    disabled: bool = False


@dataclass
class AgentConfig:
    """Configuration for an AI agent"""
    name: str = None
    model: str = "deepseek"
    role: str = "sub"
    prompt: str = "{content}"
    max_tokens: int = 5000
    reasoning_effort: Optional[str] = None
    description: str = ""
    prompt_extra_env: bool = True
    prompt_extra_lsp: bool = True
    prompt_path_flag: bool = False
    prompt_lsp_flag: bool = False
    skills: []=None
    tools: []=None
    mcp: []=None


@dataclass
class ShellConfig:
    """Configuration for shell"""
    path: str = "/bin/bash"
    args: list = field(default_factory=lambda: ["-l"])


@dataclass
class MCPServerConfig:
    """Configuration for MCP server"""
    type: str = "stdio"
    command: Optional[str] = None
    url: Optional[str] = None
    env: list = field(default_factory=list)
    args: list = field(default_factory=list)
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class LSPConfig:
    """Configuration for Language Server Protocol"""
    disabled: bool = False
    command: str = ""
    args: list = field(default_factory=list)


@dataclass
class Config:
    """Main configuration class"""
    data_directory: str = ".aickoo"
    providers: Dict[str, ProviderConfig] = field(default_factory=dict)
    ai_providers: Dict[str, Dict] = field(default_factory=dict)
    agents: Dict[str, AgentConfig] = field(default_factory=dict)
    shell: ShellConfig = field(default_factory=ShellConfig)
    mcp_servers: Dict[str, MCPServerConfig] = field(default_factory=dict)
    lsp: Dict[str, LSPConfig] = field(default_factory=dict)
    debug: bool = False
    debug_lsp: bool = False
    auto_compact: bool = True
    path_workspace: str = None
    path_skills: str = None
    runner: str = "标准编排器"


def get_config_paths(cwd: str) -> list:
    """Get list of possible config file paths in order of precedence"""
    paths = []
    
    # Local directory
    paths.append(Path(cwd) / "aickoo.json")
    
    # XDG config directory
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        paths.append(Path(xdg_config_home) / "aickoo" / "aickoo.json")
    else:
        # Fallback to ~/.config
        paths.append(Path.home() / ".config" / "aickooo" / "aickoo.json")
    
    # Home directory
    paths.append(Path.home() / "aickoo.json")
    
    return paths


def load_config(cwd: str, debug: bool = False) -> Config:
    """Load configuration from file"""
    config_paths = get_config_paths(cwd)
    
    config_data = {}
    config_file_path = None
    
    # Find first existing config file
    for path in config_paths:
        if path.exists():
            try:
                with open(path, "r", encoding='utf-8') as f:
                    config_data = json.load(f)
                config_file_path = path
                logging.info(f"Loaded configuration from {path}")
                break
            except json.JSONDecodeError as e:
                logging.warn(f"Failed to parse config file {path}: {e}")
            except Exception as e:
                logging.warn(f"Failed to read config file {path}: {e}")
    
    # Create config object
    config = Config()
    config.debug = debug or config_data.get("debug", False)
    config.debug_lsp = config_data.get("debugLSP", False)
    config.auto_compact = config_data.get("autoCompact", True)
    
    # Data directory
    if "data" in config_data and "directory" in config_data["data"]:
        config.data_directory = config_data["data"]["directory"]
    
    # Providers
    if "providers" in config_data:
        for provider_name, provider_config in config_data["providers"].items():
            config.providers[provider_name] = ProviderConfig(
                api_key=provider_config.get("apiKey"),
                disabled=provider_config.get("disabled", False)
            )

    # AI Providers (from ai section)
    if "ai" in config_data:
        for ai_name, ai_config in config_data["ai"].items():
            config.ai_providers[ai_name] = ai_config
            # config.ai_providers[ai_name] = {
            #     "base_url": ai_config.get("base_url"),
            #     "api_key": ai_config.get("api_key"),
            #     "model": ai_config.get("model")
            # }

    # Agents
    if "agents" in config_data:
        for agent_name, agent_config in config_data["agents"].items():
            config.agents[agent_name] = AgentConfig(
                name=agent_name,
                model=agent_config.get("model", "deepseek"),
                role=agent_config.get("role", "sub"),
                prompt=agent_config.get("prompt", "{content}"),
                max_tokens=agent_config.get("maxTokens", 5000),
                description=agent_config.get('description', ''),
                reasoning_effort=agent_config.get("reasoningEffort"),
                prompt_extra_env=agent_config.get("prompt_extra_env", True),
                prompt_extra_lsp=agent_config.get("prompt_extra_lsp", True),
                prompt_path_flag=agent_config.get("prompt_path_flag", False),
                prompt_lsp_flag=agent_config.get("prompt_lsp_flag", False),
                tools=agent_config.get("tools", []),
                skills=agent_config.get("skills", []),
                mcp=agent_config.get("mcp", [])
            )

    # Params
    if "params" in config_data:
        for param_name, param_value in config_data["params"].items():
            setattr(config, param_name, param_value)

        # set default value
        cwd = os.getcwd().replace("\\", "/")
        config.path_workspace = cwd if config.path_workspace is None else config.path_workspace
        config.path_skills = f"{cwd}/skills" if config.path_skills is None else config.path_skills
    
    # Shell
    if "shell" in config_data:
        shell_config = config_data["shell"]
        config.shell = ShellConfig(
            path=shell_config.get("path", "/bin/bash"),
            args=shell_config.get("args", ["-l"])
        )
    
    # MCP servers
    if "mcpServers" in config_data:
        for server_name, server_config in config_data["mcpServers"].items():
            config.mcp_servers[server_name] = MCPServerConfig(
                type=server_config.get("type", "stdio"),
                command=server_config.get("command"),
                url=server_config.get("url"),
                env=server_config.get("env", []),
                args=server_config.get("args", []),
                headers=server_config.get("headers", {})
            )
    
    # LSP
    if "lsp" in config_data:
        for language, lsp_config in config_data["lsp"].items():
            config.lsp[language] = LSPConfig(
                disabled=lsp_config.get("disabled", False),
                command=lsp_config.get("command", ""),
                args=lsp_config.get("args", [])
            )
    
    # Load environment variables for API keys
    load_env_variables(config)
    
    return config


def load_env_variables(config: Config) -> None:
    """Load API keys from environment variables"""
    env_mapping = {
        "ANTHROPIC_API_KEY": "anthropic",
        "OPENAI_API_KEY": "openai",
        "GEMINI_API_KEY": "gemini",
        "GITHUB_TOKEN": "copilot",
        "GROQ_API_KEY": "groq",
        "LOCAL_ENDPOINT": "local",
    }
    
    for env_var, provider_name in env_mapping.items():
        value = os.environ.get(env_var)
        if value:
            if provider_name not in config.providers:
                config.providers[provider_name] = ProviderConfig()
            config.providers[provider_name].api_key = value


def save_config(config: Config, path: Path) -> None:
    """Save configuration to file"""
    config_data = {
        "data": {
            "directory": config.data_directory
        },
        "debug": config.debug,
        "debugLSP": config.debug_lsp,
        "autoCompact": config.auto_compact
    }
    
    # Providers
    if config.providers:
        config_data["providers"] = {}
        for provider_name, provider_config in config.providers.items():
            config_data["providers"][provider_name] = {
                "apiKey": provider_config.api_key,
                "disabled": provider_config.disabled
            }
    
    # Agents
    if config.agents:
        config_data["agents"] = {}
        for agent_name, agent_config in config.agents.items():
            agent_data = {
                "model": agent_config.model,
                "maxTokens": agent_config.max_tokens
            }
            if agent_config.reasoning_effort:
                agent_data["reasoningEffort"] = agent_config.reasoning_effort
            config_data["agents"][agent_name] = agent_data
    
    # Shell
    if config.shell:
        config_data["shell"] = {
            "path": config.shell.path,
            "args": config.shell.args
        }
    
    # MCP servers
    if config.mcp_servers:
        config_data["mcpServers"] = {}
        for server_name, server_config in config.mcp_servers.items():
            server_data = {
                "type": server_config.type,
                "env": server_config.env,
                "args": server_config.args
            }
            if server_config.command:
                server_data["command"] = server_config.command
            if server_config.url:
                server_data["url"] = server_config.url
            if server_config.headers:
                server_data["headers"] = server_config.headers
            config_data["mcpServers"][server_name] = server_data
    
    # LSP
    if config.lsp:
        config_data["lsp"] = {}
        for language, lsp_config in config.lsp.items():
            config_data["lsp"][language] = {
                "disabled": lsp_config.disabled,
                "command": lsp_config.command,
                "args": lsp_config.args
            }
    
    # Ensure directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write config file
    with open(path, "w") as f:
        json.dump(config_data, f, indent=2)
    
    logging.info(f"Saved configuration to {path}")