#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.

Message management for Aickoo-Assistant
"""

from typing import List, Optional, Dict, Any
from ..db import Database, Message as DBMessage


class MessageManager:
    """Manages messages"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def create_message(self, session_id: str, role: str, content: str,
                       reasoning_content:str = '',
                       tool_calls: Optional[List[Dict]] = None,
                       tool_results: Optional[List[Dict]] = None,
                       tool_call_id: Optional[str] = None) -> DBMessage:
        """Create a new message"""
        return self.db.create_message(session_id, role, content, reasoning_content, tool_calls, tool_results, tool_call_id)

    def create_message_without_store_db(self, session_id: str, role: str, content: str,
                      tool_calls: Optional[List[Dict]] = None,
                      tool_results: Optional[List[Dict]] = None) -> DBMessage:
        """Create a new message without store db"""
        return self.db.create_message_without_store_db(session_id, role, content, tool_calls, tool_results)
    
    def get_messages(self, session_id: str, limit: int = 100,
                    offset: int = 0) -> List[DBMessage]:
        """Get messages for a session"""
        return self.db.get_messages(session_id, limit, offset)

    def get_max_messages_with_first_line(self, session_id: str, limit: int = 100) -> List[DBMessage]:
        """Get max limit messages and first line for a session"""
        return self.db.get_max_messages_with_first_line(session_id, limit)
    
    def delete_messages(self, session_id: str) -> int:
        """Delete all messages for a session"""
        return self.db.delete_messages(session_id)

    def clear_messages(self) -> int:
        """Delete all messages for a session"""
        return self.db.clear_messages()
    
    def get_conversation_history(self, session_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        """Get conversation history in a format suitable for AI models"""
        return self.db.get_conversation_history(session_id)
    
    def save_conversation(self, session_id: str, content: str, role: str) -> None:
        """Save a message to the conversation table"""
        self.db.create_conversation(session_id, content, role)

    def get_message_history(self, session_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        """Get conversation history in a format suitable for AI models"""
        # messages = self.get_messages(session_id, limit=limit)
        messages = self.get_max_messages_with_first_line(session_id, limit=limit)

        history = []
        for msg in messages:

            if msg.role == 'tool':
                message_data = {
                    "role": msg.role,
                    "content": msg.content,
                    "tool_call_id": msg.tool_call_id
                }
            else:
                message_data = {
                    "role": msg.role,
                    "content": msg.content,
                    "reasoning_content": msg.reasoning_content
                }

                # Add tool calls if present
                if msg.tool_calls:
                    message_data["tool_calls"] = msg.tool_calls

                # Add tool results if present
                if msg.tool_results:
                    message_data["tool_results"] = msg.tool_results

            history.append(message_data)

        return history


class FinishReason:
    FinishReasonEndTurn = "end_turn"      # ✅ 正常完成
    FinishReasonMaxTokens = "max_tokens"    # ⚠️ 达到 token 上限
    FinishReasonToolUse = "tool_use"      # 🔧 需要工具调用
    FinishReasonToolCall = "tool_calls"  # 🔧 需要工具调用
    FinishReasonCanceled = "canceled"      # ❌ 用户取消
    FinishReasonError = "error"          # ❌ 执行错误
    FinishReasonPermissionDenied = "permission_denied"  # ❌ 权限拒绝