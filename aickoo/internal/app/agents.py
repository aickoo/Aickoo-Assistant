#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.

AI agents for Aickoo-Assistant
"""

import asyncio

from mpmath.calculus.extrapolation import limit

from aickoo.internal.config import AgentConfig
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from aickoo import logging
from aickoo.internal.config import Config
from aickoo.internal.db import Message
from aickoo.internal.app.permissions import Permissions
from aickoo.internal.app.tools import ToolRegistry, ToolFactory, ToolKitRegistry, McpToolKit
from aickoo.internal.app.messages import FinishReason
from aickoo.internal.app.llm import DeepseekClient, LLMResponse
from aickoo.internal.util.prompt_util import get_environment_info, lsp_information, count_tokens, get_message_tokens
from aickoo.internal.util.utils import detect_and_convert_to_utf8
from aickoo.internal.listener import emit_thinking_event
import json
import ast
from concurrent.futures import ThreadPoolExecutor
from aickoo.internal.app.messages import MessageManager

class BaseAgent:
    """Base class for AI agents"""
    # 上下文配置（适配130000 token上限）
    CONTEXT_WINDOW_TOTAL = 130000  # 模型总上下文
    CONTEXT_RESERVE = 15000  # 预留token（系统提示+输出）
    CONTEXT_AVAILABLE = CONTEXT_WINDOW_TOTAL - CONTEXT_RESERVE  # 115000
    TOOL_OUTPUT_MAX_TOKENS = 40000  # 保留最近工具输出的token上限
    HISTORY_MAX_TOKENS = 80000  # 保留最近工具输出的token上限
    SUMMARY_TRIGGER_THRESHOLD = 100000  # 超过这个值才触发摘要
    
    def __init__(self, config: AgentConfig, permissions: Permissions, message_manager: MessageManager):
        self.config = config
        self.permissions = permissions
        self.message_manager = message_manager
        self.prompt = config.prompt
        self.tool_registry = ToolRegistry()
        self.llm_client = self._create_llm_client()
        self._setup_tools()
    
    def _setup_tools(self) -> None:
        """Setup available tools"""
        config_tools = self.config.tools
        config_mcps = self.config.mcp

        for tool_name in config_tools:
            # if tool_name == 'mcp':
            #     continue
            tools = ToolKitRegistry.get_tools_by_name(tool_name)
            for tool in tools:
                self.tool_registry.register(tool)

        if config_mcps:
            mcp_toolkit = McpToolKit(allowed_mcp=config_mcps)
            for tool in mcp_toolkit.get_tools():
                self.tool_registry.register(tool)

        config_skills = self.config.skills
        for skill in ToolFactory.create_tools_all_skills():
            if skill.name[6:] in config_skills:
                self.tool_registry.register(skill)

    def _create_llm_client(self):
        """Create LLM client based on configuration"""
        if not self.config:
            # Default to a simple echo client for now
            return EchoClient()
            # return DeepseekClient()

        # Check which provider to use based on model
        model = self.config.model.lower()

        if "claude" in model:
            return AnthropicClient(self.config)
        elif "gpt" in model:
            return OpenAIClient(self.config)
        elif "gemini" in model:
            return GeminiClient(self.config)
        elif "deepseek" in model:
            return DeepseekClient(self.config)
        else:
            # Fallback to echo client
            logging.warn(f"Unsupported model: {model}, using echo client")
            return EchoClient()

    def process_message(self, session_id: str, message: Message, conversation_history: List[str] = None,  quiet: bool = False):

        """Process a message and return response - 轻量修剪版本"""

        history = []
        # insert system prompt into history
        system_prompt = self.system_prompt() if callable(self.system_prompt) else self.system_prompt
        if system_prompt is not None and system_prompt != '':
            history.append({"role": "system", "content": system_prompt})
            # 计算系统提示的token消耗
            system_tokens = get_message_tokens(history[-1])

        # For EchoClient, we don't have a database connection
        # Create a temporary message manager with the app's db if available
        if self.message_manager is not None:
            message_manager = self.message_manager
        if hasattr(self, '_db') and self._db:
            message_manager = MessageManager(self._db)
        elif hasattr(self.llm_client, 'db') and self.llm_client.db:
            message_manager = MessageManager(self.llm_client.db)
        else:
            # Fallback: return simple response without history
            return self.llm_client.generate_response([], self.tool_registry.get_tools(), quiet).content

        # 获取完整历史（不再限制条数，改为按token筛选）
        old_history = message_manager.get_message_history(session_id, limit=None)  # 取消条数限制
        
        # 将conversation历史记录添加到old_history之前，作为额外的上下文
        if conversation_history:
            old_history = conversation_history + old_history

        # 1. 轻量修剪：处理工具输出，保留最近的TOOL_OUTPUT_MAX_TOKENS
        pruned_history = self._lightweight_pruning(old_history)

        # 2. 计算当前历史的总token数
        total_tokens = system_tokens + sum([get_message_tokens(msg) for msg in pruned_history])

        # 3. 动态触发摘要：仅当接近阈值时才摘要
        processed_history = []
        if total_tokens > self.SUMMARY_TRIGGER_THRESHOLD:
            # 拆分历史：旧部分摘要，新部分保留完整
            processed_history = self._dynamic_summarization(pruned_history, total_tokens)
        else:
            # 未达阈值，直接使用修剪后的历史
            processed_history = pruned_history

        # 合并系统提示和处理后的历史
        final_history = history + processed_history

        # print('\n*************************************************************************************************************************************\n')
        # print(final_history)

        # Call LLM
        response = None
        try:
            response = self.llm_client.generate_response(
                messages=final_history,
                tools=self.tool_registry.get_tools(),
                quiet=quiet
            )
        except Exception as e:
            print(str(e))

        # Emit thinking event
        if response and hasattr(response, 'content'):
            emit_thinking_event(response.content)

        # Execute tool calls if any
        tool_results = []
        tool_calls = []
        tool_call_message = None
        tool_result_message = None
        if response.tool_calls:
            for tool_call in response.tool_calls:
                tool_id = tool_call.get('id')
                tool_name = tool_call.get("name")
                tool_args = tool_call.get("arguments", {})
                tool_calls.append({
                    "id": tool_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(tool_args, ensure_ascii=False)
                    }
                })

        # append tool_call to history
        tool_call_message = message_manager.create_message(session_id, "assistant", response.content, response.reasoning_content, tool_calls, None)

        if len(tool_calls) > 0:
            # Execute tool
            for tool_call in tool_calls:
                tool_call_id = tool_call.get('id')
                tool_name = tool_call.get('function').get("name")
                tool_args = tool_call.get('function').get("arguments", {})
                result_content = ''
                try:
                    result = self.tool_registry.execute(name=tool_name, **json.loads(tool_args))
                    result_content = json.dumps(result, ensure_ascii=False)
                    # 轻量修剪：工具结果超过上限时才摘要
                    if count_tokens(result_content) > self.TOOL_OUTPUT_MAX_TOKENS:
                        result_content = self.llm_summarize(result_content, quiet).content
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": result_content
                    })
                except Exception as e:
                    result_content = str(e)
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": result_content
                    })

                # append tool_result to history
                tool_result_message = message_manager.create_message(session_id, "tool", result_content, '', None, None, tool_call_id)

        # return
        return response, tool_results, tool_result_message if tool_result_message is not None else tool_call_message if tool_call_message is not None else message if message is not None else None

    def _lightweight_pruning(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        修复版轻量修剪：只清理最旧的tool结果，保留最新的tool结果
        核心逻辑：
        1. 从前往后遍历（最旧→最新）
        2. 先累计旧tool的token，超上限则标记清理
        3. 最新的tool结果完整保留，不做任何清理
        4. 保证tool call和tool结果的配对不中断
        """
        # 若history长度在范围之内则不用修剪，直接返回原数据
        if len(str(history)) < self.HISTORY_MAX_TOKENS:
            return history

        pruned_history = []

        # 第一步：分离“旧历史”和“最新的tool结果段”
        # 从最近往以前找最后一个tool结果的位置（最新的tool结果开始的索引）
        last_tool_index = -1
        for i in reversed(range(len(history) - 1)):
            if history[i].get('role') == 'tool':
                last_tool_index = i
                break

        # 划分：旧历史（0 ~ last_tool_index-1） + 最新tool段（last_tool_index ~ 末尾）
        old_history = history[:(last_tool_index+1)] if last_tool_index != -1 else []
        latest_history = history[(last_tool_index+1):] if last_tool_index != -1 else history

        len_latest_history = len(str(latest_history))  # latest history 字符数量
        # 第二步：处理旧历史（只清理这里的旧tool结果）
        for msg in old_history:
            role = msg.get('role', '')
            if role == 'tool':
                len_history = len(str(old_history)) + len_latest_history
                # 如果超出最大允许的长度，继续清理当前tool msg的内容。否则内容保留
                if len_history > self.HISTORY_MAX_TOKENS:
                    msg['content'] = "[result cleared]"

        pruned_history.extend(old_history)

        # 第三步：拼接“处理后的旧历史” + “完整保留的最新tool段”
        # 最新的tool结果段完整保留，不做任何清理
        pruned_history.extend(latest_history)

        # 最终检查：确保没有未配对的tool call
        self._ensure_tool_pairing(pruned_history)

        return pruned_history

    def _ensure_tool_pairing(self, history: List[Dict[str, Any]]) -> None:
        """
        保障tool call和tool结果的配对：
        如果有未配对的tool call，补充一个空的tool结果标记，避免模型错乱
        """
        for i in range(len(history) - 1):
            current_msg = history[i]
            next_msg = history[i + 1]

            # 检查：当前是带tool call的assistant消息，下一条不是tool消息
            if (current_msg.get('role') == 'assistant'
                    and current_msg.get('tool_calls')
                    and next_msg.get('role') != 'tool'):
                # 补充配对标记，避免模型找不到tool结果
                history.insert(i + 1, {
                    "role": "tool",
                    "tool_call_id": current_msg['tool_calls'][0]['id'] if current_msg['tool_calls'] else "",
                    "content": "[tool result pending - 该工具调用的结果未找到，可能已清理]"
                })

    def _dynamic_summarization(self, history: List[Dict[str, Any]], total_tokens: int) -> List[Dict[str, Any]]:
        """
        动态摘要：仅当token接近上限时触发
        拆分历史为：需要摘要的旧历史 + 保留完整的新历史
        """
        # 目标：摘要后总token控制在SUMMARY_TRIGGER_THRESHOLD以下
        target_tokens = self.SUMMARY_TRIGGER_THRESHOLD - self.CONTEXT_RESERVE
        current_tokens = 0
        split_index = 0

        # 找到拆分点：前面的摘要，后面的保留
        for i, msg in enumerate(history):
            current_tokens += get_message_tokens(msg)
            if current_tokens > target_tokens:
                split_index = i
                break

        if history[split_index]['role'] == 'tool' or (history[split_index]['role'] == 'assistant' and history[split_index]['tool_calls'] is not None):
            for i in range(split_index + 1, len(history)-1):
                if history[i]['role'] != 'tool':
                    break

                split_index = i

        # 对旧历史进行摘要
        old_part = history[:split_index + 1]
        new_part = history[split_index + 1:]

        if old_part:
            old_content = json.dumps(old_part, ensure_ascii=False)
            summary = self.llm_summarize(old_content, quiet=True)
            # 摘要结果作为system消息
            summary_msg = {
                "role": "system",
                "content": f"""【对话历史摘要】：\n{summary.content}\n\n以上是早期对话历史的核心摘要，保留了关键决策、任务进展和重要信息。"""
            }
            return [summary_msg] + new_part
        else:
            return history

    def llm_summarize(self, summerize_content, quiet, tools=[], max_tokens=12000):
        """优化摘要提示词，更贴合代码场景"""
        summarize_history = []
        summarize_history.append({
            "role": "system",
            "content": """你是专业的代码对话摘要助手，需要：
1. 提取核心需求：用户的核心编程任务、问题、目标
2. 保留关键决策：已做出的技术选择、代码修改、解决方案
3. 记录任务状态：已完成的步骤、待解决的问题、需要继续的工作
4. 忽略重复内容和临时工具输出
5. 摘要简洁但不丢失关键信息，控制在12000 token以内"""
        })
        summarize_history.append({
            "role": "user",
            "content": f"提取以下编程对话的核心摘要，保留关键信息：\n{summerize_content}"
        })
        summarize_response = self.llm_client.generate_response(
            messages=summarize_history,
            max_tokens=max_tokens,
            tools=tools,
            quiet=quiet
        )
        return summarize_response

    def process_message_loop(self, session_id: str, message: Message, conversation_history: List[str] = None, quiet: bool = False):
        """修复原代码中重复定义process_message的问题，改为循环处理工具调用"""
        while True:
            response, tool_results, result_message = self.process_message(session_id, message, conversation_history, quiet)
            finish_reason = response.finish_reason
            if (finish_reason == FinishReason.FinishReasonToolUse or finish_reason == FinishReason.FinishReasonToolCall) and tool_results:
                # 需要执行工具 → 把结果加入历史，继续循环
                continue
            break
        return response, tool_results, result_message


    def llm_summarize(self, summerize_content, quiet, tools=[], max_tokens=12000):
        summarize_history = []
        summarize_history.append({"role": "system", "content": "你是一个文本摘要助手，需要提取文本的核心信息，保留关键内容，尽可能缩减长度但不丢失重要信息。"})
        summarize_history.append({"role": "user", "content": "提取以下文本的摘要：\n" + summerize_content})
        summarize_response = self.llm_client.generate_response(
            messages=summarize_history,
            max_tokens=max_tokens,
            tools=tools,  # self.tool_registry.get_tools(),
            quiet=quiet
        )
        return summarize_response

    def system_prompt(self):
        return ''
    
    def shutdown(self) -> None:
        """Shutdown the agent"""
        pass


class PrimaryAgent(BaseAgent):
    """Coder agent for code-related tasks"""
    
    def __init__(self, config: Config, permissions: Permissions, message_manager, db=None):
        super().__init__(config, permissions, message_manager)
        self._db = db  # Store database reference for message history

    def system_prompt(self):
        env = get_environment_info(self.config) if self.config.prompt_extra_env else ""
        lsp = lsp_information() if self.config.prompt_extra_lsp else ""
        return f'{self.prompt}\n{env}\n{lsp}'

    def process_message_loop(self, session_id: str, message: Message, quiet: bool = False):
        return super().process_message_loop(session_id, message, quiet)

    def start_process_message(self, session_id: str, content: str, role: str = 'user', conversation_history: List[str] = None, quiet: bool = False):
        # Create user message
        logging.debug(f"Creating user message for session: {session_id}")
        user_message = self.message_manager.create_message(
            session_id=session_id,
            role=role,
            content=content
        )
        return super().process_message_loop(session_id, user_message, conversation_history, quiet)


class Agent(BaseAgent):
    """Task Agent专用提示词"""

    def __init__(self, config: Config, permissions: Permissions, message_manager, db=None):
        super().__init__(config, permissions)
        self._db = db  # Store database reference for message history

    def system_prompt(self):
        return """You are an agent. Given the user's prompt, you should use the tools available to you to answer the user's question.
Notes:
1. IMPORTANT: You should be concise, direct, and to the point, since your responses will be displayed on a command line interface. 
2. When relevant, share file names and code snippets relevant to the query
3. Any file paths you return in your final response MUST be absolute. DO NOT use relative paths.
4. You can ONLY use read-only tools (glob, powershell, read). You CANNOT modify files or execute modify powershell commands that can modify files."""


class EchoClient:
    """Simple echo client for testing"""

    def __init__(self, agent_name: str = None):
        self.agent_name = agent_name
    
    def generate_response(self, messages: List[Dict], tools: List[Dict], 
                         quiet: bool = False) -> LLMResponse:
        """Generate a response by echoing the last message"""
        if not messages:
            return LLMResponse(content="Hello! I'm Aickoo-Assistant. How can I help you?")
        
        last_message = messages[-1]
        content = last_message.get("content", "")
        
        return LLMResponse(
            content=f"I received your message: {content}\n\n(This is an echo response. In production, this would call a real LLM, but you should config model for agent(${self.agent_name}) first.)"
        )


class OpenAIClient:
    """OpenAI client"""
    
    def __init__(self, agent_config, config):
        self.agent_config = agent_config
        self.config = config
    
    def generate_response(self, messages: List[Dict], tools: List[Dict], 
                         quiet: bool = False) -> LLMResponse:
        """Generate response using OpenAI"""
        # This would be implemented with the actual OpenAI SDK
        raise NotImplementedError("OpenAI client not fully implemented")


class AnthropicClient:
    """Anthropic Claude client"""
    
    def __init__(self, agent_config, config):
        self.agent_config = agent_config
        self.config = config
    
    def generate_response(self, messages: List[Dict], tools: List[Dict], 
                         quiet: bool = False) -> LLMResponse:
        """Generate response using Anthropic"""
        # This would be implemented with the actual Anthropic SDK
        raise NotImplementedError("Anthropic client not fully implemented")


class GeminiClient:
    """Google Gemini client"""
    
    def __init__(self, config):
        self.config = config
    
    def generate_response(self, messages: List[Dict], tools: List[Dict], 
                         quiet: bool = False) -> LLMResponse:
        """Generate response using Gemini"""
        # This would be implemented with the actual Gemini SDK
        raise NotImplementedError("Gemini client not fully implemented")



# ============================================================================
# 5. 高级功能：并行SubAgent调用
# ============================================================================

class ParallelAgentExecutor:
    """
    并行Agent执行器
    支持同时启动多个SubAgent任务
    """

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    async def execute_parallel(self, prompts: List[str]) -> List[str]:
        """
        并行执行多个SubAgent任务

        对应：
        - 在单个消息中同时调用多个agent工具
        - 使用asyncio.gather实现并行
        """
        print(f"\n[ParallelExecutor] Starting {len(prompts)} parallel tasks...")

        # 创建任务列表
        tasks = []
        for i, prompt in enumerate(prompts):
            task = self._run_single_agent(prompt, i)
            tasks.append(task)

        # 并行执行所有任务
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"  Task {i + 1} failed: {result}")
                processed_results.append(f"Error: {result}")
            else:
                print(f"  Task {i + 1} completed")
                processed_results.append(result)

        return processed_results

    async def _run_single_agent(self, prompt: str, index: int = 0) -> str:
        """运行单个SubAgent"""
        print(f"  [Task {index + 1}] Starting: {prompt[:50]}...")

        # 创建新的TaskAgent实例
        agent = ToolFactory.create_tool_agent()

        # 执行
        result = await agent.execute(prompt)

        return result

