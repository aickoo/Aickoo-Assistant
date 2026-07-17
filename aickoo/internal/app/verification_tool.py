#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.

Verification Tool for Aickoo-Assistant
"""

from typing import Dict, Any
from aickoo.internal.app.tools import Tool


class VerificationTool:
    """Tool for accessing the Verification Agent"""
    
    @staticmethod
    def create_verification_tool():
        return Tool(
            name="verify",
            description="Perform adversarial verification of code or system design",
            function=VerificationTool._verify_tool,
            parameters={
                "type": {"type": "string", "description": "Type of verification: 'code' or 'design'"},
                "content": {"type": "string", "description": "Code or design description to verify"},
                "language": {"type": "string", "description": "Programming language (for code verification)", "optional": True},
                "context": {"type": "string", "description": "Additional context", "optional": True}
            }
        )
    
    @staticmethod
    def _verify_tool(type: str, content: str, language: str = "python", context: str = "") -> Dict[str, Any]:
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
            
            # Create message manager
            message_manager = MessageManager(db)
            
            # Create permissions
            permissions = Permissions(config)
            
            # Create verification agent
            agent = VerificationAgent(config, permissions, message_manager, db)
            
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
