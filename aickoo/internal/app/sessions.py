#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.

Session management for Aickoo-Assistant
"""

from typing import List, Optional
from ..db import Database, Session as DBSession


class SessionManager:
    """Manages sessions"""
    
    def __init__(self, db: Database):
        self.db = db
        self.current_session: Optional[DBSession] = None
    
    def create_session(self, title: str, parent_id: Optional[str] = None,
                      summary: Optional[str] = None) -> DBSession:
        """Create a new session"""
        session = self.db.create_session(title, parent_id, summary)
        self.current_session = session
        return session
    
    def get_session(self, session_id: str) -> Optional[DBSession]:
        """Get a session by ID"""
        return self.db.get_session(session_id)
    
    def list_sessions(self, limit: int = 100, offset: int = 0) -> List[DBSession]:
        """List all sessions"""
        return self.db.list_sessions(limit, offset)
    
    def update_session(self, session_id: str, title: Optional[str] = None,
                      summary: Optional[str] = None) -> Optional[DBSession]:
        """Update a session"""
        return self.db.update_session(session_id, title, summary)
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session"""
        if self.current_session and self.current_session.id == session_id:
            self.current_session = None
        
        return self.db.delete_session(session_id)
    
    def set_current_session(self, session: DBSession) -> None:
        """Set the current session"""
        self.current_session = session
    
    def get_current_session(self) -> Optional[DBSession]:
        """Get the current session"""
        return self.current_session
    
    def compact_session(self, session_id: str) -> Optional[DBSession]:
        """Compact a session by creating a summary"""
        # Get the session
        session = self.get_session(session_id)
        if not session:
            return None
        
        # Get messages for the session
        messages = self.db.get_messages(session_id)
        
        # Create a summary (in a real implementation, this would use AI)
        summary = f"Session with {len(messages)} messages"
        
        # Update session with summary
        return self.update_session(session_id, summary=summary)