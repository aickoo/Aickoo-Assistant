#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.

Database module for Aickoo-Assistant
"""

import os
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from aickoo import logging
from aickoo.internal.config import Config
from uuid import uuid4
import json
import time


@dataclass
class Session:
    """Session model"""
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    parent_id: Optional[str] = None
    summary: Optional[str] = None


@dataclass
class Message:
    """Message model"""
    id: str
    session_id: str
    role: str  # "user", "assistant", "system"
    content: str
    created_at: datetime
    reasoning_content: str = None
    tool_calls: Optional[List[Dict]] = None
    tool_results: Optional[List[Dict]] = None
    tool_call_id: Optional[str] = None


@dataclass
class File:
    """File model"""
    id: str
    session_id: str
    path: str
    content_hash: str
    created_at: datetime


@dataclass
class Conversation:
    """Conversation model - stores chat messages for eel_ui"""
    id: str
    session_id: str
    content: str
    role: str  # "user", "assistant", "system"
    created_at: datetime


class Database:
    """Database connection and operations"""
    
    def __init__(self, config: Config):
        self.config = config
        self.conn: Optional[sqlite3.Connection] = None
        
    def connect(self) -> sqlite3.Connection:
        """Connect to database and run migrations"""
        if self.conn:
            return self.conn
        
        # Create data directory if it doesn't exist
        data_dir = Path(self.config.data_directory)
        data_dir.mkdir(parents=True, exist_ok=True)
        
        db_path = data_dir / "history.db"
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        
        # Run migrations
        self._run_migrations()
        
        logging.info(f"Connected to database at {db_path}")
        return self.conn
    
    def _run_migrations(self) -> None:
        """Run database migrations"""
        cursor = self.conn.cursor()
        
        # Create sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                parent_id TEXT,
                summary TEXT,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                FOREIGN KEY (parent_id) REFERENCES sessions (id)
            )
        """)
        
        # Create messages table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                reasoning_content TEXT NOT NULL,
                tool_calls TEXT,
                tool_results TEXT,
                tool_call_id TEXT,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
            )
        """)
        
        # Create files table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                path TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
            )
        """)
        
        # Create conversation table for eel_ui chat messages
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversation (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                content TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages (session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages (created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions (updated_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_session_id ON files (session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversation_session_id ON conversation (session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversation_created_at ON conversation (created_at)")
        
        self.conn.commit()
        logging.info("Database migrations completed")
    
    def close(self) -> None:
        """Close database connection"""
        if self.conn:
            self.conn.close()
            self.conn = None
            logging.info("Database connection closed")
    
    # Session operations
    def create_session(self, title: str, parent_id: Optional[str] = None, 
                      summary: Optional[str] = None) -> Session:
        """Create a new session"""
        from uuid import uuid4
        import time
        
        session_id = str(uuid4())
        now = datetime.fromtimestamp(time.time())
        
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO sessions (id, title, parent_id, summary, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session_id, title, parent_id, summary, now, now))
        
        self.conn.commit()
        
        return Session(
            id=session_id,
            title=title,
            parent_id=parent_id,
            summary=summary,
            created_at=now,
            updated_at=now
        )
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return Session(
            id=row["id"],
            title=row["title"],
            parent_id=row["parent_id"],
            summary=row["summary"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"])
        )
    
    def list_sessions(self, limit: int = 100, offset: int = 0) -> List[Session]:
        """List all sessions ordered by updated_at"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM sessions 
            ORDER BY updated_at DESC 
            LIMIT ? OFFSET ?
        """, (limit, offset))
        
        sessions = []
        for row in cursor.fetchall():
            sessions.append(Session(
                id=row["id"],
                title=row["title"],
                parent_id=row["parent_id"],
                summary=row["summary"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"])
            ))
        
        return sessions
    
    def update_session(self, session_id: str, title: Optional[str] = None, 
                      summary: Optional[str] = None) -> Optional[Session]:
        """Update a session"""
        import time
        
        updates = []
        params = []
        
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        
        if summary is not None:
            updates.append("summary = ?")
            params.append(summary)
        
        if not updates:
            return self.get_session(session_id)
        
        updates.append("updated_at = ?")
        params.append(datetime.fromtimestamp(time.time()))
        params.append(session_id)
        
        cursor = self.conn.cursor()
        cursor.execute(f"""
            UPDATE sessions 
            SET {', '.join(updates)}
            WHERE id = ?
        """, params)
        
        self.conn.commit()
        
        return self.get_session(session_id)
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self.conn.commit()
        
        return cursor.rowcount > 0
    
    # Message operations
    def create_message(self, session_id: str, role: str, content: str,
                       reasoning_content: str='',
                       tool_calls: Optional[List[Dict]] = None,
                       tool_results: Optional[List[Dict]] = None,
                       tool_call_id: Optional[str] = None) -> Message:
        """Create a new message"""
        message_id = str(uuid4())
        now = datetime.fromtimestamp(time.time())
        
        tool_calls_json = json.dumps(tool_calls) if tool_calls else None
        tool_results_json = json.dumps(tool_results) if tool_results else None
        
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO messages (id, session_id, role, content, reasoning_content, tool_calls, tool_results, tool_call_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (message_id, session_id, role, content, reasoning_content, tool_calls_json, tool_results_json, tool_call_id, now))
        
        # Update session updated_at
        cursor.execute("""
            UPDATE sessions 
            SET updated_at = ? 
            WHERE id = ?
        """, (now, session_id))
        
        self.conn.commit()
        
        return Message(
            id=message_id,
            session_id=session_id,
            role=role,
            content=content,
            reasoning_content=reasoning_content,
            tool_calls=tool_calls,
            tool_results=tool_results,
            tool_call_id=tool_call_id,
            created_at=now
        )

    def create_message_without_store_db(self, session_id: str, role: str, content: str,
                       tool_calls: Optional[List[Dict]] = None,
                       tool_results: Optional[List[Dict]] = None) -> Message:
        """Create a new message"""
        message_id = str(uuid4())
        now = datetime.fromtimestamp(time.time())

        return Message(
            id=message_id,
            session_id=session_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
            tool_results=tool_results,
            created_at=now
        )
    
    def get_messages(self, session_id: str, limit: int = 100, 
                    offset: int = 0) -> List[Message]:
        """Get messages for a session"""
        import json
        
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM messages 
            WHERE session_id = ? 
            ORDER BY ROWID ASC 
            LIMIT ? OFFSET ?
        """, (session_id, limit, offset))
        
        messages = []
        for row in cursor.fetchall():
            tool_calls = json.loads(row["tool_calls"]) if row["tool_calls"] else None
            tool_results = json.loads(row["tool_results"]) if row["tool_results"] else None
            
            messages.append(Message(
                id=row["id"],
                session_id=row["session_id"],
                role=row["role"],
                content=row["content"],
                reasoning_content=row['reasoning_content'],
                tool_calls=tool_calls,
                tool_results=tool_results,
                tool_call_id=row['tool_call_id'],
                created_at=datetime.fromisoformat(row["created_at"])
            ))
        
        return messages

    def get_max_messages_with_first_line(self, session_id: str, limit: int = 50) -> List[Message]:
        """Get messages for a session"""
        cursor = self.conn.cursor()

        # 合并第一行和排除第一行的倒数前十行，并自动去重, 最后按时间排序
        cursor.execute(f"""
        SELECT *, ROWID FROM (
            SELECT *, ROWID 
            FROM messages 
            WHERE session_id = ? 
            ORDER BY ROWID 
            LIMIT 1
        ) AS first_row""", (session_id,))
        all = cursor.fetchall()

        limit_clause = '' if limit is None else ("LIMIT " + limit)
        cursor.execute(f"""
        SELECT *, ROWID FROM (
            SELECT *, ROWID 
            FROM messages 
            WHERE session_id = ?
            ORDER BY ROWID DESC 
            {limit_clause}
        ) AS last_ten_rows_exclude_first
        ORDER BY ROWID ASC;
        """, (session_id,) )
        results = cursor.fetchall()

        if results and len(results) > 0 and results[0]["role"] == "tool":
            cursor.execute(f"""
                    SELECT *, ROWID FROM (
                        SELECT *, ROWID 
                        FROM messages 
                        WHERE session_id = ? AND ROWID < ?
                        ORDER BY ROWID DESC;
            """, (session_id, results[0]["id"]))
            for row in cursor.fetchall():
                results.insert(0, row)
                if row['tool_calls'] is not None:
                    break

        # 当第一个和后面的第一个为相同对象的时候，去重
        if all and len(results) > 0 and all[0]['id'] == results[0]['id']:
            all = results
        else:
            all.extend(results)

        messages = []
        for row in all:
            tool_calls = json.loads(row["tool_calls"]) if row["tool_calls"] else None
            tool_results = json.loads(row["tool_results"]) if row["tool_results"] else None

            messages.append(Message(
                id=row["id"],
                session_id=row["session_id"],
                role=row["role"],
                content=row["content"],
                reasoning_content=row['reasoning_content'],
                tool_calls=tool_calls,
                tool_results=tool_results,
                tool_call_id=row['tool_call_id'],
                created_at=datetime.fromisoformat(row["created_at"])
            ))

        return messages

    
    def delete_messages(self, session_id: str) -> int:
        """Delete all messages for a session"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        self.conn.commit()
        
        return cursor.rowcount

    def clear_messages(self) -> int:
        """Delete all messages for a session"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM messages")
        self.conn.commit()

        return cursor.rowcount
    
    # File operations
    def create_file(self, session_id: str, path: str, content_hash: str) -> File:
        """Create a new file record"""
        from uuid import uuid4
        import time
        
        file_id = str(uuid4())
        now = datetime.fromtimestamp(time.time())
        
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO files (id, session_id, path, content_hash, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (file_id, session_id, path, content_hash, now))
        
        self.conn.commit()
        
        return File(
            id=file_id,
            session_id=session_id,
            path=path,
            content_hash=content_hash,
            created_at=now
        )
    
    def get_files(self, session_id: str) -> List[File]:
        """Get files for a session"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM files 
            WHERE session_id = ? 
            ORDER BY created_at ASC
        """, (session_id,))
        
        files = []
        for row in cursor.fetchall():
            files.append(File(
                id=row["id"],
                session_id=row["session_id"],
                path=row["path"],
                content_hash=row["content_hash"],
                created_at=datetime.fromisoformat(row["created_at"])
            ))
        
        return files
    
    def delete_files(self, session_id: str) -> int:
        """Delete all files for a session"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM files WHERE session_id = ?", (session_id,))
        self.conn.commit()
        
        return cursor.rowcount
    
    # Conversation operations
    def create_conversation(self, session_id: str, content: str, role: str) -> Conversation:
        """Create a new conversation record"""
        conversation_id = str(uuid4())
        now = datetime.fromtimestamp(time.time())
        
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO conversation (id, session_id, content, role, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (conversation_id, session_id, content, role, now))
        
        self.conn.commit()
        
        return Conversation(
            id=conversation_id,
            session_id=session_id,
            content=content,
            role=role,
            created_at=now
        )
    
    def get_conversations(self, session_id: str, limit: int = 100, 
                         offset: int = 0) -> List[Conversation]:
        """Get conversations for a session"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM conversation 
            WHERE session_id = ? 
            ORDER BY created_at ASC 
            LIMIT ? OFFSET ?
        """, (session_id, limit, offset))
        
        conversations = []
        for row in cursor.fetchall():
            conversations.append(Conversation(
                id=row["id"],
                session_id=row["session_id"],
                content=row["content"],
                role=row["role"],
                created_at=datetime.fromisoformat(row["created_at"])
            ))
        
        return conversations

    def get_conversation_history(self, session_id: str, limit: int = None) -> []:
        limit_clause = '' if limit is None else ("LIMIT " + str(limit))

        """Get conversations for a session"""
        cursor = self.conn.cursor()
        cursor.execute(f"""
            SELECT * FROM conversation
            WHERE session_id = '{session_id}'
            ORDER BY created_at ASC
            {limit_clause}
        """)

        conversations = []
        for row in cursor.fetchall():
            conversations.append({'role': row["role"], 'content': row["content"]})

        return conversations
    
    def delete_conversations(self, session_id: str) -> int:
        """Delete all conversations for a session"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM conversation WHERE session_id = ?", (session_id,))
        self.conn.commit()
        
        return cursor.rowcount


def connect_db(config: Optional[Config] = None) -> Database:
    """Connect to database with default config if not provided"""
    if config is None:
        from ..config import Config
        config = Config()
    
    db = Database(config)
    db.connect()
    return db