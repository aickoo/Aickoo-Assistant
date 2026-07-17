#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.

Permissions management for Aickoo-Assistant
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum


class PermissionLevel(Enum):
    """Permission levels"""
    DENY = "deny"
    ALLOW = "allow"
    ALLOW_SESSION = "allow_session"


@dataclass
class Permission:
    """Permission for a specific tool"""
    tool: str
    level: PermissionLevel
    reason: Optional[str] = None


class Permissions:
    """Manages permissions for tools"""
    
    def __init__(self):
        self._permissions: Dict[str, Permission] = {}
        self._session_permissions: Dict[str, Permission] = {}
    
    def check(self, tool: str, default: PermissionLevel = PermissionLevel.DENY) -> PermissionLevel:
        """Check permission for a tool"""
        # Check session permissions first
        if tool in self._session_permissions:
            return self._session_permissions[tool].level
        
        # Check persistent permissions
        if tool in self._permissions:
            return self._permissions[tool].level
        
        return default
    
    def grant(self, tool: str, level: PermissionLevel, reason: Optional[str] = None,
             persistent: bool = True) -> None:
        """Grant permission for a tool"""
        permission = Permission(tool=tool, level=level, reason=reason)
        
        if persistent:
            self._permissions[tool] = permission
        else:
            self._session_permissions[tool] = permission
    
    def revoke(self, tool: str) -> None:
        """Revoke permission for a tool"""
        if tool in self._permissions:
            del self._permissions[tool]
        if tool in self._session_permissions:
            del self._session_permissions[tool]
    
    def clear_session_permissions(self) -> None:
        """Clear all session permissions"""
        self._session_permissions.clear()
    
    def get_all(self) -> Dict[str, Permission]:
        """Get all permissions"""
        return {**self._permissions, **self._session_permissions}