#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.

Tool system for Aickoo-Assistant
"""
import os.path
from typing import Dict, Any, Callable, Optional, List
from enum import Enum
import ast
import glob
import base64
import asyncio
from aickoo.internal.util.utils import get_current_path
from aickoo.internal.app.skills import SkillFactory, Skill
from aickoo.internal.app.llm import volcengine_generate_image, volcengine_image_qa_client
from aickoo.internal.app.excel_tools import ExcelTool
from pathlib import Path
import subprocess
import shlex
import requests
import threading
import json
import concurrent
import aickoo.logging as logging
import re
from aickoo.internal.mcp import McpManager
import time
import importlib.util
import inspect
from abc import ABC, abstractmethod
from aickoo.internal.app.plugins import load_plugin_toolkits
from aickoo.internal.app.base import Tool, ToolType, BaseToolKit

class ToolRegistry:
    """Registry for managing tools"""
    
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
    
    def register(self, tool: Tool) -> None:
        """Register a tool"""
        self._tools[tool.name] = tool
    
    def unregister(self, name: str) -> bool:
        """Unregister a tool"""
        if name in self._tools:
            del self._tools[name]
            return True
        return False
    
    def get_tool(self, name: str) -> Optional[Tool]:
        """Get a tool by name"""
        return self._tools.get(name, None)
    
    def get_tools(self) -> List[Dict[str, Any]]:
        """Get all tools in a format suitable for LLMs"""
        tools = []
        for tool in self._tools.values():
            params = tool.parameters
            # MCP tools register the complete OpenAI schema object.
            # Legacy tools register only the property definitions.
            if isinstance(params, dict) and params.get("type") == "object" and "properties" in params:
                parameters = params
            else:
                parameters = {
                    "type": "object",
                    "properties": params
                }
            tool_def = {
                "type": tool.type.value,
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": parameters
                }
            }
            tools.append(tool_def)
        return tools
    
    def execute(self, name: str, **kwargs) -> Any:
        """Execute a tool"""
        tool = self.get_tool(name)
        if not tool:
            # raise ValueError(f"Tool not found: {name}")
            return f"Tool not found: {name}"
        
        # Validate parameters
        self._validate_parameters(tool, kwargs)
        
        # Execute tool
        return tool.function(**kwargs)
    
    def _validate_parameters(self, tool: Tool, provided_params: Dict[str, Any]) -> None:
        """Validate provided parameters against tool definition"""
        params = tool.parameters

        # If parameters is a complete OpenAI schema object, extract properties and required.
        if isinstance(params, dict) and params.get("type") == "object" and "properties" in params:
            properties = params.get("properties", {})
            required = params.get("required", [])
        else:
            # Legacy flat parameters dict.
            properties = params
            required = [name for name, defn in params.items()
                       if isinstance(defn, dict) and not defn.get("optional", False)]

        # Check required parameters
        for param_name in required:
            if param_name not in provided_params:
                raise ValueError(f"Missing required parameter: {param_name}")

        # Check for unknown parameters
        for param_name in provided_params:
            if param_name not in properties:
                raise ValueError(f"Unknown parameter: {param_name}")


class ToolKitRegistry:
    """Registry for managing tool kits"""
    
    _tool_kits: Dict[str, BaseToolKit] = {}
    _initialized = False
    
    @classmethod
    def _ensure_initialized(cls):
        """Ensure default tool kits are registered"""
        if not cls._initialized:
            cls._tool_kits = {}
            cls._register_default_tool_kits()
            cls._register_plugin_tool_kits()
            cls._initialized = True
    
    @classmethod
    def _register_toolkit(cls, toolkit: BaseToolKit) -> None:
        """Register a tool kit"""
        cls._tool_kits[toolkit.name] = toolkit
    
    @classmethod
    def get_toolkit(cls, name: str) -> Optional[BaseToolKit]:
        """Get a tool kit by name"""
        cls._ensure_initialized()
        return cls._tool_kits.get(name, None)
    
    @classmethod
    def get_tools_by_name(cls, name: str) -> List[Tool]:
        """Get all tools from a tool kit by name"""
        toolkit = cls.get_toolkit(name)
        if toolkit:
            return toolkit.get_tools()
        return []
    
    @classmethod
    def get_all_kits(cls) -> List[BaseToolKit]:
        """Get all registered tool kits"""
        cls._ensure_initialized()
        return list(cls._tool_kits.values())
    
    @classmethod
    def _register_default_tool_kits(cls):
        """Register all default tool kits"""
        cls._register_toolkit(GlobToolKit())
        cls._register_toolkit(ReadToolKit())
        cls._register_toolkit(WriteToolKit())
        cls._register_toolkit(PowershellToolKit())
        cls._register_toolkit(SubagentToolKit())
        cls._register_toolkit(GenerateImageToolKit())
        cls._register_toolkit(ImageQAToolKit())
        cls._register_toolkit(VerifyToolKit())
        cls._register_toolkit(CdpToolKit())
        cls._register_toolkit(ExcelToolKit())
    
    @classmethod
    def _register_plugin_tool_kits(cls):
        toolkits = load_plugin_toolkits()
        for toolkit in toolkits:
            cls._register_toolkit(toolkit)


class GlobToolKit(BaseToolKit):
    """Tool kit for file glob operations"""
    
    def __init__(self):
        super().__init__("glob")
    
    def get_tools(self) -> List[Tool]:
        return [ToolFactory.create_tool_glob()]


class ReadToolKit(BaseToolKit):
    """Tool kit for file reading operations"""
    
    def __init__(self):
        super().__init__("read")
    
    def get_tools(self) -> List[Tool]:
        return [ToolFactory.create_tool_read()]


class WriteToolKit(BaseToolKit):
    """Tool kit for file writing operations"""
    
    def __init__(self):
        super().__init__("write")
    
    def get_tools(self) -> List[Tool]:
        return [ToolFactory.create_tool_write()]


class PowershellToolKit(BaseToolKit):
    """Tool kit for powershell commands"""
    
    def __init__(self):
        super().__init__("powershell")
    
    def get_tools(self) -> List[Tool]:
        return [ToolFactory.create_tool_powershell()]


class SubagentToolKit(BaseToolKit):
    """Tool kit for sub-agent operations"""
    
    def __init__(self):
        super().__init__("subagent")
    
    def get_tools(self) -> List[Tool]:
        return [ToolFactory.create_tool_agent()]


class GenerateImageToolKit(BaseToolKit):
    """Tool kit for image generation"""
    
    def __init__(self):
        super().__init__("generate_image")
    
    def get_tools(self) -> List[Tool]:
        return [ToolFactory.create_tool_generate_image()]


class ImageQAToolKit(BaseToolKit):
    """Tool kit for image question answering"""
    
    def __init__(self):
        super().__init__("image_qa")
    
    def get_tools(self) -> List[Tool]:
        return [ToolFactory.create_tool_image_qa()]


class VerifyToolKit(BaseToolKit):
    """Tool kit for verification"""
    
    def __init__(self):
        super().__init__("verify")
    
    def get_tools(self) -> List[Tool]:
        return [ToolFactory.create_tool_verify()]


class CdpToolKit(BaseToolKit):
    """Tool kit for CDP browser operations"""
    
    def __init__(self):
        super().__init__("cdp")
    
    def get_tools(self) -> List[Tool]:
        return ToolFactory.create_tool_cdp()


class ExcelToolKit(BaseToolKit):
    """Tool kit for Excel operations"""
    
    def __init__(self):
        super().__init__("excel")
    
    def get_tools(self) -> List[Tool]:
        return ToolFactory.create_tool_excel()


class McpToolKit(BaseToolKit):
    """Tool kit for MCP services"""
    
    def __init__(self, allowed_mcp: Optional[List[str]] = None):
        super().__init__("mcp")
        self.allowed_mcp = allowed_mcp
    
    def get_tools(self) -> List[Tool]:
        return ToolFactory.create_tool_mcp(allowed_mcp=self.allowed_mcp)


class ToolFactory:
    _cdp_event_loop = None
    _cdp_loop_thread = None
    _mcp_manager = None  # 延迟初始化

    @classmethod
    def _get_mcp_manager(cls):
        """获取或创建 MCP 管理器（延迟初始化）"""
        if cls._mcp_manager is None:
            cls._mcp_manager = McpManager()
        return cls._mcp_manager



    @classmethod
    def _ensure_cdp_event_loop(cls):
        if cls._cdp_event_loop is not None and not cls._cdp_event_loop.is_closed() and cls._cdp_event_loop.is_running():
            return cls._cdp_event_loop
            
        if cls._cdp_event_loop is not None and not cls._cdp_event_loop.is_closed():
            cls._cdp_event_loop.close()
            
        cls._cdp_event_loop = asyncio.new_event_loop()
        cls._cdp_loop_thread = threading.Thread(
            target=cls._cdp_event_loop.run_forever,
            daemon=True
        )
        cls._cdp_loop_thread.start()
        
        while not cls._cdp_event_loop.is_running():
            pass
            
        return cls._cdp_event_loop


    @staticmethod
    def create_tool_glob():
        return Tool(
            name="glob",
            description="Find files by pattern",
            function=ToolFactory._glob_tool,
            parameters={
                "pattern": {"type": "string", "description": "File pattern to match"},
                "path": {"type": "string", "description": "Directory to search in", "optional": True}
            }
        )

    @staticmethod
    def create_tool_read():
        return Tool(
            name="read",
            description="Read file contents",
            function=ToolFactory._read_tool,
            parameters={
                "file_path": {"type": "string", "description": "Path to file to read"},
                "offset": {"type": "integer", "description": "Line offset", "optional": True},
                "limit": {"type": "integer", "description": "Number of lines, the recommended range is between 200 and 500.", "optional": True}
            }
        )

    @staticmethod
    def create_tool_write():
        return Tool(
            name="write",
            description="Write to file",
            function=ToolFactory._write_tool,
            parameters={
                "file_path": {"type": "string", "description": "Path to file to write"},
                "content": {"type": "string", "description": "Content to write"}
            }
        )

    @staticmethod
    def create_tool_powershell():
        return Tool(
            name="powershell",
            description="Execute powershell command",
            function=ToolFactory._powershell_tool,
            parameters={
                "command": {"type": "string", "description": "String of command with all parameters to be execute"},
                "cwd": {"type": "string", "description": "absolute path of current work directory", "optional": True},
                "timeout": {"type": "integer", "description": "Timeout in milliseconds, at least 60000", "optional": True}
            }
        )

    @staticmethod
    def create_tool_agent():
        return Tool(
            name="agent",
            description="Launch a new sub-agent with read-only tools",
            function=ToolFactory._agent_tool,
            parameters={
                "prompt": {"type": "string", "description": "prompt to execute"}
            }
        )

    @staticmethod
    def create_tool_generate_image():
        return Tool(
            name="generate_pic",
            description="Generate image using a multimodal model and save them locally",
            function=ToolFactory._generate_image_tool,
            parameters={
                "prompt": {"type": "string", "description": "String of prompt for image generation"},
                "generated_img_path": {"type": "string", "description": "Local storage path for images generated"},
                "reference_img_path": {"type": "string", "description": "Local storage path of images for reference", "optional": True}
            }
        )

    @staticmethod
    def create_tool_image_qa():
        return Tool(
            name="image_qa",
            description="Answer questions based on the image",
            function=ToolFactory._image_qa_tool,
            parameters={
                "prompt": {"type": "string", "description": "Prompts for image-based question and answer"},
                "reference_img_path": {"type": "string", "description": "Local storage path of images for reference"},
                "file_id": {"type": "string", "description": "If an image has been submitted before, there will be a file ID that can be used for reuse, but the file_id will expire 3 days after created.", "optional": True}
            }
        )

    @staticmethod
    def create_tool_verify():
        return Tool(
            name="verify",
            description="Perform adversarial verification of code or system design",
            function=ToolFactory._verify_tool,
            parameters={
                "type": {"type": "string", "description": "Type of verification: 'code' or 'design'"},
                "content": {"type": "string", "description": "Code or design description to verify"},
                "language": {"type": "string", "description": "Programming language (for code verification)",
                             "optional": True},
                "context": {"type": "string", "description": "Additional context", "optional": True}
            }
        )

    @staticmethod
    def create_tool_mcp(allowed_mcp: Optional[List[str]] = None):
        """创建 MCP 工具集合。allowed_mcp 为白名单服务名列表，None 表示不限制（兼容旧用法）。"""
        mcp_tools = []
    
        try:
            mcp_manager = ToolFactory._get_mcp_manager()
            mcp_manager.ensure_connected()
        except Exception as e:
            print(f"Failed to connect MCP services: {e}")
            return mcp_tools
        
        _allowed = list(allowed_mcp) if allowed_mcp is not None else None
        for mcp_name in allowed_mcp:
            mcp_tool_schemas = mcp_manager.get_client_tools(mcp_name)
            for mcp_tool_schema in mcp_tool_schemas:
                if mcp_tool_schema.get('type', None) != 'function' or mcp_tool_schema.get('function', None) is None:
                    continue
                function = mcp_tool_schema.get('function')
                tool_name = function["name"]

                # Create a closure that binds tool_name and allowed_mcp.
                # The agent calls execute(name=..., **kwargs) where kwargs are
                # the actual tool arguments (e.g. query=..., count=...).
                def _make_bound_call(_tool_name, _allowed):
                    def _bound_call(**kwargs) -> Dict[str, Any]:
                        return ToolFactory._mcp_tool_call(_tool_name, kwargs, allowed_mcp=_allowed)
                    return _bound_call

                mcp_tools.append(Tool(
                    name=tool_name,
                    description=function["description"],
                    function=_make_bound_call(tool_name, _allowed),
                    parameters=function["parameters"]
                ))
            
        return mcp_tools

    @staticmethod
    def _verify_tool(type: str, content: str, language: str = "python", context: str = "") -> dict:
        """Execute verification tool"""
        try:
            # Import here to avoid circular dependencies
            from aickoo.internal.app.agents import MessageManager
            from aickoo.internal.db import Database
            from aickoo.internal.config import load_config
            from aickoo.internal.app.verification_agent import VerificationAgent
            from aickoo.internal.app.permissions import Permissions
            import os

            # Load configuration
            config = load_config(os.getcwd())

            # Create database connection
            db = Database(config)
            db.connect()

            # Create message manager
            message_manager = MessageManager(db)

            # Create permissions
            permissions = Permissions()

            # Create verification agent config
            from aickoo.internal.config import AgentConfig
            agent_config = AgentConfig(
                name="verification",
                model="deepseek",
                role="verification",
                prompt="You are a Verification Agent specialized in adversarial testing and security verification.",
                max_tokens=15000,
                tools=["glob", "read", "verify"]
            )

            # Create verification agent
            agent = VerificationAgent(agent_config, permissions, message_manager, db)

            # Perform verification based on type
            if type == "code":
                result = agent.verify_code(content, language, context)
            elif type == "design":
                result = agent.verify_system_design(content, context)
            else:
                return {"error": "Invalid verification type. Use 'code' or 'design'"}

            return {"result": result}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def create_tool_cdp():
        """创建 CDP 浏览器工具集合"""
        cdp_tools = []
        
        # ==================== 标签页管理类工具 ====================
        cdp_tools.append(Tool(
            name="browser_list_tabs",
            description="列出所有浏览器标签页，返回每个标签页的 target_id、标题、URL 等信息",
            function=ToolFactory._browser_list_tabs_tool,
            parameters={}
        ))
        
        cdp_tools.append(Tool(
            name="browser_new_tab",
            description="创建新标签页",
            function=ToolFactory._browser_new_tab_tool,
            parameters={
                "url": {"type": "string", "description": "新标签页的初始 URL", "optional": True}
            }
        ))
        
        # ==================== 导航类工具 ====================
        cdp_tools.append(Tool(
            name="browser_search",
            description="在浏览器中搜索并导航到指定 URL",
            function=ToolFactory._browser_navigate_tool,
            parameters={
                "url": {"type": "string", "description": "目标 URL 或搜索关键词"},
                "target_id": {"type": "string", "description": "目标标签页 ID，为空则使用当前活动标签页", "optional": True}
            }
        ))
        
        cdp_tools.append(Tool(
            name="browser_navigate",
            description="导航到指定 URL",
            function=ToolFactory._browser_navigate_tool,
            parameters={
                "url": {"type": "string", "description": "目标 URL"},
                "target_id": {"type": "string", "description": "目标标签页 ID，为空则使用当前活动标签页", "optional": True}
            }
        ))
        
        cdp_tools.append(Tool(
            name="browser_go_back",
            description="返回上一页",
            function=ToolFactory._browser_go_back_tool,
            parameters={
                "target_id": {"type": "string", "description": "目标标签页 ID，为空则使用当前活动标签页", "optional": True}
            }
        ))
        
        cdp_tools.append(Tool(
            name="browser_switch_tab",
            description="切换到指定的浏览器标签页",
            function=ToolFactory._browser_switch_tab_tool,
            parameters={
                "target_id": {"type": "string", "description": "目标标签页 ID"}
            }
        ))
        
        cdp_tools.append(Tool(
            name="browser_close_tab",
            description="关闭指定的浏览器标签页",
            function=ToolFactory._browser_close_tab_tool,
            parameters={
                "target_id": {"type": "string", "description": "要关闭的标签页 ID，为空则关闭当前标签页", "optional": True}
            }
        ))
        
        # ==================== 元素交互类工具 ====================
        cdp_tools.append(Tool(
            name="browser_click",
            description="点击页面上的指定元素",
            function=ToolFactory._browser_click_tool,
            parameters={
                "selector": {"type": "string", "description": "CSS 选择器"},
                "target_id": {"type": "string", "description": "目标标签页 ID，为空则使用当前活动标签页", "optional": True}
            }
        ))
        
        cdp_tools.append(Tool(
            name="browser_input",
            description="在输入框中输入文本",
            function=ToolFactory._browser_input_tool,
            parameters={
                "selector": {"type": "string", "description": "CSS 选择器"},
                "text": {"type": "string", "description": "要输入的文本"},
                "target_id": {"type": "string", "description": "目标标签页 ID，为空则使用当前活动标签页", "optional": True}
            }
        ))
        
        cdp_tools.append(Tool(
            name="browser_upload_file",
            description="上传文件到指定输入框",
            function=ToolFactory._browser_upload_file_tool,
            parameters={
                "selector": {"type": "string", "description": "CSS 选择器"},
                "file_path": {"type": "string", "description": "要上传的文件路径"},
                "target_id": {"type": "string", "description": "目标标签页 ID，为空则使用当前活动标签页", "optional": True}
            }
        ))
        
        cdp_tools.append(Tool(
            name="browser_scroll",
            description="滚动页面到指定位置",
            function=ToolFactory._browser_scroll_tool,
            parameters={
                "x": {"type": "integer", "description": "水平滚动位置", "optional": True},
                "y": {"type": "integer", "description": "垂直滚动位置", "optional": True},
                "selector": {"type": "string", "description": "滚动到指定元素", "optional": True},
                "target_id": {"type": "string", "description": "目标标签页 ID，为空则使用当前活动标签页", "optional": True}
            }
        ))
        
        cdp_tools.append(Tool(
            name="browser_send_keys",
            description="发送键盘按键",
            function=ToolFactory._browser_send_keys_tool,
            parameters={
                "keys": {"type": "string", "description": "按键组合，如 'Ctrl+A', 'Enter'"},
                "target_id": {"type": "string", "description": "目标标签页 ID，为空则使用当前活动标签页", "optional": True}
            }
        ))
        
        cdp_tools.append(Tool(
            name="browser_get_dropdown_options",
            description="获取下拉框的所有选项",
            function=ToolFactory._browser_get_dropdown_options_tool,
            parameters={
                "selector": {"type": "string", "description": "下拉框的 CSS 选择器"},
                "target_id": {"type": "string", "description": "目标标签页 ID，为空则使用当前活动标签页", "optional": True}
            }
        ))
        
        cdp_tools.append(Tool(
            name="browser_select_dropdown",
            description="选择下拉框的指定选项",
            function=ToolFactory._browser_select_dropdown_tool,
            parameters={
                "selector": {"type": "string", "description": "下拉框的 CSS 选择器"},
                "option_value": {"type": "string", "description": "要选择的选项值或文本"},
                "target_id": {"type": "string", "description": "目标标签页 ID，为空则使用当前活动标签页", "optional": True}
            }
        ))
        
        # ==================== 页面操作类工具 ====================
        cdp_tools.append(Tool(
            name="browser_wait",
            description="等待指定时间",
            function=ToolFactory._browser_wait_tool,
            parameters={
                "seconds": {"type": "integer", "description": "等待的秒数，最少7秒"}
            }
        ))
        
        # cdp_tools.append(Tool(
        #     name="browser_screenshot",
        #     description="捕获页面截图",
        #     function=ToolFactory._browser_screenshot_tool,
        #     parameters={
        #         "format": {"type": "string", "description": "图片格式 (png, jpeg, webp)", "optional": True},
        #         "quality": {"type": "integer", "description": "图片质量 (0-100)", "optional": True},
        #         "save_path": {"type": "string", "description": "保存路径", "optional": True},
        #         "target_id": {"type": "string", "description": "目标标签页 ID，为空则使用当前活动标签页", "optional": True}
        #     }
        # ))
        #
        # cdp_tools.append(Tool(
        #     name="browser_save_as_pdf",
        #     description="将页面保存为 PDF",
        #     function=ToolFactory._browser_save_as_pdf_tool,
        #     parameters={
        #         "save_path": {"type": "string", "description": "PDF 保存路径"},
        #         "landscape": {"type": "boolean", "description": "是否横向", "optional": True},
        #         "target_id": {"type": "string", "description": "目标标签页 ID，为空则使用当前活动标签页", "optional": True}
        #     }
        # ))
        #
        # cdp_tools.append(Tool(
        #     name="browser_extract",
        #     description="提取页面内容为 Markdown 格式",
        #     function=ToolFactory._browser_extract_tool,
        #     parameters={
        #         "selector": {"type": "string", "description": "提取指定元素的内容", "optional": True},
        #         "target_id": {"type": "string", "description": "目标标签页 ID，为空则使用当前活动标签页", "optional": True}
        #     }
        # ))
        
        # ==================== 探索工具类 ====================
        cdp_tools.append(Tool(
            name="browser_search_page",
            description="在页面中搜索文本",
            function=ToolFactory._browser_search_page_tool,
            parameters={
                "text": {"type": "string", "description": "要搜索的文本"},
                "target_id": {"type": "string", "description": "目标标签页 ID，为空则使用当前活动标签页", "optional": True}
            }
        ))
        
        cdp_tools.append(Tool(
            name="browser_find_elements",
            description="查找页面中匹配选择器的所有元素",
            function=ToolFactory._browser_find_elements_tool,
            parameters={
                "selector": {"type": "string", "description": "CSS 选择器"},
                "target_id": {"type": "string", "description": "目标标签页 ID，为空则使用当前活动标签页", "optional": True}
            }
        ))
        
        cdp_tools.append(Tool(
            name="browser_find_text",
            description="在页面中查找文本并滚动到该位置",
            function=ToolFactory._browser_find_text_tool,
            parameters={
                "text": {"type": "string", "description": "要查找的文本"},
                "target_id": {"type": "string", "description": "目标标签页 ID，为空则使用当前活动标签页", "optional": True}
            }
        ))
        
        cdp_tools.append(Tool(
            name="browser_evaluate",
            description="执行 JavaScript 代码",
            function=ToolFactory._browser_evaluate_tool,
            parameters={
                "script": {"type": "string", "description": "JavaScript 代码"},
                "target_id": {"type": "string", "description": "目标标签页 ID，为空则使用当前活动标签页", "optional": True}
            }
        ))
        
        cdp_tools.append(Tool(
            name="browser_get_state",
            description="获取浏览器当前状态",
            function=ToolFactory._browser_get_state_tool,
            parameters={
                "target_id": {"type": "string", "description": "目标标签页 ID，为空则使用当前活动标签页", "optional": True}
            }
        ))
        
        cdp_tools.append(Tool(
            name="browser_get_cookies",
            description="获取浏览器 Cookie",
            function=ToolFactory._browser_get_cookies_tool,
            parameters={
                "urls": {"type": "array", "description": "目标 URL 列表", "optional": True},
                "target_id": {"type": "string", "description": "目标标签页 ID，为空则使用当前活动标签页", "optional": True}
            }
        ))
        
        cdp_tools.append(Tool(
            name="browser_set_cookie",
            description="设置浏览器 Cookie",
            function=ToolFactory._browser_set_cookie_tool,
            parameters={
                "name": {"type": "string", "description": "Cookie 名称"},
                "value": {"type": "string", "description": "Cookie 值"},
                "url": {"type": "string", "description": "目标 URL"},
                "target_id": {"type": "string", "description": "目标标签页 ID，为空则使用当前活动标签页", "optional": True}
            }
        ))

        cdp_tools.append(Tool(
            name="browser_get_selector_map",
            description="获取页面上所有可交互元素的选择器映射，包括按钮、链接、输入框等",
            function=ToolFactory._browser_get_selector_map_tool,
            parameters={
                "target_id": {"type": "string", "description": "目标标签页 ID，为空则使用当前活动标签页", "optional": True}
            }
        ))

        return cdp_tools

    @staticmethod
    def create_tool_excel():
        """创建 Excel 操作工具集合"""
        excel_tools = []

        # ==================== Excel 读取类工具 ====================
        excel_tools.append(Tool(
            name="excel_read",
            description="读取 Excel 文件，支持大文件优化和智能采样",
            function=ToolFactory._excel_read_tool,
            parameters={
                "file_path": {"type": "string", "description": "Excel 文件路径"},
                "sheet_name": {"type": "string", "description": "工作表名", "optional": True},
                "rows_limit": {"type": "integer", "description": "最大读取行数(0=全部)", "optional": True},
                "columns": {"type": "array", "description": "指定列名列表", "optional": True},
                "sample_mode": {"type": "string", "description": "采样模式: head, tail, random, head_tail", "optional": True},
                "sample_size": {"type": "integer", "description": "采样大小", "optional": True},
                "token_budget": {"type": "integer", "description": "Token 预算", "optional": True}
            }
        ))

        excel_tools.append(Tool(
            name="excel_summarize",
            description="生成 Excel 数据摘要，帮助快速理解数据结构和内容",
            function=ToolFactory._excel_summarize_tool,
            parameters={
                "file_path": {"type": "string", "description": "Excel 文件路径"},
                "sheet_name": {"type": "string", "description": "工作表名", "optional": True}
            }
        ))

        # ==================== Excel 查询类工具 ====================
        excel_tools.append(Tool(
            name="excel_query",
            description="执行 Pandas 查询表达式，如 'df[df[\"age\"] > 18]'",
            function=ToolFactory._excel_query_tool,
            parameters={
                "file_path": {"type": "string", "description": "Excel 文件路径"},
                "query_expr": {"type": "string", "description": "查询表达式"},
                "sheet_name": {"type": "string", "description": "工作表名", "optional": True},
                "limit": {"type": "integer", "description": "返回行数限制", "optional": True}
            }
        ))

        excel_tools.append(Tool(
            name="excel_describe",
            description="生成详细的统计描述（类似 pandas describe）",
            function=ToolFactory._excel_describe_tool,
            parameters={
                "file_path": {"type": "string", "description": "Excel 文件路径"},
                "columns": {"type": "array", "description": "要描述的列名列表", "optional": True},
                "sheet_name": {"type": "string", "description": "工作表名", "optional": True}
            }
        ))

        excel_tools.append(Tool(
            name="excel_correlation",
            description="计算数值列之间的相关系数矩阵",
            function=ToolFactory._excel_correlation_tool,
            parameters={
                "file_path": {"type": "string", "description": "Excel 文件路径"},
                "columns": {"type": "array", "description": "列名列表", "optional": True},
                "sheet_name": {"type": "string", "description": "工作表名", "optional": True},
                "method": {"type": "string", "description": "相关系数方法: pearson, kendall, spearman", "optional": True}
            }
        ))

        # ==================== Excel 数据操作类工具 ====================
        excel_tools.append(Tool(
            name="excel_add_row",
            description="向 Excel 添加一行数据",
            function=ToolFactory._excel_add_row_tool,
            parameters={
                "file_path": {"type": "string", "description": "Excel 文件路径"},
                "row_data": {"type": "object", "description": "字典，键为列名，值为要添加的值"},
                "sheet_name": {"type": "string", "description": "工作表名", "optional": True},
                "save": {"type": "boolean", "description": "是否保存到文件", "optional": True},
                "output_path": {"type": "string", "description": "保存路径", "optional": True}
            }
        ))

        excel_tools.append(Tool(
            name="excel_add_column",
            description="添加新列，列值由表达式计算得出",
            function=ToolFactory._excel_add_column_tool,
            parameters={
                "file_path": {"type": "string", "description": "Excel 文件路径"},
                "column_name": {"type": "string", "description": "新列名"},
                "expression": {"type": "string", "description": "计算表达式，如 \"df['A'] + df['B']\""},
                "sheet_name": {"type": "string", "description": "工作表名", "optional": True},
                "save": {"type": "boolean", "description": "是否保存到文件", "optional": True},
                "output_path": {"type": "string", "description": "保存路径", "optional": True}
            }
        ))

        excel_tools.append(Tool(
            name="excel_update_cell",
            description="更新指定单元格的值",
            function=ToolFactory._excel_update_cell_tool,
            parameters={
                "file_path": {"type": "string", "description": "Excel 文件路径"},
                "row_index": {"type": "integer", "description": "行索引（0-based，不含表头）"},
                "column": {"type": "string", "description": "列名"},
                "value": {"type": "string", "description": "新值"},
                "sheet_name": {"type": "string", "description": "工作表名", "optional": True},
                "save": {"type": "boolean", "description": "是否保存到文件", "optional": True},
                "output_path": {"type": "string", "description": "保存路径", "optional": True}
            }
        ))

        excel_tools.append(Tool(
            name="excel_update_column",
            description="更新整列的值，由表达式计算得出",
            function=ToolFactory._excel_update_column_tool,
            parameters={
                "file_path": {"type": "string", "description": "Excel 文件路径"},
                "column": {"type": "string", "description": "要更新的列名"},
                "expression": {"type": "string", "description": "计算表达式，如 \"df['A'] * 2\""},
                "sheet_name": {"type": "string", "description": "工作表名", "optional": True},
                "save": {"type": "boolean", "description": "是否保存到文件", "optional": True},
                "output_path": {"type": "string", "description": "保存路径", "optional": True}
            }
        ))

        excel_tools.append(Tool(
            name="excel_delete_rows",
            description="删除满足条件的行",
            function=ToolFactory._excel_delete_rows_tool,
            parameters={
                "file_path": {"type": "string", "description": "Excel 文件路径"},
                "condition": {"type": "string", "description": "布尔表达式，如 \"df['age'] > 100\""},
                "sheet_name": {"type": "string", "description": "工作表名", "optional": True},
                "save": {"type": "boolean", "description": "是否保存到文件", "optional": True},
                "output_path": {"type": "string", "description": "保存路径", "optional": True}
            }
        ))

        excel_tools.append(Tool(
            name="excel_delete_columns",
            description="删除指定列",
            function=ToolFactory._excel_delete_columns_tool,
            parameters={
                "file_path": {"type": "string", "description": "Excel 文件路径"},
                "columns": {"type": "array", "description": "要删除的列名列表"},
                "sheet_name": {"type": "string", "description": "工作表名", "optional": True},
                "save": {"type": "boolean", "description": "是否保存到文件", "optional": True},
                "output_path": {"type": "string", "description": "保存路径", "optional": True}
            }
        ))

        excel_tools.append(Tool(
            name="excel_aggregate",
            description="分组聚合操作",
            function=ToolFactory._excel_aggregate_tool,
            parameters={
                "file_path": {"type": "string", "description": "Excel 文件路径"},
                "group_by": {"type": "string", "description": "分组列名"},
                "agg_dict": {"type": "object", "description": "聚合字典，如 {'sales': 'sum', 'profit': ['mean', 'max']}"},
                "sheet_name": {"type": "string", "description": "工作表名", "optional": True}
            }
        ))

        return excel_tools

    @staticmethod
    def create_tools_all_skills():
        skills = SkillFactory.get_all_skills()
        tools = []
        for skill in skills:
            tools.append(ToolFactory.generate_skill_tool(skill))

        return tools

    @staticmethod
    def create_tool_skill(name: str):
        skill = SkillFactory.get_skill(name)
        return ToolFactory.generate_skill_tool(skill)

    @staticmethod
    def generate_skill_tool(skill: Skill):
        return Tool(
                name=f"skill-{skill.meta.name}",
                description=skill.meta.description,
                function=ToolFactory._skill_tool,
                parameters={
                    "skill_name": {"type": "string", "description": "Load the skill instructions with the skill name."}
                }
            )

    @staticmethod
    def _glob_tool(pattern: str, path: Optional[str] = None) -> Dict[str, Any]:
        """Find files by pattern"""
        try:
            # 还原（会自动解析引号和转义符）
            # path = ast.literal_eval(path)

            search_path = Path(path) if path else Path(get_current_path())
            full_pattern = str(search_path / pattern)

            files = []
            for file_path in glob.glob(full_pattern, recursive=True):
                files.append(str(Path(file_path).relative_to(search_path)))

            return {"files": files}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def _read_tool(file_path: str, offset: Optional[int] = None,
                   limit: Optional[int] = None) -> Dict[str, Any]:
        """Read file contents"""
        try:
            # file_path = ast.literal_eval(file_path)
            if not os.path.isabs(file_path):
                cwd = get_current_path()
                file_path = f'{cwd}/{file_path}'

            path = Path(file_path)
            if not path.exists():
                return {"error": f"File not found: {file_path}"}

            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if offset is not None:
                lines = lines[offset:]
            if limit is not None:
                lines = lines[:limit]

            return {
                "content": "".join(lines),
                "total_lines": len(lines)
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def _write_tool(file_path: str, content: str) -> Dict[str, Any]:
        """Write to file"""
        try:
            # 还原（会自动解析引号和转义符）
            # file_path = ast.literal_eval(file_path)
            if not os.path.isabs(file_path):
                cwd = get_current_path()
                file_path = f'{cwd}/{file_path}'

            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            return {"success": True, "path": str(path)}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def _powershell_tool(command: str, cwd: str = None, timeout: Optional[int] = 60000) -> Dict[str, Any]:
        try:
            if timeout < 60000:
                timeout = 60000

            if cwd is None:
                cwd = get_current_path()
            # 判断当前路径是否存在，若不存在则获取默认的当前路径
            if cwd is None or not os.path.exists(cwd):
                cwd = os.getcwd()


            # Execute command
            # 针对末尾//，需要修复成////
            command = re.sub(r'([A-Za-z]):\\(\s|$)', r'\1:\\\\\2', command)
            # print(f"清洗修复后命令: {command}")

            args = shlex.split(command)
            if args and len(args) > 0 and args[0] != 'powershell':
                args.insert(0, 'powershell')
                args.insert(1, '-NoProfile')  # 核心修复：不加载用户配置，不会输出\x1b乱码
                args.insert(1, '-NonInteractive')  # 非交互模式，关闭终端着色逻辑

            # 核心修改1：修正命令拼接逻辑，确保chcp和业务命令在同一个-Command参数中
            # 1. 先移除可能重复的-Command（避免参数混乱）
            if '-Command' in args:
                args.remove('-Command')
            # 2. 插入-Command参数
            args.insert(3, '-Command')
            # 3. 拼接编码设置命令 + 原始命令（关键：合并成一个字符串，避免拆分）
            command_with_encoding = f'chcp 65001 > $null; {" ".join(args[4:])}'
            # 4. 重构参数列表（powershell + -Command + 完整命令字符串）
            args = [args[0], args[1], args[2], args[3], command_with_encoding]
            logging.info(f"最终执行参数: {args}")

            # 核心修改2：执行命令时先尝试UTF-8，捕获字节流而非直接解码
            result = subprocess.run(
                args,
                capture_output=True,  # 捕获stdout/stderr的字节流
                text=False,  # 关键：先返回字节，手动处理解码，避免自动解码报错
                cwd=cwd,
                timeout=(timeout / 1000) if timeout else None
            )

            # 手动处理解码逻辑（UTF-8优先，GBK兜底）
            def safe_decode(byte_data):
                if not byte_data:
                    return ""
                try:
                    # 优先用UTF-8解码
                    return byte_data.decode('utf-8')
                except UnicodeDecodeError:
                    # 兜底：用GBK解码（Windows中文环境默认编码）
                    return byte_data.decode('gbk', errors='replace')

            stdout_str = safe_decode(result.stdout)
            stderr_str = safe_decode(result.stderr)

            return {
                "stdout": stdout_str,
                "stderr": stderr_str,
                "returncode": result.returncode,
                "success": result.returncode == 0
            }
        except subprocess.TimeoutExpired:
            return {"error": "Powershell command timed out"}
        except UnicodeDecodeError as e:
            return {"error": f"解码错误: {str(e)}", "hint": "尝试检查命令输出编码"}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def _generate_image_tool(prompt: str, generated_img_path: str, reference_img_path: str = None) -> Dict[str, Any]:
        """generate pic"""
        try:
            result = volcengine_generate_image.generate_image(prompt=prompt, generated_img_path=generated_img_path, reference_img_path=reference_img_path)
            return {"success": (result >= 1), "created_image_count": result}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def _image_qa_tool(prompt: str, reference_img_path: str, file_id: str = None) -> Dict[str, Any]:
        """generate pic"""
        try:
            answer, file_id = volcengine_image_qa_client.image_qa(prompt=prompt, reference_img_path=reference_img_path, file_id=file_id)
            return {"success": (answer is not None), "answer": answer, "file_id": file_id}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def _mcp_tool(uri: str, server: str = "http://127.0.0.1:15000/mcp", protocol: str='sse', parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        单函数实现：全协议兼容 MCP (Model Context Protocol) 同步调用工具
        支持：http/https、sse、stdio 所有标准 MCP 协议，无外部依赖函数
        """
        # 初始化参数与返回结果
        params = parameters if parameters is not None else {}
        result = {}

        if protocol == 'sse':
            session = requests.Session()
            message_endpoint = None
            session_id = None
            sse_connection = None
            sse_thread = None
            stop_sse_event = threading.Event()

            # ---------- 辅助函数：建立 SSE 连接并提取 endpoint ----------
            try:
                # 1. 建立 SSE 长连接（注意：这里使用 GET 到 /sse）, 主要用于获取 sesssion id
                connect_request = {
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "connect",
                    "params": {}
                }
                sse_start = session.post(
                    url=server,
                    headers={"Accept": "text/event-stream, application/json", "Content-Type": "application/json"},
                    data=json.dumps(connect_request)
                )
                session_id = sse_start.headers['mcp-session-id']

                # 2. 建立 SSE 长连接（注意：这里使用 GET 到 /sse）
                sse_connection = session.get(
                    url=server,
                    stream=True,
                    headers={"Accept": "text/event-stream, application/json", "Content-Type": "application/json", "mcp-session-id": session_id},
                    timeout=120
                )
                sse_connection.raise_for_status()  # 判断是否是有效链接

                # 步骤 3：【必须！】发送 initialize 初始化
                init_req = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "1.0",
                        "capabilities": {},
                        "clientInfo": {
                            "name": "python-client",
                            "version": "1.0"
                        }
                    }
                }

                sse_init = session.post(
                    url=server,
                    headers={
                        "Accept": "text/event-stream, application/json",
                        "Content-Type": "application/json",
                        "mcp-session-id": session_id
                    },
                    data=json.dumps(init_req)
                )

                call_way = "tool"
                if uri.find("/") > 0:
                    call_way = "resource"

                if call_way == "resource":
                    # 步骤 4： 获取静态资源
                    list_tools_resource = {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "resources/read",  # 固定方法
                        "params": {
                            "uri": uri
                        }
                    }
                    sse_resource = session.post(
                        url=server,
                        headers={
                            "Accept": "text/event-stream, application/json",
                            "Content-Type": "application/json",
                            "mcp-session-id": session_id
                        },
                        data=json.dumps(list_tools_resource)
                    )
                    print(str(sse_resource))
                    return {"data":sse_resource.text}

                else:
                    # ----------------------
                    # 6. ✅执行tool call
                    # ----------------------
                    data_tool = {
                        "jsonrpc": "2.0",
                        "id": "2",
                        "method": "tools/call",
                        "params": {
                            "name": uri,
                            "arguments": params
                        }
                    }

                    sse_tool = session.post(
                        url=server,
                        stream=True,
                        headers={"Accept": "text/event-stream, application/json", "Content-Type": "application/json",
                                 "mcp-session-id": session_id, },
                        timeout=120,
                        data=json.dumps(data_tool)
                    )
                    return {"data": sse_tool.text}

                # ----------------------
                # 6. ✅【关键】先获取服务器支持的所有静态资源列表
                # ----------------------
                # list_resource_req = {
                #     "jsonrpc": "2.0",
                #     "id": 3,
                #     "method": "resources/list",  # 固定方法
                #     "params": {}
                # }
                # sse_resouce_list = session.post(
                #     url=server,
                #     headers={
                #         "Accept": "text/event-stream, application/json",
                #         "Content-Type": "application/json",
                #         "mcp-session-id": session_id
                #     },
                #     data=json.dumps(list_resource_req)
                # )
                # print(str(sse_resouce_list))
                # resouces = json.loads(sse_resouce_list.text)

                # ----------------------
                # 4. ✅【关键】先获取服务器支持的所有工具列表
                # ----------------------
                # list_tools_req = {
                #     "jsonrpc": "2.0",
                #     "id": 3,
                #     "method": "tools/list",  # 固定方法
                #     "params": {}
                # }
                # sse_list = session.post(
                #     url=server,
                #     headers={
                #         "Accept": "text/event-stream, application/json",
                #         "Content-Type": "application/json",
                #         "mcp-session-id": session_id
                #     },
                #     data=json.dumps(list_tools_req)
                # )


                print(str(sse_tool))

            except Exception as e:
                result["errors"].append(f"建立 SSE 连接失败: {str(e)}")
                raise

        return result

    @staticmethod
    def _extract_service_name(prefixed_name: str) -> str:
        """从带前缀的工具名中提取服务名。使用 '---' 作为分隔符。"""
        if "---" in prefixed_name:
            return prefixed_name.split("---", 1)[0]
        return prefixed_name

    @staticmethod
    def _mcp_tool_call(tool_name: str, arguments: Optional[Dict[str, Any]] = None,
                       allowed_mcp: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        调用已发现的 MCP 服务工具（通过 McpManager）

        :param tool_name: 工具名称（带服务前缀，如 service---tool）
        :param arguments: 工具参数
        :param allowed_mcp: 允许使用的服务名列表，None 表示不限制
        :return: 执行结果
        """
        try:
            manager = ToolFactory._get_mcp_manager()
            manager.ensure_connected()

            # 白名单检查
            if allowed_mcp is not None:
                service_name = ToolFactory._extract_service_name(tool_name)
                if service_name not in allowed_mcp:
                    return {"error": f"服务 '{service_name}' 不在本 agent 允许的 MCP 白名单中，可用服务：{allowed_mcp}"}

            # 执行工具调用
            args = arguments if arguments is not None else {}
            result = manager.call_tool(tool_name, args)
            return {"success": True, "result": result}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def _mcp_list_services(allowed_mcp: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        列出已连接的 MCP 服务及其可用工具

        :param allowed_mcp: 允许展示的服务名列表，None 表示不限制
        :return: 服务列表和工具信息
        """
        try:
            manager = ToolFactory._get_mcp_manager()
            manager.ensure_connected()

            # 获取服务信息，按白名单过滤
            services = manager.get_service_info()
            all_tools = manager.get_all_tools()

            if allowed_mcp is not None:
                services = [s for s in services if s.get("name") in allowed_mcp]
                all_tools = [
                    t for t in all_tools
                    if ToolFactory._extract_service_name(t.get("function", {}).get("name", "")) in allowed_mcp
                ]

            return {
                "success": True,
                "services": services,
                "tools": all_tools
            }
        except Exception as e:
            return {"error": str(e)}

    # @staticmethod
    # def _powershell_tool(command: str, timeout: Optional[int] = None) -> Dict[str, Any]:
    #     """Execute powershell command"""
    #     try:
    #         cwd = get_current_path()
    #         # 先构造切换到工作目录的命令，拼接cd命令和原命令，注意用分号分隔PowerShell命令
    #         # command = f'cd "{cwd}"; {command}'
    #
    #         # Execute command
    #         args = shlex.split(command)
    #         if args and len(args) > 0 and args[0] != 'powershell':
    #             args.insert(0, 'powershell')
    #
    #         # 核心修改：插入 chcp 65001 命令（切换编码为 UTF-8）
    #         # 1. 添加 -Command 参数（PowerShell 执行命令的参数）
    #         # 2. 拼接 chcp 65001 > $null; （> $null 隐藏编码切换的输出）
    #         # 3. 拼接原始命令内容
    #         args.insert(1, '-Command')
    #         args.insert(2, 'chcp 65001 > $null;')
    #         # 将后续的所有参数重新拼接成一个字符串（避免参数拆分错误）
    #         args = args[:3] + [' '.join(args[3:])]
    #         print(args)
    #
    #         result = subprocess.run(
    #             args,
    #             capture_output=True,
    #             text=True,
    #             cwd=cwd,
    #             encoding='utf-8',
    #             timeout=(timeout / 1000) if timeout else None
    #         )
    #
    #         return {
    #             "stdout": result.stdout,
    #             "stderr": result.stderr,
    #             "returncode": result.returncode,
    #             "success": result.returncode == 0
    #         }
    #     except subprocess.TimeoutExpired:
    #         return {"error": "Command timed out"}
    #     except UnicodeDecodeError as e:
    #         # 兜底：若仍有解码错误，用 GBK 手动解码字节流
    #         return {"error": f"解码错误: {str(e)}", "hint": "尝试检查命令输出编码"}
    #     except Exception as e:
    #         return {"error": str(e)}

    @staticmethod
    def _bash_tool(command: str, timeout: Optional[int] = None) -> Dict[str, Any]:
        """Execute shell command"""
        try:
            # Check permission
            # if self.permissions.check("bash").value != "allow":
            #     return {"error": "Permission denied for bash tool"}

            # 还原（会自动解析引号和转义符）
            # command = ast.literal_eval(command)

            cwd = get_current_path()

            # Execute command
            args = shlex.split(command)
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=(timeout / 1000) if timeout else None
            )

            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "success": result.returncode == 0
            }
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def _agent_tool():
        from aickoo.internal.app.agents import Agent
        return Agent(config=None, permissions=None, db=None)

    @staticmethod
    def _skill_tool(skill_name: str) -> str:
        try:
            skill = SkillFactory.get_skill(skill_name)
            return f'{skill.meta.description}\n{skill.content}\n\n# Base Path:\nThe base path of this skill is {skill.base_path}'
        except Exception as e:
            return {"error": str(e)}

    # ==================== CDP 浏览器工具实现 ====================

    @staticmethod
    def _get_browser_session():
        """获取或创建浏览器会话实例（单例模式）"""
        if not hasattr(ToolFactory, '_browser_session'):
            from aickoo.internal.app.browser_session import BrowserSession
            ToolFactory._browser_session = BrowserSession()
        return ToolFactory._browser_session

    @staticmethod
    def _run_cdp_async(coro):
        loop = ToolFactory._ensure_cdp_event_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        try:
            # 等待结果，超时时间可配置
            result = future.result(timeout=90)
            return result
        except concurrent.futures.TimeoutError:
            return {"error": "操作超时"}
        except Exception as e:
            return {"error": str(e)}


        # """运行异步函数的同步包装器"""
        # import threading
        # import queue
        #
        # result_queue = queue.Queue()
        # exception_queue = queue.Queue()
        #
        # def run_in_thread():
        #     """在新线程中运行协程"""
        #     try:
        #         result = asyncio.run(coro)
        #         result_queue.put(('success', result))
        #     except Exception as e:
        #         exception_queue.put(e)
        #
        # # 在新线程中运行，避免阻塞主线程
        # thread = threading.Thread(target=run_in_thread, daemon=True)
        # thread.start()
        # thread.join(timeout=30)  # 最多等待30秒
        #
        # # 检查是否有异常
        # if not exception_queue.empty():
        #     exception = exception_queue.get()
        #     return {"error": str(exception)}
        #
        # # 检查是否有结果
        # if result_queue.empty():
        #     return {"error": "操作超时"}
        #
        # status, result = result_queue.get()
        # return result

    # ==================== 标签页管理类工具实现 ====================

    @staticmethod
    def _browser_list_tabs_tool() -> Dict[str, Any]:
        """列出所有浏览器标签页"""
        async def _list_tabs():
            try:
                session = ToolFactory._get_browser_session()

                # 如果未连接，先连接
                if not session._cdp_client_root:
                    success = await session.connect()
                    if not success:
                        return {"error": "无法连接到浏览器"}

                # 获取所有目标
                targets = await session.list_targets()

                # 格式化输出
                tabs = []
                for target in targets:
                    tabs.append({
                        "target_id": target.get("target_id"),
                        "title": target.get("title", "无标题"),
                        "url": target.get("url", ""),
                        "type": target.get("type"),
                        "is_current": target.get("is_current", False)
                    })

                return {
                    "success": True,
                    "tabs": tabs,
                    "current_tab": session.get_current_target_id()
                }
            except Exception as e:
                return {"error": str(e)}

        return ToolFactory._run_cdp_async(_list_tabs())

    @staticmethod
    def _browser_new_tab_tool(url: str = None) -> Dict[str, Any]:
        """创建新标签页"""
        async def _new_tab():
            try:
                session = ToolFactory._get_browser_session()

                # 如果未连接，先连接
                if not session._cdp_client_root:
                    success = await session.connect()
                    if not success:
                        return {"error": "无法连接到浏览器"}

                # 创建新标签页
                target_id = await session.create_new_tab(url or "about:blank")

                return {"success": True, "target_id": target_id, "url": url or "about:blank"}
            except Exception as e:
                return {"error": str(e)}

        return ToolFactory._run_cdp_async(_new_tab())

    # ==================== 导航类工具实现 ====================

    @staticmethod
    def _browser_navigate_tool(url: str, target_id: str = None) -> Dict[str, Any]:
        """导航到指定 URL"""
        async def _navigate():
            try:
                session = ToolFactory._get_browser_session()

                # 如果未连接，先连接
                if not session._cdp_client_root:
                    success = await session.connect()
                    if not success:
                        return {"error": "无法连接到浏览器"}

                # 导航到 URL（使用 target_id）
                frame_id = await session.navigate_to(url, target_id)
                current_target = session.get_current_target_id()

                return {"success": True, "url": url, "target_id": current_target, "frame_id": frame_id}
            except Exception as e:
                return {"error": str(e)}

        return ToolFactory._run_cdp_async(_navigate())

    @staticmethod
    def _browser_go_back_tool(target_id: str = None) -> Dict[str, Any]:
        """返回上一页"""
        async def _go_back():
            try:
                session = ToolFactory._get_browser_session()
                client, session_id = await session._ensure_session(target_id)
                await client.page_navigate_back(session_id)
                return {"success": True, "target_id": target_id or session.get_current_target_id()}
            except Exception as e:
                return {"error": str(e)}

        return ToolFactory._run_cdp_async(_go_back())

    @staticmethod
    def _browser_switch_tab_tool(target_id: str) -> Dict[str, Any]:
        """切换到指定的浏览器标签页"""
        async def _switch_tab():
            try:
                session = ToolFactory._get_browser_session()
                session_id = await session.switch_to_target(target_id)
                return {"success": True, "target_id": target_id, "session_id": session_id}
            except Exception as e:
                return {"error": str(e)}

        return ToolFactory._run_cdp_async(_switch_tab())

    @staticmethod
    def _browser_close_tab_tool(target_id: str = None) -> Dict[str, Any]:
        """关闭指定的浏览器标签页"""
        async def _close_tab():
            try:
                session = ToolFactory._get_browser_session()

                # 使用外部函数的 target_id 参数，如果为 None 则获取当前标签页
                # 使用局部变量避免 Python 作用域问题
                resolved_target_id = target_id
                if resolved_target_id is None:
                    resolved_target_id = session.get_current_target_id()

                if resolved_target_id:
                    await session.close_target(resolved_target_id)
                    return {"success": True, "target_id": resolved_target_id}
                return {"error": "没有可关闭的标签页"}
            except Exception as e:
                return {"error": str(e)}

        return ToolFactory._run_cdp_async(_close_tab())

    # ==================== 元素交互类工具实现 ====================

    @staticmethod
    def _browser_click_tool(selector: str, target_id: str = None) -> Dict[str, Any]:
        """点击页面上的指定元素"""
        async def _click():
            try:
                session = ToolFactory._get_browser_session()
                await session.click_element(selector, target_id)
                return {"success": True, "selector": selector, "target_id": target_id or session.get_current_target_id()}
            except Exception as e:
                return {"error": str(e)}

        return ToolFactory._run_cdp_async(_click())

    @staticmethod
    def _browser_input_tool(selector: str, text: str, target_id: str = None) -> Dict[str, Any]:
        """在输入框中输入文本"""
        async def _input():
            try:
                session = ToolFactory._get_browser_session()
                await session.type_text(selector, text, target_id)
                return {"success": True, "selector": selector, "text": text, "target_id": target_id or session.get_current_target_id()}
            except Exception as e:
                return {"error": str(e)}

        return ToolFactory._run_cdp_async(_input())

    @staticmethod
    def _browser_upload_file_tool(selector: str, file_path: str, target_id: str = None) -> Dict[str, Any]:
        """上传文件到指定输入框"""
        async def _upload():
            try:
                session = ToolFactory._get_browser_session()
                # 使用 JavaScript 设置文件输入
                script = f"""
                    const el = document.querySelector('{selector}');
                    if (el && el.type === 'file') {{
                        const dataTransfer = new DataTransfer();
                        dataTransfer.items.add(new File([], '{file_path}'));
                        el.files = dataTransfer.files;
                        el.dispatchEvent(new Event('change'));
                    }}
                """
                await session.execute_script(script, target_id)
                return {"success": True, "selector": selector, "file_path": file_path, "target_id": target_id or session.get_current_target_id()}
            except Exception as e:
                return {"error": str(e)}

        return ToolFactory._run_cdp_async(_upload())

    @staticmethod
    def _browser_scroll_tool(x: int = None, y: int = None, selector: str = None, target_id: str = None) -> Dict[str, Any]:
        """滚动页面到指定位置"""
        async def _scroll():
            try:
                session = ToolFactory._get_browser_session()

                if selector:
                    # 滚动到指定元素
                    script = f"document.querySelector('{selector}').scrollIntoView({{behavior: 'smooth'}})"
                    await session.execute_script(script, target_id)
                elif x is not None or y is not None:
                    # 滚动到指定坐标
                    script = f"window.scrollTo({x or 0}, {y or 0})"
                    await session.execute_script(script, target_id)

                return {"success": True, "target_id": target_id or session.get_current_target_id()}
            except Exception as e:
                return {"error": str(e)}

        return ToolFactory._run_cdp_async(_scroll())

    @staticmethod
    def _browser_send_keys_tool(keys: str, target_id: str = None) -> Dict[str, Any]:
        """发送键盘按键"""
        async def _send_keys():
            try:
                session = ToolFactory._get_browser_session()
                # 使用 JavaScript 模拟键盘事件
                key_map = {
                    'Enter': 'Enter',
                    'Escape': 'Escape',
                    'Tab': 'Tab',
                    'Backspace': 'Backspace',
                    'Delete': 'Delete',
                    'Ctrl+A': 'Ctrl+A',
                    'Ctrl+C': 'Ctrl+C',
                    'Ctrl+V': 'Ctrl+V',
                    'Ctrl+X': 'Ctrl+X'
                }

                script = f"""
                    const event = new KeyboardEvent('keydown', {{key: '{key_map.get(keys, keys)}'}});
                    document.activeElement.dispatchEvent(event);
                """
                await session.execute_script(script, target_id)
                return {"success": True, "keys": keys, "target_id": target_id or session.get_current_target_id()}
            except Exception as e:
                return {"error": str(e)}

        return ToolFactory._run_cdp_async(_send_keys())

    @staticmethod
    def _browser_get_dropdown_options_tool(selector: str, target_id: str = None) -> Dict[str, Any]:
        """获取下拉框的所有选项"""
        async def _get_options():
            try:
                session = ToolFactory._get_browser_session()
                script = f"""
                    const select = document.querySelector('{selector}');
                    if (!select) return {{error: 'Element not found'}};
                    const options = Array.from(select.options).map(opt => ({{
                        value: opt.value,
                        text: opt.text,
                        selected: opt.selected
                    }}));
                    return options;
                """
                options = await session.execute_script(script, target_id)
                return {"success": True, "options": options, "target_id": target_id or session.get_current_target_id()}
            except Exception as e:
                return {"error": str(e)}

        return ToolFactory._run_cdp_async(_get_options())

    @staticmethod
    def _browser_select_dropdown_tool(selector: str, option_value: str, target_id: str = None) -> Dict[str, Any]:
        """选择下拉框的指定选项"""
        async def _select():
            try:
                session = ToolFactory._get_browser_session()
                script = f"""
                    const select = document.querySelector('{selector}');
                    if (!select) return {{error: 'Element not found'}};
                    for (let i = 0; i < select.options.length; i++) {{
                        if (select.options[i].value === '{option_value}' || select.options[i].text === '{option_value}') {{
                            select.selectedIndex = i;
                            select.dispatchEvent(new Event('change'));
                            break;
                        }}
                    }}
                """
                await session.execute_script(script, target_id)
                return {"success": True, "selected": option_value, "target_id": target_id or session.get_current_target_id()}
            except Exception as e:
                return {"error": str(e)}

        return ToolFactory._run_cdp_async(_select())

    # ==================== 页面操作类工具实现 ====================

    @staticmethod
    def _browser_wait_tool(seconds: int) -> Dict[str, Any]:
        # 最小为7秒钟，防止总是AI监听到页面状态未结束
        if seconds < 7:
            seconds = 7

        """等待指定时间"""
        async def _wait():
            try:
                await asyncio.sleep(seconds)
                return {"success": True, "waited_seconds": seconds}
            except Exception as e:
                return {"error": str(e)}

        return ToolFactory._run_cdp_async(_wait())

    @staticmethod
    def _browser_screenshot_tool(format: str = "png", quality: int = 100, save_path: str = None, target_id: str = None) -> Dict[str, Any]:
        """捕获页面截图"""
        async def _screenshot():
            try:
                session = ToolFactory._get_browser_session()
                screenshot = await session.screenshot(format, quality, target_id)

                if save_path:
                    with open(save_path, "wb") as f:
                        f.write(screenshot)
                    return {"success": True, "saved_to": save_path, "target_id": target_id or session.get_current_target_id()}
                else:
                    return {"success": True, "data": base64.b64encode(screenshot).decode(), "target_id": target_id or session.get_current_target_id()}
            except Exception as e:
                return {"error": str(e)}

        return ToolFactory._run_cdp_async(_screenshot())

    @staticmethod
    def _browser_save_as_pdf_tool(save_path: str, landscape: bool = False, target_id: str = None) -> Dict[str, Any]:
        """将页面保存为 PDF"""
        async def _save_pdf():
            try:
                session = ToolFactory._get_browser_session()
                client, session_id = await session._ensure_session(target_id)

                # 使用 CDP 的 Page.printToPDF
                result = await client._send(
                    "Page.printToPDF",
                    {
                        "landscape": landscape,
                        "printBackground": True,
                        "preferCSSPageSize": True
                    },
                    session_id
                )

                pdf_data = base64.b64decode(result.get('data', ''))
                with open(save_path, "wb") as f:
                    f.write(pdf_data)

                return {"success": True, "saved_to": save_path, "target_id": target_id or session.get_current_target_id()}
            except Exception as e:
                return {"error": str(e)}

        return ToolFactory._run_cdp_async(_save_pdf())

    @staticmethod
    def _browser_extract_tool(selector: str = None, target_id: str = None) -> Dict[str, Any]:
        """提取页面内容为 Markdown 格式"""
        async def _extract():
            try:
                session = ToolFactory._get_browser_session()

                if selector:
                    script = f"""
                        const el = document.querySelector('{selector}');
                        return el ? el.innerText : '';
                    """
                else:
                    script = "document.body.innerText"

                content = await session.execute_script(script, target_id)

                # 简单转换为 Markdown
                markdown = content.replace('\n\n', '\n\n')

                return {"success": True, "markdown": markdown, "target_id": target_id or session.get_current_target_id()}
            except Exception as e:
                return {"error": str(e)}

        return ToolFactory._run_cdp_async(_extract())

    # ==================== 探索工具类工具实现 ====================

    @staticmethod
    def _browser_search_page_tool(text: str, target_id: str = None) -> Dict[str, Any]:
        """在页面中搜索文本"""
        async def _search():
            try:
                session = ToolFactory._get_browser_session()
                script = f"""
                    const found = window.find('{text}');
                    return found;
                """
                found = await session.execute_script(script, target_id)
                return {"success": True, "found": found, "text": text, "target_id": target_id or session.get_current_target_id()}
            except Exception as e:
                return {"error": str(e)}

        return ToolFactory._run_cdp_async(_search())

    @staticmethod
    def _browser_find_elements_tool(selector: str, target_id: str = None) -> Dict[str, Any]:
        """查找页面中匹配选择器的所有元素"""
        async def _find():
            try:
                session = ToolFactory._get_browser_session()
                script = f"""
                    const elements = document.querySelectorAll('{selector}');
                    return {{
                        count: elements.length,
                        elements: Array.from(elements).map(el => ({{
                            tagName: el.tagName,
                            id: el.id,
                            className: el.className,
                            text: el.textContent.substring(0, 100)
                        }}))
                    }};
                """
                result = await session.execute_script(script, target_id)
                return {"success": True, "count": result.get("count", 0), "elements": result.get("elements", []), "target_id": target_id or session.get_current_target_id()}
            except Exception as e:
                return {"error": str(e)}

        return ToolFactory._run_cdp_async(_find())

    @staticmethod
    def _browser_find_text_tool(text: str, target_id: str = None) -> Dict[str, Any]:
        """在页面中查找文本并滚动到该位置"""
        async def _find_text():
            try:
                session = ToolFactory._get_browser_session()
                script = f"""
                    const elements = Array.from(document.querySelectorAll('*')).filter(el => 
                        el.textContent.includes('{text}')
                    );
                    if (elements.length > 0) {{
                        elements[0].scrollIntoView({{behavior: 'smooth'}});
                        return {{found: true, position: elements[0].getBoundingClientRect()}};
                    }}
                    return {{found: false}};
                """
                result = await session.execute_script(script, target_id)
                return {"success": True, "result": result, "text": text, "target_id": target_id or session.get_current_target_id()}
            except Exception as e:
                return {"error": str(e)}

        return ToolFactory._run_cdp_async(_find_text())

    @staticmethod
    def _browser_evaluate_tool(script: str, target_id: str = None) -> Dict[str, Any]:
        """执行 JavaScript 代码"""
        async def _evaluate():
            try:
                session = ToolFactory._get_browser_session()
                result = await session.execute_script(script, target_id)
                return {"success": True, "result": result, "target_id": target_id or session.get_current_target_id()}
            except Exception as e:
                return {"error": str(e)}

        return ToolFactory._run_cdp_async(_evaluate())

    @staticmethod
    def _browser_get_state_tool(target_id: str = None) -> Dict[str, Any]:
        """获取浏览器当前状态"""
        async def _get_state():
            try:
                session = ToolFactory._get_browser_session()
                state = await session.get_browser_state_summary()
                return {
                    "success": True,
                    "state": {
                        "current_url": state.current_url,
                        "current_title": state.current_title,
                        "current_target_id": state.current_target_id,
                        "page_loaded": state.page_loaded,
                        "cookies_count": state.cookies_count,
                        "open_tabs": state.open_tabs
                    }
                }
            except Exception as e:
                return {"error": str(e)}

        return ToolFactory._run_cdp_async(_get_state())

    @staticmethod
    def _browser_get_cookies_tool(urls: List[str] = None, target_id: str = None) -> Dict[str, Any]:
        """获取浏览器 Cookie"""
        async def _get_cookies():
            try:
                session = ToolFactory._get_browser_session()
                cookies = await session.get_cookies(urls, target_id)
                return {"success": True, "cookies": cookies, "count": len(cookies), "target_id": target_id or session.get_current_target_id()}
            except Exception as e:
                return {"error": str(e)}

        return ToolFactory._run_cdp_async(_get_cookies())

    @staticmethod
    def _browser_set_cookie_tool(name: str, value: str, url: str, target_id: str = None) -> Dict[str, Any]:
        """设置浏览器 Cookie"""
        async def _set_cookie():
            try:
                session = ToolFactory._get_browser_session()
                cookie = {
                    "name": name,
                    "value": value,
                    "url": url
                }
                await session.set_cookie(cookie, target_id)
                return {"success": True, "cookie": cookie, "target_id": target_id or session.get_current_target_id()}
            except Exception as e:
                return {"error": str(e)}

        return ToolFactory._run_cdp_async(_set_cookie())

    @staticmethod
    def _browser_get_selector_map_tool(target_id: str = None) -> Dict[str, Any]:
        """获取页面选择器映射"""
        async def _get_selector_map():
            try:
                session = ToolFactory._get_browser_session()
                if target_id:
                    session_id = await session.get_or_create_cdp_session(target_id)
                else:
                    session_id = session._current_session_id

                selector_map = await session.get_selector_map(session_id)

                result_list = []
                for selector, info in selector_map.items():
                    result_list.append({
                        "selector": info.selector,
                        "tag_name": info.tag_name,
                        "text_content": info.text_content,
                        "attributes": info.attributes
                    })

                return {
                    "success": True,
                    "count": len(result_list),
                    "selectors": result_list,
                    "target_id": target_id or session.get_current_target_id()
                }
            except Exception as e:
                return {"error": str(e)}

        return ToolFactory._run_cdp_async(_get_selector_map())
    
    # ==================== Excel 工具实现 ====================
    
    @staticmethod
    def _excel_read_tool(file_path: str, sheet_name: str = None, rows_limit: int = 0, 
                        columns: List[str] = None, sample_mode: str = "head_tail", 
                        sample_size: int = 100, token_budget: int = 4000) -> Dict[str, Any]:
        """读取 Excel 文件"""
        return ExcelTool.read(
            file_path=file_path,
            sheet_name=sheet_name,
            rows_limit=rows_limit,
            columns=columns,
            sample_mode=sample_mode,
            sample_size=sample_size,
            token_budget=token_budget
        )
    
    @staticmethod
    def _excel_summarize_tool(file_path: str, sheet_name: str = None) -> Dict[str, Any]:
        """生成 Excel 数据摘要"""
        return ExcelTool.summarize(file_path=file_path, sheet_name=sheet_name)
    
    @staticmethod
    def _excel_query_tool(file_path: str, query_expr: str, sheet_name: str = None, 
                        limit: int = 1000) -> Dict[str, Any]:
        """执行 Pandas 查询"""
        return ExcelTool.query(
            file_path=file_path,
            query_expr=query_expr,
            sheet_name=sheet_name,
            limit=limit
        )
    
    @staticmethod
    def _excel_describe_tool(file_path: str, columns: List[str] = None, 
                            sheet_name: str = None) -> Dict[str, Any]:
        """生成统计描述"""
        return ExcelTool.describe(
            file_path=file_path,
            columns=columns,
            sheet_name=sheet_name
        )
    
    @staticmethod
    def _excel_correlation_tool(file_path: str, columns: List[str] = None, 
                                sheet_name: str = None, method: str = 'pearson') -> Dict[str, Any]:
        """计算相关系数矩阵"""
        return ExcelTool.correlation(
            file_path=file_path,
            columns=columns,
            sheet_name=sheet_name,
            method=method
        )
    
    @staticmethod
    def _excel_add_row_tool(file_path: str, row_data: Dict[str, Any], 
                            sheet_name: str = None, save: bool = False, 
                            output_path: str = None) -> Dict[str, Any]:
        """添加一行数据"""
        return ExcelTool.add_row(
            file_path=file_path,
            row_data=row_data,
            sheet_name=sheet_name,
            save=save,
            output_path=output_path
        )
    
    @staticmethod
    def _excel_add_column_tool(file_path: str, column_name: str, expression: str, 
                                sheet_name: str = None, save: bool = False, 
                                output_path: str = None) -> Dict[str, Any]:
        """添加新列"""
        return ExcelTool.add_column(
            file_path=file_path,
            column_name=column_name,
            expression=expression,
            sheet_name=sheet_name,
            save=save,
            output_path=output_path
        )
    
    @staticmethod
    def _excel_update_cell_tool(file_path: str, row_index: int, column: str, 
                                value: Any, sheet_name: str = None, 
                                save: bool = False, output_path: str = None) -> Dict[str, Any]:
        """更新单元格"""
        return ExcelTool.update_cell(
            file_path=file_path,
            row_index=row_index,
            column=column,
            value=value,
            sheet_name=sheet_name,
            save=save,
            output_path=output_path
        )
    
    @staticmethod
    def _excel_update_column_tool(file_path: str, column: str, expression: str, 
                                sheet_name: str = None, save: bool = False, 
                                output_path: str = None) -> Dict[str, Any]:
        """更新整列"""
        return ExcelTool.update_column(
            file_path=file_path,
            column=column,
            expression=expression,
            sheet_name=sheet_name,
            save=save,
            output_path=output_path
        )
    
    @staticmethod
    def _excel_delete_rows_tool(file_path: str, condition: str, 
                                sheet_name: str = None, save: bool = False, 
                                output_path: str = None) -> Dict[str, Any]:
        """删除满足条件的行"""
        return ExcelTool.delete_rows(
            file_path=file_path,
            condition=condition,
            sheet_name=sheet_name,
            save=save,
            output_path=output_path
        )
    
    @staticmethod
    def _excel_delete_columns_tool(file_path: str, columns: List[str], 
                                    sheet_name: str = None, save: bool = False, 
                                    output_path: str = None) -> Dict[str, Any]:
        """删除指定列"""
        return ExcelTool.delete_columns(
            file_path=file_path,
            columns=columns,
            sheet_name=sheet_name,
            save=save,
            output_path=output_path
        )
    
    @staticmethod
    def _excel_aggregate_tool(file_path: str, group_by: str, agg_dict: Dict[str, Any], 
                            sheet_name: str = None) -> Dict[str, Any]:
        """分组聚合"""
        return ExcelTool.aggregate(
            file_path=file_path,
            group_by=group_by,
            agg_dict=agg_dict,
            sheet_name=sheet_name
        )


    # Bash tool
    # @staticmethod
    # self.tool_registry.register(Tool(
    #     name="bash",
    #     description="Execute shell command",
    #     function=self._bash_tool,
    #     parameters={
    #         "command": {"type": "string", "description": "Command to execute"},
    #         "timeout": {"type": "integer", "description": "Timeout in milliseconds", "optional": True}
    #     }
    # ))

# 测试示例（替换为你的实际命令）
if __name__ == "__main__":
    # 测试 pandoc 命令（解决中文路径和编码问题）
    test_command = 'python read_docx.py C:\\Users\\sur\\Videos\\无人机产业对接活动方案-1101.docx'
    test_cwd = "D:\\workspace_python\\python-aickoo"

    result = ToolFactory._powershell_tool(test_command)
    print("标准输出:", result["stdout"])
    print("错误输出:", result["stderr"])
    print("返回码:", result["returncode"])
