#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.

Core application module for Aickoo-Assistant
"""

import asyncio
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from aickoo import logging
from aickoo.internal.config import Config
from aickoo.internal.db import Database, Session, Message
from aickoo.internal.app.permissions import Permissions
from aickoo.internal.app.sessions import SessionManager
from aickoo.internal.app.messages import MessageManager
from aickoo.internal.app.agents import PrimaryAgent
from aickoo.internal.app.orchestrator import SequentialOrchestrator
from aickoo.internal.app import llm
from aickoo.internal.app.plugins import load_plugin_agents


@dataclass
class App:
    """Main application class"""
    db: Database
    config: Config
    sessions: SessionManager = field(init=False)
    messages: MessageManager = field(init=False)
    primary_agent: PrimaryAgent = field(init=False)
    primary_agent_dict: Dict = field(default_factory=dict)
    permissions: Permissions = field(default_factory=Permissions)
    _running: bool = False
    
    def __post_init__(self):
        """Initialize application components"""
        # 设置全局配置到 llm 模块
        llm.set_global_config(self.config)

        self.sessions = SessionManager(self.db)
        self.messages = MessageManager(self.db)

        # 清除消息历史记录
        self.messages.clear_messages()

        # primary agent
        for name, agent_config in self.config.agents.items():
            # put primary agent to dict
            self.primary_agent_dict[agent_config.name] = PrimaryAgent(agent_config, self.permissions, self.messages, self.db)
            # set default primary agent
            # if hasattr(agent_config, 'role') and agent_config.role == 'primary':
            #     self.primary_agent = PrimaryAgent(agent_config, self.permissions, self.db)
            #     # break

        # if self.primary_agent is None:
        #     logging.error(f"没有指定任何的主代理（Primary Agent）, 可以通过在aickoo.json里添加role:primary实现")

        # 加载插件代理
        self.primary_agent_dict.update(load_plugin_agents())

        # 初始化编排器
        self.orchestrator = SequentialOrchestrator(
            # agent_factory={
            #     "primary": self.primary_agent,
            #     "task_agent": self.task_agent
            # },
            primary_agent_dict=self.primary_agent_dict,
            message_manager=self.messages
        )
    
    def run_interactive(self) -> None:
        """Run application in interactive mode"""
        self._running = True
        
        try:
            # Start Eel web interface - import inside method to avoid circular import
            from aickoo.internal.eel_ui import EelUI
            eel_ui = EelUI(self)
            eel_ui.run()
            
        except KeyboardInterrupt:
            logging.info("Application interrupted by user")
        except Exception as e:
            logging.error(f"Application error: {e}")
            raise
        finally:
            self.shutdown()
    
    def run_non_interactive(self, prompt: str, output_format: str = "text", 
                           quiet: bool = False) -> str:
        """Run application in non-interactive mode"""
        self._running = True
        
        try:
            # Create a temporary session
            session = self.sessions.create_session("Non-interactive session")
            
            # Add user message
            user_message = self.messages.create_message(
                session_id=session.id,
                role="user",
                content=prompt
            )
            
            # Get AI response
            response = self.primary_agent.process_message(
                session_id=session.id,
                message=user_message,
                quiet=quiet
            )
            
            # Add assistant message
            self.messages.create_message(
                session_id=session.id,
                role="assistant",
                content=response
            )
            
            return response
            
        except Exception as e:
            logging.error(f"Non-interactive mode error: {e}")
            raise
        finally:
            self.shutdown()
    
    def shutdown(self) -> None:
        """Shutdown application"""
        if not self._running:
            return
        
        self._running = False
        
        # Shutdown all agents
        for agent in self.primary_agent_dict.values():
            try:
                agent.shutdown()
            except Exception as e:
                logging.error(f"Error shutting down agent: {e}")
        
        # Close database connection
        self.db.close()
        
        logging.info("Application shutdown completed")