#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.

Verification Agent for Aickoo-Assistant
This agent performs adversarial verification to delete the security and robustness of code or systems.
"""

from typing import Dict, Any, Optional, List
from aickoo.internal.app.agents import BaseAgent, LLMResponse
from aickoo.internal.config import AgentConfig
from aickoo.internal.app.permissions import Permissions
from aickoo.internal.app.messages import MessageManager
from aickoo import logging


class VerificationAgent(BaseAgent):
    """Agent for performing adversarial verification"""
    
    def __init__(self, config: AgentConfig, permissions: Permissions, message_manager: MessageManager, db=None):
        super().__init__(config, permissions, message_manager)
        self._db = db  # Store database reference for message history

    def system_prompt(self):
        return """You are a Verification Agent specialized in adversarial testing and security verification.

Your primary goal is to identify vulnerabilities, edge cases, and potential failures in code or systems by taking an adversarial approach.

Core responsibilities:
1. Analyze code or system designs for potential security vulnerabilities
2. Generate delete cases that exploit edge cases and boundary conditions
3. Identify logical flaws and potential attack vectors
4. Provide detailed analysis of found issues with severity ratings
5. Suggest concrete remediation strategies

Approach:
- Think like an attacker - look for ways to bypass security controls
- Test boundary conditions and edge cases
- Analyze input validation and error handling
- Review authentication and authorization mechanisms
- Check for information disclosure vulnerabilities
- Evaluate overall system robustness

When analyzing code:
- Identify potential injection vulnerabilities (SQL, XSS, command injection)
- Check for insecure cryptography usage
- Review access control implementations
- Look for race conditions and concurrency issues
- Evaluate error handling and logging practices

Provide comprehensive reports with:
- Detailed description of each issue
- Severity rating (Critical/High/Medium/Low)
- Steps to reproduce the issue
- Potential impact
- Recommended fixes
"""

    def verify_code(self, code: str, language: str = "python", context: str = "") -> str:
        """
        Verify code for vulnerabilities and issues
        
        Args:
            code: The code to verify
            language: The programming language
            context: Additional context about the code
            
        Returns:
            A comprehensive verification report
        """
        prompt = f"""Please perform a comprehensive adversarial verification of the following {language} code:

```
{code}
```

Additional context:
{context}

Please analyze this code for:
1. Security vulnerabilities (injection, XSS, CSRF, etc.)
2. Edge cases and boundary conditions
3. Logical flaws and error handling issues
4. Performance and reliability concerns
5. Best practice violations

Provide a detailed report with:
- Issue description
- Severity rating (Critical/High/Medium/Low)
- Potential impact
- Steps to reproduce
- Recommended fix
"""
        
        # Create a temporary session for verification
        session_id = f"verification_{hash(code) % 1000000}"
        
        # Create user message
        user_message = self.message_manager.create_message(
            session_id=session_id,
            role="user",
            content=prompt
        )
        
        # Process the message
        response, tool_results, result_message = self.process_message_loop(session_id, user_message, quiet=True)
        
        return response.content

    def verify_system_design(self, design: str, context: str = "") -> str:
        """
        Verify system design for vulnerabilities and issues
        
        Args:
            design: The system design description
            context: Additional context about the system
            
        Returns:
            A comprehensive verification report
        """
        prompt = f"""Please perform a comprehensive adversarial verification of the following system design:

{design}

Additional context:
{context}

Please analyze this design for:
1. Security vulnerabilities and attack vectors
2. Architectural flaws
3. Scalability and reliability issues
4. Authentication and authorization weaknesses
5. Data protection concerns
6. Disaster recovery gaps

Provide a detailed report with:
- Issue description
- Severity rating (Critical/High/Medium/Low)
- Potential impact
- Recommended mitigation strategies
"""
        
        # Create a temporary session for verification
        session_id = f"verification_{hash(design) % 1000000}"
        
        # Create user message
        user_message = self.message_manager.create_message(
            session_id=session_id,
            role="user",
            content=prompt
        )
        
        # Process the message
        response, tool_results, result_message = self.process_message_loop(session_id, user_message, quiet=True)
        
        return response.content


class VerificationTool:
    """Tool for accessing the Verification Agent"""
    
    @staticmethod
    def create_verification_tool():
        from aickoo.internal.app.tools import Tool
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
            import os
            
            # Load configuration
            config = load_config(os.getcwd())
            
            # Create database connection
            db = Database(config)
            
            # Create message manager
            message_manager = MessageManager(db)
            
            # Create verification agent
            from aickoo.internal.app.permissions import Permissions
            permissions = Permissions(config)
            
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
